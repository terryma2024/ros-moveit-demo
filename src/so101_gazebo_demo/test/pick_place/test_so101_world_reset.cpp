#include <gtest/gtest.h>

#include <chrono>
#include <memory>
#include <optional>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include "so101_gazebo_demo/pick_place/so101_profile.hpp"
#include "so101_gazebo_demo/pick_place/world_reset_coordinator.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{

ActionResult succeeded()
{
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult failed(std::string code)
{
  return {ActionStatus::FAILED,
          Failure{FailureCategory::WORLD_INCONSISTENCY, std::move(code), "failure", {}}};
}

class FakeGazeboResetAdapter final : public IGazeboResetAdapter
{
public:
  std::optional<GazeboResetState> observe() override
  {
    ++observe_calls;
    return observation_available ? std::optional<GazeboResetState>(state) : std::nullopt;
  }

  ActionResult detachTaskObject() override
  {
    ++detach_calls;
    commands.emplace_back("gazebo_detach");
    if (events) events->emplace_back("gazebo_detach");
    if (detach_result.status == ActionStatus::SUCCEEDED && detach_converges) {
      state.task_object_attached = false;
      ++state.attachment_revision;
    }
    return detach_result;
  }

  ActionResult setTaskObjectWorldPose(const Pose3d & pose) override
  {
    ++set_pose_calls;
    commands.emplace_back("gazebo_pose");
    if (events) events->emplace_back("gazebo_pose");
    if (set_pose_result.status == ActionStatus::SUCCEEDED && pose_converges) {
      state.task_object_world_pose = pose;
      ++state.pose_revision;
    }
    return set_pose_result;
  }

  GazeboResetState state;
  bool observation_available{true};
  bool detach_converges{true};
  bool pose_converges{true};
  ActionResult detach_result{succeeded()};
  ActionResult set_pose_result{succeeded()};
  int observe_calls{0};
  int detach_calls{0};
  int set_pose_calls{0};
  std::vector<std::string> commands;
  std::shared_ptr<std::vector<std::string>> events;
};

class FakeMoveItSceneAdapter final : public IMoveItSceneAdapter
{
public:
  ActionResult attachTaskObject(const MoveItAttachmentSpec &) override
  {
    return succeeded();
  }

  ActionResult detachTaskObject() override
  {
    ++detach_calls;
    commands.emplace_back("moveit_detach");
    if (events) events->emplace_back("moveit_detach");
    if (detach_result.status == ActionStatus::SUCCEEDED && detach_converges) {
      state.task_object_attached = false;
      state.task_object_in_world = true;
      state.attached_link.clear();
      state.touch_links.clear();
    }
    return detach_result;
  }

  ActionResult upsertTaskObjectWorldPose(const Pose3d & pose) override
  {
    ++task_object_upsert_calls;
    commands.emplace_back("moveit_task_object");
    if (events) events->emplace_back("moveit_task_object");
    if (task_object_upsert_result.status == ActionStatus::SUCCEEDED && upsert_converges) {
      state.task_object_attached = false;
      state.task_object_in_world = true;
      state.task_object_world_pose = pose;
    }
    return task_object_upsert_result;
  }

  ActionResult upsertTableWorldPose(const Pose3d & pose) override
  {
    ++table_upsert_calls;
    commands.emplace_back("moveit_table");
    if (events) events->emplace_back("moveit_table");
    if (table_upsert_result.status == ActionStatus::SUCCEEDED && upsert_converges) {
      state.table_in_world = true;
      state.table_world_pose = pose;
    }
    return table_upsert_result;
  }

  ActionResult upsertPedestalWorldPose(const Pose3d & pose) override
  {
    ++pedestal_upsert_calls;
    commands.emplace_back("moveit_pedestal");
    if (events) events->emplace_back("moveit_pedestal");
    if (pedestal_upsert_result.status == ActionStatus::SUCCEEDED && upsert_converges) {
      state.pedestal_in_world = true;
      state.pedestal_world_pose = pose;
    }
    return pedestal_upsert_result;
  }

  std::optional<MoveItSceneState> observe() override
  {
    ++observe_calls;
    return observation_available ? std::optional<MoveItSceneState>(state) : std::nullopt;
  }

  MoveItSceneState state;
  bool observation_available{true};
  bool detach_converges{true};
  bool upsert_converges{true};
  ActionResult detach_result{succeeded()};
  ActionResult task_object_upsert_result{succeeded()};
  ActionResult table_upsert_result{succeeded()};
  ActionResult pedestal_upsert_result{succeeded()};
  int observe_calls{0};
  int detach_calls{0};
  int task_object_upsert_calls{0};
  int table_upsert_calls{0};
  int pedestal_upsert_calls{0};
  std::vector<std::string> commands;
  std::shared_ptr<std::vector<std::string>> events;
};

class FakeRobotHomeResetAdapter final : public IRobotHomeResetAdapter
{
public:
  std::optional<CurrentJointStateEvidence> observeJoints() override
  {
    ++observe_calls;
    if (events) events->emplace_back("observe_joints");
    return observation_available ? joints : std::nullopt;
  }
  ActionResult commandGripper(double q6) override
  {
    ++gripper_calls;
    gripper_targets.push_back(q6);
    if (events) events->emplace_back("gripper:" + std::to_string(q6));
    if (gripper_result.status == ActionStatus::SUCCEEDED &&
        (q6 != -0.059303612618397 || home_gripper_converges)) {
      joints->gripper_position = q6 + home_gripper_offset;
      joints->gripper_velocity = 0.0;
    }
    return gripper_result;
  }
  PlanResult planArmHome(const std::vector<double> & goal) override
  {
    ++plan_calls;
    last_arm_goal = goal;
    if (events) events->emplace_back("plan_arm_home");
    return {plan_result, plan_result.status == ActionStatus::SUCCEEDED ? plan : nullptr};
  }
  ActionResult executeArmHome(const PlanArtifact &) override
  {
    ++execute_calls;
    if (events) events->emplace_back("execute_arm_home");
    if (execute_result.status == ActionStatus::SUCCEEDED && arm_converges) {
      joints->positions = last_arm_goal;
      if (!joints->positions.empty()) {
        joints->positions.back() += arm_home_residual;
      }
      joints->velocities.assign(last_arm_goal.size(), 0.0);
    }
    return execute_result;
  }
  ActionResult cancelArmAndWait() override { return succeeded(); }

  std::optional<CurrentJointStateEvidence> joints;
  std::shared_ptr<PlanArtifact> plan{[] {
    auto value = std::make_shared<PlanArtifact>();
    value->trajectory_points = 2;
    return value;
  }()};
  bool observation_available{true};
  bool home_gripper_converges{true};
  bool arm_converges{true};
  double home_gripper_offset{0.0};
  double arm_home_residual{0.0};
  ActionResult gripper_result{succeeded()};
  ActionResult plan_result{succeeded()};
  ActionResult execute_result{succeeded()};
  int observe_calls{0};
  int gripper_calls{0};
  int plan_calls{0};
  int execute_calls{0};
  std::vector<double> gripper_targets;
  std::vector<double> last_arm_goal;
  std::shared_ptr<std::vector<std::string>> events;
};

std::shared_ptr<FakeRobotHomeResetAdapter> robotAdapter()
{
  auto robot = std::make_shared<FakeRobotHomeResetAdapter>();
  CurrentJointStateEvidence joints;
  joints.joint_names = {"1", "2", "3", "4", "5"};
  joints.positions = {0.2, -0.1, 0.1, -0.2, 0.1};
  joints.velocities = {0.0, 0.0, 0.0, 0.0, 0.0};
  joints.gripper_position = 0.5;
  joints.gripper_velocity = 0.0;
  joints.received_at = std::chrono::steady_clock::now();
  robot->joints = joints;
  return robot;
}

WorldResetConfig canonicalConfig()
{
  const auto & profile = SO101Profile::canonical();
  return {profile.table_pose, profile.pedestal_pose, profile.task_object_pose,
          0.02, 0.001, 1e-5, 1e-4};
}

void seed(const std::shared_ptr<FakeGazeboResetAdapter> & gazebo,
          const std::shared_ptr<FakeMoveItSceneAdapter> & moveit, bool gazebo_attached,
          bool moveit_attached)
{
  gazebo->state.task_object_attached = gazebo_attached;
  gazebo->state.task_object_world_pose = {0.3, 0.2, 0.4, 0.1, 0.2, 0.3, 0.9};
  gazebo->state.pose_revision = 10;
  gazebo->state.attachment_revision = 10;
  moveit->state.task_object_attached = moveit_attached;
  moveit->state.task_object_in_world = !moveit_attached;
  if (moveit_attached) {
    moveit->state.attached_link = "gripper";
    moveit->state.touch_links = {"gripper", "jaw"};
  }
}

TEST(SO101WorldResetCoordinator, FourInitialStatesUseOnlyNecessaryDetachCalls)
{
  const std::vector<std::tuple<bool, bool, int, int>> cases{{false, false, 0, 0},
                                                            {true, false, 1, 0},
                                                            {false, true, 0, 1},
                                                            {true, true, 1, 1}};

  for (const auto & [gazebo_attached, moveit_attached, expected_gazebo_detach,
                     expected_moveit_detach] : cases) {
    auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
    auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
    seed(gazebo, moveit, gazebo_attached, moveit_attached);
    WorldResetCoordinator resetter(gazebo, moveit, robotAdapter(), canonicalConfig());

    const auto result = resetter.reset();

    EXPECT_EQ(ActionStatus::SUCCEEDED, result.status);
    EXPECT_EQ(expected_gazebo_detach, gazebo->detach_calls);
    EXPECT_EQ(expected_moveit_detach, moveit->detach_calls);
    EXPECT_EQ(1, gazebo->set_pose_calls);
    EXPECT_EQ(1, moveit->table_upsert_calls);
    EXPECT_EQ(1, moveit->pedestal_upsert_calls);
    EXPECT_EQ(1, moveit->task_object_upsert_calls);
    EXPECT_FALSE(gazebo->state.task_object_attached);
    EXPECT_FALSE(moveit->state.task_object_attached);
    EXPECT_TRUE(moveit->state.task_object_in_world);
  }
}

TEST(SO101WorldResetCoordinator, RepeatedResetDoesNotIssueHistoricalDetachCalls)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  seed(gazebo, moveit, true, true);
  WorldResetCoordinator resetter(gazebo, moveit, robotAdapter(), canonicalConfig());

  ASSERT_EQ(ActionStatus::SUCCEEDED, resetter.reset().status);
  ASSERT_EQ(ActionStatus::SUCCEEDED, resetter.reset().status);

  EXPECT_EQ(1, gazebo->detach_calls);
  EXPECT_EQ(1, moveit->detach_calls);
  EXPECT_EQ(2, gazebo->set_pose_calls);
  EXPECT_EQ(2, moveit->table_upsert_calls);
  EXPECT_EQ(2, moveit->pedestal_upsert_calls);
  EXPECT_EQ(2, moveit->task_object_upsert_calls);
}

