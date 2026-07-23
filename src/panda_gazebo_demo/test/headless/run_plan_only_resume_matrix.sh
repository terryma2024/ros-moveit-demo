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
  last_attachment_is_detached
  EXPECTED_COKE_DETACHED=true "${package_root}/scripts/reset_world.sh" \
    >"${directory}/reset.log" 2>&1
  timeout 5 ros2 service call /get_planning_scene \
    moveit_msgs/srv/GetPlanningScene '{components: {components: 28}}' \
    >"${directory}/reset_moveit_before_setup.txt" 2>&1
  python3 "${script_dir}/assert_reset_moveit_scene.py" \
    "${directory}/reset_moveit_before_setup.txt"
  timeout 15 ros2 run panda_gazebo_demo planning_scene_setup \
    >"${directory}/planning_scene_reset.log" 2>&1
  sleep 1
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
  local phase="$2"
  local directory="$3"
  local checkpoint="$4"
  local session="$5"
  mkdir -p "${directory}"
  capture_snapshot "${directory}" before
  cp "${checkpoint}" "${directory}/checkpoint.before.json"
  sha256sum "${directory}/checkpoint.before.json" \
    >"${directory}/checkpoint.before.sha256"

  run_machine "${directory}/plan_only_1.log" "${checkpoint}" "${session}" \
    -p mode:=plan_only -p resume:=true
  python3 "${script_dir}/assert_plan_only_resume.py" \
    "${directory}/plan_only_1.log" "${state}" "${phase}" \
    "${directory}/checkpoint.before.json" "${checkpoint}"
  run_machine "${directory}/plan_only_2.log" "${checkpoint}" "${session}" \
    -p mode:=plan_only -p resume:=true
  python3 "${script_dir}/assert_plan_only_resume.py" \
    "${directory}/plan_only_2.log" "${state}" "${phase}" \
    "${directory}/checkpoint.before.json" "${checkpoint}"

  capture_snapshot "${directory}" after
  python3 "${script_dir}/assert_resume_snapshot_unchanged.py" \
    "${directory}/before_snapshot.json" "${directory}/after_snapshot.json"
  python3 "${script_dir}/assert_plan_only_tcp_unchanged.py" \
    "${directory}/plan_only_1.log" "${directory}/plan_only_2.log" "${state}"
  cp "${checkpoint}" "${directory}/checkpoint.after.json"
  sha256sum "${directory}/checkpoint.after.json" \
    >"${directory}/checkpoint.after.sha256"
  cmp -s "${directory}/checkpoint.before.json" \
    "${directory}/checkpoint.after.json"
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

forward_root="${run_root}/forward"
forward_checkpoint="${forward_root}/checkpoint.json"
forward_session="plan-only-forward-${ROS_DOMAIN_ID}-$$-$(date +%s%N)"
reset_fixture "${forward_root}"
execute_stop "${forward_root}/prepare.log" "${forward_checkpoint}" \
  "${forward_session}" PREPARE_OPEN_GRIPPER false

forward_states=(
  MOVE_ABOVE_OBJECT
  DESCEND
  LIFT
  MOVE_ABOVE_PLACE
  DESCEND_TO_PLACE
  RETREAT
)
declare -A bridges=(
  [DESCEND]=ATTACH_MOVEIT
  [DESCEND_TO_PLACE]=SYNC_WORLD_OBJECT
)
for state in "${forward_states[@]}"; do
  state_directory="${forward_root}/${state}"
  plan_only_pair "${state}" FORWARD "${state_directory}" \
    "${forward_checkpoint}" "${forward_session}"
  execute_stop "${state_directory}/execute.log" "${forward_checkpoint}" \
    "${forward_session}" "${state}"
  if [[ -n "${bridges[${state}]:-}" ]]; then
    bridge="${bridges[${state}]}"
    execute_stop "${state_directory}/bridge_to_${bridge}.log" \
      "${forward_checkpoint}" "${forward_session}" "${bridge}"
  fi
done

recovery_root="${run_root}/recovery"
recovery_checkpoint="${recovery_root}/checkpoint.json"
recovery_session="plan-only-recovery-${ROS_DOMAIN_ID}-$$-$(date +%s%N)"
reset_fixture "${recovery_root}"
execute_stop "${recovery_root}/attach_moveit_boundary.log" \
  "${recovery_checkpoint}" "${recovery_session}" ATTACH_MOVEIT false
timeout 120 ros2 run panda_gazebo_demo attach_and_lift_demo --ros-args \
  -p use_sim_time:=true \
  -p plan_lift:=true -p execute_lift:=true -p lift_distance:=0.03 \
  -p lateral_offset_y:=-0.03 >"${recovery_root}/low_carry_fixture.log" 2>&1
sleep 1
capture_snapshot "${recovery_root}" low_carry \
  "${recovery_root}/low_carry_fixture.log"
python3 "${script_dir}/seed_recovery_checkpoint.py" \
  "${recovery_checkpoint}" "${recovery_root}/low_carry_snapshot.json" \
  ATTACH_MOVEIT

recovery_motion_states=(
  RECOVER_LIFT_TO_SAFE_HEIGHT
  RECOVER_MOVE_ABOVE_PICK
  RECOVER_DESCEND_TO_PICK
)
for state in "${recovery_motion_states[@]}"; do
  state_directory="${recovery_root}/${state}"
  plan_only_pair "${state}" RECOVERY "${state_directory}" \
    "${recovery_checkpoint}" "${recovery_session}"
  execute_stop "${state_directory}/execute.log" "${recovery_checkpoint}" \
    "${recovery_session}" "${state}"
done

cleanup_directory="${recovery_root}/cleanup"
mkdir -p "${cleanup_directory}"
execute_stop "${cleanup_directory}/through_sync.log" "${recovery_checkpoint}" \
  "${recovery_session}" RECOVER_SYNC_WORLD_OBJECT
plan_only_pair RECOVER_RETREAT RECOVERY \
  "${recovery_root}/RECOVER_RETREAT" "${recovery_checkpoint}" \
  "${recovery_session}"
execute_stop "${recovery_root}/RECOVER_RETREAT/execute.log" \
  "${recovery_checkpoint}" "${recovery_session}" RECOVER_RETREAT

set +e
run_machine "${recovery_root}/final_error.log" "${recovery_checkpoint}" \
  "${recovery_session}" -p mode:=execute -p resume:=true
final_status=$?
set -e
if [[ "${final_status}" -eq 0 || "${final_status}" -eq 124 ]]; then
  printf 'Recovery finalization returned unexpected status %s\n' \
    "${final_status}" >&2
  exit 1
fi
grep -q 'Run failed: status=ERROR state=ERROR.*code=HEADLESS_RECOVERY_TRIGGER' \
  "${recovery_root}/final_error.log"

printf 'PASS: forward and recovery plan-only/resume matrix; logs: %s\n' \
  "${run_root}"
