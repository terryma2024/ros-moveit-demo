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
mkdir -p "${fake_bin}"

cat >"${fake_bin}/gz" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ "$1" == service && "$2" == -l ]]; then
  printf '%s\n' \
    /world/pick_place_world/control \
    /world/pick_place_world/set_pose
elif [[ "$1" == service ]]; then
  printf 'data: true\n'
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

if [[ "$1" == action && "$2" == list ]]; then
  printf '%s\n' \
    /panda_arm_controller/follow_joint_trajectory \
    /panda_hand_controller/gripper_cmd
elif [[ "$1" == action && "$2" == send_goal ]]; then
  status=SUCCEEDED
  if [[ "$*" == *'/panda_hand_controller/gripper_cmd'* ]]; then
    status="${FAKE_GRIPPER_STATUS:-SUCCEEDED}"
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
    ROS2_COMMAND_LOG="${ros2_command_log}" \
    FAKE_GRIPPER_STATUS="${1:-SUCCEEDED}" \
    bash "${reset_script}"
}

run_reset >/dev/null

mapfile -t goal_commands < <(grep '^action send_goal' "${ros2_command_log}")
[[ "${#goal_commands[@]}" -eq 2 ]] ||
  fail "expected arm and gripper goals, got ${#goal_commands[@]}"
[[ "${goal_commands[0]}" == *'/panda_arm_controller/follow_joint_trajectory'* ]] ||
  fail 'arm goal was not sent first'
[[ "${goal_commands[1]}" == *'/panda_hand_controller/gripper_cmd'* ]] ||
  fail 'gripper goal was not sent second'
[[ "${goal_commands[1]}" == *'position: 0.0'* ]] ||
  fail 'gripper goal did not command the closed position'

: >"${ros2_command_log}"
if run_reset ABORTED >/dev/null 2>&1; then
  fail 'reset succeeded after the gripper action reported ABORTED'
fi

printf 'PASS: reset closes the gripper and rejects unsuccessful gripper results\n'
