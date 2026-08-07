#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iterator>
#include <map>
#include <set>
#include <sstream>
#include <string>

#include <gtest/gtest.h>
#include <geometric_shapes/shapes.h>
#include <moveit/robot_model_loader/robot_model_loader.hpp>
#include <moveit/robot_state/robot_state.hpp>
#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/so101_fixed_motion_targets.hpp"
#include "so101_gazebo_demo/pick_place/fingertip_pad_gap_calibration_data.hpp"
#include "so101_gazebo_demo/pick_place/policy_config.hpp"
#include "so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

std::string readFile(const std::string & path)
{
  std::ifstream stream(path);
  return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

void writeFile(const std::filesystem::path & path, const std::string & contents)
{
  std::ofstream stream(path, std::ios::binary | std::ios::trunc);
  ASSERT_TRUE(stream) << path;
  stream << contents;
}

std::string replaceOnce(std::string value, const std::string & from, const std::string & to)
{
  const auto position = value.find(from);
  EXPECT_NE(position, std::string::npos) << from;
  if (position != std::string::npos)
    value.replace(position, from.size(), to);
  return value;
}

struct PolicyFiles
{
  explicit PolicyFiles(const std::string & name) :
      root(std::filesystem::temp_directory_path() / ("so101_configured_policy_" + name))
  {
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);
    const std::filesystem::path source(SO101_TEST_POLICY_CONFIG_ROOT);
    writeFile(object(), readFile((source / "task_objects/light_plastic_cup.yaml").string()));
    writeFile(motion(), readFile((source / "motion_policies/light_cup_wall_pick.yaml").string()));
    writeFile(validation(),
              readFile((source / "validation_policies/light_cup_wall_pick.yaml").string()));
  }

  ~PolicyFiles()
  {
    std::filesystem::remove_all(root);
  }

  [[nodiscard]] std::filesystem::path object() const
  {
    return root / "object.yaml";
  }
  [[nodiscard]] std::filesystem::path motion() const
  {
    return root / "motion.yaml";
  }
  [[nodiscard]] std::filesystem::path validation() const
  {
    return root / "validation.yaml";
  }
  [[nodiscard]] spp::PolicyPaths paths() const
  {
    return {object().string(), motion().string(), validation().string()};
  }

  std::filesystem::path root;
};

spp::SO101ConfiguredMotionTargetPolicy configuredPolicy()
{
  const std::filesystem::path root(SO101_TEST_POLICY_CONFIG_ROOT);
  const auto loaded =
    spp::loadPolicyBundle({(root / "task_objects/light_plastic_cup.yaml").string(),
                           (root / "motion_policies/light_cup_wall_pick.yaml").string(),
                           (root / "validation_policies/light_cup_wall_pick.yaml").string()});
  if (!loaded.bundle) {
    throw std::runtime_error(loaded.failure ? loaded.failure->message : "policy load failed");
  }
  return {loaded.bundle->motion, loaded.bundle->validation};
}

spp::SO101Profile configuredProfile()
{
  const std::filesystem::path root(SO101_TEST_POLICY_CONFIG_ROOT);
  const auto loaded =
    spp::loadPolicyBundle({(root / "task_objects/light_plastic_cup.yaml").string(),
                           (root / "motion_policies/light_cup_wall_pick.yaml").string(),
                           (root / "validation_policies/light_cup_wall_pick.yaml").string()});
  if (!loaded.bundle) {
    throw std::runtime_error(loaded.failure ? loaded.failure->message : "policy load failed");
  }
  return spp::SO101Profile::configured(loaded.bundle->object, loaded.bundle->motion,
                                       loaded.bundle->validation);
}

const std::vector<std::vector<double>> kGoldenWaypoints{
  {-0.000282114209, 0.200965792445, 0.129655454807, 1.240181404713, -0.000289555209},
  {-0.000276912349, 0.287984861834, 0.150788067636, 1.132029723496, -0.000284352650},
  {-0.000283745683, 0.253568199427, 0.213237198063, 1.103997256470, -0.000291185985},
  {-0.000283936540, 0.312943337339, 0.250048785615, 1.007810530006, -0.000291376841},
  {-0.000284124852, 0.381814591288, 0.272246878070, 0.916741182602, -0.000291565154},
  {-0.000206491845, 0.472194274096, 0.214652624195, 0.854922375695, 0.000576703465},
  {0.414521193913, 0.179437354347, 0.140117134131, 1.230305282671, -0.000268782932},
  {0.412761019553, 0.231656466651, 0.201890961785, 1.116312343800, -0.000268760093},
  {0.410549243529, 0.284379863507, 0.263091668828, 1.002388239890, -0.000268760311},
  {0.407916176553, 0.360728562196, 0.333930438812, 0.849391852381, 0.000527139337},
};

std::vector<std::vector<double>>
calibratedWaypoints(const spp::SO101FixedMotionTargetPolicy & policy)
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
  for (const auto value : values)
    out << value << ',';
}

