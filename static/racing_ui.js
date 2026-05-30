/** hibs-racing racecard UI — meeting/race navigation, single-race accordion, persisted state */

(function () {
  const STORAGE_MEETING = 'hibs_racing_meeting';
  const STORAGE_RACE = 'hibs_racing_race';
  const STORAGE_HERO = 'hibs_racing_hero_open';

  function activePanel() {
    return document.querySelector('.meeting-panel.is-active');
  }

  function rebuildRaceSelect(panel) {
    const raceSel = document.getElementById('race-select');
    if (!raceSel || !panel) return;
    raceSel.innerHTML = '';
    panel.querySelectorAll('.race-drawer').forEach((el, i) => {
      const opt = document.createElement('option');
      opt.value = el.id;
      const off = el.dataset.off || '?';
      const name = el.querySelector('.race-name')?.textContent?.trim() || 'Race';
      opt.textContent = `${off} · ${name.slice(0, 52)}`;
      raceSel.appendChild(opt);
    });
  }

  function openRace(raceId, panel) {
    panel = panel || activePanel();
    if (!panel) return;
    panel.querySelectorAll('.race-drawer').forEach((d) => {
      d.open = d.id === raceId;
    });
    const drawer = document.getElementById(raceId);
    if (drawer) {
      drawer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      try {
        localStorage.setItem(STORAGE_RACE, raceId);
      } catch (_) {}
    }
    panel.querySelectorAll('.race-tab').forEach((t) => {
      t.classList.toggle('is-active', t.dataset.target === raceId);
      t.setAttribute('aria-selected', t.dataset.target === raceId ? 'true' : 'false');
    });
    const raceSel = document.getElementById('race-select');
    if (raceSel && raceSel.value !== raceId) raceSel.value = raceId;
  }

  function switchMeeting(slug) {
    document.querySelectorAll('.meeting-panel').forEach((p) => {
      const on = p.dataset.meeting === slug;
      p.classList.toggle('is-active', on);
      p.hidden = !on;
    });
    const panel = activePanel();
    rebuildRaceSelect(panel);
    try {
      localStorage.setItem(STORAGE_MEETING, slug);
    } catch (_) {}
    let raceId = null;
    try {
      raceId = localStorage.getItem(STORAGE_RACE);
    } catch (_) {}
    const saved = raceId && panel?.querySelector(`#${CSS.escape(raceId)}`);
    const target = saved ? raceId : panel?.querySelector('.race-drawer')?.id;
    if (target) openRace(target, panel);
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

    let slug = meetingSel.value;
    try {
      const saved = localStorage.getItem(STORAGE_MEETING);
      if (saved && document.querySelector(`[data-meeting="${saved}"]`)) {
        meetingSel.value = saved;
        slug = saved;
      }
    } catch (_) {}
    switchMeeting(slug);
    const opt = meetingSel.options[meetingSel.selectedIndex];
    const hint = document.getElementById('meeting-hint');
    if (hint && opt?.dataset.hint) hint.textContent = opt.dataset.hint;
  }

  function bindHero() {
    const panel = document.getElementById('hero-monitor');
    const btn = document.getElementById('hero-collapse-btn');
    if (!panel || !btn) return;
    let open = false;
    try {
      open = localStorage.getItem(STORAGE_HERO) === '1';
    } catch (_) {}
    panel.classList.toggle('is-open', open);
    btn.textContent = open ? 'Hide picks' : 'Show picks';
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.addEventListener('click', () => {
      open = panel.classList.toggle('is-open');
      btn.textContent = open ? 'Hide picks' : 'Show picks';
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      try {
        localStorage.setItem(STORAGE_HERO, open ? '1' : '0');
      } catch (_) {}
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      bindRacecard();
      bindHero();
    });
  } else {
    bindRacecard();
    bindHero();
  }
})();
