#include <gtest/gtest.h>

#include <array>
#include <chrono>
#include <cstdint>
#include <future>
#include <thread>
#include <limits>

#include "so101_mujoco_support/controller_stop_witness.hpp"

#include "controller_stop_witness_test_access.hpp"

namespace
{
using so101_mujoco_support::ControllerStopWitness;
using so101_mujoco_support::ControllerStopWitnessTestAccess;

ControllerStopWitness::Observation stopped_sample(uint64_t sequence)
{
  ControllerStopWitness::Observation sample{};
  sample.sequence = sequence;
  sample.sim_time_ns = static_cast<int64_t>(sequence) * 2000000;
  sample.received_monotonic_ns = 1000000000 + static_cast<int64_t>(sequence) * 2000000;
  sample.joint_count = 5;
  sample.holding = true;
  sample.active_goal = false;
  sample.measured_positions = {0.1, 0.2, 0.3, 0.4, 0.5};
  sample.reference_positions = sample.measured_positions;
  sample.measured_velocities.fill(0.0);
  sample.reference_velocities.fill(0.0);
  return sample;
}

void fill_stopped_window(ControllerStopWitness & witness)
{
  for (uint64_t sequence = 1; sequence <= 51; ++sequence) {
    witness.observe(stopped_sample(sequence));
  }
}
}  // namespace

TEST(ControllerStopWitness, RequiresACompleteFreshLocalStoppedWindow)
{
  ControllerStopWitness witness(5);
  for (uint64_t sequence = 1; sequence < 51; ++sequence) {
    witness.observe(stopped_sample(sequence));
  }
  EXPECT_FALSE(witness.proof(1102000000).has_value());
  witness.observe(stopped_sample(51));
  const auto proof = witness.proof(1102000000);
  ASSERT_TRUE(proof.has_value());
  EXPECT_EQ(proof->sample_count, 51u);
  EXPECT_EQ(proof->last_sim_time_ns, 102000000);
  EXPECT_EQ(proof->measured_positions[0], 0.1);
  EXPECT_FALSE(witness.proof(1303000000).has_value());
}

TEST(ControllerStopWitness, RejectsGapsMotionReferenceDriftAndActiveGoals)
{
  for (int mode = 0; mode < 6; ++mode) {
    ControllerStopWitness witness(5);
    fill_stopped_window(witness);
    auto changed = stopped_sample(52);
    if (mode == 0) {changed.sequence = 54;}
    if (mode == 1) {changed.sim_time_ns += 1;}
    if (mode == 2) {changed.measured_velocities[2] = 0.0021;}
    if (mode == 3) {changed.reference_positions[3] += 0.0001;}
    if (mode == 4) {changed.active_goal = true;}
    if (mode == 5) {changed.holding = false;}
    witness.observe(changed);
    EXPECT_FALSE(witness.proof(1104000000).has_value()) << mode;
  }
}

TEST(ControllerStopWitness, RejectsNonfiniteAndWrongJointScope)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  auto changed = stopped_sample(52);
  changed.measured_positions[0] = std::numeric_limits<double>::quiet_NaN();
  witness.observe(changed);
  EXPECT_FALSE(witness.proof(1104000000).has_value());
  changed = stopped_sample(53);
  changed.joint_count = 1;
  witness.observe(changed);
  EXPECT_FALSE(witness.proof(1106000000).has_value());
}

TEST(ControllerStopWitness, NonblockingInvalidationImmediatelyRevokesAWindow)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  ASSERT_TRUE(witness.proof(1102000000).has_value());
  witness.invalidate_nonblocking();
  EXPECT_FALSE(witness.proof(1102000000).has_value());
  witness.observe(stopped_sample(52));
  EXPECT_FALSE(witness.proof(1104000000).has_value());
}

