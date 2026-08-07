#include <gtest/gtest.h>

#include <array>
#include <chrono>
#include <cstdint>
#include <functional>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "so101_gazebo_demo/pick_place/final_placement_evidence_store.hpp"
#include "so101_gazebo_demo/pick_place/release_settle_executor.hpp"

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
  result.settle_timeout_s = 1.0;
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

WorldSnapshot sample(std::uint64_t sequence, std::chrono::steady_clock::duration time)
{
  WorldSnapshot result;
  result.observed_at = std::chrono::steady_clock::time_point{time};
  result.fresh = true;
  result.arm_stationary = true;
  result.gripper_open = true;
  result.simulation_session_id = "session";
  result.gazebo_pose_sequence = sequence;
  result.gazebo_pose_observed_at = result.observed_at;
  result.gazebo_task_object_pose_world = Pose3d{-0.08, -0.25, 0.165, 0.0, 0.0, 0.0, 1.0};
  result.gazebo_task_object_attached = false;
  result.moveit_task_object_attached = false;
  result.gazebo_task_object_intended_support_contact = true;
  result.gazebo_task_object_gripper_contact = false;
  result.gazebo_support_contact_observed_at = result.observed_at;
  result.gazebo_gripper_contact_observed_at = result.observed_at;
  return result;
}

ExecutionContext context()
{
  return {State::WAIT_RELEASE_SETTLE, State::VALIDATE_FINAL_PLACEMENT, sample(10, 0ms), nullptr};
}

class FakeObserver final : public IWorldObserver
{
public:
  explicit FakeObserver(std::vector<WorldSnapshot> samples) : samples_(std::move(samples)) {}

  ObservationResult observe() override
  {
    ++calls;
    if (next_ >= samples_.size())
      return {{}, Failure{FailureCategory::OBSERVATION, "NO_SAMPLE", "No sample", {}}};
    return {samples_[next_++], std::nullopt};
  }

  std::size_t calls{0};

private:
  std::vector<WorldSnapshot> samples_{};
  std::size_t next_{0};
};

class FakeWaiter final : public ISettleWaiter
{
public:
  void waitFor(std::chrono::steady_clock::duration duration) override
  {
    waits.push_back(duration);
    if (after_wait)
      after_wait();
  }

  std::vector<std::chrono::steady_clock::duration> waits{};
  std::function<void()> after_wait{};
};

std::vector<WorldSnapshot> stableSamples()
{
  return {sample(11, 100ms), sample(12, 200ms), sample(13, 300ms), sample(14, 400ms)};
}

TEST(ReleaseSettleExecutor, StartsEpochAfterConfirmedOpenPostObservation)
{
  FakeObserver observer(stableSamples());
  FakeWaiter waiter;
  InMemoryFinalPlacementEvidenceStore evidence;
  auto configured = policy();
  ReleaseSettleExecutor executor(observer, FinalPlacementEvaluator(configured), evidence,
                                 configured, waiter);

  EXPECT_EQ(ActionStatus::SUCCEEDED, executor.execute(context()).status);
  ASSERT_TRUE(evidence.frozen());
  EXPECT_EQ(10U, evidence.frozen()->epoch.start_sequence);
  EXPECT_EQ("session", evidence.frozen()->epoch.simulation_session_id);
  EXPECT_NE(std::string::npos, evidence.frozen()->epoch.id.find("session"));
  EXPECT_NE(std::string::npos, evidence.frozen()->epoch.id.find("10"));
}

TEST(ReleaseSettleExecutor, NeverPassesPreReleaseSamplesToEvaluator)
{
  auto samples = stableSamples();
  samples.insert(samples.begin(), sample(10, 50ms));
  samples.insert(samples.begin(), sample(9, 25ms));
  FakeObserver observer(std::move(samples));
  FakeWaiter waiter;
  InMemoryFinalPlacementEvidenceStore evidence;
  auto configured = policy();
  ReleaseSettleExecutor executor(observer, FinalPlacementEvaluator(configured), evidence,
                                 configured, waiter);

  EXPECT_EQ(ActionStatus::SUCCEEDED, executor.execute(context()).status);
  ASSERT_TRUE(evidence.frozen());
  EXPECT_EQ(2U, evidence.frozen()->evaluation.metrics.pre_release_rejected_count);
  ASSERT_TRUE(evidence.frozen()->evaluation.evidence);
  EXPECT_GT(evidence.frozen()->evaluation.evidence->first_counted_sequence, 10U);
}

