#include "so101_mujoco_support/controller_reservation_protocol.hpp"

#include <algorithm>
#include <cstring>
#include <random>
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
namespace so101_mujoco_support
{

// ---------------------------------------------------------------------------
// Frozen v2 bound reservation frame (see the Batch 3 protocol audit).
// Structure parsing and CDR deserialization happen here, outside any gate mutex,
// producing an immutable value; semantic validation happens in the admission.
// ---------------------------------------------------------------------------
namespace
{
uint32_t read_u32_be(const uint8_t * bytes)
{
  return (static_cast<uint32_t>(bytes[0]) << 24) | (static_cast<uint32_t>(bytes[1]) << 16) |
         (static_cast<uint32_t>(bytes[2]) << 8) | static_cast<uint32_t>(bytes[3]);
}

constexpr size_t bound_prefix_size = 6;      // "SOGB" + version + operation
constexpr size_t bound_capability_size = 32;
constexpr size_t bound_fixed_size = 8 + 16 + 1 + 16 + 32 + 8 + 8;

bool all_zero(const uint8_t * bytes, size_t size)
{
  for (size_t index = 0; index < size; ++index) {
    if (bytes[index] != 0) {
      return false;
    }
  }
  return true;
}

std::string read_bounded_string(const uint8_t * body, size_t body_size, size_t & offset)
{
  if (offset + 1 > body_size) {throw std::invalid_argument("BOUND_STRING_TRUNCATED");}
  const size_t length = body[offset++];
  if (length == 0 || length > so101_mujoco_support::kMaxIncarnationBytes ||
    offset + length > body_size)
  {
    throw std::invalid_argument("BOUND_STRING_INVALID");
  }
  std::string value(reinterpret_cast<const char *>(body + offset), length);   // no whole-body copy
  offset += length;
  for (const char character : value) {
    const auto code = static_cast<unsigned char>(character);
    if (code < 0x20 || code > 0x7e) {throw std::invalid_argument("BOUND_STRING_NOT_ASCII");}
  }
  return value;
}
}  // namespace

BoundControllerReservationRequest parse_bound_controller_reservation_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability,
  ControllerReservationRole expected_role)
{
  if (frame.size() < prefix_size + bound_prefix_size + bound_capability_size) {
    throw std::invalid_argument("BOUND_FRAME_TRUNCATED");
  }
  const uint32_t declared = read_u32_be(frame.data());
  if (declared != frame.size() - prefix_size || declared > kMaxBoundBodyBytes) {
    throw std::invalid_argument("BOUND_FRAME_LENGTH_INVALID");
  }
  const uint8_t * body = frame.data() + prefix_size;
  const size_t body_size = declared;
  if (std::memcmp(body, "SOGB", 4) != 0) {throw std::invalid_argument("BOUND_FRAME_MAGIC");}
  if (body[4] != kBoundProtocolVersion) {throw std::invalid_argument("BOUND_FRAME_VERSION");}
  if (body[5] != kBoundReservationOperation) {throw std::invalid_argument("BOUND_FRAME_OPERATION");}
  if (std::memcmp(body + bound_prefix_size, expected_capability.data(),
                  bound_capability_size) != 0)
  {
    throw std::invalid_argument("BOUND_FRAME_CAPABILITY");
  }
  size_t offset = bound_prefix_size + bound_capability_size;
  if (offset + bound_fixed_size > body_size) {
    throw std::invalid_argument("BOUND_FRAME_TRUNCATED");
  }
  BoundControllerReservationRequest request;   // NSDMIs initialise every field
  request.generation = read_u64(body + offset);
  if (request.generation == 0) {throw std::invalid_argument("BOUND_FRAME_GENERATION_INVALID");}
  offset += 8;
  std::memcpy(request.uuid.data(), body + offset, 16);
  if (all_zero(request.uuid.data(), 16)) {
    throw std::invalid_argument("BOUND_FRAME_GOAL_UUID_INVALID");
  }
  offset += 16;
  const uint8_t role_byte = body[offset++];
  if (role_byte != static_cast<uint8_t>(expected_role)) {
    throw std::invalid_argument("BOUND_FRAME_ROLE_MISMATCH");
  }
  request.role = expected_role;
  std::memcpy(request.permit_uuid.data(), body + offset, 16);
  if (all_zero(request.permit_uuid.data(), 16) || (request.permit_uuid[6] >> 4) != 4 ||
    (request.permit_uuid[8] & 0xc0) != 0x80)
  {
    throw std::invalid_argument("BOUND_FRAME_PERMIT_UUID_INVALID");   // RFC 4122 v4 + variant
  }
  offset += 16;
  std::memcpy(request.target_digest.data(), body + offset, 32);
  if (all_zero(request.target_digest.data(), 32)) {
    throw std::invalid_argument("BOUND_FRAME_DIGEST_INVALID");
  }
  offset += 32;
  request.claim_monotonic_ns = static_cast<int64_t>(read_u64(body + offset));
  offset += 8;
  request.deadline_ns = static_cast<int64_t>(read_u64(body + offset));
  offset += 8;
  if (request.claim_monotonic_ns <= 0 || request.deadline_ns <= 0 ||
    request.claim_monotonic_ns > request.deadline_ns)
  {
    throw std::invalid_argument("BOUND_FRAME_TIME_INVALID");
  }
  request.session_id = read_bounded_string(body, body_size, offset);
  request.broker_incarnation = read_bounded_string(body, body_size, offset);
  request.controller_incarnation = read_bounded_string(body, body_size, offset);
  request.controller_boot_incarnation = read_bounded_string(body, body_size, offset);
  if (offset + 4 > body_size) {throw std::invalid_argument("BOUND_FRAME_GOAL_LENGTH_MISSING");}
  const uint32_t goal_length = read_u32_be(body + offset);
  offset += 4;
  if (goal_length == 0 || goal_length > kMaxGoalCdrBytes || offset + goal_length != body_size) {
    throw std::invalid_argument("BOUND_FRAME_GOAL_LENGTH_INVALID");
  }
  rclcpp::SerializedMessage serialized(goal_length);
  auto & raw = serialized.get_rcl_serialized_message();
  std::memcpy(raw.buffer, body + offset, goal_length);
  raw.buffer_length = goal_length;
  try {
    rclcpp::Serialization<ControllerGoalAdmission::Goal> serializer;
    serializer.deserialize_message(&serialized, &request.goal);
  } catch (const std::exception & error) {
    throw std::invalid_argument(std::string("BOUND_FRAME_GOAL_CDR_INVALID:") + error.what());
  }
  return request;
}

}  // namespace so101_mujoco_support

