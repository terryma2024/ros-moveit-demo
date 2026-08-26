# RGB-D Pick-Place on mujoco_ros2_control 0.1.0 Main Integration Ledger

```yaml
task_id: so101-rgbd-pick-place-mrc010-main
goal: Prove RGB-D-driven physical pick-place from all four MJCF cup keyframes on macOS and ai-station using child main@5e9d67c.
success_contract: Four independent FULL_RESTART successes on macOS, four independent FULL_RESTART successes on ai-station, plus one ai-station task_start repeat so the final fixed candidate has five consecutive valid live runs.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-pick-place-mujoco-0-1-main
branch: codex/rgbd-pick-place-mujoco-0-1-main
base_commit: b73748f86acc891711aa455fc911a9ebde52686d
current_commit: 6f40b480f4f0acdaa74946549e3643381750da52
target_child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
evidence_root: /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/
confirmed_conclusions:
  - OBS-001: child main@5e9d67c contains aeff7e5 and both commits have identical trees.
  - OBS-002: parent main@b73748f clean isolated-install baseline passed 303 of 303 so101_demo_py tests from /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-baseline-canonical.
  - OBS-003: origin/codex/rgbd-perception-pick-place@0649f3b retains prior four-position qualification, but those runs do not count for this new child-main candidate.
disproven_routes:
  - OBS-004: sourcing the parent checkout .envrc in a nested worktree selects the parent install and is not valid candidate provenance.
  - OBS-005: using non-canonical /tmp build paths on macOS makes installed manifest and ament prefix strings diverge.
open_hypotheses:
  - The tree-identical child-main merge commit preserves all qualified 0.1.0 runtime behavior after RGB-D integration.
  - The merged camera contract retains both 0.1.0 lifecycle and perception task-camera requirements.
  - The final installed candidate succeeds at all four positions on both platforms.
latest_checkpoint: CP-001
next_experiment: EXP-010
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
status: PLANNED
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
  source_commit: UNFROZEN_PRE_IMPLEMENTATION
  install_overlay: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install
  runtime_executable: /private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-candidate/project-install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 220
  gz_partition: mac-mrc010-task-start-exp010
commands:
  - command: ROS_DOMAIN_ID=220 GZ_PARTITION=mac-mrc010-task-start-exp010 ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false session_id:=mac-mrc010-task-start-exp010 mujoco_initial_keyframe:=task_start evidence_file:=/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010/task-start.json
    exit_code: PENDING
observed:
  - NOT_RUN
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-010
decision: PENDING
next_experiment: EXP-011
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
  source_commit: UNFROZEN_PRE_IMPLEMENTATION
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
  source_commit: UNFROZEN_PRE_IMPLEMENTATION
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
  source_commit: UNFROZEN_PRE_IMPLEMENTATION
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
  source_commit: UNFROZEN_PRE_IMPLEMENTATION
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
