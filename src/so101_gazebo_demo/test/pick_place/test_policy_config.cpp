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

const std::vector<std::string> kMotionStates{
  "MOVE_ABOVE_OBJECT", "DESCEND", "LIFT", "MOVE_ABOVE_PLACE", "DESCEND_TO_PLACE",
  "RETREAT", "RECOVER_LIFT_TO_SAFE_HEIGHT", "RECOVER_MOVE_ABOVE_PICK",
  "RECOVER_DESCEND_TO_PICK", "RECOVER_RETREAT"};

class PolicyFixture
{
public:
  explicit PolicyFixture(const std::string & name)
  : root(std::filesystem::temp_directory_path() / ("so101_policy_config_" + name))
  {
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);
    write(objectPath(), validObjectYaml());
    write(motionPath(), validMotionYaml());
    write(validationPath(), validValidationYaml());
  }

  ~PolicyFixture() {std::filesystem::remove_all(root);}

  [[nodiscard]] std::filesystem::path objectPath() const {return root / "object.yaml";}
  [[nodiscard]] std::filesystem::path motionPath() const {return root / "motion.yaml";}
  [[nodiscard]] std::filesystem::path validationPath() const {return root / "validation.yaml";}

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
fingertip_adapters:
  enabled: true
  material: TPU_95A
  shore_hardness_a: 95.0
  contact_model: rigid_primitive_approximation
  geometry_reference_q6: 0.30
  target_reference_gap_m: 0.0025
  tongue_extension_m: 0.019671037305
  tongue_width_m: 0.012
  tongue_height_m: 0.027
  friction_coefficient: 1.2
  fixed_tongue:
    size_xyz: [0.019671037305, 0.012, 0.027]
    origin_xyz_rpy: [-0.001764481200, 0.0, -0.130449432212, 0.0, 0.0, 0.0]
  fixed_stem:
    size_xyz: [0.004, 0.012, 0.038]
    origin_xyz_rpy: [-0.013599999852, 0.0, -0.100000000000, 0.0, 0.0, 0.0]
  moving_tongue:
    size_xyz: [0.019671037305, 0.012, 0.027]
    origin_xyz_rpy: [-0.031437919338, -0.102329204263, 0.018800393214, -1.5708, 0.0, -0.30]
  moving_stem:
    size_xyz: [0.004, 0.012, 0.038]
    origin_xyz_rpy: [-0.011132594002, -0.076737385516, 0.018800281367, -1.5708, 0.0, -0.30]
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
  preopen_q6: 0.89
  close_q6: 0.29
  release_q6: 1.70
states:
)";
    for (const auto & state : kMotionStates) {
      if (state == omitted_state) continue;
      yaml += "  " + state + ":\n";
      yaml += "    logical_start: [0.0, 0.0, 0.0, 0.0, 0.0]\n";
      yaml += "    waypoints:\n";
      yaml += "      - [0.1, 0.2, 0.3, 0.4, 0.5]\n";
      yaml += "    require_waypoint_ladder: false\n";
      yaml += "    gripper_q6: 1.1\n";
    }
    return yaml;
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
  q6_position_tolerance_rad: 0.01
  q6_contact_stop_tolerance_rad: 0.01
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
  if (position != std::string::npos) value.replace(position, from.size(), to);
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
  EXPECT_DOUBLE_EQ(0.01, result.bundle->validation.runtime.q6_position_tolerance_rad);
  EXPECT_DOUBLE_EQ(0.01, result.bundle->validation.runtime.q6_contact_stop_tolerance_rad);
  EXPECT_DOUBLE_EQ(0.89, result.bundle->motion.gripper_actions.preopen_q6);
  EXPECT_DOUBLE_EQ(0.001, result.bundle->motion.approach_outside_clearance_m);
  EXPECT_DOUBLE_EQ(0.29, result.bundle->motion.gripper_actions.close_q6);
  EXPECT_DOUBLE_EQ(1.70, result.bundle->motion.gripper_actions.release_q6);
  const auto & adapters = result.bundle->object.fingertip_adapters;
  EXPECT_TRUE(adapters.enabled);
  EXPECT_EQ("TPU_95A", adapters.material);
  EXPECT_DOUBLE_EQ(95.0, adapters.shore_hardness_a);
  EXPECT_EQ("rigid_primitive_approximation", adapters.contact_model);
  EXPECT_DOUBLE_EQ(0.30, adapters.geometry_reference_q6);
  EXPECT_DOUBLE_EQ(0.0025, adapters.target_reference_gap_m);
  EXPECT_DOUBLE_EQ(0.019671037305, adapters.tongue_extension_m);
  EXPECT_DOUBLE_EQ(1.2, adapters.friction_coefficient);
  EXPECT_EQ((std::array<double, 3>{0.019671037305, 0.012, 0.027}),
            adapters.fixed_tongue.size_xyz);
  EXPECT_EQ(result.bundle->object.object_id, "plastic_cup");
  EXPECT_EQ(result.bundle->motion.policy_id, "light_cup_wall_pick");
  EXPECT_EQ(result.bundle->validation.policy_id, "light_cup_wall_pick");
  EXPECT_EQ(result.bundle->object_path, std::filesystem::canonical(fixture.objectPath()));
  EXPECT_EQ(result.bundle->motion_path, std::filesystem::canonical(fixture.motionPath()));
  EXPECT_EQ(result.bundle->validation_path, std::filesystem::canonical(fixture.validationPath()));
  for (const auto & digest : result.bundle->sha256) EXPECT_EQ(digest.size(), 64U);
  EXPECT_EQ(result.bundle->bundle_sha256.size(), 64U);
}

