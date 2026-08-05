#include <gtest/gtest.h>

#include <fstream>
#include <cmath>
#include <memory>
#include <sstream>

#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/so101_profile.hpp"
#include "so101_gazebo_demo/workspace/workspace_state_evaluator.hpp"

namespace ws = so101_gazebo_demo::workspace;
namespace spp = so101_gazebo_demo::pick_place;

namespace
{
std::string readFile(const std::string & path)
{
  std::ifstream stream(path);
  std::ostringstream output;
  output << stream.rdbuf();
  return output.str();
}

std::unique_ptr<ws::WorkspaceStateEvaluator> makeEvaluator()
{
  if (!rclcpp::ok())
    rclcpp::init(0, nullptr);
  rclcpp::NodeOptions options;
  options.parameter_overrides(
    {rclcpp::Parameter("robot_description", readFile(SO101_TEST_URDF)),
     rclcpp::Parameter("robot_description_semantic", readFile(SO101_TEST_SRDF))});
  auto node = std::make_shared<rclcpp::Node>("workspace_evaluator_test", options);
  auto result = ws::WorkspaceStateEvaluator::create(node, spp::SO101Profile::canonical());
  EXPECT_FALSE(result.failure.has_value());
  return std::move(result.evaluator);
}
}  // namespace

TEST(WorkspaceStateEvaluator, UsesFiveArmJointsAndFixedPreopen)
{
  auto evaluator = makeEvaluator();
  ASSERT_TRUE(evaluator);
  const ws::GeneratedJointSample generated{1,
                                           ws::SampleSource::HALTON_GLOBAL,
                                           {0.0, 0.0, 0.0, 0.0, 0.0}};
  const auto sample = evaluator->evaluate(7, generated);
  EXPECT_EQ(sample.arm_joints.size(), 5U);
  EXPECT_DOUBLE_EQ(sample.gripper_q6, spp::SO101Profile::canonical().q6_preopen);
  EXPECT_TRUE(std::isfinite(sample.tcp_pose.x));
  EXPECT_TRUE(std::isfinite(sample.tcp_pose.qw));
  EXPECT_EQ(sample.collision_free,
            sample.bounds_valid && !sample.self_collision && !sample.scene_collision);
}

TEST(WorkspaceStateEvaluator, SceneContainsTableAndPedestalButNotCup)
{
  auto evaluator = makeEvaluator();
  ASSERT_TRUE(evaluator);
  EXPECT_EQ(evaluator->worldObjectIds(), (std::vector<std::string>{"base_pedestal", "table"}));
}

TEST(WorkspaceStateEvaluator, InvalidModelFailsClosed)
{
  rclcpp::NodeOptions options;
  options.parameter_overrides({rclcpp::Parameter("robot_description", "<robot name='bad'/>")});
  auto node = std::make_shared<rclcpp::Node>("workspace_bad_model_test", options);
  auto result = ws::WorkspaceStateEvaluator::create(node, spp::SO101Profile::canonical());
  EXPECT_FALSE(result.evaluator);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "model_load_failed");
}
