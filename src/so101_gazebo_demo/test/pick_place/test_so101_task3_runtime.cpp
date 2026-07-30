#include <gtest/gtest.h>

#include <memory>
#include <optional>

#include "so101_gazebo_demo/pick_place/common_resume_validator.hpp"
#include "so101_gazebo_demo/pick_place/runner.hpp"
#include "so101_gazebo_demo/pick_place/so101_task3_runtime.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

namespace
{

class FakeGripper final : public pick_place::ISO101GripperCommand
{
public:
  pick_place::ActionResult command(double q6) override
  {
    ++calls;
    last_q6 = q6;
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }
  pick_place::ActionResult cancelAndWait() override
  {
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }
  int calls{0};
  double last_q6{0.0};
};

class FakeExecutor final : public pick_place::IStateExecutor
{
public:
  pick_place::ActionResult execute(const pick_place::ExecutionContext &) override
  {
    ++calls;
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }
  pick_place::ActionResult cancel() override
  {
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }
  int calls{0};
};

class FakeScene final : public pick_place::IMoveItSceneAdapter
{
public:
  pick_place::ActionResult attachTaskObject(const pick_place::MoveItAttachmentSpec &) override
  {
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }
  pick_place::ActionResult detachTaskObject() override
  {
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }
  pick_place::ActionResult upsertTaskObjectWorldPose(const pick_place::Pose3d &) override
  {
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }
  pick_place::ActionResult upsertTableWorldPose(const pick_place::Pose3d &) override
  {
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }
  pick_place::ActionResult upsertPedestalWorldPose(const pick_place::Pose3d &) override
  {
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }
  std::optional<pick_place::MoveItSceneState> observe() override
  {
    return pick_place::MoveItSceneState{};
  }
};

class NeverObserved final : public pick_place::IWorldObserver
{
public:
  pick_place::ObservationResult observe() override
  {
    ++calls;
    return {std::nullopt,
            pick_place::Failure{pick_place::FailureCategory::OBSERVATION, "UNEXPECTED_OBSERVE",
                                "preflight should run first", {}}};
  }
  int calls{0};
};

class FakeCheckpointStore final : public pick_place::ICheckpointStore
{
public:
  std::optional<pick_place::Failure> commit(const pick_place::Checkpoint &) override
  {
    return std::nullopt;
  }
  pick_place::CheckpointLoadResult loadLatestCompatible() override
  {
    return {};
  }
};

pick_place::SO101Task3RuntimeDependencies dependencies()
{
  auto gazebo_attach = std::make_shared<FakeExecutor>();
  auto gazebo_detach = std::make_shared<FakeExecutor>();
  auto recovery_gazebo_detach = std::make_shared<FakeExecutor>();
  return {std::make_shared<FakeGripper>(), std::make_shared<FakeScene>(), gazebo_attach,
          gazebo_detach, recovery_gazebo_detach};
}

}  // namespace

