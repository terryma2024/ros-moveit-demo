// Copyright 2026 SO-101 maintainers
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#ifndef SO101_QUEUED_STATE_PUBLISHER__QUEUED_STATE_PUBLISHER_HPP_
#define SO101_QUEUED_STATE_PUBLISHER__QUEUED_STATE_PUBLISHER_HPP_

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <mutex>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "realtime_tools/lock_free_queue.hpp"

namespace so101_queued_state_publisher
{
/// Lossless hand-off of a state message from a realtime update to a dedicated NON-realtime publishing thread.
///
/// `realtime_tools::RealtimePublisher::try_publish()` keeps ONE slot: while the publishing thread has not finished the
/// previous message, the next one is refused and is gone. Under CPU load the publishing thread is late, so the stream
/// silently loses ticks. This class keeps a bounded pool of messages instead.
///
/// Two `realtime_tools::LockFreeSPSCQueue`s of slot indices connect the threads: `free_` (publishing thread -> realtime
/// thread) and `ready_` (realtime thread -> publishing thread). `push()` takes a free slot, assigns the message into it
/// and posts the index; the publishing thread publishes slots in order and returns them. The slots are clones of a
/// prototype whose vectors are already sized, so `push()` neither blocks nor allocates for messages of the prototype's
/// shape. A full pool refuses the message, and that refusal is COUNTED (`overflowed`) and logged at a bounded rate; it is
/// never silent. Messages are published unchanged and in the order they were pushed.
template<typename MsgT>
class QueuedStatePublisher
{
public:
  using Sink = std::function<void (const MsgT &)>;
  enum class Level { kInfo, kWarn };
  using Log = std::function<void (Level, const std::string &)>;

  struct Stats
  {
    uint64_t enqueued{0};      ///< messages accepted into the pool
    uint64_t published{0};     ///< messages handed to the sink
    uint64_t overflowed{0};    ///< messages refused because the pool was full (lost, counted)
    uint64_t sink_errors{0};   ///< messages whose sink call threw (lost, counted)
    /// Enqueues that found the previous message not yet fully published: each one is a message that the single-slot
    /// `RealtimePublisher::try_publish()` would have refused.
    uint64_t would_have_skipped{0};
    std::size_t high_water{0};  ///< largest number of messages waiting at an enqueue
    std::size_t capacity{0};
  };

  static constexpr std::size_t kDefaultCapacity = 2048;

  QueuedStatePublisher(
    const MsgT & prototype, std::size_t capacity, Sink sink, Log log = nullptr,
    std::string name = "state",
    std::chrono::milliseconds stats_period = std::chrono::milliseconds(5000))
  : slots_(capacity > 0 ? capacity : 1, prototype),
    free_(slots_.size()),
    ready_(slots_.size()),
    sink_(std::move(sink)),
    log_(std::move(log)),
    name_(std::move(name)),
    stats_period_(stats_period)
  {
    for (std::size_t i = 0; i < slots_.size(); ++i) {
      (void)free_.push(static_cast<uint32_t>(i));
    }
    thread_ = std::thread(&QueuedStatePublisher::run, this);
  }

  ~QueuedStatePublisher() {stop();}
  QueuedStatePublisher(const QueuedStatePublisher &) = delete;
  QueuedStatePublisher & operator=(const QueuedStatePublisher &) = delete;

  /// Realtime thread only. Never blocks. False (and counted) when the pool is full.
  bool push(const MsgT & msg)
  {
    uint32_t index = 0;
    if (!free_.pop(index)) {
      overflowed_.fetch_add(1, std::memory_order_relaxed);
      return false;
    }
    const uint64_t enqueued_before = enqueued_.load(std::memory_order_relaxed);
    const uint64_t settled = settled_.load(std::memory_order_acquire);
    if (settled < enqueued_before) {
      would_have_skipped_.fetch_add(1, std::memory_order_relaxed);
    }
    const std::size_t waiting = static_cast<std::size_t>(enqueued_before - settled) + 1;
    if (waiting > high_water_.load(std::memory_order_relaxed)) {
      high_water_.store(waiting, std::memory_order_relaxed);
    }
    slots_[index] = msg;
    (void)ready_.push(index);  // same capacity as free_, so a taken slot always fits
    enqueued_.store(enqueued_before + 1, std::memory_order_release);
    if (sleeping_.load(std::memory_order_acquire)) {
      wake_.notify_one();
    }
    return true;
  }

  Stats stats() const
  {
    Stats out;
    out.enqueued = enqueued_.load(std::memory_order_acquire);
    out.published = published_.load(std::memory_order_acquire);
    out.overflowed = overflowed_.load(std::memory_order_acquire);
    out.sink_errors = sink_errors_.load(std::memory_order_acquire);
    out.would_have_skipped = would_have_skipped_.load(std::memory_order_acquire);
    out.high_water = high_water_.load(std::memory_order_acquire);
    out.capacity = slots_.size();
    return out;
  }

