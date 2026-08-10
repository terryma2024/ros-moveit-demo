#!/usr/bin/env bash
set -euo pipefail

# macOS System Integrity Protection strips DYLD_* variables while entering the
# /usr/bin/env shebang. Re-source the selected ROS overlay inside this process
# so rclpy and ros2 can find their dylibs again.
if [[ -n "${PANDA_RUNTIME_SETUP:-}" ]]; then
  if [[ ! -r "${PANDA_RUNTIME_SETUP}" ]]; then
    printf 'Runtime setup file is not readable: %s\n' \
      "${PANDA_RUNTIME_SETUP}" >&2
    exit 1
  fi
  set +u
  source "${PANDA_RUNTIME_SETUP}"
  set -u
fi

WORLD_NAME="${WORLD_NAME:-pick_place_world}"
MODEL_NAME="${MODEL_NAME:-coke}"
TIMEOUT_MS="${TIMEOUT_MS:-3000}"
ARM_ACTION="${ARM_ACTION:-/panda_arm_controller/follow_joint_trajectory}"
READY_DURATION_SECONDS="${READY_DURATION_SECONDS:-3}"
ARM_ACTION_TIMEOUT_SECONDS="${ARM_ACTION_TIMEOUT_SECONDS:-10}"
GRIPPER_ACTION="${GRIPPER_ACTION:-/panda_hand_controller/gripper_cmd}"
GRIPPER_OPEN_POSITION="${GRIPPER_OPEN_POSITION:-0.04}"
GRIPPER_CLOSED_POSITION="${GRIPPER_CLOSED_POSITION:-0.0}"
GRIPPER_MAX_EFFORT="${GRIPPER_MAX_EFFORT:-0.0}"
GRIPPER_ACTION_TIMEOUT_SECONDS="${GRIPPER_ACTION_TIMEOUT_SECONDS:-10}"
GAZEBO_DETACH_TOPIC="${GAZEBO_DETACH_TOPIC:-/panda/detach_coke}"
ATTACHMENT_OUTPUT_TOPIC="${ATTACHMENT_OUTPUT_TOPIC:-/panda/coke_attached}"
ATTACHMENT_OBSERVATION_TIMEOUT_SECONDS="${ATTACHMENT_OBSERVATION_TIMEOUT_SECONDS:-3}"
MOVEIT_RESET_PACKAGE="${MOVEIT_RESET_PACKAGE:-panda_gazebo_demo_cpp}"
MOVEIT_RESET_EXECUTABLE="${MOVEIT_RESET_EXECUTABLE:-reset_moveit_world}"
MOVEIT_RESET_TIMEOUT_SECONDS="${MOVEIT_RESET_TIMEOUT_SECONDS:-120}"
EXPECTED_COKE_DETACHED="${EXPECTED_COKE_DETACHED:-false}"
GAZEBO_RESET_POSITION_TOLERANCE="${GAZEBO_RESET_POSITION_TOLERANCE:-0.002}"
GAZEBO_RESET_ORIENTATION_TOLERANCE_RAD="${GAZEBO_RESET_ORIENTATION_TOLERANCE_RAD:-0.02}"
GAZEBO_POSE_OBSERVATION_ATTEMPTS="${GAZEBO_POSE_OBSERVATION_ATTEMPTS:-30}"
GAZEBO_POSE_POLL_INTERVAL_SECONDS="${GAZEBO_POSE_POLL_INTERVAL_SECONDS:-0.1}"
GAZEBO_SERVICE_DISCOVERY_TIMEOUT_SECONDS="${GAZEBO_SERVICE_DISCOVERY_TIMEOUT_SECONDS:-30}"
GAZEBO_SERVICE_DISCOVERY_POLL_INTERVAL_SECONDS="${GAZEBO_SERVICE_DISCOVERY_POLL_INTERVAL_SECONDS:-0.25}"

CONTROL_SERVICE="/world/${WORLD_NAME}/control"
SET_POSE_SERVICE="/world/${WORLD_NAME}/set_pose"
CANONICAL_POSE_REQUEST="name: \"${MODEL_NAME}\", position: {x: 0.3, y: 0.0, z: 0.836}, orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}"

paused=false

call_service() {
  local service="$1"
  local request_type="$2"
  local request="$3"
  local response

  response="$(
    gz service \
      -s "${service}" \
      --reqtype "${request_type}" \
      --reptype gz.msgs.Boolean \
      --timeout "${TIMEOUT_MS}" \
      --req "${request}"
  )"

  printf '%s\n' "${response}"
  if ! grep -q 'data: true' <<<"${response}"; then
    printf 'Gazebo service failed: %s\n' "${service}" >&2
    return 1
  fi
}

resume_world() {
  if [[ "${paused}" == true ]]; then
    gz service \
      -s "${CONTROL_SERVICE}" \
      --reqtype gz.msgs.WorldControl \
      --reptype gz.msgs.Boolean \
      --timeout "${TIMEOUT_MS}" \
      --req 'pause: false' >/dev/null 2>&1 || true
  fi
}

