#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
INSTALL_DIR_DEFAULT="$HOME/.komodo"
CACHE_BASE="${KOMODO_REPRO_CACHE_DIR:-$HOME/.cache/komodo-repro}"
PY2_PREFIX="$CACHE_BASE/python2.7"
PY2_EXE="$PY2_PREFIX/bin/python2.7"
PY2_SRC_DIR="$CACHE_BASE/src/Python-2.7.18"
PY2_TARBALL="$CACHE_BASE/src/Python-2.7.18.tgz"
PY2_URL="https://www.python.org/ftp/python/2.7.18/Python-2.7.18.tgz"
MOZ_SRC_TARBALL_URL_DEFAULT="https://github.com/transfairs/komodo-edit-mozilla35-src/releases/download/mozilla-35.0-ko12.10-v4/mozilla-35.0-ko12.10-FIREFOX_35_0_RELEASE-patched-src-v4.tar.gz"
MOZ_SRC_TARBALL_SHA256_DEFAULT="7988f91b38e42921ace3a5bcc2aea6573894e3a4adb89ad00f74209e42b2c5cd"
MOZ_SRC_TARBALL_CACHE="$CACHE_BASE/src/mozilla-35.0-ko12.10-patched-src.tar.gz"

usage() {
  cat <<'EOF'
Usage:
  scripts/komodo-repro.sh deps
  scripts/komodo-repro.sh build
  scripts/komodo-repro.sh install [install_dir]
  scripts/komodo-repro.sh uninstall [install_dir]
  scripts/komodo-repro.sh all [install_dir]

Commands:
  deps       Install Ubuntu dependencies and bootstrap local Python 2.7.
  build      Build Komodo artifacts.
  install    Create layout in install_dir and install desktop entry.
  uninstall  Remove installed files and desktop integration.
  all        Run: deps -> build -> install.

Defaults:
  install_dir = ~/.komodo

Environment knobs:
  KOMODO_BUILD_MOZILLA=1      Force Mozilla build (default: auto on missing artifacts).
  KOMODO_MOZILLA_CLEAN=1      Use mozilla build.py distclean all (default: 0).
  KOMODO_USE_SUDO=0           Disable sudo for apt installs.
  KOMODO_PY2_REBUILD=1        Rebuild local Python 2.7 even if present.
  KOMODO_REPRO_CACHE_DIR=...  Override cache directory (default: ~/.cache/komodo-repro).
  KOMODO_USE_HG_SRC=1         Fetch Mozilla source from hg.mozilla.org instead of the
                              pre-patched tarball (default: 0, use the tarball).
  KOMODO_MOZ_SRC_TARBALL_URL=...
                              Override the pre-patched Mozilla source tarball URL
                              (default: komodo-edit-mozilla35-src release asset).
EOF
}

