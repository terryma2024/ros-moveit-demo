#include "pick_place_common/transition_contract.hpp"

#include <stdexcept>

namespace pick_place_common
{
void TransitionContractRegistry::registerContract(
  TransitionKey key, std::shared_ptr<const ITransitionContract> contract)
{
  if (!contract && reject_null_)
    throw std::invalid_argument("null contract");
  if (contracts_.count(key) && reject_duplicate_)
    throw std::logic_error("duplicate contract");
  contracts_[key] = std::move(contract);
}

bool TransitionContractRegistry::hasContract(TransitionKey key) const noexcept
{
  const auto found = contracts_.find(key);
  return found != contracts_.end() && found->second;
}

ValidationResult TransitionContractRegistry::validatePrecondition(TransitionKey key,
                                                                  const WorldSnapshot & world) const
{
  const auto found = contracts_.find(key);
  return found == contracts_.end() || !found->second
           ? ValidationResult{false,
                              {{FailureCategory::CONFIGURATION,
                                "MISSING_TRANSITION_CONTRACT",
                                "contract missing",
                                {}}},
                              {}}
           : found->second->validatePrecondition(world);
}

ValidationResult TransitionContractRegistry::validate(TransitionKey key,
                                                      const WorldSnapshot & before,
                                                      const WorldSnapshot & after,
                                                      const ActionResult & result) const
{
  const auto found = contracts_.find(key);
  return found == contracts_.end() || !found->second
           ? ValidationResult{false,
                              {{FailureCategory::CONFIGURATION,
                                "MISSING_TRANSITION_CONTRACT",
                                "contract missing",
                                {}}},
                              {}}
           : found->second->validate(before, after, result);
}

ValidationResult TransitionContractRegistry::validateResume(TransitionKey key,
                                                            const WorldSnapshot & expected,
                                                            const WorldSnapshot & current) const
{
  return validate(key, expected, current, {ActionStatus::SUCCEEDED, {}});
}

std::optional<Failure> TransitionContractRegistry::validateExecuteCoverage(
  const WorkflowDefinition & workflow) const
{
  for (const auto & [state, transitions] : workflow.transitions) {
    if (state == workflow.initial_state || !workflow.forward_states.count(state) ||
        workflow.terminal_states.count(state)) {
      continue;
    }
    if (!hasContract({state, transitions.succeeded})) {
      return Failure{FailureCategory::CONFIGURATION,
                     "MISSING_TRANSITION_CONTRACT",
                     std::string("No execute transition contract registered for ") +
                       toString(state) + " -> " + toString(transitions.succeeded),
                     {}};
    }
  }
  return std::nullopt;
}

ValidationResult AlwaysPassValidator::validatePrecondition(const WorldSnapshot &) const
{
  return {true, {}, {}};
}

ValidationResult AlwaysPassValidator::validate(const WorldSnapshot &, const WorldSnapshot &,
                                               const ActionResult &) const
{
  return {true, {}, {}};
}
}  // namespace pick_place_common
