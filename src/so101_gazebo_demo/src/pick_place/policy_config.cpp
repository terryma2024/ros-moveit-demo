#include "so101_gazebo_demo/pick_place/policy_config.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iterator>
#include <limits>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <utility>

#include <openssl/evp.h>
#include <yaml-cpp/yaml.h>

#include "so101_gazebo_demo/pick_place/fingertip_pad_gap_calibration_data.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{

struct PolicyError : std::runtime_error
{
  PolicyError(std::string error_code, const std::string & message) :
      std::runtime_error(message), code(std::move(error_code))
  {
  }

  std::string code;
};

constexpr std::array<State, 10> kMotionStates{State::MOVE_ABOVE_OBJECT,
                                              State::DESCEND,
                                              State::LIFT,
                                              State::MOVE_ABOVE_PLACE,
                                              State::DESCEND_TO_PLACE,
                                              State::RETREAT,
                                              State::RECOVER_LIFT_TO_SAFE_HEIGHT,
                                              State::RECOVER_MOVE_ABOVE_PICK,
                                              State::RECOVER_DESCEND_TO_PICK,
                                              State::RECOVER_RETREAT};

Failure failure(std::string code, std::string message)
{
  return {FailureCategory::CONFIGURATION, std::move(code), std::move(message), {}};
}

void requireMap(const YAML::Node & node, std::string_view context)
{
  if (!node || !node.IsMap()) {
    throw PolicyError("POLICY_INVALID_VALUE", std::string(context) + " must be a map");
  }
}

void rejectUnknownFields(const YAML::Node & node, const std::set<std::string> & allowed,
                         std::string_view context)
{
  requireMap(node, context);
  for (const auto & entry : node) {
    if (!entry.first.IsScalar()) {
      throw PolicyError("POLICY_UNKNOWN_FIELD", std::string(context) + " has a non-string field");
    }
    const auto key = entry.first.as<std::string>();
    if (allowed.count(key) == 0U) {
      throw PolicyError("POLICY_UNKNOWN_FIELD", std::string(context) + " has unknown field " + key);
    }
  }
}

YAML::Node requireField(const YAML::Node & node, const char * field, std::string_view context)
{
  const auto value = node[field];
  if (!value) {
    throw PolicyError("POLICY_INVALID_VALUE", std::string(context) + " missing field " + field);
  }
  return value;
}

std::string parseString(const YAML::Node & node, std::string_view context)
{
  if (!node.IsScalar()) {
    throw PolicyError("POLICY_INVALID_VALUE", std::string(context) + " must be a string");
  }
  const auto value = node.as<std::string>();
  if (value.empty()) {
    throw PolicyError("POLICY_INVALID_VALUE", std::string(context) + " must not be empty");
  }
  return value;
}

double parseFinite(const YAML::Node & node, std::string_view context)
{
  if (!node.IsScalar()) {
    throw PolicyError("POLICY_INVALID_VALUE", std::string(context) + " must be numeric");
  }
  const auto value = node.as<double>();
  if (!std::isfinite(value)) {
    throw PolicyError("POLICY_INVALID_VALUE", std::string(context) + " must be finite");
  }
  return value;
}

double parseNonNegative(const YAML::Node & node, std::string_view context)
{
  const double value = parseFinite(node, context);
  if (value < 0.0) {
    throw PolicyError("POLICY_INVALID_VALUE", std::string(context) + " must be non-negative");
  }
  return value;
}

double parseNonPositive(const YAML::Node & node, std::string_view context)
{
  const double value = parseFinite(node, context);
  if (value > 0.0) {
    throw PolicyError("POLICY_INVALID_VALUE", std::string(context) + " must be non-positive");
  }
  return value;
}

double parsePositive(const YAML::Node & node, std::string_view context)
{
  const double value = parseFinite(node, context);
  if (value <= 0.0) {
    throw PolicyError("POLICY_INVALID_VALUE", std::string(context) + " must be positive");
  }
  return value;
}

std::vector<double> parseVector(const YAML::Node & node, std::size_t size, std::string_view context)
{
  if (!node.IsSequence() || node.size() != size) {
    throw PolicyError("POLICY_INVALID_VALUE", std::string(context) + " has wrong element count");
  }
  std::vector<double> result;
  result.reserve(size);
  for (std::size_t index = 0; index < size; ++index) {
    result.push_back(
      parseFinite(node[index], std::string(context) + "[" + std::to_string(index) + "]"));
  }
  return result;
}

Vec3 parseVec3(const YAML::Node & node, std::string_view context)
{
  const auto values = parseVector(node, 3, context);
  return {values[0], values[1], values[2]};
}

Pose3d parsePose(const YAML::Node & node, std::string_view context)
{
  const auto values = parseVector(node, 7, context);
  const double quaternion_norm = std::sqrt(values[3] * values[3] + values[4] * values[4] +
                                           values[5] * values[5] + values[6] * values[6]);
  if (quaternion_norm <= 0.0) {
    throw PolicyError("POLICY_INVALID_VALUE", std::string(context) + " has a zero quaternion");
  }
  return {values[0], values[1], values[2], values[3], values[4], values[5], values[6]};
}

