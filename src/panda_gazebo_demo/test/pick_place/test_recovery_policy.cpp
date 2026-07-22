#include <gtest/gtest.h>

#include <memory>

#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"
#include "panda_gazebo_demo/pick_place/recovery_policy.hpp"

namespace pick_place = panda_gazebo_demo::pick_place;

namespace
{

pick_place::WorldSnapshot snapshot(bool gazebo_attached, bool moveit_attached, double tcp_z)
{
  pick_place::WorldSnapshot world;
  world.fresh = true;
  world.arm_stationary = true;
  world.tcp_pose_world = {0.3, 0.0, tcp_z, 1.0, 0.0, 0.0, 0.0};
  world.gazebo_coke_attached = gazebo_attached;
  world.moveit_coke_attached = moveit_attached;
  return world;
}

pick_place::Failure originalFailure()
{
  return {pick_place::FailureCategory::EXECUTION, "MOVE_FAILED", "move failed", {}};
}

void expectRoute(
  const pick_place::FixedRecoveryPolicy & policy,
  const pick_place::WorldSnapshot & world, pick_place::State expected)
{
  const auto route = policy.select(
    pick_place::State::MOVE_ABOVE_PLACE, originalFailure(), world);
  ASSERT_TRUE(route.next_state);
  EXPECT_EQ(expected, *route.next_state);
  EXPECT_FALSE(route.failure);
}

void expectRouteError(
  const pick_place::FixedRecoveryPolicy & policy,
  const pick_place::WorldSnapshot & world, const std::string & expected_code)
{
  const auto route = policy.select(
    pick_place::State::MOVE_ABOVE_PLACE, originalFailure(), world);
  EXPECT_FALSE(route.next_state);
  ASSERT_TRUE(route.failure);
  EXPECT_EQ(expected_code, route.failure->code);
}

}  // namespace

TEST(FixedRecoveryPolicy, SelectsExactFactMatrix)
{
  const pick_place::FixedRecoveryPolicy policy(
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), 0.02);

  expectRoute(
    policy, snapshot(true, true, 1.0), pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT);
  expectRoute(
    policy, snapshot(true, true, 0.93), pick_place::State::RECOVER_OPEN_GRIPPER);
  expectRoute(
    policy, snapshot(true, false, 0.93), pick_place::State::RECOVER_OPEN_GRIPPER);
  expectRoute(
    policy, snapshot(false, true, 0.93), pick_place::State::RECOVER_OPEN_GRIPPER);
  expectRoute(
    policy, snapshot(false, false, 0.93), pick_place::State::RECOVER_OPEN_GRIPPER);

  auto stale = snapshot(false, false, 0.93);
  stale.fresh = false;
  expectRouteError(policy, stale, "RECOVERY_OBSERVATION_NOT_FRESH");

  auto moving = snapshot(false, false, 0.93);
  moving.arm_stationary = false;
  expectRouteError(policy, moving, "RECOVERY_ROBOT_NOT_STATIONARY");

  auto missing_attachment = snapshot(false, false, 0.93);
  missing_attachment.gazebo_coke_attached.reset();
  expectRouteError(policy, missing_attachment, "RECOVERY_ATTACHMENT_STATE_UNKNOWN");
}
