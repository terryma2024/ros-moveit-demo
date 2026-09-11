---
task_id: so101-act-head-wrist-moveit-expert-baseline-20260911
goal: Complete one coherent exactly 20-point RESET_WORLD batch on one owned visible stack, requiring YOLO-Seg first at every point, permitting Grounded-SAM only after an allowed pre-acceptance YOLO failure, and requiring full physical SUCCEEDED/DONE for all 20 points.
success_contract: A batch counts only if all 20 frozen points run in order on one persistent stack with consecutive reset epochs; each point attempts YOLO-Seg first and may invoke Grounded-SAM only before an accepted cup pose for an explicitly allowed detection, geometry, quality, publication, acknowledgement, or bounded-timeout failure; every point must reach full physical DONE with unchanged force, geometry, sampled-corridor, scene, cleanup, and fresh visual gates.
worktree: /data/work/ws_moveit
branch: main
base_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
current_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
evidence_root: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW
confirmed_conclusions:
  - CP-001 observed a clean source worktree and no live SO-101 application stack.
  - EXP-011 completed a valid 20-scene baseline with 16 successes and 4 product failures.
  - CP-014 reconfirmed the frozen source, paired runtime, manifest and policy hashes, clean process boundary, and empty ROS domain before the four retry experiments.
  - EXP-012 validly repeated the sample_05_near_center perception-radius failure under FULL_RESTART.
  - EXP-013 validly repeated the sample_14_far_right MOVE_ABOVE_OBJECT dynamic IK residual failure under FULL_RESTART.
  - EXP-014 validly failed sample_15_far_center at DESCEND force monitoring under FULL_RESTART, a different first bad boundary from EXP-011.
  - EXP-015 validly succeeded sample_16_far_right end to end under FULL_RESTART after independently proving canonical initial state.
  - CP-016 registered dispatch 3c35b60f-2211-4e2b-aca4-181604915188, a unique immutable optimization subtree, exact paired runtime/model provenance, and two frozen P09 backend attempts before either stack start.
  - EXP-016 and EXP-017 each completed P09 once under independent FULL_RESTART, with YOLO-Seg and Grounded-SAM respectively; both achieved full physical DONE without tuning.
  - EXP-018 and EXP-019 completed P18 and P19 under independent FULL_RESTART using the same deterministic bounded whole-prefix planner and actual MoveIt sampled-corridor validation.
  - EXP-022 preserved a nearby previously successful far-point result at sample_13_far_center after EXP-020 and EXP-021 safely exposed a repeatable sampled-orientation rejection at sample_16_far_right.
  - CP-019 registered dispatch 8a87dc3e-9836-4feb-8f3c-3286b1efcaff, reconfirmed the frozen manifest and dirty baseline, and preregistered the next full RESET_WORLD batch before implementation or runtime work.
  - EXP-023 completed one coherent 20-of-20 RESET_WORLD batch on one persistent visible stack; every point used YOLO-Seg first and accepted its YOLO result, so Grounded-SAM was never invoked.
disproven_routes:
  - Treating EXP-011 sample_16_far_right's declared reachability rejection as deterministic across independent FULL_RESTART attempts; EXP-015 was reachable and succeeded.
  - Treating sample_16_far_right as a stable regression point for this sampled-corridor contract; two new independent stacks rejected its MOVE_ABOVE_OBJECT path orientation before motion.
open_hypotheses:
  - NONE
latest_checkpoint: CP-020
next_experiment: NONE
---

# SO-101 ACT Head/Wrist MoveIt Expert Baseline Experiment Ledger

This ledger records engineering qualification only. It does not update learner progress, implement
ACT, collect formal demonstrations, tune the expert, or authorize publication.

## Registered task boundary

- Authoritative handoff: `/tmp/so101-moveit-expert-baseline-task-20260911.md`.
- Sole evidence root: `/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW`.
- Lifecycle for the counted batch: `RESET_WORLD` on one owned, visible stack.
- Frozen source: `main@ea0215180ed8cc0a90d6683a5e80d475987b5bc0`.
- Frozen submodule: `third_party/mujoco_ros2_control@71bc9346cf93d6227a6678fcacf63f3e18acfcba`.
- Frozen expert policy source: `src/so101_demo_py/config/policies/dynamic_cup_pick/v1/mujoco.yaml`; its SHA256 will be recorded after the task-owned overlay is built.
- Fixed runtime isolation: `ROS_DOMAIN_ID=211`; `GZ_PARTITION=so101_act_moveit_baseline_20260911` is recorded for the evidence schema but MuJoCo does not consume Gazebo Transport.

## Harness boundary

Source inspection at CP-001 found that `so101_mujoco_rgbd_batch` owns the desired persistent stack,
transactional reset, reachability, fresh consumer-before-perception handshake, per-point artifacts,
and fail-closed continuation behavior. Its `MacViewerCapture` calls `/usr/bin/swift` and
`/usr/sbin/screencapture`, so that capture boundary cannot run on GNOME Linux. If execution confirms
the remaining orchestration is portable, the only permitted harness change is a task-local adapter
under the registered evidence root that routes each terminal capture through the project
`gui-capture` GNOME helper. It must not alter motion policy, grasp geometry, perception thresholds,
recovery parameters, product source, installed package content, or counted result semantics.

## CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: A task-owned current-commit overlay and one non-counted task_start smoke can establish runtime qualification before manifest freeze.
working_tree_status: clean before this ledger; after registration only this ledger is intentionally untracked
owned_processes: NONE
preserved_processes: codex-19 and unrelated colcon version-check process observed during initial inspection; no Gazebo, MuJoCo, move_group, RViz, pick-place, or SO-101 ROS nodes were present
confirmed_conclusions:
  - hostname is AI-STATION-001 and worktree is /data/work/ws_moveit.
  - source is clean main@ea0215180ed8cc0a90d6683a5e80d475987b5bc0 with clean submodule 71bc9346cf93d6227a6678fcacf63f3e18acfcba.
  - origin/main local and remote both resolve to ea0215180ed8cc0a90d6683a5e80d475987b5bc0.
  - the required github remote is absent in this checkout, so GitHub parity is not established.
  - top-level install/setup.zsh references a missing historical Python develop hook; the currently resolved fusion-final package lacks the public batch executable while install/so101_demo_py contains a stale egg-link.
disproven_routes:
  - Treating the pre-existing top-level install as current runtime provenance is disproven by the missing develop hook, stale egg-link, and executable-set mismatch.
open_risks:
  - Current-commit isolated package build may expose additional missing runtime dependencies.
  - GNOME capture must be proven fresh and visually inspected before any run is accepted.
next_command: Build so101_demo_py into the registered evidence root from the frozen source after sourcing ROS Jazzy and the pinned MuJoCo fork overlay, then inspect --help and launch --show-args.
```

## Planned experiments

`EXP-001` is reserved for the non-counted `task_start` smoke. Its complete `PLANNED` record and
exact command will be appended only after the current-commit task-owned overlay, public CLI help,
launch arguments, and GUI capture route have been verified. No behavior run has started.

## EXP-001

```yaml
experiment_id: EXP-001
status: INVALID
prior_experiment: NONE
hypothesis: The frozen current-commit MoveIt expert can consume a new task_camera RGB-D sample and complete one physical task_start pick-place on a single visible owned MuJoCo stack.
prediction: The task_start smoke exits zero and its workflow acceptance, controller/joint/TF, MuJoCo physical outcome, Planning Scene lifecycle, cleanup, and fresh GNOME MuJoCo screenshot all pass.
single_variable: Run the existing task_start point once as a non-counted smoke; no expert parameter or scene geometry changes.
lifecycle: FULL_RESTART
preconditions:
  - No existing MuJoCo, move_group, RViz, pick-place, or SO-101 ROS application nodes in ROS_DOMAIN_ID 211.
  - Source remains main@ea0215180ed8cc0a90d6683a5e80d475987b5bc0 and only this ledger is dirty.
  - Task-owned overlay resolves so101_demo_py to /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/install2/so101_demo_py.
  - GNOME X11 window inventory succeeds through gui-capture.
success_criteria:
  - Fresh perception provenance is consumed by the dynamic workflow.
  - All motion stages plan and execute with correlated controller, joint-state, and TF evidence.
  - MuJoCo records physical grasp, lift, transport, release, stable supported final placement, and no final fingertip contact.
  - Planning Scene attached objects are cleared, plastic_cup world pose is synchronized, retreat and owned cleanup complete.
  - A post-terminal window capture is fresh and visually confirms the resulting MuJoCo scene.
failure_criteria:
  - Any normal perception, planning, controller, grasp, lift, transport, release, placement, retreat, timeout, or acceptance failure is a valid smoke failure and stops progression to the counted batch.
invalid_criteria:
  - Wrong source/install/runtime provenance, duplicate stack, reset/initial state mismatch, session/epoch mismatch, or contaminated/missing required evidence.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  install_overlay: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/install2
  runtime_executable: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/linux_rgbd_batch.py wrapping installed so101_mujoco_rgbd_batch with capture-only adaptation
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: source ~/gui-env.zsh; source /opt/ros/jazzy/setup.zsh; source /data/work/ws_mujoco_ros2_control_fork/install/setup.zsh; source /data/work/ws_moveit/install/fusion-final/setup.zsh; source /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/install2/setup.zsh; ROS_DOMAIN_ID=211 GZ_PARTITION=so101_act_moveit_baseline_20260911 python3 /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/linux_rgbd_batch.py --points /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/smoke-task-start.yaml --batch-id smoke-task-start --session-id act-moveit-baseline-smoke-20260911 --evidence-root /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW
    exit_code: 130
observed:
  - 2026-09-11T11:13+08:00 preflight reconfirmed no application nodes or relevant processes in the isolated domain; the harness passed py_compile and GNOME X11 window inventory was available.
  - 2026-09-11T11:14+08:00 launch failed before MoveIt readiness because ament_index selected /data/work/ws_moveit/install/fusion-final/so101_mujoco_support, whose libexec lacks graceful_shutdown_move_group.
  - The launch process nevertheless started owned ros2_control_node PID 3977748; the run was interrupted, that exact PID was stopped, and the owned tmux session was removed. No relevant process remained.
inferred:
  - The fusion-final support prefix predates commit 91f7ebbc, while /data/work/ws_moveit/install/so101_mujoco_support contains the renamed executable built after that source change.
conclusion: INVALID_ENVIRONMENT_PROVENANCE; no expert behavior was exercised or counted.
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/provenance/isolated-build.typescript (failed pre-build scope attempt retained)
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/provenance/isolated-build2.typescript (current-commit task-owned overlay build, exit 0)
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/provenance/runtime-entrypoints.typescript
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/smoke-run.typescript
decision: REPEAT
next_experiment: EXP-002
```

## EXP-002

```yaml
experiment_id: EXP-002
status: INVALID
prior_experiment: EXP-001
hypothesis: Prepending the current workspace so101_mujoco_support prefix removes the sole EXP-001 launch-provenance mismatch and permits the unchanged task_start smoke to reach all expert acceptance boundaries.
prediction: so101_mujoco_support resolves to /data/work/ws_moveit/install/so101_mujoco_support with graceful_shutdown_move_group present, then the unchanged task_start smoke exits zero with complete electronic and visual evidence.
single_variable: Runtime overlay selection for so101_mujoco_support; all source, expert, perception, scene, reset, and acceptance inputs remain unchanged.
lifecycle: FULL_RESTART
preconditions:
  - EXP-001 owned process tree is fully stopped and ROS_DOMAIN_ID 211 has no application nodes.
  - /data/work/ws_moveit/install/so101_mujoco_support contains graceful_shutdown_move_group and its owning source has not changed since commit 91f7ebbc776b0af7dd3c57bb4942a2b06d80c4de.
  - All EXP-001 success, failure, and invalid criteria otherwise remain unchanged.
success_criteria:
  - Same full non-counted smoke criteria frozen in EXP-001.
failure_criteria:
  - Same valid product-failure criteria frozen in EXP-001.
invalid_criteria:
  - Same provenance, reset, duplication, and evidence-pollution criteria frozen in EXP-001.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  install_overlay: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/install2 with /data/work/ws_moveit/install/so101_mujoco_support explicitly prepended
  runtime_executable: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/linux_rgbd_batch.py wrapping installed so101_mujoco_rgbd_batch with capture-only adaptation
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: source the frozen overlays; source /data/work/ws_moveit/install/so101_mujoco_support/share/so101_mujoco_support/package.zsh; prepend /data/work/ws_moveit/install/so101_mujoco_support to AMENT_PREFIX_PATH; run linux_rgbd_batch.py with smoke-task-start.yaml, batch-id smoke-task-start-02, and session-id act-moveit-baseline-smoke-02-20260911
    exit_code: 1
observed:
  - 2026-09-11T11:16+08:00 corrected ament resolution returns /data/work/ws_moveit/install/so101_mujoco_support and lists graceful_shutdown_move_group.
  - EXP-001 also left owned spawner PID 3977749 after its launch parent exited; the exact PID was stopped and ROS_DOMAIN_ID 211 then returned an empty node list.
  - The corrected stack loaded the current support executable, MuJoCo model, RGB-D camera, MoveIt, all controllers, and the formal Planning Scene.
  - Before the runner's one-shot joint-state readiness sample, arm/gripper controllers were still serializing startup; `/joint_states` was not discoverable at that instant, so the runner stopped the stack before any point reset or expert action.
  - The owned stack and tmux session shut down cleanly; ROS_DOMAIN_ID 211 was empty afterward.
inferred:
  - Public cold-start orchestration has a transient readiness race on this host; attaching only after explicit readback can distinguish that environment condition from expert behavior without changing the expert.
conclusion: INVALID_STARTUP_READINESS; no expert behavior was exercised or counted.
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/smoke-02-run.typescript
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/smoke-02-run.typescript
decision: REPEAT
next_experiment: EXP-003
```

## EXP-003

```yaml
experiment_id: EXP-003
status: INVALID
prior_experiment: EXP-002
hypothesis: An explicitly owned visible task-station stack that is allowed to reach stable controller, joint-state, and Planning Scene readiness will support the unchanged attached task_start smoke.
prediction: After readiness readback, the attached batch performs one reset epoch and the unchanged expert completes with all EXP-001 success evidence; the stack remains owned and paused for the counted RESET_WORLD batch.
single_variable: Externalize stack startup/readiness before invoking the public --attach-existing-stack mode; no product parameter changes.
lifecycle: FULL_RESTART
preconditions:
  - ROS_DOMAIN_ID 211 is empty and no relevant application process exists.
  - One task-owned tmux session starts exactly one task-station stack using the same source/install/policy/config as EXP-002.
  - controller list reports joint_state_broadcaster, arm_controller, and gripper_controller active; a fresh /joint_states sample and Planning Scene observation succeed before the attached runner starts.
success_criteria:
  - Same full non-counted smoke criteria frozen in EXP-001.
failure_criteria:
  - Same valid product-failure criteria frozen in EXP-001.
invalid_criteria:
  - Same provenance, reset, duplication, and evidence-pollution criteria frozen in EXP-001.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  install_overlay: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/install2 with current workspace so101_mujoco_support prepended
  runtime_executable: task-owned so101_mujoco_task_station.launch.py plus linux_rgbd_batch.py --attach-existing-stack; capture-only adapter
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: Start ros2 launch so101_demo_py so101_mujoco_task_station.launch.py headless:=false sensor_rendering:=true session_id:=act-moveit-baseline-main-20260911 task_evidence_root:=/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/stack include_teleop:=false in tmux so101-act-moveit-baseline-stack; after readiness run linux_rgbd_batch.py with --attach-existing-stack and the exact owned MuJoCo PID.
    exit_code: 1
observed:
  - 2026-09-11T11:19+08:00 pre-start ROS_DOMAIN_ID 211 and relevant process inventory were empty.
  - The owned stack reached stable readiness: all three controllers were active, fresh joint states were near zero, all required services/actions were available, and the Planning Scene contained only pedestal, plastic_cup, and table with no attached object or primitive-count mismatch.
  - All seven task_start reachability plans returned REACHABLE before any reset or motion execution.
  - The first transactional pause/reset crashed ros2_control_node with SIGSEGV in MujocoSystemInterface::set_pause_callback called by SimulationEvidencePlugin::on_physics_step; no reset epoch was created and the point result is TRANSACTIONAL_RESET_FAILED.
  - Runtime readback showed the core came from /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install, built 2026-08-13, while so101_mujoco_support came from the newer top-level workspace install. The pinned submodule is 71bc9346cf93d6227a6678fcacf63f3e18acfcba dated 2026-08-28.
  - The required-process launch shutdown completed; the two exact task-owned tmux sessions were removed, and no task process remained.
