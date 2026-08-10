#pragma once

#include <pick_place_common/gazebo_attachment_executor.hpp>

#include "panda_gazebo_demo/pick_place/state_action.hpp"
#include "panda_gazebo_demo/pick_place/state_validation.hpp"

namespace panda_gazebo_demo::pick_place
{
class PandaAttachmentConvergencePolicy final
    : public pick_place_common::ros_adapters::IAttachmentConvergencePolicy
{
public:
  explicit PandaAttachmentConvergencePolicy(GripperLimits gripper_limits) :
      gripper_limits_(gripper_limits)
  {
  }

  [[nodiscard]] bool canTreatAsConverged(const ExecutionContext & context,
                                         bool desired_attached) const override
  {
    const auto & snapshot = context.before;
    if (desired_attached) {
      return snapshot.fresh && snapshot.gazebo_task_object_attached &&
             *snapshot.gazebo_task_object_attached;
    }
    return snapshot.fresh && snapshot.arm_stationary && snapshot.gazebo_task_object_attached &&
           !*snapshot.gazebo_task_object_attached &&
           snapshot.moveit_task_object_attached.has_value() &&
           snapshot.gazebo_task_object_pose_world.has_value() &&
           snapshot.gazebo_task_object_stationary && *snapshot.gazebo_task_object_stationary &&
           validateGripperOpen(snapshot, gripper_limits_).ok;
  }

private:
  GripperLimits gripper_limits_;
};
}  // namespace panda_gazebo_demo::pick_place
