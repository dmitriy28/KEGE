#!/usr/bin/env bash
# Сборка KEGE Station для Ubuntu 26.04 LTS (amd64/arm64): переносимый tar.gz и пакет .deb.
# Использование: ./build_linux.sh            — собрать всё в dist/
#                SKIP_DEB=1 ./build_linux.sh — только tar.gz
set -euo pipefail
cd "$(dirname "$0")"

VERSION="$(python3 -c 'import re,pathlib;print(re.search(r"__version__ = \"([^\"]+)\"",pathlib.Path("kege_app/__init__.py").read_text()).group(1))')"
ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
NAME="kege-station"

[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-build.txt

rm -rf build dist
python -m PyInstaller --noconfirm --clean --windowed \
  --name KEGE_Station \
  --add-data "assets:assets" \
  --add-data "examples:examples" \
  run.py

mkdir -p dist/release
TAR="dist/release/${NAME}_${VERSION}_linux_${ARCH}.tar.gz"
tar -C dist -czf "$TAR" KEGE_Station
echo "Архив: $TAR"

if [ -z "${SKIP_DEB:-}" ]; then
  command -v dpkg-deb >/dev/null || { echo "dpkg-deb не найден (sudo apt install dpkg-dev)"; exit 1; }
  PKG="dist/deb/${NAME}_${VERSION}_${ARCH}"
  rm -rf "$PKG"
  mkdir -p "$PKG/DEBIAN" "$PKG/opt/$NAME" "$PKG/usr/bin" \
           "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/256x256/apps"
  cp -a dist/KEGE_Station/. "$PKG/opt/$NAME/"
  ln -s "/opt/$NAME/KEGE_Station" "$PKG/usr/bin/$NAME"
  install -m 0644 packaging/linux/kege-station.desktop "$PKG/usr/share/applications/$NAME.desktop"
  install -m 0644 assets/app_icon.png "$PKG/usr/share/icons/hicolor/256x256/apps/$NAME.png"
  SIZE="$(du -sk "$PKG" | cut -f1)"
  cat > "$PKG/DEBIAN/control" <<EOF
Package: $NAME
Version: $VERSION
Section: education
Priority: optional
Architecture: $ARCH
Installed-Size: $SIZE
Depends: libc6, libegl1, libgl1, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libfontconfig1, libdbus-1-3, xdg-utils
Recommends: libreoffice-calc, fonts-noto-core
Maintainer: KEGE Station <noreply@users.noreply.github.com>
Homepage: https://github.com/dmitriy28/KEGE
Description: Offline trainer for the Russian computer-based informatics exam
 KEGE Station imitates the participant workplace of the computer-based exam:
 registration, timer, tasks with attachments, answer entry and checksum.
EOF
  mkdir -p dist/release
  dpkg-deb --root-owner-group --build "$PKG" "dist/release/${NAME}_${VERSION}_${ARCH}.deb"
  echo "Пакет: dist/release/${NAME}_${VERSION}_${ARCH}.deb"
fi

( cd dist/release && sha256sum * > SHA256SUMS && cat SHA256SUMS )
