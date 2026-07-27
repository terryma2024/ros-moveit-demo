#include <gtest/gtest.h>

#include <cmath>
#include <memory>

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
};

pick_place::Pose3d cokePose()
{
  return pick_place::SO101Profile::canonical().coke_pose;
}

pick_place::WorldSnapshot snapshot(double q6, double velocity = 0.0)
{
  pick_place::WorldSnapshot world;
  world.fresh = true;
  world.arm_stationary = true;
  world.joint_positions.emplace("6", q6);
  world.joint_velocities.emplace("6", velocity);
  world.gazebo_coke_pose_world = cokePose();
  world.gazebo_coke_stationary = true;
  world.gazebo_coke_attached = false;
  world.moveit_coke_attached = false;
  const auto & profile = pick_place::SO101Profile::canonical();
  world.moveit_world_object_poses[profile.table_object] = profile.table_pose;
  world.moveit_world_object_poses[profile.coke_model] = profile.coke_pose;
  return world;
}

void setAttached(pick_place::WorldSnapshot & world)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  world.gazebo_coke_attached = true;
  world.moveit_coke_attached = true;
  world.moveit_world_object_poses.erase(profile.coke_model);
  world.moveit_coke_attached_link = profile.moveit_attach_link;
  world.moveit_coke_touch_links = {profile.moveit_touch_links.begin(),
                                   profile.moveit_touch_links.end()};
  world.moveit_coke_attached_relative_pose = profile.calibrated_grasp_relative_pose;
}

pick_place::ExecutionContext context(pick_place::State state,
                                     const pick_place::WorldSnapshot & before)
{
  const auto next = pick_place::TransitionTable::resolve(state, pick_place::ActionStatus::SUCCEEDED);
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
    {pick_place::State::CLOSE_GRIPPER, pick_place::SO101GripperTarget::CONTACT,
     profile.q6_contact},
    {pick_place::State::OPEN_GRIPPER, pick_place::SO101GripperTarget::FULL_OPEN,
     profile.q6_full_open},
    {pick_place::State::RECOVER_OPEN_GRIPPER, pick_place::SO101GripperTarget::FULL_OPEN,
     profile.q6_full_open},
  };

  for (const auto & test_case : cases) {
    auto command = std::make_shared<FakeGripperCommand>();
    pick_place::SO101GripperStateExecutor executor(
      command, {test_case.state, test_case.target, test_case.state ==
                                                   pick_place::State::RECOVER_OPEN_GRIPPER},
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
  current.gazebo_coke_attached = false;
  current.moveit_coke_attached = false;

  const auto result = executor.execute(
    context(pick_place::State::RECOVER_OPEN_GRIPPER, current));

  EXPECT_EQ(pick_place::ActionStatus::SUCCEEDED, result.status);
  EXPECT_EQ(0, command->command_calls);
}

TEST(SO101GripperValidation, ContactAcceptsPassiveStopWindowButOtherTargetsStayExact)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  EXPECT_DOUBLE_EQ(0.010, profile.contact_q6_stop_tolerance);
  EXPECT_DOUBLE_EQ(0.001, profile.contact_width_oversize_tolerance);

  const auto physical_contact = snapshot(profile.q6_contact + 0.0067);
  EXPECT_TRUE(pick_place::validateSO101GripperTarget(
    physical_contact, pick_place::SO101GripperTarget::CONTACT, profile).ok);

  const auto still_too_wide = snapshot(profile.q6_contact + 0.012);
  EXPECT_FALSE(pick_place::validateSO101GripperTarget(
    still_too_wide, pick_place::SO101GripperTarget::CONTACT, profile).ok);

  const auto imprecise_preopen = snapshot(profile.q6_preopen - 0.0067);
  EXPECT_FALSE(pick_place::validateSO101GripperTarget(
    imprecise_preopen, pick_place::SO101GripperTarget::PREOPEN, profile).ok);
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
    {pick_place::State::PREPARE_OPEN_GRIPPER,
     pick_place::SO101GripperTarget::PREOPEN, false}, profile);
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

TEST(SO101GripperTransitionContract, CloseRejectsCokeSixDegreeDriftUsingProfileTolerance)
{
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto contract = pick_place::makeSO101GripperContract(
    {pick_place::State::CLOSE_GRIPPER, pick_place::SO101GripperTarget::CONTACT, false}, profile);
  const auto before = snapshot(profile.q6_preopen);
  auto after = snapshot(profile.q6_contact);
  after.gazebo_coke_pose_world->x += profile.coke_position_drift_tolerance * 2.0;
  const pick_place::ActionResult action{pick_place::ActionStatus::SUCCEEDED, std::nullopt};

  const auto position_drift = contract->validate(before, after, action);
  EXPECT_FALSE(position_drift.ok);
  ASSERT_FALSE(position_drift.failures.empty());
  EXPECT_EQ("COKE_POSITION_DRIFT", position_drift.failures.front().code);

  after = snapshot(profile.q6_contact);
  after.gazebo_coke_pose_world->qz =
    std::sin(profile.coke_orientation_drift_tolerance_rad);
  after.gazebo_coke_pose_world->qw =
    std::cos(profile.coke_orientation_drift_tolerance_rad);
  const auto orientation_drift = contract->validate(before, after, action);
  EXPECT_FALSE(orientation_drift.ok);
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
  detached_after.gazebo_coke_attached.reset();
  EXPECT_FALSE(prepare->validate(detached_before, detached_after, action).ok);

  const auto open = pick_place::makeSO101GripperContract(
    {pick_place::State::OPEN_GRIPPER, pick_place::SO101GripperTarget::FULL_OPEN, false}, profile);
  auto attached_before = snapshot(profile.q6_contact);
  auto attached_after = snapshot(profile.q6_full_open);
  setAttached(attached_before);
  setAttached(attached_after);
  EXPECT_TRUE(open->validate(attached_before, attached_after, action).ok);
  attached_after.moveit_coke_attached_link = "wrong";
  EXPECT_FALSE(open->validate(attached_before, attached_after, action).ok);

  const auto recovery = pick_place::makeSO101GripperContract(
    {pick_place::State::RECOVER_OPEN_GRIPPER, pick_place::SO101GripperTarget::FULL_OPEN, true},
    profile);
  EXPECT_TRUE(recovery->validate(snapshot(profile.q6_contact),
                                 snapshot(profile.q6_full_open), action).ok);
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
  gazebo_only_before.gazebo_coke_attached = true;
  gazebo_only_after.gazebo_coke_attached = true;
  EXPECT_TRUE(recovery->validatePrecondition(gazebo_only_before).ok);
  EXPECT_TRUE(recovery->validate(gazebo_only_before, gazebo_only_after, action).ok);

  auto moveit_only_before = snapshot(profile.q6_contact);
  auto moveit_only_after = snapshot(profile.q6_full_open);
  setAttached(moveit_only_before);
  setAttached(moveit_only_after);
  moveit_only_before.gazebo_coke_attached = false;
  moveit_only_after.gazebo_coke_attached = false;
  EXPECT_TRUE(recovery->validatePrecondition(moveit_only_before).ok);
  EXPECT_TRUE(recovery->validate(moveit_only_before, moveit_only_after, action).ok);

  moveit_only_after.moveit_coke_attached_link = "wrong";
  EXPECT_FALSE(recovery->validate(moveit_only_before, moveit_only_after, action).ok);
}
