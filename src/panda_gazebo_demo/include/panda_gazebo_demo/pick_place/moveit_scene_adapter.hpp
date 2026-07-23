#pragma once

#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include "panda_gazebo_demo/pick_place/world_observer.hpp"

namespace rclcpp
{
class Node;
}

namespace panda_gazebo_demo::pick_place
{

struct MoveItSceneState
{
  bool coke_in_world{false};
  bool coke_attached{false};
  std::string attached_link;
  std::set<std::string> touch_links;
  std::optional<Pose3d> coke_world_pose;
};

class IMoveItSceneAdapter
{
public:
  virtual ~IMoveItSceneAdapter() = default;
  [[nodiscard]] virtual ActionResult attachCoke(
    const std::string & link_name,
    const std::vector<std::string> & touch_links) = 0;
  [[nodiscard]] virtual ActionResult detachCoke() = 0;
  [[nodiscard]] virtual ActionResult syncCokeWorldPose(const Pose3d & pose) = 0;
  [[nodiscard]] virtual ActionResult upsertCokeWorldPose(const Pose3d & pose) = 0;
  [[nodiscard]] virtual std::optional<MoveItSceneState> observe() = 0;
};

class MoveItSceneAdapter final : public IMoveItSceneAdapter
{
public:
  MoveItSceneAdapter(
    std::shared_ptr<rclcpp::Node> node, std::string planning_group,
    std::string object_id = "coke");
  ~MoveItSceneAdapter() override;

  [[nodiscard]] ActionResult attachCoke(
    const std::string & link_name,
    const std::vector<std::string> & touch_links) override;
  [[nodiscard]] ActionResult detachCoke() override;
  [[nodiscard]] ActionResult syncCokeWorldPose(const Pose3d & pose) override;
  [[nodiscard]] ActionResult upsertCokeWorldPose(const Pose3d & pose) override;
  [[nodiscard]] std::optional<MoveItSceneState> observe() override;

private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace panda_gazebo_demo::pick_place
