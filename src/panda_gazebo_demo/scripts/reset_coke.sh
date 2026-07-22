#!/usr/bin/env bash
set -euo pipefail

WORLD_NAME="${WORLD_NAME:-pick_place_world}"
MODEL_NAME="${MODEL_NAME:-coke}"
TIMEOUT_MS="${TIMEOUT_MS:-3000}"
ARM_ACTION="${ARM_ACTION:-/panda_arm_controller/follow_joint_trajectory}"
READY_DURATION_SECONDS="${READY_DURATION_SECONDS:-3}"

CONTROL_SERVICE="/world/${WORLD_NAME}/control"
SET_POSE_SERVICE="/world/${WORLD_NAME}/set_pose"

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

  if ! command -v ros2 >/dev/null 2>&1; then
    printf 'ros2 command not found. Source the ROS environment first.\n' >&2
    return 1
  fi

  action_list="$(ros2 action list)"
  if ! grep -Fxq "${ARM_ACTION}" <<<"${action_list}"; then
    printf 'Arm trajectory action not found: %s\n' "${ARM_ACTION}" >&2
    return 1
  fi

  printf 'Moving Panda arm to ready pose over %s seconds...\n' "${READY_DURATION_SECONDS}"
  ros2 action send_goal --wait "${ARM_ACTION}" control_msgs/action/FollowJointTrajectory \
    "{trajectory: {joint_names: [panda_joint1, panda_joint2, panda_joint3, panda_joint4, panda_joint5, panda_joint6, panda_joint7], points: [{positions: [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785], time_from_start: {sec: ${READY_DURATION_SECONDS}}}]}}"
}

trap resume_world EXIT

if ! command -v gz >/dev/null 2>&1; then
  printf 'gz command not found. Source the Gazebo environment first.\n' >&2
  exit 1
fi

if ! gz service -l | grep -Fxq "${CONTROL_SERVICE}"; then
  printf 'Gazebo control service not found: %s\n' "${CONTROL_SERVICE}" >&2
  exit 1
fi

if ! gz service -l | grep -Fxq "${SET_POSE_SERVICE}"; then
  printf 'Gazebo set_pose service not found: %s\n' "${SET_POSE_SERVICE}" >&2
  exit 1
fi

printf 'Pausing world %s...\n' "${WORLD_NAME}"
call_service "${CONTROL_SERVICE}" gz.msgs.WorldControl 'pause: true'
paused=true

printf 'Resetting %s to (0.3, 0.0, 0.836), identity orientation...\n' "${MODEL_NAME}"
call_service \
  "${SET_POSE_SERVICE}" \
  gz.msgs.Pose \
  "name: \"${MODEL_NAME}\", position: {x: 0.3, y: 0.0, z: 0.836}, orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}"

printf 'Resuming world %s...\n' "${WORLD_NAME}"
call_service "${CONTROL_SERVICE}" gz.msgs.WorldControl 'pause: false'
paused=false
trap - EXIT

printf 'Current %s pose:\n' "${MODEL_NAME}"
gz model -m "${MODEL_NAME}" -p

move_arm_to_ready
