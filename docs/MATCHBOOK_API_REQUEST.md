# Matchbook API access — application reply template

Copy the block below into your reply email. Items marked `[FILL]` must be completed before sending.

**Minimum requirement:** account balance **≥ $200** before API access is granted.

---

**Subject:** Re: Matchbook API access request — UK/Ireland horse racing analytics (read-only odds)

Dear Matchbook team,

Thank you for your email. Please find answers to your questions below.

---

### What will the API feed be used for?

**Read-only** REST API access to horse racing prices for a **UK/Ireland racing analytics platform** (commercial licensing / white-label SaaS).

The feed is used to:

1. Authenticate once per daily batch (~**06:00 Europe/London**).
2. Pull **win and place (each-way)** prices for upcoming GB + IRE racecard runners.
3. Merge exchange odds into a **LightGBM place-ranking engine** and flag value selections.
4. Log each-way value picks to a **paper-trading audit ledger** with SHA-256 verification hashes for third-party due diligence.

**We do not use the API to place bets.** Order placement and live execution are **disabled** in the codebase (`EXECUTION_DISABLED = True`). The product is analytics, paper ledger, and affiliate deep-links only.

**We do not redistribute** raw Matchbook prices. Only derived analytics (probabilities, value flags, P&L on our own site) are shown.

Technical integration: Python client → `https://api.matchbook.com/edge/rest` → `/security/session` (username/password). Invoked from `refresh-cards --odds-source auto` during `scripts/daily_refresh.sh`.

---

### Details of your website, if any?

| Item | Detail |
|------|--------|
| **Product name** | Hibs Racing Intelligence |
| **Category** | UK/Ireland horse racing analytics · daily value sheet · verified paper ledger |
| **Public site** | `[FILL: e.g. https://your-domain.com/tracker — or "In development / staging only; not yet public"]` |
| **Track record** | Read-only `/tracker` page + CSV export (`/api/tracker/export.csv`) |
| **Affiliate** | UTM-tagged partner links to Matchbook (no website scraping) |
| **Related product** | Separate football engine (hibs-bet) — **does not use Matchbook** |

---

### How often do you intend to hit the feed?

| Mode | Frequency |
|------|-----------|
| **Production** | **Once per day** — morning batch after cards are published (~06:00 UK) |
| **Per batch** | One session login + odds fetch for that day’s racecards (GB + IRE, ~24h window) |
| **Development** | Occasional manual refreshes during testing — typically **a few sessions per week**, not continuous |
| **In-play / live polling** | **None** |

Estimated API volume: **low** — well within standard retail limits (not a high-frequency or in-play bot).

---

### What sports and markets do you trade on?

| | |
|---|---|
| **Sports** | **Horse racing only** (United Kingdom + Ireland) |
| **Markets** | **Win** and **place** (each-way) on pre-race racecard runners |
| **Timing** | **Morning / pre-race** odds at batch time — not in-play |
| **Not covered** | Football, tennis, or other sports via this API integration |

---

### What type of trading do you engage in (arbing etc.)?

| | |
|---|---|
| **Via API** | **None** — read-only odds ingestion only |
| **Arbitrage** | **No** |
| **Automated / bot trading** | **No** — no API order placement |
| **Personal betting** | Occasional **manual, discretionary** each-way bets on flagged selections after review — standard recreational exchange use, not arbing |

---

### What's your average bet size?

| Context | Typical stake |
|---------|----------------|
| **Personal manual bets** (not API-driven) | **£5–£20 each-way** per selection |
| **Paper ledger** (analytics only) | **1 abstract unit** per logged pick for ROI reporting — not live API orders |

---

### What is your Matchbook account name that you will be using for trading?

**Matchbook username:** `[FILL: your Matchbook login]`

**Registered email:** `[FILL: email on Matchbook account]`

**Account country:** United Kingdom

---

### Has your account been funded? (A minimum balance of $200 is required for API access to be granted).

`[FILL ONE:]`

- [ ] **Yes** — account funded with at least **$200** (or GBP equivalent).
- [ ] **No** — I will fund to the minimum before using the API.
- [ ] **Pending** — funding in progress; expect completion by `[FILL: date]`.

---

### Details for main contact person?

| Field | Detail |
|-------|--------|
| **Name** | Philip Macleod |
| **Role** | Product owner / developer |
| **Email** | `[FILL: your contact email]` |
| **Country** | United Kingdom |
| **Phone** | `[FILL: optional]` |
| **Company / trading name** | `[FILL: optional — e.g. sole trader / Ltd name]` |

---

### Additional technical context (optional paragraph)

Session login currently returns **403 Forbidden**, which I understand is pending API enablement on the account. Once enabled, the daily pipeline will:

1. Ingest raceform results (lookback window).
2. Refresh 24h GB + IRE cards.
3. Score with LightGBM ranker.
4. Attach Matchbook odds where available.
5. Log value picks with `--paper` and optional Telegram/Discord digest.

No scraping of the Matchbook website — **REST API only**.

Please advise if you need a short architecture PDF, UI screenshots, or further verification.

Kind regards,  
Philip Macleod  
`[FILL: contact email]`

---

## Quick checklist before send

- [ ] Matchbook username and email filled in
- [ ] Funding ≥ $200 confirmed (or date you will fund)
- [ ] Website line accurate (live URL vs staging)
- [ ] Reply sent from the **same email** registered on the Matchbook account (if they require it)

## Internal reference

- Odds client: `src/hibs_racing/odds/matchbook.py`
- Daily batch: `scripts/daily_refresh.sh` @ 06:00
- Env vars: `MATCHBOOK_USERNAME`, `MATCHBOOK_PASSWORD`, optional `MATCHBOOK_API_BASE`
- Affiliate (separate from API): `HIBS_AFFILIATE_VENUE=matchbook` in `.env`
