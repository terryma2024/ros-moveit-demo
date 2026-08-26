# RGB-D Pick-Place on mujoco_ros2_control 0.1.0 Main Integration Ledger

```yaml
task_id: so101-rgbd-pick-place-mrc010-main
goal: Prove RGB-D-driven physical pick-place from all four MJCF cup keyframes on macOS and ai-station using child main@5e9d67c.
success_contract: Four independent FULL_RESTART successes on macOS, four independent FULL_RESTART successes on ai-station, plus one ai-station task_start repeat so the final fixed candidate has five consecutive valid live runs.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-pick-place-mujoco-0-1-main
branch: codex/rgbd-pick-place-mujoco-0-1-main
base_commit: b73748f86acc891711aa455fc911a9ebde52686d
current_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_commit: 1a0c532cb4ff012bc1cef95a47594ca8a1a65fa5
commit_semantics: current_commit and implementation_commit identify the immutable installed runtime; record_commit identifies the ledger-only commit that first contains CP-002 and is resolved additively after that commit exists.
target_child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
evidence_root: /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/
confirmed_conclusions:
  - OBS-001: child main@5e9d67c contains aeff7e5 and both commits have identical trees.
  - OBS-002: parent main@b73748f clean isolated-install baseline passed 303 of 303 so101_demo_py tests from /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-baseline-canonical.
  - OBS-003: origin/codex/rgbd-perception-pick-place@0649f3b retains prior four-position qualification, but those runs do not count for this new child-main candidate.
  - OBS-006: implementation 208dd216 with child main@5e9d67c built into isolated Mac fork/project installs; 17 registered child CTests (230 JUnit cases), 442 project tests, and the 153-test directed integration set pass.
disproven_routes:
  - OBS-004: sourcing the parent checkout .envrc in a nested worktree selects the parent install and is not valid candidate provenance.
  - OBS-005: using non-canonical /tmp build paths on macOS makes installed manifest and ament prefix strings diverge.
  - OBS-007: enabling zsh nounset before generated colcon setup scripts aborts source at unset COLCON_TRACE and removes required CMake prefixes.
  - OBS-008: colcon's macOS child environment omits DYLD_LIBRARY_PATH; accepted child tests use direct Homebrew CTest after same-process setup, with the candidate fork ahead of the dylib farm.
  - OBS-009: putting the dylib farm ahead of the task fork selects the old fork library and is invalid candidate provenance.
  - OBS-010: Mac EXP-015 is a VALID product failure: candidate project-install omitted ABI-dependent so101_mujoco_support, so the new 0.1.0 pre_step caller loaded the old isolated-workspace SimulationEvidencePlugin vtable and crashed with SIGSEGV before perception.
  - OBS-011: The RED support-plugin prefix contract is GREEN after building so101_mujoco_support against the candidate fork into the candidate project overlay; support CTest 1/1 and project pytest 443/443 pass.
  - OBS-012: Non-qualifying SMOKE-001 loaded only the ABI-aligned candidate SimulationEvidencePlugin, advanced authoritative simulation evidence from step 90989 to 90994, crossed the EXP-015 crash boundary for 221.44 s, and shut down cleanly after one owned SIGINT with no -11 or owned residue.
  - OBS-013: EXP-016 is a VALID product failure after the ABI fix: exact installed provenance and cwd passed, but rgbd_cup_pose exhausted its startup deadline during ROS runtime construction before producing any RGB-D/point-cloud/cup-pose evidence.
  - OBS-014: SMOKE-002 measures material live-stack contention: the same runtime probe grows from 6.69 s empty-graph to 17.14 s with MuJoCo/MoveIt live, principally Open3D 3.32 to 9.01 s and create_node 2.85 to 6.82 s, but a single probe still remains below 30 s.
open_hypotheses:
  - The tree-identical child-main merge commit preserves all qualified 0.1.0 runtime behavior after RGB-D integration.
  - The merged camera contract retains both 0.1.0 lifecycle and perception task-camera requirements.
  - A clean so101_mujoco_support rebuild against the frozen 0.1.0 child removes the confirmed ABI mismatch without source behavior changes.
latest_checkpoint: CP-022
next_experiment: SMOKE-003
```

## Shared live acceptance contract

`AC-001` requires every countable run to prove all of the following from the same session:

- exact parent commit, child gitlink/checkout `5e9d67c`, isolated installed package prefix, executable,
  ROS domain, partition, session, keyframe, and owned PID set;
- real aligned `640x480` CameraInfo/RGB/depth samples in `task_camera_frame`, encodings `rgb8` and
  `32FC1`, with finite positive depth;
- accepted segmented point cloud, radius fit, retained summary and nonempty PLY;
- fresh `world` `/cup_pose` from `rgbd_cup_pose`, no truth publisher, and error within the existing
  `0.01 m` tolerance of MuJoCo truth;
- installed exact-status runner exits zero, `dynamic_cup_pick_place` reaches `DONE` with 19 expected
  transitions, and motion states contain trajectory/joint/TF evidence;
- bilateral unsupported lift and transport, detach before open, stable table-supported final pose in
  the red target, zero final fingertip contacts, and no final physical attachment;
- MoveIt cup shadow attaches, detaches, and ends as a world object at the final MuJoCo pose;
- fresh baseline, transport, and final images are captured and inspected for the same Viewer/session;
- only run-owned processes exit, with no owned node, Viewer, tmux pane, or domain process remaining.

Any missing provenance, duplicate stack, old screenshot, wrong session, unavailable camera sample,
or mixed evidence makes the run `INVALID`. A countable behavioral failure is `VALID` failure and
ends the fixed-candidate consecutive batch.

## Planned macOS runs

```yaml
experiment_id: EXP-010
status: INVALID
prior_experiment: NONE
hypothesis: The final installed candidate completes AC-001 from task_start on macOS.
prediction: The perceived start pose is near [0.02, -0.28, 0.165] and the cup is released stably in the red target.
single_variable: initial_keyframe=task_start
lifecycle: FULL_RESTART
preconditions:
  - Candidate commit is frozen, clean, and installed from the isolated worktree.
  - Domain 220, session mac-mrc010-task-start-exp010, and the run evidence path are empty.
success_criteria:
  - AC-001 passes every clause.
failure_criteria:
  - The clean candidate starts correctly but any AC-001 product clause fails.
invalid_criteria:
  - Provenance, process isolation, GUI freshness, or evidence ownership is missing.
provenance:
  source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 220
  gz_partition: mac-mrc010-task-start-exp010
commands:
  - command: ROS_DOMAIN_ID=220 GZ_PARTITION=mac-mrc010-task-start-exp010 ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-task-start-exp010 mujoco_initial_keyframe:=task_start evidence_file:=/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/task-start.json
    exit_code: 1
observed:
  - INVALID_ENVIRONMENT: tmux inherited a deleted historical worktree as cwd; eleven getcwd-failed XML parser diagnostics preceded RGBD_CUP_POSE_TIMEOUT.
  - The exact Viewer baseline was captured and inspected, but transport and final boundaries never existed.
inferred:
  - The stale cwd is a launch-environment contaminant; this run cannot support product behavior conclusions.
conclusion: Strict INVALID; excluded from the Mac success set.
evidence:
  - /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010
decision: REPEAT
next_experiment: EXP-014
```

```yaml
experiment_id: EXP-014
status: INVALID
prior_experiment: EXP-010
hypothesis: Binding the task-owned tmux pane to the current live worktree removes only the stale-cwd contamination and permits the unchanged task_start candidate to complete AC-001.
prediction: No getcwd-failed diagnostic occurs; the perceived start pose is near [0.02, -0.28, 0.165], and the unchanged workflow releases the cup stably in the red target.
single_variable: tmux startup adds -c /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-pick-place-mujoco-0-1-main; product command, overlays, keyframe, policy, geometry, thresholds, and capture boundaries are unchanged.
lifecycle: FULL_RESTART
preconditions:
  - EXP-010 exact-owned product, capture helper, Viewer, tmux, and domain processes are absent; its invalid evidence remains immutable.
  - The candidate is unchanged, the task worktree exists, and the new tmux pane cwd readback equals that task worktree before the product command starts.
  - Domain 229, session mac-mrc010-task-start-retry-exp014, and the new run evidence path are empty.
success_criteria:
  - AC-001 passes every clause.
failure_criteria:
  - The clean unchanged candidate starts correctly but any AC-001 product clause fails.
invalid_criteria:
  - Provenance, cwd/process isolation, GUI freshness, or evidence ownership is missing.
provenance:
  source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 229
  gz_partition: mac-mrc010-task-start-retry-exp014
commands:
  - command: ROS_DOMAIN_ID=229 GZ_PARTITION=mac-mrc010-task-start-retry-exp014 ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-task-start-retry-exp014 mujoco_initial_keyframe:=task_start evidence_file:=/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/task-start-retry.json
    exit_code: 245
observed:
  - INVALID_ENVIRONMENT: the explicit tmux -c precondition failed before product startup; pane readback still selected the deleted historical worktree and child getcwd returned dot.
  - Seven getcwd-failed diagnostics preceded the required MuJoCo runtime SIGSEGV; launch then shut down the remaining owned graph.
inferred:
  - No causal claim between stale cwd and the SIGSEGV is required or made; the pre-registered cwd isolation precondition independently makes the run non-counting.
conclusion: Strict INVALID; excluded from product behavior conclusions.
evidence:
  - /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014
decision: REPEAT_AFTER_NON_PRODUCT_TMUX_CWD_AB
next_experiment: NONE
```

```yaml
experiment_id: EXP-011
status: PLANNED
prior_experiment: EXP-010
hypothesis: Changing only the keyframe to cup_test_forward_5cm preserves AC-001 on macOS.
prediction: The perceived start pose is near [0.02, -0.33, 0.165] and the same physical workflow succeeds.
single_variable: initial_keyframe=cup_test_forward_5cm
lifecycle: FULL_RESTART
preconditions:
  - EXP-010 owned processes are absent and the candidate is unchanged.
  - Domain 221, session mac-mrc010-forward-exp011, and the run evidence path are empty.
success_criteria:
  - AC-001 passes every clause.
failure_criteria:
  - The clean candidate starts correctly but any AC-001 product clause fails.
invalid_criteria:
  - Provenance, process isolation, GUI freshness, or evidence ownership is missing.
provenance:
  source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 221
  gz_partition: mac-mrc010-forward-exp011
commands:
  - command: ROS_DOMAIN_ID=221 GZ_PARTITION=mac-mrc010-forward-exp011 ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-forward-exp011 mujoco_initial_keyframe:=cup_test_forward_5cm evidence_file:=/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-011/forward.json
    exit_code: PENDING
observed:
  - NOT_RUN
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-011
decision: PENDING
next_experiment: EXP-012
```

