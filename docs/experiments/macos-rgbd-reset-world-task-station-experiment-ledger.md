# macOS RGB-D RESET_WORLD Task Station Experiment Ledger

```yaml
task_id: so101-macos-rgbd-reset-world-task-ui-20260827
goal: Reuse one visible macOS MuJoCo environment to run arbitrary RGB-D perception-driven cup pick-place points and browse task evidence through Teleop.
success_contract: One unchanged visible MuJoCo session completes the four approved presets through RESET_WORLD with monotonically increasing epochs, then proves unreachable-point continuation, manual RGB-D capture, evidence browsing, and owned-process cleanup.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/macos-rgbd-reset-world-task-station
branch: codex/macos-rgbd-reset-world-task-station
base_commit: 6e807f8d7a5aff9ff7c2ff931d517828355fa5f2
current_commit: be4fae084e486578bd508a0413ed16808c1e00bd
child_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
child_version: 0.1.0
evidence_root: /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/
confirmed_conclusions:
  - The parent tree pins mujoco_ros2_control commit 5e9d67ce9fde39d35bf94cc498721abf203a0ddd.
  - The isolated linked worktree resolves to its own absolute core.worktree after correcting the missing per-worktree metadata.
  - EXP-001 validates strict schema-version-one task points and the four shipped presets with 17 focused tests.
  - EXP-002 validates the 0.1.0 ResetWorld free-joint override and arbitrary cup-position CLI with 40 focused and regression tests.
  - EXP-003 validates seven-segment plan-only reachability with terminal-state chaining and first-failure classification.
  - EXP-004 validates the MoveGroup plan-only wire adapter, stable task CLI contract, and mandatory dynamic pre-motion reachability gate.
  - EXP-005 validates one-stamp RGB, full-cloud, cup-cloud, deterministic preview, and summary generation before pose publication.
  - EXP-006 validates exclusive batch/point allocation, fsynced atomic JSON, content addressing, and symlink/outside-root rejection.
  - EXP-007 validates point-local continuation, shared/held-cup abort, monotonic epochs, safe cancellation, and required terminal evidence.
disproven_routes:
  - A linked worktree without per-worktree core.worktree is invalid in this submodule checkout because the common core.worktree redirects Git into the submodule metadata directory.
open_hypotheses:
  - The approved point schema and immutable point values can be added without changing existing dynamic pick-place defaults.
  - The frozen four-point behavior remains valid when one stack is reused through RESET_WORLD.
latest_checkpoint: CP-014
next_experiment: EXP-008
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

## CP-003 — Task 1 committed and package baseline characterized

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-001
current_hypothesis: The 0.1.0 ResetWorld request can carry one plastic_cup free-joint override while preserving the legacy default when no position is supplied.
working_tree_status: clean at d1e1d58f28990f8cc75899712f6281311ee62cd9 before planning EXP-002
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 1 is committed as d1e1d58f28990f8cc75899712f6281311ee62cd9.
  - The child checkout is initialized at exact commit 5e9d67ce9fde39d35bf94cc498721abf203a0ddd.
  - The full source suite reaches 460 passes and one installed-provenance failure; the identical assertion also fails on untouched main because the active old install lacks so101_mujoco_perception_pick_place.
disproven_routes:
  - The old main install cannot be used as final installed-runtime evidence; Task 14 must build and source the isolated candidate overlay.
open_risks:
  - The current old-install provenance failure remains expected until the isolated candidate install gate.
next_command: Write and run the EXP-002 ResetWorld free-joint override RED tests.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/baseline-full.log sha256=afe2ffb11ea00201887d49ed2a19e629d115b0d5ded78905072b97aa457acc34
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/baseline-main-ab.log sha256=c342d21024a69e7a231ed90955b04bd3a0d2806aa6e5fe584af51dc8f40fd0fe
```

