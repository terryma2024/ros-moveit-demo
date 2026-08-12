---
task_id: so101-demo-py-fusion
goal: Fuse the qualified MuJoCo and Gazebo Python demos into the single so101_demo_py implementation package while preserving the frozen MuJoCo policy bytes.
success_contract: Complete approved Tasks 1-18; obtain separate fixed-bundle MuJoCo FULL_RESTART 5/5 and RESET_WORLD 5/5; record one valid Gazebo execute result and fresh visual/numeric evidence; do not push or merge.
worktree: /data/work/ws_moveit/.worktrees/so101-demo-py-fusion
branch: codex/so101-demo-py-fusion
base_commit: 866656b217eff4c57eade161c94ea0cef326d13d
current_commit: 17b2b924d4b5a87b65901967fdd3acfec97886ea
evidence_root: /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/
confirmed_conclusions:
  - Clean main at 866656b contains the qualified migration and is the selected implementation base; CP-FUSION-001.
  - The frozen MuJoCo policy SHA-256 is aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356; CP-FUSION-001.
  - Historical CP-156 records separate qualified FULL_RESTART EXP-158 through EXP-162 and RESET_WORLD EXP-163 through EXP-167 batches; CP-FUSION-001.
  - The initialized clean-baseline MuJoCo Python suite passes 525 tests with 4 skips; CP-FUSION-001.
  - Tasks 2-5 preserve mapped identity, core/runtime parity, nine-phase order, and exact v1 simulator policy bytes; CP-FUSION-002.
  - Task 6 installs strict neutral world/lifecycle contracts and MuJoCo adapters with fresh-state validation; CP-FUSION-003.
  - Task 7 installs typed robot/scene ports and removes direct ROS client construction from application; CP-FUSION-004.
  - Task 8 makes lossless physics-step tracing optional for execute and mandatory for MuJoCo qualification; CP-FUSION-005.
  - Task 9 centralizes backend composition and separates execution classification from qualification status; CP-FUSION-006.
  - Task 10 installs common visual/task geometry with separate simulator collision/physics trees; CP-FUSION-007.
  - Task 11 installs four explicit launchers and restores exact qualified MuJoCo model/scene fingerprints; CP-FUSION-008.
disproven_routes:
  - Historical TASK15-FULL-A is INVALID because headless execution could not satisfy the required viewer-camera readiness gate; CP-156.
  - Recreating or sourcing the removed migration worktree is unnecessary and would contradict the verified merged-main handoff; CP-FUSION-001.
open_hypotheses:
  - The strangler migration can preserve the qualified MuJoCo behavior while making the unified package the sole runtime owner.
  - The clean-main Gazebo installed-independence failure will become GREEN when Tasks 10 and 14 remove legacy runtime ownership.
latest_checkpoint: CP-FUSION-017
next_experiment: NONE_RUNNER_REPAIR_COMMIT
---

# SO-101 Demo Python Fusion Experiment Ledger

Raw build, test, runtime, screenshot, video, and qualification evidence remains under the single
task evidence root. This ledger stores checkpoints and conclusions only. Live experiments must be
pre-registered here before any stack is launched.

## Checkpoint CP-FUSION-016 — qualification runner and pinned-fork gate

```yaml
checkpoint_id: CP-FUSION-016
status: COMPLETE
source_commit: 17b2b924d4b5a87b65901967fdd3acfec97886ea
installed_prefix: /data/work/ws_moveit/.worktrees/so101-demo-py-fusion/install/fusion-final/so101_demo_py
mujoco_ros2_control:
  gitlink_commit: 738e304551b4ea6db020b466086a13db71b65607
  installed_prefix: /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install
  executable_sha256: 9fd047eaae7ed2eff3f49aeb42880f88019ccf84787ecd5183ee5de78d73506e
policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
bundle_sha256: d9a0206b7e1a36b75a0cc0240117d29966bfcf8a2b9bcf09c6146d73dfab7459
static_gates:
  unified_tests: 102 passed
  teleop_profile_tests: 18 passed
  installed_provenance: 3 passed
  fusion_contract: PASS
noncounting_smoke:
  batch_id: fusion-smoke-005
  lifecycle: FULL_RESTART
  result: VALID_SUCCESS_NONCOUNTING
  completed_phases: [staged_approach, contact_hold, micro_lift, policy_lift_waypoint1, remaining_lift, transport, descend, place_alignment, release_retreat]
  reset_epoch: 1
  physical_outcome: {primary_failure: null, intended_support_contact: true, moveit_attached: false, world_object_synchronized: true}
  final_cup_position_world_m: [-0.07915379018633091, -0.2490218766824613, 0.16547659376286236]
  clean_shutdown: PASS
  manifest_sha256: 21f0bd3ddd26d2ba774a79a7fa1426d19e304b83af9178463f67b054f0659aac
diagnosis_closed:
  - Two earlier non-counting native crashes resolved to the wrong /opt/ros/jazzy mujoco_ros2_control runtime; the bundle now hashes the pinned fork executable and rejects that provenance drift.
  - Headless qualification no longer calls the unavailable interactive viewer.
  - Ordered shutdown signals only the stack supervisor, avoiding duplicate SIGINT delivery through ROS launch.
owned_processes_after_smoke: NONE
preserved_sessions_unchanged: [MNT-Q-RESET-EXP136-140, codex, codex-cua, so101-mujoco-gui]
decision: Freeze this source, installed overlay, policy, pinned dependency, and bundle for both counted Task 17 and Task 18 batches.
```

## Checkpoint CP-FUSION-017 — first counted batch terminated on invalid evidence

