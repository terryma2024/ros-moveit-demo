---
task_id: so101-mujoco-ros2-migration
goal: Replace the Gazebo Python demonstration with an independently packaged MuJoCo ROS 2 demonstration.
success_contract: The MuJoCo implementation satisfies its ROS 2 and physical outcome contracts without changing or depending on the protected Gazebo Python tree.
main_base_commit: d300e7a41fb274d6d7e120699b7040666ea61904
task_base_commit: 45c6efc701b133c45875e86b0053cfc37dab7f4f
behavior_source_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
rejected_backup_commit: 3add34f8390b78a1f4a13ff49aefb2dc87638245
rejected_backup_branch: codex/so101-mujoco-ros2-pre-isolation-20260810
branch: codex/so101-mujoco-ros2
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
base_commit: d300e7a41fb274d6d7e120699b7040666ea61904
last_verified_implementation_commit: 263818aabc5a6be09db8baaa137eb18668081d42
ledger_commit_pending: false
task_status: TASK_9_COMPLETE
evidence_root: /tmp/so101-debug-mujoco-migration/
protected_nontracked_baseline_sha256: 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f
strict_physics_contract: The successful positive path must use physical contact and grasp forces with no weld, no equality constraint, no adhesion or adhesive actuator, no mocap body, no teleport or set-pose, no direct object qpos writes, and no direct object qvel writes.
confirmed_conclusions:
  - The rebased migration starts from the exact main baseline; CP-001.
disproven_routes:
  - The pre-isolation backup is provenance only and is not an implementation source; CP-001.
open_hypotheses:
  - The behavior source can be migrated to MuJoCo while preserving the strict no-weld/no-teleport contract.
latest_checkpoint: CP-013
next_experiment: EXP-013
---

# SO-101 MuJoCo ROS 2 Migration Experiment Ledger

Raw logs, screenshots, videos, bags, and build artifacts belong only under the evidence root. The
ledger records conclusions and evidence references, never copied raw evidence. Experiments must use
the `PLANNED -> RUNNING -> VALID | INVALID` state transitions from the SO-101 development workflow.

## Checkpoint CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The behavior source can be migrated without a Gazebo Python runtime dependency and without weld or teleport shortcuts.
working_tree_status: Clean baseline plus the three Task 1 isolation deliverables pending their single scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - HEAD before the Task 1 commit is 45c6efc701b133c45875e86b0053cfc37dab7f4f.
  - The merge-base with origin/main is d300e7a41fb274d6d7e120699b7040666ea61904.
  - The protected Gazebo Python tree has no baseline difference or worktree status.
disproven_routes:
  - The rejected backup must remain read-only provenance and must not supply migration behavior.
open_risks:
  - No MuJoCo runtime experiment has run yet.
next_command: Define EXP-001 before the first runtime-affecting migration experiment.
```

## Checkpoint CP-007

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-001
current_hypothesis: The independent MJCF can preserve the repository robot's six-joint kinematics and stable evidence names.
working_tree_status: Clean at Task 5 implementation commit 9b951ced787c418364a8304b0160ecdf2a5ba73c; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - Immutable ObjectState, ContactEvidence, SimulationEvidence, and ResetReceipt types implement the expanded atomic schema and ordering key.
  - WorldObserver.snapshot and WorldReset.reset expose no call-site freshness or session overrides.
  - Provenance entries resolve only against behavior source commit 8d7913e7f552a40ee627d65be8b873ac16748bc9 with verified source hashes and new-package destinations.
  - Package-level colcon test passed 63 tests with zero errors, failures, or skips; Ruff, isolation, install-layout, and protected-tree gates passed.
disproven_routes:
  - Provenance source paths cannot be restricted to behavior_source.paths alone; exact adaptation source_path fields are required and now validated against the declared set.
  - Ruff invocation cannot inherit caller cwd because import classification changes; the executable gate now fixes cwd to the package root.
open_risks:
  - No MJCF has compiled or passed URDF parity yet.
next_command: Start Task 6 with MJCF compile and model-parity RED tests.
```