## EXP-002 — arbitrary cup-position ResetWorld contract

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: The pinned 0.1.0 ResetWorld message can atomically apply one world-frame plastic_cup free-joint pose with zero twist while the default CLI path remains byte-for-byte compatible in behavior.
prediction: The RED tests fail because reset_world accepts only keyframe and the CLI has no cup-position argument; GREEN passes message construction, validation, transaction verification, and legacy defaults.
single_variable: Add only the free-joint override value, ResetWorld conversion, per-call verification inputs, and teleop_reset option.
lifecycle: RESET_WORLD
preconditions:
  - Source commit is d1e1d58f28990f8cc75899712f6281311ee62cd9 and child checkout is exact 5e9d67ce9fde39d35bf94cc498721abf203a0ddd.
  - No simulator or ROS stack is started for this source-level contract experiment.
success_criteria:
  - The 0.1.0 request contains one plastic_cup FreeJointState with world-frame pose, identity quaternion, and explicit zero twist.
  - Duplicate names, non-finite values, and non-unit quaternions fail closed before service invocation.
  - Reset verification checks requested position, identity orientation, zero twist, step zero, unchanged session, and epoch old plus one.
  - Omitting the CLI option preserves task_start and no override; supplying XYZ creates exactly one override and records the requested position.
failure_criteria:
  - Any malformed override reaches the service, a requested point is not verified, or a legacy reset regression appears.
invalid_criteria:
  - The test fails only because the old main install provenance assertion is still stale.
provenance:
  source_commit: d1e1d58f28990f8cc75899712f6281311ee62cd9
  install_overlay: SOURCE_WITH_MAIN_ROS_ENV
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python
  ros_domain_id: NOT_STARTED
  gz_partition: NOT_STARTED
commands:
  - command: Source the main macOS ROS environment and run focused test_mujoco_reset_client.py plus test_teleop_reset_cli.py under the evidence-root source shim.
    exit_code: 2
  - command: colcon --log-base /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task2-msg-log build --base-paths third_party/mujoco_ros2_control --packages-select mujoco_ros2_control_msgs --merge-install --build-base /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task2-msg-build --install-base /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task2-msg-install --event-handlers console_direct+
    exit_code: 0
  - command: Source task2-msg-install and run test_mujoco_reset_client.py, test_teleop_reset_cli.py, test_transactional_reset.py, and test_teleop_owner.py.
    exit_code: 0
observed:
  - The valid RED failed because FreeJointResetOverride did not exist.
  - The first GREEN attempt was INVALID because moveit-demo/install advertises package version 0.1.0 but its generated Python messages contain neither FreeJointState nor ResetWorld.state_overrides.
  - A source-backed message-only overlay built from child commit 5e9d67ce9fde39d35bf94cc498721abf203a0ddd and exposed both required 0.1.0 symbols.
  - The source-backed GREEN passed 40 tests in 0.49 seconds.
inferred:
  - The earlier import failure was installed-message provenance drift, not a ResetWorld implementation defect.
conclusion: Explicit XYZ creates one validated world-frame plastic_cup override with identity orientation and zero twist; the transaction verifies the requested atomic state and the default CLI path remains compatible.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task2-red.log sha256=d853b080870ae4c0aabc061061f82e3bc7e5f9e40db4eefb82fb78da8d4aeda4
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task2-green-invalid-stale-msg.log sha256=091539f1650d034f30120ce71e974108111902c3e01a419b2f57ef2a152c2984
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task2-msg-build-summary.log sha256=a6c051568c08f93d877f8cbcb488aafdccfbb209c16aed7e24ad8123fefa0dd4
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task2-green.log sha256=cbe16372bea6b69d9271a417d275f17ec04f9dd8df00a9746334c08c2b6560dc
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task2-msg-install/share/mujoco_ros2_control_msgs/package.xml sha256=cb5b1e5590d0bbfd56fa461045d350fc8d46c614a1663fc60e23271204530710
decision: KEEP
next_experiment: EXP-003
```

## CP-004 — Task 2 GREEN, commit pending

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-002
current_hypothesis: The seven dynamic motion targets can be checked sequentially without exposing any execution method at the reachability boundary.
working_tree_status: ledger plus the six planned Task 2 source and test files are modified
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - The exact 0.1.0 child source and generated candidate messages support ResetWorld.state_overrides.free_joints.
  - Task 2 focused and legacy reset regressions pass 40 tests.
disproven_routes:
  - The old moveit-demo/install generated message package cannot exercise the 0.1.0 ResetWorld wire contract despite its package.xml version string.
open_risks:
  - Full project installed provenance remains deferred to the isolated Task 14 overlay.
next_command: git diff --check && commit the seven planned Task 2 paths.
```

