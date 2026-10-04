import { $, escapeHtml } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { onLangChange, t } from "../../../shared/i18n/js/i18n.js";
import { api } from "../../api.js";
import { state, searchEmpty, searchSkeleton, rememberSearch, clearRecentSearches } from "../../state.js";
import { ICO } from "../../ui/js/icons.js";
import { artHtml } from "../../../shared/ui/js/art.js";
import { showToast } from "../../ui/js/toast.js";
import { loadWho } from "../../ui/js/who.js";
import { handlePointError } from "../../ui/js/ads.js";
import { closeOverlay } from "../../ui/js/overlays.js";
import { repaintPreviewChrome, stopPreview, togglePreview } from "./preview.js";

/** Hit currently shown in the detail sheet; null while the sheet is closed. */
let sheetHit = null;
/** Hit ids imported during this result set; reset on every fresh search. */
const imported = new Set();
/** Lyrics candidates per hit id; filled when the detail sheet opens. */
const hitLyricsCache = new Map();
/** Lyric edition the singer pinned per hit id; falls back to the scored pick. */
const selectedLyric = new Map();
/** Monotonic request id so a slow lyric fetch cannot paint a stale sheet. */
let sheetLyricsReq = 0;

function hitById(id) {
  return state.searchHits.find((item) => String(item.id) === String(id));
}

/** ``escapeHtml`` leaves quotes alone, which is fine for text nodes but not
 *  for attribute values; ids/titles land in attributes here. */
function escapeAttr(text) {
  return escapeHtml(text).replace(/"/g, "&quot;");
}

function hitBadge(hit) {
  const isMv = hit.is_mv === true || hit.source === "mugen" || hit.source === "bilibili";
  return isMv ? "MV" : "";
}

/** Lyrics/duration pills shared by the card footer and the detail sheet. */
function hitMeta(hit) {
  const duration = Number(hit.duration || 0);
  const durationText =
    duration > 0 ? `${Math.floor(duration / 60)}:${String(Math.floor(duration % 60)).padStart(2, "0")}` : "";
  // ``null`` means no comparable LRC was found; Number(null) would turn it
  // into 0 and falsely present a real percentage.
  const lyricScore = hit.lyrics_match_score == null ? Number.NaN : Number(hit.lyrics_match_score);
  const lyricLabel = Number.isFinite(lyricScore)
    ? t("phone.search.lyricsMatch", { n: Math.round(lyricScore) })
    : hit.lyrics_match === "available"
      ? t("phone.search.lyricsAvailable")
      : hit.lyrics_match === "none"
        ? t("phone.search.lyricsNone")
        : t("phone.search.lyricsUnknown");
  const timingMatch =
    hit.duration_match === "exact"
      ? t("phone.search.durationExact")
      : hit.duration_match === "close"
        ? t("phone.search.durationClose")
        : "";
  const lyricTone = Number.isFinite(lyricScore)
    ? lyricScore >= 80
      ? "is-good"
      : lyricScore >= 50
        ? "is-mid"
        : "is-low"
    : hit.lyrics_match === "available"
      ? "is-good"
      : hit.lyrics_match === "none"
        ? "is-low"
        : "";
  return [
    `<i class="meta-pill ${lyricTone}"><span class="lyrics-match">${escapeHtml(lyricLabel)}</span></i>`,
    timingMatch ? `<i class="meta-pill is-good">${escapeHtml(timingMatch)}</i>` : "",
    durationText ? `<i>${durationText}</i>` : ""
  ].join("");
}

/** Buttons bound to one hit: the card add button plus the sheet buttons. */
function hitButtons(id) {
  const out = [];
  const cardBtn = $("hits").querySelector(`[data-hit-id="${id}"] .hit-add`);
  if (cardBtn) out.push(cardBtn);
  if (sheetHit && String(sheetHit.id) === String(id)) out.push($("hitSheetAdd"));
  return out;
}

/** Repaint add-button chrome (icon / label / done state) for imported hits. */
function repaintImportChrome(onlyId = "") {
  $("hits")
    .querySelectorAll(".hit-card")
    .forEach((card) => {
      if (onlyId && card.dataset.hitId !== String(onlyId)) return;
      const btn = card.querySelector(".hit-add");
      if (!btn) return;
      if (imported.has(card.dataset.hitId)) {
        btn.classList.add("on");
        btn.classList.remove("busy");
        btn.disabled = true;
        btn.setAttribute("aria-label", t("phone.search.added"));
        btn.innerHTML = ICO.check;
      } else if (!btn.classList.contains("busy")) {
        btn.innerHTML = ICO.plus;
      }
    });
  const add = $("hitSheetAdd");
  if (add && (!onlyId || (sheetHit && String(sheetHit.id) === String(onlyId)))) {
    if (sheetHit && imported.has(String(sheetHit.id))) {
      add.classList.add("on");
      add.classList.remove("busy");
      add.disabled = true;
      add.setAttribute("aria-label", t("phone.search.added"));
      add.innerHTML = `${ICO.check}<span>${t("phone.search.added")}</span>`;
    } else if (!add.classList.contains("busy")) {
      add.innerHTML = `${ICO.plus}<span>${t("phone.search.add")}</span>`;
    }
  }
}

async function runImport(hit, q) {
  if (!hit || !hit.id) return;
  const buttons = hitButtons(hit.id);
  stopPreview();
  buttons.forEach((btn) => {
    btn.disabled = true;
    btn.classList.add("busy");
  });
  if (sheetHit && String(sheetHit.id) === String(hit.id)) {
    $("hitSheetAdd").innerHTML = `${ICO.loading}<span>${t("common.loading")}</span>`;
  }
  const body = {
    query: q,
    id: hit.id,
    title: hit.title,
    artist: hit.artist,
    language: hit.language || "",
    source: hit.source || "",
    // Carry the lyric edition the singer picked in the sheet (or the one
    // scored during search); the importer can still re-check duration, but
    // must not start from an unrelated same-title result.
    lyrics_id: pickedLyricId(hit)
  };
  const {
    ok,
    status,
    data: created
  } = await fetchJson("/api/songs/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  buttons.forEach((btn) => {
    btn.disabled = false;
    btn.classList.remove("busy");
  });
  if (!ok || !created.id) {
    repaintImportChrome(hit.id);
    showToast(created.detail || t("phone.search.importFailed"));
    if (status === 402 || status === 429) handlePointError(status, created.detail);
    return;
  }
  imported.add(String(hit.id));
  repaintImportChrome(hit.id);
  showToast(t("phone.search.addedToast"));
  api.loadSongs();
  loadWho();
}

