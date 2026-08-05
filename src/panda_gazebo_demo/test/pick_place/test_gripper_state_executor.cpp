#include <gtest/gtest.h>

#include <memory>
#include <optional>

#include "panda_gazebo_demo/pick_place/gripper_command_adapter.hpp"
#include "panda_gazebo_demo/pick_place/gripper_state_executor.hpp"

namespace pick_place = panda_gazebo_demo::pick_place;

namespace
{

class FakeGripperCommandAdapter final : public pick_place::IGripperCommandAdapter
{
public:
  pick_place::ActionResult command(double position, double max_effort) override
  {
    ++command_calls;
    last_position = position;
    last_max_effort = max_effort;
    return command_result;
  }

  pick_place::ActionResult cancelAndWait() override
  {
    ++cancel_calls;
    return cancel_result;
  }

  pick_place::ActionResult command_result{pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  pick_place::ActionResult cancel_result{pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  int command_calls{0};
  int cancel_calls{0};
  double last_position{-1.0};
  double last_max_effort{-1.0};
};

pick_place::ExecutionContext contextFor(pick_place::State state,
                                        pick_place::WorldSnapshot before = {})
{
  return {state, pick_place::State::DONE, std::move(before), nullptr};
}

pick_place::WorldSnapshot safelyOpenSnapshot()
{
  pick_place::WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.arm_stationary = true;
  snapshot.gazebo_task_object_pose_world = pick_place::Pose3d{};
  snapshot.gazebo_task_object_attached = false;
  snapshot.moveit_task_object_attached = false;
  snapshot.gazebo_task_object_stationary = true;
  snapshot.joint_positions = {{"panda_finger_joint1", 0.04}, {"panda_finger_joint2", 0.04}};
  snapshot.joint_velocities = {{"panda_finger_joint1", 0.0}, {"panda_finger_joint2", 0.0}};
  return snapshot;
}

}  // namespace

TEST(GripperExecutor, CloseSendsZeroPositionOnce)
{
  const auto adapter = std::make_shared<FakeGripperCommandAdapter>();
  pick_place::GripperStateExecutor executor(adapter,
                                            {pick_place::State::CLOSE_GRIPPER, 0.0, 20.0, false});

  const auto result = executor.execute(contextFor(pick_place::State::CLOSE_GRIPPER));

  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(1, adapter->command_calls);
  EXPECT_DOUBLE_EQ(0.0, adapter->last_position);
  EXPECT_DOUBLE_EQ(20.0, adapter->last_max_effort);
}

TEST(GripperExecutor, RecoveryOpenNoOpsWhenSnapshotAlreadyOpen)
{
  const auto adapter = std::make_shared<FakeGripperCommandAdapter>();
  pick_place::GripperStateExecutor executor(
    adapter, {pick_place::State::RECOVER_OPEN_GRIPPER, 0.04, 20.0, true});

  const auto result =
    executor.execute(contextFor(pick_place::State::RECOVER_OPEN_GRIPPER, safelyOpenSnapshot()));

  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(0, adapter->command_calls);
}

TEST(GripperExecutor, RejectsUnsupportedStateBeforeSendingGoal)
{
  const auto adapter = std::make_shared<FakeGripperCommandAdapter>();
  pick_place::GripperStateExecutor executor(adapter,
                                            {pick_place::State::CLOSE_GRIPPER, 0.0, 20.0, false});

  const auto result = executor.execute(contextFor(pick_place::State::OPEN_GRIPPER));

  EXPECT_EQ(pick_place::ActionStatus::NOT_SUPPORTED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("STATE_NOT_EXECUTABLE", result.failure->code);
  EXPECT_EQ(0, adapter->command_calls);
}

TEST(GripperExecutor, PropagatesGoalRejection)
{
  const auto adapter = std::make_shared<FakeGripperCommandAdapter>();
  adapter->command_result = {pick_place::ActionStatus::FAILED,
                             pick_place::Failure{pick_place::FailureCategory::GRIPPER,
                                                 "GRIPPER_GOAL_REJECTED",
                                                 "goal rejected",
                                                 {}}};
  pick_place::GripperStateExecutor executor(adapter,
                                            {pick_place::State::OPEN_GRIPPER, 0.04, 20.0, false});

  const auto result = executor.execute(contextFor(pick_place::State::OPEN_GRIPPER));

  EXPECT_EQ(pick_place::ActionStatus::FAILED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("GRIPPER_GOAL_REJECTED", result.failure->code);
  EXPECT_EQ(1, adapter->command_calls);
}

TEST(GripperExecutor, WaitsForCancellationAcknowledgement)
{
  const auto adapter = std::make_shared<FakeGripperCommandAdapter>();
  pick_place::GripperStateExecutor executor(adapter,
                                            {pick_place::State::OPEN_GRIPPER, 0.04, 20.0, false});

  const auto result = executor.cancel();

  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(1, adapter->cancel_calls);
}

TEST(GripperExecutor, ReportsCancelRejectedInsteadOfSuccess)
{
  const auto adapter = std::make_shared<FakeGripperCommandAdapter>();
  adapter->cancel_result = {pick_place::ActionStatus::FAILED,
                            pick_place::Failure{pick_place::FailureCategory::GRIPPER,
                                                "GRIPPER_CANCEL_REJECTED",
                                                "cancel rejected",
                                                {}}};
  pick_place::GripperStateExecutor executor(adapter,
                                            {pick_place::State::OPEN_GRIPPER, 0.04, 20.0, false});

  const auto result = executor.cancel();

  EXPECT_EQ(pick_place::ActionStatus::FAILED, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("GRIPPER_CANCEL_REJECTED", result.failure->code);
  EXPECT_EQ(1, adapter->cancel_calls);
}
