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

### EXP-006: Task 5 full fork candidate gate

```yaml
fork_base: ff4aa7db2d92cef56b69d6d5243dd507a4a2b1dc
fork_candidate: 5d94c8d4c44128da427aea027ba7cdf2cd109283
parent_base: 64099931c5aaf1b3d3d21a872bd62eacacf1cf67
parent_gitlink_commit: e02735e744fa402d3fadbc5bedd436357a466528
implementer: /root/task5_fork_gate
state: REVIEW_IN_PROGRESS
packages_discovered: 6
packages_built: 6/6
registered_wrappers: 22/22 passed
tests_total: 301
tests_passed: 282
tests_skipped: 19
tests_failed: 0
test_errors: 0
normal_camera_plugin: 6/6 passed
registered_pykdl_pytest: 101/101 passed
source_less_wrappers: 9/9 passed
source_less_tests: 174/174 passed
upstream_ancestor: 57fc6744844902d4532160b403fa95840c1d6f96 PASS
r11_ancestor: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08 PASS
plugin_base_abi: exact upstream byte hash retained
viewer_interfaces: exact r11 byte hashes retained
bundle: /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate-worktree/final-candidate/mujoco_ros2_control-0.1.0-r1.bundle
bundle_sha256: bd28ae42c8c9100162dbcb19963ff51d9dc72ed26bf92c330402f392acb0d127
bundle_verify: complete history and exact branch ref PASS
final_tag_created: false
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate-worktree
archived_runs: []
deletion_candidates:
  - superseded RED, setup, environment, and focused diagnostic directories retained under the Task 5 evidence root
```

Task 5 closed the prior full-overlay boundaries: the ordinary CameraPlugin registered wrapper passed 6/6, and the PyKDL-dependent registered pytest wrapper passed 101/101. The authoritative count supersedes an earlier non-authoritative skip undercount. The source-backed candidate contains Simulate and macOS UI objects; the forced source-less branch contains no `simulate.cc` object and passes its complete 174-case core suite.

Task 5 independent review:

```yaml
spec_compliance: FAIL
verdict: Needs fixes
critical: 0
important:
  - Apple conversion warning demotions are target-wide and hide unrelated or future conversion regressions
  - installed core dylib contains 52 build-host/evidence/user-specific LC_RPATH entries through INSTALL_RPATH_USE_LINK_PATH
  - launch camera integration can be skipped by unrestricted ambient SKIP_CAMERA_TESTS on every platform
minor:
  - site-velocity service wait is 45 seconds on Linux although only Darwin required the cold-start accommodation
fix_round: 1/5 IN_PROGRESS
implementer: /root/task5_fork_gate
```

The candidate commit and bundle above remain immutable evidence of the rejected first candidate; they are superseded for acceptance and must not be presented as final after Fix Round 1 produces new hashes.

Task 5 fix round 1 implementation and scoped re-review:

```yaml
fork_candidate: 715c4bc4e80297045e46d78ce3585ae7ef76ba2d
parent_gitlink_commit: f92c8602ae485965b166064f0393226da90e3a57
packages_built: 6/6 fresh compile followed by non-symlink production copy-install
registered_wrappers: 22/22 passed
tests_total: 323
tests_skipped: 19 deterministic
tests_failed: 0
test_errors: 0
source_less_wrappers: 9/9 passed
source_less_tests: 177/177 passed
installed_macho: 18
installed_lc_rpath: exactly one @loader_path and zero forbidden paths
relocation_load: PASS
bundle_sha256: 2f0b3440cdec40ee47e8c8211f0ffec238b56b9b49a45580772d33b2f2e6774c
original_important_findings: 3/3 CLOSED
original_minor: CLOSED
new_important:
  - rangefinder interval conversion compares against rounded double(SIZE_MAX - 1), allowing an out-of-range float-to-size_t conversion or resource-unbounded vector allocation
new_minor:
  - report points the controller startup runtime RED at an AttributeError probe instead of the retained candidate-2 launch failure
review_verdict: REJECT
fix_round: 2/5 IN_PROGRESS
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate-worktree
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/reviews/task5-fix1-parent.md
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/reviews/task5-fix1-fork.md
archived_runs: []
deletion_candidates:
  - superseded candidates 1-6 and failed intermediate audits retained pending explicit authorization
```

