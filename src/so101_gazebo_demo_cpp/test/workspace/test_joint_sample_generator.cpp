#include <gtest/gtest.h>

#include "so101_gazebo_demo/workspace/joint_sample_generator.hpp"

namespace ws = so101_gazebo_demo::workspace;

namespace
{
ws::JointBounds unitBounds()
{
  return {{{0.0, 1.0}, {0.0, 1.0}, {0.0, 1.0}, {0.0, 1.0}, {0.0, 1.0}}};
}
}  // namespace

TEST(JointSampleGenerator, GlobalPrefixUsesApprovedHaltonBases)
{
  ws::JointSampleGenerator generator(unitBounds());
  const auto samples = generator.nextGlobal(2);
  ASSERT_EQ(samples.size(), 2U);
  EXPECT_EQ(samples[0].source, ws::SampleSource::HALTON_GLOBAL);
  EXPECT_NEAR(samples[0].arm_joints[0], 0.5, 1e-15);
  EXPECT_NEAR(samples[0].arm_joints[1], 1.0 / 3.0, 1e-15);
  EXPECT_NEAR(samples[0].arm_joints[2], 0.2, 1e-15);
  EXPECT_NEAR(samples[0].arm_joints[3], 1.0 / 7.0, 1e-15);
  EXPECT_NEAR(samples[0].arm_joints[4], 1.0 / 11.0, 1e-15);
  EXPECT_NEAR(samples[1].arm_joints[0], 0.25, 1e-15);
}

TEST(JointSampleGenerator, RestoreContinuesAtTheSameGlobalIndex)
{
  ws::JointSampleGenerator first(unitBounds());
  first.nextGlobal(13);
  const auto checkpoint = first.checkpoint();
  const auto expected = first.nextGlobal(5);
  ws::JointSampleGenerator resumed(unitBounds());
  resumed.restore(checkpoint);
  const auto actual = resumed.nextGlobal(5);
  ASSERT_EQ(actual.size(), expected.size());
  for (std::size_t i = 0; i < actual.size(); ++i) {
    EXPECT_EQ(actual[i].sequence_id, expected[i].sequence_id);
    EXPECT_EQ(actual[i].arm_joints, expected[i].arm_joints);
  }
}

TEST(JointSampleGenerator, ExplicitSamplesAreDeduplicatedAndDoNotConsumeGlobalIndex)
{
  ws::JointSampleGenerator generator(unitBounds());
  const auto samples = generator.explicitSamples({0.5, 0.5, 0.5, 0.5, 0.5});
  EXPECT_EQ(samples.size(), 11U);
  EXPECT_EQ(generator.checkpoint().next_global_index, 1U);
  for (const auto & sample : samples) {
    EXPECT_EQ(sample.source, ws::SampleSource::EXPLICIT_BOUNDARY);
  }
}

TEST(JointSampleGenerator, LocalPerturbationsReflectRatherThanClamp)
{
  ws::JointSampleGenerator generator(unitBounds());
  const ws::RefinementSeed seed{7, 1, {0, 0, 0}, {0.0, 0.0, 0.0, 0.0, 0.0}, 0};
  const auto samples = generator.nextRefined({seed}, 1);
  ASSERT_EQ(samples.size(), 1U);
  for (double joint : samples.front().arm_joints) {
    EXPECT_GT(joint, 0.0);
    EXPECT_LT(joint, 1.0);
  }
}
