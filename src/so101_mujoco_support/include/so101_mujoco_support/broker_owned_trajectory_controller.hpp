#ifndef SO101_MUJOCO_SUPPORT__BROKER_OWNED_TRAJECTORY_CONTROLLER_HPP_
#define SO101_MUJOCO_SUPPORT__BROKER_OWNED_TRAJECTORY_CONTROLLER_HPP_

#include <joint_trajectory_controller/joint_trajectory_controller.hpp>

#include <chrono>
#include <filesystem>
#include <memory>
#include <mutex>
#include <string>

#include "so101_mujoco_support/controller_goal_admission.hpp"
#include "so101_mujoco_support/controller_reservation_provision.hpp"
#include "so101_mujoco_support/controller_reservation_socket.hpp"

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

private:
  void configure_reservation_scope();
  void start_reservation_monitor();
  void poll_reservation_provision();
  void close_reservation_service();

  std::mutex reservation_mutex_;
  std::unique_ptr<ControllerReservationService> reservation_service_;
  rclcpp::TimerBase::SharedPtr reservation_timer_;
  std::filesystem::path reservation_provision_path_;
  std::filesystem::path reservation_socket_path_;
  std::string reservation_session_;
  ControllerReservationRole reservation_role_{ControllerReservationRole::ARM};
  std::chrono::steady_clock::time_point reservation_deadline_;
};

}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__BROKER_OWNED_TRAJECTORY_CONTROLLER_HPP_
