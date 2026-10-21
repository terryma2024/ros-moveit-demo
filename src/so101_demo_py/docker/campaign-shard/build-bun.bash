#!/usr/bin/bash
# Bun wrapper for the shard image build. Only `install` is special.
#
# Bun keys its cache entries by registry host (`name@version@@registry.npmmirror.com@@@1`). The cache is filled on the
# host through the npmmirror registry, so the registry must be the same here; with bun's default registry every entry
# misses and all packages are downloaded from registry.npmjs.org.
#
# `install` first runs `--offline`: it uses only the copied cache and never touches the network. If the cache is
# incomplete the wrapper says so and repeats the install against the same mirror, so a package that is genuinely missing
# is fetched from the mirror instead of failing the build. The lockfile stays frozen in both runs and bun still checks
# the integrity hashes in bun.lock.
#
# SO101_BUN_BIN and SO101_BUN_CACHE_DIR exist so a test can point the wrapper at fixtures; the image uses the defaults.
set -euo pipefail
bun_bin="${SO101_BUN_BIN:-/act/source/build-deps/bun}"
cache_dir="${SO101_BUN_CACHE_DIR:-/act/build-source/build-deps/bun-cache}"
export BUN_CONFIG_REGISTRY="${BUN_CONFIG_REGISTRY:-https://registry.npmmirror.com}"
if [[ "${1:-}" == install ]]; then
    shift
    if "$bun_bin" install "$@" --frozen-lockfile --cache-dir "$cache_dir" --offline; then
        exit 0
    fi
    echo "build-bun: offline install failed; the bun cache is incomplete, retrying from ${BUN_CONFIG_REGISTRY}" >&2
    exec "$bun_bin" install "$@" --frozen-lockfile --cache-dir "$cache_dir"
fi
exec "$bun_bin" "$@"
