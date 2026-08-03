#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <memory>
#include <thread>

#include <gz/msgs/empty.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/transport/Node.hh>
#include <unistd.h>

#include "pick_place_common/gazebo_attachment_executor.hpp"

namespace pp = pick_place_common;
namespace adapters = pick_place_common::ros_adapters;
using namespace std::chrono_literals;

namespace
{
std::string uniqueTopic(const char * stem)
{
  static std::atomic<unsigned> sequence{0};
  return std::string("/common/attachment/") + stem + "_" + std::to_string(getpid()) + "_" +
         std::to_string(sequence++);
}

void configurePartition()
{
  static const bool configured = []() {
    const auto partition = "common_attachment_test_" + std::to_string(getpid());
    return setenv("GZ_PARTITION", partition.c_str(), 1) == 0;
  }();
  ASSERT_TRUE(configured);
}

pp::ExecutionContext context(pp::State state, std::optional<bool> attached)
{
  pp::WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.gazebo_task_object_attached = attached;
  return {state, pp::State::DONE, snapshot, nullptr};
}

struct Topics
{
  std::string attach{uniqueTopic("attach")};
  std::string detach{uniqueTopic("detach")};
  std::string state{uniqueTopic("state")};
};
}  // namespace

TEST(CommonGazeboAttachmentExecutor, PublishesOnceAndWaitsForDesiredDurableState)
{
  configurePartition();
  const Topics topics;
  gz::transport::Node peer;
  auto state = peer.Advertise<gz::msgs::StringMsg>(topics.state);
  std::atomic<int> commands{0};
  ASSERT_TRUE(peer.Subscribe<gz::msgs::Empty>(topics.attach, [&](const auto &) {
    ++commands;
    gz::msgs::StringMsg output;
    output.set_data("attached");
    state.Publish(output);
  }));
  adapters::GazeboAttachmentExecutor executor(pp::State::ATTACH_GAZEBO, true, topics.attach,
                                              topics.detach, topics.state, 0.5, 0.005, false);
  std::this_thread::sleep_for(100ms);
  EXPECT_EQ(pp::ActionStatus::SUCCEEDED,
            executor.execute(context(pp::State::ATTACH_GAZEBO, false)).status);
  EXPECT_EQ(1, commands.load());
}

TEST(CommonGazeboAttachmentExecutor, OppositeFreshStateTimesOutAndWrongStateIsRejected)
{
  configurePartition();
  const Topics topics;
  gz::transport::Node peer;
  auto state = peer.Advertise<gz::msgs::StringMsg>(topics.state);
  ASSERT_TRUE(peer.Subscribe<gz::msgs::Empty>(topics.attach, [&](const auto &) {
    gz::msgs::StringMsg output;
    output.set_data("detached");
    state.Publish(output);
  }));
  adapters::GazeboAttachmentExecutor executor(pp::State::ATTACH_GAZEBO, true, topics.attach,
                                              topics.detach, topics.state, 0.05, 0.005, false);
  std::this_thread::sleep_for(100ms);
  const auto wrong = executor.execute(context(pp::State::DETACH_GAZEBO, false));
  ASSERT_TRUE(wrong.failure);
  EXPECT_EQ("STATE_NOT_EXECUTABLE", wrong.failure->code);
  const auto timeout = executor.execute(context(pp::State::ATTACH_GAZEBO, false));
  ASSERT_TRUE(timeout.failure);
  EXPECT_EQ("GAZEBO_ATTACHMENT_TIMEOUT", timeout.failure->code);
}

TEST(CommonGazeboAttachmentExecutor, IdempotencyRequiresAndUsesPolicy)
{
  configurePartition();
  const Topics topics;
  adapters::GazeboAttachmentExecutor missing_policy({pp::State::RECOVER_DETACH_GAZEBO, false,
                                                     topics.attach, topics.detach, topics.state,
                                                     0.05, 0.005, true},
                                                    nullptr);
  const auto missing = missing_policy.execute(context(pp::State::RECOVER_DETACH_GAZEBO, false));
  ASSERT_TRUE(missing.failure);
  EXPECT_EQ("GAZEBO_ATTACHMENT_POLICY_MISSING", missing.failure->code);

  adapters::GazeboAttachmentExecutor converged(pp::State::RECOVER_DETACH_GAZEBO, false,
                                               topics.attach, topics.detach, topics.state, 0.05,
                                               0.005, true);
  EXPECT_EQ(pp::ActionStatus::SUCCEEDED,
            converged.execute(context(pp::State::RECOVER_DETACH_GAZEBO, false)).status);
}

TEST(CommonGazeboAttachmentExecutor, CancellationInterruptsConvergenceWait)
{
  configurePartition();
  const Topics topics;
  gz::transport::Node peer;
  std::atomic<int> commands{0};
  ASSERT_TRUE(peer.Subscribe<gz::msgs::Empty>(
    topics.attach, [&commands](const gz::msgs::Empty &) { ++commands; }));
  adapters::GazeboAttachmentExecutor executor(pp::State::ATTACH_GAZEBO, true, topics.attach,
                                              topics.detach, topics.state, 1.0, 0.005, false);
  std::this_thread::sleep_for(100ms);
  pp::ActionResult result;
  std::thread worker(
    [&]() { result = executor.execute(context(pp::State::ATTACH_GAZEBO, false)); });
  std::this_thread::sleep_for(20ms);
  EXPECT_EQ(pp::ActionStatus::SUCCEEDED, executor.cancel().status);
  worker.join();
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("GAZEBO_ATTACHMENT_CANCELLED", result.failure->code);
}
