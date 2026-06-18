#!/usr/bin/env bash
# Mac launchd — observation catch-up on wake + hourly 6–11 (sleep-safe).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CATCHUP="${SCRIPT_DIR}/observation_catchup.sh"
LABEL="com.hibs.racing.observation-catchup"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

chmod +x "${CATCHUP}" "${SCRIPT_DIR}/daily_refresh.sh" 2>/dev/null || true
mkdir -p "${ROOT}/logs" "${HOME}/Library/LaunchAgents"

cat >"${PLIST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${CATCHUP}</string>
  </array>
  <key>StartInterval</key>
  <integer>3600</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${ROOT}/logs/observation_catchup.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT}/logs/observation_catchup.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HIBS_OBSERVATION_LANE</key>
    <string>1</string>
  </dict>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "${PLIST}" 2>/dev/null || launchctl load "${PLIST}" 2>/dev/null || true

echo "Installed launchd catch-up: ${PLIST}"
echo "Runs hourly + on login; skips if today's refresh already OK."
echo "Logs: ${ROOT}/logs/observation_catchup.log"
