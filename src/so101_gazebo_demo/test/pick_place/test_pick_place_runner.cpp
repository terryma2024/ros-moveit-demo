#include <gtest/gtest.h>

#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <future>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "so101_gazebo_demo/pick_place/runner.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

namespace
{

using pick_place::ActionResult;
using pick_place::ActionStatus;
using pick_place::Checkpoint;
using pick_place::CheckpointPhase;
using pick_place::Failure;
using pick_place::FailureCategory;
using pick_place::ObservationResult;
using pick_place::PlanArtifact;
using pick_place::PlanResult;
using pick_place::RunMode;
using pick_place::State;
using pick_place::TransitionKey;
using pick_place::ValidationResult;
using pick_place::WorldSnapshot;

Failure failure(FailureCategory category, std::string code)
{
  return {category, std::move(code), "injected test failure", {}};
}

WorldSnapshot snapshot(std::string session = "session-a")
{
  WorldSnapshot value;
  value.fresh = true;
  value.arm_stationary = true;
  value.gripper_open = true;
  value.tcp_pose_world = {0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 1.0};
  value.joint_positions = {{"joint_a", 0.25}, {"joint_b", -0.5}};
  value.joint_velocities = {{"joint_a", 0.0}, {"joint_b", 0.0}};
  value.moveit_world_object_poses = {{"object", {0.4, 0.5, 0.6, 0.0, 0.0, 0.0, 1.0}}};
  value.moveit_task_object_attached = false;
  value.moveit_task_object_attached_link = "tool_link";
  value.moveit_task_object_touch_links = {"left_contact", "right_contact"};
  value.gazebo_task_object_pose_world = {0.4, 0.5, 0.6, 0.0, 0.0, 0.0, 1.0};
  value.gazebo_task_object_attached = false;
  value.gazebo_task_object_stationary = true;
  value.simulation_session_id = std::move(session);
  return value;
}

void setExpected(Checkpoint & checkpoint, const WorldSnapshot & value)
{
  checkpoint.expected.tcp_pose_world = value.tcp_pose_world;
  checkpoint.expected.gripper_open = value.gripper_open;
  checkpoint.expected.joint_positions = value.joint_positions;
  checkpoint.expected.moveit_world_object_poses = value.moveit_world_object_poses;
  checkpoint.expected.moveit_task_object_attached = value.moveit_task_object_attached;
  checkpoint.expected.gazebo_task_object_pose_world = value.gazebo_task_object_pose_world;
  checkpoint.expected.gazebo_task_object_attached = value.gazebo_task_object_attached;
  checkpoint.expected.gazebo_task_object_stationary = value.gazebo_task_object_stationary;
  checkpoint.expected.required_world_objects = {"object"};
}

std::string event(const char * operation, State state)
{
  return std::string(operation) + ":" + pick_place::toString(state);
}

struct Scenario
{
  std::vector<std::string> events;
  WorldSnapshot world{snapshot()};
  std::optional<State> fail_plan;
  std::optional<State> fail_plan_validation;
  std::optional<State> fail_execute;
  std::optional<State> fail_precondition;
  std::optional<State> transient_precondition_state;
  int transient_precondition_failures{0};
  std::string transient_precondition_failure_code{"ARM_NOT_QUIESCENT"};
  std::optional<State> fail_transition;
  std::optional<State> transient_transition_state;
  int transient_transition_failures{0};
  std::string transient_transition_failure_code{"MOTION_JOINT_ENDPOINT_MISMATCH"};
  std::optional<int> fail_observation_call;
  int observation_failure_count{1};
  std::string observation_failure_code{"OBSERVATION_INJECTED"};
  std::chrono::milliseconds observation_failure_delay{0};
  bool precondition_has_late_environment_failure{false};
  bool cancel_makes_arm_nonstationary{false};
  std::map<std::string, double> execute_failure_metrics;
  ActionResult cancel_result{ActionStatus::SUCCEEDED, std::nullopt};
  int observation_calls{0};
  int planner_calls{0};
  int executor_calls{0};
  int cancel_calls{0};
  int precondition_calls{0};
  int transition_calls{0};
  int validation_calls{0};
  std::optional<WorldSnapshot> planned_world;
  std::optional<WorldSnapshot> executed_world;
};

class FakeObserver final : public pick_place::IWorldObserver
{
public:
  explicit FakeObserver(Scenario & scenario) : scenario_(scenario) {}

  ObservationResult observe() override
  {
    scenario_.events.emplace_back("observe");
    ++scenario_.observation_calls;
    if (scenario_.fail_observation_call &&
        scenario_.observation_calls >= *scenario_.fail_observation_call &&
        scenario_.observation_calls <
          *scenario_.fail_observation_call + scenario_.observation_failure_count) {
      std::this_thread::sleep_for(scenario_.observation_failure_delay);
      return {std::nullopt,
              failure(FailureCategory::OBSERVATION, scenario_.observation_failure_code)};
    }
    return {scenario_.world, std::nullopt};
  }

private:
  Scenario & scenario_;
};

class FakePlanner final : public pick_place::IStatePlanner
{
public:
  FakePlanner(State state, Scenario & scenario) : state_(state), scenario_(scenario) {}

  PlanResult plan(State state, State, const ObservationResult & observation) override
  {
    scenario_.events.push_back(event("plan", state));
    ++scenario_.planner_calls;
    scenario_.planned_world = observation.snapshot;
    if (scenario_.fail_plan == state_) {
      return {{ActionStatus::FAILED, failure(FailureCategory::PLANNING, "PLANNING_INJECTED")},
              nullptr};
    }
    auto artifact = std::make_shared<PlanArtifact>();
    artifact->trajectory_points = 2;
    return {{ActionStatus::SUCCEEDED, std::nullopt}, std::move(artifact)};
  }

private:
  State state_;
  Scenario & scenario_;
};

class FakePlanValidator final : public pick_place::IPlanValidator
{
public:
  FakePlanValidator(State state, Scenario & scenario) : state_(state), scenario_(scenario) {}

  [[nodiscard]] ValidationResult validate(State state, const WorldSnapshot &,
                                          const PlanArtifact &) const override
  {
    scenario_.events.push_back(event("plan-validate", state));
    ++scenario_.validation_calls;
    if (scenario_.fail_plan_validation == state_) {
      return {false, {failure(FailureCategory::PLAN_VALIDATION, "PLAN_INVALID_INJECTED")}, {}};
    }
    return {true, {}, {}};
  }

private:
  State state_;
  Scenario & scenario_;
};

class FakeExecutor final : public pick_place::IStateExecutor
{
public:
  FakeExecutor(State state, Scenario & scenario) : state_(state), scenario_(scenario) {}