move_arm_to_ready() {
  local action_list
  local response

  action_list="$(ros2 action list)"
  if ! grep -Fxq "${ARM_ACTION}" <<<"${action_list}"; then
    printf 'Arm trajectory action not found: %s\n' "${ARM_ACTION}" >&2
    return 1
  fi

  printf 'Moving Panda arm to ready pose over %s seconds...\n' "${READY_DURATION_SECONDS}"
  if ! response="$(
      ros2 action send_goal -t "${ARM_ACTION_TIMEOUT_SECONDS}" \
        "${ARM_ACTION}" control_msgs/action/FollowJointTrajectory \
        "{trajectory: {joint_names: [panda_joint1, panda_joint2, panda_joint3, panda_joint4, panda_joint5, panda_joint6, panda_joint7], points: [{positions: [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785], time_from_start: {sec: ${READY_DURATION_SECONDS}}}]}}"
    )"; then
    printf '%s\n' "${response}"
    printf 'Failed to send the arm ready goal.\n' >&2
    return 1
  fi
  printf '%s\n' "${response}"
  if ! grep -Fq 'Goal finished with status: SUCCEEDED' <<<"${response}"; then
    printf 'Arm ready action did not succeed.\n' >&2
    return 1
  fi
}

command_gripper() {
  local position="$1"
  local operation="$2"
  local action_list
  local response

  action_list="$(ros2 action list)"
  if ! grep -Fxq "${GRIPPER_ACTION}" <<<"${action_list}"; then
    printf 'Gripper action not found: %s\n' "${GRIPPER_ACTION}" >&2
    return 1
  fi

  printf '%s Panda gripper to position %s...\n' "${operation}" "${position}"
  if ! response="$(
      ros2 action send_goal -t "${GRIPPER_ACTION_TIMEOUT_SECONDS}" \
        "${GRIPPER_ACTION}" control_msgs/action/GripperCommand \
        "{command: {position: ${position}, max_effort: ${GRIPPER_MAX_EFFORT}}}"
    )"; then
    printf '%s\n' "${response}"
    printf 'Failed to send the gripper %s goal.\n' "${operation}" >&2
    return 1
  fi

  printf '%s\n' "${response}"
  if ! grep -Fq 'Goal finished with status: SUCCEEDED' <<<"${response}"; then
    printf 'Gripper %s action did not succeed.\n' "${operation}" >&2
    return 1
  fi
}

request_gazebo_detach() {
  printf 'Requesting Gazebo Coke detach on %s...\n' "${GAZEBO_DETACH_TOPIC}"
  gz topic -t "${GAZEBO_DETACH_TOPIC}" -m gz.msgs.Empty -p 'unused: true'
}

require_detached_coke() {
  local response

  if ! response="$(
      timeout "${ATTACHMENT_OBSERVATION_TIMEOUT_SECONDS}" \
        gz topic -e -t "${ATTACHMENT_OUTPUT_TOPIC}" -n 1
    )"; then
    printf 'Unable to observe Gazebo Coke attachment state on %s.\n' \
      "${ATTACHMENT_OUTPUT_TOPIC}" >&2
    return 1
  fi
  if grep -Eq 'data: *"?attached"?' <<<"${response}"; then
    printf 'Coke remained Gazebo-attached after detach request.\n' >&2
    return 1
  fi
  if ! grep -Eq 'data: *"?detached"?' <<<"${response}"; then
    printf 'Unknown Gazebo Coke attachment state: %s\n' "${response}" >&2
    return 1
  fi
}

reset_moveit_world() {
  printf 'Detaching and synchronizing MoveIt Coke...\n'
  if ! timeout "${MOVEIT_RESET_TIMEOUT_SECONDS}" \
      ros2 run "${MOVEIT_RESET_PACKAGE}" "${MOVEIT_RESET_EXECUTABLE}"
  then
    printf 'MoveIt Coke detach/synchronization failed.\n' >&2
    return 1
  fi
}

preflight_ros_interfaces() {
  local action_list
  local topic_list

  action_list="$(ros2 action list)"
  if ! grep -Fxq "${ARM_ACTION}" <<<"${action_list}"; then
    printf 'Arm trajectory action not found: %s\n' "${ARM_ACTION}" >&2
    return 1
  fi
  if ! grep -Fxq "${GRIPPER_ACTION}" <<<"${action_list}"; then
    printf 'Gripper action not found: %s\n' "${GRIPPER_ACTION}" >&2
    return 1
  fi

  topic_list="$(gz topic -l)"
  if ! grep -Fxq "${GAZEBO_DETACH_TOPIC}" <<<"${topic_list}"; then
    printf 'Gazebo Coke detach topic not found: %s\n' \
      "${GAZEBO_DETACH_TOPIC}" >&2
    return 1
  fi
  if ! grep -Fxq "${ATTACHMENT_OUTPUT_TOPIC}" <<<"${topic_list}"; then
    printf 'Gazebo Coke attachment topic not found: %s\n' \
      "${ATTACHMENT_OUTPUT_TOPIC}" >&2
    return 1
  fi

  if ! timeout "${MOVEIT_RESET_TIMEOUT_SECONDS}" \
      ros2 run "${MOVEIT_RESET_PACKAGE}" "${MOVEIT_RESET_EXECUTABLE}" --help \
      >/dev/null
  then
    printf 'MoveIt world reset helper is unavailable.\n' >&2
    return 1
  fi
}

