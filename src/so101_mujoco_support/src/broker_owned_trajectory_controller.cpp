#include "so101_mujoco_support/broker_owned_trajectory_controller.hpp"

#include <pluginlib/class_list_macros.hpp>

namespace so101_mujoco_support
{

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_configure(
  const rclcpp_lifecycle::State & previous_state)
{
  const auto result = joint_trajectory_controller::JointTrajectoryController::on_configure(
    previous_state);
  if (result != controller_interface::CallbackReturn::SUCCESS) {
    return result;
  }
  // The base controller also accepts unowned fire-and-forget topic commands.
  // Drop that subscription before this controller can be activated.
  subscriber_is_active_.store(false);
  joint_command_subscriber_.reset();
  return controller_interface::CallbackReturn::SUCCESS;
}

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_activate(
  const rclcpp_lifecycle::State & previous_state)
{
  if (joint_command_subscriber_) {
    return controller_interface::CallbackReturn::ERROR;
  }
  const auto result = joint_trajectory_controller::JointTrajectoryController::on_activate(
    previous_state);
  subscriber_is_active_.store(false);
  return result;
}

}  // namespace so101_mujoco_support

PLUGINLIB_EXPORT_CLASS(
  so101_mujoco_support::BrokerOwnedTrajectoryController,
  controller_interface::ControllerInterface)
