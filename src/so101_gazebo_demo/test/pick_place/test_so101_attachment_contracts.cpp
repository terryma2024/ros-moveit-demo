#include <gtest/gtest.h>

#include <chrono>
#include <cmath>
#include <limits>
#include <set>
#include <sstream>
#include <variant>
#include <vector>

#include "so101_gazebo_demo/pick_place/final_placement_evidence_store.hpp"
#include "so101_gazebo_demo/pick_place/so101_attachment_contracts.hpp"
#include "so101_gazebo_demo/pick_place/so101_moveit_scene_policy.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

namespace
{

pick_place::TaskObjectContactSample contactSample(std::string cup_collision, double normal_y,
                                                  double local_z, double depth = 0.0004);

pick_place::WorldSnapshot world(bool gazebo_attached, bool moveit_attached)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.observed_at = std::chrono::steady_clock::time_point{std::chrono::milliseconds{100}};
  snapshot.arm_stationary = true;
  snapshot.joint_positions.emplace(profile.gripper_joint, profile.q6_contact);
  snapshot.joint_velocities.emplace(profile.gripper_joint, 0.0);
  snapshot.gazebo_task_object_pose_world = profile.task_object_pose;
  snapshot.gazebo_pose_sequence = 7;
  snapshot.gazebo_pose_observed_at = snapshot.observed_at;
  snapshot.gazebo_task_object_stationary = true;
  snapshot.gazebo_task_object_gripper_contact = true;
  snapshot.gazebo_task_object_fixed_finger_contact = true;
  snapshot.gazebo_task_object_moving_jaw_contact = true;
  snapshot.gazebo_task_object_gripper_max_depth = 0.0005;
  snapshot.gazebo_task_object_fixed_contact_min_height = 0.185;
  snapshot.gazebo_task_object_fixed_contact_max_height = 0.187;
  snapshot.gazebo_task_object_moving_contact_min_height = 0.190;
  snapshot.gazebo_task_object_moving_contact_max_height = 0.192;
  snapshot.gazebo_task_object_fixed_finger_contacts = {contactSample("wall_near", 1.0, 0.020)};
  snapshot.gazebo_task_object_moving_jaw_contacts = {contactSample("wall_near", -1.0, 0.020)};
  snapshot.gazebo_task_object_attached = gazebo_attached;
  snapshot.moveit_task_object_attached = moveit_attached;
  snapshot.moveit_world_object_poses.emplace(profile.table_object, profile.table_pose);
  if (moveit_attached) {
    snapshot.moveit_task_object_attached_link = profile.moveit_attach_link;
    snapshot.moveit_task_object_touch_links =
      std::set<std::string>(profile.moveit_touch_links.begin(), profile.moveit_touch_links.end());
    snapshot.moveit_task_object_attached_relative_pose = profile.calibrated_grasp_relative_pose;
    snapshot.moveit_gripper_pose_world = pick_place::Pose3d{};
  } else {
    snapshot.moveit_world_object_poses.emplace(profile.task_object_id, profile.task_object_pose);
  }
  return snapshot;
}

pick_place::ActionResult succeeded()
{
  return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
}

std::string failureCodes(const pick_place::ValidationResult & result)
{
  std::ostringstream output;
  for (const auto & failure : result.failures) {
    if (output.tellp() > 0)
      output << ',';
    output << failure.code;
  }
  return output.str();
}

pick_place::TransitionKey key(pick_place::State from, pick_place::State to)
{
  return {from, to};
}

void setTaskObjectPose(pick_place::WorldSnapshot & snapshot, const pick_place::Pose3d & pose)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  snapshot.gazebo_task_object_pose_world = pose;
  if (!snapshot.moveit_task_object_attached.value_or(true)) {
    snapshot.moveit_world_object_poses[profile.task_object_id] = pose;
  }
}

pick_place::TaskObjectContactSample contactSample(std::string cup_collision, double normal_y,
                                                  double local_z, double depth)
{
  pick_place::TaskObjectContactSample sample;
  sample.task_object_collision = std::move(cup_collision);
  sample.finger_collision = "finger_collision";
  sample.point_world = {0.02, -0.24, 0.165 + local_z};
  sample.normal_toward_finger_world = {0.0, normal_y, 0.0};
  sample.point_task_object = {0.0, 0.039, local_z};
  sample.normal_toward_finger_task_object = {0.0, normal_y, 0.0};
  sample.depth = depth;
  return sample;
}

pick_place::WorldSnapshot semanticWallGrasp()
{
  auto snapshot = world(false, false);
  snapshot.gazebo_task_object_fixed_finger_contacts = {contactSample("wall_near", 1.0, 0.020)};
  snapshot.gazebo_task_object_moving_jaw_contacts = {contactSample("wall_near", -1.0, 0.020)};
  return snapshot;
}

