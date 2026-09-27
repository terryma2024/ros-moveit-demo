#include <gtest/gtest.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "control_msgs/action/follow_joint_trajectory.hpp"
#include "rclcpp/serialization.hpp"
#include "rclcpp/serialized_message.hpp"
#include "so101_mujoco_support/controller_goal_admission.hpp"

namespace
{
using so101_mujoco_support::ControllerGoalAdmission;
using Goal = control_msgs::action::FollowJointTrajectory::Goal;
using Result = ControllerGoalAdmission::Result;

ControllerGoalAdmission::GoalUUID uuid(uint8_t value)
{
  ControllerGoalAdmission::GoalUUID id{};
  id.fill(value);
  return id;
}

Goal expected_goal()
{
  Goal goal;
  goal.trajectory.header.stamp.sec = 123;
  goal.trajectory.header.stamp.nanosec = 456;
  goal.trajectory.header.frame_id = "base_link";
  goal.trajectory.joint_names = {"1", "2"};
  trajectory_msgs::msg::JointTrajectoryPoint point;
  point.positions = {0.125, -0.25};
  point.velocities = {0.0, 0.5};
  point.accelerations = {0.125, -0.125};
  point.time_from_start.nanosec = 2000000;
  goal.trajectory.points = {point};
  control_msgs::msg::JointTolerance path;
  path.name = "1";
  path.position = 0.001;
  path.velocity = 0.002;
  path.acceleration = 0.003;
  goal.path_tolerance = {path};
  control_msgs::msg::JointTolerance terminal;
  terminal.name = "2";
  terminal.position = 0.004;
  terminal.velocity = 0.005;
  terminal.acceleration = 0.006;
  goal.goal_tolerance = {terminal};
  goal.goal_time_tolerance.nanosec = 50000000;
  return goal;
}

std::vector<uint8_t> python_fixture()
{
  const auto path = std::filesystem::path(__FILE__).parent_path() /
    "fixtures/follow_joint_trajectory_goal.cdr.hex";
  std::ifstream input(path);
  std::string hex;
  input >> hex;
  if (hex.size() % 2 != 0) {
    return {};
  }
  std::vector<uint8_t> bytes;
  bytes.reserve(hex.size() / 2);
  for (size_t i = 0; i < hex.size(); i += 2) {
    bytes.push_back(static_cast<uint8_t>(std::stoul(hex.substr(i, 2), nullptr, 16)));
  }
  return bytes;
}
}  // namespace

TEST(ControllerGoalAdmission, PythonCdrDecodesToEveryExpectedTypedField)
{
  const auto bytes = python_fixture();
  ASSERT_EQ(bytes.size(), 256u);
  rclcpp::SerializedMessage serialized(bytes.size());
  auto & raw = serialized.get_rcl_serialized_message();
  std::copy(bytes.begin(), bytes.end(), raw.buffer);
  raw.buffer_length = bytes.size();
  Goal decoded;
  rclcpp::Serialization<Goal>().deserialize_message(&serialized, &decoded);
  EXPECT_EQ(decoded, expected_goal());
}

TEST(ControllerGoalAdmission, DefaultsClosedAndConsumesExactTypedReservationOnce)
{
  int64_t now = 1000;
  ControllerGoalAdmission gate([&now]() {return now;}, 100, 1024);
  const auto id = uuid(1);
  const auto goal = expected_goal();
  EXPECT_EQ(gate.admit(id, goal, 1), Result::DENY_CLOSED);
  ASSERT_TRUE(gate.arm(1));
  ASSERT_TRUE(gate.reserve(id, goal, 1));
  now = 1099;
  EXPECT_EQ(gate.admit(id, goal, 1), Result::ALLOW);
  EXPECT_EQ(gate.admit(id, goal, 1), Result::DENY_FAULT);
  EXPECT_FALSE(gate.arm(1));
  EXPECT_TRUE(gate.arm(2));
}

TEST(ControllerGoalAdmission, AlteredTypedFieldOrUuidClosesTheGeneration)
{
  int64_t now = 1000;
  ControllerGoalAdmission gate([&now]() {return now;}, 100, 1024);
  const auto goal = expected_goal();
  auto altered = goal;
  altered.goal_tolerance[0].velocity = 0.007;
  ASSERT_TRUE(gate.arm(5));
  ASSERT_TRUE(gate.reserve(uuid(1), goal, 5));
  EXPECT_EQ(gate.admit(uuid(1), altered, 5), Result::DENY_FAULT);
  EXPECT_EQ(gate.admit(uuid(1), goal, 5), Result::DENY_CLOSED);
  ASSERT_TRUE(gate.arm(6));
  ASSERT_TRUE(gate.reserve(uuid(1), goal, 6));
  EXPECT_EQ(gate.admit(uuid(2), goal, 6), Result::DENY_FAULT);
  EXPECT_EQ(gate.admit(uuid(1), goal, 6), Result::DENY_CLOSED);
}

TEST(ControllerGoalAdmission, DeadlineAndClockRegressionFailClosed)
{
  int64_t now = 1000;
  ControllerGoalAdmission gate([&now]() {return now;}, 100, 1024);
  const auto goal = expected_goal();
  ASSERT_TRUE(gate.arm(1));
  ASSERT_TRUE(gate.reserve(uuid(1), goal, 1));
  now = 1100;
  EXPECT_EQ(gate.admit(uuid(1), goal, 1), Result::DENY_FAULT);
  ASSERT_TRUE(gate.arm(2));
  ASSERT_TRUE(gate.reserve(uuid(1), goal, 2));
  now = 1099;
  EXPECT_EQ(gate.admit(uuid(1), goal, 2), Result::DENY_FAULT);
}

TEST(ControllerGoalAdmission, RejectsEmptyOversizedAndDuplicateReservations)
{
  int64_t now = 1000;
  ControllerGoalAdmission gate([&now]() {return now;}, 100, 1024);
  const auto goal = expected_goal();
  ASSERT_TRUE(gate.arm(1));
  EXPECT_FALSE(gate.reserve(uuid(0), goal, 1));
  EXPECT_EQ(gate.admit(uuid(1), goal, 1), Result::DENY_CLOSED);
  ASSERT_TRUE(gate.arm(2));
  EXPECT_FALSE(gate.reserve(uuid(1), Goal{}, 2));
  ASSERT_TRUE(gate.arm(3));
  ControllerGoalAdmission tiny_gate([&now]() {return now;}, 100, 4);
  ASSERT_TRUE(tiny_gate.arm(1));
  EXPECT_FALSE(tiny_gate.reserve(uuid(1), goal, 1));
  ASSERT_TRUE(gate.reserve(uuid(1), goal, 3));
  EXPECT_FALSE(gate.reserve(uuid(1), goal, 3));
  EXPECT_EQ(gate.admit(uuid(1), goal, 3), Result::DENY_CLOSED);
}
