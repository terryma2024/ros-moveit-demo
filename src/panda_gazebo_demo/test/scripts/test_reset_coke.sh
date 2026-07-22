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
  :
elif [[ "$1" == topic && "$2" == -e ]]; then
  printf 'data: "%s"\n' "${FAKE_ATTACHMENT_STATE:-detached}"
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
  PATH="${fake_bin}:${PATH}" \
    COMMAND_LOG="${command_log}" \
    ROS2_COMMAND_LOG="${ros2_command_log}" \
    FAKE_GRIPPER_STATUS="${1:-SUCCEEDED}" \
    FAKE_ATTACHMENT_STATE="${2:-detached}" \
    FAKE_ARM_STATUS="${3:-SUCCEEDED}" \
    EXPECTED_COKE_DETACHED="${4:-}" \
    bash "${reset_script}"
}

run_reset >/dev/null

mapfile -t goal_commands < <(grep '^action send_goal' "${ros2_command_log}")
[[ "${#goal_commands[@]}" -eq 3 ]] ||
  fail "expected open, arm, and close goals, got ${#goal_commands[@]}"
[[ "${goal_commands[0]}" == *'/panda_hand_controller/gripper_cmd'* ]] ||
  fail 'gripper open goal was not sent first'
[[ "${goal_commands[0]}" == *'position: 0.04'* ]] ||
  fail 'first gripper goal did not command the open position'
[[ "${goal_commands[1]}" == *'/panda_arm_controller/follow_joint_trajectory'* ]] ||
  fail 'arm goal was not sent after opening'
[[ "${goal_commands[2]}" == *'/panda_hand_controller/gripper_cmd'* ]] ||
  fail 'gripper close goal was not sent last'
[[ "${goal_commands[2]}" == *'position: 0.0'* ]] ||
  fail 'gripper goal did not command the closed position'

open_line="$(grep -En 'ros2 action send_goal.*position: 0\.04,' "${command_log}" | cut -d: -f1)"
arm_line="$(grep -n 'ros2 action send_goal.*/panda_arm_controller' "${command_log}" | cut -d: -f1)"
reset_line="$(grep -n 'gz service -s /world/pick_place_world/set_pose' "${command_log}" | cut -d: -f1)"
close_line="$(grep -En 'ros2 action send_goal.*position: 0\.0,' "${command_log}" | cut -d: -f1)"
[[ "${open_line}" -lt "${arm_line}" && "${arm_line}" -lt "${reset_line}" &&
  "${reset_line}" -lt "${close_line}" ]] ||
  fail 'reset did not use open, move, reset, close order'

: >"${ros2_command_log}"
: >"${command_log}"
if run_reset SUCCEEDED attached >/dev/null 2>&1; then
  fail 'reset succeeded while Gazebo reported Coke attached'
fi
if grep -Eq 'action send_goal|set_pose' "${command_log}"; then
  fail 'attached reset performed a physical side effect before failing closed'
fi

: >"${ros2_command_log}"
: >"${command_log}"
if ! run_reset SUCCEEDED unknown SUCCEEDED true >/dev/null 2>&1; then
  fail 'reset rejected explicit caller evidence that Coke is detached'
fi
if grep -q 'gz topic -e' "${command_log}"; then
  fail 'reset redundantly subscribed to event-driven state despite caller evidence'
fi

: >"${ros2_command_log}"
if run_reset ABORTED >/dev/null 2>&1; then
  fail 'reset succeeded after the gripper action reported ABORTED'
fi

: >"${ros2_command_log}"
if run_reset SUCCEEDED detached ABORTED >/dev/null 2>&1; then
  fail 'reset succeeded after the arm action reported ABORTED'
fi

printf 'PASS: reset requires detached Coke, then safely opens, moves, resets, and closes\n'
