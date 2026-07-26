#include <chrono>
#include <cmath>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>

#include <gz/msgs/stringmsg.pb.h>
#include <gz/transport/Node.hh>
#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/attachment_state_reducer.hpp"
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
    const auto period_seconds = declare_parameter("publish_period_seconds", 0.05);
    if (event_topic.empty() || state_topic.empty() || event_topic == state_topic ||
        !std::isfinite(period_seconds) || period_seconds <= 0.0) {
      throw std::invalid_argument("invalid SO-101 attachment relay configuration");
    }
    state_publisher_ = transport_.Advertise<gz::msgs::StringMsg>(state_topic);
    if (!state_publisher_.Valid() ||
        !transport_.Subscribe(event_topic, &GazeboAttachmentStateRelay::onEvent, this)) {
      throw std::runtime_error("unable to configure SO-101 attachment relay transport");
    }
    timer_ = create_wall_timer(std::chrono::duration_cast<std::chrono::nanoseconds>(
                                 std::chrono::duration<double>(period_seconds)),
                               [this]() { publish(); });
  }

private:
  void onEvent(const gz::msgs::StringMsg & event)
  {
    if (reducer_.consume(event.data())) {
      RCLCPP_INFO(get_logger(), "RAW_ATTACHMENT_EVENT state=%s", event.data().c_str());
    }
  }

  void publish()
  {
    const auto state_value = reducer_.state();
    if (!state_value) {
      return;
    }
    gz::msgs::StringMsg state;
    state.set_data(*state_value ? "attached" : "detached");
    if (last_logged_state_ != state_value) {
      RCLCPP_INFO(get_logger(), "DURABLE_ATTACHMENT_STATE state=%s",
                  *state_value ? "attached" : "detached");
      last_logged_state_ = state_value;
    }
    static_cast<void>(state_publisher_.Publish(state));
  }

  gz::transport::Node transport_;
  gz::transport::Node::Publisher state_publisher_;
  so101_gazebo_demo::pick_place::AttachmentStateReducer reducer_;
  std::optional<bool> last_logged_state_;
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
