// Copyright 2026 zjumty
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Phase 3b.2 RED: the socket must detect SOGB v2 before legacy dispatch, parse
// outside the gate lock and consume the reservation once via admit_bound_action.
//
// Planned API:
//   bool is_bound_reservation_frame(const std::vector<uint8_t> & frame);
//   ControllerGoalAdmission::BoundReserveStatus handle_bound_reservation_frame(
//     ControllerGoalAdmission & gate, const std::vector<uint8_t> & frame,
//     ControllerReservationRole expected_role);

#include <gtest/gtest.h>

#include <cstdint>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

#include "so101_mujoco_support/controller_goal_admission.hpp"
#include "so101_mujoco_support/controller_reservation_protocol.hpp"

namespace
{

using so101_mujoco_support::BoundReserveStatus;
using so101_mujoco_support::ControllerGoalAdmission;
using so101_mujoco_support::ControllerReservationCapability;
using so101_mujoco_support::ControllerReservationRole;
using so101_mujoco_support::ServiceControllerIdentity;
using so101_mujoco_support::handle_bound_reservation_frame;
using so101_mujoco_support::is_bound_reservation_frame;

std::string fixture_path(const char * name)
{
  const std::string file(__FILE__);
  return file.substr(0, file.find_last_of('/')) + "/fixtures/" + name;
}

std::vector<uint8_t> golden_frame()
{
  std::ifstream input(fixture_path("bound_frame_v2.bin"), std::ios::binary);
  return std::vector<uint8_t>(std::istreambuf_iterator<char>(input),
                              std::istreambuf_iterator<char>());
}

int64_t g_now = 9906000000;

}  // namespace

TEST(Gate6BoundSocket, SogbV2IsDetectedBeforeLegacyDispatch)
{
  const auto bound = golden_frame();
  EXPECT_TRUE(is_bound_reservation_frame(bound));
  std::vector<uint8_t> legacy{'S', 'O', 'G', 'R', 1, 1};
  EXPECT_FALSE(is_bound_reservation_frame(legacy));
}

TEST(Gate6BoundSocket, WrongCapabilityOrRoleIsRejected)
{
  ControllerGoalAdmission gate([&]() {return g_now;}, 1000000000, 1048576, 2048,
    ServiceControllerIdentity{ControllerReservationRole::ARM,
      "inc-1", "boot-1"});
  ASSERT_TRUE(gate.arm(1));
  const auto frame = golden_frame();
  ControllerReservationCapability wrong{};
  wrong.fill(0x11);
  EXPECT_THROW(
    handle_bound_reservation_frame(gate, frame, ControllerReservationRole::ARM, wrong),
    std::exception);
  ControllerReservationCapability good{};
  good.fill(0x5a);
  EXPECT_THROW(
    handle_bound_reservation_frame(gate, frame, ControllerReservationRole::GRIPPER, good),
    std::exception);
}

TEST(Gate6BoundSocket, BoundFrameReservesThroughTheGateAndConsumesOnce)
{
  ControllerReservationCapability capability{};
  capability.fill(0x5a);
  ControllerGoalAdmission gate([&]() {return g_now;}, 1000000000, 1048576, 2048,
    ServiceControllerIdentity{ControllerReservationRole::ARM,
      "inc-1", "boot-1"});
  ASSERT_TRUE(gate.arm(1));
  const auto frame = golden_frame();
  const auto capability_from_fixture = []() {
      ControllerReservationCapability value{};
      value.fill(0x5a);                       // the fixture capability, tests only
      return value;
    };
  EXPECT_EQ(handle_bound_reservation_frame(gate, frame, ControllerReservationRole::ARM,
                                          capability_from_fixture()),
            BoundReserveStatus::ACCEPTED);
  // a second identical frame is a replay and closes the gate
  EXPECT_NE(handle_bound_reservation_frame(gate, frame, ControllerReservationRole::ARM,
                                          capability_from_fixture()),
            BoundReserveStatus::ACCEPTED);
}
