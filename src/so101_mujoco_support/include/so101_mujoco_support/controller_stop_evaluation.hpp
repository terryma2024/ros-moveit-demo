#ifndef SO101_MUJOCO_SUPPORT__CONTROLLER_STOP_EVALUATION_HPP_
#define SO101_MUJOCO_SUPPORT__CONTROLLER_STOP_EVALUATION_HPP_

#include "so101_mujoco_support/controller_reservation_protocol.hpp"
#include "so101_mujoco_support/controller_stop_witness.hpp"

namespace so101_mujoco_support
{
struct ControllerStopEvaluation
{
  bool allowed{false};
  StopProofRecord record;
  std::optional<ControllerStopWitness::Proof> proof;
  std::optional<ControllerStopWitness::Snapshot> snapshot;
  ControllerStopEvaluation() = default;
  // Compatibility for legacy boolean-only socket callbacks. These cannot produce
  // an authenticated readiness/diagnostic ACK because no witness record exists.
  ControllerStopEvaluation(bool value) : allowed(value) {}
  explicit operator bool() const {return allowed;}
};

// Wrapper callbacks run outside the witness mutex. The checked snapshot and
// decision are copied once, so subsequent observations cannot rewrite a receipt.
template<typename Active, typename SelectWitness, typename GoalActive>
ControllerStopEvaluation evaluate_controller_stop(
  uint64_t evaluation_id, Active && active, SelectWitness && select, GoalActive && goal_active)
{
  ControllerStopEvaluation result;
  result.record.evaluation_id = evaluation_id;
  const auto reject = [&](StopWrapperReason reason) {
      result.allowed = false;
      result.proof.reset();
      result.record.wrapper_reason = reason;
      return result;
    };
  if (!active()) {return reject(StopWrapperReason::INACTIVE_BEFORE);}
  ControllerStopWitness * witness = select();
  if (!witness) {return reject(StopWrapperReason::JOINT_SCOPE);}
  if (goal_active()) {
    witness->invalidate_nonblocking();
    return reject(StopWrapperReason::ACTIVE_BEFORE);
  }
  const auto checked = witness->checked_proof();
  result.snapshot = checked.snapshot;
  result.proof = checked.proof;
  if (checked.snapshot) {
    const auto & s = *checked.snapshot;
    auto & p = result.record;
    p.witness_rejection = static_cast<uint8_t>(s.rejection);
    p.last_reset_reason = static_cast<uint8_t>(s.last_reset_reason);
    p.flags = 1 | (s.lost ? 2 : 0) | (s.has_samples ? 4 : 0);
    p.sample_count = static_cast<uint16_t>(s.sample_count);
    p.failing_sample_index = static_cast<int8_t>(s.failing_sample_index);
    p.failing_joint_index = static_cast<int8_t>(s.failing_joint_index);
    p.last_reset_joint_index = static_cast<int8_t>(s.last_reset_joint_index);
    p.cumulative_observation_lock_losses = s.cumulative_observation_lock_losses;
    if (s.has_samples) {
      p.first_sequence = s.first.sequence; p.last_sequence = s.last.sequence;
      p.first_sim_time_ns = s.first.sim_time_ns; p.last_sim_time_ns = s.last.sim_time_ns;
      p.first_received_ns = s.first.received_monotonic_ns;
      p.last_received_ns = s.last.received_monotonic_ns;
    }
    p.evaluated_ns = s.evaluated_monotonic_ns;
  }
  if (!active()) {
    witness->invalidate_nonblocking();
    return reject(StopWrapperReason::INACTIVE_AFTER);
  }
  if (goal_active()) {
    witness->invalidate_nonblocking();
    return reject(StopWrapperReason::ACTIVE_AFTER);
  }
  if (checked.availability == ControllerStopWitness::CheckedProof::Availability::SNAPSHOT_UNAVAILABLE) {
    return reject(StopWrapperReason::SNAPSHOT_UNAVAILABLE);
  }
  if (!checked.proof) {return reject(StopWrapperReason::WITNESS_REJECT);}
  result.allowed = true;
  result.record.wrapper_reason = StopWrapperReason::PASS;
  return result;
}
}  // namespace so101_mujoco_support
#endif
