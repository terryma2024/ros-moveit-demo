#include <gtest/gtest.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <limits>
#include <memory>
#include <string>
#include <thread>
#include <type_traits>
#include <vector>

#include <mujoco/mujoco.h>

#define private public
#include "so101_mujoco_support/simulation_evidence_plugin.hpp"
#undef private

namespace
{
using so101_mujoco_support::EvidenceBuilder;
using so101_mujoco_support::EvidenceState;
using so101_mujoco_support::SimulationEvidencePlugin;
using so101_mujoco_support::msg::SimulationEvidence;

struct ModelDeleter
{
  void operator()(mjModel * value) const
  {
    mj_deleteModel(value);
  }
};
struct DataDeleter
{
  void operator()(mjData * value) const
  {
    mj_deleteData(value);
  }
};

class AtomicEvidenceTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    const auto xml_path = std::filesystem::temp_directory_path() / "so101_atomic_evidence.xml";
    std::ofstream(xml_path) << R"(<mujoco><option timestep="0.001" gravity="0 0 -9.81"/>
      <worldbody><geom name="table" type="plane" size="1 1 .1"/>
      <body name="cup" pos="0 0 .08"><freejoint name="cup_joint"/><geom name="cup_geom" type="sphere" size=".05" mass=".1"/></body>
      <body name="left"><freejoint name="left_joint"/><geom name="left_tip" type="sphere" size=".02" mass=".1"/></body>
      <body name="right"><freejoint name="right_joint"/><geom name="right_tip" type="sphere" size=".02" mass=".1"/></body>
      </worldbody></mujoco>)";
    char error[1024]{};
    model_.reset(mj_loadXML(xml_path.c_str(), nullptr, error, sizeof(error)));
    ASSERT_NE(model_, nullptr) << error;
    data_.reset(mj_makeData(model_.get()));
    ASSERT_NE(data_, nullptr);
    ASSERT_TRUE(builder_.configure(model_.get(), "cup", "left_tip", "right_tip", {"table"}, 32));
    state_.simulation_session_id = "session-a";
  }

  void place_free_body(const char * joint, double x, double y, double z)
  {
    const int id = mj_name2id(model_.get(), mjOBJ_JOINT, joint);
    ASSERT_GE(id, 0);
    const int address = model_->jnt_qposadr[id];
    data_->qpos[address] = x;
    data_->qpos[address + 1] = y;
    data_->qpos[address + 2] = z;
    data_->qpos[address + 3] = 1.0;
  }

  std::unique_ptr<mjModel, ModelDeleter> model_;
  std::unique_ptr<mjData, DataDeleter> data_;
  EvidenceBuilder builder_;
  EvidenceState state_;
};

TEST_F(AtomicEvidenceTest, ZeroContactSnapshotIsAtomicAndFinite)
{
  place_free_body("left_joint", -.3, 0, .2);
  place_free_body("right_joint", .3, 0, .2);
  mj_forward(model_.get(), data_.get());
  const auto message = builder_.build(model_.get(), data_.get(), false, state_);
  EXPECT_EQ(message.simulation_session_id, "session-a");
  EXPECT_EQ(message.reset_epoch, 0U);
  EXPECT_EQ(message.simulation_step, 0U);
  EXPECT_EQ(message.publisher_sequence, 0U);
  EXPECT_FALSE(message.paused);
  EXPECT_FALSE(message.has_contact);
  EXPECT_DOUBLE_EQ(message.minimum_signed_distance_m, 0.0);
  EXPECT_DOUBLE_EQ(message.maximum_normal_force_n, 0.0);
  EXPECT_TRUE(message.left_fingertip_contacts.empty());
  EXPECT_TRUE(message.right_fingertip_contacts.empty());
  EXPECT_TRUE(message.other_object_contacts.empty());
  EXPECT_EQ(message.object_body, "cup");
  EXPECT_GE(message.object_body_id, 0);
  EXPECT_EQ(message.header.frame_id, "world");
  EXPECT_TRUE(std::isfinite(message.object_pose_world.position.z));
}

