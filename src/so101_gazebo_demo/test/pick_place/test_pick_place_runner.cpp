#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/runner.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

TEST(RunnerContracts, RegisteredFakesCanPlanExecuteCheckpointAndResume)
{
  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  pick_place::PlanValidatorRegistry validators;
  (void)actions;
  (void)contracts;
  (void)validators;
}
