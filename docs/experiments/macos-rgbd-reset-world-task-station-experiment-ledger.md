# macOS RGB-D RESET_WORLD Task Station Experiment Ledger

```yaml
task_id: so101-macos-rgbd-reset-world-task-ui-20260827
goal: Reuse one visible macOS MuJoCo environment to run arbitrary RGB-D perception-driven cup pick-place points and browse task evidence through Teleop.
success_contract: One unchanged visible MuJoCo session completes the four approved presets through RESET_WORLD with monotonically increasing epochs, then proves unreachable-point continuation, manual RGB-D capture, evidence browsing, and owned-process cleanup.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/macos-rgbd-reset-world-task-station
branch: codex/macos-rgbd-reset-world-task-station
base_commit: 6e807f8d7a5aff9ff7c2ff931d517828355fa5f2
current_commit: 137cfd9
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
  - EXP-008 validates persistent visible launch composition, exact child argv/ordering, owned PGID cleanup, and PID-bound MuJoCo screenshots.
disproven_routes:
  - A linked worktree without per-worktree core.worktree is invalid in this submodule checkout because the common core.worktree redirects Git into the submodule metadata directory.
open_hypotheses:
  - The approved point schema and immutable point values can be added without changing existing dynamic pick-place defaults.
  - The frozen four-point behavior remains valid when one stack is reused through RESET_WORLD.
latest_checkpoint: CP-016
next_experiment: EXP-009
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

## CP-015 — Task 7 committed; Task 8 preregistered

```yaml
checkpoint_id: CP-015
last_valid_experiment: EXP-007
current_hypothesis: A persistent-stack ROS/process runtime can implement the batch port with exact process ownership, subscription-before-perception ordering, and one public CLI.
working_tree_status: clean at dd15da54adbd758091b184d9ede0e70c5b91e7a7 before Task 8 RED tests
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 7 is committed as dd15da54adbd758091b184d9ede0e70c5b91e7a7.
disproven_routes:
  - NONE beyond prior checkpoints.
open_risks:
  - Owned process groups, first-terminal status, macOS viewer PID/window identity, and attached-stack non-ownership require explicit seams and tests.
next_command: Write and run Task 8 process/runtime/launch/CLI RED tests.
```

## EXP-008 — persistent stack and ROS/process batch runtime

```yaml
experiment_id: EXP-008
status: VALID
prior_experiment: EXP-007
hypothesis: Argument-array subprocesses, owned process groups, ROS subscription probing, and PID-bound window capture can bind Task 7 to one reusable visible stack without broad process cleanup.
prediction: RED fails because task_batch_runtime, task_stack, viewer_capture, public CLI, and task-station launch do not exist.
single_variable: Add only the Task 8 ROS/process adapters, persistent composition, viewer capture, CLI, packaging, and tests.
lifecycle: RESET_WORLD
preconditions:
  - Source commit is dd15da54adbd758091b184d9ede0e70c5b91e7a7.
  - Unit tests inject process, ROS graph, window, and screencapture seams; no live stack starts.
success_criteria:
  - Dynamic consumer starts and advertises /cup_pose subscription before perception starts.
  - Child argv carries the exact session, reset epoch, and point-specific evidence paths without shell=True.
  - Only owned PGIDs receive bounded SIGINT then SIGTERM escalation in reverse dependency order.
  - The persistent launch uses headless=false and includes base stack plus both approved static TF nodes but no perception/workflow.
  - macOS capture accepts exactly one on-screen MuJoCo window for the recorded PID and verifies fresh PNG output.
  - CLI owns and shuts its stack unless attach-existing-stack is explicit; any failed point returns nonzero.
failure_criteria:
  - Perception races subscription, an unowned process is signaled, desktop fallback is used, or attached parent stack is shut down.
invalid_criteria:
  - Tests invoke live ROS, Swift, screencapture, or MuJoCo instead of injected seams.
provenance:
  source_commit: dd15da54adbd758091b184d9ede0e70c5b91e7a7
  install_overlay: SOURCE_WITH_MACOS_JAZZY_FOR_LAUNCH_TESTS
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python
  ros_domain_id: NOT_STARTED
  gz_partition: NOT_STARTED
commands:
  - command: Run Task 8 runtime, stack, viewer, CLI, and launch tests.
    exit_code: 2
  - command: Run Task 8 tests plus launch composition, perception launch, and RGB-D pose regressions in sourced macOS Jazzy.
    exit_code: 0
  - command: Run the complete source test suite with the source-backed 0.1.0 message overlay.
    exit_code: 1
observed:
  - Valid RED failed at collection because the task-station builder and Task 8 runtime modules did not exist.
  - GREEN passed 115 tests; changed Python compiled, the Swift helper parsed, and whitespace checks passed.
  - Full source regression passed 528 tests; only the explicitly deferred old-install executable closure failed.
  - Consumer argv carries the exact session/epoch and subscribes to /cup_pose before perception starts with point-specific RGB/full/cup/preview paths.
  - Persistent process roles stop in reverse order and only owned PGIDs receive bounded SIGINT/SIGTERM.
  - The launch defaults headless=false, contains MuJoCo/controllers/MoveIt/scene plus both static TF nodes, and contains no perception or workflow.
  - Viewer capture filters exactly one on-screen MuJoCo window by recorded PID and rejects ambiguous, stale, or non-PNG output without desktop fallback.
inferred:
  - Automatic and attached-stack modes now share the same batch port while ownership remains explicit: only automatic mode shuts down its parent launch.
