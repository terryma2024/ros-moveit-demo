#include <limits>
#include <memory>

#include <Eigen/Geometry>
#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/so101_joint_motion_adapter.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

spp::Pose3d tablePose()
{
  return {0.0, -0.20, 0.10, 0.0, 0.0, 0.0, 1.0};
}

spp::Pose3d pickPose()
{
  return {0.02, -0.28, 0.181, 0.0, 0.0, 0.0, 1.0};
}

spp::Pose3d graspRelativePose()
{
  return {0.0214000012, -0.0000000417348703, -0.124949,
          -0.000000365, 0.000000355, 0.717237013, 0.696829296};
}

spp::Pose3d compose(const spp::Pose3d & parent, const spp::Pose3d & child)
{
  const Eigen::Quaterniond q_parent(parent.qw, parent.qx, parent.qy, parent.qz);
  const Eigen::Quaterniond q_child(child.qw, child.qx, child.qy, child.qz);
  const Eigen::Vector3d translated =
    Eigen::Vector3d(parent.x, parent.y, parent.z) +
    q_parent.normalized() * Eigen::Vector3d(child.x, child.y, child.z);
  const Eigen::Quaterniond q = (q_parent.normalized() * q_child.normalized()).normalized();
  return {translated.x(), translated.y(), translated.z(), q.x(), q.y(), q.z(), q.w()};
}

class FakeBoundary final : public spp::IJointPlanningBoundary,
                           public spp::IRobotStateEvidenceProvider
{
public:
  std::optional<spp::CurrentJointStateEvidence> currentState() override
  {
    ++current_state_calls;
    return current;
  }
  std::optional<spp::MotionPlanningSceneFacts> sceneFacts() override
  {
    ++scene_fact_calls;
    return scene;
  }
  spp::JointSegmentPlanResult planSegment(const std::vector<std::string> & names,
                                          const std::vector<double> & start,
                                          const std::vector<double> & goal,
                                          const std::set<std::string> & allowed_touch_pairs,
                                          const std::optional<spp::TemporalContactPolicy> &,
                                          double gripper_position) override
  {
    ++plan_calls;
    starts.push_back(start);
    goals.push_back(goal);
    allowed_pairs.push_back(allowed_touch_pairs);
    gripper_positions.push_back(gripper_position);
    spp::JointSegmentPlan segment;
    segment.joint_names = names;
    segment.moveit_success = true;
    segment.moveit_error_code = 1;
    segment.planner_id = "RRTConnectkConfigDefault";
    segment.collision_aware = true;
    auto reported_start = start;
    if (wrong_segment_start) reported_start[0] += 0.01;
    const double origin = offset_segment_timestamps ? 4.0 : 0.0;
    segment.points = {{reported_start, origin}, {goal, origin + 1.0}};
    return {{spp::ActionStatus::SUCCEEDED, std::nullopt}, segment};
  }
  std::optional<spp::RobotStateEvidence>
  evaluate(const std::vector<std::string> &, const std::vector<double> & positions,
           const std::set<std::string> &,
           const std::optional<spp::TemporalContactPolicy> &, double) const override
  {
    return spp::RobotStateEvidence{{positions[0], positions[1], 0.3 - positions[2], 0, 0, 0, 1},
                                   true};
  }

  spp::CurrentJointStateEvidence current{{"1", "2", "3", "4", "5"},
                                         {0, 0, 0, 0, 0}, 1234};
  spp::MotionPlanningSceneFacts scene{true, true, false, std::nullopt, {},
                                      tablePose(), pickPose(), std::nullopt, std::nullopt};
  int plan_calls{0};
  int current_state_calls{0};
  int scene_fact_calls{0};
  bool wrong_segment_start{false};
  bool offset_segment_timestamps{false};
  std::vector<std::vector<double>> starts;
  std::vector<std::vector<double>> goals;
  std::vector<std::set<std::string>> allowed_pairs;
  std::vector<double> gripper_positions;
};

