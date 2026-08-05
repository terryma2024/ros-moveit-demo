#include "so101_gazebo_demo/pick_place/pick_place_runtime.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <limits>
#include <set>
#include <sstream>
#include <mutex>
#include <thread>
#include <utility>

#include <Eigen/Geometry>

#include "so101_gazebo_demo/pick_place/so101_gripper_validation.hpp"
#include "so101_gazebo_demo/pick_place/so101_gripper_state.hpp"
#include "so101_gazebo_demo/pick_place/support_pose.hpp"
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

constexpr std::array<State, 4> kPhysicalGraspStates{{
  State::WAIT_GRASP_STABLE,
  State::MICRO_LIFT,
  State::WAIT_MICRO_LIFT_STABLE,
  State::VERIFY_PHYSICAL_GRASP,
}};

bool finite(double value)
{
  return std::isfinite(value);
}

double wallNormalPositionError(const Pose3d & actual, const Pose3d & expected, const Vec3 & outward)
{
  const double magnitude = std::hypot(outward.x, std::hypot(outward.y, outward.z));
  if (!isFinitePose(actual) || !isFinitePose(expected) || !finite(magnitude) ||
      magnitude <= 1e-12) {
    return std::numeric_limits<double>::infinity();
  }
  const double projected = (actual.x - expected.x) * outward.x +
                           (actual.y - expected.y) * outward.y +
                           (actual.z - expected.z) * outward.z;
  return std::abs(projected) / magnitude;
}

// SO-101 owns axial tilt: cylindrical cups permit yaw while constraining the local Z axis.
double axialTiltDistance(const Pose3d & first, const Pose3d & second)
{
  if (!isFinitePose(first) || !isFinitePose(second)) {
    return std::numeric_limits<double>::infinity();
  }
  const Eigen::Vector3d first_axis =
    Eigen::Quaterniond(first.qw, first.qx, first.qy, first.qz).normalized() *
    Eigen::Vector3d::UnitZ();
  const Eigen::Vector3d second_axis =
    Eigen::Quaterniond(second.qw, second.qx, second.qy, second.qz).normalized() *
    Eigen::Vector3d::UnitZ();
  return std::acos(std::clamp(first_axis.dot(second_axis), -1.0, 1.0));
}

Pose3d invalidPose()
{
  const double nan = std::numeric_limits<double>::quiet_NaN();
  return {nan, nan, nan, nan, nan, nan, nan};
}

bool poseWithin(const Pose3d & actual, const Pose3d & expected, double position_tolerance,
                double orientation_tolerance)
{
  return positionDistance(actual, expected) <= position_tolerance &&
         orientationDistance(actual, expected) <= orientation_tolerance;
}

