#include "so101_gazebo_demo/pick_place/gazebo_reset_adapter.hpp"

#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <optional>
#include <string>
#include <utility>

#include <gz/msgs/boolean.pb.h>
#include <gz/msgs/empty.pb.h>
#include <gz/msgs/pose.pb.h>
#include <gz/msgs/pose_v.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/transport/Node.hh>

namespace so101_gazebo_demo::pick_place
{
namespace
{

ActionResult gazeboFailure(ActionStatus status, std::string code, std::string message)
{
  return {status,
          Failure{FailureCategory::WORLD_INCONSISTENCY, std::move(code), std::move(message), {}}};
}

Pose3d toPose3d(const gz::msgs::Pose & pose)
{
  return {pose.position().x(),    pose.position().y(),    pose.position().z(),
          pose.orientation().x(), pose.orientation().y(), pose.orientation().z(),
          pose.orientation().w()};
}

}  // namespace

class GazeboResetAdapter::Impl
{
public:
  Impl(const std::string & world_name, std::string task_object_id, const std::string & detach_topic,
       const std::string & attachment_topic, double observation_timeout_seconds,
       unsigned int service_timeout_ms) :
      task_object_id(std::move(task_object_id)), set_pose_service("/world/" + world_name + "/set_pose"),
      observation_timeout(std::chrono::duration<double>(observation_timeout_seconds)),
      service_timeout_ms(service_timeout_ms),
      detach_publisher(node.Advertise<gz::msgs::Empty>(detach_topic))
  {
    pose_subscription_ok =
      node.Subscribe("/world/" + world_name + "/pose/info", &Impl::onPoses, this);
    attachment_subscription_ok = node.Subscribe(attachment_topic, &Impl::onAttachment, this);
  }

  void onPoses(const gz::msgs::Pose_V & message)
  {
    std::lock_guard<std::mutex> lock(mutex);
    for (const auto & pose : message.pose()) {
      if (pose.name() == task_object_id || pose.name().find("::" + task_object_id) != std::string::npos) {
        state.task_object_world_pose = toPose3d(pose);
        ++state.pose_revision;
        pose_received_at = std::chrono::steady_clock::now();
        have_pose = true;
        condition.notify_all();
        return;
      }
    }
  }

  void onAttachment(const gz::msgs::StringMsg & message)
  {
    std::lock_guard<std::mutex> lock(mutex);
    if (message.data() == "attached") {
      state.task_object_attached = true;
    } else if (message.data() == "detached") {
      state.task_object_attached = false;
    } else {
      return;
    }
    ++state.attachment_revision;
    attachment_received_at = std::chrono::steady_clock::now();
    have_attachment = true;
    condition.notify_all();
  }

  std::string task_object_id;
  std::string set_pose_service;
  std::chrono::duration<double> observation_timeout;
  unsigned int service_timeout_ms;
  gz::transport::Node node;
  gz::transport::Node::Publisher detach_publisher;
  bool pose_subscription_ok{false};
  bool attachment_subscription_ok{false};
  std::mutex mutex;
  std::condition_variable condition;
  GazeboResetState state;
  bool have_pose{false};
  bool have_attachment{false};
  std::chrono::steady_clock::time_point pose_received_at{};
  std::chrono::steady_clock::time_point attachment_received_at{};
};

GazeboResetAdapter::GazeboResetAdapter(const std::string & world_name, std::string task_object_id,
                                       const std::string & detach_topic,
                                       const std::string & attachment_topic,
                                       double observation_timeout_seconds,
                                       unsigned int service_timeout_ms) :
    impl_(std::make_unique<Impl>(world_name, std::move(task_object_id), detach_topic, attachment_topic,
                                 observation_timeout_seconds, service_timeout_ms))
{
}

GazeboResetAdapter::~GazeboResetAdapter() = default;

std::optional<GazeboResetState> GazeboResetAdapter::observe()
{
  if (!impl_->pose_subscription_ok || !impl_->attachment_subscription_ok ||
      impl_->observation_timeout <= std::chrono::duration<double>::zero()) {
    return std::nullopt;
  }
  std::unique_lock<std::mutex> lock(impl_->mutex);
  impl_->condition.wait_for(lock, impl_->observation_timeout,
                            [this]() { return impl_->have_pose && impl_->have_attachment; });
  const auto now = std::chrono::steady_clock::now();
  if (!impl_->have_pose || !impl_->have_attachment ||
      now - impl_->pose_received_at > impl_->observation_timeout ||
      now - impl_->attachment_received_at > impl_->observation_timeout) {
    return std::nullopt;
  }
  return impl_->state;
}

ActionResult GazeboResetAdapter::detachTaskObject()
{
  if (!impl_->detach_publisher.Valid()) {
    return gazeboFailure(ActionStatus::FAILED, "GAZEBO_DETACH_PUBLISHER_INVALID",
                         "Gazebo detach publisher is invalid");
  }
  gz::msgs::Empty request;
  if (!impl_->detach_publisher.Publish(request)) {
    return gazeboFailure(ActionStatus::FAILED, "GAZEBO_DETACH_PUBLISH_FAILED",
                         "Gazebo detach command could not be published");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult GazeboResetAdapter::setTaskObjectWorldPose(const Pose3d & pose)
{
  gz::msgs::Pose request;
  request.set_name(impl_->task_object_id);
  request.mutable_position()->set_x(pose.x);
  request.mutable_position()->set_y(pose.y);
  request.mutable_position()->set_z(pose.z);
  request.mutable_orientation()->set_x(pose.qx);
  request.mutable_orientation()->set_y(pose.qy);
  request.mutable_orientation()->set_z(pose.qz);
  request.mutable_orientation()->set_w(pose.qw);
  gz::msgs::Boolean reply;
  bool service_result = false;
  if (!impl_->node.Request(impl_->set_pose_service, request, impl_->service_timeout_ms, reply,
                           service_result)) {
    return gazeboFailure(ActionStatus::TIMED_OUT, "GAZEBO_SET_POSE_TIMEOUT",
                         "Gazebo set_pose service timed out");
  }
  if (!service_result || !reply.data()) {
    return gazeboFailure(ActionStatus::FAILED, "GAZEBO_SET_POSE_REJECTED",
                         "Gazebo rejected the TaskObject set_pose request");
  }
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

}  // namespace so101_gazebo_demo::pick_place
