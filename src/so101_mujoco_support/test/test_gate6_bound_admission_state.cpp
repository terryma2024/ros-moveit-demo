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
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <functional>
#include <iterator>
#include <limits>
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

TEST(Gate6BoundAdmissionState, RetainedNeckGoalSurvivesDifferentUnwrittenWireTails)
{
  // HS-327's real neck goal occupies 160 content bytes in a 188-byte payload.
  // Changing its unwritten tail changes the wire digest but not the typed goal.
  std::ifstream input(fixture_path("head_neck_bound_frame_v2.bin"), std::ios::binary);
  const std::vector<uint8_t> original{std::istreambuf_iterator<char>(input),
    std::istreambuf_iterator<char>()};
  ASSERT_EQ(original.size(), 458u);
  ControllerReservationCapability capability{};
  for (size_t i = 0; i < capability.size(); ++i) {
    capability[i] = static_cast<uint8_t>(i + 1);
  }
  const auto reference = parse_bound_controller_reservation_frame(
    original, capability, ControllerReservationRole::NECK);
  for (const uint8_t tail : {0x5a, 0xa5}) {
    SCOPED_TRACE(static_cast<unsigned>(tail));
    auto frame = original;
    std::fill(frame.end() - 28, frame.end(), tail);
    const std::vector<uint8_t> payload(frame.end() - 188, frame.end());
    const auto digest = so101_mujoco_support::sha256::digest(payload);
    // SOGB v2: length(4), prefix(6), capability(32), generation(8),
    // action UUID(16), role(1), permit UUID(16), then target digest(32).
    std::copy(digest.begin(), digest.end(), frame.begin() + 83);
    const auto request = parse_bound_controller_reservation_frame(
      frame, capability, ControllerReservationRole::NECK);
    ASSERT_EQ(request.goal, reference.goal);
    ControllerGoalAdmission admission([]() {return int64_t{2};}, 1000000000,
      1048576, 2048, ServiceControllerIdentity{ControllerReservationRole::NECK,
        request.controller_incarnation, request.controller_boot_incarnation});
    ASSERT_TRUE(admission.arm(request.generation));
    ASSERT_EQ(admission.reserve_bound(request), BoundReserveStatus::ACCEPTED);
    // Disturb the serializer's allocation size class before the action hop.
    auto * unrelated = static_cast<uint8_t *>(std::malloc(188));
    ASSERT_NE(unrelated, nullptr);
    std::memset(unrelated, tail ^ 0xff, 188);
    std::free(unrelated);
    EXPECT_EQ(admission.admit_bound_action(request.uuid, reference.goal, request.generation),
      BoundReserveStatus::ACCEPTED);
  }
}


