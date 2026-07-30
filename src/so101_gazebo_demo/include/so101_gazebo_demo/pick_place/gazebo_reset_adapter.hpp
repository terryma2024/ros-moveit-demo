#pragma once

#include <memory>
#include <string>

#include "so101_gazebo_demo/pick_place/world_reset_coordinator.hpp"

namespace so101_gazebo_demo::pick_place
{

class GazeboResetAdapter final : public IGazeboResetAdapter
{
public:
  GazeboResetAdapter(const std::string & world_name, std::string task_object_id,
                     const std::string & detach_topic, const std::string & attachment_topic,
                     double observation_timeout_seconds, unsigned int service_timeout_ms);
  ~GazeboResetAdapter() override;

  [[nodiscard]] std::optional<GazeboResetState> observe() override;
  [[nodiscard]] ActionResult detachTaskObject() override;
  [[nodiscard]] ActionResult setTaskObjectWorldPose(const Pose3d & pose) override;

private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace so101_gazebo_demo::pick_place
