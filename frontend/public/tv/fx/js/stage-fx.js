(function (global) {
  "use strict";

  const { EFFECTS } = global.LovStageFxPrimitives;
  const { create, reduceMotion } = global.LovStageFxRuntime;

  let party = null;

  function bindParty(canvas) {
    if (!global.confetti || !canvas) return null;
    party = global.confetti.create(canvas, {
      resize: true,
      useWorker: false,
      disableForReducedMotion: true,
    });
    return party;
  }

  function celebrate(kind) {
    if (reduceMotion()) return;
    const fire = party || global.confetti;
    if (!fire) return;
    const colors = ["#f5c16c", "#ff4d8d", "#ffffff", "#6ec8ff"];
    if (kind === "side") {
      fire({ particleCount: 55, angle: 60, spread: 62, origin: { x: 0, y: 0.7 }, colors });
      fire({ particleCount: 55, angle: 120, spread: 62, origin: { x: 1, y: 0.7 }, colors });
      return;
    }
    fire({ particleCount: 90, spread: 78, startVelocity: 42, origin: { y: 0.62 }, colors });
  }

  function hookTexts(cues) {
    const counts = {};
    for (const cue of cues || []) {
      const text = String(cue.text || "").trim();
      if (!text) continue;
      counts[text] = (counts[text] || 0) + 1;
    }
    return new Set(Object.keys(counts).filter((text) => counts[text] >= 3));
  }

  global.LovStageFx = { EFFECTS, create, bindParty, celebrate, hookTexts, reduceMotion };
})(window);
