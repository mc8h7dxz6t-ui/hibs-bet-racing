# hibs-bet in-play CTMC + FVE deploy patches

6 commits on top of `main`. Includes CTMC engine, I1–I5 evidence, FVE/CTMC installers.

## Mac — push branch to GitHub

```bash
cd ~/hibs-bet
git checkout main && git pull origin main
git checkout -b cursor/live-inplay-ctmc-engine-7e4d
git am ~/hibs-racing/docs/export-inplay-ctmc/*.patch
git push -u origin cursor/live-inplay-ctmc-engine-7e4d
```

## VPS — after merge or git am on server

**FVE box (77.68.89.75):**
```bash
curl -fsSL https://raw.githubusercontent.com/mc8h7dxz6t-ui/hibs-bet/main/deploy/ops-bootstrap-fve-vps.sh | sudo \
  HIBS_MAIN_IP=77.68.89.73 HIBS_UPSTREAM_BASE_URL=https://hibs-bet.co.uk bash
```

**Main VPS (77.68.89.73):**
```bash
cd /opt/hibs-bet && git pull   # or apply patches
sudo bash scripts/install_fve_inplay_evidence_stack.sh
```

**Verify:**
```bash
bash scripts/install_fve_lines_stack.sh --verify
bash scripts/score_inplay_institutional.sh    # target 96%
bash scripts/verify_inplay_evidence_gates.sh  # I1–I5 calendar
```
