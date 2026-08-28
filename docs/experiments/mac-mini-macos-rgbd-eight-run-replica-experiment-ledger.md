---
task_id: so101-mac-mini-macos-rgbd-eight-run-replica-20260828
goal: Replicate the current Mac moveit-demo runtime on mac-mini and qualify RGB-D perception-driven pick-place at four frozen cup positions in both headless and visible Viewer modes.
success_contract: Eight VALID FULL_RESTART runs, one per headless-mode and keyframe pair; each must prove installed provenance, synchronized 640x480 rgb8/32FC1/camera-info processing, /cup_pose, DONE with 19 transitions, physical final-placement evidence, clean exit, and no owned runtime residue. Visible runs also require a fresh exact MuJoCo window capture.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo
branch: main
base_commit: 00608c6085287cd6278c4582473d98e4df8e9086
current_commit: f0677823d7bc25268b30b690ef8bc8665787407f
evidence_root: /tmp/so101-debug-mac-mini-rgbd-replica-20260828
confirmed_conclusions:
  - Orchestrator and Gitee main are e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4 with child 71bc9346cf93d6227a6678fcacf63f3e18acfcba (EXP-301 preflight).
  - mac-mini main is clean at 00608c6085287cd6278c4582473d98e4df8e9086 with clean child 738e304551b4ea6db020b466086a13db71b65607 (EXP-301 preflight).
  - No MuJoCo, MoveIt, perception, Teleop, RViz, or Gazebo runtime was active on mac-mini during preflight (EXP-301 preflight).
  - mac-mini fast-forwarded to e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4 and materialized child 71bc9346cf93d6227a6678fcacf63f3e18acfcba without modifying preserved tmux session 0 (EXP-301).
  - mac-mini rebuilt the locked MuJoCo 3.4.0 vendor and eight-package project dependency closure; installed prefixes resolve to the project install, CTest passed 7+10+1 tests, and so101_demo_py passed 553 tests (EXP-302).
  - The mac-mini ROS Python environment now imports Open3D 0.19.0, NumPy 2.4.6, scikit-learn 1.9.0, and SciPy 1.17.1; an Open3D DBSCAN smoke test and rclpy import both pass (CP-303).
  - All eight headless/keyframe pairs independently passed the functional RGB-D and physical workflow contract: 640x480, positive point counts, perceived planar error below 2 mm, DONE with 19 transitions, final table contact, exit zero, and empty owned-process residue (EXP-313, EXP-304 through EXP-310, and EXP-314).
  - The four headless=true runs are VALID and each reports successful CGL initialization.
  - The four headless=false runs expose one exact 1706x992 ros2_control_node Viewer window, but cannot be marked VALID because macOS TCC rejects SSH-initiated exact-window capture.
  - EXP-316 proved exact Viewer Accessibility mapping and AXRaise; only Screen Recording in the SSH responsibility context remains blocked.
  - After authorizing `/usr/libexec/sshd-session`, the patched original helper captured and manifested exact Ghostty window 533; SSH Screen Recording is now available (EXP-318).
  - Four authorized visible replacement runs are VALID: task_start EXP-324, forward EXP-326, left EXP-327, and right EXP-329. Each reached DONE/19, retained exact Viewer outcome evidence, exited zero, and left no owned process residue.
  - The final source sync fast-forwarded mac-mini to f0677823d7bc25268b30b690ef8bc8665787407f; the delta from the runtime-qualified e6ab8c1 contains only SO-101 dependency documentation and experiment ledgers, while the locked child remains 71bc9346cf93d6227a6678fcacf63f3e18acfcba.
disproven_routes:
  - An SSH or task-owned tmux child cannot foreground/capture the Viewer without mac-mini Accessibility and Screen Recording authorization.
  - Enabling the `sshd-keygen-wrapper` Screen Recording switch does not take effect in the current Remote Login responsibility context, including two fresh SSH connections (post-EXP-316 probe).
open_hypotheses: []
latest_checkpoint: CP-309
next_experiment: NONE
---

# mac-mini macOS RGB-D eight-run replica ledger

## Frozen matrix

| Experiment | Headless | Lifecycle | Keyframe | Expected cup XYZ | ROS domain | GZ partition | Session |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EXP-313 | `true` | `FULL_RESTART` | `task_start` | `(0.02, -0.28, 0.165)` | 221 | `so101_macmini_rgbd_exp313` | `macmini-rgbd-exp313-headless-task-start` |
| EXP-304 | `true` | `FULL_RESTART` | `cup_test_forward_5cm` | `(0.02, -0.33, 0.165)` | 212 | `so101_macmini_rgbd_exp304` | `macmini-rgbd-exp304-headless-forward` |
| EXP-305 | `true` | `FULL_RESTART` | `cup_test_left_5cm` | `(-0.03, -0.28, 0.165)` | 213 | `so101_macmini_rgbd_exp305` | `macmini-rgbd-exp305-headless-left` |
| EXP-306 | `true` | `FULL_RESTART` | `cup_test_right_5cm` | `(0.07, -0.28, 0.165)` | 214 | `so101_macmini_rgbd_exp306` | `macmini-rgbd-exp306-headless-right` |
| EXP-314 | `false` | `FULL_RESTART` | `task_start` | `(0.02, -0.28, 0.165)` | 222 | `so101_macmini_rgbd_exp314` | `macmini-rgbd-exp314-visible-task-start` |
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

