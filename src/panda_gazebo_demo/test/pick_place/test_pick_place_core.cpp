#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <limits>
#include <memory>
#include <type_traits>

#include <moveit_msgs/msg/collision_object.hpp>

#include "panda_gazebo_demo/pick_place/cartesian_plan_validation.hpp"
#include "panda_gazebo_demo/pick_place/checkpoint.hpp"
#include "panda_gazebo_demo/pick_place/descend_planner_executor.hpp"
#include "panda_gazebo_demo/pick_place/moveit_world_object_pose.hpp"
#include "panda_gazebo_demo/pick_place/plan_validation.hpp"
#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"
#include "panda_gazebo_demo/pick_place/runner.hpp"

namespace pick_place = panda_gazebo_demo::pick_place;

namespace
{

class FakePlanner final : public pick_place::IStatePlanner
{
public:
  pick_place::PlanResult plan(
    pick_place::State state, pick_place::State next_state,
    const pick_place::ObservationResult & observation) override
  {
    ++calls;
    last_state = state;
    last_next_state = next_state;
    last_observation = observation;
    auto artifact = std::make_shared<pick_place::PlanArtifact>();
    artifact->trajectory_points = 3;
    return {{pick_place::ActionStatus::SUCCEEDED, std::nullopt}, artifact};
  }

