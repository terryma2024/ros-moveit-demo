#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/physical_grasp_retry.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{
spp::WorldSnapshot safeWorld()
{
  spp::WorldSnapshot world;
  world.fresh = true;
  world.arm_stationary = true;
  world.gazebo_task_object_stationary = true;
  world.gazebo_task_object_attached = false;
  world.moveit_task_object_attached = false;
  return world;
}

spp::PhysicalGraspResult failed(std::string code, bool contact = true)
{
  spp::PhysicalGraspResult result;
  result.failure.code = std::move(code);
  result.tcp_z_delta_m = 0.002;
  result.xy_slip_m = 0.0;
  result.orientation_change_rad = 0.0;
  result.gripper_contact = contact;
  return result;
}
}  // namespace

TEST(PhysicalGraspRetry, ContactHistoryControlsOnlyCumulativeRecloseTarget)
{
  const auto & profile = spp::SO101Profile::canonical();
  spp::PhysicalGraspRetryProgress progress{1, 0, profile.q6_contact};
  const bool contacts[] = {false, true, false, true};
  const double offsets[] = {-0.001, -0.001, -0.002, -0.002};
  for (std::size_t index = 0; index < 4; ++index) {
    const auto decision = spp::decidePhysicalGraspRetry(
      {}, profile, progress,
      failed(contacts[index] ? "PHYSICAL_GRASP_FOLLOW_RATIO" : "PHYSICAL_GRASP_CONTACT_MISSING",
             contacts[index]),
      safeWorld());
    ASSERT_TRUE(decision.retry) << index << ":"
                                << (decision.rejection ? decision.rejection->code : "no rejection");
    EXPECT_DOUBLE_EQ(profile.q6_contact + offsets[index], decision.next.current_reclose_target_q6);
    progress = decision.next;
  }
}

TEST(PhysicalGraspRetry, RejectsExhaustionAndUnsafeFacts)
{
  const auto & profile = spp::SO101Profile::canonical();
  auto world = safeWorld();
  auto result = failed("PHYSICAL_GRASP_TABLE_CLEARANCE");
  EXPECT_FALSE(
    spp::decidePhysicalGraspRetry({}, profile, {5, 0, profile.q6_contact}, result, world).retry);
  result.tcp_z_delta_m = 0.0;
  EXPECT_FALSE(
    spp::decidePhysicalGraspRetry({}, profile, {1, 0, profile.q6_contact}, result, world).retry);
  result = failed("PHYSICAL_GRASP_XY_SLIP");
  EXPECT_FALSE(
    spp::decidePhysicalGraspRetry({}, profile, {1, 0, profile.q6_contact}, result, world).retry);
  result = failed("PHYSICAL_GRASP_ORIENTATION");
  EXPECT_FALSE(
    spp::decidePhysicalGraspRetry({}, profile, {1, 0, profile.q6_contact}, result, world).retry);
  result = failed("PHYSICAL_GRASP_FOLLOW_RATIO");
  world.gazebo_task_object_attached = true;
  EXPECT_FALSE(
    spp::decidePhysicalGraspRetry({}, profile, {1, 0, profile.q6_contact}, result, world).retry);
}
