# MuJoCo ROS 2 Control 0.1.0 Upgrade Experiment Ledger

```yaml
task_id: mujoco-control-1-0-upgrade-20260825
evidence_root: /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825
parent_branch: codex/mujoco-ros2-control-0-1-upgrade
parent_head: 453faaddcca6468bc0d68cb5dbc81cd7bb773e34
upstream_target: 57fc6744844902d4532160b403fa95840c1d6f96
local_r11: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
fork_branch: codex/upstream-0.1.0-so101-r1
retained_runs: []
archived_runs: []
deletion_candidates: []

latest_checkpoint:
  state: TASK_2_QUALIFIED
  hypothesis: The reviewed optional observer dispatcher can now be wired only at upstream 0.1.0's authoritative physics, pause, reset, and snapshot transition points.
  next_command: Add Task 3 RED transition-order and reset-atomicity tests before wiring the dispatcher into MujocoSimulation.
```

## Controller rulings

- Ruling: use the current clean dedicated feature checkout instead of creating a nested parent-repository worktree. The checkout is itself a Git submodule of the parent robotics repository, is already on the approved feature branch, and the vendored dependency has its own branch boundary. Cost if wrong: changes are visible in this checkout, but remain isolated from `main` and recoverable through the task commits.

## Experiments

### EXP-000: relevant contract baseline

```yaml
scope: read-only local contract baseline; no runtime or source mutation
controlled_environment:
  python: /Users/matianyi/ros2_jazzy/.venv/bin/python
  ros_underlay: /opt/ros/jazzy/setup.zsh
  pytest_plugin_autoload: disabled for pure source/installer contract tests
command: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -p no:cacheprovider src/so101_demo_py/test/test_macos_install_contract.py src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py -q
result: 16 passed in 5.01s
diagnosis: The first unsourced run failed to find ament_cmake. Sourcing ROS exposed launch_testing auto-collection, so the pure contract suite disables plugin autoload while retaining the ROS CMake environment.
```

No runtime experiment has started. All ordinary logs and artifacts for this task are registered under the single evidence root above.

### Task 1 dispatch

```yaml
base: 453faaddcca6468bc0d68cb5dbc81cd7bb773e34
implementer: /root/task1_merge_baseline
brief: .superpowers/sdd/2026-08-25-mujoco-ros2-control-0-1-upgrade/task-1-brief.md
state: COMPLETE
```

### EXP-001: upstream-first fork merge baseline

```yaml
scope: Git history and resolved source-tree provenance; no runtime
fork_merge_commit: 6c562f861e09394ba631fa7dc4e63ea98f95e04c
merge_parents:
  - 57fc6744844902d4532160b403fa95840c1d6f96
  - f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
parent_commit: 34c87e4bd2e1e826f142a6417fe941679bc33ae2
ancestry_checks: PASS
diff_checks: PASS
upstream_surface_checks: PASS
contract_tests:
  passed: 15
  failed: 1
  expected_failure: test_r11_gitlink_history_and_portable_bytes_are_exact because Task 6 has not updated the r11 dependency lock yet
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/upstream
archived_runs: []
deletion_candidates: []
review_state: ACCEPTED_AFTER_FIX_ROUND_1
```

Conflict resolution retained upstream ownership for the new simulation and plugin architecture, removed the legacy core camera implementation, retained viewer-camera sources/interfaces/tests as later migration inputs, kept upstream camera streaming/polled/disabled behavior, and preserved only the macOS compile boundary in the baseline camera plugin. Exact conflict rationale and commands are in the SDD Task 1 report.

Merge conflicts resolved:

