#include <atomic>
#include <chrono>
#include <cmath>
#include <memory>
#include <stdexcept>
#include <string>

#include <gz/msgs/empty.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/transport/Node.hh>
#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

namespace
{
class GazeboAttachmentStateRelay final : public rclcpp::Node
{
public:
  GazeboAttachmentStateRelay() : Node("so101_gazebo_attachment_state_relay")
  {
    const auto & profile = so101_gazebo_demo::pick_place::SO101Profile::canonical();
    const auto event_topic = declare_parameter("event_topic", profile.attachment_event_topic);
    const auto state_topic = declare_parameter("state_topic", profile.attachment_state_topic);
    const auto detach_topic = declare_parameter("detach_topic", profile.detach_topic);
    const auto initially_detached = declare_parameter("initially_detached", true);
    const auto period_seconds = declare_parameter("publish_period_seconds", 0.05);
    if (event_topic.empty() || state_topic.empty() || event_topic == state_topic ||
        !std::isfinite(period_seconds) || period_seconds <= 0.0) {
      throw std::invalid_argument("invalid SO-101 attachment relay configuration");
    }
    state_publisher_ = transport_.Advertise<gz::msgs::StringMsg>(state_topic);
    detach_publisher_ = transport_.Advertise<gz::msgs::Empty>(detach_topic);
    if (!state_publisher_.Valid() || !detach_publisher_.Valid() ||
        !transport_.Subscribe(event_topic, &GazeboAttachmentStateRelay::onEvent, this)) {
      throw std::runtime_error("unable to configure SO-101 attachment relay transport");
    }
    timer_ = create_wall_timer(std::chrono::duration_cast<std::chrono::nanoseconds>(
                                 std::chrono::duration<double>(period_seconds)),
                               [this]() { publish(); });
    if (initially_detached) {
      attached_.store(false);
      initialized_.store(true);
    }
  }

private:
  void onEvent(const gz::msgs::StringMsg & event)
  {
    if (event.data() == "attached") {
      attached_.store(true);
      initialized_.store(true);
    } else if (event.data() == "detached") {
      attached_.store(false);
      initialized_.store(true);
    }
  }

  void publish()
  {
    if (!initialized_.load()) {
      gz::msgs::Empty detach;
      static_cast<void>(detach_publisher_.Publish(detach));
      return;
    }
    gz::msgs::StringMsg state;
    state.set_data(attached_.load() ? "attached" : "detached");
    static_cast<void>(state_publisher_.Publish(state));
  }

  gz::transport::Node transport_;
  gz::transport::Node::Publisher state_publisher_;
  gz::transport::Node::Publisher detach_publisher_;
  std::atomic<bool> attached_{false};
  std::atomic<bool> initialized_{false};
  rclcpp::TimerBase::SharedPtr timer_;
};
}  // namespace

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  try {
    rclcpp::spin(std::make_shared<GazeboAttachmentStateRelay>());
  } catch (const std::exception & error) {
    RCLCPP_FATAL(rclcpp::get_logger("so101_gazebo_attachment_state_relay"), "%s", error.what());
    rclcpp::shutdown();
    return 1;
  }
  rclcpp::shutdown();
  return 0;
}
