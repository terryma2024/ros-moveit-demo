#include <gtest/gtest.h>

#include <algorithm>
#include <memory>

#include <moveit_msgs/msg/collision_object.hpp>

#include "panda_gazebo_demo/pick_place/checkpoint.hpp"
#include "panda_gazebo_demo/pick_place/moveit_world_object_pose.hpp"
#include "panda_gazebo_demo/pick_place/runner.hpp"

namespace pick_place = panda_gazebo_demo::pick_place;

namespace
{

class FakePlanner final : public pick_place::IStatePlanner
{
public:
  pick_place::PlanResult plan(pick_place::State state) override
  {
    ++calls;
    last_state = state;
    auto artifact = std::make_shared<pick_place::PlanArtifact>();
    artifact->trajectory_points = 3;
    return {{pick_place::ActionStatus::SUCCEEDED, std::nullopt}, artifact};
  }

  int calls{0};
  pick_place::State last_state{pick_place::State::ERROR};
};

class FakeExecutor final : public pick_place::IStateExecutor
{
public:
  pick_place::ActionResult execute(
    pick_place::State state, std::shared_ptr<const pick_place::PlanArtifact>) override
  {
    ++calls;
    last_state = state;
    return execute_result;
  }

  pick_place::ActionResult cancel() override
  {
    ++cancel_calls;
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }

  int calls{0};
  int cancel_calls{0};
  pick_place::State last_state{pick_place::State::ERROR};
  pick_place::ActionResult execute_result{pick_place::ActionStatus::SUCCEEDED, std::nullopt};
};

pick_place::WorldSnapshot makeSnapshot()
{
  pick_place::WorldSnapshot snapshot;
  snapshot.observed_at = std::chrono::steady_clock::now();
  snapshot.fresh = true;
  snapshot.arm_stationary = true;
  snapshot.gripper_open = true;
  snapshot.tcp_pose_world = {0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0};
  snapshot.joint_positions = {{"panda_joint1", 0.0}, {"panda_finger_joint1", 0.04},
    {"panda_finger_joint2", 0.04}};
  snapshot.moveit_world_object_poses = {{"table", {}},
    {"coke", {0.3, 0.0, 0.836, 0.0, 0.0, 0.0, 1.0}}};
  snapshot.moveit_coke_attached = false;
  snapshot.gazebo_coke_pose_world = {0.3, 0.0, 0.836, 0.0, 0.0, 0.0, 1.0};
  snapshot.gazebo_coke_attached = false;
  snapshot.simulation_session_id = "test-session";
  return snapshot;
}

pick_place::Checkpoint makeCheckpoint(const pick_place::WorldSnapshot & snapshot)
{
  pick_place::Checkpoint checkpoint;
  checkpoint.run_id = "run";
  checkpoint.sequence = 1;
  checkpoint.last_completed_state = pick_place::State::PREPARE_OPEN_GRIPPER;
  checkpoint.next_state = pick_place::State::MOVE_ABOVE_OBJECT;
  checkpoint.expected.tcp_pose_world = snapshot.tcp_pose_world;
  checkpoint.expected.gripper_open = snapshot.gripper_open;
  checkpoint.expected.joint_positions = snapshot.joint_positions;
  checkpoint.expected.moveit_world_object_poses = snapshot.moveit_world_object_poses;
  checkpoint.expected.moveit_coke_attached = snapshot.moveit_coke_attached;
  checkpoint.expected.gazebo_coke_pose_world = snapshot.gazebo_coke_pose_world;
  checkpoint.expected.gazebo_coke_attached = snapshot.gazebo_coke_attached;
  checkpoint.expected.required_world_objects = {"table", "coke"};
  checkpoint.configuration_hash = "test-config";
  checkpoint.simulation_session_id = snapshot.simulation_session_id;
  return checkpoint;
}

pick_place::CommonResumeValidator makeCommonResumeValidator()
{
  return {"test-config", "test-session"};
}

void registerMoveAboveObjectToDescendValidator(pick_place::TransitionContractRegistry & contracts)
{
  contracts.registerContract(
    {pick_place::State::MOVE_ABOVE_OBJECT, pick_place::State::DESCEND},
    std::make_shared<pick_place::MoveAboveObjectToDescendValidator>(
      pick_place::Pose3d{0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0},
      std::vector<std::string>{"table", "coke"}, 0.02, 0.1, 0.01, 0.1));
}

void registerPrepareOpenGripperToMoveAboveObjectValidator(
  pick_place::TransitionContractRegistry & contracts)
{
  contracts.registerContract(
    {pick_place::State::PREPARE_OPEN_GRIPPER, pick_place::State::MOVE_ABOVE_OBJECT},
    std::make_shared<pick_place::PrepareOpenGripperToMoveAboveObjectValidator>(
      std::vector<std::string>{"table", "coke"}, 0.02, 0.1, 0.01, 0.1));
}

class FakeObserver final : public pick_place::IWorldObserver
{
public:
  pick_place::ObservationResult observe() override
  {
    ++calls;
    return {calls == 1 || !after_snapshot ? snapshot : *after_snapshot, std::nullopt};
  }

