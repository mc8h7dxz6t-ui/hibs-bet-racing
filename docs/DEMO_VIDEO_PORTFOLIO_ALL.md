# Portfolio Demo Video — All 8 Services

**Purpose:** One screen-recording covering **every product** — real terminal, plain-English voiceover.  
**Length:** ~18–25 minutes (or split into Part 1 / Part 2 at 10 min)  
**Not:** AI avatar marketing — **you + terminal** is the trust signal.

---

## Quick start (record today)

```bash
cd /path/to/hibs-bet-racing
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,instpp]"

# Guided — pauses before each product
./scripts/record_portfolio_demo_video.sh --clean

# Or fast run (no pauses)
SKIP_LIVE=1 ./scripts/demo_portfolio_all.sh --clean
```

**Artifacts:** `data/demo/portfolio/*.tar` — eight verify-bundle tarballs.

---

## Title card (10 sec)

```
Eight guardrails. One proof spine.
Decisions · APIs · Webhooks · Data · AI · Ads · Health · Models
Prove it offline — your cloud.
```

---

## Opening (60 sec) — read aloud

> “Software moves money and decisions faster than humans can explain them afterward.  
> When something goes wrong — a double charge, a runaway API call, bad data, runaway ad spend — someone asks **prove it**. Dashboards aren’t enough.  
> I built **eight small tools** on **one audit spine**: they **stop common failures** and leave **tamper-evident records** an outsider can check **without logging into our website**.  
> Everything runs in **the customer’s cloud** — this isn’t a flashy SaaS app.  
> Next fifteen minutes: **all eight**, real commands, real proof exports. Sports and betting analytics are a **separate project** — this is **business infrastructure**.”

**[ACTION]** Start recording. Terminal full screen. Run:

```bash
source .venv/bin/activate
export SKIP_LIVE=1
./scripts/record_portfolio_demo_video.sh --clean
```

---

## Per product — what to say at each pause

When the script pauses, read the **SAY** block (~60–90 sec each), then press Enter.

---

### 1/8 — Compliance Logger

**Plain:** CCTV for business decisions.

**SAY:**

> “**One — Compliance Logger.** When someone approves a loan, blocks a user, or escalates a case, regulated teams need proof later — not a Jira export. This records the decision in a **sealed log**: what went in, what was decided, who did it. At the end you get a **bundle an auditor verifies offline** — no callback to us. Think **evidence**, not ServiceNow.”

**On screen:** ingest → check → export → verify-bundle PASS.

---

### 2/8 — Proxy-Risk

**Plain:** Bouncer on outbound API calls.

**SAY:**

> “**Two — Proxy-Risk.** Outbound calls to brokers, payments, APIs — one bug can fire thousands of requests. This is a **bouncer**: rate limits, duplicate detection, kill switch. You can **practice in shadow** so nothing leaves the building, then go live. **Every allow or block is logged** the same way — prove what the gateway did on a bad day.”

**On screen:** shadow gates → check → export → verify.

---

### 3/8 — Alt-Data

**Plain:** Smoke alarm for data feeds.

**SAY:**

> “**Three — Alt-Data.** Desks use scraped or third-party feeds. When the API breaks, dashboards often look fine until you’ve already traded. This **checks coverage before you trust the feed**, tries backup sources, and **seals each poll** so you can answer: what did we actually have on date X?”

**On screen:** poll → check → export → verify.

---

### 4/8 — AI Kit

**Plain:** Flight recorder for AI agents.

**SAY:**

> “**Four — AI Kit.** Production AI agents crash, hit rate limits, lose their place mid-task. This adds **safe throttling**, **checkpoints to resume**, and a **trace ledger** — what did the agent do, exportable for review. Not ChatGPT — **guardrails around your agents**.”

**On screen:** agent run (stub) → check → export → verify.

---

### 5/8 — Webhook Mesh

**Plain:** Never charge twice for one webhook.

**SAY:**

> “**Five — Webhook Mesh.** Stripe and Shopify send ‘something happened’ messages. Delivered twice to two servers — **double charge**. This **dedupes across pods**, **writes safely before you say OK**, and logs **ingress proof** for billing disputes. The money-saver for SaaS and fintech.”

