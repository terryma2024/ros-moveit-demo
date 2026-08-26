# MuJoCo RGB-D Perception Pick-Place Experiment Ledger

```yaml
task_id: so101-mujoco-rgbd-perception-pick-place
goal: Complete one RGB-D perception-driven physical MuJoCo pick-place from each of four named cup positions on ai-station.
success_contract: Four independent FULL_RESTART runs each use real aligned RGB-D, publish a fresh world /cup_pose from rgbd_cup_pose, reach dynamic DONE, and pass physical, Planning Scene, controller, TF, and visual gates.
worktree: /data/work/ws_moveit/.worktrees/rgbd-perception-pick-place
branch: codex/rgbd-perception-pick-place
base_commit: a7e3745f13b892a8b7501980fdaf87436392ad50
current_commit: 37964ba216b7d808fd5fbb51c93d6115c316e411
evidence_root: /tmp/so101-debug-rgbd-perception-pick-place-20260826/
confirmed_conclusions:
  - Existing macOS CameraPlugin acceptance proves real aligned RGB-D is available only from a correctly sourced interactive runtime; topic names alone are insufficient.
  - Existing dynamic MuJoCo execution accepts one fresh world-frame /cup_pose and has already completed a canonical physical demonstration with a truth-only test bridge.
  - Tasks 2-5 established code-owned static camera TF, exact-stamp RGB-D localization, a fail-closed /cup_pose producer, and perception-confirmed MoveIt cup-shadow synchronization at source level.
  - Task 6 installed a dedicated behavior-tested fail-closed perception launch while preserving the fixed MuJoCo workflow composition (EXP-002).
  - EXP-003 is audit-invalid and non-counting because its production attempt has no durable stdout/stderr plus exit sidecar and no retained RUNNING-transition snapshot; a later independent diagnostic remains useful only as non-counting evidence.
  - EXP-004 is environment-invalid and non-counting: after complete RUNNING/observer readiness evidence, all three controller spawners failed before static TF or production because the sandbox denied the ROS controller-spawner lock under ~/.ros/locks.
  - EXP-005 is pre-RUNNING environment-invalid and non-counting: normal-scope process isolation could not be audited because `ps` was denied and targeted `pgrep` returned rc3, so observers, elevation, stack, production, Viewer action, and motion never started.
  - EXP-006 is interrupted/environment-invalid and non-counting: elevated pre/post process probes, observers, elevated stack, active controllers, and static TF publishers passed, but production and Viewer acceptance never started; strict lock metadata preservation also failed because atime/mtime/ctime changed despite stable identity, mode, size, and SHA-256.
  - CP-016 recovered the task on ai-station at branch commit 12c0d69252f8b84ad1335877192bf23b22947c52 with no conflicting runtime graph, but the required f19a8cc3af61feccacb22a9f0d16cc972e3b2c08 submodule commit is not fetchable from Gitee and the r8 provenance gate remains closed.
  - CORR-CP-016-001 preserves CP-016 as historical blocked evidence and records that Gitee branch codex/rgbd-camera-plugin-r8 now advertises exact f19a8cc, while the ai-station task worktree independently passes the gitlink/HEAD/describe/clean gate.
disproven_routes:
  - Publishing MuJoCo truth as /cup_pose does not validate production camera perception.
  - Routing production through cup_pose_tf_demo duplicates the selected world-point transform boundary.
open_hypotheses:
  - The current color mask, DBSCAN, static TF, and circle fit localize all four named positions within 0.01 m.
  - Raising only production rgbd_cup_pose startup_timeout_s from 30 to 90 seconds may distinguish a bounded aggregate readiness delay from segmentation, fit, QoS/callback, or another production-only pipeline cause.
  - A fresh ai-station Linux build from the exact f19a8cc submodule can pass the perception-only gate without starting dynamic_cup_pick_place or robot motion.
latest_checkpoint: CP-020
next_experiment: EXP-009
```

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: Threading a supported named initial keyframe through the MuJoCo launch composition into the rendered URDF selects the corresponding scene keyframe while preserving task_start as the default.
prediction: The MuJoCo launch description exposes mujoco_initial_keyframe and rendering with cup_test_left_5cm produces the matching hardware initial_keyframe parameter.
single_variable: named initial keyframe is threaded into rendered URDF
lifecycle: ISOLATED_STACK
preconditions:
  - Source worktree is /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place at a7e3745f13b892a8b7501980fdaf87436392ad50 on codex/rgbd-perception-pick-place.
  - The worktree is clean before Task 1 changes; protected baseline is recorded in /tmp/so101-debug-rgbd-perception-pick-place-20260826/protected-baseline.txt.
  - No runtime command starts in this experiment; this is a source-level launch/URDF contract test only.
success_criteria:
  - The declared MuJoCo launch argument accepts all four named keyframes with task_start as the default.
  - Rendering a supported selection writes the exact initial_keyframe hardware parameter.
  - The three cup-test keyframes leave all six robot qpos values at zero and set the cup free-joint pose exactly.
failure_criteria:
  - A supported named keyframe is absent from the launch contract or rendered URDF parameter.
  - A cup-test keyframe changes a robot qpos or has a different cup pose.
invalid_criteria:
  - The source worktree, test environment, or evidence root is not the recorded isolated baseline.
provenance:
  source_commit: a7e3745f13b892a8b7501980fdaf87436392ad50
  install_overlay: NOT_STARTED_NO_RUNTIME
  runtime_executable: NOT_STARTED_NO_RUNTIME
  ros_domain_id: NOT_STARTED_NO_RUNTIME
  gz_partition: NOT_STARTED_NO_RUNTIME
commands:
  - command: PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q src/so101_demo_py/test
    exit_code: 1
  - command: source /Users/matianyi/ros2_jazzy/.venv/bin/activate; source /opt/ros/jazzy/setup.zsh; use evidence-root source and ament shims; PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider src/so101_demo_py/test/test_mujoco_cup_test_keyframes.py src/so101_demo_py/test/test_launch_composition.py::test_mujoco_launch_declares_and_renders_selected_initial_keyframe
    exit_code: 1
  - command: source /Users/matianyi/ros2_jazzy/.venv/bin/activate; source /opt/ros/jazzy/setup.zsh; use evidence-root source and ament shims; PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider src/so101_demo_py/test/test_mujoco_cup_test_keyframes.py src/so101_demo_py/test/test_geometry_manifest.py src/so101_demo_py/test/test_launch_composition.py
    exit_code: 0
  - command: source /Users/matianyi/ros2_jazzy/.venv/bin/activate; source /opt/ros/jazzy/setup.zsh; use evidence-root source and ament shims; PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider src/so101_demo_py/test
    exit_code: 2
observed:
  - Protected baseline provenance and process/tmux snapshot are stored at /tmp/so101-debug-rgbd-perception-pick-place-20260826/protected-baseline.txt.
  - The default Python 3.14 baseline cannot import pytest; the failure is recorded in /tmp/so101-debug-rgbd-perception-pick-place-20260826/baseline-package-tests.txt.
  - The documented /Users/matianyi/ros2_jazzy/.venv Python 3.11.15 with pytest 8.4.2 resolved both target source and package share to this worktree through retained evidence-root shims.
  - The initial-keyframe RED had one passing MJCF characterization test and one expected launch-contract failure because mujoco_initial_keyframe was absent.
  - Focused GREEN suite passed 18 tests; scene.xml and so101.urdf SHA-256 values are recorded in /tmp/so101-debug-rgbd-perception-pick-place-20260826/geometry-hashes.txt.
  - Full package collection could not import generated dependency so101_mujoco_support; no permitted reference install artifact existed for the required hash-gated dependency-only overlay.
inferred:
  - The requested source-level launch/URDF initial-keyframe contract is verified; package-wide validation remains blocked by the missing generated dependency overlay.
conclusion: Supported named keyframes are selectable at MuJoCo startup and render into the hardware initial_keyframe parameter while task_start remains the default.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/protected-baseline.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/test-provenance.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/launch-contract-red.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/green-focused-tests.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/full-package-tests.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/geometry-hashes.txt
decision: KEEP
next_experiment: EXP-002
```

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: Thread a selected supported named initial keyframe through MuJoCo launch composition and rendered URDF.
working_tree_status: clean before Task 1 changes
owned_processes: NONE
preserved_processes: pgrep unavailable in the local sandbox; no process was started or stopped by this task
confirmed_conclusions:
  - No runtime command is authorized or required for EXP-001.
disproven_routes:
  - NONE
open_risks:
  - Runtime and visual acceptance are intentionally deferred to subsequent experiments.
next_command: PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q src/so101_demo_py/test
```

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-001
current_hypothesis: The selected named keyframe is now preserved from MuJoCo launch configuration through rendered URDF hardware parameters.
working_tree_status: Task 1 files modified; commit pending
owned_processes: NONE
preserved_processes: No process was started or stopped; pgrep was unavailable in the sandbox during protected-baseline capture.
confirmed_conclusions:
  - EXP-001 source-level launch contract passed focused tests with current-worktree source/share provenance.
disproven_routes:
  - Using the reference checkout installed so101_demo_py package/share for target tests is prohibited and was not used.
open_risks:
  - Full package test collection is blocked by missing generated so101_mujoco_support dependency artifacts in the permitted isolated environment.
  - The evidence root contains an unauthorized test-venv creation from before controller correction; it is retained as an auditable deletion candidate and is not used for validation.
next_command: Source a permitted matching so101_mujoco_support dependency overlay, then rerun the full package suite with the retained current-worktree source/share shims.
```

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-001
current_hypothesis: A dedicated public launch can fail closed while starting static TF before sensor callbacks and starting perception plus dynamic execution only after successful scene setup.
working_tree_status: clean at 6be854fdd68e4744e512b81ba151413b82799bea before Task 6 changes
owned_processes: NONE
preserved_processes: pgrep is unavailable in the local sandbox; Task 6 will not start or stop a live stack
confirmed_conclusions:
  - Task 5 source behavior and reviewer fixes are present at 6be854fdd68e4744e512b81ba151413b82799bea.
  - Existing current-worktree source/share shims and ROS Python 3.11 are the permitted test environment.
disproven_routes:
  - Source-text inspection is not sufficient as the primary launch topology or fail-closed proof.
open_risks:
  - Launch event semantics must distinguish perception failure from clean perception exit during workflow-owned shutdown.
  - Full package collection may remain blocked by the recorded generated so101_mujoco_support dependency gap.
next_command: Add behavior-level RED tests for the missing perception launch builder and event gating.
```

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: A dedicated perception launch can validate all execute inputs before process construction, reuse the fixed MuJoCo stack, start static TF with that stack, gate perception and dynamic execution on successful scene setup, and shut down fail closed without misclassifying perception exit during workflow-owned shutdown.
prediction: Behavior-level launch entity inspection and injected process-exit events show no perception/workflow action on scene failure, both actions on scene success, failure on pre-completion perception exit, and workflow-status-preserving shutdown with no competing perception-failure event after workflow completion.
single_variable: dedicated fail-closed RGB-D perception launch composition
lifecycle: ISOLATED_STACK
preconditions:
  - Source worktree is /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place on codex/rgbd-perception-pick-place, based on 6be854fdd68e4744e512b81ba151413b82799bea.
  - Evidence is retained only below /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/.
  - No live MuJoCo, MoveIt, controller, ROS graph, or GUI process starts in this source/build/install contract experiment.
success_criteria:
  - RED fails for the missing dedicated launch behavior and unusable path acceptance.
  - GREEN proves exact arguments, substitutions, producer uniqueness, scene-success gating, scene-failure shutdown, perception-failure shutdown, workflow failure status, and shutdown-race suppression.
  - Existing fixed launch and package identity regressions pass, and the installed public launch is discoverable from a current-worktree package build.
failure_criteria:
  - Any executable starts before validation or scene success, or a failure path can leave the owned graph running.
  - The production graph contains cup_pose_tf_demo or mujoco_cup_pose_bridge.
invalid_criteria:
  - Tests resolve source/share outside this worktree, use the unauthorized test virtualenv, or require an unapproved live stack.
provenance:
  source_commit: bccd6e9e18e3a882962e7e880140d52a0d98c86f
  install_overlay: /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/install-final
  runtime_executable: /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/install-final/so101_demo_py/share/so101_demo_py/launch/so101_mujoco_perception_pick_place.launch.py
  ros_domain_id: NOT_STARTED_NO_RUNTIME
  gz_partition: NOT_STARTED_NO_RUNTIME
commands:
  - command: source ROS Jazzy and current-worktree source/share shims; PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider src/so101_demo_py/test/test_perception_pick_place_launch.py
    exit_code: 1
  - command: source ROS Jazzy and current-worktree source/share shims; PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider src/so101_demo_py/test/test_perception_pick_place_launch.py -k invalid_execute_inputs
    exit_code: 1
  - command: source ROS Jazzy and current-worktree source/share shims; PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider src/so101_demo_py/test/test_perception_pick_place_launch.py src/so101_demo_py/test/test_launch_composition.py src/so101_demo_py/test/test_package_identity.py src/so101_demo_py/test/test_camera_tf_contract.py src/so101_demo_py/test/test_mujoco_cup_test_keyframes.py
    exit_code: 0
  - command: colcon build --base-paths src/so101_demo_py --packages-select so101_demo_py --build-base /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/build-final --install-base /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/install-final --symlink-install
    exit_code: 0
  - command: source /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/install-final/setup.zsh; ros2 pkg prefix so101_demo_py; ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py --show-args
    exit_code: 0
observed:
  - OBSERVED: Initial behavior RED produced 18 expected failures because the dedicated builder was missing; evidence red-perception-launch-expected.txt.
  - OBSERVED: Path-usability RED produced two expected failures for a directory evidence seed and nonexistent MJCF scene; evidence red-path-usability.txt.
  - OBSERVED: Fresh post-commit source, camera-TF, and keyframe suite passed 38 tests with two existing lark deprecation warnings; evidence post-commit-source-tests.txt.
  - OBSERVED: The current-worktree one-package build finished successfully and the installed package prefix resolved to the Task 6 install-final directory.
  - OBSERVED: Installed --show-args exposed execute gates, headless=false, all four Task 1 keyframes, and finite perception/cup-pose timeout defaults.
  - OBSERVED: Injected ProcessExited handlers proved scene and perception failure closure plus workflow-owned race suppression without inspect.getsource topology assertions.
inferred:
  - INFERRED: The dedicated source/build/install launch contract is ready for Task 7 live perception validation; no live sensor, motion, physics, or visual outcome is implied.
conclusion: The dedicated perception launch is behavior-verified and installed at source/package-contract level, while live RGB-D and physical acceptance remain unrun.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/red-perception-launch-expected.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/red-path-usability.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/post-commit-source-tests.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/final-package-build.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/final-installed-launch-discovery.txt
decision: KEEP
next_experiment: EXP-003
```

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-002
current_hypothesis: Task 7 EXP-003 must verify real aligned RGB-D and /cup_pose before any motion.
working_tree_status: Task 6 production commit bccd6e9e18e3a882962e7e880140d52a0d98c86f; ledger and Task 6 report remain controller-owned handoff files
owned_processes: NONE
preserved_processes: pgrep is unavailable in the local sandbox; Task 6 started no live stack and stopped no process
confirmed_conclusions:
  - EXP-002 behavior RED failed for the missing launch builder, then 38 final focused and affected tests passed under current-worktree source/share provenance.
  - EXP-002 injected ProcessExited events prove scene-success gating, scene-failure shutdown, early-perception failure, workflow-status preservation, and suppression of perception exit after workflow-owned shutdown.
  - EXP-002 current-worktree package build and installed public launch discovery passed from the Task 6 evidence root.
disproven_routes:
  - Source-text inspection was not used as the primary topology or fail-closed proof.
  - The production graph contains neither cup_pose_tf_demo nor mujoco_cup_pose_bridge.
open_risks:
  - No live RGB-D, ROS graph, MuJoCo, controller, MoveIt, or visual acceptance was run in Task 6; those remain Task 7 EXP-003 and later gates.
  - Full package collection still has the previously recorded generated so101_mujoco_support environment gap.
next_command: Create PLANNED EXP-003 from Task 7 before starting the local Mac perception-only runtime gate.
```

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-002
current_hypothesis: Task 7 EXP-003 must verify real aligned RGB-D and /cup_pose before any motion.
working_tree_status: production review fix committed at e586686; this ledger checkpoint is the only subsequent tracked change
owned_processes: NONE
preserved_processes: Task 6 reviewer-fix tests used only short-lived Python child processes under LaunchService; no live ROS graph or simulator was started
confirmed_conclusions:
  - Reviewer correction supersedes the earlier claim that Shutdown plus OpaqueFunction preserves an arbitrary child status through LaunchService.
  - The installed so101_mujoco_perception_pick_place runner executes the public builder with a shared first-terminal status and real LaunchService tests prove scene 12 maps to 12 and workflow 23 maps to 23.
  - Derived evidence root preflight creates and contains <evidence-stem>.d/<session> and rejects symlink, non-directory, and conflicting-owner components before node construction.
  - The final affected source suite passed 47 tests; one-package build and installed runner/public-launch discovery passed from the reviewer-fix overlay.
disproven_routes:
  - Direct OpaqueFunction exception execution is not sufficient proof of shell-status preservation.
  - Standard LaunchService return status alone cannot carry arbitrary child codes; the installed status-aware command is the exact-status boundary.
open_risks:
  - No live RGB-D, ROS graph, MuJoCo, controller, MoveIt, motion, or visual acceptance was run in Task 6.
  - Full package collection still has the previously recorded generated so101_mujoco_support environment gap.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/reviewer-fix/red-review-findings.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/reviewer-fix/final-source-tests.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/reviewer-fix/package-build.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/reviewer-fix/installed-launch-discovery-final.txt
next_command: Create PLANNED EXP-003 from Task 7 before starting the local Mac perception-only runtime gate.
```

```yaml
experiment_id: EXP-003
status: INVALID
result: NON_COUNTING_AUDIT_INVALID
audit_correction: CORR-EXP-003-002
prior_experiment: EXP-002
hypothesis: The current installed Mac runtime can produce real aligned RGB-D and a fresh perception-owned world /cup_pose within 0.01 m of MuJoCo truth before any robot motion.
prediction: An isolated task_start MuJoCo stack publishes exact-stamp 640x480 rgb8 and 32FC1 samples with finite positive depth; production rgbd_cup_pose emits a nonempty segmented cloud, PLY, JSON receipt, and finite fresh world pose whose Euclidean error from MuJoCo cup truth is at most 0.01 m.
single_variable: execute one perception-only Mac Aqua runtime gate from the Task 6 current-worktree installation
lifecycle: ISOLATED_STACK
preconditions:
  - Source worktree is /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place at 2c622b6197b354fefa49aabfd7bb9f3b26df1699 on codex/rgbd-perception-pick-place and is clean except this planned ledger entry.
  - ROS_DOMAIN_ID 180 is empty before launch; GZ_PARTITION rgbd-perception-gate-20260826 and session rgbd-perception-gate-20260826 are unique to this experiment.
  - The complete current-worktree package build succeeds and installed package prefixes and executables resolve to this worktree before the live gate.
  - The logged-in Mac Aqua session is available for a headless=false MuJoCo viewer, and no unowned conflicting simulator, move_group, RViz, dynamic_cup_pick_place, or rgbd_cup_pose process is stopped or reused.
  - dynamic_cup_pick_place is never started and the robot remains motionless throughout this experiment.
