#include "so101_gazebo_demo/pick_place/physical_grasp_retry.hpp"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <string>
#include <utility>
#include <variant>

#include "so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp"
#include "so101_gazebo_demo/pick_place/physical_grasp_evidence_store.hpp"
#include "so101_gazebo_demo/pick_place/physical_grasp_stabilizer.hpp"
#include "so101_gazebo_demo/pick_place/so101_gripper_state.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{
Failure rejection(std::string code, std::string message)
{
  return {FailureCategory::POSTCONDITION, std::move(code), std::move(message), {}};
}
}  // namespace

PhysicalGraspRetryDecision decidePhysicalGraspRetry(const PhysicalGraspRetryConfig & config,
                                                    const SO101Profile & profile,
                                                    const PhysicalGraspRetryProgress & current,
                                                    const PhysicalGraspResult & physical_result,
                                                    const WorldSnapshot & after)
{
  PhysicalGraspRetryDecision decision{false, current, std::nullopt};
  if (config.max_attempts == 0 || config.max_attempts > 2 ||
      config.contact_missing_tighten_step_q6 <= 0.0 || config.max_tighten_q6 < 0.0 ||
      current.attempt_index == 0 || current.attempt_index > config.max_attempts ||
      current.contact_missing_count >= config.max_attempts ||
      !std::isfinite(current.current_reclose_target_q6)) {
    decision.rejection = rejection("PHYSICAL_GRASP_RETRY_CONFIG_INVALID",
                                   "Physical-grasp retry configuration is invalid");
    return decision;
  }
  if (physical_result.passed || current.attempt_index >= config.max_attempts)
    return decision;

  const bool retryable_code = physical_result.failure.code == "PHYSICAL_GRASP_INSUFFICIENT_LIFT" ||
                              physical_result.failure.code == "PHYSICAL_GRASP_POSITION_ERROR" ||
                              physical_result.failure.code == "PHYSICAL_GRASP_TABLE_CLEARANCE" ||
                              physical_result.failure.code == "PHYSICAL_GRASP_FOLLOW_RATIO" ||
                              physical_result.failure.code == "PHYSICAL_GRASP_CONTACT_MISSING";
  const bool detached =
    after.gazebo_task_object_attached.has_value() && !*after.gazebo_task_object_attached &&
    after.moveit_task_object_attached.has_value() && !*after.moveit_task_object_attached;
  const bool safe = retryable_code && physical_result.tcp_z_delta_m > 0.0 &&
                    physical_result.xy_slip_m <= PhysicalGraspThresholds{}.max_xy_slip_m &&
                    physical_result.orientation_change_rad <=
                      PhysicalGraspThresholds{}.max_orientation_change_rad &&
                    after.fresh && after.arm_stationary &&
                    after.gazebo_task_object_stationary.value_or(false) && detached;
  if (!safe) {
    decision.rejection = rejection("PHYSICAL_GRASP_RETRY_NOT_SAFE",
                                   "Physical-grasp retry safety predicates are not satisfied");
    return decision;
  }

  decision.next.attempt_index = current.attempt_index + 1;
  if (!physical_result.gripper_contact)
    ++decision.next.contact_missing_count;
  const double deepest_allowed =
    std::max({profile.q6_contact - config.max_tighten_q6,
              profile.q6_contact - profile.q6_regrasp_squeeze_offset, profile.q6_safe_lower});
  const double requested =
    profile.q6_contact - static_cast<double>(decision.next.contact_missing_count) *
                           config.contact_missing_tighten_step_q6;
  decision.next.current_reclose_target_q6 = std::max(requested, deepest_allowed);
  decision.retry = true;
  return decision;
}

class PhysicalGraspRetryCoordinator::Impl
{
public:
  enum class ActiveOperation
  {
    NONE,
    GRIPPER,
    DESCEND,
    LIFT,
    STABILIZER,
  };

  Impl(std::shared_ptr<ISO101GripperCommand> gripper_value,
       std::shared_ptr<IWorldZMicroLift> micro_lift_value,
       std::shared_ptr<IWorldObserver> observer_value,
       std::shared_ptr<IPhysicalGraspEvidenceStore> evidence_value,
       std::shared_ptr<SO101PhysicalGraspStabilizer> stabilizer_value,
       PhysicalGraspValidator validator_value, PhysicalGraspGeometry geometry_value,
       SO101Profile profile_value, PhysicalGraspRetryConfig config_value) :
      gripper(std::move(gripper_value)), micro_lift(std::move(micro_lift_value)),
      observer(std::move(observer_value)), evidence(std::move(evidence_value)),
      stabilizer(std::move(stabilizer_value)), validator(validator_value), geometry(geometry_value),
      profile(std::move(profile_value)), config(config_value)
  {
  }

