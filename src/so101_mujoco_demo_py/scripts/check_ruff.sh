#!/usr/bin/env bash
set -euo pipefail

readonly expected_version="ruff 0.15.20"
package_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
readonly package_root
readonly config="$package_root/ruff.toml"

command -v ruff >/dev/null 2>&1 || {
  printf 'Ruff gate failed: ruff is not installed\n' >&2
  exit 1
}
actual_version=$(ruff --version)
if [[ "$actual_version" != "$expected_version" ]]; then
  printf 'Ruff gate failed: expected %s, got %s\n' "$expected_version" "$actual_version" >&2
  exit 1
fi

targets=(
  "$package_root/setup.py"
  "$package_root/so101_mujoco_demo_py"
  "$package_root/test"
  "$package_root/scripts"
)
for optional_directory in launch config; do
  if [[ -d "$package_root/$optional_directory" ]]; then
    targets+=("$package_root/$optional_directory")
  fi
done

ruff check --config "$config" "${targets[@]}"
ruff format --check --config "$config" "${targets[@]}"
