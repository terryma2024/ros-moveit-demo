# SO-101 macOS service campaign closure implementation ledger

Single writer for this task. Dispatch `2208b154-6e9f-4ae1-a448-1fa0101df9b1`. This ledger records
facts for audit; it does not itself authorize measurement, promotion, publication, process
termination, or evidence deletion.

```yaml
task_id: so101-macos-service-campaign-closure
goal: close service-driven macOS W2, W1 and single-point retry with lightweight StartGuard protection
success_contract: design section 16, with candidate and production evidence kept separate
executor: Gate A Codex dispatch a50dcb6c-1eba-43d5-a2ea-2725a18e3a27 inline on mac-mini; user-authorized control repair resumed after CP-MSC-A1 without dst
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: 6d5069026fbd322076f58d0d4b9504891abeb861
current_commit: e4cf6dcf003f09e755dc7d609a5e39af01c439a3 before the final CP-MSC-A1 ledger edit
upstream: origin/codex/so101-unified-webapp (ahead 47 before the final ledger commit; no push authorized)
evidence_root: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
dispatch_receipt: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1/dispatch.receipt
dispatch_receipt_sha256: bea49ba76cf9d131529ca0b72d82bf8c9c6350d9eebc69fdefbe8ad19bc34b51
handoff_sha256: 4e672949dba8b72e18ed85ae6ef103063c1ce537b974e735defd492a2bcfede9
design: docs/superpowers/specs/2026-09-21-so101-macos-service-campaign-closure-design.md
design_sha256: 0a5f5e0d8006016fb778d186f7029247b7fe828f0e1efaea34e4e96b00480015
plan: docs/superpowers/plans/2026-09-21-so101-macos-service-campaign-closure-implementation.md
plan_sha256: 8fdce5b60eb1218726ab9eedd4fdf84da68e233e20f1f0ddadc00c4ba3f41538
execution_host: Terry-Mac-mini.local (macOS, arm64, user matianyi)
run_root: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
test_python: /Users/matianyi/ros2_jazzy/.venv/bin/python (Python 3.11.15, pytest 8.4.2, pydantic 2.13.4)
test_python_declared_by_plan: python3 (resolves to /opt/homebrew/bin/python3, Python 3.14.6, no pytest/pydantic; see D-1)
ros_workspace: /Users/matianyi/ros2_jazzy (macOS source build; no /opt/ros/jazzy on this host)
gate_recorder: src/so101_teleop/test/e2e/record_gate.py
gate_policy: <RUN_ROOT>/operator/gate-policy.json
gate_policy_sha256: 374439d0bbf02f74a428cfa444ab4e78c965e06063dd3ef32e5ee0c759f1b9fa
gate_env: <RUN_ROOT>/operator/gate-env.sh
gate_env_sha256: 55cc16fc22210fd144f600b1ab3c2b1365ecfb3e4ba01438b4d48085894d28d9
confirmed_conclusions:
  - Minimal controller-manager path reaches CONTROLLER_MANAGER_SERVICES_READY and answers a direct list_controllers call (EXP-MSC-001E)
  - Task-owned MuJoCo RobotSystem path loads the plugin, services the main-thread UI task and publishes a callable controller-manager service about 5.1 s after hardware init (EXP-MSC-002B)
  - The full macOS task station reaches READY with the task-owned closure: 3 controllers active, 3 MoveIt services, 3 actions (EXP-MSC-003B)
  - An incomplete dynamic-library closure reproduces the campaign symptom exactly (EXP-MSC-002)
disproven_routes:
  - Controller service registration requires the aggregate MoveIt graph first (EXP-MSC-001E)
  - The shipped macOS UI dispatcher deadlocks controller construction (EXP-MSC-002B, EXP-MSC-003B)
open_hypotheses:
  - Product C++ root cause for the campaign's STATION_NOT_READY stays UNCONFIRMED (see the
    correction in CP-MSC-CORR-1: the earlier "campaign environment loader-path defect"
    inference is retracted)
  - Mixed-provenance dylib resolution through the project's dylib farm can bind
    mujoco_ros2_control artifacts to the foreign fork prefix; whether that is what the
    campaign loaded is not yet measured
  - A manifest-bound filtered ROS dylib farm can satisfy the host ROS dependencies while
    preserving the exact MuJoCo vendor boundary as the sole N/P semantic delta
latest_checkpoint: CP-MSC-A1-REPAIR-CHECKPOINT
next_experiment: NONE
```

## CP-MSC-A1-FIX-TAKEOVER: user-authorized invalid-control repair

```yaml
checkpoint_id: CP-MSC-A1-FIX-TAKEOVER
recorded_at: 2026-09-21T13:57:08+0800
authorization: >-
  The user explicitly authorized code changes for the two unresolved dylib boundaries, requested
  a design based on the macOS Apple Silicon guide, approved that design, and then required Codex
  to execute it directly without dst.
scope: repair Gate A N/P control construction and ros2 interpreter boundaries only; do not start Task 2
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
source_commit: ab3efeb23b4307e8d2a373e0dde332e38726925e
submodule_commit: e4c0241aee52a40727681bd5872c09bf814e941a
working_tree_status_at_takeover: clean
evidence_root: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
repair_run_root: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1/gate-a-resolution/a50dcb6c-1eba-43d5-a2ea-2725a18e3a27/fix-dylib-baseline
preserved_processes:
  - tmux session dst-so101-macos-closure (paused and untouched)
  - legacy static_transform_publisher processes 1541 and 1542 (foreign and untouched)
owned_processes: NONE
model_tool_deviation: >-
  Repository defaults request GPT-5.6 Sol / High and dst for plan execution. This session cannot
  verify the model tier, and the user explicitly prohibited dst and directed Codex to execute the
  approved repair itself.
next_experiment: EXP-MSC-A1-002
```

