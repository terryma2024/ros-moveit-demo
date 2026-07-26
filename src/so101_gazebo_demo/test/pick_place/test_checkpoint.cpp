#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/checkpoint.hpp"
#include "so101_gazebo_demo/pick_place/common_resume_validator.hpp"
#include "so101_gazebo_demo/pick_place/file_checkpoint_store.hpp"
#include "so101_gazebo_demo/pick_place/simulation_session_id.hpp"

#include <filesystem>

namespace pick_place = so101_gazebo_demo::pick_place;

TEST(CheckpointV3, RequiresSchemaV3AndResumeSession)
{
  pick_place::Checkpoint checkpoint;
  EXPECT_EQ(3U, checkpoint.schema_version);
  const auto resume = pick_place::resolveSimulationSessionId(pick_place::RunMode::EXECUTE, true,
                                                               "", 1);
  EXPECT_FALSE(resume.value);
  EXPECT_FALSE(resume.error.empty());
}

TEST(CheckpointV3, FileStoreRoundTripsAndResumeValidatorBindsConfigurationAndSession)
{
  const auto path = std::filesystem::temp_directory_path() / "so101_checkpoint_v3_test";
  std::filesystem::remove(path);
  pick_place::FileCheckpointStore store(path);
  pick_place::Checkpoint checkpoint;
  checkpoint.run_id = "dry-run-boundary";
  checkpoint.sequence = 7;
  checkpoint.next_state = pick_place::State::ATTACH_MOVEIT;
  checkpoint.configuration_hash = "config-a";
  checkpoint.simulation_session_id = "session-a";
  EXPECT_FALSE(store.commit(checkpoint));

  const auto loaded = store.loadLatestCompatible();
  ASSERT_TRUE(loaded.checkpoint);
  EXPECT_EQ(3U, loaded.checkpoint->schema_version);
  EXPECT_EQ(pick_place::State::ATTACH_MOVEIT, loaded.checkpoint->next_state);
  pick_place::WorldSnapshot observed;
  observed.fresh = true;
  observed.arm_stationary = true;
  observed.simulation_session_id = "session-a";
  const pick_place::CommonResumeValidator matching("config-a", "session-a");
  EXPECT_TRUE(matching.validate(*loaded.checkpoint, observed).ok);
  const pick_place::CommonResumeValidator stale("config-b", "session-a");
  ASSERT_FALSE(stale.validate(*loaded.checkpoint, observed).ok);
  EXPECT_EQ("RESUME_CONFIGURATION_MISMATCH",
            stale.validate(*loaded.checkpoint, observed).failures.front().code);
  std::filesystem::remove(path);
}
