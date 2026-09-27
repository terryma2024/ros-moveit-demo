#include <gtest/gtest.h>

#include <array>
#include <cstdint>
#include <limits>

#include "so101_mujoco_support/controller_stop_witness.hpp"

namespace
{
using so101_mujoco_support::ControllerStopWitness;

ControllerStopWitness::Observation stopped_sample(uint64_t sequence)
{
  ControllerStopWitness::Observation sample{};
  sample.sequence = sequence;
  sample.sim_time_ns = static_cast<int64_t>(sequence) * 2000000;
  sample.received_monotonic_ns = 1000000000 + static_cast<int64_t>(sequence) * 2000000;
  sample.joint_count = 5;
  sample.holding = true;
  sample.active_goal = false;
  sample.measured_positions = {0.1, 0.2, 0.3, 0.4, 0.5};
  sample.reference_positions = sample.measured_positions;
  sample.measured_velocities.fill(0.0);
  sample.reference_velocities.fill(0.0);
  return sample;
}

void fill_stopped_window(ControllerStopWitness & witness)
{
  for (uint64_t sequence = 1; sequence <= 51; ++sequence) {
    witness.observe(stopped_sample(sequence));
  }
}
}  // namespace

TEST(ControllerStopWitness, RequiresACompleteFreshLocalStoppedWindow)
{
  ControllerStopWitness witness(5);
  for (uint64_t sequence = 1; sequence < 51; ++sequence) {
    witness.observe(stopped_sample(sequence));
  }
  EXPECT_FALSE(witness.proof(1102000000).has_value());
  witness.observe(stopped_sample(51));
  const auto proof = witness.proof(1102000000);
  ASSERT_TRUE(proof.has_value());
  EXPECT_EQ(proof->sample_count, 51u);
  EXPECT_EQ(proof->last_sim_time_ns, 102000000);
  EXPECT_EQ(proof->measured_positions[0], 0.1);
  EXPECT_FALSE(witness.proof(1303000000).has_value());
}

TEST(ControllerStopWitness, RejectsGapsMotionReferenceDriftAndActiveGoals)
{
  for (int mode = 0; mode < 6; ++mode) {
    ControllerStopWitness witness(5);
    fill_stopped_window(witness);
    auto changed = stopped_sample(52);
    if (mode == 0) {changed.sequence = 54;}
    if (mode == 1) {changed.sim_time_ns += 1;}
    if (mode == 2) {changed.measured_velocities[2] = 0.0021;}
    if (mode == 3) {changed.reference_positions[3] += 0.0001;}
    if (mode == 4) {changed.active_goal = true;}
    if (mode == 5) {changed.holding = false;}
    witness.observe(changed);
    EXPECT_FALSE(witness.proof(1104000000).has_value()) << mode;
  }
}

TEST(ControllerStopWitness, RejectsNonfiniteAndWrongJointScope)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  auto changed = stopped_sample(52);
  changed.measured_positions[0] = std::numeric_limits<double>::quiet_NaN();
  witness.observe(changed);
  EXPECT_FALSE(witness.proof(1104000000).has_value());
  changed = stopped_sample(53);
  changed.joint_count = 1;
  witness.observe(changed);
  EXPECT_FALSE(witness.proof(1106000000).has_value());
}
