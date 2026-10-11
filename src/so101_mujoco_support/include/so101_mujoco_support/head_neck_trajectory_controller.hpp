#ifndef SO101_MUJOCO_SUPPORT__HEAD_NECK_TRAJECTORY_CONTROLLER_HPP_
#define SO101_MUJOCO_SUPPORT__HEAD_NECK_TRAJECTORY_CONTROLLER_HPP_

#include <joint_trajectory_controller/joint_trajectory_controller.hpp>

#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "so101_mujoco_support/head_neck_deadman.hpp"

namespace so101_mujoco_support
{

// The Head neck controller: a thin subclass of the stock Jazzy joint_trajectory_controller
// (4.42.1). It adds no limits of its own; the trajectory shape, speed and prefix checks live in
// the Python guard (design section 2). What it adds is closure and fault behaviour:
//   * inputs closed after every base configure (no topic command, no speed-scaling input, no
//     query service, angle wraparound off, immutable parameters frozen);
//   * per-tick refusal of a scaling factor other than 1 and of non-finite state (return ERROR);
//   * action goals admitted only while the owner's dead-man socket is connected and unlatched;
//   * a latch (owner EOF or silence) that aborts the active goal and holds.
// A deactivation never forwards a non-finite command.
class HeadNeckTrajectoryController : public joint_trajectory_controller::JointTrajectoryController
{
public:
  ~HeadNeckTrajectoryController() override;

  controller_interface::CallbackReturn on_init() override;
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

  enum class ErrorReason : int {
    NONE = 0, SCALING_FACTOR, NON_FINITE_STATE, NON_FINITE_COMMANDED_STATE
  };

protected:
  // The one admission decision shared by the action callback and the tests.
  bool goal_admitted() const;
  rclcpp_action::GoalResponse decide_goal(
    const rclcpp_action::GoalUUID & uuid,
    const std::shared_ptr<const control_msgs::action::FollowJointTrajectory::Goal> & goal);
  rclcpp_action::CancelResponse decide_cancel(
    const std::shared_ptr<rclcpp_action::ServerGoalHandle<
      control_msgs::action::FollowJointTrajectory>> & goal_handle);
  std::shared_ptr<NeckDeadman> deadman_copy() const;
  ErrorReason last_error_reason() const {return error_reason_.load(std::memory_order_acquire);}
  uint64_t goals_rejected() const {return goals_rejected_.load(std::memory_order_acquire);}
  uint64_t activation_id() const {return activation_id_.load(std::memory_order_acquire);}
  bool latch_handled_for_test() const {return latch_handled_;}

private:
  void close_inputs();
  void check_immutable_configuration();
  void create_action_server();
  void register_parameter_callback();
  void set_internal_parameter(const std::string & name, int64_t value);
  void stop_deadman();
  void sanitize_command_interface() noexcept;
  void finish_stranded_cancels();

  mutable std::mutex deadman_mutex_;
  std::shared_ptr<NeckDeadman> deadman_;
  std::atomic<NeckDeadman *> rt_deadman_{nullptr};
  std::atomic<bool> active_{false};
  std::atomic<uint64_t> activation_id_{0};
  std::atomic<uint64_t> goals_rejected_{0};
  std::atomic<ErrorReason> error_reason_{ErrorReason::NONE};
  std::atomic<bool> pid_set_{false};
  std::atomic<bool> internal_set_{false};
  bool latch_handled_{false};
  double last_finite_command_{0.0};
  bool have_finite_command_{false};
  std::atomic<bool> parameter_frozen_{false};
  std::string deadman_directory_;
  double deadman_timeout_s_{0.2};
  rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr parameter_callback_;

  // Canceled goals that were no longer the active goal (the latch had already aborted them). The
  // realtime handle cannot finish them, so a non-realtime timer does.
  struct StrandedCancel
  {
    std::shared_ptr<rclcpp_action::ServerGoalHandle<
      control_msgs::action::FollowJointTrajectory>> goal;
    int attempts{0};
  };
  std::mutex stranded_mutex_;
  std::vector<StrandedCancel> stranded_cancels_;
  rclcpp::TimerBase::SharedPtr stranded_timer_;
};

}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__HEAD_NECK_TRAJECTORY_CONTROLLER_HPP_