pick_place::TaskObjectConfig testObjectConfig(const pick_place::SO101Profile & profile)
{
  pick_place::TaskObjectConfig object;
  object.object_id = profile.task_object_id;
  object.model.height_m = profile.task_object_height;
  object.model.outer_radius_m = profile.task_object_outer_radius;
  object.model.wall_thickness_m = profile.task_object_wall_thickness;
  object.model.bottom_thickness_m = profile.task_object_bottom_thickness;
  object.grasp_frame.near_wall_outward_world = {0.0, 1.0, 0.0};
  return object;
}

pick_place::GraspContactValidationConfig testContactPolicy()
{
  return {true,   true,  "wall_near", "outside", "inside",
          0.0008, 0.008, 0.035,       0.020,     {"rim", "bottom", "wall_opposite"}};
}

pick_place::PhysicalOutcomePolicyConfig physicalOutcomePolicy()
{
  pick_place::PhysicalOutcomePolicyConfig result;
  result.planning_shadow.max_position_divergence_m = 0.01;
  result.planning_shadow.max_orientation_divergence_rad = 0.1;
  result.planning_shadow.max_pair_age_s = 0.2;
  result.calibration_complete = true;
  return result;
}

std::shared_ptr<const pick_place::TransitionContractRegistry::ITransitionContract>
attachmentContract(pick_place::TransitionKey transition,
                   const pick_place::SO101Profile & profile = pick_place::SO101Profile::canonical())
{
  return pick_place::makeSO101AttachmentContract(transition, profile, testObjectConfig(profile),
                                                 testContactPolicy());
}

}  // namespace

TEST(SO101AttachmentContracts, RegistersEveryForwardAndRecoveryAttachmentBoundary)
{
  pick_place::TransitionContractRegistry registry;
  const auto & profile = pick_place::SO101Profile::canonical();
  pick_place::registerSO101AttachmentContracts(registry, profile, testObjectConfig(profile),
                                               testContactPolicy());

  for (const auto transition : {
         key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT),
         key(pick_place::State::ATTACH_MOVEIT, pick_place::State::LIFT),
         key(pick_place::State::DETACH_GAZEBO, pick_place::State::DETACH_MOVEIT),
         key(pick_place::State::DETACH_MOVEIT, pick_place::State::WAIT_RELEASE_SETTLE),
         key(pick_place::State::SYNC_WORLD_OBJECT, pick_place::State::DONE),
         key(pick_place::State::RECOVER_DETACH_GAZEBO, pick_place::State::RECOVER_DETACH_MOVEIT),
         key(pick_place::State::RECOVER_DETACH_MOVEIT,
             pick_place::State::RECOVER_SYNC_WORLD_OBJECT),
         key(pick_place::State::RECOVER_SYNC_WORLD_OBJECT, pick_place::State::RECOVER_RETREAT),
       }) {
    EXPECT_TRUE(registry.hasContract(transition));
  }
}

TEST(SO101AttachmentContracts, GazeboAttachNeedsFreshTrueEvidenceAndNoTaskObjectJump)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = attachmentContract(
    key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT), profile);
  const auto before = world(false, false);
  auto after = world(true, false);
  const auto accepted = contract->validate(before, after, succeeded());
  EXPECT_TRUE(accepted.ok) << failureCodes(accepted);

  after.gazebo_task_object_attached = false;
  EXPECT_FALSE(contract->validate(before, after, succeeded()).ok);
  after = world(true, false);
  after.gazebo_task_object_pose_world->x += profile.task_object_position_drift_tolerance * 2.0;
  EXPECT_FALSE(contract->validate(before, after, succeeded()).ok);
}

TEST(SO101AttachmentContracts, GazeboAttachPreconditionAcceptsOnlyConfiguredBoundedPreload)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = attachmentContract(
    key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT), profile);
  auto before = world(false, false);
  before.joint_positions[profile.gripper_joint] =
    profile.q6_contact - profile.q6_regrasp_squeeze_offset;

  EXPECT_TRUE(contract->validatePrecondition(before).ok)
    << failureCodes(contract->validatePrecondition(before));

  before.joint_positions[profile.gripper_joint] -= 0.0001;
  EXPECT_FALSE(contract->validatePrecondition(before).ok);

  auto after = world(true, false);
  after.joint_positions[profile.gripper_joint] =
    profile.q6_contact - profile.q6_regrasp_squeeze_offset;
  EXPECT_FALSE(contract->validate(world(false, false), after, succeeded()).ok);
}

TEST(SO101AttachmentContracts, ArmQuiescenceFailureReportsEveryJointVelocity)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = attachmentContract(
    key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT), profile);
  auto before = world(false, false);
  before.arm_stationary = false;
  for (std::size_t i = 0; i < profile.arm_joints.size(); ++i) {
    before.joint_velocities[profile.arm_joints[i]] = 0.001 * static_cast<double>(i + 1);
  }
  before.joint_velocities[profile.gripper_joint] = 0.012;

  const auto result = contract->validatePrecondition(before);

  ASSERT_FALSE(result.ok);
  const auto failure =
    std::find_if(result.failures.begin(), result.failures.end(),
                 [](const auto & item) { return item.code == "ARM_NOT_QUIESCENT"; });
  ASSERT_NE(failure, result.failures.end());
  EXPECT_DOUBLE_EQ(0.01, failure->metrics.at("stationary_velocity_limit"));
  for (std::size_t i = 0; i < profile.arm_joints.size(); ++i) {
    EXPECT_DOUBLE_EQ(0.001 * static_cast<double>(i + 1),
                     failure->metrics.at("actual_velocity_" + profile.arm_joints[i]));
  }
  EXPECT_DOUBLE_EQ(0.012, failure->metrics.at("actual_velocity_" + profile.gripper_joint));
  EXPECT_DOUBLE_EQ(0.0, failure->metrics.at("q6_included_in_stationary_decision"));
}

