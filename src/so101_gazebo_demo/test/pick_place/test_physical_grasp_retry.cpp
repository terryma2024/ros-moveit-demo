#include <algorithm>
#include <functional>
#include <iterator>
#include <memory>
#include <optional>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/physical_grasp_evidence_store.hpp"
#include "so101_gazebo_demo/pick_place/physical_grasp_retry.hpp"
#include "so101_gazebo_demo/pick_place/physical_grasp_stabilizer.hpp"
#include "so101_gazebo_demo/pick_place/so101_joint_motion_adapter.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{
spp::WorldSnapshot safeWorld()
{
  spp::WorldSnapshot world;
  world.fresh = true;
  world.arm_stationary = true;
  world.gazebo_task_object_stationary = true;
  world.gazebo_task_object_attached = false;
  world.moveit_task_object_attached = false;
  return world;
}

spp::PhysicalGraspResult failed(std::string code, bool contact = true)
{
  spp::PhysicalGraspResult result;
  result.failure.code = std::move(code);
  result.tcp_z_delta_m = 0.002;
  result.xy_slip_m = 0.0;
  result.orientation_change_rad = 0.0;
  result.gripper_contact = contact;
  return result;
}

spp::WorldSnapshot retryWorld(const spp::SO101Profile & profile)
{
  auto world = safeWorld();
  world.simulation_session_id = "retry-test";
  world.tcp_pose_world = {0.02, -0.28, 0.202, 0.0, 0.0, 0.0, 1.0};
  const spp::Pose3d cup{0.02, -0.28, 0.0, 0.0, 0.0, 0.0, 1.0};
  world.gazebo_task_object_pose_world = cup;
  world.moveit_world_object_poses[profile.task_object_id] = cup;
  world.gazebo_task_object_gripper_contact = true;
  world.gazebo_task_object_fixed_finger_contact = true;
  world.gazebo_task_object_moving_jaw_contact = true;
  world.gazebo_task_object_gripper_max_depth = 0.001;
  return world;
}

spp::PhysicalGraspEvidenceRecord retryRecord(const spp::SO101Profile & profile, bool success,
                                             bool contact = true)
{
  spp::PhysicalGraspEvidenceRecord record;
  record.simulation_session_id = "retry-test";
  record.configuration_fingerprint = "retry-fingerprint";
  record.retry.progress = {1, 0, profile.q6_contact};
  record.retry.micro_lift_preload_target_q6 =
    std::max(profile.q6_safe_lower, profile.q6_contact - profile.q6_regrasp_squeeze_offset);
  record.before_lift = spp::PhysicalGraspSample{spp::State::WAIT_GRASP_STABLE,
                                                1,
                                                {0.02, -0.28, 0.200, 0.0, 0.0, 0.0, 1.0},
                                                {0.02, -0.28, 0.0, 0.0, 0.0, 0.0, 1.0},
                                                true};
  record.after_lift = *record.before_lift;
  record.after_lift->capture_state = spp::State::WAIT_MICRO_LIFT_STABLE;
  record.after_lift->captured_at_unix_ns = 2;
  record.after_lift->tcp_pose_world.z += 0.002;
  record.after_lift->gripper_contact = contact;
  if (success)
    record.after_lift->task_object_pose_world.z += 0.002;
  return record;
}

struct EventRecorder
{
  void add(std::string event)
  {
    entries.push_back(std::move(event));
    if (after_event)
      after_event(entries.back());
  }
  std::vector<std::string> entries;
  std::function<void(const std::string &)> after_event;
};

class RecordingObserver final : public spp::IWorldObserver
{
public:
  spp::ObservationResult observe() override
  {
    events->add("observe");
    ++calls;
    if (fail_on_call && calls == *fail_on_call)
      return {std::nullopt, spp::Failure{spp::FailureCategory::OBSERVATION,
                                         "INJECTED_OBSERVER_FAILURE",
                                         "injected observer failure",
                                         {}}};
    return {current, std::nullopt};
  }
  std::shared_ptr<EventRecorder> events;
  spp::WorldSnapshot current;
  std::optional<std::size_t> fail_on_call;
  std::size_t calls{0};
};