```yaml
checkpoint_id: CP-FUSION-017
terminal_batch: fusion-full-restart-001
task: 17
lifecycle: FULL_RESTART
status: INVALID_BATCH
source_commit: 17b2b924d4b5a87b65901967fdd3acfec97886ea
bundle_sha256: d9a0206b7e1a36b75a0cc0240117d29966bfcf8a2b9bcf09c6146d73dfab7459
attempt_count: 2
run_01: {status: SUCCESS, reset_epoch: 1, physical_primary_failure: null, clean_shutdown: true}
run_02:
  runner_recorded_status: VALID_FAILURE
  corrected_classification_from_raw_evidence: INVALID
  failed_phase: transport
  phase_exit_code: 1
  evidence_outcome_class: INVALID_EVIDENCE
  invalid_reason: EvidenceInvalid chunk sequence mismatch
  persisted_chunk_sequence_range: [4974, 5667]
  persisted_physics_step_range: [24871, 28340]
  persisted_chunks_contiguous: true
  producer_history_depth: 100
  consumer_history_depth: 20
  physical_policy_failure: false
  clean_shutdown: true
manifest_sha256: ea084fa0a2a15c7ae5eb15ddd182ef40f79bbf838bcc5f7e62e405e2e1856428
diagnosis:
  observed: The durable index has 694 consecutive chunks with no internal sequence or physics-step gap, then the observer latched the next-delivery sequence mismatch.
  inference: The reliable high-rate consumer retained only 20 samples while the producer retained 100, allowing executor/storage scheduling to overrun subscriber history without a producer evidence_loss latch.
  classification_defect: teleop_workflow returned only PHASE_EXIT_NONZERO, so the qualification runner incorrectly called invalid trace evidence a VALID_FAILURE.
repair_gates:
  - consumer reliable history depth must be at least producer depth 100
  - INVALID_EVIDENCE must propagate as TELEOP_WORKFLOW_EVIDENCE_INVALID
  - focused tests and complete installed gates must pass before committing a new source/bundle
owned_processes_after_batch: NONE
preserved_sessions_unchanged: [MNT-Q-RESET-EXP136-140, codex, codex-cua, so101-mujoco-gui]
decision: Preserve and reject the entire batch. Repair evidence handling, commit/rebuild a new immutable bundle, then preregister a fresh FULL_RESTART batch; no result from this batch may be reused.
```

## Planned batch FUSION-FULL-RESTART-001

```yaml
batch_id: fusion-full-restart-001
status: PLANNED
task: 17
lifecycle: FULL_RESTART
backend: mujoco
required_consecutive_successes: 5
invalid_run_effect: invalidate_batch
valid_failure_effect: break_streak
source_commit: 17b2b924d4b5a87b65901967fdd3acfec97886ea
installed_prefix: /data/work/ws_moveit/.worktrees/so101-demo-py-fusion/install/fusion-final/so101_demo_py
mujoco_ros2_control_prefix: /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install
mujoco_ros2_control_gitlink: 738e304551b4ea6db020b466086a13db71b65607
mujoco_ros2_control_executable_sha256: 9fd047eaae7ed2eff3f49aeb42880f88019ccf84787ecd5183ee5de78d73506e
policy_id: light_cup_wall_pick
policy_version: v1
policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
bundle_sha256: d9a0206b7e1a36b75a0cc0240117d29966bfcf8a2b9bcf09c6146d73dfab7459
ros_domain_ids: [180, 181, 182, 183, 184]
ports: [27500, 27501, 27502, 27503, 27504]
evidence_root: /data/work/so101-debug-fusion-full-restart-001
evidence_root_pre_registration_state: ABSENT
evidence_filesystem: /data NVMe
command: ros2 run so101_demo_py run_qualification --batch-id fusion-full-restart-001 --lifecycle FULL_RESTART --count 5 --fingerprint d9a0206b7e1a36b75a0cc0240117d29966bfcf8a2b9bcf09c6146d73dfab7459 --evidence-root /data/work/so101-debug-fusion-full-restart-001 --base-domain-id 180 --base-port 27500 --headless
owned_processes_before_launch: NONE
preserved_processes: tmux sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui; pre-existing ros2 daemons
abort_criteria:
  - any source, installed-prefix, dependency, policy, bundle, session, lifecycle, or epoch mismatch
  - any invalid run, valid physical failure, missing/truncated artifact hash, or unclean shutdown
  - any unowned process selected for cleanup
cleanup_scope: each independently created qualification supervisor and its exact child launch trees only
expected: exactly five independent VALID/SUCCESS records with unique sessions and clean ordered shutdown
```

## Checkpoint CP-FUSION-015 — compatibility, real-stub, and installed static gates

```yaml
checkpoint_id: CP-FUSION-015
status: COMPLETE
tasks: [14, 15, 16]
legacy_compatibility:
  focused_test_result: 15 passed
  full_unified_test_result_before_task_16: 88 passed
  old_cli_exit_codes: {mujoco: 0, gazebo: 0}
  deprecation_warning_count_per_command: 1
  unified_forward_target: so101_demo/cli/pick_place.py
  legacy_runtime_files_removed: 412
  legacy_binary_assets_removed: 150
  legacy_installed_runtime_assets: NONE
real_stub:
  focused_test_result: 10 passed
  run_status: REJECTED
  error_code: REAL_HARDWARE_NOT_CONFIGURED
  io_symbols_present: false
  real_launcher_present: false
installed_gate:
  overlay: /data/work/ws_moveit/.worktrees/so101-demo-py-fusion/install/fusion-final
  clean_dependency_closure_packages_built: 9
  contract_test_result: 91 passed
  collected_tests: 91
  installed_provenance_test_result: 3 passed
  installed_executables: [gazebo_execute, pick_place, run_qualification, scene_setup]
  installed_launchers: [so101_gazebo.launch.py, so101_gazebo_pick_place.launch.py, so101_mujoco.launch.py, so101_mujoco_pick_place.launch.py]
  policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  provisional_bundle_sha256: 55169154005eca4a06d479ac188baf179ce58f02b4e64f7f3660cef18cbea85c
decision: Commit the static acceptance artifacts, rebuild the final overlay at that immutable commit, then preregister independent FULL_RESTART and RESET_WORLD qualification batches.
```

## Baseline recovery

The last trusted historical checkpoint is migration ledger `CP-156`. Its counted qualification
batches are `EXP-158` through `EXP-162` (`FULL_RESTART`) and `EXP-163` through `EXP-167`
(`RESET_WORLD`). Those results establish the behavior baseline only and are never counted toward
the new fusion bundle.

The approved plan's former migration-worktree commands are stale after the migration was merged
and that worktree was removed. The verified handoff and live clean-main/content checks replace
that path-specific probe without weakening the baseline gate. The installed colcon CLI also
requires global `--log-base` before the subcommand, so plan commands will use that equivalent
argument order.

## Checkpoint CP-FUSION-001

