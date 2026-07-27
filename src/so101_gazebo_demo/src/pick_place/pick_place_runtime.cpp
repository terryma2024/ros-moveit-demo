#include "so101_gazebo_demo/pick_place/pick_place_runtime.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <limits>
#include <set>
#include <sstream>
#include <thread>
#include <utility>

#include <Eigen/Geometry>

#include "so101_gazebo_demo/pick_place/so101_gripper_validation.hpp"
#include "so101_gazebo_demo/pick_place/so101_gripper_state.hpp"
#include "so101_gazebo_demo/pick_place/transition_table.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{

constexpr std::array<State, 10> kMotionStates{{
  State::MOVE_ABOVE_OBJECT,
  State::DESCEND,
  State::LIFT,
  State::MOVE_ABOVE_PLACE,
  State::DESCEND_TO_PLACE,
  State::RETREAT,
  State::RECOVER_LIFT_TO_SAFE_HEIGHT,
  State::RECOVER_MOVE_ABOVE_PICK,
  State::RECOVER_DESCEND_TO_PICK,
  State::RECOVER_RETREAT,
}};

bool finite(double value) { return std::isfinite(value); }

bool finitePose(const Pose3d & pose)
{
  const double norm = std::hypot(std::hypot(pose.qx, pose.qy),
                                 std::hypot(pose.qz, pose.qw));
  return finite(pose.x) && finite(pose.y) && finite(pose.z) && finite(pose.qx) &&
         finite(pose.qy) && finite(pose.qz) && finite(pose.qw) && finite(norm) &&
         norm > 1e-12;
}

double positionDistance(const Pose3d & first, const Pose3d & second)
{
  return std::hypot(std::hypot(first.x - second.x, first.y - second.y),
                    first.z - second.z);
}

double orientationDistance(const Pose3d & first, const Pose3d & second)
{
  if (!finitePose(first) || !finitePose(second)) {
    return std::numeric_limits<double>::infinity();
  }
  const Eigen::Quaterniond a(first.qw, first.qx, first.qy, first.qz);
  const Eigen::Quaterniond b(second.qw, second.qx, second.qy, second.qz);
  return 2.0 * std::acos(std::clamp(std::abs(a.normalized().dot(b.normalized())), 0.0, 1.0));
}

Pose3d relativePose(const Pose3d & frame, const Pose3d & object)
{
  if (!finitePose(frame) || !finitePose(object)) {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    return {nan, nan, nan, nan, nan, nan, nan};
  }
  const Eigen::Isometry3d world_frame =
    Eigen::Translation3d(frame.x, frame.y, frame.z) *
    Eigen::Quaterniond(frame.qw, frame.qx, frame.qy, frame.qz).normalized();
  const Eigen::Isometry3d world_object =
    Eigen::Translation3d(object.x, object.y, object.z) *
    Eigen::Quaterniond(object.qw, object.qx, object.qy, object.qz).normalized();
  const Eigen::Isometry3d relative = world_frame.inverse() * world_object;
  const Eigen::Quaterniond orientation(relative.rotation());
  return {relative.translation().x(), relative.translation().y(), relative.translation().z(),
          orientation.x(), orientation.y(), orientation.z(), orientation.w()};
}

bool poseWithin(const Pose3d & actual, const Pose3d & expected,
                double position_tolerance, double orientation_tolerance)
{
  return positionDistance(actual, expected) <= position_tolerance &&
         orientationDistance(actual, expected) <= orientation_tolerance;
}

Failure observationFailure(std::string code, std::string message)
{
  return {FailureCategory::OBSERVATION, std::move(code), std::move(message), {}};
}

void addFailure(ValidationResult & result, FailureCategory category, std::string code,
                std::string message)
{
  result.failures.push_back({category, std::move(code), std::move(message), {}});
  result.ok = false;
}

void merge(ValidationResult & result, ValidationResult additional)
{
  result.failures.insert(result.failures.end(), additional.failures.begin(),
                         additional.failures.end());
  result.metrics.insert(additional.metrics.begin(), additional.metrics.end());
  result.ok = result.failures.empty();
}

