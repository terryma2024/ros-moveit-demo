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

TEST(SO101MotionPlanValidator, CarryingStateRequiresFiniteAttachedTaskObjectPoseAtEverySample)
{
  auto plan = validLadder();
  for (auto & sample : plan.samples) sample.attached_task_object_pose_world = pose(0.1, 0.2, 0.3);
  const spp::SO101MotionPlanValidator validator(descendConfig(), true);
  const auto result = validator.validate(spp::State::LIFT, {}, plan);
  EXPECT_TRUE(result.ok);
}

TEST(SO101MotionPlanValidator, CarryingStateRejectsMissingAttachedTaskObjectPose)
{
  auto plan = validLadder();
  for (auto & sample : plan.samples) sample.attached_task_object_pose_world = pose(0.1, 0.2, 0.3);
  plan.samples[1].attached_task_object_pose_world.reset();
  const spp::SO101MotionPlanValidator validator(descendConfig(), true);
  const auto result = validator.validate(spp::State::LIFT, {}, plan);
  ASSERT_FALSE(result.ok);
  ASSERT_FALSE(result.failures.empty());
  EXPECT_EQ(result.failures.front().code, "ATTACHED_TASK_OBJECT_POSE_EVIDENCE_MISSING");
}

TEST(SO101MotionPlanValidator, CarryingStateRejectsNonfiniteAttachedTaskObjectPose)
{
  auto plan = validLadder();
  for (auto & sample : plan.samples) sample.attached_task_object_pose_world = pose(0.1, 0.2, 0.3);
  plan.samples[2].attached_task_object_pose_world->qz =
    std::numeric_limits<double>::quiet_NaN();
  const spp::SO101MotionPlanValidator validator(descendConfig(), true);
  const auto result = validator.validate(spp::State::MOVE_ABOVE_PLACE, {}, plan);
  ASSERT_FALSE(result.ok);
  ASSERT_FALSE(result.failures.empty());
  EXPECT_EQ(result.failures.front().code, "ATTACHED_TASK_OBJECT_POSE_EVIDENCE_NONFINITE");
}

TEST(SO101MotionPlanValidator, DetachedStateDoesNotRequireAttachedTaskObjectPose)
{
  const spp::SO101MotionPlanValidator validator(descendConfig(), true);
  EXPECT_TRUE(validator.validate(spp::State::DESCEND, {}, validLadder()).ok);
}

TEST(SO101MotionConfiguration, RejectsNonfiniteNegativeAndIllegalZeroValuesAtEntry)
{
  const double nan = std::numeric_limits<double>::quiet_NaN();
  const double inf = std::numeric_limits<double>::infinity();
  for (const int mutation : {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
                             12, 13, 14, 15, 16, 17, 18}) {
    auto config = descendConfig();
    switch (mutation) {
      case 0: config.endpoint_position.x = nan; break;
      case 1: config.local_approach_axis = {0, 0, 0}; break;
      case 2: config.target_approach_axis.y = inf; break;
      case 3: config.path_direction = {0, 0, 0}; break;
      case 4: config.position_tolerance = 0.0; break;
      case 5: config.position_tolerance = -0.1; break;
      case 6: config.position_tolerance = nan; break;
      case 7: config.axis_tolerance_rad = 0.0; break;
      case 8: config.axis_tolerance_rad = M_PI + 0.01; break;
      case 9: config.max_lateral_deviation = -0.1; break;
      case 10: config.max_lateral_deviation = 0.0; break;
      case 11: config.max_joint_jump = inf; break;
      case 12: config.max_joint_jump = 0.0; break;
      case 13: config.joint_endpoint_tolerance = -0.001; break;
      case 14: config.joint_endpoint_tolerance = 0.0; break;
      case 15: config.min_duration_seconds = nan; break;
      case 16: config.min_duration_seconds = 0.0; break;
      case 17: config.monotonic_tolerance = -1e-5; break;
      case 18: config.monotonic_tolerance = inf; break;
    }
    const auto result = spp::validateWaypointLadder(validLadder(), config);
    ASSERT_FALSE(result.ok) << mutation;
    ASSERT_FALSE(result.failures.empty()) << mutation;
    EXPECT_EQ(result.failures.front().category, spp::FailureCategory::CONFIGURATION) << mutation;
    EXPECT_EQ(result.failures.front().code, "MOTION_VALIDATION_CONFIG_INVALID") << mutation;
  }
}

