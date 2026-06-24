# Spend Guard — Real-Time API Spend Boundary Enforcer

Reserve-before-dispatch wallet with drift lockout and genesis audit.

## One job

Hold budget before API calls clear; settle on actual cost; lock wallet on spend drift.

## Quick start

```bash
pip install -e ".[dev,instpp]"

spend-guard init-wallet --wallet-db data/demo/spend_wallet.sqlite --balance 1000

spend-guard reserve --request-id req-1 --cost 50 \
  --wallet-db data/demo/spend_wallet.sqlite --ledger-db data/demo/spend_guard.sqlite

spend-guard settle --hold-id <hold_id> --request-id req-1 --actual-cost 48 \
  --wallet-db data/demo/spend_wallet.sqlite --ledger-db data/demo/spend_guard.sqlite

spend-guard demo-drift-lock --wallet-db data/demo/spend_wallet.sqlite \
  --ledger-db data/demo/spend_guard.sqlite

spend-guard export --database data/demo/spend_guard.sqlite --tarball data/demo/spend_guard_bundle.tar
spend-guard verify-bundle --tarball data/demo/spend_guard_bundle.tar
```

## Integration

```python
from spend_guard.integrate import reserve_api_call, settle_api_call

r = reserve_api_call(request_id="x", estimated_cost=0.05, wallet_db=Path("wallet.sqlite"))
# ... upstream LLM call ...
settle_api_call(hold_id=r["hold_id"], actual_cost=0.04, request_id="x", wallet_db=Path("wallet.sqlite"))
```

## Non-goals

- Not a full LiteLLM/Portkey proxy (pairs with them)
- Not multi-currency treasury
- Not Postgres HA (SQLite VPC default; Postgres adapter = design partner SOW)
