#include "so101_gazebo_demo/pick_place/so101_motion_planner.hpp"

#include <utility>

namespace so101_gazebo_demo::pick_place
{

bool isCarryingMotionState(State state) noexcept
{
  switch (state) {
    case State::LIFT:
    case State::MOVE_ABOVE_PLACE:
    case State::DESCEND_TO_PLACE:
    case State::RECOVER_LIFT_TO_SAFE_HEIGHT:
    case State::RECOVER_MOVE_ABOVE_PICK:
    case State::RECOVER_DESCEND_TO_PICK:
      return true;
    default:
      return false;
  }
}

SO101MotionPlanner::SO101MotionPlanner(std::shared_ptr<const IJointMotionTargetPolicy> policy,
                                       std::shared_ptr<IMoveItJointMotionAdapter> adapter,
                                       SO101Profile profile)
: policy_(std::move(policy)), adapter_(std::move(adapter)), profile_(std::move(profile))
{
}

PlanResult SO101MotionPlanner::plan(State state, State next_state,
                                    const ObservationResult & observation)
{
  if (!policy_ || !adapter_) {
    return {{ActionStatus::FAILED,
             Failure{FailureCategory::CONFIGURATION, "MOTION_DEPENDENCY_MISSING",
                     "SO-101 motion planner requires target policy and MoveIt adapter", {}}},
            nullptr};
  }
  auto selected = policy_->target(state, next_state, observation);
  if (!selected.target) {
    return {{ActionStatus::FAILED,
             selected.failure.value_or(Failure{FailureCategory::CONFIGURATION,
                                               "MOTION_TARGET_UNAVAILABLE",
                                               "SO-101 motion target is unavailable", {}})},
            nullptr};
  }
  const auto & target = *selected.target;
  JointMotionRequest request{state, next_state, target.joint_names, target.joint_waypoints,
                             target.ladder, isCarryingMotionState(state), {},
                             target.gripper_position,
                             target.temporal_contact_policy};
  if (state == State::DESCEND) {
    for (const auto & link : profile_.moveit_touch_links) {
      request.allowed_touch_pairs.insert(profile_.coke_model + ":" + link);
    }
  }
  return adapter_->plan(request, observation);
}

}  // namespace so101_gazebo_demo::pick_place
