// Copyright 2026 zjumty
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Gate 6 Batch 3 — known-answer tests for the hand-written SHA-256.
// A self-written hash is not trusted without published vectors.

#include <gtest/gtest.h>

#include <cstdint>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

#include "so101_mujoco_support/sha256.hpp"

namespace
{

std::string to_hex(const std::array<uint8_t, 32> & value)
{
  static const char * digits = "0123456789abcdef";
  std::string out;
  for (const auto byte : value) {
    out.push_back(digits[(byte >> 4) & 0xf]);
    out.push_back(digits[byte & 0xf]);
  }
  return out;
}

std::string fixture_path(const char * name)
{
  const std::string file(__FILE__);
  return file.substr(0, file.find_last_of('/')) + "/fixtures/" + name;
}

}  // namespace

TEST(Gate6Sha256Vectors, PublishedKnownAnswers)
{
  using so101_mujoco_support::sha256::digest;
  EXPECT_EQ(to_hex(digest({})),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  const std::vector<uint8_t> abc{'a', 'b', 'c'};
  EXPECT_EQ(to_hex(digest(abc)),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  const std::string long_input(1000000, 'a');
  const std::vector<uint8_t> million(long_input.begin(), long_input.end());
  EXPECT_EQ(to_hex(digest(million)),
            "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
}

TEST(Gate6Sha256Vectors, GoldenGoalCdrMatchesTheFrozenDigest)
{
  // The fixture's own goal CDR must hash to the digest frozen in the manifest,
  // which is also what the parser compares against the frame's target_digest.
  std::ifstream input(fixture_path("bound_frame_v2.bin"), std::ios::binary);
  const std::vector<uint8_t> frame{std::istreambuf_iterator<char>(input),
    std::istreambuf_iterator<char>()};
  ASSERT_EQ(frame.size(), 484u);
  const size_t goal_len = 308;                       // manifest goal_cdr_len
  const std::vector<uint8_t> goal_cdr(frame.end() - static_cast<long>(goal_len), frame.end());
  EXPECT_EQ(to_hex(so101_mujoco_support::sha256::digest(goal_cdr)),
            "709350546e50e2bdac2b6fda67aba06212a8b8a115442aa711f90b4ec0ea0902");
}
