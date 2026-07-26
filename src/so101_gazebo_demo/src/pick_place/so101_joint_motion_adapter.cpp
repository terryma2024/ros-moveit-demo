#include "so101_gazebo_demo/pick_place/so101_joint_motion_adapter.hpp"

#include <algorithm>
#include <cmath>
#include <utility>

namespace so101_gazebo_demo::pick_place
{
namespace
{

PlanResult fail(FailureCategory category, std::string code, std::string message)
{
  return {{ActionStatus::FAILED,
           Failure{category, std::move(code), std::move(message), {}}}, nullptr};
}

bool samePositions(const std::vector<double> & a, const std::vector<double> & b)
{
  if (a.size() != b.size()) return false;
  for (std::size_t i = 0; i < a.size(); ++i) {
    if (!std::isfinite(a[i]) || !std::isfinite(b[i]) || std::abs(a[i] - b[i]) > 1e-9) {
      return false;
    }
  }
  return true;
}

bool positionsWithin(const std::vector<double> & a, const std::vector<double> & b,
                     double tolerance)
{
  if (a.size() != b.size()) return false;
  for (std::size_t i = 0; i < a.size(); ++i) {
    if (!std::isfinite(a[i]) || !std::isfinite(b[i]) ||
        std::abs(a[i] - b[i]) > tolerance) return false;
  }
  return true;
}

bool validScene(const MotionPlanningSceneFacts & facts, bool carrying,
                const SO101Profile & profile)
{
  if (!facts.table_in_world) return false;
  if (carrying) {
    return !facts.coke_in_world && facts.coke_attached && facts.attached_link &&
           *facts.attached_link == profile.moveit_attach_link &&
           facts.touch_links == std::set<std::string>(profile.moveit_touch_links.begin(),
                                                       profile.moveit_touch_links.end());
  }
  return facts.coke_in_world && !facts.coke_attached && !facts.attached_link &&
         facts.touch_links.empty();
}

}  // namespace

ProfiledJointMotionAdapter::ProfiledJointMotionAdapter(
  std::shared_ptr<IJointPlanningBoundary> boundary,
  std::shared_ptr<const IRobotStateEvidenceProvider> evaluator, SO101Profile profile)
: boundary_(std::move(boundary)), evaluator_(std::move(evaluator)), profile_(std::move(profile))
{
}

PlanResult ProfiledJointMotionAdapter::plan(const JointMotionRequest & request,
                                            const ObservationResult & observation)
{
  if (!boundary_ || !evaluator_) {
    return fail(FailureCategory::CONFIGURATION, "MOTION_ADAPTER_DEPENDENCY_MISSING",
                "Joint motion adapter requires planning and state-evidence boundaries");
  }
  if (!observation.snapshot || !observation.snapshot->fresh) {
    return fail(FailureCategory::OBSERVATION, "MOTION_OBSERVATION_MISSING",
                "Motion planning requires a fresh world observation");
  }
  if (!observation.snapshot->arm_stationary) {
    return fail(FailureCategory::PRECONDITION, "ARM_NOT_STATIONARY_BEFORE_PLAN",
                "Arm must be stationary before planning");
  }
  const auto q6_position =
    observation.snapshot->joint_positions.find(profile_.gripper_joint);
  const auto q6_velocity =
    observation.snapshot->joint_velocities.find(profile_.gripper_joint);
  if (q6_position == observation.snapshot->joint_positions.end() ||
      q6_velocity == observation.snapshot->joint_velocities.end() ||
      !std::isfinite(q6_position->second) || !std::isfinite(q6_velocity->second)) {
    return fail(FailureCategory::OBSERVATION, "CURRENT_GRIPPER_STATE_UNAVAILABLE",
                "Motion planning requires fresh finite q6 position and velocity evidence");
  }
  if (std::abs(q6_velocity->second) > profile_.q6_velocity_tolerance) {
    return fail(FailureCategory::PRECONDITION, "GRIPPER_NOT_STATIONARY_BEFORE_PLAN",
                "Gripper joint 6 must be stationary before planning");
  }
  if (!std::isfinite(request.gripper_position) ||
      std::abs(q6_position->second - request.gripper_position) > profile_.q6_tolerance) {
    return fail(FailureCategory::PRECONDITION, "GRIPPER_CONTEXT_MISMATCH_BEFORE_PLAN",
                "Observed q6 does not match the motion state's expected gripper context");
  }
  if (request.joint_names != profile_.arm_joints || request.joint_waypoints.empty() ||
      (!request.ladder && request.joint_waypoints.size() != 1)) {
    return fail(FailureCategory::CONFIGURATION, "JOINT_MOTION_REQUEST_INVALID",
                "Request must use profile arm joints and a goal or waypoint ladder");
  }
  for (const auto & waypoint : request.joint_waypoints) {
    if (waypoint.size() != profile_.arm_joints.size()) {
      return fail(FailureCategory::CONFIGURATION, "JOINT_MOTION_REQUEST_INVALID",
                  "Every target waypoint must cover all SO-101 arm joints");
    }
  }
  const auto scene = boundary_->sceneFacts();
  if (!scene) {
    return fail(FailureCategory::MOVEIT_SCENE, "PLANNING_SCENE_OBSERVATION_UNAVAILABLE",
                "Current MoveIt Planning Scene facts are unavailable");
  }
  if (!validScene(*scene, request.carrying, profile_)) {
    return fail(FailureCategory::MOVEIT_SCENE,
                request.carrying ? "CARRYING_PLANNING_SCENE_INVALID"
                                 : "DETACHED_PLANNING_SCENE_INVALID",
                "MoveIt Coke membership or attachment metadata does not match the motion mode");
  }
  const auto current = boundary_->currentState();
  if (!current || current->joint_names != profile_.arm_joints ||
      current->positions.size() != profile_.arm_joints.size()) {
    return fail(FailureCategory::OBSERVATION, "CURRENT_ARM_STATE_UNAVAILABLE",
                "Current SO-101 arm joint state is unavailable or incomplete");
  }

  TrajectoryEvidenceInput combined;
  combined.joint_names = profile_.arm_joints;
  combined.current_joint_snapshot = current->positions;
  combined.start_state_stamp_nanoseconds = current->observed_stamp_nanoseconds;
  combined.moveit_success = true;
  combined.collision_aware_planner = true;
  combined.allowed_touch_pairs = request.allowed_touch_pairs;
  combined.gripper_position = q6_position->second;
  combined.temporal_contact_policy = request.temporal_contact_policy;
  std::vector<double> segment_start = current->positions;
  double time_offset = 0.0;

  for (const auto & waypoint : request.joint_waypoints) {
    auto result = boundary_->planSegment(profile_.arm_joints, segment_start, waypoint,
                                         request.allowed_touch_pairs,
                                         request.temporal_contact_policy,
                                         q6_position->second);
    if (result.action.status != ActionStatus::SUCCEEDED || !result.segment) {
      return {result.action, nullptr};
    }
    const auto & segment = *result.segment;
    if (!segment.moveit_success || segment.joint_names != profile_.arm_joints ||
        segment.points.size() < 2 || !segment.collision_aware) {
      return fail(FailureCategory::PLANNING, "MOVEIT_SEGMENT_PLAN_INVALID",
                  "MoveIt segment lacks success, joint-order, points, or collision-aware evidence");
    }
    if (!samePositions(segment.points.front().joint_positions, segment_start)) {
      return fail(FailureCategory::PLAN_VALIDATION, "SEGMENT_START_JOINT_MISMATCH",
                  "MoveIt segment first point does not match the requested segment start");
    }
    if (combined.planner_id.empty()) combined.planner_id = segment.planner_id;
    if (segment.planner_id != combined.planner_id) {
      return fail(FailureCategory::PLANNING, "MIXED_SEGMENT_PLANNERS",
                  "All ladder segments must use the same configured planner");
    }
    combined.moveit_error_code = segment.moveit_error_code;
    const double segment_time_origin = segment.points.front().time_from_start_seconds;
    const std::size_t first = combined.points.empty() ? 0 : 1;
    if (!combined.points.empty() &&
        !positionsWithin(combined.points.back().joint_positions, segment_start,
                         profile_.q6_tolerance)) {
      return fail(FailureCategory::PLAN_VALIDATION, "SEGMENT_BOUNDARY_DISCONTINUITY",
                  "Prior segment endpoint is outside continuity tolerance of the next start");
    }
    for (std::size_t i = first; i < segment.points.size(); ++i) {
      auto point = segment.points[i];
      point.time_from_start_seconds =
        time_offset + point.time_from_start_seconds - segment_time_origin;
      if (!combined.points.empty() &&
          point.time_from_start_seconds <= combined.points.back().time_from_start_seconds) {
        return fail(FailureCategory::PLAN_VALIDATION, "SEGMENT_TIME_NOT_INCREASING",
                    "Stitched ladder time must strictly increase after boundary de-duplication");
      }
      combined.points.push_back(std::move(point));
    }
    if (combined.points.empty()) {
      return fail(FailureCategory::PLAN_VALIDATION, "EMPTY_STITCHED_TRAJECTORY",
                  "No points remain after stitching MoveIt segments");
    }
    time_offset = combined.points.back().time_from_start_seconds;
    segment_start = waypoint;
  }

  auto built = buildMotionPlanEvidence(combined, *evaluator_);
  if (!built.artifact) {
    return {{ActionStatus::FAILED, built.failure}, nullptr};
  }
  return {{ActionStatus::SUCCEEDED, std::nullopt}, std::move(built.artifact)};
}

ActionResult ProfiledJointMotionAdapter::execute(const MotionPlanArtifact & artifact)
{
  return boundary_ ? boundary_->execute(artifact)
                   : ActionResult{ActionStatus::FAILED,
                                  Failure{FailureCategory::CONFIGURATION,
                                          "MOTION_ADAPTER_DEPENDENCY_MISSING",
                                          "Joint planning boundary is missing", {}}};
}

ActionResult ProfiledJointMotionAdapter::cancel()
{
  return boundary_ ? boundary_->cancel()
                   : ActionResult{ActionStatus::FAILED,
                                  Failure{FailureCategory::CONFIGURATION,
                                          "MOTION_ADAPTER_DEPENDENCY_MISSING",
                                          "Joint planning boundary is missing", {}}};
}

}  // namespace so101_gazebo_demo::pick_place
