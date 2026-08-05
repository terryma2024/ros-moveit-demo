#include <gtest/gtest.h>

#include "pick_place_common/validation_result_utils.hpp"

namespace pp = pick_place_common;

TEST(ValidationResultUtils, AppendMergeAndFinalizePreserveAssemblySemantics)
{
  pp::ValidationResult result{true, {}, {{"shared", 1.0}, {"first", 2.0}}};
  pp::appendFailure(result, pp::FailureCategory::PRECONDITION, "FIRST", "first failure");
  pp::ValidationResult additional{
    false,
    {{pp::FailureCategory::POSTCONDITION, "SECOND", "second failure", {{"shared", 9.0}}}},
    {{"shared", 3.0}, {"second", 4.0}}};

  pp::mergeValidationResult(result, std::move(additional));
  result = pp::finalizeValidationResult(std::move(result));

  ASSERT_FALSE(result.ok);
  ASSERT_EQ(2U, result.failures.size());
  EXPECT_EQ("FIRST", result.failures[0].code);
  EXPECT_EQ("SECOND", result.failures[1].code);
  EXPECT_EQ(1.0, result.metrics.at("shared"));
  EXPECT_EQ(4.0, result.metrics.at("second"));
  EXPECT_EQ(1.0, result.failures[0].metrics.at("shared"));
  EXPECT_EQ(9.0, result.failures[1].metrics.at("shared"));
  EXPECT_EQ(2.0, result.failures[1].metrics.at("first"));
}

TEST(ValidationResultUtils, FinalizeDerivesOkOnlyFromFailureEmptiness)
{
  EXPECT_TRUE(pp::finalizeValidationResult({false, {}, {}}).ok);
  EXPECT_FALSE(pp::finalizeValidationResult(
                 {true, {{pp::FailureCategory::EXECUTION, "E", "error", {}}}, {}})
                 .ok);
}
