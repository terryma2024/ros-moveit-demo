#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <limits>
#include <memory>
#include <thread>

#include <gz/msgs/empty.pb.h>
#include <gz/msgs/pose_v.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/transport/Node.hh>
#include <unistd.h>

#include "so101_gazebo_demo/pick_place/gazebo_attachment_executor.hpp"
#include "so101_gazebo_demo/pick_place/gazebo_world_observer.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;
using namespace std::chrono_literals;

namespace
{
std::string unique(const char * stem)
{
  static std::atomic<unsigned> sequence{0};
  return std::string("/so101/test/") + stem + "_" + std::to_string(getpid()) + "_" +
         std::to_string(sequence++);
}

void configurePartition()
{
  static const bool configured = []() {
    const auto partition = "so101_attachment_test_" + std::to_string(getpid());
    return setenv("GZ_PARTITION", partition.c_str(), 1) == 0;
  }();
  ASSERT_TRUE(configured);
}

bool connected(gz::transport::Node::Publisher & publisher)
{
  for (int i = 0; i < 100 && !publisher.HasConnections(); ++i) {
    std::this_thread::sleep_for(5ms);
  }
  return publisher.HasConnections();
}

pick_place::ExecutionContext context(pick_place::State state, std::optional<bool> attached)
{
  pick_place::WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.gazebo_coke_attached = attached;
  snapshot.gazebo_coke_pose_world = pick_place::Pose3d{};
  snapshot.gazebo_coke_stationary = true;
  return {state, pick_place::State::DONE, snapshot, nullptr};
}

class BaseObserver final : public pick_place::IWorldObserver
{
public:
  pick_place::ObservationResult observe() override
  {
    pick_place::WorldSnapshot snapshot;
    snapshot.fresh = true;
    snapshot.arm_stationary = true;
    return {snapshot, std::nullopt};
  }
};
}  // namespace

TEST(SO101GazeboAttachmentExecutor, UsesCommandAndFreshDurableStateTopics)
{
  configurePartition();
  const auto attach = unique("attach");
  const auto detach = unique("detach");
  const auto state = unique("state");
  gz::transport::Node peer;
  auto durable = peer.Advertise<gz::msgs::StringMsg>(state);
  std::atomic<int> commands{0};
  ASSERT_TRUE(peer.Subscribe<gz::msgs::Empty>(attach, [&](const gz::msgs::Empty &) {
    ++commands;
    gz::msgs::StringMsg message;
    message.set_data("attached");
    durable.Publish(message);
  }));
  pick_place::GazeboAttachmentExecutor executor(pick_place::State::ATTACH_GAZEBO, true, attach,
                                                detach, state, 0.5, 0.005, false);
  std::this_thread::sleep_for(100ms);

  const auto result = executor.execute(context(pick_place::State::ATTACH_GAZEBO, false));

  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(1, commands.load());
}

TEST(SO101GazeboAttachmentExecutor, RecoveryNoOpUsesCurrentDetachedFact)
{
  configurePartition();
  const auto attach = unique("attach");
  const auto detach = unique("detach");
  const auto state = unique("state");
  gz::transport::Node peer;
  std::atomic<int> commands{0};
  ASSERT_TRUE(
    peer.Subscribe<gz::msgs::Empty>(detach, [&](const gz::msgs::Empty &) { ++commands; }));
  pick_place::GazeboAttachmentExecutor executor(pick_place::State::RECOVER_DETACH_GAZEBO, false,
                                                attach, detach, state, 0.1, 0.005, true);
  std::this_thread::sleep_for(100ms);

  const auto result = executor.execute(context(pick_place::State::RECOVER_DETACH_GAZEBO, false));

  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(0, commands.load());
}

