#include <gtest/gtest.h>

#include <algorithm>
#include <chrono>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <shape_msgs/msg/solid_primitive.hpp>

#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "so101_gazebo_demo/pick_place/moveit_scene_executor.hpp"
#include "so101_gazebo_demo/pick_place/so101_moveit_scene_policy.hpp"
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
  return {profile.world_frame,
          "table",
          profile.table_size,
          "base_pedestal",
          profile.pedestal_size,
          "plastic_cup",
          0.090,
          0.040,
          0.002,
          0.002,
          12};
}

MoveItAttachmentSpec canonicalAttachment()
{
  const auto & profile = SO101Profile::canonical();
  return {profile.moveit_attach_link, profile.moveit_touch_links};
}

MoveItSceneState attachedState(bool in_world = false)
{
  MoveItSceneState state;
  state.task_object_in_world = in_world;
  state.task_object_attached = true;
  state.attached_link = "gripper";
  state.touch_links = {"gripper", "jaw"};
  return state;
}

MoveItSceneState detachedState(const Pose3d & pose = {})
{
  MoveItSceneState state;
  state.task_object_in_world = true;
  state.task_object_attached = false;
  state.task_object_world_pose = pose;
  return state;
}

class FakeMoveItSceneAdapter final : public ISO101MoveItSceneAdapter
{
public:
  ActionResult attachTaskObject(const MoveItAttachmentSpec & spec) override
  {
    calls.emplace_back("attach");
    attached_spec = spec;
    ++attach_calls;
    return attach_result;
  }

  ActionResult detachTaskObject() override
  {
    ++detach_calls;
    return detach_result;
  }

  ActionResult upsertTaskObjectWorldPose(const Pose3d & pose) override
  {
    calls.emplace_back("upsert");
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
  std::vector<std::string> calls;
};

ExecutionContext contextFor(State state)
{
  WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.observed_at = std::chrono::steady_clock::now();
  snapshot.gazebo_task_object_pose_world = Pose3d{};
  snapshot.gazebo_pose_sequence = 1;
  snapshot.gazebo_pose_observed_at = snapshot.observed_at;
  snapshot.moveit_gripper_pose_world = Pose3d{};
  return {state, State::ERROR, std::move(snapshot), nullptr};
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

  const Pose3d cup_pose{0.02, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0};
  const auto cup = makeTaskObjectCollisionObject(geometry, cup_pose);
  ASSERT_EQ(13U, cup.primitives.size());
  ASSERT_EQ(13U, cup.primitive_poses.size());
  EXPECT_EQ("world", cup.header.frame_id);
  EXPECT_EQ("plastic_cup", cup.id);
  EXPECT_EQ(12U,
            std::count_if(cup.primitives.begin(), cup.primitives.end(), [](const auto & primitive) {
              return primitive.type == shape_msgs::msg::SolidPrimitive::BOX;
            }));
  EXPECT_EQ(1U,
            std::count_if(cup.primitives.begin(), cup.primitives.end(), [](const auto & primitive) {
              return primitive.type == shape_msgs::msg::SolidPrimitive::CYLINDER;
            }));
  EXPECT_DOUBLE_EQ(0.02, cup.pose.position.x);
  EXPECT_DOUBLE_EQ(-0.28, cup.pose.position.y);
  EXPECT_DOUBLE_EQ(0.165, cup.pose.position.z);
  EXPECT_DOUBLE_EQ(1.0, cup.pose.orientation.w);
}

TEST(SO101MoveItSceneExecutor, AttachUsesExactOrderedMetadataAndExclusiveMembership)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {attachedState(true), attachedState(false)};
  MoveItSceneExecutor executor(adapter,
                               {State::ATTACH_MOVEIT, MoveItSceneOperation::ATTACH, false,
                                "plastic_cup", canonicalAttachment(), 0.05, 0.001},
                               std::make_shared<SO101MoveItScenePolicy>("plastic_cup", false));