```yaml
experiment_id: EXP-MSC-A1-002
status: COMPLETE_WITH_STRICT_GATE_BLOCKED
prior_experiment: EXP-MSC-A1-001
hypothesis: >-
  A task-owned filtered view of the canonical macOS ROS dylib farm will resolve
  libhardware_interface.dylib and librosidl_typesupport_c.dylib without exposing the MuJoCo vendor
  library to N, while invoking ros2 through the frozen current sys.executable will preserve that
  environment across the macOS script boundary.
prediction: >-
  Unit contracts first fail for the absent filtered-farm and explicit-interpreter behavior, then
  pass after the minimal implementation; a rebuilt N/P pair reaches the intended MuJoCo boundary
  with N using only the filtered ROS farm and P adding only the manifest vendor directory.
single_variable: P adds only the manifest-bound MuJoCo vendor directory after the identical filtered ROS farm
lifecycle: ISOLATED_STACK
preconditions:
  - worktree and submodule match the takeover identities
  - the canonical dylib farm current link resolves to one fixed run for manifest construction
  - the filtered view excludes every basename supplied by the frozen task closure and vendor directory
  - no task-owned station process is running before live validation
success_criteria:
  - RED tests fail for missing filtered-farm and explicit-interpreter behavior
  - GREEN targeted and package tests pass with nonzero collection
  - N and P semantic validation proves the exact one-path vendor delta
  - direct probe and station bootstrap both resolve the two previously missing ROS dylibs
failure_criteria:
  - either ROS dylib remains unresolved with a valid filtered-farm binding
  - the explicit interpreter still loses the frozen DYLD environment
invalid_criteria:
  - farm current target changes during construction or validation
  - filtered farm contains any frozen closure/vendor basename
  - test collection fails before the intended assertion boundary
provenance:
  source_commit: ab3efeb23b4307e8d2a373e0dde332e38726925e
  submodule_commit: e4c0241aee52a40727681bd5872c09bf814e941a
  install_overlay: PENDING
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python
  ros_domain_id: PENDING
  gz_partition: NOT_APPLICABLE_MUJOCO
commands:
  - command: targeted RED tests for filtered farm and explicit ros2 interpreter contracts
    exit_code: 1 (valid assertion RED: 5 failed, 14 passed)
  - command: related Gate A suite after implementation
    exit_code: 0 (92 passed, 2 pre-existing Lark warnings)
  - command: full ordinary so101_demo_py test directory on macOS
    exit_code: 1 (environment-invalid for this experiment: 3363 passed, 233 failed, 8 skipped)
observed:
  - The first attempted RED exited 4 because launch_testing collected an unrelated test and hit the known stale FreeJointState underlay; it did not reach the intended assertion and is INVALID evidence.
  - With third-party pytest autoload disabled, the intended RED reached the new APIs and failed with 5 expected failures while 14 existing tests passed.
  - The related Gate A suite passed all 92 tests after the implementation.
  - The full ordinary test directory collected and ran 3604 tests; its 233 failures were outside the changed files and were dominated by Linux-only /data/work fixture paths on this macOS host, plus one existing Python-3.12 literal assertion. No modified Gate A test failed.
  - Correction: the ledger status transition from PLANNED to RUNNING was recorded after the RED/GREEN commands instead of immediately before them; command logs and immutable JUnit files preserve the actual order.
  - The valid N/P pair used one copied closure and one filtered ROS dylib baseline. N stopped on the exact manifest vendor dependency before ROS plugin instance initialization; P added only the vendor directory and passed the full station.
  - The reducer returned CONFIRMED_RPATH / EXCLUDED_BEFORE_ROS_PLUGIN_INSTANCE_INIT. The valid control evidence is control-attempt-006; its manifest SHA-256 is a943efb6593ec96aa870c148db02775e853af3dd53152138f79f252916f245d7.
  - The Apple install rpath fix was committed in submodule 6591771de32c4d2e66bcb5076b3a851cfe6a9833 and parent e4cf6dcf003f09e755dc7d609a5e39af01c439a3.
  - The rebuilt F closure froze with install inventory 43bd67f15b8b13144569e2ba00cec446fcfeed978cdd6a6d61142a66e36b9f5c. Its corrected manifest file SHA-256 is d7591a987338b328f0b083a9d5438d37e05c5d3ff3adaa089ab51e060918973a; the canonical manifest hash recorded by every station report is 8d2c3e183b1e208d5bc7f38b00195cc90a06c0daaf239c8d59eea3051204c198.
  - F direct dlopen and the full station passed when F retained the manifest-bound ROS dylib baseline but omitted the vendor directory from DYLD_LIBRARY_PATH. The controller process loaded the manifest plugin and vendor bytes, reached READY, and shut down with zero process or IPC residue.
  - Five fresh FULL_RESTART runs passed consecutively in full-restart-batch-002-round-1 through -5 on ROS domains 203 through 207. Every run recorded six phase markers, three active controllers, three MoveIt services, three actions, stable controller identity, matching plugin/vendor path and SHA, and zero residue.
  - A literal no-DYLD probe, with every DYLD_* variable removed, still fails on @rpath/libhardware_interface.dylib. The original plan's strict no-DYLD completion condition is therefore not met by this repair.
  - The final related gate passed 142 tests in 9.21 seconds. It includes the Linux/macOS path-adaptive tests requested by the user.
inferred:
  - The MuJoCo vendor defect is fixed by the new relative install rpath. Host ROS dylibs remain an external macOS runtime dependency and still require the filtered task-owned baseline unless they are copied into a future self-contained closure.
conclusion: >-
  CONFIRMED_RPATH and CURRENT_CONTROLLER_PATH_OPERATIONAL under the filtered ROS dylib baseline;
  the strict all-DYLD-cleared Gate A contract remains blocked by @rpath/libhardware_interface.dylib.
evidence:
  - /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1/gate-a-resolution/a50dcb6c-1eba-43d5-a2ea-2725a18e3a27/fix-dylib-baseline
decision: stop at CP-MSC-A1, release writer, and do not start Task 2
next_experiment: NONE
```

## CP-MSC-A1-REPAIR-CHECKPOINT: current product passes with the ROS baseline; strict no-DYLD remains blocked

This entry supersedes the earlier invalid-control result for the repaired N/P construction. It
does not rewrite the earlier `CP-MSC-A1` or legacy `CP-MSC-A=UNCONFIRMED` text.

```yaml
checkpoint_id: CP-MSC-A1
recorded_at: 2026-09-21T16:12:36+0800
dispatch_id: a50dcb6c-1eba-43d5-a2ea-2725a18e3a27
experiment: EXP-MSC-A1-002
legacy_attribution: LEGACY_PROVENANCE_UNRECOVERABLE
legacy_checkpoint: CP-MSC-A=UNCONFIRMED (preserved verbatim below)
current_boundary_verdict: CONFIRMED_RPATH
np_controller_verdict: EXCLUDED_BEFORE_ROS_PLUGIN_INSTANCE_INIT
operational_controller_verdict: CURRENT_CONTROLLER_PATH_OPERATIONAL
negative_class: MISSING_VENDOR_BEFORE_ROS_PLUGIN_INSTANCE_INIT
positive_class: PASS
amended_ros_baseline_gate: PASS_5_OF_5
strict_no_dyld_gate: BLOCKED
gate_a_status: STRICT_CURRENT_PRODUCT_GATE_NOT_PASSED
strict_blocker: '@rpath/libhardware_interface.dylib is absent from the copied F closure when all DYLD_* variables are cleared'
control_manifest_sha256: a943efb6593ec96aa870c148db02775e853af3dd53152138f79f252916f245d7
f_manifest_file_sha256: d7591a987338b328f0b083a9d5438d37e05c5d3ff3adaa089ab51e060918973a
f_manifest_canonical_sha256: 8d2c3e183b1e208d5bc7f38b00195cc90a06c0daaf239c8d59eea3051204c198
f_install_inventory_sha256: 43bd67f15b8b13144569e2ba00cec446fcfeed978cdd6a6d61142a66e36b9f5c
source_commit: e4cf6dcf003f09e755dc7d609a5e39af01c439a3
submodule_commit: 6591771de32c4d2e66bcb5076b3a851cfe6a9833
code_commits:
  - a92b6c94ee341c05f635f84d29b68c857d0fca65 fix(so101): preserve macOS ROS dylib baseline
  - a9f4de3ef0ecbe06f45facdccd08ac2adbd5ca0f fix(so101): make macOS controls host portable
  - afaa91310447baac74a72e28d0dd7eb766456621 fix(so101): bind copied controller libraries
  - 630170ddd0ac6a2f72cddda485e303ff94637241 fix(so101): execute installed readiness probe
  - 3f3a0d1b565373f9cc66143b6cfc4423042a6f51 fix(so101): tolerate inaccessible vmmap entries
  - 6591771de32c4d2e66bcb5076b3a851cfe6a9833 fix(mujoco): close macOS vendor install rpath
  - e4cf6dcf003f09e755dc7d609a5e39af01c439a3 fix(so101): attest relocatable macOS station closure
five_consecutive_full_restart_runs:
  - full-restart-batch-002-round-1: PASS, ROS_DOMAIN_ID=203
  - full-restart-batch-002-round-2: PASS, ROS_DOMAIN_ID=204
  - full-restart-batch-002-round-3: PASS, ROS_DOMAIN_ID=205
  - full-restart-batch-002-round-4: PASS, ROS_DOMAIN_ID=206
  - full-restart-batch-002-round-5: PASS, ROS_DOMAIN_ID=207
test_evidence:
  - tests/green/path-portability-targeted: 47 passed
  - tests/green/final-related-006: 142 passed in 9.21 seconds, exit 0
cleanup_complete: true
owned_processes: NONE - all recorded station descendants stopped; final task-owned process scan empty
task_owned_ipc_residue: NONE
task_2_started: false
writer_release: effective after this checkpoint ledger commit and writer-release evidence marker
evidence_root: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
retained_runs:
  - gate-a-resolution/a50dcb6c-1eba-43d5-a2ea-2725a18e3a27/fix-dylib-baseline/control-attempt-006
  - gate-a-resolution/a50dcb6c-1eba-43d5-a2ea-2725a18e3a27/fix-dylib-baseline/fixed
  - gate-a-resolution/a50dcb6c-1eba-43d5-a2ea-2725a18e3a27/fix-dylib-baseline/tests
archived_runs: NONE
deletion_candidates:
  - failed and invalid control/manifest/attestation attempt directories under fix-dylib-baseline
  - fixed/vendor-workspace/build, fixed/mujoco-build*, fixed/station-build*, and fixed/teleop-build*
  - all per-invocation tmp directories under fix-dylib-baseline/tests and fixed/full-restart-*
deletions_performed: NONE
next_command: NONE - writer released; stop Task 1 and do not start Task 2
```

