# Inst++ Portfolio Strategy — HIBS vs New Products

**Purpose:** Laser-focused direction after HIBS harvest — what to sell, what's worth building, and how UK governance maps to Inst++.

---

## Executive verdict

You have **two distinct portfolios** — do not conflate them in pitch or pricing:

| Portfolio | Buyer | Value driver | Realistic exit (code only) | Realistic exit (with traction) |
|-----------|-------|--------------|---------------------------|-------------------------------|
| **HIBS** (football + racing + trading) | Quant syndicates, acquirers | Proven alpha + audit trail | £40k–£70k bundle | £250k–£500k+ **only with ARR** |
| **Inst++** (7 spine products) | B2B infra buyers | Cost-to-replicate + compliance | £60k–£90k ecosystem | £250k–£350k at min promotion |

**Critical valuation truth:** Acquire/Flippa buy **cash flow**, not algorithms. £450k–£700k HIBS targets require ~£100k+ clean annual profit (3.5–4x SDE), not 60 days of clean logs alone.

**60-day family runway goal:** Reframe as **commercialisation runway** (first £2k–£7.5k MRR), not "code appreciation to £450k."

---

## HIBS — keep, harvest, don't over-build

### What you have (proven engineering)

- Football: Dixon–Coles + LightGBM, F1–F9 evidence gates, `prediction_audit.sqlite`
- Racing: Inst++ layer live (WAL, genesis, gates) — 26 tests passing
- Trading Core: staged pipeline Shadow → Paper → Micro → Live

### Monetisation paths (ranked by fit to your skills)

| Path | Model | ARR to hit £300k valuation | Your edge |
|------|-------|------------------------------|-----------|
| **A. B2B JSON data feed** | 5 × £1,500/mo | £90k ARR | Already have HTTP JSON + data room exports |
| **B. Private signal community** | 100 × £99/mo | ~£118k ARR | Place-finder hit rates market well |
| **C. Trading Core boilerplate** | N/A — overlaps Inst++ Proxy-Risk | — | **Don't duplicate** — sell spine not alpha |

### Success probability (honest)

| Outcome | Rough probability |
|---------|-------------------|
| Technical soak (no crashes, clean logs) | **~90%** |
| Model alpha (edge after commission/slippage) | **~40–50%** |
| Commercial monetisation (paying strangers) | **~10–15%** |

**Tilt odds:** Public verification dashboard + pre-sell beta data access **now**, not day 60.

---

## Inst++ — product portfolio (laser-focused)

Built on `src/inst_spine/` — **zero sports imports**. Sell **individually**, not as one bundle.

### Core four (in build order)

| # | Product | One job | Code status | Next to 95% |
|---|---------|---------|-------------|-------------|
| 1 | **Compliance Logger** | Tamper-proof decision audit | P2 export done | Auditor dry-run + offsite genesis |
| 2 | **Proxy-Risk Gateway** | Outbound circuit breaker | P1 shadow | Upstream forward + p99 bench |
| 3 | **Alt-Data Extractor** | One feed, ≥95% coverage | P1 demo | One real non-sports target |
| 4 | **AI Kit** | Rate limits + checkpoints | P1 demo | Pydantic retry E2E |

### Spine extensions (products 5–7) — difficulty assessment

All three are **thin product layers** on existing `inst_spine/` — no core file changes required. Each is a new package (`webhook_mesh/`, `ad_guard/`, `health_telemetry/`) importing spine only.

| # | Product | Difficulty | Spine reuse | New work | Sales velocity |
|---|---------|------------|-------------|----------|----------------|
| **5** | **Webhook Idempotency Mesh** | **Easy** | ~75% | Delivery FSM, provider sigs | **High** |
| **6** | **Ad-Tech Budget Guardrail** | **Easy–Medium** | ~85% | Spend metric extraction | Medium |
| **7** | **Health Telemetry Recorder** | **Medium (tech) / Hard (GTM)** | ~90% | HIPAA/DTAC packaging | Slow, high ticket |

**Difficulty key:** Easy = fork `proxy_risk` + config; Medium = new domain logic + compliance docs; Hard = regulatory sales cycle, not Python.

