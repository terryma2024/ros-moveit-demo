# SO-101 Text Agent dual-platform four-point profiling experiment ledger

```yaml
task_id: so101-text-agent-dual-platform-four-point-profiling-20260831
status: COMPLETE_WITH_MACOS_VISUAL_EVIDENCE_GAP
goal: Run DeepSeek-driven Text Agent RGB-D pick-place at four frozen MuJoCo cup keyframes on mac-mini and ai-station and compare the correlated profiling results.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/so101-cross-platform-profiling
branch: codex/so101-cross-platform-profiling
source_commit: 1a00ce20167ef3fcac53fc45c74ca6c7a0fba4ba
local_evidence_root: /tmp/so101-debug-text-agent-dual-profile-20260831-071156
platform_evidence_roots:
  mac_mini: /tmp/so101-debug-text-agent-dual-profile-20260831-071156
  ai_station: /data/work/so101-evidence/so101-text-agent-dual-profile/20260831T071156Z
retained_runs:
  mac_mini: [EXP-MAC-017, EXP-MAC-018, EXP-MAC-019, EXP-MAC-020]
  ai_station: [EXP-LNX-013, EXP-LNX-014, EXP-LNX-015, EXP-LNX-016]
archived_runs: []
deletion_candidates:
  - Invalid preflight and capture-diagnostic runs under both registered roots; retained pending explicit authorization.
confirmed_conclusions:
  - All eight measured runs used provider=deepseek, fallback_used=false, and model=deepseek-v4-flash.
  - No Ollama process or active Ollama user service was present before or after the measured matrices; no process needed to be stopped.
  - All eight measured runs produced 640x480 RGB-D cup poses, reached RUNTIME_COMPLETED and DONE with 19 transitions, ended with table_contact=true, and left no MoveIt attached object.
  - All eight portable profiling manifests are complete with no malformed, mismatched, or incomplete streams.
  - Linux additionally produced four readable ros2_tracing CTF sessions totaling 14812202 decoded events, and removed every LTTng session at shutdown.
  - Linux exact-window captures visually show the cup in the target ring in all four runs.
  - macOS exact-window capture was denied by the SSH responsibility chain after the window ID was frozen; desktop or coordinate-crop substitutes were not used.
latest_checkpoint: CP-003
next_experiment: NONE
```

## Measured matrix

All rows used `FULL_RESTART`, `headless=false`, `sensor_rendering=true`, the instruction `Pick the plastic cup. Apply no constraints.`, unique ROS domains and GZ partitions, and the exact installed profiling candidate at commit `1a00ce20167ef3fcac53fc45c74ca6c7a0fba4ba`.

| Experiment | Host | Keyframe | Domain | Backend | Launch s | Runtime s | Planner s | Result |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | --- |
| EXP-MAC-017 | mac-mini | `task_start` | 213 | portable | 67.649 | 52.293 | 0.574 | functional/profile pass; window capture TCC denied |
| EXP-MAC-018 | mac-mini | `cup_test_forward_5cm` | 214 | portable | 72.566 | 56.629 | 0.888 | functional/profile pass; window capture TCC denied |
| EXP-MAC-019 | mac-mini | `cup_test_left_5cm` | 215 | portable | 65.759 | 50.267 | 0.574 | functional/profile pass; window capture TCC denied |
| EXP-MAC-020 | mac-mini | `cup_test_right_5cm` | 216 | portable | 72.435 | 56.885 | 0.645 | functional/profile pass; window capture TCC denied |
| EXP-LNX-013 | ai-station | `task_start` | 205 | portable + ros2_tracing | 59.907 | 56.080 | 1.066 | full pass |
| EXP-LNX-014 | ai-station | `cup_test_forward_5cm` | 206 | portable + ros2_tracing | 66.283 | 62.367 | 1.166 | full pass |
| EXP-LNX-015 | ai-station | `cup_test_left_5cm` | 207 | portable + ros2_tracing | 57.956 | 53.942 | 1.451 | full pass |
| EXP-LNX-016 | ai-station | `cup_test_right_5cm` | 208 | portable + ros2_tracing | 62.142 | 58.618 | 0.955 | full pass |

