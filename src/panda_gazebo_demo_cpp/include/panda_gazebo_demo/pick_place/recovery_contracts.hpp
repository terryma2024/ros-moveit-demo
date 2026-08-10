#pragma once

#include "panda_gazebo_demo/pick_place/pick_place_contracts.hpp"

namespace panda_gazebo_demo::pick_place
{

void registerRecoveryContracts(TransitionContractRegistry & registry,
                               const TargetPolicyPtr & target_policy,
                               const PickPlaceContractConfig & config);

}  // namespace panda_gazebo_demo::pick_place
