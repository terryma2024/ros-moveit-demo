#include <gtest/gtest.h>

#include <array>
#include <memory>
#include <set>
#include <string>
#include <vector>

#include "panda_gazebo_demo/pick_place/motion_plan_evidence.hpp"
#include "panda_gazebo_demo/pick_place/pick_place_contracts.hpp"
#include "panda_gazebo_demo/pick_place/transition_table.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

constexpr Pose3d kAbovePick{0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d kPick{0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d kAbovePlace{0.3, 0.2, 0.987, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d kPlace{0.3, 0.2, 0.93, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d kCokePick{0.3, 0.0, 0.836, 0.0, 0.0, 0.0, 1.0};
constexpr Pose3d kCokeAbovePick{0.3, 0.0, 0.893, 0.0, 0.0, 0.0, 1.0};
constexpr Pose3d kCokeAbovePlace{0.3, 0.2, 0.893, 0.0, 0.0, 0.0, 1.0};
constexpr Pose3d kCokePlace{0.3, 0.2, 0.836, 0.0, 0.0, 0.0, 1.0};

ActionResult succeeded()
{
  return {ActionStatus::SUCCEEDED, std::nullopt};
}

WorldSnapshot detachedSnapshot(
  const Pose3d & tcp = kPick, const Pose3d & coke = kCokePick,
  bool gripper_open = true)
{
  WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.arm_stationary = true;
  snapshot.gripper_open = gripper_open;
  snapshot.tcp_pose_world = tcp;
  snapshot.gazebo_coke_pose_world = coke;
  snapshot.gazebo_coke_attached = false;
  snapshot.moveit_coke_attached = false;
  snapshot.gazebo_coke_stationary = true;
  snapshot.moveit_world_object_poses = {{"table", Pose3d{}}, {"coke", coke}};
  const double finger_position = gripper_open ? 0.04 : 0.032;
  snapshot.joint_positions = {{"panda_finger_joint1", finger_position},
    {"panda_finger_joint2", finger_position}};
  snapshot.joint_velocities = {{"panda_finger_joint1", 0.0},
    {"panda_finger_joint2", 0.0}};
  return snapshot;
}

WorldSnapshot carryingSnapshot(
  const Pose3d & tcp, const Pose3d & coke, bool gripper_open = false)
{
  auto snapshot = detachedSnapshot(tcp, coke, gripper_open);
  snapshot.gazebo_coke_attached = true;
  snapshot.moveit_coke_attached = true;
  snapshot.moveit_world_object_poses.erase("coke");
  snapshot.moveit_coke_attached_link = "panda_hand";
  snapshot.moveit_coke_touch_links =
  {"panda_hand", "panda_leftfinger", "panda_rightfinger"};
  return snapshot;
}

WorldSnapshot gazeboOnlyAttachedSnapshot()
{
  auto snapshot = detachedSnapshot(kPick, kCokePick, false);
  snapshot.gazebo_coke_attached = true;
  return snapshot;
}

WorldSnapshot moveItOnlyAttachedSnapshot(bool gripper_open = true)
{
  auto snapshot = detachedSnapshot(kPlace, kCokePlace, gripper_open);
  snapshot.gazebo_coke_attached = false;
  snapshot.moveit_coke_attached = true;
  snapshot.moveit_world_object_poses.erase("coke");
  snapshot.moveit_coke_attached_link = "panda_hand";
  snapshot.moveit_coke_touch_links =
  {"panda_hand", "panda_leftfinger", "panda_rightfinger"};
  return snapshot;
}

void expectMetricBearingFailure(const ValidationResult & result)
{
  EXPECT_FALSE(result.ok);
  ASSERT_FALSE(result.failures.empty());
  EXPECT_FALSE(result.metrics.empty());
  for (const auto & failure : result.failures) {
    EXPECT_FALSE(failure.metrics.empty()) << failure.code;
  }
}

std::shared_ptr<const PickPlaceTargetPolicy> targetPolicy()
{
  return std::make_shared<FixedPickPlaceTargetPolicy>();
}

class MetriclessFailingContract final : public Contract
{
public:
  ValidationResult validatePrecondition(const WorldSnapshot &) const override
  {
    return {false, {{FailureCategory::PRECONDITION, "METRICLESS_FAILURE", "failed", {}}}, {}};
  }

  ValidationResult validate(
    const WorldSnapshot &, const WorldSnapshot &,
    const ActionResult &) const override
  {
    return {false, {{FailureCategory::POSTCONDITION, "METRICLESS_FAILURE", "failed", {}}}, {}};
  }
};

TEST(ForwardContracts, CloseRequiresPickPoseAndDetachedStableCoke)
{
  const auto contract = makeCloseToGazeboAttachContract(targetPolicy(), {});
  auto before = detachedSnapshot();
  before.tcp_pose_world.x += 0.05;
  before.gazebo_coke_stationary = false;
  before.gazebo_coke_attached = true;

  expectMetricBearingFailure(contract->validatePrecondition(before));
}

TEST(ForwardContracts, CloseAcceptsSymmetricStoppedCokeWidthGrasp)
{
  const auto contract = makeCloseToGazeboAttachContract(targetPolicy(), {});
  const auto before = detachedSnapshot();
  auto after = detachedSnapshot(kPick, kCokePick, false);

  const auto result = contract->validate(before, after, succeeded());

  EXPECT_TRUE(result.ok);
  EXPECT_DOUBLE_EQ(result.metrics.at("finger_symmetry_error"), 0.0);
}

TEST(ForwardContracts, GazeboAttachRequiresValidGrasp)
{
  const auto contract = makeGazeboToMoveItAttachContract({});
  auto before = detachedSnapshot(kPick, kCokePick, false);
  before.joint_positions["panda_finger_joint1"] = 0.01;

  expectMetricBearingFailure(contract->validatePrecondition(before));
}

TEST(ForwardContracts, GazeboAttachRequiresOnlyGazeboToChange)
{
  const auto contract = makeGazeboToMoveItAttachContract({});
  const auto before = detachedSnapshot(kPick, kCokePick, false);
  auto after = gazeboOnlyAttachedSnapshot();

  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);

  after.moveit_coke_attached = true;
  expectMetricBearingFailure(contract->validate(before, after, succeeded()));
}

TEST(ForwardContracts, MoveItAttachRequiresExactAttachedMetadata)
{
  const auto contract = makeMoveItAttachToLiftContract({});
  const auto before = gazeboOnlyAttachedSnapshot();
  auto after = carryingSnapshot(kPick, kCokePick);
  after.moveit_coke_attached_link = "panda_tcp";
  after.moveit_coke_touch_links.erase("panda_rightfinger");

  expectMetricBearingFailure(contract->validate(before, after, succeeded()));
}

TEST(ForwardContracts, LiftPreservesBothAttachmentsAndRelativePose)
{
  const auto contract = makeLiftToMoveAbovePlaceContract(targetPolicy(), {});
  const auto before = carryingSnapshot(kPick, kCokePick);
  auto after = carryingSnapshot(kAbovePick, kCokeAbovePick);

  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);

  after.gazebo_coke_pose_world->x += 0.02;
  expectMetricBearingFailure(contract->validate(before, after, succeeded()));
}

TEST(ForwardContracts, MoveAbovePlacePreservesCarriedObject)
{
  const auto contract = makeMoveAbovePlaceToDescendContract(targetPolicy(), {});
  const auto before = carryingSnapshot(kAbovePick, kCokeAbovePick);
  const auto after = carryingSnapshot(kAbovePlace, kCokeAbovePlace);

  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);
}

TEST(ForwardContracts, DescendToPlaceRequiresSupportedPlacePose)
{
  const auto contract = makeDescendPlaceToOpenContract(targetPolicy(), {});
  const auto before = carryingSnapshot(kAbovePlace, kCokeAbovePlace);
  auto after = carryingSnapshot(kPlace, kCokePlace);

  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);

  after.gazebo_coke_pose_world->z += 0.03;
  expectMetricBearingFailure(contract->validate(before, after, succeeded()));
}

