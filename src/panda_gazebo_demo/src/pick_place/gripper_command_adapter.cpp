#include "panda_gazebo_demo/pick_place/gripper_command_adapter.hpp"

#include <chrono>
#include <exception>
#include <future>
#include <mutex>
#include <optional>
#include <utility>

#include <control_msgs/action/gripper_command.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

namespace panda_gazebo_demo::pick_place
{

namespace
{

using GripperCommand = control_msgs::action::GripperCommand;
using GripperGoalHandle = rclcpp_action::ClientGoalHandle<GripperCommand>;
using GripperCancelResponse = rclcpp_action::Client<GripperCommand>::CancelResponse;

ActionResult gripperFailure(
  ActionStatus status, std::string code, std::string message)
{
  return {status, Failure{FailureCategory::GRIPPER, std::move(code), std::move(message), {}}};
}

}  // namespace

class GripperCommandAdapter::Impl
{
public:
  explicit Impl(const std::shared_ptr<rclcpp::Node> & node, const std::string & action_name)
  : client(rclcpp_action::create_client<GripperCommand>(node, action_name))
  {
  }

  rclcpp_action::Client<GripperCommand>::SharedPtr client;
  std::mutex mutex;
  std::optional<std::shared_future<GripperGoalHandle::SharedPtr>> pending_goal_response;
  GripperGoalHandle::SharedPtr active_goal;
};

GripperCommandAdapter::GripperCommandAdapter(
  std::shared_ptr<rclcpp::Node> node, std::string action_name,
  double action_timeout_seconds)
: node_(std::move(node)), action_name_(std::move(action_name)),
  action_timeout_seconds_(action_timeout_seconds),
  impl_(std::make_unique<Impl>(node_, action_name_))
{
}

GripperCommandAdapter::~GripperCommandAdapter() = default;

ActionResult GripperCommandAdapter::command(double position, double max_effort)
{
  const auto timeout = std::chrono::duration<double>(action_timeout_seconds_);
  if (!impl_->client->wait_for_action_server(timeout)) {
    return gripperFailure(ActionStatus::TIMED_OUT, "GRIPPER_ACTION_UNAVAILABLE",
      "Gripper action server is unavailable: " + action_name_);
  }
  {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    if (impl_->active_goal || impl_->pending_goal_response) {
      return gripperFailure(ActionStatus::FAILED, "GRIPPER_GOAL_ALREADY_ACTIVE",
        "A gripper action goal is active or still awaiting a response");
    }
  }

  GripperCommand::Goal goal;
  goal.command.position = position;
  goal.command.max_effort = max_effort;
  try {
    const auto goal_future = impl_->client->async_send_goal(goal);
    {
      std::lock_guard<std::mutex> lock(impl_->mutex);
      impl_->pending_goal_response = goal_future;
    }
    if (goal_future.wait_for(timeout) != std::future_status::ready) {
      return gripperFailure(ActionStatus::TIMED_OUT, "GRIPPER_GOAL_RESPONSE_TIMEOUT",
        "Timed out while waiting for the gripper goal response");
    }
    const auto goal_handle = goal_future.get();
    {
      std::lock_guard<std::mutex> lock(impl_->mutex);
      impl_->pending_goal_response.reset();
    }
    if (!goal_handle) {
      return gripperFailure(ActionStatus::FAILED, "GRIPPER_GOAL_REJECTED",
        "The gripper controller rejected the goal");
    }
    {
      std::lock_guard<std::mutex> lock(impl_->mutex);
      impl_->active_goal = goal_handle;
    }

    const auto result_future = impl_->client->async_get_result(goal_handle);
    if (result_future.wait_for(timeout) != std::future_status::ready) {
      return gripperFailure(ActionStatus::TIMED_OUT, "GRIPPER_RESULT_TIMEOUT",
        "Timed out while waiting for the gripper action result");
    }
    const auto result = result_future.get();
    {
      std::lock_guard<std::mutex> lock(impl_->mutex);
      if (impl_->active_goal == goal_handle) {
        impl_->active_goal.reset();
      }
    }
    if (result.result) {
      RCLCPP_INFO(
        node_->get_logger(),
        "GRIPPER_CONTROLLER_RESULT action=%s code=%d position=%.6f effort=%.6f "
        "reached_goal=%s stalled=%s",
        action_name_.c_str(), static_cast<int>(result.code), result.result->position,
        result.result->effort, result.result->reached_goal ? "true" : "false",
        result.result->stalled ? "true" : "false");
    }
    if (result.code == rclcpp_action::ResultCode::SUCCEEDED) {
      return {ActionStatus::SUCCEEDED, std::nullopt};
    }
    if (result.code == rclcpp_action::ResultCode::CANCELED) {
      return gripperFailure(ActionStatus::CANCELLED, "GRIPPER_GOAL_CANCELLED",
        "The gripper action was cancelled");
    }
    return gripperFailure(ActionStatus::FAILED, "GRIPPER_ACTION_FAILED",
      "The gripper action did not complete successfully");
  } catch (const std::exception & exception) {
    return gripperFailure(ActionStatus::FAILED, "GRIPPER_ACTION_EXCEPTION",
      "Gripper action client failed: " + std::string(exception.what()));
  }
}

ActionResult GripperCommandAdapter::cancelAndWait()
{
  std::optional<std::shared_future<GripperGoalHandle::SharedPtr>> pending_goal_response;
  GripperGoalHandle::SharedPtr active_goal;
  {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    pending_goal_response = impl_->pending_goal_response;
    active_goal = impl_->active_goal;
  }

  const auto timeout = std::chrono::duration<double>(action_timeout_seconds_);
  try {
    if (pending_goal_response) {
      if (pending_goal_response->wait_for(timeout) != std::future_status::ready) {
        return gripperFailure(ActionStatus::TIMED_OUT, "GRIPPER_PENDING_GOAL_UNRESOLVED",
          "Could not prove whether the timed-out gripper goal was accepted");
      }
      active_goal = pending_goal_response->get();
      {
        std::lock_guard<std::mutex> lock(impl_->mutex);
        impl_->pending_goal_response.reset();
        impl_->active_goal = active_goal;
      }
      if (!active_goal) {
        return {ActionStatus::SUCCEEDED, std::nullopt};
      }
    }
    if (!active_goal) {
      return {ActionStatus::SUCCEEDED, std::nullopt};
    }
    const auto cancel_future = impl_->client->async_cancel_goal(active_goal);
    if (cancel_future.wait_for(timeout) != std::future_status::ready) {
      return gripperFailure(ActionStatus::TIMED_OUT, "GRIPPER_CANCEL_RESPONSE_TIMEOUT",
        "Timed out while waiting for the gripper cancel response");
    }
    const auto response = cancel_future.get();
    if (!response ||
      response->return_code != GripperCancelResponse::ERROR_NONE ||
      response->goals_canceling.empty())
    {
      return gripperFailure(ActionStatus::FAILED, "GRIPPER_CANCEL_REJECTED",
        "The gripper controller rejected the cancel request");
    }
    {
      std::lock_guard<std::mutex> lock(impl_->mutex);
      if (impl_->active_goal == active_goal) {
        impl_->active_goal.reset();
      }
    }
    return {ActionStatus::SUCCEEDED, std::nullopt};
  } catch (const std::exception & exception) {
    return gripperFailure(ActionStatus::FAILED, "GRIPPER_CANCEL_EXCEPTION",
      "Gripper cancel request failed: " + std::string(exception.what()));
  }
}

}  // namespace panda_gazebo_demo::pick_place
