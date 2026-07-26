#include <set>

#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/so101_fixed_motion_targets.hpp"

namespace spp = so101_gazebo_demo::pick_place;

TEST(SO101FixedMotionTargets, CoversExactTenStatePlanOnlyMatrix)
{
  spp::SO101FixedMotionTargetPolicy policy;
  const std::set<spp::State> states{
    spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND, spp::State::LIFT,
    spp::State::MOVE_ABOVE_PLACE, spp::State::DESCEND_TO_PLACE, spp::State::RETREAT,
    spp::State::RECOVER_LIFT_TO_SAFE_HEIGHT, spp::State::RECOVER_MOVE_ABOVE_PICK,
    spp::State::RECOVER_DESCEND_TO_PICK, spp::State::RECOVER_RETREAT};
  EXPECT_EQ(policy.version(), "so101-fixed-table-d20-v1");
  for (const auto state : states) {
    const auto spec = policy.spec(state);
    ASSERT_TRUE(spec) << spp::toString(state);
    EXPECT_EQ(spec->logical_start.size(), 5U);
    EXPECT_EQ(spec->target.joint_names,
              (std::vector<std::string>{"1", "2", "3", "4", "5"}));
    EXPECT_FALSE(spec->target.joint_waypoints.empty());
    EXPECT_TRUE(spec->expected_gripper_q6 == 0.707194871 ||
                spec->expected_gripper_q6 == 0.662818811 ||
                spec->expected_gripper_q6 == 1.7);
  }
}

TEST(SO101FixedMotionTargets, ScopesPersistentAndBoundaryTouchPolicies)
{
  spp::SO101FixedMotionTargetPolicy policy;
  const std::set<std::string> expected{"coke:gripper", "coke:jaw"};
  EXPECT_EQ(policy.spec(spp::State::DESCEND)->validation.allowed_touch_pairs, expected);
  EXPECT_TRUE(policy.spec(spp::State::RECOVER_RETREAT)->validation.allowed_touch_pairs.empty());
  EXPECT_TRUE(policy.spec(spp::State::LIFT)->validation.allowed_touch_pairs.empty());
  const auto lift_policy = spp::TemporalContactPolicy{
    {"coke:table"}, spp::TemporalContactLocation::FIRST_ONLY};
  EXPECT_EQ(policy.spec(spp::State::LIFT)->validation.temporal_contact_policy,
            lift_policy);
  EXPECT_EQ(policy.spec(spp::State::LIFT)->target.temporal_contact_policy,
            lift_policy);
  EXPECT_TRUE(policy.spec(spp::State::RECOVER_DESCEND_TO_PICK)->validation.allowed_touch_pairs.empty());
  EXPECT_EQ(policy.spec(spp::State::RECOVER_DESCEND_TO_PICK)->validation.temporal_contact_policy,
            (spp::TemporalContactPolicy{{"coke:table"},
                                        spp::TemporalContactLocation::LAST_ONLY}));
  for (const auto state : {spp::State::RETREAT, spp::State::RECOVER_RETREAT}) {
    EXPECT_EQ(policy.spec(state)->validation.temporal_contact_policy,
              (spp::TemporalContactPolicy{expected,
                spp::TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE, 0.043}));
  }
}

TEST(SO101FixedMotionTargets, UsesFkOptimizedVerticalLaddersNotJointInterpolation)
{
  spp::SO101FixedMotionTargetPolicy policy;
  for (const auto state : {spp::State::DESCEND, spp::State::LIFT,
                           spp::State::DESCEND_TO_PLACE, spp::State::RETREAT,
                           spp::State::RECOVER_LIFT_TO_SAFE_HEIGHT,
                           spp::State::RECOVER_DESCEND_TO_PICK,
                           spp::State::RECOVER_RETREAT}) {
    const auto spec = policy.spec(state);
    ASSERT_TRUE(spec);
    EXPECT_TRUE(spec->target.ladder);
    EXPECT_EQ(spec->target.joint_waypoints.size(), 3U);
  }
}

TEST(SO101FixedMotionTargets, LocksPlaceCoordinatesContinuityQ6AndJointMargins)
{
  spp::SO101FixedMotionTargetPolicy policy;
  const auto above_pick = policy.spec(spp::State::MOVE_ABOVE_OBJECT);
  const auto descend = policy.spec(spp::State::DESCEND);
  const auto lift = policy.spec(spp::State::LIFT);
  const auto above_place = policy.spec(spp::State::MOVE_ABOVE_PLACE);
  const auto place = policy.spec(spp::State::DESCEND_TO_PLACE);
  ASSERT_TRUE(above_pick && descend && lift && above_place && place);
  EXPECT_EQ(above_pick->target.joint_waypoints.back(), descend->logical_start);
  EXPECT_EQ(descend->target.joint_waypoints.back(), lift->logical_start);
  EXPECT_EQ(lift->target.joint_waypoints.back(), above_place->logical_start);
  EXPECT_EQ(above_place->target.joint_waypoints.back(), place->logical_start);
  EXPECT_DOUBLE_EQ(above_place->validation.endpoint_position.x, -0.08);
  EXPECT_DOUBLE_EQ(above_place->validation.endpoint_position.y, -0.25);
  EXPECT_DOUBLE_EQ(place->validation.endpoint_position.x, -0.08);
  EXPECT_DOUBLE_EQ(place->validation.endpoint_position.y, -0.25);
  EXPECT_DOUBLE_EQ(descend->expected_gripper_q6, 0.707194871);
  EXPECT_DOUBLE_EQ(lift->expected_gripper_q6, 0.662818811);
  EXPECT_DOUBLE_EQ(policy.spec(spp::State::RETREAT)->expected_gripper_q6, 1.7);
  EXPECT_DOUBLE_EQ(policy.spec(spp::State::RECOVER_RETREAT)->expected_gripper_q6, 1.7);

  const std::vector<std::pair<double, double>> limits{
    {-1.91986, 1.91986}, {-1.74533, 1.74533}, {-1.74533, 1.5708},
    {-1.65806, 1.65806}, {-2.79253, 2.79253}};
  for (const auto state : {spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND,
                           spp::State::MOVE_ABOVE_PLACE, spp::State::DESCEND_TO_PLACE}) {
    const auto spec = policy.spec(state);
    ASSERT_TRUE(spec);
    for (const auto & waypoint : spec->target.joint_waypoints) {
      for (std::size_t i = 0; i < waypoint.size(); ++i) {
        EXPECT_GT(std::min(waypoint[i] - limits[i].first, limits[i].second - waypoint[i]),
                  0.05) << spp::toString(state) << " joint " << i;
      }
    }
  }
}