## CP-MSC-A1-TAKEOVER: current-product Gate A writer handoff

```yaml
checkpoint_id: CP-MSC-A1-TAKEOVER
recorded_at: 2026-09-21T12:31:32+0800
dispatch_id: a50dcb6c-1eba-43d5-a2ea-2725a18e3a27
previous_writer: dst-so101-macos-closure (paused and preserved; no capture, message, signal, or service action by this dispatch)
current_writer: Gate A Codex dispatch a50dcb6c-1eba-43d5-a2ea-2725a18e3a27
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
source_commit: 3def7ac4f0c22e6e03cc7e72d6224ca3d7bd0975
submodule_commit: e4c0241aee52a40727681bd5872c09bf814e941a
working_tree_status_at_takeover: clean
legacy_ledger_sha256: fa25d1fc9651a05ddbfe27d273a457a97f61ce5b109e71b3c19c8cf1632565a4
task_root: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
gate_a_run_root: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1/gate-a-resolution/a50dcb6c-1eba-43d5-a2ea-2725a18e3a27
legacy_attribution: LEGACY_PROVENANCE_UNRECOVERABLE
legacy_checkpoint: CP-MSC-A=UNCONFIRMED (preserved verbatim below)
model_tool_deviation: >-
  Repository defaults route plan execution through dst, but the reviewed Task 1 plan and this
  dispatch explicitly assign Task 1 inline to a separate Codex session while requiring the dst
  session to remain paused. The narrower Task 1 dispatch controls this handoff.
preserved_processes:
  - dst-so101-macos-closure process tree (paused writer; untouched)
  - pid 62670 so101_teleop.expert_validation.main (foreign service; untouched)
owned_processes: NONE
next_experiment: EXP-MSC-A1-001
```

```yaml
experiment_id: EXP-MSC-A1-001
status: INVALID
prior_experiment: EXP-MSC-003B
hypothesis: >-
  The frozen current product has an install-rpath-only MuJoCo closure gap: N without DYLD fails
  for the exact manifest vendor before ROS plugin instance initialization, while P with only the
  manifest vendor directory added to DYLD_LIBRARY_PATH passes the full task station.
prediction: >-
  The deterministic reducer returns CONFIRMED_RPATH only for a valid N missing-vendor observation
  and a valid P PASS observation; if N and P both pass it returns CURRENT_CLOSURE_ALREADY_VALID.
single_variable: P adds only the manifest-bound MuJoCo vendor directory to DYLD_LIBRARY_PATH
lifecycle: ISOLATED_STACK
preconditions:
  - worktree and submodule match the recorded takeover identities
  - one frozen merged closure and one GateAControlSetManifest are shared by N and P
  - each run uses a fresh valid ROS_DOMAIN_ID, session, run binding, ROS home/log and temp directory
  - no task-owned station process is running before either control
success_criteria:
  - N and P each classify under the reviewed required/allowed-absent table
  - the reducer chooses exactly one plan-authorized route
  - each control has stable controller process identity and zero task-owned cleanup residue
failure_criteria:
  - CURRENT_NON_RPATH_FAILURE from a valid classified control pair
invalid_criteria:
  - manifest, semantic, binding, collector, process identity, timeout, cleanup or substitution invariant fails
provenance:
  source_commit: 62a7431690bef974718e55dbcfb54a36ffc6af6b
  submodule_commit: e4c0241aee52a40727681bd5872c09bf814e941a
  install_overlay: gate-a-resolution/a50dcb6c-1eba-43d5-a2ea-2725a18e3a27/control-set/closure
  runtime_executable: control-set/closure/lib/so101_demo_py/so101_diagnose_macos_station
  ros_domain_id: N=83; P=175
  gz_partition: NOT_APPLICABLE_MUJOCO
  manifest_sha256: 2765ab9f236793ec9c67ec84bfc8a06b8fa4f277ff442437b64cd63b2f36567c
commands:
  - command: build and freeze task-owned N/P merged closure per reviewed Task 1 Step 3
    exit_code: 0 after preserving a Python 3.14 selection failure and sandboxed lodepng fetch failure
  - command: run N direct dlopen and FULL_TASK_STATION
    exit_code: direct=1; station=1
  - command: run P direct dlopen and FULL_TASK_STATION with the single authorized DYLD variable
    exit_code: direct=1; station=1
observed:
  - The copied closure and exact installer alias froze successfully; all other external Ament hook symlinks were dereferenced into the copied closure while the original build tree was retained.
  - N and P direct dlopen both failed first on @rpath/libhardware_interface.dylib, before the MuJoCo vendor edge could be isolated.
  - N and P station launch both failed before a controller runtime existed because ros2/rclpy could not resolve @rpath/librosidl_typesupport_c.dylib after the required DYLD sanitization.
  - Both reports classified INVALID with STATION_CONTROLLER_PROCESS_MISSING; cleanup was complete, residue_pids and IPC residue were empty.
  - The deterministic reducer returned INVALID_CONTROL / NOT_EXCLUDED; decision SHA-256 is 9a6395b645150fbb19d040ee1ec7ff5da876e0a3412cc15f7a6c95ab8e31232f.
inferred:
  - The reviewed N/P environment does not provide a loadable ROS host-underlay closure, so this control pair cannot distinguish a MuJoCo install-rpath defect from broader missing ROS dylib search paths.
conclusion: INVALID_CONTROL; no current-product root-cause claim and no RPATH product edit are authorized
evidence:
  - /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1/gate-a-resolution/a50dcb6c-1eba-43d5-a2ea-2725a18e3a27
decision: stop Task 1 at CP-MSC-A1 for independent review
next_experiment: NONE - Task 2 and five-run readiness remain forbidden
```

## CP-MSC-A1: current-product Gate A stopped on invalid controls

