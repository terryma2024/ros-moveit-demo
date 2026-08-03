#include "so101_gazebo_demo/pick_place/common_resume_validator.hpp"

#include <memory>

#include "so101_gazebo_demo/pick_place/so101_resume_validation_policy.hpp"

namespace so101_gazebo_demo::pick_place
{

CommonResumeValidator::CommonResumeValidator(std::string policy_bundle_sha256,
                                             std::string simulation_session_id, double tolerance) :
    pick_place_common::CommonResumeValidator(
      std::move(policy_bundle_sha256), std::move(simulation_session_id),
      std::make_shared<SO101ResumeValidationPolicy>(), tolerance)
{
}

}  // namespace so101_gazebo_demo::pick_place