## Checkpoint CP-008

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-001
current_hypothesis: The independent deterministic scene can add the task object and table without weakening the verified robot-model parity contract.
working_tree_status: Clean at Task 6 implementation commit 1f73813ae79665562692158400ac2a62b8269e5b; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The independent MJCF compiles and exposes joints 1 through 6, stable robot body and geom names, fingertip collision geoms, six actuators, the so101_tcp site, and a home keyframe without weld, equality, adhesion, mocap, teleport, or direct object state writes.
  - Eleven deterministic URDF/MJCF FK samples passed with maximum position error 4.484050470211362e-16 m and maximum orientation error 0.0 degrees, below the declared 0.0005 m and 0.2 degree limits.
  - The package owns and installs its URDF, MJCF, model-parity configuration, and 43 versioned STL files; every copied input records an exact behavior-source path and SHA-256 in provenance.
  - Package-level colcon test passed 69 tests with zero errors, failures, or skips, including the real fail-closed Ruff integration; Ruff, isolation, install-layout, and protected-tree gates passed.
disproven_routes:
  - Flattening fixed and moving fingertip collision mesh basenames is ambiguous; distinct fixed_fingertip_pad_collision and moving_fingertip_pad_collision names are required.
  - A repository-relative Xacro object-config argument is not cwd-stable because Xacro resolves it below the URDF directory; the copied deterministic robot URDF is therefore produced offline and installed as an owned asset.
open_risks:
  - The task object, table, deterministic reset keyframes, and collision-free scene feasibility are not yet implemented or verified.
next_command: Start Task 7 with RED tests for the independent task scene and deterministic keyframes.
```

## Checkpoint CP-009

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-001
current_hypothesis: The initial uncalibrated MuJoCo contact inputs do not yet prove a stationary free cup over the required ten-second headless run.
working_tree_status: Dirty Task 7 RED/GREEN work is intentionally preserved and uncommitted; no files are staged.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, so101-py-qual, and so101-physical-cpp-gui-019; no session or process was stopped.
confirmed_conclusions:
  - The independent scene compiles, contains a fixed table and free-joint cup, and reaches 10.000000000000009 simulated seconds with a finite 26-element time/qpos/qvel state.
  - The structural no-hidden-grasp tests pass: no equality, weld, adhesion, mocap body, cup actuator, or production object qpos/qvel write path is present.
  - The stationary-cup gate fails: displacement from 2 to 10 seconds is 4.034323607231733e-05 m and final translational speed is 0.009015012052262135 m/s, both above the provisional 1.0e-05 limits.
disproven_routes:
  - The first uncalibrated table/cup contact inputs cannot be accepted as stationary without a controlled diagnosis.
open_risks:
  - EXP-002 was not entered as PLANNED before the first headless execution; the run is diagnostic evidence only and cannot be promoted to VALID.
  - The failed speed may be contact/integration residual or an indexing defect; neither has been isolated.
next_command: NONE
```

## Checkpoint CP-010

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-007
current_hypothesis: The deterministic independent scene is ready for the pinned mujoco_ros2_control system and controller wiring.
working_tree_status: Clean at Task 7 implementation commit 583ef2fdaf1053cd5a66b90b8c56f7decb14f4b7; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The independent scene compiles with a fixed table, rigid free-joint cup, stable names, lights/camera, inherited home keyframe, and task_start keyframe.
  - Structural tests reject equality, weld, adhesion, mocap following, hidden cup actuators, and production object qpos/qvel write paths.
  - EXP-007 is VALID: ten simulated seconds remained finite; 2-to-10-second cup displacement was 4.4468415042278435e-06 m, final-two-second envelope was 9.676037340306193e-06 m, and net speed was 2.380545878240552e-06 m/s.
  - Passive cup damping 1.0 and all friction/damping values are explicitly UNCALIBRATED MuJoCo inputs, not migrated Gazebo/Bullet values; instantaneous solver qvel remains reported and cannot prove later atomic twist success.
  - Package-level colcon test passed 74 tests before the final provenance test addition; the final focused scene/provenance set passed 8 tests, and Ruff, isolation, install-layout, and protected-tree gates passed.
disproven_routes:
  - Final-frame qvel alone is not a reliable stationary-pose metric for the contact solver; position displacement, sampled envelope, and net finite-difference speed remain required together.
  - Passive damping 0.01 and 0.1 did not satisfy the full predeclared stationarity gate.
open_risks:
  - No ROS graph, controller manager, or atomic support-plugin publication has run against the task scene.