TEST(ControllerStopWitness, ClockReadAllowsObserveAndRevalidatesWindow)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  bool observed = false;
  const auto proof = witness.proof_with_clock([&]() {
      if (!observed) {
        auto feedback = std::async(std::launch::async, [&]() {
            witness.observe(stopped_sample(52));
          });
        feedback.get();
        observed = true;
      }
      return int64_t{1104000000};
    });
  ASSERT_TRUE(proof);
  EXPECT_EQ(proof->last_sim_time_ns, 104000000);
  EXPECT_EQ(witness.checked_proof(1104000000).snapshot->cumulative_observation_lock_losses, 0u);
}

TEST(ControllerStopWitness, FreshFeedbackAfterRequestTimeUsesTheCurrentProofTime)
{
  const auto monotonic_now = []() {
      return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    };
  const auto request_time = monotonic_now();
  ControllerStopWitness witness(5);
  for (uint64_t sequence = 1; sequence <= 51; ++sequence) {
    auto sample = stopped_sample(sequence);
    sample.received_monotonic_ns = monotonic_now();
    witness.observe(sample);
  }
  EXPECT_FALSE(witness.proof(request_time).has_value());
  const auto proof = witness.proof();
  ASSERT_TRUE(proof.has_value());
  EXPECT_GT(proof->last_received_monotonic_ns, request_time);
  EXPECT_EQ(proof->sample_count, 51u);
}

TEST(ControllerStopWitness, LockedClockPreservesFutureAndAgeBoundaries)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  EXPECT_TRUE(witness.proof_with_clock([]() {return int64_t{1102000000};}).has_value());
  EXPECT_FALSE(witness.proof_with_clock([]() {return int64_t{1101999999};}).has_value());
  EXPECT_TRUE(witness.proof_with_clock([]() {return int64_t{1202000000};}).has_value());
  EXPECT_FALSE(witness.proof_with_clock([]() {return int64_t{1202000001};}).has_value());
  EXPECT_FALSE(witness.proof_with_clock([]() {return int64_t{-1};}).has_value());
}

TEST(ControllerStopWitness, LockedClockPreservesIncompleteAndUnsafeWindows)
{
  for (int mode = 0; mode < 7; ++mode) {
    ControllerStopWitness witness(5);
    fill_stopped_window(witness);
    auto changed = stopped_sample(52);
    if (mode == 0) {changed.sequence = 54;}
    if (mode == 1) {changed.sim_time_ns += 1;}
    if (mode == 2) {changed.measured_velocities[2] = 0.0021;}
    if (mode == 3) {changed.reference_positions[3] += 0.0001;}
    if (mode == 4) {changed.active_goal = true;}
    if (mode == 5) {changed.holding = false;}
    witness.observe(changed);
    if (mode == 6) {witness.invalidate_nonblocking();}
    EXPECT_FALSE(witness.proof_with_clock([]() {return int64_t{1104000000};}).has_value())
      << mode;
  }
}

TEST(ControllerStopWitness, CheckedProofReportsWindowAndFreshnessBoundaries)
{
  using Reason = ControllerStopWitness::RejectionReason;
  ControllerStopWitness witness(5);
  auto checked = witness.checked_proof(1102000000);
  EXPECT_FALSE(checked.proof.has_value());
  EXPECT_EQ(checked.snapshot->rejection, Reason::INCOMPLETE);
  EXPECT_EQ(checked.snapshot->last_reset_reason, ControllerStopWitness::ResetReason::UNKNOWN);
  EXPECT_EQ(checked.snapshot->sample_count, 0u);
  EXPECT_FALSE(checked.snapshot->has_samples);
  fill_stopped_window(witness);
  struct Case {int64_t now; Reason reason; int index;};
  const std::array<Case, 5> cases{{
    {1102000000, Reason::NONE, -1},
    {1101999999, Reason::FUTURE_SAMPLE, 50},
    {1202000000, Reason::NONE, -1},
    {1202000001, Reason::STALE_SAMPLE, 0},
    {-1, Reason::NEGATIVE_NOW, -1}}};
  for (const auto & item : cases) {
    const auto result = witness.checked_proof(item.now);
    EXPECT_EQ(result.proof.has_value(), witness.proof(item.now).has_value());
    EXPECT_EQ(result.snapshot->rejection, item.reason);
    EXPECT_EQ(result.snapshot->failing_sample_index, item.index);
    EXPECT_EQ(result.snapshot->sample_count, 51u);
    EXPECT_EQ(result.snapshot->evaluated_monotonic_ns, item.now);
    EXPECT_EQ(result.snapshot->first.sequence, 1u);
    EXPECT_EQ(result.snapshot->last.sequence, 51u);
    EXPECT_EQ(result.snapshot->first.sim_time_ns, 2000000);
    EXPECT_EQ(result.snapshot->last.received_monotonic_ns, 1102000000);
    if (result.proof) {
      const auto original = witness.proof(item.now);
      EXPECT_EQ(result.proof->measured_positions, original->measured_positions);
      EXPECT_EQ(result.proof->reference_positions, original->reference_positions);
      EXPECT_EQ(result.proof->last_sim_time_ns, original->last_sim_time_ns);
    }
  }
}

