#!/usr/bin/env bash
set -euo pipefail

# Compatibility entry point.  The migration-era name is retained for callers;
# the implementation is now the stable backend integration contract.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$script_dir/check_backend_integration.py" "$@"
