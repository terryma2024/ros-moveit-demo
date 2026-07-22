#!/usr/bin/env bash
set -euo pipefail

WORLD_NAME="${WORLD_NAME:-pick_place_world}"
MODEL_NAME="${MODEL_NAME:-coke}"
TIMEOUT_MS="${TIMEOUT_MS:-3000}"
ARM_ACTION="${ARM_ACTION:-/panda_arm_controller/follow_joint_trajectory}"
READY_DURATION_SECONDS="${READY_DURATION_SECONDS:-3}"
ARM_ACTION_TIMEOUT_SECONDS="${ARM_ACTION_TIMEOUT_SECONDS:-10}"
GRIPPER_ACTION="${GRIPPER_ACTION:-/panda_hand_controller/gripper_cmd}"
GRIPPER_CLOSED_POSITION="${GRIPPER_CLOSED_POSITION:-0.0}"
GRIPPER_MAX_EFFORT="${GRIPPER_MAX_EFFORT:-0.0}"
GRIPPER_ACTION_TIMEOUT_SECONDS="${GRIPPER_ACTION_TIMEOUT_SECONDS:-10}"

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
  ros2 action send_goal -t "${ARM_ACTION_TIMEOUT_SECONDS}" \
    "${ARM_ACTION}" control_msgs/action/FollowJointTrajectory \
    "{trajectory: {joint_names: [panda_joint1, panda_joint2, panda_joint3, panda_joint4, panda_joint5, panda_joint6, panda_joint7], points: [{positions: [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785], time_from_start: {sec: ${READY_DURATION_SECONDS}}}]}}"
}

close_gripper() {
  local action_list
  local response

  action_list="$(ros2 action list)"
  if ! grep -Fxq "${GRIPPER_ACTION}" <<<"${action_list}"; then
    printf 'Gripper action not found: %s\n' "${GRIPPER_ACTION}" >&2
    return 1
  fi

  printf 'Closing Panda gripper to position %s...\n' "${GRIPPER_CLOSED_POSITION}"
  if ! response="$(
      ros2 action send_goal -t "${GRIPPER_ACTION_TIMEOUT_SECONDS}" \
        "${GRIPPER_ACTION}" control_msgs/action/GripperCommand \
        "{command: {position: ${GRIPPER_CLOSED_POSITION}, max_effort: ${GRIPPER_MAX_EFFORT}}}"
    )"; then
    printf '%s\n' "${response}"
    printf 'Failed to send the gripper close goal.\n' >&2
    return 1
  fi

  printf '%s\n' "${response}"
  if ! grep -Fq 'Goal finished with status: SUCCEEDED' <<<"${response}"; then
    printf 'Gripper close action did not succeed.\n' >&2
    return 1
  fi
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
close_gripper