FingertipPadGeometryConfig parseFingertipPadGeometry(const YAML::Node & node,
                                                     const std::string & context,
                                                     const std::string & expected_axis,
                                                     double expected_direction,
                                                     std::size_t expected_profile_count)
{
  rejectUnknownFields(node,
                      {"opening_axis_thickness_m", "contact_direction_x", "axial_axis",
                       "native_axial_bounds_m", "profile_points"},
                      context);
  FingertipPadGeometryConfig result;
  result.opening_axis_thickness_m = parsePositive(
    requireField(node, "opening_axis_thickness_m", context), context + ".opening_axis_thickness_m");
  result.contact_direction_x = parseFinite(requireField(node, "contact_direction_x", context),
                                           context + ".contact_direction_x");
  result.axial_axis =
    parseString(requireField(node, "axial_axis", context), context + ".axial_axis");
  const auto native = parseVector(requireField(node, "native_axial_bounds_m", context), 2,
                                  context + ".native_axial_bounds_m");
  const auto points = requireField(node, "profile_points", context);
  if (!points.IsSequence() || points.size() != expected_profile_count) {
    throw PolicyError("POLICY_INVALID_VALUE", context + ".profile_points has wrong element count");
  }
  if (result.opening_axis_thickness_m != 0.005 ||
      result.contact_direction_x != expected_direction || result.axial_axis != expected_axis ||
      !(native[0] < native[1])) {
    throw PolicyError("POLICY_INVALID_VALUE",
                      context + " must retain the measured native pad envelope");
  }
  result.native_axial_bounds_m = {native[0], native[1]};
  double previous_axis = -std::numeric_limits<double>::infinity();
  for (std::size_t index = 0; index < points.size(); ++index) {
    const auto point =
      parseVec3(points[index], context + ".profile_points[" + std::to_string(index) + "]");
    if (!(previous_axis < point.x && point.y > 0.0)) {
      throw PolicyError("POLICY_INVALID_VALUE",
                        context + ".profile_points must be ordered and tapered");
    }
    previous_axis = point.x;
    result.profile_points.push_back(point);
  }
  if (!(native[0] < result.profile_points.front().x &&
        result.profile_points.back().x < native[1])) {
    throw PolicyError("POLICY_INVALID_VALUE", context + " extends past the native fingertip");
  }
  return result;
}

int parseSchemaVersion(const YAML::Node & root, std::string_view context, int expected)
{
  const auto node = requireField(root, "schema_version", context);
  if (!node.IsScalar()) {
    throw PolicyError("POLICY_INVALID_VALUE",
                      std::string(context) + " schema_version must be scalar");
  }
  const int version = node.as<int>();
  if (version != expected) {
    throw PolicyError("POLICY_SCHEMA_UNSUPPORTED", std::string(context) +
                                                     " schema_version must equal " +
                                                     std::to_string(expected));
  }
  return version;
}

std::vector<std::string> parseStrings(const YAML::Node & node, std::string_view context,
                                      bool allow_empty)
{
  if (!node.IsSequence() || (!allow_empty && node.size() == 0U)) {
    throw PolicyError("POLICY_INVALID_VALUE", std::string(context) + " must be a sequence");
  }
  std::vector<std::string> result;
  std::set<std::string> unique;
  for (std::size_t index = 0; index < node.size(); ++index) {
    const auto value =
      parseString(node[index], std::string(context) + "[" + std::to_string(index) + "]");
    if (!unique.insert(value).second) {
      throw PolicyError("POLICY_INVALID_VALUE", std::string(context) + " contains duplicates");
    }
    result.push_back(value);
  }
  return result;
}

std::set<std::string> parseStringSet(const YAML::Node & node, std::string_view context)
{
  const auto values = parseStrings(node, context, true);
  return {values.begin(), values.end()};
}

State parseRequiredState(const std::string & name)
{
  const auto state = stateFromString(name);
  if (!state ||
      std::find(kMotionStates.begin(), kMotionStates.end(), *state) == kMotionStates.end()) {
    throw PolicyError("POLICY_UNKNOWN_FIELD", "states has unknown motion state " + name);
  }
  return *state;
}

void requireAllMotionStates(const std::map<State, StateMotionConfig> & states)
{
  for (const auto state : kMotionStates) {
    if (states.count(state) == 0U) {
      throw PolicyError("POLICY_STATE_MISSING",
                        std::string("motion policy missing state ") + toString(state));
    }
  }
}

void requireAllValidationStates(const std::map<State, StateValidationConfig> & states)
{
  for (const auto state : kMotionStates) {
    if (states.count(state) == 0U) {
      throw PolicyError("POLICY_STATE_MISSING",
                        std::string("validation policy missing state ") + toString(state));
    }
  }
}

