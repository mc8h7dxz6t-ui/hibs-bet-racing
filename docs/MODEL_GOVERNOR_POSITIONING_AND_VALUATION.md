# ModelGovernor — Strategic Positioning, Comps & Valuation

**Purpose:** Honest buyer/investor framing for ModelGovernor — what ships today vs the strategic north star, how comps overlap, and how valuation should be read.  
**Not:** Financial, tax, or legal advice. For a real exit, use a UK corporate finance adviser and tax accountant.  
**Date:** June 2026

---

## One sentence (investors / buyers)

**LiteLLM and Portkey govern traffic; ModelGovernor governs money** — reserve-before-dispatch, ledger settlement, and audit surfaces that proxies and observability tools were not built to own.

*That line is the product thesis. Runnable proof is `make demo-gold` (11-step walkthrough). The portfolio **#8 CLI** also ships model lifecycle governance on `inst_spine` — see [Shipped today vs north star](#shipped-today-vs-north-star).*

---

## Shipped today vs north star

| Layer | Status | What it is |
|-------|--------|------------|
| **LLM spend control plane (canonical demo)** | ✅ `make demo-gold` | Gateway + sidecar + reconciler on `docker-compose.demo.yml` — reserve → dispatch → settle, drift lockout in step 10 |
| **#8 ModelGovernor CLI (portfolio SKU)** | ✅ Gold standard | ML model lifecycle governance ledger — `register` / `approve` / `deploy` / `drift_alert` on `inst_spine`, offline `verify-bundle` |

**Diligence lens:** Buyers comparing you to LiteLLM/Portkey should run **`make demo-gold`**. Buyers evaluating SR 11-7 / model-risk evidence use the **#8 CLI** lifecycle ledger.

### Canonical sales demo (`make demo-gold`)

```bash
make demo-gold-up
make demo-gold          # full 11-step walkthrough
make demo-gold-reset    # before rerun (wallet locked after step 10)
make demo-gold-down     # teardown
```

| Command | Stack | Purpose |
|---------|-------|---------|
| `make demo-gold` | `docker-compose.demo.yml` (gateway + sidecar + reconciler) | **Canonical** — governance + reliability; drift lockout in **step 10** (`DRIFT_THRESHOLD_EXCEEDED` → wallet locked → 409 on next reserve) |
| `make demo-drift-lock` | `docker-compose.yml` (sidecar only, legacy) | Optional standalone drift drill — **not** required for sales; redundant if you ran gold |

Full reference: [DEMO_GOLD.md](DEMO_GOLD.md)

### Portfolio CLI proof (#8 lifecycle)

```bash
./scripts/demo_model_governor.sh
model-governor verify-bundle --tarball ./model_governor_bundle.tar
```

---

## The honest map: who overlaps what

Nothing is the same end-to-end. Several products touch parts of what the north star describes; almost none combine **ledger-grade finance control + pre-dispatch enforcement + multi-provider gateway** in one control plane. That gap is the valuation story — and also why comps are messy.

| Category | Examples | What they do well | What they usually don't do |
|----------|----------|-------------------|----------------------------|
| **AI gateway / proxy** | LiteLLM, Portkey, Kong AI Gateway, Helicone gateway, OpenRouter | Route models, keys, fallbacks, budgets, logs | Postgres ledger, reserve-before-dispatch, drift → wallet lockout, reconciler for stranded holds |
| **LLM observability** | Helicone, LangSmith, Arize | Traces, evals, analytics | Block spend before inference; authoritative settlement |
| **Cloud / FinOps** | Kubecost → IBM, Cloudability, native AWS/Azure budgets | Infra spend, chargeback, alerts | Per-request LLM governance at the gateway |
| **Build your own** | Internal platform teams | Fits your stack | ~12–18 engineer-months + institutional test suite for production-grade finance plane |

**Sales-call trap:** buyers compare you to LiteLLM/Portkey. **Diligence lens:** compare to FinOps + gateway — that's the white space.

