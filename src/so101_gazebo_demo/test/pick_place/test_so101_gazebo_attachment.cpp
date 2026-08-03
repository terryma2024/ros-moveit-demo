#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <limits>
#include <memory>
#include <thread>

#include <gz/msgs/empty.pb.h>
#include <gz/msgs/contacts.pb.h>
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
  snapshot.gazebo_task_object_attached = attached;
  snapshot.gazebo_task_object_pose_world = pick_place::Pose3d{};
  snapshot.gazebo_task_object_stationary = true;
  return {state, pick_place::State::DONE, snapshot, nullptr};
}

class BaseObserver final : public pick_place::IWorldObserver
{
public:
  pick_place::ObservationResult observe() override
  {
    ++calls;
    if (fail_on_second && calls > 1) {
      return {std::nullopt, pick_place::Failure{pick_place::FailureCategory::OBSERVATION,
                                                "MOVEIT_REFRESH_FAILED",
                                                "MoveIt refresh failed after Gazebo wait",
                                                {}}};
    }
    pick_place::WorldSnapshot snapshot;
    snapshot.fresh = true;
    snapshot.arm_stationary = true;
    return {snapshot, std::nullopt};
  }

  int calls{0};
  bool fail_on_second{false};
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
  pick_place::GazeboWorldObserver observer(base, world, "plastic_cup", state_topic, "session", 0.5,
                                           3, 0.005, 0.002, 0.02);
  gz::transport::Node peer;
  auto poses = peer.Advertise<gz::msgs::Pose_V>("/world/" + world + "/pose/info");
  auto state = peer.Advertise<gz::msgs::StringMsg>(state_topic);
  auto contacts = peer.Advertise<gz::msgs::Contacts>(
    "/world/" + world +
    "/model/plastic_cup/link/body/sensor/task_object_contact_wall_near/contact");
  ASSERT_TRUE(connected(poses));
  ASSERT_TRUE(connected(state));
  ASSERT_TRUE(connected(contacts));
  std::thread publish([&]() {
    for (int i = 0; i < 3; ++i) {
      gz::msgs::Pose_V message;
      auto * pose = message.add_pose();
      pose->set_name("plastic_cup");
      pose->mutable_position()->set_x(0.02);
      pose->mutable_position()->set_y(-0.28);
      pose->mutable_position()->set_z(0.181);
      pose->mutable_orientation()->set_w(1.0);
      poses.Publish(message);
      gz::msgs::StringMsg attached;
      attached.set_data("detached");
      state.Publish(attached);
      gz::msgs::Contacts contact_message;
      auto * fixed = contact_message.add_contact();
      fixed->mutable_collision1()->set_name("plastic_cup::body::wall_near");
      fixed->mutable_collision2()->set_name("so101::gripper::fixed_fingertip_pad_collision_000");
      auto * fixed_position = fixed->add_position();
      fixed_position->set_y(-0.24);
      fixed_position->set_z(0.205);
      fixed->add_normal()->set_y(1.0);
      fixed->add_depth(0.0004);
      // Repeated positive manifold points remain valid physical penetration
      // evidence.  Deduplication must not erase the live 1.260 mm maximum.
      for (int duplicate = 0; duplicate < 2; ++duplicate) {
        auto * repeated = fixed->add_position();
        repeated->set_y(-0.24);
        repeated->set_z(0.205);
        fixed->add_normal()->set_y(1.0);
        fixed->add_depth(0.001260);
      }
      // Bullet may include separated manifold points beside a real contact.
      // A negative depth is not a physical finger contact and must not poison
      // the semantic sample set or its vertical band.
      auto * separated_fixed_position = fixed->add_position();
      separated_fixed_position->set_y(-0.24);
      separated_fixed_position->set_z(0.300);
      fixed->add_normal()->set_y(1.0);
      fixed->add_depth(-0.001);
      auto * moving = contact_message.add_contact();
      moving->mutable_collision1()->set_name("plastic_cup::body::wall_near");
      moving->mutable_collision2()->set_name("so101::jaw::moving_fingertip_pad_collision_000");
      auto * moving_position = moving->add_position();
      moving_position->set_y(-0.242);
      moving_position->set_z(0.215);
      auto * moving_position_2 = moving->add_position();
      moving_position_2->set_y(-0.242);
      moving_position_2->set_z(0.217);
      moving->add_normal()->set_y(-1.0);
      moving->add_normal()->set_y(-1.0);
      moving->add_depth(0.0006);
      moving->add_depth(0.0005);
      auto * deep_moving_position = moving->add_position();
      deep_moving_position->set_y(-0.242);
      deep_moving_position->set_z(0.215);
      moving->add_normal()->set_y(-1.0);
      moving->add_depth(0.0009644);
      auto * body = contact_message.add_contact();
      body->mutable_collision1()->set_name("plastic_cup::body::collision");
      body->mutable_collision2()->set_name(
        "so101::gripper::gripper_fixed_joint_lump__fixed_finger_mount_collision");
      body->add_position()->set_z(0.250);
      body->add_depth(0.009);
      contacts.Publish(contact_message);
      std::this_thread::sleep_for(10ms);
    }
  });

  const auto result = observer.observe();
  publish.join();