```yaml
checkpoint_id: CP-MSC-A1
recorded_at: 2026-09-21T13:31:54+0800
dispatch_id: a50dcb6c-1eba-43d5-a2ea-2725a18e3a27
code_commits:
  - 5dcf028b0be8f7ac5c10d9ef316487e066cede75 test(so101): freeze macOS Gate A controls
  - 62a7431690bef974718e55dbcfb54a36ffc6af6b fix(so101): accept precreated Gate A run directories
source_commit: 62a7431690bef974718e55dbcfb54a36ffc6af6b
submodule_commit: e4c0241aee52a40727681bd5872c09bf814e941a
legacy_attribution: LEGACY_PROVENANCE_UNRECOVERABLE
legacy_checkpoint: CP-MSC-A=UNCONFIRMED (preserved verbatim below)
experiment: EXP-MSC-A1-001
current_boundary_verdict: INVALID_CONTROL
controller_verdict: NOT_EXCLUDED
negative_class: INVALID
positive_class: INVALID
reason: one or both controls violate required invariants
first_unresolved_direct_dependency: '@rpath/libhardware_interface.dylib'
first_unresolved_station_dependency: '@rpath/librosidl_typesupport_c.dylib'
invalid_reason: STATION_CONTROLLER_PROCESS_MISSING
cleanup_complete: true
owned_processes: NONE - fresh filtered host scan has zero matches
task_owned_ipc_residue: NONE - fresh socket scan is empty
targeted_test_gate: 80 passed, 2 pre-existing Lark deprecation warnings, exit 0
git_diff_check: exit 0
preserved_processes:
  - pid 62670 so101_teleop.expert_validation.main (foreign service; alive and untouched)
  - tmux session dst-so101-macos-closure (present, paused, and untouched)
rpath_route_started: false
five_consecutive_full_restart_runs: NOT_RUN
task_2_started: false
writer_release: effective after this checkpoint ledger commit and writer-release evidence marker
evidence_root: /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
retained_runs:
  - gate-a-resolution/a50dcb6c-1eba-43d5-a2ea-2725a18e3a27 (all control, build, test, invalid-attempt, and cleanup evidence)
archived_runs: NONE
deletion_candidates:
  - control-set/vendor-workspace/build
  - control-set/mujoco-build
  - control-set/station-build
  - control-set/closure-build-staging
  - per-invocation tests/red/*/tmp and tests/green/*/tmp trees
deletions_performed: NONE
next_command: NONE - release writer and wait for independent review; do not start Task 2
```

## CP-MSC-000: registration, frozen base and baseline (Task 0 Steps 1-3)

### Required first actions

- Receipt written first, exactly `2208b154-6e9f-4ae1-a448-1fa0101df9b1` + newline, file and
  containing directory fsynced, before any other task action (file mode 0644, 37 bytes,
  sha256 `bea49ba7...`).
- Read: `AGENTS.md`, `.agents/skills/so101-dev/SKILL.md` with references
  (`ai-station-access.md`, `so101-system-map.md`, `debug-evidence.md`, `test-and-acceptance.md`,
  `experiment-ledger.md`), the design and plan above, and both predecessor document pairs:
  `2026-09-18-so101-parallel-unbounded-queue-resource-budget` design
  (`5e085f98e9926591fbefd3d6e16c16b33bfc9956df9221c46f383b310553657b`) / plan
  (`cd1b606fd8a40d7bb6e576f6f59a6ef5abcb45a8bee7e2a669c7b7a40bcfc8789`), and
  `2026-09-19-so101-macos-mps-private-ipc` design
  (`480da6dcdfea1da988f9f4e706c8340dbb6d7283200c27bb723859119145db1b`) / plan
  (`d018aae3bae372abd9a58a6e0ec7d7fef1f09dbef67860680690614bc31bb875`).

### Checkout ownership read-back (fail-closed checks passed)

- `hostname` = `Terry-Mac-mini.local`; `pwd` = the target worktree above. This dispatch runs
  directly on mac-mini; no SSH to mac-mini or ai-station was issued.
- Branch `codex/so101-unified-webapp`; HEAD `90385e3fb4aa748788c5d8a4b4551ee307db4987` — exactly
  the required starting HEAD. Upstream `origin/codex/so101-unified-webapp`, ahead 23.
- `git status --short` empty; `git diff --submodule=log` empty; submodule
  `third_party/mujoco_ros2_control` at `e4c0241aee52a40727681bd5872c09bf814e941a`, clean.
- Raw read-backs: `<RUN_ROOT>/baseline/git-baseline.txt`,
  `<RUN_ROOT>/baseline/process-inventory.txt`, `<RUN_ROOT>/baseline/evidence-root-identity.txt`.

### Writer and process ownership

- The only processes referencing this worktree are this dispatch's own TUI chain
  (pid 64248 dst -> 64249 dsh-tui -> 64251 dsh, tmux session `dst-so101-macos-closure`, created
  2026-09-21 10:24:48). No second writer overlaps the worktree.
- Preserved, not touched: tmux `dst` (pid 44357 shell), tmux `dst-so101-macos-mps-w2` (pane pid
  10776, TUI of dispatch 6954bbb9 in a different worktree, state `blocked`), tmux
  `so101-teleop-w2-e2e` with long-running pid 62670
  (`so101_teleop.expert_validation.main`, started ~24 h earlier, belongs to another task),
  and legacy TF publishers pid 1541/1542 (`static_transform_publisher`, ~1 day 10 h old).
- No TCP listener exists on this host (empty `lsof -nP -iTCP -sTCP:LISTEN`), so no duplicate
  service or port conflict was started or observed.

### Frozen run environment (adopted dispatch root, not a second root)

The handoff makes the dispatch directory the task's single ordinary evidence root, so Task 0 Step 2
adopted it instead of running `mktemp -d`; no second root was created. Within it:

| item | frozen value |
| --- | --- |
| `RUN_ROOT` | `/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1` (mode 0700, uid 501) |
| `TEST_PYTHON` | `/Users/matianyi/ros2_jazzy/.venv/bin/python` |
| `ROS_HOME` | `<RUN_ROOT>/ros_home` |
| `ROS_LOG_DIR` | `<RUN_ROOT>/ros_log` |
| `TMPDIR`/`TMP`/`TEMP` | `<RUN_ROOT>/tmp` (per gate invocation: `<RUN_ROOT>/gates/<uuid>/tmp`) |
| gate policy | `<RUN_ROOT>/operator/gate-policy.json`, sha256 `374439d0...` |

Proof of the frozen interpreter/tempfile pair (both assertions exit 0, recorded in
`<RUN_ROOT>/baseline/task0-step2.txt`):
`sys.executable=/Users/matianyi/ros2_jazzy/.venv/bin/python`,
`tempfile.gettempdir()=/private/tmp/so101-debug-macos-service-campaign-closure-2208b154-.../tmp`.

### Deviations (reported, not silent substitutions)

- **D-1 test interpreter.** The plan's literal `TEST_PYTHON="$(command -v python3)"` resolves on
  this host to `/opt/homebrew/bin/python3` (Python 3.14.6), which cannot import `pytest` or
  `pydantic` and therefore cannot run any gate; treating its failures as RED/GREEN would be
  invalid. The repository's own macOS test contract
  (`.agents/skills/so101-dev/references/test-and-acceptance.md`) and the predecessor dispatch on
  this exact worktree and branch both register `/Users/matianyi/ros2_jazzy/.venv/bin/python`
  (3.11.15, pytest 8.4.2, pydantic 2.13.4, `rclpy` importable after sourcing
  `~/ros2_jazzy/install/setup.bash`). That verified interpreter is frozen as `TEST_PYTHON`; the
  literal value and its failed capability probe are recorded in
  `<RUN_ROOT>/baseline/task0-step2.txt`.
