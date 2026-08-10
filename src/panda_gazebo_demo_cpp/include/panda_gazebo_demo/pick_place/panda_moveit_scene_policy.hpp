#pragma once

#include <pick_place_common/moveit_scene_executor.hpp>

#include "panda_gazebo_demo/pick_place/state_action.hpp"
#include "panda_gazebo_demo/pick_place/state_validation.hpp"

namespace panda_gazebo_demo::pick_place
{
class PandaMoveItScenePolicy final : public pick_place_common::ros_adapters::IMoveItScenePolicy
{
public:
  PandaMoveItScenePolicy(GripperLimits gripper_limits, bool idempotent) :
      gripper_limits_(gripper_limits), idempotent_(idempotent)
  {
  }

  [[nodiscard]] pick_place_common::ros_adapters::ScenePreparation
  prepare(pick_place_common::ros_adapters::MoveItSceneOperation operation,
          const pick_place_common::ExecutionContext & context) const override;

private:
  GripperLimits gripper_limits_;
  bool idempotent_;
};
}  // namespace panda_gazebo_demo::pick_place