success_criteria:
  - Real /task_camera/camera_info, /task_camera/color, and /task_camera/depth samples are aligned at one exact source stamp, are 640x480, use rgb8 and 32FC1, and depth contains finite positive values.
  - world to task_camera_frame static TF lookup succeeds with the approved transforms.
  - Production rgbd_cup_pose is the sole /cup_pose publisher and writes a nonempty cup PLY plus JSON receipt with a valid fit/radius.
  - A fresh finite world-frame /cup_pose uses the RGB-D source stamp and differs from MuJoCo cup truth by at most 0.01 m.
  - A Computer Use snapshot, action, and fresh snapshot are retained and visually inspected to show the canonical cup and active MuJoCo scene.
  - Only owned process groups receive SIGINT; afterward ROS domain 180 and the owned targeted process set are clean.
failure_criteria:
  - The isolated stack starts correctly but any real sample, encoding/dimension, exact-stamp alignment, finite depth, TF, segmentation, fit, publisher provenance, pose freshness/frame, truth-error, visual, or cleanup gate fails.
  - dynamic_cup_pick_place or any robot motion is observed.
invalid_criteria:
  - Domain 180, the partition/session, installed provenance, initial task_start state, GUI session, or evidence is contaminated or unavailable before the measured boundary.
  - A required process is unowned, an unapproved environment/install is used, or samples cannot be causally attributed to this experiment.
provenance:
  source_commit: 2c622b6197b354fefa49aabfd7bb9f3b26df1699
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place/install/so101_demo_py/lib/so101_demo_py/rgbd_cup_pose
  ros_domain_id: 180
  gz_partition: rgbd-perception-gate-20260826
commands:
  - command: source /opt/ros/jazzy/setup.zsh and /Users/matianyi/ros2_jazzy/.venv; PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider src/so101_demo_py/test
    exit_code: 0
  - command: source documented ROS Jazzy runtime; colcon build --packages-select so101_demo_py --symlink-install --event-handlers console_direct+
    exit_code: 0
  - command: source install/setup.zsh; verify so101_demo_py, mujoco_ros2_control, and mujoco_ros2_control_plugins prefixes, installed executables, launch, and scene provenance
    exit_code: 0
  - command: ROS_DOMAIN_ID=180 GZ_PARTITION=rgbd-perception-gate-20260826 ROS_LOG_DIR=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/ros ros2 launch so101_demo_py so101_mujoco.launch.py run_mode:=execute execute:=true headless:=false session_id:=rgbd-perception-gate-20260826 mujoco_initial_keyframe:=task_start evidence_file:=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/stack.json
    exit_code: 0
  - command: start the two approved static_transform_publisher processes in domain 180, then ROS_DOMAIN_ID=180 ros2 run so101_demo_py rgbd_cup_pose --startup-timeout-s 30 --output-topic /cup_pose --output-ply /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/cup.ply --evidence-json /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/perception.json
    exit_code: EVIDENCE_UNAVAILABLE
  - command: capture bounded one-shot RGB-D, TF, /cup_pose, publisher, MuJoCo truth, process, and Computer Use visual evidence; then SIGINT only owned process groups and verify cleanup
    exit_code: EVIDENCE_INCOMPLETE
observed:
  - OBSERVED: CORR-EXP-003-001 cleared the historical preflight block at effective source ef6175dd146275d56979ad2860f1f3a6f94dbf79; the complete package suite passed 369 tests, the package rebuilt with exit 0, and runtime imports and installed so101_demo_py artifacts resolved to this worktree.
  - OBSERVED: The immediate pre-launch graph in ROS domain 180 and the owned-process target set were empty; the isolated task_start/headless=false execute stack started its real MuJoCo camera rendering loop at 640x480 and activated all controllers without starting dynamic_cup_pick_place or commanding motion.
  - OBSERVED: Real CameraInfo was 640x480 at stamp 220.322000000; real color was 640x480 rgb8 with step 1920 and 921600 bytes at stamp 279.248000000; real depth was 640x480 32FC1 with step 2560 and 1228800 bytes at stamp 275.534000000. These separate one-shot samples prove message contents but are not an aligned triple.
  - OBSERVED: During the observed 30 s production attempt, aggregate valid-pose readiness did not produce an acceptable /cup_pose. The transient PTY showed an aggregate timeout, but no durable production stdout/stderr log or exit-code sidecar survives, so the exact production exit is not auditable and is not reconstructed here.
  - OBSERVED: A bounded 90 s rgbd_point_cloud diagnostic then exited 0 with one exact aligned triple at stamp_ns 337986000000 in task_camera_frame; it accepted 640x480 rgb8/32FC1, retained 98082 finite positive-depth points, selected 259 orange candidates, segmented 141 cup points, and wrote a 4013-byte diagnostic PLY.
  - OBSERVED: world to task_camera_frame initially reported that frame `world` did not exist, then became stable at translation [0.650, -0.650, 0.550] and quaternion [0.799, 0.331, -0.192, -0.465]. The first fresh MuJoCo truth sample was world [0.020000000000000018, -0.28, 0.16480156647042168].
  - OBSERVED: Computer Use application discovery reported org.mujoco.mujoco isRunning=false, so no causally attributable Viewer snapshot-action-fresh-snapshot sequence could be captured without launching an unrelated app; the visual gate failed.
  - OBSERVED: The retained final targeted process scan contains only its own scan command. The zero-byte domain-180-after-cleanup.txt has no exit-code sidecar, so it cannot prove a successful empty ROS graph check. Transient PTY shutdown observations are retained in the audit narrative but are not promoted to durable cleanup-exit evidence.
inferred:
  - INFERRED: The only supported production conclusion is that aggregate valid-pose readiness did not produce an acceptable /cup_pose within the observed 30 s attempt. The later independent diagnostic proves exact RGB-D, segmentation, and TF availability, but does not exclude segmentation, radius fit, QoS/callback delivery, TF timing, or another production-only pipeline cause during the production attempt.
  - INFERRED: No perception-vs-truth error can be accepted because no durable acceptable production pose sample exists. Diagnostic camera-frame center and MuJoCo truth are retained only for the next controlled experiment, not substituted for production output.
conclusion: EXP-003 is audit-invalid and cannot count as product success or failure. The observed 30 s production attempt produced no acceptable /cup_pose; later independent exact-RGB-D, segmentation, and TF observations are retained only as non-counting diagnostic evidence.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/
decision: REPEAT_WITH_COMPLETE_EVIDENCE
next_experiment: EXP-004
preflight_status: HISTORICAL_SUPERSEDED
preflight_historical_status: BLOCKED_BEFORE_RUNTIME
preflight_superseded_by: CORR-EXP-003-001
preflight_commands:
  - command: source documented ROS Jazzy runtime; colcon build --packages-select mujoco_vendor so101_mujoco_support so101_demo_py --symlink-install --event-handlers console_direct+
    exit_code: 2
  - command: source current install; LIBRARY_PATH=/opt/homebrew/lib; colcon build --packages-select so101_mujoco_support so101_demo_py --symlink-install --event-handlers console_direct+
    exit_code: 0
  - command: source current install and set ROS_LOG_DIR below EXP-003; PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider src/so101_demo_py/test
    exit_code: 1
  - command: source current install and set ROS_LOG_DIR below EXP-003; run the seven RGB-D, TF, keyframe, composition, and perception focused test files
    exit_code: 0
preflight_observed:
  - OBSERVED: The current-worktree build produced so101_demo_py, generated so101_mujoco_support messages and plugin, and mujoco_vendor after reusing only documented local MuJoCo source/stage and Homebrew GLFW inputs; the final build exit was 0.
  - OBSERVED: The first corrected full suite passed 366 tests and exposed two linked-worktree nested-submodule failures plus one stale installed-launch expectation.
  - OBSERVED: A no-fetch submodule update could not read locked commit f19a8cc from its newly created object store; the failed checkout was retained under EXP-003 and replaced by a linked worktree from the existing local main-checkout submodule repository.
  - OBSERVED: After local submodule repair, the full suite passed 368 tests and failed only test_final_install_contains_runtime_contract because the old EXPECTED_LAUNCHERS set rejects installed so101_mujoco_perception_pick_place.launch.py.
  - OBSERVED: The focused affected suite passed 99 tests. Domain 180 remained empty and no Task 7 live stack or owned background process was started.
preflight_conclusion: HISTORICAL_ONLY; the original preflight block was cleared by CORR-EXP-003-001 before the runtime attempt and is not a current EXP-003 state.
preflight_evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/tests/colcon-build-final.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/tests/pytest-after-submodule-repair.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/tests/pytest-focused-affected.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/tests/submodule-local-object-check.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/process-isolation-after-block.txt
```

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-002
current_hypothesis: Task 7 EXP-003 must verify real aligned RGB-D and /cup_pose before any motion.
working_tree_status: production re-review fix committed at 66b436578081cdf9638e0c4fe4efd04eb78cab6b; this ledger correction is the only subsequent tracked change
owned_processes: NONE
preserved_processes: Task 6 re-review used only short-lived Python children in test-owned LaunchService instances; no live ROS graph or simulator was started
confirmed_conclusions:
  - Recorded nonzero child status wins exactly; recorded zero or absent child status defers to LaunchService status, so teardown failure cannot be masked as success.
  - Real LaunchService tests retain scene 12 to 12 and workflow 23 to 23 and additionally prove recorded clean child plus LaunchService failure returns 1.
  - Preflight now creates and validates resolved perception and dynamic directories before Node construction, rejecting symlink, non-directory, and simulated foreign-owner children.
  - The final affected source suite passed 55 tests; one-package build and installed runner/public-launch discovery passed from reviewer-fix-2.
disproven_routes:
  - A recorded clean child exit is not sufficient to declare the owned graph successful when LaunchService reports teardown or handler failure.
  - Validating only the session directory does not prevent final perception or dynamic path symlink escape.
open_risks:
  - No live RGB-D, ROS graph, MuJoCo, controller, MoveIt, motion, or visual acceptance was run in Task 6.
  - Full package collection still has the previously recorded generated so101_mujoco_support environment gap.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/reviewer-fix-2/red-review-findings.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/reviewer-fix-2/final-source-tests.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/reviewer-fix-2/package-build.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/task-6/reviewer-fix-2/installed-launch-discovery.txt
next_command: Create PLANNED EXP-003 from Task 7 before starting the local Mac perception-only runtime gate.
```

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-002
current_hypothesis: The production Mac RGB-D chain remains unmeasured because Task 7 stopped before runtime on a package-suite regression inherited from Task 6.
working_tree_status: only docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md is tracked dirty at source commit 2c622b6197b354fefa49aabfd7bb9f3b26df1699; build/install/log and ignored so101_teleop web artifacts are retained
owned_processes: NONE
preserved_processes: Unowned process commands 46888, 47057, and 47058 from a separate mujoco-control task appeared in the final system scan and were not signaled or modified; their status may have changed after the snapshot
confirmed_conclusions:
  - Current-worktree mujoco_vendor, so101_mujoco_support, and so101_demo_py build successfully using only existing local dependencies; focused affected tests pass 99 tests.
  - The linked-worktree nested MuJoCo fork is now present at locked commit f19a8cc using the existing local main-checkout submodule repository, with no fetch.
  - The corrected full package suite passes 368 tests and has one real remaining regression: test_installed_provenance rejects the newly installed Task 6 perception launch because EXPECTED_LAUNCHERS is stale.
  - ROS domain 180 was empty both before and after preflight; no live stack, rgbd_cup_pose, dynamic workflow, motion, or Computer Use action occurred.
disproven_routes:
  - The initial 35 collection errors were not a generated-message product failure; they came from an invalid source package mapping and overwritten ROS PYTHONPATH and are superseded by current-overlay test evidence.
  - The two nested-fork failures in the 366-pass run were checkout-provenance failures and disappeared after the local no-network submodule repair.
open_risks:
  - No RGB-D sample, TF lookup, segmented cloud, PLY/JSON receipt, /cup_pose, truth comparison, or visual evidence exists for EXP-003 because runtime was correctly not started.
  - Unowned processes from a separate MuJoCo task appeared after the initial isolation scan; a fresh ownership/domain gate is mandatory before EXP-003 runtime starts.
  - The wide failed build created ignored so101_teleop web node_modules, dist, and tsconfig.tsbuildinfo artifacts; they are retained deletion candidates and were not removed.
next_command: Return the stale EXPECTED_LAUNCHERS failure to the Task 6 fix loop, rebuild so101_demo_py, and rerun the full package suite before changing EXP-003 from PLANNED.
```

```yaml
correction_id: CORR-EXP-003-001
applies_to: EXP-003
recorded_at: 2026-08-26T04:49:00+08:00
reason: Task 6 fixed the sole package-suite regression with one test-only launcher-contract addition after EXP-003 was originally frozen at 2c622b6.
historical_plan_preserved: The original EXP-003 PLANNED source_commit and the blocked preflight results above remain unchanged as audit history.
corrected_pre_run_provenance:
  source_commit: ef6175dd146275d56979ad2860f1f3a6f94dbf79
  delta_from_original_plan: one-line test-only EXPECTED_LAUNCHERS addition in test_installed_provenance.py
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place/install/so101_demo_py/lib/so101_demo_py/rgbd_cup_pose
  ros_domain_id: 180
  gz_partition: rgbd-perception-gate-20260826
verification:
  - command: source current worktree install with evidence-owned ROS_LOG_DIR; PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider src/so101_demo_py/test
    exit_code: 0
    observed: 369 passed and 2 existing lark deprecation warnings in 10.47 seconds
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/tests/task6-full-suite-green.log
decision: PRE_RUN_BLOCKER_CLEARED
next_command: Rebuild and re-source so101_demo_py at ef6175d, verify installed provenance, then immediately recheck domain 180 and process ownership before transitioning EXP-003 to RUNNING.
```

```yaml
checkpoint_id: CP-008
checkpoint_status: SUPERSEDED_BY_CORR-EXP-003-002
last_valid_experiment: EXP-003
current_hypothesis: Production rgbd_cup_pose misses its 30 s Mac startup/readiness deadline before a first valid aligned RGB-D plus world-TF pose can complete; an instrumented fix must preserve fail-closed behavior and prove the first delayed boundary.
working_tree_status: source commit ef6175dd146275d56979ad2860f1f3a6f94dbf79 is unchanged; only this persistent ledger is tracked dirty and the Task 7 scratch report is ignored
owned_processes: NONE
preserved_processes: No unowned process was signaled or modified; final ROS domain 180 and the exact owned targeted process scan were empty
confirmed_conclusions:
  - The full package suite passes 369 tests and the rebuilt, sourced production executable resolves to the current worktree.
  - The live task_start camera produces real exact-stamp 640x480 rgb8/32FC1 with finite positive depth; the 90 s diagnostic segmented 141 cup points and wrote a nonempty PLY.
  - Production rgbd_cup_pose published no /cup_pose and wrote no production PLY/JSON before its 30 s timeout, so the perception-only acceptance gate failed before publisher provenance or truth error could be evaluated.
  - world to task_camera_frame was initially unavailable and later stable; MuJoCo truth was [0.020000000000000018, -0.28, 0.16480156647042168].
  - Computer Use could not identify a running org.mujoco.mujoco Aqua app for the owned GLFW viewer, so the required snapshot-action-fresh-snapshot visual gate was not met.
  - No dynamic_cup_pick_place process or robot motion occurred, and all exact owned processes shut down cleanly with SIGINT.
disproven_routes:
  - Camera topic registration and camera-plugin rendering logs alone are insufficient; production can still miss its valid-pose startup deadline.
  - A successful standalone rgbd_point_cloud diagnostic cannot be substituted for a production /cup_pose sample or its publisher/truth evidence.
open_risks:
  - The aggregate production timeout does not distinguish delayed exact-stamp RGB-D from delayed world TF; the next fix task must instrument or otherwise isolate the first readiness boundary before changing behavior.
  - Production radius fit, /cup_pose freshness, source stamp, publisher identity, perception-vs-truth error, and Viewer visual evidence remain unmeasured.
  - The wide preflight build's ignored so101_teleop web artifacts and the retained failed submodule-init copy remain deletion candidates; nothing was deleted.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/diagnostic-point-cloud.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/diagnostic-cup.ply
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/tf-world-task-camera.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/mujoco-truth-once.yaml
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/viewer-discovery.json
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/owned-processes-after-cleanup.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/domain-180-after-cleanup.txt
next_command: Start a new Task 7 fix loop for EXP-004 that adds focused readiness diagnostics or a justified startup-boundary fix, then rerun the same perception-only gate before any motion task.
```

```yaml
correction_id: CORR-EXP-003-002
applies_to:
  - EXP-003
  - CP-008
  - task-7-report.md written from ledger commit 83a3033e51c6f6d47b1c4164be29252e8a929221
recorded_at: 2026-08-26T05:20:00+08:00
review_verdict: NEEDS_DOCUMENTATION_AND_EVIDENCE_BOUNDARY_FIXES
reason: The prior record promoted transient PTY observations into a countable VALID failure without a durable production stdout/stderr log, production exit-code sidecar, or retained snapshot proving the PLANNED to RUNNING transition.
history_preserved:
  - Commit 83a3033 retains the earlier VALID-failure wording and CP-008 as the reviewed historical record.
  - This correction does not fabricate or reconstruct missing production or cleanup evidence and does not discard the later independent diagnostic artifacts.
effective_status: INVALID
counting_effect: EXP-003 is excluded from product success and failure denominators and last_valid_experiment remains EXP-002.
supported_conclusion:
  - Aggregate production valid-pose readiness did not produce an acceptable /cup_pose within the observed 30 s attempt.
  - A later independent diagnostic proved exact-stamp RGB-D, segmentation, and world-TF availability, but cannot exclude segmentation, fit, QoS/callback, TF timing, or another production-only pipeline cause during the production attempt.
durable_evidence_present:
  - Separate real CameraInfo, rgb8 color, and 32FC1 depth payload captures.
  - Later independent exact-stamp rgbd_point_cloud diagnostic log and nonempty PLY.
  - Later tf2_echo log, MuJoCo truth sample, Viewer discovery JSON, and exact targeted process scan.
critical_evidence_missing:
  - Production rgbd_cup_pose complete stdout/stderr.
  - Production rgbd_cup_pose exit-code sidecar.
  - Durable EXP-003 RUNNING-transition snapshot with timestamp and provenance.
  - Cleanup ROS graph command exit-code sidecar; domain-180-after-cleanup.txt is zero bytes and therefore does not prove command success.
cleanup_correction: The final targeted process scan is durable and shows no owned target process beyond the scan itself; ROS graph emptiness remains an audit gap.
decision: REPEAT_AS_EXP-004_WITH_COMPLETE_CAPTURE
next_experiment: EXP-004
```

```yaml
experiment_id: EXP-004
status: INVALID
result: ENVIRONMENT_INVALID_BEFORE_PRODUCTION
pre_run_amendment: CORR-EXP-004-001
running_transition:
  wall_time_ns: 1787693709792530000
  monotonic_ns: 1486256726203291
  source_head: 83a6e8c828e1483c9d6e367e728120bbf03b91e2
  running_snapshot: /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/running-snapshot.txt
  running_snapshot_exit: 0
  observer_readiness_snapshot: /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/observers/observers-ready-snapshot.txt
  observer_readiness_exit: 0
  sample_observer_session: 21199
  publisher_provenance_observer_session: 87454
