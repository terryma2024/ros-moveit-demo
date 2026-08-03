#include <gtest/gtest.h>

#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "so101_gazebo_demo/pick_place/robot_home_reset_adapter.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{

ActionResult succeeded()
{
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

class MarkerPlan final : public PlanArtifact
{
public:
  explicit MarkerPlan(int identifier) : id(identifier) { trajectory_points = 3; }
  int id;
};

class FakeArmHomePlanningBoundary final : public IArmHomePlanningBoundary
{
public:
  PlanResult planHome(const std::vector<std::string> & joint_names,
                      const std::vector<double> & goal) override
  {
    ++plan_calls;
    last_joint_names = joint_names;
    last_goal = goal;
    return {plan_result, plan_result.status == ActionStatus::SUCCEEDED ? plan : nullptr};
  }

  ActionResult executeHome(const PlanArtifact & artifact) override
  {
    ++execute_calls;
    executed = &artifact;
    return execute_result;
  }

  ActionResult cancelAndWait() override { return succeeded(); }

  ActionResult plan_result{succeeded()};
  ActionResult execute_result{succeeded()};
  std::shared_ptr<MarkerPlan> plan{std::make_shared<MarkerPlan>(41)};
  int plan_calls{0};
  int execute_calls{0};
  std::vector<std::string> last_joint_names;
  std::vector<double> last_goal;
  const PlanArtifact * executed{nullptr};
};

class FakeJointBoundary final : public IJointPlanningBoundary
{
public:
  std::optional<CurrentJointStateEvidence> currentState() override { return current; }
  std::optional<MotionPlanningSceneFacts> sceneFacts() override { return std::nullopt; }
  JointSegmentPlanResult planSegment(
    const std::vector<std::string> &, const std::vector<double> &,
    const std::vector<double> &, const std::set<std::string> &,
    const std::optional<TemporalContactPolicy> &, double, double, double) override
  {
    return {{ActionStatus::NOT_SUPPORTED, std::nullopt}, std::nullopt};
  }

  std::optional<CurrentJointStateEvidence> current;
};

class FakeGripperCommand final : public ISO101GripperCommand
{
public:
  ActionResult command(double q6) override
  {
    targets.push_back(q6);
    return command_result;
  }
  ActionResult cancelAndWait() override { return succeeded(); }

  ActionResult command_result{succeeded()};
  std::vector<double> targets;
};

TEST(MoveItRobotHomeResetAdapter, PlansCanonicalHomeAndExecutesTheExactArtifact)
{
  const auto & profile = SO101Profile::canonical();
  auto arm = std::make_shared<FakeArmHomePlanningBoundary>();
  auto joints = std::make_shared<FakeJointBoundary>();
  auto gripper = std::make_shared<FakeGripperCommand>();
  MoveItRobotHomeResetAdapter adapter(arm, joints, gripper, profile);

  const auto planned = adapter.planArmHome(profile.arm_home_positions);
  ASSERT_EQ(ActionStatus::SUCCEEDED, planned.action.status);
  ASSERT_TRUE(planned.artifact);
  EXPECT_EQ(profile.arm_joints, arm->last_joint_names);
  EXPECT_EQ((std::vector<double>{0.0, 0.0, 0.0, 0.0, 0.0}), arm->last_goal);

  EXPECT_EQ(ActionStatus::SUCCEEDED,
            adapter.executeArmHome(*planned.artifact).status);
  EXPECT_EQ(planned.artifact.get(), arm->executed);
  EXPECT_EQ(1, arm->plan_calls);
  EXPECT_EQ(1, arm->execute_calls);
}

TEST(MoveItRobotHomeResetAdapter, RejectsNonCanonicalHomeWithoutPlanning)
{
  const auto & profile = SO101Profile::canonical();
  auto arm = std::make_shared<FakeArmHomePlanningBoundary>();
  MoveItRobotHomeResetAdapter adapter(
    arm, std::make_shared<FakeJointBoundary>(),
    std::make_shared<FakeGripperCommand>(), profile);

  const auto result = adapter.planArmHome({0.0, 0.0, 0.0, 0.0, 0.1});

  EXPECT_EQ(ActionStatus::FAILED, result.action.status);
  ASSERT_TRUE(result.action.failure);
  EXPECT_EQ("ARM_HOME_TARGET_INVALID", result.action.failure->code);
  EXPECT_EQ(0, arm->plan_calls);
}

TEST(MoveItRobotHomeResetAdapter, ExposesIndependentJointsAndCommandsExactQ6)
{
  const auto & profile = SO101Profile::canonical();
  auto arm = std::make_shared<FakeArmHomePlanningBoundary>();
  auto joints = std::make_shared<FakeJointBoundary>();
  auto gripper = std::make_shared<FakeGripperCommand>();
  CurrentJointStateEvidence evidence;
  evidence.positions = {1.0, 2.0, 3.0, 4.0, 5.0};
  joints->current = evidence;
  MoveItRobotHomeResetAdapter adapter(arm, joints, gripper, profile);

  const auto observed = adapter.observeJoints();
  ASSERT_TRUE(observed);
  EXPECT_EQ(evidence.positions, observed->positions);
  EXPECT_EQ(ActionStatus::SUCCEEDED, adapter.commandGripper(profile.q6_home).status);
  ASSERT_EQ(1U, gripper->targets.size());
  EXPECT_DOUBLE_EQ(profile.q6_home, gripper->targets.front());
}

}  // namespace
}  // namespace so101_gazebo_demo::pick_place
