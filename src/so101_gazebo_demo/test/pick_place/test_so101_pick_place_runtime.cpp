#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
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

class FakeMicroLift final : public spp::IWorldZMicroLift
{
public:
  spp::ActionResult executeWorldZMicroLift(const spp::Pose3d &, double delta_m) override
  {
    ++calls;
    return delta_m == 0.001 ? spp::ActionResult{spp::ActionStatus::SUCCEEDED, std::nullopt}
                            : spp::ActionResult{spp::ActionStatus::FAILED,
                              spp::Failure{spp::FailureCategory::CONFIGURATION,
                                           "MICRO_LIFT_DELTA_INVALID", "unexpected probe", {}}};
  }
  spp::ActionResult cancelWorldZMicroLift() override
  {
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  int calls{0};
};

class FakePhysicalObserver final : public spp::IWorldObserver
{
public:
  spp::ObservationResult observe() override { return {snapshot, std::nullopt}; }
  spp::WorldSnapshot snapshot;
};

class FakeScene final : public spp::IMoveItSceneAdapter
{
public:
  spp::ActionResult attachTaskObject(const spp::MoveItAttachmentSpec &) override
  {
    ++attach_calls;
    state.task_object_attached = true;
    state.task_object_in_world = false;
    state.attached_link = "gripper";
    state.touch_links = {"gripper", "jaw"};
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult detachTaskObject() override
  {
    state.task_object_attached = false;
    state.task_object_in_world = true;
    state.attached_link.clear();
    state.touch_links.clear();
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult upsertTaskObjectWorldPose(const spp::Pose3d & pose) override
  {
    state.task_object_world_pose = pose;
    state.task_object_in_world = true;
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult upsertTableWorldPose(const spp::Pose3d &) override
  {
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult upsertPedestalWorldPose(const spp::Pose3d & pose) override
  {
    state.pedestal_in_world = true;
    state.pedestal_world_pose = pose;
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  std::optional<spp::MoveItSceneState> observe() override
  {
    return state;
  }

  spp::MoveItSceneState state{true, false, {}, {}, spp::SO101Profile::canonical().task_object_pose,
                              true, spp::SO101Profile::canonical().table_pose,
                              true, spp::SO101Profile::canonical().pedestal_pose};
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

// This fixture models the CP22 transfer shape: the configured safety
// waypoints keep individual joint jumps bounded, but the home sample has not
// yet rotated the tool onto the final downward approach axis.  It is not an
// axial descent, so endpoint validation must remain distinct from the
// planner's requirement to visit every joint waypoint.
class TransferWaypointMotion final : public spp::IMoveItJointMotionAdapter
{
public:
  explicit TransferWaypointMotion(spp::SO101FixedMotionSpec spec) : spec_(std::move(spec)) {}

  spp::PlanResult plan(const spp::JointMotionRequest & request,
                       const spp::ObservationResult &) override
  {
    last_request = request;
    auto artifact = std::make_shared<spp::MotionPlanArtifact>();
    artifact->joint_names = request.joint_names;
    artifact->start_joint_positions = spec_.logical_start;
    artifact->goal_joint_positions = request.joint_waypoints.back();
    artifact->trajectory_points = request.joint_waypoints.size() + 1U;
    artifact->collision_aware = true;
    artifact->time_parameterized = true;
    artifact->moveit_success = true;
    artifact->allowed_touch_pairs = request.allowed_touch_pairs;
    artifact->temporal_contact_policy = request.temporal_contact_policy;
    const auto & endpoint = spec_.validation.endpoint_position;
    const double initial_z = endpoint.z + 0.10;
    constexpr double kQuarterTurnHalfAngleSinCos = 0.7071067811865476;
    artifact->samples.push_back({{endpoint.x, endpoint.y, initial_z,
                                  kQuarterTurnHalfAngleSinCos, 0.0, 0.0,
                                  kQuarterTurnHalfAngleSinCos},
                                 spec_.logical_start, 0.0, true});
    for (std::size_t i = 0; i < request.joint_waypoints.size(); ++i) {
      const double fraction = static_cast<double>(i + 1U) /
                              static_cast<double>(request.joint_waypoints.size());
      artifact->samples.push_back({{endpoint.x, endpoint.y,
                                    initial_z + fraction * (endpoint.z - initial_z),
                                    0.0, 0.0, 0.0, 1.0},
                                   request.joint_waypoints[i],
                                   static_cast<double>(i + 1U), true});
    }
    return {{spp::ActionStatus::SUCCEEDED, std::nullopt}, artifact};
  }

  spp::ActionResult execute(const spp::MotionPlanArtifact &) override
  {
    return {spp::ActionStatus::SUCCEEDED, std::nullopt};
  }
  spp::ActionResult cancel() override { return {spp::ActionStatus::SUCCEEDED, std::nullopt}; }

  spp::SO101FixedMotionSpec spec_;
  std::optional<spp::JointMotionRequest> last_request;
};

class FakeBoundary final : public spp::IJointPlanningBoundary
{
public:
  std::optional<spp::CurrentJointStateEvidence> currentState() override
  {
    ++current_calls;
    if (current_after_scene && scene_calls > 0) return current_after_scene;
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
  std::optional<spp::CurrentJointStateEvidence> current_after_scene;
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

std::shared_ptr<const spp::SO101ConfiguredMotionTargetPolicy> configuredPolicy()
{
  const std::filesystem::path root(SO101_TEST_POLICY_CONFIG_ROOT);
  const auto loaded = spp::loadPolicyBundle({
    (root / "task_objects/light_plastic_cup.yaml").string(),
    (root / "motion_policies/light_cup_wall_pick.yaml").string(),
    (root / "validation_policies/light_cup_wall_pick.yaml").string()});
  if (!loaded.bundle) {
    throw std::runtime_error(loaded.failure ? loaded.failure->message : "policy load failed");
  }
  return std::make_shared<const spp::SO101ConfiguredMotionTargetPolicy>(
    loaded.bundle->motion, loaded.bundle->validation);
}

spp::SO101PickPlaceRuntimeDependencies completeDependencies()
{
  spp::SO101PickPlaceRuntimeDependencies dependencies;
  dependencies.gripper = std::make_shared<FakeGripper>();
  dependencies.moveit_scene = std::make_shared<FakeScene>();
  dependencies.gazebo_attach = std::make_shared<FakeExecutor>();
  dependencies.gazebo_detach = std::make_shared<FakeExecutor>();
  dependencies.recovery_gazebo_detach = std::make_shared<FakeExecutor>();
  dependencies.motion_policy = configuredPolicy();
  dependencies.motion = std::make_shared<RecordingMotion>();
  dependencies.micro_lift = std::make_shared<FakeMicroLift>();
  auto observer = std::make_shared<FakePhysicalObserver>();
  const auto & profile = spp::SO101Profile::canonical();
  observer->snapshot.fresh = true;
  observer->snapshot.arm_stationary = true;
  observer->snapshot.tcp_pose_world = {0.02, -0.28, 0.205, 0.0, 0.0, 0.0, 1.0};
  observer->snapshot.gazebo_task_object_pose_world = profile.task_object_pose;
  observer->snapshot.gazebo_task_object_stationary = true;
  observer->snapshot.gazebo_task_object_gripper_contact = true;
  dependencies.physical_observer = std::move(observer);
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
  world.gazebo_task_object_pose_world = profile.task_object_pose;
  world.gazebo_task_object_attached = false;
  world.gazebo_task_object_stationary = true;
  world.moveit_task_object_attached = false;
  world.moveit_world_object_poses[profile.table_object] = profile.table_pose;
  world.moveit_world_object_poses[profile.task_object_id] = profile.task_object_pose;
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
  boundary->scene.pedestal_in_world = true;
  boundary->scene.task_object_in_world = true;
  boundary->scene.task_object_attached = false;
  boundary->scene.table_world_pose = profile.table_pose;
  boundary->scene.pedestal_world_pose = profile.pedestal_pose;
  boundary->scene.task_object_world_pose = profile.task_object_pose;
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
  const auto task_object = spec.state == spp::State::RETREAT ? profile.place_task_object_pose
                                                       : profile.task_object_pose;
  world.moveit_world_object_poses[profile.task_object_id] = task_object;
  world.moveit_task_object_attached = false;
  world.gazebo_task_object_pose_world = task_object;
  world.gazebo_task_object_attached = false;
  world.gazebo_task_object_stationary = true;
  return world;
}

spp::WorldSnapshot transferStartWorld(const spp::SO101FixedMotionSpec & spec,
                                      const spp::SO101Profile & profile)
{
  auto world = detachedMotionWorld(spec, profile);
  for (std::size_t i = 0; i < profile.arm_joints.size(); ++i) {
    world.joint_positions[profile.arm_joints[i]] = spec.logical_start[i];
  }
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
    if (state == spp::State::IDLE || spp::isTerminal(state) || !spp::isAction(state)) continue;
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

TEST(SO101PickPlaceRuntime, TransferSafetyWaypointsDoNotSelectAxialPathValidation)
{
  auto dependencies = completeDependencies();
  const auto spec = dependencies.motion_policy->spec(spp::State::MOVE_ABOVE_OBJECT);
  ASSERT_TRUE(spec);
  auto motion = std::make_shared<TransferWaypointMotion>(*spec);
  dependencies.motion = motion;
  const auto runtime = spp::makeSO101PickPlaceRuntimeRegistries(dependencies);
  ASSERT_TRUE(runtime.execution_safe);
  auto * planner = runtime.actions.findPlanner(spp::State::MOVE_ABOVE_OBJECT);
  ASSERT_NE(planner, nullptr);

  const auto planned = planner->plan(spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND,
                                     detachedObservation());
  ASSERT_EQ(planned.action.status, spp::ActionStatus::SUCCEEDED);
  ASSERT_TRUE(planned.artifact);
  ASSERT_TRUE(motion->last_request);
  EXPECT_TRUE(motion->last_request->ladder);

  const auto result = runtime.plan_validators.validate(
    spp::State::MOVE_ABOVE_OBJECT, transferStartWorld(*spec, spp::SO101Profile::canonical()),
    *planned.artifact);
  EXPECT_TRUE(result.ok) << (result.failures.empty() ? "" : result.failures.front().code);
}

TEST(SO101PickPlaceRuntime, AttachMoveItIsOnlyExecutedInItsOwnState)
{
  auto dependencies = completeDependencies();
  auto scene = std::dynamic_pointer_cast<FakeScene>(dependencies.moveit_scene);
  const auto runtime = spp::makeSO101PickPlaceRuntimeRegistries(dependencies);
  auto before = *detachedObservation().snapshot;
  before.gazebo_task_object_attached = true;

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
  EXPECT_EQ(result.snapshot->moveit_world_object_poses.at(profile.task_object_id).z,
            profile.task_object_pose.z);
  EXPECT_EQ(result.snapshot->moveit_task_object_attached, false);
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
      boundary->scene.task_object_in_world = true;
      boundary->scene.task_object_attached = true;
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

TEST(SO101MoveItWorldObserver, RejectsJointEvidenceThatGoesStaleWhileSceneIsCollected)
{
  auto boundary = validBoundary();
  boundary->current_after_scene = boundary->current;
  boundary->current_after_scene->received_at =
    std::chrono::steady_clock::now() - std::chrono::seconds(2);
  spp::SO101MoveItWorldObserver observer(
    boundary, spp::SO101Profile::canonical(),
    spp::SO101WorldObservationConfig{0.5, 1, 0.001, 0.001});

  const auto result = observer.observe();

  EXPECT_FALSE(result.snapshot);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ("JOINT_EVIDENCE_STALE", result.failure->code);
  EXPECT_GE(boundary->current_calls, 2);
}

TEST(SO101MoveItWorldObserver, RejectsJointOrGripperChangeWhileSceneIsCollected)
{
  for (const bool mutate_gripper : {false, true}) {
    auto boundary = validBoundary();
    boundary->current_after_scene = boundary->current;
    boundary->current_after_scene->received_at = std::chrono::steady_clock::now();
    if (mutate_gripper) {
      *boundary->current_after_scene->gripper_position += 0.01;
    } else {
      boundary->current_after_scene->positions[0] += 0.01;
    }
    spp::SO101MoveItWorldObserver observer(
      boundary, spp::SO101Profile::canonical(),
      spp::SO101WorldObservationConfig{0.5, 1, 0.001, 0.001});

    const auto result = observer.observe();

    EXPECT_FALSE(result.snapshot) << mutate_gripper;
    ASSERT_TRUE(result.failure) << mutate_gripper;
    EXPECT_EQ("ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION", result.failure->code)
      << mutate_gripper;
  }
}

TEST(SO101MoveItWorldObserver, DefaultToleranceAcceptsBulletGripperSettlingDrift)
{
  auto boundary = validBoundary();
  boundary->current_after_scene = boundary->current;
  boundary->current_after_scene->received_at = std::chrono::steady_clock::now();
  *boundary->current_after_scene->gripper_position += 0.002;
  spp::SO101MoveItWorldObserver observer(boundary);

  const auto result = observer.observe();

  ASSERT_TRUE(result.snapshot) << (result.failure ? result.failure->code : "");
  EXPECT_TRUE(result.snapshot->arm_stationary);
}

TEST(SO101MoveItWorldObserver, ArmStationaryExcludesTheSeparatelyValidatedGripperAxis)
{
  const auto & profile = spp::SO101Profile::canonical();
  auto boundary = validBoundary();
  *boundary->current.gripper_velocity = profile.q6_velocity_tolerance * 1.2;
  boundary->current_after_scene = boundary->current;
  boundary->current_after_scene->received_at = std::chrono::steady_clock::now();
  spp::SO101MoveItWorldObserver observer(
    boundary, profile, spp::SO101WorldObservationConfig{0.5, 1, 0.001, 0.001});

  const auto result = observer.observe();

  ASSERT_TRUE(result.snapshot) << (result.failure ? result.failure->code : "");
  EXPECT_TRUE(result.snapshot->arm_stationary);
  EXPECT_DOUBLE_EQ(
    profile.q6_velocity_tolerance * 1.2,
    result.snapshot->joint_velocities.at(profile.gripper_joint));
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
    *configuredPolicy()->spec(spp::State::DESCEND));
  ASSERT_TRUE(contract);
  EXPECT_THROW(contracts.registerContract(key, nullptr), std::invalid_argument);
  contracts.registerContract(key, contract);
  EXPECT_THROW(contracts.registerContract(key, contract), std::logic_error);
}

TEST(SO101MotionContract, FullOpenMotionUsesJointOnlySemantics)
{
  auto profile = spp::SO101Profile::canonical();
  profile.gripper_geometry_model_fingerprint = "deliberately-unavailable-width-model";
  const auto policy = configuredPolicy();
  const auto spec = policy->spec(spp::State::RETREAT);
  ASSERT_TRUE(spec);
  const auto contract = spp::makeSO101MotionContract(*spec, profile);
  ASSERT_TRUE(contract);

  const auto result = contract->validatePrecondition(detachedMotionWorld(*spec, profile));

  EXPECT_TRUE(result.ok) << (result.failures.empty() ? "" : result.failures.front().code);
}

TEST(SO101MotionContract, ContactCriticalDescentsRejectSucceededActionsOutsideArmEndpointContract)
{
  const auto & profile = spp::SO101Profile::canonical();
  for (const auto state : {spp::State::DESCEND, spp::State::RECOVER_DESCEND_TO_PICK}) {
    const auto spec = configuredPolicy()->spec(state);
    ASSERT_TRUE(spec) << spp::toString(state);
    ASSERT_TRUE(spec->validation.contact_wall_normal_endpoint_tolerance)
      << spp::toString(state);
    EXPECT_DOUBLE_EQ(spec->validation.joint_endpoint_tolerance, 0.00025)
      << spp::toString(state);
    EXPECT_DOUBLE_EQ(*spec->validation.contact_wall_normal_endpoint_tolerance, 0.0001)
      << spp::toString(state);
    auto contract_spec = *spec;
    if (state == spp::State::RECOVER_DESCEND_TO_PICK) {
      // Keep the recovery state/endpoint contract, while supplying its arm
      // check with independently valid q6 evidence.
      contract_spec.expected_gripper_q6 = profile.q6_preopen;
      contract_spec.target.gripper_position = profile.q6_preopen;
    }
    const auto contract = spp::makeSO101MotionContract(contract_spec, profile);
    ASSERT_TRUE(contract) << spp::toString(state);
    auto before = detachedMotionWorld(contract_spec, profile);
    if (state == spp::State::RECOVER_DESCEND_TO_PICK) {
      before.gazebo_task_object_attached = true;
      before.moveit_task_object_attached = true;
      before.moveit_world_object_poses.erase(profile.task_object_id);
      before.moveit_task_object_attached_link = profile.moveit_attach_link;
      before.moveit_task_object_touch_links = {"gripper", "jaw"};
      before.moveit_task_object_attached_relative_pose = profile.calibrated_grasp_relative_pose;
      before.moveit_gripper_pose_world = spp::Pose3d{};
      before.gazebo_task_object_pose_world = profile.calibrated_grasp_relative_pose;
      before.gazebo_task_object_gripper_contact = true;
      before.gazebo_task_object_gripper_max_depth = 0.0;
    }
    auto after = before;

    // This is inside the legacy 5 mm Euclidean TCP allowance.  A terminal
    // FollowJointTrajectory success must still block the next CLOSE/ATTACH
    // transition when the live FK is too far along the cup wall normal.
    after.tcp_pose_world.y += 0.0002;
    const auto result = contract->validate(
      before, after, {spp::ActionStatus::SUCCEEDED, std::nullopt});

    EXPECT_FALSE(result.ok) << spp::toString(state);
    EXPECT_NE(std::find_if(result.failures.begin(), result.failures.end(), [](const auto & failure) {
                return failure.category == spp::FailureCategory::POSTCONDITION &&
                       failure.code == "CONTACT_CRITICAL_WALL_NORMAL_ENDPOINT_MISMATCH";
              }), result.failures.end()) << spp::toString(state);
  }
}

TEST(SO101MotionContract, ContactCriticalDescentsRejectSucceededActionsOutsideJointEndpointBounds)
{
  const auto & profile = spp::SO101Profile::canonical();
  for (const auto state : {spp::State::DESCEND, spp::State::RECOVER_DESCEND_TO_PICK}) {
    const auto spec = configuredPolicy()->spec(state);
    ASSERT_TRUE(spec) << spp::toString(state);
    auto contract_spec = *spec;
    if (state == spp::State::RECOVER_DESCEND_TO_PICK) {
      contract_spec.expected_gripper_q6 = profile.q6_preopen;
      contract_spec.target.gripper_position = profile.q6_preopen;
    }
    const auto contract = spp::makeSO101MotionContract(contract_spec, profile);
    ASSERT_TRUE(contract) << spp::toString(state);
    auto before = detachedMotionWorld(contract_spec, profile);
    if (state == spp::State::RECOVER_DESCEND_TO_PICK) {
      before.gazebo_task_object_attached = true;
      before.moveit_task_object_attached = true;
      before.moveit_world_object_poses.erase(profile.task_object_id);
      before.moveit_task_object_attached_link = profile.moveit_attach_link;
      before.moveit_task_object_touch_links = {"gripper", "jaw"};
      before.moveit_task_object_attached_relative_pose = profile.calibrated_grasp_relative_pose;
      before.moveit_gripper_pose_world = spp::Pose3d{};
      before.gazebo_task_object_pose_world = profile.calibrated_grasp_relative_pose;
      before.gazebo_task_object_gripper_contact = true;
      before.gazebo_task_object_gripper_max_depth = 0.0;
    }
    auto after = before;
    after.joint_positions[profile.arm_joints.front()] += 0.000251;

    const auto result = contract->validate(
      before, after, {spp::ActionStatus::SUCCEEDED, std::nullopt});

    EXPECT_FALSE(result.ok) << spp::toString(state);
    EXPECT_NE(std::find_if(result.failures.begin(), result.failures.end(), [](const auto & failure) {
                return failure.category == spp::FailureCategory::POSTCONDITION &&
                       failure.code == "MOTION_JOINT_ENDPOINT_MISMATCH";
              }), result.failures.end()) << spp::toString(state);
  }
}

TEST(SO101MotionContract, ContactCriticalDescentsAcceptLiveEndpointInsideDerivedBounds)
{
  const auto & profile = spp::SO101Profile::canonical();
  for (const auto state : {spp::State::DESCEND, spp::State::RECOVER_DESCEND_TO_PICK}) {
    const auto spec = configuredPolicy()->spec(state);
    ASSERT_TRUE(spec) << spp::toString(state);
    auto contract_spec = *spec;
    if (state == spp::State::RECOVER_DESCEND_TO_PICK) {
      // Keep the recovery state/endpoint contract, while supplying its arm
      // check with independently valid q6 evidence.
      contract_spec.expected_gripper_q6 = profile.q6_preopen;
      contract_spec.target.gripper_position = profile.q6_preopen;
    }
    const auto contract = spp::makeSO101MotionContract(contract_spec, profile);
    ASSERT_TRUE(contract) << spp::toString(state);
    auto before = detachedMotionWorld(contract_spec, profile);
    if (state == spp::State::RECOVER_DESCEND_TO_PICK) {
      before.gazebo_task_object_attached = true;
      before.moveit_task_object_attached = true;
      before.moveit_world_object_poses.erase(profile.task_object_id);
      before.moveit_task_object_attached_link = profile.moveit_attach_link;
      before.moveit_task_object_touch_links = {"gripper", "jaw"};
      before.moveit_task_object_attached_relative_pose = profile.calibrated_grasp_relative_pose;
      before.moveit_gripper_pose_world = spp::Pose3d{};
      before.gazebo_task_object_pose_world = profile.calibrated_grasp_relative_pose;
      before.gazebo_task_object_gripper_contact = true;
      before.gazebo_task_object_gripper_max_depth = 0.0;
    }
    auto after = before;

    for (const auto & joint : profile.arm_joints) after.joint_positions[joint] += 0.000125;
    after.tcp_pose_world.y += 0.00005;
    const auto result = contract->validate(
      before, after, {spp::ActionStatus::SUCCEEDED, std::nullopt});

    EXPECT_TRUE(result.ok) << spp::toString(state)
                           << (result.failures.empty() ? "" : result.failures.front().code);
  }
}

TEST(SO101MotionContract, RetreatProvesDetachedTaskObjectStayedFixedWhileArmLeft)
{
  const auto & profile = spp::SO101Profile::canonical();
  const auto spec = configuredPolicy()->spec(spp::State::RETREAT);
  ASSERT_TRUE(spec);
  const auto contract = spp::makeSO101MotionContract(*spec, profile);
  auto before = detachedMotionWorld(*spec, profile);
  auto after = before;
  after.gazebo_task_object_pose_world->x += profile.task_object_position_drift_tolerance * 2.0;
  after.moveit_world_object_poses[profile.task_object_id] = *after.gazebo_task_object_pose_world;

  const auto result = contract->validate(
    before, after, {spp::ActionStatus::SUCCEEDED, std::nullopt});

  EXPECT_FALSE(result.ok);
  EXPECT_NE(std::find_if(result.failures.begin(), result.failures.end(), [](const auto & failure) {
              return failure.category == spp::FailureCategory::POSTCONDITION &&
                     failure.code == "DETACHED_TASK_OBJECT_DRIFT";
            }), result.failures.end());
}

TEST(SO101MotionContract, RequiresTrueGazeboTaskObjectStationarityBeforeMotion)
{
  const auto & profile = spp::SO101Profile::canonical();
  const auto spec = configuredPolicy()->spec(
    spp::State::MOVE_ABOVE_OBJECT);
  ASSERT_TRUE(spec);
  const auto contract = spp::makeSO101MotionContract(*spec, profile);
  auto before = detachedMotionWorld(*spec, profile);
  before.gazebo_task_object_stationary = false;

  const auto result = contract->validatePrecondition(before);

  EXPECT_FALSE(result.ok);
  EXPECT_NE(std::find_if(result.failures.begin(), result.failures.end(), [](const auto & failure) {
              return failure.category == spp::FailureCategory::OBSERVATION &&
                     failure.code == "GAZEBO_TASK_OBJECT_NOT_STATIONARY";
            }), result.failures.end());
}

TEST(SO101MotionContract, RequiresTrueGazeboTaskObjectStationarityAfterMotion)
{
  const auto & profile = spp::SO101Profile::canonical();
  const auto spec = configuredPolicy()->spec(
    spp::State::MOVE_ABOVE_OBJECT);
  ASSERT_TRUE(spec);
  const auto contract = spp::makeSO101MotionContract(*spec, profile);
  const auto before = detachedMotionWorld(*spec, profile);
  auto after = before;
  after.gazebo_task_object_stationary = false;

  const auto result = contract->validate(
    before, after, {spp::ActionStatus::SUCCEEDED, std::nullopt});

  EXPECT_FALSE(result.ok);
  EXPECT_NE(std::find_if(result.failures.begin(), result.failures.end(), [](const auto & failure) {
              return failure.category == spp::FailureCategory::OBSERVATION &&
                     failure.code == "GAZEBO_TASK_OBJECT_NOT_STATIONARY";
            }), result.failures.end());
}
