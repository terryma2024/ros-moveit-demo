#!/usr/bin/env bash
set -euo pipefail

validator=$1
fixtures=$2
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

run_validator() {
  python3 "${validator}" \
    "${1:-${fixtures}/snapshot_gazebo.txt}" \
    "${fixtures}/snapshot_attachment.txt" \
    "${2:-${fixtures}/snapshot_joint_states.txt}" \
    "${3:-${fixtures}/snapshot_planning_scene.txt}"
}

run_validator

sed 's/\[0.000000 0.000000 0.000000\]/[0.523599 0.000000 0.000000]/' \
  "${fixtures}/snapshot_gazebo.txt" >"${tmp_dir}/tipped_gazebo.txt"
if run_validator "${tmp_dir}/tipped_gazebo.txt" \
    >"${tmp_dir}/gazebo.out" 2>"${tmp_dir}/gazebo.err"; then
  echo 'FAIL: snapshot validator accepted a tipped Gazebo Coke' >&2
  exit 1
fi
grep -Fq 'Gazebo Coke orientation' "${tmp_dir}/gazebo.err"

sed 's/x=0.0, y=0.0, z=0.0, w=1.0/x=0.258819, y=0.0, z=0.0, w=0.965926/' \
  "${fixtures}/snapshot_planning_scene.txt" >"${tmp_dir}/tipped_moveit.txt"
if run_validator '' '' "${tmp_dir}/tipped_moveit.txt" \
    >"${tmp_dir}/moveit.out" 2>"${tmp_dir}/moveit.err"; then
  echo 'FAIL: snapshot validator accepted a tipped MoveIt Coke' >&2
  exit 1
fi
grep -Fq 'MoveIt Coke orientation' "${tmp_dir}/moveit.err"

sed '0,/^- 0\.0$/s//- nan/' "${fixtures}/snapshot_joint_states.txt" \
  >"${tmp_dir}/nonfinite_joints.txt"
if run_validator '' "${tmp_dir}/nonfinite_joints.txt" \
    >"${tmp_dir}/joints.out" 2>"${tmp_dir}/joints.err"; then
  echo 'FAIL: snapshot validator accepted non-finite joint evidence' >&2
  exit 1
fi
grep -Fq 'joint-state evidence is non-finite' "${tmp_dir}/joints.err"

echo 'PASS: snapshot validator accepts complete 6DoF evidence and rejects corrupt evidence'