conclusion: The Task 8 ROS/process binding is source-valid; real process/window identity and visible motion remain Task 15 gates.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task8-red.log sha256=ba46b88eb28b5e2b488c10fce1be2ef462c27b7924354834d1967a6f42076f1e
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task8-green.log sha256=6fe6755a8e8a4f410c5758d8792908dd7006aa447756139c4bc3c56013c4f6ea
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task8-full-source.log sha256=eebf1ab16774c1a292166006b47330c8c0a6543da6fcc872f779a5b329a6f85c
decision: KEEP
next_experiment: EXP-009
```

## CP-016 — Task 8 GREEN, commit pending

```yaml
checkpoint_id: CP-016
last_valid_experiment: EXP-008
current_hypothesis: Teleop can host one asynchronous task owner beside existing pages without changing their routes or workflow contracts.
working_tree_status: ledger plus planned Task 8 runtime, launch, Swift asset, CLI, continuous preview output, packaging, provenance expectation, and tests are modified
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 8 launch/runtime regressions pass 115 tests and complete source regression passes 528 tests apart from the deferred old-install gate.
disproven_routes:
  - Desktop-wide screenshot fallback and starting perception before the dynamic /cup_pose subscription are forbidden.
open_risks:
  - Teleop has no task owner or /tasks page yet; live stack readiness and capture remain unqualified.
next_command: git diff --check and commit the planned Task 8 paths.
```

## CP-017 — Task 8 committed

```yaml
checkpoint_id: CP-017
last_valid_experiment: EXP-008
current_hypothesis: A backend-profile-gated asynchronous task gateway can own one batch process group without exposing arbitrary commands or paths.
working_tree_status: clean at 269b874b215ed45e29cfaeac23d8d3cb02e4d667
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 8 persistent launch/runtime/viewer work is committed as 269b874.
disproven_routes:
  - NONE beyond prior checkpoints.
open_risks:
  - Task subprocess ownership, one-active-batch exclusion, atomic status reads, and capability gating are not implemented yet.
next_command: Add Task 9 gateway/profile RED tests and run them without a live ROS graph.
```

## EXP-009 — teleop task capability boundary and owned CLI gateway

```yaml
experiment_id: EXP-009
status: VALID
prior_experiment: EXP-008
hypothesis: Four explicit backend capabilities plus a fixed installed CLI gateway can expose batch, reachability, capture, and owned shutdown without weakening Teleop command safety.
prediction: RED fails because the task capability fields, task operation enum values, and CliTaskGateway do not exist.
single_variable: Add only Task 9 profile capability declarations, fixed operation specs, owned CLI task gateway, and unit tests.
lifecycle: RESET_WORLD
preconditions:
  - Source commit is 269b874b215ed45e29cfaeac23d8d3cb02e4d667.
  - Tests inject resolver/process/signal seams and do not start ROS or MuJoCo.
success_criteria:
  - Gazebo profiles report every task capability false.
  - MuJoCo reports task_batch, task_reachability, and sensor_capture true; task_environment_shutdown is true only for its supervisor-owned batch operation.
  - Gateway accepts typed requests, writes submitted YAML below an exclusive input directory, and launches a fixed argv with shell disabled and a new session.
  - A second active batch is rejected; status reads only its atomic manifest; cancellation signals only the owned PGID with bounded escalation.
  - Task service-facing gateway surface is limited to start_batch, status, cancel, and capture.
failure_criteria:
  - Caller-controlled executable or shell reaches subprocess, paths escape the evidence root, multiple batches run, or an unowned PID/PGID is signaled.
invalid_criteria:
  - Tests start a live ROS graph or depend on the current installed overlay.
provenance:
  source_commit: 269b874b215ed45e29cfaeac23d8d3cb02e4d667
  install_overlay: SOURCE_ONLY
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python
  ros_domain_id: NOT_STARTED
  gz_partition: NOT_STARTED
commands:
  - command: Run Task 9 profile and gateway RED tests.
    exit_code: 2
  - command: Run Task 9 focused profile, adapter, capability, and gateway tests.
    exit_code: 0
  - command: Run the complete Teleop test suite outside the process-inspection sandbox.
    exit_code: 0
observed:
  - Valid RED failed during collection because so101_teleop.task_gateway did not exist.
  - Focused GREEN passed 48 tests including one-active-batch exclusion, fixed argv, owned PGID cancellation, capture, and symlinked-manifest rejection.
  - The complete Teleop regression passed 225 tests; the first sandboxed attempt had two invalid recorder failures because macOS denied ps, and the unsandboxed rerun passed.
  - Gazebo task capabilities are all false; MuJoCo advertises batch, reachability, capture, and supervisor-owned shutdown with installed executable specs.
inferred:
  - TaskService can depend on four narrow asynchronous methods without acquiring arbitrary subprocess or filesystem access.
conclusion: The fixed CLI task owner boundary is source-valid and preserves all existing Teleop tests.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task9-red.log sha256=d70544d86cc01717038adcd988d64d70c50e1018618f9894eac466d3145a04ba
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task9-green.log sha256=784596e380d9b1652e6d0d2b9134ad7151abdfac997c1f9fa053e3d0554df9ea
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task9-teleop-regression-unsandboxed.log sha256=21c5d5a0712e6c3192bdcc351239a9ca011c7d974093f9cd83640d334d9cffd0
decision: KEEP
next_experiment: EXP-010
```

## CP-018 — Task 9 GREEN, commit pending

```yaml
checkpoint_id: CP-018
last_valid_experiment: EXP-009
current_hypothesis: A lease-gated TaskService and artifact sandbox can expose task lifecycle and evidence without weakening existing command routes.
working_tree_status: ledger plus Task 9 profiles, protocol, gateway, and tests are modified
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 9 focused tests pass 48 and complete Teleop regression passes 225.
disproven_routes:
  - Reading a manifest through a replaced symlinked batches directory is rejected.