  pick_place::WorldSnapshot snapshot{makeSnapshot()};
  std::optional<pick_place::WorldSnapshot> after_snapshot;
  int calls{0};
};

class FakeCheckpointStore final : public pick_place::ICheckpointStore
{
public:
  std::optional<pick_place::Failure> commit(const pick_place::Checkpoint & value) override
  {
    checkpoint = value;
    ++calls;
    return failure;
  }

  pick_place::CheckpointLoadResult loadLatestCompatible() override
  {
    ++load_calls;
    return load_result;
  }

  std::optional<pick_place::Checkpoint> checkpoint;
  std::optional<pick_place::Failure> failure;
  pick_place::CheckpointLoadResult load_result;
  int calls{0};
  int load_calls{0};
};

}  // namespace

TEST(MoveItWorldObjectPose, UsesObjectPoseInsteadOfLocalPrimitivePose)
{
  moveit_msgs::msg::CollisionObject object;
  object.pose.position.x = 0.3;
  object.pose.position.y = -0.2;
  object.pose.position.z = 0.836;
  object.pose.orientation.w = 1.0;

  geometry_msgs::msg::Pose local_primitive_pose;
  local_primitive_pose.orientation.w = 1.0;
  object.primitive_poses.push_back(local_primitive_pose);

  const auto observed = pick_place::worldPoseFromCollisionObject(object);
  EXPECT_DOUBLE_EQ(0.3, observed.x);
  EXPECT_DOUBLE_EQ(-0.2, observed.y);
  EXPECT_DOUBLE_EQ(0.836, observed.z);
  EXPECT_DOUBLE_EQ(1.0, observed.qw);
}

TEST(TransitionTable, SeparatesBusinessStateFromRunStatus)
{
  EXPECT_FALSE(pick_place::stateFromString("PLAN_ONLY_COMPLETE").has_value());
  EXPECT_FALSE(pick_place::stateFromString("MOVE_ABOVE_OBJECT_EXECUTED").has_value());
  EXPECT_STREQ("PLAN_ONLY_COMPLETE",
    pick_place::toString(pick_place::RunStatus::PLAN_ONLY_COMPLETE));
}

TEST(TransitionTable, RoutesSuccessAndFailureEdges)
{
  pick_place::StateMachine machine;
  EXPECT_EQ(pick_place::State::PREPARE_OPEN_GRIPPER,
    machine.advance(pick_place::ActionStatus::SUCCEEDED));
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT,
    machine.advance(pick_place::ActionStatus::SUCCEEDED));
}

TEST(TransitionTable, RoutesPrepareOpenGripperFailureToError)
{
  pick_place::StateMachine machine;
  static_cast<void>(machine.advance(pick_place::ActionStatus::SUCCEEDED));
  EXPECT_EQ(pick_place::State::ERROR, machine.advance(pick_place::ActionStatus::FAILED));
}

TEST(Runner, DryRunCompletesAndNeverNeedsAnActionRegistry)
{
  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  const pick_place::StateMachineRunner runner(actions, contracts);

  const auto result = runner.run({pick_place::RunMode::DRY_RUN, std::nullopt, false, std::nullopt,
        100});
  EXPECT_EQ(pick_place::RunStatus::DONE, result.status);
  EXPECT_EQ(pick_place::State::DONE, result.current_state);
  EXPECT_FALSE(result.failure.has_value());
}