TEST(SO101WorldResetCoordinator, StopsAfterGazeboDetachCommandFailure)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  seed(gazebo, moveit, true, true);
  gazebo->detach_result = failed("GAZEBO_DETACH_REJECTED");
  WorldResetCoordinator resetter(gazebo, moveit, robotAdapter(), canonicalConfig());

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::FAILED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("GAZEBO_DETACH_REJECTED", result.failure->code);
  EXPECT_EQ(0, moveit->detach_calls);
  EXPECT_EQ(0, gazebo->set_pose_calls);
  EXPECT_EQ(0, moveit->task_object_upsert_calls);
}

TEST(SO101WorldResetCoordinator, ApiSuccessWithoutDetachConvergenceTimesOut)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  seed(gazebo, moveit, true, false);
  gazebo->detach_converges = false;
  auto config = canonicalConfig();
  config.timeout_seconds = 0.004;
  WorldResetCoordinator resetter(gazebo, moveit, robotAdapter(), config);

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::TIMED_OUT, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("WORLD_RESET_GAZEBO_DETACH_TIMEOUT", result.failure->code);
  EXPECT_EQ(0, gazebo->set_pose_calls);
}

TEST(SO101WorldResetCoordinator, RejectsWrongFinalOrientationAfterSuccessfulCommands)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  seed(gazebo, moveit, false, false);
  gazebo->pose_converges = false;
  auto config = canonicalConfig();
  config.timeout_seconds = 0.004;
  WorldResetCoordinator resetter(gazebo, moveit, robotAdapter(), config);

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::TIMED_OUT, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("WORLD_RESET_CONVERGENCE_TIMEOUT", result.failure->code);
}

