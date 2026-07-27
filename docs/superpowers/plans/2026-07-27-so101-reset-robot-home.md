# SO-101 Reset Robot Home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `reset_so101_world` safely restore the arm and gripper to SRDF `home` as well as restoring detached canonical Gazebo and MoveIt world facts.

**Architecture:** `WorldResetCoordinator` remains ROS-independent and orchestrates a new `IRobotHomeResetAdapter`. The production adapter explicitly plans and executes the arm home trajectory with MoveIt, commands q6 through the existing FollowJointTrajectory adapter, and reads independent joint evidence through `IJointPlanningBoundary`. Every command is followed by a bounded observation gate.

**Tech Stack:** C++17, ROS 2 Jazzy, MoveIt 2 `MoveGroupInterface`, ros2_control `FollowJointTrajectory`, GoogleTest, pytest/launch testing, colcon.

## Global Constraints

- Final arm home is joints `1..5 = [0, 0, 0, 0, 0]`.
- Final gripper home is joint `6 = 0`; `q6 = 1.7` is only a release intermediate.
- Arm home must use explicit collision-aware `plan → execute`; plan failure or an incomplete trajectory forbids execute.
- Initial Gazebo, MoveIt, and complete finite joint evidence are required before any side effect.
- API success never replaces independent position, velocity, attachment, and 6D-pose validation.
- Preserve unrelated dirty-worktree changes and do not modify `panda_gazebo_demo`.
- The current worktree has overlapping user changes; implementation milestones use focused tests and
  diff inspection rather than creating commits that could capture unrelated edits.

---

### Task 1: Robot-home reset boundary and canonical configuration

**Files:**
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_profile.hpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/world_reset_coordinator.hpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_so101_world_reset.cpp`

**Interfaces:**
- Consumes: `CurrentJointStateEvidence`, `PlanResult`, `PlanArtifact`, `ActionResult`.
- Produces: `IRobotHomeResetAdapter`, expanded `WorldResetConfig`, and canonical profile home values.

- [ ] **Step 1: Write the failing canonical-state and dependency tests**

Add assertions that the canonical profile exposes:

```cpp
EXPECT_EQ((std::vector<double>{0, 0, 0, 0, 0}), profile.arm_home_positions);
EXPECT_DOUBLE_EQ(0.0, profile.q6_home);
EXPECT_DOUBLE_EQ(1.7, profile.q6_full_open);
```

Add a `FakeRobotHomeResetAdapter` implementing this required boundary:

```cpp
class IRobotHomeResetAdapter {
public:
  virtual ~IRobotHomeResetAdapter() = default;
  virtual std::optional<CurrentJointStateEvidence> observeJoints() = 0;
  virtual ActionResult commandGripper(double q6) = 0;
  virtual PlanResult planArmHome(const std::vector<double> & goal) = 0;
  virtual ActionResult executeArmHome(const PlanArtifact & plan) = 0;
  virtual ActionResult cancelArmAndWait() = 0;
};
```

Construct the coordinator with a null robot adapter and expect
`WORLD_RESET_ADAPTER_MISSING` before any Gazebo or MoveIt command.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
colcon build --packages-select so101_gazebo_demo --cmake-target test_so101_world_reset
./build/so101_gazebo_demo/test_so101_world_reset \
  --gtest_filter='SO101Profile.*:SO101WorldResetCoordinator.RequiresRobotHomeAdapter'
```

Expected: compile failure because the home fields, interface, and constructor dependency do not exist.

- [ ] **Step 3: Add the minimal interface and configuration**

Add to `SO101Profile`:

```cpp
std::vector<double> arm_home_positions{0.0, 0.0, 0.0, 0.0, 0.0};
double q6_home{0.0};
```

Expand `WorldResetConfig` with arm joint names, arm home positions, q6 release/home targets,
joint position tolerance, and joint velocity tolerance. Inject
`std::shared_ptr<IRobotHomeResetAdapter>` into `WorldResetCoordinator`.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the command from Step 2. Expected: selected tests pass.

- [ ] **Step 5: Inspect only Task 1 files without committing overlapping changes**

```bash
git diff --check -- \
  src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_profile.hpp \
  src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/world_reset_coordinator.hpp \
  src/so101_gazebo_demo/test/pick_place/test_so101_world_reset.cpp
```

### Task 2: Coordinator safe order and joint convergence gates