bool carrying(State state) { return isCarryingMotionState(state); }

ValidationResult validateMotionQ6(const WorldSnapshot & snapshot,
                                  double expected_q6,
                                  const SO101Profile & profile)
{
  if (std::abs(expected_q6 - profile.q6_full_open) <= profile.q6_tolerance) {
    return validateSO101GripperTarget(snapshot, SO101GripperTarget::FULL_OPEN, profile);
  }
  const double expected_width =
    std::abs(expected_q6 - profile.q6_contact) <= profile.q6_tolerance
      ? profile.contact_width : profile.preopen_width;
  return validateQ6Target(snapshot, expected_q6, expected_width, profile);
}

const Pose3d & expectedDetachedPose(State state, const SO101Profile & profile)
{
  return state == State::RETREAT ? profile.place_coke_pose : profile.coke_pose;
}

void requireCompleteSnapshot(ValidationResult & result, const WorldSnapshot & snapshot,
                             const SO101Profile & profile)
{
  if (!snapshot.fresh) {
    addFailure(result, FailureCategory::OBSERVATION, "STALE_WORLD_SNAPSHOT",
               "Motion requires a fresh combined world snapshot");
  }
  if (!snapshot.arm_stationary) {
    addFailure(result, FailureCategory::PRECONDITION, "ARM_NOT_QUIESCENT",
               "All SO-101 joints must be stationary at the motion boundary");
  }
  if (!finitePose(snapshot.tcp_pose_world)) {
    addFailure(result, FailureCategory::OBSERVATION, "TCP_POSE_EVIDENCE_INVALID",
               "A finite full TCP pose is required");
  }
  auto required = profile.arm_joints;
  required.push_back(profile.gripper_joint);
  for (const auto & name : required) {
    const auto position = snapshot.joint_positions.find(name);
    const auto velocity = snapshot.joint_velocities.find(name);
    if (position == snapshot.joint_positions.end() ||
        velocity == snapshot.joint_velocities.end() || !finite(position->second) ||
        !finite(velocity->second)) {
      addFailure(result, FailureCategory::OBSERVATION, "JOINT_EVIDENCE_INCOMPLETE",
                 "Finite position and velocity evidence is required for joints 1 through 6");
      break;
    }
  }
  const auto table = snapshot.moveit_world_object_poses.find(profile.table_object);
  if (table == snapshot.moveit_world_object_poses.end() ||
      !poseWithin(table->second, profile.table_pose, 1e-5, 1e-4)) {
    addFailure(result, FailureCategory::MOVEIT_SCENE, "TABLE_WORLD_POSE_MISMATCH",
               "The canonical MoveIt table pose is required");
  }
  if (!snapshot.gazebo_coke_pose_world || !finitePose(*snapshot.gazebo_coke_pose_world) ||
      !snapshot.gazebo_coke_attached || !snapshot.gazebo_coke_stationary ||
      !snapshot.moveit_coke_attached) {
    addFailure(result, FailureCategory::OBSERVATION, "ENVIRONMENT_EVIDENCE_INCOMPLETE",
               "Independent finite Gazebo and MoveIt Coke evidence is required");
  }
  if (snapshot.gazebo_coke_stationary && !*snapshot.gazebo_coke_stationary) {
    addFailure(result, FailureCategory::OBSERVATION, "GAZEBO_COKE_NOT_STATIONARY",
               "Gazebo Coke must be stationary at every motion boundary");
  }
}

