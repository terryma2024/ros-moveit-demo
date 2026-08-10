#pragma once

#include <pick_place_common/runner.hpp>

#include "panda_gazebo_demo/pick_place/checkpoint.hpp"
#include "panda_gazebo_demo/pick_place/common_resume_validator.hpp"
#include "panda_gazebo_demo/pick_place/panda_workflow.hpp"
#include "panda_gazebo_demo/pick_place/plan_validation.hpp"
#include "panda_gazebo_demo/pick_place/recovery_policy.hpp"
#include "panda_gazebo_demo/pick_place/state_action.hpp"
#include "panda_gazebo_demo/pick_place/transition_contract.hpp"
#include "panda_gazebo_demo/pick_place/transition_table.hpp"
#include "panda_gazebo_demo/pick_place/world_observer.hpp"

namespace panda_gazebo_demo::pick_place
{

using pick_place_common::IExecutionObservationSink;

class StateMachineRunner
{
public:
  StateMachineRunner(const StateActionRegistry & actions,
                     const TransitionContractRegistry & contracts,
                     IWorldObserver * observer = nullptr,
                     ICheckpointStore * checkpoint_store = nullptr,
                     const CommonResumeValidator * resume_validator = nullptr,
                     IExecutionObservationSink * observation_sink = nullptr,
                     const PlanValidatorRegistry * plan_validators = nullptr,
                     const IRecoveryPolicy * recovery_policy = nullptr) :
      impl_(pandaWorkflowDefinition(), actions, contracts, observer, checkpoint_store,
            resume_validator, observation_sink, plan_validators, recovery_policy)
  {
  }

  [[nodiscard]] RunResult run(const RunRequest & request) const
  {
    return impl_.run(request);
  }

private:
  pick_place_common::StateMachineRunner impl_;
};

}  // namespace panda_gazebo_demo::pick_place
