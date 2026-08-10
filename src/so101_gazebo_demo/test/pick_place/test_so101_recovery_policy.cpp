#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/so101_recovery_policy.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

namespace
{

pick_place::Failure originalFailure()
{
  return {pick_place::FailureCategory::EXECUTION, "ORIGINAL", "injected", {}};
}

pick_place::Failure unexecutedPlanValidationFailure()
{
  return {pick_place::FailureCategory::PLAN_VALIDATION,
          "TARGET_PLAN_VALIDATION_FAILED",
          "injected",
          {{"plan_only_target_not_executed", 1.0}}};
}

pick_place::WorldSnapshot observed(bool gazebo_attached, bool moveit_attached, double q6)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::WorldSnapshot snapshot;
  snapshot.observed_at = std::chrono::steady_clock::now();
  snapshot.fresh = true;
  snapshot.arm_stationary = true;
  for (std::size_t index = 0; index < profile.arm_joints.size(); ++index) {
    snapshot.joint_positions.emplace(profile.arm_joints[index], profile.arm_home_positions[index]);
    snapshot.joint_velocities.emplace(profile.arm_joints[index], 0.0);
  }
  snapshot.joint_positions.emplace(profile.gripper_joint, q6);
  snapshot.joint_velocities.emplace(profile.gripper_joint, 0.0);
  snapshot.gazebo_task_object_pose_world = profile.task_object_pose;
  snapshot.gazebo_pose_observed_at = snapshot.observed_at;
  snapshot.gazebo_pose_sequence = 1;
  snapshot.gazebo_task_object_stationary = true;
  snapshot.gazebo_task_object_attached = gazebo_attached;
  snapshot.moveit_task_object_attached = moveit_attached;
  snapshot.moveit_world_object_poses.emplace(profile.table_object, profile.table_pose);
  if (!moveit_attached) {
    snapshot.moveit_world_object_poses.emplace(profile.task_object_id, profile.task_object_pose);
  } else {
    snapshot.moveit_task_object_attached_link = profile.moveit_attach_link;
    snapshot.moveit_task_object_touch_links = {profile.moveit_attach_link, "jaw"};
  }
  return snapshot;
}

void markPhysicallyHeld(pick_place::WorldSnapshot & snapshot, bool supported)
{
  snapshot.gazebo_task_object_gripper_contact = true;
  snapshot.gazebo_gripper_contact_observed_at = snapshot.observed_at;
  snapshot.gazebo_task_object_intended_support_contact = supported;
  snapshot.gazebo_support_contact_observed_at = snapshot.observed_at;
}

}  // namespace

TEST(SO101RecoveryPolicy, RoutesOnlyFromFreshStationaryCurrentFacts)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::SO101RecoveryPolicy policy(profile);
  auto world = observed(false, false, profile.q6_preopen);
  world.fresh = false;
  EXPECT_FALSE(
    policy.select(pick_place::State::CLOSE_GRIPPER, originalFailure(), world).next_state);
  world = observed(false, false, profile.q6_preopen);
  world.arm_stationary = false;
  EXPECT_FALSE(
    policy.select(pick_place::State::CLOSE_GRIPPER, originalFailure(), world).next_state);
  world = observed(false, false, profile.q6_preopen);
  world.gazebo_task_object_attached.reset();
  EXPECT_FALSE(
    policy.select(pick_place::State::CLOSE_GRIPPER, originalFailure(), world).next_state);
  world = observed(false, false, profile.q6_preopen);
  world.joint_velocities[profile.gripper_joint] = profile.q6_velocity_tolerance * 2.0;
  EXPECT_FALSE(
    policy.select(pick_place::State::CLOSE_GRIPPER, originalFailure(), world).next_state);
}

TEST(SO101RecoveryPolicy, CurrentQ6AndAttachmentFactsChooseMinimalSafeReleaseRoute)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::SO101RecoveryPolicy policy(profile);
  const auto failure = originalFailure();

  auto held_with_shadow = observed(true, true, profile.q6_contact);
  markPhysicallyHeld(held_with_shadow, true);
  EXPECT_FALSE(
    policy.select(pick_place::State::ATTACH_MOVEIT, failure, held_with_shadow).next_state);
  EXPECT_EQ(pick_place::State::RECOVER_DETACH_MOVEIT,
            policy
              .select(pick_place::State::ATTACH_MOVEIT, failure,
                      observed(false, true, profile.q6_full_open))
              .next_state);
}

