#pragma once

#include "panda_gazebo_demo/pick_place/checkpoint.hpp"
#include "panda_gazebo_demo/pick_place/common_resume_validator.hpp"
#include "panda_gazebo_demo/pick_place/state_action.hpp"
#include "panda_gazebo_demo/pick_place/transition_contract.hpp"
#include "panda_gazebo_demo/pick_place/transition_table.hpp"
#include "panda_gazebo_demo/pick_place/world_observer.hpp"

namespace panda_gazebo_demo::pick_place
{

class StateMachineRunner
{
public:
  StateMachineRunner(
    const StateActionRegistry & actions,
    const TransitionContractRegistry & contracts, IWorldObserver * observer = nullptr,
    ICheckpointStore * checkpoint_store = nullptr,
    const CommonResumeValidator * common_resume_validator = nullptr)
  : actions_(actions), contracts_(contracts), observer_(observer),
    checkpoint_store_(checkpoint_store), common_resume_validator_(common_resume_validator) {}

  [[nodiscard]] RunResult run(const RunRequest & request) const;

private:
  [[nodiscard]] RunResult runDryRun(const RunRequest & request) const;
  [[nodiscard]] RunResult runPlanOnly(const RunRequest & request) const;
  [[nodiscard]] RunResult runPlanOnly(State state, const RunRequest & request) const;
  [[nodiscard]] RunResult runExecuteMoveAboveObject(const RunRequest & request) const;
  [[nodiscard]] RunResult runExecuteStep(
    State state, State next_state, const RunRequest & request,
    std::optional<WorldSnapshot> before = std::nullopt,
    std::uint64_t checkpoint_sequence = 1) const;
  [[nodiscard]] RunResult runResume(const RunRequest & request) const;
  [[nodiscard]] std::optional<Failure> stopAndObserveAfterFailure(
    State state, IStateExecutor & executor, Failure original_failure) const;
  [[nodiscard]] static RunResult error(
    State state, Failure failure,
    std::uint64_t transition_count = 0);

  const StateActionRegistry & actions_;
  const TransitionContractRegistry & contracts_;
  IWorldObserver * observer_;
  ICheckpointStore * checkpoint_store_;
  const CommonResumeValidator * common_resume_validator_;
};

}  // namespace panda_gazebo_demo::pick_place
