#include "panda_gazebo_demo/pick_place/open_gripper_executor.hpp"

#include <chrono>
#include <future>
#include <mutex>
#include <utility>

#include <control_msgs/action/gripper_command.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

namespace panda_gazebo_demo::pick_place
{

namespace
{

using GripperCommand = control_msgs::action::GripperCommand;
using GripperGoalHandle = rclcpp_action::ClientGoalHandle<GripperCommand>;

ActionResult gripperFailure(std::string code, std::string message)
{
  return {ActionStatus::FAILED, Failure{FailureCategory::GRIPPER, std::move(code),
      std::move(message), {}}};
}

}  // namespace

class OpenGripperExecutor::Impl
{
public:
  explicit Impl(const std::shared_ptr<rclcpp::Node> & node, const std::string & action_name)
  : client(rclcpp_action::create_client<GripperCommand>(node, action_name))
  {
  }

  rclcpp_action::Client<GripperCommand>::SharedPtr client;
  std::mutex mutex;
  GripperGoalHandle::SharedPtr active_goal;
};

OpenGripperExecutor::OpenGripperExecutor(
  std::shared_ptr<rclcpp::Node> node, std::string action_name, double open_position,
  double max_effort, double action_timeout_seconds)
: node_(std::move(node)), action_name_(std::move(action_name)), open_position_(open_position),
  max_effort_(max_effort), action_timeout_seconds_(action_timeout_seconds),
  impl_(std::make_unique<Impl>(node_, action_name_))
{
}

OpenGripperExecutor::~OpenGripperExecutor() = default;

ActionResult OpenGripperExecutor::execute(const ExecutionContext & context)
{
  if (context.state != State::PREPARE_OPEN_GRIPPER) {
    return gripperFailure("STATE_NOT_EXECUTABLE",
      "OpenGripperExecutor only supports PREPARE_OPEN_GRIPPER");
  }
  const auto timeout = std::chrono::duration<double>(action_timeout_seconds_);
  if (!impl_->client->wait_for_action_server(timeout)) {
    return gripperFailure("GRIPPER_ACTION_UNAVAILABLE",
      "Gripper action server is unavailable: " + action_name_);
  }
  GripperCommand::Goal goal;
  goal.command.position = open_position_;
  goal.command.max_effort = max_effort_;
  const auto goal_future = impl_->client->async_send_goal(goal);
  if (goal_future.wait_for(timeout) != std::future_status::ready) {
    return gripperFailure("GRIPPER_GOAL_TIMEOUT", "Timed out while sending the gripper open goal");
  }
  const auto goal_handle = goal_future.get();
  if (!goal_handle) {
    return gripperFailure("GRIPPER_GOAL_REJECTED", "The gripper controller rejected the open goal");
  }
  {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->active_goal = goal_handle;
  }
  const auto result_future = impl_->client->async_get_result(goal_handle);
  if (result_future.wait_for(timeout) != std::future_status::ready) {
    static_cast<void>(impl_->client->async_cancel_goal(goal_handle));
    return gripperFailure("GRIPPER_RESULT_TIMEOUT",
      "Timed out while waiting for the gripper open action result");
  }
  const auto result = result_future.get();
  {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->active_goal.reset();
  }
  if (result.code != rclcpp_action::ResultCode::SUCCEEDED) {
    return gripperFailure("GRIPPER_OPEN_FAILED",
        "The gripper action did not complete successfully");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult OpenGripperExecutor::cancel()
{
  std::lock_guard<std::mutex> lock(impl_->mutex);
  if (impl_->active_goal) {
    static_cast<void>(impl_->client->async_cancel_goal(impl_->active_goal));
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

}  // namespace panda_gazebo_demo::pick_place
