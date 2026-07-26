#include <gtest/gtest.h>

#include <memory>
#include <optional>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include "so101_gazebo_demo/pick_place/so101_profile.hpp"
#include "so101_gazebo_demo/pick_place/world_reset_coordinator.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{

ActionResult succeeded()
{
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult failed(std::string code)
{
  return {ActionStatus::FAILED,
          Failure{FailureCategory::WORLD_INCONSISTENCY, std::move(code), "failure", {}}};
}

class FakeGazeboResetAdapter final : public IGazeboResetAdapter
{
public:
  std::optional<GazeboResetState> observe() override
  {
    ++observe_calls;
    return observation_available ? std::optional<GazeboResetState>(state) : std::nullopt;
  }

  ActionResult detachCoke() override
  {
    ++detach_calls;
    commands.emplace_back("gazebo_detach");
    if (detach_result.status == ActionStatus::SUCCEEDED && detach_converges) {
      state.coke_attached = false;
      ++state.attachment_revision;
    }
    return detach_result;
  }

  ActionResult setCokeWorldPose(const Pose3d & pose) override
  {
    ++set_pose_calls;
    commands.emplace_back("gazebo_pose");
    if (set_pose_result.status == ActionStatus::SUCCEEDED && pose_converges) {
      state.coke_world_pose = pose;
      ++state.pose_revision;
    }
    return set_pose_result;
  }

  GazeboResetState state;
  bool observation_available{true};
  bool detach_converges{true};
  bool pose_converges{true};
  ActionResult detach_result{succeeded()};
  ActionResult set_pose_result{succeeded()};
  int observe_calls{0};
  int detach_calls{0};
  int set_pose_calls{0};
  std::vector<std::string> commands;
};

class FakeMoveItSceneAdapter final : public IMoveItSceneAdapter
{
public:
  ActionResult attachCoke(const MoveItAttachmentSpec &) override
  {
    return succeeded();
  }

  ActionResult detachCoke() override
  {
    ++detach_calls;
    commands.emplace_back("moveit_detach");
    if (detach_result.status == ActionStatus::SUCCEEDED && detach_converges) {
      state.coke_attached = false;
      state.coke_in_world = true;
      state.attached_link.clear();
      state.touch_links.clear();
    }
    return detach_result;
  }

  ActionResult upsertCokeWorldPose(const Pose3d & pose) override
  {
    ++coke_upsert_calls;
    commands.emplace_back("moveit_coke");
    if (coke_upsert_result.status == ActionStatus::SUCCEEDED && upsert_converges) {
      state.coke_attached = false;
      state.coke_in_world = true;
      state.coke_world_pose = pose;
    }
    return coke_upsert_result;
  }

  ActionResult upsertTableWorldPose(const Pose3d & pose) override
  {
    ++table_upsert_calls;
    commands.emplace_back("moveit_table");
    if (table_upsert_result.status == ActionStatus::SUCCEEDED && upsert_converges) {
      state.table_in_world = true;
      state.table_world_pose = pose;
    }
    return table_upsert_result;
  }

  std::optional<MoveItSceneState> observe() override
  {
    ++observe_calls;
    return observation_available ? std::optional<MoveItSceneState>(state) : std::nullopt;
  }

  MoveItSceneState state;
  bool observation_available{true};
  bool detach_converges{true};
  bool upsert_converges{true};
  ActionResult detach_result{succeeded()};
  ActionResult coke_upsert_result{succeeded()};
  ActionResult table_upsert_result{succeeded()};
  int observe_calls{0};
  int detach_calls{0};
  int coke_upsert_calls{0};
  int table_upsert_calls{0};
  std::vector<std::string> commands;
};

WorldResetConfig canonicalConfig()
{
  const auto & profile = SO101Profile::canonical();
  return {profile.table_pose, profile.coke_pose, 0.02, 0.001, 1e-5, 1e-4};
}

void seed(const std::shared_ptr<FakeGazeboResetAdapter> & gazebo,
          const std::shared_ptr<FakeMoveItSceneAdapter> & moveit, bool gazebo_attached,
          bool moveit_attached)
{
  gazebo->state.coke_attached = gazebo_attached;
  gazebo->state.coke_world_pose = {0.3, 0.2, 0.4, 0.1, 0.2, 0.3, 0.9};
  gazebo->state.pose_revision = 10;
  gazebo->state.attachment_revision = 10;
  moveit->state.coke_attached = moveit_attached;
  moveit->state.coke_in_world = !moveit_attached;
  if (moveit_attached) {
    moveit->state.attached_link = "gripper";
    moveit->state.touch_links = {"gripper", "jaw"};
  }
}

TEST(SO101WorldResetCoordinator, FourInitialStatesUseOnlyNecessaryDetachCalls)
{
  const std::vector<std::tuple<bool, bool, int, int>> cases{{false, false, 0, 0},
                                                            {true, false, 1, 0},
                                                            {false, true, 0, 1},
                                                            {true, true, 1, 1}};

  for (const auto & [gazebo_attached, moveit_attached, expected_gazebo_detach,
                     expected_moveit_detach] : cases) {
    auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
    auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
    seed(gazebo, moveit, gazebo_attached, moveit_attached);
    WorldResetCoordinator resetter(gazebo, moveit, canonicalConfig());

    const auto result = resetter.reset();

    EXPECT_EQ(ActionStatus::SUCCEEDED, result.status);
    EXPECT_EQ(expected_gazebo_detach, gazebo->detach_calls);
    EXPECT_EQ(expected_moveit_detach, moveit->detach_calls);
    EXPECT_EQ(1, gazebo->set_pose_calls);
    EXPECT_EQ(1, moveit->table_upsert_calls);
    EXPECT_EQ(1, moveit->coke_upsert_calls);
    EXPECT_FALSE(gazebo->state.coke_attached);
    EXPECT_FALSE(moveit->state.coke_attached);
    EXPECT_TRUE(moveit->state.coke_in_world);
  }
}

TEST(SO101WorldResetCoordinator, RepeatedResetDoesNotIssueHistoricalDetachCalls)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  seed(gazebo, moveit, true, true);
  WorldResetCoordinator resetter(gazebo, moveit, canonicalConfig());

  ASSERT_EQ(ActionStatus::SUCCEEDED, resetter.reset().status);
  ASSERT_EQ(ActionStatus::SUCCEEDED, resetter.reset().status);

  EXPECT_EQ(1, gazebo->detach_calls);
  EXPECT_EQ(1, moveit->detach_calls);
  EXPECT_EQ(2, gazebo->set_pose_calls);
  EXPECT_EQ(2, moveit->table_upsert_calls);
  EXPECT_EQ(2, moveit->coke_upsert_calls);
}