---

## Closest “same aisle” — and how you're different

### 1. LiteLLM (BerriAI)

| | |
|---|---|
| **Same** | OpenAI-shaped API, multi-provider, budgets, virtual keys, self-host |
| **Different** | LiteLLM is a proxy + logging; budgets are typically limits/tracking, not an append-only ledger with reserve → settle → drift lockout |
| **Valuation signal** | ~$6M+ ARR cited publicly on ~$2M raised — market pays for adoption + gateway, not ledger depth |

### 2. Portkey → Palo Alto (~$120–140M acquisition, 2026)

| | |
|---|---|
| **Same** | Enterprise AI gateway, governance, cost visibility, routing, agent-era story |
| **Different** | Portkey had massive token volume and revenue narrative; the north-star edge is finance-plane semantics (reserve before dispatch, reconciler, hash-chain audit) — deeper on money correctness, lighter on traction |
| **Valuation signal** | Strategic buyer paid for control-plane position + distribution, not just code |

### 3. Helicone → Mintlify (acquired 2026)

| | |
|---|---|
| **Same** | Gateway + observability, OpenAI compat, routing |
| **Different** | Observability-first; not a wallet/ledger control plane |
| **Valuation signal** | Smaller outcome (YC-scale) — traffic + OSS, not institutional finance |

### 4. Kubecost → IBM (2024)

| | |
|---|---|
| **Same** | “Stop runaway spend before the bill” — FinOps control-plane mindset |
| **Different** | Kubernetes/cloud infra, not LLM token paths |
| **Valuation signal** | Validates that spend control planes get strategic M&A; north star is the LLM-shaped version |

### 5. Kong / MuleSoft / TrueFoundry / Bifrost

| | |
|---|---|
| **Same** | Centralized AI traffic, SSO, quotas, enterprise deploy |
| **Different** | API-management or MLOps platform extended to LLMs; rarely micro-cent ledger + reconciler + finance chaos tests |

---

## Is there “nothing else the same”?

**Correct** in this narrow sense:

A self-hostable stack where every governed LLM call goes **reserve → provider → settle** on real tokens, with Postgres as source of truth, drift lockout, leader-elected reconciler, and tamper-evident audit — plus demo + K8s/GitOps in one repo.

**Incorrect** if you say:

- “We're the only AI gateway” or “we're the only cost tool.”

There are many gateways and many cost dashboards. The claim is **ledger-backed governance**, not “another proxy.”

---

## What exists in this repo today (building blocks)

