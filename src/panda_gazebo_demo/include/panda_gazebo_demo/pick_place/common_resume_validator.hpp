#pragma once

#include <pick_place_common/common_resume_validator.hpp>

#include "panda_gazebo_demo/pick_place/checkpoint.hpp"
#include "panda_gazebo_demo/pick_place/transition_contract.hpp"

namespace panda_gazebo_demo::pick_place
{

class CommonResumeValidator final : public pick_place_common::CommonResumeValidator
{
public:
  CommonResumeValidator(std::string configuration_fingerprint, std::string simulation_session_id,
                        double joint_position_tolerance = 0.01);
  [[nodiscard]] const std::string & configurationHash() const noexcept
  {
    return configurationFingerprint();
  }
};

}  // namespace panda_gazebo_demo::pick_place