/** Lyric id the import should pin: user's pick, else the scored one. */
function pickedLyricId(hit) {
  const key = String(hit.id);
  if (selectedLyric.has(key)) return selectedLyric.get(key);
  if (hit.lyrics_id) return String(hit.lyrics_id);
  const cached = hitLyricsCache.get(key) || [];
  const best = cached.find((item) => item.recommended);
  return best ? String(best.id) : "";
}

function lyricRowHtml(hit, cand) {
  const score =
    cand.score == null
      ? `<i class="meta-pill">${t("phone.search.lyricsUnknown")}</i>`
      : `<i class="meta-pill ${cand.score >= 80 ? "is-good" : cand.score >= 50 ? "is-mid" : "is-low"}"><span class="lyrics-match">${escapeHtml(t("phone.search.lyricsMatch", { n: Math.round(cand.score) }))}</span></i>`;
  const best = cand.recommended ? `<i class="lyric-best">${t("phone.search.lyricBest")}</i>` : "";
  const duration = Number(cand.last_ms || 0);
  const durationText =
    duration > 0
      ? `${Math.floor(duration / 60000)}:${String(Math.floor((duration % 60000) / 1000)).padStart(2, "0")}`
      : "";
  const lines = (cand.lines || []).map((line) => `<span>${escapeHtml(line)}</span>`).join("");
  const on = String(cand.id) === pickedLyricId(hit);
  return `<button type="button" class="hit-lyric${on ? " on" : ""}" data-lyric="${escapeAttr(cand.id)}">
    <span class="hit-lyric-top"><b>${escapeHtml(cand.title || hit.title)}</b><span class="tiny">${escapeHtml(cand.artist || "")}</span>${durationText ? `<i>${durationText}</i>` : ""}${score}${best}</span>
    ${lines ? `<span class="hit-lyric-lines">${lines}</span>` : ""}
  </button>`;
}

