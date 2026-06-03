#!/bin/bash
# Install HIBS Racing.app on Desktop (macOS).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="HIBS Racing"
INSTALL_TO="${1:-$HOME/Desktop}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer builds a macOS .app bundle. On Linux, run:"
  echo "  bash scripts/hibs-racing-desktop-launch.sh"
  exit 1
fi

APP_DIR="${INSTALL_TO%/}/${APP_NAME}.app"
LAUNCH_SH="${ROOT}/scripts/hibs-racing-desktop-launch.sh"
ICON_SRC="${ROOT}/static/logo_hibs_racing.svg"
# Optional shared crest (football repo) if present
ALT_ICON="${HOME}/Applications/static/hibs_harvested_logo.png"
if [[ -f "${ALT_ICON}" ]]; then
  ICON_SRC="${ALT_ICON}"
fi

mkdir -p "${APP_DIR}/Contents/MacOS" "${APP_DIR}/Contents/Resources"
chmod +x "${LAUNCH_SH}"

cat > "${APP_DIR}/Contents/MacOS/launch" << EOF
#!/bin/bash
exec "${LAUNCH_SH}"
EOF
chmod +x "${APP_DIR}/Contents/MacOS/launch"

cat > "${APP_DIR}/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en-GB</string>
  <key>CFBundleExecutable</key>
  <string>launch</string>
  <key>CFBundleIdentifier</key>
  <string>uk.co.hibs-bet.racing</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>HIBS Racing</string>
  <key>CFBundleDisplayName</key>
  <string>HIBS Racing</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>11.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

if [[ -f "${ICON_SRC}" && "${ICON_SRC}" == *.png ]]; then
  ICONSET="${APP_DIR}/Contents/Resources/AppIcon.iconset"
  mkdir -p "${ICONSET}"
  sips -z 16 16     "${ICON_SRC}" --out "${ICONSET}/icon_16x16.png" >/dev/null 2>&1 || true
  sips -z 32 32     "${ICON_SRC}" --out "${ICONSET}/icon_16x16@2x.png" >/dev/null 2>&1 || true
  sips -z 32 32     "${ICON_SRC}" --out "${ICONSET}/icon_32x32.png" >/dev/null 2>&1 || true
  sips -z 64 64     "${ICON_SRC}" --out "${ICONSET}/icon_32x32@2x.png" >/dev/null 2>&1 || true
  sips -z 128 128   "${ICON_SRC}" --out "${ICONSET}/icon_128x128.png" >/dev/null 2>&1 || true
  sips -z 256 256   "${ICON_SRC}" --out "${ICONSET}/icon_128x128@2x.png" >/dev/null 2>&1 || true
  sips -z 256 256   "${ICON_SRC}" --out "${ICONSET}/icon_256x256.png" >/dev/null 2>&1 || true
  sips -z 512 512   "${ICON_SRC}" --out "${ICONSET}/icon_256x256@2x.png" >/dev/null 2>&1 || true
  sips -z 512 512   "${ICON_SRC}" --out "${ICONSET}/icon_512x512.png" >/dev/null 2>&1 || true
  sips -z 1024 1024 "${ICON_SRC}" --out "${ICONSET}/icon_512x512@2x.png" >/dev/null 2>&1 || true
  if iconutil -c icns "${ICONSET}" -o "${APP_DIR}/Contents/Resources/AppIcon.icns" 2>/dev/null; then
    /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" "${APP_DIR}/Contents/Info.plist" 2>/dev/null \
      || /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile AppIcon" "${APP_DIR}/Contents/Info.plist" 2>/dev/null || true
    rm -rf "${ICONSET}"
  fi
fi

echo "Installed: ${APP_DIR}"
echo "  → starts local dashboard at http://127.0.0.1:5003 (needs .venv + .env)"
echo "Drag to the Dock to pin."
