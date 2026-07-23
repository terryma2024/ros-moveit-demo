# Retreat Ready-and-Close Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `RETREAT -> DONE` and `RECOVER_RETREAT -> ERROR` return the Panda arm to MoveIt's `ready` named target and close the gripper, while preserving their different task-result semantics.

**Architecture:** Add a typed MoveIt named-target planning path and a focused `ReadyRetreatAction` that composes it with the existing gripper adapter. Resolve `ready` from the loaded MoveIt SRDF once, inject the resolved joint map into the action, plan validator, and transition contracts, and never duplicate Panda joint values in C++ or shell code. The state graph remains unchanged: normal retreat ends at `DONE`; recovery retreat reaches `ERROR` after the same verified physical reset.

**Tech Stack:** C++17, ROS 2 Jazzy, MoveIt 2 `MoveGroupInterface`, GoogleTest, ament/colcon.

## Global Constraints

- Keep `RETREAT -> DONE` and `RECOVER_RETREAT -> ERROR`; `RECOVER_RETREAT` must never report task success.
- Resolve the configurable named target `ready` from MoveIt's SRDF; do not hard-code its seven joint values.
- Fail closed for a missing adapter, unresolved named target, mismatched typed plan artifact, empty trajectory, invalid planned endpoint, arm execution failure, intermediate observation failure, or gripper failure.
- In execute mode execute arm-to-ready, observe stationary ready joints, then command close-gripper; in plan-only never command the gripper.
- Both transition contracts remain the single validator for post-action completion and resume at the adjacent boundary.
- Retain detached/synchronized/stable Coke invariants and the normal place-completion check.
- Never run `ament_uncrustify --reformat`.

---

### Task 1: Typed named-target MoveIt planning and pure validation

**Files:**
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/motion_plan_evidence.hpp`
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/named_target_validation.hpp`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/moveit_motion_adapter.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/moveit_motion_adapter.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/motion_plan_validation.cpp`
- Create: `src/panda_gazebo_demo/src/pick_place/named_target_validation.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Test: `src/panda_gazebo_demo/test/pick_place/test_motion_plan_validation.cpp`

**Interfaces:**
- Produces `NamedTargetPlanningRequest { State state; State next_state; std::string target_name; }`.
- Extends `IMoveItMotionAdapter` with `planNamedTarget(const NamedTargetPlanningRequest &, const ObservationResult &)` and `namedTargetJointPositions(const std::string &) -> std::optional<std::map<std::string, double>>`.
- Extends `MotionPlanEvidence` with `std::optional<std::string> named_target`, `planned_end_joint_positions`, and `target_joint_positions`.
- Produces `NamedTargetPlanValidator(State, State, std::string, std::map<std::string, double>, double)`.
- Produces `validateNamedJointTarget(const WorldSnapshot &, const std::map<std::string, double> &, double) -> ValidationResult`.

- [ ] **Step 1: Write failing pure validation tests**

Add `NamedTargetPlanValidator` tests with a minimal `MotionPlanEvidence`: accept a nonempty
`MotionKind::NAMED_TARGET` plan whose state, next state, named target, expected target map, and
planned endpoint map agree; reject each of an empty trajectory, wrong transition, absent named
target, missing requested joint, and endpoint delta greater than `0.010`.

```cpp
TEST(NamedTargetPlanValidator, RejectsWrongPlannedEndpoint)
{
  MotionPlanEvidence evidence;
  evidence.state = State::RETREAT;
  evidence.next_state = State::DONE;
  evidence.kind = MotionKind::NAMED_TARGET;
  evidence.named_target = "ready";
  evidence.trajectory_points = 2;
  evidence.target_joint_positions = {{"panda_joint1", 0.0}};
  evidence.planned_end_joint_positions = {{"panda_joint1", 0.02}};

  const NamedTargetPlanValidator validator(
    State::RETREAT, State::DONE, "ready", {{"panda_joint1", 0.0}}, 0.010);
  EXPECT_FALSE(validator.validate(State::RETREAT, WorldSnapshot{}, evidence).ok);
}
```

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```bash
colcon build --packages-select panda_gazebo_demo --event-handlers console_direct+ && \
./build/panda_gazebo_demo/test_motion_plan_validation \
  --gtest_filter='NamedTargetPlanValidator.*'
```

Expected: compilation fails because `NAMED_TARGET` and `NamedTargetPlanValidator` do not exist.

- [ ] **Step 3: Add the typed request and validator**