TEST(Runner, DryRunFailureFollowsTheRecoveryPathAndReportsTheInjection)
{
  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  const pick_place::StateMachineRunner runner(actions, contracts);

  const auto result = runner.run({pick_place::RunMode::DRY_RUN, std::nullopt, false,
        pick_place::State::DESCEND, 100});
  EXPECT_EQ(pick_place::RunStatus::ERROR, result.status);
  EXPECT_EQ(pick_place::State::ERROR, result.current_state);
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("DRY_RUN_FAILURE_INJECTED", result.failure->code);
}

TEST(Runner, DryRunFailureTakesPriorityOverStopAfter)
{
  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  const pick_place::StateMachineRunner runner(actions, contracts);

  const auto result = runner.run({pick_place::RunMode::DRY_RUN, pick_place::State::DESCEND, false,
        pick_place::State::DESCEND, 100});
  EXPECT_EQ(pick_place::RunStatus::ERROR, result.status);
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("DRY_RUN_FAILURE_INJECTED", result.failure->code);
}

TEST(Runner, PlanOnlyUsesExactlyOnePlannerAndDoesNotAdvanceBusinessState)
{
  pick_place::StateActionRegistry actions;
  auto planner = std::make_shared<FakePlanner>();
  actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, planner);
  pick_place::TransitionContractRegistry contracts;
  const pick_place::StateMachineRunner runner(actions, contracts);

  const auto result = runner.run({pick_place::RunMode::PLAN_ONLY, std::nullopt, false, std::nullopt,
        100});
  EXPECT_EQ(pick_place::RunStatus::PLAN_ONLY_COMPLETE, result.status);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, result.current_state);
  EXPECT_EQ(pick_place::State::DESCEND, *result.next_state);
  EXPECT_EQ(1, planner->calls);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, planner->last_state);
}

TEST(Runner, ExecuteWorkflowRequiresExecutionInfrastructure)
{
  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  const pick_place::StateMachineRunner runner(actions, contracts);

  const auto result = runner.run({pick_place::RunMode::EXECUTE, std::nullopt, false, std::nullopt,
        100});
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("EXECUTE_INFRASTRUCTURE_MISSING", result.failure->code);
}

TEST(Runner, ExecutesPrepareOpenGripperWithoutPlanningAndCommitsAfterPostValidation)
{
  pick_place::StateActionRegistry actions;
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerExecutor(pick_place::State::PREPARE_OPEN_GRIPPER, executor);
  pick_place::TransitionContractRegistry contracts;
  registerPrepareOpenGripperToMoveAboveObjectValidator(contracts);
  FakeObserver observer;
  observer.snapshot.gripper_open = false;
  observer.after_snapshot = observer.snapshot;
  observer.after_snapshot->gripper_open = true;
  FakeCheckpointStore checkpoints;
  const auto common_resume_validator = makeCommonResumeValidator();
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator);

  const auto result = runner.run({pick_place::RunMode::EXECUTE,
        pick_place::State::PREPARE_OPEN_GRIPPER, false, std::nullopt, 100});
  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(pick_place::State::PREPARE_OPEN_GRIPPER, result.current_state);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, *result.next_state);
  EXPECT_EQ(1, executor->calls);
  EXPECT_EQ(pick_place::State::PREPARE_OPEN_GRIPPER, executor->last_state);
  EXPECT_EQ(2, observer.calls);
  ASSERT_TRUE(checkpoints.checkpoint.has_value());
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, checkpoints.checkpoint->next_state);
  EXPECT_FALSE(*checkpoints.checkpoint->expected.gazebo_coke_attached);
  EXPECT_FALSE(*checkpoints.checkpoint->expected.moveit_coke_attached);
}

TEST(Runner, ExecuteWorkflowAdvancesThroughRegisteredStatesUntilStopAfter)
{
  pick_place::StateActionRegistry actions;
  auto planner = std::make_shared<FakePlanner>();
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerExecutor(pick_place::State::PREPARE_OPEN_GRIPPER, executor);
  actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, planner);
  actions.registerExecutor(pick_place::State::MOVE_ABOVE_OBJECT, executor);
  pick_place::TransitionContractRegistry contracts;
  registerPrepareOpenGripperToMoveAboveObjectValidator(contracts);
  registerMoveAboveObjectToDescendValidator(contracts);
  FakeObserver observer;
  observer.snapshot.gripper_open = false;
  observer.after_snapshot = observer.snapshot;
  observer.after_snapshot->gripper_open = true;
  FakeCheckpointStore checkpoints;
  const auto common_resume_validator = makeCommonResumeValidator();
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator);

  const auto result = runner.run({pick_place::RunMode::EXECUTE,
        pick_place::State::MOVE_ABOVE_OBJECT, false, std::nullopt, 100});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, result.current_state);
  EXPECT_EQ(pick_place::State::DESCEND, *result.next_state);
  EXPECT_EQ(3U, result.transition_count);
  EXPECT_EQ(2, executor->calls);
  EXPECT_EQ(1, planner->calls);
  EXPECT_EQ(2, checkpoints.calls);
  ASSERT_TRUE(checkpoints.checkpoint.has_value());
  EXPECT_EQ(pick_place::State::DESCEND, checkpoints.checkpoint->next_state);
}

