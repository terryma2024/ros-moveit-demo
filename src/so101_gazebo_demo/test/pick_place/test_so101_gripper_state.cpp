#include <gtest/gtest.h>

#include <cmath>
#include <memory>
#include <vector>

#include "so101_gazebo_demo/pick_place/so101_gripper_state.hpp"
#include "so101_gazebo_demo/pick_place/transition_table.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

namespace
{

class FakeGripperCommand final : public pick_place::ISO101GripperCommand
{
public:
  pick_place::ActionResult command(double q6) override
  {
    ++command_calls;
    last_q6 = q6;
    commanded_q6.push_back(q6);
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
  double last_q6{0.0};
  std::vector<double> commanded_q6;
};

class FakeWorldObserver final : public pick_place::IWorldObserver
{
public:
  pick_place::ObservationResult observe() override
  {
    ++calls;
    return {world, std::nullopt};
  }
  pick_place::WorldSnapshot world;
  int calls{0};
};

pick_place::Pose3d task_objectPose()
{
  return pick_place::SO101Profile::canonical().task_object_pose;
}

pick_place::WorldSnapshot snapshot(double q6, double velocity = 0.0)
{
  pick_place::WorldSnapshot world;
  world.fresh = true;
  world.arm_stationary = true;
  world.joint_positions.emplace("6", q6);
  world.joint_velocities.emplace("6", velocity);
  world.gazebo_task_object_pose_world = task_objectPose();
  world.gazebo_task_object_stationary = true;
  world.gazebo_task_object_attached = false;
  world.moveit_task_object_attached = false;
  const auto & profile = pick_place::SO101Profile::canonical();
  world.moveit_world_object_poses[profile.table_object] = profile.table_pose;
  world.moveit_world_object_poses[profile.task_object_id] = profile.task_object_pose;
  return world;
}

void setAttached(pick_place::WorldSnapshot & world)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  world.gazebo_task_object_attached = true;
  world.moveit_task_object_attached = true;
  world.moveit_world_object_poses.erase(profile.task_object_id);
  world.moveit_task_object_attached_link = profile.moveit_attach_link;
  world.moveit_task_object_touch_links = {profile.moveit_touch_links.begin(),
                                          profile.moveit_touch_links.end()};
  world.moveit_task_object_attached_relative_pose = profile.calibrated_grasp_relative_pose;
}

pick_place::ExecutionContext context(pick_place::State state,
                                     const pick_place::WorldSnapshot & before)
{
  const auto next =
    pick_place::TransitionTable::resolve(state, pick_place::ActionStatus::SUCCEEDED);
  return {state, next, before, nullptr};
}

}  // namespace

TEST(SO101GripperStateExecutor, CommandsExactProfileTargetForAllFourStates)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const struct
  {
    pick_place::State state;
    pick_place::SO101GripperTarget target;
    double expected_q6;
  } cases[] = {
    {pick_place::State::PREPARE_OPEN_GRIPPER, pick_place::SO101GripperTarget::PREOPEN,
     profile.q6_preopen},
    {pick_place::State::CLOSE_GRIPPER, pick_place::SO101GripperTarget::CONTACT, profile.q6_close},
    {pick_place::State::OPEN_GRIPPER, pick_place::SO101GripperTarget::FULL_OPEN,
     profile.q6_full_open},
    {pick_place::State::RECOVER_OPEN_GRIPPER, pick_place::SO101GripperTarget::FULL_OPEN,
     profile.q6_full_open},
  };

  for (const auto & test_case : cases) {
    auto command = std::make_shared<FakeGripperCommand>();
    pick_place::SO101GripperStateExecutor executor(
      command,
      {test_case.state, test_case.target,
       test_case.state == pick_place::State::RECOVER_OPEN_GRIPPER},
      profile);
    const auto result = executor.execute(context(test_case.state, snapshot(profile.q6_contact)));
    EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, result.status);
    EXPECT_EQ(1, command->command_calls);
    EXPECT_DOUBLE_EQ(test_case.expected_q6, command->last_q6);
  }
}

TEST(SO101GripperStateExecutor, RecoveryNoOpUsesCurrentQ6AndNeedsNoAttachment)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  auto command = std::make_shared<FakeGripperCommand>();
  pick_place::SO101GripperStateExecutor executor(
    command,
    {pick_place::State::RECOVER_OPEN_GRIPPER, pick_place::SO101GripperTarget::FULL_OPEN, true},
    profile);
  auto current = snapshot(profile.q6_full_open);
  current.gazebo_task_object_attached = false;
  current.moveit_task_object_attached = false;

  const auto result = executor.execute(context(pick_place::State::RECOVER_OPEN_GRIPPER, current));

  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(0, command->command_calls);
}

