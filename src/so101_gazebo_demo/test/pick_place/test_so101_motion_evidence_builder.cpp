#include <optional>
#include <vector>

#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/so101_motion_evidence_builder.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

class RecordingStateEvaluator final : public spp::IRobotStateEvidenceProvider
{
public:
  std::optional<spp::RobotStateEvidence>
  evaluate(const std::vector<std::string> & joint_names,
           const std::vector<double> & joint_positions) const override
  {
    seen_names.push_back(joint_names);
    seen_positions.push_back(joint_positions);
    if (fail_at && seen_positions.size() == *fail_at) return std::nullopt;
    const double sum = joint_positions[0] + joint_positions[1] + joint_positions[2] +
                       joint_positions[3] + joint_positions[4];
    return spp::RobotStateEvidence{{sum, -0.28, 0.30 - sum, 0, 0, 0, 1},
                                   collision_at != seen_positions.size()};
  }

  mutable std::vector<std::vector<std::string>> seen_names;
  mutable std::vector<std::vector<double>> seen_positions;
  std::optional<std::size_t> fail_at;
  std::size_t collision_at{0};
};

spp::TrajectoryEvidenceInput input()
{
  spp::TrajectoryEvidenceInput value;
  value.joint_names = {"1", "2", "3", "4", "5"};
  value.current_joint_snapshot = {0, 0, 0, 0, 0};
  value.points = {{{0, 0, 0, 0, 0}, 0.0},
                  {{0.01, 0.02, 0.03, 0.04, 0.05}, 1.0},
                  {{0.02, 0.03, 0.04, 0.05, 0.06}, 2.0}};
  value.moveit_success = true;
  value.moveit_error_code = 1;
  value.planner_id = "RRTConnectkConfigDefault";
  value.start_state_stamp_nanoseconds = 4242000000ULL;
  value.collision_aware_planner = true;
  return value;
}

}  // namespace

TEST(SO101MotionEvidenceBuilder, ReconstructsEveryTcpAndCollisionSample)
{
  RecordingStateEvaluator evaluator;
  const auto result = spp::buildMotionPlanEvidence(input(), evaluator);
  ASSERT_TRUE(result.artifact);
  EXPECT_FALSE(result.failure);
  EXPECT_EQ(evaluator.seen_positions.size(), 3U);
  EXPECT_EQ(result.artifact->trajectory_points, 3U);
  EXPECT_EQ(result.artifact->joint_names,
            (std::vector<std::string>{"1", "2", "3", "4", "5"}));
  EXPECT_EQ(result.artifact->start_joint_positions,
            (std::vector<double>{0, 0, 0, 0, 0}));
  EXPECT_EQ(result.artifact->goal_joint_positions,
            (std::vector<double>{0.02, 0.03, 0.04, 0.05, 0.06}));
  EXPECT_TRUE(result.artifact->collision_aware);
  EXPECT_TRUE(result.artifact->time_parameterized);
  EXPECT_TRUE(result.artifact->moveit_success);
  EXPECT_EQ(result.artifact->moveit_error_code, 1);
  EXPECT_EQ(result.artifact->planner_id, "RRTConnectkConfigDefault");
  EXPECT_EQ(result.artifact->start_state_stamp_nanoseconds, 4242000000ULL);
  EXPECT_EQ(result.artifact->current_joint_snapshot,
            (std::vector<double>{0, 0, 0, 0, 0}));
  EXPECT_NEAR(result.artifact->samples[2].tcp_pose.x, 0.20, 1e-12);
}

TEST(SO101MotionEvidenceBuilder, PreservesCollidingSampleAsNegativeEvidence)
{
  RecordingStateEvaluator evaluator;
  evaluator.collision_at = 2;
  const auto result = spp::buildMotionPlanEvidence(input(), evaluator);
  ASSERT_TRUE(result.artifact);
  EXPECT_FALSE(result.artifact->samples[1].collision_free);
  EXPECT_FALSE(spp::validateJointGoalPlan(*result.artifact,
    {{"1", "2", "3", "4", "5"}, {0.20, -0.28, 0.10}, {0, 0, -1}, {0, 0, -1},
     {0, 0, -1}, 0.01, 0.1, 0.01, 0.2, 0.001, 0.1, 1e-5}).ok);
}

TEST(SO101MotionEvidenceBuilder, FailsClosedWhenFkOrPointShapeIsUnavailable)
{
  RecordingStateEvaluator evaluator;
  evaluator.fail_at = 2;
  auto result = spp::buildMotionPlanEvidence(input(), evaluator);
  EXPECT_FALSE(result.artifact);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "MOTION_STATE_EVIDENCE_UNAVAILABLE");

  auto malformed = input();
  malformed.points[1].joint_positions.pop_back();
  result = spp::buildMotionPlanEvidence(malformed, evaluator);
  EXPECT_FALSE(result.artifact);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "TRAJECTORY_POINT_SHAPE_MISMATCH");
}
