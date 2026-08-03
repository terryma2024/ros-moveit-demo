#include <gtest/gtest.h>

#include <array>
#include <filesystem>
#include <fstream>
#include <string>
#include <tuple>
#include <vector>

#include "so101_gazebo_demo/pick_place/policy_config.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

const std::vector<std::string> kMotionStates{"MOVE_ABOVE_OBJECT",
                                             "DESCEND",
                                             "LIFT",
                                             "MOVE_ABOVE_PLACE",
                                             "DESCEND_TO_PLACE",
                                             "RETREAT",
                                             "RECOVER_LIFT_TO_SAFE_HEIGHT",
                                             "RECOVER_MOVE_ABOVE_PICK",
                                             "RECOVER_DESCEND_TO_PICK",
                                             "RECOVER_RETREAT"};

std::string replaceOnce(std::string value, const std::string & from, const std::string & to);

class PolicyFixture
{
public:
  explicit PolicyFixture(const std::string & name) :
      root(std::filesystem::temp_directory_path() / ("so101_policy_config_" + name))
  {
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);
    write(objectPath(), validObjectYaml());
    write(motionPath(), validMotionYaml());
    write(validationPath(), validValidationYaml());
  }

  ~PolicyFixture()
  {
    std::filesystem::remove_all(root);
  }

  [[nodiscard]] std::filesystem::path objectPath() const
  {
    return root / "object.yaml";
  }
  [[nodiscard]] std::filesystem::path motionPath() const
  {
    return root / "motion.yaml";
  }
  [[nodiscard]] std::filesystem::path validationPath() const
  {
    return root / "validation.yaml";
  }

  [[nodiscard]] spp::PolicyPaths paths() const
  {
    return {objectPath().string(), motionPath().string(), validationPath().string()};
  }

  static void write(const std::filesystem::path & path, const std::string & contents)
  {
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    ASSERT_TRUE(output) << path;
    output << contents;
  }

  static std::string validObjectYaml()
  {
    return R"(schema_version: 1
object_id: plastic_cup
model:
  mass_kg: 0.020
  height_m: 0.090
  outer_radius_m: 0.040
  wall_thickness_m: 0.002
  bottom_thickness_m: 0.002
  side_count: 12
  collision_kind: compound_primitives
scene:
  spawn_pose_xyz_xyzw: [0.020, -0.280, 0.165, 0.0, 0.0, 0.0, 1.0]
  place_pose_xyz_xyzw: [-0.080, -0.250, 0.165, 0.0, 0.0, 0.0, 1.0]
grasp_frame:
  near_wall_outward_world: [0.0, 1.0, 0.0]
  fixed_finger_side: outside
  moving_jaw_side: inside
  insertion_depth_below_rim_m: 0.025
  rim_clearance_m: 0.008
  bottom_clearance_m: 0.020
  attachment_relative_pose_xyz_xyzw: [0.047, 0.002, -0.154, 0.0, 0.0, 0.72, 0.69]
fingertip_pads:
  enabled: true
  material: TPU_95A
  shore_hardness_a: 95.0
  contact_model: rigid_link_local_mesh
  geometry_reference_q6: 0.30
  safe_lower_q6: -0.059303612618397
  safe_gap_m: 0.001
  grasp_gap_m: 0.001960000000000000
  calibration_fingerprint: b101b7db33a13c82797eb80c2356f1c6b509e04bdae7999efd4b6a8ce0d1094f
  friction_coefficient: 1.2
  fixed_pad:
    opening_axis_thickness_m: 0.005
    contact_direction_x: 1.0
    axial_axis: z
    native_axial_bounds_m: [0.065720335, 0.105374999]
    profile_points: [[0.06622, 0.00720, -0.01160], [0.07500, 0.00715, -0.01160], [0.084875, 0.00680, -0.01160], [0.085875, 0.00580, -0.00990], [0.094875, 0.00545, -0.00990], [0.095875, 0.00490, -0.00790], [0.10000, 0.00410, -0.00790], [0.104875, 0.00145, -0.00790]]
  moving_pad:
    opening_axis_thickness_m: 0.005
    contact_direction_x: -1.0
    axial_axis: y
    native_axial_bounds_m: [-0.082000002, -0.061999999]
    profile_points: [[-0.0815, 0.0036, -0.01230], [-0.0780, 0.0045, -0.01230], [-0.0730, 0.0054, -0.01230], [-0.0722, 0.0057, -0.01230], [-0.0718, 0.0058, -0.01030], [-0.0670, 0.0060, -0.01030], [-0.0625, 0.0060, -0.01030]]
)";
  }

  static std::string validMotionYaml(const std::string & omitted_state = "")
  {
    std::string yaml = R"(schema_version: 1
policy_id: light_cup_wall_pick
object_id: plastic_cup
arm_joints: ["1", "2", "3", "4", "5"]
approach_outside_clearance_m: 0.001
gripper_actions:
  preopen_q6: 0.465038
  grasp_close_q6: -0.047409691482075
  release_q6: 1.70
states:
)";
    for (const auto & state : kMotionStates) {
      if (state == omitted_state)
        continue;
      yaml += "  " + state + ":\n";
      yaml += "    logical_start: [0.0, 0.0, 0.0, 0.0, 0.0]\n";
      yaml += "    waypoints:\n";
      yaml += "      - [0.1, 0.2, 0.3, 0.4, 0.5]\n";
      yaml += "    require_waypoint_ladder: false\n";
      yaml += "    require_axial_path_validation: false\n";
      yaml += "    gripper_q6: -0.047409691482075\n";
      yaml += "    velocity_scaling: 0.10\n";
      yaml += "    acceleration_scaling: 0.10\n";
    }
    return yaml;
  }

  static std::string nativeFingertipPadObjectYaml()
  {
    return validObjectYaml();
  }

  static std::string nativeFingertipPadMotionYaml()
  {
    return validMotionYaml();
  }

  static std::string nativeFingertipPadValidationYaml()
  {
    return validValidationYaml();
  }

  static std::string validValidationYaml()
  {
    std::string yaml = R"(schema_version: 1
policy_id: light_cup_wall_pick
object_id: plastic_cup
grasp_contact:
  require_fixed_finger: true
  require_moving_jaw: true
  required_wall_collision: wall_near
  fixed_surface: outside
  moving_surface: inside
  max_penetration_m: 0.0008
  min_below_rim_m: 0.008
  max_below_rim_m: 0.035
  min_bottom_clearance_m: 0.020
  forbidden_collisions: [rim, bottom, wall_opposite]
runtime:
  min_real_time_factor: 0.85
  q6_velocity_tolerance_rad_s: 0.01
  q6_position_tolerance_rad: 0.001
  q6_contact_stop_tolerance_rad: 0.00125
states:
)";
    for (const auto & state : kMotionStates) {
      yaml += "  " + state + ":\n";
      yaml += "    endpoint_position: [0.02, -0.28, 0.28]\n";
      yaml += "    local_approach_axis: [0.0, 0.0, -1.0]\n";
      yaml += "    target_approach_axis: [0.0, 0.0, -1.0]\n";
      yaml += "    path_direction: [0.0, 0.0, -1.0]\n";
      yaml += "    position_tolerance_m: 0.005\n";
      yaml += "    axis_tolerance_rad: 0.0872664626\n";
      yaml += "    max_lateral_deviation_m: 0.005\n";
      yaml += "    max_joint_jump_rad: 0.15\n";
      yaml += "    joint_endpoint_tolerance_rad: 0.005\n";
      yaml += "    min_duration_s: 0.1\n";
      yaml += "    monotonic_tolerance_m: 0.00001\n";
      yaml += "    allowed_touch_pairs: []\n";
      yaml += "    temporal_contact: null\n";
    }
    return yaml;
  }

  std::filesystem::path root;
};

