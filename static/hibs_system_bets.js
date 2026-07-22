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
    var dayTag = leg.day_label || leg.card_date || "";
    var meta = leg.event || "—";
    if (!leg.event && (leg.course || leg.off_time)) {
      meta = [dayTag, [leg.course, leg.off_time].filter(Boolean).join(" ")].filter(Boolean).join(" · ") || "—";
    }
    return (
      '<div class="value-strip-card sys-bets-leg-card">' +
      (dayTag ? '<div class="sys-bets-leg-day">' + esc(dayTag) + "</div>" : "") +
      '<div class="vsc-meta">' + esc(meta) + "</div>" +
      '<div class="vsc-pick">' + esc(leg.selection || "—") + "</div>" +
      '<div class="vsc-odds sys-bets-market">' +
      esc((leg.market || "win").replace(/_/g, " ")) +
      (leg.odds_decimal ? " · " + formatOdds(leg.odds_decimal) : "") +
      (leg.ew_combined_ev != null ? ' · EV ' + esc(leg.ew_combined_ev) : "") +
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

  function updateIntro(source, pickSource) {
    var intro = document.getElementById("system-bets-intro");
    if (!intro) return;
    if (source === "tipster") {
      intro.innerHTML =
        'Parsed from today&apos;s tipster email. Paste or refresh on <a href="' +
        esc(intro.querySelector("a") ? intro.querySelector("a").getAttribute("href") || "/tips" : "/tips") +
        '">Tips</a> (include lines like <code>0.25pt Win Trixie</code>).';
    } else if (source === "engine" || pickSource === "value_lane") {
      intro.textContent =
        "Value-lane system bets — doubles, Trixies and Lucky 15 per racing day (today vs tomorrow). Each leg shows the day, course and off time.";
    }
  }

  function renderDaySection(day, insights, mount, comboOffset) {
    var html = "";
    var combos = day.combinations || [];
    var singles = day.singles || [];
    var title = day.day_label || day.card_date || "Racing day";
    var dateBits = [title];
    if (day.card_date && day.card_date !== title) dateBits.push(day.card_date);
    if (day.pick_count != null) dateBits.push(day.pick_count + " value pick" + (day.pick_count === 1 ? "" : "s"));
    html +=
      '<section class="sys-bets-day-section" data-card-date="' + esc(day.card_date || "") + '">' +
      '<h3 class="sys-bets-day-title">' + esc(dateBits.join(" · ")) + "</h3>";
    if (!combos.length && !singles.length) {
      html +=
        '<p class="sys-bets-empty">Need at least two value-lane runners on ' +
        esc(title) +
        " for doubles / Trixies.</p></section>";
      return { html: html, nextOffset: comboOffset };
    }
    combos.forEach(function (group, i) {
      html += renderCombination(group, comboOffset + i, insights);
    });
    html += renderSingles(singles, insights);
    html += "</section>";
    return { html: html, nextOffset: comboOffset + combos.length };
  }

  function renderPayload(data, mount) {
    var combos = data.combinations || [];
    var singles = data.singles || [];
    var days = data.days || [];
    var insights = data.win_engine && data.win_engine.insights ? data.win_engine.insights : null;
    var tipsUrl = (mount && mount.getAttribute("data-tips-url")) || "/tips";
    var source = data.source || (data.tip_count > 0 ? "tipster" : "engine");
    var pickSource = data.pick_source;

    updateIntro(source, pickSource);

    var hasDayContent = days.some(function (day) {
      return (day.combinations && day.combinations.length) || (day.singles && day.singles.length);
    });

    if (!combos.length && !singles.length && !hasDayContent) {
      if (data.message) {
        return '<p class="sys-bets-empty">' + esc(data.message) + "</p>";
      }
      if (source === "engine" || pickSource === "value_lane") {
        return (
          '<p class="sys-bets-empty">No value-lane system-bet legs yet — need at least two <strong>value_flag</strong> runners with positive EV per day. Check the Value lane panel above and run <strong>Refresh 24h</strong>.</p>'
        );
      }
      return (
        '<p class="sys-bets-empty">No Trixie / double / Lucky 15 combos for ' +
        esc(data.card_date || "today") +
        '. <a href="' + esc(tipsUrl) + '">Paste today&apos;s tip email</a> on the Tips page (include lines like <code>0.25pt Win Trixie</code>).</p>'
      );
    }

    var html = renderCalibrationBanner(calibrationFromPayload(data));
    if (days.length > 1) {
      html += '<p class="sys-bets-date">Combinations are split by racing day — legs never mix today with tomorrow.</p>';
    } else if (data.card_date) {
      var dayLine = data.day_label || data.card_date;
      if (data.day_label && data.card_date && data.day_label !== data.card_date) {
        dayLine = data.day_label + " · " + data.card_date;
      }
      html +=
        '<p class="sys-bets-date">' +
        esc(dayLine) +
        (source === "tipster" && data.tip_count != null ? " · " + data.tip_count + " tips ingested" : "") +
        (pickSource === "value_lane" || source === "engine" ? " · value-lane EV ranked" : "") +
        (insights ? " · win engine overlay" : "") +
        "</p>";
    }
    if (insights) {
      html += '<p class="sys-bets-dual-hint">Win % = model chance to win · Place % = chance of a place (usually top 3). VALUE = price looks better than our model.</p>';
    }

    mount._sysBetGroups = [];
    var comboOffset = 0;
    if (days.length) {
      days.forEach(function (day) {
        var rendered = renderDaySection(day, insights, mount, comboOffset);
        html += rendered.html;
        (day.combinations || []).forEach(function (group) {
          mount._sysBetGroups.push(group);
        });
        comboOffset = rendered.nextOffset;
      });
    } else {
      mount._sysBetGroups = combos.slice();
      combos.forEach(function (group, i) {
        html += renderCombination(group, i, insights);
      });
      html += renderSingles(singles, insights);
    }
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
