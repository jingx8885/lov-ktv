import { $, escapeHtml } from "../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../shared/ui/js/http.js";
import { t } from "../../../shared/i18n/js/i18n.js";
import { api } from "../../api.js";
import { state, searchEmpty } from "../../state.js";
import { ICO } from "../../ui/js/icons.js";
import { showToast } from "../../ui/js/toast.js";
import { stopPreview, togglePreview } from "./preview.js";

export function bindSearchHits(q) {
  $("hits").querySelectorAll("[data-preview]").forEach((btn) => {
    btn.onclick = () => {
      const hit = JSON.parse(btn.parentElement.querySelector("[data-import]").dataset.import);
      togglePreview(hit, btn);
    };
  });
  $("hits").querySelectorAll("[data-import]").forEach((btn) => {
    btn.onclick = async () => {
      const hit = JSON.parse(btn.dataset.import);
      stopPreview();
      btn.disabled = true;
      btn.classList.add("busy");
      const body = {
        query: q,
        id: hit.id,
        title: hit.title,
        artist: hit.artist,
        language: hit.language || "",
        source: hit.source || "",
      };
      const { data: created } = await fetchJson("/api/songs/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!created.id) {
        btn.disabled = false;
        btn.classList.remove("busy");
        showToast(created.detail || t("phone.search.importFailed"));
        return;
      }
      btn.classList.add("on");
      btn.setAttribute("aria-label", t("phone.search.added"));
      showToast(t("phone.search.addedToast"));
      api.loadSongs();
    };
  });
  $("hits").querySelectorAll("[data-page]").forEach((btn) => {
    btn.onclick = () => runSearch(Number(btn.dataset.page), true);
  });
}

export function searchCard(hit) {
  const isMv = hit.is_mv === true || hit.source === "mugen" || hit.source === "bilibili";
  const channel = ({
    mugen: "Mugen",
    bilibili: t("phone.search.bilibili"),
    soundcloud: "SoundCloud",
  })[hit.source] || "";
  const bits = [
    escapeHtml(hit.artist || t("common.unknownArtist")),
    channel ? `<span class="source-tag ${escapeHtml(hit.source)}">${escapeHtml(channel)}</span>` : "",
    isMv ? "MV" : t("phone.search.song"),
  ].filter(Boolean);
  return `
        <article class="list-row">
          <div class="list-copy">
            <b>${escapeHtml(hit.title)}</b>
            <span class="tiny">${bits.join(" · ")}</span>
          </div>
          ${hit.id ? `<button type="button" class="row-action ghost list-preview" data-preview="${escapeHtml(hit.id)}" aria-label="${t("phone.search.preview")}">${ICO.play}</button>` : ""}
          <button type="button" class="row-action list-add" data-import='${JSON.stringify(hit)}' aria-label="${t("phone.search.add")}">${ICO.plus}</button>
        </article>`;
}

export function paintSearchHits(q, hasMore) {
  const cards = state.searchHits.map(searchCard).join("")
    || `<div class="empty-state"><span class="empty-ico" aria-hidden="true"></span><p>${t("phone.search.none")}</p><span class="tiny">${t("phone.search.noneHint")}</span></div>`;
  const more = hasMore ? `<button type="button" class="list-more" data-page="${state.searchPage + 1}">${t("common.loadMore")}</button>` : "";
  $("hits").innerHTML = cards + more;
  bindSearchHits(q);
  if (state.previewId) {
    const live = $("hits").querySelector(`[data-preview="${state.previewId}"]`);
    if (live) {
      live.classList.add("on");
      live.innerHTML = ICO.pause;
      live.setAttribute("aria-label", t("phone.search.stopPreview"));
    }
  }
}

export async function runSearch(page, append = false) {
  const q = $("q").value.trim();
  if (!q) return;
  state.searchPage = Math.max(1, page);
  const moreBtn = $("hits").querySelector(".list-more");
  if (!append) {
    stopPreview();
    state.searchHits = [];
    $("hits").innerHTML = `<div class="empty-state"><p>${t("common.searching")}</p></div>`;
  } else if (moreBtn) {
    moreBtn.disabled = true;
    moreBtn.textContent = t("common.loading");
  }
  /** @type {{ ok: boolean, data: SearchPage }} */
  const { ok, data } = await fetchJson(`/api/search?q=${encodeURIComponent(q)}&page=${state.searchPage}&count=10`);
  if (!ok) {
    if (append && moreBtn) {
      moreBtn.disabled = false;
      moreBtn.textContent = t("common.loadMore");
      showToast(data.detail || t("common.loadFailed"));
      return;
    }
    $("hits").innerHTML = `<div class="empty-state"><p>${escapeHtml(data.detail || t("api.search_failed", { exc: "" }))}</p></div>`;
    return;
  }
  const hits = data.hits || [];
  if (append) {
    const seen = new Set(state.searchHits.map((hit) => hit.id));
    state.searchHits = state.searchHits.concat(hits.filter((hit) => hit.id && !seen.has(hit.id)));
  } else {
    state.searchHits = hits;
  }
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
  $("q").addEventListener("input", syncSearchChrome);
  $("q").addEventListener("focus", syncSearchChrome);
  $("q").addEventListener("blur", () => setTimeout(syncSearchChrome, 80));
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
      const { ok, data } = await fetchJson("/api/songs", { method: "POST", body: fd });
      if (!ok) throw new Error(data.detail || t("phone.search.uploadFailed"));
      $("file").value = "";
      api.showPage("desk");
    } catch (err) {
      showToast(err.message || t("phone.search.uploadFailed"));
    } finally {
      btn.disabled = false;
    }
  };
}

