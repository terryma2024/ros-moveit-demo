#include "so101_mujoco_support/broker_owned_trajectory_controller.hpp"

#include <cstdlib>
#include <array>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <system_error>

#include <pluginlib/class_list_macros.hpp>
#include <rcl_interfaces/msg/parameter_descriptor.hpp>
#include <rclcpp_action/create_server.hpp>

namespace so101_mujoco_support
{
namespace
{
constexpr double kHeadGeometryLimit = 6.283175307179587;
constexpr double kHeadVelocityLimit = 0.5;
constexpr double kHeadAccelerationLimit = 0.5;
constexpr double kHeadMeasuredVelocityLimit = 0.04136050464213824;
constexpr double kHeadMeasuredPositionMismatchLimit = 0.002;
constexpr int64_t kNanosecondsPerSecond = 1000000000LL;

bool duration_ns(const builtin_interfaces::msg::Duration & duration, int64_t & value)
{
  if (duration.sec < 0 || duration.nanosec >= static_cast<uint32_t>(kNanosecondsPerSecond)) {
    return false;
  }
  const auto seconds = static_cast<int64_t>(duration.sec);
  if (seconds > (std::numeric_limits<int64_t>::max() - duration.nanosec) /
    kNanosecondsPerSecond)
  {
    return false;
  }
  value = seconds * kNanosecondsPerSecond + duration.nanosec;
  return true;
}

bool stamp_ns(const builtin_interfaces::msg::Time & stamp, int64_t & value)
{
  if (stamp.sec < 0 || stamp.nanosec >= static_cast<uint32_t>(kNanosecondsPerSecond)) {
    return false;
  }
  const auto seconds = static_cast<int64_t>(stamp.sec);
  if (seconds > (std::numeric_limits<int64_t>::max() - stamp.nanosec) /
    kNanosecondsPerSecond)
  {
    return false;
  }
  value = seconds * kNanosecondsPerSecond + stamp.nanosec;
  return true;
}

template<size_t N>
bool split_bernstein(const std::array<double, N> & input,
  std::array<double, N> & left, std::array<double, N> & right)
{
  std::array<double, N> work = input;
  left[0] = work[0];
  right[N - 1] = work[N - 1];
  for (size_t level = 1; level < N; ++level) {
    for (size_t i = 0; i < N - level; ++i) {
      work[i] = (work[i] + work[i + 1]) * 0.5;
      if (!std::isfinite(work[i])) {return false;}
    }
    left[level] = work[0];
    right[N - level - 1] = work[N - level - 1];
  }
  return true;
}

template<size_t N>
bool subdivide_bernstein(
  const std::array<double, N> & original,
  std::array<std::array<double, N>, 64> & leaves)
{
  leaves[0] = original;
  size_t count = 1;
  for (size_t depth = 0; depth < 6; ++depth) {
    for (size_t leaf = count; leaf-- > 0;) {
      std::array<double, N> left{};
      std::array<double, N> right{};
      if (!split_bernstein(leaves[leaf], left, right)) {return false;}
      leaves[leaf * 2] = left;
      leaves[leaf * 2 + 1] = right;
    }
    count *= 2;
  }
  return count == leaves.size();
}
}  // namespace

controller_interface::return_type BrokerOwnedTrajectoryController::update(
  const rclcpp::Time & time, const rclcpp::Duration & period)
{
  if (head_simulation_mode_) {
    read_state_from_state_interfaces(state_current_);
    const auto candidate_slot = head_candidate_buffer_.readFromRT();
    const auto candidate = candidate_slot ? *candidate_slot : std::shared_ptr<HeadCandidate>{};
    if (state_current_.positions.size() != 1 || state_current_.velocities.size() != 1 ||
      !state_current_.accelerations.empty() || !std::isfinite(state_current_.positions[0]) ||
      !std::isfinite(state_current_.velocities[0]) ||
      std::abs(state_current_.positions[0]) > kHeadGeometryLimit)
    {
      head_motion_faulted_.store(true, std::memory_order_release);
      fail_head_candidate_without_hold(candidate);
      return controller_interface::return_type::ERROR;
    }
    if (head_motion_faulted_.load(std::memory_order_acquire)) {
      if (!hold_head_at_current_position()) {
        fail_head_candidate_without_hold(candidate);
        return controller_interface::return_type::ERROR;
      }
      fail_head_candidate_without_hold(candidate);
      head_motion_faulted_.store(false, std::memory_order_release);
    }
    if (scaling_factor_.load(std::memory_order_acquire) != 1.0 ||
      scaling_factor_cmd_.load(std::memory_order_acquire) != 1.0)
    {
      fail_head_candidate_without_hold(candidate);
      return controller_interface::return_type::ERROR;
    }
    const bool revoked = revocation_latch_ &&
      revocation_latch_->load(std::memory_order_acquire);
    if (candidate) {
      if (revoked) {
        if (!hold_head_at_current_position()) {
          fail_head_candidate_without_hold(candidate);
          return controller_interface::return_type::ERROR;
        }
        candidate->consumed.store(true, std::memory_order_release);
        rt_has_pending_goal_.store(false, std::memory_order_release);
        rt_active_goal_.initRT(RealtimeGoalHandlePtr{});
        head_active_goal_.store(false, std::memory_order_release);
        candidate->terminal.store(HeadTerminalRequest::ABORT, std::memory_order_release);
      } else if (candidate->terminal.load(std::memory_order_acquire) ==
        HeadTerminalRequest::ABORT)
      {
        if (!hold_head_at_current_position()) {
          fail_head_candidate_without_hold(candidate);
          return controller_interface::return_type::ERROR;
        }
        rt_has_pending_goal_.store(false, std::memory_order_release);
        rt_active_goal_.initRT(RealtimeGoalHandlePtr{});
        head_active_goal_.store(false, std::memory_order_release);
      } else if (candidate->cancel_requested.load(std::memory_order_acquire)) {
        if (!hold_head_at_current_position()) {
          fail_head_candidate_without_hold(candidate);
          return controller_interface::return_type::ERROR;
        }
        candidate->consumed.store(true, std::memory_order_release);
        rt_has_pending_goal_.store(false, std::memory_order_release);
        rt_active_goal_.initRT(RealtimeGoalHandlePtr{});
        head_active_goal_.store(false, std::memory_order_release);
        candidate->terminal.store(HeadTerminalRequest::CANCEL, std::memory_order_release);
      } else if (!candidate->consumed.load(std::memory_order_acquire) &&
        validate_head_prefix(*candidate->trajectory, state_current_, time.nanoseconds()))
      {
        new_trajectory_msg_.initRT(candidate->trajectory);
        active_tolerances_.initRT(candidate->tolerances);
        rt_active_goal_.initRT(candidate->goal);
        rt_has_pending_goal_.store(false, std::memory_order_release);
        rt_is_holding_.store(false, std::memory_order_release);
        head_active_goal_.store(true, std::memory_order_release);
        candidate->consumed.store(true, std::memory_order_release);
      } else if (!candidate->consumed.load(std::memory_order_acquire)) {
        if (!hold_head_at_current_position()) {
          fail_head_candidate_without_hold(candidate);
          return controller_interface::return_type::ERROR;
        }
        candidate->consumed.store(true, std::memory_order_release);
        rt_has_pending_goal_.store(false, std::memory_order_release);
        rt_active_goal_.initRT(RealtimeGoalHandlePtr{});
        head_active_goal_.store(false, std::memory_order_release);
        candidate->terminal.store(HeadTerminalRequest::ABORT, std::memory_order_release);
      }
      if (!candidate->goal && candidate->terminal.load(std::memory_order_acquire) !=
        HeadTerminalRequest::NONE)
      {
        head_goal_reserved_.store(false, std::memory_order_release);
      }
    } else if (revoked) {
      if (!hold_head_at_current_position()) {
        fail_head_candidate_without_hold({});
        return controller_interface::return_type::ERROR;
      }
      rt_has_pending_goal_.store(false, std::memory_order_release);
      rt_active_goal_.initRT(RealtimeGoalHandlePtr{});
      head_active_goal_.store(false, std::memory_order_release);
    }
  }
  const auto result = joint_trajectory_controller::JointTrajectoryController::update(time, period);
  if (result != controller_interface::return_type::OK) {
    witness_active_.store(false, std::memory_order_release);
    arm_stop_witness_.invalidate_nonblocking();
    gripper_stop_witness_.invalidate_nonblocking();
    neck_stop_witness_.invalidate_nonblocking();
    return result;
  }
  if (!witness_active_.load(std::memory_order_acquire)) {return result;}
  const auto joints = monitored_joints_.load(std::memory_order_acquire);
  if (joints != 1 && joints != 5) {return result;}
  auto & witness = joints == 5 ? arm_stop_witness_ :
    reservation_role_ == ControllerReservationRole::NECK ? neck_stop_witness_ :
    gripper_stop_witness_;
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
  if (head_simulation_mode_) {
    sample.active_goal = head_goal_reserved_.load(std::memory_order_acquire) ||
      head_active_goal_.load(std::memory_order_acquire);
  } else {
    const auto active_goal = rt_active_goal_.readFromRT();
    sample.active_goal = rt_has_pending_goal_.load() || (active_goal && *active_goal);
  }
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
  if (joints == 1) {
    witness = reservation_role_ == ControllerReservationRole::NECK ?
      &neck_stop_witness_ : &gripper_stop_witness_;
  }
  if (!witness) {return std::nullopt;}
  const auto goal_is_active = [this]() {
      if (head_simulation_mode_) {
        return head_goal_reserved_.load(std::memory_order_acquire) ||
               head_active_goal_.load(std::memory_order_acquire) ||
               !rt_is_holding_.load(std::memory_order_acquire);
      }
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

std::optional<ControllerIngressWitness::Snapshot>
BrokerOwnedTrajectoryController::controller_ingress_snapshot()
{
  return ingress_witness_.snapshot();
}

bool BrokerOwnedTrajectoryController::validate_head_goal_shape(
  const trajectory_msgs::msg::JointTrajectory & trajectory) const
{
  if (!head_simulation_mode_ || params_.joints.size() != 1 ||
    params_.joints.front() != "neck_yaw_joint" || trajectory.joint_names.size() != 1 ||
    trajectory.joint_names.front() != "neck_yaw_joint" || trajectory.points.size() != 2)
  {
    return false;
  }
  int64_t header_ns = 0;
  if (!stamp_ns(trajectory.header.stamp, header_ns) || header_ns == 0) {return false;}
  std::array<int64_t, 2> times{};
  std::array<double, 2> positions{};
  for (size_t i = 0; i < trajectory.points.size(); ++i) {
    const auto & point = trajectory.points[i];
    if (!duration_ns(point.time_from_start, times[i]) || point.positions.size() != 1 ||
      point.velocities.size() != 1 || point.accelerations.size() != 1 || !point.effort.empty() ||
      !std::isfinite(point.positions[0]) || !std::isfinite(point.velocities[0]) ||
      !std::isfinite(point.accelerations[0]) || std::abs(point.positions[0]) > kHeadGeometryLimit)
    {
      return false;
    }
    positions[i] = point.positions[0];
  }
  if (times[0] <= 0 || times[1] <= times[0] || times[1] < 100000000LL ||
    times[1] > 5000000000LL || trajectory.points[0].velocities[0] != 0.0 ||
    trajectory.points[0].accelerations[0] != 0.0 || trajectory.points[1].velocities[0] != 0.0 ||
    trajectory.points[1].accelerations[0] != 0.0)
  {
    return false;
  }
  const double duration = static_cast<double>(times[1] - times[0]) / kNanosecondsPerSecond;
  if (!std::isfinite(duration) || duration < 0.1 || duration > 5.0) {return false;}
  const double displacement = std::abs(positions[1] - positions[0]);
  const double peak_velocity = 1.875 * displacement / duration;
  const double peak_acceleration = 5.773502691896258 * displacement / (duration * duration);
  return std::isfinite(peak_velocity) && std::isfinite(peak_acceleration) &&
         peak_velocity <= kHeadVelocityLimit && peak_acceleration <= kHeadAccelerationLimit;
}

bool BrokerOwnedTrajectoryController::validate_head_prefix(
  const trajectory_msgs::msg::JointTrajectory & trajectory,
  const trajectory_msgs::msg::JointTrajectoryPoint & measured, int64_t update_time_ns) const
{
  if (!validate_head_goal_shape(trajectory) || update_time_ns < 0 ||
    measured.positions.size() != 1 || measured.velocities.size() != 1 ||
    !measured.accelerations.empty() || !std::isfinite(measured.positions[0]) ||
    !std::isfinite(measured.velocities[0]) ||
    std::abs(measured.positions[0]) > kHeadGeometryLimit ||
    std::abs(measured.velocities[0]) > kHeadMeasuredVelocityLimit)
  {
    return false;
  }
  int64_t header_ns = 0;
  int64_t first_ns = 0;
  if (!stamp_ns(trajectory.header.stamp, header_ns) ||
    !duration_ns(trajectory.points[0].time_from_start, first_ns) ||
    header_ns > std::numeric_limits<int64_t>::max() - first_ns)
  {
    return false;
  }
  const int64_t first_absolute_ns = header_ns + first_ns;
  if (first_absolute_ns <= update_time_ns) {return false;}
  const int64_t remaining_ns = first_absolute_ns - update_time_ns;
  if (remaining_ns > first_ns + 14000000LL) {return false;}
  const double remaining = static_cast<double>(remaining_ns) / kNanosecondsPerSecond;
  const double first_offset = static_cast<double>(first_ns) / kNanosecondsPerSecond;
  const double first_position = trajectory.points[0].positions[0];
  const double measured_position = measured.positions[0];
  const double measured_velocity = measured.velocities[0];
  if (!std::isfinite(remaining) || !std::isfinite(first_offset) ||
    std::abs(measured_position - first_position) > kHeadMeasuredPositionMismatchLimit)
  {
    return false;
  }
  const double envelope_radius = kHeadMeasuredPositionMismatchLimit +
    0.4 * kHeadMeasuredVelocityLimit * (first_offset + 0.014);
  if (!std::isfinite(envelope_radius)) {return false;}

  std::array<double, 6> position{};
  position[0] = measured_position;
  position[1] = measured_position + measured_velocity * remaining / 5.0;
  position[2] = measured_position + 2.0 * measured_velocity * remaining / 5.0;
  position[3] = first_position;
  position[4] = first_position;
  position[5] = first_position;
  std::array<double, 5> velocity{};
  std::array<double, 4> acceleration{};
  for (size_t i = 0; i < velocity.size(); ++i) {
    velocity[i] = 5.0 * (position[i + 1] - position[i]) / remaining;
  }
  const double acceleration_scale = 20.0 / (remaining * remaining);
  for (size_t i = 0; i < acceleration.size(); ++i) {
    acceleration[i] = acceleration_scale *
      (position[i + 2] - 2.0 * position[i + 1] + position[i]);
  }
  for (const auto value : position) {if (!std::isfinite(value)) {return false;}}
  for (const auto value : velocity) {if (!std::isfinite(value)) {return false;}}
  for (const auto value : acceleration) {if (!std::isfinite(value)) {return false;}}

  std::array<std::array<double, 6>, 64> position_leaves{};
  std::array<std::array<double, 5>, 64> velocity_leaves{};
  std::array<std::array<double, 4>, 64> acceleration_leaves{};
  if (!subdivide_bernstein(position, position_leaves) ||
    !subdivide_bernstein(velocity, velocity_leaves) ||
    !subdivide_bernstein(acceleration, acceleration_leaves))
  {
    return false;
  }
  const double envelope_lower = first_position - envelope_radius;
  const double envelope_upper = first_position + envelope_radius;
  if (!std::isfinite(envelope_lower) || !std::isfinite(envelope_upper)) {return false;}
  for (size_t leaf = 0; leaf < position_leaves.size(); ++leaf) {
    for (const auto value : position_leaves[leaf]) {
      if (value < -kHeadGeometryLimit || value > kHeadGeometryLimit ||
        value < envelope_lower || value > envelope_upper)
      {
        return false;
      }
    }
    for (const auto value : velocity_leaves[leaf]) {
      if (std::abs(value) > kHeadVelocityLimit) {return false;}
    }
    for (const auto value : acceleration_leaves[leaf]) {
      if (std::abs(value) > kHeadAccelerationLimit) {return false;}
    }
  }
  return true;
}

bool BrokerOwnedTrajectoryController::hold_head_at_current_position() noexcept
{
  if (!head_hold_position_msg_ || state_current_.positions.size() != 1 ||
    !std::isfinite(state_current_.positions[0]) ||
    std::abs(state_current_.positions[0]) > kHeadGeometryLimit)
  {
    return false;
  }
  head_hold_position_msg_->points[0].positions[0] = state_current_.positions[0];
  rt_is_holding_.store(true, std::memory_order_release);
  new_trajectory_msg_.initRT(head_hold_position_msg_);
  return true;
}

void BrokerOwnedTrajectoryController::fail_head_candidate_without_hold(
  const std::shared_ptr<HeadCandidate> & candidate) noexcept
{
  if (candidate) {
    candidate->consumed.store(true, std::memory_order_release);
  }
  rt_has_pending_goal_.store(false, std::memory_order_release);
  rt_active_goal_.initRT(RealtimeGoalHandlePtr{});
  head_active_goal_.store(false, std::memory_order_release);
  if (candidate) {
    candidate->terminal.store(HeadTerminalRequest::ABORT, std::memory_order_release);
    if (!candidate->goal) {head_goal_reserved_.store(false, std::memory_order_release);}
  }
  witness_active_.store(false, std::memory_order_release);
  arm_stop_witness_.invalidate_nonblocking();
  gripper_stop_witness_.invalidate_nonblocking();
  neck_stop_witness_.invalidate_nonblocking();
}

void BrokerOwnedTrajectoryController::stage_head_trajectory_for_testing(
  std::shared_ptr<trajectory_msgs::msg::JointTrajectory> trajectory)
{
  auto candidate = std::make_shared<HeadCandidate>();
  candidate->trajectory = std::move(trajectory);
  candidate->tolerances = default_tolerances_;
  candidate->result = std::make_shared<FollowJTrajAction::Result>();
  head_goal_reserved_.store(true, std::memory_order_release);
  rt_has_pending_goal_.store(true, std::memory_order_release);
  head_candidate_buffer_.writeFromNonRT(candidate);
}

void BrokerOwnedTrajectoryController::accept_head_goal(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowJTrajAction>> & goal_handle)
{
  if (!goal_handle || !goal_handle->get_goal()) {return;}
  auto candidate = std::make_shared<HeadCandidate>();
  candidate->trajectory = std::make_shared<trajectory_msgs::msg::JointTrajectory>(
    goal_handle->get_goal()->trajectory);
  auto realtime_goal_handle = goal_handle;
  candidate->result = std::make_shared<FollowJTrajAction::Result>();
  auto feedback = std::make_shared<FollowJTrajAction::Feedback>();
  candidate->goal = std::make_shared<RealtimeGoalHandle>(
    realtime_goal_handle, candidate->result, feedback);
  candidate->goal->preallocated_feedback_->joint_names = params_.joints;
  candidate->goal->execute();
  auto logger = get_node()->get_logger();
  candidate->tolerances = joint_trajectory_controller::get_segment_tolerances(
    logger, default_tolerances_, *(goal_handle->get_goal()), params_.joints);
  candidate->result->error_code = FollowJTrajAction::Result::INVALID_GOAL;
  candidate->result->error_string = "Head measured-prefix guard refused the first command";
  {
    std::lock_guard<std::mutex> lock(head_goal_mutex_);
    if (head_owned_candidate_) {
      auto rejected = std::make_shared<FollowJTrajAction::Result>();
      rejected->error_code = FollowJTrajAction::Result::INVALID_GOAL;
      rejected->error_string = "Head controller already owns an accepted goal";
      goal_handle->abort(rejected);
      head_goal_reserved_.store(true, std::memory_order_release);
      return;
    }
    head_owned_candidate_ = candidate;
  }
  rt_has_pending_goal_.store(true, std::memory_order_release);
  const std::weak_ptr<HeadCandidate> weak_candidate(candidate);
  candidate->status_timer = get_node()->create_wall_timer(
    action_monitor_period_.to_chrono<std::chrono::nanoseconds>(),
    [this, weak_candidate]() {
      if (const auto locked = weak_candidate.lock()) {monitor_head_goal(locked);}
    });
  // Publish only after trajectory, tolerances, action handle, and terminal storage are ready.
  head_candidate_buffer_.writeFromNonRT(candidate);
}

rclcpp_action::CancelResponse BrokerOwnedTrajectoryController::cancel_head_goal(
  const std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowJTrajAction>> & goal_handle)
{
  std::lock_guard<std::mutex> lock(head_goal_mutex_);
  if (!goal_handle || !head_owned_candidate_ || !head_owned_candidate_->goal ||
    head_owned_candidate_->goal->gh_ != goal_handle ||
    head_owned_candidate_->retired.load(std::memory_order_acquire))
  {
    return rclcpp_action::CancelResponse::REJECT;
  }
  head_owned_candidate_->cancel_requested.store(true, std::memory_order_release);
  return rclcpp_action::CancelResponse::ACCEPT;
}

void BrokerOwnedTrajectoryController::monitor_head_goal(
  const std::shared_ptr<HeadCandidate> & candidate)
{
  if (!candidate || !candidate->goal) {return;}
  bool terminal = false;
  {
    std::lock_guard<std::mutex> lock(candidate->status_mutex);
    if (candidate->retired.load(std::memory_order_acquire)) {return;}
    const auto request = candidate->terminal.exchange(
      HeadTerminalRequest::NONE, std::memory_order_acq_rel);
    if (request == HeadTerminalRequest::ABORT) {
      // The realtime wrapper only publishes aborts from EXECUTING. Native
      // close can overlap an accepted cancel, which has already moved the
      // same handle to CANCELING. Finish that abort here, outside the RT loop.
      if (candidate->goal->gh_->is_canceling()) {
        candidate->goal->gh_->abort(candidate->result);
      } else {
        candidate->goal->setAborted(candidate->result);
      }
    } else if (request == HeadTerminalRequest::CANCEL) {
      auto canceled = std::make_shared<FollowJTrajAction::Result>();
      candidate->goal->setCanceled(canceled);
    }
    candidate->goal->runNonRealtime();
    terminal = !candidate->goal->gh_->is_active();
    if (terminal) {candidate->retired.store(true, std::memory_order_release);}
  }
  if (!terminal) {return;}
  std::lock_guard<std::mutex> lock(head_goal_mutex_);
  if (head_owned_candidate_ == candidate) {
    head_owned_candidate_.reset();
    candidate->status_timer.reset();
    head_candidate_buffer_.writeFromNonRT(std::shared_ptr<HeadCandidate>{});
    head_goal_reserved_.store(false, std::memory_order_release);
    head_active_goal_.store(false, std::memory_order_release);
  }
}

void BrokerOwnedTrajectoryController::retire_head_goal_for_lifecycle()
{
  std::shared_ptr<HeadCandidate> candidate;
  {
    std::lock_guard<std::mutex> lock(head_goal_mutex_);
    candidate = std::move(head_owned_candidate_);
    if (candidate && candidate->status_timer) {candidate->status_timer->cancel();}
    head_candidate_buffer_.writeFromNonRT(std::shared_ptr<HeadCandidate>{});
    head_goal_reserved_.store(false, std::memory_order_release);
    head_active_goal_.store(false, std::memory_order_release);
  }
  if (candidate && candidate->goal) {
    std::lock_guard<std::mutex> lock(candidate->status_mutex);
    if (!candidate->retired.exchange(true, std::memory_order_acq_rel)) {
      auto aborted = std::make_shared<FollowJTrajAction::Result>();
      aborted->error_code = FollowJTrajAction::Result::INVALID_GOAL;
      aborted->error_string = "Head goal retired during lifecycle transition";
      if (candidate->goal->gh_->is_canceling()) {
        candidate->goal->gh_->abort(aborted);
      } else {
        candidate->goal->setAborted(aborted);
      }
      candidate->goal->runNonRealtime();
    }
    candidate->status_timer.reset();
  }
}

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_configure(
  const rclcpp_lifecycle::State & previous_state)
{
  close_reservation_service();
  try {
    configure_head_parameters();
  } catch (const std::exception & failure) {
    RCLCPP_ERROR(get_node()->get_logger(), "Head parameter binding refused: %s", failure.what());
    return controller_interface::CallbackReturn::ERROR;
  }
  const auto result = joint_trajectory_controller::JointTrajectoryController::on_configure(
    previous_state);
  if (result != controller_interface::CallbackReturn::SUCCESS) {
    return result;
  }
  if (head_simulation_mode_) {
    const auto node = get_node();
    constexpr char kSpeedScalingInputEnabled[] = "speed_scaling_input_enabled";
    if (!node->has_parameter(kSpeedScalingInputEnabled)) {
      RCLCPP_ERROR(get_node()->get_logger(), "Head requires the JTC speed scaling switch.");
      return controller_interface::CallbackReturn::ERROR;
    }
    const auto parameter = node->get_parameter(kSpeedScalingInputEnabled);
    if (parameter.get_type() != rclcpp::ParameterType::PARAMETER_BOOL ||
      parameter.as_bool() || !node->describe_parameter(kSpeedScalingInputEnabled).read_only)
    {
      RCLCPP_ERROR(get_node()->get_logger(), "Head requires speed scaling disabled and read-only.");
      return controller_interface::CallbackReturn::ERROR;
    }
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
        return decide_goal_admission(uuid, goal);   // real callback decision
      },
      [this](
        std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowJTrajAction>> goal_handle)
      {
        auto ingress = ingress_witness_.enter();
        return head_simulation_mode_ ? cancel_head_goal(goal_handle) :
               joint_trajectory_controller::JointTrajectoryController::goal_cancelled_callback(
          goal_handle);
      },
      [this](
        std::shared_ptr<rclcpp_action::ServerGoalHandle<FollowJTrajAction>> goal_handle)
      {
        auto ingress = ingress_witness_.enter();
        (void)ingress;
        if (head_simulation_mode_) {accept_head_goal(goal_handle);} else {
          joint_trajectory_controller::JointTrajectoryController::goal_accepted_callback(
            goal_handle);
        }
      });
    configure_reservation_scope();
    if (head_simulation_mode_) {
      // Head checks complete unwrapped quintics before executing them. The
      // continuous physical neck must retain those coordinates in the JTC
      // measured prefix and error calculation; angular lifting changes them.
      if (params_.joints == std::vector<std::string>{"neck_yaw_joint"} &&
        joints_angle_wraparound_.size() == 1)
      {
        joints_angle_wraparound_[0] = false;
      }
      if (get_update_rate() != 500 || !head_measured_prefix_guard_enabled_ ||
        params_.joints != std::vector<std::string>{"neck_yaw_joint"} ||
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
        throw std::runtime_error("CONTROLLER_HEAD_JTC_CONFIGURATION_UNSUPPORTED");
      }
      head_hold_position_msg_ = std::make_shared<trajectory_msgs::msg::JointTrajectory>();
      head_hold_position_msg_->joint_names = params_.joints;
      head_hold_position_msg_->points.resize(1);
      head_hold_position_msg_->points[0].positions.resize(1);
      head_hold_position_msg_->points[0].velocities.clear();
      head_hold_position_msg_->points[0].accelerations.clear();
      head_hold_position_msg_->points[0].effort.clear();
      scaling_factor_.store(1.0, std::memory_order_release);
      scaling_factor_cmd_.store(1.0, std::memory_order_release);
      query_state_srv_.reset();
      head_parameter_callback_ = get_node()->add_on_set_parameters_callback(
        [this](const std::vector<rclcpp::Parameter> & parameters) {
          rcl_interfaces::msg::SetParametersResult response;
          response.successful = true;
          for (const auto & parameter : parameters) {
            const auto & name = parameter.get_name();
            if (name == "open_loop_control" || name == "interpolate_from_desired_state" ||
              name == "interpolation_method" || name == "allow_partial_joints_goal" ||
              name == "allow_integration_in_goal_trajectories" ||
              name.rfind("speed_scaling.", 0) == 0)
            {
              response.successful = false;
              response.reason = "CONTROLLER_HEAD_JTC_CONFIGURATION_IMMUTABLE";
              break;
            }
          }
          return response;
        });
    }
  } catch (const std::exception & failure) {
    RCLCPP_ERROR(get_node()->get_logger(), "Admission-wrapped action server refused: %s",
      failure.what());
    action_server_.reset();
    return controller_interface::CallbackReturn::ERROR;
  }
  return controller_interface::CallbackReturn::SUCCESS;
}

rclcpp_action::GoalResponse BrokerOwnedTrajectoryController::decide_goal_admission(
  const rclcpp_action::GoalUUID & uuid,
  const std::shared_ptr<const control_msgs::action::FollowJointTrajectory::Goal> & goal)
{
  auto ingress = ingress_witness_.enter();
  arm_stop_witness_.invalidate_nonblocking();
  gripper_stop_witness_.invalidate_nonblocking();
  neck_stop_witness_.invalidate_nonblocking();
  (void)ingress;
  if (head_simulation_mode_) {
    bool expected = false;
    if (!head_goal_reserved_.compare_exchange_strong(expected, true,
        std::memory_order_acq_rel, std::memory_order_acquire))
    {
      return rclcpp_action::GoalResponse::REJECT;
    }
    if (!goal || !validate_head_goal_shape(goal->trajectory)) {
      head_goal_reserved_.store(false, std::memory_order_release);
      return rclcpp_action::GoalResponse::REJECT;
    }
  }
  const auto gate = active_gate_copy();      // brief copy; the mutex is released here
  if (!goal || !gate) {
    if (head_simulation_mode_) {head_goal_reserved_.store(false, std::memory_order_release);}
    // no active gate (before provision or after detach) fails closed
    return rclcpp_action::GoalResponse::REJECT;
  }
  if (gate->has_service_identity()) {
    // bound mode: consume the exact bound reservation once, no legacy fallback
    if (gate->admit_bound_action(uuid, *goal, gate->generation()) !=
      BoundReserveStatus::ACCEPTED)
    {
      if (head_simulation_mode_) {head_goal_reserved_.store(false, std::memory_order_release);}
      return rclcpp_action::GoalResponse::REJECT;
    }
  } else if (gate->admit_current(uuid, *goal) !=
    ControllerGoalAdmission::Result::ALLOW)
  {
    if (head_simulation_mode_) {head_goal_reserved_.store(false, std::memory_order_release);}
    return rclcpp_action::GoalResponse::REJECT;   // legacy-only test gates
  }
  const auto response = joint_trajectory_controller::JointTrajectoryController::
    goal_received_callback(uuid, goal);
  if (head_simulation_mode_ && response != rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE) {
    head_goal_reserved_.store(false, std::memory_order_release);
  }
  return response;
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
    neck_stop_witness_.reset();
    witness_active_.store(true, std::memory_order_release);
    start_reservation_monitor();
  }
  return result;
}

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_deactivate(
  const rclcpp_lifecycle::State & previous_state)
{
  close_reservation_service();
  if (head_simulation_mode_) {retire_head_goal_for_lifecycle();}
  return joint_trajectory_controller::JointTrajectoryController::on_deactivate(previous_state);
}

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_cleanup(
  const rclcpp_lifecycle::State & previous_state)
{
  close_reservation_service();
  if (head_simulation_mode_) {retire_head_goal_for_lifecycle();}
  head_parameter_callback_.reset();
  action_server_.reset();
  return joint_trajectory_controller::JointTrajectoryController::on_cleanup(previous_state);
}

