#!/usr/bin/env bash
# Apply embedded football overlay bundle — NO git, NO GitHub curl (private repo safe).
#
#   sudo bash /opt/hibs-bet/scripts/vps_football_apply_embedded_overlay.sh
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }
[[ -d "${BET}" ]] || { echo "missing ${BET}" >&2; exit 1; }

TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="${BET}/.cache/overlay-bak-${TS}"
mkdir -p "${BACKUP}"

echo "[embedded-overlay] extracting bundle ($(date -u +%H:%M:%S))"
"${BET}/.venv/bin/python3" - "${BET}" "${BACKUP}" <<'PY'
import base64, io, pathlib, shutil, sys, tarfile

bet = pathlib.Path(sys.argv[1])
backup = pathlib.Path(sys.argv[2])
data = base64.b64decode("""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""")
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

WEB="${BET}/src/hibs_predictor/web.py"
"${BET}/.venv/bin/python3" - "$WEB" <<'PY'
import pathlib, re, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text()
filters = ("fmt_num", "fmt_pct", "fmt_prob", "fmt_odds", "fmt_roi")
missing = [n for n in filters if f"add_template_filter({n}" not in text]
if not missing:
    print("filters OK")
    sys.exit(0)
imp = "from hibs_predictor.web_format import fmt_num, fmt_odds, fmt_pct, fmt_prob, fmt_roi"
if "from hibs_predictor.web_format import" in text:
    text = re.sub(r"from hibs_predictor\.web_format import[^\n]+", imp, text, count=1)
else:
    needle = "return str(rank) if rank is not None else str(value or \'\')"
    idx = text.find(needle)
    end = text.find("\n\n", idx) + 2
    block = "\n" + imp + "\n\n" + "".join(f'app.add_template_filter({n}, "{n}")\n' for n in filters) + "\n"
    text = text[:end] + block + text[end:]
for n in missing:
    if f"add_template_filter({n}" not in text:
        p = text.rfind("app.add_template_filter(")
        e = text.find("\n", p)
        text = text[: e + 1] + f'app.add_template_filter({n}, "{n}")\n' + text[e + 1 :]
path.write_text(text)
print("registered:", ", ".join(missing))
PY

if grep -q expand_panel "${BET}/templates/_fixture_row_compact.html" 2>/dev/null; then
  echo "WARN: expand panel still referenced"
else
  echo "OK: compact fixture row"
fi

chown -R www-data:www-data "${BET}/templates" "${BET}/src/hibs_predictor/web_format.py" "${BET}/src/hibs_predictor/web.py"
rm -f "${BET}/.cache"/dashboard_page_* 2>/dev/null || true
systemctl restart hibs-bet
sleep 6
for i in 1 2 3; do
  curl -sS -o /dev/null -w "try${i} ping=%{http_code} root=%{http_code}\n" \
    http://127.0.0.1:8000/api/ping http://127.0.0.1:8000/ || true
  sleep 2
done
echo "Backup: ${BACKUP}"