TaskObjectConfig parseObject(const YAML::Node & root)
{
  rejectUnknownFields(
    root, {"schema_version", "object_id", "model", "scene", "grasp_frame", "fingertip_pads"},
    "object config");
  TaskObjectConfig result;
  result.schema_version = parseSchemaVersion(root, "object config", 1);
  result.object_id = parseString(requireField(root, "object_id", "object config"), "object_id");

  const auto model = requireField(root, "model", "object config");
  rejectUnknownFields(model,
                      {"mass_kg", "height_m", "outer_radius_m", "wall_thickness_m",
                       "bottom_thickness_m", "side_count", "collision_kind"},
                      "model");
  result.model.mass_kg = parsePositive(requireField(model, "mass_kg", "model"), "mass_kg");
  result.model.height_m = parsePositive(requireField(model, "height_m", "model"), "height_m");
  result.model.outer_radius_m =
    parsePositive(requireField(model, "outer_radius_m", "model"), "outer_radius_m");
  result.model.wall_thickness_m =
    parsePositive(requireField(model, "wall_thickness_m", "model"), "wall_thickness_m");
  result.model.bottom_thickness_m =
    parsePositive(requireField(model, "bottom_thickness_m", "model"), "bottom_thickness_m");
  result.model.side_count = requireField(model, "side_count", "model").as<int>();
  if (result.model.side_count < 3 || result.model.wall_thickness_m >= result.model.outer_radius_m ||
      result.model.bottom_thickness_m >= result.model.height_m) {
    throw PolicyError("POLICY_INVALID_VALUE", "object model dimensions are inconsistent");
  }
  result.model.collision_kind =
    parseString(requireField(model, "collision_kind", "model"), "collision_kind");
  if (result.model.collision_kind != "compound_primitives") {
    throw PolicyError("POLICY_INVALID_VALUE", "collision_kind must be compound_primitives");
  }

  const auto scene = requireField(root, "scene", "object config");
  rejectUnknownFields(
    scene, {"spawn_pose_xyz_xyzw", "place_pose_xyz_xyzw", "reset_parking_pose_xyz_xyzw"}, "scene");
  result.scene.spawn_pose =
    parsePose(requireField(scene, "spawn_pose_xyz_xyzw", "scene"), "spawn_pose_xyz_xyzw");
  result.scene.place_pose =
    parsePose(requireField(scene, "place_pose_xyz_xyzw", "scene"), "place_pose_xyz_xyzw");
  result.scene.reset_parking_pose = parsePose(
    requireField(scene, "reset_parking_pose_xyz_xyzw", "scene"), "reset_parking_pose_xyz_xyzw");

  const auto grasp = requireField(root, "grasp_frame", "object config");
  rejectUnknownFields(grasp,
                      {"near_wall_outward_world", "fixed_finger_side", "moving_jaw_side",
                       "insertion_depth_below_rim_m", "rim_clearance_m", "bottom_clearance_m",
                       "attachment_relative_pose_xyz_xyzw"},
                      "grasp_frame");
  result.grasp_frame.near_wall_outward_world = parseVec3(
    requireField(grasp, "near_wall_outward_world", "grasp_frame"), "near_wall_outward_world");
  const auto & outward = result.grasp_frame.near_wall_outward_world;
  if (std::hypot(outward.x, std::hypot(outward.y, outward.z)) <= 0.0) {
    throw PolicyError("POLICY_INVALID_VALUE", "near_wall_outward_world must be non-zero");
  }
  result.grasp_frame.fixed_finger_side =
    parseString(requireField(grasp, "fixed_finger_side", "grasp_frame"), "fixed_finger_side");
  result.grasp_frame.moving_jaw_side =
    parseString(requireField(grasp, "moving_jaw_side", "grasp_frame"), "moving_jaw_side");
  if (result.grasp_frame.fixed_finger_side != "outside" ||
      result.grasp_frame.moving_jaw_side != "inside") {
    throw PolicyError("POLICY_INVALID_VALUE",
                      "first policy requires fixed outside and moving inside");
  }
  result.grasp_frame.insertion_depth_below_rim_m =
    parseNonNegative(requireField(grasp, "insertion_depth_below_rim_m", "grasp_frame"),
                     "insertion_depth_below_rim_m");
  result.grasp_frame.rim_clearance_m =
    parseNonNegative(requireField(grasp, "rim_clearance_m", "grasp_frame"), "rim_clearance_m");
  result.grasp_frame.bottom_clearance_m = parseNonNegative(
    requireField(grasp, "bottom_clearance_m", "grasp_frame"), "bottom_clearance_m");
  result.grasp_frame.attachment_relative_pose =
    parsePose(requireField(grasp, "attachment_relative_pose_xyz_xyzw", "grasp_frame"),
              "attachment_relative_pose_xyz_xyzw");

  const auto pads = requireField(root, "fingertip_pads", "object config");
  rejectUnknownFields(pads,
                      {"enabled", "material", "shore_hardness_a", "contact_model",
                       "geometry_reference_q6", "safe_lower_q6", "safe_gap_m", "grasp_gap_m",
                       "calibration_fingerprint", "friction_coefficient", "contact_material",
                       "fixed_pad", "moving_pad"},
                      "fingertip_pads");
  auto & pad = result.fingertip_pads;
  pad.enabled = requireField(pads, "enabled", "fingertip_pads").as<bool>();
  pad.material =
    parseString(requireField(pads, "material", "fingertip_pads"), "fingertip_pads.material");
  pad.shore_hardness_a = parsePositive(requireField(pads, "shore_hardness_a", "fingertip_pads"),
                                       "fingertip_pads.shore_hardness_a");
  pad.contact_model = parseString(requireField(pads, "contact_model", "fingertip_pads"),
                                  "fingertip_pads.contact_model");
  pad.geometry_reference_q6 =
    parseFinite(requireField(pads, "geometry_reference_q6", "fingertip_pads"),
                "fingertip_pads.geometry_reference_q6");
  pad.safe_lower_q6 = parseFinite(requireField(pads, "safe_lower_q6", "fingertip_pads"),
                                  "fingertip_pads.safe_lower_q6");
  pad.safe_gap_m =
    parsePositive(requireField(pads, "safe_gap_m", "fingertip_pads"), "fingertip_pads.safe_gap_m");
  pad.grasp_gap_m = parsePositive(requireField(pads, "grasp_gap_m", "fingertip_pads"),
                                  "fingertip_pads.grasp_gap_m");
  pad.calibration_fingerprint =
    parseString(requireField(pads, "calibration_fingerprint", "fingertip_pads"),
                "fingertip_pads.calibration_fingerprint");
  pad.friction_coefficient =
    parsePositive(requireField(pads, "friction_coefficient", "fingertip_pads"),
                  "fingertip_pads.friction_coefficient");
  const auto contact_material = requireField(pads, "contact_material", "fingertip_pads");
  rejectUnknownFields(contact_material,
                      {"axial_friction_coefficient", "transverse_friction_coefficient",
                       "contact_stiffness_n_m", "contact_damping_n_s_m",
                       "max_correcting_velocity_m_s", "min_depth_m"},
                      "fingertip_pads.contact_material");
  auto & contact = pad.contact_material;
  contact.axial_friction_coefficient =
    parsePositive(requireField(contact_material, "axial_friction_coefficient", "contact_material"),
                  "contact_material.axial_friction_coefficient");
  contact.transverse_friction_coefficient = parsePositive(
    requireField(contact_material, "transverse_friction_coefficient", "contact_material"),
    "contact_material.transverse_friction_coefficient");
  contact.contact_stiffness_n_m =
    parsePositive(requireField(contact_material, "contact_stiffness_n_m", "contact_material"),
                  "contact_material.contact_stiffness_n_m");
  contact.contact_damping_n_s_m =
    parsePositive(requireField(contact_material, "contact_damping_n_s_m", "contact_material"),
                  "contact_material.contact_damping_n_s_m");
  contact.max_correcting_velocity_m_s =
    parsePositive(requireField(contact_material, "max_correcting_velocity_m_s", "contact_material"),
                  "contact_material.max_correcting_velocity_m_s");
  contact.min_depth_m =
    parsePositive(requireField(contact_material, "min_depth_m", "contact_material"),
                  "contact_material.min_depth_m");
  pad.fixed_pad = parseFingertipPadGeometry(requireField(pads, "fixed_pad", "fingertip_pads"),
                                            "fingertip_pads.fixed_pad", "z", 1.0, 8U);
  pad.moving_pad = parseFingertipPadGeometry(requireField(pads, "moving_pad", "fingertip_pads"),
                                             "fingertip_pads.moving_pad", "y", -1.0, 7U);
  if (!pad.enabled || pad.material != "TPU_95A" || pad.shore_hardness_a != 95.0 ||
      pad.contact_model != "rigid_link_local_mesh" || pad.safe_gap_m != 0.001 ||
      std::abs(pad.grasp_gap_m - fingertip_pad_calibration::kGraspGapM) > 1e-12) {
    throw PolicyError("POLICY_INVALID_VALUE",
                      "fingertip pads must use the enabled TPU 95A native-only mesh approximation");
  }
  return result;
}

