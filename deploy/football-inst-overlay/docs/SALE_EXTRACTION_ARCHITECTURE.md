# Sale extraction architecture

Four independent SKUs with HTTP-only integration. No shared SQLite reads across product boundaries.

## SKUs

| SKU | Repo | Install root | Port | Buyer gets |
|-----|------|--------------|------|------------|
| Football | `hibs-bet` | `/opt/hibs-bet` | 8000 | Predictions, CLV audit, evidence gates |
| Racing | `hibs-bet-racing` | `/opt/hibs-racing` | 5003 | Cards, paper ledger, R-gates |
| FVE / Lines | `football-app` | Docker on dedicated VPS | 8010 | Line shop, WS lines, scrape ingest |
| Trading | `hibs-bet` (`trading_core`) | `/opt/trading-core` | 9108/9109 | Shadow/paper execution (future standalone repo) |

## VPS layout (production reference)

| Host | Role | Block storage |
|------|------|---------------|
| `77.68.89.73` (2GB/80GB) | nginx, football, racing, trading, line-trader HTML shell | `/mnt/hibs-racing-data` — racing SQLite |
| `77.68.89.75` (1GB/10GB) | FVE only (`:8010`) | `/mnt/fve-data` — Docker volumes |

Main VPS nginx proxies `/line-trader` UI and upstream FVE API to the 1GB box (`FVE_UPSTREAM_HOST`).

## Integration rules

1. **HTTP only** — products expose `/api/health`, product-specific JSON APIs. No cross-repo file or DB access.
2. **Football must not read racing SQLite** — `racing_health_aggregator` is HTTP-only (`HIBS_RACING_BASE_URL/api/health?full=1`).
3. **Trading metrics stay localhost** — `/metrics` and `/ready` on `127.0.0.1` only; football dashboard links via env URL.
4. **Secrets per root** — football `.env`, racing `.env`, `/etc/trading_secrets`; never mixed.
5. **Tenant manifests** — `tenants/*.yaml` describe layout; secrets live on VPS after provision.

## Extraction checklist (per SKU)

- [x] Remove cross-SQLite reads from football (`racing_health_aggregator` → HTTP only)
- [ ] Document public API surface (`/api/health`, evidence endpoints)
- [ ] Standalone deploy script + systemd unit
- [ ] Whitelabel env vars only (no hard-coded partner strings)
- [ ] Evidence gates runnable without sibling products

## Deploy references

```bash
# Main stack sync
sudo HIBS_SYNC_REF=main bash /opt/hibs-bet/deploy/vps-sync-from-github.sh

# FVE remote upstream on main nginx
sudo FVE_REMOTE_HOST=77.68.89.75 bash /opt/hibs-bet/deploy/apply-vps-fve-remote-host.sh

# FVE dedicated box bootstrap
sudo bash /opt/hibs-bet/deploy/bootstrap-fve-dedicated-1gb.sh
```

See also: `docs/STACK_BOUNDARIES.md`, `docs/METRICS_UPGRADE_LADDER.md`, `tenants/production.yaml`.
