# FVE collector fix

**Cause:** `scrapers` exists in `/opt/fve/scrapers` (inside the Docker image). Python adds `/app/scripts` to `sys.path` when you run `python scripts/fve_hibs_lines_collector.py`, so `import scrapers` fails unless `PYTHONPATH=/app`.

**Quickest fix on VPS** (paste as root):

```bash
cd /opt/fve
FIX=$(curl -sS http://127.0.0.1:8000/api/fve/fixtures | python3 -c "import json,sys; d=json.load(sys.stdin); print(','.join(x['fixture_key'] for x in (d.get('fixtures') or [])[:30] if x.get('fixture_key')))")
if [[ -n "$FIX" ]]; then
  docker compose exec -T -w /app worker env PYTHONPATH=/app python scripts/fve_hibs_lines_collector.py --fixtures "$FIX"
else
  docker compose exec -T -w /app worker env PYTHONPATH=/app python scripts/fve_hibs_lines_collector.py --from-watchlist
fi
curl -sS http://127.0.0.1:8010/health | python3 -m json.tool | head -20
```

Replace broken cron:

```bash
( crontab -l 2>/dev/null | grep -vE 'fve_hibs_lines_collector|from-watchlist' || true
  echo '*/5 * * * * HIBS_UPSTREAM_BASE_URL=http://127.0.0.1:8000 bash /opt/hibs-bet/scripts/run_fve_lines_collector.sh >> /var/log/fve/lines-collector.log 2>&1'
) | crontab -
```

Copy `scripts/run_fve_lines_collector.sh` from hibs-bet if missing on VPS.
