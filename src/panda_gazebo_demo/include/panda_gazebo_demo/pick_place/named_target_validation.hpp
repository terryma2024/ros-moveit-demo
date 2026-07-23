#pragma once

#include <map>
#include <string>

#include "panda_gazebo_demo/pick_place/motion_plan_evidence.hpp"

namespace panda_gazebo_demo::pick_place
{

[[nodiscard]] ValidationResult validateNamedJointTarget(
  const WorldSnapshot & snapshot,
  const std::map<std::string, double> & target_joint_positions,
  double tolerance);

class NamedTargetPlanValidator final : public IPlanValidator
{
public:
  NamedTargetPlanValidator(
    State state, State next_state, std::string named_target,
    std::map<std::string, double> target_joint_positions, double joint_tolerance);

  [[nodiscard]] ValidationResult validate(
    State state, const WorldSnapshot & before,
    const PlanArtifact & artifact) const override;

private:
  State state_;
  State next_state_;
  std::string named_target_;
  std::map<std::string, double> target_joint_positions_;
  double joint_tolerance_;
};

}  // namespace panda_gazebo_demo::pick_place