open_risks:
  - No lease-gated task API, event stream, or artifact-serving sandbox exists yet.
next_command: git diff --check and commit the Task 9 paths.
```

## CP-019 — Task 9 committed

```yaml
checkpoint_id: CP-019
last_valid_experiment: EXP-009
current_hypothesis: A typed TaskService can reuse the current Teleop lease/session gate while isolating task events and manifest-only artifact reads.
working_tree_status: clean at ec342949d045894e7051473c8a638a9e987dd04f
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 9 is committed as ec34294 with no live process started.
disproven_routes:
  - NONE beyond prior checkpoints.
open_risks:
  - Task API idempotency, lease/session enforcement, event ordering, old-command lockout, and artifact containment are unimplemented.
next_command: Add Task 10 service, API, and artifact RED tests.
```

## EXP-010 — lease-gated task API and manifest artifact sandbox

```yaml
experiment_id: EXP-010
status: VALID
prior_experiment: EXP-009
hypothesis: One typed TaskService can own task lifecycle, events, and manifest-indexed artifacts while the existing Teleop service remains wire-compatible and rejects conflicting mutations.
prediction: RED fails because task models, TaskService, ManifestArtifactStore, /tasks routes, and the active-task mutation gate do not exist.
single_variable: Add only Task 10 models, service, routes, task binding, artifact store, generated OpenAPI, and tests.
lifecycle: RESET_WORLD
preconditions:
  - Source commit is ec342949d045894e7051473c8a638a9e987dd04f.
  - Tests use fake gateways and temporary evidence roots; no ROS or MuJoCo process starts.
success_criteria:
  - Start, reachability, cancel, recovery, capture, rendered image upload, and shutdown require a valid current lease/session and idempotent command ID.
  - One active task blocks old motion/reset/attachment/scene/workflow mutations while telemetry and evidence reads remain unchanged.
  - Browser refresh can read active/completed status and task events remain ordered through bounded queues.
  - Opaque artifact reads reject unknown IDs, traversal, absolute paths, symlinks, non-regular files, size/hash drift, and root escape.
  - Render uploads accept only bounded PNG bytes, finite view metadata, and a source PLY from the same capture.
failure_criteria:
  - A task starts without the lease/session gate, an old motion command overlaps, or a caller-selected path is served.
invalid_criteria:
  - Tests depend on live ROS, MuJoCo, or the old installed overlay.
provenance:
  source_commit: ec342949d045894e7051473c8a638a9e987dd04f
  install_overlay: SOURCE_ONLY
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python
  ros_domain_id: NOT_STARTED
  gz_partition: NOT_STARTED
commands:
  - command: Run Task 10 service, artifact, API, and safety RED tests.
    exit_code: 2
  - command: Run Task 10 focused gateway, service, artifact, API, safety, OpenAPI, and lifecycle tests.
    exit_code: 0
  - command: Run the complete Teleop regression outside the process-inspection sandbox.
    exit_code: 0
observed:
  - Valid RED failed during collection because task models, TaskService, and ManifestArtifactStore did not exist.
  - Focused GREEN passed 78 tests after the WebSocket disconnect path was changed to concurrently observe client closure; one deliberately hung test process was exact-stopped by PID without touching ROS or MuJoCo.
  - Complete Teleop regression passed 247 tests after task construction was gated to task-capable backends, preserving Gazebo lifecycle behavior.
  - Lease/session/capability gates, command idempotency, one-active-run ownership, old-command lockout, ordered bounded events, browser-refresh status, and confirmation-gated recovery/shutdown are covered.
  - Artifact reads require a registered opaque ID and verify containment, regular-file type, no symlinks, size, and SHA-256; rendered images require PNG magic, a same-capture PLY, bounded bytes, and finite view metadata.
  - Cancellation timeout retains both gateway ownership and the Teleop mutation lock instead of allowing an overlap with a still-running process.
inferred:
  - The new /tasks transport is isolated from existing /snapshot, /telemetry, /workflow, and legacy page route semantics.
conclusion: The Task 10 API/service/artifact boundary is source-valid and fail-closed; live installed behavior remains a Task 14/15 gate.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task10-red.log sha256=d0daa6b87ac70b7c58ce49363168f88d95d4497cc58f249e923b0ff68ced6e30
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task10-green.log sha256=57c79bb79898f044afbbc4118462df440cbbd1b0cce2132100997d82f9d28b31
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task10-teleop-regression.log sha256=92efa4158d4f8d666a268749f3ed844412b0c89aee52fd4ee15ae2f227aa3ded
decision: KEEP
next_experiment: EXP-011
```

## CP-020 — Task 10 GREEN, commit pending

```yaml
checkpoint_id: CP-020
last_valid_experiment: EXP-010
current_hypothesis: A separate /tasks frontend shell can consume the typed API without importing or altering prior Teleop page state.
working_tree_status: ledger plus Task 10 models, service, API, artifact store, task binding, generated OpenAPI, CMake test registration, and tests are modified
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 10 focused tests pass 78 and complete Teleop regression passes 247.
disproven_routes:
  - A WebSocket loop that waits only on task events cannot observe a quiet client disconnect and was replaced with concurrent disconnect observation.
  - Cancel timeout may not release task ownership or the old-command mutation lock.
open_risks:
  - The /tasks browser shell, free-point editor, reachability UX, and independent route-state tests do not exist yet.
