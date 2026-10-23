// AGPL-3.0-only; see third_party/quik/LICENSE.
#include <gtest/gtest.h>
#include <so101_quik/c_api.h>

#include <array>
#include <cmath>
#include <memory>

namespace {
const std::array<double, 20> dh = {
  0.1, 0, 0, 0, 0.2, 0, 0, 0, 0.1, 0, 0, 0, 0.1, 0, 0, 0, 0.1, 0, 0, 0};
const std::array<double, 16> identity = {
  1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1};
using Context = std::unique_ptr<void, decltype(&quik_destroy)>;
}

TEST(QuikCAbi, RowMajorFk)
{
  Context context(quik_create(dh.data(), identity.data(), identity.data(), 0), quik_destroy);
  ASSERT_NE(context.get(), nullptr);
  const std::array<double, 5> q = {0, 0, 0, 0, 1.5707963267948966};
  const std::array<double, 16> expected = {
    0, -1, 0, 0.5, 1, 0, 0, 0.1, 0, 0, 1, 0, 0, 0, 0, 1};
  std::array<double, 16> actual{};
  ASSERT_EQ(quik_fk(context.get(), q.data(), actual.data()), 0);
  for (std::size_t index = 0; index < actual.size(); ++index) {
    EXPECT_NEAR(actual[index], expected[index], 1e-12);
  }
}

TEST(QuikCAbi, SolveNonzeroPose)
{
  Context context(quik_create(dh.data(), identity.data(), identity.data(), 0), quik_destroy);
  ASSERT_NE(context.get(), nullptr);
  const std::array<double, 16> target = {
    0.8660254037844386, -0.5, 0, 0.5196152422706632,
    0.5, 0.8660254037844386, 0, 0.3, 0, 0, 1, 0, 0, 0, 0, 1};
  std::array<double, 5> seed{}, output{};
  std::array<double, 6> error{};
  int iterations = 0, reason = 0;
  ASSERT_EQ(quik_solve(context.get(), target.data(), seed.data(), output.data(), error.data(),
    &iterations, &reason), 0);
  for (double value : output) {
    ASSERT_TRUE(std::isfinite(value));
  }
  std::array<double, 16> actual{};
  ASSERT_EQ(quik_fk(context.get(), output.data(), actual.data()), 0);
  for (std::size_t index = 0; index < actual.size(); ++index) {
    EXPECT_NEAR(actual[index], target[index], 1e-8);
  }
}