**On screen:** server, Stripe route, check → export → verify.

---

### 6/8 — Ad Guard

**Plain:** Circuit breaker on ad API spend.

**SAY:**

> “**Six — Ad Guard.** Wrong Google or Meta settings can burn thousands in hours; finance finds out after. This **watches spend at the API**, **cuts off abnormal velocity**, records **why** — for marketing finance and agencies. Creative safety tools live **upstream**; this is **spend at the door**.”

**On screen:** evaluate → check → export → verify.

---

### 7/8 — Health Telemetry

**Plain:** Sealed envelope for device readings.

**SAY:**

> “**Seven — Health Telemetry.** Remote monitoring needs to show **readings weren’t tampered with** — without a full hospital IT project. Device batches get **sealed and exported** for diligence. **Not an FDA device** — **integrity of the log**.”

**On screen:** ingest batch → check → export → verify.

---

### 8/8 — ModelGovernor

**Plain:** Signed model approvals.

**SAY:**

> “**Eight — ModelGovernor.** Banks and lenders ask: **who approved model version three point two for production?** Spreadsheets fail. This records **register, approve, deploy** with a **fingerprint of the model file** — offline proof for model risk.  
> There’s also an **LLM spend control plane** for platform teams — meter before the model runs — that’s a separate demo (`make demo-gold`) for AI gateway buyers.”

**On screen:** register → approve → check → export → verify.

---

## Closing spine (45 sec)

**SAY:**

> “Same idea across all eight: **stop the mistake, seal the evidence, verify offline**.  
> For regulated companies that’s often **webhooks in, decisions, APIs out** — we bundle those.  
> **Four-week pilots in your VPC** from **two and a half thousand pounds** — shadow first if you want.  
> Contact below — or DM for a fifteen-minute dry-run on **one** product that hurts. Thanks.”

**[ON SCREEN]**

```
Prove it happened — before the bill, the audit, or the dispute.
Pilot from £2.5k · [your email / LinkedIn]
```

---

## Split into two videos (optional)

| Part | Products | ~Length |
|------|----------|---------|
| **Part 1 — Money & APIs** | #1 Compliance, #2 Proxy, #5 Webhook, #6 Ad Guard | ~10 min |
| **Part 2 — Data, AI, Health, Models** | #3 Alt-Data, #4 AI Kit, #7 Health, #8 ModelGovernor | ~10 min |

Run half the script manually with `PAUSE=1` and stop after product 4 or 5.

---

## YouTube description (all 8)

```
Full portfolio demo — 8 VPC audit products on one cryptographic spine.

1 Compliance Logger — decision proof
2 Proxy-Risk — outbound API guard
3 Alt-Data — feed coverage proof
4 AI Kit — agent trace + checkpoints
5 Webhook Mesh — billing webhook dedupe
6 Ad Guard — marketing API spend kill
7 Health Telemetry — device batch integrity
8 ModelGovernor — model approval proof

Every product: check → export → offline verify-bundle (no vendor callback).

For: fintech, SaaS billing, lending, platform eng, marketing finance, health tech, MRM.
Deploy: your VPC. Pilots from £2.5k.

Contact: [your details]

Commands: ./scripts/demo_portfolio_all.sh
```

---

## Title options

1. **8 ways to prove your software didn’t lie (full demo)**  
2. **VPC audit infrastructure — all 8 products, one spine (live demo)**  
3. **Stop double charges, runaway APIs, and audit gaps — 20 min proof**

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Demo fails mid-run | `SKIP_LIVE=1` · Python 3.12 · `pip install -e ".[dev,instpp]"` |
| Mac FD errors | `ulimit -n 4096` · see INSTITUTIONAL_STANDARD.md |
| Video too long | Split Part 1 / Part 2 · or show 3 products + “seven more same pattern” |
| ModelGovernor LLM spend | Mention only · full stack = `make demo-gold` when available |

---

## Related

- `scripts/demo_portfolio_all.sh` — run all 8 without recording  
- `scripts/record_portfolio_demo_video.sh` — guided pauses  
- `docs/DEMO_VIDEO_WEBHOOK_MESH.md` — deep dive single product  
- `docs/PORTFOLIO_SALES_SHEET.md` — pricing
