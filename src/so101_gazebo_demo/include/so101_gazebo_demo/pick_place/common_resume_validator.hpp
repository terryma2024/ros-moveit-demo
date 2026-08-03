#pragma once
#include <string>
#include "so101_gazebo_demo/pick_place/checkpoint.hpp"
#include "so101_gazebo_demo/pick_place/plan_validation.hpp"
namespace so101_gazebo_demo::pick_place
{
class CommonResumeValidator
{
public:
  CommonResumeValidator(std::string, std::string, double = 0.01);
  ValidationResult validate(const Checkpoint &, const WorldSnapshot &) const;
  const std::string & policyBundleSha256() const noexcept;
  const std::string & simulationSessionId() const noexcept;

private:
  std::string policy_bundle_sha256_;
  std::string simulation_session_id_;
  double tolerance_;
};
}  // namespace so101_gazebo_demo::pick_place