```yaml
experiment_id: EXP-012
status: PLANNED
prior_experiment: EXP-011
hypothesis: Changing only the keyframe to cup_test_left_5cm preserves AC-001 on macOS.
prediction: The perceived start pose is near [-0.03, -0.28, 0.165] and the same physical workflow succeeds.
single_variable: initial_keyframe=cup_test_left_5cm
lifecycle: FULL_RESTART
preconditions:
  - EXP-011 owned processes are absent and the candidate is unchanged.
  - Domain 222, session mac-mrc010-left-exp012, and the run evidence path are empty.
success_criteria:
  - AC-001 passes every clause.
failure_criteria:
  - The clean candidate starts correctly but any AC-001 product clause fails.
invalid_criteria:
  - Provenance, process isolation, GUI freshness, or evidence ownership is missing.
provenance:
  source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 222
  gz_partition: mac-mrc010-left-exp012
commands:
  - command: ROS_DOMAIN_ID=222 GZ_PARTITION=mac-mrc010-left-exp012 ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-left-exp012 mujoco_initial_keyframe:=cup_test_left_5cm evidence_file:=/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-012/left.json
    exit_code: PENDING
observed:
  - NOT_RUN
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-012
decision: PENDING
next_experiment: EXP-013
```

```yaml
experiment_id: EXP-013
status: PLANNED
prior_experiment: EXP-012
hypothesis: Changing only the keyframe to cup_test_right_5cm preserves AC-001 on macOS.
prediction: The perceived start pose is near [0.07, -0.28, 0.165] and the same physical workflow succeeds.
single_variable: initial_keyframe=cup_test_right_5cm
lifecycle: FULL_RESTART
preconditions:
  - EXP-012 owned processes are absent and the candidate is unchanged.
  - Domain 223, session mac-mrc010-right-exp013, and the run evidence path are empty.
success_criteria:
  - AC-001 passes every clause.
failure_criteria:
  - The clean candidate starts correctly but any AC-001 product clause fails.
invalid_criteria:
  - Provenance, process isolation, GUI freshness, or evidence ownership is missing.
provenance:
  source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 223
  gz_partition: mac-mrc010-right-exp013
commands:
  - command: ROS_DOMAIN_ID=223 GZ_PARTITION=mac-mrc010-right-exp013 ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-right-exp013 mujoco_initial_keyframe:=cup_test_right_5cm evidence_file:=/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-013/right.json
    exit_code: PENDING
observed:
  - NOT_RUN
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-013
decision: PENDING
next_experiment: EXP-020
```

## Planned ai-station runs

The ai-station entries use the same full `AC-001` criteria. The command is identical to the Mac
runner command after sourcing `/opt/ros/jazzy/setup.zsh`, the isolated fork install, and the isolated
project install. Only the frozen keyframe, domain, session, partition, and evidence file change.

| Experiment | Domain | Keyframe | Session and partition | Evidence file |
|---|---:|---|---|---|
| EXP-020 | 224 | `task_start` | `linux-mrc010-task-start-exp020` | `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-runs/exp-020/task-start.json` |
| EXP-021 | 225 | `cup_test_forward_5cm` | `linux-mrc010-forward-exp021` | `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-runs/exp-021/forward.json` |
| EXP-022 | 226 | `cup_test_left_5cm` | `linux-mrc010-left-exp022` | `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-runs/exp-022/left.json` |
| EXP-023 | 227 | `cup_test_right_5cm` | `linux-mrc010-right-exp023` | `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-runs/exp-023/right.json` |
| EXP-024 | 228 | `task_start` | `linux-mrc010-task-start-repeat-exp024` | `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-runs/exp-024/task-start-repeat.json` |

For each `EXP-020` through `EXP-024`:

```yaml
status: PLANNED
lifecycle: FULL_RESTART
preconditions:
  - The exact pushed candidate is checked out cleanly in a new ai-station isolation root.
  - The previous experiment's owned graph is absent; the listed domain, session, and evidence path are empty.
success_criteria:
  - AC-001 passes every clause.
failure_criteria:
  - The clean candidate starts correctly but any AC-001 product clause fails.
invalid_criteria:
  - Provenance, process isolation, GUI freshness, or evidence ownership is missing.
provenance:
  source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
  install_overlay: /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-candidate/project-install
  runtime_executable: /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/linux-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
observed:
  - NOT_RUN
inferred:
  - NONE
conclusion: PENDING
decision: PENDING
```

The table row supplies each experiment's single variable, exact domain, partition/session, command
argument, and evidence path. EXP-024 repeats EXP-020 with an otherwise unchanged fixed candidate to
complete the five-run ai-station stability batch.

## Checkpoints

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The approved main integration can be implemented without changing qualified perception or motion behavior.
working_tree_status: Design amendment and this ledger are uncommitted; production source and submodule remain at parent main baseline.
owned_processes: NONE
preserved_processes: Mac parent checkout user changes; all existing ai-station worktrees, tmux sessions, Codex processes, and user stacks.
confirmed_conclusions:
  - Child main ancestry/tree equality and the 303-test clean parent baseline are observed.
disproven_routes:
  - Parent .envrc and non-canonical macOS /tmp build paths are invalid provenance routes.
open_risks:
  - Merge compatibility, dual-platform builds, nine live runs, and visual gates remain unverified.
next_command: Commit the amended design, ledger, and implementation plan; then begin the version-lock RED test.
```

```yaml
checkpoint_id: CP-002
recorded_at: 2026-08-26T23:03:02+08:00
last_valid_experiment: NONE
current_hypothesis: The exact installed 0.1.0-main candidate is statically qualified; EXP-010 must be the first fresh Mac live acceptance run.
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_commit: 1a0c532cb4ff012bc1cef95a47594ca8a1a65fa5
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
working_tree_status: Only this ledger is modified for CP-002; implementation commit 208dd216 and child checkout are clean.
owned_processes: NONE
preserved_processes: Mac parent checkout user changes; all unrelated local and ai-station worktrees, processes, tmux sessions, and evidence.
installed_provenance:
  fork_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install
  project_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  package_prefixes:
    mujoco_3d_lidar: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/mujoco_3d_lidar
    mujoco_ros2_control_msgs: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/mujoco_ros2_control_msgs
    mujoco_ros2_control_plugins: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/mujoco_ros2_control_plugins
    mujoco_ros2_control: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/mujoco_ros2_control
    so101_demo_py: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  launch_file: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/share/so101_demo_py/launch/so101_mujoco_perception_pick_place.launch.py
  python_runtime_module: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-build/so101_demo_py/so101_demo/runtime/launch_composition.py
  bundle_sha256: 0caa56a10cc6d13d808aa8b57f5fbfae8c7fca808b53edccbbb47d03de7bc30e
commands:
  - command: colcon build four selected child packages into mac-candidate/fork-build and fork-install
    exit_code: 0
  - command: direct Homebrew CTest for all four selected child package build directories after same-process overlay setup
    exit_code: 0
  - command: colcon test-result over accepted direct-CTest JUnit scope
    exit_code: 0
  - command: colcon build --packages-select so101_demo_py into mac-candidate/project-build and project-install
    exit_code: 0
  - command: python -m pytest src/so101_demo_py/test -q
    exit_code: 0
  - command: python -m pytest nine directed version/camera/keyframe/TF/RGB-D/scene-sync/runner files -q
    exit_code: 0
automated_results:
  child_build: Four of four selected packages built; zero-package discovery did not occur.
  child_tests: 17 of 17 registered CTests pass; 230 JUnit cases, 0 errors, 0 failures. The lidar and msgs packages register no standalone tests; core and plugins provide the nonzero package gate.
  project_build: so101_demo_py built into the independent project overlay.
  project_full_tests: 442 passed in 21.03 s; collect-only independently found 442 tests.
  project_directed_tests: 153 passed in 17.45 s.
  backend_integration: PASS
  lock_gitlink_child_parity: Both installed locks, source locks, gitlink, and child HEAD select main@5e9d67c; child contains upstream 0.1.0 and f19a8cc lineage, and its tree equals aeff7e5.
invalid_non_counting_attempts:
  - Initial child build failed before compilation because nounset interrupted generated setup scripts; it is retained under fork-build-invalid-nounset and fork-log-invalid-nounset.
  - Initial colcon test child environment dropped DYLD_LIBRARY_PATH and produced loader errors; its dashboard and complete log are retained under fork-test-invalid-colcon-child-env and fork-test-command.log.
  - The first direct CTest A/B put the dylib farm before the task fork and selected an old library; direct-ctest-ab-core.log is retained.
  - A provenance readback reused zsh special variable path and lost PATH; installed-provenance-readback-invalid-zsh-path.txt is retained.
  - An unsourced collect-only probe produced collection errors; project-pytest-collect-only-invalid-unsourced.log is retained.
confirmed_conclusions:
  - OBSERVED: Natural ament prefixes resolve all four child packages to fork-install and so101_demo_py to project-install; the installed runner, launch, locks, runtime library, and immutable bundle are readable there.
  - OBSERVED: The accepted same-process Mac loader order puts the task fork before the existing farm and old fork, so candidate symbols and ROS dylibs both resolve.
  - OBSERVED: Static qualification is complete without changing grasp geometry, motion policy, camera extrinsics, target, controller, or recovery behavior.
disproven_routes:
  - nounset-before-source, colcon child-env test execution, farm-before-candidate, zsh special path reuse, and unsourced pytest collection are invalid environment routes, not product regressions.
open_risks:
  - EXP-010 through EXP-013 have not run; camera, point cloud, TF, physical workflow, Planning Scene, fresh visuals, and clean shutdown remain live acceptance gates.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-build-command-r2.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-ctest.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-test-result-verbose-clean-scope.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-build-command.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-full.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-collect-only.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-directed-pytest.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/installed-provenance-readback.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/installed-provenance-manifest.json
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/final-static-verification.txt
decision: PROCEED_TO_EXP_010_MAC_FULL_RESTART
next_experiment: EXP-010
next_command: Read the project-local gui-capture skill, prove domain 220/session/evidence/Viewer isolation, and transition only EXP-010 to RUNNING before starting the GUI stack.
```

## CP-002-AUDIT-CORRECTION — Task 3 review round 1

This is additive; it does not rewrite CP-002 or change installed implementation commit
`208dd216f9ef52e2792830a19c1e070b8aef1778`.

```yaml
correction_id: CP-002-AUDIT-CORRECTION
record_head_before_correction: ae4d20af0645bbf26459e4132e4287407cba8800
acceptance_ruling:
  - Upstream mujoco_3d_lidar and mujoco_ros2_control_msgs intentionally register no standalone CTest. Their literal "No tests were found!!!" output is preserved and is not counted as a test.
  - A selected leaf with no standalone CTest passes only through nonzero installed-artifact or installed-interface consumer tests against the exact candidate overlay; a raw no-tests output never passes alone.
  - mujoco_3d_lidar substitute gate is the 3-case test_3d_lidar_plugin ament-resource/plugin consumer; 3/3 passed.
  - mujoco_ros2_control_msgs substitute gate is test_mujoco_simulation (44 cases) plus test_viewer_camera (7 cases); 51/51 generated-interface consumer cases passed.
  - Project contract nodeids test_macos_install_contract.py::test_installer_builds_exact_upgrade_package_set_and_checks_new_artifacts and test_macos_install_contract.py::test_integration_guide_reads_back_all_four_fork_package_prefixes passed inside the 442-case full suite. They assert the exact four-package set, required message interfaces/artifacts, and all four candidate prefix readbacks.