void expectFailure(const spp::PolicyPaths & paths, const std::string & code)
{
  const auto result = spp::loadPolicyBundle(paths);
  EXPECT_FALSE(result.bundle.has_value());
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ(result.failure->code, code);
}

std::string replaceOnce(std::string value, const std::string & from, const std::string & to)
{
  const auto position = value.find(from);
  EXPECT_NE(position, std::string::npos) << from;
  if (position != std::string::npos)
    value.replace(position, from.size(), to);
  return value;
}

}  // namespace

TEST(PolicyConfig, LoadsValidBundleWithCanonicalPathsAndContentDigests)
{
  PolicyFixture fixture("valid");

  const auto result = spp::loadPolicyBundle(fixture.paths());

  ASSERT_TRUE(result.bundle.has_value());
  EXPECT_FALSE(result.failure.has_value());
  EXPECT_TRUE(result.bundle->validation.grasp_contact.require_fixed_finger);
  EXPECT_TRUE(result.bundle->validation.grasp_contact.require_moving_jaw);
  EXPECT_EQ("wall_near", result.bundle->validation.grasp_contact.required_wall_collision);
  EXPECT_EQ("outside", result.bundle->validation.grasp_contact.fixed_surface);
  EXPECT_EQ("inside", result.bundle->validation.grasp_contact.moving_surface);
  EXPECT_DOUBLE_EQ(0.0008, result.bundle->validation.grasp_contact.max_penetration_m);
  EXPECT_EQ((std::vector<std::string>{"rim", "bottom", "wall_opposite"}),
            result.bundle->validation.grasp_contact.forbidden_collisions);
  EXPECT_DOUBLE_EQ(0.85, result.bundle->validation.runtime.min_real_time_factor);
  EXPECT_DOUBLE_EQ(0.01, result.bundle->validation.runtime.q6_velocity_tolerance_rad_s);
  EXPECT_DOUBLE_EQ(0.001, result.bundle->validation.runtime.q6_position_tolerance_rad);
  EXPECT_DOUBLE_EQ(0.00125, result.bundle->validation.runtime.q6_contact_stop_tolerance_rad);
  EXPECT_DOUBLE_EQ(0.465038, result.bundle->motion.gripper_actions.preopen_q6);
  EXPECT_DOUBLE_EQ(0.001, result.bundle->motion.approach_outside_clearance_m);
  EXPECT_DOUBLE_EQ(-0.047409691482075, result.bundle->motion.gripper_actions.grasp_close_q6);
  EXPECT_DOUBLE_EQ(1.70, result.bundle->motion.gripper_actions.release_q6);
  const auto & pads = result.bundle->object.fingertip_pads;
  EXPECT_TRUE(pads.enabled);
  EXPECT_EQ("TPU_95A", pads.material);
  EXPECT_DOUBLE_EQ(95.0, pads.shore_hardness_a);
  EXPECT_EQ("rigid_link_local_mesh", pads.contact_model);
  EXPECT_DOUBLE_EQ(0.30, pads.geometry_reference_q6);
  EXPECT_DOUBLE_EQ(-0.059303612618397, pads.safe_lower_q6);
  EXPECT_DOUBLE_EQ(1.2, pads.friction_coefficient);
  EXPECT_DOUBLE_EQ(0.005, pads.fixed_pad.opening_axis_thickness_m);
  EXPECT_DOUBLE_EQ(0.005, pads.moving_pad.opening_axis_thickness_m);
  EXPECT_EQ(8U, pads.fixed_pad.profile_points.size());
  EXPECT_EQ(7U, pads.moving_pad.profile_points.size());
  EXPECT_EQ(result.bundle->object.object_id, "plastic_cup");
  EXPECT_EQ(result.bundle->motion.policy_id, "light_cup_wall_pick");
  EXPECT_EQ(result.bundle->validation.policy_id, "light_cup_wall_pick");
  EXPECT_EQ(result.bundle->object_path, std::filesystem::canonical(fixture.objectPath()));
  EXPECT_EQ(result.bundle->motion_path, std::filesystem::canonical(fixture.motionPath()));
  EXPECT_EQ(result.bundle->validation_path, std::filesystem::canonical(fixture.validationPath()));
  for (const auto & digest : result.bundle->sha256)
    EXPECT_EQ(digest.size(), 64U);
  EXPECT_EQ(result.bundle->bundle_sha256.size(), 64U);
}