inferred:
  - The crash is an ABI/provenance mismatch between an older MuJoCo control core and a newer simulation-evidence plugin, not an expert behavior result.
conclusion: INVALID_BINARY_PROVENANCE; reachability was exercised, but reset and expert execution were not validly entered and nothing is counted.
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/stack-run.typescript
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/smoke-03-run.typescript
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/batches/smoke-task-start-03/batch-result.json
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/batches/smoke-task-start-03/points/01-task_start_smoke/point-result.json
decision: REBUILD_PAIRED_PINNED_OVERLAY_AND_REPEAT
next_experiment: EXP-004
```

## EXP-004

```yaml
experiment_id: EXP-004
status: INVALID
prior_experiment: EXP-003
hypothesis: Rebuilding the MuJoCo control core and so101_mujoco_support together from the frozen pinned sources removes the sole EXP-003 ABI mismatch and permits the unchanged attached task_start smoke.
prediction: Runtime prefix and binary hashes resolve only to task-owned paired overlays; transactional reset creates a valid epoch; the unchanged expert then satisfies every EXP-001 success criterion.
single_variable: Replace the mixed historical core/current support binaries with a paired task-owned build from the frozen submodule and parent source; behavior, policy, scene, perception, reset, and acceptance inputs remain unchanged.
lifecycle: FULL_RESTART
preconditions:
  - EXP-003 task process tree and owned tmux sessions are absent.
  - Parent and submodule commits remain frozen and clean except for this ledger.
  - Prior qualification records establish that pinned submodule 71bc9346cf93d6227a6678fcacf63f3e18acfcba passed its Linux build/test gates; this task rebuild does not reuse runtime binaries from that missing retained root.
success_criteria:
  - Same full non-counted smoke criteria frozen in EXP-001, plus exact installed-prefix and binary-hash readback for the paired overlay.
failure_criteria:
  - Same valid product-failure criteria frozen in EXP-001 after a valid reset epoch is established.
invalid_criteria:
  - Same provenance, reset, duplication, and evidence-pollution criteria frozen in EXP-001.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  fork_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  install_overlay: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/paired-build/{fork,support,demo}/install in dependency order
  runtime_executable: unchanged task-station launch plus capture-only linux_rgbd_batch.py adapter
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: Build the four locked fork packages, current so101_mujoco_support, and frozen so101_demo_py into new task-owned overlays; read back exact prefixes and hashes; start one visible owned stack and invoke the unchanged attached task_start smoke after readiness.
    exit_code: 1
observed:
  - The four pinned fork packages, current support package, and frozen demo package built successfully into three task-owned overlays without product-source changes.
  - Prefix readback resolves every fork package to paired-build/fork/install, so101_mujoco_support to paired-build/support/install, and so101_demo_py to paired-build/demo/install; core executable SHA256 is d18bf9aefdcccb6297e1da77895403ac4bf599cb9533c2a0058e5475a4619516 and support plugin SHA256 is 4be2e0ef5b98fd18385971a54bff15c00f4d9e0ec021d8b091d04307f295f095.
  - The visible owned stack is ready with all three controllers active, fresh near-zero joint state, complete action/service readiness, canonical Planning Scene readback, and exact task-owned core/support executable paths.
  - All seven task_start planning states were REACHABLE; RESET_WORLD completed without a crash, created reset epoch 1, applied the requested free-joint override, and restored the controllers.
  - rgbd_cup_pose then failed its declared preflight because Open3D was absent from the ROS Python environment; the waiting consumer was interrupted before receiving /cup_pose or executing motion.
  - GNOME produced a fresh exact-window PNG, but copying it with preserved source mtime during the early-abort cleanup caused the adapter freshness comparison to replace the primary preflight failure with TERMINAL_CAPTURE_FAILED. Both artifacts are retained; neither is product-behavior evidence.
inferred:
  - The paired binary correction is proven through reset. The remaining failure is missing declared perception runtime dependency, so expert behavior was not validly entered.
conclusion: INVALID_PERCEPTION_ENVIRONMENT; no smoke outcome is counted.
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/paired-build
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/batches/smoke-task-start-04
decision: MATERIALIZE_TASK_LOCAL_OPEN3D_AND_REPEAT
next_experiment: EXP-005
```

## EXP-005

```yaml
experiment_id: EXP-005
status: INVALID
prior_experiment: EXP-004
hypothesis: Adding only the declared Open3D 0.19 runtime dependency under the registered task root allows the unchanged RGB-D producer/consumer chain and expert smoke to run on the already qualified paired stack.
prediction: Import preflight reports Open3D 0.19.0 and NumPy 1.26.4 from the task-local dependency root; a new RESET_WORLD epoch, fresh perception sample, unchanged expert, acceptance, and terminal screenshot all pass.
single_variable: Prepend the task-local Python dependency root containing Open3D 0.19.0; core/support/demo binaries, stack, scene, policy, point, reset, and capture implementation remain unchanged.
lifecycle: RESET_WORLD
preconditions:
  - EXP-004 left the single owned paired stack alive and paused with no point child process.
  - Task-local Open3D import and ROS imports succeed together under PYTHONNOUSERSITE=1 before invocation.
success_criteria:
  - Same full non-counted smoke criteria frozen in EXP-001.
failure_criteria:
  - Same valid product-failure criteria frozen in EXP-001 after dependency and reset preconditions pass.
invalid_criteria:
  - Same provenance, reset, duplication, and evidence-pollution criteria frozen in EXP-001.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  fork_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  install_overlay: unchanged EXP-004 paired overlay
  python_dependency_root: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/python-deps
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: Run linux_rgbd_batch.py --attach-existing-stack for task_start with a fresh batch ID and the exact owned PID under the task-local Python dependency root.
    exit_code: 1
observed:
  - Pre-invocation import readback resolves Open3D 0.19.0 and NumPy 1.26.4 from the task-local dependency root while rclpy and cv_bridge resolve from ROS Jazzy and so101_demo resolves from the frozen paired demo build.
  - RESET_WORLD created fresh epoch 2; perception published a fresh source stamp with fitted radius 0.0393805 m and planar error about 0.64 mm at task_start.
  - The unchanged expert completed all 19 transitions through DONE. MuJoCo recorded bilateral grasp contact, lift and transport off the table, release, stable table support, no final fingertip contact, final XY error 0.002616 m, Planning Scene detach/world sync, and retreat.
  - GNOME captured a fresh exact-window PNG after terminal. Direct visual inspection shows the cup upright and supported inside the red target ring with the gripper open and retreated.
  - The task-local adapter failed after capture because capture-gui.sh intentionally prints human-readable Image/Manifest lines while the adapter attempted json.loads on stdout. The workflow artifact was registered, but the viewer artifact and point success receipt were not, so the run is invalid for evidence acceptance.
inferred:
  - Expert behavior is successful at task_start, but the smoke cannot count until the capture adapter registers the already-proven GNOME contract correctly.
conclusion: INVALID_TERMINAL_EVIDENCE_ADAPTER; physical workflow succeeded but the run is not accepted or counted.
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/python-deps-install.typescript
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/python-deps-resolve.typescript
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/batches/smoke-task-start-05
decision: CORRECT_CAPTURE_RECEIPT_PARSING_AND_REPEAT
next_experiment: EXP-006
```

## EXP-006

```yaml
experiment_id: EXP-006
status: VALID
prior_experiment: EXP-005
hypothesis: Parsing capture-gui.sh's declared Manifest path, then validating the manifest JSON exactly as before, removes the sole EXP-005 evidence-registration defect.
prediction: A fresh task_start RESET_WORLD run repeats DONE and registers viewer.png plus all workflow/perception artifacts, yielding a SUCCESS point and batch exit zero.
single_variable: Capture-only adapter receipt parsing changes from direct stdout JSON to the shell driver's declared Manifest path; selection, exact PID/window validation, motion, perception, policy, scene, and acceptance remain unchanged.
lifecycle: RESET_WORLD
preconditions:
  - EXP-005 point children exited and the single owned paired stack remains alive and paused.
  - A manual exact-PID diagnostic reproduces JSONDecodeError only after capture-gui.sh successfully wrote a valid image and manifest.
  - The retained EXP-005 image has been inspected and is visually consistent with its successful physical manifest.
success_criteria:
  - Same full non-counted smoke criteria frozen in EXP-001.
failure_criteria:
  - Same valid product-failure criteria frozen in EXP-001 after reset and evidence preconditions pass.
invalid_criteria:
  - Same provenance, reset, duplication, and evidence-pollution criteria frozen in EXP-001.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  install_overlay: unchanged EXP-004 paired overlay
  python_dependency_root: unchanged EXP-005 root
  capture_adapter: linux_rgbd_batch.py parsing capture-gui.sh Manifest path, otherwise unchanged
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: Validate the corrected capture adapter against the exact owned MuJoCo PID, then run a fresh attached task_start smoke with a new batch ID.
    exit_code: 0
observed:
  - Corrected no-motion diagnostic selected window 50331655 owned by exact task MuJoCo PID 3991674, produced viewer.png plus viewer-capture.json, and returned successfully.
  - Fresh RESET_WORLD epoch 3, seven-state reachability, Open3D RGB-D perception, 19-transition expert workflow, physical outcome, Planning Scene lifecycle, retreat, and terminal capture all succeeded.
  - The batch registered reset, workflow, RGB, full cloud, cup cloud, preview, exact-window viewer, and both child logs; point and batch statuses are SUCCEEDED with no failure code or shared failure.
  - Direct visual inspection of the registered viewer.png shows the cup upright and table-supported inside the red target ring, with open fingers separated from the cup and the arm retreated.
inferred:
  - The frozen existing expert is qualified for the 20-scene counted baseline under the paired overlay and task-local Open3D dependency set.
conclusion: ACCEPTED_NON_COUNTED_SMOKE
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/capture-diagnostic
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/batches/smoke-task-start-06
decision: PROCEED_TO_INDEPENDENT_MANIFEST_VALIDATION
next_experiment: EXP-007
```

## EXP-007

```yaml
experiment_id: EXP-007
status: INVALID
prior_experiment: EXP-006
hypothesis: The four anchors plus sixteen fixed-seed continuous XY samples are independently valid stable MuJoCo start scenes before expert evaluation.
prediction: All 20 candidates satisfy frozen table-edge and pairwise-spacing geometry, then each transactional reset succeeds with an exact request receipt, consecutive epoch, stable physical verification, and canonical unattached Planning Scene.
single_variable: Candidate cup XY position across a preregistered reset-only sequence; no expert process, perception process, or motion execution is started.
lifecycle: RESET_WORLD
preconditions:
  - EXP-006 accepted smoke is complete and its point children exited.
  - Candidate manifest has 20 unique IDs: the four required anchors and 16 samples generated by Python random seed 20260911 across near/mid/far and left/center/right strata.
  - Scene-derived tabletop bounds are x [-0.25, 0.25], y [-0.50, 0.10], top z 0.12; cup outer radius is 0.04 m and center z is 0.165 m.
success_criteria:
  - Minimum cup outer-edge clearance is at least 0.12 m and minimum requested pairwise XY separation is at least 0.015 m.
  - All 20 resets return success with exact requested coordinates, consecutive epochs, no attached object, no scene mismatch, and primitive counts pedestal=1, plastic_cup=13, table=1.
failure_criteria:
  - Any geometric contract, reset stability, request readback, epoch, or Planning Scene check fails.
invalid_criteria:
  - Expert execution occurs, stack provenance changes, duplicate stack appears, or validation evidence collides with an existing path.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  candidate_manifest: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/manifest/candidate-points.yaml
  generator_seed: 20260911
  expert_execution: false
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: Run validate_candidate_resets.py once on the owned paired stack and write one unique receipt per point plus summary.json.
    exit_code: 1
observed:
  - The validator established its unique output directory, but the first task_start reset returned TRANSACTIONAL_RESET_FAILED with message initial evidence unavailable.
  - No candidate reset epoch was created and no expert, perception, controller trajectory, or scene result was evaluated.
inferred:
  - EXP-006 intentionally left physics paused; unlike the public batch runtime, the standalone reset-only validator did not resume physics before asking transactional_reset to acquire initial evidence.
conclusion: INVALID_STARTUP_LIFECYCLE; candidate validity remains unmeasured.
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/manifest/reset-validation
decision: ADD_PUBLIC_RESUME_BOUNDARY_AND_REPEAT
next_experiment: EXP-008
```

## EXP-008

```yaml
experiment_id: EXP-008
status: INVALID
prior_experiment: EXP-007
hypothesis: Calling the same public resume_physics boundary used by the batch runner before each reset lets the unchanged reset-only validation measure all 20 candidates.
prediction: Physics resumes, initial evidence becomes available, and all frozen EXP-007 geometric/reset/scene success criteria pass for the identical candidate bytes.
single_variable: Add resume_physics(None) immediately before each standalone transactional reset; manifest, stack, reset implementation, and all validity thresholds remain unchanged.
lifecycle: RESET_WORLD
preconditions:
  - EXP-007 created no reset epoch and started no expert/perception/motion process.
  - The first output root is retained without reuse; reset-validation-r2 does not exist.
success_criteria:
  - Identical EXP-007 success criteria for all 20 candidates.
failure_criteria:
  - Identical EXP-007 failure criteria after successful resume.
invalid_criteria:
  - Identical EXP-007 invalid criteria.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  candidate_manifest: unchanged candidate-points.yaml
  generator_seed: 20260911
  expert_execution: false
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: Run corrected validate_candidate_resets.py once, writing unique reset-validation-r2 receipts and summary.
    exit_code: 1
observed:
  - The validator failed at Python import before calling resume or reset because resume_physics was imported from teleop_runtime instead of its public backends.mujoco.lifecycle module.
  - No candidate reset, expert, perception, or motion process started; reset-validation-r2 is retained without reuse.
inferred:
  - The lifecycle hypothesis remains untested; this is a harness bootstrap error.
conclusion: INVALID_HARNESS_IMPORT
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/manifest/reset-validation-r2
decision: CORRECT_PUBLIC_IMPORT_AND_REPEAT
next_experiment: EXP-009
```

## EXP-009

```yaml
experiment_id: EXP-009
status: VALID
prior_experiment: EXP-008
hypothesis: Importing resume_physics from so101_demo.backends.mujoco.lifecycle permits the identical reset-only candidate validation to execute.
prediction: The corrected public import succeeds, then all 20 unchanged EXP-007 candidate criteria pass into a new reset-validation-r3 root.
single_variable: Correct the resume_physics module path; no runtime, manifest, threshold, or lifecycle behavior changes.
lifecycle: RESET_WORLD
preconditions:
  - EXP-008 exited before any runtime call and its unique root is retained.
  - reset-validation-r3 does not exist and the paired stack remains the sole application stack.
success_criteria:
  - Identical EXP-007 success criteria for all 20 candidates.
failure_criteria:
  - Identical EXP-007 failure criteria after successful import/resume.
invalid_criteria:
  - Identical EXP-007 invalid criteria.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  candidate_manifest: unchanged candidate-points.yaml
  generator_seed: 20260911
  expert_execution: false
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: Run validate_candidate_resets.py with corrected lifecycle import, writing reset-validation-r3.
    exit_code: 0
observed:
  - Geometry validation passed for 20 unique IDs with minimum cup outer-edge/table-edge clearance 0.120555 m and minimum pairwise XY separation 0.0151162 m.
  - All 20 reset-only transactions succeeded at consecutive epochs 4 through 23 with exact requested coordinate receipts, stable physical verification internal to transactional_reset, no attached object, no scene mismatch, and canonical primitive counts.
  - No expert, perception, or controller trajectory process ran during validation.
inferred:
  - Every frozen scene is independently valid; subsequent planning/perception/control failures are valid product failures and must remain in the counted denominator.
conclusion: ACCEPT_CANDIDATES_AND_FREEZE_MANIFEST
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/manifest/reset-validation-r3
decision: PROCEED_TO_COUNTED_BATCH
next_experiment: EXP-010
```

## EXP-010

```yaml
experiment_id: EXP-010
status: INVALID
prior_experiment: EXP-009
hypothesis: The unchanged existing RGB-D MoveIt expert can complete the independently valid frozen 20-scene baseline on first attempts under one persistent RESET_WORLD stack.
prediction: Every point produces a first-attempt terminal result and full electronic/visual evidence; aggregate and stratified success rates can be reported without exclusions except authoritative invalid-environment criteria.
single_variable: Frozen scene position in manifest order; source, install, stack, policy, perception, reset lifecycle, capture adapter, thresholds, and evidence contract remain fixed.
lifecycle: RESET_WORLD
preconditions:
  - EXP-006 non-counted smoke is accepted.
  - EXP-009 independently validates all 20 scenes without expert execution.
  - Frozen points SHA256 is c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5 and file mode is read-only.
  - One task-owned paired stack is alive; no point child/validator or duplicate application stack exists.
