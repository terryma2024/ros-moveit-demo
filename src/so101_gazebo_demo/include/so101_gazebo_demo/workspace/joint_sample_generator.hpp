#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <map>
#include <utility>
#include <vector>

#include "so101_gazebo_demo/workspace/workspace_types.hpp"

namespace so101_gazebo_demo::workspace
{
using JointBounds = std::array<std::pair<double, double>, 5>;

struct GeneratorCheckpoint
{
  std::uint64_t next_global_index{1};
  std::uint64_t next_local_index{1};
  std::map<std::uint64_t, std::uint32_t> refinement_scale_levels;
};

struct RefinementSeed
{
  std::uint64_t sample_id;
  std::uint8_t priority;
  PositionVoxelKey voxel;
  std::array<double, 5> arm_joints;
  std::uint32_t scale_level;
};

class JointSampleGenerator
{
public:
  explicit JointSampleGenerator(JointBounds bounds);
  std::vector<GeneratedJointSample> explicitSamples(const std::array<double, 5> & home) const;
  std::vector<GeneratedJointSample> nextGlobal(std::size_t count);
  std::vector<GeneratedJointSample> nextRefined(const std::vector<RefinementSeed> & seeds,
                                                std::size_t count);
  GeneratorCheckpoint checkpoint() const;
  void restore(const GeneratorCheckpoint & checkpoint);

private:
  JointBounds bounds_;
  GeneratorCheckpoint checkpoint_;
};
}  // namespace so101_gazebo_demo::workspace
