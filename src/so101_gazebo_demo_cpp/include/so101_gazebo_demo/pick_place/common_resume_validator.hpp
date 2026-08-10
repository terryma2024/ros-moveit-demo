#pragma once

#include <pick_place_common/common_resume_validator.hpp>

#include "so101_gazebo_demo/pick_place/checkpoint.hpp"

namespace so101_gazebo_demo::pick_place
{

class CommonResumeValidator final : public pick_place_common::CommonResumeValidator
{
public:
  CommonResumeValidator(std::string policy_bundle_sha256, std::string simulation_session_id,
                        double tolerance = 0.01);
  [[nodiscard]] const std::string & policyBundleSha256() const noexcept
  {
    return configurationFingerprint();
  }
};

}  // namespace so101_gazebo_demo::pick_place