TEST(SO101AttachmentContracts, MovingGripperIsRejectedByQ6NotArmQuiescence)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = attachmentContract(
    key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT), profile);
  auto before = world(false, false);
  before.arm_stationary = true;
  before.joint_velocities[profile.gripper_joint] = profile.q6_velocity_tolerance * 1.2;

  const auto result = contract->validatePrecondition(before);

  ASSERT_FALSE(result.ok);
  EXPECT_TRUE(std::any_of(result.failures.begin(), result.failures.end(), [](const auto & failure) {
    return failure.code == "Q6_NOT_STATIONARY";
  }));
  EXPECT_FALSE(
    std::any_of(result.failures.begin(), result.failures.end(),
                [](const auto & failure) { return failure.code == "ARM_NOT_QUIESCENT"; }));
}

TEST(SO101AttachmentContracts, GazeboAttachRejectsMergedContactWithoutBothFingerSides)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = attachmentContract(
    key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT), profile);
  auto before = world(false, false);
  before.gazebo_task_object_gripper_contact = true;
  before.gazebo_task_object_fixed_finger_contact.reset();
  before.gazebo_task_object_moving_jaw_contact.reset();

  const auto result = contract->validatePrecondition(before);

  EXPECT_FALSE(result.ok);
}

TEST(SO101AttachmentContracts, GazeboAttachRejectsEitherSingleSidedContact)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = attachmentContract(
    key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT), profile);
  for (const bool fixed_only : {false, true}) {
    auto before = world(false, false);
    before.gazebo_task_object_fixed_finger_contact = fixed_only;
    before.gazebo_task_object_moving_jaw_contact = !fixed_only;

    const auto result = contract->validatePrecondition(before);

    EXPECT_FALSE(result.ok);
    ASSERT_FALSE(result.failures.empty());
    EXPECT_TRUE(
      std::any_of(result.failures.begin(), result.failures.end(), [](const auto & failure) {
        return failure.code == "BILATERAL_GRIPPER_CONTACT_REQUIRED";
      }));
  }
}

TEST(SO101AttachmentContracts, StableWindowSolverReportedDepthKeepsConservativeLimit)
{
  auto profile = pick_place::SO101Profile::canonical();
  profile.max_gripper_contact_depth = 0.0008;
  const auto contract = attachmentContract(
    key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT), profile);
  auto before = world(false, false);
  before.gazebo_task_object_gripper_max_depth = 0.001260;

  const auto result = contract->validatePrecondition(before);

  EXPECT_FALSE(result.ok);
  const auto failure =
    std::find_if(result.failures.begin(), result.failures.end(), [](const auto & item) {
      return item.code == "GRIPPER_CONTACT_PENETRATION_EXCEEDED";
    });
  ASSERT_NE(failure, result.failures.end());
  EXPECT_DOUBLE_EQ(0.001260,
                   result.metrics.at("gazebo_task_object_gripper_solver_reported_max_depth"));
  EXPECT_DOUBLE_EQ(0.0008, result.metrics.at("stable_solver_reported_depth_limit"));
}

TEST(SO101AttachmentContracts, AcceptsOpposingSurfacesOfTheSameNearWall)
{
  const auto contract =
    attachmentContract(key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT));
  EXPECT_TRUE(contract->validatePrecondition(semanticWallGrasp()).ok);
}

TEST(SO101AttachmentContracts, UsesYamlLocalVerticalBandInsteadOfLegacyWorldHeightBand)
{
  const auto contract =
    attachmentContract(key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT));
  auto snapshot = semanticWallGrasp();
  // These aggregate world heights reproduce the light-cup GUI contact.  The
  // semantic samples are 25 mm below the rim and therefore satisfy the YAML
  // policy regardless of the legacy can-specific world-height defaults.
  snapshot.gazebo_task_object_fixed_contact_min_height = 0.175046;
  snapshot.gazebo_task_object_fixed_contact_max_height = 0.202055;
  snapshot.gazebo_task_object_moving_contact_min_height = 0.175062;
  snapshot.gazebo_task_object_moving_contact_max_height = 0.202169;

  const auto result = contract->validatePrecondition(snapshot);

  EXPECT_TRUE(result.ok) << failureCodes(result);
}

TEST(SO101AttachmentContracts, RejectsEitherMissingFingerAtTheNearWall)
{
  const auto contract =
    attachmentContract(key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT));
  for (const bool remove_fixed : {false, true}) {
    auto snapshot = semanticWallGrasp();
    (remove_fixed ? snapshot.gazebo_task_object_fixed_finger_contacts
                  : snapshot.gazebo_task_object_moving_jaw_contacts)
      .clear();
    EXPECT_FALSE(contract->validatePrecondition(snapshot).ok);
  }
}