void requireMotionEnvironment(ValidationResult & result, const WorldSnapshot & snapshot,
                              State state, const SO101Profile & profile)
{
  requireCompleteSnapshot(result, snapshot, profile);
  if (!snapshot.gazebo_coke_attached || !snapshot.moveit_coke_attached ||
      !snapshot.gazebo_coke_pose_world) {
    return;
  }
  const std::set<std::string> expected_touch_links(profile.moveit_touch_links.begin(),
                                                    profile.moveit_touch_links.end());
  if (carrying(state)) {
    if (!*snapshot.gazebo_coke_attached || !*snapshot.moveit_coke_attached ||
        snapshot.moveit_world_object_poses.count(profile.coke_model) != 0 ||
        !snapshot.moveit_coke_attached_link ||
        *snapshot.moveit_coke_attached_link != profile.moveit_attach_link ||
        snapshot.moveit_coke_touch_links != expected_touch_links ||
        !snapshot.moveit_coke_attached_relative_pose ||
        !snapshot.moveit_gripper_pose_world ||
        !poseWithin(*snapshot.moveit_coke_attached_relative_pose,
                    profile.calibrated_grasp_relative_pose,
                    profile.coke_position_drift_tolerance,
                    profile.coke_orientation_drift_tolerance_rad)) {
      addFailure(result, FailureCategory::WORLD_INCONSISTENCY,
                 "CARRYING_ATTACHMENT_EVIDENCE_INVALID",
                 "Carrying requires exact independent Gazebo and MoveIt attachment facts");
    }
    if (snapshot.moveit_gripper_pose_world &&
        !poseWithin(relativePose(*snapshot.moveit_gripper_pose_world,
                                 *snapshot.gazebo_coke_pose_world),
                    profile.calibrated_grasp_relative_pose,
                    profile.coke_position_drift_tolerance,
                    profile.coke_orientation_drift_tolerance_rad)) {
      addFailure(result, FailureCategory::WORLD_INCONSISTENCY,
                 "GAZEBO_COKE_GRIPPER_RELATIVE_POSE_INVALID",
                 "Gazebo Coke must match the independently observed gripper-relative pose");
    }
    return;
  }
  const auto moveit_coke = snapshot.moveit_world_object_poses.find(profile.coke_model);
  const auto & expected = expectedDetachedPose(state, profile);
  if (*snapshot.gazebo_coke_attached || *snapshot.moveit_coke_attached ||
      snapshot.moveit_coke_attached_link || !snapshot.moveit_coke_touch_links.empty() ||
      snapshot.moveit_coke_attached_relative_pose || moveit_coke == snapshot.moveit_world_object_poses.end() ||
      !poseWithin(moveit_coke->second, *snapshot.gazebo_coke_pose_world,
                  profile.coke_position_drift_tolerance,
                  profile.coke_orientation_drift_tolerance_rad) ||
      !poseWithin(*snapshot.gazebo_coke_pose_world, expected,
                  profile.coke_position_drift_tolerance,
                  profile.coke_orientation_drift_tolerance_rad)) {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY,
               "DETACHED_SUPPORT_EVIDENCE_INVALID",
               "Detached motion requires matching supported Gazebo and MoveIt Coke poses");
  }
}

class MotionAction final : public IStatePlanner, public IStateExecutor
{
public:
  MotionAction(State state, State next_state,
               std::shared_ptr<const SO101FixedMotionTargetPolicy> policy,
               std::shared_ptr<IMoveItJointMotionAdapter> motion, SO101Profile profile)
  : state_(state), next_state_(next_state), planner_(std::move(policy), motion, std::move(profile)),
    motion_(std::move(motion))
  {
  }

  PlanResult plan(State state, State next_state,
                  const ObservationResult & observation) override
  {
    if (state != state_ || next_state != next_state_) {
      return {{ActionStatus::NOT_SUPPORTED,
               Failure{FailureCategory::CONFIGURATION, "MOTION_STATE_MISMATCH",
                       "Motion planner is registered for a different state transition", {}}},
              nullptr};
    }
    return planner_.plan(state, next_state, observation);
  }

  ActionResult execute(const ExecutionContext & context) override
  {
    if (context.state != state_ || context.next_state != next_state_) {
      return {ActionStatus::NOT_SUPPORTED,
              Failure{FailureCategory::CONFIGURATION, "MOTION_STATE_MISMATCH",
                      "Motion executor is registered for a different state transition", {}}};
    }
    const auto artifact =
      std::dynamic_pointer_cast<const MotionPlanArtifact>(context.plan);
    if (!motion_ || !artifact) {
      return {ActionStatus::FAILED,
              Failure{FailureCategory::EXECUTION, "MOTION_ARTIFACT_INVALID",
                      "Execution requires the exact validated SO-101 motion artifact", {}}};
    }
    return motion_->execute(*artifact);
  }

