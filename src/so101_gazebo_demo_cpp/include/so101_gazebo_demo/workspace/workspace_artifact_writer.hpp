#pragma once

#include <cstdint>
#include <filesystem>
#include <map>
#include <string>
#include <vector>

#include "so101_gazebo_demo/workspace/pose_coverage_index.hpp"

namespace so101_gazebo_demo::workspace
{
struct CommittedBatch
{
  std::uint64_t batch_number;
  std::uint64_t sample_count;
  std::uint64_t collision_free_count;
  std::filesystem::path csv_path;
  std::filesystem::path all_ply_path;
  std::filesystem::path free_ply_path;
  std::map<std::string, std::string> sha256_by_file;
};

struct FinalArtifacts
{
  WorkspaceArtifactPaths paths;
  std::uint64_t total_vertices;
  std::uint64_t collision_free_vertices;
  std::uint64_t position_voxels;
};

class WorkspaceArtifactWriter
{
public:
  explicit WorkspaceArtifactWriter(std::filesystem::path output_directory,
                                   double position_voxel_size_m = 0.005);
  CommittedBatch writeBatch(std::uint64_t batch_number, const std::vector<PoseSample> & samples);
  FinalArtifacts finalize(const std::vector<CommittedBatch> & batches,
                          const std::vector<PositionVoxelSummary> & voxels);
  const std::filesystem::path & outputDirectory() const noexcept;

private:
  std::filesystem::path output_directory_;
  double position_voxel_size_m_;
};
}  // namespace so101_gazebo_demo::workspace