1. `mujoco_ros2_control/CMakeLists.txt`
2. `mujoco_ros2_control/include/mujoco_ros2_control/mujoco_cameras.hpp`
3. `mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system_interface.hpp`
4. `mujoco_ros2_control/src/mujoco_cameras.cpp`
5. `mujoco_ros2_control/src/mujoco_system_interface.cpp`
6. `mujoco_ros2_control/tests/CMakeLists.txt`
7. `mujoco_ros2_control/tests/test_headless_init.cpp`
8. `mujoco_ros2_control_msgs/CMakeLists.txt`
9. `mujoco_ros2_control_plugins/CMakeLists.txt`
10. `mujoco_ros2_control_plugins/mujoco_ros2_control_plugins.xml`
11. `mujoco_ros2_control_plugins/src/camera_plugin.cpp`
12. `mujoco_ros2_control_plugins/src/camera_plugin.hpp`
13. `mujoco_ros2_control_plugins/src/heartbeat_publisher_plugin.cpp`

Provenance commands and observed results:

```text
git -C third_party/mujoco_ros2_control merge-base --is-ancestor 57fc6744844902d4532160b403fa95840c1d6f96 HEAD
exit 0

git -C third_party/mujoco_ros2_control merge-base --is-ancestor f19a8cc3af61feccacb22a9f0d16cc972e3b2c08 HEAD
exit 0

git -C third_party/mujoco_ros2_control rev-list --parents -n 1 HEAD
6c562f861e09394ba631fa7dc4e63ea98f95e04c 57fc6744844902d4532160b403fa95840c1d6f96 f19a8cc3af61feccacb22a9f0d16cc972e3b2c08

git -C third_party/mujoco_ros2_control diff --check
exit 0

test -f third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/mujoco_simulation.hpp
test -f third_party/mujoco_ros2_control/mujoco_extensions/mujoco_3d_lidar/package.xml
test -f third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/src/base_velocity_plugin.cpp
test -f third_party/mujoco_ros2_control/mujoco_ros2_control_msgs/srv/SetFreeJointState.srv
all exit 0
```

### EXP-002: Task 1 fix round 1 primary-monitor guard

```yaml
finding: The upstream 0.1.0 owner dereferenced primary monitor and video mode without null checks, while the retained regression test still targeted the removed r11 owner.
red_command: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/matianyi/ros2_jazzy/.venv/bin/python -m pytest -p no:cacheprovider third_party/mujoco_ros2_control/mujoco_ros2_control/tests/test_primary_monitor_guard.py -q
red_result: 1 failed because MujocoSimulation lacked the required GLFWmonitor guard
fork_fix_commit: 102aba33f7566918a884aef3a57eefdf892cd56f
parent_gitlink_commit: dadeb5c413cde9d50177612ecba67690cc7c99fc
green_direct: 1 passed
green_registered_ctest: 1/1 passed
ancestry_checks: PASS
diff_checks: PASS
full_build_observation: Upstream mujoco_3d_lidar did not compile because its target lacks the C++17 requirement for std::byte; this is a downstream full-fork gate issue, not claimed passing here.
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task1-fix-round-1
archived_runs: []
deletion_candidates: []
```

Task 1 scoped re-review verdict:

```yaml
primary_monitor_guard: ADDRESSED
ledger_completion: ADDRESSED
new_breakage: none
verdict: ACCEPTED
```

### Task 2 dispatch

```yaml
parent_base: e265dde
fork_base: 102aba33f7566918a884aef3a57eefdf892cd56f
implementer: /root/task2_capabilities
state: COMPLETE
scope: Optional plugin capability header, fault-isolated observer dispatcher, focused tests, and unchanged upstream base ABI.
ruling: The upstream mujoco_3d_lidar C++17 defect remains outside Task 2 and is a mandatory Task 5 full-fork gate item.
```

### EXP-003: Task 2 optional capabilities and dispatcher

```yaml
fork_commit: 65d60eab9f23ea30cbbf1f73ae4a81ee1ce6c899
parent_gitlink_commit: 7154a17df27e1abce18f2924d994bb2e264b6974
focused_gtests: 3/3 passed
abi_base_header_diff: empty
abi_base_header_sha256: e4bb0f69a48fd9686a1cd50e7e064cae0bdfc011b09576b91d6945b8f5d8b5ee
ancestry_checks: PASS
format_check: PASS
full_package_gate: NOT_CLAIMED
full_package_blockers:
  - upstream mujoco_3d_lidar missing C++17 target requirement for std::byte
  - upstream plugin/core AppleClang -Werror sign/float conversion diagnostics
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task2
archived_runs: []
deletion_candidates: []
review_state: ACCEPTED
```

