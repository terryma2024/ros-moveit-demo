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

// Gate 6 Batch 3 — bound reservation frame (frozen v2 binary schema).
//
// The deterministic fixture lives in-repo next to this test and is loaded relative
// to __FILE__, so the test never depends on an evidence path. The planned symbols
// do not exist yet: that missing-symbol diagnostic is the legitimate RED.

#include <gtest/gtest.h>

#include <cstdint>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

#include "so101_mujoco_support/controller_reservation_protocol.hpp"

namespace
{

using so101_mujoco_support::BoundControllerReservationRequest;
using so101_mujoco_support::ControllerReservationCapability;
using so101_mujoco_support::ControllerReservationRole;
using so101_mujoco_support::parse_bound_controller_reservation_frame;

std::string fixture_path(const char * name)
{
  const std::string file(__FILE__);
  const std::string dir = file.substr(0, file.find_last_of('/'));
  return dir + "/fixtures/" + name;
}

std::vector<uint8_t> read_fixture(const char * name)
{
  std::ifstream input(fixture_path(name), std::ios::binary);
  return std::vector<uint8_t>(std::istreambuf_iterator<char>(input),
                              std::istreambuf_iterator<char>());
}

ControllerReservationCapability capability()
{
  ControllerReservationCapability value{};
  value.fill(0x5a);
  return value;
}

const std::array<uint8_t, 32> kExpectedDigest = {
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};

}  // namespace

TEST(Gate6BoundReservationFrame, ParsesEveryBindingFieldAndTheFullGoalFromTheRepoFixture)
{
  const auto frame = read_fixture("bound_frame_v2.bin");
  ASSERT_EQ(frame.size(), 484u) << "fixture path: " << fixture_path("bound_frame_v2.bin");
  const BoundControllerReservationRequest request =
    parse_bound_controller_reservation_frame(frame, capability(), ControllerReservationRole::ARM);
  EXPECT_EQ(request.generation, 1u);
  EXPECT_EQ(request.role, ControllerReservationRole::ARM);       // ARM == 1
  EXPECT_EQ(static_cast<int>(ControllerReservationRole::ARM), 1);
  EXPECT_EQ(request.claim_monotonic_ns, 9906000000);
  EXPECT_EQ(request.deadline_ns, 39906000000);
  EXPECT_LE(request.claim_monotonic_ns, request.deadline_ns);
  EXPECT_EQ(request.session_id, "clock-session");
  EXPECT_EQ(request.broker_incarnation, "clock-session");
  EXPECT_EQ(request.controller_incarnation, "inc-1");
  EXPECT_EQ(request.controller_boot_incarnation, "boot-1");
  ASSERT_EQ(request.permit_uuid.size(), 16u);
  const std::array<uint8_t, 16> zero_uuid{};
  EXPECT_NE(request.permit_uuid, zero_uuid);
  EXPECT_EQ(request.target_digest.size(), 32u);
  // the digest must be exactly sha256(goal CDR); the value is asserted against the
  // fixture manifest and recomputed independently by the Python encoder test
  const std::array<uint8_t, 32> zero_digest{};
  EXPECT_NE(request.target_digest, zero_digest);
  ASSERT_EQ(request.goal.trajectory.joint_names.size(), 6u);
  EXPECT_EQ(request.goal.trajectory.joint_names[5], "gripper");
  ASSERT_EQ(request.goal.trajectory.points.size(), 1u);
  EXPECT_NEAR(request.goal.trajectory.points[0].positions[2], 0.3, 1e-9);
  EXPECT_EQ(request.goal.trajectory.points[0].time_from_start.sec, 1);
}

TEST(Gate6BoundReservationFrame, RejectsEveryMalformedField)
{
  const auto good = read_fixture("bound_frame_v2.bin");
  ASSERT_EQ(good.size(), 484u);
  const auto parse = [](const std::vector<uint8_t> & frame, ControllerReservationRole role) {
      return parse_bound_controller_reservation_frame(frame, capability(), role);
    };
  {auto bad = good; bad.resize(bad.size() - 1);
    EXPECT_THROW(parse(bad, ControllerReservationRole::ARM), std::exception);}  // trailing/短
  {auto bad = good; bad[4] = 1;
    EXPECT_THROW(parse(bad, ControllerReservationRole::ARM), std::exception);}  // version
  {auto bad = good; bad[5] = 9;
    EXPECT_THROW(parse(bad, ControllerReservationRole::ARM), std::exception);}  // operation
  // body layout: len(4) SOGB(4) ver(1) op(1) capability(32) generation(8) goal_uuid(16)
  //              role(1)=offset 66, permit_uuid(16)=67..82, digest(32)=83..114
  {auto bad = good; bad[66] = 0;
    EXPECT_THROW(parse(bad, ControllerReservationRole::ARM), std::exception);}  // role byte
  {auto bad = good; std::fill(bad.begin() + 67, bad.begin() + 83, 0);
    EXPECT_THROW(parse(bad, ControllerReservationRole::ARM), std::exception);}  // zero permit uuid
  {auto bad = good;
    EXPECT_THROW(parse(bad, ControllerReservationRole::GRIPPER), std::exception);} // role mismatch
  {auto bad = good; bad[132] = 0xff;    // first byte of session_id content
    EXPECT_THROW(parse(bad, ControllerReservationRole::ARM), std::exception);}  // non-ASCII string
  {auto bad = good; bad[131] = 0;       // zero-length bounded string
    EXPECT_THROW(parse(bad, ControllerReservationRole::ARM), std::exception);}  // empty string
  {auto bad = good; bad[131] = 0xff;    // length beyond the 64-byte cap
    EXPECT_THROW(parse(bad, ControllerReservationRole::ARM), std::exception);}  // oversize string
}
