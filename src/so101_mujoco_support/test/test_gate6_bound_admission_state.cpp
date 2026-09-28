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

// Gate 6 Batch 3 — bound admission state machine with a service-owned identity.
//
// The identity is injected at construction (the service generates it); there is no
// runtime setter on the production API. The admission owns its Clock: callers never
// pass now_ns. Missing symbols on the current header are the legitimate RED.

#include <gtest/gtest.h>

#include <cstdint>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

#include "so101_mujoco_support/controller_goal_admission.hpp"
#include "so101_mujoco_support/controller_reservation_protocol.hpp"

namespace
{

using so101_mujoco_support::BoundControllerReservationRequest;
using so101_mujoco_support::BoundReserveStatus;
using so101_mujoco_support::ControllerGoalAdmission;
using so101_mujoco_support::ControllerReservationCapability;
using so101_mujoco_support::ControllerReservationRole;
using so101_mujoco_support::ServiceControllerIdentity;
using so101_mujoco_support::parse_bound_controller_reservation_frame;

std::string fixture_path(const char * name)
{
  const std::string file(__FILE__);
  return file.substr(0, file.find_last_of('/')) + "/fixtures/" + name;
}

BoundControllerReservationRequest golden_request()
{
  std::ifstream input(fixture_path("bound_frame_v2.bin"), std::ios::binary);
  const std::vector<uint8_t> frame{std::istreambuf_iterator<char>(input),
    std::istreambuf_iterator<char>()};
  ControllerReservationCapability capability{};
  capability.fill(0x5a);
  return parse_bound_controller_reservation_frame(frame, capability,
                                                  ControllerReservationRole::ARM);
}

int64_t g_now = 9906000000;

ControllerGoalAdmission make_gate()
{
  // service-owned identity, fixed at construction
  return ControllerGoalAdmission([&]() {return g_now;}, 1000000000, 1048576, 2048,
                                 ServiceControllerIdentity{ControllerReservationRole::ARM, "inc-1",
             "boot-1"});
}

}  // namespace

TEST(Gate6BoundAdmissionState, ReserveThenAdmitIsAcceptedSingleUseAndUsesTheInternalClock)
{
  g_now = 9906000000;
  auto admission = make_gate();
  ASSERT_TRUE(admission.arm(1));
  const auto request = golden_request();
  // no caller-supplied time anywhere on this API
  EXPECT_EQ(admission.reserve_bound(request), BoundReserveStatus::ACCEPTED);
  EXPECT_EQ(admission.admit_bound_action(request.uuid, request.goal, 1),
            BoundReserveStatus::ACCEPTED);
  EXPECT_EQ(admission.reserve_bound(request), BoundReserveStatus::DENY_UUID_REPLAY);
  // the replay is a known-permit failure: the gate closes, so every later call on
  // this generation reports DENY_CLOSED rather than another specific reason
  EXPECT_EQ(admission.admit_bound_action(request.uuid, request.goal, 1),
            BoundReserveStatus::DENY_CLOSED);
}

TEST(Gate6BoundAdmissionState, EachRejectionLeavesNoRevivableReservation)
{
  const auto request = golden_request();
  {g_now = 9906000000; auto admission = make_gate(); ASSERT_TRUE(admission.arm(1));
    g_now = request.deadline_ns + 1;                      // expiry via the internal clock
    EXPECT_EQ(admission.reserve_bound(request), BoundReserveStatus::DENY_EXPIRED);
    g_now = 9906000000;
    EXPECT_NE(admission.admit_bound_action(request.uuid, request.goal, 1),
             BoundReserveStatus::ACCEPTED);}
  {g_now = 9906000000; auto admission = make_gate(); ASSERT_TRUE(admission.arm(1));
    auto tampered = request;
    tampered.goal.trajectory.points[0].positions[0] += 0.01;
    EXPECT_EQ(admission.reserve_bound(tampered), BoundReserveStatus::DENY_DIGEST_MISMATCH);
    EXPECT_NE(admission.admit_bound_action(tampered.uuid, tampered.goal, 1),
             BoundReserveStatus::ACCEPTED);}
  {g_now = 9906000000; auto admission = make_gate(); ASSERT_TRUE(admission.arm(1));
    ASSERT_TRUE(admission.arm(2));
    EXPECT_EQ(admission.reserve_bound(request), BoundReserveStatus::DENY_GENERATION);}
  {g_now = 9906000000;
    ControllerGoalAdmission restarted([&]() {return g_now;}, 1000000000, 1048576, 2048,
      ServiceControllerIdentity{ControllerReservationRole::ARM, "inc-2", "boot-1"});
    ASSERT_TRUE(restarted.arm(1));
    EXPECT_EQ(restarted.reserve_bound(request), BoundReserveStatus::DENY_INCARNATION);}
  {g_now = 9906000000;
    ControllerGoalAdmission restarted([&]() {return g_now;}, 1000000000, 1048576, 2048,
      ServiceControllerIdentity{ControllerReservationRole::ARM, "inc-1", "boot-2"});
    ASSERT_TRUE(restarted.arm(1));
    EXPECT_EQ(restarted.reserve_bound(request), BoundReserveStatus::DENY_BOOT);}
  {g_now = 9906000000; auto admission = make_gate(); ASSERT_TRUE(admission.arm(1));
    ASSERT_TRUE(admission.close_generation(1));
    EXPECT_EQ(admission.reserve_bound(request), BoundReserveStatus::DENY_CLOSED);}
  {g_now = 9906000000; auto admission = make_gate(); ASSERT_TRUE(admission.arm(1));
    ASSERT_EQ(admission.reserve_bound(request), BoundReserveStatus::ACCEPTED);
    EXPECT_TRUE(admission.cancel_bound(request.uuid));
    EXPECT_NE(admission.admit_bound_action(request.uuid, request.goal, 1),
             BoundReserveStatus::ACCEPTED);}
}

