#include <gtest/gtest.h>

#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "panda_gazebo_demo/pick_place/moveit_scene_executor.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

ActionResult succeeded()
{
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

MoveItSceneState attachedState(bool in_world = false)
{
  return {
    in_world, true, "panda_hand",
    {"panda_hand", "panda_leftfinger", "panda_rightfinger"}, std::nullopt};
}

MoveItSceneState detachedState(const Pose3d & pose = {})
{
  return {true, false, "", {}, pose};
}

class FakeMoveItSceneAdapter final : public IMoveItSceneAdapter
{
public:
  ActionResult attachCoke(
    const std::string & link_name,
    const std::vector<std::string> & touch_links) override
  {
    ++attach_calls;
    attached_link = link_name;
    attached_touch_links = touch_links;
    return attach_result;
  }

  ActionResult detachCoke() override
  {
    ++detach_calls;
    return detach_result;
  }

  ActionResult syncCokeWorldPose(const Pose3d & pose) override
  {
    ++sync_calls;
    synced_pose = pose;
    return sync_result;
  }

  std::optional<MoveItSceneState> observe() override
  {
    ++observe_calls;
    if (observations.empty()) {
      return std::nullopt;
    }
    const auto index = observation_index < observations.size() ?
      observation_index++ : observations.size() - 1;
    return observations[index];
  }

  ActionResult attach_result{succeeded()};
  ActionResult detach_result{succeeded()};
  ActionResult sync_result{succeeded()};
  std::vector<MoveItSceneState> observations;
  std::size_t observation_index{0};
  int attach_calls{0};
  int detach_calls{0};
  int sync_calls{0};
  int observe_calls{0};
  std::string attached_link;
  std::vector<std::string> attached_touch_links;
  std::optional<Pose3d> synced_pose;
  int geometry_revision{17};
};

ExecutionContext contextFor(State state)
{
  return {state, State::ERROR, WorldSnapshot{}, nullptr};
}

MoveItSceneExecutor executorFor(
  const std::shared_ptr<FakeMoveItSceneAdapter> & adapter,
  State state, MoveItSceneOperation operation, bool idempotent = false)
{
  return MoveItSceneExecutor(adapter, {state, operation, idempotent}, 0.05, 0.001);
}

TEST(MoveItSceneExecutor, AttachUsesPandaHandAndExactTouchLinks)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {attachedState()};
  auto executor = executorFor(adapter, State::ATTACH_MOVEIT, MoveItSceneOperation::ATTACH);

  const auto result = executor.execute(contextFor(State::ATTACH_MOVEIT));

  EXPECT_EQ(result.status, ActionStatus::SUCCEEDED);
  EXPECT_EQ(adapter->attached_link, "panda_hand");
  EXPECT_EQ(adapter->attached_touch_links,
    (std::vector<std::string>{"panda_hand", "panda_leftfinger", "panda_rightfinger"}));
}

TEST(MoveItSceneExecutor, AttachWaitsForWorldAttachedMutualExclusion)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {attachedState(true), attachedState(false)};
  auto executor = executorFor(adapter, State::ATTACH_MOVEIT, MoveItSceneOperation::ATTACH);

  const auto result = executor.execute(contextFor(State::ATTACH_MOVEIT));

  EXPECT_EQ(result.status, ActionStatus::SUCCEEDED);
  EXPECT_EQ(adapter->observe_calls, 2);
}

TEST(MoveItSceneExecutor, DetachWaitsForReturnToWorld)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {attachedState(false), detachedState()};
  auto executor = executorFor(adapter, State::DETACH_MOVEIT, MoveItSceneOperation::DETACH);

  const auto result = executor.execute(contextFor(State::DETACH_MOVEIT));

  EXPECT_EQ(result.status, ActionStatus::SUCCEEDED);
  EXPECT_EQ(adapter->observe_calls, 2);
}

