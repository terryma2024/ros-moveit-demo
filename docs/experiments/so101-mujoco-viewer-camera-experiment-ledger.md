---
task_id: so101-mujoco-viewer-camera
goal: provide four reproducible table-corner debug views without changing physics
success_contract: all four presets round-trip through set/get, preserve physics lifecycle, and show the full robot base cup and main table in fresh CUA screenshots
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
branch: codex/so101-mujoco-ros2
base_commit: 2de4a0ef4cf26e333a56d6c57d5b440060a38624
current_commit: 076c9bb72dc293131758c0d5c7c394aaba248b37
fork_commit: 9f02f82aae2888d6e29c472c6dd64c34b38c5f93
fork_tag: so101-0.0.3-r2
workspace_env: SO101_WORKSPACE_DIR
workspace_default: repo_parent
install_overlay: /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install
runtime_executable: /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install/lib/mujoco_ros2_control/ros2_control_node
evidence_root: /tmp/so101-debug-mujoco-viewer-camera/
task_status: TASK_10_COMPLETE
latest_checkpoint: CP-008
current_experiment: EXP-003 VALID
next_experiment: NONE
---

# SO-101 MuJoCo Viewer Camera Experiment Ledger

Raw logs and screenshots remain under the evidence root. This ledger is the only persistent record
of experiment state and conclusions. Experiments follow `PLANNED -> RUNNING -> VALID | INVALID`.

## Experiment EXP-001

```yaml
experiment_id: EXP-001
prior_experiment: NONE
status: PLANNED
lifecycle: FULL_RESTART
hypothesis: A fork-overlay GUI stack exposes a writable and readable free viewer camera whose measured reference can generate four symmetric table-corner views without affecting simulation lifecycle or controller state.
independent_variable: MuJoCo viewer free-camera pose, followed by 90-degree azimuth rotations through the typed camera service.
controlled_variables: HEAD 2de4a0ef4cf26e333a56d6c57d5b440060a38624; fork f58e2fdc5ed06af98dd58fdf36080e0f989d64f7 tag so101-0.0.3-r1; source order /opt/ros/jazzy -> fork overlay -> project overlay; ROS_DOMAIN_ID 191; simulation_session_id viewer-camera-exp001-domain191; normal unpaused physics; no reset, pause, step, qpos, qvel, controller, object-pose, or Teleop operation.
acceptance_criteria: All four set responses and independent get responses match; reset_epoch is unchanged; simulation_step advances; named controller states remain active and unchanged; four fresh CUA frames each show the complete arm, gripper, base, cup, and main table without important clipping, with visibly distinct directions and consistent scale.
invalid_criteria: Nonempty domain 191 before launch, provenance mismatch, wrong executable/interface prefix, unowned process, missing service, missing camera read-back, CUA busy/session conflict, incomplete fresh screenshots, or cleanup ambiguity invalidates the measurement.
evidence_path: /tmp/so101-debug-mujoco-viewer-camera/exp-001/
domain_id: 191
owned_processes: Reserved task-owned tmux session so101-mujoco-camera; not started at PLANNED registration.
preserved_processes: Existing codex, codex-cua, codex-teleop, kimi, so101-mujoco-gui, so101-phy5-v2-r0, and so101-py-qual tmux sessions; domain-138 MoveIt process; domain-189 Gazebo/MoveIt processes; EXP-057 remains RUNNING and is not terminalized.
result: PENDING
next_command: Verify CUA remains idle and domain 191 remains empty, then start only so101-mujoco-camera.
```

## Experiment EXP-001 Terminal Result

```yaml
experiment_id: EXP-001
status: INVALID
result: GUI_EVIDENCE_PLUGIN_CONCURRENCY_CRASH
owned_processes: Task-owned launch PID 2377033 and ros2_control_node PID 2377046 exited; so101-mujoco-camera remains as an idle shell for later owned reuse.
observed: The fork executable loaded, created reset/pause/step and set/get viewer-camera services, initialized the GUI viewer, and then SIGSEGV occurred in mj_contactForce while SimulationEvidencePlugin::update built evidence from mj_data_control_ concurrently with the physics thread copying that buffer.
evidence: /tmp/so101-debug-mujoco-viewer-camera/exp-001/gui-launch.log
visual_actions: NONE; CUA remained idle and no snapshot/action session was started.
preserved_processes: All preregistered unrelated sessions/processes and EXP-057 were untouched.
decision: Repair the owning fork synchronization boundary with TDD, publish a new fork release, rebuild, and preregister EXP-002 before another FULL_RESTART.
```

