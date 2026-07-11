# Institutional test logs (committed evidence)

```bash
./scripts/instpp_smoke_test.sh
./scripts/instpp_proof_lite.sh      # PR diligence
./scripts/instpp_rigorous_test.sh   # full E2E
make proof                            # smoke + rigorous + verify-portfolio
```

| Artifact | Description |
|----------|-------------|
| `instpp_rigorous_<UTC>.log` | Full timestamped rigorous run output |
| `instpp_rigorous_latest.log` | Symlink to latest rigorous log |
| `instpp_rigorous_latest_summary.json` | Rigorous PASS/FAIL summary (`skipped_sections`, waves) |
| `instpp_proof_lite_latest_summary.json` | PR proof-lite summary (profile gates + 12/12 verify) |
| `instpp_ci_autonomy_phases.json` | Phase 1.1–1.4 + Phase 2.1–2.12 + Phase 3.1–3.20 implementation ledger |
| `soc2_evidence_latest.json` | SOC2 VPC evidence from `PORTFOLIO_MANIFEST.json` |

## CI autonomy phases (SKU only)

`instpp_ci_autonomy_phases.json` is rewritten on each `proof-lite` or `rigorous` run by `scripts/instpp_ci_autonomy_log.py`. It records:

- Phase checklist (1.1–1.4 smoke/rigorous honesty, 2.1–2.12 production envelope, 3.1–3.20 buyer depth)
- Last run metadata (commit, branch, skipped sections, Redis/Postgres env presence)
- Pointers to summary artifacts

```bash
cat docs/test_logs/instpp_ci_autonomy_phases.json
cat docs/test_logs/instpp_proof_lite_latest_summary.json
cat docs/test_logs/instpp_rigorous_latest_summary.json
```

Latest archived passing rigorous run: see `instpp_rigorous_latest.log`.

Coverage: institutional unit suite + rigorous E2E across 12 SKUs (Compliance through Agent Ledger).

See `docs/INST_PLUS_GOLD_STANDARD.md` for dimension definitions.
