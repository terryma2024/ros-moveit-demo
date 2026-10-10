#ifndef SO101_MUJOCO_SUPPORT__CONTROLLER_STOP_WITNESS_HPP_
#define SO101_MUJOCO_SUPPORT__CONTROLLER_STOP_WITNESS_HPP_

#include "so101_mujoco_support/stop_timing_collector.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <limits>
#include <optional>
#include <stdexcept>
#include <utility>

namespace so101_mujoco_support
{

// A controller-local observation window. It cannot arm goal admission.
class ControllerStopWitness final
{
public:
  static constexpr size_t required_samples = 51;
  static constexpr int64_t step_ns = 2000000;
  static constexpr int64_t max_age_ns = 200000000;
  static constexpr double stop_velocity_rad_s = 0.002;

  struct Observation
  {
    uint64_t sequence{0};
    int64_t sim_time_ns{0};
    int64_t received_monotonic_ns{0};
    size_t joint_count{0};
    bool holding{false};
    bool active_goal{false};
    std::array<double, 5> measured_positions{};
    std::array<double, 5> measured_velocities{};
    std::array<double, 5> reference_positions{};
    std::array<double, 5> reference_velocities{};
  };

  struct Proof
  {
    size_t sample_count;
    int64_t first_sim_time_ns;
    int64_t last_sim_time_ns;
    int64_t last_received_monotonic_ns;
    std::array<double, 5> measured_positions;
    std::array<double, 5> measured_velocities;
    std::array<double, 5> reference_positions;
  };

  enum class RejectionReason
  {
    NONE, LOST, INCOMPLETE, NEGATIVE_NOW, NONCONSECUTIVE, FUTURE_SAMPLE,
    STALE_SAMPLE, REFERENCE_CHANGED
  };

  enum class ResetReason
  {
    UNKNOWN, NONE, EXPLICIT_RESET, NONBLOCKING_INVALIDATION, OBSERVATION_LOCK_LOSS,
    ZERO_SEQUENCE, INVALID_SIM_TIME, INVALID_RECEIVED_TIME, JOINT_SCOPE,
    NOT_HOLDING, ACTIVE_GOAL, NONFINITE_MEASURED_POSITION, NONFINITE_MEASURED_VELOCITY,
    NONFINITE_REFERENCE_POSITION, NONFINITE_REFERENCE_VELOCITY,
    MEASURED_VELOCITY, REFERENCE_VELOCITY, SEQUENCE_GAP, SIM_TIME_GAP,
    RECEIVED_TIME_REGRESSION
  };

  // Bounded diagnostic values captured from the same published window as the proof.
  // An empty initial window has UNKNOWN reset provenance, not an inferred cause.
  struct Snapshot
  {
    RejectionReason rejection{RejectionReason::NONE};
    ResetReason last_reset_reason{ResetReason::UNKNOWN};
    int failing_sample_index{-1};
    int failing_joint_index{-1};
    int last_reset_joint_index{-1};
    size_t sample_count{0};
    uint32_t cumulative_observation_lock_losses{0};
    int64_t evaluated_monotonic_ns{0};
    bool lost{false};
    bool has_samples{false};
    Observation first{};
    Observation last{};
    Observation last_reset_sample{};
  };

  struct CheckedProof
  {
    enum class Availability {AVAILABLE, SNAPSHOT_UNAVAILABLE};
    Availability availability{Availability::SNAPSHOT_UNAVAILABLE};
    std::optional<Proof> proof;
    std::optional<Snapshot> snapshot;
  };

  static const char * reason_name(RejectionReason reason)
  {
    switch (reason) {
      case RejectionReason::NONE: return "none";
      case RejectionReason::LOST: return "lost";
      case RejectionReason::INCOMPLETE: return "incomplete";
      case RejectionReason::NEGATIVE_NOW: return "negative_now";
      case RejectionReason::NONCONSECUTIVE: return "nonconsecutive";
      case RejectionReason::FUTURE_SAMPLE: return "future_sample";
      case RejectionReason::STALE_SAMPLE: return "stale_sample";
      case RejectionReason::REFERENCE_CHANGED: return "reference_changed";
    }
    return "unknown";
  }

