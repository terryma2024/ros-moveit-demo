# MuJoCo RGB-D Perception Pick-Place Experiment Ledger

```yaml
task_id: so101-mujoco-rgbd-perception-pick-place
goal: Complete one RGB-D perception-driven physical MuJoCo pick-place from each of four named cup positions on the local Mac.
success_contract: Four independent FULL_RESTART runs each use real aligned RGB-D, publish a fresh world /cup_pose from rgbd_cup_pose, reach dynamic DONE, and pass physical, Planning Scene, controller, TF, and visual gates.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place
branch: codex/rgbd-perception-pick-place
base_commit: a7e3745f13b892a8b7501980fdaf87436392ad50
current_commit: bccd6e9e18e3a882962e7e880140d52a0d98c86f
evidence_root: /tmp/so101-debug-rgbd-perception-pick-place-20260826/
confirmed_conclusions:
  - Existing macOS CameraPlugin acceptance proves real aligned RGB-D is available only from a correctly sourced interactive runtime; topic names alone are insufficient.
  - Existing dynamic MuJoCo execution accepts one fresh world-frame /cup_pose and has already completed a canonical physical demonstration with a truth-only test bridge.
  - Tasks 2-5 established code-owned static camera TF, exact-stamp RGB-D localization, a fail-closed /cup_pose producer, and perception-confirmed MoveIt cup-shadow synchronization at source level.
  - Task 6 installed a dedicated behavior-tested fail-closed perception launch while preserving the fixed MuJoCo workflow composition (EXP-002).
disproven_routes:
  - Publishing MuJoCo truth as /cup_pose does not validate production camera perception.
  - Routing production through cup_pose_tf_demo duplicates the selected world-point transform boundary.
open_hypotheses:
  - The current color mask, DBSCAN, static TF, and circle fit localize all four named positions within 0.01 m.
latest_checkpoint: CP-004
next_experiment: EXP-003
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