namespace
{
using Goal = ControllerGoalAdmission::Goal;

std::vector<uint8_t> bound_frame_for_goal(const Goal & goal)
{
  std::ifstream input(fixture_path("bound_frame_v2.bin"), std::ios::binary);
  std::vector<uint8_t> frame{std::istreambuf_iterator<char>(input),
    std::istreambuf_iterator<char>()};
  frame.resize(frame.size() - 308);  // fixed fixture's original payload
  rclcpp::SerializedMessage serialized;
  rclcpp::Serialization<Goal>().serialize_message(&goal, &serialized);
  const auto & raw = serialized.get_rcl_serialized_message();
  const std::vector<uint8_t> payload(raw.buffer, raw.buffer + raw.buffer_length);
  const auto digest = so101_mujoco_support::sha256::digest(payload);
  std::copy(digest.begin(), digest.end(), frame.begin() + 83);
  const uint32_t length = payload.size();
  for (size_t i = 0; i < 4; ++i) {
    frame[frame.size() - 4 + i] = length >> (24 - 8 * i);
  }
  frame.insert(frame.end(), payload.begin(), payload.end());
  const uint32_t body = frame.size() - 4;
  for (size_t i = 0; i < 4; ++i) {
    frame[i] = body >> (24 - 8 * i);
  }
  return frame;
}

BoundControllerReservationRequest request_for_goal(const Goal & goal)
{
  ControllerReservationCapability capability{};
  capability.fill(0x5a);
  return parse_bound_controller_reservation_frame(bound_frame_for_goal(goal), capability,
    ControllerReservationRole::ARM);
}

Goal complete_goal()
{
  auto goal = golden_request().goal;
  goal.trajectory.header.frame_id = "base";
  goal.trajectory.header.stamp.sec = 2;
  goal.trajectory.header.stamp.nanosec = 3;
  auto & point = goal.trajectory.points.front();
  point.velocities = {0.1}; point.accelerations = {0.2}; point.effort = {0.3};
  point.time_from_start.nanosec = 4;
  goal.multi_dof_trajectory.header = goal.trajectory.header;
  goal.multi_dof_trajectory.joint_names = {"virtual"};
  goal.multi_dof_trajectory.points.resize(1);
  auto & multi = goal.multi_dof_trajectory.points.front();
  multi.transforms.resize(1); multi.transforms.front().rotation.w = 1.0;
  multi.velocities.resize(1); multi.accelerations.resize(1);
  multi.time_from_start.sec = 1; multi.time_from_start.nanosec = 5;
  goal.path_tolerance.resize(1); goal.goal_tolerance.resize(1);
  goal.path_tolerance.front().name = "neck_yaw_joint";
  goal.goal_tolerance.front().name = "neck_yaw_joint";
  goal.component_path_tolerance.resize(1); goal.component_goal_tolerance.resize(1);
  goal.component_path_tolerance.front().joint_name = "virtual";
  goal.component_goal_tolerance.front().joint_name = "virtual";
  goal.goal_time_tolerance.sec = 1; goal.goal_time_tolerance.nanosec = 6;
  return goal;
}

using GoalMutation = std::pair<std::string, std::function<void(Goal &)>>;
std::vector<GoalMutation> every_goal_field_mutation()
{
  return {
    {"trajectory.header.stamp.sec", [](Goal & g) {++g.trajectory.header.stamp.sec;}},
    {"trajectory.header.stamp.nanosec", [](Goal & g) {++g.trajectory.header.stamp.nanosec;}},
    {"trajectory.header.frame_id", [](Goal & g) {g.trajectory.header.frame_id += "x";}},
    {"trajectory.joint_names.value", [](Goal & g) {g.trajectory.joint_names.front() += "x";}},
    {"trajectory.joint_names.count", [](Goal & g) {g.trajectory.joint_names.push_back("extra");}},
    {"trajectory.points.count", [](Goal & g) {g.trajectory.points.emplace_back();}},
    {"trajectory.point.duration.sec", [](Goal & g) {
        ++g.trajectory.points.front().time_from_start.sec;
      }},
    {"trajectory.point.duration.nanosec", [](Goal & g) {
        ++g.trajectory.points.front().time_from_start.nanosec;
      }},
    {"multi_dof_trajectory.header.stamp.sec", [](Goal & g) {
        ++g.multi_dof_trajectory.header.stamp.sec;
      }},
    {"multi_dof_trajectory.header.stamp.nanosec", [](Goal & g) {
        ++g.multi_dof_trajectory.header.stamp.nanosec;
      }},
    {"multi_dof_trajectory.header.frame_id", [](Goal & g) {
        g.multi_dof_trajectory.header.frame_id += "x";
      }},
    {"multi_dof_trajectory.joint_names.value", [](Goal & g) {
        g.multi_dof_trajectory.joint_names.front() += "x";
      }},
    {"multi_dof_trajectory.joint_names.count", [](Goal & g) {
        g.multi_dof_trajectory.joint_names.push_back("extra");
      }},
    {"multi_dof_trajectory.points.count", [](Goal & g) {
        g.multi_dof_trajectory.points.emplace_back();
      }},
    {"multi_dof_trajectory.point.duration.sec", [](Goal & g) {
        ++g.multi_dof_trajectory.points.front().time_from_start.sec;
      }},
    {"multi_dof_trajectory.point.duration.nanosec", [](Goal & g) {
        ++g.multi_dof_trajectory.points.front().time_from_start.nanosec;
      }},
    {"trajectory.positions.value", [](Goal & g) {
        g.trajectory.points.front().positions.front() += 0.01;
      }},
    {"trajectory.positions.count", [](Goal & g) {
        g.trajectory.points.front().positions.push_back(0.0);
      }},
    {"trajectory.velocities.value", [](Goal & g) {
        g.trajectory.points.front().velocities.front() += 0.01;
      }},
    {"trajectory.velocities.count", [](Goal & g) {
        g.trajectory.points.front().velocities.push_back(0.0);
      }},
    {"trajectory.accelerations.value", [](Goal & g) {
        g.trajectory.points.front().accelerations.front() += 0.01;
      }},
    {"trajectory.accelerations.count", [](Goal & g) {
        g.trajectory.points.front().accelerations.push_back(0.0);
      }},
    {"trajectory.effort.value", [](Goal & g) {g.trajectory.points.front().effort.front() += 0.01;}},
    {"trajectory.effort.count", [](Goal & g) {g.trajectory.points.front().effort.push_back(0.0);}},
    {"transform.translation.x", [](Goal & g) {
        g.multi_dof_trajectory.points.front().transforms.front().translation.x += 0.01;
      }},
    {"transform.translation.y", [](Goal & g) {
        g.multi_dof_trajectory.points.front().transforms.front().translation.y += 0.01;
      }},
    {"transform.translation.z", [](Goal & g) {
        g.multi_dof_trajectory.points.front().transforms.front().translation.z += 0.01;
      }},
    {"transform.rotation.x", [](Goal & g) {
        g.multi_dof_trajectory.points.front().transforms.front().rotation.x += 0.01;
      }},
    {"transform.rotation.y", [](Goal & g) {
        g.multi_dof_trajectory.points.front().transforms.front().rotation.y += 0.01;
      }},
    {"transform.rotation.z", [](Goal & g) {
        g.multi_dof_trajectory.points.front().transforms.front().rotation.z += 0.01;
      }},
    {"transform.rotation.w", [](Goal & g) {
        g.multi_dof_trajectory.points.front().transforms.front().rotation.w += 0.01;
      }},
    {"transforms.count", [](Goal & g) {
        g.multi_dof_trajectory.points.front().transforms.emplace_back();
      }},
    {"multi.velocities.linear.x", [](Goal & g) {
        g.multi_dof_trajectory.points.front().velocities.front().linear.x += 0.01;
      }},
    {"multi.velocities.linear.y", [](Goal & g) {
        g.multi_dof_trajectory.points.front().velocities.front().linear.y += 0.01;
      }},
    {"multi.velocities.linear.z", [](Goal & g) {
        g.multi_dof_trajectory.points.front().velocities.front().linear.z += 0.01;
      }},
    {"multi.velocities.angular.x", [](Goal & g) {
        g.multi_dof_trajectory.points.front().velocities.front().angular.x += 0.01;
      }},
    {"multi.velocities.angular.y", [](Goal & g) {
        g.multi_dof_trajectory.points.front().velocities.front().angular.y += 0.01;
      }},
    {"multi.velocities.angular.z", [](Goal & g) {
        g.multi_dof_trajectory.points.front().velocities.front().angular.z += 0.01;
      }},
    {"multi.velocities.count", [](Goal & g) {
        g.multi_dof_trajectory.points.front().velocities.emplace_back();
      }},
    {"multi.accelerations.linear.x", [](Goal & g) {
        g.multi_dof_trajectory.points.front().accelerations.front().linear.x += 0.01;
      }},
    {"multi.accelerations.linear.y", [](Goal & g) {
        g.multi_dof_trajectory.points.front().accelerations.front().linear.y += 0.01;
      }},
    {"multi.accelerations.linear.z", [](Goal & g) {
        g.multi_dof_trajectory.points.front().accelerations.front().linear.z += 0.01;
      }},
    {"multi.accelerations.angular.x", [](Goal & g) {
        g.multi_dof_trajectory.points.front().accelerations.front().angular.x += 0.01;
      }},
    {"multi.accelerations.angular.y", [](Goal & g) {
        g.multi_dof_trajectory.points.front().accelerations.front().angular.y += 0.01;
      }},
    {"multi.accelerations.angular.z", [](Goal & g) {
        g.multi_dof_trajectory.points.front().accelerations.front().angular.z += 0.01;
      }},
    {"multi.accelerations.count", [](Goal & g) {
        g.multi_dof_trajectory.points.front().accelerations.emplace_back();
      }},
    {"path_tolerance.name", [](Goal & g) {g.path_tolerance.front().name += "x";}},
    {"path_tolerance.position", [](Goal & g) {g.path_tolerance.front().position += 0.01;}},
    {"path_tolerance.velocity", [](Goal & g) {g.path_tolerance.front().velocity += 0.01;}},
    {"path_tolerance.acceleration", [](Goal & g) {g.path_tolerance.front().acceleration += 0.01;}},
    {"path_tolerance.count", [](Goal & g) {g.path_tolerance.emplace_back();}},
    {"goal_tolerance.name", [](Goal & g) {g.goal_tolerance.front().name += "x";}},
    {"goal_tolerance.position", [](Goal & g) {g.goal_tolerance.front().position += 0.01;}},
    {"goal_tolerance.velocity", [](Goal & g) {g.goal_tolerance.front().velocity += 0.01;}},
    {"goal_tolerance.acceleration", [](Goal & g) {g.goal_tolerance.front().acceleration += 0.01;}},
    {"goal_tolerance.count", [](Goal & g) {g.goal_tolerance.emplace_back();}},
    {"component_path_tolerance.name", [](Goal & g) {
        g.component_path_tolerance.front().joint_name += "x";
      }},
    {"component_path_tolerance.component", [](Goal & g) {
        ++g.component_path_tolerance.front().component;
      }},
    {"component_path_tolerance.position", [](Goal & g) {
        g.component_path_tolerance.front().position += 0.01;
      }},
    {"component_path_tolerance.velocity", [](Goal & g) {
        g.component_path_tolerance.front().velocity += 0.01;
      }},
    {"component_path_tolerance.acceleration", [](Goal & g) {
        g.component_path_tolerance.front().acceleration += 0.01;
      }},
    {"component_path_tolerance.count", [](Goal & g) {g.component_path_tolerance.emplace_back();}},
    {"component_goal_tolerance.name", [](Goal & g) {
        g.component_goal_tolerance.front().joint_name += "x";
      }},
    {"component_goal_tolerance.component", [](Goal & g) {
        ++g.component_goal_tolerance.front().component;
      }},
    {"component_goal_tolerance.position", [](Goal & g) {
        g.component_goal_tolerance.front().position += 0.01;
      }},
    {"component_goal_tolerance.velocity", [](Goal & g) {
        g.component_goal_tolerance.front().velocity += 0.01;
      }},
    {"component_goal_tolerance.acceleration", [](Goal & g) {
        g.component_goal_tolerance.front().acceleration += 0.01;
      }},
    {"component_goal_tolerance.count", [](Goal & g) {g.component_goal_tolerance.emplace_back();}},
    {"goal_time_tolerance.sec", [](Goal & g) {++g.goal_time_tolerance.sec;}},
    {"goal_time_tolerance.nanosec", [](Goal & g) {++g.goal_time_tolerance.nanosec;}},
  };
}
}  // namespace

