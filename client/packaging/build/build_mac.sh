#!/usr/bin/env bash
# client/packaging/build/build_mac.sh
# Awesome Novel — macOS 一键构建 .app + DMG
#
# 用法:
#   ./build_mac.sh            → 构建 onedir .app + DMG（版本取 git describe）
#   ./build_mac.sh v1.2.3     → 指定版本号
#
# 前置: Node.js 20+, Python 3.12+, macOS（含 iconutil / hdiutil / codesign）
#
# 注意: 无 Apple Developer 证书时用 ad-hoc 签名(-)，仅够 arm64 本机执行；
#       分发到其他 Mac 需真证书 + notarization（见 docs 记录，留待后续）。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# HERE = <repo>/client/packaging/build → 上三级才是仓库根（../.. 只到 client/，脚本 [1/5] cd 会失败）
ROOT="$(cd "$HERE/../../.." && pwd)"
DIST_DIR="$HERE/dist"
STAGE="$HERE/.dmg_stage"

APP_VERSION="${1:-}"
if [[ -z "$APP_VERSION" ]]; then
  APP_VERSION="$(git -C "$ROOT" describe --tags --always --dirty 2>/dev/null || echo 0.0.0)"
fi
# 清洗为 DMG 文件名合法字符（分支名可能含 / 等）
APP_VERSION="$(printf '%s' "$APP_VERSION" | tr -c 'A-Za-z0-9._-' '-')"

echo "===== Awesome Novel Build v$APP_VERSION ====="

echo "[1/5] Building frontend..."
cd "$ROOT/client/frontend"
npm ci
npm run build

echo "[2/5] Installing backend deps..."
cd "$ROOT/client/backend"
python3 -m pip install -r requirements.txt

echo "[3/5] Installing packaging deps (pyinstaller/tinyaes)..."
python3 -m pip install -r "$HERE/requirements.txt"

echo "[4/5] PyInstaller → dist/AwesomeNovel.app..."
cd "$HERE"
rm -rf dist build_py
python3 -m PyInstaller build.spec --clean --noconfirm --workpath build_py

echo "[5/5] codesign + DMG..."
APP="$DIST_DIR/AwesomeNovel.app"
# arm64 必须签名才能执行；无证书用 ad-hoc（-）
codesign --force --deep --sign - "$APP"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
DMG="$DIST_DIR/AwesomeNovel_mac_$APP_VERSION.dmg"
rm -f "$DMG"
hdiutil create -volname "Awesome Novel" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

echo "[OK] Output: $DMG"