success_criteria:
  - Each scene succeeds only if fresh perception, planning and execution, controller/joint/TF motion, MuJoCo grasp/lift/transport/release/final stability, Planning Scene detach/world sync, retreat/cleanup, and fresh exact-window visual evidence all pass.
  - Per-scene result, first-failure stage, perception error, physical metrics, and screenshot inspection are summarized; aggregate and strata include Wilson 95% confidence intervals.
failure_criteria:
  - Any independently valid scene's perception, planning rejection, controller, grasp, transport, release, placement, cleanup, or visual failure counts as a product failure in the denominator.
invalid_criteria:
  - Only wrong provenance, failed/mismatched reset, duplicate stack, or evidence contamination invalidates the counted batch.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  fork_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  install_overlay: unchanged paired-build fork/support/demo installs
  policy_sha256: dc17d704ea9a333a387896bf36293a876bedc0be7868bc8b1ea800f4ce19d66d
  manifest_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  python_dependency_root: unchanged task-local Open3D dependency root
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: Run linux_rgbd_batch.py once with batch-id counted-20-scene-first-attempt, explicit frozen points/policy, --attach-existing-stack, and exact owned MuJoCo PID 3991674.
    exit_code: 1
observed:
  - Scenes 1 through 8 completed successfully at consecutive reset epochs 24 through 31 with registered workflow and terminal artifacts.
  - Scene 9, sample_05_near_center, established valid reset epoch 32 and was reachable, then produced a local RGBD_PERCEPTION_EXITED_EARLY result after every fitted frame reported radius 0.019058 m against the frozen 0.040000 +/- 0.010000 m contract. This is diagnostically a perception-geometry product failure, but the invalid batch is not counted.
  - Scene 10 was independently REACHABLE but failed before creating a reset receipt or epoch with TRANSACTIONAL_RESET_FAILED; the batch stopped immediately with first_shared_failure TRANSACTIONAL_RESET_FAILED and did not allocate scenes 11 through 20.
  - The stack log shows the reset client's initial snapshot request paused physics at 1789099243.537825602, but no fresh atomic evidence reached the newly created reset subscriber. The reset emitted initial evidence unavailable after its 10-second timeout.
  - An exact standalone diagnostic reset after the batch reproduced initial evidence unavailable in 10.77 seconds. No reset service call or epoch occurred. The owned stack and exact MuJoCo PID remained alive and unique.
inferred:
  - Competing hypothesis H1, a newly created reset subscriber can race its first pause request and strand itself without a fresh volatile evidence frame, is consistent with the pause-without-reset trace and exact reproduction.
  - Competing hypothesis H2, the evidence publisher or simulator died, is disfavored because the same stack accepted resume/pause service calls, continued MoveIt planning, retained its exact PID, and had already passed 20 consecutive reset-only transactions when the public resume boundary was used.
  - This is shared reset/evidence orchestration invalidation, not an expert failure. Per the frozen contract, no EXP-010 scene contributes to the baseline denominator.
conclusion: INVALID_RESET_EVIDENCE_DISCOVERY_RACE
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/batches/counted-20-scene-first-attempt
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/counted-batch.typescript
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/diagnostics/reset-after-perception-failure/teleop-reset.log
decision: ADD_TASK_LOCAL_PRE_RESET_EVIDENCE_HANDSHAKE_AND_REPEAT_AS_A_NEW_BATCH
next_experiment: EXP-011
```

## EXP-011

```yaml
experiment_id: EXP-011
status: VALID
prior_experiment: EXP-010
hypothesis: A task-local reset-entry adapter that resumes physics and waits for the reset observer to receive a fresh atomic evidence frame before invoking the unchanged transactional reset removes the EXP-010 subscriber-discovery race.
prediction: A reset-only A/B probe on the unchanged stack creates epoch 33 with the exact scene-10 position; afterward a fresh 20-scene batch completes without shared reset invalidation while all policy, perception, motion, scene, acceptance, and manifest bytes remain unchanged.
single_variable: Add a pre-reset evidence-subscriber readiness handshake in the task-local experiment harness; do not change product source, installed package content, expert policy, perception thresholds, grasp geometry, recovery parameters, point ordering, or result semantics.
lifecycle: RESET_WORLD
preconditions:
  - EXP-010 is sealed and retained; none of its point results is counted.
  - The exact paired stack, source commit, overlay hashes, policy hash, manifest hash, isolation values, and MuJoCo PID remain unchanged and unique.
  - The adapter must still call the existing public resume boundary and existing transactional reset, and must fail closed if a fresh session-bound atomic frame is unavailable.
success_criteria:
  - Reset-only A/B establishes an exact receipt and consecutive epoch without expert execution.
  - A new unique batch root contains all 20 first-attempt point results and no shared failure.
  - Identical full per-scene success and valid product-failure criteria frozen in EXP-010 apply.
failure_criteria:
  - Normal independently valid per-scene perception, planning, execution, grasp, transport, release, placement, retreat, cleanup, timeout, or visual failures enter the denominator.
invalid_criteria:
  - Any reset/epoch/session mismatch, wrong provenance, duplicate stack, evidence contamination, or harness failure terminates and invalidates this batch.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  fork_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  install_overlay: unchanged paired-build fork/support/demo installs
  policy_sha256: dc17d704ea9a333a387896bf36293a876bedc0be7868bc8b1ea800f4ce19d66d
  manifest_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: Run the task-local robust reset entry once for sample_06_mid_left after public resume and save its full receipt/log under diagnostics/reset-handshake-ab.
    exit_code: 0
  - command: If and only if the A/B reset passes, run linux_rgbd_batch.py with the reset-entry adapter, batch-id counted-20-scene-first-attempt-r2, the unchanged frozen manifest and policy, --attach-existing-stack, and exact MuJoCo PID 3991674.
    exit_code: 1
observed:
  - The task-local scripts passed Python bytecode compilation; no product source or installed package file was changed.
  - The A/B entry called the public resume boundary, received a fresh session-bound running frame before pause, and completed the unchanged transactional reset in 2.54 seconds.
  - Its receipt advanced the exact stack from epoch 32 to 33, read back requested position [-0.044253, -0.285035, 0.165], retained the simulation session, and confirmed canonical world objects with no attachment or mismatch.
  - The fresh counted batch ran from 2026-09-11T12:08:44+08:00 to 2026-09-11T12:26:47+08:00. It allocated all 20 points, had no first_shared_failure, and used consecutive reset epochs 34 through 52 for the 19 points that passed declared reachability.
  - Sixteen points independently passed fresh producer/consumer stamp equality, operational MoveIt trajectory and terminal joint/FK evidence, bilateral physical grasp and lift, transport, stable release in the configured target, empty attached set plus synchronized world object, retreat, zero final fingertip contact, and visual review.
  - Four independently valid points were product failures: sample_05_near_center failed perception after fitted radius 0.019058 m repeatedly violated the 0.040000 +/- 0.010000 m contract; sample_14_far_right locked fresh perception then failed DYNAMIC_IK_RESIDUAL_EXCEEDED before MOVE_ABOVE_OBJECT; sample_15_far_center locked fresh perception, approached, grasped, and micro-lifted, then failed DYNAMIC_IK_RESIDUAL_EXCEEDED at full LIFT; sample_16_far_right was rejected at declared MOVE_ABOVE_OBJECT planning with MOVEIT_PLAN_FAILED code 99999 before reset or execution.
  - The primary success rate is 16/20 = 80.0%, Wilson 95% CI [58.4%, 91.9%]. Conditional on a fresh perception lock it is 16/18 = 88.9%, Wilson 95% CI [67.2%, 96.9%].
  - Funnel counts are proposed 20, scene-valid 20, perception-fresh/locked 18, first operational plan accepted 17, correlated execution success 17, physical grasp 17, release-stable 16, and done-clean 16.
  - Distance strata are near 4/5 = 80.0% (Wilson [37.6%, 96.4%]), mid 9/9 = 100% ([70.1%, 100%]), and far 3/6 = 50.0% ([18.8%, 81.2%]). Lateral strata are left 6/6 = 100% ([61.0%, 100%]), center 6/8 = 75.0% ([40.9%, 92.9%]), and right 4/6 = 66.7% ([30.0%, 90.3%]). Anchors are 4/4; fixed-seed continuous samples are 12/16.
  - Across the 18 fresh perceptions, mean position error is 0.000714 m and maximum is 0.001440 m. Across the 16 successes, maximum cup z is 0.227919 to 0.228369 m, explicit micro-lift is 0.003942 to 0.004001 m, final z is 0.164775 to 0.164930 m, final XY error is 0.002281 to 0.003382 m, and final upright tilt is 0.003246 to 0.007135 rad.
  - No categorical edge-clearance bin was frozen, so no post-outcome bin is promoted as a preregistered stratum. Per-point clearance is retained; the three far product failures have 0.120555 m, 0.120566 m, and 0.138426 m clearance, while the near perception failure has 0.188876 m clearance.
  - Nineteen point-owned exact-window screenshots and one fresh post-planner scene-20 capture were actually inspected in five contact sheets. All 16 successes visibly show an upright cup inside the red target ring with an open retreated gripper. The three executed failures visibly remain outside the ring; scene 19 retains fingertip contact. Scene 20's separate paused capture honestly shows the unchanged scene-19 residual because its planning rejection happened before reset.
  - A post-batch atomic diagnostic at epoch 52 numerically confirms the scene-19/20 residual: cup position [0.0081773395, -0.3388196987, 0.1688752152] m, nearly upright, one left and one right fingertip contact, no table contact, and near-zero velocity. It was collected only after the counted batch and does not alter its result.
  - Final integrity verification recalculated all 164 registered artifact sizes and SHA256 values, validated 19 reset receipts from old epoch 33 through new epoch 52, and confirmed all 19 point-owned captures used exact MuJoCo window ID 50331655 in window mode.
inferred:
  - The bounded pre-pause subscriber handshake is sufficient to remove the observed invalid reset race without changing expert behavior or acceptance semantics.
  - Failures concentrate at the far/right boundary, but intervals are wide at n=20 and do not support a broad generalization claim.
  - The frozen manifest and EXP-011 results are a usable shared evaluation baseline, but the public runner is not drop-in qualified without carrying the recorded reset handshake and the pre-reset declared-reachability sequencing caveat.
conclusion: VALID_BASELINE_16_OF_20_CONDITIONALLY_SUITABLE
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/diagnostics/reset-handshake-ab
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/batches/counted-20-scene-first-attempt-r2
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/counted-batch-r2.typescript
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/analysis/baseline-summary.json
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/analysis/per-scene.tsv
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/visual-review
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/diagnostics/post-batch-atomic-evidence.json
decision: ACCEPT_BASELINE_WITH_RUNTIME_CAVEATS_AND_SHUT_DOWN_OWNED_STACK
next_experiment: NONE
```

## CP-013

```yaml
checkpoint_id: CP-013
last_valid_experiment: EXP-011
current_hypothesis: NONE
working_tree_status: only this ledger is intentionally untracked; source and submodule commits remain frozen
owned_processes: NONE; the counted batch shell and paired visible task-station stack were stopped by exact tmux ownership after evidence finalization
preserved_processes: codex-19 and unrelated pre-existing colcon version-check process
confirmed_conclusions:
  - A valid 20-scene first-attempt baseline is complete at 16 successes and 4 product failures with no invalid scene in EXP-011.
  - All electronic, physical, Planning Scene, and visual acceptance evidence for the 16 successes passed the independent analyzer.
  - EXP-010 remains wholly invalid and excluded; no point was silently retried or substituted.
  - Graceful shutdown completed in under two seconds: MoveIt emitted GRACEFUL_SHUTDOWN_MOVE_GROUP_OK, ros2_control_node PID 3991674 and its launch tree exited cleanly, stack launch returned 0, and both owned tmux sessions were removed.
  - ROS_DOMAIN_ID 211 has zero nodes after shutdown; no task process remains and codex-19 is preserved.
disproven_routes:
  - Running the public reset entry without a pre-pause subscriber handshake on this best-effort volatile evidence stream.
  - Treating batch exit code 1, DONE alone, or screenshot alone as the success criterion.
open_risks:
  - The reset subscriber-discovery fix exists only in the task-local harness, not product source.
  - Declared reachability runs before per-point reset; scene 20 therefore has no counted reset epoch and its post-terminal visual/physical world inherits scene 19's residual bilateral contact.
  - Small strata have wide confidence intervals; far/right performance requires more evidence before policy or dataset decisions.
next_command: jq '{counts,funnel,rates,failure_stage_distribution}' /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/analysis/baseline-summary.json
```

## CP-012

```yaml
checkpoint_id: CP-012
last_valid_experiment: EXP-009
current_hypothesis: EXP-011
working_tree_status: only this ledger is intentionally untracked; immutable task artifacts remain below the evidence root
owned_processes: one paired visible task-station stack at MuJoCo PID 3991674; no batch or point child
preserved_processes: codex-19 and unrelated pre-existing colcon version-check process
confirmed_conclusions:
  - EXP-010 stopped after the first shared reset failure and is invalid in full; its eight apparent successes and one perception failure are retained only as diagnostic results.
  - Scene 10 never entered reset, perception, or motion; the exact reset failure reproduces as initial evidence unavailable while the unique simulator remains alive.
disproven_routes:
  - Retrying or extending the invalid EXP-010 batch.
  - Classifying scene 10 as an expert-policy failure.
open_risks:
  - The task-local pre-reset subscriber handshake must prove that it removes only the shared evidence-discovery race before a fresh full batch is allowed.
next_command: Implement the bounded task-local reset-entry adapter, validate it with the planned reset-only A/B, then update EXP-011 before starting the fresh counted batch.
```

## CP-011

```yaml
checkpoint_id: CP-011
last_valid_experiment: EXP-009
current_hypothesis: EXP-010
working_tree_status: only this ledger is intentionally untracked; immutable task artifacts remain below the evidence root
owned_processes: one paired visible task-station stack; no validator or point child
preserved_processes: codex-19 and unrelated pre-existing colcon version-check process
confirmed_conclusions:
  - All 20 independently valid scene positions are frozen before any counted expert attempt.
  - The counted manifest preserves four anchors and 16 fixed-seed continuous samples balanced across near/mid/far and left/center/right strata.
disproven_routes:
  - Filtering the candidate set using expert success, planning success, or perception success.
open_risks:
  - Counted first-attempt outcomes and per-point visual inspection remain to be measured.
next_command: Start EXP-010 once with the exact frozen manifest and monitor without intervention or retries.
```

## CP-010

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-006
current_hypothesis: EXP-009
working_tree_status: only this ledger is intentionally untracked; harness/manifest artifacts remain below the registered evidence root
owned_processes: one paired visible task-station stack; no validator or point child
preserved_processes: codex-19 and unrelated pre-existing colcon version-check process
confirmed_conclusions:
  - EXP-008 stopped before runtime due solely to the wrong Python module path for the public resume helper.
disproven_routes:
  - Importing resume_physics from backends.mujoco.teleop_runtime.
open_risks:
  - Independent candidate reset validity remains unproven.
next_command: Start EXP-009 with the corrected public import and untouched candidate manifest.
```

## CP-009

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-006
current_hypothesis: EXP-008
working_tree_status: only this ledger is intentionally untracked; harness/manifest artifacts remain below the registered evidence root
owned_processes: one paired visible task-station stack; no point child or validator process
preserved_processes: codex-19 and unrelated pre-existing colcon version-check process
confirmed_conclusions:
  - EXP-007 did not test a candidate because paused physics prevented initial evidence acquisition before the first reset.
disproven_routes:
  - Calling standalone transactional reset directly while the persistent batch stack is paused.
open_risks:
  - Independent reset validity for all 20 candidates remains unproven.
next_command: Start EXP-008 with the public resume boundary and the same candidate manifest.
```

## CP-008

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-006
current_hypothesis: EXP-007
working_tree_status: only this ledger is intentionally untracked; all harness/manifest candidates are below the registered evidence root
owned_processes: one paired visible task-station stack; no point child process
preserved_processes: codex-19 and unrelated pre-existing colcon version-check process
confirmed_conclusions:
  - The task_start smoke is accepted end to end with fresh electronic and visually inspected terminal evidence.
  - Candidate generation is deterministic at seed 20260911 and preserves all four required anchors.
disproven_routes:
  - Freezing a candidate manifest before independent reset-only validation.
open_risks:
  - Reset stability for the sixteen continuous points and final manifest freeze remain unproven.
next_command: Run EXP-007 reset-only validation, then freeze the exact manifest hash if and only if all 20 candidates pass.
```