**Files:**
- Modify: `src/so101_gazebo_demo/src/pick_place/world_reset_coordinator.cpp`
- Test: `src/so101_gazebo_demo/test/pick_place/test_so101_world_reset.cpp`

**Interfaces:**
- Consumes: `IRobotHomeResetAdapter` and expanded `WorldResetConfig` from Task 1.
- Produces: deterministic detach → release → arm plan/execute → world sync → gripper home flow.

- [ ] **Step 1: Write failing order, fail-closed, and metrics tests**

Use one shared event vector across all fakes, filter it to side-effecting operations, and require:

```cpp
EXPECT_EQ((std::vector<std::string>{
  "gripper:1.700000", "plan_arm_home", "execute_arm_home",
  "gazebo_pose", "moveit_table", "moveit_pedestal", "moveit_coke",
  "gripper:0.000000"}), commandEvents(events));
```

Add independent tests proving:

```cpp
// Missing initial joints: no detach, gripper, arm, or pose command.
EXPECT_EQ("WORLD_RESET_INITIAL_JOINT_OBSERVATION_FAILED", result.failure->code);

// Failed/empty arm plan: execute is never called and world reset does not begin.
EXPECT_EQ(0, robot->execute_calls);
EXPECT_EQ(0, gazebo->set_pose_calls);

// Final q6 mismatch exposes both values.
EXPECT_DOUBLE_EQ(0.0, result.failure->metrics.at("expected_q6"));
EXPECT_DOUBLE_EQ(1.7, result.failure->metrics.at("actual_q6"));
```

- [ ] **Step 2: Run the coordinator suite and verify RED**

```bash
colcon build --packages-select so101_gazebo_demo --cmake-target test_so101_world_reset
./build/so101_gazebo_demo/test_so101_world_reset
```

Expected: new order and joint-gate tests fail because reset still performs only world operations.

- [ ] **Step 3: Implement the minimal gated sequence**

Implement helpers that validate complete joint names, finite positions/velocities, home position
tolerance, and velocity tolerance. `reset()` must:

```cpp
observe all initial facts;
detach only currently attached backends;
commandGripper(q6_full_open);
poll joint evidence until q6 is full-open and stopped;
planArmHome(arm_home_positions);
reject failed, null, or zero-point plans;
executeArmHome(*plan.artifact);
poll until arm joints are home and stopped;
reset and verify canonical world facts;
commandGripper(q6_home);
poll until all six joints are home and stopped;
```

Return specific timeout codes and attach sorted `expected_*`, `actual_*`, and velocity metrics.

- [ ] **Step 4: Run the coordinator suite and verify GREEN**

Run the command from Step 2. Expected: all coordinator tests pass, including the existing four
attachment combinations and repeated-reset idempotence tests.

- [ ] **Step 5: Inspect only Task 2 files without committing overlapping changes**

```bash
git diff --check -- src/so101_gazebo_demo/src/pick_place/world_reset_coordinator.cpp \
  src/so101_gazebo_demo/test/pick_place/test_so101_world_reset.cpp
```

### Task 3: MoveIt/ros2_control production robot-home adapter

**Files:**
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/robot_home_reset_adapter.hpp`
- Create: `src/so101_gazebo_demo/src/pick_place/robot_home_reset_adapter.cpp`
- Create: `src/so101_gazebo_demo/test/pick_place/test_robot_home_reset_adapter.cpp`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: `IRobotHomeResetAdapter`, `IJointPlanningBoundary`, and `ISO101GripperCommand`.
- Produces: `IArmHomePlanningBoundary`, `MoveGroupArmHomePlanningBoundary`, and
  `MoveItRobotHomeResetAdapter` with exact validated-plan execution.

- [ ] **Step 1: Write failing adapter tests**

Define the test seam:

```cpp
class IArmHomePlanningBoundary {
public:
  virtual ~IArmHomePlanningBoundary() = default;
  virtual PlanResult planHome(const std::vector<std::string> & joint_names,
                              const std::vector<double> & goal) = 0;
  virtual ActionResult executeHome(const PlanArtifact & plan) = 0;
  virtual ActionResult cancelAndWait() = 0;
};
```

Use fake arm, joint-observation, and gripper boundaries to prove:

```cpp
EXPECT_EQ(profile.arm_joints, planner.last_joint_names);
EXPECT_EQ(profile.arm_home_positions, planner.last_goal);
EXPECT_TRUE(planner.collision_aware);
EXPECT_EQ(ActionStatus::FAILED, adapter.planArmHome(profile.arm_home_positions).action.status);
EXPECT_EQ(0, planner.execute_calls);  // incomplete plan is never executable
EXPECT_DOUBLE_EQ(profile.q6_home, gripper.last_target);
```

Also prove `executeArmHome()` executes the exact artifact returned by `planArmHome()` rather than
planning again.

- [ ] **Step 2: Build the new test target and verify RED**

```bash
colcon build --packages-select so101_gazebo_demo \
  --cmake-target test_robot_home_reset_adapter
