#!/usr/bin/env bash
set -euo pipefail
worktree=/data/work/ws_moveit/.worktrees/so101-gazebo-demo-py
evidence_root="${1:-$(mktemp -d /tmp/so101-py-e2e-XXXXXXXX)}"
domain_id="${ROS_DOMAIN_ID:-$((170 + RANDOM % 20))}"
partition="so101_py_e2e_${domain_id}_$$"
export ROS_DOMAIN_ID="$domain_id" GZ_PARTITION="$partition" ROS_LOG_DIR="$evidence_root/ros-logs" SO101_PY_EVIDENCE_DIR="$evidence_root"
mkdir -p "$ROS_LOG_DIR"
set +u
source /opt/ros/jazzy/setup.bash
source "$worktree/install/setup.bash"
set -u
session="so101-py-e2e-$domain_id-$$"
cleanup() { tmux kill-session -t "$session" 2>/dev/null || true; }
trap cleanup EXIT
tmux new-session -d -s "$session" -n stack "bash -lc 'export ROS_DOMAIN_ID=$domain_id GZ_PARTITION=$partition ROS_LOG_DIR=$ROS_LOG_DIR; source /opt/ros/jazzy/setup.bash; source $worktree/install/setup.bash; ros2 launch so101_gazebo_demo_py so101_gazebo.launch.py headless:=true 2>&1 | tee $evidence_root/gazebo.log'"
tmux new-window -t "$session" -n moveit "bash -lc 'export ROS_DOMAIN_ID=$domain_id GZ_PARTITION=$partition ROS_LOG_DIR=$ROS_LOG_DIR; source /opt/ros/jazzy/setup.bash; source $worktree/install/setup.bash; ros2 launch so101_gazebo_demo_py so101_move_group_headless.launch.py 2>&1 | tee $evidence_root/moveit.log'"
ready=false
for _ in $(seq 1 60); do
  attachment_state="$(timeout 2 gz topic -e -t /so101/object_attached -n 1 2>/dev/null || true)"
  if ros2 control list_controllers 2>/dev/null | grep -q 'gripper_controller.*active' \
    && ros2 service type /plan_kinematic_path 2>/dev/null | grep -q GetMotionPlan \
    && grep -Eq '"(attached|detached)"' <<<"$attachment_state"; then ready=true; break; fi
  sleep 1
done
test "$ready" = true
python3 -c 'from so101_gazebo_demo.gazebo.transport import GazeboTransport; assert GazeboTransport().publish_empty("/so101/detach_object")'
detached=false
for _ in $(seq 1 20); do
  attachment_state="$(timeout 2 gz topic -e -t /so101/object_attached -n 1 2>/dev/null || true)"
  if grep -q '"detached"' <<<"$attachment_state"; then detached=true; break; fi
done
test "$detached" = true
ros2 control list_controllers | tee "$evidence_root/controllers.txt"
ros2 run so101_gazebo_demo_py pick_place_state_machine --mode execute --session-id "$partition" --checkpoint "$evidence_root/checkpoint.json" 2>&1 | tee "$evidence_root/state-machine.txt"
python3 "$worktree/src/so101_gazebo_demo_py/test/headless/assert_pick_place_evidence.py" "$evidence_root/live-summary.json"
echo "$evidence_root"
