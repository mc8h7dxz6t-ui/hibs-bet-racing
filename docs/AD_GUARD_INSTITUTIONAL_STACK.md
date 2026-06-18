# Ad Guard — Institutional Enterprise Stack Positioning

**Product #6:** Outbound marketing API spend guard + cryptographic audit trail.  
**One job:** Kill statistically anomalous spend velocity before dollars leave the agency account — with tamper-evident evidence.

---

## Where Inst++ fits (and where it does not)

Enterprise ad guardrails split into **two pillars**. Inst++ Ad Guard occupies a **third, narrower slot** that neither pillar fully covers:

| Pillar | Enterprise incumbents | Latency | Inst++ overlap |
|--------|----------------------|---------|----------------|
| **Pre-bid programmatic verification** | DoubleVerify, IAS, Oracle Moat | Sub-millisecond (DSP-integrated) | **None** — not an RTB exchange insert |
| **GenAI creative / agent safety** | NeMo Guardrails, Llama Guard, Guardrails AI, Bedrock Guardrails | Real-time inference (~10–100ms) | **None** — not an LLM firewall |
| **Outbound API spend control + audit** | Fragmented (scripts, DSP caps, finance alerts) | API proxy (~1–10ms) | **Full fit** |

**Honest pitch:** Inst++ Ad Guard is the **Compliance & Spend Control firewall** in the nested stack — not a DoubleVerify replacement, not a NeMo replacement.

---

## Institutional nested firewall architecture

```
[ GenAI Marketing Input ]
              │
              ▼
 ┌─────────────────────────┐
 │   LLM SAFETY FIREWALL   │  NeMo / Llama Guard / Bedrock Guardrails
 │   (NOT Inst++ Ad Guard) │  Blocks prompt injection & brand violations
 └────────────┬────────────┘
              │ (Approved Copy/Asset)
              ▼
 ┌─────────────────────────┐
 │   COMPLIANCE & SPEND    │  ◄── Inst++ Ad Guard (#6)
 │   CONTROL LAYER         │      Z-score spend drift, per-campaign bucket
 └────────────┬────────────┘      WAL + genesis audit export
              │ (Locked Assets)
              ▼
 ┌─────────────────────────┐
 │     ENTERPRISE DSP      │  Integrates DoubleVerify / IAS pre-bid
 └────────────┬────────────┘
              │ (Sub-millisecond placement auction)
              ▼
     [ Verified Safe Ad ]
```

**Deployment pattern:** Air-gapped proxy between marketing automation scripts and Google Ads / Meta Marketing API. All outbound mutations pass through `ad_guard` before reaching the network.

---

## Institutional-grade capability matrix

| Capability | Mid-market tools | DV / IAS (pre-bid) | NeMo / Bedrock (GenAI) | **Inst++ Ad Guard** |
|------------|------------------|--------------------|-------------------------|---------------------|
| **Latency** | Async / minutes | Sub-ms pre-bid | ~10–100ms inference | **<10ms** API proxy (memory gates) |
| **SLA posture** | 99% web hosting | 99.999% + penalties | Cloud-managed | **VPC / on-prem** — buyer-operated |
| **Data privacy** | Shared cloud | Enterprise contracts | Vendor cloud | **Zero-retention proxy** — WAL local only |
| **Compliance proof** | CSV dashboards | SOC 2 + contractual metrics | Model cards | **Genesis chain + deterministic export** |
| **Customisation** | Keyword blocklists | Custom brand suitability NLP | Programmable rails | **Per-campaign Z-score + token bucket** |
| **Spend velocity kill** | Finance alerts (lagging) | Pre-bid placement block | N/A | **Real-time circuit KILL** |

---

## Pre-bid incumbents (reference — do not compete)

### DoubleVerify Enterprise
- Custom brand suitability profiles, real-time pre-bid filtering, fraud protection
- **DV Authentic Ad** as contractual baseline for enterprise media buys
- Inst++ role: **audit spine** for spend decisions DV does not see (API-layer mutations)