MotionPolicyConfig parseMotion(const YAML::Node & root)
{
  rejectUnknownFields(root,
                      {"schema_version", "policy_id", "object_id", "arm_joints",
                       "approach_outside_clearance_m", "gripper_actions", "states"},
                      "motion policy");
  MotionPolicyConfig result;
  result.schema_version = parseSchemaVersion(root, "motion policy", 1);
  result.policy_id =
    parseString(requireField(root, "policy_id", "motion policy"), "motion policy_id");
  result.object_id =
    parseString(requireField(root, "object_id", "motion policy"), "motion object_id");
  result.arm_joints =
    parseStrings(requireField(root, "arm_joints", "motion policy"), "arm_joints", false);
  if (result.arm_joints.size() != 5U) {
    throw PolicyError("POLICY_INVALID_VALUE", "arm_joints must contain five names");
  }
  result.approach_outside_clearance_m =
    parseNonNegative(requireField(root, "approach_outside_clearance_m", "motion policy"),
                     "approach_outside_clearance_m");
  if (result.approach_outside_clearance_m > 0.010) {
    throw PolicyError("POLICY_INVALID_VALUE", "approach_outside_clearance_m must not exceed 10 mm");
  }
  const auto gripper = requireField(root, "gripper_actions", "motion policy");
  rejectUnknownFields(gripper,
                      {"preopen_q6", "grasp_close_q6", "seating_preload_rad", "release_q6"},
                      "gripper_actions");
  result.gripper_actions.preopen_q6 = parseFinite(
    requireField(gripper, "preopen_q6", "gripper_actions"), "gripper_actions.preopen_q6");
  result.gripper_actions.grasp_close_q6 = parseFinite(
    requireField(gripper, "grasp_close_q6", "gripper_actions"), "gripper_actions.grasp_close_q6");
  result.gripper_actions.close_q6 = result.gripper_actions.grasp_close_q6;
  result.gripper_actions.seating_preload_rad =
    parseNonNegative(requireField(gripper, "seating_preload_rad", "gripper_actions"),
                     "gripper_actions.seating_preload_rad");
  if (result.gripper_actions.seating_preload_rad > 0.006) {
    throw PolicyError("POLICY_INVALID_VALUE",
                      "gripper_actions.seating_preload_rad must be within [0.0, 0.006] rad");
  }
  result.gripper_actions.release_q6 = parseFinite(
    requireField(gripper, "release_q6", "gripper_actions"), "gripper_actions.release_q6");
  if (!(result.gripper_actions.grasp_close_q6 < result.gripper_actions.preopen_q6 &&
        result.gripper_actions.preopen_q6 <= result.gripper_actions.release_q6)) {
    throw PolicyError("POLICY_INVALID_VALUE", "gripper action q6 values are not ordered");
  }
  const auto states = requireField(root, "states", "motion policy");
  requireMap(states, "motion states");
  for (const auto & entry : states) {
    const auto name = parseString(entry.first, "motion state name");
    const auto state = parseRequiredState(name);
    const auto node = entry.second;
    rejectUnknownFields(node,
                        {"logical_start", "waypoints", "require_waypoint_ladder",
                         "require_axial_path_validation", "gripper_q6", "velocity_scaling",
                         "acceleration_scaling"},
                        name);
    StateMotionConfig config;
    config.state = state;
    config.logical_start =
      parseVector(requireField(node, "logical_start", name), 5, name + ".logical_start");
    const auto waypoints = requireField(node, "waypoints", name);
    if (!waypoints.IsSequence() || waypoints.size() == 0U) {
      throw PolicyError("POLICY_INVALID_VALUE", name + ".waypoints must not be empty");
    }
    for (std::size_t index = 0; index < waypoints.size(); ++index) {
      config.waypoints.push_back(
        parseVector(waypoints[index], 5, name + ".waypoints[" + std::to_string(index) + "]"));
    }
    config.require_waypoint_ladder = requireField(node, "require_waypoint_ladder", name).as<bool>();
    config.require_axial_path_validation =
      requireField(node, "require_axial_path_validation", name).as<bool>();
    config.gripper_q6 = parseFinite(requireField(node, "gripper_q6", name), name + ".gripper_q6");
    config.velocity_scaling =
      parsePositive(requireField(node, "velocity_scaling", name), name + ".velocity_scaling");
    config.acceleration_scaling = parsePositive(requireField(node, "acceleration_scaling", name),
                                                name + ".acceleration_scaling");
    if (config.velocity_scaling > 1.0 || config.acceleration_scaling > 1.0) {
      throw PolicyError("POLICY_INVALID_VALUE", name + " motion scaling must not exceed 1");
    }
    result.states.emplace(state, std::move(config));
  }
  requireAllMotionStates(result.states);
  return result;
}

