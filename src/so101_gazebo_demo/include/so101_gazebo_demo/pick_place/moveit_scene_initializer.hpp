#pragma once

#include <chrono>
#include <optional>

#include "so101_gazebo_demo/pick_place/domain_types.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

namespace so101_gazebo_demo::pick_place
{

class IJointPlanningBoundary;
class IMoveItSceneAdapter;

class MoveItSceneInitializer
{
public:
  MoveItSceneInitializer(IJointPlanningBoundary & boundary, IMoveItSceneAdapter & scene,
                         std::chrono::milliseconds poll_interval = std::chrono::milliseconds(50));

  [[nodiscard]] std::optional<Failure> initialize(const SO101Profile & profile,
                                                  std::chrono::milliseconds timeout,
                                                  bool preserve_task_object = false);

private:
  IJointPlanningBoundary & boundary_;
  IMoveItSceneAdapter & scene_;
  std::chrono::milliseconds poll_interval_;
};

}  // namespace so101_gazebo_demo::pick_place
