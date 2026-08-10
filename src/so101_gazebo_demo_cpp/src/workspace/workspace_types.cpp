#include "so101_gazebo_demo/workspace/workspace_types.hpp"

#include <limits>
#include <tuple>

namespace so101_gazebo_demo::workspace
{
bool PositionVoxelKey::operator==(const PositionVoxelKey & other) const noexcept
{
  return std::tie(x, y, z) == std::tie(other.x, other.y, other.z);
}

bool PositionVoxelKey::operator<(const PositionVoxelKey & other) const noexcept
{
  return std::tie(x, y, z) < std::tie(other.x, other.y, other.z);
}

WorkspaceSamplingConfig configForProfile(WorkspaceProfile profile)
{
  WorkspaceSamplingConfig config;
  if (profile == WorkspaceProfile::QUICK) {
    config.time_budget = std::chrono::seconds(300);
    config.batch_size = 10000;
    config.minimum_samples = 10000;
    config.maximum_samples = 100000;
    config.stable_batches = 3;
  }
  return config;
}

std::optional<std::string> validateConfig(const WorkspaceSamplingConfig & config)
{
  if (config.maximum_samples >= (std::uint64_t{1} << 32)) {
    return "maximum_samples must fit PLY uint32 sample_id";
  }
  if (config.batch_size == 0)
    return "batch_size must be positive";
  if (config.minimum_samples > config.maximum_samples) {
    return "minimum_samples must not exceed maximum_samples";
  }
  if (config.time_budget.count() <= 0)
    return "time_budget must be positive";
  if (config.position_voxel_size_m <= 0.0)
    return "position_voxel_size_m must be positive";
  if (config.orientation_threshold_rad <= 0.0)
    return "orientation_threshold_rad must be positive";
  if (config.stable_batches == 0)
    return "stable_batches must be positive";
  return std::nullopt;
}

std::optional<WorkspaceProfile> workspaceProfileFromString(const std::string & value)
{
  if (value == "quick")
    return WorkspaceProfile::QUICK;
  if (value == "full")
    return WorkspaceProfile::FULL;
  if (value == "deep")
    return WorkspaceProfile::DEEP;
  return std::nullopt;
}

std::string toString(WorkspaceProfile profile)
{
  switch (profile) {
    case WorkspaceProfile::QUICK:
      return "quick";
    case WorkspaceProfile::FULL:
      return "full";
    case WorkspaceProfile::DEEP:
      return "deep";
  }
  return "unknown";
}

std::string toString(SampleSource source)
{
  switch (source) {
    case SampleSource::EXPLICIT_BOUNDARY:
      return "explicit_boundary";
    case SampleSource::REGULAR_BASELINE:
      return "regular_baseline";
    case SampleSource::HALTON_GLOBAL:
      return "halton_global";
    case SampleSource::LOCAL_REFINEMENT:
      return "local_refinement";
  }
  return "unknown";
}

std::string toString(StopReason reason)
{
  switch (reason) {
    case StopReason::CONVERGED_AT_CONFIGURED_RESOLUTION:
      return "converged_at_configured_resolution";
    case StopReason::SAMPLE_CAP_REACHED:
      return "sample_cap_reached";
    case StopReason::BUDGET_EXHAUSTED:
      return "budget_exhausted";
    case StopReason::INTERRUPTED:
      return "interrupted";
    case StopReason::FAILED:
      return "failed";
  }
  return "unknown";
}
}  // namespace so101_gazebo_demo::workspace
