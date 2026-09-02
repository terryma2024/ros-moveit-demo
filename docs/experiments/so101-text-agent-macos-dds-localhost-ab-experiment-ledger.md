# SO-101 Text Agent macOS DDS discovery A/B experiment ledger

```yaml
task_id: so101-text-agent-macos-dds-localhost-ab-20260901
status: COMPLETE
goal: Separate RGB-D subscription matching, first callbacks, and first common stamp, then compare SUBNET and LOCALHOST discovery over the four frozen MuJoCo keyframes on mac-mini.
success_contract: Profiling-off preserves the uninstrumented subscription path; enabled profiling emits complete matched, first-callback, and common-stamp milestones; four SUBNET and four LOCALHOST FULL_RESTART runs use DeepSeek only and satisfy the existing functional and physical acceptance contract.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo
branch: main
base_commit: 7bd5505f2a6a80c8c9c17ebed586c22592cf23e3
tested_candidate_commit: 1e350bd259cffc4b7feab5a42840534aa5ef5d4f
merged_main_commit: c5f69ceb528b199a8fcc3f3b5b0fdb55f76f286a
evidence_root: /tmp/so101-debug-text-agent-macos-dds-localhost-ab-20260901
platform_evidence_root_mac_mini: /tmp/so101-debug-text-agent-macos-dds-localhost-ab-20260901-macmini
confirmed_conclusions:
  - The prior four-keyframe macOS matrix measured perception.wait_synchronized_frame at 3.329 seconds mean, but that span did not distinguish DDS matching, first callback delivery, and RGB-D common-stamp formation.
  - The profiling branch was clean and rebased without conflicts from 1ffd17ab6f8d720d6ff045e81241e727006caf1c onto main 7bd5505f2a6a80c8c9c17ebed586c22592cf23e3, producing f90641bf5896eb30e4144ed6665d847e9faa09f5 before this task's edits.
  - All eight formal mac-mini runs passed the functional, physical, provider, profiling, provenance, and cleanup gates.
  - Endpoint matching completed in 34.213 ms mean for SUBNET and 32.940 ms for LOCALHOST; the paired direction split 2 faster and 2 slower, so the first round does not support a material DDS matching win.
  - The seconds-scale difference occurs after matching, primarily before the first color callback and, in two SUBNET runs, while waiting for a common RGB-D stamp.
disproven_routes:
  - Treating the complete first-frame wait as DDS discovery is unsupported by the existing aggregate span.
  - The first-round data does not support the hypothesis that SUBNET interface discovery materially delays endpoint matching relative to LOCALHOST.
open_hypotheses:
  - The lower LOCALHOST first-color and common-stamp waits may include block-order or warm-cache effects because all SUBNET runs preceded all LOCALHOST runs.
latest_checkpoint: CP-DDS-004
next_experiment: NONE
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
candidate_commit: 1e350bd259cffc4b7feab5a42840534aa5ef5d4f
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
| EXP-DDS-MAC-017 | `SUBNET` | `task_start` | 225 | `so101-dds-subnet-017` |
| EXP-DDS-MAC-018 | `SUBNET` | `cup_test_forward_5cm` | 226 | `so101-dds-subnet-018` |
| EXP-DDS-MAC-019 | `SUBNET` | `cup_test_left_5cm` | 227 | `so101-dds-subnet-019` |
| EXP-DDS-MAC-020 | `SUBNET` | `cup_test_right_5cm` | 228 | `so101-dds-subnet-020` |
| EXP-DDS-MAC-021 | `LOCALHOST` | `task_start` | 229 | `so101-dds-localhost-021` |
| EXP-DDS-MAC-022 | `LOCALHOST` | `cup_test_forward_5cm` | 230 | `so101-dds-localhost-022` |
| EXP-DDS-MAC-023 | `LOCALHOST` | `cup_test_left_5cm` | 231 | `so101-dds-localhost-023` |
| EXP-DDS-MAC-024 | `LOCALHOST` | `cup_test_right_5cm` | 232 | `so101-dds-localhost-024` |

Acceptance requires the existing functional/physical contract plus complete
portable profiling streams. A run is excluded if provider evidence is not
`provider=deepseek` and `fallback_used=false`, if any registered correlation
field differs, or if the discovery range is not the preregistered value.

The local diagnostic folder named `EXP-DDS-MAC-001` is excluded before the
formal matrix. It ran on `matianyideMacBook-Air.local`, not the user-specified
mac-mini, and MuJoCo UI initialization never completed; all three matched
milestones timed out with `pending_count=3`. It is retained as diagnostic
evidence and its identifier is not reused.

The mac-mini folders `EXP-DDS-MAC-009` and `EXP-DDS-MAC-013` are also excluded
before the formal matrix. The inherited dependency environment omitted
`install/mujoco_vendor/opt/mujoco_vendor/lib` from `DYLD_LIBRARY_PATH`, so
`libmujoco_ros2_control.dylib` could not load `libmujoco.3.4.0.dylib` under
either discovery setting. The corrected frozen dependency path passes a direct
`ctypes.CDLL` preflight; the invalid identifiers are not reused.

## Formal matrix results

Times are cumulative from profiled RGB-D subscription construction unless a
column explicitly names a delta. `Callback after match` is
`wait_all_first_callbacks - wait_all_subscriptions_matched`; `Align after
callbacks` is `wait_common_stamp - wait_all_first_callbacks`. These deltas must
not be added to the cumulative columns again.

| Experiment | Range | Keyframe | All matched ms | All first callbacks ms | Common stamp ms | Callback after match ms | Align after callbacks ms | Runtime setup s | Launch total s |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EXP-DDS-MAC-017 | `SUBNET` | `task_start` | 33.108 | 3093.412 | 3590.449 | 3060.304 | 497.038 | 9.986 | 70.311 |
| EXP-DDS-MAC-018 | `SUBNET` | `cup_test_forward_5cm` | 35.959 | 2078.119 | 2078.134 | 2042.160 | 0.015 | 7.117 | 72.163 |
| EXP-DDS-MAC-019 | `SUBNET` | `cup_test_left_5cm` | 35.625 | 3160.344 | 5940.237 | 3124.719 | 2779.893 | 10.203 | 68.566 |
| EXP-DDS-MAC-020 | `SUBNET` | `cup_test_right_5cm` | 32.163 | 2896.335 | 2896.369 | 2864.172 | 0.034 | 8.750 | 71.744 |
| EXP-DDS-MAC-021 | `LOCALHOST` | `task_start` | 33.195 | 1314.360 | 1314.375 | 1281.166 | 0.015 | 3.625 | 66.865 |
| EXP-DDS-MAC-022 | `LOCALHOST` | `cup_test_forward_5cm` | 33.078 | 1706.713 | 1706.729 | 1673.635 | 0.017 | 6.629 | 71.738 |
| EXP-DDS-MAC-023 | `LOCALHOST` | `cup_test_left_5cm` | 32.018 | 294.279 | 294.297 | 262.261 | 0.018 | 4.708 | 63.164 |
| EXP-DDS-MAC-024 | `LOCALHOST` | `cup_test_right_5cm` | 33.470 | 2797.302 | 2816.398 | 2763.832 | 19.096 | 8.551 | 71.366 |

## Aggregate A/B analysis

| Metric | SUBNET mean | LOCALHOST mean | LOCALHOST minus SUBNET | Relative change |
| --- | ---: | ---: | ---: | ---: |
| All subscriptions matched | 34.213 ms | 32.940 ms | -1.273 ms | -3.7% |
| All first callbacks | 2807.052 ms | 1528.163 ms | -1278.889 ms | -45.6% |
| Callback after match | 2772.839 ms | 1495.223 ms | -1277.615 ms | -46.1% |
| First common stamp | 3626.297 ms | 1532.950 ms | -2093.348 ms | -57.7% |
| Align after all first callbacks | 819.245 ms | 4.786 ms | -814.459 ms | -99.4% mean |
| Legacy synchronized-frame wait | 3626.269 ms | 1532.922 ms | -2093.347 ms | -57.7% |
| Runtime setup | 9.014 s | 5.878 s | -3.136 s | -34.8% |
| Stack startup | 14.427 s | 14.500 s | +0.073 s | +0.5% |
| Launch total | 70.696 s | 68.283 s | -2.413 s | -3.4% |

The paired all-matched differences for task-start, forward, left, and right
were `+0.087`, `-2.881`, `-3.607`, and `+1.308` ms respectively. This mixed
direction and the 2.348 ms sample standard deviation are larger than the 1.273
ms mean effect. LOCALHOST is still the safer single-host isolation policy, but
this matrix does not justify claiming a seconds-scale DDS discovery win.

The first-callback split identifies the actual wait. Per-topic SUBNET versus
LOCALHOST means were 96.934 versus 76.389 ms for CameraInfo, 134.161 versus
113.954 ms for Depth, and 2806.886 versus 1528.067 ms for Color. Endpoint
matching itself was tightly grouped at 31.863 to 35.945 ms across every topic
and run. Therefore the large interval includes publisher/render readiness and
sample delivery after matching, not endpoint discovery.

Common-stamp alignment was near zero in six runs. SUBNET task-start added
497.038 ms and SUBNET left added 2779.893 ms; LOCALHOST right added 19.096 ms.
The mean is consequently outlier-sensitive: medians were 248.536 ms for SUBNET
and 0.017 ms for LOCALHOST. The new `wait_common_stamp` and the legacy
`wait_synchronized_frame` agree within tens of microseconds, validating the new
semantic boundary.

Because the matrix used a preregistered block order rather than interleaving,
the first-color/common-stamp improvement cannot yet be assigned solely to
LOCALHOST. A follow-up intended to establish causality should use an
interleaved or ABBA order with repeated keyframes and the same dylib preflight.
DeepSeek plan latency is external-network dominated and is excluded from the
DDS conclusion.

## CP-DDS-003 - final checkpoint

```yaml
checkpoint_id: CP-DDS-003
last_valid_experiment: EXP-DDS-MAC-024
retained_formal_runs: [EXP-DDS-MAC-017, EXP-DDS-MAC-018, EXP-DDS-MAC-019, EXP-DDS-MAC-020, EXP-DDS-MAC-021, EXP-DDS-MAC-022, EXP-DDS-MAC-023, EXP-DDS-MAC-024]
retained_invalid_runs:
  local: [EXP-DDS-MAC-001]
  mac_mini: [EXP-DDS-MAC-009, EXP-DDS-MAC-013]
