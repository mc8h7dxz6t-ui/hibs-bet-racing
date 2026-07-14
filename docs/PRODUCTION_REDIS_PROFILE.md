# Production Redis Profile — Multi-Instance VPC

**Purpose:** Procurement and SRE guide for horizontal scale on `inst_spine` SKUs.  
**Audience:** Platform engineering, InfoSec, SRE deploying 2+ gateway/mesh workers.  
**Status:** Shipped on `main` — rigorous E2E includes Redis stream mock + optional live `INST_REDIS_URL` soak (PR #28, CI `redis-soak` job).

---

## When Redis is required

| Deploy shape | Redis needed? | Backend |
|--------------|---------------|---------|
| **Single-tenant VPC** (1 pod / 1 VM) | **No** | In-memory idempotency + file-backed drift state |
| **Multi-instance** (2+ replicas, K8s HPA) | **Yes** | Shared CAS + streams + rolling windows |

Single-instance perpetual licenses run **production-grade** without Redis. Redis is the **scale profile**, not a license prerequisite.

---

## One environment block (copy-paste)

```bash
# .env.instpp or K8s ConfigMap (see deploy/k8s/configmap-instpp.yaml)
INST_REDIS_URL=redis://redis:6379/0
WEBHOOK_DISPATCH_MODE=redis
```

**TLS (managed Redis):**

```bash
INST_REDIS_URL=rediss://user:password@your-elasticache:6379/0
```

**Docker (local / staging):**

```bash
make redis-up
export INST_REDIS_URL=redis://127.0.0.1:6379/0
export WEBHOOK_DISPATCH_MODE=redis
```

Compose file: `docker-compose.instpp.yml` (profile `redis`).

---

## Per-SKU mapping

| # | SKU | `INST_REDIS_URL` enables | Prod notes |
|---|-----|--------------------------|------------|
| **2** | Proxy-Risk | Token bucket + idempotency CAS across replicas | Fail-closed on Redis error (no silent bypass) |
| **5** | Webhook Mesh | Durable delivery queue (`RedisStreamDeliveryQueue`) | Set `WEBHOOK_DISPATCH_MODE=redis`; background queue is dev-only |
| **6** | Ad Guard | Multi-instance idempotency | Same spine backends as Proxy |
| **7** | Health Telemetry | Optional HTTP batch idempotency (multi-instance ingress) | **Not required** single-instance; sequence gate is SQLite |
| **9** | Drift Gate | Shared rolling feature windows (`RedisRollingStateBackend`) | File state OK for single instance; Redis for enforce at scale |
| **11** | Spend Guard | Not required for wallet correctness | Wallet/ledger are SQLite or Postgres — Redis is not the spend source of truth |

**Not Redis-dependent for single instance:** #1, #3, #4, #7 (core path), #8, #10, #11, #12.

---

## Webhook Mesh production checklist

```bash
export WEBHOOK_PROVIDER_SECRET='<hmac-secret>'
export INST_REDIS_URL=redis://redis:6379/0
export WEBHOOK_DISPATCH_MODE=redis
webhook-mesh serve --port 8787
```

| Check | Expected |
|-------|----------|
| Ingress | WAL fsync before HTTP 200 |
| Idempotency | Duplicate `X-Webhook-Id` → `ALREADY_PROCESSED` |
| Delivery | `XADD` to Redis stream `inst:webhook:delivery` (not in-process only) |
| Consumer group | `webhook-workers` created on first enqueue |
| Crash recovery | `XAUTOCLAIM` reclaims stale pending messages |
| Optional capture | `WEBHOOK_REPLAY_CAPTURE_DIR=./data/captures` |

Rigorous proof: mocked Redis stream in `instpp_rigorous_test.sh` + `tests/test_industry_gold.py` + `tests/test_webhook_mesh_chaos.py`.

---

## Proxy-Risk + Drift Gate production checklist

```bash
export INST_REDIS_URL=redis://redis:6379/0
export PROXY_DRIFT_BASELINE=./baselines/model_v1.json   # optional hot-path drift
proxy-risk evaluate --client-id prod --method POST --path /infer --body '{"features":{...}}'
```

| Check | Expected |
|-------|----------|
| Idempotency | Same key rejected across pods |
| Rate limit | Shared token bucket (Lua CAS) |
| Drift rolling | `drift-gate evaluate` sees shared window when Redis key set |
| Redis down | **Fail-closed** — no silent in-memory fallback when URL set |

---

## Spend Guard + demo-gold (not a Redis profile)

Spend Guard reserve/settle uses **SQLite or Postgres wallet** — not Redis.

| Path | Proof |
|------|-------|
| CLI walkthrough | `make demo-gold` / `./scripts/demo_gold.sh` |
| Rigorous CI | `instpp_rigorous_test.sh` section **“Spend Guard — gold demo walkthrough”** |
| OpenAI-compat gateway | `spend-guard serve` + `SPEND_GUARD_API_KEY` (VPC boundary) |

Postgres HA wallet is a **design-partner profile** — see `docs/PRODUCTION_DEPLOYMENT.md`, not required for Redis scale.

---

## CI verification (GitHub Actions)

Workflow: `.github/workflows/instpp-ci.yml`

| Job | When | What it proves |
|-----|------|----------------|
| `smoke` | Every PR | 157+ (191+ on hardening branch) unit/integration |
| `redis-soak` | Push / dispatch | `tests/test_redis_soak.py` — idempotency + drift rolling (50 iter default) |
| `rigorous` | Push / dispatch | Full 12/12 E2E log + `demo_gold.sh` section |

**Local soak:**

```bash
export INST_REDIS_URL=redis://127.0.0.1:6379/0
make redis-soak                    # or ./scripts/instpp_redis_soak.sh
INST_REDIS_SOAK_ITERATIONS=200 make redis-soak
```

---

## Kubernetes quick reference

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/configmap-instpp.yaml
kubectl apply -f deploy/k8s/redis-deployment.yaml
kubectl apply -f deploy/k8s/inst-workflow-deployment.yaml
```

ConfigMap keys: `INST_REDIS_URL`, `WEBHOOK_DISPATCH_MODE`, `PORTFOLIO_DEMO_DIR`.  
See `docs/PRODUCTION_DEPLOYMENT.md` and `docs/PRODUCTION_RUNBOOK.md`.

---

## Fail-closed semantics

All Redis backends in `inst_spine.rates` and `webhook_mesh.queue`:

- **Redis unreachable** → idempotency / rate limit / delivery **errors** (not bypass)
- **No fallback to in-memory** when `INST_REDIS_URL` is set
- Tests: `tests/test_industry_gold.py`, `tests/test_redis_live.py`, `tests/test_redis_soak.py`

Implementation: `inst_spine.rates.RedisIdempotencyBackend`, `RedisTokenBucketBackend`, `RedisRollingStateBackend`; `webhook_mesh.queue.RedisStreamDeliveryQueue`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `idempotency: redis error` on Proxy | Redis down or ACL | Restore Redis; check `INST_REDIS_URL` |
| Duplicate webhooks delivered 2× | `WEBHOOK_DISPATCH_MODE=background` in prod | Set `WEBHOOK_DISPATCH_MODE=redis` |
| Drift windows diverge across pods | File-backed rolling state | Set `INST_REDIS_URL` + drift Redis key |
| `BUSYGROUP` in logs | Consumer group already exists | Benign on restart — queue handles |
| Soak test skipped locally | `INST_REDIS_URL` unset | `make redis-up` then export URL |
| CI smoke fails p99 forensic | Shared runner noise | `INST_P99_THRESHOLD_MS` raised on GHA automatically |

---

## Verification (5 minutes)

```bash
pip install -e ".[dev,instpp]"

# 1. Preflight (optional Redis ping)
./scripts/demo_ready.sh

# 2. With Redis running:
export INST_REDIS_URL=redis://127.0.0.1:6379/0
python3 -c "import redis; redis.from_url('$INST_REDIS_URL').ping()"

# 3. Soak (optional)
make redis-soak

# 4. Rigorous E2E (includes mocked Redis stream + demo_gold + full 12 SKUs)
./scripts/instpp_rigorous_test.sh
cat docs/test_logs/instpp_rigorous_latest_summary.json
```

Expected summary fields: `"status": "PASSED"`, `"industry_gold": true`, `"demo_gold": true`.

---

## HA notes (buyer-operated)

| Topic | Guidance |
|-------|----------|
| **Redis topology** | Buyer-managed — single primary, Sentinel, or Elasticache |
| **Secrets** | `WEBHOOK_PROVIDER_SECRET`, API keys — buyer vault; not in tarball |
| **Ledger durability** | SQLite + genesis WAL per product DB — not stored in Redis |
| **Backup** | Export `verify-bundle` tarballs + genesis anchors; Redis is ephemeral coordination |
| **Memory** | Size for stream depth + idempotency TTL; webhook DLQ on disk |

---

## Explicit non-goals

- Not a managed Redis SaaS from vendor
- Not Redis Cluster auto-provisioning in repo
- Postgres HA wallet (`make demo-gold` compose north star) — separate from this profile
- Not using Redis as compliance ledger or spend wallet store

---

## Related documents

- `docs/PRODUCTION_DEPLOYMENT.md` — K8s minimal / redis / postgres profiles
- `docs/PRODUCTION_RUNBOOK.md` — failure drills
- `docs/RUN_DEMO.md` — `make redis-up`, `make demo-gold`
- `docs/INST_PLUS_TEST_AND_DEMO.md` — env reference
- `docs/WEBHOOK_MESH_SALES_TECH_SPEC.md` — ingress + delivery
- `docs/PROXY_RISK_SALES_TECH_SPEC.md` — gate chain + Redis
- `docs/DRIFT_GATE_SALES_TECH_SPEC.md` — rolling state
- `docs/HEALTH_TELEMETRY_SALES_TECH_SPEC.md` — seq/WAL ingress (#7, not Redis-first)
- `.env.instpp.example` — commented production block
