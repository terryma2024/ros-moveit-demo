#include "panda_gazebo_demo/pick_place/plan_validation.hpp"

#include <utility>

namespace panda_gazebo_demo::pick_place
{

void PlanValidatorRegistry::registerValidator(State state,
                                              std::shared_ptr<const IPlanValidator> validator)
{
  validators_[state] = std::move(validator);
}

bool PlanValidatorRegistry::hasValidator(State state) const noexcept
{
  const auto validator = validators_.find(state);
  return validator != validators_.end() && validator->second != nullptr;
}

ValidationResult PlanValidatorRegistry::validate(State state, const WorldSnapshot & before,
                                                 const PlanArtifact & artifact) const
{
  const auto validator = validators_.find(state);
  if (validator == validators_.end() || validator->second == nullptr) {
    return {false,
            {{FailureCategory::CONFIGURATION,
              "PLAN_VALIDATOR_NOT_REGISTERED",
              std::string("No plan validator is registered for ") + toString(state),
              {}}},
            {}};
  }
  return validator->second->validate(state, before, artifact);
}

ValidationResult NonEmptyPlanValidator::validate(State state, const WorldSnapshot & before,
                                                 const PlanArtifact & artifact) const
{
  static_cast<void>(state);
  static_cast<void>(before);
  if (artifact.trajectory_points == 0) {
    return {false,
            {{FailureCategory::PLAN_VALIDATION,
              "EMPTY_PLAN_ARTIFACT",
              "Planner returned an empty trajectory",
              {}}},
            {}};
  }
  return {true, {}, {{"trajectory_points", static_cast<double>(artifact.trajectory_points)}}};
}

}  // namespace panda_gazebo_demo::pick_place