controller_interface::CallbackReturn BrokerOwnedTrajectoryController::on_error(
  const rclcpp_lifecycle::State & previous_state)
{
  close_reservation_service();
  if (head_simulation_mode_) {retire_head_goal_for_lifecycle();}
  head_parameter_callback_.reset();
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
    primary_fault_provision_path_.clear();
    primary_fault_socket_path_.clear();
  }
  const auto name = std::string(get_node()->get_name());
  monitored_joints_.store(name == "arm_controller" ? 5 :
    name == "gripper_controller" || name == "neck_controller" ? 1 : 0,
    std::memory_order_release);
  if (name != "arm_controller" && name != "gripper_controller" &&
    name != "neck_controller")
  {
    return;
  }
  const auto role = name == "arm_controller" ? ControllerReservationRole::ARM :
    name == "gripper_controller" ? ControllerReservationRole::GRIPPER :
    ControllerReservationRole::NECK;
  reservation_role_ = role;
  const auto * directory_text = std::getenv("SO101_ACT_CONTROLLER_RESERVATION_DIR");
  const auto * session_text = std::getenv("SO101_SIMULATION_SESSION_ID");
  if (!directory_text && !session_text &&
    !(role == ControllerReservationRole::NECK && head_simulation_mode_))
  {
    return;
  }
  if (!directory_text || !session_text || !*directory_text || !*session_text) {
    throw std::runtime_error("CONTROLLER_RESERVATION_SCOPE_INVALID");
  }
  const auto directory = std::filesystem::path(directory_text);
  if (!directory.is_absolute() || directory != directory.lexically_normal()) {
    throw std::runtime_error("CONTROLLER_RESERVATION_SCOPE_INVALID");
  }
  const auto basename = name == "arm_controller" ? "arm" :
    name == "gripper_controller" ? "gripper" : "neck";
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
    if (role == ControllerReservationRole::NECK && head_simulation_mode_) {
      primary_fault_socket_path_ = directory / "neck-primary-revoke.sock";
      primary_fault_provision_path_ = directory / "neck-primary-revoke.provision";
      if (primary_fault_socket_path_.string().size() > 107) {
        throw std::runtime_error("CONTROLLER_REVOKER_PATH_TOO_LONG");
      }
    }
  }
  start_reservation_monitor();
}

