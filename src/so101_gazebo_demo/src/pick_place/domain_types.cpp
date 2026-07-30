#include "so101_gazebo_demo/pick_place/domain_types.hpp"

#include <iomanip>
#include <sstream>

namespace so101_gazebo_demo::pick_place {
namespace { constexpr State kStates[] = { State::IDLE, State::PREPARE_OPEN_GRIPPER, State::MOVE_ABOVE_OBJECT, State::DESCEND, State::CLOSE_GRIPPER, State::WAIT_GRASP_STABLE, State::MICRO_LIFT, State::WAIT_MICRO_LIFT_STABLE, State::VERIFY_PHYSICAL_GRASP, State::VALIDATION_FAILED, State::ATTACH_GAZEBO, State::ATTACH_MOVEIT, State::LIFT, State::MOVE_ABOVE_PLACE, State::DESCEND_TO_PLACE, State::OPEN_GRIPPER, State::DETACH_GAZEBO, State::DETACH_MOVEIT, State::SYNC_WORLD_OBJECT, State::RETREAT, State::RECOVER_LIFT_TO_SAFE_HEIGHT, State::RECOVER_MOVE_ABOVE_PICK, State::RECOVER_DESCEND_TO_PICK, State::RECOVER_DETACH_MOVEIT, State::RECOVER_OPEN_GRIPPER, State::RECOVER_DETACH_GAZEBO, State::RECOVER_SYNC_WORLD_OBJECT, State::RECOVER_RETREAT, State::DONE, State::ERROR }; }
const char * toString(State s) noexcept { static constexpr const char * names[] = {"IDLE","PREPARE_OPEN_GRIPPER","MOVE_ABOVE_OBJECT","DESCEND","CLOSE_GRIPPER","WAIT_GRASP_STABLE","MICRO_LIFT","WAIT_MICRO_LIFT_STABLE","VERIFY_PHYSICAL_GRASP","VALIDATION_FAILED","ATTACH_GAZEBO","ATTACH_MOVEIT","LIFT","MOVE_ABOVE_PLACE","DESCEND_TO_PLACE","OPEN_GRIPPER","DETACH_GAZEBO","DETACH_MOVEIT","SYNC_WORLD_OBJECT","RETREAT","RECOVER_LIFT_TO_SAFE_HEIGHT","RECOVER_MOVE_ABOVE_PICK","RECOVER_DESCEND_TO_PICK","RECOVER_DETACH_MOVEIT","RECOVER_OPEN_GRIPPER","RECOVER_DETACH_GAZEBO","RECOVER_SYNC_WORLD_OBJECT","RECOVER_RETREAT","DONE","ERROR"}; return names[static_cast<int>(s)]; }
const char * toString(RunStatus s) noexcept { static constexpr const char * n[] = {"RUNNING","PLAN_ONLY_COMPLETE","CHECKPOINT_COMPLETE","DONE","ERROR"}; return n[static_cast<int>(s)]; }
const char * toString(RunMode m) noexcept { static constexpr const char * n[] = {"dry_run","plan_only","execute"}; return n[static_cast<int>(m)]; }
std::optional<State> stateFromString(std::string_view value) { for (auto s : kStates) if (value == toString(s)) return s; return std::nullopt; }
std::optional<RunMode> runModeFromString(std::string_view value) { for (auto m : {RunMode::DRY_RUN,RunMode::PLAN_ONLY,RunMode::EXECUTE}) if (value == toString(m)) return m; return std::nullopt; }
std::string formatFailure(const Failure & failure) {
  std::ostringstream output;
  output << "failure=" << failure.code;
  if (!failure.message.empty()) {
    output << "\nfailure_message=" << failure.message;
  }
  if (!failure.metrics.empty()) {
    output << "\nfailure_metrics" << std::setprecision(12);
    for (const auto & [name, value] : failure.metrics) {
      output << ' ' << name << '=' << value;
    }
  }
  return output.str();
}
bool isTerminal(State s) noexcept { return s == State::DONE || s == State::ERROR; }
bool isAction(State s) noexcept { return s >= State::PREPARE_OPEN_GRIPPER && s <= State::RECOVER_RETREAT && s != State::VALIDATION_FAILED; }
}  // namespace so101_gazebo_demo::pick_place
