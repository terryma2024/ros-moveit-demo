#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <limits>
#include <memory>
#include <string>
#include <type_traits>

#include <mujoco/mujoco.h>

#include "so101_mujoco_support/simulation_evidence_plugin.hpp"

namespace
{
using so101_mujoco_support::EvidenceBuilder;
using so101_mujoco_support::EvidenceState;

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

TEST_F(AtomicEvidenceTest, OrdersStepsSequencesAndResetEpoch)
{
  mj_forward(model_.get(), data_.get());
  const auto first = builder_.build(model_.get(), data_.get(), false, state_);
  data_->time = .001;
  const auto second = builder_.build(model_.get(), data_.get(), false, state_);
  data_->time = 0.0;
  const auto reset = builder_.build(model_.get(), data_.get(), false, state_);
  EXPECT_EQ(second.publisher_sequence, first.publisher_sequence + 1);
  EXPECT_EQ(second.simulation_step, first.simulation_step + 1);
  EXPECT_EQ(reset.reset_epoch, first.reset_epoch + 1);
  EXPECT_EQ(reset.simulation_step, 0U);
  EXPECT_EQ(reset.simulation_session_id, first.simulation_session_id);
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

TEST_F(AtomicEvidenceTest, MarksPausedAndTruncatesBoundedContacts)
{
  mj_forward(model_.get(), data_.get());
  const auto running = builder_.build(model_.get(), data_.get(), false, state_);
  const auto paused = builder_.build(model_.get(), data_.get(), true, state_);
  EXPECT_TRUE(paused.paused);
  EXPECT_EQ(paused.publisher_sequence, 1U);
  EXPECT_EQ(paused.simulation_step, running.simulation_step);
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
