# Reproducible Linux workflow (Ubuntu 26.04)

This repository includes one entry-point script for repeatable setup, build, install and uninstall:

- scripts/komodo-repro.sh deps
- scripts/komodo-repro.sh build
- scripts/komodo-repro.sh install
- scripts/komodo-repro.sh uninstall

## Quick start on Ubuntu 26.04

Run from repository root:

```bash
./scripts/komodo-repro.sh deps
./scripts/komodo-repro.sh build
./scripts/komodo-repro.sh install
```

Remove the local install:

```bash
./scripts/komodo-repro.sh uninstall
```

## What each command does

- deps
  - Installs Debian/Ubuntu build dependencies via apt.
  - Bootstraps Python 2.7 into ~/.cache/komodo-repro/python2.7 (needed by legacy build tooling).
  - Uses GCC-compatible CFLAGS for Python 2.7 bootstrap on modern toolchains.
- build
  - Runs git submodule initialization.
  - Auto-builds Mozilla when required artifacts are missing.
  - Runs bk configure and bk build.
- install
  - Calls make-komodo-layout.sh and creates the install directly in ~/.komodo (default).
  - Writes desktop entry ~/.local/share/applications/komodo-edit-local.desktop.
  - Optional override: set KOMODO_DESKTOP_HOME to place the desktop file elsewhere.
- uninstall
  - Removes install directory (default ~/.komodo).
  - Removes desktop entry.

## Useful options

Full rebuild of Mozilla:

```bash
KOMODO_MOZILLA_CLEAN=1 KOMODO_BUILD_MOZILLA=1 ./scripts/komodo-repro.sh build
```

Force re-bootstrap Python 2.7:

```bash
KOMODO_PY2_REBUILD=1 ./scripts/komodo-repro.sh deps
```

Custom cache location:

```bash
KOMODO_REPRO_CACHE_DIR=/path/to/cache ./scripts/komodo-repro.sh deps
```

Custom CFLAGS for Python 2.7 bootstrap (only if needed):

```bash
KOMODO_PY2_CFLAGS='-std=gnu17' ./scripts/komodo-repro.sh deps
```

Mozilla source: by default, `build` fetches a pre-patched Mozilla 35.0
source snapshot from a GitHub release
([transfairs/komodo-edit-mozilla35-src](https://github.com/transfairs/komodo-edit-mozilla35-src)),
so builds no longer depend on `hg.mozilla.org` staying online. To use the
original Mercurial-based fetch instead:

```bash
KOMODO_USE_HG_SRC=1 ./scripts/komodo-repro.sh build
```

Or point at a different pre-patched tarball:

```bash
KOMODO_MOZ_SRC_TARBALL_URL=https://example.com/mozilla-35.0-src.tar.gz \
KOMODO_MOZ_SRC_TARBALL_SHA256=<sha256> \
./scripts/komodo-repro.sh build
```

Custom install path:

```bash
./scripts/komodo-repro.sh install /path/to/install
./scripts/komodo-repro.sh uninstall /path/to/install
```