## CP-007

```yaml
checkpoint_id: CP-007
last_valid_experiment: NONE
current_hypothesis: EXP-006
working_tree_status: only this ledger is intentionally untracked; task-local harness remains under the evidence root
owned_processes: one paired visible task-station stack; no point child process
preserved_processes: codex-19 and unrelated pre-existing colcon version-check process
confirmed_conclusions:
  - EXP-005 proves the unchanged task_start expert and physical acceptance chain reaches DONE after fresh Open3D RGB-D perception.
  - Exact-window GNOME capture itself succeeds; only the adapter's interpretation of capture-gui.sh stdout prevented evidence registration.
disproven_routes:
  - Treating capture-gui.sh human-readable receipt output as raw manifest JSON.
open_risks:
  - Corrected artifact registration and a fully accepted smoke remain to be proven.
next_command: Run a no-motion exact-PID capture diagnostic with corrected parsing, then invoke EXP-006 on a fresh reset epoch.
```

## CP-006

```yaml
checkpoint_id: CP-006
last_valid_experiment: NONE
current_hypothesis: EXP-005
working_tree_status: only this ledger is intentionally untracked
owned_processes: one paired visible task-station stack in so101-act-moveit-baseline-exp004; no point child process
preserved_processes: codex-19 and unrelated pre-existing colcon version-check process
confirmed_conclusions:
  - Paired pinned core/support binaries survive transactional pause/reset and create the expected reset epoch.
  - EXP-004 stopped at missing Open3D preflight before perception publication or expert execution.
disproven_routes:
  - Depending on the ai-station system ROS Python alone for the declared Open3D runtime.
open_risks:
  - Combined task-local dependency import, complete expert motion, physical outcome, and successful post-terminal capture remain unproven.
next_command: Verify task-local Open3D plus ROS imports, then invoke EXP-005 on the owned paused stack.
```

## CP-005

```yaml
checkpoint_id: CP-005
last_valid_experiment: NONE
current_hypothesis: EXP-004
working_tree_status: only this ledger is intentionally untracked
owned_processes: NONE
preserved_processes: codex-19 and unrelated pre-existing colcon version-check process; neither task-owned session remains
confirmed_conclusions:
  - EXP-003 proves all seven task_start planning states are reachable on a stable single stack.
  - EXP-003 is invalid before reset because an August 13 historical core and newer support plugin crashed at their callback ABI boundary.
  - The pinned 71bc934 fork was previously qualified on ai-station, but that old evidence root is no longer present and cannot supply runtime binaries.
disproven_routes:
  - Mixing the historical .worktrees MuJoCo control install with current workspace so101_mujoco_support.
open_risks:
  - The paired task-owned build and subsequent transactional reset remain to be proven.
next_command: Build and read back a paired pinned fork/support overlay inside the registered evidence root, then start EXP-004.
```

## CP-004

```yaml
checkpoint_id: CP-004
last_valid_experiment: NONE
current_hypothesis: EXP-003
working_tree_status: only this ledger is intentionally untracked
owned_processes: NONE
preserved_processes: codex-19 only
confirmed_conclusions:
  - Corrected runtime prefixes can load the simulator, RGB-D camera, MoveIt, controllers, and formal scene.
  - EXP-002 invalidated only the cold-start one-shot joint readiness boundary.
disproven_routes:
  - Starting the attached batch before explicit stable readiness on this host.
open_risks:
  - Full expert and capture acceptance remain unproven.
next_command: Start the one owned task-station tmux, prove readiness, then mark EXP-003 RUNNING at attached batch invocation.
```

## CP-003

```yaml
checkpoint_id: CP-003
last_valid_experiment: NONE
current_hypothesis: EXP-002
working_tree_status: only this ledger is intentionally untracked
owned_processes: NONE
preserved_processes: codex-19 only; no application stack remains
confirmed_conclusions:
  - EXP-001 is invalid at pre-MoveIt launch provenance and provides no expert outcome evidence.
  - Current workspace so101_mujoco_support has the required executable; selecting that prefix is the minimum environment correction.
disproven_routes:
  - Using fusion-final/so101_mujoco_support for the current task-station launch.
open_risks:
  - Live readiness, GUI capture PID matching, and complete expert acceptance remain unproven.
next_command: Verify the corrected support prefix and start EXP-002 on a fresh owned tmux session.
```

## CP-002

```yaml
checkpoint_id: CP-002
last_valid_experiment: NONE
current_hypothesis: EXP-001
working_tree_status: only docs/experiments/so101-act-head-wrist-moveit-expert-baseline-experiment-ledger.md is intentionally untracked
owned_processes: NONE
preserved_processes: codex-19; no application stack present
confirmed_conclusions:
  - Restricted-discovery isolated build2 completed with exit 0 and imports so101_demo from the task-owned build2 source link.
  - The installed public batch and task-station launch expose the expected entrypoints and fixed visible sensor-rendering contract.
  - The task-local harness changes only terminal image capture from macOS screencapture to exact-ID GNOME gui-capture.
disproven_routes:
  - The first unrestricted isolated build attempt failed before compilation because colcon rebound three unselected workspace dependencies to an empty install base.
open_risks:
  - EXP-001 must prove live stack readiness and exact-PID window matching.
next_command: Start EXP-001 in a uniquely named task tmux session and monitor its owned process tree to completion.
```

## FULL_RESTART retries dispatched by de50ad48-41a0-4176-997f-198fb4ea3f3c

The following four experiments are independent second attempts for the four valid failures in
EXP-011. They are not amendments to EXP-011 and must not be blended with its first-attempt 16/20
statistic. Each experiment owns one fresh visible stack from launch through graceful shutdown, and
only one formal point invocation is permitted for that experiment ID.

## EXP-012

```yaml
experiment_id: EXP-012
status: VALID
prior_experiment: EXP-011
hypothesis: The EXP-011 sample_05_near_center fitted-radius perception failure may not repeat after a completely independent stack restart.
prediction: The unchanged point either satisfies the full accepted contract or produces one valid independently measured first bad boundary, with no environment or evidence invalidation.
single_variable: One independent second attempt for P09/sample_05_near_center after a complete stack restart; all source, binaries, policy, thresholds, geometry, point coordinates, recovery parameters, sequencing, and success criteria remain unchanged.
lifecycle: FULL_RESTART
preconditions:
  - No prior task-owned stack, process, tmux session, or ROS node remains in ROS_DOMAIN_ID 211.
  - A uniquely named visible stack starts from the qualified paired overlay with simulation_session_id act-moveit-retry-exp012-de50ad48 and canonical robot, MuJoCo cup, and Planning Scene state.
  - Controllers, fresh joint state, Planning Scene, exact runtime executable/prefix, source commit, paired binary hashes, manifest hash, and policy hash all match the frozen provenance.
  - The one-point manifest preserves sample_05_near_center at [0.021124, -0.240778, 0.165].
success_criteria:
  - Fresh dynamic perception is consumed with matching producer/consumer provenance and passes the frozen perception contract.
  - All required MoveIt plans and executions complete with correlated controller results and joint/TF motion.
  - MuJoCo proves bilateral grasp, lift, transport, release, stable supported final placement, no final fingertip contact, and the frozen target tolerance.
  - Planning Scene proves correct attach/detach lifecycle, empty final attached set, synchronized plastic_cup world object, retreat, and cleanup.
  - A fresh exact-PID MuJoCo window screenshot is captured after terminal and visually inspected against the electronic and physical outcome.
failure_criteria:
  - Any normal perception, planning, execution, controller, grasp, lift, transport, release, placement, retreat, cleanup, timeout, or visual failure after valid preconditions is a valid retry failure with its first bad boundary recorded.
  - A declared reachability rejection before reset is a valid independent planning failure when the fresh canonical initial state and provenance are proven; no reset or execution is then claimed.
invalid_criteria:
  - Wrong source/install/runtime/policy/manifest provenance, duplicate stack, noncanonical initial state, reset/session/epoch mismatch, stale or missing required evidence, harness failure, or process contamination.
  - Any second formal point invocation under EXP-012 or any behavior/parameter/coordinate/criterion change invalidates the experiment and stops the campaign.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  fork_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  install_overlay: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/paired-build/{fork,support,demo}/install
  runtime_executable: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/paired-build/fork/install/lib/mujoco_ros2_control/ros2_control_node plus /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/linux_rgbd_batch.py
  policy_sha256: dc17d704ea9a333a387896bf36293a876bedc0be7868bc8b1ea800f4ce19d66d
  manifest_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: tmux new-session -d -s so101-retry-exp012-stack /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/retries/full-restart/EXP-012/start-stack.zsh
    exit_code: 0
  - command: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/retries/full-restart/EXP-012/run-point.zsh 4084290
    exit_code: 1
  - command: tmux send-keys -t so101-retry-exp012-stack C-c; wait for exact session exit; verify ROS_DOMAIN_ID 211 node/process inventory
    exit_code: 0
observed:
  - 2026-09-11T13:47+08:00 the fresh visible stack reached READY with all three controllers active, canonical Planning Scene, exact paired ros2_control_node PID 4084290, one exact MuJoCo window, reset_epoch 0, canonical cup pose [0.020000, -0.280000, 0.164802], table contact, no fingertip contact, and fresh near-zero joint feedback.
  - The first immediate joint-state CLI sample raced topic discovery; a bounded second readiness sample succeeded before any retry invocation. No reset, perception, or motion had run.
  - The sole formal retry created exact reset epoch 1 for [0.021124, -0.240778, 0.165], remained REACHABLE, had no shared failure, then returned RGBD_PERCEPTION_EXITED_EARLY after every fitted frame reported radius 0.019058 m against the frozen 0.040000 +/- 0.010000 m contract.
  - No cup-pose sample reached the waiting consumer and no motion state executed. Post-terminal joint values and TCP remained at their initial pose; MuJoCo showed the upright cup table-supported at [0.021124, -0.240778, 0.164802] with no fingertip contact; Planning Scene remained empty-attached and canonical.
  - The fresh exact-PID window capture used X11 window 50331655. Direct original-resolution inspection shows the arm open in its initial pose and the upright cup at the requested start position outside the red target ring, consistent with a pre-motion perception failure.
  - Exact graceful shutdown emitted GRACEFUL_SHUTDOWN_MOVE_GROUP_OK, ros2_control_node PID 4084290 exited, the owned tmux session disappeared, and ROS_DOMAIN_ID 211 was empty; codex-19 remained untouched.
inferred:
  - The same deterministic fitted-radius boundary seen in EXP-011 repeated on a fully independent stack; this is a valid product retry failure rather than lifecycle or harness invalidation.
conclusion: VALID_RETRY_FAILURE_RGBD_PERCEPTION_RADIUS
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/retries/full-restart/EXP-012
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/batches/retry-exp012-p09-sample-05-near-center
decision: KEEP
next_experiment: EXP-013
```

## EXP-013

```yaml
experiment_id: EXP-013
status: VALID
prior_experiment: EXP-011
hypothesis: The EXP-011 sample_14_far_right pre-MOVE_ABOVE_OBJECT dynamic IK residual failure may not repeat after a completely independent stack restart.
prediction: The unchanged point either satisfies the full accepted contract or produces one valid independently measured first bad boundary, with no environment or evidence invalidation.
single_variable: One independent second attempt for P18/sample_14_far_right after a complete stack restart; all source, binaries, policy, thresholds, geometry, point coordinates, recovery parameters, sequencing, and success criteria remain unchanged.
lifecycle: FULL_RESTART
preconditions:
  - No prior task-owned stack, process, tmux session, or ROS node remains in ROS_DOMAIN_ID 211.
  - A uniquely named visible stack starts from the qualified paired overlay with simulation_session_id act-moveit-retry-exp013-de50ad48 and canonical robot, MuJoCo cup, and Planning Scene state.
  - Controllers, fresh joint state, Planning Scene, exact runtime executable/prefix, source commit, paired binary hashes, manifest hash, and policy hash all match the frozen provenance.
  - The one-point manifest preserves sample_14_far_right at [0.051023, -0.339445, 0.165].
success_criteria:
  - Fresh dynamic perception is consumed with matching producer/consumer provenance and passes the frozen perception contract.
  - All required MoveIt plans and executions complete with correlated controller results and joint/TF motion.
  - MuJoCo proves bilateral grasp, lift, transport, release, stable supported final placement, no final fingertip contact, and the frozen target tolerance.
  - Planning Scene proves correct attach/detach lifecycle, empty final attached set, synchronized plastic_cup world object, retreat, and cleanup.
  - A fresh exact-PID MuJoCo window screenshot is captured after terminal and visually inspected against the electronic and physical outcome.
failure_criteria:
  - Any normal perception, planning, execution, controller, grasp, lift, transport, release, placement, retreat, cleanup, timeout, or visual failure after valid preconditions is a valid retry failure with its first bad boundary recorded.
  - A declared reachability rejection before reset is a valid independent planning failure when the fresh canonical initial state and provenance are proven; no reset or execution is then claimed.
invalid_criteria:
  - Wrong source/install/runtime/policy/manifest provenance, duplicate stack, noncanonical initial state, reset/session/epoch mismatch, stale or missing required evidence, harness failure, or process contamination.
  - Any second formal point invocation under EXP-013 or any behavior/parameter/coordinate/criterion change invalidates the experiment and stops the campaign.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  fork_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  install_overlay: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/paired-build/{fork,support,demo}/install
  runtime_executable: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/paired-build/fork/install/lib/mujoco_ros2_control/ros2_control_node plus /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/linux_rgbd_batch.py
  policy_sha256: dc17d704ea9a333a387896bf36293a876bedc0be7868bc8b1ea800f4ce19d66d
  manifest_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: tmux new-session -d -s so101-retry-exp013-stack /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/retries/full-restart/EXP-013/start-stack.zsh
    exit_code: 0
  - command: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/retries/full-restart/EXP-013/run-point.zsh 4090041
    exit_code: 1
  - command: tmux send-keys -t so101-retry-exp013-stack C-c; wait for exact session exit; verify ROS_DOMAIN_ID 211 node/process inventory
    exit_code: 0
observed:
  - 2026-09-11T13:53+08:00 the fresh visible stack reached READY with all three controllers active, fresh near-zero joint feedback, canonical Planning Scene, exact paired ros2_control_node PID 4090041, one exact MuJoCo window, and session-bound reset_epoch 0 evidence showing the upright cup at [0.020000, -0.280000, 0.164802], table contact, and no fingertip contact.
  - The generic ROS topic CLI briefly lost best-effort evidence discovery; the qualified public current_evidence boundary then returned the required atomic sample without reset or motion. No formal retry had run.
  - The sole formal retry created exact reset epoch 1 for [0.051023, -0.339445, 0.165], remained REACHABLE, locked fresh perception at [0.0506443, -0.3398418, 0.1650000] with fitted radius 0.0394441 m, and returned DYNAMIC_WORKFLOW_FAILED with first bad boundary DYNAMIC_IK_RESIDUAL_EXCEEDED at MOVE_ABOVE_OBJECT (position 0.006311 m, orientation 0.064505 rad).
  - PREPARE_OPEN_GRIPPER and the controller-correlated RECOVER_RETREAT executed successfully. The post-recovery joints were [0.426874, 0.163731, 0.045086, 1.372757, 0.039016, 0.465035]; MuJoCo retained the upright cup at [0.051023, -0.339445, 0.164802] with table contact and no fingertip contact.
  - Post-terminal Planning Scene contained the correct objects and no attachment but reported plastic_cup.pose mismatch, an additional failure-path cleanup inconsistency rather than an environment invalidation.
  - The fresh exact-PID window capture used X11 window 50331655. Direct original-resolution inspection shows the cup upright outside the target ring and the open arm at its recovered retreat pose, with no grasp or transport.
  - Exact graceful shutdown emitted GRACEFUL_SHUTDOWN_MOVE_GROUP_OK, ros2_control_node PID 4090041 exited, the owned tmux session disappeared, and ROS_DOMAIN_ID 211 was empty; codex-19 remained untouched.
inferred:
  - The same MOVE_ABOVE_OBJECT IK residual boundary seen in EXP-011 repeated on a fully independent stack; the post-failure scene-pose mismatch is product cleanup evidence and does not invalidate the retry environment.
conclusion: VALID_RETRY_FAILURE_DYNAMIC_IK_MOVE_ABOVE_OBJECT
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/retries/full-restart/EXP-013
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/batches/retry-exp013-p18-sample-14-far-right
decision: KEEP
next_experiment: EXP-014
```

