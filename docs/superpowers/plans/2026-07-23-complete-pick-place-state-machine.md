# Complete Panda Pick-Place State Machine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete every forward and recovery action, plan validator, transition contract, checkpoint boundary, and headless verification path for the fixed-space Panda pick-place state machine.

**Architecture:** Keep the pure state-machine core independent from ROS. State-level actions consume reusable MoveIt, gripper, Gazebo attachment, and Planning Scene adapters. Every forward action follows observe, pre-validate, plan, plan-validate, execute, observe, post-validate, checkpoint; failures are stopped, observed, classified by `IRecoveryPolicy`, and routed through idempotent recovery actions.

**Tech Stack:** C++17, ROS 2 Jazzy, MoveIt 2, Gazebo Harmonic / gz-transport13, ros2_control GripperActionController, GTest, ament/colcon.

## Global Constraints

- Preserve commits `75f9f68` (`FixedPickPlaceTargetPolicy`) and `07ee3a1` (Cartesian `DESCEND`) as the verified baseline.
- Use fixed TCP targets: above-pick `(0.30,0.00,0.987)`, pick `(0.30,0.00,0.870)`, above-place `(0.30,0.20,0.987)`, place `(0.30,0.20,0.870)`, all with quaternion `(1,0,0,0)`. The pick/place height was corrected during Task 12 after Gazebo geometry diagnostics proved the former `0.930` target left a 24 mm gap above the Coke; a one-variable `0.870` test produced the expected contact-stalled grasp.
- Never duplicate fixed target literals outside `FixedPickPlaceTargetPolicy` and its tests.
- One state produces one independently observable side effect.
- Missing Executor, TransitionContract, or PlanValidator fails closed.
- Partial Cartesian paths are never executed; default minimum fraction is `0.99`.
- Never release a carried Coke in the air. Carrying recovery returns it to the original pick surface.
- Gazebo is authoritative for physical Coke pose/attachment; MoveIt is authoritative for collision-world membership/attachment.
- Primary business actions are not automatically retried. Each recovery action is idempotent and attempted once.
- No production code is written before the focused failing test is observed.
- Do not add perception, Agent, SO-ARM101, navigation, or a generic behavior-tree framework.

All commands run from `/data/work/ws_moveit` after:

```bash
source /opt/ros/jazzy/setup.bash
```

---

### Task 1: Add ExecutionContext and fail-closed PlanValidatorRegistry

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/plan_validation.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/plan_validation.cpp`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/state_action.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/state_action.cpp`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/runner.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/runner.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/move_above_object_planner.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/descend_planner_executor.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/open_gripper_executor.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Test: `src/panda_gazebo_demo/test/pick_place/test_pick_place_core.cpp`

**Interfaces:**
- Produces: `ExecutionContext`, `IPlanValidator`, `PlanValidatorRegistry`.
- Changes: `IStateExecutor::execute(const ExecutionContext &)`.
- Consumes: existing `WorldSnapshot`, `PlanArtifact`, `ValidationResult`.

- [ ] **Step 1: Write failing core tests**

Add tests with these exact expectations:

```cpp
TEST(Runner, RejectsPlannedExecuteStateWithoutPlanValidator)
{
  // Register planner, executor, transition contract, observer, and checkpoint store,
  // but intentionally omit the plan validator.
  const auto result = runner.run(executeStopAfter(State::MOVE_ABOVE_OBJECT));
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("PLAN_VALIDATOR_NOT_REGISTERED", result.failure->code);
  EXPECT_EQ(0, executor->calls);
}

TEST(Runner, PassesVerifiedBeforeSnapshotToExecutor)
{
  const auto result = runner.run(executeStopAfter(State::MOVE_ABOVE_OBJECT));
  ASSERT_EQ(RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_NEAR(
    observer.snapshot.tcp_pose_world.x,
    executor->last_context.before.tcp_pose_world.x, 1e-12);
  EXPECT_NEAR(
    observer.snapshot.tcp_pose_world.y,
    executor->last_context.before.tcp_pose_world.y, 1e-12);
  EXPECT_NEAR(
    observer.snapshot.tcp_pose_world.z,
    executor->last_context.before.tcp_pose_world.z, 1e-12);
  EXPECT_EQ(State::MOVE_ABOVE_OBJECT, executor->last_context.state);
  EXPECT_EQ(State::DESCEND, executor->last_context.next_state);
}

TEST(PlanValidatorRegistry, RejectsEmptyTrajectory)
{
  PlanArtifact artifact;
  artifact.trajectory_points = 0;
  const auto result = registry.validate(State::MOVE_ABOVE_OBJECT, snapshot, artifact);
  EXPECT_FALSE(result.ok);
  EXPECT_EQ("EMPTY_PLAN_ARTIFACT", result.failures.front().code);
}
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
colcon build --packages-select panda_gazebo_demo --symlink-install
```

Expected: compile failure naming missing `ExecutionContext` / `PlanValidatorRegistry`, proving the new API is not implemented.

- [ ] **Step 3: Add the core interfaces**

Implement:

```cpp
struct ExecutionContext
{
  State state;
  State next_state;
  WorldSnapshot before;
  std::shared_ptr<const PlanArtifact> plan;
};

class IPlanValidator
{
public:
  virtual ~IPlanValidator() = default;
  [[nodiscard]] virtual ValidationResult validate(
    State state, const WorldSnapshot & before,
    const PlanArtifact & artifact) const = 0;
};

class PlanValidatorRegistry
{
public:
  void registerValidator(State state, std::shared_ptr<const IPlanValidator> validator);
  [[nodiscard]] bool hasValidator(State state) const noexcept;
  [[nodiscard]] ValidationResult validate(
    State state, const WorldSnapshot & before,
    const PlanArtifact & artifact) const;
private:
  std::map<State, std::shared_ptr<const IPlanValidator>> validators_;
};

class NonEmptyPlanValidator final : public IPlanValidator
{
public:
  [[nodiscard]] ValidationResult validate(
    State state, const WorldSnapshot & before,
    const PlanArtifact & artifact) const override;
};
```

Add `PlanValidatorRegistry` to `StateMachineRunner`. In `runPlanOnly` and `runExecuteStep`, require a validator whenever a planner exists. Validate the artifact before invoking the executor. Construct `ExecutionContext{state,next_state,*before,plan_artifact}` and migrate the three existing executors.

Register `NonEmptyPlanValidator` for `MOVE_ABOVE_OBJECT` and `DESCEND`; it rejects zero-point artifacts and preserves their existing internal endpoint checks during this migration. Task 8 replaces it with typed evidence validators.

- [ ] **Step 4: Run focused and full tests GREEN**

Run:

```bash
colcon build --packages-select panda_gazebo_demo --symlink-install
colcon test --packages-select panda_gazebo_demo --event-handlers console_direct+
colcon test-result --verbose
```

Expected: all existing tests plus the three new tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/panda_gazebo_demo
git commit -m "refactor: add execution context and plan validation"
```

---

### Task 2: Extend targets, states, and canonical transition graph

**Files:**
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/domain_types.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/domain_types.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/transition_table.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/pick_place_target_policy.cpp`
- Test: `src/panda_gazebo_demo/test/pick_place/test_pick_place_targets.cpp`
- Test: `src/panda_gazebo_demo/test/pick_place/test_pick_place_core.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Produces target-policy support for every fixed and recovery motion transition.
- Adds states: `RECOVER_LIFT_TO_SAFE_HEIGHT`, `RECOVER_MOVE_ABOVE_PICK`, `RECOVER_DESCEND_TO_PICK`.

- [ ] **Step 1: Write failing target and transition tests**

```cpp
TEST(FixedTargets, SuppliesAllForwardMotionTargets)
{
  EXPECT_POSE(policy, State::LIFT, State::MOVE_ABOVE_PLACE, 0.30, 0.00, 0.987);
  EXPECT_POSE(policy, State::MOVE_ABOVE_PLACE, State::DESCEND_TO_PLACE, 0.30, 0.20, 0.987);
  EXPECT_POSE(policy, State::DESCEND_TO_PLACE, State::OPEN_GRIPPER, 0.30, 0.20, 0.870);
  EXPECT_POSE(policy, State::RETREAT, State::DONE, 0.30, 0.20, 0.987);
}

TEST(FixedTargets, UsesObservedXYForRecoverySafeHeight)
{
  auto observation = makeObservation();
  observation.snapshot->tcp_pose_world = {0.12, -0.08, 0.95, 1, 0, 0, 0};
  const auto result = policy.targetPose(
    State::RECOVER_LIFT_TO_SAFE_HEIGHT, State::RECOVER_MOVE_ABOVE_PICK, observation);
  ASSERT_TRUE(result.target_pose);
  EXPECT_DOUBLE_EQ(0.12, result.target_pose->x);
  EXPECT_DOUBLE_EQ(-0.08, result.target_pose->y);
  EXPECT_DOUBLE_EQ(0.987, result.target_pose->z);
}