accepted_environment_preamble_before_child_build: |-
  source /Users/matianyi/ros2_jazzy/.venv/bin/activate
  source /opt/ros/jazzy/setup.zsh
  source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
  source /Users/matianyi/ros2_jazzy/so101_isolated_ws/install/setup.zsh
  export VIRTUAL_ENV=/Users/matianyi/ros2_jazzy/.venv
  export PATH="/Users/matianyi/ros2_jazzy/.venv/bin:${PATH}"
  export PYTHONNOUSERSITE=1
  export DYLD_LIBRARY_PATH="/Users/matianyi/ros2_jazzy/macos_dylib_farm/current${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
  export ROS_LOG_DIR=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/ros-log
accepted_environment_preamble_before_child_test: |-
  source /Users/matianyi/ros2_jazzy/.venv/bin/activate
  source /opt/ros/jazzy/setup.zsh
  source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
  source /Users/matianyi/ros2_jazzy/so101_isolated_ws/install/setup.zsh
  export DYLD_LIBRARY_PATH="/Users/matianyi/ros2_jazzy/macos_dylib_farm/current${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
  source /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/setup.zsh
  export VIRTUAL_ENV=/Users/matianyi/ros2_jazzy/.venv
  export PATH="/Users/matianyi/ros2_jazzy/.venv/bin:${PATH}"
  export PYTHONNOUSERSITE=1
  export ROS_LOG_DIR=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/ros-log
accepted_environment_preamble_before_project_test: |-
  source /Users/matianyi/ros2_jazzy/.venv/bin/activate
  source /opt/ros/jazzy/setup.zsh
  source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
  source /Users/matianyi/ros2_jazzy/so101_isolated_ws/install/setup.zsh
  export DYLD_LIBRARY_PATH="/Users/matianyi/ros2_jazzy/macos_dylib_farm/current${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
  source /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/setup.zsh
  source /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/setup.zsh
  export VIRTUAL_ENV=/Users/matianyi/ros2_jazzy/.venv
  export PATH="/Users/matianyi/ros2_jazzy/.venv/bin:${PATH}"
  export PYTHONNOUSERSITE=1
  export SO101_SOURCE_COMMIT=208dd216f9ef52e2792830a19c1e070b8aef1778
  export ROS_LOG_DIR=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-ros-log
accepted_commands:
  - command: |-
      colcon --log-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-log build --base-paths third_party/mujoco_ros2_control --build-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-build --install-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install --packages-select mujoco_3d_lidar mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control --symlink-install --event-handlers console_direct+ > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-build-command-r2.log 2>&1
      task_rc=$?; printf '%s\n' "${task_rc}" > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-build-exit-code.txt; exit "${task_rc}"
    preamble: accepted_environment_preamble_before_child_build
    exit_code: 0
    exit_code_evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-build-exit-code.txt
  - command: |-
      : > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-ctest.log; task_rc=0
      for package in mujoco_3d_lidar mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control; do printf 'PACKAGE=%s\n' "${package}" >> /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-ctest.log; ctest --test-dir "/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-build/${package}" --output-on-failure >> /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-ctest.log 2>&1; package_rc=$?; printf 'PACKAGE_EXIT=%s\n' "${package_rc}" >> /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-ctest.log; if test "${package_rc}" -ne 0; then task_rc=${package_rc}; fi; done
      printf '%s\n' "${task_rc}" > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-ctest-exit-code.txt; test "${task_rc}" -eq 0 || exit "${task_rc}"
      colcon test-result --test-result-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-build --all --verbose > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-test-result-verbose-clean-scope.txt 2>&1
      task_rc=$?; printf '%s\n' "${task_rc}" > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-test-result-clean-scope-exit-code.txt; exit "${task_rc}"
    preamble: accepted_environment_preamble_before_child_test
    exit_code: 0
    exit_code_evidence: [/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-ctest-exit-code.txt, /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-direct-test-result-clean-scope-exit-code.txt]
  - command: |-
      colcon --log-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-log build --base-paths src --build-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-build --install-base /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install --packages-select so101_demo_py --symlink-install --event-handlers console_direct+ > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-build-command.log 2>&1
      task_rc=$?; printf '%s\n' "${task_rc}" > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-build-exit-code.txt; exit "${task_rc}"
    preamble: accepted_environment_preamble_before_child_test
    exit_code: 0
    exit_code_evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-build-exit-code.txt
  - command: |-
      python -m pytest src/so101_demo_py/test -q -o cache_dir=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-cache > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-full.log 2>&1
      task_rc=$?; printf '%s\n' "${task_rc}" > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-full-exit-code.txt; exit "${task_rc}"
    preamble: accepted_environment_preamble_before_project_test
    result: 442 passed in 21.03 s
    exit_code: 0
    exit_code_evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-full-exit-code.txt
  - command: |-
      python -m pytest src/so101_demo_py/test/test_macos_install_contract.py src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py src/so101_demo_py/test/test_mujoco_cup_test_keyframes.py src/so101_demo_py/test/test_camera_tf_contract.py src/so101_demo_py/test/test_rgbd_point_cloud.py src/so101_demo_py/test/test_rgbd_cup_pose.py src/so101_demo_py/test/test_dynamic_scene_sync.py src/so101_demo_py/test/test_perception_pick_place_launch.py src/so101_demo_py/test/test_perception_launch_runner.py -q -o cache_dir=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-directed-pytest-cache > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-directed-pytest.log 2>&1
      task_rc=$?; printf '%s\n' "${task_rc}" > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-directed-pytest-exit-code.txt; exit "${task_rc}"
    preamble: accepted_environment_preamble_before_project_test
    result: 153 passed in 17.45 s
    exit_code: 0
    exit_code_evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-directed-pytest-exit-code.txt
  - command: |-
      python -m pytest src/so101_demo_py/test --collect-only -q -o cache_dir=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-cache-collect > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-collect-only.log 2>&1
      task_rc=$?; printf '%s\n' "${task_rc}" > /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-collect-only-exit-code.txt; exit "${task_rc}"
    preamble: accepted_environment_preamble_before_project_test
    result: 442 tests collected
    exit_code: 0
    exit_code_evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-pytest-collect-only-exit-code.txt
non_counting_out_of_root_evidence:
  path: /tmp/so101-debug-mrc010-task1/
  status: Retained, not used for CP-002 acceptance, and not part of the registered evidence root.
  disposition: Deletion candidate only; no deletion performed and explicit user authorization remains required.
retained_runs: [/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/]
archived_runs: []
deletion_candidates: [/tmp/so101-debug-mrc010-task1/, registered-root invalid environment attempts listed in CP-002]
decision: CP-002_STATIC_QUALIFICATION_REMAINS_ACCEPTED_WITH_EXPLICIT_LEAF_PACKAGE_SUBSTITUTE_GATES
```

## CP-003 / TRANS-EXP-010-RUNNING-001 — Mac live recovery and first run

```yaml
checkpoint_id: CP-003
transition_id: TRANS-EXP-010-RUNNING-001
recorded_at: 2026-08-26T23:28:16+08:00
experiment_id: EXP-010
from: PLANNED
to: RUNNING
last_valid_experiment: NONE
current_hypothesis: The frozen installed candidate completes AC-001 from task_start on macOS.
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_transition: 0a6be4799f017e9b088a9698457279754d7dee38
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
working_tree_status: Clean before this ledger-only transition; the immutable implementation and child checkout are unchanged.
owned_processes: NONE
preserved_processes: Four unrelated historical tmux sessions were left untouched; no live conflicting MuJoCo, MoveIt, RGB-D, workflow, or Viewer process was observed.
pre_running_observed:
  - OBSERVED: The current host is matianyideMacBook-Air.local and the task worktree, branch, implementation commit, child gitlink/checkout, and frozen candidate overlay match CP-002.
  - OBSERVED: Natural ament prefix readback resolves so101_demo_py and all four child packages to the frozen project/fork installs; the installed exact-status runner exists and has SHA256 9ade27dcc334b8cf26d203e3e6dc8b5b26e0fe46487ca4dd7539a52286f9bfd1.
  - OBSERVED: Domain 220 returned no nodes; session/partition mac-mrc010-task-start-exp010, task-owned tmux mrc010-mac-exp010, exact MuJoCo Viewer title, and the nominal evidence path were empty.
  - OBSERVED: The node-list probe itself created ros2-daemon processes for domains 220 through 223 despite the attempted no-daemon environment flag. Those exact probe-owned daemons were stopped by domain before this transition; no product process or evidence identity was created.
confirmed_conclusions:
  - CP-002 remains the last trusted static checkpoint; none of its disproven environment routes is being reused.
disproven_routes:
  - A ros2 node-list emptiness probe is not process-neutral on this Mac and must be followed by exact domain daemon cleanup before a FULL_RESTART run.