  static const char * reason_name(ResetReason reason)
  {
    switch (reason) {
      case ResetReason::UNKNOWN: return "unknown";
      case ResetReason::NONE: return "none";
      case ResetReason::EXPLICIT_RESET: return "explicit_reset";
      case ResetReason::NONBLOCKING_INVALIDATION: return "nonblocking_invalidation";
      case ResetReason::OBSERVATION_LOCK_LOSS: return "observation_lock_loss";
      case ResetReason::ZERO_SEQUENCE: return "zero_sequence";
      case ResetReason::INVALID_SIM_TIME: return "invalid_sim_time";
      case ResetReason::INVALID_RECEIVED_TIME: return "invalid_received_time";
      case ResetReason::JOINT_SCOPE: return "joint_scope";
      case ResetReason::NOT_HOLDING: return "not_holding";
      case ResetReason::ACTIVE_GOAL: return "active_goal";
      case ResetReason::NONFINITE_MEASURED_POSITION: return "nonfinite_measured_position";
      case ResetReason::NONFINITE_MEASURED_VELOCITY: return "nonfinite_measured_velocity";
      case ResetReason::NONFINITE_REFERENCE_POSITION: return "nonfinite_reference_position";
      case ResetReason::NONFINITE_REFERENCE_VELOCITY: return "nonfinite_reference_velocity";
      case ResetReason::MEASURED_VELOCITY: return "measured_velocity";
      case ResetReason::REFERENCE_VELOCITY: return "reference_velocity";
      case ResetReason::SEQUENCE_GAP: return "sequence_gap";
      case ResetReason::SIM_TIME_GAP: return "sim_time_gap";
      case ResetReason::RECEIVED_TIME_REGRESSION: return "received_time_regression";
    }
    return "unknown";
  }

  explicit ControllerStopWitness(size_t joint_count)
  : joint_count_(joint_count)
  {
    if (joint_count_ != 1 && joint_count_ != 5) {
      throw std::invalid_argument("CONTROLLER_STOP_JOINT_SCOPE_INVALID");
    }
  }

  void set_timing_collector(StopTimingCollector * collector) noexcept
  {timing_collector_ = collector;}

