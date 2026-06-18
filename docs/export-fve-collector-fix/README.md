# FVE lines collector fix (scrapers ModuleNotFoundError)

Apply on hibs-bet when `--from-watchlist` fails inside FVE Docker:

```bash
cd /opt/hibs-bet
git fetch origin
git checkout cursor/fix-fve-collector-fixtures-7e4d   # after merge
# or:
git am /path/to/0001-fix-fve-use-hibs-fixtures-API-for-lines-collector-in.patch
```

Immediate VPS workaround (no git):

```bash
# 1. Replace broken cron (host python + --from-watchlist)
( crontab -l 2>/dev/null | grep -vE 'fve_hibs_lines_collector|from-watchlist' || true ) | crontab -

# 2. Run collector via docker with hibs fixture keys (skips if count=0)
FIX=$(curl -sS http://127.0.0.1:8000/api/fve/fixtures | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(','.join(x['fixture_key'] for x in (d.get('fixtures') or [])[:20] if x.get('fixture_key')))
")
if [[ -n "$FIX" ]]; then
  cd /opt/fve
  docker compose exec -T worker python scripts/fve_hibs_lines_collector.py --fixtures "$FIX"
else
  echo "fixtures count=0 — copy .cache from old VPS or wait for API quota reset"
fi
```

Root blocker when `count=0`: warm football fixture disk cache (see four-stack migration notes).
