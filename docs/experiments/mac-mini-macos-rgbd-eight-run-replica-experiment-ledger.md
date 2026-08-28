---
task_id: so101-mac-mini-macos-rgbd-eight-run-replica-20260828
goal: Replicate the current Mac moveit-demo runtime on mac-mini and qualify RGB-D perception-driven pick-place at four frozen cup positions in both headless and visible Viewer modes.
success_contract: Eight VALID FULL_RESTART runs, one per headless-mode and keyframe pair; each must prove installed provenance, synchronized 640x480 rgb8/32FC1/camera-info processing, /cup_pose, DONE with 19 transitions, physical final-placement evidence, clean exit, and no owned runtime residue. Visible runs also require a fresh exact MuJoCo window capture.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo
branch: main
base_commit: 00608c6085287cd6278c4582473d98e4df8e9086
current_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
evidence_root: /tmp/so101-debug-mac-mini-rgbd-replica-20260828
confirmed_conclusions:
  - Orchestrator and Gitee main are e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4 with child 71bc9346cf93d6227a6678fcacf63f3e18acfcba (EXP-301 preflight).
  - mac-mini main is clean at 00608c6085287cd6278c4582473d98e4df8e9086 with clean child 738e304551b4ea6db020b466086a13db71b65607 (EXP-301 preflight).
  - No MuJoCo, MoveIt, perception, Teleop, RViz, or Gazebo runtime was active on mac-mini during preflight (EXP-301 preflight).
  - mac-mini fast-forwarded to e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4 and materialized child 71bc9346cf93d6227a6678fcacf63f3e18acfcba without modifying preserved tmux session 0 (EXP-301).
  - mac-mini rebuilt the locked MuJoCo 3.4.0 vendor and eight-package project dependency closure; installed prefixes resolve to the project install, CTest passed 7+10+1 tests, and so101_demo_py passed 553 tests (EXP-302).
  - The mac-mini ROS Python environment now imports Open3D 0.19.0, NumPy 2.4.6, scikit-learn 1.9.0, and SciPy 1.17.1; an Open3D DBSCAN smoke test and rclpy import both pass (CP-303).
disproven_routes:
  - NONE
open_hypotheses:
  - The published parent and child can be fast-forwarded and built on mac-mini without overwriting user work.
  - The rebuilt installed runtime completes the frozen eight-run FULL_RESTART matrix.
latest_checkpoint: CP-303
next_experiment: EXP-312
---

# mac-mini macOS RGB-D eight-run replica ledger

## Frozen matrix

| Experiment | Headless | Lifecycle | Keyframe | Expected cup XYZ | ROS domain | GZ partition | Session |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EXP-312 | `true` | `FULL_RESTART` | `task_start` | `(0.02, -0.28, 0.165)` | 220 | `so101_macmini_rgbd_exp312` | `macmini-rgbd-exp312-headless-task-start` |
| EXP-304 | `true` | `FULL_RESTART` | `cup_test_forward_5cm` | `(0.02, -0.33, 0.165)` | 212 | `so101_macmini_rgbd_exp304` | `macmini-rgbd-exp304-headless-forward` |
| EXP-305 | `true` | `FULL_RESTART` | `cup_test_left_5cm` | `(-0.03, -0.28, 0.165)` | 213 | `so101_macmini_rgbd_exp305` | `macmini-rgbd-exp305-headless-left` |
| EXP-306 | `true` | `FULL_RESTART` | `cup_test_right_5cm` | `(0.07, -0.28, 0.165)` | 214 | `so101_macmini_rgbd_exp306` | `macmini-rgbd-exp306-headless-right` |
| EXP-307 | `false` | `FULL_RESTART` | `task_start` | `(0.02, -0.28, 0.165)` | 215 | `so101_macmini_rgbd_exp307` | `macmini-rgbd-exp307-visible-task-start` |
| EXP-308 | `false` | `FULL_RESTART` | `cup_test_forward_5cm` | `(0.02, -0.33, 0.165)` | 216 | `so101_macmini_rgbd_exp308` | `macmini-rgbd-exp308-visible-forward` |
| EXP-309 | `false` | `FULL_RESTART` | `cup_test_left_5cm` | `(-0.03, -0.28, 0.165)` | 217 | `so101_macmini_rgbd_exp309` | `macmini-rgbd-exp309-visible-left` |
| EXP-310 | `false` | `FULL_RESTART` | `cup_test_right_5cm` | `(0.07, -0.28, 0.165)` | 218 | `so101_macmini_rgbd_exp310` | `macmini-rgbd-exp310-visible-right` |

## CP-300 - preflight