prior_experiment: EXP-003
hypothesis: The observed 30 s aggregate valid-pose readiness failure is a bounded startup delay; increasing only production rgbd_cup_pose startup_timeout_s from 30 to 90 seconds will yield a fresh acceptable /cup_pose without changing code, topics, TF, segmentation, fit, QoS, or scene configuration.
prediction: With otherwise identical task_start perception-only conditions, production rgbd_cup_pose publishes its first finite fresh world /cup_pose before the 90 s deadline; if it still fails, complete production evidence will preserve the first auditable failure for a subsequent instrumentation task.
single_variable: production rgbd_cup_pose --startup-timeout-s changes from 30 to 90 seconds
lifecycle: ISOLATED_STACK
preconditions:
  - Runtime source remains ef6175dd146275d56979ad2860f1f3a6f94dbf79 and installed source/package/runtime provenance is freshly read back before launch.
  - No production code, topic, TF, color mask, DBSCAN, radius fit, QoS, scene, keyframe, camera, or controller configuration changes between EXP-003 and EXP-004.
  - ROS_DOMAIN_ID 180 is empty immediately before launch or EXP-004 is amended before RUNNING with a newly verified empty domain; session and partition are unique to EXP-004.
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/ exists before launch and every long-lived command has a predetermined complete stdout/stderr path, monotonic start/end timestamp path, and exit-code sidecar.
  - A durable RUNNING snapshot is written after provenance/isolation checks and before any stack process starts; missing this snapshot makes EXP-004 INVALID.
  - Before production starts, a dedicated owned `/cup_pose` one-shot sample observer and a dedicated owned `/cup_pose` publisher-provenance observer are both running, their PID/PGID and wall/monotonic start timestamps are retained, and a readiness probe proves the sample observer subscription exists.
  - Prelaunch Computer Use discovery proves org.mujoco.mujoco is not already running; after the owned stack starts, the same app identity must become attributable to the owned session before any Viewer image can count.
  - dynamic_cup_pick_place is never started and no robot motion is commanded.
success_criteria:
  - Production rgbd_cup_pose complete stdout/stderr, monotonic start/end timestamps, PID/process ownership, and exit sidecar are retained.
  - The first production-owned /cup_pose sample and verbose publisher provenance are retained; the pose is finite, world-frame, fresh, and carries the exact aligned RGB-D source stamp.
  - Exact-stamp 640x480 rgb8/32FC1, finite positive depth, production PLY/JSON, valid fitted radius, static TF, and perception-vs-MuJoCo truth error at most 0.01 m all pass.
  - The sample observer was ready before production start and retains the first `/cup_pose` sample; the concurrent provenance observer retains a publisher count of 1, node name rgbd_cup_pose, namespace, endpoint GID, topic type, and QoS before it exits.
  - A causally attributable MuJoCo Viewer baseline is saved, a Computer Use camera-view-only action is recorded, and a fresh post-action snapshot is saved and actually inspected; attribution, wall/monotonic timestamps, action coordinates, image paths, sizes, SHA-256 values, and inspection findings are retained.
  - Cleanup begin/end monotonic timestamps, every owned process exit sidecar, final exact targeted process scan, and ROS domain command output plus exit sidecar are retained.
failure_criteria:
  - Complete evidence shows production emits no acceptable /cup_pose within 90 s or fails any sample, segmentation, fit, TF, publisher, freshness, truth-error, visual, or cleanup gate.
invalid_criteria:
  - Any production stdout/stderr, start/end timestamp, exit sidecar, RUNNING snapshot, ownership record, or cleanup output/exit sidecar is missing or ambiguous.
  - Either observer starts after production, is not proven ready/owned, lacks its complete log/timestamps/exit sidecar, or remains running after first evidence or production exit.
  - The Viewer baseline -> Computer Use action -> fresh snapshot sequence is missing, stale, uninspected, or cannot be causally attributed to the owned MuJoCo stack and EXP-004 session.
  - Provenance, initial state, domain/session isolation, or causality is contaminated; an unowned process is reused or stopped; or robot motion starts.
provenance:
  source_commit: ef6175dd146275d56979ad2860f1f3a6f94dbf79
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place/install/so101_demo_py/lib/so101_demo_py/rgbd_cup_pose
  ros_domain_id: 180
  gz_partition: rgbd-perception-gate-exp004-20260826
commands:
  - command: capture current commit/status, installed prefixes/imports, domain/process isolation, exact shell environment, wall time, monotonic_ns, and Computer Use sky.list_apps prelaunch discovery into /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/running-snapshot.txt and visual/viewer-prelaunch.json; require org.mujoco.mujoco isRunning=false; write command exit to running-snapshot.exit; only after exit 0 update status PLANNED to RUNNING
    exit_code: 0
  - command: ROS_DOMAIN_ID=180 GZ_PARTITION=rgbd-perception-gate-exp004-20260826 ROS_LOG_DIR=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/ros/stack ros2 launch so101_demo_py so101_mujoco.launch.py run_mode:=execute execute:=true headless:=false session_id:=rgbd-perception-gate-exp004-20260826 mujoco_initial_keyframe:=task_start evidence_file:=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/stack.json > /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/stack.log 2>&1; record monotonic start/end and exact exit sidecars
    exit_code: 130
  - command: start the two approved static_transform_publisher commands unchanged in domain 180, each with complete stdout/stderr, monotonic start/end, PID/PGID ownership, and exit sidecars below /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/
    exit_code: NOT_STARTED_AFTER_INVALID_BOUNDARY
  - command: BEFORE production, in a dedicated owned PTY/session run `ROS_DOMAIN_ID=180 ros2 topic echo /cup_pose --once` with output at exp-004/observers/cup-pose-first.log; wrapper installs INT/TERM traps that write cup-pose-first.end.wall_ns, .end.monotonic_ns, and .exit, and records cup-pose-first.start.wall_ns, .start.monotonic_ns, and .owner PID/PGID/session; poll `ROS_DOMAIN_ID=180 ros2 topic info /cup_pose --verbose` into cup-pose-subscriber-ready.log until Subscription count is at least 1, then write readiness exit sidecar
    exit_code: 130
  - command: BEFORE production, in a second dedicated owned PTY/session poll `ROS_DOMAIN_ID=180 ros2 topic info /cup_pose --verbose` every 0.1 s into exp-004/observers/cup-pose-publisher-provenance.log and exit 0 only after one attempt records Publisher count 1 and Node name rgbd_cup_pose; wrapper installs INT/TERM traps and writes wall/monotonic start/end, owner PID/PGID/session, and exact exit sidecars on success, production-first exit, or signal
    exit_code: 130
  - command: ROS_DOMAIN_ID=180 ROS_LOG_DIR=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/ros/perception ros2 run so101_demo_py rgbd_cup_pose --startup-timeout-s 90 --output-topic /cup_pose --output-ply /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/cup.ply --evidence-json /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/perception.json > /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/production.log 2>&1; record monotonic start/end, PID/PGID, first /cup_pose or failure, and exact exit sidecars
    exit_code: NOT_STARTED_AFTER_INVALID_BOUNDARY
  - command: after owned-stack attribution succeeds, use only node_repl plus @oai/sky to call sky.get_app_state for org.mujoco.mujoco and save visual/viewer-baseline.png plus baseline state/timestamps; derive a small camera-view-only sky.drag from that fresh baseline and save visual/viewer-action.json; immediately call sky.get_app_state again and save visual/viewer-fresh.png plus fresh state/timestamps; record sizes/SHA-256 and write visual/viewer-inspection.md describing the canonical cup, active owned scene, and visible post-action view change
    exit_code: NOT_STARTED_AFTER_INVALID_BOUNDARY
  - command: when the first sample and provenance observers have both exited, or immediately when production exits first, write observers/stop.wall_ns and stop.monotonic_ns, SIGINT only any still-running exact owned observer PTY/session or PID/PGID, wait for both wrappers to write end timestamps and exit sidecars, and prove neither observer remains before general cleanup
    exit_code: 0
  - command: before signaling, record cleanup-begin monotonic_ns and exact owned PID/PGID set; SIGINT only those owned sessions/process groups; record every exit, cleanup-end monotonic_ns, final targeted process scan plus exit sidecar, and ROS_DOMAIN_ID=180 ros2 node list --no-daemon output plus exit sidecar
    exit_code: 0
observed:
  - OBSERVED: The first running-snapshot attempt was rejected before RUNNING because direnv placed `/Users/matianyi/ros2_jazzy/ws_mujoco_ros2_control_fork/install` ahead of the EXP-003 main-repository runtime. The retained final snapshot removed only that conflicting prefix from ROS/runtime path variables and proved current-worktree demo/support/vendor plus main-repository mujoco_ros2_control/plugins, domain 180 empty, prelaunch org.mujoco.mujoco not running, clean head 83a6e8c, and no production-source diff.
  - OBSERVED: The initially preregistered untyped `ros2 topic echo /cup_pose --once` observer exited 1 before RUNNING because no publisher existed to provide a topic type. The attempt is retained. A replacement observer explicitly supplied the already fixed geometry_msgs/msg/PoseStamped type, registered one subscription, and was recorded as owned session 21199 before RUNNING; this measurement-command deviation is another reason EXP-004 cannot count.
  - OBSERVED: The publisher-provenance observer was recorded as owned session 87454 and polled publisher count 0 before RUNNING. The durable RUNNING transition at wall_time_ns 1787693709792530000 retained both live observer PID/PGID/session records and readiness exit 0.
  - OBSERVED: The owned stack session 34760 started task_start/headless=false, but joint_state_broadcaster, arm_controller, and gripper_controller spawners each raised PermissionError for `/Users/matianyi/.ros/locks/ros2-control-controller-spawner.lock` and died with child exit 1. Controllers therefore never reached the preregistered initial state.
  - OBSERVED: After the first invalid boundary, no static TF, production rgbd_cup_pose timeout-90 command, Viewer attribution/action, dynamic_cup_pick_place, or robot motion was started.
  - OBSERVED: Exact owned sessions 87454, 21199, and 34760 received SIGINT; their wrapper sidecars are 130. Final targeted process output and ROS domain 180 output are both zero bytes with exit sidecars proving command exit 0 and empty results; cleanup exit is 0.
inferred:
  - INFERRED: EXP-004 contains no information about whether increasing production startup_timeout_s from 30 to 90 seconds changes perception behavior because production never started. The first bad boundary is sandbox denial of the controller-spawner lock, plus the pre-RUNNING observer command deviation; neither is the registered timeout variable.
conclusion: EXP-004 is INVALID and excluded from product success/failure denominators. The timeout-only A/B remains unmeasured; a new experiment may repeat timeout 90 only after preregistering the explicit PoseStamped observer type and ensuring the owned stack can access the existing ROS controller-spawner lock path.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/
decision: REPEAT_TIMEOUT_AB_AFTER_ENVIRONMENT_AND_MEASUREMENT_FIX
next_experiment: EXP-005
post_failure_rule: Because EXP-004 was INVALID before production, EXP-005 must repeat the same timeout-90 A/B with only the preregistered environment and observer-command corrections; instrument readiness only after that repeat is a fully evidenced VALID failure.
```

```yaml
checkpoint_id: CP-009
checkpoint_status: SUPERSEDED_BY_CORR-EXP-004-001
last_valid_experiment: EXP-002
current_hypothesis: A timeout-only 30 to 90 second A/B must run before production readiness instrumentation; EXP-003 cannot determine which production boundary failed.
working_tree_status: runtime source remains ef6175dd146275d56979ad2860f1f3a6f94dbf79; audit correction prepared from ledger commit 83a3033e51c6f6d47b1c4164be29252e8a929221 with only this ledger tracked dirty and the Task 7 report ignored
owned_processes: NONE_STARTED_BY_THIS_DOCUMENTATION_CORRECTION
preserved_processes: No process inspection, signal, live stack, test, build, or production command was run by this correction task
confirmed_conclusions:
  - EXP-003 is INVALID and non-counting because critical production stdout/stderr, exit sidecar, and RUNNING-transition evidence are missing.
  - The observed 30 s production attempt supports only the aggregate no-acceptable-/cup_pose statement; later independent exact-RGB-D, segmentation, and TF evidence does not isolate the production cause.
  - The retained targeted cleanup process scan is auditable; ROS graph emptiness is not because its zero-byte output lacks an exit sidecar.
disproven_routes:
  - EXP-003 cannot be used as a countable VALID failure or as proof that segmentation, fit, QoS/callback, TF timing, or another production-only stage was not the cause.
open_risks:
  - EXP-004 must retain every production and cleanup evidence boundary before it can be VALID.
  - Production pose, radius fit, publisher provenance, truth error, and Viewer visual acceptance remain unverified.
  - Existing retained and deletion-candidate evidence is unchanged; no artifact was deleted or archived.
next_command: After an implementer rechecks ledger, provenance, and isolation, write EXP-004 running-snapshot.txt plus running-snapshot.exit and only then transition EXP-004 from PLANNED to RUNNING before launching any process.
```

```yaml
correction_id: CORR-EXP-004-001
applies_to:
  - EXP-004 PLANNED measurement contract committed at 440dbbcbefcdbb69bb429329ac1b8239a4611e40
  - CP-009
recorded_at: 2026-08-26T05:35:00+08:00
reason: Final pre-run review required lossless first-publish observation and a causally attributable, inspected MuJoCo Viewer baseline-action-fresh-snapshot sequence before EXP-004 can transition to RUNNING.
history_preserved: The original EXP-004 hypothesis, prediction, lifecycle, behavior configuration, and timeout-only single variable remain unchanged; this amendment tightens measurement and validity gates before any process starts.
single_variable_unchanged: production rgbd_cup_pose --startup-timeout-s changes from 30 to 90 seconds
observer_contract:
  ordering:
    - Start the owned `/cup_pose` one-shot sample observer before production.
    - Prove its subscription is registered and retain the readiness log/exit sidecar.
    - Start the owned publisher-provenance polling observer before production.
    - Only after both owners, start timestamps, and readiness are durable may production start.
  sample_mechanism: ROS_DOMAIN_ID=180 ros2 topic echo /cup_pose --once
  provenance_mechanism: Poll ROS_DOMAIN_ID=180 ros2 topic info /cup_pose --verbose every 0.1 s and retain the first attempt with Publisher count 1 and Node name rgbd_cup_pose, including namespace, endpoint GID, type, and QoS.
  per_observer_evidence:
    - Complete stdout/stderr log.
    - Wall-clock and monotonic start/end timestamps.
    - Owned PTY/session plus wrapper PID and PGID.
    - Exact exit-code sidecar and observer-readiness evidence.
  termination:
    - Each observer exits itself after its first required evidence.
    - If production exits first, record stop wall/monotonic timestamps, SIGINT only the still-running exact owned observer session or PID/PGID, wait for trap-written end/exit sidecars, and prove no observer remains.
  validity_rule: Starting either observer after production, failing to prove readiness/ownership, missing any sidecar, or leaving an observer running makes EXP-004 INVALID.
visual_contract:
  attribution:
    - Before stack launch, Computer Use sky.list_apps must retain visual/viewer-prelaunch.json showing org.mujoco.mujoco isRunning=false; an already-running Viewer makes the run contaminated.
    - After the owned headless=false stack starts, retain visual/viewer-attribution.json with app identity, owned session/stack PID-PGID reference, wall/monotonic timestamps, and fresh accessibility/window state that ties the Viewer to EXP-004.
    - If org.mujoco.mujoco never becomes running or the owned session cannot be tied to it, do not launch another app and mark EXP-004 INVALID.
  sequence:
    - Save a full fresh baseline from sky.get_app_state to visual/viewer-baseline.png and visual/viewer-baseline.json.
    - Derive a small camera-view-only drag from the fresh baseline, perform it with sky.drag, and save app id, from/to coordinates, wall/monotonic timestamps, and purpose in visual/viewer-action.json.
    - Immediately call sky.get_app_state again and save visual/viewer-fresh.png and visual/viewer-fresh.json.
    - Record both image sizes and SHA-256 values and write visual/viewer-inspection.md describing the canonical cup, active owned MuJoCo scene, and visible view change actually inspected.
  validity_rule: Missing, stale, identical-without-explained-change, uninspected, or unattributable baseline-action-fresh evidence makes EXP-004 INVALID.
decision: KEEP_EXP-004_PLANNED_WITH_STRICTER_MEASUREMENT_CONTRACT
next_experiment: EXP-004
```

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-002
current_hypothesis: EXP-004 must test only timeout 30 to 90 while pre-start observers prevent loss of the first production sample/provenance and Computer Use proves a causally attributable Viewer sequence.
working_tree_status: runtime source remains ef6175dd146275d56979ad2860f1f3a6f94dbf79; final pre-run measurement amendment prepared from ledger commit 440dbbcbefcdbb69bb429329ac1b8239a4611e40 with only this ledger tracked dirty and Task 7 report ignored
owned_processes: NONE_STARTED_BY_THIS_DOCUMENTATION_CORRECTION
preserved_processes: No process inspection, signal, live stack, test, build, production command, or Computer Use action was run by this correction task
confirmed_conclusions:
  - EXP-003 remains INVALID and non-counting; EXP-004 remains PLANNED with timeout 30 to 90 as its only behavior variable.
  - The sample and publisher-provenance observers are measurement-only and must be running before production, with complete ordering, ownership, timestamps, logs, and exit evidence.
  - Viewer acceptance requires owned-stack attribution plus an actually inspected Computer Use baseline, camera-view-only action, and fresh snapshot; missing or unattributable visual evidence invalidates the run.
disproven_routes:
  - Starting `/cup_pose` observers after production can miss a transient first publish and cannot satisfy EXP-004.
  - A Viewer screenshot without prelaunch/postlaunch attribution, recorded Computer Use action, fresh post-action image, and inspection record cannot satisfy visual acceptance.
open_risks:
  - The Mac GLFW Viewer may not surface as org.mujoco.mujoco to Computer Use; if attribution cannot be established, EXP-004 must be INVALID rather than using an unrelated launched app.
  - Production pose, fit, publisher, truth-error, cleanup, and visual gates remain unrun.
next_command: Before any process, create EXP-004 evidence directories and complete running-snapshot plus prelaunch Viewer discovery; after the stack and static TF start, pre-start both owned `/cup_pose` observers and prove readiness before launching production with timeout 90.
```