TEST(SO101AttachmentContracts, RejectsRimAndBottomContacts)
{
  const auto contract =
    attachmentContract(key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT));
  for (const std::string collision : {"rim", "bottom"}) {
    auto snapshot = semanticWallGrasp();
    snapshot.gazebo_task_object_moving_jaw_contacts.front().task_object_collision = collision;
    EXPECT_FALSE(contract->validatePrecondition(snapshot).ok) << collision;
  }
}

TEST(SO101AttachmentContracts, RejectsNearAndOppositeWallSplit)
{
  const auto contract =
    attachmentContract(key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT));
  auto snapshot = semanticWallGrasp();
  snapshot.gazebo_task_object_moving_jaw_contacts.front().task_object_collision = "wall_opposite";
  EXPECT_FALSE(contract->validatePrecondition(snapshot).ok);
}

TEST(SO101AttachmentContracts, RejectsWrongInsideOutsideNormals)
{
  const auto contract =
    attachmentContract(key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT));
  auto snapshot = semanticWallGrasp();
  snapshot.gazebo_task_object_moving_jaw_contacts.front().normal_toward_finger_task_object.y = 1.0;
  EXPECT_FALSE(contract->validatePrecondition(snapshot).ok);
}

TEST(SO101AttachmentContracts, AcceptsEdgeNormalWhenFingerHasValidSurfaceWitness)
{
  const auto contract =
    attachmentContract(key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT));
  auto snapshot = semanticWallGrasp();
  auto edge_sample = contactSample("wall_near", 1.0, 0.020);
  edge_sample.normal_toward_finger_world = {1.0, 0.0, 0.0};
  edge_sample.normal_toward_finger_task_object = {1.0, 0.0, 0.0};
  snapshot.gazebo_task_object_fixed_finger_contacts.push_back(edge_sample);

  const auto result = contract->validatePrecondition(snapshot);

  EXPECT_TRUE(result.ok) << failureCodes(result);
}

TEST(SO101AttachmentContracts, RejectsSemanticContactDepthAbovePolicyLimit)
{
  const auto contract =
    attachmentContract(key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT));
  auto snapshot = semanticWallGrasp();
  snapshot.gazebo_task_object_moving_jaw_contacts.front().depth = 0.0009;
  EXPECT_FALSE(contract->validatePrecondition(snapshot).ok);
}

TEST(SO101AttachmentContracts, GazeboAttachRejectsCanTopEdgeContact)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = attachmentContract(
    key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT), profile);
  auto before = world(false, false);
  before.gazebo_task_object_moving_jaw_contacts = {
    contactSample("wall_near", -1.0, profile.task_object_height / 2.0 - 0.001)};

  const auto result = contract->validatePrecondition(before);

  EXPECT_FALSE(result.ok);
}

TEST(SO101AttachmentContracts, PostRetreatDetachUsesCurrentDualWorldFacts)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto gazebo_contract = attachmentContract(
    key(pick_place::State::DETACH_GAZEBO, pick_place::State::DETACH_MOVEIT), profile);
  auto before = world(true, true);
  auto after_gazebo = world(false, true);
  before.joint_positions[profile.gripper_joint] = profile.q6_full_open;
  after_gazebo.joint_positions[profile.gripper_joint] = profile.q6_full_open;
  setTaskObjectPose(before, profile.place_task_object_pose);
  setTaskObjectPose(after_gazebo, profile.place_task_object_pose);
  EXPECT_TRUE(gazebo_contract->validate(before, after_gazebo, succeeded()).ok);
  after_gazebo.gazebo_task_object_attached = true;
  EXPECT_FALSE(gazebo_contract->validate(before, after_gazebo, succeeded()).ok);
  after_gazebo = world(false, false);
  after_gazebo.joint_positions[profile.gripper_joint] = profile.q6_full_open;
  EXPECT_FALSE(gazebo_contract->validate(before, after_gazebo, succeeded()).ok);

  const auto moveit_contract = attachmentContract(
    key(pick_place::State::DETACH_MOVEIT, pick_place::State::WAIT_RELEASE_SETTLE), profile);
  before = world(false, true);
  auto after_moveit = world(false, false);
  before.joint_positions[profile.gripper_joint] = profile.q6_full_open;
  after_moveit.joint_positions[profile.gripper_joint] = profile.q6_full_open;
  setTaskObjectPose(before, profile.place_task_object_pose);
  setTaskObjectPose(after_moveit, profile.place_task_object_pose);
  EXPECT_TRUE(moveit_contract->validate(before, after_moveit, succeeded()).ok);
  after_moveit.moveit_world_object_poses.erase(profile.task_object_id);
  EXPECT_FALSE(moveit_contract->validate(before, after_moveit, succeeded()).ok);
}