  int calls{0};
  pick_place::State last_state{pick_place::State::ERROR};
  pick_place::State last_next_state{pick_place::State::ERROR};
  pick_place::ObservationResult last_observation;
};

class FakeExecutor final : public pick_place::IStateExecutor
{
public:
  pick_place::ActionResult execute(const pick_place::ExecutionContext & context) override
  {
    ++calls;
    last_state = context.state;
    last_context = context;
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
  pick_place::ExecutionContext last_context{};
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

pick_place::CartesianPlanEvidence validDescendPlanEvidence()
{
  pick_place::CartesianPlanEvidence evidence;
  evidence.fraction = 1.0;
  evidence.trajectory_points = 3;
  evidence.max_joint_delta = 0.05;
  evidence.time_parameterized = true;
  evidence.start_tcp_pose = {0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0};
  evidence.tcp_path = {
    {0.3, 0.0, 0.97, 1.0, 0.0, 0.0, 0.0},
    {0.3, 0.0, 0.95, 1.0, 0.0, 0.0, 0.0},
    {0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0},
  };
  return evidence;
}

pick_place::CartesianPlanLimits descendPlanLimits()
{
  return {0.99, 0.2, 0.02, 0.1, 0.02, 0.1};
}

std::string firstFailureCode(const pick_place::ValidationResult & result)
{
  return result.failures.empty() ? "" : result.failures.front().code;
}

TEST(CartesianPlanValidation, AcceptsCompleteVerticalDescent)
{
  const auto result = pick_place::validateCartesianPlan(
    validDescendPlanEvidence(), {0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0}, descendPlanLimits());

  EXPECT_TRUE(result.ok);
  EXPECT_DOUBLE_EQ(1.0, result.metrics.at("cartesian_fraction"));
  EXPECT_DOUBLE_EQ(0.05, result.metrics.at("max_joint_delta"));
  EXPECT_DOUBLE_EQ(0.0, result.metrics.at("max_lateral_deviation"));
}

TEST(DescendPlannerExecutor, ImplementsIndependentPlannerAndExecutorInterfaces)
{
  EXPECT_TRUE((std::is_base_of_v<pick_place::IStatePlanner,
    pick_place::DescendPlannerExecutor>));
  EXPECT_TRUE((std::is_base_of_v<pick_place::IStateExecutor,
    pick_place::DescendPlannerExecutor>));
}

TEST(CartesianPlanValidation, RejectsPartialCartesianPath)
{
  auto evidence = validDescendPlanEvidence();
  evidence.fraction = 0.98;

  const auto result = pick_place::validateCartesianPlan(
    evidence, {0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0}, descendPlanLimits());

  EXPECT_FALSE(result.ok);
  EXPECT_EQ("CARTESIAN_FRACTION_BELOW_THRESHOLD", firstFailureCode(result));
}

TEST(CartesianPlanValidation, RejectsEmptyCartesianTrajectory)
{
  auto evidence = validDescendPlanEvidence();
  evidence.trajectory_points = 0;
  evidence.tcp_path.clear();

  const auto result = pick_place::validateCartesianPlan(
    evidence, {0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0}, descendPlanLimits());

  EXPECT_FALSE(result.ok);
  EXPECT_EQ("EMPTY_CARTESIAN_TRAJECTORY", firstFailureCode(result));
}

TEST(CartesianPlanValidation, RejectsTrajectoryWithoutIncreasingTime)
{
  auto evidence = validDescendPlanEvidence();
  evidence.time_parameterized = false;

  const auto result = pick_place::validateCartesianPlan(
    evidence, {0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0}, descendPlanLimits());

  EXPECT_FALSE(result.ok);
  EXPECT_EQ("CARTESIAN_TRAJECTORY_NOT_TIME_PARAMETERIZED", firstFailureCode(result));
}

TEST(CartesianPlanValidation, RejectsAdjacentJointJump)
{
  auto evidence = validDescendPlanEvidence();
  evidence.max_joint_delta = 0.21;

  const auto result = pick_place::validateCartesianPlan(
    evidence, {0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0}, descendPlanLimits());

  EXPECT_FALSE(result.ok);
  EXPECT_EQ("CARTESIAN_JOINT_JUMP_EXCEEDED", firstFailureCode(result));
}

TEST(CartesianPlanValidation, RejectsLateralSweep)
{
  auto evidence = validDescendPlanEvidence();
  evidence.tcp_path[1].x = 0.321;

  const auto result = pick_place::validateCartesianPlan(
    evidence, {0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0}, descendPlanLimits());

  EXPECT_FALSE(result.ok);
  EXPECT_EQ("CARTESIAN_LATERAL_DEVIATION_EXCEEDED", firstFailureCode(result));
}

TEST(CartesianPlanValidation, RejectsUpwardMotion)
{
  auto evidence = validDescendPlanEvidence();
  evidence.tcp_path[1].z = 0.975;

  const auto result = pick_place::validateCartesianPlan(
    evidence, {0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0}, descendPlanLimits());

  EXPECT_FALSE(result.ok);
  EXPECT_EQ("CARTESIAN_PATH_NOT_MONOTONIC_DESCENT", firstFailureCode(result));
}

TEST(CartesianPlanValidation, RejectsOrientationDrift)
{
  auto evidence = validDescendPlanEvidence();
  evidence.tcp_path[1] = {0.3, 0.0, 0.95, 0.7071067811865476, 0.0, 0.0,
    0.7071067811865476};

  const auto result = pick_place::validateCartesianPlan(
    evidence, {0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0}, descendPlanLimits());

  EXPECT_FALSE(result.ok);
  EXPECT_EQ("CARTESIAN_ORIENTATION_DEVIATION_EXCEEDED", firstFailureCode(result));
}

TEST(CartesianPlanValidation, RejectsWrongSixDofEndpoint)
{
  auto evidence = validDescendPlanEvidence();
  evidence.tcp_path.back().z = 0.909;

  const auto result = pick_place::validateCartesianPlan(
    evidence, {0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0}, descendPlanLimits());

  EXPECT_FALSE(result.ok);
  EXPECT_EQ("CARTESIAN_ENDPOINT_POSITION_OUTSIDE_TOLERANCE", firstFailureCode(result));
}

TEST(CartesianPlanValidation, RejectsNonFiniteTcpPathPose)
{
  auto evidence = validDescendPlanEvidence();
  evidence.tcp_path[1].x = std::numeric_limits<double>::quiet_NaN();

  const auto result = pick_place::validateCartesianPlan(
    evidence, {0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0}, descendPlanLimits());

  EXPECT_FALSE(result.ok);
  EXPECT_EQ("CARTESIAN_TCP_PATH_NON_FINITE", firstFailureCode(result));
}

TEST(PickPlaceTargetPolicy, ReturnsFixedMoveAboveObjectTarget)
{
  const pick_place::FixedPickPlaceTargetPolicy policy;
  const pick_place::ObservationResult observation{makeSnapshot(), std::nullopt};

  const auto result = policy.targetPose(
    pick_place::State::MOVE_ABOVE_OBJECT, pick_place::State::DESCEND, observation);

  ASSERT_TRUE(result.target_pose.has_value());
  EXPECT_FALSE(result.failure.has_value());
  EXPECT_DOUBLE_EQ(0.3, result.target_pose->x);
  EXPECT_DOUBLE_EQ(0.0, result.target_pose->y);
  EXPECT_DOUBLE_EQ(0.987, result.target_pose->z);
  EXPECT_DOUBLE_EQ(1.0, result.target_pose->qx);
  EXPECT_DOUBLE_EQ(0.0, result.target_pose->qy);
  EXPECT_DOUBLE_EQ(0.0, result.target_pose->qz);
  EXPECT_DOUBLE_EQ(0.0, result.target_pose->qw);
}

TEST(PickPlaceTargetPolicy, ReturnsFixedDescendTarget)
{
  const pick_place::FixedPickPlaceTargetPolicy policy;
  const pick_place::ObservationResult observation{makeSnapshot(), std::nullopt};

  const auto result = policy.targetPose(
    pick_place::State::DESCEND, pick_place::State::CLOSE_GRIPPER, observation);

  ASSERT_TRUE(result.target_pose.has_value());
  EXPECT_FALSE(result.failure.has_value());
  EXPECT_DOUBLE_EQ(0.3, result.target_pose->x);
  EXPECT_DOUBLE_EQ(0.0, result.target_pose->y);
  EXPECT_DOUBLE_EQ(0.87, result.target_pose->z);
  EXPECT_DOUBLE_EQ(1.0, result.target_pose->qx);
  EXPECT_DOUBLE_EQ(0.0, result.target_pose->qy);
  EXPECT_DOUBLE_EQ(0.0, result.target_pose->qz);
  EXPECT_DOUBLE_EQ(0.0, result.target_pose->qw);
}

TEST(PickPlaceTargetPolicy, RejectsUnsupportedTransition)
{
  const pick_place::FixedPickPlaceTargetPolicy policy;
  const pick_place::ObservationResult observation{makeSnapshot(), std::nullopt};

  const auto result = policy.targetPose(
    pick_place::State::PREPARE_OPEN_GRIPPER, pick_place::State::MOVE_ABOVE_OBJECT, observation);

  EXPECT_FALSE(result.target_pose.has_value());
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("TARGET_POLICY_UNSUPPORTED_TRANSITION", result.failure->code);
}

TEST(PickPlaceTargetPolicy, ConfigurationSignatureIncludesEveryFixedTarget)
{
  const pick_place::FixedPickPlaceTargetPolicy policy;

  EXPECT_EQ(
    "fixed-v4|above_pick=0.3,0,0.987,1,0,0,0|pick=0.3,0,0.87,1,0,0,0|"
    "above_place=0.3,0.2,0.987,1,0,0,0|place=0.3,0.2,0.87,1,0,0,0|"
    "supported_coke_offset_z=-0.034|"
    "recovery_safe_height=0.987",
    policy.configurationSignature());
}

class ObservationDrivenTargetPolicy final : public pick_place::PickPlaceTargetPolicy
{
public:
  pick_place::TargetPoseResult targetPose(
    pick_place::State current_state, pick_place::State next_state,
    const pick_place::ObservationResult & observation) const override
  {
    if (current_state != pick_place::State::MOVE_ABOVE_OBJECT ||
      next_state != pick_place::State::DESCEND || !observation.snapshot)
    {
      return {std::nullopt, pick_place::Failure{pick_place::FailureCategory::CONFIGURATION,
          "UNEXPECTED_POLICY_INPUT", "Unexpected target policy input", {}}};
    }
    auto target = observation.snapshot->tcp_pose_world;
    target.z += 0.05;
    return {target, std::nullopt};
  }

  std::string configurationSignature() const override
  {
    return "observation-driven-test-policy";
  }
};

TEST(TransitionContracts, ResolvesMoveAboveTargetFromPreExecutionObservation)
{
  const auto policy = std::make_shared<ObservationDrivenTargetPolicy>();
  const pick_place::MoveAboveObjectToDescendValidator contract(
    policy, std::vector<std::string>{"table", "coke"}, 0.001, 0.1, 0.01, 0.1);
  const auto before = makeSnapshot();
  auto after = before;
  after.tcp_pose_world.z += 0.05;

  const auto result = contract.validate(
    before, after, {pick_place::ActionStatus::SUCCEEDED, std::nullopt});

  EXPECT_TRUE(result.ok);
  EXPECT_DOUBLE_EQ(0.0, result.metrics.at("tcp_position_error"));
}

TEST(WorldObserverMath, NonFinitePositionReturnsInfinity)
{
  auto lhs = makeSnapshot().tcp_pose_world;
  const auto rhs = lhs;
  lhs.x = std::numeric_limits<double>::quiet_NaN();

  EXPECT_TRUE(std::isinf(pick_place::positionDistance(lhs, rhs)));
}

TEST(WorldObserverMath, NonFiniteQuaternionReturnsInfinity)
{
  auto lhs = makeSnapshot().tcp_pose_world;
  const auto rhs = lhs;
  lhs.qw = std::numeric_limits<double>::quiet_NaN();

  EXPECT_TRUE(std::isinf(pick_place::orientationDistance(lhs, rhs)));
}

TEST(TransitionContracts, RejectsNonFiniteTcpPose)
{
  const auto before = makeSnapshot();
  auto after = before;
  after.tcp_pose_world.x = std::numeric_limits<double>::quiet_NaN();
  const pick_place::MoveAboveObjectToDescendValidator contract(
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), {"table", "coke"},
    0.02, 0.1, 0.01, 0.1);

  const auto result = contract.validate(
    before, after, {pick_place::ActionStatus::SUCCEEDED, std::nullopt});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(std::isinf(result.metrics.at("tcp_position_error")));
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
  const auto target_policy = std::make_shared<pick_place::FixedPickPlaceTargetPolicy>();
  contracts.registerContract(
    {pick_place::State::MOVE_ABOVE_OBJECT, pick_place::State::DESCEND},
    std::make_shared<pick_place::MoveAboveObjectToDescendValidator>(
      target_policy,
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

void registerDescendToCloseGripperValidator(pick_place::TransitionContractRegistry & contracts)
{
  const auto target_policy = std::make_shared<pick_place::FixedPickPlaceTargetPolicy>();
  contracts.registerContract(
    {pick_place::State::DESCEND, pick_place::State::CLOSE_GRIPPER},
    std::make_shared<pick_place::DescendToCloseGripperValidator>(
      target_policy, std::vector<std::string>{"table", "coke"}, 0.02, 0.1, 0.01, 0.1));
}

pick_place::Checkpoint makeMoveAboveCheckpoint(const pick_place::WorldSnapshot & snapshot)
{
  auto checkpoint = makeCheckpoint(snapshot);
  checkpoint.last_completed_state = pick_place::State::MOVE_ABOVE_OBJECT;
  checkpoint.next_state = pick_place::State::DESCEND;
  return checkpoint;
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

class RecordingExecutionObservationSink final : public pick_place::IExecutionObservationSink
{
public:
  void record(
    pick_place::State state, const pick_place::WorldSnapshot & before,
    const pick_place::WorldSnapshot & after) override
  {
    ++calls;
    last_state = state;
    before_snapshot = before;
    after_snapshot = after;
  }

  int calls{0};
  pick_place::State last_state{pick_place::State::ERROR};
  std::optional<pick_place::WorldSnapshot> before_snapshot;
  std::optional<pick_place::WorldSnapshot> after_snapshot;
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

TEST(TransitionTable, CarryFailureUsesCarryRecovery)
{
  const pick_place::TransitionTable table;

  EXPECT_EQ(
    pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT,
    table.resolve(pick_place::State::MOVE_ABOVE_PLACE, pick_place::ActionStatus::FAILED));
}

TEST(TransitionTable, NewRecoveryStatesRoundTripAndAreNotForwardActions)
{
  const std::map<pick_place::State, std::string> expected{
    {pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT, "RECOVER_LIFT_TO_SAFE_HEIGHT"},
    {pick_place::State::RECOVER_MOVE_ABOVE_PICK, "RECOVER_MOVE_ABOVE_PICK"},
    {pick_place::State::RECOVER_DESCEND_TO_PICK, "RECOVER_DESCEND_TO_PICK"},
  };

  for (const auto & [state, name] : expected) {
    EXPECT_STREQ(name.c_str(), pick_place::toString(state));
    EXPECT_EQ(state, pick_place::stateFromString(name));
    EXPECT_FALSE(pick_place::isForwardAction(state));
  }
}

TEST(TransitionTable, ActionStatesIncludeForwardAndRecoveryButRejectControlStates)
{
  EXPECT_TRUE(pick_place::isAction(pick_place::State::MOVE_ABOVE_OBJECT));
  EXPECT_TRUE(pick_place::isAction(pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT));
  EXPECT_TRUE(pick_place::isAction(pick_place::State::RECOVER_RETREAT));
  EXPECT_FALSE(pick_place::isAction(pick_place::State::IDLE));
  EXPECT_FALSE(pick_place::isAction(pick_place::State::DONE));
  EXPECT_FALSE(pick_place::isAction(pick_place::State::ERROR));
}

TEST(TransitionTable, CarryRecoveryReturnsObjectToPickBeforeCleanup)
{
  const pick_place::TransitionTable table;

  EXPECT_EQ(
    pick_place::State::RECOVER_MOVE_ABOVE_PICK,
    table.resolve(
      pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT, pick_place::ActionStatus::SUCCEEDED));
  EXPECT_EQ(
    pick_place::State::RECOVER_DESCEND_TO_PICK,
    table.resolve(
      pick_place::State::RECOVER_MOVE_ABOVE_PICK, pick_place::ActionStatus::SUCCEEDED));
  EXPECT_EQ(
    pick_place::State::RECOVER_OPEN_GRIPPER,
    table.resolve(
      pick_place::State::RECOVER_DESCEND_TO_PICK, pick_place::ActionStatus::SUCCEEDED));
}

TEST(TransitionTable, UsesCanonicalFailureEdges)
{
  const pick_place::TransitionTable table;
  const std::map<pick_place::State, pick_place::State> expected{
    {pick_place::State::PREPARE_OPEN_GRIPPER, pick_place::State::ERROR},
    {pick_place::State::MOVE_ABOVE_OBJECT, pick_place::State::RECOVER_RETREAT},
    {pick_place::State::DESCEND, pick_place::State::RECOVER_OPEN_GRIPPER},
    {pick_place::State::CLOSE_GRIPPER, pick_place::State::RECOVER_OPEN_GRIPPER},
    {pick_place::State::ATTACH_GAZEBO, pick_place::State::RECOVER_OPEN_GRIPPER},
    {pick_place::State::ATTACH_MOVEIT, pick_place::State::RECOVER_OPEN_GRIPPER},
    {pick_place::State::LIFT, pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT},
    {pick_place::State::MOVE_ABOVE_PLACE, pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT},
    {pick_place::State::DESCEND_TO_PLACE, pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT},
    {pick_place::State::OPEN_GRIPPER, pick_place::State::RECOVER_OPEN_GRIPPER},
    {pick_place::State::DETACH_GAZEBO, pick_place::State::RECOVER_DETACH_GAZEBO},
    {pick_place::State::DETACH_MOVEIT, pick_place::State::RECOVER_DETACH_MOVEIT},
    {pick_place::State::SYNC_WORLD_OBJECT, pick_place::State::RECOVER_SYNC_WORLD_OBJECT},
    {pick_place::State::RETREAT, pick_place::State::RECOVER_RETREAT},
  };

  for (const auto & [state, recovery_state] : expected) {
    EXPECT_EQ(recovery_state, table.resolve(state, pick_place::ActionStatus::FAILED)) <<
      pick_place::toString(state);
  }
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
  pick_place::PlanValidatorRegistry plan_validators;
  plan_validators.registerValidator(
    pick_place::State::MOVE_ABOVE_OBJECT,
    std::make_shared<pick_place::NonEmptyPlanValidator>());
  pick_place::TransitionContractRegistry contracts;
  FakeObserver observer;
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, nullptr, nullptr, nullptr, &plan_validators);

  const auto result = runner.run({pick_place::RunMode::PLAN_ONLY, std::nullopt, false, std::nullopt,
        100});
  EXPECT_EQ(pick_place::RunStatus::PLAN_ONLY_COMPLETE, result.status);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, result.current_state);
  EXPECT_EQ(pick_place::State::DESCEND, *result.next_state);
  EXPECT_EQ(1, planner->calls);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, planner->last_state);
  EXPECT_EQ(pick_place::State::DESCEND, planner->last_next_state);
  ASSERT_TRUE(planner->last_observation.snapshot.has_value());
  EXPECT_EQ("test-session", planner->last_observation.snapshot->simulation_session_id);
  EXPECT_EQ(1, observer.calls);
}

TEST(Runner, RejectsPlannedExecuteStateWithoutPlanValidator)
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

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("PLAN_VALIDATOR_NOT_REGISTERED", result.failure->code);
  EXPECT_EQ(0, executor->calls);
}

TEST(Runner, PassesVerifiedBeforeSnapshotToExecutor)
{
  pick_place::StateActionRegistry actions;
  auto planner = std::make_shared<FakePlanner>();
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, planner);
  actions.registerExecutor(pick_place::State::MOVE_ABOVE_OBJECT, executor);
  pick_place::PlanValidatorRegistry plan_validators;
  plan_validators.registerValidator(
    pick_place::State::MOVE_ABOVE_OBJECT,
    std::make_shared<pick_place::NonEmptyPlanValidator>());
  pick_place::TransitionContractRegistry contracts;
  registerPrepareOpenGripperToMoveAboveObjectValidator(contracts);
  registerMoveAboveObjectToDescendValidator(contracts);
  FakeObserver observer;
  FakeCheckpointStore checkpoints;
  checkpoints.load_result.checkpoint = makeCheckpoint(observer.snapshot);
  const auto common_resume_validator = makeCommonResumeValidator();
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator, nullptr,
    &plan_validators);