  std::shared_ptr<ISO101GripperCommand> gripper;
  std::shared_ptr<IWorldZMicroLift> micro_lift;
  std::shared_ptr<IWorldObserver> observer;
  std::shared_ptr<IPhysicalGraspEvidenceStore> evidence;
  std::shared_ptr<SO101PhysicalGraspStabilizer> stabilizer;
  PhysicalGraspValidator validator;
  PhysicalGraspGeometry geometry;
  SO101Profile profile;
  PhysicalGraspRetryConfig config;
  std::atomic_bool cancelled{false};
  std::atomic<ActiveOperation> active{ActiveOperation::NONE};
};

namespace
{
ActionResult retryFailure(FailureCategory category, std::string code, std::string message)
{
  return {ActionStatus::FAILED, Failure{category, std::move(code), std::move(message), {}}};
}

WorldSnapshot sampleWorld(const PhysicalGraspSample & sample)
{
  WorldSnapshot world;
  world.fresh = true;
  // Persisted samples are only produced after the stabilizer has observed a
  // stationary arm/cup window; the compact evidence record does not duplicate
  // that boolean.
  world.arm_stationary = true;
  world.gazebo_task_object_stationary = true;
  world.tcp_pose_world = sample.tcp_pose_world;
  world.gazebo_task_object_pose_world = sample.task_object_pose_world;
  world.gazebo_task_object_gripper_contact = sample.gripper_contact;
  return world;
}

std::optional<Failure> validateRetryWorld(const WorldSnapshot & world,
                                          const PhysicalGraspEvidenceRecord & record,
                                          const SO101Profile & profile)
{
  const auto moveit = world.moveit_world_object_poses.find(profile.task_object_id);
  const bool detached =
    world.gazebo_task_object_attached.has_value() && !*world.gazebo_task_object_attached &&
    world.moveit_task_object_attached.has_value() && !*world.moveit_task_object_attached;
  const bool stable =
    world.fresh && world.arm_stationary && world.gazebo_task_object_stationary.value_or(false);
  const bool provenance = !record.simulation_session_id.empty() &&
                          world.simulation_session_id == record.simulation_session_id;
  const bool poses_match =
    world.gazebo_task_object_pose_world && moveit != world.moveit_world_object_poses.end() &&
    positionDistance(*world.gazebo_task_object_pose_world, moveit->second) <=
      profile.task_object_position_drift_tolerance &&
    orientationDistance(*world.gazebo_task_object_pose_world, moveit->second) <=
      profile.task_object_orientation_drift_tolerance_rad;
  if (!stable || !detached || !provenance || !poses_match) {
    return Failure{FailureCategory::POSTCONDITION,
                   "PHYSICAL_GRASP_RETRY_NOT_SAFE",
                   "Retry requires fresh matching detached stationary world evidence",
                   {}};
  }
  return std::nullopt;
}

Failure interruptedFailure(const PhysicalGraspRetryEvidence & retry)
{
  return {FailureCategory::POSTCONDITION,
          "PHYSICAL_GRASP_RETRY_INTERRUPTED",
          "Physical-grasp retry stopped during an uncertain side-effect phase",
          {{"attempt_index", static_cast<double>(retry.progress.attempt_index)},
           {"phase", static_cast<double>(retry.phase)},
           {"close_target_q6", retry.progress.current_reclose_target_q6}}};
}
}  // namespace

PhysicalGraspRetryCoordinator::PhysicalGraspRetryCoordinator(
  std::shared_ptr<ISO101GripperCommand> gripper, std::shared_ptr<IWorldZMicroLift> micro_lift,
  std::shared_ptr<IWorldObserver> observer, std::shared_ptr<IPhysicalGraspEvidenceStore> evidence,
  std::shared_ptr<SO101PhysicalGraspStabilizer> stabilizer, PhysicalGraspValidator validator,
  PhysicalGraspGeometry geometry, SO101Profile profile, PhysicalGraspRetryConfig config) :
    impl_(std::make_unique<Impl>(std::move(gripper), std::move(micro_lift), std::move(observer),
                                 std::move(evidence), std::move(stabilizer), validator, geometry,
                                 std::move(profile), config))
{
}

PhysicalGraspRetryCoordinator::~PhysicalGraspRetryCoordinator() = default;
PhysicalGraspRetryCoordinator::PhysicalGraspRetryCoordinator(
  PhysicalGraspRetryCoordinator &&) noexcept = default;
PhysicalGraspRetryCoordinator &
PhysicalGraspRetryCoordinator::operator=(PhysicalGraspRetryCoordinator &&) noexcept = default;

