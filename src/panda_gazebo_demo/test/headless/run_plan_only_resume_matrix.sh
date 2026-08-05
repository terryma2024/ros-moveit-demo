#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
package_root="$(cd "${script_dir}/../.." && pwd)"
workspace_root="$(cd "${package_root}/../.." && pwd)"
log_root="${workspace_root}/build/panda_gazebo_demo/test_logs"

unset COLCON_CURRENT_PREFIX
set +u
source /opt/ros/jazzy/setup.bash
source "${workspace_root}/install/setup.bash"
set -u

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-$((100 + $$ % 100))}"
export GZ_PARTITION="${GZ_PARTITION:-panda_plan_only_resume_$$}"
run_root="${log_root}/plan_only_resume_$(date +%Y%m%d_%H%M%S)_$$"
mkdir -p "${run_root}"

launch_pid=""
attachment_monitor_pid=""
cleanup() {
  local attempt
  if [[ -n "${attachment_monitor_pid}" ]]; then
    kill -TERM "${attachment_monitor_pid}" 2>/dev/null || true
    wait "${attachment_monitor_pid}" 2>/dev/null || true
  fi
  if [[ -z "${launch_pid}" ]]; then
    return
  fi
  kill -TERM -- "-${launch_pid}" 2>/dev/null || true
  for attempt in {1..50}; do
    if ! kill -0 -- "-${launch_pid}" 2>/dev/null; then
      wait "${launch_pid}" 2>/dev/null || true
      return
    fi
    sleep 0.1
  done
  kill -KILL -- "-${launch_pid}" 2>/dev/null || true
  wait "${launch_pid}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait_until() {
  local timeout_seconds="$1"
  local description="$2"
  shift 2
  local deadline=$((SECONDS + timeout_seconds))
  while ((SECONDS < deadline)); do
    if "$@" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  printf 'Timed out waiting for %s\n' "${description}" >&2
  return 1
}

gazebo_ready() {
  gz service -l | grep -Fxq /world/pick_place_world/control
}

move_group_ready() {
  ros2 node list 2>/dev/null | grep -Fxq /move_group
}

controllers_ready() {
  local controllers
  controllers="$(ros2 control list_controllers 2>/dev/null)" || return 1
  grep -Eq '^panda_arm_controller[[:space:]].*active' <<<"${controllers}" &&
    grep -Eq '^panda_hand_controller[[:space:]].*active' <<<"${controllers}" &&
    grep -Eq '^joint_state_broadcaster[[:space:]].*active' <<<"${controllers}"
}

joint_states_ready() {
  timeout 2 ros2 topic echo /joint_states --once 2>/dev/null |
    grep -q panda_finger_joint1
}

attachment_output_detached() {
  timeout 2 gz topic -e -t /panda/coke_attached -n 1 2>/dev/null |
    grep -Eq 'data: *"?detached"?'
}

planning_scene_ready() {
  timeout 3 ros2 service call /get_planning_scene \
    moveit_msgs/srv/GetPlanningScene '{components: {components: 28}}' 2>/dev/null |
    grep -q "id='coke'"
}

joint_states_stationary() {
  local output="$1"
  timeout 3 ros2 topic echo /joint_states --once >"${output}" 2>&1 || return 1
  python3 - "${output}" <<'PY'
import math
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')
match = re.search(r'velocity:\s*\n(?P<body>(?:- [^\n]+\n)+)effort:', text)
if not match:
    raise SystemExit(1)
velocities = [float(line[2:]) for line in match.group('body').splitlines()]
raise SystemExit(0 if velocities and all(
    math.isfinite(value) and abs(value) <= 0.01 for value in velocities
) else 1)
PY
}

last_attachment_is_detached() {
  grep 'data:' "${run_root}/attachment_events.txt" | tail -1 |
    grep -Eq 'data: *"?detached"?'
}

