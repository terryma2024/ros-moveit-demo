#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <string>
#include <thread>

#include <gz/msgs/empty.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/transport/Node.hh>

#include "panda_gazebo_demo/pick_place/gazebo_attachment_executor.hpp"
#include "panda_gazebo_demo/pick_place/panda_attachment_convergence_policy.hpp"

namespace pick_place = panda_gazebo_demo::pick_place;
using namespace std::chrono_literals;

namespace
{

struct TestTopics
{
  std::string attach;
  std::string detach;
  std::string output;
};

TestTopics uniqueTopics()
{
  static std::atomic<unsigned int> sequence{0};
  const auto suffix = std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) +
                      "_" + std::to_string(sequence.fetch_add(1));
  const auto prefix = "/panda_gazebo_demo/test/attachment_" + suffix;
  return {prefix + "/attach", prefix + "/detach", prefix + "/output"};
}

pick_place::ExecutionContext contextFor(pick_place::State state,
                                        std::optional<bool> attached = std::nullopt)
{
  pick_place::WorldSnapshot before;
  before.fresh = true;
  before.arm_stationary = true;
  before.gripper_open = true;
  before.gazebo_task_object_attached = attached;
  before.moveit_task_object_attached = false;
  before.gazebo_task_object_pose_world = pick_place::Pose3d{};
  before.gazebo_task_object_stationary = true;
  before.joint_positions = {{"panda_finger_joint1", 0.04}, {"panda_finger_joint2", 0.04}};
  before.joint_velocities = {{"panda_finger_joint1", 0.0}, {"panda_finger_joint2", 0.0}};
  return {state, pick_place::State::DONE, before, nullptr};
}

void waitForDiscovery()
{
  std::this_thread::sleep_for(100ms);
}

}  // namespace

TEST(GazeboAttachmentExecutor, PublishesAttachAndWaitsForTrueOutput)
{
  const auto topics = uniqueTopics();
  gz::transport::Node peer;
  auto output = peer.Advertise<gz::msgs::StringMsg>(topics.output);
  std::atomic<int> attach_messages{0};
  ASSERT_TRUE(peer.Subscribe<gz::msgs::Empty>(topics.attach,
                                              [&output, &attach_messages](const gz::msgs::Empty &) {
                                                ++attach_messages;
                                                gz::msgs::StringMsg response;
                                                response.set_data("attached");
                                                output.Publish(response);
                                              }));
  pick_place::GazeboAttachmentExecutor executor(pick_place::State::ATTACH_GAZEBO, true,
                                                topics.attach, topics.detach, topics.output, 0.5,
                                                0.005, false);
  waitForDiscovery();

  const auto result = executor.execute(contextFor(pick_place::State::ATTACH_GAZEBO, false));

  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(1, attach_messages.load());
}

TEST(GazeboAttachmentExecutor, PublishesDetachAndWaitsForFalseOutput)
{
  const auto topics = uniqueTopics();
  gz::transport::Node peer;
  auto output = peer.Advertise<gz::msgs::StringMsg>(topics.output);
  std::atomic<int> detach_messages{0};
  ASSERT_TRUE(peer.Subscribe<gz::msgs::Empty>(topics.detach,
                                              [&output, &detach_messages](const gz::msgs::Empty &) {
                                                ++detach_messages;
                                                gz::msgs::StringMsg response;
                                                response.set_data("detached");
                                                output.Publish(response);
                                              }));
  pick_place::GazeboAttachmentExecutor executor(pick_place::State::DETACH_GAZEBO, false,
                                                topics.attach, topics.detach, topics.output, 0.5,
                                                0.005, false);
  waitForDiscovery();

  const auto result = executor.execute(contextFor(pick_place::State::DETACH_GAZEBO, true));

  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(1, detach_messages.load());
}

