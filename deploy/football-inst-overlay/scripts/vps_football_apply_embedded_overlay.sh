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
