/**
 * Line Shop presentation — stateless matrix, localized DOM swaps, no page reloads.
 * Ingestion/display only — no order routing or capital execution.
 */
(function (root) {
  "use strict";

  var MARKETS = [
    ["Home", "home", "Home"],
    ["Draw", "draw", "Draw"],
    ["Away", "away", "Away"],
  ];

  function parseTsMs(raw) {
    if (raw == null || raw === "") return null;
    if (typeof raw === "number" && Number.isFinite(raw)) {
      return raw < 1e12 ? raw * 1000 : raw;
    }
    var n = Number(raw);
    if (Number.isFinite(n)) return n < 1e12 ? n * 1000 : n;
    var d = Date.parse(String(raw));
    return Number.isFinite(d) ? d : null;
  }

  function fmtOdds(v) {
    var n = Number(v);
    return Number.isFinite(n) && n > 1 ? n.toFixed(2) : "—";
  }

  function fmtBps(v) {
    var n = Number(v);
    if (!Number.isFinite(n)) return "—";
    return (n >= 0 ? "+" : "") + n.toFixed(0);
  }

  function probToDecimal(p) {
    var n = Number(p);
    if (!Number.isFinite(n) || n <= 0) return null;
    return 1 / n;
  }

  function bestBookOdds(shopped, marketLabel) {
    if (!shopped || !shopped[marketLabel]) return null;
    var row = shopped[marketLabel];
    var best = null;
    ["all", "sharp", "exchange", "soft"].forEach(function (ch) {
      var q = row[ch];
      if (!q) return;
      var o = q.odds != null ? Number(q.odds) : null;
      if (o != null && o > 1 && (best == null || o > best.odds)) {
        best = { odds: o, quote: q };
      }
    });
    return best;
  }

  function newestQuoteTs(shopped, marketLabel) {
    var row = shopped && shopped[marketLabel];
    if (!row) return null;
    var newest = null;
    Object.keys(row).forEach(function (ch) {
      var q = row[ch];
      if (!q || typeof q !== "object") return;
      var ts =
        parseTsMs(q.ts_ms) ||
        parseTsMs(q.updated_at_ms) ||
        parseTsMs(q.updated_at) ||
        parseTsMs(q.captured_at) ||
        parseTsMs(q.timestamp);
      if (ts != null && (newest == null || ts > newest)) newest = ts;
    });
    return newest;
  }

  function trueLineOdds(sharpFair, key) {
    if (!sharpFair || sharpFair[key] == null) return null;
    return probToDecimal(sharpFair[key]);
  }

  function edgeBps(bookOdds, trueOdds) {
    var b = Number(bookOdds);
    var t = Number(trueOdds);
    if (!Number.isFinite(b) || !Number.isFinite(t) || b <= 1 || t <= 1) return null;
    return ((b / t) - 1) * 10000;
  }

  function createLineShopController(opts) {
    var mount = opts.mount;
    var metaEl = opts.metaEl;
    var decaySecs = Number(opts.decayTimeoutSecs) || 120;
    var arbDeltaBps = Number(opts.arbDeltaBps) || 50;
    var state = {
      shopped: null,
      sharpFair: null,
      restBook: null,
      fveFrameTs: null,
      ready: false,
    };
    var rowEls = {};
    var decayTimer = null;

    function ensureMatrix() {
      if (state.ready) return;
      mount.setAttribute("aria-busy", "false");
      mount.innerHTML =
        '<table class="lt-matrix" role="grid" aria-label="Line shop matrix">' +
        "<thead><tr>" +
        "<th scope=\"col\">Sel</th>" +
        "<th scope=\"col\" class=\"lt-col-book\">Book decimal</th>" +
        "<th scope=\"col\" class=\"lt-col-true\">Zero-margin true line</th>" +
        "<th scope=\"col\" class=\"lt-col-gap\">Value gap</th>" +
        "</tr></thead><tbody></tbody></table>";
      var tbody = mount.querySelector("tbody");
      MARKETS.forEach(function (m) {
        var tr = document.createElement("tr");
        tr.dataset.market = m[1];
        tr.innerHTML =
          "<th scope=\"row\" class=\"lt-sel\">" +
          m[0] +
          "</th>" +
          "<td class=\"lt-cell-book num\" data-field=\"book\">—</td>" +
          "<td class=\"lt-cell-true num\" data-field=\"true\">—</td>" +
          "<td class=\"lt-cell-gap num\" data-field=\"gap\">—</td>";
        tbody.appendChild(tr);
        rowEls[m[1]] = {
          row: tr,
          book: tr.querySelector('[data-field="book"]'),
          true: tr.querySelector('[data-field="true"]'),
          gap: tr.querySelector('[data-field="gap"]'),
        };
      });
      state.ready = true;
    }

    function showSkeleton(message) {
      state.ready = false;
      rowEls = {};
      mount.setAttribute("aria-busy", "true");
      mount.innerHTML =
        '<div class="hibs-deferred-loading lt-matrix-skel-wrap">' +
        (message || "Loading line shop…") +
        '<div class="lt-matrix-skel" aria-hidden="true">' +
        "<div class=\"lt-skel-row\"></div><div class=\"lt-skel-row\"></div><div class=\"lt-skel-row\"></div>" +
        "</div></div>";
    }

    function setCell(el, text, classes) {
      if (!el) return;
      if (el.textContent !== text) el.textContent = text;
      var want = classes || [];
      var cls = ["num"].concat(want).join(" ");
      if (el.className !== cls) el.className = cls;
    }

    function applyRow(key, bookOdds, trueOdds, frameAgeMs) {
      var cells = rowEls[key];
      if (!cells) return;
      var stale = frameAgeMs != null && frameAgeMs > decaySecs * 1000;
      var bps = edgeBps(bookOdds, trueOdds);
      var valueHit = bps != null && bps >= arbDeltaBps;

      var rowCls = ["lt-matrix-row"];
      if (stale) rowCls.push("lt-row-stale");
      if (valueHit) rowCls.push("lt-row-value");
      cells.row.className = rowCls.join(" ");

      var bookCls = [];
      var trueCls = [];
      var gapCls = [];
      if (stale) {
        bookCls.push("lt-cell-stale");
        trueCls.push("lt-cell-stale");
      }
      if (valueHit) {
        bookCls.push("lt-cell-value");
        gapCls.push("lt-cell-value");
      }

      setCell(cells.book, fmtOdds(bookOdds), bookCls);
      setCell(cells.true, fmtOdds(trueOdds), trueCls);
      setCell(cells.gap, bps != null ? fmtBps(bps) + " bps" : "—", gapCls);
    }

    function refreshMatrix() {
      if (!state.ready) ensureMatrix();
      var now = Date.now();
      var frameTs =
        state.fveFrameTs ||
        (state.shopped ? Math.max.apply(null, MARKETS.map(function (m) {
          return newestQuoteTs(state.shopped, m[2]) || 0;
        }).concat([0])) : null);
      var frameAgeMs = frameTs ? now - frameTs : null;

      MARKETS.forEach(function (m) {
        var key = m[1];
        var label = m[2];
        var fromWs = bestBookOdds(state.shopped, label);
        var rest =
          state.restBook && state.restBook[key] != null ? Number(state.restBook[key]) : null;
        var bookOdds = fromWs ? fromWs.odds : rest;
        var trueOdds = trueLineOdds(state.sharpFair, key);
        applyRow(key, bookOdds, trueOdds, frameAgeMs);
      });

      if (metaEl) {
        var parts = [];
        if (frameTs) parts.push("frame " + new Date(frameTs).toISOString().slice(11, 19) + "Z");
        if (frameAgeMs != null) {
          parts.push("age " + Math.round(frameAgeMs / 1000) + "s");
          if (frameAgeMs > decaySecs * 1000) parts.push("STALE");
        }
        if (state.sharpFair) parts.push("FVE true line");
        metaEl.textContent = parts.join(" · ");
      }
    }

    function ingestLines(lines, meta) {
      if (!lines) return;
      if (lines.shopped) state.shopped = lines.shopped;
      if (lines.sharp_fair_probs) state.sharpFair = lines.sharp_fair_probs;
      var ts =
        parseTsMs(meta && meta.ts_ms) ||
        parseTsMs(meta && meta.updated_at) ||
        parseTsMs(lines.fve_updated_at) ||
        parseTsMs(lines.updated_at) ||
        parseTsMs(lines.frame_ts);
      if (ts) state.fveFrameTs = ts;
      ensureMatrix();
      refreshMatrix();
    }

    function ingestRestBook(best) {
      state.restBook = best && typeof best === "object" ? best : null;
      ensureMatrix();
      refreshMatrix();
    }

    function startDecayWatch() {
      if (decayTimer) return;
      decayTimer = setInterval(function () {
        if (state.ready) refreshMatrix();
      }, 5000);
    }

    function stopDecayWatch() {
      if (decayTimer) {
        clearInterval(decayTimer);
        decayTimer = null;
      }
    }

    showSkeleton();
    startDecayWatch();

    return {
      showSkeleton: showSkeleton,
      ingestLines: ingestLines,
      ingestRestBook: ingestRestBook,
      refreshMatrix: refreshMatrix,
      stopDecayWatch: stopDecayWatch,
    };
  }

  root.createLineShopController = createLineShopController;
  root.LineShopUtils = {
    parseTsMs: parseTsMs,
    edgeBps: edgeBps,
    trueLineOdds: trueLineOdds,
    bestBookOdds: bestBookOdds,
  };
})(typeof globalThis !== "undefined" ? globalThis : typeof window !== "undefined" ? window : this);
