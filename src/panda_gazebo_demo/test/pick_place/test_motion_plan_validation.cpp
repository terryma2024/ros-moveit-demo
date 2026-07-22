#include <gtest/gtest.h>

#include <algorithm>
#include <string>

#include "panda_gazebo_demo/pick_place/motion_plan_evidence.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

constexpr Pose3d kStart{0.3, 0.0, 0.93, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d kLiftTarget{0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0};
constexpr Pose3d kPlaceTarget{0.3, 0.2, 0.93, 1.0, 0.0, 0.0, 0.0};

MotionPlanEvidence validEvidence(
  MotionKind kind, const Pose3d & start, const Pose3d & target, bool carrying)
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
    {start.x, start.y, (start.z + target.z) / 2.0,
      target.qx, target.qy, target.qz, target.qw},
    target};
  evidence.collision_aware = true;
  evidence.attached_object_in_model = carrying;
  evidence.carried_relative_pose_available = carrying;
  evidence.max_carried_relative_position_error = 0.0;
  evidence.max_carried_relative_orientation_error_rad = 0.0;
  evidence.carried_clearance_verified = carrying;
  return evidence;
}

bool hasFailure(const ValidationResult & result, const std::string & code)
{
  return std::any_of(result.failures.begin(), result.failures.end(),
           [&code](const Failure & failure) {return failure.code == code;});
}

TEST(CarriedMotionPlan, RejectsMissingAttachedObjectEvidence)
{
  auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);
  evidence.attached_object_in_model = false;
  evidence.carried_clearance_verified = false;

  const auto result = validateMotionPlan(
    evidence, kLiftTarget, MotionKind::CARTESIAN_UP, true, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "ATTACHED_OBJECT_MODEL_EVIDENCE_MISSING"));
  EXPECT_TRUE(hasFailure(result, "CARRIED_OBJECT_CLEARANCE_EVIDENCE_MISSING"));
}

TEST(CarriedMotionPlan, RejectsRelativePoseDrift)
{
  auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);
  evidence.max_carried_relative_position_error = 0.02;
  evidence.max_carried_relative_orientation_error_rad = 0.2;

  const auto result = validateMotionPlan(
    evidence, kLiftTarget, MotionKind::CARTESIAN_UP, true, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "CARRIED_RELATIVE_POSITION_DRIFT"));
  EXPECT_TRUE(hasFailure(result, "CARRIED_RELATIVE_ORIENTATION_DRIFT"));
}

TEST(CartesianLiftPlan, RejectsLateralMotion)
{
  auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kStart, kLiftTarget, true);
  evidence.tcp_path.front().x += 0.03;

  const auto result = validateMotionPlan(
    evidence, kLiftTarget, MotionKind::CARTESIAN_UP, true, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "CARTESIAN_LATERAL_DEVIATION_EXCEEDED"));
}

TEST(CartesianPlacePlan, RejectsUpwardSegment)
{
  const Pose3d start{0.3, 0.2, 0.987, 1.0, 0.0, 0.0, 0.0};
  auto evidence = validEvidence(MotionKind::CARTESIAN_DOWN, start, kPlaceTarget, true);
  evidence.tcp_path = {
    {0.3, 0.2, 1.00, 1.0, 0.0, 0.0, 0.0},
    kPlaceTarget};

  const auto result = validateMotionPlan(
    evidence, kPlaceTarget, MotionKind::CARTESIAN_DOWN, true, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "CARTESIAN_PATH_NOT_MONOTONIC_DOWN"));
}

TEST(RetreatPlan, RejectsDownwardSegment)
{
  const Pose3d target{0.3, 0.2, 0.987, 1.0, 0.0, 0.0, 0.0};
  auto evidence = validEvidence(MotionKind::CARTESIAN_UP, kPlaceTarget, target, false);
  evidence.state = State::RETREAT;
  evidence.next_state = State::DONE;
  evidence.tcp_path = {
    {0.3, 0.2, 0.91, 1.0, 0.0, 0.0, 0.0},
    target};

  const auto result = validateMotionPlan(
    evidence, target, MotionKind::CARTESIAN_UP, false, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "CARTESIAN_PATH_NOT_MONOTONIC_UP"));
}

TEST(PoseCarryPlan, RequiresTimedCollisionAwareTrajectory)
{
  const Pose3d target{0.3, 0.2, 0.987, 1.0, 0.0, 0.0, 0.0};
  auto evidence = validEvidence(MotionKind::POSE, kLiftTarget, target, true);
  evidence.duration_seconds = 0.0;
  evidence.collision_aware = false;

  const auto result = validateMotionPlan(
    evidence, target, MotionKind::POSE, true, MotionPlanLimits{});

  EXPECT_FALSE(result.ok);
  EXPECT_TRUE(hasFailure(result, "MOTION_TRAJECTORY_NOT_TIMED"));
  EXPECT_TRUE(hasFailure(result, "COLLISION_AWARE_PLAN_EVIDENCE_MISSING"));
}

}  // namespace
}  // namespace panda_gazebo_demo::pick_place