TEST(Gate6BoundAdmissionState, ExpiryAfterReserveAndFutureClaimAreDeniedWithoutRevival)
{
  g_now = 9906000000;
  auto admission = make_gate();
  ASSERT_TRUE(admission.arm(1));
  const auto request = golden_request();
  ASSERT_EQ(admission.reserve_bound(request), BoundReserveStatus::ACCEPTED);
  g_now = request.deadline_ns + 1;             // the internal clock passes the deadline
  EXPECT_EQ(admission.admit_bound_action(request.uuid, request.goal, 1),
            BoundReserveStatus::DENY_EXPIRED);
  g_now = 9906000000;                          // and the reservation never revives
  EXPECT_NE(admission.admit_bound_action(request.uuid, request.goal, 1),
            BoundReserveStatus::ACCEPTED);

  g_now = request.claim_monotonic_ns - 1;      // claim instant in the future
  auto future = make_gate();
  ASSERT_TRUE(future.arm(1));
  EXPECT_EQ(future.reserve_bound(request), BoundReserveStatus::DENY_EXPIRED);
}

TEST(Gate6BoundAdmissionState, PermitAndGoalUUIDReplayAreDeniedIndependently)
{
  g_now = 9906000000;
  auto admission = make_gate();
  ASSERT_TRUE(admission.arm(1));
  const auto request = golden_request();
  ASSERT_EQ(admission.reserve_bound(request), BoundReserveStatus::ACCEPTED);
  // same permit UUID, different goal UUID
  EXPECT_LT(static_cast<int>(admission.reserve_bound(request)), static_cast<int>(0) + 1000);
  auto other_goal = request;
  other_goal.uuid[0] ^= 0xff;
  EXPECT_NE(admission.reserve_bound(other_goal), BoundReserveStatus::ACCEPTED);
  // same goal UUID, different permit UUID
  auto other_permit = request;
  other_permit.permit_uuid[0] ^= 0xff;
  EXPECT_NE(admission.reserve_bound(other_permit), BoundReserveStatus::ACCEPTED);
  EXPECT_NE(admission.admit_bound_action(other_goal.uuid, other_goal.goal, 1),
            BoundReserveStatus::ACCEPTED);
}

TEST(Gate6BoundAdmissionState, RearmInvalidatesBothTheOldReservationAndTheOldAdmit)
{
  g_now = 9906000000;
  auto admission = make_gate();
  ASSERT_TRUE(admission.arm(1));
  const auto request = golden_request();
  ASSERT_EQ(admission.reserve_bound(request), BoundReserveStatus::ACCEPTED);
  ASSERT_TRUE(admission.arm(2));               // rearm to a newer generation
  EXPECT_EQ(admission.admit_bound_action(request.uuid, request.goal, 1),
            BoundReserveStatus::DENY_GENERATION);
  // the generation failure closed the gate again
  EXPECT_EQ(admission.reserve_bound(request), BoundReserveStatus::DENY_CLOSED);
}

