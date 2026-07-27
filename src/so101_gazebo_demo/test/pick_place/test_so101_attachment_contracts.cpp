#include <gtest/gtest.h>

#include <set>

#include "so101_gazebo_demo/pick_place/so101_attachment_contracts.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

namespace
{

pick_place::WorldSnapshot world(bool gazebo_attached, bool moveit_attached)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.arm_stationary = true;
  snapshot.joint_positions.emplace(profile.gripper_joint, profile.q6_contact);
  snapshot.joint_velocities.emplace(profile.gripper_joint, 0.0);
  snapshot.gazebo_coke_pose_world = profile.coke_pose;
  snapshot.gazebo_coke_stationary = true;
  snapshot.gazebo_coke_attached = gazebo_attached;
  snapshot.moveit_coke_attached = moveit_attached;
  snapshot.moveit_world_object_poses.emplace(profile.table_object, profile.table_pose);
  if (moveit_attached) {
    snapshot.moveit_coke_attached_link = profile.moveit_attach_link;
    snapshot.moveit_coke_touch_links =
      std::set<std::string>(profile.moveit_touch_links.begin(), profile.moveit_touch_links.end());
    snapshot.moveit_coke_attached_relative_pose = profile.calibrated_grasp_relative_pose;
  } else {
    snapshot.moveit_world_object_poses.emplace(profile.coke_model, profile.coke_pose);
  }
  return snapshot;
}

pick_place::ActionResult succeeded()
{
  return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
}

pick_place::TransitionKey key(pick_place::State from, pick_place::State to)
{
  return {from, to};
}

}  // namespace

TEST(SO101AttachmentContracts, RegistersEveryForwardAndRecoveryAttachmentBoundary)
{
  pick_place::TransitionContractRegistry registry;
  pick_place::registerSO101AttachmentContracts(registry, pick_place::SO101Profile::canonical());

  for (const auto transition : {
         key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT),
         key(pick_place::State::ATTACH_MOVEIT, pick_place::State::LIFT),
         key(pick_place::State::DETACH_GAZEBO, pick_place::State::DETACH_MOVEIT),
         key(pick_place::State::DETACH_MOVEIT, pick_place::State::SYNC_WORLD_OBJECT),
         key(pick_place::State::SYNC_WORLD_OBJECT, pick_place::State::RETREAT),
         key(pick_place::State::RECOVER_DETACH_GAZEBO,
             pick_place::State::RECOVER_DETACH_MOVEIT),
         key(pick_place::State::RECOVER_DETACH_MOVEIT,
             pick_place::State::RECOVER_SYNC_WORLD_OBJECT),
         key(pick_place::State::RECOVER_SYNC_WORLD_OBJECT,
             pick_place::State::RECOVER_RETREAT),
       }) {
    EXPECT_TRUE(registry.hasContract(transition));
  }
}

TEST(SO101AttachmentContracts, GazeboAttachNeedsFreshTrueEvidenceAndNoCokeJump)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = pick_place::makeSO101AttachmentContract(
    key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT), profile);
  const auto before = world(false, false);
  auto after = world(true, false);
  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);

  after.gazebo_coke_attached = false;
  EXPECT_FALSE(contract->validate(before, after, succeeded()).ok);
  after = world(true, false);
  after.gazebo_coke_pose_world->x += profile.coke_position_drift_tolerance * 2.0;
  EXPECT_FALSE(contract->validate(before, after, succeeded()).ok);
}

TEST(SO101AttachmentContracts, MoveItAttachNeedsIndependentExactMetadataAndBothWorldsAttached)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = pick_place::makeSO101AttachmentContract(
    key(pick_place::State::ATTACH_MOVEIT, pick_place::State::LIFT), profile);
  const auto before = world(true, false);
  auto after = world(true, true);
  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);

  after.moveit_coke_attached_link = "jaw";
  EXPECT_FALSE(contract->validate(before, after, succeeded()).ok);
  after = world(true, true);
  after.moveit_coke_touch_links = {"gripper"};
  EXPECT_FALSE(contract->validate(before, after, succeeded()).ok);
  after = world(true, true);
  after.moveit_world_object_poses.emplace(profile.coke_model, profile.coke_pose);
  EXPECT_FALSE(contract->validate(before, after, succeeded()).ok);
  after = world(true, true);
  after.moveit_coke_attached_relative_pose->x += profile.coke_position_drift_tolerance * 2.0;
  EXPECT_FALSE(contract->validate(before, after, succeeded()).ok);
}

