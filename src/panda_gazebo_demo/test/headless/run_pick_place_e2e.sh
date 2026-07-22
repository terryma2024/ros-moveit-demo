#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
package_root="$(cd "${script_dir}/../.." && pwd)"
workspace_root="$(cd "${package_root}/../.." && pwd)"
log_root="${workspace_root}/build/panda_gazebo_demo/test_logs"
runs=1
label="e2e"

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --runs)
      runs="$2"
      shift 2
      ;;
    --label)
      label="$2"
      shift 2
      ;;
    *)
      printf 'unknown argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

[[ "${runs}" =~ ^[1-9][0-9]*$ ]] || {
  printf -- '--runs must be a positive integer\n' >&2
  exit 2
}

unset COLCON_CURRENT_PREFIX
set +u
source /opt/ros/jazzy/setup.bash
source "${workspace_root}/install/setup.bash"
set -u

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-$((100 + $$ % 100))}"
export GZ_PARTITION="${GZ_PARTITION:-panda_pick_place_${label}_$$}"
mkdir -p "${log_root}"
run_root="${log_root}/${label}_$(date +%Y%m%d_%H%M%S)_$$"
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

planning_scene_coke_at_pick() {
  timeout 3 ros2 service call /get_planning_scene \
    moveit_msgs/srv/GetPlanningScene '{components: {components: 24}}' 2>/dev/null |
    grep -Eq "Point\(x=0\.3, y=0\.0, z=0\.836\).*id='coke'"
}

verify_reset_world() {
  local pose attachment
  pose="$(gz model -m coke -p 2>/dev/null)"
  attachment="$(grep 'data:' "${run_root}/attachment_events.txt" | tail -1)"
  python3 -c '
import math, re, sys
match = re.search(r"Pose \[ XYZ \(m\) \] \[ RPY \(rad\) \]:\s*\[\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", sys.argv[1])
raise SystemExit(0 if match and math.dist(tuple(map(float, match.groups())), (0.3, 0.0, 0.836)) <= 0.005 else 1)
' "${pose}" &&
    grep -Eq 'data: *"?detached"?' <<<"${attachment}"
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
gz service -l >"${run_root}/readiness_gazebo_services.txt"
wait_until 45 'MoveGroup' move_group_ready
ros2 node list >"${run_root}/readiness_ros_nodes.txt" 2>&1
wait_until 45 'active controllers' controllers_ready
ros2 control list_controllers >"${run_root}/readiness_controllers.txt" 2>&1
wait_until 20 '/joint_states' joint_states_ready
timeout 3 ros2 topic echo /joint_states --once \
  >"${run_root}/readiness_joint_states.txt" 2>&1
gz topic -t /panda/detach_coke -m gz.msgs.Empty -p 'unused: true'
wait_until 10 'owned world detached state' attachment_output_detached
timeout 3 gz topic -e -t /panda/coke_attached -n 1 \
  >"${run_root}/initial_attachment.txt" 2>&1
grep -Eq 'data: *"?detached"?' "${run_root}/initial_attachment.txt"
cp "${run_root}/initial_attachment.txt" "${run_root}/attachment_events.txt"
gz topic -e -t /panda/coke_attached >>"${run_root}/attachment_events.txt" 2>&1 &
attachment_monitor_pid=$!
wait_until 30 'Planning Scene Coke object' planning_scene_ready
timeout 5 ros2 service call /get_planning_scene \
  moveit_msgs/srv/GetPlanningScene '{components: {components: 24}}' \
  >"${run_root}/readiness_planning_scene.txt" 2>&1

for ((run = 1; run <= runs; ++run)); do
  run_log="${run_root}/run_${run}.log"
  checkpoint="${run_root}/run_${run}_checkpoint.json"
  # The initial readiness probe, or the previous accepted run, established
  # detached state. DetachableJoint is event-driven and does not replay that
  # fact to reset_coke.sh, so pass the already-asserted evidence explicitly.
  EXPECTED_COKE_DETACHED=true "${package_root}/scripts/reset_coke.sh" \
    >"${run_root}/run_${run}_reset.log" 2>&1
  timeout 15 ros2 run panda_gazebo_demo planning_scene_setup \
    >"${run_root}/run_${run}_planning_scene_reset.log" 2>&1
  wait_until 10 'detached Coke at reset pose' verify_reset_world
  wait_until 10 'MoveIt Coke at reset pose' planning_scene_coke_at_pick
  gz model -m coke -p >"${run_root}/run_${run}_reset_gazebo_coke.txt" 2>&1
  grep 'data:' "${run_root}/attachment_events.txt" | tail -1 \
    >"${run_root}/run_${run}_reset_attachment.txt"
  timeout 5 ros2 service call /get_planning_scene \
    moveit_msgs/srv/GetPlanningScene '{components: {components: 24}}' \
    >"${run_root}/run_${run}_reset_planning_scene.txt" 2>&1

  session="${label}-${ROS_DOMAIN_ID}-$$-${run}-$(date +%s%N)"
  if ! timeout 180 ros2 run panda_gazebo_demo pick_place_state_machine \
      --ros-args -p mode:=execute \
      -p simulation_session_id:="${session}" \
      -p checkpoint_path:="${checkpoint}" >"${run_log}" 2>&1; then
    printf 'State machine run %s failed; see %s\n' "${run}" "${run_log}" >&2
    exit 1
  fi

  python3 "${script_dir}/assert_pick_place_log.py" "${run_log}"
  gz model -m coke -p >"${run_root}/run_${run}_final_gazebo_coke.txt" 2>&1
  grep 'data:' "${run_root}/attachment_events.txt" | tail -1 \
    >"${run_root}/run_${run}_final_attachment.txt"
  grep -Eq 'data: *"?detached"?' \
    "${run_root}/run_${run}_final_attachment.txt"
  timeout 3 ros2 topic echo /joint_states --once \
    >"${run_root}/run_${run}_final_joint_states.txt" 2>&1
  timeout 5 ros2 service call /get_planning_scene \
    moveit_msgs/srv/GetPlanningScene '{components: {components: 28}}' \
    >"${run_root}/run_${run}_final_planning_scene.txt" 2>&1
  python3 "${script_dir}/assert_pick_place_snapshot.py" \
    "${run_root}/run_${run}_final_gazebo_coke.txt" \
    "${run_root}/run_${run}_final_attachment.txt" \
    "${run_root}/run_${run}_final_joint_states.txt" \
    "${run_root}/run_${run}_final_planning_scene.txt"
done

printf 'PASS: %s complete headless pick-place run(s); logs: %s\n' \
  "${runs}" "${run_root}"