TEST(PolicyConfig, LoadsNativeFingertipPadConfiguration)
{
  PolicyFixture fixture("native_fingertip_pad");
  PolicyFixture::write(fixture.objectPath(), PolicyFixture::nativeFingertipPadObjectYaml());
  PolicyFixture::write(fixture.motionPath(), PolicyFixture::nativeFingertipPadMotionYaml());
  PolicyFixture::write(fixture.validationPath(), PolicyFixture::nativeFingertipPadValidationYaml());

  const auto result = spp::loadPolicyBundle(fixture.paths());

  ASSERT_TRUE(result.bundle.has_value()) << (result.failure ? result.failure->code : "");
  const auto & pads = result.bundle->object.fingertip_pads;
  EXPECT_EQ("z", pads.fixed_pad.axial_axis);
  EXPECT_EQ("y", pads.moving_pad.axial_axis);
  EXPECT_DOUBLE_EQ(1.0, pads.fixed_pad.contact_direction_x);
  EXPECT_DOUBLE_EQ(-1.0, pads.moving_pad.contact_direction_x);
  EXPECT_DOUBLE_EQ(0.465038, result.bundle->motion.gripper_actions.preopen_q6);
  EXPECT_DOUBLE_EQ(0.001, result.bundle->validation.runtime.q6_position_tolerance_rad);
  EXPECT_DOUBLE_EQ(0.00125, result.bundle->validation.runtime.q6_contact_stop_tolerance_rad);
  EXPECT_EQ("b101b7db33a13c82797eb80c2356f1c6b509e04bdae7999efd4b6a8ce0d1094f",
            pads.calibration_fingerprint);
}

