// Copyright 2026 SO-101 maintainers

#include <gtest/gtest.h>
#include <mujoco/mujoco.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <atomic>
#include <limits>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <type_traits>
#include <vector>

#include <mujoco_ros2_control_plugins/mujoco_ros2_control_plugin_capabilities.hpp>

#define private public
#include "so101_mujoco_support/simulation_evidence_plugin.hpp"
#undef private

static_assert(std::is_base_of_v<
  mujoco_ros2_control_plugins::MuJoCoROS2ControlSimulationObserver,
  so101_mujoco_support::SimulationEvidencePlugin>);

namespace
{
using so101_mujoco_support::EvidenceBuilder;
using so101_mujoco_support::EvidenceState;
using so101_mujoco_support::PhysicsStepEvidenceBuffer;
using so101_mujoco_support::SimulationEvidencePlugin;
using so101_mujoco_support::StampingChunkPublisher;
using so101_mujoco_support::make_physics_step_evidence;
using so101_mujoco_support::make_cancellation_ack;
using so101_mujoco_support::msg::ContactSample;
using so101_mujoco_support::msg::PhysicsStepEvidence;
using so101_mujoco_support::msg::PhysicsStepEvidenceChunk;
using so101_mujoco_support::msg::PhysicsStepFenceAck;
using so101_mujoco_support::msg::PhysicsStepFenceRequest;
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
    std::ofstream(xml_path) <<
      R"(<mujoco><option timestep="0.001" gravity="0 0 -9.81"/>
      <worldbody><geom name="table" type="plane" size="1 1 .1"/>
      <body name="cup" pos="0 0 .08"><freejoint name="cup_joint"/><geom name="cup_geom" type="sphere" size=".05" mass=".1"/></body>
      <body name="left"><freejoint name="left_joint"/><geom name="left_tip" type="sphere" size=".02" mass=".1"/></body>
      <body name="right"><freejoint name="right_joint"/><geom name="right_tip" type="sphere" size=".02" mass=".1"/></body>
      <body name="mast" pos=".7 .2 .2"><freejoint name="mast_joint"/><geom name="mast_geom" type="sphere" size=".02" mass=".1"/></body>
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

TEST_F(AtomicEvidenceTest, PhysicsStepPoseMatchesPostIntegrationFreeJointState)
{
  place_free_body("cup_joint", 0, 0, .2);
  place_free_body("left_joint", -.3, 0, .2);
  place_free_body("right_joint", .3, 0, .2);
  mj_forward(model_.get(), data_.get());
  const int cup_joint = mj_name2id(model_.get(), mjOBJ_JOINT, "cup_joint");
  const int cup_body = mj_name2id(model_.get(), mjOBJ_BODY, "cup");
  const int address = model_->jnt_qposadr[cup_joint];
  mj_step(model_.get(), data_.get());
  ASSERT_GT(std::abs(data_->qpos[address + 2] - data_->xpos[3 * cup_body + 2]), 1e-8)
    << "this test must exercise MuJoCo's post-step derived-state lag";

  const auto step = builder_.build_step(model_.get(), data_.get(), false, state_, 0, 1.0, 10.0);
  ASSERT_EQ(step.model_qpos.size(), static_cast<std::size_t>(model_->nq));
  EXPECT_DOUBLE_EQ(step.object_pose_world.position.x, step.model_qpos[address]);
  EXPECT_DOUBLE_EQ(step.object_pose_world.position.y, step.model_qpos[address + 1]);
  EXPECT_DOUBLE_EQ(step.object_pose_world.position.z, step.model_qpos[address + 2]);
  EXPECT_DOUBLE_EQ(step.object_pose_world.orientation.w, step.model_qpos[address + 3]);
  EXPECT_DOUBLE_EQ(step.object_pose_world.orientation.x, step.model_qpos[address + 4]);
  EXPECT_DOUBLE_EQ(step.object_pose_world.orientation.y, step.model_qpos[address + 5]);
  EXPECT_DOUBLE_EQ(step.object_pose_world.orientation.z, step.model_qpos[address + 6]);
}

TEST_F(AtomicEvidenceTest, WorldPoseAndRawStepMatchTheSamePostIntegrationConfiguration)
{
  place_free_body("cup_joint", 0, 0, .2);
  place_free_body("left_joint", -.3, 0, .2);
  place_free_body("right_joint", .3, 0, .2);
  const int joint = mj_name2id(model_.get(), mjOBJ_JOINT, "cup_joint");
  const int body = mj_name2id(model_.get(), mjOBJ_BODY, "cup");
  const int address = model_->jnt_qposadr[joint];
  const int velocity_address = model_->jnt_dofadr[joint];
  data_->qvel[velocity_address] = .2;
  data_->qvel[velocity_address + 4] = .3;
  mj_forward(model_.get(), data_.get());
  mj_step(model_.get(), data_.get());
  ASSERT_GT(std::abs(data_->qpos[address] - data_->xpos[3 * body]), 1e-8);
  ASSERT_GT(std::abs(data_->qpos[address + 5] - data_->xquat[4 * body + 2]), 1e-8);
  const std::vector<mjtNum> original_qpos(data_->qpos, data_->qpos + model_->nq);
  const std::vector<mjtNum> original_qvel(data_->qvel, data_->qvel + model_->nv);
  const std::vector<mjtNum> original_xpos(data_->xpos, data_->xpos + 3 * model_->nbody);
  const std::vector<mjtNum> original_xquat(data_->xquat, data_->xquat + 4 * model_->nbody);
  const auto world = builder_.build(model_.get(), data_.get(), false, state_);
  const auto raw = builder_.build_step(model_.get(), data_.get(), false, state_, 0, 1.0, 10.0);
  EXPECT_DOUBLE_EQ(world.object_pose_world.position.x, original_qpos[address]);
  EXPECT_DOUBLE_EQ(world.object_pose_world.position.y, original_qpos[address + 1]);
  EXPECT_DOUBLE_EQ(world.object_pose_world.position.z, original_qpos[address + 2]);
  EXPECT_DOUBLE_EQ(world.object_pose_world.orientation.w, original_qpos[address + 3]);
  EXPECT_DOUBLE_EQ(world.object_pose_world.orientation.x, original_qpos[address + 4]);
  EXPECT_DOUBLE_EQ(world.object_pose_world.orientation.y, original_qpos[address + 5]);
  EXPECT_DOUBLE_EQ(world.object_pose_world.orientation.z, original_qpos[address + 6]);
  EXPECT_EQ(world.object_pose_world, raw.object_pose_world);
  EXPECT_EQ(original_qpos, std::vector<mjtNum>(data_->qpos, data_->qpos + model_->nq));
  EXPECT_EQ(original_qvel, std::vector<mjtNum>(data_->qvel, data_->qvel + model_->nv));
  EXPECT_EQ(original_xpos, std::vector<mjtNum>(data_->xpos, data_->xpos + 3 * model_->nbody));
  EXPECT_EQ(original_xquat, std::vector<mjtNum>(data_->xquat, data_->xquat + 4 * model_->nbody));
}

TEST_F(AtomicEvidenceTest, WorldTwistMatchesForwardedPostIntegrationStateWithoutMutatingLiveData)
{
  const auto xml_path = std::filesystem::temp_directory_path() / "so101_atomic_evidence.xml";
  std::ifstream source(xml_path);
  std::string xml((std::istreambuf_iterator<char>(source)), std::istreambuf_iterator<char>());
  const auto geom_offset = xml.find("name=\"cup_geom\"");
  ASSERT_NE(geom_offset, std::string::npos);
  xml.insert(geom_offset, "pos=\".015 0 0\" ");
  const auto offset_path = std::filesystem::temp_directory_path() / "so101_offset_evidence.xml";
  std::ofstream(offset_path) << xml;
  char error[1024]{};
  model_.reset(mj_loadXML(offset_path.c_str(), nullptr, error, sizeof(error)));
  ASSERT_NE(model_, nullptr) << error;
  data_.reset(mj_makeData(model_.get()));
  ASSERT_NE(data_, nullptr);
  ASSERT_TRUE(builder_.configure(model_.get(), "cup", "left_tip", "right_tip", {"table"}, 32));
  place_free_body("cup_joint", 0, 0, .2);
  place_free_body("left_joint", -.3, 0, .2);
  place_free_body("right_joint", .3, 0, .2);
  const int joint = mj_name2id(model_.get(), mjOBJ_JOINT, "cup_joint");
  const int body = mj_name2id(model_.get(), mjOBJ_BODY, "cup");
  const int address = model_->jnt_qposadr[joint];
  const int velocity_address = model_->jnt_dofadr[joint];
  // A rotated body with a nonzero inertial offset exercises world angular
  // conversion and the original mjOBJ_BODY centre-of-mass velocity semantics.
  ASSERT_NEAR(model_->body_ipos[3 * body], .015, 1e-12);
  data_->qpos[address + 3] = std::sqrt(.5);
  data_->qpos[address + 6] = std::sqrt(.5);
  data_->qvel[velocity_address] = .2;
  data_->qvel[velocity_address + 4] = .3;
  mj_forward(model_.get(), data_.get());
  mj_step(model_.get(), data_.get());
  std::unique_ptr<mjData, DataDeleter> independent(mj_makeData(model_.get()));
  ASSERT_NE(independent, nullptr);
  mj_copyData(independent.get(), model_.get(), data_.get());
  mj_forward(model_.get(), independent.get());
  mjtNum expected[6]{};
  mj_objectVelocity(model_.get(), independent.get(), mjOBJ_BODY, body, expected, 0);
  mjtNum body_origin[6]{};
  mj_objectVelocity(model_.get(), independent.get(), mjOBJ_XBODY, body, body_origin, 0);
  ASSERT_GT(std::abs(expected[5] - body_origin[5]), .001)
    << "the fixture must exercise the nonzero COM rotational velocity correction";
  mjtNum cached[6]{};
  mj_objectVelocity(model_.get(), data_.get(), mjOBJ_BODY, body, cached, 0);
  ASSERT_GT(std::abs(expected[5] - cached[5]), 1e-8);
  const std::vector<mjtNum> original_qpos(data_->qpos, data_->qpos + model_->nq);
  const std::vector<mjtNum> original_qvel(data_->qvel, data_->qvel + model_->nv);
  const std::vector<mjtNum> original_cvel(data_->cvel, data_->cvel + 6 * model_->nbody);
  const auto world = builder_.build(model_.get(), data_.get(), false, state_);
  const auto raw = builder_.build_step(model_.get(), data_.get(), false, state_, 0, 1.0, 10.0);
  EXPECT_NEAR(world.object_twist_world.angular.x, expected[0], 1e-12);
  EXPECT_NEAR(world.object_twist_world.angular.y, expected[1], 1e-12);
  EXPECT_NEAR(world.object_twist_world.angular.z, expected[2], 1e-12);
  EXPECT_NEAR(world.object_twist_world.linear.x, expected[3], 1e-12);
  EXPECT_NEAR(world.object_twist_world.linear.y, expected[4], 1e-12);
  EXPECT_NEAR(world.object_twist_world.linear.z, expected[5], 1e-12);
  EXPECT_EQ(world.object_twist_world, raw.object_twist_world);
  EXPECT_EQ(original_qpos, std::vector<mjtNum>(data_->qpos, data_->qpos + model_->nq));
  EXPECT_EQ(original_qvel, std::vector<mjtNum>(data_->qvel, data_->qvel + model_->nv));
  EXPECT_EQ(original_cvel, std::vector<mjtNum>(data_->cvel, data_->cvel + 6 * model_->nbody));
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

TEST(CancellationEvidenceTest, AckUsesPluginPhysicsStepAsConservativeRequestUpperBound)
{
  so101_mujoco_support::msg::PhysicsCancellationRequest request;
  request.simulation_session_id = "session-a";
  request.reset_epoch = 4;
  request.hazard_physics_step = 100;
  request.request_sequence = 7;

  const auto ack = make_cancellation_ack(request, 4, 123, 0.246);

  EXPECT_EQ(ack.simulation_session_id, "session-a");
  EXPECT_EQ(ack.reset_epoch, 4U);
  EXPECT_EQ(ack.hazard_physics_step, 100U);
  EXPECT_EQ(ack.request_sequence, 7U);
  EXPECT_EQ(ack.observed_physics_step, 123U);
  EXPECT_DOUBLE_EQ(ack.observed_simulation_time_s, 0.246);
  EXPECT_EQ(ack.observed_physics_step - ack.hazard_physics_step, 23U);
}

TEST(SimulationEvidencePluginParameterScopeTest,
     SubNodeTypedLookupUsesSlashScopedOverrideWhilePluginLookupReadsRoot)
{
  if (!rclcpp::ok()) {
    rclcpp::init(0, nullptr);
  }
  auto root_only_options = rclcpp::NodeOptions()
    .parameter_overrides({rclcpp::Parameter("simulation_session_id", "root-session")})
    .automatically_declare_parameters_from_overrides(true);
  auto root_only = std::make_shared<rclcpp::Node>("root_only_session", root_only_options);
  auto root_only_plugin = root_only->create_sub_node("simulation_evidence");
  std::string resolved;
  EXPECT_EQ(root_only_plugin->get_sub_namespace(), "simulation_evidence");
  EXPECT_FALSE(root_only_plugin->get_parameter("simulation_session_id", resolved));
  ASSERT_TRUE(root_only_plugin->has_parameter("simulation_session_id"));
  EXPECT_EQ(
    root_only_plugin->get_parameter("simulation_session_id").as_string(), "root-session");

  auto scoped_options = rclcpp::NodeOptions()
    .parameter_overrides({
      rclcpp::Parameter("simulation_session_id", "root-session"),
      rclcpp::Parameter("simulation_evidence/simulation_session_id", "plugin-session"),
    })
    .automatically_declare_parameters_from_overrides(true);
  auto scoped = std::make_shared<rclcpp::Node>("scoped_session", scoped_options);
  auto scoped_plugin = scoped->create_sub_node("simulation_evidence");
  ASSERT_TRUE(scoped_plugin->get_parameter("simulation_session_id", resolved));
  EXPECT_EQ(resolved, "plugin-session");
  rclcpp::shutdown();
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
    {&message.left_fingertip_contacts, &message.right_fingertip_contacts})
  {
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

TEST_F(AtomicEvidenceTest, CopiedContactSnapshotWithoutSolverForcesFailsClosed)
{
  place_free_body("left_joint", -.045, 0, .08);
  place_free_body("right_joint", .045, 0, .08);
  mj_forward(model_.get(), data_.get());
  ASSERT_GT(data_->ncon, 0);

  std::unique_ptr<mjData, DataDeleter> snapshot(mj_makeData(model_.get()));
  ASSERT_NE(snapshot, nullptr);
  ASSERT_NE(mj_copyData(snapshot.get(), model_.get(), data_.get()), nullptr);
  ASSERT_GT(snapshot->ncon, 0);

  auto * solver_forces = snapshot->efc_force;
  ASSERT_GT(snapshot->nefc, 0);
  ASSERT_NE(solver_forces, nullptr);
  snapshot->efc_force = nullptr;
  const auto message = builder_.build(model_.get(), snapshot.get(), false, state_);
  snapshot->efc_force = solver_forces;

  EXPECT_TRUE(message.truncated);
  EXPECT_FALSE(message.has_contact);
  EXPECT_TRUE(message.left_fingertip_contacts.empty());
  EXPECT_TRUE(message.right_fingertip_contacts.empty());
}

TEST(SimulationEvidencePluginContactSets,
     ClassifiesEveryConfiguredFingertipGeomWithoutAggregateCollision)
{
  const auto xml_path =
    std::filesystem::temp_directory_path() / "so101_atomic_evidence_contact_sets.xml";
  std::ofstream(xml_path) <<
      R"(<mujoco><option gravity="0 0 0"/>
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
  if (!rclcpp::ok()) {
    rclcpp::init(0, nullptr);
  }
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
    [&messages](const SimulationEvidence & message) {messages.push_back(message);});
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

TEST_F(AtomicEvidenceTest, LateJoiningObserverReceivesLatestAuthoritativePausedSnapshot)
{
  if (!rclcpp::ok()) {
    rclcpp::init(0, nullptr);
  }
  const auto topic = "/test/so101/late_join_paused_snapshot";
  auto options = rclcpp::NodeOptions().parameter_overrides({
      rclcpp::Parameter("object_body", "cup"),
      rclcpp::Parameter("left_fingertip_geoms", std::vector<std::string>{"left_tip"}),
      rclcpp::Parameter("right_fingertip_geoms", std::vector<std::string>{"right_tip"}),
      rclcpp::Parameter("other_contact_geoms", std::vector<std::string>{"table"}),
      rclcpp::Parameter("simulation_session_id", "late-join-test"),
      rclcpp::Parameter("publish_rate", 100.0),
      rclcpp::Parameter("topic", topic),
  });
  auto plugin_node = std::make_shared<rclcpp::Node>("late_join_snapshot_plugin", options);
  SimulationEvidencePlugin plugin;
  ASSERT_TRUE(plugin.init(plugin_node, model_.get(), data_.get()));

  plugin.on_pause(true);
  plugin.on_state_snapshot(model_.get(), data_.get(), true);

  auto observer_node = std::make_shared<rclcpp::Node>("late_join_snapshot_observer");
  std::vector<SimulationEvidence> messages;
  const auto qos = rclcpp::QoS(rclcpp::KeepLast(1)).reliable().transient_local();
  const auto subscription = observer_node->create_subscription<SimulationEvidence>(
    topic, qos, [&messages](const SimulationEvidence & message) {messages.push_back(message);});
  (void)subscription;
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(plugin_node);
  executor.add_node(observer_node);
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (messages.empty() && std::chrono::steady_clock::now() < deadline) {
    executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }

  ASSERT_EQ(messages.size(), 1U);
  EXPECT_TRUE(messages.back().paused);
  EXPECT_EQ(messages.back().simulation_session_id, "late-join-test");
  plugin.cleanup();
  executor.remove_node(observer_node);
  executor.remove_node(plugin_node);
  rclcpp::shutdown();
}

TEST_F(AtomicEvidenceTest,
       RunningUpdateRetainsPendingGenerationUntilPausedSnapshotPublishesStepZero)
{
  if (!rclcpp::ok()) {
    rclcpp::init(0, nullptr);
  }
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
    [&messages](const SimulationEvidence & message) {messages.push_back(message);});
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
  EXPECT_EQ(plugin.physics_state_.reset_epoch, 1U);
  EXPECT_EQ(plugin.physics_state_.consumed_reset_generation, 1U);
  EXPECT_EQ(plugin.physics_state_.simulation_step, 0U);
  EXPECT_DOUBLE_EQ(plugin.physics_state_.previous_time, 0.001);
  EXPECT_EQ(std::vector<mjtNum>(data_->qpos, data_->qpos + model_->nq), qpos);
  EXPECT_EQ(std::vector<mjtNum>(data_->qvel, data_->qvel + model_->nv), qvel);
  EXPECT_EQ(std::vector<mjtNum>(data_->ctrl, data_->ctrl + model_->nu), ctrl);
  EXPECT_EQ(std::vector<mjtNum>(data_->xfrc_applied, data_->xfrc_applied + 6 * model_->nbody),
            xfrc);

  plugin.on_pause(false);
  data_->time = 0.002;
  plugin.on_physics_step(model_.get(), data_.get());
  const auto first_post_reset_chunk = plugin.physics_step_buffer_->prepare_chunk();
  ASSERT_EQ(first_post_reset_chunk.samples.size(), 1U);
  EXPECT_EQ(first_post_reset_chunk.simulation_session_id, "snapshot-test");
  EXPECT_EQ(first_post_reset_chunk.reset_epoch, 1U);
  EXPECT_EQ(first_post_reset_chunk.first_physics_step, 1U);

  plugin.cleanup();
  executor.remove_node(observer_node);
  executor.remove_node(plugin_node);
  rclcpp::shutdown();
}

TEST_F(AtomicEvidenceTest, SnapshotPublisherContentionKeepsGenerationPendingForIdempotentRetry)
{
  if (!rclcpp::ok()) {
    rclcpp::init(0, nullptr);
  }
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
    [&messages](const SimulationEvidence & message) {messages.push_back(message);});
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

PhysicsStepEvidence physics_step_sample(uint64_t step, double force_n)
{
  PhysicsStepEvidence sample;
  sample.simulation_session_id = "phase-aware-test";
  sample.reset_epoch = 3;
  sample.physics_step = step;
  sample.simulation_time_s = static_cast<double>(step) * 0.002;
  sample.maximum_normal_force_n = force_n;
  sample.global_max_single_contact_force_n = force_n;
  sample.total_normal_force_n = force_n;
  return sample;
}

TEST(PhysicsStepEvidenceBufferTest, KeepsIntermediateFiveHundredHertzSpikeInHundredHertzChunk)
{
  PhysicsStepEvidenceBuffer buffer(64, 5, 11.60);
  const std::vector<double> forces{1.0, 2.0, 12.0, 2.0, 1.0};
  for (std::size_t index = 0; index < forces.size(); ++index) {
    ASSERT_TRUE(buffer.append(physics_step_sample(index + 1, forces[index])));
  }

  ASSERT_TRUE(buffer.ready());
  const auto chunk = buffer.prepare_chunk();
  ASSERT_EQ(chunk.samples.size(), 5U);
  EXPECT_EQ(chunk.first_physics_step, 1U);
  EXPECT_EQ(chunk.last_physics_step, 5U);
  EXPECT_DOUBLE_EQ(chunk.samples[2].global_max_single_contact_force_n, 12.0);
  EXPECT_FALSE(chunk.evidence_loss);
}

TEST(PhysicsStepEvidenceBufferTest, FailedPublishAttemptRetainsContinuousRangeAndIsDetectable)
{
  PhysicsStepEvidenceBuffer buffer(64, 5, 11.60);
  for (uint64_t step = 1; step <= 5; ++step) {
    ASSERT_TRUE(buffer.append(physics_step_sample(step, static_cast<double>(step))));
  }
  const auto first_attempt = buffer.prepare_chunk();
  buffer.mark_publish_failed();
  const auto retry = buffer.prepare_chunk();

  ASSERT_EQ(first_attempt.samples.size(), retry.samples.size());
  EXPECT_EQ(retry.first_physics_step, 1U);
  EXPECT_EQ(retry.last_physics_step, 5U);
  EXPECT_EQ(retry.failed_publish_attempts, 1U);
  for (std::size_t index = 0; index < retry.samples.size(); ++index) {
    EXPECT_EQ(retry.samples[index].physics_step, index + 1);
  }
}

TEST(PhysicsStepEvidenceBufferTest, CumulativePublishDeferralsAreCarriedByEveryChunkAndResetWithTheBuffer)
{
  PhysicsStepEvidenceBuffer buffer(64, 5, 11.60);
  for (uint64_t step = 1; step <= 5; ++step) {
    ASSERT_TRUE(buffer.append(physics_step_sample(step, static_cast<double>(step))));
  }
  buffer.mark_publish_failed();
  buffer.mark_publish_failed();
  const auto deferred = buffer.prepare_chunk();
  EXPECT_EQ(deferred.failed_publish_attempts, 2U);
  EXPECT_EQ(deferred.publish_deferrals_total, 2U);
  buffer.mark_published();
  for (uint64_t step = 6; step <= 10; ++step) {
    ASSERT_TRUE(buffer.append(physics_step_sample(step, static_cast<double>(step))));
  }
  const auto next = buffer.prepare_chunk();
  EXPECT_EQ(next.failed_publish_attempts, 0U);       // per chunk: reset by the publish
  EXPECT_EQ(next.publish_deferrals_total, 2U);       // cumulative: survives it
  buffer.reset();
  EXPECT_EQ(buffer.prepare_chunk().publish_deferrals_total, 0U);
}

TEST(PhysicsStepEvidenceBufferTest, EmptyLossSentinelRetainsTheLastObservedIdentity)
{
  PhysicsStepEvidenceBuffer buffer(64, 5, 11.60);
  for (uint64_t step = 1; step <= 5; ++step) {
    ASSERT_TRUE(buffer.append(physics_step_sample(step, 1.0)));
  }
  ASSERT_TRUE(buffer.ready());
  buffer.mark_published();
  ASSERT_FALSE(buffer.append(physics_step_sample(7, 1.0)));

  const auto sentinel = buffer.prepare_chunk();

  EXPECT_TRUE(sentinel.evidence_loss);
  EXPECT_TRUE(sentinel.samples.empty());
  EXPECT_EQ(sentinel.simulation_session_id, "phase-aware-test");
  EXPECT_EQ(sentinel.reset_epoch, 3U);
}

TEST(PhysicsStepEvidenceBufferTest, EqualityBreachesAndFirstHazardLatchCannotBeOverwritten)
{
  PhysicsStepEvidenceBuffer buffer(64, 5, 11.60);
  ASSERT_TRUE(buffer.append(physics_step_sample(1, 11.59)));
  ASSERT_TRUE(buffer.append(physics_step_sample(2, 11.60)));
  ASSERT_TRUE(buffer.append(physics_step_sample(3, 15.0)));
  ASSERT_TRUE(buffer.append(physics_step_sample(4, 1.0)));

  const auto hazard = buffer.hazard_latch();
  ASSERT_TRUE(hazard.has_value());
  EXPECT_EQ(hazard->physics_step, 2U);
  EXPECT_DOUBLE_EQ(hazard->simulation_time_s, 0.004);
  EXPECT_DOUBLE_EQ(hazard->force_n, 11.60);
  EXPECT_EQ(hazard->simulation_session_id, "phase-aware-test");
  EXPECT_EQ(hazard->reset_epoch, 3U);
}

TEST(PhysicsStepEvidenceBufferTest, SummedContactsLatchBeforeAnySingleContactReachesLimit)
{
  PhysicsStepEvidenceBuffer buffer(64, 5, 11.60);
  auto sample = physics_step_sample(1, 6.0);
  sample.total_normal_force_n = 12.0;
  ASSERT_TRUE(buffer.append(sample));
  const auto hazard = buffer.hazard_latch();
  ASSERT_TRUE(hazard.has_value());
  EXPECT_EQ(hazard->physics_step, 1U);
  EXPECT_DOUBLE_EQ(hazard->force_n, 12.0);
}

TEST(PhysicsStepEvidenceMetricsTest, KeepsForceSemanticsSeparateAndCompressionFingertipOnly)
{
  SimulationEvidence snapshot;
  snapshot.simulation_session_id = "metric-test";
  snapshot.reset_epoch = 4;
  snapshot.simulation_step = 10;
  snapshot.has_contact = true;
  snapshot.maximum_normal_force_n = 5.0;
  const auto contact = [](double force, double distance, double nx, double ny, double nz) {
      ContactSample sample;
      sample.normal_force_n = force;
      sample.signed_distance_m = distance;
      sample.normal_world.x = nx;
      sample.normal_world.y = ny;
      sample.normal_world.z = nz;
      return sample;
    };
  snapshot.left_fingertip_contacts = {
    contact(2.0, -0.001, 1.0, 0.0, 0.0),
    contact(3.0, -0.002, 1.0, 0.0, 0.0),
  };
  snapshot.right_fingertip_contacts = {
    contact(4.0, -0.003, 0.0, 1.0, 0.0),
  };
  snapshot.other_object_contacts = {
    contact(5.0, -0.010, 0.0, 0.0, 1.0),
  };

  const auto sample = make_physics_step_evidence(snapshot, 0.020, 1.1579004532160448, 11.60);

  EXPECT_DOUBLE_EQ(sample.maximum_normal_force_n, 5.0);
  EXPECT_DOUBLE_EQ(sample.global_max_single_contact_force_n, 5.0);
  EXPECT_DOUBLE_EQ(sample.total_normal_force_n, 14.0);
  EXPECT_DOUBLE_EQ(sample.left_fingertip_total_normal_force_n, 5.0);
  EXPECT_DOUBLE_EQ(sample.right_fingertip_total_normal_force_n, 4.0);
  EXPECT_DOUBLE_EQ(sample.fingertip_max_single_contact_force_n, 4.0);
  EXPECT_DOUBLE_EQ(sample.left_fingertip_compression_m, 0.002);
  EXPECT_DOUBLE_EQ(sample.right_fingertip_compression_m, 0.003);
  EXPECT_DOUBLE_EQ(sample.net_contact_force_world_n.x, 5.0);
  EXPECT_DOUBLE_EQ(sample.net_contact_force_world_n.y, 4.0);
  EXPECT_DOUBLE_EQ(sample.net_contact_force_world_n.z, 5.0);
  EXPECT_TRUE(sample.static_shadow_crossed);
  EXPECT_TRUE(sample.diagnostic_hazard_breached);
}

TEST_F(AtomicEvidenceTest, PhysicsHookAdvancesAtFiveHundredHertzNotControllerCadence)
{
  if (!rclcpp::ok()) {
    rclcpp::init(0, nullptr);
  }
  model_->opt.timestep = 0.002;
  const auto chunk_topic = "/test/so101/physics_step_chunks";
  auto options = rclcpp::NodeOptions().parameter_overrides({
      rclcpp::Parameter("object_body", "cup"),
      rclcpp::Parameter("left_fingertip_geom", "left_tip"),
      rclcpp::Parameter("right_fingertip_geom", "right_tip"),
      rclcpp::Parameter("other_contact_geoms", std::vector<std::string>{"table"}),
      rclcpp::Parameter("simulation_session_id", "physics-step-test"),
      rclcpp::Parameter("publish_rate", 100.0),
      rclcpp::Parameter("topic", "/test/so101/physics_step_snapshot"),
      rclcpp::Parameter("physics_step_topic", chunk_topic),
  });
  auto node = std::make_shared<rclcpp::Node>("physics_step_plugin", options);
  auto observer = std::make_shared<rclcpp::Node>("physics_step_observer");
  std::vector<PhysicsStepEvidenceChunk> chunks;
  const auto subscription = observer->create_subscription<PhysicsStepEvidenceChunk>(
    chunk_topic, rclcpp::QoS(rclcpp::KeepLast(10)).reliable(),
    [&chunks](const PhysicsStepEvidenceChunk & message) {chunks.push_back(message);});
  (void)subscription;
  SimulationEvidencePlugin plugin;
  ASSERT_TRUE(plugin.init(node, model_.get(), data_.get()));
  EXPECT_GE(plugin.publisher_->get_actual_qos().get_rmw_qos_profile().depth, 256U);
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  executor.add_node(observer);

  plugin.on_physics_step(model_.get(), data_.get());
  for (uint64_t step = 1; step <= 5; ++step) {
    data_->time = static_cast<double>(step) * model_->opt.timestep;
    plugin.on_physics_step(model_.get(), data_.get());
  }

  EXPECT_EQ(plugin.physics_state_.simulation_step, 5U);
  EXPECT_FALSE(plugin.physics_step_buffer_->evidence_loss_latched());
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (chunks.empty() && std::chrono::steady_clock::now() < deadline) {
    executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  ASSERT_EQ(chunks.size(), 1U);
  ASSERT_EQ(chunks.front().samples.size(), 5U);
  int64_t previous_clock_end_ns = 0;
  for (const auto & sample : chunks.front().samples) {
    EXPECT_GT(sample.clock_interval_begin_monotonic_ns, previous_clock_end_ns);
    EXPECT_GE(sample.clock_interval_end_monotonic_ns,
      sample.clock_interval_begin_monotonic_ns);
    previous_clock_end_ns = sample.clock_interval_end_monotonic_ns;
    EXPECT_EQ(sample.model_qpos.size(), static_cast<std::size_t>(model_->nq));
    EXPECT_EQ(sample.model_qvel.size(), static_cast<std::size_t>(model_->nv));
    for (int i = 0; i < model_->nq; ++i) {
      EXPECT_DOUBLE_EQ(sample.model_qpos[i], data_->qpos[i]);
    }
    for (int i = 0; i < model_->nv; ++i) {
      EXPECT_DOUBLE_EQ(sample.model_qvel[i], data_->qvel[i]);
    }
  }
  EXPECT_EQ(chunks.front().first_physics_step, 1U);
  EXPECT_EQ(chunks.front().last_physics_step, 5U);
  EXPECT_EQ(chunks.front().simulation_session_id, "physics-step-test");
  // The publish path stamps itself. handoff = the physics thread posted the chunk; publish = the publishing thread
  // was about to call publish(); both on the clock of the samples' clock intervals.
  const auto & stamped = chunks.front();
  EXPECT_GT(stamped.handoff_monotonic_ns, 0U);
  EXPECT_GE(stamped.handoff_monotonic_ns,
    static_cast<uint64_t>(stamped.samples.back().clock_interval_end_monotonic_ns));
  EXPECT_GE(stamped.publish_monotonic_ns, stamped.handoff_monotonic_ns);
  EXPECT_EQ(stamped.publish_deferrals_total, 0U);
  plugin.cleanup();
  executor.remove_node(observer);
  executor.remove_node(node);
  rclcpp::shutdown();
}

TEST_F(AtomicEvidenceTest, PhysicsFenceAckCarriesClockBoundsFromTheActualStepHook)
{
  if (!rclcpp::ok()) {
    rclcpp::init(0, nullptr);
  }
  model_->opt.timestep = .002;
  const auto ack_topic = "/test/so101/physics_clock_ack";
  auto options = rclcpp::NodeOptions().parameter_overrides({
      rclcpp::Parameter("object_body", "cup"),
      rclcpp::Parameter("left_fingertip_geom", "left_tip"),
      rclcpp::Parameter("right_fingertip_geom", "right_tip"),
      rclcpp::Parameter("other_contact_geoms", std::vector<std::string>{"table"}),
      rclcpp::Parameter("simulation_session_id", "clock-test"),
      rclcpp::Parameter("physics_step_fence_ack_topic", ack_topic),
  });
  auto node = std::make_shared<rclcpp::Node>("physics_clock_plugin", options);
  auto observer = std::make_shared<rclcpp::Node>("physics_clock_observer");
  std::vector<PhysicsStepFenceAck> acknowledgements;
  const auto subscription = observer->create_subscription<PhysicsStepFenceAck>(
    ack_topic, rclcpp::QoS(rclcpp::KeepLast(5)).reliable(),
    [&acknowledgements](const PhysicsStepFenceAck & ack) {acknowledgements.push_back(ack);});
  (void)subscription;
  SimulationEvidencePlugin plugin;
  ASSERT_TRUE(plugin.init(node, model_.get(), data_.get()));
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  executor.add_node(observer);
  const auto discovery_deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (plugin.step_fence_ack_publisher_->get_subscription_count() == 0 &&
    std::chrono::steady_clock::now() < discovery_deadline)
  {
    executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  ASSERT_GT(plugin.step_fence_ack_publisher_->get_subscription_count(), 0U);

  plugin.on_reset();
  plugin.on_pause(true);
  plugin.on_state_snapshot(model_.get(), data_.get(), true);
  plugin.on_pause(false);
  PhysicsStepFenceRequest request;
  request.simulation_session_id = "clock-test";
  request.reset_epoch = 1;
  request.request_sequence = 1;
  ASSERT_TRUE(plugin.step_fence_.request(request));
  data_->time = .002;
  const auto steady_ns = [] {
      return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    };
  const auto outer_begin_ns = steady_ns();
  plugin.on_physics_step(model_.get(), data_.get());
  const auto outer_end_ns = steady_ns();
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (acknowledgements.empty() && std::chrono::steady_clock::now() < deadline) {
    executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  ASSERT_EQ(acknowledgements.size(), 1U);
  const auto & ack = acknowledgements.front();
  EXPECT_EQ(ack.reset_epoch, 1U);
  EXPECT_EQ(ack.marked_physics_step, 1U);
  EXPECT_DOUBLE_EQ(ack.marked_simulation_time_s, .002);
  EXPECT_EQ(ack.marked_sample.simulation_session_id, ack.simulation_session_id);
  EXPECT_EQ(ack.marked_sample.reset_epoch, ack.reset_epoch);
  EXPECT_EQ(ack.marked_sample.physics_step, ack.marked_physics_step);
  EXPECT_DOUBLE_EQ(ack.marked_sample.simulation_time_s, ack.marked_simulation_time_s);
  EXPECT_EQ(ack.marked_sample.model_qpos,
    std::vector<double>(data_->qpos, data_->qpos + model_->nq));
  EXPECT_EQ(ack.marked_sample.model_qvel,
    std::vector<double>(data_->qvel, data_->qvel + model_->nv));
  EXPECT_LE(outer_begin_ns, ack.clock_interval_begin_monotonic_ns);
  EXPECT_LE(ack.clock_interval_begin_monotonic_ns, ack.clock_interval_end_monotonic_ns);
  EXPECT_LE(ack.clock_interval_end_monotonic_ns, outer_end_ns);
  EXPECT_EQ(ack.marked_sample.clock_interval_begin_monotonic_ns,
    ack.clock_interval_begin_monotonic_ns);
  EXPECT_LE(ack.marked_sample.clock_interval_begin_monotonic_ns,
    ack.marked_sample.clock_interval_end_monotonic_ns);
  EXPECT_LE(ack.marked_sample.clock_interval_end_monotonic_ns,
    ack.clock_interval_end_monotonic_ns);
  plugin.cleanup();
  executor.remove_node(observer);
  executor.remove_node(node);
  rclcpp::shutdown();
}

// ---- the publish gate is an integer-nanosecond grid ----------------------------------------------------------------------

namespace
{
// The simulation time as MuJoCo accumulates it: one 2 ms addition per step, rounded in the binade the sum is in.
std::vector<int> publish_gaps_in_steps(double start_time, int steps, bool old_rule)
{
  const double period = 1.0 / 100.0;
  double time = start_time;
  double last_time = start_time;
  int64_t last_grid = so101_mujoco_support::publish_grid_index(start_time, 10000000);
  int last_step = 0;
  std::vector<int> gaps;
  for (int step = 1; step <= steps; ++step) {
    time += 0.002;
    const bool publish = old_rule ? (time - last_time >= period) :
      (so101_mujoco_support::publish_grid_index(time, 10000000) != last_grid);
    if (publish) {
      gaps.push_back(step - last_step);
      last_step = step;
      last_time = time;
      last_grid = so101_mujoco_support::publish_grid_index(time, 10000000);
    }
  }
  return gaps;
}
}  // namespace

TEST(PublishGridTest, EveryBinadePublishesEveryFiveStepsWhileTheOldGateDid_5_Or_6)
{
  // [4,8) [8,16) [16,32) [32,64) [64,128) s, each from an offset that is not a multiple of the period (a reset restores the time)
  for (const double start : {4.002, 9.0, 16.0, 17.3, 31.0, 33.0, 64.0, 70.7, 100.0, 127.0 - 0.004}) {
    for (const int steps : {5000, 20000}) {
      const auto gaps = publish_gaps_in_steps(start, steps, false);
      ASSERT_GT(gaps.size(), 100U);
      for (std::size_t i = 1; i < gaps.size(); ++i) {
        EXPECT_EQ(gaps[i], 5) << "start " << start << " message " << i;      // the first gap depends on the phase of the start
      }
      EXPECT_LE(gaps.front(), 5);
    }
  }
  // the defect the integer grid replaces: in the [16,32) and [64,128) binades the accumulated double falls just under 10 ms
  // after five steps, so the old gate waited for a sixth (12 ms, 83 Hz)
  int sixes = 0;
  for (const double start : {16.0, 64.0}) {
    for (const int gap : publish_gaps_in_steps(start, 20000, true)) {sixes += gap == 6;}
  }
  EXPECT_GT(sixes, 100);
}

TEST(PublishGridTest, GridIndexIsAFloorAndExactAtTheBoundaries)
{
  using so101_mujoco_support::publish_grid_index;
  EXPECT_EQ(publish_grid_index(0.0, 10000000), 0);
  EXPECT_EQ(publish_grid_index(0.0099999, 10000000), 0);
  EXPECT_EQ(publish_grid_index(0.01, 10000000), 1);
  EXPECT_EQ(publish_grid_index(16.0, 10000000), 1600);
  EXPECT_EQ(publish_grid_index(16.0 - 1e-12, 10000000), 1600) << "below the boundary by less than a nanosecond rounds onto it";
  EXPECT_EQ(publish_grid_index(127.99, 10000000), 12799);
  EXPECT_EQ(publish_grid_index(-0.001, 10000000), -1) << "floor, not truncation";
}

TEST(PublishGridTest, ThePeriodMustBeAWholeNumberOfPhysicsSteps)
{
  using so101_mujoco_support::publish_grid_valid;
  EXPECT_TRUE(publish_grid_valid(10000000, 2000000));
  EXPECT_TRUE(publish_grid_valid(10000000, 1000000));
  EXPECT_FALSE(publish_grid_valid(10000000, 3000000));
  EXPECT_FALSE(publish_grid_valid(3333333, 2000000));
  EXPECT_FALSE(publish_grid_valid(0, 2000000));
  EXPECT_FALSE(publish_grid_valid(10000000, 0));
}

TEST_F(AtomicEvidenceTest, PluginRefusesAPublishRateThatIsNotAWholeNumberOfStepsAndKeepsTheGridAcrossBinadesAndReset)
{
  if (!rclcpp::ok()) {
    rclcpp::init(0, nullptr);
  }
  model_->opt.timestep = 0.002;
  const auto make_options = [](double rate, const std::string & topic) {
      return rclcpp::NodeOptions().parameter_overrides({
          rclcpp::Parameter("object_body", "cup"),
          rclcpp::Parameter("left_fingertip_geoms", std::vector<std::string>{"left_tip"}),
          rclcpp::Parameter("right_fingertip_geoms", std::vector<std::string>{"right_tip"}),
          rclcpp::Parameter("other_contact_geoms", std::vector<std::string>{"table"}),
          rclcpp::Parameter("simulation_session_id", "grid-test"),
          rclcpp::Parameter("publish_rate", rate),
          rclcpp::Parameter("topic", topic),
      });
    };
  {
    // 300 Hz is a 3.333 ms period: not a whole number of 2 ms steps
    auto node = std::make_shared<rclcpp::Node>("grid_refused_plugin", make_options(300.0, "/test/so101/grid_refused"));
    SimulationEvidencePlugin refused;
    EXPECT_FALSE(refused.init(node, model_.get(), data_.get()));
  }
  auto node = std::make_shared<rclcpp::Node>("grid_plugin", make_options(100.0, "/test/so101/grid"));
  SimulationEvidencePlugin plugin;
  ASSERT_TRUE(plugin.init(node, model_.get(), data_.get()));
  EXPECT_EQ(plugin.publish_period_ns_, 10000000);

  // The plugin never blocks: a step that finds the publisher busy publishes nothing and the grid message comes one step late.
  // The test therefore waits until the publisher thread has taken the previous message (a condition, with a long backstop: under
  // load that thread can be starved for seconds) and says so when it did not, instead of failing later on a spacing of six.
  const auto free_publisher = [&plugin]() {
      const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(30);
      while (std::chrono::steady_clock::now() < deadline) {
        if (plugin.realtime_publisher_->trylock()) {
          plugin.realtime_publisher_->unlock();
          return true;
        }
        std::this_thread::sleep_for(std::chrono::microseconds(50));
      }
      ADD_FAILURE() << "the publisher thread did not release the publisher within 30 s";
      return false;
    };
  // run 600 steps of 2 ms from `start`; returns the steps (from the start) at which a message was published
  const auto run = [&](double start, int steps) {
      data_->time = start;
      std::vector<int> published_at;
      int64_t seen = plugin.last_publish_grid_;
      for (int step = 1; step <= steps; ++step) {
        data_->time += 0.002;
        free_publisher();
        plugin.update(model_.get(), data_.get());
        // The publisher thread polls its mutex, so even a publisher that was free a moment ago can be locked by it when update()
        // tries: the plugin then publishes nothing for that step by design (it never blocks) and the grid message comes with the
        // next one. This test is about the cadence of the messages, so a step that should have published and did not is offered again
        // at the same time; a plugin that kept missing the grid would still fail below.
        for (int again = 0; again < 200 &&
          plugin.last_publish_grid_ != so101_mujoco_support::publish_grid_index(data_->time, plugin.publish_period_ns_) &&
          plugin.last_publish_grid_ == seen; ++again)
        {
          free_publisher();
          plugin.update(model_.get(), data_.get());
        }
        if (plugin.last_publish_grid_ != seen) {
          seen = plugin.last_publish_grid_;
          published_at.push_back(step);
        }
      }
      return published_at;
    };
  const auto expect_every_five = [](const std::vector<int> & at, const char * what) {
      ASSERT_GT(at.size(), 50U) << what;
      for (std::size_t i = 2; i < at.size(); ++i) {       // the first message after a jump of the time is off the grid phase
        EXPECT_EQ(at[i] - at[i - 1], 5) << what << " message " << i;
      }
    };
  plugin.update(model_.get(), data_.get());                               // the first message (time 0)
  expect_every_five(run(16.0, 600), "16-32 s binade");
  expect_every_five(run(64.0, 600), "64-128 s binade");
  expect_every_five(run(32.0, 600), "32-64 s binade");

  // reset and the restored time: the pending reset is consumed by the paused snapshot (which publishes, bypassing the gate), the
  // time restored lower than before; the grid resumes at once and stays every five steps
  plugin.on_pause(true);
  plugin.on_reset();
  data_->time = 3.5;
  free_publisher();
  plugin.on_state_snapshot(model_.get(), data_.get(), true);
  plugin.on_pause(false);
  const auto after_reset = run(3.5, 600);
  expect_every_five(after_reset, "after the reset");
  EXPECT_LE(after_reset.front(), 5) << "the first message after a time restore comes within one period";
  plugin.cleanup();
  rclcpp::shutdown();
}

TEST_F(AtomicEvidenceTest, ControllerUpdatesDoNotInventPhysicsStepEvidence)
{
  if (!rclcpp::ok()) {
    rclcpp::init(0, nullptr);
  }
  auto options = rclcpp::NodeOptions().parameter_overrides({
      rclcpp::Parameter("object_body", "cup"),
      rclcpp::Parameter("left_fingertip_geom", "left_tip"),
      rclcpp::Parameter("right_fingertip_geom", "right_tip"),
      rclcpp::Parameter("other_contact_geoms", std::vector<std::string>{"table"}),
      rclcpp::Parameter("simulation_session_id", "non-advancing-test"),
      rclcpp::Parameter("publish_rate", 100.0),
      rclcpp::Parameter("topic", "/test/so101/non_advancing_snapshot"),
  });
  auto node = std::make_shared<rclcpp::Node>("non_advancing_plugin", options);
  SimulationEvidencePlugin plugin;
  ASSERT_TRUE(plugin.init(node, model_.get(), data_.get()));

  plugin.update(model_.get(), data_.get());
  data_->time = 0.02;
  plugin.update(model_.get(), data_.get());

  EXPECT_EQ(plugin.physics_state_.simulation_step, 0U);
  ASSERT_NE(plugin.physics_step_buffer_, nullptr);
  EXPECT_TRUE(plugin.physics_step_buffer_->prepare_chunk().samples.empty());
  EXPECT_FALSE(plugin.physics_step_buffer_->evidence_loss_latched());
  plugin.cleanup();
  rclcpp::shutdown();
}
}  // namespace

TEST(ScalarJointEvidenceTest, NamedHingeSnapshotUsesActualAddressesAndResetScope)
{
  const auto path = std::filesystem::temp_directory_path() / "so101_scalar_evidence.xml";
  std::ofstream(path) << R"(<mujoco><worldbody><body name="robot">
    <joint name="neck_yaw_joint" type="hinge"/><geom type="sphere" size=".02"/>
    <body name="arm"><joint name="1" type="hinge"/><geom type="sphere" size=".02"/></body>
    </body><body name="cup"><freejoint/><geom type="sphere" size=".02"/></body>
    </worldbody></mujoco>)";
  char error[1024]{};
  std::unique_ptr<mjModel, ModelDeleter> model(mj_loadXML(path.c_str(), nullptr, error, sizeof(error)));
  ASSERT_NE(model, nullptr) << error;
  std::unique_ptr<mjData, DataDeleter> data(mj_makeData(model.get()));
  data->qpos[0] = -.4; data->qpos[1] = .2; data->qvel[0] = .01;
  data->time = 3.5;
  const auto message = so101_mujoco_support::make_scalar_joint_evidence(
    model.get(), data.get(), {"1", "neck_yaw_joint"}, "session-a", 4, 0, true);
  EXPECT_EQ(message.simulation_session_id, "session-a");
  EXPECT_EQ(message.reset_epoch, 4U); EXPECT_EQ(message.simulation_step, 0U);
  EXPECT_TRUE(message.paused); EXPECT_EQ(message.joint_names, (std::vector<std::string>{"1", "neck_yaw_joint"}));
  EXPECT_EQ(message.positions_rad, (std::vector<double>{.2, -.4}));
  EXPECT_EQ(message.velocities_rad_s, (std::vector<double>{0., .01}));
  EXPECT_EQ(message.header.stamp.sec, 3); EXPECT_EQ(message.header.stamp.nanosec, 500000000U);
  EXPECT_THROW(so101_mujoco_support::make_scalar_joint_evidence(
    model.get(), data.get(), {"missing"}, "s", 0, 0, true), std::invalid_argument);
}

TEST_F(AtomicEvidenceTest, WholeRobotBuilderKeepsNonCupContactAndLegacyFilter)
{
  so101_mujoco_support::RobotContactBuilder robot;
  ASSERT_TRUE(robot.configure(model_.get(), {"left", "right"}, 128));
  place_free_body("cup_joint", .5, 0, .2);
  place_free_body("left_joint", 0, 0, .01);
  place_free_body("right_joint", 0, 0, .03);
  mj_forward(model_.get(), data_.get());
  const auto output = robot.build(model_.get(), data_.get(), "session-a", 1, 1);
  EXPECT_FALSE(output.truncated);
  EXPECT_GE(output.geom_a.size(), 2u);
  EXPECT_EQ(output.geom_a.size(), output.geom_b.size());
  const auto legacy = builder_.build(model_.get(), data_.get(), false, state_);
  EXPECT_FALSE(legacy.has_contact);
}

TEST(RobotContactBufferTest, OverflowAndTransientContactPersistUntilExplicitEpochReset)
{
  so101_mujoco_support::RobotContactBuffer buffer(2);
  so101_mujoco_support::msg::RobotContactEvidence sample;
  sample.simulation_session_id = "s";
  sample.reset_epoch = 1;
  sample.physics_step = 1;
  sample.simulation_time_s = .002;
  sample.geom_a = {"arm"}; sample.geom_b = {"table"};
  sample.signed_distance_m = {-.001}; sample.normal_force_n = {2.};
  ASSERT_TRUE(buffer.append(sample));
  sample.physics_step = 2;sample.simulation_time_s = .004;
  sample.geom_a.clear();sample.geom_b.clear();sample.signed_distance_m.clear();sample.normal_force_n.clear();
  ASSERT_TRUE(buffer.append(sample));
  sample.physics_step = 3;sample.simulation_time_s = .006;
  EXPECT_FALSE(buffer.append(sample));
  EXPECT_TRUE(buffer.front().evidence_loss);
  EXPECT_EQ(buffer.front().geom_a.front(), "arm");
  buffer.pop_published();
  EXPECT_TRUE(buffer.front().evidence_loss);
  buffer.reset(2);
  sample.reset_epoch = 2;sample.physics_step = 1;sample.simulation_time_s = .008;
  ASSERT_TRUE(buffer.append(sample));
  EXPECT_FALSE(buffer.front().evidence_loss);
}

// ---- plan A21: RobotContactEvidence has its own non-real-time publishing thread ----

namespace
{
using so101_mujoco_support::RobotContactPublisher;
using so101_mujoco_support::msg::RobotContactEvidence;

RobotContactEvidence contact_step(uint64_t epoch, uint64_t step)
{
  RobotContactEvidence sample;
  sample.simulation_session_id = "s";
  sample.reset_epoch = epoch;
  sample.physics_step = step;
  sample.simulation_time_s = static_cast<double>(step) * .002;
  return sample;
}

struct Delivered
{
  std::mutex mutex;
  std::vector<RobotContactEvidence> rows;
  void add(const RobotContactEvidence & row)
  {
    std::lock_guard<std::mutex> lock(mutex);
    rows.push_back(row);
  }
  std::size_t count()
  {
    std::lock_guard<std::mutex> lock(mutex);
    return rows.size();
  }
};

template<typename Predicate>
bool wait_until(Predicate predicate, std::chrono::milliseconds limit = std::chrono::milliseconds(5000))
{
  const auto end = std::chrono::steady_clock::now() + limit;
  while (std::chrono::steady_clock::now() < end) {
    if (predicate()) {return true;}
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return predicate();
}
}  // namespace

TEST(RobotContactPublisherTest, PacedPushAtTheStepRateIsDeliveredCompletelyInOrderAtTheSameRate)
{
  Delivered delivered;
  RobotContactPublisher publisher(5000, [&delivered](const RobotContactEvidence & row) {delivered.add(row);});
  const int count = 600;
  const auto begin = std::chrono::steady_clock::now();
  for (int step = 1; step <= count; ++step) {
    ASSERT_TRUE(publisher.push(contact_step(1, step)));
    std::this_thread::sleep_for(std::chrono::microseconds(1500));  // faster than the 2 ms physics step
  }
  ASSERT_TRUE(wait_until([&]() {return delivered.count() == static_cast<std::size_t>(count);}));
  const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - begin).count();
  EXPECT_GE(static_cast<double>(count) / seconds, 400.0);  // delivered at (about) the push rate, no backlog growth
  std::lock_guard<std::mutex> lock(delivered.mutex);
  for (int index = 0; index < count; ++index) {
    ASSERT_EQ(delivered.rows[index].physics_step, static_cast<uint64_t>(index + 1));  // in order, none missing
    EXPECT_FALSE(delivered.rows[index].evidence_loss);
  }
  const auto stats = publisher.stats();
  EXPECT_EQ(stats.pushed, static_cast<uint64_t>(count));
  EXPECT_EQ(stats.published, static_cast<uint64_t>(count));
  EXPECT_EQ(stats.dropped, 0u);
}

TEST(RobotContactPublisherTest, ABurstFasterThanOneMessagePerPublishCycleIsDrainedInBatchesInOrder)
{
  Delivered delivered;
  RobotContactPublisher publisher(5000, [&delivered](const RobotContactEvidence & row) {
      std::this_thread::sleep_for(std::chrono::microseconds(30));  // a sink slower than the push loop
      delivered.add(row);
    });
  const int count = 3000;
  for (int step = 1; step <= count; ++step) {
    ASSERT_TRUE(publisher.push(contact_step(1, step)));  // never blocks on the sink
  }
  ASSERT_TRUE(wait_until([&]() {return delivered.count() == static_cast<std::size_t>(count);}));
  std::lock_guard<std::mutex> lock(delivered.mutex);
  for (int index = 0; index < count; ++index) {
    ASSERT_EQ(delivered.rows[index].physics_step, static_cast<uint64_t>(index + 1));
  }
  const auto stats = publisher.stats();
  EXPECT_GT(stats.high_water, 100u);  // the backlog really queued up behind the slow sink and was fully drained
  EXPECT_EQ(stats.published, static_cast<uint64_t>(count));
  EXPECT_EQ(stats.dropped, 0u);
}

TEST(RobotContactPublisherTest, ThePhysicsThreadNeverBlocksOnASinkThatIsStuck)
{
  std::mutex gate;
  std::unique_lock<std::mutex> hold(gate);
  std::atomic<int> entered{0};
  RobotContactPublisher publisher(5000, [&](const RobotContactEvidence &) {
      ++entered;
      std::lock_guard<std::mutex> wait(gate);  // stuck until released
    });
  const auto begin = std::chrono::steady_clock::now();
  for (int step = 1; step <= 1000; ++step) {
    ASSERT_TRUE(publisher.push(contact_step(1, step)));
  }
  EXPECT_LT(std::chrono::steady_clock::now() - begin, std::chrono::milliseconds(500));
  hold.unlock();
  ASSERT_TRUE(wait_until([&]() {return publisher.stats().published == 1000u;}));
}

TEST(RobotContactPublisherTest, OverflowKeepsTheLossSignallingOnEveryLaterMessageUntilReset)
{
  std::mutex gate;
  std::unique_lock<std::mutex> hold(gate);
  std::atomic<int> entered{0};
  Delivered delivered;
  RobotContactPublisher publisher(8, [&](const RobotContactEvidence & row) {
      ++entered;
      std::lock_guard<std::mutex> wait(gate);
      delivered.add(row);
    });
  ASSERT_TRUE(publisher.push(contact_step(1, 1)));
  ASSERT_TRUE(wait_until([&]() {return entered.load() == 1;}));  // step 1 is in flight, the queue is empty
  for (int step = 2; step <= 9; ++step) {
    ASSERT_TRUE(publisher.push(contact_step(1, step)));  // fills the 8-slot queue
  }
  EXPECT_FALSE(publisher.push(contact_step(1, 10)));  // overflow: refused, exactly like RobotContactBuffer::append
  EXPECT_EQ(publisher.stats().dropped, 1u);
  hold.unlock();
  ASSERT_TRUE(wait_until([&]() {return delivered.count() == 9u;}));
  {
    std::lock_guard<std::mutex> lock(delivered.mutex);
    EXPECT_FALSE(delivered.rows[0].evidence_loss);  // left before the overflow
    for (int index = 1; index < 9; ++index) {
      EXPECT_EQ(delivered.rows[index].physics_step, static_cast<uint64_t>(index + 1));
      EXPECT_TRUE(delivered.rows[index].evidence_loss);  // the latch is applied to every later message
    }
  }
  ASSERT_TRUE(publisher.push(contact_step(1, 11)));
  ASSERT_TRUE(wait_until([&]() {return delivered.count() == 10u;}));
  std::lock_guard<std::mutex> lock(delivered.mutex);
  EXPECT_TRUE(delivered.rows[9].evidence_loss);  // persists until an explicit epoch reset
}

TEST(RobotContactPublisherTest, ResetClearsTheQueueDropsTheRestOfABatchAndKeepsEpochSemantics)
{
  std::mutex gate;
  std::unique_lock<std::mutex> hold(gate);
  std::atomic<int> entered{0};
  Delivered delivered;
  RobotContactPublisher publisher(5000, [&](const RobotContactEvidence & row) {
      ++entered;
      std::lock_guard<std::mutex> wait(gate);
      delivered.add(row);
    });
  for (int step = 1; step <= 6; ++step) {
    ASSERT_TRUE(publisher.push(contact_step(1, step)));
  }
  ASSERT_TRUE(wait_until([&]() {return entered.load() == 1;}));
  std::thread resetter([&]() {publisher.reset(2);});  // waits (bounded) for the one in-flight message
  std::this_thread::sleep_for(std::chrono::milliseconds(80));
  hold.unlock();
  resetter.join();
  ASSERT_TRUE(wait_until([&]() {return delivered.count() >= 1u;}));
  ASSERT_TRUE(publisher.push(contact_step(2, 1)));  // the new epoch restarts at step 1, no loss carried over
  ASSERT_TRUE(wait_until([&]() {return delivered.count() >= 2u;}));
  std::this_thread::sleep_for(std::chrono::milliseconds(50));
  std::lock_guard<std::mutex> lock(delivered.mutex);
  ASSERT_EQ(delivered.rows.size(), 2u);  // steps 2..6 of epoch 1 never follow the new epoch
  EXPECT_EQ(delivered.rows[0].reset_epoch, 1u);
  EXPECT_EQ(delivered.rows[1].reset_epoch, 2u);
  EXPECT_EQ(delivered.rows[1].physics_step, 1u);
  EXPECT_FALSE(delivered.rows[1].evidence_loss);
}

TEST(RobotContactPublisherTest, ASinkFailureIsLostEvidenceAndStopJoinsTheThread)
{
  std::atomic<int> calls{0};
  Delivered delivered;
  auto publisher = std::make_unique<RobotContactPublisher>(100, [&](const RobotContactEvidence & row) {
      if (++calls == 1) {throw std::runtime_error("publish failed");}
      delivered.add(row);
    });
  ASSERT_TRUE(publisher->push(contact_step(1, 1)));
  ASSERT_TRUE(wait_until([&]() {return publisher->stats().sink_errors == 1u;}));
  ASSERT_TRUE(publisher->push(contact_step(1, 2)));
  ASSERT_TRUE(wait_until([&]() {return delivered.count() == 1u;}));
  EXPECT_TRUE(delivered.rows[0].evidence_loss);  // the message that never left is signalled as lost evidence
  publisher->stop();
  publisher->stop();  // idempotent
  const auto after_stop = calls.load();
  publisher->push(contact_step(1, 3));
  std::this_thread::sleep_for(std::chrono::milliseconds(30));
  EXPECT_EQ(calls.load(), after_stop);  // the joined thread delivers nothing more
  publisher.reset();  // destructor after stop is clean
}

TEST(RobotContactPublisherTest, DestructionWithQueuedMessagesJoinsWithoutHanging)
{
  std::atomic<int> calls{0};
  {
    RobotContactPublisher publisher(5000, [&](const RobotContactEvidence &) {
        ++calls;
        std::this_thread::sleep_for(std::chrono::microseconds(200));
      });
    for (int step = 1; step <= 2000; ++step) {publisher.push(contact_step(1, step));}
  }  // joins here; queued messages are discarded
  const auto at_exit = calls.load();
  std::this_thread::sleep_for(std::chrono::milliseconds(30));
  EXPECT_EQ(calls.load(), at_exit);
}

TEST_F(AtomicEvidenceTest, WholeRobotRetainsArmTableArmArmAndArmMastPairs)
{
  so101_mujoco_support::RobotContactBuilder robot;
  ASSERT_TRUE(robot.configure(model_.get(), {"left", "right", "mast"}, 128));
  place_free_body("cup_joint", .5, 0, .2);
  place_free_body("left_joint", 0, 0, .01);
  place_free_body("right_joint", 0, 0, .03);
  place_free_body("mast_joint", 0, 0, .06);
  mj_forward(model_.get(), data_.get());
  const auto output = robot.build(model_.get(), data_.get(), "session-a", 1, 1);
  const auto has_pair = [&output](const std::string & first, const std::string & second) {
      for (std::size_t i = 0; i < output.geom_a.size(); ++i) {
        if ((output.geom_a[i] == first && output.geom_b[i] == second) ||
          (output.geom_a[i] == second && output.geom_b[i] == first)) {return true;}
      }
      return false;
    };
  EXPECT_TRUE(has_pair("left_tip", "table"));
  EXPECT_TRUE(has_pair("left_tip", "right_tip"));
  EXPECT_TRUE(has_pair("right_tip", "mast_geom"));
  EXPECT_FALSE(output.evidence_loss);
  EXPECT_FALSE(builder_.build(model_.get(), data_.get(), false, state_).has_contact);
  ASSERT_TRUE(robot.configure(model_.get(), {"left", "right", "mast"}, 1));
  EXPECT_TRUE(robot.build(model_.get(), data_.get(), "session-a", 1, 1).truncated);
}

TEST_F(AtomicEvidenceTest, FullSceneStateTracksEveryDynamicBodyAndBindsCompiledModel)
{
  so101_mujoco_support::SceneStateBuilder scene;
  ASSERT_TRUE(scene.configure(model_.get()));
  const auto fingerprint = scene.model_sha256();
  ASSERT_EQ(fingerprint.size(), 64U);
  place_free_body("mast_joint", .8, .3, .4);
  data_->time = .25;
  const auto before = std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
  const auto sample = scene.build(model_.get(), data_.get(), "session-a", 3, 17, false, before);
  const auto after = std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
  EXPECT_EQ(sample.clock_interval_begin_monotonic_ns, before);
  EXPECT_LE(before, sample.clock_interval_end_monotonic_ns);
  EXPECT_LE(sample.clock_interval_end_monotonic_ns, after);
  EXPECT_EQ(sample.model_sha256, fingerprint);
  EXPECT_EQ(sample.qpos.size(), static_cast<std::size_t>(model_->nq));
  EXPECT_EQ(sample.simulation_session_id, "session-a");
  EXPECT_EQ(sample.reset_epoch, 3U);
  EXPECT_EQ(sample.simulation_step, 17U);
  EXPECT_FALSE(sample.paused);
  for (int i=0; i<model_->nq; ++i) {EXPECT_DOUBLE_EQ(sample.qpos[i], data_->qpos[i]);}
  const auto paused = scene.build(model_.get(), data_.get(), "session-a", 4, 0, true, before);
  EXPECT_TRUE(paused.paused);
  EXPECT_EQ(paused.reset_epoch, 4U);
  EXPECT_EQ(paused.simulation_step, 0U);
  EXPECT_EQ(paused.qpos, sample.qpos);
  model_->geom_size[0] += .001;
  so101_mujoco_support::SceneStateBuilder changed;
  ASSERT_TRUE(changed.configure(model_.get()));
  EXPECT_NE(changed.model_sha256(), fingerprint);
}

TEST_F(AtomicEvidenceTest, WithoutAnOverrideTheSceneStateIsWhatItAlwaysWasAndNamesTheLoadedModelOnly)
{
  so101_mujoco_support::SceneStateBuilder plain;
  ASSERT_TRUE(plain.configure(model_.get()));
  EXPECT_EQ(plain.model_sha256(), plain.computed_model_sha256());
  place_free_body("mast_joint", .8, .3, .4);
  data_->time = .25;
  const auto begin = std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
  const auto sample = plain.build(model_.get(), data_.get(), "session-a", 1, 1, false, begin);
  EXPECT_EQ(sample.model_sha256, plain.model_sha256());
  EXPECT_EQ(sample.loaded_model_sha256, plain.model_sha256());
  EXPECT_TRUE(sample.declared_model_sha256.empty());
  EXPECT_TRUE(sample.equivalence_proof_sha256.empty());
}

TEST_F(AtomicEvidenceTest, ASceneVariantStackPublishesBothHashesAndTheProofHashAndRefusesAnOverrideWithoutAProof)
{
  so101_mujoco_support::SceneStateBuilder plain;
  ASSERT_TRUE(plain.configure(model_.get()));
  const std::string nominal(64, 'a');
  const std::string proof(64, 'b');
  so101_mujoco_support::SceneStateBuilder declared;
  ASSERT_TRUE(declared.configure(model_.get(), nominal, proof));
  EXPECT_EQ(declared.model_sha256(), nominal);
  EXPECT_EQ(declared.computed_model_sha256(), plain.model_sha256());
  place_free_body("mast_joint", .8, .3, .4);
  data_->time = .25;
  const auto begin = std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
  const auto sample = declared.build(model_.get(), data_.get(), "session-a", 1, 1, false, begin);
  EXPECT_EQ(sample.model_sha256, nominal);
  EXPECT_EQ(sample.declared_model_sha256, nominal);
  EXPECT_EQ(sample.loaded_model_sha256, plain.model_sha256());
  EXPECT_EQ(sample.equivalence_proof_sha256, proof);
  // an override is a declared identity AND a proof hash, each 64 lowercase hex characters
  so101_mujoco_support::SceneStateBuilder no_proof;
  EXPECT_FALSE(no_proof.configure(model_.get(), nominal));
  EXPECT_TRUE(no_proof.model_sha256().empty());
  so101_mujoco_support::SceneStateBuilder proof_only;
  EXPECT_FALSE(proof_only.configure(model_.get(), std::string(), proof));
  for (const auto & bad : {std::string(63, 'a'), std::string(65, 'a'), std::string(64, 'A'), std::string(64, 'g'), std::string("../")}) {
    so101_mujoco_support::SceneStateBuilder refused;
    EXPECT_FALSE(refused.configure(model_.get(), bad, proof)) << bad;
    EXPECT_FALSE(refused.configure(model_.get(), nominal, bad)) << bad;
    EXPECT_TRUE(refused.model_sha256().empty());
  }
}


TEST(StampingChunkPublisherTest, StampsThePublishTimeInItsOwnThreadAndNeverBlocksThePostingThread)
{
  rclcpp::init(0, nullptr);
  auto node = std::make_shared<rclcpp::Node>("stamping_publisher_test");
  const auto topic = "/test/so101/stamping_chunks";
  std::vector<PhysicsStepEvidenceChunk> received;
  const auto subscription = node->create_subscription<PhysicsStepEvidenceChunk>(
    topic, rclcpp::QoS(rclcpp::KeepLast(100)).reliable(),
    [&received](const PhysicsStepEvidenceChunk & message) {received.push_back(message);});
  (void)subscription;
  auto publisher = node->create_publisher<PhysicsStepEvidenceChunk>(
    topic, rclcpp::QoS(rclcpp::KeepLast(100)).reliable());
  StampingChunkPublisher stamping(publisher);
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);

  std::size_t accepted = 0;
  std::chrono::nanoseconds slowest{0};
  for (uint64_t sequence = 1; sequence <= 50; ++sequence) {
    PhysicsStepEvidenceChunk chunk;
    chunk.chunk_sequence = sequence;
    chunk.handoff_monotonic_ns = static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
    const auto before = std::chrono::steady_clock::now();
    const bool posted = stamping.try_post(chunk);
    slowest = std::max(slowest, std::chrono::steady_clock::now() - before);
    accepted += posted ? 1U : 0U;
    executor.spin_some();
  }
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (received.size() < accepted && std::chrono::steady_clock::now() < deadline) {
    executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  EXPECT_GT(accepted, 0U);
  EXPECT_EQ(received.size(), accepted);                   // everything accepted is published, in order
  EXPECT_LT(slowest, std::chrono::milliseconds(5));       // the physics thread is never blocked
  uint64_t previous_sequence = 0;
  for (const auto & chunk : received) {
    EXPECT_GT(chunk.chunk_sequence, previous_sequence);
    previous_sequence = chunk.chunk_sequence;
    EXPECT_GE(chunk.publish_monotonic_ns, chunk.handoff_monotonic_ns);
    EXPECT_GT(chunk.publish_monotonic_ns, 0U);
  }
  executor.remove_node(node);
  rclcpp::shutdown();
}
