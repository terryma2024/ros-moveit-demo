# Cup Pose Subscriber Experiment Ledger

## Task registration

```yaml
task_id: cup-pose-subscriber-20260814
status: COMPLETE_WITHOUT_LIVE_ROS_RUNTIME
evidence_root: /tmp/so101-debug-coke-pose-subscriber-20260814
source_commit: 4ff3239ce7d6163523fb6b5a59f3b0482eea50fe
branch: main
runtime: test executable only; no simulator or hardware action
ros_domain_id: unset
gz_partition: unset
install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py
intent: Continuously subscribe to /cup_pose geometry_msgs/msg/PoseStamped, emit every valid input, report invalid input, and exit only on SIGINT or message-inactivity timeout.
```

## Planned RED/GREEN cycle

```yaml
single_variable: rename the pose input contract to cup_pose
initial_boundary: no cup_pose module or console executable exists; the subscriber still uses the former object-specific topic and status codes
red_command: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q src/so101_demo_py/test/test_cup_pose_subscriber.py
green_command: PYTHONPATH=src/so101_demo_py/src:$PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q src/so101_demo_py/test/test_cup_pose_subscriber.py
acceptance: the only public executable is cup_pose_subscriber; it subscribes to /cup_pose; empty frame, non-finite fields, and zero quaternion are reported as one-line CUP_POSE_INVALID records then listening continues; only message inactivity fails closed as CUP_POSE_TIMEOUT; SIGINT exits cleanly; no internal Pose fallback or legacy alias exists.
```

## Result

```yaml
recorded_at: 2026-08-14T17:48:30+08:00
red_result: 12 failures; cup_pose_subscriber module and console-script registration did not yet exist.
green_result: 12 passed with source-first PYTHONPATH and ROS pytest autoload disabled
build_result: colcon build --packages-select so101_demo_py --symlink-install PASS
static_validation:
  git_diff_check: PASS
  installed_executable: install/so101_demo_py/lib/so101_demo_py/cup_pose_subscriber
  stale_executable_removed: former object-specific console-script wrapper
live_ros_runtime: BLOCKED
live_ros_runtime_reason: ros2 itself cannot import rclpy because @rpath/librosidl_typesupport_c.dylib is unavailable in the local Jazzy environment; the failed command is retained in runtime-rclpy-import-failure.log.
conclusion: cup_pose_subscriber continuously emits every received valid PoseStamped, reports CUP_POSE_INVALID for malformed input and continues listening, reports CUP_POSE_TIMEOUT only after no message arrives within the configured inactivity timeout, and exits 0 after SIGINT without creating a fallback pose. Each status report is one terminal line, and cleanup checks rclpy.ok() before shutdown so an already stopped context is not shut down twice.
retained_runs:
  - /tmp/so101-debug-coke-pose-subscriber-20260814
archived_runs: []
deletion_candidates:
  - /tmp/so101-debug-coke-pose-subscriber-20260814
```
