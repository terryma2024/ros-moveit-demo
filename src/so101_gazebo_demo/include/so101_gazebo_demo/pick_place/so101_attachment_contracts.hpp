#pragma once

#include <memory>

#include "so101_gazebo_demo/pick_place/so101_profile.hpp"
#include "so101_gazebo_demo/pick_place/transition_contract.hpp"

namespace so101_gazebo_demo::pick_place
{

[[nodiscard]] std::shared_ptr<const TransitionContractRegistry::ITransitionContract>
makeSO101AttachmentContract(TransitionKey key,
                            SO101Profile profile = SO101Profile::canonical());

void registerSO101AttachmentContracts(
  TransitionContractRegistry & registry, SO101Profile profile = SO101Profile::canonical());

}  // namespace so101_gazebo_demo::pick_place