## CP-005 — Task 2 committed; Task 3 preregistered

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-002
current_hypothesis: The seven dynamic motion targets can be checked sequentially without exposing any execution method at the reachability boundary.
working_tree_status: clean at 2ee7676040d1bb5eaf972fdbb70bd4fc6850b062 before writing the Task 3 RED test
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 2 is committed as 2ee7676040d1bb5eaf972fdbb70bd4fc6850b062.
  - Candidate message overlay remains /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task2-msg-install for source tests requiring the 0.1.0 wire interface.
disproven_routes:
  - NONE beyond the previously recorded stale installed-message path.
open_risks:
  - Reachability is still an application-only contract until Task 4 binds MoveGroup plan-only.
next_command: Run the missing task_reachability module RED test.
```

## EXP-003 — backend-neutral sequential reachability

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: Planning each of the seven dynamic TCP targets from the prior accepted trajectory terminal state can classify a point as REACHABLE, UNREACHABLE, or UNKNOWN without any execution method.
prediction: The RED test fails because application.task_reachability is absent; GREEN passes ordered terminal-state propagation, first-failure stop, and infrastructure-unknown cases.
single_variable: Add only the backend-neutral reachability values, protocol, ordered sequence, algorithm, and tests.
lifecycle: RESET_WORLD
preconditions:
  - Source commit is 2ee7676040d1bb5eaf972fdbb70bd4fc6850b062.
  - No ROS action, controller, simulator, or process is started.
success_criteria:
  - The exact seven production states are planned in order.
  - Each accepted terminal state becomes the next segment start.
  - The first rejected segment ends planning and preserves its MoveIt code, failure code, and collision pairs.
  - Stale scene/joints, timeout, or unavailable planner classify UNKNOWN.
  - ReachabilityPlannerPort exposes no execution operation.
failure_criteria:
  - A later segment is attempted after failure, terminal state propagation is lost, or infrastructure failure is misclassified reachable.
invalid_criteria:
  - The test imports ROS or fails from the stale installed message package.
provenance:
  source_commit: 2ee7676040d1bb5eaf972fdbb70bd4fc6850b062
  install_overlay: SOURCE_ONLY
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python
  ros_domain_id: NOT_STARTED
  gz_partition: NOT_STARTED
commands:
  - command: Run test_task_reachability.py under the evidence-root source shim.
    exit_code: 2
  - command: Run test_task_reachability.py, test_dynamic_pick.py, and test_dynamic_plan_only.py under the evidence-root source shim.
    exit_code: 0
observed:
  - The valid RED failed because so101_demo.application.task_reachability did not exist.
  - The GREEN passed 16 tests in 0.05 seconds.
  - The application protocol contains plan only; no execute method is present.
inferred:
  - UNKNOWN is reserved for unavailable/stale infrastructure or missing terminal state; deterministic target resolution and MoveIt rejection are UNREACHABLE.
conclusion: The exact seven dynamic states plan in order, each accepted terminal state seeds the next segment, and the first failure stops further planning with preserved diagnostics.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task3-red.log sha256=b2029f02647300cc3387a4409569435f058f5c86d1edd3f85ccf6e71b3a4196d
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task3-green.log sha256=30055d158000922f5cf284b6a3dccf5b6fbaaf37d82c50405629f507b4d6441c
decision: KEEP
next_experiment: EXP-004
```

