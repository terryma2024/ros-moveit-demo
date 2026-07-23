#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <memory>

#include <nlohmann/json.hpp>

#include "panda_gazebo_demo/pick_place/common_resume_validator.hpp"
#include "panda_gazebo_demo/pick_place/file_checkpoint_store.hpp"
#include "panda_gazebo_demo/pick_place/recovery_policy.hpp"
#include "panda_gazebo_demo/pick_place/runner.hpp"

namespace pick_place = panda_gazebo_demo::pick_place;

namespace
{

std::filesystem::path checkpointPath(const std::string & name)
{
  return std::filesystem::temp_directory_path() / ("panda_gazebo_demo_" + name + ".json");
}

pick_place::WorldSnapshot makeSnapshot()
{
  pick_place::WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.arm_stationary = true;
  snapshot.gripper_open = true;
  snapshot.tcp_pose_world = {0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0};
  snapshot.joint_positions = {{"panda_joint1", 0.0}};
  snapshot.moveit_world_object_poses = {{"table", {}}, {"coke", {}}};
  snapshot.moveit_coke_attached = false;
  snapshot.gazebo_coke_pose_world = {0.3, 0.0, 0.836, 0.0, 0.0, 0.0, 1.0};
  snapshot.gazebo_coke_attached = false;
  snapshot.gazebo_coke_stationary = true;
  snapshot.simulation_session_id = "test-session";
  return snapshot;
}

pick_place::Checkpoint makeRecoveryCheckpoint()
{
  const auto snapshot = makeSnapshot();
  pick_place::Checkpoint checkpoint;
  checkpoint.run_id = "test-run";
  checkpoint.sequence = 7;
  checkpoint.phase = pick_place::CheckpointPhase::RECOVERY;
  checkpoint.last_completed_state = pick_place::State::MOVE_ABOVE_PLACE;
  checkpoint.failed_state = pick_place::State::MOVE_ABOVE_PLACE;
  checkpoint.original_failure = pick_place::Failure{pick_place::FailureCategory::EXECUTION,
                                                    "MOVE_FAILED",
                                                    "move failed",
                                                    {{"error", 0.5}}};
  checkpoint.next_state = pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT;
  checkpoint.expected.tcp_pose_world = snapshot.tcp_pose_world;
  checkpoint.expected.gripper_open = snapshot.gripper_open;
  checkpoint.expected.joint_positions = snapshot.joint_positions;
  checkpoint.expected.moveit_world_object_poses = snapshot.moveit_world_object_poses;
  checkpoint.expected.moveit_coke_attached = snapshot.moveit_coke_attached;
  checkpoint.expected.gazebo_coke_pose_world = snapshot.gazebo_coke_pose_world;
  checkpoint.expected.gazebo_coke_attached = snapshot.gazebo_coke_attached;
  checkpoint.expected.gazebo_coke_stationary = snapshot.gazebo_coke_stationary;
  checkpoint.expected.required_world_objects = {"table", "coke"};
  checkpoint.configuration_hash = "test-config";
  checkpoint.simulation_session_id = "test-session";
  return checkpoint;
}

pick_place::Checkpoint makeForwardCheckpoint()
{
  auto checkpoint = makeRecoveryCheckpoint();
  checkpoint.phase = pick_place::CheckpointPhase::FORWARD;
  checkpoint.last_completed_state = pick_place::State::DESCEND;
  checkpoint.failed_state.reset();
  checkpoint.original_failure.reset();
  checkpoint.next_state = pick_place::State::CLOSE_GRIPPER;
  return checkpoint;
}

class FakeObserver final : public pick_place::IWorldObserver
{
public:
  pick_place::ObservationResult observe() override
  {
    ++calls;
    return {snapshot, std::nullopt};
  }

  pick_place::WorldSnapshot snapshot{makeSnapshot()};
  int calls{0};
};

class FakeCheckpointStore final : public pick_place::ICheckpointStore
{
public:
  std::optional<pick_place::Failure> commit(const pick_place::Checkpoint & checkpoint) override
  {
    committed = checkpoint;
    ++commit_calls;
    return std::nullopt;
  }

  pick_place::CheckpointLoadResult loadLatestCompatible() override
  {
    return {loaded, std::nullopt};
  }