  const auto result = runner.run({pick_place::RunMode::EXECUTE,
        pick_place::State::MOVE_ABOVE_OBJECT, true, std::nullopt, 100});

  ASSERT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_NEAR(
    observer.snapshot.tcp_pose_world.x,
    executor->last_context.before.tcp_pose_world.x, 1e-12);
  EXPECT_NEAR(
    observer.snapshot.tcp_pose_world.y,
    executor->last_context.before.tcp_pose_world.y, 1e-12);
  EXPECT_NEAR(
    observer.snapshot.tcp_pose_world.z,
    executor->last_context.before.tcp_pose_world.z, 1e-12);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, executor->last_context.state);
  EXPECT_EQ(pick_place::State::DESCEND, executor->last_context.next_state);
}

TEST(PlanValidatorRegistry, RejectsEmptyTrajectory)
{
  pick_place::PlanValidatorRegistry registry;
  registry.registerValidator(
    pick_place::State::MOVE_ABOVE_OBJECT,
    std::make_shared<pick_place::NonEmptyPlanValidator>());
  const auto snapshot = makeSnapshot();
  pick_place::PlanArtifact artifact;
  artifact.trajectory_points = 0;

  const auto result = registry.validate(
    pick_place::State::MOVE_ABOVE_OBJECT, snapshot, artifact);

  EXPECT_FALSE(result.ok);
  ASSERT_FALSE(result.failures.empty());
  EXPECT_EQ("EMPTY_PLAN_ARTIFACT", result.failures.front().code);
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

TEST(Runner, RecordsExistingPreAndPostExecutionSnapshotsOnce)
{
  pick_place::StateActionRegistry actions;
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerExecutor(pick_place::State::PREPARE_OPEN_GRIPPER, executor);
  pick_place::TransitionContractRegistry contracts;
  registerPrepareOpenGripperToMoveAboveObjectValidator(contracts);
  FakeObserver observer;
  observer.snapshot.gripper_open = false;
  observer.snapshot.gazebo_coke_pose_world->x = 0.301;
  observer.after_snapshot = observer.snapshot;
  observer.after_snapshot->gripper_open = true;
  observer.after_snapshot->gazebo_coke_pose_world->x = 0.302;
  observer.after_snapshot->moveit_world_object_poses.at("coke").x = 0.302;
  FakeCheckpointStore checkpoints;
  const auto common_resume_validator = makeCommonResumeValidator();
  RecordingExecutionObservationSink sink;
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator, &sink);

  const auto result = runner.run({pick_place::RunMode::EXECUTE,
        pick_place::State::PREPARE_OPEN_GRIPPER, false, std::nullopt, 100});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(1, sink.calls);
  EXPECT_EQ(pick_place::State::PREPARE_OPEN_GRIPPER, sink.last_state);
  ASSERT_TRUE(sink.before_snapshot.has_value());
  ASSERT_TRUE(sink.after_snapshot.has_value());
  EXPECT_DOUBLE_EQ(0.301, sink.before_snapshot->gazebo_coke_pose_world->x);
  EXPECT_DOUBLE_EQ(0.302, sink.after_snapshot->gazebo_coke_pose_world->x);
  EXPECT_EQ(2, observer.calls);
}

