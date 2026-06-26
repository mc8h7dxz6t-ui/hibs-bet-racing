# Roadmap & GTM Discipline — What We Do **Not** SKU

**Purpose:** Stop scope creep. These items have value but **wrong packaging** as standalone products. Use the action column — not “build anyway.”

| Item | Portfolio fit | Verdict | Action |
|------|---------------|---------|--------|
| **PII egress vault** | ~15% overlap with Proxy + compliance story | **Do not SKU** | High audit burden; crowded (**Skyflow**, **VGS**, **Privy**). Build **only** with a **named buyer LOI** + SOW. Otherwise: document as Proxy-Risk egress hook in diligence FAQ only. |
| **Tenant migrate** | ~15% — enterprise services | **Do not SKU** | Clear enterprise pain; **no product code** today. Sell as **design-partner SOW** (£8k–£25k) + license once you have cash. Not a GTM motion pre-revenue. |
| **Telemetry sequence gate** | ~25% — extends #7 Health Telemetry | **✅ Shipped in #7** | Monotonic `seq` + gap detection + WAL ingress live in `health_telemetry` — **not SKU #13**. Multi-device VectorClock remains roadmap-only unless named buyer LOI. |
| **Postgres `make demo-gold` compose** | ~10% in repo | **North star only** | Strategic demo for design partners. **Honest shipped path:** `make demo-gold` (Spend Guard CLI) + `make spend-gateway` (OpenAI-compat). Do not claim Postgres HA wallet in rigorous CI. |
| **mesh-limiter standalone** | ~90% already in Proxy-Risk | **Feature, not SKU** | Rate bucket + Z-score + idempotency = Proxy-Risk. Sell as **Proxy-Risk Enterprise tier** (£900–£1,200/mo). Never separate price list. |
| **local-vault seats** | ~20% — commodity | **Internal lib only** | Credential vault lives in `inst_spine` / Proxy-Ad-Guard paths. No seat-based SKU; no sales sheet line. |

---

## Decision tree (before building anything new)

```
New idea
   │
   ├─ Extends existing SKU >25%?  → Ship as feature / tier on that SKU
   │
   ├─ Crowded SaaS category + no LOI?  → Stop
   │
   ├─ Services-only (migrate, integrate)?  → SOW after first £50k ARR
   │
   └─ New spine SKU + rigorous E2E + buyer doc?  → Only if Agent Ledger–class wedge
```

---

## What we **do** sell (12 SKUs)

See [PORTFOLIO_FULL_TECH_SALES_12.md](PORTFOLIO_FULL_TECH_SALES_12.md) — full tech spec, comps, monthly income, exit table.

**GTM focus order (cash tomorrow):** Proxy-Risk · Webhook Mesh · Spend Guard · Agent Ledger · Compliance Logger — not vault/migrate/sequence standalone.
