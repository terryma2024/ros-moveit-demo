#include <cmath>
#include <limits>
#include <memory>

#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/so101_motion_validation.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

spp::Pose3d pose(double x, double y, double z, double qx = 0.0, double qy = 0.0,
                 double qz = 0.0, double qw = 1.0)
{
  return {x, y, z, qx, qy, qz, qw};
}

spp::MotionPlanArtifact validLadder()
{
  spp::MotionPlanArtifact plan;
  plan.trajectory_points = 3;
  plan.joint_names = {"1", "2", "3", "4", "5"};
  plan.start_joint_positions = {0.0, 0.0, 0.0, 0.0, 0.0};
  plan.goal_joint_positions = {0.03, 0.04, 0.05, 0.02, 0.01};
  plan.collision_aware = true;
  plan.time_parameterized = true;
  plan.samples = {
    {{0.020, -0.280, 0.300, 0.0, 0.0, 0.0, 1.0}, {0, 0, 0, 0, 0}, 0.0, true},
    {{0.021, -0.280, 0.250, 0.0, 0.0, 0.0, 1.0}, {0.01, 0.02, 0.03, 0.01, 0.0}, 1.0, true},
    {{0.020, -0.280, 0.210, 0.0, 0.0, 0.0, 1.0}, {0.03, 0.04, 0.05, 0.02, 0.01}, 2.0, true},
  };
  return plan;
}

spp::MotionValidationConfig descendConfig()
{
  spp::MotionValidationConfig config;
  config.expected_joint_names = {"1", "2", "3", "4", "5"};
  config.endpoint_position = {0.020, -0.280, 0.210};
  config.local_approach_axis = {0.0, 0.0, -1.0};
  config.target_approach_axis = {0.0, 0.0, -1.0};
  config.path_direction = {0.0, 0.0, -1.0};
  config.position_tolerance = 0.005;
  config.axis_tolerance_rad = 0.05;
  config.max_lateral_deviation = 0.005;
  config.max_joint_jump = 0.1;
  config.min_duration_seconds = 0.1;
  return config;
}

}  // namespace

TEST(SO101MotionAxis, AcceptsDifferentAxialTwistWithIdenticalApproachAxis)
{
  const spp::Vec3 local{0.0, 0.0, -1.0};
  const spp::Vec3 target{0.0, 0.0, -1.0};
  const auto identity = pose(0, 0, 0);
  const double half = 0.5 * M_PI_2;
  const auto ninety_degree_twist = pose(0, 0, 0, 0.0, 0.0, std::sin(half), std::cos(half));

  EXPECT_NEAR(spp::approachAxisError(identity, local, target), 0.0, 1e-12);
  EXPECT_NEAR(spp::approachAxisError(ninety_degree_twist, local, target), 0.0, 1e-12);
}

TEST(SO101MotionAxis, RejectsExcessiveToolAxisTilt)
{
  const double half = 0.5 * (20.0 * M_PI / 180.0);
  const auto tilted = pose(0, 0, 0, std::sin(half), 0.0, 0.0, std::cos(half));
  EXPECT_GT(spp::approachAxisError(tilted, {0, 0, -1}, {0, 0, -1}), 0.3);
}

TEST(SO101MotionAxis, FailsClosedForZeroOrNonfiniteInputs)
{
  auto invalid_pose = pose(0, 0, 0);
  invalid_pose.qw = std::numeric_limits<double>::quiet_NaN();
  EXPECT_TRUE(std::isinf(spp::approachAxisError(pose(0, 0, 0), {0, 0, 0}, {0, 0, -1})));
  EXPECT_TRUE(std::isinf(spp::approachAxisError(invalid_pose, {0, 0, -1}, {0, 0, -1})));
}

TEST(SO101MotionLadder, AcceptsCompleteNearVerticalCollisionAwarePath)
{
  const auto result = spp::validateWaypointLadder(validLadder(), descendConfig());
  EXPECT_TRUE(result.ok);
  EXPECT_TRUE(result.failures.empty());
  EXPECT_NEAR(result.metrics.at("duration_seconds"), 2.0, 1e-12);
  EXPECT_NEAR(result.metrics.at("max_joint_jump"), 0.03, 1e-12);
  EXPECT_NEAR(result.metrics.at("max_lateral_deviation"), 0.001, 1e-12);
  EXPECT_NEAR(result.metrics.at("axis_error"), 0.0, 1e-12);
}

TEST(SO101MotionLadder, RejectsLateralDrift)
{
  auto plan = validLadder();
  plan.samples[1].tcp_pose.x = 0.035;
  const auto result = spp::validateWaypointLadder(plan, descendConfig());
  EXPECT_FALSE(result.ok);
  EXPECT_EQ(result.failures.front().code, "TCP_PATH_LATERAL_DEVIATION");
}

TEST(SO101MotionLadder, RejectsNonMonotonicAxialProgress)
{
  auto plan = validLadder();
  plan.samples[1].tcp_pose.z = 0.310;
  const auto result = spp::validateWaypointLadder(plan, descendConfig());
  EXPECT_FALSE(result.ok);
  EXPECT_EQ(result.failures.front().code, "TCP_PATH_NON_MONOTONIC");
}

TEST(SO101MotionLadder, RejectsTiltAtAnySample)
{
  auto plan = validLadder();
  const double half = 0.5 * (10.0 * M_PI / 180.0);
  plan.samples[1].tcp_pose.qx = std::sin(half);
  plan.samples[1].tcp_pose.qw = std::cos(half);
  const auto result = spp::validateWaypointLadder(plan, descendConfig());
  EXPECT_FALSE(result.ok);
  EXPECT_EQ(result.failures.front().code, "TCP_AXIS_OUTSIDE_TOLERANCE");
}

TEST(SO101MotionLadder, RejectsMissingSafetyEvidence)
{
  auto config = descendConfig();
  for (const auto mutate : {0, 1, 2, 3}) {
    auto plan = validLadder();
    if (mutate == 0) plan.collision_aware = false;
    if (mutate == 1) plan.time_parameterized = false;
    if (mutate == 2) plan.samples[1].collision_free = false;
    if (mutate == 3) plan.samples[2].time_from_start_seconds = plan.samples[1].time_from_start_seconds;
    EXPECT_FALSE(spp::validateWaypointLadder(plan, config).ok) << mutate;
  }
}

TEST(SO101MotionLadder, RejectsJointJump)
{
  auto plan = validLadder();
  plan.samples[1].joint_positions[2] = 0.5;
  const auto result = spp::validateWaypointLadder(plan, descendConfig());
  EXPECT_FALSE(result.ok);
  EXPECT_EQ(result.failures.front().code, "JOINT_WAYPOINT_JUMP_TOO_LARGE");
}

TEST(SO101MotionGoal, RequiresEndpointAxisStartCollisionAndTimingEvidence)
{
  auto plan = validLadder();
  plan.samples = {plan.samples.front(), plan.samples.back()};
  plan.trajectory_points = 2;
  auto config = descendConfig();

  EXPECT_TRUE(spp::validateJointGoalPlan(plan, config).ok);
  plan.start_joint_positions.clear();
  EXPECT_FALSE(spp::validateJointGoalPlan(plan, config).ok);
}
