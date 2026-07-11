# Governor Portfolio — Tech Spec, Bundle Wiring, and Diligence

**Audience:** Chief systems architects, acquirers, design partners, internal GTM  
**Repo:** `hibs-bet-racing` (Inst++ 12-SKU portfolio on `inst_spine`)  
**As-of:** July 2026  
**Status:** 🟡 **Active hardening** — governors are **not** frozen or vendor-of-record ready; engineering and audit posture improve continuously on two parallel tracks (below).  
**Policy:** **No commercial figures in this document** — license fees, deal sizes, valuations, and buyer spend thresholds belong in external SOWs and order forms only.

---

## Hardening status (read before diligence)

Governors are **still being hardened and improved**. Treat every forensic score, compose-smoke claim, and platform port map as **point-in-time engineering**, not a shipped certification.

### Two parallel hardening tracks

| Track | Where | What is moving | Buyer can rely on today |
|-------|-------|----------------|-------------------------|
| **A — Inst++ SKU + bundle ingredients** | This repo (`hibs-bet-racing`) | Production profile `/ready`, Redis/Postgres gates, observation-lane export, WAL/replay scale, rigorous E2E per SKU | **CLI proof spine** — `make plug` / `make proof`, offline `verify-bundle`, design-partner VPC pilots on individual SKUs |
| **B — Four governor platforms** | External `modelgovernor.v01` (not this tree) | Industry-hardening waves: asyncpg SERIALIZABLE reserve, Lua Redis CAS guardrails, Ed25519 bundle sign, mmap `.wrcap` WAL, phase 3–4 closure (ADR 002/003), `deployment-forensic-review`, `gov-live-demo` | **Engineering in flight** — local/CI proof when that repo is in scope; **do not** attribute platform scores to this repo alone |