TEST(PolicyConfig, ConfiguresRuntimeGripperTargetsAndTolerancesFromYaml)
{
  PolicyFixture fixture("profile");
  const auto result = spp::loadPolicyBundle(fixture.paths());
  ASSERT_TRUE(result.bundle);

  const auto profile = spp::SO101Profile::configured(
    result.bundle->object, result.bundle->motion, result.bundle->validation);

  EXPECT_DOUBLE_EQ(0.89, profile.q6_preopen);
  EXPECT_DOUBLE_EQ(0.29, profile.q6_close);
  EXPECT_DOUBLE_EQ(0.29, profile.q6_contact);
  EXPECT_DOUBLE_EQ(1.70, profile.q6_full_open);
  EXPECT_DOUBLE_EQ(0.01, profile.q6_tolerance);
  EXPECT_DOUBLE_EQ(0.01, profile.contact_q6_stop_tolerance);
  EXPECT_DOUBLE_EQ(0.01, profile.q6_velocity_tolerance);
  EXPECT_NEAR(0.041207026063, profile.contact_width, 1e-12);
}

TEST(PolicyConfig, ConfiguresAttachmentRelativePoseFromObjectYaml)
{
  PolicyFixture fixture("attachment_pose");
  const auto result = spp::loadPolicyBundle(fixture.paths());
  ASSERT_TRUE(result.bundle) << (result.failure ? result.failure->code : "");
  const auto profile = spp::SO101Profile::configured(
    result.bundle->object, result.bundle->motion, result.bundle->validation);

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
         {"model", "contact_model: rigid_primitive_approximation",
          "contact_model: fake_soft_body"}}) {
    PolicyFixture fixture("adapter_" + name);
    PolicyFixture::write(
      fixture.objectPath(), replaceOnce(PolicyFixture::validObjectYaml(), from, to));
    expectFailure(fixture.paths(), "POLICY_INVALID_VALUE");
  }
}

TEST(PolicyConfig, RejectsNonpositiveAdapterGapOrFriction)
{
  for (const auto & [name, from, to] :
       std::vector<std::tuple<std::string, std::string, std::string>>{
         {"gap", "target_reference_gap_m: 0.0025", "target_reference_gap_m: 0.0"},
         {"friction", "friction_coefficient: 1.2", "friction_coefficient: 0.0"}}) {
    PolicyFixture fixture("adapter_" + name);
    PolicyFixture::write(
      fixture.objectPath(), replaceOnce(PolicyFixture::validObjectYaml(), from, to));
    expectFailure(fixture.paths(), "POLICY_INVALID_VALUE");
  }
}

TEST(PolicyConfig, RejectsUnsupportedSchemaVersion)
{
  PolicyFixture fixture("schema");
  PolicyFixture::write(
    fixture.motionPath(), replaceOnce(PolicyFixture::validMotionYaml(), "schema_version: 1",
                                      "schema_version: 2"));
  expectFailure(fixture.paths(), "POLICY_SCHEMA_UNSUPPORTED");
}

TEST(PolicyConfig, RejectsNonFiniteNumbers)
{
  for (const auto & [name, value] :
       std::vector<std::pair<std::string, std::string>>{{"nan", ".nan"}, {"inf", ".inf"}}) {
    PolicyFixture fixture("non_finite_" + name);
    PolicyFixture::write(
      fixture.objectPath(), replaceOnce(PolicyFixture::validObjectYaml(), "mass_kg: 0.020",
                                        "mass_kg: " + value));
    expectFailure(fixture.paths(), "POLICY_INVALID_VALUE");
  }
}

TEST(PolicyConfig, RejectsPoseWithWrongElementCount)
{
  PolicyFixture fixture("pose_shape");
  PolicyFixture::write(
    fixture.objectPath(),
    replaceOnce(PolicyFixture::validObjectYaml(),
                "[0.020, -0.280, 0.165, 0.0, 0.0, 0.0, 1.0]",
                "[0.020, -0.280, 0.165, 0.0, 0.0, 1.0]"));
  expectFailure(fixture.paths(), "POLICY_INVALID_VALUE");
}

TEST(PolicyConfig, RejectsJointWaypointWithWrongElementCount)
{
  PolicyFixture fixture("waypoint_shape");
  PolicyFixture::write(
    fixture.motionPath(), replaceOnce(PolicyFixture::validMotionYaml(),
                                      "[0.1, 0.2, 0.3, 0.4, 0.5]",
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
  PolicyFixture::write(
    fixture.motionPath(), replaceOnce(PolicyFixture::validMotionYaml(),
                                      "object_id: plastic_cup", "object_id: other_object"));
  expectFailure(fixture.paths(), "POLICY_ID_MISMATCH");
}

TEST(PolicyConfig, RejectsValidationPolicyIdMismatch)
{
  PolicyFixture fixture("mismatched_policy");
  PolicyFixture::write(
    fixture.validationPath(), replaceOnce(PolicyFixture::validValidationYaml(),
                                          "policy_id: light_cup_wall_pick",
                                          "policy_id: another_policy"));
  expectFailure(fixture.paths(), "POLICY_ID_MISMATCH");
}
