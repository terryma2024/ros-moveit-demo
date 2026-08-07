#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <limits>
#include <string>
#include <thread>

#include <unistd.h>

#include <gz/msgs/contacts.pb.h>
#include <gz/msgs/pose_v.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/transport/Node.hh>

#include "so101_gazebo_demo/pick_place/gazebo_world_observer.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{
using namespace std::chrono_literals;

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
  static std::atomic<unsigned> sequence{0};
  return prefix + "_" + std::to_string(getpid()) + "_" + std::to_string(sequence++);
}

void configurePartition()
{
  static const bool configured = []() {
    const auto partition = "so101_world_observer_" + std::to_string(getpid());
    return setenv("GZ_PARTITION", partition.c_str(), 1) == 0;
  }();
  ASSERT_TRUE(configured);
}

bool connected(gz::transport::Node::Publisher & publisher)
{
  for (int attempt = 0; attempt < 100 && !publisher.HasConnections(); ++attempt) {
    std::this_thread::sleep_for(5ms);
  }
  return publisher.HasConnections();
}

struct ObserverFixture
{
  explicit ObserverFixture(double max_age = 0.5) :
      world(uniqueName("world")), state_topic("/test/" + uniqueName("attachment")),
      observer(base, world, "plastic_cup", state_topic, "session", max_age, 2, 0.001, 0.002, 0.02),
      poses(transport.Advertise<gz::msgs::Pose_V>("/world/" + world + "/pose/info")),
      attachment(transport.Advertise<gz::msgs::StringMsg>(state_topic)),
      bottom(transport.Advertise<gz::msgs::Contacts>(
        "/world/" + world +
        "/model/plastic_cup/link/body/sensor/task_object_contact_bottom/contact")),
      finger(transport.Advertise<gz::msgs::Contacts>(
        "/world/" + world +
        "/model/plastic_cup/link/body/sensor/task_object_contact_wall_near/contact"))
  {
    EXPECT_TRUE(connected(poses));
    EXPECT_TRUE(connected(attachment));
    EXPECT_TRUE(connected(bottom));
    EXPECT_TRUE(connected(finger));
  }

  void publishReady()
  {
    for (int sample = 0; sample < 2; ++sample) {
      gz::msgs::Pose_V message;
      auto * pose = message.add_pose();
      pose->set_name("plastic_cup");
      pose->mutable_position()->set_z(0.165);
      pose->mutable_orientation()->set_w(1.0);
      ASSERT_TRUE(poses.Publish(message));
      gz::msgs::StringMsg state;
      state.set_data("detached");
      ASSERT_TRUE(attachment.Publish(state));
      std::this_thread::sleep_for(2ms);
    }
  }

  static void publishContact(gz::transport::Node::Publisher & publisher,
                             const std::string & object_collision,
                             const std::string & other_collision,
                             std::optional<double> depth = 0.001)
  {
    gz::msgs::Contacts message;
    auto * contact = message.add_contact();
    contact->mutable_collision1()->set_name(object_collision);
    contact->mutable_collision2()->set_name(other_collision);
    contact->add_position()->set_z(0.12);
    contact->add_normal()->set_z(-1.0);
    if (depth)
      contact->add_depth(*depth);
    ASSERT_TRUE(publisher.Publish(message));
    std::this_thread::sleep_for(10ms);
  }

  BaseObserver base;
  std::string world;
  std::string state_topic;
  GazeboWorldObserver observer;
  gz::transport::Node transport;
  gz::transport::Node::Publisher poses;
  gz::transport::Node::Publisher attachment;
  gz::transport::Node::Publisher bottom;
  gz::transport::Node::Publisher finger;
};

TEST(GazeboWorldObserver, PreservesFreshBottomToIntendedTableContact)
{
  configurePartition();
  ObserverFixture fixture;
  fixture.publishReady();
  ObserverFixture::publishContact(fixture.bottom, "plastic_cup::body::bottom",
                                  "default::table::link::collision");

  const auto result = fixture.observer.observe();

  ASSERT_TRUE(result.snapshot) << (result.failure ? result.failure->code : "missing snapshot");
  ASSERT_TRUE(result.snapshot->gazebo_task_object_intended_support_contact);
  EXPECT_TRUE(*result.snapshot->gazebo_task_object_intended_support_contact);
  ASSERT_EQ(1U, result.snapshot->gazebo_task_object_support_contacts.size());
  EXPECT_EQ("table::link::collision",
            result.snapshot->gazebo_task_object_support_contacts.front().support_collision);
  EXPECT_TRUE(result.snapshot->gazebo_support_contact_observed_at);
}

