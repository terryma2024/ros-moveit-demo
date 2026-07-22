# DESCEND Cartesian Planner and Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement collision-aware Cartesian DESCEND planning/execution and its complete transition contract through the CLOSE_GRIPPER boundary.

**Architecture:** A dedicated ROS adapter owns DESCEND planning and execution, while pure core validation checks Cartesian-path evidence without MoveIt dependencies. The existing state-bound `DescendToCloseGripperValidator` owns both completion and resume semantics, and a generic runner observation sink exposes pre/post physical snapshots for structured logs.

**Tech Stack:** C++17, ROS 2 Jazzy, MoveIt 2 MoveGroupInterface/GetCartesianPath, GoogleTest, ament/colcon.

## Global Constraints

- Use `computeCartesianPath` with `avoid_collisions=true`; never execute a partial path.
- Defaults are `descend_eef_step=0.005`, `descend_min_fraction=0.99`, and `descend_joint_jump_threshold=0.2` radians.
- Enforce joint jumps manually because ROS 2 Jazzy ignores the deprecated Cartesian API jump argument.
- Keep `MoveAboveObjectPlanner` and `DescendPlannerExecutor` independent.
- Use `DescendToCloseGripperValidator` for both post-execution and resume validation.
- Do not register a `CLOSE_GRIPPER` executor in this phase.
- Never run `ament_uncrustify --reformat`.

---

### Task 1: Pure Cartesian plan validation

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/cartesian_plan_validation.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/cartesian_plan_validation.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Test: `src/panda_gazebo_demo/test/pick_place/test_pick_place_core.cpp`

**Interfaces:**
- Consumes: `Pose3d`, `positionDistance`, and `orientationDistance`.
- Produces: `CartesianPlanEvidence`, `CartesianPlanLimits`, and `validateCartesianPlan(...) -> ValidationResult`.

- [ ] **Step 1: Write failing tests for accepted vertical descent and every rejection gate**

Add tests that construct path TCP poses and adjacent joint deltas, then assert exact failure codes
for low fraction, empty trajectory, excessive joint jump, lateral motion, rising motion, orientation
drift, and wrong endpoint.

- [ ] **Step 2: Run the focused test binary and confirm RED**

Run: `colcon build --packages-select panda_gazebo_demo && ./build/panda_gazebo_demo/test_pick_place_core --gtest_filter='CartesianPlanValidation.*'`

Expected: compilation fails because the validation header/API does not exist.

- [ ] **Step 3: Implement the minimal pure validation function**

Compute metrics `cartesian_fraction`, `trajectory_points`, `max_joint_delta`,
`max_lateral_deviation`, `max_orientation_error_rad`, `planned_tcp_position_error`, and
`planned_tcp_orientation_error_rad`; return the exact tested failure code for each violated gate.

- [ ] **Step 4: Rebuild and confirm the focused tests pass**

Run the Task 1 focused command again. Expected: all `CartesianPlanValidation.*` tests pass.

### Task 2: DESCEND transition validation

**Files:**
- Modify: `src/panda_gazebo_demo/src/pick_place/transition_contract.cpp`
- Test: `src/panda_gazebo_demo/test/pick_place/test_pick_place_core.cpp`

**Interfaces:**
- Consumes: shared `PickPlaceTargetPolicy` targets for both adjacent transitions.
- Produces: complete `DescendToCloseGripperValidator` pre/post/resume semantics.

- [ ] **Step 1: Write failing precondition and postcondition tests**

Assert that DESCEND pre-validation rejects a TCP not at the MOVE_ABOVE target and records position
and orientation errors. Assert that post-validation rejects Gazebo Coke rotation and accepts a valid
stationary descent with open gripper and detached, consistent Coke.

- [ ] **Step 2: Run `TransitionContracts.Descend*` and confirm RED**

Expected: the displaced starting TCP and rotated Coke are currently accepted.

- [ ] **Step 3: Extend `DescendToCloseGripperValidator` through shared helpers**

Resolve the MOVE_ABOVE target during pre-validation and apply 6-DoF start checks. Extend common
motion completion with Coke orientation drift and state-neutral failure messages/codes.

- [ ] **Step 4: Re-run the focused transition tests and confirm GREEN**

Expected: all DESCEND transition tests pass, including resume through the same validator.

### Task 3: Generic pre/post observation trace