next_command: Start Task 8 RED tests for pinned mujoco_ros2_control, controllers, and minimal launch.
```

## Checkpoint CP-011

```yaml
checkpoint_id: CP-011
last_valid_experiment: EXP-008
current_hypothesis: The live atomic evidence stream can be consumed by a backend-specific MuJoCo observer with strict freshness and ordering enforcement.
working_tree_status: Clean at Task 8 implementation commit ad8f87717aa092eb023d0bc9090a06f64134abdd; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE; Task 8 tmux and PIDs 3774884, 3774929, 3774930, 3774931, 3774932, and 3774933 were stopped and verified absent.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated session or process was stopped.
confirmed_conclusions:
  - The minimal launch defaults to start_simulation=false, run_mode=dry_run, headless=true, a 30-second readiness timeout, and a newly generated simulation session id.
  - EXP-008 is VALID in isolated ROS_DOMAIN_ID 81: all three controllers were active, /joint_states exposed joints 1 through 6, /clock published, and atomic evidence carried the exact session id, finite object pose/twist, table contact, and truncated=false.
  - The copied URDF's corrupted shell-expanded model path was replaced by launch-resolved package-local scene/headless tokens; installed launch/config/scene assets were used at runtime.
  - Package-level colcon test passed 80 tests with zero errors, failures, or skips; Ruff, isolation, install-layout, and protected-tree gates passed.
disproven_routes:
  - A plain resolved URDF cannot retain an unexpanded $(find ...) expression; launch-time explicit package-share substitution is required.
  - Reusing a non-symlink ament Python build artifact blocks --symlink-install; the exact stale Task-owned directory was moved recoverably under the evidence root before rebuilding.
open_risks:
  - With no commanded trajectory, the live robot settled away from zero under gravity (joint 2 approximately 1.094 rad); wiring success is not action or physical success and controller/actuator tuning remains unproven.
  - Atomic evidence freshness, session/reset ordering, and reset receipt correlation are not yet enforced by a Python observer/reset adapter.
