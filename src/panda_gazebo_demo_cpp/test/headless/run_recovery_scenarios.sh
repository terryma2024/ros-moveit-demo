#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
package_root="$(cd "${script_dir}/../.." && pwd)"
workspace_root="$(cd "${package_root}/../.." && pwd)"
log_root="${workspace_root}/build/panda_gazebo_demo_cpp/test_logs"

unset COLCON_CURRENT_PREFIX
set +u
source /opt/ros/jazzy/setup.bash
source "${workspace_root}/install/setup.bash"
set -u

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-$((100 + $$ % 100))}"
export GZ_PARTITION="${GZ_PARTITION:-panda_pick_place_recovery_$$}"
run_root="${log_root}/recovery_$(date +%Y%m%d_%H%M%S)_$$"
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
    moveit_msgs/srv/GetPlanningScene '{components: {components: 24}}' 2>/dev/null |
    grep -q "id='coke'"
}

last_attachment_is_detached() {
  grep 'data:' "${run_root}/attachment_events.txt" | tail -1 |
    grep -Eq 'data: *"?detached"?'
}

reset_fixture() {
  local scenario_dir="$1"
  last_attachment_is_detached
  EXPECTED_COKE_DETACHED=true "${package_root}/scripts/reset_world.sh" \
    >"${scenario_dir}/reset.log" 2>&1
  timeout 5 ros2 service call /get_planning_scene \
    moveit_msgs/srv/GetPlanningScene '{components: {components: 28}}' \
    >"${scenario_dir}/reset_moveit.txt" 2>&1
  python3 "${script_dir}/assert_reset_moveit_scene.py" \
    "${scenario_dir}/reset_moveit.txt"
}

seed_recovery_checkpoint() {
  local checkpoint="$1"
  local failed_state="$2"
  python3 - "${checkpoint}" "${failed_state}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
checkpoint = json.loads(path.read_text(encoding='utf-8'))
checkpoint['phase'] = 'RECOVERY'
checkpoint['failed_state'] = sys.argv[2]
checkpoint['original_failure'] = {
    'category': 4,
    'code': 'HEADLESS_RECOVERY_TRIGGER',
    'message': 'Recovery checkpoint seeded from an observed forward boundary',
    'metrics': {},
}
# This value is intentionally only a hint: recovery resume must ignore it and
# reclassify the live Gazebo / MoveIt attachment facts through RecoveryPolicy.
checkpoint['next_state'] = 'RECOVER_RETREAT'
temporary = path.with_suffix(path.suffix + '.tmp')
temporary.write_text(json.dumps(checkpoint, indent=2) + '\n', encoding='utf-8')
temporary.replace(path)
PY
}

assert_recovery_log() {
  local log_file="$1"
  local expected_states="$2"
  local actual_states
  actual_states="$(sed -n \
      's/.*STATE_TRANSITION state=\([^ ]*\) next_state=.*/\1/p' \
      "${log_file}" | paste -sd, -)"
  [[ "${actual_states}" == "${expected_states}" ]] || {
    printf 'Unexpected recovery order\nexpected: %s\nactual:   %s\n' \
      "${expected_states}" "${actual_states}" >&2
    return 1
  }
  grep -q 'CHECKPOINT_PHASE=RECOVERY' "${log_file}"
  grep -q 'Run failed: status=ERROR state=ERROR.*code=HEADLESS_RECOVERY_TRIGGER' \
    "${log_file}"
  if grep -q 'Run completed: status=DONE' "${log_file}"; then
    printf 'Recovery fixture incorrectly reached DONE\n' >&2
    return 1
  fi
}

capture_and_assert_final() {
  local scenario_dir="$1"
  local expected_x="$2"
  local expected_y="$3"
  local expected_z="$4"
  gz model -m coke -p >"${scenario_dir}/final_gazebo_coke.txt" 2>&1
  grep 'data:' "${run_root}/attachment_events.txt" | tail -1 \
    >"${scenario_dir}/final_attachment.txt"
  timeout 3 ros2 topic echo /joint_states --once \
    >"${scenario_dir}/final_joint_states.txt" 2>&1
  timeout 5 ros2 service call /get_planning_scene \
    moveit_msgs/srv/GetPlanningScene '{components: {components: 28}}' \
    >"${scenario_dir}/final_planning_scene.txt" 2>&1
  python3 "${script_dir}/assert_pick_place_snapshot.py" \
    "${scenario_dir}/final_gazebo_coke.txt" \
    "${scenario_dir}/final_attachment.txt" \
    "${scenario_dir}/final_joint_states.txt" \
    "${scenario_dir}/final_planning_scene.txt" \
    "${expected_x}" "${expected_y}" "${expected_z}"
}