TEST(ControllerStopWitness, CheckedProofIdentifiesReferenceChangeWithoutResettingWindow)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  auto changed = stopped_sample(52);
  changed.reference_positions[3] += 0.0001;
  witness.observe(changed);
  const auto result = witness.checked_proof(1104000000);
  EXPECT_FALSE(result.proof.has_value());
  EXPECT_FALSE(witness.proof(1104000000).has_value());
  EXPECT_EQ(result.snapshot->rejection, ControllerStopWitness::RejectionReason::REFERENCE_CHANGED);
  EXPECT_EQ(result.snapshot->failing_sample_index, 50);
  EXPECT_EQ(result.snapshot->failing_joint_index, 3);
  EXPECT_EQ(result.snapshot->sample_count, 52u);
  EXPECT_EQ(result.snapshot->first.sequence, 2u);
}

TEST(ControllerStopWitness, CheckedProofReportsEveryInvalidObservationReset)
{
  using Reset = ControllerStopWitness::ResetReason;
  const std::array<Reset, 14> reasons{{Reset::ZERO_SEQUENCE, Reset::INVALID_SIM_TIME,
    Reset::INVALID_RECEIVED_TIME, Reset::JOINT_SCOPE, Reset::NOT_HOLDING, Reset::ACTIVE_GOAL,
    Reset::NONFINITE_MEASURED_POSITION, Reset::NONFINITE_MEASURED_VELOCITY,
    Reset::NONFINITE_REFERENCE_POSITION, Reset::NONFINITE_REFERENCE_VELOCITY,
    Reset::MEASURED_VELOCITY, Reset::REFERENCE_VELOCITY,
    Reset::MEASURED_VELOCITY, Reset::REFERENCE_VELOCITY}};
  for (size_t mode = 0; mode < reasons.size(); ++mode) {
    ControllerStopWitness witness(5);
    fill_stopped_window(witness);
    auto sample = stopped_sample(52);
    const auto nan = std::numeric_limits<double>::quiet_NaN();
    if (mode == 0) {sample.sequence = 0;}
    if (mode == 1) {sample.sim_time_ns = 0;}
    if (mode == 2) {sample.received_monotonic_ns = 0;}
    if (mode == 3) {sample.joint_count = 1;}
    if (mode == 4) {sample.holding = false;}
    if (mode == 5) {sample.active_goal = true;}
    if (mode == 6) {sample.measured_positions[2] = nan;}
    if (mode == 7) {sample.measured_velocities[2] = nan;}
    if (mode == 8) {sample.reference_positions[2] = nan;}
    if (mode == 9) {sample.reference_velocities[2] = nan;}
    if (mode == 10) {sample.measured_velocities[2] = 0.0020001;}
    if (mode == 11) {sample.reference_velocities[2] = 0.0020001;}
    if (mode == 12) {sample.measured_velocities[2] = -0.0020001;}
    if (mode == 13) {sample.reference_velocities[2] = -0.0020001;}
    witness.observe(sample);
    const auto result = witness.checked_proof(1104000000);
    EXPECT_FALSE(result.proof.has_value()) << mode;
    EXPECT_FALSE(witness.proof(1104000000).has_value()) << mode;
    EXPECT_EQ(result.snapshot->rejection, ControllerStopWitness::RejectionReason::INCOMPLETE);
    EXPECT_EQ(result.snapshot->last_reset_reason, reasons[mode]) << mode;
    EXPECT_EQ(result.snapshot->last_reset_joint_index, mode >= 6 ? 2 : -1) << mode;
    EXPECT_EQ(result.snapshot->last_reset_sample.sequence, sample.sequence);
    EXPECT_EQ(result.snapshot->sample_count, 0u);
    for (uint64_t seq = 53; seq <= 103; ++seq) {
      witness.observe(stopped_sample(seq));
    }
    EXPECT_TRUE(witness.checked_proof(1206000000).proof.has_value()) << mode;
    EXPECT_TRUE(witness.proof(1206000000).has_value()) << mode;
  }
}

