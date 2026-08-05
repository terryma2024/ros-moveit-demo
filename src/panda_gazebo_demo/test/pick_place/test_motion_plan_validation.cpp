#include <gtest/gtest.h>

#include <algorithm>
#include <limits>
#include <memory>
#include <string>

#include "panda_gazebo_demo/pick_place/motion_plan_evidence.hpp"
#include "panda_gazebo_demo/pick_place/moveit_motion_adapter.hpp"
#include "panda_gazebo_demo/pick_place/named_target_validation.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

constexpr Pose3d kStart{0.3, 0.0, 0.87, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d kLiftTarget{0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d kPlaceTarget{0.3, 0.2, 0.87, 1.0, 0.0, 0.0, 0.0};

MotionPlanEvidence validEvidence(MotionKind kind, const Pose3d & start, const Pose3d & target,
                                 bool carrying)
{
  MotionPlanEvidence evidence;
  evidence.state = State::LIFT;
  evidence.next_state = State::MOVE_ABOVE_PLACE;
  evidence.kind = kind;
  evidence.carrying = carrying;
  evidence.cartesian_fraction = 1.0;
  evidence.trajectory_points = 2;
  evidence.duration_seconds = 1.0;
  evidence.max_joint_jump = 0.05;
  evidence.start_tcp_pose = start;
  evidence.end_tcp_pose = target;
  evidence.tcp_path = {
    {start.x, start.y, (start.z + target.z) / 2.0, target.qx, target.qy, target.qz, target.qw},
    target};
  evidence.collision_aware = true;
  evidence.attached_object_in_model = carrying;
  evidence.carried_relative_pose_available = carrying;
  evidence.max_carried_relative_position_error = 0.0;
  evidence.max_carried_relative_orientation_error_rad = 0.0;
  evidence.carried_clearance_verified = carrying;
  evidence.planned_start_joint_positions = {{"panda_joint1", 0.1}, {"panda_joint2", -0.2}};
  return evidence;
}

bool hasFailure(const ValidationResult & result, const std::string & code)
{
  return std::any_of(result.failures.begin(), result.failures.end(),
                     [&code](const Failure & failure) { return failure.code == code; });
}

TEST(CarriedMotionPlan, RejectsMissingAttachedObjectEvidence)
{
  auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);
  evidence.attached_object_in_model = false;
  evidence.carried_clearance_verified = false;

  const auto result =
    validateMotionPlan(evidence, kLiftTarget, MotionKind::CARTESIAN_UP, true, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "ATTACHED_OBJECT_MODEL_EVIDENCE_MISSING"));
  EXPECT_TRUE(hasFailure(result, "CARRIED_OBJECT_CLEARANCE_EVIDENCE_MISSING"));
}

TEST(CarriedMotionPlan, RejectsRelativePoseDrift)
{
  auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);
  evidence.max_carried_relative_position_error = 0.02;
  evidence.max_carried_relative_orientation_error_rad = 0.2;

  const auto result =
    validateMotionPlan(evidence, kLiftTarget, MotionKind::CARTESIAN_UP, true, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "CARRIED_RELATIVE_POSITION_DRIFT"));
  EXPECT_TRUE(hasFailure(result, "CARRIED_RELATIVE_ORIENTATION_DRIFT"));
}

TEST(CartesianLiftPlan, RejectsLateralMotion)
{
  auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);
  evidence.tcp_path.front().x += 0.03;

  const auto result =
    validateMotionPlan(evidence, kLiftTarget, MotionKind::CARTESIAN_UP, true, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "CARTESIAN_LATERAL_DEVIATION_EXCEEDED"));
}

TEST(CartesianMotionPlan, AcceptsCompleteFiniteTrajectory)
{
  const auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);

  const auto result =
    validateMotionPlan(evidence, kLiftTarget, MotionKind::CARTESIAN_UP, true, MotionPlanLimits{});

  EXPECT_TRUE(result.ok);
  EXPECT_DOUBLE_EQ(1.0, result.metrics.at("cartesian_fraction"));
  EXPECT_DOUBLE_EQ(0.05, result.metrics.at("max_joint_jump"));
}

TEST(CartesianMotionPlan, RejectsPartialPath)
{
  auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);
  evidence.cartesian_fraction = 0.98;

  const auto result =
    validateMotionPlan(evidence, kLiftTarget, MotionKind::CARTESIAN_UP, true, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "CARTESIAN_FRACTION_BELOW_THRESHOLD"));
}