TEST(TransitionTable, CarryFailureUsesCarryRecovery)
{
  EXPECT_EQ(State::RECOVER_LIFT_TO_SAFE_HEIGHT,
    table.resolve(State::MOVE_ABOVE_PLACE, ActionStatus::FAILED));
}
```

- [ ] **Step 2: Run RED**

Run `colcon build --packages-select panda_gazebo_demo --symlink-install`.

Expected: new recovery states or targets are unavailable.

- [ ] **Step 3: Implement the complete target map and state strings**

Add the fixed targets from the approved spec. Map recovery transitions as follows:

```text
RECOVER_LIFT_TO_SAFE_HEIGHT -> RECOVER_MOVE_ABOVE_PICK : observed x/y, z=0.987
RECOVER_MOVE_ABOVE_PICK -> RECOVER_DESCEND_TO_PICK     : above_pick
RECOVER_DESCEND_TO_PICK -> RECOVER_OPEN_GRIPPER       : pick
RECOVER_RETREAT -> ERROR                               : observed x/y, z=0.987
```

Canonical failure edges used by dry-run:

```text
PREPARE_OPEN_GRIPPER -> ERROR
MOVE_ABOVE_OBJECT -> RECOVER_RETREAT
DESCEND/CLOSE/ATTACH_* -> RECOVER_OPEN_GRIPPER
LIFT/MOVE_ABOVE_PLACE/DESCEND_TO_PLACE -> RECOVER_LIFT_TO_SAFE_HEIGHT
OPEN_GRIPPER -> RECOVER_OPEN_GRIPPER
DETACH_GAZEBO -> RECOVER_DETACH_GAZEBO
DETACH_MOVEIT -> RECOVER_DETACH_MOVEIT
SYNC_WORLD_OBJECT -> RECOVER_SYNC_WORLD_OBJECT
RETREAT -> RECOVER_RETREAT
```

- [ ] **Step 4: Run GREEN**

Run the target tests and existing dry-run transition tests. Expected: all pass and `configurationSignature()` includes all fixed targets.

- [ ] **Step 5: Commit**

```bash
git add src/panda_gazebo_demo
git commit -m "feat: define complete pick-place targets and states"
```

---

### Task 3: Add fact-driven RecoveryPolicy and recovery checkpoint schema v3

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/recovery_policy.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/recovery_policy.cpp`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/checkpoint.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/file_checkpoint_store.cpp`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/runner.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/runner.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/common_resume_validator.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Test: `src/panda_gazebo_demo/test/pick_place/test_recovery_policy.cpp`
- Test: `src/panda_gazebo_demo/test/pick_place/test_checkpoint_v3.cpp`

**Interfaces:**
- Produces: `CheckpointPhase`, `RecoveryRoute`, `IRecoveryPolicy`, `FixedRecoveryPolicy`.
- Consumes: stopped `WorldSnapshot`, failed state, original `Failure`, target policy.

- [ ] **Step 1: Write failing policy matrix tests**

Cover exactly:

```cpp
EXPECT_ROUTE(bothAttachedMidair(), State::RECOVER_LIFT_TO_SAFE_HEIGHT);
EXPECT_ROUTE(bothAttachedAtPick(), State::RECOVER_OPEN_GRIPPER);
EXPECT_ROUTE(gazeboOnlyAttached(), State::RECOVER_OPEN_GRIPPER);
EXPECT_ROUTE(moveitOnlyAttached(), State::RECOVER_OPEN_GRIPPER);
EXPECT_ROUTE(bothDetached(), State::RECOVER_OPEN_GRIPPER);
EXPECT_ROUTE_ERROR(staleSnapshot(), "RECOVERY_OBSERVATION_NOT_FRESH");
EXPECT_ROUTE_ERROR(movingRobot(), "RECOVERY_ROBOT_NOT_STATIONARY");
EXPECT_ROUTE_ERROR(missingAttachmentState(), "RECOVERY_ATTACHMENT_STATE_UNKNOWN");
```

Add checkpoint JSON round-trip assertions for `phase`, `failed_state`, `original_failure`, and `next_state`. Add a Runner test proving recovery resume reclassifies current facts instead of blindly using persisted `next_state`.

- [ ] **Step 2: Run RED**

Expected: missing policy and schema-v3 fields.

- [ ] **Step 3: Implement the policy and v3 schema**

Use:

```cpp
enum class CheckpointPhase { FORWARD, RECOVERY };

struct RecoveryRoute
{
  std::optional<State> next_state;
  std::optional<Failure> failure;
};

class IRecoveryPolicy
{
public:
  virtual ~IRecoveryPolicy() = default;
  [[nodiscard]] virtual RecoveryRoute select(
    State failed_state, const Failure & original_failure,
    const WorldSnapshot & stopped_world) const = 0;
};
```

Extend `Checkpoint` with `phase`, optional `failed_state`, and optional `original_failure`. After action failure, Runner cancels, waits for a fresh stationary snapshot, calls `select`, commits a recovery checkpoint, and starts the selected recovery state. Recovery resume validates common invariants and calls `select` again.

The resume classification is a fact-driven recovery cursor, not only an initial route selector. It
must advance past completed side effects: carrying height selects lift/move-above-pick/descend;
supported open partial attachments select the matching detach; detached open worlds select sync or
retreat according to full 6D cross-world equality. Missing facts fail closed and no attached Coke is
released away from a proven pick/place support pose. This is the minimum consistency correction
required for `stop_after` recovery checkpoints to make progress across process restarts.

Task 12 cross-process verification requires `stop_after` to accept recovery
actions as well as forward actions. The CLI therefore accepts every
non-terminal action state while continuing to reject `IDLE`, `DONE`, and
`ERROR`; `fail_at` remains forward-only. A real low carrying recovery fixture
is formed from the `ATTACH_MOVEIT` checkpoint by lifting 30 mm and then moving
30 mm laterally at the lifted height. The two-segment order avoids a low-height
lateral sweep, while ensuring recovery lift preserves an off-axis x/y so the
fact cursor subsequently selects move-above-pick and descend.

Recovery action failure terminates immediately; it must not ask the policy for another potentially unsafe route.

- [ ] **Step 4: Run GREEN and migration tests**

Verify v2 files are rejected with `CHECKPOINT_INCOMPATIBLE`, while v3 forward and recovery checkpoints round-trip.

- [ ] **Step 5: Commit**

```bash
git add src/panda_gazebo_demo
git commit -m "feat: add fact-driven recovery checkpoints"
```

---

### Task 4: Add reusable world and gripper validation primitives

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/state_validation.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/state_validation.cpp`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/world_observer.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/gazebo_world_observer.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/move_above_object_planner.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Test: `src/panda_gazebo_demo/test/pick_place/test_state_validation.cpp`

**Interfaces:**
- Produces `GripperEvidence`, `AttachmentExpectation`, Coke stability metrics, and shared validation functions.
- Adds `gazebo_coke_stationary` to `WorldSnapshot`.

- [ ] **Step 1: Write failing table tests**

