#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CLEAN_HOME=${KOMODO_CLEAN_HOME:-/tmp/komodo-clean-home}
mkdir -p "$CLEAN_HOME"

mkdir -p "$CLEAN_HOME/.komodoedit/12.0/XRE"
cat > "$CLEAN_HOME/.komodoedit/12.0/XRE/user.js" <<'EOF'
// Clean-profile startup prefs for reducing cache/update background loops.
user_pref("browser.cache.use_new_backend", 0);
user_pref("browser.cache.disk.enable", false);
user_pref("browser.cache.offline.enable", false);
user_pref("browser.cache.memory.enable", true);
user_pref("browser.cache.disk.capacity", 0);
user_pref("browser.cache.disk.smart_size.enabled", false);
user_pref("network.http.use-cache", false);
user_pref("app.update.enabled", false);
user_pref("extensions.update.enabled", false);
user_pref("extensions.blocklist.enabled", false);
EOF

exec env HOME="$CLEAN_HOME" "$ROOT/run-komodo.sh" "$@"
