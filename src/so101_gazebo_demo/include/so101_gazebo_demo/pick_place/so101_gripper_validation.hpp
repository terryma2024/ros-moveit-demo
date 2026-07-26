#pragma once

#include "so101_gazebo_demo/pick_place/plan_validation.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

namespace so101_gazebo_demo::pick_place
{

[[nodiscard]] double gripperWidthAtSection(double q6, const SO101Profile & profile);
[[nodiscard]] ValidationResult validateQ6Target(const WorldSnapshot & snapshot, double target_q6,
                                                double target_width, const SO101Profile & profile);

}  // namespace so101_gazebo_demo::pick_place
