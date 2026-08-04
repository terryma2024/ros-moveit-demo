#pragma once

#include <array>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>

#include "so101_gazebo_demo/pick_place/world_observer.hpp"

namespace so101_gazebo_demo::workspace
{
enum class WorkspaceProfile
{
  QUICK,
  FULL,
  DEEP
};
enum class SampleSource : std::uint8_t
{
  EXPLICIT_BOUNDARY = 0,
  REGULAR_BASELINE = 1,
  HALTON_GLOBAL = 2,
  LOCAL_REFINEMENT = 3
};
enum class StopReason
{
  CONVERGED_AT_CONFIGURED_RESOLUTION,
  SAMPLE_CAP_REACHED,
  BUDGET_EXHAUSTED,
  INTERRUPTED,
  FAILED
};

struct WorkspaceSamplingConfig
{
  std::chrono::seconds time_budget{1800};
  std::size_t batch_size{25000};
  std::uint64_t minimum_samples{250000};
  std::uint64_t maximum_samples{2000000};
  double position_voxel_size_m{0.005};
  double orientation_threshold_rad{0.17453292519943295};
  std::size_t stable_batches{5};
  double position_new_rate_threshold{0.001};
  double orientation_new_rate_threshold{0.002};
};

struct PositionVoxelKey
{
  std::int32_t x;
  std::int32_t y;
  std::int32_t z;
  bool operator==(const PositionVoxelKey & other) const noexcept;
  bool operator<(const PositionVoxelKey & other) const noexcept;
};

struct GeneratedJointSample
{
  std::uint64_t sequence_id;
  SampleSource source;
  std::array<double, 5> arm_joints;
};

struct PoseSample
{
  std::uint64_t sample_id;
  SampleSource source;
  std::array<double, 5> arm_joints;
  double gripper_q6;
  pick_place::Pose3d tcp_pose;
  bool bounds_valid;
  bool self_collision;
  bool scene_collision;
  bool collision_free;
  PositionVoxelKey position_voxel;
  std::uint32_t orientation_cluster_id;
};

struct BatchCoverageDelta
{
  std::uint64_t new_position_voxels;
  std::uint64_t new_orientation_clusters;
  std::uint64_t existing_position_voxels_before_batch;
  std::uint64_t existing_orientation_clusters_before_batch;
};

struct WorkspaceFailure
{
  std::string code;
  std::string message;
};
struct WorkspaceArtifactPaths
{
  std::filesystem::path samples_csv;
  std::filesystem::path all_poses_ply;
  std::filesystem::path collision_free_poses_ply;
  std::filesystem::path position_voxels_ply;
};
struct RunSummary
{
  bool success;
  StopReason stop_reason;
  std::uint64_t completed_samples;
  std::uint64_t collision_free_samples;
  std::optional<WorkspaceFailure> failure;
  std::filesystem::path output_directory;
  std::optional<WorkspaceArtifactPaths> artifacts;
};

WorkspaceSamplingConfig configForProfile(WorkspaceProfile profile);
std::optional<std::string> validateConfig(const WorkspaceSamplingConfig & config);
std::optional<WorkspaceProfile> workspaceProfileFromString(const std::string & value);
std::string toString(WorkspaceProfile profile);
std::string toString(SampleSource source);
std::string toString(StopReason reason);
}  // namespace so101_gazebo_demo::workspace