log() {
  printf '[komodo-repro] %s\n' "$*"
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  fi
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

apt_install() {
  local -a pkgs=("$@")
  local sudo_cmd="sudo"

  if [[ "${KOMODO_USE_SUDO:-1}" == "0" || "$(id -u)" == "0" ]]; then
    sudo_cmd=""
  fi

  if [[ -n "$sudo_cmd" ]]; then
    $sudo_cmd apt-get update
    $sudo_cmd apt-get install -y "${pkgs[@]}"
  else
    apt-get update
    apt-get install -y "${pkgs[@]}"
  fi
}

bootstrap_python2() {
  if [[ -x "$PY2_EXE" && "${KOMODO_PY2_REBUILD:-0}" != "1" ]]; then
    log "Using existing local Python 2.7: $PY2_EXE"
    return
  fi

  mkdir -p "$CACHE_BASE/src"

  if [[ ! -d "$PY2_SRC_DIR" ]]; then
    if [[ ! -f "$PY2_TARBALL" ]]; then
      log "Downloading Python 2.7.18 source"
      if have_cmd curl; then
        curl -fsSL "$PY2_URL" -o "$PY2_TARBALL"
      else
        wget -O "$PY2_TARBALL" "$PY2_URL"
      fi
    fi
    log "Extracting Python 2.7.18 source"
    tar -xzf "$PY2_TARBALL" -C "$CACHE_BASE/src"
  fi

  log "Building local Python 2.7 (this may take a few minutes)"
  pushd "$PY2_SRC_DIR" >/dev/null
  # GCC 15 defaults to newer C language modes; Python 2.7 sources need an
  # older C dialect to avoid keyword clashes (e.g. false/true in asdl.h).
  local py2_cflags="${KOMODO_PY2_CFLAGS:--std=gnu17}"
  # Bake in an RPATH (classic DT_RPATH, via --disable-new-dtags, which
  # takes priority over LD_LIBRARY_PATH -- unlike the default DT_RUNPATH)
  # to this Python's own lib dir. Downstream steps of the Komodo build
  # (bk build's Cons-based subprocess environments) don't reliably
  # propagate LD_LIBRARY_PATH to every command they spawn, and this
  # --enable-shared build otherwise has no way to find its own
  # libpython2.7.so without it, crashing with "cannot open shared
  # object file". An RPATH makes that propagation unnecessary.
  local py2_ldflags="${KOMODO_PY2_LDFLAGS:--Wl,-rpath,$PY2_PREFIX/lib -Wl,--disable-new-dtags}"
  make distclean >/dev/null 2>&1 || true
  CFLAGS="$py2_cflags" LDFLAGS="$py2_ldflags" ./configure --prefix="$PY2_PREFIX" --enable-shared --with-ensurepip=no
  CFLAGS="$py2_cflags" LDFLAGS="$py2_ldflags" make -j"$(nproc)"
  make install
  popd >/dev/null

  if [[ ! -x "$PY2_EXE" ]]; then
    printf 'Python 2.7 bootstrap failed: %s not found\n' "$PY2_EXE" >&2
    exit 1
  fi
}

setup_build_env() {
  export PATH="$ROOT_DIR/util/black:$PY2_PREFIX/bin:$PATH"
  # Keep Python runtime deterministic on fresh and previously-used systems.
  export LD_LIBRARY_PATH="$PY2_PREFIX/lib"
  export PERL5LIB="$ROOT_DIR${PERL5LIB:+:$PERL5LIB}"
  export KOMODO_UNSILOED_PYTHON_EXE="$PY2_EXE"
  unset PYTHONHOME || true
  unset PYTHONPATH || true

  local ac
  for ac in autoconf-2.13 autoconf2.13 autoconf213; do
    if have_cmd "$ac"; then
      export AUTOCONF
      AUTOCONF="$(command -v "$ac")"
      break
    fi
  done
}

run_preflight() {
  need_cmd git
  need_cmd make
  need_cmd perl
  need_cmd "$PY2_EXE"

  if [[ ! -d "$ROOT_DIR/mozilla" || ! -f "$ROOT_DIR/mozilla/build.py" ]]; then
    printf 'Missing mozilla sources in this checkout.\n' >&2
    exit 1
  fi
}

run_deps() {
  need_cmd apt-get

  log "Installing Ubuntu build dependencies"
  apt_install \
    ca-certificates curl git zip unzip wget mercurial subversion \
    build-essential pkg-config yasm autoconf2.13 \
    libgtk2.0-dev libdbus-glib-1-dev libasound2-dev libpulse-dev libxt-dev \
    libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
    libffi-dev libncursesw5-dev xz-utils tk-dev patchelf

  bootstrap_python2
  setup_build_env

  log "Dependency setup complete"
}

should_build_mozilla() {
  if [[ "${KOMODO_BUILD_MOZILLA:-}" == "1" ]]; then
    return 0
  fi
  if [[ "${KOMODO_BUILD_MOZILLA:-}" == "0" ]]; then
    return 1
  fi
  [[ ! -x "$ROOT_DIR/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/dist/bin/komodo" ]]
}

download_moz_src_tarball() {
  local url="${KOMODO_MOZ_SRC_TARBALL_URL:-$MOZ_SRC_TARBALL_URL_DEFAULT}"
  local sha256="${KOMODO_MOZ_SRC_TARBALL_SHA256:-$MOZ_SRC_TARBALL_SHA256_DEFAULT}"

  mkdir -p "$(dirname "$MOZ_SRC_TARBALL_CACHE")"

  if [[ -f "$MOZ_SRC_TARBALL_CACHE" ]] \
     && echo "$sha256  $MOZ_SRC_TARBALL_CACHE" | sha256sum -c - >/dev/null 2>&1; then
    log "Pre-patched Mozilla source tarball already cached and verified"
  else
    log "Downloading pre-patched Mozilla source tarball from $url"
    if have_cmd curl; then
      curl -fsSL "$url" -o "$MOZ_SRC_TARBALL_CACHE"
    else
      wget -O "$MOZ_SRC_TARBALL_CACHE" "$url"
    fi
    if ! echo "$sha256  $MOZ_SRC_TARBALL_CACHE" | sha256sum -c - >/dev/null 2>&1; then
      log "ERROR: checksum mismatch for downloaded Mozilla source tarball"
      rm -f "$MOZ_SRC_TARBALL_CACHE"
      exit 1
    fi
  fi
}

run_build() {
  setup_build_env
  run_preflight

  log "Syncing git submodules"
  pushd "$ROOT_DIR" >/dev/null
  git submodule update --init --recursive
  popd >/dev/null

  if should_build_mozilla; then
    log "Configuring Mozilla"
    pushd "$ROOT_DIR/mozilla" >/dev/null
    "$PY2_EXE" build.py configure -k 12.10
    if [[ "${KOMODO_USE_HG_SRC:-0}" != "1" ]]; then
      log "Pointing Mozilla source fetch at pre-patched tarball (set KOMODO_USE_HG_SRC=1 to use hg.mozilla.org instead)"
      download_moz_src_tarball
      cat >> config.py <<EOF
mozSrcType = 'tarball'
mozSrcTarball = '$MOZ_SRC_TARBALL_CACHE'
EOF
    fi
    # The pre-patched tarball already has every mozilla/patches-new/ patch
    # baked in, but patchtree.py's "already applied" detection is not
    # reliable for every patch (e.g. multi-file/new-file patches), so
    # re-running the patch/patch_pyxpcom/patch_komodo targets against it
    # can fail on hunks that are already satisfied. Skip straight to the
    # post-patch targets in that case; only re-patch when actually
    # fetching unpatched source from hg.mozilla.org.
    if [[ "${KOMODO_USE_HG_SRC:-0}" == "1" ]]; then
      local moz_targets="all"
    else
      local moz_targets="src src_pyxpcom configure_mozilla mozilla pyxpcom silo_python regmozbuild"
    fi
    if [[ "${KOMODO_MOZILLA_CLEAN:-0}" == "1" ]]; then
      log "Running full Mozilla rebuild (distclean $moz_targets)"
      "$PY2_EXE" build.py distclean $moz_targets
    else
      log "Building Mozilla"
      "$PY2_EXE" build.py $moz_targets
    fi
    popd >/dev/null
  else
    log "Mozilla artifacts already present, skipping Mozilla build"
  fi

  log "Running bk configure/build"
  pushd "$ROOT_DIR" >/dev/null
  bk configure -V 12.10.0-devel --komodo-buildnum=12
  bk build
  popd >/dev/null
}

install_desktop_entry() {
  local install_dir="$1"
  local desktop_home="${KOMODO_DESKTOP_HOME:-$HOME}"
  local app_dir="$desktop_home/.local/share/applications"
  local desktop_file="$app_dir/komodo-edit.desktop"

  mkdir -p "$app_dir"
  cat > "$desktop_file" <<EOF
[Desktop Entry]
Encoding=UTF-8
Version=1.0
Type=Application
Name=Komodo Edit
GenericName=Editor
Comment=Free multi-platform editor that makes it easy to write quality code.
Exec=$install_dir/bin/komodo %F
Icon=$install_dir/share/icons/komodo48.png
StartupWMClass=Komodo edit
Terminal=false
Categories=Application;Development;IDE;Editor;Utility;TextEditor;
MimeType=text/plain;
EOF

  if have_cmd update-desktop-database; then
    update-desktop-database "$app_dir" >/dev/null 2>&1 || true
  fi

  log "Desktop entry installed: $desktop_file"
}

remove_desktop_entry() {
  local desktop_home="${KOMODO_DESKTOP_HOME:-$HOME}"
  local app_dir="$desktop_home/.local/share/applications"
  local desktop_file="$app_dir/komodo-edit.desktop"

  rm -f "$desktop_file"
  if have_cmd update-desktop-database; then
    update-desktop-database "$app_dir" >/dev/null 2>&1 || true
  fi

  log "Desktop entry removed: $desktop_file"
}

run_install() {
  local install_dir="${1:-$INSTALL_DIR_DEFAULT}"

  if [[ ! -x "$ROOT_DIR/mozilla/build/moz3500-ko12.10/mozilla/ko-rel/dist/bin/komodo" ]]; then
    printf 'Build artifacts missing. Run build first.\n' >&2
    exit 1
  fi

  log "Creating install layout in $install_dir"
  "$ROOT_DIR/make-komodo-layout.sh" "$install_dir"

  install_desktop_entry "$install_dir"
  log "Install done. Launch with: $install_dir/bin/komodo"
}

run_uninstall() {
  local install_dir="${1:-$INSTALL_DIR_DEFAULT}"

  log "Removing install dir: $install_dir"
  rm -rf "$install_dir"
  remove_desktop_entry
  log "Uninstall done"
}

main() {
  local cmd="${1:-}"

  case "$cmd" in
    deps)
      run_deps
      ;;
    build)
      run_build
      ;;
    install)
      run_install "${2:-$INSTALL_DIR_DEFAULT}"
      ;;
    uninstall)
      run_uninstall "${2:-$INSTALL_DIR_DEFAULT}"
      ;;
    all)
      run_deps
      run_build
      run_install "${2:-$INSTALL_DIR_DEFAULT}"
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      printf 'Unknown command: %s\n\n' "$cmd" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
