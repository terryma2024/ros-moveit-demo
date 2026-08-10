#pragma once

#include <mutex>
#include <optional>
#include <string>
#include <utility>

#include <pick_place_common/moveit_scene_executor.hpp>

#include "so101_gazebo_demo/pick_place/state_action.hpp"
#include "so101_gazebo_demo/pick_place/final_placement_evidence_store.hpp"

namespace so101_gazebo_demo::pick_place
{
class SO101MoveItScenePolicy final : public pick_place_common::ros_adapters::IMoveItScenePolicy
{
public:
  SO101MoveItScenePolicy(std::string task_object_id, bool idempotent,
                         const IFinalPlacementEvidenceStore * final_evidence = nullptr) :
      task_object_id_(std::move(task_object_id)), idempotent_(idempotent),
      final_evidence_(final_evidence)
  {
  }

  [[nodiscard]] pick_place_common::ros_adapters::ScenePreparation
  prepare(pick_place_common::ros_adapters::MoveItSceneOperation operation,
          const pick_place_common::ExecutionContext & context) const override;

  [[nodiscard]] std::optional<Pose3d> attachedShadowRelativePose() const;

private:
  std::string task_object_id_;
  bool idempotent_;
  const IFinalPlacementEvidenceStore * final_evidence_;
  mutable std::mutex mutex_;
  mutable std::optional<Pose3d> attached_shadow_relative_pose_;
};
}  // namespace so101_gazebo_demo::pick_place