## EXP-304 through EXP-314 - eight qualifying FULL_RESTART candidates

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

## EXP-312 - invalid dynamic-loader precondition

```yaml
experiment_id: EXP-312
status: INVALID
prior_experiment: EXP-311
hypothesis: The dependency-complete installed runtime performs the headless task_start workflow.
prediction: The controller loads the rebuilt MuJoCo plugin and reaches live RGB-D perception.
single_variable: Added exact perception Python dependencies
lifecycle: FULL_RESTART
preconditions:
  - CP-303 is current.
success_criteria:
  - The runtime reaches the live perception and motion contract.
failure_criteria:
  - A dependency-complete runtime reaches a product failure.
invalid_criteria:
  - The dynamic loader cannot resolve a declared native runtime dependency.
provenance:
  source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 220
  gz_partition: so101_macmini_rgbd_exp312
commands:
  - command: run_full_restart.zsh EXP-312 true task_start 220 so101_macmini_rgbd_exp312 macmini-rgbd-exp312-headless-task-start
    exit_code: 1
observed:
  - controller_manager could not load libmujoco_ros2_control.dylib because @rpath/libmujoco.3.4.0.dylib was absent from the effective loader path.
  - RGB-D then timed out as a downstream symptom; no physical action occurred and processes-after.txt is empty.
inferred:
  - The current Mac runtime also depends on its macos_dylib_farm/current fallback, which was absent on mac-mini.
conclusion: No product conclusion; reproduce the effective current-Mac dylib selection and prove plugin dlopen before replacement EXP-313.
evidence:
  - /tmp/so101-debug-mac-mini-rgbd-replica-20260828/full-restart/EXP-312
decision: REPEAT
next_experiment: EXP-313
```

## EXP-313, EXP-304, EXP-305, and EXP-306 - headless matrix results

| Experiment | Keyframe | Perceived XYZ | Full/cup points | Result | Final XY error | Residue | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EXP-313 | task_start | `(0.019499, -0.280405, 0.165)` | 98078 / 141 | `DONE`, 19 transitions, table contact | 0.002636 m | 0 | VALID |
| EXP-304 | cup_test_forward_5cm | `(0.019624, -0.330460, 0.165)` | 98078 / 168 | `DONE`, 19 transitions, table contact | 0.002473 m | 0 | VALID |
| EXP-305 | cup_test_left_5cm | `(-0.030362, -0.280587, 0.165)` | 98135 / 378 | `DONE`, 19 transitions, table contact | 0.002474 m | 0 | VALID |
| EXP-306 | cup_test_right_5cm | `(0.069633, -0.280513, 0.165)` | 98078 / 126 | `DONE`, 19 transitions, table contact | 0.002563 m | 0 | VALID |

Each run used 640x480 input, an independent domain/partition/session and FULL_RESTART,
reported `CGL: Successfully initialized headless OpenGL context`, exited zero, and
left an empty `processes-after.txt`.

## EXP-307 and EXP-314 - visible task_start visual-gate attempts

```yaml
experiment_id: EXP-307
status: INVALID
observed:
  - Functional task_start workflow passed with 640x480 RGB-D, DONE/19, final table contact, exit zero, and no residue.
  - Exact Viewer window 415 (ros2_control_node, 1706x992) was found, but the required Accessibility foreground operation hung without authorization and produced no image.
conclusion: Functional evidence is positive, but no visual qualification conclusion; replace with EXP-314 using the active Ghostty tmux GUI context.
decision: REPEAT
```

```yaml
experiment_id: EXP-314
status: INVALID_VISUAL_GATE
observed:
  - Functional task_start workflow passed with perceived XYZ (0.019499, -0.280405, 0.165), 98078/141 points, DONE/19, 0.002628 m final XY error, table contact, exit zero, and no residue.
  - Exact Viewer window 427 (ros2_control_node, 1706x992) was found.
  - Both task-owned tmux/JXA foreground capture and direct screencapture by exact window ID were denied by macOS TCC; no image was created.
conclusion: headless=false product/runtime behavior passed, but the strict exact-window visual gate remains unqualified.
decision: REPEAT_AFTER_TCC_PERMISSION
```

## EXP-308, EXP-309, and EXP-310 - visible shifted-keyframe results

