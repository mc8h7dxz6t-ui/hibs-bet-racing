# hibs-bet in-play CTMC branch export

Cloud agent branch `cursor/live-inplay-ctmc-engine-7e4d` (5 commits on top of `main` @ 596f68c).

Apply on your Mac:

```bash
cd ~/hibs-bet
git checkout main
git pull origin main
git checkout -b cursor/live-inplay-ctmc-engine-7e4d
git am ~/hibs-racing/exports/hibs-bet-inplay-ctmc/*.patch
git push -u origin cursor/live-inplay-ctmc-engine-7e4d
```

If `git am` fails, abort with `git am --abort` and report the conflict.

After push, open a PR on GitHub or merge to main.
