/* Legacy WebView compatibility shim (Android 10 system WebView ≈ Chrome 74).
 *
 * Modern CSS the UI relies on: flex/grid `gap`, `inset`, `dvh`, `place-items`,
 * `clamp()/min()`, `:where()`, `:has()` … Older engines ignore the whole rule
 * or declaration, which leaves overlays unpositioned and rows cramped.
 *
 * Stylesheets already carry static fallbacks (top/right/bottom/left before
 * `inset`, `vh` before `dvh`, …). This shim handles what cannot be expressed
 * statically: flex `gap` is emulated with child margins injected into a
 * <style> override element, so dynamic styles and later rules keep working.
 */
(function () {
  'use strict';

  var supportsFlexGap = (function () {
    if (typeof CSS === 'undefined' || !CSS.supports) return false;
    try {
      var el = document.createElement('div');
      el.style.display = 'flex';
      el.style.flexDirection = 'column';
      el.style.rowGap = '1px';
      el.style.position = 'absolute';
      el.style.visibility = 'hidden';
      var a = document.createElement('div');
      var b = document.createElement('div');
      el.appendChild(a);
      el.appendChild(b);
      (document.body || document.documentElement).appendChild(el);
      var ok = el.scrollHeight === 1;
      el.parentNode.removeChild(el);
      return ok;
    } catch (e) {
      return false;
    }
  })();

  function visitRules(rules, mediaText, fn) {
    if (!rules) return;
    for (var i = 0; i < rules.length; i++) {
      var rule = rules[i];
      if (rule.type === CSSRule.STYLE_RULE) {
        fn(rule, mediaText);
      } else if (rule.type === CSSRule.MEDIA_RULE) {
        visitRules(rule.cssRules, rule.conditionText || rule.media.mediaText, fn);
      }
    }
  }

  var supportsHas = (function () {
    try { return typeof CSS !== 'undefined' && CSS.supports && CSS.supports('selector(:has(*))'); }
    catch (e) { return false; }
  })();
  var supportsWhere = (function () {
    try { return typeof CSS !== 'undefined' && CSS.supports && CSS.supports('selector(:where(*))'); }
    catch (e) { return false; }
  })();

  // Evaluate a selector containing :has() / :where() against the DOM and
  // return matching elements, so their declarations can be applied via
  // inline styles on old engines that drop the whole rule.
  function matchesLegacy(rootEl, selector) {
    var out = [];
    try {
      var parts = selector.split(',');
      var set = {};
      for (var pi = 0; pi < parts.length; pi++) {
        var sel = parts[pi].trim();
        // Replace :where(a,b) inner list by evaluating each alternative;
        // simplest robust path: strip :where(...) to a plain descendant check.
        var cleaned = sel
          .replace(/:where\(([^()]*)\)/g, function (_, inner) {
            return inner.split(',')[0].trim() || '*';
          })
          .replace(/:has\(([^()]*)\)/g, '');
        var base = cleaned || '*';
        var els = (rootEl || document).querySelectorAll(base);
        var hasRe = /:has\(>?\s*([^()]*)\)/;
        for (var ei = 0; ei < els.length; ei++) {
          var el = els[ei];
          var ok = true;
          var hm = sel.match(hasRe);
          if (hm) {
            var sub = hm[1].trim();
            var direct = /:has\(>/.test(sel);
            try {
              ok = direct ? el.querySelector(':scope > ' + sub) !== null
                          : el.querySelector(sub) !== null;
            } catch (e) { ok = false; }
            // handle :has(.a + .b)-style siblings only roughly: skip
          }
          if (ok && !set[ei + ':' + pi]) { set[ei + ':' + pi] = 1; out.push(el); }
        }
      }
    } catch (e) {}
    return out;
  }

  function applyHasRules() {
    if (supportsHas) return;
    var sheets = document.styleSheets;
    var jobs = [];
    for (var i = 0; i < sheets.length; i++) {
      try {
        visitRules(sheets[i].cssRules, null, function (rule, media) {
          if (rule.selectorText && (rule.selectorText.indexOf(':has(') >= 0 ||
              (!supportsWhere && rule.selectorText.indexOf(':where(') >= 0))) {
            jobs.push(rule);
          }
        });
      } catch (e) {}
    }
    jobs.forEach(function (rule) {
      var els = matchesLegacy(document, rule.selectorText);
      for (var j = 0; j < els.length; j++) {
        var st = rule.style;
        for (var k = 0; k < st.length; k++) {
          var prop = st[k];
          try {
            els[j].style.setProperty(prop, st.getPropertyValue(prop),
              st.getPropertyPriority(prop));
          } catch (e) {}
        }
      }
    });
  }

  if (!supportsFlexGap) {
    var overrides = [];

    function push(sel, prop, val, media) {
      var decl = prop + ':' + val + ' !important';
      var rule = sel + '{' + decl + '}';
      overrides.push(media ? '@media ' + media + '{' + rule + '}' : rule);
    }

    function emit(rule, media) {
      var st = rule.style;
      var row = st.getPropertyValue('row-gap');
      var col = st.getPropertyValue('column-gap');
      var gap = st.getPropertyValue('gap');
      if (gap && !row && !col) {
        var parts = gap.trim().split(/\s+/);
        row = parts[0];
        col = parts.length > 1 ? parts[1] : parts[0];
      }
      var isFlex = /(^|\s)flex/.test(st.display || '');
      if (!isFlex || (!row && !col)) return;
      var sel = rule.selectorText;
      // Emulate with margins on children. margin-* longhands; last child reset.
      if (col && col !== '0' && col !== '0px' && col !== 'normal') {
        push(sel + ' > *', 'margin-right', col, media);
        push(sel + ' > *:last-child', 'margin-right', '0', media);
      }
      if (row && row !== '0' && row !== '0px' && row !== 'normal') {
        push(sel + ' > *', 'margin-bottom', row, media);
        push(sel + ' > *:last-child', 'margin-bottom', '0', media);
      }
    }

    function scan() {
      var sheets = document.styleSheets;
      for (var i = 0; i < sheets.length; i++) {
        var sheet = sheets[i];
        try {
          visitRules(sheet.cssRules, null, emit);
        } catch (e) {
          /* cross-origin sheet: skip */
        }
      }
      if (overrides.length) {
        var style = document.createElement('style');
        style.id = 'lovktv-legacy-gap';
        style.textContent = overrides.join('\n');
        document.head.appendChild(style);
      }
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', scan);
    } else {
      scan();
    }
  }

  if (!supportsHas || !supportsWhere) {
    var run = function () {
      applyHasRules();
      // Dynamic lyrics rows appear later; re-run a few times on a timer.
      setTimeout(applyHasRules, 800);
      setTimeout(applyHasRules, 2500);
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', run);
    } else {
      run();
    }
  }
})();
