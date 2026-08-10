#pragma once
#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include "panda_gazebo_demo/pick_place/world_observer.hpp"
#include <pick_place_common/state_action.hpp>
namespace panda_gazebo_demo::pick_place
{
using pick_place_common::ExecutionContext;
using pick_place_common::IStateExecutor;
using pick_place_common::IStatePlanner;
using pick_place_common::PlanArtifact;
using pick_place_common::PlanResult;
using pick_place_common::StateActionRegistry;
}  // namespace panda_gazebo_demo::pick_place