TEST(GazeboWorldObserver, DoesNotTreatOtherBottomCollisionAsSupport)
{
  configurePartition();
  ObserverFixture fixture;
  fixture.publishReady();
  ObserverFixture::publishContact(fixture.bottom, "plastic_cup::body::bottom",
                                  "default::floor::link::collision");

  const auto result = fixture.observer.observe();

  ASSERT_TRUE(result.snapshot);
  ASSERT_TRUE(result.snapshot->gazebo_task_object_intended_support_contact);
  EXPECT_FALSE(*result.snapshot->gazebo_task_object_intended_support_contact);
  EXPECT_EQ((std::set<std::string>{"floor::link::collision"}),
            result.snapshot->gazebo_task_object_support_collision_names);
}

TEST(GazeboWorldObserver, KeepsBottomAndFingerFreshnessIndependent)
{
  configurePartition();
  ObserverFixture fixture;
  fixture.publishReady();
  ObserverFixture::publishContact(fixture.bottom, "plastic_cup::body::bottom",
                                  "table::link::collision");
  const auto bottom_time = std::chrono::steady_clock::now();
  ObserverFixture::publishContact(fixture.finger, "plastic_cup::body::wall_near",
                                  "so101::gripper::fixed_fingertip_pad_collision_000");

  const auto result = fixture.observer.observe();

  ASSERT_TRUE(result.snapshot);
  ASSERT_TRUE(result.snapshot->gazebo_support_contact_observed_at);
  ASSERT_TRUE(result.snapshot->gazebo_gripper_contact_observed_at);
  EXPECT_LT(*result.snapshot->gazebo_support_contact_observed_at, bottom_time);
  EXPECT_GT(*result.snapshot->gazebo_gripper_contact_observed_at, bottom_time);
}

TEST(GazeboWorldObserver, RejectsNegativeMissingAndNonFiniteSupportDepth)
{
  configurePartition();
  ObserverFixture fixture;
  fixture.publishReady();
  for (const auto depth : {std::optional<double>{-0.001}, std::optional<double>{},
                           std::optional<double>{std::numeric_limits<double>::quiet_NaN()}}) {
    ObserverFixture::publishContact(fixture.bottom, "plastic_cup::body::bottom",
                                    "table::link::collision", depth);
  }

  const auto result = fixture.observer.observe();

  ASSERT_TRUE(result.snapshot);
  ASSERT_TRUE(result.snapshot->gazebo_task_object_intended_support_contact);
  EXPECT_FALSE(*result.snapshot->gazebo_task_object_intended_support_contact);
  EXPECT_TRUE(result.snapshot->gazebo_task_object_support_contacts.empty());
}

TEST(GazeboWorldObserver, IncrementsPoseReceiptSequenceAndTimestamp)
{
  configurePartition();
  ObserverFixture fixture;
  fixture.publishReady();
  const auto first = fixture.observer.observe();
  ASSERT_TRUE(first.snapshot);
  ASSERT_TRUE(first.snapshot->gazebo_pose_sequence);
  ASSERT_TRUE(first.snapshot->gazebo_pose_observed_at);

  std::this_thread::sleep_for(2ms);
  fixture.publishReady();
  const auto second = fixture.observer.observe();

  ASSERT_TRUE(second.snapshot);
  ASSERT_TRUE(second.snapshot->gazebo_pose_sequence);
  ASSERT_TRUE(second.snapshot->gazebo_pose_observed_at);
  EXPECT_GT(*second.snapshot->gazebo_pose_sequence, *first.snapshot->gazebo_pose_sequence);
  EXPECT_GT(*second.snapshot->gazebo_pose_observed_at, *first.snapshot->gazebo_pose_observed_at);
}

}  // namespace
}  // namespace so101_gazebo_demo::pick_place
