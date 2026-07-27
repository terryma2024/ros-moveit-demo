#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iterator>
#include <map>
#include <set>
#include <sstream>
#include <string>

#include <gtest/gtest.h>
#include <moveit/robot_model_loader/robot_model_loader.hpp>
#include <moveit/robot_state/robot_state.hpp>
#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/so101_fixed_motion_targets.hpp"
#include "so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

std::string readFile(const std::string & path)
{
  std::ifstream stream(path);
  return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

const std::vector<std::vector<double>> kGoldenWaypoints{
  {-0.000074896, 0.406242712, -0.335892969, 1.500452910, -0.029650203},
  {-0.004520982, 0.427298423, -0.219093530, 1.362597749, -0.083117591},
  {-0.000416079, 0.471283543, -0.135531958, 1.235051068, -0.033743502},
  {-0.000011454, 0.536286226, -0.082912794, 1.117429221, -0.028880766},
  {0.331019977, 0.550670543, -0.562313463, 1.582446437, -1.600206428},
  {0.331012586, 0.555338833, -0.421537209, 1.437001892, -1.597230266},
  {0.331041085, 0.592207044, -0.331690813, 1.310287286, -1.607707019},
  {0.331034755, 0.648891100, -0.272710221, 1.194622637, -1.605735287},
};

std::vector<std::vector<double>> calibratedWaypoints(const spp::SO101FixedMotionTargetPolicy & policy)
{
  std::vector<std::vector<double>> result;
  result.push_back(policy.spec(spp::State::MOVE_ABOVE_OBJECT)->target.joint_waypoints.back());
  const auto pick = policy.spec(spp::State::DESCEND)->target.joint_waypoints;
  result.insert(result.end(), pick.begin(), pick.end());
  result.push_back(policy.spec(spp::State::MOVE_ABOVE_PLACE)->target.joint_waypoints.back());
  const auto place = policy.spec(spp::State::DESCEND_TO_PLACE)->target.joint_waypoints;
  result.insert(result.end(), place.begin(), place.end());
  return result;
}

void appendValues(std::ostringstream & out, const std::vector<double> & values)
{
  for (const auto value : values) out << value << ',';
}

std::string policyFingerprint(const spp::SO101FixedMotionTargetPolicy & policy)
{
  std::ostringstream serialized;
  serialized << std::setprecision(17);
  const auto & profile = spp::SO101Profile::canonical();
  for (const auto & pose : {profile.table_pose, profile.coke_pose,
                            profile.place_coke_pose,
                            profile.calibrated_grasp_relative_pose}) {
    serialized << pose.x << ',' << pose.y << ',' << pose.z << ','
               << pose.qx << ',' << pose.qy << ',' << pose.qz << ',' << pose.qw << '|';
  }
  for (const auto state : {spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND,
                           spp::State::LIFT, spp::State::MOVE_ABOVE_PLACE,
                           spp::State::DESCEND_TO_PLACE, spp::State::RETREAT,
                           spp::State::RECOVER_LIFT_TO_SAFE_HEIGHT,
                           spp::State::RECOVER_MOVE_ABOVE_PICK,
                           spp::State::RECOVER_DESCEND_TO_PICK,
                           spp::State::RECOVER_RETREAT}) {
    const auto spec = policy.spec(state);
    EXPECT_TRUE(spec);
    if (!spec) continue;
    serialized << static_cast<int>(state) << '|';
    appendValues(serialized, spec->logical_start);
    serialized << '|';
    for (const auto & waypoint : spec->target.joint_waypoints) {
      appendValues(serialized, waypoint);
      serialized << ';';
    }
    const auto & c = spec->validation;
    serialized << '|' << spec->target.ladder << '|' << spec->target.gripper_position
               << '|' << c.endpoint_position.x << ',' << c.endpoint_position.y << ','
               << c.endpoint_position.z << '|' << c.local_approach_axis.x << ','
               << c.local_approach_axis.y << ',' << c.local_approach_axis.z << '|'
               << c.target_approach_axis.x << ',' << c.target_approach_axis.y << ','
               << c.target_approach_axis.z << '|' << c.path_direction.x << ','
               << c.path_direction.y << ',' << c.path_direction.z << '|'
               << c.position_tolerance << ',' << c.axis_tolerance_rad << ','
               << c.max_lateral_deviation << ',' << c.max_joint_jump << ','
               << c.joint_endpoint_tolerance << ',' << c.min_duration_seconds << ','
               << c.monotonic_tolerance << '|';
    for (const auto & pair : c.allowed_touch_pairs) serialized << pair << ',';
    if (c.temporal_contact_policy) {
      serialized << static_cast<int>(c.temporal_contact_policy->location) << ','
                 << c.temporal_contact_policy->max_axial_clearance_m << ',';
      for (const auto & pair : c.temporal_contact_policy->allowed_pairs) {
        serialized << pair << ',';
      }
    }
    serialized << '\n';
  }
  std::uint64_t hash = 1469598103934665603ULL;
  for (const unsigned char byte : serialized.str()) {
    hash ^= byte;
    hash *= 1099511628211ULL;
  }
  std::ostringstream result;
  result << std::hex << std::setfill('0') << std::setw(16) << hash;
  return result.str();
}

}  // namespace