```yaml
checkpoint_id: CP-FUSION-001
last_valid_experiment: EXP-168 historical uncounted visual corroboration
current_hypothesis: Mechanical migration from the qualified MuJoCo package can preserve all nine production phases under the new mapped namespace.
working_tree_status: Clean implementation worktree at 66918d7 before adding this ledger and baseline provenance record.
owned_processes: NONE
preserved_processes: tmux sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui; no live SO-101, ROS, Gazebo, RViz, MoveIt, or MuJoCo process was observed.
confirmed_conclusions:
  - Main, origin/main, and the selected base all equal 866656b217eff4c57eade161c94ea0cef326d13d.
  - The implementation worktree is isolated on codex/so101-demo-py-fusion and contains only the two approved docs-only commits above the selected base.
  - The canonical policy hash is aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356.
  - The historical FULL_RESTART qualification manifest remains available and hashes to 98c29b847cd40c5ca2061596739f8d66eaf96d3b4b1c707048371fb9773b6f11.
  - After pinned submodule initialization, the MuJoCo Python baseline is 525 passed and 4 skipped.
  - Gazebo baseline is 227 passed, 1 failed, and 2 skipped; the failure is the pre-existing installed legacy-ownership sentinel targeted by Tasks 10 and 14.
disproven_routes:
  - Running both flat test directories in one pytest process is invalid because duplicate test module basenames collide; package suites must be invoked independently.
  - Running linked-worktree dependency tests before submodule initialization produces false wrong-remote/wrong-commit evidence because git falls back to the superproject.
open_risks:
  - No unified package exists yet and no fusion-bundle live behavior has been tested.
  - The Gazebo clean-main ownership failure must become GREEN without weakening the installed-independence contract.
next_command: Write and run the Task 2 mapped-layout RED tests before creating src/so101_demo_py production files.
```

## Checkpoint CP-FUSION-002

```yaml
checkpoint_id: CP-FUSION-002
last_valid_experiment: EXP-168 historical uncounted visual corroboration; no fusion live experiment has started
current_hypothesis: The direct MuJoCo world and lifecycle dependencies can be replaced by neutral ports without changing the installed nine-phase behavior.
working_tree_status: HEAD 616308b3bc24c4cc2c0d684a2aa2e6c8f503d3a7; Task 5 policy registry, provenance, immutable variants, tests, and this ledger checkpoint are intentionally dirty before the scoped Task 5 commit.
owned_processes: NONE
preserved_processes: tmux sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui; no preserved session was controlled.
confirmed_conclusions:
  - Task 2 mapped namespace/ament identity is installed under install/fusion-t2 and its four original identity tests passed.
  - Task 3 core parity plus selected legacy domain/runner/policy tests passed 43/43; unified tests at that checkpoint passed 10/10.
  - Task 4 unified tests passed 14/14 and the selected legacy motion/MoveIt/runtime/phase/qualification/outcome/recovery suite passed 150/150.
  - Task 4 installed executables are pick_place and run_qualification; installed dry-run completes the unchanged 19-transition state trace.
  - Task 5 unified suite passes 25/25 and its installed provenance module prints exactly one 64-character hash with empty stderr.
  - v1 mujoco.yaml and gazebo.yaml are byte-identical to the canonical source and each hash to aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356.
  - No live stack, GUI action, or physical experiment was needed for Tasks 1-5.
disproven_routes:
  - The design snippet using find_packages(where="src", include=(python_package, ...)) would discover zero packages for a namespace mapped directly to the src directory; behavioral setup capture proves the explicit mapped-root plus prefixed subpackage list.
  - An immutable MappingProxyType bundle manifest is not JSON serializable; canonical plain mappings retain deterministic hashing and support evidence publication.
  - Eagerly importing provenance from runtime.__init__ contaminates module execution with a runpy warning; the runtime package now leaves module selection explicit.
open_risks:
  - MuJoCo application phases still consume direct concrete clients; Tasks 6-9 must inject neutral ports one boundary at a time.
  - The current bundle hash covers the policy registry and installed prefix only; Tasks 10 and 16 must expand it to the complete installed asset/control/evidence closure before qualification.
next_command: Write and run Task 6 WorldPort/LifecyclePort contract tests before modifying the MuJoCo adapters or application.
evidence:
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task3-green.log sha256=50b8f9f6d1a623001b13c6d56e82ba636af5acaf0eb2d3c285b40e977928a188
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task4-unified-tests.log sha256=e9a40502bbab4cd186bd34f41859604522147a6b66ee852c24ddbc945d7e0a5a
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task4-legacy-selected.log sha256=7eb2a748ac180ba6cc281861db498e923702dc0a24152ca1c96addd88a16dcad
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task5-unified-tests.log sha256=f2a8ce02b42cc30701feff1a09e68203a567b1e4f46c1861cb179bdb4da53bd1
```

## Planned experiment EXP-FUSION-003

```yaml
experiment_id: EXP-FUSION-003
status: PLANNED
purpose: Task 13 one bounded installed Gazebo execute through the unified simulator/model/controller/MoveIt graph and common result classification.
lifecycle: FULL_RESTART_SINGLE_RUN
counting_qualification_run: false
source_commit: f184617805e551b92bc5773433244c6193442abc
installed_prefix: /data/work/ws_moveit/.worktrees/so101-demo-py-fusion/install/fusion-t13-live/so101_demo_py
runtime_executable: /opt/ros/jazzy/bin/ros2
backend: gazebo
policy_id: light_cup_wall_pick
policy_version: v1
policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
bundle_sha256: 4edb642e4f152eb913fac5d2fecd2e6a969fad3a8774be72749c92e75092382f
ros_domain_id: 173
gz_partition: fusion-exp-003-f184617
session_id: fusion-exp-003-f184617
evidence_root: /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/exp-fusion-003
evidence_root_pre_registration_state: ABSENT
command: ros2 launch so101_demo_py so101_gazebo_pick_place.launch.py run_mode:=execute execute:=true headless:=true policy_id:=light_cup_wall_pick policy_version:=v1 session_id:=fusion-exp-003-f184617 evidence_file:=/tmp/so101-debug-so101-demo-py-fusion-SyIBjl/exp-fusion-003/result.json readiness_timeout_s:=60.0
owned_processes_before_launch: NONE
preserved_processes: tmux sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui; pre-existing ros2 daemons
acceptance:
  - result is FAILED or SUCCEEDED with evidence_valid semantics; INVALID cannot satisfy Task 13
  - no SKIPPED or pre-rejected Gazebo path
  - FAILED identifies the first real phase and stable action/planning error code
  - source, prefix, policy, bundle, session, ROS domain, and GZ partition match registration
abort_criteria:
  - provenance or identity mismatch
  - missing/contaminated initial world, joint, controller, bridge, or MoveIt evidence
  - unowned process selected for control or cleanup
cleanup_scope: only the launch process group and GZ partition created for EXP-FUSION-003; bounded shutdown followed by exact owned-PID/partition audit
expected: a valid non-INVALID policy result at the first natural controller/MoveIt boundary, likely MOVE_ABOVE_OBJECT PATH_TOLERANCE_VIOLATED, with nonzero exit for FAILED
```

## Checkpoint CP-FUSION-012 — EXP-FUSION-003 invalid pre-action provenance abort

