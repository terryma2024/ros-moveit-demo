// Copyright 2026 SO-101 maintainers

#ifndef SO101_MUJOCO_SUPPORT__PHYSICS_STEP_FENCE_HPP_
#define SO101_MUJOCO_SUPPORT__PHYSICS_STEP_FENCE_HPP_

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <mutex>
#include <optional>
#include <string>
#include <utility>

#include "so101_mujoco_support/msg/physics_step_fence_ack.hpp"
#include "so101_mujoco_support/msg/physics_step_fence_request.hpp"
#include "so101_mujoco_support/msg/physics_step_evidence.hpp"

namespace so101_mujoco_support
{
// A read-only marker. A subscriber callback can queue a request, but only an
// advancing physics callback can produce the acknowledgement.
class PhysicsStepFence
{
public:
  explicit PhysicsStepFence(std::string session_id)
  : session_id_(std::move(session_id)) {}

  void configure_session(std::string session_id)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    session_id_ = std::move(session_id);
    epoch_ = 0;
    last_sequence_ = 0;
    last_clock_interval_end_ns_ = 0;
    pending_.reset();
  }

  void reset(uint64_t epoch)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    epoch_ = epoch;
    last_sequence_ = 0;
    last_clock_interval_end_ns_ = 0;
    pending_.reset();
  }

  bool request(const msg::PhysicsStepFenceRequest & value)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (session_id_.empty() || epoch_ == 0 ||
      value.simulation_session_id != session_id_ || value.reset_epoch != epoch_ ||
      value.request_sequence == 0 || value.request_sequence <= last_sequence_ || pending_)
    {
      return false;
    }
    pending_ = value;
    last_sequence_ = value.request_sequence;
    return true;
  }

  std::optional<msg::PhysicsStepFenceAck> observe(
    const msg::PhysicsStepEvidence & sample, bool paused,
    int64_t clock_begin_ns, int64_t clock_end_ns)
  {
    std::unique_lock<std::mutex> lock(mutex_, std::try_to_lock);
    if (!lock.owns_lock() || !pending_ || paused ||
      sample.simulation_session_id != session_id_ || sample.reset_epoch != epoch_ ||
      sample.physics_step == 0 || !std::isfinite(sample.simulation_time_s) ||
      sample.simulation_time_s < 0.0 || sample.truncated ||
      sample.diagnostic_hazard_breached || sample.model_qpos.empty() ||
      sample.model_qvel.empty() ||
      !std::all_of(sample.model_qpos.begin(), sample.model_qpos.end(),
      [](double value) {return std::isfinite(value);}) ||
      !std::all_of(sample.model_qvel.begin(), sample.model_qvel.end(),
      [](double value) {return std::isfinite(value);}) || clock_begin_ns <= 0 ||
      clock_begin_ns < last_clock_interval_end_ns_ || clock_end_ns < clock_begin_ns)
    {
      return std::nullopt;
    }
    msg::PhysicsStepFenceAck ack;
    ack.simulation_session_id = session_id_;
    ack.reset_epoch = epoch_;
    ack.request_sequence = pending_->request_sequence;
    ack.marked_physics_step = sample.physics_step;
    ack.marked_simulation_time_s = sample.simulation_time_s;
    ack.marked_sample = sample;
    ack.clock_interval_begin_monotonic_ns = clock_begin_ns;
    ack.clock_interval_end_monotonic_ns = clock_end_ns;
    last_clock_interval_end_ns_ = clock_end_ns;
    pending_.reset();
    return ack;
  }

private:
  std::mutex mutex_;
  std::string session_id_;
  uint64_t epoch_{0};
  uint64_t last_sequence_{0};
  int64_t last_clock_interval_end_ns_{0};
  std::optional<msg::PhysicsStepFenceRequest> pending_;
};
}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__PHYSICS_STEP_FENCE_HPP_