## Checkpoint CP-002

```yaml
checkpoint_id: CP-002
last_valid_experiment: NONE
current_experiment: NONE
working_tree_status: HEAD 2de4a0ef4cf26e333a56d6c57d5b440060a38624; index empty; this ledger plus the three preserved Task13 files are untracked.
owned_processes: NONE; the Task-owned tmux shell remains, but its launch tree exited after the invalid crash.
preserved_processes: Existing unrelated sessions/processes and EXP-057 remain unchanged.
confirmed_conclusions:
  - EXP-001 is invalid before visual measurement because its evidence boundary crashed.
  - The fault stack is inside mj_contactForce called from the evidence plugin on mj_data_control_.
  - PhysicsLoop writes mj_data_control_ under sim_mutex_, while MujocoSystemInterface::read currently invokes plugin update without that mutex; this is the owning data race.
  - Fork TDD produced the exact unlocked-read RED, then the minimal read lock passed the focused test and the complete 129-test fork regression; commit 9f02f82aae2888d6e29c472c6dd64c34b38c5f93 and tag so101-0.0.3-r2 were pushed to Gitee before the project gitlink update.
open_risks:
  - A fork read-lock correction must pass focused RED/GREEN, the entire 128-test fork regression, and a real GUI restart before calibration.
next_command: Add a fork test proving read/plugin update waits for sim_mutex_, then implement the minimal lock.
```

## Checkpoint CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_experiment: EXP-001 PLANNED
working_tree_status: HEAD 2de4a0ef4cf26e333a56d6c57d5b440060a38624; index empty; only this ledger plus the three preserved Task13 files are untracked.
owned_processes: NONE; so101-mujoco-camera does not exist and domain 191 has no ROS daemon or observed process.
preserved_processes: Existing sessions and processes listed in EXP-001 remain untouched. The so101-mujoco-gui session is preserved even though its earlier ros2_control process exited; EXP-057 remains RUNNING in its separate ledger.
confirmed_conclusions:
  - codex-cua is at an idle shell prompt and the cua-driver daemon is running.
  - Fork source, installed interfaces, project build, headless live service contract, and package regression passed before this experiment.
  - The three preserved Task13 files are config/contact_calibration.yaml, scripts/analyze_contact_calibration.py, and test/test_contact_calibration_contract.py under src/so101_mujoco_demo_py.
open_risks:
  - The GUI reference camera has not been measured or visually accepted.