next_command: Start Task 9 RED tests for the MuJoCo observer.
```

## Experiment EXP-002

```yaml
experiment_id: EXP-002
status: INVALID
hypothesis: The initial independent scene remains finite and stationary for ten simulated seconds.
independent_variable: First uncalibrated MuJoCo table/cup contact inputs in the dirty Task 7 scene.
controlled_variables: Headless MuJoCo vendor library; timestep 0.002 s; no ROS graph; no controller launch; no hardware; no object state writes.
acceptance_criteria: Finite state through ten seconds; fixed table; cup displacement and final translational speed each no greater than 1.0e-05 in their declared units.
evidence_path: Console result associated with CP-009; RED artifact /tmp/so101-debug-mujoco-migration/task7-red.txt records the preceding missing-scene boundary.
owned_processes: NONE
result: INVALID because cup displacement was 4.034323607231733e-05 m and final translational speed was 0.009015012052262135 m/s; additionally, PLANNED was not recorded before execution.
next_command: NONE
```

## Experiment EXP-003

```yaml
experiment_id: EXP-003
status: INVALID
hypothesis: The failed cup-speed gate is explained by a vertical contact/integration residual rather than horizontal drift or an incorrect qvel slice.
independent_variable: Read-only capture of the complete free-joint cup position and velocity components at settle and at ten seconds using the existing scene and timestep.
controlled_variables: Exact dirty Task 7 scene; timestep 0.002 s; same initial keyframe/default state; MuJoCo vendor library; no ROS graph; no controller launch; no hardware; no source-state mutation after start.
acceptance_criteria: State layout is 1 time + 13 qpos + 12 qvel; cup quaternion remains finite and normalized; reported cup translational components identify whether the residual is vertical; cup horizontal displacement remains no greater than 1.0e-05 m.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-003-contact-residual.json
owned_processes: NONE
result: INVALID. State layout was correct and quaternion norm was 1.0, but the residual was not vertical: horizontal displacement was 4.0322194457956205e-05 m and final linear velocity was [-0.007257727062271137, 0.005347353961549931, -4.0568484134831707e-05] m/s. Evidence SHA-256 is 09a041b52afd0cc18eeb66572c1aa15f17199c40b4c40db7057ab29e85b3a339.
next_command: NONE
```

## Experiment EXP-004

```yaml
experiment_id: EXP-004
status: INVALID
hypothesis: A small explicitly uncalibrated passive damping value on the cup free joint allows contact motion to decay below the unchanged stationary gate by ten seconds without constraining or actuating the object.
independent_variable: cup_free_joint_damping = 0.01 N-s per generalized velocity unit.
controlled_variables: Exact EXP-003 scene and checker; unchanged timestep, table/cup friction, initial pose, 10-second duration, and 1.0e-05 displacement/speed limits; no equality, weld, adhesion, mocap, actuator, teleport, or object state write.
acceptance_criteria: All structural gates pass; finite state; cup displacement from 2 to 10 seconds no greater than 1.0e-05 m; final translational speed no greater than 1.0e-05 m/s.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-004-passive-damping.json
owned_processes: NONE
result: INVALID. Structural tests passed, but displacement was 1.5165012719267708e-05 m and final speed was 0.0004656655362538531 m/s. Evidence SHA-256 is b4959e6270cbcd41b7fae792d56391d0009cbfdcbc9d1d4f4bf1bad72df98a77.
next_command: NONE
```

## Experiment EXP-005

```yaml
experiment_id: EXP-005
status: INVALID
hypothesis: Increasing only the explicitly uncalibrated passive cup free-joint damping to 0.1 allows contact motion to decay below the unchanged stationary gate by ten seconds.
independent_variable: cup_free_joint_damping = 0.1 N-s per generalized velocity unit.
controlled_variables: Exact EXP-004 scene and checker; unchanged timestep, friction, pose, duration, and 1.0e-05 limits; no hidden constraint, actuator, teleport, or object state write.
acceptance_criteria: Structural gates pass; finite state; displacement from 2 to 10 seconds and final translational speed each no greater than 1.0e-05 in declared units.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-005-passive-damping.json
owned_processes: NONE
result: INVALID. Position displacement passed at 1.8224771852428455e-06 m, but instantaneous final translational qvel was 0.0006198185333119207 m/s. Evidence SHA-256 is 9be96d419449c8c95c1e435de34f70f4df90a8578c096f2da6d2cdb0294d38fe.
next_command: NONE
```

## Experiment EXP-006

```yaml
experiment_id: EXP-006
status: INVALID
hypothesis: The nonzero final cup qvel is a contact-solver residual that does not represent macroscopic cup motion over the final two seconds.
independent_variable: Add read-only 100 Hz position sampling over simulated seconds 8 through 10 and compare pose envelope/net finite-difference speed with final qvel.
controlled_variables: Exact EXP-005 model and all physical parameters; checker remains read-only; existing pass/fail thresholds remain unchanged during diagnosis.
acceptance_criteria: Finite sampled states; final-two-second translation envelope and net finite-difference speed are reported; evidence establishes whether they are below 1.0e-05 m and 1.0e-05 m/s while instantaneous qvel is not.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-006-stationarity-metrics.json
owned_processes: NONE
result: INVALID. Net final-two-second speed was 2.3202913980782535e-06 m/s, but the 201-sample translation envelope was 1.920915022571309e-05 m, above the unchanged 1.0e-05 m gate. Evidence SHA-256 is 36d9396f6abba8c865e66b1fd7b8d7f64c537ff25ffe51e3af7f6597ebb25d5b.
next_command: NONE
```

## Experiment EXP-007

```yaml
experiment_id: EXP-007
status: VALID
hypothesis: Increasing only passive cup free-joint damping from 0.1 to 1.0 suppresses the measured final-two-second pose envelope below 1.0e-05 m.
independent_variable: cup_free_joint_damping = 1.0 N-s per generalized velocity unit.
controlled_variables: Exact EXP-006 scene/checker and all other physics inputs; unchanged structural and stationarity limits; no hidden grasp mechanism or object state write.
acceptance_criteria: Structural gates pass; finite state; 2-to-10-second displacement, final-two-second translation envelope, and final-two-second net speed are all no greater than 1.0e-05 in declared units.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-007-passive-damping.json
owned_processes: NONE
result: VALID. Structural gates passed; 2-to-10-second displacement was 4.4468415042278435e-06 m, final-two-second envelope was 9.676037340306193e-06 m, and net speed was 2.380545878240552e-06 m/s. Instantaneous qvel remains reported as a solver residual and is not used to claim later atomic twist success. Evidence SHA-256 is feaf3cd7895fcace7bc5dfad5765e0bd7f007859bfe02cbc901584a031a5aee4.
next_command: Run the full Task 7 package, Ruff, isolation, and protected-tree gates.
```

## Experiment EXP-008

```yaml
experiment_id: EXP-008
status: VALID
hypothesis: The pinned apt MuJoCo system, independent controller configuration, and atomic evidence plugin launch together in an isolated ROS domain and expose the required Task 8 runtime interfaces.
independent_variable: Launch Task 8 with start_simulation=true, headless=true, run_mode=dry_run, simulation_session_id=task8-20260810-81, and ROS_DOMAIN_ID=81.
controlled_variables: Installed worktree overlay; apt mujoco_ros2_control 0.0.3; independent package assets; no MoveIt/workflow; no hardware; no commands; unrelated domains, sessions, and processes preserved.
acceptance_criteria: Controller manager lists active joint_state_broadcaster, arm_controller, and gripper_controller; /joint_states and /clock each publish; atomic evidence publishes the exact session id with finite object state; launch exits cleanly when only the recorded task-owned session is stopped.
evidence_path: /tmp/so101-debug-mujoco-migration/task8-runtime/
owned_processes: tmux session so101-mujoco-task8; launch PID 3774884; robot_state_publisher PID 3774929; ros2_control_node PID 3774930; one-shot spawner PIDs 3774931, 3774932, and 3774933. All stopped and verified absent.
result: VALID. All three controllers were active; /joint_states contained joints 1 through 6; /clock published; atomic evidence session id was task8-20260810-81 with finite cup pose/twist, table contact, and truncated=false. Domain 81 contained no nodes after stopping the owned session. Evidence hashes: launch 07470fb7..., controllers 7a77a1a3..., joint states 40200621..., clock af647d99..., atomic evidence 8c68190a..., process tree d21a697e..., empty post-stop nodes e3b0c442....
next_command: Run complete Task 8 package tests and isolation gates, then create the scoped implementation commit.
```

## Experiment EXP-009

```yaml
experiment_id: EXP-009
status: INVALID
hypothesis: MujocoWorldObserver consumes consecutive real atomic plugin messages in an isolated domain while enforcing its configured session and freshness contract.
independent_variable: Run test_observer_live_contract.py against a task-owned headless launch with session task9-20260810-82 in ROS_DOMAIN_ID 82.
controlled_variables: Task 8 launch/config/model; no commands, MoveIt, workflow, or hardware; unrelated sessions/processes preserved; observer max_age_s=0.5.
acceptance_criteria: Live pytest receives two consecutive accepted immutable evidence values with exact session id, increasing publisher sequence, nondecreasing step, cup identity, complete contact arrays, and truncated=false; only recorded task-owned processes are stopped afterward.
evidence_path: /tmp/so101-debug-mujoco-migration/task9-runtime/
owned_processes: tmux session so101-mujoco-task9; launch PID 3790065; robot_state_publisher PID 3790107; ros2_control_node PID 3790108; all stopped and verified absent.
result: INVALID. The isolated plugin launched and published its topic, but test_observer_live_contract received no accepted snapshot in 10 seconds (first=None, second=None). Live test evidence SHA-256 is e106c67b5f00ab7190a1dd02d673712174172f98ba22fd01ffc598d931f163a2; launch log 63ca0175...; process tree 78a7530f.... No diagnostic run was performed after the critical gate failure.
next_command: NONE
```

## Checkpoint CP-012

```yaml
checkpoint_id: CP-012
last_valid_experiment: EXP-008
current_hypothesis: The observer unit contract is correct, but the first live subscriber run either receives no callback or rejects every callback before storing latest evidence.
working_tree_status: Dirty Task 9 observer, unit/live tests, package dependency, and this checkpoint are intentionally preserved; no files are staged.
owned_processes: NONE; Task 9 tmux and PIDs 3790065, 3790107, and 3790108 were stopped and verified absent.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated session or process was stopped.
confirmed_conclusions:
  - Synthetic observer RED then GREEN passed 7 unit tests for conversion, immutable output, wrong-session/truncated/missing-side rejection, ordering, freshness, and rejection diagnostics.
  - Ruff passed and both independent packages built successfully before the isolated live test.
  - EXP-009 is INVALID because no live snapshot was accepted within 10 seconds; the test provides no evidence yet distinguishing discovery/QoS from conversion rejection.