single_variable: Exercise task_start in domain 220/session mac-mrc010-task-start-exp010; implementation, overlays, policy, geometry, extrinsics, target, controller, recovery, and capture protocol remain frozen.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/host-worktree-process-window-preflight.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/escalated-process-tmux-window-preflight.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/exp010-exact-provenance-isolation.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/ros-daemon-probe-cleanup.txt
decision: START_EXACT_INSTALLED_EXP_010
next_command: Commit this transition, then start only mrc010-mac-exp010 and concurrently capture baseline, transport, and final from the exact MuJoCo Viewer window ID.
```

## CLOSE-EXP-010-001 / CP-004 — Invalid stale-cwd environment run

```yaml
closure_id: CLOSE-EXP-010-001
checkpoint_id: CP-004
recorded_at: 2026-08-26T23:35:48+08:00
experiment_id: EXP-010
status: INVALID
classification: stale_tmux_server_cwd_invalid_environment
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_closure: 6088dc2
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
first_bad_boundary: The new tmux pane inherited the removed .worktrees/mujoco-ros2-control-0-1-upgrade cwd; getcwd failed before production perception runtime construction.
observed:
  - OBSERVED: Frozen prefixes, installed runner ownership, domain 220, session, keyframe, and child commit were exact, but lsof proved shell PID 52920 held a deleted cwd and the old pathname no longer existed.
  - OBSERVED: The log contains 11 getcwd-failed diagnostics. RGB-D perception then returned RGBD_CUP_POSE_TIMEOUT before constructing its ROS runtime; the wrapper naturally returned 1 after 11 starts, 9 clean exits, and 2 required-process deaths.
  - OBSERVED: Exact Viewer window 45233 owned by ros2_control_node was captured once at baseline. Original-resolution inspection shows the table-supported orange cup at task_start, empty red target, open gripper, and Running status. The 2504x1770 PNG SHA256 is 6ac20e8f58e3e5dd20a61740bbd75ebdb515ffd3be9e7279431fafdb2cdfd2a7.
  - OBSERVED: No accepted perception summary, point cloud, dynamic manifest, transport boundary, or final boundary exists; no product behavior conclusion is drawn.
  - OBSERVED: After product terminal, the exact capture helper was interrupted with observed status 130 because its transport boundary could no longer occur. The dead exact-owned tmux was removed; target session/process/domain-daemon/Viewer identities are absent.
inferred:
  - INFERRED: The deleted cwd contaminated middleware runtime construction. A new tmux pane created with an explicit current worktree cwd distinguishes that environment cause without modifying the product.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/run/child.owner
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/run/full-restart.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/run/capture-terminal-note.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/gui/baseline-helper/20260826T233239-0b7a5ef12109/manifest.json
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/gui/baseline-helper/20260826T233239-0b7a5ef12109/window.png
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/post-cleanup.log
decision: REPEAT_AS_EXP_014_WITH_EXPLICIT_TMUX_CWD
last_valid_experiment: NONE
owned_processes: NONE
preserved_processes: All unrelated historical tmux sessions and desktop windows remain untouched.
open_risks:
  - All four Mac positions remain unqualified under the current candidate.
next_experiment: EXP-014
next_command: Commit this INVALID closure, prove EXP-014 domain/session/evidence/Viewer isolation, transition EXP-014 to RUNNING, and start its tmux pane with -c set to the current worktree.
```

## CP-005 / TRANS-EXP-014-RUNNING-001 — Clean task_start retry

```yaml
checkpoint_id: CP-005
transition_id: TRANS-EXP-014-RUNNING-001
recorded_at: 2026-08-26T23:37:34+08:00
experiment_id: EXP-014
from: PLANNED
to: RUNNING
last_valid_experiment: NONE
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_transition: ef62dd6d62a1d06e9290db14fc9670559eacffa6
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
working_tree_status: Clean before this ledger-only transition; immutable implementation and installed overlays are unchanged.
owned_processes: NONE
pre_running_observed:
  - OBSERVED: Current task worktree exists at /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-pick-place-mujoco-0-1-main and is the explicit tmux startup cwd for this retry.
  - OBSERVED: Domain 229 session/partition process identity, mrc010-mac-exp014 tmux, exact Viewer title, and /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014 were empty.
  - OBSERVED: EXP-010 is terminal INVALID, its evidence remains retained, and no exact-owned product/capture process from it remains.
single_variable: Add the explicit existing task worktree as the tmux pane cwd; all product inputs and the capture protocol are unchanged from EXP-010.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/exp014-provenance-isolation.txt
decision: START_EXACT_INSTALLED_EXP_014
next_command: Commit this transition, create mrc010-mac-exp014 with tmux -c set to the task worktree, verify the pane cwd readback, and run the unchanged installed command with concurrent exact-window capture.
```

## CLOSE-EXP-014-001 / CP-006 — Explicit tmux `-c` did not satisfy cwd precondition

```yaml
closure_id: CLOSE-EXP-014-001
checkpoint_id: CP-006
recorded_at: 2026-08-26T23:41:01+08:00
experiment_id: EXP-014
status: INVALID
classification: explicit_tmux_cwd_precondition_failed
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_closure: 7a99fce
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
first_bad_boundary: Before product startup, tmux-start-readback recorded pane_current_path as the deleted .worktrees/mujoco-ros2-control-0-1-upgrade path instead of the pre-registered live task worktree; child pwd -P consequently produced dot.
competing_hypotheses:
  - H1: The existing shared tmux server cannot honor new-session -c while its inherited base cwd has been unlinked.
  - H2: An explicit absolute cd in the new pane command repairs cwd without restarting or disturbing the shared tmux server.
  - H3: The current task worktree itself cannot be entered from a tmux pane.
observed:
  - OBSERVED: The current task worktree existed and was clean before launch. The exact start command did include tmux new-session -c with that path, but the immediate pane readback selected the deleted historical path and the child owner recorded working_directory=dot.
  - OBSERVED: The first runtime diagnostics at 23:38:57 were getcwd failures in the MuJoCo runtime, robot_state_publisher, and both camera TF publishers; seven total processes reported the same boundary before any controller became active or scene setup completed.
  - OBSERVED: The required MuJoCo runtime later raised SIGSEGV in the physics/plugin callback and exited -11. That first terminal child caused launch-owned SIGINT; scene_setup's wait_for_service interruption and move_group SIGKILL are downstream teardown, not external interrupts.
  - OBSERVED: The exact wrapper naturally returned 245 with 9 starts, 6 clean exits, and 3 died processes. No perception process, point cloud, dynamic manifest, workflow state, transport, or final placement existed.
  - OBSERVED: Capture helper started before launch, selected exact Viewer window 45252/PID 56131, and preserved one inspected 2504x1770 baseline. It performed no signal action and was interrupted with observed status 130 only after product terminal.
  - OBSERVED: Original-resolution inspection shows task_start cup on table, red target empty, gripper open, and Viewer Running. PNG SHA256 is 7658774a607b0ee35e1c3499eb6727b7a0c5a9edfeddd1182ebf4ca09ecbfc04.
  - OBSERVED: Exact-owned tmux was removed after terminal; target session/process/domain-daemon/Viewer identities are absent. Unrelated tmux sessions/windows remain preserved.
classification_rationale:
  - The pre-registered EXP-014 invalid criterion includes cwd/process isolation, and that precondition failed before any product boundary. Therefore this is INVALID even though the later MuJoCo SIGSEGV is observed; no claim that cwd caused SIGSEGV is necessary or made.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/run/tmux-start-readback.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/run/child.owner
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/run/full-restart.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/run/capture.owner
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/run/capture-terminal-note.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/gui/baseline-helper/20260826T233909-4f14a62519c6/manifest.json
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/gui/baseline-helper/20260826T233909-4f14a62519c6/window.png
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-014/post-cleanup.log
decision: RUN_NON_PRODUCT_TMUX_CWD_AB_BEFORE_NEW_EXPERIMENT
last_valid_experiment: NONE
owned_processes: NONE
open_risks:
  - Whether explicit in-pane cd repairs the stale shared tmux server cwd is not yet observed.
  - No current-candidate Mac position is qualified.
next_experiment: NONE
next_command: Commit this INVALID closure, then run a task-owned empty tmux A/B that records pwd for -c alone versus explicit absolute cd; do not start ROS or MuJoCo.
```

## CP-007 — tmux cwd A/B root cause and repaired retry plan

```yaml
checkpoint_id: CP-007
recorded_at: 2026-08-26T23:42:32+08:00
last_valid_experiment: NONE
current_hypothesis: Explicit absolute cd inside the new pane command repairs only the shared tmux server cwd contamination and permits a clean unchanged task_start run.
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_checkpoint: c71a099
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
working_tree_status: Clean before this ledger-only checkpoint; no production or installed artifact changed.
owned_processes: NONE
ab_result:
  - OBSERVED: Probe A used tmux new-session -c with the live task worktree but no in-pane cd. The pane still reported the deleted historical worktree and pwd -P produced dot.
  - OBSERVED: Probe B used the same tmux server and -c option but added an explicit absolute cd in the pane command. Both pane_current_path and pwd -P reported the live task worktree exactly.
  - OBSERVED: Neither probe sourced ROS nor started MuJoCo. Both task-owned sessions were removed and are absent.
root_cause:
  - CONFIRMED: The existing shared tmux server does not honor new-session -c while its inherited base cwd is unlinked; explicit in-pane cd repairs cwd without restarting or disturbing that shared server.
  - H1 confirmed; H2 confirmed; H3 disproved.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/cwd-probe-a.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/cwd-probe-b.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/cwd-ab-readback.txt
decision: PLAN_EXP_015_WITH_EXPLICIT_IN_PANE_CD
next_experiment: EXP-015
```

```yaml
experiment_id: EXP-015
status: VALID_FAILURE
prior_experiment: EXP-014
hypothesis: The unchanged frozen candidate completes task_start AC-001 when the exact-owned pane performs an observed explicit cd to the live worktree before sourcing or starting ROS.
prediction: Pane and child cwd readbacks are exact, getcwd failures are zero, RGB-D perception succeeds, and the full physical workflow releases the cup stably in the red target.
single_variable: Replace ineffective tmux -c-only cwd binding with explicit in-pane absolute cd; product command, overlays, keyframe, policy, geometry, thresholds, and capture protocol remain unchanged.
lifecycle: FULL_RESTART
preconditions:
  - EXP-014 is terminal INVALID and all its exact-owned identities are absent; A/B probe sessions are absent.
  - The immutable candidate and child are unchanged and clean.
  - Domain 230, session mac-mrc010-task-start-retry-exp015, mrc010-mac-exp015, exact Viewer title, and the evidence path are empty.
  - tmux pane_current_path and child pwd readback must equal /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-pick-place-mujoco-0-1-main.
success_criteria:
  - AC-001 passes every clause and getcwd-failed count is zero.
failure_criteria:
  - All preconditions pass but any AC-001 product clause fails.
invalid_criteria:
  - Provenance, cwd/process isolation, GUI freshness, or evidence ownership is missing.
provenance:
  source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 230
  gz_partition: mac-mrc010-task-start-retry-exp015
commands:
  - command: ROS_DOMAIN_ID=230 GZ_PARTITION=mac-mrc010-task-start-retry-exp015 ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-task-start-retry-exp015 mujoco_initial_keyframe:=task_start evidence_file:=/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-015/task-start-retry.json
    exit_code: 245