```yaml
checkpoint_id: CP-300
last_valid_experiment: NONE
current_hypothesis: The clean mac-mini checkout can receive and qualify the published macOS headless CGL RGB-D runtime.
working_tree_status: orchestrator has one unrelated ai-station ledger plus this task ledger; mac-mini main and child clean
owned_processes: NONE
preserved_processes: existing unrelated tmux session 0
confirmed_conclusions:
  - Published target revisions and clean remote starting revisions are recorded above.
  - No relevant runtime stack is active on mac-mini.
disproven_routes:
  - NONE
open_risks:
  - mac-mini build/test and installed-runtime provenance are unverified.
  - Screen Recording and Accessibility permission for exact Viewer capture are unverified.
next_command: Fast-forward mac-mini main, update the locked child, and copy this registered ledger without touching existing tmux session 0.
```

## EXP-301 - source upgrade

```yaml
experiment_id: EXP-301
status: VALID
prior_experiment: NONE
hypothesis: The clean mac-mini checkout can fast-forward to the published parent and locked child revisions without overwriting user work.
prediction: Parent and child match the frozen revisions and remain clean except for this task-owned ledger.
single_variable: Published parent and child revisions
lifecycle: ISOLATED_STACK
preconditions:
  - mac-mini parent and child statuses are clean.
  - No task runtime stack is active.
success_criteria:
  - git pull --ff-only and recursive submodule update exit zero.
  - Parent and child revisions match the frozen target.
failure_criteria:
  - Non-fast-forward, dirty conflict, missing object, or submodule update failure.
invalid_criteria:
  - Any pre-existing user file, process, or tmux session is modified.
provenance:
  source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
  install_overlay: NOT_BUILT
  runtime_executable: NOT_BUILT
  ros_domain_id: 210
  gz_partition: so101_macmini_rgbd_exp301
commands:
  - command: git pull --ff-only origin main; git submodule sync --recursive; git submodule update --init --recursive
    exit_code: 0
observed:
  - Parent fast-forwarded from 00608c6085287cd6278c4582473d98e4df8e9086 to e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4.
  - Locked child updated from 738e304551b4ea6db020b466086a13db71b65607 to 71bc9346cf93d6227a6678fcacf63f3e18acfcba.
  - Remote status contains only this task-owned untracked ledger; unrelated tmux session 0 remains present.
inferred:
  - The published source candidate is ready for mac-mini build and installed-runtime qualification.
conclusion: Source upgrade completed without overwriting user work.
evidence:
  - /tmp/so101-debug-mac-mini-rgbd-replica-20260828/upgrade
decision: KEEP
next_experiment: EXP-302
```

## CP-301 - upgraded source

```yaml
checkpoint_id: CP-301
last_valid_experiment: EXP-301
current_hypothesis: The upgraded source builds and passes package/runtime provenance gates on mac-mini.
working_tree_status: mac-mini main has only the task-owned untracked ledger; child detached clean
owned_processes: NONE
preserved_processes: unrelated tmux session 0
confirmed_conclusions:
  - Parent and child source revisions match the published frozen target.
  - Upgrade logs and revision read-back are retained below the registered evidence root.
disproven_routes:
  - NONE
open_risks:
  - mac-mini build/test and exact installed prefixes are unverified.
  - GUI capture permissions remain unverified.
next_command: Rebuild the locked MuJoCo fork and project dependency closure using current repository scripts.
```

## EXP-302 - environment build, tests, and installed provenance

