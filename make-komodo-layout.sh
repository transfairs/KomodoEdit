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

# The siloed Python's "relocatable" build leaves some extension modules
# (and libpython itself) with a hardcoded absolute RPATH pointing back at
# the build-tree ko-rel/dist/lib, instead of a portable $ORIGIN-relative
# one. That breaks the install once the build tree is gone (or on any
# other machine). bin/komodo already builds a correct LD_LIBRARY_PATH
# (covering lib/mozilla and lib/python/lib) before exec'ing, and a
# leftover absolute RPATH takes priority over LD_LIBRARY_PATH and wins
# with the wrong, non-existent path -- so just strip those, and let
# LD_LIBRARY_PATH do its job.
if command -v patchelf >/dev/null 2>&1; then
    find "$OUT" -type f \( -name "*.so" -o -name "*.so.*" \) 2>/dev/null | while IFS= read -r so; do
        cur_rpath=$(patchelf --print-rpath "$so" 2>/dev/null || true)
        case "$cur_rpath" in
            *'$ORIGIN'*|"") continue ;;
            /*)
                perms=$(stat -c '%a' "$so")
                chmod u+w "$so"
                patchelf --remove-rpath "$so"
                chmod "$perms" "$so"
                ;;
        esac
    done
else
    echo "WARNING: patchelf not found; leaving broken absolute RPATHs in place (install '\''patchelf'\'' to fix)" >&2
fi

echo "Created layout: $OUT"
echo "Start with: $OUT/bin/komodo"
