#include <gtest/gtest.h>
#include <time.h>
#include <unistd.h>

#include <array>
#include <cstdint>
#include <limits>

#include "so101_mujoco_support/head_revocation_transport.h"

namespace
{
uint64_t current_ns()
{
  timespec now{};
  EXPECT_EQ(clock_gettime(CLOCK_MONOTONIC, &now), 0);
  return static_cast<uint64_t>(now.tv_sec) * 1000000000ULL + now.tv_nsec;
}

uint32_t call(uint64_t request, uint64_t budget, uint32_t operation,
  So101HeadRevocationResult & result, bool simulation = false)
{
  std::array<uint8_t, 32> capability{};capability[0] = 1;
  const auto transport = simulation ? so101_head_revocation_simulation_exchange :
    so101_head_revocation_exchange;
  return transport("/no/actual/socket", capability.data(), 5,
    geteuid(), getpid(), 1, request, budget, operation, &result);
}
}  // namespace

TEST(HeadRevocationTransport, DelayedNativeEntryConsumesOriginalDeadline)
{
  So101HeadRevocationResult result{};
  const auto request = current_ns() - 3000000;
  EXPECT_EQ(call(request, 2000000, 2, result), 5U);
  EXPECT_EQ(result.phase, 0U);
  EXPECT_EQ(result.phases_present, 0U);
  EXPECT_EQ(result.ack_ns, 0U);
  EXPECT_GE(result.entry_ns, request + 2000000);
}

TEST(HeadRevocationTransport, ExcessBudgetAndClockOverflowNeverReachSocket)
{
  So101HeadRevocationResult result{};
  EXPECT_EQ(call(current_ns(), 2000001, 2, result), 1U);
  EXPECT_EQ(result.phases_present, 0U);
  EXPECT_EQ(call(std::numeric_limits<uint64_t>::max(), 2000000, 2, result), 1U);
  EXPECT_EQ(result.ack_ns, 0U);
}

TEST(HeadRevocationTransport, InterfaceCannotEncodeArmOrReserve)
{
  So101HeadRevocationResult result{};
  for (uint32_t operation : {0U, 3U, 4U}) {
    EXPECT_EQ(call(current_ns(), 2000000, operation, result), 1U);
    EXPECT_EQ(result.phases_present, 0U);
    EXPECT_EQ(result.reply_size, 0U);
  }
}

TEST(HeadRevocationTransport, ExplicitSimulationBudgetIsFiniteAndIncludesDelayedEntry)
{
  EXPECT_EQ(so101_head_revocation_simulation_max_budget_ns(), 250000000U);
  So101HeadRevocationResult result{};
  EXPECT_EQ(call(current_ns() - 60000000, 50000000, 2, result, true), 5U);
  EXPECT_EQ(result.phases_present, 0U);
  EXPECT_EQ(result.ack_ns, 0U);
  EXPECT_EQ(call(current_ns(), 250000001, 2, result, true), 1U);
  EXPECT_EQ(result.phases_present, 0U);
  EXPECT_EQ(call(current_ns(), 0, 2, result, true), 1U);
  EXPECT_EQ(call(std::numeric_limits<uint64_t>::max(), 50000000, 2, result, true), 1U);
  // Within the explicit budget, the unchanged private-path check is reached.
  EXPECT_EQ(call(current_ns(), 50000000, 2, result, true), 2U);
}

TEST(HeadRevocationTransport, ExplicitSimulationCannotEncodeArmOrReserve)
{
  So101HeadRevocationResult result{};
  for (uint32_t operation : {0U, 3U, 4U}) {
    EXPECT_EQ(call(current_ns(), 50000000, operation, result, true), 1U);
    EXPECT_EQ(result.phases_present, 0U);
    EXPECT_EQ(result.reply_size, 0U);
  }
}