- **D-2 `/data` durable root.** `/data/work/so101-evidence` does not exist on this host and
  `AGENTS.md` exempts macOS from the ai-station NVMe rule. Per plan Global Constraints this only
  blocks Stage C's high-rate sampling: before the first durable high-frequency sample the plan
  requires the durable root to be created and registered, and if it is unavailable the run must
  stop and ask for a storage decision. That decision is not required for Tasks 0-3.
- **D-3 plan literal root command.** Task 0 Step 2's `mktemp -d` invocation was superseded by the
  dispatch handoff's "adopt the already-created root, do not create a second task root" rule.
  Every other literal element of the step (directory layout, exports, interpreter/tempfile
  assertion, read-back into the ledger) was executed.

### Baseline collection (Task 0 Step 3, read-only)

- Module origins (`gates/a46b2848efa24fb8bf1d33504e1a6ccc`):
  `rclpy` from `/Users/matianyi/ros2_jazzy/install/rclpy/lib/python3.11/site-packages/rclpy/__init__.py`,
  `so101_demo` from the source shim `<RUN_ROOT>/pyshim/so101_demo/__init__.py` (the package maps
  `so101_demo -> src/` only at install time), `so101_teleop` from this worktree's source tree,
  `sys.executable=/Users/matianyi/ros2_jazzy/.venv/bin/python`.
- Frozen config bytes: `parallel_batch_v4_macos_mps_w2.yaml`
  `2f9d7a87fe57a0440cdfd139c2ac42b7af86002edfcc2ed2ef3077568dc6b06b`,
  `parallel_batch_v3.yaml` `991b5c1b4fbd0cc1f0a97bd20a5b5a4e02028634f3f4ef288ad87554b383ab70`,
  `rgbd_task_points.yaml` `75591214ba3d1dfdd2827c390c0f2ec1d61e7a8dca80d89daabb1e7840627e73`.
- Retired measurement entry still fails closed: `-m so101_demo.cli.measure_parallel_resources`
  exits 2 with `MEASUREMENT_ENTRY_RETIRED` / `authorizes_execution=false`, both bare and with
  `--authorization /nonexistent --intent QUALIFICATION`
  (`gates/4874802dd6ae449f9e2e0421ad25bf32`, `gates/762c6f5691b84947b0882d7026a79d0a`).
- Package collection counts: `src/so101_demo_py/test` collects 3517 tests with 2 pre-existing
  collection errors (`test_mujoco_reset_client.py`, `test_teleop_owner.py`: `FreeJointState`
  missing from the installed `mujoco_ros2_control_msgs` fork overlay — an underlay gap on this
  host, unrelated to this dispatch), exit 2; `src/so101_teleop/test` collects 744 tests, exit 0.
  Summary: `<RUN_ROOT>/baseline/collection-baseline.txt`.
- Targeted baseline for the files Tasks 1-2 touch: `test_task_stack.py` +
  `test_motion_stack_ready.py` = 8 passed
  (`gates/da96626319de4fa388fe604ce519a2d2`).
- RED-target absence confirmed: `so101_demo.runtime.runtime_closure` and
  `so101_demo.cli.diagnose_macos_station` do not exist yet
  (`<RUN_ROOT>/baseline/probe_task1_task2_targets.py`).

### Evidence accounting at CP-MSC-000

- Retained: dispatch receipt/handoff/pane captures, `baseline/`, `operator/`, all `gates/<uuid>/`
  records, `pytest-*/junit.xml` invocation directories.
