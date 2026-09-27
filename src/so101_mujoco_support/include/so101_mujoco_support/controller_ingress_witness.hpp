// Copyright 2026 SO-101 maintainers

#ifndef SO101_MUJOCO_SUPPORT__CONTROLLER_INGRESS_WITNESS_HPP_
#define SO101_MUJOCO_SUPPORT__CONTROLLER_INGRESS_WITNESS_HPP_

#include <time.h>

#include <cstdint>
#include <functional>
#include <limits>
#include <mutex>
#include <optional>
#include <utility>

namespace so101_mujoco_support
{
// The action server records callback entry and completion. A snapshot never
// authorizes a command and refuses to summarize an in-flight callback.
class ControllerIngressWitness final
{
public:
  using Clock = std::function<int64_t()>;

  struct Snapshot
  {
    uint64_t sequence;
    int64_t last_ingress_monotonic_ns;
    int64_t observed_monotonic_ns;
  };

  class Scope final
  {
public:
    explicit Scope(ControllerIngressWitness & witness)
    : witness_(witness)
    {
      witness_.begin_callback();
    }
    ~Scope() {witness_.finish_callback();}
    Scope(const Scope &) = delete;
    Scope & operator=(const Scope &) = delete;

private:
    ControllerIngressWitness & witness_;
  };

  explicit ControllerIngressWitness(Clock clock = monotonic_now_ns)
  : clock_(std::move(clock)) {}

  Scope enter() {return Scope(*this);}

  std::optional<Snapshot> snapshot()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto now = read_clock();
    if (!now || in_flight_ != 0 || fault_) {return std::nullopt;}
    return Snapshot{sequence_, last_ingress_ns_, *now};
  }

private:
  static int64_t monotonic_now_ns()
  {
    timespec time{};
    if (clock_gettime(CLOCK_MONOTONIC, &time) != 0 || time.tv_sec < 0 ||
      time.tv_sec > std::numeric_limits<int64_t>::max() / 1000000000)
    {
      return -1;
    }
    return static_cast<int64_t>(time.tv_sec) * 1000000000 + time.tv_nsec;
  }

  std::optional<int64_t> read_clock()
  {
    int64_t now = -1;
    try {
      if (clock_) {now = clock_();}
    } catch (...) {
      fault_ = true;
      return std::nullopt;
    }
    if (now <= 0 || now < last_clock_ns_) {
      fault_ = true;
      return std::nullopt;
    }
    last_clock_ns_ = now;
    return now;
  }

  void begin_callback()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    read_clock();
    if (sequence_ == std::numeric_limits<uint64_t>::max() ||
      in_flight_ == std::numeric_limits<uint64_t>::max())
    {
      fault_ = true;
    } else {
      ++sequence_;
      ++in_flight_;
    }
  }

  void finish_callback()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto now = read_clock();
    if (in_flight_ == 0) {
      fault_ = true;
      return;
    }
    --in_flight_;
    if (now) {last_ingress_ns_ = *now;}
  }

  std::mutex mutex_;
  Clock clock_;
  uint64_t sequence_{0};
  uint64_t in_flight_{0};
  int64_t last_ingress_ns_{0};
  int64_t last_clock_ns_{0};
  bool fault_{false};
};
}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__CONTROLLER_INGRESS_WITNESS_HPP_