TEST(MoveItSceneExecutor, RecoveryDetachNoOpsWhenAlreadyDetached)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  auto executor = executorFor(
    adapter, State::RECOVER_DETACH_MOVEIT, MoveItSceneOperation::DETACH, true);
  auto context = contextFor(State::RECOVER_DETACH_MOVEIT);
  context.before.fresh = true;
  context.before.arm_stationary = true;
  context.before.gripper_open = true;
  context.before.gazebo_coke_attached = false;
  context.before.gazebo_coke_pose_world = Pose3d{};
  context.before.gazebo_coke_stationary = true;
  context.before.moveit_coke_attached = false;
  context.before.joint_positions = {{"panda_finger_joint1", 0.04},
    {"panda_finger_joint2", 0.04}};
  context.before.joint_velocities = {{"panda_finger_joint1", 0.0},
    {"panda_finger_joint2", 0.0}};
  context.before.moveit_world_object_poses.emplace("table", Pose3d{});
  context.before.moveit_world_object_poses.emplace("coke", Pose3d{});

  const auto result = executor.execute(context);

  EXPECT_EQ(result.status, ActionStatus::SUCCEEDED);
  EXPECT_EQ(adapter->detach_calls, 0);
  EXPECT_EQ(adapter->observe_calls, 0);
}

TEST(MoveItSceneExecutor, RecoveryNoOpUsesInjectedGripperLimits)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {detachedState()};
  GripperLimits strict_gripper;
  strict_gripper.open_min = 0.041;
  MoveItSceneExecutor executor(
    adapter, {State::RECOVER_DETACH_MOVEIT, MoveItSceneOperation::DETACH, true},
    0.05, 0.001, strict_gripper);
  auto context = contextFor(State::RECOVER_DETACH_MOVEIT);
  context.before.fresh = true;
  context.before.arm_stationary = true;
  context.before.gazebo_coke_attached = false;
  context.before.gazebo_coke_pose_world = Pose3d{};
  context.before.gazebo_coke_stationary = true;
  context.before.moveit_coke_attached = false;
  context.before.joint_positions = {{"panda_finger_joint1", 0.04},
    {"panda_finger_joint2", 0.04}};
  context.before.joint_velocities = {{"panda_finger_joint1", 0.0},
    {"panda_finger_joint2", 0.0}};
  context.before.moveit_world_object_poses.emplace("table", Pose3d{});
  context.before.moveit_world_object_poses.emplace("coke", Pose3d{});

  const auto result = executor.execute(context);

  EXPECT_EQ(result.status, ActionStatus::SUCCEEDED);
  EXPECT_EQ(adapter->detach_calls, 1);
}

TEST(MoveItSceneExecutor, SyncUsesBeforeGazeboPoseAndPreservesGeometry)
{
  const Pose3d gazebo_pose{0.42, -0.17, 0.84, 0.1, 0.2, 0.3, 0.9};
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {detachedState(gazebo_pose)};
  const int geometry_before = adapter->geometry_revision;
  auto executor = executorFor(
    adapter, State::SYNC_WORLD_OBJECT, MoveItSceneOperation::SYNC);
  auto context = contextFor(State::SYNC_WORLD_OBJECT);
  context.before.gazebo_coke_pose_world = gazebo_pose;

  const auto result = executor.execute(context);

  ASSERT_EQ(result.status, ActionStatus::SUCCEEDED);
  ASSERT_TRUE(adapter->synced_pose.has_value());
  EXPECT_DOUBLE_EQ(adapter->synced_pose->x, gazebo_pose.x);
  EXPECT_DOUBLE_EQ(adapter->synced_pose->y, gazebo_pose.y);
  EXPECT_DOUBLE_EQ(adapter->synced_pose->z, gazebo_pose.z);
  EXPECT_DOUBLE_EQ(adapter->synced_pose->qx, gazebo_pose.qx);
  EXPECT_DOUBLE_EQ(adapter->synced_pose->qy, gazebo_pose.qy);
  EXPECT_DOUBLE_EQ(adapter->synced_pose->qz, gazebo_pose.qz);
  EXPECT_DOUBLE_EQ(adapter->synced_pose->qw, gazebo_pose.qw);
  EXPECT_EQ(adapter->geometry_revision, geometry_before);
}

TEST(MoveItSceneExecutor, SyncRejectsMissingGazeboPose)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  auto executor = executorFor(
    adapter, State::SYNC_WORLD_OBJECT, MoveItSceneOperation::SYNC);

  const auto result = executor.execute(contextFor(State::SYNC_WORLD_OBJECT));

  EXPECT_EQ(result.status, ActionStatus::FAILED);
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ(result.failure->category, FailureCategory::MOVEIT_SCENE);
  EXPECT_EQ(result.failure->code, "GAZEBO_COKE_POSE_MISSING");
  EXPECT_EQ(adapter->sync_calls, 0);
}

}  // namespace
}  // namespace panda_gazebo_demo::pick_place