TEST(Runner, DoesNotCommitWhenPostValidationFails)
{
  pick_place::StateActionRegistry actions;
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerExecutor(pick_place::State::PREPARE_OPEN_GRIPPER, executor);
  pick_place::TransitionContractRegistry contracts;
  registerPrepareOpenGripperToMoveAboveObjectValidator(contracts);
  FakeObserver observer;
  observer.snapshot.gripper_open = false;
  observer.after_snapshot = observer.snapshot;
  observer.after_snapshot->gripper_open = true;
  observer.after_snapshot->tcp_pose_world.x = 0.5;
  FakeCheckpointStore checkpoints;
  const auto common_resume_validator = makeCommonResumeValidator();
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator);

  const auto result = runner.run({pick_place::RunMode::EXECUTE,
        pick_place::State::PREPARE_OPEN_GRIPPER, false, std::nullopt, 100});
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("TCP_MOVED_DURING_GRIPPER_OPEN", result.failure->code);
  EXPECT_EQ(1, executor->calls);
  EXPECT_EQ(1, executor->cancel_calls);
  EXPECT_EQ(0, checkpoints.calls);
}

TEST(Runner, PrepareOpenGripperFailureTransitionsToError)
{
  pick_place::StateActionRegistry actions;
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerExecutor(pick_place::State::PREPARE_OPEN_GRIPPER, executor);
  pick_place::TransitionContractRegistry contracts;
  registerPrepareOpenGripperToMoveAboveObjectValidator(contracts);
  FakeObserver observer;
  observer.snapshot.gripper_open = false;
  observer.after_snapshot = observer.snapshot;
  FakeCheckpointStore checkpoints;
  const auto common_resume_validator = makeCommonResumeValidator();
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator);

  const auto result = runner.run({pick_place::RunMode::EXECUTE,
        pick_place::State::PREPARE_OPEN_GRIPPER, false, std::nullopt, 100});

  EXPECT_EQ(pick_place::RunStatus::ERROR, result.status);
  EXPECT_EQ(pick_place::State::ERROR, result.current_state);
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("GRIPPER_NOT_SAFELY_OPEN", result.failure->code);
  EXPECT_EQ(0, checkpoints.calls);
}

TEST(Runner, ExecutionFailureCancelsAndObservesStationaryRobotBeforeReturningError)
{
  pick_place::StateActionRegistry actions;
  auto executor = std::make_shared<FakeExecutor>();
  executor->execute_result = {pick_place::ActionStatus::FAILED,
    pick_place::Failure{pick_place::FailureCategory::GRIPPER, "GRIPPER_OPEN_FAILED",
      "trajectory failed", {}}};
  actions.registerExecutor(pick_place::State::PREPARE_OPEN_GRIPPER, executor);
  pick_place::TransitionContractRegistry contracts;
  registerPrepareOpenGripperToMoveAboveObjectValidator(contracts);
  FakeObserver observer;
  FakeCheckpointStore checkpoints;
  const auto common_resume_validator = makeCommonResumeValidator();
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator);

  const auto result = runner.run({pick_place::RunMode::EXECUTE,
        pick_place::State::PREPARE_OPEN_GRIPPER, false, std::nullopt, 100});

  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("GRIPPER_OPEN_FAILED", result.failure->code);
  EXPECT_EQ(1, executor->cancel_calls);
  EXPECT_EQ(2, observer.calls);
  EXPECT_EQ(0, checkpoints.calls);
  EXPECT_DOUBLE_EQ(1.0, result.failure->metrics.at("arm_stationary_after_cancel"));
}