TEST(Runner, ExecuteWorkflowAdvancesThroughRegisteredStatesUntilStopAfter)
{
  pick_place::StateActionRegistry actions;
  auto planner = std::make_shared<FakePlanner>();
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerExecutor(pick_place::State::PREPARE_OPEN_GRIPPER, executor);
  actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, planner);
  actions.registerExecutor(pick_place::State::MOVE_ABOVE_OBJECT, executor);
  pick_place::PlanValidatorRegistry plan_validators;
  plan_validators.registerValidator(
    pick_place::State::MOVE_ABOVE_OBJECT,
    std::make_shared<pick_place::NonEmptyPlanValidator>());
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
    actions, contracts, &observer, &checkpoints, &common_resume_validator, nullptr,
    &plan_validators);

  const auto result = runner.run({pick_place::RunMode::EXECUTE,
        pick_place::State::MOVE_ABOVE_OBJECT, false, std::nullopt, 100});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, result.current_state);
  EXPECT_EQ(pick_place::State::DESCEND, *result.next_state);
  EXPECT_EQ(3U, result.transition_count);
  EXPECT_EQ(2, executor->calls);
  EXPECT_EQ(1, planner->calls);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, planner->last_state);
  EXPECT_EQ(pick_place::State::DESCEND, planner->last_next_state);
  ASSERT_TRUE(planner->last_observation.snapshot.has_value());
  EXPECT_TRUE(planner->last_observation.snapshot->gripper_open);
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
  pick_place::PlanValidatorRegistry plan_validators;
  plan_validators.registerValidator(
    pick_place::State::MOVE_ABOVE_OBJECT,
    std::make_shared<pick_place::NonEmptyPlanValidator>());
  pick_place::TransitionContractRegistry contracts;
  registerPrepareOpenGripperToMoveAboveObjectValidator(contracts);
  FakeObserver observer;
  FakeCheckpointStore checkpoints;
  checkpoints.load_result.checkpoint = makeCheckpoint(observer.snapshot);
  const auto common_resume_validator = makeCommonResumeValidator();
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator, nullptr,
    &plan_validators);

  const auto result = runner.run({pick_place::RunMode::PLAN_ONLY, std::nullopt, true,
        std::nullopt, 100});
  EXPECT_EQ(pick_place::RunStatus::PLAN_ONLY_COMPLETE, result.status);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, result.current_state);
  EXPECT_EQ(pick_place::State::DESCEND, *result.next_state);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, planner->last_state);
  EXPECT_EQ(0, checkpoints.calls);
  EXPECT_EQ(1, checkpoints.load_calls);
}

