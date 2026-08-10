#pragma once

#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include "panda_gazebo_demo/pick_place/world_observer.hpp"
#include <pick_place_common/moveit_scene_executor.hpp>

namespace rclcpp
{
class Node;
}

namespace panda_gazebo_demo::pick_place
{

using pick_place_common::ros_adapters::IMoveItSceneAdapter;
using pick_place_common::ros_adapters::MoveItAttachmentSpec;
using pick_place_common::ros_adapters::MoveItSceneState;

class IPandaMoveItSceneAdapter : public IMoveItSceneAdapter
{
public:
  [[nodiscard]] virtual ActionResult upsertTableWorldPose(const Pose3d & pose) = 0;
};

class MoveItSceneAdapter final : public IPandaMoveItSceneAdapter
{
public:
  MoveItSceneAdapter(const std::shared_ptr<rclcpp::Node> & node, const std::string & planning_group,
                     std::string object_id = "coke");
  ~MoveItSceneAdapter() override;

  [[nodiscard]] ActionResult attachTaskObject(const MoveItAttachmentSpec & spec) override;
  [[nodiscard]] ActionResult detachTaskObject() override;
  [[nodiscard]] ActionResult upsertTaskObjectWorldPose(const Pose3d & pose) override;
  [[nodiscard]] ActionResult upsertTableWorldPose(const Pose3d & pose) override;
  [[nodiscard]] std::optional<MoveItSceneState> observe() override;

private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace panda_gazebo_demo::pick_place