## CP-006 — Task 3 GREEN, commit pending

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-003
current_hypothesis: MoveGroup plan-only can implement the reachability port with a request-local plastic_cup Planning Scene diff and no execution side effect.
working_tree_status: ledger, core/dynamic_pick.py, application/task_reachability.py, and test_task_reachability.py contain only planned Task 3 changes
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 3 focused and dynamic-target regressions pass 16 tests.
  - The public ordered reachability tuple contains MOVE_ABOVE_OBJECT, DESCEND, MICRO_LIFT, LIFT, MOVE_ABOVE_PLACE, DESCEND_TO_PLACE, and RETREAT.
disproven_routes:
  - Independent planning of every segment from the same initial state is rejected; accepted terminal state chaining is required.
open_risks:
  - Scene revision and collision diagnostics remain adapter-supplied until Task 4.
next_command: git diff --check && commit the four planned Task 3 paths.
```

## CP-007 — Task 3 committed; Task 4 preregistered

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-003
current_hypothesis: MoveGroup plan-only can implement the reachability port with a request-local plastic_cup Planning Scene diff and no execution side effect.
working_tree_status: clean at 73356e9a4353310892630ec9dd919c4a8aea75ae before Task 4 RED tests
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 3 is committed as 73356e9a4353310892630ec9dd919c4a8aea75ae.
disproven_routes:
  - NONE beyond prior checkpoints.
open_risks:
  - MoveGroup action result and request-local scene fields require source-backed ROS message validation.
next_command: Run Task 4 ROS wire and CLI RED tests.
```

## EXP-004 — MoveGroup plan-only adapter and task CLI

```yaml
experiment_id: EXP-004
status: VALID
prior_experiment: EXP-003
hypothesis: A MoveGroup action goal with plan_only true and an is_diff request-local cup object can plan the seven targets without mutating the global Planning Scene or executing a trajectory.
prediction: RED fails because ros.task_reachability and cli.task_reachability are absent; GREEN proves wire fields, terminal trajectory chaining, stable JSON/exit codes, installed entry point, and dynamic pre-motion rejection.
single_variable: Bind Task 3 reachability to MoveGroup plan-only and expose the installed JSON CLI plus dynamic execute preflight.
lifecycle: RESET_WORLD
preconditions:
  - Source commit is 73356e9a4353310892630ec9dd919c4a8aea75ae.
  - Tests use the sourced macOS ROS environment; no action server or controller is started.
success_criteria:
  - Goal plan_only is true, replan is false, start state is exact, and scene diff contains only plastic_cup.
  - Accepted result returns the final trajectory point; rejection and timeout preserve stable diagnostics.
  - No execute_trajectory, apply_planning_scene, or controller action client is created.
  - CLI exit codes are 0 reachable, 2 unreachable, and 1 unknown/infrastructure.
  - Dynamic execution rejects non-REACHABLE before creating workflow actions.
failure_criteria:
  - Any global scene mutation or execution boundary is invoked, diagnostics are lost, or motion begins after failed preflight.
invalid_criteria:
  - Tests resolve stale generated ROS messages or the old installed project executable set.
provenance:
  source_commit: 73356e9a4353310892630ec9dd919c4a8aea75ae
  install_overlay: SOURCE_WITH_TASK2_MSG_CANDIDATE
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python
  ros_domain_id: NOT_STARTED
  gz_partition: NOT_STARTED
commands:
  - command: Run test_task_reachability_ros.py and test_task_reachability_cli.py.
    exit_code: 2
  - command: Run test_task_reachability_ros.py, test_task_reachability_cli.py, and test_dynamic_scene_sync.py.
    exit_code: 0
  - command: Run the complete src/so101_demo_py/test suite with writable ROS_HOME and ROS_LOG_DIR.
    exit_code: 1
observed:
  - The valid RED failed only because the ROS adapter and CLI modules did not exist.
  - Focused GREEN passed 33 tests; dynamic execution regressions added another 13 passes.
  - The full source suite passed 491 tests; its sole failure is the explicitly deferred old-install executable closure assertion.
  - The MoveGroup goal is plan_only, contains only a request-local plastic_cup scene diff, and returns the accepted trajectory's final joint point.
  - An UNREACHABLE preflight writes reachability-observed.json and prevents execution construction, action building, and runner invocation.
inferred:
  - The request-local Planning Scene avoids mutating the global scene during reachability planning while the existing scene convergence gate still runs first.
conclusion: The installed CLI contract and dynamic pre-motion gate are source-valid; fresh installed-runtime closure remains deliberately deferred to Task 14.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task4-red.log sha256=b7956ee9a0e1c45488c415998fc47c0a2f230d9c05dd7e68bccf14435bea1310
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task4-green.log sha256=5f3ebba9afb45526e1e1b6b61ba22c64ccca996c3e903535228dbc9b3e4fb033
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task4-full-source.log sha256=05f710835a05170d620b8af913a79dc5b37e00d15ee1c7b0cb66c58741cd691a
decision: KEEP
next_experiment: EXP-005
```