TEST(MotionPlan, RejectsEmptyTrajectory)
{
  auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);
  evidence.trajectory_points = 0;
  evidence.tcp_path.clear();

  const auto result =
    validateMotionPlan(evidence, kLiftTarget, MotionKind::CARTESIAN_UP, true, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "EMPTY_MOTION_TRAJECTORY"));
}

TEST(MotionPlan, RejectsJointJumpAboveLimit)
{
  auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);
  evidence.max_joint_jump = 0.21;

  const auto result =
    validateMotionPlan(evidence, kLiftTarget, MotionKind::CARTESIAN_UP, true, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "MOTION_JOINT_JUMP_EXCEEDED"));
}

TEST(MotionPlan, RejectsNonFiniteTcpPath)
{
  auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);
  evidence.tcp_path.front().x = std::numeric_limits<double>::quiet_NaN();

  const auto result =
    validateMotionPlan(evidence, kLiftTarget, MotionKind::CARTESIAN_UP, true, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "MOTION_TCP_PATH_NON_FINITE"));
}

TEST(MotionPlan, RejectsOrientationDriftAndWrongEndpoint)
{
  auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);
  evidence.tcp_path.front() = {0.3, 0.0, 0.92, 0.7071067811865476, 0.0, 0.0, 0.7071067811865476};
  evidence.end_tcp_pose.z -= 0.03;

  const auto result =
    validateMotionPlan(evidence, kLiftTarget, MotionKind::CARTESIAN_UP, true, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "MOTION_ORIENTATION_DEVIATION_EXCEEDED"));
  EXPECT_TRUE(hasFailure(result, "MOTION_ENDPOINT_POSITION_OUTSIDE_TOLERANCE"));
}

TEST(CartesianPlacePlan, RejectsUpwardSegment)
{
  const Pose3d start{0.3, 0.2, 0.987, 1.0, 0.0, 0.0, 0.0};
  auto evidence = validEvidence(MotionKind::CARTESIAN_DOWN, start, kPlaceTarget, true);
  evidence.tcp_path = {{0.3, 0.2, 1.00, 1.0, 0.0, 0.0, 0.0}, kPlaceTarget};

  const auto result = validateMotionPlan(evidence, kPlaceTarget, MotionKind::CARTESIAN_DOWN, true,
                                         MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "CARTESIAN_PATH_NOT_MONOTONIC_DOWN"));
}

TEST(RetreatPlan, RejectsDownwardSegment)
{
  const Pose3d target{0.3, 0.2, 0.987, 1.0, 0.0, 0.0, 0.0};
  auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kPlaceTarget, target, false);
  evidence.state = State::RETREAT;
  evidence.next_state = State::DONE;
  evidence.tcp_path = {{0.3, 0.2, 0.85, 1.0, 0.0, 0.0, 0.0}, target};

  const auto result =
    validateMotionPlan(evidence, target, MotionKind::CARTESIAN_UP, false, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "CARTESIAN_PATH_NOT_MONOTONIC_UP"));
}

TEST(PoseCarryPlan, RequiresTimedCollisionAwareTrajectory)
{
  const Pose3d target{0.3, 0.2, 0.987, 1.0, 0.0, 0.0, 0.0};
  auto evidence = validEvidence(MotionKind::POSE, kLiftTarget, target, true);
  evidence.duration_seconds = 0.0;
  evidence.collision_aware = false;

  const auto result =
    validateMotionPlan(evidence, target, MotionKind::POSE, true, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "MOTION_TRAJECTORY_NOT_TIMED"));
  EXPECT_TRUE(hasFailure(result, "COLLISION_AWARE_PLAN_EVIDENCE_MISSING"));
}

TEST(MotionPlanValidator, RejectsMissingPlannedStartJointEvidence)
{
  auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);
  evidence.planned_start_joint_positions.clear();
  WorldSnapshot before;
  before.joint_positions = {{"panda_joint1", 0.1}, {"panda_joint2", -0.2}};
  MotionPlanValidator validator(
    {State::LIFT, State::MOVE_ABOVE_PLACE, MotionKind::CARTESIAN_UP, true},
    std::make_shared<FixedPickPlaceTargetPolicy>());

  const auto result = validator.validate(State::LIFT, before, evidence);

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "MOTION_START_JOINTS_MISSING"));
}

