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

// Phase 3b focused lifecycle tests: shared active gate, bound-mode consumption,
// legacy bypass refusal, fail-closed before provision, detach safety and restart
// identity change. The bound reserve/admit assertions use the real gate API the
// controller callback calls, and the null/detach cases use the real decision helper.

#include <gtest/gtest.h>

#include <cstdint>
#include <fstream>
#include <iterator>
#include <memory>
#include <string>
#include <vector>

#include "so101_mujoco_support/broker_owned_trajectory_controller.hpp"
#include "so101_mujoco_support/controller_goal_admission.hpp"
#include "so101_mujoco_support/controller_reservation_protocol.hpp"

namespace
{
using Admission = so101_mujoco_support::ControllerGoalAdmission;
using Identity = so101_mujoco_support::ServiceControllerIdentity;
using Role = so101_mujoco_support::ControllerReservationRole;
using Capability = so101_mujoco_support::ControllerReservationCapability;

int64_t g_now = 9906000000;

Capability fixture_capability()
{
  Capability value{};
  value.fill(0x5a);
  return value;
}

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

std::shared_ptr<Admission> bound_gate()
{
  return std::make_shared<Admission>([&]() {return g_now;}, 1000000000, 1048576, 2048,
                                     Identity{Role::ARM, "inc-1", "boot-1"});
}

class InspectableController : public so101_mujoco_support::BrokerOwnedTrajectoryController
{
public:
  void close_lifecycle() {close_reservation_service();}   // the real production path
  void install(std::shared_ptr<Admission> gate) {install_active_gate_for_testing(std::move(gate));}
  void clear() {install_active_gate_for_testing(nullptr);}
  rclcpp_action::GoalResponse decide(
    const Admission::GoalUUID & uuid,
    const std::shared_ptr<const control_msgs::action::FollowJointTrajectory::Goal> & goal)
  {
    return decide_goal_admission(uuid, goal);
  }
};
}  // namespace

TEST(Gate6Lifecycle, NullBeforeProvisionRejectsWithoutCallingTheBaseCallback)
{
  InspectableController controller;
  controller.clear();
  auto goal = std::make_shared<control_msgs::action::FollowJointTrajectory::Goal>();
  Admission::GoalUUID uuid{};
  EXPECT_EQ(controller.decide(uuid, goal), rclcpp_action::GoalResponse::REJECT);
}

TEST(Gate6Lifecycle, PointerDetachLeavesTheCopiedGateAliveAndUsable)
{
  InspectableController controller;
  auto gate = bound_gate();
  controller.install(gate);
  ASSERT_TRUE(gate->arm(1));
  const auto frame = golden_frame();
  ASSERT_EQ(so101_mujoco_support::handle_bound_reservation_frame(
      *gate, frame, Role::ARM, fixture_capability()),
    so101_mujoco_support::BoundReserveStatus::ACCEPTED);
  // pointer-detach unit semantics (the real lifecycle path is covered by
  // LifecycleDetachClosesTheGateForAnInflightCopy below)
  controller.clear();
  // the controller no longer exposes a gate, but the object a callback copied is
  // still alive (no use-after-free) and still armed until it is explicitly closed
  EXPECT_TRUE(gate->has_service_identity());
  EXPECT_EQ(gate->generation(), 1u);
  gate->close();                            // closing the detached gate is safe
  EXPECT_EQ(gate->generation(), 0u);
  auto goal = std::make_shared<control_msgs::action::FollowJointTrajectory::Goal>();
  Admission::GoalUUID uuid{};
  EXPECT_EQ(controller.decide(uuid, goal), rclcpp_action::GoalResponse::REJECT);
}

TEST(Gate6Lifecycle, LifecycleDetachClosesTheGateForAnInflightCopy)
{
  g_now = 9906000000;
  InspectableController controller;
  auto gate = bound_gate();
  controller.install(gate);
  ASSERT_TRUE(gate->arm(1));
  // a callback in flight holds its own copy, exactly as active_gate_copy() returns
  auto inflight = gate;
  ASSERT_TRUE(inflight->has_service_identity());
  EXPECT_EQ(inflight->generation(), 1u);

  controller.close_lifecycle();          // real lifecycle detach + close

  // the in-flight copy observes a closed gate: no use-after-free, no authorization
  EXPECT_EQ(inflight->generation(), 0u);
  const auto frame = golden_frame();
  const auto request = so101_mujoco_support::parse_bound_controller_reservation_frame(
    frame, fixture_capability(), Role::ARM);
  EXPECT_NE(inflight->admit_bound_action(request.uuid, request.goal, 1),
            so101_mujoco_support::BoundReserveStatus::ACCEPTED);
  auto goal = std::make_shared<control_msgs::action::FollowJointTrajectory::Goal>();
  Admission::GoalUUID uuid{};
  EXPECT_EQ(controller.decide(uuid, goal), rclcpp_action::GoalResponse::REJECT);
}

