#ifndef SO101_STOP_WITNESS_TEST_ACCESS_HPP_
#define SO101_STOP_WITNESS_TEST_ACCESS_HPP_
#include "so101_mujoco_support/controller_stop_witness.hpp"
namespace so101_mujoco_support
{
struct ControllerStopWitnessTestAccess
{
  static void writer_lock(ControllerStopWitness & w) {w.mutex_.lock();}
  static void writer_unlock(ControllerStopWitness & w) {w.mutex_.unlock();}
  static void reader_lock(ControllerStopWitness & w) {w.reader_mutex_.lock();}
  static void reader_unlock(ControllerStopWitness & w) {w.reader_mutex_.unlock();}
  static uint64_t pin(ControllerStopWitness & w)
  {
    w.reader_mutex_.lock();
    const auto descriptor = w.published_.load();
    w.pinned_[descriptor & 3u].store(true);
    return descriptor;
  }
  static void unpin(ControllerStopWitness & w, uint64_t descriptor)
  {
    w.pinned_[descriptor & 3u].store(false);
    w.reader_mutex_.unlock();
  }
  static uint64_t pinned_last_sequence(ControllerStopWitness & w, uint64_t descriptor)
  {
    const auto & slot = w.slots_[descriptor & 3u];
    return slot.samples[(slot.next + slot.samples.size() - 1) % slot.samples.size()].sequence;
  }
  static void publish_after_unhandled_invalidation(ControllerStopWitness & w)
  {
    std::lock_guard<std::mutex> lock(w.mutex_);
    const auto loaded = w.invalidation_.load();
    w.invalidate_nonblocking();
    w.window_.handled_invalidation = loaded;
    w.publish_window();
  }
  static void set_event(ControllerStopWitness & w, uint32_t epoch, uint32_t count)
  {
    w.invalidation_.store((uint64_t{epoch} << 32) | (uint64_t{count} << 8) |
      static_cast<uint64_t>(ControllerStopWitness::ResetReason::OBSERVATION_LOCK_LOSS));
  }
  static uint64_t event(ControllerStopWitness & w) {return w.invalidation_.load();}
  static void set_version(ControllerStopWitness & w, uint64_t version)
  {
    w.published_.store((version << 2) | (w.published_.load() & 3u));
  }
  static bool exhaust_cas(ControllerStopWitness & w, size_t & calls)
  {
    struct RejectEveryCas
    {
      size_t & calls;
      uint64_t load() {return 1;}
      bool compare_exchange_strong(uint64_t & expected, uint64_t)
      {
        expected += uint64_t{1} << 32;
        ++calls;
        return false;
      }
    } events{calls};
    return w.invalidate_event_on(events,
      ControllerStopWitness::ResetReason::NONBLOCKING_INVALIDATION, false);
  }
};
}
#endif