  pick_place::Checkpoint loaded{makeRecoveryCheckpoint()};
  std::optional<pick_place::Checkpoint> committed;
  int commit_calls{0};
};

class RecordingRecoveryPolicy final : public pick_place::IRecoveryPolicy
{
public:
  pick_place::RecoveryRoute select(pick_place::State failed_state,
                                   const pick_place::Failure & original_failure,
                                   const pick_place::WorldSnapshot & stopped_world) const override
  {
    ++calls;
    observed_failed_state = failed_state;
    observed_failure_code = original_failure.code;
    observed_gazebo_attached = stopped_world.gazebo_coke_attached;
    return {pick_place::State::RECOVER_OPEN_GRIPPER, std::nullopt};
  }

  mutable int calls{0};
  mutable pick_place::State observed_failed_state{pick_place::State::ERROR};
  mutable std::string observed_failure_code;
  mutable std::optional<bool> observed_gazebo_attached;
};

class FakeExecutor final : public pick_place::IStateExecutor
{
public:
  pick_place::ActionResult execute(const pick_place::ExecutionContext & context) override
  {
    ++calls;
    last_state = context.state;
    return result;
  }

  pick_place::ActionResult cancel() override
  {
    ++cancel_calls;
    return {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  }

  pick_place::ActionResult result{pick_place::ActionStatus::FAILED,
                                  pick_place::Failure{pick_place::FailureCategory::EXECUTION,
                                                      "ACTION_FAILED",
                                                      "action failed",
                                                      {}}};
  pick_place::State last_state{pick_place::State::ERROR};
  int calls{0};
  int cancel_calls{0};
};

}  // namespace

TEST(CheckpointV3, RecoveryJsonRoundTripsPhaseFailureAndNextState)
{
  const auto path = checkpointPath("round_trip");
  std::filesystem::remove(path);
  pick_place::FileCheckpointStore store(path);
  const auto checkpoint = makeRecoveryCheckpoint();

  EXPECT_FALSE(store.commit(checkpoint));
  const auto loaded = store.loadLatestCompatible();

  ASSERT_TRUE(loaded.checkpoint);
  EXPECT_EQ(3U, loaded.checkpoint->schema_version);
  EXPECT_EQ(pick_place::CheckpointPhase::RECOVERY, loaded.checkpoint->phase);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_PLACE, loaded.checkpoint->failed_state);
  ASSERT_TRUE(loaded.checkpoint->original_failure);
  EXPECT_EQ(pick_place::FailureCategory::EXECUTION, loaded.checkpoint->original_failure->category);
  EXPECT_EQ("MOVE_FAILED", loaded.checkpoint->original_failure->code);
  EXPECT_EQ("move failed", loaded.checkpoint->original_failure->message);
  EXPECT_DOUBLE_EQ(0.5, loaded.checkpoint->original_failure->metrics.at("error"));
  EXPECT_EQ(pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT, loaded.checkpoint->next_state);
  std::filesystem::remove(path);
}

TEST(CheckpointV3, RejectsSchemaV2AsIncompatible)
{
  const auto path = checkpointPath("v2");
  std::ofstream output(path, std::ios::out | std::ios::trunc);
  output << nlohmann::json{{"schema_version", 2}};
  output.close();
  pick_place::FileCheckpointStore store(path);

  const auto loaded = store.loadLatestCompatible();

  EXPECT_FALSE(loaded.checkpoint);
  ASSERT_TRUE(loaded.failure);
  EXPECT_EQ("CHECKPOINT_INCOMPATIBLE", loaded.failure->code);
  std::filesystem::remove(path);
}

TEST(CheckpointV3, ForwardJsonRoundTripsWithoutRecoveryContext)
{
  const auto path = checkpointPath("forward_round_trip");
  std::filesystem::remove(path);
  pick_place::FileCheckpointStore store(path);
  const auto checkpoint = makeForwardCheckpoint();

  EXPECT_FALSE(store.commit(checkpoint));
  const auto loaded = store.loadLatestCompatible();

  ASSERT_TRUE(loaded.checkpoint);
  EXPECT_EQ(pick_place::CheckpointPhase::FORWARD, loaded.checkpoint->phase);
  EXPECT_FALSE(loaded.checkpoint->failed_state);
  EXPECT_FALSE(loaded.checkpoint->original_failure);
  EXPECT_EQ(pick_place::State::CLOSE_GRIPPER, loaded.checkpoint->next_state);
  std::filesystem::remove(path);
}