  ActionResult execute(const pick_place::ExecutionContext & context) override
  {
    scenario_.events.push_back(event("execute", context.state));
    ++scenario_.executor_calls;
    scenario_.executed_world = context.before;
    if (scenario_.fail_execute == state_) {
      return {ActionStatus::FAILED,
              Failure{FailureCategory::EXECUTION, "EXECUTION_INJECTED", "injected test failure",
                      scenario_.execute_failure_metrics}};
    }
    switch (state_) {
      case State::ATTACH_GAZEBO:
        scenario_.world.gazebo_task_object_attached = true;
        break;
      case State::ATTACH_MOVEIT:
        scenario_.world.moveit_task_object_attached = true;
        break;
      case State::DETACH_GAZEBO:
      case State::RECOVER_DETACH_GAZEBO:
        scenario_.world.gazebo_task_object_attached = false;
        break;
      case State::DETACH_MOVEIT:
      case State::RECOVER_DETACH_MOVEIT:
        scenario_.world.moveit_task_object_attached = false;
        break;
      default:
        break;
    }
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  ActionResult cancel() override
  {
    scenario_.events.push_back(event("cancel", state_));
    ++scenario_.cancel_calls;
    if (scenario_.cancel_makes_arm_nonstationary) {
      scenario_.world.arm_stationary = false;
    }
    return scenario_.cancel_result;
  }

private:
  State state_;
  Scenario & scenario_;
};

class BlockingCancelExecutor final : public pick_place::IStateExecutor
{
public:
  ActionResult execute(const pick_place::ExecutionContext &) override
  {
    return {ActionStatus::FAILED, failure(FailureCategory::EXECUTION, "EXECUTION_INJECTED")};
  }

  ActionResult cancel() override
  {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      cancel_entered_ = true;
    }
    condition_.notify_all();
    std::unique_lock<std::mutex> lock(mutex_);
    condition_.wait(lock, [this]() { return terminal_; });
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  bool waitForCancel(std::chrono::milliseconds timeout)
  {
    std::unique_lock<std::mutex> lock(mutex_);
    return condition_.wait_for(lock, timeout, [this]() { return cancel_entered_; });
  }

  void makeTerminal()
  {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      terminal_ = true;
    }
    condition_.notify_all();
  }

private:
  std::mutex mutex_;
  std::condition_variable condition_;
  bool cancel_entered_{false};
  bool terminal_{false};
};

class FakeContract final : public pick_place::TransitionContractRegistry::ITransitionContract
{
public:
  FakeContract(State state, Scenario & scenario) : state_(state), scenario_(scenario) {}

  [[nodiscard]] ValidationResult validatePrecondition(const WorldSnapshot &) const override
  {
    scenario_.events.push_back(event("precondition", state_));
    ++scenario_.precondition_calls;
    if (scenario_.transient_precondition_state == state_ &&
        scenario_.transient_precondition_failures > 0) {
      --scenario_.transient_precondition_failures;
      return {
        false,
        {failure(FailureCategory::PRECONDITION, scenario_.transient_precondition_failure_code)},
        {}};
    }
    if (scenario_.fail_precondition == state_) {
      return {false, {failure(FailureCategory::PRECONDITION, "PRECONDITION_INJECTED")}, {}};
    }
    if (scenario_.precondition_has_late_environment_failure) {
      return {false,
              {failure(FailureCategory::PRECONDITION, "ARM_NOT_QUIESCENT"),
               failure(FailureCategory::OBSERVATION, "STALE_SECONDARY_EVIDENCE")},
              {}};
    }
    return {true, {}, {}};
  }

  [[nodiscard]] ValidationResult validate(const WorldSnapshot &, const WorldSnapshot &,
                                          const ActionResult &) const override
  {
    scenario_.events.push_back(event("transition-validate", state_));
    ++scenario_.transition_calls;
    if (scenario_.transient_transition_state == state_ &&
        scenario_.transient_transition_failures > 0) {
      --scenario_.transient_transition_failures;
      return {
        false,
        {failure(FailureCategory::POSTCONDITION, scenario_.transient_transition_failure_code)},
        {}};
    }
    if (scenario_.fail_transition == state_) {
      return {false, {failure(FailureCategory::POSTCONDITION, "POSTCONDITION_INJECTED")}, {}};
    }
    return {true, {}, {}};
  }

private:
  State state_;
  Scenario & scenario_;
};

class MemoryCheckpointStore final : public pick_place::ICheckpointStore
{
public:
  explicit MemoryCheckpointStore(Scenario & scenario) : scenario_(scenario) {}

  std::optional<Failure> commit(const Checkpoint & checkpoint) override
  {
    scenario_.events.push_back(event("checkpoint", checkpoint.next_state));
    ++commit_calls;
    if (commit_failure) {
      return commit_failure;
    }
    latest = checkpoint;
    history.push_back(checkpoint);
    return std::nullopt;
  }

  pick_place::CheckpointLoadResult loadLatestCompatible() override
  {
    ++load_calls;
    return latest ? pick_place::CheckpointLoadResult{latest, std::nullopt}
                  : pick_place::CheckpointLoadResult{
                      std::nullopt, failure(FailureCategory::CHECKPOINT, "NO_CHECKPOINT")};
  }

  Scenario & scenario_;
  std::optional<Checkpoint> latest;
  std::vector<Checkpoint> history;
  std::optional<Failure> commit_failure;
  int commit_calls{0};
  int load_calls{0};
};

class FactDrivenRecoveryPolicy final : public pick_place::IRecoveryPolicy
{
public:
  explicit FactDrivenRecoveryPolicy(Scenario & scenario) : scenario_(scenario) {}

  pick_place::RecoveryRoute select(State state, const Failure &,
                                   const WorldSnapshot & current) const override
  {
    scenario_.events.push_back(event("recover", state));
    ++calls;
    if (route_failure) {
      return {std::nullopt, route_failure};
    }
    if (current.gazebo_task_object_attached.value_or(false) &&
        current.moveit_task_object_attached.value_or(false)) {
      return {State::RECOVER_LIFT_TO_SAFE_HEIGHT, std::nullopt};
    }
    if (current.gazebo_task_object_attached.value_or(false) ||
        current.moveit_task_object_attached.value_or(false)) {
      return {State::RECOVER_OPEN_GRIPPER, std::nullopt};
    }
    return {State::RECOVER_RETREAT, std::nullopt};
  }