TEST(SO101AttachmentContracts, MoveItDetachUsesSafeReleaseEnvelopeWithoutFinalTiltGate)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = attachmentContract(
    key(pick_place::State::DETACH_MOVEIT, pick_place::State::WAIT_RELEASE_SETTLE), profile);
  auto before = world(false, true);
  auto after = world(false, false);
  before.joint_positions[profile.gripper_joint] = profile.q6_full_open;
  after.joint_positions[profile.gripper_joint] = profile.q6_full_open;
  const pick_place::Pose3d live_release_pose{
    -0.07489179074764252, -0.25029996037483215, 0.17534954845905304, -0.04800073703704309,
    -0.12080902111287307, -0.20319523606076123, 0.9704704082464405};
  setTaskObjectPose(before, live_release_pose);
  setTaskObjectPose(after, live_release_pose);

  EXPECT_TRUE(contract->validatePrecondition(before).ok);
  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);

  before.gazebo_task_object_pose_world->x =
    profile.place_task_object_pose.x + profile.place_detach_xy_tolerance + 0.001;
  EXPECT_FALSE(contract->validatePrecondition(before).ok);
}

TEST(SO101AttachmentContracts, SyncComparesIndependentGazeboAndMoveItSixDegreePoses)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract =
    attachmentContract(key(pick_place::State::SYNC_WORLD_OBJECT, pick_place::State::DONE), profile);
  auto before = world(false, false);
  auto after = world(false, false);
  before.joint_positions[profile.gripper_joint] = profile.q6_full_open;
  after.joint_positions[profile.gripper_joint] = profile.q6_full_open;
  const auto observed = profile.place_task_object_pose;
  setTaskObjectPose(before, observed);
  setTaskObjectPose(after, observed);
  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);

  after.moveit_world_object_poses[profile.task_object_id].qz =
    std::sin(profile.task_object_orientation_drift_tolerance_rad);
  after.moveit_world_object_poses[profile.task_object_id].qw =
    std::cos(profile.task_object_orientation_drift_tolerance_rad);
  EXPECT_FALSE(contract->validate(before, after, succeeded()).ok);
}

TEST(SO101AttachmentContracts, RecoveryDetachAndSyncAcceptAlreadyConvergedCurrentFacts)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  auto detached = world(false, false);
  detached.joint_positions[profile.gripper_joint] = profile.q6_full_open;
  for (const auto transition : {
         key(pick_place::State::RECOVER_DETACH_GAZEBO, pick_place::State::RECOVER_DETACH_MOVEIT),
         key(pick_place::State::RECOVER_DETACH_MOVEIT,
             pick_place::State::RECOVER_SYNC_WORLD_OBJECT),
         key(pick_place::State::RECOVER_SYNC_WORLD_OBJECT, pick_place::State::RECOVER_RETREAT),
       }) {
    const auto contract = attachmentContract(transition, profile);
    EXPECT_TRUE(contract->validate(detached, detached, succeeded()).ok);
  }
}

TEST(SO101AttachmentContracts, ActionSuccessAloneNeverSatisfiesMissingObservations)
{
  const auto contract =
    attachmentContract(key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT),
                       pick_place::SO101Profile::canonical());
  pick_place::WorldSnapshot empty;
  EXPECT_FALSE(contract->validate(empty, empty, succeeded()).ok);
}