**Bundle labels (FG / IG / CG)** in track A are **recipes over improving SKUs** — not a unified platform binary. **ModelGovernor (#8)** is the only governor-named **product** in this tree; it is also under active hardening (deploy drift gate, gold demo, export).

### What “hardening” means (no false finish line)

| Layer | In progress (both tracks) | Not done / not claimed |
|-------|---------------------------|-------------------------|
| **Concurrency** | SERIALIZABLE reserve paths (external MG); idempotent wallet replay (SKU #11) | Global chain partition; repair CronJob for orphaned business rows (external) |
| **HA / scale** | Redis fail-closed, stream dispatch, Lua guardrails (external + partial SKU) | Mandatory Postgres in all rigorous CI paths; PgBouncer + asyncpg soak everywhere |
| **Audit / crypto** | `verify_chain_linkage` for observation lane; optional Ed25519 (both) | Mandatory signing on all examiner packs; key rotation `trusted_public_keys[]` |
| **Ingress / egress** | WAL-before-ack (#5, #10); proxy gate chain (#2) | mTLS/HMAC on all webhook ingress; Envoy ext_authz (CG platform) |
| **Mesh / wedges** | Env-wired drift + deploy (#8+#9), proxy baseline (#2+#9) | Warranty mesh (parent FROZEN → child block); ClaimGate, WireMatch, AlgoFreeze as code |
| **Compliance packs** | SOC2/HIPAA **templates** | SOC 2 Type II, signed BAA, IL 9 letters |

### How to cite readiness externally

| Safe to say | Do not say yet |
|-------------|----------------|
| “Inst++ audit spine with offline verify-bundle on 12 SKUs” | “Four governor platforms production-ready” (from this repo alone) |
| “Governor bundles are SKU combinations we license and harden together” | “ClaimGate / AlgoFreeze / CG `:8120` shipped” |
| “Active hardening program; design-partner pilots on proof spine” | “IL 9 / 10 across portfolio” without naming the repo + commit + test log |
| “External MG platform repo has compose-smoke and forensic review (when green)” | “Vendor-of-record without operating company + SOC 2” |

**When this doc conflicts with a slide deck**, trust **git + test logs** (`make proof`, `instpp_rigorous_latest.log`, external `deployment-forensic-review` when applicable).

---

## Read this first — two different “governor” meanings

External decks and a separate **`modelgovernor.v01`** product line describe **four runnable governor platforms** (gateway / sidecar / reconciler / Postgres spine, ports 8080–8131, `governor-spine-core`, compose-smoke matrices, industry-hardening waves). **That platform tree is not in this repository.**

| Concept | In `hibs-bet-racing`? | Where it lives |
|---------|----------------------|----------------|
| **ModelGovernor platform** (`:8080` gateway, reserve-before-dispatch, asyncpg SERIALIZABLE) | ❌ | External `modelgovernor.v01` (or successor repo) |
| **Finance Governor platform** (`:8090` CCP spine, WireMatch, AlgoFreeze) | ❌ | External repo / sales fiction if sold from *this* tree alone |
| **Insurance Governor platform** (`:8100` ClaimGate, FNOL mesh, FedNow smoke) | ❌ | External repo |
| **Cybersecurity Governor platform** (`:8120` EgressGovern, Envoy ext_authz) | ❌ | External repo |
| **ModelGovernor SKU #8** (lifecycle CLI on `inst_spine`) | ✅ | `src/model_governor/` |
| **Finance / Insurance / Cyber “Governors”** as **bundle labels** | ✅ (marketing only) | Combinations of Inst++ SKUs below |
| **ClaimGate, AlgoFreeze, `:8128` ComplianceLogger wedge** | ❌ | Zero code references — diligence-fatal if claimed from this repo |

**Honest one-liner for this repo:** Twelve standalone audit SKUs share one cryptographic spine; four “Governor” names are **vertical bundles** (SKU recipes), except **ModelGovernor (#8)** which is also a real CLI product.

Cross-check: [FORENSIC_ARCHITECTURE_TRUTH.md](FORENSIC_ARCHITECTURE_TRUTH.md) · [compliance/README.md](compliance/README.md) · `deploy/football-inst-overlay/src/hibs_predictor/stack_truth.py`

---

## Governor bundle wiring (ingredients)

Bundles are **not** separate binaries. They are **licensed combinations** of existing SKUs with shared `inst_spine` export and offline `verify-bundle`.

### Ingredient map

| Inst++ SKU | Finance Governor (FG) | Insurance Governor (IG) | Cyber Governor (CG) wedge | In-repo anchor |
|------------|----------------------|-------------------------|----------------------------|----------------|
| **#1** `compliance-log` | — | ✅ Core (decision attestation) | ✅ Evidence export wedge | `src/compliance_log/` · `compliance-log-serve` · `INST_COMPLIANCE_OBSERVATION_LANE` |
| **#2** `proxy-risk` | ✅ Optional (egress gate pattern) | — | ✅ Outbound gate + audit | `src/proxy_risk/serve.py` · `PROXY_DRIFT_BASELINE` → #9 |
| **#5** `webhook-mesh` | — | — | ✅ Ingress WAL-before-ack | `src/webhook_mesh/` · `WEBHOOK_DISPATCH_MODE=redis` |
| **#8** `model-governor` | — | ✅ Core (lifecycle FSM) | — | `src/model_governor/` · `make demo-mg-gold` |
| **#9** `drift-gate` | ✅ Core (model/spend drift) | ✅ Core (ModelRiskFreeze analogue) | — | `src/drift_gate/` · `DRIFT_GATE_REQUIRE_REDIS` · `RollingStateStore` |
| **#11** `spend-guard` | ✅ Core (reserve/settle plane) | — | — | `src/spend_guard/` · `make demo-gold` |
| **#12** `agent-ledger` | — | — | ✅ Authorize-before-invoke | `src/agent_ledger/` · observation-lane export default on |

### Bundle definitions (this repo)

| Governor label | SKU recipe | Commercial story (no prices) | Runnable “platform” in tree? |
|----------------|------------|------------------------------|------------------------------|
| **Finance Governor** | #11 + #9 (+ #2 optional) | Reserve-before-dispatch for LLM/API spend + PSI/KS drift enforce + optional outbound proxy gate | **No** — three CLIs / optional HTTP serves |
| **Insurance Governor** | #8 + #9 + #1 | Model lifecycle proof + drift at deploy + regulated decision log | **No** — three CLIs |
| **Cyber Governor** | #2 + #1 + #5 (+ #12 optional) | Egress gate audit + compliance export + ingress WAL integrity (+ tool permit) | **No** — closest honest mapping; not a TCP mesh |
| **ModelGovernor (MG)** | #8 (+ #11 for spend plane, + #9 for deploy drift) | Lifecycle ledger (#8) **or** spend plane (#11 via `demo-gold`) | **Partial** — #8 CLI only; spend plane is SKU #11 |

### External platform names → this repo (do not conflate)

| External wedge / port | Claimed job | This repo equivalent |
|----------------------|-------------|----------------------|
| MG `:8080` governed dispatch | Reserve before LLM call | **#11 Spend Guard** gateway (`spend_guard/serve.py`) |
| FG AlgoFreeze `:8094` | Freeze before EMS | **#9 Drift Gate** enforce + **#2 Proxy-Risk** circuit (integration via env, not mesh) |
| FG WireMatch `:8093` | Pre-rail semantic gate | **Not implemented** — would be design-partner SOW |
| IG ClaimGate `:8103` | FNOL → governed payout | **Not implemented** |
| IG ReserveReconcile `:8113` | Reserve vs subledger drift | **#9 Drift Gate** + **#11 wallet** (different domain, same math class) |
| IG ModelRiskFreeze `:8111` | Model version freeze → block payout | **#8 deploy** + `MODEL_GOVERNOR_DRIFT_BASELINE` + **#9** |
| CG EgressGovern `:8123` | Envoy ext_authz | **#2 Proxy-Risk** live/shadow forward pattern |
| CG ComplianceLogger `:8128` | Regulatory evidence export | **#1 Compliance Logger** export + observation lane |
| CG IdentityGovern `:8124` | Session arm mesh | **#12 Agent Ledger** authorize (tool-level, not SSO) |

**Warranty mesh** (parent FROZEN blocks child commit) exists in external governor repos; **not** in this repo. Cross-SKU coupling here is **env-wired integration** (e.g. `PROXY_DRIFT_BASELINE`, `MODEL_GOVERNOR_DRIFT_BASELINE`), not a runtime crystal mesh.

---

## Shared spine — all governors and all 12 SKUs

Every ingredient SKU uses `inst_spine`:

| Primitive | Commercial meaning | Code |
|-----------|-------------------|------|
| Genesis + hash chain | Tamper-evident audit; offline `verify-bundle` | `inst_spine/hash.py`, `ledger.py` |
| Lamport clocks (F4) | Anti backdating per writer | `inst_spine/clocks.py` |
| F1–F9 gates | Institutional check before export | `inst_spine/check.py`, `gates/engine.py` |
| Deterministic export (F9) | Same ledger → same tarball SHA256 | `inst_spine/export.py` |
| Observation lane | Redact secrets/PHI/prompts; chain linkage verify | `verify_chain_linkage()` in `hash.py` |
| Production profile | Fail-closed `/ready` without Redis/Postgres/durable dispatch | `inst_spine/production_profile.py` |
| Bundle signing (optional) | Ed25519 detached `.sig.json` when `INST_BUNDLE_SIGNING_KEY` set | `inst_spine/bundle_sign.py` |

**Portfolio proof (this repo):**

```bash
make plug                    # install + demo-all 12/12 + offline verify
make proof                   # smoke + rigorous + verify-portfolio
make demo-gold               # Finance Governor spend-plane walkthrough (SKU #11)
make demo-mg-gold            # ModelGovernor lifecycle walkthrough (SKU #8)
./scripts/instpp_rigorous_test.sh
```

Expected rigorous summary: `"status": "PASSED"`, `"products": 12`, `"industry_gold": true`

---

## Forensic readiness — ingredient SKUs (governor-relevant)

Scores = **engineering / production-envelope readiness** in *this* tree, not external IL rubric. Scale 1–10.

| SKU | Inst Gold (9 dim) | Prod profile | Forensic | Prod 🟡 | → 10 requires |
|-----|-------------------|--------------|----------|---------|---------------|
| #1 Compliance | ✅ | Postgres optional | **9** | 🟡 mTLS partial | Signed export policy, SOC2 evidence automation |
| #2 Proxy-Risk | ✅ | Redis required multi | **9** | 🟡 Redis soak | Live auth metrics, rigorous Redis compose |
| #5 Webhook Mesh | ✅ | Redis stream prod | **9** | 🟡 dispatch default background | Stream chaos, mTLS ingress |
| #8 ModelGovernor | ✅ | CLI only | **9** | 🟡 no HTTP | Deploy drift in all gold demos; artifact signing |
| #9 Drift Gate | ✅ | Redis rolling prod | **10** | 🟡 golden PSI files | PSI/KS regression golden files |
| #11 Spend Guard | ✅ | Postgres wallet SOW | **9** | 🟡 SQLite default CI | Postgres in rigorous CI, compose honesty |
| #12 Agent Ledger | ✅ | Redis optional | **8** | 🟡 HTTP auth | mTLS on authorize, permit TTL prod metrics |

Full 12-SKU matrix: [FORENSIC_HARDENING_AUDIT.md](FORENSIC_HARDENING_AUDIT.md)

### Governor-level rollup (honest)

| Governor (bundle) | Effective forensic band | Limiting factor | Hardening focus (active) |
|-------------------|------------------------|-----------------|--------------------------|
| **FG** (#11+#9+#2) | **~8.5/10** | No unified compose; Postgres wallet not default CI; no WireMatch | Spend gateway + drift Redis + proxy integration |
| **IG** (#8+#9+#1) | **~8/10** | No ClaimGate; deploy drift opt-in; three separate CLIs | MG gold demo, deploy drift in rigorous, compliance export |
| **CG** (#2+#1+#5+#12) | **~8/10** | No Envoy ext_authz; no mesh; ingress auth gaps | Mesh ingress WAL, proxy egress, agent authorize HTTP |
| **MG** (#8, spend via #11) | **#8: 9** · **spend: 9** | Not a single platform binary | Lifecycle FSM + optional deploy drift; spend plane on #11 |

**Not claimable from this repo alone:** IL 9/10 per external governor, `deployment-forensic-review` 10/10 green, `gov-live-demo`, examiner packs, SERIALIZABLE asyncpg reserve stack — those belong to **`modelgovernor.v01`** hardening program (ADR 002/003), which is **also still in progress** (phase 4b: signing CronJob, chain repair, ingress auth, partitioning).

---

## 1. ModelGovernor (MG)

### Sales sheet

| Field | Value |
|-------|-------|
| **In this repo** | Inst++ SKU #8 — `model-governor` CLI |
| **Not in this repo** | MG platform (`:8080` gateway, sidecar `:8081`, reconciler `:8082`, Postgres SoT) |
| **Buyer** | ML platform, model risk, legal, procurement |
| **One line** | Tamper-evident **model lifecycle** ledger — register, approve, deploy, retire, drift_alert |
| **vs market** | MLflow = version history; GRC = workflow; MG CLI = **offline cryptographic proof** per event |

### What it does (shipped)

1. `record` — governance action + model snapshot + outcome on `AppendOnlyLedger`
2. Lifecycle FSM — illegal transitions fail closed (`model_governor/lifecycle.py`)
3. Optional deploy drift gate — when `MODEL_GOVERNOR_DRIFT_BASELINE` + `deploy_features` in snapshot (`model_governor/record.py`)
4. `check` — F1–F9 institutional gates
5. `export` / `verify-bundle` — deterministic tarball, offline auditor replay

**Spend plane is SKU #11**, not #8: `make demo-gold` exercises reserve → settle → drift lockout on Spend Guard. Docs historically labeled this “ModelGovernor 8b”; honest labeling: **Spend Guard with MG narrative**.

### Architecture (this repo)

```
model_snapshot.json + action + outcome
        │
        ▼
┌─────────────────────┐
│ model_governor.cli  │  record | check | export | verify-bundle
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ inst_spine ledger   │  genesis · hash chain · Lamport · F1–F9
└─────────────────────┘
           │
           optional deploy ──► drift_gate (SKU #9) shadow/enforce
```

| Component | Exists here? | Path / command |
|-----------|--------------|----------------|
| Lifecycle CLI | ✅ | `src/model_governor/` |
| HTTP gateway | ❌ | Use Spend Guard `#11` for OpenAI-compat |
| Postgres SoT | ❌ (SKU #8) | SQLite default; optional via `inst_spine` ledger factory |
| Drift at deploy | ✅ opt-in | `MODEL_GOVERNOR_DRIFT_BASELINE`, `MODEL_GOVERNOR_DRIFT_MODE` |

### Test execution pyramid (this repo)

| Tier | Command | Proves |
|------|---------|--------|
| L1 — unit | `pytest tests/test_model_governor.py` | FSM, record, export |
| L2 — portfolio | `make demo-mg-gold` | 7-step lifecycle + export + verify |
| L3 — rigorous E2E | `instpp_rigorous_test.sh` § ModelGovernor | record · check · export · deploy drift shadow |
| L4 — integration | `tests/test_sku_layer_hardening.py` | production profile, export redaction patterns |
| L5 — full portfolio | `make proof` | 12/12 + smoke |

**External platform tests (not runnable here):** `make mg-certification-l4-ci`, `compose-smoke-mg`, `mg-pilot-attestation`, `deployment-forensic-review`

### Deployment SKUs (honest)

| SKU label (external) | In this repo |
|---------------------|--------------|
| MG-PLATFORM-DEMO | `make demo-mg-gold` + `demo_model_governor.sh` |
| MG-PLATFORM-STAGING | Design-partner Kustomize — **external repo** |
| MG spend plane | `make demo-gold` on **Spend Guard** |

### Non-goals

- Full MRM platform, model registry UI, champion/challenger automation
- Hosted multi-tenant SaaS
- Single binary “MG platform” from this tree

---

## 2. Finance Governor (FG)

### Sales sheet

| Field | Value |
|-------|-------|
| **In this repo** | Bundle label: **#11 Spend Guard + #9 Drift Gate + (#2 Proxy-Risk optional)** |
| **Not in this repo** | FG spine `:8090`, WireMatch, AlgoFreeze, SubledgerSync, CCP mesh |
| **Buyer** | CFO, FinOps, treasurer, model risk (spend + drift) |
| **One line** | **No financial surprise without a logged gate** — reserve before dispatch, drift enforce, optional egress proxy |
| **vs market** | GRC paperwork vs runtime reserve/freeze at the API boundary |

### What it does (ingredient behavior)

| Ingredient | Job | Entry |
|------------|-----|-------|
| **#11 Spend Guard** | Wallet reserve → upstream dispatch → settle; drift wallet lockout | `spend-guard` CLI · `spend_guard/serve.py` OpenAI-compat gateway |
| **#9 Drift Gate** | PSI/KS vs baseline; shadow or enforce | `drift-gate` CLI · env on Proxy `#2` or MG deploy |
| **#2 Proxy-Risk** (optional) | Circuit · schema · rate · idempotency · forward | `proxy-risk-serve` |

**Mesh story (external):** “Desk FROZEN blocks wire commit” — **not implemented here**. Closest: drift enforce rejects + wallet lockout on separate ledgers.

### Architecture (this repo)

```
Client ──► Spend Guard :gateway ──► reserve (wallet SQLite/Postgres)
                │                        │
                ▼                        ▼
           upstream LLM/API         spend_guard ledger (inst_spine)
                │
Drift Gate ◄────┴── baseline file / Redis rolling window
Proxy-Risk ◄──── optional egress gate chain
```

### Test execution pyramid (this repo)

| Tier | Command | Proves |
|------|---------|--------|
| L1 | `pytest tests/test_spend_guard.py tests/test_drift_gate.py` | Wallet, PSI/KS |
| L2 | `make demo-gold` | 11-step spend walkthrough |
| L3 | `instpp_rigorous_test.sh` § Spend Guard + drift sections | HTTP gateway E2E, shadow deploy drift |
| L4 | `tests/test_industry_gold.py` | wallet idempotency, contention patterns |
| L5 | `make proof` | full portfolio |

**External only:** `fg-demo-gold`, `compose-smoke-fg`, `fg-certification-l4-ci`, Toxiproxy chaos

### Deployment SKUs (honest)

| Motion | This repo proof |
|--------|-----------------|
| FG spend pilot | `make demo-gold` + buyer VPC Helm for Spend Guard (buyer-operated) |
| FG + AlgoFreeze wedge | **Not in repo** — sell #9 + #2 integration SOW |
| FG + WireMatch | **Not in repo** — design-partner only |

### Non-goals

- Treasury wire rails, SWIFT semantic matching, EMS insert
- Crystal Commit Protocol mesh
- Single `:8090` binary

---

## 3. Insurance Governor (IG)

### Sales sheet

| Field | Value |
|-------|-------|
| **In this repo** | Bundle label: **#8 ModelGovernor + #9 Drift Gate + #1 Compliance Logger** |
| **Not in this repo** | IG spine `:8100`, ClaimGate, FNOL vendors, FedNow sandbox, warranty mesh |
| **Buyer** | Chief claims officer (aspirational), MGA platform, carrier innovation lab, **strategic acquirer of IP** |
| **One line** | Governed **model + decision evidence** — lifecycle proof, drift at deploy, regulated decision log |
| **vs market** | Guidewire = SoR workflow; Shift/FRISS = fraud scores; **this bundle** = cryptographic audit spine across three CLIs |

### What it does (ingredient behavior)

| Wedge analogue (external) | This repo ingredient | Status |
|---------------------------|---------------------|--------|
| ModelRiskFreeze | #8 deploy + #9 enforce | ✅ opt-in env |
| ReserveReconcile | #9 drift + #11 if extended | 🟡 math class only, not claims reserves |
| ClaimGate / FNOL | — | ❌ |
| Compliance attestation export | #1 `compliance-log` export + observation lane | ✅ |
| UnderwritingGovern | — | ❌ |

### Architecture (this repo)

```
FNOL / decision (buyer system)
        │
        ▼
#1 compliance-log ──► decision snapshot + outcome on chain
#8 model-governor ──► register → approve → deploy (optional drift)
#9 drift-gate     ──► baseline evaluate at deploy or batch
        │
        ▼
export + verify-bundle (each SKU) or portfolio manifest
```

### Test execution pyramid (this repo)

| Tier | Command | Proves |
|------|---------|--------|
| L1 | `pytest tests/test_compliance_cli.py tests/test_model_governor.py tests/test_drift_gate.py` | per-SKU |
| L2 | `make demo-mg-gold` + `demo_compliance_logger.sh` + `demo_drift_gate.sh` | bundle story in parts |
| L3 | `instpp_rigorous_test.sh` | MG + drift deploy shadow + compliance sections |
| L4 | `tests/test_compliance_serve.py` | HTTP ingest + `/ready` |
| L5 | `make proof` | 12/12 |

**External only:** `compose-smoke-ig`, `ig-certification-l4-ci`, `ig-pilot-attestation`, `ig-full-rehearsal`, FNOL WAL consumer

### Regulatory mapping (documentation only)

NAIC MAR, state DOI, FCA Consumer Duty, Solvency II, SR 11-7 **analogues** may be cited in buyer conversations — **no certification** in tree. See external `uk-us-regulatory-framework.md` **only if that file exists in the governor platform repo**, not assumed here.

### Non-goals

- PAS replacement (Guidewire, Snapsheet)
- Claims payment rail
- Carrier-grade FNOL adapter pack from this repo

---

## 4. Cybersecurity Governor (CG)

### Sales sheet

| Field | Value |
|-------|-------|
| **In this repo** | **No CG product.** Closest **bundle recipe**: #2 + #1 + #5 (+ #12) |
| **Not in this repo** | CG spine `:8120`, EgressGovern Envoy ext_authz, ThreatProxy, mesh rules |
| **Buyer** | CISO, SOC lead, zero-trust architects |
| **One line (honest)** | **Ingress integrity + egress gate audit + evidence export** — not SIEM, not XDR |
| **vs market** | SIEM correlates after; CG platform blocks commits via mesh — **that platform is not here** |

### What it does (closest ingredients)

| External CG wedge | Ingredient | Proof |
|-------------------|------------|-------|
| EgressGovern | #2 Proxy-Risk | Shadow/live evaluate, rate, idempotency, chain |
| ComplianceLogger | #1 Compliance Logger | Observation-lane export |
| Ingress durability | #5 Webhook Mesh | HMAC · WAL-before-200 · Redis dispatch |
| IR / tool gate | #12 Agent Ledger | Authorize-before-invoke |

### Architecture (this repo)

```
Internet ──► Webhook Mesh (#5) ──► WAL fsync ──► 200 OK
                │
App egress ──► Proxy-Risk (#2) ──► gate chain ──► upstream
                │
Agent tools ──► Agent Ledger (#12) ──► permit / deny
                │
Auditor ◄── Compliance Logger (#1) export tarball
```

### Test execution pyramid (this repo)

| Tier | Command | Proves |
|------|---------|--------|
| L1 | `pytest tests/test_proxy_risk*.py tests/test_webhook_mesh.py tests/test_agent_ledger.py` | |
| L2 | `demo_proxy_risk.sh` · `demo_webhook_mesh.sh` · `demo_agent_ledger.sh` | |
| L3 | `instpp_rigorous_test.sh` | mesh + proxy + agent sections |
| L4 | `tests/test_forensic*.py` | WAL, DLQ, idempotency tiers |
| L5 | `make proof` | |

**External only:** `cg-egress-wedge-demo`, `compose-smoke-cg`, `cg-certification-l4-ci`

### Non-goals

- SIEM replacement (Splunk, Sentinel)
- Endpoint XDR
- Envoy ext_authz sidecar pack from this tree
- Threat crystal mesh across platforms

---

## Monetization — motions only (no figures)

Commercial terms are negotiated in **external** SOWs, order forms, and data rooms. Below: **structure only**.

### Five revenue motions

| Motion | What buyer gets | Proof bundle (this repo) | Typical conversion |
|--------|-----------------|--------------------------|-------------------|
| **Design-partner pilot** | Named VPC install, 60–90 day eval, one vertical bundle | `make demo-gold` (FG) or `make demo-mg-gold` + rigorous log | Pilot → annual VPC license |
| **Annual VPC subscription** | Buyer-operated K8s/VM; unlimited internal users; updates | `make plug` + `verify-portfolio` + prod profile docs | Renewal + maintenance |
| **Perpetual VPC + maintenance** | Copyright / source grant + 12-month updates | Full git tree + `instpp_rigorous_latest.log` | Acquirer engineering |
| **OEM embed** | ISV embeds gate API (e.g. FNOL vendor, proxy vendor) | Stable CLI/HTTP contract + `verify-bundle` spec | Royalty or per-seat (contract only) |
| **Source-code asset sale** | Pre-revenue IP to technical acquirer | `make proof` + forensic docs + no customer reps | Acqui-hire / IP purchase |

### Monetization priority (this repo’s honest GTM)

| Priority | Lead with | Why |
|----------|-----------|-----|
| 1 | **FG recipe** via Spend Guard `#11` | Shortest proof (`make demo-gold`), clearest FinOps buyer |
| 2 | **#2 Proxy-Risk** + **#5 Webhook Mesh** | Standalone SKUs with HTTP serves, acute pain |
| 3 | **#12 Agent Ledger** | Agent-security narrative |
| 4 | **IG recipe** | Richest story **if** buyer accepts three CLIs, not ClaimGate |
| 5 | **CG recipe** | Only after egress/ingress ingredients positioned honestly — not as “CG platform” |

**Do not lead with:** “Four governor platform vendor-of-record” from **this repo alone**.

### Deal examples (structure only — no amounts)

| Example | Buyer type | Deliverable | Proof |
|---------|------------|-------------|-------|
| **A — FG pilot** | Fintech running LLM APIs in production | Spend Guard gateway in buyer VPC + drift baseline | `make demo-gold`, rigorous Spend Guard HTTP section |
| **B — IG acquirer** | InsurTech or PE roll-up engineering | SKU #8+#9+#1 source + docs | `make demo-mg-gold`, compliance export, drift evaluate |
| **C — CG OEM** | Security/proxy vendor | Proxy + mesh HTTP contracts white-labeled | Proxy rigorous + webhook mesh chaos tests |
| **D — FG AlgoFreeze analogue** | Quant desk | Drift enforce + proxy freeze integration | `#9` + `#2` env wiring SOW |
| **E — Full portfolio** | RegTech holding co | All 12 SKUs + `inst_spine` | `make proof`, `FORENSIC_HARDENING_AUDIT.md` |

### Public-sector / government buyers (secondary)

| Buyer type | Best bundle | Hook | Blocker |
|------------|-------------|------|---------|
| Treasury / payments bureau | FG (aspirational WireMatch) | Pre-commit audit chain | No wire rail; no FedRAMP pack in tree |
| State insurance DOI | IG recipe | Model + decision evidence export | Not PAS; carrier must operate |
| Federal AI platform shop | MG `#8` + `#11` | NIST AI RMF **documentation** angle | No FedRAMP; buyer operates VPC |
| Cyber program | CG recipe | Ingress WAL + egress gate proof | Not SIEM; no STIG/FIPS bundle shipped |

---

## Industry hardening — where work lives

Principal-engineer waves (asyncpg SERIALIZABLE, Lua Redis CAS, Ed25519 bundle sign, mmap WAL `.wrcap`, phase 3–4 closure) are tracked in **`modelgovernor.v01`** ADR 002/003 — **not merged into this repo’s spine**.

| Capability | This repo (`inst_spine`) | External governor platform |
|------------|--------------------------|----------------------------|
| SQLite ledger + optional Postgres DSN | ✅ | Postgres SoT |
| SERIALIZABLE asyncpg reserve | ❌ | ✅ (MG ledger_asyncpg) |
| Lua atomic guardrails | ❌ | ✅ (mg/fg/ig/cg prefixes) |
| Ed25519 mandatory examiner sign | 🟡 optional `INST_BUNDLE_SIGNING_KEY` | ✅ phase 4a |
| Webhook WAL `.wrcap` | ✅ SKU #10 + #5 ingress | ✅ IG FNOL WAL (external) |
| `verify_chain_linkage` for observation lane | ✅ | parallel pattern |
| `INST_PRODUCTION_PROFILE` fail-closed `/ready` | ✅ | compose probes (external) |

**Portfolio score (this repo, post SKU hardening):** architecture ~8 · code ~7.5 · execution ~7 · audit ~7 · **overall ~7.5/10** — honest ceiling until Postgres in rigorous CI, mandatory signing, and ingress mTLS land universally. **Scores rise as hardening lands; they are not marketing certifications.**

### Active hardening backlog (governor-relevant)

| Priority | Item | Track | Governor impact |
|----------|------|-------|-----------------|
| P0 | Postgres wallet in rigorous CI | A | FG credibility |
| P0 | Redis stream dispatch default in portfolio demo | A | CG / FG ingress story |
| P1 | Signed export policy + mandatory Ed25519 on examiner paths | A + B | IG / CG diligence |
| P1 | Deploy drift in all MG gold paths (`deploy_features`) | A | IG ModelRiskFreeze analogue |
| P1 | Chain finalize repair + signing CronJob | B | MG/FG/IG/CG platform |
| P2 | Webhook ingress mTLS/HMAC | A + B | CG |
| P2 | Mesh / ClaimGate / WireMatch wedges | B | IG / FG platform |
| P2 | Per-account chain partitioning | B | All platforms at scale |

Update this table when waves close — do not remove the section when items complete; move rows to “Recently landed” with commit/PR reference.

---

## One-command diligence packs

### This repository

```bash
# Full Inst++ portfolio (12 SKUs)
make proof

# Finance Governor story
make demo-gold && pytest tests/test_spend_guard.py tests/test_drift_gate.py -q

# Insurance Governor story (in parts)
make demo-mg-gold && ./scripts/demo_compliance_logger.sh && ./scripts/demo_drift_gate.sh

# Cyber Governor story (in parts)
./scripts/demo_webhook_mesh.sh && ./scripts/demo_proxy_risk.sh && ./scripts/demo_agent_ledger.sh

# Forensic + production profile
pytest tests/test_forensic*.py tests/test_production_profile.py tests/test_sku_layer_hardening.py -q
```

### External governor platform (not runnable from this tree)

```bash
# Documented in modelgovernor.v01 — require that workspace
make deployment-forensic-review
make gov-live-demo
make plug
```

---

## Related documents

| Doc | Purpose |
|-----|---------|
| [PORTFOLIO_FULL_TECH_SALES_12.md](PORTFOLIO_FULL_TECH_SALES_12.md) | 12 SKU index (contains legacy prices — prefer this doc for governor context) |
| [FORENSIC_ARCHITECTURE_TRUTH.md](FORENSIC_ARCHITECTURE_TRUTH.md) | Sports vs Inst++ vs fabricated names |
| [FORENSIC_HARDENING_AUDIT.md](FORENSIC_HARDENING_AUDIT.md) | Per-SKU forensic grades |
| [INST_PLUS_GOLD_STANDARD.md](INST_PLUS_GOLD_STANDARD.md) | Nine Industry Gold dimensions |
| [PRODUCTION_REDIS_PROFILE.md](PRODUCTION_REDIS_PROFILE.md) | Multi-instance Redis |
| [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) | Postgres HA design-partner path |
| [compliance/README.md](compliance/README.md) | What is not in this repo |
| [ROADMAP_GTM_DISCIPLINE.md](ROADMAP_GTM_DISCIPLINE.md) | Explicit non-SKUs |

---

## Acquirer FAQ (one paragraph each)

**Q: Are FinanceGovernor, Insurance Governor, and CyberGovernor real products?**  
A: In this repo they are **bundle licenses** over Inst++ SKUs. Runnable governor platforms with dedicated spines are a **separate codebase**.

**Q: Is ModelGovernor the `:8080` gateway?**  
A: **No** in this repo. SKU #8 is a lifecycle CLI. The gateway spend plane is **Spend Guard (#11)**. External MG platform is different.

**Q: Do you have ClaimGate or AlgoFreeze?**  
A: **No.** Claiming them from this tree is misrepresentation (`stack_truth.FABRICATED_PRODUCT_NAMES`).

**Q: SOC 2 / HIPAA?**  
A: Templates only. Buyer-operated VPC scope.

**Q: What is the defensible IP?**  
A: `inst_spine` cryptographic audit kernel + 12 SKU gate patterns + offline `verify-bundle` + rigorous CI logs — not four Postgres governor databases in this git tree.

**Q: Are governors “done”?**  
A: **No.** Governors are **actively being hardened** on two tracks: Inst++ SKU/bundle ingredients in this repo, and four platform spines in `modelgovernor.v01`. Forensic bands in this doc are engineering estimates, not final attestations. Design-partner and pilot motions are the appropriate GTM while hardening continues.

---

*No license fees, royalties, deal sizes, valuations, or buyer spend thresholds appear in this document. Incident-class references (e.g. Knight-class operational risk) may be used in external decks; headline loss amounts do not belong in repo docs.*