- Archived: none. Deletion candidates: none proposed at this checkpoint (the two `/tmp` trees of
  other dispatches are not this task's evidence and are left untouched).

## CP-MSC-002: Tasks 1-2 (runtime closure and independent controller evidence)

### Task 1 - runtime closure, run binding, attestation  (commit `fea8f57c`)

Delivered `src/so101_demo_py/src/runtime/runtime_closure.py` plus the `PersistentTaskStack`
wiring (closure verified before the first spawn, attestation only after PID/birth identity and
loaded-image read-back) and `src/so101_demo_py/test/test_runtime_closure.py`.

RED: `gates/bcc93e0c8bc14af8b56392935596ec1a` + `task1-red-pre-edit.xml` - 21 tests, 21
failures, 0 errors, every failure `AssertionError: so101_demo.runtime.runtime_closure is not
implemented yet` (collection succeeded, so this is an assertion RED and not a bootstrap
failure). The test file was then changed three times for self-consistency, each change making
an assertion stricter or better targeted (forbidden root = the canonical checkout itself; the
station environment used to build the closure is the merged launch environment; the stack tests
pass `ROS_DOMAIN_ID`). A second RED run (`task1-red.xml`) recorded 4 failures / 17 passes with
the module present but `task_stack` not yet wired - exactly the stack-integration assertions -
so the remaining RED is still genuine.

GREEN: `gates/8d665e8e4b0649f582fb46d1f7f275a6` - 23 passed, exit 0
(`test_runtime_closure.py` + the unmodified `test_task_stack.py`).
Adjacent: `pyrgate test_parallel_worker_runtime.py + closure + task_stack` =
`gates/7e049300ef91458f864d2704d96c2a90`, 81 passed, exit 0. A first attempt without the ROS
overlay produced 37 failures whose only cause was `RuntimeError: ros2 executable is not
available`; that is an environment artifact, not a regression, and the ROS-sourced run is the
recorded result.

Covered by the tests: stable closure hash across fresh domain/session/evidence roots; volatile
environment keys excluded; distinct run/attestation hashes; relative, classified inventories;
unclassified installed bytes changing the install inventory; config drift; source/submodule
commit drift; missing submodule commit; environment drift; canonical checkout prefix
contamination; symlinked prefix and symlinked file; replacement race through a single fd;
loaded image outside the copied install; loaded-image byte drift; ROS-domain mismatch; empty
process identities; verify-before-spawn; attest-only-after-read-back with child reaping;
closure/run-binding pairing in the stack config.

### Task 2 - direct controller query separated from MoveIt readiness  (commit `e264d1eb`)

Delivered `src/so101_demo_py/src/cli/diagnose_macos_station.py` (closed
`MINIMAL_CONTROLLER_MANAGER` / `ROBOT_SYSTEM_CONTROLLER_MANAGER` modes, six design phases with
independent deadlines, distinct failure codes, direct observation without the MoveIt graph,
JSON report) and changed `motion_stack_ready` so controller traffic no longer waits behind the
MoveIt service/action graph while final READY still requires all three active controllers plus
the three MoveIt services and actions. `setup.py` registers the
`so101_diagnose_macos_station` console script.

RED: `gates/adfb42b8bf9046ad9b3dea54e55e7452` - 13 failed / 5 passed, exit 1; the 13 are the
new diagnostic contract plus the three new `motion_stack_ready` assertions, the 5 passes are the
untouched pre-existing readiness tests.
GREEN: `gates/25fecc1763b446e4ac907f046a45365a` - 18 passed, exit 0.
Adjacent: `gates/8ce6ec5d63e34f02bf003c80c017ad1f` - install contract + copied entrypoint +
readiness + diagnostic = 36 passed, 8 skipped, exit 0.

### Provenance found while scouting Gate A (read-only)

- `ros2 pkg prefix mujoco_ros2_control` resolves to
  `/Users/matianyi/ros2_jazzy/ws_mujoco_ros2_control_fork/install`, a foreign workspace whose
  source tree has uncommitted modifications (`M CMakeLists.txt`,
  `mujoco_system_interface.{hpp,cpp}`, `mujoco_ros2_control_node.cpp`, tests...). That prefix
  is NOT this task's provenance and must not be used as a result carrier.
- `ros2 pkg prefix so101_demo_py` resolves to
  `/Users/matianyi/ros2_jazzy/so101_isolated_ws/install/so101_demo_py` - another branch's
  install, also not this task's provenance.
- The worktree submodule `third_party/mujoco_ros2_control` (commit
  `e4c0241aee52a40727681bd5872c09bf814e941a`) contains `mujoco_ros2_control_msgs`,
  `mujoco_ros2_control_plugins` (including
  `mujoco_ros2_control_plugin_capabilities.hpp`), `mujoco_ros2_control` and test sources, so a
  task-owned overlay for the A/B has to be built from it rather than borrowed from the fork.

### Planned experiments (frozen before any stack starts)

```yaml
experiment_id: EXP-MSC-001
status: PLANNED
prior_experiment: NONE
hypothesis: The controller manager registers /controller_manager/list_controllers and answers a direct query even when no RobotSystem is loaded, so a station that never reaches readiness is not failing at service registration itself.
prediction: With MINIMAL_CONTROLLER_MANAGER the direct client observes service_visible=true and call_completed=true with an empty controller list, and no C++ or config change is needed for that path.
single_variable: NONE (first observation of the minimal path)
lifecycle: ISOLATED_STACK
preconditions:
  - no other station, controller manager or ROS graph owned by this task is running
  - fresh ROS_DOMAIN_ID, fresh session id, task-owned child process
success_criteria:
  - report shows service_visible and call_completed with ros_domain_id equal to the fresh domain
failure_criteria:
  - service_visible never becomes true within the bounded timeout
invalid_criteria:
  - another writer's controller manager or a stale ROS daemon answers instead
provenance:
  source_commit: e264d1eb (Task 2 HEAD)
  install_overlay: ros2_jazzy/install (ROS) + ws_mujoco_ros2_control_fork/install is NOT used
  runtime_executable: controller_manager/ros2_control_node from the ROS underlay
  ros_domain_id: 231
  gz_partition: so101_msc_ga_minimal
commands:
  - command: PENDING
    exit_code: PENDING
observed: []
inferred: []
conclusion: PENDING
evidence: []
decision: PENDING
next_experiment: EXP-MSC-002

experiment_id: EXP-MSC-002
status: PLANNED
prior_experiment: EXP-MSC-001
hypothesis: Changing only the controller-manager launch to the MuJoCo RobotSystem path moves the last observed structured phase, which locates the first bad boundary between service registration and hardware bring-up.
prediction: The robot-system run reaches a different (earlier) structured phase or stalls before CONTROLLER_MANAGER_SERVICES_READY, and the difference from EXP-MSC-001 is attributable to the RobotSystem path alone.
single_variable: controller-manager mode (MINIMAL -> ROBOT_SYSTEM)
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-MSC-001 completed with a valid observation
  - task-owned build of third_party/mujoco_ros2_control if the foreign fork prefix may not be used
success_criteria:
  - a structured phase/failure-code pair that differs from EXP-MSC-001
failure_criteria:
  - both runs observe exactly the same phase and code (boundary NOT distinguished)
invalid_criteria:
  - the run depends on the foreign fork install or its modified working tree
provenance:
  source_commit: e264d1eb plus the frozen submodule commit e4c0241a
  install_overlay: PENDING (task-owned submodule build under the registered root)
  runtime_executable: PENDING
  ros_domain_id: 232
  gz_partition: so101_msc_ga_robotsystem
commands:
  - command: PENDING
    exit_code: PENDING
observed: []
inferred: []
conclusion: PENDING
evidence: []
decision: PENDING
next_experiment: NONE
```

## CP-MSC-003: Gate A execution log (controller-manager A/B)

All runs below are task-owned: the child processes were started by this dispatch's runners,
recorded through the registered gate, and stopped by the same runner. No foreign process was
signalled and no shared service was started or stopped.

| run | command (recorded gate) | exit | key observation |
| --- | --- | --- | --- |
| EXP-MSC-001 | `gates/d0577436bda742f5b0acd248732ef220` | 1 | MINIMAL without any robot description: controller_manager logs `Subscribing to '/robot_description' topic` and then `Waiting for data ... to finish initialization` for the whole 25 s; `/controller_manager/list_controllers` never becomes callable |
| EXP-MSC-001B | `gates/446da084ff72414ea1d456915004ff8d` | 3 | same, with `-p robot_description:=<stub>`: the parameter is ignored and the node still waits on the topic |
| EXP-MSC-001C | `gates/6cdc68aa59a849599c89db2466006b5b` | 3 | a task-owned latched `/robot_description` publisher delivers the stub; controller_manager logs `no 'ros2_control' tag found in the URDF` and never registers services |
| EXP-MSC-001D | `gates/7fe70aa9332a4ee6afb1370fd0f7b5e3` | 1 | **INVALID**: `ROS_DOMAIN_ID=233` exceeds the RMW port range (`Calculated port number is too high. Probably the domainId is over 232`). Not counted; re-run as 001E on domain 230 |
| EXP-MSC-001E | `gates/ad8facff3e9c481f950537c3e224e98b` | 0 | MINIMAL with the station's own joint/interface set and `mock_components/GenericSystem` as the only difference: `Loaded hardware 'RobotSystem' ... Initialize ... Activating ... Resource Manager has been successfully initialized. Starting Controller Manager services...`; direct call completes, phase `CONTROLLER_MANAGER_SERVICES_READY`, controllers `{}` |
| EXP-MSC-002 | `gates/8746ac496a6440ff9845facafb03ba6a` | 0 | first robot-system attempt from the task-owned overlay: the plugin could not be dlopen'ed (`Library not loaded: @rpath/libmujoco.3.4.0.dylib`), so controller_manager kept waiting and never registered services - the *same* downstream symptom as the campaign, caused by an incomplete dynamic-library closure of the build, not by controller construction |
| EXP-MSC-002B | `gates/07182fcc2b3046bdad8efd5eb309d67a` | 0 | same command with `DYLD_LIBRARY_PATH` including the MuJoCo vendor lib dir: `Loaded hardware 'RobotSystem' from plugin 'mujoco_ros2_control/MujocoSystemInterface'`, `Submitting MuJoCo UI task to the process main thread`, `Running MuJoCo UI task on the process main thread`, then ~5.1 s later `Resource Manager has been successfully initialized. Starting Controller Manager services...`; direct call completes, phase `CONTROLLER_MANAGER_SERVICES_READY`, controllers `{}` (no spawner was run in this diagnostic) |

### Provenance of the Gate A runs

- `EXP-MSC-001*`: `controller_manager` from `/Users/matianyi/ros2_jazzy/extra_ws/install`
  (host underlay), no project install involved.
- `EXP-MSC-002*`: `ros2 pkg prefix mujoco_ros2_control` =
  `<RUN_ROOT>/gate-a/ga-install2/mujoco_ros2_control`, i.e. a **task-owned colcon build of the
  worktree submodule** `third_party/mujoco_ros2_control` at `e4c0241a`, built into
  `<RUN_ROOT>/gate-a/ga-build2` / `ga-install2` by `gate-a/build_submodule.sh`
  (`COLCON_BUILD_RC=0`, 4 packages: msgs 17.7 s, mujoco_3d_lidar 3.7 s, plugins 15.3 s,
  mujoco_ros2_control 26.5 s). The foreign fork install
  `/Users/matianyi/ros2_jazzy/ws_mujoco_ros2_control_fork/install` was **not** used.
- Fresh `ROS_DOMAIN_ID` per run (231 / 231 / 231 / invalid 233 / 230 / 229 / 228) and a
  task-local `ROS_HOME`/`ROS_LOG_DIR`/`TMPDIR` per experiment.
- The robot description in EXP-MSC-001E and EXP-MSC-002B is rendered by the station's own
  renderer from `assets/mujoco/so101.urdf`; 001E differs from 002B in the hardware plugin
  block only, and the runner prints
  `same_bytes_except_hardware=True` for that comparison.

### Experiment states after Gate A

- `EXP-MSC-001` -> **VALID** (observation of the deliberate wait; batch continues as 001B/001C).
- `EXP-MSC-001D` -> **INVALID** (invalid ROS domain; not counted).
- `EXP-MSC-001E` -> **VALID** (minimal boundary reached).
- `EXP-MSC-002` -> **VALID** but diagnosed as an incomplete dylib closure of the build
  (`@rpath/libmujoco.3.4.0.dylib`), not a controller/hardware startup defect; superseded by 002B.
- `EXP-MSC-002B` -> **VALID** (robot-system boundary reached in ~5.1 s with the task-owned
  overlay).

### Conclusion at this point (Gate A)

`OBSERVED`: with the task-owned overlay built from the worktree submodule, the macOS
`RobotSystem` path loads the MuJoCo plugin, services the main-thread UI task through the
existing dispatcher, and controller_manager publishes a callable
`/controller_manager/list_controllers` about 5.1 s after `Initialize hardware`. The failure
described in the design ("`ros2_control_node` stops while loading `RobotSystem`, the service
never appears stably") **did not reproduce** in this closure.

`OBSERVED`: the same downstream symptom (no callable service, spawners therefore unable to
activate controllers) is produced by an incomplete dynamic-library closure of the built plugin
(EXP-MSC-002).

`INFERRED`: the campaign's `STATION_NOT_READY` is consistent with an overlay/loader-path defect
in the environment the campaign used (a foreign, locally modified fork workspace whose prefix
the project's own `.envrc.example` deliberately excludes) rather than with a controller
constructions or macOS UI-dispatch ordering defect in the allowlisted C++ files. This is stated
as an inference, not a confirmed root cause: the campaign's own overlay was not re-run because
its provenance is foreign to this dispatch.

`UNCONFIRMED`: the plan's Gate A requires a *confirmed* first bad boundary plus a RED/GREEN
regression at that boundary. No product C++ boundary was confirmed, and per the plan
("Do not edit C++ based only on timeout length or downstream `STATION_NOT_READY`") no
speculative product edit was made. CP-MSC-A therefore cannot be declared PASS in this state.

### Task 2 defect found and repaired during Gate A (commit `82b7a7d9`)

The first live diagnostic run failed with
`TypeError: replace() argument 2 must be str, not PosixPath` in
`station_robot_description`. RED with the ROS-sourced gate:
`gates/86a6c121b5064516876369fa09cec6fe` (1 failed / 10 passed, the failure being exactly that
TypeError); the same test under the plain gate first failed with
`ModuleNotFoundError: ament_index_python` (`gates/8c108966cb5d45798cb67cbac2bf605f`), which is
a runner/overlay artifact and was **not** counted as RED. GREEN:
`gates/e7c1b6983ddc448fae555ffb9e90d53d` (19 passed, exit 0).

## CP-MSC-003B: full task station with the task-owned closure reaches READY

`gates/74d6aafae26a4413bf8d60d2a4c31d6c` (exit 0). One bounded run
(`gate-a/run_station_once.sh`), fresh `ROS_DOMAIN_ID=227`, `GZ_PARTITION=so101_msc_ga_station`:

- Prefixes read back before the launch:
  `so101_demo_py` = `<RUN_ROOT>/gate-a/station-install/so101_demo_py`,
  `mujoco_ros2_control` = `<RUN_ROOT>/gate-a/ga-install2/mujoco_ros2_control`,
  `so101_mujoco_support` = `<RUN_ROOT>/gate-a/station-install/so101_mujoco_support`.
  All three are task-owned builds of this worktree; the foreign fork prefix was not sourced.
- `ros2 launch so101_demo_py so101_mujoco_task_station.launch.py headless:=false
  sensor_rendering:=true include_teleop:=false session_id:=msc-ga-003` started, and
  `ros2 run so101_demo_py motion_stack_ready --timeout-s 100` returned exit 0 with
  `{"ready": true, "phase": "READY", "failure_code": null}` and all three controllers
  `active`, all three MoveIt services and all three actions `true`
  (`experiments/EXP-MSC-003/readiness.json`).
- Launch log (retained at `experiments/EXP-MSC-003/station-launch.log`) shows the full macOS
  path working: `mujoco_macos_ui: Waiting for a MuJoCo UI task on the process main thread` ->
  `Loaded hardware 'RobotSystem' from plugin 'mujoco_ros2_control/MujocoSystemInterface'` ->
  `Submitting MuJoCo UI task to the process main thread` ->
  `Running MuJoCo UI task on the process main thread` -> `Resource Manager has been
  successfully initialized` -> `spawner_* : Configured and activated <controller>` ->
  `Successfully switched controllers!`.
- Run 003 (`gates/ea3824fd5b644dbb940cda7785cd1f41`) is **INVALID**: `setsid` and `timeout` do
  not exist on macOS, so the readiness probe never ran (`READINESS_RC=127`). Fixed by removing
  both and using an explicit bounded wait; 003B is the recorded run.
- Cleanup: the first SIGINT to the `ros2 launch` process stopped the spawners but left the
  launch process and three children alive (`LAUNCH_TREE_STILL_ALIVE=true`). They were stopped by
  the exact PIDs this run recorded (77417, 77423, 77427, then 77422, 77420, 77421) with
  SIGTERM, SIGKILL only where SIGTERM did not settle. Final scans:
  `ps -Ao pid,ppid,etime,command | grep -E "ros2_control_node|move_group|spawner|robot_state_publisher|msc-ga-003"` -> **no task-owned ROS residue**.
  Preserved and untouched: pid 1541/1542 (long-lived foreign TF publishers) and pid 62670
  (another task's `so101_teleop.expert_validation.main`).

### What this means for Gate A

- `OBSERVED`: with a task-owned closure built from this worktree (source `82b7a7d9` plus
  submodule `e4c0241a`), the macOS task station reaches full readiness - controllers active,
  MoveIt services and actions ready - on the first bounded attempt. The failure the design
  describes did **not** reproduce.
- `OBSERVED`: an incomplete dynamic-library closure of the built MuJoCo plugin reproduces the
  exact downstream symptom (controller_manager never publishes a callable service; the
  spawners then time out), see EXP-MSC-002.
- `INFERRED`: the campaign's `STATION_NOT_READY` is consistent with an overlay / loader-path
  defect in the environment the campaign was using, not with a macOS UI-dispatch ordering or
  controller-construction defect in the allowlisted C++ files.
- `UNCONFIRMED`: no product-code first bad boundary was confirmed. Per the plan no C++
  regression was written and no product edit was made; `CP-MSC-A` cannot be declared PASS and
  `Gate B` live work stays forbidden.

## CP-MSC-A checkpoint

```yaml
checkpoint_id: CP-MSC-A
last_valid_experiment: EXP-MSC-002B (robot-system boundary) and EXP-MSC-003B (station READY)
current_hypothesis: >-
  The campaign's STATION_NOT_READY came from an incomplete overlay/dylib closure in the
  environment it used, not from a defect in the allowlisted macOS controller-startup code.
  Product C++ root cause: UNCONFIRMED.
working_tree_status: >-
  clean except this ledger (to be committed together with the checkpoint);
  commits 1f50619c (ledger baseline), fea8f57c (runtime closure), e264d1eb (controller/MoveIt
  readiness separation), 82b7a7d9 (diagnostic robot-description repair)
owned_processes: NONE (all task-owned children stopped by recorded PID; final scan empty)
preserved_processes:
  - pid 1541, 1542 static_transform_publisher (pre-existing, >1 day old, untouched)
  - pid 62670 so101_teleop.expert_validation.main (another task's service, untouched)
  - tmux sessions dst, dst-so101-macos-mps-w2, so101-teleop-w2-e2e (untouched)
confirmed_conclusions:
  - Minimal controller-manager path reaches CONTROLLER_MANAGER_SERVICES_READY and answers a
    direct list_controllers call (EXP-MSC-001E)
  - Task-owned MuJoCo RobotSystem path loads the plugin, services the main-thread UI task and
    publishes a callable controller-manager service about 5.1 s after hardware init (EXP-MSC-002B)
  - The full task station reaches READY (3 controllers active, 3 MoveIt services, 3 actions)
    with the task-owned closure (EXP-MSC-003B)
  - A missing dylib closure reproduces the campaign symptom exactly (EXP-MSC-002)
disproven_routes:
  - "controller service registration needs the MoveIt graph first" (the direct client works
    without it; EXP-MSC-001E)
  - "the shipped macOS UI dispatcher deadlocks controller construction" (it appears in the
    successful runs and completes the main-thread task; EXP-MSC-002B/003B)
open_risks:
  - The station reached readiness once, not five consecutive FULL_RESTART times; Gate A's 5/5
    requirement is unmet and Gate B live work is forbidden until the boundary question is
    resolved with Sol/High
  - The task-owned overlay needs DYLD_LIBRARY_PATH to include the MuJoCo vendor lib dir;
    whether the product's frozen install must encode that rpath (allowlisted CMakeLists.txt)
    is an open question for review
  - ros2 launch on macOS did not stop its children on SIGINT; a task-owned cleanup step with
    recorded PIDs was required
next_command: NONE - wait for GPT-5.6 Sol / High review of CP-MSC-A
```

## Evidence accounting at CP-MSC-A

- Retained (all under the single registered root): dispatch receipt/handoff, `baseline/`,
  `operator/`, every `gates/<uuid>/` record with argv/exit/elapsed/JUnit, the three experiment
  directories (`experiments/EXP-MSC-001`, `-002`, `-003`) including runner scripts, rendered
  URDF variants, launch logs and `readiness.json`, and the task-owned build trees
  `gate-a/ga-install2` and `gate-a/station-install` with their logs (`COLCON_BUILD_RC=0`).
- Archived: none.
- Deletion candidates (reported only; nothing deleted): `gate-a/ga-build`, `gate-a/ga-build2`,
  `gate-a/station-build` (regenerable build trees, ~417 MB total for the root) and the
  `pytest-XXXXXXXX` invocation directories of green runs. Deletion requires explicit user
  authorisation.

## CP-MSC-CORR-1: correction to the CP-MSC-003/CP-MSC-A loader-path inference

Appended after CP-MSC-A was committed. Reason: the evidence below was gathered after the
checkpoint and contradicts part of the CP-MSC-A reasoning. Historical entries are left
unchanged; this correction supersedes the affected statements.

### Facts (all read-only checks on this host)

1. The committed submodule CMakeLists is explicit about the macOS rpath:
   `third_party/mujoco_ros2_control/mujoco_ros2_control/CMakeLists.txt` sets, under
   `if(APPLE)`, `INSTALL_RPATH "@loader_path"` with the comment "Keep the macOS artifact
   relocatable: ROS underlays belong in the test or launch environment, not in the production
   binary's LC_RPATH commands", while the non-Apple branch uses
   `$ORIGIN/../lib;$ORIGIN/../opt/mujoco_vendor/lib;${CMAKE_INSTALL_PREFIX}/lib`.
   The plugin built from the committed source therefore has exactly one `LC_RPATH`
   (`@loader_path`) and a dependency line `@rpath/libmujoco.3.4.0.dylib` - by design.
2. The project's sanctioned shell environment resolves it: `.envrc.example` appends
   `DYLD_LIBRARY_PATH="${DYLD_LIBRARY_PATH:+$DYLD_LIBRARY_PATH:}$dylib_farm"` with
   `dylib_farm="$ros_workspace/macos_dylib_farm/current"`, and that farm contains
   `libmujoco.3.4.0.dylib -> /Users/matianyi/ros2_jazzy/extra_ws/install/opt/mujoco_vendor/lib/libmujoco.3.4.0.dylib`.
3. The foreign fork workspace carries an **uncommitted** local patch that adds exactly this
   macOS rpath (`@loader_path;@loader_path/../opt/mujoco_vendor/lib;${CMAKE_INSTALL_PREFIX}/lib`)
   plus, on APPLE, `target_link_libraries(ros2_control_node PUBLIC mujoco_ros2_control)` and the
   Cocoa/CoreVideo frameworks. Its built plugin indeed carries those three `LC_RPATH` entries.

### Correction

- The `INFERRED` statement in CP-MSC-003/CP-MSC-A ("the campaign's `STATION_NOT_READY` is
  consistent with an overlay / loader-path defect in the environment the campaign used") is
  **retracted**. EXP-MSC-002 failed because *this dispatch's runners* did not load the
  project's sanctioned environment (no `.envrc` / dylib farm), so `DYLD_LIBRARY_PATH` never
  contained the MuJoCo vendor directory. That is a defect of my run environment, not evidence
  about the campaign's.
- What EXP-MSC-002 does prove is narrower and still useful: this stack fails **hard and
  misleadingly** when the loader environment is incomplete - pluginlib reports
  `Failed to load library ... Make sure that you are calling the PLUGINLIB_EXPORT_CLASS macro`,
  which points at the plugin export while the real cause is `Library not loaded`, and
  controller_manager then loops on `/robot_description` forever without publishing
  `/controller_manager/list_controllers`. Any diagnosis that reads only the pluginlib hint or
  the downstream `STATION_NOT_READY` would be misled.
- The campaign's failure therefore stays **UNCONFIRMED** with no surviving environment
  explanation from this dispatch.

### New, checkable hypothesis (not yet measured)

The same farm resolves `libmujoco_ros2_control.dylib` and every
`libmujoco_ros2_control_msgs*` dylib to the **foreign fork** prefix. With the farm on
`DYLD_LIBRARY_PATH`, a process that loads this worktree's plugin by absolute path can still
bind its dependencies (or any artifact resolved by leaf name) to the fork's copies - a
mixed-provenance closure of exactly the kind `RuntimeClosureIdentity`/`RuntimeAttestation`
(Task 1) is built to detect. Whether the campaign's controller-manager ever reached readiness
under such a mix is not measured here.

Next command if this is pursued (requires no product edit, task-owned processes only):
run `so101_diagnose_macos_station --mode ROBOT_SYSTEM_CONTROLLER_MANAGER` with the project's
sanctioned environment loaded (farm included) and attest the live process with
`default_loaded_image_probe` + `build_runtime_attestation` to record which prefix every
`mujoco_ros2_control*` image actually came from.
