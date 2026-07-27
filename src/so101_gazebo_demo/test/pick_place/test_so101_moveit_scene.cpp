#include <gtest/gtest.h>

#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <shape_msgs/msg/solid_primitive.hpp>

#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "so101_gazebo_demo/pick_place/moveit_scene_executor.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{

ActionResult succeeded()
{
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

MoveItSceneGeometry canonicalGeometry()
{
  const auto & profile = SO101Profile::canonical();
  return {profile.world_frame, "table", profile.table_size,
          "base_pedestal", profile.pedestal_size,
          profile.coke_model, profile.coke_height, profile.coke_radius};
}

MoveItAttachmentSpec canonicalAttachment()
{
  const auto & profile = SO101Profile::canonical();
  return {profile.moveit_attach_link, profile.moveit_touch_links};
}

MoveItSceneState attachedState(bool in_world = false)
{
  MoveItSceneState state;
  state.coke_in_world = in_world;
  state.coke_attached = true;
  state.attached_link = "gripper";
  state.touch_links = {"gripper", "jaw"};
  return state;
}

MoveItSceneState detachedState(const Pose3d & pose = {})
{
  MoveItSceneState state;
  state.coke_in_world = true;
  state.coke_attached = false;
  state.coke_world_pose = pose;
  return state;
}

class FakeMoveItSceneAdapter final : public IMoveItSceneAdapter
{
public:
  ActionResult attachCoke(const MoveItAttachmentSpec & spec) override
  {
    attached_spec = spec;
    ++attach_calls;
    return attach_result;
  }

  ActionResult detachCoke() override
  {
    ++detach_calls;
    return detach_result;
  }

  ActionResult upsertCokeWorldPose(const Pose3d & pose) override
  {
    synced_pose = pose;
    ++upsert_calls;
    return sync_result;
  }

  ActionResult upsertTableWorldPose(const Pose3d &) override
  {
    return succeeded();
  }

  ActionResult upsertPedestalWorldPose(const Pose3d &) override
  {
    return succeeded();
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

  ActionResult attach_result{succeeded()};
  ActionResult detach_result{succeeded()};
  ActionResult sync_result{succeeded()};
  std::vector<MoveItSceneState> observations;
  std::size_t observation_index{0};
  int attach_calls{0};
  int detach_calls{0};
  int upsert_calls{0};
  int observe_calls{0};
  std::optional<MoveItAttachmentSpec> attached_spec;
  std::optional<Pose3d> synced_pose;
};

ExecutionContext contextFor(State state)
{
  return {state, State::ERROR, WorldSnapshot{}, nullptr};
}

TEST(SO101MoveItSceneGeometry, BuildsExactProfileDrivenCollisionObjects)
{
  const auto & profile = SO101Profile::canonical();
  const auto geometry = canonicalGeometry();

  const auto table = makeTableCollisionObject(geometry, profile.table_pose);
  ASSERT_EQ(1U, table.primitives.size());
  EXPECT_EQ("world", table.header.frame_id);
  EXPECT_EQ("table", table.id);
  EXPECT_EQ(shape_msgs::msg::SolidPrimitive::BOX, table.primitives.front().type);
  ASSERT_EQ(3U, table.primitives.front().dimensions.size());
  EXPECT_DOUBLE_EQ(0.50, table.primitives.front().dimensions[0]);
  EXPECT_DOUBLE_EQ(0.60, table.primitives.front().dimensions[1]);
  EXPECT_DOUBLE_EQ(0.04, table.primitives.front().dimensions[2]);
  EXPECT_DOUBLE_EQ(0.0, table.pose.position.x);
  EXPECT_DOUBLE_EQ(-0.20, table.pose.position.y);
  EXPECT_DOUBLE_EQ(0.10, table.pose.position.z);
  EXPECT_DOUBLE_EQ(1.0, table.pose.orientation.w);

  const auto pedestal = makePedestalCollisionObject(geometry, profile.pedestal_pose);
  ASSERT_EQ(1U, pedestal.primitives.size());
  EXPECT_EQ("world", pedestal.header.frame_id);
  EXPECT_EQ("base_pedestal", pedestal.id);
  EXPECT_EQ(shape_msgs::msg::SolidPrimitive::BOX, pedestal.primitives.front().type);
  ASSERT_EQ(3U, pedestal.primitives.front().dimensions.size());
  EXPECT_DOUBLE_EQ(0.18, pedestal.primitives.front().dimensions[0]);
  EXPECT_DOUBLE_EQ(0.18, pedestal.primitives.front().dimensions[1]);
  EXPECT_DOUBLE_EQ(0.10, pedestal.primitives.front().dimensions[2]);
  EXPECT_DOUBLE_EQ(0.0, pedestal.pose.position.x);
  EXPECT_DOUBLE_EQ(0.0, pedestal.pose.position.y);
  EXPECT_DOUBLE_EQ(0.17, pedestal.pose.position.z);
  EXPECT_DOUBLE_EQ(1.0, pedestal.pose.orientation.w);

  const auto coke = makeCokeCollisionObject(geometry, profile.coke_pose);
  ASSERT_EQ(1U, coke.primitives.size());
  EXPECT_EQ("world", coke.header.frame_id);
  EXPECT_EQ("coke", coke.id);
  EXPECT_EQ(shape_msgs::msg::SolidPrimitive::CYLINDER, coke.primitives.front().type);
  ASSERT_EQ(2U, coke.primitives.front().dimensions.size());
  EXPECT_DOUBLE_EQ(0.122, coke.primitives.front().dimensions[0]);
  EXPECT_DOUBLE_EQ(0.033, coke.primitives.front().dimensions[1]);
  EXPECT_DOUBLE_EQ(0.02, coke.pose.position.x);
  EXPECT_DOUBLE_EQ(-0.28, coke.pose.position.y);
  EXPECT_DOUBLE_EQ(0.181, coke.pose.position.z);
  EXPECT_DOUBLE_EQ(1.0, coke.pose.orientation.w);
}

TEST(SO101MoveItSceneExecutor, AttachUsesExactOrderedMetadataAndExclusiveMembership)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {attachedState(true), attachedState(false)};
  MoveItSceneExecutor executor(adapter, {State::ATTACH_MOVEIT, MoveItSceneOperation::ATTACH, false},
                               canonicalAttachment(), 0.05, 0.001);

  const auto result = executor.execute(contextFor(State::ATTACH_MOVEIT));

  EXPECT_EQ(ActionStatus::SUCCEEDED, result.status);
  ASSERT_TRUE(adapter->attached_spec);
  EXPECT_EQ("gripper", adapter->attached_spec->link_name);
  EXPECT_EQ((std::vector<std::string>{"gripper", "jaw"}), adapter->attached_spec->touch_links);
  EXPECT_EQ(2, adapter->observe_calls);
}

TEST(SO101MoveItSceneExecutor, RejectsWrongTouchLinkOrderDespiteApiSuccess)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  auto wrong = attachedState(false);
  wrong.touch_links = {"jaw", "gripper"};
  adapter->observations = {wrong};
  MoveItSceneExecutor executor(adapter, {State::ATTACH_MOVEIT, MoveItSceneOperation::ATTACH, false},
                               canonicalAttachment(), 0.005, 0.001);

  const auto result = executor.execute(contextFor(State::ATTACH_MOVEIT));

  EXPECT_EQ(ActionStatus::TIMED_OUT, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("MOVEIT_SCENE_CONVERGENCE_TIMEOUT", result.failure->code);
}

TEST(SO101MoveItSceneExecutor, DetachRequiresExclusiveReturnToWorld)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {attachedState(false), detachedState()};
  MoveItSceneExecutor executor(adapter, {State::DETACH_MOVEIT, MoveItSceneOperation::DETACH, false},
                               canonicalAttachment(), 0.05, 0.001);

  const auto result = executor.execute(contextFor(State::DETACH_MOVEIT));

  EXPECT_EQ(ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(1, adapter->detach_calls);
  EXPECT_EQ(2, adapter->observe_calls);
}

TEST(SO101MoveItSceneExecutor, SyncUsesAllSixPoseDegrees)
{
  const Pose3d pose{0.02, -0.28, 0.181, 0.1, -0.2, 0.3, 0.9};
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {detachedState(pose)};
  MoveItSceneExecutor executor(adapter,
                               {State::SYNC_WORLD_OBJECT, MoveItSceneOperation::SYNC, false},
                               canonicalAttachment(), 0.05, 0.001);
  auto context = contextFor(State::SYNC_WORLD_OBJECT);
  context.before.gazebo_coke_pose_world = pose;

  const auto result = executor.execute(context);

  EXPECT_EQ(ActionStatus::SUCCEEDED, result.status);
  ASSERT_TRUE(adapter->synced_pose);
  EXPECT_DOUBLE_EQ(0.1, adapter->synced_pose->qx);
  EXPECT_DOUBLE_EQ(-0.2, adapter->synced_pose->qy);
  EXPECT_DOUBLE_EQ(0.3, adapter->synced_pose->qz);
  EXPECT_DOUBLE_EQ(0.9, adapter->synced_pose->qw);
}

}  // namespace
}  // namespace so101_gazebo_demo::pick_place