disproven_routes:
  - Unit conversion and ordering tests alone are insufficient to claim the observer consumes real plugin output.
open_risks:
  - The live callback may not execute, or every real message may violate a conversion/ordering invariant; exact cause is intentionally unresolved after the critical gate failure.
next_command: NONE
```

## Checkpoint CP-013

```yaml
checkpoint_id: CP-013
last_valid_experiment: EXP-012
current_hypothesis: The proven observer stream can be correlated transactionally with pause, named reset, and exact step services.
working_tree_status: Clean at Task 9 implementation commit 263818aabc5a6be09db8baaa137eb18668081d42; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE; all Task 9 diagnostic/repeat tmux sessions and recorded descendants were stopped and verified absent.
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no unrelated session or process was stopped.
confirmed_conclusions:
  - MujocoWorldObserver converts one atomic ROS message into immutable backend-neutral evidence and rejects wrong sessions, truncation, missing arrays, stale receipts, publisher-sequence regression, step regression, same-step unpaused evidence, and reset-epoch skips.
  - Callback rejection diagnostics expose count and last reason without replacing the latest accepted snapshot.
  - EXP-012 is VALID: five of five fresh launch/domain/subscriber runs passed with exact sessions, increasing sequences, nondecreasing steps, complete contact arrays, clean owned-PID shutdown, and empty post-stop domains.
  - Package colcon reported 87 passed and one explicitly opt-in live skip; the skipped live case was separately executed successfully five times. Ruff, isolation, and protected-tree gates passed.
