#include "panda_gazebo_demo/pick_place/panda_workflow.hpp"
#include <stdexcept>
namespace panda_gazebo_demo::pick_place
{
const pick_place_common::WorkflowDefinition & pandaWorkflowDefinition()
{
  using S = pick_place_common::State;
  static const auto workflow = [] {
    pick_place_common::WorkflowDefinition w;
    w.transitions = {{S::IDLE, {S::PREPARE_OPEN_GRIPPER, S::ERROR}},
                     {S::PREPARE_OPEN_GRIPPER, {S::MOVE_ABOVE_OBJECT, S::ERROR}},
                     {S::MOVE_ABOVE_OBJECT, {S::DESCEND, S::RECOVER_RETREAT}},
                     {S::DESCEND, {S::CLOSE_GRIPPER, S::RECOVER_OPEN_GRIPPER}},
                     {S::CLOSE_GRIPPER, {S::ATTACH_GAZEBO, S::RECOVER_OPEN_GRIPPER}},
                     {S::ATTACH_GAZEBO, {S::ATTACH_MOVEIT, S::RECOVER_OPEN_GRIPPER}},
                     {S::ATTACH_MOVEIT, {S::LIFT, S::RECOVER_OPEN_GRIPPER}},
                     {S::LIFT, {S::MOVE_ABOVE_PLACE, S::RECOVER_LIFT_TO_SAFE_HEIGHT}},
                     {S::MOVE_ABOVE_PLACE, {S::DESCEND_TO_PLACE, S::RECOVER_LIFT_TO_SAFE_HEIGHT}},
                     {S::DESCEND_TO_PLACE, {S::OPEN_GRIPPER, S::RECOVER_LIFT_TO_SAFE_HEIGHT}},
                     {S::OPEN_GRIPPER, {S::DETACH_GAZEBO, S::RECOVER_OPEN_GRIPPER}},
                     {S::DETACH_GAZEBO, {S::DETACH_MOVEIT, S::RECOVER_DETACH_GAZEBO}},
                     {S::DETACH_MOVEIT, {S::SYNC_WORLD_OBJECT, S::RECOVER_DETACH_MOVEIT}},
                     {S::SYNC_WORLD_OBJECT, {S::RETREAT, S::RECOVER_SYNC_WORLD_OBJECT}},
                     {S::RETREAT, {S::DONE, S::RECOVER_RETREAT}},
                     {S::RECOVER_LIFT_TO_SAFE_HEIGHT, {S::RECOVER_MOVE_ABOVE_PICK, S::ERROR}},
                     {S::RECOVER_MOVE_ABOVE_PICK, {S::RECOVER_DESCEND_TO_PICK, S::ERROR}},
                     {S::RECOVER_DESCEND_TO_PICK, {S::RECOVER_OPEN_GRIPPER, S::ERROR}},
                     {S::RECOVER_OPEN_GRIPPER, {S::RECOVER_DETACH_GAZEBO, S::ERROR}},
                     {S::RECOVER_DETACH_GAZEBO, {S::RECOVER_DETACH_MOVEIT, S::ERROR}},
                     {S::RECOVER_DETACH_MOVEIT, {S::RECOVER_SYNC_WORLD_OBJECT, S::ERROR}},
                     {S::RECOVER_SYNC_WORLD_OBJECT, {S::RECOVER_RETREAT, S::ERROR}},
                     {S::RECOVER_RETREAT, {S::ERROR, S::ERROR}}};
    for (const auto & entry : w.transitions)
      if (entry.first != S::IDLE)
        w.action_states.insert(entry.first);
    w.forward_states = {S::IDLE,
                        S::PREPARE_OPEN_GRIPPER,
                        S::MOVE_ABOVE_OBJECT,
                        S::DESCEND,
                        S::CLOSE_GRIPPER,
                        S::ATTACH_GAZEBO,
                        S::ATTACH_MOVEIT,
                        S::LIFT,
                        S::MOVE_ABOVE_PLACE,
                        S::DESCEND_TO_PLACE,
                        S::OPEN_GRIPPER,
                        S::DETACH_GAZEBO,
                        S::DETACH_MOVEIT,
                        S::SYNC_WORLD_OBJECT,
                        S::RETREAT,
                        S::DONE};
    w.terminal_states = {S::DONE, S::ERROR};
    w.plan_only_states = {S::MOVE_ABOVE_OBJECT, S::DESCEND,          S::LIFT,
                          S::MOVE_ABOVE_PLACE,  S::DESCEND_TO_PLACE, S::RETREAT};
    if (auto failure = pick_place_common::validateWorkflowDefinition(w))
      throw std::logic_error(failure->code);
    return w;
  }();
  return workflow;
}
}  // namespace panda_gazebo_demo::pick_place