class RecordingStore final : public spp::IPhysicalGraspEvidenceStore
{
public:
  std::optional<spp::Failure> resetForFreshRun() override
  {
    return std::nullopt;
  }
  std::optional<spp::Failure> saveBefore(const spp::WorldSnapshot & snapshot) override
  {
    events->add("save_before");
    record.before_lift =
      spp::PhysicalGraspSample{spp::State::WAIT_GRASP_STABLE, ++stamp, snapshot.tcp_pose_world,
                               *snapshot.gazebo_task_object_pose_world,
                               snapshot.gazebo_task_object_gripper_contact.value_or(false)};
    return std::nullopt;
  }
  std::optional<spp::Failure> saveAfter(const spp::WorldSnapshot & snapshot) override
  {
    events->add("save_after");
    record.after_lift =
      spp::PhysicalGraspSample{spp::State::WAIT_MICRO_LIFT_STABLE, ++stamp, snapshot.tcp_pose_world,
                               *snapshot.gazebo_task_object_pose_world,
                               snapshot.gazebo_task_object_gripper_contact.value_or(false)};
    return std::nullopt;
  }
  std::optional<spp::Failure>
  saveRetryEvidence(const spp::PhysicalGraspRetryEvidence & retry) override
  {
    record.retry = retry;
    events->add("save_" + std::to_string(static_cast<int>(retry.phase)));
    if (fail_phase && retry.phase == *fail_phase)
      return spp::Failure{spp::FailureCategory::CHECKPOINT,
                          "INJECTED_STORE_FAILURE",
                          "injected store failure",
                          {}};
    return std::nullopt;
  }
  std::variant<spp::PhysicalGraspEvidenceRecord, spp::Failure> load() const override
  {
    events->add("load");
    return record;
  }
  std::shared_ptr<EventRecorder> events;
  mutable spp::PhysicalGraspEvidenceRecord record;
  std::int64_t stamp{10};
  std::optional<spp::PhysicalGraspRetryPhase> fail_phase;
};

