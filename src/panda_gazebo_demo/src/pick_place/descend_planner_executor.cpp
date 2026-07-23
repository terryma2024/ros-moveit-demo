#include "panda_gazebo_demo/pick_place/descend_planner_executor.hpp"

#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "panda_gazebo_demo/pick_place/motion_state_action.hpp"
#include "panda_gazebo_demo/pick_place/moveit_motion_adapter.hpp"

namespace panda_gazebo_demo::pick_place
{

class DescendPlannerExecutor::Impl
{
public:
  Impl(std::shared_ptr<rclcpp::Node> node, std::string planning_group, std::string tcp_link,
       std::shared_ptr<const PickPlaceTargetPolicy> target_policy, double velocity_scaling,
       double acceleration_scaling, double eef_step) :
      adapter(std::make_shared<MoveItMotionAdapter>(
        std::move(node), std::move(planning_group), std::move(tcp_link),
        std::vector<std::string>{"table", "coke"}, velocity_scaling, acceleration_scaling,
        eef_step)),
      action(adapter, std::move(target_policy),
             {State::DESCEND, State::CLOSE_GRIPPER, MotionKind::CARTESIAN_DOWN, false})
  {
  }

  std::shared_ptr<MoveItMotionAdapter> adapter;
  MotionStateAction action;
};

DescendPlannerExecutor::DescendPlannerExecutor(
  std::shared_ptr<rclcpp::Node> node, std::string planning_group, std::string tcp_link,
  std::shared_ptr<const PickPlaceTargetPolicy> target_policy, double velocity_scaling,
  double acceleration_scaling, double eef_step, double min_fraction, double joint_jump_threshold,
  double tcp_position_tolerance, double tcp_orientation_tolerance_rad) :
    impl_(std::make_unique<Impl>(std::move(node), std::move(planning_group), std::move(tcp_link),
                                 std::move(target_policy), velocity_scaling, acceleration_scaling,
                                 eef_step))
{
  static_cast<void>(min_fraction);
  static_cast<void>(joint_jump_threshold);
  static_cast<void>(tcp_position_tolerance);
  static_cast<void>(tcp_orientation_tolerance_rad);
}

DescendPlannerExecutor::~DescendPlannerExecutor() = default;

PlanResult DescendPlannerExecutor::plan(State current_state, State next_state,
                                        const ObservationResult & observation)
{
  return impl_->action.plan(current_state, next_state, observation);
}

ActionResult DescendPlannerExecutor::execute(const ExecutionContext & context)
{
  return impl_->action.execute(context);
}

ActionResult DescendPlannerExecutor::cancel()
{
  return impl_->action.cancel();
}

}  // namespace panda_gazebo_demo::pick_place