/** Paint the lyric-version list inside the open sheet. ``candidates`` is
 *  ``null`` when the request failed so the state reads as an error. */
function paintSheetLyrics(hit, candidates) {
  const list = $("hitLyrics");
  if (!list) return;
  if (hit.source === "mugen") {
    list.innerHTML = `<p class="tiny hit-lyrics-note">${t("phone.search.lyricBundled")}</p>`;
    return;
  }
  if (candidates === null) {
    list.innerHTML = `<p class="tiny hit-lyrics-note">${t("phone.search.lyricFailed")}</p>`;
    return;
  }
  if (!candidates || !candidates.length) {
    list.innerHTML = `<p class="tiny hit-lyrics-note">${t("phone.search.lyricEmpty")}</p>`;
    return;
  }
  list.innerHTML =
    `<p class="hit-lyrics-title">${t("phone.search.lyricVersions")}<span class="tiny">${t("phone.search.lyricHint")}</span></p>` +
    candidates.map((cand) => lyricRowHtml(hit, cand)).join("");
}

/** Fetch (or reuse) the lyric versions for ``hit`` and paint them. */
async function loadSheetLyrics(hit, q) {
  const list = $("hitLyrics");
  if (!list || !hit) return;
  const req = ++sheetLyricsReq;
  const key = String(hit.id);
  if (hit.source === "mugen") {
    paintSheetLyrics(hit, []);
    return;
  }
  if (hitLyricsCache.has(key)) {
    paintSheetLyrics(hit, hitLyricsCache.get(key));
    return;
  }
  list.innerHTML = `<p class="tiny hit-lyrics-note">${t("phone.search.lyricLoading")}</p>`;
  const loaded = await fetchJson(
    `/api/lyric_candidates?title=${encodeURIComponent(hit.title || "")}&artist=${encodeURIComponent(hit.artist || "")}&duration=${Number(hit.duration || 0)}&q=${encodeURIComponent(q || "")}`
  ).catch(() => null);
  if (req !== sheetLyricsReq || !sheetHit || String(sheetHit.id) !== key) return;
  if (!loaded || !loaded.ok) {
    paintSheetLyrics(hit, null);
    return;
  }
  const candidates = Array.isArray(loaded.data.candidates) ? loaded.data.candidates : [];
  hitLyricsCache.set(key, candidates);
  paintSheetLyrics(hit, candidates);
}

/** Paint the detail sheet for ``hit`` and reveal it. */
export function openHitSheet(hit) {
  if (!hit) return;
  // A different hit's video preview must not flash inside this sheet.
  if (sheetHit && String(sheetHit.id) !== String(hit.id)) stopPreview();
  sheetHit = hit;
  $("hitSheetHead").innerHTML =
    artHtml({
      key: `${hit.title}|${hit.artist || ""}`,
      title: hit.title,
      src: hit.pic || "",
      cls: "hit-sheet-art",
      badge: hitBadge(hit)
    }) +
    `<div class="hit-sheet-copy">` +
    `<h2 id="hitSheetTitle">${escapeHtml(hit.title)}</h2>` +
    `<p class="tiny">${escapeHtml(hit.artist || t("common.unknownArtist"))}</p>` +
    `</div>`;
  $("hitSheetMeta").innerHTML = hitMeta(hit);
  const play = $("hitSheetPlay");
  play.dataset.preview = String(hit.id || "");
  play.hidden = !hit.id;
  repaintPreviewChrome();
  repaintImportChrome(hit.id);
  $("hitSheet").hidden = false;
  loadSheetLyrics(hit, $("q").value.trim());
}

/** Re-paint the open sheet after a locale switch; no-op while it is closed. */
export function repaintHitSheet() {
  if (sheetHit && $("hitSheet") && !$("hitSheet").hidden) openHitSheet(sheetHit);
}

export function closeHitSheet() {
  if (!$("hitSheet") || $("hitSheet").hidden) return;
  stopPreview();
  sheetHit = null;
  closeOverlay("hitSheet");
}