  Scenario & scenario_;
  mutable int calls{0};
  std::optional<Failure> route_failure;
};

const std::vector<State> kActionStates{State::PREPARE_OPEN_GRIPPER,
                                       State::MOVE_ABOVE_OBJECT,
                                       State::DESCEND,
                                       State::CLOSE_GRIPPER,
                                       State::WAIT_GRASP_STABLE,
                                       State::MICRO_LIFT,
                                       State::WAIT_MICRO_LIFT_STABLE,
                                       State::VERIFY_PHYSICAL_GRASP,
                                       State::ATTACH_GAZEBO,
                                       State::ATTACH_MOVEIT,
                                       State::LIFT,
                                       State::MOVE_ABOVE_PLACE,
                                       State::DESCEND_TO_PLACE,
                                       State::OPEN_GRIPPER,
                                       State::DETACH_GAZEBO,
                                       State::DETACH_MOVEIT,
                                       State::SYNC_WORLD_OBJECT,
                                       State::RETREAT,
                                       State::RECOVER_LIFT_TO_SAFE_HEIGHT,
                                       State::RECOVER_MOVE_ABOVE_PICK,
                                       State::RECOVER_DESCEND_TO_PICK,
                                       State::RECOVER_OPEN_GRIPPER,
                                       State::RECOVER_DETACH_GAZEBO,
                                       State::RECOVER_DETACH_MOVEIT,
                                       State::RECOVER_SYNC_WORLD_OBJECT,
                                       State::RECOVER_RETREAT};

const std::set<State> kPlannedStates{State::MOVE_ABOVE_OBJECT,
                                     State::DESCEND,
                                     State::LIFT,
                                     State::MOVE_ABOVE_PLACE,
                                     State::DESCEND_TO_PLACE,
                                     State::RETREAT,
                                     State::RECOVER_LIFT_TO_SAFE_HEIGHT,
                                     State::RECOVER_MOVE_ABOVE_PICK,
                                     State::RECOVER_DESCEND_TO_PICK,
                                     State::RECOVER_RETREAT};

struct Harness
{
  Harness() : observer(scenario), store(scenario), recovery(scenario) {}

  void registerState(State state, bool planned = false)
  {
    actions.registerExecutor(state, std::make_shared<FakeExecutor>(state, scenario));
    const auto next = pick_place::TransitionTable::resolve(state, ActionStatus::SUCCEEDED);
    contracts.registerContract({state, next}, std::make_shared<FakeContract>(state, scenario));
    if (planned) {
      actions.registerPlanner(state, std::make_shared<FakePlanner>(state, scenario));
      validators.registerValidator(state, std::make_shared<FakePlanValidator>(state, scenario));
    }
  }

  void registerAll()
  {
    for (const auto state : kActionStates) {
      registerState(state, kPlannedStates.count(state) != 0);
    }
    contracts.registerContract({State::VALIDATION_FAILED, State::ATTACH_GAZEBO},
                               std::make_shared<FakeContract>(State::VALIDATION_FAILED, scenario));
  }

  void registerAllExcept(std::optional<State> executor_gap, std::optional<State> planner_gap,
                         std::optional<State> validator_gap, std::optional<State> contract_gap)
  {
    for (const auto state : kActionStates) {
      const auto next = pick_place::TransitionTable::resolve(state, ActionStatus::SUCCEEDED);
      if (executor_gap != state) {
        actions.registerExecutor(state, std::make_shared<FakeExecutor>(state, scenario));
      }
      if (contract_gap != state) {
        contracts.registerContract({state, next}, std::make_shared<FakeContract>(state, scenario));
      }
      if (kPlannedStates.count(state) != 0) {
        if (planner_gap != state) {
          actions.registerPlanner(state, std::make_shared<FakePlanner>(state, scenario));
        }
        if (validator_gap != state) {
          validators.registerValidator(state, std::make_shared<FakePlanValidator>(state, scenario));
        }
      }
    }
  }

  pick_place::StateMachineRunner runner()
  {
    return {actions, contracts, &observer, &store, &resume, &validators, &recovery};
  }

  Scenario scenario;
  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  pick_place::PlanValidatorRegistry validators;
  FakeObserver observer;
  MemoryCheckpointStore store;
  pick_place::CommonResumeValidator resume{"config-a", "session-a"};
  FactDrivenRecoveryPolicy recovery;
};

Checkpoint forwardCheckpoint(State last, State next, const WorldSnapshot & world)
{
  Checkpoint checkpoint;
  checkpoint.run_id = "pick_place_state_machine";
  checkpoint.sequence = 4;
  checkpoint.source_mode = RunMode::EXECUTE;
  checkpoint.phase = CheckpointPhase::FORWARD;
  checkpoint.last_completed_state = last;
  checkpoint.next_state = next;
  checkpoint.policy_bundle_sha256 = "config-a";
  checkpoint.simulation_session_id = "session-a";
  setExpected(checkpoint, world);
  return checkpoint;
}

std::vector<State> normalTrace()
{
  return {State::IDLE,
          State::PREPARE_OPEN_GRIPPER,
          State::MOVE_ABOVE_OBJECT,
          State::DESCEND,
          State::CLOSE_GRIPPER,
          State::WAIT_GRASP_STABLE,
          State::ATTACH_GAZEBO,
          State::ATTACH_MOVEIT,
          State::LIFT,
          State::MOVE_ABOVE_PLACE,
          State::DESCEND_TO_PLACE,
          State::OPEN_GRIPPER,
          State::DETACH_GAZEBO,
          State::DETACH_MOVEIT,
          State::SYNC_WORLD_OBJECT,
          State::RETREAT,
          State::DONE};
}

TEST(PureRunnerIntegration, ExecuteUsesTheCompleteBoundaryInOrder)
{
  Harness harness;
  harness.registerAll();

  const auto result =
    harness.runner().run({RunMode::EXECUTE, State::MOVE_ABOVE_OBJECT, false, std::nullopt, 20});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  const std::vector<std::string> expected{"observe",
                                          "precondition:PREPARE_OPEN_GRIPPER",
                                          "execute:PREPARE_OPEN_GRIPPER",
                                          "observe",
                                          "transition-validate:PREPARE_OPEN_GRIPPER",
                                          "checkpoint:MOVE_ABOVE_OBJECT",
                                          "observe",
                                          "precondition:MOVE_ABOVE_OBJECT",
                                          "plan:MOVE_ABOVE_OBJECT",
                                          "plan-validate:MOVE_ABOVE_OBJECT",
                                          "execute:MOVE_ABOVE_OBJECT",
                                          "observe",
                                          "transition-validate:MOVE_ABOVE_OBJECT",
                                          "checkpoint:DESCEND"};
  EXPECT_EQ(expected, harness.scenario.events);
  ASSERT_TRUE(harness.scenario.planned_world);
  ASSERT_TRUE(harness.scenario.executed_world);
  EXPECT_EQ(std::optional<std::string>("tool_link"),
            harness.scenario.planned_world->moveit_task_object_attached_link);
  EXPECT_EQ((std::set<std::string>{"left_contact", "right_contact"}),
            harness.scenario.executed_world->moveit_task_object_touch_links);
}

TEST(PureRunnerIntegration, PlanOnlyStopBoundaryPlansValidatesAndCheckpointsWithoutActing)
{
  Harness harness;
  harness.registerState(State::MOVE_ABOVE_OBJECT, true);

  const auto result =
    harness.runner().run({RunMode::PLAN_ONLY, State::MOVE_ABOVE_OBJECT, false, std::nullopt, 20});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(0, harness.scenario.executor_calls);
  EXPECT_EQ(0, harness.scenario.transition_calls);
  EXPECT_EQ(
    (std::vector<std::string>{"observe", "precondition:MOVE_ABOVE_OBJECT", "plan:MOVE_ABOVE_OBJECT",
                              "plan-validate:MOVE_ABOVE_OBJECT", "checkpoint:MOVE_ABOVE_OBJECT"}),
    harness.scenario.events);
  ASSERT_TRUE(harness.store.latest);
  EXPECT_EQ(RunMode::PLAN_ONLY, harness.store.latest->source_mode);
  EXPECT_EQ(State::PREPARE_OPEN_GRIPPER, harness.store.latest->last_completed_state);
  EXPECT_EQ(State::MOVE_ABOVE_OBJECT, harness.store.latest->next_state);
}

TEST(PureRunnerIntegration, ExecuteStopCheckpointResumesWithFreshRunnerAndObserver)
{
  Harness first;
  first.registerAll();
  ASSERT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE,
            first.runner()
              .run({RunMode::EXECUTE, State::PREPARE_OPEN_GRIPPER, false, std::nullopt, 20})
              .status);

