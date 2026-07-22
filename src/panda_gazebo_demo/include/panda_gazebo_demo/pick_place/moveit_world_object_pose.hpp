#pragma once

#include <moveit_msgs/msg/collision_object.hpp>

#include "panda_gazebo_demo/pick_place/world_observer.hpp"

namespace panda_gazebo_demo::pick_place
{

/// Returns a CollisionObject's pose in its header frame.
///
/// CollisionObject primitive and mesh poses are defined relative to this pose.
[[nodiscard]] Pose3d worldPoseFromCollisionObject(
  const moveit_msgs::msg::CollisionObject & object) noexcept;

}  // namespace panda_gazebo_demo::pick_place
