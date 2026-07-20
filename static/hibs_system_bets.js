/**
 * Racing tip combinations — Trixie, doubles, Lucky 15 + optional win-engine overlay.
 */
(function (global) {
  "use strict";

  var COMBO_LABELS = {
    trixie: "Trixie",
    patent: "Patent",
    treble: "Treble",
    double: "Double",
    ew_double: "Each-way double",
    lucky_15: "Lucky 15",
    lucky_31: "Lucky 31",
    lucky_63: "Lucky 63",
    accumulator: "Accumulator",
    acca: "Acca",
  };

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function formatOdds(odds) {
    return odds != null && !Number.isNaN(Number(odds)) ? Number(odds).toFixed(2) : "—";
  }

  function insightForLeg(leg, insights) {
    if (!insights || !leg || !leg.runner_id) return null;
    return insights[leg.runner_id] || null;
  }

  function comboTitle(group) {
    if (group.label) return group.label;
    var kind = String(group.type || "").toLowerCase();
    var label = COMBO_LABELS[kind] || kind.replace(/_/g, " ");
    var parts = [label];
    if (group.stake_units != null) parts.push(group.stake_units + "pt");
    if (group.bet_count) parts.push(group.bet_count + " bet" + (group.bet_count === 1 ? "" : "s"));
    return parts.join(" · ") || "Combination";
  }

  function comboSlipText(group) {
    var lines = [comboTitle(group)];
    (group.legs || []).forEach(function (leg) {
      var bits = [leg.selection || "?"];
      if (leg.event) bits.push(leg.event);
      if (leg.odds_decimal) bits.push("@" + formatOdds(leg.odds_decimal));
      if (leg.market) bits.push(String(leg.market).replace(/_/g, " "));
      lines.push(bits.join(" · "));
    });
    return lines.join("\n");
  }

  async function copyText(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
      if (btn) {
        var prev = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(function () {
          btn.textContent = prev;
        }, 1400);
      }
    } catch (e) {
      if (btn) btn.textContent = "Copy failed";
    }
  }

  function renderDualInsight(leg, insight) {
    if (!insight) return "";
    var winLabel = insight.win_value_label;
    if (!winLabel && insight.live_odds != null && insight.fair_odds != null) {
      winLabel = formatOdds(insight.live_odds) + " vs " + formatOdds(insight.fair_odds);
    }
    var placeLabel = insight.place_value_label;
    if (!placeLabel && insight.place_probability != null) {
      placeLabel = (Number(insight.place_probability) * 100).toFixed(1) + "%";
    }
    if (!winLabel && !placeLabel) return "";
    return (
      '<div class="sys-bets-dual-grid">' +
      '<div class="sys-bets-dual-col"><span class="sys-bets-dual-lbl">WIN VALUE</span>' +
      '<span class="sys-bets-dual-val">' + esc(winLabel || "—") + "</span></div>" +
      '<div class="sys-bets-dual-col"><span class="sys-bets-dual-lbl">PLACE VALUE</span>' +
      '<span class="sys-bets-dual-val sys-bets-place-val">' +
      esc(placeLabel ? "R8 " + placeLabel : "—") +
      "</span></div></div>"
    );
  }

  function renderLegCard(leg, insights) {
    var insight = insightForLeg(leg, insights);
    return (
      '<div class="value-strip-card sys-bets-leg-card">' +
      '<div class="vsc-meta">' + esc(leg.event || "—") + "</div>" +
      '<div class="vsc-pick">' + esc(leg.selection || "—") + "</div>" +
      '<div class="vsc-odds sys-bets-market">' +
      esc((leg.market || "win").replace(/_/g, " ")) +
      (leg.odds_decimal ? " · " + formatOdds(leg.odds_decimal) : "") +
      "</div>" +
      renderDualInsight(leg, insight) +
      "</div>"
    );
  }

  function renderLegCards(legs, insights) {
    if (!legs || !legs.length) {
      return '<p class="sys-bets-empty-legs">No legs parsed — check the email format above/below the header line.</p>';
    }
    return (
      '<div class="sys-bets-leg-grid">' +
      legs.map(function (leg) { return renderLegCard(leg, insights); }).join("") +
      "</div>"
    );
  }

  function renderCombination(group, index, insights) {
    return (
      '<article class="sys-bets-combo" data-system-bet-idx="' + index + '">' +
      '<div class="sys-bets-combo-hd">' +
      '<span class="sys-bets-combo-title">' + esc(comboTitle(group)) + "</span>" +
      '<button type="button" class="sys-bets-copy-btn" data-sys-bet-idx="' + index + '">Copy slip</button>' +
      "</div>" +
      renderLegCards(group.legs, insights) +
      "</article>"
    );
  }

  function renderSingles(singles, insights) {
    if (!singles || !singles.length) return "";
    return (
      '<div class="sys-bets-singles">' +
      '<div class="sys-bets-singles-title">Singles (not in a combo)</div>' +
      renderLegCards(singles, insights) +
      "</div>"
    );
  }

  function calibrationFromPayload(data) {
    var we = data && data.win_engine;
    if (!we) return null;
    var state = we.calibration_state;
    var brier = we.rolling_brier;
    var warn = !we.active || state !== "CALIBRATED";
    if (brier != null && brier > 0.185) warn = true;
    return {
      engineering_warning: warn,
      calibration_state: state,
      rolling_brier: brier,
      brier_pass_max: 0.185,
    };
  }

  function renderCalibrationBanner(cal) {
    if (!cal || !cal.engineering_warning) return "";
    return (
      '<div class="sys-bets-cal-warn" role="alert">' +
      "<strong>Win engine not fully calibrated</strong> — dual WIN/PLACE overlays are advisory only " +
      "(state " + esc(cal.calibration_state || "unknown") + ").</div>"
    );
  }

  function renderPayload(data, mount) {
    var combos = data.combinations || [];
    var singles = data.singles || [];
    var insights = data.win_engine && data.win_engine.insights ? data.win_engine.insights : null;
    var tipsUrl = (mount && mount.getAttribute("data-tips-url")) || "/tips";

    if (!combos.length && !singles.length) {
      return (
        '<p class="sys-bets-empty">No Trixie / double / Lucky 15 combos for ' +
        esc(data.card_date || "today") +
        '. <a href="' + esc(tipsUrl) + '">Paste today&apos;s tip email</a> on the Tips page (include lines like <code>0.25pt Win Trixie</code>).</p>'
      );
    }

    var html = renderCalibrationBanner(calibrationFromPayload(data));
    if (data.card_date) {
      html +=
        '<p class="sys-bets-date">' +
        esc(data.card_date) +
        (data.tip_count != null ? " · " + data.tip_count + " tips ingested" : "") +
        (insights ? " · win engine overlay" : "") +
        "</p>";
    }
    if (insights) {
      html += '<p class="sys-bets-dual-hint">Overlay: live vs fair win odds · R8 place % (advisory).</p>';
    }

    mount._sysBetGroups = combos;
    combos.forEach(function (group, i) {
      html += renderCombination(group, i, insights);
    });
    html += renderSingles(singles, insights);
    return html;
  }

  function renderSkeleton() {
    return (
      '<div class="sys-bets-skeleton-grid">' +
      '<div class="value-strip-card sys-bets-leg-card hibs-deferred-loading" style="min-height:72px;"></div>' +
      '<div class="value-strip-card sys-bets-leg-card hibs-deferred-loading" style="min-height:72px;"></div>' +
      "</div>"
    );
  }

  function bindCopyButtons(root, mount) {
    (root || document).querySelectorAll(".sys-bets-copy-btn").forEach(function (btn) {
      if (btn.dataset.hibsSysBetBound) return;
      btn.dataset.hibsSysBetBound = "1";
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        var idx = parseInt(btn.getAttribute("data-sys-bet-idx") || "0", 10);
        var group = (mount && mount._sysBetGroups && mount._sysBetGroups[idx]) || null;
        if (!group) return;
        copyText(comboSlipText(group), btn);
      });
    });
  }

  function normalizeRacingApiUrl(url) {
    if (!url) return "/api/racing/tips/combinations";
    if (/^https?:\/\//i.test(url)) return url;
    if (url.indexOf("/api/racing/") === 0) return url;
    if (url.indexOf("/racing/api/") === 0) return url.replace("/racing/api/", "/api/racing/");
    if (url.indexOf("/api/") === 0) return "/api/racing" + url.slice(4);
    return url;
  }

  function loadPanel(mount, opts) {
    if (!mount) return;
    if (!opts || !opts.force) {
      if (mount.dataset.hibsSysBetsLoaded === "1") return;
    }
    var url = normalizeRacingApiUrl(mount.getAttribute("data-fetch-url"));
    var sep = url.indexOf("?") >= 0 ? "&" : "?";
    if (url.indexOf("date=") < 0) {
      url += sep + "date=" + new Date().toISOString().slice(0, 10);
    }
    mount.dataset.hibsSysBetsLoaded = "1";
    mount.innerHTML = renderSkeleton();
    mount.setAttribute("aria-busy", "true");

    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        mount.innerHTML = renderPayload(data, mount);
        mount.setAttribute("aria-busy", "false");
        bindCopyButtons(mount, mount);
      })
      .catch(function () {
        mount.dataset.hibsSysBetsLoaded = "0";
        mount.innerHTML = '<p class="sys-bets-empty">Tip combinations unavailable — check racing service is up.</p>';
        mount.setAttribute("aria-busy", "false");
      });
  }

  function init() {
    var mount = document.getElementById("system-bets-mount");
    if (mount) loadPanel(mount);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  global.HibsSystemBets = {
    loadPanel: loadPanel,
    renderPayload: renderPayload,
    bindCopyButtons: bindCopyButtons,
  };
})(window);
