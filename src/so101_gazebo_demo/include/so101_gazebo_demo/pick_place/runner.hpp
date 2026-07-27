#pragma once

#include "so101_gazebo_demo/pick_place/common_resume_validator.hpp"
#include "so101_gazebo_demo/pick_place/recovery_policy.hpp"
#include "so101_gazebo_demo/pick_place/state_action.hpp"
#include "so101_gazebo_demo/pick_place/transition_contract.hpp"
#include "so101_gazebo_demo/pick_place/transition_table.hpp"

namespace so101_gazebo_demo::pick_place
{

class StateMachineRunner
{
public:
  StateMachineRunner();
  StateMachineRunner(const StateActionRegistry & actions,
                     const TransitionContractRegistry & contracts,
                     IWorldObserver * observer = nullptr,
                     ICheckpointStore * checkpoint_store = nullptr,
                     const CommonResumeValidator * common_resume_validator = nullptr,
                     const PlanValidatorRegistry * plan_validators = nullptr,
                     const IRecoveryPolicy * recovery_policy = nullptr);

  [[nodiscard]] RunResult run(const RunRequest & request) const;

private:
  [[nodiscard]] static RunResult runDryRun(const RunRequest & request);
  [[nodiscard]] RunResult
  runPlanOnly(State state, const RunRequest & request,
              std::optional<ObservationResult> observation = std::nullopt) const;
  [[nodiscard]] RunResult runExecuteWorkflow(State initial_state, const RunRequest & request,
                                             std::optional<WorldSnapshot> initial_snapshot,
                                             std::uint64_t checkpoint_sequence,
                                             std::uint64_t initial_transition_count,
                                             CheckpointPhase phase = CheckpointPhase::FORWARD,
                                             std::optional<State> failed_state = std::nullopt,
                                             std::optional<Failure> original_failure = std::nullopt,
                                             bool include_idle = false) const;
  [[nodiscard]] RunResult runExecuteStep(State state, std::optional<WorldSnapshot> before,
                                         std::uint64_t checkpoint_sequence, CheckpointPhase phase,
                                         std::optional<State> failed_state,
                                         std::optional<Failure> original_failure) const;
  [[nodiscard]] RunResult runResume(const RunRequest & request) const;
  [[nodiscard]] std::optional<Failure> validateExecuteConfiguration() const;
  [[nodiscard]] RunResult handleActionFailure(State state, IStateExecutor & executor,
                                              Failure original_failure,
                                              std::uint64_t checkpoint_sequence) const;

  struct StopObservationResult
  {
    std::optional<WorldSnapshot> snapshot;
    std::optional<Failure> failure;
  };
  [[nodiscard]] StopObservationResult observeAfterSuccessfulAction(State state) const;
  [[nodiscard]] StopObservationResult stopAndObserveAfterFailure(IStateExecutor & executor) const;
  [[nodiscard]] static RunResult error(Failure failure, std::uint64_t transition_count = 0);

  const StateActionRegistry & actions_;
  const TransitionContractRegistry & contracts_;
  IWorldObserver * observer_;
  ICheckpointStore * checkpoint_store_;
  const CommonResumeValidator * common_resume_validator_;
  const PlanValidatorRegistry * plan_validators_;
  const IRecoveryPolicy * recovery_policy_;
};

}  // namespace so101_gazebo_demo::pick_place
