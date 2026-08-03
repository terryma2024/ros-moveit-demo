#pragma once
#include <memory>
#include <string>
#include "pick_place_common/checkpoint.hpp"
#include "pick_place_common/plan_validation.hpp"
namespace pick_place_common
{
class IResumeValidationPolicy
{
public:
  virtual ~IResumeValidationPolicy() = default;
  virtual ValidationResult validateBoundary(const Checkpoint &, const WorldSnapshot &,
                                            double tolerance) const = 0;
  virtual std::string fingerprintMismatchCode() const = 0;
};
class CommonResumeValidator
{
public:
  CommonResumeValidator(std::string configuration_fingerprint,
                        std::string simulation_session_id,
                        std::shared_ptr<const IResumeValidationPolicy> policy,
                        double tolerance = 0.01);
  ValidationResult validate(const Checkpoint &, const WorldSnapshot &) const;
  const std::string & configurationFingerprint() const noexcept;
  const std::string & simulationSessionId() const noexcept;
private:
  std::string configuration_fingerprint_;
  std::string simulation_session_id_;
  std::shared_ptr<const IResumeValidationPolicy> policy_;
  double tolerance_;
};
}  // namespace pick_place_common