Add `NAMED_TARGET` without changing TCP pose planning. The validator must first dynamic-cast to
`MotionPlanEvidence`, then check the configured state/edge, named target, nonempty trajectory,
exact target-joint key set, finite values, and absolute per-joint endpoint error at or below the
configured tolerance. Return failures with these exact codes:

```cpp
"INVALID_NAMED_TARGET_PLAN_ARTIFACT"
"NAMED_TARGET_TRAJECTORY_EMPTY"
"NAMED_TARGET_MISMATCH"
"NAMED_TARGET_JOINTS_MISSING"
"NAMED_TARGET_ENDPOINT_MISMATCH"
```

Place `validateNamedJointTarget` in `named_target_validation.cpp`; it checks the observed map and
returns `NAMED_TARGET_JOINTS_MISSING` or `NAMED_TARGET_ENDPOINT_MISMATCH`. Both the new action and
the transition contracts use this function, so physical postconditions and resume validation have
identical named-joint logic.

- [ ] **Step 4: Implement MoveIt SRDF resolution and planning**

Implement the two adapter methods using the adapter's planning group:

```cpp
const auto values = move_group.getNamedTargetValues(request.target_name);
if (values.empty() || !move_group.setNamedTarget(request.target_name)) {
  return planningFailure(FailureCategory::CONFIGURATION,
    "NAMED_TARGET_UNAVAILABLE", "MoveIt named target is unavailable: " + request.target_name);
}
```

Configure the same current state, velocity/acceleration scaling, Planning Scene object checks, and
collision-aware `move_group.plan(plan)` path used by pose planning. Build evidence from the returned
trajectory, set `kind = MotionKind::NAMED_TARGET`, `named_target`, `target_joint_positions`, and
`planned_end_joint_positions` from the final trajectory point. Log
`NAMED_JOINT_TARGET state=<state> target=<target>`. `namedTargetJointPositions` returns an empty
optional when MoveIt cannot resolve a nonempty complete target map; it must not invent joint values.

- [ ] **Step 5: Re-run focused tests and build**

Run the Step 2 command and then:

```bash
colcon build --packages-select panda_gazebo_demo --event-handlers console_direct+
```

Expected: every `NamedTargetPlanValidator.*` test passes and the package builds.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/motion_plan_evidence.hpp \
  src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/named_target_validation.hpp \
  src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/moveit_motion_adapter.hpp \
  src/panda_gazebo_demo/src/pick_place/motion_plan_validation.cpp \
  src/panda_gazebo_demo/src/pick_place/named_target_validation.cpp \
  src/panda_gazebo_demo/src/pick_place/moveit_motion_adapter.cpp \
  src/panda_gazebo_demo/CMakeLists.txt \
  src/panda_gazebo_demo/test/pick_place/test_motion_plan_validation.cpp
git commit -m "feat: add MoveIt named target planning"
```

### Task 2: Ready-retreat composite state action

**Files:**
- Create: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/ready_retreat_action.hpp`
- Create: `src/panda_gazebo_demo/src/pick_place/ready_retreat_action.cpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Test: `src/panda_gazebo_demo/test/pick_place/test_ready_retreat_action.cpp`

**Interfaces:**
- Consumes the Task 1 named-target adapter API, `IGripperCommandAdapter`, `IWorldObserver`,
  `GripperLimits`, and a resolved ready joint map.
- Produces `ReadyRetreatConfig { State state; State next_state; std::string named_target; std::map<std::string, double> ready_joint_positions; double joint_tolerance; double close_position; double max_effort; GripperLimits gripper; }`.
- Produces `ReadyRetreatAction : IStatePlanner, IStateExecutor`.

- [ ] **Step 1: Write failing action ordering tests**

Use recording motion, gripper, and world-observer fakes to assert all of the following:

```cpp
TEST(ReadyRetreatAction, ExecutesReadyArmThenVerifiesThenClosesGripper)
{
  auto motion = std::make_shared<RecordingNamedTargetMotionAdapter>();
  auto gripper = std::make_shared<RecordingGripperAdapter>();
  auto observer = std::make_shared<RecordingWorldObserver>(readySnapshot());
  ReadyRetreatAction action(motion, gripper, observer, readyConfig(State::RETREAT, State::DONE));
  const auto plan = action.plan(State::RETREAT, State::DONE, ObservationResult{readySnapshot(), {}});
  ASSERT_EQ(action.execute({State::RETREAT, State::DONE, readySnapshot(), plan.artifact}).status,
    ActionStatus::SUCCEEDED);
  EXPECT_EQ(motion->events, (std::vector<std::string>{"motion.execute"}));
  EXPECT_EQ(observer->events, (std::vector<std::string>{"observer.observe"}));
  EXPECT_EQ(gripper->events, (std::vector<std::string>{"gripper.command"}));
}

