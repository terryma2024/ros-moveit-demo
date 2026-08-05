#include <gtest/gtest.h>

#include <chrono>
#include <atomic>
#include <future>
#include <memory>
#include <optional>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "pick_place_common/moveit_scene_executor.hpp"

namespace pick_place_common::ros_adapters
{
namespace
{
ActionResult success()
{
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

class FakeAdapter final : public IMoveItSceneAdapter
{
public:
  ActionResult attachTaskObject(const MoveItAttachmentSpec & spec) override
  {
    calls.emplace_back("attach");
    attachment = spec;
    return success();
  }
  ActionResult detachTaskObject() override
  {
    calls.emplace_back("detach");
    return success();
  }
  ActionResult upsertTaskObjectWorldPose(const Pose3d & pose) override
  {
    calls.emplace_back("upsert");
    upserted_pose = pose;
    return success();
  }
  std::optional<MoveItSceneState> observe() override
  {
    observation_count.fetch_add(1);
    if (states.empty()) {
      return std::nullopt;
    }
    const auto index = state_index < states.size() ? state_index++ : states.size() - 1;
    return states[index];
  }

  std::vector<std::string> calls;
  MoveItAttachmentSpec attachment;
  std::optional<Pose3d> upserted_pose;
  std::vector<MoveItSceneState> states;
  std::size_t state_index{0};
  std::atomic<std::size_t> observation_count{0};
};

class FakePolicy final : public IMoveItScenePolicy
{
public:
  ScenePreparation prepare(MoveItSceneOperation operation, const ExecutionContext &) const override
  {
    observed_operation = operation;
    return preparation;
  }

  ScenePreparation preparation;
  mutable MoveItSceneOperation observed_operation{MoveItSceneOperation::SYNC};
};

ExecutionContext context(State state)
{
  return {state, State::ERROR, WorldSnapshot{}, nullptr};
}

MoveItSceneConfig config(State state, MoveItSceneOperation operation)
{
  return {state, operation, false, "task_object", {"tool", {"tool", "left_finger", "right_finger"}},
          0.03,  0.001};
}

TEST(MoveItSceneExecutor, UpsertsBeforeAttachAndRequiresExclusiveMembershipAndExactTouchLinks)
{
  const Pose3d pose{0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 1.0};
  auto adapter = std::make_shared<FakeAdapter>();
  adapter->states = {{true, true, "tool", {"tool", "left_finger", "right_finger"}, std::nullopt},
                     {false, true, "tool", {"right_finger", "left_finger", "tool"}, std::nullopt},
                     {false, true, "tool", {"tool", "left_finger", "right_finger"}, std::nullopt}};
  auto policy = std::make_shared<FakePolicy>();
  policy->preparation = {false, true, pose, std::nullopt};
  MoveItSceneExecutor executor(adapter, config(State::ATTACH_MOVEIT, MoveItSceneOperation::ATTACH),
                               policy);

  const auto result = executor.execute(context(State::ATTACH_MOVEIT));

  EXPECT_EQ(result.status, ActionStatus::SUCCEEDED);
  EXPECT_EQ(adapter->calls, (std::vector<std::string>{"upsert", "attach"}));
  EXPECT_EQ(adapter->attachment.touch_links,
            (std::vector<std::string>{"tool", "left_finger", "right_finger"}));
  EXPECT_EQ(adapter->observation_count.load(), 3U);
}

TEST(MoveItSceneExecutor, DetachConvergesOnlyAfterReturningToWorld)
{
  auto adapter = std::make_shared<FakeAdapter>();
  adapter->states = {{false, false, "", {}, std::nullopt}, {true, false, "", {}, Pose3d{}}};
  auto policy = std::make_shared<FakePolicy>();
  MoveItSceneExecutor executor(adapter, config(State::DETACH_MOVEIT, MoveItSceneOperation::DETACH),
                               policy);

  EXPECT_EQ(executor.execute(context(State::DETACH_MOVEIT)).status, ActionStatus::SUCCEEDED);
  EXPECT_EQ(adapter->calls, (std::vector<std::string>{"detach"}));
  EXPECT_EQ(adapter->observation_count.load(), 2U);
}

TEST(MoveItSceneExecutor, SyncConvergesAtPreparedPose)
{
  const Pose3d pose{0.4, -0.2, 0.7, 0.0, 0.0, 0.0, 1.0};
  auto adapter = std::make_shared<FakeAdapter>();
  adapter->states = {{true, false, "", {}, pose}};
  auto policy = std::make_shared<FakePolicy>();
  policy->preparation.task_object_pose = pose;
  MoveItSceneExecutor executor(
    adapter, config(State::SYNC_WORLD_OBJECT, MoveItSceneOperation::SYNC), policy);

  EXPECT_EQ(executor.execute(context(State::SYNC_WORLD_OBJECT)).status, ActionStatus::SUCCEEDED);
  ASSERT_TRUE(adapter->upserted_pose.has_value());
  EXPECT_DOUBLE_EQ(adapter->upserted_pose->x, pose.x);
}

TEST(MoveItSceneExecutor, TimeoutReportsObservationCount)
{
  auto adapter = std::make_shared<FakeAdapter>();
  auto policy = std::make_shared<FakePolicy>();
  MoveItSceneExecutor executor(adapter, config(State::DETACH_MOVEIT, MoveItSceneOperation::DETACH),
                               policy);

  const auto result = executor.execute(context(State::DETACH_MOVEIT));

  ASSERT_EQ(result.status, ActionStatus::TIMED_OUT);
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ(result.failure->code, "MOVEIT_SCENE_CONVERGENCE_TIMEOUT");
  EXPECT_EQ(result.failure->metrics.at("observation_count"), adapter->observation_count.load());
  EXPECT_GT(adapter->observation_count.load(), 0U);
}

TEST(MoveItSceneExecutor, CancelInterruptsConvergenceWait)
{
  auto adapter = std::make_shared<FakeAdapter>();
  auto policy = std::make_shared<FakePolicy>();
  auto execution_config = config(State::DETACH_MOVEIT, MoveItSceneOperation::DETACH);
  execution_config.timeout_seconds = 1.0;
  execution_config.poll_interval_seconds = 0.5;
  MoveItSceneExecutor executor(adapter, execution_config, policy);
  auto future = std::async(
    std::launch::async, [&executor]() { return executor.execute(context(State::DETACH_MOVEIT)); });
  while (adapter->observation_count.load() == 0U) {
    std::this_thread::yield();
  }

  EXPECT_EQ(executor.cancel().status, ActionStatus::SUCCEEDED);
  const auto result = future.get();
  EXPECT_EQ(result.status, ActionStatus::CANCELLED);
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ(result.failure->code, "MOVEIT_SCENE_CANCELLED");
}

TEST(MoveItSceneExecutor, PolicyControlsIdempotentSkip)
{
  auto adapter = std::make_shared<FakeAdapter>();
  auto policy = std::make_shared<FakePolicy>();
  policy->preparation.skip_command = true;
  auto execution_config = config(State::DETACH_MOVEIT, MoveItSceneOperation::DETACH);
  execution_config.idempotent = true;
  MoveItSceneExecutor executor(adapter, execution_config, policy);

  EXPECT_EQ(executor.execute(context(State::DETACH_MOVEIT)).status, ActionStatus::SUCCEEDED);
  EXPECT_TRUE(adapter->calls.empty());
  EXPECT_EQ(adapter->observation_count.load(), 0U);
}
}  // namespace
}  // namespace pick_place_common::ros_adapters
