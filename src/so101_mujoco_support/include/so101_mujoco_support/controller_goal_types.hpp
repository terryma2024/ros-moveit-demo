// Copyright 2026 zjumty
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#ifndef SO101_MUJOCO_SUPPORT__CONTROLLER_GOAL_TYPES_HPP_
#define SO101_MUJOCO_SUPPORT__CONTROLLER_GOAL_TYPES_HPP_

#include <array>
#include <cstdint>

#include "control_msgs/action/follow_joint_trajectory.hpp"

namespace so101_mujoco_support
{

// Shared goal types, declared once in a leaf header so the admission primitive and
// the bound reservation request agree without a circular include.
using ControllerGoalUUID = std::array<uint8_t, 16>;
using ControllerGoal = control_msgs::action::FollowJointTrajectory::Goal;

}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__CONTROLLER_GOAL_TYPES_HPP_