export function searchCard(hit) {
  const id = escapeAttr(hit.id || "");
  return `<article class="hit-card" data-hit-id="${id}" role="button" tabindex="0" aria-label="${escapeAttr(`${hit.title} ${hit.artist || ""}`)}">
    <div class="hit-artbox">
      ${artHtml({ key: `${hit.title}|${hit.artist || ""}`, title: hit.title, src: hit.pic || "", cls: "hit-art", badge: hitBadge(hit) })}
      ${hit.id ? `<span class="hit-play" data-preview="${id}" aria-hidden="true">${ICO.play}</span>` : ""}
    </div>
    <div class="hit-foot">
      <div class="hit-copy">
        <b>${escapeHtml(hit.title)}</b>
        <span class="tiny">${escapeHtml(hit.artist || t("common.unknownArtist"))}</span>
        <span class="list-meta">${hitMeta(hit)}</span>
      </div>
      ${hit.id ? `<button type="button" class="hit-add" data-add="${id}" aria-label="${t("phone.search.add")}">${ICO.plus}</button>` : ""}
    </div>
  </article>`;
}

export function paintSearchHits(q, hasMore) {
  state.searchHasMore = !!hasMore;
  const cards =
    state.searchHits.map(searchCard).join("") ||
    `<div class="empty-state"><span class="empty-ico" aria-hidden="true"></span><p>${t("phone.search.none")}</p><span class="tiny">${t("phone.search.noneHint")}</span></div>`;
  const tail = hasMore
    ? `<button type="button" class="list-more list-sentinel" data-page="${state.searchPage + 1}">${t("common.loadMore")}</button>`
    : "";
  $("hits").innerHTML = cards + tail;
  repaintImportChrome();
  const more = $("hits").querySelector(".list-more");
  if (more) more.onclick = () => runSearch(Number(more.dataset.page) || state.searchPage + 1, true);
  if (state.previewId) {
    const live = $("hits").querySelector(`[data-preview="${state.previewId}"]`);
    if (live) {
      live.classList.add("on");
      live.innerHTML = ICO.pause;
      live.closest(".hit-card")?.classList.add("is-playing");
    }
  }
}

export async function runSearch(page, append = false) {
  const q = $("q").value.trim();
  if (!q) return;
  if (state.searchLoading) return;
  state.searchPage = Math.max(1, page);
  state.searchLoading = true;
  const moreBtn = $("hits").querySelector(".list-more");
  if (!append) {
    closeHitSheet();
    stopPreview();
    imported.clear();
    hitLyricsCache.clear();
    selectedLyric.clear();
    state.searchHits = [];
    state.searchHasMore = false;
    rememberSearch(q);
    $("hits").innerHTML = searchSkeleton();
  } else if (moreBtn) {
    moreBtn.textContent = t("common.loading");
    moreBtn.disabled = true;
  }
  /** @type {{ ok: boolean, data: SearchPage } | null} */
  const loaded = await fetchJson(`/api/search?q=${encodeURIComponent(q)}&page=${state.searchPage}&count=10`).catch(
    () => null
  );
  state.searchLoading = false;
  if (!loaded) {
    if (append && moreBtn) {
      moreBtn.textContent = t("common.loadMore");
      moreBtn.disabled = false;
      showToast(t("common.loadFailed"));
      return;
    }
    $("hits").innerHTML = `<div class="empty-state"><p>${t("common.loadFailed")}</p></div>`;
    return;
  }
  const { ok, data } = loaded;
  if (!ok) {
    if (append && moreBtn) {
      moreBtn.textContent = t("common.loadMore");
      moreBtn.disabled = false;
      showToast(data.detail || t("common.loadFailed"));
      return;
    }
    $("hits").innerHTML =
      `<div class="empty-state"><p>${escapeHtml(data.detail || t("api.search_failed", { exc: "" }))}</p></div>`;
    return;
  }
  const hits = data.hits || [];
  if (data.page && data.page !== state.searchPage) return;
  if (append) {
    const seen = new Set(state.searchHits.map((hit) => hit.id).filter(Boolean));
    const extra = hits.filter((hit) => hit.id && !seen.has(hit.id));
    state.searchHits = state.searchHits.concat(extra);
    paintSearchHits(q, !!data.has_more && extra.length > 0);
    return;
  }
  state.searchHits = hits;
  paintSearchHits(q, !!data.has_more && hits.length > 0);
}

