#pragma once

#include <pick_place_common/common_resume_validator.hpp>

namespace panda_gazebo_demo::pick_place
{

class PandaResumeValidationPolicy final : public pick_place_common::IResumeValidationPolicy
{
public:
  [[nodiscard]] pick_place_common::ValidationResult
  validateBoundary(const pick_place_common::Checkpoint & checkpoint,
                   const pick_place_common::WorldSnapshot & current,
                   double tolerance) const override;
  [[nodiscard]] std::string fingerprintMismatchCode() const override;
};

}  // namespace panda_gazebo_demo::pick_place