observed:
  - Pane and child cwd readbacks equal the live task worktree, exact installed source/fork/project provenance is recorded, and getcwd-failed count is zero.
  - The candidate loaded and initialized mujoco_camera_plugin and simulation_evidence, then ros2_control_node died with SIGSEGV -11 on the first physics pre-step callback; wrapper exit is 245.
  - Nine ROS processes started; six exited cleanly, scene_setup exited 1 after launch shutdown, ros2_control_node exited -11, and move_group exited -9 after bounded teardown.
  - GUI helper resolved exact Viewer window 45272 but AXRaise failed after the early product crash, so EXP-015 has no countable capture and no PNG is claimed.
  - Exact-owned tmux, domain/session processes, and Viewer are absent after cleanup; four unrelated tmux sessions remain untouched.
inferred:
  - Candidate project-build/project-install contain no so101_mujoco_support package. Pluginlib resolved the 2026-08-14 isolated-workspace SimulationEvidencePlugin, whose CMakeCache points to the old mujoco_ros2_control_plugins install.
  - Child 738e304's base vtable uses the slot after update for on_physics_step(model,data), while 5e9d67c uses that slot for pre_step(data). The crash report contains both the candidate runtime UUID and the stale plugin UUID and faults precisely at plugin->pre_step(data).
conclusion: VALID behavioral failure. The installed candidate is incomplete across an ABI boundary; all four Mac positions remain unqualified and the consecutive batch stops.
evidence:
  - /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-015
  - /Users/matianyi/Library/Logs/DiagnosticReports/ros2_control_node-2026-08-26-234448.ips
decision: STOP_BATCH_REBUILD_ABI_DEPENDENT_SUPPORT_BEFORE_NEW_QUALIFICATION
next_experiment: NONE
```

## CP-008 / TRANS-EXP-015-RUNNING-001 — A/B-proven cwd repair

```yaml
checkpoint_id: CP-008
transition_id: TRANS-EXP-015-RUNNING-001
recorded_at: 2026-08-26T23:43:28+08:00
experiment_id: EXP-015
from: PLANNED
to: RUNNING
last_valid_experiment: NONE
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_transition: 33ba47d37bd924bbc96795eeba0f6fff897e1b98
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
working_tree_status: Clean before this ledger-only transition; implementation, installed overlays, and child are unchanged.
owned_processes: NONE
pre_running_observed:
  - OBSERVED: Current task worktree and child are exact; domain 230/session process identity, mrc010-mac-exp015, exact Viewer title, and the EXP-015 evidence path are empty.
  - OBSERVED: CP-007 non-product A/B proves the explicit in-pane absolute cd produces the exact live worktree on this preserved shared tmux server.
single_variable: Apply only the A/B-proven in-pane cd before the unchanged installed product command.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/exp015-provenance-isolation.txt
decision: START_EXACT_INSTALLED_EXP_015
next_command: Commit this transition, start exact-owned mrc010-mac-exp015 with explicit in-pane cd, verify pane and child cwd readbacks, and concurrently capture the three exact-window boundaries.
```

## CP-009 / CLOSE-EXP-015-001 — Valid runtime crash stops Mac batch

```yaml
checkpoint_id: CP-009
transition_id: CLOSE-EXP-015-001
recorded_at: 2026-08-26T23:52:18+08:00
experiment_id: EXP-015
from: RUNNING
to: VALID_FAILURE
last_valid_experiment: NONE
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_transition: f1d2744fbf5a44c179bb6c8bd66d6bd723ebcf98
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
working_tree_status: Implementation and frozen installs were unchanged during EXP-015; this closure changes only the ledger.
first_bad_boundary:
  - All registered environment, cwd, ownership, and frozen executable checks passed.
  - Both configured plugins initialized; the first authoritative physics pre-step fanout called plugin->pre_step(data) and ros2_control_node died SIGSEGV -11.
root_cause:
  status: CONFIRMED
  hypothesis: Task 3 omitted ABI-dependent so101_mujoco_support from candidate project-build/install, allowing the new 0.1.0 runtime to load the old plugin vtable.
  evidence:
    - Candidate project-build/project-install have no so101_mujoco_support prefix, plugin XML, or dylib.
    - Runtime pluginlib resource and plugin UUID 909C9671-8ACF-3018-8014-5516D2A54918 resolve to the 2026-08-14 isolated-workspace package; its CMakeCache targets the old fork prefix.
    - Candidate runtime UUID CC34CCF1-ACC8-39A9-A7A1-543C105E0015 appears in the crash report and contains the failing pre_step callback.
    - The base virtual slot changed from old on_physics_step(model,data) to new pre_step(data); the stale dylib is therefore ABI-incompatible at the exact faulting call.
  alternatives:
    - Camera rendering failure is disproved as the immediate boundary: the camera plugin initialized, has a current-ABI default pre_step, and its update thread remained waiting in the crash report.
    - External signal is disproved: capture failed only after the product crash, performed no signal, and the crash is EXC_BAD_ACCESS on the physics thread.
    - Stale cwd is disproved for EXP-015 by exact tmux/child readbacks and zero getcwd diagnostics.
cleanup:
  - mrc010-mac-exp015 removed; no domain 230/session process or exact Viewer remains.
  - Unrelated tmux sessions mrc010-exp013-final-stack, mrc010-exp013-smoke-r3, mrc010-macos-task7a-r4, and mrc010-macos-task7a-r5 were preserved.
  - Evidence was retained; nothing was deleted.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-015/run/full-restart.log
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-015/run/child.owner
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-015/run/cleanup.txt
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-015/diagnosis/root-cause-boundary.md
  - /Users/matianyi/Library/Logs/DiagnosticReports/ros2_control_node-2026-08-26-234448.ips
decision: STOP_MAC_BATCH_AND_REQUIRE_RED_RUNTIME_CONTRACT_PLUS_CLEAN_SUPPORT_REBUILD
next_experiment: NONE
```

## CP-010 — RED candidate support-plugin provenance contract

```yaml
checkpoint_id: CP-010
recorded_at: 2026-08-26T23:56:16+08:00
phase: RED
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_change: f2fed42
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
contract:
  - When so101_demo_py is selected from the isolated candidate project overlay, so101_mujoco_support must resolve from the same project-install base.
  - That support prefix must contain the pluginlib XML and libso101_simulation_evidence_plugin with the host platform suffix.
red_command: zsh /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/support-abi-red.zsh
red_nodeid: src/so101_demo_py/test/test_installed_provenance.py::test_mujoco_support_plugin_comes_from_the_candidate_project_overlay
red_exit_code: 1
observed:
  - Expected support prefix is /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_mujoco_support.
  - Actual support prefix is /Users/matianyi/ros2_jazzy/so101_isolated_ws/install/so101_mujoco_support.
  - The assertion fails before artifact checks, exactly detecting Task 3's omitted ABI-dependent package.
planned_single_fix:
  - Build so101_mujoco_support and so101_demo_py into the candidate project build/install against the frozen fork overlay; do not change product source behavior.
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/support-abi-red.zsh
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-015/diagnosis/root-cause-boundary.md
decision: COMMIT_RED_THEN_CLEAN_BUILD_SUPPORT
next_experiment: NONE
```

## CP-011 — GREEN ABI-aligned support install

```yaml
checkpoint_id: CP-011
recorded_at: 2026-08-27T00:01:32+08:00
phase: GREEN
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_change: 74a65234551527fb5483366aa06a79a8f5efacfe
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
single_fix:
  - Built source package so101_mujoco_support, followed by so101_demo_py, into the existing isolated candidate project build/install after the candidate fork overlay.
  - No grasp, policy, geometry, extrinsics, controller, camera, recovery, or runtime orchestration source changed.
installed_provenance:
  support_prefix: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_mujoco_support
  support_cmake_dependency: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/fork-install/mujoco_ros2_control_plugins
  plugin_sha256: f4487cc3e2467e2ffec5b2ca2fa407d8c372b63cfe07cc1e71e777185d1a7ab7
  plugin_uuid: 74A169FE-F055-3D0D-A333-9F7F7BAEF574
  plugin_symbols:
    - MuJoCoROS2ControlPluginBase::pre_step(mjData_*)
    - SimulationEvidencePlugin::update(mjModel_ const*, mjData_*)
    - SimulationEvidencePlugin::on_physics_step(mjModel_ const*, mjData_ const*) through the separate observer interface
tests:
  - focused installed prefix/XML/dylib contract: 1 passed in 0.40 s
  - support direct CTest: 1/1 passed; test_simulation_evidence_plugin, 4.48 s
  - full project pytest: 443/443 passed in 20.36 s
  - ros2 package readback selects candidate project-install for both so101_demo_py and so101_mujoco_support
evidence:
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/build-support-green.zsh
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/test-support-green.zsh
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/test-project-green.zsh
  - /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-log-support-r1
decision: COMMIT_GREEN_THEN_RUN_NON_QUALIFICATION_CRASH_BOUNDARY_SMOKE
next_experiment: NONE
```

## CP-012 — Plan non-qualification ABI crash-boundary smoke

```yaml
checkpoint_id: CP-012
recorded_at: 2026-08-27T00:03:21+08:00
smoke_id: SMOKE-001
status: RUNNING
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_change: 05200680b07487abed9419003e91d65fa51a0246
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
hypothesis: The ABI-aligned candidate support plugin crosses the first authoritative physics pre_step boundary without the EXP-015 SIGSEGV.
single_variable: Replace only the stale isolated-workspace support plugin with the candidate project-overlay support plugin built at CP-011.
command_scope:
  - Launch the installed base MuJoCo stack, not the perception or dynamic pick-place workflow.
  - Use headless=false only to exercise the same camera/rendering/plugin combination.
  - Observe active controllers, advancing simulation evidence, and process survival for at least ten seconds past the prior crash boundary; then send one owned SIGINT for controlled shutdown.
preconditions:
  - Domain 231, session mac-mrc010-abi-smoke-r1, task tmux mrc010-mac-abi-smoke-r1, exact Viewer title, and evidence path are empty.
  - Candidate demo, support, and fork prefixes are the CP-011 overlays.
  - Unrelated historical tmux sessions and windows remain untouched.
success_criteria:
  - Both plugins initialize, physics advances for at least ten seconds beyond initialization, ros2_control_node remains alive, and no SIGSEGV/pre_step crash occurs.
  - Owned SIGINT produces bounded clean shutdown with no domain/session/tmux/Viewer residue.
failure_criteria:
  - Any product process dies before the owned stop, physics evidence does not advance, or the old pre_step SIGSEGV recurs.
evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-smoke/abi-r1
decision: COMMIT_PLAN_THEN_TRANSITION_RUNNING
next_experiment: SMOKE-001
```

## CP-013 / TRANS-SMOKE-001-RUNNING-001 — Start ABI smoke

```yaml
checkpoint_id: CP-013
transition_id: TRANS-SMOKE-001-RUNNING-001
recorded_at: 2026-08-27T00:03:50+08:00
smoke_id: SMOKE-001
from: PLANNED
to: RUNNING
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: a8b913424374f5c2c1932aa646af714860240cd8
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
pre_running_observed:
  - Candidate worktree is clean; installed prefix contract, support CTest, and 443-case project suite are GREEN.
  - Domain 231/session process identity, task tmux, exact Viewer title, and evidence path are empty.