TEST(PolicyConfig, RejectsNativePadCalibrationFingerprintMismatchAtRuntimeProfileBinding)
{
  PolicyFixture fixture("native_pad_fingerprint_mismatch");
  PolicyFixture::write(
    fixture.objectPath(),
    replaceOnce(
      PolicyFixture::nativeFingertipPadObjectYaml(),
      "calibration_fingerprint: b101b7db33a13c82797eb80c2356f1c6b509e04bdae7999efd4b6a8ce0d1094f",
      "calibration_fingerprint: wrong-pad-model"));
  PolicyFixture::write(fixture.motionPath(), PolicyFixture::nativeFingertipPadMotionYaml());
  PolicyFixture::write(fixture.validationPath(), PolicyFixture::nativeFingertipPadValidationYaml());
  const auto loaded = spp::loadPolicyBundle(fixture.paths());
  ASSERT_TRUE(loaded.bundle) << (loaded.failure ? loaded.failure->code : "");
  EXPECT_THROW((void)spp::SO101Profile::configured(loaded.bundle->object, loaded.bundle->motion,
                                                   loaded.bundle->validation),
               std::invalid_argument);
}

TEST(PolicyConfig, FingertipPadRejectsStemField)
{
  PolicyFixture fixture("fingertip_pad_stem");
  PolicyFixture::write(fixture.objectPath(),
                       PolicyFixture::nativeFingertipPadObjectYaml() + R"(  fixed_stem:
    size_xyz: [0.004, 0.012, 0.038]
    origin_xyz_rpy: [-0.013599999852, 0.0, -0.100000000000, 0.0, 0.0, 0.0]
)");
  PolicyFixture::write(fixture.motionPath(), PolicyFixture::nativeFingertipPadMotionYaml());
  PolicyFixture::write(fixture.validationPath(), PolicyFixture::nativeFingertipPadValidationYaml());
  expectFailure(fixture.paths(), "POLICY_UNKNOWN_FIELD");
}