```yaml
checkpoint_id: CP-FUSION-012
terminal_experiment: EXP-FUSION-003
status: INVALID_PREACTION_ABORT
failure: Installed symlink provenance resolved the later ledger HEAD 27c7b9c2d07b56276e176efcc8ca4cb5d3a353be because SO101_SOURCE_COMMIT was omitted, instead of the registered implementation commit f184617805e551b92bc5773433244c6193442abc.
observed_bundle_sha256: e3fdba028e2af5b0975cdd44111333360b8f9f4abe1d8c0496a8b2368fb321c8
expected_bundle_sha256: 4edb642e4f152eb913fac5d2fecd2e6a969fad3a8774be72749c92e75092382f
simulation_started: true
controller_action_started: false
result_manifest_created: false
identifier_reusable: false
cleanup:
  exact_owned_process_group: 2949049
  signal: SIGINT
  owned_processes_after_probe: NONE
  preserved_sessions_unchanged: [MNT-Q-RESET-EXP136-140, codex, codex-cua, so101-mujoco-gui]
artifact_sha256:
  launch_log: acdf931bdd749dd03d0d6fd4d62616e17562035fcc81ab00d8d1cd2c65cfa142
root_cause: Runtime provenance intentionally honors SO101_SOURCE_COMMIT; the launch environment must freeze it when ledger commits occur after the immutable implementation build.
decision: Register a fresh ID with the identical installed bytes and behavior, explicitly exporting the already registered source commit. Do not rebuild or alter policy/behavior.
next_experiment: EXP-FUSION-004
```

## Planned experiment EXP-FUSION-004

```yaml
experiment_id: EXP-FUSION-004
status: PLANNED
purpose: Replacement Task 13 bounded Gazebo execute after correcting only the launch provenance environment.
lifecycle: FULL_RESTART_SINGLE_RUN
counting_qualification_run: false
source_commit: f184617805e551b92bc5773433244c6193442abc
installed_prefix: /data/work/ws_moveit/.worktrees/so101-demo-py-fusion/install/fusion-t13-live/so101_demo_py
policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
bundle_sha256: 4edb642e4f152eb913fac5d2fecd2e6a969fad3a8774be72749c92e75092382f
single_variable_from_EXP_FUSION_003: Export SO101_SOURCE_COMMIT=f184617805e551b92bc5773433244c6193442abc before provenance audit and launch.
behavior_changes: NONE
ros_domain_id: 174
gz_partition: fusion-exp-004-f184617
session_id: fusion-exp-004-f184617
evidence_root: /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/exp-fusion-004
evidence_root_pre_registration_state: ABSENT
owned_processes_before_launch: NONE
preserved_processes: tmux sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui; pre-existing ros2 daemons
acceptance_and_abort_criteria: IDENTICAL_TO_EXP_FUSION_003
cleanup_scope: only the launch process group and GZ partition created for EXP-FUSION-004
expected: registered source/bundle at launch, then a valid non-INVALID natural Gazebo result
```

## Checkpoint CP-FUSION-014 — EXP-FUSION-005 valid Gazebo execute boundary

```yaml
checkpoint_id: CP-FUSION-014
terminal_experiment: EXP-FUSION-005
status: COMPLETE
task_13_gate: PASS
run_status: FAILED
qualification_status: NOT_QUALIFIED
failure_category: EXECUTION
first_failed_phase: PREPARE_OPEN_GRIPPER
error_code: ACTION_REJECTED
evidence_valid: true
runner_exit_code: 1
simulation_started: true
controller_action_started: true
observed_boundary: The gripper FollowJointTrajectory server received and rejected the pre-open goal while controller activation completed; this is the first actual controller boundary and is classified as a valid execution failure, not INVALID or SKIPPED.
provenance:
  source_commit: f184617805e551b92bc5773433244c6193442abc
  policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
  bundle_sha256: 4edb642e4f152eb913fac5d2fecd2e6a969fad3a8774be72749c92e75092382f
  ros_domain_id: 175
  gz_partition: fusion-exp-005-f184617
evidence_retained: [initial_joints_rad, terminal_joints_rad, world_pose, world_stats, action_status, action_error_code]
artifact_sha256:
  launch_log: c19793b53d7678ff986f4df8dca73d592eedadc07dfcb264906cca375bf2f16b
  result_manifest: 5c761515ebdaad9c0cef67106f6c6e086dc13b37a907ae0de3c8ae0ac72b460b
  raw_evidence: ceabcdd2970be226ae45aecfe8af011f08df67419142a3df21613ee9273c6cfc
cleanup:
  owned_processes_after_probe: NONE
  preserved_sessions_unchanged: [MNT-Q-RESET-EXP136-140, codex, codex-cua, so101-mujoco-gui]
decision: Task 13 accepts either valid FAILED or SUCCEEDED. Proceed to compatibility forwarding without tuning Gazebo behavior.
```

## Checkpoint CP-FUSION-013 — EXP-FUSION-004 invalid pre-launch command

```yaml
checkpoint_id: CP-FUSION-013
terminal_experiment: EXP-FUSION-004
status: INVALID_PRELAUNCH_ABORT
failure: The operator invoked nonexistent gazebo_demo.launch.py instead of the registered so101_gazebo_pick_place.launch.py entry point.
simulation_started: false
controller_action_started: false
result_manifest_created: false
identifier_reusable: false
owned_processes_after_probe: NONE
artifact_sha256:
  launch_log: d3e74c9a101e999a2accb8a65e8f86254c1249e69db8bdf588915d1b36330eca
decision: Register a fresh ID with identical installed bytes, provenance, behavior, and acceptance criteria; correct only the launch filename.
next_experiment: EXP-FUSION-005
```

## Planned experiment EXP-FUSION-005

```yaml
experiment_id: EXP-FUSION-005
status: PLANNED
purpose: Replacement Task 13 bounded Gazebo execute after correcting only the launch filename.
lifecycle: FULL_RESTART_SINGLE_RUN
counting_qualification_run: false
source_commit: f184617805e551b92bc5773433244c6193442abc
installed_prefix: /data/work/ws_moveit/.worktrees/so101-demo-py-fusion/install/fusion-t13-live/so101_demo_py
policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
bundle_sha256: 4edb642e4f152eb913fac5d2fecd2e6a969fad3a8774be72749c92e75092382f
single_variable_from_EXP_FUSION_004: Invoke so101_gazebo_pick_place.launch.py, the installed launch entry point named in the approved plan and EXP-FUSION-003 registration.
behavior_changes: NONE
ros_domain_id: 175
gz_partition: fusion-exp-005-f184617
session_id: fusion-exp-005-f184617
evidence_root: /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/exp-fusion-005
evidence_root_pre_registration_state: ABSENT
owned_processes_before_launch: NONE
preserved_processes: tmux sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui; pre-existing ros2 daemons
acceptance_and_abort_criteria: IDENTICAL_TO_EXP_FUSION_003
cleanup_scope: only the launch process group and GZ partition created for EXP-FUSION-005
expected: registered source/bundle at launch, then a valid non-INVALID natural Gazebo result
```