next_command: Start the preregistered FULL_RESTART GUI stack in so101-mujoco-camera on domain 191.
```

## Experiment EXP-002

```yaml
experiment_id: EXP-002
prior_experiment: EXP-001 INVALID
status: VALID
lifecycle: FULL_RESTART
hypothesis: Fork release r2 removes the evidence-buffer race, allowing an unpaused GUI stack to remain stable while camera state is measured and four symmetric presets are round-tripped without lifecycle or controller changes.
independent_variable: MuJoCo viewer free-camera pose and successive 90-degree azimuth rotations through the typed camera service.
controlled_variables: HEAD 076c9bb72dc293131758c0d5c7c394aaba248b37; fork 9f02f82aae2888d6e29c472c6dd64c34b38c5f93 tag so101-0.0.3-r2; source order /opt/ros/jazzy -> fork overlay -> project overlay; ROS_DOMAIN_ID 192; simulation_session_id viewer-camera-exp002-domain192; normal unpaused physics; evidence plugin enabled; no reset, pause, step, qpos, qvel, controller, object-pose, or Teleop operation.
acceptance_criteria: The GUI remains stable; all four set responses and independent get responses match; reset_epoch is unchanged; simulation_step advances; named controller states remain active and unchanged; four fresh CUA frames each show the complete arm, gripper, base, cup, and main table without important clipping, with visibly distinct directions and consistent scale.
invalid_criteria: Nonempty domain 192 before launch, provenance mismatch, wrong executable/interface prefix, unowned process, crash, missing service/evidence/camera read-back, CUA busy/session conflict, incomplete fresh screenshots, or cleanup ambiguity invalidates the measurement.
evidence_path: /tmp/so101-debug-mujoco-viewer-camera/exp-002/
domain_id: 192
owned_processes: so101-mujoco-camera shell PID 2376826; launch PID/PGID 2393227; tee PID 2393228; fork ros2_control_node PID 2393256; robot_state_publisher PID 2393255; remaining launch children share PGID 2393227.
preserved_processes: All sessions/processes listed in EXP-001; EXP-057 remains RUNNING and untouched.
result: VALID; baseline evidence is reset_epoch 0, simulation_step 1367, paused false, with all three named controllers active. After four set/get round trips, reset_epoch remained 0, simulation_step advanced to 27607, paused remained false, and all three controller states remained active. Each independent YAML read-back exactly matched its preset.
visual_result: CUA snapshots s029b, s029c, s029d, and s029e show visibly distinct table-corner directions at consistent scale; every frame contains the complete robot arm, gripper, base, cup, and main table without important geometry clipping.
screenshot_evidence: table_corner_nw.png sha256 53c5238f7b277b328246091314b0265afa9893dbbe3b6e64e1605796ffbe5010; table_corner_ne.png sha256 9cdf991405b8b4a78f6197c168480d65c4c27db78d824527d31d6328badfd356; table_corner_se.png sha256 119da4f0d876b0b40c6613af8d755d0d7d6f688e34127633563fb4927265f34e; table_corner_sw.png sha256 bba0c2c4baf70613ca5e74f41da764db6b683c8bd0082740961558107443ed11.
readback_evidence: /tmp/so101-debug-mujoco-viewer-camera/exp-002/table_corner_{nw,ne,se,sw}-readback.log
next_command: Pre-register EXP-003 against this accepted visual calibration before collecting the final no-pause physics-invariance qualification in the same lifecycle.
```

## Checkpoint CP-003

```yaml
checkpoint_id: CP-003
last_valid_experiment: NONE
current_experiment: EXP-002 PLANNED
working_tree_status: HEAD 076c9bb72dc293131758c0d5c7c394aaba248b37; index empty; this ledger and the three preserved Task13 files are untracked.
owned_processes: Idle so101-mujoco-camera shell PID 2376826 only; no child launch process.
preserved_processes: Existing unrelated sessions/processes and EXP-057 remain unchanged.
confirmed_conclusions:
  - Fork r2 was pushed before project gitlink commit 076c9bb72dc293131758c0d5c7c394aaba248b37.
  - The r2 installer, 129-test fork regression, static dependency contracts, and runtime provenance validation are GREEN.
  - Domain 192 has no ROS daemon or observed process; codex-cua remains at an idle prompt.
open_risks:
  - GUI stability and the visual/camera acceptance contract remain unproven after r2.
next_command: Launch EXP-002 and update ownership/status to RUNNING before any CUA action.
```

## Checkpoint CP-004

```yaml
checkpoint_id: CP-004
last_valid_experiment: NONE
current_experiment: EXP-002 RUNNING
working_tree_status: HEAD 076c9bb72dc293131758c0d5c7c394aaba248b37; index empty; this ledger and the three preserved Task13 files are untracked.
owned_processes: so101-mujoco-camera shell 2376826; launch/PGID 2393227; tee 2393228; robot_state_publisher 2393255; fork ros2_control_node 2393256; all remaining launch children are task-owned under PGID 2393227.
preserved_processes: Existing unrelated sessions/processes and EXP-057 remain unchanged.
confirmed_conclusions:
  - r2 GUI remained alive through readiness and baseline sampling with the evidence plugin enabled.
  - Reset/pause/step and set/get camera services exist; three named controllers are active.
  - Baseline evidence is session viewer-camera-exp002-domain192, reset_epoch 0, simulation_step 1367, paused false.
  - Initial viewer state is a free camera at lookat [0.0, -0.20000000000000004, 0.12404123391314203], distance 1.2451965895004553, azimuth 135.0, elevation -20.0, orthographic false.
open_risks:
  - No CUA frame has yet confirmed the full robot/base/gripper/cup/table composition.