Task 2 independent review:

```yaml
spec_compliance: PASS
task_quality: Approved
critical: 0
important: 0
minor: 0
package_full_fork_green: not established and explicitly deferred to Task 5
```

### Task 3 dispatch

```yaml
parent_base: 9decd7a
fork_base: 65d60eab9f23ea30cbbf1f73ae4a81ee1ce6c899
implementer: /root/task3_lifecycle
state: IN_PROGRESS
scope: Register observers and wire authoritative post-step, paused atomic reset, pause, and state-snapshot transitions without moving ordinary update or pre_step ownership.
ruling: Every actual upstream successful mj_step path must implement the approved semantic order even when plan pseudocode helper names differ.
```

### EXP-004: Task 3 authoritative lifecycle transitions

```yaml
fork_commit: e6702bbb335ee3f9ce0dc5987fcdb7689ede2b3b
parent_gitlink_commit: f7ad56ba287d1912381eb314b12e0c519d8ccd5b
focused_real_source_ctest: 2/2 passed
simulation_tests: 25/25 passed
system_interface_tests: 4/4 passed
full_package_ctest: 4/7 passed and NOT_CLAIMED
full_package_boundaries:
  - focused plugin install lacks ament resource index for test_plugin
  - focused core install lacks Python package exposure for two Python tests
format_check: uncrustify executable unavailable; no format pass claimed
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task3
archived_runs: []
deletion_candidates: []
review_state: IN_PROGRESS
```

Task 3 first review findings:

```yaml
spec_compliance: FAIL
task_quality: Needs fixes
critical:
  - Observer callbacks can race with or execute after plugin cleanup.
  - Divergent catch-up/paused steps can continue integration or publish non-authoritative state; successful paused steps can publish twice.
important:
  - StepSimulation paused-state check and queue setup race SetPause.
  - Protected registration test seam permits unsafe runtime mutation and bypasses loader semantics.
fix_round: 1/5 IN_PROGRESS
```

Task 3 fix round 1 scoped re-review:

```yaml
observer_cleanup_race: ADDRESSED
failed_step_publication_and_continued_integration: NOT_ADDRESSED
step_pause_race: ADDRESSED
unsafe_registration_seam: ADDRESSED
remaining_critical: SetPause(false) can resume a divergence-latched simulation and trigger another integration attempt before reset.
fix_round: 2/5 IN_PROGRESS
```

Task 3 fix round 2 scoped re-review:

```yaml
service_reset_resume_gate: ADDRESSED
new_critical: Early UI reset can bypass common reset recovery because time-based reset detection requires prevSimTime > 0.1, leaving divergence latched after a first-step failure.
fix_round: 3/5 IN_PROGRESS
```

Task 3 fix round 3 scoped re-review:

```yaml
early_ui_reset_recovery: NOT_ACCEPTED
critical_regression: Strict backward-time detection misclassifies viewer history scrub or other backward state restoration as reset and overwrites the selected state.
required_architecture: Reset-specific durable signal from the actual Simulate Sync reset operation, plus actual reset versus history-backward regression coverage.
fix_round: 4/5 IN_PROGRESS
implementer: /root/task3_fix4
```

Ruling: `Simulate::Sync()` is non-virtual; actual reset and history paths clear their pending flags before releasing the shared mutex, leaving no reliable post-lock discriminator. A project-owned wrapper translation unit may instrument the actual installed `simulate.cc` reset call with a per-`mjData` durable reset callback/generation. It must not edit vendor sources and must be guarded by real Sync reset/history tests. Cost if wrong: this seam is coupled to the installed Simulate source structure and must be revisited when the vendor source changes.

