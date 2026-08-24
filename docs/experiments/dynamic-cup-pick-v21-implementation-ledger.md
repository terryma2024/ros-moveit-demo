# Dynamic Cup Pick V2.1 Implementation Ledger

```yaml
task_id: dynamic-cup-pick-v21-20260823
goal: Implement separately runnable fixed and perception-driven cup-pick entry points with dynamic execution hard-disabled.
success_contract: V1 remains behavior-compatible; V2 acquires one valid world-frame cup pose, resolves complete dynamic targets, produces plan-only evidence, and never falls back or executes.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo
branch: main
base_commit: 5407592100823bcfa43138611f8de6b0de0c93f8
current_commit: 5407592100823bcfa43138611f8de6b0de0c93f8
evidence_root: /tmp/so101-debug-dynamic-cup-pick-v21-20260823
install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py
runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py/lib/so101_demo_py/{fixed_cup_pick_place,dynamic_cup_pick_place}
ros_domain_id: unset
gz_partition: unset
confirmed_conclusions:
  - Fixed joint waypoints and perception-driven TCP targets require separate strategy providers.
  - Dynamic V2.1 execute must remain hard-disabled until a separately qualified bundle exists.
  - Both strategies must reuse StateMachineRunner and SO101_WORKFLOW rather than add another state machine.
disproven_routes:
  - Preplanning multiple TCP segments from the same live joint state.
  - Reusing the simplified backends/gazebo/workflow.py as the dynamic orchestration contract.
open_hypotheses:
  - Pure target resolution plus an injected plan-only planner can establish the V2.1 boundary locally before live MoveIt qualification.
latest_checkpoint: DCP-V21-CP-002
next_experiment: live Gazebo/MoveIt single-state plan-only qualification when an inventoried stack is available
```

```yaml
checkpoint_id: DCP-V21-CP-001
recorded_at: 2026-08-23 Asia/Shanghai
last_valid_experiment: NONE
current_hypothesis: A shared state-machine contract with separate motion target providers preserves V1 while enabling fail-closed V2 plan-only.
working_tree_status:
  - docs/experiments/dynamic-cup-pick-v21-implementation-ledger.md (task-owned)
owned_processes: NONE
preserved_processes: Process enumeration unavailable in the restricted local environment; no ROS, Gazebo, MoveIt, RViz, or tmux process will be started or stopped before explicit runtime inventory.
confirmed_conclusions:
  - Source baseline is 5407592100823bcfa43138611f8de6b0de0c93f8 on main.
  - ROS_DOMAIN_ID and GZ_PARTITION are unset in the current shell.
disproven_routes:
  - NONE beyond the design-review conclusions above.
open_risks:
  - colcon and ros2 are not visible in the current non-direnv shell.
next_command: Add RED tests for strategy entry points and dynamic target/input contracts.
```

