# Proxy-Risk Gateway — Buyer Sheet

**One job:** Institutional outbound API firewall — rate limit, dedupe, drift kill, and cryptographic audit before traffic hits upstream brokers or payment rails.

**Pitch:** *Control what leaves your boundary — and prove every gate decision.*

---

## Buyer

| Segment | Pain | Institutional answer |
|---------|------|---------------|
| Fintech / broker ops | Runaway API calls after bug or fat finger | Token bucket + Z-score kill switch |
| Quant / trading infra | Need shadow mode before live capital | Shadow default; `--live` when ready |
| Platform teams | No audit trail on proxy layer | Every gate outcome logged to genesis chain |

**Price band:** £400–£1,200/mo per tenant (API proxy + audit).

---

## Gate chain (hot path, in-memory)

```
circuit → schema → token bucket → idempotency → z-score drift → [shadow | live forward]
```

| Mode | Behavior |
|------|----------|
| **Shadow** | Gates run; no upstream call; ledger append async |
| **Live** | Sync WAL before upstream; 4xx/5xx → REJECT (fail-closed) |

**Latency target:** p99 &lt; 10ms shadow (10k bench in test suite); prod Redis for multi-instance.

---

## 60-second demo

```bash
./scripts/demo_proxy_risk.sh
```

Live forward requires:
```bash
export PROXY_RISK_UPSTREAM_BASE=https://your-api.example.com
export PROXY_RISK_UPSTREAM_TOKEN=...   # optional bearer
proxy-risk evaluate --live --path /orders --body '{"symbol":"AAPL"}'
```

---

## Non-goals

- **Not** sub-5ms RTB exchange insert (Go/Rust territory)
- **Not** DoubleVerify / IAS pre-bid placement
- **Not** HashiCorp Vault in P1 (env token adapter; vault swap documented)
- **Not** inbound webhook mesh (see Product #5)

---

## Environment

| Variable | Purpose |
|----------|---------|
| `PROXY_RISK_UPSTREAM_BASE` | Live upstream URL |
| `PROXY_RISK_UPSTREAM_TOKEN` | Bearer token for upstream |
| `PROXY_RISK_API_TOKEN` | Optional auth on `/evaluate` serve |
| `INST_CIRCUIT_KILL=1` | Emergency traffic sever |
| `INST_REDIS_URL` | Multi-instance idempotency + token bucket |

---

## CLI

| Command | Purpose |
|---------|---------|
| `evaluate` | Single request through gate chain |
| `check` | F1–F9 on proxy ledger |
| `export` | Audit bundle |
| `verify-bundle` | Offline auditor replay |
| `serve` | HTTP gateway (shadow or live) |

See `src/proxy_risk/README.md` for architecture.  
**Full spec:** `docs/PROXY_RISK_SALES_TECH_SPEC.md`

---

## Next step

| Step | Action |
|------|--------|
| 1 | `./scripts/demo_proxy_risk.sh` (60s) |
| 2 | `proxy-risk verify-bundle --tarball ./proxy_bundle.tar` |
| 3 | RFP depth → `docs/PROXY_RISK_SALES_TECH_SPEC.md` |
| 4 | Portfolio pricing → `docs/PORTFOLIO_SALES_SHEET.md` |
