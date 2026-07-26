#pragma once
#include <chrono>
#include <map>
#include <optional>
#include <set>
#include <string>
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
  std::optional<bool> moveit_coke_attached;
  std::optional<std::string> moveit_coke_attached_link;
  std::set<std::string> moveit_coke_touch_links;
  std::optional<Pose3d> gazebo_coke_pose_world;
  std::optional<bool> gazebo_coke_attached;
  std::optional<bool> gazebo_coke_stationary;
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
