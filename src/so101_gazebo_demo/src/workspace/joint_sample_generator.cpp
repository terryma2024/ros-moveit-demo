#include "so101_gazebo_demo/workspace/joint_sample_generator.hpp"

#include <algorithm>
#include <cmath>
#include <set>
#include <stdexcept>
#include <tuple>

namespace so101_gazebo_demo::workspace
{
namespace
{
constexpr std::array<unsigned, 5> kGlobalBases{2, 3, 5, 7, 11};
constexpr std::array<unsigned, 5> kLocalBases{13, 17, 19, 23, 29};

double halton(std::uint64_t index, unsigned base)
{
  double result = 0.0;
  double factor = 1.0;
  while (index > 0) {
    factor /= static_cast<double>(base);
    result += factor * static_cast<double>(index % base);
    index /= base;
  }
  return result;
}

double reflectIntoBounds(double value, double lower, double upper)
{
  const double width = upper - lower;
  const double period = 2.0 * width;
  double offset = std::fmod(value - lower, period);
  if (offset < 0.0)
    offset += period;
  return offset <= width ? lower + offset : upper - (offset - width);
}

using QuantizedJointKey = std::array<std::int64_t, 5>;
QuantizedJointKey quantized(const std::array<double, 5> & joints)
{
  QuantizedJointKey key{};
  std::transform(joints.begin(), joints.end(), key.begin(), [](double value) {
    return static_cast<std::int64_t>(std::llround(value * 1.0e12));
  });
  return key;
}
}  // namespace

JointSampleGenerator::JointSampleGenerator(JointBounds bounds) : bounds_(std::move(bounds))
{
  for (const auto & [lower, upper] : bounds_) {
    if (!std::isfinite(lower) || !std::isfinite(upper) || lower >= upper) {
      throw std::invalid_argument("joint bounds must be finite and increasing");
    }
  }
}

std::vector<GeneratedJointSample>
JointSampleGenerator::explicitSamples(const std::array<double, 5> & home) const
{
  std::vector<GeneratedJointSample> output;
  std::set<QuantizedJointKey> seen;
  std::array<double, 5> midpoint{};
  for (std::size_t joint = 0; joint < bounds_.size(); ++joint) {
    midpoint[joint] = (bounds_[joint].first + bounds_[joint].second) * 0.5;
  }
  const auto append = [&](const std::array<double, 5> & joints) {
    if (seen.insert(quantized(joints)).second) {
      output.push_back(
        {static_cast<std::uint64_t>(output.size()), SampleSource::EXPLICIT_BOUNDARY, joints});
    }
  };
  append(home);
  append(midpoint);
  for (std::size_t joint = 0; joint < bounds_.size(); ++joint) {
    auto lower = midpoint;
    auto upper = midpoint;
    lower[joint] = bounds_[joint].first;
    upper[joint] = bounds_[joint].second;
    append(lower);
    append(upper);
  }
  return output;
}

std::vector<GeneratedJointSample> JointSampleGenerator::nextGlobal(std::size_t count)
{
  std::vector<GeneratedJointSample> output;
  output.reserve(count);
  for (std::size_t sample = 0; sample < count; ++sample) {
    const auto index = checkpoint_.next_global_index++;
    std::array<double, 5> joints{};
    for (std::size_t joint = 0; joint < joints.size(); ++joint) {
      const auto [lower, upper] = bounds_[joint];
      joints[joint] = lower + halton(index, kGlobalBases[joint]) * (upper - lower);
    }
    output.push_back({index, SampleSource::HALTON_GLOBAL, joints});
  }
  return output;
}

std::vector<GeneratedJointSample>
JointSampleGenerator::nextRefined(const std::vector<RefinementSeed> & seeds, std::size_t count)
{
  if (seeds.empty())
    return {};
  auto ordered = seeds;
  std::sort(ordered.begin(), ordered.end(), [](const auto & lhs, const auto & rhs) {
    return std::tie(lhs.priority, lhs.voxel, lhs.sample_id) <
           std::tie(rhs.priority, rhs.voxel, rhs.sample_id);
  });
  std::vector<GeneratedJointSample> output;
  output.reserve(count);
  for (std::size_t sample = 0; sample < count; ++sample) {
    const auto & seed = ordered[sample % ordered.size()];
    const auto local_index = checkpoint_.next_local_index++;
    auto & stored_level = checkpoint_.refinement_scale_levels[seed.sample_id];
    stored_level = std::max(stored_level, seed.scale_level);
    const double scale = std::max(0.00125, 0.02 / std::pow(2.0, stored_level));
    auto joints = seed.arm_joints;
    for (std::size_t joint = 0; joint < joints.size(); ++joint) {
      const auto [lower, upper] = bounds_[joint];
      const double signed_halton = 2.0 * halton(local_index, kLocalBases[joint]) - 1.0;
      joints[joint] =
        reflectIntoBounds(joints[joint] + signed_halton * scale * (upper - lower), lower, upper);
    }
    ++stored_level;
    output.push_back({local_index, SampleSource::LOCAL_REFINEMENT, joints});
  }
  return output;
}

GeneratorCheckpoint JointSampleGenerator::checkpoint() const
{
  return checkpoint_;
}
void JointSampleGenerator::restore(const GeneratorCheckpoint & checkpoint)
{
  checkpoint_ = checkpoint;
}
}  // namespace so101_gazebo_demo::workspace