| Experiment | Keyframe | Viewer window | Perceived XYZ | Full/cup points | Result | Final XY error | Functional | Visual gate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EXP-308 | cup_test_forward_5cm | 440, 1706x992 | `(0.019624, -0.330460, 0.165)` | 98078 / 168 | `DONE`, 19 transitions, table contact | 0.002499 m | PASS | BLOCKED: capture exit 1 |
| EXP-309 | cup_test_left_5cm | 445, 1706x992 | `(-0.030362, -0.280587, 0.165)` | 98135 / 378 | `DONE`, 19 transitions, table contact | 0.002499 m | PASS | BLOCKED: capture exit 1 |
| EXP-310 | cup_test_right_5cm | 457, 1706x992 | `(0.069633, -0.280513, 0.165)` | 98078 / 126 | `DONE`, 19 transitions, table contact | 0.002506 m | PASS | BLOCKED: capture exit 1 |

All three runs exited zero with empty process residue. Their exact window inventories,
capture stderr (`could not create image from window`), and capture exit status are retained
inside each experiment's `visual/` evidence child. Per the preregistered invalid criteria,
these runs are `INVALID_VISUAL_GATE` rather than VALID.

## CP-304 - functional matrix complete, visual gate blocked

```yaml
checkpoint_id: CP-304
last_valid_experiment: EXP-306
current_hypothesis: Granting mac-mini TCC permission permits four fresh visible replacement runs to satisfy the remaining exact-window gate.
working_tree_status: mac-mini parent and child match Gitee; only this task-owned untracked ledger is present
owned_processes: NONE
preserved_processes: unrelated tmux session 0
confirmed_conclusions:
  - Fresh aggregate verification accepted all eight functional runs: each has planar perception error below 2 mm, 640x480 input, positive point counts, DONE/19, final table contact, exit zero, and no owned residue.
  - Fresh tests passed plugin CTest 7/7, core CTest 10/10, support CTest 1/1, and so101_demo_py pytest 553/553.
  - Parent and origin/main both resolve e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4; the locked child resolves 71bc9346cf93d6227a6678fcacf63f3e18acfcba.
  - Only the original unrelated tmux session 0 remains.
disproven_routes:
  - Direct SSH capture and a task-owned tmux child cannot satisfy macOS Accessibility/Screen Recording without explicit user authorization in System Settings.
open_risks:
  - The four visible rows do not satisfy the exact-window visual gate and must not be reported as fully qualified.
  - The replicated dylib fallback contains 877 current-Mac selections, of which 303 absolute targets are absent at the same remote path; the task runtime resolves its tested closure through earlier environment-hook paths plus the verified MuJoCo fallback, but unrelated ROS applications are outside this qualification.
next_command: After the user grants macOS TCC permissions for the SSH/terminal capture context, allocate four new experiment IDs and repeat the visible matrix with exact-window screenshots.
```

## EXP-315 - post-authorization visible task_start replacement

```yaml
experiment_id: EXP-315
status: INVALID_VISUAL_GATE
prior_experiment: EXP-314
hypothesis: Granting Ghostty Screen Recording and Accessibility permissions allows its task-owned tmux child to raise and capture the exact MuJoCo Viewer window.
prediction: The exact Viewer-window capture command exits zero, produces a fresh nonempty PNG and valid manifest, and the unchanged task_start workflow still reaches DONE/19 with final table contact and clean shutdown.
single_variable: macOS TCC authorization for /Applications/Ghostty.app
lifecycle: FULL_RESTART
preconditions:
  - CP-304 is current and the user explicitly reports that Ghostty permissions are granted.
  - Parent e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4 and child 71bc9346cf93d6227a6678fcacf63f3e18acfcba remain selected.
  - No owned SO-101 or capture process is active; unrelated tmux session 0 remains preserved.
success_criteria:
  - Exact ros2_control_node Viewer window resolves once and task-owned tmux capture exits zero.
  - Manifest identifies the exact window and the fresh PNG is visually inspected at original resolution.
  - Perception is OK at 640x480 with positive points and planar error below 2 mm.
  - Dynamic workflow is DONE with 19 transitions, final table contact, exit zero, and no owned residue.
failure_criteria:
  - A dependency-complete runtime reaches a perception, motion, physical, placement, capture, or shutdown failure.
invalid_criteria:
  - Wrong source/overlay, duplicate stack, stale window ID/evidence, remaining GUI permission denial, or lifecycle contamination.
provenance:
  source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 223
  gz_partition: so101_macmini_rgbd_exp315
commands:
  - command: run_full_restart.zsh EXP-315 false task_start 223 so101_macmini_rgbd_exp315 macmini-rgbd-exp315-visible-task-start
    exit_code: 0
  - command: capture-gui.sh --local --window-id <fresh-id> --platform macos --output-root /tmp/so101-debug-mac-mini-rgbd-replica-20260828/full-restart/EXP-315/visual
    exit_code: 1
observed:
  - Exact Viewer window 547 (ros2_control_node, PID 31279, 1706x992) was found after Ghostty restart.
  - Functional task_start workflow passed with perceived XYZ (0.019499, -0.280405, 0.165), DONE/19, exit zero, and no process residue.
  - Capture no longer hung, but the helper's Accessibility mapping step returned osascript exit 1 before screencapture; no PNG or manifest was produced.
  - A post-run task-owned tmux probe successfully made Ghostty frontmost and enumerated one window, proving Accessibility authorization is active in that tmux context.
inferred:
  - The remaining failure is the Viewer CoreGraphics-to-Accessibility window mapping or AXRaise operation, not a blanket Ghostty Accessibility denial.
conclusion: Functional behavior passed; visual qualification remains invalid until a live Viewer probe identifies and resolves the exact mapping failure.
evidence:
  - /tmp/so101-debug-mac-mini-rgbd-replica-20260828/full-restart/EXP-315
decision: REPEAT
next_experiment: EXP-316
```