owned_processes: NONE
decision: START_BASE_STACK_SMOKE
next_command: Start exact-owned tmux with explicit live-worktree cd, observe the old crash boundary plus five seconds, then send SIGINT only to the owned pane.
```

## CP-014 / CLOSE-SMOKE-001-001 — ABI-aligned support crosses crash boundary

```yaml
checkpoint_id: CP-014
transition_id: CLOSE-SMOKE-001-001
recorded_at: 2026-08-27T00:10:09+08:00
smoke_id: SMOKE-001
from: RUNNING
to: PASS_NON_QUALIFYING
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 7d0cf1d
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
runtime_identity:
  domain: 231
  session: mac-mrc010-abi-smoke-r1
  tmux: mrc010-mac-abi-smoke-r1
  ros2_control_pid: 64876
  support_prefix: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_mujoco_support
  loaded_plugin: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_mujoco_support/lib/libso101_simulation_evidence_plugin.dylib
  loaded_plugin_sha256: f4487cc3e2467e2ffec5b2ca2fa407d8c372b63cfe07cc1e71e777185d1a7ab7
  loaded_plugin_uuid: 74A169FE-F055-3D0D-A333-9F7F7BAEF574
  old_isolated_plugin_loaded: false
observations:
  - MuJoCo physics thread started at 1787760321.650565; camera plugin initialized at 1787760324.136948; simulation_evidence initialized at 1787760324.247731; hardware activated at 1787760324.251299.
  - Direct same-domain rclpy observer exited zero after samples 16571 and 16572 advanced simulation_step 90989 to 90994 for exact session mac-mrc010-abi-smoke-r1.
  - gripper_controller, joint_state_broadcaster, and arm_controller all configured and activated; scene_setup READ_BACK succeeded.
  - One Ctrl-C was sent only to the exact owned tmux pane at 1787760545.692; the candidate plugin therefore survived 221.44 s beyond its initialization and 224.04 s beyond physics-thread start.
  - Log contains no SIGSEGV, segmentation fault, process died, exit code -11, or unexpected child exit before the owned stop.
shutdown:
  - controller manager deactivated and shut down all three controllers and RobotSystem.
  - so101_move_group emitted SO101_MOVE_GROUP_ORDERED_SHUTDOWN_OK; move_group, robot_state_publisher, and ros2_control_node all reported clean process exit.
  - Post-cleanup process-environment scan found no ROS_DOMAIN_ID=231, session, or smoke-tmux process; exact tmux is absent and GUI inventory contains no Viewer window.
  - Historical unrelated tmux sessions mrc010-exp013-final-stack, mrc010-exp013-smoke-r3, mrc010-macos-task7a-r4, and mrc010-macos-task7a-r5 remain untouched.
known_observation_gap:
  - Ctrl-C reached the foreground launch and pane shell, so the wrapper did not write exit-code.txt or finished-at.txt. Component-level ordered clean-exit records and exact absence readback establish bounded cleanup; no wrapper exit code is claimed.
evidence:
  owner: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-smoke/abi-r1/owner.txt
  owner_sha256: 34d836ee13a4524a3444d791e2fd815877ca96bccace418ed41b6f987269635f
  log: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-smoke/abi-r1/full.log
  log_sha256: 151c45de34bd1844ae978705ba83474fb564f765b686f4936d2700ac7899e417
  observer: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-smoke/abi-r1/observer-result.json
  observer_sha256: 6aa71fdb317c795adea142568980092430c66226ab093f1f79efa034331cb0b3
  loaded_plugin: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-smoke/abi-r1/loaded-plugin.txt
  loaded_plugin_sha256: 030cec1caa40138f0f7f1dc9232778dc4ec807869f73b3353c342de16e7bf9cf
decision: PASS_NON_QUALIFYING_ABI_SMOKE
next_experiment: EXP-016
```

## CP-015 — Plan rebuilt-candidate task_start qualification

```yaml
checkpoint_id: CP-015
recorded_at: 2026-08-27T00:12:16+08:00
experiment_id: EXP-016
status: PLANNED
qualification: true
position: task_start
lifecycle: FULL_RESTART
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
production_source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_checkpoint: 1f5a12d20a17f24a7304a55bf4b79b67afcd7c14
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
hypothesis: The ABI-aligned installed candidate completes every AC-001 clause from task_start on macOS.
single_variable_from_smoke: Replace the non-qualifying base-stack smoke with the exact installed perception pick-place workflow; installed overlays, product policy, geometry, camera extrinsics, target, controller, and recovery remain frozen.
identity:
  domain: 232
  session: mac-mrc010-task-start-exp016
  partition: mac-mrc010-task-start-exp016
  tmux: mrc010-mac-exp016
  evidence_file: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016/task-start.json
  evidence_root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016
command: ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-task-start-exp016 mujoco_initial_keyframe:=task_start evidence_file:=/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016/task-start.json
preconditions:
  - SMOKE-001 is terminal PASS_NON_QUALIFYING; its exact owned domain/session/tmux/Viewer identities are absent.
  - Worktree and child checkout are exact and clean; installed demo/support/fork prefixes and bundle hashes are freshly read back before RUNNING.
  - Domain 232, session identity, mrc010-mac-exp016, exact Viewer title, and the entire EXP-016 evidence path are empty.
  - Product tmux command starts with an explicit absolute in-pane cd and both pane and child cwd read back as the live worktree.
capture_protocol:
  - Resolve one exact MuJoCo : so101_task_scene Viewer window ID and retain the same ID for all captures.
  - Capture and preserve helper manifest plus PNG at baseline, transport, and released-final live-manifest boundaries.
  - Inspect all three PNGs at original resolution before classification.
success_criteria:
  - Every AC-001 perception, TF, no-truth-bridge, workflow, motion, physical-contact, Planning Scene, capture, exit, and cleanup clause passes from same-session evidence.
failure_criteria:
  - Preconditions and provenance are valid but any AC-001 product clause fails; stop the four-position batch for systematic debugging.
invalid_criteria:
  - Provenance, source order, cwd/process isolation, exact-window capture freshness, or evidence ownership is concretely invalid; retain evidence and use a fresh experiment ID.
sequence_gate: EXP-017 forward is forbidden until EXP-016 has a committed countable-success closure.
decision: COMMIT_PLAN_THEN_PREFLIGHT
next_experiment: EXP-016
```

## CP-016 / TRANS-EXP-016-RUNNING-001 — Start rebuilt-candidate task_start qualification

```yaml
checkpoint_id: CP-016
transition_id: TRANS-EXP-016-RUNNING-001
recorded_at: 2026-08-27T00:15:39+08:00
experiment_id: EXP-016
from: PLANNED
to: RUNNING
qualification: true
position: task_start
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
production_source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_transition: 9f9670626b2e1e630106c9c7d33c7d7c9018d5a2
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
working_tree_status: Clean before this ledger-only transition; no production source or installed artifact changed after CP-011.
pre_running_observed:
  - Domain 232 and exact session process identity, mrc010-mac-exp016, exact Viewer title, and the entire EXP-016 evidence path are empty; preflight created no ROS daemon.
  - Candidate demo/support/fork prefixes resolve to the registered frozen overlays; exact installed runner SHA256 is 9ade27dcc334b8cf26d203e3e6dc8b5b26e0fe46487ca4dd7539a52286f9bfd1.
  - Installed support plugin SHA256 f4487cc3e2467e2ffec5b2ca2fa407d8c372b63cfe07cc1e71e777185d1a7ab7 and UUID 74A169FE-F055-3D0D-A333-9F7F7BAEF574 match the passing ABI smoke.
  - Installed bundle SHA256 is e2d777dfa2d925998583b8c1b376f063ec47f476d98402297701b541da455175 under SO101_SOURCE_COMMIT 74a6523.
  - Frozen task-owned runner and capture helpers pass zsh syntax checks; capture uses the same exact Viewer window ID at all three live-manifest boundaries.
evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-live-preflight/exp016-provenance-isolation.txt
owned_processes: NONE
decision: START_EXACT_INSTALLED_EXP_016
next_command: Commit this transition; create only mrc010-mac-exp016 with explicit in-pane absolute cd; verify pane and child cwd; run the exact installed command and same-ID three-boundary GUI capture.
```

## CP-017 / CLOSE-EXP-016-001 — Valid RGB-D runtime-construction timeout

```yaml
checkpoint_id: CP-017
transition_id: CLOSE-EXP-016-001
recorded_at: 2026-08-27T00:20:46+08:00
experiment_id: EXP-016
from: RUNNING
to: VALID_FAILURE
qualification: true
position: task_start
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
production_source_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
record_head_before_transition: 3dc08029a00311c2bb1f7b96d50a8097e17f8c0c
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
classification: VALID_BEHAVIORAL_FAILURE
first_bad_boundary: rgbd_cup_pose exited 1 with RGBD_CUP_POSE_TIMEOUT and message startup deadline expired during ROS runtime construction before creating summary.json or cup.ply.
validity_basis:
  - Explicit in-pane cd repaired the shared tmux cwd; pane and child readbacks equal the live task worktree and the log contains zero getcwd failures.
  - Domain 232, session, evidence path, task tmux, and exact Viewer were fresh; owner readback records the exact demo/support/fork prefixes, installed bundle e2d777dfa2d925998583b8c1b376f063ec47f476d98402297701b541da455175, runner SHA 9ade27dc, and ABI-aligned support SHA f4487cc3/UUID 74A169FE.
  - Candidate camera and simulation_evidence plugins initialized without SIGSEGV; all three controllers activated and Planning Scene READ_BACK succeeded before perception started.
observed:
  - Eleven ROS processes started. The wrapper naturally exited 1; nine processes exited cleanly, rgbd_cup_pose exited 1, and dynamic_cup_pick_place exited -2 only after launch-owned SIGINT teardown.
  - Perception and dynamic evidence directories were exclusively created, but no summary, PLY, dynamic manifest, point-cloud, cup-pose, state-machine, trajectory, contact, or final-placement evidence exists.
  - No truth bridge was introduced; no product motion began. Dynamic exit -2 and KeyboardInterrupt are downstream of the required perception exit and are not separate root causes.
capture:
  - GUI helper selected exact Viewer window 45303/PID 66158 and preserved one fresh 2504x1770 baseline manifest/PNG.
  - Original-resolution inspection shows the task_start cup table-supported, red target empty, gripper open, and Viewer Running.
  - Transport/final boundaries never existed. After product terminal the exact capture PID was stopped with SIGINT and returned 130; no transport or final image is claimed.
  - baseline_png_sha256: 82e1e84573635879cc59e54e16d43e6a635d6f85b691afd7dc9ecccf291c4439
  - baseline_manifest_sha256: adf4acc65089bb4d75cf169640a2484786ec1083368982ffd1b68048af7dcdad
