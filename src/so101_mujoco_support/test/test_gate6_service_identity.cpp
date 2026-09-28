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

// Phase 3b.2 RED: service-owned per-role identity and its bounded binary ACK.
//
// Planned API (frozen corrections 4/7/8):
//   ServiceControllerIdentity generate_service_identity(
//     ControllerReservationRole role, const ControllerReservationCapability & capability);
//   std::array<uint8_t, ...> encode_identity_reply(role, generation, incarnation, boot);
//   bool parse_identity_reply(const std::vector<uint8_t> & reply,
//     ControllerReservationRole expected_role, ServiceControllerIdentity * out);
// The symbols do not exist yet: that missing-symbol diagnostic is the RED.

#include <gtest/gtest.h>

#include <array>
#include <cstdint>
#include <string>
#include <vector>

#include "so101_mujoco_support/controller_reservation_protocol.hpp"

namespace
{

using so101_mujoco_support::ControllerReservationCapability;
using so101_mujoco_support::ControllerReservationRole;
using so101_mujoco_support::ServiceControllerIdentity;
using so101_mujoco_support::encode_identity_reply;
using so101_mujoco_support::generate_service_identity;
using so101_mujoco_support::parse_identity_reply;

ControllerReservationCapability capability()
{
  ControllerReservationCapability value{};
  value.fill(0x5a);
  return value;
}

}  // namespace

TEST(Gate6ServiceIdentity, EveryRoleGetsItsOwnNonemptyPrintableBoundedIdentity)
{
  std::array<ServiceControllerIdentity, 3> identities{
    generate_service_identity(ControllerReservationRole::ARM, capability()),
    generate_service_identity(ControllerReservationRole::GRIPPER, capability()),
    generate_service_identity(ControllerReservationRole::NECK, capability())};
  for (const auto & identity : identities) {
    EXPECT_FALSE(identity.incarnation.empty());
    EXPECT_FALSE(identity.boot.empty());
    EXPECT_LE(identity.incarnation.size(), 64u);
    EXPECT_LE(identity.boot.size(), 64u);
    for (const char character : identity.incarnation + identity.boot) {
      const auto code = static_cast<unsigned char>(character);
      EXPECT_GE(code, 0x20);
      EXPECT_LE(code, 0x7e);
    }
  }
  // role-scoped: no two roles share an identity
  EXPECT_NE(identities[0].incarnation, identities[1].incarnation);
  EXPECT_NE(identities[1].incarnation, identities[2].incarnation);
  EXPECT_NE(identities[0].boot, identities[2].boot);
}

TEST(Gate6ServiceIdentity, IdentityReplyRoundTripsAndIsBounded)
{
  const auto identity = generate_service_identity(ControllerReservationRole::ARM, capability());
  const auto reply = encode_identity_reply(ControllerReservationRole::ARM, 7,
                                           identity.incarnation, identity.boot);
  EXPECT_LE(reply.size(), 160u);
  ServiceControllerIdentity parsed{};
  ASSERT_TRUE(parse_identity_reply(reply, ControllerReservationRole::ARM, &parsed));
  EXPECT_EQ(parsed.incarnation, identity.incarnation);
  EXPECT_EQ(parsed.boot, identity.boot);
  // malformed replies are refused
  ServiceControllerIdentity other{};
  auto truncated = reply;
  truncated.resize(truncated.size() - 1);
  EXPECT_FALSE(parse_identity_reply(truncated, ControllerReservationRole::ARM, &other));
  auto wrong_role = reply;
  EXPECT_FALSE(parse_identity_reply(wrong_role, ControllerReservationRole::GRIPPER, &other));
  auto oversized = reply;
  oversized.insert(oversized.end(), {0x00});
  EXPECT_FALSE(parse_identity_reply(oversized, ControllerReservationRole::ARM, &other));
}
