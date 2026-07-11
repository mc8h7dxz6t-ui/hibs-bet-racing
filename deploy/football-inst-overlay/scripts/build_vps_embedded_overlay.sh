#!/usr/bin/env python3
"""Build vps_football_apply_embedded_overlay.sh from overlay templates (no network on VPS)."""
from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "templates/_hibs_brand.html",
    "templates/_launch_wait_overlay.html",
    "templates/_portfolio_bar.html",
    "templates/_term_hint.html",
    "templates/_site_ops_chips.html",
    "templates/_inst_grade_chip.html",
    "templates/_players_dock.html",
    "templates/_betslip_drawer.html",
    "templates/_fixture_row_compact.html",
    "templates/_dashboard_logged_results.html",
    "templates/_dashboard_recent_results.html",
    "templates/_betting_guide.html",
    "templates/_assistant_widget.html",
    "templates/_football_site_nav.html",
    "templates/login.html",
    "src/hibs_predictor/web_format.py",
]

buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    for rel in FILES:
        tar.add(ROOT / rel, arcname=rel)
payload = base64.b64encode(buf.getvalue()).decode("ascii")

OUT = ROOT / "scripts" / "vps_football_apply_embedded_overlay.sh"
script = f'''#!/usr/bin/env bash
# Apply embedded football overlay bundle — NO git, NO GitHub curl (private repo safe).
#
#   sudo bash /opt/hibs-bet/scripts/vps_football_apply_embedded_overlay.sh
set -euo pipefail

BET="${{DEPLOY_PATH:-/opt/hibs-bet}}"
[[ "$(id -u)" -eq 0 ]] || {{ echo "run as root: sudo bash $0" >&2; exit 1; }}
[[ -d "${{BET}}" ]] || {{ echo "missing ${{BET}}" >&2; exit 1; }}

TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="${{BET}}/.cache/overlay-bak-${{TS}}"
mkdir -p "${{BACKUP}}"

echo "[embedded-overlay] extracting bundle ($(date -u +%H:%M:%S))"
"${{BET}}/.venv/bin/python3" - "${{BET}}" "${{BACKUP}}" <<'PY'
import base64, io, pathlib, shutil, sys, tarfile

bet = pathlib.Path(sys.argv[1])
backup = pathlib.Path(sys.argv[2])
data = base64.b64decode("""{payload}""")
with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
    for member in tar.getmembers():
        if not member.isfile():
            continue
        dest = bet / member.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file():
            shutil.copy2(dest, backup / member.name.replace("/", "__"))
        extracted = tar.extractfile(member)
        if extracted is None:
            continue
        dest.write_bytes(extracted.read())
        print("wrote", member.name)
PY

WEB="${{BET}}/src/hibs_predictor/web.py"
"${{BET}}/.venv/bin/python3" - "$WEB" <<'PY'
import pathlib, re, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text()
filters = ("fmt_num", "fmt_pct", "fmt_prob", "fmt_odds", "fmt_roi")
missing = [n for n in filters if f"add_template_filter({{n}}" not in text]
if not missing:
    print("filters OK")
    sys.exit(0)
imp = "from hibs_predictor.web_format import fmt_num, fmt_odds, fmt_pct, fmt_prob, fmt_roi"
if "from hibs_predictor.web_format import" in text:
    text = re.sub(r"from hibs_predictor\\.web_format import[^\\n]+", imp, text, count=1)
else:
    needle = "return str(rank) if rank is not None else str(value or \\'\\')"
    idx = text.find(needle)
    end = text.find("\\n\\n", idx) + 2
    block = "\\n" + imp + "\\n\\n" + "".join(f'app.add_template_filter({{n}}, "{{n}}")\\n' for n in filters) + "\\n"
    text = text[:end] + block + text[end:]
for n in missing:
    if f"add_template_filter({{n}}" not in text:
        p = text.rfind("app.add_template_filter(")
        e = text.find("\\n", p)
        text = text[: e + 1] + f'app.add_template_filter({{n}}, "{{n}}")\\n' + text[e + 1 :]
path.write_text(text)
print("registered:", ", ".join(missing))
PY

if grep -q expand_panel "${{BET}}/templates/_fixture_row_compact.html" 2>/dev/null; then
  echo "WARN: expand panel still referenced"
else
  echo "OK: compact fixture row"
fi

chown -R www-data:www-data "${{BET}}/templates" "${{BET}}/src/hibs_predictor/web_format.py" "${{BET}}/src/hibs_predictor/web.py"
rm -f "${{BET}}/.cache"/dashboard_page_* 2>/dev/null || true
systemctl restart hibs-bet
sleep 6
for i in 1 2 3; do
  curl -sS -o /dev/null -w "try${{i}} ping=%{{http_code}} root=%{{http_code}}\\n" \\
    http://127.0.0.1:8000/api/ping http://127.0.0.1:8000/ || true
  sleep 2
done
echo "Backup: ${{BACKUP}}"
'''
OUT.write_text(script, encoding="utf-8")
OUT.chmod(0o755)
print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