TEST(ControllerStopWitness, CheckedProofReportsGapsAndRetainsResetAfterRecovery)
{
  using Reset = ControllerStopWitness::ResetReason;
  const std::array<Reset, 3> reasons{{Reset::SEQUENCE_GAP, Reset::SIM_TIME_GAP,
    Reset::RECEIVED_TIME_REGRESSION}};
  for (size_t mode = 0; mode < reasons.size(); ++mode) {
    ControllerStopWitness witness(5);
    fill_stopped_window(witness);
    auto sample = stopped_sample(52);
    if (mode == 0) {sample.sequence = 54;}
    if (mode == 1) {sample.sim_time_ns += 1;}
    if (mode == 2) {sample.received_monotonic_ns = 1101999999;}
    witness.observe(sample);
    auto result = witness.checked_proof(1104000000);
    EXPECT_FALSE(result.proof.has_value());
    EXPECT_FALSE(witness.proof(1104000000).has_value());
    EXPECT_EQ(result.snapshot->last_reset_reason, reasons[mode]);
    EXPECT_EQ(result.snapshot->sample_count, 1u);
    for (size_t index = 1; index <= 50; ++index) {
      ++sample.sequence;
      sample.sim_time_ns += 2000000;
      sample.received_monotonic_ns += 2000000;
      witness.observe(sample);
    }
    result = witness.checked_proof(sample.received_monotonic_ns);
    EXPECT_TRUE(result.proof.has_value());
    EXPECT_TRUE(witness.proof(sample.received_monotonic_ns).has_value());
    EXPECT_EQ(result.snapshot->last_reset_reason, reasons[mode]);
  }
}

TEST(ControllerStopWitness, CheckedProofSeparatesReaderFromWriterLockLoss)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  bool observed = false;
  const auto checked = witness.checked_proof_with_clock([&]() {
      if (!observed) {witness.observe(stopped_sample(52)); observed = true;}
      return int64_t{1104000000};
    });
  EXPECT_TRUE(checked.proof);
  EXPECT_EQ(checked.snapshot->cumulative_observation_lock_losses, 0u);
  ControllerStopWitnessTestAccess::writer_lock(witness);
  auto collision = std::async(std::launch::async, [&]() {witness.observe(stopped_sample(53));});
  collision.get();
  ControllerStopWitnessTestAccess::writer_unlock(witness);
  const auto lost = witness.checked_proof(1106000000);
  EXPECT_FALSE(lost.proof);
  EXPECT_EQ(lost.snapshot->rejection, ControllerStopWitness::RejectionReason::LOST);
  EXPECT_EQ(lost.snapshot->last_reset_reason, ControllerStopWitness::ResetReason::OBSERVATION_LOCK_LOSS);
  EXPECT_EQ(lost.snapshot->cumulative_observation_lock_losses, 1u);
  for (uint64_t seq = 54; seq <= 103; ++seq) {witness.observe(stopped_sample(seq));}
  EXPECT_FALSE(witness.proof(1206000000));
  witness.observe(stopped_sample(104));
  const auto recovered = witness.checked_proof(1208000000);
  EXPECT_TRUE(recovered.proof);
  EXPECT_EQ(recovered.snapshot->last_reset_reason, ControllerStopWitness::ResetReason::OBSERVATION_LOCK_LOSS);
}