TEST_F(AtomicEvidenceTest, ResetGenerationIsTheOnlyEpochAuthority)
{
  mj_forward(model_.get(), data_.get());
  const auto first = builder_.build(model_.get(), data_.get(), false, state_, 0);
  data_->time = .001;
  const auto second = builder_.build(model_.get(), data_.get(), false, state_, 0);
  data_->time = 0.0;
  const auto time_decrease = builder_.build(model_.get(), data_.get(), false, state_, 0);
  const auto reset = builder_.build(model_.get(), data_.get(), false, state_, 1);
  EXPECT_EQ(second.publisher_sequence, first.publisher_sequence + 1);
  EXPECT_EQ(second.simulation_step, first.simulation_step + 1);
  EXPECT_EQ(time_decrease.reset_epoch, first.reset_epoch);
  EXPECT_EQ(time_decrease.simulation_step, second.simulation_step);
  EXPECT_EQ(reset.reset_epoch, first.reset_epoch + 1);
  EXPECT_EQ(reset.simulation_step, 0U);
  EXPECT_EQ(reset.simulation_session_id, first.simulation_session_id);
  EXPECT_EQ(reset.publisher_sequence, time_decrease.publisher_sequence + 1);
}

TEST_F(AtomicEvidenceTest, ConsumesAllResetGenerationIncrementsWithoutLoss)
{
  mj_forward(model_.get(), data_.get());
  const auto first = builder_.build(model_.get(), data_.get(), false, state_, 0);
  const auto reset_twice = builder_.build(model_.get(), data_.get(), false, state_, 2);
  const auto unchanged = builder_.build(model_.get(), data_.get(), false, state_, 2);
  EXPECT_EQ(reset_twice.reset_epoch, first.reset_epoch + 2);
  EXPECT_EQ(reset_twice.simulation_step, 0U);
  EXPECT_EQ(unchanged.reset_epoch, reset_twice.reset_epoch);
  EXPECT_EQ(unchanged.simulation_step, reset_twice.simulation_step);
}

TEST_F(AtomicEvidenceTest, ClassifiesLeftRightAndOtherContactsWithIdsAndAggregates)
{
  place_free_body("left_joint", -.045, 0, .08);
  place_free_body("right_joint", .045, 0, .08);
  mj_forward(model_.get(), data_.get());
  const auto message = builder_.build(model_.get(), data_.get(), false, state_);
  ASSERT_TRUE(message.has_contact);
  EXPECT_FALSE(message.left_fingertip_contacts.empty());
  EXPECT_FALSE(message.right_fingertip_contacts.empty());
  EXPECT_LE(message.minimum_signed_distance_m, 0.0);
  EXPECT_GE(message.maximum_normal_force_n, 0.0);
  double observed_minimum = std::numeric_limits<double>::infinity();
  double observed_maximum_force = 0.0;
  for (const auto * contacts :
       {&message.left_fingertip_contacts, &message.right_fingertip_contacts}) {
    for (const auto & contact : *contacts) {
      EXPECT_GE(contact.body1_id, 0);
      EXPECT_GE(contact.geom1_id, 0);
      EXPECT_GE(contact.body2_id, 0);
      EXPECT_GE(contact.geom2_id, 0);
      EXPECT_FALSE(contact.body1.empty());
      EXPECT_FALSE(contact.geom1.empty());
      EXPECT_FALSE(contact.body2.empty());
      EXPECT_FALSE(contact.geom2.empty());
      EXPECT_EQ(contact.body1, mj_id2name(model_.get(), mjOBJ_BODY, contact.body1_id));
      EXPECT_EQ(contact.geom1, mj_id2name(model_.get(), mjOBJ_GEOM, contact.geom1_id));
      EXPECT_EQ(contact.body2, mj_id2name(model_.get(), mjOBJ_BODY, contact.body2_id));
      EXPECT_EQ(contact.geom2, mj_id2name(model_.get(), mjOBJ_GEOM, contact.geom2_id));
      EXPECT_GE(contact.normal_force_n, 0.0);
      EXPECT_TRUE(std::isfinite(contact.signed_distance_m));
      EXPECT_TRUE(std::isfinite(contact.position_world.x));
      EXPECT_TRUE(std::isfinite(contact.normal_world.x));
      observed_minimum = std::min(observed_minimum, contact.signed_distance_m);
      observed_maximum_force = std::max(observed_maximum_force, contact.normal_force_n);
    }
  }
  EXPECT_DOUBLE_EQ(message.minimum_signed_distance_m, observed_minimum);
  EXPECT_DOUBLE_EQ(message.maximum_normal_force_n, observed_maximum_force);
}