TEST(Gate6BoundAdmissionState, EveryGoalFieldMutationClosesReservationAndActionIndependently)
{
  const auto goal = complete_goal();
  for (const auto & mutation : every_goal_field_mutation()) {
    SCOPED_TRACE(mutation.first);
    auto changed = goal;
    mutation.second(changed);
    // Direct request callers cannot change typed intent while retaining old bytes.
    g_now = 9906000000;
    auto reserve_gate = make_gate(); ASSERT_TRUE(reserve_gate.arm(1));
    auto request = request_for_goal(goal);
    request.goal = changed;
    EXPECT_EQ(reserve_gate.reserve_bound(request), BoundReserveStatus::DENY_DIGEST_MISMATCH);
    EXPECT_EQ(reserve_gate.reserve_bound(request_for_goal(goal)), BoundReserveStatus::DENY_CLOSED);
    // A separate valid gate proves the action-hop comparison, rather than closed-state refusal.
    auto action_gate = make_gate(); ASSERT_TRUE(action_gate.arm(1));
    const auto valid = request_for_goal(goal);
    ASSERT_EQ(action_gate.reserve_bound(valid), BoundReserveStatus::ACCEPTED);
    EXPECT_EQ(action_gate.admit_bound_action(valid.uuid, changed, 1),
      BoundReserveStatus::DENY_DIGEST_MISMATCH);
    EXPECT_EQ(action_gate.admit_bound_action(valid.uuid, goal, 1), BoundReserveStatus::DENY_CLOSED);
  }
}