TEST(ControllerStopWitness, CheckedProofReportsExplicitInvalidationAndReset)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  witness.invalidate_nonblocking();
  const auto result = witness.checked_proof(-1);
  EXPECT_EQ(result.snapshot->rejection, ControllerStopWitness::RejectionReason::LOST);
  EXPECT_EQ(result.snapshot->last_reset_reason,
    ControllerStopWitness::ResetReason::NONBLOCKING_INVALIDATION);
  EXPECT_FALSE(result.proof.has_value());
  EXPECT_FALSE(witness.proof(-1).has_value());
  witness.reset();
  const auto reset = witness.checked_proof(-1);
  EXPECT_EQ(reset.snapshot->rejection, ControllerStopWitness::RejectionReason::INCOMPLETE);
  EXPECT_EQ(reset.snapshot->last_reset_reason, ControllerStopWitness::ResetReason::EXPLICIT_RESET);
  EXPECT_FALSE(reset.snapshot->has_samples);
}

TEST(ControllerStopWitness, CheckedProofPreservesExactVelocityLimitForBothJointScopes)
{
  for (const size_t joints : {size_t{1}, size_t{5}}) {
    ControllerStopWitness witness(joints);
    for (uint64_t seq = 1; seq <= 80; ++seq) {
      auto sample = stopped_sample(seq);
      sample.joint_count = joints;
      sample.measured_velocities.fill(-0.002);
      sample.reference_velocities.fill(0.002);
      witness.observe(sample);
    }
    const auto result = witness.checked_proof(1160000000);
    ASSERT_TRUE(result.proof.has_value());
    EXPECT_TRUE(witness.proof(1160000000).has_value());
    EXPECT_EQ(result.snapshot->sample_count, 64u);
    EXPECT_EQ(result.snapshot->first.sequence, 30u);
    EXPECT_EQ(result.snapshot->last.sequence, 80u);
    EXPECT_EQ(result.proof->sample_count, 51u);
  }
}

TEST(ControllerStopWitness, aligned_500hz_queries_keep_window_and_recover_real_writer_loss)
{
  using namespace std::chrono_literals;
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  std::promise<void> captured, release;
  auto released = release.get_future();
  bool first = true;
  auto query = std::async(std::launch::async, [&]() {
      return witness.checked_proof_with_clock([&]() {
          if (first) {first = false; captured.set_value(); released.wait();}
          return int64_t{1104000000};
        });
    });
  captured.get_future().wait();
  witness.observe(stopped_sample(52));
  release.set_value();
  EXPECT_TRUE(query.get().proof);
  EXPECT_EQ(witness.checked_proof(1104000000).snapshot->cumulative_observation_lock_losses, 0u);
  ControllerStopWitnessTestAccess::writer_lock(witness);
  auto collision = std::async(std::launch::async, [&]() {witness.observe(stopped_sample(53));});
  collision.get();
  ControllerStopWitnessTestAccess::writer_unlock(witness);
  EXPECT_FALSE(witness.proof(1106000000));
  const auto replied = std::chrono::steady_clock::now();
  for (uint64_t seq = 54; seq <= 116; ++seq) {witness.observe(stopped_sample(seq));}
  std::this_thread::sleep_until(replied + 125ms);
  const auto recovered = witness.checked_proof(1232000000);
  EXPECT_TRUE(recovered.proof);
  EXPECT_EQ(recovered.snapshot->sample_count, 63u);
  EXPECT_EQ(recovered.snapshot->cumulative_observation_lock_losses, 1u);
  ASSERT_TRUE(recovered.proof);
  EXPECT_EQ(recovered.proof->sample_count, 51u);
  EXPECT_EQ(recovered.snapshot->last_reset_reason, ControllerStopWitness::ResetReason::OBSERVATION_LOCK_LOSS);
  EXPECT_EQ(witness.checked_proof(2232000000).snapshot->rejection, ControllerStopWitness::RejectionReason::STALE_SAMPLE);
}