```yaml
experiment_id: DCP-V21-EXP-001
status: VALID
prior_experiment: NONE
hypothesis: The reviewed V2.1 boundary can be expressed with pure target/input contracts and two isolated public entry points without changing V1 behavior.
prediction: New tests fail before implementation and pass after adding the providers, dynamic plan-only composition, configuration, and entry points.
single_variable: source implementation at fixed baseline 5407592100823bcfa43138611f8de6b0de0c93f8
lifecycle: REUSE_STACK
preconditions:
  - No runtime or robot process is started by this experiment.
  - Existing fixed policy files remain byte-identical.
success_criteria:
  - RED tests fail for missing V1/V2 contracts, then pass after implementation.
  - Dynamic execute is rejected before ROS subscription, scene mutation, planning, gripper, or attachment work.
  - Invalid messages do not extend the absolute acquisition deadline and never provide a fallback pose.
failure_criteria:
  - V1 imports ROS/dynamic modules or changes the fixed policy bundle.
  - V2 can execute or fall back to fixed waypoints.
invalid_criteria:
  - Tests run against a different source checkout or unrecorded overlay.
provenance:
  source_commit: 5407592100823bcfa43138611f8de6b0de0c93f8
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py
  runtime_executable: source tree during RED/GREEN
  ros_domain_id: unset
  gz_partition: unset
commands:
  - command: direnv exec . python -m pytest -q <four initial dynamic test modules>
    exit_code: 1
    result: RED, 12 expected failures for missing modules and entry points
  - command: direnv exec . python -m pytest -q <targeted dynamic and compatibility tests>
    exit_code: 0
    result: 31 passed in 0.24s
  - command: direnv exec . colcon build --packages-select so101_demo_py --symlink-install
    exit_code: 0
    result: 1 package finished in 5.41s
  - command: ROS_LOG_DIR=<evidence>/ros-log direnv exec . python -m pytest -q src/so101_demo_py/test --junitxml=<evidence>/package-pytest-final.xml
    exit_code: 0
    result: 236 passed in 8.24s
  - command: ROS_LOG_DIR=<evidence>/ros-log direnv exec . colcon test --packages-select so101_demo_py --event-handlers console_direct+
    exit_code: 2
    result: pytest selected correctly after replacing ignored tests_require metadata, but the colcon child environment omits DYLD_LIBRARY_PATH and cannot load librosidl_typesupport_c.dylib during collection
  - command: direnv exec . ros2 run so101_demo_py fixed_cup_pick_place --mode dry_run
    exit_code: 0
    result: DONE after 19 transitions
  - command: direnv exec . ros2 run so101_demo_py dynamic_cup_pick_place --mode execute --execute
    exit_code: 1
    result: expected DYNAMIC_EXECUTION_NOT_QUALIFIED before ROS initialization
  - command: ROS_LOG_DIR=<evidence>/ros-log direnv exec . ros2 run so101_demo_py dynamic_cup_pick_place --mode plan_only --plan-only-state MOVE_ABOVE_OBJECT --cup-pose-timeout-s 0.2 --evidence-file <evidence>/no-message-plan.json
    exit_code: 1
    result: expected CUP_POSE_TIMEOUT with no fallback evidence file
observed:
  - RED/GREEN established the new contracts without changing the baseline commit identity.
  - Installed package prefix is /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py.
  - ros2 pkg executables lists fixed_cup_pick_place and dynamic_cup_pick_place and no longer lists the generic pick_place entry.
  - Installed dynamic policy loads as dynamic_cup_pick with SHA f1d47b8780dce642d78b8de00865cb66b1fdbea5ce076bfb71805f5c82842d19.
  - V1 fixed policy SHA values remain aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356 for Gazebo/MuJoCo and e5a96cc1c78049095415c3569c1fd153585188451b6a62230c10a3ecd7a4be62 for real_stub.
  - A stale generated install/lib/so101_demo_py/pick_place script from the old entry point was removed after its regenerated egg-info proved it was no longer published.
  - colcon now selects pytest through extras_require.test, but colcon test is still not a valid package-test signal in this macOS shell: its child command omits DYLD_LIBRARY_PATH and fails to load librosidl_typesupport_c.dylib. Direct pytest in the same direnv passes all 236 tests.
inferred:
  - Pure target resolution and the installed CLI checks establish the V2.1 fail-closed boundary, but do not establish a successful live MoveIt plan.
conclusion: Source, build, installed-entry, V1 dry-run, V2 execute-rejection, and no-message fail-closed acceptance passed. Live Gazebo/MoveIt plan-only remains deliberately unqualified because no runtime stack was inventoried or started.
evidence:
  - /tmp/so101-debug-dynamic-cup-pick-v21-20260823/red-targeted.log
  - /tmp/so101-debug-dynamic-cup-pick-v21-20260823/green-targeted.log
  - /tmp/so101-debug-dynamic-cup-pick-v21-20260823/colcon-build.log
  - /tmp/so101-debug-dynamic-cup-pick-v21-20260823/package-pytest-final.xml
decision: ACCEPT V2.1 implementation boundary; do not claim live plan or execute qualification.
next_experiment: DCP-V21-EXP-002 live Gazebo/MoveIt single-state plan-only qualification
```

```yaml
checkpoint_id: DCP-V21-CP-002
recorded_at: 2026-08-23 Asia/Shanghai
last_valid_experiment: DCP-V21-EXP-001
current_hypothesis: The installed V2.1 path will plan one selected TCP state when an existing Gazebo/MoveIt stack reports mutually consistent cup poses.
working_tree_status:
  - task-owned source, tests, policy, design, plan, and ledger are uncommitted on main
owned_processes: NONE
preserved_processes: No ROS, Gazebo, MoveIt, RViz, or tmux process was started or stopped.
confirmed_conclusions:
  - fixed_cup_pick_place preserves the V1 dry-run state trace.
  - dynamic_cup_pick_place rejects execute and times out without fallback.
  - package pytest passes 236 tests and colcon build installs both named executables.
disproven_routes:
  - Treating an incremental install directory as self-cleaning; the retired pick_place script required explicit generated-artifact cleanup.
  - Wrapping ROS Python verification in a second system zsh or the current colcon child test environment on macOS; both omit the required DYLD lookup path.
open_risks:
  - A live Gazebo/MoveIt scene has not yet exercised the two scene gates and GetMotionPlan adapter.
  - The dynamic template remains CALIBRATION_REQUIRED and execution_allowed is false.
next_command: Inventory an existing Gazebo/MoveIt stack before running DCP-V21-EXP-002.
```
