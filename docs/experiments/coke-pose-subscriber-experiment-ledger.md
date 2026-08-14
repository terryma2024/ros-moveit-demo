# Coke Pose Subscriber Experiment Ledger

## Task registration

```yaml
task_id: coke-pose-subscriber-20260814
status: COMPLETE_WITHOUT_LIVE_ROS_RUNTIME
evidence_root: /tmp/so101-debug-coke-pose-subscriber-20260814
source_commit: 25f0aa98ae5594af028e6d20d4f37f667d723ebd
branch: main
runtime: test executable only; no simulator or hardware action
ros_domain_id: unset
gz_partition: unset
install_overlay: not built
intent: Subscribe once to /coke_pose geometry_msgs/msg/PoseStamped, validate input, and fail closed on invalid input or timeout.
```

## Planned RED/GREEN cycle

```yaml
single_variable: add coke_pose_subscriber executable and its validation boundary
initial_boundary: no module or executable exists
red_command: python3 -m pytest -q src/so101_demo_py/test/test_coke_pose_subscriber.py
green_command: python3 -m pytest -q src/so101_demo_py/test/test_coke_pose_subscriber.py
acceptance: valid external message is returned unchanged; empty frame, non-finite fields, zero quaternion, and missing message fail closed; no internal Pose fallback exists.
```

## Result

```yaml
recorded_at: 2026-08-14T00:48:00+08:00
red_result: 8 failures; missing coke_pose_subscriber module and setup entrypoint
green_result: 8 passed
static_validation:
  py_compile: PASS
  git_diff_check: PASS
live_ros_runtime: NOT_RUN
live_ros_runtime_reason: ros2 and /opt/ros/jazzy/setup.zsh are unavailable in this checkout environment
conclusion: The new executable is fail-closed: it accepts only the received valid PoseStamped, reports COKE_POSE_INVALID for malformed input, and reports COKE_POSE_TIMEOUT without creating a fallback pose.
retained_runs:
  - /tmp/so101-debug-coke-pose-subscriber-20260814
archived_runs: []
deletion_candidates:
  - /tmp/so101-debug-coke-pose-subscriber-20260814
```