```yaml
experiment_id: EXP-302
status: VALID
prior_experiment: EXP-301
hypothesis: mac-mini can reproduce the locked ROS/MuJoCo dependency overlay and project install from the upgraded source.
prediction: Changed packages build, non-zero directed/package tests pass, and installed package prefixes and executable resolve to mac-mini's rebuilt overlay.
single_variable: Rebuilt installed environment from EXP-301 source
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-301 is VALID.
  - Build, test, ROS_HOME, and ROS_LOG_DIR evidence is registered below the single task root.
success_criteria:
  - Locked MuJoCo fork build/tests exit zero.
  - Project dependency closure build and relevant package tests collect non-zero tests and pass.
  - Installed parent/child manifests and package prefixes match the frozen revisions.
failure_criteria:
  - Compile, link, assertion, dependency-lock, or installed provenance failure.
invalid_criteria:
  - Tests or runtime resolve a stale fork or stale project install.
provenance:
  source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: PENDING_BUILD
  ros_domain_id: 210
  gz_partition: so101_macmini_rgbd_exp302
commands:
  - command: Build and test locked MuJoCo fork and project dependency closure using current repository scripts and zsh environment.
    exit_code: 0
observed:
  - Initial project build failed closed because mac-mini had no prepared MuJoCo staging; this was an environment precondition failure, not a source assertion failure.
  - The first vendor preparation attempt was archived after its GitHub clone had no proxy environment; rerunning with the existing local Xray SOCKS endpoint populated the locked dependencies.
  - mac-mini uses /Users/matianyi/ros2_jazzy/install as its actual ROS underlay, while the orchestrator uses /opt/ros/jazzy; the installer completed with SO101_ROS_UNDERLAY set to the live remote path.
  - The eight-package dependency closure built successfully from the frozen parent and child revisions.
  - Installed prefixes for mujoco_vendor, messages, plugins, core, support, and so101_demo_py all resolve below /Users/matianyi/Projects/robot_demo_001/moveit-demo/install.
  - CTest passed CameraPlugin 7/7, core 10/10, and support 1/1; direct package pytest imported rclpy from the remote Jazzy source install and passed 553/553.
inferred:
  - The mac-mini installed runtime now matches the source and locked dependency contract needed for the eight live runs.
conclusion: Build, tests, and installed provenance are valid; proceed to live FULL_RESTART qualification.
evidence:
  - /tmp/so101-debug-mac-mini-rgbd-replica-20260828/build
decision: KEEP
next_experiment: EXP-303
```

## CP-302 - installed candidate ready

```yaml
checkpoint_id: CP-302
last_valid_experiment: EXP-302
current_hypothesis: The rebuilt installed runtime completes all eight frozen FULL_RESTART runs.
working_tree_status: mac-mini source has only task-owned .envrc and ledger; child clean; build/install artifacts are ignored
owned_processes: NONE
preserved_processes: unrelated tmux session 0
confirmed_conclusions:
  - Source, locked child, MuJoCo staging, project install, runtime executable, and package tests are current and verified.
  - The no-proxy vendor attempt is retained under the registered root as an archived diagnostic batch.
disproven_routes:
  - Building mujoco_vendor before preparing MUJOCO_STAGE_ROOT cannot succeed.
  - Running the vendor installer with the orchestrator-only /opt/ros/jazzy default cannot succeed on mac-mini.
open_risks:
  - Live CGL rendering, physical workflow, visible Viewer, and exact-window capture are not yet verified on mac-mini.
next_command: Run EXP-303 headless task_start as an independent FULL_RESTART.
```

## EXP-303 through EXP-310 - eight FULL_RESTART runs

Each experiment is preregistered by the frozen matrix. Only `headless` and the
selected keyframe vary across the matrix; source, child, install overlay,
sensor rendering, motion policy, thresholds, and success contract remain
fixed. A run starts only after the previous owned process tree is gone.

```yaml
status: PLANNED
prior_experiment: EXP-302 for EXP-303; immediately preceding FULL_RESTART thereafter
hypothesis: The rebuilt installed runtime performs RGB-D perception-driven pick/place for the selected headless-mode and keyframe pair.
prediction: The renderer produces synchronized 640x480 rgb8/32FC1/camera-info data; perception emits a bounded /cup_pose; dynamic workflow reaches DONE with physical final-placement evidence and exits cleanly. Visible mode additionally exposes one capturable MuJoCo Viewer window.
single_variable: headless and mujoco_initial_keyframe as frozen by the matrix
lifecycle: FULL_RESTART
preconditions:
  - EXP-302 is VALID.
  - No prior task runtime process remains.
  - Unique ROS_DOMAIN_ID, GZ_PARTITION, session, ROS_HOME, ROS_LOG_DIR, and evidence child are active.
success_criteria:
  - Perception status is OK with 640x480 input and positive point counts.
  - Perceived XYZ is within 2 mm planar tolerance of the frozen keyframe position.
  - Dynamic manifest is DONE with 19 transitions and final-placement validation.
  - Runtime exits zero and no owned process remains.
  - For headless=false, exact Viewer-window capture succeeds and the fresh image is visually inspected.
failure_criteria:
  - Valid startup reaches a perception, planning, execution, physical, placement, visual, or shutdown failure.
invalid_criteria:
  - Wrong source/overlay, duplicate stack, stale evidence, GUI permission failure, or lifecycle contamination.
provenance:
  source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: PENDING_EXP302
  ros_domain_id: FROM_FROZEN_MATRIX
  gz_partition: FROM_FROZEN_MATRIX
commands:
  - command: ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=<mode> sensor_rendering:=true mujoco_initial_keyframe:=<keyframe> ...
    exit_code: PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - Child directory below the registered evidence root for the experiment ID
decision: PENDING
next_experiment: NEXT_ROW_OR_NONE
```

## EXP-303 - invalid wrapper preflight

