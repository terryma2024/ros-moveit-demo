#include <gtest/gtest.h>

#include <chrono>
#include <cstdlib>
#include <memory>
#include <string>
#include <thread>

#include <unistd.h>

#include <gz/msgs/pose_v.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/transport/Node.hh>

#include "panda_gazebo_demo/pick_place/gazebo_world_observer.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

class BaseObserver final : public IWorldObserver
{
public:
  ObservationResult observe() override
  {
    WorldSnapshot snapshot;
    snapshot.fresh = true;
    snapshot.arm_stationary = true;
    return {snapshot, std::nullopt};
  }
};

std::string uniqueName(const std::string & prefix)
{
  static int sequence = 0;
  return prefix + std::to_string(++sequence);
}

void configureUniquePartition()
{
  static const bool configured = []() {
    const auto partition =
      "panda_gazebo_world_observer_" + std::to_string(static_cast<long long>(getpid()));
    return setenv("GZ_PARTITION", partition.c_str(), 1) == 0;
  }();
  ASSERT_TRUE(configured);
}

bool waitForConnections(gz::transport::Node::Publisher & publisher)
{
  for (int attempt = 0; attempt < 100 && !publisher.HasConnections(); ++attempt) {
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  return publisher.HasConnections();
}

void publishPose(gz::transport::Node::Publisher & publisher, const std::string & model)
{
  gz::msgs::Pose_V poses;
  auto * pose = poses.add_pose();
  pose->set_name(model);
  pose->mutable_position()->set_x(0.3);
  pose->mutable_position()->set_z(0.836);
  pose->mutable_orientation()->set_w(1.0);
  ASSERT_TRUE(publisher.Publish(poses));
}

void publishAttachment(gz::transport::Node::Publisher & publisher, const std::string & state)
{
  gz::msgs::StringMsg message;
  message.set_data(state);
  ASSERT_TRUE(publisher.Publish(message));
}

TEST(GazeboWorldObserver, WaitsForFirstPoseAndAttachmentMessages)
{
  configureUniquePartition();
  BaseObserver base;
  const auto world = uniqueName("observer_world_");
  const auto attachment_topic = "/test/" + world + "/attachment";
  GazeboWorldObserver observer(base, world, "coke", attachment_topic, "session", 0.5, 2, 0.01,
                               0.002, 0.02, true);
  gz::transport::Node transport;
  auto pose_publisher = transport.Advertise<gz::msgs::Pose_V>("/world/" + world + "/pose/info");
  auto attachment_publisher = transport.Advertise<gz::msgs::StringMsg>(attachment_topic);
  ASSERT_TRUE(waitForConnections(pose_publisher));
  ASSERT_TRUE(waitForConnections(attachment_publisher));

  std::thread delayed_publish([&]() {
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    publishPose(pose_publisher, "coke");
    publishAttachment(attachment_publisher, "detached");
  });
  const auto result = observer.observe();
  delayed_publish.join();

  ASSERT_TRUE(result.snapshot);
  ASSERT_TRUE(result.snapshot->gazebo_task_object_pose_world);
  ASSERT_TRUE(result.snapshot->gazebo_task_object_attached);
  EXPECT_FALSE(*result.snapshot->gazebo_task_object_attached);
}

TEST(GazeboWorldObserver, MissingInitialPoseStillFailsClosedAtDeadline)
{
  configureUniquePartition();
  BaseObserver base;
  const auto world = uniqueName("missing_pose_world_");
  const auto attachment_topic = "/test/" + world + "/attachment";
  GazeboWorldObserver observer(base, world, "coke", attachment_topic, "session", 0.05, 2, 0.01,
                               0.002, 0.02, true);
  gz::transport::Node transport;
  auto attachment_publisher = transport.Advertise<gz::msgs::StringMsg>(attachment_topic);
  ASSERT_TRUE(waitForConnections(attachment_publisher));
  publishAttachment(attachment_publisher, "detached");

  const auto result = observer.observe();

  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "GAZEBO_COKE_POSE_UNAVAILABLE");
}

TEST(GazeboWorldObserver, MissingInitialAttachmentStillFailsClosedAtDeadline)
{
  configureUniquePartition();
  BaseObserver base;
  const auto world = uniqueName("missing_attachment_world_");
  const auto attachment_topic = "/test/" + world + "/attachment";
  GazeboWorldObserver observer(base, world, "coke", attachment_topic, "session", 0.05, 2, 0.01,
                               0.002, 0.02, true);
  gz::transport::Node transport;
  auto pose_publisher = transport.Advertise<gz::msgs::Pose_V>("/world/" + world + "/pose/info");
  ASSERT_TRUE(waitForConnections(pose_publisher));
  publishPose(pose_publisher, "coke");

  const auto result = observer.observe();

  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "GAZEBO_ATTACHMENT_STATE_UNAVAILABLE");
}

TEST(GazeboWorldObserver, AttachmentStateAgesOutWhenRelayStopsPublishing)
{
  configureUniquePartition();
  BaseObserver base;
  const auto world = uniqueName("stale_attachment_world_");
  const auto attachment_topic = "/test/" + world + "/attachment";
  GazeboWorldObserver observer(base, world, "coke", attachment_topic, "session", 0.5, 2, 0.01,
                               0.002, 0.02, true);
  gz::transport::Node transport;
  auto pose_publisher = transport.Advertise<gz::msgs::Pose_V>("/world/" + world + "/pose/info");
  auto attachment_publisher = transport.Advertise<gz::msgs::StringMsg>(attachment_topic);
  ASSERT_TRUE(waitForConnections(pose_publisher));
  ASSERT_TRUE(waitForConnections(attachment_publisher));
  std::thread initial_publish([&]() {
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    for (int attempt = 0; attempt < 5; ++attempt) {
      publishPose(pose_publisher, "coke");
      publishAttachment(attachment_publisher, "detached");
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
  });
  const auto initial = observer.observe();
  initial_publish.join();
  ASSERT_TRUE(initial.snapshot) << (initial.failure ? initial.failure->code
                                                    : "missing snapshot without failure");

  std::this_thread::sleep_for(std::chrono::milliseconds(550));
  publishPose(pose_publisher, "coke");
  std::this_thread::sleep_for(std::chrono::milliseconds(10));
  const auto stale = observer.observe();

  ASSERT_TRUE(stale.failure);
  EXPECT_EQ(stale.failure->code, "GAZEBO_ATTACHMENT_STATE_UNAVAILABLE");
}

}  // namespace
}  // namespace panda_gazebo_demo::pick_place
