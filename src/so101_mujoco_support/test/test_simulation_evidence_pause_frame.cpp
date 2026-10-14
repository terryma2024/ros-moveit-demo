// Copyright 2026 SO-101 maintainers

// The authoritative paused frame is published once, from the pause/reset snapshot hook. If that single attempt finds
// the realtime publisher busy it used to be lost for good: the controller-cycle update only retried a frame while
// `published_` was false, and `published_` is already true from the last running frame. A reset transaction that waits
// for a paused frame then fails with "final transaction evidence is not paused". These tests make the first attempt
// fail on purpose and require the frame to be published afterwards, exactly once, with unchanged content.

#include <gtest/gtest.h>
#include <mujoco/mujoco.h>

#include <chrono>
#include <filesystem>
#include <fstream>
#include <memory>
#include <string>
#include <thread>
#include <vector>

#define private public
#include "so101_mujoco_support/simulation_evidence_plugin.hpp"
#undef private

namespace
{
using so101_mujoco_support::SimulationEvidencePlugin;
using so101_mujoco_support::msg::SceneStateEvidence;
using so101_mujoco_support::msg::SimulationEvidence;

struct ModelDeleter
{
  void operator()(mjModel * value) const {mj_deleteModel(value);}
};
struct DataDeleter
{
  void operator()(mjData * value) const {mj_deleteData(value);}
};

class PauseFrameTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    const auto xml_path = std::filesystem::temp_directory_path() / "so101_pause_frame.xml";
    std::ofstream(xml_path) <<
      R"(<mujoco><option timestep="0.001" gravity="0 0 -9.81"/>
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
    if (!rclcpp::ok()) {
      rclcpp::init(0, nullptr);
    }
  }

  void TearDown() override
  {
    if (plugin_) {plugin_->cleanup();}
    if (executor_) {
      executor_->remove_node(observer_node_);
      executor_->remove_node(plugin_node_);
    }
    rclcpp::shutdown();
  }

  void start(const std::string & name, bool with_scene)
  {
    const std::string topic = "/test/so101/" + name + "/evidence";
    std::vector<rclcpp::Parameter> parameters{
      rclcpp::Parameter("object_body", "cup"),
      rclcpp::Parameter("left_fingertip_geoms", std::vector<std::string>{"left_tip"}),
      rclcpp::Parameter("right_fingertip_geoms", std::vector<std::string>{"right_tip"}),
      rclcpp::Parameter("other_contact_geoms", std::vector<std::string>{"table"}),
      rclcpp::Parameter("simulation_session_id", name),
      rclcpp::Parameter("publish_rate", 100.0),
      rclcpp::Parameter("topic", topic)};
    if (with_scene) {
      parameters.emplace_back("robot_contact_roots", std::vector<std::string>{"left"});
    }
    plugin_node_ = std::make_shared<rclcpp::Node>(
      name + "_plugin", rclcpp::NodeOptions().parameter_overrides(parameters));
    observer_node_ = std::make_shared<rclcpp::Node>(name + "_observer");
    evidence_subscription_ = observer_node_->create_subscription<SimulationEvidence>(
      topic, rclcpp::SensorDataQoS(),
      [this](const SimulationEvidence & message) {evidence_.push_back(message);});
    if (with_scene) {
      scene_subscription_ = observer_node_->create_subscription<SceneStateEvidence>(
        "/so101/simulation/scene_state",
        rclcpp::QoS(rclcpp::KeepLast(1)).reliable().transient_local(),
        [this](const SceneStateEvidence & message) {scene_.push_back(message);});
    }
    plugin_ = std::make_unique<SimulationEvidencePlugin>();
    ASSERT_TRUE(plugin_->init(plugin_node_, model_.get(), data_.get()));
    executor_ = std::make_unique<rclcpp::executors::SingleThreadedExecutor>();
    executor_->add_node(plugin_node_);
    executor_->add_node(observer_node_);
  }

  /// Spins until `count` evidence messages arrived or the time ran out.
  void spin_for_evidence(
    std::size_t count, std::chrono::milliseconds limit = std::chrono::milliseconds(1500))
  {
    const auto deadline = std::chrono::steady_clock::now() + limit;
    while (evidence_.size() < count && std::chrono::steady_clock::now() < deadline) {
      executor_->spin_some();
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }

  /// Gives a message that must NOT appear the time to appear.
  void settle(std::chrono::milliseconds duration = std::chrono::milliseconds(150))
  {
    const auto deadline = std::chrono::steady_clock::now() + duration;
    while (std::chrono::steady_clock::now() < deadline) {
      executor_->spin_some();
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
  }

  void publish_running_frame()
  {
    plugin_->on_pause(false);
    plugin_->update(model_.get(), data_.get());
    spin_for_evidence(1);
    ASSERT_EQ(evidence_.size(), 1U);
    ASSERT_FALSE(evidence_.back().paused);
  }

  /// The pause service's snapshot while the realtime publisher is busy: the frame cannot be published.
  void paused_snapshot_while_publisher_is_busy()
  {
    plugin_->on_pause(true);
    ASSERT_TRUE(plugin_->realtime_publisher_->trylock());
    plugin_->on_state_snapshot(model_.get(), data_.get(), true);
    plugin_->realtime_publisher_->unlock();
    settle(kShort);
  }

  void controller_cycles(int count)
  {
    for (int i = 0; i < count; ++i) {
      plugin_->update(model_.get(), data_.get());
      executor_->spin_some();
      std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
  }

  const std::chrono::milliseconds kShort{50};
  std::unique_ptr<mjModel, ModelDeleter> model_;
  std::unique_ptr<mjData, DataDeleter> data_;
  rclcpp::Node::SharedPtr plugin_node_;
  rclcpp::Node::SharedPtr observer_node_;
  std::unique_ptr<SimulationEvidencePlugin> plugin_;
  std::unique_ptr<rclcpp::executors::SingleThreadedExecutor> executor_;
  rclcpp::Subscription<SimulationEvidence>::SharedPtr evidence_subscription_;
  rclcpp::Subscription<SceneStateEvidence>::SharedPtr scene_subscription_;
  std::vector<SimulationEvidence> evidence_;
  std::vector<SceneStateEvidence> scene_;
};
}  // namespace

TEST_F(PauseFrameTest,
       PausedFrameAtTheSameTimeAsTheLastRunningFrameIsRetriedAndPublishedExactlyOnce)
{
  start("pause_same_time", false);
  publish_running_frame();
  paused_snapshot_while_publisher_is_busy();
  ASSERT_EQ(evidence_.size(), 1U) << "the busy snapshot must not have published";

  controller_cycles(5);
  spin_for_evidence(2);
  ASSERT_EQ(evidence_.size(), 2U) << "the paused frame must be retried by the controller cycle";
  EXPECT_TRUE(evidence_.back().paused);
  EXPECT_EQ(evidence_.back().publisher_sequence, 1U) << "no sequence number is skipped or reused";
  EXPECT_EQ(evidence_.back().reset_epoch, 0U);

  controller_cycles(10);
  settle();
  EXPECT_EQ(evidence_.size(), 2U) << "once published the paused frame is not published again";
}

TEST_F(PauseFrameTest, PausedFrameInTheSameGridCellAsTheLastRunningFrameIsRetriedWithItsOwnContent)
{
  start("pause_same_cell", false);
  publish_running_frame();
  data_->time = 0.003;  // three steps later, still inside the 10 ms publish cell of the running frame
  plugin_->update(model_.get(), data_.get());
  settle(kShort);
  ASSERT_EQ(evidence_.size(), 1U) << "ordinary updates stay rate limited";
  paused_snapshot_while_publisher_is_busy();
  ASSERT_EQ(evidence_.size(), 1U);

  controller_cycles(5);
  spin_for_evidence(2);
  ASSERT_EQ(evidence_.size(), 2U);
  EXPECT_TRUE(evidence_.back().paused);
  EXPECT_EQ(evidence_.back().simulation_step, 3U)
    << "same content as an uncontended snapshot would carry";
  EXPECT_EQ(evidence_.back().header.stamp.nanosec, 3000000U);
  EXPECT_EQ(evidence_.back().publisher_sequence, 1U);

  controller_cycles(10);
  settle();
  EXPECT_EQ(evidence_.size(), 2U);
}

TEST_F(PauseFrameTest, ARetriedFrameStillConsumesThePendingResetGeneration)
{
  start("pause_reset", false);
  publish_running_frame();
  plugin_->on_reset();
  paused_snapshot_while_publisher_is_busy();
  ASSERT_EQ(evidence_.size(), 1U);
  ASSERT_EQ(plugin_->physics_state_.consumed_reset_generation, 0U)
    << "the failed attempt consumed nothing";

  controller_cycles(5);
  spin_for_evidence(2);
  ASSERT_EQ(evidence_.size(), 2U);
  EXPECT_TRUE(evidence_.back().paused);
  EXPECT_EQ(evidence_.back().reset_epoch, 1U);
  EXPECT_EQ(evidence_.back().simulation_step, 0U);
  EXPECT_EQ(plugin_->physics_state_.consumed_reset_generation, 1U);
  EXPECT_EQ(plugin_->physics_state_.reset_epoch, 1U);
  controller_cycles(5);
  settle();
  EXPECT_EQ(evidence_.size(), 2U);
}

TEST_F(PauseFrameTest, ResumingBeforeTheRetryDropsTheStalePausedFrame)
{
  start("pause_resume", false);
  publish_running_frame();
  paused_snapshot_while_publisher_is_busy();
  plugin_->on_pause(false);
  data_->time = 0.02;
  controller_cycles(3);
  spin_for_evidence(2);
  ASSERT_EQ(evidence_.size(), 2U);
  EXPECT_FALSE(evidence_.back().paused)
    << "the running stream carries on; no stale paused frame follows it";
  controller_cycles(5);
  settle();
  for (const auto & message : evidence_) {
    EXPECT_FALSE(message.paused);
  }
}

TEST_F(PauseFrameTest, APausedSceneStateFrameThatFoundItsPublisherBusyIsRetriedExactlyOnce)
{
  start("pause_scene", true);
  publish_running_frame();
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (scene_.empty() && std::chrono::steady_clock::now() < deadline) {
    executor_->spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  ASSERT_EQ(scene_.size(), 1U);
  ASSERT_FALSE(scene_.back().paused);

  plugin_->on_pause(true);
  ASSERT_TRUE(plugin_->realtime_scene_publisher_->trylock());
  plugin_->on_state_snapshot(model_.get(), data_.get(), true);
  plugin_->realtime_scene_publisher_->unlock();
  spin_for_evidence(2);
  ASSERT_EQ(evidence_.size(), 2U) << "the evidence frame itself was not blocked";
  settle(kShort);
  ASSERT_EQ(scene_.size(), 1U) << "the busy scene publisher dropped the paused scene frame";

  controller_cycles(5);
  settle();
  ASSERT_EQ(scene_.size(), 2U) << "the paused scene frame must be retried";
  EXPECT_TRUE(scene_.back().paused);
  EXPECT_EQ(scene_.back().simulation_step, evidence_.back().simulation_step);
  EXPECT_EQ(scene_.back().reset_epoch, evidence_.back().reset_epoch);
  EXPECT_EQ(evidence_.size(), 2U) << "the evidence frame is not published again for a scene retry";
  controller_cycles(10);
  settle();
  EXPECT_EQ(scene_.size(), 2U);
  EXPECT_EQ(evidence_.size(), 2U);
}
