# RGB-D Pick-Place on mujoco_ros2_control 0.1.0 Main Integration Ledger

```yaml
task_id: so101-rgbd-pick-place-mrc010-main
goal: Prove RGB-D-driven physical pick-place from all four MJCF cup keyframes on macOS and ai-station using child main@5e9d67c.
success_contract: Four independent FULL_RESTART successes on macOS, four independent FULL_RESTART successes on ai-station, plus one ai-station task_start repeat so the final fixed candidate has five consecutive valid live runs.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-pick-place-mujoco-0-1-main
branch: codex/rgbd-pick-place-mujoco-0-1-main
base_commit: b73748f86acc891711aa455fc911a9ebde52686d
current_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
implementation_commit: 208dd216f9ef52e2792830a19c1e070b8aef1778
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
open_hypotheses:
  - The tree-identical child-main merge commit preserves all qualified 0.1.0 runtime behavior after RGB-D integration.
  - The merged camera contract retains both 0.1.0 lifecycle and perception task-camera requirements.
  - The final installed candidate succeeds at all four positions on both platforms.
latest_checkpoint: CP-006
next_experiment: NONE
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
