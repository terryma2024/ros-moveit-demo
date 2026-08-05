#pragma once

#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

#include "so101_gazebo_demo/workspace/workspace_artifact_writer.hpp"

namespace so101_gazebo_demo::workspace
{
struct WorkspaceProvenance
{
  std::string urdf_sha256;
  std::string srdf_sha256;
  std::string scene_sha256;
  std::string config_sha256;
  std::string executable_sha256;
  std::string package_prefix;
  bool operator==(const WorkspaceProvenance & other) const noexcept;
};

struct WorkspaceCheckpoint
{
  std::uint32_t schema_version{1};
  WorkspaceProvenance provenance;
  GeneratorCheckpoint generator;
  PoseCoverageCheckpoint coverage;
  std::vector<CommittedBatch> committed_batches;
  std::uint64_t next_sample_id{0};
  std::uint64_t next_batch_number{1};
  std::uint64_t completed_samples{0};
  StopReason stop_reason{StopReason::INTERRUPTED};
};

struct ResumeDecision
{
  bool allowed;
  std::string code;
  std::string message;
};

std::string sha256(std::string_view value);
std::string configSha256(const WorkspaceSamplingConfig & config);
ResumeDecision validateResume(const WorkspaceProvenance & expected,
                              const WorkspaceProvenance & actual, StopReason stop_reason);

class WorkspaceCheckpointStore
{
public:
  WorkspaceCheckpointStore(std::filesystem::path output_directory,
                           WorkspaceProvenance expected_provenance);
  void writeCheckpointAtomically(const WorkspaceCheckpoint & checkpoint);
  WorkspaceCheckpoint loadCheckpoint() const;
  ResumeDecision validateResume(const WorkspaceCheckpoint & checkpoint) const;
  void prepareResumeDirectory(const WorkspaceCheckpoint & checkpoint) const;
  const WorkspaceProvenance & expectedProvenance() const noexcept;

private:
  std::filesystem::path output_directory_;
  WorkspaceProvenance expected_provenance_;
};
}  // namespace so101_gazebo_demo::workspace