TEST(SimulationEvidencePluginContactSets,
     ClassifiesEveryConfiguredFingertipGeomWithoutAggregateCollision)
{
  const auto xml_path =
    std::filesystem::temp_directory_path() / "so101_atomic_evidence_contact_sets.xml";
  std::ofstream(xml_path) << R"(<mujoco><option gravity="0 0 0"/>
    <worldbody>
      <body name="cup"><freejoint name="cup_joint"/>
        <geom name="cup_geom" type="sphere" size=".02" mass=".02"/>
      </body>
      <body name="left"><freejoint name="left_joint"/>
        <geom name="left_a" type="sphere" pos="-.04 0 0" size=".02" mass=".01"/>
        <geom name="left_b" type="sphere" pos=".04 0 0" size=".02" mass=".01"/>
      </body>
      <body name="right"><freejoint name="right_joint"/>
        <geom name="right_a" type="sphere" pos="-.04 0 0" size=".02" mass=".01"/>
        <geom name="right_b" type="sphere" pos=".04 0 0" size=".02" mass=".01"/>
      </body>
    </worldbody></mujoco>)";
  char error[1024]{};
  std::unique_ptr<mjModel, ModelDeleter> model(
    mj_loadXML(xml_path.c_str(), nullptr, error, sizeof(error)));
  ASSERT_NE(model, nullptr) << error;
  std::unique_ptr<mjData, DataDeleter> data(mj_makeData(model.get()));
  ASSERT_NE(data, nullptr);
  EvidenceBuilder builder;
  ASSERT_TRUE(builder.configure(model.get(), "cup", std::vector<std::string>{"left_a", "left_b"},
                                std::vector<std::string>{"right_a", "right_b"}, {}, 32));

  EvidenceState state;
  state.simulation_session_id = "contact-set-test";
  const int left_address = model->jnt_qposadr[mj_name2id(model.get(), mjOBJ_JOINT, "left_joint")];
  const int right_address = model->jnt_qposadr[mj_name2id(model.get(), mjOBJ_JOINT, "right_joint")];
  data->qpos[left_address] = 0.04;
  data->qpos[left_address + 3] = 1.0;
  data->qpos[right_address] = -0.04;
  data->qpos[right_address + 3] = 1.0;
  mj_forward(model.get(), data.get());

  const auto first = builder.build(model.get(), data.get(), false, state);
  ASSERT_FALSE(first.left_fingertip_contacts.empty());
  ASSERT_FALSE(first.right_fingertip_contacts.empty());
  EXPECT_EQ(first.left_fingertip_contacts.front().geom2, "left_a");
  EXPECT_EQ(first.right_fingertip_contacts.front().geom2, "right_b");

  data->qpos[left_address] = -0.04;
  data->qpos[right_address] = 0.04;
  mj_forward(model.get(), data.get());
  const auto second = builder.build(model.get(), data.get(), false, state);
  ASSERT_FALSE(second.left_fingertip_contacts.empty());
  ASSERT_FALSE(second.right_fingertip_contacts.empty());
  EXPECT_EQ(second.left_fingertip_contacts.front().geom2, "left_b");
  EXPECT_EQ(second.right_fingertip_contacts.front().geom2, "right_a");
}

TEST_F(AtomicEvidenceTest, MarksPausedAndTruncatesBoundedContacts)
{
  mj_forward(model_.get(), data_.get());
  const auto running = builder_.build(model_.get(), data_.get(), false, state_);
  const auto paused = builder_.build(model_.get(), data_.get(), true, state_);
  EXPECT_TRUE(paused.paused);
  EXPECT_EQ(paused.publisher_sequence, 1U);
  EXPECT_EQ(paused.simulation_step, running.simulation_step);
}