  ActionResult cancel() override
  {
    return motion_ ? motion_->cancel()
                   : ActionResult{ActionStatus::FAILED,
                                  Failure{FailureCategory::CONFIGURATION,
                                          "MOTION_DEPENDENCY_MISSING",
                                          "SO-101 motion adapter is missing", {}}};
  }

private:
  State state_;
  State next_state_;
  SO101MotionPlanner planner_;
  std::shared_ptr<IMoveItJointMotionAdapter> motion_;
};

class RuntimeMotionPlanValidator final : public IPlanValidator
{
public:
  RuntimeMotionPlanValidator(SO101FixedMotionSpec spec, SO101Profile profile)
  : spec_(std::move(spec)), profile_(std::move(profile)),
    delegate_(spec_.validation, spec_.target.ladder)
  {
  }

  ValidationResult validate(State state, const WorldSnapshot & before,
                            const PlanArtifact & artifact) const override
  {
    if (state != spec_.state) {
      return {false,
              {{FailureCategory::CONFIGURATION, "MOTION_VALIDATOR_STATE_MISMATCH",
                "Motion validator is registered for another state", {}}},
              {}};
    }
    auto result = delegate_.validate(state, before, artifact);
    const auto * motion = dynamic_cast<const MotionPlanArtifact *>(&artifact);
    if (!motion) return result;
    if (motion->start_joint_positions.size() != profile_.arm_joints.size()) {
      addFailure(result, FailureCategory::PLAN_VALIDATION,
                 "PLAN_START_OBSERVATION_MISMATCH",
                 "Plan start must cover the observed SO-101 arm joints");
      return result;
    }
    for (std::size_t i = 0; i < profile_.arm_joints.size(); ++i) {
      const auto observed = before.joint_positions.find(profile_.arm_joints[i]);
      if (observed == before.joint_positions.end() || !finite(observed->second) ||
          std::abs(observed->second - motion->start_joint_positions[i]) >
            spec_.validation.joint_endpoint_tolerance) {
        addFailure(result, FailureCategory::PLAN_VALIDATION,
                   "PLAN_START_OBSERVATION_MISMATCH",
                   "Validated trajectory start does not match the observed arm state");
        break;
      }
    }
    if (carrying(state) && before.gazebo_coke_pose_world && finitePose(before.tcp_pose_world)) {
      const auto expected_relative =
        relativePose(before.tcp_pose_world, *before.gazebo_coke_pose_world);
      for (std::size_t i = 0; i < motion->samples.size(); ++i) {
        if (!motion->samples[i].attached_coke_pose_world ||
            !poseWithin(relativePose(motion->samples[i].tcp_pose,
                                     *motion->samples[i].attached_coke_pose_world),
                        expected_relative, profile_.coke_position_drift_tolerance,
                        profile_.coke_orientation_drift_tolerance_rad)) {
          addFailure(result, FailureCategory::PLAN_VALIDATION,
                     "ATTACHED_COKE_RELATIVE_PATH_MISMATCH",
                     "Every carrying sample must preserve the observed TCP-Coke relative pose");
          break;
        }
      }
    }
    result.ok = result.failures.empty();
    return result;
  }

private:
  SO101FixedMotionSpec spec_;
  SO101Profile profile_;
  SO101MotionPlanValidator delegate_;
};

class MotionContract final : public TransitionContractRegistry::ITransitionContract
{
public:
  MotionContract(SO101FixedMotionSpec spec, SO101Profile profile)
  : spec_(std::move(spec)), profile_(std::move(profile))
  {
  }

  ValidationResult validatePrecondition(const WorldSnapshot & before) const override
  {
    ValidationResult result{true, {}, {}};
    requireMotionEnvironment(result, before, spec_.state, profile_);
    merge(result, validateMotionQ6(before, spec_.expected_gripper_q6, profile_));
    result.ok = result.failures.empty();
    return result;
  }

