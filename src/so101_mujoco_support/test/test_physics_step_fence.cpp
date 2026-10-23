// Copyright 2026 SO-101 maintainers

#include <gtest/gtest.h>

#include <limits>
#include <string>
#include <utility>

#include "so101_mujoco_support/physics_step_fence.hpp"
#include "so101_mujoco_support/msg/physics_step_evidence.hpp"

namespace
{
using so101_mujoco_support::PhysicsStepFence;
using so101_mujoco_support::msg::PhysicsStepEvidence;
using so101_mujoco_support::msg::PhysicsStepFenceRequest;

PhysicsStepFenceRequest request(uint64_t sequence, uint64_t epoch = 2)
{
  PhysicsStepFenceRequest value;
  value.simulation_session_id = "session-one";
  value.reset_epoch = epoch;
  value.request_sequence = sequence;
  return value;
}

PhysicsStepEvidence sample(
  uint64_t step, double time_s,
  std::string session = "session-one", uint64_t epoch = 2)
{
  PhysicsStepEvidence value;
  value.simulation_session_id = std::move(session);
  value.reset_epoch = epoch;
  value.physics_step = step;
  value.simulation_time_s = time_s;
  value.model_qpos = {0.1, 0.2};
  value.model_qvel = {0.3};
  return value;
}

TEST(PhysicsStepFence, MarksOnlyAnAdvancingStepAfterTheRequest)
{
  PhysicsStepFence fence("session-one");
  fence.reset(2);
  EXPECT_FALSE(fence.observe(sample(99, 1.198), false, 10, 11).has_value());
  ASSERT_TRUE(fence.request(request(1)));
  EXPECT_FALSE(fence.observe(sample(99, 1.198), true, 12, 13).has_value());
  const auto ack = fence.observe(sample(100, 1.2), false, 14, 15);
  ASSERT_TRUE(ack.has_value());
  EXPECT_EQ(ack->simulation_session_id, "session-one");
  EXPECT_EQ(ack->reset_epoch, 2U);
  EXPECT_EQ(ack->request_sequence, 1U);
  EXPECT_EQ(ack->marked_physics_step, 100U);
  EXPECT_DOUBLE_EQ(ack->marked_simulation_time_s, 1.2);
  EXPECT_EQ(ack->marked_sample.model_qpos, sample(100, 1.2).model_qpos);
  EXPECT_EQ(ack->marked_sample.model_qvel, sample(100, 1.2).model_qvel);
  EXPECT_FALSE(fence.observe(sample(101, 1.202), false, 16, 17).has_value());
}

TEST(PhysicsStepFence, RejectsReplayAndInvalidScopeWithoutReplacingPendingRequest)
{
  PhysicsStepFence fence("session-one");
  fence.reset(2);
  auto foreign = request(1);
  foreign.simulation_session_id = "other";
  EXPECT_FALSE(fence.request(foreign));
  EXPECT_FALSE(fence.request(request(1, 3)));
  EXPECT_FALSE(fence.request(request(0)));
  ASSERT_TRUE(fence.request(request(1)));
  EXPECT_FALSE(fence.request(request(2)));
  EXPECT_FALSE(fence.observe(sample(100, 1.2, "other"), false, 10, 11).has_value());
  EXPECT_FALSE(fence.observe(sample(100, 1.2, "session-one", 3), false, 12, 13).has_value());
  EXPECT_EQ(fence.observe(sample(100, 1.2), false, 14, 15)->request_sequence, 1U);
  EXPECT_FALSE(fence.request(request(1)));
  ASSERT_TRUE(fence.request(request(2)));
  EXPECT_EQ(fence.observe(sample(101, 1.202), false, 16, 17)->request_sequence, 2U);
}

TEST(PhysicsStepFence, ResetInvalidatesPendingRequestAndRejectsPausedOrInvalidSteps)
{
  PhysicsStepFence fence("session-one");
  fence.reset(2);
  ASSERT_TRUE(fence.request(request(1)));
  EXPECT_FALSE(fence.observe(sample(0, 0.0), false, 10, 11).has_value());
  fence.reset(3);
  EXPECT_FALSE(fence.observe(sample(1, 0.002, "session-one", 3), false, 12, 13).has_value());
  EXPECT_FALSE(fence.request(request(2, 2)));
  ASSERT_TRUE(fence.request(request(1, 3)));
  EXPECT_FALSE(fence.observe(sample(1, 0.002, "session-one", 3), true, 14, 15).has_value());
  EXPECT_EQ(fence.observe(sample(2, 0.004, "session-one", 3), false, 16, 17)->request_sequence, 1U);
}

TEST(PhysicsStepFence, BindsTheMarkedStepToItsOriginalMonotonicInterval)
{
  PhysicsStepFence fence("session-one");
  fence.reset(2);
  ASSERT_TRUE(fence.request(request(1)));
  auto incomplete = sample(100, 1.2);
  incomplete.model_qvel[0] = std::numeric_limits<double>::quiet_NaN();
  EXPECT_FALSE(fence.observe(incomplete, false, 90, 99).has_value());
  incomplete = sample(100, 1.2);
  incomplete.truncated = true;
  EXPECT_FALSE(fence.observe(incomplete, false, 90, 99).has_value());
  const auto first = fence.observe(sample(100, 1.2), false, 100, 110);
  ASSERT_TRUE(first.has_value());
  EXPECT_EQ(first->clock_interval_begin_monotonic_ns, 100);
  EXPECT_EQ(first->clock_interval_end_monotonic_ns, 110);
  EXPECT_EQ(first->marked_physics_step, 100U);
  EXPECT_DOUBLE_EQ(first->marked_simulation_time_s, 1.2);

  ASSERT_TRUE(fence.request(request(2)));
  EXPECT_FALSE(fence.observe(sample(101, 1.202), false, 109, 120).has_value());
  EXPECT_FALSE(fence.observe(sample(101, 1.202), false, 120, 119).has_value());
  const auto second = fence.observe(sample(101, 1.202), false, 111, 120);
  ASSERT_TRUE(second.has_value());
  EXPECT_EQ(second->clock_interval_begin_monotonic_ns, 111);
  EXPECT_EQ(second->clock_interval_end_monotonic_ns, 120);
}
}  // namespace