TEST(ReadyRetreatAction, PlanOnlyDoesNotCommandTheGripper)
{
  auto gripper = std::make_shared<RecordingGripperAdapter>();
  ReadyRetreatAction action(recordingMotion(), gripper, recordingObserver(),
    readyConfig(State::RETREAT, State::DONE));
  EXPECT_EQ(action.plan(State::RETREAT, State::DONE, ObservationResult{readySnapshot(), {}})
    .action.status, ActionStatus::SUCCEEDED);
  EXPECT_EQ(gripper->command_calls, 0);
}

TEST(ReadyRetreatAction, ArmFailurePreventsGripperClose)
{
  auto motion = failingMotion();
  auto gripper = std::make_shared<RecordingGripperAdapter>();
  ReadyRetreatAction action(motion, gripper, recordingObserver(),
    readyConfig(State::RETREAT, State::DONE));
  EXPECT_EQ(action.execute(validReadyExecutionContext()).status, ActionStatus::FAILED);
  EXPECT_EQ(gripper->command_calls, 0);
}
```

Also test both legal edges (`RETREAT -> DONE`, `RECOVER_RETREAT -> ERROR`), rejects a mismatched
edge before dependency calls, and rejects an intermediate observation that is missing, nonstationary,
or outside ready-joint tolerance before close-gripper.

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```bash
colcon build --packages-select panda_gazebo_demo --event-handlers console_direct+ && \
./build/panda_gazebo_demo/test_ready_retreat_action
```

Expected: compilation fails because `ready_retreat_action.hpp` does not exist.

- [ ] **Step 3: Implement the narrow composite action**

`plan()` accepts only its configured edge and calls:

```cpp
return motion_->planNamedTarget(
  {current_state, next_state, config_.named_target}, observation);
```

`execute()` validates the typed named-target evidence, invokes `motion_->execute`, observes through
the injected `IWorldObserver`, verifies `fresh`, `arm_stationary`, and every configured ready joint
within `joint_tolerance`, then invokes:

```cpp
return gripper_->command(config_.close_position, config_.max_effort);
```

Use `READY_RETREAT_*` failure codes, including `READY_RETREAT_OBSERVER_MISSING`,
`READY_RETREAT_OBSERVATION_MISSING`, `READY_RETREAT_ARM_NOT_READY`, and
`READY_RETREAT_GRIPPER_ADAPTER_MISSING`. `cancel()` calls motion cancellation and gripper
`cancelAndWait()`, and returns failure if either cancellation fails.

- [ ] **Step 4: Re-run focused tests and build**

Run the Step 2 command. Expected: all `ReadyRetreatAction.*` tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/ready_retreat_action.hpp \
  src/panda_gazebo_demo/src/pick_place/ready_retreat_action.cpp \
  src/panda_gazebo_demo/CMakeLists.txt \
  src/panda_gazebo_demo/test/pick_place/test_ready_retreat_action.cpp
git commit -m "feat: add ready retreat action"
```

### Task 3: Terminal transition contracts and runtime registration

**Files:**
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/pick_place_runtime.hpp`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/pick_place_contracts.hpp`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/state_validation.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/pick_place_contracts.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/recovery_contracts.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/state_validation.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
- Test: `src/panda_gazebo_demo/test/pick_place/test_forward_contracts.cpp`
- Test: `src/panda_gazebo_demo/test/pick_place/test_recovery_workflow.cpp`
- Test: `src/panda_gazebo_demo/test/pick_place/test_registration_coverage.cpp`

**Interfaces:**
- Extends `PickPlaceRuntimeDependencies` with `std::shared_ptr<IWorldObserver> observer`.
- Extends `PickPlaceRuntimeConfig` with `ready_named_target`, `ready_joint_positions`, and
  `ready_joint_tolerance`, `gripper_close_position`, and `gripper_close_tolerance`.
- Produces `validateGripperClosed(const WorldSnapshot &, double target_position, double tolerance, const GripperLimits &) -> ValidationResult`.

- [ ] **Step 1: Write failing forward/recovery contract tests**

Update terminal fixtures to start with detached Coke and open fingers, then assert:

```cpp
EXPECT_TRUE(runtime.contracts.validatePrecondition(
  {State::RETREAT, State::DONE}, before_open_detached).ok);
EXPECT_FALSE(runtime.contracts.validate(
  {State::RETREAT, State::DONE}, before_open_detached,
  after_ready_but_open, succeeded()).ok);
EXPECT_FALSE(runtime.contracts.validate(
  {State::RECOVER_RETREAT, State::ERROR}, before_open_detached,
  after_closed_but_not_ready, succeeded()).ok);
EXPECT_TRUE(runtime.contracts.validate(
  {State::RECOVER_RETREAT, State::ERROR}, before_open_detached,
  after_ready_closed_detached, succeeded()).ok);
```

Keep the recovery workflow expectation `RunStatus::ERROR` and `current_state == State::ERROR`.
Update registration coverage so both retreat states remain planner/executor/plan-validator states,
but are not listed in the generic `kMotionStates` set.

- [ ] **Step 2: Run focused tests to verify RED**

Run:

```bash
colcon build --packages-select panda_gazebo_demo --event-handlers console_direct+ && \
./build/panda_gazebo_demo/test_forward_contracts \
  --gtest_filter='*Retreat*' && \
./build/panda_gazebo_demo/test_recovery_workflow \
  --gtest_filter='*RecoverRetreat*' && \
./build/panda_gazebo_demo/test_registration_coverage
```

Expected: terminal contracts still accept an open gripper and TCP vertical-retreat target, and the
factory still registers generic Cartesian actions for the two retreat states.

- [ ] **Step 3: Implement terminal ready-and-closed validation and apply it at both boundaries**

`validateGripperClosed` fails for missing/nonfinite finger positions/velocities, asymmetric
fingers, any finger farther than the configured close tolerance from `gripper_close_position`, or
nonstationary fingers. Preserve current retreat
preconditions: stationary, open fingers, detached/synchronized supported Coke, Planning Scene
objects, and cross-world equality. Replace only postcondition target checks with the named-joint
helper from Task 1 and `validateGripperClosed`. Keep normal place-completion checks.
Keep recovery postconditions detached/synchronized and remove its old `RECOVER_RETREAT` vertical
TCP target check. The failure edge remains `RECOVER_RETREAT -> ERROR`.

Register one `ReadyRetreatAction` and one `NamedTargetPlanValidator` for each of:

```cpp
{State::RETREAT, State::DONE}
{State::RECOVER_RETREAT, State::ERROR}
```

Remove these two entries from `kMotionConfigs`, leaving all other pose/Cartesian state registrations
unchanged. The registrations must be omitted or fail closed if `motion`, `gripper`, `observer`, or
the resolved ready-joint map is absent.

- [ ] **Step 4: Re-run focused tests and build**

Run the Step 2 command. Expected: terminal contracts require ready-and-closed physical state;
recovery still ends `ERROR`; coverage reports no missing executor, contract, or plan validator.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/pick_place_runtime.hpp \
  src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/pick_place_contracts.hpp \
  src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/state_validation.hpp \
  src/panda_gazebo_demo/src/pick_place/pick_place_contracts.cpp \
  src/panda_gazebo_demo/src/pick_place/recovery_contracts.cpp \
  src/panda_gazebo_demo/src/pick_place/state_validation.cpp \
  src/panda_gazebo_demo/src/pick_place/pick_place_runtime.cpp \
  src/panda_gazebo_demo/test/pick_place/test_forward_contracts.cpp \
  src/panda_gazebo_demo/test/pick_place/test_recovery_workflow.cpp \
  src/panda_gazebo_demo/test/pick_place/test_registration_coverage.cpp
git commit -m "feat: verify terminal ready retreat"
```

### Task 4: Runtime parameters, node wiring, and configuration identity

**Files:**
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/runtime_parameters.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/runtime_parameters.cpp`
- Modify: `src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp`
- Test: `src/panda_gazebo_demo/test/pick_place/test_registration_coverage.cpp`

**Interfaces:**
- Adds `std::string ready_named_target{"ready"}` and `double ready_joint_tolerance{0.010}` to
  `PickPlaceParameters`.
- Adds `double gripper_close_tolerance{0.004}` to `PickPlaceParameters`.
- Wires `MoveItMotionAdapter::namedTargetJointPositions(parameters.ready_named_target)` into
  `PickPlaceRuntimeConfig::ready_joint_positions`.

- [ ] **Step 1: Write failing runtime-parameter tests**