Fix round 2 requires an explicit pre-allocation bound tied to the model-provided rangefinder count or another documented practical implementation limit, with overflow-safe `+1`. Registered RED/GREEN coverage must include `range=1, increment=2^-64`, a second finite-but-huge count, and a normal valid configuration, and must prove invalid configurations return `false` without exception or large allocation. Afterward the full fresh-build, 22-wrapper, source-less, copy-install/RPATH/relocation, ancestry/ABI/interface, and bundle gates must be repeated. No final tag is authorized.

Task 5 fix round 2 implementation and scoped re-review:

```yaml
fork_candidate: 0ed759a7198e76be847e163673782b1d2cbacf26
parent_gitlink_commit: 3419f40888bce1e15c84620b66a92d40fc53dec0
fork_changed_files: 3
parent_change: nested gitlink only
packages_built: 6/6 fresh
registered_wrappers: 23/23 passed
tests_total: 327
tests_skipped: 16 XML testcase skips
tests_failed: 0
test_errors: 0
rangefinder_boundary: 4/4 passed including 2^-64, finite million-ray, normal 3-ray, and production 24-ray
camera_plugin: 6/6 passed
registered_pykdl: 101/101 passed
source_less_wrappers: 9/9 passed
source_less_tests: 177/177 passed
copy_install: 18 Mach-O, exactly one @loader_path, zero forbidden paths, relocated load PASS
bundle_sha256: 1a184391050b0e55af7e90ccdc9f457adbbd376c8595e761da0bd45e47e769d3
bundle_verify_clone_fsck_ref: PASS
final_tag_created: false
review_spec_compliance: PASS
review_verdict: Approved
critical: 0
important: 0
minor: 0
task_state: COMPLETE
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate-worktree/fix-round-2
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/reviews/task5-fix2-parent.md
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/reviews/task5-fix2-fork.md
archived_runs: []
deletion_candidates:
  - superseded candidates and probes remain retained pending explicit authorization
```

The accepted count increase from 22 to 23 registered wrappers is intentional: Fix Round 2 adds one registered four-case rangefinder boundary target. The production bound is derived from the number of same-name, resolvable rangefinders in the loaded MuJoCo model and is checked before the first input-derived `size_t` conversion or allocation. Invalid huge finite configurations return `false`; the real 24-ray configuration remains accepted. Task 6 must pin this exact candidate and label it `so101-0.1.0-r1-candidate`; no final tag is authorized until both platform runtime qualifications pass.

### EXP-007: Task 6 project adapter and candidate pin

```yaml
parent_base: 3096db0
implementation_candidate: 62da4a7b98e384377fd5ca7170b8ab56618d9a3a
fork_gitlink: 0ed759a7198e76be847e163673782b1d2cbacf26 unchanged
changed_files: 11 planned paths
focused_contracts: 18/18 passed
support_gtests: 19/19 passed
demo_pytest: 261/261 passed
aggregate: 281 tests, 0 failures, 0 errors, 0 skips
review_spec_compliance: FAIL
critical: 0
important:
  - integration guide still assigns on_physics_step to the base ABI and documents the obsolete owner and authoritative-step ordering
minor:
  - four-package provenance example omits ros2 pkg prefix mujoco_3d_lidar
review_verdict: Rejected
fix_round: 1/5 IN_PROGRESS
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/project-adapter-worktree
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/reviews/task6-parent.md
archived_runs: []
deletion_candidates: []
```

The implementation, lock, installer, camera-probe, isolated build, and test-shim boundaries passed review. Fix Round 1 is documentation-scoped: register a contract that rejects the obsolete base-hook text; migrate guide sections 4.1, 4.2, 4.4, and the related fault-table entry to the optional `MuJoCoROS2ControlSimulationObserver`, `SimulationObserverDispatcher`, and actual control/pre-step -> `mj_step` -> divergence -> observer -> snapshot/clock flow; and add the lidar package-prefix read-back. No production-code change is justified by this review.

