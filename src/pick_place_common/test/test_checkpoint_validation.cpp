#include <gtest/gtest.h>

#include <cmath>
#include <limits>

#include "pick_place_common/checkpoint_validation.hpp"

namespace pp = pick_place_common;

TEST(CheckpointValidation, ComparesNamedJointsAtToleranceBoundariesAndAnyOrder)
{
  const std::map<std::string, double> expected{{"a", 1.0}, {"b", 2.0}};
  auto comparison = pp::compareNamedJointPositions(expected, {{"b", 2.125}, {"a", 1.0}}, 0.125);
  EXPECT_TRUE(comparison.complete);
  EXPECT_TRUE(comparison.within_tolerance);
  EXPECT_DOUBLE_EQ(0.125, comparison.maximum_error);

  comparison = pp::compareNamedJointPositions(expected, {{"a", 1.0}, {"b", 2.100001}}, 0.1);
  EXPECT_TRUE(comparison.complete);
  EXPECT_FALSE(comparison.within_tolerance);
}

TEST(CheckpointValidation, DefinesInvalidComparisonAsIncompleteWithInfiniteMaximum)
{
  const std::map<std::string, double> one{{"a", 1.0}};
  for (const auto result : {
         pp::compareNamedJointPositions(one, {}, 0.1),
         pp::compareNamedJointPositions(one, {{"a", 1.0}, {"b", 2.0}}, 0.1),
         pp::compareNamedJointPositions(one, {{"a", NAN}}, 0.1),
         pp::compareNamedJointPositions(one, one, -1.0),
         pp::compareNamedJointPositions(one, one, NAN),
       }) {
    EXPECT_FALSE(result.complete);
    EXPECT_FALSE(result.within_tolerance);
    EXPECT_TRUE(std::isinf(result.maximum_error));
  }
  const auto empty = pp::compareNamedJointPositions({}, {}, 0.0);
  EXPECT_TRUE(empty.complete);
  EXPECT_TRUE(empty.within_tolerance);
  EXPECT_EQ(0.0, empty.maximum_error);
}

TEST(CheckpointValidation, FinitePredicatesRejectEmptyNamesAndNonFiniteValues)
{
  EXPECT_TRUE(pp::hasFiniteJointPositions({}));
  EXPECT_TRUE(pp::hasFinitePoseMap({}));
  EXPECT_TRUE(pp::hasFiniteJointPositions({{"joint", 1.0}}));
  EXPECT_FALSE(pp::hasFiniteJointPositions({{"", 1.0}}));
  EXPECT_FALSE(pp::hasFiniteJointPositions({{"joint", INFINITY}}));
  EXPECT_TRUE(pp::hasFinitePoseMap({{"object", {0, 0, 0, 0, 0, 0, 1}}}));
  EXPECT_FALSE(pp::hasFinitePoseMap({{"object", {NAN, 0, 0, 0, 0, 0, 1}}}));
}