## Checkpoint CP-FUSION-003

```yaml
checkpoint_id: CP-FUSION-003
last_valid_experiment: EXP-168 historical uncounted visual corroboration; no fusion live experiment has started
current_hypothesis: Shared MoveIt and ros2_control behavior can be placed behind typed robot-control and planning-scene ports without changing the qualified phase semantics.
working_tree_status: HEAD 703c765edd48d0a451179001ea343886d9ec11b8; Task 6 ports, adapters, tests, and this checkpoint are intentionally dirty before the scoped Task 6 commit.
owned_processes: NONE
preserved_processes: tmux sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui; pre-existing ros2 daemon processes only; no preserved session or daemon was controlled.
confirmed_conclusions:
  - WorldEvidence and receipt values are immutable, finite, backend-neutral, and retain MuJoCo-only quantities under backend_metadata.
  - MuJoCo world adaptation rejects same-session/epoch publisher-sequence or simulation-step regression.
  - MuJoCo reset and pause results require observed post-request world state; raw service acknowledgement alone is insufficient.
  - Task 6 focused source/installed contracts pass 7/7 after the fusion-t6 build.
  - The frozen MuJoCo policy remains aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356.
disproven_routes:
  - A zero-contact legacy SimulationEvidence fixture cannot carry a nonzero aggregate signed distance; the real value invariant correctly rejected that invalid test setup.
  - Running the Task 6 live execute before unified assets and launch ownership exist would execute an old package's stack and produce falsely attributed fusion evidence.
open_risks:
  - Phase modules still construct concrete robot/scene clients and must be migrated through Tasks 7-9 before the application import-boundary gate is green.
  - The deferred Task 6-9 installed live gate must be run from the unified launcher after Tasks 10-11, with a pre-registered isolated-stack experiment.
next_command: Write and run Task 7 PlanningScenePort and RobotControlPort RED contracts.
evidence:
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task6/contracts.log sha256=229e4533d1597c28d56b8b7c42e076151a9d019effe66ced40bfb2ba3347ae36
  - log/fusion-t6/latest_build
```

## Checkpoint CP-FUSION-004

```yaml
checkpoint_id: CP-FUSION-004
last_valid_experiment: EXP-168 historical uncounted visual corroboration; no fusion live experiment has started
current_hypothesis: MuJoCo physics-step diagnostics can become an optional capability-gated port without changing the qualified transport implementation.
working_tree_status: HEAD 7574f2dca28126849f156230768204936a1e03fe; Task 7 ports, shared controls, concrete-phase relocation, tests, and this checkpoint are intentionally dirty before the scoped Task 7 commit.
owned_processes: NONE
preserved_processes: unchanged preserved tmux sessions and pre-existing ros2 daemons; no process or session was controlled.
confirmed_conclusions:
  - Planning Scene attachment is typed as planning shadow only and cannot claim physical-grasp proof.
  - Temporary collision permission is represented by an auditable single-pair lease with an exact one-time restore operation.
  - SharedRobotControl captures the plan start state and rejects execution after joint-state drift beyond tolerance.
  - The application tree contains no create_client, ActionClient, or FollowJointTrajectory construction; qualified concrete ROS/MuJoCo entry points live under the MuJoCo adapter tree.
  - The complete unified suite passes 37/37 after the fusion-t7 build, and the installed dry-run retains the exact 19-transition trace.
  - The frozen MuJoCo policy remains aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356.
disproven_routes:
  - Protocol declarations alone were insufficient: the Task 7 source scan exposed direct application client creation until the qualified concrete entry points were moved behind the backend boundary.
open_risks:
  - The CLI still selects the MuJoCo lifecycle callback directly; Task 9 must make runtime composition the sole backend selector.
  - The qualified concrete phase sequence still uses MuJoCo-specific trace observers; Task 8 must expose the diagnostic contract and enforce it only for the qualification profile.
next_command: Write and run Task 8 PhaseEvidencePort and capability-requirement RED tests.
evidence:
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task7/unified-tests.log sha256=bc3ccfa25decf36a5f93b78e8da1ae26ac0fb5b1312cb8711260a9c4900b4e7e
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task7/application-client-scan.log sha256=0aec8a871a5714aed65de820979bf5e9ad3ae180970168cec852b054c2e0d83b
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task7-dry-run.log sha256=ce72e16ecb692aa0a1555ea6a15834ab984c05495b6da872e76a7aa087c54074
  - log/fusion-t7/latest_build
```

## Checkpoint CP-FUSION-005

```yaml
checkpoint_id: CP-FUSION-005
last_valid_experiment: EXP-168 historical uncounted visual corroboration; no fusion live experiment has started
current_hypothesis: Runtime composition can become the sole backend selector while preserving the distinction between run validity and qualification outcome.
working_tree_status: HEAD 2af3b51ff36d01291261762e9530b919a5ec71cb; Task 8 trace port, capability rules, adapter, tests, and this checkpoint are intentionally dirty before the scoped Task 8 commit.
owned_processes: NONE
preserved_processes: unchanged preserved tmux sessions and pre-existing ros2 daemons; no process or session was controlled.
confirmed_conclusions:
  - CapabilityRequirements.base_execute accepts a backend without lossless physics-step trace.
  - CapabilityRequirements.mujoco_qualification rejects that same backend with CAPABILITY_MISSING and names lossless_physics_step_trace.
  - PhaseEvidencePort exposes observation-only trace begin, boundary, and finish receipts bound to session and reset epoch.
  - The MuJoCo phase-evidence adapter delegates only to trace observer/checkpoint methods and has no world, policy, trajectory, or pause mutation surface.
  - The complete unified suite passes 41/41 after the fusion-t8 build, and the installed dry-run retains the exact 19-transition trace.
  - The frozen MuJoCo policy remains aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356.
disproven_routes:
  - Treating the qualified MuJoCo trace as a universal simulator prerequisite would incorrectly reject the planned Gazebo v1 execute path.
open_risks:
  - Backend selection and live result classification are not yet centralized; the CLI still imports a MuJoCo lifecycle callback directly.
  - The Task 6-9 live gate remains deferred until the unified package owns its installed assets and launch graph.
next_command: Write and run Task 9 runtime-composition, result-classification, and AST import-boundary RED tests.
evidence:
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task8/unified-tests.log sha256=2f4732c586995104aa071102838621cbfe536f747d36a0e7427909f1c6593a0d
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task8/dry-run.log sha256=ce72e16ecb692aa0a1555ea6a15834ab984c05495b6da872e76a7aa087c54074
  - log/fusion-t8/latest_build
```

