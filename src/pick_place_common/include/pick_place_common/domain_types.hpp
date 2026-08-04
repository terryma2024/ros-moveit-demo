#pragma once

#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace pick_place_common
{
enum class State
{
  IDLE,
  PREPARE_OPEN_GRIPPER,
  MOVE_ABOVE_OBJECT,
  DESCEND,
  CLOSE_GRIPPER,
  WAIT_GRASP_STABLE,
  MICRO_LIFT,
  WAIT_MICRO_LIFT_STABLE,
  VERIFY_PHYSICAL_GRASP,
  VALIDATION_FAILED,
  ATTACH_GAZEBO,
  ATTACH_MOVEIT,
  LIFT,
  MOVE_ABOVE_PLACE,
  DESCEND_TO_PLACE,
  OPEN_GRIPPER,
  DETACH_GAZEBO,
  DETACH_MOVEIT,
  SYNC_WORLD_OBJECT,
  RETREAT,
  RECOVER_LIFT_TO_SAFE_HEIGHT,
  RECOVER_MOVE_ABOVE_PICK,
  RECOVER_DESCEND_TO_PICK,
  RECOVER_DETACH_MOVEIT,
  RECOVER_OPEN_GRIPPER,
  RECOVER_DETACH_GAZEBO,
  RECOVER_SYNC_WORLD_OBJECT,
  RECOVER_RETREAT,
  DONE,
  ERROR
};
enum class RunStatus
{
  RUNNING,
  PLAN_ONLY_COMPLETE,
  CHECKPOINT_COMPLETE,
  DONE,
  ERROR
};
enum class RunMode
{
  DRY_RUN,
  PLAN_ONLY,
  EXECUTE
};
enum class ActionStatus
{
  SUCCEEDED,
  FAILED,
  CANCELLED,
  TIMED_OUT,
  NOT_SUPPORTED
};
enum class FailureCategory
{
  CONFIGURATION,
  OBSERVATION,
  PRECONDITION,
  PLANNING,
  PLAN_VALIDATION,
  EXECUTION,
  POSTCONDITION,
  COLLISION,
  TF,
  GRIPPER,
  GAZEBO_ATTACHMENT,
  MOVEIT_SCENE,
  WORLD_INCONSISTENCY,
  CHECKPOINT,
  RESUME_VALIDATION,
  INTERNAL
};
struct Failure
{
  FailureCategory category{FailureCategory::INTERNAL};
  std::string code;
  std::string message;
  std::map<std::string, double> metrics;
};
struct ActionResult
{
  ActionStatus status{ActionStatus::FAILED};
  std::optional<Failure> failure;
};
struct RunRequest
{
  RunMode mode{RunMode::DRY_RUN};
  std::optional<State> stop_after;
  std::optional<State> plan_only_state;
  bool resume{false};
  std::optional<State> fail_at;
  std::uint64_t max_state_transitions{100};
  bool single_step{false};
  bool force_continue{false};
};
struct RunResult
{
  RunStatus status{RunStatus::ERROR};
  State current_state{State::ERROR};
  std::optional<State> next_state;
  std::optional<Failure> failure;
  std::uint64_t transition_count{0};
  std::vector<State> state_trace;
};
[[nodiscard]] const char * toString(State) noexcept;
[[nodiscard]] const char * toString(RunStatus) noexcept;
[[nodiscard]] const char * toString(RunMode) noexcept;
[[nodiscard]] std::optional<State> stateFromString(std::string_view);
[[nodiscard]] std::optional<RunMode> runModeFromString(std::string_view);
[[nodiscard]] std::string formatFailure(const Failure &);
[[nodiscard]] bool isTerminal(State) noexcept;
[[nodiscard]] bool isForwardAction(State) noexcept;
[[nodiscard]] bool isAction(State) noexcept;
}  // namespace pick_place_common