TEST(ControllerStopWitness, sustained_aligned_reads_preserve_window_and_age_out_when_paused)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  for (uint64_t seq = 52; seq < 56; ++seq) {
    bool first = true;
    const auto check = witness.checked_proof_with_clock([&]() {
        if (first) {
          first = false;
          auto feedback = std::async(std::launch::async, [&]() {witness.observe(stopped_sample(seq));});
          feedback.get();
        }
        return int64_t{1200000000};
      });
    EXPECT_TRUE(check.proof);
  }
  EXPECT_EQ(witness.checked_proof(1200000000).snapshot->cumulative_observation_lock_losses, 0u);
  for (int i = 0; i < 5; ++i) {
    EXPECT_EQ(witness.checked_proof(1400000000).snapshot->rejection, ControllerStopWitness::RejectionReason::STALE_SAMPLE);
  }
}

TEST(ControllerStopWitness, ClockDelayedBeforeEvaluationUsesNewTime)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  const auto checked = witness.checked_proof_with_clock([]() {return int64_t{1303000000};});
  EXPECT_FALSE(checked.proof);
  EXPECT_EQ(checked.snapshot->rejection, ControllerStopWitness::RejectionReason::STALE_SAMPLE);
  EXPECT_EQ(checked.snapshot->evaluated_monotonic_ns, 1303000000);
}

TEST(ControllerStopWitness, PublishedReplacementNeverRevivesOldReady)
{
  for (int mode = 0; mode < 5; ++mode) {
    ControllerStopWitness witness(5);
    fill_stopped_window(witness);
    bool replaced = false;
    const auto result = witness.checked_proof_with_clock([&]() {
        if (!replaced) {
          replaced = true;
          if (mode == 0) {witness.reset();}
          else if (mode == 1) {witness.invalidate_nonblocking();}
          else {
            auto sample = stopped_sample(52);
            if (mode == 2) {sample.active_goal = true;}
            if (mode == 3) {sample.reference_positions[2] += 0.000001;}
            if (mode == 4) {sample.measured_velocities[0] = 0.002001;}
            witness.observe(sample);
          }
        }
        return int64_t{1104000000};
      });
    ASSERT_TRUE(result.snapshot) << mode;
    EXPECT_FALSE(result.proof) << mode;
    EXPECT_NE(result.snapshot->rejection, ControllerStopWitness::RejectionReason::NONE);
  }
}

TEST(ControllerStopWitness, PinThenThreeSlotRotationNeverOverwritesReader)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  const auto descriptor = ControllerStopWitnessTestAccess::pin(witness);
  for (uint64_t seq = 52; seq <= 61; ++seq) {
    witness.observe(stopped_sample(seq));
    EXPECT_EQ(ControllerStopWitnessTestAccess::pinned_last_sequence(witness, descriptor), 51u);
  }
  ControllerStopWitnessTestAccess::unpin(witness, descriptor);
  const auto check = witness.checked_proof(1122000000);
  ASSERT_TRUE(check.proof);
  EXPECT_EQ(check.snapshot->last.sequence, 61u);
  EXPECT_EQ(check.snapshot->cumulative_observation_lock_losses, 0u);
}

TEST(ControllerStopWitness, BusyReaderPinReturnsUnavailableWithoutWriterLoss)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  ControllerStopWitnessTestAccess::reader_lock(witness);
  auto reader = std::async(std::launch::async, [&]() {return witness.checked_proof(1104000000);});
  const auto unavailable = reader.get();
  witness.observe(stopped_sample(52));
  std::this_thread::sleep_for(std::chrono::milliseconds(5));
  ControllerStopWitnessTestAccess::reader_unlock(witness);
  EXPECT_EQ(unavailable.availability, ControllerStopWitness::CheckedProof::Availability::SNAPSHOT_UNAVAILABLE);
  EXPECT_FALSE(unavailable.snapshot);
  EXPECT_FALSE(unavailable.proof);
  const auto check = witness.checked_proof(1104000000);
  ASSERT_TRUE(check.proof);
  EXPECT_EQ(check.snapshot->cumulative_observation_lock_losses, 0u);
}