Task 3 fix round 4 implementation checkpoint:

```yaml
fork_commit: 2e6875feaa745995188ff3e83bbdb3324b833242
parent_gitlink_commit: 0fa52c9d1aed76f1cd8003f2c96bcace826161ec
actual_sync_red: 0/2 passed
actual_sync_green: 2/2 passed
simulation_tests: 32/32 passed
focused_ctest: 2/2 passed
build_and_audits: passed
review_state: INTERRUPTED_FOR_WORKTREE_MIGRATION
remaining_review_focus:
  - wrapper compatibility with the pinned Simulate source on macOS and Linux
  - registry lifetime and concurrency
  - installed static-library and source-less interactive behavior
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task3
archived_runs: []
deletion_candidates: []
```

The scoped round-4 re-review was intentionally interrupted before changing the main checkout. It must be restarted from the isolated upgrade worktree before Task 3 is accepted.

### Worktree migration checkpoint

```yaml
requested_isolation: true
main_checkout:
  path: /Users/matianyi/Projects/robot_demo_001/moveit-demo
  branch: main
  commit: db1b658b4bc34f11c923640e1d188cf11aeebc1b
  submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
  status: clean
upgrade_worktree:
  path: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/mujoco-ros2-control-0-1-upgrade
  branch: codex/mujoco-ros2-control-0-1-upgrade
  commit: fea6dfbfc5d43fd34cad6676bf97d41ad867ac15
  fork_branch: codex/upstream-0.1.0-so101-r1
  fork_commit: 2e6875feaa745995188ff3e83bbdb3324b833242
  status: clean_before_ledger_update
test_isolation: all future build/install/log paths remain under the registered task-specific evidence root; main checkout build/install/log are out of scope
migration_baseline: 15/16 passed
known_baseline_failure: gitlink is 2e6875f while the candidate lock intentionally remains f19a8cc until Task 6
evidence: /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/worktree-migration/baseline-contracts.txt
```

The parent repository is itself a submodule and has a shared `core.worktree`. The isolated linked worktree therefore uses a worktree-local `core.worktree` override. The nested fork was populated from the existing local fork branch because `2e6875f` has not yet been published; no early push was performed.

Task 3 fix round 4 scoped re-review:

```yaml
original_history_scrub_critical: ADDRESSED_ON_SOURCE_BACKED_PATH
critical: 0
important:
  - source-less Conda/pixi prebuilt-libsimulate interactive initialization is rejected even though upstream supports it and interactive mode is the default
minor:
  - installed source-backed libsimulate.a has an undefined dependency on the project-private reset notifier
verdict: REJECT
fix_round: 5/5 IN_PROGRESS
implementer: /root/task3_fix4
```

Round 5 hypothesis to test: `ROS2ControlGlfwAdapter::PollEvents()` executes under the render loop's simulation mutex after MuJoCo's UI callback sets `pending_.reset` and before `Sync()`. A focused project-owned adapter seam may therefore consume only that exact reset request, reproduce the pinned upstream reset block, align/publish the reset-specific event, and clear the pending flag without wrapping vendor `simulate.cc`. This must preserve all upstream reset bookkeeping, source-less/source-backed interactive initialization, history/keyframe behavior, and installed archive linkability; otherwise the hypothesis is rejected rather than silently degrading UI reset semantics.

Task 3 fix round 5 implementation and scoped re-review:

```yaml
fork_commit: 9ba53fa90d7bbeb6e49539b7d971d8ac466100a9
parent_gitlink_commit: fd9aced65409feabd92dc724a4fb82e782171c44
source_backed_simulation: 32/32 passed
focused_ctest: 2/2 passed
source_contract: 2/2 passed
forced_source_less_reset_history: 2/2 passed
full_build_install: passed
archive_audit: one direct simulate.cc object and no project-private reset symbol
plugin_base_abi: exact upstream byte hash retained
authoritative_mj_step: sole production call retained
round_4_source_less_important: ADDRESSED
round_4_archive_minor: ADDRESSED
new_important: coalesced reset plus later history/keyframe/zero-control is fully processed by inner Sync, but the adapter still publishes common-reset recovery and can overwrite the winning later state
review_verdict: REJECT
fix_round: 5/5 COMPLETE
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task3/fix-round-5-worktree
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/reviews/task3-rereview5-worktree
archived_runs: []
deletion_candidates: []
```