reset_fixture() {
  local directory="$1"
  mkdir -p "${directory}"
  EXPECTED_COKE_DETACHED=true "${package_root}/scripts/reset_world.sh" \
    >"${directory}/reset.log" 2>&1
  wait_until 10 'detached state after independent reset' last_attachment_is_detached
  timeout 5 ros2 service call /get_planning_scene \
    moveit_msgs/srv/GetPlanningScene '{components: {components: 28}}' \
    >"${directory}/reset_moveit.txt" 2>&1
  python3 "${script_dir}/assert_reset_moveit_scene.py" \
    "${directory}/reset_moveit.txt"
}

capture_snapshot() {
  local directory="$1"
  local label="$2"
  local tcp_evidence="${3:-}"
  local tcp_argument=()
  gz model -m coke -p >"${directory}/${label}_gazebo_coke.txt" 2>&1
  timeout 3 gz topic -e -t /panda/coke_attached -n 1 \
    >"${directory}/${label}_attachment.txt" 2>&1
  timeout 5 ros2 service call /get_planning_scene \
    moveit_msgs/srv/GetPlanningScene '{components: {components: 28}}' \
    >"${directory}/${label}_planning_scene.txt" 2>&1
  wait_until 15 'stationary joint-state snapshot' joint_states_stationary \
    "${directory}/${label}_joint_states.txt"
  if [[ -n "${tcp_evidence}" ]]; then
    tcp_argument=("${tcp_evidence}")
  fi
  python3 "${script_dir}/capture_resume_snapshot.py" \
    "${directory}/${label}_gazebo_coke.txt" \
    "${directory}/${label}_attachment.txt" \
    "${directory}/${label}_joint_states.txt" \
    "${directory}/${label}_planning_scene.txt" \
    "${directory}/${label}_snapshot.json" "${tcp_argument[@]}"
}

run_machine() {
  local log_file="$1"
  local checkpoint="$2"
  local session="$3"
  shift 3
  timeout 180 ros2 run panda_gazebo_demo pick_place_state_machine \
    --ros-args "$@" -p simulation_session_id:="${session}" \
    -p checkpoint_path:="${checkpoint}" >"${log_file}" 2>&1
}

execute_stop() {
  local log_file="$1"
  local checkpoint="$2"
  local session="$3"
  local state="$4"
  local resume="${5:-true}"
  local resume_argument=()
  if [[ "${resume}" == true ]]; then
    resume_argument=(-p resume:=true)
  fi
  run_machine "${log_file}" "${checkpoint}" "${session}" \
    -p mode:=execute -p stop_after:="${state}" "${resume_argument[@]}"
  grep -q \
    "Run completed: status=CHECKPOINT_COMPLETE current_state=${state}" \
    "${log_file}"
}

plan_only_pair() {
  local state="$1"
  local directory="$2"
  local checkpoint="$3"
  local session="$4"
  mkdir -p "${directory}"
  reset_fixture "${directory}"
  capture_snapshot "${directory}" initial

  run_machine "${directory}/fresh.log" "${checkpoint}" "${session}" \
    -p mode:=plan_only -p plan_only_state:="${state}" -p resume:=false
  grep -q \
    "Run completed: status=PLAN_ONLY_COMPLETE current_state=${state}" \
    "${directory}/fresh.log"
  if grep -Eq "(EXECUTED_END_TCP_POSE|STATE_TRANSITION)[^[:cntrl:]]*[[:space:]]state=${state}([[:space:]]|$)" \
    "${directory}/fresh.log"; then
    printf 'Fresh plan-only executed target %s\n' "${state}" >&2
    return 1
  fi
  capture_snapshot "${directory}" target_entry
  python3 - "${checkpoint}" "${directory}/target_entry_snapshot.json" "${state}" <<'PY'
import json
import math
import pathlib
import sys

checkpoint = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
snapshot = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding='utf-8'))
target = sys.argv[3]
assert checkpoint['schema_version'] == 3
assert checkpoint['source_mode'] == 'execute'
assert checkpoint['phase'] == 'FORWARD'
assert checkpoint['next_state'] == target
assert not target.startswith('RECOVER_')
expected = checkpoint['expected']
for name, value in expected['joint_positions'].items():
    assert math.isclose(snapshot['joint_positions'][name], value, abs_tol=0.01)