gazebo_pose_is_canonical() {
  local pose="$1"

  python3 - "${pose}" "${GAZEBO_RESET_POSITION_TOLERANCE}" \
    "${GAZEBO_RESET_ORIENTATION_TOLERANCE_RAD}" <<'PY'
import math
import re
import sys

text = sys.argv[1]
position_tolerance = float(sys.argv[2])
orientation_tolerance = float(sys.argv[3])
match = re.search(
    r"Pose \[ XYZ \(m\) \] \[ RPY \(rad\) \]:\s*"
    r"\[\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\]\s*"
    r"\[\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\]",
    text,
)
if not match:
    raise SystemExit(1)

x, y, z, roll, pitch, yaw = map(float, match.groups())
values = (x, y, z, roll, pitch, yaw, position_tolerance, orientation_tolerance)
if not all(math.isfinite(value) for value in values):
    raise SystemExit(1)

cr, sr = math.cos(roll / 2.0), math.sin(roll / 2.0)
cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
qw = cr * cp * cy + sr * sp * sy
orientation_error = 2.0 * math.acos(min(1.0, abs(qw)))
position_error = math.dist((x, y, z), (0.3, 0.0, 0.836))
raise SystemExit(
    0
    if position_error <= position_tolerance
    and orientation_error <= orientation_tolerance
    else 1
)
PY
}

require_canonical_gazebo_pose() {
  local attempt
  local pose=''

  for ((attempt = 1; attempt <= GAZEBO_POSE_OBSERVATION_ATTEMPTS; ++attempt)); do
    if pose="$(gz model -m "${MODEL_NAME}" -p)" && \
        gazebo_pose_is_canonical "${pose}"
    then
      printf 'Current %s pose:\n%s\n' "${MODEL_NAME}" "${pose}"
      return 0
    fi
    if ((attempt < GAZEBO_POSE_OBSERVATION_ATTEMPTS)); then
      sleep "${GAZEBO_POSE_POLL_INTERVAL_SECONDS}"
    fi
  done

  printf 'Gazebo %s did not converge to the canonical 6D pose. Last observation:\n%s\n' \
    "${MODEL_NAME}" "${pose}" >&2
  return 1
}

wait_for_gazebo_service() {
  local service="$1"
  local deadline=$((SECONDS + GAZEBO_SERVICE_DISCOVERY_TIMEOUT_SECONDS))

  while ((SECONDS <= deadline)); do
    if gz service -l | grep -Fxq "${service}"; then
      return 0
    fi
    sleep "${GAZEBO_SERVICE_DISCOVERY_POLL_INTERVAL_SECONDS}"
  done

  return 1
}

trap resume_world EXIT

if ! command -v gz >/dev/null 2>&1; then
  printf 'gz command not found. Source the Gazebo environment first.\n' >&2
  exit 1
fi
if ! command -v ros2 >/dev/null 2>&1; then
  printf 'ros2 command not found. Source the ROS environment first.\n' >&2
  exit 1
fi
if ! wait_for_gazebo_service "${CONTROL_SERVICE}"; then
  printf 'Gazebo control service not found: %s\n' "${CONTROL_SERVICE}" >&2
  exit 1
fi
if ! wait_for_gazebo_service "${SET_POSE_SERVICE}"; then
  printf 'Gazebo set_pose service not found: %s\n' "${SET_POSE_SERVICE}" >&2
  exit 1
fi
preflight_ros_interfaces

request_gazebo_detach
if [[ "${EXPECTED_COKE_DETACHED}" == true ]]; then
  printf 'Using caller-provided evidence for initial Gazebo detach convergence.\n'
else
  require_detached_coke
fi

printf 'Pausing world %s...\n' "${WORLD_NAME}"
call_service "${CONTROL_SERVICE}" gz.msgs.WorldControl 'pause: true'
paused=true

printf 'Resetting %s to (0.3, 0.0, 0.836), identity orientation...\n' "${MODEL_NAME}"
call_service "${SET_POSE_SERVICE}" gz.msgs.Pose "${CANONICAL_POSE_REQUEST}"
reset_moveit_world

printf 'Resuming world %s...\n' "${WORLD_NAME}"
call_service "${CONTROL_SERVICE}" gz.msgs.WorldControl 'pause: false'
paused=false
require_detached_coke
require_canonical_gazebo_pose

command_gripper "${GRIPPER_OPEN_POSITION}" Opening
move_arm_to_ready
command_gripper "${GRIPPER_CLOSED_POSITION}" Closing

trap - EXIT