  Harness resumed;
  resumed.store.latest = first.store.latest;
  resumed.registerAll();

  const auto result =
    resumed.runner().run({RunMode::EXECUTE, State::MOVE_ABOVE_OBJECT, true, std::nullopt, 20});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ((std::vector<State>{State::MOVE_ABOVE_OBJECT, State::DESCEND}), result.state_trace);
  EXPECT_EQ(1, resumed.scenario.executor_calls);
  EXPECT_EQ(1, resumed.store.load_calls);
}

TEST(PureRunnerIntegration, MotionWaitsForAStablePostExecutionObservation)
{
  Harness harness;
  harness.registerAll();
  harness.scenario.fail_observation_call = 4;
  harness.scenario.observation_failure_code = "ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION";
  harness.scenario.observation_failure_count = 16;
  harness.scenario.observation_failure_delay = std::chrono::milliseconds(600);

  const auto result =
    harness.runner().run({RunMode::EXECUTE, State::MOVE_ABOVE_OBJECT, false, std::nullopt, 20});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(State::MOVE_ABOVE_OBJECT, result.current_state);
  EXPECT_EQ(State::DESCEND, result.next_state);
  EXPECT_EQ(20, harness.scenario.observation_calls);
  EXPECT_EQ(0, harness.scenario.cancel_calls);
  ASSERT_TRUE(harness.store.latest);
  EXPECT_EQ(State::MOVE_ABOVE_OBJECT, harness.store.latest->last_completed_state);
}

TEST(PureRunnerIntegration, SuccessfulNonMotionActionWaitsForAConsistentObservation)
{
  Harness harness;
  harness.registerAll();
  harness.scenario.fail_observation_call = 2;
  harness.scenario.observation_failure_code = "ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION";
  harness.scenario.observation_failure_count = 2;

  const auto result =
    harness.runner().run({RunMode::EXECUTE, State::PREPARE_OPEN_GRIPPER, false, std::nullopt, 20});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(State::PREPARE_OPEN_GRIPPER, result.current_state);
  EXPECT_EQ(State::MOVE_ABOVE_OBJECT, result.next_state);
  EXPECT_EQ(4, harness.scenario.observation_calls);
  EXPECT_EQ(1, harness.scenario.executor_calls);
  EXPECT_EQ(0, harness.scenario.cancel_calls);
  ASSERT_TRUE(harness.store.latest);
  EXPECT_EQ(State::PREPARE_OPEN_GRIPPER, harness.store.latest->last_completed_state);
}

TEST(PureRunnerIntegration, MotionWaitsForEndpointPostconditionConvergence)
{
  Harness harness;
  harness.registerAll();
  harness.scenario.transient_transition_state = State::MOVE_ABOVE_OBJECT;
  harness.scenario.transient_transition_failures = 1;

  const auto result =
    harness.runner().run({RunMode::EXECUTE, State::MOVE_ABOVE_OBJECT, false, std::nullopt, 20});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(State::MOVE_ABOVE_OBJECT, result.current_state);
  EXPECT_EQ(State::DESCEND, result.next_state);
  EXPECT_EQ(5, harness.scenario.observation_calls);
  EXPECT_EQ(3, harness.scenario.transition_calls);
  EXPECT_EQ(0, harness.scenario.cancel_calls);
}

TEST(PureRunnerIntegration, GripperActionWaitsForEndpointPostconditionConvergence)
{
  Harness harness;
  harness.registerAll();
  harness.scenario.transient_transition_state = State::PREPARE_OPEN_GRIPPER;
  harness.scenario.transient_transition_failures = 1;
  harness.scenario.transient_transition_failure_code = "Q6_TARGET_OUT_OF_TOLERANCE";

  const auto result =
    harness.runner().run({RunMode::EXECUTE, State::PREPARE_OPEN_GRIPPER, false, std::nullopt, 20});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(State::PREPARE_OPEN_GRIPPER, result.current_state);
  EXPECT_EQ(State::MOVE_ABOVE_OBJECT, result.next_state);
  EXPECT_EQ(3, harness.scenario.observation_calls);
  EXPECT_EQ(2, harness.scenario.transition_calls);
  EXPECT_EQ(0, harness.scenario.cancel_calls);
}

TEST(PureRunnerIntegration, GripperActionWaitsForArmQuiescenceAfterContact)
{
  Harness harness;
  harness.registerAll();
  harness.scenario.transient_transition_state = State::CLOSE_GRIPPER;
  harness.scenario.transient_transition_failures = 1;
  harness.scenario.transient_transition_failure_code = "ARM_NOT_QUIESCENT";

  const auto result =
    harness.runner().run({RunMode::EXECUTE, State::CLOSE_GRIPPER, false, std::nullopt, 20});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(State::CLOSE_GRIPPER, result.current_state);
  EXPECT_EQ(State::WAIT_GRASP_STABLE, result.next_state);
  EXPECT_GE(harness.scenario.observation_calls, 3);
  EXPECT_GE(harness.scenario.transition_calls, 2);
  EXPECT_EQ(0, harness.scenario.cancel_calls);
}