TEST(Gate6Lifecycle, BoundReserveThenAdmitConsumesExactlyOnce)
{
  g_now = 9906000000;
  auto gate = bound_gate();
  ASSERT_TRUE(gate->arm(1));
  const auto frame = golden_frame();
  ASSERT_EQ(so101_mujoco_support::handle_bound_reservation_frame(
      *gate, frame, Role::ARM, fixture_capability()),
    so101_mujoco_support::BoundReserveStatus::ACCEPTED);
  const auto request = so101_mujoco_support::parse_bound_controller_reservation_frame(
    frame, fixture_capability(), Role::ARM);
  EXPECT_EQ(gate->admit_bound_action(request.uuid, request.goal, 1),
            so101_mujoco_support::BoundReserveStatus::ACCEPTED);
  // the same uuid+goal cannot be consumed twice
  EXPECT_NE(gate->admit_bound_action(request.uuid, request.goal, 1),
            so101_mujoco_support::BoundReserveStatus::ACCEPTED);
}

TEST(Gate6Lifecycle, AlteredGoalOrUuidIsRejectedAndClosesTheGate)
{
  g_now = 9906000000;
  const auto frame = golden_frame();
  const auto request = so101_mujoco_support::parse_bound_controller_reservation_frame(
    frame, fixture_capability(), Role::ARM);
  {   // altered goal
    auto gate = bound_gate();
    ASSERT_TRUE(gate->arm(1));
    ASSERT_EQ(so101_mujoco_support::handle_bound_reservation_frame(
        *gate, frame, Role::ARM, fixture_capability()),
      so101_mujoco_support::BoundReserveStatus::ACCEPTED);
    auto altered = request.goal;
    altered.trajectory.points[0].positions[0] += 0.01;
    EXPECT_NE(gate->admit_bound_action(request.uuid, altered, 1),
              so101_mujoco_support::BoundReserveStatus::ACCEPTED);
    EXPECT_EQ(gate->admit_bound_action(request.uuid, request.goal, 1),
              so101_mujoco_support::BoundReserveStatus::DENY_CLOSED);
  }
  {   // altered uuid
    auto gate = bound_gate();
    ASSERT_TRUE(gate->arm(1));
    ASSERT_EQ(so101_mujoco_support::handle_bound_reservation_frame(
        *gate, frame, Role::ARM, fixture_capability()),
      so101_mujoco_support::BoundReserveStatus::ACCEPTED);
    auto other = request.uuid;
    other[0] ^= 0xff;
    EXPECT_EQ(gate->admit_bound_action(other, request.goal, 1),
              so101_mujoco_support::BoundReserveStatus::DENY_UUID_REPLAY);
    EXPECT_EQ(gate->admit_bound_action(request.uuid, request.goal, 1),
              so101_mujoco_support::BoundReserveStatus::DENY_CLOSED);
  }
}

TEST(Gate6Lifecycle, LegacyRawReserveCannotAuthorizeOnABoundGate)
{
  g_now = 9906000000;
  auto gate = bound_gate();
  ASSERT_TRUE(gate->arm(1));
  const auto frame = golden_frame();
  const auto request = so101_mujoco_support::parse_bound_controller_reservation_frame(
    frame, fixture_capability(), Role::ARM);
  // a legacy raw reservation on a bound-mode gate authorizes nothing: the bound
  // admit for that uuid is refused and the gate closes
  ASSERT_TRUE(gate->reserve(request.uuid, request.goal, 1));
  EXPECT_NE(gate->admit_bound_action(request.uuid, request.goal, 1),
            so101_mujoco_support::BoundReserveStatus::ACCEPTED);
  EXPECT_EQ(gate->admit_bound_action(request.uuid, request.goal, 1),
            so101_mujoco_support::BoundReserveStatus::DENY_CLOSED);
}

TEST(Gate6Lifecycle, RestartCreatesADifferentServiceIdentity)
{
  const auto first = so101_mujoco_support::generate_service_identity(Role::ARM,
                                                                    fixture_capability());
  const auto second = so101_mujoco_support::generate_service_identity(Role::ARM,
                                                                     fixture_capability());
  EXPECT_NE(first.incarnation, second.incarnation);
  EXPECT_NE(first.boot, second.boot);
  auto restarted = std::make_shared<Admission>([&]() {return g_now;}, 1000000000, 1048576, 2048,
                                               second);
  EXPECT_TRUE(restarted->has_service_identity());
  EXPECT_FALSE(restarted->has_service_identity() && first.incarnation == second.incarnation);
}
