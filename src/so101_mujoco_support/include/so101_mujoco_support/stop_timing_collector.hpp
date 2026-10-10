#ifndef SO101_STOP_TIMING_COLLECTOR_HPP_
#define SO101_STOP_TIMING_COLLECTOR_HPP_

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <fcntl.h>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <time.h>
#include <unistd.h>

namespace so101_mujoco_support
{
inline int64_t stop_timing_now_ns() noexcept
{
  timespec value{};
  if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) {return -1;}
  return static_cast<int64_t>(value.tv_sec) * 1000000000 + value.tv_nsec;
}

struct StopTimingRecord
{
  uint64_t kind, proof_availability, controller_id, update_id, sample_sequence;
  int64_t planned_ns, sim_time_ns, period_ns, start_ns, end_ns;
  uint64_t ready;
};
static_assert(sizeof(StopTimingRecord) == 88, "STOP_TIMING_RECORD_SIZE");

class StopTimingCollector final
{
public:
  static constexpr size_t capacity = 131072;
  ~StopTimingCollector()
  {
    stop_drain();
    if (fd_ >= 0) {
      if (fsync(fd_) != 0) {io_failed_.store(true);}
      close(fd_);
      // Only the non-RT owner writes the final integrity receipt.
      std::ofstream out(output_path_ + ".status.json");
      out << "{\"records_reserved\":" << next_.load() << ",\"records_written\":" << drained_
          << ",\"overflow\":" << (overflow() ? "true" : "false")
          << ",\"io_failed\":" << (io_failed() ? "true" : "false") << "}\n";
    }
  }
  void configure(const std::string & output_path, uint32_t controller_id)
  {
    if (fd_ >= 0) {throw std::logic_error("STOP_TIMING_ALREADY_CONFIGURED");}
    auto records = std::make_unique<AtomicTimingRecord[]>(capacity);
    const int fd = open(output_path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0) {throw std::runtime_error("STOP_TIMING_OUTPUT_REFUSED");}
    records_ = std::move(records);
    fd_ = fd;
    output_path_ = output_path;
    controller_id_ = controller_id;
    if (!write_all("SOTM0001", 8)) {throw std::runtime_error("STOP_TIMING_HEADER_FAILED");}
  }
  void start_drain()
  {
    if (fd_ < 0 || thread_.joinable()) {throw std::logic_error("STOP_TIMING_DRAIN_INVALID");}
    stop_.store(false);
    thread_ = std::thread([this]() {
        while (!stop_.load()) {
          drain_ready();
          std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
        drain_ready();
      });
  }
  // The caller quiesces every producer before this final drain.
  void stop_drain()
  {
    stop_.store(true);
    if (thread_.joinable()) {thread_.join();}
    if (fd_ >= 0) {drain_ready();}
  }
  void record(uint8_t kind, uint8_t availability, uint64_t update_id, uint64_t sequence,
    int64_t planned, int64_t sim_time, int64_t period, int64_t start, int64_t end) noexcept
  {
    if (overflow_.load(std::memory_order_relaxed)) {return;}
    const auto index = next_.fetch_add(1, std::memory_order_relaxed);
    if (index >= capacity) {overflow_.store(true); return;}
    auto & row = records_[index];
    row.kind.store(kind, std::memory_order_relaxed);
    row.availability.store(availability, std::memory_order_relaxed);
    row.controller_id.store(controller_id_, std::memory_order_relaxed);
    row.update_id.store(update_id, std::memory_order_relaxed);
    row.sequence.store(sequence, std::memory_order_relaxed);
    row.planned.store(planned, std::memory_order_relaxed);
    row.sim_time.store(sim_time, std::memory_order_relaxed);
    row.period.store(period, std::memory_order_relaxed);
    row.start.store(start, std::memory_order_relaxed);
    row.end.store(end, std::memory_order_relaxed);
    row.ready.store(1, std::memory_order_release);
  }
  bool overflow() const {return overflow_.load();}
  bool io_failed() const {return io_failed_.load();}

private:
  static_assert(std::atomic<uint64_t>::is_always_lock_free, "TIMING_ATOMICS_MUST_BE_LOCK_FREE");
  static_assert(std::atomic<int64_t>::is_always_lock_free, "TIMING_CLOCK_ATOMICS_MUST_BE_LOCK_FREE");
  struct AtomicTimingRecord
  {
    std::atomic<uint64_t> kind{0}, availability{0}, controller_id{0}, update_id{0}, sequence{0};
    std::atomic<int64_t> planned{0}, sim_time{0}, period{0}, start{0}, end{0};
    std::atomic<uint64_t> ready{0};
  };
  bool write_all(const void * payload, size_t size) noexcept
  {
    const auto * bytes = static_cast<const char *>(payload);
    while (size != 0) {
      const auto written = write(fd_, bytes, size);
      if (written < 0 && errno == EINTR) {continue;}
      if (written <= 0) {io_failed_.store(true); return false;}
      bytes += written;
      size -= static_cast<size_t>(written);
    }
    return true;
  }
  void drain_ready() noexcept
  {
    const auto limit = std::min<uint64_t>(next_.load(), capacity);
    while (drained_ < limit) {
      const auto & row = records_[drained_];
      if (row.ready.load(std::memory_order_acquire) != 1) {break;}
      const StopTimingRecord plain{
        row.kind.load(std::memory_order_relaxed), row.availability.load(std::memory_order_relaxed),
        row.controller_id.load(std::memory_order_relaxed), row.update_id.load(std::memory_order_relaxed),
        row.sequence.load(std::memory_order_relaxed), row.planned.load(std::memory_order_relaxed),
        row.sim_time.load(std::memory_order_relaxed), row.period.load(std::memory_order_relaxed),
        row.start.load(std::memory_order_relaxed), row.end.load(std::memory_order_relaxed), 1};
      if (!write_all(&plain, sizeof(plain))) {return;}
      ++drained_;
    }
  }
  std::unique_ptr<AtomicTimingRecord[]> records_;
  std::atomic<uint64_t> next_{0};
  std::atomic<bool> overflow_{false}, io_failed_{false}, stop_{false};
  uint64_t drained_{0};
  uint32_t controller_id_{0};
  int fd_{-1};
  std::string output_path_;
  std::thread thread_;
};

// Stack lifetime spans every return path; record() performs only bounded atomic writes.
struct StopTimingScope
{
  StopTimingCollector * collector;
  uint8_t kind, availability{0};
  uint64_t update_id{0}, sequence{0};
  int64_t planned{0}, sim_time{0}, period{0}, started;
  StopTimingScope(StopTimingCollector * value, uint8_t record_kind) noexcept
  : collector(value), kind(record_kind), started(value ? stop_timing_now_ns() : 0) {}
  ~StopTimingScope()
  {
    if (collector) {
      collector->record(kind, availability, update_id, sequence, planned, sim_time, period,
        started, stop_timing_now_ns());
    }
  }
};
}  // namespace so101_mujoco_support
#endif
