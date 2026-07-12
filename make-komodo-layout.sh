#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT=${1:-"$ROOT/Komodo-Edit-local"}

copy_tree() {
    src=$1
    dest=$2
    mkdir -p "$dest"
    cp -aL "$src"/. "$dest"/
}

rm -rf "$OUT"
mkdir -p "$OUT/bin" "$OUT/lib" "$OUT/share"

# Launcher stub with portable runtime env bootstrap.
cp "$ROOT/src/main/stub/komodo" "$OUT/bin/komodo"
chmod +x "$OUT/bin/komodo"

# Build-tree runtime payload.
copy_tree "$ROOT/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/dist/bin" "$OUT/lib/mozilla"
copy_tree "$ROOT/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/dist/lib" "$OUT/lib/mozilla"
copy_tree "$ROOT/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/dist/komodo-bits/support" "$OUT/lib/support"
copy_tree "$ROOT/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/dist/komodo-bits/sdk" "$OUT/lib/sdk"

# A portable bundle must not advertise itself as a dev tree, otherwise
# runtime directory lookup points into a non-existent lib/komodo-bits tree.
rm -f "$OUT/lib/mozilla/is_dev_tree.txt"

# PyXPCOM runtime bits live under the Python extension payload as well.
if [ -d "$ROOT/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/extensions/python/dist" ]; then
    copy_tree "$ROOT/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/extensions/python/dist" "$OUT/lib/mozilla/extensions/python/dist"
fi

# Optional convenience links if present.
if [ -d "$ROOT/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/dist/python" ]; then
    copy_tree "$ROOT/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/dist/python" "$OUT/lib/python"
fi
if [ -d "$ROOT/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/dist/bin/icons" ]; then
    copy_tree "$ROOT/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/dist/bin/icons" "$OUT/share/icons"
fi

echo "Created layout: $OUT"
echo "Start with: $OUT/bin/komodo"
