#include <gtest/gtest.h>
#include <array>
#include <atomic>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <future>
#include <thread>
#include <unistd.h>
#include <vector>
#include "controller_stop_witness_test_access.hpp"
#include "so101_mujoco_support/stop_timing_collector.hpp"
using namespace so101_mujoco_support;
namespace
{
int64_t now_ns()
{
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
}
ControllerStopWitness::Observation sample(uint64_t sequence)
{
  ControllerStopWitness::Observation value;
  value.sequence = sequence;
  value.sim_time_ns = sequence * 2000000;
  value.received_monotonic_ns = now_ns();
  value.joint_count = 5;
  value.holding = true;
  value.measured_positions = {1, 2, 3, 4, 5};
  value.reference_positions = value.measured_positions;
  return value;
}
std::filesystem::path timing_path(const std::string & name)
{
  const auto root = std::filesystem::temp_directory_path() /
    ("stop-timing-" + std::to_string(getpid()) + "-" + name);
  if (!std::filesystem::create_directory(root)) {throw std::runtime_error("TIMING_OUTPUT_EXISTS");}
  return root / "records.bin";
}
std::vector<StopTimingRecord> read_records(const std::filesystem::path & path)
{
  std::ifstream input(path, std::ios::binary);
  char magic[8];
  input.read(magic, 8);
  EXPECT_EQ(std::string(magic, 8), "SOTM0001");
  std::vector<StopTimingRecord> records;
  StopTimingRecord row;
  while (input.read(reinterpret_cast<char *>(&row), sizeof(row))) {records.push_back(row);}
  EXPECT_TRUE(input.eof());
  return records;
}
}
TEST(ControllerStopWitnessStress, TimingIncludesEveryPublicationAndCompletedProof)
{
  const auto path = timing_path("complete");
  StopTimingCollector collector;
  collector.configure(path.string(), 3);
  collector.start_drain();
  ControllerStopWitness witness(5);
  witness.set_timing_collector(&collector);
  for (uint64_t seq = 1; seq <= 51; ++seq) {witness.observe(sample(seq));}
  ASSERT_TRUE(witness.proof());
  ControllerStopWitnessTestAccess::reader_lock(witness);
  auto busy = std::async(std::launch::async, [&]() {return witness.checked_proof();});
  EXPECT_FALSE(busy.get().snapshot);
  ControllerStopWitnessTestAccess::reader_unlock(witness);
  collector.stop_drain();
  EXPECT_FALSE(collector.overflow());
  EXPECT_FALSE(collector.io_failed());
  const auto rows = read_records(path);
  ASSERT_EQ(rows.size(), 53u);
  for (size_t i = 0; i < 51; ++i) {
    EXPECT_EQ(rows[i].kind, 2u);
    EXPECT_EQ(rows[i].sample_sequence, i + 1);
    EXPECT_EQ(rows[i].controller_id, 3u);
    EXPECT_EQ(rows[i].proof_availability, 0u);
    EXPECT_GE(rows[i].end_ns, rows[i].start_ns);
    EXPECT_EQ(rows[i].ready, 1u);
  }
  EXPECT_EQ(rows[51].kind, 3u);
  EXPECT_EQ(rows[51].proof_availability, 1u);
  EXPECT_EQ(rows[52].kind, 3u);
  EXPECT_EQ(rows[52].proof_availability, 2u);
}
TEST(ControllerStopWitnessStress, CollectorOverflowIsStickyAndNeverReusesSlots)
{
  const auto path = timing_path("overflow");
  StopTimingCollector collector;
  collector.configure(path.string(), 1);
  collector.start_drain();
  for (size_t i = 0; i <= StopTimingCollector::capacity; ++i) {
    collector.record(2, 0, i, i, i, i, 2000000, i, i + 1);
  }
  collector.stop_drain();
  EXPECT_TRUE(collector.overflow());
  const auto rows = read_records(path);
  ASSERT_EQ(rows.size(), StopTimingCollector::capacity);
  for (size_t i = 0; i < rows.size(); ++i) {EXPECT_EQ(rows[i].sample_sequence, i);}
}
TEST(ControllerStopWitnessStress, FourReadersDoNotLoseWriterSamplesOrMixPayloads)
{
  ControllerStopWitness witness(5);
  std::atomic<bool> running{true}, bad{false};
  std::array<std::thread, 4> readers;
  for (auto & reader : readers) {
    reader = std::thread([&]() {
        while (running.load()) {
          const auto checked = witness.checked_proof();
          if (checked.snapshot && checked.snapshot->cumulative_observation_lock_losses != 0) {bad.store(true);}
          if (checked.proof && (checked.proof->sample_count != 51 ||
            checked.proof->reference_positions != std::array<double, 5>{1, 2, 3, 4, 5}))
          {bad.store(true);}
          if (checked.availability == ControllerStopWitness::CheckedProof::Availability::SNAPSHOT_UNAVAILABLE &&
            (checked.snapshot || checked.proof)) {bad.store(true);}
        }
      });
  }
  for (uint64_t seq = 1; seq <= 10000; ++seq) {witness.observe(sample(seq));}
  running.store(false);
  for (auto & reader : readers) {reader.join();}
  EXPECT_FALSE(bad.load());
  const auto checked = witness.checked_proof();
  ASSERT_TRUE(checked.proof);
  EXPECT_EQ(checked.snapshot->last.sequence, 10000u);
  EXPECT_EQ(checked.snapshot->cumulative_observation_lock_losses, 0u);
}
TEST(ControllerStopWitnessStress, PinBusyRetryAndPausedAgeAreDistinct)
{
  ControllerStopWitness witness(5);
  for (uint64_t seq = 1; seq <= 51; ++seq) {witness.observe(sample(seq));}
  const auto descriptor = ControllerStopWitnessTestAccess::pin(witness);
  for (uint64_t seq = 52; seq <= 61; ++seq) {
    witness.observe(sample(seq));
    EXPECT_EQ(ControllerStopWitnessTestAccess::pinned_last_sequence(witness, descriptor), 51u);
  }
  auto busy = std::async(std::launch::async, [&]() {return witness.checked_proof();});
  EXPECT_FALSE(busy.get().snapshot);
  std::this_thread::sleep_for(std::chrono::milliseconds(5));
  ControllerStopWitnessTestAccess::unpin(witness, descriptor);
  uint64_t seq = 61;
  int calls = 0;
  const auto unavailable = witness.checked_proof_with_clock([&]() {
      ++calls; witness.observe(sample(++seq)); return now_ns();
    });
  EXPECT_EQ(calls, 3);
  EXPECT_FALSE(unavailable.snapshot);
  EXPECT_TRUE(witness.proof());
  std::this_thread::sleep_for(std::chrono::milliseconds(201));
  const auto stale = witness.checked_proof();
  ASSERT_TRUE(stale.snapshot);
  EXPECT_EQ(stale.snapshot->rejection, ControllerStopWitness::RejectionReason::STALE_SAMPLE);
  EXPECT_EQ(stale.snapshot->cumulative_observation_lock_losses, 0u);
}