TEST(SO101GripperStateExecutor, NormalOpenUsesConfiguredStagedRelease)
{
  auto profile = pick_place::SO101Profile::canonical();
  profile.release_stages_q6 = {0.209, 0.506, profile.q6_full_open};
  auto command = std::make_shared<FakeGripperCommand>();
  pick_place::SO101GripperStateExecutor executor(
    command, {pick_place::State::OPEN_GRIPPER, pick_place::SO101GripperTarget::FULL_OPEN, false},
    profile);

  const auto result =
    executor.execute(context(pick_place::State::OPEN_GRIPPER, snapshot(profile.q6_contact)));

  EXPECT_EQ(result.status, pick_place::ActionStatus::SUCCEEDED);
  EXPECT_EQ(command->commanded_q6, profile.release_stages_q6);
}

TEST(SO101GripperStateExecutor, StagedOpenAcceptsAbortOnlyAfterObservedPhysicalConvergence)
{
  auto profile = pick_place::SO101Profile::canonical();
  profile.release_stages_q6 = {profile.q6_full_open};
  auto command = std::make_shared<FakeGripperCommand>();
  command->command_result = {pick_place::ActionStatus::FAILED,
                             pick_place::Failure{pick_place::FailureCategory::GRIPPER,
                                                 "GRIPPER_ACTION_ABORTED",
                                                 "controller aborted after reaching target",
                                                 {}}};
  auto observer = std::make_shared<FakeWorldObserver>();
  observer->world = snapshot(profile.q6_full_open - 0.006, 0.0);
  setAttached(observer->world);
  pick_place::SO101GripperStateExecutor executor(
    command, {pick_place::State::OPEN_GRIPPER, pick_place::SO101GripperTarget::FULL_OPEN, false},
    profile, observer);

  const auto result =
    executor.execute(context(pick_place::State::OPEN_GRIPPER, snapshot(profile.q6_contact)));

  EXPECT_EQ(result.status, pick_place::ActionStatus::SUCCEEDED);
  EXPECT_EQ(observer->calls, 3);
}

TEST(SO101GripperValidation, ContactAcceptsPassiveStopWindowButOtherTargetsStayExact)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  EXPECT_DOUBLE_EQ(0.010, profile.contact_q6_stop_tolerance);
  EXPECT_DOUBLE_EQ(0.001, profile.contact_width_oversize_tolerance);

  const auto physical_contact = snapshot(profile.q6_contact + 0.0060);
  EXPECT_TRUE(pick_place::validateSO101GripperTarget(
                physical_contact, pick_place::SO101GripperTarget::CONTACT, profile)
                .ok);

  const auto still_too_wide = snapshot(profile.q6_contact + 0.012);
  EXPECT_FALSE(pick_place::validateSO101GripperTarget(
                 still_too_wide, pick_place::SO101GripperTarget::CONTACT, profile)
                 .ok);

  const auto imprecise_preopen = snapshot(profile.q6_preopen - 0.0067);
  EXPECT_FALSE(pick_place::validateSO101GripperTarget(
                 imprecise_preopen, pick_place::SO101GripperTarget::PREOPEN, profile)
                 .ok);
}

TEST(SO101GripperValidation, FullOpenAcceptsBulletFeatherstoneSettlingError)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  EXPECT_DOUBLE_EQ(0.012, profile.q6_full_open_tolerance);

  const auto settled = snapshot(profile.q6_full_open + 0.005, 0.0);
  EXPECT_TRUE(pick_place::validateSO101GripperTarget(
                settled, pick_place::SO101GripperTarget::FULL_OPEN, profile)
                .ok);
}

TEST(SO101GripperValidation, GazeboJawContactAcceptsPhysicalStopBeforeCommandedQ6)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  auto physical_stop = snapshot(profile.q6_contact + 0.25, 0.0);
  physical_stop.gazebo_task_object_gripper_contact = true;
  physical_stop.gazebo_task_object_gripper_max_depth = 0.0012;

  const auto result = pick_place::validateSO101GripperTarget(
    physical_stop, pick_place::SO101GripperTarget::CONTACT, profile);

  EXPECT_TRUE(result.ok);
  EXPECT_DOUBLE_EQ(result.metrics.at("gazebo_task_object_gripper_contact"), 1.0);
  EXPECT_DOUBLE_EQ(result.metrics.at("gazebo_task_object_gripper_max_depth"), 0.0012);
}

TEST(SO101GripperTransitionContract, ActionSuccessCannotReplaceFreshStoppedQ6Postcondition)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = pick_place::makeSO101GripperContract(
    {pick_place::State::PREPARE_OPEN_GRIPPER, pick_place::SO101GripperTarget::PREOPEN, false},
    profile);
  const auto before = snapshot(profile.q6_contact);
  auto wrong_q6 = snapshot(profile.q6_contact);
  const pick_place::ActionResult action{pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  EXPECT_FALSE(contract->validate(before, wrong_q6, action).ok);

  auto moving = snapshot(profile.q6_preopen, profile.q6_velocity_tolerance * 2.0);
  EXPECT_FALSE(contract->validate(before, moving, action).ok);

  auto correct = snapshot(profile.q6_preopen);
  EXPECT_TRUE(contract->validate(before, correct, action).ok);
}

