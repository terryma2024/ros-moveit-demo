#include "so101_mujoco_support/broker_owned_trajectory_controller.hpp"

#include <cstdlib>
#include <stdexcept>
#include <system_error>

#include <pluginlib/class_list_macros.hpp>
#include <rclcpp_action/create_server.hpp>

namespace so101_mujoco_support
{

controller_interface::return_type BrokerOwnedTrajectoryController::update(
  const rclcpp::Time & time, const rclcpp::Duration & period)
{
  const auto result = joint_trajectory_controller::JointTrajectoryController::update(time, period);
  if (result != controller_interface::return_type::OK) {
    witness_active_.store(false, std::memory_order_release);
    arm_stop_witness_.invalidate_nonblocking();
    gripper_stop_witness_.invalidate_nonblocking();
    return result;
  }
  if (!witness_active_.load(std::memory_order_acquire)) {return result;}
  const auto joints = monitored_joints_.load(std::memory_order_acquire);
  if (joints != 1 && joints != 5) {return result;}
  auto & witness = joints == 5 ? arm_stop_witness_ : gripper_stop_witness_;
  if (state_current_.positions.size() != joints ||
    state_current_.velocities.size() != joints ||
    state_desired_.positions.size() != joints ||
    state_desired_.velocities.size() != joints)
  {
    witness.invalidate_nonblocking();
    return result;
  }
  ControllerStopWitness::Observation sample{};
  sample.sequence = update_sequence_.fetch_add(1, std::memory_order_relaxed) + 1;
  sample.sim_time_ns = time.nanoseconds();
  sample.received_monotonic_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
  sample.joint_count = joints;
  sample.holding = rt_is_holding_.load();
  const auto active_goal = rt_active_goal_.readFromRT();
  sample.active_goal = rt_has_pending_goal_.load() || (active_goal && *active_goal);
  for (size_t joint = 0; joint < joints; ++joint) {
    sample.measured_positions[joint] = state_current_.positions[joint];
    sample.measured_velocities[joint] = state_current_.velocities[joint];
    sample.reference_positions[joint] = state_desired_.positions[joint];
    sample.reference_velocities[joint] = state_desired_.velocities[joint];
  }
  witness.observe(sample);
  return result;
}

std::optional<ControllerStopWitness::Proof> BrokerOwnedTrajectoryController::controller_stop_proof(
  int64_t now_monotonic_ns)
{
  if (!witness_active_.load(std::memory_order_acquire)) {return std::nullopt;}
  const auto joints = monitored_joints_.load(std::memory_order_acquire);
  ControllerStopWitness * witness = nullptr;
  if (joints == 5) {witness = &arm_stop_witness_;}
  if (joints == 1) {witness = &gripper_stop_witness_;}
  if (!witness) {return std::nullopt;}
  const auto goal_is_active = [this]() {
      const auto active_goal = rt_active_goal_.readFromRT();
      return rt_has_pending_goal_.load() || !rt_is_holding_.load() ||
             (active_goal && *active_goal);
    };
  if (goal_is_active()) {
    witness->invalidate_nonblocking();
    return std::nullopt;
  }
  const auto stopped = witness->proof(now_monotonic_ns);
  if (!witness_active_.load(std::memory_order_acquire) || goal_is_active()) {
    witness->invalidate_nonblocking();
    return std::nullopt;
  }
  return stopped;
}

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_configure(
  const rclcpp_lifecycle::State & previous_state)
{
  close_reservation_service();
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
        arm_stop_witness_.invalidate_nonblocking();
        gripper_stop_witness_.invalidate_nonblocking();
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
    configure_reservation_scope();
  } catch (const std::exception & error) {
    RCLCPP_ERROR(get_node()->get_logger(), "Action admission setup failed: %s", error.what());
    close_reservation_service();
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
  if (result == controller_interface::CallbackReturn::SUCCESS) {
    arm_stop_witness_.reset();
    gripper_stop_witness_.reset();
    witness_active_.store(true, std::memory_order_release);
    start_reservation_monitor();
  }
  return result;
}

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_deactivate(
  const rclcpp_lifecycle::State & previous_state)
{
  close_reservation_service();
  return joint_trajectory_controller::JointTrajectoryController::on_deactivate(previous_state);
}

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_cleanup(
  const rclcpp_lifecycle::State & previous_state)
{
  close_reservation_service();
  action_server_.reset();
  return joint_trajectory_controller::JointTrajectoryController::on_cleanup(previous_state);
}

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_error(
  const rclcpp_lifecycle::State & previous_state)
{
  close_reservation_service();
  action_server_.reset();
  return joint_trajectory_controller::JointTrajectoryController::on_error(previous_state);
}

void BrokerOwnedTrajectoryController::configure_reservation_scope()
{
  {
    std::lock_guard<std::mutex> lock(reservation_mutex_);
    reservation_provision_path_.clear();
    reservation_socket_path_.clear();
    reservation_session_.clear();
  }
  const auto name = std::string(get_node()->get_name());
  monitored_joints_.store(name == "arm_controller" ? 5 :
    name == "gripper_controller" ? 1 : 0, std::memory_order_release);
  if (name != "arm_controller" && name != "gripper_controller") {
    return;
  }
  const auto * directory_text = std::getenv("SO101_ACT_CONTROLLER_RESERVATION_DIR");
  const auto * session_text = std::getenv("SO101_SIMULATION_SESSION_ID");
  if (!directory_text && !session_text) {return;}
  if (!directory_text || !session_text || !*directory_text || !*session_text) {
    throw std::runtime_error("CONTROLLER_RESERVATION_SCOPE_INVALID");
  }
  const auto directory = std::filesystem::path(directory_text);
  if (!directory.is_absolute() || directory != directory.lexically_normal()) {
    throw std::runtime_error("CONTROLLER_RESERVATION_SCOPE_INVALID");
  }
  const auto role = name == "arm_controller" ? ControllerReservationRole::ARM :
    ControllerReservationRole::GRIPPER;
  const auto basename = name == "arm_controller" ? "arm" : "gripper";
  const auto socket_path = directory / (std::string(basename) + ".sock");
  if (socket_path.string().size() > 107) {
    throw std::runtime_error("CONTROLLER_RESERVATION_PATH_TOO_LONG");
  }
  {
    std::lock_guard<std::mutex> lock(reservation_mutex_);
    reservation_role_ = role;
    reservation_session_ = session_text;
    reservation_provision_path_ = directory / (std::string(basename) + ".provision");
    reservation_socket_path_ = socket_path;
  }
  start_reservation_monitor();
}

void BrokerOwnedTrajectoryController::start_reservation_monitor()
{
  std::lock_guard<std::mutex> lock(reservation_mutex_);
  if (reservation_provision_path_.empty() || reservation_service_ || reservation_timer_) {return;}
  reservation_deadline_ = std::chrono::steady_clock::now() + std::chrono::seconds(30);
  reservation_timer_ = get_node()->create_wall_timer(
    std::chrono::milliseconds(50), [this]() {poll_reservation_provision();});
}

void BrokerOwnedTrajectoryController::poll_reservation_provision()
{
  std::lock_guard<std::mutex> lock(reservation_mutex_);
  if (!reservation_timer_ || reservation_service_) {return;}
  if (std::chrono::steady_clock::now() >= reservation_deadline_) {
    goal_admission_.close();
    reservation_timer_->cancel();
    RCLCPP_ERROR(get_node()->get_logger(), "Controller reservation provision timed out");
    return;
  }
  std::error_code error;
  const auto current = std::filesystem::symlink_status(reservation_provision_path_, error);
  if (current.type() == std::filesystem::file_type::not_found ||
    error == std::errc::no_such_file_or_directory)
  {
    return;
  }
  try {
    if (error) {throw std::runtime_error("CONTROLLER_RESERVATION_PROVISION_UNREADABLE");}
    const auto provision = read_controller_reservation_provision(
      reservation_provision_path_, reservation_role_, reservation_session_);
    reservation_service_ = std::make_unique<ControllerReservationService>(
      reservation_socket_path_, goal_admission_, provision.capability, provision.peer,
      std::chrono::milliseconds(50), [this]() {
        const auto now = std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch()).count();
        return controller_stop_proof(now).has_value();
      });
    reservation_timer_->cancel();
  } catch (const std::exception & failure) {
    goal_admission_.close();
    reservation_timer_->cancel();
    RCLCPP_ERROR(get_node()->get_logger(), "Controller reservation service refused: %s",
      failure.what());
  }
}

void BrokerOwnedTrajectoryController::close_reservation_service()
{
  witness_active_.store(false, std::memory_order_release);
  arm_stop_witness_.reset();
  gripper_stop_witness_.reset();
  std::lock_guard<std::mutex> lock(reservation_mutex_);
  if (reservation_timer_) {
    reservation_timer_->cancel();
    reservation_timer_.reset();
  }
  reservation_service_.reset();
  goal_admission_.close();
}

}  // namespace so101_mujoco_support

PLUGINLIB_EXPORT_CLASS(
  so101_mujoco_support::BrokerOwnedTrajectoryController,
  controller_interface::ControllerInterface)
