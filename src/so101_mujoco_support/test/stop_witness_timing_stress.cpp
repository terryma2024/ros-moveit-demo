#include "so101_mujoco_support/controller_stop_witness.hpp"
#include <atomic>
#include <cerrno>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
using namespace so101_mujoco_support;
namespace
{
void wait_tick(int64_t deadline)
{
  const timespec target{deadline / 1000000000, deadline % 1000000000};
  int rc;
  do {rc = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &target, nullptr);} while (rc == EINTR);
  if (rc != 0) {throw std::runtime_error("ABSOLUTE_TICK_FAILED");}
}
void copy_maps(const std::filesystem::path & output)
{
  std::ifstream input("/proc/self/maps");
  std::ofstream result(output);
  result << input.rdbuf();
}
}
int main(int argc, char ** argv)
{
  try {
    std::map<std::string, std::string> arguments;
    for (int i = 1; i < argc; i += 2) {
      if (i + 1 >= argc || !arguments.emplace(argv[i], argv[i + 1]).second) {
        throw std::invalid_argument("TIMING_ARGUMENTS");
      }
    }
    const auto mode = arguments.at("--mode");
    const auto run_id = arguments.at("--run-id");
    const auto scope = std::stoul(arguments.at("--scope"));
    const auto seconds = std::stoul(arguments.at("--duration-s"));
    if (arguments.size() != 5 || scope != 5 ||
      (mode != "single" && mode != "four" && mode != "aligned" && mode != "tsan") ||
      seconds != (mode == "tsan" ? 10u : 120u))
    {throw std::invalid_argument("FROZEN_WORKLOAD_MISMATCH");}
    const std::filesystem::path output = arguments.at("--output");
    if (!std::filesystem::create_directory(output)) {throw std::runtime_error("TIMING_OUTPUT_EXISTS");}
    copy_maps(output / "maps.txt");
    std::atomic<bool> stop{false}, bad{false};
    std::atomic<uint64_t> unavailable{0}, available{0}, loss_max{0}, ready{0};
    std::atomic<int64_t> writer_jitter_max{0};
    const int64_t started = stop_timing_now_ns() + 50000000;
    const int64_t ticks = static_cast<int64_t>(seconds) * 500;
    {
      StopTimingCollector collector;
      collector.configure((output / "records.bin").string(), 1);
      collector.start_drain();
      ControllerStopWitness witness(5);
      witness.set_timing_collector(&collector);
      const size_t readers = mode == "four" || mode == "tsan" ? 4 : 1;
      std::vector<std::thread> threads;
      for (size_t reader = 0; reader < readers; ++reader) {
        threads.emplace_back([&, reader]() {
          int64_t scheduled = started + (mode == "four" ?
            static_cast<int64_t>(reader) * 31250000 : 0);
          int64_t index = 0;
          while (!stop.load()) {
            if (mode == "aligned" && index >= ticks) {break;}
            wait_tick(scheduled);
            if (stop.load()) {break;}
            const auto checked = witness.checked_proof();
            if (checked.availability == ControllerStopWitness::CheckedProof::Availability::SNAPSHOT_UNAVAILABLE) {
              unavailable.fetch_add(1);
              if (checked.snapshot || checked.proof) {bad.store(true);}
            } else {
              available.fetch_add(1);
              if (!checked.snapshot) {bad.store(true); continue;}
              const auto & s = *checked.snapshot;
              auto old = loss_max.load();
              while (old < s.cumulative_observation_lock_losses &&
                !loss_max.compare_exchange_weak(old, s.cumulative_observation_lock_losses)) {}
              if (checked.proof) {
                ready.fetch_add(1);
                if (checked.proof->sample_count != 51 || s.last.sequence - s.first.sequence != 50 ||
                  checked.proof->last_sim_time_ns - checked.proof->first_sim_time_ns != 100000000 ||
                  checked.proof->reference_positions != std::array<double, 5>{1, 2, 3, 4, 5} ||
                  s.rejection != ControllerStopWitness::RejectionReason::NONE)
                {bad.store(true);}
              }
            }
            ++index;
            scheduled = mode == "aligned" ? started + index * 2000000 :
              stop_timing_now_ns() + (mode == "tsan" ? 2000000 : 125000000);
          }
        });
      }
      for (int64_t tick = 0; tick < ticks; ++tick) {
        const int64_t planned = started + tick * 2000000;
        wait_tick(planned);
        const auto actual = stop_timing_now_ns();
        auto previous = writer_jitter_max.load();
        while (previous < actual - planned &&
          !writer_jitter_max.compare_exchange_weak(previous, actual - planned)) {}
        ControllerStopWitness::Observation sample;
        sample.sequence = tick + 1;
        sample.sim_time_ns = (tick + 1) * 2000000;
        sample.received_monotonic_ns = actual;
        sample.joint_count = 5;
        sample.holding = true;
        sample.measured_positions = {1, 2, 3, 4, 5};
        sample.reference_positions = sample.measured_positions;
        witness.observe(sample, sample.sequence, planned);
      }
      wait_tick(started + static_cast<int64_t>(seconds) * 1000000000);
      stop.store(true);
      for (auto & thread : threads) {thread.join();}
      const auto last = witness.checked_proof();
      if (!last.snapshot || last.snapshot->last.sequence != static_cast<uint64_t>(ticks) ||
        last.snapshot->cumulative_observation_lock_losses != 0) {bad.store(true);}
      collector.stop_drain();
      if (collector.overflow() || collector.io_failed()) {bad.store(true);}
    }
    uint64_t publications = 0, proof_calls = 0, publish_overruns = 0, proof_overruns = 0;
    int64_t publish_max = 0, proof_max = 0;
    std::ifstream file(output / "records.bin", std::ios::binary);
    char magic[8];
    file.read(magic, 8);
    if (std::string(magic, 8) != "SOTM0001") {bad.store(true);}
    StopTimingRecord row{};
    while (file.read(reinterpret_cast<char *>(&row), sizeof(row))) {
      const auto duration = row.end_ns - row.start_ns;
      if (row.ready != 1 || row.start_ns <= 0 || duration < 0) {bad.store(true);}
      if (row.kind == 2) {
        ++publications;
        publish_max = std::max(publish_max, duration);
        if (duration >= 2000000) {++publish_overruns;}
        if (row.period_ns != 2000000 || row.sim_time_ns !=
          static_cast<int64_t>(row.sample_sequence) * 2000000 ||
          row.sample_sequence != publications)
        {bad.store(true);}
      } else if (row.kind == 3) {
        ++proof_calls;
        proof_max = std::max(proof_max, duration);
        if (duration >= 2000000) {++proof_overruns;}
        if (row.proof_availability != 1 && row.proof_availability != 2) {bad.store(true);}
      } else {bad.store(true);}
    }
    if (!file.eof() || publications != static_cast<uint64_t>(ticks)) {bad.store(true);}
    const bool qualified = !bad.load() && loss_max.load() == 0 &&
      (mode == "tsan" || (publish_overruns == 0 &&
        (mode != "single" || (proof_overruns == 0 && unavailable.load() == 0))));
    std::ofstream summary(output / "summary.json");
    summary << "{\"mode\":\"" << mode << "\",\"run_id\":\"" << run_id
            << "\",\"qualified\":" << (qualified ? "true" : "false")
            << ",\"safety_bad\":" << (bad.load() ? "true" : "false")
            << ",\"publication_count\":" << publications << ",\"proof_count\":" << proof_calls
            << ",\"available\":" << available.load() << ",\"unavailable\":" << unavailable.load()
            << ",\"ready\":" << ready.load() << ",\"lock_loss_max\":" << loss_max.load()
            << ",\"publish_max_ns\":" << publish_max << ",\"proof_max_ns\":" << proof_max
            << ",\"publish_overruns\":" << publish_overruns << ",\"proof_overruns\":" << proof_overruns
            << ",\"writer_scheduling_jitter_max_ns\":" << writer_jitter_max.load()
            << ",\"instrumented_safety_only\":" << (mode == "tsan" ? "true" : "false") << "}\n";
    return qualified ? 0 : 1;
  } catch (const std::exception & failure) {
    std::cerr << failure.what() << "\n";
    return 2;
  }
}