## EXP-014

```yaml
experiment_id: EXP-014
status: VALID
prior_experiment: EXP-011
hypothesis: The EXP-011 sample_15_far_center LIFT-stage dynamic IK residual failure may not repeat after a completely independent stack restart.
prediction: The unchanged point either satisfies the full accepted contract or produces one valid independently measured first bad boundary, with no environment or evidence invalidation.
single_variable: One independent second attempt for P19/sample_15_far_center after a complete stack restart; all source, binaries, policy, thresholds, geometry, point coordinates, recovery parameters, sequencing, and success criteria remain unchanged.
lifecycle: FULL_RESTART
preconditions:
  - No prior task-owned stack, process, tmux session, or ROS node remains in ROS_DOMAIN_ID 211.
  - A uniquely named visible stack starts from the qualified paired overlay with simulation_session_id act-moveit-retry-exp014-de50ad48 and canonical robot, MuJoCo cup, and Planning Scene state.
  - Controllers, fresh joint state, Planning Scene, exact runtime executable/prefix, source commit, paired binary hashes, manifest hash, and policy hash all match the frozen provenance.
  - The one-point manifest preserves sample_15_far_center at [0.008183, -0.339434, 0.165].
success_criteria:
  - Fresh dynamic perception is consumed with matching producer/consumer provenance and passes the frozen perception contract.
  - All required MoveIt plans and executions complete with correlated controller results and joint/TF motion.
  - MuJoCo proves bilateral grasp, lift, transport, release, stable supported final placement, no final fingertip contact, and the frozen target tolerance.
  - Planning Scene proves correct attach/detach lifecycle, empty final attached set, synchronized plastic_cup world object, retreat, and cleanup.
  - A fresh exact-PID MuJoCo window screenshot is captured after terminal and visually inspected against the electronic and physical outcome.
failure_criteria:
  - Any normal perception, planning, execution, controller, grasp, lift, transport, release, placement, retreat, cleanup, timeout, or visual failure after valid preconditions is a valid retry failure with its first bad boundary recorded.
  - A declared reachability rejection before reset is a valid independent planning failure when the fresh canonical initial state and provenance are proven; no reset or execution is then claimed.
invalid_criteria:
  - Wrong source/install/runtime/policy/manifest provenance, duplicate stack, noncanonical initial state, reset/session/epoch mismatch, stale or missing required evidence, harness failure, or process contamination.
  - Any second formal point invocation under EXP-014 or any behavior/parameter/coordinate/criterion change invalidates the experiment and stops the campaign.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  fork_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  install_overlay: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/paired-build/{fork,support,demo}/install
  runtime_executable: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/paired-build/fork/install/lib/mujoco_ros2_control/ros2_control_node plus /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/linux_rgbd_batch.py
  policy_sha256: dc17d704ea9a333a387896bf36293a876bedc0be7868bc8b1ea800f4ce19d66d
  manifest_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: tmux new-session -d -s so101-retry-exp014-stack /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/retries/full-restart/EXP-014/start-stack.zsh
    exit_code: 0
  - command: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/retries/full-restart/EXP-014/run-point.zsh 4094498
    exit_code: 1
  - command: tmux send-keys -t so101-retry-exp014-stack C-c; wait for exact session exit; verify ROS_DOMAIN_ID 211 node/process inventory
    exit_code: 0
observed:
  - 2026-09-11T13:57+08:00 the fresh visible stack reached READY with all three controllers active, fresh near-zero joint feedback, canonical Planning Scene, exact paired ros2_control_node PID 4094498, one exact MuJoCo window, and session-bound reset_epoch 0 evidence showing the upright cup at [0.020000, -0.280000, 0.164802], table contact, and no fingertip contact. No reset or motion had run.
  - The sole formal retry created exact reset epoch 1 for [0.008183, -0.339434, 0.165], remained REACHABLE, and locked fresh perception at [0.0078312, -0.3400004, 0.1650000] with fitted radius 0.0393283 m.
  - MOVE_ABOVE_OBJECT planned and executed with correlated joint/FK evidence. The first bad boundary was DESCEND, which returned MOVEIT_EXECUTION_MONITOR_ABORTED: DYNAMIC_FORCE_LIMIT_EXCEEDED after left-fingertip contact reached 16.7133 N while the cup remained table-supported.
  - Recovery opened the gripper, detached both shadows, synchronized the world object, and retreated. A later atomic snapshot showed the cup settled at [0.0071721, -0.3381833, 0.1655159], orientation [-0.0110335, -0.0009615, 0.0000238, 0.9999387], table contact, and no final fingertip contact.
  - Post-terminal Planning Scene contained the correct objects and no attachment but reported plastic_cup pose and all 13 primitive-pose mismatches, additional failure-path cleanup evidence rather than environment invalidation.
  - The fresh exact-PID window capture used X11 window 50331655. Direct original-resolution inspection shows the cup outside the target ring, slightly tilted but supported, with the open arm at its recovered retreat pose and no transport.
  - Exact graceful shutdown emitted GRACEFUL_SHUTDOWN_MOVE_GROUP_OK, ros2_control_node PID 4094498 exited, the owned tmux session disappeared, and ROS_DOMAIN_ID 211 was empty; codex-19 remained untouched.
inferred:
  - EXP-014 is a valid independent retry failure, but it does not repeat EXP-011's LIFT-stage IK boundary; run-to-run variation moved the first failure upstream to force monitoring during DESCEND.
conclusion: VALID_RETRY_FAILURE_DESCEND_FORCE_LIMIT
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/retries/full-restart/EXP-014
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/batches/retry-exp014-p19-sample-15-far-center
decision: KEEP
next_experiment: EXP-015
```

## EXP-015

```yaml
experiment_id: EXP-015
status: VALID
prior_experiment: EXP-011
hypothesis: The EXP-011 sample_16_far_right declared MOVE_ABOVE_OBJECT reachability rejection may or may not repeat from an independently proven canonical fresh-stack state.
prediction: The unchanged point either satisfies the full accepted contract or is again validly rejected before reset with no target reset/execution and a screenshot honestly showing the canonical initial scene rather than the requested target.
single_variable: One independent second attempt for P20/sample_16_far_right after a complete stack restart; all source, binaries, policy, thresholds, geometry, point coordinates, recovery parameters, sequencing, and success criteria remain unchanged.
lifecycle: FULL_RESTART
preconditions:
  - No prior task-owned stack, process, tmux session, or ROS node remains in ROS_DOMAIN_ID 211.
  - A uniquely named visible stack starts from the qualified paired overlay with simulation_session_id act-moveit-retry-exp015-de50ad48 and canonical robot, MuJoCo cup, and Planning Scene state independently proven before declared reachability.
  - Controllers, fresh joint state, Planning Scene, exact runtime executable/prefix, source commit, paired binary hashes, manifest hash, and policy hash all match the frozen provenance.
  - The one-point manifest preserves sample_16_far_right at [0.071574, -0.319255, 0.165].
success_criteria:
  - Fresh dynamic perception is consumed with matching producer/consumer provenance and passes the frozen perception contract.
  - All required MoveIt plans and executions complete with correlated controller results and joint/TF motion.
  - MuJoCo proves bilateral grasp, lift, transport, release, stable supported final placement, no final fingertip contact, and the frozen target tolerance.
  - Planning Scene proves correct attach/detach lifecycle, empty final attached set, synchronized plastic_cup world object, retreat, and cleanup.
  - A fresh exact-PID MuJoCo window screenshot is captured after terminal and visually inspected against the electronic and physical outcome.
failure_criteria:
  - Any normal perception, planning, execution, controller, grasp, lift, transport, release, placement, retreat, cleanup, timeout, or visual failure after valid preconditions is a valid retry failure with its first bad boundary recorded.
  - A declared reachability rejection before reset is a valid independent planning failure only after canonical initial state is independently proven; the record must explicitly say no point reset, perception, or execution occurred and the screenshot must remain labeled as canonical-initial-state evidence.
invalid_criteria:
  - Wrong source/install/runtime/policy/manifest provenance, duplicate stack, noncanonical or unproven initial state, reset/session/epoch mismatch, stale/misrepresented/missing evidence, harness failure, or process contamination.
  - Any second formal point invocation under EXP-015 or any behavior/parameter/coordinate/criterion change invalidates the experiment and stops the campaign.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  fork_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  install_overlay: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/paired-build/{fork,support,demo}/install
  runtime_executable: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/paired-build/fork/install/lib/mujoco_ros2_control/ros2_control_node plus /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/linux_rgbd_batch.py
  policy_sha256: dc17d704ea9a333a387896bf36293a876bedc0be7868bc8b1ea800f4ce19d66d
  manifest_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  ros_domain_id: 211
  gz_partition: so101_act_moveit_baseline_20260911
commands:
  - command: tmux new-session -d -s so101-retry-exp015-stack /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/retries/full-restart/EXP-015/start-stack.zsh
    exit_code: 0
  - command: Run a manual exact-PID canonical-state capture without sourcing gui-env; no image was written and no runtime state changed.
    exit_code: 1
  - command: Source the qualified runtime-env and capture canonical-viewer.png from exact MuJoCo PID 4098847/window 50331655 before the point invocation.
    exit_code: 0
  - command: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/retries/full-restart/EXP-015/run-point.zsh 4098847
    exit_code: 0
  - command: tmux send-keys -t so101-retry-exp015-stack C-c; wait for exact session exit; verify ROS_DOMAIN_ID 211 node/process inventory
    exit_code: 0
observed:
  - 2026-09-11T14:01+08:00 the fresh visible stack reached READY with all three controllers active, fresh near-zero joint feedback, canonical Planning Scene, exact paired ros2_control_node PID 4098847, one exact MuJoCo window, and session-bound reset_epoch 0 evidence showing the upright cup at [0.020000, -0.280000, 0.164802], table contact, and no fingertip contact. No reset or motion had run.
  - A first manual capture probe omitted the qualified gui-env and therefore found no PID-matched X11 window; it wrote no image and changed no runtime state. The same read-only capture under runtime-env then matched PID 4098847 to window 50331655 and wrote canonical-viewer.png. Original-resolution inspection shows the open arm and upright cup in the canonical task_start scene outside the target ring.
  - The sole formal retry independently returned REACHABLE, created exact reset epoch 1 for [0.071574, -0.319255, 0.165], and locked fresh perception at [0.0712848, -0.3197365, 0.1650000] with fitted radius 0.0393661 m and 0.000562 m position error.
  - All 19 workflow transitions completed through DONE. Every operational trajectory has terminal joint/FK reconciliation; the final RETREAT TCP was [-0.073491, -0.232048, 0.277546] with terminal position/orientation errors 0.000480 m and 0.000628 rad, and a fresh TF sample agreed at approximately [-0.073, -0.232, 0.278].
  - MuJoCo proved bilateral grasp, table-clear micro-lift at z=0.168902 m, full lift at z=0.224154 m, transport, release, and stable table support. VALIDATE_FINAL_PLACEMENT recorded final pose [-0.0779735, -0.2475113, 0.1647901], XY error 0.002440 m, upright tilt 0.003614 rad, near-zero velocity, and zero final fingertip contacts.
  - MoveIt attachment contained plastic_cup after physical grasp, DETACH_MOVEIT cleared the attached set and restored all three world objects, and SYNC_WORLD_OBJECT passed updated-geometry readback with plastic_cup primitive count 13. The later generic scene_setup observe compared the moved cup against the static task-start geometry and therefore reported pose differences; this command is not a MuJoCo-vs-updated-scene comparator and does not replace the successful dynamic sync receipt.
  - All nine registered point artifacts matched their recorded sizes and SHA256 hashes. The fresh exact-PID terminal capture used X11 window 50331655; direct original-resolution inspection shows the upright cup inside the red target ring with the gripper open and arm retreated.
  - Exact graceful shutdown emitted GRACEFUL_SHUTDOWN_MOVE_GROUP_OK, ros2_control_node PID 4098847 exited, the owned tmux session disappeared, and ROS_DOMAIN_ID 211 was empty; codex-19 remained untouched.
inferred:
  - EXP-011's P20 reachability rejection is not deterministic across independent stack lifecycles; the unchanged second attempt passed the full electronic, physical, Planning Scene, cleanup, and visual contract.
conclusion: VALID_RETRY_SUCCESS_FULL_CONTRACT
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/retries/full-restart/EXP-015
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/batches/retry-exp015-p20-sample-16-far-right
decision: KEEP
next_experiment: NONE
```

## CP-014

```yaml
checkpoint_id: CP-014
last_valid_experiment: EXP-011
current_hypothesis: EXP-012 through EXP-015 independent FULL_RESTART retry measurements
working_tree_status: only docs/experiments/so101-act-head-wrist-moveit-expert-baseline-experiment-ledger.md is intentionally untracked; source and submodule are frozen and clean
owned_processes: NONE; ROS_DOMAIN_ID 211 has zero nodes and no SO-101 application stack is present
preserved_processes: codex-19; no unrelated process was stopped or changed
confirmed_conclusions:
  - EXP-011 remains immutable at 16 successes and 4 valid first-attempt failures under RESET_WORLD.
  - Host AI-STATION-001, worktree, source/submodule commits, exact dirty path, paired overlays and binary hashes, manifest/policy hashes, tmux/process inventory, ROS_DOMAIN_ID 211, and GZ_PARTITION so101_act_moveit_baseline_20260911 were reconciled before stack start.
  - The dispatch receipt contains exactly de50ad48-41a0-4176-997f-198fb4ea3f3c with no trailing newline.
disproven_routes:
  - Blending these FULL_RESTART retries into the EXP-011 RESET_WORLD first-attempt statistic.
  - Retrying a valid failure more than once inside the same experiment ID.
open_risks:
  - Each fresh stack must independently pass cold-start readiness and canonical-state evidence; any harness/environment invalidation stops the campaign.
  - P20 may reject during declared reachability before reset, in which case only canonical-initial-state visual/physical evidence is truthful.
next_command: Start the uniquely owned EXP-012 stack only after the four one-point manifests are created and verified against the frozen candidate manifest.
```

## CP-015

```yaml
checkpoint_id: CP-015
last_valid_experiment: EXP-015
current_hypothesis: NONE
working_tree_status: only docs/experiments/so101-act-head-wrist-moveit-expert-baseline-experiment-ledger.md is intentionally untracked; source and submodule commits remain frozen and clean
owned_processes: NONE; all four retry stack sessions and exact ros2_control_node process trees exited, and ROS_DOMAIN_ID 211 has zero nodes
preserved_processes: codex-19; no unrelated process was stopped or changed
confirmed_conclusions:
  - All four planned retries are VALID under independent FULL_RESTART lifecycles, with one formal point invocation per experiment and no shared failure.
  - Retry success is 1/4: EXP-012, EXP-013, and EXP-014 are valid product failures; EXP-015 is a full-contract success.
  - EXP-011 remains immutable at 16/20 and is statistically separate from these retries.
  - P09 repeated its fitted-radius perception failure; P18 repeated its MOVE_ABOVE_OBJECT dynamic IK residual failure; P19 instead failed earlier at DESCEND force monitoring; P20 changed from pre-reset reachability rejection to complete success.
  - Four unique simulation session IDs, four reset-epoch-0 canonical preflights, four exact paired runtime PIDs, and four graceful shutdowns prove FULL_RESTART isolation.
disproven_routes:
  - Treating P20's EXP-011 declared reachability rejection as deterministic across independent full restarts.
  - Combining the 1/4 retry statistic with EXP-011's 16/20 first-attempt baseline.
open_risks:
  - The sample is only one retry per failure; it measures outcomes but cannot estimate stable per-point probabilities.
  - P19's first bad boundary changed between attempts, indicating run-to-run variability at the far workspace boundary.
  - The task-local reset handshake remains outside product source, and generic static scene_setup observe is not an after-placement MuJoCo-vs-MoveIt pose comparator.
next_command: NONE
```


## Evidence retention classification