TEST(SO101MotionConfiguration, AllowsZeroOnlyForNonnegativeMonotonicTolerance)
{
  auto config = descendConfig();
  config.monotonic_tolerance = 0.0;
  EXPECT_TRUE(spp::validateWaypointLadder(validLadder(), config).ok);
}

TEST(SO101MotionConfiguration, RejectsMalformedTemporalPolicyAtEntry)
{
  for (const double clearance : {0.0, -0.001,
                                 std::numeric_limits<double>::quiet_NaN(),
                                 std::numeric_limits<double>::infinity()}) {
    auto config = descendConfig();
    config.temporal_contact_policy = spp::TemporalContactPolicy{
      {"plastic_cup:gripper"}, spp::TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE,
      clearance};
    auto plan = validLadder();
    plan.temporal_contact_policy = config.temporal_contact_policy;
    const auto result = spp::validateWaypointLadder(plan, config);
    ASSERT_FALSE(result.ok);
    ASSERT_FALSE(result.failures.empty());
    EXPECT_EQ(result.failures.front().category, spp::FailureCategory::CONFIGURATION);
    EXPECT_EQ(result.failures.front().code, "MOTION_VALIDATION_CONFIG_INVALID");
  }

  auto config = descendConfig();
  config.temporal_contact_policy = spp::TemporalContactPolicy{
    {"plastic_cup:table"}, spp::TemporalContactLocation::FIRST_ONLY, 0.001};
  auto plan = validLadder();
  plan.temporal_contact_policy = config.temporal_contact_policy;
  EXPECT_FALSE(spp::validateWaypointLadder(plan, config).ok);
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

TEST(SO101MotionLadder, BoundsMeasuredEndpointSettlingWithoutHidingRealRollback)
{
  auto measured = validLadder();
  measured.trajectory_points = 4;
  measured.samples[1].tcp_pose.z = 0.2502048768443;
  auto settle = measured.samples[1];
  settle.tcp_pose.z = 0.2502275306637;  // 22.6538194 um backward at sample 37.
  settle.time_from_start_seconds = 1.1;
  measured.samples.insert(measured.samples.begin() + 2, settle);

  auto config = descendConfig();
  config.monotonic_tolerance = 0.00003;
  EXPECT_TRUE(spp::validateWaypointLadder(measured, config).ok);

  auto real_rollback = measured;
  real_rollback.samples[2].tcp_pose.z =
    real_rollback.samples[1].tcp_pose.z + 0.000031;
  const auto rejected = spp::validateWaypointLadder(real_rollback, config);
  ASSERT_FALSE(rejected.ok);
  ASSERT_FALSE(rejected.failures.empty());
  EXPECT_EQ("TCP_PATH_NON_MONOTONIC", rejected.failures.front().code);
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

TEST(SO101MotionTouchException, AcceptsOnlyExactStateScopedDescendWhitelist)
{
  auto plan = validLadder();
  auto config = descendConfig();
  config.allowed_touch_pairs = {"plastic_cup:gripper", "plastic_cup:jaw"};
  plan.allowed_touch_pairs = config.allowed_touch_pairs;
  plan.raw_contact_pairs = {"plastic_cup:gripper", "plastic_cup:jaw"};
  plan.samples[1].raw_contact_pairs = plan.raw_contact_pairs;
  EXPECT_TRUE(spp::validateWaypointLadder(plan, config).ok);

  plan.raw_contact_pairs.insert("plastic_cup:lower_arm");
  plan.samples[1].raw_contact_pairs.insert("plastic_cup:lower_arm");
  auto result = spp::validateWaypointLadder(plan, config);
  EXPECT_FALSE(result.ok);
  EXPECT_EQ(result.failures.front().code, "RAW_CONTACT_OUTSIDE_TOUCH_WHITELIST");
}

TEST(SO101MotionTouchException, RejectsWorldTouchExceptionForNonDescendState)
{
  auto plan = validLadder();
  plan.allowed_touch_pairs = {"plastic_cup:gripper"};
  plan.raw_contact_pairs = {"plastic_cup:gripper"};
  plan.samples[1].raw_contact_pairs = plan.raw_contact_pairs;
  const auto result = spp::validateJointGoalPlan(plan, descendConfig());
  EXPECT_FALSE(result.ok);
  EXPECT_EQ(result.failures.front().code, "TOUCH_WHITELIST_CONTEXT_MISMATCH");
}

TEST(SO101MotionTouchException, RejectsTableOrOtherRobotContact)
{
  auto plan = validLadder();
  auto config = descendConfig();
  config.allowed_touch_pairs = {"plastic_cup:gripper", "plastic_cup:jaw"};
  plan.allowed_touch_pairs = config.allowed_touch_pairs;
  for (const std::string pair : {"table:jaw", "plastic_cup:lower_arm"}) {
    plan.raw_contact_pairs = {pair};
    plan.samples[1].raw_contact_pairs = {pair};
    EXPECT_FALSE(spp::validateWaypointLadder(plan, config).ok) << pair;
  }
}

TEST(SO101MotionTemporalContact, AllowsFirstOnlyTaskObjectTableAtSampleZero)
{
  auto plan = validLadder();
  auto config = descendConfig();
  config.path_direction = {0, 0, -1};
  config.temporal_contact_policy =
    spp::TemporalContactPolicy{{"plastic_cup:table"}, spp::TemporalContactLocation::FIRST_ONLY};
  plan.temporal_contact_policy = config.temporal_contact_policy;
  plan.samples[0].raw_contact_pairs = {"plastic_cup:table"};
  plan.raw_contact_pairs = {"plastic_cup:table"};
  EXPECT_TRUE(spp::validateWaypointLadder(plan, config).ok);
}

TEST(SO101MotionTemporalContact, RejectsFirstOnlyPersistenceOrRecurrenceAfterSampleZero)
{
  for (const auto index : {1U, 2U}) {
    auto plan = validLadder();
    auto config = descendConfig();
    config.temporal_contact_policy =
      spp::TemporalContactPolicy{{"plastic_cup:table"}, spp::TemporalContactLocation::FIRST_ONLY};
    plan.temporal_contact_policy = config.temporal_contact_policy;
    plan.samples[0].raw_contact_pairs = {"plastic_cup:table"};
    plan.samples[index].raw_contact_pairs = {"plastic_cup:table"};
    const auto result = spp::validateWaypointLadder(plan, config);
    ASSERT_FALSE(result.ok);
    EXPECT_EQ(result.failures.front().code, "TEMPORAL_CONTACT_AT_WRONG_SAMPLE");
  }
}

TEST(SO101MotionTemporalContact, AllowsLastOnlyTaskObjectTableAtFinalSample)
{
  auto plan = validLadder();
  auto config = descendConfig();
  config.temporal_contact_policy =
    spp::TemporalContactPolicy{{"plastic_cup:table"}, spp::TemporalContactLocation::LAST_ONLY};
  plan.temporal_contact_policy = config.temporal_contact_policy;
  plan.samples.back().raw_contact_pairs = {"plastic_cup:table"};
  plan.raw_contact_pairs = {"plastic_cup:table"};
  EXPECT_TRUE(spp::validateWaypointLadder(plan, config).ok);
}

TEST(SO101MotionTemporalContact, RejectsLastOnlyContactBeforeFinalSample)
{
  for (const auto index : {0U, 1U}) {
    auto plan = validLadder();
    auto config = descendConfig();
    config.temporal_contact_policy =
      spp::TemporalContactPolicy{{"plastic_cup:table"}, spp::TemporalContactLocation::LAST_ONLY};
    plan.temporal_contact_policy = config.temporal_contact_policy;
    plan.samples[index].raw_contact_pairs = {"plastic_cup:table"};
    const auto result = spp::validateWaypointLadder(plan, config);
    ASSERT_FALSE(result.ok);
    EXPECT_EQ(result.failures.front().code, "TEMPORAL_CONTACT_AT_WRONG_SAMPLE");
  }
}

TEST(SO101MotionTemporalContact, RejectsLastOnlyUnexpectedPairAtFinalSample)
{
  auto plan = validLadder();
  auto config = descendConfig();
  config.temporal_contact_policy =
    spp::TemporalContactPolicy{{"plastic_cup:table"}, spp::TemporalContactLocation::LAST_ONLY};
  plan.temporal_contact_policy = config.temporal_contact_policy;
  plan.samples.back().raw_contact_pairs = {"plastic_cup:jaw"};
  plan.raw_contact_pairs = {"plastic_cup:jaw"};
  const auto result = spp::validateWaypointLadder(plan, config);
  ASSERT_FALSE(result.ok);
  EXPECT_EQ(result.failures.front().code, "RAW_CONTACT_OUTSIDE_TOUCH_WHITELIST");
}

TEST(SO101MotionTemporalContact, AllowsExactGripperPairOnlyAtFirstSample)
{
  auto plan = validLadder();
  auto config = descendConfig();
  config.temporal_contact_policy = spp::TemporalContactPolicy{
    {"plastic_cup:gripper", "plastic_cup:jaw"}, spp::TemporalContactLocation::FIRST_ONLY};
  plan.temporal_contact_policy = config.temporal_contact_policy;
  plan.samples.front().raw_contact_pairs = {"plastic_cup:gripper"};
  plan.raw_contact_pairs = {"plastic_cup:gripper"};
  EXPECT_TRUE(spp::validateWaypointLadder(plan, config).ok);

  plan.samples[1].raw_contact_pairs = {"plastic_cup:jaw"};
  const auto result = spp::validateWaypointLadder(plan, config);
  ASSERT_FALSE(result.ok);
  EXPECT_EQ(result.failures.front().code, "TEMPORAL_CONTACT_AT_WRONG_SAMPLE");
}

TEST(SO101MotionTemporalContact, AllowsContiguousPrefixWithinAxialClearance)
{
  auto plan = validLadder();
  auto config = descendConfig();
  plan.samples[0].tcp_pose.z = 0.300;
  plan.samples[1].tcp_pose.z = 0.280;
  plan.samples[2].tcp_pose.z = 0.250;
  config.endpoint_position.z = 0.250;
  const spp::TemporalContactPolicy policy{
    {"plastic_cup:gripper", "plastic_cup:jaw"},
    spp::TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE, 0.043};
  config.temporal_contact_policy = policy;
  plan.temporal_contact_policy = policy;
  plan.samples[0].raw_contact_pairs = {"plastic_cup:gripper"};
  plan.samples[1].raw_contact_pairs = {"plastic_cup:gripper"};
  plan.raw_contact_pairs = {"plastic_cup:gripper"};
  EXPECT_TRUE(spp::validateWaypointLadder(plan, config).ok);
}

TEST(SO101MotionTemporalContact, RejectsPrefixContactBeyondAxialClearance)
{
  auto plan = validLadder();
  auto config = descendConfig();
  plan.samples[0].tcp_pose.z = 0.300;
  plan.samples[1].tcp_pose.z = 0.280;
  plan.samples[2].tcp_pose.z = 0.250;
  config.endpoint_position.z = 0.250;
  const spp::TemporalContactPolicy policy{
    {"plastic_cup:gripper", "plastic_cup:jaw"},
    spp::TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE, 0.043};
  config.temporal_contact_policy = policy;
  plan.temporal_contact_policy = policy;
  for (auto & sample : plan.samples) sample.raw_contact_pairs = {"plastic_cup:gripper"};
  plan.raw_contact_pairs = {"plastic_cup:gripper"};
  const auto result = spp::validateWaypointLadder(plan, config);
  ASSERT_FALSE(result.ok);
  EXPECT_EQ(result.failures.front().code, "TEMPORAL_CONTACT_BEYOND_AXIAL_CLEARANCE");
}

TEST(SO101MotionTemporalContact, RetreatFailsClosedWithStableContactClearanceCode)
{
  auto plan = validLadder();
  auto config = descendConfig();
  plan.samples[0].tcp_pose.z = 0.300;
  plan.samples[1].tcp_pose.z = 0.280;
  plan.samples[2].tcp_pose.z = 0.250;
  config.endpoint_position.z = 0.250;
  const spp::TemporalContactPolicy policy{
    {"plastic_cup:gripper", "plastic_cup:jaw"},
    spp::TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE, 0.043};
  config.temporal_contact_policy = policy;
  plan.temporal_contact_policy = policy;
  for (auto & sample : plan.samples) sample.raw_contact_pairs = {"plastic_cup:gripper"};
  plan.raw_contact_pairs = {"plastic_cup:gripper"};
  spp::SO101MotionPlanValidator validator(config, true);

  const auto result = validator.validate(spp::State::RETREAT, {}, plan);

  ASSERT_FALSE(result.ok);
  ASSERT_FALSE(result.failures.empty());
  EXPECT_EQ(result.failures.front().code, "RETREAT_CONTACT_NOT_CLEARED");
}

TEST(SO101MotionTemporalContact, AcceptsIntermittentContactInsidePrefixAndProvesFinalClearance)
{
  auto plan = validLadder();
  auto config = descendConfig();
  plan.samples[0].tcp_pose.z = 0.300;
  plan.samples[1].tcp_pose.z = 0.285;
  plan.samples[2].tcp_pose.z = 0.270;
  plan.samples.insert(plan.samples.end(), plan.samples.back());
  plan.samples[3].tcp_pose.z = 0.250;
  plan.samples[3].time_from_start_seconds = 3.0;
  plan.trajectory_points = plan.samples.size();
  config.endpoint_position.z = 0.250;
  const spp::TemporalContactPolicy policy{
    {"plastic_cup:gripper", "plastic_cup:jaw"},
    spp::TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE, 0.043};
  config.temporal_contact_policy = policy;
  plan.temporal_contact_policy = policy;
  plan.samples[0].raw_contact_pairs = {"plastic_cup:gripper"};
  plan.samples[2].raw_contact_pairs = {"plastic_cup:gripper"};
  plan.raw_contact_pairs = {"plastic_cup:gripper"};
  const auto result = spp::validateWaypointLadder(plan, config);
  EXPECT_TRUE(result.ok) << (result.failures.empty() ? "" : result.failures.front().code);
}

TEST(SO101MotionTemporalContact, RejectsPrefixContactWithNegativeAxialProgress)
{
  auto plan = validLadder();
  auto config = descendConfig();
  plan.samples[0].tcp_pose.z = 0.300;
  plan.samples[1].tcp_pose.z = 0.310;
  plan.samples[2].tcp_pose.z = 0.250;
  config.endpoint_position.z = 0.250;
  const spp::TemporalContactPolicy policy{
    {"plastic_cup:gripper", "plastic_cup:jaw"},
    spp::TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE, 0.043};
  config.temporal_contact_policy = policy;
  plan.temporal_contact_policy = policy;
  plan.samples[0].raw_contact_pairs = {"plastic_cup:gripper"};
  plan.samples[1].raw_contact_pairs = {"plastic_cup:gripper"};
  plan.raw_contact_pairs = {"plastic_cup:gripper"};
  const auto result = spp::validateWaypointLadder(plan, config);
  ASSERT_FALSE(result.ok);
  EXPECT_EQ(result.failures.front().code, "TEMPORAL_CONTACT_NEGATIVE_AXIAL_PROGRESS");
}

TEST(SO101MotionTemporalContact, RejectsMismatchedContextOrAnyOtherPair)
{
  auto plan = validLadder();
  plan.temporal_contact_policy =
    spp::TemporalContactPolicy{{"plastic_cup:table"}, spp::TemporalContactLocation::FIRST_ONLY};
  plan.samples[0].raw_contact_pairs = {"plastic_cup:table"};
  auto result = spp::validateWaypointLadder(plan, descendConfig());
  ASSERT_FALSE(result.ok);
  EXPECT_EQ(result.failures.front().code, "TEMPORAL_CONTACT_CONTEXT_MISMATCH");

  auto config = descendConfig();
  config.temporal_contact_policy = plan.temporal_contact_policy;
  plan.samples[0].raw_contact_pairs = {"plastic_cup:lower_arm"};
  result = spp::validateWaypointLadder(plan, config);
  ASSERT_FALSE(result.ok);
  EXPECT_EQ(result.failures.front().code, "RAW_CONTACT_OUTSIDE_TOUCH_WHITELIST");
}