TEST(Runner, ResumePlanOnlyWaitsForForwardCokeStationaryEvidence)
{
  pick_place::StateActionRegistry actions;
  auto planner = std::make_shared<FakePlanner>();
  actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, planner);
  pick_place::PlanValidatorRegistry plan_validators;
  plan_validators.registerValidator(
    pick_place::State::MOVE_ABOVE_OBJECT,
    std::make_shared<pick_place::NonEmptyPlanValidator>());
  pick_place::TransitionContractRegistry contracts;
  registerPrepareOpenGripperToMoveAboveObjectValidator(contracts);
  FakeObserver observer;
  observer.snapshot.gazebo_coke_stationary = false;
  observer.after_snapshot = observer.snapshot;
  observer.after_snapshot->gazebo_coke_stationary = true;
  FakeCheckpointStore checkpoints;
  auto checkpoint_snapshot = observer.snapshot;
  checkpoint_snapshot.gazebo_coke_stationary = true;
  checkpoints.load_result.checkpoint = makeCheckpoint(checkpoint_snapshot);
  checkpoints.load_result.checkpoint->expected.gazebo_coke_stationary = true;
  const auto common_resume_validator = makeCommonResumeValidator();
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator, nullptr,
    &plan_validators);

  const auto result = runner.run({pick_place::RunMode::PLAN_ONLY, std::nullopt, true,
        std::nullopt, 100});

  EXPECT_EQ(pick_place::RunStatus::PLAN_ONLY_COMPLETE, result.status);
  EXPECT_GE(observer.calls, 2);
  EXPECT_EQ(1, planner->calls);
}