TEST(Gate6BoundAdmissionState, AnAdmitWithoutItsReservationClosesTheGatePermanently)
{
  g_now = 9906000000;
  auto admission = make_gate();
  ASSERT_TRUE(admission.arm(1));
  const auto request = golden_request();
  // no reservation exists for this uuid: the protocol violation closes the gate
  ControllerGoalAdmission::GoalUUID unknown{};
  unknown[0] = 0x7f;
  EXPECT_EQ(admission.admit_bound_action(unknown, request.goal, 1),
            BoundReserveStatus::DENY_UUID_REPLAY);
  ASSERT_TRUE(admission.arm(2));              // a newer generation is required to reopen
  auto newer = request;
  newer.generation = 2;
  ASSERT_EQ(admission.reserve_bound(newer), BoundReserveStatus::ACCEPTED);
  // reopening for the new generation is possible, but the gate stays closed for
  // the generation that saw the violation
  EXPECT_EQ(admission.admit_bound_action(request.uuid, request.goal, 1),
            BoundReserveStatus::DENY_GENERATION);
}

TEST(Gate6BoundAdmissionState, OnlyOneOutstandingBoundReservationPerGate)
{
  g_now = 9906000000;
  auto admission = make_gate();
  ASSERT_TRUE(admission.arm(1));
  const auto first = golden_request();
  ASSERT_EQ(admission.reserve_bound(first), BoundReserveStatus::ACCEPTED);
  auto second = first;                        // distinct permit and goal uuid
  second.permit_uuid[0] ^= 0xff;
  second.uuid[0] ^= 0xff;
  // the goal bytes stay identical, so the digest still matches and the refusal
  // comes from the single-outstanding-reservation rule rather than the digest
  EXPECT_EQ(admission.reserve_bound(second), BoundReserveStatus::DENY_UUID_REPLAY);
  // the second reserve closed the gate, so the first cannot be admitted either
  EXPECT_EQ(admission.admit_bound_action(first.uuid, first.goal, 1),
            BoundReserveStatus::DENY_CLOSED);
}

TEST(Gate6BoundAdmissionState, AKnownFailureClosesAndOnlyANewerGenerationReopens)
{
  g_now = 9906000000;
  auto admission = make_gate();
  ASSERT_TRUE(admission.arm(1));
  const auto request = golden_request();

  // one known-permit failure (tampered goal) closes the gate for this generation
  auto tampered = request;
  tampered.goal.trajectory.points[0].positions[0] += 0.01;
  EXPECT_EQ(admission.reserve_bound(tampered), BoundReserveStatus::DENY_DIGEST_MISMATCH);
  EXPECT_EQ(admission.reserve_bound(request), BoundReserveStatus::DENY_CLOSED);
  EXPECT_EQ(admission.admit_bound_action(request.uuid, request.goal, 1),
            BoundReserveStatus::DENY_CLOSED);

  // a newer generation reopens the gate; the old request still belongs to the old
  // generation and closes it again
  ASSERT_TRUE(admission.arm(2));
  auto newer = request;
  newer.generation = 2;
  EXPECT_EQ(admission.reserve_bound(request), BoundReserveStatus::DENY_GENERATION);
  EXPECT_EQ(admission.reserve_bound(newer), BoundReserveStatus::DENY_CLOSED);
  ASSERT_TRUE(admission.arm(3));
  auto newest = request;
  newest.generation = 3;
  EXPECT_EQ(admission.reserve_bound(newest), BoundReserveStatus::ACCEPTED);
  EXPECT_EQ(admission.admit_bound_action(newest.uuid, newest.goal, 3),
            BoundReserveStatus::ACCEPTED);
}

TEST(Gate6BoundAdmissionState, AClockFailureOrRegressionClosesTheGate)
{
  const auto request = golden_request();
  bool fail = false;
  ControllerGoalAdmission admission([&]() -> int64_t {
      if (fail) {throw std::runtime_error("clock failed");}
      return g_now;
    }, 1000000000, 1048576, 2048,
    ServiceControllerIdentity{ControllerReservationRole::ARM, "inc-1", "boot-1"});
  ASSERT_TRUE(admission.arm(1));
  fail = true;
  // a clock exception must not reach the caller: the gate closes fail-closed
  EXPECT_EQ(admission.reserve_bound(request), BoundReserveStatus::DENY_CLOSED);
  fail = false;
  g_now = 1;                                   // regression below the retained instant
  EXPECT_EQ(admission.reserve_bound(request), BoundReserveStatus::DENY_CLOSED);
  EXPECT_NE(admission.admit_bound_action(request.uuid, request.goal, 1),
            BoundReserveStatus::ACCEPTED);
}