TEST(PureRunnerIntegration, AttachmentWaitsForArmQuiescenceBeforeSideEffect)
{
  Harness harness;
  harness.registerAll();
  harness.scenario.transient_precondition_state = State::ATTACH_GAZEBO;
  harness.scenario.transient_precondition_failures = 1;

  const auto result =
    harness.runner().run({RunMode::EXECUTE, State::ATTACH_GAZEBO, false, std::nullopt, 20});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(State::ATTACH_GAZEBO, result.current_state);
  EXPECT_EQ(State::ATTACH_MOVEIT, result.next_state);
  EXPECT_GE(harness.scenario.observation_calls, 3);
  EXPECT_GE(harness.scenario.precondition_calls, 2);
  EXPECT_EQ(1, std::count(harness.scenario.events.begin(), harness.scenario.events.end(),
                          "execute:ATTACH_GAZEBO"));
  EXPECT_EQ(0, harness.scenario.cancel_calls);
}

TEST(PureRunnerIntegration, AttachmentWaitsForTransientBilateralContactBeforeSideEffect)
{
  Harness harness;
  harness.registerAll();
  harness.scenario.transient_precondition_state = State::ATTACH_GAZEBO;
  harness.scenario.transient_precondition_failures = 2;
  harness.scenario.transient_precondition_failure_code = "BILATERAL_GRIPPER_CONTACT_REQUIRED";

  const auto result =
    harness.runner().run({RunMode::EXECUTE, State::ATTACH_GAZEBO, false, std::nullopt, 20});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(State::ATTACH_GAZEBO, result.current_state);
  EXPECT_EQ(State::ATTACH_MOVEIT, result.next_state);
  EXPECT_GE(harness.scenario.observation_calls, 4);
  EXPECT_GE(harness.scenario.precondition_calls, 3);
  EXPECT_EQ(1, std::count(harness.scenario.events.begin(), harness.scenario.events.end(),
                          "execute:ATTACH_GAZEBO"));
  EXPECT_EQ(0, harness.scenario.cancel_calls);
}

TEST(PureRunnerIntegration, DescendPostconditionFailureNeverExecutesCloseOrAttach)
{
  Harness harness;
  harness.registerAll();
  harness.scenario.fail_transition = State::DESCEND;

  const auto result =
    harness.runner().run({RunMode::EXECUTE, State::DESCEND, false, std::nullopt, 20});

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("POSTCONDITION_INJECTED", result.failure->code);
  EXPECT_EQ((std::vector<State>{State::IDLE, State::PREPARE_OPEN_GRIPPER, State::MOVE_ABOVE_OBJECT,
                                State::DESCEND, State::RECOVER_RETREAT, State::ERROR}),
            result.state_trace);
  EXPECT_NE(
    std::find(harness.scenario.events.begin(), harness.scenario.events.end(), "execute:DESCEND"),
    harness.scenario.events.end());
  EXPECT_EQ(std::find(harness.scenario.events.begin(), harness.scenario.events.end(),
                      "execute:CLOSE_GRIPPER"),
            harness.scenario.events.end());
  EXPECT_EQ(std::find(harness.scenario.events.begin(), harness.scenario.events.end(),
                      "execute:ATTACH_GAZEBO"),
            harness.scenario.events.end());
  EXPECT_EQ(std::find(harness.scenario.events.begin(), harness.scenario.events.end(),
                      "execute:ATTACH_MOVEIT"),
            harness.scenario.events.end());
}

TEST(PureRunnerIntegration, ResumeValidatesCommonAndTransitionBoundaryBeforeAnyAction)
{
  Harness harness;
  harness.registerAll();
  harness.store.latest = forwardCheckpoint(State::PREPARE_OPEN_GRIPPER, State::MOVE_ABOVE_OBJECT,
                                           harness.scenario.world);
  harness.scenario.fail_transition = State::PREPARE_OPEN_GRIPPER;

  const auto result =
    harness.runner().run({RunMode::EXECUTE, std::nullopt, true, std::nullopt, 20});

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("POSTCONDITION_INJECTED", result.failure->code);
  EXPECT_EQ(0, harness.scenario.executor_calls);
  EXPECT_EQ(0, harness.scenario.planner_calls);
  EXPECT_EQ(1, harness.scenario.transition_calls);
}

TEST(PureRunnerIntegration, ResumeMismatchStaleSessionConfigAndSkippedBoundaryFailClosed)
{
  const std::vector<std::string> cases{"world", "stale", "session", "config", "skipped"};
  for (const auto & which : cases) {
    Harness harness;
    harness.registerAll();
    harness.store.latest = forwardCheckpoint(State::PREPARE_OPEN_GRIPPER, State::MOVE_ABOVE_OBJECT,
                                             harness.scenario.world);
    if (which == "world") {
      harness.scenario.world.tcp_pose_world.x += 1.0;
    } else if (which == "stale") {
      harness.scenario.world.fresh = false;
    } else if (which == "session") {
      harness.scenario.world.simulation_session_id = "other-session";
    } else if (which == "config") {
      harness.store.latest->policy_bundle_sha256 = "other-config";
    } else {
      harness.store.latest->next_state = State::DESCEND;
    }

    const auto result =
      harness.runner().run({RunMode::EXECUTE, std::nullopt, true, std::nullopt, 20});

    EXPECT_EQ(pick_place::RunStatus::ERROR, result.status) << which;
    EXPECT_EQ(0, harness.scenario.executor_calls) << which;
    EXPECT_EQ(0, harness.scenario.planner_calls) << which;
  }
}