TEST(SO101RecoveryPolicy, UnexpectedGazeboAttachmentHoldsForOperatorWithoutDetachCommand)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::SO101RecoveryPolicy policy(profile);
  const auto route = policy.select(pick_place::State::ATTACH_MOVEIT, originalFailure(),
                                   observed(true, false, profile.q6_full_open));

  EXPECT_FALSE(route.next_state);
  ASSERT_TRUE(route.failure);
  EXPECT_EQ("ORIGINAL", route.failure->code);
  EXPECT_DOUBLE_EQ(1.0, route.failure->metrics.at("recovery_disposition_hold_for_operator"));
}

TEST(SO101RecoveryPolicy, DetachedFactsChooseOpenSyncOrRetreat)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::SO101RecoveryPolicy policy(profile);
  const auto failure = originalFailure();

  auto supported = observed(false, false, profile.q6_contact);
  markPhysicallyHeld(supported, true);
  EXPECT_EQ(pick_place::State::RECOVER_OPEN_GRIPPER,
            policy.select(pick_place::State::DETACH_MOVEIT, failure, supported).next_state);

  auto mismatch = observed(false, false, profile.q6_full_open);
  mismatch.moveit_world_object_poses[profile.task_object_id].x +=
    profile.task_object_position_drift_tolerance * 2.0;
  EXPECT_EQ(pick_place::State::RECOVER_SYNC_WORLD_OBJECT,
            policy.select(pick_place::State::DETACH_MOVEIT, failure, mismatch).next_state);

  auto missing = observed(false, false, profile.q6_full_open);
  missing.moveit_world_object_poses.erase(profile.task_object_id);
  EXPECT_EQ(pick_place::State::RECOVER_SYNC_WORLD_OBJECT,
            policy.select(pick_place::State::DETACH_MOVEIT, failure, missing).next_state);

  EXPECT_EQ(pick_place::State::RECOVER_RETREAT,
            policy
              .select(pick_place::State::DETACH_MOVEIT, failure,
                      observed(false, false, profile.q6_full_open))
              .next_state);
}

TEST(SO101RecoveryPolicy, SameCurrentWorldIgnoresFailedStateAndHistoricalFlags)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::SO101RecoveryPolicy policy(profile);
  const auto current = observed(false, true, profile.q6_full_open);
  const auto first = policy.select(pick_place::State::CLOSE_GRIPPER, originalFailure(), current);
  auto different_history = originalFailure();
  different_history.metrics["gazebo_was_attached"] = 0.0;
  different_history.metrics["moveit_was_attached"] = 1.0;
  const auto second =
    policy.select(pick_place::State::MOVE_ABOVE_PLACE, different_history, current);
  EXPECT_EQ(first.next_state, second.next_state);
  EXPECT_EQ(pick_place::State::RECOVER_DETACH_MOVEIT, second.next_state);
}

TEST(SO101RecoveryPolicy, AttachedTaskObjectAwayFromKnownSupportFailsClosedUntilMotionPolicyExists)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::SO101RecoveryPolicy policy(profile);
  auto unsupported = observed(true, true, profile.q6_contact);
  unsupported.gazebo_task_object_pose_world->z += 0.10;

  const auto route = policy.select(pick_place::State::LIFT, originalFailure(), unsupported);

  EXPECT_FALSE(route.next_state);
  ASSERT_TRUE(route.failure);
  EXPECT_EQ(pick_place::FailureCategory::WORLD_INCONSISTENCY, route.failure->category);
  EXPECT_EQ("UNSAFE_RECOVERY_OBSERVATION", route.failure->code);
}

TEST(SO101RecoveryPolicy, PhysicallyHeldUnsupportedCupStopsWithoutOpening)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::SO101RecoveryPolicy policy(profile);
  auto unsupported = observed(false, false, profile.q6_contact);
  markPhysicallyHeld(unsupported, false);

  const auto route = policy.select(pick_place::State::LIFT, originalFailure(), unsupported);

  EXPECT_FALSE(route.next_state);
  ASSERT_TRUE(route.failure);
  EXPECT_EQ("ORIGINAL", route.failure->code);
  EXPECT_DOUBLE_EQ(1.0, route.failure->metrics.at("recovery_disposition_hold_for_operator"));
}

TEST(SO101RecoveryPolicy, SupportedHeldCupMaySelectControlledOpen)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::SO101RecoveryPolicy policy(profile);
  auto supported = observed(false, false, profile.q6_contact);
  markPhysicallyHeld(supported, true);

  EXPECT_EQ(
    pick_place::State::RECOVER_OPEN_GRIPPER,
    policy.select(pick_place::State::DESCEND_TO_PLACE, originalFailure(), supported).next_state);

  supported.moveit_task_object_attached = true;
  supported.moveit_world_object_poses.erase(profile.task_object_id);
  EXPECT_FALSE(
    policy.select(pick_place::State::DESCEND_TO_PLACE, originalFailure(), supported).next_state);
}

