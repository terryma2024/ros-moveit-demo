#!/usr/bin/bash
set -euo pipefail
if [[ "${1:-}" == install ]]; then
    exec /act/source/build-deps/bun "$@" --offline --cache-dir /act/build-source/build-deps/bun-cache
fi
exec /act/source/build-deps/bun "$@"