cleanup:
  - Exact owned product tmux, capture PID, domain/session processes, all eleven owned PIDs, and exact Viewer are absent.
  - Historical unrelated tmux sessions remain untouched; no evidence was deleted.
evidence:
  owner: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016/run/child.owner
  owner_sha256: 888bf908218a22b9f19d9409e83116277c33a030861f1a790b7c209979f37f9c
  log: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016/run/full-restart.log
  log_sha256: 8a6a06e77f82ea563e736a37e9f3b3b82b791116b89b4b6190290579acf100d6
  baseline_manifest: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016/gui/baseline-helper/20260827T001704-01ac7fe6b42d/manifest.json
  baseline_png: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016/gui/baseline-helper/20260827T001704-01ac7fe6b42d/window.png
  cleanup: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-016/post-cleanup.txt
decision: STOP_BATCH_AND_DEBUG_RGBD_RUNTIME_CONSTRUCTION
next_experiment: NONE
```

## CP-018 — Plan non-qualification runtime-contention A/B

```yaml
checkpoint_id: CP-018
recorded_at: 2026-08-27T00:27:16+08:00
smoke_id: SMOKE-002
status: PLANNED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_checkpoint: 17dd8fd15bdf6d8f0bf37445a7b5c0af729b0b23
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
problem: EXP-016 exceeded the 30 s startup budget after Open3D preflight but before ROS runtime construction returned.
empty_graph_control:
  - Fresh-process probes in legal domains 224, 225, and 226 all exited zero with total construction 6.686 to 6.782 s.
  - Open3D import used 3.303 to 3.384 s and rclpy create_node used 2.847 to 2.872 s; no other segment exceeded 0.25 s.
  - Fast DDS rejects domains above 232, so 233 through 235 are invalid diagnostic attempts and may not be reused for qualification.
hypothesis: A live MuJoCo camera/physics plus MoveIt/controller stack causes CPU or thread contention that stretches one measured Open3D/ROS construction segment past 30 s.
single_variable: Run the same staged timing probe in the same ROS domain while the exact installed base stack is live; do not start rgbd_cup_pose, dynamic_cup_pick_place, or any pick-place workflow.
identity:
  domain: 227
  session: mac-mrc010-runtime-contention-r1
  tmux: mrc010-mac-runtime-contention-r1
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/runtime-contention-r1
method:
  - Start exact installed base MuJoCo stack with headless=false and explicit in-pane cwd.
  - Wait for ABI-aligned plugins, all three controllers, and Planning Scene READ_BACK.
  - Run the frozen timing probe in the same domain with a 120 s external bound; record segment JSON and rc.
  - Send one SIGINT only to the exact owned base-stack tmux and prove bounded cleanup.
success_criteria: The A/B identifies whether Open3D import, ROS API load, rclpy init, create_node, TF listener, publisher, or subscriptions accounts for the EXP-016 overrun.
failure_criteria: No segment reproduces the overrun; retain the result and reject the contention hypothesis rather than changing timeout.
decision: COMMIT_PLAN_THEN_RUN_NON_QUALIFYING_AB
next_experiment: SMOKE-002
```

## CP-019 / TRANS-SMOKE-002-RUNNING-001 — Start runtime-contention A/B

```yaml
checkpoint_id: CP-019
transition_id: TRANS-SMOKE-002-RUNNING-001
recorded_at: 2026-08-27T00:28:28+08:00
smoke_id: SMOKE-002
from: PLANNED
to: RUNNING
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 6892c87bcfff4e38fc184b5a90c59f0ad020d5fa
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
pre_running_observed:
  - Domain 227/session process identity, mrc010-mac-runtime-contention-r1, exact Viewer title, and diagnosis evidence path are empty.
  - Worktree is clean; installed candidate prefixes remain frozen and SMOKE-001's ABI-aligned plugin is unchanged.
  - Base runner and timing probe pass syntax/readback; SHA256 values are 41d02e347ff3982d35afc8707e4119e1f3888e2f61b0b67d335bc9360425727e and a0e6083edc8953a73562e80ad7da5871579e01aaf584c9ec2160ee50f6566d91.
owned_processes: NONE
decision: START_NON_QUALIFYING_BASE_STACK_AB
next_command: Commit transition, start exact-owned base stack with explicit cwd, wait for all readiness markers, run same-domain timing probe under 120 s bound, then exact SIGINT cleanup.
```

## CP-020 / CLOSE-SMOKE-002-001 — Live stack amplifies but does not alone exhaust startup budget

```yaml
checkpoint_id: CP-020
transition_id: CLOSE-SMOKE-002-001
recorded_at: 2026-08-27T00:33:24+08:00
smoke_id: SMOKE-002
from: RUNNING
to: PASS_DIAGNOSTIC
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: cad4f4f84c8e43de3b7eae5ee9797f7a7a8c61e4
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
control_result:
  - Three fresh-process empty-graph probes in domains 224 through 226 exited zero at 6.686, 6.691, and 6.782 s total.
  - Domains 233 through 235 are invalid because Fast DDS rejects domain IDs above 232; no product conclusion uses them.
live_stack_result:
  - Exact candidate camera/support plugins, all three controllers, MoveIt, and Planning Scene reached steady-state READ_BACK in domain 227.
  - The same-domain probe exited zero under its 120 s bound at 17.142 s, a 2.56x slowdown but still below the 30 s product startup deadline.
  - Open3D import grew from 3.318 to 9.010 s (2.72x) and rclpy create_node from 2.847 to 6.821 s (2.40x); other individual resource segments remained below 0.50 s.
  - During the probe ros2_control_node used about 146 to 149% CPU, move_group about 24 to 25%, WindowServer about 35%, and an unrelated preserved VS Code helper about 99 to 100%.
inference:
  - Live stack CPU/thread contention is real and explains much of EXP-016's reduced margin, but a steady-state stack plus one probe does not reproduce the >30 s failure.
  - The remaining product-only variable is simultaneous scene-success startup of rgbd_cup_pose and dynamic_cup_pick_place; launch sequencing/concurrent startup must be tested before changing timeout.
shutdown:
  - One SIGINT was sent only to the exact owned base tmux. Controller/RobotSystem teardown, move_group ordered shutdown, robot_state_publisher, and ros2_control_node all completed cleanly.
  - Domain 227/session/tmux/Viewer residue is absent; unrelated sessions/processes were preserved.
  - Ctrl-C ended the pane before wrapper exit files were written; component clean exits and absence readback are claimed, not a wrapper rc.
evidence:
  owner: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/runtime-contention-r1/owner.txt
  owner_sha256: 1f231c3dd77ef5d8dd69802a9b6787ed8024a293b07846f0bde2eba20b4ea87a
  base_log: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/runtime-contention-r1/base-stack.log
  base_log_sha256: 23b4e9d2b172da9533d131580363de6af687a7b2726c32e9e0ad59523f86c567
  timing: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/runtime-contention-r1/timing-result.txt
  timing_sha256: caa1fc2412c49633ed8149366f1a58ede2c0f303ed75854e775863e057600126
decision: RETAIN_RESULT_AND_PLAN_CONCURRENT_STARTUP_AB
next_experiment: NONE
```

## CP-021 — Plan scene-success concurrent-startup A/B

```yaml
checkpoint_id: CP-021
recorded_at: 2026-08-27T00:34:41+08:00
smoke_id: SMOKE-003
status: PLANNED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_checkpoint: 49a0e3a8f01bc16a045951cd166f46bdcd2d7bf2
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
hypothesis: With the live stack already reducing runtime-construction margin to 17.14 s, simultaneous startup of dynamic_cup_pick_place at scene success supplies the remaining contention that can push rgbd_cup_pose construction past 30 s.
single_variable: At steady-state Scene READ_BACK, start the frozen timing probe and exact installed dynamic_cup_pick_place on one barrier; retain the same low-rate GUI polling coordinator shape that was active in EXP-016.
identity:
  domain: 228
  session: mac-mrc010-concurrent-startup-r1
  tmux: mrc010-mac-concurrent-startup-r1
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/concurrent-startup-r1
dynamic_scope:
  - backend mujoco, mode execute, execute flag, scene_source observe_only, expected reset epoch zero.
  - No /cup_pose publisher is started, so dynamic can only construct its source and wait; it cannot plan or move.
  - Dynamic timeout/exit due absent /cup_pose is expected diagnostic behavior, not a product result.
method:
  - Start exact installed base stack headless=false; wait for both plugins, all controllers, and Planning Scene READ_BACK.
  - Barrier-start timing probe plus installed dynamic wait, capture their separate stdout/stderr/rc/wall time, CPU snapshots, and impose a 120 s observer bound.
  - Stop polling coordinator and base stack by exact owned identity, then prove domain/session/tmux/Viewer cleanup.
decision_rule:
  - If timing construction exceeds 30 s, concurrent scene-success startup reproduces the EXP-016 boundary and launch sequencing needs a TDD fix: start perception earlier while leaving dynamic scene-gated.
  - If it stays below 30 s, reject this reproduction and do not change timeout or launch sequencing without a new discriminating RED.
decision: COMMIT_PLAN_THEN_RUN_CONCURRENT_AB
next_experiment: SMOKE-003
```

## CP-022 / TRANS-SMOKE-003-RUNNING-001 — Start concurrent-startup A/B

```yaml
checkpoint_id: CP-022
transition_id: TRANS-SMOKE-003-RUNNING-001
recorded_at: 2026-08-27T00:36:21+08:00
smoke_id: SMOKE-003
from: PLANNED
to: RUNNING
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: cf0b45fe36ab6c578a90fd110d254c028ace9a19
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
pre_running_observed:
  - Domain 228/session process identity, task tmux, exact Viewer, and diagnosis evidence path are empty.
  - Worktree is clean; base, barrier-orchestrator, and GUI polling helpers pass syntax checks with SHA256 7f9b74a7, c63e948a, and bf207075.
  - A shell-level python command was unavailable before activating the frozen venv; the venv interpreter syntax check is GREEN and no diagnostic state was created by that observer error.
