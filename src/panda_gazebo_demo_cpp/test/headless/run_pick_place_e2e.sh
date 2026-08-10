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
if [[ -n "${PANDA_RUNTIME_SETUP:-}" ]]; then
  if [[ ! -r "${PANDA_RUNTIME_SETUP}" ]]; then
    printf 'Runtime setup file is not readable: %s\n' \
      "${PANDA_RUNTIME_SETUP}" >&2
    exit 1
  fi
  source "${PANDA_RUNTIME_SETUP}"
else
  source /opt/ros/jazzy/setup.bash
  source "${workspace_root}/install/setup.bash"
fi
set -u

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-$((100 + $$ % 100))}"
export GZ_PARTITION="${GZ_PARTITION:-panda_pick_place_${label}_$$}"
mkdir -p "${log_root}"
run_root="${log_root}/${label}_$(date +%Y%m%d_%H%M%S)_$$"
mkdir -p "${run_root}"
readiness_completion_gate="${run_root}/readiness_completion_gate"

launch_pid=""
attachment_monitor_pid=""
readiness_probe_pid=""
cleanup() {
  local attempt
  if [[ -n "${readiness_probe_pid}" ]]; then
    kill -TERM "${readiness_probe_pid}" 2>/dev/null || true
    wait "${readiness_probe_pid}" 2>/dev/null || true
  fi
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

probe_milestone_ready() {
  grep -Fq "\"status\": \"$1\"" "${run_root}/readiness_probe.jsonl"
}

configure_controller_manager_wall_time_for_macos() {
  if [[ "${PANDA_FORCE_WALL_TIME:-false}" != true ]]; then
    return 0
  fi

  # gz_ros2_control forces use_sim_time=true even when its YAML says otherwise.
  # On this macOS build that leaves all controllers active but prevents the
  # controller update clock from producing /joint_states. Apply only the manager
  # override first; changing other node clocks before the first state sample can
  # interrupt this transition on macOS.
  timeout 20 ros2 param set /controller_manager use_sim_time false
  sleep 3
  timeout 20 ros2 param get /controller_manager use_sim_time
}

configure_moveit_wall_time_for_macos() {
  if [[ "${PANDA_FORCE_WALL_TIME:-false}" != true ]]; then
    return 0
  fi

  timeout 20 ros2 param set /move_group use_sim_time false
  timeout 20 ros2 param get /move_group use_sim_time
}

attachment_output_detached() {
  timeout 2 gz topic -e -t /panda/coke_attached -n 1 2>/dev/null |
    grep -Eq 'data: *"?detached"?'
}

planning_scene_coke_at_pick() {
  timeout 30 ros2 service call /get_planning_scene \
    moveit_msgs/srv/GetPlanningScene '{components: {components: 24}}' 2>/dev/null |
    grep -Eq "Point\(x=0\.3, y=0\.0, z=0\.836\).*id='coke'"
}

start_new_session() {
  if command -v setsid >/dev/null 2>&1; then
    exec setsid "$@"
  fi
  exec python3 -c \
    'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' \
    "$@"
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

if ros2 node list --no-daemon 2>/dev/null |
    grep -Eq '/(controller_manager|move_group)$'; then
  printf 'Isolated ROS_DOMAIN_ID %s is already in use\n' "${ROS_DOMAIN_ID}" >&2
  exit 1
fi
if gz service -l 2>/dev/null | grep -Fq /world/pick_place_world/control; then
  printf 'Isolated GZ_PARTITION %s is already in use\n' "${GZ_PARTITION}" >&2
  exit 1
fi

printf 'ROS_DOMAIN_ID=%s\nGZ_PARTITION=%s\n' \
  "${ROS_DOMAIN_ID}" "${GZ_PARTITION}" >"${run_root}/environment.txt"
start_new_session ros2 launch panda_gazebo_demo panda_gazebo.launch.py \
  headless:=true run_state_machine:=false >"${run_root}/launch.log" 2>&1 &
launch_pid=$!
python3 "${script_dir}/readiness_probe.py" --timeout 420 \
  --completion-gate "${readiness_completion_gate}" \
  >"${run_root}/readiness_probe.jsonl" \
  2>"${run_root}/readiness_probe.stderr.log" &
readiness_probe_pid=$!

wait_until 180 'Gazebo control service' gazebo_ready
gz service -l >"${run_root}/readiness_gazebo_services.txt"
wait_until 300 'core ROS readiness' probe_milestone_ready CORE_READY
configure_controller_manager_wall_time_for_macos \
  >"${run_root}/readiness_controller_manager_wall_time.txt" 2>&1
touch "${readiness_completion_gate}"
wait_until 120 'complete ROS readiness' probe_milestone_ready ALL_READY
wait "${readiness_probe_pid}"
readiness_probe_pid=""
configure_moveit_wall_time_for_macos \
  >"${run_root}/readiness_moveit_wall_time.txt" 2>&1
gz topic -t /panda/detach_coke -m gz.msgs.Empty -p 'unused: true'
wait_until 10 'owned world detached state' attachment_output_detached
timeout 3 gz topic -e -t /panda/coke_attached -n 1 \
  >"${run_root}/initial_attachment.txt" 2>&1
grep -Eq 'data: *"?detached"?' "${run_root}/initial_attachment.txt"
cp "${run_root}/initial_attachment.txt" "${run_root}/attachment_events.txt"
gz topic -e -t /panda/coke_attached >>"${run_root}/attachment_events.txt" 2>&1 &
attachment_monitor_pid=$!
for ((run = 1; run <= runs; ++run)); do
  run_log="${run_root}/run_${run}.log"
  checkpoint="${run_root}/run_${run}_checkpoint.json"
  # The initial readiness probe, or the previous accepted run, established
  # detached state. DetachableJoint is event-driven and does not replay that
  # fact to reset_world.sh, so pass the already-asserted evidence explicitly.
  EXPECTED_COKE_DETACHED=true "${package_root}/scripts/reset_world.sh" \
    >"${run_root}/run_${run}_reset.log" 2>&1
  timeout 30 ros2 service call /get_planning_scene \
    moveit_msgs/srv/GetPlanningScene '{components: {components: 28}}' \
    >"${run_root}/run_${run}_reset_moveit.txt" 2>&1
  python3 "${script_dir}/assert_reset_moveit_scene.py" \
    "${run_root}/run_${run}_reset_moveit.txt"
  wait_until 10 'detached Coke at reset pose' verify_reset_world
  wait_until 10 'MoveIt Coke at reset pose' planning_scene_coke_at_pick
  gz model -m coke -p >"${run_root}/run_${run}_reset_gazebo_coke.txt" 2>&1
  grep 'data:' "${run_root}/attachment_events.txt" | tail -1 \
    >"${run_root}/run_${run}_reset_attachment.txt"
  timeout 30 ros2 service call /get_planning_scene \
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
  timeout 10 ros2 topic echo /joint_states --once \
    >"${run_root}/run_${run}_final_joint_states.txt" 2>&1
  timeout 30 ros2 service call /get_planning_scene \
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
