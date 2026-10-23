#include "so101_mujoco_support/head_neck_trajectory_controller.hpp"

#include <unistd.h>

#include <chrono>
#include <cmath>
#include <stdexcept>
#include <vector>

#include <pluginlib/class_list_macros.hpp>
#include <rcl_interfaces/msg/parameter_descriptor.hpp>
#include <rclcpp_action/create_server.hpp>

namespace so101_mujoco_support
{
namespace
{
constexpr char kDirectory[] = "head_deadman_directory";
constexpr char kTimeout[] = "head_deadman_timeout_s";
constexpr char kPeerPid[] = "head_deadman_peer_pid";
constexpr char kActivationId[] = "head_activation_id";

bool finite(const std::vector<double> & values)
{
  for (const double value : values) {
    if (!std::isfinite(value)) {return false;}
  }
  return true;
}

bool finite(const trajectory_msgs::msg::JointTrajectoryPoint & point)
{
  return finite(point.positions) && finite(point.velocities) && finite(point.accelerations);
}

// The stock JTC keeps its ~/speed_scaling_input subscription in a private member. The explicit
// instantiation access idiom reaches exactly that member (no header edit, no ODR violation).
using ScalingSubscription = rclcpp::Subscription<control_msgs::msg::SpeedScalingFactor>::SharedPtr;
struct ScalingSubscriptionTag
{
  using type = ScalingSubscription joint_trajectory_controller::JointTrajectoryController::*;
  friend type get(ScalingSubscriptionTag);
};
template<typename Tag, typename Tag::type Member>
struct MemberAccess
{
  friend typename Tag::type get(Tag) {return Member;}
};
}  // namespace
template struct MemberAccess<ScalingSubscriptionTag,
  &joint_trajectory_controller::JointTrajectoryController::scaling_factor_sub_>;

HeadNeckTrajectoryController::~HeadNeckTrajectoryController() {stop_deadman();}

controller_interface::CallbackReturn HeadNeckTrajectoryController::on_init()
{
  const auto result = joint_trajectory_controller::JointTrajectoryController::on_init();
  if (result != controller_interface::CallbackReturn::SUCCESS) {return result;}
  try {
    const auto node = get_node();
    rcl_interfaces::msg::ParameterDescriptor read_only;
    read_only.read_only = true;
    node->declare_parameter(kDirectory, std::string(), read_only);
    node->declare_parameter(kTimeout, 0.2, read_only);
    node->declare_parameter(kPeerPid, int64_t(0));
    node->declare_parameter(kActivationId, int64_t(0));
    register_parameter_callback();
  } catch (const std::exception & error) {
    RCLCPP_ERROR(get_node()->get_logger(), "Head neck parameters refused: %s", error.what());
    return controller_interface::CallbackReturn::ERROR;
  }
  return controller_interface::CallbackReturn::SUCCESS;
}

void HeadNeckTrajectoryController::register_parameter_callback()
{
  parameter_callback_ = get_node()->add_on_set_parameters_callback(
    [this](const std::vector<rclcpp::Parameter> & parameters) {
      rcl_interfaces::msg::SetParametersResult response;
      response.successful = true;
      const bool internal = internal_set_.load(std::memory_order_acquire);
      for (const auto & parameter : parameters) {
        const auto & name = parameter.get_name();
        if (name == kPeerPid) {
          if (internal) {continue;}
          if (active_.load(std::memory_order_acquire)) {
            response.successful = false;
            response.reason = "CONTROLLER_HEAD_PEER_PID_READ_ONLY_WHILE_ACTIVE";
          } else if (parameter.get_type() != rclcpp::ParameterType::PARAMETER_INTEGER ||
            parameter.as_int() <= 0)
          {
            response.successful = false;
            response.reason = "CONTROLLER_HEAD_PEER_PID_INVALID";
          } else if (pid_set_.exchange(true, std::memory_order_acq_rel)) {
            response.successful = false;
            response.reason = "CONTROLLER_HEAD_PEER_PID_SET_ONCE_PER_ACTIVATION";
          }
        } else if (name == kActivationId || name == kDirectory || name == kTimeout) {
          if (!internal && get_node()->has_parameter(name) && name != kDirectory && name != kTimeout) {
            response.successful = false;
            response.reason = "CONTROLLER_HEAD_PARAMETER_INTERNAL_ONLY";
          }
        } else if (!internal && (name == "open_loop_control" ||
          name == "interpolate_from_desired_state" || name == "interpolation_method" ||
          name == "allow_partial_joints_goal" || name == "allow_integration_in_goal_trajectories" ||
          name.rfind("speed_scaling.", 0) == 0))
        {
          // Only after the configuration was frozen; declaration-time overrides pass before.
          if (parameter_frozen_) {
            response.successful = false;
            response.reason = "CONTROLLER_HEAD_JTC_CONFIGURATION_IMMUTABLE";
          }
        }
        if (!response.successful) {break;}
      }
      return response;
    });
}

void HeadNeckTrajectoryController::set_internal_parameter(const std::string & name, int64_t value)
{
  internal_set_.store(true, std::memory_order_release);
  try {
    get_node()->set_parameter(rclcpp::Parameter(name, value));
  } catch (...) {
    internal_set_.store(false, std::memory_order_release);
    throw;
  }
  internal_set_.store(false, std::memory_order_release);
}

std::shared_ptr<NeckDeadman> HeadNeckTrajectoryController::deadman_copy() const
{
  std::lock_guard<std::mutex> lock(deadman_mutex_);
  return deadman_;
}

bool HeadNeckTrajectoryController::goal_admitted() const
{
  if (!active_.load(std::memory_order_acquire)) {return false;}
  const auto deadman = deadman_copy();
  return deadman && deadman->owner_connected() && !deadman->latched();
}

rclcpp_action::CancelResponse HeadNeckTrajectoryController::decide_cancel(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowJTrajAction>> & goal_handle)
{
  // The base callback hands a cancel to the realtime goal handle only while the goal is still the
  // active goal. The dead-man latch aborts the active goal on the controller thread and clears it,
  // and a cancel can arrive just after that (or between this callback's read and the latch's
  // clear): the goal then becomes canceling, the realtime handle only aborts an executing goal, and
  // the goal would stay canceling for good, so the stop could never be proved. Every accepted
  // cancel is therefore watched: a goal still canceling after a short grace (the normal path ends
  // in a few milliseconds through the realtime handle) is finished here as canceled by a
  // non-realtime timer. The server marks the goal canceling only after this callback returns.
  const auto response =
    joint_trajectory_controller::JointTrajectoryController::goal_cancelled_callback(goal_handle);
  if (response == rclcpp_action::CancelResponse::ACCEPT) {
    const auto accepted = std::chrono::steady_clock::now();
    std::lock_guard<std::mutex> lock(stranded_mutex_);
    stranded_cancels_.push_back(StrandedCancel{
        goal_handle, accepted + kStrandedCancelGrace, accepted + kStrandedCancelExpiry});
  }
  return response;
}

void HeadNeckTrajectoryController::finish_stranded_cancels()
{
  std::vector<StrandedCancel> pending;
  {
    std::lock_guard<std::mutex> lock(stranded_mutex_);
    pending.swap(stranded_cancels_);
  }
  const auto now = std::chrono::steady_clock::now();
  std::vector<StrandedCancel> waiting;
  for (auto & entry : pending) {
    if (!entry.goal->is_active() || now >= entry.expires) {continue;}
    if (now < entry.ready || !entry.goal->is_canceling()) {
      waiting.push_back(entry);
      continue;
    }
    try {
      auto result = std::make_shared<FollowJTrajAction::Result>();
      result->set__error_code(FollowJTrajAction::Result::SUCCESSFUL);
      result->set__error_string("Canceled: the realtime goal handle did not finish the goal");
      entry.goal->canceled(result);
    } catch (const std::exception & failure) {
      RCLCPP_WARN(get_node()->get_logger(), "Stranded cancel not finished: %s", failure.what());
    }
  }
  if (!waiting.empty()) {
    std::lock_guard<std::mutex> lock(stranded_mutex_);
    stranded_cancels_.insert(stranded_cancels_.end(), waiting.begin(), waiting.end());
  }
}

rclcpp_action::GoalResponse HeadNeckTrajectoryController::decide_goal(
  const rclcpp_action::GoalUUID & uuid,
  const std::shared_ptr<const control_msgs::action::FollowJointTrajectory::Goal> & goal)
{
  if (!goal_admitted()) {
    goals_rejected_.fetch_add(1, std::memory_order_acq_rel);
    return rclcpp_action::GoalResponse::REJECT;
  }
  return joint_trajectory_controller::JointTrajectoryController::goal_received_callback(uuid, goal);
}

void HeadNeckTrajectoryController::close_inputs()
{
  // The base controller accepts unowned fire-and-forget topic commands: drop that subscription.
  subscriber_is_active_.store(false);
  joint_command_subscriber_.reset();
  (this->*get(ScalingSubscriptionTag{})).reset();
  query_state_srv_.reset();
  // The continuous physical neck must keep the unwrapped coordinates the guard checked.
  if (joints_angle_wraparound_.size() == 1) {joints_angle_wraparound_[0] = false;}
  scaling_factor_.store(1.0, std::memory_order_release);
  scaling_factor_cmd_.store(1.0, std::memory_order_release);
}

void HeadNeckTrajectoryController::check_immutable_configuration()
{
  if (get_update_rate() != 500 || params_.joints != std::vector<std::string>{"neck_yaw_joint"} ||
    !params_.command_joints.empty() ||
    params_.command_interfaces != std::vector<std::string>{"position"} ||
    params_.state_interfaces != std::vector<std::string>{"position", "velocity"} ||
    params_.open_loop_control || params_.interpolate_from_desired_state ||
    params_.interpolation_method != "splines" || params_.allow_partial_joints_goal ||
    params_.allow_integration_in_goal_trajectories ||
    !params_.speed_scaling.state_interface.empty() ||
    !params_.speed_scaling.command_interface.empty() ||
    params_.speed_scaling.initial_scaling_factor != 1.0 ||
    joints_angle_wraparound_.size() != 1 || joints_angle_wraparound_[0] ||
    !has_position_command_interface_ || has_velocity_command_interface_ ||
    !has_velocity_state_interface_ || has_acceleration_state_interface_)
  {
    throw std::runtime_error("CONTROLLER_HEAD_NECK_CONFIGURATION_UNSUPPORTED");
  }
}

void HeadNeckTrajectoryController::create_action_server()
{
  // The goal callbacks of 4.42.1 are non-virtual, so the base server is destroyed and re-created
  // with admission-wrapped callbacks. Releasing it removes its waitable first.
  action_server_.reset();
  action_server_ = rclcpp_action::create_server<FollowJTrajAction>(
    get_node()->get_node_base_interface(), get_node()->get_node_clock_interface(),
    get_node()->get_node_logging_interface(), get_node()->get_node_waitables_interface(),
    std::string(get_node()->get_name()) + "/follow_joint_trajectory",
    [this](
      const rclcpp_action::GoalUUID & uuid, std::shared_ptr<const FollowJTrajAction::Goal> goal)
    {
      return decide_goal(uuid, goal);
    },
    [this](std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowJTrajAction>> goal_handle)
    {
      return decide_cancel(goal_handle);
    },
    [this](std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowJTrajAction>> goal_handle)
    {
      // The latch can be set between the admission and this acceptance.
      if (!goal_admitted()) {
        auto result = std::make_shared<FollowJTrajAction::Result>();
        result->error_code = FollowJTrajAction::Result::INVALID_GOAL;
        result->error_string = "Head neck dead-man latched before the goal was accepted";
        goal_handle->execute();
        goal_handle->abort(result);
        return;
      }
      joint_trajectory_controller::JointTrajectoryController::goal_accepted_callback(goal_handle);
    });
  {
    std::lock_guard<std::mutex> lock(stranded_mutex_);
    stranded_cancels_.clear();
  }
  stranded_timer_.reset();
  stranded_timer_ = get_node()->create_wall_timer(
    std::chrono::milliseconds(10), [this]() {finish_stranded_cancels();});
}

controller_interface::CallbackReturn HeadNeckTrajectoryController::on_configure(
  const rclcpp_lifecycle::State & previous_state)
{
  try {
    const auto node = get_node();
    deadman_directory_ = node->get_parameter(kDirectory).as_string();
    deadman_timeout_s_ = node->get_parameter(kTimeout).as_double();
    if (deadman_directory_.empty() || deadman_directory_[0] != '/' ||
      !(deadman_timeout_s_ > 0.0 && deadman_timeout_s_ <= 1.0))
    {
      RCLCPP_ERROR(node->get_logger(), "Head neck dead-man configuration invalid");
      return controller_interface::CallbackReturn::ERROR;
    }
  } catch (const std::exception & error) {
    RCLCPP_ERROR(get_node()->get_logger(), "Head neck dead-man parameters: %s", error.what());
    return controller_interface::CallbackReturn::ERROR;
  }
  parameter_frozen_ = false;
  const auto result = joint_trajectory_controller::JointTrajectoryController::on_configure(
    previous_state);
  if (result != controller_interface::CallbackReturn::SUCCESS) {return result;}
  try {
    close_inputs();
    check_immutable_configuration();
    create_action_server();
    parameter_frozen_ = true;
  } catch (const std::exception & failure) {
    RCLCPP_ERROR(get_node()->get_logger(), "Head neck configuration refused: %s", failure.what());
    action_server_.reset();
    return controller_interface::CallbackReturn::ERROR;
  }
  return controller_interface::CallbackReturn::SUCCESS;
}

controller_interface::CallbackReturn HeadNeckTrajectoryController::on_activate(
  const rclcpp_lifecycle::State & previous_state)
{
  try {
    const auto node = get_node();
    const int64_t pid = node->get_parameter(kPeerPid).as_int();
    if (pid <= 0 || !pid_set_.load(std::memory_order_acquire)) {
      RCLCPP_ERROR(node->get_logger(), "Head neck activation needs the owner peer pid first");
      return controller_interface::CallbackReturn::ERROR;
    }
    NeckDeadman::Config config;
    config.directory = deadman_directory_;
    config.peer_pid = static_cast<pid_t>(pid);
    config.timeout = std::chrono::nanoseconds(static_cast<int64_t>(deadman_timeout_s_ * 1e9));
    config.activation_id = activation_id_.load() + 1;
    auto deadman = std::make_shared<NeckDeadman>(config);
    deadman->start();
    {
      std::lock_guard<std::mutex> lock(deadman_mutex_);
      deadman_ = deadman;
    }
    activation_id_.store(config.activation_id, std::memory_order_release);
    set_internal_parameter(kActivationId, static_cast<int64_t>(config.activation_id));
  } catch (const std::exception & failure) {
    RCLCPP_ERROR(get_node()->get_logger(), "Head neck dead-man refused: %s", failure.what());
    stop_deadman();
    return controller_interface::CallbackReturn::ERROR;
  }
  latch_handled_ = false;
  error_reason_.store(ErrorReason::NONE, std::memory_order_release);
  const auto result = joint_trajectory_controller::JointTrajectoryController::on_activate(
    previous_state);
  if (result != controller_interface::CallbackReturn::SUCCESS) {
    stop_deadman();
    return result;
  }
  have_finite_command_ = false;
  active_.store(true, std::memory_order_release);
  rt_deadman_.store(deadman_copy().get(), std::memory_order_release);
  return controller_interface::CallbackReturn::SUCCESS;
}

controller_interface::return_type HeadNeckTrajectoryController::update(
  const rclcpp::Time & time, const rclcpp::Duration & period)
{
  if (scaling_factor_.load(std::memory_order_acquire) != 1.0 ||
    scaling_factor_cmd_.load(std::memory_order_acquire) != 1.0)
  {
    error_reason_.store(ErrorReason::SCALING_FACTOR, std::memory_order_release);
    return controller_interface::return_type::ERROR;
  }
  read_state_from_state_interfaces(state_current_);
  if (!finite(state_current_)) {
    error_reason_.store(ErrorReason::NON_FINITE_STATE, std::memory_order_release);
    return controller_interface::return_type::ERROR;
  }
  if (!finite(state_desired_) || !finite(last_commanded_state_)) {
    error_reason_.store(ErrorReason::NON_FINITE_COMMANDED_STATE, std::memory_order_release);
    return controller_interface::return_type::ERROR;
  }
  const NeckDeadman * deadman = rt_deadman_.load(std::memory_order_acquire);
  if (deadman != nullptr && deadman->latched() && !latch_handled_) {
    latch_handled_ = true;
    const auto active_goal = *rt_active_goal_.readFromRT();
    if (active_goal) {
      auto result = std::make_shared<FollowJTrajAction::Result>();
      result->set__error_code(FollowJTrajAction::Result::INVALID_GOAL);
      result->set__error_string("Aborted: Head neck dead-man latched");
      active_goal->setAborted(result);
      rt_active_goal_.writeFromNonRT(RealtimeGoalHandlePtr());
    }
    if (active_goal || rt_has_pending_goal_.load() || !rt_is_holding_.load()) {
      rt_has_pending_goal_ = false;
      new_trajectory_msg_.reset();
      new_trajectory_msg_.initRT(set_hold_position());
    }
  }
  const auto result = joint_trajectory_controller::JointTrajectoryController::update(time, period);
  if (result == controller_interface::return_type::OK && has_position_command_interface_ &&
    !joint_command_interface_.empty() && !joint_command_interface_[0].empty())
  {
    const auto written = joint_command_interface_[0][0].get().get_optional();
    if (written.has_value() && std::isfinite(written.value())) {
      last_finite_command_ = written.value();
      have_finite_command_ = true;
    }
  }
  return result;
}

void HeadNeckTrajectoryController::sanitize_command_interface() noexcept
{
  try {
    if (!has_position_command_interface_ || joint_command_interface_.empty() ||
      joint_command_interface_[0].empty())
    {
      return;
    }
    auto & command = joint_command_interface_[0][0].get();
    const auto value = command.get_optional();
    if ((!value.has_value() || !std::isfinite(value.value())) && have_finite_command_) {
      (void)command.set_value(last_finite_command_);
    }
  } catch (...) {
  }
}

void HeadNeckTrajectoryController::stop_deadman()
{
  rt_deadman_.store(nullptr, std::memory_order_release);
  std::shared_ptr<NeckDeadman> deadman;
  {
    std::lock_guard<std::mutex> lock(deadman_mutex_);
    deadman = std::move(deadman_);
  }
  if (deadman) {deadman->stop();}
}

controller_interface::CallbackReturn HeadNeckTrajectoryController::on_deactivate(
  const rclcpp_lifecycle::State & previous_state)
{
  active_.store(false, std::memory_order_release);
  rt_deadman_.store(nullptr, std::memory_order_release);
  // The base writes the current command interface value back: it must never be non-finite.
  sanitize_command_interface();
  const auto result = joint_trajectory_controller::JointTrajectoryController::on_deactivate(
    previous_state);
  stop_deadman();
  pid_set_.store(false, std::memory_order_release);
  try {
    set_internal_parameter(kPeerPid, 0);
  } catch (...) {
  }
  return result;
}

controller_interface::CallbackReturn HeadNeckTrajectoryController::on_cleanup(
  const rclcpp_lifecycle::State & previous_state)
{
  active_.store(false, std::memory_order_release);
  stop_deadman();
  stranded_timer_.reset();
  parameter_frozen_ = false;
  return joint_trajectory_controller::JointTrajectoryController::on_cleanup(previous_state);
}

controller_interface::CallbackReturn HeadNeckTrajectoryController::on_error(
  const rclcpp_lifecycle::State & previous_state)
{
  active_.store(false, std::memory_order_release);
  stop_deadman();
  parameter_frozen_ = false;
  return joint_trajectory_controller::JointTrajectoryController::on_error(previous_state);
}

}  // namespace so101_mujoco_support

PLUGINLIB_EXPORT_CLASS(
  so101_mujoco_support::HeadNeckTrajectoryController, controller_interface::ControllerInterface)
