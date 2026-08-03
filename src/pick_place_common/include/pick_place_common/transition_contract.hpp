#pragma once
#include <map>
#include <memory>
#include <optional>
#include "pick_place_common/plan_validation.hpp"
#include "pick_place_common/workflow_definition.hpp"
namespace pick_place_common
{
struct TransitionKey
{
  State from;
  State to;
  friend bool operator<(const TransitionKey & a, const TransitionKey & b) noexcept
  {
    return a.from != b.from ? a.from < b.from : a.to < b.to;
  }
};
class TransitionContractRegistry
{
public:
  class ITransitionContract
  {
  public:
    virtual ~ITransitionContract() = default;
    virtual ValidationResult validatePrecondition(const WorldSnapshot &) const = 0;
    virtual ValidationResult validate(const WorldSnapshot &, const WorldSnapshot &,
                                      const ActionResult &) const = 0;
  };
  void registerContract(TransitionKey, std::shared_ptr<const ITransitionContract>);
  bool hasContract(TransitionKey) const noexcept;
  ValidationResult validatePrecondition(TransitionKey, const WorldSnapshot &) const;
  ValidationResult validate(TransitionKey, const WorldSnapshot &, const WorldSnapshot &,
                            const ActionResult &) const;
  ValidationResult validateResume(TransitionKey, const WorldSnapshot &,
                                  const WorldSnapshot &) const;
  std::optional<Failure> validateExecuteCoverage(const WorkflowDefinition &) const;

private:
  std::map<TransitionKey, std::shared_ptr<const ITransitionContract>> contracts_;
};
class AlwaysPassValidator final : public TransitionContractRegistry::ITransitionContract
{
public:
  ValidationResult validatePrecondition(const WorldSnapshot &) const override;
  ValidationResult validate(const WorldSnapshot &, const WorldSnapshot &,
                            const ActionResult &) const override;
};
}  // namespace pick_place_common
