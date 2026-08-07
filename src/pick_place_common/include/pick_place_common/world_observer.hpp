#pragma once
#include <chrono>
#include <cstdint>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>
#include "pick_place_common/domain_types.hpp"
#include "pick_place_common/pose_geometry.hpp"
namespace pick_place_common
{
struct ContactVector3
{
  double x{0.0};
  double y{0.0};
  double z{0.0};
};
struct TaskObjectContactSample
{
  std::string task_object_collision;
  std::string finger_collision;
  ContactVector3 point_world;
  ContactVector3 normal_toward_finger_world;
  ContactVector3 point_task_object;
  ContactVector3 normal_toward_finger_task_object;
  double depth{0.0};
};
struct TaskObjectSupportContactSample
{
  std::string task_object_collision;
  std::string support_collision;
  ContactVector3 point_world;
  ContactVector3 normal_toward_support_world;
  double depth{0.0};
  std::chrono::steady_clock::time_point observed_at{};
};
struct WorldSnapshot
{
  std::chrono::steady_clock::time_point observed_at{};
  bool fresh{false};
  bool arm_stationary{false};
  bool gripper_open{false};
  Pose3d tcp_pose_world{};
  std::map<std::string, double> joint_positions;
  std::map<std::string, double> joint_velocities;
  std::map<std::string, Pose3d> moveit_world_object_poses;
  std::optional<bool> moveit_task_object_attached;
  std::optional<std::string> moveit_task_object_attached_link;
  std::set<std::string> moveit_task_object_touch_links;
  std::optional<Pose3d> moveit_task_object_attached_relative_pose;
  std::optional<Pose3d> moveit_gripper_pose_world;
  std::optional<Pose3d> gazebo_task_object_pose_world;
  std::optional<std::uint64_t> gazebo_pose_sequence;
  std::optional<std::chrono::steady_clock::time_point> gazebo_pose_observed_at;
  std::optional<bool> gazebo_task_object_attached;
  std::optional<bool> gazebo_task_object_stationary;
  std::optional<bool> gazebo_task_object_gripper_contact;
  std::optional<bool> gazebo_task_object_fixed_finger_contact;
  std::optional<bool> gazebo_task_object_moving_jaw_contact;
  std::optional<double> gazebo_task_object_gripper_max_depth;
  std::set<std::string> gazebo_task_object_gripper_collision_names;
  std::optional<double> gazebo_task_object_fixed_contact_min_height;
  std::optional<double> gazebo_task_object_fixed_contact_max_height;
  std::optional<double> gazebo_task_object_moving_contact_min_height;
  std::optional<double> gazebo_task_object_moving_contact_max_height;
  std::vector<TaskObjectContactSample> gazebo_task_object_fixed_finger_contacts;
  std::vector<TaskObjectContactSample> gazebo_task_object_moving_jaw_contacts;
  std::optional<std::chrono::steady_clock::time_point> gazebo_gripper_contact_observed_at;
  std::optional<bool> gazebo_task_object_intended_support_contact;
  std::set<std::string> gazebo_task_object_support_collision_names;
  std::vector<TaskObjectSupportContactSample> gazebo_task_object_support_contacts;
  std::optional<std::chrono::steady_clock::time_point> gazebo_support_contact_observed_at;
  std::optional<double> gazebo_task_object_linear_speed_m_s;
  std::optional<double> gazebo_task_object_angular_speed_rad_s;
  std::string simulation_session_id;
};
struct ObservationResult
{
  std::optional<WorldSnapshot> snapshot;
  std::optional<Failure> failure;
};
class IWorldObserver
{
public:
  virtual ~IWorldObserver() = default;
  virtual ObservationResult observe() = 0;
};
}  // namespace pick_place_common