TEST(SO101GazeboAttachmentExecutor, RejectsStaleOrOppositeStateEvidence)
{
  configurePartition();
  const auto attach = unique("attach");
  const auto detach = unique("detach");
  const auto state = unique("state");
  gz::transport::Node peer;
  auto durable = peer.Advertise<gz::msgs::StringMsg>(state);
  ASSERT_TRUE(peer.Subscribe<gz::msgs::Empty>(attach, [&](const gz::msgs::Empty &) {
    gz::msgs::StringMsg message;
    message.set_data("detached");
    durable.Publish(message);
  }));
  pick_place::GazeboAttachmentExecutor executor(pick_place::State::ATTACH_GAZEBO, true, attach,
                                                detach, state, 0.08, 0.005, false);
  std::this_thread::sleep_for(100ms);

  const auto result = executor.execute(context(pick_place::State::ATTACH_GAZEBO, false));

  EXPECT_EQ(pick_place::ActionStatus::TIMED_OUT, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("GAZEBO_ATTACHMENT_TIMEOUT", result.failure->code);
}

TEST(SO101GazeboWorldObserver, RequiresFreshPoseAndDurableAttachmentState)
{
  configurePartition();
  BaseObserver base;
  const auto world = unique("world").substr(1);
  const auto state_topic = unique("durable");
  pick_place::GazeboWorldObserver observer(base, world, "coke", state_topic, "session", 0.5, 3,
                                           0.005, 0.002, 0.02);
  gz::transport::Node peer;
  auto poses = peer.Advertise<gz::msgs::Pose_V>("/world/" + world + "/pose/info");
  auto state = peer.Advertise<gz::msgs::StringMsg>(state_topic);
  ASSERT_TRUE(connected(poses));
  ASSERT_TRUE(connected(state));
  std::thread publish([&]() {
    for (int i = 0; i < 3; ++i) {
      gz::msgs::Pose_V message;
      auto * pose = message.add_pose();
      pose->set_name("coke");
      pose->mutable_position()->set_x(0.02);
      pose->mutable_position()->set_y(-0.28);
      pose->mutable_position()->set_z(0.181);
      pose->mutable_orientation()->set_w(1.0);
      poses.Publish(message);
      gz::msgs::StringMsg attached;
      attached.set_data("detached");
      state.Publish(attached);
      std::this_thread::sleep_for(10ms);
    }
  });

  const auto result = observer.observe();
  publish.join();

  ASSERT_TRUE(result.snapshot) << (result.failure ? result.failure->code : "no failure");
  ASSERT_TRUE(result.snapshot->gazebo_coke_attached);
  EXPECT_FALSE(*result.snapshot->gazebo_coke_attached);
  ASSERT_TRUE(result.snapshot->gazebo_coke_stationary);
  EXPECT_TRUE(*result.snapshot->gazebo_coke_stationary);
}

TEST(SO101GazeboWorldObserver, RejectsNonfiniteCokePoseEvidence)
{
  configurePartition();
  BaseObserver base;
  const auto world = unique("world_nonfinite").substr(1);
  const auto state_topic = unique("durable_nonfinite");
  pick_place::GazeboWorldObserver observer(base, world, "coke", state_topic, "session", 0.2, 3,
                                           0.005, 0.002, 0.02);
  gz::transport::Node peer;
  auto poses = peer.Advertise<gz::msgs::Pose_V>("/world/" + world + "/pose/info");
  auto state = peer.Advertise<gz::msgs::StringMsg>(state_topic);
  ASSERT_TRUE(connected(poses));
  ASSERT_TRUE(connected(state));
  std::thread publish([&]() {
    for (int i = 0; i < 3; ++i) {
      gz::msgs::Pose_V message;
      auto * pose = message.add_pose();
      pose->set_name("coke");
      pose->mutable_position()->set_x(std::numeric_limits<double>::quiet_NaN());
      pose->mutable_orientation()->set_w(1.0);
      poses.Publish(message);
      gz::msgs::StringMsg detached;
      detached.set_data("detached");
      state.Publish(detached);
      std::this_thread::sleep_for(10ms);
    }
  });

  const auto result = observer.observe();
  publish.join();

  EXPECT_FALSE(result.snapshot);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("GAZEBO_COKE_POSE_NONFINITE", result.failure->code);
}
