// Copyright 2026 SO-101 maintainers

#include <gtest/gtest.h>

#include "so101_mujoco_support/physics_step_fence.hpp"

namespace
{
using so101_mujoco_support::PhysicsStepFence;
using so101_mujoco_support::msg::PhysicsStepFenceRequest;

PhysicsStepFenceRequest request(uint64_t sequence, uint64_t epoch = 2)
{
  PhysicsStepFenceRequest value;
  value.simulation_session_id = "session-one";
  value.reset_epoch = epoch;
  value.request_sequence = sequence;
  return value;
}

TEST(PhysicsStepFence, MarksOnlyAnAdvancingStepAfterTheRequest)
{
  PhysicsStepFence fence("session-one");
  fence.reset(2);
  EXPECT_FALSE(fence.observe("session-one", 2, 99, 1.198, false).has_value());
  ASSERT_TRUE(fence.request(request(1)));
  EXPECT_FALSE(fence.observe("session-one", 2, 99, 1.198, true).has_value());
  const auto ack = fence.observe("session-one", 2, 100, 1.2, false);
  ASSERT_TRUE(ack.has_value());
  EXPECT_EQ(ack->simulation_session_id, "session-one");
  EXPECT_EQ(ack->reset_epoch, 2U);
  EXPECT_EQ(ack->request_sequence, 1U);
  EXPECT_EQ(ack->marked_physics_step, 100U);
  EXPECT_DOUBLE_EQ(ack->marked_simulation_time_s, 1.2);
  EXPECT_FALSE(fence.observe("session-one", 2, 101, 1.202, false).has_value());
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
  EXPECT_FALSE(fence.observe("other", 2, 100, 1.2, false).has_value());
  EXPECT_FALSE(fence.observe("session-one", 3, 100, 1.2, false).has_value());
  EXPECT_EQ(fence.observe("session-one", 2, 100, 1.2, false)->request_sequence, 1U);
  EXPECT_FALSE(fence.request(request(1)));
  ASSERT_TRUE(fence.request(request(2)));
  EXPECT_EQ(fence.observe("session-one", 2, 101, 1.202, false)->request_sequence, 2U);
}

TEST(PhysicsStepFence, ResetInvalidatesPendingRequestAndRejectsPausedOrInvalidSteps)
{
  PhysicsStepFence fence("session-one");
  fence.reset(2);
  ASSERT_TRUE(fence.request(request(1)));
  EXPECT_FALSE(fence.observe("session-one", 2, 0, 0.0, false).has_value());
  fence.reset(3);
  EXPECT_FALSE(fence.observe("session-one", 3, 1, 0.002, false).has_value());
  EXPECT_FALSE(fence.request(request(2, 2)));
  ASSERT_TRUE(fence.request(request(1, 3)));
  EXPECT_FALSE(fence.observe("session-one", 3, 1, 0.002, true).has_value());
  EXPECT_EQ(fence.observe("session-one", 3, 2, 0.004, false)->request_sequence, 1U);
}
}  // namespace
