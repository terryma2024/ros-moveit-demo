#pragma once

#include "pick_place_common/checkpoint.hpp"
#include "pick_place_common/common_resume_validator.hpp"
#include "pick_place_common/recovery_policy.hpp"
#include "pick_place_common/transition_contract.hpp"

namespace pick_place_common
{

class IExecutionObservationSink
{
public:
  virtual ~IExecutionObservationSink() = default;
  virtual void record(State, const WorldSnapshot &, const WorldSnapshot &) = 0;
};

class IRunnerBehaviorPolicy
{
public:
  virtual ~IRunnerBehaviorPolicy() = default;
  virtual bool retryPrecondition(State, const Failure &, std::size_t attempt) const = 0;
  virtual bool retryPostcondition(State, const Failure &, std::size_t attempt) const = 0;
  virtual bool includeIdleInTrace() const noexcept = 0;
  virtual bool runExecutePreflight() const noexcept = 0;
  virtual bool recoverForwardObservationFailure() const noexcept = 0;
  virtual bool preserveEnvironmentFailureWithoutRecovery() const noexcept = 0;
  virtual bool retryTransientObservation(State, const Failure &, std::size_t) const = 0;
  virtual bool waitForStationaryObjectOnResume() const noexcept = 0;
  virtual bool preserveOriginalFailureOnRecoveryError() const noexcept = 0;
};

class DefaultRunnerBehaviorPolicy final : public IRunnerBehaviorPolicy
{
public:
  bool retryPrecondition(State, const Failure &, std::size_t) const override
  {
    return false;
  }
  bool retryPostcondition(State, const Failure &, std::size_t) const override
  {
    return false;
  }
  bool includeIdleInTrace() const noexcept override
  {
    return false;
  }
  bool runExecutePreflight() const noexcept override { return false; }
  bool recoverForwardObservationFailure() const noexcept override { return true; }
  bool preserveEnvironmentFailureWithoutRecovery() const noexcept override { return false; }
  bool retryTransientObservation(State, const Failure &, std::size_t) const override { return false; }
  bool waitForStationaryObjectOnResume() const noexcept override { return true; }
  bool preserveOriginalFailureOnRecoveryError() const noexcept override { return false; }
};

class StateMachineRunner
{
public:
  StateMachineRunner(const WorkflowDefinition &, const StateActionRegistry &,
                     const TransitionContractRegistry &, IWorldObserver * = nullptr,
                     ICheckpointStore * = nullptr, const CommonResumeValidator * = nullptr,
                     IExecutionObservationSink * = nullptr, const PlanValidatorRegistry * = nullptr,
                     const IRecoveryPolicy * = nullptr, const IRunnerBehaviorPolicy * = nullptr);
  [[nodiscard]] RunResult run(const RunRequest &) const;

private:
  [[nodiscard]] RunResult runDryRun(const RunRequest &) const;
  [[nodiscard]] RunResult runPlanOnlyTarget(State, const RunRequest &,
                                            std::optional<ObservationResult> = std::nullopt,
                                            std::uint64_t checkpoint_sequence = 1) const;
  [[nodiscard]] RunResult runExecuteWorkflow(
    State, const RunRequest &, std::optional<WorldSnapshot> = std::nullopt,
    std::uint64_t checkpoint_sequence = 1, std::uint64_t initial_transition_count = 0,
    CheckpointPhase = CheckpointPhase::FORWARD, std::optional<State> failed_state = std::nullopt,
    std::optional<Failure> original_failure = std::nullopt, bool include_idle = false) const;
  [[nodiscard]] RunResult
  runExecuteStep(State, std::optional<WorldSnapshot> = std::nullopt,
                 std::uint64_t checkpoint_sequence = 1, CheckpointPhase = CheckpointPhase::FORWARD,
                 std::optional<State> failed_state = std::nullopt,
                 std::optional<Failure> original_failure = std::nullopt) const;
  [[nodiscard]] RunResult runResume(const RunRequest &) const;
  [[nodiscard]] RunResult handleActionFailure(State, IStateExecutor &, Failure,
                                              std::uint64_t checkpoint_sequence) const;
  struct StopObservationResult
  {
    std::optional<WorldSnapshot> snapshot;
    std::optional<Failure> failure;
  };
  [[nodiscard]] StopObservationResult stopAndObserveAfterFailure(IStateExecutor &) const;
  [[nodiscard]] static RunResult error(State, Failure, std::uint64_t transition_count = 0);
  [[nodiscard]] State resolve(State, ActionStatus) const;
  [[nodiscard]] bool terminal(State) const;
  [[nodiscard]] bool forwardAction(State) const;

  const WorkflowDefinition & workflow_;
  const StateActionRegistry & actions_;
  const TransitionContractRegistry & contracts_;
  IWorldObserver * observer_;
  ICheckpointStore * checkpoint_store_;
  const CommonResumeValidator * resume_validator_;
  IExecutionObservationSink * observation_sink_;
  const PlanValidatorRegistry * plan_validators_;
  const IRecoveryPolicy * recovery_policy_;
  const IRunnerBehaviorPolicy & behavior_policy_;
};

}  // namespace pick_place_common
