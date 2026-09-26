#!/usr/bin/env bash
# Membuat paket portable Windows: dist/RE-Baru-Portable(.zip)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"; PKG="$DIST/RE-Baru-Portable"; DL="$DIST/dl"; WHEELS="$DIST/wheels"
PY_VER="${PY_VER:-3.11.9}"; MONGO_VER="${MONGO_VER:-7.0.14}"
mkdir -p "$DL" "$WHEELS"

echo "[1/7] Unduh runtime (dilewati jika sudah ada)..."
[ -f "$DL/python-embed.zip" ] || curl -L -o "$DL/python-embed.zip" "https://www.python.org/ftp/python/$PY_VER/python-$PY_VER-embed-amd64.zip"
[ -f "$DL/mongodb.zip" ] || curl -L -o "$DL/mongodb.zip" "https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-$MONGO_VER.zip"
[ -f "$DL/vc_redist.x64.exe" ] || curl -L -o "$DL/vc_redist.x64.exe" "https://aka.ms/vs/17/release/vc_redist.x64.exe"

echo "[2/7] Unduh wheel Windows untuk dependency backend..."
pip download -q --platform win_amd64 --python-version 3.11 --only-binary=:all: --implementation cp \
  -d "$WHEELS" -r "$ROOT/backend/requirements-portable.txt"

echo "[3/7] Susun struktur folder..."
rm -rf "$PKG"
mkdir -p "$PKG"/{runtime/python,runtime/mongodb,runtime/vcredist,app/backend,app/frontend_build,data/db,data/galeri,backup}
rsync -a --exclude tests --exclude __pycache__ --exclude local_storage --exclude backups \
  --exclude '.env' --exclude pytest.ini --exclude requirements.txt "$ROOT/backend/" "$PKG/app/backend/"
cp "$ROOT/portable/env.portable" "$PKG/app/backend/.env"
cp "$ROOT/portable/JALANKAN_APLIKASI.bat" "$ROOT/portable/PANDUAN.md" "$PKG/"
printf 'Folder ini berisi DATABASE aplikasi. Jangan mengubah/menghapus isinya secara manual.\r\n' > "$PKG/data/BACA_SAYA.txt"
printf 'File backup .zip otomatis & manual. Salin ke komputer lain secara berkala.\r\n' > "$PKG/backup/BACA_SAYA.txt"

echo "[4/7] Build frontend (mode offline, same-origin)..."
cd "$ROOT/frontend"
cp public/index.html /tmp/index.html.online
trap 'cp /tmp/index.html.online "$ROOT/frontend/public/index.html"' EXIT
cp public/index.offline.html public/index.html
REACT_APP_BACKEND_URL= BUILD_PATH="$PKG/app/frontend_build" GENERATE_SOURCEMAP=false DISABLE_ESLINT_PLUGIN=true \
  DISABLE_EMERGENT_OVERLAY=true yarn -s build
cp /tmp/index.html.online public/index.html
rm -f "$PKG/app/frontend_build/index.offline.html"

echo "[5/7] Python embeddable + library..."
cd "$PKG/runtime/python"
unzip -q "$DL/python-embed.zip"
PTH="$(ls python3*._pth)"
printf 'python311.zip\n.\nLib\\site-packages\nimport site\n' > "$PTH"
mkdir -p Lib/site-packages
pip install -q --no-deps --no-index --find-links "$WHEELS" --target Lib/site-packages \
  --platform win_amd64 --python-version 3.11 --only-binary=:all: --implementation cp "$WHEELS"/*.whl
find Lib/site-packages -type d -name "__pycache__" -prune -exec rm -rf {} +

echo "[6/7] mongod.exe + VC++ redist..."
rm -rf "$DIST/mongo_extract"
unzip -q -o "$DL/mongodb.zip" 'mongodb-win*/bin/mongod.exe' -d "$DIST/mongo_extract"
cp "$DIST"/mongo_extract/*/bin/mongod.exe "$PKG/runtime/mongodb/"
cp "$DL/vc_redist.x64.exe" "$PKG/runtime/vcredist/"

echo "[7/7] Zip paket..."
cd "$DIST" && rm -f RE-Baru-Portable.zip && zip -qr RE-Baru-Portable.zip RE-Baru-Portable
du -sh "$PKG" RE-Baru-Portable.zip
echo "SELESAI: $DIST/RE-Baru-Portable.zip"