run_scenario() {
  local name="$1"
  local stop_after="$2"
  local failed_state="$3"
  local expected_states="$4"
  local expected_y="$5"
  local detach_gazebo="${6:-false}"
  local scenario_dir="${run_root}/${name}"
  local checkpoint="${scenario_dir}/checkpoint.json"
  local session="recovery-${name}-${ROS_DOMAIN_ID}-$$-$(date +%s%N)"
  local resume_status
  mkdir -p "${scenario_dir}"

  reset_fixture "${scenario_dir}"
  timeout 180 ros2 run panda_gazebo_demo_cpp pick_place_state_machine \
    --ros-args -p mode:=execute -p stop_after:="${stop_after}" \
    -p simulation_session_id:="${session}" -p checkpoint_path:="${checkpoint}" \
    >"${scenario_dir}/forward.log" 2>&1
  grep -q "Run completed: status=CHECKPOINT_COMPLETE current_state=${stop_after}" \
    "${scenario_dir}/forward.log"

  if [[ "${detach_gazebo}" == true ]]; then
    gz topic -t /panda/detach_coke -m gz.msgs.Empty -p 'unused: true'
    wait_until 5 'Gazebo-detached recovery fixture' last_attachment_is_detached
    sleep 1
  fi

  seed_recovery_checkpoint "${checkpoint}" "${failed_state}"
  set +e
  timeout 240 ros2 run panda_gazebo_demo_cpp pick_place_state_machine \
    --ros-args -p mode:=execute -p resume:=true \
    -p simulation_session_id:="${session}" -p checkpoint_path:="${checkpoint}" \
    >"${scenario_dir}/recovery.log" 2>&1
  resume_status=$?
  set -e
  if [[ "${resume_status}" -eq 0 || "${resume_status}" -eq 124 ]]; then
    printf 'Recovery %s returned unexpected status %s\n' \
      "${name}" "${resume_status}" >&2
    return 1
  fi
  assert_recovery_log "${scenario_dir}/recovery.log" "${expected_states}"
  capture_and_assert_final "${scenario_dir}" 0.3 "${expected_y}" 0.836
  printf 'PASS: recovery scenario %s\n' "${name}"
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
setsid ros2 launch panda_gazebo_demo_cpp panda_gazebo.launch.py \
  headless:=true run_state_machine:=false >"${run_root}/launch.log" 2>&1 &
launch_pid=$!

wait_until 45 'Gazebo control service' gazebo_ready
wait_until 45 'MoveGroup' move_group_ready
wait_until 45 'active controllers' controllers_ready
wait_until 20 '/joint_states' joint_states_ready
gz topic -t /panda/detach_coke -m gz.msgs.Empty -p 'unused: true'
wait_until 10 'owned world detached state' attachment_output_detached
timeout 3 gz topic -e -t /panda/coke_attached -n 1 \
  >"${run_root}/initial_attachment.txt" 2>&1
grep -Eq 'data: *"?detached"?' "${run_root}/initial_attachment.txt"
cp "${run_root}/initial_attachment.txt" "${run_root}/attachment_events.txt"
gz topic -e -t /panda/coke_attached >>"${run_root}/attachment_events.txt" 2>&1 &
attachment_monitor_pid=$!
wait_until 30 'Planning Scene Coke object' planning_scene_ready

cleanup_states='RECOVER_OPEN_GRIPPER,RECOVER_DETACH_GAZEBO,RECOVER_DETACH_MOVEIT,RECOVER_SYNC_WORLD_OBJECT,RECOVER_RETREAT'
safe_carrying_states='RECOVER_DESCEND_TO_PICK,'"${cleanup_states}"
moveit_only_states='RECOVER_DETACH_MOVEIT,RECOVER_SYNC_WORLD_OBJECT,RECOVER_RETREAT'
run_scenario gazebo_only ATTACH_GAZEBO ATTACH_MOVEIT "${cleanup_states}" 0.0
run_scenario both_attached LIFT MOVE_ABOVE_PLACE "${safe_carrying_states}" 0.0
run_scenario moveit_only OPEN_GRIPPER DETACH_GAZEBO "${moveit_only_states}" 0.2 true

printf 'PASS: all recovery scenarios; logs: %s\n' "${run_root}"
