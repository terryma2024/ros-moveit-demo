# PickPlaceTargetPolicy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one injectable policy select TCP targets for both planning and validation.

**Architecture:** Add an abstract `PickPlaceTargetPolicy` and a fixed mapping implementation.
Pass one pre-plan observation through `IStatePlanner`, and inject the same policy instance into
`MoveAboveObjectPlanner` and transition validators. Include the policy signature in resume
configuration identity.

**Tech Stack:** C++17, ROS 2 Jazzy, MoveIt, GoogleTest, ament/colcon

## Global Constraints

- Preserve existing uncommitted formatting changes in `pick_place_state_machine_node.cpp`.
- Do not run `ament_uncrustify --reformat`.
- Do not use `gh`; the remote repository is Gitee.
- Unsupported policy transitions fail closed without a fallback target.

---

### Task 1: Define and test the target policy

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/pick_place_target_policy.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/pick_place_target_policy.cpp`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_pick_place_core.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Produces: `TargetPoseResult`, `PickPlaceTargetPolicy::targetPose`,
  `PickPlaceTargetPolicy::configurationSignature`, and `FixedPickPlaceTargetPolicy`.

- [ ] Add failing tests for both fixed transitions and an unsupported transition.
- [ ] Run `test_pick_place_core` and confirm compilation fails because the policy types are absent.
- [ ] Implement the policy and register its source in `pick_place_core`.
- [ ] Rebuild and run `test_pick_place_core`; expect all policy tests to pass.

### Task 2: Pass one observation to planners

**Files:**
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/state_action.hpp`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/move_above_object_planner.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/move_above_object_planner.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/runner.cpp`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_pick_place_core.cpp`

**Interfaces:**
- Consumes: `PickPlaceTargetPolicy` and the Runner's pre-execution `ObservationResult`.
- Produces: `IStatePlanner::plan(State, State, const ObservationResult &)`.

- [ ] Change `FakePlanner` tests first to assert current state, next state, and snapshot identity.
- [ ] Build and confirm the old planner interface fails those tests.
- [ ] Update `IStatePlanner`, Runner plan-only/execute paths, and `MoveAboveObjectPlanner`.
- [ ] Rebuild and run core tests; expect Planner and Runner tests to pass.

### Task 3: Inject the policy into validators and node wiring

**Files:**
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/transition_contract.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/transition_contract.cpp`
- Modify: `src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_pick_place_core.cpp`

**Interfaces:**
- Consumes: one shared `PickPlaceTargetPolicy` instance.
- Produces: validators that resolve expected TCP poses from their transition and pre-state
  observation instead of constructor pose literals.

- [ ] Add a recording policy test showing the Validator receives the transition's `before`
  snapshot and rejects a pose resolved by that policy when the endpoint differs.
- [ ] Run the test and confirm the existing pose-based constructor cannot satisfy it.
- [ ] Replace validator pose constructor arguments with the shared policy.
- [ ] Construct one fixed policy in the node and inject it into Planner and Validators.
- [ ] Append `configurationSignature()` to `configurationHash` input.
- [ ] Rebuild and run core tests; expect all tests to pass.

### Task 4: Full verification

**Files:**
- Verify all files above without automatic reformatting.

- [ ] Run `git diff --check` and inspect the node diff to ensure prior user formatting remains.
- [ ] Run `colcon build --packages-select panda_gazebo_demo --cmake-args -DBUILD_TESTING=ON`.
- [ ] Run `colcon test --packages-select panda_gazebo_demo --event-handlers console_direct+`.
- [ ] Run `colcon test-result --verbose`; expect zero errors and zero failures.