class RecordingGripper final : public spp::ISO101GripperCommand
{
public:
  spp::ActionResult command(double q6) override
  {
    targets.push_back(q6);
    events->add("gripper");
    if (fail_on_call && targets.size() == *fail_on_call)
      return {spp::ActionStatus::FAILED, spp::Failure{spp::FailureCategory::EXECUTION,
                                                      "INJECTED_GRIPPER_FAILURE",
                                                      "injected gripper failure",
                                                      {}}};
    const bool closed = q6 != profile.q6_preopen;
    observer->current.gazebo_task_object_gripper_contact = closed;
    observer->current.gazebo_task_object_fixed_finger_contact = closed;
    observer->current.gazebo_task_object_moving_jaw_contact = closed;
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult cancelAndWait() override
  {
    events->add("cancel_gripper");
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  std::shared_ptr<EventRecorder> events;
  std::shared_ptr<RecordingObserver> observer;
  spp::SO101Profile profile;
  std::vector<double> targets;
  std::optional<std::size_t> fail_on_call;
};

class RecordingMicroLift final : public spp::IWorldZMicroLift
{
public:
  spp::ActionResult executeWorldZMicroLift(const spp::Pose3d &, double delta) override
  {
    events->add("lift");
    ++lift_calls;
    if (fail_lift)
      return {spp::ActionStatus::FAILED, spp::Failure{spp::FailureCategory::EXECUTION,
                                                      "INJECTED_LIFT_FAILURE",
                                                      "injected lift failure",
                                                      {}}};
    observer->current.tcp_pose_world.z += delta;
    const bool follows = lift_calls <= cup_follows.size() && cup_follows[lift_calls - 1];
    const bool contact = lift_calls <= contacts.size() ? contacts[lift_calls - 1] : true;
    if (follows)
      observer->current.gazebo_task_object_pose_world->z += delta;
    observer->current.moveit_world_object_poses[profile.task_object_id] =
      *observer->current.gazebo_task_object_pose_world;
    observer->current.gazebo_task_object_gripper_contact = contact;
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult cancelWorldZMicroLift() override
  {
    events->add("cancel_lift");
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult executeWorldZMicroDescend(const spp::Pose3d &, double target_z) override
  {
    events->add("descend");
    descend_targets.push_back(target_z);
    if (fail_descend)
      return {spp::ActionStatus::FAILED, spp::Failure{spp::FailureCategory::EXECUTION,
                                                      "INJECTED_DESCEND_FAILURE",
                                                      "injected descend failure",
                                                      {}}};
    observer->current.tcp_pose_world.z = target_z;
    observer->current.gazebo_task_object_pose_world->z = 0.0;
    observer->current.moveit_world_object_poses[profile.task_object_id] =
      *observer->current.gazebo_task_object_pose_world;
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult cancelWorldZMicroDescend() override
  {
    events->add("cancel_descend");
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  std::shared_ptr<EventRecorder> events;
  std::shared_ptr<RecordingObserver> observer;
  spp::SO101Profile profile;
  std::vector<bool> cup_follows;
  std::vector<bool> contacts;
  std::vector<double> descend_targets;
  std::size_t lift_calls{0};
  bool fail_descend{false};
  bool fail_lift{false};
};

struct RetryHarness
{
  RetryHarness(bool initial_success, bool initial_contact = true) :
      events(std::make_shared<EventRecorder>()), observer(std::make_shared<RecordingObserver>()),
      store(std::make_shared<RecordingStore>()), gripper(std::make_shared<RecordingGripper>()),
      motion(std::make_shared<RecordingMicroLift>())
  {
    observer->events = events;
    observer->current = retryWorld(profile);
    store->events = events;
    store->record = retryRecord(profile, initial_success, initial_contact);
    gripper->events = events;
    gripper->observer = observer;
    gripper->profile = profile;
    motion->events = events;
    motion->observer = observer;
    motion->profile = profile;
    stabilizer =
      std::make_shared<spp::SO101PhysicalGraspStabilizer>(observer, store, gripper, profile);
    coordinator = std::make_unique<spp::PhysicalGraspRetryCoordinator>(
      gripper, motion, observer, store, stabilizer, spp::PhysicalGraspValidator{}, geometry,
      profile, spp::PhysicalGraspRetryConfig{});
  }
  spp::SO101Profile profile{spp::SO101Profile::canonical()};
  spp::PhysicalGraspGeometry geometry{0.0, 0.0};
  std::shared_ptr<EventRecorder> events;
  std::shared_ptr<RecordingObserver> observer;
  std::shared_ptr<RecordingStore> store;
  std::shared_ptr<RecordingGripper> gripper;
  std::shared_ptr<RecordingMicroLift> motion;
  std::shared_ptr<spp::SO101PhysicalGraspStabilizer> stabilizer;
  std::unique_ptr<spp::PhysicalGraspRetryCoordinator> coordinator;
};
}  // namespace

TEST(PhysicalGraspRetryCoordinator, ExposesTheApprovedSO101OnlyDependencyBoundary)
{
  EXPECT_TRUE((std::is_constructible_v<
               spp::PhysicalGraspRetryCoordinator, std::shared_ptr<spp::ISO101GripperCommand>,
               std::shared_ptr<spp::IWorldZMicroLift>, std::shared_ptr<spp::IWorldObserver>,
               std::shared_ptr<spp::IPhysicalGraspEvidenceStore>,
               std::shared_ptr<spp::SO101PhysicalGraspStabilizer>, spp::PhysicalGraspValidator,
               spp::PhysicalGraspGeometry, spp::SO101Profile, spp::PhysicalGraspRetryConfig>));
}

TEST(PhysicalGraspRetryCoordinator, InitialSuccessDispatchesNoRetrySideEffect)
{
  RetryHarness harness(true);
  const auto result = harness.coordinator->verifyOrRetry();
  EXPECT_EQ(result.status, spp::ActionStatus::SUCCEEDED);
  EXPECT_EQ(harness.motion->lift_calls, 0U);
  EXPECT_TRUE(harness.gripper->targets.empty());
  EXPECT_TRUE(harness.motion->descend_targets.empty());
}

TEST(PhysicalGraspRetryCoordinator, ContactMissingRunsExactRetryAndTightensOnlyReclose)
{
  RetryHarness harness(false, false);
  harness.motion->cup_follows = {true};
  harness.motion->contacts = {true};
  const auto result = harness.coordinator->verifyOrRetry();
  ASSERT_EQ(result.status, spp::ActionStatus::SUCCEEDED)
    << (result.failure ? result.failure->code : "");
  ASSERT_EQ(harness.gripper->targets.size(), 3U);
  EXPECT_DOUBLE_EQ(harness.gripper->targets[0], harness.profile.q6_preopen);
  EXPECT_DOUBLE_EQ(harness.gripper->targets[1], harness.profile.q6_contact - 0.001);
  EXPECT_DOUBLE_EQ(
    harness.gripper->targets[2],
    std::max(harness.profile.q6_safe_lower,
             harness.profile.q6_contact - harness.profile.q6_regrasp_squeeze_offset));
  ASSERT_EQ(harness.motion->descend_targets.size(), 1U);
  EXPECT_DOUBLE_EQ(harness.motion->descend_targets[0], 0.200);
  EXPECT_EQ(harness.motion->lift_calls, 1U);
  std::vector<std::string> major;
  std::copy_if(harness.events->entries.begin(), harness.events->entries.end(),
               std::back_inserter(major),
               [](const std::string & event) { return event != "observe"; });
  EXPECT_EQ(major,
            (std::vector<std::string>{"load", "save_1", "gripper", "save_2", "descend", "save_3",
                                      "gripper", "gripper", "save_before", "save_4", "lift",
                                      "save_after", "save_5", "load", "save_6"}));
}

TEST(PhysicalGraspRetryCoordinator, ContactPresentReusesCurrentRecloseTarget)
{
  RetryHarness harness(false, true);
  harness.motion->cup_follows = {true};
  harness.motion->contacts = {true};
  const auto result = harness.coordinator->verifyOrRetry();
  ASSERT_EQ(result.status, spp::ActionStatus::SUCCEEDED);
  ASSERT_EQ(harness.gripper->targets.size(), 3U);
  EXPECT_DOUBLE_EQ(harness.gripper->targets[1], harness.profile.q6_contact);
}

TEST(PhysicalGraspRetryCoordinator, SuccessOnAttemptsTwoThroughFiveStopsImmediately)
{
  for (std::size_t successful_attempt = 2; successful_attempt <= 5; ++successful_attempt) {
    RetryHarness harness(false, true);
    harness.motion->cup_follows.assign(successful_attempt - 1, false);
    harness.motion->cup_follows.back() = true;
    harness.motion->contacts.assign(successful_attempt - 1, true);
    const auto result = harness.coordinator->verifyOrRetry();
    ASSERT_EQ(result.status, spp::ActionStatus::SUCCEEDED) << successful_attempt;
    EXPECT_EQ(harness.motion->lift_calls, successful_attempt - 1) << successful_attempt;
    EXPECT_EQ(harness.motion->descend_targets.size(), successful_attempt - 1) << successful_attempt;
    EXPECT_EQ(harness.gripper->targets.size(), 3 * (successful_attempt - 1)) << successful_attempt;
    const auto preload =
      std::max(harness.profile.q6_safe_lower,
               harness.profile.q6_contact - harness.profile.q6_regrasp_squeeze_offset);
    for (std::size_t retry = 0; retry + 1 < successful_attempt; ++retry)
      EXPECT_DOUBLE_EQ(harness.gripper->targets[retry * 3 + 2], preload);
  }
}

TEST(PhysicalGraspRetryCoordinator, MixedContactExhaustionHasFourRetriesAndNoSixthSideEffect)
{
  RetryHarness harness(false, false);
  harness.motion->cup_follows = {false, false, false, false};
  harness.motion->contacts = {true, false, true, false};
  const auto result = harness.coordinator->verifyOrRetry();
  ASSERT_EQ(result.status, spp::ActionStatus::FAILED);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "PHYSICAL_GRASP_CONTACT_MISSING");
  EXPECT_EQ(result.failure->message, "Cup/gripper contact is required");
  EXPECT_EQ(harness.motion->lift_calls, 4U);
  EXPECT_EQ(harness.motion->descend_targets.size(), 4U);
  ASSERT_EQ(harness.gripper->targets.size(), 12U);
  EXPECT_DOUBLE_EQ(harness.gripper->targets[1], harness.profile.q6_contact - 0.001);
  EXPECT_DOUBLE_EQ(harness.gripper->targets[4], harness.profile.q6_contact - 0.001);
  EXPECT_DOUBLE_EQ(harness.gripper->targets[7], harness.profile.q6_contact - 0.002);
  EXPECT_DOUBLE_EQ(harness.gripper->targets[10], harness.profile.q6_contact - 0.002);
  EXPECT_EQ(result.failure->metrics.at("physical_grasp_attempts"), 5.0);
  EXPECT_EQ(result.failure->metrics.at("physical_grasp_retries"), 4.0);
  EXPECT_EQ(result.failure->metrics.at("retry_exhausted"), 1.0);
}

TEST(PhysicalGraspRetryCoordinator, UnsafeOrInterruptedEvidenceDispatchesNoRetry)
{
  RetryHarness unsafe(false);
  unsafe.observer->current.gazebo_task_object_attached = true;
  auto result = unsafe.coordinator->verifyOrRetry();
  EXPECT_EQ(result.status, spp::ActionStatus::FAILED);
  EXPECT_TRUE(unsafe.gripper->targets.empty());
  EXPECT_TRUE(unsafe.motion->descend_targets.empty());

  RetryHarness interrupted(false);
  interrupted.store->record.retry.phase = spp::PhysicalGraspRetryPhase::LIFT_PENDING;
  result = interrupted.coordinator->verifyOrRetry();
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "PHYSICAL_GRASP_RETRY_INTERRUPTED");
  EXPECT_TRUE(interrupted.gripper->targets.empty());
  EXPECT_TRUE(interrupted.motion->descend_targets.empty());
}

TEST(PhysicalGraspRetryCoordinator, EveryExternalSubstepFailurePreservesItsExactCode)
{
  const auto expect_failure = [](RetryHarness & harness, const std::string & code) {
    const auto result = harness.coordinator->verifyOrRetry();
    ASSERT_TRUE(result.failure);
    EXPECT_EQ(result.failure->code, code);
  };
  {
    RetryHarness harness(false);
    harness.store->fail_phase = spp::PhysicalGraspRetryPhase::OPEN_PENDING;
    expect_failure(harness, "INJECTED_STORE_FAILURE");
    EXPECT_TRUE(harness.gripper->targets.empty());
  }
  {
    RetryHarness harness(false);
    harness.gripper->fail_on_call = 1;
    expect_failure(harness, "INJECTED_GRIPPER_FAILURE");
    EXPECT_NE(
      std::find(harness.events->entries.begin(), harness.events->entries.end(), "cancel_gripper"),
      harness.events->entries.end());
  }
  {
    RetryHarness harness(false);
    harness.motion->fail_descend = true;
    expect_failure(harness, "INJECTED_DESCEND_FAILURE");
    EXPECT_NE(
      std::find(harness.events->entries.begin(), harness.events->entries.end(), "cancel_descend"),
      harness.events->entries.end());
  }
  {
    RetryHarness harness(false);
    harness.gripper->fail_on_call = 2;
    expect_failure(harness, "INJECTED_GRIPPER_FAILURE");
  }
  {
    RetryHarness harness(false);
    harness.observer->fail_on_call = 4;
    expect_failure(harness, "INJECTED_OBSERVER_FAILURE");
  }
  {
    RetryHarness harness(false);
    harness.motion->fail_lift = true;
    expect_failure(harness, "INJECTED_LIFT_FAILURE");
    EXPECT_NE(
      std::find(harness.events->entries.begin(), harness.events->entries.end(), "cancel_lift"),
      harness.events->entries.end());
  }
}

TEST(PhysicalGraspRetryCoordinator, EveryInterruptedPhaseFailsClosedWithoutSideEffects)
{
  const spp::PhysicalGraspRetryPhase phases[]{
    spp::PhysicalGraspRetryPhase::OPEN_PENDING, spp::PhysicalGraspRetryPhase::DESCEND_PENDING,
    spp::PhysicalGraspRetryPhase::CLOSE_PENDING, spp::PhysicalGraspRetryPhase::LIFT_PENDING,
    spp::PhysicalGraspRetryPhase::VERIFY_PENDING};
  for (const auto phase : phases) {
    RetryHarness harness(false);
    harness.store->record.retry.phase = phase;
    const auto result = harness.coordinator->verifyOrRetry();
    ASSERT_TRUE(result.failure);
    EXPECT_EQ(result.failure->code, "PHYSICAL_GRASP_RETRY_INTERRUPTED");
    EXPECT_TRUE(harness.gripper->targets.empty());
    EXPECT_TRUE(harness.motion->descend_targets.empty());
    EXPECT_EQ(harness.motion->lift_calls, 0U);
  }
}

TEST(PhysicalGraspRetryCoordinator, CancellationBetweenEveryCoordinatorCallDispatchesNothingLater)
{
  const std::vector<std::string> sequence{
    "load",        "save_1", "gripper", "save_2",     "descend", "save_3", "gripper", "gripper",
    "save_before", "save_4", "lift",    "save_after", "save_5",  "load",   "save_6"};
  for (std::size_t cancel_after = 0; cancel_after + 1 < sequence.size(); ++cancel_after) {
    RetryHarness harness(false, false);
    harness.motion->cup_follows = {true};
    harness.motion->contacts = {true};
    std::size_t next = 0;
    std::size_t event_count_at_cancel = 0;
    bool fired = false;
    harness.events->after_event = [&](const std::string & event) {
      if (fired || next >= sequence.size() || event != sequence[next])
        return;
      if (next == cancel_after) {
        fired = true;
        event_count_at_cancel = harness.events->entries.size();
        static_cast<void>(harness.coordinator->cancel());
      }
      ++next;
    };
    const auto result = harness.coordinator->verifyOrRetry();
    ASSERT_TRUE(fired) << cancel_after;
    EXPECT_EQ(result.status, spp::ActionStatus::FAILED) << cancel_after;
    ASSERT_TRUE(result.failure) << cancel_after;
    EXPECT_EQ(result.failure->code, "PHYSICAL_GRASP_RETRY_CANCELLED") << cancel_after;
    EXPECT_EQ(next, cancel_after + 1) << cancel_after;
    for (std::size_t index = event_count_at_cancel; index < harness.events->entries.size(); ++index)
      EXPECT_EQ(harness.events->entries[index].find("cancel_"), 0U)
        << cancel_after << ":" << harness.events->entries[index];
  }
}

TEST(PhysicalGraspRetry, ContactHistoryControlsOnlyCumulativeRecloseTarget)
{
  const auto & profile = spp::SO101Profile::canonical();
  spp::PhysicalGraspRetryProgress progress{1, 0, profile.q6_contact};
  const bool contacts[] = {false, true, false, true};
  const double offsets[] = {-0.001, -0.001, -0.002, -0.002};
  for (std::size_t index = 0; index < 4; ++index) {
    const auto decision = spp::decidePhysicalGraspRetry(
      {}, profile, progress,
      failed(contacts[index] ? "PHYSICAL_GRASP_FOLLOW_RATIO" : "PHYSICAL_GRASP_CONTACT_MISSING",
             contacts[index]),
      safeWorld());
    ASSERT_TRUE(decision.retry) << index << ":"
                                << (decision.rejection ? decision.rejection->code : "no rejection");
    EXPECT_DOUBLE_EQ(profile.q6_contact + offsets[index], decision.next.current_reclose_target_q6);
    progress = decision.next;
  }
}

TEST(PhysicalGraspRetry, RejectsExhaustionAndUnsafeFacts)
{
  const auto & profile = spp::SO101Profile::canonical();
  auto world = safeWorld();
  auto result = failed("PHYSICAL_GRASP_TABLE_CLEARANCE");
  EXPECT_FALSE(
    spp::decidePhysicalGraspRetry({}, profile, {5, 0, profile.q6_contact}, result, world).retry);
  result.tcp_z_delta_m = 0.0;
  EXPECT_FALSE(
    spp::decidePhysicalGraspRetry({}, profile, {1, 0, profile.q6_contact}, result, world).retry);
  result = failed("PHYSICAL_GRASP_XY_SLIP");
  EXPECT_FALSE(
    spp::decidePhysicalGraspRetry({}, profile, {1, 0, profile.q6_contact}, result, world).retry);
  result = failed("PHYSICAL_GRASP_ORIENTATION");
  EXPECT_FALSE(
    spp::decidePhysicalGraspRetry({}, profile, {1, 0, profile.q6_contact}, result, world).retry);
  result = failed("PHYSICAL_GRASP_FOLLOW_RATIO");
  world.gazebo_task_object_attached = true;
  EXPECT_FALSE(
    spp::decidePhysicalGraspRetry({}, profile, {1, 0, profile.q6_contact}, result, world).retry);
}