### Integral Ad Science (IAS) Total Media Quality
- Frame-by-frame video, context-level sentiment, safety tiers across open web + social
- Inst++ role: **complement** — IAS blocks bad placements; Ad Guard blocks runaway API spend

### Oracle Moat (legacy enterprise)
- Viewability, attention, IVT at massive scale
- Inst++ role: none at RTB layer

---

## GenAI guardrail incumbents (reference — do not compete)

| Platform | Role | Inst++ boundary |
|----------|------|-----------------|
| **NVIDIA NeMo Guardrails** | Programmable LLM conversational rails | Ad Guard runs **after** creative is approved |
| **Llama Guard (Meta)** | Input/output safety classifier | Creative safety ≠ spend safety |
| **Guardrails AI Hub** | Typed validators on commercial LLMs | Schema/tone ≠ bid velocity |
| **Amazon Bedrock Guardrails** | Managed cross-model PII + keyword filters | PII block ≠ campaign spend anomaly |

**Integration point:** Ad Guard accepts only requests tagged with an upstream approval manifest (future: `X-Creative-Approval-Id` header gate).

---

## Inst++ Ad Guard — technical architecture

```
[Marketing script / agent] → POST /v1/guard/{client_id}
                                    │
                              HOT PATH (<10ms)
                                    ├─ circuit breaker (KILL latch)
                                    ├─ schema validation
                                    ├─ extract campaign_id + bid/spend (spend.py)
                                    ├─ token bucket per campaign_id (Redis Lua)
                                    ├─ Z-score on spend_delta | bid_amount
                                    └─ APPROVE | REJECT | KILL
                                    │
                              COLD PATH (async)
                                    ├─ WAL fsync via AppendOnlyLedger
                                    ├─ genesis-anchored hash chain
                                    └─ export_ad_audit.sh (deterministic bundle)
```

### Provider parsers (`ad_guard/spend.py`)

| Provider | campaign_id source | spend signal |
|----------|-------------------|--------------|
| `google` | `campaignId`, resource `campaigns/{id}` | `bidMicros`, `costMicros` |
| `meta` | `campaign_id` | `daily_budget`, `spend` |
| `generic` | `campaign_id` body field | `bid_amount`, `spend_delta` |

### Gate chain (`ad_guard/proxy.py`)

Same spine as Proxy-Risk — forked config:

| Proxy-Risk | Ad Guard |
|------------|----------|
| `reference_price` | `bid_amount` / `spend_delta` |
| Token bucket per `client_id` | Token bucket per `campaign_id` |
| `proxy_request` ledger event | `ad_spend_request` ledger event |

---

## What makes it "institutional-grade" for Inst++

1. **Fail-closed circuit** — `|Z| > z_max` → `circuit.kill()` latches until operator reset
2. **Cryptographic audit** — every decision in genesis-anchored chain; `compliance-log export --repro-check`
3. **Air-gapped deploy** — no vendor cloud dependency; runs in agency VPC
4. **Deterministic export** — auditor replays bundle without vendor call
5. **Explicit non-goals** — no RTB, no LLM inference, no creative optimisation

---

## Pricing & buyer

| Segment | Price | Buyer |
|---------|-------|-------|
| Agency / holding company | £300–£800/mo per instance | Head of programmatic, finance ops |
| Enterprise marketing ops | £5k–£15k license + maintenance | Procurement + legal (audit requirement) |

**Do NOT build before buyer:** Bid strategy, creative scoring, reporting UI, DSP UI, RTB exchange adapter.

---

## Build status

| Component | Status |
|-----------|--------|
| `ad_guard/spend.py` | **Done** |
| `ad_guard/proxy.py` | **Done** |
| `ad_guard/serve.py` | **Done** |
| `ad_guard/cli.py` | **Done** — `evaluate`, `serve`, `export` |
| `export_ad_audit.sh` | **Done** |
| Creative approval header gate | P2 |

---

## Related

- `docs/INST_PLUS_STRATEGY.md` — portfolio strategy
- `src/proxy_risk/` — fork base
- `src/inst_spine/rates.py` — token bucket + Z-score math