| Component | Product | Relevance to north star |
|-----------|---------|-------------------------|
| `inst_spine` | All 8 SKUs | Genesis WAL, hash chain, Lamport clocks, F1–F9, deterministic export — **audit spine** for any finance plane |
| `proxy_risk` (#2) | Outbound API firewall | **Pre-upstream gate chain** pattern — analogous to pre-dispatch enforcement |
| `ai_kit` (#4) | Agent traces + rate limits | OpenAI-compat client, token buckets — **not** reserve/settle wallet |
| `ad_guard` (#6) | Spend kill + gate audit | **Spend enforcement** pattern on marketing APIs |
| `model_governor` (#8) | Model lifecycle ledger | **Shipped SKU** — model governance, not LLM wallet |

The portfolio already proves institutional correctness (157+ tests, 12/12 rigorous E2E, offline verify-bundle). The north star adds a **finance hot path** on top of that spine.

---

## North star architecture (roadmap)

```
Client (OpenAI-compat)
        │
        ▼
┌───────────────────┐
│  Gateway proxy    │  route / keys / fallbacks / multi-provider
└─────────┬─────────┘
          │ reserve (wallet hold)
          ▼
┌───────────────────┐
│  Postgres ledger  │  append-only wallet + settlement
└─────────┬─────────┘
          │ dispatch if reserved
          ▼
     Provider API
          │
          ▼ settle on actual tokens
┌───────────────────┐
│  Reconciler       │  leader-elected; release stranded holds
└─────────┬─────────┘
          │ drift threshold
          ▼
     Wallet lockout (fail-closed)
```

**Roadmap milestones** (each unlocks comp narrative):

| Milestone | Moves you toward… |
|-----------|-------------------|
| 1–2 paid pilots ($150K+) | LiteLLM-style ACV comp |
| Fortune 500 logo (even unpaid design partner) | Portkey-style strategic narrative |
| Published “we replaced LiteLLM budgets with reserve/settle” case study | Clear category of one |
| Managed/SaaS control plane | 2–3× ACV multiple |

---

## How valuation should be read

You're not priced like revenue-stage Portkey. You're closer to:

| Comp lens | What it implies |
|-----------|-----------------|
| LiteLLM (ARR, no ledger) | Ceiling if you stay “proxy only” |
| Portkey (strategic exit) | Ceiling if you get logos + token volume |
| Kubecost (FinOps M&A) | Validates control-plane premium |
| Replacement cost (~12–18 eng-mo for production finance pack) | Floor — what it costs to rebuild |

**Pre-revenue fair value** is basically:

```
replacement cost
+ differentiation premium (ledger + reconciler + institutional tests)
+ optional narrative premium (design partners, pipeline)
− discount for no ARR/logos
```

That's why a single number feels slippery: comps are in different categories (proxy vs FinOps vs acqui-hire).

---

## Valuation bands (June 2026)

### #8 as-built (model lifecycle governance SKU)

| Context | Range |
|---------|-------|
| Standalone IP (#8 only) | **£25k–£70k** |
| Full 8-product portfolio | **£70k–£150k** |

See [INST_PLUS_PRE_REV_VALUATION.md](INST_PLUS_PRE_REV_VALUATION.md) for portfolio methodology.

### North star platform (LLM spend control plane — not shipped)

Assumptions: clean repo, demo works for finance plane, CI green, no paying customers, no formal data room, one buyer not a process.

| Scenario | Indicative headline (company / IP) | Cash at close (rough) | You keep ~5–15% |
|----------|--------------------------------------|----------------------|-----------------|
| **Weak** (buyer knows you're rushed) | £1.5M – £2.5M | £1.0M – £1.8M | Rolled stock in buyer; illiquid |
| **Base** (strategic fit, decent diligence) | £2.5M – £4.5M | £2.0M – £3.5M | Common on larger strategics |
| **Strong** (2 bidders, clear FinOps/gateway fit) | £4.5M – £7M | £3.5M – £5.5M | Less common without revenue |

**USD** (at ~£1 ≈ $1.28–1.32): roughly **$2M – $9M** headline on the same assumptions.

Internal deck logic (~$4.5M–$6.5M “fair” pre-revenue) is achievable in a **proper process** with a strategic buyer — not the median outcome for a single-buyer, tomorrow sale (expect ~20–35% haircut vs “fair”).

### Why not “Portkey money”?

| Comp | Why it doesn't price you tomorrow |
|------|-----------------------------------|
| Portkey ~$120–140M | Revenue, token volume, 24k+ orgs, Palo Alto strategic |
| LiteLLM ~$6M ARR | Paying customers, OSS gravity |
| Helicone → Mintlify | Team + traffic acqui-hire, not ledger IP alone |

You're priced closer to **replacement cost + strategic optionality**, not ARR multiples.

---

## What “exit tomorrow” actually means

With no revenue and no auction, you're not selling like Portkey ($120M+ with traction). You're in one of these buckets:

| Deal type | Who buys | Typical driver |
|-----------|----------|----------------|
| **Asset / IP purchase** | US strategic, UK integrator, PE roll-up | Code + docs + avoid 12–18 eng-month rebuild |
| **Acqui-hire** | Larger product co. needs team + tech | People + velocity matter as much as IP |
| **Licensing / white-label** | Not a full exit; smaller upfront | Weak “exit,” keeps upside |

“Keeping a small %” usually means **rollover equity** (part cash, part shares in buyer/newco) or earn-out tied to retention — often 5–15% with 2–4 year vesting.

### Rollover example (£3.5M headline, 10% rollover, 80% cash at close)

| Line | Amount |
|------|--------|
| Headline | £3.5M |
| Cash at close (~80%) | ~£2.8M |
| Rollover (10%) | ~£350k paper in buyer equity |
| Escrow / holdback (typical 10%) | ~£350k released over 12–18 months |

**Upside:** if buyer 3×'s, your 10% might be worth more than extra cash you gave up.  
**Downside:** rollover is illiquid, employment-tied, and can go to zero.

**Rule of thumb:** only rollover if you believe in the buyer's stock more than cash in hand.

---

## UK-specific (June 2026) — ask a solicitor

| Topic | Why it matters |
|-------|----------------|
| Share sale vs asset sale | Tax and what you actually sell differ massively |
| Business Asset Disposal Relief (ex-Entrepreneurs' Relief) | CGT on qualifying share disposals — limits/rates change; confirm current rules |
| EMI / options | If anyone has options, exit structure gets messy |
| Buyer location | US buyer → UKCo often fine; W&I insurance, warranties, £50k–£150k+ legal fees |
| Currency | Deal often in USD; your net is GBP after FX |

Budget **£75k–£200k** all-in for legal + tax on a £2M–£5M deal if done properly.

---

## What moves you up one band (even in 2–4 weeks)

1. One design-partner LOI (even unpaid) — “Fortune 500 evaluating”
2. Paid pilot term sheet — even £50k–£150k changes the conversation
3. Mini data room — capability matrix, demo video, CI badge, architecture
4. Two strategic conversations — Portkey/LiteLLM replacement narrative

That's often **+£1M–£2M** on headline vs a fire sale.

---

## Plain-English summary

| Question | Answer |
|----------|--------|
| Exit tomorrow, small % kept — UK June 2026? | Plan on **~£2M–£4M headline**, **~£1.5M–£3M cash at close** as the realistic band for the **north-star platform** unless you already have a motivated strategic buyer |
| Best case without revenue? | **£4.5M–£7M** if strategic + competitive tension |
| Worst case rushed? | **£1M–£2M** acqui-hire / asset strip |
| #8 as-built alone? | **£25k–£70k** — lifecycle governance SKU, not gateway exit |
| Full portfolio as-is? | **£70k–£150k** — see [INST_PLUS_PRE_REV_VALUATION.md](INST_PLUS_PRE_REV_VALUATION.md) |

You're not worthless — you're **pre-traction**, so price is buyer-specific, not formulaic.

---

## One line for a buyer conversation

“We're the ledger control plane for LLM spend — not LiteLLM with budgets. Institutional++: `make demo-gold` in five minutes (reserve-before-dispatch, drift lockout in step 10). We're open to cash + small rollover for the right strategic.”

---

## Related documents

| Doc | Scope |
|-----|-------|
| [DEMO_GOLD.md](DEMO_GOLD.md) | Canonical `make demo-gold` walkthrough |
| [MODEL_GOVERNOR_BUYER.md](MODEL_GOVERNOR_BUYER.md) | Shipped #8 buyer sheet |
| [MODEL_GOVERNOR_SALES_TECH_SPEC.md](MODEL_GOVERNOR_SALES_TECH_SPEC.md) | Shipped #8 RFP depth |
| [INST_PLUS_PRE_REV_VALUATION.md](INST_PLUS_PRE_REV_VALUATION.md) | Portfolio pre-rev valuation (as-built) |
| [PORTFOLIO_SALES_SHEET.md](PORTFOLIO_SALES_SHEET.md) | All 8 SKUs commercial matrix |
| [AI_KIT_SALES_TECH_SPEC.md](AI_KIT_SALES_TECH_SPEC.md) | Closest shipped LLM-adjacent SKU |