void BrokerOwnedTrajectoryController::configure_head_parameters()
{
  if (std::string(get_node()->get_name()) != "neck_controller") {return;}
  // Bind mode and safety inputs before invoking JTC configure or exposing services.
  rcl_interfaces::msg::ParameterDescriptor descriptor;
  descriptor.read_only = true;
  const auto node = get_node();
  if (!node->has_parameter("head_simulation_mode")) {
    node->declare_parameter("head_simulation_mode", std::string{}, descriptor);
  }
  if (!node->has_parameter("head_fault_connection_timeout_ns")) {
    node->declare_parameter("head_fault_connection_timeout_ns", int64_t(2000000), descriptor);
  }
  if (!node->has_parameter("head_measured_prefix_guard")) {
    node->declare_parameter("head_measured_prefix_guard", std::string{}, descriptor);
  }
  const auto mode = node->get_parameter("head_simulation_mode").as_string();
  const auto timeout = node->get_parameter("head_fault_connection_timeout_ns").as_int();
  const auto prefix_guard = node->get_parameter("head_measured_prefix_guard").as_string();
  if (!node->describe_parameter("head_simulation_mode").read_only ||
    !node->describe_parameter("head_fault_connection_timeout_ns").read_only ||
    !node->describe_parameter("head_measured_prefix_guard").read_only ||
    (mode.empty() ? timeout != 2000000 :
    mode != "mujoco_bounded_stop_search_file_v1" || timeout != 50000000 ||
    prefix_guard != "quintic_measured_prefix_v1") || (mode.empty() && !prefix_guard.empty()))
  {
    throw std::runtime_error("CONTROLLER_HEAD_SIMULATION_POLICY_INVALID");
  }
  head_simulation_mode_ = !mode.empty();
  head_measured_prefix_guard_enabled_ = !prefix_guard.empty();
  head_fault_connection_timeout_ = std::chrono::nanoseconds(timeout);
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
    if (active_goal_admission_) {active_goal_admission_->close();}
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
    // one service incarnation: identity from OS entropy, gate created with it
    const auto identity = generate_service_identity(reservation_role_, provision.capability);
    auto gate = make_scoped_goal_admission(identity);
    std::optional<ControllerReservationProvision> primary_fault;
    if (head_simulation_mode_) {
      const auto current_primary = std::filesystem::symlink_status(primary_fault_provision_path_,
          error);
      if (current_primary.type() == std::filesystem::file_type::not_found ||
        error == std::errc::no_such_file_or_directory)
      {
        return;
      }
      if (error) {throw std::runtime_error("CONTROLLER_PRIMARY_FAULT_PROVISION_UNREADABLE");}
      primary_fault = read_controller_primary_fault_provision(
        primary_fault_provision_path_, reservation_session_, primary_fault_socket_path_);
      if (primary_fault->peer.uid != provision.peer.uid ||
        primary_fault->peer.pid != provision.peer.pid ||
        primary_fault->peer.start_ticks != provision.peer.start_ticks ||
        primary_fault->capability == provision.capability)
      {
        throw std::runtime_error("CONTROLLER_PRIMARY_FAULT_EXACT_PRIMARY_REQUIRED");
      }
    }
    // Bind the local Head close-only authority before exposing main admission.
    // Both services share the same gate; the main service remains the only
    // reserve/ARM authority.
    std::unique_ptr<ControllerReservationService> primary_fault_service;
    if (primary_fault) {
      primary_fault_service = std::make_unique<ControllerReservationService>(
        primary_fault_socket_path_, gate, primary_fault->capability, primary_fault->peer,
        head_fault_connection_timeout_, ControllerReservationSocket::StopProof{}, reservation_role_,
        ControllerReservationSocket::IngressSnapshot{},
        ControllerReservationSocket::Authority::PRIMARY_FAULT, head_simulation_mode_);
    }
    auto reservation_service = std::make_unique<ControllerReservationService>(
      reservation_socket_path_, gate, provision.capability, provision.peer,
      std::chrono::milliseconds(50), [this]() {
        const auto now = std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch()).count();
        return controller_stop_proof(now).has_value();
      }, reservation_role_, [this]() {return controller_ingress_snapshot();});
    primary_fault_service_ = std::move(primary_fault_service);
    reservation_service_ = std::move(reservation_service);
    active_goal_admission_ = std::move(gate);      // publish under the same lock
    reservation_timer_->cancel();
  } catch (const std::exception & failure) {
    if (active_goal_admission_) {active_goal_admission_->close();}
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
  neck_stop_witness_.reset();
  std::unique_ptr<ControllerReservationService> service;
  std::unique_ptr<ControllerReservationService> primary_fault;
  std::shared_ptr<ControllerGoalAdmission> gate;
  detach_reservation_lifecycle(&service, &primary_fault, &gate);
  if (gate) {gate->close();}                       // close outside the lock
  primary_fault.reset();
  service.reset();                                 // destroy outside the lock
}

}  // namespace so101_mujoco_support

PLUGINLIB_EXPORT_CLASS(
  so101_mujoco_support::BrokerOwnedTrajectoryController,
  controller_interface::ControllerInterface)