## CP-008 — Task 4 GREEN, commit pending

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-004
current_hypothesis: A typed sequential supervisor can reuse one visible stack, isolate every point's evidence, and continue after a point-local failure.
working_tree_status: ledger plus Task 4 ROS adapter, CLI, setup entry point, dynamic gate, provenance expectation, and tests contain only planned changes
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 4 focused reachability and orchestration tests pass 33 tests.
  - Complete Python source regression passes 491 tests, with only the known old-install executable closure gate deferred to Task 14.
disproven_routes:
  - Running ROS launch-construction tests without writable ROS_HOME and ROS_LOG_DIR is invalid under the workspace sandbox.
open_risks:
  - The real MoveGroup action and macOS simulator have not been started; source-valid does not imply runtime-qualified.
next_command: git diff --check and commit the nine planned Task 4 paths.
```

## CP-009 — Task 4 committed; Task 5 preregistered

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-004
current_hypothesis: One exact-stamp RGB-D frame can own RGB, full-cloud, cup-cloud, deterministic preview, and summary artifacts without a file round-trip.
working_tree_status: clean at 507169114e60b10bbe983dec14233927ab802112 before Task 5 RED tests
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 4 is committed as 507169114e60b10bbe983dec14233927ab802112.
disproven_routes:
  - NONE beyond prior checkpoints.
open_risks:
  - Deterministic PNG and PLY writers must fail closed before success is reported.
next_command: Write and run Task 5 synchronized artifact RED tests.
```

## EXP-005 — synchronized RGB-D snapshot artifacts

