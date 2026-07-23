#pragma once

#include <map>
#include <memory>

#include "panda_gazebo_demo/pick_place/state_action.hpp"
#include "panda_gazebo_demo/pick_place/transition_contract.hpp"

namespace panda_gazebo_demo::pick_place
{

class IPlanValidator
{
public:
  virtual ~IPlanValidator() = default;
  [[nodiscard]] virtual ValidationResult validate(State state, const WorldSnapshot & before,
                                                  const PlanArtifact & artifact) const = 0;
};

class PlanValidatorRegistry
{
public:
  void registerValidator(State state, std::shared_ptr<const IPlanValidator> validator);
  [[nodiscard]] bool hasValidator(State state) const noexcept;
  [[nodiscard]] ValidationResult validate(State state, const WorldSnapshot & before,
                                          const PlanArtifact & artifact) const;

private:
  std::map<State, std::shared_ptr<const IPlanValidator>> validators_;
};

class NonEmptyPlanValidator final : public IPlanValidator
{
public:
  [[nodiscard]] ValidationResult validate(State state, const WorldSnapshot & before,
                                          const PlanArtifact & artifact) const override;
};

}  // namespace panda_gazebo_demo::pick_place
