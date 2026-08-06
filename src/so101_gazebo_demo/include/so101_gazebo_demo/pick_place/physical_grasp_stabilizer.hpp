#pragma once

#include <memory>

#include "so101_gazebo_demo/pick_place/physical_grasp_evidence_store.hpp"
#include "so101_gazebo_demo/pick_place/so101_gripper_state.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"
#include "so101_gazebo_demo/pick_place/world_observer.hpp"

namespace so101_gazebo_demo::pick_place
{

class SO101PhysicalGraspStabilizer
{
public:
  SO101PhysicalGraspStabilizer(std::shared_ptr<IWorldObserver> observer,
                               std::shared_ptr<IPhysicalGraspEvidenceStore> evidence,
                               std::shared_ptr<ISO101GripperCommand> gripper,
                               SO101Profile profile = SO101Profile::canonical());

  [[nodiscard]] ActionResult captureBeforeLift();
  [[nodiscard]] ActionResult captureAfterLift();
  [[nodiscard]] ActionResult cancel();

private:
  [[nodiscard]] ActionResult capture(bool before_lift);

  std::shared_ptr<IWorldObserver> observer_;
  std::shared_ptr<IPhysicalGraspEvidenceStore> evidence_;
  std::shared_ptr<ISO101GripperCommand> gripper_;
  SO101Profile profile_;
};

}  // namespace so101_gazebo_demo::pick_place
