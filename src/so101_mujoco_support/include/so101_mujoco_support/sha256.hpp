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

#ifndef SO101_MUJOCO_SUPPORT__SHA256_HPP_
#define SO101_MUJOCO_SUPPORT__SHA256_HPP_

#include <array>
#include <cstdint>
#include <cstring>
#include <vector>

namespace so101_mujoco_support
{
namespace sha256
{

inline uint32_t rotr(uint32_t value, uint32_t bits)
{
  return (value >> bits) | (value << (32 - bits));
}

// Minimal, dependency-free SHA-256 over a byte vector.
inline std::array<uint8_t, 32> digest(const std::vector<uint8_t> & data)
{
  static const uint32_t k[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
  std::vector<uint8_t> message = data;
  const uint64_t bit_length = static_cast<uint64_t>(data.size()) * 8;
  message.push_back(0x80);
  while ((message.size() % 64) != 56) {message.push_back(0);}
  for (int shift = 56; shift >= 0; shift -= 8) {
    message.push_back(static_cast<uint8_t>((bit_length >> shift) & 0xff));
  }
  uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  for (size_t offset = 0; offset < message.size(); offset += 64) {
    uint32_t w[64];
    for (int index = 0; index < 16; ++index) {
      w[index] = (static_cast<uint32_t>(message[offset + index * 4]) << 24) |
        (static_cast<uint32_t>(message[offset + index * 4 + 1]) << 16) |
        (static_cast<uint32_t>(message[offset + index * 4 + 2]) << 8) |
        static_cast<uint32_t>(message[offset + index * 4 + 3]);
    }
    for (int index = 16; index < 64; ++index) {
      const uint32_t s0 = rotr(w[index - 15], 7) ^ rotr(w[index - 15], 18) ^ (w[index - 15] >> 3);
      const uint32_t s1 = rotr(w[index - 2], 17) ^ rotr(w[index - 2], 19) ^ (w[index - 2] >> 10);
      w[index] = w[index - 16] + s0 + w[index - 7] + s1;
    }
    uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int index = 0; index < 64; ++index) {
      const uint32_t s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const uint32_t ch = (e & f) ^ ((~e) & g);
      const uint32_t temp1 = hh + s1 + ch + k[index] + w[index];
      const uint32_t s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
      const uint32_t temp2 = s0 + maj;
      hh = g; g = f; f = e; e = d + temp1; d = c; c = b; b = a; a = temp1 + temp2;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d;
    h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
  }
  std::array<uint8_t, 32> out{};
  for (int index = 0; index < 8; ++index) {
    out[index * 4] = static_cast<uint8_t>((h[index] >> 24) & 0xff);
    out[index * 4 + 1] = static_cast<uint8_t>((h[index] >> 16) & 0xff);
    out[index * 4 + 2] = static_cast<uint8_t>((h[index] >> 8) & 0xff);
    out[index * 4 + 3] = static_cast<uint8_t>(h[index] & 0xff);
  }
  return out;
}

}  // namespace sha256
}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__SHA256_HPP_
