#include "so101_gazebo_demo/pick_place/gazebo_attachment_executor.hpp"

#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <optional>
#include <utility>

#include <gz/msgs/empty.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/transport/Node.hh>

namespace so101_gazebo_demo::pick_place
{

namespace
{

ActionResult attachmentFailure(ActionStatus status, std::string code, std::string message,
                               std::map<std::string, double> metrics = {})
{
  return {status, Failure{FailureCategory::GAZEBO_ATTACHMENT, std::move(code), std::move(message),
                          std::move(metrics)}};
}

bool supportedState(State state) noexcept
{
  return state == State::ATTACH_GAZEBO || state == State::DETACH_GAZEBO ||
         state == State::RECOVER_DETACH_GAZEBO;
}

bool detachedPostconditionSatisfied(const WorldSnapshot & snapshot)
{
  return snapshot.fresh && snapshot.gazebo_task_object_attached && !*snapshot.gazebo_task_object_attached;
}

}  // namespace

class GazeboAttachmentExecutor::Impl
{
public:
  Impl(const std::string & attach_topic, const std::string & detach_topic,
       const std::string & output_topic) :
      attach_publisher(node.Advertise<gz::msgs::Empty>(attach_topic)),
      detach_publisher(node.Advertise<gz::msgs::Empty>(detach_topic))
  {
    subscription_ok = node.Subscribe(output_topic, &Impl::onOutput, this);
  }

  void onOutput(const gz::msgs::StringMsg & message)
  {
    {
      std::lock_guard<std::mutex> lock(mutex);
      if (message.data() == "attached") {
        last_output = true;
      } else if (message.data() == "detached") {
        last_output = false;
      } else {
        last_output.reset();
      }
      ++output_sequence;
    }
    condition.notify_all();
  }

  gz::transport::Node node;
  gz::transport::Node::Publisher attach_publisher;
  gz::transport::Node::Publisher detach_publisher;
  bool subscription_ok{false};
  std::mutex mutex;
  std::condition_variable condition;
  std::optional<bool> last_output;
  std::uint64_t output_sequence{0};
  bool cancel_requested{false};
};

GazeboAttachmentExecutor::GazeboAttachmentExecutor(State allowed_state, bool desired_attached,
                                                   const std::string & attach_topic,
                                                   const std::string & detach_topic,
                                                   const std::string & output_topic,
                                                   double timeout_seconds,
                                                   double poll_interval_seconds, bool idempotent) :
    allowed_state_(allowed_state), desired_attached_(desired_attached),
    timeout_seconds_(timeout_seconds), poll_interval_seconds_(poll_interval_seconds),
    idempotent_(idempotent), impl_(std::make_unique<Impl>(attach_topic, detach_topic, output_topic))
{
}

GazeboAttachmentExecutor::~GazeboAttachmentExecutor() = default;

ActionResult GazeboAttachmentExecutor::execute(const ExecutionContext & context)
{
  if (context.state != allowed_state_ || !supportedState(allowed_state_)) {
    return attachmentFailure(ActionStatus::NOT_SUPPORTED, "STATE_NOT_EXECUTABLE",
                             std::string("Gazebo attachment executor configured for ") +
                               toString(allowed_state_) + " cannot execute " +
                               toString(context.state));
  }
  if (idempotent_ && !desired_attached_ && detachedPostconditionSatisfied(context.before)) {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
  if (!impl_->subscription_ok) {
    return attachmentFailure(ActionStatus::FAILED, "GAZEBO_ATTACHMENT_SUBSCRIPTION_FAILED",
                             "Unable to subscribe to the Gazebo attachment output topic");
  }

  auto & publisher = desired_attached_ ? impl_->attach_publisher : impl_->detach_publisher;
  if (!publisher.Valid()) {
    return attachmentFailure(ActionStatus::FAILED, "GAZEBO_ATTACHMENT_PUBLISH_FAILED",
                             "Gazebo attachment command publisher is invalid");
  }

  std::uint64_t baseline_sequence;
  {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    baseline_sequence = impl_->output_sequence;
    impl_->cancel_requested = false;
  }
  gz::msgs::Empty command;
  if (!publisher.Publish(command)) {
    return attachmentFailure(ActionStatus::FAILED, "GAZEBO_ATTACHMENT_PUBLISH_FAILED",
                             "Failed to publish the Gazebo attachment command");
  }

  const auto deadline =
    std::chrono::steady_clock::now() + std::chrono::duration<double>(timeout_seconds_);
  const auto poll_interval = std::chrono::duration<double>(poll_interval_seconds_);
  std::unique_lock<std::mutex> lock(impl_->mutex);
  while (std::chrono::steady_clock::now() < deadline) {
    if (impl_->cancel_requested) {
      return attachmentFailure(ActionStatus::CANCELLED, "GAZEBO_ATTACHMENT_CANCELLED",
                               "Gazebo attachment convergence wait was cancelled");
    }
    if (impl_->output_sequence > baseline_sequence && impl_->last_output &&
        *impl_->last_output == desired_attached_) {
      return {ActionStatus::SUCCEEDED, std::nullopt};
    }
    impl_->condition.wait_for(lock, poll_interval);
  }

  const std::map<std::string, double> metrics{
    {"desired_attached", desired_attached_ ? 1.0 : 0.0},
    {"fresh_output_count", static_cast<double>(impl_->output_sequence - baseline_sequence)},
    {"last_attached", impl_->last_output ? (*impl_->last_output ? 1.0 : 0.0) : -1.0},
  };
  if (impl_->output_sequence == baseline_sequence) {
    return attachmentFailure(ActionStatus::TIMED_OUT, "GAZEBO_ATTACHMENT_STALE_OUTPUT",
                             "No attachment output message arrived after the command", metrics);
  }
  return attachmentFailure(ActionStatus::TIMED_OUT, "GAZEBO_ATTACHMENT_TIMEOUT",
                           "Fresh Gazebo attachment output did not converge to the requested state",
                           metrics);
}

ActionResult GazeboAttachmentExecutor::cancel()
{
  {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    impl_->cancel_requested = true;
  }
  impl_->condition.notify_all();
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

}  // namespace so101_gazebo_demo::pick_place