std::optional<TemporalContactPolicy> parseTemporal(const YAML::Node & node,
                                                   const std::string & context)
{
  if (node.IsNull())
    return std::nullopt;
  rejectUnknownFields(node, {"allowed_pairs", "location", "max_axial_clearance_m"}, context);
  TemporalContactPolicy result;
  result.allowed_pairs =
    parseStringSet(requireField(node, "allowed_pairs", context), context + ".allowed_pairs");
  const auto location = parseString(requireField(node, "location", context), context + ".location");
  if (location == "FIRST_ONLY")
    result.location = TemporalContactLocation::FIRST_ONLY;
  else if (location == "LAST_ONLY")
    result.location = TemporalContactLocation::LAST_ONLY;
  else if (location == "PREFIX_UNTIL_AXIAL_CLEARANCE") {
    result.location = TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE;
  } else {
    throw PolicyError("POLICY_INVALID_VALUE", context + ".location is invalid");
  }
  result.max_axial_clearance_m = parseNonNegative(
    requireField(node, "max_axial_clearance_m", context), context + ".max_axial_clearance_m");
  return result;
}

bool isCalibrationRequired(const YAML::Node & node)
{
  return node.IsScalar() && node.as<std::string>() == "CALIBRATION_REQUIRED";
}

std::array<double, 2> parseFinitePair(const YAML::Node & node, const std::string & context)
{
  const auto values = parseVector(node, 2, context);
  return {values[0], values[1]};
}

std::array<double, 6> parseFiniteBounds(const YAML::Node & node, const std::string & context)
{
  const auto values = parseVector(node, 6, context);
  return {values[0], values[1], values[2], values[3], values[4], values[5]};
}

std::size_t parsePositiveSize(const YAML::Node & node, const std::string & context)
{
  if (!node.IsScalar()) {
    throw PolicyError("POLICY_INVALID_VALUE", context + " must be a positive integer");
  }
  const auto value = node.as<long long>();
  if (value <= 0) {
    throw PolicyError("POLICY_INVALID_VALUE", context + " must be a positive integer");
  }
  return static_cast<std::size_t>(value);
}