Task 6 fix round 1 implementation and scoped re-review:

```yaml
parent_candidate: 42e2d87838347a4c0bd496828eec000dbd683535
fork_gitlink: 0ed759a7198e76be847e163673782b1d2cbacf26 unchanged and clean
fix_changed_files: 2 planned paths
production_code_changes: 0
red_contracts: 2 expected failures
focused_contracts: 20/20 passed
demo_pytest: 263/263 passed
support_gtests: 19/19 passed
aggregate: 283 tests, 0 failures, 0 errors, 0 skips
review_spec_compliance: PASS
review_verdict: Approved
critical: 0
important: 0
minor: 0
task_state: COMPLETE
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/project-adapter-worktree/fix-round-1
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/reviews/task6-fix1-parent.md
archived_runs: []
deletion_candidates: []
```

The guide now matches the implemented optional-observer architecture and dispatcher ownership, states the actual authoritative ordering, and reads back all four installed fork packages including `mujoco_3d_lidar`. The registered documentation contracts prevent the obsolete base-hook guidance from returning. Task 7 consumes this exact parent and fork candidate in an isolated macOS runtime overlay.

### EXP-008: Task 7 macOS runtime and camera-probe breaker

```yaml
parent_head: 2abca94748ddc382a05d70f918899367c0259d5e
fork_candidate: 0ed759a7198e76be847e163673782b1d2cbacf26
ros_domain_id: 227
gz_partition: mrc010-macos-227
tmux_session: mrc010-macos-upgrade
runtime_state: BREAKER_NOT_QUALIFIED
stack_initialization: main-thread GLFW, camera renderer, evidence plugin, controllers, MoveGroup PASS
camera_contract_before_frequency: dimensions/frame/encodings/payload/full-depth/alignment PASS
final_samples: 30 camera_info, 30 color, 30 depth
aligned_timestamps: 4
final_color_header_frequency_hz: 5.918367346938775 FAIL
dynamic_pick_place: NOT_RUN because camera prerequisite failed
final_screenshot: NOT_CREATED
fix_rounds: 5/5 exhausted
committed_task7_changes: none
rejected_patch: /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/runtime/rejected-task7-concurrent-probe.patch
rejected_patch_sha256: 7a66ffaa602f177c98dae2cc4f39ad0205d9dc9696692377e8a726151e0f28ed
review_ruling: current concurrent multiprocessing probe rejected; no CameraPlugin publisher defect proven; phase-separated strict Task 7A approved
clean_shutdown: attempt 1 ordered but PAL invalid-context errors; attempt 2 process absence only, final clean shutdown still required
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/runtime
archived_runs: []
deletion_candidates: []
```

The decisive A/B result is that a color-only subscriber observed 120 consecutive real color header stamps at 9.993281827 Hz, while simultaneous large-message collection lost color samples even though camera-info and depth retained continuous 100 ms stamps. The final multiprocessing barrier cleared only Python-side metadata, not DDS subscription backlog. It therefore did not prove a camera publisher defect and is not accepted into the branch.

Task 7A is a new experiment boundary, not a sixth incremental repair of the rejected concurrent collector. In one invocation and against the same stack/candidate provenance, phase one must subscribe only to real color messages and require at least 30 unique header stamps at 8-12 Hz using the original end-to-end formula. After complete teardown, phase two must collect all three topics and require at least three real samples each, at least one common header timestamp, 640x480, `task_camera_frame`, `rgb8`, `32FC1`, non-empty payloads, and a full-payload finite-positive depth check for a common timestamp. Only both phases may produce the single success JSON. Configured rate, wall timer, median/tail frequency, or historical diagnostic substitution is forbidden. A fresh dynamic run, final screenshot, and ordered error-free shutdown remain mandatory after camera success.

### EXP-009: Task 7A phase-separated camera and final macOS breaker