  void reset()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!invalidate_event(ResetReason::EXPLICIT_RESET, false)) {return;}
    const auto event = invalidation_.load();
    window_.count = 0;
    window_.next = 0;
    window_.handled_invalidation = event;
    record_reset(event_reason(event));
    publish_window();
  }

  void invalidate_nonblocking()
  {
    invalidate_event(ResetReason::NONBLOCKING_INVALIDATION, false);
  }

  void observe(const Observation & sample, uint64_t timing_update_id = 0, int64_t planned_ns = 0)
  {
    if (!mutex_.try_lock()) {
      invalidate_event(ResetReason::OBSERVATION_LOCK_LOSS, true);
      return;
    }
    std::lock_guard<std::mutex> lock(mutex_, std::adopt_lock);
    if (internal_unavailable_.load()) {return;}
    const auto event = invalidation_.load();
    if (event != window_.handled_invalidation) {
      window_.count = 0;
      record_reset(event_reason(event));
      window_.handled_invalidation = event;
    }
    const auto update_id = timing_update_id ? timing_update_id : sample.sequence;
    int invalid_joint = -1;
    const auto invalid = invalid_sample_reason(sample, invalid_joint);
    if (invalid != ResetReason::NONE) {
      window_.count = 0;
      record_reset(invalid, sample, invalid_joint);
      publish_window(update_id, planned_ns, sample);
      return;
    }
    if (window_.count != 0) {
      const auto & previous = window_.samples[(window_.next + window_.samples.size() - 1) %
        window_.samples.size()];
      ResetReason gap = ResetReason::NONE;
      if (sample.sequence != previous.sequence + 1) {
        gap = ResetReason::SEQUENCE_GAP;
      } else if (sample.sim_time_ns - previous.sim_time_ns != step_ns) {
        gap = ResetReason::SIM_TIME_GAP;
      } else if (sample.received_monotonic_ns < previous.received_monotonic_ns) {
        gap = ResetReason::RECEIVED_TIME_REGRESSION;
      }
      if (gap != ResetReason::NONE) {
        window_.count = 0;
        record_reset(gap, sample);
      }
    }
    window_.samples[window_.next] = sample;
    window_.next = (window_.next + 1) % window_.samples.size();
    window_.count = std::min(window_.count + 1, window_.samples.size());
    publish_window(update_id, planned_ns, sample);
  }

  std::optional<Proof> proof() const
  {
    return proof_with_clock([]() {
      return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    });
  }

  // Take time after copying the window, then revalidate at that time.
  template<typename Clock>
  std::optional<Proof> proof_with_clock(Clock && clock) const
  {
    return checked_proof_with_clock(std::forward<Clock>(clock)).proof;
  }

  // Fixed-time evaluation for deterministic observation-window tests.
  std::optional<Proof> proof(int64_t now_monotonic_ns) const
  {
    return checked_proof(now_monotonic_ns).proof;
  }

  CheckedProof checked_proof() const
  {
    const auto clock = []() {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch()).count();
      };
    return checked_proof_with_clock(clock);
  }

  template<typename Clock>
  CheckedProof checked_proof_with_clock(Clock && clock) const
  {
    StopTimingScope timing(timing_collector_, 3);
    timing.availability = 2;
    for (size_t attempt = 0; attempt < 3; ++attempt) {
      WindowState local;
      uint64_t descriptor = 0;
      if (!capture_window(local, descriptor)) {continue;}
      const auto d1 = published_.load();
      const auto i1 = invalidation_.load();
      const auto f1 = internal_unavailable_.load();
      const int64_t now = clock();
      const auto f2 = internal_unavailable_.load();
      const auto i2 = invalidation_.load();
      const auto d2 = published_.load();
      if (d1 == descriptor && d2 == descriptor && i1 == i2 && !f1 && !f2) {
        auto result = evaluate_window(local, i1, now);
        timing.availability = 1;
        if (result.snapshot->has_samples) {
          timing.sequence = result.snapshot->last.sequence;
          timing.sim_time = result.snapshot->last.sim_time_ns;
          timing.period = step_ns;
        }
        return result;
      }
    }
    return CheckedProof{};
  }

  CheckedProof checked_proof(int64_t now_monotonic_ns) const
  {
    return checked_proof_with_clock([now_monotonic_ns]() {return now_monotonic_ns;});
  }

