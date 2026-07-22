#include <gtest/gtest.h>

#include <limits>
#include <optional>

#include "panda_gazebo_demo/pick_place/headless_fault_fixture.hpp"
#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"

namespace pick_place = panda_gazebo_demo::pick_place;

namespace
{

pick_place::ObservationResult makeObservation()
{
  pick_place::WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.tcp_pose_world = {0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0};
  return {snapshot, std::nullopt};
}

void expectPose(
  const pick_place::FixedPickPlaceTargetPolicy & policy,
  pick_place::State current_state, pick_place::State next_state,
  double x, double y, double z)
{
  const auto result = policy.targetPose(current_state, next_state, makeObservation());
  ASSERT_TRUE(result.target_pose);
  EXPECT_DOUBLE_EQ(x, result.target_pose->x);
  EXPECT_DOUBLE_EQ(y, result.target_pose->y);
  EXPECT_DOUBLE_EQ(z, result.target_pose->z);
  EXPECT_DOUBLE_EQ(1.0, result.target_pose->qx);
  EXPECT_DOUBLE_EQ(0.0, result.target_pose->qy);
  EXPECT_DOUBLE_EQ(0.0, result.target_pose->qz);
  EXPECT_DOUBLE_EQ(0.0, result.target_pose->qw);
}

}  // namespace

TEST(FixedTargets, SuppliesAllForwardMotionTargets)
{
  const pick_place::FixedPickPlaceTargetPolicy policy;

  expectPose(
    policy, pick_place::State::DESCEND, pick_place::State::CLOSE_GRIPPER,
    0.30, 0.00, 0.870);
  expectPose(
    policy, pick_place::State::LIFT, pick_place::State::MOVE_ABOVE_PLACE,
    0.30, 0.00, 0.987);
  expectPose(
    policy, pick_place::State::MOVE_ABOVE_PLACE, pick_place::State::DESCEND_TO_PLACE,
    0.30, 0.20, 0.987);
  expectPose(
    policy, pick_place::State::DESCEND_TO_PLACE, pick_place::State::OPEN_GRIPPER,
    0.30, 0.20, 0.870);
  expectPose(
    policy, pick_place::State::RETREAT, pick_place::State::DONE,
    0.30, 0.20, 0.987);
}

TEST(FixedTargets, UsesObservedXYForRecoverySafeHeight)
{
  const pick_place::FixedPickPlaceTargetPolicy policy;
  auto observation = makeObservation();
  observation.snapshot->tcp_pose_world = {0.12, -0.08, 0.95, 1.0, 0.0, 0.0, 0.0};

  const auto result = policy.targetPose(
    pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT,
    pick_place::State::RECOVER_MOVE_ABOVE_PICK, observation);

  ASSERT_TRUE(result.target_pose);
  EXPECT_DOUBLE_EQ(0.12, result.target_pose->x);
  EXPECT_DOUBLE_EQ(-0.08, result.target_pose->y);
  EXPECT_DOUBLE_EQ(0.987, result.target_pose->z);
}

TEST(HeadlessFaultFixture, BuildsLiftThenLateralWaypoints)
{
  const pick_place::Pose3d start{0.3, 0.0, 0.87, 1.0, 0.0, 0.0, 0.0};

  const auto result = pick_place::buildLiftThenLateralWaypoints(start, 0.03, -0.03);

  ASSERT_FALSE(result.failure);
  ASSERT_EQ(2U, result.waypoints.size());
  EXPECT_DOUBLE_EQ(0.3, result.waypoints[0].x);
  EXPECT_DOUBLE_EQ(0.0, result.waypoints[0].y);
  EXPECT_DOUBLE_EQ(0.9, result.waypoints[0].z);
  EXPECT_DOUBLE_EQ(0.3, result.waypoints[1].x);
  EXPECT_DOUBLE_EQ(-0.03, result.waypoints[1].y);
  EXPECT_DOUBLE_EQ(0.9, result.waypoints[1].z);
  EXPECT_EQ(start.qx, result.waypoints[1].qx);
  EXPECT_EQ(start.qw, result.waypoints[1].qw);
}