Extend `RuntimeParameters.DefaultsAreValidAndEveryBehaviorParameterChangesTheHash` so changing
either `ready_named_target` or `ready_joint_tolerance` changes the hash. Extend invalid-range tests
to reject an empty target, zero/nonfinite ready tolerance, and a nonpositive/nonfinite close
tolerance.

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```bash
colcon build --packages-select panda_gazebo_demo --event-handlers console_direct+ && \
./build/panda_gazebo_demo/test_registration_coverage \
  --gtest_filter='RuntimeParameters.*'
```

Expected: compilation fails because the parameters do not exist.

- [ ] **Step 3: Declare, validate, hash, and wire the values**

Declare both ready ROS parameters beside the existing motion parameters. Validate nonempty target
and positive finite ready tolerance, append both values to `pickPlaceConfigurationHash`, and set
the runtime config fields. Validate and hash `gripper_close_tolerance` with the other gripper
safety values. Construct `GazeboWorldObserver` before runtime registration as a shared observer;
inject that same observer into `PickPlaceRuntimeDependencies` and use it as the runner observer.
Resolve the ready named target before factory registration:

```cpp
const auto ready_joints = motion_adapter->namedTargetJointPositions(parameters.ready_named_target);
if (!ready_joints) {
  RCLCPP_ERROR(logger, "NAMED_TARGET_UNAVAILABLE: %s", parameters.ready_named_target.c_str());
  rclcpp::shutdown();
  return EXIT_FAILURE;
}
runtime_config.ready_joint_positions = *ready_joints;
```

This is the only state-machine source for ready joint values. It must run for plan-only and execute
startup; resume and checkpoints bind the target name/tolerance through the configuration hash.

- [ ] **Step 4: Re-run focused tests and build**

Run the Step 2 command and:

```bash
colcon build --packages-select panda_gazebo_demo --event-handlers console_direct+
```

Expected: default parameters remain valid, changed ready parameters alter the hash, and the node
builds with a single shared physical observer.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/runtime_parameters.hpp \
  src/panda_gazebo_demo/src/pick_place/runtime_parameters.cpp \
  src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp \
  src/panda_gazebo_demo/test/pick_place/test_registration_coverage.cpp
git commit -m "feat: configure ready retreat target"
```

### Task 5: End-to-end regression coverage and verification

**Files:**
- Modify: `src/panda_gazebo_demo/test/pick_place/test_forward_contracts.cpp`
- Modify: `src/panda_gazebo_demo/test/pick_place/test_recovery_workflow.cpp`
- Modify only explicitly required files for manual lint corrections.

**Interfaces:**
- Consumes all Tasks 1–4.
- Produces automated proof that normal terminal success is ready-and-closed, while recovery is
  ready-and-closed but terminal `ERROR`.

- [ ] **Step 1: Add failing workflow-level assertions**

In the normal fake workflow, after `RETREAT` update the observed snapshot to ready joints and closed
fingers; assert the result is `RunStatus::DONE`. In the recovery fake workflow, make the same final
physical observation; assert `RunStatus::ERROR`, `current_state == State::ERROR`, and the retained
original forward failure code is unchanged.

- [ ] **Step 2: Run workflow tests to verify the intended boundary**

Run:

```bash
colcon build --packages-select panda_gazebo_demo --event-handlers console_direct+ && \
./build/panda_gazebo_demo/test_forward_contracts && \
./build/panda_gazebo_demo/test_recovery_workflow
```

Expected: tests pass after Tasks 1–4; any failure identifies a contract/action integration gap.

- [ ] **Step 3: Run complete automated verification**

Run:

```bash
colcon test --packages-select panda_gazebo_demo --event-handlers console_direct+
colcon test-result --verbose
git diff --check
```

Run configured lint checks read-only. Do not invoke `ament_uncrustify --reformat`; make any required
format corrections through targeted patches and rerun the affected check.

Expected: zero test failures and no whitespace errors.

- [ ] **Step 4: Perform simulator evidence run when the local stack is available**

Run a successful execute workflow to `stop_after:=RETREAT`, then verify the checkpoint/logs contain
the ready joint values and closed finger positions before `DONE`. Run a deliberately failing forward
workflow that reaches recovery with `stop_after:=RECOVER_RETREAT`; verify its checkpoint/logs show
the same ready-and-closed state while the runner result is `ERROR` and preserves the original
failure. If Gazebo/MoveIt services are unavailable, retain the automated evidence and report the
service-level blocker without claiming physical verification.

- [ ] **Step 5: Commit Task 5**

```bash
git add src/panda_gazebo_demo/test/pick_place/test_forward_contracts.cpp \
  src/panda_gazebo_demo/test/pick_place/test_recovery_workflow.cpp
git commit -m "test: cover ready retreat terminal behavior"
```