export function syncSearchChrome() {
  const q = $("q");
  const has = !!q.value;
  const focus = document.activeElement === q;
  $("searchClear").hidden = !has;
  $("searchCancel").hidden = !(focus || has);
}

export function bindSearch() {
  $("q").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      $("q").blur();
      runSearch(1);
    }
  });
  $("hits").addEventListener("click", (event) => {
    const target = /** @type {HTMLElement} */ (event.target);
    const chip = target.closest("[data-recent]");
    if (chip instanceof HTMLElement) {
      $("q").value = chip.dataset.recent || "";
      syncSearchChrome();
      runSearch(1);
      return;
    }
    if (target.closest("[data-recent-clear]")) {
      clearRecentSearches();
      $("hits").innerHTML = searchEmpty();
      return;
    }
    const addBtn = target.closest(".hit-add");
    if (addBtn instanceof HTMLElement) {
      const card = addBtn.closest(".hit-card");
      runImport(card instanceof HTMLElement ? hitById(card.dataset.hitId) : null, $("q").value.trim());
      return;
    }
    const card = target.closest(".hit-card");
    if (card instanceof HTMLElement) {
      openHitSheet(hitById(card.dataset.hitId));
    }
  });
  $("hits").addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const card = /** @type {HTMLElement} */ (event.target).closest(".hit-card");
    if (!card) return;
    event.preventDefault();
    openHitSheet(hitById(card.dataset.hitId));
  });
  if (!$("q").value.trim() && !state.searchHits.length) $("hits").innerHTML = searchEmpty();
  $("q").addEventListener("input", syncSearchChrome);
  $("q").addEventListener("focus", syncSearchChrome);
  $("q").addEventListener("blur", () => setTimeout(syncSearchChrome, 80));
  onLangChange(() => repaintHitSheet());
  $("hitSheetBack").onclick = closeHitSheet;
  $("hitSheetClose").onclick = closeHitSheet;
  $("hitSheetPlay").onclick = () => {
    if (sheetHit) togglePreview(sheetHit, $("hitSheetPlay"));
  };
  $("hitSheetAdd").onclick = () => {
    if (sheetHit) runImport(sheetHit, $("q").value.trim());
  };
  $("hitLyrics").addEventListener("click", (event) => {
    const row = /** @type {HTMLElement} */ (event.target).closest("[data-lyric]");
    if (!(row instanceof HTMLElement) || !sheetHit) return;
    selectedLyric.set(String(sheetHit.id), row.dataset.lyric || "");
    $("hitLyrics")
      .querySelectorAll(".hit-lyric")
      .forEach((item) => item.classList.toggle("on", item === row));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("hitSheet") && !$("hitSheet").hidden) closeHitSheet();
  });
  $("searchClear").onclick = () => {
    $("q").value = "";
    $("q").focus();
    state.searchHits = [];
    $("hits").innerHTML = searchEmpty();
    syncSearchChrome();
  };
  $("searchCancel").onclick = () => {
    $("q").value = "";
    $("q").blur();
    state.searchHits = [];
    $("hits").innerHTML = searchEmpty();
    syncSearchChrome();
  };
  $("page-search").addEventListener("scroll", () => {
    const page = $("page-search");
    if (!page || page.hidden) return;
    if (page.scrollHeight - page.scrollTop - page.clientHeight > 160) return;
    if (!state.searchHasMore || state.searchLoading) return;
    runSearch(state.searchPage + 1, true);
  });
  $("openUpload").onclick = () => $("file").click();
  $("file").onchange = async () => {
    const file = $("file").files[0];
    if (!file) return;
    const btn = $("openUpload");
    btn.disabled = true;
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("title", file.name);
      fd.append("lyrics", "");
      const { ok, status, data } = await fetchJson("/api/songs", { method: "POST", body: fd });
      if (!ok) {
        if (status === 402 || status === 429) handlePointError(status, data.detail);
        throw new Error(data.detail || t("phone.search.uploadFailed"));
      }
      $("file").value = "";
      loadWho();
      api.showPage("desk");
    } catch (err) {
      showToast(err.message || t("phone.search.uploadFailed"));
    } finally {
      btn.disabled = false;
    }
  };
}