TEST(ForwardContracts, OpenAtPlaceKeepsBothAttachmentsAndCokeStable)
{
  const auto contract = makeOpenToGazeboDetachContract(targetPolicy(), {});
  const auto before = carryingSnapshot(kPlace, kCokePlace);
  auto after = carryingSnapshot(kPlace, kCokePlace, true);

  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);

  after.gazebo_coke_attached = false;
  expectMetricBearingFailure(contract->validate(before, after, succeeded()));
}

TEST(ForwardContracts, GazeboDetachRequiresOpenFingersAndCokeSettling)
{
  const auto contract = makeGazeboToMoveItDetachContract({});
  const auto before = carryingSnapshot(kPlace, kCokePlace, true);
  auto after = moveItOnlyAttachedSnapshot(true);

  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);

  after.gazebo_coke_stationary = false;
  expectMetricBearingFailure(contract->validate(before, after, succeeded()));
}

TEST(ForwardContracts, MoveItDetachDefersCrossWorldPoseEquality)
{
  const auto contract = makeMoveItDetachToSyncContract({});
  const auto before = moveItOnlyAttachedSnapshot(true);
  auto after = detachedSnapshot(kPlace, kCokePlace, true);
  after.moveit_world_object_poses["coke"].x += 0.05;

  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);
}