next_command: git diff --check and commit Task 10, then write Task 11 Bun RED tests.
```

## CP-021 — Task 10 committed and Bun provenance

```yaml
checkpoint_id: CP-021
last_valid_experiment: EXP-010
current_hypothesis: The root module can dispatch /tasks to a separate controlled task builder without importing task state into the old App.
working_tree_status: clean at 52fdcf781d9e501ea28f42221b4956b1f40322d3
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
tool_provenance:
  bun_path: /Users/matianyi/.bun/bin/bun
  bun_version: 1.3.14
confirmed_conclusions:
  - Task 10 is committed as 52fdcf7.
  - Bun is locally available for all Task 11-13 frontend work; npm and npx are unnecessary.
disproven_routes:
  - NONE beyond prior checkpoints.
open_risks:
  - Task YAML validation, free-point ordering/editing, lease-driven actions, and route isolation are unimplemented.
next_command: Add Task 11 Bun RED tests for YAML and TaskBuilder.
```

## EXP-011 — separate task shell and free-point builder

```yaml
experiment_id: EXP-011
status: VALID
prior_experiment: EXP-010
hypothesis: Path dispatch plus controlled point editing can add the /tasks experience without modifying the existing App component or its state.
prediction: RED fails because TaskApp, TaskBuilder, task API types/client, and strict task YAML helpers do not exist.
single_variable: Add only Task 11 frontend task shell, editor, API client/types, YAML helpers, path dispatch, and Bun tests.
lifecycle: RESET_WORLD
preconditions:
  - Source commit is 52fdcf781d9e501ea28f42221b4956b1f40322d3.
  - Bun executable is /Users/matianyi/.bun/bin/bun version 1.3.14.
success_criteria:
  - /tasks renders TaskApp while / renders the byte-equivalent existing App import with no task state added to app.tsx.
  - Four server presets and arbitrary finite free points can be added, reordered, edited, and deleted without duplicate IDs.
  - Schema version 1 YAML round-trips in order and rejects non-finite XYZ, unknown fields, duplicate IDs, and invalid shapes.
  - Validate, start, cancel, recovery, capture, and shutdown remain disabled until a lease and current session exist.
failure_criteria:
  - Old App source/state changes, task input reaches fetch without local validation, or npm/npx is used.
invalid_criteria:
  - Tests depend on ROS, MuJoCo, browser filesystem APIs beyond injected File/Blob seams, or network package mutation.
provenance:
  source_commit: 52fdcf781d9e501ea28f42221b4956b1f40322d3
  install_overlay: SOURCE_FRONTEND_ONLY
  runtime_executable: /Users/matianyi/.bun/bin/bun
  ros_domain_id: NOT_STARTED
  gz_partition: NOT_STARTED
commands:
  - command: Run Task 11 YAML and TaskBuilder RED tests with Bun.
    exit_code: 1
  - command: Run Task 11 focused Vitest through Bun.
    exit_code: 0
  - command: Run the Bun production build.
    exit_code: 0
  - command: Run all Web unit/component tests through Bun.
    exit_code: 0
observed:
  - Valid RED failed because task-yaml and task-builder did not exist; the worktree-local dependencies were then installed from the frozen Bun lock without changing bun.lock.
  - Focused GREEN passed 7 tests for ordered schema round-trip, strict validation, preset/free-point editing, reorder, and duplicate-ID visibility.
  - Complete Web regression passed 52 tests across 16 files.
  - TypeScript and Vite production build succeeded; its existing greater-than-500-kB chunk warning remains non-fatal and will be revisited with the Three.js split in Task 12.
  - app.tsx has zero diff; main.tsx alone selects TaskApp for /tasks and the existing App otherwise.
inferred:
  - The new task workflow can evolve without coupling its state or controls to the established Teleop page.
conclusion: Task 11 is source-valid with strict free-point/YAML handling and a separately dispatched task shell.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task11-red.log sha256=2c57554172b65191f5c342682eb601030252c264c40ee5c9e165cdc2715b0d94
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task11-green.log sha256=47f860aefb88485d1baa3448aa54b97c7029b8cb74bdf0248d2faa610276a31f
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task11-build.log sha256=68ad732822b698212a9069f0bbd94b49bd63d98102db9739d1750cfa2c917cb2
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task11-web-regression.log sha256=69a2d20f1967910bfd31a20c52eb556f9a375aedc63198d8c127c0ac7b73fe0d
decision: KEEP
next_experiment: EXP-012
```

## CP-022 — Task 11 GREEN, commit pending

```yaml
checkpoint_id: CP-022
last_valid_experiment: EXP-011
current_hypothesis: Exact-pinned Three.js can render registered PLY evidence and save view-bound PNG metadata without weakening the artifact boundary.
working_tree_status: ledger plus Task 11 task types/client, YAML, builder, shell, path dispatch, and tests are modified
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 11 focused tests pass 7, full Web regression passes 52, and production build passes.
  - Existing app.tsx remains unchanged.
disproven_routes:
  - Direct bun test bypasses the repository Vitest setup; the accepted Bun-only command is bun run test.
open_risks:
  - No PLY viewer, current RGB-D capture view, or rendered-image upload exists yet.
next_command: git diff --check and commit Task 11, then add exact Three.js dependency and Task 12 RED tests.
```

## CP-023 — Task 11 committed and Three.js pinned

```yaml
checkpoint_id: CP-023
last_valid_experiment: EXP-011
current_hypothesis: Three.js PLYLoader and an injected renderer seam can provide deterministic point-cloud interaction and screenshot metadata without a CDN or server path exposure.
working_tree_status: package.json and bun.lock contain the planned exact Three.js dependencies after clean Task 11 commit 78f344de159612a05fcd0d0c57713cd96fae910f
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
dependency_provenance:
  three: 0.184.0 exact production dependency
  types_three: 0.184.0 exact development dependency
  installer: /Users/matianyi/.bun/bin/bun 1.3.14