  ASSERT_TRUE(result.snapshot) << (result.failure ? result.failure->code : "no failure");
  ASSERT_TRUE(result.snapshot->gazebo_task_object_attached);
  EXPECT_FALSE(*result.snapshot->gazebo_task_object_attached);
  ASSERT_TRUE(result.snapshot->gazebo_task_object_stationary);
  EXPECT_TRUE(*result.snapshot->gazebo_task_object_stationary);
  ASSERT_TRUE(result.snapshot->gazebo_task_object_fixed_finger_contact);
  EXPECT_TRUE(*result.snapshot->gazebo_task_object_fixed_finger_contact);
  ASSERT_TRUE(result.snapshot->gazebo_task_object_moving_jaw_contact);
  EXPECT_TRUE(*result.snapshot->gazebo_task_object_moving_jaw_contact);
  EXPECT_EQ(result.snapshot->gazebo_task_object_gripper_collision_names,
            (std::set<std::string>{"so101::gripper::fixed_fingertip_pad_collision_000",
                                   "so101::jaw::moving_fingertip_pad_collision_000"}));
  ASSERT_TRUE(result.snapshot->gazebo_task_object_fixed_contact_min_height);
  ASSERT_TRUE(result.snapshot->gazebo_task_object_fixed_contact_max_height);
  EXPECT_DOUBLE_EQ(*result.snapshot->gazebo_task_object_fixed_contact_min_height, 0.205);
  EXPECT_DOUBLE_EQ(*result.snapshot->gazebo_task_object_fixed_contact_max_height, 0.205);
  ASSERT_TRUE(result.snapshot->gazebo_task_object_moving_contact_min_height);
  ASSERT_TRUE(result.snapshot->gazebo_task_object_moving_contact_max_height);
  EXPECT_DOUBLE_EQ(*result.snapshot->gazebo_task_object_moving_contact_min_height, 0.215);
  EXPECT_DOUBLE_EQ(*result.snapshot->gazebo_task_object_moving_contact_max_height, 0.217);
  ASSERT_TRUE(result.snapshot->gazebo_task_object_gripper_max_depth);
  EXPECT_DOUBLE_EQ(*result.snapshot->gazebo_task_object_gripper_max_depth, 0.001260);
  ASSERT_EQ(3U, result.snapshot->gazebo_task_object_fixed_finger_contacts.size());
  ASSERT_EQ(3U, result.snapshot->gazebo_task_object_moving_jaw_contacts.size());
  const auto & fixed_sample = result.snapshot->gazebo_task_object_fixed_finger_contacts.front();
  EXPECT_EQ("wall_near", fixed_sample.task_object_collision);
  EXPECT_NEAR(0.040, fixed_sample.point_task_object.y, 1e-9);
  EXPECT_NEAR(0.024, fixed_sample.point_task_object.z, 1e-9);
  EXPECT_DOUBLE_EQ(1.0, fixed_sample.normal_toward_finger_task_object.y);
  EXPECT_DOUBLE_EQ(0.0004, fixed_sample.depth);
  const auto & moving_sample = result.snapshot->gazebo_task_object_moving_jaw_contacts.front();
  EXPECT_EQ("wall_near", moving_sample.task_object_collision);
  EXPECT_NEAR(0.038, moving_sample.point_task_object.y, 1e-9);
  EXPECT_DOUBLE_EQ(-1.0, moving_sample.normal_toward_finger_task_object.y);
  EXPECT_DOUBLE_EQ(0.0006, moving_sample.depth);
}

TEST(SO101GazeboWorldObserver, RejectsNonfiniteTaskObjectPoseEvidence)
{
  configurePartition();
  BaseObserver base;
  const auto world = unique("world_nonfinite").substr(1);
  const auto state_topic = unique("durable_nonfinite");
  pick_place::GazeboWorldObserver observer(base, world, "plastic_cup", state_topic, "session", 0.2,
                                           3, 0.005, 0.002, 0.02);
  gz::transport::Node peer;
  auto poses = peer.Advertise<gz::msgs::Pose_V>("/world/" + world + "/pose/info");
  auto state = peer.Advertise<gz::msgs::StringMsg>(state_topic);
  ASSERT_TRUE(connected(poses));
  ASSERT_TRUE(connected(state));
  std::thread publish([&]() {
    for (int i = 0; i < 3; ++i) {
      gz::msgs::Pose_V message;
      auto * pose = message.add_pose();
      pose->set_name("plastic_cup");
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
  EXPECT_EQ("GAZEBO_TASK_OBJECT_POSE_NONFINITE", result.failure->code);
}

TEST(SO101GazeboWorldObserver, ReobservesMoveItAfterGazeboWait)
{
  configurePartition();
  BaseObserver base;
  base.fail_on_second = true;
  const auto world = unique("world_moveit_refresh").substr(1);
  const auto state_topic = unique("durable_moveit_refresh");
  pick_place::GazeboWorldObserver observer(base, world, "plastic_cup", state_topic, "session", 0.2,
                                           2, 0.005, 0.002, 0.02);
  gz::transport::Node peer;
  auto poses = peer.Advertise<gz::msgs::Pose_V>("/world/" + world + "/pose/info");
  auto state = peer.Advertise<gz::msgs::StringMsg>(state_topic);
  ASSERT_TRUE(connected(poses));
  ASSERT_TRUE(connected(state));
  std::thread publish([&]() {
    for (int i = 0; i < 2; ++i) {
      gz::msgs::Pose_V message;
      auto * pose = message.add_pose();
      pose->set_name("plastic_cup");
      pose->mutable_position()->set_x(0.02);
      pose->mutable_position()->set_y(-0.28);
      pose->mutable_position()->set_z(0.181);
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
  EXPECT_EQ("MOVEIT_REFRESH_FAILED", result.failure->code);
  EXPECT_EQ(2, base.calls);
}