TEST(Runner, ResumeExecuteRunsMoveAboveObjectFromPrepareCheckpoint)
{
  pick_place::StateActionRegistry actions;
  auto planner = std::make_shared<FakePlanner>();
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, planner);
  actions.registerExecutor(pick_place::State::MOVE_ABOVE_OBJECT, executor);
  pick_place::PlanValidatorRegistry plan_validators;
  plan_validators.registerValidator(
    pick_place::State::MOVE_ABOVE_OBJECT,
    std::make_shared<pick_place::NonEmptyPlanValidator>());
  pick_place::TransitionContractRegistry contracts;
  registerPrepareOpenGripperToMoveAboveObjectValidator(contracts);
  registerMoveAboveObjectToDescendValidator(contracts);
  FakeObserver observer;
  FakeCheckpointStore checkpoints;
  checkpoints.load_result.checkpoint = makeCheckpoint(observer.snapshot);
  const auto common_resume_validator = makeCommonResumeValidator();
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator, nullptr,
    &plan_validators);

  const auto result = runner.run({pick_place::RunMode::EXECUTE,
        pick_place::State::MOVE_ABOVE_OBJECT, true, std::nullopt, 100});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_OBJECT, result.current_state);
  EXPECT_EQ(pick_place::State::DESCEND, *result.next_state);
  EXPECT_EQ(1, planner->calls);
  EXPECT_EQ(1, executor->calls);
}

