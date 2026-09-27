#include <gtest/gtest.h>

#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "so101_mujoco_support/controller_reservation_protocol.hpp"

namespace
{
using so101_mujoco_support::ControllerReservationCapability;
using so101_mujoco_support::ReservationReplyStatus;
using so101_mujoco_support::encode_controller_reservation_reply;
using so101_mujoco_support::parse_controller_reservation_frame;

ControllerReservationCapability capability()
{
  ControllerReservationCapability value{};
  value.fill(0xa5);
  return value;
}

std::vector<uint8_t> fixture_payload()
{
  const auto path = std::filesystem::path(__FILE__).parent_path() /
    "fixtures/follow_joint_trajectory_goal.cdr.hex";
  std::ifstream input(path);
  std::string hex;
  input >> hex;
  std::vector<uint8_t> bytes;
  for (size_t i = 0; i + 1 < hex.size(); i += 2) {
    bytes.push_back(static_cast<uint8_t>(std::stoul(hex.substr(i, 2), nullptr, 16)));
  }
  return bytes;
}

std::vector<uint8_t> valid_frame()
{
  const auto payload = fixture_payload();
  std::vector<uint8_t> frame{0, 0, 1, 62, 'S', 'O', 'G', 'R', 1, 1};
  const auto key = capability();
  frame.insert(frame.end(), key.begin(), key.end());
  frame.insert(frame.end(), {0, 0, 0, 0, 0, 0, 0, 5});
  frame.insert(frame.end(), 16, 0x11);
  frame.insert(frame.end(), payload.begin(), payload.end());
  return frame;
}
}  // namespace

TEST(ControllerReservationProtocol, PythonGoalFrameDecodesEveryReservedField)
{
  const auto frame = valid_frame();
  ASSERT_EQ(frame.size(), 322u);
  const auto request = parse_controller_reservation_frame(frame, capability());
  EXPECT_EQ(request.generation, 5u);
  EXPECT_EQ(request.uuid, (std::array<uint8_t, 16>{
    0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11,
    0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11}));
  const auto & goal = request.goal;
  EXPECT_EQ(goal.trajectory.header.stamp.sec, 123);
  EXPECT_EQ(goal.trajectory.header.stamp.nanosec, 456u);
  EXPECT_EQ(goal.trajectory.header.frame_id, "base_link");
  EXPECT_EQ(goal.trajectory.joint_names, (std::vector<std::string>{"1", "2"}));
  ASSERT_EQ(goal.trajectory.points.size(), 1u);
  EXPECT_EQ(goal.trajectory.points[0].positions, (std::vector<double>{0.125, -0.25}));
  EXPECT_EQ(goal.trajectory.points[0].velocities, (std::vector<double>{0.0, 0.5}));
  EXPECT_EQ(goal.trajectory.points[0].accelerations, (std::vector<double>{0.125, -0.125}));
  EXPECT_EQ(goal.trajectory.points[0].time_from_start.nanosec, 2000000u);
  ASSERT_EQ(goal.path_tolerance.size(), 1u);
  EXPECT_EQ(goal.path_tolerance[0].name, "1");
  EXPECT_DOUBLE_EQ(goal.path_tolerance[0].position, 0.001);
  ASSERT_EQ(goal.goal_tolerance.size(), 1u);
  EXPECT_EQ(goal.goal_tolerance[0].name, "2");
  EXPECT_DOUBLE_EQ(goal.goal_tolerance[0].velocity, 0.005);
  EXPECT_EQ(goal.goal_time_tolerance.nanosec, 50000000u);
  EXPECT_TRUE(goal.multi_dof_trajectory.points.empty());
  EXPECT_TRUE(goal.component_path_tolerance.empty());
  EXPECT_TRUE(goal.component_goal_tolerance.empty());

  EXPECT_EQ(encode_controller_reservation_reply(ReservationReplyStatus::ACK, 5),
    (std::array<uint8_t, 16>{'S', 'O', 'G', 'A', 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5}));
}

TEST(ControllerReservationProtocol, RejectsMalformedOrUnauthenticatedFrames)
{
  const auto valid = valid_frame();
  ASSERT_EQ(valid.size(), 322u);
  auto wrong_key = capability();
  wrong_key[0] ^= 1;
  EXPECT_THROW(parse_controller_reservation_frame(valid, wrong_key), std::invalid_argument);
  wrong_key = capability();
  wrong_key[31] ^= 1;
  EXPECT_THROW(parse_controller_reservation_frame(valid, wrong_key), std::invalid_argument);
  for (const auto [offset, value] : std::vector<std::pair<size_t, uint8_t>>{
    {0, 1}, {7, 'X'}, {8, 2}, {9, 2}})
  {
    auto frame = valid;
    frame[offset] = value;
    EXPECT_THROW(parse_controller_reservation_frame(frame, capability()), std::invalid_argument);
  }
  auto truncated = valid;
  truncated.pop_back();
  EXPECT_THROW(parse_controller_reservation_frame(truncated, capability()), std::invalid_argument);
  auto oversized = valid;
  oversized[0] = 1;
  EXPECT_THROW(parse_controller_reservation_frame(oversized, capability()), std::invalid_argument);
  auto zero_uuid = valid;
  for (size_t i = 50; i < 66; ++i) {
    zero_uuid[i] = 0;
  }
  EXPECT_THROW(parse_controller_reservation_frame(zero_uuid, capability()), std::invalid_argument);
  auto zero_generation = valid;
  for (size_t i = 42; i < 50; ++i) {
    zero_generation[i] = 0;
  }
  EXPECT_THROW(parse_controller_reservation_frame(zero_generation, capability()),
    std::invalid_argument);
  auto invalid_cdr = valid;
  invalid_cdr.resize(70);
  invalid_cdr[2] = 0;
  invalid_cdr[3] = 66;
  EXPECT_THROW(parse_controller_reservation_frame(invalid_cdr, capability()),
    std::invalid_argument);
}