deletion_candidates: The three invalid diagnostic runs; retained pending explicit user authorization.
functional_acceptance:
  launch_exit_zero: 8/8
  acceptance_exit_zero: 8/8
  deepseek_and_no_fallback: 8/8
  done_with_19_transitions: 8/8
  final_table_contact: 8/8
  attached_object_ids_empty: 8/8
  complete_portable_profile: 8/8
cleanup:
  formal_nodes_after_empty: 8/8
  owned_processes_after: NONE
  ollama_listener_after: ABSENT
evidence_size_mac_mini: 124M
analysis_artifact_mac_mini: /tmp/so101-debug-text-agent-macos-dds-localhost-ab-20260901-macmini/analysis.json
analysis_copy_local: /tmp/so101-debug-text-agent-macos-dds-localhost-ab-20260901/macmini-analysis.json
decision: COMPLETE
next_experiment: NONE
```

## CP-DDS-004 - local main merge and profiling source guide

```yaml
checkpoint_id: CP-DDS-004
last_valid_experiment: EXP-DDS-MAC-024
main_merge:
  method: fast-forward
  from: 7bd5505f2a6a80c8c9c17ebed586c22592cf23e3
  to: c5f69ceb528b199a8fcc3f3b5b0fdb55f76f286a
discovery_contract:
  product_mode: SUBNET
  source_launch_config_changes: NONE
  localhost_content: Historical A/B experiment evidence only; no product discovery setting was changed.