disproven_routes:
  - The first EXP-009 timeout did not represent a persistent observer defect; five valid fresh runs could not reproduce it.
  - Shell nounset is incompatible with the ROS setup scripts used by the repeat harness, and daemon-backed node lists are not authoritative for post-stop isolation checks.
open_risks:
  - Pause/reset/step service responses are not yet correlated to observer epoch/step evidence or exposed as ResetReceipt.
next_command: Start Task 10 RED tests for transactional pause/reset/step.
```

## Experiment EXP-010

```yaml
experiment_id: EXP-010
status: INVALID
hypothesis: Real plugin callbacks are arriving, but every message is rejected by one observable observer invariant before latest evidence is stored.
independent_variable: Add rejection count/last-reason to the unchanged live test failure and rerun once against session task9-diag-20260810-83 in ROS_DOMAIN_ID 83.
controlled_variables: Exact Task 9 observer logic and Task 8 launch/model/plugin; no command, MoveIt, workflow, hardware, threshold change, or QoS change; task-owned tmux only.
acceptance_criteria: Failure output distinguishes zero callbacks (rejected_count=0) from systematic rejection (rejected_count>0 with exact reason), enabling one root-cause boundary without changing acceptance behavior.
evidence_path: /tmp/so101-debug-mujoco-migration/task9-diagnostic/
owned_processes: tmux session so101-mujoco-task9-diag and descendants, to be recorded and stopped.
result: INVALID because the hypothesized systematic rejection did not reproduce: the unchanged observer live test passed in 0.42 seconds with no rejection failure. Evidence SHA-256 is 791acbb2840ecff621592488f8e65512e312896e3865560d4000495c22ef5d13; all task-owned processes were stopped.
next_command: NONE
```

## Experiment EXP-011

```yaml
experiment_id: EXP-011
status: INVALID
hypothesis: The live observer contract is repeatable across five fresh simulator/subscriber discovery boundaries and the EXP-009 timeout was a nonpersistent first-run anomaly.
independent_variable: Five fresh launches and live pytest processes with unique domains 84 through 88 and exact session ids task9-repeat-1 through task9-repeat-5.
controlled_variables: Exact observer, live test, Task 8 launch/model/plugin, 10-second timeout, no commands/MoveIt/workflow/hardware; each task-owned tmux and descendants stopped before the next run.
acceptance_criteria: Five of five fresh runs pass; each post-stop domain is empty; no task-owned PID remains; rejection diagnostics remain available on any failure.
evidence_path: /tmp/so101-debug-mujoco-migration/task9-repeat/
owned_processes: Per-run tmux sessions so101-mujoco-task9-r1 through r5 and their recorded descendants.
result: INVALID before observer execution. Harness nounset caused ROS setup to omit the installed so101_mujoco_support Python package, producing collection ModuleNotFoundError; daemon-backed node listing then reported stale names although all recorded PIDs were absent and --no-daemon showed domain 84 empty.
next_command: NONE
```

## Experiment EXP-012

```yaml
experiment_id: EXP-012
status: VALID
hypothesis: The live observer contract passes across five fresh simulator/subscriber discovery boundaries when the ROS environment and cleanup probes are valid.
independent_variable: Five fresh launches/live pytest processes with unique domains 89 through 93 and session ids task9-repeat-valid-1 through task9-repeat-valid-5.
controlled_variables: Exact observer/live test/Task 8 stack; no shell nounset; cleanup uses recorded PIDs and ros2 node list --no-daemon; no product source changes, commands, MoveIt, workflow, or hardware.
acceptance_criteria: Five of five live tests pass; each recorded launch PID disappears; each domain is empty via --no-daemon after stop; no unrelated session/process is changed.
evidence_path: /tmp/so101-debug-mujoco-migration/task9-repeat-valid/
owned_processes: Per-run tmux sessions so101-mujoco-task9-v1 through v5 and recorded descendants.
result: VALID. Five of five fresh live observer tests passed in domains 89 through 93; every recorded launch/child PID disappeared and every post-stop --no-daemon node list was empty. Live-test SHA-256 values are 3a650440..., c9bcb144..., 4237eb8d..., 718af798..., and 261e0cc6....
next_command: Run full package, Ruff, isolation, and protected-tree gates and create the scoped Task 9 commit.
```

## Checkpoint CP-RUFF-001

```yaml
checkpoint_id: CP-RUFF-001
last_valid_experiment: EXP-001
current_hypothesis: The main migration can resume with every new-package Python change guarded by the executable Ruff gate.
working_tree_status: Ruff gate, behavior tests, fixed configuration, mechanical lint/format changes, and this checkpoint are pending one isolated commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - Ruff 0.15.20 and rules E4, E7, E9, F, and I are explicitly pinned; the gate executes both check and format --check over only the independent MuJoCo Python package targets.
  - Strict RED produced 2 failures because the executable gate and configuration were absent; behavior GREEN passed 2 of 2.
  - The first real audit covered 8 Python files and found 6 I001 import-order findings across 6 files; format check identified 4 files requiring formatting and 4 already formatted.
  - Mechanical repair applied 6 import-order fixes and formatted 4 files without intended behavior change.
  - The package-level colcon test executed 47 pytest cases including a real Ruff pass and a disposable-copy F821 rejection; test-result reported zero errors, failures, or skips.
  - Complete pre-fix evidence is ruff-before-{files,check,statistics,format}.txt under the evidence root with SHA-256 values 2610d669..., 40e62557..., 6df5bb43..., and f1eff9fb... respectively.
