// Copyright 2026 SO-101 maintainers

#include <gtest/gtest.h>

#include "so101_mujoco_support/controller_ingress_witness.hpp"

namespace
{
using so101_mujoco_support::ControllerIngressWitness;

TEST(ControllerIngressWitness, RefusesSnapshotWhileNativeCallbackIsInFlight)
{
  int64_t now = 100;
  ControllerIngressWitness witness([&now] {return now;});
  ASSERT_TRUE(witness.snapshot().has_value());
  EXPECT_EQ(witness.snapshot()->sequence, 0U);
  {
    now = 110;
    auto ingress = witness.enter();
    EXPECT_FALSE(witness.snapshot().has_value());
    now = 120;
  }
  now = 130;
  const auto snapshot = witness.snapshot();
  ASSERT_TRUE(snapshot.has_value());
  EXPECT_EQ(snapshot->sequence, 1U);
  EXPECT_EQ(snapshot->last_ingress_monotonic_ns, 120);
  EXPECT_EQ(snapshot->observed_monotonic_ns, 130);
}

TEST(ControllerIngressWitness, LatchesClockRegressionAcrossCallbacksAndQueries)
{
  int64_t now = 100;
  ControllerIngressWitness witness([&now] {return now;});
  {
    now = 110;
    auto ingress = witness.enter();
    now = 120;
  }
  now = 119;
  EXPECT_FALSE(witness.snapshot().has_value());
  now = 130;
  EXPECT_FALSE(witness.snapshot().has_value());
}

TEST(ControllerIngressWitness, CountsRejectedAndAcceptedCallbacksAsSeparateIngress)
{
  int64_t now = 100;
  ControllerIngressWitness witness([&now] {return now;});
  for (int index = 0; index != 3; ++index) {
    now += 10;
    auto ingress = witness.enter();
    now += 5;
  }
  now += 5;
  const auto snapshot = witness.snapshot();
  ASSERT_TRUE(snapshot.has_value());
  EXPECT_EQ(snapshot->sequence, 3U);
  EXPECT_EQ(snapshot->last_ingress_monotonic_ns, 145);
}
}  // namespace
