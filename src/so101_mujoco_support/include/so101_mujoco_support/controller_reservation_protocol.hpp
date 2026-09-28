#ifndef SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_PROTOCOL_HPP_
#define SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_PROTOCOL_HPP_

#include <array>
#include <cstdint>
#include <string>
#include <vector>

#include "so101_mujoco_support/bound_reservation.hpp"
#include "so101_mujoco_support/controller_goal_admission.hpp"
#include "so101_mujoco_support/controller_reservation_role.hpp"

namespace so101_mujoco_support
{

using ControllerReservationCapability = std::array<uint8_t, 32>;

struct ControllerReservationRequest
{
  uint64_t generation;
  ControllerGoalAdmission::GoalUUID uuid;
  ControllerGoalAdmission::Goal goal;
};

enum class ReservationReplyStatus : uint8_t {ACK = 0, REJECT = 1};

// Frozen v2 bound reservation schema (see the protocol audit). The binding block is
// explicit and separate from the goal bytes: a legacy reserve can never treat a
// bound frame as a bare goal. The request type itself lives next to the admission
// primitive to avoid an include cycle.
bool is_bound_reservation_frame(const std::vector<uint8_t> & frame);

// Parse outside the gate lock, then reserve inside it: the socket path never holds
// the gate mutex across CDR deserialization.
BoundReserveStatus handle_bound_reservation_frame(
  ControllerGoalAdmission & gate, const std::vector<uint8_t> & frame,
  ControllerReservationRole expected_role,
  const ControllerReservationCapability & expected_capability);

BoundControllerReservationRequest parse_bound_controller_reservation_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability,
  ControllerReservationRole expected_role);

ControllerReservationRequest parse_controller_reservation_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability);

uint64_t parse_controller_reservation_close_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability);

uint64_t parse_controller_reservation_arm_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability);

uint64_t parse_controller_ingress_query_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability,
  ControllerReservationRole expected_role);

std::array<uint8_t, 16> encode_controller_reservation_reply(
  ReservationReplyStatus status, uint64_t generation);

std::array<uint8_t, 40> encode_controller_ingress_reply(
  ReservationReplyStatus status, ControllerReservationRole role, uint64_t generation,
  uint64_t ingress_sequence, int64_t last_ingress_monotonic_ns,
  int64_t observed_monotonic_ns);

}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_PROTOCOL_HPP_