- Retained: `/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW` (entire 2.2 GiB task root), including the accepted smoke, frozen manifest and reset validation, invalid EXP-010, valid EXP-011, independent FULL_RESTART retries EXP-012 through EXP-015, paired installed runtime, task-local Python dependencies, full logs, screenshots, contact sheets, retry summary, verification scripts and transcripts, the non-mutating failed EXP-015 canonical-capture probe, and analysis.
- Archived: none.
- Deletion candidates, only after explicit user approval: root-level failed/obsolete preparation trees `build/`, `install/`, `build-log/`, `build2/`, `install2/`, and `build2-log/`; reproducible compilation intermediates under `paired-build/fork/build/`, `paired-build/support/build/`, and `paired-build/demo/build/`; generated `__pycache__/`. Installed paired binaries, `python-deps/`, all logs, all invalid/valid batches, all screenshots, and all analysis remain retained rather than deletion candidates.
- Pytest/colcon scratch: none was created because this task ran no pytest or colcon test command.
- Deletions performed: none.

## Optimization dispatch 3c35b60f-2211-4e2b-aca4-181604915188

This continuation is governed by
`/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/handoffs/dispatch-3c35b60f-2211-4e2b-aca4-181604915188-p09-p18-p19-optimization.md`.
Its receipt was written before any other task action. The registered evidence root remains unchanged;
all new durable artifacts are isolated below
`optimization/3c35b60f-2211-4e2b-aca4-181604915188`. EXP-011 through EXP-015 and their
frozen artifacts remain immutable.

## CP-016

```yaml
checkpoint_id: CP-016
last_valid_experiment: EXP-015
current_hypothesis: P09 backend comparison followed by a shared deterministic whole-prefix planning optimization for P18/P19
working_tree_status: only this pre-existing untracked ledger is dirty; source main@ea0215180ed8cc0a90d6683a5e80d475987b5bc0 and submodule 71bc9346cf93d6227a6678fcacf63f3e18acfcba are unchanged
owned_processes: NONE; no SO-101 application stack is present and ROS_DOMAIN_ID 211 is empty
preserved_processes: codex-19; no unrelated process was stopped or changed
confirmed_conclusions:
  - The dispatch receipt contains exactly 3c35b60f-2211-4e2b-aca4-181604915188 with no trailing newline.
  - The paired fork/support/demo overlays, policy SHA256 dc17d704ea9a333a387896bf36293a876bedc0be7868bc8b1ea800f4ce19d66d, and candidate-manifest SHA256 c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5 match CP-015.
  - The registered YOLO-Seg weights are retained read-only at optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt with SHA256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 and model ID plastic-cup-yolo11s-seg-v2.
  - The registered Grounded-SAM bundle at /data/work/so101-models/grounded-sam-v2-scipy-lock passes its complete manifest/file verification with manifest SHA256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 and model ID grounding-dino-tiny+sam2.1-hiera-tiny.
  - Both formal P09 attempts will use the same task image so101-perception-multibackend:3c35b60f@sha256:bceca1a0bf549ba292c20f3aedab5cb8cc4584c49605222579388a1d323ca104, derived from exact local base sha256:fafdb147fab33758b45f8edb39d6ddb231b38ebe59b99dce17f01a0bf35d3a3e; runtime readback proves ROS rclpy, torch 2.13.0+cu130, transformers 4.56.2, ultralytics 8.4.115, scipy 1.17.1, CUDA availability, and NVIDIA GeForce RTX 5080.
  - The evidence-only multibackend batch wrapper passed py_compile and dry command-contract checks for both backends; it preserves the existing dynamic consumer, robust transactional reset, point policy, full workflow, terminal GNOME exact-PID capture, and acceptance semantics.
disproven_routes:
  - Resolving the local base by its unqualified digest, which caused Docker to query Docker Hub; a task-local tag was bound to the already-proven exact local image ID instead.
  - Treating a bare Docker build-layer Python environment as the ROS runtime; rclpy is correctly verified after /ros_entrypoint.sh sources ROS.
open_risks:
  - Either registered backend may validly reject P09 at detection or localization; no P09 parameter tuning or retry is authorized.
  - Grounded-SAM cold load is materially longer than YOLO-Seg, so the unchanged fresh-frame gate uses the frozen 180 s bounded startup allowance for both backends.
next_command: Materialize and verify the identical one-point P09 manifests and start only EXP-016's isolated YOLO-Seg stack.
```

Preparation transcripts retained under the optimization subtree include the initial model-provenance
wrapper parse failure, the remote digest-resolution timeout, the build-layer rclpy assertion failure,
and the malformed image-inspect assertion. Each stopped before a formal point invocation; corrected
`-r2`/`-r3` transcripts preserve the successful readbacks. No preparation artifact was deleted.

## EXP-016

```yaml
experiment_id: EXP-016
status: VALID
prior_experiment: EXP-012
hypothesis: The registered YOLO-Seg model can segment P09's cup closely enough for the unchanged RGB-D localizer to satisfy the frozen 0.040 +/- 0.010 m radius contract and permit the full MoveIt pick-place workflow.
prediction: The sole attempt either passes the complete frozen task contract or records one valid first bad boundary with fresh source image, backend detections/masks/overlay, localization output, topic-publication log, physical state, and exact-PID terminal screenshot.
single_variable: Use the registered yolo_seg backend and plastic-cup-yolo11s-seg-v2 weights for P09; the point, policy, motion, reset, lifecycle, safety gates, localization thresholds, success criteria, assets, source, and paired stack remain frozen.
lifecycle: FULL_RESTART
preconditions:
  - No SO-101 application stack or conflicting ROS graph exists before start.
  - A unique visible stack starts from the frozen paired runtime and independently proves active controllers, fresh near-zero joints, canonical Planning Scene, reset epoch 0, canonical cup state, and one exact-PID MuJoCo window.
  - The one-point manifest is exactly sample_05_near_center at [0.021124, -0.240778, 0.165].
  - Model, container, source, policy, manifest, session, domain, and partition provenance match CP-016.
success_criteria:
  - Fresh YOLO-Seg output passes the frozen localization contract and publishes a fresh /cup_pose only after the waiting dynamic consumer is discovered.
  - Every frozen workflow, MoveIt/controller/joint/TF, MuJoCo grasp/lift/transport/release/stability, Planning Scene attach/detach/world-sync, retreat/cleanup, and visual acceptance gate passes.
failure_criteria:
  - Any normal backend, detection, localization, planning, execution, controller, force, grasp, placement, cleanup, timeout, or visual failure after valid preconditions is a valid product result with its first bad boundary preserved.
invalid_criteria:
  - Wrong or mixed provenance, duplicate stack, noncanonical initial state, stale/missing required evidence, reset/session mismatch, harness failure, process contamination, or any second formal invocation.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  fork_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  perception_backend: yolo_seg
  model_id: plastic-cup-yolo11s-seg-v2
  model_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  perception_image_id: sha256:bceca1a0bf549ba292c20f3aedab5cb8cc4584c49605222579388a1d323ca104
  ros_domain_id: 221
  gz_partition: so101_opt_3c35_p09_yolo
commands:
  - command: tmux new-session -d -s so101-opt-exp016-stack optimization/3c35b60f-2211-4e2b-aca4-181604915188/EXP-016/start-stack.zsh
    exit_code: 0
  - command: Run canonical readiness; repeat only the read-only /so101/simulation/evidence sample after its first ROS discovery race.
    exit_code: 0
  - command: optimization/3c35b60f-2211-4e2b-aca4-181604915188/EXP-016/run-point.zsh 4190537
    exit_code: 0
  - command: Resume for one post-terminal joint/physical readback, pause via current_evidence, then gracefully stop exact owned stack and verify ROS/domain/container cleanup.
    exit_code: 0
observed:
  - The fresh stack independently reached READY with all three controllers active, fresh near-zero joint feedback, canonical Planning Scene, exact paired ros2_control_node PID 4190537, X11 MuJoCo window 50331655 bound to that PID, and reset epoch 0 physical evidence for the canonical upright table-supported cup with no fingertip contacts.
  - The first simulation-evidence topic sample hit the known discovery race after all earlier readiness gates passed; a bounded read-only repeat returned the canonical epoch-0 sample before any reset, perception, or motion.
  - The sole formal invocation reset sample_05_near_center to exact epoch 1, remained REACHABLE, and produced one fresh CUDA YOLO-Seg candidate at source stamp 132749999999 with confidence 0.957681, 3821 mask pixels, center [0.0211884, -0.2412698, 0.1650000], 0.000496 m position error, and acknowledged /cup_pose publication.
  - The complete dynamic workflow reached DONE through all 18 operational states. Physical evidence proves bilateral grasp, micro-lift, full lift, transport, detach/release, stable table support, zero final fingertip contacts, and final cup pose [-0.0782948, -0.2474257, 0.1648255] with 0.002108 m XY error and 0.004503 rad upright tilt.
  - Planning Scene evidence records plastic_cup attachment during grasp, an empty attached set after detach, all 13 cup primitives restored and synchronized, and a reconciled retreat ending with 0.000501 m TCP position error and 0.000698 rad orientation error.
  - All 21 registered point artifacts match recorded sizes and SHA256 hashes. Original-resolution inspection of the fresh terminal exact-PID screenshot shows an upright cup inside the red target ring, open gripper, and retreated arm; the prediction overlay visibly confines the segmentation to the cup.
  - Graceful shutdown removed exact PID 4190537 and the owned tmux session; ROS_DOMAIN_ID 221 and the task container inventory were empty afterward, while codex-19 remained untouched.
inferred:
  - Registered YOLO-Seg removes P09's prior color-geometry radius failure without any localization, motion, safety, or acceptance tuning; this isolated attempt passes the full contract.
conclusion: VALID_FULL_CONTRACT_SUCCESS_YOLO_SEG
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/EXP-016
decision: KEEP
next_experiment: EXP-017
```

## EXP-017

```yaml
experiment_id: EXP-017
status: VALID
prior_experiment: EXP-016
hypothesis: The registered Grounded-SAM pipeline can segment P09's cup closely enough for the unchanged RGB-D localizer to satisfy the frozen 0.040 +/- 0.010 m radius contract and permit the full MoveIt pick-place workflow.
prediction: The sole attempt either passes the complete frozen task contract or records one valid first bad boundary with fresh source image, backend detections/masks/overlay, localization output, topic-publication log, physical state, and exact-PID terminal screenshot.
single_variable: Use the registered grounded_sam backend and grounding-dino-tiny+sam2.1-hiera-tiny bundle for P09; all point, policy, motion, reset, lifecycle, safety gates, localization thresholds, success criteria, assets, source, paired stack, and container runtime inputs remain identical to EXP-016.
lifecycle: FULL_RESTART
preconditions:
  - EXP-016's exact owned process tree and ROS graph have fully exited before this independently named visible stack starts.
  - The fresh stack independently satisfies the same canonical readiness gates frozen in EXP-016.
  - The one-point manifest is byte-identical to EXP-016's manifest and contains only sample_05_near_center at [0.021124, -0.240778, 0.165].
  - Model, container, source, policy, manifest, session, domain, and partition provenance match CP-016.
success_criteria:
  - Fresh Grounded-SAM output passes the frozen localization contract and publishes a fresh /cup_pose only after the waiting dynamic consumer is discovered.
  - Every frozen workflow, MoveIt/controller/joint/TF, MuJoCo grasp/lift/transport/release/stability, Planning Scene attach/detach/world-sync, retreat/cleanup, and visual acceptance gate passes.
failure_criteria:
  - Same valid product-failure boundary as EXP-016 after valid preconditions.
invalid_criteria:
  - Same environment, provenance, evidence, lifecycle, and single-invocation invalidation boundaries as EXP-016.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0
  fork_commit: 71bc9346cf93d6227a6678fcacf63f3e18acfcba
  perception_backend: grounded_sam
  model_id: grounding-dino-tiny+sam2.1-hiera-tiny
  model_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
  perception_image_id: sha256:bceca1a0bf549ba292c20f3aedab5cb8cc4584c49605222579388a1d323ca104
  ros_domain_id: 222
  gz_partition: so101_opt_3c35_p09_grounded
commands:
  - command: Verify EXP-016 exact stack/domain/container cleanup, then tmux new-session -d -s so101-opt-exp017-stack optimization/3c35b60f-2211-4e2b-aca4-181604915188/EXP-017/start-stack.zsh
    exit_code: 0
  - command: Run canonical readiness and exact PID/window binding on ROS_DOMAIN_ID 222.
    exit_code: 0
  - command: optimization/3c35b60f-2211-4e2b-aca4-181604915188/EXP-017/run-point.zsh 1516
    exit_code: 0
  - command: Resume for post-terminal readback; after a joint-topic discovery race, obtain session-bound current_evidence, pause, gracefully stop exact owned stack, and verify domain/container cleanup.
    exit_code: 0
observed:
  - After EXP-016 cleanup, the independent stack reached READY with all controllers active, fresh near-zero joints, canonical Planning Scene, exact paired ros2_control_node PID 1516, X11 window 50331655 bound to that PID, and canonical reset epoch 0 table-supported cup evidence with no fingertip contacts.
  - The sole formal invocation reset the byte-identical sample_05_near_center manifest to exact epoch 1, remained REACHABLE, and produced one fresh CUDA Grounded-SAM candidate at source stamp 108831999999 with detector confidence 0.897298, SAM quality 0.953356, 4231 mask pixels, center [0.0212048, -0.2412218, 0.1650000], 0.000490 m position error, and acknowledged /cup_pose publication.
  - Model provenance contains the complete verified offline bundle manifest with SHA256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775; cold start was 5875.55 ms and inference was 210.61 ms in the same pinned container used by EXP-016.
  - The complete dynamic workflow reached DONE through all 18 operational states. Physical evidence proves bilateral grasp, micro-lift, full lift, transport, detach/release, stable table support, zero final fingertip contacts, and final cup pose [-0.0782792, -0.2473829, 0.1648211] with 0.002110 m XY error and 0.004392 rad upright tilt.
  - Planning Scene evidence records attachment during grasp, empty attachment after detach, all 13 cup primitives restored and synchronized, and retreat ending with 0.000470 m TCP position error and 0.000524 rad orientation error.
  - All 21 registered artifacts pass size and SHA256 readback. Original-resolution terminal inspection shows an upright cup inside the red ring with open gripper and retreated arm; the overlay visibly confines the selected Grounded-SAM mask to the cup.
  - The first separate post-terminal joint sample hit a ROS discovery race, while the workflow's terminal reconciliation was already complete; a session-bound current_evidence readback proved stable table contact, zero fingertip contacts, epoch 1, and then paused the world. Graceful shutdown removed exact PID 1516, its tmux session and the task container; ROS_DOMAIN_ID 222 was empty and codex-19 remained untouched.
inferred:
  - Registered Grounded-SAM also removes P09's prior color-geometry radius failure without tuning and passes the full contract. For this fixed scene it produced a slightly larger mask than YOLO-Seg, with similar localization accuracy but higher cold-start and inference latency.
conclusion: VALID_FULL_CONTRACT_SUCCESS_GROUNDED_SAM
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/EXP-017
decision: KEEP
next_experiment: P18_P19_IMPLEMENTATION
```

## CP-017

```yaml
checkpoint_id: CP-017
last_valid_experiment: EXP-019
current_hypothesis: The first EXP-020 regression rejection was a safe sampled-trajectory rejection of one OMPL path, not intrinsic unreachability of the previously successful sample_16_far_right endpoint.
working_tree_status: implementation and focused tests are uncommitted; the pre-existing ledger remains preserved
owned_processes: NONE after exact EXP-020 shutdown and GUI cleanup readback
confirmed_conclusions:
  - EXP-018 and EXP-019 independently completed P18 and P19 under FULL_RESTART with the shared deterministic whole-prefix horizon and unchanged safety gates.
  - EXP-020 stopped before reset or motion because actual MoveIt sampled-corridor validation rejected MOVE_ABOVE_OBJECT with CARTESIAN_CORRIDOR_ORIENTATION.
  - EXP-020 then proved the epoch-0 cup physically settled on the table, canonical Planning Scene readback synchronized, exact owned stack stopped, and MuJoCo window absent.
recording_note: EXP-018 through EXP-020 were materialized as immutable per-run manifests before execution, but their ledger blocks were appended here after their terminal readback instead of before stack start; this ordering deviation is preserved explicitly and is not rewritten.
next_command: Execute one independently restarted, unchanged-code EXP-021 repeat of the previously successful sample_16_far_right regression to test the bounded-OMPL-path hypothesis; do not repeat again if its first boundary differs or remains rejected.
```

## EXP-018

