#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 4 ]]; then
  printf 'usage: %s LAUNCH E2E RECOVERY PLAN_ONLY\n' "$0" >&2
  exit 2
fi

launch_file="$1"
shift

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

if rg -n '\bplanning_scene_setup\b' "${launch_file}" "$@"; then
  fail 'active launch or headless caller still references planning_scene_setup'
fi
rg -Fq "executable='reset_moveit_world'" "${launch_file}" ||
  fail 'launch does not start reset_moveit_world'
for harness in "$@"; do
  rg -Fq 'scripts/reset_world.sh' "${harness}" ||
    fail "headless harness does not call reset_world.sh: ${harness}"
  rg -Fq 'assert_reset_moveit_scene.py' "${harness}" ||
    fail "headless harness lacks independent MoveIt reset assertion: ${harness}"
done
printf 'PASS: world reset callers use reset_moveit_world and reset_world.sh\n'
