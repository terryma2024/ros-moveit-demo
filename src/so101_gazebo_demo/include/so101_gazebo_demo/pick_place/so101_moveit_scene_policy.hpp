#pragma once

#include <string>
#include <utility>

#include <pick_place_common/moveit_scene_executor.hpp>

#include "so101_gazebo_demo/pick_place/state_action.hpp"

namespace so101_gazebo_demo::pick_place
{
class SO101MoveItScenePolicy final : public pick_place_common::ros_adapters::IMoveItScenePolicy
{
public:
  SO101MoveItScenePolicy(std::string task_object_id, bool idempotent) :
      task_object_id_(std::move(task_object_id)), idempotent_(idempotent)
  {
  }

  [[nodiscard]] pick_place_common::ros_adapters::ScenePreparation
  prepare(pick_place_common::ros_adapters::MoveItSceneOperation operation,
          const pick_place_common::ExecutionContext & context) const override;

private:
  std::string task_object_id_;
  bool idempotent_;
};
}  // namespace so101_gazebo_demo::pick_place