TEST(PureRunnerIntegration, MissingPlannerExecutorValidatorContractAndObserverFailClosed)
{
  {
    Harness harness;
    harness.validators.registerValidator(
      State::MOVE_ABOVE_OBJECT,
      std::make_shared<FakePlanValidator>(State::MOVE_ABOVE_OBJECT, harness.scenario));
    harness.actions.registerExecutor(
      State::MOVE_ABOVE_OBJECT,
      std::make_shared<FakeExecutor>(State::MOVE_ABOVE_OBJECT, harness.scenario));
    harness.contracts.registerContract(
      {State::MOVE_ABOVE_OBJECT, State::DESCEND},
      std::make_shared<FakeContract>(State::MOVE_ABOVE_OBJECT, harness.scenario));
    const auto result =
      harness.runner().run({RunMode::PLAN_ONLY, State::MOVE_ABOVE_OBJECT, false, std::nullopt, 20});
    ASSERT_TRUE(result.failure);
    EXPECT_EQ("PLANNER_NOT_REGISTERED", result.failure->code);
  }
  {
    Harness harness;
    harness.registerState(State::PREPARE_OPEN_GRIPPER);
    harness.actions = {};
    const auto result = harness.runner().run(
      {RunMode::EXECUTE, State::PREPARE_OPEN_GRIPPER, false, std::nullopt, 20});
    ASSERT_TRUE(result.failure);
    EXPECT_EQ("EXECUTE_ACTION_NOT_REGISTERED", result.failure->code);
  }
  {
    Harness harness;
    harness.actions.registerPlanner(
      State::MOVE_ABOVE_OBJECT,
      std::make_shared<FakePlanner>(State::MOVE_ABOVE_OBJECT, harness.scenario));
    const auto result =
      harness.runner().run({RunMode::PLAN_ONLY, State::MOVE_ABOVE_OBJECT, false, std::nullopt, 20});
    ASSERT_TRUE(result.failure);
    EXPECT_EQ("PLAN_VALIDATOR_NOT_REGISTERED", result.failure->code);
  }
  {
    Harness harness;
    harness.actions.registerExecutor(
      State::PREPARE_OPEN_GRIPPER,
      std::make_shared<FakeExecutor>(State::PREPARE_OPEN_GRIPPER, harness.scenario));
    const auto result = harness.runner().run(
      {RunMode::EXECUTE, State::PREPARE_OPEN_GRIPPER, false, std::nullopt, 20});
    ASSERT_TRUE(result.failure);
    EXPECT_EQ("MISSING_TRANSITION_CONTRACT", result.failure->code);
  }
}

TEST(PureRunnerIntegration, PlanningAndExecutionFailuresKeepTheirClassificationAndRecover)
{
  const std::vector<std::pair<std::string, FailureCategory>> cases{
    {"precondition", FailureCategory::PRECONDITION},
    {"plan", FailureCategory::PLANNING},
    {"plan-validation", FailureCategory::PLAN_VALIDATION},
    {"execute", FailureCategory::EXECUTION},
    {"post-observe", FailureCategory::OBSERVATION},
    {"transition", FailureCategory::POSTCONDITION}};
  for (const auto & [which, category] : cases) {
    Harness harness;
    harness.registerAll();
    if (which == "precondition") {
      harness.scenario.fail_precondition = State::MOVE_ABOVE_OBJECT;
    } else if (which == "plan") {
      harness.scenario.fail_plan = State::MOVE_ABOVE_OBJECT;
    } else if (which == "plan-validation") {
      harness.scenario.fail_plan_validation = State::MOVE_ABOVE_OBJECT;
    } else if (which == "execute") {
      harness.scenario.fail_execute = State::MOVE_ABOVE_OBJECT;
    } else if (which == "post-observe") {
      harness.scenario.fail_observation_call = 4;
    } else {
      harness.scenario.fail_transition = State::MOVE_ABOVE_OBJECT;
    }

    const auto result =
      harness.runner().run({RunMode::EXECUTE, std::nullopt, false, std::nullopt, 100});

    ASSERT_TRUE(result.failure) << which;
    EXPECT_EQ(category, result.failure->category) << which;
    EXPECT_EQ(pick_place::RunStatus::ERROR, result.status) << which;
    EXPECT_GE(harness.scenario.cancel_calls, 1) << which;
    EXPECT_EQ(State::ERROR, result.state_trace.back()) << which;
  }
}

TEST(PureRunnerIntegration, StopObservationRetriesTransientRobotStateChangesAndKeepsFirstFailure)
{
  Harness harness;
  harness.registerAll();
  harness.scenario.fail_transition = State::MOVE_ABOVE_OBJECT;
  // Calls 1-4 cover the initial and successful-action observations through
  // MOVE_ABOVE_OBJECT.  The first stop observation is call 5.
  harness.scenario.fail_observation_call = 5;
  harness.scenario.observation_failure_code = "ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION";
  harness.scenario.observation_failure_count = 2;

  const auto result =
    harness.runner().run({RunMode::EXECUTE, std::nullopt, false, std::nullopt, 100});

  ASSERT_TRUE(result.failure);
  EXPECT_EQ(FailureCategory::POSTCONDITION, result.failure->category);
  EXPECT_EQ("POSTCONDITION_INJECTED", result.failure->code);
  EXPECT_GE(harness.scenario.observation_calls, 7);
  EXPECT_GE(harness.scenario.cancel_calls, 1);
}

TEST(PureRunnerIntegration, PostCancelQuiescenceFailureRetainsOriginalActionFailureContext)
{
  Harness harness;
  harness.registerAll();
  harness.scenario.fail_execute = State::PREPARE_OPEN_GRIPPER;
  harness.scenario.execute_failure_metrics = {{"observed_q6", -0.059303}};
  harness.scenario.cancel_makes_arm_nonstationary = true;

  const auto result =
    harness.runner().run({RunMode::EXECUTE, State::PREPARE_OPEN_GRIPPER, false, std::nullopt, 100});

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("ARM_NOT_QUIESCENT_AFTER_CANCEL", result.failure->code);
  EXPECT_NE(std::string::npos, result.failure->message.find(
                                 "original failure EXECUTION_INJECTED: injected test failure"));
  const auto original_q6 = result.failure->metrics.find("original_observed_q6");
  ASSERT_NE(result.failure->metrics.end(), original_q6);
  EXPECT_DOUBLE_EQ(-0.059303, original_q6->second);
}

TEST(PureRunnerIntegration, RecoveryClassificationFailureRetainsOriginalActionFailureContext)
{
  Harness harness;
  harness.registerAll();
  harness.scenario.fail_transition = State::MOVE_ABOVE_OBJECT;
  harness.recovery.route_failure = Failure{FailureCategory::WORLD_INCONSISTENCY,
                                           "UNSAFE_RECOVERY_OBSERVATION",
                                           "recovery classification rejected the stopped world",
                                           {}};

  const auto result =
    harness.runner().run({RunMode::EXECUTE, std::nullopt, false, std::nullopt, 100});

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("UNSAFE_RECOVERY_OBSERVATION", result.failure->code);
  EXPECT_NE(std::string::npos, result.failure->message.find(
                                 "original failure POSTCONDITION_INJECTED: injected test failure"));
}

