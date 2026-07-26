#pragma once

#include <cstdint>
#include <memory>
#include <optional>

#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"

namespace so101_gazebo_demo::pick_place
{

struct GazeboResetState
{
  bool coke_attached{false};
  Pose3d coke_world_pose;
  std::uint64_t pose_revision{0};
  std::uint64_t attachment_revision{0};
};

class IGazeboResetAdapter
{
public:
  virtual ~IGazeboResetAdapter() = default;
  [[nodiscard]] virtual std::optional<GazeboResetState> observe() = 0;
  [[nodiscard]] virtual ActionResult detachCoke() = 0;
  [[nodiscard]] virtual ActionResult setCokeWorldPose(const Pose3d & pose) = 0;
};

struct WorldResetConfig
{
  Pose3d table_pose;
  Pose3d coke_pose;
  double timeout_seconds{2.0};
  double poll_interval_seconds{0.05};
  double position_tolerance{0.002};
  double orientation_tolerance_rad{0.02};
};

class WorldResetCoordinator
{
public:
  WorldResetCoordinator(std::shared_ptr<IGazeboResetAdapter> gazebo,
                        std::shared_ptr<IMoveItSceneAdapter> moveit, WorldResetConfig config);

  [[nodiscard]] ActionResult reset();

private:
  std::shared_ptr<IGazeboResetAdapter> gazebo_;
  std::shared_ptr<IMoveItSceneAdapter> moveit_;
  WorldResetConfig config_;
};

}  // namespace so101_gazebo_demo::pick_place
