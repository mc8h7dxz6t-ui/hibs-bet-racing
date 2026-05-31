# Matchbook API access — reply template

Copy, fill `[brackets]`, and reply to Matchbook support.

---

**Subject:** Re: API access request — read-only odds for analytics platform

Hello,

Thank you for following up. Please find my account and intended use details below.

**Account details**
- Matchbook username: `[your username — e.g. philmac1]`
- Registered email: `[your Matchbook account email]`
- Account country: `[e.g. United Kingdom]`

**Commercial intent**
I am building a **UK/Ireland horse racing analytics platform** for commercial licensing (SaaS / tipping syndicate / affiliate distribution). The product is **analytics and paper-trading only** — not automated live betting.

**Requested API access**
- **Read-only** REST API access to horse racing markets (win/place prices, market metadata)
- Endpoint: `https://api.matchbook.com/edge/rest`
- Use case: merge exchange odds into a LightGBM scoring engine, flag value selections, and log picks to a **public SHA-256 audit ledger** for third-party verification

**What we will NOT do**
- No automated order placement or live execution via the API
- No scraping of the website — REST API only
- No redistribution of raw Matchbook feed data; only derived analytics outputs

**Technical context**
- Batch job runs once daily (~06:00 Europe/London) to refresh cards and odds
- Python client authenticates via `/security/session` with username/password
- Current status: `403 Forbidden` on session login pending account API enablement

**Volume**
- Low frequency: one authentication per daily batch + occasional manual refreshes during development
- Estimated: well under free-tier / standard retail API limits

Please enable API access on my account or advise any additional verification steps.

Kind regards,  
`[Your full name]`  
`[Contact email]`  
`[Optional: company / product name — Hibs Racing Intelligence]`
