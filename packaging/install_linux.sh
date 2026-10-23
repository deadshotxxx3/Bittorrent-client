#!/usr/bin/env bash
set -e
here="$(cd "$(dirname "$0")/.." && pwd)"
if [ -x "$here/dist/BitClient/BitClient" ]; then
  exec_line="$here/dist/BitClient/BitClient"
else
  exec_line="$(command -v python3) $here/app.py"
fi
target="$HOME/.local/share/applications"
mkdir -p "$target"
sed "s|BITCLIENT_EXEC|$exec_line|" "$here/packaging/bitclient.desktop" > "$target/bitclient.desktop"
update-desktop-database "$target" 2>/dev/null || true
xdg-mime default bitclient.desktop application/x-bittorrent
xdg-mime default bitclient.desktop x-scheme-handler/magnet
echo "BitClient registered for .torrent files and magnet links"
