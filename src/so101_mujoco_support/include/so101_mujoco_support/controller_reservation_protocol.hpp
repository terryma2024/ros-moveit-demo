#ifndef SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_PROTOCOL_HPP_
#define SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_PROTOCOL_HPP_

#include <array>
#include <cstdint>
#include <vector>

#include "so101_mujoco_support/controller_goal_admission.hpp"

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

ControllerReservationRequest parse_controller_reservation_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability);

uint64_t parse_controller_reservation_close_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability);

uint64_t parse_controller_reservation_arm_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability);

std::array<uint8_t, 16> encode_controller_reservation_reply(
  ReservationReplyStatus status, uint64_t generation);

}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_PROTOCOL_HPP_
