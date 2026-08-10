#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <map>
#include <vector>

#include "so101_gazebo_demo/workspace/joint_sample_generator.hpp"

namespace so101_gazebo_demo::workspace
{
struct OrientationAssignment
{
  PositionVoxelKey voxel;
  std::uint32_t cluster_id;
  bool created_position_voxel;
  bool created_orientation_cluster;
};

struct PositionVoxelSummary
{
  PositionVoxelKey key;
  std::uint64_t sample_count;
  std::uint64_t collision_free_count;
  std::uint32_t orientation_count;
  std::uint32_t collision_free_orientation_count;
};

struct OrientationClusterSnapshot
{
  std::uint32_t cluster_id;
  std::array<double, 4> representative_xyzw;
  bool has_collision_free_sample;
};

struct PositionVoxelSnapshot
{
  PositionVoxelSummary summary;
  std::vector<OrientationClusterSnapshot> clusters;
  std::vector<RefinementSeed> seed_candidates;
};

struct PoseCoverageCheckpoint
{
  std::vector<PositionVoxelSnapshot> voxels;
  std::size_t consecutive_stable_batches;
};

class PoseCoverageIndex
{
public:
  PoseCoverageIndex(double position_voxel_size_m, double orientation_threshold_rad);
  PositionVoxelKey keyFor(const std::array<double, 3> & xyz) const;
  OrientationAssignment insert(PoseSample & sample);
  BatchCoverageDelta finishBatch();
  std::vector<PositionVoxelSummary> voxelSummaries() const;
  std::vector<RefinementSeed> refinementSeeds() const;
  PoseCoverageCheckpoint checkpoint() const;
  void restore(const PoseCoverageCheckpoint & checkpoint);

private:
  struct VoxelState
  {
    PositionVoxelSummary summary{};
    std::vector<OrientationClusterSnapshot> clusters;
    std::vector<RefinementSeed> seed_candidates;
    bool has_colliding{false};
  };
  double voxel_size_;
  double orientation_threshold_;
  std::map<PositionVoxelKey, VoxelState> voxels_;
  std::uint64_t positions_at_batch_start_{0};
  std::uint64_t orientations_at_batch_start_{0};
};

class ConvergenceTracker
{
public:
  explicit ConvergenceTracker(WorkspaceSamplingConfig config);
  bool observe(const BatchCoverageDelta & delta, std::uint64_t completed_samples);
  std::size_t consecutiveStableBatches() const noexcept;
  void restore(std::size_t consecutive_stable_batches);

private:
  WorkspaceSamplingConfig config_;
  std::size_t consecutive_stable_batches_{0};
};
}  // namespace so101_gazebo_demo::workspace
