#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# Workaround for Ubuntu 26.04 snap/system glibc conflict:
# Filter out snap libc from LD_LIBRARY_PATH to avoid GLIBC_PRIVATE symbol clashes
export LD_LIBRARY_PATH="$ROOT/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/extensions/python/dist/bin:$ROOT/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/dist/lib:$ROOT/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/dist/bin:$ROOT/.py2.new/lib:/usr/lib/x86_64-linux-gnu:/lib/x86_64-linux-gnu"

exec env \
  LD_LIBRARY_PATH="$LD_LIBRARY_PATH" \
  "$ROOT/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/dist/bin/komodo" "$@"