## EXP-316 - live exact-window mapping diagnostic and replacement

```yaml
experiment_id: EXP-316
status: INVALID_VISUAL_GATE
prior_experiment: EXP-315
hypothesis: With Ghostty Accessibility active, a live diagnostic of the exact Viewer exposes whether title, geometry, or AXRaise matching caused EXP-315 capture to fail, after which the exact window can be captured.
prediction: The live Viewer resolves to one Accessibility window, AXRaise succeeds, exact-ID screencapture produces a fresh PNG, and the unchanged task_start workflow reaches DONE/19 and clean shutdown.
single_variable: Instrumented live Accessibility mapping for the post-authorization Viewer
lifecycle: FULL_RESTART
preconditions:
  - EXP-315 functional contract passed and its post-run Ghostty Accessibility probe exited zero.
  - Parent and child source revisions remain frozen; no owned runtime process remains.
success_criteria:
  - Live diagnostic retains CoreGraphics and Accessibility title/geometry/action metadata for the exact Viewer.
  - The exact Viewer is raised and captured by window ID into a fresh nonempty PNG, then visually inspected.
  - Perception, DONE/19, final placement, exit zero, and no-residue gates pass unchanged.
failure_criteria:
  - A dependency-complete runtime or authorized exact-window capture reaches a product/capture failure.
invalid_criteria:
  - Stale window ID, ambiguous Accessibility match, permission denial, lifecycle contamination, or missing fresh image.
provenance:
  source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 224
  gz_partition: so101_macmini_rgbd_exp316
commands:
  - command: run_full_restart.zsh EXP-316 false task_start 224 so101_macmini_rgbd_exp316 macmini-rgbd-exp316-visible-task-start
    exit_code: 0
  - command: authorized live exact-window diagnostic and capture for the fresh Viewer ID
    exit_code: 1
observed:
  - Exact CoreGraphics Viewer window 578 mapped uniquely to Accessibility window `MuJoCo : so101_task_scene` at 427,112 with size 1706x992.
  - Accessibility foreground and AXRaise both succeeded; the window exposed the AXRaise action and it was performed.
  - Exact-ID screencapture still exited 1 with `could not create image from window`; a direct new-SSH probe against a live Ghostty window failed identically.
  - macOS displayed the requested Screen Recording authorization principal as `sshd-keygen-wrapper`, identifying the remaining TCC subject.
  - Functional task_start workflow passed with perceived XYZ (0.019499, -0.280405, 0.165), DONE/19, 0.002624 m final XY error, final table contact, exit zero, and no process residue.
inferred:
  - Ghostty Accessibility is active, but Screen Recording is not active for the SSH TCC responsibility chain represented by `sshd-keygen-wrapper`.
conclusion: Functional behavior passed and exact window targeting/raising is proven; visual qualification remains invalid pending Screen Recording enablement for `sshd-keygen-wrapper`.
evidence:
  - /tmp/so101-debug-mac-mini-rgbd-replica-20260828/full-restart/EXP-316
decision: REPEAT_AFTER_SSHD_SCREEN_RECORDING_PERMISSION
next_experiment: EXP-317
```

## CP-305 - Screen Recording switch enabled but current SSH context unchanged

```yaml
checkpoint_id: CP-305
last_valid_experiment: EXP-306
current_hypothesis: A fresh tmux server launched locally by authorized Ghostty will make exact-window Screen Recording available without restarting Remote Login.
working_tree_status: mac-mini parent and child match the frozen revisions; only this task-owned untracked ledger is present
owned_processes: NONE
preserved_processes: unrelated tmux session 0
confirmed_conclusions:
  - EXP-316 functionally passed and uniquely mapped/raised the exact Viewer; Accessibility is not the remaining boundary.
  - After the user enabled Screen Recording for `sshd-keygen-wrapper`, two fresh direct SSH attempts against exact Ghostty window 532 still returned `could not create image from window`.
  - A fresh invocation of the unchanged `capture-gui.sh --local --window-id 532` exited 1 in its `osascript` Accessibility mapping step before invoking `screencapture`; it created no PNG or manifest.
  - No SO-101, MoveIt, MuJoCo, perception, or capture process remains after the probes.
disproven_routes:
  - Merely reconnecting SSH after toggling the listed Screen Recording permission does not refresh the active Remote Login responsibility context.
open_risks:
  - Four fresh visible FULL_RESTART runs and exact Viewer screenshots remain outstanding.
  - Restarting Remote Login remotely would sever the administration channel, so it was not performed.
next_command: Record the permission principal shown by the fresh unchanged-helper probe, then choose the approved durable capture-agent design before preregistering EXP-317.
```