TEST(ControllerStopWitness, InvalidationAfterWriterLoadBeforePublishIsNotLost)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  ControllerStopWitnessTestAccess::publish_after_unhandled_invalidation(witness);
  const auto lost = witness.checked_proof(1102000000);
  ASSERT_TRUE(lost.snapshot);
  EXPECT_FALSE(lost.proof);
  EXPECT_EQ(lost.snapshot->rejection, ControllerStopWitness::RejectionReason::LOST);
  EXPECT_EQ(lost.snapshot->last_reset_reason, ControllerStopWitness::ResetReason::NONBLOCKING_INVALIDATION);
  for (uint64_t seq = 52; seq <= 101; ++seq) {witness.observe(stopped_sample(seq));}
  EXPECT_FALSE(witness.proof(1202000000));
  witness.observe(stopped_sample(102));
  EXPECT_TRUE(witness.proof(1204000000));
}

TEST(ControllerStopWitness, LossCountSaturatesWithoutSuppressingEvents)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  ControllerStopWitnessTestAccess::set_event(witness, 12, 0xFFFFFD);
  for (uint32_t i = 1; i <= 3; ++i) {
    ControllerStopWitnessTestAccess::writer_lock(witness);
    auto collision = std::async(std::launch::async, [&]() {witness.observe(stopped_sample(52));});
    collision.get();
    ControllerStopWitnessTestAccess::writer_unlock(witness);
    const auto checked = witness.checked_proof(1104000000);
    ASSERT_TRUE(checked.snapshot);
    EXPECT_EQ(checked.snapshot->rejection, ControllerStopWitness::RejectionReason::LOST);
    EXPECT_EQ(checked.snapshot->cumulative_observation_lock_losses, std::min(0xFFFFFDu + i, 0xFFFFFFu));
    EXPECT_EQ(ControllerStopWitnessTestAccess::event(witness) >> 32, 12u + i);
  }
}

TEST(ControllerStopWitness, VersionAndEventNearWrapFailClosed)
{
  for (int mode = 0; mode < 2; ++mode) {
    ControllerStopWitness witness(5);
    fill_stopped_window(witness);
    if (mode == 0) {
      ControllerStopWitnessTestAccess::set_version(witness, (uint64_t{1} << 62) - 2);
      witness.observe(stopped_sample(52));
    } else {
      ControllerStopWitnessTestAccess::set_event(witness, 0xFFFFFFFEu, 0);
      witness.invalidate_nonblocking();
    }
    for (int query = 0; query < 3; ++query) {
      const auto unavailable = witness.checked_proof(1104000000);
      EXPECT_FALSE(unavailable.snapshot);
      EXPECT_FALSE(unavailable.proof);
      EXPECT_EQ(unavailable.availability, ControllerStopWitness::CheckedProof::Availability::SNAPSHOT_UNAVAILABLE);
      witness.reset();
    }
  }
}

TEST(ControllerStopWitness, ThreeRetriesExhaustToUnavailable)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  uint64_t seq = 51;
  int calls = 0;
  const auto checked = witness.checked_proof_with_clock([&]() {
      ++calls;
      witness.observe(stopped_sample(++seq));
      return stopped_sample(seq).received_monotonic_ns;
    });
  EXPECT_EQ(calls, 3);
  EXPECT_FALSE(checked.proof);
  EXPECT_FALSE(checked.snapshot);
  EXPECT_EQ(checked.availability, ControllerStopWitness::CheckedProof::Availability::SNAPSHOT_UNAVAILABLE);
  EXPECT_TRUE(witness.proof(stopped_sample(seq).received_monotonic_ns));
}

TEST(ControllerStopWitness, EightFailedEventCasAttemptsPermanentlyReject)
{
  ControllerStopWitness witness(5);
  fill_stopped_window(witness);
  size_t calls = 0;
  EXPECT_FALSE(ControllerStopWitnessTestAccess::exhaust_cas(witness, calls));
  EXPECT_EQ(calls, 8u);
  EXPECT_FALSE(witness.checked_proof(1102000000).snapshot);
  witness.reset();
  EXPECT_FALSE(witness.checked_proof(1102000000).snapshot);
}