  const Pose3d settled_pose{0.0204, -0.2791, 0.1653, 0.01, -0.02, 0.03, 0.999};
  auto context = contextFor(State::ATTACH_MOVEIT);
  context.before.gazebo_task_object_pose_world = settled_pose;
  const auto result = executor.execute(context);

  EXPECT_EQ(ActionStatus::SUCCEEDED, result.status);
  ASSERT_TRUE(adapter->attached_spec);
  EXPECT_EQ("gripper", adapter->attached_spec->link_name);
  EXPECT_EQ((std::vector<std::string>{"gripper", "jaw"}), adapter->attached_spec->touch_links);
  ASSERT_TRUE(adapter->synced_pose);
  EXPECT_DOUBLE_EQ(settled_pose.x, adapter->synced_pose->x);
  EXPECT_DOUBLE_EQ(settled_pose.y, adapter->synced_pose->y);
  EXPECT_DOUBLE_EQ(settled_pose.z, adapter->synced_pose->z);
  EXPECT_EQ((std::vector<std::string>{"upsert", "attach"}), adapter->calls);
  EXPECT_EQ(2, adapter->observe_calls);
}

TEST(SO101MoveItSceneExecutor, AttachRejectsMissingSettledGazeboPose)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  MoveItSceneExecutor executor(adapter,
                               {State::ATTACH_MOVEIT, MoveItSceneOperation::ATTACH, false,
                                "plastic_cup", canonicalAttachment(), 0.05, 0.001},
                               std::make_shared<SO101MoveItScenePolicy>("plastic_cup", false));

  auto context = contextFor(State::ATTACH_MOVEIT);
  context.before.gazebo_task_object_pose_world.reset();
  const auto result = executor.execute(context);

  EXPECT_EQ(ActionStatus::FAILED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("GAZEBO_TASK_OBJECT_POSE_MISSING", result.failure->code);
  EXPECT_EQ(0, adapter->upsert_calls);
  EXPECT_EQ(0, adapter->attach_calls);
}

TEST(SO101MoveItSceneExecutor, RejectsWrongTouchLinkOrderDespiteApiSuccess)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  auto wrong = attachedState(false);
  wrong.touch_links = {"jaw", "gripper"};
  adapter->observations = {wrong};
  MoveItSceneExecutor executor(adapter,
                               {State::ATTACH_MOVEIT, MoveItSceneOperation::ATTACH, false,
                                "plastic_cup", canonicalAttachment(), 0.005, 0.001},
                               std::make_shared<SO101MoveItScenePolicy>("plastic_cup", false));

  auto context = contextFor(State::ATTACH_MOVEIT);
  context.before.gazebo_task_object_pose_world = SO101Profile::canonical().task_object_pose;
  const auto result = executor.execute(context);

  EXPECT_EQ(ActionStatus::TIMED_OUT, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("MOVEIT_SCENE_CONVERGENCE_TIMEOUT", result.failure->code);
}

TEST(SO101MoveItSceneExecutor, DetachRequiresExclusiveReturnToWorld)
{
  auto adapter = std::make_shared<FakeMoveItSceneAdapter>();
  adapter->observations = {attachedState(false), detachedState()};
  MoveItSceneExecutor executor(adapter,
                               {State::DETACH_MOVEIT, MoveItSceneOperation::DETACH, false,
                                "plastic_cup", canonicalAttachment(), 0.05, 0.001},
                               std::make_shared<SO101MoveItScenePolicy>("plastic_cup", false));

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
                               {State::SYNC_WORLD_OBJECT, MoveItSceneOperation::SYNC, false,
                                "plastic_cup", canonicalAttachment(), 0.05, 0.001},
                               std::make_shared<SO101MoveItScenePolicy>("plastic_cup", false));
  auto context = contextFor(State::SYNC_WORLD_OBJECT);
  context.before.gazebo_task_object_pose_world = pose;

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
