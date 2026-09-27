#include "so101_mujoco_support/controller_reservation_protocol.hpp"

#include <algorithm>
#include <cstring>
#include <stdexcept>

#include "rclcpp/serialization.hpp"
#include "rclcpp/serialized_message.hpp"
#include "rcutils/error_handling.h"

namespace so101_mujoco_support
{
namespace
{
constexpr size_t prefix_size = 4;
constexpr size_t request_header_size = 62;
constexpr uint32_t max_body_size = 1048640;

uint64_t read_u64(const uint8_t * bytes)
{
  uint64_t value = 0;
  for (size_t i = 0; i < 8; ++i) {
    value = (value << 8) | bytes[i];
  }
  return value;
}

bool capability_matches(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability)
{
  uint8_t difference = 0;
  for (size_t i = 0; i < expected_capability.size(); ++i) {
    difference |= frame[10 + i] ^ expected_capability[i];
  }
  return difference == 0;
}

uint64_t parse_generation_control_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability,
  uint8_t operation, const char * invalid)
{
  if (frame.size() != prefix_size + request_header_size ||
    frame[0] != 0 || frame[1] != 0 || frame[2] != 0 || frame[3] != request_header_size ||
    frame[4] != 'S' || frame[5] != 'O' || frame[6] != 'G' || frame[7] != 'R' ||
    frame[8] != 1 || frame[9] != operation ||
    !capability_matches(frame, expected_capability) ||
    std::any_of(frame.begin() + 50, frame.end(), [](uint8_t value) {return value != 0;}))
  {
    throw std::invalid_argument(invalid);
  }
  const auto generation = read_u64(frame.data() + 42);
  if (generation == 0) {throw std::invalid_argument(invalid);}
  return generation;
}
}  // namespace

ControllerReservationRequest parse_controller_reservation_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability)
{
  constexpr auto invalid = "CONTROLLER_RESERVATION_FRAME_INVALID";
  if (frame.size() <= prefix_size + request_header_size) {
    throw std::invalid_argument(invalid);
  }
  const uint32_t body_size =
    (static_cast<uint32_t>(frame[0]) << 24) |
    (static_cast<uint32_t>(frame[1]) << 16) |
    (static_cast<uint32_t>(frame[2]) << 8) |
    static_cast<uint32_t>(frame[3]);
  if (body_size > max_body_size || body_size != frame.size() - prefix_size ||
    frame[4] != 'S' || frame[5] != 'O' || frame[6] != 'G' || frame[7] != 'R' ||
    frame[8] != 1 || frame[9] != 1)
  {
    throw std::invalid_argument(invalid);
  }

  if (!capability_matches(frame, expected_capability)) {
    throw std::invalid_argument(invalid);
  }

  ControllerReservationRequest request{0, {}, ControllerGoalAdmission::Goal()};
  request.generation = read_u64(frame.data() + 42);
  std::copy_n(frame.begin() + 50, request.uuid.size(), request.uuid.begin());
  if (request.generation == 0 ||
    std::all_of(request.uuid.begin(), request.uuid.end(), [](uint8_t value) {return value == 0;}))
  {
    throw std::invalid_argument(invalid);
  }

  try {
    const auto cdr_size = frame.size() - prefix_size - request_header_size;
    rclcpp::SerializedMessage serialized(cdr_size);
    auto & raw = serialized.get_rcl_serialized_message();
    std::memcpy(raw.buffer, frame.data() + prefix_size + request_header_size, cdr_size);
    raw.buffer_length = cdr_size;
    rclcpp::Serialization<ControllerGoalAdmission::Goal>().deserialize_message(
      &serialized, &request.goal);
  } catch (...) {
    rcutils_reset_error();
    throw std::invalid_argument(invalid);
  }
  if (request.goal.trajectory.joint_names.empty() || request.goal.trajectory.points.empty()) {
    throw std::invalid_argument(invalid);
  }
  return request;
}

uint64_t parse_controller_reservation_close_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability)
{
  return parse_generation_control_frame(
    frame, expected_capability, 2, "CONTROLLER_RESERVATION_CLOSE_FRAME_INVALID");
}

uint64_t parse_controller_reservation_arm_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability)
{
  return parse_generation_control_frame(
    frame, expected_capability, 3, "CONTROLLER_RESERVATION_ARM_FRAME_INVALID");
}

uint64_t parse_controller_ingress_query_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability,
  ControllerReservationRole expected_role)
{
  constexpr auto invalid = "CONTROLLER_INGRESS_QUERY_FRAME_INVALID";
  const auto role = static_cast<uint8_t>(expected_role);
  if (role < 1 || role > 3 || frame.size() != prefix_size + request_header_size ||
    frame[0] != 0 || frame[1] != 0 || frame[2] != 0 ||
    frame[3] != request_header_size ||
    frame[4] != 'S' || frame[5] != 'O' || frame[6] != 'G' || frame[7] != 'R' ||
    frame[8] != 1 || frame[9] != 4 ||
    !capability_matches(frame, expected_capability) || frame[50] != role ||
    std::any_of(frame.begin() + 51, frame.end(), [](uint8_t value) {return value != 0;}))
  {
    throw std::invalid_argument(invalid);
  }
  const auto generation = read_u64(frame.data() + 42);
  if (generation == 0) {throw std::invalid_argument(invalid);}
  return generation;
}

std::array<uint8_t, 16> encode_controller_reservation_reply(
  ReservationReplyStatus status, uint64_t generation)
{
  std::array<uint8_t, 16> reply{'S', 'O', 'G', 'A', 1, static_cast<uint8_t>(status)};
  for (size_t i = 0; i < 8; ++i) {
    reply[15 - i] = static_cast<uint8_t>(generation & 0xff);
    generation >>= 8;
  }
  return reply;
}

std::array<uint8_t, 40> encode_controller_ingress_reply(
  ReservationReplyStatus status, ControllerReservationRole role, uint64_t generation,
  uint64_t ingress_sequence, int64_t last_ingress_monotonic_ns,
  int64_t observed_monotonic_ns)
{
  const auto role_code = static_cast<uint8_t>(role);
  if (role_code < 1 || role_code > 3 || generation == 0 ||
    (status == ReservationReplyStatus::ACK &&
    (last_ingress_monotonic_ns < 0 || observed_monotonic_ns <= 0 ||
    last_ingress_monotonic_ns > observed_monotonic_ns)) ||
    (status == ReservationReplyStatus::REJECT &&
    (ingress_sequence != 0 || last_ingress_monotonic_ns != 0 ||
    observed_monotonic_ns != 0)))
  {
    throw std::invalid_argument("CONTROLLER_INGRESS_REPLY_INVALID");
  }
  std::array<uint8_t, 40> reply{'S', 'O', 'G', 'I', 1, static_cast<uint8_t>(status),
    role_code, 0};
  const auto write = [&reply](size_t end, uint64_t value) {
      for (size_t index = 0; index < 8; ++index) {
        reply[end - index] = static_cast<uint8_t>(value & 0xff);
        value >>= 8;
      }
    };
  write(15, generation);
  write(23, ingress_sequence);
  write(31, static_cast<uint64_t>(last_ingress_monotonic_ns));
  write(39, static_cast<uint64_t>(observed_monotonic_ns));
  return reply;
}

}  // namespace so101_mujoco_support