TEST(PureRunnerIntegration, DoesNotObserveOrRecoverBeforeCancelReachesTerminal)
{
  Harness harness;
  harness.registerAllExcept(State::PREPARE_OPEN_GRIPPER, std::nullopt, std::nullopt, std::nullopt);
  auto blocking = std::make_shared<BlockingCancelExecutor>();
  harness.actions.registerExecutor(State::PREPARE_OPEN_GRIPPER, blocking);

  auto run = std::async(std::launch::async, [&harness]() {
    return harness.runner().run({RunMode::EXECUTE, std::nullopt, false, std::nullopt, 100});
  });
  ASSERT_TRUE(blocking->waitForCancel(std::chrono::milliseconds(500)));
  EXPECT_EQ(std::future_status::timeout, run.wait_for(std::chrono::milliseconds(100)));
  EXPECT_EQ(1, harness.scenario.observation_calls);
  EXPECT_EQ(0, harness.recovery.calls);

  blocking->makeTerminal();
  EXPECT_EQ(std::future_status::ready, run.wait_for(std::chrono::seconds(2)));
  EXPECT_EQ(pick_place::RunStatus::ERROR, run.get().status);
  EXPECT_GT(harness.scenario.observation_calls, 1);
}

TEST(PureRunnerIntegration, NormalAndFailureRunsExposeExactForwardAndRecoveryTraces)
{
  Harness normal;
  normal.registerAll();
  const auto successful =
    normal.runner().run({RunMode::EXECUTE, std::nullopt, false, std::nullopt, 100});
  EXPECT_EQ(pick_place::RunStatus::DONE, successful.status);
  EXPECT_EQ(normalTrace(), successful.state_trace);

  Harness failed;
  failed.registerAll();
  failed.scenario.fail_execute = State::LIFT;
  const auto recovered =
    failed.runner().run({RunMode::EXECUTE, std::nullopt, false, std::nullopt, 100});
  const std::vector<State> expected{State::IDLE,
                                    State::PREPARE_OPEN_GRIPPER,
                                    State::MOVE_ABOVE_OBJECT,
                                    State::DESCEND,
                                    State::CLOSE_GRIPPER,
                                    State::WAIT_GRASP_STABLE,
                                    State::ATTACH_GAZEBO,
                                    State::ATTACH_MOVEIT,
                                    State::LIFT,
                                    State::RECOVER_LIFT_TO_SAFE_HEIGHT,
                                    State::RECOVER_MOVE_ABOVE_PICK,
                                    State::RECOVER_DESCEND_TO_PICK,
                                    State::RECOVER_OPEN_GRIPPER,
                                    State::RECOVER_DETACH_GAZEBO,
                                    State::RECOVER_DETACH_MOVEIT,
                                    State::RECOVER_SYNC_WORLD_OBJECT,
                                    State::RECOVER_RETREAT,
                                    State::ERROR};
  EXPECT_EQ(expected, recovered.state_trace);
}

TEST(PureRunnerIntegration, RecoveryResumeReclassifiesFromCurrentFactsInsteadOfCheckpointHistory)
{
  Harness harness;
  harness.registerAll();
  auto historical = harness.scenario.world;
  historical.gazebo_task_object_attached = true;
  historical.moveit_task_object_attached = true;
  auto checkpoint = forwardCheckpoint(State::LIFT, State::RECOVER_LIFT_TO_SAFE_HEIGHT, historical);
  checkpoint.phase = CheckpointPhase::RECOVERY;
  checkpoint.failed_state = State::LIFT;
  checkpoint.original_failure = failure(FailureCategory::EXECUTION, "ORIGINAL_FAILURE");
  harness.store.latest = checkpoint;
  harness.scenario.world.gazebo_task_object_attached = false;
  harness.scenario.world.moveit_task_object_attached = false;

  const auto result =
    harness.runner().run({RunMode::EXECUTE, std::nullopt, true, std::nullopt, 100});

  EXPECT_EQ((std::vector<State>{State::RECOVER_RETREAT, State::ERROR}), result.state_trace);
  EXPECT_EQ(1, harness.recovery.calls);
}

TEST(PureRunnerIntegration, RecoveryResumeRequiresStationaryObjectBeforePolicyOrAction)
{
  for (const bool omit_stationary_evidence : {false, true}) {
    Harness harness;
    harness.registerAll();
    auto checkpoint =
      forwardCheckpoint(State::LIFT, State::RECOVER_LIFT_TO_SAFE_HEIGHT, harness.scenario.world);
    checkpoint.phase = CheckpointPhase::RECOVERY;
    checkpoint.failed_state = State::LIFT;
    checkpoint.original_failure = failure(FailureCategory::EXECUTION, "ORIGINAL_FAILURE");
    harness.store.latest = checkpoint;
    if (omit_stationary_evidence) {
      harness.scenario.world.gazebo_task_object_stationary.reset();
    } else {
      harness.scenario.world.gazebo_task_object_stationary = false;
    }

    const auto result =
      harness.runner().run({RunMode::EXECUTE, std::nullopt, true, std::nullopt, 100});

    EXPECT_EQ(pick_place::RunStatus::ERROR, result.status);
    EXPECT_EQ(0, harness.recovery.calls);
    EXPECT_EQ(0, harness.scenario.planner_calls);
    EXPECT_EQ(0, harness.scenario.executor_calls);
    EXPECT_EQ((std::vector<std::string>{"observe"}), harness.scenario.events);
  }
}

TEST(PureRunnerIntegration, RecoveryResumeRejectsPlanOnlySourceBeforeObservationOrAction)
{
  Harness harness;
  harness.registerAll();
  auto checkpoint =
    forwardCheckpoint(State::LIFT, State::RECOVER_LIFT_TO_SAFE_HEIGHT, harness.scenario.world);
  checkpoint.source_mode = RunMode::PLAN_ONLY;
  checkpoint.phase = CheckpointPhase::RECOVERY;
  checkpoint.failed_state = State::LIFT;
  checkpoint.original_failure = failure(FailureCategory::EXECUTION, "ORIGINAL_FAILURE");
  harness.store.latest = checkpoint;

  const auto result =
    harness.runner().run({RunMode::EXECUTE, std::nullopt, true, std::nullopt, 100});

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("CHECKPOINT_INCOMPATIBLE", result.failure->code);
  EXPECT_TRUE(harness.scenario.events.empty());
  EXPECT_EQ(0, harness.scenario.observation_calls);
  EXPECT_EQ(0, harness.recovery.calls);
  EXPECT_EQ(0, harness.scenario.executor_calls);
}

