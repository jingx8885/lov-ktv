import { $, escapeHtml } from "../../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { state } from "../../../state.js";
import { showToast } from "../../../ui/js/toast.js";
import { getStudyWords } from "../../../desk/js/lyrics.js";

/** @type {LearnCampaign | null} */
let campaign = null;

export function currentCampaign() {
  return campaign;
}

export function setCampaign(data) {
  campaign = data || null;
  return campaign;
}

export async function loadCampaign(force, silent = false) {
  const song = state.playerSong;
  if (!song) return null;
  if (!force && campaign && campaign.song_id === song.id) return campaign;
  const { ok, status, data } = await fetchJson(`/api/songs/${song.id}/learn/campaign`);
  if (!ok) {
    if (!silent) showToast((data && data.detail) || (status === 409 ? t("learn.cant") : t("learn.loadFail")));
    return null;
  }
  campaign = data;
  return data;
}

function goalView(key, slice) {
  const total = (slice && slice.total) || 0;
  const done = Math.min((slice && slice.done) || 0, total);
  const pct = total ? Math.round((done / total) * 100) : 0;
  return `
    <div class="learn-goal${done >= total && total ? " is-done" : ""}">
      <div class="learn-ring" style="--pct:${pct}"><span>${done}/${total || 0}</span></div>
      <b>${escapeHtml(t("learn.goal." + key))}</b>
    </div>
  `;
}

function nodeLabel(skill) {
  return t("learn.skill." + skill);
}

/**
 * A circle holding four Han characters is unreadable at 68px, so the node shows
 * the skill as a glyph and keeps the wording as a caption underneath.
 */
const SKILL_ICO = {
  word: "M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm6 4-3.6 10h2.1l.7-2.1h3.6l.7 2.1h2.1L13 7h-2Zm1 2.6 1.2 3.5h-2.4L12 9.6Z",
  sentence: "M4 5h16v2.4H4V5Zm0 5.8h16v2.4H4v-2.4ZM4 16.6h10V19H4v-2.4Z",
  listen:
    "M12 3a8 8 0 0 0-8 8v6a3 3 0 0 0 3 3h1a1 1 0 0 0 1-1v-6a1 1 0 0 0-1-1H6.4A5.6 5.6 0 0 1 12 5.4 5.6 5.6 0 0 1 17.6 12H16a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h1a3 3 0 0 0 3-3v-6a8 8 0 0 0-8-8Z",
  read: "M12 6.2C10.3 4.9 8.1 4.3 5.6 4.3c-.9 0-1.8.1-2.6.3v13.6c.8-.2 1.7-.3 2.6-.3 2.5 0 4.7.6 6.4 1.9 1.7-1.3 3.9-1.9 6.4-1.9.9 0 1.8.1 2.6.3V4.6c-.8-.2-1.7-.3-2.6-.3-2.5 0-4.7.6-6.4 1.9Z",
  sing: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3ZM5 11.5a1 1 0 0 1 2 0 5 5 0 0 0 10 0 1 1 0 0 1 2 0 7 7 0 0 1-6 6.9V21h2.5a1 1 0 0 1 0 2h-7a1 1 0 0 1 0-2H11v-2.6a7 7 0 0 1-6-6.9Z"
};

function nodeIcon(skill) {
  const path = SKILL_ICO[skill] || SKILL_ICO.word;
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
}

/**
 * A song can chunk into a dozen units × 5 skills. Painting all 60 nodes buries
 * the one unlocked node under nine screens of grey, so only the unit being
 * worked on is drawn in full; cleared units fold to a single row and the locked
 * tail collapses to a count. Both fold-outs stay reachable by tap.
 * @type {Set<string>}
 */
const expanded = new Set();
let expandedSong = "";

function unitState(unit) {
  const skills = unit.skills || [];
  if (skills.some((skill) => skill.status === "ready")) return "current";
  if (skills.length && skills.every((skill) => skill.status === "passed" || skill.status === "mastered")) {
    return "done";
  }
  return "locked";
}

function nodesView(unit, ready) {
  return (unit.skills || [])
    .map((skill) => {
      const current = ready && ready.unit.id === unit.id && ready.skill.id === skill.id;
      const label = escapeHtml(nodeLabel(skill.id));
      // aria-disabled rather than disabled: a real disabled button swallows the
      // click, so the "clear the earlier stages first" hint could never fire.
      // The step carries is-current too: the "start" pill floats above its node
      // and needs headroom reserved that node spacing alone doesn't give.
      return `<div class="learn-step${current ? " is-current" : ""}"><button type="button" class="learn-node is-${skill.status}${
        current ? " is-current" : ""
      }" data-unit="${escapeHtml(unit.id)}" data-skill="${escapeHtml(skill.id)}" data-status="${escapeHtml(
        skill.status
      )}" data-start="${escapeHtml(t("learn.start"))}" aria-label="${label}" ${
        skill.status === "locked" ? 'aria-disabled="true"' : ""
      }>${nodeIcon(skill.id)}</button><em class="learn-node-tag">${label}</em></div>`;
    })
    .join("");
}

function unitView(unit, ready, foldable) {
  // The current unit stays pinned open; anything the user opened by hand can be
  // folded back from its own header.
  const cls = `learn-unit-h${foldable ? " is-foldable" : " is-current"}`;
  const head = foldable
    ? `<button type="button" class="${cls}" data-unit-collapse="${escapeHtml(unit.id)}">`
    : `<div class="${cls}">`;
  return `
      <section class="learn-unit is-open">
        ${head}
          <span class="learn-unit-txt">
            <b>${escapeHtml(t("learn.unit", { n: unit.index + 1 }))}</b>
            <em>${escapeHtml(t("learn.unitLines", { from: unit.from_line + 1, to: unit.to_line + 1 }))}</em>
          </span>
          ${foldable ? '<i class="learn-unit-fold" aria-hidden="true">︿</i>' : ""}
        ${foldable ? "</button>" : "</div>"}
        <div class="learn-nodes">${nodesView(unit, ready)}</div>
      </section>
    `;
}

