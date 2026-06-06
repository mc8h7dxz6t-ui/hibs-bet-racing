/** hibs-racing racecard UI — meeting/race navigation, deep-links, persisted state */

(function brandingModule(global) {
  const STORAGE_KEY = 'hibs_racing_brand_v1';
  const DEFAULTS = {
    productName: '',
    tagline: '',
    primaryColor: '',
    neonColor: '',
    wordmarkFont: '',
    logoDataUrl: '',
  };

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return { ...DEFAULTS };
      return { ...DEFAULTS, ...JSON.parse(raw) };
    } catch (_) {
      return { ...DEFAULTS };
    }
  }

  function save(payload) {
    const next = { ...load(), ...payload };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch (_) {}
    return next;
  }

  function reset() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (_) {}
  }

  function apply(payload) {
    const b = payload || load();
    const root = document.documentElement;
    if (b.primaryColor) {
      root.style.setProperty('--primary-brand-color', b.primaryColor);
      root.style.setProperty('--hibs-green', b.primaryColor);
    }
    if (b.neonColor) {
      root.style.setProperty('--hibs-neon', b.neonColor);
      root.style.setProperty('--accent', b.neonColor);
    }
    if (b.wordmarkFont) {
      const stack = b.wordmarkFont === 'Inter' ? "'Inter',sans-serif" : `'${b.wordmarkFont}',sans-serif`;
      root.style.setProperty('--wordmark-font', stack);
    }
    const wordmark = document.getElementById('site-wordmark');
    if (wordmark && b.productName) wordmark.textContent = b.productName;
    const tagline = document.getElementById('site-tagline');
    if (tagline && b.tagline) tagline.textContent = b.tagline;
    const crest = document.getElementById('site-crest-primary');
    if (crest && b.logoDataUrl) {
      crest.src = b.logoDataUrl;
      crest.alt = b.productName || crest.alt;
    }
    if (b.productName) document.title = document.title.replace(/^[^—]+/, b.productName + ' ');
  }

  global.HibsBranding = { load, save, reset, apply, STORAGE_KEY };
})(window);

