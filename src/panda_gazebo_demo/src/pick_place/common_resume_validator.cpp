#include "panda_gazebo_demo/pick_place/common_resume_validator.hpp"

#include <memory>

#include "panda_gazebo_demo/pick_place/panda_resume_validation_policy.hpp"

namespace panda_gazebo_demo::pick_place
{

CommonResumeValidator::CommonResumeValidator(std::string configuration_fingerprint,
                                             std::string simulation_session_id,
                                             double joint_position_tolerance) :
    pick_place_common::CommonResumeValidator(
      std::move(configuration_fingerprint), std::move(simulation_session_id),
      std::make_shared<PandaResumeValidationPolicy>(), joint_position_tolerance)
{
}

}  // namespace panda_gazebo_demo::pick_place