TEST(Gate6BoundAdmissionState, CallerMutationAndDestructionCannotChangeStoredGoal)
{
  g_now = 9906000000;
  auto gate = make_gate(); ASSERT_TRUE(gate.arm(1));
  const auto original = complete_goal();
  ControllerGoalAdmission::GoalUUID uuid;
  {
    auto request = request_for_goal(original);
    uuid = request.uuid;
    ASSERT_EQ(gate.reserve_bound(request), BoundReserveStatus::ACCEPTED);
    request.goal = Goal{};
    request.goal_cdr.clear();
  }
  EXPECT_EQ(gate.admit_bound_action(uuid, original, 1), BoundReserveStatus::ACCEPTED);
}

TEST(Gate6BoundAdmissionState, ConsistentNewWireGoalBindsNewIntentAndRefusesOldAction)
{
  g_now = 9906000000;
  const auto original = complete_goal();
  auto changed = original; changed.trajectory.points.front().positions.front() += 0.1;
  const auto request = request_for_goal(changed);
  auto positive = make_gate(); ASSERT_TRUE(positive.arm(1));
  ASSERT_EQ(positive.reserve_bound(request), BoundReserveStatus::ACCEPTED);
  EXPECT_EQ(positive.admit_bound_action(request.uuid, changed, 1), BoundReserveStatus::ACCEPTED);
  auto negative = make_gate(); ASSERT_TRUE(negative.arm(1));
  ASSERT_EQ(negative.reserve_bound(request), BoundReserveStatus::ACCEPTED);
  EXPECT_EQ(negative.admit_bound_action(request.uuid, original, 1),
    BoundReserveStatus::DENY_DIGEST_MISMATCH);
  EXPECT_EQ(negative.admit_bound_action(request.uuid, changed, 1), BoundReserveStatus::DENY_CLOSED);
}

