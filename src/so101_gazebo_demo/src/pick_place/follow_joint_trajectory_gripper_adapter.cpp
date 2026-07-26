#include "so101_gazebo_demo/pick_place/follow_joint_trajectory_gripper_adapter.hpp"

#include <chrono>
#include <cmath>
#include <future>
#include <mutex>
#include <optional>
#include <utility>

#include <control_msgs/action/follow_joint_trajectory.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

namespace so101_gazebo_demo::pick_place
{
namespace
{
using Follow = control_msgs::action::FollowJointTrajectory;
using GoalHandle = rclcpp_action::ClientGoalHandle<Follow>;
using CancelResponse = rclcpp_action::Client<Follow>::CancelResponse;

ActionResult failure(ActionStatus status, std::string code, std::string message)
{
  return {status, Failure{FailureCategory::GRIPPER, std::move(code), std::move(message), {}}};
}
}  // namespace

class RosTrajectoryActionClient::Impl
{
public:
  Impl(const std::shared_ptr<rclcpp::Node> & node, const std::string & action_name) :
      client(rclcpp_action::create_client<Follow>(node, action_name))
  {
  }
  rclcpp_action::Client<Follow>::SharedPtr client;
  std::mutex mutex;
  std::optional<std::shared_future<GoalHandle::SharedPtr>> pending;
  GoalHandle::SharedPtr active;
  std::optional<std::shared_future<GoalHandle::WrappedResult>> result;
  bool cancel_accepted{false};
};

RosTrajectoryActionClient::RosTrajectoryActionClient(std::shared_ptr<rclcpp::Node> node,
                                                     std::string action_name) :
    node_(std::move(node)), action_name_(std::move(action_name)),
    impl_(std::make_unique<Impl>(node_, action_name_))
{
}

RosTrajectoryActionClient::~RosTrajectoryActionClient() = default;

ActionResult RosTrajectoryActionClient::send(const SingleJointTrajectoryGoal & requested,
                                             double timeout_seconds)
{
  if (requested.joint_names.size() != 1 || requested.positions.size() != 1 ||
      requested.joint_names.front() != "6" || !std::isfinite(requested.positions.front()) ||
      !std::isfinite(requested.duration_seconds) || requested.duration_seconds <= 0.0 ||
      !std::isfinite(timeout_seconds) || timeout_seconds <= 0.0) {
    return failure(ActionStatus::FAILED, "GRIPPER_GOAL_INVALID",
                   "A finite positive-duration single-joint 6 trajectory is required");
  }
  const auto timeout = std::chrono::duration<double>(timeout_seconds);
  if (!impl_->client->wait_for_action_server(timeout)) {
    return failure(ActionStatus::TIMED_OUT, "GRIPPER_ACTION_UNAVAILABLE",
                   "Gripper action server is unavailable: " + action_name_);
  }
  Follow::Goal goal;
  goal.trajectory.joint_names = requested.joint_names;
  trajectory_msgs::msg::JointTrajectoryPoint point;
  point.positions = requested.positions;
  const auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::duration<double>(requested.duration_seconds));
  point.time_from_start.sec = static_cast<std::int32_t>(duration.count() / 1000000000LL);
  point.time_from_start.nanosec = static_cast<std::uint32_t>(duration.count() % 1000000000LL);
  goal.trajectory.points.push_back(point);