disproven_routes:
  - A configuration-only or grep-only lint declaration is insufficient; pytest executes the gate and proves both Ruff subcommands and scope.
open_risks:
  - Future environments must provide exactly Ruff 0.15.20 or the gate intentionally fails closed.
next_command: Run final package tests, real Ruff gate, isolation and protected-tree gates, then commit the isolated Ruff change and resume Task 5.
```

## Checkpoint CP-006

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-001
current_hypothesis: The independent Python contracts can faithfully represent the expanded atomic ROS message without backend leakage.
working_tree_status: Clean at Task 4 implementation commit 6d598b8340b50925c217e5a9a088ab600156099a; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The independent support package publishes session, reset epoch, simulation step, publisher sequence, pause, object state, aggregate contact metrics, and separate left/right/other contact arrays.
  - Model-backed GTest passed 5 of 5; aggregate colcon results contain 246 tests, zero errors, zero failures, and two pre-existing skips.
  - Message interface and pluginlib export were verified from the installed Task 4 overlay.
  - Static read-only scan found no qpos/qvel writes, reset/set calls, equality, weld, adhesion, or mocap operations in the plugin implementation.
disproven_routes:
  - Incrementing simulation_step on a paused same-time publication is invalid; the builder now holds step constant while publisher_sequence advances.
open_risks:
  - Live simulator publication and reset service correlation remain unproven until the launch/runtime tasks.
next_command: Start Task 5 RED tests for immutable backend-neutral Python evidence and provenance.
```

## Checkpoint CP-004