---

## Product 5: Webhook Reliability & Delivery Engine

**One job:** Ingest provider webhooks → WAL ack → dedupe → async forward → never double-process.

### Why this is the easiest add

`proxy_risk` is already 75% of this product — inverted direction (inbound HTTP vs outbound broker).

| Capability | Already in repo | Webhook-specific gap |
|------------|-----------------|----------------------|
| Async uvloop listener | `proxy_risk/serve` | Stripe/Shopify route mounts |
| WAL before ack | `inst_spine/wal.py` | Log **raw bytes** + `payload_hash` |
| Idempotency | `IdempotencyGuard` (memory) | **Redis SETNX** backend (same pattern as token bucket) |
| Token bucket burst | `rates.py` | Per-tenant ingress rate |
| Cold-path ledger | `AppendOnlyLedger` | Delivery state: `received → forwarded → acked` |
| Export bundle | `export.py` | `export_webhook_audit.sh` (rename + labels) |

### Architecture

```
[Stripe/Shopify] → POST /hooks/{tenant}
                         │
                   HOT PATH (<10ms)
                         ├─ verify provider signature (HMAC)
                         ├─ payload_hash = SHA256(raw_body)
                         ├─ Redis idempotency SETNX(payload_hash) → duplicate? return 200 (no re-forward)
                         ├─ WAL append raw bytes (SYNC fsync)
                         └─ HTTP 200 OK to provider
                         │
                   COLD PATH (async worker)
                         ├─ forward to customer URL
                         ├─ retry with backoff (3x)
                         └─ dead-letter + ledger event
```

### Effort estimate (technical)

| Component | Invasiveness | Notes |
|-----------|--------------|-------|
| `webhook_mesh/ingress.py` | New ~400 LOC | Fork `proxy_risk/router.py` |
| `webhook_mesh/delivery.py` | New ~300 LOC | Retry queue + DLQ |
| `RedisIdempotencyBackend` | New ~80 LOC | Copy `RedisTokenBucketBackend` pattern |
| Stripe sig verify | New ~60 LOC | Well-documented HMAC |
| Tests | New ~200 LOC | Duplicate delivery, crash-before-forward |
| **Core `inst_spine/` changes** | **Zero** | |

**Verdict: Easy** — build immediately after Proxy-Risk P2. Highest ARPU velocity of the three.

**Price:** £199–£599/mo per tenant.

**Do NOT build:** Multi-tenant SaaS UI, webhook transformation DSL, or queue replay dashboard before first paying tenant.

---

## Product 6: Ad-Tech Budget Guardrail Kernel

**One job:** Air-gapped **outbound** proxy on marketing API calls — kill when spend velocity is statistically anomalous.

### Why this is almost free after Proxy-Risk

Product 6 **is** Proxy-Risk with different config:

| Proxy-Risk | Ad Guardrail |
|------------|--------------|
| Inbound/outbound broker API | Outbound Google/Meta/TTD API |
| Z-score on `reference_price` | Z-score on `bid_amount` or `spend_delta` |
| Token bucket per `client_id` | Token bucket per `campaign_id` |
| `export_audit.sh` | `export_ad_audit.sh` (same code, different manifest label) |

### Architecture

```
[Marketing script] → ad_guard proxy → [Google Ads API]
                           │
                     Z-score on spend/sec per campaign
                     |Z| > 3 → circuit.kill("spend anomaly")
                     WAL log every outbound request
```

### Effort estimate

| Component | Invasiveness | Notes |
|-----------|--------------|-------|
| `ad_guard/proxy.py` | New ~250 LOC | **Subclass or config flag on ProxyRiskGateway** |
| `ZScoreConfig` per campaign | Exists | `rates.py` already has `ZScoreConfig` |
| Spend metric parser | New ~150 LOC | JSON path extract for bid/campaign |
| **True RTB exchange (<5ms)** | **Not in scope** | Would need Go/Rust — say no |
| **Core changes** | **Zero** | |

