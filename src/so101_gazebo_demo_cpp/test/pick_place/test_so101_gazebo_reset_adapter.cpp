#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <functional>
#include <string>
#include <thread>

#include <gz/msgs/boolean.pb.h>
#include <gz/msgs/empty.pb.h>
#include <gz/msgs/pose.pb.h>
#include <gz/msgs/pose_v.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/transport/Node.hh>

#include "so101_gazebo_demo/pick_place/gazebo_reset_adapter.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{
using namespace std::chrono_literals;

std::string unique(const std::string & suffix)
{
  return "/so101_reset_" + std::to_string(::getpid()) + "_" + suffix;
}

TEST(SO101GazeboResetAdapter, CommandsAndObservesIndependentDurableFacts)
{
  const auto partition = "so101_reset_adapter_" + std::to_string(::getpid());
  ASSERT_EQ(0, setenv("GZ_PARTITION", partition.c_str(), 1));
  const auto world = "world_" + std::to_string(::getpid());
  const auto detach_topic = unique("detach");
  const auto state_topic = unique("state");
  const auto set_pose_service = "/world/" + world + "/set_pose";
  const auto pose_topic = "/world/" + world + "/pose/info";

  gz::transport::Node peer;
  auto states = peer.Advertise<gz::msgs::StringMsg>(state_topic);
  auto poses = peer.Advertise<gz::msgs::Pose_V>(pose_topic);
  std::atomic<int> detach_calls{0};
  ASSERT_TRUE(peer.Subscribe<gz::msgs::Empty>(detach_topic, [&](const gz::msgs::Empty &) {
    ++detach_calls;
    gz::msgs::StringMsg state;
    state.set_data("detached");
    states.Publish(state);
  }));
  Pose3d requested_pose;
  std::function<bool(const gz::msgs::Pose &, gz::msgs::Boolean &)> set_pose =
    [&](const gz::msgs::Pose & request, gz::msgs::Boolean & reply) {
      requested_pose = {request.position().x(),    request.position().y(),
                        request.position().z(),    request.orientation().x(),
                        request.orientation().y(), request.orientation().z(),
                        request.orientation().w()};
      reply.set_data(true);
      gz::msgs::Pose_V update;
      *update.add_pose() = request;
      poses.Publish(update);
      return true;
    };
  ASSERT_TRUE(peer.Advertise(set_pose_service, set_pose));

  GazeboResetAdapter adapter(world, "plastic_cup", detach_topic, state_topic, 0.5, 500);
  std::this_thread::sleep_for(100ms);
  gz::msgs::StringMsg attached;
  attached.set_data("attached");
  states.Publish(attached);
  gz::msgs::Pose_V initial;
  auto * initial_task_object = initial.add_pose();
  initial_task_object->set_name("plastic_cup");
  initial_task_object->mutable_position()->set_x(0.4);
  initial_task_object->mutable_orientation()->set_w(1.0);
  poses.Publish(initial);

  const auto before = adapter.observe();
  ASSERT_TRUE(before);
  EXPECT_TRUE(before->task_object_attached);
  EXPECT_DOUBLE_EQ(0.4, before->task_object_world_pose.x);

  ASSERT_EQ(ActionStatus::SUCCEEDED, adapter.detachTaskObject().status);
  const Pose3d canonical{0.02, -0.28, 0.181, 0.0, 0.0, 0.0, 1.0};
  ASSERT_EQ(ActionStatus::SUCCEEDED, adapter.setTaskObjectWorldPose(canonical).status);
  std::optional<GazeboResetState> after;
  const auto deadline = std::chrono::steady_clock::now() + 500ms;
  while (std::chrono::steady_clock::now() < deadline) {
    after = adapter.observe();
    if (after && !after->task_object_attached &&
        after->attachment_revision > before->attachment_revision &&
        after->pose_revision > before->pose_revision) {
      break;
    }
    std::this_thread::sleep_for(5ms);
  }

  ASSERT_TRUE(after);
  EXPECT_FALSE(after->task_object_attached);
  EXPECT_GT(after->attachment_revision, before->attachment_revision);
  EXPECT_GT(after->pose_revision, before->pose_revision);
  EXPECT_EQ(1, detach_calls.load());
  EXPECT_DOUBLE_EQ(0.02, requested_pose.x);
  EXPECT_DOUBLE_EQ(-0.28, requested_pose.y);
  EXPECT_DOUBLE_EQ(0.181, requested_pose.z);
  EXPECT_DOUBLE_EQ(1.0, requested_pose.qw);
}

TEST(SO101GazeboResetAdapter, ServiceTimeoutIsClassified)
{
  const auto partition = "so101_reset_timeout_" + std::to_string(::getpid());
  ASSERT_EQ(0, setenv("GZ_PARTITION", partition.c_str(), 1));
  GazeboResetAdapter adapter("missing_world", "plastic_cup", unique("detach_missing"),
                             unique("state_missing"), 0.01, 5);

  const auto result = adapter.setTaskObjectWorldPose(Pose3d{});

  EXPECT_EQ(ActionStatus::TIMED_OUT, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("GAZEBO_SET_POSE_TIMEOUT", result.failure->code);
}

}  // namespace
}  // namespace so101_gazebo_demo::pick_place
