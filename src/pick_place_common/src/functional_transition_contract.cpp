#include "pick_place_common/functional_transition_contract.hpp"

#include <utility>

namespace pick_place_common
{

FunctionalTransitionContract::FunctionalTransitionContract(Precondition precondition,
                                                           Postcondition postcondition) :
    precondition_(std::move(precondition)), postcondition_(std::move(postcondition))
{
}

ValidationResult
FunctionalTransitionContract::validatePrecondition(const WorldSnapshot & before) const
{
  return precondition_(before);
}

ValidationResult FunctionalTransitionContract::validate(const WorldSnapshot & before,
                                                        const WorldSnapshot & after,
                                                        const ActionResult & action) const
{
  return postcondition_(before, after, action);
}

}  // namespace pick_place_common
