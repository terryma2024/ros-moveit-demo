#pragma once

#include <pick_place_common/common_resume_validator.hpp>

namespace so101_gazebo_demo::pick_place
{

class SO101ResumeValidationPolicy final : public pick_place_common::IResumeValidationPolicy
{
public:
  [[nodiscard]] pick_place_common::ValidationResult
  validateBoundary(const pick_place_common::Checkpoint &, const pick_place_common::WorldSnapshot &,
                   double tolerance) const override;
  [[nodiscard]] std::string fingerprintMismatchCode() const override;
};

}  // namespace so101_gazebo_demo::pick_place