TEST(PureRunnerIntegration, ExecutePreflightRejectsEveryLateRegistrationGapWithoutSideEffects)
{
  struct Gap
  {
    std::optional<State> executor;
    std::optional<State> planner;
    std::optional<State> validator;
    std::optional<State> contract;
    const char * code;
  };
  const std::vector<Gap> gaps{
    {State::RECOVER_RETREAT, std::nullopt, std::nullopt, std::nullopt,
     "EXECUTE_ACTION_NOT_REGISTERED"},
    {std::nullopt, State::RECOVER_RETREAT, std::nullopt, std::nullopt, "PLANNER_NOT_REGISTERED"},
    {std::nullopt, std::nullopt, State::RECOVER_RETREAT, std::nullopt,
     "PLAN_VALIDATOR_NOT_REGISTERED"},
    {std::nullopt, std::nullopt, std::nullopt, State::RECOVER_RETREAT,
     "MISSING_TRANSITION_CONTRACT"}};

  for (const auto & gap : gaps) {
    Harness harness;
    harness.registerAllExcept(gap.executor, gap.planner, gap.validator, gap.contract);

    const auto result =
      harness.runner().run({RunMode::EXECUTE, std::nullopt, false, std::nullopt, 100});

    ASSERT_TRUE(result.failure);
    EXPECT_EQ(gap.code, result.failure->code);
    EXPECT_TRUE(harness.scenario.events.empty()) << gap.code;
    EXPECT_EQ(0, harness.scenario.observation_calls) << gap.code;
    EXPECT_EQ(0, harness.scenario.planner_calls) << gap.code;
    EXPECT_EQ(0, harness.scenario.executor_calls) << gap.code;
  }

  Harness missing_recovery;
  missing_recovery.registerAll();
  const pick_place::StateMachineRunner runner(
    missing_recovery.actions, missing_recovery.contracts, &missing_recovery.observer,
    &missing_recovery.store, &missing_recovery.resume, &missing_recovery.validators, nullptr);
  const auto result = runner.run({RunMode::EXECUTE, std::nullopt, false, std::nullopt, 100});
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("RECOVERY_POLICY_MISSING", result.failure->code);
  EXPECT_TRUE(missing_recovery.scenario.events.empty());
}

TEST(PureRunnerIntegration, ExecutePreflightRejectsLateNonPlanningPlannerValidatorAsymmetry)
{
  constexpr auto late_non_planning_state = State::RECOVER_SYNC_WORLD_OBJECT;
  for (const bool planner_only : {true, false}) {
    Harness harness;
    harness.registerAll();
    if (planner_only) {
      harness.actions.registerPlanner(
        late_non_planning_state,
        std::make_shared<FakePlanner>(late_non_planning_state, harness.scenario));
    } else {
      harness.validators.registerValidator(
        late_non_planning_state,
        std::make_shared<FakePlanValidator>(late_non_planning_state, harness.scenario));
    }

    const auto result = harness.runner().run(
      {RunMode::EXECUTE, State::PREPARE_OPEN_GRIPPER, false, std::nullopt, 100});

    ASSERT_TRUE(result.failure);
    EXPECT_EQ(planner_only ? "PLAN_VALIDATOR_NOT_REGISTERED" : "PLANNER_NOT_REGISTERED",
              result.failure->code);
    EXPECT_TRUE(harness.scenario.events.empty());
    EXPECT_EQ(0, harness.scenario.observation_calls);
    EXPECT_EQ(0, harness.scenario.planner_calls);
    EXPECT_EQ(0, harness.scenario.executor_calls);
  }
}

TEST(PureRunnerIntegration, CancelFailureStopsWithoutRecoveryActions)
{
  Harness harness;
  harness.registerAll();
  harness.scenario.fail_execute = State::MOVE_ABOVE_OBJECT;
  harness.scenario.cancel_result = {ActionStatus::FAILED,
                                    failure(FailureCategory::EXECUTION, "CANCEL_INJECTED")};

  const auto result =
    harness.runner().run({RunMode::EXECUTE, std::nullopt, false, std::nullopt, 100});

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("CANCEL_INJECTED", result.failure->code);
  EXPECT_EQ(0, harness.recovery.calls);
}

TEST(PureRunnerIntegration, RegistriesRegisterQueryAndReportCoverage)
{
  Harness harness;
  harness.registerAll();
  for (const auto state : kActionStates) {
    EXPECT_NE(nullptr, harness.actions.findExecutor(state));
  }
  EXPECT_EQ(nullptr, harness.actions.findExecutor(State::DONE));
  EXPECT_FALSE(harness.contracts.validateExecuteCoverage().has_value());

  pick_place::TransitionContractRegistry incomplete;
  ASSERT_TRUE(incomplete.validateExecuteCoverage().has_value());
  EXPECT_EQ("MISSING_TRANSITION_CONTRACT", incomplete.validateExecuteCoverage()->code);
}

TEST(PureRunnerIntegration, FailAtOutsideDryRunAndInvalidTransitionLimitFailClosed)
{
  Harness harness;
  const auto fail_at =
    harness.runner().run({RunMode::EXECUTE, std::nullopt, false, State::MOVE_ABOVE_OBJECT, 20});
  ASSERT_TRUE(fail_at.failure);
  EXPECT_EQ("FAIL_AT_MODE_MISMATCH", fail_at.failure->code);

  const auto no_transitions =
    harness.runner().run({RunMode::DRY_RUN, std::nullopt, false, std::nullopt, 0});
  ASSERT_TRUE(no_transitions.failure);
  EXPECT_EQ("INVALID_MAX_TRANSITIONS", no_transitions.failure->code);
  EXPECT_EQ(0, harness.scenario.executor_calls);
}

TEST(PureRunnerIntegration, PreExecutionObservationFailureStopsWithoutBlindRecovery)
{
  Harness harness;
  harness.registerAll();
  harness.scenario.fail_observation_call = 1;

  const auto result = harness.runner().run({RunMode::EXECUTE});

  EXPECT_EQ(result.status, pick_place::RunStatus::ERROR);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->category, FailureCategory::OBSERVATION);
  EXPECT_EQ(result.failure->code, "OBSERVATION_INJECTED");
  EXPECT_EQ(harness.scenario.observation_calls, 1);
  EXPECT_EQ(harness.scenario.cancel_calls, 0);
  EXPECT_EQ(harness.recovery.calls, 0);
  EXPECT_EQ(harness.store.commit_calls, 0);
}

TEST(PureRunnerIntegration, AnyEnvironmentPreconditionFailureStopsWithoutCancelOrRecovery)
{
  Harness harness;
  harness.registerAll();
  harness.scenario.precondition_has_late_environment_failure = true;

  const auto result = harness.runner().run({RunMode::EXECUTE});

  EXPECT_EQ(result.status, pick_place::RunStatus::ERROR);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->category, FailureCategory::OBSERVATION);
  EXPECT_EQ(result.failure->code, "STALE_SECONDARY_EVIDENCE");
  EXPECT_EQ(harness.scenario.cancel_calls, 0);
  EXPECT_EQ(harness.recovery.calls, 0);
  EXPECT_EQ(harness.store.commit_calls, 0);
}

}  // namespace