TEST(PolicyConfig, FingertipPadRejectsGraspBelowSafeLower)
{
  PolicyFixture fixture("fingertip_pad_lower_bound");
  PolicyFixture::write(fixture.objectPath(), PolicyFixture::nativeFingertipPadObjectYaml());
  PolicyFixture::write(fixture.motionPath(),
                       replaceOnce(PolicyFixture::nativeFingertipPadMotionYaml(),
                                   "grasp_close_q6: -0.047409691482075",
                                   "grasp_close_q6: -0.0594"));
  PolicyFixture::write(fixture.validationPath(), PolicyFixture::nativeFingertipPadValidationYaml());
  expectFailure(fixture.paths(), "POLICY_INVALID_VALUE");
}

TEST(PolicyConfig, ConfiguresRuntimeGripperTargetsAndTolerancesFromYaml)
{
  PolicyFixture fixture("profile");
  const auto result = spp::loadPolicyBundle(fixture.paths());
  ASSERT_TRUE(result.bundle);

  const auto profile = spp::SO101Profile::configured(result.bundle->object, result.bundle->motion,
                                                     result.bundle->validation);

  EXPECT_DOUBLE_EQ(0.465038, profile.q6_preopen);
  EXPECT_DOUBLE_EQ(-0.047409691482075, profile.q6_close);
  EXPECT_DOUBLE_EQ(-0.047409691482075, profile.q6_contact);
  EXPECT_DOUBLE_EQ(1.70, profile.q6_full_open);
  ASSERT_EQ(profile.release_stages_q6.size(), 3U);
  EXPECT_DOUBLE_EQ(1.70, profile.release_stages_q6.back());
  EXPECT_DOUBLE_EQ(0.001, profile.q6_tolerance);
  EXPECT_DOUBLE_EQ(0.00125, profile.contact_q6_stop_tolerance);
  EXPECT_DOUBLE_EQ(0.01, profile.q6_velocity_tolerance);
  EXPECT_NEAR(0.001960000000000, profile.contact_width, 1e-12);
}

TEST(PolicyConfig, ConfiguresAttachmentRelativePoseFromObjectYaml)
{
  PolicyFixture fixture("attachment_pose");
  const auto result = spp::loadPolicyBundle(fixture.paths());
  ASSERT_TRUE(result.bundle) << (result.failure ? result.failure->code : "");
  const auto profile = spp::SO101Profile::configured(result.bundle->object, result.bundle->motion,
                                                     result.bundle->validation);

  EXPECT_DOUBLE_EQ(0.047, profile.calibrated_grasp_relative_pose.x);
  EXPECT_DOUBLE_EQ(0.002, profile.calibrated_grasp_relative_pose.y);
  EXPECT_DOUBLE_EQ(-0.154, profile.calibrated_grasp_relative_pose.z);
  EXPECT_DOUBLE_EQ(0.72, profile.calibrated_grasp_relative_pose.qz);
  EXPECT_DOUBLE_EQ(0.69, profile.calibrated_grasp_relative_pose.qw);
}

TEST(PolicyConfig, RejectsMissingFile)
{
  PolicyFixture fixture("missing");
  std::filesystem::remove(fixture.motionPath());
  expectFailure(fixture.paths(), "POLICY_FILE_MISSING");
}

TEST(PolicyConfig, RejectsUnknownTopLevelField)
{
  PolicyFixture fixture("unknown_field");
  PolicyFixture::write(fixture.objectPath(), PolicyFixture::validObjectYaml() + "surprise: true\n");
  expectFailure(fixture.paths(), "POLICY_UNKNOWN_FIELD");
}

TEST(PolicyConfig, RejectsUnsupportedAdapterMaterialOrContactModel)
{
  for (const auto & [name, from, to] :
       std::vector<std::tuple<std::string, std::string, std::string>>{
         {"material", "material: TPU_95A", "material: silicone"},
         {"model", "contact_model: rigid_link_local_mesh", "contact_model: fake_soft_body"}}) {
    PolicyFixture fixture("adapter_" + name);
    PolicyFixture::write(fixture.objectPath(),
                         replaceOnce(PolicyFixture::validObjectYaml(), from, to));
    expectFailure(fixture.paths(), "POLICY_INVALID_VALUE");
  }
}

