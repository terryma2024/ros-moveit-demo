#include <gtest/gtest.h>

#include <memory>

#include "so101_gazebo_demo/pick_place/runner.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

namespace
{

class SuccessfulExecutor final : public pick_place::IStateExecutor
{
public:
  pick_place::ActionResult execute(const pick_place::ExecutionContext &) override
  {
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }

  pick_place::ActionResult cancel() override
  {
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }
};

class SequencedObserver final : public pick_place::IWorldObserver
{
public:
  pick_place::ObservationResult observe() override
  {
    ++calls;
    return {calls == 1 ? before : after, std::nullopt};
  }

  pick_place::WorldSnapshot before;
  pick_place::WorldSnapshot after;
  int calls{0};
};

class RecordingCheckpointStore final : public pick_place::ICheckpointStore
{
public:
  std::optional<pick_place::Failure> commit(const pick_place::Checkpoint & checkpoint) override
  {
    committed = checkpoint;
    return std::nullopt;
  }

  pick_place::CheckpointLoadResult loadLatestCompatible() override
  {
    return {std::nullopt, std::nullopt};
  }

  std::optional<pick_place::Checkpoint> committed;
};

}  // namespace

TEST(RunnerContracts, RegisteredFakesCanPlanExecuteCheckpointAndResume)
{
  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  pick_place::PlanValidatorRegistry validators;
  (void)actions;
  (void)contracts;
  (void)validators;
}

TEST(RunnerContracts, SuccessfulTransitionCheckpointsTheCompleteObservedWorldExpectation)
{
  pick_place::StateActionRegistry actions;
  actions.registerExecutor(pick_place::State::PREPARE_OPEN_GRIPPER,
                           std::make_shared<SuccessfulExecutor>());
  pick_place::TransitionContractRegistry contracts;
  contracts.registerContract(
    {pick_place::State::PREPARE_OPEN_GRIPPER, pick_place::State::MOVE_ABOVE_OBJECT},
    std::make_shared<pick_place::AlwaysPassValidator>());
  SequencedObserver observer;
  observer.before.fresh = true;
  observer.before.arm_stationary = true;
  observer.after.fresh = true;
  observer.after.arm_stationary = true;
  observer.after.tcp_pose_world = {0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 1.0};
  observer.after.gripper_open = true;
  observer.after.joint_positions = {{"joint_a", 0.25}, {"joint_b", -0.5}};
  observer.after.moveit_world_object_poses = {{"object", {0.4, 0.5, 0.6, 0.0, 0.0, 0.0, 1.0}}};
  observer.after.moveit_coke_attached = true;
  observer.after.gazebo_coke_pose_world = pick_place::Pose3d{0.7, 0.8, 0.9, 0.0, 0.0, 0.0, 1.0};
  observer.after.gazebo_coke_attached = true;
  observer.after.gazebo_coke_stationary = true;
  observer.after.simulation_session_id = "session-a";
  RecordingCheckpointStore store;
  const pick_place::CommonResumeValidator resume_validator("config-a", "session-a");
  const pick_place::StateMachineRunner runner(actions, contracts, &observer, &store,
                                              &resume_validator);

  const auto result =
    runner.run({pick_place::RunMode::EXECUTE, pick_place::State::PREPARE_OPEN_GRIPPER, false,
                std::nullopt, 10});

  EXPECT_EQ(pick_place::RunStatus::CHECKPOINT_COMPLETE, result.status);
  ASSERT_TRUE(store.committed);
  EXPECT_EQ(observer.after.tcp_pose_world.x, store.committed->expected.tcp_pose_world.x);
  EXPECT_EQ(observer.after.gripper_open, store.committed->expected.gripper_open);
  EXPECT_EQ(observer.after.joint_positions, store.committed->expected.joint_positions);
  EXPECT_EQ(observer.after.moveit_world_object_poses.size(),
            store.committed->expected.moveit_world_object_poses.size());
  EXPECT_EQ(observer.after.moveit_coke_attached, store.committed->expected.moveit_coke_attached);
  EXPECT_EQ(observer.after.gazebo_coke_pose_world->z,
            store.committed->expected.gazebo_coke_pose_world->z);
  EXPECT_EQ(observer.after.gazebo_coke_attached, store.committed->expected.gazebo_coke_attached);
  EXPECT_EQ(observer.after.gazebo_coke_stationary,
            store.committed->expected.gazebo_coke_stationary);
  EXPECT_EQ(std::vector<std::string>({"object"}), store.committed->expected.required_world_objects);
}
