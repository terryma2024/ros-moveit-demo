#include "so101_gazebo_demo/pick_place/runner.hpp"

namespace so101_gazebo_demo::pick_place
{
// Compatibility surface only; the workflow algorithm lives in pick_place_common.
namespace
{
const StateActionRegistry kEmptyActions;
const TransitionContractRegistry kEmptyContracts;
}  // namespace

StateMachineRunner::StateMachineRunner() : StateMachineRunner(kEmptyActions, kEmptyContracts) {}

StateMachineRunner::StateMachineRunner(const StateActionRegistry & actions,
                                       const TransitionContractRegistry & contracts,
                                       IWorldObserver * observer,
                                       ICheckpointStore * checkpoint_store,
                                       const CommonResumeValidator * resume_validator,
                                       const PlanValidatorRegistry * plan_validators,
                                       const IRecoveryPolicy * recovery_policy) :
    behavior_policy_(),
    impl_(so101WorkflowDefinition(), actions, contracts, observer, checkpoint_store,
          resume_validator, nullptr, plan_validators, recovery_policy, &behavior_policy_)
{
}

RunResult StateMachineRunner::run(const RunRequest & request) const
{
  return impl_.run(request);
}

}  // namespace so101_gazebo_demo::pick_place