  ValidationResult validate(const WorldSnapshot & before, const WorldSnapshot & after,
                            const ActionResult & action) const override
  {
    ValidationResult result{true, {}, {}};
    if (action.status != ActionStatus::SUCCEEDED) {
      addFailure(result, FailureCategory::EXECUTION, "ACTION_DID_NOT_SUCCEED",
                 "Motion action did not report success");
    }
    requireMotionEnvironment(result, after, spec_.state, profile_);
    merge(result, validateMotionQ6(after, spec_.expected_gripper_q6, profile_));
    for (std::size_t i = 0; i < profile_.arm_joints.size(); ++i) {
      const auto joint = after.joint_positions.find(profile_.arm_joints[i]);
      if (joint == after.joint_positions.end() || !finite(joint->second) ||
          std::abs(joint->second - spec_.target.joint_waypoints.back()[i]) >
            spec_.validation.joint_endpoint_tolerance) {
        addFailure(result, FailureCategory::POSTCONDITION,
                   "MOTION_JOINT_ENDPOINT_MISMATCH",
                   "Observed arm endpoint does not match the validated trajectory goal");
        break;
      }
    }
    const Pose3d endpoint{spec_.validation.endpoint_position.x,
                          spec_.validation.endpoint_position.y,
                          spec_.validation.endpoint_position.z, 0.0, 0.0, 0.0, 1.0};
    const double endpoint_error = positionDistance(after.tcp_pose_world, endpoint);
    const double axis_error = approachAxisError(after.tcp_pose_world,
                                                spec_.validation.local_approach_axis,
                                                spec_.validation.target_approach_axis);
    result.metrics["tcp_endpoint_error"] = endpoint_error;
    result.metrics["tcp_axis_error"] = axis_error;
    if (!finite(endpoint_error) || endpoint_error > spec_.validation.position_tolerance) {
      addFailure(result, FailureCategory::POSTCONDITION, "TCP_ENDPOINT_OUTSIDE_TOLERANCE",
                 "Observed TCP endpoint is outside the state-specific tolerance");
    }
    if (!finite(axis_error) || axis_error > spec_.validation.axis_tolerance_rad) {
      addFailure(result, FailureCategory::POSTCONDITION, "TCP_AXIS_OUTSIDE_TOLERANCE",
                 "Observed TCP tool axis is outside the state-specific tolerance");
    }
    if (before.gazebo_coke_pose_world && after.gazebo_coke_pose_world) {
      Pose3d before_evidence = *before.gazebo_coke_pose_world;
      Pose3d after_evidence = *after.gazebo_coke_pose_world;
      if (carrying(spec_.state)) {
        before_evidence = relativePose(before.tcp_pose_world, before_evidence);
        after_evidence = relativePose(after.tcp_pose_world, after_evidence);
      }
      const double coke_position = positionDistance(before_evidence, after_evidence);
      const double coke_orientation = orientationDistance(before_evidence, after_evidence);
      result.metrics[carrying(spec_.state) ? "coke_follow_position_error"
                                           : "coke_position_drift"] = coke_position;
      result.metrics[carrying(spec_.state) ? "coke_follow_orientation_error_rad"
                                           : "coke_orientation_drift_rad"] = coke_orientation;
      if (coke_position > profile_.coke_position_drift_tolerance ||
          coke_orientation > profile_.coke_orientation_drift_tolerance_rad) {
        addFailure(result, FailureCategory::POSTCONDITION,
                   carrying(spec_.state) ? "COKE_DID_NOT_FOLLOW_GRIPPER"
                                         : "DETACHED_COKE_DRIFT",
                   carrying(spec_.state)
                     ? "Gazebo Coke did not preserve its relative pose while carried"
                     : "Detached Gazebo Coke moved while the arm moved");
      }
    }
    result.ok = result.failures.empty();
    for (auto & failure : result.failures) {
      failure.metrics.insert(result.metrics.begin(), result.metrics.end());
    }
    return result;
  }

private:
  SO101FixedMotionSpec spec_;
  SO101Profile profile_;
};

