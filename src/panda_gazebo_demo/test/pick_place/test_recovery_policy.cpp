#include <gtest/gtest.h>

#include <memory>

#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"
#include "panda_gazebo_demo/pick_place/recovery_policy.hpp"

namespace pick_place = panda_gazebo_demo::pick_place;

namespace
{

constexpr pick_place::Pose3d kPick{0.3, 0.0, 0.87, 1.0, 0.0, 0.0, 0.0};
constexpr pick_place::Pose3d kPlace{0.3, 0.2, 0.87, 1.0, 0.0, 0.0, 0.0};
constexpr pick_place::Pose3d kAbovePick{0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0};
constexpr pick_place::Pose3d kCokePick{0.3, 0.0, 0.836, 0.0, 0.0, 0.0, 1.0};
constexpr pick_place::Pose3d kCokePlace{0.3, 0.2, 0.836, 0.0, 0.0, 0.0, 1.0};
constexpr pick_place::Pose3d kCokeAbovePick{0.3, 0.0, 0.953, 0.0, 0.0, 0.0, 1.0};

pick_place::WorldSnapshot snapshot(
  bool gazebo_attached, bool moveit_attached,
  const pick_place::Pose3d & tcp = kPick,
  const pick_place::Pose3d & coke = kCokePick)
{
  pick_place::WorldSnapshot world;
  world.fresh = true;
  world.arm_stationary = true;
  world.tcp_pose_world = tcp;
  world.gazebo_coke_pose_world = coke;
  world.gazebo_coke_stationary = true;
  world.gazebo_coke_attached = gazebo_attached;
  world.moveit_coke_attached = moveit_attached;
  world.joint_positions = {{"panda_finger_joint1", 0.032},
    {"panda_finger_joint2", 0.032}};
  world.joint_velocities = {{"panda_finger_joint1", 0.0},
    {"panda_finger_joint2", 0.0}};
  if (!moveit_attached) {
    world.moveit_world_object_poses["coke"] = coke;
  }
  return world;
}

void setGripperOpen(pick_place::WorldSnapshot & world)
{
  world.gripper_open = true;
  world.joint_positions["panda_finger_joint1"] = 0.04;
  world.joint_positions["panda_finger_joint2"] = 0.04;
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
    policy, snapshot(true, true,
    {0.3, 0.0, 0.95, 1.0, 0.0, 0.0, 0.0},
    {0.3, 0.0, 0.916, 0.0, 0.0, 0.0, 1.0}),
    pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT);
  expectRoute(
    policy, snapshot(true, true), pick_place::State::RECOVER_OPEN_GRIPPER);
  expectRoute(
    policy, snapshot(true, false), pick_place::State::RECOVER_OPEN_GRIPPER);
  expectRoute(
    policy, snapshot(false, true), pick_place::State::RECOVER_OPEN_GRIPPER);
  expectRoute(
    policy, snapshot(false, false), pick_place::State::RECOVER_OPEN_GRIPPER);

  auto stale = snapshot(false, false);
  stale.fresh = false;
  expectRouteError(policy, stale, "RECOVERY_OBSERVATION_NOT_FRESH");

  auto moving = snapshot(false, false);
  moving.arm_stationary = false;
  expectRouteError(policy, moving, "RECOVERY_ROBOT_NOT_STATIONARY");

  auto missing_attachment = snapshot(false, false);
  missing_attachment.gazebo_coke_attached.reset();
  expectRouteError(policy, missing_attachment, "RECOVERY_ATTACHMENT_STATE_UNKNOWN");
}

TEST(FixedRecoveryPolicy, OpensOnlyWithPositivePickOrPlaceSupportEvidence)
{
  const pick_place::FixedRecoveryPolicy policy(
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), 0.02);

  expectRoute(
    policy, snapshot(true, true, kPick, kCokePick),
    pick_place::State::RECOVER_OPEN_GRIPPER);
  expectRoute(
    policy, snapshot(true, true, kPlace, kCokePlace),
    pick_place::State::RECOVER_OPEN_GRIPPER);
}

TEST(FixedRecoveryPolicy, BothAttachedWithoutPositiveSupportUsesCarryingRecovery)
{
  const pick_place::FixedRecoveryPolicy policy(
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), 0.02);

  auto wrong_xy = snapshot(true, true,
      {0.1, 0.1, 0.87, 1.0, 0.0, 0.0, 0.0},
      {0.1, 0.1, 0.836, 0.0, 0.0, 0.0, 1.0});
  expectRoute(policy, wrong_xy, pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT);

  auto wrong_orientation = snapshot(true, true);
  wrong_orientation.tcp_pose_world = {0.3, 0.0, 0.87, 0.0, 0.0, 0.0, 1.0};
  expectRoute(policy, wrong_orientation, pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT);

  auto missing_coke = snapshot(true, true);
  missing_coke.gazebo_coke_pose_world.reset();
  expectRouteError(policy, missing_coke, "RECOVERY_COKE_POSE_UNKNOWN");

  auto tilted_coke = snapshot(true, true);
  tilted_coke.gazebo_coke_pose_world = {0.3, 0.0, 0.836, 0.258819, 0.0, 0.0, 0.965926};
  expectRouteError(policy, tilted_coke, "RECOVERY_CARRIED_POSE_INCONSISTENT");
}