**Files:**
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/runner.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/runner.cpp`
- Modify: `src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp`
- Test: `src/panda_gazebo_demo/test/pick_place/test_pick_place_core.cpp`

**Interfaces:**
- Produces: `IExecutionObservationSink::record(State, const WorldSnapshot &, const WorldSnapshot &)` and an optional constructor injection into `StateMachineRunner`.

- [ ] **Step 1: Write a failing runner test using a recording sink**

Execute one successful fake state action and assert that the sink receives the exact before/after
snapshots once, after the post-action observation and before checkpoint completion.

- [ ] **Step 2: Run the focused runner test and confirm RED**

Expected: compilation fails because no sink interface or constructor argument exists.

- [ ] **Step 3: Add the optional generic sink and ROS INFO logger implementation**

Do not re-observe. In the node, log Gazebo pose fields and RPY under `COKE_POSE_BEFORE` and
`COKE_POSE_AFTER`; log an explicit unavailable message if either optional pose is absent.

- [ ] **Step 4: Re-run the focused runner test and confirm GREEN**

Expected: the sink receives one matching pair and existing runner tests remain compatible via the
default null sink.

### Task 4: DescendPlannerExecutor ROS adapter

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/descend_planner_executor.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/descend_planner_executor.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Modify: `src/panda_gazebo_demo/package.xml`

**Interfaces:**
- Consumes: `PickPlaceTargetPolicy`, Cartesian validation API, MoveIt current state/model, scaling and DESCEND parameters.
- Produces: `DescendPlannerExecutor : IStatePlanner, IStateExecutor` and a private MoveIt trajectory artifact.

- [ ] **Step 1: Add compile-time/API tests for the adapter contract where practical**

Use static assertions for the planner/executor base classes and retain behavior tests in the pure
validator so no live MoveIt server is required by unit tests.

- [ ] **Step 2: Confirm RED before adding the adapter header**

Expected: compilation fails because `DescendPlannerExecutor` does not exist.

- [ ] **Step 3: Implement Cartesian planning, FK/timing evidence, execute, cancel, and logs**

Reject states other than `DESCEND -> CLOSE_GRIPPER`; resolve the shared target; configure the TCP and
start state; configure scaling; call non-deprecated `computeCartesianPath`; log
`CARTESIAN_FRACTION`; derive path poses, joint deltas, and strictly increasing timestamps from the
server-returned trajectory; call pure validation; return a nonempty artifact; execute only that
artifact; stop via `MoveGroupInterface::stop()`.

- [ ] **Step 4: Build the adapter and confirm GREEN**

Run: `colcon build --packages-select panda_gazebo_demo --event-handlers console_direct+`

Expected: package and all targets build without warnings introduced by the new adapter.

### Task 5: Parameters, hash, and state-machine registration

**Files:**
- Modify: `src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp`
- Test: `src/panda_gazebo_demo/test/pick_place/test_pick_place_core.cpp`

**Interfaces:**
- Consumes: `DescendPlannerExecutor` and the existing DESCEND transition validator.
- Produces: plan-only/execute registration and configuration-hash binding for all three parameters.

- [ ] **Step 1: Add failing runner boundary tests**

Register fake actions through DESCEND and assert `stop_after=DESCEND` returns checkpoint success.
Without `stop_after`, assert the retained first failure is `EXECUTE_ACTION_NOT_REGISTERED` for
`CLOSE_GRIPPER` and the workflow ends in ERROR.

- [ ] **Step 2: Confirm the boundary tests fail for the missing registrations/setup**

Run the two focused tests and verify the expected missing DESCEND action behavior.

- [ ] **Step 3: Declare/validate/hash parameters and register the adapter**

Register the planner in plan-only and execute modes and the executor only in execute mode. Preserve
the existing `DescendToCloseGripperValidator` registration and leave CLOSE_GRIPPER unregistered.

- [ ] **Step 4: Re-run boundary tests and package build**

Expected: both boundary tests and compilation pass.

### Task 6: Full verification

**Files:**
- Modify only files required for explicit lint corrections.

- [ ] **Step 1: Run the package build and full test suite**

Run: `colcon build --packages-select panda_gazebo_demo --event-handlers console_direct+`

Run: `colcon test --packages-select panda_gazebo_demo --event-handlers console_direct+`

Run: `colcon test-result --verbose`

Expected: zero failures.

- [ ] **Step 2: Run read-only formatting/lint verification**

Run the package's configured lint tests and `ament_uncrustify` without `--reformat`. Apply only
targeted manual patches if it reports differences.

- [ ] **Step 3: Attempt the requested simulator workflow when services are available**

Execute through MOVE_ABOVE with a checkpoint; resume plan-only for DESCEND; resume execute with
`stop_after:=DESCEND`. Confirm fraction/end-pose/Coke logs and the CLOSE_GRIPPER boundary. If the
simulation stack is unavailable, preserve automated evidence and report the runtime limitation.
