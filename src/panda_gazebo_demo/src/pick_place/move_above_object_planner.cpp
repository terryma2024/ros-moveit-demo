#include "panda_gazebo_demo/pick_place/move_above_object_planner.hpp"

#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "panda_gazebo_demo/pick_place/motion_state_action.hpp"
#include "panda_gazebo_demo/pick_place/moveit_motion_adapter.hpp"

namespace panda_gazebo_demo::pick_place
{

class MoveAboveObjectPlanner::Impl
{
public:
  Impl(
    std::shared_ptr<rclcpp::Node> node, std::string planning_group,
    std::string tcp_link, std::vector<std::string> required_world_objects,
    std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
    double velocity_scaling, double acceleration_scaling)
  : adapter(std::make_shared<MoveItMotionAdapter>(
      std::move(node), std::move(planning_group), std::move(tcp_link),
      std::move(required_world_objects), velocity_scaling, acceleration_scaling, 0.005)),
    action(adapter, std::move(target_policy),
      {State::MOVE_ABOVE_OBJECT, State::DESCEND, MotionKind::POSE, false})
  {
  }

  std::shared_ptr<MoveItMotionAdapter> adapter;
  MotionStateAction action;
};

MoveAboveObjectPlanner::MoveAboveObjectPlanner(
  std::shared_ptr<rclcpp::Node> node, std::string planning_group,
  std::string tcp_link, std::vector<std::string> required_world_objects,
  std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
  double velocity_scaling, double acceleration_scaling)
: impl_(std::make_unique<Impl>(std::move(node), std::move(planning_group),
    std::move(tcp_link), std::move(required_world_objects), std::move(target_policy),
    velocity_scaling, acceleration_scaling))
{
}

MoveAboveObjectPlanner::~MoveAboveObjectPlanner() = default;

PlanResult MoveAboveObjectPlanner::plan(
  State current_state, State next_state,
  const ObservationResult & observation)
{
  return impl_->action.plan(current_state, next_state, observation);
}

ActionResult MoveAboveObjectPlanner::execute(const ExecutionContext & context)
{
  return impl_->action.execute(context);
}

ActionResult MoveAboveObjectPlanner::cancel()
{
  return impl_->action.cancel();
}

ObservationResult MoveAboveObjectPlanner::observe()
{
  return impl_->adapter->observe();
}

}  // namespace panda_gazebo_demo::pick_place
