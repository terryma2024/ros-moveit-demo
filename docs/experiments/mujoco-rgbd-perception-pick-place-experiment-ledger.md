# MuJoCo RGB-D Perception Pick-Place Experiment Ledger

```yaml
task_id: so101-mujoco-rgbd-perception-pick-place
goal: Complete one RGB-D perception-driven physical MuJoCo pick-place from each of four named cup positions on the local Mac.
success_contract: Four independent FULL_RESTART runs each use real aligned RGB-D, publish a fresh world /cup_pose from rgbd_cup_pose, reach dynamic DONE, and pass physical, Planning Scene, controller, TF, and visual gates.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place
branch: codex/rgbd-perception-pick-place
base_commit: a7e3745f13b892a8b7501980fdaf87436392ad50
current_commit: ef6175dd146275d56979ad2860f1f3a6f94dbf79
evidence_root: /tmp/so101-debug-rgbd-perception-pick-place-20260826/
confirmed_conclusions:
  - Existing macOS CameraPlugin acceptance proves real aligned RGB-D is available only from a correctly sourced interactive runtime; topic names alone are insufficient.
  - Existing dynamic MuJoCo execution accepts one fresh world-frame /cup_pose and has already completed a canonical physical demonstration with a truth-only test bridge.
  - Tasks 2-5 established code-owned static camera TF, exact-stamp RGB-D localization, a fail-closed /cup_pose producer, and perception-confirmed MoveIt cup-shadow synchronization at source level.
  - Task 6 installed a dedicated behavior-tested fail-closed perception launch while preserving the fixed MuJoCo workflow composition (EXP-002).
  - EXP-003 is a valid perception-only runtime failure: the production rgbd_cup_pose process published no /cup_pose and exited 1 at its 30 s startup deadline, although an extended diagnostic later captured and segmented an exact-stamp RGB-D triple.
disproven_routes:
  - Publishing MuJoCo truth as /cup_pose does not validate production camera perception.
  - Routing production through cup_pose_tf_demo duplicates the selected world-point transform boundary.
open_hypotheses:
  - The current color mask, DBSCAN, static TF, and circle fit localize all four named positions within 0.01 m.
  - The Mac production startup/readiness boundary must be instrumented or extended so delayed first RGB-D and world TF availability cannot consume the complete 30 s pose deadline.
latest_checkpoint: CP-008
next_experiment: EXP-004
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
status: VALID
result: FAILURE
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
    exit_code: 1
  - command: capture bounded one-shot RGB-D, TF, /cup_pose, publisher, MuJoCo truth, process, and Computer Use visual evidence; then SIGINT only owned process groups and verify cleanup
    exit_code: 1
observed:
  - OBSERVED: CORR-EXP-003-001 cleared the historical preflight block at effective source ef6175dd146275d56979ad2860f1f3a6f94dbf79; the complete package suite passed 369 tests, the package rebuilt with exit 0, and runtime imports and installed so101_demo_py artifacts resolved to this worktree.
  - OBSERVED: The immediate pre-launch graph in ROS domain 180 and the owned-process target set were empty; the isolated task_start/headless=false execute stack started its real MuJoCo camera rendering loop at 640x480 and activated all controllers without starting dynamic_cup_pick_place or commanding motion.
  - OBSERVED: Real CameraInfo was 640x480 at stamp 220.322000000; real color was 640x480 rgb8 with step 1920 and 921600 bytes at stamp 279.248000000; real depth was 640x480 32FC1 with step 2560 and 1228800 bytes at stamp 275.534000000. These separate one-shot samples prove message contents but are not an aligned triple.
  - OBSERVED: Production rgbd_cup_pose exited 1 after `RGBD_CUP_POSE_TIMEOUT: no valid RGB-D cup pose was published within 30.000 seconds`; /cup_pose never appeared and production cup.ply and perception.json were absent.
  - OBSERVED: A bounded 90 s rgbd_point_cloud diagnostic then exited 0 with one exact aligned triple at stamp_ns 337986000000 in task_camera_frame; it accepted 640x480 rgb8/32FC1, retained 98082 finite positive-depth points, selected 259 orange candidates, segmented 141 cup points, and wrote a 4013-byte diagnostic PLY.
  - OBSERVED: world to task_camera_frame initially reported that frame `world` did not exist, then became stable at translation [0.650, -0.650, 0.550] and quaternion [0.799, 0.331, -0.192, -0.465]. The first fresh MuJoCo truth sample was world [0.020000000000000018, -0.28, 0.16480156647042168].
  - OBSERVED: Computer Use application discovery reported org.mujoco.mujoco isRunning=false, so no causally attributable Viewer snapshot-action-fresh-snapshot sequence could be captured without launching an unrelated app; the visual gate failed.
  - OBSERVED: The two owned static-TF sessions received SIGINT; their remaining exact owned process groups 69568 and 70363 also received SIGINT. The owned launch session then received Ctrl-C and returned 0 after ordered MoveGroup, controller, robot-state-publisher, and MuJoCo shutdown. The final targeted process scan and ROS domain 180 graph were empty.
inferred:
  - INFERRED: The first production boundary is startup/readiness, not topic registration or point-cloud segmentation: no valid world pose completed inside 30 s, while extended evidence proves the same live stack can later deliver valid aligned RGB-D, segmentation, and TF. Because production emitted only its aggregate timeout, this experiment does not distinguish whether delayed first aligned input, delayed world TF, or both consumed the deadline.
  - INFERRED: No perception-vs-truth error can be accepted because production never published a pose. Diagnostic camera-frame center and MuJoCo truth are retained only for the next instrumented experiment, not substituted for production output.
conclusion: EXP-003 is a valid failed perception-only gate. Production /cup_pose, production PLY/JSON, truth-error, publisher/sample provenance, and Viewer visual evidence did not meet acceptance; no robot-motion workflow was started.
evidence:
  - /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/
decision: KEEP_VALID_FAILURE_EVIDENCE_AND_FIX_FIRST_BOUNDARY
next_experiment: EXP-004
preflight_status: BLOCKED_BEFORE_RUNTIME
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
preflight_conclusion: EXP-003 remains PLANNED and no runtime sample may be counted until the Task 6 installed-provenance regression is fixed and the full suite is rerun.
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
