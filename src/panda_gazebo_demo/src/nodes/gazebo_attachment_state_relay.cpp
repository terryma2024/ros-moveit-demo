#include <atomic>
#include <chrono>
#include <cmath>
#include <memory>
#include <stdexcept>
#include <string>

#include <gz/msgs/stringmsg.pb.h>
#include <gz/msgs/empty.pb.h>
#include <gz/transport/Node.hh>
#include <rclcpp/rclcpp.hpp>

namespace
{

class GazeboAttachmentStateRelay final : public rclcpp::Node
{
public:
  GazeboAttachmentStateRelay()
  : Node("gazebo_attachment_state_relay")
  {
    const auto event_topic = declare_parameter<std::string>(
      "event_topic", "/panda/coke_attached_event");
    const auto state_topic = declare_parameter<std::string>(
      "state_topic", "/panda/coke_attached");
    const auto detach_topic = declare_parameter<std::string>(
      "detach_topic", "/panda/detach_coke");
    enforce_initially_detached_ = declare_parameter<bool>(
      "enforce_initially_detached", true);
    const auto publish_period_seconds = declare_parameter<double>(
      "publish_period_seconds", 0.05);
    if (event_topic.empty() || state_topic.empty() || detach_topic.empty() ||
      event_topic == state_topic)
    {
      throw std::invalid_argument(
              "attachment event and state topics must be non-empty and distinct");
    }
    if (!std::isfinite(publish_period_seconds) || publish_period_seconds <= 0.0) {
      throw std::invalid_argument("attachment state publish period must be positive and finite");
    }

    state_publisher_ = transport_.Advertise<gz::msgs::StringMsg>(state_topic);
    detach_publisher_ = transport_.Advertise<gz::msgs::Empty>(detach_topic);
    if (!state_publisher_.Valid()) {
      throw std::runtime_error("unable to advertise Gazebo attachment state topic");
    }
    if (!detach_publisher_.Valid()) {
      throw std::runtime_error("unable to advertise Gazebo detach command topic");
    }
    if (!transport_.Subscribe(event_topic, &GazeboAttachmentStateRelay::onEvent, this)) {
      throw std::runtime_error("unable to subscribe to Gazebo attachment event topic");
    }
    const auto period = std::chrono::duration_cast<std::chrono::nanoseconds>(
      std::chrono::duration<double>(publish_period_seconds));
    timer_ = create_wall_timer(period, [this]() {publishState();});
    RCLCPP_INFO(
      get_logger(), "Relaying attachment events from %s as durable state on %s; initial state "
      "remains unknown until a validated raw event arrives",
      event_topic.c_str(), state_topic.c_str());
  }

private:
  void onEvent(const gz::msgs::StringMsg & message)
  {
    if (message.data() == "attached") {
      if (enforce_initially_detached_ && !initialized_.load()) {
        RCLCPP_INFO(
          get_logger(), "Observed initial attached state; awaiting confirmed safe detach");
        return;
      }
      attached_.store(true);
      initialized_.store(true);
    } else if (message.data() == "detached") {
      attached_.store(false);
      initialized_.store(true);
    } else {
      RCLCPP_WARN(
        get_logger(), "Ignoring invalid attachment event '%s'", message.data().c_str());
    }
  }

  void publishState()
  {
    if (!initialized_.load()) {
      if (enforce_initially_detached_) {
        gz::msgs::Empty command;
        if (!detach_publisher_.Publish(command)) {
          RCLCPP_ERROR_THROTTLE(
            get_logger(), *get_clock(), 1000,
            "Failed to enforce initially detached state while attachment is unknown");
        }
      }
      return;
    }
    gz::msgs::StringMsg message;
    message.set_data(attached_.load() ? "attached" : "detached");
    if (!state_publisher_.Publish(message)) {
      RCLCPP_ERROR_THROTTLE(
        get_logger(), *get_clock(), 1000, "Failed to publish Gazebo attachment state");
    }
  }

  gz::transport::Node transport_;
  gz::transport::Node::Publisher state_publisher_;
  gz::transport::Node::Publisher detach_publisher_;
  std::atomic<bool> attached_{false};
  std::atomic<bool> initialized_{false};
  bool enforce_initially_detached_{true};
  rclcpp::TimerBase::SharedPtr timer_;
};

}  // namespace

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  try {
    rclcpp::spin(std::make_shared<GazeboAttachmentStateRelay>());
  } catch (const std::exception & error) {
    RCLCPP_FATAL(rclcpp::get_logger("gazebo_attachment_state_relay"), "%s", error.what());
    rclcpp::shutdown();
    return 1;
  }
  rclcpp::shutdown();
  return 0;
}
