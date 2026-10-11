// Copyright 2026 SO-101 maintainers

#include "so101_mujoco_support/simulation_evidence_plugin.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <exception>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <rcutils/sha256.h>

#include "evidence_internal.hpp"

namespace so101_mujoco_support
{
PhysicsStepEvidenceBuffer::PhysicsStepEvidenceBuffer(
  std::size_t capacity, std::size_t flush_step_count, double diagnostic_hard_stop_force_n)
: capacity_(capacity),
  flush_step_count_(flush_step_count),
  diagnostic_hard_stop_force_n_(diagnostic_hard_stop_force_n)
{
  if (capacity_ == 0 || flush_step_count_ == 0 || flush_step_count_ > capacity_ ||
    !std::isfinite(diagnostic_hard_stop_force_n_) || diagnostic_hard_stop_force_n_ <= 0.0)
  {
    throw std::invalid_argument("invalid physics-step buffer configuration");
  }
}

bool PhysicsStepEvidenceBuffer::append(const msg::PhysicsStepEvidence & sample)
{
  if (last_observed_.has_value()) {
    const auto & previous = *last_observed_;
    if (sample.simulation_session_id != previous.simulation_session_id ||
      sample.reset_epoch != previous.reset_epoch ||
      sample.physics_step != previous.physics_step + 1 ||
      !std::isfinite(sample.simulation_time_s) ||
      sample.simulation_time_s <= previous.simulation_time_s)
    {
      evidence_loss_ = true;
      return false;
    }
  }
  if (samples_.size() >= capacity_) {
    evidence_loss_ = true;
    return false;
  }
  samples_.push_back(sample);
  last_observed_ = sample;
  if (!hazard_latch_.has_value() &&
    sample.total_normal_force_n >= diagnostic_hard_stop_force_n_)
  {
    msg::PhysicsHazardLatch hazard;
    hazard.simulation_session_id = sample.simulation_session_id;
    hazard.reset_epoch = sample.reset_epoch;
    hazard.physics_step = sample.physics_step;
    hazard.simulation_time_s = sample.simulation_time_s;
    hazard.force_n = sample.total_normal_force_n;
    hazard.threshold_n = diagnostic_hard_stop_force_n_;
    hazard.evidence_loss = evidence_loss_;
    hazard_latch_ = hazard;
  }
  return true;
}

bool PhysicsStepEvidenceBuffer::ready() const
{
  return samples_.size() >= flush_step_count_ || evidence_loss_ || hazard_latch_.has_value();
}

msg::PhysicsStepEvidenceChunk PhysicsStepEvidenceBuffer::prepare_chunk() const
{
  msg::PhysicsStepEvidenceChunk chunk;
  chunk.chunk_sequence = chunk_sequence_;
  chunk.failed_publish_attempts = failed_publish_attempts_;
  chunk.publish_deferrals_total = publish_deferrals_total_;
  chunk.evidence_loss = evidence_loss_;
  if (samples_.empty()) {
    if (last_observed_.has_value()) {
      chunk.simulation_session_id = last_observed_->simulation_session_id;
      chunk.reset_epoch = last_observed_->reset_epoch;
    }
    return chunk;
  }
  chunk.simulation_session_id = samples_.front().simulation_session_id;
  chunk.reset_epoch = samples_.front().reset_epoch;
  chunk.first_physics_step = samples_.front().physics_step;
  chunk.last_physics_step = samples_.back().physics_step;
  chunk.first_simulation_time_s = samples_.front().simulation_time_s;
  chunk.last_simulation_time_s = samples_.back().simulation_time_s;
  chunk.samples.assign(samples_.begin(), samples_.end());
  return chunk;
}

void PhysicsStepEvidenceBuffer::mark_publish_failed()
{
  ++failed_publish_attempts_;
  ++publish_deferrals_total_;
}

void PhysicsStepEvidenceBuffer::mark_published()
{
  samples_.clear();
  ++chunk_sequence_;
  failed_publish_attempts_ = 0;
}

std::optional<msg::PhysicsHazardLatch> PhysicsStepEvidenceBuffer::hazard_latch() const
{
  return hazard_latch_;
}

bool PhysicsStepEvidenceBuffer::evidence_loss_latched() const
{
  return evidence_loss_;
}

void PhysicsStepEvidenceBuffer::reset()
{
  samples_.clear();
  chunk_sequence_ = 0;
  failed_publish_attempts_ = 0;
  publish_deferrals_total_ = 0;
  evidence_loss_ = false;
  last_observed_.reset();
  hazard_latch_.reset();
}
}  // namespace so101_mujoco_support
