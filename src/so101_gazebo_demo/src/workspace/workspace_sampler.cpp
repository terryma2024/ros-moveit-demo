#include "so101_gazebo_demo/workspace/workspace_sampler.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <utility>

#include <nlohmann/json.hpp>

namespace so101_gazebo_demo::workspace
{
namespace
{
using Json = nlohmann::ordered_json;

std::uint64_t freeSamples(const std::vector<CommittedBatch> & batches)
{
  std::uint64_t result = 0;
  for (const auto & batch : batches)
    result += batch.collision_free_count;
  return result;
}

void writeJson(const std::filesystem::path & path, const Json & value)
{
  const auto partial = std::filesystem::path(path.string() + ".partial");
  std::ofstream stream(partial, std::ios::binary | std::ios::trunc);
  stream << value.dump(2) << '\n';
  stream.flush();
  if (!stream)
    throw std::runtime_error("failed writing " + path.string());
  stream.close();
  std::filesystem::rename(partial, path);
}
}  // namespace

WorkspaceSampler::WorkspaceSampler(WorkspaceSamplingConfig config, JointSampleGenerator generator,
                                   WorkspaceStateEvaluator & evaluator, PoseCoverageIndex coverage,
                                   WorkspaceArtifactWriter & writer,
                                   WorkspaceCheckpointStore & checkpoint_store) :
    config_(config), generator_(std::move(generator)), evaluator_(evaluator),
    coverage_(std::move(coverage)), writer_(writer), checkpoint_store_(checkpoint_store)
{
}

RunSummary WorkspaceSampler::run(const RunControl & control)
{
  RunSummary summary{false,        StopReason::FAILED,        0,           0,
                     std::nullopt, writer_.outputDirectory(), std::nullopt};
  if (const auto validation = validateConfig(config_)) {
    summary.failure = WorkspaceFailure{"invalid_config", *validation};
    return summary;
  }
  WorkspaceCheckpoint checkpoint;
  checkpoint.provenance = checkpoint_store_.expectedProvenance();
  ConvergenceTracker convergence(config_);
  std::vector<Json> convergence_history;
  try {
    if (std::filesystem::exists(writer_.outputDirectory() / "checkpoint.json")) {
      checkpoint = checkpoint_store_.loadCheckpoint();
      const auto decision = checkpoint_store_.validateResume(checkpoint);
      if (!decision.allowed) {
        summary.failure = WorkspaceFailure{decision.code, decision.message};
        return summary;
      }
      checkpoint_store_.prepareResumeDirectory(checkpoint);
      generator_.restore(checkpoint.generator);
      coverage_.restore(checkpoint.coverage);
      convergence.restore(checkpoint.coverage.consecutive_stable_batches);
      summary.completed_samples = checkpoint.completed_samples;
    }
    const auto started = control.now();
    while (checkpoint.completed_samples < config_.maximum_samples) {
      if (control.stop_requested()) {
        checkpoint.stop_reason = StopReason::INTERRUPTED;
        checkpoint.generator = generator_.checkpoint();
        checkpoint.coverage = coverage_.checkpoint();
        checkpoint.coverage.consecutive_stable_batches = convergence.consecutiveStableBatches();
        checkpoint_store_.writeCheckpointAtomically(checkpoint);
        summary.stop_reason = StopReason::INTERRUPTED;
        summary.completed_samples = checkpoint.completed_samples;
        summary.collision_free_samples = freeSamples(checkpoint.committed_batches);
        summary.failure = WorkspaceFailure{"interrupted", "sampling stopped at a batch boundary"};
        return summary;
      }
      const auto remaining = config_.maximum_samples - checkpoint.completed_samples;
      const auto count =
        static_cast<std::size_t>(std::min<std::uint64_t>(config_.batch_size, remaining));
      std::vector<GeneratedJointSample> generated;
      if (checkpoint.completed_samples == 0) {
        generated = generator_.explicitSamples({0.0, 0.0, 0.0, 0.0, 0.0});
        if (generated.size() > count)
          generated.resize(count);
        const auto global = generator_.nextGlobal(count - generated.size());
        generated.insert(generated.end(), global.begin(), global.end());
      } else if (checkpoint.next_batch_number <= 2) {
        generated = generator_.nextGlobal(count);
      } else {
        const auto local_count = count / 5;
        const auto global_count = count - local_count;
        generated = generator_.nextGlobal(global_count);
        const auto local = generator_.nextRefined(coverage_.refinementSeeds(), local_count);
        generated.insert(generated.end(), local.begin(), local.end());
        if (local.size() < local_count) {
          const auto fallback = generator_.nextGlobal(local_count - local.size());
          generated.insert(generated.end(), fallback.begin(), fallback.end());
        }
      }
      std::vector<PoseSample> evaluated;
      evaluated.reserve(generated.size());
      for (const auto & generated_sample : generated) {
        auto sample = evaluator_.evaluate(checkpoint.next_sample_id++, generated_sample);
        coverage_.insert(sample);
        evaluated.push_back(sample);
      }
      const auto delta = coverage_.finishBatch();
      const auto batch_number = checkpoint.next_batch_number++;
      checkpoint.committed_batches.push_back(writer_.writeBatch(batch_number, evaluated));
      checkpoint.completed_samples += evaluated.size();
      checkpoint.generator = generator_.checkpoint();
      const bool converged = convergence.observe(delta, checkpoint.completed_samples);
      checkpoint.coverage = coverage_.checkpoint();
      checkpoint.coverage.consecutive_stable_batches = convergence.consecutiveStableBatches();
      checkpoint.stop_reason = StopReason::INTERRUPTED;
      checkpoint_store_.writeCheckpointAtomically(checkpoint);
      const double position_rate = static_cast<double>(delta.new_position_voxels) /
                                   static_cast<double>(std::max<std::uint64_t>(
                                     1, delta.existing_position_voxels_before_batch));
      const double orientation_rate = static_cast<double>(delta.new_orientation_clusters) /
                                      static_cast<double>(std::max<std::uint64_t>(
                                        1, delta.existing_orientation_clusters_before_batch));
      convergence_history.push_back({{"batch", batch_number},
                                     {"completed_samples", checkpoint.completed_samples},
                                     {"new_position_rate", position_rate},
                                     {"new_orientation_rate", orientation_rate}});

      std::optional<StopReason> stop;
      if (converged)
        stop = StopReason::CONVERGED_AT_CONFIGURED_RESOLUTION;
      else if (checkpoint.completed_samples >= config_.maximum_samples)
        stop = StopReason::SAMPLE_CAP_REACHED;
      else if (control.now() - started >= config_.time_budget) {
        if (checkpoint.completed_samples < config_.minimum_samples) {
          checkpoint.stop_reason = StopReason::FAILED;
          checkpoint_store_.writeCheckpointAtomically(checkpoint);
          summary.completed_samples = checkpoint.completed_samples;
          summary.collision_free_samples = freeSamples(checkpoint.committed_batches);
          summary.failure = WorkspaceFailure{"minimum_samples_not_reached",
                                             "time budget expired before minimum samples"};
          writeJson(writer_.outputDirectory() / "summary.json",
                    {{"status", "incomplete"},
                     {"failure_code", summary.failure->code},
                     {"completed_samples", summary.completed_samples}});
          return summary;
        }
        stop = StopReason::BUDGET_EXHAUSTED;
      }
      if (stop) {
        checkpoint.stop_reason = *stop;
        checkpoint_store_.writeCheckpointAtomically(checkpoint);
        const auto artifacts =
          writer_.finalize(checkpoint.committed_batches, coverage_.voxelSummaries());
        summary.success = true;
        summary.stop_reason = *stop;
        summary.completed_samples = checkpoint.completed_samples;
        summary.collision_free_samples = artifacts.collision_free_vertices;
        summary.artifacts = artifacts.paths;
        std::ofstream collision_pairs(writer_.outputDirectory() / "collision_pairs.csv");
        collision_pairs << "first,second,count,representative_sample_ids\n";
        for (const auto & [pair, occurrences] : evaluator_.collisionPairCounts()) {
          collision_pairs << pair.first << ',' << pair.second << ',' << occurrences << ',';
          const auto & ids = evaluator_.collisionPairSampleIds().at(pair);
          for (std::size_t index = 0; index < ids.size(); ++index) {
            if (index != 0)
              collision_pairs << ';';
            collision_pairs << ids[index];
          }
          collision_pairs << '\n';
        }
        writeJson(writer_.outputDirectory() / "summary.json",
                  {{"status", "complete"},
                   {"stop_reason", toString(*stop)},
                   {"converged", *stop == StopReason::CONVERGED_AT_CONFIGURED_RESOLUTION},
                   {"completed_samples", summary.completed_samples},
                   {"collision_free_samples", summary.collision_free_samples},
                   {"position_voxels", artifacts.position_voxels},
                   {"convergence_history", convergence_history}});
        const auto & provenance = checkpoint.provenance;
        writeJson(writer_.outputDirectory() / "manifest.json",
                  {{"schema_version", 1},
                   {"completed_samples", summary.completed_samples},
                   {"stop_reason", toString(*stop)},
                   {"scene_objects", Json::array({"base_pedestal", "table"})},
                   {"q6_preopen", evaluator_.gripperPreopen()},
                   {"sampling_dimensions", Json::array({"1", "2", "3", "4", "5"})},
                   {"urdf_sha256", provenance.urdf_sha256},
                   {"srdf_sha256", provenance.srdf_sha256},
                   {"scene_sha256", provenance.scene_sha256},
                   {"config_sha256", provenance.config_sha256},
                   {"executable_sha256", provenance.executable_sha256},
                   {"package_prefix", provenance.package_prefix}});
        return summary;
      }
    }
  } catch (const std::exception & error) {
    checkpoint.stop_reason = StopReason::FAILED;
    try {
      checkpoint_store_.writeCheckpointAtomically(checkpoint);
    } catch (...) {
    }
    summary.completed_samples = checkpoint.completed_samples;
    summary.collision_free_samples = freeSamples(checkpoint.committed_batches);
    summary.failure = WorkspaceFailure{"sampling_failed", error.what()};
    try {
      writeJson(writer_.outputDirectory() / "summary.json",
                {{"status", "incomplete"},
                 {"failure_code", summary.failure->code},
                 {"message", summary.failure->message},
                 {"completed_samples", summary.completed_samples}});
    } catch (...) {
    }
  }
  return summary;
}
}  // namespace so101_gazebo_demo::workspace