confirmed_conclusions:
  - Task 11 is committed as 78f344d.
  - package-lock.json is absent and both Three.js packages are exact-pinned in bun.lock.
disproven_routes:
  - Initial sandboxed bun add could not write its temp directory; the approved Bun command succeeded outside that restriction.
open_risks:
  - WebGL lifecycle, deterministic >400000 point sampling, capture metadata, and artifact mapping are unimplemented.
next_command: Add Task 12 renderer and live-sensor RED component tests.
```

## EXP-012 — Three.js PLY viewer and synchronized current capture

```yaml
experiment_id: EXP-012
status: VALID
prior_experiment: EXP-011
hypothesis: A disposal-aware Three.js adapter can render registered full/cup PLY artifacts, deterministically bound display size, and upload a PNG bound to exact view/source metadata.
prediction: RED fails because PointCloudViewer and LiveSensor do not exist.
single_variable: Add only Task 12 exact dependencies, capture response metadata, viewer/live-sensor components, task-shell placement, and tests.
lifecycle: RESET_WORLD
preconditions:
  - Source commit is 78f344de159612a05fcd0d0c57713cd96fae910f.
  - Tests inject renderer and API seams; no WebGL context, ROS, camera, or network is used.
success_criteria:
  - Full and cup PLY load by opaque artifact ID; RGB/full/cup metadata share one capture/source stamp.
  - Original PLY remains unchanged; display uses all points up to 400000 and fixed stride above it with exact counts recorded.
  - Screenshot forces a render and uploads PNG plus source ID/SHA, matrices, viewport, point size, color/background, count, and sampling metadata.
  - Capture change and unmount dispose geometry, materials, controls, renderer, object URLs, and animation resources.
  - Production bundle contains pinned local Three.js code and no CDN reference.
failure_criteria:
  - Viewer accepts a filesystem path, silently downsamples without metadata, reuses stale capture, leaks renderer resources, or uploads non-source-bound PNG.
invalid_criteria:
  - Tests require GPU/WebGL, live topics, a browser download, or npm/npx.
provenance:
  source_commit: 78f344de159612a05fcd0d0c57713cd96fae910f
  install_overlay: SOURCE_FRONTEND_ONLY
  runtime_executable: /Users/matianyi/.bun/bin/bun
  ros_domain_id: NOT_STARTED
  gz_partition: NOT_STARTED
commands:
  - command: Run Task 12 viewer and live-sensor RED tests through Bun.
    exit_code: 1
  - command: Run all Web tests through Bun after implementation.
    exit_code: 0
  - command: Run the TypeScript and Vite production build through Bun.
    exit_code: 0
  - command: Run Teleop Python plus RGB-D snapshot regression from the source overlay.
    exit_code: 0
observed:
  - RED failed on the two absent component modules.
  - Web regression passed 56 tests across 18 files; the production build passed with only the known non-fatal bundle-size warning.
  - Python regression passed 131 tests and retained only existing deprecation warnings.
  - Capture responses expose manifest descriptors, SHA-256, exact source stamp, and cup-center metadata; rendered PNG registration validates same-capture PLY provenance and view/sampling metadata.
  - The local exact Three.js 0.184.0 PLYLoader renders full/cup clouds, displays axes and the computed center, bounds display to 400000 points using recorded fixed stride, and disposes its renderer resources.
inferred:
  - Current RGB-D evidence can be inspected and saved in the isolated task page without filesystem disclosure, CDN code, or a MuJoCo restart.
conclusion: Task 12 is source-valid and production-build-valid.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task12-red.log sha256=3cff059038fc500d8b4cc1100d3602f3ef99b110f38f7f1b708070170b134ec3
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task12-web-green.log sha256=02a25917257e47f2b1b886cef066b6ed8301a06af11100c31ed99a289f7f6fab
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task12-web-build.log sha256=edba38316e2e571f22aa7c0f1757a3a1564b541131b5a9f1c1281e808fbeb686
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task12-python-green.log sha256=9271699a928309b3312e21fec72c1afd94b4ef74fdaf7824f1ba6069b76b2d30
decision: KEEP
next_experiment: EXP-013
```

## CP-024 — Task 12 GREEN, commit pending

```yaml
checkpoint_id: CP-024
last_valid_experiment: EXP-012
current_hypothesis: Existing task events and point summaries can drive a reconnect-safe progress and evidence browser without polling filesystem state.
working_tree_status: Task 12 RGB-D capture metadata, Three.js viewer, live sensor panel, generated API, tests, and ledger are modified
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 12 passes 56 Web tests, production build, and 131 Python/RGB-D tests.
  - No npm/npx, CDN, WebGL test dependency, or live ROS process was used.
open_risks:
  - Run events are not yet rendered live and per-point evidence artifacts are not yet browsable from the task page.
next_command: Commit Task 12, then add Task 13 progress/evidence RED tests.
```

## EXP-013 — Reconnect-safe progress and per-point evidence browser

```yaml
experiment_id: EXP-013
status: VALID
prior_experiment: EXP-012
hypothesis: Event-triggered authoritative status refresh plus artifact summaries can restore ordered progress and expose evidence without leaking paths.
prediction: RED fails because TaskProgress, EvidenceBrowser, and point artifact summaries do not exist.
single_variable: Add Task 13 progress, reconnect, evidence presentation, and isolated page E2E only.
lifecycle: RESET_WORLD
preconditions:
  - Source commit is 54b85146ec1d8e4ce7166161c4ae781d66ce9063.
  - Browser tests mock HTTP task state and do not start ROS or MuJoCo.