## Aggregate timing

Values are arithmetic mean over the four frozen keyframes. The percent column is `(Linux / macOS - 1) * 100`; negative values favor Linux.

| Span | macOS mean | Linux mean | Linux versus macOS |
| --- | ---: | ---: | ---: |
| `launch.total` | 69.602 s | 61.572 s | -11.5% |
| `launch.stack_startup` | 14.266 s | 2.296 s | -83.9% |
| `agent.plan` | 0.670 s | 1.160 s | +73.0% |
| `perception.wait_synchronized_frame` | 3.329 s | 0.582 s | -82.5% |
| `perception.estimate_cup_pose` | 8.412 ms | 42.229 ms | +402.0% mean; Linux median is 17.464 ms because one run was 118.246 ms |
| `runtime.setup` | 8.271 s | 3.787 s | -54.2% |
| `runtime.total` | 54.018 s | 57.752 s | +6.9% |
| `runtime.state.DESCEND` | 8.093 s | 9.963 s | +23.1% |
| `runtime.state.MOVE_ABOVE_PLACE` | 9.631 s | 11.444 s | +18.8% |
| `runtime.state.DESCEND_TO_PLACE` | 7.429 s | 9.431 s | +26.9% |
| `runtime.state.RETREAT` | 3.350 s | 3.798 s | +13.4% |

The end-to-end advantage on Linux comes from startup, camera readiness, and runtime setup. Once physical motion starts, macOS is faster in the dominant trajectory states. DeepSeek latency is external-network dominated and should not be treated as a host CPU benchmark.

## Functional and physical evidence

| Check | macOS | Linux |
| --- | --- | --- |
| DeepSeek only | 4/4 | 4/4 |
| Synchronized RGB-D and cup pose | 4/4 | 4/4 |
| Maximum cup-pose error versus frozen keyframe | 0.690 mm | 0.693 mm |
| `DONE`, 19 transitions | 4/4 | 4/4 |
| Final `table_contact=true` | 4/4 | 4/4 |
| Attached-object readback empty | 4/4 | 4/4 |
| Complete portable profile | 4/4 | 4/4 |
| Readable ros2_tracing CTF | N/A | 4/4 |
| Exact-window visual evidence | 0/4, TCC denied | 4/4, visually inspected |
| Clean task process, ROS graph, and trace-session shutdown | 4/4 | 4/4 |

## Invalid and diagnostic runs

These runs remain under the registered roots and are excluded from every statistic above.

- Early wrapper preflights failed before launch because strict nounset was enabled before ROS setup or GUI environment setup.
- `EXP-LNX-001`, `EXP-LNX-005`, and `EXP-LNX-009` used a polluted or incomplete visible-rendering environment and failed before business execution with `could not create window`.
- The validated Linux route is `/opt/ros/jazzy` plus the isolated MuJoCo fork and project overlays, followed by the profiling `local_setup.zsh`, with `__GLX_VENDOR_LIBRARY_NAME=mesa` and `LIBGL_ALWAYS_SOFTWARE=1`.
- `EXP-MAC-001`, `EXP-MAC-005`, `EXP-MAC-009`, and `EXP-MAC-013` completed business execution but were excluded while the capture timing and macOS TCC path were diagnosed.
- macOS CoreGraphics inventory uniquely resolved the current MuJoCo window, but `AXRaise` was unavailable and direct `screencapture -l` returned `could not create image from window`. No desktop or coordinate-crop replacement was accepted.

## CP-003 - final checkpoint

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-MAC-020 and EXP-LNX-016
working_tree_status: only this task ledger is untracked in the profiling worktree; unrelated target-host worktrees were preserved
owned_processes: NONE
owned_ros_graph_nodes: NONE
owned_lttng_sessions: NONE
preserved_processes: ai-station codex and codex-cua sessions and all unrelated target-host processes
evidence_sizes:
  mac_mini: 123M
  ai_station: 3.3G
decision: COMPLETE_WITH_MACOS_VISUAL_EVIDENCE_GAP
next_experiment: NONE
```
