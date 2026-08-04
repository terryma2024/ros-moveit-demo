#include <gtest/gtest.h>

#include "pick_place_common/functional_transition_contract.hpp"

namespace pp = pick_place_common;

TEST(FunctionalTransitionContract, DelegatesBothFunctionsWithOriginalArguments)
{
  pp::WorldSnapshot before;
  pp::WorldSnapshot after;
  before.fresh = true;
  after.arm_stationary = true;
  pp::FunctionalTransitionContract contract(
    [&](const pp::WorldSnapshot & value) {
      EXPECT_EQ(&before, &value);
      return pp::ValidationResult{true, {}, {{"pre", 1.0}}};
    },
    [&](const pp::WorldSnapshot & first, const pp::WorldSnapshot & second,
        const pp::ActionResult & action) {
      EXPECT_EQ(&before, &first);
      EXPECT_EQ(&after, &second);
      EXPECT_EQ(pp::ActionStatus::FAILED, action.status);
      return pp::ValidationResult{false,
                                  {{pp::FailureCategory::POSTCONDITION, "POST", "failed", {}}},
                                  {{"post", 2.0}}};
    });

  EXPECT_EQ(1.0, contract.validatePrecondition(before).metrics.at("pre"));
  const auto post = contract.validate(before, after, {pp::ActionStatus::FAILED, {}});
  ASSERT_FALSE(post.ok);
  EXPECT_EQ("POST", post.failures.front().code);
}