## Checkpoint CP-FUSION-006

```yaml
checkpoint_id: CP-FUSION-006
last_valid_experiment: EXP-168 historical uncounted visual corroboration; no fusion live experiment has started
current_hypothesis: Common visual/task geometry can be made single-source while preserving backend-specific collision and physics assets.
working_tree_status: HEAD 93beccf1e811a83c15586236a8d903f95ff03d7d; Task 9 composition, result model, CLI routing, tests, and this checkpoint are intentionally dirty before the scoped Task 9 commit.
owned_processes: NONE
preserved_processes: unchanged preserved tmux sessions and pre-existing ros2 daemons; no process or session was controlled.
confirmed_conclusions:
  - Runtime composition selects exactly one backend, exact policy variant, explicit adapter set, capabilities, and deterministic qualification bundle without fallback.
  - Core and application AST scans reject imports rooted at so101_demo.backends, mujoco, gazebo, or ros_gz.
  - Valid policy/execution failures classify as FAILED; contaminated evidence classifies as INVALID; capability/safety refusal classifies as REJECTED.
  - QualificationStatus is independent of execution status.
  - The complete unified suite passes 47/47 after the fusion-t9 build, and the installed --backend mujoco --run-mode dry_run path retains the exact 19-transition trace.
  - The frozen MuJoCo policy remains aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356.
disproven_routes:
  - Extending the frozen state-machine RunStatus enum breaks Task 3 public-domain parity; the new four-way execution classification therefore uses the separate ExecutionRunStatus enum while legacy RunStatus remains unchanged.
open_risks:
  - The composition bundle still lacks the unified asset closure that Task 10 must install and Task 16 must gate.
  - Concrete runtime adapter construction needs the installed launch graph from Tasks 10-12; the adapter provider is intentionally explicit and fail-closed until then.
next_command: Write and run Task 10 geometry-manifest and installed asset-closure RED tests.
evidence:
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task9/unified-tests.log sha256=a40a1467baf3f2b62bc1f66d715e6cd7155b2eb4f4d52c5009bfa7b1b6be3805
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task9/dry-run.log sha256=ce72e16ecb692aa0a1555ea6a15834ab984c05495b6da872e76a7aa087c54074
  - log/fusion-t9/latest_build
```

## Checkpoint CP-FUSION-007

```yaml
checkpoint_id: CP-FUSION-007
last_valid_experiment: EXP-168 historical uncounted visual corroboration; no fusion live experiment has started
current_hypothesis: Four explicit launch entry points can share argument/provenance composition while selecting distinct simulator graphs.
working_tree_status: HEAD fc0285d2280fd68f5cff8acb8a0bf0ebe2230209; Task 10 assets, manifest, packaging, tests, and this checkpoint are intentionally dirty before the scoped Task 10 commit.
owned_processes: NONE
preserved_processes: unchanged preserved tmux sessions and pre-existing ros2 daemons; no process or session was controlled.
confirmed_conclusions:
  - Both simulator manifests point visual geometry to assets/common/visual while retaining separate assets/mujoco/collision and assets/gazebo/collision trees.
  - Common visual meshes are byte-identical between the two legacy package sources and every installed common visual is SHA-256 enumerated.
  - Unified MuJoCo scene.xml compiles successfully through the installed MuJoCo C library after path rewriting.
  - Source asset tests pass 6/6; installed closure passes 3/3; the complete unified suite passes 53/53 after the fusion-t10 build.
  - No unified installed asset text references so101_mujoco_demo_py or so101_gazebo_demo_py.
  - The qualification bundle now hashes the complete installed assets tree.
  - The frozen MuJoCo policy remains aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356.
disproven_routes:
  - Importing the pip-style mujoco Python module is unavailable in this environment; the repository's established ctypes compile gate against /opt/ros/jazzy/opt/mujoco_vendor/lib/libmujoco.so is the valid check.
  - gz sdf -k is not a clean regression gate for this committed world because both the legacy and unified files report the same pre-existing non-unique cup link child names.
open_risks:
  - Launch composition and backend-specific installed environment variables are not yet owned by the unified package.
  - The Gazebo model's semantic execution must be tested through the real Task 13 launch, not inferred from static SDF validation.
next_command: Write and run Task 11 launch-composition argument and ownership RED tests.
evidence:
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task10/unified-tests.log sha256=314da351f80066375fef750f2bb45e062edccfc46922f80c0f37e6208f792ccd
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task10/installed-closure.log sha256=e0a6ea218ea5d725ce7272da8d68d45a029e489423e03af6960c7bff0f7fe414
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task10/mujoco-compile.log sha256=4f876d366ffab84cd4db209096d5fc10b8be80890d82adf0204fafc5460996cd
  - log/fusion-t10/latest_build
```

## Checkpoint CP-FUSION-008

```yaml
checkpoint_id: CP-FUSION-008
last_valid_experiment: EXP-168 historical uncounted visual corroboration; no fusion live experiment has started
current_hypothesis: The unified installed MuJoCo launch graph can complete one isolated qualified execute without reading either legacy package.
working_tree_status: HEAD 01b252a8b0d04c8f62ceaf052991b936b2723f25; Task 11 launch/config/runtime closure, tests, and this checkpoint are intentionally dirty before the scoped Task 11 commit.
owned_processes: NONE
preserved_processes: unchanged preserved tmux sessions and pre-existing ros2 daemons; no process or session was controlled.
confirmed_conclusions:
  - Four installed launchers exist for explicit MuJoCo/Gazebo stack and pick-place entry points; none declares a backend argument.
  - Common launch arguments are run_mode, execute, headless, policy_id, policy_version, session_id, evidence_file, and readiness_timeout_s.
  - MuJoCo declares only mujoco_scene and Gazebo declares only gazebo_world.
  - Installed launch provenance logs backend, exact source commit, installed prefix, policy SHA-256, bundle SHA-256, execute state, session, ROS domain, and Gazebo partition where applicable.
  - The complete unified suite passes 57/57; both --show-args gates pass; installed MuJoCo launch dry-run retains the exact 19-transition trace.
  - Qualified MuJoCo XML was restored byte-for-byte after a path-only rewrite was found to break the approved contact fingerprint: model f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca and scene b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0.
  - The frozen MuJoCo policy remains aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356.
disproven_routes:
  - Semantically equivalent XML path rewrites are not provenance-equivalent and cannot be used with the approved contact calibration fingerprint.
open_risks:
  - The newly owned MuJoCo execute graph has not yet been launched; it requires a pre-registered isolated-stack experiment after this commit and rebuild.
  - Gazebo execute registration remains intentionally absent until Task 12 adapters are implemented.
next_command: Commit Task 11, rebuild from the clean commit, pre-register EXP-FUSION-001, and run the deferred isolated MuJoCo execute gate.
evidence:
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task11/unified-tests.log sha256=8a7c2bf4792044745a0bd452c6764604f458f985ef2a35df01ed50ddf9e87ec3
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task11/mujoco-show-args.log sha256=8a150c7dcade44efac9dc860f12a1465e41af6e51a3c88c55a812cf6b77e481e
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task11/gazebo-show-args.log sha256=84e10d1f45cbd7a78a1b24844013586504356fbb2e92a6e04be79ae58ff7bae6
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task11/dry-run.log sha256=111caa2698bd02860b7ce95112ce36f6873ba7ebe3c558acee5eeee1099aa3ec
  - log/fusion-t11/latest_build
```