## EXP-317 - empty CoreGraphics title mapping smoke

```yaml
experiment_id: EXP-317
status: VALID
prior_experiment: EXP-316
hypothesis: The unchanged helper exits before Screen Recording because it requires an empty CoreGraphics title to equal Ghostty's nonempty Accessibility title.
prediction: Ignoring the Accessibility title only when the selected CoreGraphics title is empty will preserve unique PID/geometry matching, complete AXRaise, and advance the original helper to exact-ID screencapture.
single_variable: Empty CoreGraphics title fallback in the Accessibility mapping predicate
lifecycle: ISOLATED_STACK
preconditions:
  - Ghostty window 532 remains the only visible Ghostty CoreGraphics window.
  - No SO-101 runtime or task-owned capture process remains.
  - The helper regression test failed before the patch and passed after the minimal predicate change.
success_criteria:
  - The original capture-gui wrapper no longer exits from its osascript Accessibility mapping step.
  - The attempt either produces a valid exact-window PNG/manifest or reaches a direct Screen Recording denial, cleanly separating the next boundary.
failure_criteria:
  - The patched helper still fails before screencapture despite matching PID and geometry.
invalid_criteria:
  - Ghostty window identity or geometry changes between inventory and capture, or more than one Accessibility geometry match exists.
provenance:
  source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4 plus task-owned helper patch e80e0dfa
  install_overlay: NOT_APPLICABLE_GUI_HELPER
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.agents/skills/gui-capture/scripts/gui-capture.py
  helper_sha256: e80e0dfae8187074f27c1cf7d741fd3f42351d4e15389dc3faac48bd9a9beba5
  ros_domain_id: 225
  gz_partition: so101_macmini_rgbd_exp317_no_stack
commands:
  - command: python3 -m unittest discover -s .agents/skills/gui-capture/test -p test_gui_capture.py -k test_macos_focus_allows_unique_geometry_match_when_cg_title_is_empty
    exit_code: 0
  - command: capture-gui.sh --local --window-id <fresh-ghostty-id> --platform macos --output-root /tmp/so101-debug-mac-mini-rgbd-replica-20260828/empty-title-smoke/EXP-317
    exit_code: 1
observed:
  - RED failed because the original script lacked the empty-title fallback; GREEN passed after the one-predicate change, and the full gui-capture suite passed 15/15.
  - mac-mini's focused gui-capture Python suite passed 13/13 with helper SHA256 e80e0dfae8187074f27c1cf7d741fd3f42351d4e15389dc3faac48bd9a9beba5.
  - The patched original wrapper uniquely selected fresh Ghostty window 533 at 1405,360 with size 943x889, completed Accessibility mapping and AXRaise, and invoked exact-ID screencapture.
  - Exact-ID screencapture exited 1; the wrapper produced no PNG or manifest and left no capture process residue.
  - Two wrapper-only tests fail on mac-mini before exercising capture because its Bash 3.2 treats an expanded empty array as unbound under `set -u`; local Bash passed the complete 15/15 suite. This pre-existing portability issue is outside the approved empty-title patch.
inferred:
  - The empty-title mapping defect is fixed. Screen Recording authorization is now the first failing boundary.
conclusion: EXP-317 validly isolates and resolves the empty-title defect; the unchanged helper now reaches screencapture and fails closed at the independent TCC boundary.
evidence:
  - /tmp/so101-debug-mac-mini-rgbd-replica-20260828/empty-title-smoke/EXP-317
decision: KEEP
next_experiment: EXP-318
```

## CP-306 - empty-title mapping fixed; Screen Recording is first bad boundary

```yaml
checkpoint_id: CP-306
last_valid_experiment: EXP-317
current_hypothesis: With exact Accessibility mapping fixed, the remaining exact-window failure is solely the Screen Recording TCC responsibility context.
working_tree_status: local has task-owned gui-capture helper/test and experiment-ledger changes plus the preserved unrelated ai-station ledger; mac-mini has the same helper/test patch and task ledger
owned_processes: NONE
preserved_processes: unrelated mac-mini tmux session 0
confirmed_conclusions:
  - Empty CoreGraphics titles now fall back to unique same-PID geometry matching; nonempty titles remain strict and ambiguity remains fail-closed.
  - RED/GREEN and live A/B both prove the patched wrapper advances from osascript failure to direct screencapture invocation.
disproven_routes:
  - The current Ghostty capture failure is no longer caused by CoreGraphics-to-Accessibility title mismatch.
open_risks:
  - Screen Recording still rejects the SSH-owned exact-window capture; no PNG or manifest exists yet.
  - The mac-mini Bash 3.2 wrapper-test portability issue is separately retained and was not modified.
next_command: Record whether macOS displayed a Screen Recording prompt for the EXP-317 attempt, then choose an authorization-context refresh or the fixed-identity capture agent.
```