TEST(Runner, ResumePlanOnlyValidatesCheckpointAndPlansMoveAboveWithoutCommitting)
{
  pick_place::StateActionRegistry actions;
  auto planner = std::make_shared<FakePlanner>();
  actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, planner);
  pick_place::TransitionContractRegistry contracts;
  registerPrepareOpenGripperToMoveAboveObjectValidator(contracts);
  FakeObserver observer;
  FakeCheckpointStore checkpoints;
  checkpoints.load_result.checkpoint = makeCheckpoint(observer.snapshot);
  const auto common_resume_validator = makeCommonResumeValidator();
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator);

  const auto result = runner.run({pick_place::RunMode::PLAN_ONLY, std::nullopt, true,
        std::nullopt, 100});
  EXPECT_EQ(pick_place::RunStatus::PLAN_ONLY_COMPLETE, result.status);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, result.current_state);
  EXPECT_EQ(pick_place::State::DESCEND, *result.next_state);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, planner->last_state);
  EXPECT_EQ(0, checkpoints.calls);
  EXPECT_EQ(1, checkpoints.load_calls);
}

TEST(Runner, ResumeExecuteRunsMoveAboveObjectFromPrepareCheckpoint)
{
  pick_place::StateActionRegistry actions;
  auto planner = std::make_shared<FakePlanner>();
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, planner);
  actions.registerExecutor(pick_place::State::MOVE_ABOVE_OBJECT, executor);
  pick_place::TransitionContractRegistry contracts;
  registerPrepareOpenGripperToMoveAboveObjectValidator(contracts);
  registerMoveAboveObjectToDescendValidator(contracts);
  FakeObserver observer;
  FakeCheckpointStore checkpoints;
  checkpoints.load_result.checkpoint = makeCheckpoint(observer.snapshot);
  const auto common_resume_validator = makeCommonResumeValidator();
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator);

  const auto result = runner.run({pick_place::RunMode::EXECUTE,
        pick_place::State::MOVE_ABOVE_OBJECT, true, std::nullopt, 100});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, result.current_state);
  EXPECT_EQ(pick_place::State::DESCEND, *result.next_state);
  EXPECT_EQ(1, planner->calls);
  EXPECT_EQ(1, executor->calls);
}

TEST(Runner, ResumeRejectsWorldMismatchBeforePlanning)
{
  pick_place::StateActionRegistry actions;
  auto planner = std::make_shared<FakePlanner>();
  actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, planner);
  pick_place::TransitionContractRegistry contracts;
  registerPrepareOpenGripperToMoveAboveObjectValidator(contracts);
  FakeObserver observer;
  observer.snapshot.tcp_pose_world.x = 0.5;
  FakeCheckpointStore checkpoints;
  checkpoints.load_result.checkpoint = makeCheckpoint(makeSnapshot());
  const auto common_resume_validator = makeCommonResumeValidator();
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator);

  const auto result = runner.run({pick_place::RunMode::PLAN_ONLY, std::nullopt, true,
        std::nullopt, 100});
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("TCP_MOVED_DURING_GRIPPER_OPEN", result.failure->code);
  EXPECT_EQ(0, planner->calls);
}

TEST(TransitionContracts, RejectsTcpOrientationErrorAndReportsItsMetric)
{
  const auto before = makeSnapshot();
  auto after = before;
  after.tcp_pose_world = {0.3, 0.0, 0.987, 0.7071067811865476, 0.0, 0.0,
    0.7071067811865476};
  const pick_place::MoveAboveObjectToDescendValidator contract(
    {0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0}, {"table", "coke"}, 0.02, 0.1, 0.01, 0.1);

  const auto result = contract.validate(
    before, after, {pick_place::ActionStatus::SUCCEEDED, std::nullopt});

  EXPECT_FALSE(result.ok);
  EXPECT_GT(result.metrics.at("tcp_orientation_error_rad"), 1.5);
  ASSERT_FALSE(result.failures.empty());
  EXPECT_EQ("TCP_ORIENTATION_OUTSIDE_TARGET_TOLERANCE", result.failures.front().code);
}