success_criteria:
  - Refresh/reconnect restores the active/latest run and refetches authoritative status after event connection.
  - Failed or unreachable points remain ordered and later successful points remain visible.
  - Evidence links use only /tasks/artifacts opaque IDs; response models contain basenames and hashes but no paths.
  - Existing / Teleop E2E remains green beside the separate /tasks page.
failure_criteria:
  - WebSocket frames become authoritative state, retries spin unbounded, filesystem paths reach the browser, or existing Teleop controls regress.
invalid_criteria:
  - E2E requires live ROS/MuJoCo or modifies pre-existing mrc010 processes.
commands:
  - command: Run TaskProgress, EvidenceBrowser, and TaskPointSummary RED tests.
    exit_code: 1
  - command: Run all Web unit tests and production build.
    exit_code: 0
  - command: Run complete macOS Chrome Playwright suite for / and /tasks.
    exit_code: 0
  - command: Run Teleop Python regression after OpenAPI regeneration.
    exit_code: 0
observed:
  - RED failed on both absent Web modules and the absent point artifacts field.
  - Web regression passed 59 tests across 21 files and the production bundle built successfully.
  - macOS Chrome E2E passed all 10 scenarios, including task refresh, failure/unreachable continuation presentation, evidence links, and all existing Teleop scenarios.
  - Teleop Python regression passed 128 tests; generated OpenAPI contains the path-free artifact summary contract.
  - WebSocket retry starts at 250 ms, caps at 4000 ms, refetches run state after every open, and cancels its socket/timer on unmount.
inferred:
  - Task progress is reconnect-safe and the separate task page does not regress the existing Teleop page.
conclusion: Task 13 is source-, build-, and browser-E2E-valid.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task13-red.log sha256=923bd28a115e72ebad1790feae344b341f6fb84c4abf801c12c9793a59b8ba00
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task13-web-green.log sha256=c75b5ee71638d3639a4b03eefaf15492adec8665ee57a2389f9dec2e0dc70b84
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task13-web-build.log sha256=401d2454c06e3adddc1a065960fe787fb3b6b126a1d24bd318f1cd265d8f809c
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task13-e2e-green.log sha256=b8ea3847f2c7bbbe23ccacfb03aaa98176d5c09219fc151af3f4806ce9e8f4e6
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task13-python-green.log sha256=9ac127a59c51fbe13921fa8a0e3f2b960e9658dd5a2611397c39cea3a12efc15
decision: KEEP
next_experiment: EXP-014
```

## CP-025 — Task 13 GREEN, commit pending

```yaml
checkpoint_id: CP-025
last_valid_experiment: EXP-013
current_hypothesis: A clean isolated candidate overlay will close package/install provenance and reveal any remaining installed-entrypoint defects before live qualification.
working_tree_status: Task 13 progress, reconnect client, path-free artifact summaries, evidence browser, macOS Playwright config, tests, generated API, and ledger are modified
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Task 13 passes 59 Web tests, 128 Python tests, production build, and 10 macOS Chrome E2E tests.
open_risks:
  - Installed ROS package closure and candidate-overlay provenance remain unverified.
next_command: Commit Task 13, then execute Task 14 source/package/install/provenance gates.
```

## EXP-014 — full source, candidate install, and provenance qualification

```yaml
experiment_id: EXP-014
status: VALID
prior_experiment: EXP-013
hypothesis: The complete task-station implementation is source-green and resolves every required runtime entry point from one isolated macOS candidate overlay built against mujoco_ros2_control 0.1.0.
prediction: Focused install contracts, complete Python/Web suites, the production bundle, candidate build, installed tests, and launch introspection all pass without resolving the fork from the parent/default overlay.
single_variable: Add Task 14 packaging/provenance assertions and documentation; do not change runtime behavior.
lifecycle: NOT_STARTED
preconditions:
  - Runtime source commit is 0d8a3a6f3dd58e5aaa4deb76b209378f3146b4c2.
  - mujoco_ros2_control submodule commit is 5e9d67ce9fde39d35bf94cc498721abf203a0ddd and every fork package version is 0.1.0.
  - Registered evidence root is /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827.
success_criteria:
  - Complete so101_demo_py and so101_teleop source suites collect non-zero tests and pass.
  - Complete Vitest suite and production bundle pass using Bun 1.3.14.
  - Candidate prefix contains the batch, reachability, sensor-capture, task-station launch, preset YAML, task page, and exact Three.js dependencies.
  - so101_demo_py, so101_teleop, mujoco_ros2_control, plugins, messages, and 3d_lidar resolve from the candidate prefix; all fork package versions are 0.1.0.
  - Installed provenance tests and launch --show-args pass from the candidate overlay.
failure_criteria:
  - Zero tests collected, source-only entry point, parent/default fork resolution, stale package version, or missing runtime resource.
invalid_criteria:
  - A raw bun test run that bypasses Vitest configuration, a source test run against the old default install, or macOS CTest with a corrupted DYLD_LIBRARY_PATH is not a qualifying product result.
provenance:
  source_commit: 0d8a3a6f3dd58e5aaa4deb76b209378f3146b4c2
  submodule_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
  install_overlay: /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/install
  build_base: /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/build
  ros_domain_id: NOT_STARTED
commands:
  - command: Run focused source install-contract tests.
    exit_code: 0
  - command: Run complete so101_demo_py source suite in the selected direnv/candidate environment.
    exit_code: 0
  - command: Run complete so101_teleop source suite outside the process-enumeration sandbox.
    exit_code: 0
  - command: Run the complete Vitest suite through bun run test.
    exit_code: 0
  - command: Run the TypeScript and Vite production build through Bun.
    exit_code: 0
  - command: Build the dependency-closed candidate with merge-install, explicitly skipping only locked macOS mujoco_vendor.
    exit_code: 0
  - command: Run installed provenance tests with SO101_DEMO_EXPECTED_PREFIX bound to the candidate.
    exit_code: 0
  - command: Record package prefixes, executable realpaths/stats, package XML hashes, submodule SHA, versions, and launch --show-args.
    exit_code: 0