std::string policyFingerprint(const spp::SO101FixedMotionTargetPolicy & policy)
{
  std::ostringstream serialized;
  serialized << std::setprecision(17);
  const auto & profile = spp::SO101Profile::canonical();
  for (const auto & pose :
       {profile.table_pose, profile.task_object_pose, profile.place_task_object_pose,
        profile.calibrated_grasp_relative_pose}) {
    serialized << pose.x << ',' << pose.y << ',' << pose.z << ',' << pose.qx << ',' << pose.qy
               << ',' << pose.qz << ',' << pose.qw << '|';
  }
  for (const auto state :
       {spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND, spp::State::LIFT,
        spp::State::MOVE_ABOVE_PLACE, spp::State::DESCEND_TO_PLACE, spp::State::RETREAT,
        spp::State::RECOVER_LIFT_TO_SAFE_HEIGHT, spp::State::RECOVER_MOVE_ABOVE_PICK,
        spp::State::RECOVER_DESCEND_TO_PICK, spp::State::RECOVER_RETREAT}) {
    const auto spec = policy.spec(state);
    EXPECT_TRUE(spec);
    if (!spec)
      continue;
    serialized << static_cast<int>(state) << '|';
    appendValues(serialized, spec->logical_start);
    serialized << '|';
    for (const auto & waypoint : spec->target.joint_waypoints) {
      appendValues(serialized, waypoint);
      serialized << ';';
    }
    const auto & c = spec->validation;
    serialized << '|' << spec->target.ladder << '|' << spec->target.gripper_position << '|'
               << c.endpoint_position.x << ',' << c.endpoint_position.y << ','
               << c.endpoint_position.z << '|' << c.local_approach_axis.x << ','
               << c.local_approach_axis.y << ',' << c.local_approach_axis.z << '|'
               << c.target_approach_axis.x << ',' << c.target_approach_axis.y << ','
               << c.target_approach_axis.z << '|' << c.path_direction.x << ',' << c.path_direction.y
               << ',' << c.path_direction.z << '|' << c.position_tolerance << ','
               << c.axis_tolerance_rad << ',' << c.max_lateral_deviation << ',' << c.max_joint_jump
               << ',' << c.joint_endpoint_tolerance << ',' << c.min_duration_seconds << ','
               << c.monotonic_tolerance << '|';
    for (const auto & pair : c.allowed_touch_pairs)
      serialized << pair << ',';
    if (c.temporal_contact_policy) {
      serialized << static_cast<int>(c.temporal_contact_policy->location) << ','
                 << c.temporal_contact_policy->max_axial_clearance_m << ',';
      for (const auto & pair : c.temporal_contact_policy->allowed_pairs) {
        serialized << pair << ',';
      }
    }
    serialized << "|target-temporal:";
    if (spec->target.temporal_contact_policy) {
      serialized << static_cast<int>(spec->target.temporal_contact_policy->location) << ','
                 << spec->target.temporal_contact_policy->max_axial_clearance_m << ',';
      for (const auto & pair : spec->target.temporal_contact_policy->allowed_pairs) {
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

TEST(SO101ConfiguredMotionTargets, MotionYamlQ6ChangesTargetWithoutChangingBinary)
{
  PolicyFiles first("q6_first");
  PolicyFiles second("q6_second");
  writeFile(second.motion(), replaceOnce(readFile(second.motion().string()),
                                         "gripper_q6: 0.465038000", "gripper_q6: 0.475038000"));
  const auto first_bundle = spp::loadPolicyBundle(first.paths());
  const auto second_bundle = spp::loadPolicyBundle(second.paths());
  ASSERT_TRUE(first_bundle.bundle);
  ASSERT_TRUE(second_bundle.bundle);

  const spp::SO101ConfiguredMotionTargetPolicy first_policy(first_bundle.bundle->motion,
                                                            first_bundle.bundle->validation);
  const spp::SO101ConfiguredMotionTargetPolicy second_policy(second_bundle.bundle->motion,
                                                             second_bundle.bundle->validation);

  ASSERT_TRUE(first_policy.spec(spp::State::MOVE_ABOVE_OBJECT));
  ASSERT_TRUE(second_policy.spec(spp::State::MOVE_ABOVE_OBJECT));
  EXPECT_DOUBLE_EQ(first_policy.spec(spp::State::MOVE_ABOVE_OBJECT)->target.gripper_position,
                   0.465038);
  EXPECT_DOUBLE_EQ(second_policy.spec(spp::State::MOVE_ABOVE_OBJECT)->target.gripper_position,
                   0.475038);
  EXPECT_NE(first_bundle.bundle->bundle_sha256, second_bundle.bundle->bundle_sha256);
}

TEST(SO101ConfiguredMotionTargets, RetreatUsesValidatedLowSpeedDynamics)
{
  const auto policy = configuredPolicy();

  const auto retreat = policy.spec(spp::State::RETREAT);
  const auto recovery = policy.spec(spp::State::RECOVER_RETREAT);

  ASSERT_TRUE(retreat);
  ASSERT_TRUE(recovery);
  EXPECT_DOUBLE_EQ(retreat->target.velocity_scaling, 0.03);
  EXPECT_DOUBLE_EQ(retreat->target.acceleration_scaling, 0.03);
  EXPECT_DOUBLE_EQ(recovery->target.velocity_scaling, 0.03);
  EXPECT_DOUBLE_EQ(recovery->target.acceleration_scaling, 0.03);
}

TEST(SO101ConfiguredMotionTargets, ValidationYamlToleranceChangesValidatorWithoutChangingBinary)
{
  PolicyFiles first("validation_first");
  PolicyFiles second("validation_second");
  writeFile(second.validation(),
            replaceOnce(readFile(second.validation().string()), "position_tolerance_m: 0.005",
                        "position_tolerance_m: 0.007"));
  const auto first_bundle = spp::loadPolicyBundle(first.paths());
  const auto second_bundle = spp::loadPolicyBundle(second.paths());
  ASSERT_TRUE(first_bundle.bundle);
  ASSERT_TRUE(second_bundle.bundle);

  const spp::SO101ConfiguredMotionTargetPolicy first_policy(first_bundle.bundle->motion,
                                                            first_bundle.bundle->validation);
  const spp::SO101ConfiguredMotionTargetPolicy second_policy(second_bundle.bundle->motion,
                                                             second_bundle.bundle->validation);

  ASSERT_TRUE(first_policy.spec(spp::State::MOVE_ABOVE_OBJECT));
  ASSERT_TRUE(second_policy.spec(spp::State::MOVE_ABOVE_OBJECT));
  EXPECT_DOUBLE_EQ(first_policy.spec(spp::State::MOVE_ABOVE_OBJECT)->validation.position_tolerance,
                   0.005);
  EXPECT_DOUBLE_EQ(second_policy.spec(spp::State::MOVE_ABOVE_OBJECT)->validation.position_tolerance,
                   0.007);
  EXPECT_NE(first_bundle.bundle->bundle_sha256, second_bundle.bundle->bundle_sha256);
}

TEST(SO101FixedMotionTargets, CoversExactTenStatePlanOnlyMatrix)
{
  const auto policy = configuredPolicy();
  const std::set<spp::State> states{spp::State::MOVE_ABOVE_OBJECT,
                                    spp::State::DESCEND,
                                    spp::State::LIFT,
                                    spp::State::MOVE_ABOVE_PLACE,
                                    spp::State::DESCEND_TO_PLACE,
                                    spp::State::RETREAT,
                                    spp::State::RECOVER_LIFT_TO_SAFE_HEIGHT,
                                    spp::State::RECOVER_MOVE_ABOVE_PICK,
                                    spp::State::RECOVER_DESCEND_TO_PICK,
                                    spp::State::RECOVER_RETREAT};
  EXPECT_EQ(policy.version(), "light_cup_wall_pick");
  for (const auto state : states) {
    const auto spec = policy.spec(state);
    ASSERT_TRUE(spec) << spp::toString(state);
    EXPECT_EQ(spec->logical_start.size(), 5U);
    EXPECT_EQ(spec->target.joint_names, (std::vector<std::string>{"1", "2", "3", "4", "5"}));
    EXPECT_FALSE(spec->target.joint_waypoints.empty());
    EXPECT_TRUE(spec->expected_gripper_q6 == 0.465038000 ||
                spec->expected_gripper_q6 == spp::fingertip_pad_calibration::kGraspQ6 ||
                spec->expected_gripper_q6 == 0.750);
  }
}

TEST(SO101FixedMotionTargets, UsesConfiguredPolicyIdentifier)
{
  const auto policy = configuredPolicy();
  EXPECT_EQ(policy.version(), "light_cup_wall_pick");
}

TEST(SO101FixedMotionTargets, DetachedRobotStateDoesNotEmitMissingAttachedBodyError)
{
  if (!rclcpp::ok())
    rclcpp::init(0, nullptr);
  auto node = std::make_shared<rclcpp::Node>("so101_detached_body_lookup_test");
  robot_model_loader::RobotModelLoader::Options options(readFile(SO101_TEST_URDF),
                                                        readFile(SO101_TEST_SRDF));
  options.load_kinematics_solvers = false;
  robot_model_loader::RobotModelLoader loader(node, options);
  const auto & model = loader.getModel();
  ASSERT_TRUE(model);
  moveit::core::RobotState state(model);
  state.setToDefaultValues();
  state.update();

  testing::internal::CaptureStderr();
  const auto pose = spp::updatedAttachedBodyPose(state, "plastic_cup");
  const auto stderr_output = testing::internal::GetCapturedStderr();

  EXPECT_FALSE(pose);
  EXPECT_EQ(stderr_output.find("does not have attached body"), std::string::npos);
}

TEST(SO101FixedMotionTargets, AttachedObjectEvidenceUsesObjectFrameNotFirstCollisionPrimitive)
{
  if (!rclcpp::ok())
    rclcpp::init(0, nullptr);
  auto node = std::make_shared<rclcpp::Node>("so101_attached_object_frame_test");
  robot_model_loader::RobotModelLoader::Options options(readFile(SO101_TEST_URDF),
                                                        readFile(SO101_TEST_SRDF));
  options.load_kinematics_solvers = false;
  robot_model_loader::RobotModelLoader loader(node, options);
  const auto & model = loader.getModel();
  ASSERT_TRUE(model);
  moveit::core::RobotState state(model);
  state.setToDefaultValues();
  state.update();
  Eigen::Isometry3d object_pose = Eigen::Isometry3d::Identity();
  object_pose.translation() = Eigen::Vector3d(0.01, -0.02, 0.03);
  Eigen::Isometry3d collision_offset = Eigen::Isometry3d::Identity();
  collision_offset.translation() = Eigen::Vector3d(0.04, 0.0, 0.0);
  state.attachBody("plastic_cup", object_pose,
                   {std::make_shared<const shapes::Box>(0.01, 0.01, 0.01)}, {collision_offset},
                   std::set<std::string>{"gripper"}, "gripper");
  state.update();
  const auto * attached = state.getAttachedBody("plastic_cup");
  ASSERT_NE(attached, nullptr);

  const auto pose = spp::updatedAttachedBodyPose(state, "plastic_cup");

  ASSERT_TRUE(pose);
  const auto & expected = attached->getGlobalPose().translation();
  EXPECT_NEAR(pose->x, expected.x(), 1e-12);
  EXPECT_NEAR(pose->y, expected.y(), 1e-12);
  EXPECT_NEAR(pose->z, expected.z(), 1e-12);
}

TEST(SO101FixedMotionTargets, LocksAllTenCalibratedJointVectorsExactly)
{
  const auto policy = configuredPolicy();
  EXPECT_EQ(calibratedWaypoints(policy), kGoldenWaypoints);
}

TEST(SO101FixedMotionTargets, RobotModelFkLocksXyzToolAxisAndJointMarginForEveryGoldenWaypoint)
{
  if (!rclcpp::ok())
    rclcpp::init(0, nullptr);
  {
    auto node = std::make_shared<rclcpp::Node>("so101_fixed_target_robot_model_test");
    robot_model_loader::RobotModelLoader::Options options(readFile(SO101_TEST_URDF),
                                                          readFile(SO101_TEST_SRDF));
    options.load_kinematics_solvers = false;
    robot_model_loader::RobotModelLoader loader(node, options);
    const auto & model = loader.getModel();
    ASSERT_TRUE(model);
    moveit::core::RobotState state(model);
    const auto profile = configuredProfile();
    const std::vector<spp::Vec3> expected_positions{
      {0.020673898, -0.254062366, 0.259792378},  {0.020673884, -0.258022783, 0.241331096},
      {0.020673885, -0.253024373, 0.239831664},  {0.020673885, -0.253024210, 0.224832847},
      {0.020673884, -0.253024034, 0.210034129},  {0.020676684, -0.262821021, 0.200630611},
      {-0.072885185, -0.235515275, 0.262755728}, {-0.072653526, -0.236004954, 0.245614538},
      {-0.071642733, -0.234971310, 0.228845176}, {-0.070033365, -0.232824468, 0.207660672},
    };
    for (std::size_t index = 0; index < kGoldenWaypoints.size(); ++index) {
      state.setToDefaultValues();
      state.setVariablePositions(profile.arm_joints, kGoldenWaypoints[index]);
      state.setVariablePosition(profile.gripper_joint, profile.q6_preopen);
      state.update();
      const auto & transform = state.getGlobalLinkTransform(profile.tcp_link);
      const Eigen::Quaterniond q(transform.rotation());
      const spp::Pose3d pose{transform.translation().x(),
                             transform.translation().y(),
                             transform.translation().z(),
                             q.x(),
                             q.y(),
                             q.z(),
                             q.w()};
      EXPECT_NEAR(pose.x, expected_positions[index].x, 2e-7) << index;
      EXPECT_NEAR(pose.y, expected_positions[index].y, 2e-7) << index;
      EXPECT_NEAR(pose.z, expected_positions[index].z, 2e-7) << index;
      const double expected_tilt = index == 5   ? 0.029033379064
                                   : index == 9 ? 0.026752852892
                                   : index > 5  ? 0.020943951205
                                                : 0.0;
      EXPECT_NEAR(spp::approachAxisError(pose, {0, 0, -1}, {0, 0, -1}), expected_tilt, 2e-5)
        << index;
      for (std::size_t joint = 0; joint < profile.arm_joints.size(); ++joint) {
        const auto & bounds = model->getVariableBounds(profile.arm_joints[joint]);
        EXPECT_GT(std::min(kGoldenWaypoints[index][joint] - bounds.min_position_,
                           bounds.max_position_ - kGoldenWaypoints[index][joint]),
                  0.05)
          << index << ":" << joint;
      }
    }
    state.setToDefaultValues();
    state.setVariablePositions(profile.arm_joints, kGoldenWaypoints[5]);
    state.setVariablePosition(profile.gripper_joint, profile.q6_contact);
    state.update();
    Eigen::Isometry3d gripper_task_object = Eigen::Isometry3d::Identity();
    const auto & relative = profile.calibrated_grasp_relative_pose;
    gripper_task_object.translation() = Eigen::Vector3d(relative.x, relative.y, relative.z);
    gripper_task_object.linear() =
      Eigen::Quaterniond(relative.qw, relative.qx, relative.qy, relative.qz)
        .normalized()
        .toRotationMatrix();
    const auto world_task_object =
      state.getGlobalLinkTransform(profile.moveit_attach_link) * gripper_task_object;
    Eigen::Isometry3d desired_world_task_object = Eigen::Isometry3d::Identity();
    desired_world_task_object.translation() = Eigen::Vector3d(
      profile.task_object_pose.x, profile.task_object_pose.y, profile.task_object_pose.z);
    desired_world_task_object.linear() =
      Eigen::Quaterniond(profile.task_object_pose.qw, profile.task_object_pose.qx,
                         profile.task_object_pose.qy, profile.task_object_pose.qz)
        .normalized()
        .toRotationMatrix();
    const auto gentle_relative =
      state.getGlobalLinkTransform(profile.moveit_attach_link).inverse() *
      desired_world_task_object;
    const Eigen::Quaterniond gentle_relative_q(gentle_relative.rotation());
    std::cerr << std::setprecision(15) << "[GENTLE-ATTACH-RELATIVE] xyz_xyzw=["
              << gentle_relative.translation().x() << ", " << gentle_relative.translation().y()
              << ", " << gentle_relative.translation().z() << ", " << gentle_relative_q.x() << ", "
              << gentle_relative_q.y() << ", " << gentle_relative_q.z() << ", "
              << gentle_relative_q.w() << "]\n";
    EXPECT_NEAR(world_task_object.translation().x(), profile.task_object_pose.x, 2e-6);
    // The runtime-validated gentle entry uses an FK-bound attachment transform,
    // so attachment does not teleport the cup after physical contact succeeds.
    EXPECT_NEAR(world_task_object.translation().y(), profile.task_object_pose.y, 2e-6);
    EXPECT_NEAR(world_task_object.translation().z(), profile.task_object_pose.z, 2e-6);
    EXPECT_LE((world_task_object.translation() - Eigen::Vector3d(profile.task_object_pose.x,
                                                                 profile.task_object_pose.y,
                                                                 profile.task_object_pose.z))
                .norm(),
              0.003);
    const Eigen::Quaterniond world_orientation(world_task_object.rotation());
    EXPECT_NEAR(std::abs(world_orientation.normalized().w()), 1.0, 2e-6);
    EXPECT_NEAR(world_task_object.linear().col(2).dot(Eigen::Vector3d::UnitZ()), 1.0, 2e-6);
    const double table_top_z = profile.table_pose.z + profile.table_size[2] / 2.0;
    const Eigen::Vector3d pick_bottom_center =
      world_task_object *
      Eigen::Vector3d(
        0.0, 0.0, -profile.task_object_height / 2.0 + profile.task_object_bottom_thickness / 2.0);
    EXPECT_GE(pick_bottom_center.z() - profile.task_object_bottom_thickness / 2.0 - table_top_z,
              -2e-6);

    // The place endpoint uses the real gripper FK and the full calibrated SE(3)
    // attachment.  Its cup bottom is a finite cylinder: account for both the
    // bottom disc radius and the attachment orientation before comparing it to
    // the table.  A scalar TCP-to-cup z offset is invalid once orientation moves.
    state.setToDefaultValues();
    state.setVariablePositions(profile.arm_joints, kGoldenWaypoints.back());
    state.setVariablePosition(profile.gripper_joint, profile.q6_contact);
    state.update();
    const auto placed_task_object =
      state.getGlobalLinkTransform(profile.moveit_attach_link) * gripper_task_object;
    EXPECT_NEAR(placed_task_object.translation().x(), -0.077441044414, 2e-6);
    EXPECT_NEAR(placed_task_object.translation().y(), -0.248248951915, 2e-6);
    EXPECT_NEAR(placed_task_object.translation().z(), 0.171990975872, 2e-6);
    const Eigen::Quaterniond placed_orientation(placed_task_object.rotation());
    EXPECT_NEAR(placed_orientation.normalized().z(), -0.202672188771, 2e-6);
    EXPECT_NEAR(std::abs(placed_orientation.normalized().w()), 0.979245977116, 2e-6);
    const Eigen::Vector3d cup_axis = placed_task_object.linear().col(2);
    EXPECT_NEAR(cup_axis.dot(Eigen::Vector3d::UnitZ()), 0.999997399600, 2e-6);
    const Eigen::Vector3d bottom_center =
      placed_task_object *
      Eigen::Vector3d(
        0.0, 0.0, -profile.task_object_height / 2.0 + profile.task_object_bottom_thickness / 2.0);
    const double bottom_lowest_z =
      bottom_center.z() -
      profile.task_object_outer_radius * std::hypot(cup_axis.x(), cup_axis.y()) -
      profile.task_object_bottom_thickness / 2.0 * std::abs(cup_axis.z());
    EXPECT_GE(bottom_lowest_z - table_top_z, 0.0025 - 2e-6);
  }
}

TEST(SO101MoveItJointPlanningBoundary, UpdatesDirtyRobotStateBeforeReadingLinkPose)
{
  if (!rclcpp::ok())
    rclcpp::init(0, nullptr);
  {
    auto node = std::make_shared<rclcpp::Node>("so101_dirty_robot_state_pose_test");
    robot_model_loader::RobotModelLoader::Options options(readFile(SO101_TEST_URDF),
                                                          readFile(SO101_TEST_SRDF));
    options.load_kinematics_solvers = false;
    robot_model_loader::RobotModelLoader loader(node, options);
    const auto & model = loader.getModel();
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

TEST(SO101MoveItJointPlanningBoundary, UsesTaskObjectFirstInExactTouchWhitelist)
{
  const auto profile = spp::SO101Profile::canonical();
  const std::set<std::string> expected{"plastic_cup:gripper", "plastic_cup:jaw"};
  EXPECT_EQ(spp::exactTaskObjectTouchWhitelist(profile), expected);
}

TEST(SO101FixedMotionTargets, ScopesPersistentAndBoundaryTouchPolicies)
{
  const auto policy = configuredPolicy();
  EXPECT_TRUE(policy.spec(spp::State::DESCEND)->validation.allowed_touch_pairs.empty());
  EXPECT_TRUE(policy.spec(spp::State::RECOVER_RETREAT)->validation.allowed_touch_pairs.empty());
  EXPECT_TRUE(policy.spec(spp::State::LIFT)->validation.allowed_touch_pairs.empty());
  const auto lift_policy =
    spp::TemporalContactPolicy{{"plastic_cup:table"},
                               spp::TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE,
                               0.012};
  EXPECT_EQ(policy.spec(spp::State::LIFT)->validation.temporal_contact_policy, lift_policy);
  EXPECT_EQ(policy.spec(spp::State::LIFT)->target.temporal_contact_policy, lift_policy);
  const auto place_policy =
    spp::TemporalContactPolicy{{"plastic_cup:table"}, spp::TemporalContactLocation::LAST_ONLY};
  EXPECT_TRUE(policy.spec(spp::State::DESCEND_TO_PLACE)->validation.allowed_touch_pairs.empty());
  EXPECT_EQ(policy.spec(spp::State::DESCEND_TO_PLACE)->validation.temporal_contact_policy,
            place_policy);
  EXPECT_EQ(policy.spec(spp::State::DESCEND_TO_PLACE)->target.temporal_contact_policy,
            place_policy);
  EXPECT_TRUE(
    policy.spec(spp::State::RECOVER_DESCEND_TO_PICK)->validation.allowed_touch_pairs.empty());
  EXPECT_EQ(
    policy.spec(spp::State::RECOVER_DESCEND_TO_PICK)->validation.temporal_contact_policy,
    (spp::TemporalContactPolicy{{"plastic_cup:table"}, spp::TemporalContactLocation::LAST_ONLY}));
  EXPECT_EQ(policy.spec(spp::State::RETREAT)->validation.temporal_contact_policy,
            (spp::TemporalContactPolicy{{"plastic_cup:gripper", "plastic_cup:jaw"},
                                        spp::TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE,
                                        0.0044}));
  EXPECT_EQ(policy.spec(spp::State::RECOVER_RETREAT)->validation.temporal_contact_policy,
            (spp::TemporalContactPolicy{{"plastic_cup:gripper", "plastic_cup:jaw"},
                                        spp::TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE,
                                        0.043}));
}

TEST(SO101FixedMotionTargets, UsesFkOptimizedVerticalLaddersNotJointInterpolation)
{
  const auto policy = configuredPolicy();
  for (const auto state : {spp::State::DESCEND, spp::State::LIFT, spp::State::DESCEND_TO_PLACE,
                           spp::State::RETREAT, spp::State::RECOVER_LIFT_TO_SAFE_HEIGHT,
                           spp::State::RECOVER_DESCEND_TO_PICK, spp::State::RECOVER_RETREAT}) {
    const auto spec = policy.spec(state);
    ASSERT_TRUE(spec);
    EXPECT_TRUE(spec->target.ladder);
    const bool pick_dogleg =
      state == spp::State::LIFT || state == spp::State::DESCEND || state == spp::State::RETREAT ||
      state == spp::State::RECOVER_DESCEND_TO_PICK || state == spp::State::RECOVER_RETREAT;
    const std::size_t expected_waypoints =
      state == spp::State::RETREAT ? 6U : (pick_dogleg ? 5U : 3U);
    EXPECT_EQ(spec->target.joint_waypoints.size(), expected_waypoints);
  }
}

TEST(SO101FixedMotionTargets, SeparatesTransferWaypointPlanningFromAxialPathValidation)
{
  const auto policy = configuredPolicy();
  for (const auto state : {spp::State::MOVE_ABOVE_OBJECT, spp::State::MOVE_ABOVE_PLACE,
                           spp::State::RECOVER_MOVE_ABOVE_PICK, spp::State::RETREAT}) {
    const auto spec = policy.spec(state);
    ASSERT_TRUE(spec);
    EXPECT_FALSE(spec->require_axial_path_validation) << spp::toString(state);
  }
  for (const auto state : {spp::State::DESCEND, spp::State::LIFT, spp::State::DESCEND_TO_PLACE,
                           spp::State::RECOVER_LIFT_TO_SAFE_HEIGHT,
                           spp::State::RECOVER_DESCEND_TO_PICK, spp::State::RECOVER_RETREAT}) {
    const auto spec = policy.spec(state);
    ASSERT_TRUE(spec);
    EXPECT_TRUE(spec->target.ladder) << spp::toString(state);
    EXPECT_TRUE(spec->require_axial_path_validation) << spp::toString(state);
  }
}

TEST(SO101FixedMotionTargets, LocksPlaceCoordinatesContinuityQ6AndJointMargins)
{
  const auto policy = configuredPolicy();
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
  EXPECT_DOUBLE_EQ(above_place->validation.endpoint_position.x, -0.072885185);
  EXPECT_DOUBLE_EQ(above_place->validation.endpoint_position.y, -0.235515275);
  EXPECT_DOUBLE_EQ(place->validation.endpoint_position.x, -0.069889681);
  EXPECT_DOUBLE_EQ(place->validation.endpoint_position.y, -0.232459408);
  EXPECT_DOUBLE_EQ(descend->expected_gripper_q6, 0.465038000);
  EXPECT_DOUBLE_EQ(lift->expected_gripper_q6, spp::fingertip_pad_calibration::kGraspQ6);
  EXPECT_DOUBLE_EQ(policy.spec(spp::State::RETREAT)->expected_gripper_q6, 0.750);
  EXPECT_DOUBLE_EQ(policy.spec(spp::State::RECOVER_RETREAT)->expected_gripper_q6, 0.750);

  const std::vector<std::pair<double, double>> limits{{-1.91986, 1.91986},
                                                      {-1.74533, 1.74533},
                                                      {-1.74533, 1.5708},
                                                      {-1.65806, 1.65806},
                                                      {-2.79253, 2.79253}};
  for (const auto state : {spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND,
                           spp::State::MOVE_ABOVE_PLACE, spp::State::DESCEND_TO_PLACE}) {
    const auto spec = policy.spec(state);
    ASSERT_TRUE(spec);
    for (const auto & waypoint : spec->target.joint_waypoints) {
      for (std::size_t i = 0; i < waypoint.size(); ++i) {
        EXPECT_GT(std::min(waypoint[i] - limits[i].first, limits[i].second - waypoint[i]), 0.05)
          << spp::toString(state) << " joint " << i;
      }
    }
  }
}

TEST(SO101FixedMotionTargets, UsesOutsideAboveLaneAndSeatedNearWallEndpoint)
{
  const auto policy = configuredPolicy();
  const auto above = policy.spec(spp::State::MOVE_ABOVE_OBJECT);
  const auto descend = policy.spec(spp::State::DESCEND);
  const auto place = policy.spec(spp::State::DESCEND_TO_PLACE);
  ASSERT_TRUE(above && descend && place);

  // These are so101_tcp validation coordinates, obtained by FK through the
  // fixed gripper-to-TCP transform.  They deliberately are not the gripper-
  // origin contact-face coordinates used by the pad/wall geometry audit.
  constexpr double pick_tcp_x = 0.020673889;
  constexpr double precontact_tcp_x = 0.020676683784;
  constexpr double outside_tcp_y = -0.254030551;
  constexpr double precontact_tcp_y = -0.262821021238;
  constexpr double place_tcp_x = -0.069889681;
  constexpr double place_tcp_y = -0.232459408;
  EXPECT_DOUBLE_EQ(above->validation.endpoint_position.x, pick_tcp_x);
  EXPECT_DOUBLE_EQ(descend->validation.endpoint_position.x, precontact_tcp_x);
  EXPECT_DOUBLE_EQ(place->validation.endpoint_position.x, place_tcp_x);
  EXPECT_NEAR(above->validation.endpoint_position.y, outside_tcp_y, 1e-9);
  EXPECT_NEAR(descend->validation.endpoint_position.y, precontact_tcp_y, 1e-9);
  EXPECT_NEAR(place->validation.endpoint_position.y, place_tcp_y, 1e-9);
}

TEST(SO101FixedMotionTargets, UsesValidatedGentlePregraspAndFiftyMillimetreLift)
{
  const auto policy = configuredPolicy();
  const auto above = policy.spec(spp::State::MOVE_ABOVE_OBJECT);
  const auto descend = policy.spec(spp::State::DESCEND);
  const auto lift = policy.spec(spp::State::LIFT);
  const auto above_place = policy.spec(spp::State::MOVE_ABOVE_PLACE);
  const auto place = policy.spec(spp::State::DESCEND_TO_PLACE);
  const auto recover_descend = policy.spec(spp::State::RECOVER_DESCEND_TO_PICK);
  ASSERT_TRUE(above && descend && lift && above_place && place && recover_descend);

  EXPECT_NEAR(above->validation.endpoint_position.z - descend->validation.endpoint_position.z,
              0.059206598416, 2e-9);
  EXPECT_GE(lift->validation.endpoint_position.z - descend->validation.endpoint_position.z,
            0.050 - 3e-9);
  EXPECT_GE(above_place->validation.endpoint_position.z - place->validation.endpoint_position.z,
            0.050);
  EXPECT_DOUBLE_EQ(recover_descend->validation.endpoint_position.x,
                   descend->validation.endpoint_position.x);
  EXPECT_DOUBLE_EQ(recover_descend->validation.endpoint_position.y,
                   descend->validation.endpoint_position.y);
  EXPECT_DOUBLE_EQ(recover_descend->validation.endpoint_position.z,
                   descend->validation.endpoint_position.z);
}

TEST(SO101FixedMotionTargets, VerifiesGoldenFkAndPrintsRetreatTargetForComputeIk)
{
  if (!rclcpp::ok())
    rclcpp::init(0, nullptr);
  auto node = std::make_shared<rclcpp::Node>("so101_cp30_fk_probe");
  robot_model_loader::RobotModelLoader::Options options(readFile(SO101_TEST_URDF),
                                                        readFile(SO101_TEST_SRDF));
  options.load_kinematics_solvers = false;
  robot_model_loader::RobotModelLoader loader(node, options);
  const auto & model = loader.getModel();
  ASSERT_TRUE(model);
  moveit::core::RobotState state(model);
  const auto profile = configuredProfile();

  // Golden DESCEND vectors: outside logical start, +8-mm lane, then below-rim seating.
  const std::vector<std::vector<double>> descend_golden{
    {-0.000282114209, 0.200965792445, 0.129655454807, 1.240181404713, -0.000289555209},
    {-0.000276912349, 0.287984861834, 0.150788067636, 1.132029723496, -0.000284352650},
    {-0.000283745683, 0.253568199427, 0.213237198063, 1.103997256470, -0.000291185985},
    {-0.000283936540, 0.312943337339, 0.250048785615, 1.007810530006, -0.000291376841},
    {-0.000284124852, 0.381814591288, 0.272246878070, 0.916741182602, -0.000291565154},
    {-0.000272729232, 0.468371565456, 0.176832790859, 0.925598296383, -0.000280169534},
  };
  const std::vector<spp::Vec3> expected_tcp{
    {0.020673898, -0.254062366, 0.259792378}, {0.020673884, -0.258022783, 0.241331096},
    {0.020673885, -0.253024373, 0.239831664}, {0.020673885, -0.253024210, 0.224832847},
    {0.020673884, -0.253024034, 0.210034129}, {0.020673892, -0.261584688, 0.204789143},
  };

  // Step 1: verify real-model FK reproduces golden TCP for all five DESCEND joint vectors.
  std::vector<Eigen::Isometry3d> poses;
  for (std::size_t i = 0; i < descend_golden.size(); ++i) {
    state.setToDefaultValues();
    state.setVariablePositions(profile.arm_joints, descend_golden[i]);
    state.setVariablePosition(profile.gripper_joint, profile.q6_preopen);
    state.update();
    const auto & transform = state.getGlobalLinkTransform(profile.tcp_link);
    poses.emplace_back(transform);
    EXPECT_NEAR(poses.back().translation().x(), expected_tcp[i].x, 1e-6)
      << "FK X mismatch at index " << i;
    EXPECT_NEAR(poses.back().translation().y(), expected_tcp[i].y, 1e-6)
      << "FK Y mismatch at index " << i;
    EXPECT_NEAR(poses.back().translation().z(), expected_tcp[i].z, 1e-6)
      << "FK Z mismatch at index " << i;
    const Eigen::Quaterniond q(poses.back().rotation());
    std::cerr << std::setprecision(12) << "[FK] index=" << i << " xyz=["
              << poses.back().translation().x() << ", " << poses.back().translation().y() << ", "
              << poses.back().translation().z() << "]" << " qxyzw=[" << q.x() << ", " << q.y()
              << ", " << q.z() << ", " << q.w() << "]\n";
  }

  // Step 2: compute retreat target pose for the /compute_ik service.
  // wall_near outward normal = +Y world.  "Away from wall" = -Y.
  // Interpolate position at 30% from start toward endpoint, shift -4mm in Y.
  // Keep orientation from the start pose (DESCEND maintains approach axis -Z).
  constexpr double interp_t = 0.30;
  constexpr double retreat_dy = -0.004;
  Eigen::Vector3d start_pos = poses[0].translation();
  Eigen::Vector3d end_pos = poses[4].translation();
  Eigen::Vector3d target_pos = start_pos + interp_t * (end_pos - start_pos);
  target_pos.y() += retreat_dy;
  Eigen::Isometry3d target_pose = poses[0];
  target_pose.translation() = target_pos;
  const Eigen::Quaterniond target_q(target_pose.rotation());

  std::cerr << std::setprecision(12) << "[RETREAT-TARGET] xyz=[" << target_pos.x() << ", "
            << target_pos.y() << ", " << target_pos.z() << "] qxyzw=[" << target_q.x() << ", "
            << target_q.y() << ", " << target_q.z() << ", " << target_q.w() << "]\n";

  // Step 3: print seed joints (DESCEND logical_start) for the IK request.
  std::cerr << "[IK-SEED] joints=[";
  for (std::size_t j = 0; j < descend_golden[0].size(); ++j) {
    std::cerr << (j > 0 ? ", " : "") << descend_golden[0][j];
  }
  std::cerr << "]\n";

  // Step 4: print alternative retreat targets for comparison.
  for (const double dy : {-0.005, -0.010, -0.012}) {
    Eigen::Vector3d alt_pos = start_pos + interp_t * (end_pos - start_pos);
    alt_pos.y() += dy;
    std::cerr << std::setprecision(12) << "[ALT-TARGET dy=" << (dy * 1000) << "mm] xyz=["
              << alt_pos.x() << ", " << alt_pos.y() << ", " << alt_pos.z() << "]\n";
  }

  // Step 5: print the YAML-format service request for /compute_ik.
  std::cerr << "\n=== /compute_ik service request (position_ik) ===\n"
            << "ik_request:\n"
            << "  group_name: arm\n"
            << "  robot_state:\n"
            << "    joint_state:\n"
            << "      name: [\"1\", \"2\", \"3\", \"4\", \"5\"]\n"
            << "      position: [" << descend_golden[0][0] << ", " << descend_golden[0][1] << ", "
            << descend_golden[0][2] << ", " << descend_golden[0][3] << ", " << descend_golden[0][4]
            << "]\n"
            << "  ik_link_names: [\"" << profile.tcp_link << "\"]\n"
            << "  pose_stamped:\n"
            << "    header:\n"
            << "      frame_id: \"" << profile.world_frame << "\"\n"
            << "    pose:\n"
            << "      position:\n"
            << "        x: " << target_pos.x() << "\n"
            << "        y: " << target_pos.y() << "\n"
            << "        z: " << target_pos.z() << "\n"
            << "      orientation:\n"
            << "        x: " << target_q.x() << "\n"
            << "        y: " << target_q.y() << "\n"
            << "        z: " << target_q.z() << "\n"
            << "        w: " << target_q.w() << "\n"
            << "  attempts: 10\n"
            << "  timeout:\n"
            << "    sec: 1\n"
            << "    nanosec: 0\n";
}

TEST(SO101FixedMotionTargets, DescendIntermediateWaypointRetreatsFromWallNear)
{
  if (!rclcpp::ok())
    rclcpp::init(0, nullptr);
  auto node = std::make_shared<rclcpp::Node>("so101_cp30_red_retreat_assertion");
  robot_model_loader::RobotModelLoader::Options options(readFile(SO101_TEST_URDF),
                                                        readFile(SO101_TEST_SRDF));
  options.load_kinematics_solvers = false;
  robot_model_loader::RobotModelLoader loader(node, options);
  const auto & model = loader.getModel();
  ASSERT_TRUE(model);
  moveit::core::RobotState state(model);
  const auto profile = configuredProfile();

  const auto policy = configuredPolicy();
  const auto descend_spec = policy.spec(spp::State::DESCEND);
  ASSERT_TRUE(descend_spec);
  const auto & waypoints = descend_spec->target.joint_waypoints;
  ASSERT_GE(waypoints.size(), 2U) << "DESCEND must have at least start waypoint and endpoint";

  // Compute TCP Y for the DESCEND logical start (from MOVE_ABOVE endpoint).
  state.setToDefaultValues();
  state.setVariablePositions(profile.arm_joints, descend_spec->logical_start);
  state.setVariablePosition(profile.gripper_joint, profile.q6_preopen);
  state.update();
  const double start_y = state.getGlobalLinkTransform(profile.tcp_link).translation().y();

  // Compute TCP Y for the DESCEND endpoint (last waypoint).
  state.setToDefaultValues();
  state.setVariablePositions(profile.arm_joints, waypoints.back());
  state.setVariablePosition(profile.gripper_joint, profile.q6_preopen);
  state.update();
  const double end_y = state.getGlobalLinkTransform(profile.tcp_link).translation().y();

  // Check every intermediate waypoint (excluding the seated endpoint).
  // At least one must have TCP Y at least 3mm farther along the +Y outward normal
  // than the linear interpolation between start and endpoint at the same
  // fractional progress.
  bool has_retreat = false;
  constexpr double min_retreat_m = 0.003;
  for (std::size_t i = 0; i + 1 < waypoints.size(); ++i) {
    state.setToDefaultValues();
    state.setVariablePositions(profile.arm_joints, waypoints[i]);
    state.setVariablePosition(profile.gripper_joint, profile.q6_preopen);
    state.update();
    const double wp_y = state.getGlobalLinkTransform(profile.tcp_link).translation().y();

    // Compute the fractional progress in Z between start and endpoint.
    state.setToDefaultValues();
    state.setVariablePositions(profile.arm_joints, waypoints[i]);
    state.update();
    const double wp_z = state.getGlobalLinkTransform(profile.tcp_link).translation().z();

    // Re-get start/end Z for the fractional calculation.
    state.setToDefaultValues();
    state.setVariablePositions(profile.arm_joints, descend_spec->logical_start);
    state.update();
    const double start_z = state.getGlobalLinkTransform(profile.tcp_link).translation().z();
    state.setToDefaultValues();
    state.setVariablePositions(profile.arm_joints, waypoints.back());
    state.update();
    const double end_z = state.getGlobalLinkTransform(profile.tcp_link).translation().z();

    const double z_range = start_z - end_z;
    const double frac = (z_range > 1e-6) ? (start_z - wp_z) / z_range : 0.0;
    const double line_y = start_y + frac * (end_y - start_y);
    const double retreat = wp_y - line_y;  // positive = farther from wall_near

    std::cerr << "[RED-CHECK] wp[" << i << "] Y=" << wp_y << " line_Y=" << line_y
              << " retreat=" << (retreat * 1000) << "mm\n";

    if (retreat >= min_retreat_m) {
      has_retreat = true;
      break;
    }
  }
  EXPECT_TRUE(has_retreat) << "DESCEND lacks an intermediate waypoint that retreats at least "
                           << (min_retreat_m * 1000) << " mm from wall_near";
}