```cpp
TEST(GripperValidation, RequiresBothOpenAndStopped);
TEST(GripperValidation, AcceptsSymmetricCokeWidthGrasp);
TEST(GripperValidation, RejectsOnlyLeftFingerInRange);
TEST(GripperValidation, RejectsAsymmetricFingerPositions);
TEST(AttachmentValidation, DistinguishesAllFourAttachmentCombinations);
TEST(GazeboObserver, ReportsCokeStationaryAfterFiveStableSamples);
TEST(GazeboObserver, ReportsMovingAfterPoseDeltaExceedsTolerance);
```

- [ ] **Step 2: Run RED**

Expected: missing `state_validation.hpp` and stationary evidence.

- [ ] **Step 3: Implement pure validation functions**

Implement:

```cpp
struct GripperLimits
{
  double open_min{0.038};
  double grasp_min{0.028};
  double grasp_max{0.037};
  double symmetry_tolerance{0.003};
  double velocity_tolerance{0.010};
};

ValidationResult validateGripperOpen(const WorldSnapshot &, const GripperLimits &);
ValidationResult validateGripperGrasp(const WorldSnapshot &, const GripperLimits &);
ValidationResult validateAttachmentState(
  const WorldSnapshot &, bool gazebo_attached, bool moveit_attached);
```

Update the Gazebo observer to retain the last five timestamped Coke poses and set `gazebo_coke_stationary` when every adjacent sample is within `0.002 m` and `0.020 rad`.

- [ ] **Step 4: Run GREEN**

Run focused tests, then the whole package.

- [ ] **Step 5: Commit**

```bash
git add src/panda_gazebo_demo
git commit -m "feat: add gripper and world validation evidence"
```

---

### Task 5: Implement close/open GripperCommand states with acknowledged cancel

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/gripper_command_adapter.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/gripper_command_adapter.cpp`
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/gripper_state_executor.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/gripper_state_executor.cpp`
- Modify: `src/panda_gazebo_demo/config/controllers.yaml`
- Remove after migration: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/open_gripper_executor.hpp`
- Remove after migration: `src/panda_gazebo_demo/src/pick_place/open_gripper_executor.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Test: `src/panda_gazebo_demo/test/pick_place/test_gripper_state_executor.cpp`

**Interfaces:**
- Produces `IGripperCommandAdapter` and `GripperStateExecutor`.
- Supports `PREPARE_OPEN_GRIPPER`, `CLOSE_GRIPPER`, `OPEN_GRIPPER`, and `RECOVER_OPEN_GRIPPER` through separate configured instances.

- [ ] **Step 1: Write failing executor tests with a fake adapter**

Test exact behavior:

```cpp
TEST(GripperExecutor, CloseSendsZeroPositionOnce);
TEST(GripperExecutor, RecoveryOpenNoOpsWhenSnapshotAlreadyOpen);
TEST(GripperExecutor, RejectsUnsupportedStateBeforeSendingGoal);
TEST(GripperExecutor, PropagatesGoalRejection);
TEST(GripperExecutor, WaitsForCancellationAcknowledgement);
TEST(GripperExecutor, ReportsCancelRejectedInsteadOfSuccess);
```

- [ ] **Step 2: Run RED**

Expected: missing adapter and executor.

- [ ] **Step 3: Implement adapter and configured executor**

Use:

```cpp
class IGripperCommandAdapter
{
public:
  virtual ~IGripperCommandAdapter() = default;
  [[nodiscard]] virtual ActionResult command(double position, double max_effort) = 0;
  [[nodiscard]] virtual ActionResult cancelAndWait() = 0;
};

struct GripperStateConfig
{
  State state;
  double target_position;
  double max_effort;
  bool no_op_if_already_open{false};
};
```

The ROS adapter waits for action-server availability, goal response, result, and cancel response. It never reports cancel success merely because `async_cancel_goal` was called.

Configure `panda_hand_controller`:

```yaml
allow_stalling: true
stall_velocity_threshold: 0.001
stall_timeout: 1.0
goal_tolerance: 0.002
```

- [ ] **Step 4: Run GREEN and a live open/close smoke test**

Verify both finger positions/velocities and controller result are logged. Do not place Coke under the gripper for the empty close smoke test; the state-machine grasp test happens in Task 11.

- [ ] **Step 5: Commit**

```bash
git add src/panda_gazebo_demo
git commit -m "feat: implement verified gripper states"
```

---

### Task 6: Implement Gazebo attach/detach states

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/gazebo_attachment_executor.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/gazebo_attachment_executor.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Test: `src/panda_gazebo_demo/test/pick_place/test_gazebo_attachment_executor.cpp`

**Interfaces:**
- Produces a configured executor for `ATTACH_GAZEBO`, `DETACH_GAZEBO`, and `RECOVER_DETACH_GAZEBO`.
- Uses gz-transport13 topics and waits for output convergence.

- [ ] **Step 1: Write failing tests on unique test topics**

```cpp
TEST(GazeboAttachmentExecutor, PublishesAttachAndWaitsForTrueOutput);
TEST(GazeboAttachmentExecutor, PublishesDetachAndWaitsForFalseOutput);
TEST(GazeboAttachmentExecutor, RecoveryDetachNoOpsWhenAlreadyDetached);
TEST(GazeboAttachmentExecutor, TimesOutWithoutExpectedOutput);
TEST(GazeboAttachmentExecutor, RejectsWrongStateWithoutPublishing);
```

- [ ] **Step 2: Run RED**

Expected: executor missing.

- [ ] **Step 3: Implement command and convergence waiting**

Constructor inputs:

```cpp
GazeboAttachmentExecutor(
  State allowed_state, bool desired_attached,
  std::string attach_topic, std::string detach_topic,
  std::string output_topic, double timeout_seconds,
  double poll_interval_seconds, bool idempotent);
```

Publish exactly one `gz::msgs::Empty` command. Wait until a fresh output message equals `desired_attached`; distinguish publish failure, stale output, and timeout codes.
The Gazebo Sim 8 DetachableJoint output is `gz::msgs::StringMsg`: map `attached` to `true` and
`detached` to `false` before checking convergence.

Task 12 runtime verification found that this local Gazebo Sim 8 plugin is event-driven, does not
replay its latest state to resumed processes, and its binary does not implement the
`initially_detached` tag. The consistent implementation therefore routes raw output through
`/panda/coke_attached_event` to a launch-lifetime relay. The relay starts unknown, validates raw
strings, enforces and confirms the initial detach, and periodically publishes durable current
state on `/panda/coke_attached`. Observers fail closed until that validated state is available.
`GazeboWorldObserver` uses `max_observation_age_seconds` for both the maximum accepted sample age
and the bounded startup wait for the first Coke-pose and durable attachment-state messages; a
missing fact at the deadline remains an observation failure. Pose and validated attachment samples
carry independent receive timestamps, so a stopped relay ages out with
`GAZEBO_ATTACHMENT_STATE_UNAVAILABLE` even when Coke poses continue.

Task 12 critical review tightened recovery classification: release is permitted only when both the
TCP and Gazebo Coke are within the corresponding pick or place 6DoF support regions. Both-attached
states lacking that complete evidence take carrying recovery; partially attached states lacking it
fail closed instead of opening the gripper.

- [ ] **Step 4: Run GREEN**

Run unit tests and a headless topic smoke test against `/panda/attach_coke`, `/panda/detach_coke`, and `/panda/coke_attached`.

- [ ] **Step 5: Commit**

```bash
git add src/panda_gazebo_demo
git commit -m "feat: implement Gazebo attachment states"
```

---

### Task 7: Implement MoveIt attach/detach and world synchronization

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/moveit_scene_adapter.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/moveit_scene_adapter.cpp`
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/moveit_scene_executor.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/moveit_scene_executor.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Test: `src/panda_gazebo_demo/test/pick_place/test_moveit_scene_executor.cpp`

**Interfaces:**
- Produces `IMoveItSceneAdapter`, `MoveItSceneState`, and configured attach/detach/sync executors.

- [ ] **Step 1: Write failing fake-adapter tests**

```cpp
TEST(MoveItSceneExecutor, AttachUsesPandaHandAndExactTouchLinks);
TEST(MoveItSceneExecutor, AttachWaitsForWorldAttachedMutualExclusion);
TEST(MoveItSceneExecutor, DetachWaitsForReturnToWorld);
TEST(MoveItSceneExecutor, RecoveryDetachNoOpsWhenAlreadyDetached);
TEST(MoveItSceneExecutor, SyncUsesBeforeGazeboPoseAndPreservesGeometry);
TEST(MoveItSceneExecutor, SyncRejectsMissingGazeboPose);
```

- [ ] **Step 2: Run RED**

Expected: missing scene adapter.

- [ ] **Step 3: Implement the interface and ROS adapter**

```cpp
struct MoveItSceneState
{
  bool coke_in_world{false};
  bool coke_attached{false};
  std::string attached_link;
  std::set<std::string> touch_links;
  std::optional<Pose3d> coke_world_pose;
};

class IMoveItSceneAdapter
{
public:
  virtual ~IMoveItSceneAdapter() = default;
  virtual ActionResult attachCoke(const std::string &, const std::vector<std::string> &) = 0;
  virtual ActionResult detachCoke() = 0;
  virtual ActionResult syncCokeWorldPose(const Pose3d &) = 0;
  virtual std::optional<MoveItSceneState> observe() = 0;
};
```

Configured executors use `ExecutionContext.before` for idempotency and synchronization. The real adapter polls at `0.05 s` up to `2.0 s`.

- [ ] **Step 4: Run GREEN and Planning Scene integration smoke tests**

Confirm exact world/attached mutual exclusion and full 6D pose synchronization.

- [ ] **Step 5: Commit**

```bash
git add src/panda_gazebo_demo
git commit -m "feat: implement MoveIt attachment and scene sync"
```

---

### Task 8: Implement shared motion evidence and all forward motion states

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/motion_plan_evidence.hpp`
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/moveit_motion_adapter.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/moveit_motion_adapter.cpp`
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/motion_state_action.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/motion_state_action.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/move_above_object_planner.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/descend_planner_executor.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/cartesian_plan_validation.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Test: `src/panda_gazebo_demo/test/pick_place/test_motion_plan_validation.cpp`
- Test: `src/panda_gazebo_demo/test/pick_place/test_motion_state_action.cpp`

**Interfaces:**
- Produces generic evidence and configured actions for `LIFT`, `MOVE_ABOVE_PLACE`, `DESCEND_TO_PLACE`, and `RETREAT`.
- Migrates existing MoveAbove/Descend internals to the same adapter without changing behavior.

- [ ] **Step 1: Write failing plan-evidence tests**

Cover:

```cpp
TEST(CarriedMotionPlan, RejectsMissingAttachedObjectEvidence);
TEST(CarriedMotionPlan, RejectsRelativePoseDrift);
TEST(CartesianLiftPlan, RejectsLateralMotion);
TEST(CartesianPlacePlan, RejectsUpwardSegment);
TEST(RetreatPlan, RejectsDownwardSegment);
TEST(PoseCarryPlan, RequiresTimedCollisionAwareTrajectory);
```

Add configured-action tests proving every state asks TargetPolicy for its transition and passes `carrying=true` only for Lift/transport/place descent.

- [ ] **Step 2: Run RED**

Expected: missing generic evidence/actions.

- [ ] **Step 3: Implement shared artifacts and validators**

```cpp
enum class MotionKind { POSE, CARTESIAN_UP, CARTESIAN_DOWN };