spp::ObservationResult observation(double q6 = 0.707194871, double velocity = 0.0)
{
  spp::WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.arm_stationary = true;
  snapshot.joint_positions.emplace("6", q6);
  snapshot.joint_velocities.emplace("6", velocity);
  snapshot.gazebo_coke_pose_world = pickPose();
  snapshot.gazebo_coke_attached = false;
  snapshot.gazebo_coke_stationary = true;
  return {snapshot, std::nullopt};
}

spp::ObservationResult carryingObservation()
{
  auto result = observation(0.662818811, 0.0);
  const spp::Pose3d gripper{0.25, -0.10, 0.40, 0.0, 0.0, 0.0, 1.0};
  result.snapshot->gazebo_coke_pose_world = compose(gripper, graspRelativePose());
  result.snapshot->gazebo_coke_attached = true;
  return result;
}

spp::MotionPlanningSceneFacts carryingScene()
{
  return {true, false, true, std::string("gripper"), {"gripper", "jaw"},
          tablePose(), std::nullopt, graspRelativePose(),
          spp::Pose3d{0.25, -0.10, 0.40, 0.0, 0.0, 0.0, 1.0}};
}

spp::JointMotionRequest goalRequest()
{
  return {spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND,
          {"1", "2", "3", "4", "5"}, {{0.1, 0.2, 0.3, 0.4, 0.5}}, false, false,
          {}, 0.707194871};
}

}  // namespace

TEST(SO101JointMotionAdapter, RejectsMissingNonfiniteMovingOrWrongQ6BeforeAnyBoundaryCall)
{
  const auto nan = std::numeric_limits<double>::quiet_NaN();
  for (const int mutation : {0, 1, 2, 3, 4}) {
    auto boundary = std::make_shared<FakeBoundary>();
    auto observed = observation();
    if (mutation == 0) observed.snapshot->joint_positions.erase("6");
    if (mutation == 1) observed.snapshot->joint_velocities.erase("6");
    if (mutation == 2) observed.snapshot->joint_positions["6"] = nan;
    if (mutation == 3) observed.snapshot->joint_velocities["6"] = 0.02;
    if (mutation == 4) observed.snapshot->joint_positions["6"] = 0.662818811;

    spp::ProfiledJointMotionAdapter adapter(boundary, boundary);
    const auto result = adapter.plan(goalRequest(), observed);

    ASSERT_EQ(result.action.status, spp::ActionStatus::FAILED) << mutation;
    ASSERT_TRUE(result.action.failure) << mutation;
    EXPECT_TRUE(result.action.failure->category == spp::FailureCategory::OBSERVATION ||
                result.action.failure->category == spp::FailureCategory::PRECONDITION) << mutation;
    EXPECT_EQ(boundary->scene_fact_calls, 0) << mutation;
    EXPECT_EQ(boundary->current_state_calls, 0) << mutation;
    EXPECT_EQ(boundary->plan_calls, 0) << mutation;
  }
}

TEST(SO101JointMotionAdapter, PassesObservedQ6RatherThanAnExpectedFallbackIntoPlanning)
{
  auto boundary = std::make_shared<FakeBoundary>();
  auto request = goalRequest();
  request.gripper_position = 0.662818811;
  spp::ProfiledJointMotionAdapter adapter(boundary, boundary);

  const auto result = adapter.plan(request, observation(0.662818811, 0.0));

  ASSERT_EQ(result.action.status, spp::ActionStatus::SUCCEEDED);
  ASSERT_EQ(boundary->gripper_positions.size(), 1U);
  EXPECT_DOUBLE_EQ(boundary->gripper_positions.front(), 0.662818811);
}

TEST(SO101JointMotionAdapter, PlansGoalFromObservedCurrentStateAndBuildsEvidence)
{
  auto boundary = std::make_shared<FakeBoundary>();
  spp::ProfiledJointMotionAdapter adapter(boundary, boundary);
  const auto result = adapter.plan(goalRequest(), observation());

  EXPECT_EQ(result.action.status, spp::ActionStatus::SUCCEEDED);
  ASSERT_TRUE(result.artifact);
  const auto artifact = std::dynamic_pointer_cast<const spp::MotionPlanArtifact>(result.artifact);
  ASSERT_TRUE(artifact);
  EXPECT_EQ(boundary->plan_calls, 1);
  EXPECT_EQ(boundary->starts[0], (std::vector<double>{0, 0, 0, 0, 0}));
  EXPECT_EQ(artifact->start_state_stamp_nanoseconds, 1234U);
  EXPECT_EQ(artifact->goal_joint_positions,
            (std::vector<double>{0.1, 0.2, 0.3, 0.4, 0.5}));
}