```yaml
final_parent_code: 22a98d740219abda9459ea3c9cc67eb9fb07fc12
task_report_commit: 0899900bc6d0590174b48b49e277d2e616e56483
final_fork_gitlink: f0f09abfe1498e1c6aa84a37a78cea87d2198b1d
fork_bundle_sha256: f3ea454231135e3eb96d7740ccdbef475dd87e117ea98c8d692bb553f663f186
fork_full_gate: 23 wrappers, 334 cases, 0 failures, 0 errors, 19 skips
source_less_gate: 9/9 wrappers, 182 cases
project_gate: 293/293 passed
phase_probe_source_review: PASS 0 critical, 0 important, 0 minor
pal_shutdown_source_review: PASS 0 critical, 0 important, 0 minor
round_4_camera: PASS 30 unique color stamps, 9.81719702098849 Hz, aligned RGB-D, 307200/307200 finite-positive depth
round_4_dynamic: DONE with 19 transitions and full lift/transport/place/release/retreat evidence
round_4_screenshot_sha256: 0d1f875ba9b23c813e0ae90573d2f5eb44960a8d7878dad247476c44b87997ce
round_4_qualification: INVALID because two PAL invalid-context errors and SIGTERM escalation occurred on shutdown
round_5_runtime: BREAKER_NOT_QUALIFIED
round_5_failure: SIGSEGV in _glfwSetWindowSizeCocoa, ros2_control_node exit -11, MoveGroup SIGTERM escalation
round_5_camera: NOT_RUN
round_5_dynamic: NOT_RUN
round_5_screenshot: NOT_CREATED
runtime_rounds: 5/5 exhausted
final_tag_created: false
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/runtime-task7a
archived_runs: []
deletion_candidates:
  - rejected Task 7 concurrent probe patch and superseded build/runtime diagnostics remain retained pending explicit authorization
```

The final macOS code and regression candidate is fully built and reviewed, and one retained run proves the camera and dynamic behavior functionally. It is nevertheless not macOS-qualified because no single final run combines those outcomes with the mandatory clean-shutdown contract. The fifth and final runtime attempt crashed in the Cocoa GLFW window-resize path before readiness. The approved SDD ceiling prohibits a sixth Task 7A runtime attempt; Linux qualification proceeds independently and cannot erase this macOS blocker.

### EXP-010: Task 8 Linux checkpoint and reproducible source blocker

```yaml
parent_code: 22a98d740219abda9459ea3c9cc67eb9fb07fc12
fork_candidate: f0f09abfe1498e1c6aa84a37a78cea87d2198b1d
remote_host: AI-STATION-001
remote_tmux: mrc010-linux-upgrade-codex retained
checkpoint_1: PASS exact bundles, hashes, detached clean commits, gitlink, locks, double ancestry
linux_packages_built: 6/6
linux_applicable_wrappers: 22
cross_platform_source_inventory: 23 with one APPLE-only lifecycle wrapper
wrapper_result: 21 passed, 1 timeout/error
junit_cases: 287 total, 270 passed, 16 skipped, 0 assertion failures, 1 missing-result error
blocking_test: MujocoSimulationTest.PausedDivergenceRejectsResumeUntilReset
minimal_red: iterations 1-2 exit 0; iteration 3 hung after reset/resume and ignored SIGTERM
ambient_skip_linux_camera_gate: PASS; Linux camera tests executed under SKIP_CAMERA_TESTS=true
checkpoint_2: BLOCKED_REPRODUCIBLE_SOURCE_DEFECT
checkpoint_3_camera: NOT_RUN
checkpoint_4_dynamic: NOT_RUN
checkpoint_5_screenshot: NOT_RUN
copyback_files: 317 SHA-verified
copyback_manifest_sha256: 55bde8a9196e7941da7994a60039183f994fd2f468f051bfddbe8db9d222e820
fix_round: 1/5 IN_PROGRESS
retained_remote_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/linux-runtime
retained_local_copy:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/linux/remote-evidence
archived_runs: []
deletion_candidates: []
```

Package parallelism and CTest wrapping are disproven as sole causes because a fresh sequential full run hit the same boundary and the direct single-test binary hung on the third iteration. The exact lock/wait owner is not yet proven. Fix Round 1 must instrument and establish that owner before changing production code; increasing timeouts, detaching threads, skipping teardown, or force-exiting cannot qualify as a fix.