owned_processes: NONE
decision: START_NON_QUALIFYING_CONCURRENT_AB
next_command: Commit transition; start base/capture; wait Scene READ_BACK; barrier-start timing plus installed dynamic wait; exact cleanup.
```

## CP-023 / CLOSE-SMOKE-003-001 — Concurrent dynamic startup does not reproduce the deadline overrun

```yaml
checkpoint_id: CP-023
transition_id: CLOSE-SMOKE-003-001
recorded_at: 2026-08-27T00:43:32+08:00
smoke_id: SMOKE-003
from: RUNNING
to: PASS_DIAGNOSTIC_HYPOTHESIS_REJECTED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 235608efdab55f02369aa53e1f44cd07afd048fd
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
readiness:
  - Exact candidate camera/support plugins, all three controllers, MoveIt, and Planning Scene reached READ_BACK success in legal domain 228.
  - The low-rate exact-Viewer GUI coordinator captured its baseline and remained active across the barrier, matching EXP-016's observer shape.
barrier_result:
  - The frozen timing probe and exact installed dynamic_cup_pick_place process started 0.004321 s apart.
  - Timing probe exited zero: 18.331570 s internal and 20.710140 s wall; Open3D import used 9.617970 s and create_node used 7.309310 s.
  - The installed dynamic process constructed successfully and exited one only at the expected CUP_POSE_TIMEOUT because this diagnostic intentionally provided no /cup_pose; it ran 52.719200 s and never planned or moved.
  - No observer timeout occurred. CPU load remained high: ros2_control about 134 to 137%, preserved unrelated Code helper about 96 to 97%, move_group about 23 to 24%, and WindowServer about 35% before the barrier.
inference:
  - Same-barrier dynamic startup did not push runtime construction beyond the 30 s deadline, so this hypothesis does not reproduce EXP-016.
  - This result does not authorize changing launch sequencing or the timeout. The next diagnostic must exercise the real installed rgbd_cup_pose entrypoint and split the actual deadline-covered phases.
shutdown:
  - SIGINT was sent only to exact task-owned GUI helper PID 69883 and exact tmux mrc010-mac-concurrent-startup-r1.
  - Controller/RobotSystem teardown, move_group ordered shutdown, robot_state_publisher, and ros2_control_node completed cleanly.
  - Exact PIDs 69883, 69874, 69878, 69873, 71764, and 71765 are absent; task tmux is absent; unrelated tmux sessions remain preserved.
  - The base wrapper pane ended before wrapper exit files were written; component clean exits and absence readback are claimed, not a wrapper rc.
evidence:
  owner: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/concurrent-startup-r1/owner.txt
  owner_sha256: 17d4231a6cc1f35e30fd6f017216c000cf067b84f923dffdbd36ad4d283f9e72
  base_log: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/concurrent-startup-r1/base-stack.log
  base_log_sha256: c659cd0291164f490c0d15c876d1cd63fcfcdfe8ed65c801dae5ff93d1bc975b
  barrier_result: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/concurrent-startup-r1/barrier-result.txt
  barrier_result_sha256: 65629c7feedc52487d028af2b810a0609572c0d411aea1414154f009b89e7cd8
  baseline_manifest: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/concurrent-startup-r1/gui/baseline-helper/20260827T003740-a00000095a6d/manifest.json
  baseline_png: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/concurrent-startup-r1/gui/baseline-helper/20260827T003740-a00000095a6d/window.png
decision: RETAIN_RESULT_AND_PLAN_REAL_INSTALLED_RGBD_ENTRYPOINT_AB
next_experiment: NONE
```

## CP-024 — Plan real installed rgbd_cup_pose entrypoint A/B

```yaml
checkpoint_id: CP-024
recorded_at: 2026-08-27T00:45:23+08:00
smoke_id: SMOKE-004
status: PLANNED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_checkpoint: 0ef545585ef417985911c62a4cd11a9d13125d41
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
problem: Staged probes reproduce the heavy Open3D/import/create-node path in 17 to 18 s, but they do not execute the actual installed CLI, RosRuntime class construction, callbacks, TF lookup, point-cloud path, or the shared 30 s first-valid deadline that failed in EXP-016.
hypothesis: One omitted real-entrypoint phase, rather than dynamic startup alone, exhausts the remaining deadline margin on the live MuJoCo stack.
frozen_scope:
  - Use only the installed candidate at implementation commit 74a6523; do not rebuild, source-import, or change production code.
  - Invoke ros2 run so101_demo_py rgbd_cup_pose with the exact formal-launch parameters: 30.0 s startup timeout, /cup_pose, run-owned cup.ply and summary.json, and use_sim_time true.
  - Do not start dynamic_cup_pick_place; this diagnostic cannot plan or move the robot.
identity:
  empty_domain: 219
  empty_session: mac-mrc010-real-rgbd-empty-r1
  live_domain: 218
  live_session: mac-mrc010-real-rgbd-live-r1
  live_tmux: mrc010-mac-real-rgbd-live-r1
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-entrypoint-r1
method:
  - Empty control first: run the exact installed entrypoint in an otherwise empty legal domain. Expected result is runtime construction below 30 s followed by the explicit no-valid-RGB-D timeout, not a construction timeout.
  - Stop on any valid empty-control construction failure and retain stdout/stderr/ROS logs.
  - Live A/B only after the control passes: start exact candidate MuJoCo base stack, both formal static TF publishers, GUI baseline polling, all controllers, MoveIt, and Planning Scene READ_BACK; then start the same exact installed entrypoint.
  - A live PASS requires first summary.json/cup.ply and a valid /cup_pose publication before 30 s. A construction timeout or first-valid timeout is the first valid failure and ends the A/B.
  - Retain a separate read-only staged timing record for Buffer/TransformListener/QoS/publisher/three subscriptions comparison; it does not replace the real entrypoint result.
cleanup: Send signals only to exact recorded observer/static-TF/base tmux identities; preserve unrelated processes, windows, and tmux sessions.
decision: COMMIT_PLAN_THEN_RUN_EMPTY_CONTROL
next_experiment: SMOKE-004
```

## CP-025 / TRANS-SMOKE-004-RUNNING-001 — Start real installed RGB-D empty control

```yaml
checkpoint_id: CP-025
transition_id: TRANS-SMOKE-004-RUNNING-001
recorded_at: 2026-08-27T00:50:16+08:00
smoke_id: SMOKE-004
from: PLANNED
to: RUNNING
phase: EMPTY_CONTROL
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: a806e15c49c23b3d3aa15cd2060192686b49dacd
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
pre_running_observed:
  - Legal domains 219 and 218 contain no ROS nodes with daemon use disabled; session/process identities, task tmux, exact Viewer, and the registered diagnosis path are empty.
  - Candidate prefixes resolve to project-install so101_demo_py/support and fork-install mujoco_ros2_control; installed bundle SHA256 is e2d777dfa2d925998583b8c1b376f063ec47f476d98402297701b541da455175.
  - Empty/base/static-TF/perception helpers have task-owned paths and syntax/readback; their SHA256 values are cb79439d, 42a53e25, c30bf0bf, and c2dd5fde.
  - A read-only syntax observer printed macOS nice permission warnings for background static-TF lines; exact process readback proved it started no process and created no diagnosis state.
owned_processes: NONE
decision: RUN_EMPTY_CONTROL_AND_STOP_ON_CONSTRUCTION_FAILURE
next_command: Start exact installed rgbd_cup_pose in domain 219 with formal 30 s parameters; retain natural result before considering live A/B.
```

## CP-026 / CLOSE-SMOKE-004-001 — Reject helper-expanded ROS parameter token

```yaml
checkpoint_id: CP-026
transition_id: CLOSE-SMOKE-004-001
recorded_at: 2026-08-27T00:52:00+08:00
smoke_id: SMOKE-004
from: RUNNING
to: INVALID_RUNNER
phase: EMPTY_CONTROL
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_transition: 85cecb547d1310916aa48d2c4d49eb9e2bf4044f
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
observed:
  - The generated owner command proves zsh expanded the unquoted token use_sim_time:=true to use_sim_time:/usr/bin/true.
  - rclpy rejected that malformed parameter override before rgbd_cup_pose entered product setup; wrapper rc was one after 2.107121459 s.
  - No construction, callback, TF, point-cloud, or deadline inference is valid from this run.
classification_basis: This is a deterministic task-helper quoting defect outside the frozen installed implementation and formal launch token semantics.
cleanup:
  - The malformed process exited naturally; domain 219 readback contains no nodes and no task tmux/Viewer was created.
  - The invalid evidence remains retained and will not be overwritten or reused.
evidence:
  root: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-entrypoint-r1/empty
  owner_sha256: b9e2de234f10ce58dd2fafe8a850464fa4c781443d59d464a8b18dbfe0524964
  stdout_sha256: 61a0fdb70abd07ba5f495131693f8f612162ee16b27dfdc490a9281e28fad719
  stderr_sha256: 98c4e3ce09db4e5180bafa1e47debc179d5e5b0b5c301d1d25a76829be73be70
decision: RETAIN_INVALID_AND_REPEAT_WITH_QUOTED_TOKEN_FRESH_IDENTITY
next_experiment: NONE
```

## CP-027 — Plan corrected-token real installed RGB-D A/B

```yaml
checkpoint_id: CP-027
recorded_at: 2026-08-27T00:54:11+08:00
smoke_id: SMOKE-005
status: PLANNED
qualification: false
implementation_commit: 74a65234551527fb5483366aa06a79a8f5efacfe
record_head_before_checkpoint: 87e7f710139559480d01e6c65bc3dd889bc0df62
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
prior_invalid: SMOKE-004
single_variable: Quote the zsh array token as use_sim_time:=true so it reaches rclpy unchanged; formal launch semantics, installed executable, 30 s timeout, and all product parameters remain identical.
identity:
  empty_domain: 217
  empty_session: mac-mrc010-real-rgbd-empty-r2
  live_domain: 216
  live_session: mac-mrc010-real-rgbd-live-r2
  live_tmux: mrc010-mac-real-rgbd-live-r2
  evidence: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-diagnosis/real-rgbd-entrypoint-r2
helpers:
  empty_sha256: 8129326df523fc5791031bc5049758240f815db0926899f3bbde86d0afe24d09
  base_sha256: 5ca739935378b905b4a9e4415df8094b540887d7bf5f6b66d415d5d8a17d33f9
  static_tf_sha256: fe3098a8836f95737cbab90ca44fa8460940cc9bebe07848cf53ca3a0e1fac8d
  perception_sha256: 99311773950a7c3a9b1eee1cf8b232349c13451cc45a022c1edff5b45e9da652
decision_rule:
  - Empty control must enter the real installed node and end only with the expected no-valid-RGB-D timeout; a construction timeout is a valid failure and stops the A/B.
  - Only after that control passes may the fresh live identity run. Live first-valid summary/cup.ply before 30 s is PASS_DIAGNOSTIC; either real deadline timeout is the first valid failure.
decision: COMMIT_PLAN_THEN_PREFLIGHT_FRESH_IDENTITY
next_experiment: SMOKE-005
```