TEST_F(AtomicEvidenceTest, PluginPublishesAuthoritativePausedResetOnlyFromSnapshotHook)
{
  if (!rclcpp::ok())
    rclcpp::init(0, nullptr);
  const auto topic = "/test/so101/authoritative_pause";
  auto options = rclcpp::NodeOptions().parameter_overrides({
    rclcpp::Parameter("object_body", "cup"),
    rclcpp::Parameter("left_fingertip_geoms", std::vector<std::string>{"left_tip"}),
    rclcpp::Parameter("right_fingertip_geoms", std::vector<std::string>{"right_tip"}),
    rclcpp::Parameter("other_contact_geoms", std::vector<std::string>{"table"}),
    rclcpp::Parameter("simulation_session_id", "pause-test"),
    rclcpp::Parameter("publish_rate", 100.0),
    rclcpp::Parameter("topic", topic),
  });
  auto plugin_node = std::make_shared<rclcpp::Node>("authoritative_pause_plugin", options);
  auto observer_node = std::make_shared<rclcpp::Node>("authoritative_pause_observer");
  std::vector<SimulationEvidence> messages;
  const auto subscription = observer_node->create_subscription<SimulationEvidence>(
    topic, rclcpp::SensorDataQoS(),
    [&messages](const SimulationEvidence & message) { messages.push_back(message); });
  (void)subscription;
  SimulationEvidencePlugin plugin;
  ASSERT_TRUE(plugin.init(plugin_node, model_.get(), data_.get()));
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(plugin_node);
  executor.add_node(observer_node);

  const auto spin_until = [&executor, &messages](std::size_t expected) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (messages.size() < expected && std::chrono::steady_clock::now() < deadline) {
      executor.spin_some();
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  };

  plugin.on_pause(false);
  plugin.update(model_.get(), data_.get());
  spin_until(1);
  ASSERT_EQ(messages.size(), 1U);
  EXPECT_FALSE(messages.back().paused);
  EXPECT_EQ(messages.back().reset_epoch, 0U);

  plugin.on_pause(true);
  plugin.on_reset();
  data_->time = 0.001;
  plugin.update(model_.get(), data_.get());
  executor.spin_some();
  ASSERT_EQ(messages.size(), 1U) << "running update must retain pending reset generation";
  plugin.on_state_snapshot(model_.get(), data_.get(), true);
  spin_until(2);
  ASSERT_EQ(messages.size(), 2U) << "paused snapshot must bypass the ordinary rate gate";
  EXPECT_TRUE(messages.back().paused);
  EXPECT_EQ(messages.back().reset_epoch, 1U);
  EXPECT_EQ(messages.back().simulation_step, 0U);

  plugin.on_pause(false);
  data_->time = 0.002;
  plugin.update(model_.get(), data_.get());
  executor.spin_some();
  EXPECT_EQ(messages.size(), 2U) << "ordinary updates remain rate limited";

  data_->time = 0.02;
  plugin.update(model_.get(), data_.get());
  spin_until(3);
  ASSERT_EQ(messages.size(), 3U);
  EXPECT_FALSE(messages.back().paused);
  plugin.cleanup();
  executor.remove_node(observer_node);
  executor.remove_node(plugin_node);
  rclcpp::shutdown();
}

TEST_F(AtomicEvidenceTest,
       RunningUpdateRetainsPendingGenerationUntilPausedSnapshotPublishesStepZero)
{
  if (!rclcpp::ok())
    rclcpp::init(0, nullptr);
  const auto topic = "/test/so101/pending_until_snapshot";
  auto options = rclcpp::NodeOptions().parameter_overrides({
    rclcpp::Parameter("object_body", "cup"),
    rclcpp::Parameter("left_fingertip_geom", "left_tip"),
    rclcpp::Parameter("right_fingertip_geom", "right_tip"),
    rclcpp::Parameter("other_contact_geoms", std::vector<std::string>{"table"}),
    rclcpp::Parameter("simulation_session_id", "snapshot-test"),
    rclcpp::Parameter("publish_rate", 100.0),
    rclcpp::Parameter("topic", topic),
  });
  auto plugin_node = std::make_shared<rclcpp::Node>("pending_snapshot_plugin", options);
  auto observer_node = std::make_shared<rclcpp::Node>("pending_snapshot_observer");
  std::vector<SimulationEvidence> messages;
  const auto subscription = observer_node->create_subscription<SimulationEvidence>(
    topic, rclcpp::SensorDataQoS(),
    [&messages](const SimulationEvidence & message) { messages.push_back(message); });
  (void)subscription;
  SimulationEvidencePlugin plugin;
  ASSERT_TRUE(plugin.init(plugin_node, model_.get(), data_.get()));
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(plugin_node);
  executor.add_node(observer_node);
  const auto spin_until = [&executor, &messages](std::size_t expected) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (messages.size() < expected && std::chrono::steady_clock::now() < deadline) {
      executor.spin_some();
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  };

  plugin.on_pause(false);
  plugin.update(model_.get(), data_.get());
  spin_until(1);
  ASSERT_EQ(messages.size(), 1U);
  plugin.on_reset();
  data_->time = 0.001;
  plugin.update(model_.get(), data_.get());
  executor.spin_some();
  EXPECT_EQ(messages.size(), 1U) << "running update must not expose or consume pending epoch";

  const std::vector<mjtNum> qpos(data_->qpos, data_->qpos + model_->nq);
  const std::vector<mjtNum> qvel(data_->qvel, data_->qvel + model_->nv);
  const std::vector<mjtNum> ctrl(data_->ctrl, data_->ctrl + model_->nu);
  const std::vector<mjtNum> xfrc(data_->xfrc_applied, data_->xfrc_applied + 6 * model_->nbody);
  plugin.on_pause(true);
  plugin.on_state_snapshot(model_.get(), data_.get(), true);
  spin_until(2);
  ASSERT_EQ(messages.size(), 2U);
  EXPECT_EQ(messages.back().reset_epoch, 1U);
  EXPECT_EQ(messages.back().simulation_step, 0U);
  EXPECT_TRUE(messages.back().paused);
  EXPECT_EQ(std::vector<mjtNum>(data_->qpos, data_->qpos + model_->nq), qpos);
  EXPECT_EQ(std::vector<mjtNum>(data_->qvel, data_->qvel + model_->nv), qvel);
  EXPECT_EQ(std::vector<mjtNum>(data_->ctrl, data_->ctrl + model_->nu), ctrl);
  EXPECT_EQ(std::vector<mjtNum>(data_->xfrc_applied, data_->xfrc_applied + 6 * model_->nbody),
            xfrc);

  plugin.cleanup();
  executor.remove_node(observer_node);
  executor.remove_node(plugin_node);
  rclcpp::shutdown();
}

