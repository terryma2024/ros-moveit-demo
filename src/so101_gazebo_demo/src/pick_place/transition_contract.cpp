#include "so101_gazebo_demo/pick_place/transition_contract.hpp"

#include "so101_gazebo_demo/pick_place/transition_table.hpp"

namespace so101_gazebo_demo::pick_place
{
void TransitionContractRegistry::registerContract(
  TransitionKey key, std::shared_ptr<const ITransitionContract> contract)
{
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

std::optional<Failure> TransitionContractRegistry::validateExecuteCoverage() const
{
  for (const auto & [state, transitions] : TransitionTable::entries()) {
    if (state == State::IDLE || isTerminal(state)) {
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
}  // namespace so101_gazebo_demo::pick_place