  auto future = impl_->client->async_send_goal(goal);
  {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->pending = future;
  }
  if (future.wait_for(timeout) != std::future_status::ready) {
    return failure(ActionStatus::TIMED_OUT, "GRIPPER_GOAL_RESPONSE_TIMEOUT",
                   "Timed out waiting for joint 6 goal acceptance");
  }
  const auto handle = future.get();
  {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->pending.reset();
    impl_->active = handle;
    impl_->cancel_accepted = false;
  }
  if (!handle) {
    return failure(ActionStatus::FAILED, "GRIPPER_GOAL_REJECTED",
                   "The joint 6 trajectory goal was rejected");
  }
  auto result_future = impl_->client->async_get_result(handle);
  {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->result = result_future;
  }
  if (result_future.wait_for(timeout) != std::future_status::ready) {
    return failure(ActionStatus::TIMED_OUT, "GRIPPER_RESULT_TIMEOUT",
                   "Timed out waiting for the joint 6 trajectory result");
  }
  const auto result = result_future.get();
  {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->pending.reset();
    impl_->active.reset();
    impl_->result.reset();
    impl_->cancel_accepted = false;
  }
  if (result.code == rclcpp_action::ResultCode::SUCCEEDED && result.result &&
      result.result->error_code == Follow::Result::SUCCESSFUL) {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
  if (result.code == rclcpp_action::ResultCode::CANCELED) {
    return failure(ActionStatus::CANCELLED, "GRIPPER_GOAL_CANCELLED",
                   "The joint 6 trajectory goal was cancelled");
  }
  return failure(ActionStatus::FAILED, "GRIPPER_ACTION_ABORTED",
                 "The joint 6 trajectory action did not complete successfully");
}

ActionResult RosTrajectoryActionClient::cancelAndWait(double timeout_seconds)
{
  std::optional<std::shared_future<GoalHandle::SharedPtr>> pending;
  GoalHandle::SharedPtr active;
  std::optional<std::shared_future<GoalHandle::WrappedResult>> result;
  bool cancel_accepted{false};
  {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    pending = impl_->pending;
    active = impl_->active;
    result = impl_->result;
    cancel_accepted = impl_->cancel_accepted;
  }
  if (!std::isfinite(timeout_seconds) || timeout_seconds <= 0.0) {
    return failure(ActionStatus::FAILED, "GRIPPER_CANCEL_TIMEOUT_INVALID",
                   "Cancellation requires a finite positive timeout");
  }
  const auto deadline = std::chrono::steady_clock::now() +
                        std::chrono::duration<double>(timeout_seconds);
  if (pending) {
    if (pending->wait_until(deadline) != std::future_status::ready) {
      return failure(ActionStatus::TIMED_OUT, "GRIPPER_PENDING_GOAL_UNRESOLVED",
                     "Could not prove whether the timed-out joint 6 goal was accepted");
    }
    active = pending->get();
    if (active && !result) {
      result = impl_->client->async_get_result(active);
    }
    {
      std::lock_guard<std::mutex> lock(impl_->mutex);
      impl_->pending.reset();
      impl_->active = active;
      impl_->result = result;
      impl_->cancel_accepted = false;
    }
    cancel_accepted = false;
  }
  if (!active) {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
  if (!result) {
    result = impl_->client->async_get_result(active);
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->result = result;
  }
  if (!cancel_accepted) {
    auto future = impl_->client->async_cancel_goal(active);
    if (future.wait_until(deadline) != std::future_status::ready) {
      return failure(ActionStatus::TIMED_OUT, "GRIPPER_CANCEL_RESPONSE_TIMEOUT",
                     "Timed out waiting for joint 6 cancel response");
    }
    const auto response = future.get();
    if (!response || response->return_code != CancelResponse::ERROR_NONE ||
        response->goals_canceling.empty()) {
      return failure(ActionStatus::FAILED, "GRIPPER_CANCEL_REJECTED",
                     "The joint 6 controller rejected cancellation");
    }
    cancel_accepted = true;
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->cancel_accepted = true;
  }
  if (result->wait_until(deadline) != std::future_status::ready) {
    return failure(ActionStatus::TIMED_OUT, "GRIPPER_CANCEL_TERMINAL_TIMEOUT",
                   "Cancel was accepted but the joint 6 goal did not become terminal");
  }
  const auto terminal = result->get();
  {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->pending.reset();
    impl_->active.reset();
    impl_->result.reset();
    impl_->cancel_accepted = false;
  }
  if (terminal.code != rclcpp_action::ResultCode::CANCELED) {
    return failure(ActionStatus::FAILED, "GRIPPER_CANCEL_TERMINAL_NOT_CANCELLED",
                   "The joint 6 goal became terminal without a cancelled result");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

FollowJointTrajectoryGripperAdapter::FollowJointTrajectoryGripperAdapter(
  std::shared_ptr<ITrajectoryActionClient> client, double trajectory_duration_seconds,
  double action_timeout_seconds) :
    client_(std::move(client)), trajectory_duration_seconds_(trajectory_duration_seconds),
    action_timeout_seconds_(action_timeout_seconds)
{
}

ActionResult FollowJointTrajectoryGripperAdapter::command(double q6)
{
  if (!client_) {
    return failure(ActionStatus::FAILED, "GRIPPER_ACTION_CLIENT_MISSING",
                   "Joint 6 trajectory client is not configured");
  }
  return client_->send({{"6"}, {q6}, trajectory_duration_seconds_}, action_timeout_seconds_);
}

ActionResult FollowJointTrajectoryGripperAdapter::cancelAndWait()
{
  if (!client_) {
    return failure(ActionStatus::FAILED, "GRIPPER_ACTION_CLIENT_MISSING",
                   "Joint 6 trajectory client is not configured");
  }
  return client_->cancelAndWait(action_timeout_seconds_);
}

}  // namespace so101_gazebo_demo::pick_place
