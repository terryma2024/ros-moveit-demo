#pragma once
#include <map>
#include <memory>
#include <optional>
#include <utility>
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
class ITransitionValidationDecorator
{
public:
  virtual ~ITransitionValidationDecorator() = default;
  virtual ValidationResult decoratePrecondition(TransitionKey, const WorldSnapshot &,
                                                ValidationResult) const = 0;
  virtual ValidationResult decoratePostcondition(TransitionKey, const WorldSnapshot &,
                                                 const WorldSnapshot &, const ActionResult &,
                                                 ValidationResult) const = 0;
  virtual ValidationResult decorateResume(TransitionKey, const WorldSnapshot &,
                                          const WorldSnapshot &, ValidationResult) const = 0;
};
class TransitionContractRegistry
{
public:
  explicit TransitionContractRegistry(
    bool reject_null = true, bool reject_duplicate = true,
    std::shared_ptr<const ITransitionValidationDecorator> decorator = nullptr) :
      reject_null_(reject_null), reject_duplicate_(reject_duplicate),
      decorator_(std::move(decorator))
  {
  }
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
  bool reject_null_;
  bool reject_duplicate_;
  std::shared_ptr<const ITransitionValidationDecorator> decorator_;
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