TEST(SO101FixedMotionTargets, CoversExactTenStatePlanOnlyMatrix)
{
  spp::SO101FixedMotionTargetPolicy policy;
  const std::set<spp::State> states{
    spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND, spp::State::LIFT,
    spp::State::MOVE_ABOVE_PLACE, spp::State::DESCEND_TO_PLACE, spp::State::RETREAT,
    spp::State::RECOVER_LIFT_TO_SAFE_HEIGHT, spp::State::RECOVER_MOVE_ABOVE_PICK,
    spp::State::RECOVER_DESCEND_TO_PICK, spp::State::RECOVER_RETREAT};
  EXPECT_EQ(policy.version(), "so101-fixed-table-d20-v2");
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

TEST(SO101FixedMotionTargets, BindsPolicyVersionToAllMotionConstants)
{
  const spp::SO101FixedMotionTargetPolicy policy;
  const std::map<std::string, std::string> version_to_golden_fingerprint{
    {"so101-fixed-table-d20-v1", "a73316019c50dbe4"},
    {"so101-fixed-table-d20-v2", "7a4e38c05f8d9057"},
  };
  ASSERT_EQ(version_to_golden_fingerprint.count(policy.version()), 1U);
  EXPECT_EQ(policyFingerprint(policy), version_to_golden_fingerprint.at(policy.version()));
}

TEST(SO101FixedMotionTargets, LocksAllEightCalibratedJointVectorsExactly)
{
  spp::SO101FixedMotionTargetPolicy policy;
  EXPECT_EQ(calibratedWaypoints(policy), kGoldenWaypoints);
}

TEST(SO101FixedMotionTargets, RobotModelFkLocksXyzToolAxisAndJointMarginForEveryGoldenWaypoint)
{
  if (!rclcpp::ok()) rclcpp::init(0, nullptr);
  {
  auto node = std::make_shared<rclcpp::Node>("so101_fixed_target_robot_model_test");
  robot_model_loader::RobotModelLoader::Options options(
    readFile(SO101_TEST_URDF), readFile(SO101_TEST_SRDF));
  options.load_kinematics_solvers = false;
  robot_model_loader::RobotModelLoader loader(node, options);
  const auto model = loader.getModel();
  ASSERT_TRUE(model);
  moveit::core::RobotState state(model);
  const auto profile = spp::SO101Profile::canonical();
  const std::vector<spp::Vec3> expected_positions{
    {0.02, -0.28, 0.282}, {0.02, -0.28, 0.262},
    {0.02, -0.28, 0.242}, {0.02, -0.28, 0.222},
    {-0.08, -0.25, 0.282}, {-0.08, -0.25, 0.262},
    {-0.08, -0.25, 0.242}, {-0.08, -0.25, 0.222},
  };
  for (std::size_t index = 0; index < kGoldenWaypoints.size(); ++index) {
    state.setToDefaultValues();
    state.setVariablePositions(profile.arm_joints, kGoldenWaypoints[index]);
    state.setVariablePosition(profile.gripper_joint, profile.q6_preopen);
    state.update();
    const auto & transform = state.getGlobalLinkTransform(profile.tcp_link);
    const Eigen::Quaterniond q(transform.rotation());
    const spp::Pose3d pose{transform.translation().x(), transform.translation().y(),
                           transform.translation().z(), q.x(), q.y(), q.z(), q.w()};
    EXPECT_NEAR(pose.x, expected_positions[index].x, 2e-7) << index;
    EXPECT_NEAR(pose.y, expected_positions[index].y, 2e-7) << index;
    EXPECT_NEAR(pose.z, expected_positions[index].z, 2e-7) << index;
    EXPECT_NEAR(spp::approachAxisError(pose, {0, 0, -1}, {0, 0, -1}), 0.0, 2e-5)
      << index;
    for (std::size_t joint = 0; joint < profile.arm_joints.size(); ++joint) {
      const auto & bounds = model->getVariableBounds(profile.arm_joints[joint]);
      EXPECT_GT(std::min(kGoldenWaypoints[index][joint] - bounds.min_position_,
                         bounds.max_position_ - kGoldenWaypoints[index][joint]), 0.05)
        << index << ":" << joint;
    }
  }
  state.setToDefaultValues();
  state.setVariablePositions(profile.arm_joints, kGoldenWaypoints[3]);
  state.setVariablePosition(profile.gripper_joint, profile.q6_contact);
  state.update();
  Eigen::Isometry3d gripper_coke = Eigen::Isometry3d::Identity();
  const auto & relative = profile.calibrated_grasp_relative_pose;
  gripper_coke.translation() = Eigen::Vector3d(relative.x, relative.y, relative.z);
  gripper_coke.linear() = Eigen::Quaterniond(
    relative.qw, relative.qx, relative.qy, relative.qz).normalized().toRotationMatrix();
  const auto world_coke =
    state.getGlobalLinkTransform(profile.moveit_attach_link) * gripper_coke;
  EXPECT_NEAR(world_coke.translation().x(), profile.coke_pose.x, 2e-6);
  EXPECT_NEAR(world_coke.translation().y(), profile.coke_pose.y, 2e-6);
  EXPECT_NEAR(world_coke.translation().z(), profile.coke_pose.z, 2e-6);
  const Eigen::Quaterniond world_orientation(world_coke.rotation());
  EXPECT_NEAR(std::abs(world_orientation.normalized().w()), 1.0, 2e-6);
  }
}

TEST(SO101MoveItJointPlanningBoundary, UpdatesDirtyRobotStateBeforeReadingLinkPose)
{
  if (!rclcpp::ok()) rclcpp::init(0, nullptr);
  {
  auto node = std::make_shared<rclcpp::Node>("so101_dirty_robot_state_pose_test");
  robot_model_loader::RobotModelLoader::Options options(
    readFile(SO101_TEST_URDF), readFile(SO101_TEST_SRDF));
  options.load_kinematics_solvers = false;
  robot_model_loader::RobotModelLoader loader(node, options);
  const auto model = loader.getModel();
  ASSERT_TRUE(model);
  moveit::core::RobotState dirty(model);
  dirty.setToDefaultValues();
  dirty.update();
  dirty.setVariablePosition("2", 0.25);

  const auto actual = spp::updatedLinkPose(dirty, "gripper");
  ASSERT_TRUE(actual);
  EXPECT_TRUE(std::isfinite(actual->x));
  EXPECT_TRUE(std::isfinite(actual->y));
  EXPECT_TRUE(std::isfinite(actual->z));
  EXPECT_TRUE(std::isfinite(actual->qx));
  EXPECT_TRUE(std::isfinite(actual->qy));
  EXPECT_TRUE(std::isfinite(actual->qz));
  EXPECT_TRUE(std::isfinite(actual->qw));
  EXPECT_FALSE(spp::updatedLinkPose(dirty, "missing_link"));
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
  const auto place_policy = spp::TemporalContactPolicy{
    {"coke:table"}, spp::TemporalContactLocation::LAST_ONLY};
  EXPECT_TRUE(policy.spec(spp::State::DESCEND_TO_PLACE)->validation.allowed_touch_pairs.empty());
  EXPECT_EQ(policy.spec(spp::State::DESCEND_TO_PLACE)->validation.temporal_contact_policy,
            place_policy);
  EXPECT_EQ(policy.spec(spp::State::DESCEND_TO_PLACE)->target.temporal_contact_policy,
            place_policy);
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