TEST(SO101AttachmentContracts, DetachAllowsBoundedSettlingWhileSyncAndRecoveryRequireNoDrift)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  struct Case
  {
    pick_place::TransitionKey transition;
    pick_place::WorldSnapshot before;
    pick_place::WorldSnapshot after;
    pick_place::Pose3d expected_support;
  };
  std::vector<Case> cases{
    {key(pick_place::State::DETACH_GAZEBO, pick_place::State::DETACH_MOVEIT), world(true, true),
     world(false, true), profile.place_task_object_pose},
    {key(pick_place::State::DETACH_MOVEIT, pick_place::State::WAIT_RELEASE_SETTLE),
     world(false, true), world(false, false), profile.place_task_object_pose},
    {key(pick_place::State::SYNC_WORLD_OBJECT, pick_place::State::DONE), world(false, false),
     world(false, false), profile.place_task_object_pose},
    {key(pick_place::State::RECOVER_DETACH_GAZEBO, pick_place::State::RECOVER_DETACH_MOVEIT),
     world(false, false), world(false, false), profile.task_object_pose},
    {key(pick_place::State::RECOVER_DETACH_MOVEIT, pick_place::State::RECOVER_SYNC_WORLD_OBJECT),
     world(false, false), world(false, false), profile.task_object_pose},
    {key(pick_place::State::RECOVER_SYNC_WORLD_OBJECT, pick_place::State::RECOVER_RETREAT),
     world(false, false), world(false, false), profile.task_object_pose},
  };
  for (auto & test_case : cases) {
    const bool released = test_case.transition.from == pick_place::State::DETACH_GAZEBO ||
                          test_case.transition.from == pick_place::State::DETACH_MOVEIT ||
                          test_case.transition.from == pick_place::State::SYNC_WORLD_OBJECT ||
                          test_case.transition.from == pick_place::State::RECOVER_DETACH_GAZEBO ||
                          test_case.transition.from == pick_place::State::RECOVER_DETACH_MOVEIT ||
                          test_case.transition.from == pick_place::State::RECOVER_SYNC_WORLD_OBJECT;
    for (auto * snapshot : {&test_case.before, &test_case.after}) {
      snapshot->joint_positions[profile.gripper_joint] =
        released ? profile.q6_full_open : profile.q6_contact;
      snapshot->gazebo_task_object_pose_world = test_case.expected_support;
      if (!snapshot->moveit_task_object_attached.value_or(true)) {
        snapshot->moveit_world_object_poses[profile.task_object_id] = test_case.expected_support;
      }
    }
    const auto contract = attachmentContract(test_case.transition, profile);
    ASSERT_TRUE(contract->validate(test_case.before, test_case.after, succeeded()).ok)
      << pick_place::toString(test_case.transition.from);

    const bool forward_detach = test_case.transition.from == pick_place::State::DETACH_GAZEBO ||
                                test_case.transition.from == pick_place::State::DETACH_MOVEIT;
    auto drifted = test_case.after;
    drifted.gazebo_task_object_pose_world->x +=
      forward_detach ? profile.place_support_xy_tolerance * 0.8
                     : profile.task_object_position_drift_tolerance * 2.0;
    if (!drifted.moveit_task_object_attached.value_or(true)) {
      drifted.moveit_world_object_poses[profile.task_object_id] =
        *drifted.gazebo_task_object_pose_world;
    }
    EXPECT_EQ(contract->validate(test_case.before, drifted, succeeded()).ok, forward_detach)
      << pick_place::toString(test_case.transition.from) << " applied the wrong settling invariant";

    auto unsupported_before = test_case.before;
    auto unsupported_after = test_case.after;
    unsupported_before.gazebo_task_object_pose_world->y +=
      forward_detach || test_case.transition.from == pick_place::State::SYNC_WORLD_OBJECT
        ? (forward_detach ? profile.place_detach_xy_tolerance
                          : profile.place_support_xy_tolerance) +
            0.001
        : profile.task_object_position_drift_tolerance * 2.0;
    unsupported_after.gazebo_task_object_pose_world =
      unsupported_before.gazebo_task_object_pose_world;
    if (!unsupported_after.moveit_task_object_attached.value_or(true)) {
      unsupported_after.moveit_world_object_poses[profile.task_object_id] =
        *unsupported_after.gazebo_task_object_pose_world;
    }
    EXPECT_FALSE(contract->validatePrecondition(unsupported_before).ok)
      << pick_place::toString(test_case.transition.from)
      << " accepted unsupported TaskObject precondition";
    EXPECT_FALSE(contract->validate(unsupported_before, unsupported_after, succeeded()).ok)
      << pick_place::toString(test_case.transition.from) << " accepted unsupported TaskObject pose";

    auto nonfinite = test_case.after;
    nonfinite.gazebo_task_object_pose_world->x = std::numeric_limits<double>::quiet_NaN();
    if (!nonfinite.moveit_task_object_attached.value_or(true)) {
      nonfinite.moveit_world_object_poses[profile.task_object_id] =
        *nonfinite.gazebo_task_object_pose_world;
    }
    EXPECT_FALSE(contract->validate(test_case.before, nonfinite, succeeded()).ok)
      << pick_place::toString(test_case.transition.from) << " accepted nonfinite TaskObject pose";
  }
}

TEST(SO101AttachmentContracts, ForwardDetachAcceptsCylindricalYawInsideSupportEnvelope)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = attachmentContract(
    key(pick_place::State::DETACH_GAZEBO, pick_place::State::DETACH_MOVEIT), profile);
  auto before = world(true, true);
  auto after = world(false, true);
  auto supported = profile.place_task_object_pose;
  supported.x += 0.002;
  supported.y -= 0.001;
  supported.z += 0.008;
  supported.qz = std::sin(0.2);
  supported.qw = std::cos(0.2);
  for (auto * snapshot : {&before, &after}) {
    snapshot->joint_positions[profile.gripper_joint] = profile.q6_full_open;
    snapshot->gazebo_task_object_pose_world = supported;
  }

  EXPECT_TRUE(contract->validatePrecondition(before).ok);
  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);

  before.gazebo_task_object_pose_world->x =
    profile.place_task_object_pose.x + profile.place_detach_xy_tolerance + 0.001;
  EXPECT_FALSE(contract->validatePrecondition(before).ok);
}

TEST(SO101AttachmentContracts, ForwardDetachAllowsBoundedHighPoseBeforeStrictlySupportedAfterPose)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = attachmentContract(
    key(pick_place::State::DETACH_GAZEBO, pick_place::State::DETACH_MOVEIT), profile);
  auto before = world(true, true);
  auto after = world(false, true);
  before.joint_positions[profile.gripper_joint] = profile.q6_full_open;
  after.joint_positions[profile.gripper_joint] = profile.q6_full_open;
  before.gazebo_task_object_pose_world = profile.place_task_object_pose;
  before.gazebo_task_object_pose_world->z += 0.010111;
  after.gazebo_task_object_pose_world = profile.place_task_object_pose;

  EXPECT_TRUE(contract->validatePrecondition(before).ok);
  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);
}

