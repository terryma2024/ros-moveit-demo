#include <gtest/gtest.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "panda_gazebo_demo/pick_place/pick_place_runtime.hpp"
#include "panda_gazebo_demo/pick_place/runtime_parameters.hpp"
#include "panda_gazebo_demo/pick_place/transition_table.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

class FakeMotionAdapter final : public IMoveItMotionAdapter
{
public:
  PlanResult plan(const MotionPlanningRequest &, const ObservationResult &) override
  {
    return {{ActionStatus::NOT_SUPPORTED, std::nullopt}, nullptr};
  }

  ActionResult execute(const MotionPlanEvidence &) override
  {
    return {ActionStatus::NOT_SUPPORTED, std::nullopt};
  }

  ActionResult cancel() override
  {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
};

class FakeGripperAdapter final : public IGripperCommandAdapter
{
public:
  ActionResult command(double, double) override
  {
    return {ActionStatus::NOT_SUPPORTED, std::nullopt};
  }

  ActionResult cancelAndWait() override
  {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
};

class FakeSceneAdapter final : public IMoveItSceneAdapter
{
public:
  ActionResult attachTaskObject(const MoveItAttachmentSpec &) override
  {
    return {ActionStatus::NOT_SUPPORTED, std::nullopt};
  }

  ActionResult detachTaskObject() override
  {
    return {ActionStatus::NOT_SUPPORTED, std::nullopt};
  }

  ActionResult upsertTaskObjectWorldPose(const Pose3d &) override
  {
    return {ActionStatus::NOT_SUPPORTED, std::nullopt};
  }

  std::optional<MoveItSceneState> observe() override
  {
    return std::nullopt;
  }
};

class FakeExecutor final : public IStateExecutor
{
public:
  ActionResult execute(const ExecutionContext &) override
  {
    return {ActionStatus::NOT_SUPPORTED, std::nullopt};
  }