```yaml
experiment_id: EXP-005
status: INVALID
result: ENVIRONMENT_INVALID_BEFORE_RUNNING
running_transition: NOT_REACHED
prior_experiment: EXP-004
hypothesis: Repeating the still-unmeasured production timeout-90 A/B with the owned MuJoCo stack launched through require_escalated will remove only the sandbox lock denial and allow the experiment to reach the production perception boundary without changing behavior.
prediction: The same task_start/headless=false stack reaches active controllers when run outside the filesystem sandbox, both pre-production observers are ready, and production rgbd_cup_pose either yields an acceptable /cup_pose within 90 s or provides a fully evidenced VALID product failure.
single_variable: NONE_BEHAVIOR; repeat timeout 90 after removing the EXP-004 sandbox execution contamination
lifecycle: ISOLATED_STACK
preconditions:
  - Production runtime source remains ef6175dd146275d56979ad2860f1f3a6f94dbf79 and the worktree is clean before the PLANNED to RUNNING transition.
  - Fresh readback proves current-worktree so101_demo_py/support/vendor, main-repository mujoco_ros2_control/plugins, empty ROS domain 180, unique session/partition, and prelaunch org.mujoco.mujoco not running.
  - The owned stack command alone is launched with require_escalated so existing `/Users/matianyi/.ros/locks/ros2-control-controller-spawner.lock` access matches the documented Mac runtime; HOME is unchanged and no lock file is copied, moved, replaced, or deleted.
  - The first-sample observer is preregistered as `ros2 topic echo /cup_pose geometry_msgs/msg/PoseStamped --once`; readiness proves its subscription before production. The publisher-provenance observer and all CORR-EXP-004-001 timestamp/ownership/exit gates remain unchanged.
  - Production remains `rgbd_cup_pose --startup-timeout-s 90`; task_start, topics, TF, camera, mask, DBSCAN, fit, QoS, scene, and controller configuration remain unchanged.
  - dynamic_cup_pick_place is never started and no robot motion is commanded.
success_criteria:
  - All EXP-004 observer, production, RGB-D, TF, truth-error, Viewer attribution/action/inspection, and cleanup evidence gates pass with complete sidecars.
  - All controllers reach active before production, and production provides its first acceptable world /cup_pose within 90 s with sole-publisher provenance and truth error at most 0.01 m.
failure_criteria:
  - With complete valid evidence and active controllers, production emits no acceptable /cup_pose within 90 s or fails any perception, publisher, fit, TF, truth-error, Viewer, or cleanup gate.
invalid_criteria:
  - The owned stack is not require_escalated, lock access still fails, HOME or lock files are altered, provenance/domain/session/initial state is contaminated, an observer/evidence/visual/cleanup sidecar is missing, an unowned process is reused or stopped, or motion starts.
provenance:
  source_commit: ef6175dd146275d56979ad2860f1f3a6f94dbf79
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place/install/so101_demo_py/lib/so101_demo_py/rgbd_cup_pose
  ros_domain_id: 180
  gz_partition: rgbd-perception-gate-exp005-20260826
commands:
  - command: create /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-005; capture clean head, exact package/import/runtime provenance, empty domain/process set, prelaunch Viewer=false, wall/monotonic timestamps, and exit sidecars before RUNNING
    exit_code: 1
  - command: start and prove ready the explicit-type first-sample observer and publisher-provenance observer before production, retaining complete CORR-EXP-004-001 logs/owners/timestamps/exits
    exit_code: NOT_STARTED_AFTER_PREFLIGHT_INVALID
  - command: with sandbox_permissions=require_escalated and unchanged HOME, run the same ROS_DOMAIN_ID=180 GZ_PARTITION=rgbd-perception-gate-exp005-20260826 ros2 launch so101_demo_py so101_mujoco.launch.py run_mode:=execute execute:=true headless:=false session_id:=rgbd-perception-gate-exp005-20260826 mujoco_initial_keyframe:=task_start command with complete stack log/owner/timestamp/exit evidence
    exit_code: NOT_REQUESTED_AFTER_PREFLIGHT_INVALID
  - command: after controllers are active, start the two unchanged approved static_transform_publisher commands, then production rgbd_cup_pose with --startup-timeout-s 90 and all sample/provenance/PLY/JSON/TF/truth/Viewer evidence captures
    exit_code: NOT_STARTED_AFTER_PREFLIGHT_INVALID
  - command: stop only exact owned observer/static-TF/production/stack sessions or PID/PGIDs with SIGINT and retain cleanup begin/end, each exit sidecar, empty targeted process output, and empty domain output plus command exit sidecars
    exit_code: 1
observed:
  - OBSERVED: At clean head ba70eac01f8b5a0aabd96c0616417547f4ef2c76, the normal HOME/lock gate passed. HOME was `/Users/matianyi`; the exact lock resolved to itself, was regular and not a symlink, and canonical before metadata was device 16777233, inode 13891096, uid 501, gid 20, mode 100644, size 0, atime 1787694630, mtime 1787691140, ctime 1787691140, SHA-256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855.
  - OBSERVED: Current-worktree so101_demo_py/support/vendor and main-repository mujoco_ros2_control/plugins provenance, clean source, production-source diff empty, and prelaunch `org.mujoco.mujoco isRunning=false` all passed.
  - OBSERVED: The first normal-scope isolation attempt failed before RUNNING. `ps -axo ...` was denied with `operation not permitted` and rc127. The initial domain probe also returned rc1 only because it attempted to write `/Users/matianyi/.ros/log/...`; this was retained rather than called a graph result.
  - OBSERVED: A normal-scope retry redirected ROS_LOG_DIR into the registered evidence root and proved ROS domain 180 empty with command rc0 and zero-byte output. All six targeted read-only `pgrep -lf` scans returned rc3, so process isolation remained unauditable and the aggregate retry exited 1.
  - OBSERVED: Because isolation never passed, observers were not started, PLANNED never transitioned to RUNNING, require_escalated was not requested, and no stack, static TF, production rgbd_cup_pose, Viewer baseline/action/fresh sequence, dynamic workflow, or robot motion started.
  - OBSERVED: Normal-shell after evidence exactly matched normal-before HOME, lstat/resolved path, SHA-256, and every metadata field; each comparison exit was 0. Elevated-before evidence is correctly absent because no elevated wrapper ran, so the aggregate environment-preservation sidecar is 1 rather than fabricated success.
  - OBSERVED: Final normal-scope ROS domain 180 output is empty with command rc0, and Computer Use again reported `org.mujoco.mujoco isRunning=false`. Final process cleanup cannot be claimed because the same six `pgrep` probes returned rc3; cleanup sidecar is 1. No long-lived owned process or session was ever started.
inferred:
  - INFERRED: EXP-005 measures only a normal-scope sandbox observability failure. It provides no evidence about controller activation, the 90-second production timeout, RGB-D, TF, segmentation/fit, /cup_pose, truth error, or Viewer acceptance.
conclusion: EXP-005 is INVALID and non-counting before RUNNING because its required process-isolation and cleanup process scans were unavailable in normal scope. HOME and the existing lock were demonstrably preserved, but that does not cure the missing isolation boundary. The timeout-90 A/B remains unmeasured.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-005/
decision: REPEAT_WITH_ELEVATED_READ_ONLY_ISOLATION_PROBES
next_experiment: EXP-006
```

```yaml
checkpoint_id: CP-011
last_valid_experiment: EXP-002
current_hypothesis: The timeout-90 perception A/B remains unmeasured because EXP-004 failed at sandbox controller-spawner lock access before static TF or production; EXP-005 must repeat it with only require_escalated stack execution as an environment correction.
working_tree_status: runtime source remains ef6175dd146275d56979ad2860f1f3a6f94dbf79; EXP-004 runtime documentation is the only tracked dirty file from clean head 83a6e8c828e1483c9d6e367e728120bbf03b91e2 and Task 7 report is ignored
owned_processes: NONE; owned EXP-004 sessions 87454, 21199, and 34760 received SIGINT and exact wrappers/process groups are absent
preserved_processes: No unowned process was signaled or modified; HOME and existing ROS lock files were not changed
confirmed_conclusions:
  - EXP-004 running/provenance/domain/Viewer-prelaunch/observer-readiness evidence was durable, but its environment was invalid when all three controller spawners were denied the existing ROS lock path.
  - Static TF, production timeout90, production pose/fit/truth comparison, Viewer action sequence, dynamic workflow, and motion never started in EXP-004.
  - Cleanup is durable: exact owned wrappers exited 130 after SIGINT, final targeted process and domain outputs are empty with exit 0 sidecars, and cleanup exit is 0.
disproven_routes:
  - EXP-004 cannot count as a timeout-90 product success/failure or support any perception-pipeline conclusion.
  - An untyped pre-publisher `ros2 topic echo /cup_pose --once` cannot establish the observer; the known PoseStamped type must be explicit in the next preregistration.
open_risks:
  - EXP-005 must prove require_escalated restores controller activation without altering HOME/locks before production.
  - The timeout-90 production, Viewer, and all downstream acceptance gates remain unmeasured.
  - Existing retained/deletion-candidate evidence is unchanged; nothing was deleted or archived.
next_command: In a new turn, re-read EXP-005, capture fresh clean provenance/domain/prelaunch Viewer evidence, start the explicit PoseStamped and provenance observers, then launch only the owned stack with require_escalated; do not start production until controllers are active.
```

```yaml
correction_id: CORR-EXP-005-001
applies_to: EXP-005
status: PLANNED
effective_status: SATISFIED_ONLY_FOR_NORMAL_BEFORE_AFTER; EXP-005 INVALID before elevated wrapper
outcome: Normal HOME/lock before-versus-after comparisons passed exactly, but elevated-before evidence is absent by design because process isolation failed and no elevation was requested; aggregate environment-preservation exit is 1.
recorded_after_commit: 3918f9d
reason: The original EXP-005 environment correction prohibited HOME and lock mutation but did not freeze durable before/elevated/after evidence sufficient to prove that require_escalated preserved the existing controller-spawner lock identity, metadata, and content digest.
correction_scope: Measurement-only preregistration; no runtime, build, test, production, GUI, permission escalation, HOME change, or lock operation occurred while recording this correction.
single_variable_effect: NONE; production startup_timeout_s remains 90 and all stack, TF, camera, perception, QoS, Viewer, scene, keyframe, and controller behavior remains unchanged.
lock_path: /Users/matianyi/.ros/locks/ros2-control-controller-spawner.lock
expected_home: /Users/matianyi
expected_mutable_lock_fields: NONE
prohibited_actions:
  - Do not assign, unset, override, or redirect HOME; do not use an alternate HOME or alternate ROS lock directory in either the normal shell or elevated wrapper.
  - Do not copy, move, replace, chmod, chown, truncate, delete, recreate, repair, or otherwise mutate the controller-spawner lock or its parent lock directory.
  - Do not read, print, parse, or retain lock contents. SHA-256 is computed mechanically with `shasum -a 256`; only its digest and path may be retained.
pre_run_evidence_contract:
  - In the normal preflight shell, write `$HOME` and its command exit to `environment/home-normal-before.txt` and `.exit`; require the value to be exactly `/Users/matianyi`.
  - Before requesting elevation, require the exact lock path to exist as a regular file; use `os.lstat` to retain path, `os.path.realpath`, raw lstat mode, and `is_symlink=0` in `environment/lock-normal-before.lstat.txt`, with an exit sidecar that is nonzero for missing, non-regular, or symlinked input.
  - Mechanically hash the exact lock with `shasum -a 256` into `environment/lock-normal-before.sha256`, then capture device, inode, uid, gid, mode, size, atime, mtime, and ctime using Darwin `/usr/bin/stat -f` into `environment/lock-normal-before.metadata.txt`; retain separate exact exit sidecars. Hash precedes metadata so the canonical before metadata includes any access-time effect caused by measurement itself.
  - The require_escalated stack wrapper must first record its own `$HOME` in `environment/home-elevated-before.txt`, prove exact equality with the normal-shell HOME using `cmp -s`, and retain both command and comparison exit sidecars before any ROS launch child starts.
  - Still inside the elevated wrapper and before any ROS launch child, repeat the same lstat/realpath/no-symlink gate, mechanical SHA-256, and Darwin stat capture as `lock-elevated-before.*`; compare the normal and elevated resolved path, lstat, digest, and metadata files byte-for-byte with `cmp -s`, retain each comparison exit, and refuse to launch on any nonzero result.
post_cleanup_evidence_contract:
  - After every owned process has exited and before concluding EXP-005, the unchanged normal shell must record `home-normal-after.txt`, repeat the same missing/non-regular/symlink lstat gate, hash-first SHA-256, and Darwin stat metadata capture as `lock-after.*`, with complete exit sidecars.
  - Compare normal-before, elevated-before, and after HOME byte-for-byte; compare the canonical elevated-before resolved path, lstat, SHA-256, and every metadata field against after cleanup byte-for-byte. Retain each `cmp -s` result plus `environment-preservation.compare.txt` and `.exit` aggregating all required checks.
  - Exact preservation is preregistered: no atime, mtime, ctime, size, mode, ownership, inode, device, path, lstat type, or digest difference is expected. Any difference makes EXP-005 INVALID rather than being explained after seeing the result.
exact_commands:
  - command: In the normal shell, set the task-specific non-exported variable `exp005_evidence=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-005`, create only its `environment` evidence directory, run `printf '%s\n' "$HOME" > "$exp005_evidence/environment/home-normal-before.txt"; printf '%s\n' "$?" > "$exp005_evidence/environment/home-normal-before.exit"`, require the file to contain exactly `/Users/matianyi`, then use `/usr/bin/python3 -c 'import os,stat,sys; p=sys.argv[1]; s=os.lstat(p); print(f"path={p}\\nrealpath={os.path.realpath(p)}\\nmode={oct(s.st_mode)}\\nis_regular={int(stat.S_ISREG(s.st_mode))}\\nis_symlink={int(stat.S_ISLNK(s.st_mode))}"); raise SystemExit(0 if stat.S_ISREG(s.st_mode) and not stat.S_ISLNK(s.st_mode) else 1)' /Users/matianyi/.ros/locks/ros2-control-controller-spawner.lock` into `lock-normal-before.lstat.txt` plus its exact exit sidecar.
    exit_code: PENDING
  - command: In the normal shell, run `/usr/bin/shasum -a 256 /Users/matianyi/.ros/locks/ros2-control-controller-spawner.lock` into `lock-normal-before.sha256` plus exit sidecar, then `/usr/bin/stat -f 'device=%d inode=%i uid=%u gid=%g mode=%p size=%z atime=%a mtime=%m ctime=%c' /Users/matianyi/.ros/locks/ros2-control-controller-spawner.lock` into `lock-normal-before.metadata.txt` plus exit sidecar; do not otherwise open or inspect the file.
    exit_code: PENDING
  - command: As the first statements inside the require_escalated stack wrapper, capture `$HOME` as `home-elevated-before.txt`, repeat the exact lstat, SHA-256-then-stat commands as `lock-elevated-before.*`, and use `/usr/bin/cmp -s` to require normal-before versus elevated-before HOME, lstat/resolved path, digest, and metadata equality; write every exit and aggregate `elevated-prelaunch.compare.exit`, and start `ros2 launch` only when all are 0.
    exit_code: PENDING
  - command: After cleanup, capture `home-normal-after.txt`, repeat the exact lstat, SHA-256-then-stat commands as `lock-after.*`, use `/usr/bin/cmp -s` for all preregistered HOME/path/lstat/digest/metadata comparisons, and write every exit plus human-readable `environment-preservation.compare.txt` and aggregate `environment-preservation.compare.exit`; any nonzero makes EXP-005 INVALID.
    exit_code: PENDING
invalid_criteria:
  - Either HOME value differs from `/Users/matianyi` or differs between normal-before, elevated-before, and normal-after evidence.
  - The exact lock is missing, is not a regular file, is a symlink, resolves to another path, or any required lstat/metadata/hash/comparison/exit sidecar is missing or nonzero.
  - Any lock device, inode, uid, gid, mode, size, atime, mtime, ctime, resolved path, lstat type, or SHA-256 value differs between the canonical elevated-before and after-cleanup records; no field exception is preregistered.
  - Any prohibited HOME/lock/lock-directory action occurs, even if later evidence appears equal.
decision: This correction is part of EXP-005's effective PLANNED contract and must be satisfied before PLANNED transitions to RUNNING; it does not start EXP-005.
```

```yaml
checkpoint_id: CP-012
last_valid_experiment: EXP-002
current_hypothesis: EXP-005 may remove only EXP-004's sandbox lock denial by elevating the owned stack while preserving the exact existing HOME and controller-spawner lock identity, metadata, and digest; the timeout-90 production A/B remains unmeasured.
working_tree_status: At correction authoring, only the experiment ledger is tracked dirty from clean documentation head 3918f9d; the Task 7 report remains ignored and the correction must be committed ledger-only.
owned_processes: NONE_STARTED_OR_INSPECTED_BY_CORR-EXP-005-001
preserved_processes: No runtime, process scan, signal, build, test, production command, GUI action, or permission escalation was performed; existing HOME, lock, evidence, and unowned processes were untouched.
confirmed_conclusions:
  - CORR-EXP-005-001 adds measurement-only HOME and exact lock-preservation gates without changing EXP-005's timeout90 behavior variable.
  - The elevated wrapper must fail closed before ROS launch if HOME, regular-file/no-symlink, resolved path, hash, metadata, or comparison evidence is absent or nonzero.
  - Post-cleanup exact comparison has no preregistered mutable lock field; any difference makes the run INVALID and may not be retrospectively justified.
disproven_routes:
  - Elevation alone is not evidence that HOME and the existing controller-spawner lock were preserved.
  - Copying, moving, replacing, permission-changing, truncating, deleting, recreating, or redirecting the lock/HOME to make the stack launch is prohibited and invalidates EXP-005.
open_risks:
  - The unchanged controller spawners may themselves change a lock field; because no expected mutation is preregistered, such a result will invalidate EXP-005 and require a separately planned investigation.
  - EXP-005 runtime, timeout90 production, Viewer, pose/truth, and downstream acceptance remain unrun.
  - Existing retained/deletion-candidate evidence remains unchanged; nothing was deleted or archived.
next_command: In a new turn only, re-read EXP-005 plus CORR-EXP-005-001, create its registered evidence directories, capture the normal-shell HOME and lock gates plus existing provenance/domain/Viewer preflight, then start observers and request require_escalated only for the owned wrapper that rechecks HOME/lock before launching the stack.
```