```

Expected: compile/configuration failure because the adapter files and target do not exist.

- [ ] **Step 3: Implement the production adapter**

The adapter must use `MoveGroupInterface::Plan` in a private `PlanArtifact` subtype, call
`setJointValueTarget()` for joints `1..5`, and reject plans with missing joint names, zero points,
non-finite endpoint values, or endpoint mismatch. Its execute method accepts only its own artifact
type and calls `move_group.execute(exact_plan)`. Gripper commands delegate to
`ISO101GripperCommand::command(q6)`, and joint observation delegates to
`IJointPlanningBoundary::currentState()`.

- [ ] **Step 4: Run adapter and coordinator tests and verify GREEN**

```bash
colcon build --packages-select so101_gazebo_demo
./build/so101_gazebo_demo/test_robot_home_reset_adapter
./build/so101_gazebo_demo/test_so101_world_reset
```

Expected: both test executables pass.

- [ ] **Step 5: Inspect only Task 3 files without committing**

```bash
git diff --check -- \
  src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/robot_home_reset_adapter.hpp \
  src/so101_gazebo_demo/src/pick_place/robot_home_reset_adapter.cpp \
  src/so101_gazebo_demo/test/pick_place/test_robot_home_reset_adapter.cpp \
  src/so101_gazebo_demo/CMakeLists.txt
```

### Task 4: Reset executable wiring and live acceptance

**Files:**
- Modify: `src/so101_gazebo_demo/src/nodes/reset_so101_world.cpp`
- Modify: `src/so101_gazebo_demo/test/headless/test_so101_world_reset_live.py`
- Modify: `src/so101_gazebo_demo/test/scripts/test_so101_reset_cli.sh`

**Interfaces:**
- Consumes: `MoveItRobotHomeResetAdapter` and canonical profile home targets.
- Produces: end-to-end `reset_so101_world` behavior and diagnostic output.

- [ ] **Step 1: Write failing CLI and live assertions**

Extend CLI contract checks to require the success message:

```text
Gazebo, MoveIt, arm, and gripper converged to canonical SO-101 reset facts
```

Extend the live test to command a small safe non-home arm target and non-home q6, disturb Coke,
run reset, then assert `/joint_states` has joints `1..5` near zero, q6 near zero, and all six
velocities below the configured stop threshold in addition to existing world/attachment checks.

- [ ] **Step 2: Run CLI/live tests and verify RED**

```bash
colcon build --packages-select so101_gazebo_demo
colcon test --packages-select so101_gazebo_demo \
  --ctest-args -R 'test_so101_reset_cli|test_so101_world_reset_live' --output-on-failure
```

Expected: wiring/acceptance assertions fail because the executable does not create the robot adapter.

- [ ] **Step 3: Wire the production dependencies**

Create the node spinner, `MoveItJointPlanningBoundary`, ROS trajectory action client,
`FollowJointTrajectoryGripperAdapter`, and `MoveItRobotHomeResetAdapter`; pass the robot adapter and
home values into the coordinator. On failure, print `formatFailure(*result.failure)` so expected and
actual joint metrics are visible.

- [ ] **Step 4: Run focused, full, and real verification**

```bash
colcon build --packages-select so101_gazebo_demo
colcon test --packages-select so101_gazebo_demo
colcon test-result --verbose
git diff --check
```

Expected: build exits 0; all package tests report zero failures; diff check is clean.

With the existing GUI simulation running, command a non-home arm/q6 and disturbed Coke, run:

```bash
ros2 run so101_gazebo_demo reset_so101_world
ros2 topic echo /joint_states --once
```

Then independently query Gazebo and Planning Scene. Expected: six home joints are stationary,
both attachment backends are detached, and table/pedestal/Coke have matching canonical poses.

- [ ] **Step 5: Inspect final scope and preserve all pre-existing changes**

```bash
git diff --check
git status --short
git -C src/panda_gazebo_demo status --short
```