PhysicalOutcomePolicyConfig parsePhysicalOutcome(const YAML::Node & node)
{
  constexpr std::string_view context = "physical_outcome";
  rejectUnknownFields(node,
                      {"intended_support_collision", "minimum_support_contact_depth_m",
                       "final_target_region", "support_height_range_m", "max_upright_tilt_rad",
                       "max_linear_speed_m_s", "max_angular_speed_rad_s", "consecutive_samples",
                       "minimum_stable_duration_s", "sample_interval_s", "settle_timeout_s",
                       "max_observation_age_s", "max_telemetry_samples", "catastrophic_loss",
                       "planning_shadow"},
                      context);
  PhysicalOutcomePolicyConfig result;
  result.intended_support_collision =
    parseString(requireField(node, "intended_support_collision", context),
                "physical_outcome.intended_support_collision");
  if (result.intended_support_collision != "table::table_top::collision") {
    throw PolicyError("POLICY_INVALID_VALUE", "physical_outcome.intended_support_collision must be "
                                              "table::table_top::collision");
  }

  const std::array<const char *, 12> direct_thresholds{"minimum_support_contact_depth_m",
                                                       "final_target_region",
                                                       "support_height_range_m",
                                                       "max_upright_tilt_rad",
                                                       "max_linear_speed_m_s",
                                                       "max_angular_speed_rad_s",
                                                       "consecutive_samples",
                                                       "minimum_stable_duration_s",
                                                       "sample_interval_s",
                                                       "settle_timeout_s",
                                                       "max_observation_age_s",
                                                       "max_telemetry_samples"};
  const auto catastrophic = requireField(node, "catastrophic_loss", context);
  rejectUnknownFields(
    catastrophic,
    {"workspace_bounds_m", "max_relative_position_drift_m", "max_relative_orientation_drift_rad"},
    "physical_outcome.catastrophic_loss");
  const auto shadow = requireField(node, "planning_shadow", context);
  rejectUnknownFields(
    shadow, {"max_position_divergence_m", "max_orientation_divergence_rad", "max_pair_age_s"},
    "physical_outcome.planning_shadow");

  std::size_t sentinel_count = 0;
  for (const auto * field : direct_thresholds) {
    sentinel_count += isCalibrationRequired(requireField(node, field, context)) ? 1U : 0U;
  }
  for (const auto * field : {"workspace_bounds_m", "max_relative_position_drift_m",
                             "max_relative_orientation_drift_rad"}) {
    sentinel_count +=
      isCalibrationRequired(requireField(catastrophic, field, "physical_outcome.catastrophic_loss"))
        ? 1U
        : 0U;
  }
  for (const auto * field :
       {"max_position_divergence_m", "max_orientation_divergence_rad", "max_pair_age_s"}) {
    sentinel_count +=
      isCalibrationRequired(requireField(shadow, field, "physical_outcome.planning_shadow")) ? 1U
                                                                                             : 0U;
  }
  constexpr std::size_t threshold_count = 18U;
  if (sentinel_count != 0U && sentinel_count != threshold_count) {
    throw PolicyError("POLICY_INVALID_VALUE",
                      "physical_outcome cannot mix CALIBRATION_REQUIRED and numeric thresholds");
  }
  if (sentinel_count == threshold_count) {
    return result;
  }

  result.minimum_support_contact_depth_m =
    parseNonPositive(requireField(node, "minimum_support_contact_depth_m", context),
                     "physical_outcome.minimum_support_contact_depth_m");

  const auto region = requireField(node, "final_target_region", context);
  rejectUnknownFields(region, {"kind", "min_xy_m", "max_xy_m"},
                      "physical_outcome.final_target_region");
  if (parseString(requireField(region, "kind", "physical_outcome.final_target_region"),
                  "physical_outcome.final_target_region.kind") != "axis_aligned_box") {
    throw PolicyError("POLICY_INVALID_VALUE",
                      "physical_outcome.final_target_region.kind must be axis_aligned_box");
  }
  const auto min_xy =
    parseFinitePair(requireField(region, "min_xy_m", "physical_outcome.final_target_region"),
                    "physical_outcome.final_target_region.min_xy_m");
  const auto max_xy =
    parseFinitePair(requireField(region, "max_xy_m", "physical_outcome.final_target_region"),
                    "physical_outcome.final_target_region.max_xy_m");
  if (!(min_xy[0] < max_xy[0] && min_xy[1] < max_xy[1])) {
    throw PolicyError("POLICY_INVALID_VALUE",
                      "physical_outcome.final_target_region bounds must be ordered");
  }
  result.final_target_region = {min_xy[0], min_xy[1], max_xy[0], max_xy[1]};
  result.support_height_range_m =
    parseFinitePair(requireField(node, "support_height_range_m", context),
                    "physical_outcome.support_height_range_m");
  if (!((*result.support_height_range_m)[0] < (*result.support_height_range_m)[1])) {
    throw PolicyError("POLICY_INVALID_VALUE",
                      "physical_outcome.support_height_range_m must be ordered");
  }
  result.max_upright_tilt_rad = parsePositive(requireField(node, "max_upright_tilt_rad", context),
                                              "physical_outcome.max_upright_tilt_rad");
  result.max_linear_speed_m_s = parsePositive(requireField(node, "max_linear_speed_m_s", context),
                                              "physical_outcome.max_linear_speed_m_s");
  result.max_angular_speed_rad_s =
    parsePositive(requireField(node, "max_angular_speed_rad_s", context),
                  "physical_outcome.max_angular_speed_rad_s");
  result.consecutive_samples = parsePositiveSize(requireField(node, "consecutive_samples", context),
                                                 "physical_outcome.consecutive_samples");
  result.minimum_stable_duration_s =
    parsePositive(requireField(node, "minimum_stable_duration_s", context),
                  "physical_outcome.minimum_stable_duration_s");
  result.sample_interval_s = parsePositive(requireField(node, "sample_interval_s", context),
                                           "physical_outcome.sample_interval_s");
  result.settle_timeout_s = parsePositive(requireField(node, "settle_timeout_s", context),
                                          "physical_outcome.settle_timeout_s");
  result.max_observation_age_s = parsePositive(requireField(node, "max_observation_age_s", context),
                                               "physical_outcome.max_observation_age_s");
  result.max_telemetry_samples = parsePositiveSize(
    requireField(node, "max_telemetry_samples", context), "physical_outcome.max_telemetry_samples");
  if (*result.settle_timeout_s < *result.minimum_stable_duration_s) {
    throw PolicyError("POLICY_INVALID_VALUE",
                      "physical_outcome.settle_timeout_s must cover minimum_stable_duration_s");
  }

  result.catastrophic_loss.workspace_bounds_m = parseFiniteBounds(
    requireField(catastrophic, "workspace_bounds_m", "physical_outcome.catastrophic_loss"),
    "physical_outcome.catastrophic_loss.workspace_bounds_m");
  const auto & bounds = *result.catastrophic_loss.workspace_bounds_m;
  if (!(bounds[0] < bounds[3] && bounds[1] < bounds[4] && bounds[2] < bounds[5])) {
    throw PolicyError("POLICY_INVALID_VALUE",
                      "physical_outcome catastrophic workspace bounds must be ordered");
  }
  result.catastrophic_loss.max_relative_position_drift_m =
    parsePositive(requireField(catastrophic, "max_relative_position_drift_m",
                               "physical_outcome.catastrophic_loss"),
                  "physical_outcome.catastrophic_loss.max_relative_position_drift_m");
  result.catastrophic_loss.max_relative_orientation_drift_rad =
    parsePositive(requireField(catastrophic, "max_relative_orientation_drift_rad",
                               "physical_outcome.catastrophic_loss"),
                  "physical_outcome.catastrophic_loss.max_relative_orientation_drift_rad");
  result.planning_shadow.max_position_divergence_m = parsePositive(
    requireField(shadow, "max_position_divergence_m", "physical_outcome.planning_shadow"),
    "physical_outcome.planning_shadow.max_position_divergence_m");
  result.planning_shadow.max_orientation_divergence_rad = parsePositive(
    requireField(shadow, "max_orientation_divergence_rad", "physical_outcome.planning_shadow"),
    "physical_outcome.planning_shadow.max_orientation_divergence_rad");
  result.planning_shadow.max_pair_age_s =
    parsePositive(requireField(shadow, "max_pair_age_s", "physical_outcome.planning_shadow"),
                  "physical_outcome.planning_shadow.max_pair_age_s");
  result.calibration_complete = true;
  return result;
}