  ActionResult cancel() override
  {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
};

class FakeObserver final : public IWorldObserver
{
public:
  ObservationResult observe() override
  {
    return {WorldSnapshot{}, std::nullopt};
  }
};

const std::array<State, 22> kActionStates{{
  State::PREPARE_OPEN_GRIPPER,
  State::MOVE_ABOVE_OBJECT,
  State::DESCEND,
  State::CLOSE_GRIPPER,
  State::ATTACH_GAZEBO,
  State::ATTACH_MOVEIT,
  State::LIFT,
  State::MOVE_ABOVE_PLACE,
  State::DESCEND_TO_PLACE,
  State::OPEN_GRIPPER,
  State::DETACH_GAZEBO,
  State::DETACH_MOVEIT,
  State::SYNC_WORLD_OBJECT,
  State::RETREAT,
  State::RECOVER_LIFT_TO_SAFE_HEIGHT,
  State::RECOVER_MOVE_ABOVE_PICK,
  State::RECOVER_DESCEND_TO_PICK,
  State::RECOVER_OPEN_GRIPPER,
  State::RECOVER_DETACH_GAZEBO,
  State::RECOVER_DETACH_MOVEIT,
  State::RECOVER_SYNC_WORLD_OBJECT,
  State::RECOVER_RETREAT,
}};

const std::array<State, 10> kMotionStates{{
  State::MOVE_ABOVE_OBJECT,
  State::DESCEND,
  State::LIFT,
  State::MOVE_ABOVE_PLACE,
  State::DESCEND_TO_PLACE,
  State::RETREAT,
  State::RECOVER_LIFT_TO_SAFE_HEIGHT,
  State::RECOVER_MOVE_ABOVE_PICK,
  State::RECOVER_DESCEND_TO_PICK,
  State::RECOVER_RETREAT,
}};

bool isMotionState(State state)
{
  return std::find(kMotionStates.begin(), kMotionStates.end(), state) != kMotionStates.end();
}

TEST(RegistrationCoverage, FactoryBuildsTheCompleteRuntimeGraph)
{
  const auto gazebo_attach = std::make_shared<FakeExecutor>();
  const auto gazebo_detach = std::make_shared<FakeExecutor>();
  const auto recovery_gazebo_detach = std::make_shared<FakeExecutor>();
  PickPlaceRuntimeDependencies dependencies;
  dependencies.motion = std::make_shared<FakeMotionAdapter>();
  dependencies.gripper = std::make_shared<FakeGripperAdapter>();
  dependencies.observer = std::make_shared<FakeObserver>();
  dependencies.moveit_scene = std::make_shared<FakeSceneAdapter>();
  dependencies.gazebo_attach = gazebo_attach;
  dependencies.gazebo_detach = gazebo_detach;
  dependencies.recovery_gazebo_detach = recovery_gazebo_detach;
  PickPlaceRuntimeConfig config;
  config.target_policy = std::make_shared<FixedPickPlaceTargetPolicy>();
  config.required_world_objects = {"table", "coke"};
  config.ready_joint_positions = {{"panda_joint1", 0.0}};

  const auto runtime = makePickPlaceRuntimeRegistries(dependencies, config);

  for (const auto state : kActionStates) {
    EXPECT_NE(runtime.actions.findExecutor(state), nullptr) << toString(state);
    EXPECT_EQ(runtime.actions.findPlanner(state) != nullptr, isMotionState(state))
      << toString(state);
    EXPECT_EQ(runtime.plan_validators.hasValidator(state), isMotionState(state)) << toString(state);
  }
  for (const auto state : {State::IDLE, State::DONE, State::ERROR}) {
    EXPECT_EQ(runtime.actions.findExecutor(state), nullptr) << toString(state);
    EXPECT_EQ(runtime.actions.findPlanner(state), nullptr) << toString(state);
    EXPECT_FALSE(runtime.plan_validators.hasValidator(state)) << toString(state);
  }
  EXPECT_EQ(runtime.actions.findExecutor(State::ATTACH_GAZEBO), gazebo_attach.get());
  EXPECT_EQ(runtime.actions.findExecutor(State::DETACH_GAZEBO), gazebo_detach.get());
  EXPECT_EQ(runtime.actions.findExecutor(State::RECOVER_DETACH_GAZEBO),
            recovery_gazebo_detach.get());
  EXPECT_EQ(runtime.actions.findExecutor(State::WAIT_RELEASE_SETTLE), nullptr);
  EXPECT_EQ(runtime.actions.findExecutor(State::VALIDATE_FINAL_PLACEMENT), nullptr);

  for (const auto & [state, edges] : TransitionTable::entries()) {
    static_cast<void>(edges);
    if (state != State::IDLE && !isTerminal(state)) {
      EXPECT_TRUE(runtime.contracts.hasContract(
        {state, TransitionTable::resolve(state, ActionStatus::SUCCEEDED)}))
        << toString(state);
    }
  }
  EXPECT_FALSE(runtime.contracts.validateExecuteCoverage().has_value());
}

TEST(RegistrationCoverage, PlanOnlyDependenciesDoNotRequireGazeboExecutors)
{
  PickPlaceRuntimeDependencies dependencies;
  dependencies.motion = std::make_shared<FakeMotionAdapter>();
  dependencies.observer = std::make_shared<FakeObserver>();
  PickPlaceRuntimeConfig config;
  config.target_policy = std::make_shared<FixedPickPlaceTargetPolicy>();
  config.required_world_objects = {"table", "coke"};
  config.ready_joint_positions = {{"panda_joint1", 0.0}};

  PickPlaceRuntimeRegistries runtime;
  EXPECT_NO_THROW(runtime = makePickPlaceRuntimeRegistries(dependencies, config));
  EXPECT_NE(runtime.actions.findPlanner(State::MOVE_ABOVE_OBJECT), nullptr);
  EXPECT_EQ(runtime.actions.findExecutor(State::ATTACH_GAZEBO), nullptr);
  EXPECT_EQ(runtime.actions.findExecutor(State::DETACH_GAZEBO), nullptr);
  EXPECT_EQ(runtime.actions.findExecutor(State::RECOVER_DETACH_GAZEBO), nullptr);
}

TEST(RegistrationCoverage, NullTransitionContractIsNotRegisteredCoverage)
{
  TransitionContractRegistry contracts;
  const TransitionKey key{State::CLOSE_GRIPPER, State::ATTACH_GAZEBO};

  contracts.registerContract(key, nullptr);

  EXPECT_FALSE(contracts.hasContract(key));
}

TEST(RuntimeParameters, DefaultsAreValidAndEveryBehaviorParameterChangesTheHash)
{
  const PickPlaceParameters defaults;
  EXPECT_FALSE(validatePickPlaceParameters(defaults));
  const auto default_hash = pickPlaceConfigurationHash(defaults, "target-signature");
  std::vector<PickPlaceParameters> variants;
  const auto add = [&defaults, &variants](const auto & mutate) {
    auto variant = defaults;
    mutate(variant);
    variants.push_back(std::move(variant));
  };
  add([](auto & value) { value.planning_group = "other_arm"; });
  add([](auto & value) { value.tcp_link = "other_tcp"; });
  add([](auto & value) { value.required_world_objects.push_back("fixture"); });
  add([](auto & value) { value.velocity_scaling = 0.11; });
  add([](auto & value) { value.acceleration_scaling = 0.11; });
  add([](auto & value) { value.cartesian_eef_step = 0.006; });
  add([](auto & value) { value.cartesian_min_fraction = 0.98; });
  add([](auto & value) { value.joint_jump_threshold = 0.21; });
  add([](auto & value) { value.motion_start_joint_tolerance = 0.011; });
  add([](auto & value) { value.ready_named_target = "other_ready"; });
  add([](auto & value) { value.ready_joint_tolerance = 0.011; });
  add([](auto & value) { value.tcp_position_tolerance = 0.021; });
  add([](auto & value) { value.tcp_orientation_tolerance_rad = 0.08; });
  add([](auto & value) { value.coke_position_tolerance = 0.011; });
  add([](auto & value) { value.coke_orientation_tolerance_rad = 0.08; });
  add([](auto & value) { value.gripper_open_position = 0.039; });
  add([](auto & value) { value.gripper_open_min_position = 0.037; });
  add([](auto & value) { value.gripper_close_position = 0.001; });
  add([](auto & value) { value.gripper_close_tolerance = 0.003; });
  add([](auto & value) { value.gripper_grasp_min_position = 0.027; });
  add([](auto & value) { value.gripper_grasp_max_position = 0.036; });
  add([](auto & value) { value.gripper_symmetry_tolerance = 0.002; });
  add([](auto & value) { value.joint_velocity_tolerance = 0.009; });
  add([](auto & value) { value.gripper_max_effort = 1.0; });
  add([](auto & value) { value.gripper_action_timeout_seconds = 4.0; });
  add([](auto & value) { value.attachment_timeout_seconds = 2.1; });
  add([](auto & value) { value.planning_scene_timeout_seconds = 2.1; });
  add([](auto & value) { value.state_poll_interval_seconds = 0.04; });
  add([](auto & value) { value.gazebo_initial_observation_timeout_seconds = 31.0; });
  add([](auto & value) { value.gazebo_observation_max_age_seconds = 0.6; });
  add([](auto & value) { value.coke_settle_samples = 6; });
  add([](auto & value) { value.coke_settle_interval_seconds = 0.04; });
  add([](auto & value) { value.coke_settle_position_tolerance = 0.001; });
  add([](auto & value) { value.coke_settle_orientation_tolerance_rad = 0.019; });
  add([](auto & value) { value.recovery_safe_height = 0.997; });
  add([](auto & value) { value.gazebo_world_name = "other_world"; });
  add([](auto & value) { value.gazebo_coke_model = "other_coke"; });
  add([](auto & value) { value.gazebo_attach_topic = "/other/attach"; });
  add([](auto & value) { value.gazebo_detach_topic = "/other/detach"; });
  add([](auto & value) { value.gazebo_attachment_event_topic = "/other/event"; });
  add([](auto & value) { value.gazebo_attachment_topic = "/other/attached"; });
  add([](auto & value) { value.gazebo_coke_initially_detached = false; });
  add([](auto & value) { value.gripper_action_name = "/other/gripper"; });
  add([](auto & value) { value.max_state_transitions = 101; });

  for (const auto & variant : variants) {
    EXPECT_NE(default_hash, pickPlaceConfigurationHash(variant, "target-signature"));
  }
  EXPECT_NE(default_hash, pickPlaceConfigurationHash(defaults, "other-target-signature"));
}

TEST(RuntimeParameters, RejectsNonFiniteAndUnsafeRanges)
{
  PickPlaceParameters parameters;
  parameters.velocity_scaling = std::numeric_limits<double>::quiet_NaN();
  EXPECT_TRUE(validatePickPlaceParameters(parameters));
  parameters = {};
  parameters.gazebo_initial_observation_timeout_seconds = 0.1;
  EXPECT_TRUE(validatePickPlaceParameters(parameters));
  parameters = {};
  parameters.cartesian_min_fraction = 1.1;
  EXPECT_TRUE(validatePickPlaceParameters(parameters));
  parameters = {};
  parameters.motion_start_joint_tolerance = 0.0;
  EXPECT_TRUE(validatePickPlaceParameters(parameters));
  parameters = {};
  parameters.ready_named_target.clear();
  EXPECT_TRUE(validatePickPlaceParameters(parameters));
  parameters = {};
  parameters.gripper_close_tolerance = 0.0;
  EXPECT_TRUE(validatePickPlaceParameters(parameters));
  parameters = {};
  parameters.recovery_safe_height = FixedPickPlaceTargetPolicy::kCanonicalSafeHeight - 0.001;
  EXPECT_TRUE(validatePickPlaceParameters(parameters));
  parameters = {};
  parameters.coke_settle_samples = 1;
  EXPECT_TRUE(validatePickPlaceParameters(parameters));
  parameters = {};
  parameters.gripper_grasp_min_position = parameters.gripper_grasp_max_position;
  EXPECT_TRUE(validatePickPlaceParameters(parameters));
  parameters = {};
  parameters.gripper_open_min_position = parameters.gripper_open_position + 0.001;
  EXPECT_TRUE(validatePickPlaceParameters(parameters));
  parameters = {};
  parameters.gazebo_attachment_event_topic = parameters.gazebo_attachment_topic;
  EXPECT_TRUE(validatePickPlaceParameters(parameters));
}

}  // namespace
}  // namespace panda_gazebo_demo::pick_place