Task 8 fix rounds 1-2 diagnosis, implementation, and scoped review:

```yaml
root_cause: test-local EventCollector, observer, and callback state could be destroyed before the resumed physics thread was stopped and joined
gdb_wait_chain: fixture TearDown -> MujocoSimulation::shutdown -> physics thread in RecordingObserverPlugin::on_physics_step -> EventCollector::add
production_code_changes: 0
fork_fix_round_1: fbd61956bc99ad2fd3fd1500e7750d31bc0c72ae
fix_round_1_review: FAIL; 0 critical, 1 important, 0 minor
fix_round_1_finding: shutdown guard was constructed after physics start and two fatal assertions, leaving early-return paths unguarded
fork_fix_round_2: fcbc9f7b23f4493ceed888a22f32805a37493624
parent_fix_round_2: fa37de5af725fbd61c037623dc0fdd64f577f0ff
fix_round_2_scope: one test file; declare thread-referenced locals, then guard, then register callback and start physics
macos_source_backed: focused 20/20; core 9/9
macos_source_less: core 9/9; direct prebuilt simulate branch; no simulate.cc object
linux_source_backed: fresh 6-package build 6/6; focused 20/20; corrected core 9/9
parent_contracts: macOS install contract 16/16; backend integration PASS
fix_round_2_review: PASS; 0 critical, 0 important, 0 minor
fork_bundle_sha256: 5f0b23cc50838287c47d6754056b31d9d565108cf57b9e8ec71ce7ead84a3cf1
parent_bundle_sha256: a6e357659f813e59f98bf9fe8ca7b6c99c351ed889b0a7e2640b8f6b9ec64a64
invalid_runs:
  - macOS shell run with SIP-stripped dylib environment; excluded
  - Linux first core run imported an ambient /opt/ros Python module; excluded after corrected isolated import provenance
checkpoint_2_resume: COMPLETE against exact fa37de5/fcbc9f7 candidate in fresh ai-station directories
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/linux-fix1-worktree
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/reviews/task8-fix1-fork.md
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/reviews/task8-fix2-fork.md
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/reviews/task8-fix2-parent.md
archived_runs: []
deletion_candidates: []
```

The accepted fix is test-lifecycle-only. `SimulationShutdownGuard` is declared after every local object referenced by the physics thread and before the thread starts, so C++ reverse destruction order synchronously shuts down and joins on normal, fatal-assertion, and exception exits. The production `shutdown()` mutex/completion guard makes the later fixture call idempotent. No timeout, detach, skip, forced exit, or production workaround was accepted. Full Linux checkpoints resume only after this exact candidate passed independent review.

Task 8 final Linux qualification:

