import { $, escapeHtml } from "../../../../shared/ui/js/dom.js";
import { fetchJson } from "../../../../shared/ui/js/http.js";
import { t } from "../../../../shared/i18n/js/i18n.js";
import { state } from "../../../state.js";
import { showToast } from "../../../ui/js/toast.js";

/** @type {LearnCampaign | null} */
let campaign = null;

export function currentCampaign() {
  return campaign;
}

export function setCampaign(data) {
  campaign = data || null;
  return campaign;
}

export async function loadCampaign(force) {
  const song = state.playerSong;
  if (!song) return null;
  if (!force && campaign && campaign.song_id === song.id) return campaign;
  const { ok, status, data } = await fetchJson(`/api/songs/${song.id}/learn/campaign`);
  if (!ok) {
    showToast((data && data.detail) || (status === 409 ? t("learn.cant") : t("learn.loadFail")));
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
  const bookMeta = $("learnBookMeta");
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
  const ready = firstReady(pack);
  if (path) {
    path.innerHTML = (pack.units || [])
      .map(
        (unit) => `
      <section class="learn-unit">
        <div class="learn-unit-h">
          <b>${escapeHtml(t("learn.unit", { n: unit.index + 1 }))}</b>
          <span>${escapeHtml(
            t("learn.unitLines", { from: unit.from_line + 1, to: unit.to_line + 1 })
          )}</span>
        </div>
        <div class="learn-nodes">
          ${(unit.skills || [])
            .map((skill) => {
              const current =
                ready && ready.unit.id === unit.id && ready.skill.id === skill.id;
              return `<button type="button" class="learn-node is-${skill.status}${
                current ? " is-current" : ""
              }" data-unit="${escapeHtml(unit.id)}" data-skill="${escapeHtml(
                skill.id
              )}" data-status="${escapeHtml(skill.status)}" data-start="${escapeHtml(
                t("learn.start")
              )}" ${skill.status === "locked" ? "disabled" : ""}>${escapeHtml(
                nodeLabel(skill.id)
              )}</button>`;
            })
            .join("")}
        </div>
      </section>
    `
      )
      .join("");
  }
  const miss = Number(pack.mistakes || 0);
  if (bookBtn) {
    bookBtn.hidden = miss <= 0;
    if (bookMeta) bookMeta.textContent = t("learn.bookHint", { n: miss });
  }
}

export function bindCampaign(handlers) {
  const path = $("learnPath");
  if (path) {
    path.addEventListener("click", (event) => {
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
