#include <gtest/gtest.h>

#include <algorithm>
#include <array>
#include <functional>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include "panda_gazebo_demo/pick_place/gazebo_attachment_executor.hpp"
#include "panda_gazebo_demo/pick_place/gripper_state_executor.hpp"
#include "panda_gazebo_demo/pick_place/motion_plan_evidence.hpp"
#include "panda_gazebo_demo/pick_place/motion_state_action.hpp"
#include "panda_gazebo_demo/pick_place/moveit_scene_executor.hpp"
#include "panda_gazebo_demo/pick_place/recovery_contracts.hpp"
#include "panda_gazebo_demo/pick_place/runner.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

constexpr Pose3d kAbovePick{0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d kPick{0.3, 0.0, 0.87, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d kAbovePlace{0.3, 0.2, 0.987, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d kPlace{0.3, 0.2, 0.87, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d kCokePick{0.3, 0.0, 0.836, 0.0, 0.0, 0.0, 1.0};
constexpr Pose3d kCokeAbovePick{0.3, 0.0, 0.953, 0.0, 0.0, 0.0, 1.0};
constexpr Pose3d kCokeAbovePlace{0.3, 0.2, 0.953, 0.0, 0.0, 0.0, 1.0};
constexpr Pose3d kCokePlace{0.3, 0.2, 0.836, 0.0, 0.0, 0.0, 1.0};
const std::set<std::string> kTouchLinks{"panda_hand", "panda_leftfinger", "panda_rightfinger"};

WorldSnapshot detachedSnapshot(const Pose3d & tcp = kPick, const Pose3d & coke = kCokePick,
                               bool synchronized = true)
{
  WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.arm_stationary = true;
  snapshot.gripper_open = true;
  snapshot.tcp_pose_world = tcp;
  snapshot.joint_positions = {{"panda_joint1", 0.0},
                              {"panda_finger_joint1", 0.04},
                              {"panda_finger_joint2", 0.04}};
  snapshot.joint_velocities = {{"panda_joint1", 0.0},
                               {"panda_finger_joint1", 0.0},
                               {"panda_finger_joint2", 0.0}};
  snapshot.gazebo_task_object_pose_world = coke;
  snapshot.gazebo_task_object_attached = false;
  snapshot.gazebo_task_object_stationary = true;
  snapshot.moveit_task_object_attached = false;
  auto moveit_coke = coke;
  if (!synchronized) {
    moveit_coke.x += 0.02;
  }
  snapshot.moveit_world_object_poses = {{"table", Pose3d{}}, {"coke", moveit_coke}};
  snapshot.simulation_session_id = "recovery-test-session";
  return snapshot;
}

WorldSnapshot carryingSnapshot(const Pose3d & tcp, const Pose3d & coke)
{
  auto snapshot = detachedSnapshot(tcp, coke);
  snapshot.gripper_open = false;
  snapshot.joint_positions["panda_finger_joint1"] = 0.032;
  snapshot.joint_positions["panda_finger_joint2"] = 0.032;
  snapshot.gazebo_task_object_attached = true;
  snapshot.moveit_task_object_attached = true;
  snapshot.moveit_world_object_poses.erase("coke");
  snapshot.moveit_task_object_attached_link = "panda_hand";
  snapshot.moveit_task_object_touch_links = kTouchLinks;
  return snapshot;
}

void openGripper(WorldSnapshot & snapshot)
{
  snapshot.gripper_open = true;
  snapshot.joint_positions["panda_finger_joint1"] = 0.04;
  snapshot.joint_positions["panda_finger_joint2"] = 0.04;
  snapshot.joint_velocities["panda_finger_joint1"] = 0.0;
  snapshot.joint_velocities["panda_finger_joint2"] = 0.0;
}

void applySuccessfulRecoveryState(State state, WorldSnapshot & snapshot)
{
  switch (state) {
    case State::RECOVER_LIFT_TO_SAFE_HEIGHT:
      snapshot.tcp_pose_world = kAbovePlace;
      snapshot.gazebo_task_object_pose_world = kCokeAbovePlace;
      break;
    case State::RECOVER_MOVE_ABOVE_PICK:
      snapshot.tcp_pose_world = kAbovePick;
      snapshot.gazebo_task_object_pose_world = kCokeAbovePick;
      break;
    case State::RECOVER_DESCEND_TO_PICK:
      snapshot.tcp_pose_world = kPick;
      snapshot.gazebo_task_object_pose_world = kCokePick;
      break;
    case State::RECOVER_OPEN_GRIPPER:
      openGripper(snapshot);
      break;
    case State::RECOVER_DETACH_GAZEBO:
      snapshot.gazebo_task_object_attached = false;
      break;
    case State::RECOVER_DETACH_MOVEIT:
      snapshot.moveit_task_object_attached = false;
      snapshot.moveit_task_object_attached_link.reset();
      snapshot.moveit_task_object_touch_links.clear();
      snapshot.moveit_world_object_poses["coke"] =
        Pose3d{kCokePick.x + 0.02, kCokePick.y,  kCokePick.z, kCokePick.qx,
               kCokePick.qy,       kCokePick.qz, kCokePick.qw};
      break;
    case State::RECOVER_SYNC_WORLD_OBJECT:
      snapshot.moveit_world_object_poses["coke"] = *snapshot.gazebo_task_object_pose_world;
      break;
    case State::RECOVER_RETREAT:
      snapshot.tcp_pose_world.z = kAbovePick.z;
      snapshot.gripper_open = false;
      snapshot.joint_positions["panda_joint1"] = 0.0;
      snapshot.joint_positions["panda_finger_joint1"] = 0.0;
      snapshot.joint_positions["panda_finger_joint2"] = 0.0;
      break;
    default:
      break;
  }
}

class MutableObserver final : public IWorldObserver
{
public:
  ObservationResult observe() override
  {
    ++calls;
    snapshot.fresh = true;
    snapshot.arm_stationary = true;
    if (stationary_after_call > 0) {
      snapshot.gazebo_task_object_stationary = calls >= stationary_after_call;
    }
    return {snapshot, std::nullopt};
  }

  WorldSnapshot snapshot;
  int calls{0};
  int stationary_after_call{0};
};

void setExpected(Checkpoint & checkpoint, const WorldSnapshot & snapshot)
{
  checkpoint.expected.tcp_pose_world = snapshot.tcp_pose_world;
  checkpoint.expected.gripper_open = snapshot.gripper_open;
  checkpoint.expected.joint_positions = snapshot.joint_positions;
  checkpoint.expected.moveit_world_object_poses = snapshot.moveit_world_object_poses;
  checkpoint.expected.moveit_task_object_attached = snapshot.moveit_task_object_attached;
  checkpoint.expected.gazebo_task_object_pose_world = snapshot.gazebo_task_object_pose_world;
  checkpoint.expected.gazebo_task_object_attached = snapshot.gazebo_task_object_attached;
  checkpoint.expected.gazebo_task_object_stationary = snapshot.gazebo_task_object_stationary;
  checkpoint.expected.required_world_objects = {"table", "coke"};
}

Checkpoint recoveryCheckpoint(const WorldSnapshot & snapshot)
{
  Checkpoint checkpoint;
  checkpoint.run_id = "recovery-test";
  checkpoint.sequence = 10;
  checkpoint.phase = CheckpointPhase::RECOVERY;
  checkpoint.last_completed_state = State::MOVE_ABOVE_PLACE;
  checkpoint.failed_state = State::MOVE_ABOVE_PLACE;
  checkpoint.original_failure = Failure{FailureCategory::EXECUTION,
                                        "FORWARD_FAILED",
                                        "forward motion failed",
                                        {{"forward_metric", 0.25}}};
  checkpoint.next_state = State::RECOVER_LIFT_TO_SAFE_HEIGHT;
  checkpoint.configuration_fingerprint = "recovery-test-config";
  checkpoint.simulation_session_id = "recovery-test-session";
  setExpected(checkpoint, snapshot);
  return checkpoint;
}

class MemoryCheckpointStore final : public ICheckpointStore
{
public:
  std::optional<Failure> commit(const Checkpoint & checkpoint) override
  {
    ++commit_attempts;
    if (failing_commit_attempts.count(commit_attempts) != 0) {
      return Failure{FailureCategory::CHECKPOINT,
                     "CHECKPOINT_WRITE_FAILED",
                     "configured checkpoint write failure",
                     {}};
    }
    committed.push_back(checkpoint);
    loaded = checkpoint;
    return std::nullopt;
  }

  CheckpointLoadResult loadLatestCompatible() override
  {
    return {loaded, std::nullopt};
  }

  Checkpoint loaded;
  std::vector<Checkpoint> committed;
  std::set<int> failing_commit_attempts;
  int commit_attempts{0};
};

Checkpoint forwardCarryingCheckpoint(const WorldSnapshot & snapshot)
{
  Checkpoint checkpoint;
  checkpoint.run_id = "forward-failure-test";
  checkpoint.sequence = 7;
  checkpoint.phase = CheckpointPhase::FORWARD;
  checkpoint.last_completed_state = State::LIFT;
  checkpoint.next_state = State::MOVE_ABOVE_PLACE;
  checkpoint.configuration_fingerprint = "recovery-test-config";
  checkpoint.simulation_session_id = "recovery-test-session";
  setExpected(checkpoint, snapshot);
  return checkpoint;
}

class ConfigurableForwardContract final : public TransitionContractRegistry::ITransitionContract
{
public:
  [[nodiscard]] ValidationResult validatePrecondition(const WorldSnapshot &) const override
  {
    return precondition;
  }

  [[nodiscard]] ValidationResult validate(const WorldSnapshot &, const WorldSnapshot &,
                                          const ActionResult &) const override
  {
    return {true, {}, {}};
  }

  ValidationResult precondition{true, {}, {}};
};

class ConfigurableForwardAction final : public IStatePlanner, public IStateExecutor
{
public:
  PlanResult plan(State, State, const ObservationResult &) override
  {
    ++plan_calls;
    if (plan_failure) {
      return {{ActionStatus::FAILED, plan_failure}, nullptr};
    }
    auto artifact = std::make_shared<PlanArtifact>();
    artifact->trajectory_points = 1;
    return {{ActionStatus::SUCCEEDED, std::nullopt}, artifact};
  }

  ActionResult execute(const ExecutionContext &) override
  {
    ++execute_calls;
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  ActionResult cancel() override
  {
    ++cancel_calls;
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  std::optional<Failure> plan_failure;
  int plan_calls{0};
  int execute_calls{0};
  int cancel_calls{0};
};

class ConfigurableForwardPlanValidator final : public IPlanValidator
{
public:
  [[nodiscard]] ValidationResult validate(State, const WorldSnapshot &,
                                          const PlanArtifact &) const override
  {
    return validation;
  }

  ValidationResult validation{true, {}, {}};
};

class RecordingRecoveryAction final : public IStatePlanner, public IStateExecutor
{
public:
  RecordingRecoveryAction(State state, State next_state,
                          std::optional<MotionStateConfig> motion_config,
                          MutableObserver * observer, std::vector<State> * execution_order,
                          std::vector<State> * planning_order, std::optional<State> fail_state) :
      state_(state), next_state_(next_state), motion_config_(motion_config), observer_(observer),
      execution_order_(execution_order), planning_order_(planning_order), fail_state_(fail_state)
  {
  }

  PlanResult plan(State current_state, State next_state,
                  const ObservationResult & observation) override
  {
    planning_order_->push_back(state_);
    if (!motion_config_ || current_state != state_ || next_state != next_state_ ||
        !observation.snapshot) {
      return {{ActionStatus::FAILED, Failure{FailureCategory::PLANNING,
                                             "TEST_PLANNER_MISUSE",
                                             "test planner received an invalid request",
                                             {}}},
              nullptr};
    }
    auto evidence = std::make_shared<MotionPlanEvidence>();
    evidence->state = state_;
    evidence->next_state = next_state_;
    evidence->kind = motion_config_->kind;
    evidence->carrying = motion_config_->carrying;
    evidence->cartesian_fraction = 1.0;
    evidence->duration_seconds = 1.0;
    evidence->max_joint_jump = 0.01;
    evidence->planned_start_joint_positions = observation.snapshot->joint_positions;
    evidence->start_tcp_pose = observation.snapshot->tcp_pose_world;
    auto after = *observation.snapshot;
    applySuccessfulRecoveryState(state_, after);
    evidence->end_tcp_pose = after.tcp_pose_world;
    evidence->tcp_path = {after.tcp_pose_world};
    evidence->trajectory_points = 1;
    evidence->collision_aware = true;
    evidence->attached_object_in_model = motion_config_->carrying;
    evidence->carried_relative_pose_available = motion_config_->carrying;
    evidence->carried_clearance_verified = motion_config_->carrying;
    return {{ActionStatus::SUCCEEDED, std::nullopt}, evidence};
  }

  ActionResult execute(const ExecutionContext & context) override
  {
    execution_order_->push_back(state_);
    if (context.state != state_ || context.next_state != next_state_) {
      return {ActionStatus::FAILED, Failure{FailureCategory::EXECUTION,
                                            "TEST_EXECUTOR_MISUSE",
                                            "test executor received an invalid transition",
                                            {}}};
    }
    if (fail_state_ == state_) {
      return {ActionStatus::FAILED,
              Failure{FailureCategory::EXECUTION,
                      std::string("RECOVERY_FAILED_") + toString(state_),
                      std::string("recovery action failed at ") + toString(state_),
                      {{"recovery_metric", 0.5}}}};
    }
    applySuccessfulRecoveryState(state_, observer_->snapshot);
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  ActionResult cancel() override
  {
    ++cancel_calls;
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  int cancel_calls{0};

private:
  State state_;
  State next_state_;
  std::optional<MotionStateConfig> motion_config_;
  MutableObserver * observer_;
  std::vector<State> * execution_order_;
  std::vector<State> * planning_order_;
  std::optional<State> fail_state_;
};

const std::array<MotionStateConfig, 4> kRecoveryMotionConfigs{{
  {State::RECOVER_LIFT_TO_SAFE_HEIGHT, State::RECOVER_MOVE_ABOVE_PICK, MotionKind::CARTESIAN_UP,
   true},
  {State::RECOVER_MOVE_ABOVE_PICK, State::RECOVER_DESCEND_TO_PICK, MotionKind::POSE, true},
  {State::RECOVER_DESCEND_TO_PICK, State::RECOVER_OPEN_GRIPPER, MotionKind::CARTESIAN_DOWN, true},
  {State::RECOVER_RETREAT, State::ERROR, MotionKind::CARTESIAN_UP, false},
}};

const std::array<std::pair<State, State>, 4> kRecoveryNonMotionTransitions{{
  {State::RECOVER_OPEN_GRIPPER, State::RECOVER_DETACH_GAZEBO},
  {State::RECOVER_DETACH_GAZEBO, State::RECOVER_DETACH_MOVEIT},
  {State::RECOVER_DETACH_MOVEIT, State::RECOVER_SYNC_WORLD_OBJECT},
  {State::RECOVER_SYNC_WORLD_OBJECT, State::RECOVER_RETREAT},
}};

class WorkflowHarness
{
public:
  explicit WorkflowHarness(WorldSnapshot initial_snapshot,
                           std::optional<State> fail_state = std::nullopt) :
      target_policy(std::make_shared<FixedPickPlaceTargetPolicy>()),
      recovery_policy(target_policy, 0.005),
      common_resume("recovery-test-config", "recovery-test-session")
  {
    observer.snapshot = std::move(initial_snapshot);
    checkpoints.loaded = recoveryCheckpoint(observer.snapshot);
    PickPlaceContractConfig contract_config;
    contract_config.ready_joint_positions = {{"panda_joint1", 0.0}};
    contract_config.gripper_close_position = 0.0;
    contract_config.gripper_close_tolerance = 0.004;
    registerRecoveryContracts(contracts, target_policy, contract_config);
    for (const auto & config : kRecoveryMotionConfigs) {
      auto action = std::make_shared<RecordingRecoveryAction>(config.state, config.next_state,
                                                              config, &observer, &execution_order,
                                                              &planning_order, fail_state);
      actions.registerPlanner(config.state, action);
      actions.registerExecutor(config.state, action);
      plan_validators.registerValidator(
        config.state, std::make_shared<MotionPlanValidator>(config, target_policy));
    }
    for (const auto & [state, next_state] : kRecoveryNonMotionTransitions) {
      actions.registerExecutor(state, std::make_shared<RecordingRecoveryAction>(
                                        state, next_state, std::nullopt, &observer,
                                        &execution_order, &planning_order, fail_state));
    }
  }

  RunResult run()
  {
    const StateMachineRunner runner(actions, contracts, &observer, &checkpoints, &common_resume,
                                    nullptr, &plan_validators, &recovery_policy);
    return runner.run({RunMode::EXECUTE, std::nullopt, true, std::nullopt, 100});
  }

  std::shared_ptr<const PickPlaceTargetPolicy> target_policy;
  FixedRecoveryPolicy recovery_policy;
  CommonResumeValidator common_resume;
  MutableObserver observer;
  MemoryCheckpointStore checkpoints;
  StateActionRegistry actions;
  TransitionContractRegistry contracts;
  PlanValidatorRegistry plan_validators;
  std::vector<State> execution_order;
  std::vector<State> planning_order;
};

enum class ForwardFailureStage
{
  PRECONDITION,
  PLANNER,
  PLAN_VALIDATOR,
  CHECKPOINT,
};

class ForwardFailureHarness
{
public:
  explicit ForwardFailureHarness(ForwardFailureStage stage) :
      workflow(carryingSnapshot(kAbovePlace, kCokeAbovePlace)),
      action(std::make_shared<ConfigurableForwardAction>()),
      contract(std::make_shared<ConfigurableForwardContract>()),
      validator(std::make_shared<ConfigurableForwardPlanValidator>())
  {
    workflow.checkpoints.loaded = forwardCarryingCheckpoint(workflow.observer.snapshot);
    workflow.contracts.registerContract({State::LIFT, State::MOVE_ABOVE_PLACE},
                                        std::make_shared<AlwaysPassValidator>());
    workflow.contracts.registerContract({State::MOVE_ABOVE_PLACE, State::DESCEND_TO_PLACE},
                                        contract);
    workflow.actions.registerPlanner(State::MOVE_ABOVE_PLACE, action);
    workflow.actions.registerExecutor(State::MOVE_ABOVE_PLACE, action);
    workflow.plan_validators.registerValidator(State::MOVE_ABOVE_PLACE, validator);

    const Failure failure{FailureCategory::PRECONDITION,
                          "FORWARD_PRECONDITION_FAILED",
                          "configured precondition failure",
                          {}};
    if (stage == ForwardFailureStage::PRECONDITION) {
      contract->precondition = {false, {failure}, {}};
    } else if (stage == ForwardFailureStage::PLANNER) {
      action->plan_failure =
        Failure{FailureCategory::PLANNING, "FORWARD_PLAN_FAILED", "configured planner failure", {}};
    } else if (stage == ForwardFailureStage::PLAN_VALIDATOR) {
      validator->validation = {false,
                               {Failure{FailureCategory::PLAN_VALIDATION,
                                        "FORWARD_PLAN_INVALID",
                                        "configured plan-validation failure",
                                        {}}},
                               {}};
    } else {
      workflow.checkpoints.failing_commit_attempts = {1, 2};
    }
  }

  RunResult run()
  {
    return workflow.run();
  }

  WorkflowHarness workflow;
  std::shared_ptr<ConfigurableForwardAction> action;
  std::shared_ptr<ConfigurableForwardContract> contract;
  std::shared_ptr<ConfigurableForwardPlanValidator> validator;
};

std::vector<State> fullRecoveryOrder()
{
  return {State::RECOVER_LIFT_TO_SAFE_HEIGHT, State::RECOVER_MOVE_ABOVE_PICK,
          State::RECOVER_DESCEND_TO_PICK,     State::RECOVER_OPEN_GRIPPER,
          State::RECOVER_DETACH_GAZEBO,       State::RECOVER_DETACH_MOVEIT,
          State::RECOVER_SYNC_WORLD_OBJECT,   State::RECOVER_RETREAT};
}

std::vector<State> recoveryOrderFromSafeHeight()
{
  auto order = fullRecoveryOrder();
  order.erase(order.begin());
  return order;
}

class FakeGripperAdapter final : public IGripperCommandAdapter
{
public:
  ActionResult command(double, double) override
  {
    ++command_calls;
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
  ActionResult cancelAndWait() override
  {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
  int command_calls{0};
};

class FakeSceneAdapter final : public IMoveItSceneAdapter
{
public:
  ActionResult attachCoke(const std::string &, const std::vector<std::string> &) override
  {
    return {ActionStatus::NOT_SUPPORTED, std::nullopt};
  }
  ActionResult detachCoke() override
  {
    ++detach_calls;
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
  ActionResult syncCokeWorldPose(const Pose3d & pose) override
  {
    ++sync_calls;
    synchronized_pose = pose;
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
  ActionResult upsertCokeWorldPose(const Pose3d & pose) override
  {
    return syncCokeWorldPose(pose);
  }
  ActionResult upsertTableWorldPose(const Pose3d &) override
  {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
  std::optional<MoveItSceneState> observe() override
  {
    return MoveItSceneState{true, false, "", {}, synchronized_pose, false, std::nullopt};
  }

  int detach_calls{0};
  int sync_calls{0};
  std::optional<Pose3d> synchronized_pose;
};

class FakeMotionAdapter final : public IMoveItMotionAdapter
{
public:
  PlanResult plan(const MotionPlanningRequest &, const ObservationResult &) override
  {
    ++plan_calls;
    return {{ActionStatus::FAILED, Failure{FailureCategory::PLANNING,
                                           "FAKE_PLAN_CALLED",
                                           "fake adapter planning was called",
                                           {}}},
            nullptr};
  }

  ActionResult execute(const MotionPlanEvidence &) override
  {
    ++execute_calls;
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  ActionResult cancel() override
  {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  int plan_calls{0};
  int execute_calls{0};
};

TEST(RecoveryWorkflow, CarryFailureReturnsToPickBeforeOpening)
{
  WorkflowHarness harness(carryingSnapshot(kAbovePlace, kCokeAbovePlace));

  const auto result = harness.run();

  EXPECT_EQ(result.status, RunStatus::ERROR);
  EXPECT_EQ(harness.execution_order, recoveryOrderFromSafeHeight());
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "FORWARD_FAILED");
}

TEST(RecoveryWorkflow, CarryingPreconditionFailureRunsTheExactRecoveryWorkflow)
{
  ForwardFailureHarness harness(ForwardFailureStage::PRECONDITION);

  const auto result = harness.run();

  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "FORWARD_PRECONDITION_FAILED");
  EXPECT_EQ(harness.action->cancel_calls, 1);
  EXPECT_EQ(harness.action->plan_calls, 0);
  EXPECT_EQ(harness.action->execute_calls, 0);
  EXPECT_EQ(harness.workflow.execution_order, recoveryOrderFromSafeHeight());
  ASSERT_FALSE(harness.workflow.checkpoints.committed.empty());
  EXPECT_EQ(harness.workflow.checkpoints.committed.front().phase, CheckpointPhase::RECOVERY);
  EXPECT_EQ(harness.workflow.checkpoints.committed.front().next_state,
            State::RECOVER_MOVE_ABOVE_PICK);
}

TEST(RecoveryWorkflow, CarryingPlannerFailureRunsTheExactRecoveryWorkflow)
{
  ForwardFailureHarness harness(ForwardFailureStage::PLANNER);

  const auto result = harness.run();

  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "FORWARD_PLAN_FAILED");
  EXPECT_EQ(harness.action->cancel_calls, 1);
  EXPECT_EQ(harness.action->plan_calls, 1);
  EXPECT_EQ(harness.action->execute_calls, 0);
  EXPECT_EQ(harness.workflow.execution_order, recoveryOrderFromSafeHeight());
}

TEST(RecoveryWorkflow, CarryingPlanValidatorFailureRunsTheExactRecoveryWorkflow)
{
  ForwardFailureHarness harness(ForwardFailureStage::PLAN_VALIDATOR);

  const auto result = harness.run();

  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "FORWARD_PLAN_INVALID");
  EXPECT_EQ(harness.action->cancel_calls, 1);
  EXPECT_EQ(harness.action->plan_calls, 1);
  EXPECT_EQ(harness.action->execute_calls, 0);
  EXPECT_EQ(harness.workflow.execution_order, recoveryOrderFromSafeHeight());
}

TEST(RecoveryWorkflow, CheckpointFailuresStillRunEmergencyRecoveryInProcess)
{
  ForwardFailureHarness harness(ForwardFailureStage::CHECKPOINT);

  const auto result = harness.run();

  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "CHECKPOINT_WRITE_FAILED");
  EXPECT_EQ(result.failure->metrics.at("recovery_checkpoint_persisted"), 0.0);
  EXPECT_EQ(harness.action->cancel_calls, 1);
  EXPECT_EQ(harness.action->execute_calls, 1);
  EXPECT_EQ(harness.workflow.execution_order, recoveryOrderFromSafeHeight());
  EXPECT_EQ(harness.workflow.checkpoints.commit_attempts, 9);
  EXPECT_EQ(harness.workflow.checkpoints.committed.size(), 7U);
}

TEST(RecoveryWorkflow, CarryFailureAtPlaceSurfaceOpensBeforeCleanup)
{
  WorkflowHarness harness(carryingSnapshot(kPlace, kCokePlace));

  const auto result = harness.run();

  EXPECT_EQ(result.status, RunStatus::ERROR);
  EXPECT_EQ(harness.execution_order,
            (std::vector<State>{State::RECOVER_OPEN_GRIPPER, State::RECOVER_DETACH_GAZEBO,
                                State::RECOVER_DETACH_MOVEIT, State::RECOVER_SYNC_WORLD_OBJECT,
                                State::RECOVER_RETREAT}));
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "FORWARD_FAILED");
}

TEST(RecoveryWorkflow, GazeboOnlyAttachNeverPlansCarryingMotion)
{
  auto snapshot = detachedSnapshot(kPick, kCokePick);
  snapshot.gripper_open = false;
  snapshot.joint_positions["panda_finger_joint1"] = 0.032;
  snapshot.joint_positions["panda_finger_joint2"] = 0.032;
  snapshot.gazebo_task_object_attached = true;
  WorkflowHarness harness(snapshot);

  const auto result = harness.run();

  EXPECT_EQ(result.status, RunStatus::ERROR);
  EXPECT_EQ(harness.planning_order, (std::vector<State>{State::RECOVER_RETREAT}));
  ASSERT_FALSE(harness.execution_order.empty());
  EXPECT_EQ(harness.execution_order.front(), State::RECOVER_OPEN_GRIPPER);
}

TEST(RecoveryWorkflow, AlreadyDetachedCleanupNoOpsAndSynchronizes)
{
  auto snapshot = detachedSnapshot(kPick, kCokePick, false);
  const auto gripper_adapter = std::make_shared<FakeGripperAdapter>();
  GripperStateExecutor open_executor(gripper_adapter,
                                     {State::RECOVER_OPEN_GRIPPER, 0.04, 20.0, true});
  GazeboAttachmentExecutor gazebo_detach(State::RECOVER_DETACH_GAZEBO, false, "/unused/attach",
                                         "/unused/detach", "/unused/output", 0.01, 0.001, true);
  const auto scene_adapter = std::make_shared<FakeSceneAdapter>();
  MoveItSceneExecutor moveit_detach(
    scene_adapter, {State::RECOVER_DETACH_MOVEIT, MoveItSceneOperation::DETACH, true});
  MoveItSceneExecutor synchronize(
    scene_adapter, {State::RECOVER_SYNC_WORLD_OBJECT, MoveItSceneOperation::SYNC, true}, 0.05,
    0.001);

  EXPECT_EQ(
    open_executor
      .execute({State::RECOVER_OPEN_GRIPPER, State::RECOVER_DETACH_GAZEBO, snapshot, nullptr})
      .status,
    ActionStatus::SUCCEEDED);
  EXPECT_EQ(
    gazebo_detach
      .execute({State::RECOVER_DETACH_GAZEBO, State::RECOVER_DETACH_MOVEIT, snapshot, nullptr})
      .status,
    ActionStatus::SUCCEEDED);
  EXPECT_EQ(
    moveit_detach
      .execute({State::RECOVER_DETACH_MOVEIT, State::RECOVER_SYNC_WORLD_OBJECT, snapshot, nullptr})
      .status,
    ActionStatus::SUCCEEDED);
  EXPECT_EQ(
    synchronize
      .execute({State::RECOVER_SYNC_WORLD_OBJECT, State::RECOVER_RETREAT, snapshot, nullptr})
      .status,
    ActionStatus::SUCCEEDED);
  EXPECT_EQ(gripper_adapter->command_calls, 0);
  EXPECT_EQ(scene_adapter->detach_calls, 0);
  EXPECT_EQ(scene_adapter->sync_calls, 1);
  ASSERT_TRUE(scene_adapter->synchronized_pose);
  EXPECT_DOUBLE_EQ(scene_adapter->synchronized_pose->x, kCokePick.x);

  auto incomplete = detachedSnapshot(kPick, kCokePick);
  incomplete.gazebo_task_object_stationary = false;
  EXPECT_EQ(
    open_executor
      .execute({State::RECOVER_OPEN_GRIPPER, State::RECOVER_DETACH_GAZEBO, incomplete, nullptr})
      .status,
    ActionStatus::SUCCEEDED);
  EXPECT_EQ(gripper_adapter->command_calls, 1);

  auto stale_moveit_metadata = detachedSnapshot(kPick, kCokePick);
  stale_moveit_metadata.moveit_task_object_attached_link = "panda_hand";
  EXPECT_EQ(moveit_detach
              .execute({State::RECOVER_DETACH_MOVEIT, State::RECOVER_SYNC_WORLD_OBJECT,
                        stale_moveit_metadata, nullptr})
              .status,
            ActionStatus::SUCCEEDED);
  EXPECT_EQ(scene_adapter->detach_calls, 1);

  const auto synchronized_snapshot = detachedSnapshot(kPick, kCokePick);
  EXPECT_EQ(synchronize
              .execute({State::RECOVER_SYNC_WORLD_OBJECT, State::RECOVER_RETREAT,
                        synchronized_snapshot, nullptr})
              .status,
            ActionStatus::SUCCEEDED);
  EXPECT_EQ(scene_adapter->sync_calls, 1);

  const auto motion_adapter = std::make_shared<FakeMotionAdapter>();
  const auto target_policy = std::make_shared<FixedPickPlaceTargetPolicy>();
  const MotionStateConfig retreat_config{State::RECOVER_RETREAT, State::ERROR,
                                         MotionKind::CARTESIAN_UP, false, true};
  MotionStateAction retreat(motion_adapter, target_policy, retreat_config);
  const auto already_retreated = detachedSnapshot(kAbovePick, kCokePick);
  const auto no_op_plan = retreat.plan(State::RECOVER_RETREAT, State::ERROR,
                                       ObservationResult{already_retreated, std::nullopt});
  ASSERT_EQ(no_op_plan.action.status, ActionStatus::SUCCEEDED);
  ASSERT_TRUE(no_op_plan.artifact);
  const MotionPlanValidator retreat_validator(retreat_config, target_policy);
  EXPECT_TRUE(
    retreat_validator.validate(State::RECOVER_RETREAT, already_retreated, *no_op_plan.artifact).ok);
  EXPECT_EQ(
    retreat.execute({State::RECOVER_RETREAT, State::ERROR, already_retreated, no_op_plan.artifact})
      .status,
    ActionStatus::SUCCEEDED);
  EXPECT_EQ(motion_adapter->plan_calls, 0);
  EXPECT_EQ(motion_adapter->execute_calls, 0);
}

TEST(RecoveryWorkflow, RecoveryActionFailureStopsImmediately)
{
  for (const auto failed_state : recoveryOrderFromSafeHeight()) {
    SCOPED_TRACE(toString(failed_state));
    WorkflowHarness harness(carryingSnapshot(kAbovePlace, kCokeAbovePlace), failed_state);

    const auto result = harness.run();

    ASSERT_EQ(result.status, RunStatus::ERROR);
    ASSERT_FALSE(harness.execution_order.empty());
    EXPECT_EQ(harness.execution_order.back(), failed_state);
    EXPECT_EQ(
      std::count(harness.execution_order.begin(), harness.execution_order.end(), failed_state), 1);
    ASSERT_TRUE(result.failure);
    EXPECT_EQ(result.failure->code, std::string("RECOVERY_FAILED_") + toString(failed_state));
  }

  const Pose3d low_tcp{0.3, 0.2, 0.93, 1.0, 0.0, 0.0, 0.0};
  const Pose3d low_coke = supportedCokePoseFromTcp(low_tcp);
  WorkflowHarness lift_harness(carryingSnapshot(low_tcp, low_coke),
                               State::RECOVER_LIFT_TO_SAFE_HEIGHT);

  const auto lift_result = lift_harness.run();

  ASSERT_EQ(lift_result.status, RunStatus::ERROR);
  ASSERT_EQ(lift_harness.execution_order.size(), 1U);
  EXPECT_EQ(lift_harness.execution_order.front(), State::RECOVER_LIFT_TO_SAFE_HEIGHT);
  ASSERT_TRUE(lift_result.failure);
  EXPECT_EQ(lift_result.failure->code, "RECOVERY_FAILED_RECOVER_LIFT_TO_SAFE_HEIGHT");
}

TEST(RecoveryWorkflow, FinalErrorPreservesOriginalAndRecoveryFailure)
{
  WorkflowHarness harness(carryingSnapshot(kAbovePlace, kCokeAbovePlace),
                          State::RECOVER_DETACH_GAZEBO);

  const auto result = harness.run();

  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "RECOVERY_FAILED_RECOVER_DETACH_GAZEBO");
  EXPECT_NE(result.failure->message.find("FORWARD_FAILED"), std::string::npos);
  EXPECT_DOUBLE_EQ(result.failure->metrics.at("recovery_metric"), 0.5);
  EXPECT_DOUBLE_EQ(result.failure->metrics.at("original_forward_metric"), 0.25);
}

TEST(RecoveryWorkflow, ResumeReclassifiesChangedAttachmentFacts)
{
  WorkflowHarness harness(carryingSnapshot(kAbovePlace, kCokeAbovePlace));
  harness.checkpoints.loaded = recoveryCheckpoint(carryingSnapshot(kAbovePlace, kCokeAbovePlace));
  harness.observer.snapshot = detachedSnapshot(kPick, kCokePick, false);

  const auto result = harness.run();

  EXPECT_EQ(result.status, RunStatus::ERROR);
  ASSERT_FALSE(harness.execution_order.empty());
  EXPECT_EQ(harness.execution_order.front(), State::RECOVER_SYNC_WORLD_OBJECT);
  EXPECT_EQ(harness.planning_order, (std::vector<State>{State::RECOVER_RETREAT}));
}

TEST(RecoveryWorkflow, ResumeWaitsForGazeboCokeStationaryEvidence)
{
  WorkflowHarness harness(carryingSnapshot(kAbovePlace, kCokeAbovePlace));
  harness.observer.stationary_after_call = 3;

  const auto result = harness.run();

  EXPECT_EQ(result.status, RunStatus::ERROR);
  EXPECT_EQ(harness.execution_order, recoveryOrderFromSafeHeight());
  EXPECT_GE(harness.observer.calls, 3);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "FORWARD_FAILED");
}

}  // namespace
}  // namespace panda_gazebo_demo::pick_place
