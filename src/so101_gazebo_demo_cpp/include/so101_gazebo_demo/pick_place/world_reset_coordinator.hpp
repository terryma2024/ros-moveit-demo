#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <vector>

#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "so101_gazebo_demo/pick_place/so101_joint_motion_adapter.hpp"

namespace so101_gazebo_demo::pick_place
{

struct GazeboResetState
{
  bool task_object_attached{false};
  Pose3d task_object_world_pose;
  std::uint64_t pose_revision{0};
  std::uint64_t attachment_revision{0};
};

class IGazeboResetAdapter
{
public:
  virtual ~IGazeboResetAdapter() = default;
  [[nodiscard]] virtual std::optional<GazeboResetState> observe() = 0;
  [[nodiscard]] virtual ActionResult detachTaskObject() = 0;
  [[nodiscard]] virtual ActionResult setTaskObjectWorldPose(const Pose3d & pose) = 0;
};

class IRobotHomeResetAdapter
{
public:
  virtual ~IRobotHomeResetAdapter() = default;
  [[nodiscard]] virtual std::optional<CurrentJointStateEvidence> observeJoints() = 0;
  [[nodiscard]] virtual ActionResult commandGripper(double q6) = 0;
  [[nodiscard]] virtual PlanResult planArmHome(const std::vector<double> & goal) = 0;
  [[nodiscard]] virtual ActionResult executeArmHome(const PlanArtifact & plan) = 0;
  [[nodiscard]] virtual ActionResult cancelArmAndWait() = 0;
};

struct WorldResetConfig
{
  Pose3d table_pose;
  Pose3d pedestal_pose;
  Pose3d task_object_pose;
  Pose3d reset_parking_task_object_pose;
  double timeout_seconds{2.0};
  double poll_interval_seconds{0.05};
  double position_tolerance{0.002};
  double orientation_tolerance_rad{0.02};
  std::vector<std::string> arm_joints{"1", "2", "3", "4", "5"};
  std::vector<double> arm_home_positions{0.0, 0.0, 0.0, 0.0, 0.0};
  std::string gripper_joint{"6"};
  double q6_release_position{1.7};
  double q6_safe_lower{-0.059600220867817};
  double q6_home_position{-0.059600220867817};
  double arm_joint_position_tolerance{0.002};
  double gripper_position_tolerance{0.001};
  double joint_velocity_tolerance{0.01};
};

class WorldResetCoordinator
{
public:
  WorldResetCoordinator(std::shared_ptr<IGazeboResetAdapter> gazebo,
                        std::shared_ptr<ISO101MoveItSceneAdapter> moveit,
                        std::shared_ptr<IRobotHomeResetAdapter> robot, WorldResetConfig config);

  [[nodiscard]] ActionResult reset();

private:
  std::shared_ptr<IGazeboResetAdapter> gazebo_;
  std::shared_ptr<ISO101MoveItSceneAdapter> moveit_;
  std::shared_ptr<IRobotHomeResetAdapter> robot_;
  WorldResetConfig config_;
};

}  // namespace so101_gazebo_demo::pick_place