TEST(PolicyConfig, RejectsNonpositiveAdapterGapOrFriction)
{
  for (const auto & [name, from, to] :
       std::vector<std::tuple<std::string, std::string, std::string>>{
         {"gap", "safe_gap_m: 0.001", "safe_gap_m: 0.0"},
         {"friction", "friction_coefficient: 1.2", "friction_coefficient: 0.0"}}) {
    PolicyFixture fixture("adapter_" + name);
    PolicyFixture::write(fixture.objectPath(),
                         replaceOnce(PolicyFixture::validObjectYaml(), from, to));
    expectFailure(fixture.paths(), "POLICY_INVALID_VALUE");
  }
}

TEST(PolicyConfig, RejectsUnsupportedSchemaVersion)
{
  PolicyFixture fixture("schema");
  PolicyFixture::write(fixture.motionPath(), replaceOnce(PolicyFixture::validMotionYaml(),
                                                         "schema_version: 1", "schema_version: 2"));
  expectFailure(fixture.paths(), "POLICY_SCHEMA_UNSUPPORTED");
}

TEST(PolicyConfig, RejectsNonFiniteNumbers)
{
  for (const auto & [name, value] :
       std::vector<std::pair<std::string, std::string>>{{"nan", ".nan"}, {"inf", ".inf"}}) {
    PolicyFixture fixture("non_finite_" + name);
    PolicyFixture::write(fixture.objectPath(), replaceOnce(PolicyFixture::validObjectYaml(),
                                                           "mass_kg: 0.020", "mass_kg: " + value));
    expectFailure(fixture.paths(), "POLICY_INVALID_VALUE");
  }
}

TEST(PolicyConfig, RejectsPoseWithWrongElementCount)
{
  PolicyFixture fixture("pose_shape");
  PolicyFixture::write(fixture.objectPath(),
                       replaceOnce(PolicyFixture::validObjectYaml(),
                                   "[0.020, -0.280, 0.165, 0.0, 0.0, 0.0, 1.0]",
                                   "[0.020, -0.280, 0.165, 0.0, 0.0, 1.0]"));
  expectFailure(fixture.paths(), "POLICY_INVALID_VALUE");
}

TEST(PolicyConfig, RejectsJointWaypointWithWrongElementCount)
{
  PolicyFixture fixture("waypoint_shape");
  PolicyFixture::write(fixture.motionPath(),
                       replaceOnce(PolicyFixture::validMotionYaml(), "[0.1, 0.2, 0.3, 0.4, 0.5]",
                                   "[0.1, 0.2, 0.3, 0.4]"));
  expectFailure(fixture.paths(), "POLICY_INVALID_VALUE");
}

TEST(PolicyConfig, RejectsMissingRequiredMotionState)
{
  PolicyFixture fixture("missing_state");
  PolicyFixture::write(fixture.motionPath(), PolicyFixture::validMotionYaml("RETREAT"));
  expectFailure(fixture.paths(), "POLICY_STATE_MISSING");
}

TEST(PolicyConfig, RejectsObjectIdMismatch)
{
  PolicyFixture fixture("mismatched_object");
  PolicyFixture::write(fixture.motionPath(),
                       replaceOnce(PolicyFixture::validMotionYaml(), "object_id: plastic_cup",
                                   "object_id: other_object"));
  expectFailure(fixture.paths(), "POLICY_ID_MISMATCH");
}

TEST(PolicyConfig, RejectsValidationPolicyIdMismatch)
{
  PolicyFixture fixture("mismatched_policy");
  PolicyFixture::write(fixture.validationPath(),
                       replaceOnce(PolicyFixture::validValidationYaml(),
                                   "policy_id: light_cup_wall_pick", "policy_id: another_policy"));
  expectFailure(fixture.paths(), "POLICY_ID_MISMATCH");
}
