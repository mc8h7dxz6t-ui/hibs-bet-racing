# Production Redis Profile — Multi-Instance VPC

**Purpose:** One-page procurement guide for horizontal scale on `inst_spine` SKUs.  
**Audience:** Platform engineering, InfoSec, SRE deploying 2+ gateway/mesh workers.

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
# .env.instpp or K8s ConfigMap
INST_REDIS_URL=redis://redis:6379/0
WEBHOOK_DISPATCH_MODE=redis
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
| **9** | Drift Gate | Shared rolling feature windows (`RedisRollingStateBackend`) | File state OK for single instance; Redis for enforce at scale |

**Not Redis-dependent for single instance:** #1, #3, #4, #7, #8, #10, #11, #12.

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
| Delivery | `XADD` to Redis stream (not in-process only) |
| Optional capture | `WEBHOOK_REPLAY_CAPTURE_DIR=./data/captures` |

Rigorous proof: mocked Redis stream in `instpp_rigorous_test.sh` + `tests/test_industry_gold.py`.

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
| Rate limit | Shared token bucket |
| Drift rolling | `drift-gate evaluate` sees shared window when Redis key set |

---

## Fail-closed semantics

All Redis backends in `inst_spine.rates` and `webhook_mesh.queue`:

- **Redis unreachable** → idempotency / rate limit / delivery **errors** (not bypass)
- **No fallback to in-memory** when `INST_REDIS_URL` is set
- Tests: `tests/test_industry_gold.py` (Redis stream integration)

---

## Verification (5 minutes)

```bash
pip install -e ".[dev,instpp]"

# 1. Preflight (optional Redis ping)
./scripts/demo_ready.sh

# 2. With Redis running:
export INST_REDIS_URL=redis://127.0.0.1:6379/0
python3 -c "import redis; redis.from_url('$INST_REDIS_URL').ping()"

# 3. Rigorous E2E (includes mocked Redis stream + full 12 SKUs)
./scripts/instpp_rigorous_test.sh
cat docs/test_logs/instpp_rigorous_latest_summary.json
```

---

## HA notes (buyer-operated)

| Topic | Guidance |
|-------|----------|
| **Redis topology** | Buyer-managed — single primary, Sentinel, or Elasticache |
| **Secrets** | `WEBHOOK_PROVIDER_SECRET`, API keys — buyer vault; not in tarball |
| **Ledger durability** | SQLite + genesis WAL per product DB — not stored in Redis |
| **Backup** | Export `verify-bundle` tarballs + genesis anchors; Redis is ephemeral coordination |

---

## Explicit non-goals

- Not a managed Redis SaaS from vendor
- Not Redis Cluster auto-provisioning in repo
- Postgres HA wallet (`make demo-gold` compose north star) — separate from this profile

---

## Related documents

- `docs/RUN_DEMO.md` — `make redis-up`
- `docs/INST_PLUS_TEST_AND_DEMO.md` — env reference
- `docs/WEBHOOK_MESH_SALES_TECH_SPEC.md` — ingress + delivery
- `docs/PROXY_RISK_SALES_TECH_SPEC.md` — gate chain + Redis
- `docs/DRIFT_GATE_SALES_TECH_SPEC.md` — rolling state
- `.env.instpp.example` — commented production block