Breaker ruling: the coalesced-event finding is real and affects viewer state semantics. It is carried into Task 4 because Task 4 immediately owns the same `ROS2ControlGlfwAdapter`, `MujocoSimulation`, viewer lifecycle, and test surfaces. Task 4 must begin with RED regressions for actual PollEvents batches containing `reset + load_from_history`, `reset + load_key`, and `reset + zero_ctrl`, then publish common-reset generation only when reset remains the winning state transaction after the complete upstream `Sync()`. A sixth Task 3 fix round is prohibited by the approved SDD process.

Task 3 is complete with one breaker-carried finding. No live Cocoa RenderLoop launch or Linux runtime claim is made here; those remain explicit Task 4/7/8 gates.

### EXP-005: Task 4 viewer camera and rendering lifecycle migration

```yaml
parent_base: c44404e08d022eb8359cb5b11909547f57dc3c08
fork_base: 9ba53fa90d7bbeb6e49539b7d971d8ac466100a9
fork_commit: ff4aa7db2d92cef56b69d6d5243dd507a4a2b1dc
parent_gitlink_commit: 64ee1d7b57e5a0ade2774247f4cead30a068c87a
implementer: /root/task4_viewer_camera
state: REVIEW_IN_PROGRESS
breaker_red: 0/3 passed
breaker_green: 5/5 passed
source_backed_build_install: passed
simulation: 44/44 passed
system_interface: 6/6 passed
viewer: 7/7 passed
registered_core_ctest: 4/4 passed
source_contracts: 7/7 passed
camera_modes: 6/6 passed
fake_apple_lifecycle: 5/5 passed
registered_camera_lifecycle_ctest: 1/1 passed
forced_source_less_reset_history: 2/2 passed
forced_source_less_adapter_contract: 2/2 passed
plugin_base_abi: exact upstream byte hash retained
viewer_interfaces: exact r11 byte hashes retained
authoritative_mj_step: sole production call retained
node_linkage: shared macOS UI dispatcher only; hardware-plugin DSO not preloaded
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task4-worktree
archived_runs: []
deletion_candidates:
  - invalid or interrupted Task 4 setup diagnostics retained in place
  - failed registered pytest-wrapper attempts retained in place
  - superseded focused build attempts retained in place
```

Known non-passing boundaries are not promoted to success: the combined registered ament pytest wrappers collect sibling PyKDL-dependent tests in the focused macOS environment, and the normal CameraPlugin target still encounters the pre-existing source-tree heartbeat installed-header boundary. The exact requested source contracts and real CameraPlugin sources were exercised through focused registered harnesses. No live Cocoa/OpenGL, Linux, ai-station, or dynamic pick-place claim is made in Task 4.

Task 4 independent review:

```yaml
spec_compliance: PASS
verdict: Approved
critical: 0
important: 0
minor:
  - teardown completion is released after a future nonconforming renderer throws from close before worker join is proven
  - failed rendering-plugin init rollback lacks a direct blocking-worker plus concurrent-shutdown regression
  - Task 4 report lifecycle prose reverses the production renderer-stop and runtime-use-drain order
review_evidence: /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/reviews/task4-review-worktree
task_state: COMPLETE_WITH_3_DEFERRED_MINORS
```

The suspected discard-versus-context race was adjudicated not reachable in the production macOS topology: failed-init rollback runs synchronously inside `on_init`, and the external-initialization completion guard prevents main-thread context destruction until it returns; if shutdown owns the lifecycle first, discard waits for renderer shutdown completion.