bool cylindricalPoseWithin(const Pose3d & actual, const Pose3d & expected,
                           double position_tolerance, double tilt_tolerance)
{
  return positionDistance(actual, expected) <= position_tolerance &&
         axialTiltDistance(actual, expected) <= tilt_tolerance;
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

bool carrying(State state)
{
  return isCarryingMotionState(state);
}

ValidationResult validateMotionQ6(const WorldSnapshot & snapshot, double expected_q6,
                                  const SO101Profile & profile)
{
  if (std::abs(expected_q6 - profile.q6_full_open) <= profile.q6_tolerance) {
    return validateSO101GripperTarget(snapshot, SO101GripperTarget::FULL_OPEN, profile);
  }
  const double expected_width = std::abs(expected_q6 - profile.q6_contact) <= profile.q6_tolerance
                                  ? profile.contact_width
                                  : profile.preopen_width;
  return validateQ6Target(snapshot, expected_q6, expected_width, profile);
}

const Pose3d & expectedDetachedPose(State state, const SO101Profile & profile)
{
  return state == State::RETREAT ? profile.place_task_object_pose : profile.task_object_pose;
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
  if (!isFinitePose(snapshot.tcp_pose_world)) {
    addFailure(result, FailureCategory::OBSERVATION, "TCP_POSE_EVIDENCE_INVALID",
               "A finite full TCP pose is required");
  }
  auto required = profile.arm_joints;
  required.push_back(profile.gripper_joint);
  for (const auto & name : required) {
    const auto position = snapshot.joint_positions.find(name);
    const auto velocity = snapshot.joint_velocities.find(name);
    if (position == snapshot.joint_positions.end() || velocity == snapshot.joint_velocities.end() ||
        !finite(position->second) || !finite(velocity->second)) {
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
  if (!snapshot.gazebo_task_object_pose_world ||
      !isFinitePose(*snapshot.gazebo_task_object_pose_world) ||
      !snapshot.gazebo_task_object_attached || !snapshot.gazebo_task_object_stationary ||
      !snapshot.moveit_task_object_attached) {
    addFailure(result, FailureCategory::OBSERVATION, "ENVIRONMENT_EVIDENCE_INCOMPLETE",
               "Independent finite Gazebo and MoveIt TaskObject evidence is required");
  }
  if (snapshot.gazebo_task_object_stationary && !*snapshot.gazebo_task_object_stationary) {
    addFailure(result, FailureCategory::OBSERVATION, "GAZEBO_TASK_OBJECT_NOT_STATIONARY",
               "Gazebo TaskObject must be stationary at every motion boundary");
  }
}

void requireMotionEnvironment(ValidationResult & result, const WorldSnapshot & snapshot,
                              State state, const SO101Profile & profile)
{
  requireCompleteSnapshot(result, snapshot, profile);
  if (!snapshot.gazebo_task_object_attached || !snapshot.moveit_task_object_attached ||
      !snapshot.gazebo_task_object_pose_world) {
    return;
  }
  const std::set<std::string> expected_touch_links(profile.moveit_touch_links.begin(),
                                                   profile.moveit_touch_links.end());
  if (carrying(state)) {
    if (!*snapshot.gazebo_task_object_attached || !*snapshot.moveit_task_object_attached ||
        snapshot.moveit_world_object_poses.count(profile.task_object_id) != 0 ||
        !snapshot.moveit_task_object_attached_link ||
        *snapshot.moveit_task_object_attached_link != profile.moveit_attach_link ||
        snapshot.moveit_task_object_touch_links != expected_touch_links ||
        !snapshot.moveit_task_object_attached_relative_pose ||
        !snapshot.moveit_gripper_pose_world ||
        !cylindricalPoseWithin(*snapshot.moveit_task_object_attached_relative_pose,
                               profile.calibrated_grasp_relative_pose,
                               profile.task_object_position_drift_tolerance,
                               profile.task_object_attachment_orientation_tolerance_rad)) {
      addFailure(result, FailureCategory::WORLD_INCONSISTENCY,
                 "CARRYING_ATTACHMENT_EVIDENCE_INVALID",
                 "Carrying requires exact independent Gazebo and MoveIt attachment facts");
    }
    if (snapshot.moveit_gripper_pose_world &&
        !cylindricalPoseWithin(
          relativePose(*snapshot.moveit_gripper_pose_world, *snapshot.gazebo_task_object_pose_world)
            .value_or(invalidPose()),
          profile.calibrated_grasp_relative_pose, profile.task_object_position_drift_tolerance,
          profile.task_object_attachment_orientation_tolerance_rad)) {
      addFailure(result, FailureCategory::WORLD_INCONSISTENCY,
                 "GAZEBO_TASK_OBJECT_GRIPPER_RELATIVE_POSE_INVALID",
                 "Gazebo TaskObject must match the independently observed gripper-relative pose");
    }
    return;
  }
  const auto moveit_task_object = snapshot.moveit_world_object_poses.find(profile.task_object_id);
  const auto & expected = expectedDetachedPose(state, profile);
  const bool at_pick_pose = poseWithin(*snapshot.gazebo_task_object_pose_world, expected,
                                       profile.task_object_position_drift_tolerance,
                                       profile.task_object_orientation_drift_tolerance_rad);
  const bool at_pick_support = supportedAtPick(*snapshot.gazebo_task_object_pose_world, profile);
  const bool at_place_support = supportedAtPlace(*snapshot.gazebo_task_object_pose_world, profile);
  const bool expected_support =
    state == State::RETREAT
      ? at_place_support
      : (state == State::RECOVER_RETREAT ? at_pick_support || at_place_support : at_pick_pose);
  if (*snapshot.gazebo_task_object_attached || *snapshot.moveit_task_object_attached ||
      snapshot.moveit_task_object_attached_link ||
      !snapshot.moveit_task_object_touch_links.empty() ||
      snapshot.moveit_task_object_attached_relative_pose ||
      moveit_task_object == snapshot.moveit_world_object_poses.end() ||
      !poseWithin(moveit_task_object->second, *snapshot.gazebo_task_object_pose_world,
                  profile.task_object_position_drift_tolerance,
                  profile.task_object_orientation_drift_tolerance_rad) ||
      !expected_support) {
    addFailure(result, FailureCategory::WORLD_INCONSISTENCY, "DETACHED_SUPPORT_EVIDENCE_INVALID",
               "Detached motion requires matching supported Gazebo and MoveIt TaskObject poses");
  }
}

class MotionAction final : public IStatePlanner, public IStateExecutor
{
public:
  MotionAction(State state, State next_state,
               std::shared_ptr<const SO101ConfiguredMotionTargetPolicy> policy,
               std::shared_ptr<IMoveItJointMotionAdapter> motion, SO101Profile profile) :
      state_(state), next_state_(next_state),
      planner_(std::move(policy), motion, std::move(profile)), motion_(std::move(motion))
  {
  }

  PlanResult plan(State state, State next_state, const ObservationResult & observation) override
  {
    if (state != state_ || next_state != next_state_) {
      return {{ActionStatus::NOT_SUPPORTED,
               Failure{FailureCategory::CONFIGURATION,
                       "MOTION_STATE_MISMATCH",
                       "Motion planner is registered for a different state transition",
                       {}}},
              nullptr};
    }
    return planner_.plan(state, next_state, observation);
  }

  ActionResult execute(const ExecutionContext & context) override
  {
    if (context.state != state_ || context.next_state != next_state_) {
      return {ActionStatus::NOT_SUPPORTED,
              Failure{FailureCategory::CONFIGURATION,
                      "MOTION_STATE_MISMATCH",
                      "Motion executor is registered for a different state transition",
                      {}}};
    }
    const auto artifact = std::dynamic_pointer_cast<const MotionPlanArtifact>(context.plan);
    if (!motion_ || !artifact) {
      return {ActionStatus::FAILED,
              Failure{FailureCategory::EXECUTION,
                      "MOTION_ARTIFACT_INVALID",
                      "Execution requires the exact validated SO-101 motion artifact",
                      {}}};
    }
    return motion_->execute(*artifact);
  }

  ActionResult cancel() override
  {
    return motion_ ? motion_->cancel()
                   : ActionResult{ActionStatus::FAILED, Failure{FailureCategory::CONFIGURATION,
                                                                "MOTION_DEPENDENCY_MISSING",
                                                                "SO-101 motion adapter is missing",
                                                                {}}};
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
  RuntimeMotionPlanValidator(SO101FixedMotionSpec spec, SO101Profile profile) :
      spec_(std::move(spec)), profile_(std::move(profile)),
      delegate_(spec_.validation, spec_.require_axial_path_validation)
  {
  }

  [[nodiscard]] ValidationResult validate(State state, const WorldSnapshot & before,
                                          const PlanArtifact & artifact) const override
  {
    if (state != spec_.state) {
      return {false,
              {{FailureCategory::CONFIGURATION,
                "MOTION_VALIDATOR_STATE_MISMATCH",
                "Motion validator is registered for another state",
                {}}},
              {}};
    }
    auto result = delegate_.validate(state, before, artifact);
    const auto * motion = dynamic_cast<const MotionPlanArtifact *>(&artifact);
    if (!motion)
      return result;
    if (motion->start_joint_positions.size() != profile_.arm_joints.size()) {
      addFailure(result, FailureCategory::PLAN_VALIDATION, "PLAN_START_OBSERVATION_MISMATCH",
                 "Plan start must cover the observed SO-101 arm joints");
      return result;
    }
    for (std::size_t i = 0; i < profile_.arm_joints.size(); ++i) {
      const auto observed = before.joint_positions.find(profile_.arm_joints[i]);
      if (observed == before.joint_positions.end() || !finite(observed->second) ||
          std::abs(observed->second - motion->start_joint_positions[i]) >
            spec_.validation.joint_endpoint_tolerance) {
        addFailure(result, FailureCategory::PLAN_VALIDATION, "PLAN_START_OBSERVATION_MISMATCH",
                   "Validated trajectory start does not match the observed arm state");
        break;
      }
    }
    if (carrying(state) && before.gazebo_task_object_pose_world &&
        isFinitePose(before.tcp_pose_world)) {
      const auto expected_relative =
        relativePose(before.tcp_pose_world, *before.gazebo_task_object_pose_world)
          .value_or(invalidPose());
      for (const auto & sample : motion->samples) {
        if (!sample.attached_task_object_pose_world ||
            !withinSO101AttachmentModelTolerance(
              relativePose(sample.tcp_pose, *sample.attached_task_object_pose_world)
                .value_or(invalidPose()),
              expected_relative, profile_)) {
          addFailure(
            result, FailureCategory::PLAN_VALIDATION, "ATTACHED_TASK_OBJECT_RELATIVE_PATH_MISMATCH",
            "Every carrying sample must preserve the observed TCP-TaskObject relative pose");
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
  MotionContract(SO101FixedMotionSpec spec, SO101Profile profile) :
      spec_(std::move(spec)), profile_(std::move(profile))
  {
  }

  [[nodiscard]] ValidationResult validatePrecondition(const WorldSnapshot & before) const override
  {
    ValidationResult result{true, {}, {}};
    requireMotionEnvironment(result, before, spec_.state, profile_);
    merge(result, validateMotionQ6(before, spec_.expected_gripper_q6, profile_));
    result.ok = result.failures.empty();
    return result;
  }

  [[nodiscard]] ValidationResult validate(const WorldSnapshot & before, const WorldSnapshot & after,
                                          const ActionResult & action) const override
  {
    ValidationResult result{true, {}, {}};
    if (action.status != ActionStatus::SUCCEEDED) {
      addFailure(result, FailureCategory::EXECUTION, "ACTION_DID_NOT_SUCCEED",
                 "Motion action did not report success");
    }
    requireMotionEnvironment(result, after, spec_.state, profile_);
    merge(result, validateMotionQ6(after, spec_.expected_gripper_q6, profile_));
    double max_joint_endpoint_error = 0.0;
    for (std::size_t i = 0; i < profile_.arm_joints.size(); ++i) {
      const auto joint = after.joint_positions.find(profile_.arm_joints[i]);
      if (joint != after.joint_positions.end() && finite(joint->second)) {
        max_joint_endpoint_error =
          std::max(max_joint_endpoint_error,
                   std::abs(joint->second - spec_.target.joint_waypoints.back()[i]));
      }
      if (joint == after.joint_positions.end() || !finite(joint->second) ||
          std::abs(joint->second - spec_.target.joint_waypoints.back()[i]) >
            spec_.validation.joint_endpoint_tolerance) {
        addFailure(result, FailureCategory::POSTCONDITION, "MOTION_JOINT_ENDPOINT_MISMATCH",
                   "Observed arm endpoint does not match the validated trajectory goal");
        break;
      }
    }
    result.metrics["max_joint_endpoint_error"] = max_joint_endpoint_error;
    const Pose3d endpoint{spec_.validation.endpoint_position.x,
                          spec_.validation.endpoint_position.y,
                          spec_.validation.endpoint_position.z,
                          0.0,
                          0.0,
                          0.0,
                          1.0};
    const double endpoint_error = positionDistance(after.tcp_pose_world, endpoint);
    const double axis_error =
      approachAxisError(after.tcp_pose_world, spec_.validation.local_approach_axis,
                        spec_.validation.target_approach_axis);
    result.metrics["tcp_endpoint_error"] = endpoint_error;
    result.metrics["tcp_axis_error"] = axis_error;
    if (!finite(endpoint_error) || endpoint_error > spec_.validation.position_tolerance) {
      addFailure(result, FailureCategory::POSTCONDITION, "TCP_ENDPOINT_OUTSIDE_TOLERANCE",
                 "Observed TCP endpoint is outside the state-specific tolerance");
    }
    if (spec_.validation.contact_wall_normal_endpoint_tolerance) {
      const double normal_error = wallNormalPositionError(after.tcp_pose_world, endpoint,
                                                          profile_.task_object_near_wall_outward);
      result.metrics["contact_wall_normal_endpoint_error"] = normal_error;
      result.metrics["contact_wall_normal_endpoint_tolerance"] =
        *spec_.validation.contact_wall_normal_endpoint_tolerance;
      if (!finite(normal_error) ||
          normal_error > *spec_.validation.contact_wall_normal_endpoint_tolerance) {
        addFailure(
          result, FailureCategory::POSTCONDITION, "CONTACT_CRITICAL_WALL_NORMAL_ENDPOINT_MISMATCH",
          "Observed URDF-FK TCP endpoint is outside the contact-critical wall-normal tolerance");
      }
    }
    if (!finite(axis_error) || axis_error > spec_.validation.axis_tolerance_rad) {
      addFailure(result, FailureCategory::POSTCONDITION, "TCP_AXIS_OUTSIDE_TOLERANCE",
                 "Observed TCP tool axis is outside the state-specific tolerance");
    }
    if (before.gazebo_task_object_pose_world && after.gazebo_task_object_pose_world) {
      Pose3d before_evidence = *before.gazebo_task_object_pose_world;
      Pose3d after_evidence = *after.gazebo_task_object_pose_world;
      if (carrying(spec_.state)) {
        before_evidence =
          relativePose(before.tcp_pose_world, before_evidence).value_or(invalidPose());
        after_evidence = relativePose(after.tcp_pose_world, after_evidence).value_or(invalidPose());
      }
      const double task_object_position = positionDistance(before_evidence, after_evidence);
      const double task_object_orientation = orientationDistance(before_evidence, after_evidence);
      const double task_object_tilt = axialTiltDistance(before_evidence, after_evidence);
      result.metrics[carrying(spec_.state) ? "task_object_follow_position_error"
                                           : "task_object_position_drift"] = task_object_position;
      result.metrics[carrying(spec_.state) ? "task_object_follow_orientation_error_rad"
                                           : "task_object_orientation_drift_rad"] =
        task_object_orientation;
      if (carrying(spec_.state)) {
        result.metrics["task_object_follow_tilt_error_rad"] = task_object_tilt;
      }
      if (task_object_position > profile_.task_object_position_drift_tolerance ||
          (carrying(spec_.state) ? task_object_tilt : task_object_orientation) >
            profile_.task_object_orientation_drift_tolerance_rad) {
        addFailure(result, FailureCategory::POSTCONDITION,
                   carrying(spec_.state) ? "TASK_OBJECT_DID_NOT_FOLLOW_GRIPPER"
                                         : "DETACHED_TASK_OBJECT_DRIFT",
                   carrying(spec_.state)
                     ? "Gazebo TaskObject did not preserve its relative pose while carried"
                     : "Detached Gazebo TaskObject moved while the arm moved");
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

class StablePhysicalGraspAction final : public IStateExecutor
{
public:
  StablePhysicalGraspAction(State state, bool before_lift, std::shared_ptr<IWorldObserver> observer,
                            std::shared_ptr<IPhysicalGraspEvidenceStore> evidence,
                            std::shared_ptr<ISO101GripperCommand> gripper, SO101Profile profile) :
      state_(state), before_lift_(before_lift), observer_(std::move(observer)),
      evidence_(std::move(evidence)), gripper_(std::move(gripper)), profile_(std::move(profile))
  {
  }

  ActionResult execute(const ExecutionContext & context) override
  {
    if (!observer_ || !evidence_) {
      return {ActionStatus::FAILED,
              Failure{FailureCategory::CONFIGURATION,
                      "PHYSICAL_GRASP_EVIDENCE_DEPENDENCY_MISSING",
                      "Physical-grasp stability checks require the production world observer",
                      {}}};
    }
    std::optional<WorldSnapshot> last;
    const int required_consecutive = before_lift_ ? 6 : 3;
    const int max_samples = before_lift_ ? 30 : 3;
    int consecutive = 0;
    int consecutive_unilateral = 0;
    bool regrasp_attempted = false;
    bool regrasp_relaxed = false;
    for (int sample = 0; sample < max_samples; ++sample) {
      const auto observed = observer_->observe();
      if (!observed.snapshot) {
        return {ActionStatus::FAILED, observed.failure.value_or(Failure{
                                        FailureCategory::OBSERVATION,
                                        "PHYSICAL_GRASP_STABILITY_OBSERVATION_FAILED",
                                        "Unable to collect physical-grasp stability evidence",
                                        {}})};
      }
      const auto & snapshot = *observed.snapshot;
      if (!snapshot.fresh || !snapshot.gazebo_task_object_stationary ||
          !snapshot.gazebo_task_object_pose_world) {
        return {ActionStatus::FAILED,
                Failure{FailureCategory::POSTCONDITION,
                        "PHYSICAL_GRASP_NOT_STABLE",
                        "Cup/contact/arm evidence was not stable for three samples",
                        {}}};
      }
      if (!snapshot.arm_stationary || !*snapshot.gazebo_task_object_stationary) {
        consecutive = 0;
        consecutive_unilateral = 0;
        if (sample + 1 < max_samples)
          std::this_thread::sleep_for(std::chrono::milliseconds(50));
        continue;
      }
      const bool bilateral =
        snapshot.gazebo_task_object_gripper_contact.value_or(false) &&
        snapshot.gazebo_task_object_fixed_finger_contact.value_or(false) &&
        snapshot.gazebo_task_object_moving_jaw_contact.value_or(false) &&
        snapshot.gazebo_task_object_gripper_max_depth &&
        *snapshot.gazebo_task_object_gripper_max_depth <= profile_.max_gripper_contact_depth;
      if (!before_lift_ || bilateral) {
        ++consecutive;
        consecutive_unilateral = 0;
        last = snapshot;
        if (consecutive >= required_consecutive) {
          if (before_lift_ && regrasp_attempted && !regrasp_relaxed) {
            // The retry deliberately moves the cup into bilateral contact, but
            // its deep squeeze is only a transient seating action.  Return to
            // the calibrated wall target before attachment, then require a
            // second full stable window so an over-compressed grasp can never
            // be frozen into the Gazebo detachable joint.
            const auto relaxed = gripper_->command(profile_.q6_contact);
            const bool contact_abort = relaxed.status == ActionStatus::FAILED && relaxed.failure &&
                                       relaxed.failure->code == "GRIPPER_ACTION_ABORTED";
            if (relaxed.status != ActionStatus::SUCCEEDED && !contact_abort)
              return relaxed;
            regrasp_relaxed = true;
            consecutive = 0;
            last.reset();
          } else {
            break;
          }
        }
      } else {
        consecutive = 0;
        ++consecutive_unilateral;
        // Spend the single bounded regrasp as soon as unilateral contact is
        // observed.  Delaying this squeeze lets the lightly seated cup tilt
        // before attachment and produces an unstable carrying transform.
        if (!regrasp_attempted && consecutive_unilateral >= 1) {
          if (!gripper_) {
            return {ActionStatus::FAILED,
                    Failure{FailureCategory::CONFIGURATION,
                            "PHYSICAL_REGRASP_COMMAND_MISSING",
                            "Bilateral contact retry requires the production gripper command",
                            {}}};
          }
          const double retry_target = std::max(
            profile_.q6_safe_lower, profile_.q6_contact - profile_.q6_regrasp_squeeze_offset);
          const auto retry = gripper_->command(retry_target);
          const bool contact_abort = retry.status == ActionStatus::FAILED && retry.failure &&
                                     retry.failure->code == "GRIPPER_ACTION_ABORTED";
          if (retry.status != ActionStatus::SUCCEEDED && !contact_abort)
            return retry;
          regrasp_attempted = true;
        }
      }
      if (sample + 1 < max_samples)
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    if (!last || consecutive < required_consecutive || (regrasp_attempted && !regrasp_relaxed)) {
      return {ActionStatus::FAILED, Failure{FailureCategory::POSTCONDITION,
                                            "PHYSICAL_GRASP_BILATERAL_STABILITY_TIMEOUT",
                                            "Bilateral fixed-finger and moving-jaw contact did not "
                                            "remain stable after one bounded regrasp",
                                            {}}};
    }
    const auto failure = before_lift_ ? evidence_->saveBefore(*last) : evidence_->saveAfter(*last);
    if (failure)
      return {ActionStatus::FAILED, *failure};
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  ActionResult cancel() override
  {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

private:
  State state_;
  bool before_lift_;
  std::shared_ptr<IWorldObserver> observer_;
  std::shared_ptr<IPhysicalGraspEvidenceStore> evidence_;
  std::shared_ptr<ISO101GripperCommand> gripper_;
  SO101Profile profile_;
};

class DetachAndWaitForStationary final : public IStateExecutor
{
public:
  DetachAndWaitForStationary(std::shared_ptr<IStateExecutor> detach,
                             std::shared_ptr<IWorldObserver> observer) :
      detach_(std::move(detach)), observer_(std::move(observer))
  {
  }

  ActionResult execute(const ExecutionContext & context) override
  {
    auto detached = detach_->execute(context);
    if (detached.status != ActionStatus::SUCCEEDED)
      return detached;
    constexpr int kRequiredConsecutive = 3;
    constexpr int kMaxSamples = 40;
    int consecutive = 0;
    for (int sample = 0; sample < kMaxSamples; ++sample) {
      const auto observed = observer_->observe();
      if (!observed.snapshot) {
        return {ActionStatus::FAILED, observed.failure.value_or(Failure{
                                        FailureCategory::OBSERVATION,
                                        "POST_DETACH_OBSERVATION_UNAVAILABLE",
                                        "Gazebo detach settling requires a fresh world observation",
                                        {}})};
      }
      const auto & snapshot = *observed.snapshot;
      const bool stationary_detached =
        snapshot.fresh && snapshot.arm_stationary && snapshot.gazebo_task_object_attached &&
        !*snapshot.gazebo_task_object_attached && snapshot.gazebo_task_object_pose_world &&
        snapshot.gazebo_task_object_stationary && *snapshot.gazebo_task_object_stationary;
      consecutive = stationary_detached ? consecutive + 1 : 0;
      if (consecutive >= kRequiredConsecutive) {
        return {ActionStatus::SUCCEEDED, std::nullopt};
      }
      if (sample + 1 < kMaxSamples) {
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
      }
    }
    return {ActionStatus::TIMED_OUT,
            Failure{FailureCategory::POSTCONDITION,
                    "GAZEBO_TASK_OBJECT_SETTLE_TIMEOUT",
                    "Detached TaskObject did not become stationary for three consecutive samples",
                    {}}};
  }

  ActionResult cancel() override
  {
    return detach_->cancel();
  }

private:
  std::shared_ptr<IStateExecutor> detach_;
  std::shared_ptr<IWorldObserver> observer_;
};

class WorldZMicroLiftAction final : public IStateExecutor
{
public:
  explicit WorldZMicroLiftAction(std::shared_ptr<IWorldZMicroLift> micro_lift) :
      micro_lift_(std::move(micro_lift))
  {
  }

  ActionResult execute(const ExecutionContext & context) override
  {
    if (!micro_lift_) {
      return {ActionStatus::FAILED, Failure{FailureCategory::CONFIGURATION,
                                            "MICRO_LIFT_DEPENDENCY_MISSING",
                                            "World-Z micro-lift requires the MoveIt boundary",
                                            {}}};
    }
    // A 1 mm probe was smaller than the simulator's table/contact settling
    // band: the TCP moved while a valid bilateral grip could remain seated.
    // Two millimetres clears that band while staying far below the 50 mm
    // carrying lift, so this remains a diagnostic probe rather than transport.
    return micro_lift_->executeWorldZMicroLift(context.before.tcp_pose_world, 0.002);
  }
  ActionResult cancel() override
  {
    return micro_lift_ ? micro_lift_->cancelWorldZMicroLift()
                       : ActionResult{ActionStatus::FAILED,
                                      Failure{FailureCategory::CONFIGURATION,
                                              "MICRO_LIFT_DEPENDENCY_MISSING",
                                              "World-Z micro-lift requires the MoveIt boundary",
                                              {}}};
  }

private:
  std::shared_ptr<IWorldZMicroLift> micro_lift_;
};

class VerifyPhysicalGraspAction final : public IStateExecutor
{
public:
  VerifyPhysicalGraspAction(std::shared_ptr<IPhysicalGraspEvidenceStore> evidence,
                            PhysicalGraspValidator validator, PhysicalGraspGeometry geometry) :
      evidence_(std::move(evidence)), validator_(validator), geometry_(geometry)
  {
  }

  ActionResult execute(const ExecutionContext &) override
  {
    if (!evidence_) {
      return {ActionStatus::FAILED, Failure{FailureCategory::CONFIGURATION,
                                            "PHYSICAL_GRASP_EVIDENCE_DEPENDENCY_MISSING",
                                            "Physical-grasp evidence store is missing",
                                            {}}};
    }
    auto loaded = evidence_->load();
    if (std::holds_alternative<Failure>(loaded))
      return {ActionStatus::FAILED, std::get<Failure>(std::move(loaded))};
    const auto record = std::get<PhysicalGraspEvidenceRecord>(std::move(loaded));
    if (!record.before_lift || !record.after_lift) {
      return {ActionStatus::FAILED, Failure{FailureCategory::POSTCONDITION,
                                            "PHYSICAL_GRASP_EVIDENCE_INCOMPLETE",
                                            "Both stable windows are required before attachment",
                                            {}}};
    }
    WorldSnapshot before;
    before.tcp_pose_world = record.before_lift->tcp_pose_world;
    before.gazebo_task_object_pose_world = record.before_lift->task_object_pose_world;
    before.gazebo_task_object_gripper_contact = record.before_lift->gripper_contact;
    WorldSnapshot after;
    after.tcp_pose_world = record.after_lift->tcp_pose_world;
    after.gazebo_task_object_pose_world = record.after_lift->task_object_pose_world;
    after.gazebo_task_object_gripper_contact = record.after_lift->gripper_contact;
    auto result = validator_.evaluate(before, after, geometry_);
    if (!result.passed)
      return {ActionStatus::FAILED, result.failure};
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
  ActionResult cancel() override
  {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

private:
  std::shared_ptr<IPhysicalGraspEvidenceStore> evidence_;
  PhysicalGraspValidator validator_;
  PhysicalGraspGeometry geometry_;
};

class PhysicalGraspContract final : public TransitionContractRegistry::ITransitionContract
{
public:
  [[nodiscard]] ValidationResult validatePrecondition(const WorldSnapshot & snapshot) const override
  {
    ValidationResult result{true, {}, {}};
    if (!snapshot.fresh || !snapshot.arm_stationary || !snapshot.gazebo_task_object_pose_world) {
      addFailure(result, FailureCategory::OBSERVATION, "PHYSICAL_GRASP_PRECONDITION_INVALID",
                 "Physical-grasp gate requires fresh stationary TCP and Gazebo cup evidence");
    }
    result.ok = result.failures.empty();
    return result;
  }
  [[nodiscard]] ValidationResult validate(const WorldSnapshot &, const WorldSnapshot & after,
                                          const ActionResult & action) const override
  {
    ValidationResult result{true, {}, {}};
    if (action.status != ActionStatus::SUCCEEDED) {
      addFailure(result, FailureCategory::POSTCONDITION, "PHYSICAL_GRASP_ACTION_FAILED",
                 "Physical-grasp gate action did not succeed");
    }
    if (!after.fresh || !after.gazebo_task_object_pose_world) {
      addFailure(result, FailureCategory::OBSERVATION, "PHYSICAL_GRASP_POSTCONDITION_INVALID",
                 "Physical-grasp gate requires fresh post-action cup evidence");
    }
    result.ok = result.failures.empty();
    return result;
  }
};

void registerPhysicalGrasp(SO101PickPlaceRuntimeRegistries & runtime,
                           const SO101PickPlaceRuntimeDependencies & dependencies,
                           const SO101PickPlaceRuntimeConfig & config)
{
  if (!dependencies.physical_observer || !dependencies.micro_lift ||
      !dependencies.physical_grasp_evidence)
    return;
  const PhysicalGraspGeometry geometry{config.profile.table_pose.z +
                                         config.profile.table_size[2] * 0.5,
                                       -config.profile.task_object_height * 0.5};
  runtime.actions.registerExecutor(State::WAIT_GRASP_STABLE,
                                   std::make_shared<StablePhysicalGraspAction>(
                                     State::WAIT_GRASP_STABLE, true, dependencies.physical_observer,
                                     dependencies.physical_grasp_evidence, dependencies.gripper,
                                     config.profile));
  runtime.actions.registerExecutor(
    State::MICRO_LIFT, std::make_shared<WorldZMicroLiftAction>(dependencies.micro_lift));
  runtime.actions.registerExecutor(
    State::WAIT_MICRO_LIFT_STABLE,
    std::make_shared<StablePhysicalGraspAction>(
      State::WAIT_MICRO_LIFT_STABLE, false, dependencies.physical_observer,
      dependencies.physical_grasp_evidence, dependencies.gripper, config.profile));
  runtime.actions.registerExecutor(
    State::VERIFY_PHYSICAL_GRASP,
    std::make_shared<VerifyPhysicalGraspAction>(dependencies.physical_grasp_evidence,
                                                PhysicalGraspValidator{}, geometry));
  for (const auto state : kPhysicalGraspStates) {
    runtime.contracts.registerContract(
      {state, TransitionTable::resolve(state, ActionStatus::SUCCEEDED)},
      std::make_shared<PhysicalGraspContract>());
  }
  runtime.contracts.registerContract({State::VALIDATION_FAILED, State::ATTACH_GAZEBO},
                                     std::make_shared<PhysicalGraspContract>());
}

std::optional<Failure>
missingDependencyFailure(const SO101PickPlaceRuntimeDependencies & dependencies)
{
  std::vector<std::string> missing;
  if (!dependencies.gripper)
    missing.emplace_back("gripper");
  if (!dependencies.moveit_scene)
    missing.emplace_back("moveit_scene");
  if (!dependencies.gazebo_attach)
    missing.emplace_back("gazebo_attach");
  if (!dependencies.gazebo_detach)
    missing.emplace_back("gazebo_detach");
  if (!dependencies.recovery_gazebo_detach)
    missing.emplace_back("recovery_gazebo_detach");
  if (!dependencies.motion_policy)
    missing.emplace_back("motion_policy");
  if (!dependencies.motion)
    missing.emplace_back("motion");
  if (!dependencies.micro_lift)
    missing.emplace_back("micro_lift");
  if (!dependencies.physical_observer)
    missing.emplace_back("physical_observer");
  if (!dependencies.physical_grasp_evidence)
    missing.emplace_back("physical_grasp_evidence");
  if (missing.empty())
    return std::nullopt;
  std::ostringstream message;
  message << "Production SO-101 runtime dependencies are missing:";
  for (const auto & name : missing)
    message << ' ' << name;
  return Failure{FailureCategory::CONFIGURATION, "RUNTIME_DEPENDENCY_MISSING", message.str(), {}};
}

}  // namespace

SO101MoveItWorldObserver::SO101MoveItWorldObserver(std::shared_ptr<IJointPlanningBoundary> boundary,
                                                   SO101Profile profile,
                                                   SO101WorldObservationConfig config) :
    boundary_(std::move(boundary)), profile_(std::move(profile)), config_(config)
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
      config_.joint_settle_tolerance < 0.0 ||
      !finite(config_.joint_stationary_position_tolerance) ||
      config_.joint_stationary_position_tolerance < 0.0) {
    return {std::nullopt,
            observationFailure("WORLD_OBSERVER_CONFIG_INVALID",
                               "World observer timing and settle limits are invalid")};
  }
  std::optional<CurrentJointStateEvidence> previous;
  std::optional<CurrentJointStateEvidence> current;
  bool stationary = true;
  const bool use_position_window = config_.settle_samples > 1;
  const auto validate_current =
    [this](const std::optional<CurrentJointStateEvidence> & evidence) -> std::optional<Failure> {
    if (!evidence || evidence->joint_names != profile_.arm_joints ||
        evidence->positions.size() != profile_.arm_joints.size() ||
        evidence->velocities.size() != profile_.arm_joints.size() || !evidence->gripper_position ||
        !evidence->gripper_velocity) {
      return observationFailure("JOINT_EVIDENCE_INCOMPLETE",
                                "Joint 1 through 6 evidence is incomplete");
    }
    const auto now = std::chrono::steady_clock::now();
    if (evidence->received_at == std::chrono::steady_clock::time_point{} ||
        evidence->received_at > now ||
        now - evidence->received_at > std::chrono::duration<double>(config_.max_age_seconds)) {
      return observationFailure("JOINT_EVIDENCE_STALE", "Joint 1 through 6 evidence is stale");
    }
    for (std::size_t i = 0; i < evidence->positions.size(); ++i) {
      if (!finite(evidence->positions[i]) || !finite(evidence->velocities[i])) {
        return observationFailure("JOINT_EVIDENCE_NONFINITE",
                                  "Joint position or velocity is non-finite");
      }
    }
    if (!finite(*evidence->gripper_position) || !finite(*evidence->gripper_velocity)) {
      return observationFailure("JOINT_EVIDENCE_NONFINITE", "Joint 6 evidence is non-finite");
    }
    return std::nullopt;
  };
  for (std::size_t sample = 0; sample < config_.settle_samples; ++sample) {
    current = boundary_->currentState();
    if (auto failure = validate_current(current))
      return {std::nullopt, std::move(failure)};
    for (std::size_t i = 0; i < current->positions.size(); ++i) {
      if (previous)
        stationary = stationary && std::abs(previous->positions[i] - current->positions[i]) <=
                                     config_.joint_stationary_position_tolerance;
      else if (!use_position_window)
        stationary =
          stationary && std::abs(current->velocities[i]) <= profile_.q6_velocity_tolerance;
    }
    if (previous && std::abs(*previous->gripper_position - *current->gripper_position) >
                      config_.joint_settle_tolerance) {
      stationary = false;
    }
    previous = current;
    if (sample + 1 < config_.settle_samples && config_.settle_interval_seconds > 0.0) {
      std::this_thread::sleep_for(std::chrono::duration<double>(config_.settle_interval_seconds));
    }
  }

  const auto scene = boundary_->sceneFacts();
  if (!scene || !scene->table_in_world || !scene->table_world_pose ||
      !isFinitePose(*scene->table_world_pose) || !scene->pedestal_in_world ||
      !scene->pedestal_world_pose || !isFinitePose(*scene->pedestal_world_pose) ||
      !scene->current_tcp_pose_world || !isFinitePose(*scene->current_tcp_pose_world) ||
      !poseWithin(*scene->table_world_pose, profile_.table_pose, 1e-5, 1e-4) ||
      !poseWithin(*scene->pedestal_world_pose, profile_.pedestal_pose, 1e-5, 1e-4)) {
    return {std::nullopt,
            observationFailure("MOVEIT_SCENE_EVIDENCE_INCOMPLETE",
                               "Canonical table, pedestal, and finite TCP evidence are required")};
  }
  if (scene->task_object_in_world == scene->task_object_attached) {
    return {std::nullopt,
            observationFailure("MOVEIT_TASK_OBJECT_MEMBERSHIP_INCONSISTENT",
                               "TaskObject must be exactly world or attached in MoveIt")};
  }
  if ((scene->task_object_in_world &&
       (!scene->task_object_world_pose || !isFinitePose(*scene->task_object_world_pose))) ||
      (scene->task_object_attached &&
       (!scene->attached_link || scene->touch_links.empty() || !scene->attached_relative_pose ||
        !isFinitePose(*scene->attached_relative_pose) || !scene->current_gripper_pose_world ||
        !isFinitePose(*scene->current_gripper_pose_world)))) {
    return {std::nullopt,
            observationFailure("MOVEIT_TASK_OBJECT_POSE_EVIDENCE_INCOMPLETE",
                               "MoveIt TaskObject 6D pose and attachment metadata are incomplete")};
  }
  if (!scene->task_object_attached &&
      (scene->attached_link || !scene->touch_links.empty() || scene->attached_relative_pose)) {
    return {std::nullopt, observationFailure("MOVEIT_TASK_OBJECT_MEMBERSHIP_INCONSISTENT",
                                             "Detached TaskObject retains attachment metadata")};
  }

  previous = current;
  current = boundary_->currentState();
  if (auto failure = validate_current(current))
    return {std::nullopt, std::move(failure)};
  for (std::size_t i = 0; i < current->positions.size(); ++i) {
    const double position_delta = std::abs(previous->positions[i] - current->positions[i]);
    if (position_delta > config_.joint_settle_tolerance) {
      return {std::nullopt,
              observationFailure("ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION",
                                 "Arm joints changed while MoveIt scene evidence was collected")};
    }
    if (use_position_window)
      stationary = stationary && position_delta <= config_.joint_stationary_position_tolerance;
    else
      stationary = stationary && std::abs(current->velocities[i]) <= profile_.q6_velocity_tolerance;
  }
  if (std::abs(*previous->gripper_position - *current->gripper_position) >
      config_.joint_settle_tolerance) {
    return {std::nullopt,
            observationFailure("ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION",
                               "Gripper joint changed while MoveIt scene evidence was collected")};
  }
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
  if (scene->task_object_world_pose) {
    snapshot.moveit_world_object_poses[profile_.task_object_id] = *scene->task_object_world_pose;
  }
  snapshot.moveit_task_object_attached = scene->task_object_attached;
  snapshot.moveit_task_object_attached_link = scene->attached_link;
  snapshot.moveit_task_object_touch_links = scene->touch_links;
  snapshot.moveit_task_object_attached_relative_pose = scene->attached_relative_pose;
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

bool withinSO101AttachmentModelTolerance(const Pose3d & observed_relative_pose,
                                         const Pose3d & planned_relative_pose,
                                         const SO101Profile & profile)
{
  return cylindricalPoseWithin(observed_relative_pose, planned_relative_pose,
                               profile.task_object_position_drift_tolerance,
                               profile.task_object_attachment_orientation_tolerance_rad);
}

SO101PickPlaceRuntimeRegistries
makeSO101PickPlaceRuntimeRegistries(const SO101PickPlaceRuntimeDependencies & dependencies,
                                    const SO101PickPlaceRuntimeConfig & config)
{
  SO101Task3RuntimeDependencies task3_dependencies{
    dependencies.gripper,       dependencies.moveit_scene,           dependencies.gazebo_attach,
    dependencies.gazebo_detach, dependencies.recovery_gazebo_detach, dependencies.gripper_observer};
  task3_dependencies.gripper_observer = dependencies.physical_observer;
  if (task3_dependencies.gazebo_detach && dependencies.physical_observer) {
    task3_dependencies.gazebo_detach = std::make_shared<DetachAndWaitForStationary>(
      task3_dependencies.gazebo_detach, dependencies.physical_observer);
  }
  auto task3 = makeSO101Task3Runtime(task3_dependencies, config);
  SO101PickPlaceRuntimeRegistries runtime{
    std::move(task3.actions),         {},    std::move(task3.contracts),
    std::move(task3.recovery_policy), false, std::nullopt};
  runtime.configuration_failure = missingDependencyFailure(dependencies);
  if (!dependencies.motion_policy || !dependencies.motion)
    return runtime;

  registerPhysicalGrasp(runtime, dependencies, config);

  for (const auto state : kMotionStates) {
    const auto spec = dependencies.motion_policy->spec(state);
    if (!spec) {
      runtime.configuration_failure =
        Failure{FailureCategory::CONFIGURATION,
                "MOTION_SPEC_MISSING",
                std::string("Canonical motion specification missing for ") + toString(state),
                {}};
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
  if (runtime.configuration_failure)
    return runtime;
  for (const auto & [state, transitions] : TransitionTable::entries()) {
    if (state == State::IDLE || isTerminal(state) || !isAction(state))
      continue;
    if (!runtime.actions.findExecutor(state) ||
        !runtime.contracts.hasContract({state, transitions.succeeded})) {
      runtime.configuration_failure =
        Failure{FailureCategory::CONFIGURATION,
                "RUNTIME_REGISTRY_INCOMPLETE",
                std::string("Runtime registry is incomplete at ") + toString(state),
                {}};
      return runtime;
    }
    const bool needs_plan =
      std::find(kMotionStates.begin(), kMotionStates.end(), state) != kMotionStates.end();
    if ((runtime.actions.findPlanner(state) != nullptr) != needs_plan ||
        runtime.plan_validators.hasValidator(state) != needs_plan) {
      runtime.configuration_failure =
        Failure{FailureCategory::CONFIGURATION,
                "RUNTIME_REGISTRY_INCOMPLETE",
                std::string("Runtime planning registry is incomplete at ") + toString(state),
                {}};
      return runtime;
    }
  }
  runtime.execution_safe = true;
  return runtime;
}

}  // namespace so101_gazebo_demo::pick_place