TEST(TransitionContracts, RejectsGazeboAndMoveItCokePoseMismatch)
{
  const auto before = makeSnapshot();
  auto after = before;
  after.gazebo_coke_pose_world->y = -0.426;
  after.gazebo_coke_pose_world->z = 0.987;
  const pick_place::MoveAboveObjectToDescendValidator contract(
    {0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0}, {"table", "coke"}, 0.02, 0.1, 0.01, 0.1);

  const auto result = contract.validate(
    before, after, {pick_place::ActionStatus::SUCCEEDED, std::nullopt});

  EXPECT_FALSE(result.ok);
  EXPECT_GT(result.metrics.at("gazebo_moveit_coke_position_error"), 0.1);
  ASSERT_FALSE(result.failures.empty());
  EXPECT_EQ("COKE_POSE_MISMATCH", result.failures.front().code);
}

TEST(TransitionContracts, PrepareRequiresBothFingersSafelyOpenAndCokeStationary)
{
  auto before = makeSnapshot();
  before.gripper_open = false;
  auto after = before;
  after.gazebo_coke_pose_world->x += 0.1;
  const pick_place::PrepareOpenGripperToMoveAboveObjectValidator contract(
    {"table", "coke"}, 0.02, 0.1, 0.01, 0.1);

  const auto result = contract.validate(
    before, after, {pick_place::ActionStatus::SUCCEEDED, std::nullopt});

  EXPECT_FALSE(result.ok);
  ASSERT_GE(result.failures.size(), 2U);
  EXPECT_TRUE(std::any_of(result.failures.begin(), result.failures.end(),
    [](const pick_place::Failure & failure) {return failure.code == "GRIPPER_NOT_SAFELY_OPEN";}));
  EXPECT_GT(result.metrics.at("coke_position_drift"), 0.01);
}

TEST(CommonResumeValidator, RejectsSessionMismatch)
{
  const auto checkpoint = makeCheckpoint(makeSnapshot());
  auto current = makeSnapshot();
  current.simulation_session_id = "new-session";
  const auto validator = makeCommonResumeValidator();

  const auto result = validator.validate(checkpoint, current);

  EXPECT_FALSE(result.ok);
  ASSERT_FALSE(result.failures.empty());
  EXPECT_EQ("RESUME_SIMULATION_SESSION_MISMATCH", result.failures.front().code);
}

TEST(TransitionContracts, ResumeUsesTheSameMoveAboveObjectToDescendValidator)
{
  const auto checkpoint = makeCheckpoint(makeSnapshot());
  auto current = makeSnapshot();
  current.moveit_world_object_poses.at("coke").x = 0.5;
  pick_place::TransitionContractRegistry contracts;
  registerMoveAboveObjectToDescendValidator(contracts);

  const auto result = contracts.validateResume(
    {pick_place::State::MOVE_ABOVE_OBJECT, pick_place::State::DESCEND},
    makeSnapshot(), current);

  EXPECT_FALSE(result.ok);
  ASSERT_FALSE(result.failures.empty());
  EXPECT_EQ("COKE_POSE_MISMATCH", result.failures.front().code);
}

TEST(TransitionContracts, ResumeUsesTheSamePrepareOpenGripperValidator)
{
  auto expected = makeSnapshot();
  expected.gripper_open = true;
  auto current = expected;
  current.gripper_open = false;
  pick_place::TransitionContractRegistry contracts;
  registerPrepareOpenGripperToMoveAboveObjectValidator(contracts);

  const auto result = contracts.validateResume(
    {pick_place::State::PREPARE_OPEN_GRIPPER, pick_place::State::MOVE_ABOVE_OBJECT},
    expected, current);

  EXPECT_FALSE(result.ok);
  ASSERT_FALSE(result.failures.empty());
  EXPECT_EQ("GRIPPER_NOT_SAFELY_OPEN", result.failures.front().code);
}

TEST(Runner, RejectsFailureInjectionOutsideDryRun)
{
  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  const pick_place::StateMachineRunner runner(actions, contracts);

  const auto result = runner.run({pick_place::RunMode::PLAN_ONLY, std::nullopt, false,
        pick_place::State::MOVE_ABOVE_OBJECT, 100});
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("FAIL_AT_MODE_MISMATCH", result.failure->code);
}

TEST(TransitionContracts, MissingExecuteContractFailsClosed)
{
  pick_place::TransitionContractRegistry contracts;
  pick_place::TransitionTable table;
  const auto failure = contracts.validateExecuteCoverage(table);
  ASSERT_TRUE(failure.has_value());
  EXPECT_EQ("MISSING_TRANSITION_CONTRACT", failure->code);
}