private:
  friend struct ControllerStopWitnessTestAccess;
  struct WindowState
  {
    std::array<Observation, 64> samples{};
    size_t count{0};
    size_t next{0};
    ResetReason last_reset_reason{ResetReason::UNKNOWN};
    Observation last_reset_sample{};
    int last_reset_joint_index{-1};
    uint64_t handled_invalidation{static_cast<uint64_t>(ResetReason::NONE)};
  };

  static ResetReason event_reason(uint64_t event)
  {
    return static_cast<ResetReason>(event & 0xFFu);
  }

  bool invalidate_event(ResetReason reason, bool loss)
  {
    return invalidate_event_on(invalidation_, reason, loss);
  }

  template<typename AtomicEvent>
  bool invalidate_event_on(AtomicEvent & events, ResetReason reason, bool loss)
  {
    auto previous = events.load();
    for (size_t attempt = 0; attempt < 8; ++attempt) {
      const auto epoch = previous >> 32;
      if (epoch >= 0xFFFFFFFEu) {break;}
      auto count = (previous >> 8) & 0xFFFFFFu;
      if (loss && count < 0xFFFFFFu) {++count;}
      const auto next = ((epoch + 1) << 32) | (count << 8) | static_cast<uint64_t>(reason);
      if (events.compare_exchange_strong(previous, next)) {return true;}
    }
    internal_unavailable_.store(true);
    return false;
  }

  bool publish_window()
  {
    return publish_window(0, 0, Observation{});
  }

  bool publish_window(uint64_t update_id, int64_t planned_ns, const Observation & sample)
  {
    StopTimingScope timing(timing_collector_, 2);
    timing.update_id = update_id;
    timing.sequence = sample.sequence;
    timing.planned = planned_ns;
    timing.sim_time = sample.sim_time_ns;
    timing.period = step_ns;
    const auto previous = published_.load();
    const auto version = previous >> 2;
    if (internal_unavailable_.load() || version >= ((uint64_t{1} << 62) - 2)) {
      internal_unavailable_.store(true);
      return false;
    }
    const auto current = previous & 3u;
    for (size_t slot = 0; slot < slots_.size(); ++slot) {
      if (slot != current && !pinned_[slot].load()) {
        slots_[slot] = window_;
        published_.store(((version + 1) << 2) | slot);
        return true;
      }
    }
    internal_unavailable_.store(true);
    return false;
  }

  bool capture_window(WindowState & local, uint64_t & descriptor) const
  {
    std::unique_lock<std::mutex> lock(reader_mutex_, std::try_to_lock);
    if (!lock.owns_lock() || internal_unavailable_.load()) {return false;}
    descriptor = published_.load();
    const auto slot = descriptor & 3u;
    if (slot >= slots_.size()) {return false;}
    // Every operation in the pin handshake is sequentially consistent. A
    // writer only overwrites noncurrent, unpinned slots; versions never repeat.
    pinned_[slot].store(true);
    struct Unpin
    {
      std::atomic<bool> & pin;
      ~Unpin() {pin.store(false);}
    } unpin{pinned_[slot]};
    if (published_.load() != descriptor) {return false;}
    local = slots_[slot];
    return true;
  }

  CheckedProof evaluate_window(
    const WindowState & window, uint64_t event, int64_t now_monotonic_ns) const
  {
    CheckedProof result{};
    result.availability = CheckedProof::Availability::AVAILABLE;
    result.snapshot.emplace();
    auto & snapshot = *result.snapshot;
    snapshot.lost = event != window.handled_invalidation;
    snapshot.sample_count = window.count;
    snapshot.cumulative_observation_lock_losses = static_cast<uint32_t>((event >> 8) & 0xFFFFFFu);
    snapshot.evaluated_monotonic_ns = now_monotonic_ns;
    snapshot.last_reset_reason = snapshot.lost ? event_reason(event) : window.last_reset_reason;
    if (!snapshot.lost) {
      snapshot.last_reset_joint_index = window.last_reset_joint_index;
      snapshot.last_reset_sample = window.last_reset_sample;
    }
    snapshot.has_samples = window.count != 0;
    const auto window_count = std::min(window.count, required_samples);
    const auto first_index = (window.next + window.samples.size() - window_count) % window.samples.size();
    if (snapshot.has_samples) {
      snapshot.first = window.samples[first_index];
      snapshot.last = window.samples[(window.next + window.samples.size() - 1) % window.samples.size()];
    }
    if (snapshot.lost) {
      snapshot.rejection = RejectionReason::LOST;
      return result;
    }
    if (window.count < required_samples) {
      snapshot.rejection = RejectionReason::INCOMPLETE;
      return result;
    }
    if (now_monotonic_ns < 0) {
      snapshot.rejection = RejectionReason::NEGATIVE_NOW;
      return result;
    }
    const auto & first = window.samples[first_index];
    for (size_t index = 0; index < required_samples; ++index) {
      const auto & sample = window.samples[(first_index + index) % window.samples.size()];
      if (sample.sim_time_ns != first.sim_time_ns + static_cast<int64_t>(index) * step_ns ||
        sample.sequence != first.sequence + index)
      {
        snapshot.rejection = RejectionReason::NONCONSECUTIVE;
      } else if (sample.received_monotonic_ns > now_monotonic_ns) {
        snapshot.rejection = RejectionReason::FUTURE_SAMPLE;
      } else if (now_monotonic_ns - sample.received_monotonic_ns > max_age_ns) {
        snapshot.rejection = RejectionReason::STALE_SAMPLE;
      }
      if (snapshot.rejection != RejectionReason::NONE) {
        snapshot.failing_sample_index = static_cast<int>(index);
        return result;
      }
      for (size_t joint = 0; joint < joint_count_; ++joint) {
        if (sample.reference_positions[joint] != first.reference_positions[joint]) {
          snapshot.rejection = RejectionReason::REFERENCE_CHANGED;
          snapshot.failing_sample_index = static_cast<int>(index);
          snapshot.failing_joint_index = static_cast<int>(joint);
          return result;
        }
      }
    }
    const auto & last = window.samples[(window.next + window.samples.size() - 1) % window.samples.size()];
    result.proof = Proof{required_samples, first.sim_time_ns, last.sim_time_ns,
      last.received_monotonic_ns, last.measured_positions, last.measured_velocities,
      last.reference_positions};
    return result;
  }

  ResetReason invalid_sample_reason(const Observation & sample, int & invalid_joint) const
  {
    if (sample.sequence == 0) {return ResetReason::ZERO_SEQUENCE;}
    if (sample.sim_time_ns <= 0) {return ResetReason::INVALID_SIM_TIME;}
    if (sample.received_monotonic_ns <= 0) {return ResetReason::INVALID_RECEIVED_TIME;}
    if (sample.joint_count != joint_count_) {return ResetReason::JOINT_SCOPE;}
    if (!sample.holding) {return ResetReason::NOT_HOLDING;}
    if (sample.active_goal) {return ResetReason::ACTIVE_GOAL;}
    for (size_t joint = 0; joint < joint_count_; ++joint) {
      ResetReason reason = ResetReason::NONE;
      if (!std::isfinite(sample.measured_positions[joint])) {
        reason = ResetReason::NONFINITE_MEASURED_POSITION;
      } else if (!std::isfinite(sample.measured_velocities[joint])) {
        reason = ResetReason::NONFINITE_MEASURED_VELOCITY;
      } else if (!std::isfinite(sample.reference_positions[joint])) {
        reason = ResetReason::NONFINITE_REFERENCE_POSITION;
      } else if (!std::isfinite(sample.reference_velocities[joint])) {
        reason = ResetReason::NONFINITE_REFERENCE_VELOCITY;
      } else if (std::abs(sample.measured_velocities[joint]) > stop_velocity_rad_s) {
        reason = ResetReason::MEASURED_VELOCITY;
      } else if (std::abs(sample.reference_velocities[joint]) > stop_velocity_rad_s) {
        reason = ResetReason::REFERENCE_VELOCITY;
      }
      if (reason != ResetReason::NONE) {
        invalid_joint = static_cast<int>(joint);
        return reason;
      }
    }
    return ResetReason::NONE;
  }

  void record_reset(ResetReason reason)
  {
    record_reset(reason, Observation{});
  }

  void record_reset(ResetReason reason, const Observation & sample, int joint = -1)
  {
    window_.last_reset_reason = reason;
    window_.last_reset_sample = sample;
    window_.last_reset_joint_index = joint;
  }

  StopTimingCollector * timing_collector_{nullptr};
  const size_t joint_count_;
  mutable std::mutex mutex_;
  static_assert(std::atomic<uint64_t>::is_always_lock_free, "STOP_WITNESS_ATOMICS_MUST_BE_LOCK_FREE");
  static_assert(std::atomic<bool>::is_always_lock_free, "STOP_WITNESS_PINS_MUST_BE_LOCK_FREE");
  WindowState window_{};
  std::array<WindowState, 3> slots_{};
  std::atomic<uint64_t> published_{0};
  mutable std::array<std::atomic<bool>, 3> pinned_{{false, false, false}};
  mutable std::mutex reader_mutex_;
  std::atomic<uint64_t> invalidation_{static_cast<uint64_t>(ResetReason::NONE)};
  std::atomic<bool> internal_unavailable_{false};
};

}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__CONTROLLER_STOP_WITNESS_HPP_