```yaml
experiment_id: EXP-018
status: VALID
prior_experiment: EXP-017
hypothesis: The shared deterministic bounded multistart whole-prefix planner can resolve P18 and validate every actual MoveIt path before physical motion.
single_variable: Apply the shared planning implementation to sample_14_far_right; force, policy, geometry, lifecycle, and acceptance tolerances remain unchanged.
lifecycle: FULL_RESTART
provenance:
  point: sample_14_far_right [0.051023, -0.339445, 0.165]
  ros_domain_id: 223
  gz_partition: so101_opt_3c35_p18
observed:
  - Independent readiness, source-backed runtime readback, full workflow DONE, physical placement, 13-primitive world restoration, fresh screenshot inspection, post-terminal stable evidence, and exact owned cleanup all passed.
  - The horizon admitted a complete nine-waypoint pick prefix and retained 374 candidate receipts; all actual MoveIt sampled corridors passed before execution.
conclusion: VALID_FULL_CONTRACT_SUCCESS_P18
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/EXP-018
decision: KEEP
```

## EXP-019

```yaml
experiment_id: EXP-019
status: VALID
prior_experiment: EXP-018
hypothesis: The same shared planner can resolve P19's downstream lift posture while validating its six-segment descent on actual MoveIt trajectory samples.
single_variable: Point changes from P18 to sample_15_far_center; implementation, policy, force, geometry, lifecycle, and acceptance tolerances remain unchanged.
lifecycle: FULL_RESTART
provenance:
  point: sample_15_far_center [0.008183, -0.339434, 0.165]
  ros_domain_id: 224
  gz_partition: so101_opt_3c35_p19
observed:
  - Independent readiness, full workflow DONE, physical placement, fresh screenshot inspection, exact dynamic Planning Scene pose readback, and exact owned cleanup all passed.
  - The horizon admitted a complete nine-waypoint pick prefix and retained 374 candidate receipts; all actual MoveIt sampled corridors passed, including all six DESCEND segments, MICRO_LIFT, and LIFT.
conclusion: VALID_FULL_CONTRACT_SUCCESS_P19
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/EXP-019
decision: KEEP
```

## EXP-020

```yaml
experiment_id: EXP-020
status: VALID
prior_experiment: EXP-019
hypothesis: The shared planner preserves the prior full-restart success at nearby far point sample_16_far_right.
single_variable: Point changes to the previously successful sample_16_far_right; code and all policy/safety/acceptance inputs remain unchanged.
lifecycle: FULL_RESTART
provenance:
  point: sample_16_far_right [0.071574, -0.319255, 0.165]
  ros_domain_id: 225
  gz_partition: so101_opt_3c35_regression
observed:
  - Canonical independent readiness passed.
  - Before reset or motion, reachability rejected the first actual MOVE_ABOVE_OBJECT MoveIt trajectory with CARTESIAN_CORRIDOR_ORIENTATION.
  - Failure cleanup proved the epoch-0 cup stable, the canonical scene synchronized, the exact stack stopped, and no MuJoCo window remained.
conclusion: VALID_SAFE_PREFLIGHT_REJECTION; regression success criterion not met
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/EXP-020
decision: PRESERVE_AND_ONE_CONTROLLED_REPEAT
```

## EXP-021

```yaml
experiment_id: EXP-021
status: VALID
prior_experiment: EXP-020
hypothesis: Because EXP-020's deterministic endpoint horizon passed and only one valid but excessive-orientation OMPL path was rejected, one fresh stack may produce a different safe sampled path to the same previously successful endpoint without changing any code or tolerance.
prediction: Independent readiness passes and the unchanged point either completes full DONE with all physical, Planning Scene, terminal, visual, and cleanup gates, or records one final regression failure without a further repeat.
single_variable: Independent FULL_RESTART lifecycle only; point, source, build, planner settings, randomization behavior, policy, model, force, geometry, and every tolerance are byte-for-byte unchanged from EXP-020.
lifecycle: FULL_RESTART
preconditions:
  - EXP-020 exact owned process and MuJoCo GUI are absent.
  - A unique ROS domain, partition, session and evidence directory are used.
success_criteria:
  - Same full physical DONE and evidence contract as EXP-018/EXP-019.
failure_criteria:
  - Any normal reachability, sampled-corridor, execution, physical, scene, or acceptance failure after valid readiness is retained as the final regression result.
invalid_criteria:
  - Mixed provenance, duplicate stack, stale initial state, missing evidence, or any code/config/tolerance change from EXP-020.
provenance:
  point: sample_16_far_right [0.071574, -0.319255, 0.165]
  ros_domain_id: 226
  gz_partition: so101_opt_3c35_regression_r2
observed:
  - Independent canonical readiness passed with unchanged point-manifest SHA256 3a64a9ba06d967803361a2cdb806f4a6f2f41c780879fdb048ba2713b54bcdfb.
  - Reachability again rejected the first MOVE_ABOVE_OBJECT actual MoveIt path with CARTESIAN_CORRIDOR_ORIENTATION before reset or motion.
  - Epoch-0 physical settle, canonical Planning Scene synchronization, exact graceful shutdown, and GUI cleanup all passed.
conclusion: VALID_SAFE_PREFLIGHT_REJECTION; repeated P20 regression route disproved
decision: PRESERVE_AND_DO_NOT_REPEAT
```

## EXP-022

```yaml
experiment_id: EXP-022
status: VALID
prior_experiment: EXP-021
hypothesis: The same shared implementation preserves sample_13_far_center, a nearby far point that completed the frozen counted baseline and is 18.637 mm from P19 in XY.
prediction: The independently restarted unchanged stack completes full workflow DONE with physical pick-place, actual sampled-corridor receipts, synchronized 13-primitive world cup, exit zero, fresh inspected screenshot, and exact cleanup.
single_variable: Regression point changes from the disproved P20 route to historically successful sample_13_far_center; source, runtime, policy, perception model, force, geometry, planner settings, and tolerances remain unchanged.
lifecycle: FULL_RESTART
preconditions:
  - Frozen EXP-011 records sample_13_far_center as SUCCEEDED/REACHABLE.
  - EXP-021 exact owned stack and MuJoCo GUI are absent.
  - A unique ROS domain, partition, session and evidence directory are used.
success_criteria:
  - Same full physical DONE and evidence contract as EXP-018/EXP-019.
failure_criteria:
  - Any normal product failure after valid readiness is retained; no silent substitution or further regression retry.
invalid_criteria:
  - Mixed provenance, duplicate stack, stale initial state, missing evidence, or any source/config/tolerance change.
provenance:
  point: sample_13_far_center [0.007874, -0.3208, 0.165]
  prior_evidence: counted-20-scene-first-attempt-r2 point 17 SUCCEEDED
  ros_domain_id: 227
  gz_partition: so101_opt_3c35_regression_sample13
observed:
  - Independent readiness passed with all controllers active, canonical initial scene, exact task-owned runtime prefixes, the source-backed deterministic_horizon.py, and one MuJoCo window.
  - The workflow reached DONE through all 19 transitions. The deterministic horizon admitted three complete paths and retained 374 candidate receipts; every actual MoveIt sampled corridor was accepted before execution.
  - Physical terminal evidence recorded a stable table-supported cup, no fingertip contacts, and no attached MoveIt object; all 13 world primitives were restored.
  - Fresh post-terminal readback measured 0.001197 m between the physical cup and Planning Scene cup, 0.0000091 rad orientation difference, 13 primitives and no attachment.
  - Original-resolution inspection shows the cup upright inside the target ring, open gripper and retreated arm. All 21 artifact hashes/sizes passed readback; exact graceful shutdown and final GUI cleanup passed.
conclusion: VALID_FULL_CONTRACT_SUCCESS_NEARBY_FAR_REGRESSION
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/EXP-022
decision: KEEP
```

## CP-018

```yaml
checkpoint_id: CP-018
last_valid_experiment: EXP-022
current_hypothesis: NONE; the authorized outcome and minimum verification are complete
working_tree_status:
  - Uncommitted implementation changes are limited to task_reachability.py, underactuated_ik.py, dynamic_mujoco_execution.py, task_reachability.py ROS adapter, three related test files, and the new deterministic_horizon.py plus its test.
  - The pre-existing untracked experiment ledger remains uncommitted and now contains this monotonic continuation.
  - No commit or push was performed.
owned_processes: NONE; ROS domains 221 through 227 are empty, all seven recorded task stack PIDs are absent, no MuJoCo window remains, and no task perception container is running
confirmed_causes:
  - P18 failed previously because execution used one custom-IK seed while reachability used a different MoveIt pose-goal contract; viable multistart solutions existed but were never considered by execution.
  - P19's greedy stage-by-stage endpoint selection did not reserve a downstream-feasible lift posture and six endpoints did not validate the intervening TCP path; baseline evidence therefore alternated between lift residual and unsafe descent-force boundaries.
implementation:
  - deterministic_horizon.py adds current-state, prior-stage, structured base/yaw and frozen-bank seeds, deterministic bounded beam search, complete-path scoring for residual, joint margin, continuity and kinematic clearance, candidate receipts, chosen-path reason, and actual MoveIt trajectory TCP corridor validation.
  - Reachability and execution now resolve the same explicit horizon joint goals rather than pose goals versus single-seed joint goals; both reject the same actual sampled-path failure codes.
  - The full pick prefix is admitted before first motion: MOVE_ABOVE_OBJECT, six DESCEND waypoints, MICRO_LIFT and LIFT. Execution caches and uses those exact selected joint targets.
  - The force limit remains 11.60 N. Position, orientation, displacement, geometry, scene and acceptance tolerances were not relaxed. Simulator truth remains evaluation/audit only.
verification:
  - RED transcripts reproduce missing shared horizon behavior, reachability mismatch and execution mismatch under tests/red-002.typescript through red-004.typescript; the initial quoting-only tests-red-001.typescript is retained as preparation history.
  - Focused GREEN culminated in 34 passed; final-focused-001.typescript independently reconfirmed 34 passed in 11.44 s with /usr/bin/python3 and tempfile rooted at scratch/final-focused-001/tmp.
  - The broad source-backed package gate tests/package-pytest-010.typescript passed 1675 tests with 1 skipped in 37.46 s, excluding only test_installed_provenance.py because task-local setuptools copies intentionally lack Git-source identity. The earlier unfiltered venv gate passed 1677 tests and exposed only two pre-existing paired-prefix layout assertions; all intermediate transcripts remain retained.
  - build-merged.typescript and build-isolated.typescript exited zero; readiness for EXP-018, EXP-019 and EXP-022 read back the paired fork/support/demo prefixes and source-backed deterministic_horizon.py actually consumed at runtime.
  - final-static-001.typescript reports eight files formatted, Ruff checks passed, and git diff --check passed.
  - artifact-readback.typescript rehashed all 21 artifacts for each of EXP-016, EXP-017, EXP-018, EXP-019 and EXP-022, plus the YOLO weights, with no mismatch.
live_results:
  - EXP-016 P09 YOLO-Seg: one authorized attempt, SUCCEEDED/DONE. Model SHA256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781; dynamic manifest ac02c51f1a05177ec148ef588cb62ac95b9493151dac29f529594556be3705f4; screenshot adc8a401522d0137734fa65a64882999238a768ef78ba04620c4c736b67db8f2; overlay 12aa0882ca7c36e4b97a36ceeb369fd2ad5fc735dfa2beb9fd9ab7923da38e85.
  - EXP-017 P09 Grounded-SAM: one authorized attempt, SUCCEEDED/DONE. Bundle manifest SHA256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775; dynamic manifest fead3daab280c939a618a92cd8c52856b0229ae841b2cdbda83fed2e7bc94aeb; screenshot 022d17739c2ea2ffea0abcc62e98cbb4a6cfe1757bb250de919c98db01927b9a; overlay b84686ea50c7c94466c2b2f3430917e222573d4685d1fd5dc6762c2d64085f66.
  - EXP-018 P18: SUCCEEDED/DONE with 374 horizon candidate receipts. Actual MoveIt MOVE_ABOVE_OBJECT used 77 samples and stayed within 0.044311 m / 0.098148 rad; all close-contact corridors passed. Dynamic manifest 68cfaeb1c0939b6604b82b83c000dbb8dc95de3217bef31215f4aac848e9e760; screenshot 3ea05114f41ce584b04a2bab74b0742a3463739201361cb7402caca49c223b24.
  - EXP-019 P19: SUCCEEDED/DONE with 374 candidate receipts. Its selected first waypoint had 0.001828 m position residual and 0.014386 rad orientation residual; six actual DESCEND corridors stayed below 0.000431 m deviation, MICRO_LIFT below 0.000032 m, and LIFT below 0.001701 m. Dynamic manifest 3190fd5f4a6ee0cf1ed0dfd2bc94f55993abae7b595238cbaef3c22242a2758c; screenshot d386196598f6e20b165470fb8dd044f5f4d9fdc3b918f9bcae1f12681e52187e.
  - EXP-020 and EXP-021 are preserved valid safe preflight rejections for sample_16_far_right; both stopped before reset/motion at CARTESIAN_CORRIDOR_ORIENTATION and ended in stable canonical state with synchronized scene and exact cleanup.
  - EXP-022 nearby far regression sample_13_far_center: SUCCEEDED/DONE, dynamic manifest d4aeac6a261a443fe4e4764edef33c302ec061bd2c964a1111855a495a0aee84, screenshot 8fdd3e75a3d468a5b6f34b9ef3e9d3d6ac795287167a7c1a40ec5db810159f84.
remaining_risks:
  - The underlying OMPL plan service is stochastic. The unchanged strict sampled-orientation gate repeatably rejects sample_16_far_right on these new stacks even though historical EXP-015 succeeded; this point should not be treated as a deterministic regression sentinel without a separately authorized bounded trajectory-selection improvement.
  - The task-local paired overlay emits warnings for one stale historical top-level develop hook while all explicit package-prefix and source-module readbacks select the registered paired runtime.
retention:
  retained:
    - Entire /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW root, currently 2.8 GiB.
    - Entire immutable optimization/3c35b60f-2211-4e2b-aca4-181604915188 subtree, currently 612 MiB, including successful and failed experiments, screenshots, models/provenance, tests, builds, logs and readbacks.
  archived: NONE
  deletion_candidates_after_explicit_user_approval:
    - All optimization scratch directories red-001 through red-004, green-001 through green-005, package-pytest-001 through package-pytest-010, and final-focused-001; every tree was retained after readback.
    - Reproducible optimization build intermediates merged-build, merged-install, merged-log, isolated-build, isolated-install, isolated-log and unified build intermediates.
    - Generated optimization __pycache__ and .pytest_cache directories.
  deletions_performed: NONE
next_command: NONE
```
## CP-019

```yaml
checkpoint_id: CP-019
last_valid_experiment: EXP-022
current_hypothesis: A bounded candidate-plan selector plus a strict pre-acceptance perception fallback controller can produce one coherent 20-of-20 RESET_WORLD batch without weakening any safety or acceptance gate.
working_tree_status:
  - Preserved modified files: src/so101_demo_py/src/application/task_reachability.py, src/so101_demo_py/src/control/moveit/underactuated_ik.py, src/so101_demo_py/src/ros/dynamic_mujoco_execution.py, src/so101_demo_py/src/ros/task_reachability.py, src/so101_demo_py/test/test_dynamic_execute.py, src/so101_demo_py/test/test_task_reachability_ros.py.
  - Preserved untracked files: docs/experiments/so101-act-head-wrist-moveit-expert-baseline-experiment-ledger.md, src/so101_demo_py/src/control/moveit/deterministic_horizon.py, src/so101_demo_py/test/test_deterministic_ik_horizon.py.
  - Source remains main@ea0215180ed8cc0a90d6683a5e80d475987b5bc0 with submodule third_party/mujoco_ros2_control@71bc9346cf93d6227a6678fcacf63f3e18acfcba; no commit, push, reset, stash, clean, or deletion was performed.
owned_processes: NONE; no SO-101 stack, MuJoCo window, MoveIt node, RViz process, or task perception container was present
preserved_processes: codex-19 tmux session and unrelated colcon version-check process
confirmed_conclusions:
  - EXP-011 is the authoritative frozen RESET_WORLD baseline: 16/20 full successes and four valid product failures.
  - EXP-016 and EXP-017 independently prove YOLO-Seg and Grounded-SAM can each publish an accepted fresh P09 cup pose and reach full physical DONE.
  - EXP-018, EXP-019, and EXP-022 prove the shared deterministic horizon at P18, P19, and nearby sample_13; EXP-020 and EXP-021 repeatably reject P20 at CARTESIAN_CORRIDOR_ORIENTATION before reset or motion.
  - The frozen 20-point manifest SHA256 is c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5 and matches EXP-011, frozen-manifest.json, and 20 independently validated table-geometry/reset receipts.
disproven_routes:
  - Retrying a single P20 stochastic OMPL path until it passes.
  - Invoking Grounded-SAM after YOLO has already published and the consumer has accepted a cup pose.
open_risks:
  - P20 requires bounded candidate planning and actual sampled-trajectory validation without changing endpoint, force, corridor, or acceptance tolerances.
  - Fallback must distinguish allowed pre-acceptance failures from a published/acknowledged YOLO pose and must fail closed on stale attempt, source-stamp, session, acknowledgement, or fallback failure.
next_command: Add failing contract tests for bounded MoveIt candidate selection and YOLO-first pre-acceptance-only fallback, record RED, then implement the minimum source/harness changes and run focused GREEN plus the package gate using registered NVMe scratch.
```