struct MotionStateConfig
{
  State state;
  State next_state;
  MotionKind kind;
  bool carrying;
};

struct MotionPlanEvidence
{
  double cartesian_fraction{1.0};
  std::size_t trajectory_points{0};
  double duration_seconds{0.0};
  double max_joint_jump{0.0};
  Pose3d start_tcp_pose;
  Pose3d end_tcp_pose;
  std::vector<Pose3d> tcp_path;
  bool collision_aware{false};
  bool attached_object_in_model{false};
};
```

Create configured instances for all four forward states. Preserve TOTG timing and the current Cartesian endpoint/FK validation.

- [ ] **Step 4: Run GREEN plus plan-only smoke tests**

For each motion state, use execute checkpoints followed by `resume + plan_only`. Confirm no actual TCP, joint, or Coke pose movement and no recovery checkpoint.

Implementation sequencing note (2026-07-23): Task 8 can perform this live smoke for the
already reachable `MOVE_ABOVE_OBJECT` and `DESCEND` states. Real execute checkpoints for
`LIFT`, `MOVE_ABOVE_PLACE`, `DESCEND_TO_PLACE`, and `RETREAT` require the forward contracts
from Task 9 and complete runtime registration from Task 11. Their checkpoint-based plan-only
smoke tests are therefore completed in Task 11/12; Task 8 must not synthesize checkpoints to
bypass those fail-closed prerequisites.

- [ ] **Step 5: Commit**

```bash
git add src/panda_gazebo_demo
git commit -m "feat: implement carried and release motions"
```

---

### Task 9: Implement every forward TransitionContract

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/pick_place_contracts.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/pick_place_contracts.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/transition_contract.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Test: `src/panda_gazebo_demo/test/pick_place/test_forward_contracts.cpp`

**Interfaces:**
- Produces one factory per transition, each returning an explicit `ITransitionContract` instance.
- Reuses Task 4 validation primitives and TargetPolicy.

- [ ] **Step 1: Write one failing pre/post test per forward transition**

Required test names:

```text
CloseRequiresPickPoseAndDetachedStableCoke
CloseAcceptsSymmetricStoppedCokeWidthGrasp
GazeboAttachRequiresValidGrasp
GazeboAttachRequiresOnlyGazeboToChange
MoveItAttachRequiresExactAttachedMetadata
LiftPreservesBothAttachmentsAndRelativePose
MoveAbovePlacePreservesCarriedObject
DescendToPlaceRequiresSupportedPlacePose
OpenAtPlaceKeepsBothAttachmentsAndCokeStable
GazeboDetachRequiresOpenFingersAndCokeSettling
MoveItDetachDefersCrossWorldPoseEquality
SyncRequiresCrossWorldPoseEquality
RetreatRequiresOpenDetachedSynchronizedWorld
DoneRequiresAllFinalInvariants
```

- [ ] **Step 2: Run RED**

Expected: factories missing.

- [ ] **Step 3: Implement explicit factories**

Expose:

```cpp
struct PickPlaceContractConfig
{
  double tcp_position_tolerance{0.005};
  double tcp_orientation_tolerance_rad{0.035};
  double coke_position_tolerance{0.003};
  double coke_orientation_tolerance_rad{0.035};
  double carried_relative_position_tolerance{0.003};
  double carried_relative_orientation_tolerance_rad{0.035};
  GripperLimits gripper{};
};

using Contract = TransitionContractRegistry::ITransitionContract;
using TargetPolicyPtr = std::shared_ptr<const PickPlaceTargetPolicy>;

std::shared_ptr<const Contract> makeCloseToGazeboAttachContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
std::shared_ptr<const Contract> makeGazeboToMoveItAttachContract(
  PickPlaceContractConfig config);
std::shared_ptr<const Contract> makeMoveItAttachToLiftContract(
  PickPlaceContractConfig config);
std::shared_ptr<const Contract> makeLiftToMoveAbovePlaceContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
std::shared_ptr<const Contract> makeMoveAbovePlaceToDescendContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
std::shared_ptr<const Contract> makeDescendPlaceToOpenContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
std::shared_ptr<const Contract> makeOpenToGazeboDetachContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
std::shared_ptr<const Contract> makeGazeboToMoveItDetachContract(
  PickPlaceContractConfig config);
std::shared_ptr<const Contract> makeMoveItDetachToSyncContract(
  PickPlaceContractConfig config);
std::shared_ptr<const Contract> makeSyncToRetreatContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
std::shared_ptr<const Contract> makeRetreatToDoneContract(
  TargetPolicyPtr target_policy, PickPlaceContractConfig config);
