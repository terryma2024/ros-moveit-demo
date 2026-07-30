#include <gtest/gtest.h>

#include <chrono>
#include <cmath>
#include <limits>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "so101_gazebo_demo/pick_place/world_readiness_gate.hpp"
#include "so101_gazebo_demo/pick_place/world_observer.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

constexpr auto kPoll = std::chrono::milliseconds(1);
constexpr auto kTimeout = std::chrono::milliseconds(100);
constexpr char kSession[] = "readiness-test-session";

spp::ObservationResult failure(std::string code)
{
  return {std::nullopt,
          spp::Failure{spp::FailureCategory::OBSERVATION, std::move(code), "test", {}}};
}

spp::WorldSnapshot readySnapshot()
{
  spp::WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.arm_stationary = true;
  snapshot.gazebo_task_object_pose_world = spp::Pose3d{0.1, -0.2, 0.3, 0.0, 0.0, 0.0, 1.0};
  snapshot.gazebo_task_object_attached = false;
  snapshot.simulation_session_id = kSession;
  return snapshot;
}

spp::ObservationResult snapshot(spp::WorldSnapshot value)
{
  return {std::move(value), std::nullopt};
}

class FakeObserver final : public spp::IWorldObserver
{
public:
  spp::ObservationResult observe() override
  {
    ++calls;
    if (next < observations.size()) {
      return observations[next++];
    }
    return observations.empty() ? failure("UNEXPECTED_OBSERVATION") : observations.back();
  }

  std::vector<spp::ObservationResult> observations;
  std::size_t next{0};
  int calls{0};
};

}  // namespace

TEST(WorldReadinessGate, retriesTransientMotionUntilSnapshotIsReady)
{
  FakeObserver observer;
  observer.observations = {failure("ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION"),
                           snapshot(readySnapshot())};

  spp::WorldReadinessGate gate(observer, kPoll, 1);
  EXPECT_FALSE(gate.waitForReady(kSession, kTimeout).has_value());
  EXPECT_EQ(observer.calls, 2);
}

TEST(WorldReadinessGate, retriesDelayedPoseAndAttachmentUntilSnapshotIsReady)
{
  auto no_pose = readySnapshot();
  no_pose.gazebo_task_object_pose_world.reset();
  auto no_attachment = readySnapshot();
  no_attachment.gazebo_task_object_attached.reset();
  FakeObserver observer;
  observer.observations = {snapshot(no_pose), snapshot(no_attachment), snapshot(readySnapshot())};

  spp::WorldReadinessGate gate(observer, kPoll, 1);
  EXPECT_FALSE(gate.waitForReady(kSession, kTimeout).has_value());
  EXPECT_EQ(observer.calls, 3);
}

TEST(WorldReadinessGate, requiresAStableRunOfReadyObservations)
{
  auto stale = readySnapshot();
  stale.fresh = false;
  FakeObserver observer;
  observer.observations = {snapshot(readySnapshot()), snapshot(stale), snapshot(readySnapshot()),
                           snapshot(readySnapshot()), snapshot(readySnapshot())};

  spp::WorldReadinessGate gate(observer, kPoll, 3);
  EXPECT_FALSE(gate.waitForReady(kSession, kTimeout).has_value());
  EXPECT_EQ(observer.calls, 5);
}

TEST(WorldReadinessGate, timesOutWhileOnlyTransientObservationIsAvailable)
{
  FakeObserver observer;
  observer.observations = {failure("GAZEBO_TASK_OBJECT_POSE_UNAVAILABLE")};

  spp::WorldReadinessGate gate(observer, kPoll);
  const auto result = gate.waitForReady(kSession, std::chrono::milliseconds(5));
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "WORLD_READINESS_TIMEOUT");
}

TEST(WorldReadinessGate, rejectsWrongSessionAndStaleSnapshotsUntilTimeout)
{
  auto wrong_session = readySnapshot();
  wrong_session.simulation_session_id = "other-session";
  auto stale = readySnapshot();
  stale.fresh = false;
  FakeObserver observer;
  observer.observations = {snapshot(wrong_session), snapshot(stale)};

  spp::WorldReadinessGate gate(observer, kPoll);
  const auto result = gate.waitForReady(kSession, std::chrono::milliseconds(5));
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "WORLD_READINESS_TIMEOUT");
}

TEST(WorldReadinessGate, rejectsNonFiniteTaskPoseUntilTimeout)
{
  auto nonfinite = readySnapshot();
  nonfinite.gazebo_task_object_pose_world->z = std::numeric_limits<double>::quiet_NaN();
  FakeObserver observer;
  observer.observations = {snapshot(nonfinite)};

  spp::WorldReadinessGate gate(observer, kPoll);
  const auto result = gate.waitForReady(kSession, std::chrono::milliseconds(5));
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "WORLD_READINESS_TIMEOUT");
}

TEST(WorldReadinessGate, returnsNonTransientFailureImmediately)
{
  FakeObserver observer;
  observer.observations = {failure("MOVEIT_SCENE_UNAVAILABLE")};

  spp::WorldReadinessGate gate(observer, kPoll);
  const auto result = gate.waitForReady(kSession, kTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "MOVEIT_SCENE_UNAVAILABLE");
  EXPECT_EQ(observer.calls, 1);
}
