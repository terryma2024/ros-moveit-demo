#include "pick_place_common/validation_result_utils.hpp"

#include <iterator>
#include <utility>

namespace pick_place_common
{

void appendFailure(ValidationResult & result, FailureCategory category, std::string code,
                   std::string message)
{
  result.failures.push_back({category, std::move(code), std::move(message), {}});
}

void mergeValidationResult(ValidationResult & result, ValidationResult additional)
{
  result.metrics.insert(additional.metrics.begin(), additional.metrics.end());
  result.failures.insert(result.failures.end(),
                         std::make_move_iterator(additional.failures.begin()),
                         std::make_move_iterator(additional.failures.end()));
}

ValidationResult finalizeValidationResult(ValidationResult result)
{
  result.ok = result.failures.empty();
  for (auto & failure : result.failures) {
    failure.metrics.insert(result.metrics.begin(), result.metrics.end());
  }
  return result;
}

}  // namespace pick_place_common