## EXP-318 - authorized exact Ghostty capture

```yaml
experiment_id: EXP-318
status: VALID
prior_experiment: EXP-317
hypothesis: Granting Screen Recording to `/usr/libexec/sshd-session` allows the patched original helper to complete exact-window capture over SSH.
prediction: A fresh SSH invocation returns zero and produces a valid manifest plus nonempty PNG for the unique Ghostty window.
single_variable: Screen Recording authorization for com.apple.sshd-session
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-317 proved Accessibility mapping and exact screencapture invocation.
  - No SO-101 runtime is active.
success_criteria:
  - Exact capture exits zero with matching window ID, manifest, and visually inspected PNG.
failure_criteria:
  - Authorized exact capture exits nonzero or produces invalid evidence.
invalid_criteria:
  - Stale or ambiguous identity, or desktop substitution.
provenance:
  source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4 plus task-owned helper patch e80e0dfa
  install_overlay: NOT_APPLICABLE_GUI_HELPER
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.agents/skills/gui-capture/scripts/gui-capture.py
  ros_domain_id: 226
  gz_partition: so101_macmini_rgbd_exp318_no_stack
commands:
  - command: manual SSH wrapper capture of the uniquely inventoried Ghostty window
    exit_code: 0
observed:
  - Manifest identifies macOS Aqua exact window 533 owned by Ghostty at 1405,360 with logical size 943x889.
  - PNG SHA256 is 85615bfbff849f9d0acd87f85fb931de974972bb6b0299fcd79dc88724e99663 and pixel dimensions are 2110x2002.
  - Original-resolution inspection shows one isolated, unobscured Ghostty window with title bar, tabs, and terminal prompt; it is not a desktop crop.
inferred:
  - Screen Recording TCC authorization now covers fresh SSH capture sessions.
conclusion: GUI permission and empty-title mapping prerequisites for visible Viewer qualification are valid.
evidence:
  - /tmp/so101-debug-mac-mini-rgbd-replica-20260828/manual-ghostty-capture-20260828-153757
decision: KEEP
next_experiment: EXP-319
```

## EXP-319 through EXP-322 - authorized visible replacement matrix

These replace the visually invalid EXP-314/308/309/310 runs. Product settings
remain frozen; only the repaired and authorized visual evidence context changes.
Each experiment uses FULL_RESTART plus an independent domain, partition,
session, ROS_HOME, ROS_LOG_DIR, and evidence child.

| Experiment | Prior | Keyframe | Expected cup XYZ | ROS domain | GZ partition | Session |
| --- | --- | --- | --- | --- | --- | --- |
| EXP-319 | EXP-314 | `task_start` | `(0.02, -0.28, 0.165)` | 227 | `so101_macmini_rgbd_exp319` | `macmini-rgbd-exp319-visible-task-start` |
| EXP-320 | EXP-308 | `cup_test_forward_5cm` | `(0.02, -0.33, 0.165)` | 228 | `so101_macmini_rgbd_exp320` | `macmini-rgbd-exp320-visible-forward` |
| EXP-321 | EXP-309 | `cup_test_left_5cm` | `(-0.03, -0.28, 0.165)` | 229 | `so101_macmini_rgbd_exp321` | `macmini-rgbd-exp321-visible-left` |
| EXP-322 | EXP-310 | `cup_test_right_5cm` | `(0.07, -0.28, 0.165)` | 230 | `so101_macmini_rgbd_exp322` | `macmini-rgbd-exp322-visible-right` |