TEST(MotionPlanValidator, RejectsNonFiniteObservedStartJoint)
{
  const auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);
  WorldSnapshot before;
  before.joint_positions = {{"panda_joint1", 0.1},
                            {"panda_joint2", std::numeric_limits<double>::quiet_NaN()}};
  MotionPlanValidator validator(
    {State::LIFT, State::MOVE_ABOVE_PLACE, MotionKind::CARTESIAN_UP, true},
    std::make_shared<FixedPickPlaceTargetPolicy>());

  const auto result = validator.validate(State::LIFT, before, evidence);

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "MOTION_START_JOINT_NON_FINITE"));
}

TEST(MotionPlanValidator, RejectsObservedStartJointMismatch)
{
  const auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);
  WorldSnapshot before;
  before.joint_positions = {{"panda_joint1", 0.1}, {"panda_joint2", -0.3}};
  MotionPlanLimits limits;
  limits.start_joint_tolerance = 0.01;
  MotionPlanValidator validator(
    {State::LIFT, State::MOVE_ABOVE_PLACE, MotionKind::CARTESIAN_UP, true},
    std::make_shared<FixedPickPlaceTargetPolicy>(), limits);

  const auto result = validator.validate(State::LIFT, before, evidence);

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "MOTION_START_JOINT_MISMATCH"));
}

TEST(MotionExecutionStartValidation, RejectsStateChangedAfterPlanValidation)
{
  const std::map<std::string, double> planned{{"panda_joint1", 0.1}, {"panda_joint2", -0.2}};
  const std::map<std::string, double> current{{"panda_joint1", 0.1}, {"panda_joint2", -0.25}};

  const auto result = validateMotionStartJoints(planned, current, 0.01);

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "MOTION_START_JOINT_MISMATCH"));
}

TEST(MotionObservationThresholds, ConfiguredLimitsChangeObservedFacts)
{
  WorldSnapshot snapshot;
  snapshot.joint_positions = {{"panda_finger_joint1", 0.04}, {"panda_finger_joint2", 0.04}};
  snapshot.joint_velocities = {{"panda_joint1", 0.02},
                               {"panda_finger_joint1", 0.0},
                               {"panda_finger_joint2", 0.0}};
  GripperLimits strict_gripper;
  strict_gripper.open_min = 0.041;

  applyMotionObservationThresholds(snapshot, 0.01, strict_gripper);
  EXPECT_FALSE(snapshot.arm_stationary);
  EXPECT_FALSE(snapshot.gripper_open);

  GripperLimits permissive_gripper;
  permissive_gripper.open_min = 0.038;
  applyMotionObservationThresholds(snapshot, 0.03, permissive_gripper);
  EXPECT_TRUE(snapshot.arm_stationary);
  EXPECT_TRUE(snapshot.gripper_open);
}

MotionPlanEvidence readyEvidence()
{
  MotionPlanEvidence evidence;
  evidence.state = State::RETREAT;
  evidence.next_state = State::DONE;
  evidence.kind = MotionKind::NAMED_TARGET;
  evidence.named_target = "ready";
  evidence.trajectory_points = 2;
  evidence.target_joint_positions = {{"panda_joint1", 0.0}, {"panda_joint2", -0.785}};
  evidence.planned_end_joint_positions = evidence.target_joint_positions;
  return evidence;
}

TEST(NamedTargetPlanValidator, AcceptsMatchingReadyPlan)
{
  const auto evidence = readyEvidence();
  const NamedTargetPlanValidator validator(State::RETREAT, State::DONE, "ready",
                                           evidence.target_joint_positions, 0.010);

  EXPECT_TRUE(validator.validate(State::RETREAT, WorldSnapshot{}, evidence).ok);
}

TEST(NamedTargetPlanValidator, RejectsWrongPlannedEndpoint)
{
  auto evidence = readyEvidence();
  evidence.planned_end_joint_positions["panda_joint1"] = 0.02;
  const NamedTargetPlanValidator validator(State::RETREAT, State::DONE, "ready",
                                           evidence.target_joint_positions, 0.010);

  const auto result = validator.validate(State::RETREAT, WorldSnapshot{}, evidence);

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "NAMED_TARGET_ENDPOINT_MISMATCH"));
}

TEST(NamedTargetPlanValidator, RejectsMissingRequestedJoint)
{
  auto evidence = readyEvidence();
  evidence.planned_end_joint_positions.erase("panda_joint2");
  const NamedTargetPlanValidator validator(State::RETREAT, State::DONE, "ready",
                                           evidence.target_joint_positions, 0.010);

  const auto result = validator.validate(State::RETREAT, WorldSnapshot{}, evidence);

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "NAMED_TARGET_JOINTS_MISSING"));
}

}  // namespace
}  // namespace panda_gazebo_demo::pick_place