TEST(SO101WorldResetCoordinator, MissingInitialObservationFailsBeforeCommands)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  gazebo->observation_available = false;
  WorldResetCoordinator resetter(gazebo, moveit, robotAdapter(), canonicalConfig());

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::FAILED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("WORLD_RESET_INITIAL_OBSERVATION_FAILED", result.failure->code);
  EXPECT_EQ(0, gazebo->detach_calls);
  EXPECT_EQ(0, moveit->detach_calls);
}

TEST(SO101ProfileCanonical, RobotHomeMatchesTheSrdfNamedState)
{
  const auto & profile = SO101Profile::canonical();
  EXPECT_EQ((std::vector<double>{0.0, 0.0, 0.0, 0.0, 0.0}), profile.arm_home_positions);
  EXPECT_DOUBLE_EQ(-0.059303612618397, profile.q6_home);
  EXPECT_DOUBLE_EQ(1.7, profile.q6_full_open);
}

TEST(SO101WorldResetCoordinator, RequiresRobotHomeAdapterBeforeAnyCommand)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  seed(gazebo, moveit, true, true);
  WorldResetCoordinator resetter(gazebo, moveit, nullptr, canonicalConfig());

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::FAILED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("WORLD_RESET_ADAPTER_MISSING", result.failure->code);
  EXPECT_EQ(0, gazebo->detach_calls);
  EXPECT_EQ(0, moveit->detach_calls);
}

