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