observed:
  - so101_demo_py passed 530 tests; so101_teleop passed 250 tests; Vitest passed 59 tests across 21 files; the production bundle built successfully with only the existing non-fatal chunk-size warning.
  - The dependency-closed candidate built 7 packages in 95.8 seconds: fork core/plugins/messages/3d_lidar, so101_mujoco_support, so101_demo_py, and so101_teleop.
  - mujoco_vendor was not rebuilt because the repository macOS environment supplies its locked staged headers and dylibs from the selected main underlay; no fork runtime package was reused from that underlay.
  - Installed provenance passed 4 tests and launch argument introspection showed headless=false plus the four supported initial keyframes.
  - A direct bun test invocation failed because Bun's native runner ignored Vitest jsdom and collected Playwright files; bun run test is the repository contract and passed.
  - An additional colcon test attempt is non-qualifying: CTest emitted repeated append-env DYLD_LIBRARY_PATH assignments that collapsed to incomplete library lookup and rclpy could not load librosidl_typesupport_c.dylib. The same tests pass in the verified direnv shell, so this is retained as a macOS CTest harness limitation rather than converted into a product pass.
inferred:
  - The selected install is a complete, locally bundled task-station candidate with explicit 0.1.0 fork provenance; source and installed-runtime evidence are independently green.
conclusion: Task 14 is source-, Web-, package-, install-, and provenance-valid; visible physical qualification remains Task 15.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task14-demo-source-green.log sha256=33ff758dfa71b0727969b3d526f546245f6060365949540b40bcfa827fc06842
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task14-teleop-source-green.log sha256=ea875985082fab160938fd9e06ba6144c8b7a39cc54af062eaef236a8ca37c24
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task14-web-vitest-green.log sha256=c21c27ad48bf3763a9ac6c1f10aafbbe89456836879f73cf930b233b3685084b
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task14-web-build-green.log sha256=babebb63088df147e66e9f965fd61422d2fd171add9e283519989fc8de54941f
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/colcon-log/build_2026-08-27_15-02-05/logger_all.log sha256=d5d29d9739182c4d5c5d85595662ec773b10c372dd4a292719821d9a0169b89e
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task14-installed-tests-green.log sha256=b354845c1e7b877d6fce29971f341f6719cafc886ee0c5f7d940103175fa1492
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task14-installed-provenance.log sha256=fb291051f374e13010ddafedaf70b9674334a4303a66c1f6e20cd00f538ce808
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task14-colcon-test-green.log sha256=9fe9e5451d59a77a29f7b7031d0ca3f68eda2147ed7bc21868065186cdccef36 non-qualifying harness evidence
decision: KEEP
next_experiment: EXP-015
```

## CP-026 — Task 14 GREEN, visible runtime pending

```yaml
checkpoint_id: CP-026
last_valid_experiment: EXP-014
current_hypothesis: The exact candidate overlay can complete one visible four-preset RESET_WORLD batch and continue from an unreachable point to a later reachable point while retaining inspectable macOS evidence.
working_tree_status: Task 14 install/provenance tests, teaching guide, and ledger are committed; runtime source is unchanged from candidate commit 0d8a3a6.
owned_processes: NONE
preserved_processes: Pre-existing mrc010 tmux sessions and server process remain untouched.
confirmed_conclusions:
  - Complete source suites pass 530 and 250 tests; Web passes 59 tests and production build; installed provenance passes 4 tests.
  - Candidate runtime and all mujoco_ros2_control fork packages resolve from the isolated merge-install prefix at version 0.1.0.
open_risks:
  - Real visible Viewer capture, four-point physical success, unreachable continuation, task-page live capture, and owned cleanup have not run at this checkpoint.
next_command: Read the gui-capture skill, inventory live state, and start Task 15 with a unique ROS domain and session.
```

## EXP-015 — visible persistent RESET_WORLD runtime qualification

```yaml
experiment_id: EXP-015
status: VALID
prior_experiment: EXP-014
hypothesis: One visible macOS MuJoCo/MoveIt stack can complete all four approved RGB-D cup points through atomic RESET_WORLD, and a deterministically unreachable point can be skipped before motion without blocking a later reachable point.
prediction: The four-point batch succeeds with one simulation session and epochs 1..4; a second batch records SKIPPED_UNREACHABLE without reset, then succeeds at task_start with epoch 1.
single_variable: Exercise the already packaged task-station runtime and apply only defects exposed by physical/runtime evidence.
lifecycle: RESET_WORLD
preconditions:
  - Source runtime commit is 137cfd9 after correcting the RGB-D startup flag exposed by diagnostic run r17.
  - Candidate overlay is /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/install.
  - mujoco_ros2_control child is 5e9d67ce9fde39d35bf94cc498721abf203a0ddd and all six package versions are 0.1.0.
  - Viewer is launched with headless=false; pre-existing mrc010 tmux sessions remain out of scope.
success_criteria:
  - Four presets succeed in order in one persistent session with reset epochs exactly 1, 2, 3, 4.
  - Every successful point records aligned RGB-D/perception, dynamic DONE/19, terminal physical evidence, and registered artifacts.
  - A target whose derived TCP exceeds the safe workspace is skipped before reset or motion, and the next reachable point succeeds.
  - Exact-window GUI evidence, full source/Web suites, installed provenance, and owned-process cleanup are independently verified.
