#include <algorithm>
#include <chrono>
#include <limits>
#include <memory>
#include <optional>
#include <set>
#include <stdexcept>
#include <vector>

#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/pick_place_runtime.hpp"
#include "so101_gazebo_demo/pick_place/so101_fixed_motion_targets.hpp"
#include "so101_gazebo_demo/pick_place/transition_table.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

class FakeGripper final : public spp::ISO101GripperCommand
{
public:
  spp::ActionResult command(double) override
  {
    ++calls;
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult cancelAndWait() override
  {
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  int calls{0};
};

class FakeExecutor final : public spp::IStateExecutor
{
public:
  spp::ActionResult execute(const spp::ExecutionContext &) override
  {
    ++calls;
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult cancel() override
  {
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  int calls{0};
};

class FakeScene final : public spp::IMoveItSceneAdapter
{
public:
  spp::ActionResult attachCoke(const spp::MoveItAttachmentSpec &) override
  {
    ++attach_calls;
    state.coke_attached = true;
    state.coke_in_world = false;
    state.attached_link = "gripper";
    state.touch_links = {"gripper", "jaw"};
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult detachCoke() override
  {
    state.coke_attached = false;
    state.coke_in_world = true;
    state.attached_link.clear();
    state.touch_links.clear();
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult upsertCokeWorldPose(const spp::Pose3d & pose) override
  {
    state.coke_world_pose = pose;
    state.coke_in_world = true;
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult upsertTableWorldPose(const spp::Pose3d &) override
  {
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  std::optional<spp::MoveItSceneState> observe() override
  {
    return state;
  }

  spp::MoveItSceneState state{true, false, {}, {}, spp::SO101Profile::canonical().coke_pose,
                              true, spp::SO101Profile::canonical().table_pose};
  int attach_calls{0};
};

class RecordingMotion final : public spp::IMoveItJointMotionAdapter
{
public:
  spp::PlanResult plan(const spp::JointMotionRequest & request,
                       const spp::ObservationResult &) override
  {
    ++plan_calls;
    last_request = request;
    auto artifact = std::make_shared<spp::MotionPlanArtifact>();
    artifact->trajectory_points = 2;
    artifact->joint_names = request.joint_names;
    artifact->start_joint_positions.assign(request.joint_names.size(), 0.0);
    artifact->goal_joint_positions = request.joint_waypoints.back();
    artifact->samples.resize(2);
    artifact->samples.front().joint_positions = artifact->start_joint_positions;
    artifact->samples.back().joint_positions = artifact->goal_joint_positions;
    last_planned = artifact;
    return {{spp::ActionStatus::SUCCEEDED, std::nullopt}, artifact};
  }

  spp::ActionResult execute(const spp::MotionPlanArtifact & artifact) override
  {
    ++execute_calls;
    executed = &artifact;
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }

  spp::ActionResult cancel() override
  {
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }

  int plan_calls{0};
  int execute_calls{0};
  const spp::MotionPlanArtifact * executed{nullptr};
  std::shared_ptr<spp::MotionPlanArtifact> last_planned;
  spp::JointMotionRequest last_request;
};

class FakeBoundary final : public spp::IJointPlanningBoundary
{
public:
  std::optional<spp::CurrentJointStateEvidence> currentState() override
  {
    ++current_calls;
    return current;
  }
  std::optional<spp::MotionPlanningSceneFacts> sceneFacts() override
  {
    ++scene_calls;
    return scene;
  }
  spp::JointSegmentPlanResult planSegment(
    const std::vector<std::string> &, const std::vector<double> &,
    const std::vector<double> &, const std::set<std::string> &,
    const std::optional<spp::TemporalContactPolicy> &, double) override
  {
    return {{spp::ActionStatus::NOT_SUPPORTED, std::nullopt}, std::nullopt};
  }

  spp::CurrentJointStateEvidence current;
  spp::MotionPlanningSceneFacts scene;
  int current_calls{0};
  int scene_calls{0};
};

class StubPlannerExecutor final : public spp::IStatePlanner, public spp::IStateExecutor
{
public:
  spp::PlanResult plan(spp::State, spp::State, const spp::ObservationResult &) override
  {
    return {{spp::ActionStatus::SUCCEEDED, std::nullopt},
            std::make_shared<spp::PlanArtifact>()};
  }
  spp::ActionResult execute(const spp::ExecutionContext &) override
  {
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult cancel() override
  {
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
};

spp::SO101PickPlaceRuntimeDependencies completeDependencies()
{
  spp::SO101PickPlaceRuntimeDependencies dependencies;
  dependencies.gripper = std::make_shared<FakeGripper>();
  dependencies.moveit_scene = std::make_shared<FakeScene>();
  dependencies.gazebo_attach = std::make_shared<FakeExecutor>();
  dependencies.gazebo_detach = std::make_shared<FakeExecutor>();
  dependencies.recovery_gazebo_detach = std::make_shared<FakeExecutor>();
  dependencies.motion_policy = std::make_shared<spp::SO101FixedMotionTargetPolicy>();
  dependencies.motion = std::make_shared<RecordingMotion>();
  return dependencies;
}

spp::ObservationResult detachedObservation()
{
  const auto & profile = spp::SO101Profile::canonical();
  spp::WorldSnapshot world;
  world.fresh = true;
  world.arm_stationary = true;
  world.joint_positions[profile.gripper_joint] = profile.q6_preopen;
  world.joint_velocities[profile.gripper_joint] = 0.0;
  world.gazebo_coke_pose_world = profile.coke_pose;
  world.gazebo_coke_attached = false;
  world.gazebo_coke_stationary = true;
  world.moveit_coke_attached = false;
  world.moveit_world_object_poses[profile.table_object] = profile.table_pose;
  world.moveit_world_object_poses[profile.coke_model] = profile.coke_pose;
  return {world, std::nullopt};
}

std::shared_ptr<FakeBoundary> validBoundary()
{
  const auto & profile = spp::SO101Profile::canonical();
  auto boundary = std::make_shared<FakeBoundary>();
  boundary->current.joint_names = profile.arm_joints;
  boundary->current.positions = {0.0, 0.1, 0.2, 0.3, 0.4};
  boundary->current.velocities = {0.0, 0.0, 0.0, 0.0, 0.0};
  boundary->current.gripper_position = profile.q6_preopen;
  boundary->current.gripper_velocity = 0.0;
  boundary->current.observed_stamp_nanoseconds = 1234;
  boundary->current.received_at = std::chrono::steady_clock::now();
  boundary->scene.table_in_world = true;
  boundary->scene.coke_in_world = true;
  boundary->scene.coke_attached = false;
  boundary->scene.table_world_pose = profile.table_pose;
  boundary->scene.coke_world_pose = profile.coke_pose;
  boundary->scene.current_gripper_pose_world =
    spp::Pose3d{0.0, -0.28, 0.25, 0.0, 0.0, 0.0, 1.0};
  boundary->scene.current_tcp_pose_world =
    spp::Pose3d{0.02, -0.28, 0.282, 0.0, 0.0, 0.0, 1.0};
  return boundary;
}

spp::WorldSnapshot detachedMotionWorld(const spp::SO101FixedMotionSpec & spec,
                                       const spp::SO101Profile & profile)
{
  spp::WorldSnapshot world;
  world.observed_at = std::chrono::steady_clock::now();
  world.fresh = true;
  world.arm_stationary = true;
  world.tcp_pose_world = {spec.validation.endpoint_position.x,
                          spec.validation.endpoint_position.y,
                          spec.validation.endpoint_position.z,
                          0.0, 0.0, 0.0, 1.0};
  for (std::size_t i = 0; i < profile.arm_joints.size(); ++i) {
    world.joint_positions[profile.arm_joints[i]] = spec.target.joint_waypoints.back()[i];
    world.joint_velocities[profile.arm_joints[i]] = 0.0;
  }
  world.joint_positions[profile.gripper_joint] = spec.expected_gripper_q6;
  world.joint_velocities[profile.gripper_joint] = 0.0;
  world.moveit_world_object_poses[profile.table_object] = profile.table_pose;
  const auto coke = spec.state == spp::State::RETREAT ? profile.place_coke_pose
                                                       : profile.coke_pose;
  world.moveit_world_object_poses[profile.coke_model] = coke;
  world.moveit_coke_attached = false;
  world.gazebo_coke_pose_world = coke;
  world.gazebo_coke_attached = false;
  world.gazebo_coke_stationary = true;
  return world;
}

}  // namespace

TEST(SO101PickPlaceRuntime, RegistersEveryConcreteActionValidatorAndContractExactlyOnce)
{
  const auto runtime = spp::makeSO101PickPlaceRuntimeRegistries(completeDependencies());
  ASSERT_TRUE(runtime.execution_safe);
  EXPECT_FALSE(runtime.configuration_failure);

  const std::set<spp::State> planned{
    spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND, spp::State::LIFT,
    spp::State::MOVE_ABOVE_PLACE, spp::State::DESCEND_TO_PLACE, spp::State::RETREAT,
    spp::State::RECOVER_LIFT_TO_SAFE_HEIGHT, spp::State::RECOVER_MOVE_ABOVE_PICK,
    spp::State::RECOVER_DESCEND_TO_PICK, spp::State::RECOVER_RETREAT};
  for (const auto & [state, transitions] : spp::TransitionTable::entries()) {
    if (state == spp::State::IDLE || spp::isTerminal(state)) continue;
    EXPECT_NE(runtime.actions.findExecutor(state), nullptr) << spp::toString(state);
    EXPECT_TRUE(runtime.contracts.hasContract({state, transitions.succeeded}))
      << spp::toString(state);
    EXPECT_EQ(runtime.actions.findPlanner(state) != nullptr, planned.count(state) == 1)
      << spp::toString(state);
    EXPECT_EQ(runtime.plan_validators.hasValidator(state), planned.count(state) == 1)
      << spp::toString(state);
  }
  EXPECT_EQ(runtime.actions.findPlanner(spp::State::ATTACH_MOVEIT), nullptr);
  EXPECT_FALSE(runtime.plan_validators.hasValidator(spp::State::ATTACH_MOVEIT));
}

TEST(SO101PickPlaceRuntime, MissingDependenciesRemainUnsafeWithoutPlaceholderActions)
{
  auto dependencies = completeDependencies();
  dependencies.motion.reset();
  const auto runtime = spp::makeSO101PickPlaceRuntimeRegistries(dependencies);

  EXPECT_FALSE(runtime.execution_safe);
  ASSERT_TRUE(runtime.configuration_failure);
  EXPECT_EQ(runtime.configuration_failure->category, spp::FailureCategory::CONFIGURATION);
  EXPECT_EQ(runtime.configuration_failure->code, "RUNTIME_DEPENDENCY_MISSING");
  for (const auto state : {spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND,
                           spp::State::LIFT, spp::State::MOVE_ABOVE_PLACE,
                           spp::State::DESCEND_TO_PLACE, spp::State::RETREAT,
                           spp::State::RECOVER_LIFT_TO_SAFE_HEIGHT,
                           spp::State::RECOVER_MOVE_ABOVE_PICK,
                           spp::State::RECOVER_DESCEND_TO_PICK,
                           spp::State::RECOVER_RETREAT}) {
    EXPECT_EQ(runtime.actions.findPlanner(state), nullptr) << spp::toString(state);
    EXPECT_EQ(runtime.actions.findExecutor(state), nullptr) << spp::toString(state);
    EXPECT_FALSE(runtime.plan_validators.hasValidator(state)) << spp::toString(state);
  }
}

TEST(SO101PickPlaceRuntime, MotionExecutorUsesExactPlannedArtifactWithoutReplanning)
{
  auto dependencies = completeDependencies();
  auto motion = std::dynamic_pointer_cast<RecordingMotion>(dependencies.motion);
  const auto runtime = spp::makeSO101PickPlaceRuntimeRegistries(dependencies);
  auto * planner = runtime.actions.findPlanner(spp::State::MOVE_ABOVE_OBJECT);
  auto * executor = runtime.actions.findExecutor(spp::State::MOVE_ABOVE_OBJECT);
  ASSERT_NE(planner, nullptr);
  ASSERT_NE(executor, nullptr);

  const auto observation = detachedObservation();
  const auto planned = planner->plan(spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND,
                                     observation);
  ASSERT_EQ(planned.action.status, spp::ActionStatus::SUCCEEDED);
  ASSERT_TRUE(planned.artifact);
  const auto result = executor->execute({spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND,
                                         *observation.snapshot, planned.artifact});

  EXPECT_EQ(result.status, spp::ActionStatus::SUCCEEDED);
  EXPECT_EQ(motion->plan_calls, 1);
  EXPECT_EQ(motion->execute_calls, 1);
  EXPECT_EQ(motion->executed, planned.artifact.get());
}

TEST(SO101PickPlaceRuntime, AttachMoveItIsOnlyExecutedInItsOwnState)
{
  auto dependencies = completeDependencies();
  auto scene = std::dynamic_pointer_cast<FakeScene>(dependencies.moveit_scene);
  const auto runtime = spp::makeSO101PickPlaceRuntimeRegistries(dependencies);
  auto before = *detachedObservation().snapshot;
  before.gazebo_coke_attached = true;

  const auto attach = runtime.actions.findExecutor(spp::State::ATTACH_MOVEIT)->execute(
    {spp::State::ATTACH_MOVEIT, spp::State::LIFT, before, nullptr});
  ASSERT_EQ(attach.status, spp::ActionStatus::SUCCEEDED);
  EXPECT_EQ(scene->attach_calls, 1);

  auto * lift_planner = runtime.actions.findPlanner(spp::State::LIFT);
  ASSERT_NE(lift_planner, nullptr);
  static_cast<void>(lift_planner->plan(spp::State::LIFT, spp::State::MOVE_ABOVE_PLACE,
                                       detachedObservation()));
  EXPECT_EQ(scene->attach_calls, 1);
}

TEST(SO101MoveItWorldObserver, ProducesCompleteFreshJointTcpAndSceneEvidence)
{
  const auto & profile = spp::SO101Profile::canonical();
  auto boundary = validBoundary();
  spp::SO101MoveItWorldObserver observer(
    boundary, profile, spp::SO101WorldObservationConfig{1.0, 1, 0.001, 0.001});

  const auto result = observer.observe();

  ASSERT_TRUE(result.snapshot);
  EXPECT_TRUE(result.snapshot->fresh);
  EXPECT_TRUE(result.snapshot->arm_stationary);
  EXPECT_EQ(result.snapshot->joint_positions.size(), 6U);
  EXPECT_EQ(result.snapshot->joint_velocities.size(), 6U);
  EXPECT_EQ(result.snapshot->tcp_pose_world.x, boundary->scene.current_tcp_pose_world->x);
  ASSERT_TRUE(result.snapshot->moveit_gripper_pose_world);
  EXPECT_EQ(result.snapshot->moveit_gripper_pose_world->x,
            boundary->scene.current_gripper_pose_world->x);
  EXPECT_EQ(result.snapshot->moveit_world_object_poses.at(profile.table_object).z,
            profile.table_pose.z);
  EXPECT_EQ(result.snapshot->moveit_world_object_poses.at(profile.coke_model).z,
            profile.coke_pose.z);
  EXPECT_EQ(result.snapshot->moveit_coke_attached, false);
}

TEST(SO101MoveItWorldObserver, RejectsMissingStaleNonfiniteOrInconsistentEvidence)
{
  for (const int mutation : {0, 1, 2, 3, 4, 5}) {
    auto boundary = validBoundary();
    if (mutation == 0) boundary->current.velocities.pop_back();
    if (mutation == 1) {
      boundary->current.received_at = std::chrono::steady_clock::now() - std::chrono::seconds(2);
    }
    if (mutation == 2) {
      boundary->current.positions[0] = std::numeric_limits<double>::quiet_NaN();
    }
    if (mutation == 3) boundary->scene.current_tcp_pose_world.reset();
    if (mutation == 4) boundary->scene.table_world_pose.reset();
    if (mutation == 5) {
      boundary->scene.coke_in_world = true;
      boundary->scene.coke_attached = true;
    }
    spp::SO101MoveItWorldObserver observer(
      boundary, spp::SO101Profile::canonical(),
      spp::SO101WorldObservationConfig{0.5, 1, 0.001, 0.001});

    const auto result = observer.observe();

    EXPECT_FALSE(result.snapshot) << mutation;
    ASSERT_TRUE(result.failure) << mutation;
    EXPECT_EQ(result.failure->category, spp::FailureCategory::OBSERVATION) << mutation;
  }
}

TEST(SO101RuntimeRegistries, RejectNullAndDuplicateEntries)
{
  auto action = std::make_shared<StubPlannerExecutor>();
  spp::StateActionRegistry actions;
  EXPECT_THROW(actions.registerPlanner(spp::State::DESCEND, nullptr), std::invalid_argument);
  EXPECT_THROW(actions.registerExecutor(spp::State::DESCEND, nullptr), std::invalid_argument);
  actions.registerPlanner(spp::State::DESCEND, action);
  actions.registerExecutor(spp::State::DESCEND, action);
  EXPECT_THROW(actions.registerPlanner(spp::State::DESCEND, action), std::logic_error);
  EXPECT_THROW(actions.registerExecutor(spp::State::DESCEND, action), std::logic_error);

  spp::PlanValidatorRegistry validators;
  auto validator = std::make_shared<spp::SO101MotionPlanValidator>(
    spp::MotionValidationConfig{}, false);
  EXPECT_THROW(validators.registerValidator(spp::State::DESCEND, nullptr),
               std::invalid_argument);
  validators.registerValidator(spp::State::DESCEND, validator);
  EXPECT_THROW(validators.registerValidator(spp::State::DESCEND, validator), std::logic_error);

  spp::TransitionContractRegistry contracts;
  const spp::TransitionKey key{spp::State::DESCEND, spp::State::CLOSE_GRIPPER};
  auto contract = spp::makeSO101MotionContract(
    *spp::SO101FixedMotionTargetPolicy().spec(spp::State::DESCEND));
  ASSERT_TRUE(contract);
  EXPECT_THROW(contracts.registerContract(key, nullptr), std::invalid_argument);
  contracts.registerContract(key, contract);
  EXPECT_THROW(contracts.registerContract(key, contract), std::logic_error);
}

TEST(SO101MotionContract, FullOpenMotionUsesJointOnlySemantics)
{
  auto profile = spp::SO101Profile::canonical();
  profile.gripper_geometry_model_fingerprint = "deliberately-unavailable-width-model";
  const spp::SO101FixedMotionTargetPolicy policy(profile);
  const auto spec = policy.spec(spp::State::RETREAT);
  ASSERT_TRUE(spec);
  const auto contract = spp::makeSO101MotionContract(*spec, profile);
  ASSERT_TRUE(contract);

  const auto result = contract->validatePrecondition(detachedMotionWorld(*spec, profile));

  EXPECT_TRUE(result.ok) << (result.failures.empty() ? "" : result.failures.front().code);
}

TEST(SO101MotionContract, RetreatProvesDetachedCokeStayedFixedWhileArmLeft)
{
  const auto & profile = spp::SO101Profile::canonical();
  const auto spec = spp::SO101FixedMotionTargetPolicy(profile).spec(spp::State::RETREAT);
  ASSERT_TRUE(spec);
  const auto contract = spp::makeSO101MotionContract(*spec, profile);
  auto before = detachedMotionWorld(*spec, profile);
  auto after = before;
  after.gazebo_coke_pose_world->x += profile.coke_position_drift_tolerance * 2.0;
  after.moveit_world_object_poses[profile.coke_model] = *after.gazebo_coke_pose_world;

  const auto result = contract->validate(
    before, after, {spp::ActionStatus::SUCCEEDED, std::nullopt});

  EXPECT_FALSE(result.ok);
  EXPECT_NE(std::find_if(result.failures.begin(), result.failures.end(), [](const auto & failure) {
              return failure.category == spp::FailureCategory::POSTCONDITION &&
                     failure.code == "DETACHED_COKE_DRIFT";
            }), result.failures.end());
}