```yaml
experiment_id: EXP-006
status: INVALID
result: INTERRUPTED_ENVIRONMENT_INVALID_BEFORE_PRODUCTION
running_transition:
  wall_time_ns: 1787695702048939000
  monotonic_ns: 1488248994071083
  source_head: 572bba7b2703245bee6396ea5ca546e59e81f6e8
  preflight_final_exit: 0
  canonical_pre_probe_exit: 0
  observer_readiness_final_exit: 0
  sample_observer_session: 18865
  publisher_provenance_observer_session: 50421
prior_experiment: EXP-005
hypothesis: EXP-005's only unresolved preflight contamination was the filesystem sandbox blocking read-only process enumeration; permitting only the exact read-only isolation probes plus the already approved owned stack wrapper through require_escalated will reach the still-unmeasured production timeout-90 boundary without changing robot or perception behavior.
prediction: Elevated read-only process probes prove no conflicting stack, the unchanged elevated owned stack reaches active controllers while preserving HOME/lock, and normal-scope observers plus production either yield an acceptable /cup_pose within 90 s or retain a fully evidenced VALID product failure.
single_variable: Relative to EXP-005, allow require_escalated for exact read-only process-isolation probes; the owned stack remains require_escalated as already planned, while timeout90 and all behavior remain unchanged.
lifecycle: ISOLATED_STACK
preconditions:
  - Reprove clean current-worktree so101_demo_py/support/vendor and main-repository mujoco_ros2_control/plugins provenance, empty ROS domain 180 with ROS_LOG_DIR under the registered evidence root, unique EXP-006 session/partition, and prelaunch Viewer=false in normal scope.
  - Reuse CORR-EXP-005-001 unchanged: normal-before, elevated-wrapper-before, and normal-after HOME plus exact lock lstat/path/hash/stat evidence and comparisons are mandatory; expected mutable lock fields remain NONE and all prohibited HOME/lock operations remain prohibited.
  - Only two tool-call classes may use require_escalated: exact read-only process-isolation probes and the exact owned `ros2 launch so101_demo_py so101_mujoco.launch.py ...` stack wrapper. Observers, ROS graph probes, TF, production, Computer Use, samples, truth, evidence capture, and cleanup signaling remain normal scope.
  - The elevated process probe may only execute `/bin/ps -axo pid=,ppid=,pgid=,comm=,args=` and targeted read-only matching into the registered evidence root; it must record HOME, wall/monotonic start/end, command, exit, and zero conflicting matches, and may not signal or mutate any process.
  - The explicit PoseStamped first-sample observer and publisher-provenance observer are started and proven ready before RUNNING. Production remains `rgbd_cup_pose --startup-timeout-s 90`; task_start, TF, camera, mask, DBSCAN, fit, QoS, Viewer, scene, and controllers remain unchanged.
  - dynamic_cup_pick_place is never started and no robot motion is commanded.
success_criteria:
  - Every EXP-005 provenance, observer, stack/controller, static TF, production sample/provenance, aligned RGB-D, PLY/JSON, world TF, truth error at most 0.01 m, causally attributed Viewer baseline/action/fresh inspection, HOME/lock, and cleanup gate passes with complete sidecars.
  - Production's sole acceptable world /cup_pose is observed within 90 s and owned publisher provenance is complete.
failure_criteria:
  - With clean elevated read-only isolation, active controllers, exact environment preservation, and complete valid evidence, production emits no acceptable /cup_pose within 90 s or fails a product acceptance gate.
invalid_criteria:
  - Any command other than the exact read-only isolation probe and exact owned stack wrapper is elevated; a probe mutates/signals state; HOME/lock differs; process/domain/provenance/session/Viewer/observer/evidence/cleanup gates are absent or nonzero; an unowned process is reused/stopped; or dynamic/motion starts.
provenance:
  source_commit: ef6175dd146275d56979ad2860f1f3a6f94dbf79
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place/install/so101_demo_py/lib/so101_demo_py/rgbd_cup_pose
  ros_domain_id: 180
  gz_partition: rgbd-perception-gate-exp006-20260826
commands:
  - command: In normal scope create `/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-006/`, capture CORR-EXP-005-001 normal-before HOME/lock, clean provenance, empty domain180 with evidence-local ROS_LOG_DIR, and Viewer prelaunch=false.
    exit_code: 0
  - command: With require_escalated, run only the owned read-only process-isolation wrapper containing `/bin/ps -axo pid=,ppid=,pgid=,comm=,args=` plus targeted matching, capture unchanged HOME/timestamps/command/exit, require zero conflicts, and make no signal or mutation.
    exit_code: 0
  - command: In normal scope start and prove ready the explicit PoseStamped first-sample and publisher-provenance observers, then retain the RUNNING transition snapshot.
    exit_code: 0
  - command: With require_escalated, run only the exact owned task_start/headless=false `ros2 launch so101_demo_py so101_mujoco.launch.py` stack wrapper after its independent CORR-EXP-005-001 elevated HOME/lock equality gate; require all controllers active.
    exit_code: 0
  - command: In normal scope start the exact two static TFs and production `rgbd_cup_pose --startup-timeout-s 90`, capture all production/sample/TF/truth/Viewer evidence, then SIGINT only exact owned sessions/PGIDs and retain empty domain/process plus after HOME/lock comparisons.
    exit_code: INTERRUPTED_AFTER_STATIC_TF_BEFORE_PRODUCTION; PROCESS_AND_DOMAIN_CLEANUP_0; ENVIRONMENT_PRESERVATION_1
observed:
  - OBSERVED: Normal preflight passed at clean head 572bba7b2703245bee6396ea5ca546e59e81f6e8 after retaining an initial documentation-only attempt that incorrectly expanded the task's short head to a wrong full hash. The corrected readback, source/package/runtime provenance, empty domain 180, normal HOME/lock, and Viewer-not-running gates all exited 0.
  - OBSERVED: The canonical elevated read-only pre probe exited 0 with ps_rc=0, matcher_rc=0, HOME/hash comparisons 0, and zero-byte targeted output. Explicit PoseStamped sample observer session 18865 and publisher-provenance observer session 50421 retained owners/start timestamps; actual `/cup_pose` topic readback showed Publisher count 0 and Subscription count 1 before the durable RUNNING transition.
  - OBSERVED: An additional normal-scope `kill -0` readiness diagnostic returned 1 under the sandbox. It was not a preregistered readiness gate and did not replace the actual topic endpoint, owner/timestamp, and continuously timestamped publisher-provenance evidence; the failed extra diagnostic is retained.
  - OBSERVED: The elevated stack wrapper independently proved elevated HOME and normal-versus-elevated lock lstat/path/SHA/stat equality, then started owned session 37058. All three controllers were sampled active - arm_controller, gripper_controller, and joint_state_broadcaster. The stack log also proved real CameraPlugin initialization and a 640x480 rendering loop.
  - OBSERVED: Exact normal-scope static TF sessions 90059 and 43155 published camera_link to task_camera_frame and base to camera_link with the approved translations/rotations. A bounded Python tf2 Buffer diagnostic did not return and was stopped as owned session 88538; a replacement tf2_echo session 31727 was still sourcing/waiting when the user changed the immediate objective.
  - OBSERVED: Per the user interruption, production `rgbd_cup_pose --startup-timeout-s 90`, production RGB-D sample/PLY/JSON/publisher/truth error, and Viewer baseline/action/fresh inspection were never started. dynamic_cup_pick_place and robot motion never started.
  - OBSERVED: Normal cleanup sent Ctrl-C only to exact owned sessions 18865, 50421, 90059, 43155, 31727, and 37058; the Python diagnostic 88538 had already been stopped with Ctrl-C. Observer/TF/tf2 wrappers exited 130, while the owned stack completed ordered controller/hardware shutdown and exited 0.
  - OBSERVED: The canonical elevated post probe exited 0 with ps/matcher/HOME/hash comparisons 0 and zero-byte targeted output; its command SHA-256 exactly matched pre. Final ROS domain 180 was empty with command rc0, and Computer Use reported org.mujoco.mujoco not running. Therefore no exact-owned target remains live.
  - OBSERVED: Normal-before/elevated-before/normal-after HOME, resolved path, lstat type, device 16777233, inode 13891096, uid 501, gid 20, mode 100644, size 0, and SHA-256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 remained equal. Strict metadata comparison failed because atime changed 1787694630 to 1787707782 and mtime/ctime changed 1787691140 to 1787707487; environment-preservation exit is 1 as preregistered.
inferred:
  - INFERRED: EXP-006 proves the approved elevation boundary can overcome EXP-004/005's lock-access and process-observability contamination through active controllers and exact cleanup. It does not measure perception timeout90 or any product acceptance gate because production never started.
  - INFERRED: The unchanged empty lock digest and stable file identity show no content replacement, but controller-spawner use changed timestamps. Because expected_mutable_lock_fields was preregistered as NONE, the metadata difference independently invalidates the run and cannot be retrospectively waived.
conclusion: EXP-006 is INVALID and non-counting. The immediate runtime was safely stopped and handed off with no owned target remaining, but the experiment was interrupted before production/Viewer product gates and failed strict lock metadata preservation. No conclusion about RGB-D segmentation, fit, /cup_pose, truth error, or timeout90 is supported.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-006/
decision: STOP_AND_HANDOFF
next_experiment: NONE
```

```yaml
checkpoint_id: CP-013
last_valid_experiment: EXP-002
current_hypothesis: The timeout-90 production A/B remains unmeasured; EXP-005 was invalid only because normal-scope process enumeration was unavailable, while source/runtime, domain, Viewer prelaunch, and normal HOME/lock preservation passed.
working_tree_status: EXP-005 outcome plus EXP-006 plan are the only tracked ledger edits from clean head ba70eac01f8b5a0aabd96c0616417547f4ef2c76; Task 7 report is ignored.
owned_processes: NONE; EXP-005 never started any long-lived observer, stack, TF, production, Viewer action, dynamic workflow, or motion process.
preserved_processes: No signal was sent. No elevated runtime command was requested. HOME and the exact existing controller-spawner lock matched byte-for-byte before versus after in normal scope.
confirmed_conclusions:
  - EXP-005 is INVALID before RUNNING and contributes no product result; normal `ps` was denied rc127 and targeted `pgrep` returned rc3.
  - Domain 180 was proven empty after moving only ROS logging into the registered evidence root; the initial ROS-log write failure is retained as a superseded probe attempt, not a graph result.
  - Normal-before versus normal-after HOME, resolved path/lstat, SHA-256, and all lock metadata fields matched exactly; no elevated-before evidence exists because elevation was never requested.
  - MuJoCo Viewer was not running both before and after the invalid attempt; no Computer Use action occurred.
disproven_routes:
  - Normal-scope process enumeration in the current sandbox cannot satisfy the isolation or cleanup-process gate.
  - Proven empty ROS graph or unchanged lock cannot substitute for an auditable process scan.
open_risks:
  - EXP-006 elevated read-only probes require explicit approval and must be limited to read-only enumeration; denial or any wider command makes the next attempt invalid.
  - Controller activation, timeout90 production, RGB-D/pose/truth, Viewer action, and all downstream product gates remain unrun.
  - Existing evidence is retained; nothing was archived or deleted.
next_command: In a new turn only, re-read EXP-006, capture normal HOME/lock/provenance/domain/Viewer preflight, then request require_escalated for the exact read-only isolation probe; do not start observers or stack unless it exits 0 with zero conflicts.
```

```yaml
correction_id: CORR-EXP-006-001
applies_to: EXP-006
status: PLANNED
recorded_after_commit: 999f7bf713a725100babcb2da8d6409ce4b67572
reason: EXP-006 originally preregistered the elevated read-only process-isolation probe only before observers/RUNNING while its cleanup command still ambiguously required an empty process result in normal scope, which EXP-005 proved unavailable.
correction_scope: Measurement-only; no runtime, elevation, process probe, test, build, ROS command, GUI action, signal, or cleanup was performed while recording this correction.
single_variable_effect: NONE; the identical exact elevated read-only targeted process probe is now required at both the pre-observers/pre-RUNNING and post-normal-cleanup boundaries, while timeout90 and all robot/perception behavior remain unchanged.
canonical_probe_contract:
  executable: /bin/ps
  arguments: -axo pid=,ppid=,pgid=,comm=,args=
  bounded_targets:
    - rgbd_cup_pose
    - dynamic_cup_pick_place
    - so101_mujoco.launch.py
    - ros2_control_node
    - static_transform_publisher
    - rgbd-perception-gate-exp006-20260826
  self_exclusion: Exclude only the exactly recorded probe wrapper, `/bin/ps` child, bounded matcher PID, and their explicitly recorded tool-runner parent PID; every excluded PID/PGID/command must be retained in the phase owner sidecar, and no target process may be excluded by name, session, or ownership assumption.
  output_rule: Retain only rows matching the bounded target list after exact self-exclusion; zero bytes means no conflict only when the ps command, matcher, HOME check, command comparison, and aggregate phase exit are all 0.
  safety_rule: The probe is read-only. It may not signal, stop, inspect file contents, change priority, attach, mutate environment outside its wrapper, or modify any process or system state.
identical_boundary_contract:
  - Write one canonical probe command text under `exp-006/isolation/canonical-probe-command.txt` and its SHA-256 before either invocation. Both elevated tool calls execute that exact body with only a phase argument of `pre` or `post`; retain each rendered command plus SHA-256 and byte-compare the invariant body to the canonical file.
  - The pre probe runs after normal HOME/lock/provenance/domain/Viewer preflight and before any observer starts or PLANNED transitions to RUNNING. Retain `isolation/pre.home.txt`, `.owner`, `.command.txt`, `.command.sha256`, `.start.wall_ns`, `.start.monotonic_ns`, `.targeted.txt`, `.stderr`, `.end.wall_ns`, `.end.monotonic_ns`, and `.exit`.
  - The post probe runs only after normal-scope SIGINT has been sent to every exact owned remaining observer/static-TF/production/stack session or PGID and their wrapper exits have been retained. Retain the identical `isolation/post.*` evidence set.
  - Both probes require `$HOME` to equal `/Users/matianyi` and to byte-match normal-before HOME. Each phase requires `/bin/ps` exit 0, matcher exit 0, canonical command comparison exit 0, zero-byte targeted output, and aggregate phase exit 0.
  - Compare the pre and post invariant command text/SHA-256 and bounded target list exactly; retain `isolation/pre-vs-post-command.compare.txt` and `.exit`. Only the phase label, phase-specific output filenames, owner PIDs/PGIDs, and timestamps may differ.
cleanup_order:
  - In normal scope record cleanup begin wall/monotonic timestamps and the exact owned session/PID/PGID set.
  - In normal scope send SIGINT only to those exact owned sessions/PGIDs, wait for every wrapper exit sidecar, and prove no owned wrapper remains using its exact owner records. No cleanup signal may be elevated.
  - Run the canonical post elevated read-only probe and require zero bounded matches with complete sidecars.
  - In normal scope capture empty domain 180 with an evidence-local ROS_LOG_DIR, normal-after HOME/lock exact comparisons, cleanup end timestamps, and aggregate cleanup exit.
invalid_criteria:
  - Either boundary does not run the canonical exact elevated read-only probe, runs a different target list/body, lacks HOME/command/owner/wall/monotonic/output/exit evidence, returns nonzero, or retains any conflicting target row.
  - The post probe runs before all normal-scope exact-owned SIGINT/wrapper-exit evidence is complete, cleanup signaling is elevated, any unowned process is signaled, or the probe itself signals or mutates state.
  - Any self-exclusion is not tied to an exactly recorded probe/tool PID or hides a bounded target process; any command/body/target comparison is nonzero or missing.
  - All existing EXP-006 provenance, observer, controller, perception, Viewer, HOME/lock, domain, evidence, no-dynamic/no-motion, and cleanup invalid criteria remain in force.
decision: CORR-EXP-006-001 is part of EXP-006's effective PLANNED measurement contract and must pass at both boundaries; it does not start EXP-006.
```

```yaml
checkpoint_id: CP-014
last_valid_experiment: EXP-002
current_hypothesis: EXP-006 may reach the still-unmeasured timeout90 production boundary only if the same bounded elevated read-only process probe proves isolation both before observers/RUNNING and after normal-scope exact-owned cleanup.
working_tree_status: At correction authoring, only the experiment ledger is tracked dirty from clean head 999f7bf713a725100babcb2da8d6409ce4b67572; Task 7 report remains ignored and the correction must be committed ledger-only.
owned_processes: NONE_STARTED_OR_INSPECTED_BY_CORR-EXP-006-001
preserved_processes: No process probe, elevation, signal, runtime, test, build, ROS command, GUI action, HOME/lock operation, or evidence deletion occurred.
confirmed_conclusions:
  - CORR-EXP-006-001 closes EXP-006's cleanup observability gap by requiring one canonical elevated read-only targeted probe at both pre-RUNNING and post-normal-cleanup boundaries.
  - Cleanup signaling remains normal-scope and exact-owned only; elevation is measurement-only after cleanup and cannot broaden signal authority.
  - A zero-byte targeted output is accepted only with complete command/owner/HOME/timestamp/comparison sidecars and aggregate exit 0; either a conflicting row or nonzero/missing evidence makes EXP-006 INVALID.
disproven_routes:
  - A pre-RUNNING process probe cannot substitute for the post-cleanup process boundary.
  - Empty ROS graph, exact wrapper exits, or unchanged HOME/lock cannot substitute for the canonical post-cleanup targeted process probe.
open_risks:
  - Both elevated read-only probe approvals and the separate owned-stack approval remain external preconditions; denial makes the run invalid without workaround.
  - EXP-006 controller, timeout90 perception, /cup_pose, truth error, Viewer sequence, and downstream product gates remain unrun.
  - Existing evidence remains retained; nothing was archived or deleted.
next_command: In a new turn only, re-read EXP-006 plus CORR-EXP-006-001, capture normal preflight and canonical probe command evidence, then request require_escalated for the pre probe; do not start observers unless it exits 0 with zero targeted rows.
```

```yaml
checkpoint_id: CP-015
last_valid_experiment: EXP-002
current_hypothesis: The production timeout90 hypothesis remains unmeasured. EXP-006 reached active controllers and static TF publishers under the approved elevation boundary, but user interruption and strict lock timestamp changes made the run INVALID before production.
working_tree_status: EXP-006 final INVALID result is the only tracked ledger edit from clean head 572bba7b2703245bee6396ea5ca546e59e81f6e8; Task 7 report is ignored and must be updated before a ledger-only commit.
owned_processes: NONE; canonical post probe targeted output is zero bytes with exit 0, domain 180 is empty with exit 0, and Viewer is not running.
preserved_processes: Only exact owned sessions 18865, 50421, 90059, 43155, 31727, 37058, and prior diagnostic 88538 received Ctrl-C. No broad kill, unowned signal, dynamic workflow, production command, Viewer action, or robot motion occurred.
confirmed_conclusions:
  - Approved elevated process probes passed both boundaries with identical command SHA-256 and no bounded target matches; normal exact-owned cleanup completed.
  - Elevated stack HOME/lock prelaunch equality passed and all three controllers reached active, so EXP-004's lock PermissionError was not repeated.
  - Exact static TF publishers started, but no acceptable TF lookup sample completed before interruption and production/Viewer acceptance never started.
  - Lock identity, ownership, mode, size, and digest remained exact, while atime/mtime/ctime changed; strict CORR-EXP-005-001 therefore invalidates EXP-006 independently of the interruption.
disproven_routes:
  - Active controllers and healthy camera-render logs cannot substitute for production RGB-D samples, /cup_pose, PLY/JSON, truth error, or Viewer inspection.
  - Successful process/domain cleanup cannot convert an interrupted or environment-invalid run into a countable product result.
open_risks:
  - The timeout90 production chain and TF lookup behavior remain unmeasured under the repaired elevation boundary.
  - Any future experiment must explicitly decide before launch whether controller-spawner timestamp changes are expected; EXP-006's frozen NONE rule cannot be rewritten.
  - Existing evidence remains retained; nothing was archived or deleted.
next_command: NONE; runtime experimentation is stopped per user direction. Await a new explicitly preregistered experiment before any process, elevation, production, GUI action, or motion.
```

```yaml
experiment_id: EXP-007
status: PLANNED
prior_experiment: EXP-006
hypothesis: A fresh ai-station Linux overlay built from the exact pinned mujoco_ros2_control commit f19a8cc3af61feccacb22a9f0d16cc972e3b2c08 can produce one production-owned, fresh world /cup_pose from real aligned RGB-D within 0.01 m of MuJoCo truth before any dynamic workflow or robot motion starts.
prediction: After the exact gitlink/submodule/cleanliness and installed-runtime provenance gates pass, an isolated task_start stack will provide aligned 640x480 rgb8 and 32FC1 samples, finite positive depth, a nonempty segmented cup cloud and valid fit, exact-stamp TF, sole rgbd_cup_pose publisher provenance, and a world pose within 0.01 m of current MuJoCo truth, together with an inspected baseline-action-fresh Viewer sequence and exact-owned cleanup.
single_variable: Run on ai-station Linux with a fresh task-owned build/install overlay instead of the prior Mac runtime environment; production code and perception configuration remain fixed at source commit 12c0d69252f8b84ad1335877192bf23b22947c52.
lifecycle: ISOLATED_STACK
preconditions:
  - The task worktree is /data/work/ws_moveit/.worktrees/rgbd-perception-pick-place on codex/rgbd-perception-pick-place at exactly 12c0d69252f8b84ad1335877192bf23b22947c52, with no user-owned tracked changes except this planned ledger entry.
  - git ls-tree HEAD third_party/mujoco_ros2_control, the task-worktree submodule HEAD, and the runtime build input all equal f19a8cc3af61feccacb22a9f0d16cc972e3b2c08; describe is so101-0.0.3-r8-3-gf19a8cc and the submodule is clean.
  - The required f19a8cc commit is fetched from the configured Gitee submodule origin; no canonical-main r6 build/install or local substitute is used.
  - Fresh build and install bases are task-owned below /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/ and all installed package prefixes and runtime executables are read back before launch.
  - ROS_DOMAIN_ID 185 and GZ_PARTITION rgbd-perception-ai-station-exp007-20260826 are empty and unique immediately before RUNNING, and no unowned conflicting simulator, MoveIt, controller, perception, dynamic workflow, or Viewer process is reused or stopped.
  - dynamic_cup_pick_place is not started and no robot motion is commanded in EXP-007.
success_criteria:
  - Real CameraInfo, color, and depth form one exact-stamp 640x480 task_camera_frame triple with rgb8 and 32FC1 encodings and finite positive depth.
  - Production rgbd_cup_pose is the sole fresh /cup_pose publisher, writes a nonempty selected PLY and JSON receipt with a valid fitted radius, and retains the aligned source stamp.
  - world to task_camera_frame TF succeeds at the source stamp and the finite world /cup_pose differs from current MuJoCo cup truth by at most 0.01 m.
  - A causally attributable MuJoCo Viewer baseline, camera-view-only action, and fresh screenshot are retained and actually inspected.
  - Only exact owned processes are stopped; the final targeted process set and ROS domain are empty with complete exit sidecars.
failure_criteria:
  - With all preconditions and evidence contracts satisfied, any RGB-D, segmentation, fit, TF, publisher, freshness, truth-error, visual, or cleanup product gate fails.
invalid_criteria:
  - The required submodule commit is unavailable from Gitee, the gitlink/HEAD/describe/cleanliness assertions fail, any runtime resolves to canonical r6 or another overlay, isolation or evidence is contaminated, an unowned process is reused or stopped, or dynamic workflow/robot motion starts.
provenance:
  source_commit: 12c0d69252f8b84ad1335877192bf23b22947c52
  install_overlay: /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/install
  runtime_executable: /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/install/so101_demo_py/lib/so101_demo_py/rgbd_cup_pose
  ros_domain_id: 185
  gz_partition: rgbd-perception-ai-station-exp007-20260826
commands:
  - command: In the task worktree run git submodule sync --recursive, fetch the required exact commit from the configured Gitee origin, run git submodule update --init --recursive, and assert gitlink equals submodule HEAD f19a8cc3af61feccacb22a9f0d16cc972e3b2c08, describe equals so101-0.0.3-r8-3-gf19a8cc, and submodule status is clean.
    exit_code: PENDING
  - command: Build and test Tasks 1-6 into the fresh task-owned build/install overlay, source it, and prove package prefixes plus ros2_control_node and MuJoCo runtime provenance derive from f19a8cc.
    exit_code: PENDING
  - command: Capture complete RUNNING provenance/isolation/ownership evidence, then start only the isolated task_start MuJoCo stack, approved static TF publishers, pre-start /cup_pose observers, and production rgbd_cup_pose with complete logs/timestamps/exits.
    exit_code: PENDING
  - command: Capture aligned RGB-D, finite-depth, point-cloud/fit, TF, /cup_pose publisher/source-stamp, MuJoCo truth-error, and ai-station Viewer baseline-action-fresh evidence; then stop only exact owned processes and prove cleanup.
    exit_code: PENDING
observed:
  - NONE; EXP-007 has not transitioned to RUNNING because its required submodule precondition is not currently satisfiable from Gitee.
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/
decision: PENDING
next_experiment: NONE
```