TEST(Runner, ResumeExecuteStopsSuccessfullyAfterDescendCheckpoint)
{
  pick_place::StateActionRegistry actions;
  auto planner = std::make_shared<FakePlanner>();
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerPlanner(pick_place::State::DESCEND, planner);
  actions.registerExecutor(pick_place::State::DESCEND, executor);
  pick_place::PlanValidatorRegistry plan_validators;
  plan_validators.registerValidator(
    pick_place::State::DESCEND,
    std::make_shared<pick_place::NonEmptyPlanValidator>());
  pick_place::TransitionContractRegistry contracts;
  registerMoveAboveObjectToDescendValidator(contracts);
  registerDescendToCloseGripperValidator(contracts);
  FakeObserver observer;
  observer.after_snapshot = observer.snapshot;
  observer.after_snapshot->tcp_pose_world.z = 0.87;
  FakeCheckpointStore checkpoints;
  checkpoints.load_result.checkpoint = makeMoveAboveCheckpoint(observer.snapshot);
  const auto common_resume_validator = makeCommonResumeValidator();
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator, nullptr,
    &plan_validators);

  const auto result = runner.run({pick_place::RunMode::EXECUTE,
        pick_place::State::DESCEND, true, std::nullopt, 100});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  EXPECT_EQ(pick_place::State::DESCEND, result.current_state);
  ASSERT_TRUE(result.next_state.has_value());
  EXPECT_EQ(pick_place::State::CLOSE_GRIPPER, *result.next_state);
  EXPECT_EQ(1, planner->calls);
  EXPECT_EQ(1, executor->calls);
  ASSERT_TRUE(checkpoints.checkpoint.has_value());
  EXPECT_EQ(pick_place::State::DESCEND, checkpoints.checkpoint->last_completed_state);
}

TEST(Runner, ResumeExecuteReachesExpectedUnregisteredCloseGripperBoundary)
{
  pick_place::StateActionRegistry actions;
  auto planner = std::make_shared<FakePlanner>();
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerPlanner(pick_place::State::DESCEND, planner);
  actions.registerExecutor(pick_place::State::DESCEND, executor);
  pick_place::PlanValidatorRegistry plan_validators;
  plan_validators.registerValidator(
    pick_place::State::DESCEND,
    std::make_shared<pick_place::NonEmptyPlanValidator>());
  pick_place::TransitionContractRegistry contracts;
  registerMoveAboveObjectToDescendValidator(contracts);
  registerDescendToCloseGripperValidator(contracts);
  FakeObserver observer;
  observer.after_snapshot = observer.snapshot;
  observer.after_snapshot->tcp_pose_world.z = 0.87;
  FakeCheckpointStore checkpoints;
  checkpoints.load_result.checkpoint = makeMoveAboveCheckpoint(observer.snapshot);
  const auto common_resume_validator = makeCommonResumeValidator();
  const pick_place::StateMachineRunner runner(
    actions, contracts, &observer, &checkpoints, &common_resume_validator, nullptr,
    &plan_validators);

  const auto result = runner.run({pick_place::RunMode::EXECUTE, std::nullopt, true,
        std::nullopt, 100});

  EXPECT_EQ(pick_place::RunStatus::ERROR, result.status);
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ("EXECUTE_ACTION_NOT_REGISTERED", result.failure->code);
  EXPECT_NE(std::string::npos, result.failure->message.find("CLOSE_GRIPPER"));
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
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), {"table", "coke"}, 0.02, 0.1,
    0.01, 0.1);

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
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), {"table", "coke"}, 0.02, 0.1,
    0.01, 0.1);

  const auto result = contract.validate(
    before, after, {pick_place::ActionStatus::SUCCEEDED, std::nullopt});

  EXPECT_FALSE(result.ok);
  EXPECT_GT(result.metrics.at("gazebo_moveit_coke_position_error"), 0.1);
  ASSERT_FALSE(result.failures.empty());
  EXPECT_EQ("COKE_POSE_MISMATCH", result.failures.front().code);
}

TEST(TransitionContracts, DescendRequiresTcpAtMoveAboveTargetBeforePlanning)
{
  auto before = makeSnapshot();
  before.tcp_pose_world.x += 0.03;
  const pick_place::DescendToCloseGripperValidator contract(
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), {"table", "coke"}, 0.02, 0.1,
    0.01, 0.1);

  const auto result = contract.validatePrecondition(before);

  EXPECT_FALSE(result.ok);
  EXPECT_GT(result.metrics.at("tcp_position_error"), 0.02);
  EXPECT_EQ("TCP_OUTSIDE_DESCEND_START_TOLERANCE", firstFailureCode(result));
}

TEST(TransitionContracts, DescendRejectsCokeOrientationDriftAfterExecution)
{
  const auto before = makeSnapshot();
  auto after = before;
  after.tcp_pose_world.z = 0.87;
  const pick_place::Pose3d rotated_coke{
    0.3, 0.0, 0.836, 0.0, 0.0, 0.1, 0.99498743710662};
  after.gazebo_coke_pose_world = rotated_coke;
  after.moveit_world_object_poses.at("coke") = rotated_coke;
  const pick_place::DescendToCloseGripperValidator contract(
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), {"table", "coke"}, 0.02, 0.1,
    0.01, 0.1);

  const auto result = contract.validate(
    before, after, {pick_place::ActionStatus::SUCCEEDED, std::nullopt});

  EXPECT_FALSE(result.ok);
  EXPECT_GT(result.metrics.at("coke_orientation_drift_rad"), 0.1);
  EXPECT_EQ("COKE_ROTATED_DURING_MOTION", firstFailureCode(result));
}