## Planned experiment EXP-FUSION-001

```yaml
experiment_id: EXP-FUSION-001
status: PLANNED
purpose: Deferred Tasks 6-9 installed complete MuJoCo execute gate after unified asset and launch ownership exists.
lifecycle: ISOLATED_STACK
counting_qualification_run: false
source_commit: ab96a689f7c7db8c761d4bfb54b284ed3e1202ed
installed_prefix: /data/work/ws_moveit/.worktrees/so101-demo-py-fusion/install/fusion-t11-live/so101_demo_py
runtime_executable: /opt/ros/jazzy/bin/ros2
policy_id: light_cup_wall_pick
policy_version: v1
policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
bundle_sha256: d48293fde8a37f9d8f3450564c297506091588f6aa92d72deaf40bb162197978
ros_domain_id: 171
gz_partition: NOT_APPLICABLE
session_id: fusion-exp-001-ab96a68
evidence_root: /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/exp-fusion-001
command: ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py run_mode:=execute execute:=true headless:=true session_id:=fusion-exp-001-ab96a68 evidence_file:=/tmp/so101-debug-so101-demo-py-fusion-SyIBjl/exp-fusion-001/result.json
owned_processes_before_launch: NONE
preserved_processes: tmux sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui; pre-existing ros2 daemons
abort_criteria:
  - any session, epoch, policy, installed-prefix, or bundle mismatch
  - unavailable controller, MoveIt, scene, observer, reset/pause, or evidence service
  - any phase nonzero exit, missing/invalid evidence, safety boundary, or physical outcome failure
  - any unowned process selected for cleanup
cleanup_scope: only the launch process group created for EXP-FUSION-001; bounded launch shutdown, then exact owned-PID audit
expected: one complete nine-phase success, valid installed evidence manifest, and no owned orphan
```

## Checkpoint CP-FUSION-009 — EXP-FUSION-001 terminal valid failure

```yaml
checkpoint_id: CP-FUSION-009
recorded_at: 2026-08-13T03:17:31+08:00
terminal_experiment: EXP-FUSION-001
status: VALID_FAILURE_NONCOUNTING
source_commit: ab96a689f7c7db8c761d4bfb54b284ed3e1202ed
policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
bundle_sha256: d48293fde8a37f9d8f3450564c297506091588f6aa92d72deaf40bb162197978
completed_phases: [staged_approach, contact_hold, micro_lift, policy_lift_waypoint1, remaining_lift]
failed_phase: transport
failure: EvidenceInvalid chunk sequence mismatch
first_stored_chunk: {sequence: 5384, first_physics_step: 26923, last_physics_step: 26927, reset_epoch: 0}
diagnosis:
  first_bad_boundary: The strict high-rate transport consumer observed a gap immediately after its first durably checkpointed five-sample chunk.
  evidence_filesystem: {source: /dev/sda3, mount_target: /tmp, filesystem: ext4}
  matching_repository_evidence: MNT-CP-057 records the same /tmp chunk-gap failure; EXP-124 and EXP-126 through EXP-130 prove the unchanged 500 Hz trace on /data NVMe.
  robot_strategy_defect: false
  policy_or_threshold_defect: false
  unified_launch_or_phase_order_defect: false
  task_result: The unified launch graph, controllers, MoveIt, scene setup, and first five physical phases all executed; the deferred complete-execute gate remains unsatisfied.
artifacts_sha256:
  transport_result: fac1c77acbb34260737f04baf51b97e18e6b40474b553d674ccab06606e963df
  raw_run_index: 730ba2975dfccf0e7998d09a558827cbebe0a5e6f3f9487a9e9d1fc29c4d49a8
  live_runtime_manifest: 15472fd27a2665ff5db85e6a120cf351abdb4a4df1a9b0d181cd57a13eaf1f8f
  launch_log: 02b0502843c355373f57a68b38c8d89e9b419317d3d0f113910e2e2eb60d65f3
cleanup:
  ordered_launch_shutdown: true
  owned_processes_after_probe: NONE
  preserved_sessions_unchanged: [MNT-Q-RESET-EXP136-140, codex, codex-cua, so101-mujoco-gui]
decision: Do not reuse EXP-FUSION-001. Register one replacement with evidence storage as the sole changed variable and no source, policy, model, scene, timing, target, or threshold change.
next_experiment: EXP-FUSION-002
```

## Planned experiment EXP-FUSION-002

```yaml
experiment_id: EXP-FUSION-002
status: PLANNED
purpose: Replacement deferred Tasks 6-9 installed complete MuJoCo execute gate after correcting only the known high-rate durable-evidence storage boundary.
lifecycle: ISOLATED_STACK
counting_qualification_run: false
source_commit: ab96a689f7c7db8c761d4bfb54b284ed3e1202ed
installed_prefix: /data/work/ws_moveit/.worktrees/so101-demo-py-fusion/install/fusion-t11-live/so101_demo_py
runtime_executable: /opt/ros/jazzy/bin/ros2
policy_id: light_cup_wall_pick
policy_version: v1
policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
bundle_sha256: d48293fde8a37f9d8f3450564c297506091588f6aa92d72deaf40bb162197978
single_variable_from_EXP_FUSION_001: Evidence root moves from /tmp on /dev/sda3 to /data/work on /dev/nvme0n1p5.
behavior_changes: NONE
ros_domain_id: 172
gz_partition: NOT_APPLICABLE
session_id: fusion-exp-002-ab96a68
evidence_root: /data/work/so101-debug-so101-demo-py-fusion-SyIBjl/exp-fusion-002
evidence_root_pre_registration_state: ABSENT
evidence_filesystem: {source: /dev/nvme0n1p5, mount_target: /data, filesystem: ext4}
command: ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py run_mode:=execute execute:=true headless:=true session_id:=fusion-exp-002-ab96a68 evidence_file:=/data/work/so101-debug-so101-demo-py-fusion-SyIBjl/exp-fusion-002/result.json
owned_processes_before_launch: NONE
preserved_processes: tmux sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui; pre-existing ros2 daemons
abort_criteria:
  - any session, epoch, policy, installed-prefix, or bundle mismatch
  - unavailable controller, MoveIt, scene, observer, reset/pause, or evidence service
  - any phase nonzero exit, missing/invalid evidence, safety boundary, or physical outcome failure
  - any unowned process selected for cleanup
cleanup_scope: only the launch process group created for EXP-FUSION-002; bounded launch shutdown, then exact owned-PID audit
expected: one complete nine-phase success with lossless transport evidence on the qualified NVMe volume, valid installed evidence manifest, and no owned orphan
```

