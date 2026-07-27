#pragma once

#include <array>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <moveit_msgs/msg/collision_object.hpp>

#include "so101_gazebo_demo/pick_place/domain_types.hpp"
#include "so101_gazebo_demo/pick_place/world_observer.hpp"

namespace rclcpp
{
class Node;
}

namespace so101_gazebo_demo::pick_place
{

struct MoveItSceneGeometry
{
  std::string world_frame;
  std::string table_id;
  std::array<double, 3> table_size;
  std::string pedestal_id;
  std::array<double, 3> pedestal_size;
  std::string coke_id;
  double coke_height;
  double coke_radius;
};

struct MoveItAttachmentSpec
{
  std::string link_name;
  std::vector<std::string> touch_links;
};

struct MoveItSceneState
{
  bool coke_in_world{false};
  bool coke_attached{false};
  std::string attached_link;
  std::vector<std::string> touch_links;
  std::optional<Pose3d> coke_world_pose;
  bool table_in_world{false};
  std::optional<Pose3d> table_world_pose;
  bool pedestal_in_world{false};
  std::optional<Pose3d> pedestal_world_pose;
};

[[nodiscard]] moveit_msgs::msg::CollisionObject
makeCokeCollisionObject(const MoveItSceneGeometry & geometry, const Pose3d & pose);

[[nodiscard]] moveit_msgs::msg::CollisionObject
makeTableCollisionObject(const MoveItSceneGeometry & geometry, const Pose3d & pose);

[[nodiscard]] moveit_msgs::msg::CollisionObject
makePedestalCollisionObject(const MoveItSceneGeometry & geometry, const Pose3d & pose);

class IMoveItSceneAdapter
{
public:
  virtual ~IMoveItSceneAdapter() = default;
  [[nodiscard]] virtual ActionResult attachCoke(const MoveItAttachmentSpec & spec) = 0;
  [[nodiscard]] virtual ActionResult detachCoke() = 0;
  [[nodiscard]] virtual ActionResult upsertCokeWorldPose(const Pose3d & pose) = 0;
  [[nodiscard]] virtual ActionResult upsertTableWorldPose(const Pose3d & pose) = 0;
  [[nodiscard]] virtual ActionResult upsertPedestalWorldPose(const Pose3d & pose) = 0;
  [[nodiscard]] virtual std::optional<MoveItSceneState> observe() = 0;
};

class MoveItSceneAdapter final : public IMoveItSceneAdapter
{
public:
  MoveItSceneAdapter(const std::shared_ptr<rclcpp::Node> & node, const std::string & planning_group,
                     MoveItSceneGeometry geometry);
  ~MoveItSceneAdapter() override;

  [[nodiscard]] ActionResult attachCoke(const MoveItAttachmentSpec & spec) override;
  [[nodiscard]] ActionResult detachCoke() override;
  [[nodiscard]] ActionResult upsertCokeWorldPose(const Pose3d & pose) override;
  [[nodiscard]] ActionResult upsertTableWorldPose(const Pose3d & pose) override;
  [[nodiscard]] ActionResult upsertPedestalWorldPose(const Pose3d & pose) override;
  [[nodiscard]] std::optional<MoveItSceneState> observe() override;

private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace so101_gazebo_demo::pick_place