**Verdict: Easy–Medium** — trivial if positioned as **marketing API proxy** (Meta/Google). Medium only if buyer expects sub-5ms RTB exchange insertion.

**Price:** £300–£800/mo per instance.

**Do NOT build:** Bid strategy, creative optimization, or reporting UI.

---

## Product 7: Healthcare Device Telemetry Recorder

**One job:** Ingest high-frequency sensor packets → Lamport-ordered sealed log → auditor export bundle.

### Why tech is easy but sale is hard

| Capability | Spine match |
|------------|-------------|
| Clock drift on devices | **Solved** — Lamport seq, wall time metadata only |
| Tamper-proof chain | **Done** — genesis + WAL + `export.py` |
| High-volume ingest | **Partial** — need batching, not new math |
| HIPAA / DTAC / Caldicott | **Not in code** — legal, BAA, encryption docs, PHI handling |

### Architecture

```
[Device / gateway] → POST /telemetry/batch
                           │
                     async ingest (uvloop)
                     WAL fsync per batch (not per packet if volume extreme)
                     lamport_seq per batch row
                     compliance_log.ingest(snapshot, outcome, actor)
```

### Effort estimate

| Component | Invasiveness | Notes |
|-----------|--------------|-------|
| `health_telemetry/ingest.py` | New ~300 LOC | Batch endpoint + schema validation |
| Batching strategy | New ~100 LOC | Aggregate 100 packets → one chain entry |
| `export_health_audit.sh` | Trivial | Wrapper on `export.py` |
| HIPAA compliance pack | **Docs only** | BAA template, encryption at rest statement, access log policy |
| FDA / DTAC certification | **Out of scope** | Years + consultants — sell **audit spine** not certification |
| **Core changes** | **Zero** | |

**Verdict: Medium (engineering) / Hard (commercial)** — code is a weekend fork of Compliance Logger; revenue requires enterprise compliance sales (6–12 month cycles).

**Price:** £5k–£15k license + £500/mo maintenance.

**Do NOT build:** EMR integration, HL7 FHIR full stack, or diagnostic claims before first hospital pilot.

---

## Reuse matrix (all 7 products)

| `inst_spine` module | P1 Proxy | P2 Alt | P3 Compliance | P4 AI | **P5 Webhook** | **P6 Ad** | **P7 Health** |
|---------------------|----------|--------|---------------|-------|----------------|-----------|---------------|
| `wal.py` | ● | ● | ● | ○ | **●** | **●** | **●** |
| `hash.py` + genesis | ○ | ○ | ● | ○ | ○ | ○ | **●** |
| `rates.py` token bucket | ● | ● | ○ | ● | **●** | **●** | ○ |
| `rates.py` Z-score | ● | ○ | ○ | ○ | ○ | **●** | ○ |
| `clocks.py` Lamport | ○ | ○ | ● | ● | ○ | ○ | **●** |
| `gates/circuit.py` KILL | ● | ○ | ○ | ○ | ○ | **●** | ○ |
| `export.py` | ○ | ○ | ● | ○ | **●** | **●** | **●** |

● = required · ○ = optional

---

## Amended build order (do not parallelize)

```
DONE   inst_spine v3 (WAL, genesis, Redis buckets, export P2)
NEXT   Compliance auditor dry-run (close P2)
       Proxy-Risk P2 (upstream forward)

EASY WINS (pick one):
  5a. Webhook Mesh P0–P1  ← recommended (fastest to £199/mo)
  6a. Ad Guard P0         ← if you have agency contact (fork Proxy-Risk)

LATER:
  3. Alt-Data one feed
  4. AI Kit P2
  7. Health Telemetry     ← only with enterprise buyer lined up
```

**Rule:** Products 5 and 6 should **not** start until Proxy-Risk P2 proves upstream forwarding. They are forks, not parallel greenfield.

---

## Honest "how hard?" summary

