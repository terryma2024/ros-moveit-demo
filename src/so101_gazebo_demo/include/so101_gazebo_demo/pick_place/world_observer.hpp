#pragma once
#include <chrono>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>
#include "so101_gazebo_demo/pick_place/domain_types.hpp"
namespace so101_gazebo_demo::pick_place
{
struct Pose3d
{
  double x{0};
  double y{0};
  double z{0};
  double qx{0};
  double qy{0};
  double qz{0};
  double qw{1};
};
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
}  // namespace so101_gazebo_demo::pick_place
