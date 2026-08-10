#pragma once

#include <pick_place_common/transition_contract.hpp>

#include "so101_gazebo_demo/pick_place/plan_validation.hpp"
#include "so101_gazebo_demo/pick_place/so101_workflow.hpp"

namespace so101_gazebo_demo::pick_place
{

using pick_place_common::AlwaysPassValidator;
using pick_place_common::TransitionKey;

class TransitionContractRegistry : public pick_place_common::TransitionContractRegistry
{
public:
  using pick_place_common::TransitionContractRegistry::TransitionContractRegistry;
  [[nodiscard]] std::optional<Failure> validateExecuteCoverage() const
  {
    return pick_place_common::TransitionContractRegistry::validateExecuteCoverage(
      so101WorkflowDefinition());
  }
};

}  // namespace so101_gazebo_demo::pick_place