```yaml
checkpoint_id: CP-016
last_valid_experiment: EXP-002
current_hypothesis: EXP-007 can test the fresh ai-station Linux perception-only boundary only after the exact f19a8cc submodule commit becomes fetchable from Gitee and the gitlink/HEAD/describe/clean gate passes.
working_tree_status: Branch codex/rgbd-perception-pick-place is at 12c0d69252f8b84ad1335877192bf23b22947c52; this ledger is tracked dirty, and the failed submodule initialization leaves third_party/mujoco_ros2_control at 78758d5 with an unpopulated/deleted worktree rather than the required gitlink target.
owned_processes: NONE; no stack, Viewer action, controller, static TF, perception, dynamic workflow, or robot motion was started.
preserved_processes: Existing tmux sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui were only listed and were not sent input, stopped, or modified. No unowned process was signaled.
confirmed_conclusions:
  - Canonical main remains clean at b3770360b26fe8f6fac0e19338d250b6f5cab0e7 with gitlink/submodule 738e304551b4ea6db020b466086a13db71b65607 (so101-0.0.3-r6); it was not modified.
  - The independent task worktree is on codex/rgbd-perception-pick-place at exact commit 12c0d69252f8b84ad1335877192bf23b22947c52, whose gitlink is exact f19a8cc3af61feccacb22a9f0d16cc972e3b2c08.
  - Gitee advertises mujoco_ros2_control main/tag so101-0.0.3-r8 at 78758d5becf1829e611da1dafb201fa018ddbe7b, but no head/tag at f19a8cc; exact fetch of f19a8cc returns 128 with `not our ref`, and the required object remains absent.
  - The initial ROS graph contained only /parameter_events and /rosout; targeted process inspection found no simulator, MoveIt, controller, perception, dynamic workflow, or Viewer runtime conflict.
  - CP-015 is preserved: EXP-006 remains strict INVALID because controller-spawner lock atime/mtime/ctime changed, all Mac exact-owned sessions exited, post probe and target set were empty, domain 180 was empty, Viewer was false, and production, Viewer action, dynamic workflow, and robot motion never started.
disproven_routes:
  - Canonical r6 and Gitee r8 tag 78758d5 cannot satisfy the required f19a8cc runtime provenance gate.
  - EXP-003 through EXP-006 remain non-counting INVALID runs and are not treated as product failures, passes, or reasons to repeat their prior contaminated routes.
open_risks:
  - The exact f19a8cc commit must be published to the configured Gitee submodule origin before build/runtime can proceed.
  - The failed checkout is retained in place for audit and must not be treated as a clean or usable submodule.
  - EXP-007 perception, TF, Viewer, and all four later FULL_RESTART physical acceptance runs remain unstarted.
next_command: git -C /data/work/ws_moveit/.worktrees/rgbd-perception-pick-place/third_party/mujoco_ros2_control fetch origin f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
```

```yaml
correction_id: CORR-CP-016-001
applies_to:
  - CP-016
  - EXP-007 preconditions and provenance
recorded_at: 2026-08-26T09:51:55+08:00
reason: After CP-016 was committed, the orchestrator published the previously unavailable pinned submodule commit to the configured Gitee origin and completed the task-worktree submodule update. This correction records the newly observable external state without rewriting CP-016's historically correct blocked conclusion.
history_preserved:
  - CP-016 remains the authoritative record that exact fetch returned 128 and the local submodule gate was closed at that checkpoint.
  - EXP-003 through EXP-006 remain INVALID, non-counting, and unchanged.
observed:
  - OBSERVED: Parent HEAD is 371992e6e5e8b259f0019548d4e54f764ff3d335 on codex/rgbd-perception-pick-place and the superproject is clean before this ledger correction.
  - OBSERVED: `git ls-tree HEAD third_party/mujoco_ros2_control` and task-worktree submodule HEAD both equal f19a8cc3af61feccacb22a9f0d16cc972e3b2c08.
  - OBSERVED: Task-worktree submodule describe is exactly so101-0.0.3-r8-3-gf19a8cc and its status is clean.
  - OBSERVED: Gitee branch codex/rgbd-camera-plugin-r8 advertises exact f19a8cc3af61feccacb22a9f0d16cc972e3b2c08.
  - OBSERVED: Canonical main remains clean at b3770360b26fe8f6fac0e19338d250b6f5cab0e7 with gitlink and submodule HEAD 738e304551b4ea6db020b466086a13db71b65607 (so101-0.0.3-r6); it was not modified.
  - OBSERVED: No conflicting MuJoCo, MoveIt, controller, static-TF, rgbd_cup_pose, or dynamic_cup_pick_place runtime was present in the read-only recovery probe; existing tmux sessions were not operated.
effective_exp007_provenance:
  source_commit: 371992e6e5e8b259f0019548d4e54f764ff3d335
  implementation_commit: 12c0d69252f8b84ad1335877192bf23b22947c52
  submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
  install_overlay: /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/install
  runtime_executable: /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/install/so101_demo_py/lib/so101_demo_py/rgbd_cup_pose
  ros_domain_id: 185
  gz_partition: rgbd-perception-ai-station-exp007-20260826
effective_precondition_correction:
  - EXP-007's original exact-parent precondition is superseded only for the ledger-only checkpoint commit: parent HEAD is 371992e6, whose runtime implementation is unchanged from 12c0d692, and only this ledger may become tracked dirty before the RUNNING transition.
  - EXP-007's original submodule-fetch command is satisfied by the orchestrator update plus this independent read-only verification. Do not repeat the historical failing exact-fetch route; continue with clean gate assertions and the fresh build/install overlay.
decision: EXP-007 remains PLANNED and may proceed to fresh-overlay build/test provenance; it has not transitioned to RUNNING and no stack, GUI action, dynamic workflow, or motion has started.
```

```yaml
checkpoint_id: CP-017
last_valid_experiment: EXP-002
current_hypothesis: With CP-016's external submodule blocker removed and exact f19a8cc provenance independently verified, EXP-007 can now distinguish ai-station fresh-overlay perception behavior from the prior invalid Mac environment runs without starting dynamic workflow or robot motion.
working_tree_status: Before this correction the task superproject and f19a8cc submodule were clean at parent 371992e6; only docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md is now intentionally tracked dirty.
owned_processes: NONE; no stack, Viewer action, controller, static TF, perception, dynamic workflow, or robot motion has started.
preserved_processes: Existing sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui were listed only and were not sent input, stopped, or modified. Canonical main remains untouched.
confirmed_conclusions:
  - CORR-CP-016-001 removes only CP-016's current external-state blocker; it does not change CP-016's historical result or any EXP-003 through EXP-006 status.
  - Parent gitlink, task submodule HEAD, describe, cleanliness, and Gitee branch ref now satisfy the f19a8cc hard gate.
  - EXP-007 remains the next experiment and provides new host/OS/fresh-overlay information; historical failed fetch and contaminated Mac attempts must not be repeated.
disproven_routes:
  - Canonical r6 remains prohibited and is not a fallback build/runtime source.
  - Gitee availability alone does not prove installed runtime provenance; fresh overlay build and installed-prefix/readback gates remain mandatory.
open_risks:
  - ai-station package dependencies, full package tests, installed r8 runtime provenance, and perception-only acceptance remain unverified.
  - GUI/CUA instructions must be loaded before the first Viewer action.
  - Four independent FULL_RESTART physical runs remain gated on an independently reviewed VALID EXP-007.
next_command: source /opt/ros/jazzy/setup.zsh and build the required dependency closure plus so101_demo_py with build/install/log bases only under /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/
```

```yaml
checkpoint_id: CP-018
recorded_at: 2026-08-26T10:08:28+08:00
last_valid_experiment: EXP-002
next_experiment: EXP-007
experiment_state: PLANNED
current_hypothesis: Exact f19a8cc CameraPlugin plus the fresh Linux overlay can produce a real aligned RGB-D cup pose within 0.01 m of MuJoCo truth without starting dynamic_cup_pick_place or commanding robot motion.
working_tree_status: Branch codex/rgbd-perception-pick-place is clean at 919f7faa619c887f5c05df579b2ac17c545b77fe before this ledger-only checkpoint; the f19a8cc submodule is clean.
owned_processes: NONE; build, test, package inspection, Open3D installation, and smoke tests started no ROS stack, Viewer action, dynamic workflow, or robot motion.
preserved_processes: Existing tmux sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui were not sent input, stopped, or modified. Canonical main and its r6 submodule remain untouched.
observed:
  - OBSERVED: The first fresh-overlay build failed at the so101_mujoco_support consumer boundary because f19a8cc exports OpenGL::EGL and OpenGL::OpenGL in its plugin target without exporting the OpenGL dependency; the retained RED log is exp-007/tests/colcon-build-fresh.log.
  - OBSERVED: Commit 919f7faa adds the minimal non-Apple consumer-side OpenGL discovery before importing the locked plugin target; an exact-commit rebuild finished all five selected packages with exit 0.
  - OBSERVED: The first full pytest invocation was invalid as a test environment because it replaced ROS PYTHONPATH and produced 35 import collection errors; after sourcing /opt/ros/jazzy then the fresh overlay without replacing PYTHONPATH, five remaining failures were isolated to a test fixture's hard-coded historical Mac evidence path.
  - OBSERVED: Commit 919f7faa makes only those five lifecycle test invocations use pytest tmp_path while preserving production evidence fail-closed behavior; the focused file passed 34 tests and the exact-commit full package suite passed 369 tests in 4.45 seconds.
  - OBSERVED: Task-owned Open3D 0.19.0 with NumPy 1.26.4 was installed below ai-station-overlay/python-deps; import and a three-point DBSCAN smoke test passed. The interrupted slow pip attempt is retained with exit 130, and the successful uv installation is retained with exit 0.
  - OBSERVED: gitlink and submodule HEAD both equal f19a8cc3af61feccacb22a9f0d16cc972e3b2c08, describe is so101-0.0.3-r8-3-gf19a8cc, and the submodule is clean.
  - OBSERVED: mujoco_ros2_control_msgs, mujoco_ros2_control_plugins, mujoco_ros2_control, so101_mujoco_support, and so101_demo_py all resolve below the fresh task-owned install overlay; only upstream mujoco_vendor resolves to /opt/ros/jazzy.
  - OBSERVED: The installed ros2_control_node resolves to the task-owned build binary, and ldd resolves task-built MuJoCo message libraries from the task overlay plus upstream MuJoCo 3.4.0 from /opt/ros/jazzy; no canonical r6 build/install path appears in the retained provenance readback.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/tests/colcon-build-fresh.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/tests/colcon-build-green.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/tests/colcon-build-exact-919f7faa.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/tests/pytest-perception-launch-fixture-fix.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/tests/pytest-full-exact-919f7faa.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/tests/uv-open3d-task-owned.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/tests/open3d-smoke.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/tests/fresh-overlay-provenance.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/tests/fresh-overlay-ldd.log
confirmed_conclusions:
  - CP-016 and CORR-CP-016-001 remain unchanged historical records; the former was correctly blocked at that time and the latter records the external publication correction.
  - Fresh Linux build, full package regression, Open3D runtime dependency, exact f19 source identity, and installed runtime provenance gates are closed without using r6.
  - EXP-007 has not transitioned to RUNNING; perception-only runtime, aligned sample, truth error, Viewer action, and exact-owned cleanup remain unverified.
open_risks:
  - ROS domain 185, GZ partition rgbd-perception-ai-station-exp007-20260826, process ownership, and GUI state must be freshly audited immediately before RUNNING.
  - Camera topics, segmentation/fit, exact-stamp TF, sole /cup_pose publisher, truth error, and causal Viewer screenshot remain runtime gates.
  - Four independent FULL_RESTART physical runs remain prohibited until EXP-007 is VALID and independently reviewed.
decision: EXP-007 may proceed to its immediate pre-RUNNING isolation snapshot using only the task-owned overlay and Python dependency path. No dynamic workflow or motion is authorized in EXP-007.
next_command: Capture and retain the exact ROS_DOMAIN_ID=185 graph, GZ_PARTITION, targeted process set, tmux list, git/submodule/install provenance, and owned launch command immediately before changing EXP-007 from PLANNED to RUNNING.
```

```yaml
transition_id: TRANS-EXP-007-RUNNING-001
recorded_at: 2026-08-26T10:11:57+08:00
experiment_id: EXP-007
from: PLANNED
to: RUNNING
lifecycle: ISOLATED_STACK
host: AI-STATION-001
source_commit: e4a39923b1e3146f0c601baf6ec0b6de07cafebc
implementation_commit: 919f7faa619c887f5c05df579b2ac17c545b77fe
submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
submodule_describe: so101-0.0.3-r8-3-gf19a8cc
install_overlay: /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/install
python_dependencies: /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/python-deps
ros_domain_id: 185
gz_partition: rgbd-perception-ai-station-exp007-20260826
session_id: rgbd-perception-ai-station-exp007-20260826
owned_tmux_session: rgbd-exp007-20260826
immediate_pre_running_observed:
  - OBSERVED: ROS_DOMAIN_ID 185 returned no nodes with --no-daemon; only built-in /parameter_events and /rosout topics were listed.
  - OBSERVED: The targeted simulator, controller, MoveIt, static-TF, rgbd_cup_pose, dynamic workflow, and RViz process set was empty after excluding the probe shell itself.
  - OBSERVED: No current-user process owned GZ_PARTITION rgbd-perception-ai-station-exp007-20260826.
  - OBSERVED: Parent worktree and exact f19a8cc submodule were clean, fresh overlay package prefixes were re-read, and existing tmux sessions were listed only.
  - OBSERVED: The first partition scan attempted unreadable /proc environments and produced permission noise but changed no state; isolation-snapshot-v2.log is the authoritative clean readback.
  - OBSERVED: cua-driver health is overall ok on local X11 DISPLAY=:1 with AT-SPI and screen capture available; no GUI action has occurred yet.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/pre-running/isolation-snapshot.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/pre-running/isolation-snapshot-v2.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/gui/cua-driver-probe.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/gui/cua-driver-health.log
runtime_scope:
  - Start only so101_mujoco.launch.py with task_start, the two approved static TF publishers, passive one-shot observers, and production rgbd_cup_pose.
  - Do not start dynamic_cup_pick_place, fixed_cup_pick_place, cup_pose_tf_demo, or mujoco_cup_pose_bridge; command no robot motion.
  - Capture one causally attributable Viewer baseline, camera-view-only action, and fresh post-action screenshot using snapshot-action-fresh.
  - Stop only processes owned by tmux session rgbd-exp007-20260826 and prove the final targeted process set plus domain 185 are empty.
next_command: Create exact-owned tmux session rgbd-exp007-20260826 and start its stack window from /opt/ros/jazzy plus the fresh task overlay with ROS_DOMAIN_ID=185, GZ_PARTITION=rgbd-perception-ai-station-exp007-20260826, headless=false, task_start, and the registered EXP-007 evidence paths.
```

```yaml
closure_id: CLOSE-EXP-007-001
recorded_at: 2026-08-26T10:16:24+08:00
experiment_id: EXP-007
status: INVALID
classification: environment_invalid_non_counting
first_bad_boundary:
  process: fresh-overlay mujoco_ros2_control/ros2_control_node
  child_exit_code: 1
  message: "ERROR: could not create window"
observed:
  - OBSERVED: Exact f19 hardware plugin loaded and reached MuJoCo simulation initialization, then the required ros2_control_node exited 1 before controller activation, static TF, rgbd_cup_pose, Viewer action, dynamic workflow, or robot motion.
  - OBSERVED: A same-display minimal hidden GLFW probe reproduced the failure with GLX error 65543, `Failed to create context: BadValue`, independent of ROS and SO-101.
  - OBSERVED: nvidia-smi failed with `Driver/library version mismatch` and reported user-space NVML 595.84; DISPLAY :1 still advertised GLX/NV-GLX and remained reachable for X11 capture.
  - OBSERVED: A single-variable minimal probe with __GLX_VENDOR_LIBRARY_NAME=mesa and LIBGL_ALWAYS_SOFTWARE=1 successfully created a hidden GLFW context on DISPLAY :1.
  - OBSERVED: ros2 launch itself returned 0 after required-child shutdown, but its retained child record is authoritative for the ros2_control_node exit 1.
  - OBSERVED: The owned tmux session ended, ROS_DOMAIN_ID 185 and the targeted process set were empty, and the generated MUJOCO_LOG.TXT was retained as exp-007/run/MUJOCO_LOG-attempt-1.TXT rather than deleted.
not_started:
  - approved static TF publishers
  - production rgbd_cup_pose
  - Viewer baseline/action/fresh sequence
  - dynamic_cup_pick_place
  - robot motion
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/run/stack-attempt-1.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/run/MUJOCO_LOG-attempt-1.TXT
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/run/glfw-hidden-smoke.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/run/glx-system-context.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/run/glfw-mesa-hidden-smoke.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-007/run/post-attempt-1-cleanup.log
conclusion: EXP-007 is strict INVALID due a host GLX/NVIDIA environment mismatch before the perception boundary; it is neither a perception product failure nor a pass and must not be retried in place.
decision: Preserve EXP-007 and plan EXP-008 as a new isolated perception-only run whose sole environment change is Mesa software GLX selection.
next_experiment: EXP-008
```

