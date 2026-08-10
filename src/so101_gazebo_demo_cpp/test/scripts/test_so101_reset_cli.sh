#!/usr/bin/env bash
set -euo pipefail

reset_executable=$1
scene_executable=$2
tmp_dir=$(mktemp -d)
trap 'rm -rf "${tmp_dir}"' EXIT

"${reset_executable}" --help >"${tmp_dir}/reset.txt"
"${scene_executable}" --help >"${tmp_dir}/scene.txt"

grep -Fq 'reset_so101_world [--ros-args ...]' "${tmp_dir}/reset.txt"
grep -Fq 'default gripper_trajectory_seconds=2.0' "${tmp_dir}/reset.txt"
grep -Fq 'so101_moveit_scene {observe|upsert|attach|detach} [--ros-args ...]' \
  "${tmp_dir}/scene.txt"

printf 'PASS: SO-101 reset tools expose side-effect-free help\n'
