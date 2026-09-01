# SO-101 Text Agent macOS DDS discovery A/B experiment ledger

```yaml
task_id: so101-text-agent-macos-dds-localhost-ab-20260901
goal: Separate RGB-D subscription matching, first callbacks, and first common stamp, then compare SUBNET and LOCALHOST discovery over the four frozen MuJoCo keyframes on mac-mini.
success_contract: Profiling-off preserves the uninstrumented subscription path; enabled profiling emits complete matched, first-callback, and common-stamp milestones; four SUBNET and four LOCALHOST FULL_RESTART runs use DeepSeek only and satisfy the existing functional and physical acceptance contract.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/so101-cross-platform-profiling
branch: codex/so101-cross-platform-profiling
base_commit: 7bd5505f2a6a80c8c9c17ebed586c22592cf23e3
current_commit: f90641bf5896eb30e4144ed6665d847e9faa09f5
evidence_root: /tmp/so101-debug-text-agent-macos-dds-localhost-ab-20260901
confirmed_conclusions:
  - The prior four-keyframe macOS matrix measured perception.wait_synchronized_frame at 3.329 seconds mean, but that span did not distinguish DDS matching, first callback delivery, and RGB-D common-stamp formation.
  - The profiling branch was clean and rebased without conflicts from 1ffd17ab6f8d720d6ff045e81241e727006caf1c onto main 7bd5505f2a6a80c8c9c17ebed586c22592cf23e3, producing f90641bf5896eb30e4144ed6665d847e9faa09f5 before this task's edits.
disproven_routes:
  - Treating the complete first-frame wait as DDS discovery is unsupported by the existing aggregate span.
open_hypotheses:
  - SUBNET discovery across macOS network interfaces delays endpoint matching relative to LOCALHOST.
  - If matching is fast under both settings, Open3D and ROS runtime construction or callback delivery dominate the observed wait.
latest_checkpoint: CP-DDS-002
next_experiment: EXP-DDS-MAC-001
```

## CP-DDS-001 - rebased implementation start

```yaml
checkpoint_id: CP-DDS-001
last_valid_experiment: NONE
current_hypothesis: The existing wait_synchronized_frame span combines at least three independently measurable boundaries.
working_tree_status: Test-only RED changes in src/so101_demo_py/test/test_rgbd_cup_pose.py plus this new ledger.
owned_processes: NONE
preserved_processes: All unrelated local and remote processes; local process inventory was unavailable because macOS sysmon denied pgrep.
confirmed_conclusions:
  - Existing profiling-off construction passes no QoS event callbacks.
  - ROS 2 Jazzy rclpy exposes SubscriptionEventCallbacks.matched and Node.create_subscription(event_callbacks=...).
disproven_routes:
  - NONE
open_risks:
  - QoS matched events are RMW capabilities and require live Fast DDS verification after unit and package tests.
next_command: Build an isolated macOS so101_demo_py overlay under the registered evidence root and run the RED milestone test.
```

## CP-DDS-002 - milestone implementation green

```yaml
checkpoint_id: CP-DDS-002
last_valid_experiment: NONE
candidate_commit: PENDING
implementation:
  profiling_enabled:
    - perception.subscription_matched per topic on the first positive current_count
    - perception.first_callback per topic with source_stamp_ns
    - perception.common_stamp on the first aligned RGB-D source stamp
    - perception.wait_all_subscriptions_matched cumulative span
    - perception.wait_all_first_callbacks cumulative span
    - perception.wait_common_stamp cumulative span
  profiling_disabled:
    - The original three create_subscription calls and callbacks remain the direct path.
    - SubscriptionEventCallbacks is neither imported nor constructed.
red_evidence: tests/red.log reports the expected KeyError for the absent event_callbacks before implementation; the profiling-off test passed.
green_evidence:
  - tests/green-targeted.log: 2 passed
  - tests/rgbd-cup-pose.log: 55 passed
  - tests/package-green.log: 996 passed
  - tests/profiling-off-benchmark.log: pass=true; text_agent_preview delta 22.654 ns per iteration within the 100 ns limit; dry_run_state_action delta -0.183 ns per iteration
confirmed_conclusions:
  - QoS matched events are created only for enabled profiling.
  - All pending milestone spans finish idempotently with the runtime timeout, error, or interruption outcome.
  - The package suite passes against an isolated candidate overlay containing both so101_demo_py and so101_mujoco_support.
open_risks:
  - Live Fast DDS must prove that macOS emits matched events and that all three milestones complete.
next_command: Complete package validation, commit the installed candidate, then run EXP-DDS-MAC-001.
```

## Preregistered macOS discovery matrix

All eight runs are independent `FULL_RESTART` executions with `headless=false`,
`sensor_rendering=true`, `rmw_fastrtps_cpp`, profiling `summary`, the instruction
`Pick the plastic cup. Apply no constraints.`, DeepSeek only, and no Ollama
process. The sole A/B variable is `ROS_AUTOMATIC_DISCOVERY_RANGE`.

| Experiment | Discovery range | Keyframe | ROS domain | GZ partition |
| --- | --- | --- | ---: | --- |
| EXP-DDS-MAC-001 | `SUBNET` | `task_start` | 217 | `so101-dds-subnet-001` |
| EXP-DDS-MAC-002 | `SUBNET` | `cup_test_forward_5cm` | 218 | `so101-dds-subnet-002` |
| EXP-DDS-MAC-003 | `SUBNET` | `cup_test_left_5cm` | 219 | `so101-dds-subnet-003` |
| EXP-DDS-MAC-004 | `SUBNET` | `cup_test_right_5cm` | 220 | `so101-dds-subnet-004` |
| EXP-DDS-MAC-005 | `LOCALHOST` | `task_start` | 221 | `so101-dds-localhost-005` |
| EXP-DDS-MAC-006 | `LOCALHOST` | `cup_test_forward_5cm` | 222 | `so101-dds-localhost-006` |
| EXP-DDS-MAC-007 | `LOCALHOST` | `cup_test_left_5cm` | 223 | `so101-dds-localhost-007` |
| EXP-DDS-MAC-008 | `LOCALHOST` | `cup_test_right_5cm` | 224 | `so101-dds-localhost-008` |

Acceptance requires the existing functional/physical contract plus complete
portable profiling streams. A run is excluded if provider evidence is not
`provider=deepseek` and `fallback_used=false`, if any registered correlation
field differs, or if the discovery range is not the preregistered value.