```yaml
experiment_id: EXP-005
status: VALID
prior_experiment: EXP-004
hypothesis: One immutable exact-stamp frame can retain RGB, full cloud, segmented cup cloud, and generate deterministic PNG/PLY artifacts before pose publication.
prediction: RED fails because rgbd_snapshot, point_cloud_preview, and rgbd_sensor_capture do not exist and the current cloud result discards RGB/full-cloud arrays.
single_variable: Retain and write synchronized RGB-D artifacts without changing segmentation or cup fitting algorithms.
lifecycle: RESET_WORLD
preconditions:
  - Source commit is 507169114e60b10bbe983dec14233927ab802112.
  - No ROS graph, camera, simulator, or GUI is started for source-level tests.
success_criteria:
  - Frame stamp, dimensions, RGB, full XYZ/RGB, and cup XYZ/RGB come from one aligned triple.
  - Snapshot output includes valid RGB PNG, full/cup PLY, deterministic preview PNG, and a summary with one source stamp.
  - Mismatched stamps, missing exact TF, invalid depth, or artifact write failure never report success.
  - Production first-valid publisher writes selected RGB/full/cup/summary artifacts before /cup_pose.
failure_criteria:
  - Any artifact is sourced from a different stamp, full cloud requires a PLY readback, or publication precedes evidence writes.
invalid_criteria:
  - Tests fail only because Open3D is unavailable rather than through the injected cloud seam.
provenance:
  source_commit: 507169114e60b10bbe983dec14233927ab802112
  install_overlay: SOURCE_ONLY
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python
  ros_domain_id: NOT_STARTED
  gz_partition: NOT_STARTED
commands:
  - command: Run Task 5 RGB-D point cloud, pose, snapshot, and preview tests.
    exit_code: 1
  - command: Source macOS Jazzy and run RGB-D point cloud, pose, snapshot, preview, and asset closure tests.
    exit_code: 0
  - command: Run the complete source test suite with the source-backed 0.1.0 message overlay.
    exit_code: 1
observed:
  - Valid RED exposed the discarded RGB/full-cloud arrays and three missing snapshot modules.
  - Focused GREEN plus resource closure passed 63 tests, and py_compile passed every changed production module.
  - The full source suite passed 497 tests; the sole failure remains the known old-install executable closure gate.
  - One exact source stamp owns RGB PNG, full and cup PLY, deterministic z-buffered preview PNG, and summary.json.
  - Missing exact TF or any artifact write failure prevents summary.json success output.
  - Production first-valid cup-pose evidence writes optional RGB and full PLY before cup PLY, summary, and /cup_pose publication.
inferred:
  - Retaining arrays in memory eliminates the earlier PLY round-trip risk and permits both automated and browser-oriented point-cloud evidence from the same frame.
conclusion: Synchronized RGB-D evidence generation is source-valid; live camera sampling remains a Task 15 runtime gate.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task5-red.log sha256=4ad3e462dcc69673c7f1dd917d413388c9bac22bf46b18539c8bc77d7083f15e
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task5-green.log sha256=4cf1d63d1fce6b79827d0d3e31027469019970f0fed97ee53d5235a94bc09ddb
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task5-full-source.log sha256=a437f76d3ca587a4533412ef6d8801779f45589c9900c18d13a85f0bfacdf1d7
decision: KEEP
next_experiment: EXP-006
```

## CP-010 — Task 5 GREEN, commit pending

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-005
current_hypothesis: Exclusive path-safe artifact registration can make every batch and point manifest immutable and content-addressed beneath the one caller-owned evidence root.
working_tree_status: ledger plus the planned Task 5 RGB-D frame, snapshot, preview, CLI, production evidence, packaging, and test paths are modified
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 5 focused and closure tests pass 63 tests; the complete source suite passes 497 tests apart from the deferred old-install gate.
  - The generated preview is deterministic and dependency-free; Open3D remains responsible only for production segmentation and legacy cup PLY compatibility.
disproven_routes:
  - Running ROS-aware tests without sourcing Jazzy is invalid and does not diagnose product behavior.
open_risks:
  - Artifact paths and checksums are not yet registered in exclusive batch/point manifests.
next_command: git diff --check and commit the planned Task 5 paths.
```

## CP-011 — Task 5 committed; Task 6 preregistered

```yaml
checkpoint_id: CP-011
last_valid_experiment: EXP-005
current_hypothesis: Exclusive path-safe artifact registration can make every batch and point manifest immutable and content-addressed beneath the one caller-owned evidence root.
working_tree_status: clean at 40dc356c501d12a000ff9552122ee59a6afe9b84 before Task 6 RED tests
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 5 is committed as 40dc356c501d12a000ff9552122ee59a6afe9b84.
disproven_routes:
  - NONE beyond prior checkpoints.
open_risks:
  - Directory names, symlinks, and pre-existing outputs must fail closed without escaping the registered root.