| Question | Answer |
|----------|--------|
| Do these need `inst_spine` changes? | **No** — thin product packages only |
| Which is fastest to revenue? | **#5 Webhook Mesh** (mass market, dev buyers, Stripe docs) |
| Which is least effort? | **#6 Ad Guard** — literally Proxy-Risk config swap |
| Which is highest ticket? | **#7 Health** — but sales cycle kills velocity |
| Can one developer build all three? | Yes, sequentially — **do not build all three at once** |
| Combined code-only value if all proven? | +£25k–£40k on top of core four (£85k–£110k total ecosystem IP) |

---

## Package layout (products 5–7)

```
src/
├── inst_spine/          # unchanged core
├── webhook_mesh/        # P5 — inbound idempotency proxy
│   ├── ingress.py
│   ├── delivery.py
│   └── cli.py
├── ad_guard/            # P6 — outbound spend guard (fork proxy_risk)
│   ├── proxy.py
│   └── cli.py
└── health_telemetry/    # P7 — batch ingest + export wrapper
    ├── ingest.py
    └── cli.py
```

**Zero sports imports. Zero changes to `inst_spine/` core files.**

---

## UK Code for Sports Governance — Inst++ mapping

Funded NGBs (Tier 1–3) need what Inst++ already builds — **not betting tips**:

| Code principle | Inst++ product | Evidence |
|----------------|----------------|----------|
| **Standards & Conduct** | Compliance Logger | F1–F9 gates + genesis chain |
| **Policies & Processes** | Compliance Logger | `export_audit.sh` auditor bundle |
| **Communication / Transparency** | Compliance + public verify page | Deterministic tar + SHA256 sidecar |
| **Financial discipline / risk** | Proxy-Risk Gateway | Token bucket + Z-score kill |

**Laser focus for UK sport:** Don't sell "betting platform" to NGBs. Sell **governance-grade audit infrastructure** — the same spine Compliance Logger ships to fintech.

Tier 3 NGBs (£1m+ funding) need DIAP + welfare board roles → your product is **audit trail + risk kill-switch**, not racecards.

---

## Compliance P2 — export pipeline (implemented)

```
[WAL] + [Genesis anchor] + [SQLite index]
         │
         ▼
  validate_before_export()
    ├─ genesis anchor == Block 0
    ├─ verify_chain() — abort exit 1 on fail
    └─ verify_lamport_monotonic()
         │
         ▼
  canonical JSON files (sorted keys)
         │
         ▼
  deterministic_tarball() — uid/gid/mtime=0, sorted paths
         │
         ▼
  audit_bundle.tar + .sha256 sidecar
```

**Commands:**

```bash
compliance-log export --database data/compliance_ledger.sqlite
compliance-log export --repro-check   # F9 gate
./scripts/export_audit.sh data/inst_ledger.sqlite ./audit_bundle ./audit_bundle.tar
python3 -m inst_spine.export_cli data/ledger.sqlite --repro-check
```

**Promotion:** External auditor replays bundle without vendor call; `repro-check` passes.

---

## What NOT to do

1. **Don't** pitch HIBS £450k on logs alone — pitch ARR or IP floor £40k–£70k
2. **Don't** sell Inst++ as one mega-portfolio — four buyers, four listings
3. **Don't** build Alt-Data feed #2 before feed #1 hits ≥95% coverage 30 days
4. **Don't** duplicate Trading Core as product #5 — it's Proxy-Risk
5. **Don't** parallelize products — one to P2 before starting next

---

## Recommended next 30 days

| Week | HIBS | Inst++ |
|------|------|--------|
| 1–2 | Public paper-trade verifier page | Compliance P2 auditor dry-run |
| 2–3 | Outreach: 3 syndicates for beta JSON feed | Proxy-Risk upstream forward |
| 3–4 | First paid beta (£500 flat) OR honest IP floor decision | Alt-Data: pick **one** target URL |

**North star:** £2k MRR anywhere (HIBS data **or** Inst++ compliance license) beats another month of unmonetised perfection.

---

## Related docs

- `docs/NEW_PRODUCT_INST_PLUS_ROADMAPS.md` — technical roadmaps v3
- `docs/PORTFOLIO_DEEP_DIVE.md` — racing gate lanes
- `src/inst_spine/export.py` — P2 bundle implementation
