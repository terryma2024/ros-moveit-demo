#include <gtest/gtest.h>

#include <array>
#include <chrono>
#include <cmath>
#include <limits>
#include <string>
#include <vector>

#include "so101_gazebo_demo/pick_place/final_placement_evaluator.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{
using namespace std::chrono_literals;

PhysicalOutcomePolicyConfig policy()
{
  PhysicalOutcomePolicyConfig result;
  result.intended_support_collision = "table::link::collision";
  result.final_target_region = AxisAlignedTargetRegion{-0.2, -0.4, 0.1, 0.0};
  result.support_height_range_m = std::array<double, 2>{0.15, 0.18};
  result.max_upright_tilt_rad = 0.2;
  result.max_linear_speed_m_s = 0.05;
  result.max_angular_speed_rad_s = 0.5;
  result.consecutive_samples = 3;
  result.minimum_stable_duration_s = 0.2;
  result.sample_interval_s = 0.1;
  result.settle_timeout_s = 2.0;
  result.max_observation_age_s = 0.2;
  result.max_telemetry_samples = 4;
  result.catastrophic_loss.workspace_bounds_m =
    std::array<double, 6>{-1.0, -1.0, 0.0, 1.0, 1.0, 1.0};
  result.catastrophic_loss.max_relative_position_drift_m = 0.5;
  result.catastrophic_loss.max_relative_orientation_drift_rad = 1.0;
  result.planning_shadow.max_position_divergence_m = 0.1;
  result.planning_shadow.max_orientation_divergence_rad = 0.5;
  result.planning_shadow.max_pair_age_s = 0.2;
  result.calibration_complete = true;
  return result;
}

WorldSnapshot sample(std::uint64_t sequence, std::chrono::steady_clock::duration time,
                     const std::string & session = "session")
{
  WorldSnapshot result;
  result.fresh = true;
  result.simulation_session_id = session;
  result.gazebo_pose_sequence = sequence;
  result.gazebo_pose_observed_at = std::chrono::steady_clock::time_point{time};
  result.gazebo_task_object_pose_world = Pose3d{-0.08, -0.25, 0.165, 0.0, 0.0, 0.0, 1.0};
  result.gazebo_task_object_attached = false;
  result.moveit_task_object_attached = false;
  result.gazebo_task_object_intended_support_contact = true;
  result.gazebo_task_object_gripper_contact = false;
  result.gazebo_support_contact_observed_at = result.gazebo_pose_observed_at;
  result.gazebo_gripper_contact_observed_at = result.gazebo_pose_observed_at;
  return result;
}

ReleaseEpoch epoch()
{
  return {"release-1", "session", 10};
}

std::vector<WorldSnapshot> stableWindow()
{
  return {sample(11, 0ms), sample(12, 100ms), sample(13, 200ms), sample(14, 300ms)};
}

TEST(FinalPlacementEvaluator, AcceptsOnlyConsecutivePostReleaseStableSamples)
{
  const auto evaluation = FinalPlacementEvaluator(policy()).evaluate(epoch(), stableWindow());

  EXPECT_TRUE(evaluation.stable);
  EXPECT_EQ(3U, evaluation.metrics.consecutive_samples);
  EXPECT_EQ(4U, evaluation.metrics.post_release_sample_count);
}

TEST(FinalPlacementEvaluator, RejectsEverySampleAtOrBeforeReleaseSequence)
{
  auto samples = stableWindow();
  samples.insert(samples.begin(), sample(9, -200ms));
  samples.insert(samples.begin() + 1, sample(10, -100ms));

  const auto evaluation = FinalPlacementEvaluator(policy()).evaluate(epoch(), samples);

  EXPECT_TRUE(evaluation.stable);
  EXPECT_EQ(2U, evaluation.metrics.pre_release_rejected_count);
  ASSERT_TRUE(evaluation.evidence);
  EXPECT_GT(evaluation.evidence->first_counted_sequence, epoch().start_sequence);
}

TEST(FinalPlacementEvaluator, UsesLastCountedGazeboPoseAsFinalPose)
{
  auto samples = stableWindow();
  for (auto & snapshot : samples)
    snapshot.gazebo_task_object_pose_world->x = -0.07;

  const auto evaluation = FinalPlacementEvaluator(policy()).evaluate(epoch(), samples);

  ASSERT_TRUE(evaluation.evidence);
  EXPECT_DOUBLE_EQ(-0.07, evaluation.evidence->final_pose.x);
  EXPECT_EQ(14U, evaluation.evidence->final_sequence);
}

TEST(FinalPlacementEvaluator, ResetsConsecutiveWindowOnSessionOrSequenceBreak)
{
  auto samples = stableWindow();
  samples[2].simulation_session_id = "other";
  samples[3].gazebo_pose_sequence = 12;

  const auto evaluation = FinalPlacementEvaluator(policy()).evaluate(epoch(), samples);

  EXPECT_FALSE(evaluation.stable);
  EXPECT_EQ(0U, evaluation.metrics.consecutive_samples);
  EXPECT_TRUE(evaluation.metrics.violated_predicates.count("session_or_sequence"));
}

TEST(FinalPlacementEvaluator, RequiresConfiguredCountAndMinimumDuration)
{
  auto samples = stableWindow();
  samples[3].gazebo_pose_observed_at = std::chrono::steady_clock::time_point{250ms};

  const auto evaluation = FinalPlacementEvaluator(policy()).evaluate(epoch(), samples);

  EXPECT_FALSE(evaluation.stable);
  EXPECT_EQ(3U, evaluation.metrics.consecutive_samples);
  EXPECT_LT(evaluation.metrics.consecutive_duration_s, 0.2);
}

