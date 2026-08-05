#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>

#include "so101_gazebo_demo/workspace/workspace_checkpoint_store.hpp"

namespace ws = so101_gazebo_demo::workspace;

namespace
{
ws::WorkspaceProvenance provenance(std::string urdf, std::string srdf, std::string scene,
                                   std::string config)
{
  return {std::move(urdf), std::move(srdf), std::move(scene), std::move(config), "exe", "/prefix"};
}

std::filesystem::path outputDirectory()
{
  const auto path = std::filesystem::temp_directory_path() / "workspace-checkpoint-test";
  std::filesystem::remove_all(path);
  std::filesystem::create_directories(path);
  return path;
}
}  // namespace

TEST(WorkspaceCheckpointStore, Sha256MatchesKnownVector)
{
  EXPECT_EQ(ws::sha256("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
}

TEST(WorkspaceCheckpointStore, RejectsEveryProvenanceMismatch)
{
  const auto expected = provenance("urdf-a", "srdf-a", "scene-a", "config-a");
  for (const auto & actual : {provenance("urdf-b", "srdf-a", "scene-a", "config-a"),
                              provenance("urdf-a", "srdf-b", "scene-a", "config-a"),
                              provenance("urdf-a", "srdf-a", "scene-b", "config-a"),
                              provenance("urdf-a", "srdf-a", "scene-a", "config-b")}) {
    const auto decision = ws::validateResume(expected, actual, ws::StopReason::INTERRUPTED);
    EXPECT_FALSE(decision.allowed);
    EXPECT_EQ(decision.code, "checkpoint_mismatch");
  }
}

TEST(WorkspaceCheckpointStore, BudgetExhaustedMayContinueButConvergedMayNot)
{
  const auto value = provenance("u", "s", "w", "c");
  EXPECT_TRUE(ws::validateResume(value, value, ws::StopReason::BUDGET_EXHAUSTED).allowed);
  EXPECT_FALSE(
    ws::validateResume(value, value, ws::StopReason::CONVERGED_AT_CONFIGURED_RESOLUTION).allowed);
  EXPECT_FALSE(ws::validateResume(value, value, ws::StopReason::SAMPLE_CAP_REACHED).allowed);
  EXPECT_FALSE(ws::validateResume(value, value, ws::StopReason::FAILED).allowed);
}

TEST(WorkspaceCheckpointStore, AtomicCheckpointRoundTripsCoreState)
{
  const auto output = outputDirectory();
  const auto value = provenance("u", "s", "w", "c");
  ws::WorkspaceCheckpointStore store(output, value);
  ws::WorkspaceCheckpoint checkpoint;
  checkpoint.provenance = value;
  checkpoint.generator.next_global_index = 42;
  checkpoint.next_sample_id = 77;
  checkpoint.next_batch_number = 4;
  checkpoint.completed_samples = 76;
  checkpoint.stop_reason = ws::StopReason::INTERRUPTED;
  store.writeCheckpointAtomically(checkpoint);
  const auto loaded = store.loadCheckpoint();
  EXPECT_EQ(loaded.generator.next_global_index, 42U);
  EXPECT_EQ(loaded.next_sample_id, 77U);
  EXPECT_EQ(loaded.completed_samples, 76U);
  EXPECT_FALSE(std::filesystem::exists(output / "checkpoint.json.partial"));
}

TEST(WorkspaceCheckpointStore, ResumeMovesPartialsToOrphaned)
{
  const auto output = outputDirectory();
  std::filesystem::create_directories(output / "chunks");
  std::ofstream(output / "chunks" / "batch.csv.partial") << "partial";
  const auto value = provenance("u", "s", "w", "c");
  ws::WorkspaceCheckpointStore store(output, value);
  ws::WorkspaceCheckpoint checkpoint;
  checkpoint.provenance = value;
  checkpoint.stop_reason = ws::StopReason::INTERRUPTED;
  store.prepareResumeDirectory(checkpoint);
  EXPECT_TRUE(std::filesystem::exists(output / "orphaned" / "batch.csv.partial"));
}
