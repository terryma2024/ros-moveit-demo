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
  uint8_t operation, const char * invalid, bool allow_zero = false)
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
  if (generation == 0 && !allow_zero) {throw std::invalid_argument(invalid);}
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

uint64_t parse_controller_primary_fault_close_frame(
  const std::vector<uint8_t> & frame,
  const ControllerReservationCapability & expected_capability)
{
  return parse_generation_control_frame(
    frame, expected_capability, 2, "CONTROLLER_PRIMARY_FAULT_CLOSE_FRAME_INVALID", true);
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
  request.goal_cdr.assign(body + offset, body + offset + goal_length);
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

namespace so101_mujoco_support
{
namespace
{
void require_wire(bool valid)
{
  if (!valid) {throw std::invalid_argument("CONTROLLER_STARTUP_FRAME_INVALID");}
}
void append_integer(std::vector<uint8_t> & out, uint64_t value, size_t bytes)
{
  for (size_t i = bytes; i > 0; --i) {out.push_back(static_cast<uint8_t>(value >> (8 * (i - 1))));}
}
uint64_t take_integer(const std::vector<uint8_t> & in, size_t & offset, size_t bytes)
{
  require_wire(offset + bytes <= in.size());
  uint64_t value = 0;
  for (size_t i = 0; i < bytes; ++i) {value = (value << 8) | in[offset++];}
  return value;
}
int64_t signed_integer(uint64_t value)
{
  int64_t result;
  std::memcpy(&result, &value, sizeof(result));
  return result;
}
void append_identity(std::vector<uint8_t> & out, const ServiceControllerIdentity & identity)
{
  for (const auto * value : {&identity.incarnation, &identity.boot}) {
    require_wire(!value->empty() && value->size() <= 64);
    for (unsigned char c : *value) {require_wire(c >= 0x20 && c <= 0x7e);}
    out.push_back(static_cast<uint8_t>(value->size()));
    out.insert(out.end(), value->begin(), value->end());
  }
}
ServiceControllerIdentity take_identity(
  const std::vector<uint8_t> & in, size_t & offset, uint8_t role)
{
  require_wire(role == 3);
  ServiceControllerIdentity identity{ControllerReservationRole::NECK, "", ""};
  for (auto * value : {&identity.incarnation, &identity.boot}) {
    const size_t size = take_integer(in, offset, 1);
    require_wire(size >= 1 && size <= 64 && offset + size <= in.size());
    value->assign(in.begin() + offset, in.begin() + offset + size);
    offset += size;
    for (unsigned char c : *value) {require_wire(c >= 0x20 && c <= 0x7e);}
  }
  return identity;
}
void validate_record(const StopProofRecord & p)
{
  const auto wrapper = static_cast<uint8_t>(p.wrapper_reason);
  require_wire(wrapper <= 8 && p.witness_rejection <= 7 && p.last_reset_reason <= 19 &&
    (p.flags & ~7u) == 0 && p.sample_count <= 64);
  require_wire(p.failing_sample_index >= -1 && p.failing_sample_index < 51 &&
    p.failing_joint_index >= -1 && p.failing_joint_index < 5 &&
    p.last_reset_joint_index >= -1 && p.last_reset_joint_index < 5);
  const bool snapshot = (p.flags & 1) != 0, samples = (p.flags & 4) != 0;
  if (!snapshot) {
    require_wire(p.flags == 0 && p.witness_rejection == 0 && p.last_reset_reason == 0 &&
      p.sample_count == 0 && p.failing_sample_index == -1 && p.failing_joint_index == -1 &&
      p.last_reset_joint_index == -1 && p.first_sequence == 0 && p.last_sequence == 0 &&
      p.first_sim_time_ns == 0 && p.last_sim_time_ns == 0 && p.first_received_ns == 0 &&
      p.last_received_ns == 0 && p.evaluated_ns == 0);
  }
  require_wire(samples == (p.sample_count != 0));
  if (!samples) {
    require_wire(p.first_sequence == 0 && p.last_sequence == 0 && p.first_sim_time_ns == 0 &&
      p.last_sim_time_ns == 0 && p.first_received_ns == 0 && p.last_received_ns == 0);
  } else {
    require_wire(p.first_sequence != 0 && p.last_sequence != 0 && p.first_sim_time_ns > 0 &&
      p.last_sim_time_ns > 0 && p.first_received_ns > 0 && p.last_received_ns > 0);
  }
  if (wrapper == 7) {
    require_wire(p.evaluation_id == 0 && !snapshot && p.cumulative_observation_lock_losses == 0);
  } else {
    require_wire(p.evaluation_id != 0);
  }
  if (wrapper == 8) {require_wire(!snapshot && p.cumulative_observation_lock_losses == 0);}
  if (wrapper >= 1 && wrapper <= 3) {require_wire(!snapshot);}
  if (wrapper == 6) {require_wire(snapshot && p.witness_rejection != 0);}
  if (wrapper == 0) {
    require_wire(p.flags == 5 && p.witness_rejection == 0 && p.sample_count >= 51 &&
      p.failing_sample_index == -1 && p.failing_joint_index == -1 &&
      p.last_sequence >= p.first_sequence && p.last_sequence - p.first_sequence == 50 &&
      p.last_sim_time_ns >= p.first_sim_time_ns &&
      p.last_sim_time_ns - p.first_sim_time_ns == 100000000 &&
      p.last_received_ns >= p.first_received_ns && p.evaluated_ns >= p.last_received_ns &&
      p.evaluated_ns - p.first_received_ns <= 200000000);
  }
}
void validate_scope(const IdentityScopeReply & p, bool close)
{
  require_wire(p.identity.role == ControllerReservationRole::NECK && p.generation != 0 &&
    p.status <= (close ? 3 : 1));
  if (close && p.status == 0) {require_wire(p.stored_generation == p.generation);}
  if (close && p.status == 1) {require_wire(p.stored_generation == 0);}
  if (close && p.status == 2) {
    require_wire(p.stored_generation != 0 && p.stored_generation != p.generation);
  }
}
void validate_prearm(const PrearmReply & p)
{
  validate_record(p.proof);
  const auto status = static_cast<uint8_t>(p.status);
  const auto reason = static_cast<uint16_t>(p.gate_reason);
  require_wire(p.identity.role == ControllerReservationRole::NECK && p.generation != 0 &&
    status <= 2 && reason <= 6);
  if (status < 2) {
    require_wire(reason == 0 && p.generation > p.stored_generation &&
      p.proof.evaluation_id != 0 &&
      p.proof.wrapper_reason != StopWrapperReason::NOT_EVALUATED);
    require_wire((status == 0) == p.proof.allowed());
  } else {
    require_wire(reason != 0 && p.proof.wrapper_reason == StopWrapperReason::NOT_EVALUATED);
  }
}
void validate_arm(const DiagnosticArmReply & p)
{
  validate_record(p.proof);
  const auto status = static_cast<uint8_t>(p.status), phase = static_cast<uint8_t>(p.phase);
  const auto reason = static_cast<uint16_t>(p.gate_reason);
  require_wire(p.role == ControllerReservationRole::NECK && p.generation != 0 &&
    status <= 1 && phase <= 3 && reason <= 6 && p.proof.evaluation_id != 0);
  if (status == 0) {require_wire(phase == 0 && reason == 0 && p.proof.allowed());}
  else if (phase == 2) {require_wire(reason != 0 && p.proof.allowed());}
  else {require_wire((phase == 1 || phase == 3) && reason == 0 && !p.proof.allowed() &&
    p.proof.wrapper_reason != StopWrapperReason::NOT_EVALUATED);}
}
}
uint64_t parse_prearm_query_frame(
  const std::vector<uint8_t> & frame, const ControllerReservationCapability & cap)
{
  return parse_generation_control_frame(frame, cap, 5, "PREARM_FRAME_INVALID");
}
uint64_t parse_diagnostic_arm_frame(
  const std::vector<uint8_t> & frame, const ControllerReservationCapability & cap)
{
  return parse_generation_control_frame(frame, cap, 6, "DIAGNOSTIC_ARM_FRAME_INVALID");
}
uint64_t parse_bootstrap_identity_frame(
  const std::vector<uint8_t> & frame, const ControllerReservationCapability & cap)
{
  require_wire(frame.size() == 66 && std::memcmp(frame.data() + 4, "SOPQ", 4) == 0);
  auto primary = frame;
  std::copy_n("SOGR", 4, primary.begin() + 4);
  return parse_generation_control_frame(primary, cap, 2, "BOOTSTRAP_FRAME_INVALID");
}
ScopedCloseRequest parse_scoped_close_frame(const std::vector<uint8_t> & frame)
{
  require_wire(frame.size() >= 55 && frame.size() <= 181 &&
    read_u32_be(frame.data()) == frame.size() - 4 &&
    std::memcmp(frame.data() + 4, "SOPC", 4) == 0 && frame[8] == 1 && frame[9] == 1);
  ScopedCloseRequest p;
  std::copy_n(frame.begin() + 10, 32, p.capability.begin());
  p.generation = read_u64(frame.data() + 42);
  require_wire(p.generation != 0);
  size_t offset = 51;
  p.expected_identity = take_identity(frame, offset, frame[50]);
  require_wire(offset == frame.size());
  return p;
}
std::array<uint8_t, 80> encode_stop_proof_record(const StopProofRecord & p)
{
  validate_record(p);
  std::vector<uint8_t> out;
  out.reserve(80);
  append_integer(out, p.evaluation_id, 8);
  out.insert(out.end(), {static_cast<uint8_t>(p.wrapper_reason), p.witness_rejection,
    p.last_reset_reason, p.flags});
  append_integer(out, p.sample_count, 2);
  out.insert(out.end(), {static_cast<uint8_t>(p.failing_sample_index),
    static_cast<uint8_t>(p.failing_joint_index), static_cast<uint8_t>(p.last_reset_joint_index), 0});
  append_integer(out, p.cumulative_observation_lock_losses, 4);
  append_integer(out, 0, 2);
  for (const auto value : {p.first_sequence, p.last_sequence,
    static_cast<uint64_t>(p.first_sim_time_ns), static_cast<uint64_t>(p.last_sim_time_ns),
    static_cast<uint64_t>(p.first_received_ns), static_cast<uint64_t>(p.last_received_ns),
    static_cast<uint64_t>(p.evaluated_ns)}) {append_integer(out, value, 8);}
  std::array<uint8_t, 80> result{};
  std::copy(out.begin(), out.end(), result.begin());
  return result;
}
StopProofRecord parse_stop_proof_record(const std::vector<uint8_t> & in)
{
  require_wire(in.size() == 80);
  size_t n = 0;
  StopProofRecord p;
  p.evaluation_id = take_integer(in, n, 8);
  p.wrapper_reason = static_cast<StopWrapperReason>(take_integer(in, n, 1));
  p.witness_rejection = take_integer(in, n, 1); p.last_reset_reason = take_integer(in, n, 1);
  p.flags = take_integer(in, n, 1); p.sample_count = take_integer(in, n, 2);
  const auto index = [&]() {const auto b = take_integer(in, n, 1);
      return static_cast<int8_t>(b < 128 ? b : static_cast<int>(b) - 256);};
  p.failing_sample_index = index(); p.failing_joint_index = index(); p.last_reset_joint_index = index();
  require_wire(take_integer(in, n, 1) == 0);
  p.cumulative_observation_lock_losses = take_integer(in, n, 4);
  require_wire(take_integer(in, n, 2) == 0);
  p.first_sequence = take_integer(in, n, 8); p.last_sequence = take_integer(in, n, 8);
  p.first_sim_time_ns = signed_integer(take_integer(in, n, 8));
  p.last_sim_time_ns = signed_integer(take_integer(in, n, 8));
  p.first_received_ns = signed_integer(take_integer(in, n, 8));
  p.last_received_ns = signed_integer(take_integer(in, n, 8));
  p.evaluated_ns = signed_integer(take_integer(in, n, 8));
  validate_record(p); return p;
}
std::vector<uint8_t> encode_identity_scope_reply(const IdentityScopeReply & p, bool close)
{
  validate_scope(p, close);
  std::vector<uint8_t> out{'S','O','P',static_cast<uint8_t>(close ? 'D' : 'I'),1,p.status,3,0};
  append_integer(out, p.generation, 8); append_integer(out, p.stored_generation, 8);
  append_identity(out, p.identity);
  return out;
}
IdentityScopeReply parse_identity_scope_reply(const std::vector<uint8_t> & in, bool close)
{
  require_wire(in.size() >= 28 && in.size() <= 154 &&
    std::memcmp(in.data(), close ? "SOPD" : "SOPI", 4) == 0 && in[4] == 1 && in[7] == 0);
  IdentityScopeReply p; p.status = in[5]; size_t n = 8;
  p.generation = take_integer(in, n, 8); p.stored_generation = take_integer(in, n, 8);
  p.identity = take_identity(in, n, in[6]); require_wire(n == in.size());
  validate_scope(p, close); return p;
}
std::vector<uint8_t> encode_prearm_reply(const PrearmReply & p)
{
  validate_prearm(p);
  std::vector<uint8_t> out{'S','O','P','R',1,static_cast<uint8_t>(p.status),3,0};
  append_integer(out, p.generation, 8); append_integer(out, p.stored_generation, 8);
  append_integer(out, static_cast<uint16_t>(p.gate_reason), 2); append_identity(out, p.identity);
  const auto proof = encode_stop_proof_record(p.proof); out.insert(out.end(), proof.begin(), proof.end());
  return out;
}
PrearmReply parse_prearm_reply(const std::vector<uint8_t> & in)
{
  require_wire(in.size() >= 110 && in.size() <= 236 &&
    std::memcmp(in.data(), "SOPR", 4) == 0 && in[4] == 1 && in[7] == 0);
  PrearmReply p; p.status = static_cast<PrearmStatus>(in[5]); size_t n = 8;
  p.generation = take_integer(in, n, 8); p.stored_generation = take_integer(in, n, 8);
  p.gate_reason = static_cast<GateReason>(take_integer(in, n, 2));
  p.identity = take_identity(in, n, in[6]); require_wire(n + 80 == in.size());
  p.proof = parse_stop_proof_record(std::vector<uint8_t>(in.begin() + n, in.end()));
  validate_prearm(p); return p;
}
std::array<uint8_t, 104> encode_diagnostic_arm_reply(const DiagnosticArmReply & p)
{
  validate_arm(p);
  std::vector<uint8_t> out{'S','O','A','R',1,static_cast<uint8_t>(p.status),
    static_cast<uint8_t>(p.role),static_cast<uint8_t>(p.phase)};
  append_integer(out, p.generation, 8); append_integer(out, static_cast<uint16_t>(p.gate_reason), 2);
  out.insert(out.end(), 6, 0);
  const auto proof = encode_stop_proof_record(p.proof); out.insert(out.end(), proof.begin(), proof.end());
  std::array<uint8_t, 104> result{}; std::copy(out.begin(), out.end(), result.begin()); return result;
}
DiagnosticArmReply parse_diagnostic_arm_reply(const std::vector<uint8_t> & in)
{
  require_wire(in.size() == 104 && std::memcmp(in.data(), "SOAR", 4) == 0 && in[4] == 1 &&
    std::all_of(in.begin() + 18, in.begin() + 24, [](uint8_t c) {return c == 0;}));
  DiagnosticArmReply p; p.status = static_cast<ReservationReplyStatus>(in[5]);
  p.role = static_cast<ControllerReservationRole>(in[6]); p.phase = static_cast<ArmPhase>(in[7]);
  size_t n = 8; p.generation = take_integer(in, n, 8);
  p.gate_reason = static_cast<GateReason>(take_integer(in, n, 2));
  p.proof = parse_stop_proof_record(std::vector<uint8_t>(in.begin() + 24, in.end()));
  validate_arm(p); return p;
}
}  // namespace so101_mujoco_support