```yaml
checkpoint_id: CP-004
last_valid_experiment: NONE
current_hypothesis: The pinned MuJoCo ROS 2 dependency can satisfy the required binary interface without a source fallback.
working_tree_status: Clean at Task 2 implementation commit 9c7889accfdb0eb253a2c9ef1b795b56fe680dad; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The independent ament_python package is commit 9c7889accfdb0eb253a2c9ef1b795b56fe680dad.
  - Package identity tests passed 5 of 5, the combined isolation suite passed 36 of 36, and the package-only colcon build completed successfully.
  - The installed resource marker and package manifest exist under the new package prefix, with no dependency on the protected package.
  - The protected tracked diff and protected status remained empty before and after the Task 2 implementation commit.
disproven_routes:
  - Running pytest with its cache provider inside implementation scope is incompatible with the fail-closed isolation scanner because generated node identifiers can contain rejected provenance strings.
open_risks:
  - No MuJoCo dependency interface or runtime behavior has been proven yet.
next_command: Start Task 3 with the apt mujoco_ros2_control 0.0.3 binary probe and define EXP-001 before any runtime-affecting experiment.
```

## Experiment EXP-001

```yaml
experiment_id: EXP-001
status: VALID
hypothesis: The installed apt mujoco_ros2_control 0.0.3 provider exactly satisfies the pinned package, prefix, file-hash, and service-interface contract.
independent_variable: Read-only execution of the dependency probe against the apt provider.
controlled_variables: ROS Jazzy underlay /opt/ros/jazzy; no overlay; no simulator; no ROS graph mutation; no hardware.
acceptance_criteria: Probe exit 0; all four prefixes equal /opt/ros/jazzy; control version starts 0.0.3-; exact ResetWorld, SetPause, and StepSimulation definitions; all pinned file SHA-256 values match.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-001-dependency-probe.json
owned_processes: NONE
result: Probe exit 0; all required prefixes, versions, interfaces, and pinned file hashes matched. Evidence SHA-256 is 8c2b83d7821f79e618c3ffaf5c6ead133853434367a28bf28d41e6ef978ab104.
next_command: NONE
```

## Checkpoint CP-005

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-001
current_hypothesis: Atomic evidence can be implemented against the proven apt 0.0.3 plugin API.
working_tree_status: Task 3 dependency lock, probe, contract tests, package dependencies, and this checkpoint are pending their single scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The apt provider is release 0.0.3 at /opt/ros/jazzy and no source fallback is required.
  - EXP-001 is VALID with exact versions, prefixes, service definitions, and file hashes recorded under the evidence root.
disproven_routes:
  - Floating main and unpinned source dependency resolution remain forbidden.
open_risks:
  - The Task 4 atomic evidence plugin has not yet been compiled against the proven API.
next_command: Run final Task 3 tests, package build, isolation gates, and create the scoped dependency commit.
```

## Checkpoint CP-002

```yaml
checkpoint_id: CP-002
last_valid_experiment: NONE
current_hypothesis: A fail-closed physical-tree and Python AST scanner can enforce Task 1 isolation without touching protected content or runtime processes.
working_tree_status: The three Task 1 files contain the review fix and are pending one scoped implementation commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The Task 1 base is 45c6efc701b133c45875e86b0053cfc37dab7f4f and the pinned main base is d300e7a41fb274d6d7e120699b7040666ea61904.
  - The original implementation commit is 91c482bd609f7240d5f8547c968363135524bb4f.
  - The protected tracked diff and ordinary status are empty, and its pre-fix nontracked physical baseline digest is 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f.
  - Review RED produced 25 failures and 6 passes before the fix.
disproven_routes:
  - Case-sensitive best-effort text search cannot enforce package isolation.
  - Ordinary Git status cannot detect ignored or generated protected content.
open_risks:
  - The review fix implementation commit is not known until the scoped commit is created.
next_command: Run GREEN and all pre-commit gates, then create the scoped Task 1 review-fix commit.
```

## Checkpoint CP-003

```yaml
checkpoint_id: CP-003
last_valid_experiment: NONE
current_hypothesis: NONE
working_tree_status: Clean at implementation commit e6489ee2949caf435fe028fbe7f65d30a371b5fb; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The fail-closed isolation implementation is commit e6489ee2949caf435fe028fbe7f65d30a371b5fb.
  - Review GREEN produced 31 passes, and the implementation commit passed its immediate isolation, protected-diff, protected-status, and clean-worktree gates.
  - The protected nontracked baseline remains 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f.
disproven_routes:
  - Case-sensitive text search, broad provenance exclusion, ordinary-status-only protection, and whole-repository backup scanning are not sufficient isolation gates.
open_risks:
  - No Task 1 repository-isolation risk remains; runtime migration experiments have not started.
next_command: Define EXP-001 before the first runtime-affecting migration experiment.
```