std::optional<Failure> missingDependencyFailure(
  const SO101PickPlaceRuntimeDependencies & dependencies)
{
  std::vector<std::string> missing;
  if (!dependencies.gripper) missing.emplace_back("gripper");
  if (!dependencies.moveit_scene) missing.emplace_back("moveit_scene");
  if (!dependencies.gazebo_attach) missing.emplace_back("gazebo_attach");
  if (!dependencies.gazebo_detach) missing.emplace_back("gazebo_detach");
  if (!dependencies.recovery_gazebo_detach) missing.emplace_back("recovery_gazebo_detach");
  if (!dependencies.motion_policy) missing.emplace_back("motion_policy");
  if (!dependencies.motion) missing.emplace_back("motion");
  if (missing.empty()) return std::nullopt;
  std::ostringstream message;
  message << "Production SO-101 runtime dependencies are missing:";
  for (const auto & name : missing) message << ' ' << name;
  return Failure{FailureCategory::CONFIGURATION, "RUNTIME_DEPENDENCY_MISSING",
                 message.str(), {}};
}

}  // namespace

SO101MoveItWorldObserver::SO101MoveItWorldObserver(
  std::shared_ptr<IJointPlanningBoundary> boundary, SO101Profile profile,
  SO101WorldObservationConfig config)
: boundary_(std::move(boundary)), profile_(std::move(profile)), config_(config)
{
}