## Checkpoint CP-FUSION-010 — EXP-FUSION-002 valid unified execute

```yaml
checkpoint_id: CP-FUSION-010
recorded_at: 2026-08-13T03:20:00+08:00
terminal_experiment: EXP-FUSION-002
status: VALID_SUCCESS_NONCOUNTING
source_commit: ab96a689f7c7db8c761d4bfb54b284ed3e1202ed
installed_prefix: /data/work/ws_moveit/.worktrees/so101-demo-py-fusion/install/fusion-t11-live/so101_demo_py
policy_sha256: aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356
bundle_sha256: d48293fde8a37f9d8f3450564c297506091588f6aa92d72deaf40bb162197978
simulation_session_id: fusion-exp-002-ab96a68
reset_epoch: 0
completed_phases: [staged_approach, contact_hold, micro_lift, policy_lift_waypoint1, remaining_lift, transport, descend, place_alignment, release_retreat]
phase_exit_codes: ALL_ZERO
terminal_status: DONE
transport_evidence:
  status: COMPLETE
  outcome_class: PHYSICAL_TRANSPORT_SUCCESS
  chunk_count: 742
  chunk_sequence_range: [5075, 5816]
  physics_step_range: [25378, 29087]
  independent_sequence_and_step_continuity_check: PASS
physical_outcome:
  release_retreat_status: RELEASE_RETREAT_FINAL_PLACEMENT_PROVED
  final_cup_position_world_m: [-0.08016651017027784, -0.24779766303586345, 0.16538930960565074]
  final_cup_linear_velocity_world_m_s: [3.5043346637442913e-19, 5.755666239085543e-19, 2.9274850782088535e-18]
  final_left_contact_count: 0
  final_right_contact_count: 0
  final_table_contact: true
artifacts_sha256:
  live_runtime_manifest: e793b6f6f75060850ef9c5d63727b420e9b2cc730d7994c24d18812ba941e18e
  transport_result: a0e267d88ba7ef15d59d616aaa4f8f4624f2ff47b23e5498cbe635ccddb60db9
  raw_run_index: 7db96e86e0ff9ddd26ba024907c9c12140e7fd609823245c70b2ccc7b08425fd
  dynamic_summary: b7df4b35234a10c79c701744ee2caf2b1164fe8d4badd5f9ac7092247fe64ba5
  release_retreat: 38d1bbc0c03b21c7307ac1d70242d320c81511f51f34706945dfb8ce449a0314
  launch_log: bf974d6558b332ecf06db10010bed68cf6ead79a011cffcf45371f2bc928561b
cleanup:
  launcher_exit_code: 0
  ordered_move_group_shutdown_marker: true
  owned_processes_after_probe: NONE
  preserved_sessions_unchanged: [MNT-Q-RESET-EXP136-140, codex, codex-cua, so101-mujoco-gui]
confirmed_conclusion: The unified installed MuJoCo graph preserves the qualified nine-phase behavior. EXP-FUSION-001 was a storage-volume evidence failure, not a fusion behavior regression.
plan_deviation: High-rate durable trace evidence must use /data NVMe despite the plan's illustrative /tmp paths; task metadata and ordinary logs remain under the task-specific debug roots.
next_command: Start Task 12 with RED Gazebo world/lifecycle adapter contracts.
```

## Checkpoint CP-FUSION-011

```yaml
checkpoint_id: CP-FUSION-011
last_valid_experiment: EXP-FUSION-002 valid unified MuJoCo execute
current_hypothesis: The unified Gazebo launch can now run a normal execute and classify its first real policy boundary without pre-rejection.
working_tree_status: HEAD 55cb1d05ab84359f268ff9e7b1a7310a326b6e2c; Task 12 Gazebo adapters, capability reporting, tests, and this checkpoint are intentionally dirty before the scoped Task 12 commit.
owned_processes: NONE
preserved_processes: unchanged tmux sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui; pre-existing ros2 daemons only.
confirmed_conclusions:
  - Gazebo observations convert to neutral immutable WorldEvidence while retaining contact_depth_m, contact force/collision identity, independent pose/contact receipt sequences, world stats, GZ partition, and bridge identity.
  - Gazebo reset succeeds only after the observer reports the same session, an incremented epoch, and simulation step zero; transport acknowledgement alone is rejected.
  - Gazebo readiness requires world, controllers, and bridge; pause is explicitly PAUSE_NOT_SUPPORTED and no lossless MuJoCo trace is claimed.
  - Gazebo capabilities pass the base execute profile while failing the optional lossless trace capability honestly.
  - Focused adapter/port tests pass 8/8; composition/capability tests pass 5/5; the complete unified suite passes 63/63.
  - Installed Gazebo dry-run logs base_execute_capabilities=accepted and lossless_physics_step_trace=false, then completes the exact 19-transition trace.
  - The frozen MuJoCo policy remains aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356.
open_risks:
  - Gazebo execute graph and common result manifest are not registered yet; Task 13 must launch the real simulator stack and produce a non-INVALID result.
  - The legacy Gazebo workflow still owns runtime code until Task 14 replaces both old packages with audited forwarders.
next_command: Write Task 13 RED result-classification tests, register the unified Gazebo execute graph, then pre-register one bounded installed execute.
evidence:
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task12-unified-tests.log sha256=3d1115301a16d5f19f1ca224f7795d81dd6c5b0060fef2b2bc56413ebc13452d
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task12-build.log sha256=38e729dcf9f3e0ade5b8ff1b95e0acf10211c151b9a79c2b3a75a838d5641203
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task12-gazebo-dry-run.log sha256=2e007620cf557b5804917555966030101a25a0d9a10f033a0ded43dd46fbdb43
  - log/fusion-t12/latest_build
```
