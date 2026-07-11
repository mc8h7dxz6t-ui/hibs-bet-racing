(function () {
  "use strict";

  const GATE_ORDER = [
    "ledger_chain",
    "genesis_block",
    "lamport_order",
    "F1",
    "F2",
    "F3",
    "F4",
    "F5",
    "F6",
    "F7",
    "F8",
    "F9",
  ];

  function $(sel) {
    return document.querySelector(sel);
  }

  function setOutput(id, data) {
    const el = $(id);
    if (!el) return;
    el.textContent =
      typeof data === "string" ? data : JSON.stringify(data, null, 2);
  }

  async function api(method, path, body) {
    const opts = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    const text = await res.text();
    let json;
    try {
      json = text ? JSON.parse(text) : {};
    } catch {
      json = { raw: text };
    }
    if (!res.ok) {
      const err = new Error(json.detail || json.message || res.statusText);
      err.status = res.status;
      err.payload = json;
      throw err;
    }
    return json;
  }

  function parseJsonField(id, label) {
    const raw = $(id).value.trim();
    if (!raw) return {};
    try {
      return JSON.parse(raw);
    } catch (e) {
      throw new Error(`${label}: invalid JSON — ${e.message}`);
    }
  }

  function renderGates(containerId, checks) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = "";
    const byName = {};
    (checks || []).forEach((c) => {
      byName[c.name] = c;
    });
    GATE_ORDER.forEach((name) => {
      const c = byName[name];
      if (!c) return;
      const cell = document.createElement("div");
      cell.className = "gate-cell " + (c.passed ? "pass" : "fail");
      cell.innerHTML =
        `<span class="gid">${c.name}</span>` +
        `<span class="detail">${escapeHtml(c.detail || "")}</span>`;
      el.appendChild(cell);
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function markStep(stepsId, step, state) {
    const card = document.querySelector(`#${stepsId} .step-card[data-step="${step}"]`);
    if (!card) return;
    card.classList.remove("done", "active");
    if (state) card.classList.add(state);
  }

  function renderLedger(containerId, entries) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!entries || !entries.length) {
      el.innerHTML = '<p style="color:var(--muted);font-size:0.8rem">No entries yet.</p>';
      return;
    }
    const rows = entries.slice(-12).reverse();
    const cols = ["block_index", "event_type", "lamport", "hash"];
    let html =
      '<table class="ledger-table"><thead><tr>' +
      cols.map((c) => `<th>${c}</th>`).join("") +
      "</tr></thead><tbody>";
    rows.forEach((e) => {
      html +=
        "<tr>" +
        cols
          .map((c) => {
            let v = e[c];
            if (c === "hash" && v) v = String(v).slice(0, 12) + "…";
            return `<td>${escapeHtml(v ?? "")}</td>`;
          })
          .join("") +
        "</tr>";
    });
    html += "</tbody></table>";
    el.innerHTML = html;
  }

  function showDecision(data) {
    const el = $("#proxy-decision");
    if (!el) return;
    const d = (data.decision || "").toLowerCase();
    const cls = d === "approve" ? "approve" : d === "kill" ? "kill" : "reject";
    el.innerHTML =
      `<span class="decision-pill ${cls}">${escapeHtml(data.decision || "?")}</span> ` +
      `<span style="font-size:0.8rem;color:var(--muted)">${escapeHtml(data.reason || "")}</span>`;
  }

  function initTabs() {
    document.querySelectorAll(".tabs button").forEach((btn) => {
      btn.addEventListener("click", () => {
        activateTab(btn.getAttribute("data-tab"));
      });
    });
  }

  function activateTab(tab) {
    if (!tab) return;
    document.querySelectorAll(".tabs button").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-tab") === tab);
    });
    document.querySelectorAll(".panel").forEach((p) => {
      p.classList.toggle("active", p.id === `panel-${tab}`);
    });
  }

  function applyProductConfig(cfg) {
    const title = document.getElementById("header-title");
    const badge = document.getElementById("header-badge");
    if (title) title.textContent = cfg.title || "Workflow Console";
    if (badge) badge.textContent = cfg.badge || "";

    const tabs = cfg.tabs || {};
    const tabMap = {
      arch: "tab-arch",
      proof: "tab-proof",
      compliance: "tab-compliance",
      proxy: "tab-proxy",
    };
    Object.entries(tabMap).forEach(([key, id]) => {
      const el = document.getElementById(id);
      if (el) el.style.display = tabs[key] ? "" : "none";
    });

    const archCompliance = document.getElementById("arch-compliance");
    const archProxy = document.getElementById("arch-proxy");
    if (archCompliance) archCompliance.style.display = tabs.compliance ? "" : "none";
    if (archProxy) archProxy.style.display = tabs.proxy ? "" : "none";

    const archSplit = document.querySelector(".arch-split");
    if (archSplit && cfg.product !== "both") {
      archSplit.style.gridTemplateColumns = "1fr";
    }

    activateTab(cfg.default_tab || "arch");
  }

  let activeProofProduct = "compliance";

  const GUIDED_INGEST_IDS = new Set([
    "compliance",
    "proxy",
    "altdata",
    "ai-kit",
    "webhook-mesh",
    "ad-guard",
    "health",
    "model-governor",
    "drift-gate",
    "webhook-replay",
    "spend-guard",
    "agent-ledger",
  ]);

  function supportsProofIngest(productId) {
    return GUIDED_INGEST_IDS.has(productId);
  }

  function updateProofIngestUi() {
    const hint = document.getElementById("proof-ingest-hint");
    const payloadEl = document.getElementById("proof-ingest-payload");
    const btnDemo = document.getElementById("btn-proof-demo-payload");
    const btnIngest = document.getElementById("btn-proof-ingest");
    const guided = supportsProofIngest(activeProofProduct);
    if (hint) {
      hint.textContent = guided
        ? "Guided ingest — load demo payload or edit JSON, then Ingest."
        : "Select a product from the picker.";
    }
    if (payloadEl) payloadEl.disabled = !guided;
    if (btnDemo) btnDemo.style.display = guided ? "" : "none";
    if (btnIngest) btnIngest.style.display = guided ? "" : "none";
  }

  async function loadProofCatalog() {
    const data = await api("GET", "/api/products");
    const picker = document.getElementById("proof-product-picker");
    if (!picker) return data;
    picker.innerHTML = "";
    (data.catalog || []).forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.label}${p.database_present ? "" : " (no DB)"}`;
      picker.appendChild(opt);
    });
    activeProofProduct = data.active || (data.catalog[0] && data.catalog[0].id) || "compliance";
    picker.value = activeProofProduct;
    updateProofMeta(data.catalog || []);
    updateProofIngestUi();
    return data;
  }

  function updateProofMeta(catalog) {
    const entry = (catalog || []).find((p) => p.id === activeProofProduct);
    const tag = document.getElementById("proof-tagline");
    const st = document.getElementById("proof-db-status");
    if (tag && entry) tag.textContent = entry.tagline || "";
    if (st && entry) {
      st.textContent = entry.database_present
        ? `DB: ${entry.database}`
        : `Missing DB — bootstrap SKU or ingest`;
      st.style.color = entry.database_present ? "var(--muted)" : "#c45c5c";
    }
    updateProofIngestUi();
  }

  async function onProofSelect() {
    const picker = document.getElementById("proof-product-picker");
    if (!picker) return;
    activeProofProduct = picker.value;
    await api("POST", "/api/proof/select", { product_id: activeProofProduct });
    const cat = await api("GET", "/api/products");
    updateProofMeta(cat.catalog || []);
    setOutput("#proof-output", `Selected: ${activeProofProduct}`);
    await loadProofLedger();
  }

  async function onProofDemoPayload() {
    try {
      const data = await api("GET", `/api/proof/${activeProofProduct}/demo-payload`);
      const el = document.getElementById("proof-ingest-payload");
      if (el) el.value = JSON.stringify(data.payload, null, 2);
      const hint = document.getElementById("proof-ingest-hint");
      if (hint && data.schema && data.schema.hint) {
        hint.textContent = data.schema.hint;
      }
      setOutput("#proof-output", "Demo payload loaded.");
    } catch (e) {
      setOutput("#proof-output", e.payload || e.message || String(e));
    }
  }

  async function onProofIngest() {
    try {
      markStep("proof-steps", "0", "active");
      const payload = parseJsonField("#proof-ingest-payload", "Ingest payload");
      const data = await api("POST", `/api/proof/${activeProofProduct}/ingest`, { payload });
      markStep("proof-steps", "0", data.ok !== false ? "done" : "active");
      markStep("proof-steps", "1", "done");
      setOutput("#proof-output", data);
      const cat = await api("GET", "/api/products");
      updateProofMeta(cat.catalog || []);
      await loadProofLedger();
    } catch (e) {
      setOutput("#proof-output", e.payload || e.message || String(e));
    }
  }

  async function loadProofLedger() {
    const data = await api("GET", `/api/proof/${activeProofProduct}/ledger`);
    renderLedger("proof-ledger", data.entries);
    if (data.count > 0) markStep("proof-steps", "1", "done");
    return data;
  }

  async function onProofCheck() {
    try {
      markStep("proof-steps", "2", "active");
      const data = await api("POST", `/api/proof/${activeProofProduct}/check`);
      renderGates("proof-gates", data.checks);
      markStep("proof-steps", "2", data.passed ? "done" : "active");
      setOutput("#proof-output", data);
    } catch (e) {
      setOutput("#proof-output", e.payload || e.message || String(e));
    }
  }

  async function onProofExport() {
    try {
      markStep("proof-steps", "3", "active");
      const data = await api("POST", `/api/proof/${activeProofProduct}/export`);
      markStep("proof-steps", "3", "done");
      setOutput("#proof-output", data);
    } catch (e) {
      setOutput("#proof-output", e.payload || e.message || String(e));
    }
  }

  async function onProofVerify() {
    try {
      markStep("proof-steps", "4", "active");
      const data = await api("POST", `/api/proof/${activeProofProduct}/verify-bundle`);
      markStep("proof-steps", "4", data.ok ? "done" : "active");
      setOutput("#proof-output", data);
    } catch (e) {
      setOutput("#proof-output", e.payload || e.message || String(e));
    }
  }

  async function loadProductConfig() {
    const cfg = await api("GET", "/api/config");
    applyProductConfig(cfg);
    return cfg;
  }

  async function loadComplianceLedger() {
    const data = await api("GET", "/api/compliance/ledger");
    renderLedger("compliance-ledger", data.entries);
    if (data.count > 0) {
      markStep("compliance-steps", "2", "done");
    }
    return data;
  }

  async function loadProxyLedger() {
    const data = await api("GET", "/api/proxy/ledger");
    renderLedger("proxy-ledger", data.proxy_rows || data.entries);
    return data;
  }

  async function onComplianceDemo() {
    const snap = await api("GET", "/api/demo/compliance-snapshot");
    $("#compliance-snapshot").value = JSON.stringify(snap, null, 2);
    setOutput("#compliance-output", "Demo snapshot loaded.");
  }

  async function onComplianceIngest() {
    try {
      markStep("compliance-steps", "1", "active");
      const snapshot = parseJsonField("#compliance-snapshot", "Snapshot");
      const outcome = parseJsonField("#compliance-outcome", "Outcome");
      const data = await api("POST", "/api/compliance/ingest", { snapshot, outcome });
      markStep("compliance-steps", "1", "done");
      markStep("compliance-steps", "2", "done");
      setOutput("#compliance-output", data);
      await loadComplianceLedger();
    } catch (e) {
      setOutput("#compliance-output", e.message || String(e));
    }
  }

  async function onComplianceCheck() {
    try {
      markStep("compliance-steps", "3", "active");
      const data = await api("POST", "/api/compliance/check");
      renderGates("compliance-gates", data.checks);
      markStep("compliance-steps", "3", data.passed ? "done" : "active");
      setOutput("#compliance-output", data);
    } catch (e) {
      setOutput("#compliance-output", e.message || String(e));
    }
  }

  async function onComplianceExport() {
    try {
      markStep("compliance-steps", "4", "active");
      const data = await api("POST", "/api/compliance/export");
      markStep("compliance-steps", "4", "done");
      setOutput("#compliance-output", data);
    } catch (e) {
      setOutput("#compliance-output", e.payload || e.message || String(e));
    }
  }

  async function onComplianceVerify() {
    try {
      markStep("compliance-steps", "5", "active");
      const data = await api("POST", "/api/compliance/verify-bundle");
      markStep("compliance-steps", "5", data.ok ? "done" : "active");
      setOutput("#compliance-output", data);
    } catch (e) {
      setOutput("#compliance-output", e.payload || e.message || String(e));
    }
  }

  async function onProxyDemo() {
    const req = await api("GET", "/api/demo/proxy-request");
    $("#proxy-request").value = JSON.stringify(req, null, 2);
    setOutput("#proxy-output", "Demo request loaded.");
  }

  async function onProxyEvaluate(live) {
    try {
      const step = live ? "2" : "1";
      markStep("proxy-steps", step, "active");
      const body = parseJsonField("#proxy-request", "Request");
      const data = await api("POST", "/api/proxy/evaluate", { ...body, live });
      showDecision(data);
      markStep("proxy-steps", step, "done");
      setOutput("#proxy-output", data);
      await loadProxyLedger();
    } catch (e) {
      setOutput("#proxy-output", e.payload || e.message || String(e));
    }
  }

  async function onProxyCheck() {
    try {
      markStep("proxy-steps", "3", "active");
      const data = await api("POST", "/api/proxy/check");
      renderGates("proxy-gates", data.checks);
      markStep("proxy-steps", "3", data.passed ? "done" : "active");
      setOutput("#proxy-output", data);
    } catch (e) {
      setOutput("#proxy-output", e.message || String(e));
    }
  }

  async function onProxyExport() {
    try {
      markStep("proxy-steps", "4", "active");
      const data = await api("POST", "/api/proxy/export");
      markStep("proxy-steps", "4", "done");
      setOutput("#proxy-output", data);
    } catch (e) {
      setOutput("#proxy-output", e.payload || e.message || String(e));
    }
  }

  async function onProxyVerify() {
    try {
      markStep("proxy-steps", "5", "active");
      const data = await api("POST", "/api/proxy/verify-bundle");
      markStep("proxy-steps", "5", data.ok ? "done" : "active");
      setOutput("#proxy-output", data);
    } catch (e) {
      setOutput("#proxy-output", e.payload || e.message || String(e));
    }
  }

  async function onProofBootstrap() {
    try {
      setOutput("#proof-output", "Bootstrapping SKU demo…");
      const data = await api("POST", `/api/proof/${activeProofProduct}/bootstrap`);
      setOutput("#proof-output", data);
      const cat = await api("GET", "/api/products");
      updateProofMeta(cat.catalog || []);
      await loadProofLedger();
    } catch (e) {
      setOutput("#proof-output", e.payload || e.message || String(e));
    }
  }

  async function onProofBootstrapAll() {
    try {
      setOutput("#proof-output", "Bootstrapping all 12 SKUs (offline)…");
      const data = await api("POST", "/api/proof/bootstrap-all");
      setOutput("#proof-output", data);
      await loadProofCatalog();
      await loadProofLedger();
    } catch (e) {
      setOutput("#proof-output", e.payload || e.message || String(e));
    }
  }

  async function onProofVerifyAll() {
    try {
      setOutput("#proof-output", "Verifying all 12 bundles offline…");
      const data = await api("POST", "/api/proof/verify-all");
      setOutput("#proof-output", data);
    } catch (e) {
      setOutput("#proof-output", e.payload || e.message || String(e));
    }
  }

  function bind(id, fn) {
    const el = document.getElementById(id);
    if (el) el.addEventListener("click", fn);
  }

  document.addEventListener("DOMContentLoaded", async () => {
    initTabs();
    let cfg = { tabs: { compliance: true, proxy: true } };
    try {
      cfg = await loadProductConfig();
    } catch {
      /* keep defaults */
    }
    bind("btn-compliance-demo", onComplianceDemo);
    bind("btn-compliance-ingest", onComplianceIngest);
    bind("btn-compliance-check", onComplianceCheck);
    bind("btn-compliance-export", onComplianceExport);
    bind("btn-compliance-verify", onComplianceVerify);
    bind("btn-proxy-demo", onProxyDemo);
    bind("btn-proxy-shadow", () => onProxyEvaluate(false));
    bind("btn-proxy-live", () => onProxyEvaluate(true));
    bind("btn-proxy-check", onProxyCheck);
    bind("btn-proxy-export", onProxyExport);
    bind("btn-proxy-verify", onProxyVerify);
    const proofPicker = document.getElementById("proof-product-picker");
    if (proofPicker) {
      proofPicker.addEventListener("change", () => onProofSelect().catch((e) => setOutput("#proof-output", e.message)));
    }
    bind("btn-proof-demo-payload", onProofDemoPayload);
    bind("btn-proof-ingest", onProofIngest);
    bind("btn-proof-bootstrap", onProofBootstrap);
    bind("btn-proof-bootstrap-all", onProofBootstrapAll);
    bind("btn-proof-refresh", () => loadProofLedger().catch((e) => setOutput("#proof-output", e.message)));
    bind("btn-proof-check", onProofCheck);
    bind("btn-proof-export", onProofExport);
    bind("btn-proof-verify", onProofVerify);
    bind("btn-proof-verify-all", onProofVerifyAll);
    if (cfg.tabs?.proof !== false) {
      loadProofCatalog()
        .then(() => loadProofLedger())
        .catch(() => {});
    }
    if (cfg.tabs?.compliance) loadComplianceLedger().catch(() => {});
    if (cfg.tabs?.proxy) loadProxyLedger().catch(() => {});
  });
})();
