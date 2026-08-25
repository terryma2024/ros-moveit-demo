# MuJoCo RGB-D Perception Pick-Place Experiment Ledger

```yaml
task_id: so101-mujoco-rgbd-perception-pick-place
goal: Complete one RGB-D perception-driven physical MuJoCo pick-place from each of four named cup positions on the local Mac.
success_contract: Four independent FULL_RESTART runs each use real aligned RGB-D, publish a fresh world /cup_pose from rgbd_cup_pose, reach dynamic DONE, and pass physical, Planning Scene, controller, TF, and visual gates.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/rgbd-perception-pick-place
branch: codex/rgbd-perception-pick-place
base_commit: a7e3745f13b892a8b7501980fdaf87436392ad50
current_commit: a7e3745f13b892a8b7501980fdaf87436392ad50
evidence_root: /tmp/so101-debug-rgbd-perception-pick-place-20260826/
confirmed_conclusions:
  - Existing macOS CameraPlugin acceptance proves real aligned RGB-D is available only from a correctly sourced interactive runtime; topic names alone are insufficient.
  - Existing dynamic MuJoCo execution accepts one fresh world-frame /cup_pose and has already completed a canonical physical demonstration with a truth-only test bridge.
disproven_routes:
  - Publishing MuJoCo truth as /cup_pose does not validate production camera perception.
  - Routing production through cup_pose_tf_demo duplicates the selected world-point transform boundary.
open_hypotheses:
  - The current color mask, DBSCAN, static TF, and circle fit localize all four named positions within 0.01 m.
latest_checkpoint: CP-002
next_experiment: EXP-002
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
