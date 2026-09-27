#include "so101_mujoco_support/broker_owned_trajectory_controller.hpp"

#include <pluginlib/class_list_macros.hpp>
#include <rclcpp_action/create_server.hpp>

namespace so101_mujoco_support
{

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_configure(
  const rclcpp_lifecycle::State & previous_state)
{
  goal_admission_.close();
  const auto result = joint_trajectory_controller::JointTrajectoryController::on_configure(
    previous_state);
  if (result != controller_interface::CallbackReturn::SUCCESS) {
    return result;
  }
  // The base controller also accepts unowned fire-and-forget topic commands.
  // Drop that subscription before this controller can be activated.
  subscriber_is_active_.store(false);
  joint_command_subscriber_.reset();
  // The base server binds directly to its own callbacks. Releasing it removes
  // its waitable before registering the admission-wrapped server.
  action_server_.reset();
  try {
    action_server_ = rclcpp_action::create_server<FollowJTrajAction>(
      get_node()->get_node_base_interface(), get_node()->get_node_clock_interface(),
      get_node()->get_node_logging_interface(), get_node()->get_node_waitables_interface(),
      std::string(get_node()->get_name()) + "/follow_joint_trajectory",
      [this](
        const rclcpp_action::GoalUUID & uuid,
        std::shared_ptr<const FollowJTrajAction::Goal> goal)
      {
        if (!goal || goal_admission_.admit_current(uuid, *goal) !=
        ControllerGoalAdmission::Result::ALLOW)
        {
          return rclcpp_action::GoalResponse::REJECT;
        }
        return joint_trajectory_controller::JointTrajectoryController::goal_received_callback(
          uuid, goal);
      },
      [this](
        std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowJTrajAction>> goal_handle)
      {
        return joint_trajectory_controller::JointTrajectoryController::goal_cancelled_callback(
          goal_handle);
      },
      [this](
        std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowJTrajAction>> goal_handle)
      {
        joint_trajectory_controller::JointTrajectoryController::goal_accepted_callback(goal_handle);
      });
  } catch (const std::exception & error) {
    RCLCPP_ERROR(get_node()->get_logger(), "Action admission setup failed: %s", error.what());
    action_server_.reset();
    return controller_interface::CallbackReturn::ERROR;
  }
  return controller_interface::CallbackReturn::SUCCESS;
}

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_activate(
  const rclcpp_lifecycle::State & previous_state)
{
  if (joint_command_subscriber_ || !action_server_) {
    return controller_interface::CallbackReturn::ERROR;
  }
  const auto result = joint_trajectory_controller::JointTrajectoryController::on_activate(
    previous_state);
  subscriber_is_active_.store(false);
  return result;
}

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_deactivate(
  const rclcpp_lifecycle::State & previous_state)
{
  goal_admission_.close();
  return joint_trajectory_controller::JointTrajectoryController::on_deactivate(previous_state);
}

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_cleanup(
  const rclcpp_lifecycle::State & previous_state)
{
  goal_admission_.close();
  action_server_.reset();
  return joint_trajectory_controller::JointTrajectoryController::on_cleanup(previous_state);
}

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_error(
  const rclcpp_lifecycle::State & previous_state)
{
  goal_admission_.close();
  action_server_.reset();
  return joint_trajectory_controller::JointTrajectoryController::on_error(previous_state);
}

}  // namespace so101_mujoco_support

PLUGINLIB_EXPORT_CLASS(
  so101_mujoco_support::BrokerOwnedTrajectoryController,
  controller_interface::ControllerInterface)
