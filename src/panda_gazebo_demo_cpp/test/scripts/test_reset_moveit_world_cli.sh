#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  printf 'usage: %s RESET_MOVEIT_WORLD_EXECUTABLE\n' "$0" >&2
  exit 2
fi

executable="$1"
output="$(mktemp)"
trap 'rm -f "${output}"' EXIT

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

[[ -x "${executable}" ]] || fail 'reset_moveit_world is not executable'
"${executable}" --help >"${output}" 2>&1
grep -Fq 'reset_moveit_world [--ros-args ...]' "${output}" ||
  fail 'reset_moveit_world usage was not produced'

printf 'PASS: reset_moveit_world exposes a side-effect-free help path\n'