next_command: Start a new window-only CUA session and take the required fresh baseline snapshot before any camera action.
```

## Checkpoint CP-005

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-002
current_experiment: EXP-002 VALID
working_tree_status: HEAD 076c9bb72dc293131758c0d5c7c394aaba248b37; Task 9 camera config, production invariant, and this ledger are intentional changes; the three Task13 files remain untracked and untouched.
owned_processes: EXP-002 GUI lifecycle remains running under so101-mujoco-camera shell 2376826 and launch PGID 2393227 so Task 10 can preregister and qualify camera switching without a restart.
preserved_processes: Existing unrelated sessions/processes and EXP-057 remain unchanged.
confirmed_conclusions:
  - Measured free-camera state is lookat [0.0, -0.20000000000000004, 0.12404123391314203], distance 1.2451965895004553, azimuth 135.0, elevation -20.0, orthographic false.
  - The four production records preserve every measured field except successive normalized 90-degree azimuth rotations: 135, 45, -45, and -135 degrees.
  - Each apply plus independent get round-trip matched exactly.
  - CUA snapshots s029b through s029e satisfy the complete robot, gripper, base, cup, and table visual contract with consistent scale and no important clipping.
  - reset_epoch remained 0, simulation_step advanced from 1367 to 27607, paused remained false, and joint_state_broadcaster, arm_controller, and gripper_controller stayed active.
open_risks:
  - Task 10 still must compare time-bounded joint-state deltas around switching with a no-switch baseline and run every final automated gate.
next_command: Commit Task 9, then preregister EXP-003 before recording any Task 10 numeric qualification evidence.
```

## Experiment EXP-003

```yaml
experiment_id: EXP-003
prior_experiment: EXP-002 VALID
status: VALID
lifecycle: CONTINUATION
hypothesis: Applying all four accepted viewer-camera presets during normal unpaused physics does not reset or pause simulation, alter controller lifecycle, or introduce a camera-aligned joint-position discontinuity beyond the no-switch baseline.
independent_variable: Four viewer-camera service calls in NW, NE, SE, SW order during one timestamped joint-state recording.
controlled_variables: HEAD dfc03d3; fork 9f02f82aae2888d6e29c472c6dd64c34b38c5f93 tag so101-0.0.3-r2; source order /opt/ros/jazzy -> /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install -> project install; ROS_DOMAIN_ID 192; GUI session so101-mujoco-camera; simulation_session_id viewer-camera-exp002-domain192; normal running state inherited from EXP-002; no reset, pause, step, controller, object-pose, qpos, qvel, or Teleop operation.
acceptance_criteria: reset_epoch is unchanged; simulation_step strictly increases; joint_state_broadcaster, arm_controller, and gripper_controller remain active; all four set/get round trips succeed; the maximum adjacent per-joint delta in each switch window introduces no discontinuity relative to the no-switch baseline; EXP-002 CUA screenshots remain the accepted visual evidence.
invalid_criteria: GUI crash, service/read-back failure, reset or pause change, controller lifecycle change, non-increasing simulation_step, missing timestamped joint-state windows, switch-window discontinuity, provenance drift, or process ownership ambiguity.
evidence_path: /tmp/so101-debug-mujoco-viewer-camera/exp-003/
domain_id: 192
owned_processes: Continued so101-mujoco-camera shell PID 2376826; launch PID/PGID 2393227; tee PID 2393228; fork ros2_control_node PID 2393256; robot_state_publisher PID 2393255.
preserved_processes: All unrelated sessions/processes and EXP-057 remain untouched.
result: VALID; reset_epoch remained 0 and simulation_step advanced from 42368 to 44782 while paused remained false. Before/after controller files are byte-identical (sha256 7a77a1a30f36e653f8069ae0f3dbf8d9becc0126d605ad632dec60a4edc4006e), with joint_state_broadcaster, arm_controller, and gripper_controller active. Four set/get read-backs matched. The 301-sample no-switch baseline and four switch windows of 246, 305, 277, and 304 samples each had maximum adjacent position delta 0 for every one of six joints, so camera calls introduced no discontinuity relative to baseline.
callback_boundary: Viewer camera set/get take sim_mutex_ in third_party/mujoco_ros2_control/mujoco_ros2_control/src/mujoco_system_interface.cpp lines 2763 and 2782; read/plugin update takes the same lock from line 1502.
unit_boundary: HeadlessInitTest.ViewerCameraSetGetPreservePhysicsState at test_headless_init.cpp:364 proves qpos, qvel, ctrl, and xfrc_applied remain unchanged; HeadlessInitTest.ReadWaitsForSimulationMutexAndUpdatesPluginsUnderTheLock at line 282 proves synchronized evidence reads.
visual_boundary: EXP-002 CUA snapshots s029b through s029e and their absolute screenshot paths remain the accepted four-view visual evidence.
cleanup: CUA session viewer-camera-exp002 ended successfully; launch PGID 2393227 and children exited after Ctrl-C; the exact task tmux session so101-mujoco-camera was removed; domain 192 had no daemon; unrelated sessions/processes and EXP-057 were untouched.
next_command: Run every final automated gate from a fresh shell, record results, and commit only this ledger plus the integration guide.
```

