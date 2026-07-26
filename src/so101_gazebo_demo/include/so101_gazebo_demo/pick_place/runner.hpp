#pragma once
#include "so101_gazebo_demo/pick_place/domain_types.hpp"
namespace so101_gazebo_demo::pick_place
{
// This core intentionally has no ROS or physical executors. Only dry_run is safe here.
class StateMachineRunner { public: [[nodiscard]] RunResult run(const RunRequest & request) const; };
}  // namespace so101_gazebo_demo::pick_place
