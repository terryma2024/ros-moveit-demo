#include "so101_gazebo_demo/pick_place/runner.hpp"
#include "so101_gazebo_demo/pick_place/transition_table.hpp"
namespace so101_gazebo_demo::pick_place {
RunResult StateMachineRunner::run(const RunRequest & request) const {
  if (request.max_state_transitions == 0) return {RunStatus::ERROR,State::IDLE,std::nullopt,Failure{FailureCategory::CONFIGURATION,"INVALID_MAX_TRANSITIONS","max_state_transitions must be greater than zero",{}},0,{State::IDLE}};
  if (request.mode != RunMode::DRY_RUN) return {RunStatus::ERROR,State::IDLE,std::nullopt,Failure{FailureCategory::CONFIGURATION,"UNSAFE_ADAPTERS_NOT_REGISTERED","plan_only and execute fail closed until SO-101 adapters are registered",{}},0,{State::IDLE}};
  if (request.resume) return {RunStatus::ERROR,State::IDLE,std::nullopt,Failure{FailureCategory::RESUME_VALIDATION,"CHECKPOINT_STORE_NOT_REGISTERED","resume fails closed without a checkpoint store and live observer",{}},0,{State::IDLE}};
  StateMachine machine; RunResult out; out.status=RunStatus::RUNNING; out.state_trace.push_back(machine.currentState());
  while (!machine.isTerminal() && out.transition_count < request.max_state_transitions) { const State before=machine.currentState(); const bool injected=request.fail_at==before; const State after=machine.advance(injected?ActionStatus::FAILED:ActionStatus::SUCCEEDED); ++out.transition_count; out.state_trace.push_back(after); if (injected) out.failure=Failure{FailureCategory::INTERNAL,"DRY_RUN_FAILURE_INJECTED",std::string("dry_run failure injected at ")+toString(before),{}}; if (!injected && request.stop_after==before) { out.status=RunStatus::CHECKPOINT_COMPLETE; out.current_state=after; out.next_state=after; return out; } }
  out.current_state=machine.currentState(); if (!machine.isTerminal()) { out.status=RunStatus::ERROR; out.failure=Failure{FailureCategory::INTERNAL,"MAX_TRANSITIONS_EXCEEDED","State machine exceeded max_state_transitions",{}}; return out; } out.status=out.current_state==State::DONE?RunStatus::DONE:RunStatus::ERROR; return out;
}
}  // namespace so101_gazebo_demo::pick_place