guide: docs/guides/so101-pick-place-profiling-source-guide.md
guide_review:
  humanizer_zh_applied: true
  humanizer_fenced_code_blocks_preserved: true
  local_markdown_links_resolved: true
merged_main_validation:
  isolated_overlay: /tmp/so101-debug-text-agent-macos-dds-localhost-ab-20260901/release/main-overlay-3/install
  build: 2 packages passed
  package_tests: 996 passed
  profiling_off_benchmark: pass=true; text_agent_preview delta 36.871 ns per iteration; dry_run_state_action delta 0.302 ns per iteration
  launch_show_args: profiling choices off, summary, trace; default off
invalid_release_preflights:
  - main-overlay: colcon was absent from the non-direnv PATH; build did not start.
  - main-overlay-2: CMake selected Homebrew Python 3.14 and rosidl_adapter could not import em; package build stopped before so101_demo_py.
retained_evidence_root: /tmp/so101-debug-text-agent-macos-dds-localhost-ab-20260901
archived_runs: NONE
deletion_candidates:
  - release/main-overlay
  - release/main-overlay-2
  - The three invalid DDS diagnostic runs already listed in CP-DDS-003.
owned_processes: NONE
decision: KEEP_AND_PUBLISH_MAIN
next_experiment: NONE
```
