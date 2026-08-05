#pragma once

#include <string>

#include "pick_place_common/plan_validation.hpp"

namespace pick_place_common
{

void appendFailure(ValidationResult &, FailureCategory, std::string code, std::string message);
void mergeValidationResult(ValidationResult &, ValidationResult additional);
[[nodiscard]] ValidationResult finalizeValidationResult(ValidationResult);

}  // namespace pick_place_common
