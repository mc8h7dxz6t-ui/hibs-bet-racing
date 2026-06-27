# Production Runbook — Institutional++

Fail-closed drills for VPC operators. Pair with [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md).

## Redis unavailable (multi-instance)

**Symptoms:** Proxy idempotency bypass risk; Webhook Mesh background dispatch stops; Drift Gate file-only windows diverge.

**Expected:** Fail-closed — gates reject or queue, no silent dedupe loss.

**Drill:**

```bash
# Stop Redis
docker stop instpp-redis || kubectl scale -n instpp deploy/redis --replicas=0

# Proxy should reject duplicate keys fail-closed (see tests/test_redis_live.py)
INST_REDIS_URL=redis://127.0.0.1:9 pytest tests/test_redis_live.py -q

# Restore
make redis-up
```

## Portfolio not ready (Proof Console)

**Symptoms:** `/ready` returns `ok: false`; Proof Console shows "(no DB)".

**Fix:**

```bash
make demo-all
# or in UI: Bootstrap all 12
# or: curl -X POST http://127.0.0.1:8790/api/proof/bootstrap-all
```

## Disk full / SQLite locked

**Symptoms:** `unable to open database file`; `database is locked`.

**Fix:**

1. Free disk on volume mount (`data/demo/portfolio`, WAL dirs).
2. `ulimit -n 4096` on macOS before rigorous suite.
3. Single writer per ledger path — do not share SQLite across pods without Postgres profile.

## Spend wallet drift lockout

**Symptoms:** `DRIFT_THRESHOLD_EXCEEDED`; reserves return `locked`.

**Fix:**

```bash
make demo-gold-reset
# or spend-guard CLI unlock after operator review (production: manual unlock policy)
```

## Postgres failover (#1, #11)

**Symptoms:** Connection errors to `INST_*_DSN`.

**Expected:** WAL files under `INST_LEDGER_WAL_DIR` retain crash-safe tail; replay on reconnect.

**Drill:** `pytest tests/test_postgres_profile.py` (requires `INST_TEST_POSTGRES_DSN`).

## Evidence after incident

```bash
make rigorous
./scripts/verify_portfolio.sh
# Attach docs/test_logs/instpp_rigorous_latest_summary.json to incident record
```
