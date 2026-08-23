#include "so101_gazebo_demo/workspace/workspace_checkpoint_store.hpp"

#include <array>
#include <fcntl.h>
#include <fstream>
#include <iomanip>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <system_error>
#include <unistd.h>

#include <nlohmann/json.hpp>
#include <openssl/evp.h>

namespace so101_gazebo_demo::workspace
{
namespace
{
using Json = nlohmann::ordered_json;

StopReason stopReasonFromString(const std::string & value)
{
  if (value == "converged_at_configured_resolution")
    return StopReason::CONVERGED_AT_CONFIGURED_RESOLUTION;
  if (value == "sample_cap_reached")
    return StopReason::SAMPLE_CAP_REACHED;
  if (value == "budget_exhausted")
    return StopReason::BUDGET_EXHAUSTED;
  if (value == "interrupted")
    return StopReason::INTERRUPTED;
  if (value == "failed")
    return StopReason::FAILED;
  throw std::runtime_error("unknown checkpoint stop reason");
}

Json provenanceJson(const WorkspaceProvenance & value)
{
  return {{"urdf_sha256", value.urdf_sha256},
          {"srdf_sha256", value.srdf_sha256},
          {"scene_sha256", value.scene_sha256},
          {"config_sha256", value.config_sha256},
          {"executable_sha256", value.executable_sha256},
          {"package_prefix", value.package_prefix}};
}

WorkspaceProvenance parseProvenance(const Json & value)
{
  return {value.at("urdf_sha256"),   value.at("srdf_sha256"),       value.at("scene_sha256"),
          value.at("config_sha256"), value.at("executable_sha256"), value.at("package_prefix")};
}

Json seedJson(const RefinementSeed & seed)
{
  return {{"sample_id", seed.sample_id},
          {"priority", seed.priority},
          {"voxel", {seed.voxel.x, seed.voxel.y, seed.voxel.z}},
          {"arm_joints", seed.arm_joints},
          {"scale_level", seed.scale_level}};
}

RefinementSeed parseSeed(const Json & value)
{
  const auto & voxel = value.at("voxel");
  return {value.at("sample_id"),
          value.at("priority"),
          {voxel.at(0), voxel.at(1), voxel.at(2)},
          value.at("arm_joints").get<std::array<double, 5>>(),
          value.at("scale_level")};
}

Json checkpointJson(const WorkspaceCheckpoint & checkpoint)
{
  Json coverage = Json::array();
  for (const auto & voxel : checkpoint.coverage.voxels) {
    Json clusters = Json::array();
    for (const auto & cluster : voxel.clusters) {
      clusters.push_back({{"cluster_id", cluster.cluster_id},
                          {"representative_xyzw", cluster.representative_xyzw},
                          {"has_collision_free_sample", cluster.has_collision_free_sample}});
    }
    Json seeds = Json::array();
    for (const auto & seed : voxel.seed_candidates)
      seeds.push_back(seedJson(seed));
    coverage.push_back(
      {{"key", {voxel.summary.key.x, voxel.summary.key.y, voxel.summary.key.z}},
       {"sample_count", voxel.summary.sample_count},
       {"collision_free_count", voxel.summary.collision_free_count},
       {"orientation_count", voxel.summary.orientation_count},
       {"collision_free_orientation_count", voxel.summary.collision_free_orientation_count},
       {"clusters", clusters},
       {"seed_candidates", seeds}});
  }
  Json batches = Json::array();
  for (const auto & batch : checkpoint.committed_batches) {
    batches.push_back({{"batch_number", batch.batch_number},
                       {"sample_count", batch.sample_count},
                       {"collision_free_count", batch.collision_free_count},
                       {"csv_path", batch.csv_path.string()},
                       {"all_ply_path", batch.all_ply_path.string()},
                       {"free_ply_path", batch.free_ply_path.string()},
                       {"sha256_by_file", batch.sha256_by_file}});
  }
  return {{"schema_version", checkpoint.schema_version},
          {"provenance", provenanceJson(checkpoint.provenance)},
          {"generator",
           {{"next_global_index", checkpoint.generator.next_global_index},
            {"next_local_index", checkpoint.generator.next_local_index},
            {"refinement_scale_levels", checkpoint.generator.refinement_scale_levels}}},
          {"coverage", coverage},
          {"consecutive_stable_batches", checkpoint.coverage.consecutive_stable_batches},
          {"committed_batches", batches},
          {"next_sample_id", checkpoint.next_sample_id},
          {"next_batch_number", checkpoint.next_batch_number},
          {"completed_samples", checkpoint.completed_samples},
          {"stop_reason", toString(checkpoint.stop_reason)}};
}

WorkspaceCheckpoint parseCheckpoint(const Json & value)
{
  WorkspaceCheckpoint checkpoint;
  checkpoint.schema_version = value.at("schema_version");
  if (checkpoint.schema_version != 1)
    throw std::runtime_error("unsupported checkpoint schema");
  checkpoint.provenance = parseProvenance(value.at("provenance"));
  const auto & generator = value.at("generator");
  checkpoint.generator.next_global_index = generator.at("next_global_index");
  checkpoint.generator.next_local_index = generator.at("next_local_index");
  checkpoint.generator.refinement_scale_levels =
    generator.at("refinement_scale_levels").get<std::map<std::uint64_t, std::uint32_t>>();
  checkpoint.coverage.consecutive_stable_batches = value.at("consecutive_stable_batches");
  for (const auto & stored : value.at("coverage")) {
    const auto & key = stored.at("key");
    PositionVoxelSnapshot voxel;
    voxel.summary = {{key.at(0), key.at(1), key.at(2)},
                     stored.at("sample_count"),
                     stored.at("collision_free_count"),
                     stored.at("orientation_count"),
                     stored.at("collision_free_orientation_count")};
    for (const auto & cluster : stored.at("clusters")) {
      voxel.clusters.push_back({cluster.at("cluster_id"),
                                cluster.at("representative_xyzw").get<std::array<double, 4>>(),
                                cluster.at("has_collision_free_sample")});
    }
    for (const auto & seed : stored.at("seed_candidates"))
      voxel.seed_candidates.push_back(parseSeed(seed));
    checkpoint.coverage.voxels.push_back(std::move(voxel));
  }
  for (const auto & stored : value.at("committed_batches")) {
    checkpoint.committed_batches.push_back(
      {stored.at("batch_number"), stored.at("sample_count"), stored.at("collision_free_count"),
       stored.at("csv_path").get<std::string>(), stored.at("all_ply_path").get<std::string>(),
       stored.at("free_ply_path").get<std::string>(),
       stored.at("sha256_by_file").get<std::map<std::string, std::string>>()});
  }
  checkpoint.next_sample_id = value.at("next_sample_id");
  checkpoint.next_batch_number = value.at("next_batch_number");
  checkpoint.completed_samples = value.at("completed_samples");
  checkpoint.stop_reason = stopReasonFromString(value.at("stop_reason"));
  return checkpoint;
}

void fsyncFile(const std::filesystem::path & path)
{
  const int descriptor = ::open(path.c_str(), O_RDONLY);
  if (descriptor < 0)
    throw std::system_error(errno, std::generic_category(), "open checkpoint");
  if (::fsync(descriptor) != 0) {
    const int error = errno;
    ::close(descriptor);
    throw std::system_error(error, std::generic_category(), "fsync checkpoint");
  }
  ::close(descriptor);
}
}  // namespace

bool WorkspaceProvenance::operator==(const WorkspaceProvenance & other) const noexcept
{
  return urdf_sha256 == other.urdf_sha256 && srdf_sha256 == other.srdf_sha256 &&
         scene_sha256 == other.scene_sha256 && config_sha256 == other.config_sha256 &&
         executable_sha256 == other.executable_sha256 && package_prefix == other.package_prefix;
}

std::string sha256(std::string_view value)
{
  std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> context(EVP_MD_CTX_new(),
                                                                  EVP_MD_CTX_free);
  if (!context || EVP_DigestInit_ex(context.get(), EVP_sha256(), nullptr) != 1 ||
      EVP_DigestUpdate(context.get(), value.data(), value.size()) != 1) {
    throw std::runtime_error("SHA-256 initialization failed");
  }
  std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
  unsigned int length = 0;
  if (EVP_DigestFinal_ex(context.get(), digest.data(), &length) != 1) {
    throw std::runtime_error("SHA-256 finalization failed");
  }
  std::ostringstream output;
  for (unsigned int index = 0; index < length; ++index) {
    output << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(digest[index]);
  }
  return output.str();
}

std::string configSha256(const WorkspaceSamplingConfig & config)
{
  const Json value{{"batch_size", config.batch_size},
                   {"maximum_samples", config.maximum_samples},
                   {"minimum_samples", config.minimum_samples},
                   {"orientation_new_rate_threshold", config.orientation_new_rate_threshold},
                   {"orientation_threshold_rad", config.orientation_threshold_rad},
                   {"position_new_rate_threshold", config.position_new_rate_threshold},
                   {"position_voxel_size_m", config.position_voxel_size_m},
                   {"stable_batches", config.stable_batches},
                   {"time_budget_seconds", config.time_budget.count()}};
  return sha256(value.dump());
}

ResumeDecision validateResume(const WorkspaceProvenance & expected,
                              const WorkspaceProvenance & actual, StopReason stop_reason)
{
  if (!(expected == actual))
    return {false, "checkpoint_mismatch", "checkpoint provenance differs"};
  if (stop_reason == StopReason::INTERRUPTED || stop_reason == StopReason::BUDGET_EXHAUSTED) {
    return {true, "ok", "checkpoint may resume"};
  }
  return {false, "checkpoint_terminal", "checkpoint stop reason is terminal"};
}

WorkspaceCheckpointStore::WorkspaceCheckpointStore(std::filesystem::path output_directory,
                                                   WorkspaceProvenance expected_provenance) :
    output_directory_(std::move(output_directory)),
    expected_provenance_(std::move(expected_provenance))
{
  std::filesystem::create_directories(output_directory_);
}

void WorkspaceCheckpointStore::writeCheckpointAtomically(const WorkspaceCheckpoint & checkpoint)
{
  const auto partial = output_directory_ / "checkpoint.json.partial";
  const auto final = output_directory_ / "checkpoint.json";
  std::ofstream stream(partial, std::ios::binary | std::ios::trunc);
  stream << checkpointJson(checkpoint).dump(2) << '\n';
  stream.flush();
  if (!stream)
    throw std::runtime_error("checkpoint write failed");
  stream.close();
  fsyncFile(partial);
  std::filesystem::rename(partial, final);
}

WorkspaceCheckpoint WorkspaceCheckpointStore::loadCheckpoint() const
{
  std::ifstream stream(output_directory_ / "checkpoint.json", std::ios::binary);
  if (!stream)
    throw std::runtime_error("checkpoint.json is missing");
  Json value;
  stream >> value;
  return parseCheckpoint(value);
}

ResumeDecision
WorkspaceCheckpointStore::validateResume(const WorkspaceCheckpoint & checkpoint) const
{
  return workspace::validateResume(expected_provenance_, checkpoint.provenance,
                                   checkpoint.stop_reason);
}

void WorkspaceCheckpointStore::prepareResumeDirectory(const WorkspaceCheckpoint & checkpoint) const
{
  const auto orphaned = output_directory_ / "orphaned";
  std::filesystem::create_directories(orphaned);
  for (const auto & entry : std::filesystem::recursive_directory_iterator(output_directory_)) {
    if (!entry.is_regular_file() || entry.path().extension() != ".partial" ||
        entry.path().parent_path() == orphaned)
      continue;
    std::filesystem::rename(entry.path(), orphaned / entry.path().filename());
  }
  if (checkpoint.stop_reason == StopReason::BUDGET_EXHAUSTED) {
    const auto snapshot =
      output_directory_ / "snapshots" / std::to_string(checkpoint.completed_samples);
    std::filesystem::create_directories(snapshot);
    for (const auto & name :
         {"manifest.json", "summary.json", "samples.csv", "all_poses.ply",
          "collision_free_poses.ply", "position_voxels.ply", "collision_pairs.csv"}) {
      const auto source = output_directory_ / name;
      if (std::filesystem::exists(source))
        std::filesystem::rename(source, snapshot / name);
    }
  }
}

const WorkspaceProvenance & WorkspaceCheckpointStore::expectedProvenance() const noexcept
{
  return expected_provenance_;
}
}  // namespace so101_gazebo_demo::workspace
