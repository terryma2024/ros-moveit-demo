#include "pick_place_common/common_resume_validator.hpp"
#include <cmath>
#include <stdexcept>
namespace pick_place_common
{
CommonResumeValidator::CommonResumeValidator(std::string fingerprint, std::string session,
                                             std::shared_ptr<const IResumeValidationPolicy> policy,
                                             double tolerance)
: configuration_fingerprint_(std::move(fingerprint)), simulation_session_id_(std::move(session)),
  policy_(std::move(policy)), tolerance_(tolerance)
{
  if (!std::isfinite(tolerance_) || tolerance_ < 0.0 || !policy_) {
    throw std::invalid_argument("resume validator requires policy and finite non-negative tolerance");
  }
}
ValidationResult CommonResumeValidator::validate(const Checkpoint & checkpoint,
                                                 const WorldSnapshot & current) const
{
  std::vector<Failure> failures;
  const auto add = [&failures](std::string code, std::string message) {
    failures.push_back({FailureCategory::RESUME_VALIDATION, std::move(code), std::move(message), {}});
  };
  if (checkpoint.schema_version != 3) add("CHECKPOINT_INCOMPATIBLE", "checkpoint schema is not v3");
  if (checkpoint.configuration_fingerprint != configuration_fingerprint_)
    add(policy_->fingerprintMismatchCode(), "configuration fingerprint mismatch");
  if (checkpoint.simulation_session_id.empty() || simulation_session_id_.empty() ||
      checkpoint.simulation_session_id != simulation_session_id_ ||
      current.simulation_session_id != simulation_session_id_)
    add("RESUME_SIMULATION_SESSION_MISMATCH", "simulation session mismatch");
  if (!current.fresh || !current.arm_stationary)
    add("RESUME_ARM_NOT_QUIESCENT", "current observation must be fresh and stationary");
  auto boundary = policy_->validateBoundary(checkpoint, current, tolerance_);
  failures.insert(failures.end(), boundary.failures.begin(), boundary.failures.end());
  return {failures.empty(), std::move(failures), std::move(boundary.metrics)};
}
const std::string & CommonResumeValidator::configurationFingerprint() const noexcept
{ return configuration_fingerprint_; }
const std::string & CommonResumeValidator::simulationSessionId() const noexcept
{ return simulation_session_id_; }
}  // namespace pick_place_common
