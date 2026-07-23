#include <gtest/gtest.h>

#include <array>
#include <chrono>

#include "panda_gazebo_demo/pick_place/state_validation.hpp"

namespace pick_place = panda_gazebo_demo::pick_place;

namespace
{

pick_place::WorldSnapshot gripperSnapshot(
  double finger1_position, double finger2_position,
  double finger1_velocity, double finger2_velocity)
{
  pick_place::WorldSnapshot snapshot;
  snapshot.joint_positions = {{"panda_finger_joint1", finger1_position},
    {"panda_finger_joint2", finger2_position}};
  snapshot.joint_velocities = {{"panda_finger_joint1", finger1_velocity},
    {"panda_finger_joint2", finger2_velocity}};
  return snapshot;
}

pick_place::WorldSnapshot attachmentSnapshot(bool gazebo_attached, bool moveit_attached)
{
  pick_place::WorldSnapshot snapshot;
  snapshot.gazebo_coke_attached = gazebo_attached;
  snapshot.moveit_coke_attached = moveit_attached;
  return snapshot;
}

}  // namespace

TEST(GripperValidation, RequiresBothOpenAndStopped)
{
  const pick_place::GripperLimits limits;
  const std::array cases{
    std::pair{gripperSnapshot(0.04, 0.04, 0.0, 0.0), true},
    std::pair{gripperSnapshot(0.02, 0.04, 0.0, 0.0), false},
    std::pair{gripperSnapshot(0.04, 0.02, 0.0, 0.0), false},
    std::pair{gripperSnapshot(0.04, 0.04, 0.011, 0.0), false},
    std::pair{gripperSnapshot(0.04, 0.04, 0.0, -0.011), false},
  };

  for (const auto & [snapshot, expected_ok] : cases) {
    EXPECT_EQ(expected_ok, pick_place::validateGripperOpen(snapshot, limits).ok);
  }
}

TEST(GripperValidation, AcceptsSymmetricCokeWidthGrasp)
{
  const auto result = pick_place::validateGripperGrasp(
    gripperSnapshot(0.032, 0.032, 0.0, 0.0), {});

  EXPECT_TRUE(result.ok);
  EXPECT_DOUBLE_EQ(0.0, result.metrics.at("finger_symmetry_error"));
}

TEST(GripperValidation, RejectsOnlyLeftFingerInRange)
{
  const auto result = pick_place::validateGripperGrasp(
    gripperSnapshot(0.032, 0.04, 0.0, 0.0), {});

  EXPECT_FALSE(result.ok);
  ASSERT_FALSE(result.failures.empty());
  EXPECT_EQ("GRIPPER_GRASP_POSITION_OUT_OF_RANGE", result.failures.front().code);
}

TEST(GripperValidation, RejectsAsymmetricFingerPositions)
{
  const auto result = pick_place::validateGripperGrasp(
    gripperSnapshot(0.029, 0.034, 0.0, 0.0), {});

  EXPECT_FALSE(result.ok);
  ASSERT_FALSE(result.failures.empty());
  EXPECT_EQ("GRIPPER_FINGERS_ASYMMETRIC", result.failures.front().code);
}

TEST(GripperValidation, AcceptsEmptyGripperClosedAtCommandPosition)
{
  const auto result = pick_place::validateGripperClosed(
    gripperSnapshot(0.001, 0.001, 0.0, 0.0), 0.0, 0.004, {});

  EXPECT_TRUE(result.ok);
}

TEST(AttachmentValidation, DistinguishesAllFourAttachmentCombinations)
{
  constexpr std::array combinations{
    std::pair{false, false}, std::pair{false, true},
    std::pair{true, false}, std::pair{true, true},
  };

  for (const auto & [actual_gazebo, actual_moveit] : combinations) {
    const auto snapshot = attachmentSnapshot(actual_gazebo, actual_moveit);
    for (const auto & [expected_gazebo, expected_moveit] : combinations) {
      const auto result = pick_place::validateAttachmentState(
        snapshot, expected_gazebo, expected_moveit);
      EXPECT_EQ(
        actual_gazebo == expected_gazebo && actual_moveit == expected_moveit,
        result.ok);
    }
  }
}

TEST(GazeboObserver, ReportsCokeStationaryAfterFiveStableSamples)
{
  pick_place::CokePoseStabilityTracker tracker(5, 0.002, 0.020);
  const auto start = std::chrono::steady_clock::now();
  for (int index = 0; index < 5; ++index) {
    tracker.addSample(
      {0.3 + 0.001 * index, 0.0, 0.836, 0.0, 0.0, 0.0, 1.0},
      start + std::chrono::milliseconds(index * 50));
  }

  ASSERT_TRUE(tracker.stationary());
  EXPECT_TRUE(*tracker.stationary());
}

TEST(GazeboObserver, ReportsMovingAfterPoseDeltaExceedsTolerance)
{
  pick_place::CokePoseStabilityTracker tracker(5, 0.002, 0.020);
  const auto start = std::chrono::steady_clock::now();
  const std::array<double, 5> x_positions{0.3, 0.301, 0.305, 0.306, 0.307};
  for (std::size_t index = 0; index < x_positions.size(); ++index) {
    tracker.addSample(
      {x_positions[index], 0.0, 0.836, 0.0, 0.0, 0.0, 1.0},
      start + std::chrono::milliseconds(static_cast<int>(index) * 50));
  }

  ASSERT_TRUE(tracker.stationary());
  EXPECT_FALSE(*tracker.stationary());
}