TEST(SO101AttachmentContracts, MoveItAttachUsesLatestFreshGazeboPoseAndDerivedRelativePose)
{
  auto snapshot = world(false, false);
  snapshot.gazebo_task_object_pose_world =
    pick_place::Pose3d{0.04, -0.22, 0.19, 0.0, 0.0, 0.0, 1.0};
  snapshot.moveit_gripper_pose_world = pick_place::Pose3d{0.01, -0.20, 0.21, 0.0, 0.0, 0.0, 1.0};
  pick_place::SO101MoveItScenePolicy policy("plastic_cup", false);

  const auto prepared =
    policy.prepare(pick_place_common::ros_adapters::MoveItSceneOperation::ATTACH,
                   {pick_place::State::ATTACH_MOVEIT, pick_place::State::LIFT, snapshot, nullptr});
  const auto derived = pick_place::derivePlanningShadowPose(snapshot);

  EXPECT_FALSE(prepared.failure);
  EXPECT_TRUE(prepared.upsert_before_attach);
  ASSERT_TRUE(prepared.task_object_pose);
  EXPECT_DOUBLE_EQ(snapshot.gazebo_task_object_pose_world->x, prepared.task_object_pose->x);
  ASSERT_TRUE(std::holds_alternative<pick_place::Pose3d>(derived));
  const auto expected = pick_place::relativePose(*snapshot.moveit_gripper_pose_world,
                                                 *snapshot.gazebo_task_object_pose_world);
  ASSERT_TRUE(expected);
  EXPECT_NEAR(0.0, pick_place::positionDistance(std::get<pick_place::Pose3d>(derived), *expected),
              1e-12);
}

TEST(SO101AttachmentContracts, NormalForwardCarryRequiresGazeboDetached)
{
  auto snapshot = world(true, true);
  snapshot.moveit_task_object_attached_relative_pose = snapshot.gazebo_task_object_pose_world;

  const auto result = pick_place::evaluatePlanningShadowDivergence(
    snapshot, physicalOutcomePolicy(), pick_place::State::LIFT);

  EXPECT_FALSE(result.ok);
  EXPECT_NE(std::string::npos, failureCodes(result).find("GAZEBO_FORWARD_ATTACHMENT_FORBIDDEN"));
}

TEST(SO101AttachmentContracts, PreservesForbiddenCollisionAndPenetrationCeilings)
{
  const auto contract =
    attachmentContract(key(pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT));
  auto forbidden = semanticWallGrasp();
  forbidden.gazebo_task_object_fixed_finger_contacts.front().task_object_collision = "bottom";
  auto penetrated = semanticWallGrasp();
  penetrated.gazebo_task_object_moving_jaw_contacts.front().depth =
    testContactPolicy().max_penetration_m * 2.0;

  EXPECT_FALSE(contract->validatePrecondition(forbidden).ok);
  EXPECT_FALSE(contract->validatePrecondition(penetrated).ok);
}

TEST(SO101AttachmentContracts, MoveItAttachTreatsBoundedRegraspQ6AsTelemetry)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract =
    attachmentContract(key(pick_place::State::ATTACH_MOVEIT, pick_place::State::LIFT), profile);
  auto before = semanticWallGrasp();
  before.joint_positions[profile.gripper_joint] =
    profile.q6_contact - profile.q6_regrasp_squeeze_offset;
  before.moveit_gripper_pose_world = pick_place::Pose3d{};
  auto after = world(false, true);
  after.joint_positions[profile.gripper_joint] = before.joint_positions.at(profile.gripper_joint);
  after.moveit_gripper_pose_world = pick_place::Pose3d{};
  after.moveit_task_object_attached_relative_pose = before.gazebo_task_object_pose_world;

  const auto precondition = contract->validatePrecondition(before);
  const auto postcondition = contract->validate(before, after, succeeded());

  EXPECT_TRUE(precondition.ok) << failureCodes(precondition);
  EXPECT_TRUE(postcondition.ok) << failureCodes(postcondition);
  EXPECT_DOUBLE_EQ(-profile.q6_regrasp_squeeze_offset,
                   precondition.metrics.at("q6_controller_error"));

  before.gazebo_task_object_gripper_max_depth = profile.max_gripper_contact_depth + 1e-6;
  EXPECT_FALSE(contract->validatePrecondition(before).ok);
  before.gazebo_task_object_gripper_max_depth = profile.max_gripper_contact_depth;
  after.gazebo_task_object_gripper_max_depth = profile.max_gripper_contact_depth + 1e-6;
  EXPECT_FALSE(contract->validate(before, after, succeeded()).ok);
  after.gazebo_task_object_gripper_max_depth = profile.max_gripper_contact_depth;
  before.joint_positions[profile.gripper_joint] = std::numeric_limits<double>::quiet_NaN();
  EXPECT_FALSE(contract->validatePrecondition(before).ok);
}