  /// Publishes what is still queued, then stops and joins the publishing thread. Idempotent.
  void stop()
  {
    {
      std::lock_guard<std::mutex> lock(wake_mutex_);
      stop_.store(true, std::memory_order_release);
    }
    wake_.notify_all();
    if (thread_.joinable()) {
      thread_.join();
    }
  }

private:
  void log(Level level, const std::string & text) const
  {
    if (log_) {
      try {
        log_(level, text);
      } catch (...) {
        // logging must never take the publishing thread down
      }
    }
  }

  std::string stats_line(double window_seconds, uint64_t window_published) const
  {
    const Stats s = stats();
    return "queued state publisher [" + name_ + "]: " +
           std::to_string(window_seconds > 0.0 ? window_published / window_seconds : 0.0) +
           " msg/s, enqueued(total) " + std::to_string(s.enqueued) +
           ", published(total) " + std::to_string(s.published) +
           ", overflowed(total) " + std::to_string(s.overflowed) +
           ", would_have_skipped_by_try_publish(total) " + std::to_string(s.would_have_skipped) +
           ", sink_errors(total) " + std::to_string(s.sink_errors) +
           ", queue high-water " + std::to_string(s.high_water) + "/" + std::to_string(s.capacity);
  }

  void run()
  {
    auto window_begin = std::chrono::steady_clock::now();
    uint64_t window_published = 0;
    uint64_t window_enqueued_mark = 0;
    uint64_t overflow_logged = 0;
    auto overflow_log_time = window_begin - std::chrono::hours(1);
    for (;; ) {
      uint32_t index = 0;
      bool did_work = false;
      while (ready_.pop(index)) {
        did_work = true;
        try {
          sink_(slots_[index]);
          published_.fetch_add(1, std::memory_order_release);
          ++window_published;
        } catch (...) {
          sink_errors_.fetch_add(1, std::memory_order_release);
        }
        settled_.fetch_add(1, std::memory_order_release);
        (void)free_.push(index);
      }
      if (stop_.load(std::memory_order_acquire)) {
        break;
      }
      const auto now = std::chrono::steady_clock::now();
      const uint64_t overflowed = overflowed_.load(std::memory_order_acquire);
      if (overflowed != overflow_logged && now - overflow_log_time >= std::chrono::seconds(1)) {
        log(
          Level::kWarn, "queued state publisher [" + name_ + "]: queue full, " +
          std::to_string(overflowed - overflow_logged) +
          " message(s) lost since the last warning (overflowed total " +
          std::to_string(overflowed) + ")");
        overflow_logged = overflowed;
        overflow_log_time = now;
      }
      if (now - window_begin >= stats_period_) {
        const double seconds = std::chrono::duration<double>(now - window_begin).count();
        const uint64_t enqueued = enqueued_.load(std::memory_order_acquire);
        if (enqueued != window_enqueued_mark) {
          log(Level::kInfo, stats_line(seconds, window_published));
        }
        window_enqueued_mark = enqueued;
        window_begin = now;
        window_published = 0;
      }
      if (!did_work) {
        sleeping_.store(true, std::memory_order_seq_cst);
        if (ready_.empty() && !stop_.load(std::memory_order_acquire)) {
          std::unique_lock<std::mutex> lock(wake_mutex_);
          // The timeout bounds the delay of a wake-up that raced with the flag above.
          wake_.wait_for(lock, std::chrono::milliseconds(1));
        }
        sleeping_.store(false, std::memory_order_release);
      }
    }
  }

  std::vector<MsgT> slots_;
  realtime_tools::LockFreeSPSCQueue<uint32_t> free_;
  realtime_tools::LockFreeSPSCQueue<uint32_t> ready_;
  Sink sink_;
  Log log_;
  std::string name_;
  std::chrono::milliseconds stats_period_;
  std::atomic<uint64_t> enqueued_{0};
  std::atomic<uint64_t> published_{0};
  std::atomic<uint64_t> settled_{0};  // published + sink errors: messages the publishing thread is done with
  std::atomic<uint64_t> overflowed_{0};
  std::atomic<uint64_t> sink_errors_{0};
  std::atomic<uint64_t> would_have_skipped_{0};
  std::atomic<std::size_t> high_water_{0};
  std::atomic<bool> stop_{false};
  std::atomic<bool> sleeping_{false};
  std::mutex wake_mutex_;
  std::condition_variable wake_;
  std::thread thread_;
};
}  // namespace so101_queued_state_publisher
#endif  // SO101_QUEUED_STATE_PUBLISHER__QUEUED_STATE_PUBLISHER_HPP_
