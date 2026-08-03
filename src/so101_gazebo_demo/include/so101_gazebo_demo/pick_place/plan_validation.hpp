#pragma once
#include "so101_gazebo_demo/pick_place/state_action.hpp"
#include <pick_place_common/plan_validation.hpp>
namespace so101_gazebo_demo::pick_place
{
using pick_place_common::IPlanValidator;
using pick_place_common::NonEmptyPlanValidator;
using pick_place_common::PlanValidatorRegistry;
using pick_place_common::ValidationResult;
}  // namespace so101_gazebo_demo::pick_place