ValidationPolicyConfig parseValidation(const YAML::Node & root)
{
  rejectUnknownFields(root,
                      {"schema_version", "policy_id", "object_id", "grasp_contact", "runtime",
                       "physical_outcome", "states"},
                      "validation policy");
  ValidationPolicyConfig result;
  result.schema_version = parseSchemaVersion(root, "validation policy", 2);
  result.policy_id =
    parseString(requireField(root, "policy_id", "validation policy"), "validation policy_id");
  result.object_id =
    parseString(requireField(root, "object_id", "validation policy"), "validation object_id");
  const auto grasp = requireField(root, "grasp_contact", "validation policy");
  rejectUnknownFields(grasp,
                      {"require_fixed_finger", "require_moving_jaw", "required_wall_collision",
                       "fixed_surface", "moving_surface", "max_penetration_m", "min_below_rim_m",
                       "max_below_rim_m", "min_bottom_clearance_m", "forbidden_collisions"},
                      "grasp_contact");
  auto & contact = result.grasp_contact;
  contact.require_fixed_finger =
    requireField(grasp, "require_fixed_finger", "grasp_contact").as<bool>();
  contact.require_moving_jaw =
    requireField(grasp, "require_moving_jaw", "grasp_contact").as<bool>();
  contact.required_wall_collision =
    parseString(requireField(grasp, "required_wall_collision", "grasp_contact"),
                "grasp_contact.required_wall_collision");
  contact.fixed_surface = parseString(requireField(grasp, "fixed_surface", "grasp_contact"),
                                      "grasp_contact.fixed_surface");
  contact.moving_surface = parseString(requireField(grasp, "moving_surface", "grasp_contact"),
                                       "grasp_contact.moving_surface");
  contact.max_penetration_m = parseNonNegative(
    requireField(grasp, "max_penetration_m", "grasp_contact"), "grasp_contact.max_penetration_m");
  contact.min_below_rim_m = parseNonNegative(
    requireField(grasp, "min_below_rim_m", "grasp_contact"), "grasp_contact.min_below_rim_m");
  contact.max_below_rim_m = parsePositive(requireField(grasp, "max_below_rim_m", "grasp_contact"),
                                          "grasp_contact.max_below_rim_m");
  contact.min_bottom_clearance_m =
    parseNonNegative(requireField(grasp, "min_bottom_clearance_m", "grasp_contact"),
                     "grasp_contact.min_bottom_clearance_m");
  contact.forbidden_collisions =
    parseStrings(requireField(grasp, "forbidden_collisions", "grasp_contact"),
                 "grasp_contact.forbidden_collisions", false);
  if (!contact.require_fixed_finger || !contact.require_moving_jaw ||
      contact.fixed_surface != "outside" || contact.moving_surface != "inside" ||
      contact.max_penetration_m <= 0.0 || contact.min_below_rim_m >= contact.max_below_rim_m) {
    throw PolicyError("POLICY_INVALID_VALUE", "grasp_contact first policy is inconsistent");
  }

  const auto runtime = requireField(root, "runtime", "validation policy");
  rejectUnknownFields(runtime,
                      {"min_real_time_factor", "q6_velocity_tolerance_rad_s",
                       "q6_position_tolerance_rad", "q6_contact_stop_tolerance_rad"},
                      "runtime");
  result.runtime.min_real_time_factor = parsePositive(
    requireField(runtime, "min_real_time_factor", "runtime"), "runtime.min_real_time_factor");
  result.runtime.q6_velocity_tolerance_rad_s =
    parsePositive(requireField(runtime, "q6_velocity_tolerance_rad_s", "runtime"),
                  "runtime.q6_velocity_tolerance_rad_s");
  result.runtime.q6_position_tolerance_rad =
    parsePositive(requireField(runtime, "q6_position_tolerance_rad", "runtime"),
                  "runtime.q6_position_tolerance_rad");
  result.runtime.q6_contact_stop_tolerance_rad =
    parsePositive(requireField(runtime, "q6_contact_stop_tolerance_rad", "runtime"),
                  "runtime.q6_contact_stop_tolerance_rad");
  if (result.runtime.min_real_time_factor > 1.0) {
    throw PolicyError("POLICY_INVALID_VALUE", "runtime.min_real_time_factor must not exceed 1");
  }
  result.physical_outcome =
    parsePhysicalOutcome(requireField(root, "physical_outcome", "validation policy"));
  const auto states = requireField(root, "states", "validation policy");
  requireMap(states, "validation states");
  for (const auto & entry : states) {
    const auto name = parseString(entry.first, "validation state name");
    const auto state = parseRequiredState(name);
    const auto node = entry.second;
    rejectUnknownFields(node,
                        {"endpoint_position", "local_approach_axis", "target_approach_axis",
                         "path_direction", "position_tolerance_m", "axis_tolerance_rad",
                         "max_lateral_deviation_m", "max_joint_jump_rad",
                         "joint_endpoint_tolerance_rad", "min_duration_s",
                         "contact_wall_normal_endpoint_tolerance_m", "monotonic_tolerance_m",
                         "allowed_touch_pairs", "temporal_contact"},
                        name);
    StateValidationConfig config;
    config.state = state;
    auto & motion = config.motion;
    motion.endpoint_position =
      parseVec3(requireField(node, "endpoint_position", name), name + ".endpoint_position");
    motion.local_approach_axis =
      parseVec3(requireField(node, "local_approach_axis", name), name + ".local_approach_axis");
    motion.target_approach_axis =
      parseVec3(requireField(node, "target_approach_axis", name), name + ".target_approach_axis");
    motion.path_direction =
      parseVec3(requireField(node, "path_direction", name), name + ".path_direction");
    motion.position_tolerance = parseNonNegative(requireField(node, "position_tolerance_m", name),
                                                 name + ".position_tolerance_m");
    motion.axis_tolerance_rad = parseNonNegative(requireField(node, "axis_tolerance_rad", name),
                                                 name + ".axis_tolerance_rad");
    motion.max_lateral_deviation = parseNonNegative(
      requireField(node, "max_lateral_deviation_m", name), name + ".max_lateral_deviation_m");
    motion.max_joint_jump = parseNonNegative(requireField(node, "max_joint_jump_rad", name),
                                             name + ".max_joint_jump_rad");
    motion.joint_endpoint_tolerance =
      parseNonNegative(requireField(node, "joint_endpoint_tolerance_rad", name),
                       name + ".joint_endpoint_tolerance_rad");
    if (node["contact_wall_normal_endpoint_tolerance_m"]) {
      motion.contact_wall_normal_endpoint_tolerance =
        parsePositive(node["contact_wall_normal_endpoint_tolerance_m"],
                      name + ".contact_wall_normal_endpoint_tolerance_m");
    }
    motion.min_duration_seconds =
      parsePositive(requireField(node, "min_duration_s", name), name + ".min_duration_s");
    motion.monotonic_tolerance = parseNonNegative(requireField(node, "monotonic_tolerance_m", name),
                                                  name + ".monotonic_tolerance_m");
    motion.allowed_touch_pairs = parseStringSet(requireField(node, "allowed_touch_pairs", name),
                                                name + ".allowed_touch_pairs");
    motion.temporal_contact_policy =
      parseTemporal(requireField(node, "temporal_contact", name), name + ".temporal_contact");
    result.states.emplace(state, std::move(config));
  }
  requireAllValidationStates(result.states);
  return result;
}