```

Every failure includes metrics for TCP error, Coke drift, finger positions/velocities, attachment booleans, or carried relative-pose error as applicable.

- [ ] **Step 4: Run GREEN and coverage validation**

Add an assertion that every forward transition in `TransitionTable` has a contract and every planner state has a plan validator.

- [ ] **Step 5: Commit**

```bash
git add src/panda_gazebo_demo
git commit -m "feat: add complete forward transition contracts"
```

---

### Task 10: Implement carrying recovery and idempotent cleanup

**Files:**
- Modify: `src/panda_gazebo_demo/src/pick_place/motion_state_action.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/gripper_state_executor.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/gazebo_attachment_executor.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/moveit_scene_executor.cpp`
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/recovery_contracts.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/recovery_contracts.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Test: `src/panda_gazebo_demo/test/pick_place/test_recovery_workflow.cpp`

**Interfaces:**
- Produces all recovery executors/validators using the adapters already implemented.
- Consumes `IRecoveryPolicy`, checkpoint v3, and recovery targets.

- [ ] **Step 1: Write failing workflow tests**

```cpp
TEST(RecoveryWorkflow, CarryFailureReturnsToPickBeforeOpening);
TEST(RecoveryWorkflow, CarryFailureAtPlaceSurfaceOpensBeforeCleanup);
TEST(RecoveryWorkflow, GazeboOnlyAttachNeverPlansCarryingMotion);
TEST(RecoveryWorkflow, AlreadyDetachedCleanupNoOpsAndSynchronizes);
TEST(RecoveryWorkflow, RecoveryActionFailureStopsImmediately);
TEST(RecoveryWorkflow, FinalErrorPreservesOriginalAndRecoveryFailure);
TEST(RecoveryWorkflow, ResumeReclassifiesChangedAttachmentFacts);
```

Assert exact successful carrying recovery order:

```text
RECOVER_LIFT_TO_SAFE_HEIGHT
RECOVER_MOVE_ABOVE_PICK
RECOVER_DESCEND_TO_PICK
RECOVER_OPEN_GRIPPER
RECOVER_DETACH_GAZEBO
RECOVER_DETACH_MOVEIT
RECOVER_SYNC_WORLD_OBJECT
RECOVER_RETREAT
ERROR
```

- [ ] **Step 2: Run RED**

Expected: recovery actions/contracts not registered.

- [ ] **Step 3: Configure recovery actions and contracts**

Use the same motion, gripper, Gazebo, and MoveIt classes with recovery-specific `State` configs. All detach/open/retract actions check `ExecutionContext.before` and no-op only when their complete postcondition already holds.

Task 12 real recovery execution also proved that a checkpoint may already be within the recovery
motion's 6D target tolerance, producing a one-point zero-duration Cartesian result. Every recovery
motion is therefore configured for a generic, validated no-op when a fresh stationary TCP is
already at the policy target. Execute re-resolves and rechecks the target, and the ordinary
post-contract and checkpoint still run; the trajectory validator remains strict and forward
motions do not gain no-op semantics.

Task 12 critical review also unified every non-static forward runtime failure after executor,
contract, and plan-validator coverage checks. Preconditions, observation, planning, plan
validation, execution, post-validation, and forward checkpoint persistence now all cancel/stop,
observe a stationary world, classify current facts, and enter recovery. Recovery checkpoint write
failure does not authorize abandoning a carried Coke: the current process continues emergency
recovery, records `recovery_checkpoint_persisted=0`, never claims the missing durable boundary,
and ultimately reports `ERROR` with the original and persistence context.

Recovery contract preconditions never assume the originally failed state reached its intended endpoint. They validate the actual snapshot and require both attachments for carrying recovery.

- [ ] **Step 4: Run GREEN and failure-injection matrix**

Run core tests for every recovery state failure. Verify no recovery transition continues after its own failure.

- [ ] **Step 5: Commit**

```bash
git add src/panda_gazebo_demo
git commit -m "feat: implement complete pick-place recovery"
```

---

### Task 11: Wire node configuration, registries, logging, and controller parameters

**Files:**
- Modify: `src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp`
- Modify: `src/panda_gazebo_demo/config/controllers.yaml`
- Modify: `src/panda_gazebo_demo/launch/panda_gazebo.launch.py`
- Modify: `src/panda_gazebo_demo/package.xml`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Test: `src/panda_gazebo_demo/test/pick_place/test_registration_coverage.cpp`

**Interfaces:**
- Produces the fully wired executable and complete configuration hash.

- [ ] **Step 1: Write failing registration coverage test**

Construct the same registries as the node through a new pure factory:

```cpp
struct PickPlaceRuntimeRegistries
{
  StateActionRegistry actions;
  PlanValidatorRegistry plan_validators;
  TransitionContractRegistry contracts;
};
```

Test that every nonterminal forward and recovery state has exactly the required executor, every motion state has a planner and plan validator, and every success transition has a contract.

- [ ] **Step 2: Run RED**

Expected: missing runtime factory and registrations.

- [ ] **Step 3: Add parameters and registrations**

Declare every approved parameter and validate finite ranges. Include them in `configurationHash`, including TargetPolicy signature, gripper limits, Cartesian limits, attachment/scene timeouts, Coke settle settings, and recovery safe height.

Register all forward and recovery actions, plan validators, contracts, `FixedRecoveryPolicy`, world observer, execution evidence sink, and checkpoint store.

Log:

```text
TARGET_TCP_POSE / PLANNED_END_TCP_POSE / EXECUTED_END_TCP_POSE
CARTESIAN_FRACTION / TRAJECTORY_POINTS / MAX_JOINT_JUMP / TRAJECTORY_DURATION
FINGER1_POSITION / FINGER2_POSITION / FINGER1_VELOCITY / FINGER2_VELOCITY
GAZEBO_ATTACHED / MOVEIT_ATTACHED
COKE_POSE_BEFORE / COKE_POSE_AFTER / COKE_DRIFT
TCP_COKE_RELATIVE_POSE_ERROR
CHECKPOINT_PHASE / CHECKPOINT_SEQUENCE / NEXT_STATE
```

- [ ] **Step 4: Run GREEN, linters, and explicit cppcheck**

```bash
colcon build --packages-select panda_gazebo_demo --symlink-install
colcon test --packages-select panda_gazebo_demo --event-handlers console_direct+
AMENT_CPPCHECK_ALLOW_SLOW_VERSIONS=1 colcon test \
  --packages-select panda_gazebo_demo --ctest-args -R cppcheck
