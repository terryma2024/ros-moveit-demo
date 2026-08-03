#pragma once
#include <map>
#include <memory>
#include <vector>
#include "pick_place_common/state_action.hpp"
namespace pick_place_common
{
struct ValidationResult
{
  bool ok{false};
  std::vector<Failure> failures;
  std::map<std::string, double> metrics;
};
class IPlanValidator
{
public:
  virtual ~IPlanValidator() = default;
  virtual ValidationResult validate(State, const WorldSnapshot &, const PlanArtifact &) const = 0;
};
class PlanValidatorRegistry
{
public:
  void registerValidator(State, std::shared_ptr<const IPlanValidator>);
  bool hasValidator(State) const noexcept;
  ValidationResult validate(State, const WorldSnapshot &, const PlanArtifact &) const;

private:
  std::map<State, std::shared_ptr<const IPlanValidator>> validators_;
};
class NonEmptyPlanValidator final : public IPlanValidator
{
public:
  ValidationResult validate(State, const WorldSnapshot &, const PlanArtifact &) const override;
};
}  // namespace pick_place_common
