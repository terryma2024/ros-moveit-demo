#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <memory>

#include "so101_gazebo_demo/pick_place/follow_joint_trajectory_gripper_adapter.hpp"
#include "so101_gazebo_demo/pick_place/so101_gripper_validation.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

namespace
{

class FakeTrajectoryClient final : public pick_place::ITrajectoryActionClient
{
public:
  pick_place::ActionResult send(const pick_place::SingleJointTrajectoryGoal & goal,
                                double timeout_seconds) override
  {
    ++send_calls;
    last_goal = goal;
    last_timeout = timeout_seconds;
    return send_result;
  }

  pick_place::ActionResult cancelAndWait(double timeout_seconds) override
  {
    ++cancel_calls;
    last_timeout = timeout_seconds;
    return cancel_result;
  }

  pick_place::ActionResult send_result{pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  pick_place::ActionResult cancel_result{pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  pick_place::SingleJointTrajectoryGoal last_goal;
  int send_calls{0};
  int cancel_calls{0};
  double last_timeout{0.0};
};

pick_place::WorldSnapshot q6Snapshot(double position, double velocity)
{
  pick_place::WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.joint_positions.emplace("6", position);
  snapshot.joint_velocities.emplace("6", velocity);
  return snapshot;
}

}  // namespace

TEST(SO101Profile, OwnsExactRobotSceneAndAttachmentContract)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  EXPECT_EQ("world", profile.world_frame);
  EXPECT_EQ("arm", profile.planning_group);
  EXPECT_EQ("so101_tcp", profile.tcp_link);
  EXPECT_EQ((std::vector<std::string>{"1", "2", "3", "4", "5"}), profile.arm_joints);
  EXPECT_EQ("6", profile.gripper_joint);
  EXPECT_EQ("/gripper_controller/follow_joint_trajectory", profile.gripper_action);
  EXPECT_EQ("gripper", profile.moveit_attach_link);
  EXPECT_EQ((std::vector<std::string>{"gripper", "jaw"}), profile.moveit_touch_links);
  EXPECT_DOUBLE_EQ(0.795386732, profile.q6_preopen);
  EXPECT_DOUBLE_EQ(0.662818811, profile.q6_contact);
  EXPECT_DOUBLE_EQ(0.020, profile.grasp_section_depth);
  EXPECT_DOUBLE_EQ(0.50, profile.table_size[0]);
  EXPECT_DOUBLE_EQ(0.60, profile.table_size[1]);
  EXPECT_DOUBLE_EQ(0.04, profile.table_size[2]);
  EXPECT_DOUBLE_EQ(0.033, profile.coke_radius);
  EXPECT_DOUBLE_EQ(0.122, profile.coke_height);
  EXPECT_EQ("/so101/coke_attached", profile.attachment_state_topic);
}

TEST(SO101GripperGeometry, UsesTwentyMillimeterSectionCalibrationForBothTargets)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  EXPECT_NEAR(0.076, pick_place::gripperWidthAtSection(profile.q6_preopen, profile), 2e-9);
  EXPECT_NEAR(0.066, pick_place::gripperWidthAtSection(profile.q6_contact, profile), 2e-9);
}

TEST(SO101GripperGeometry, MatchesRealMeshTruthAtNonEndpointAndRejectsExtrapolation)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  constexpr double midpoint_q6 = 0.685006841;
  constexpr double mesh_truth_width = 0.0679670145369185;

  // The runtime linearly interpolates an 80-sample table.  Bound interpolation
  // error to 0.1 micrometre at a point that is not itself a table sample.
  EXPECT_NEAR(mesh_truth_width, pick_place::gripperWidthAtSection(midpoint_q6, profile), 1e-7);
  EXPECT_TRUE(std::isnan(
    pick_place::gripperWidthAtSection(profile.q6_contact - profile.q6_tolerance - 1e-6,
                                      profile)));
}

TEST(SO101GripperGeometry, ClampsOnlyFloatingPointNoiseAtCalibrationEndpoints)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  EXPECT_NEAR(0.066,
              pick_place::gripperWidthAtSection(profile.q6_contact - 5e-10, profile), 2e-9);
  EXPECT_NEAR(0.076,
              pick_place::gripperWidthAtSection(profile.q6_preopen + 1.5e-8, profile), 2e-9);
  EXPECT_TRUE(std::isnan(
    pick_place::gripperWidthAtSection(profile.q6_contact - 2e-6, profile)));
  EXPECT_TRUE(std::isnan(
    pick_place::gripperWidthAtSection(profile.q6_preopen + 2e-6, profile)));
}