next_command: Write and run Task 6 artifact registry RED tests.
```

## EXP-006 — exclusive path-safe artifact registry

```yaml
experiment_id: EXP-006
status: VALID
prior_experiment: EXP-005
hypothesis: Exclusive allocation plus resolved-path validation can register immutable content-addressed artifacts without allowing duplicate IDs, overwrite, or symlink escape.
prediction: RED fails because runtime.task_artifacts does not exist; GREEN proves exclusive batch/point allocation, fsynced atomic JSON, checksum identity, and symlink rejection.
single_variable: Add only the backend-neutral task artifact registry and tests.
lifecycle: RESET_WORLD
preconditions:
  - Source commit is 40dc356c501d12a000ff9552122ee59a6afe9b84.
  - No ROS, simulator, process, or network is used.
success_criteria:
  - Batch and point directories are allocated exclusively under the caller root.
  - Registered files are regular non-symlink files inside the resolved root and use only relative manifest paths.
  - SHA-256, byte size, stable opaque ID, producing process, session, epoch, and UTC capture time are retained.
  - atomic_json fsyncs a same-directory temporary before replace and does not leave a temporary file.
failure_criteria:
  - Duplicate allocation overwrites data, a symlink escapes, or an absolute path enters ArtifactRecord.
invalid_criteria:
  - Tests operate outside a temporary evidence root.
provenance:
  source_commit: 40dc356c501d12a000ff9552122ee59a6afe9b84
  install_overlay: SOURCE_ONLY
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python
  ros_domain_id: NOT_STARTED
  gz_partition: NOT_STARTED
commands:
  - command: Run test_task_artifacts.py.
    exit_code: 1
  - command: Run test_task_artifacts.py and test_asset_closure.py, then py_compile and git diff --check.
    exit_code: 0
observed:
  - The valid RED failed because runtime.task_artifacts did not exist.
  - GREEN and package closure passed 13 tests, and compilation plus whitespace checks passed.
  - Duplicate batch/point allocation, unsafe IDs, foreign batches, outside-root paths, and symlink paths all fail closed.
  - Registered artifacts contain only root-relative paths plus byte size, SHA-256, stable opaque ID, process, session, epoch, and UTC time.
  - atomic_json writes and fsyncs a same-directory temporary, replaces the target, fsyncs the directory, and removes temporary residue.
inferred:
  - Later API and browser layers can expose opaque IDs and relative paths without trusting caller-supplied filesystem paths.
conclusion: The single-root artifact registry is source-valid and ready for the batch application layer.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task6-red.log sha256=3bec4ac636c7b77aa0558520785705fe8b7e2265fd68188e05dcf5c59319a680
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task6-green.log sha256=93827f6af963d1172f6b4321a05c857de4b5e0acdea33cf11473722016d3a8eb
decision: KEEP
next_experiment: EXP-007
```

## CP-012 — Task 6 GREEN, commit pending

```yaml
checkpoint_id: CP-012
last_valid_experiment: EXP-006
current_hypothesis: A first-failure batch state machine can continue after point-local failures while aborting shared-stack or held-cup failures and finalizing every point before advancing.
working_tree_status: ledger plus runtime/task_artifacts.py and test_task_artifacts.py contain only planned Task 6 changes
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 6 focused and closure tests pass 13 tests.
disproven_routes:
  - Caller-supplied absolute artifact paths and symlink traversal are rejected as manifest identities.
open_risks:
  - Batch continuation and safety classification are not yet applied to reset/perception/workflow outcomes.
next_command: git diff --check and commit the three planned Task 6 paths including the ledger.
```

## CP-013 — Task 6 committed; Task 7 preregistered

```yaml
checkpoint_id: CP-013
last_valid_experiment: EXP-006
current_hypothesis: A first-failure batch state machine can continue after point-local failures while aborting shared-stack or held-cup failures and finalizing every point before advancing.
working_tree_status: clean at be4fae084e486578bd508a0413ed16808c1e00bd before Task 7 RED tests
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 6 is committed as be4fae084e486578bd508a0413ed16808c1e00bd.
disproven_routes:
  - NONE beyond prior checkpoints.
open_risks:
  - Failure scope, held-cup recovery, epoch monotonicity, cancellation, and terminal evidence completeness must be explicit state-machine decisions.
