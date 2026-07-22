#pragma once

#include "panda_gazebo_demo/pick_place/checkpoint.hpp"
#include "panda_gazebo_demo/pick_place/common_resume_validator.hpp"
#include "panda_gazebo_demo/pick_place/plan_validation.hpp"
#include "panda_gazebo_demo/pick_place/recovery_policy.hpp"
#include "panda_gazebo_demo/pick_place/state_action.hpp"
#include "panda_gazebo_demo/pick_place/transition_contract.hpp"
#include "panda_gazebo_demo/pick_place/transition_table.hpp"
#include "panda_gazebo_demo/pick_place/world_observer.hpp"

namespace panda_gazebo_demo::pick_place
{

class IExecutionObservationSink
{
public:
  virtual ~IExecutionObservationSink() = default;
  virtual void record(
    State state, const WorldSnapshot & before,
    const WorldSnapshot & after) = 0;
};

class StateMachineRunner
{
public:
  StateMachineRunner(
    const StateActionRegistry & actions,
    const TransitionContractRegistry & contracts, IWorldObserver * observer = nullptr,
    ICheckpointStore * checkpoint_store = nullptr,
    const CommonResumeValidator * common_resume_validator = nullptr,
    IExecutionObservationSink * execution_observation_sink = nullptr,
    const PlanValidatorRegistry * plan_validators = nullptr,
    const IRecoveryPolicy * recovery_policy = nullptr)
  : actions_(actions), contracts_(contracts), observer_(observer),
    checkpoint_store_(checkpoint_store), common_resume_validator_(common_resume_validator),
    execution_observation_sink_(execution_observation_sink), plan_validators_(plan_validators),
    recovery_policy_(recovery_policy) {}

  [[nodiscard]] RunResult run(const RunRequest & request) const;

private:
  [[nodiscard]] RunResult runDryRun(const RunRequest & request) const;
  [[nodiscard]] RunResult runPlanOnly(const RunRequest & request) const;
  [[nodiscard]] RunResult runPlanOnly(
    State state, const RunRequest & request,
    std::optional<ObservationResult> observation = std::nullopt) const;
  [[nodiscard]] RunResult runExecuteWorkflow(
    State initial_state, const RunRequest & request,
    std::optional<WorldSnapshot> initial_snapshot = std::nullopt,
    std::uint64_t checkpoint_sequence = 1,
    std::uint64_t initial_transition_count = 0,
    CheckpointPhase phase = CheckpointPhase::FORWARD,
    std::optional<State> failed_state = std::nullopt,
    std::optional<Failure> original_failure = std::nullopt) const;
  [[nodiscard]] RunResult runExecuteStep(
    State state,
    std::optional<WorldSnapshot> before = std::nullopt,
    std::uint64_t checkpoint_sequence = 1,
    CheckpointPhase phase = CheckpointPhase::FORWARD,
    std::optional<State> failed_state = std::nullopt,
    std::optional<Failure> original_failure = std::nullopt) const;
  [[nodiscard]] RunResult runResume(const RunRequest & request) const;
  [[nodiscard]] RunResult handleActionFailure(
    State state, IStateExecutor & executor, Failure original_failure,
    std::uint64_t checkpoint_sequence) const;
  struct StopObservationResult
  {
    std::optional<WorldSnapshot> snapshot;
    std::optional<Failure> failure;
  };
  [[nodiscard]] StopObservationResult stopAndObserveAfterFailure(
    IStateExecutor & executor) const;
  [[nodiscard]] static RunResult error(
    State state, Failure failure,
    std::uint64_t transition_count = 0);

  const StateActionRegistry & actions_;
  const TransitionContractRegistry & contracts_;
  IWorldObserver * observer_;
  ICheckpointStore * checkpoint_store_;
  const CommonResumeValidator * common_resume_validator_;
  IExecutionObservationSink * execution_observation_sink_;
  const PlanValidatorRegistry * plan_validators_;
  const IRecoveryPolicy * recovery_policy_;
};

}  // namespace panda_gazebo_demo::pick_place
