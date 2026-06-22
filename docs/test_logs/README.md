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

Coverage: 45 unit tests + 20 E2E sections (Compliance + Proxy-Risk gold standard).

See `docs/INST_PLUS_GOLD_STANDARD.md` for dimension definitions.
