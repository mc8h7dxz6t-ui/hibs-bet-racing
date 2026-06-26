# Institutional++ — plug / demo / run

**One entry point** for buyers, diligence, and sales demos. All 11 SKUs on shared `inst_spine`.

---

## 60-second start

```bash
git clone <repo> && cd <repo>
make install
make demo-ready          # preflight: Python, CLIs, imports
make demo-all            # all 11 SKUs → data/demo/portfolio/
```

**Expected:** green preflight banner; portfolio summary `"status": "PASSED"`, `"products": 11`.

---

## What to run when

| Goal | Command | Time |
|------|---------|------|
| **Preflight** (before any demo) | `make demo-ready` | ~30s |
| **Full portfolio demo** (12 SKUs) | `make demo-all` | ~4–6 min |
| **Spend-plane sales walkthrough** | `make demo-gold` | ~60s |
| **Proof Console** (11 SKU picker + workflows) | `make demo-gold-up` → http://127.0.0.1:8790 | ~30s |
| **Spend gateway** (OpenAI-compat) | `make spend-gateway` → http://127.0.0.1:8789 | ~10s |
| **Unit + integration smoke** | `make smoke` | ~2 min |
| **Rigorous E2E 11/11** | `make rigorous` | ~3 min |
| **Chaos drills** | `make chaos` | ~1 min |
| **Offline-safe demos** | `SKIP_LIVE=1 make demo-all` | ~3 min |

---

## Makefile targets

```bash
make help              # list all inst++ targets
make install           # pip install -e ".[dev,instpp]"
make demo-ready        # preflight
make demo-all          # 11/11 portfolio demos
make demo-phase2       # drift-gate + webhook-replay + spend-guard only
make demo-gold         # 11-step spend-plane walkthrough (CLI)
make demo-gold-reset   # wipe spend-gold wallet after drift lockout
make demo-gold-up      # seed UI data + start workflow console
make demo-gold-down    # stop workflow console
make smoke             # 113+ tests
make rigorous          # logged 11/11 E2E
make chaos             # WAL / wallet / capture chaos
make test              # full pytest
```

---

## Environment (optional)

Copy and customize:

```bash
cp .env.instpp.example .env.instpp
# shellcheck disable=SC1091
source .env.instpp
```

Key variables — see `.env.instpp.example` for full list.

| Variable | Purpose |
|----------|---------|
| `SKIP_LIVE=1` | No external HTTP (proxy forward, FX feed) |
| `WEBHOOK_PROVIDER_SECRET` | Webhook Mesh / Replay signature secret |
| `WEBHOOK_REPLAY_CAPTURE_DIR` | `.wrcap` capture directory for Mesh ingress |
| `PROXY_DRIFT_BASELINE` / `PROXY_DRIFT_MODE` | Proxy-Risk + Drift Gate integration |
| `INST_REDIS_URL` | Optional Redis for drift rolling state |
| `OPENAI_API_KEY` | AI Kit live LLM (default: stub mode) |

---

## Per-SKU demos (individual)

```bash
./scripts/demo_compliance_logger.sh
./scripts/demo_proxy_risk.sh
./scripts/demo_altdata.sh
./scripts/demo_ai_kit.sh
./scripts/demo_webhook_mesh.sh
./scripts/demo_ad_guard.sh
./scripts/demo_health_telemetry.sh
./scripts/demo_model_governor.sh
./scripts/demo_drift_gate.sh
./scripts/demo_webhook_replay.sh
./scripts/demo_spend_guard.sh
```

Artifacts land in `data/demo/` (gitignored). Verify any bundle offline:

```bash
compliance-log verify-bundle --tarball data/demo/portfolio/compliance_bundle.tar
spend-guard verify-bundle --tarball data/demo/portfolio/spend_guard_bundle.tar
```

---

## Diligence pack (15 minutes)

```bash
make install
make smoke
make rigorous
make chaos
cat docs/test_logs/instpp_rigorous_latest_summary.json
make demo-all
```

See [BUYER_EVIDENCE_PACK.md](BUYER_EVIDENCE_PACK.md).

---

## Related docs

| Doc | Purpose |
|-----|---------|
| [INST_PLUS_GOLD_STANDARD.md](INST_PLUS_GOLD_STANDARD.md) | Nine dimensions, 11/11 matrix |
| [DEMO_GOLD.md](DEMO_GOLD.md) | Spend-plane sales walkthrough (`make demo-gold`) |
| [DEMO_VIDEO_PORTFOLIO_ALL.md](DEMO_VIDEO_PORTFOLIO_ALL.md) | Video recording with `PAUSE=1` |
| [PORTFOLIO_SALES_SHEET.md](PORTFOLIO_SALES_SHEET.md) | SKU one-liners for outreach |

---

## Honest limits

| Item | Status |
|------|--------|
| **11/11 CLI demos** | ✅ `make demo-all` |
| **Spend-plane gold demo** | ✅ `make demo-gold` (Spend Guard CLI) |
| **Workflow UI** | ✅ Proof Console 11 SKU picker + Compliance + Proxy (`make demo-gold-up`) |
| **Redis Stream delivery** | ✅ `WEBHOOK_DISPATCH_MODE=redis` + rigorous E2E + chaos |
| **Spend gateway (OpenAI-compat)** | ✅ `spend-guard serve` + rigorous HTTP E2E |
| **Postgres compose stack** | Design-partner north star — not required for proof |
| **Sports (hibs-racing)** | Separate product — not part of inst++ sale |