TEST(SO101JointMotionAdapter, RejectsWrongDetachedSceneBeforePlanning)
{
  auto boundary = std::make_shared<FakeBoundary>();
  boundary->scene.coke_in_world = false;
  spp::ProfiledJointMotionAdapter adapter(boundary, boundary);
  const auto result = adapter.plan(goalRequest(), observation());

  EXPECT_EQ(result.action.status, spp::ActionStatus::FAILED);
  ASSERT_TRUE(result.action.failure);
  EXPECT_EQ(result.action.failure->category, spp::FailureCategory::OBSERVATION);
  EXPECT_EQ(result.action.failure->code, "DETACHED_ENVIRONMENT_OBSERVATION_INVALID");
  EXPECT_EQ(boundary->plan_calls, 0);
}

TEST(SO101JointMotionAdapter, RejectsWrongCarryingAttachmentBeforePlanning)
{
  auto boundary = std::make_shared<FakeBoundary>();
  boundary->scene = carryingScene();
  boundary->scene.attached_link = "wrong_link";
  auto request = goalRequest();
  request.state = spp::State::LIFT;
  request.carrying = true;
  request.gripper_position = 0.662818811;
  spp::ProfiledJointMotionAdapter adapter(boundary, boundary);
  const auto result = adapter.plan(request, carryingObservation());

  EXPECT_EQ(result.action.status, spp::ActionStatus::FAILED);
  ASSERT_TRUE(result.action.failure);
  EXPECT_EQ(result.action.failure->category, spp::FailureCategory::OBSERVATION);
  EXPECT_EQ(result.action.failure->code, "CARRYING_ENVIRONMENT_OBSERVATION_INVALID");
  EXPECT_EQ(boundary->plan_calls, 0);
}

TEST(SO101JointMotionAdapter, StitchesLadderWithoutDuplicateBoundaryAndWithIncreasingTime)
{
  auto boundary = std::make_shared<FakeBoundary>();
  boundary->offset_segment_timestamps = true;
  auto request = goalRequest();
  request.ladder = true;
  request.joint_waypoints = {{0.05, 0.05, 0.05, 0.05, 0.05},
                             {0.10, 0.10, 0.10, 0.10, 0.10}};
  spp::ProfiledJointMotionAdapter adapter(boundary, boundary);
  const auto result = adapter.plan(request, observation());
  const auto artifact = std::dynamic_pointer_cast<const spp::MotionPlanArtifact>(result.artifact);

  ASSERT_TRUE(artifact);
  EXPECT_EQ(boundary->plan_calls, 2);
  ASSERT_EQ(artifact->samples.size(), 3U);
  EXPECT_LT(artifact->samples[0].time_from_start_seconds,
            artifact->samples[1].time_from_start_seconds);
  EXPECT_LT(artifact->samples[1].time_from_start_seconds,
            artifact->samples[2].time_from_start_seconds);
  EXPECT_EQ(boundary->starts[1], request.joint_waypoints[0]);
}

TEST(SO101JointMotionAdapter, AcceptsExactCarryingAttachmentFacts)
{
  auto boundary = std::make_shared<FakeBoundary>();
  boundary->scene = carryingScene();
  auto request = goalRequest();
  request.state = spp::State::LIFT;
  request.carrying = true;
  request.gripper_position = 0.662818811;
  spp::ProfiledJointMotionAdapter adapter(boundary, boundary);
  EXPECT_EQ(adapter.plan(request, carryingObservation()).action.status,
            spp::ActionStatus::SUCCEEDED);
  EXPECT_EQ(boundary->plan_calls, 1);
}


