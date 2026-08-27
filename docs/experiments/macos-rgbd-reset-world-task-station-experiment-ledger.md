# macOS RGB-D RESET_WORLD Task Station Experiment Ledger

```yaml
task_id: so101-macos-rgbd-reset-world-task-ui-20260827
goal: Reuse one visible macOS MuJoCo environment to run arbitrary RGB-D perception-driven cup pick-place points and browse task evidence through Teleop.
success_contract: One unchanged visible MuJoCo session completes the four approved presets through RESET_WORLD with monotonically increasing epochs, then proves unreachable-point continuation, manual RGB-D capture, evidence browsing, and owned-process cleanup.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/macos-rgbd-reset-world-task-station
branch: codex/macos-rgbd-reset-world-task-station
base_commit: 6e807f8d7a5aff9ff7c2ff931d517828355fa5f2
current_commit: 6e807f8d7a5aff9ff7c2ff931d517828355fa5f2
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
child_version: 0.1.0
evidence_root: /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/
confirmed_conclusions:
  - The parent tree pins mujoco_ros2_control commit 5e9d67ce9fde39d35bf94cc498721abf203a0ddd.
  - The isolated linked worktree resolves to its own absolute core.worktree after correcting the missing per-worktree metadata.
  - EXP-001 validates strict schema-version-one task points and the four shipped presets with 17 focused tests.
disproven_routes:
  - A linked worktree without per-worktree core.worktree is invalid in this submodule checkout because the common core.worktree redirects Git into the submodule metadata directory.
open_hypotheses:
  - The approved point schema and immutable point values can be added without changing existing dynamic pick-place defaults.
  - The frozen four-point behavior remains valid when one stack is reused through RESET_WORLD.
latest_checkpoint: CP-002
next_experiment: EXP-002
```

## CP-001 — isolated source checkpoint

```yaml
checkpoint_id: CP-001
recorded_at: 2026-08-27T04:54:29Z
last_valid_experiment: NONE
current_hypothesis: A strict schema-versioned point list can represent the four presets and arbitrary bounded finite XYZ values without coupling to ROS.
working_tree_status: clean before creating this ledger
owned_processes: NONE
preserved_processes: tmux sessions mrc010-exp013-final-stack and mrc010-exp013-smoke-r3, plus the pre-existing mrc010-macos-task7a-r4 tmux server process; none is owned by this task
runtime_inventory:
  host: matianyideMacBook-Air.local
  ros_graph: ros2 is not on PATH in the unsourced orchestrator shell; no runtime claim made
  codex_cua: no codex-cua tmux session listed
  bun: /Users/matianyi/.bun/bin/bun version 1.3.14
  python: /opt/homebrew/bin/python3 version 3.14.6
confirmed_conclusions:
  - Source HEAD is 6e807f8d7a5aff9ff7c2ff931d517828355fa5f2 on codex/macos-rgbd-reset-world-task-station.
  - The submodule gitlink is 5e9d67ce9fde39d35bf94cc498721abf203a0ddd; this worktree has not initialized its child checkout yet.
  - No simulator, MoveIt, controller, perception, Teleop, or task process was started by this task.
disproven_routes:
  - Editing or testing in the initially misresolved worktree was rejected before any source write.
open_risks:
  - The active macOS ROS overlay and child installed-runtime provenance remain unverified until the install/runtime gates.
next_command: PYTHONPATH=src/so101_demo_py/src python3 -m pytest -q src/so101_demo_py/test/test_task_points.py
```

## EXP-001 — strict point-list source contract

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: A ROS-free schema-versioned boundary can round-trip the four presets and arbitrary finite points while rejecting malformed, duplicate, non-finite, and out-of-workspace inputs.
prediction: The new test first fails because so101_demo.core.task_points is absent, then passes after the minimal immutable values and YAML boundary are implemented.
single_variable: Add only the Task 1 point-list schema, preset resource, loader, tests, and this ledger.
lifecycle: RESET_WORLD
preconditions:
  - The isolated worktree is on codex/macos-rgbd-reset-world-task-station at base commit 6e807f8d7a5aff9ff7c2ff931d517828355fa5f2.
  - No simulator or ROS stack is started for this source-level experiment.
success_criteria:
  - The RED test fails for the missing task_points module.
  - The GREEN test passes all point validation and round-trip cases.
  - The existing installed resource closure test includes the preset YAML.
failure_criteria:
  - A malformed or out-of-bounds point is accepted, a valid point does not round-trip, or an existing resource test regresses.
invalid_criteria:
  - The test fails for an unrelated interpreter, dependency, collection, or worktree fault.
provenance:
  source_commit: 6e807f8d7a5aff9ff7c2ff931d517828355fa5f2
  install_overlay: SOURCE_ONLY
  runtime_executable: /opt/homebrew/bin/python3
  ros_domain_id: NOT_STARTED
  gz_partition: NOT_STARTED
commands:
  - command: PYTHONPATH=/tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/source-shim PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/matianyi/ros2_jazzy/.venv/bin/python -m pytest -p no:cacheprovider -q src/so101_demo_py/test/test_task_points.py
    exit_code: 2
  - command: PYTHONPATH=/tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/source-shim PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/matianyi/ros2_jazzy/.venv/bin/python -m pytest -p no:cacheprovider -q src/so101_demo_py/test/test_task_points.py src/so101_demo_py/test/test_asset_closure.py
    exit_code: 0
observed:
  - The first invocation with Homebrew Python 3.14 was INVALID because pytest is absent.
  - The second invocation was INVALID because the repository src-layout requires the evidence-root package shim.
  - The valid RED invocation failed specifically because so101_demo.core.task_points did not exist.
  - The GREEN invocation passed 17 tests in 0.06 seconds, including the package asset closure suite.
inferred:
  - The source-level point boundary is independent of ROS and preserves the existing dynamic policy bounds contract.
conclusion: Strict task-point parsing, YAML round-trip, preset positions, and invalid-input rejection pass without changing existing runtime defaults.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task1-red.log sha256=f835aa31013e051024ad274dcdb240bc13cd8723a4b7deaa19a4dec5b7e97f83
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task1-green.log sha256=9f06d8e083d27c9fedb0b1bd87cf39ca0dbf59aa8d87f7397e579f50e0e4f246
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task1-red-invalid-python314.log sha256=c99d342a1664b93a03868ad56a22451965948da811503ce3b0d29ae5123b9dbb
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task1-red-invalid-package-layout.log sha256=d7549cdbb927a7b98a4ee2b7e184fe0c135fe6f132f8cd406096a0c576b142ea
decision: KEEP
next_experiment: EXP-002
```

## CP-002 — Task 1 GREEN, commit pending

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-001
current_hypothesis: The 0.1.0 ResetWorld request can carry one plastic_cup free-joint override while preserving the legacy default when no position is supplied.
working_tree_status: docs/experiments/macos-rgbd-reset-world-task-station-experiment-ledger.md plus the five planned Task 1 files are untracked
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - EXP-001 has a valid missing-module RED and 17-test GREEN result under Python 3.11.15 with pytest 8.4.2.
  - The four presets are task_start [0.02, -0.28, 0.165], forward [0.02, -0.33, 0.165], left [-0.03, -0.28, 0.165], and right [0.07, -0.28, 0.165].
disproven_routes:
  - Homebrew Python 3.14 and a raw src directory PYTHONPATH are invalid test environments for this package.
open_risks:
  - Ruff is not installed in the selected ROS Python environment; lint has not been claimed.
next_command: git diff --check && git add the six planned Task 1 paths && git commit -m "feat: add RGB-D task point lists"
```