(function () {
  const STORAGE_MEETING = 'hibs_racing_meeting';
  const STORAGE_RACE = 'hibs_racing_race';
  const STORAGE_HERO = 'hibs_racing_hero_open';

  function activePanel() {
    return document.querySelector('.meeting-panel.is-active');
  }

  function shellEl() {
    return document.getElementById('racecard-nav-state') || document.getElementById('racecard-shell');
  }

  function readDeepLink() {
    const shell = shellEl();
    const params = new URLSearchParams(window.location.search);
    let meeting = params.get('meeting') || shell?.dataset.initialMeeting || '';
    let race = params.get('race') || shell?.dataset.initialRace || '';
    const raceId = params.get('race_id') || '';
    const runnerId = params.get('runner_id') || params.get('runner') || shell?.dataset.highlightRunner || '';

    if (raceId && !race) {
      const drawer = document.querySelector(`.race-drawer[data-race-id="${CSS.escape(raceId)}"]`);
      if (drawer) {
        race = drawer.id;
        meeting = drawer.closest('.meeting-panel')?.dataset.meeting || meeting;
      }
    }

    return { meeting, race, raceId, runnerId };
  }

  function highlightRunner(runnerId) {
    if (!runnerId) return;
    document.querySelectorAll('tr[data-runner-id]').forEach((row) => {
      row.classList.toggle('runner-highlight', row.dataset.runnerId === runnerId);
    });
    const row = document.querySelector(`tr[data-runner-id="${CSS.escape(runnerId)}"]`);
    if (row) {
      row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  function rebuildRaceSelect(panel) {
    const raceSel = document.getElementById('race-select');
    if (!raceSel || !panel) return;
    raceSel.innerHTML = '';
    panel.querySelectorAll('.race-drawer').forEach((el) => {
      const opt = document.createElement('option');
      opt.value = el.id;
      const off = el.dataset.off || '?';
      const name = el.querySelector('.race-name')?.textContent?.trim() || 'Race';
      const verdict = el.dataset.rpVerdict || '';
      opt.textContent = verdict
        ? `${off} · ${name.slice(0, 40)} · ${verdict.slice(0, 72)}`
        : `${off} · ${name.slice(0, 52)}`;
      if (verdict) opt.title = verdict;
      opt.dataset.rpVerdict = verdict;
      raceSel.appendChild(opt);
    });
  }

  function updateRaceHint(drawer) {
    const hint = document.getElementById('race-verdict-hint');
    if (!hint || !drawer) return;
    const verdict = drawer.dataset.rpVerdict || '';
    if (verdict) {
      hint.textContent = verdict;
      hint.hidden = false;
    } else {
      hint.textContent = 'No RP verdict yet — refresh card with Racing Post credentials in .env';
      hint.hidden = false;
    }
  }

  function openRace(raceId, panel, options) {
    options = options || {};
    panel = panel || activePanel();
    if (!panel || !raceId) return;
    panel.querySelectorAll('.race-drawer').forEach((d) => {
      d.open = d.id === raceId;
    });
    const drawer = document.getElementById(raceId);
    if (drawer) {
      if (options.scroll !== false) {
        drawer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
      if (!options.skipStorage) {
        try {
          localStorage.setItem(STORAGE_RACE, raceId);
        } catch (_) {}
      }
    }
    panel.querySelectorAll('.race-tab').forEach((t) => {
      t.classList.toggle('is-active', t.dataset.target === raceId);
      t.setAttribute('aria-selected', t.dataset.target === raceId ? 'true' : 'false');
    });
    const raceSel = document.getElementById('race-select');
    if (raceSel && raceSel.value !== raceId) raceSel.value = raceId;
    updateRaceHint(drawer);
  }

  function switchMeeting(slug, options) {
    options = options || {};
    if (!slug) return;
    document.querySelectorAll('.meeting-panel').forEach((p) => {
      const on = p.dataset.meeting === slug;
      p.classList.toggle('is-active', on);
      p.hidden = !on;
    });
    const meetingSel = document.getElementById('meeting-select');
    if (meetingSel && meetingSel.value !== slug) meetingSel.value = slug;
    const panel = activePanel();
    rebuildRaceSelect(panel);
    if (!options.skipStorage) {
      try {
        localStorage.setItem(STORAGE_MEETING, slug);
      } catch (_) {}
    }

    let raceId = options.race || null;
    if (!raceId) {
      try {
        raceId = localStorage.getItem(STORAGE_RACE);
      } catch (_) {}
    }
    const saved = raceId && panel?.querySelector(`#${CSS.escape(raceId)}`);
    const target = saved ? raceId : panel?.querySelector('.race-drawer')?.id;
    if (target) openRace(target, panel, { skipStorage: !!options.race, scroll: options.scroll !== false });

    const opt = meetingSel?.options[meetingSel.selectedIndex];
    const hint = document.getElementById('meeting-hint');
    if (hint && opt?.dataset.hint) hint.textContent = opt.dataset.hint;
  }

  function applyDeepLink() {
    const link = readDeepLink();
    if (link.meeting) {
      switchMeeting(link.meeting, { race: link.race || undefined, skipStorage: true });
    } else if (link.race) {
      const drawer = document.getElementById(link.race);
      const meeting = drawer?.closest('.meeting-panel')?.dataset.meeting;
      if (meeting) switchMeeting(meeting, { race: link.race, skipStorage: true });
    }
    if (link.runnerId) {
      highlightRunner(link.runnerId);
    }
    if (link.meeting || link.race || link.raceId) {
      const target = document.getElementById('racecard-shell') || shellEl();
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  function bindRacecard() {
    const meetingSel = document.getElementById('meeting-select');
    const panels = document.querySelectorAll('.meeting-panel');
    if (!meetingSel || !panels.length) return;

    panels.forEach((p) => {
      p.hidden = !p.classList.contains('is-active');
      p.querySelectorAll('.race-drawer').forEach((drawer) => {
        drawer.addEventListener('toggle', () => {
          if (!drawer.open) return;
          p.querySelectorAll('.race-drawer').forEach((d) => {
            if (d !== drawer) d.open = false;
          });
          openRace(drawer.id, p);
        });
      });
    });

    meetingSel.addEventListener('change', () => {
      const opt = meetingSel.options[meetingSel.selectedIndex];
      const hint = document.getElementById('meeting-hint');
      if (hint && opt?.dataset.hint) hint.textContent = opt.dataset.hint;
      switchMeeting(meetingSel.value);
    });
    document.getElementById('race-select')?.addEventListener('change', (e) => openRace(e.target.value));

    document.querySelectorAll('.race-nav-strip').forEach((strip) => {
      strip.addEventListener('click', (e) => {
        const btn = e.target.closest('.race-tab');
        if (!btn) return;
        openRace(btn.dataset.target, btn.closest('.meeting-panel'));
      });
    });

    document.getElementById('btn-expand-races')?.addEventListener('click', () => {
      activePanel()?.querySelectorAll('.race-drawer').forEach((d) => {
        d.open = true;
      });
    });

    document.getElementById('btn-collapse-races')?.addEventListener('click', () => {
      activePanel()?.querySelectorAll('.race-drawer').forEach((d) => {
        d.open = false;
      });
    });

    const link = readDeepLink();
    if (link.meeting || link.raceId || link.race) {
      applyDeepLink();
    } else {
      let slug = meetingSel.value;
      try {
        const saved = localStorage.getItem(STORAGE_MEETING);
        if (saved && document.querySelector(`[data-meeting="${saved}"]`)) {
          meetingSel.value = saved;
          slug = saved;
        }
      } catch (_) {}
      switchMeeting(slug);
    }
  }

  function bindHero() {
    const panel = document.getElementById('hero-monitor');
    if (!panel) return;
    if (!window.location.search.includes('race_id=')) {
      panel.classList.add('is-open');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      bindRacecard();
      bindHero();
      window.HibsNoviceUX?.init();
    });
  } else {
    bindRacecard();
    bindHero();
    window.HibsNoviceUX?.init();
  }
})();

/** Novice UX translation layer — bankroll→cash, risk badges, smart picks, slip copy */
(function NoviceUX(global) {
  const STORAGE_BANKROLL = 'hibs_racing_bankroll';
  const STORAGE_UNIT_PCT = 'hibs_racing_unit_pct';
  const DEFAULT_UNIT_PCT = 1.0;

  const TIPS = {
    DQ: 'Data Quality Score: how complete and fresh our data is for this runner. High = more reliable.',
    EV: 'Expected Value: long-term estimated profit margin if you bet this consistently at these odds.',
    SHAP: 'Model Drivers: which stats most influenced the AI ranker selection.',
  };

  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function readBankroll() {
    const input = document.getElementById('bankroll-input');
    if (input && input.value !== '') {
      const v = parseFloat(input.value);
      if (!Number.isNaN(v) && v >= 0) return v;
    }
    try {
      const saved = parseFloat(localStorage.getItem(STORAGE_BANKROLL) || '');
      if (!Number.isNaN(saved) && saved >= 0) return saved;
    } catch (_) {}
    return null;
  }

  function unitPct() {
    try {
      const v = parseFloat(localStorage.getItem(STORAGE_UNIT_PCT) || DEFAULT_UNIT_PCT);
      return Number.isNaN(v) ? DEFAULT_UNIT_PCT : v;
    } catch (_) {
      return DEFAULT_UNIT_PCT;
    }
  }

  function impliedProb(row) {
    const mwp = parseFloat(row.model_win_prob ?? row.dataset?.modelWinProb ?? '');
    if (!Number.isNaN(mwp) && mwp > 0) return mwp;
    const odds = parseFloat(row.win_decimal ?? row.win_odds ?? row.dataset?.winOdds ?? '');
    if (!Number.isNaN(odds) && odds > 1) return 1 / odds;
    return null;
  }

  function riskProfile(prob) {
    if (prob == null || Number.isNaN(prob)) return null;
    if (prob > 0.45) return { cls: 'risk-low', label: 'Low Risk / Short Price' };
    if (prob >= 0.2) return { cls: 'risk-mid', label: 'Medium Risk / Mid Price' };
    return { cls: 'risk-high', label: 'High Risk / Longshot' };
  }

  function stakeCash(units, kellyMult) {
    const bankroll = readBankroll();
    if (bankroll == null) return null;
    const u = parseFloat(units) || 1;
    const k = parseFloat(kellyMult) || 1;
    const pct = unitPct() / 100;
    return Math.max(0, bankroll * pct * u * k);
  }

  function formatCash(amount) {
    if (amount == null) return '';
    return '£' + amount.toFixed(2);
  }

  function formatPct(units, kellyMult) {
    const pct = unitPct() * (parseFloat(units) || 1) * (parseFloat(kellyMult) || 1);
    return pct.toFixed(2) + '% of bankroll';
  }

  function applyRiskBadges(root) {
    (root || document).querySelectorAll('[data-win-odds], [data-model-win-prob], .pick-card[data-horse]').forEach((el) => {
      const prob = impliedProb({
        model_win_prob: el.dataset.modelWinProb,
        win_odds: el.dataset.winOdds,
      });
      const risk = riskProfile(prob);
      const slot = el.querySelector?.('.risk-badge-slot') || (el.classList?.contains('pick-title') ? el : null);
      const target = slot || el.querySelector('.horse-cell') || el.querySelector('.pick-title');
      if (!target || !risk) return;
      let badge = target.querySelector('.risk-badge');
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'risk-badge ' + risk.cls;
        target.appendChild(badge);
      } else {
        badge.className = 'risk-badge ' + risk.cls;
      }
      badge.textContent = '● ' + risk.label;
      badge.title = prob != null ? 'Implied win chance ~' + Math.round(prob * 100) + '%' : '';
    });
  }

  function applyStakeHints(root) {
    const bankroll = readBankroll();
    const hint = document.getElementById('bankroll-hint');
    if (hint) {
      hint.textContent = bankroll != null
        ? 'Stakes shown as cash (' + unitPct() + '% per unit × Kelly multiplier).'
        : 'Set your bankroll to see recommended stakes in cash (1 unit = ' + unitPct() + '% of bankroll).';
    }
    (root || document).querySelectorAll('[data-stake-units], .pick-card[data-horse]').forEach((row) => {
      const units = row.dataset.stakeUnits || 1;
      const kelly = row.dataset.kellyMult || 1;
      const cash = stakeCash(units, kelly);
      const pct = formatPct(units, kelly);
      const slots = row.querySelectorAll('.stake-cash-slot');
      slots.forEach((slot) => {
        if (cash == null) {
          slot.textContent = 'Stake: ' + pct;
          return;
        }
        slot.textContent = 'Recommended: ' + formatCash(cash) + ' (' + pct + ')';
      });
      row.querySelectorAll('.stake-units-label').forEach((lab) => {
        lab.textContent = cash != null ? formatCash(cash) : units + 'u';
      });
    });
    document.querySelectorAll('#hero-top-places .hero-pick').forEach((card) => {
      const cash = stakeCash(1, 1);
      if (cash == null) return;
      let el = card.querySelector('.stake-cash-hint');
      if (!el) {
        el = document.createElement('div');
        el.className = 'stake-cash-hint';
        card.appendChild(el);
      }
      el.textContent = 'Suggested stake: ' + formatCash(cash);
    });
  }

  function pickFromCard(card) {
    const horse = card.dataset.horse || '';
    const candidates = loadCandidates();
    const full = candidates.find((c) => c.horse_name === horse) || {};
    return {
      horse_name: horse,
      course: card.dataset.course || full.course || '',
      off_time: card.dataset.off || full.off_time || '',
      win_decimal: card.dataset.winOdds || full.win_decimal || '',
      bet_type: card.dataset.betType || full.bet_type || 'each_way',
      monetized_link: card.dataset.monetizedLink || full.monetized_link || '',
    };
  }

  function slipText(pick) {
    const course = pick.course || '';
    const off = pick.off_time || '';
    const horse = pick.horse_name || '';
    const odds = pick.win_decimal || '';
    const betType = pick.bet_type || 'each_way';
    const betLabel = betType === 'each_way' ? 'Each-Way' : betType;
    const oddsBit = odds ? ' (' + odds + ' EW)' : '';
    const head = 'Hibs Smart Pick: ' + off + ' ' + course + ' - ' + horse + oddsBit + ' - ' + betLabel;
    if (pick.monetized_link) {
      return head + '\nSecure these odds via our verified partner: ' + pick.monetized_link;
    }
    return head;
  }

  async function copySlip(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
      if (btn) {
        const prev = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = prev; }, 1500);
      }
    } catch (_) {
      alert(text);
    }
  }

  function bindSlipCopy() {
    document.querySelectorAll('[data-slip-copy]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const card = btn.closest('.pick-card, .smart-pick-card, tr');
        if (!card) return;
        const pick = card.classList.contains('smart-pick-card') || card.dataset.horse
          ? pickFromCard(card)
          : {
              horse_name: card.querySelector('.horse-cell')?.textContent?.trim(),
              course: card.dataset.course,
              off_time: card.dataset.off,
              win_decimal: card.dataset.winOdds,
              bet_type: 'each_way',
              monetized_link: '',
            };
        copySlip(slipText(pick), btn);
      });
    });
  }

  function loadCandidates() {
    const el = document.getElementById('pick-candidates-data');
    if (!el) return [];
    try {
      return JSON.parse(el.textContent || '[]');
    } catch (_) {
      return [];
    }
  }

  function gateReasonIsClear(reason) {
    if (reason == null) return true;
    if (typeof reason === 'number' && Number.isNaN(reason)) return true;
    if (typeof reason === 'string' && !reason.trim()) return true;
    return false;
  }

  function isValuePick(flag) {
    return flag === true || flag === 1 || flag === '1';
  }

  function filterSmartPicks(candidates) {
    const allowedGates = new Set(['proceed', 'scale_up', 'unknown']);
    return candidates
      .filter(
        (c) =>
          isValuePick(c.value_flag) &&
          gateReasonIsClear(c.value_gate_reason) &&
          (c.data_quality_pct || 0) >= 75 &&
          allowedGates.has(String(c.steam_gate || 'proceed').toLowerCase()),
      )
      .sort((a, b) => {
        const sa = parseFloat(a.place_score || a.model_place_prob || 0);
        const sb = parseFloat(b.place_score || b.model_place_prob || 0);
        return sb - sa;
      })
      .slice(0, 3);
  }

  function formatPickLine(pick, index) {
    const horse = pick.horse_name || '?';
    const course = pick.course || '?';
    const off = pick.off_time || '?';
    const dq = pick.data_quality_pct || 0;
    const gate = pick.steam_gate || 'proceed';
    const placePct = Math.round((parseFloat(pick.model_place_prob) || 0) * 100);
    const ev = pick.ew_combined_ev;
    const evS = ev != null ? Number(ev).toFixed(2) : '—';
    const winS = pick.win_decimal ? ` · win ${Number(pick.win_decimal).toFixed(2)}` : '';
    const linkS = pick.monetized_link ? `\n   Partner: ${pick.monetized_link}` : '';
    return (
      `#${index} ${horse} (${off} ${course})\n` +
      `   Place ${placePct}% · EV ${evS} · DQ ${dq}% · gate ${gate}${winS}${linkS}`
    );
  }

  function formatChannelDigest(picks, cardDates) {
    const dates = (cardDates && cardDates.length) ? cardDates.join(', ') : 'today';
    const lines = [
      '🏇 Hibs Racing Intelligence — Daily Value Sheet',
      `Cards: ${dates}`,
      '',
    ];
    if (!picks.length) {
      lines.push('No value picks passed filters today (value + DQ≥75% + steam gate).');
      lines.push('Tracker: /tracker');
    } else {
      picks.forEach((pick, i) => {
        lines.push(formatPickLine(pick, i + 1));
        lines.push('');
      });
      lines.push('Each-way paper picks logged to public SHA-256 ledger.');
    }
    return lines.join('\n').trim();
  }

  function loadCardDates() {
    const el = document.getElementById('card-dates-data');
    if (!el) return [];
    try {
      return JSON.parse(el.textContent || '[]');
    } catch (_) {
      return [];
    }
  }

  function renderChannelDigest() {
    const el = document.getElementById('channel-digest-text');
    if (!el) return;
    const picks = filterSmartPicks(loadCandidates());
    el.textContent = formatChannelDigest(picks, loadCardDates());
  }

  function renderSmartPicks() {
    const grid = document.getElementById('smart-picks-grid');
    if (!grid) return;
    const picks = filterSmartPicks(loadCandidates());
    if (!picks.length) {
      grid.innerHTML = '<div class="smart-pick-card"><span class="sp-meta">No picks pass all filters yet (value + data quality ≥75% + steam gate). Refresh cards after racing starts.</span></div>';
      return;
    }
    grid.innerHTML = picks.map((p, i) => {
      const cash = stakeCash(p.stake_units || 1, p.kelly_multiplier || 1);
      const risk = riskProfile(impliedProb(p));
      const riskHtml = risk ? `<span class="risk-badge ${risk.cls}">● ${esc(risk.label)}</span>` : '';
      const cashHtml = cash != null ? `<div class="stake-cash-hint">Suggested stake: ${formatCash(cash)}</div>` : '';
      const oddsHtml = p.win_decimal && p.monetized_link
        ? `<a class="odds-affiliate-link" href="${encodeURI(p.monetized_link)}" target="_blank" rel="noopener sponsored" title="Open partner odds">win ${p.win_decimal}</a>`
        : (p.win_decimal ? ' · win ' + p.win_decimal : '');
      return `
        <div class="smart-pick-card" data-horse="${esc(p.horse_name)}" data-course="${esc(p.course)}" data-off="${esc(p.off_time)}" data-win-odds="${p.win_decimal || ''}" data-bet-type="each_way" data-monetized-link="${esc(p.monetized_link || '')}">
          <div class="sp-horse">#${i + 1} ${esc(p.horse_name)} ${riskHtml}</div>
          <div class="sp-meta">${esc(p.off_time)} · ${esc(p.course)} · DQ ${p.data_quality_pct}% · gate ${esc(p.steam_gate)}</div>
          <div class="sp-meta">Place ${Math.round((parseFloat(p.model_place_prob) || 0) * 100)}% · EV ${p.ew_combined_ev != null ? Number(p.ew_combined_ev).toFixed(2) : '—'}${oddsHtml ? ' · ' + oddsHtml : ''}</div>
          ${cashHtml}
          <button type="button" class="slip-copy-btn" data-slip-copy style="margin-top:8px;">📋 Copy slip</button>
        </div>`;
    }).join('');
    bindSlipCopy();
    applyRiskBadges(grid);
    renderChannelDigest();
  }

  function bindBankroll() {
    const input = document.getElementById('bankroll-input');
    if (!input) return;
    try {
      const saved = localStorage.getItem(STORAGE_BANKROLL);
      if (saved) input.value = saved;
    } catch (_) {}
    const sync = () => {
      try {
        if (input.value !== '') localStorage.setItem(STORAGE_BANKROLL, input.value);
      } catch (_) {}
      applyStakeHints();
      renderSmartPicks();
    };
    input.addEventListener('input', sync);
    input.addEventListener('change', sync);
  }

  function init() {
    bindBankroll();
    bindSlipCopy();
    renderSmartPicks();
    renderChannelDigest();
    applyRiskBadges();
    applyStakeHints();
  }

  global.HibsNoviceUX = {
    init,
    readBankroll,
    stakeCash,
    riskProfile,
    impliedProb,
    filterSmartPicks,
    applyStakeHints,
    renderSmartPicks,
    renderChannelDigest,
    formatChannelDigest,
    TIPS,
  };
})(window);