TEST(TransitionContracts, DescendAcceptsStableSixDofCompletion)
{
  const auto before = makeSnapshot();
  auto after = before;
  after.tcp_pose_world.z = 0.87;
  const pick_place::DescendToCloseGripperValidator contract(
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), {"table", "coke"}, 0.02, 0.1,
    0.01, 0.1);

  const auto result = contract.validate(
    before, after, {pick_place::ActionStatus::SUCCEEDED, std::nullopt});

  EXPECT_TRUE(result.ok);
  EXPECT_DOUBLE_EQ(0.0, result.metrics.at("tcp_position_error"));
  EXPECT_DOUBLE_EQ(0.0, result.metrics.at("tcp_orientation_error_rad"));
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

TEST(CommonResumeValidator, RejectsJointPositionDrift)
{
  const auto checkpoint = makeCheckpoint(makeSnapshot());
  auto current = makeSnapshot();
  current.joint_positions.at("panda_joint1") = 0.02;
  const pick_place::CommonResumeValidator validator(
    "test-config", "test-session", 0.01);

  const auto result = validator.validate(checkpoint, current);

  EXPECT_FALSE(result.ok);
  EXPECT_EQ("RESUME_JOINT_POSITION_MISMATCH", firstFailureCode(result));
}

TEST(CommonResumeValidator, RejectsMissingJointPosition)
{
  const auto checkpoint = makeCheckpoint(makeSnapshot());
  auto current = makeSnapshot();
  current.joint_positions.erase("panda_joint1");
  const pick_place::CommonResumeValidator validator(
    "test-config", "test-session", 0.01);

  const auto result = validator.validate(checkpoint, current);

  EXPECT_FALSE(result.ok);
  EXPECT_EQ("RESUME_JOINT_POSITION_MISMATCH", firstFailureCode(result));
}

TEST(CommonResumeValidator, RejectsNonFiniteJointPosition)
{
  auto checkpoint = makeCheckpoint(makeSnapshot());
  auto current = makeSnapshot();
  checkpoint.expected.joint_positions.at("panda_joint1") =
    std::numeric_limits<double>::quiet_NaN();
  const pick_place::CommonResumeValidator validator(
    "test-config", "test-session", 0.01);

  const auto result = validator.validate(checkpoint, current);

  EXPECT_FALSE(result.ok);
  EXPECT_EQ("RESUME_JOINT_POSITION_MISMATCH", firstFailureCode(result));
}

TEST(CommonResumeValidator, RecoveryAllowsFiniteJointDriftForFactReclassification)
{
  auto checkpoint = makeCheckpoint(makeSnapshot());
  checkpoint.phase = pick_place::CheckpointPhase::RECOVERY;
  checkpoint.failed_state = pick_place::State::MOVE_ABOVE_PLACE;
  checkpoint.original_failure = pick_place::Failure{
    pick_place::FailureCategory::EXECUTION, "MOVE_FAILED", "move failed", {}};
  auto current = makeSnapshot();
  current.joint_positions.at("panda_joint1") = 0.5;
  const pick_place::CommonResumeValidator validator(
    "test-config", "test-session", 0.01);

  const auto result = validator.validate(checkpoint, current);

  EXPECT_TRUE(result.ok);
  EXPECT_DOUBLE_EQ(0.5, result.metrics.at("resume_joint_position_error_max"));
}

TEST(CommonResumeValidator, RecoveryRejectsNonFiniteJointEvidence)
{
  auto checkpoint = makeCheckpoint(makeSnapshot());
  checkpoint.phase = pick_place::CheckpointPhase::RECOVERY;
  checkpoint.failed_state = pick_place::State::MOVE_ABOVE_PLACE;
  checkpoint.original_failure = pick_place::Failure{
    pick_place::FailureCategory::EXECUTION, "MOVE_FAILED", "move failed", {}};
  auto current = makeSnapshot();
  current.joint_positions.at("panda_joint1") =
    std::numeric_limits<double>::quiet_NaN();
  const pick_place::CommonResumeValidator validator(
    "test-config", "test-session", 0.01);

  const auto result = validator.validate(checkpoint, current);

  EXPECT_FALSE(result.ok);
  EXPECT_EQ("RESUME_JOINT_POSITION_MISMATCH", firstFailureCode(result));
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

TEST(TransitionContracts, ResumeUsesTheSameDescendToCloseGripperValidator)
{
  auto expected = makeSnapshot();
  expected.tcp_pose_world.z = 0.87;
  auto current = expected;
  const pick_place::Pose3d rotated_coke{
    0.3, 0.0, 0.836, 0.0, 0.0, 0.1, 0.99498743710662};
  current.gazebo_coke_pose_world = rotated_coke;
  current.moveit_world_object_poses.at("coke") = rotated_coke;
  pick_place::TransitionContractRegistry contracts;
  registerDescendToCloseGripperValidator(contracts);

  const auto result = contracts.validateResume(
    {pick_place::State::DESCEND, pick_place::State::CLOSE_GRIPPER}, expected, current);

  EXPECT_FALSE(result.ok);
  EXPECT_EQ("COKE_ROTATED_DURING_MOTION", firstFailureCode(result));
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
