/**
 * Stack ops banner — traffic shed from football /api/stack/evidence + low-compute mode.
 */
(function hibsOpsBanner(global) {
  const cfgEl = document.getElementById('hibs-stack-evidence-config');
  const banner = document.getElementById('hibs-traffic-shed-banner');
  if (!cfgEl || !banner) return;

  let cfg = {};
  try {
    cfg = JSON.parse(cfgEl.textContent || '{}');
  } catch (_) {
    return;
  }

  const evidenceUrl = String(cfg.evidenceUrl || '').trim();
  const pollMs = Math.max(30000, Number(cfg.pollMs) || 90000);
  if (!evidenceUrl) return;

  function setShed(active, reason) {
    const was = document.documentElement.classList.contains('hibs-traffic-shed');
    banner.hidden = !active;
    if (!active) {
      banner.textContent = '';
      document.documentElement.classList.remove('hibs-traffic-shed');
    } else {
      document.documentElement.classList.add('hibs-traffic-shed');
      banner.textContent =
        reason ||
        'High load — live animations reduced. Core picks and cards still work.';
    }
    if (was !== active) {
      document.dispatchEvent(new CustomEvent('hibs-traffic-shed-change', { detail: { active } }));
    }
  }

  async function poll() {
    try {
      const r = await fetch(evidenceUrl, { credentials: 'same-origin', cache: 'no-store' });
      if (r.status === 503) {
        let reason = 'Traffic shed active — reduced refresh rate.';
        try {
          const body = await r.json();
          reason = body.detail || body.traffic_shed_reason || reason;
        } catch (_) {}
        setShed(true, typeof reason === 'string' ? reason : 'Traffic shed active.');
        return;
      }
      if (!r.ok) {
        setShed(false);
        return;
      }
      const data = await r.json();
      setShed(Boolean(data.traffic_shed), data.traffic_shed_reason || null);
    } catch (_) {
      /* football stack unreachable from racing — hide banner */
      setShed(false);
    }
  }

  poll();
  setInterval(poll, pollMs);
})(window);