TEST_F(AtomicEvidenceTest, SnapshotPublisherContentionKeepsGenerationPendingForIdempotentRetry)
{
  if (!rclcpp::ok())
    rclcpp::init(0, nullptr);
  const auto topic = "/test/so101/snapshot_contention";
  auto options = rclcpp::NodeOptions().parameter_overrides({
    rclcpp::Parameter("object_body", "cup"),
    rclcpp::Parameter("left_fingertip_geom", "left_tip"),
    rclcpp::Parameter("right_fingertip_geom", "right_tip"),
    rclcpp::Parameter("other_contact_geoms", std::vector<std::string>{"table"}),
    rclcpp::Parameter("simulation_session_id", "contention-test"),
    rclcpp::Parameter("publish_rate", 100.0),
    rclcpp::Parameter("topic", topic),
  });
  auto plugin_node = std::make_shared<rclcpp::Node>("snapshot_contention_plugin", options);
  auto observer_node = std::make_shared<rclcpp::Node>("snapshot_contention_observer");
  std::vector<SimulationEvidence> messages;
  const auto subscription = observer_node->create_subscription<SimulationEvidence>(
    topic, rclcpp::SensorDataQoS(),
    [&messages](const SimulationEvidence & message) { messages.push_back(message); });
  (void)subscription;
  SimulationEvidencePlugin plugin;
  ASSERT_TRUE(plugin.init(plugin_node, model_.get(), data_.get()));
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(plugin_node);
  executor.add_node(observer_node);

  plugin.on_reset();
  plugin.on_pause(true);
  ASSERT_TRUE(plugin.realtime_publisher_->trylock());
  plugin.on_state_snapshot(model_.get(), data_.get(), true);
  plugin.realtime_publisher_->unlock();
  executor.spin_some();
  EXPECT_TRUE(messages.empty()) << "contended snapshot must not publish or consume generation";

  plugin.on_state_snapshot(model_.get(), data_.get(), true);
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (messages.empty() && std::chrono::steady_clock::now() < deadline) {
    executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  ASSERT_EQ(messages.size(), 1U);
  EXPECT_EQ(messages.back().reset_epoch, 1U);
  EXPECT_EQ(messages.back().simulation_step, 0U);
  EXPECT_TRUE(messages.back().paused);

  data_->time = 0.001;
  plugin.update(model_.get(), data_.get());
  executor.spin_some();
  EXPECT_EQ(messages.size(), 1U) << "no-pending ordinary update must keep the existing cadence";
  plugin.cleanup();
  executor.remove_node(observer_node);
  executor.remove_node(plugin_node);
  rclcpp::shutdown();
}

TEST_F(AtomicEvidenceTest, SeparatesOtherObjectContactAndHonorsGlobalBound)
{
  place_free_body("cup_joint", 0, 0, .04);
  place_free_body("left_joint", -.3, 0, .2);
  place_free_body("right_joint", .3, 0, .2);
  mj_forward(model_.get(), data_.get());
  const auto table_contact = builder_.build(model_.get(), data_.get(), false, state_);
  ASSERT_FALSE(table_contact.other_object_contacts.empty());
  EXPECT_EQ(table_contact.other_object_contacts.front().geom2, "table");

  EvidenceBuilder bounded;
  ASSERT_TRUE(bounded.configure(model_.get(), "cup", "left_tip", "right_tip", {"table"}, 0));
  EvidenceState bounded_state;
  bounded_state.simulation_session_id = "bounded";
  const auto truncated = bounded.build(model_.get(), data_.get(), false, bounded_state);
  EXPECT_TRUE(truncated.truncated);
  EXPECT_TRUE(truncated.other_object_contacts.empty());
}
}  // namespace