TEST(SO101AttachmentContracts, ShadowDivergenceWithinLimitIsTelemetry)
{
  auto snapshot = world(false, true);
  snapshot.moveit_task_object_attached_relative_pose = snapshot.gazebo_task_object_pose_world;
  snapshot.moveit_task_object_attached_relative_pose->x += 0.005;

  const auto result = pick_place::evaluatePlanningShadowDivergence(
    snapshot, physicalOutcomePolicy(), pick_place::State::LIFT);

  EXPECT_TRUE(result.ok) << failureCodes(result);
  EXPECT_DOUBLE_EQ(0.005, result.metrics.at("planning_shadow_position_divergence_m"));
}

TEST(SO101AttachmentContracts, ShadowDivergenceAtLimitFailsPlanningValidity)
{
  auto snapshot = world(false, true);
  snapshot.moveit_task_object_attached_relative_pose = snapshot.gazebo_task_object_pose_world;
  snapshot.moveit_task_object_attached_relative_pose->x += 0.01;

  const auto result = pick_place::evaluatePlanningShadowDivergence(
    snapshot, physicalOutcomePolicy(), pick_place::State::LIFT);

  EXPECT_FALSE(result.ok);
  EXPECT_NE(std::string::npos, failureCodes(result).find("PLANNING_SHADOW_DIVERGENCE"));
}

TEST(SO101AttachmentContracts, ReleaseStatesTreatFiniteShadowTiltAsTelemetryOnly)
{
  auto snapshot = world(false, true);
  snapshot.moveit_task_object_attached_relative_pose = snapshot.gazebo_task_object_pose_world;
  const double half_tilt = 0.1;
  snapshot.moveit_task_object_attached_relative_pose->qx = std::sin(half_tilt);
  snapshot.moveit_task_object_attached_relative_pose->qy = 0.0;
  snapshot.moveit_task_object_attached_relative_pose->qz = 0.0;
  snapshot.moveit_task_object_attached_relative_pose->qw = std::cos(half_tilt);

  const auto descend = pick_place::evaluatePlanningShadowDivergence(
    snapshot, physicalOutcomePolicy(), pick_place::State::DESCEND_TO_PLACE);
  const auto retreat = pick_place::evaluatePlanningShadowDivergence(
    snapshot, physicalOutcomePolicy(), pick_place::State::RETREAT);
  const auto lift = pick_place::evaluatePlanningShadowDivergence(snapshot, physicalOutcomePolicy(),
                                                                 pick_place::State::LIFT);

  EXPECT_TRUE(descend.ok) << failureCodes(descend);
  EXPECT_TRUE(retreat.ok) << failureCodes(retreat);
  EXPECT_FALSE(lift.ok);
  EXPECT_GT(descend.metrics.at("planning_shadow_orientation_divergence_rad"), 0.1);
  EXPECT_DOUBLE_EQ(0.0, descend.metrics.at("planning_shadow_orientation_enforced"));
  EXPECT_DOUBLE_EQ(1.0, lift.metrics.at("planning_shadow_orientation_enforced"));

  snapshot.moveit_task_object_attached_relative_pose->x +=
    *physicalOutcomePolicy().planning_shadow.max_position_divergence_m;
  const auto position_diverged = pick_place::evaluatePlanningShadowDivergence(
    snapshot, physicalOutcomePolicy(), pick_place::State::DESCEND_TO_PLACE);
  EXPECT_FALSE(position_diverged.ok);
  EXPECT_NE(std::string::npos, failureCodes(position_diverged).find("PLANNING_SHADOW_DIVERGENCE"));
}

TEST(SO101AttachmentContracts, FinalSyncUsesFrozenFinalGazeboPose)
{
  pick_place::InMemoryFinalPlacementEvidenceStore evidence;
  const pick_place::ReleaseEpoch epoch{"release", "session", 10};
  ASSERT_FALSE(evidence.beginEpoch(epoch));
  pick_place::FinalPlacementEvaluation evaluation;
  evaluation.stable = true;
  const pick_place::Pose3d final_pose{-0.07, -0.31, 0.165, 0.0, 0.0, 0.0, 1.0};
  evaluation.evidence = pick_place::FinalPlacementEvidence{epoch, 11, 14, final_pose, 3, 0.2};
  ASSERT_FALSE(evidence.recordEvaluation(evaluation));
  pick_place::SO101MoveItScenePolicy policy("plastic_cup", false, &evidence);
  auto snapshot = world(false, false);
  snapshot.gazebo_task_object_pose_world->x = 0.5;

  const auto prepared = policy.prepare(
    pick_place_common::ros_adapters::MoveItSceneOperation::SYNC,
    {pick_place::State::SYNC_WORLD_OBJECT, pick_place::State::DONE, snapshot, nullptr});

  ASSERT_FALSE(prepared.failure);
  ASSERT_TRUE(prepared.task_object_pose);
  EXPECT_DOUBLE_EQ(final_pose.x, prepared.task_object_pose->x);
  EXPECT_DOUBLE_EQ(final_pose.y, prepared.task_object_pose->y);
}