```yaml
status: PLANNED
hypothesis: The installed runtime performs the selected RGB-D workflow and the authorized helper captures its exact Viewer outcome.
prediction: Perception processes synchronized 640x480 input with positive points and bounded pose error; workflow reaches DONE/19 with final table contact; fresh exact Viewer PNG/manifest evidence is retained and inspected; shutdown leaves no owned residue.
single_variable: Selected frozen keyframe; visual authorization context is fixed across replacements
lifecycle: FULL_RESTART
preconditions:
  - EXP-318 is VALID.
  - Parent e6ab8c1 and installed overlay remain frozen; helper SHA256 is e80e0dfa.
  - No prior task runtime remains; unrelated tmux session 0 is preserved.
success_criteria:
  - Perception status OK at 640x480 with positive points and planar error below 2 mm.
  - Dynamic manifest DONE with 19 transitions, final table contact, and bounded final XY error.
  - Runtime exits zero and processes-after.txt is empty.
  - Exact Viewer resolves once; at least one post-action PNG/manifest succeeds and is inspected at original resolution.
failure_criteria:
  - A valid runtime reaches a perception, motion, physical, placement, capture, or shutdown failure.
invalid_criteria:
  - Wrong source/overlay/helper, stale or ambiguous window, capture before any action only, duplicate stack, or lifecycle contamination.
provenance:
  source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  helper_sha256: e80e0dfae8187074f27c1cf7d741fd3f42351d4e15389dc3faac48bd9a9beba5
  ros_domain_id: FROM_MATRIX_ABOVE
  gz_partition: FROM_MATRIX_ABOVE
commands:
  - command: run_full_restart.zsh <experiment> false <keyframe> <domain> <partition> <session>
    exit_code: PENDING
  - command: task-owned exact Viewer capture watcher using patched original helper
    exit_code: PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - Corresponding EXP-319 through EXP-322 child below the registered evidence root
decision: PENDING
next_experiment: NEXT_MATRIX_ROW_OR_NONE
```

## CP-307 - authorized visible matrix ready

```yaml
checkpoint_id: CP-307
last_valid_experiment: EXP-318
current_hypothesis: Four fresh authorized visible replacements complete the original eight-run qualification.
working_tree_status: local and mac-mini contain task-owned gui-capture helper/test and ledger changes; unrelated local ai-station ledger remains preserved
owned_processes: NONE
preserved_processes: unrelated mac-mini tmux session 0
confirmed_conclusions:
  - Exact SSH capture now succeeds through the original helper and produces inspectable PNG/manifest evidence.
  - Functional headless and prior visible product behavior is already positive for all four keyframes.
disproven_routes:
  - Ghostty permission alone does not authorize SSH capture.
  - `sshd-keygen-wrapper` is not the live session binary; the active signed binary is `/usr/libexec/sshd-session` with identifier com.apple.sshd-session.
open_risks:
  - Four authorized Viewer outcome screenshots and corresponding fresh functional runs remain outstanding.
next_command: Run EXP-319 task_start as an isolated FULL_RESTART with the exact Viewer capture watcher.
```

## EXP-319, EXP-323, EXP-325, and EXP-328 - retained invalid diagnostics

```yaml
experiments:
  - id: EXP-319
    status: INVALID
    reason: The first watcher created the experiment root before the FULL_RESTART wrapper, so the wrapper failed closed before starting any runtime process.
  - id: EXP-323
    status: INVALID
    reason: The functional run passed, but the watcher treated early dynamic-manifest existence as completion; the last image was only simulation time 21.060 s and did not show the outcome.
  - id: EXP-325
    status: INVALID
    reason: ROS_DOMAIN_ID 233 exceeded the current Fast DDS port range; all ROS processes failed before the Viewer/action workflow started.
  - id: EXP-328
    status: INVALID
    reason: The functional right-keyframe run passed, but its last periodic frame still showed active gripper/cup contact and was not accepted as post-action visual evidence.
conclusion: All failures were preregistration, isolation, or visual-timing failures rather than product failures; each was superseded without deleting evidence.
decision: KEEP
```

## EXP-324, EXP-326, EXP-327, and EXP-329 - valid authorized visible replacements

| Experiment | Keyframe | Domain | Perceived XYZ | RGB-D points full/cup | Perception planar error | Final XY error | Exact outcome evidence |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- |
| EXP-324 | `task_start` | 232 | `(0.019499, -0.280405, 0.165)` | `98078 / 141` | `0.644 mm` | `2.622 mm` | window 706, capture 08/8, sim 61.182 s, SHA256 `5a546fd7667dbacafade06f2b320ed21a90690c0597af77cf700adf22dc0417d` |
| EXP-326 | `cup_test_forward_5cm` | 201 | `(0.019624, -0.330460, 0.165)` | `98078 / 168` | `0.594 mm` | `2.453 mm` | window 718, capture 09/9, sim 67.774 s, SHA256 `9ce60a7919748b5b06c8129e826966afca154f915338523696c58a9d3a2fa9ca` |
| EXP-327 | `cup_test_left_5cm` | 202 | `(-0.030362, -0.280587, 0.165)` | `98135 / 378` | `0.690 mm` | `2.499 mm` | window 730, capture 08/8, sim 60.530 s, SHA256 `224ef7d9f83eec437edaa5a268b9e7ac51143ef8dc6c43d9e4607cab8b6a09f6` |
| EXP-329 | `cup_test_right_5cm` | 204 | `(0.069633, -0.280513, 0.165)` | `98078 / 126` | `0.631 mm` | `2.538 mm` | window 754, status-DONE trigger, sim 68.796 s, SHA256 `9c8d79d2bac15c90dfd696f5912a54e1ab07960d767961a1d75b78ce6a63ded8` |