TEST(SO101GripperTransitionContract, FailureReportsExpectedAndActualEndpointEvidence)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = pick_place::makeSO101GripperContract(
    {pick_place::State::PREPARE_OPEN_GRIPPER, pick_place::SO101GripperTarget::PREOPEN, false},
    profile);
  const auto before = snapshot(profile.q6_full_open);
  const auto after = snapshot(profile.q6_full_open, 0.125);
  const pick_place::ActionResult action{pick_place::ActionStatus::SUCCEEDED, std::nullopt};

  const auto validation = contract->validate(before, after, action);

  ASSERT_FALSE(validation.ok);
  ASSERT_FALSE(validation.failures.empty());
  const auto & metrics = validation.failures.front().metrics;
  EXPECT_DOUBLE_EQ(profile.q6_preopen, metrics.at("expected_q6"));
  EXPECT_DOUBLE_EQ(profile.q6_full_open, metrics.at("actual_q6"));
  EXPECT_DOUBLE_EQ(profile.preopen_width, metrics.at("expected_gripper_width"));
  EXPECT_DOUBLE_EQ(0.125, metrics.at("actual_q6_velocity"));
}

TEST(SO101GripperTransitionContract, CloseRejectsTaskObjectSixDegreeDriftUsingProfileTolerance)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = pick_place::makeSO101GripperContract(
    {pick_place::State::CLOSE_GRIPPER, pick_place::SO101GripperTarget::CONTACT, false}, profile);
  const auto before = snapshot(profile.q6_preopen);
  auto after = snapshot(profile.q6_contact);
  after.gazebo_task_object_pose_world->x += profile.task_object_position_drift_tolerance * 2.0;
  const pick_place::ActionResult action{pick_place::ActionStatus::SUCCEEDED, std::nullopt};

  const auto position_drift = contract->validate(before, after, action);
  EXPECT_FALSE(position_drift.ok);
  ASSERT_FALSE(position_drift.failures.empty());
  EXPECT_EQ("TASK_OBJECT_POSITION_DRIFT", position_drift.failures.front().code);

  after = snapshot(profile.q6_contact);
  after.gazebo_task_object_pose_world->qx =
    std::sin(profile.task_object_orientation_drift_tolerance_rad);
  after.gazebo_task_object_pose_world->qw =
    std::cos(profile.task_object_orientation_drift_tolerance_rad);
  const auto orientation_drift = contract->validate(before, after, action);
  EXPECT_FALSE(orientation_drift.ok);
}

TEST(SO101GripperTransitionContract, CloseAcceptsCylindricalYawButKeepsUprightBound)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = pick_place::makeSO101GripperContract(
    {pick_place::State::CLOSE_GRIPPER, pick_place::SO101GripperTarget::CONTACT, false}, profile);
  const auto before = snapshot(profile.q6_preopen);
  auto after = snapshot(profile.q6_contact);
  after.gazebo_task_object_pose_world->qz = std::sin(0.04);
  after.gazebo_task_object_pose_world->qw = std::cos(0.04);
  const pick_place::ActionResult action{pick_place::ActionStatus::SUCCEEDED, std::nullopt};

  const auto result = contract->validate(before, after, action);

  EXPECT_TRUE(result.ok) << (result.failures.empty() ? "" : result.failures.front().code);
  EXPECT_GT(result.metrics.at("task_object_orientation_drift_rad"),
            profile.task_object_orientation_drift_tolerance_rad);
  EXPECT_NEAR(result.metrics.at("task_object_final_tilt_rad"), 0.0, 1e-12);
}