namespace so101_mujoco_support
{
namespace
{
constexpr uint8_t identity_magic[4] = {'S', 'O', 'I', 'D'};
constexpr uint8_t bound_magic[4] = {'S', 'O', 'G', 'B'};

uint8_t role_number(ControllerReservationRole role) {return static_cast<uint8_t>(role);}

std::string hex_token(size_t bytes)
{
  // OS-backed entropy; if the source cannot be read the caller must fail closed.
  std::random_device source("/dev/urandom");
  static const char * digits = "0123456789abcdef";
  std::string out;
  out.reserve(bytes * 2);
  for (size_t index = 0; index < bytes; ++index) {
    const uint32_t value = source();
    out.push_back(digits[(value >> 4) & 0xf]);
    out.push_back(digits[value & 0xf]);
  }
  if (out.size() != bytes * 2) {throw std::runtime_error("SERVICE_IDENTITY_ENTROPY_FAILED");}
  return out;
}
}  // namespace

ServiceControllerIdentity generate_service_identity(
  ControllerReservationRole role, const std::array<uint8_t, 32> & capability)
{
  if (capability.size() != 32 || std::all_of(capability.begin(), capability.end(),
    [](uint8_t value) {return value == 0;}))
  {
    throw std::invalid_argument("SERVICE_IDENTITY_CAPABILITY_INVALID");
  }
  ServiceControllerIdentity identity{};
  identity.role = role;
  identity.incarnation = "inc-" + hex_token(16);
  identity.boot = "boot-" + hex_token(16);
  if (identity.incarnation.size() > kMaxIncarnationBytes ||
    identity.boot.size() > kMaxIncarnationBytes)
  {
    throw std::runtime_error("SERVICE_IDENTITY_TOO_LONG");
  }
  return identity;
}

std::vector<uint8_t> encode_identity_reply(
  ControllerReservationRole role, uint64_t generation, const std::string & incarnation,
  const std::string & boot)
{
  const auto bounded = [](const std::string & value) {
      if (value.empty() || value.size() > kMaxIncarnationBytes) {
        throw std::invalid_argument("SERVICE_IDENTITY_STRING_INVALID");
      }
      for (const char character : value) {
        const auto code = static_cast<unsigned char>(character);
        if (code < 0x20 || code > 0x7e) {
          throw std::invalid_argument("SERVICE_IDENTITY_STRING_INVALID");
        }
      }
      return value;
    };
  std::vector<uint8_t> body{identity_magic[0], identity_magic[1], identity_magic[2],
    identity_magic[3], kIdentityProtocolVersion,
    kIdentityQueryOperation, role_number(role)};
  for (int shift = 56; shift >= 0; shift -= 8) {
    body.push_back(static_cast<uint8_t>((generation >> shift) & 0xff));
  }
  for (const std::string & value : {bounded(incarnation), bounded(boot)}) {
    body.push_back(static_cast<uint8_t>(value.size()));
    body.insert(body.end(), value.begin(), value.end());
  }
  if (body.size() > kMaxIdentityReplyBytes) {
    throw std::invalid_argument("SERVICE_IDENTITY_REPLY_TOO_LARGE");
  }
  // Body only: the transport frames it with its own 4-byte length prefix, exactly as
  // the Python client reads it back.
  return body;
}

bool parse_identity_reply(
  const std::vector<uint8_t> & reply,
  ControllerReservationRole expected_role, ServiceControllerIdentity * out)
{
  if (out == nullptr || reply.size() < 15 || std::memcmp(reply.data(), identity_magic, 4) != 0 ||
    reply[4] != kIdentityProtocolVersion || reply[5] != kIdentityQueryOperation ||
    reply[6] != role_number(expected_role))
  {
    return false;
  }
  size_t offset = 15;
  std::string values[2];
  for (int index = 0; index < 2; ++index) {
    if (offset + 1 > reply.size()) {return false;}
    const size_t length = reply[offset++];
    if (length == 0 || length > kMaxIncarnationBytes || offset + length > reply.size()) {
      return false;
    }
    values[index].assign(reply.begin() + static_cast<long>(offset),
                         reply.begin() + static_cast<long>(offset + length));
    offset += length;
    for (const char character : values[index]) {
      const auto code = static_cast<unsigned char>(character);
      if (code < 0x20 || code > 0x7e) {return false;}
    }
  }
  if (offset != reply.size()) {return false;}
  out->role = expected_role;
  out->incarnation = values[0];
  out->boot = values[1];
  return true;
}

bool is_bound_reservation_frame(const std::vector<uint8_t> & frame)
{
  return frame.size() >= prefix_size + bound_prefix_size &&
         std::memcmp(frame.data() + prefix_size, bound_magic, 4) == 0 &&
         frame[prefix_size + 4] == kBoundProtocolVersion;
}

BoundReserveStatus handle_bound_reservation_frame(
  ControllerGoalAdmission & gate, const std::vector<uint8_t> & frame,
  ControllerReservationRole expected_role,
  const ControllerReservationCapability & expected_capability)
{
  // the real socket capability is used; there is no fixed fill in production
  BoundControllerReservationRequest request =
    parse_bound_controller_reservation_frame(frame, expected_capability, expected_role);
  return gate.reserve_bound(request);
}
}  // namespace so101_mujoco_support