```yaml
status: VALID
prior_experiments: EXP-319 through EXP-328 as applicable
hypothesis: The installed runtime performs all four visible RGB-D workflows and the authorized SSH capture context retains exact post-action Viewer evidence.
prediction: Every run reaches synchronized 640x480 perception, DONE/19, valid final placement, exact outcome capture, exit zero, and empty owned residue.
single_variable: Frozen keyframe per row; EXP-329 adds a status-DONE exact-window trigger to close the visual timing gap found in EXP-328.
lifecycle: FULL_RESTART
provenance:
  runtime_source_commit: e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4
  final_checked_out_commit: f0677823d7bc25268b30b690ef8bc8665787407f
  source_delta_after_runtime_qualification: documentation_and_ledgers_only
  child_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  helper_sha256: e80e0dfae8187074f27c1cf7d741fd3f42351d4e15389dc3faac48bd9a9beba5
observed:
  - All four summaries report status OK, 640x480 input, positive full/cup points, and planar error below 1 mm.
  - All four dynamic manifests report status/current_state DONE, transition_count 19, final table contact true, empty attached-object IDs, and the cup restored in the planning-scene world.
  - All four wrappers and capture watchers exit zero; every processes-after.txt is empty.
  - Original-resolution 3636x2208 images were inspected. They show the cup at the red placement target; accepted terminal frames show an open, released gripper and a retreating or retreated arm.
conclusion: The authorized headless=false four-point matrix is valid and, together with EXP-313/304/305/306, completes the eight-run success contract.
evidence:
  - /tmp/so101-debug-mac-mini-rgbd-replica-20260828/full-restart/EXP-324
  - /tmp/so101-debug-mac-mini-rgbd-replica-20260828/full-restart/EXP-326
  - /tmp/so101-debug-mac-mini-rgbd-replica-20260828/full-restart/EXP-327
  - /tmp/so101-debug-mac-mini-rgbd-replica-20260828/full-restart/EXP-329
decision: KEEP
next_experiment: NONE
```

## CP-308 - eight-run matrix complete

```yaml
checkpoint_id: CP-308
last_valid_experiment: EXP-329
current_hypothesis: NONE; success contract satisfied
working_tree_status: mac-mini is at origin/main f067782 with task-owned gui-capture helper/test and this ledger modified; local additionally preserves the unrelated ai-station ledger modification
owned_processes: NONE
preserved_processes: unrelated mac-mini tmux session 0
confirmed_conclusions:
  - headless=true is VALID for all four frozen points (EXP-313 and EXP-304 through EXP-306).
  - headless=false is VALID for all four frozen points (EXP-324, EXP-326, EXP-327, and EXP-329).
  - Current checkout is synchronized to Gitee main and the post-runtime source delta is documentation-only.
disproven_routes:
  - Creating the evidence root from an auxiliary watcher before the FULL_RESTART wrapper.
  - Using ROS_DOMAIN_ID above 232 with this Fast DDS port configuration.
  - Treating dynamic-manifest existence or an arbitrary last periodic frame as proof of post-action state.
open_risks:
  - The gui-capture empty-title patch remains uncommitted and is not yet published.
next_command: NONE
```

## CP-309 - fresh aggregate completion verification

```yaml
checkpoint_id: CP-309
last_valid_experiment: EXP-329
verification:
  - Remote eight-run aggregate: PASS, 8 valid runs, exit 0.
  - Local gui-capture unittest discovery: 15/15 passed.
  - Remote focused gui-capture unittest discovery: 13/13 passed.
  - Remote git diff --check: exit 0.
  - Remote HEAD and origin/main: f0677823d7bc25268b30b690ef8bc8665787407f.
  - Remote locked child: 71bc9346cf93d6227a6678fcacf63f3e18acfcba.
  - Remote live owned PID file: zero bytes.
  - Preserved unrelated tmux session: session 0 remains present.
evidence:
  - /tmp/so101-debug-mac-mini-rgbd-replica-20260828/final-validation
decision: COMPLETE
next_command: NONE
```

## Evidence disposition

- Retained: build/provenance/test evidence; valid headless runs EXP-313 and EXP-304 through EXP-306; valid visible runs EXP-324, EXP-326, EXP-327, and EXP-329; valid capture diagnostics EXP-317 and EXP-318; functionally passing but visually invalid EXP-307, EXP-314 through EXP-316, EXP-323, EXP-328, and EXP-308 through EXP-310; invalid EXP-303, EXP-311, EXP-312, EXP-319, and EXP-325 diagnostic runs; recoverable pre-pull ledger backup and source-sync logs
- Archived: vendor-no-proxy-attempt (superseded but auditable partial dependency checkout)
- Deletion candidates: invalid EXP-303, EXP-311, EXP-312, EXP-319, and EXP-325 outputs; visually superseded EXP-307, EXP-323, and EXP-328; and the archived no-proxy attempt. No evidence may be deleted without explicit user authorization.
