#ifndef SO101_MUJOCO_SUPPORT__CONTROLLER_STOP_WITNESS_HPP_
#define SO101_MUJOCO_SUPPORT__CONTROLLER_STOP_WITNESS_HPP_

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <optional>
#include <stdexcept>

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

  explicit ControllerStopWitness(size_t joint_count)
  : joint_count_(joint_count)
  {
    if (joint_count_ != 1 && joint_count_ != 5) {
      throw std::invalid_argument("CONTROLLER_STOP_JOINT_SCOPE_INVALID");
    }
  }

  void reset()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    lost_.store(false, std::memory_order_release);
    count_ = 0;
    next_ = 0;
  }

  void invalidate_nonblocking()
  {
    lost_.store(true, std::memory_order_release);
  }

  void observe(const Observation & sample)
  {
    if (!mutex_.try_lock()) {
      lost_.store(true, std::memory_order_release);
      return;
    }
    std::lock_guard<std::mutex> lock(mutex_, std::adopt_lock);
    if (lost_.exchange(false, std::memory_order_acq_rel)) {count_ = 0;}
    if (!valid_sample(sample)) {
      count_ = 0;
      return;
    }
    if (count_ != 0) {
      const auto & previous = samples_[(next_ + samples_.size() - 1) % samples_.size()];
      if (sample.sequence != previous.sequence + 1 ||
        sample.sim_time_ns - previous.sim_time_ns != step_ns ||
        sample.received_monotonic_ns < previous.received_monotonic_ns)
      {
        count_ = 0;
      }
    }
    samples_[next_] = sample;
    next_ = (next_ + 1) % samples_.size();
    count_ = std::min(count_ + 1, samples_.size());
  }

  std::optional<Proof> proof(int64_t now_monotonic_ns) const
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (lost_.load(std::memory_order_acquire) || count_ < required_samples ||
      now_monotonic_ns < 0)
    {
      return std::nullopt;
    }
    const auto first_index = (next_ + samples_.size() - required_samples) % samples_.size();
    const auto & first = samples_[first_index];
    for (size_t index = 0; index < required_samples; ++index) {
      const auto & sample = samples_[(first_index + index) % samples_.size()];
      if (sample.sim_time_ns != first.sim_time_ns + static_cast<int64_t>(index) * step_ns ||
        sample.sequence != first.sequence + index ||
        sample.received_monotonic_ns > now_monotonic_ns ||
        now_monotonic_ns - sample.received_monotonic_ns > max_age_ns)
      {
        return std::nullopt;
      }
      for (size_t joint = 0; joint < joint_count_; ++joint) {
        if (sample.reference_positions[joint] != first.reference_positions[joint]) {
          return std::nullopt;
        }
      }
    }
    const auto & last = samples_[(next_ + samples_.size() - 1) % samples_.size()];
    return Proof{required_samples, first.sim_time_ns, last.sim_time_ns,
      last.received_monotonic_ns, last.measured_positions, last.measured_velocities,
      last.reference_positions};
  }

private:
  bool valid_sample(const Observation & sample) const
  {
    if (sample.sequence == 0 || sample.sim_time_ns <= 0 ||
      sample.received_monotonic_ns <= 0 || sample.joint_count != joint_count_ ||
      !sample.holding || sample.active_goal)
    {
      return false;
    }
    for (size_t joint = 0; joint < joint_count_; ++joint) {
      if (!std::isfinite(sample.measured_positions[joint]) ||
        !std::isfinite(sample.measured_velocities[joint]) ||
        !std::isfinite(sample.reference_positions[joint]) ||
        !std::isfinite(sample.reference_velocities[joint]) ||
        std::abs(sample.measured_velocities[joint]) > stop_velocity_rad_s ||
        std::abs(sample.reference_velocities[joint]) > stop_velocity_rad_s)
      {
        return false;
      }
    }
    return true;
  }

  const size_t joint_count_;
  mutable std::mutex mutex_;
  std::atomic<bool> lost_{false};
  std::array<Observation, 64> samples_{};
  size_t next_{0};
  size_t count_{0};
};

}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__CONTROLLER_STOP_WITNESS_HPP_