```yaml
experiment_id: EXP-008
status: PLANNED
prior_experiment: EXP-007
hypothesis: Selecting Mesa software GLX avoids the independently reproduced NVIDIA GLX context failure while exact f19a8cc CameraPlugin still produces real aligned RGB-D and a valid production world /cup_pose.
prediction: The fresh interactive stack creates a visible MuJoCo Viewer, publishes one aligned 640x480 rgb8/32FC1 task_camera_frame triple with finite positive depth, and production rgbd_cup_pose localizes task_start within 0.01 m of MuJoCo truth without workflow or motion.
single_variable: Add __GLX_VENDOR_LIBRARY_NAME=mesa and LIBGL_ALWAYS_SOFTWARE=1 to every owned MuJoCo stack process environment; source, overlay, f19 submodule, keyframe, perception configuration, and acceptance criteria are unchanged.
lifecycle: ISOLATED_STACK
preconditions:
  - Parent source is a clean descendant of a564f2d0 with implementation commit 919f7faa; gitlink/submodule remain exact clean f19a8cc with describe so101-0.0.3-r8-3-gf19a8cc.
  - Fresh task-owned overlay package prefixes and Open3D dependency path are unchanged from CP-018; canonical r6 is neither sourced nor reused.
  - ROS_DOMAIN_ID 186 and GZ_PARTITION rgbd-perception-ai-station-exp008-20260826 are empty immediately before RUNNING.
  - dynamic_cup_pick_place, fixed_cup_pick_place, cup_pose_tf_demo, and mujoco_cup_pose_bridge are prohibited; no robot motion is commanded.
success_criteria:
  - Real CameraInfo, color, and depth form one exact-stamp 640x480 task_camera_frame triple with rgb8 and 32FC1 encodings and finite positive depth.
  - Production rgbd_cup_pose is the sole fresh /cup_pose publisher, writes a nonempty selected PLY and JSON receipt with an accepted fitted radius, and retains the aligned source stamp.
  - world to task_camera_frame TF succeeds at the source stamp and the finite world /cup_pose differs from current MuJoCo cup truth by at most 0.01 m.
  - A causally attributable MuJoCo Viewer baseline, camera-view-only action, and fresh screenshot are retained and actually inspected.
  - Only exact-owned processes are stopped; the final targeted process set and ROS domain are empty with complete exit evidence.
failure_criteria:
  - With all preconditions satisfied, any camera, segmentation, fit, TF, publisher, freshness, truth-error, visual, or cleanup product gate fails.
invalid_criteria:
  - Exact f19/fresh-overlay provenance fails, domain/partition/process isolation is contaminated, unowned state is reused or modified, Viewer remains unavailable due host rendering, or any prohibited workflow/motion process starts.
provenance:
  source_commit: PENDING_LEDGER_COMMIT
  implementation_commit: 919f7faa619c887f5c05df579b2ac17c545b77fe
  submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
  install_overlay: /tmp/so101-debug-rgbd-perception-pick-place-20260826/ai-station-overlay/install
  ros_domain_id: 186
  gz_partition: rgbd-perception-ai-station-exp008-20260826
  session_id: rgbd-perception-ai-station-exp008-20260826
  owned_tmux_session: rgbd-exp008-20260826
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-008/
decision: PENDING
next_experiment: NONE
```

```yaml
checkpoint_id: CP-019
recorded_at: 2026-08-26T10:16:24+08:00
last_valid_experiment: EXP-002
current_hypothesis: EXP-008 can isolate the proven GLX vendor change from perception behavior while retaining exact f19 and fresh-overlay provenance.
working_tree_status: The task worktree and submodule are clean before this ledger-only closure/plan update; runtime MUJOCO_LOG.TXT was moved intact into registered EXP-007 evidence.
owned_processes: NONE; EXP-007 owned tmux ended and its ROS domain plus targeted process set are empty.
preserved_processes: Existing tmux sessions and canonical main were not operated or modified.
confirmed_conclusions:
  - EXP-007 is environment-invalid before perception and non-counting; no production or physical conclusion is drawn from it.
  - The NVIDIA GLX failure is independently reproducible, while Mesa software GLX can create a same-display GLFW context.
  - EXP-008 is the only next route; EXP-007 evidence is retained and must not be overwritten.
open_risks:
  - A minimal Mesa GLFW success does not yet prove the full Viewer plus CameraPlugin rendering path.
  - All numeric, publisher, TF, truth-error, GUI, and cleanup gates remain open.
  - Four FULL_RESTART physical runs remain prohibited.
next_command: Create /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-008, then capture a fresh domain 186, partition, process, tmux, git/submodule, prefix, and driver isolation snapshot before transitioning EXP-008 to RUNNING.
```

```yaml
transition_id: TRANS-EXP-008-RUNNING-001
recorded_at: 2026-08-26T10:18:13+08:00
experiment_id: EXP-008
from: PLANNED
to: RUNNING
source_commit: fc16504dd43b0bf591624da0b6c3a6d27d8f0b3d
implementation_commit: 919f7faa619c887f5c05df579b2ac17c545b77fe
submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
ros_domain_id: 186
gz_partition: rgbd-perception-ai-station-exp008-20260826
session_id: rgbd-perception-ai-station-exp008-20260826
owned_tmux_session: rgbd-exp008-20260826
environment_delta:
  __GLX_VENDOR_LIBRARY_NAME: mesa
  LIBGL_ALWAYS_SOFTWARE: "1"
immediate_pre_running_observed:
  - OBSERVED: Parent and f19 submodule are clean; gitlink/HEAD/describe are exact; all four task packages resolve to the fresh task overlay.
  - OBSERVED: ROS_DOMAIN_ID 186 has no nodes, the targeted process set is empty, no current-user process owns the EXP-008 GZ partition, and the exact-owned tmux name is absent.
  - OBSERVED: The prerequisite Mesa hidden-GLFW probe exit is 0; no EXP-008 stack or GUI action has yet started.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-008/pre-running/isolation-snapshot.log
runtime_scope:
  - Start only the base stack, approved static TF, passive observers, and production rgbd_cup_pose.
  - Prohibit every pick-place workflow, truth bridge, and robot motion command.
  - Use cua-driver session rgbd-exp008-viewer-20260826 with snapshot-action-fresh for the Viewer gate.
next_command: Start exact-owned tmux rgbd-exp008-20260826 stack with the frozen Mesa environment and retain all child exits before starting any static TF or perception process.
```

```yaml
closure_id: CLOSE-EXP-008-001
recorded_at: 2026-08-26T10:27:48+08:00
experiment_id: EXP-008
status: INVALID
classification: audit_invalid_non_counting
product_observations:
  - OBSERVED: Mesa software GLX started a visible owned MuJoCo Viewer; exact f19 CameraPlugin initialized its GLFW renderer and 640x480 offscreen buffer; all three controllers and Planning Scene passed readiness.
  - OBSERVED: An independently retained exact-stamp RGB-D triple at stamp 180552000000 is task_camera_frame 640x480 with rgb8/32FC1, correct packed strides and byte counts, and 307200 finite positive depth values.
  - OBSERVED: Production rgbd_cup_pose was the sole /cup_pose publisher, selected 141 cup points, fitted radius 0.03938151231973142 m, wrote a 4013-byte PLY plus JSON, and published world [0.01950111783349788, -0.28040476095521005, 0.165] with source stamp 122651999999.
  - OBSERVED: Exact-source-stamp world<-task_camera_frame lookup succeeded at translation [0.65, -0.65, 0.55]; current MuJoCo plastic_cup truth was [0.02, -0.28, 0.16480156647042168], giving 0.0006723769125849648 m 3D error.
  - OBSERVED: CUA baseline and pre-action screenshots showed the active canonical scene; top_down action read back successfully but visually occluded the cup; the subsequent table_corner_ne camera-only action read back successfully and its fresh inspected screenshot visibly showed the orange cup, red target, robot, table, and Running status.
  - OBSERVED: No dynamic/fixed workflow, truth bridge, or robot motion process started.
audit_failure:
  - OBSERVED: Sending terminal C-c to the owned helper panes terminated each wrapper shell together with its foreground child, so perception.exit, tf-base.exit, tf-optical.exit, and stack.exit were never durably written.
  - OBSERVED: The owned tmux session, every recorded wrapper PID, domain 186, targeted process set, Viewer window, and CUA session were all absent after cleanup; post-cleanup.log exited 0.
  - INFERRED: Cleanup occurred, but the frozen complete-exit-sidecar criterion cannot be reconstructed from absence alone and must not be waived retrospectively.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-008/rgbd-sample.json
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-008/point-cloud.json
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-008/perception.json
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-008/truth-tf.json
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-008/cup.ply
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-008/gui/viewer-pre-action.png
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-008/gui/viewer-post-action.png
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-008/gui/viewer-post-action-2.png
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-008/run/numeric-gates.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-008/run/post-cleanup.log
conclusion: EXP-008 is strict audit INVALID and non-counting despite passing every observed perception and visual product boundary; missing frozen exit sidecars prevent VALID status.
decision: Preserve all evidence and plan EXP-009 with identical product/runtime variables plus a prevalidated exact child PID/PGID cleanup protocol.
next_experiment: EXP-009
```

```yaml
experiment_id: EXP-009
status: PLANNED
prior_experiment: EXP-008
hypothesis: With the same exact f19 fresh-overlay Mesa runtime, an exact child-process-group wrapper can reproduce EXP-008's perception/visual gates while retaining complete real exit sidecars and exact-owned cleanup proof.
prediction: All EXP-008 product values remain within their frozen tolerances and each helper plus stack writes a real exit sidecar after only its recorded child PGID receives SIGINT.
single_variable: Replace terminal C-c cleanup with prevalidated wrappers that launch each runtime in a recorded setsid child, wait in the parent, and are stopped by exact recorded child PGID; all product, source, overlay, Mesa, keyframe, and perception settings remain fixed.
lifecycle: ISOLATED_STACK
preconditions:
  - Exact f19 and fresh overlay provenance remain clean and unchanged; Mesa software GLX hidden-window smoke remains exit 0.
  - The wrapper lifecycle is validated on a harmless task-owned process before any stack command.
  - ROS_DOMAIN_ID 187, GZ_PARTITION rgbd-perception-ai-station-exp009-20260826, targeted process set, and owned tmux name are empty immediately before RUNNING.
  - No workflow, truth bridge, or motion command is allowed.
success_criteria:
  - All EXP-008 RGB-D, point-cloud, sole publisher, radius, exact-stamp TF, <=0.01 m truth error, and fresh inspected Viewer gates pass on new EXP-009 evidence.
  - Each runtime wrapper retains its exact child PID/PGID and genuine exit sidecar; post-cleanup domain, process, Viewer, CUA, and owned tmux sets are empty.
failure_criteria:
  - With preconditions satisfied, any perception, truth, visual, or cleanup product gate fails.
invalid_criteria:
  - Isolation/provenance is contaminated, wrapper validation fails, any exit is unauditable, Viewer environment fails, or prohibited workflow/motion starts.
provenance:
  source_commit: PENDING_LEDGER_COMMIT
  implementation_commit: 919f7faa619c887f5c05df579b2ac17c545b77fe
  submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
  ros_domain_id: 187
  gz_partition: rgbd-perception-ai-station-exp009-20260826
  session_id: rgbd-perception-ai-station-exp009-20260826
  owned_tmux_session: rgbd-exp009-20260826
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-009/
decision: PENDING
next_experiment: NONE
```

```yaml
checkpoint_id: CP-020
recorded_at: 2026-08-26T10:27:48+08:00
last_valid_experiment: EXP-002
current_hypothesis: EXP-009 can convert the now-proven perception chain into a countable gate by changing only the cleanup ownership protocol.
working_tree_status: Task worktree and f19 submodule are clean before this ledger-only update; EXP-008 runtime artifacts exist only below the registered evidence root.
owned_processes: NONE; domain 186, target set, Viewer, CUA session, and owned tmux are empty.
preserved_processes: Existing tmux sessions and canonical main were not operated or modified.
confirmed_conclusions:
  - EXP-008 strongly supports the perception hypothesis but remains non-counting audit INVALID.
  - Product settings must not be tuned for EXP-009; only process ownership/exit capture changes.
  - Four FULL_RESTART runs remain prohibited until a VALID perception-only experiment is independently reviewed.
next_command: Build and pass a harmless exact-child-PGID wrapper lifecycle test below exp-009/pre-running, then perform fresh domain 187 and process isolation before the RUNNING transition.
```

```yaml
transition_id: TRANS-EXP-009-RUNNING-001
recorded_at: 2026-08-26T10:30:02+08:00
experiment_id: EXP-009
from: PLANNED
to: RUNNING
source_commit: 143c4e7ecfea13b54a58faa7ec8ae8130842da1d
implementation_commit: 919f7faa619c887f5c05df579b2ac17c545b77fe
submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
ros_domain_id: 187
gz_partition: rgbd-perception-ai-station-exp009-20260826
session_id: rgbd-perception-ai-station-exp009-20260826
owned_tmux_session: rgbd-exp009-20260826
environment:
  __GLX_VENDOR_LIBRARY_NAME: mesa
  LIBGL_ALWAYS_SOFTWARE: "1"
immediate_pre_running_observed:
  - OBSERVED: Harmless setsid wrapper smoke recorded wrapper PID, exact child PID=PGID, delivered SIGINT only to that child group, wrote genuine exit 0, and left no child.
  - OBSERVED: Parent/f19 source is exact and clean; fresh package prefixes are unchanged; domain 187, targeted processes, EXP-009 partition owners, and owned tmux name are empty.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-009/pre-running/wrapper-smoke.signal.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-009/pre-running/isolation-snapshot.log
next_command: Start the exact-child-PGID EXP-009 stack wrapper; only after stack/camera/scene readiness start approved TF, pre-start pose observer, and production perception wrappers using the same ownership protocol.
```

```yaml
closure_id: CLOSE-EXP-009-001
recorded_at: 2026-08-26T10:39:19+08:00
experiment_id: EXP-009
status: INVALID
classification: audit_invalid_non_counting
product_observations:
  - OBSERVED: Exact f19 and the fresh five-package overlay remained clean; Mesa software GLX started a fresh visible Viewer, CameraPlugin initialized its 640x480 offscreen renderer, controllers and Planning Scene passed readiness, and no workflow, truth bridge, or robot-motion process started.
  - OBSERVED: Before production start, /cup_pose had zero publishers and one waiting observer; afterward rgbd_cup_pose was its sole publisher.
  - OBSERVED: The retained exact-stamp RGB-D triple is task_camera_frame 640x480 rgb8/32FC1 with packed byte counts and all 307200 depth values finite and positive.
  - OBSERVED: Production selected 141 cup points, fitted radius 0.03938151231973142 m, wrote a 4013-byte PLY, and published world [0.01950111783349788, -0.28040476095521005, 0.165]. The independent point-cloud path also selected 141 points and wrote an identical-hash 4013-byte PLY.
  - OBSERVED: Exact-source-stamp world<-task_camera_frame lookup succeeded at translation [0.65, -0.65, 0.55]; MuJoCo plastic_cup truth was [0.02, -0.28, 0.16480156647042168], giving 0.0006723769125849648 m 3D error and passing the 0.01 m gate.
  - OBSERVED: Fresh CUA baseline and post-table_corner_ne screenshots have different hashes; the inspected post-action image visibly contains the orange cup, red target, robot, table, and Running status, while camera_preset readback reported success and matched=true.
audit_failure:
  - OBSERVED: Exact recorded child-PGID SIGINT produced genuine exits observer=0, tf-base=0, tf-optical=0, stack=0, but perception=1.
  - OBSERVED: The perception tail identifies a shutdown race: after prior successful publications, SIGINT invalidated the ROS context during a final publisher call, which raised `Failed to publish: publisher's context is invalid`; the existing runtime classified that RuntimeError as RGBD_CUP_POSE_FATAL.
  - OBSERVED: Post-cleanup domain 187, every recorded child PID, owned tmux, targeted Python process set, Viewer window, and CUA session are empty.
  - INFERRED: This is a production shutdown-classification defect, not a perception or isolation failure, but the frozen all-zero auditable-exit criterion cannot be waived.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-009/perception.json
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-009/rgbd-sample.json
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-009/truth-tf.json
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-009/point-cloud.json
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-009/cup.ply
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-009/cup-independent.ply
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-009/gui/viewer-baseline.png
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-009/gui/viewer-after-table-corner-ne.png
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-009/run/perception.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-009/run/post-cleanup.log
conclusion: EXP-009 is strict audit INVALID and non-counting despite passing every perception, truth, topology, and visual product gate; its genuine perception exit 1 proves an orderly-shutdown race that must be corrected and rerun rather than normalized in evidence.
decision: Preserve all EXP-009 evidence and plan EXP-010 with one production variable: shutdown-aware RuntimeError classification after a first valid publication.
next_experiment: EXP-010
```

```yaml
experiment_id: EXP-010
status: PLANNED
prior_experiment: EXP-009
hypothesis: If rgbd_cup_pose observes a RuntimeError only after at least one valid publication and the ROS runtime is already not-ok, classifying that exception as orderly context shutdown will preserve real failures while allowing exact PGID SIGINT to exit 0.
prediction: A focused regression test fails on the current implementation and passes after the minimal branch; a fresh exact-f19 overlay rebuild and full package suite pass; a new isolated perception run reproduces every EXP-009 product gate and records all helper plus stack exits as 0.
single_variable: In run_rgbd_cup_pose's runtime-error handler only, distinguish post-success context shutdown (`first_valid_published` and `not runtime.ok()`) from a RuntimeError while context remains live; do not change perception, TF, camera, Mesa, scene, keyframe, or lifecycle settings.
lifecycle: ISOLATED_STACK
preconditions:
  - Explicit approval of the bounded design is received before implementation, as required by the brainstorming workflow.
  - Add and observe a focused RED test before changing production code, then run focused and full package verification and rebuild the same fresh overlay.
  - Use a new ROS domain, partition, session id, owned tmux, and exp-010 evidence directory; retain EXP-009 unchanged.
success_criteria:
  - All EXP-009 product gates pass on fresh evidence and exact child-PGID cleanup writes observer=0, TF helpers=0, perception=0, and stack=0.
  - Post-cleanup domain, process, Viewer, CUA, and owned tmux sets are empty.
failure_criteria:
  - The focused fix does not make the live SIGINT path exit 0, or any product gate fails with valid isolation/provenance.
invalid_criteria:
  - Approval/TDD/provenance/isolation evidence is incomplete, prohibited workflow or motion starts, or any exit remains unauditable.
provenance:
  source_commit: PENDING
  implementation_commit: PENDING
  submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
  ros_domain_id: 188
  gz_partition: rgbd-perception-ai-station-exp010-20260826
  session_id: rgbd-perception-ai-station-exp010-20260826
  owned_tmux_session: rgbd-exp010-20260826
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010/
decision: PENDING_APPROVAL
next_experiment: NONE
```

```yaml
checkpoint_id: CP-021
recorded_at: 2026-08-26T10:39:19+08:00
last_valid_experiment: EXP-002
current_hypothesis: A minimal shutdown-aware error classification can convert the fully passing EXP-009 perception product into an auditable all-zero lifecycle on a fresh EXP-010 rerun.
working_tree_status: Parent task worktree and exact f19 submodule were clean before this ledger append; runtime artifacts remain only below the registered /tmp evidence root.
owned_processes: NONE; domain 187, all recorded child PIDs, owned tmux, Viewer, CUA session, and targeted process set are empty.
preserved_processes: Existing unrelated tmux sessions and canonical main at b3770360b26fe8f6fac0e19338d250b6f5cab0e7 were not operated or modified.
confirmed_conclusions:
  - EXP-009 independently reconfirms the RGB-D/perception/truth/visual product chain but is non-counting because perception genuinely exited 1.
  - The failure is localized to post-success ROS-context shutdown classification; normal live-context RuntimeError behavior must remain fatal.
  - Four FULL_RESTART runs remain prohibited until a VALID perception-only experiment is independently reviewed.
