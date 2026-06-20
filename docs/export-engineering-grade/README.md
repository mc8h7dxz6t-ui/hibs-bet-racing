# Engineering grade A — VPS one-shot

Apply on consolidated VPS (`87.106.100.52` or any `/opt/hibs-bet` host):

```bash
cd /opt/hibs-bet
# Copy from this export if not yet on main:
#   scp docs/export-engineering-grade/*.sh root@87.106.100.52:/tmp/
#   cp /tmp/apply-vps-engineering-grade-a.sh deploy/
#   cp /tmp/verify_engineering_grade_a.sh scripts/

sudo bash deploy/apply-vps-engineering-grade-a.sh
bash scripts/verify_engineering_grade_a.sh
```

## What engineering A requires (code: `institutional_readiness.py`)

| Check | Fix |
|-------|-----|
| Zero `blocking_issues` | `HIBS_PRODUCTION=1`, audit on, no `HIBS_DEV_FULL_DQ` |
| Zero `warnings` | Auth on + password, CLV on, full trial `HIBS_VALUE_LEAGUES`, `HIBS_SHARPEN_GATES=1`, `calibration_v1.json` exists |
| Not B+ | Any single warning keeps you at **B+**; need **zero** warnings for **A** |

## Evidence / institutional grade (separate, calendar-bound)

| Grade | Meaning |
|-------|---------|
| **F1–F3** | Audit + CLV + cron — instant after `apply-vps-engineering-grade-a.sh` |
| **F7** | ≥3 matchdays + 50% 7d 1X2 capture — needs fixtures + dashboard/cron seeds |
| **F8–F9** | CLV n≥25 + beat-close ≥50% — needs finished matches + `pred-log-sync` |
| **buyer_ready** | All F gates pass → evidence **A** |
| **inst_pp_tier** | `institutional_engineering` when eng A/B+ + automation OK; `institutional_ready` when `buyer_ready` + nine-ten ≥8.5 |

```bash
# After fixtures are flowing:
bash scripts/green_forward_evidence.sh --seed
bash scripts/verify_inst_pp_automation.sh
curl -sS 'https://hibs-bet.co.uk/api/health?light=1' | python3 -c "
import json,sys; d=json.load(sys.stdin); ir=d.get('institutional_readiness') or {}
print('engineering:', ir.get('engineering_grade'))
print('evidence:', ir.get('evidence_grade'))
print('buyer_ready:', ir.get('buyer_ready'))
"
```

## Blocker on `.52` today

Fixtures = 0 blocks FVE and snapshot seeding. Unblock first:

```bash
# FOOTBALL_DATA_ORG_KEY in .env, then:
systemctl restart hibs-bet
sudo -u www-data HOME=/opt/hibs-bet PYTHONPATH=src .venv/bin/python3 scripts/warm_football_fixtures.py
```

Then re-run engineering-grade apply + `green_forward_evidence.sh --seed`.
