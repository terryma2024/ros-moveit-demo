#include <memory>

#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/so101_joint_motion_adapter.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

class FakeBoundary final : public spp::IJointPlanningBoundary,
                           public spp::IRobotStateEvidenceProvider
{
public:
  std::optional<spp::CurrentJointStateEvidence> currentState() override { return current; }
  std::optional<spp::MotionPlanningSceneFacts> sceneFacts() override { return scene; }
  spp::JointSegmentPlanResult planSegment(const std::vector<std::string> & names,
                                          const std::vector<double> & start,
                                          const std::vector<double> & goal) override
  {
    ++plan_calls;
    starts.push_back(start);
    goals.push_back(goal);
    spp::JointSegmentPlan segment;
    segment.joint_names = names;
    segment.moveit_success = true;
    segment.moveit_error_code = 1;
    segment.planner_id = "RRTConnectkConfigDefault";
    segment.collision_aware = true;
    auto reported_start = start;
    if (wrong_segment_start) reported_start[0] += 0.01;
    segment.points = {{reported_start, 0.0}, {goal, 1.0}};
    return {{spp::ActionStatus::SUCCEEDED, std::nullopt}, segment};
  }
  std::optional<spp::RobotStateEvidence>
  evaluate(const std::vector<std::string> &, const std::vector<double> & positions) const override
  {
    return spp::RobotStateEvidence{{positions[0], positions[1], 0.3 - positions[2], 0, 0, 0, 1},
                                   true};
  }

  spp::CurrentJointStateEvidence current{{"1", "2", "3", "4", "5"},
                                         {0, 0, 0, 0, 0}, 1234};
  spp::MotionPlanningSceneFacts scene{true, true, false, std::nullopt, {}};
  int plan_calls{0};
  bool wrong_segment_start{false};
  std::vector<std::vector<double>> starts;
  std::vector<std::vector<double>> goals;
};

spp::ObservationResult observation()
{
  spp::WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.arm_stationary = true;
  return {snapshot, std::nullopt};
}

spp::JointMotionRequest goalRequest()
{
  return {spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND,
          {"1", "2", "3", "4", "5"}, {{0.1, 0.2, 0.3, 0.4, 0.5}}, false, false};
}

}  // namespace

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
  EXPECT_EQ(result.action.failure->category, spp::FailureCategory::MOVEIT_SCENE);
  EXPECT_EQ(result.action.failure->code, "DETACHED_PLANNING_SCENE_INVALID");
  EXPECT_EQ(boundary->plan_calls, 0);
}

TEST(SO101JointMotionAdapter, RejectsWrongCarryingAttachmentBeforePlanning)
{
  auto boundary = std::make_shared<FakeBoundary>();
  boundary->scene = {true, false, true, std::string("wrong_link"), {"gripper", "jaw"}};
  auto request = goalRequest();
  request.state = spp::State::LIFT;
  request.carrying = true;
  spp::ProfiledJointMotionAdapter adapter(boundary, boundary);
  const auto result = adapter.plan(request, observation());

  EXPECT_EQ(result.action.status, spp::ActionStatus::FAILED);
  ASSERT_TRUE(result.action.failure);
  EXPECT_EQ(result.action.failure->category, spp::FailureCategory::MOVEIT_SCENE);
  EXPECT_EQ(result.action.failure->code, "CARRYING_PLANNING_SCENE_INVALID");
  EXPECT_EQ(boundary->plan_calls, 0);
}

TEST(SO101JointMotionAdapter, StitchesLadderWithoutDuplicateBoundaryAndWithIncreasingTime)
{
  auto boundary = std::make_shared<FakeBoundary>();
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
  boundary->scene = {true, false, true, std::string("gripper"), {"gripper", "jaw"}};
  auto request = goalRequest();
  request.state = spp::State::LIFT;
  request.carrying = true;
  spp::ProfiledJointMotionAdapter adapter(boundary, boundary);
  EXPECT_EQ(adapter.plan(request, observation()).action.status, spp::ActionStatus::SUCCEEDED);
  EXPECT_EQ(boundary->plan_calls, 1);
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
