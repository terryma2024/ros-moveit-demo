#pragma once

#include <functional>

#include "pick_place_common/transition_contract.hpp"

namespace pick_place_common
{

class FunctionalTransitionContract final
    : public TransitionContractRegistry::ITransitionContract
{
public:
  using Precondition = std::function<ValidationResult(const WorldSnapshot &)>;
  using Postcondition = std::function<ValidationResult(
    const WorldSnapshot &, const WorldSnapshot &, const ActionResult &)>;

  FunctionalTransitionContract(Precondition precondition, Postcondition postcondition);
  ValidationResult validatePrecondition(const WorldSnapshot &) const override;
  ValidationResult validate(const WorldSnapshot &, const WorldSnapshot &,
                            const ActionResult &) const override;

private:
  Precondition precondition_;
  Postcondition postcondition_;
};

}  // namespace pick_place_common
