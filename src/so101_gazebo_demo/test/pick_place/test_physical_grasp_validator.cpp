#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/physical_grasp_validator.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{
spp::WorldSnapshot snapshot(double tcp_z, double cup_z)
{
  spp::WorldSnapshot value;
  value.fresh = true;
  value.arm_stationary = true;
  value.tcp_pose_world = {0.02, -0.26, tcp_z, 0.0, 0.0, 0.0, 1.0};
  value.gazebo_task_object_pose_world = spp::Pose3d{0.02, -0.28, cup_z, 0.0, 0.0, 0.0, 1.0};
  value.gazebo_task_object_stationary = true;
  value.gazebo_task_object_gripper_contact = true;
  return value;
}
}  // namespace

TEST(PhysicalGraspValidator, PassesWhenCupClearsTableAndFollowsTcp)
{
  const auto before = snapshot(0.205, 0.165);
  const auto after = snapshot(0.206, 0.166);
  const spp::PhysicalGraspValidator validator({0.0005, 0.8, 0.001, 0.10, true});

  const auto result = validator.evaluate(before, after, {0.12, -0.045});

  EXPECT_TRUE(result.passed);
  EXPECT_GT(result.table_clearance_m, 0.0005);
  EXPECT_GT(result.cup_follow_ratio, 0.8);
  EXPECT_EQ(result.failure.code, "");
}

TEST(PhysicalGraspValidator, RejectsMissingContactEvenWhenCupMoved)
{
  const auto before = snapshot(0.205, 0.165);
  auto after = snapshot(0.206, 0.166);
  after.gazebo_task_object_gripper_contact = false;
  const spp::PhysicalGraspValidator validator({0.0005, 0.8, 0.001, 0.10, true});

  const auto result = validator.evaluate(before, after, {0.12, -0.045});

  EXPECT_FALSE(result.passed);
  EXPECT_EQ(result.failure.code, "PHYSICAL_GRASP_CONTACT_MISSING");
}

TEST(PhysicalGraspValidator, RejectsCenterLiftWhenCupBottomStillTouchesTable)
{
  // The Gazebo cup model pose is its centre frame.  Its lowest collision point
  // is 45 mm below that frame, so a 0.5 mm centre rise still leaves the bottom
  // only 0.5 mm above the 120 mm table surface.
  const auto before = snapshot(0.205, 0.165);
  const auto after = snapshot(0.206, 0.1655);
  const spp::PhysicalGraspValidator validator({0.0008, 0.4, 0.001, 0.10, true});

  const auto result = validator.evaluate(before, after, {0.12, -0.045});

  EXPECT_FALSE(result.passed);
  EXPECT_EQ(result.failure.code, "PHYSICAL_GRASP_TABLE_CLEARANCE");
}
