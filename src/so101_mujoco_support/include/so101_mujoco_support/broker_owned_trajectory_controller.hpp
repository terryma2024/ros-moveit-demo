#ifndef SO101_MUJOCO_SUPPORT__BROKER_OWNED_TRAJECTORY_CONTROLLER_HPP_
#define SO101_MUJOCO_SUPPORT__BROKER_OWNED_TRAJECTORY_CONTROLLER_HPP_

#include <joint_trajectory_controller/joint_trajectory_controller.hpp>

#include <chrono>
#include <atomic>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <mutex>
#include <optional>
#include <string>

#include "so101_mujoco_support/controller_goal_admission.hpp"
#include "so101_mujoco_support/controller_ingress_witness.hpp"
#include "so101_mujoco_support/controller_reservation_provision.hpp"
#include "so101_mujoco_support/controller_reservation_socket.hpp"
#include "so101_mujoco_support/controller_stop_witness.hpp"

namespace so101_mujoco_support
{

class BrokerOwnedTrajectoryController
  : public joint_trajectory_controller::JointTrajectoryController
{
public:
  controller_interface::return_type update(
    const rclcpp::Time & time, const rclcpp::Duration & period) override;

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
  // Reachable by subclasses only (tests use it as the controlled lifecycle seam).
  void close_reservation_service();
  // The active bound gate is shared with the reservation service; the pointer is
  // only copied/swapped under the lifecycle mutex. Production has no setter.
  std::shared_ptr<ControllerGoalAdmission> active_goal_admission_;

  // One decision helper shared by the rclcpp goal callback and the tests, so the
  // tests exercise the real callback decision rather than a parallel copy.
  rclcpp_action::GoalResponse decide_goal_admission(
    const rclcpp_action::GoalUUID & uuid,
    const std::shared_ptr<const control_msgs::action::FollowJointTrajectory::Goal> & goal);

  // Brief pointer copy: callers must not hold the lifecycle mutex while using it.
  std::shared_ptr<ControllerGoalAdmission> active_gate_copy() const
  {
    std::lock_guard<std::mutex> lock(reservation_mutex_);
    return active_goal_admission_;
  }

  // Test-only injection point (protected, so production callers cannot reach it).
  void install_active_gate_for_testing(std::shared_ptr<ControllerGoalAdmission> gate)
  {
    std::lock_guard<std::mutex> lock(reservation_mutex_);
    active_goal_admission_ = std::move(gate);
  }

  // Controlled test seam: stage the same immutable Head candidate consumed by update().
  void stage_head_trajectory_for_testing(
    std::shared_ptr<trajectory_msgs::msg::JointTrajectory> trajectory);

  // Atomically detach the service and the active gate, then release the mutex.
  void detach_reservation_lifecycle(
    std::unique_ptr<ControllerReservationService> * service,
    std::unique_ptr<ControllerReservationService> * primary_fault,
    std::shared_ptr<ControllerGoalAdmission> * gate)
  {
    std::lock_guard<std::mutex> lock(reservation_mutex_);
    if (reservation_timer_) {
      reservation_timer_->cancel();
      reservation_timer_.reset();
    }
    *service = std::move(reservation_service_);
    *primary_fault = std::move(primary_fault_service_);
    *gate = std::move(active_goal_admission_);
  }
  std::shared_ptr<ControllerGoalAdmission> make_scoped_goal_admission(
    const ServiceControllerIdentity & identity)
  {
    return std::make_shared<ControllerGoalAdmission>(
      []() {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch()).count();
      }, 250000000, 1048576, 2048, identity, revocation_latch_);
  }
  std::optional<ControllerStopWitness::Proof> controller_stop_proof(
    int64_t now_monotonic_ns);
  std::optional<ControllerIngressWitness::Snapshot> controller_ingress_snapshot();

private:
  enum class HeadTerminalRequest : uint8_t {NONE, ABORT, CANCEL};
  struct HeadCandidate
  {
    std::shared_ptr<trajectory_msgs::msg::JointTrajectory> trajectory;
    RealtimeGoalHandlePtr goal;
    joint_trajectory_controller::SegmentTolerances tolerances;
    control_msgs::action::FollowJointTrajectory::Result::SharedPtr result;
    std::atomic<bool> consumed{false};
    std::atomic<bool> cancel_requested{false};
    std::atomic<HeadTerminalRequest> terminal{HeadTerminalRequest::NONE};
    std::atomic<bool> retired{false};
    std::mutex status_mutex;
    rclcpp::TimerBase::SharedPtr status_timer;
  };

  void configure_reservation_scope();
  void configure_head_parameters();
  void start_reservation_monitor();
  void poll_reservation_provision();
  bool validate_head_goal_shape(
    const trajectory_msgs::msg::JointTrajectory & trajectory) const;
  bool validate_head_prefix(
    const trajectory_msgs::msg::JointTrajectory & trajectory,
    const trajectory_msgs::msg::JointTrajectoryPoint & measured,
    int64_t update_time_ns) const;
  bool hold_head_at_current_position() noexcept;
  void fail_head_candidate_without_hold(const std::shared_ptr<HeadCandidate> & candidate) noexcept;
  void accept_head_goal(
    const std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowJTrajAction>> & goal_handle);
  rclcpp_action::CancelResponse cancel_head_goal(
    const std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowJTrajAction>> & goal_handle);
  void monitor_head_goal(const std::shared_ptr<HeadCandidate> & candidate);
  void retire_head_goal_for_lifecycle();

  mutable std::mutex reservation_mutex_;
  std::unique_ptr<ControllerReservationService> reservation_service_;
  std::unique_ptr<ControllerReservationService> primary_fault_service_;
  ControllerGoalAdmission::RevocationLatch revocation_latch_{
    std::make_shared<std::atomic<bool>>(false)};
  rclcpp::TimerBase::SharedPtr reservation_timer_;
  std::filesystem::path reservation_provision_path_;
  std::filesystem::path reservation_socket_path_;
  std::filesystem::path primary_fault_provision_path_;
  std::filesystem::path primary_fault_socket_path_;
  std::string reservation_session_;
  ControllerReservationRole reservation_role_{ControllerReservationRole::ARM};
  std::chrono::steady_clock::time_point reservation_deadline_;
  std::chrono::nanoseconds head_fault_connection_timeout_{2000000};
  bool head_simulation_mode_{false};
  bool head_measured_prefix_guard_enabled_{false};
  std::atomic<bool> head_motion_faulted_{false};
  realtime_tools::RealtimeBuffer<std::shared_ptr<HeadCandidate>> head_candidate_buffer_;
  mutable std::mutex head_goal_mutex_;
  std::shared_ptr<HeadCandidate> head_owned_candidate_;
  std::shared_ptr<trajectory_msgs::msg::JointTrajectory> head_hold_position_msg_;
  std::atomic<bool> head_goal_reserved_{false};
  std::atomic<bool> head_active_goal_{false};
  rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr head_parameter_callback_;
  ControllerStopWitness arm_stop_witness_{5};
  ControllerStopWitness gripper_stop_witness_{1};
  ControllerStopWitness neck_stop_witness_{1};
  std::atomic<size_t> monitored_joints_{0};
  std::atomic<bool> witness_active_{false};
  std::atomic<uint64_t> update_sequence_{0};
  ControllerIngressWitness ingress_witness_;
};

}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__BROKER_OWNED_TRAJECTORY_CONTROLLER_HPP_