ObservationResult SO101MoveItWorldObserver::observe()
{
  if (!boundary_) {
    return {std::nullopt, observationFailure("MOVEIT_OBSERVER_DEPENDENCY_MISSING",
                                             "MoveIt observation boundary is missing")};
  }
  if (!finite(config_.max_age_seconds) || config_.max_age_seconds <= 0.0 ||
      config_.settle_samples == 0 || !finite(config_.settle_interval_seconds) ||
      config_.settle_interval_seconds < 0.0 || !finite(config_.joint_settle_tolerance) ||
      config_.joint_settle_tolerance < 0.0) {
    return {std::nullopt, observationFailure("WORLD_OBSERVER_CONFIG_INVALID",
                                             "World observer timing and settle limits are invalid")};
  }
  std::optional<CurrentJointStateEvidence> previous;
  std::optional<CurrentJointStateEvidence> current;
  bool stationary = true;
  const auto validate_current = [this](
    const std::optional<CurrentJointStateEvidence> & evidence) -> std::optional<Failure> {
      if (!evidence || evidence->joint_names != profile_.arm_joints ||
          evidence->positions.size() != profile_.arm_joints.size() ||
          evidence->velocities.size() != profile_.arm_joints.size() ||
          !evidence->gripper_position || !evidence->gripper_velocity) {
        return observationFailure("JOINT_EVIDENCE_INCOMPLETE",
                                  "Joint 1 through 6 evidence is incomplete");
      }
      const auto now = std::chrono::steady_clock::now();
      if (evidence->received_at == std::chrono::steady_clock::time_point{} ||
          evidence->received_at > now ||
          now - evidence->received_at >
            std::chrono::duration<double>(config_.max_age_seconds)) {
        return observationFailure("JOINT_EVIDENCE_STALE",
                                  "Joint 1 through 6 evidence is stale");
      }
      for (std::size_t i = 0; i < evidence->positions.size(); ++i) {
        if (!finite(evidence->positions[i]) || !finite(evidence->velocities[i])) {
          return observationFailure("JOINT_EVIDENCE_NONFINITE",
                                    "Joint position or velocity is non-finite");
        }
      }
      if (!finite(*evidence->gripper_position) || !finite(*evidence->gripper_velocity)) {
        return observationFailure("JOINT_EVIDENCE_NONFINITE",
                                  "Joint 6 evidence is non-finite");
      }
      return std::nullopt;
    };
  for (std::size_t sample = 0; sample < config_.settle_samples; ++sample) {
    current = boundary_->currentState();
    if (auto failure = validate_current(current)) return {std::nullopt, std::move(failure)};
    for (std::size_t i = 0; i < current->positions.size(); ++i) {
      stationary = stationary &&
                   std::abs(current->velocities[i]) <= profile_.q6_velocity_tolerance;
      if (previous && std::abs(previous->positions[i] - current->positions[i]) >
                        config_.joint_settle_tolerance) {
        stationary = false;
      }
    }
    stationary = stationary &&
                 std::abs(*current->gripper_velocity) <= profile_.q6_velocity_tolerance;
    if (previous && std::abs(*previous->gripper_position - *current->gripper_position) >
                      config_.joint_settle_tolerance) {
      stationary = false;
    }
    previous = current;
    if (sample + 1 < config_.settle_samples && config_.settle_interval_seconds > 0.0) {
      std::this_thread::sleep_for(
        std::chrono::duration<double>(config_.settle_interval_seconds));
    }
  }

  const auto scene = boundary_->sceneFacts();
  if (!scene || !scene->table_in_world || !scene->table_world_pose ||
      !finitePose(*scene->table_world_pose) || !scene->pedestal_in_world ||
      !scene->pedestal_world_pose || !finitePose(*scene->pedestal_world_pose) ||
      !scene->current_tcp_pose_world ||
      !finitePose(*scene->current_tcp_pose_world) ||
      !poseWithin(*scene->table_world_pose, profile_.table_pose, 1e-5, 1e-4) ||
      !poseWithin(*scene->pedestal_world_pose, profile_.pedestal_pose, 1e-5, 1e-4)) {
    return {std::nullopt, observationFailure("MOVEIT_SCENE_EVIDENCE_INCOMPLETE",
                                             "Canonical table, pedestal, and finite TCP evidence are required")};
  }
  if (scene->coke_in_world == scene->coke_attached) {
    return {std::nullopt, observationFailure("MOVEIT_COKE_MEMBERSHIP_INCONSISTENT",
                                             "Coke must be exactly world or attached in MoveIt")};
  }
  if ((scene->coke_in_world && (!scene->coke_world_pose || !finitePose(*scene->coke_world_pose))) ||
      (scene->coke_attached && (!scene->attached_link || scene->touch_links.empty() ||
                                !scene->attached_relative_pose ||
                                !finitePose(*scene->attached_relative_pose) ||
                                !scene->current_gripper_pose_world ||
                                !finitePose(*scene->current_gripper_pose_world)))) {
    return {std::nullopt, observationFailure("MOVEIT_COKE_POSE_EVIDENCE_INCOMPLETE",
                                             "MoveIt Coke 6D pose and attachment metadata are incomplete")};
  }
  if (!scene->coke_attached &&
      (scene->attached_link || !scene->touch_links.empty() || scene->attached_relative_pose)) {
    return {std::nullopt, observationFailure("MOVEIT_COKE_MEMBERSHIP_INCONSISTENT",
                                             "Detached Coke retains attachment metadata")};
  }

  previous = current;
  current = boundary_->currentState();
  if (auto failure = validate_current(current)) return {std::nullopt, std::move(failure)};
  for (std::size_t i = 0; i < current->positions.size(); ++i) {
    if (std::abs(previous->positions[i] - current->positions[i]) >
        config_.joint_settle_tolerance) {
      return {std::nullopt,
              observationFailure("ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION",
                                 "Arm joints changed while MoveIt scene evidence was collected")};
    }
    stationary = stationary &&
                 std::abs(current->velocities[i]) <= profile_.q6_velocity_tolerance;
  }
  if (std::abs(*previous->gripper_position - *current->gripper_position) >
      config_.joint_settle_tolerance) {
    return {std::nullopt,
            observationFailure("ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION",
                               "Gripper joint changed while MoveIt scene evidence was collected")};
  }
  stationary = stationary &&
               std::abs(*current->gripper_velocity) <= profile_.q6_velocity_tolerance;

  WorldSnapshot snapshot;
  snapshot.observed_at = current->received_at;
  snapshot.fresh = true;
  snapshot.arm_stationary = stationary;
  snapshot.tcp_pose_world = *scene->current_tcp_pose_world;
  for (std::size_t i = 0; i < profile_.arm_joints.size(); ++i) {
    snapshot.joint_positions[profile_.arm_joints[i]] = current->positions[i];
    snapshot.joint_velocities[profile_.arm_joints[i]] = current->velocities[i];
  }
  snapshot.joint_positions[profile_.gripper_joint] = *current->gripper_position;
  snapshot.joint_velocities[profile_.gripper_joint] = *current->gripper_velocity;
  snapshot.gripper_open = *current->gripper_position >= profile_.q6_preopen - profile_.q6_tolerance;
  snapshot.moveit_world_object_poses[profile_.table_object] = *scene->table_world_pose;
  snapshot.moveit_world_object_poses[profile_.pedestal_object] = *scene->pedestal_world_pose;
  if (scene->coke_world_pose) {
    snapshot.moveit_world_object_poses[profile_.coke_model] = *scene->coke_world_pose;
  }
  snapshot.moveit_coke_attached = scene->coke_attached;
  snapshot.moveit_coke_attached_link = scene->attached_link;
  snapshot.moveit_coke_touch_links = scene->touch_links;
  snapshot.moveit_coke_attached_relative_pose = scene->attached_relative_pose;
  snapshot.moveit_gripper_pose_world = scene->current_gripper_pose_world;
  return {std::move(snapshot), std::nullopt};
}