TEST(FixedRecoveryPolicy, PartialAttachmentWithoutPositiveSupportFailsClosed)
{
  const pick_place::FixedRecoveryPolicy policy(
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), 0.02);
  const pick_place::Pose3d wrong_xy{0.1, 0.1, 0.87, 1.0, 0.0, 0.0, 0.0};

  expectRouteError(
    policy, snapshot(true, false, wrong_xy), "RECOVERY_PARTIAL_ATTACHMENT_UNSUPPORTED");
  expectRouteError(
    policy, snapshot(false, true, wrong_xy), "RECOVERY_PARTIAL_ATTACHMENT_UNSUPPORTED");
}

TEST(FixedRecoveryPolicy, CarryingResumeAdvancesFromSafeHeightToMoveAbovePick)
{
  const pick_place::FixedRecoveryPolicy policy(
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), 0.02);
  const pick_place::Pose3d safe_tcp{0.1, -0.1, 1.05, 1.0, 0.0, 0.0, 0.0};
  const pick_place::Pose3d carried_coke{0.1, -0.1, 1.016, 0.0, 0.0, 0.0, 1.0};

  expectRoute(
    policy, snapshot(true, true, safe_tcp, carried_coke),
    pick_place::State::RECOVER_MOVE_ABOVE_PICK);
}

TEST(FixedRecoveryPolicy, CarryingResumeAdvancesFromAbovePickToDescend)
{
  const pick_place::FixedRecoveryPolicy policy(
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), 0.02);

  expectRoute(
    policy, snapshot(true, true, kAbovePick, kCokeAbovePick),
    pick_place::State::RECOVER_DESCEND_TO_PICK);
}

TEST(FixedRecoveryPolicy, DetachedOpenSynchronizedResumeAdvancesToRetreat)
{
  const pick_place::FixedRecoveryPolicy policy(
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), 0.02);
  auto world = snapshot(false, false);
  setGripperOpen(world);

  expectRoute(policy, world, pick_place::State::RECOVER_RETREAT);
}

TEST(FixedRecoveryPolicy, SupportedPartialAttachmentAdvancesOnlyAfterOpening)
{
  const pick_place::FixedRecoveryPolicy policy(
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), 0.02);
  auto gazebo_only = snapshot(true, false);
  expectRoute(policy, gazebo_only, pick_place::State::RECOVER_OPEN_GRIPPER);
  setGripperOpen(gazebo_only);
  expectRoute(policy, gazebo_only, pick_place::State::RECOVER_DETACH_GAZEBO);

  auto moveit_only = snapshot(false, true);
  expectRoute(policy, moveit_only, pick_place::State::RECOVER_OPEN_GRIPPER);
  setGripperOpen(moveit_only);
  expectRoute(policy, moveit_only, pick_place::State::RECOVER_DETACH_MOVEIT);
}

TEST(FixedRecoveryPolicy, DetachedResumeOpensThenSynchronizesBeforeRetreat)
{
  const pick_place::FixedRecoveryPolicy policy(
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), 0.02);
  auto world = snapshot(false, false);
  expectRoute(policy, world, pick_place::State::RECOVER_OPEN_GRIPPER);

  setGripperOpen(world);
  world.moveit_world_object_poses["coke"].x += 0.05;
  expectRoute(policy, world, pick_place::State::RECOVER_SYNC_WORLD_OBJECT);

  world.moveit_world_object_poses["coke"] = *world.gazebo_coke_pose_world;
  expectRoute(policy, world, pick_place::State::RECOVER_RETREAT);
}

TEST(FixedRecoveryPolicy, MissingProgressFactsFailClosed)
{
  const pick_place::FixedRecoveryPolicy policy(
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(), 0.02);
  auto missing_coke = snapshot(true, true);
  missing_coke.gazebo_coke_pose_world.reset();
  expectRouteError(policy, missing_coke, "RECOVERY_COKE_POSE_UNKNOWN");

  auto missing_gripper = snapshot(false, false);
  missing_gripper.joint_positions.clear();
  expectRouteError(policy, missing_gripper, "RECOVERY_GRIPPER_STATE_UNKNOWN");

  auto missing_moveit_pose = snapshot(false, false);
  setGripperOpen(missing_moveit_pose);
  missing_moveit_pose.moveit_world_object_poses.clear();
  expectRouteError(policy, missing_moveit_pose, "RECOVERY_MOVEIT_COKE_POSE_UNKNOWN");
}
