#ifndef SO101_MUJOCO_SUPPORT__BROKER_OWNED_TRAJECTORY_CONTROLLER_HPP_
#define SO101_MUJOCO_SUPPORT__BROKER_OWNED_TRAJECTORY_CONTROLLER_HPP_

#include <joint_trajectory_controller/joint_trajectory_controller.hpp>

#include "so101_mujoco_support/controller_goal_admission.hpp"

namespace so101_mujoco_support
{

class BrokerOwnedTrajectoryController
  : public joint_trajectory_controller::JointTrajectoryController
{
public:
  controller_interface::CallbackReturn on_configure(
    const rclcpp_lifecycle::State & previous_state) override;

  controller_interface::CallbackReturn on_activate(
    const rclcpp_lifecycle::State & previous_state) override;

  controller_interface::CallbackReturn on_deactivate(
    const rclcpp_lifecycle::State & previous_state) override;

  controller_interface::CallbackReturn on_cleanup(
    const rclcpp_lifecycle::State & previous_state) override;

  controller_interface::CallbackReturn on_error(
    const rclcpp_lifecycle::State & previous_state) override;

protected:
  ControllerGoalAdmission goal_admission_;
};

}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__BROKER_OWNED_TRAJECTORY_CONTROLLER_HPP_