TEST(FinalPlacementEvaluator, DerivesAdjacentLinearAndShortestQuaternionAngularSpeed)
{
  auto samples = stableWindow();
  samples[1].gazebo_task_object_pose_world->x += 0.001;
  const double angle = 0.02;
  samples[1].gazebo_task_object_pose_world->qz = std::sin(angle / 2.0);
  samples[1].gazebo_task_object_pose_world->qw = -std::cos(angle / 2.0);

  const auto evaluation = FinalPlacementEvaluator(policy()).evaluate(epoch(), samples);

  ASSERT_FALSE(evaluation.metrics.retained_samples.empty());
  EXPECT_NEAR(0.01, evaluation.metrics.retained_samples.front().linear_speed_m_s, 1e-9);
  EXPECT_NEAR(0.2, evaluation.metrics.retained_samples.front().angular_speed_rad_s, 1e-9);
}

TEST(FinalPlacementEvaluator, TreatsNonIncreasingOrNonFiniteTimeAsStale)
{
  const std::array invalid_times{std::chrono::steady_clock::duration{100ms},
                                 std::chrono::steady_clock::duration::max()};
  for (const auto time : invalid_times) {
    auto samples = stableWindow();
    samples[2].gazebo_pose_observed_at = time == std::chrono::steady_clock::duration::max()
                                           ? std::optional<std::chrono::steady_clock::time_point>{}
                                           : std::optional<std::chrono::steady_clock::time_point>{
                                               std::chrono::steady_clock::time_point{time}};

    const auto evaluation = FinalPlacementEvaluator(policy()).evaluate(epoch(), samples);

    ASSERT_TRUE(evaluation.failure);
    EXPECT_EQ("FINAL_PLACEMENT_EVIDENCE_STALE", evaluation.failure->code);
  }
}

TEST(FinalPlacementEvaluator, BoundsTelemetryAndPreservesAggregates)
{
  auto configured = policy();
  configured.max_telemetry_samples = 2;
  auto samples = stableWindow();
  samples.push_back(sample(15, 400ms));
  samples.push_back(sample(16, 500ms));

  const auto evaluation = FinalPlacementEvaluator(configured).evaluate(epoch(), samples);

  EXPECT_EQ(2U, evaluation.metrics.retained_samples.size());
  EXPECT_EQ(6U, evaluation.metrics.post_release_sample_count);
  EXPECT_EQ(5U, evaluation.metrics.derived_speed_sample_count);
  EXPECT_TRUE(std::isfinite(evaluation.metrics.mean_linear_speed_m_s));
}

TEST(FinalPlacementEvaluator, AppliesSafetyStaleContactSupportTiltMotionRegionPrecedence)
{
  struct Case
  {
    const char * code;
    void (*mutate)(WorldSnapshot &);
  };
  const std::vector<Case> cases{
    {"FINAL_PLACEMENT_SAFETY_FAILURE",
     [](WorldSnapshot & value) { value.gazebo_task_object_pose_world->x = 2.0; }},
    {"FINAL_PLACEMENT_EVIDENCE_STALE", [](WorldSnapshot & value) { value.fresh = false; }},
    {"FINAL_PLACEMENT_GRIPPER_CONTACT",
     [](WorldSnapshot & value) { value.gazebo_task_object_gripper_contact = true; }},
    {"FINAL_PLACEMENT_UNSUPPORTED",
     [](WorldSnapshot & value) { value.gazebo_task_object_intended_support_contact = false; }},
    {"FINAL_PLACEMENT_TIPPED",
     [](WorldSnapshot & value) {
       value.gazebo_task_object_pose_world->qx = std::sin(0.3 / 2.0);
       value.gazebo_task_object_pose_world->qw = std::cos(0.3 / 2.0);
     }},
    {"FINAL_PLACEMENT_STILL_MOVING",
     [](WorldSnapshot & value) { value.gazebo_task_object_pose_world->x += 0.02; }},
    {"FINAL_PLACEMENT_OUT_OF_REGION",
     [](WorldSnapshot & value) { value.gazebo_task_object_pose_world->x = 0.2; }}};
  for (const auto & test_case : cases) {
    auto samples = stableWindow();
    if (std::string{test_case.code} == "FINAL_PLACEMENT_OUT_OF_REGION") {
      for (auto & snapshot : samples)
        test_case.mutate(snapshot);
    } else {
      test_case.mutate(samples.back());
    }
    const auto evaluation = FinalPlacementEvaluator(policy()).evaluate(epoch(), samples);
    ASSERT_TRUE(evaluation.failure) << test_case.code;
    EXPECT_EQ(test_case.code, evaluation.failure->code);
  }
}

TEST(FinalPlacementEvaluator, ReportsAllViolatedPredicatesAlongsidePrimaryCode)
{
  auto samples = stableWindow();
  auto & final = samples.back();
  final.gazebo_task_object_gripper_contact = true;
  final.gazebo_task_object_intended_support_contact = false;
  final.gazebo_task_object_pose_world->x = 0.2;

  const auto evaluation = FinalPlacementEvaluator(policy()).evaluate(epoch(), samples);

  ASSERT_TRUE(evaluation.failure);
  EXPECT_EQ("FINAL_PLACEMENT_GRIPPER_CONTACT", evaluation.failure->code);
  EXPECT_TRUE(evaluation.metrics.violated_predicates.count("gripper_contact"));
  EXPECT_TRUE(evaluation.metrics.violated_predicates.count("unsupported"));
  EXPECT_TRUE(evaluation.metrics.violated_predicates.count("out_of_region"));
}

}  // namespace
}  // namespace so101_gazebo_demo::pick_place