TEST(SO101WorldResetCoordinator, StopsAfterGazeboDetachCommandFailure)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  seed(gazebo, moveit, true, true);
  gazebo->detach_result = failed("GAZEBO_DETACH_REJECTED");
  WorldResetCoordinator resetter(gazebo, moveit, canonicalConfig());

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::FAILED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("GAZEBO_DETACH_REJECTED", result.failure->code);
  EXPECT_EQ(0, moveit->detach_calls);
  EXPECT_EQ(0, gazebo->set_pose_calls);
  EXPECT_EQ(0, moveit->coke_upsert_calls);
}

TEST(SO101WorldResetCoordinator, ApiSuccessWithoutDetachConvergenceTimesOut)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  seed(gazebo, moveit, true, false);
  gazebo->detach_converges = false;
  auto config = canonicalConfig();
  config.timeout_seconds = 0.004;
  WorldResetCoordinator resetter(gazebo, moveit, config);

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::TIMED_OUT, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("WORLD_RESET_GAZEBO_DETACH_TIMEOUT", result.failure->code);
  EXPECT_EQ(0, gazebo->set_pose_calls);
}

TEST(SO101WorldResetCoordinator, RejectsWrongFinalOrientationAfterSuccessfulCommands)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  seed(gazebo, moveit, false, false);
  gazebo->pose_converges = false;
  auto config = canonicalConfig();
  config.timeout_seconds = 0.004;
  WorldResetCoordinator resetter(gazebo, moveit, config);

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::TIMED_OUT, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("WORLD_RESET_CONVERGENCE_TIMEOUT", result.failure->code);
}

TEST(SO101WorldResetCoordinator, MissingInitialObservationFailsBeforeCommands)
{
  auto gazebo = std::make_shared<FakeGazeboResetAdapter>();
  auto moveit = std::make_shared<FakeMoveItSceneAdapter>();
  gazebo->observation_available = false;
  WorldResetCoordinator resetter(gazebo, moveit, canonicalConfig());

  const auto result = resetter.reset();

  EXPECT_EQ(ActionStatus::FAILED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("WORLD_RESET_INITIAL_OBSERVATION_FAILED", result.failure->code);
  EXPECT_EQ(0, gazebo->detach_calls);
  EXPECT_EQ(0, moveit->detach_calls);
}

}  // namespace
}  // namespace so101_gazebo_demo::pick_place
