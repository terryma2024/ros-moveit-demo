#pragma once

#include <memory>

#include "panda_gazebo_demo/pick_place/moveit_scene_adapter.hpp"

namespace panda_gazebo_demo::pick_place
{

class MoveItWorldResetter
{
public:
  MoveItWorldResetter(std::shared_ptr<IMoveItSceneAdapter> adapter, double timeout_seconds = 2.0,
                      double poll_interval_seconds = 0.05);

  [[nodiscard]] ActionResult reset(const Pose3d & target_pose);

private:
  std::shared_ptr<IMoveItSceneAdapter> adapter_;
  double timeout_seconds_;
  double poll_interval_seconds_;
};

}  // namespace panda_gazebo_demo::pick_place
