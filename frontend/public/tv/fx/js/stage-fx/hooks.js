(function (global) {
  "use strict";

  function hookTexts(cues) {
    const counts = {};
    for (const cue of cues || []) {
      const text = String(cue.text || "").trim();
      if (!text) continue;
      counts[text] = (counts[text] || 0) + 1;
    }
    return new Set(Object.keys(counts).filter((text) => counts[text] >= 3));
  }

  global.LovStageFxTextHooks = { hookTexts };
})(window);
