#include "panda_gazebo_demo/pick_place/domain_types.hpp"

namespace panda_gazebo_demo::pick_place
{

const char * toString(State state) noexcept
{
  switch (state) {
    case State::IDLE:
      return "IDLE";
    case State::PREPARE_OPEN_GRIPPER:
      return "PREPARE_OPEN_GRIPPER";
    case State::MOVE_ABOVE_OBJECT:
      return "MOVE_ABOVE_OBJECT";
    case State::DESCEND:
      return "DESCEND";
    case State::CLOSE_GRIPPER:
      return "CLOSE_GRIPPER";
    case State::ATTACH_GAZEBO:
      return "ATTACH_GAZEBO";
    case State::ATTACH_MOVEIT:
      return "ATTACH_MOVEIT";
    case State::LIFT:
      return "LIFT";
    case State::MOVE_ABOVE_PLACE:
      return "MOVE_ABOVE_PLACE";
    case State::DESCEND_TO_PLACE:
      return "DESCEND_TO_PLACE";
    case State::OPEN_GRIPPER:
      return "OPEN_GRIPPER";
    case State::DETACH_GAZEBO:
      return "DETACH_GAZEBO";
    case State::DETACH_MOVEIT:
      return "DETACH_MOVEIT";
    case State::SYNC_WORLD_OBJECT:
      return "SYNC_WORLD_OBJECT";
    case State::RETREAT:
      return "RETREAT";
    case State::RECOVER_LIFT_TO_SAFE_HEIGHT:
      return "RECOVER_LIFT_TO_SAFE_HEIGHT";
    case State::RECOVER_MOVE_ABOVE_PICK:
      return "RECOVER_MOVE_ABOVE_PICK";
    case State::RECOVER_DESCEND_TO_PICK:
      return "RECOVER_DESCEND_TO_PICK";
    case State::RECOVER_DETACH_MOVEIT:
      return "RECOVER_DETACH_MOVEIT";
    case State::RECOVER_OPEN_GRIPPER:
      return "RECOVER_OPEN_GRIPPER";
    case State::RECOVER_DETACH_GAZEBO:
      return "RECOVER_DETACH_GAZEBO";
    case State::RECOVER_SYNC_WORLD_OBJECT:
      return "RECOVER_SYNC_WORLD_OBJECT";
    case State::RECOVER_RETREAT:
      return "RECOVER_RETREAT";
    case State::DONE:
      return "DONE";
    case State::ERROR:
      return "ERROR";
  }
  return "UNKNOWN";
}

const char * toString(RunStatus status) noexcept
{
  switch (status) {
    case RunStatus::RUNNING:
      return "RUNNING";
    case RunStatus::PLAN_ONLY_COMPLETE:
      return "PLAN_ONLY_COMPLETE";
    case RunStatus::CHECKPOINT_COMPLETE:
      return "CHECKPOINT_COMPLETE";
    case RunStatus::DONE:
      return "DONE";
    case RunStatus::ERROR:
      return "ERROR";
  }
  return "UNKNOWN";
}

const char * toString(RunMode mode) noexcept
{
  switch (mode) {
    case RunMode::DRY_RUN:
      return "dry_run";
    case RunMode::PLAN_ONLY:
      return "plan_only";
    case RunMode::EXECUTE:
      return "execute";
  }
  return "unknown";
}

std::optional<State> stateFromString(std::string_view value)
{
  constexpr State states[] = {
    State::IDLE,
    State::PREPARE_OPEN_GRIPPER,
    State::MOVE_ABOVE_OBJECT,
    State::DESCEND,
    State::CLOSE_GRIPPER,
    State::ATTACH_GAZEBO,
    State::ATTACH_MOVEIT,
    State::LIFT,
    State::MOVE_ABOVE_PLACE,
    State::DESCEND_TO_PLACE,
    State::OPEN_GRIPPER,
    State::DETACH_GAZEBO,
    State::DETACH_MOVEIT,
    State::SYNC_WORLD_OBJECT,
    State::RETREAT,
    State::RECOVER_LIFT_TO_SAFE_HEIGHT,
    State::RECOVER_MOVE_ABOVE_PICK,
    State::RECOVER_DESCEND_TO_PICK,
    State::RECOVER_DETACH_MOVEIT,
    State::RECOVER_OPEN_GRIPPER,
    State::RECOVER_DETACH_GAZEBO,
    State::RECOVER_SYNC_WORLD_OBJECT,
    State::RECOVER_RETREAT,
    State::DONE,
    State::ERROR,
  };
  for (const auto state : states) {
    if (value == toString(state)) {
      return state;
    }
  }
  return std::nullopt;
}

std::optional<RunMode> runModeFromString(std::string_view value)
{
  if (value == "dry_run") {
    return RunMode::DRY_RUN;
  }
  if (value == "plan_only") {
    return RunMode::PLAN_ONLY;
  }
  if (value == "execute") {
    return RunMode::EXECUTE;
  }
  return std::nullopt;
}

bool isTerminal(State state) noexcept
{
  return state == State::DONE || state == State::ERROR;
}

bool isForwardAction(State state) noexcept
{
  return state >= State::IDLE && state <= State::RETREAT;
}

bool isAction(State state) noexcept
{
  return state >= State::PREPARE_OPEN_GRIPPER && state <= State::RECOVER_RETREAT;
}

}  // namespace panda_gazebo_demo::pick_place
