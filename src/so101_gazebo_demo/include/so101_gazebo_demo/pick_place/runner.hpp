#pragma once

#include <pick_place_common/runner.hpp>

#include "so101_gazebo_demo/pick_place/checkpoint.hpp"
#include "so101_gazebo_demo/pick_place/common_resume_validator.hpp"
#include "so101_gazebo_demo/pick_place/plan_validation.hpp"
#include "so101_gazebo_demo/pick_place/recovery_policy.hpp"
#include "so101_gazebo_demo/pick_place/so101_runner_behavior_policy.hpp"
#include "so101_gazebo_demo/pick_place/so101_workflow.hpp"
#include "so101_gazebo_demo/pick_place/state_action.hpp"
#include "so101_gazebo_demo/pick_place/transition_contract.hpp"
#include "so101_gazebo_demo/pick_place/transition_table.hpp"

namespace so101_gazebo_demo::pick_place
{

class StateMachineRunner
{
public:
  StateMachineRunner();
  StateMachineRunner(const StateActionRegistry &, const TransitionContractRegistry &,
                     IWorldObserver * = nullptr, ICheckpointStore * = nullptr,
                     const CommonResumeValidator * = nullptr,
                     const PlanValidatorRegistry * = nullptr, const IRecoveryPolicy * = nullptr);
  [[nodiscard]] RunResult run(const RunRequest & request) const;

private:
  SO101RunnerBehaviorPolicy behavior_policy_;
  pick_place_common::StateMachineRunner impl_;
};

}  // namespace so101_gazebo_demo::pick_place
