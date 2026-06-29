# Institutional++ production deployment (K8s / VPC)

Deploy profiles for **single-tenant VPC** (default) and **multi-instance** (Redis).

## Profiles

| Profile | Use when | Components |
|---------|----------|------------|
| **minimal** | 1 pod, diligence / pilot | Proof Console, SQLite ledgers |
| **redis** | 2+ gateway/mesh replicas | + Redis 7 (CAS, streams, drift windows) |
| **postgres** | HA wallet / compliance ledger | + Postgres 16 (#1, #11) |

## Quick start (minimal)

```bash
make install
make plug                              # 12/12 offline proof
INST_WORKFLOW_DEFAULT_TAB=proof make demo-gold-up
# http://127.0.0.1:8790 — Proof Console → Bootstrap all 12 → Verify all 12
```

## Kubernetes (redis profile)

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/configmap-instpp.yaml
kubectl apply -f deploy/k8s/redis-deployment.yaml
kubectl apply -f deploy/k8s/inst-workflow-deployment.yaml
kubectl port-forward -n instpp svc/inst-workflow 8790:8790
```

Set in ConfigMap or env:

```bash
INST_REDIS_URL=redis://redis:6379/0
WEBHOOK_DISPATCH_MODE=redis
PORTFOLIO_DEMO_DIR=/data/demo/portfolio
INST_WORKFLOW_DEFAULT_TAB=proof
```

## Postgres profile (#1 Compliance, #11 Spend Guard)

```bash
export INST_COMPLIANCE_LEDGER_DSN=postgresql://user:pass@postgres:5432/compliance
export INST_SPEND_WALLET_DSN=postgresql://user:pass@postgres:5432/spend
export INST_SPEND_LEDGER_DSN=postgresql://user:pass@postgres:5432/spend_ledger

compliance-log ingest --database "$INST_COMPLIANCE_LEDGER_DSN" ...
spend-guard init-wallet --wallet-db "$INST_SPEND_WALLET_DSN" ...
```

Requires: `pip install -e ".[dev,instpp]"` (includes `psycopg`).

## Health probes

| Path | Use |
|------|-----|
| `GET /health` | Liveness — server up |
| `GET /ready` | Readiness — 12/12 portfolio DBs seeded |

Seed before readiness: `make demo-all` in init container, or **Bootstrap all 12** in Proof Console.

## Related

- [PRODUCTION_REDIS_PROFILE.md](PRODUCTION_REDIS_PROFILE.md) — per-SKU Redis mapping
- [PRODUCTION_RUNBOOK.md](PRODUCTION_RUNBOOK.md) — failure drills
- [RUN_DEMO.md](RUN_DEMO.md) — plug / demo / proof