TEST(ReleaseSettleExecutor, PollsUntilConsecutiveWindowSucceeds)
{
  FakeObserver observer(stableSamples());
  FakeWaiter waiter;
  InMemoryFinalPlacementEvidenceStore evidence;
  auto configured = policy();
  ReleaseSettleExecutor executor(observer, FinalPlacementEvaluator(configured), evidence,
                                 configured, waiter);

  const auto result = executor.execute(context());

  EXPECT_EQ(ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(4U, observer.calls);
  EXPECT_EQ(3U, waiter.waits.size());
  ASSERT_TRUE(evidence.frozen());
  EXPECT_TRUE(evidence.frozen()->evaluation.stable);
}

TEST(ReleaseSettleExecutor, TimesOutWithSpecificLatestPredicateFailure)
{
  auto configured = policy();
  configured.settle_timeout_s = 0.3;
  auto samples = stableSamples();
  for (auto & value : samples)
    value.gazebo_task_object_intended_support_contact = false;
  FakeObserver observer(std::move(samples));
  FakeWaiter waiter;
  InMemoryFinalPlacementEvidenceStore evidence;
  ReleaseSettleExecutor executor(observer, FinalPlacementEvaluator(configured), evidence,
                                 configured, waiter);

  const auto result = executor.execute(context());

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("FINAL_PLACEMENT_UNSUPPORTED", result.failure->code);
  ASSERT_TRUE(evidence.frozen());
  EXPECT_EQ("FINAL_PLACEMENT_UNSUPPORTED", evidence.frozen()->evaluation.failure->code);
}

TEST(ReleaseSettleExecutor, CancellationStopsPollingAndFreezesEvidence)
{
  FakeObserver observer(stableSamples());
  FakeWaiter waiter;
  InMemoryFinalPlacementEvidenceStore evidence;
  auto configured = policy();
  ReleaseSettleExecutor executor(observer, FinalPlacementEvaluator(configured), evidence,
                                 configured, waiter);
  waiter.after_wait = [&executor]() { static_cast<void>(executor.cancel()); };

  const auto result = executor.execute(context());

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("FINAL_PLACEMENT_SETTLE_CANCELLED", result.failure->code);
  EXPECT_EQ(1U, observer.calls);
  ASSERT_TRUE(evidence.frozen());
  EXPECT_EQ("FINAL_PLACEMENT_SETTLE_CANCELLED", evidence.frozen()->evaluation.failure->code);
}

TEST(ReleaseSettleExecutor, RejectsCalibrationRequiredPolicyBeforePolling)
{
  FakeObserver observer(stableSamples());
  FakeWaiter waiter;
  InMemoryFinalPlacementEvidenceStore evidence;
  auto configured = policy();
  configured.calibration_complete = false;
  ReleaseSettleExecutor executor(observer, FinalPlacementEvaluator(configured), evidence,
                                 configured, waiter);

  const auto result = executor.execute(context());

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("FINAL_PLACEMENT_SAFETY_FAILURE", result.failure->code);
  EXPECT_EQ(0U, observer.calls);
  ASSERT_TRUE(evidence.frozen());
}

TEST(ReleaseSettleExecutor, KeepsBoundedMetricsAcrossTransientFluctuations)
{
  auto configured = policy();
  configured.max_telemetry_samples = 2;
  auto samples = stableSamples();
  samples.front().gazebo_task_object_gripper_contact = true;
  samples.push_back(sample(15, 500ms));
  FakeObserver observer(std::move(samples));
  FakeWaiter waiter;
  InMemoryFinalPlacementEvidenceStore evidence;
  ReleaseSettleExecutor executor(observer, FinalPlacementEvaluator(configured), evidence,
                                 configured, waiter);

  EXPECT_EQ(ActionStatus::SUCCEEDED, executor.execute(context()).status);
  ASSERT_TRUE(evidence.frozen());
  EXPECT_EQ(2U, evidence.frozen()->evaluation.metrics.retained_samples.size());
  EXPECT_TRUE(evidence.frozen()->evaluation.metrics.violated_predicates.count("gripper_contact") !=
              0U);
}

}  // namespace
}  // namespace so101_gazebo_demo::pick_place