TEST(SO101WorldResetCoordinator, UsesReleaseArmHomeWorldSyncThenFinalGripperHomeOrder)
{
  auto events = std::make_shared<std::vector<std::string>>();
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  auto robot = robotAdapter();
  gazebo->events = events;
  moveit->events = events;
  robot->events = events;
  seed(gazebo, moveit, false, false);
  WorldResetCoordinator resetter(gazebo, moveit, robot, canonicalConfig());

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::SUCCEEDED, result.status);
  std::vector<std::string> commands;
  for (const auto & event : *events) {
    if (event != "observe_joints") commands.push_back(event);
  }
  EXPECT_EQ((std::vector<std::string>{
              "gripper:1.700000", "plan_arm_home", "execute_arm_home",
              "gazebo_pose", "moveit_table", "moveit_pedestal", "moveit_task_object",
              "gripper:-0.059304"}), commands);
  EXPECT_EQ((std::vector<double>{0.0, 0.0, 0.0, 0.0, 0.0}), robot->last_arm_goal);
}

TEST(SO101WorldResetCoordinator, MissingInitialJointEvidenceFailsBeforeCommands)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  auto robot = robotAdapter();
  robot->observation_available = false;
  seed(gazebo, moveit, true, true);
  WorldResetCoordinator resetter(gazebo, moveit, robot, canonicalConfig());

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::FAILED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("WORLD_RESET_INITIAL_JOINT_OBSERVATION_FAILED", result.failure->code);
  EXPECT_EQ(0, gazebo->detach_calls);
  EXPECT_EQ(0, moveit->detach_calls);
  EXPECT_EQ(0, robot->gripper_calls);
}

TEST(SO101WorldResetCoordinator, FailedArmPlanNeverExecutesOrResetsWorld)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  auto robot = robotAdapter();
  robot->plan_result = failed("ARM_HOME_PLAN_FAILED");
  seed(gazebo, moveit, false, false);
  WorldResetCoordinator resetter(gazebo, moveit, robot, canonicalConfig());

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::FAILED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("ARM_HOME_PLAN_FAILED", result.failure->code);
  EXPECT_EQ(0, robot->execute_calls);
  EXPECT_EQ(0, gazebo->set_pose_calls);
  EXPECT_EQ(0, moveit->task_object_upsert_calls);
}

TEST(SO101WorldResetCoordinator, FinalGripperMismatchReportsExpectedAndActualQ6)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  auto robot = robotAdapter();
  robot->home_gripper_converges = false;
  seed(gazebo, moveit, false, false);
  auto config = canonicalConfig();
  config.timeout_seconds = 0.004;
  WorldResetCoordinator resetter(gazebo, moveit, robot, config);

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::TIMED_OUT, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("WORLD_RESET_GRIPPER_HOME_TIMEOUT", result.failure->code);
  EXPECT_DOUBLE_EQ(-0.059303612618397, result.failure->metrics.at("expected_q6"));
  EXPECT_DOUBLE_EQ(1.7, result.failure->metrics.at("actual_q6"));
}

TEST(SO101WorldResetCoordinator, UsesIndependentArmAndNativePadEndpointTolerances)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  auto robot = robotAdapter();
  robot->arm_home_residual = 0.0010310361394658685;
  seed(gazebo, moveit, false, false);
  auto config = canonicalConfig();
  config.arm_joint_position_tolerance = 0.002;
  config.gripper_position_tolerance = 0.001;
  WorldResetCoordinator resetter(gazebo, moveit, robot, config);

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::SUCCEEDED, result.status);
}

TEST(SO101WorldResetCoordinator, NativePadSafeFloorRemainsStrictWhenArmHasEndpointAllowance)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  auto robot = robotAdapter();
  robot->arm_home_residual = 0.0010310361394658685;
  robot->home_gripper_offset = -0.000101;
  seed(gazebo, moveit, false, false);
  auto config = canonicalConfig();
  config.timeout_seconds = 0.004;
  config.arm_joint_position_tolerance = 0.002;
  config.gripper_position_tolerance = 0.001;
  WorldResetCoordinator resetter(gazebo, moveit, robot, config);

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::TIMED_OUT, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("WORLD_RESET_GRIPPER_HOME_TIMEOUT", result.failure->code);
  EXPECT_LT(result.failure->metrics.at("actual_q6"), config.q6_home_position);
}

}  // namespace
}  // namespace so101_gazebo_demo::pick_place
