#include "so101_gazebo_demo/pick_place/so101_motion_evidence_builder.hpp"

#include <algorithm>
#include <cmath>
#include <utility>

namespace so101_gazebo_demo::pick_place
{
namespace
{

MotionEvidenceBuildResult fail(std::string code, std::string message)
{
  return {nullptr,
          Failure{FailureCategory::PLAN_VALIDATION, std::move(code), std::move(message), {}}};
}

bool finite(const std::vector<double> & values)
{
  return std::all_of(values.begin(), values.end(),
                     [](double value) { return std::isfinite(value); });
}

}  // namespace

MotionEvidenceBuildResult buildMotionPlanEvidence(const TrajectoryEvidenceInput & input,
                                                  const IRobotStateEvidenceProvider & evaluator)
{
  if (!input.moveit_success) {
    return fail("MOVEIT_PLAN_DID_NOT_SUCCEED", "MoveIt did not report a successful plan");
  }
  if (input.joint_names.empty() ||
      input.current_joint_snapshot.size() != input.joint_names.size() ||
      !finite(input.current_joint_snapshot) || input.points.empty()) {
    return fail("TRAJECTORY_EVIDENCE_INCOMPLETE",
                "Trajectory metadata or current state is incomplete");
  }

  auto artifact = std::make_shared<MotionPlanArtifact>();
  artifact->trajectory_points = input.points.size();
  artifact->joint_names = input.joint_names;
  artifact->start_joint_positions = input.current_joint_snapshot;
  artifact->current_joint_snapshot = input.current_joint_snapshot;
  artifact->moveit_success = input.moveit_success;
  artifact->moveit_error_code = input.moveit_error_code;
  artifact->planner_id = input.planner_id;
  artifact->start_state_stamp_nanoseconds = input.start_state_stamp_nanoseconds;
  artifact->collision_aware = input.collision_aware_planner;
  artifact->time_parameterized = true;
  artifact->allowed_touch_pairs = input.allowed_touch_pairs;
  artifact->temporal_contact_policy = input.temporal_contact_policy;

  double previous_time = -1.0;
  for (const auto & point : input.points) {
    if (point.joint_positions.size() != input.joint_names.size() ||
        !finite(point.joint_positions) || !std::isfinite(point.time_from_start_seconds)) {
      return fail("TRAJECTORY_POINT_SHAPE_MISMATCH",
                  "Trajectory point positions must match the arm joint order and be finite");
    }
    if (point.time_from_start_seconds < 0.0 ||
        (previous_time >= 0.0 && point.time_from_start_seconds <= previous_time)) {
      artifact->time_parameterized = false;
    }
    auto state =
      evaluator.evaluate(input.joint_names, point.joint_positions, input.allowed_touch_pairs,
                         input.temporal_contact_policy, input.gripper_position);
    if (!state) {
      return fail("MOTION_STATE_EVIDENCE_UNAVAILABLE",
                  "FK or independent collision evidence is unavailable for a trajectory point");
    }
    artifact->samples.push_back({state->tcp_pose, point.joint_positions,
                                 point.time_from_start_seconds, state->collision_free,
                                 state->raw_contact_pairs, state->attached_task_object_pose_world});
    artifact->raw_contact_pairs.insert(state->raw_contact_pairs.begin(),
                                       state->raw_contact_pairs.end());
    previous_time = point.time_from_start_seconds;
  }
  artifact->goal_joint_positions = input.points.back().joint_positions;
  return {std::move(artifact), std::nullopt};
}

}  // namespace so101_gazebo_demo::pick_place