assert snapshot['gazebo_attached'] == expected['gazebo_coke_attached']
assert snapshot['moveit_coke_attached'] == expected['moveit_coke_attached']
PY
  cp "${checkpoint}" "${directory}/checkpoint.before.json"
  sha256sum "${directory}/checkpoint.before.json" \
    >"${directory}/checkpoint.before.sha256"

  run_machine "${directory}/resume.log" "${checkpoint}" "${session}" \
    -p mode:=plan_only -p plan_only_state:="${state}" -p resume:=true
  python3 "${script_dir}/assert_plan_only_resume.py" \
    "${directory}/resume.log" "${state}" FORWARD \
    "${directory}/checkpoint.before.json" "${checkpoint}"

  capture_snapshot "${directory}" resumed
  python3 "${script_dir}/assert_resume_snapshot_unchanged.py" \
    "${directory}/target_entry_snapshot.json" "${directory}/resumed_snapshot.json"
  cp "${checkpoint}" "${directory}/checkpoint.after.json"
  sha256sum "${directory}/checkpoint.after.json" \
    >"${directory}/checkpoint.after.sha256"
  cmp -s "${directory}/checkpoint.before.json" \
    "${directory}/checkpoint.after.json"
}

run_independent_target() {
  local state="$1"
  local attempt state_directory checkpoint session status
  for attempt in {1..3}; do
    state_directory="${run_root}/${state}/attempt_${attempt}"
    checkpoint="${state_directory}/checkpoint.json"
    session="plan-only-${state}-${ROS_DOMAIN_ID}-$$-${attempt}-$(date +%s%N)"
    set +e
    (set -e; plan_only_pair "${state}" "${state_directory}" "${checkpoint}" "${session}")
    status=$?
    set -e
    if [[ "${status}" -eq 0 ]]; then
      printf 'PASS: %s independent attempt %s\n' "${state}" "${attempt}"
      return 0
    fi
    printf 'RETRY: %s independent attempt %s failed with status %s\n' \
      "${state}" "${attempt}" "${status}" >&2
  done
  printf 'FAIL: %s exhausted independent attempts\n' "${state}" >&2
  return 1
}

if ros2 node list 2>/dev/null | grep -Eq '/(controller_manager|move_group)$'; then
  printf 'Isolated ROS_DOMAIN_ID %s is already in use\n' "${ROS_DOMAIN_ID}" >&2
  exit 1
fi
if gz service -l 2>/dev/null | grep -Fq /world/pick_place_world/control; then
  printf 'Isolated GZ_PARTITION %s is already in use\n' "${GZ_PARTITION}" >&2
  exit 1
fi

printf 'ROS_DOMAIN_ID=%s\nGZ_PARTITION=%s\n' \
  "${ROS_DOMAIN_ID}" "${GZ_PARTITION}" >"${run_root}/environment.txt"
setsid ros2 launch panda_gazebo_demo panda_gazebo.launch.py \
  headless:=true run_state_machine:=false >"${run_root}/launch.log" 2>&1 &
launch_pid=$!

wait_until 45 'Gazebo control service' gazebo_ready
wait_until 45 'MoveGroup' move_group_ready
wait_until 45 'active controllers' controllers_ready
wait_until 20 '/joint_states' joint_states_ready
gz topic -t /panda/detach_coke -m gz.msgs.Empty -p 'unused: true'
wait_until 10 'durable detached state' attachment_output_detached
timeout 3 gz topic -e -t /panda/coke_attached -n 1 \
  >"${run_root}/initial_attachment.txt" 2>&1
cp "${run_root}/initial_attachment.txt" "${run_root}/attachment_events.txt"
gz topic -e -t /panda/coke_attached \
  >>"${run_root}/attachment_events.txt" 2>&1 &
attachment_monitor_pid=$!
wait_until 30 'Planning Scene Coke object' planning_scene_ready

forward_states=(
  MOVE_ABOVE_OBJECT
  DESCEND
  LIFT
  MOVE_ABOVE_PLACE
  DESCEND_TO_PLACE
  RETREAT
)
for state in "${forward_states[@]}"; do
  run_independent_target "${state}"
done

printf 'PASS: independent forward run-to-plan-only/resume matrix; logs: %s\n' \
  "${run_root}"
