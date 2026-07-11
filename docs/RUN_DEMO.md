# Institutional++ — plug / demo / run

**One entry point** for buyers, diligence, and sales demos. All 12 SKUs on shared `inst_spine`.

---

## 60-second start (plug and play)

```bash
git clone <repo> && cd <repo>
make plug
```

**What `make plug` does:** `install` → `demo-ready` → `demo-all` (offline) → `verify-portfolio` (offline verify-bundle 12/12).

**Expected:** green preflight banner; portfolio summary `"status": "PASSED"`, `"products": 12`; `data/demo/portfolio/PORTFOLIO_MANIFEST.json` with `"verified_ok": 12`.

---

## What to run when

| Goal | Command | Time |
|------|---------|------|
| **One-shot buyer pack** | `make plug` or `make buyer-pack` | ~5–8 min |
| **Preflight** (before any demo) | `make demo-ready` | ~30s |
| **Full portfolio demo** (12 SKUs) | `make demo-all` | ~4–6 min |
| **Offline verify all bundles** | `make verify-portfolio` | ~30s |
| **Full diligence proof** | `make proof` | ~6–8 min |
| **Spend-plane sales walkthrough** | `make demo-gold` | ~60s |
| **Proof Console** (12 SKU picker + workflows) | `make demo-gold-up` → http://127.0.0.1:8790 | ~30s |
| **Spend gateway** (OpenAI-compat) | `make spend-gateway` → http://127.0.0.1:8789 | ~10s |
| **Docker workflow UI** | `make stack-up` | ~60s |
| **Docker + Redis** (stream delivery) | `make redis-up` | ~60s |
| **Multi-instance prod profile** | `docs/PRODUCTION_REDIS_PROFILE.md` | 5 min read |
| **Unit + integration smoke** | `make smoke` | ~2 min |
| **Rigorous E2E 12/12** | `make rigorous` | ~3 min |
| **Chaos drills** | `make chaos` | ~1 min |
| **Offline-safe demos** | `SKIP_LIVE=1 make demo-all` | ~3 min |

---

## Makefile targets

```bash
make help              # list all inst++ targets
make plug              # one-shot: install + preflight + demo-all + verify
make buyer-pack        # smoke + demo-all + verify + BUYER_PACK_SUMMARY.json
make install           # pip install -e ".[dev,instpp]"
make demo-ready        # preflight
make demo-all          # 12/12 portfolio demos
make verify-portfolio  # offline verify-bundle 12/12 → PORTFOLIO_MANIFEST.json
make proof             # smoke + rigorous + verify-portfolio
make demo-phase2       # drift-gate + webhook-replay + spend-guard only
make demo-gold         # spend-plane walkthrough (CLI)
make demo-gold-reset   # wipe spend-gold wallet after drift lockout
make demo-gold-up      # seed UI data + start workflow console
make demo-gold-down    # stop workflow console
make stack-up          # docker workflow UI
make redis-up          # docker workflow + Redis
make smoke             # 157+ tests
make rigorous          # logged 12/12 E2E
make chaos             # WAL / wallet / capture chaos
make test              # full pytest
```

---

## Environment (auto-loaded)

On first run, scripts copy `.env.instpp.example` → `.env.instpp` (offline-safe defaults). All `instpp_*` scripts source this automatically.

Manual override:

```bash
cp .env.instpp.example .env.instpp
# shellcheck disable=SC1091
source .env.instpp
```

Key variables — see `.env.instpp.example` for full list.

| Variable | Purpose |
|----------|---------|
| `SKIP_LIVE=1` | No external HTTP (proxy forward, FX feed) — default in `.env.instpp` |
| `WEBHOOK_PROVIDER_SECRET` | Webhook Mesh / Replay signature secret |
| `WEBHOOK_REPLAY_CAPTURE_DIR` | `.wrcap` capture directory for Mesh ingress |
| `WEBHOOK_DISPATCH_MODE=redis` | Durable delivery (use with `make redis-up`) |
| `INST_REDIS_URL` | Redis for drift rolling state + webhook stream |

**Production Redis (multi-instance):** [PRODUCTION_REDIS_PROFILE.md](PRODUCTION_REDIS_PROFILE.md)
| `PROXY_DRIFT_BASELINE` / `PROXY_DRIFT_MODE` | Proxy-Risk + Drift Gate integration |
| `OPENAI_API_KEY` | AI Kit live LLM (default: stub mode) |

---

## Evidence artifacts (after `make plug`)

| File | Contents |
|------|----------|
| `data/demo/portfolio/*_bundle.tar` | 12 offline-auditable tarballs |
| `data/demo/portfolio/PORTFOLIO_MANIFEST.json` | Per-SKU verify-bundle results |
| `data/demo/portfolio/BUYER_PACK_SUMMARY.json` | One-shot pack metadata (`make buyer-pack`) |
| `docs/test_logs/instpp_rigorous_latest_summary.json` | Rigorous E2E summary (`make rigorous`) |

---

## Per-SKU demos (individual)

See `scripts/demo_<product>.sh` — each runs ingest → check → export → verify-bundle in &lt;60s.

---

## CI

GitHub Actions workflow `.github/workflows/instpp-ci.yml`:

- **PR:** smoke + preflight
- **Push / dispatch:** rigorous 12/12
- **Manual dispatch:** buyer-pack artifact upload

---

## Related docs

| Doc | Purpose |
|-----|---------|
| [INST_PLUS_GOLD_STANDARD.md](INST_PLUS_GOLD_STANDARD.md) | Nine dimensions, 12/12 matrix |
| [BUYER_EVIDENCE_PACK.md](BUYER_EVIDENCE_PACK.md) | Procurement 15-minute script |
| [DEMO_GOLD.md](DEMO_GOLD.md) | Spend-plane sales walkthrough |

---

## Honest limits

| Item | Status |
|------|--------|
| **12/12 CLI demos + rigorous E2E** | ✅ |
| **12/12 offline verify (`make verify-portfolio`)** | ✅ after `make demo-all` |
| **Postgres `docker-compose.demo.yml`** | ❌ North star only |
| **Proof Console guided ingest (#3–#12)** | ✅ Load demo payload → ingest → ledger → F1–F9 → export → verify |