## Checkpoint CP-006

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-002
current_experiment: EXP-003 RUNNING
working_tree_status: HEAD dfc03d3; only this ledger is intentionally modified; the three Task13 files remain untracked and untouched.
owned_processes: EXP-003 continues the exact task-owned EXP-002 GUI process tree; no restart or pause occurred between experiments.
preserved_processes: Existing unrelated sessions/processes and EXP-057 remain unchanged.
confirmed_conclusions:
  - EXP-002 provides accepted CUA visual evidence and exact four-preset read-backs.
  - EXP-003 was preregistered before its first qualification sample or camera action.
open_risks:
  - Time-bounded joint-delta and final lifecycle/controller comparisons are not yet collected.
next_command: Save before evidence/controllers, then capture baseline and switch-window joint-state streams.
```

## Checkpoint CP-007

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-003
current_experiment: EXP-003 VALID
working_tree_status: HEAD dfc03d3; this ledger and the integration guide are intentional Task 10 changes; the three Task13 files remain untracked and untouched.
owned_processes: NONE; the Task 9/10 CUA session, GUI process tree, tmux session, and domain 192 daemon state were cleanly closed after evidence capture.
preserved_processes: so101-mujoco-gui and every other unrelated session/process remain; EXP-057 remains RUNNING and untouched.
confirmed_conclusions:
  - All four camera set/get round trips succeeded in one unpaused lifecycle.
  - reset_epoch stayed 0, simulation_step increased 2414 steps, and all three controller states remained active.
  - The no-switch baseline and every camera-switch window had maximum adjacent joint-position delta 0 across all six joints; no camera-aligned discontinuity was introduced.
  - Fork unit tests bind camera calls to unchanged qpos/qvel/ctrl/xfrc arrays and both camera callbacks/read-plugin updates to sim_mutex_.
  - EXP-002's four CUA screenshots remain accepted and are not replaced by numeric service evidence.
open_risks:
  - Fresh-shell installer, complete fork/project tests, provenance, isolation, formatting, and remote read-back remain to be run.
next_command: Run the Task 10 final gates, then update the terminal checkpoint with exact results.
```

## Checkpoint CP-008

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-003
current_experiment: EXP-003 VALID
working_tree_status: HEAD dfc03d3; only this ledger and the integration guide are intentional staged candidates; the three Task13 files remain untracked and untouched.
owned_processes: NONE
preserved_processes: so101-mujoco-gui and every unrelated session/process remain; EXP-057 remains RUNNING and untouched.
confirmed_conclusions:
  - Fresh env-isolated installer rebuilt the Gitee fork overlay and reported 129 tests, 0 errors, 0 failures, 0 skipped.
  - Fresh project colcon test reported 504 tests, 0 errors, 0 failures, 6 skipped; the Python package portion reported 249 passed and 4 skipped. The preserved untracked Task13 contract test was discovered but not modified or staged.
  - Ruff 0.15.20 reported all checks passed and 73 files formatted; the script's Bash shebang was honored because the plan's zsh invocation is incompatible with its BASH_SOURCE use.
  - check_mujoco_runtime.py returned provider gitee_fork_submodule, fork commit 9f02f82aae2888d6e29c472c6dd64c34b38c5f93, tag match, empty source status, expected prefixes/hashes, and validation_errors [].
  - Migration isolation, git diff --check, and clean fork status passed.
  - EXP-003 proved unchanged epoch/controller lifecycle and no joint discontinuity; EXP-002 provides four accepted CUA screenshots and exact preset read-backs.
evidence:
  - /tmp/so101-debug-mujoco-viewer-camera/task10-installer.log
  - /tmp/so101-debug-mujoco-viewer-camera/task10-project-tests.log
  - /tmp/so101-debug-mujoco-viewer-camera/task10-static-gates.log
  - /tmp/so101-debug-mujoco-viewer-camera/exp-002/
  - /tmp/so101-debug-mujoco-viewer-camera/exp-003/
open_risks: NONE within the viewer-camera preset scope; Teleop Web UI and RGB-D sensor camera remain explicitly deferred.
next_command: Commit the guide and qualification checkpoint, then push and verify remote read-back in dependency order.
```