```yaml
experiment_id: EXP-303
status: INVALID
prior_experiment: EXP-302
hypothesis: The installed runtime performs the headless task_start workflow.
prediction: The wrapper enters the installed ROS environment and starts the runtime.
single_variable: headless=true and mujoco_initial_keyframe=task_start
lifecycle: FULL_RESTART
preconditions:
  - EXP-302 is VALID.
success_criteria:
  - Runtime starts and the live success contract is evaluated.
failure_criteria:
  - A valid runtime reaches a product failure.
invalid_criteria:
  - Wrapper cannot enter the installed environment.
provenance:
  source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: NOT_STARTED
  ros_domain_id: 211
  gz_partition: so101_macmini_rgbd_exp303
commands:
  - command: run_full_restart.zsh EXP-303 true task_start 211 so101_macmini_rgbd_exp303 macmini-rgbd-exp303-headless-task-start
    exit_code: 127
observed:
  - The direct SSH shebang shell could not resolve direnv before ROS setup; no runtime process started.
inferred:
  - Wrapper PATH, not the product/runtime, invalidated the run.
conclusion: No product conclusion; replace with EXP-311 using the verified absolute direnv path.
evidence:
  - /tmp/so101-debug-mac-mini-rgbd-replica-20260828/full-restart/EXP-303
decision: REPEAT
next_experiment: EXP-311
```

## EXP-311 - invalid runtime dependency precondition

```yaml
experiment_id: EXP-311
status: INVALID
prior_experiment: EXP-303
hypothesis: The installed runtime performs the headless task_start workflow after the wrapper PATH correction.
prediction: The runtime reaches synchronized RGB-D perception and evaluates the live success contract.
single_variable: Absolute direnv path in the corrected wrapper
lifecycle: FULL_RESTART
preconditions:
  - EXP-302 is VALID.
  - No prior task runtime process remains.
success_criteria:
  - Runtime reaches the live perception and motion contract.
failure_criteria:
  - A dependency-complete runtime reaches a product failure.
invalid_criteria:
  - A declared Python runtime dependency is absent before perception can run.
provenance:
  source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 219
  gz_partition: so101_macmini_rgbd_exp311
commands:
  - command: run_full_restart.zsh EXP-311 true task_start 219 so101_macmini_rgbd_exp311 macmini-rgbd-exp311-headless-task-start
    exit_code: 1
observed:
  - The full stack started and Planning Scene setup succeeded, then rgbd_cup_pose failed closed with "Open3D is missing" before a cup pose or physical action.
  - The wrapper preserved the non-zero status and all owned runtime processes exited; processes-after.txt is empty.
inferred:
  - The source/build candidate is intact, but the mac-mini Python runtime did not yet reproduce the current Mac Open3D dependency.
conclusion: No product conclusion; install and smoke-test the exact current-Mac perception dependencies, then replace with EXP-312.
evidence:
  - /tmp/so101-debug-mac-mini-rgbd-replica-20260828/full-restart/EXP-311
decision: REPEAT
next_experiment: EXP-312
```

## CP-303 - perception dependency ready

```yaml
checkpoint_id: CP-303
last_valid_experiment: EXP-302
current_hypothesis: The dependency-complete installed runtime completes all eight frozen FULL_RESTART runs.
working_tree_status: mac-mini source has only the task-owned ledger; child clean; build/install artifacts and .envrc are ignored
owned_processes: NONE
preserved_processes: unrelated tmux session 0
confirmed_conclusions:
  - Open3D 0.19.0, scikit-learn 1.9.0, and SciPy 1.17.1 were installed into /Users/matianyi/ros2_jazzy/.venv from the TUNA index.
  - The resulting environment imports rclpy and Open3D and completes an in-memory Open3D DBSCAN smoke test.
  - NumPy remains 2.4.6; the Open3D dependency resolution upgraded pydantic from 1.10.26 to 2.13.4, which remains subject to live runtime qualification.
disproven_routes:
  - Source/build completion alone does not reproduce the perception runtime when Open3D is absent.
open_risks:
  - Live CGL rendering, physical workflow, visible Viewer, exact-window capture, and dependency compatibility under the full stack remain unverified.
next_command: Run replacement EXP-312 headless task_start as an independent FULL_RESTART.
```

## Evidence disposition

- Retained: build/provenance/test evidence plus invalid EXP-303 and EXP-311 diagnostic runs
- Archived: vendor-no-proxy-attempt (superseded but auditable partial dependency checkout)
- Deletion candidates: invalid EXP-303 and EXP-311 outputs and the archived no-proxy attempt; no evidence may be deleted without explicit user authorization
