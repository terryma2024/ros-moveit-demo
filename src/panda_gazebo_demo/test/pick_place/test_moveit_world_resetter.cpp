#include <gtest/gtest.h>

#include <limits>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "panda_gazebo_demo/pick_place/moveit_world_resetter.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

const Pose3d kResetPose{0.3, 0.0, 0.836, 0.0, 0.0, 0.0, 1.0};
const Pose3d kTablePose{0.0, 0.0, 0.75, 0.0, 0.0, 0.0, 1.0};

ActionResult succeeded()
{
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

ActionResult failed(std::string code)
{
  return {ActionStatus::FAILED,
          Failure{FailureCategory::MOVEIT_SCENE, std::move(code), "test failure", {}}};
}

MoveItSceneState attachedState()
{
  return {false, true, "panda_hand", {"panda_hand"}, std::nullopt, false, std::nullopt};
}

MoveItSceneState detachedState(std::optional<Pose3d> pose = std::nullopt)
{
  return {pose.has_value(), false, "", {}, pose, true, kTablePose};
}

class FakeMoveItSceneAdapter final : public IMoveItSceneAdapter
{
public:
  ActionResult attachCoke(const std::string &, const std::vector<std::string> &) override
  {
    return succeeded();
  }

  ActionResult detachCoke() override
  {
    ++detach_calls;
    commands.emplace_back("detach");
    return detach_result;
  }

  ActionResult syncCokeWorldPose(const Pose3d &) override
  {
    return succeeded();
  }

  ActionResult upsertCokeWorldPose(const Pose3d & pose) override
  {
    ++upsert_calls;
    commands.emplace_back("upsert");
    upserted_pose = pose;
    return upsert_result;
  }

  ActionResult upsertTableWorldPose(const Pose3d & pose) override
  {
    ++upsert_table_calls;
    commands.emplace_back("upsert_table");
    upserted_table_pose = pose;
    return upsert_table_result;
  }

  std::optional<MoveItSceneState> observe() override
  {
    ++observe_calls;
    if (observations.empty()) {
      return std::nullopt;
    }
    const auto index =
      observation_index < observations.size() ? observation_index++ : observations.size() - 1;
    return observations[index];
  }

  ActionResult detach_result{succeeded()};
  ActionResult upsert_result{succeeded()};
  ActionResult upsert_table_result{succeeded()};
  std::vector<MoveItSceneState> observations;
  std::size_t observation_index{0};
  int detach_calls{0};
  int upsert_calls{0};
  int upsert_table_calls{0};
  int observe_calls{0};
  std::vector<std::string> commands;
  std::optional<Pose3d> upserted_pose;
  std::optional<Pose3d> upserted_table_pose;
};

TEST(MoveItWorldResetter, UpsertsCanonicalTableBeforeCanonicalCoke)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {detachedState(), detachedState(kResetPose)};
  MoveItWorldResetter resetter(adapter, 0.05, 0.001);

  const auto result = resetter.reset(kResetPose);

  EXPECT_EQ(ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(1, adapter->upsert_table_calls);
  EXPECT_EQ((std::vector<std::string>{"upsert_table", "upsert"}), adapter->commands);
  ASSERT_TRUE(adapter->upserted_table_pose);
  EXPECT_DOUBLE_EQ(kTablePose.z, adapter->upserted_table_pose->z);
}

TEST(MoveItWorldResetter, DetachesThenUpsertsCanonicalWorldPose)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {attachedState(), detachedState(), detachedState(kResetPose)};
  MoveItWorldResetter resetter(adapter, 0.05, 0.001);

  const auto result = resetter.reset(kResetPose);

  EXPECT_EQ(ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(1, adapter->detach_calls);
  EXPECT_EQ(1, adapter->upsert_calls);
  EXPECT_EQ((std::vector<std::string>{"upsert_table", "detach", "upsert"}), adapter->commands);
  ASSERT_TRUE(adapter->upserted_pose);
  EXPECT_DOUBLE_EQ(kResetPose.z, adapter->upserted_pose->z);
}

TEST(MoveItWorldResetter, AlreadyDetachedStillUpsertsCanonicalPose)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {detachedState(), detachedState(kResetPose)};
  MoveItWorldResetter resetter(adapter, 0.05, 0.001);

  const auto result = resetter.reset(kResetPose);

  EXPECT_EQ(ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(0, adapter->detach_calls);
  EXPECT_EQ(1, adapter->upsert_calls);
}

TEST(MoveItWorldResetter, CreatesMissingWorldObjectThroughUpsert)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {detachedState(), detachedState(kResetPose)};
  MoveItWorldResetter resetter(adapter, 0.05, 0.001);

  const auto result = resetter.reset(kResetPose);

  EXPECT_EQ(ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(1, adapter->upsert_calls);
}

TEST(MoveItWorldResetter, PropagatesDetachCommandFailure)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {attachedState()};
  adapter->detach_result = failed("DETACH_REJECTED");
  MoveItWorldResetter resetter(adapter, 0.05, 0.001);

  const auto result = resetter.reset(kResetPose);

  EXPECT_EQ(ActionStatus::FAILED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("DETACH_REJECTED", result.failure->code);
  EXPECT_EQ(0, adapter->upsert_calls);
}

TEST(MoveItWorldResetter, RejectsNonConvergentDetach)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {attachedState()};
  MoveItWorldResetter resetter(adapter, 0.01, 0.001);

  const auto result = resetter.reset(kResetPose);

  EXPECT_EQ(ActionStatus::TIMED_OUT, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("MOVEIT_RESET_DETACH_TIMEOUT", result.failure->code);
  EXPECT_EQ(0, adapter->upsert_calls);
}

TEST(MoveItWorldResetter, PropagatesUpsertCommandFailure)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {detachedState()};
  adapter->upsert_result = failed("UPSERT_REJECTED");
  MoveItWorldResetter resetter(adapter, 0.05, 0.001);

  const auto result = resetter.reset(kResetPose);

  EXPECT_EQ(ActionStatus::FAILED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("UPSERT_REJECTED", result.failure->code);
}

TEST(MoveItWorldResetter, RejectsWrongFinalSixDofPose)
{
  auto wrong_pose = kResetPose;
  wrong_pose.qz = 0.1;
  wrong_pose.qw = 0.99498743710662;
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {detachedState(), detachedState(wrong_pose)};
  MoveItWorldResetter resetter(adapter, 0.01, 0.001);

  const auto result = resetter.reset(kResetPose);

  EXPECT_EQ(ActionStatus::TIMED_OUT, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("MOVEIT_RESET_SYNC_TIMEOUT", result.failure->code);
}

TEST(MoveItWorldResetter, RejectsNonFiniteTargetBeforeCommands)
{
  auto target = kResetPose;
  target.x = std::numeric_limits<double>::quiet_NaN();
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  MoveItWorldResetter resetter(adapter, 0.05, 0.001);

  const auto result = resetter.reset(target);

  EXPECT_EQ(ActionStatus::FAILED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("MOVEIT_RESET_TARGET_INVALID", result.failure->code);
  EXPECT_EQ(0, adapter->detach_calls);
  EXPECT_EQ(0, adapter->upsert_calls);
}

}  // namespace
}  // namespace panda_gazebo_demo::pick_place
