#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  printf 'usage: %s RESET_SCRIPT\n' "$0" >&2
  exit 2
fi

reset_script="$(realpath "$1")"
test_dir="$(mktemp -d)"
trap 'rm -rf "${test_dir}"' EXIT

fake_bin="${test_dir}/bin"
ros2_command_log="${test_dir}/ros2-commands.log"
command_log="${test_dir}/commands.log"
attachment_state_file="${test_dir}/attachment-state.txt"
mkdir -p "${fake_bin}"

cat >"${fake_bin}/gz" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf 'gz %s\n' "$*" >>"${COMMAND_LOG}"

if [[ "$1" == service && "$2" == -l ]]; then
  printf '%s\n' \
    /world/pick_place_world/control \
    /world/pick_place_world/set_pose
elif [[ "$1" == service ]]; then
  printf 'data: true\n'
elif [[ "$1" == topic && "$2" == -t ]]; then
  if [[ "${FAKE_DETACH_CONVERGES:-true}" == true ]]; then
    printf 'detached\n' >"${ATTACHMENT_STATE_FILE}"
  fi
elif [[ "$1" == topic && "$2" == -e ]]; then
  printf 'data: "%s"\n' "$(<"${ATTACHMENT_STATE_FILE}")"
elif [[ "$1" == model ]]; then
  printf 'pose: mocked\n'
else
  printf 'unexpected gz arguments: %s\n' "$*" >&2
  exit 2
fi
EOF

cat >"${fake_bin}/ros2" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$*" >>"${ROS2_COMMAND_LOG}"
printf 'ros2 %s\n' "$*" >>"${COMMAND_LOG}"

if [[ "$1" == action && "$2" == list ]]; then
  printf '%s\n' \
    /panda_arm_controller/follow_joint_trajectory \
    /panda_hand_controller/gripper_cmd
elif [[ "$1" == action && "$2" == send_goal ]]; then
  status=SUCCEEDED
  if [[ "$*" == *'/panda_hand_controller/gripper_cmd'* ]]; then
    status="${FAKE_GRIPPER_STATUS:-SUCCEEDED}"
  elif [[ "$*" == *'/panda_arm_controller/follow_joint_trajectory'* ]]; then
    status="${FAKE_ARM_STATUS:-SUCCEEDED}"
  fi
  printf 'Goal accepted\nGoal finished with status: %s\n' "${status}"
elif [[ "$1" == run && "$2" == panda_gazebo_demo &&
  "$3" == reset_moveit_world ]]
then
  if [[ "${FAKE_MOVEIT_RESET_STATUS:-SUCCEEDED}" != SUCCEEDED ]]; then
    printf 'MoveIt reset failed\n' >&2
    exit 1
  fi
  printf 'MoveIt reset succeeded\n'
else
  printf 'unexpected ros2 arguments: %s\n' "$*" >&2
  exit 2
fi
EOF

chmod +x "${fake_bin}/gz" "${fake_bin}/ros2"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

run_reset() {
  local initial_attachment="${1:-detached}"
  local detach_converges="${2:-true}"
  local moveit_status="${3:-SUCCEEDED}"
  local expected_detached="${4:-false}"
  printf '%s\n' "${initial_attachment}" >"${attachment_state_file}"
  PATH="${fake_bin}:${PATH}" \
    COMMAND_LOG="${command_log}" \
    ROS2_COMMAND_LOG="${ros2_command_log}" \
    ATTACHMENT_STATE_FILE="${attachment_state_file}" \
    FAKE_DETACH_CONVERGES="${detach_converges}" \
    FAKE_MOVEIT_RESET_STATUS="${moveit_status}" \
    FAKE_GRIPPER_STATUS="${FAKE_GRIPPER_STATUS:-SUCCEEDED}" \
    FAKE_ARM_STATUS="${FAKE_ARM_STATUS:-SUCCEEDED}" \
    EXPECTED_COKE_DETACHED="${expected_detached}" \
    bash "${reset_script}"
}

run_reset attached >/dev/null

grep -Fq 'gz topic -t /panda/detach_coke' "${command_log}" ||
  fail 'Gazebo detach command was not published'
grep -Fq 'ros2 run panda_gazebo_demo reset_moveit_world' "${command_log}" ||
  fail 'MoveIt reset helper was not invoked'

mapfile -t goal_commands < <(grep '^action send_goal' "${ros2_command_log}")
[[ "${#goal_commands[@]}" -eq 3 ]] ||
  fail "expected open, arm, and close goals, got ${#goal_commands[@]}"
[[ "${goal_commands[0]}" == *'/panda_hand_controller/gripper_cmd'* &&
  "${goal_commands[0]}" == *'position: 0.04'* ]] ||
  fail 'gripper open goal was not first'
[[ "${goal_commands[1]}" == *'/panda_arm_controller/follow_joint_trajectory'* ]] ||
  fail 'arm ready goal was not second'
[[ "${goal_commands[2]}" == *'/panda_hand_controller/gripper_cmd'* &&
  "${goal_commands[2]}" == *'position: 0.0'* ]] ||
  fail 'gripper close goal was not last'

detach_line="$(grep -n 'gz topic -t /panda/detach_coke' "${command_log}" | head -1 | cut -d: -f1)"
pose_line="$(grep -n 'gz service -s /world/pick_place_world/set_pose' "${command_log}" | head -1 | cut -d: -f1)"
moveit_line="$(grep -n 'ros2 run panda_gazebo_demo reset_moveit_world' "${command_log}" | head -1 | cut -d: -f1)"
open_line="$(grep -En 'ros2 action send_goal.*position: 0\.04,' "${command_log}" | head -1 | cut -d: -f1)"
arm_line="$(grep -n 'ros2 action send_goal.*/panda_arm_controller' "${command_log}" | head -1 | cut -d: -f1)"
close_line="$(grep -En 'ros2 action send_goal.*position: 0\.0,' "${command_log}" | head -1 | cut -d: -f1)"
[[ "${detach_line}" -lt "${pose_line}" && "${pose_line}" -lt "${moveit_line}" &&
  "${moveit_line}" -lt "${open_line}" && "${open_line}" -lt "${arm_line}" &&
  "${arm_line}" -lt "${close_line}" ]] ||
  fail 'reset command order is not detach, pose, MoveIt, open, ready, close'

: >"${ros2_command_log}"
: >"${command_log}"
if run_reset attached false >/dev/null 2>&1; then
  fail 'reset succeeded without Gazebo detach convergence'
fi
if grep -Eq 'set_pose|ros2 run panda_gazebo_demo reset_moveit_world|action send_goal' \
    "${command_log}"
then
  fail 'detach failure allowed later side effects'
fi

: >"${ros2_command_log}"
: >"${command_log}"
if run_reset attached true FAILED >/dev/null 2>&1; then
  fail 'reset succeeded after MoveIt reset failure'
fi
if grep -q 'action send_goal' "${command_log}"; then
  fail 'MoveIt reset failure allowed arm or gripper motion'
fi

: >"${ros2_command_log}"
: >"${command_log}"
run_reset detached true SUCCEEDED true >/dev/null
grep -Fq 'gz topic -t /panda/detach_coke' "${command_log}" ||
  fail 'caller detach evidence skipped the Gazebo detach command'
grep -Fq 'gz topic -e -t /panda/coke_attached' "${command_log}" ||
  fail 'caller detach evidence skipped final Gazebo validation'

printf 'PASS: reset detaches and synchronizes both worlds before arm initialization\n'