failure_criteria:
  - Full restart between presets, stale/non-monotonic epoch, hidden MJCF-truth perception fallback, unsafe continuation, missing terminal evidence, or unresolved fork package outside the candidate.
invalid_criteria:
  - Runs r16 and r17 are diagnostic rather than qualification: r16 exposed transient controller/perception timing; r17 used a wrong newly added RGB-D CLI flag and failed before perception.
provenance:
  source_commit: 137cfd9
  submodule_commit: 5e9d67ce9fde39d35bf94cc498721abf203a0ddd
  child_package_versions: 0.1.0
  install_overlay: /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/install
  four_point_batch: /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task15-four-r18/batches/mac-rgbd-task15-four-r18-20260827/batch-result.json
  continuation_batch: /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task15-unreachable-r20/batches/mac-rgbd-task15-unreachable-r20-20260827/batch-result.json
commands:
  - command: Run visible four-preset batch r18 through so101_mujoco_rgbd_batch against the candidate overlay.
    exit_code: 0
  - command: Run r20 with a derived-TCP-outside-workspace point followed by task_start.
    exit_code: 1
    note: Expected aggregate failure because one requested point is skipped; continuation behavior passed.
  - command: Run complete so101_demo_py source suite from the candidate environment.
    exit_code: 0
  - command: Run complete so101_teleop source suite outside the process-enumeration sandbox.
    exit_code: 0
  - command: Run complete Vitest suite and production build.
    exit_code: 0
  - command: Run installed provenance tests with the expected candidate prefix.
    exit_code: 0
observed:
  - r18 batch status is SUCCEEDED with first_shared_failure=null; task_start, forward, left, and right are SUCCEEDED at reset epochs 1, 2, 3, and 4.
  - Each r18 point has 9 registered artifacts and dynamic DONE/19; perceived-center errors are 0.644, 0.594, 0.690, and 0.631 mm; final placement XY errors are 2.631, 2.458, 2.510, and 2.495 mm.
  - r18 did not use the narrow CONTROL_FAILED reconciliation path; all execution_reconciliations arrays are empty.
  - r20 point tcp_above_safe_workspace is SKIPPED_UNREACHABLE/TARGET_RESOLUTION_FAILED before reset and motion; task_start_after_skip then succeeds at epoch 1 with 9 artifacts and DONE/19.
  - r20 aggregate status is FAILED by design, but first_shared_failure=null proves the persistent stack stayed healthy for continuation.
  - The exact MuJoCo window capture is 2504x1770, bound to window ID 46798 and PID 59349; the point run associated with that live stack later reached DONE.
  - Final candidate suites pass: so101_demo_py 549 tests, so101_teleop 250 tests, Vitest 59 tests across 21 files, production build, and installed provenance 4 tests.
  - One earlier parallel test attempt resolved the parent overlay and one sandboxed Teleop attempt denied ps; corrected candidate/outside-sandbox reruns passed and are the qualifying results.
inferred:
  - The persistent macOS workflow now proves the complete MuJoCo -> aligned RGB-D -> point cloud -> tf2 -> /cup_pose -> dynamic state machine -> MoveIt -> controller -> MuJoCo loop at all four approved starting positions.
  - Reachability is enforced on derived TCP phases, not just user-entered cup XYZ, and point-local rejection does not corrupt the shared environment.
conclusion: Task 15 is physically, visually, source-, Web-, install-, and provenance-qualified on macOS for the four presets and deterministic unreachable continuation.
evidence:
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task15-four-r18/batches/mac-rgbd-task15-four-r18-20260827/batch-result.json sha256=f544339ffd84ba3305fac07ed031d369c1178fb2e2973dbce4d810a1b0d04664
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task15-unreachable-r20/batches/mac-rgbd-task15-unreachable-r20-20260827/batch-result.json sha256=a4ca24e3769bb6d75f80c44e1d7f96d7a8551cb1a5262b4744471c68e45492e0
  - /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827/task15-gui/r14-live/window.png sha256=1f8b7fd6d51ca3d5d5e07e201586a9961a57f7e109ef4df61434daf33dfd08f7
decision: KEEP
next_experiment: NONE
```

## CP-027 — Task 15 qualified and ready to integrate

```yaml
checkpoint_id: CP-027
last_valid_experiment: EXP-015
current_hypothesis: The qualified branch can be integrated into main without changing its runtime provenance or evidence record.
working_tree_status: Runtime source is committed at 137cfd9; only this final guide and ledger update remain before integration.
owned_processes: NONE
preserved_processes: Pre-existing tmux sessions mrc010-exp013-final-stack and mrc010-exp013-smoke-r3 remain untouched.
confirmed_conclusions:
  - A single visible macOS stack completed all four approved RGB-D RESET_WORLD points at epochs 1..4.
  - Derived-TCP reachability rejected an unsafe target before motion and the following point succeeded.
  - Candidate source, Web, bundle, installed provenance, physical evidence, and exact-window evidence all pass their separate gates.
retention:
  retained_root: /tmp/so101-debug-macos-rgbd-reset-world-task-ui-20260827
  retained_runs: All r2-r20 diagnostic and qualifying runs remain present; r18 and r20 are the final authoritative batch results.
  archived_runs: NONE
  deletion_candidates: Superseded diagnostic runs r2-r17 and r19 may be reviewed for deletion later, but none is deleted without explicit user authorization.
open_risks:
  - Temporary evidence under /tmp is not durable across machine cleanup; copy it to the repository-approved durable evidence hierarchy before relying on long-term retention.
next_command: Commit documentation, execute final branch verification, merge to local main, push origin, and verify remote ref parity.
```