TEST(SO101Task3Runtime, RegistersEveryNonMotionExecutorAndContractExactlyAtItsState)
{
  const auto runtime = pick_place::makeSO101Task3Runtime(dependencies());
  for (const auto state : {
         pick_place::State::PREPARE_OPEN_GRIPPER,
         pick_place::State::CLOSE_GRIPPER,
         pick_place::State::OPEN_GRIPPER,
         pick_place::State::RECOVER_OPEN_GRIPPER,
         pick_place::State::ATTACH_GAZEBO,
         pick_place::State::DETACH_GAZEBO,
         pick_place::State::RECOVER_DETACH_GAZEBO,
         pick_place::State::ATTACH_MOVEIT,
         pick_place::State::DETACH_MOVEIT,
         pick_place::State::SYNC_WORLD_OBJECT,
         pick_place::State::RECOVER_DETACH_MOVEIT,
         pick_place::State::RECOVER_SYNC_WORLD_OBJECT,
       }) {
    EXPECT_NE(nullptr, runtime.actions.findExecutor(state)) << pick_place::toString(state);
  }
  for (const auto state : {
         pick_place::State::MOVE_ABOVE_OBJECT,
         pick_place::State::DESCEND,
         pick_place::State::LIFT,
         pick_place::State::MOVE_ABOVE_PLACE,
         pick_place::State::DESCEND_TO_PLACE,
         pick_place::State::RETREAT,
         pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT,
         pick_place::State::RECOVER_MOVE_ABOVE_PICK,
         pick_place::State::RECOVER_DESCEND_TO_PICK,
         pick_place::State::RECOVER_RETREAT,
       }) {
    EXPECT_EQ(nullptr, runtime.actions.findExecutor(state)) << pick_place::toString(state);
    EXPECT_EQ(nullptr, runtime.actions.findPlanner(state)) << pick_place::toString(state);
  }

  for (const auto transition : {
         pick_place::TransitionKey{pick_place::State::PREPARE_OPEN_GRIPPER,
                                   pick_place::State::MOVE_ABOVE_OBJECT},
         {pick_place::State::CLOSE_GRIPPER, pick_place::State::WAIT_GRASP_STABLE},
         {pick_place::State::OPEN_GRIPPER, pick_place::State::DETACH_GAZEBO},
         {pick_place::State::RECOVER_OPEN_GRIPPER,
          pick_place::State::RECOVER_DETACH_GAZEBO},
         {pick_place::State::ATTACH_GAZEBO, pick_place::State::ATTACH_MOVEIT},
         {pick_place::State::ATTACH_MOVEIT, pick_place::State::LIFT},
         {pick_place::State::DETACH_GAZEBO, pick_place::State::DETACH_MOVEIT},
         {pick_place::State::DETACH_MOVEIT, pick_place::State::SYNC_WORLD_OBJECT},
         {pick_place::State::SYNC_WORLD_OBJECT, pick_place::State::RETREAT},
         {pick_place::State::RECOVER_DETACH_GAZEBO,
          pick_place::State::RECOVER_DETACH_MOVEIT},
         {pick_place::State::RECOVER_DETACH_MOVEIT,
          pick_place::State::RECOVER_SYNC_WORLD_OBJECT},
         {pick_place::State::RECOVER_SYNC_WORLD_OBJECT,
          pick_place::State::RECOVER_RETREAT},
       }) {
    EXPECT_TRUE(runtime.contracts.hasContract(transition));
  }
  ASSERT_NE(nullptr, runtime.recovery_policy);
}

TEST(SO101Task3Runtime, GazeboAttachRetargetsPositionControllerToMeasuredCarryHold)
{
  auto gripper = std::make_shared<FakeGripper>();
  auto attach = std::make_shared<FakeExecutor>();
  pick_place::SO101Task3RuntimeDependencies deps{
    gripper, std::make_shared<FakeScene>(), attach,
    std::make_shared<FakeExecutor>(), std::make_shared<FakeExecutor>()};
  const auto runtime = pick_place::makeSO101Task3Runtime(deps);
  auto * executor = runtime.actions.findExecutor(pick_place::State::ATTACH_GAZEBO);
  ASSERT_NE(nullptr, executor);
  pick_place::WorldSnapshot before;
  before.joint_positions[pick_place::SO101Profile::canonical().gripper_joint] = 0.791;
  const pick_place::ExecutionContext context{pick_place::State::ATTACH_GAZEBO,
                                             pick_place::State::ATTACH_MOVEIT, before, nullptr};
  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, executor->execute(context).status);
  EXPECT_EQ(1, attach->calls);
  EXPECT_EQ(1, gripper->calls);
  EXPECT_DOUBLE_EQ(0.791, gripper->last_q6);
}

TEST(SO101Task3Runtime, WholeExecuteGraphFailsClosedBeforeObservationWithoutTask4Motion)
{
  const auto runtime = pick_place::makeSO101Task3Runtime(dependencies());
  NeverObserved observer;
  FakeCheckpointStore checkpoint;
  pick_place::CommonResumeValidator resume("config", "session");
  pick_place::PlanValidatorRegistry plan_validators;
  pick_place::StateMachineRunner runner(runtime.actions, runtime.contracts, &observer, &checkpoint,
                                        &resume, &plan_validators,
                                        runtime.recovery_policy.get());

  const auto result = runner.run({pick_place::RunMode::EXECUTE});

  EXPECT_EQ(pick_place::RunStatus::ERROR, result.status);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("EXECUTE_ACTION_NOT_REGISTERED", result.failure->code);
  EXPECT_NE(std::string::npos, result.failure->message.find("MOVE_ABOVE_OBJECT"));
  EXPECT_EQ(0, observer.calls);
}