TEST(SO101AttachmentContracts, ForwardDetachOrderUsesCurrentDualWorldFacts)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto gazebo_contract = pick_place::makeSO101AttachmentContract(
    key(pick_place::State::DETACH_GAZEBO, pick_place::State::DETACH_MOVEIT), profile);
  auto before = world(true, true);
  auto after_gazebo = world(false, true);
  before.joint_positions[profile.gripper_joint] = profile.q6_preopen;
  after_gazebo.joint_positions[profile.gripper_joint] = profile.q6_preopen;
  EXPECT_TRUE(gazebo_contract->validate(before, after_gazebo, succeeded()).ok);
  after_gazebo.gazebo_coke_attached = true;
  EXPECT_FALSE(gazebo_contract->validate(before, after_gazebo, succeeded()).ok);
  after_gazebo = world(false, false);
  after_gazebo.joint_positions[profile.gripper_joint] = profile.q6_preopen;
  EXPECT_FALSE(gazebo_contract->validate(before, after_gazebo, succeeded()).ok);

  const auto moveit_contract = pick_place::makeSO101AttachmentContract(
    key(pick_place::State::DETACH_MOVEIT, pick_place::State::SYNC_WORLD_OBJECT), profile);
  before = world(false, true);
  auto after_moveit = world(false, false);
  before.joint_positions[profile.gripper_joint] = profile.q6_preopen;
  after_moveit.joint_positions[profile.gripper_joint] = profile.q6_preopen;
  EXPECT_TRUE(moveit_contract->validate(before, after_moveit, succeeded()).ok);
  after_moveit.moveit_world_object_poses.erase(profile.coke_model);
  EXPECT_FALSE(moveit_contract->validate(before, after_moveit, succeeded()).ok);
}

TEST(SO101AttachmentContracts, SyncComparesIndependentGazeboAndMoveItSixDegreePoses)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = pick_place::makeSO101AttachmentContract(
    key(pick_place::State::SYNC_WORLD_OBJECT, pick_place::State::RETREAT), profile);
  auto before = world(false, false);
  auto after = world(false, false);
  before.joint_positions[profile.gripper_joint] = profile.q6_preopen;
  after.joint_positions[profile.gripper_joint] = profile.q6_preopen;
  pick_place::Pose3d observed{0.11, -0.24, 0.183, 0.0, 0.0, 0.198669331, 0.980066578};
  after.gazebo_coke_pose_world = observed;
  after.moveit_world_object_poses[profile.coke_model] = observed;
  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);

  after.moveit_world_object_poses[profile.coke_model].qz = 0.0;
  after.moveit_world_object_poses[profile.coke_model].qw = 1.0;
  EXPECT_FALSE(contract->validate(before, after, succeeded()).ok);
}

TEST(SO101AttachmentContracts, RecoveryDetachAndSyncAcceptAlreadyConvergedCurrentFacts)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  auto detached = world(false, false);
  detached.joint_positions[profile.gripper_joint] = profile.q6_preopen;
  for (const auto transition : {
         key(pick_place::State::RECOVER_DETACH_GAZEBO,
             pick_place::State::RECOVER_DETACH_MOVEIT),
         key(pick_place::State::RECOVER_DETACH_MOVEIT,
             pick_place::State::RECOVER_SYNC_WORLD_OBJECT),
         key(pick_place::State::RECOVER_SYNC_WORLD_OBJECT,
             pick_place::State::RECOVER_RETREAT),
       }) {
    const auto contract = pick_place::makeSO101AttachmentContract(transition, profile);
    EXPECT_TRUE(contract->validate(detached, detached, succeeded()).ok);
  }
}

TEST(SO101AttachmentContracts, ActionSuccessAloneNeverSatisfiesMissingObservations)
{
  const auto contract = pick_place::makeSO101AttachmentContract(
    key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT),
    pick_place::SO101Profile::canonical());
  pick_place::WorldSnapshot empty;
  EXPECT_FALSE(contract->validate(empty, empty, succeeded()).ok);
}