std::shared_ptr<const TransitionContractRegistry::ITransitionContract>
makeSO101MotionContract(const SO101FixedMotionSpec & spec, SO101Profile profile)
{
  if (std::find(kMotionStates.begin(), kMotionStates.end(), spec.state) == kMotionStates.end() ||
      spec.target.joint_waypoints.empty()) {
    return {};
  }
  return std::make_shared<MotionContract>(spec, std::move(profile));
}

SO101PickPlaceRuntimeRegistries makeSO101PickPlaceRuntimeRegistries(
  const SO101PickPlaceRuntimeDependencies & dependencies, SO101PickPlaceRuntimeConfig config)
{
  auto task3 = makeSO101Task3Runtime(dependencies, config);
  SO101PickPlaceRuntimeRegistries runtime{std::move(task3.actions), {},
                                          std::move(task3.contracts),
                                          std::move(task3.recovery_policy), false, std::nullopt};
  runtime.configuration_failure = missingDependencyFailure(dependencies);
  if (!dependencies.motion_policy || !dependencies.motion) return runtime;

  for (const auto state : kMotionStates) {
    const auto spec = dependencies.motion_policy->spec(state);
    if (!spec) {
      runtime.configuration_failure =
        Failure{FailureCategory::CONFIGURATION, "MOTION_SPEC_MISSING",
                std::string("Canonical motion specification missing for ") + toString(state), {}};
      return runtime;
    }
    const auto next = TransitionTable::resolve(state, ActionStatus::SUCCEEDED);
    auto action = std::make_shared<MotionAction>(state, next, dependencies.motion_policy,
                                                 dependencies.motion, config.profile);
    runtime.actions.registerPlanner(state, action);
    runtime.actions.registerExecutor(state, action);
    runtime.plan_validators.registerValidator(
      state, std::make_shared<RuntimeMotionPlanValidator>(*spec, config.profile));
    runtime.contracts.registerContract({state, next},
                                       makeSO101MotionContract(*spec, config.profile));
  }
  if (runtime.configuration_failure) return runtime;
  for (const auto & [state, transitions] : TransitionTable::entries()) {
    if (state == State::IDLE || isTerminal(state)) continue;
    if (!runtime.actions.findExecutor(state) ||
        !runtime.contracts.hasContract({state, transitions.succeeded})) {
      runtime.configuration_failure =
        Failure{FailureCategory::CONFIGURATION, "RUNTIME_REGISTRY_INCOMPLETE",
                std::string("Runtime registry is incomplete at ") + toString(state), {}};
      return runtime;
    }
    const bool needs_plan =
      std::find(kMotionStates.begin(), kMotionStates.end(), state) != kMotionStates.end();
    if ((runtime.actions.findPlanner(state) != nullptr) != needs_plan ||
        runtime.plan_validators.hasValidator(state) != needs_plan) {
      runtime.configuration_failure =
        Failure{FailureCategory::CONFIGURATION, "RUNTIME_REGISTRY_INCOMPLETE",
                std::string("Runtime planning registry is incomplete at ") + toString(state), {}};
      return runtime;
    }
  }
  runtime.execution_safe = true;
  return runtime;
}

}  // namespace so101_gazebo_demo::pick_place