TEST(GazeboAttachmentExecutor, RecoveryDetachNoOpsWhenAlreadyDetached)
{
  const auto topics = uniqueTopics();
  gz::transport::Node peer;
  std::atomic<int> detach_messages{0};
  ASSERT_TRUE(peer.Subscribe<gz::msgs::Empty>(
    topics.detach, [&detach_messages](const gz::msgs::Empty &) { ++detach_messages; }));
  pick_place::GazeboAttachmentExecutor executor(
    pick_place::State::RECOVER_DETACH_GAZEBO, false, topics.attach, topics.detach, topics.output,
    0.5, 0.005, true,
    std::make_shared<pick_place::PandaAttachmentConvergencePolicy>(pick_place::GripperLimits{}));
  waitForDiscovery();

  const auto result = executor.execute(contextFor(pick_place::State::RECOVER_DETACH_GAZEBO, false));

  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(0, detach_messages.load());
}

TEST(GazeboAttachmentExecutor, RecoveryNoOpUsesInjectedGripperLimits)
{
  const auto topics = uniqueTopics();
  gz::transport::Node peer;
  auto output = peer.Advertise<gz::msgs::StringMsg>(topics.output);
  std::atomic<int> detach_messages{0};
  ASSERT_TRUE(peer.Subscribe<gz::msgs::Empty>(topics.detach,
                                              [&output, &detach_messages](const gz::msgs::Empty &) {
                                                ++detach_messages;
                                                gz::msgs::StringMsg response;
                                                response.set_data("detached");
                                                output.Publish(response);
                                              }));
  pick_place::GripperLimits strict_gripper;
  strict_gripper.open_min = 0.041;
  pick_place::GazeboAttachmentExecutor executor(
    pick_place::State::RECOVER_DETACH_GAZEBO, false, topics.attach, topics.detach, topics.output,
    0.5, 0.005, true,
    std::make_shared<pick_place::PandaAttachmentConvergencePolicy>(strict_gripper));
  waitForDiscovery();

  const auto result = executor.execute(contextFor(pick_place::State::RECOVER_DETACH_GAZEBO, false));

  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(1, detach_messages.load());
}

TEST(GazeboAttachmentExecutor, TimesOutWithoutExpectedOutput)
{
  const auto topics = uniqueTopics();
  gz::transport::Node peer;
  auto output = peer.Advertise<gz::msgs::StringMsg>(topics.output);
  std::atomic<int> attach_messages{0};
  ASSERT_TRUE(peer.Subscribe<gz::msgs::Empty>(topics.attach,
                                              [&output, &attach_messages](const gz::msgs::Empty &) {
                                                ++attach_messages;
                                                gz::msgs::StringMsg response;
                                                response.set_data("detached");
                                                output.Publish(response);
                                              }));
  pick_place::GazeboAttachmentExecutor executor(pick_place::State::ATTACH_GAZEBO, true,
                                                topics.attach, topics.detach, topics.output, 0.1,
                                                0.005, false);
  waitForDiscovery();

  const auto result = executor.execute(contextFor(pick_place::State::ATTACH_GAZEBO, false));

  EXPECT_EQ(pick_place::ActionStatus::TIMED_OUT, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("GAZEBO_ATTACHMENT_TIMEOUT", result.failure->code);
  EXPECT_EQ(1, attach_messages.load());
}

TEST(GazeboAttachmentExecutor, RejectsWrongStateWithoutPublishing)
{
  const auto topics = uniqueTopics();
  gz::transport::Node peer;
  std::atomic<int> attach_messages{0};
  ASSERT_TRUE(peer.Subscribe<gz::msgs::Empty>(
    topics.attach, [&attach_messages](const gz::msgs::Empty &) { ++attach_messages; }));
  pick_place::GazeboAttachmentExecutor executor(pick_place::State::ATTACH_GAZEBO, true,
                                                topics.attach, topics.detach, topics.output, 0.1,
                                                0.005, false);
  waitForDiscovery();

  const auto result = executor.execute(contextFor(pick_place::State::DETACH_GAZEBO, true));

  EXPECT_EQ(pick_place::ActionStatus::NOT_SUPPORTED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("STATE_NOT_EXECUTABLE", result.failure->code);
  EXPECT_EQ(0, attach_messages.load());
}
