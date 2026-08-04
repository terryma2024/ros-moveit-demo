#pragma once

#include "so101_gazebo_demo/pick_place/so101_profile.hpp"
#include "so101_gazebo_demo/pick_place/world_observer.hpp"

namespace so101_gazebo_demo::pick_place
{

[[nodiscard]] bool supportedAtPick(const Pose3d & pose, const SO101Profile & profile) noexcept;
[[nodiscard]] bool supportedAtPlace(const Pose3d & pose, const SO101Profile & profile) noexcept;

}  // namespace so101_gazebo_demo::pick_place