next_command: Await explicit approval of the bounded two-branch design, then begin EXP-010 with a focused RED regression test.
```

```yaml
transition_id: TRANS-EXP-010-RUNNING-001
recorded_at: 2026-08-26T11:27:53+08:00
experiment_id: EXP-010
from: PLANNED
to: RUNNING
approval: User explicitly approved the bounded shutdown-classification design.
source_commit: 9854a62f2698b361c5545a138e05f3d22fa8cc39
implementation_commit: 9854a62f2698b361c5545a138e05f3d22fa8cc39
submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
ros_domain_id: 188
gz_partition: rgbd-perception-ai-station-exp010-20260826
session_id: rgbd-perception-ai-station-exp010-20260826
owned_tmux_session: rgbd-exp010-20260826
environment:
  __GLX_VENDOR_LIBRARY_NAME: mesa
  LIBGL_ALWAYS_SOFTWARE: "1"
pre_running_observed:
  - OBSERVED: The focused RED test failed exactly because current result was 1 rather than expected orderly 0; its companion live-context RuntimeError protection test passed.
  - OBSERVED: After the minimal production branch, both focused tests passed, the full so101_demo_py suite passed 371 tests, Ruff lint passed, and the exact five-package fresh overlay rebuild exited 0.
  - OBSERVED: The package's pre-existing full-file Ruff format baseline remains nonzero on both HEAD versions; no bulk reformat was performed and git diff --check passed.
  - OBSERVED: Harmless exact-child wrapper smoke again wrote genuine exit 0 and left no child; Mesa ctypes GLFW smoke created and destroyed a hidden window with exit 0.
  - OBSERVED: The first isolation scanner self-matched its own command and is retained as invalid diagnostic evidence; corrected scanner explicitly excluded its own PID and found domain 188, target process set, partition owners, and owned tmux empty.
  - OBSERVED: Parent and exact f19 submodule are clean, canonical main remains clean at b3770360b26fe8f6fac0e19338d250b6f5cab0e7, and all five package prefixes resolve only into the fresh task overlay.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010-tdd-red-correct-env.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010-tdd-green-focused.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010-pytest-full.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010-overlay-rebuild.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010/pre-running/wrapper-smoke.signal.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010/pre-running/glfw-mesa-ctypes-hidden-smoke.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010/pre-running/isolation-snapshot.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010/pre-running/isolation-snapshot-corrected.log
next_command: Start the exact child-PGID EXP-010 stack and reproduce the frozen perception-only numeric, topology, truth, visual, and all-zero cleanup gates without workflow or robot motion.
```

```yaml
closure_id: CLOSE-EXP-010-001
recorded_at: 2026-08-26T11:36:00+08:00
experiment_id: EXP-010
status: VALID
classification: accepted_perception_only_gate
runtime_source_commit: 0e1d3cbe4b93f1b4312d393b784d35fd1cf4c117
implementation_commit: 9854a62f2698b361c5545a138e05f3d22fa8cc39
submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
observed:
  - OBSERVED: Exact f19 CameraPlugin and the fresh five-package overlay produced an exact-stamp 640x480 task_camera_frame rgb8/32FC1 triple; all 307200 depth values were finite and positive.
  - OBSERVED: /cup_pose transitioned from zero publishers plus one waiting observer to one sole rgbd_cup_pose publisher. Production selected 141 cup points, fitted radius 0.03938151231973142 m, wrote a 4013-byte PLY, and published world [0.01950111783349788, -0.28040476095521005, 0.165].
  - OBSERVED: The independent point-cloud path selected 141 points and wrote an identical-hash 4013-byte PLY with vertex count 141.
  - OBSERVED: Exact-source-stamp world<-task_camera_frame lookup succeeded; MuJoCo truth error was 0.0006723769125849648 m and within_0_01_m=true.
  - OBSERVED: Fresh baseline and post-table_corner_ne Viewer images have distinct hashes and were inspected as showing the robot, orange cup, red target, table, and Running status; camera readback was success=true and matched=true.
  - OBSERVED: No workflow, truth bridge, or robot motion started. Genuine exits were perception=0, tf-base=0, tf-optical=0, observer=0, stack=0, RGB-D receipt=0, point cloud=0, and truth-TF=0.
  - OBSERVED: Corrected post-cleanup proof found domain 188 empty, every recorded child absent, owned tmux absent, target process count zero, Viewer absent, and CUA ended.
measurement_corrections:
  - The initial GLFW probe lacking the optional Python glfw binding is retained; the equivalent ctypes probe against libglfw created and destroyed the hidden Mesa window with exit 0.
  - The first isolation and post-cleanup scanners each matched their own zsh command. Their retained corrections exclude only the recorded checker PID and produce empty target sets; no runtime process was hidden.
  - The first direct wrapper attempt failed before child creation because apply_patch did not set executable bits. Domain, process, and tmux readback were empty before the same immutable wrapper was invoked explicitly with zsh.
independent_review:
  reviewer: read-only independent subagent exp010_gate_review
  result: PASS
  blockers: NONE
  conclusion: EXP-010 meets every frozen perception-only VALID criterion; the corrections and raw-observer helper provenance do not invalidate the run.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010/rgbd-sample.json
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010/perception.json
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010/point-cloud.json
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010/truth-tf.json
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010/running-topology.txt
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010/gui/viewer-baseline.png
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010/gui/viewer-after-table-corner-ne.png
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-010/run/post-cleanup-corrected.log
conclusion: The exact-f19 fresh-overlay MuJoCo RGB-D perception chain is accepted on ai-station and independently reviewed; four physical FULL_RESTART runs may now begin.
decision: Freeze EXP-011 through EXP-014 before any full runtime starts.
next_experiment: EXP-011
```

```yaml
experiment_id: EXP-011
status: PLANNED
lifecycle: FULL_RESTART
hypothesis: The accepted RGB-D-driven dynamic workflow completes a physical pick-place from task_start without changing any policy or runtime input other than enabling the production workflow.
single_variable: initial_keyframe=task_start
provenance: {implementation_commit: 9854a62f2698b361c5545a138e05f3d22fa8cc39, submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08, ros_domain_id: 189, gz_partition: rgbd-pick-task-start-exp011-20260826, session_id: rgbd-pick-task-start-exp011-20260826, owned_tmux_session: rgbd-pick-exp011-20260826}
initial_cup_xyz_m: [0.02, -0.28, 0.165]
evidence_root: /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-011/
success_criteria: [fresh CameraPlugin RGB-D and perception summary, sole rgbd_cup_pose input, perception-to-initial-truth error <= 0.01 m, dynamic DONE with complete forward state trace, controller and joint/TCP motion evidence, bilateral physical grasp and lift, MoveIt attach/detach/world readback, stable contact-free carry, released table-supported final cup within policy tolerance, three fresh inspected Viewer frames, natural launch exit 0, exact-owned cleanup empty]
invalid_criteria: [mixed session, duplicate stack, unavailable fresh camera, missing screenshot, wrong overlay or submodule, unauditable exit, environment contamination]
decision: PENDING
```

```yaml
experiment_id: EXP-012
status: PLANNED
lifecycle: FULL_RESTART
hypothesis: With only the named initial keyframe changed, the accepted chain completes the same physical pick-place from cup_test_forward_5cm.
single_variable: initial_keyframe=cup_test_forward_5cm
provenance: {implementation_commit: 9854a62f2698b361c5545a138e05f3d22fa8cc39, submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08, ros_domain_id: 190, gz_partition: rgbd-pick-forward-exp012-20260826, session_id: rgbd-pick-forward-exp012-20260826, owned_tmux_session: rgbd-pick-exp012-20260826}
initial_cup_xyz_m: [0.02, -0.33, 0.165]
evidence_root: /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-012/
success_criteria: SAME_AS_EXP_011
invalid_criteria: SAME_AS_EXP_011
decision: PENDING
```

```yaml
experiment_id: EXP-013
status: PLANNED
lifecycle: FULL_RESTART
hypothesis: With only the named initial keyframe changed, the accepted chain completes the same physical pick-place from cup_test_left_5cm.
single_variable: initial_keyframe=cup_test_left_5cm
provenance: {implementation_commit: 9854a62f2698b361c5545a138e05f3d22fa8cc39, submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08, ros_domain_id: 191, gz_partition: rgbd-pick-left-exp013-20260826, session_id: rgbd-pick-left-exp013-20260826, owned_tmux_session: rgbd-pick-exp013-20260826}
initial_cup_xyz_m: [-0.03, -0.28, 0.165]
evidence_root: /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-013/
success_criteria: SAME_AS_EXP_011
invalid_criteria: SAME_AS_EXP_011
decision: PENDING
```

```yaml
experiment_id: EXP-014
status: PLANNED
lifecycle: FULL_RESTART
hypothesis: With only the named initial keyframe changed, the accepted chain completes the same physical pick-place from cup_test_right_5cm.
single_variable: initial_keyframe=cup_test_right_5cm
provenance: {implementation_commit: 9854a62f2698b361c5545a138e05f3d22fa8cc39, submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08, ros_domain_id: 192, gz_partition: rgbd-pick-right-exp014-20260826, session_id: rgbd-pick-right-exp014-20260826, owned_tmux_session: rgbd-pick-exp014-20260826}
initial_cup_xyz_m: [0.07, -0.28, 0.165]
evidence_root: /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-014/
success_criteria: SAME_AS_EXP_011
invalid_criteria: SAME_AS_EXP_011
decision: PENDING
```

```yaml
checkpoint_id: CP-022
recorded_at: 2026-08-26T11:36:00+08:00
last_valid_experiment: EXP-010
current_hypothesis: The independently accepted perception chain can drive four separate physical FULL_RESTART executions with only the named initial keyframe changing.
working_tree_status: Task worktree and exact f19 submodule are clean before this ledger append; canonical main remains clean at b3770360b26fe8f6fac0e19338d250b6f5cab0e7.
owned_processes: NONE; domain 188, recorded child PIDs, owned tmux, Viewer, CUA, and target process sets are empty.
preserved_processes: Existing unrelated tmux sessions and canonical main were not operated or modified.
next_command: Execute EXP-011 only after a fresh immediate domain 189, partition, process, tmux, Viewer, source, submodule, and overlay isolation snapshot.
```

```yaml
transition_id: TRANS-EXP-011-RUNNING-001
recorded_at: 2026-08-26T11:44:58+08:00
experiment_id: EXP-011
from: PLANNED
to: RUNNING
runtime_source_commit: e9e27a05e652046d9d35f18139db0e2796b28924
implementation_commit: 9854a62f2698b361c5545a138e05f3d22fa8cc39
pre_running_observed:
  - OBSERVED: Domain 189, exact session/partition target set, partition environment owners, owned tmux, and Viewer set are empty; exact f19, task source, canonical main, and all fresh overlay prefixes are clean and unchanged.
  - OBSERVED: The first scanner encoded a no-match `rg -c` as an empty viewer_count and therefore conservatively exited 1. The retained correction changes only that measurement to `rg | wc -l`, reads viewer_count=0, and exits 0 before any runtime starts.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-011/pre-running/isolation.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-011/pre-running/isolation-corrected.log
next_command: Start exact-owned tmux rgbd-pick-exp011-20260826 with the hardcoded task_start full-restart wrapper, then freeze baseline, transport, and released-final Viewer frames from manifest boundaries.
```

```yaml
closure_id: CLOSE-EXP-011-001
recorded_at: 2026-08-26T11:48:57+08:00
experiment_id: EXP-011
status: INVALID
classification: integration_invalid_non_counting
runtime_source_commit: 359c1bb251b874e5747c06b0562ae1f2c9a7b489
implementation_commit: 9854a62f2698b361c5545a138e05f3d22fa8cc39
submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
first_failure_boundary:
  - OBSERVED: Planning Scene setup completed successfully and launch started exactly one rgbd_cup_pose process plus one dynamic_cup_pick_place process.
  - OBSERVED: dynamic_cup_pick_place immediately exited 2 because argparse rejected launch-injected `--ros-args`; launch then initiated shutdown before the dynamic workflow emitted a manifest or commanded robot motion.
  - OBSERVED: During that shutdown, rgbd_cup_pose also exited 2 because argparse rejected `--ros-args --params-file /tmp/launch_params_eclt9834`; no perception summary, run result, or dynamic manifest was written.
  - OBSERVED: The launch wrapper naturally recorded exit 1. The Viewer window disappeared before the requested baseline state could be captured, so baseline.state.json contains a stale-window error and no baseline PNG exists.
  - OBSERVED: Source inspection finds both affected entrypoints call strict `parse_args(arguments)` directly, while the already launch-safe scene_setup entrypoint uses `rclpy.utilities.remove_ros_args` and has an injected-ROS-arguments regression test.
  - INFERRED: The first product boundary is CLI/launch integration, before perception publication and before any physical pick-place state; no perception or physical-placement conclusion can be drawn.
cleanup:
  - OBSERVED: Exact child PID 466504 is absent, owned tmux is absent, domain 189 has no nodes, no process owns domain 189 or partition rgbd-pick-task-start-exp011-20260826, Viewer is absent, and the CUA session is ended.
  - OBSERVED: No EXP-011 MUJOCO_LOG.TXT exists under the task evidence root or task worktree.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-011/run/full-restart.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-011/run/full-restart.exit
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-011/gui/baseline.state.json
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-011/post-cleanup/isolation-corrected.log
conclusion: EXP-011 is strict INVALID and non-counting because production launch wiring could not pass ROS launch arguments through the two application CLIs and the mandatory baseline screenshot is absent; the run reached neither perception nor physical workflow evaluation.
decision: Preserve EXP-011 unchanged, keep EXP-012 through EXP-014 PLANNED and prohibited, and require an approved TDD fix plus a fresh task_start FULL_RESTART retry before the remaining position runs.
next_experiment: EXP-015
```

```yaml
experiment_id: EXP-015
status: PLANNED
prior_experiment: EXP-011
lifecycle: FULL_RESTART
hypothesis: If both launch-spawned application CLIs remove only ROS-specific arguments before strict application parsing, the unchanged exact-f19 workflow can cross the EXP-011 integration boundary and execute the frozen task_start physical trial.
prediction: Focused tests first reproduce both exit-2 boundaries, then pass after the minimal argument separation while unknown application arguments remain rejected; the full suite, lint, fresh five-package rebuild, and a new isolated task_start runtime all pass their applicable gates.
single_variable: Apply the established scene_setup `rclpy.utilities.remove_ros_args` boundary to rgbd_cup_pose and dynamic_cup_pick_place before their existing argparse parsers; do not use parse_known_args and do not change launch parameters, perception, policy, geometry, keyframe, Mesa, or physical success criteria.
preconditions:
  - Receive explicit approval of this bounded design before implementation.
  - Add focused RED coverage for both launch-injected argument forms and retain strict rejection of an unknown non-ROS application argument.
  - Rebuild the same five-package fresh task-owned overlay from the approved implementation and prove source, exact f19, domain 193, partition, process, tmux, and Viewer isolation immediately before RUNNING.
provenance:
  source_commit: PENDING_APPROVAL
  implementation_commit: PENDING_APPROVAL
  submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
  ros_domain_id: 193
  gz_partition: rgbd-pick-task-start-exp015-20260826
  session_id: rgbd-pick-task-start-exp015-20260826
  owned_tmux_session: rgbd-pick-exp015-20260826
initial_cup_xyz_m: [0.02, -0.28, 0.165]
evidence_root: /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-015/
success_criteria: SAME_AS_EXP_011
failure_criteria: With valid provenance/isolation and successful CLI integration, any frozen perception, physical, manifest, visual, natural-exit, or cleanup product gate fails.
invalid_criteria: Approval/TDD/provenance/isolation is incomplete, ROS arguments still fail before product execution, mandatory visual evidence is missing, or any exit is unauditable.
decision: PENDING_APPROVAL
next_experiment: NONE
```

```yaml
checkpoint_id: CP-023
recorded_at: 2026-08-26T11:48:57+08:00
last_valid_experiment: EXP-010
current_hypothesis: A minimal ROS/application argument separation at the two launch-spawned CLI boundaries can make the frozen full workflow runnable without weakening application argument validation.
working_tree_status: Task worktree and exact f19 submodule were clean before this ledger append; canonical main remains clean at b3770360b26fe8f6fac0e19338d250b6f5cab0e7.
owned_processes: NONE; EXP-011 child, domain 189, partition owners, owned tmux, Viewer, and CUA session are empty.
preserved_processes: Existing unrelated tmux sessions and canonical main were not operated or modified; EXP-011 evidence is retained without overwrite or deletion.
confirmed_conclusions:
  - EXP-011 is INVALID/non-counting at a launch/CLI integration boundary; it neither confirms nor refutes physical pick-place behavior.
  - EXP-010 remains the last VALID experiment and its independent acceptance is unchanged.
  - EXP-012 through EXP-014 remain PLANNED but prohibited until an approved implementation and fresh task_start retry reach a countable physical result.
next_command: Await explicit approval of EXP-015's bounded remove_ros_args design; after approval, begin with focused RED tests for both affected CLIs.
```

```yaml
transition_id: TRANS-EXP-015-RUNNING-001
recorded_at: 2026-08-26T12:12:15+08:00
experiment_id: EXP-015
from: PLANNED
to: RUNNING
approval: User explicitly approved the bounded remove_ros_args design.
source_commit: PENDING_LEDGER_COMMIT
implementation_commit: a8b3d87ac08dc124e0d54f27fbee93f62c8cfb4a
submodule_commit: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
pre_running_observed:
  - OBSERVED: Focused RED produced exactly two exit-2 failures for the two launch-injected ROS argument forms while both unknown-application-argument controls remained strict and passed.
  - OBSERVED: The minimal implementation conditionally applies rclpy.utilities.remove_ros_args only when `--ros-args` is present; focused GREEN passed 5 tests including the existing no-rclpy-import boundary, affected regression passed 83 tests, and the full package suite passed 375 tests.
  - OBSERVED: Ruff lint passes on all four changed files, both production CLIs pass Ruff format check, git diff check passes, and the two changed test files retain only their identical pre-existing whole-file format baseline; no bulk formatting was performed.
  - OBSERVED: The implementation is committed and pushed as a8b3d87ac08dc124e0d54f27fbee93f62c8cfb4a. The same five-package task overlay rebuilt successfully, and both installed entrypoints accept their exact ROS-argument shapes with help exit 0.
  - OBSERVED: Immediate isolation finds task source and exact f19 clean, canonical main clean at b3770360b26fe8f6fac0e19338d250b6f5cab0e7, all five package prefixes in the task overlay, domain 193 empty, no domain/partition owner, owned tmux absent, Viewer count zero, and CUA daemon healthy.
  - OBSERVED: Fresh Mesa ctypes GLFW smoke created and destroyed a hidden window on DISPLAY :1 with exit 0.
environment:
  ROS_DOMAIN_ID: 193
  GZ_PARTITION: rgbd-pick-task-start-exp015-20260826
  __GLX_VENDOR_LIBRARY_NAME: mesa
  LIBGL_ALWAYS_SOFTWARE: "1"
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-015/tdd/red-focused.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-015/tdd/green-focused.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-015/tdd/green-affected.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-015/tdd/pytest-full.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-015/tdd/static-checks.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-015/overlay-rebuild.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-015/pre-running/installed-cli-ros-args-smoke.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-015/pre-running/glfw-mesa-ctypes-hidden-smoke.log
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-015/pre-running/isolation-snapshot.log
next_command: Start exact-owned tmux rgbd-pick-exp015-20260826 with the frozen task_start full-restart wrapper, then capture baseline, transport, and released-final Viewer frames at manifest boundaries.
```
