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
  StateMachineRunner(
    const StateActionRegistry &, const TransitionContractRegistry &,
    IWorldObserver * = nullptr, ICheckpointStore * = nullptr,
    const CommonResumeValidator * = nullptr, const PlanValidatorRegistry * = nullptr,
    const IRecoveryPolicy * = nullptr);
  RunResult run(const RunRequest &) const;
private:
  RunResult dry(const RunRequest &) const;
  RunResult execute(State, const RunRequest &, std::optional<WorldSnapshot>, std::uint64_t) const;
  RunResult error(Failure) const;
  const StateActionRegistry & actions_;
  const TransitionContractRegistry & contracts_;
  IWorldObserver * observer_;
  ICheckpointStore * store_;
  const CommonResumeValidator * resume_;
  const PlanValidatorRegistry * validators_;
  const IRecoveryPolicy * recovery_;
};
}  // namespace so101_gazebo_demo::pick_place
