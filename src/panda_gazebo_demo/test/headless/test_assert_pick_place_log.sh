#!/usr/bin/env bash
set -euo pipefail

validator=$1
fixtures=$2

python3 "$validator" "$fixtures/complete.log"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

assert_rejected() {
  local name="$1"
  local expected_error="$2"
  if python3 "$validator" "${tmp_dir}/${name}.log" \
      >"${tmp_dir}/${name}.out" 2>"${tmp_dir}/${name}.err"; then
    echo "FAIL: validator accepted generated fixture ${name}" >&2
    exit 1
  fi
  grep -Fq "${expected_error}" "${tmp_dir}/${name}.err" || {
    echo "FAIL: ${name} did not fail for ${expected_error}" >&2
    cat "${tmp_dir}/${name}.err" >&2
    exit 1
  }
}

sed 's/MAX_JOINT_JUMP state=DESCEND value=0.020000/MAX_JOINT_JUMP state=DESCEND value=0.250000/' \
  "$fixtures/complete.log" >"${tmp_dir}/excessive_joint_jump.log"
assert_rejected excessive_joint_jump 'DESCEND maximum joint jump'

sed 's/PLANNED_END_TCP_POSE state=LIFT x=0.300000/PLANNED_END_TCP_POSE state=LIFT x=0.350000/' \
  "$fixtures/complete.log" >"${tmp_dir}/bad_planned_endpoint.log"
assert_rejected bad_planned_endpoint 'LIFT planned endpoint position error'

sed 's/EXECUTED_END_TCP_POSE state=RETREAT x=0.300000/EXECUTED_END_TCP_POSE state=RETREAT x=0.350000/' \
  "$fixtures/complete.log" >"${tmp_dir}/bad_executed_endpoint.log"
assert_rejected bad_executed_endpoint 'RETREAT executed endpoint position error'

sed 's/TARGET_TCP_POSE state=DESCEND x=0.300000 y=0.000000 z=0.870000 roll=3.141593/TARGET_TCP_POSE state=DESCEND x=0.300000 y=0.000000 z=0.870000 roll=1.570796/' \
  "$fixtures/complete.log" >"${tmp_dir}/bad_target_orientation.log"
assert_rejected bad_target_orientation 'DESCEND target orientation error'

sed 's/COKE_POSE_AFTER state=RETREAT x=0.300000 y=0.200000 z=0.836000 roll=0.000000/COKE_POSE_AFTER state=RETREAT x=0.300000 y=0.200000 z=0.836000 roll=0.523599/' \
  "$fixtures/complete.log" >"${tmp_dir}/tipped_coke.log"
assert_rejected tipped_coke 'final Coke orientation error'

sed 's/TRAJECTORY_DURATION state=MOVE_ABOVE_PLACE value=3.000000/TRAJECTORY_DURATION state=MOVE_ABOVE_PLACE value=nan/' \
  "$fixtures/complete.log" >"${tmp_dir}/nonfinite_numeric.log"
assert_rejected nonfinite_numeric 'MOVE_ABOVE_PLACE TRAJECTORY_DURATION is missing or non-finite'

for fixture in \
  incomplete_cartesian.log \
  missing_moveit_detach.log \
  final_coke_outside_tolerance.log
do
  if python3 "$validator" "$fixtures/$fixture" \
      >"${tmp_dir}/${fixture}.out" 2>"${tmp_dir}/${fixture}.err"; then
    echo "FAIL: validator accepted $fixture" >&2
    exit 1
  fi
done

echo "PASS: complete log accepted and invalid fixtures rejected"