TEST(SO101JointMotionAdapter, RejectsMovedDetachedCokeAndMoveItGazeboWorldMismatch)
{
  for (const int mutation : {0, 1}) {
    auto boundary = std::make_shared<FakeBoundary>();
    auto observed = observation();
    if (mutation == 0) observed.snapshot->gazebo_coke_pose_world->x += 0.02;
    if (mutation == 1) boundary->scene.coke_world_pose->y += 0.02;
    spp::ProfiledJointMotionAdapter adapter(boundary, boundary);
    const auto result = adapter.plan(goalRequest(), observed);
    ASSERT_EQ(result.action.status, spp::ActionStatus::FAILED) << mutation;
    ASSERT_TRUE(result.action.failure) << mutation;
    EXPECT_EQ(result.action.failure->category, spp::FailureCategory::OBSERVATION) << mutation;
    EXPECT_EQ(boundary->plan_calls, 0) << mutation;
  }
}

TEST(SO101JointMotionAdapter, RejectsBadAttachedRelativeOrientationBeforePlanning)
{
  auto boundary = std::make_shared<FakeBoundary>();
  boundary->scene = carryingScene();
  boundary->scene.attached_relative_pose->qx = 0.0;
  boundary->scene.attached_relative_pose->qy = 0.0;
  boundary->scene.attached_relative_pose->qz = 0.0;
  boundary->scene.attached_relative_pose->qw = 1.0;
  auto request = goalRequest();
  request.state = spp::State::LIFT;
  request.carrying = true;
  request.gripper_position = 0.662818811;
  spp::ProfiledJointMotionAdapter adapter(boundary, boundary);
  const auto result = adapter.plan(request, carryingObservation());
  ASSERT_EQ(result.action.status, spp::ActionStatus::FAILED);
  ASSERT_TRUE(result.action.failure);
  EXPECT_EQ(result.action.failure->category, spp::FailureCategory::OBSERVATION);
  EXPECT_EQ(boundary->plan_calls, 0);
}

TEST(SO101JointMotionAdapter, RejectsMissingSixDegreeSceneFactsBeforePlanning)
{
  for (const int mutation : {0, 1, 2, 3, 4}) {
    auto boundary = std::make_shared<FakeBoundary>();
    auto observed = observation();
    if (mutation == 0) boundary->scene.table_world_pose.reset();
    if (mutation == 1) boundary->scene.coke_world_pose.reset();
    if (mutation == 2) observed.snapshot->gazebo_coke_pose_world.reset();
    if (mutation >= 3) {
      boundary->scene = carryingScene();
      observed = carryingObservation();
      if (mutation == 3) boundary->scene.attached_relative_pose.reset();
      if (mutation == 4) boundary->scene.current_gripper_pose_world.reset();
    }
    auto request = goalRequest();
    if (mutation >= 3) {
      request.state = spp::State::LIFT;
      request.carrying = true;
      request.gripper_position = 0.662818811;
    }
    spp::ProfiledJointMotionAdapter adapter(boundary, boundary);
    const auto result = adapter.plan(request, observed);
    ASSERT_EQ(result.action.status, spp::ActionStatus::FAILED) << mutation;
    ASSERT_TRUE(result.action.failure) << mutation;
    EXPECT_EQ(result.action.failure->category, spp::FailureCategory::OBSERVATION) << mutation;
    EXPECT_EQ(boundary->plan_calls, 0) << mutation;
  }
}

TEST(SO101JointMotionAdapter, RejectsSegmentWhoseFirstPointDoesNotMatchRequestedStart)
{
  auto boundary = std::make_shared<FakeBoundary>();
  boundary->wrong_segment_start = true;
  spp::ProfiledJointMotionAdapter adapter(boundary, boundary);
  const auto result = adapter.plan(goalRequest(), observation());
  EXPECT_EQ(result.action.status, spp::ActionStatus::FAILED);
  ASSERT_TRUE(result.action.failure);
  EXPECT_EQ(result.action.failure->code, "SEGMENT_START_JOINT_MISMATCH");
}