## EXP-023

```yaml
experiment_id: EXP-023
status: VALID
prior_experiment: EXP-022
hypothesis: With the already validated deterministic endpoint horizon, selecting one passing trajectory from a deterministic bounded set of MoveIt plans for each selected target prevents P20's repeated single-path sampled-orientation rejection; a strict attempt controller can simultaneously run YOLO-Seg first and invoke Grounded-SAM only for allowed failures before any accepted cup pose.
prediction: After RED/GREEN tests, package build/readback, canonical initial readback, and exact stack ownership, one fresh 20-point RESET_WORLD batch runs the frozen manifest in order with consecutive reset epochs and every point terminates SUCCEEDED/DONE; every point records YOLO outcome, fallback decision/reason, accepted backend, exact model provenance, fresh source stamp, confidence/quality, mask size, center, and pose error.
single_variable: Add bounded MoveIt trajectory-candidate selection for the already selected horizon joint targets and add a strict YOLO-first perception attempt controller; all source commit lineage, 20 points/order, policy, force limit 11.60 N, IK horizon endpoints, geometry, corridor thresholds, reset, physical, Planning Scene, terminal, visual, and cleanup acceptance gates remain unchanged.
lifecycle: RESET_WORLD
preconditions:
  - Focused RED/GREEN and source-backed package tests pass from a unique /data NVMe scratch rooted under reset-world-20/8a87dc3e-9836-4feb-8f3c-3286b1efcaff.
  - Product/task-local overlays are rebuilt and source, install, runtime executable, model, policy, manifest, ROS domain, partition, and dirty-state provenance is recorded and read back.
  - Exactly one owned persistent visible stack exists; controllers, near-zero joints, Planning Scene, physical cup/table/contact state, simulation session, reset epoch, and exact MuJoCo window/PID binding are canonical before point 1.
  - The points file is byte-identical to candidate-points.yaml SHA256 c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5 and contains exactly the EXP-011 order.
success_criteria:
  - Exactly 20 point roots are allocated in order and reset epochs are unique and consecutive on the same persistent stack.
  - Each point attempts YOLO-Seg first; Grounded-SAM is absent after an accepted YOLO pose and, when invoked, has an explicit allowed pre-acceptance reason and uses the same reset/session/fresh source acquisition contract.
  - All 20 points reach full workflow SUCCEEDED/DONE with correlated MoveIt plan/execute, controller/joint/TF, bilateral physical grasp/lift/transport/release/stable placement, empty final attachment, 13-primitives synchronized world cup, retreat, zero unsafe final contact, and fresh inspected exact-window screenshot evidence.
  - All registered artifacts pass path, size, and SHA256 readback and exact owned stack/container/window cleanup passes after terminal readback.
failure_criteria:
  - Any valid perception, reachability, planning, sampled-corridor, execution, controller, force, grasp, transport, release, placement, scene, cleanup, timeout, or visual failure terminates this batch as a preserved valid product failure; do not continue or accumulate successful retries.
invalid_criteria:
  - Wrong/mixed provenance, duplicate stack, noncanonical initial state, reset/session/epoch divergence, stale source/attempt/acknowledgement evidence, harness failure, missing required artifact, or process/evidence contamination invalidates and terminates the whole batch.
provenance:
  source_commit: ea0215180ed8cc0a90d6683a5e80d475987b5bc0 plus the preserved uncommitted deterministic-horizon baseline and this dispatch's bounded additions
  install_overlay: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/reset-world-20/8a87dc3e-9836-4feb-8f3c-3286b1efcaff/install
  runtime_executable: /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/reset-world-20/8a87dc3e-9836-4feb-8f3c-3286b1efcaff/implementation/fallback_rgbd_batch.py sha256 1778a3cbe34028e352f4b72141a2b342521ec56f35d8456a0806b91653aa66ab
  ros_domain_id: 228
  gz_partition: so101_reset20_8a87dc3e
commands:
  - command: python3 /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/reset-world-20/8a87dc3e-9836-4feb-8f3c-3286b1efcaff/implementation/fallback_rgbd_batch.py --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --yolo-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --points /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/manifest/candidate-points.yaml --batch-id formal-reset20-candidate-001 --session-id act-reset20-8a87dc3e --evidence-root /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/reset-world-20/8a87dc3e-9836-4feb-8f3c-3286b1efcaff --dynamic-policy /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/reset-world-20/8a87dc3e-9836-4feb-8f3c-3286b1efcaff/install/share/so101_demo_py/config/policies/dynamic_cup_pick/v1/mujoco.yaml --attach-existing-stack --mujoco-pid 190502
    exit_code: 1
  - command: zsh /data/work/ws_moveit/.codex-task/8a87dc3e-9836-4feb-8f3c-3286b1efcaff/plan-diagnostic-r3.zsh
    exit_code: 0
  - command: zsh /data/work/ws_moveit/.codex-task/8a87dc3e-9836-4feb-8f3c-3286b1efcaff/run-batch-002.zsh 190502
    exit_code: 0
observed:
  - RED-003 failed exactly on the two missing controls: stop_on_point_failure and OwnedPointProcesses.stop(role); GREEN-002 then passed 2/2.
  - Expanded focused GREEN-003 passed 95/95; the established source-backed ordinary package gate passed 1698 with 1 skip; the isolated installed-provenance gate passed 4/4; Ruff passed all dispatch-touched Python and task-local runner files.
  - The task-local merged overlay built so101_mujoco_support and so101_demo_py successfully; frozen manifest and pinned model hashes remain unchanged.
  - RUNNING was recorded before the owned stack launch, GUI capture, or formal batch execution.
  - Canonical readiness-r3 passed on the one owned visible stack: MuJoCo PID 190502, session act-reset20-8a87dc3e, reset epoch 0, all three controllers active, all six joints near zero, synchronized 13-primitive cup world object with no attachment, stable table support with no fingertip contact, and exact client window 50331655. The fresh paused initial screenshot was inspected and shows the robot at task start with the upright cup on the table.
  - formal-reset20-candidate-001 terminated fail-closed after P03. P01 and P02 were SUCCEEDED/DONE at reset epochs 1 and 2; P03 accepted a fresh YOLO-Seg pose at epoch 3 and then failed DYNAMIC_TARGET_UNREACHABLE at the first MOVE_ABOVE_OBJECT sampled-orientation corridor. Grounded-SAM was correctly absent because the YOLO pose had already been accepted. No P04 root was allocated.
  - Twelve unchanged plan-only repeats of the exact P03 perceived point all failed CARTESIAN_CORRIDOR_ORIENTATION, disproving additional whole-path stochastic sampling as the remedy. The failed batch, its three point roots, terminal screenshot, chain receipts, and all plan-only failures remain retained.
  - RED-004 reproduced the missing bounded Cartesian MOVE_ABOVE waypoint contract. The minimum implementation subdivides only the existing start-to-MOVE_ABOVE Cartesian pose into six normalized pose waypoints for the shared reachability/execution horizon; target endpoints, tolerances, force, geometry, and acceptance policy are unchanged.
  - GREEN-005 passed the new contract 1/1 and GREEN-006 passed the related source-backed suite 99/99. After rebuilding the task overlay, the exact live P03 plan-only diagnostic changed from 12/12 failures to SUCCEEDED/REACHABLE across all seven declared motion states without executing a trajectory; the stack returned paused at reset epoch 3.
  - Final source-backed ordinary package gate package-pytest-009 passed 1699 with 1 skip, installed-pytest-003 passed 4/4 against the declared merged task prefix, Ruff and git diff --check passed. Invalid environment/staging attempts package-pytest-006 through 008 and installed-pytest-002 are retained with their unique verified NVMe scratch trees.
  - The first prebatch-002 readback correctly rejected stale Planning Scene cup pose left by the pre-motion P03 failure. A transactional task_start reset advanced epoch 3 to 4 and synchronized the scene. The bounded-discovery prebatch-002-r3 readback then passed controllers, near-zero joints, exact task overlay/source, 13 cup primitives, no attachment, stable table support, no fingertip contact, one PID-bound MuJoCo window, and fresh original-resolution visual inspection.
  - formal-reset20-candidate-002 completed all 20 frozen points in order on the same persistent stack at consecutive reset epochs 5 through 24. Every point reached SUCCEEDED/REACHABLE and its dynamic execution manifest reached DONE with the exact 20-state trace, admitted 14-step pick prefix, empty final attachment, 13 synchronized cup primitives, stable table support, no final fingertip contact, and low terminal velocities.
  - All 20 perception chains attempted YOLO-Seg first and accepted that first result with a fresh source stamp, matching session/reset token, publication acknowledgement, pinned weights SHA256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781, confidence 0.919480 through 0.973342, mask size 3671 through 4945 pixels, and maximum cup-pose error 0.000535 m. Grounded-SAM fallback count was zero.
  - Fail-closed batch readback independently rehashed path, size, and SHA256 for 420 registered point artifacts and passed all 20 workflow, perception-chain, session/epoch, Planning Scene, contact, terminal-stability, and exact-window contracts. Batch result SHA256 is 0199c9cc19982fd732353be864567a3235610e6865d8930dff6bf10097aa5851; validator report SHA256 is 1314e7cc4f728f8a4c42298f1d9bbb8737149632868c8e4c60902080f746daaa.
  - Original-resolution viewer captures for P01 through P20 were each inspected: every frame shows an upright table-supported cup inside the red target ring and an open, retreated gripper clear of the cup. The synchronized paused terminal capture SHA256 is 3502a9e772dd3c71cc5f7781d946f2cff4d4f06bd72b6b212586396239329189.
  - Terminal synchronization at epoch 24 paused MuJoCo, confirmed exactly one table contact, zero left/right fingertip contacts, negligible cup velocity, no attachment, and an exact 13-primitive Planning Scene readback with no mismatch. terminal-sync.json SHA256 is 7999fb797085c404df1518f238cbbdbb327af4d7586561ae3fa0045468e8ece6.
  - Graceful Ctrl-C removed the owned tmux session and all live launch, ROS, MuJoCo, controller, perception-container, and exact-window resources; ROS domain 228 is empty and unrelated codex-19 remains. PID 190378 persists only as a resource-free zombie owned by the shared tmux server, which was not killed because it hosts codex-19; cleanup-readback.json records this explicitly and has SHA256 763ca091477f07d40c691073bc6856b70b3db30eb6917c3078ddb4b094688e15.
inferred:
  - NONE
conclusion: VALID_FULL_20_OF_20_RESET_WORLD_YOLO_FIRST
evidence:
  - /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/reset-world-20/8a87dc3e-9836-4feb-8f3c-3286b1efcaff
decision: KEEP
next_experiment: NONE
```

## CP-020

```yaml
checkpoint_id: CP-020
last_valid_experiment: EXP-023
current_hypothesis: NONE; the dispatched 20-point RESET_WORLD qualification is complete
working_tree_status:
  - Preserved modified files: src/so101_demo_py/src/application/task_batch.py, src/so101_demo_py/src/application/task_reachability.py, src/so101_demo_py/src/control/moveit/underactuated_ik.py, src/so101_demo_py/src/ros/dynamic_mujoco_execution.py, src/so101_demo_py/src/ros/dynamic_runtime.py, src/so101_demo_py/src/ros/task_reachability.py, src/so101_demo_py/src/runtime/task_batch_runtime.py, and six related test files.
  - Preserved untracked files: .codex-task task staging, this experiment ledger, src/so101_demo_py/src/control/moveit/deterministic_horizon.py, and src/so101_demo_py/test/test_deterministic_ik_horizon.py.
  - Source remains main@ea0215180ed8cc0a90d6683a5e80d475987b5bc0 with submodule third_party/mujoco_ros2_control@71bc9346cf93d6227a6678fcacf63f3e18acfcba. No commit, push, reset, stash, clean, evidence deletion, or real-robot action was performed.
implementation:
  - The batch/runtime boundary is fail-fast and tracks point-owned perception roles; accepted perception receipts carry reset epoch, session, source stamp, publication acknowledgement, backend decision, model provenance, and the POSE_ACCEPTED token.
  - The fallback controller requires YOLO-Seg first and permits Grounded-SAM only for enumerated failures before any accepted/published YOLO pose; it fails closed on stale identity, disallowed reason, acknowledgement, or process-lifecycle mismatch.
  - Reachability and execution use the same deterministic bounded horizon and actual MoveIt sampled-corridor validation. MOVE_ABOVE_OBJECT is represented by six normalized Cartesian pose waypoints, preserving the same endpoint, force limit, geometry, and acceptance tolerances.
verification:
  - RED-003 and RED-004 captured the missing fail-fast/process-role and bounded MOVE_ABOVE waypoint contracts; GREEN-002 passed 2/2, GREEN-003 passed 95/95, GREEN-005 passed 1/1, and GREEN-006 passed 99/99.
  - The final source-backed ordinary package gate passed 1699 tests with 1 skip from verified /data NVMe scratch package-pytest-009; the installed-provenance gate passed 4/4 from installed-pytest-003. Ruff and git diff --check passed.
  - Immediately before integration, precommit-package-003 independently reran the source-backed ordinary package gate and passed 1699 tests with 1 skip in 36.73 s; precommit-installed-003 reran the installed-overlay provenance gate and passed 4/4 in 2.71 s. Both exact interpreters resolved tempfile inside unique task-owned /data NVMe scratch directories. The two preceding package runner attempts were retained as invalid environment assembly evidence and did not collect product tests.
  - The task-local merged overlay built successfully; source-diff.patch SHA256 is 2a6d007dc120100f742e619da8e185983451b6a039b9a7e0aac859b93f9831d1 and fallback_rgbd_batch.py SHA256 is 1778a3cbe34028e352f4b72141a2b342521ec56f35d8456a0806b91653aa66ab.
  - Invalid setup/staging attempts and their verified unique scratch directories remain retained; none was silently discarded or counted as a passing gate.
live_result:
  - Batch formal-reset20-candidate-002: 20/20 SUCCEEDED/DONE, exact manifest order, one session act-reset20-8a87dc3e, consecutive epochs 5 through 24, 20 YOLO-Seg-first acceptances, zero Grounded-SAM fallbacks, and 420 hash-verified artifacts.
  - Visual review passed 20/20 exact-window captures plus the synchronized paused terminal capture; no tipped, airborne, held, interpenetrating, or fingertip-contact cup state was observed.
  - Terminal synchronization passed at epoch 24 with one table contact, zero fingertip contacts, no attachment, 13 cup primitives, no scene mismatch, and negligible physical velocity.
cleanup:
  - Owned tmux session so101-reset20-8a87dc3e, all live recorded child processes including MuJoCo PID 190502, ROS domain 228 nodes, live containers, and exact window 0x3000007 are absent.
  - The unrelated codex-19 tmux session is preserved. Defunct launcher PID 190378 remains a resource-free zombie under the shared tmux server and is explicitly recorded rather than killing that unrelated shared server.
retention:
  retained:
    - Entire /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW root, currently 3.4 GiB.
    - Entire reset-world-20/8a87dc3e-9836-4feb-8f3c-3286b1efcaff dispatch subtree, currently 679 MiB, including failed batch 001, successful batch 002, all screenshots, manifests, logs, validation, builds, models/provenance references, and scratch trees.
  archived: NONE
  deletion_candidates_after_explicit_user_approval:
    - Scratch directories red-001 through red-004, green-001 through green-006, package-pytest-001 through package-pytest-009, and installed-pytest-001 through installed-pytest-003 under this dispatch.
    - Pre-commit scratch directories precommit-package-001 through precommit-package-003 and precommit-installed-003; package attempts 001 and 002 are retained environment-assembly failures, while package 003 and installed 003 are the counted fresh gates.
    - Reproducible task build, install, log, Python cache, and .pytest_cache intermediates; failed or superseded validation transcripts remain auditable and are included only as potential candidates after review.
  deletions_performed: NONE
next_command: NONE
```
