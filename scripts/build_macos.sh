#!/usr/bin/env bash
#
# Build macOS .app bundle and .dmg for DBVisualizer.
#
# Usage:
#   chmod +x scripts/build_macos.sh
#   ./scripts/build_macos.sh
#
# Output:
#   dist/DBVisualizer.app
#   dist/DBVisualizer.dmg

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="DBVisualizer"
ENTRY="$ROOT/dbvisualizer/__main__.py"
ICON="$ROOT/assets/icon.icns"

# Ensure pyinstaller is available in uv venv
if ! uv run python -c "import PyInstaller" 2>/dev/null; then
    echo "Installing pyinstaller as dev dependency..."
    uv add --dev pyinstaller
fi

echo "=== Building $APP_NAME.app ==="

ICON_FLAG=()
if [[ -f "$ICON" ]]; then
    ICON_FLAG=(--icon "$ICON")
fi

uv run python -m PyInstaller \
    --name "$APP_NAME" \
    --noconfirm \
    --windowed \
    --collect-all gradio \
    --collect-all gradio_client \
    --collect-all safehttpx \
    --collect-all groovy \
    --collect-all matplotlib \
    --hidden-import natsort \
    --hidden-import seaborn \
    --hidden-import dbvisualizer \
    --hidden-import dbvisualizer.data \
    --hidden-import dbvisualizer.plot \
    --hidden-import dbvisualizer.ui \
    --distpath "$ROOT/dist" \
    --workpath "$ROOT/build" \
    --specpath "$ROOT/build" \
    "${ICON_FLAG[@]}" \
    "$ENTRY"

APP_PATH="$ROOT/dist/$APP_NAME.app"
DMG_PATH="$ROOT/dist/$APP_NAME.dmg"

if [[ ! -d "$APP_PATH" ]]; then
    # --onedir mode puts output in a folder, not .app; locate it
    APP_PATH="$ROOT/dist/$APP_NAME"
fi

echo ""
echo "=== Creating $APP_NAME.dmg ==="

# Remove old dmg if present
rm -f "$DMG_PATH"

# Create a temporary DMG directory
DMG_STAGING="$ROOT/build/dmg_staging"
rm -rf "$DMG_STAGING"
mkdir -p "$DMG_STAGING"

if [[ -d "$ROOT/dist/$APP_NAME.app" ]]; then
    cp -R "$ROOT/dist/$APP_NAME.app" "$DMG_STAGING/"
else
    # Fallback: copy the onedir folder
    cp -R "$ROOT/dist/$APP_NAME" "$DMG_STAGING/"
fi

# Create symlink to /Applications for drag-and-drop install
ln -s /Applications "$DMG_STAGING/Applications"

hdiutil create -volname "$APP_NAME" \
    -srcfolder "$DMG_STAGING" \
    -ov -format UDZO \
    "$DMG_PATH"

rm -rf "$DMG_STAGING"

echo ""
echo "Build complete:"
echo "  App: $ROOT/dist/$APP_NAME.app"
echo "  DMG: $DMG_PATH"
echo ""
echo "Run with:  open dist/$APP_NAME.app"