TEST(SO101GripperValidation, RejectsWidthAndGeometryModelIndependentlyOfExactQ6)
{
  const auto & canonical = pick_place::SO101Profile::canonical();
  const auto current = q6Snapshot(canonical.q6_contact, 0.0);
  const auto wrong_width = pick_place::validateQ6Target(
    current, canonical.q6_contact,
    canonical.contact_width + canonical.width_tolerance * 2.0, canonical);
  EXPECT_FALSE(wrong_width.ok);
  EXPECT_TRUE(std::any_of(
    wrong_width.failures.begin(), wrong_width.failures.end(),
    [](const auto & failure) { return failure.code == "Q6_WIDTH_OUT_OF_TOLERANCE"; }));

  auto mismatched_model = canonical;
  mismatched_model.gripper_geometry_model_fingerprint = "wrong-mesh-or-urdf";
  const auto mismatch = pick_place::validateQ6Target(
    current, mismatched_model.q6_contact, mismatched_model.contact_width, mismatched_model);
  EXPECT_FALSE(mismatch.ok);
  EXPECT_TRUE(std::any_of(
    mismatch.failures.begin(), mismatch.failures.end(),
    [](const auto & failure) { return failure.code == "Q6_GEOMETRY_MODEL_MISMATCH"; }));
}

TEST(SO101GripperValidation, AcceptsOnlyFreshFiniteStoppedQ6Evidence)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  auto snapshot = q6Snapshot(profile.q6_contact, 0.0);
  EXPECT_TRUE(pick_place::validateQ6Target(snapshot, profile.q6_contact, 0.066, profile).ok);

  snapshot.fresh = false;
  EXPECT_FALSE(pick_place::validateQ6Target(snapshot, profile.q6_contact, 0.066, profile).ok);
  snapshot = q6Snapshot(profile.q6_contact, 0.1);
  EXPECT_FALSE(pick_place::validateQ6Target(snapshot, profile.q6_contact, 0.066, profile).ok);
  snapshot = {};
  snapshot.fresh = true;
  snapshot.joint_positions.emplace("panda_finger_joint1", 0.04);
  snapshot.joint_velocities.emplace("panda_finger_joint1", 0.0);
  EXPECT_FALSE(pick_place::validateQ6Target(snapshot, profile.q6_contact, 0.066, profile).ok);
}

TEST(FollowJointTrajectoryGripperAdapter, SendsOnlyJointSixWithExactTargetAndDuration)
{
  auto client = std::make_shared<FakeTrajectoryClient>();
  pick_place::FollowJointTrajectoryGripperAdapter adapter(client, 0.75, 2.0);

  const auto result = adapter.command(pick_place::SO101Profile::canonical().q6_preopen);

  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, result.status);
  ASSERT_EQ(1, client->send_calls);
  EXPECT_EQ((std::vector<std::string>{"6"}), client->last_goal.joint_names);
  EXPECT_EQ((std::vector<double>{0.795386732}), client->last_goal.positions);
  EXPECT_DOUBLE_EQ(0.75, client->last_goal.duration_seconds);
  EXPECT_DOUBLE_EQ(2.0, client->last_timeout);
}

TEST(FollowJointTrajectoryGripperAdapter, PropagatesAbortTimeoutAndCancel)
{
  auto client = std::make_shared<FakeTrajectoryClient>();
  pick_place::FollowJointTrajectoryGripperAdapter adapter(client, 0.75, 2.0);
  client->send_result = {pick_place::ActionStatus::FAILED,
                         pick_place::Failure{pick_place::FailureCategory::GRIPPER,
                                             "GRIPPER_ACTION_ABORTED",
                                             "aborted",
                                             {}}};
  EXPECT_EQ(pick_place::ActionStatus::FAILED, adapter.command(0.5).status);
  client->send_result = {pick_place::ActionStatus::TIMED_OUT,
                         pick_place::Failure{pick_place::FailureCategory::GRIPPER,
                                             "GRIPPER_RESULT_TIMEOUT",
                                             "timeout",
                                             {}}};
  EXPECT_EQ(pick_place::ActionStatus::TIMED_OUT, adapter.command(0.5).status);
  client->cancel_result = {pick_place::ActionStatus::CANCELLED,
                           pick_place::Failure{pick_place::FailureCategory::GRIPPER,
                                               "GRIPPER_GOAL_CANCELLED",
                                               "cancelled",
                                               {}}};
  EXPECT_EQ(pick_place::ActionStatus::CANCELLED, adapter.cancelAndWait().status);
  EXPECT_EQ(1, client->cancel_calls);
}
