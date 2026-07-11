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
