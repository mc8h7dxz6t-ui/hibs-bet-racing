# Inst++ rigorous test logs (committed evidence)

```bash
./scripts/instpp_rigorous_test.sh
```

| Artifact | Description |
|----------|-------------|
| `instpp_rigorous_<UTC>.log` | Full timestamped run output |
| `instpp_rigorous_latest.log` | Symlink to latest log |
| `instpp_rigorous_latest_summary.json` | Machine-readable PASS/FAIL summary |

Latest archived passing run: see `instpp_rigorous_latest.log`.

Coverage: 40 unit tests + 20 E2E sections (Compliance ingest/F1–F9/export/verify-bundle/negatives + Proxy shadow/live/idempotency/kill/bench).