TEST(Runner, RecoveryResumeReclassifiesCurrentFacts)
{
  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  FakeObserver observer;
  observer.snapshot.joint_positions.at("panda_joint1") = 0.5;
  FakeCheckpointStore checkpoints;
  checkpoints.loaded.next_state = pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT;
  const pick_place::CommonResumeValidator common_resume_validator("test-config", "test-session");
  const RecordingRecoveryPolicy recovery_policy;
  const pick_place::StateMachineRunner runner(actions, contracts, &observer, &checkpoints,
                                              &common_resume_validator, nullptr, nullptr,
                                              &recovery_policy);

  const auto result =
    runner.run({pick_place::RunMode::EXECUTE, std::nullopt, true, std::nullopt, 100});

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("EXECUTE_ACTION_NOT_REGISTERED", result.failure->code);
  EXPECT_NE(std::string::npos, result.failure->message.find("RECOVER_OPEN_GRIPPER"));
  EXPECT_EQ(1, recovery_policy.calls);
  EXPECT_EQ(pick_place::State::MOVE_ABOVE_PLACE, recovery_policy.observed_failed_state);
  EXPECT_EQ("MOVE_FAILED", recovery_policy.observed_failure_code);
  ASSERT_TRUE(recovery_policy.observed_gazebo_attached);
  EXPECT_FALSE(*recovery_policy.observed_gazebo_attached);
}

TEST(Runner, ForwardActionFailureCommitsRecoveryCheckpointBeforeRecoverySideEffect)
{
  pick_place::StateActionRegistry actions;
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerExecutor(pick_place::State::CLOSE_GRIPPER, executor);
  pick_place::TransitionContractRegistry contracts;
  contracts.registerContract({pick_place::State::DESCEND, pick_place::State::CLOSE_GRIPPER},
                             std::make_shared<pick_place::AlwaysPassValidator>());
  contracts.registerContract({pick_place::State::CLOSE_GRIPPER, pick_place::State::ATTACH_GAZEBO},
                             std::make_shared<pick_place::AlwaysPassValidator>());
  FakeObserver observer;
  FakeCheckpointStore checkpoints;
  checkpoints.loaded = makeForwardCheckpoint();
  const pick_place::CommonResumeValidator common_resume_validator("test-config", "test-session");
  const RecordingRecoveryPolicy recovery_policy;
  const pick_place::StateMachineRunner runner(actions, contracts, &observer, &checkpoints,
                                              &common_resume_validator, nullptr, nullptr,
                                              &recovery_policy);

  const auto result =
    runner.run({pick_place::RunMode::EXECUTE, std::nullopt, true, std::nullopt, 100});

  ASSERT_TRUE(result.failure);
  EXPECT_EQ(1, executor->calls);
  EXPECT_EQ(1, executor->cancel_calls);
  EXPECT_EQ(1, recovery_policy.calls);
  EXPECT_EQ(1, checkpoints.commit_calls);
  ASSERT_TRUE(checkpoints.committed);
  EXPECT_EQ(pick_place::CheckpointPhase::RECOVERY, checkpoints.committed->phase);
  EXPECT_EQ(pick_place::State::CLOSE_GRIPPER, checkpoints.committed->failed_state);
  ASSERT_TRUE(checkpoints.committed->original_failure);
  EXPECT_EQ("ACTION_FAILED", checkpoints.committed->original_failure->code);
  EXPECT_EQ(pick_place::State::RECOVER_OPEN_GRIPPER, checkpoints.committed->next_state);
}

TEST(Runner, RecoveryActionFailureTerminatesWithoutSelectingAnotherRoute)
{
  pick_place::StateActionRegistry actions;
  auto executor = std::make_shared<FakeExecutor>();
  actions.registerExecutor(pick_place::State::RECOVER_OPEN_GRIPPER, executor);
  pick_place::TransitionContractRegistry contracts;
  contracts.registerContract(
    {pick_place::State::RECOVER_OPEN_GRIPPER, pick_place::State::RECOVER_DETACH_GAZEBO},
    std::make_shared<pick_place::AlwaysPassValidator>());
  FakeObserver observer;
  FakeCheckpointStore checkpoints;
  const pick_place::CommonResumeValidator common_resume_validator("test-config", "test-session");
  const RecordingRecoveryPolicy recovery_policy;
  const pick_place::StateMachineRunner runner(actions, contracts, &observer, &checkpoints,
                                              &common_resume_validator, nullptr, nullptr,
                                              &recovery_policy);

  const auto result =
    runner.run({pick_place::RunMode::EXECUTE, std::nullopt, true, std::nullopt, 100});

  ASSERT_TRUE(result.failure);
  EXPECT_EQ("ACTION_FAILED", result.failure->code);
  EXPECT_EQ(1, executor->calls);
  EXPECT_EQ(1, executor->cancel_calls);
  EXPECT_EQ(1, recovery_policy.calls);
  EXPECT_EQ(0, checkpoints.commit_calls);
}