next_command: Write and run Task 7 batch application RED tests.
```

## EXP-007 — reset-world batch continuation state machine

```yaml
experiment_id: EXP-007
status: VALID
prior_experiment: EXP-006
hypothesis: A typed application loop can skip declared-unreachable points, continue after local failures, and abort safely on shared-stack or held-cup faults while preserving monotonic reset epochs and finalized evidence.
prediction: RED fails because application.task_batch does not exist; GREEN proves point continuation, fatal abort, operator recovery, cancellation checkpoints, cleanup order, and manifest finalization.
single_variable: Add only backend-neutral batch values, protocol, state machine, manifests, and tests.
lifecycle: RESET_WORLD
preconditions:
  - Source commit is be4fae084e486578bd508a0413ed16808c1e00bd.
  - Task 6 registry owns one temporary test evidence root; no ROS or processes are started.
success_criteria:
  - UNREACHABLE is skipped without reset; UNKNOWN/shared failures abort; point-local failures finalize and continue.
  - Each executed point increments the same session epoch exactly once.
  - Consumer subscription is ready before perception starts.
  - Required RGB/full PLY/cup PLY/preview/Viewer artifacts are captured before immutable point finalization.
  - Children stop, safety passes, manifest finalizes, then and only then the next point can start.
  - Held-cup faults end NEEDS_OPERATOR_RECOVERY without an automatic reset.
failure_criteria:
  - A later point runs after a shared fault, reset occurs for an unreachable point, or missing evidence is reported successful.
invalid_criteria:
  - A fake runtime writes outside the one registry root.
provenance:
  source_commit: be4fae084e486578bd508a0413ed16808c1e00bd
  install_overlay: SOURCE_ONLY
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python
  ros_domain_id: NOT_STARTED
  gz_partition: NOT_STARTED
commands:
  - command: Run test_task_batch.py.
    exit_code: 1
  - command: Run test_task_batch.py and test_task_artifacts.py, then py_compile and git diff --check.
    exit_code: 0
observed:
  - Valid RED failed because application.task_batch did not exist.
  - GREEN passed 17 tests, and compilation plus whitespace checks passed.
  - A point-local perception failure finalized FAILED evidence and the next point completed successfully.
  - Shared session/epoch failures aborted remaining points; held-cup failure ended NEEDS_OPERATOR_RECOVERY without reset.
  - Declared UNREACHABLE skipped reset, while incomplete RGB/PLY/preview/Viewer evidence failed only that point.
  - Cancellation was honored after child cleanup, safety confirmation, and point-result.json finalization.
inferred:
  - The runtime adapter can remain process/ROS-specific while continuation policy and evidence ordering stay deterministic and unit-testable.
conclusion: The backend-neutral RESET_WORLD batch application contract is source-valid and ready for the persistent ROS/process runtime.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task7-red.log sha256=ad5a8798e46e8f4acf96b8654ede19874e730be172522094aa42e84630fdf4df
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task7-green.log sha256=a44fbc805b9e3abae541e6c7d507a2374f44792f3b183195b4b950820da72bcb
decision: KEEP
next_experiment: EXP-008
```

## CP-014 — Task 7 GREEN, commit pending

```yaml
checkpoint_id: CP-014
last_valid_experiment: EXP-007
current_hypothesis: A persistent-stack ROS/process runtime can implement the batch port with exact process ownership, subscription-before-perception ordering, and one public CLI.
working_tree_status: ledger plus application/task_batch.py and test_task_batch.py contain only planned Task 7 changes
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 7 batch and artifact regressions pass 17 tests.
disproven_routes:
  - Continuing after shared session/epoch faults or automatically resetting an unsupported held cup is forbidden.
open_risks:
  - No actual subprocess, ROS subscription, reset service, perception publisher, or viewer capture is bound yet.
next_command: git diff --check and commit the three planned Task 7 paths including the ledger.
```