```yaml
qualification: VALID
parent_code: fa37de5af725fbd61c037623dc0fdd64f577f0ff
fork_candidate: fcbc9f7b23f4493ceed888a22f32805a37493624
remote_tmux: mrc010-linux-fix2-full-codex
remote_domain: 83
remote_partition: mrc010-linux-fix2-full
checkpoint_1: VALID exact bundles, hashes, clean commits, gitlink, locks, and double ancestry
checkpoint_2: VALID
fork_gate: 6 packages; 22/22 Linux wrappers; 327 JUnit cases; 311 passed; 16 skipped; 0 failures/errors
source_less_gate: 9/9 wrappers; 179 JUnit cases; 176 passed; 3 skipped; 0 failures/errors; no simulate.cc object
project_gate: 3 packages; 25 native wrappers; 529/529 cases passed
linux_camera_skip_contamination: PASS; camera tests executed with SKIP_CAMERA_TESTS=true
static_gates: copy-install, relocation, ABI, r11 interfaces, 13 ROS interfaces, linkage, single mj_step, and backend integration PASS
checkpoint_3_camera: VALID
camera_color: 30 unique headers at 8.906633906633907 Hz
camera_alignment: 3 info/color/depth samples with common stamp 59820000000
camera_contract: 640x480; task_camera_frame; rgb8; 32FC1; 307200/307200 positive finite depth
camera_json_sha256: 508d80117c3dc8cd4db6e3eb229d418c5ecb9b30edd40f7ac82008c70d1339bc
graphics_environment: task-local Mesa software GL after host NVIDIA driver/library mismatch was independently reproduced
checkpoint_4_dynamic: VALID; exit 0; DONE; QUALIFIED; 19 transitions
dynamic_phases: lift, transport, place, release, retreat PASS
dynamic_final_xy_error_m: 0.0018543216494020017
dynamic_final_upright_tilt_rad: 0.008856173390143201
planning_scene_sync_max_position_error_m: 0.0
checkpoint_5: VALID
screenshot_sha256: 7182bb4642a8b336209fed238717cd4da0ef3755e24ea8f51b708f1b60f2b8f0
shutdown: one Ctrl-C per owned pane; 2 s runtime exit; no escalation, invalid context, or thread/context crash
post_shutdown: 0 owned runtime PIDs; 0 domain-83 task nodes; preserved sessions 5/5 and related PIDs 15/15
copyback_files: 342 SHA-verified
copyback_manifest_sha256: 651606ddecf6aab2ef8e0bf6372908c0d6d49b10fc925e2d1728311c7d712693
retained_remote_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/linux-runtime-fix2-full
retained_local_copy:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/linux/fix2-full
archived_runs: []
deletion_candidates: []
```

Fresh parent-side verification rechecked the 342-file manifest with zero mismatches, asserted all five checkpoint JSON contracts, read back the exact candidate/gitlink and both ancestry paths, recomputed camera/dynamic/screenshot hashes, and inspected the retained screenshot pixels. Linux is qualified for the exact `fa37de5`/`fcbc9f7` code candidate. Overall Task 9 remains blocked: macOS Task 7A exhausted its five permitted runtime rounds and the final exact-candidate run crashed in `_glfwSetWindowSizeCocoa` before camera/dynamic qualification. Linux success does not authorize a final tag or an overall `QUALIFIED` ledger state.

### EXP-011: platform-neutral render-context capability rename

```yaml
scope: approved ABI rename and exact-candidate requalification boundary
previous_fork_candidate: fcbc9f7b23f4493ceed888a22f32805a37493624
fork_candidate: ca654e30ea9791564fab7110c90734733b68c8cc
parent_code_pin: 6b996c72b9fc103800112f6df33e6a90fc755e40
api_change: set_macos_render_context(void*) -> set_platform_render_context(void*)
compatibility_shim: none
apple_contract: main-thread-created non-null GLFW context is handed to CameraPlugin
non_apple_contract: caller passes nullptr and CameraPlugin treats the handoff as a no-op
tdd_red: direct platform-context contract failed against the old public method name
nested_green:
  - platform/reset Python contracts 3/3
  - registered platform/reset CTest 2/2
  - Apple lifecycle 5/5
  - focused MujocoSimulation 2/2
fresh_macos_build: 6/6 nested packages in isolated build/install/log roots
fresh_macos_tests:
  - CameraPlugin 6/6
  - Apple lifecycle 5/5
  - core simulation/platform/reset CTest 3/3
parent_contracts:
  - macOS install and camera contracts 20/20
  - backend integration PASS
independent_review: PASS; 0 critical, 0 important, 0 minor
linux_previous_evidence: remains valid only for exact fa37de5/fcbc9f7 pair
linux_current_candidate: REQUALIFICATION_REQUIRED
macos_current_candidate: NOT_RUNTIME_QUALIFIED
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/platform-context-rename
archived_runs: []
deletion_candidates: []
```

This rename keeps the public optional capability platform-neutral without hiding the ownership rule:
Apple-only context creation and Cocoa work remain inside the Apple implementation path, while the common
simulation/plugin contract is shared. The fresh isolated macOS build also proved that the earlier normal
CameraPlugin typesupport loader failure came from a mixed stale overlay, not from this source change. No final
release tag is authorized until Linux and macOS runtime acceptance are both valid for the current exact candidate.
