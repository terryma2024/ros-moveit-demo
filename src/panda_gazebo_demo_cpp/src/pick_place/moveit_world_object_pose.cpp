#include "panda_gazebo_demo/pick_place/moveit_world_object_pose.hpp"

namespace panda_gazebo_demo::pick_place
{

Pose3d worldPoseFromCollisionObject(const moveit_msgs::msg::CollisionObject & object) noexcept
{
  const auto & pose = object.pose;
  return {pose.position.x,    pose.position.y,    pose.position.z,   pose.orientation.x,
          pose.orientation.y, pose.orientation.z, pose.orientation.w};
}

}  // namespace panda_gazebo_demo::pick_place