function doneRow(unit) {
  const ticks = (unit.skills || []).map(() => "✓").join("");
  return `<button type="button" class="learn-unit-row is-done" data-unit-expand="${escapeHtml(unit.id)}">
      <b>${escapeHtml(t("learn.unit", { n: unit.index + 1 }))}</b>
      <em>${escapeHtml(t("learn.unitCleared"))}</em>
      <i>${ticks}</i>
    </button>`;
}

function moreRow(n) {
  return `<button type="button" class="learn-unit-row is-more" data-unit-more>
      <b>${escapeHtml(t("learn.moreUnits", { n }))}</b>
      <strong aria-hidden="true">›</strong>
    </button>`;
}

function pathView(pack) {
  const units = pack.units || [];
  // Hand-opened units belong to the song they were opened on.
  if (pack.song_id !== expandedSong) {
    expandedSong = pack.song_id || "";
    expanded.clear();
  }
  const ready = firstReady(pack);
  // With everything passed there is no ready node; keep the last unit open so
  // the path never renders as a wall of collapsed rows.
  const currentId = ready ? ready.unit.id : (units[units.length - 1] || {}).id;
  const parts = [];
  let collapsed = 0;
  units.forEach((unit) => {
    if (unit.id === currentId) {
      parts.push(unitView(unit, ready, false));
    } else if (expanded.has(unit.id)) {
      parts.push(unitView(unit, ready, true));
    } else if (unitState(unit) === "done") {
      parts.push(doneRow(unit));
    } else {
      collapsed += 1;
    }
  });
  // Locked units always trail the current one, so the count row belongs last.
  if (collapsed) parts.push(moreRow(collapsed));
  return parts.join("");
}

function repaintPath() {
  const path = $("learnPath");
  if (path && campaign) path.innerHTML = pathView(campaign);
}

export function firstReady(data) {
  const pack = data || campaign;
  if (!pack) return null;
  for (const unit of pack.units || []) {
    for (const skill of unit.skills || []) {
      if (skill.status === "ready") return { unit, skill };
    }
  }
  return null;
}

/** @param {LearnCampaign | null | undefined} data */
export function paintCampaign(data) {
  campaign = data || campaign;
  const pack = campaign;
  const goals = $("learnGoals");
  const path = $("learnPath");
  const bookBtn = $("learnBookBtn");
  if (!pack) {
    if (goals) goals.hidden = true;
    if (path) path.innerHTML = "";
    if (bookBtn) bookBtn.hidden = true;
    return;
  }
  /** @type {LearnCampaignGoal} */
  const goal = pack.goal || {
    words: { done: 0, total: 0 },
    sentences: { done: 0, total: 0 },
    read: { done: 0, total: 0 },
    sing: { done: 0, total: 0 },
    cleared: false
  };
  if (goals) {
    goals.hidden = false;
    goals.innerHTML =
      (goal.cleared ? `<p class="learn-cleared">${escapeHtml(t("learn.cleared"))}</p>` : "") +
      `<div class="learn-goals-row">` +
      goalView("words", goal.words) +
      goalView("sentences", goal.sentences) +
      goalView("read", goal.read) +
      goalView("sing", goal.sing) +
      `</div>`;
  }
  if (path) path.innerHTML = pathView(pack);
  paintBookMeta(Number(pack.mistakes || 0));
}

/** 收藏词已经搬到服务端牌组了，本地那份只当离线兜底。先用手上的数画一遍，
    再异步拿服务端总数补一次，免得进关卡要等一个请求。 */
let deckWords = -1;

function paintBookMeta(miss, refresh = true) {
  const bookBtn = $("learnBookBtn");
  if (!bookBtn) return;
  const bookMeta = $("learnBookMeta");
  const words = deckWords >= 0 ? deckWords : getStudyWords().length;
  bookBtn.hidden = miss <= 0 && words <= 0;
  if (bookMeta) bookMeta.textContent = t("learn.bookSummary", { words, mistakes: miss });
  if (!refresh) return;
  fetchJson("/api/learn/deck?deck=word&cards=0")
    .then(({ ok, data }) => {
      if (!ok || !data) return;
      const total = Number(data.total || 0);
      if (total === deckWords) return;
      deckWords = total;
      paintBookMeta(miss, false);
    })
    .catch(() => {});
}

export function bindCampaign(handlers) {
  const path = $("learnPath");
  if (path) {
    path.addEventListener("click", (event) => {
      const fold = event.target.closest("[data-unit-expand], [data-unit-collapse], [data-unit-more]");
      if (fold) {
        if (fold.dataset.unitExpand) expanded.add(fold.dataset.unitExpand);
        else if (fold.dataset.unitCollapse) expanded.delete(fold.dataset.unitCollapse);
        else if (campaign) {
          // "N more stages" opens the locked tail in one go.
          (campaign.units || []).forEach((unit) => {
            if (unitState(unit) !== "done") expanded.add(unit.id);
          });
        }
        repaintPath();
        return;
      }
      const btn = event.target.closest("[data-skill]");
      if (!btn || btn.dataset.status === "locked") {
        if (btn && btn.dataset.status === "locked") showToast(t("learn.locked"));
        return;
      }
      handlers.onSkill(btn.dataset.unit, btn.dataset.skill);
    });
  }
  const bookBtn = $("learnBookBtn");
  if (bookBtn) bookBtn.onclick = () => handlers.onBook();
}