TEST(HeadlessFaultFixture, ZeroLateralOffsetPreservesLegacySingleLift)
{
  const pick_place::Pose3d start{0.3, 0.0, 0.87, 1.0, 0.0, 0.0, 0.0};

  const auto result = pick_place::buildLiftThenLateralWaypoints(start, 0.03, 0.0);

  ASSERT_FALSE(result.failure);
  ASSERT_EQ(1U, result.waypoints.size());
  EXPECT_DOUBLE_EQ(0.9, result.waypoints.front().z);
}

TEST(HeadlessFaultFixture, RejectsUnsafeOrNonFiniteOffsets)
{
  const pick_place::Pose3d start{0.3, 0.0, 0.87, 1.0, 0.0, 0.0, 0.0};

  EXPECT_TRUE(pick_place::buildLiftThenLateralWaypoints(start, 0.0, 0.0).failure);
  EXPECT_TRUE(pick_place::buildLiftThenLateralWaypoints(start, -0.03, 0.0).failure);
  EXPECT_TRUE(pick_place::buildLiftThenLateralWaypoints(start, 0.11, 0.0).failure);
  EXPECT_TRUE(pick_place::buildLiftThenLateralWaypoints(start, 0.03, 0.11).failure);
  EXPECT_TRUE(pick_place::buildLiftThenLateralWaypoints(
    start, 0.03, std::numeric_limits<double>::quiet_NaN()).failure);
}

TEST(FixedTargets, RecoverySafeHeightNeverCommandsDownwardMotion)
{
  const pick_place::FixedPickPlaceTargetPolicy policy;
  auto observation = makeObservation();
  observation.snapshot->tcp_pose_world.z = 1.12;

  const auto result = policy.targetPose(
    pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT,
    pick_place::State::RECOVER_MOVE_ABOVE_PICK, observation);

  ASSERT_TRUE(result.target_pose);
  EXPECT_DOUBLE_EQ(1.12, result.target_pose->z);
}

TEST(FixedTargets, DerivesSupportedCokeCenterAndUprightPoseFromTcpTarget)
{
  const pick_place::FixedPickPlaceTargetPolicy policy;

  const auto pick = pick_place::supportedCokePose(
    policy, pick_place::State::DESCEND, pick_place::State::CLOSE_GRIPPER,
    makeObservation());
  const auto place = pick_place::supportedCokePose(
    policy, pick_place::State::DESCEND_TO_PLACE, pick_place::State::OPEN_GRIPPER,
    makeObservation());

  ASSERT_TRUE(pick.target_pose);
  ASSERT_TRUE(place.target_pose);
  EXPECT_DOUBLE_EQ(0.3, pick.target_pose->x);
  EXPECT_DOUBLE_EQ(0.0, pick.target_pose->y);
  EXPECT_DOUBLE_EQ(0.836, pick.target_pose->z);
  EXPECT_DOUBLE_EQ(0.3, place.target_pose->x);
  EXPECT_DOUBLE_EQ(0.2, place.target_pose->y);
  EXPECT_DOUBLE_EQ(0.836, place.target_pose->z);
  EXPECT_DOUBLE_EQ(0.0, place.target_pose->qx);
  EXPECT_DOUBLE_EQ(0.0, place.target_pose->qy);
  EXPECT_DOUBLE_EQ(0.0, place.target_pose->qz);
  EXPECT_DOUBLE_EQ(1.0, place.target_pose->qw);
}

TEST(FixedTargets, SuppliesReturnToPickRecoveryTargets)
{
  const pick_place::FixedPickPlaceTargetPolicy policy;

  expectPose(
    policy, pick_place::State::RECOVER_MOVE_ABOVE_PICK,
    pick_place::State::RECOVER_DESCEND_TO_PICK, 0.30, 0.00, 0.987);
  expectPose(
    policy, pick_place::State::RECOVER_DESCEND_TO_PICK,
    pick_place::State::RECOVER_OPEN_GRIPPER, 0.30, 0.00, 0.870);
}

TEST(FixedTargets, ConfigurationSignatureIncludesAllTargets)
{
  const pick_place::FixedPickPlaceTargetPolicy policy;

  EXPECT_EQ(
    "fixed-v4|above_pick=0.3,0,0.987,1,0,0,0|pick=0.3,0,0.87,1,0,0,0|"
    "above_place=0.3,0.2,0.987,1,0,0,0|place=0.3,0.2,0.87,1,0,0,0|"
    "supported_coke_offset_z=-0.034|"
    "recovery_safe_height=0.987",
    policy.configurationSignature());
}