TEST(SO101RecoveryPolicy, PostReleaseFailurePreservesEvidenceWithoutMotion)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::SO101RecoveryPolicy policy(profile);
  auto released = observed(false, false, profile.q6_full_open);
  released.gazebo_task_object_gripper_contact = false;
  released.gazebo_task_object_intended_support_contact = true;
  released.gazebo_support_contact_observed_at = released.observed_at;

  const auto route =
    policy.select(pick_place::State::VALIDATE_FINAL_PLACEMENT, originalFailure(), released);

  EXPECT_FALSE(route.next_state);
  ASSERT_TRUE(route.failure);
  EXPECT_EQ("ORIGINAL", route.failure->code);
}

TEST(SO101RecoveryPolicy, StaleGazeboJointStopsForOperatorWithoutDetachCommand)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::SO101RecoveryPolicy policy(profile);
  auto stale_joint = observed(true, false, profile.q6_full_open);
  stale_joint.gazebo_task_object_gripper_contact = false;

  const auto route = policy.select(pick_place::State::IDLE, originalFailure(), stale_joint);

  EXPECT_FALSE(route.next_state);
  ASSERT_TRUE(route.failure);
  EXPECT_EQ("ORIGINAL", route.failure->code);
  EXPECT_DOUBLE_EQ(1.0, route.failure->metrics.at("recovery_disposition_hold_for_operator"));
}

TEST(SO101RecoveryPolicy, SkipsRetreatOnlyForAnUnexecutedPlanValidationTargetAtSafeHome)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::SO101RecoveryPolicy policy(profile);
  const auto failure = unexecutedPlanValidationFailure();
  const auto safe = observed(false, false, profile.q6_full_open);

  EXPECT_TRUE(policy.canSkipRecoveryAction(pick_place::State::MOVE_ABOVE_OBJECT, failure,
                                           pick_place::State::RECOVER_RETREAT, safe));

  auto not_plan_validation = failure;
  not_plan_validation.category = pick_place::FailureCategory::PLANNING;
  EXPECT_FALSE(policy.canSkipRecoveryAction(pick_place::State::MOVE_ABOVE_OBJECT,
                                            not_plan_validation, pick_place::State::RECOVER_RETREAT,
                                            safe));
  auto target_executed = failure;
  target_executed.metrics["plan_only_target_not_executed"] = 0.0;
  EXPECT_FALSE(policy.canSkipRecoveryAction(pick_place::State::MOVE_ABOVE_OBJECT, target_executed,
                                            pick_place::State::RECOVER_RETREAT, safe));
  EXPECT_FALSE(policy.canSkipRecoveryAction(pick_place::State::MOVE_ABOVE_OBJECT, failure,
                                            pick_place::State::RECOVER_SYNC_WORLD_OBJECT, safe));

  auto moving = safe;
  moving.arm_stationary = false;
  EXPECT_FALSE(policy.canSkipRecoveryAction(pick_place::State::MOVE_ABOVE_OBJECT, failure,
                                            pick_place::State::RECOVER_RETREAT, moving));
  auto away_from_home = safe;
  away_from_home.joint_positions[profile.arm_joints.front()] = 0.02;
  EXPECT_FALSE(policy.canSkipRecoveryAction(pick_place::State::MOVE_ABOVE_OBJECT, failure,
                                            pick_place::State::RECOVER_RETREAT, away_from_home));
  auto gazebo_attached = safe;
  gazebo_attached.gazebo_task_object_attached = true;
  EXPECT_FALSE(policy.canSkipRecoveryAction(pick_place::State::MOVE_ABOVE_OBJECT, failure,
                                            pick_place::State::RECOVER_RETREAT, gazebo_attached));
  auto moveit_attached = safe;
  moveit_attached.moveit_task_object_attached = true;
  EXPECT_FALSE(policy.canSkipRecoveryAction(pick_place::State::MOVE_ABOVE_OBJECT, failure,
                                            pick_place::State::RECOVER_RETREAT, moveit_attached));
  auto unsynchronized = safe;
  unsynchronized.moveit_world_object_poses[profile.task_object_id].x +=
    profile.task_object_position_drift_tolerance * 2.0;
  EXPECT_FALSE(policy.canSkipRecoveryAction(pick_place::State::MOVE_ABOVE_OBJECT, failure,
                                            pick_place::State::RECOVER_RETREAT, unsynchronized));
}