ActionResult PhysicalGraspRetryCoordinator::verifyOrRetry()
{
  auto & self = *impl_;
  self.cancelled.store(false);
  if (!self.gripper || !self.micro_lift || !self.observer || !self.evidence || !self.stabilizer) {
    return retryFailure(FailureCategory::CONFIGURATION, "PHYSICAL_GRASP_RETRY_DEPENDENCY_MISSING",
                        "Physical-grasp retry dependencies are incomplete");
  }
  auto loaded = self.evidence->load();
  if (std::holds_alternative<Failure>(loaded))
    return {ActionStatus::FAILED, std::get<Failure>(std::move(loaded))};
  auto record = std::get<PhysicalGraspEvidenceRecord>(std::move(loaded));
  if (record.retry.phase != PhysicalGraspRetryPhase::IDLE &&
      record.retry.phase != PhysicalGraspRetryPhase::COMPLETE) {
    return {ActionStatus::FAILED, interruptedFailure(record.retry)};
  }
  if (record.retry.progress.attempt_index == 1 &&
      record.retry.progress.contact_missing_count == 0 &&
      record.retry.progress.current_reclose_target_q6 == 0.0) {
    record.retry.progress.current_reclose_target_q6 = self.profile.q6_contact;
  }
  while (true) {
    if (self.cancelled.load()) {
      return retryFailure(FailureCategory::EXECUTION, "PHYSICAL_GRASP_RETRY_CANCELLED",
                          "Physical-grasp retry was cancelled");
    }
    if (!record.before_lift || !record.after_lift) {
      return retryFailure(FailureCategory::POSTCONDITION, "PHYSICAL_GRASP_EVIDENCE_INCOMPLETE",
                          "Both stable windows are required before attachment");
    }
    const auto physical = self.validator.evaluate(sampleWorld(*record.before_lift),
                                                  sampleWorld(*record.after_lift), self.geometry);
    if (physical.passed) {
      record.retry.phase = PhysicalGraspRetryPhase::COMPLETE;
      if (const auto failure = self.evidence->saveRetryEvidence(record.retry))
        return {ActionStatus::FAILED, *failure};
      return {ActionStatus::SUCCEEDED, std::nullopt};
    }
    if (record.retry.progress.attempt_index >= self.config.max_attempts) {
      auto failure = physical.failure;
      failure.metrics["physical_grasp_attempts"] = static_cast<double>(self.config.max_attempts);
      failure.metrics["physical_grasp_retries"] =
        static_cast<double>(self.config.max_attempts - 1U);
      failure.metrics["contact_missing_count"] =
        static_cast<double>(record.retry.progress.contact_missing_count);
      failure.metrics["final_reclose_target_q6"] = record.retry.progress.current_reclose_target_q6;
      failure.metrics["micro_lift_preload_target_q6"] =
        std::max(self.profile.q6_safe_lower,
                 self.profile.q6_contact - self.profile.q6_regrasp_squeeze_offset);
      failure.metrics["retry_exhausted"] = 1.0;
      return {ActionStatus::FAILED, failure};
    }
    if (self.cancelled.load())
      continue;
    const auto boundary = self.observer->observe();
    if (!boundary.snapshot)
      return {ActionStatus::FAILED, boundary.failure};
    if (const auto failure = validateRetryWorld(*boundary.snapshot, record, self.profile))
      return {ActionStatus::FAILED, *failure};
    const auto decision = decidePhysicalGraspRetry(self.config, self.profile, record.retry.progress,
                                                   physical, *boundary.snapshot);
    if (!decision.retry)
      return {ActionStatus::FAILED, physical.failure};
    record.retry.progress = decision.next;
    record.retry.micro_lift_preload_target_q6 = std::max(
      self.profile.q6_safe_lower, self.profile.q6_contact - self.profile.q6_regrasp_squeeze_offset);
    const auto persist = [&](PhysicalGraspRetryPhase phase) -> std::optional<ActionResult> {
      if (self.cancelled.load()) {
        return retryFailure(FailureCategory::EXECUTION, "PHYSICAL_GRASP_RETRY_CANCELLED",
                            "Physical-grasp retry was cancelled");
      }
      record.retry.phase = phase;
      if (const auto failure = self.evidence->saveRetryEvidence(record.retry))
        return ActionResult{ActionStatus::FAILED, *failure};
      return std::nullopt;
    };
    const auto commandGripper = [&](double target) -> ActionResult {
      if (self.cancelled.load())
        return retryFailure(FailureCategory::EXECUTION, "PHYSICAL_GRASP_RETRY_CANCELLED",
                            "Physical-grasp retry was cancelled");
      self.active.store(Impl::ActiveOperation::GRIPPER);
      auto action = self.gripper->command(target);
      self.active.store(Impl::ActiveOperation::NONE);
      if (action.status != ActionStatus::SUCCEEDED)
        static_cast<void>(self.gripper->cancelAndWait());
      return action;
    };
    if (auto stopped = persist(PhysicalGraspRetryPhase::OPEN_PENDING))
      return *stopped;
    auto action = commandGripper(self.profile.q6_preopen);
    if (action.status != ActionStatus::SUCCEEDED)
      return action;
    if (self.cancelled.load())
      continue;
    const auto opened = self.observer->observe();
    if (!opened.snapshot)
      return {ActionStatus::FAILED, opened.failure};
    if (const auto failure = validateRetryWorld(*opened.snapshot, record, self.profile))
      return {ActionStatus::FAILED, *failure};
    if (auto stopped = persist(PhysicalGraspRetryPhase::DESCEND_PENDING))
      return *stopped;
    if (self.cancelled.load())
      continue;
    self.active.store(Impl::ActiveOperation::DESCEND);
    action = self.micro_lift->executeWorldZMicroDescend(opened.snapshot->tcp_pose_world,
                                                        record.before_lift->tcp_pose_world.z);
    self.active.store(Impl::ActiveOperation::NONE);
    if (action.status != ActionStatus::SUCCEEDED) {
      static_cast<void>(self.micro_lift->cancelWorldZMicroDescend());
      return action;
    }
    if (self.cancelled.load())
      continue;
    const auto descended = self.observer->observe();
    if (!descended.snapshot)
      return {ActionStatus::FAILED, descended.failure};
    if (const auto failure = validateRetryWorld(*descended.snapshot, record, self.profile))
      return {ActionStatus::FAILED, *failure};
    if (std::abs(descended.snapshot->tcp_pose_world.z - record.before_lift->tcp_pose_world.z) >
        kMicroLiftPositionToleranceM) {
      return retryFailure(FailureCategory::POSTCONDITION,
                          "MICRO_DESCEND_ENDPOINT_OUTSIDE_TOLERANCE",
                          "World-Z micro-descend did not reach the saved before-lift height");
    }
    if (auto stopped = persist(PhysicalGraspRetryPhase::CLOSE_PENDING))
      return *stopped;
    action = commandGripper(record.retry.progress.current_reclose_target_q6);
    if (action.status != ActionStatus::SUCCEEDED)
      return action;
    if (self.cancelled.load())
      continue;
    self.active.store(Impl::ActiveOperation::STABILIZER);
    action = self.stabilizer->captureBeforeLift();
    self.active.store(Impl::ActiveOperation::NONE);
    if (self.cancelled.load())
      continue;
    if (action.status != ActionStatus::SUCCEEDED) {
      static_cast<void>(self.stabilizer->cancel());
      return action;
    }
    if (auto stopped = persist(PhysicalGraspRetryPhase::LIFT_PENDING))
      return *stopped;
    if (self.cancelled.load())
      continue;
    self.active.store(Impl::ActiveOperation::LIFT);
    action = self.micro_lift->executeWorldZMicroLift(record.before_lift->tcp_pose_world, 0.002);
    self.active.store(Impl::ActiveOperation::NONE);
    if (action.status != ActionStatus::SUCCEEDED) {
      static_cast<void>(self.micro_lift->cancelWorldZMicroLift());
      return action;
    }
    if (self.cancelled.load())
      continue;
    self.active.store(Impl::ActiveOperation::STABILIZER);
    action = self.stabilizer->captureAfterLift();
    self.active.store(Impl::ActiveOperation::NONE);
    if (self.cancelled.load())
      continue;
    if (action.status != ActionStatus::SUCCEEDED) {
      static_cast<void>(self.stabilizer->cancel());
      return action;
    }
    if (auto stopped = persist(PhysicalGraspRetryPhase::VERIFY_PENDING))
      return *stopped;
    if (self.cancelled.load())
      continue;
    loaded = self.evidence->load();
    if (std::holds_alternative<Failure>(loaded))
      return {ActionStatus::FAILED, std::get<Failure>(std::move(loaded))};
    record = std::get<PhysicalGraspEvidenceRecord>(std::move(loaded));
  }
}

ActionResult PhysicalGraspRetryCoordinator::cancel()
{
  auto & self = *impl_;
  self.cancelled.store(true);
  switch (self.active.load()) {
    case Impl::ActiveOperation::GRIPPER:
      return self.gripper->cancelAndWait();
    case Impl::ActiveOperation::DESCEND:
      return self.micro_lift->cancelWorldZMicroDescend();
    case Impl::ActiveOperation::LIFT:
      return self.micro_lift->cancelWorldZMicroLift();
    case Impl::ActiveOperation::STABILIZER:
      return self.stabilizer->cancel();
    case Impl::ActiveOperation::NONE:
      return {ActionStatus::SUCCEEDED, std::nullopt};
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}
}  // namespace so101_gazebo_demo::pick_place
