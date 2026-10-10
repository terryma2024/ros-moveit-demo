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

enum class StopWrapperReason : uint8_t {
  PASS = 0, INACTIVE_BEFORE = 1, JOINT_SCOPE = 2, ACTIVE_BEFORE = 3,
  INACTIVE_AFTER = 4, ACTIVE_AFTER = 5, WITNESS_REJECT = 6, NOT_EVALUATED = 7, SNAPSHOT_UNAVAILABLE = 8
};
struct StopProofRecord {
  uint64_t evaluation_id{0};
  StopWrapperReason wrapper_reason{StopWrapperReason::NOT_EVALUATED};
  uint8_t witness_rejection{0}, last_reset_reason{0}, flags{0};
  uint16_t sample_count{0};
  int8_t failing_sample_index{-1}, failing_joint_index{-1}, last_reset_joint_index{-1};
  uint32_t cumulative_observation_lock_losses{0};
  uint64_t first_sequence{0}, last_sequence{0};
  int64_t first_sim_time_ns{0}, last_sim_time_ns{0};
  int64_t first_received_ns{0}, last_received_ns{0}, evaluated_ns{0};
  bool allowed() const {return wrapper_reason == StopWrapperReason::PASS;}
};
using GateReason = ControllerGoalAdmission::GateReason;
using ScopedCloseStatus = ControllerGoalAdmission::ScopedCloseStatus;
struct ScopedCloseRequest {
  ControllerReservationCapability capability{};
  uint64_t generation{0};
  ServiceControllerIdentity expected_identity;
};
struct IdentityScopeReply {
  uint8_t status{0};
  uint64_t generation{0}, stored_generation{0};
  ServiceControllerIdentity identity;
};
enum class PrearmStatus : uint8_t {READY = 0, NOT_READY = 1, REJECT_SCOPE = 2};
struct PrearmReply {
  PrearmStatus status{PrearmStatus::REJECT_SCOPE};
  uint64_t generation{0}, stored_generation{0};
  GateReason gate_reason{GateReason::SERVICE_IDENTITY_UNAVAILABLE};
  ServiceControllerIdentity identity;
  StopProofRecord proof;
};
enum class ArmPhase : uint8_t {NONE = 0, STOP_BEFORE = 1, GATE_ARM = 2, STOP_AFTER = 3};
struct DiagnosticArmReply {
  ReservationReplyStatus status{ReservationReplyStatus::REJECT};
  ControllerReservationRole role{ControllerReservationRole::NECK};
  ArmPhase phase{ArmPhase::STOP_BEFORE};
  uint64_t generation{0};
  GateReason gate_reason{GateReason::NONE};
  StopProofRecord proof;
};
uint64_t parse_prearm_query_frame(
  const std::vector<uint8_t> &, const ControllerReservationCapability &);
uint64_t parse_diagnostic_arm_frame(
  const std::vector<uint8_t> &, const ControllerReservationCapability &);
uint64_t parse_bootstrap_identity_frame(
  const std::vector<uint8_t> &, const ControllerReservationCapability &);
ScopedCloseRequest parse_scoped_close_frame(const std::vector<uint8_t> &);
std::array<uint8_t, 80> encode_stop_proof_record(const StopProofRecord &);
StopProofRecord parse_stop_proof_record(const std::vector<uint8_t> &);
std::vector<uint8_t> encode_identity_scope_reply(const IdentityScopeReply &, bool close);
IdentityScopeReply parse_identity_scope_reply(const std::vector<uint8_t> &, bool close);
std::vector<uint8_t> encode_prearm_reply(const PrearmReply &);
PrearmReply parse_prearm_reply(const std::vector<uint8_t> &);
std::array<uint8_t, 104> encode_diagnostic_arm_reply(const DiagnosticArmReply &);
DiagnosticArmReply parse_diagnostic_arm_reply(const std::vector<uint8_t> &);

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

uint64_t parse_controller_primary_fault_close_frame(
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
