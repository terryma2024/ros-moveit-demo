#pragma once

#include <array>
#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include "so101_gazebo_demo/pick_place/so101_motion_validation.hpp"

namespace so101_gazebo_demo::pick_place
{

struct PolicyPaths
{
  std::string object;
  std::string motion;
  std::string validation;
};

struct TaskObjectModelConfig
{
  double mass_kg{0.0};
  double height_m{0.0};
  double outer_radius_m{0.0};
  double wall_thickness_m{0.0};
  double bottom_thickness_m{0.0};
  int side_count{0};
  std::string collision_kind;
};

struct TaskObjectSceneConfig
{
  Pose3d spawn_pose;
  Pose3d place_pose;
  Pose3d reset_parking_pose;
};

struct TaskObjectGraspFrameConfig
{
  Vec3 near_wall_outward_world;
  std::string fixed_finger_side;
  std::string moving_jaw_side;
  double insertion_depth_below_rim_m{0.0};
  double rim_clearance_m{0.0};
  double bottom_clearance_m{0.0};
  Pose3d attachment_relative_pose;
};

struct FingertipPadGeometryConfig
{
  double opening_axis_thickness_m{0.0};
  double contact_direction_x{0.0};
  std::string axial_axis;
  std::array<double, 2> native_axial_bounds_m{};
  std::vector<Vec3> profile_points;
};

struct FingertipPadConfig
{
  bool enabled{false};
  std::string material;
  double shore_hardness_a{0.0};
  std::string contact_model;
  double geometry_reference_q6{0.0};
  double safe_lower_q6{0.0};
  double safe_gap_m{0.0};
  double grasp_gap_m{0.0};
  std::string calibration_fingerprint;
  double friction_coefficient{0.0};
  FingertipPadGeometryConfig fixed_pad;
  FingertipPadGeometryConfig moving_pad;
};

struct TaskObjectConfig
{
  int schema_version{0};
  std::string object_id;
  TaskObjectModelConfig model;
  TaskObjectSceneConfig scene;
  TaskObjectGraspFrameConfig grasp_frame;
  FingertipPadConfig fingertip_pads;
};

struct StateMotionConfig
{
  State state{State::ERROR};
  std::vector<double> logical_start;
  std::vector<std::vector<double>> waypoints;
  // Planner waypoint usage and TCP axial-path validation are deliberately
  // independent: transfers may need collision-safe joint waypoints without
  // being a straight approach/descent path.
  bool require_waypoint_ladder{false};
  bool require_axial_path_validation{false};
  double gripper_q6{0.0};
  double velocity_scaling{0.1};
  double acceleration_scaling{0.1};
};

struct MotionPolicyConfig
{
  struct GripperActions
  {
    double preopen_q6{0.0};
    double grasp_close_q6{0.0};
    // Temporary source-compatibility alias while runtime consumers migrate to
    // grasp_close_q6. It is never read from YAML.
    double close_q6{0.0};
    double release_q6{0.0};
  };

  int schema_version{0};
  std::string policy_id;
  std::string object_id;
  std::vector<std::string> arm_joints;
  double approach_outside_clearance_m{0.0};
  GripperActions gripper_actions;
  std::map<State, StateMotionConfig> states;
};

struct StateValidationConfig
{
  State state{State::ERROR};
  MotionValidationConfig motion;
};

struct GraspContactValidationConfig
{
  bool require_fixed_finger{false};
  bool require_moving_jaw{false};
  std::string required_wall_collision;
  std::string fixed_surface;
  std::string moving_surface;
  double max_penetration_m{0.0};
  double min_below_rim_m{0.0};
  double max_below_rim_m{0.0};
  double min_bottom_clearance_m{0.0};
  std::vector<std::string> forbidden_collisions;
};

struct RuntimeValidationConfig
{
  double min_real_time_factor{0.0};
  double q6_velocity_tolerance_rad_s{0.0};
  double q6_position_tolerance_rad{0.0};
  double q6_contact_stop_tolerance_rad{0.0};
};

struct ValidationPolicyConfig
{
  int schema_version{0};
  std::string policy_id;
  std::string object_id;
  GraspContactValidationConfig grasp_contact;
  RuntimeValidationConfig runtime;
  std::map<State, StateValidationConfig> states;
};

struct LoadedPolicyBundle
{
  TaskObjectConfig object;
  MotionPolicyConfig motion;
  ValidationPolicyConfig validation;
  std::filesystem::path object_path;
  std::filesystem::path motion_path;
  std::filesystem::path validation_path;
  std::array<std::string, 3> sha256;
  std::string bundle_sha256;
};

struct PolicyLoadResult
{
  std::optional<LoadedPolicyBundle> bundle;
  std::optional<Failure> failure;
};

[[nodiscard]] PolicyLoadResult loadPolicyBundle(const PolicyPaths & paths);

}  // namespace so101_gazebo_demo::pick_place
