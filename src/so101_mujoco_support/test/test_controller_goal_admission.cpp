#include <gtest/gtest.h>

#include <array>
#include <cstdint>
#include <vector>

#include "so101_mujoco_support/controller_goal_admission.hpp"

namespace
{
using so101_mujoco_support::ControllerGoalAdmission;
using Result = ControllerGoalAdmission::Result;

ControllerGoalAdmission::GoalUUID uuid(uint8_t value)
{
  ControllerGoalAdmission::GoalUUID id{};
  id.fill(value);
  return id;
}
}  // namespace

TEST(ControllerGoalAdmission, DefaultsClosedAndConsumesExactReservationOnce)
{
  int64_t now = 1000;
  ControllerGoalAdmission gate([&now]() {return now;}, 100, 1024);
  const auto id = uuid(1);
  const std::vector<uint8_t> goal{1, 2, 3};
  EXPECT_EQ(gate.admit(id, goal, 1), Result::DENY_CLOSED);
  ASSERT_TRUE(gate.arm(1));
  ASSERT_TRUE(gate.reserve(id, goal, 1));
  now = 1099;
  EXPECT_EQ(gate.admit(id, goal, 1), Result::ALLOW);
  EXPECT_EQ(gate.admit(id, goal, 1), Result::DENY_FAULT);
  EXPECT_FALSE(gate.arm(1));
  EXPECT_TRUE(gate.arm(2));
}

TEST(ControllerGoalAdmission, WrongGoalContentOrUuidLatchesTheWholeGenerationClosed)
{
  int64_t now = 1000;
  ControllerGoalAdmission gate([&now]() {return now;}, 100, 1024);
  ASSERT_TRUE(gate.arm(5));
  ASSERT_TRUE(gate.reserve(uuid(1), {1, 2, 3}, 5));
  EXPECT_EQ(gate.admit(uuid(1), {1, 2, 4}, 5), Result::DENY_FAULT);
  EXPECT_EQ(gate.admit(uuid(1), {1, 2, 3}, 5), Result::DENY_CLOSED);
  ASSERT_TRUE(gate.arm(6));
  ASSERT_TRUE(gate.reserve(uuid(1), {1, 2, 3}, 6));
  EXPECT_EQ(gate.admit(uuid(2), {1, 2, 3}, 6), Result::DENY_FAULT);
  EXPECT_EQ(gate.admit(uuid(1), {1, 2, 3}, 6), Result::DENY_CLOSED);
}

TEST(ControllerGoalAdmission, DeadlineAndClockRegressionFailClosed)
{
  int64_t now = 1000;
  ControllerGoalAdmission gate([&now]() {return now;}, 100, 1024);
  ASSERT_TRUE(gate.arm(1));
  ASSERT_TRUE(gate.reserve(uuid(1), {1}, 1));
  now = 1100;
  EXPECT_EQ(gate.admit(uuid(1), {1}, 1), Result::DENY_FAULT);
  ASSERT_TRUE(gate.arm(2));
  ASSERT_TRUE(gate.reserve(uuid(1), {1}, 2));
  now = 1099;
  EXPECT_EQ(gate.admit(uuid(1), {1}, 2), Result::DENY_FAULT);
}

TEST(ControllerGoalAdmission, RejectsMalformedAndDuplicateReservationsWithoutFallback)
{
  int64_t now = 1000;
  ControllerGoalAdmission gate([&now]() {return now;}, 100, 4);
  ASSERT_TRUE(gate.arm(1));
  EXPECT_FALSE(gate.reserve(uuid(0), {1}, 1));
  EXPECT_EQ(gate.admit(uuid(1), {1}, 1), Result::DENY_CLOSED);
  ASSERT_TRUE(gate.arm(2));
  EXPECT_FALSE(gate.reserve(uuid(1), {1, 2, 3, 4, 5}, 2));
  ASSERT_TRUE(gate.arm(3));
  ASSERT_TRUE(gate.reserve(uuid(1), {1}, 3));
  EXPECT_FALSE(gate.reserve(uuid(1), {1}, 3));
  EXPECT_EQ(gate.admit(uuid(1), {1}, 3), Result::DENY_CLOSED);
}
