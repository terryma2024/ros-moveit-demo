#include "so101_gazebo_demo/pick_place/release_settle_executor.hpp"

#include <algorithm>
#include <chrono>
#include <sstream>
#include <thread>
#include <utility>

namespace so101_gazebo_demo::pick_place
{
namespace
{

Failure cancellationFailure()
{
  return {FailureCategory::EXECUTION,
          "FINAL_PLACEMENT_SETTLE_CANCELLED",
          "Post-release final placement settling was cancelled",
          {}};
}

Failure invalidMarkerFailure()
{
  return {FailureCategory::OBSERVATION,
          "FINAL_PLACEMENT_RELEASE_MARKER_STALE",
          "WAIT_RELEASE_SETTLE requires a fresh confirmed-open Gazebo pose marker",
          {}};
}

}  // namespace

void ThreadSettleWaiter::waitFor(std::chrono::steady_clock::duration duration)
{
  std::this_thread::sleep_for(duration);
}

ReleaseSettleExecutor::ReleaseSettleExecutor(IWorldObserver & observer,
                                             FinalPlacementEvaluator evaluator,
                                             IFinalPlacementEvidenceStore & evidence,
                                             PhysicalOutcomePolicyConfig policy,
                                             ISettleWaiter & waiter) :
    observer_(observer), evaluator_(std::move(evaluator)), evidence_(evidence),
    policy_(std::move(policy)), waiter_(waiter)
{
}

ActionResult ReleaseSettleExecutor::freezeFailure(FinalPlacementEvaluation evaluation,
                                                  Failure failure)
{
  evaluation.stable = false;
  evaluation.terminal_failure = failure.code == "FINAL_PLACEMENT_SAFETY_FAILURE";
  evaluation.evidence.reset();
  evaluation.failure = failure;
  if (const auto store_failure = evidence_.recordEvaluation(evaluation))
    return {ActionStatus::FAILED, *store_failure};
  return {ActionStatus::FAILED, std::move(failure)};
}

ActionResult ReleaseSettleExecutor::execute(const ExecutionContext & context)
{
  cancelled_.store(false);
  const auto & marker = context.before;
  if (!marker.fresh || !marker.gripper_open || marker.simulation_session_id.empty() ||
      !marker.gazebo_pose_sequence || !marker.gazebo_pose_observed_at) {
    return {ActionStatus::FAILED, invalidMarkerFailure()};
  }

  std::ostringstream epoch_id;
  epoch_id << marker.simulation_session_id << ":release:" << *marker.gazebo_pose_sequence;
  const ReleaseEpoch epoch{epoch_id.str(), marker.simulation_session_id,
                           *marker.gazebo_pose_sequence};
  if (const auto store_failure = evidence_.beginEpoch(epoch))
    return {ActionStatus::FAILED, *store_failure};

  FinalPlacementEvaluation latest = evaluator_.evaluate(epoch, {});
  if (!policy_.calibration_complete || !policy_.sample_interval_s || !policy_.settle_timeout_s ||
      *policy_.sample_interval_s <= 0.0 || *policy_.settle_timeout_s <= 0.0 ||
      latest.terminal_failure) {
    const auto failure = latest.failure.value_or(Failure{FailureCategory::CONFIGURATION,
                                                         "FINAL_PLACEMENT_SAFETY_FAILURE",
                                                         "Final placement policy is not calibrated",
                                                         {}});
    return freezeFailure(std::move(latest), failure);
  }

  std::vector<WorldSnapshot> samples;
  const auto interval = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
    std::chrono::duration<double>{*policy_.sample_interval_s});
  const auto timeout = std::chrono::duration_cast<std::chrono::steady_clock::duration>(
    std::chrono::duration<double>{*policy_.settle_timeout_s});
  std::chrono::steady_clock::duration elapsed{0};

  while (true) {
    if (cancelled_.load())
      return freezeFailure(std::move(latest), cancellationFailure());
    const auto observed = observer_.observe();
    if (cancelled_.load())
      return freezeFailure(std::move(latest), cancellationFailure());
    if (!observed.snapshot) {
      return freezeFailure(std::move(latest), observed.failure.value_or(Failure{
                                                FailureCategory::OBSERVATION,
                                                "FINAL_PLACEMENT_EVIDENCE_STALE",
                                                "Unable to observe post-release final placement",
                                                {}}));
    }

    samples.push_back(*observed.snapshot);
    latest = evaluator_.evaluate(epoch, samples);
    if (const auto store_failure = evidence_.recordEvaluation(latest))
      return {ActionStatus::FAILED, *store_failure};
    if (latest.stable)
      return {ActionStatus::SUCCEEDED, std::nullopt};
    if (latest.terminal_failure)
      return {ActionStatus::FAILED, latest.failure};
    if (elapsed >= timeout)
      return {ActionStatus::FAILED, latest.failure};

    const auto wait_duration = std::min(interval, timeout - elapsed);
    waiter_.waitFor(wait_duration);
    elapsed += wait_duration;
    if (cancelled_.load())
      return freezeFailure(std::move(latest), cancellationFailure());
  }
}

ActionResult ReleaseSettleExecutor::cancel()
{
  cancelled_.store(true);
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

}  // namespace so101_gazebo_demo::pick_place