TEST(ForwardContracts, SyncRequiresCrossWorldPoseEquality)
{
  const auto contract = makeSyncToRetreatContract(targetPolicy(), {});
  auto before = detachedSnapshot(kPlace, kCokePlace, true);
  before.moveit_world_object_poses["coke"].x += 0.05;
  auto after = before;

  expectMetricBearingFailure(contract->validate(before, after, succeeded()));

  after.moveit_world_object_poses["coke"] = kCokePlace;
  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);
}

TEST(ForwardContracts, RetreatRequiresOpenDetachedSynchronizedWorld)
{
  const auto contract = makeRetreatToDoneContract(targetPolicy(), {});
  auto before = detachedSnapshot(kPlace, kCokePlace, false);

  expectMetricBearingFailure(contract->validatePrecondition(before));
}

TEST(ForwardContracts, DoneRequiresAllFinalInvariants)
{
  const auto contract = makeRetreatToDoneContract(targetPolicy(), {});
  const auto before = detachedSnapshot(kPlace, kCokePlace, true);
  auto after = detachedSnapshot(kAbovePlace, kCokePlace, true);

  EXPECT_TRUE(contract->validate(before, after, succeeded()).ok);

  after.moveit_world_object_poses.erase("table");
  expectMetricBearingFailure(contract->validate(before, after, succeeded()));
}

TEST(ForwardContracts, EveryForwardTransitionAndPlannerHasValidationCoverage)
{
  const auto policy = targetPolicy();
  const std::vector<std::string> required_objects{"table", "coke"};
  TransitionContractRegistry contracts;
  contracts.registerContract({State::PREPARE_OPEN_GRIPPER, State::MOVE_ABOVE_OBJECT},
    std::make_shared<PrepareOpenGripperToMoveAboveObjectValidator>(
      required_objects, 0.005, 0.035, 0.003, 0.035));
  contracts.registerContract({State::MOVE_ABOVE_OBJECT, State::DESCEND},
    std::make_shared<MoveAboveObjectToDescendValidator>(
      policy, required_objects, 0.005, 0.035, 0.003, 0.035));
  contracts.registerContract({State::DESCEND, State::CLOSE_GRIPPER},
    std::make_shared<DescendToCloseGripperValidator>(
      policy, required_objects, 0.005, 0.035, 0.003, 0.035));
  registerPickPlaceForwardContracts(contracts, policy, {});

  const TransitionTable table;
  EXPECT_FALSE(contracts.validateExecuteCoverage(table).has_value());

  PlanValidatorRegistry plan_validators;
  const std::array motion_configs{
    MotionStateConfig{State::MOVE_ABOVE_OBJECT, State::DESCEND, MotionKind::POSE, false},
    MotionStateConfig{State::DESCEND, State::CLOSE_GRIPPER, MotionKind::CARTESIAN_DOWN, false},
    MotionStateConfig{State::LIFT, State::MOVE_ABOVE_PLACE, MotionKind::CARTESIAN_UP, true},
    MotionStateConfig{State::MOVE_ABOVE_PLACE, State::DESCEND_TO_PLACE, MotionKind::POSE, true},
    MotionStateConfig{State::DESCEND_TO_PLACE, State::OPEN_GRIPPER,
      MotionKind::CARTESIAN_DOWN, true},
    MotionStateConfig{State::RETREAT, State::DONE, MotionKind::CARTESIAN_UP, false},
  };
  for (const auto & config : motion_configs) {
    plan_validators.registerValidator(
      config.state, std::make_shared<MotionPlanValidator>(config, policy));
  }
  for (const auto & config : motion_configs) {
    EXPECT_TRUE(plan_validators.hasValidator(config.state)) << toString(config.state);
  }
}

TEST(ForwardContracts, RegistryAddsBoundaryMetricsToEveryContractFailure)
{
  TransitionContractRegistry contracts;
  contracts.registerContract(
    {State::CLOSE_GRIPPER, State::ATTACH_GAZEBO},
    std::make_shared<MetriclessFailingContract>());
  const auto snapshot = detachedSnapshot();

  const auto precondition = contracts.validatePrecondition(
    {State::CLOSE_GRIPPER, State::ATTACH_GAZEBO}, snapshot);
  const auto postcondition = contracts.validate(
    {State::CLOSE_GRIPPER, State::ATTACH_GAZEBO}, snapshot, snapshot, succeeded());

  ASSERT_FALSE(precondition.failures.empty());
  EXPECT_FALSE(precondition.failures.front().metrics.empty());
  ASSERT_FALSE(postcondition.failures.empty());
  EXPECT_FALSE(postcondition.failures.front().metrics.empty());
}

}  // namespace
}  // namespace panda_gazebo_demo::pick_place
