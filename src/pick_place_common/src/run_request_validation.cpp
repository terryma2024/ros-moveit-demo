#include "pick_place_common/run_request_validation.hpp"

#include <map>
#include <set>

namespace pick_place_common
{
namespace
{
Failure configurationFailure(const char * code, const char * message)
{
  return {FailureCategory::CONFIGURATION, code, message, {}};
}
}  // namespace

ForwardPathRelation compareForwardPathPosition(const WorkflowDefinition & workflow, State cursor,
                                               State target) noexcept
{
  std::map<State, std::size_t> positions;
  std::set<State> visited;
  State state = workflow.initial_state;
  std::size_t position = 0;
  while (true) {
    if (!visited.insert(state).second) {
      return ForwardPathRelation::UNREACHABLE;
    }
    positions.emplace(state, position++);
    if (workflow.terminal_states.count(state)) {
      break;
    }
    const auto transition = workflow.transitions.find(state);
    if (transition == workflow.transitions.end()) {
      return ForwardPathRelation::UNREACHABLE;
    }
    state = transition->second.succeeded;
  }

  const auto cursor_position = positions.find(cursor);
  const auto target_position = positions.find(target);
  if (cursor_position == positions.end() || target_position == positions.end()) {
    return ForwardPathRelation::UNREACHABLE;
  }
  if (cursor_position->second < target_position->second) {
    return ForwardPathRelation::UPSTREAM;
  }
  if (cursor_position->second > target_position->second) {
    return ForwardPathRelation::DOWNSTREAM;
  }
  return ForwardPathRelation::SAME;
}

std::optional<Failure> validateRunRequest(const WorkflowDefinition & workflow,
                                          const RunRequest & request)
{
  if (request.max_state_transitions == 0) {
    return configurationFailure("INVALID_MAX_TRANSITIONS",
                                "max_state_transitions must be greater than zero");
  }
  if (request.fail_at && request.mode != RunMode::DRY_RUN) {
    return configurationFailure("FAIL_AT_MODE_MISMATCH",
                                "fail_at is supported only in dry_run mode");
  }
  if (request.force_continue && (!request.resume || request.mode != RunMode::EXECUTE)) {
    return configurationFailure("FORCE_CONTINUE_REQUEST_INVALID",
                                "force_continue requires an execute resume");
  }
  if (request.mode != RunMode::PLAN_ONLY) {
    if (request.plan_only_state) {
      return configurationFailure("PLAN_ONLY_ARGUMENT_CONFLICT",
                                  "plan_only_state requires plan_only mode");
    }
    return std::nullopt;
  }
  if (!request.plan_only_state) {
    return configurationFailure("PLAN_ONLY_STATE_REQUIRED",
                                "plan_only mode requires plan_only_state");
  }
  if (request.stop_after || request.single_step) {
    return configurationFailure(
      "PLAN_ONLY_ARGUMENT_CONFLICT",
      "plan_only_state cannot be combined with stop_after or single_step");
  }
  if (!workflow.plan_only_states.count(*request.plan_only_state)) {
    return configurationFailure("PLAN_ONLY_STATE_NOT_ALLOWED",
                                "plan_only_state is not allowed by this workflow");
  }
  if (compareForwardPathPosition(workflow, workflow.initial_state, *request.plan_only_state) ==
      ForwardPathRelation::UNREACHABLE) {
    return configurationFailure("PLAN_ONLY_STATE_UNREACHABLE",
                                "plan_only_state is not reachable on the forward success path");
  }
  return std::nullopt;
}
}  // namespace pick_place_common