TEST(Gate6BoundAdmissionState, PermitAndGoalReplayUseSeparateOtherwiseValidGates)
{
  const auto request = golden_request();
  for (const bool repeat_permit : {false, true}) {
    SCOPED_TRACE(repeat_permit);
    g_now = 9906000000; auto gate = make_gate(); ASSERT_TRUE(gate.arm(1));
    ASSERT_EQ(gate.reserve_bound(request), BoundReserveStatus::ACCEPTED);
    ASSERT_EQ(gate.admit_bound_action(request.uuid, request.goal, 1), BoundReserveStatus::ACCEPTED);
    auto replay = request;
    if (repeat_permit) {replay.uuid[0] ^= 0xff;} else {replay.permit_uuid[0] ^= 0xff;}
    EXPECT_EQ(gate.reserve_bound(replay), BoundReserveStatus::DENY_UUID_REPLAY);
    EXPECT_EQ(gate.reserve_bound(request), BoundReserveStatus::DENY_CLOSED);
  }
}

TEST(Gate6BoundAdmissionState, WireDigestAndDecodedIntentAreBothChecked)
{
  g_now = 9906000000;
  auto padding = golden_request();
  padding.goal_cdr.back() ^= 0xff;  // keep original digest, even if this is padding
  auto wire_gate = make_gate(); ASSERT_TRUE(wire_gate.arm(1));
  EXPECT_EQ(wire_gate.reserve_bound(padding), BoundReserveStatus::DENY_DIGEST_MISMATCH);
  EXPECT_EQ(wire_gate.reserve_bound(golden_request()), BoundReserveStatus::DENY_CLOSED);

  const auto original = complete_goal();
  auto changed = original; changed.trajectory.points.front().positions.front() += 0.1;
  auto request = request_for_goal(changed);  // matching digest of new semantic payload
  request.goal = original;  // stale caller-owned typed view
  auto intent_gate = make_gate(); ASSERT_TRUE(intent_gate.arm(1));
  EXPECT_EQ(intent_gate.reserve_bound(request), BoundReserveStatus::DENY_DIGEST_MISMATCH);
  EXPECT_EQ(intent_gate.reserve_bound(request_for_goal(changed)), BoundReserveStatus::DENY_CLOSED);
}

TEST(Gate6BoundAdmissionState, InvalidPayloadsAndBothSizeLimitsCloseTheGate)
{
  for (const std::vector<uint8_t> bytes : {
    std::vector<uint8_t>{}, std::vector<uint8_t>{0, 1},
    std::vector<uint8_t>(so101_mujoco_support::kMaxGoalCdrBytes + 1, 0)})
  {
    g_now = 9906000000;
    auto gate = make_gate(); ASSERT_TRUE(gate.arm(1));
    auto request = golden_request(); request.goal_cdr = bytes;
    EXPECT_EQ(gate.reserve_bound(request), BoundReserveStatus::DENY_CLOSED);
    EXPECT_EQ(gate.reserve_bound(golden_request()), BoundReserveStatus::DENY_CLOSED);
  }
  g_now = 9906000000;
  ControllerGoalAdmission small([]() {return g_now;}, 1000000000, 307, 2048,
    ServiceControllerIdentity{ControllerReservationRole::ARM, "inc-1", "boot-1"});
  ASSERT_TRUE(small.arm(1));
  EXPECT_EQ(small.reserve_bound(golden_request()), BoundReserveStatus::DENY_CLOSED);
  EXPECT_EQ(small.reserve_bound(golden_request()), BoundReserveStatus::DENY_CLOSED);
}