TEST(SO101GripperTransitionContract, EnforcesStateSpecificIndependentAttachmentFacts)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const pick_place::ActionResult action{pick_place::ActionStatus::SUCCEEDED, std::nullopt};
  const auto prepare = pick_place::makeSO101GripperContract(
    {pick_place::State::PREPARE_OPEN_GRIPPER, pick_place::SO101GripperTarget::PREOPEN, false},
    profile);
  auto detached_before = snapshot(profile.q6_contact);
  auto detached_after = snapshot(profile.q6_preopen);
  EXPECT_TRUE(prepare->validate(detached_before, detached_after, action).ok);
  detached_after.gazebo_task_object_attached.reset();
  EXPECT_FALSE(prepare->validate(detached_before, detached_after, action).ok);

  const auto open = pick_place::makeSO101GripperContract(
    {pick_place::State::OPEN_GRIPPER, pick_place::SO101GripperTarget::FULL_OPEN, false}, profile);
  auto placed_before = snapshot(profile.q6_contact);
  auto placed_after = snapshot(profile.q6_full_open);
  setAttached(placed_before);
  setAttached(placed_after);
  placed_before.gazebo_task_object_pose_world = profile.place_task_object_pose;
  placed_after.gazebo_task_object_pose_world = profile.place_task_object_pose;
  EXPECT_TRUE(open->validate(placed_before, placed_after, action).ok);
  placed_after.moveit_task_object_attached = false;
  EXPECT_FALSE(open->validate(placed_before, placed_after, action).ok);

  const auto recovery = pick_place::makeSO101GripperContract(
    {pick_place::State::RECOVER_OPEN_GRIPPER, pick_place::SO101GripperTarget::FULL_OPEN, true},
    profile);
  EXPECT_TRUE(
    recovery->validate(snapshot(profile.q6_contact), snapshot(profile.q6_full_open), action).ok);
}

TEST(SO101GripperTransitionContract, NormalReleaseAllowsBoundedSupportSettling)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto open = pick_place::makeSO101GripperContract(
    {pick_place::State::OPEN_GRIPPER, pick_place::SO101GripperTarget::FULL_OPEN, false}, profile);
  auto before = snapshot(profile.q6_contact);
  auto after = snapshot(profile.q6_full_open);
  setAttached(before);
  setAttached(after);
  before.gazebo_task_object_pose_world = profile.place_task_object_pose;
  before.gazebo_task_object_pose_world->z += 0.008;
  after.gazebo_task_object_pose_world = profile.place_task_object_pose;
  after.gazebo_task_object_pose_world->x += 0.0015;
  after.gazebo_task_object_pose_world->qz = std::sin(0.20);
  after.gazebo_task_object_pose_world->qw = std::cos(0.20);
  const pick_place::ActionResult action{pick_place::ActionStatus::SUCCEEDED, std::nullopt};

  const auto result = open->validate(before, after, action);

  EXPECT_TRUE(result.ok) << (result.failures.empty() ? "" : result.failures.front().code);
  EXPECT_GT(result.metrics.at("task_object_position_drift"),
            profile.task_object_position_drift_tolerance);
}

TEST(SO101GripperTransitionContract, NormalReleaseRejectsSettlingOutsideSupportEnvelope)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto open = pick_place::makeSO101GripperContract(
    {pick_place::State::OPEN_GRIPPER, pick_place::SO101GripperTarget::FULL_OPEN, false}, profile);
  auto before = snapshot(profile.q6_contact);
  auto after = snapshot(profile.q6_full_open);
  setAttached(before);
  setAttached(after);
  before.gazebo_task_object_pose_world = profile.place_task_object_pose;
  after.gazebo_task_object_pose_world = profile.place_task_object_pose;
  after.gazebo_task_object_pose_world->x += profile.place_support_xy_tolerance + 0.001;
  const pick_place::ActionResult action{pick_place::ActionStatus::SUCCEEDED, std::nullopt};

  const auto result = open->validate(before, after, action);

  EXPECT_FALSE(result.ok);
  EXPECT_EQ(result.failures.front().code, "TASK_OBJECT_RELEASE_SUPPORT_INVALID");
}

TEST(SO101GripperTransitionContract, RecoveryOpenAcceptsOnlyInternallyExactMixedAttachmentFacts)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto recovery = pick_place::makeSO101GripperContract(
    {pick_place::State::RECOVER_OPEN_GRIPPER, pick_place::SO101GripperTarget::FULL_OPEN, true},
    profile);
  const pick_place::ActionResult action{pick_place::ActionStatus::SUCCEEDED, std::nullopt};

  auto gazebo_only_before = snapshot(profile.q6_contact);
  auto gazebo_only_after = snapshot(profile.q6_full_open);
  gazebo_only_before.gazebo_task_object_attached = true;
  gazebo_only_after.gazebo_task_object_attached = true;
  EXPECT_TRUE(recovery->validatePrecondition(gazebo_only_before).ok);
  EXPECT_TRUE(recovery->validate(gazebo_only_before, gazebo_only_after, action).ok);

  auto moveit_only_before = snapshot(profile.q6_contact);
  auto moveit_only_after = snapshot(profile.q6_full_open);
  setAttached(moveit_only_before);
  setAttached(moveit_only_after);
  moveit_only_before.gazebo_task_object_attached = false;
  moveit_only_after.gazebo_task_object_attached = false;
  EXPECT_TRUE(recovery->validatePrecondition(moveit_only_before).ok);
  EXPECT_TRUE(recovery->validate(moveit_only_before, moveit_only_after, action).ok);

  moveit_only_after.moveit_task_object_attached_link = "wrong";
  EXPECT_FALSE(recovery->validate(moveit_only_before, moveit_only_after, action).ok);
}
