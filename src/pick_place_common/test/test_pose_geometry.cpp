#include <gtest/gtest.h>

#include <cmath>
#include <limits>

#include "pick_place_common/pose_geometry.hpp"

namespace pick_place_common
{
namespace
{

constexpr Pose3d kIdentity{1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0};

TEST(PoseGeometry, RejectsEveryNonFiniteComponent)
{
  for (std::size_t index = 0; index < 7; ++index) {
    Pose3d pose = kIdentity;
    (&pose.x)[index] = std::numeric_limits<double>::quiet_NaN();
    EXPECT_FALSE(isFinitePose(pose)) << index;
    (&pose.x)[index] = std::numeric_limits<double>::infinity();
    EXPECT_FALSE(isFinitePose(pose)) << index;
  }
}

TEST(PoseGeometry, RejectsZeroAndNearZeroQuaternions)
{
  Pose3d pose = kIdentity;
  pose.qw = 0.0;
  EXPECT_FALSE(hasUsableQuaternion(pose));
  pose.qw = 1.0e-13;
  EXPECT_FALSE(hasUsableQuaternion(pose));
}

TEST(PoseGeometry, NormalizesQuaternionAndTreatsOppositeSignsAsSameOrientation)
{
  const Pose3d scaled{0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 2.0};
  const Pose3d opposite{0.0, 0.0, 0.0, 0.0, 0.0, -1.0, -1.0};
  EXPECT_DOUBLE_EQ(0.0, orientationDistance(scaled, opposite));
}

TEST(PoseGeometry, RelativeAndComposeRoundTripWithNonUnitQuaternion)
{
  const Pose3d frame{0.4, -0.2, 0.8, 0.0, 0.0, 1.4142135623730951, 1.4142135623730951};
  const Pose3d object{-0.1, 0.3, 1.2, 0.0, 1.0, 0.0, 1.0};
  const auto relative = relativePose(frame, object);
  ASSERT_TRUE(relative.has_value());
  const auto composed = composePose(frame, *relative);
  ASSERT_TRUE(composed.has_value());
  EXPECT_NEAR(0.0, positionDistance(object, *composed), 1.0e-12);
  EXPECT_NEAR(0.0, orientationDistance(object, *composed), 1.0e-12);
}

TEST(PoseGeometry, InvalidQuaternionCannotBeComposed)
{
  Pose3d invalid = kIdentity;
  invalid.qw = 0.0;
  EXPECT_FALSE(relativePose(invalid, kIdentity).has_value());
  EXPECT_FALSE(composePose(kIdentity, invalid).has_value());
  EXPECT_TRUE(std::isinf(orientationDistance(invalid, kIdentity)));
}

}  // namespace
}  // namespace pick_place_common