colcon test-result --verbose
```

Expected: zero failures; cppcheck must actually execute.

- [ ] **Step 5: Commit**

```bash
git add src/panda_gazebo_demo
git commit -m "feat: wire complete pick-place runtime"
```

---

### Task 12: Add headless end-to-end and recovery verification

**Files:**
- Create: `src/panda_gazebo_demo/test/headless/run_pick_place_e2e.sh`
- Create: `src/panda_gazebo_demo/test/headless/assert_pick_place_log.py`
- Create: `src/panda_gazebo_demo/test/headless/run_recovery_scenarios.sh`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Modify: `src/panda_gazebo_demo/README.md`

**Interfaces:**
- Produces repeatable headless smoke/e2e commands and evidence extraction.
- Consumes the completed executable, reset script, launch file, and structured logs.

- [ ] **Step 1: Write failing log assertions first**

`assert_pick_place_log.py` must reject a fixture missing any of:

```text
DONE terminal status
all expected forward states in order
all motion plan evidence
open final gripper
Gazebo detached
MoveIt detached
final Coke near (0.30,0.20,0.836)
cross-world Coke pose consistency
```

Add failure fixtures for incomplete Cartesian fraction, missing MoveIt detach, and final Coke outside tolerance. Run the script and observe those fixtures fail.

- [ ] **Step 2: Implement headless orchestration**

The script must:

1. launch `panda_gazebo.launch.py headless:=true`;
2. wait for Gazebo, MoveGroup, controllers, `/joint_states`, and attachment output;
3. run `reset_coke.sh` and verify detached Coke at the pick pose;
4. run one full state-machine execution with a unique `simulation_session_id`;
5. capture logs and validate final invariants;
6. terminate only processes started by the script.

Recovery scenarios establish and test:

```text
Gazebo attached / MoveIt detached -> cleanup without carried motion
both attached while carrying -> return to pick before release
Gazebo detached / MoveIt attached -> detach MoveIt, sync, retreat
```

The real recovery harness converts a forward schema-v3 checkpoint at each observed boundary to
`RECOVERY`, intentionally stores a wrong recovery next-state hint, and resumes. RecoveryPolicy must
reclassify current durable Gazebo and MoveIt facts. A newly constructed observer is allowed a
bounded wait for Coke stationary sampling before the first recovery contract.

- [ ] **Step 3: Run one normal headless E2E and three recovery scenarios**

Expected: all scripts return zero and produce retained log artifacts under `build/panda_gazebo_demo/test_logs/`.

- [ ] **Step 4: Run the course acceptance three times**

Reset between runs. All three runs must reach `DONE`, place Coke within tolerance, finish open/detached/synchronized, and show no skipped plan or validator.

- [ ] **Step 5: Run the entire verification suite once more**

```bash
colcon build --packages-select panda_gazebo_demo --symlink-install
colcon test --packages-select panda_gazebo_demo --event-handlers console_direct+
AMENT_CPPCHECK_ALLOW_SLOW_VERSIONS=1 colcon test \
  --packages-select panda_gazebo_demo --ctest-args -R cppcheck
colcon test-result --verbose
```

Expected: all tests pass, no tests are skipped while reported as passed, and the working tree contains only intended source/docs/test changes.

- [ ] **Step 6: Commit**

```bash
git add src/panda_gazebo_demo
git commit -m "test: verify complete Panda pick-place workflow"
```

---

## Final review checklist

Post-implementation review hardening added TDD coverage for planned-start joint evidence and
execute-time state drift, delayed gripper goal acceptance, event-loss-safe initial detach,
non-descending recovery safe height, policy-derived 6D Coke support poses, configured observation
and recovery no-op thresholds, null transition-contract coverage, non-finite 6DoF observations,
checkpoint-to-live named-joint drift, and plan-only target/endpoint 6DoF mismatch. These behaviors
are part of the Task 12 verification boundary and configuration hash.

- [ ] Every fixed target is sourced from `FixedPickPlaceTargetPolicy`.
- [ ] Every planner has a registered plan validator.
- [ ] Every forward/recovery executor has a transition contract.
- [ ] Gazebo and MoveIt partial attachment combinations are explicitly handled.
- [ ] No carrying recovery opens or detaches in the air.
- [ ] Cancel success means acknowledgement plus stationary observed joints.
- [ ] Plan-only never executes or writes a physical/recovery checkpoint.
- [ ] Recovery resume re-observes and reclassifies the world.
- [ ] Final `DONE` invariants include safe TCP, open fingers, both detached, stable Coke at place, and cross-world pose consistency.
- [ ] Unit, adapter, linter, explicit cppcheck, headless, recovery, and three-run acceptance evidence are all retained.
