# Four-stack automation patch (hibs-bet)

Arms hands-off repair for Football · Racing · Trading · Line shopper on consolidated VPS.

## Mac

```bash
cd ~/hibs-bet && git pull origin main
git am ~/hibs-racing/docs/export-four-stack-automation/*.patch
git push origin main   # or your branch
```

## VPS (87.106.100.52) — one command after patch/sync

```bash
ssh root@87.106.100.52
sudo HIBS_VPS_IP=87.106.100.52 bash /opt/hibs-bet/scripts/install_four_stack_automation.sh
```

Or from Mac:

```bash
DEPLOY_HOST=87.106.100.52 ./scripts/install_four_stack_automation.sh --remote
```