std::string readBytes(const std::filesystem::path & path)
{
  std::ifstream input(path, std::ios::binary);
  if (!input)
    throw PolicyError("POLICY_FILE_MISSING", "cannot read policy file " + path.string());
  return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

std::string sha256(const std::string & bytes)
{
  using Context = std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)>;
  Context context(EVP_MD_CTX_new(), EVP_MD_CTX_free);
  if (!context || EVP_DigestInit_ex(context.get(), EVP_sha256(), nullptr) != 1 ||
      EVP_DigestUpdate(context.get(), bytes.data(), bytes.size()) != 1) {
    throw PolicyError("POLICY_INVALID_VALUE", "unable to compute policy SHA-256");
  }
  std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
  unsigned int size = 0;
  if (EVP_DigestFinal_ex(context.get(), digest.data(), &size) != 1 || size != 32U) {
    throw PolicyError("POLICY_INVALID_VALUE", "unable to finalize policy SHA-256");
  }
  std::ostringstream output;
  output << std::hex << std::setfill('0');
  for (unsigned int index = 0; index < size; ++index) {
    output << std::setw(2) << static_cast<unsigned int>(digest[index]);
  }
  return output.str();
}

std::filesystem::path canonicalPolicyPath(const std::string & raw)
{
  if (raw.empty() || !std::filesystem::exists(raw)) {
    throw PolicyError("POLICY_FILE_MISSING", "policy file does not exist: " + raw);
  }
  return std::filesystem::canonical(raw);
}

}  // namespace

PolicyLoadResult loadPolicyBundle(const PolicyPaths & paths)
{
  try {
    LoadedPolicyBundle bundle;
    bundle.object_path = canonicalPolicyPath(paths.object);
    bundle.motion_path = canonicalPolicyPath(paths.motion);
    bundle.validation_path = canonicalPolicyPath(paths.validation);
    const std::array<std::string, 3> bytes{readBytes(bundle.object_path),
                                           readBytes(bundle.motion_path),
                                           readBytes(bundle.validation_path)};
    bundle.object = parseObject(YAML::Load(bytes[0]));
    bundle.motion = parseMotion(YAML::Load(bytes[1]));
    bundle.validation = parseValidation(YAML::Load(bytes[2]));
    if (bundle.object.object_id != bundle.motion.object_id ||
        bundle.object.object_id != bundle.validation.object_id) {
      throw PolicyError("POLICY_ID_MISMATCH", "object_id differs across policy files");
    }
    if (bundle.motion.policy_id != bundle.validation.policy_id) {
      throw PolicyError("POLICY_ID_MISMATCH", "policy_id differs across motion and validation");
    }
    const auto & pad = bundle.object.fingertip_pads;
    const auto & actions = bundle.motion.gripper_actions;
    if (!(pad.safe_lower_q6 <= actions.grasp_close_q6 &&
          actions.grasp_close_q6 < actions.preopen_q6 &&
          actions.preopen_q6 <= actions.release_q6)) {
      throw PolicyError("POLICY_INVALID_VALUE", "fingertip-pad q6 commands are not ordered");
    }
    for (std::size_t index = 0; index < bytes.size(); ++index) {
      bundle.sha256[index] = sha256(bytes[index]);
    }
    bundle.bundle_sha256 =
      sha256(bundle.sha256[0] + "\n" + bundle.sha256[1] + "\n" + bundle.sha256[2] + "\n");
    return {std::move(bundle), std::nullopt};
  } catch (const PolicyError & error) {
    return {std::nullopt, failure(error.code, error.what())};
  } catch (const YAML::Exception & error) {
    return {std::nullopt, failure("POLICY_INVALID_VALUE", error.what())};
  } catch (const std::exception & error) {
    return {std::nullopt, failure("POLICY_INVALID_VALUE", error.what())};
  }
}

}  // namespace so101_gazebo_demo::pick_place
