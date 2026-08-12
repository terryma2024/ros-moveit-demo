#!/usr/bin/env bash
set -euo pipefail

# Compatibility path for existing callers; logic lives in the repository-level
# backend integration contract so there is one implementation to maintain.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$script_dir/../../../scripts/check_backend_integration.py" "$@"