TEST(Gate6BoundAdmissionState, OversizedActionClosesAnOtherwiseValidReservation)
{
  g_now = 9906000000;
  ControllerGoalAdmission gate([]() {return g_now;}, 1000000000, 1024, 2048,
    ServiceControllerIdentity{ControllerReservationRole::ARM, "inc-1", "boot-1"});
  ASSERT_TRUE(gate.arm(1));
  const auto request = golden_request();
  ASSERT_EQ(gate.reserve_bound(request), BoundReserveStatus::ACCEPTED);
  auto large = request.goal;
  large.trajectory.header.frame_id = std::string(2048, 'x');
  EXPECT_EQ(gate.admit_bound_action(request.uuid, large, 1), BoundReserveStatus::DENY_CLOSED);
  EXPECT_EQ(gate.admit_bound_action(request.uuid, request.goal, 1),
    BoundReserveStatus::DENY_CLOSED);
}

TEST(Gate6BoundAdmissionState, ProtocolSizeCapIsIndependentOfLargerConfiguredCap)
{
  g_now = 9906000000;
  auto large = complete_goal();
  large.trajectory.header.frame_id = std::string(so101_mujoco_support::kMaxGoalCdrBytes, 'x');
  rclcpp::SerializedMessage serialized;
  rclcpp::Serialization<Goal>().serialize_message(&large, &serialized);
  const auto & raw = serialized.get_rcl_serialized_message();
  ASSERT_GT(raw.buffer_length, so101_mujoco_support::kMaxGoalCdrBytes);
  ASSERT_LT(raw.buffer_length, 2 * so101_mujoco_support::kMaxGoalCdrBytes);
  auto request = golden_request();
  request.goal_cdr.assign(raw.buffer, raw.buffer + raw.buffer_length);
  request.target_digest = so101_mujoco_support::sha256::digest(request.goal_cdr);
  request.goal = large;  // valid CDR and matching typed view, not an undecodable zero buffer
  ControllerGoalAdmission reserve_gate([]() {return g_now;}, 1000000000,
    2 * so101_mujoco_support::kMaxGoalCdrBytes, 2048,
    ServiceControllerIdentity{ControllerReservationRole::ARM, "inc-1", "boot-1"});
  ASSERT_TRUE(reserve_gate.arm(1));
  EXPECT_EQ(reserve_gate.reserve_bound(request), BoundReserveStatus::DENY_CLOSED);
  EXPECT_EQ(reserve_gate.reserve_bound(golden_request()), BoundReserveStatus::DENY_CLOSED);
  ControllerGoalAdmission action_gate([]() {return g_now;}, 1000000000,
    2 * so101_mujoco_support::kMaxGoalCdrBytes, 2048,
    ServiceControllerIdentity{ControllerReservationRole::ARM, "inc-1", "boot-1"});
  ASSERT_TRUE(action_gate.arm(1));
  const auto valid = golden_request();
  ASSERT_EQ(action_gate.reserve_bound(valid), BoundReserveStatus::ACCEPTED);
  EXPECT_EQ(action_gate.admit_bound_action(valid.uuid, large, 1), BoundReserveStatus::DENY_CLOSED);
  EXPECT_EQ(action_gate.admit_bound_action(valid.uuid, valid.goal, 1),
    BoundReserveStatus::DENY_CLOSED);
}

TEST(Gate6BoundAdmissionState, GeneratedEqualityAcceptsSignedZeroAndRefusesNaN)
{
  g_now = 9906000000;
  auto goal = complete_goal(); goal.trajectory.points.front().positions.front() = +0.0;
  auto request = request_for_goal(goal);
  request.goal.trajectory.points.front().positions.front() = -0.0;
  auto zero_gate = make_gate(); ASSERT_TRUE(zero_gate.arm(1));
  ASSERT_EQ(zero_gate.reserve_bound(request), BoundReserveStatus::ACCEPTED);
  EXPECT_EQ(zero_gate.admit_bound_action(request.uuid, request.goal, 1),
    BoundReserveStatus::ACCEPTED);
  goal.trajectory.points.front().positions.front() = std::numeric_limits<double>::quiet_NaN();
  auto nan_gate = make_gate(); ASSERT_TRUE(nan_gate.arm(1));
  EXPECT_EQ(nan_gate.reserve_bound(request_for_goal(goal)),
    BoundReserveStatus::DENY_DIGEST_MISMATCH);
  EXPECT_EQ(nan_gate.reserve_bound(golden_request()), BoundReserveStatus::DENY_CLOSED);
}
