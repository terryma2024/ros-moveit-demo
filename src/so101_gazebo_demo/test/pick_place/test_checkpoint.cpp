#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <limits>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "so101_gazebo_demo/pick_place/checkpoint.hpp"
#include "so101_gazebo_demo/pick_place/common_resume_validator.hpp"
#include "so101_gazebo_demo/pick_place/file_checkpoint_store.hpp"
#include "so101_gazebo_demo/pick_place/simulation_session_id.hpp"
#include "so101_gazebo_demo/pick_place/so101_resume_validation_policy.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

namespace
{

using Json = nlohmann::json;

std::filesystem::path checkpointPath(const std::string & name)
{
  const auto path =
    std::filesystem::temp_directory_path() / ("so101_checkpoint_v3_" + name + ".json");
  std::filesystem::remove_all(path);
  std::filesystem::remove(path.string() + ".tmp");
  return path;
}

pick_place::Pose3d makePose(double offset)
{
  return {0.1 + offset, 0.2 + offset, 0.3 + offset, 0.0, 0.0, 0.0, 1.0};
}

pick_place::Checkpoint makeRecoveryCheckpoint()
{
  pick_place::Checkpoint checkpoint;
  checkpoint.schema_version = 4;
  checkpoint.run_id = "run-42";
  checkpoint.sequence = 42;
  checkpoint.source_mode = pick_place::RunMode::EXECUTE;
  checkpoint.phase = pick_place::CheckpointPhase::RECOVERY;
  checkpoint.last_completed_state = pick_place::State::MOVE_ABOVE_PLACE;
  checkpoint.failed_state = pick_place::State::DESCEND_TO_PLACE;
  checkpoint.original_failure = pick_place::Failure{pick_place::FailureCategory::EXECUTION,
                                                    "TRAJECTORY_ABORTED",
                                                    "controller aborted",
                                                    {{"path_error", 0.125}, {"goal_error", 0.25}}};
  checkpoint.next_state = pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT;
  checkpoint.expected.tcp_pose_world = makePose(0.0);
  checkpoint.expected.gripper_open = true;
  checkpoint.expected.joint_positions = {{"joint_a", -0.5}, {"joint_b", 0.75}};
  checkpoint.expected.moveit_world_object_poses = {{"object", makePose(0.1)},
                                                   {"table", makePose(0.2)}};
  checkpoint.expected.moveit_task_object_attached = false;
  checkpoint.expected.gazebo_task_object_pose_world = makePose(0.3);
  checkpoint.expected.gazebo_task_object_attached = true;
  checkpoint.expected.gazebo_task_object_stationary = true;
  checkpoint.expected.gazebo_pose_sequence = 123U;
  checkpoint.expected.observation_timestamp_ns = 1000;
  checkpoint.expected.gazebo_pose_timestamp_ns = 900;
  checkpoint.expected.gazebo_task_object_intended_support_contact = true;
  checkpoint.expected.gazebo_task_object_support_collision_names = {"cup_bottom", "table"};
  checkpoint.expected.gazebo_support_contact_timestamp_ns = 950;
  checkpoint.expected.required_world_objects = {"object", "table"};
  checkpoint.configuration_fingerprint = "configuration-sha256";
  checkpoint.simulation_session_id = "simulation-session";
  checkpoint.resumable = true;
  return checkpoint;
}

pick_place::Checkpoint makeForwardCheckpointWithNullOptionals()
{
  auto checkpoint = makeRecoveryCheckpoint();
  checkpoint.source_mode = pick_place::RunMode::EXECUTE;
  checkpoint.phase = pick_place::CheckpointPhase::FORWARD;
  checkpoint.last_completed_state = pick_place::State::DESCEND;
  checkpoint.failed_state.reset();
  checkpoint.original_failure.reset();
  checkpoint.next_state = pick_place::State::CLOSE_GRIPPER;
  checkpoint.expected.moveit_task_object_attached.reset();
  checkpoint.expected.gazebo_task_object_pose_world.reset();
  checkpoint.expected.gazebo_task_object_attached.reset();
  checkpoint.expected.gazebo_task_object_stationary.reset();
  checkpoint.resumable = true;
  return checkpoint;
}

pick_place::WorldSnapshot snapshotFrom(const pick_place::Checkpoint & checkpoint)
{
  pick_place::WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.arm_stationary = true;
  snapshot.gripper_open = checkpoint.expected.gripper_open;
  snapshot.tcp_pose_world = checkpoint.expected.tcp_pose_world;
  snapshot.joint_positions = checkpoint.expected.joint_positions;
  snapshot.moveit_world_object_poses = checkpoint.expected.moveit_world_object_poses;
  snapshot.moveit_task_object_attached = checkpoint.expected.moveit_task_object_attached;
  snapshot.gazebo_task_object_pose_world = checkpoint.expected.gazebo_task_object_pose_world;
  snapshot.gazebo_task_object_attached = checkpoint.expected.gazebo_task_object_attached;
  snapshot.gazebo_task_object_stationary = checkpoint.expected.gazebo_task_object_stationary;
  snapshot.simulation_session_id = checkpoint.simulation_session_id;
  return snapshot;
}

Json readJson(const std::filesystem::path & path)
{
  std::ifstream input(path);
  Json json;
  input >> json;
  return json;
}

void writeJson(const std::filesystem::path & path, const Json & json)
{
  std::ofstream output(path, std::ios::out | std::ios::trunc);
  output << json.dump(2) << '\n';
}

void expectLoadFailure(const std::filesystem::path & path, const std::string & code)
{
  pick_place::FileCheckpointStore store(path);
  const auto loaded = store.loadLatestCompatible();
  EXPECT_FALSE(loaded.checkpoint);
  ASSERT_TRUE(loaded.failure);
  EXPECT_EQ(code, loaded.failure->code);
}

void expectPoseEqual(const pick_place::Pose3d & lhs, const pick_place::Pose3d & rhs)
{
  EXPECT_DOUBLE_EQ(lhs.x, rhs.x);
  EXPECT_DOUBLE_EQ(lhs.y, rhs.y);
  EXPECT_DOUBLE_EQ(lhs.z, rhs.z);
  EXPECT_DOUBLE_EQ(lhs.qx, rhs.qx);
  EXPECT_DOUBLE_EQ(lhs.qy, rhs.qy);
  EXPECT_DOUBLE_EQ(lhs.qz, rhs.qz);
  EXPECT_DOUBLE_EQ(lhs.qw, rhs.qw);
}

}  // namespace

TEST(CheckpointV4, RequiresSchemaV4AndResumeSession)
{
  pick_place::Checkpoint checkpoint;
  EXPECT_EQ(4U, checkpoint.schema_version);
  const auto resume =
    pick_place::resolveSimulationSessionId(pick_place::RunMode::EXECUTE, true, "", 1);
  EXPECT_FALSE(resume.value);
  EXPECT_FALSE(resume.error.empty());
}

TEST(CheckpointV4, RoundTripPreservesObservationSequencesAndSupportEvidence)
{
  const auto path = checkpointPath("full_round_trip");
  pick_place::FileCheckpointStore store(path);
  const auto checkpoint = makeRecoveryCheckpoint();

  ASSERT_FALSE(store.commit(checkpoint));
  const auto persisted = readJson(path);
  EXPECT_TRUE(persisted.contains("policy_bundle_sha256"));
  EXPECT_FALSE(persisted.contains("configuration_fingerprint"));
  EXPECT_FALSE(persisted.contains("configuration_hash"));
  const auto loaded = store.loadLatestCompatible();

  ASSERT_TRUE(loaded.checkpoint);
  EXPECT_FALSE(loaded.failure);
  EXPECT_EQ(checkpoint.schema_version, loaded.checkpoint->schema_version);
  EXPECT_EQ(checkpoint.run_id, loaded.checkpoint->run_id);
  EXPECT_EQ(checkpoint.sequence, loaded.checkpoint->sequence);
  EXPECT_EQ(checkpoint.source_mode, loaded.checkpoint->source_mode);
  EXPECT_EQ(checkpoint.phase, loaded.checkpoint->phase);
  EXPECT_EQ(checkpoint.last_completed_state, loaded.checkpoint->last_completed_state);
  EXPECT_EQ(checkpoint.failed_state, loaded.checkpoint->failed_state);
  ASSERT_TRUE(loaded.checkpoint->original_failure);
  EXPECT_EQ(checkpoint.original_failure->category, loaded.checkpoint->original_failure->category);
  EXPECT_EQ(checkpoint.original_failure->code, loaded.checkpoint->original_failure->code);
  EXPECT_EQ(checkpoint.original_failure->message, loaded.checkpoint->original_failure->message);
  EXPECT_EQ(checkpoint.original_failure->metrics, loaded.checkpoint->original_failure->metrics);
  EXPECT_EQ(checkpoint.next_state, loaded.checkpoint->next_state);
  expectPoseEqual(checkpoint.expected.tcp_pose_world, loaded.checkpoint->expected.tcp_pose_world);
  EXPECT_EQ(checkpoint.expected.gripper_open, loaded.checkpoint->expected.gripper_open);
  EXPECT_EQ(checkpoint.expected.gazebo_pose_sequence,
            loaded.checkpoint->expected.gazebo_pose_sequence);
  EXPECT_EQ(checkpoint.expected.observation_timestamp_ns,
            loaded.checkpoint->expected.observation_timestamp_ns);
  EXPECT_EQ(checkpoint.expected.gazebo_pose_timestamp_ns,
            loaded.checkpoint->expected.gazebo_pose_timestamp_ns);
  EXPECT_EQ(checkpoint.expected.gazebo_task_object_intended_support_contact,
            loaded.checkpoint->expected.gazebo_task_object_intended_support_contact);
  EXPECT_EQ(checkpoint.expected.gazebo_task_object_support_collision_names,
            loaded.checkpoint->expected.gazebo_task_object_support_collision_names);
  EXPECT_EQ(checkpoint.expected.gazebo_support_contact_timestamp_ns,
            loaded.checkpoint->expected.gazebo_support_contact_timestamp_ns);
  EXPECT_EQ(checkpoint.expected.joint_positions, loaded.checkpoint->expected.joint_positions);
  ASSERT_EQ(checkpoint.expected.moveit_world_object_poses.size(),
            loaded.checkpoint->expected.moveit_world_object_poses.size());
  for (const auto & [name, pose] : checkpoint.expected.moveit_world_object_poses) {
    expectPoseEqual(pose, loaded.checkpoint->expected.moveit_world_object_poses.at(name));
  }
  EXPECT_EQ(checkpoint.expected.moveit_task_object_attached,
            loaded.checkpoint->expected.moveit_task_object_attached);
  ASSERT_TRUE(loaded.checkpoint->expected.gazebo_task_object_pose_world);
  expectPoseEqual(*checkpoint.expected.gazebo_task_object_pose_world,
                  *loaded.checkpoint->expected.gazebo_task_object_pose_world);
  EXPECT_EQ(checkpoint.expected.gazebo_task_object_attached,
            loaded.checkpoint->expected.gazebo_task_object_attached);
  EXPECT_EQ(checkpoint.expected.gazebo_task_object_stationary,
            loaded.checkpoint->expected.gazebo_task_object_stationary);
  EXPECT_EQ(checkpoint.expected.required_world_objects,
            loaded.checkpoint->expected.required_world_objects);
  EXPECT_EQ(checkpoint.configuration_fingerprint, loaded.checkpoint->configuration_fingerprint);
  EXPECT_EQ(checkpoint.simulation_session_id, loaded.checkpoint->simulation_session_id);
  EXPECT_EQ(checkpoint.resumable, loaded.checkpoint->resumable);
  std::filesystem::remove(path);
}

TEST(CheckpointV4, OptionalWorldAndRecoveryEvidenceRoundTripsAsJsonNull)
{
  const auto path = checkpointPath("optional_null");
  pick_place::FileCheckpointStore store(path);
  const auto checkpoint = makeForwardCheckpointWithNullOptionals();

  ASSERT_FALSE(store.commit(checkpoint));
  const auto json = readJson(path);
  EXPECT_TRUE(json.at("failed_state").is_null());
  EXPECT_TRUE(json.at("original_failure").is_null());
  EXPECT_TRUE(json.at("expected").at("moveit_task_object_attached").is_null());
  EXPECT_TRUE(json.at("expected").at("gazebo_task_object_pose_world").is_null());
  EXPECT_TRUE(json.at("expected").at("gazebo_task_object_attached").is_null());
  EXPECT_TRUE(json.at("expected").at("gazebo_task_object_stationary").is_null());

  const auto loaded = store.loadLatestCompatible();
  ASSERT_TRUE(loaded.checkpoint);
  EXPECT_FALSE(loaded.checkpoint->failed_state);
  EXPECT_FALSE(loaded.checkpoint->original_failure);
  EXPECT_FALSE(loaded.checkpoint->expected.moveit_task_object_attached);
  EXPECT_FALSE(loaded.checkpoint->expected.gazebo_task_object_pose_world);
  EXPECT_FALSE(loaded.checkpoint->expected.gazebo_task_object_attached);
  EXPECT_FALSE(loaded.checkpoint->expected.gazebo_task_object_stationary);
  std::filesystem::remove(path);
}

TEST(CheckpointV4, SchemaV4IntentionallyExcludesRuntimeAttachmentMetadata)
{
  const auto path = checkpointPath("attachment_metadata_excluded");
  pick_place::FileCheckpointStore store(path);
  ASSERT_FALSE(store.commit(makeRecoveryCheckpoint()));

  const auto expected = readJson(path).at("expected");
  EXPECT_FALSE(expected.contains("moveit_task_object_attached_link"));
  EXPECT_FALSE(expected.contains("moveit_task_object_touch_links"));
  std::filesystem::remove(path);
}

TEST(CheckpointV4, RejectsPlanOnlyRecoveryCombinationOnCommitAndLoad)
{
  const auto path = checkpointPath("plan_only_recovery");
  pick_place::FileCheckpointStore store(path);
  auto invalid = makeRecoveryCheckpoint();
  invalid.source_mode = pick_place::RunMode::PLAN_ONLY;

  const auto commit_failure = store.commit(invalid);
  ASSERT_TRUE(commit_failure);
  EXPECT_EQ("CHECKPOINT_INVALID_DATA", commit_failure->code);

  ASSERT_FALSE(store.commit(makeRecoveryCheckpoint()));
  auto json = readJson(path);
  json["source_mode"] = "plan_only";
  writeJson(path, json);
  expectLoadFailure(path, "CHECKPOINT_INVALID_DATA");
  std::filesystem::remove(path);
}

TEST(CheckpointV4, RejectsSchemaThreeInsteadOfSilentlyMigrating)
{
  const auto path = checkpointPath("malformed");
  {
    std::ofstream output(path);
    output << R"({"schema_version":3,"run_id":)";
  }
  expectLoadFailure(path, "CHECKPOINT_PARSE_FAILED");

  writeJson(path, Json{{"schema_version", 2}});
  expectLoadFailure(path, "CHECKPOINT_INCOMPATIBLE");
  std::filesystem::remove(path);
}

TEST(CheckpointV4, RejectsMissingUnknownAndWrongTypedRequiredKeys)
{
  const auto path = checkpointPath("required_keys");
  pick_place::FileCheckpointStore store(path);
  ASSERT_FALSE(store.commit(makeRecoveryCheckpoint()));
  const auto valid = readJson(path);

  auto missing = valid;
  missing.erase("run_id");
  writeJson(path, missing);
  expectLoadFailure(path, "CHECKPOINT_PARSE_FAILED");

  auto unknown = valid;
  unknown["unexpected"] = true;
  writeJson(path, unknown);
  expectLoadFailure(path, "CHECKPOINT_PARSE_FAILED");

  auto wrong_type = valid;
  wrong_type["sequence"] = "42";
  writeJson(path, wrong_type);
  expectLoadFailure(path, "CHECKPOINT_PARSE_FAILED");

  auto unknown_expected = valid;
  unknown_expected["expected"]["unexpected"] = 1;
  writeJson(path, unknown_expected);
  expectLoadFailure(path, "CHECKPOINT_PARSE_FAILED");
  std::filesystem::remove(path);
}

TEST(CheckpointV4, RejectsUnknownStateModePhaseAndFailureCategoryNames)
{
  const auto path = checkpointPath("invalid_enums");
  pick_place::FileCheckpointStore store(path);
  ASSERT_FALSE(store.commit(makeRecoveryCheckpoint()));
  const auto valid = readJson(path);

  const std::vector<std::pair<std::string, Json>> mutations{
    {"source_mode", "unsafe_execute"}, {"phase", "PAUSED"},
    {"last_completed_state", "FLY"},   {"next_state", "LAND"},
    {"failed_state", "UNKNOWN_STATE"},
  };
  for (const auto & [key, value] : mutations) {
    auto invalid = valid;
    invalid[key] = value;
    writeJson(path, invalid);
    expectLoadFailure(path, "CHECKPOINT_INVALID_ENUM");
  }

  auto invalid_failure_category = valid;
  invalid_failure_category["original_failure"]["category"] = "NETWORK";
  writeJson(path, invalid_failure_category);
  expectLoadFailure(path, "CHECKPOINT_INVALID_ENUM");
  std::filesystem::remove(path);
}

TEST(CheckpointV4, RejectsWrongOptionalShapesAndNonFiniteNumericEvidence)
{
  const auto path = checkpointPath("optional_and_finite");
  pick_place::FileCheckpointStore store(path);
  auto checkpoint = makeRecoveryCheckpoint();
  ASSERT_FALSE(store.commit(checkpoint));
  const auto valid = readJson(path);

  auto wrong_optional = valid;
  wrong_optional["failed_state"] = Json::object();
  writeJson(path, wrong_optional);
  expectLoadFailure(path, "CHECKPOINT_PARSE_FAILED");

  auto wrong_map_value = valid;
  wrong_map_value["expected"]["joint_positions"]["joint_a"] = "not-a-number";
  writeJson(path, wrong_map_value);
  expectLoadFailure(path, "CHECKPOINT_PARSE_FAILED");

  auto nonfinite_json_number = valid.dump();
  const auto finite_position = nonfinite_json_number.find("-0.5");
  ASSERT_NE(std::string::npos, finite_position);
  nonfinite_json_number.replace(finite_position, 4, "1e999");
  {
    std::ofstream output(path, std::ios::out | std::ios::trunc);
    output << nonfinite_json_number;
  }
  expectLoadFailure(path, "CHECKPOINT_PARSE_FAILED");

  checkpoint.expected.joint_positions["joint_a"] = std::numeric_limits<double>::infinity();
  const auto commit_failure = store.commit(checkpoint);
  ASSERT_TRUE(commit_failure);
  EXPECT_EQ("CHECKPOINT_INVALID_DATA", commit_failure->code);

  checkpoint = makeRecoveryCheckpoint();
  checkpoint.original_failure->metrics["path_error"] = std::numeric_limits<double>::quiet_NaN();
  const auto metric_failure = store.commit(checkpoint);
  ASSERT_TRUE(metric_failure);
  EXPECT_EQ("CHECKPOINT_INVALID_DATA", metric_failure->code);
  std::filesystem::remove(path);
}

TEST(CheckpointV4, AtomicCommitReplacesTargetAndLeavesNoTemporaryFile)
{
  const auto path = checkpointPath("atomic_success");
  {
    std::ofstream output(path);
    output << "old checkpoint";
  }
  pick_place::FileCheckpointStore store(path);

  ASSERT_FALSE(store.commit(makeRecoveryCheckpoint()));
  EXPECT_EQ(4U, readJson(path).at("schema_version").get<std::uint32_t>());
  for (const auto & entry : std::filesystem::directory_iterator(path.parent_path())) {
    EXPECT_EQ(std::string::npos,
              entry.path().filename().string().find(path.filename().string() + ".tmp"));
  }
  std::filesystem::remove(path);
}

TEST(CheckpointV4, CommitFailurePreservesExistingTargetAndCleansTemporaryFile)
{
  const auto path = checkpointPath("rename_failure");
  std::filesystem::create_directory(path);
  {
    std::ofstream sentinel(path / "sentinel");
    sentinel << "preserve me";
  }
  pick_place::FileCheckpointStore store(path);

  const auto failure = store.commit(makeRecoveryCheckpoint());

  ASSERT_TRUE(failure);
  EXPECT_EQ("CHECKPOINT_ATOMIC_RENAME_FAILED", failure->code);
  EXPECT_TRUE(std::filesystem::exists(path / "sentinel"));
  for (const auto & entry : std::filesystem::directory_iterator(path.parent_path())) {
    EXPECT_EQ(std::string::npos,
              entry.path().filename().string().find(path.filename().string() + ".tmp"));
  }
  std::filesystem::remove_all(path);
}

TEST(CheckpointV4, ReportsDirectoryCreationWriteAndLoadFailures)
{
  const auto root = checkpointPath("io_failures");
  {
    std::ofstream blocking_parent(root);
    blocking_parent << "not a directory";
  }
  pick_place::FileCheckpointStore blocked_store(root / "checkpoint.json");
  const auto write_failure = blocked_store.commit(makeRecoveryCheckpoint());
  ASSERT_TRUE(write_failure);
  EXPECT_EQ("CHECKPOINT_DIRECTORY_CREATE_FAILED", write_failure->code);

  const auto missing = checkpointPath("missing");
  expectLoadFailure(missing, "CHECKPOINT_NOT_FOUND");
  std::filesystem::remove(root);
}

TEST(CommonResumeValidator, AcceptsOnlyACompleteMatchingWorldBoundary)
{
  auto checkpoint = makeRecoveryCheckpoint();
  checkpoint.resumable = true;
  const auto snapshot = snapshotFrom(checkpoint);
  const pick_place::CommonResumeValidator validator(checkpoint.configuration_fingerprint,
                                                    checkpoint.simulation_session_id);

  const auto result = validator.validate(checkpoint, snapshot);

  EXPECT_TRUE(result.ok);
  EXPECT_TRUE(result.failures.empty());
}

TEST(CommonResumeValidator, PreservesSO101QuaternionChordDistanceMetric)
{
  auto checkpoint = makeRecoveryCheckpoint();
  checkpoint.phase = pick_place::CheckpointPhase::FORWARD;
  checkpoint.failed_state.reset();
  checkpoint.original_failure.reset();
  checkpoint.resumable = true;
  auto snapshot = snapshotFrom(checkpoint);
  constexpr double rotation = 0.1;
  snapshot.tcp_pose_world.qz = std::sin(rotation / 2.0);
  snapshot.tcp_pose_world.qw = std::cos(rotation / 2.0);
  const pick_place::SO101ResumeValidationPolicy policy;

  const auto result = policy.validateBoundary(checkpoint, snapshot, 1.0);

  ASSERT_TRUE(result.ok);
  EXPECT_NEAR(result.metrics.at("resume_tcp_orientation_error"), 2.0 * std::sin(rotation / 4.0),
              1e-12);
  EXPECT_NE(result.metrics.at("resume_tcp_orientation_error"), rotation);
}

TEST(CommonResumeValidator, RejectsCheckpointFromDifferentPolicyBundle)
{
  auto checkpoint = makeRecoveryCheckpoint();
  checkpoint.configuration_fingerprint = "old-policy-bundle-sha256";
  const auto snapshot = snapshotFrom(checkpoint);
  const pick_place::CommonResumeValidator validator("new-policy-bundle-sha256",
                                                    checkpoint.simulation_session_id);

  const auto result = validator.validate(checkpoint, snapshot);

  ASSERT_FALSE(result.ok);
  const auto mismatch = std::find_if(result.failures.begin(), result.failures.end(),
                                     [](const pick_place::Failure & failure) {
                                       return failure.code == "CHECKPOINT_POLICY_MISMATCH";
                                     });
  EXPECT_NE(mismatch, result.failures.end());
}

TEST(CommonResumeValidator, ForwardResumeFailsClosedForEveryExpectedWorldBoundaryMismatch)
{
  auto checkpoint = makeRecoveryCheckpoint();
  checkpoint.phase = pick_place::CheckpointPhase::FORWARD;
  checkpoint.failed_state.reset();
  checkpoint.original_failure.reset();
  checkpoint.resumable = true;
  const pick_place::CommonResumeValidator validator(checkpoint.configuration_fingerprint,
                                                    checkpoint.simulation_session_id);
  const auto matching = snapshotFrom(checkpoint);

  std::vector<pick_place::WorldSnapshot> mismatches;
  auto tcp = matching;
  tcp.tcp_pose_world.x += 0.1;
  mismatches.push_back(tcp);
  auto gripper = matching;
  gripper.gripper_open = !gripper.gripper_open;
  mismatches.push_back(gripper);
  auto joint = matching;
  joint.joint_positions.at("joint_a") += 0.1;
  mismatches.push_back(joint);
  auto extra_joint = matching;
  extra_joint.joint_positions["joint_c"] = 0.0;
  mismatches.push_back(extra_joint);
  auto moveit_pose = matching;
  moveit_pose.moveit_world_object_poses.at("object").z += 0.1;
  mismatches.push_back(moveit_pose);
  auto missing_required_object = matching;
  missing_required_object.moveit_world_object_poses.erase("object");
  mismatches.push_back(missing_required_object);
  auto moveit_attachment = matching;
  moveit_attachment.moveit_task_object_attached = true;
  mismatches.push_back(moveit_attachment);
  auto gazebo_pose = matching;
  gazebo_pose.gazebo_task_object_pose_world->y += 0.1;
  mismatches.push_back(gazebo_pose);
  auto gazebo_attachment = matching;
  gazebo_attachment.gazebo_task_object_attached = false;
  mismatches.push_back(gazebo_attachment);
  auto gazebo_stationary = matching;
  gazebo_stationary.gazebo_task_object_stationary = false;
  mismatches.push_back(gazebo_stationary);

  for (const auto & mismatch : mismatches) {
    EXPECT_FALSE(validator.validate(checkpoint, mismatch).ok);
  }
}

TEST(CommonResumeValidator, SettlingWaitResumeAllowsOnlyGazeboPoseEvolution)
{
  auto checkpoint = makeRecoveryCheckpoint();
  checkpoint.phase = pick_place::CheckpointPhase::FORWARD;
  checkpoint.last_completed_state = pick_place::State::CLOSE_GRIPPER;
  checkpoint.next_state = pick_place::State::WAIT_GRASP_STABLE;
  checkpoint.failed_state.reset();
  checkpoint.original_failure.reset();
  checkpoint.resumable = true;
  auto settled_later = snapshotFrom(checkpoint);
  settled_later.gazebo_task_object_pose_world->x += 0.01;
  const pick_place::CommonResumeValidator validator(checkpoint.configuration_fingerprint,
                                                    checkpoint.simulation_session_id);

  EXPECT_TRUE(validator.validate(checkpoint, settled_later).ok);

  checkpoint.last_completed_state = pick_place::State::WAIT_GRASP_STABLE;
  checkpoint.next_state = pick_place::State::MICRO_LIFT;
  EXPECT_TRUE(validator.validate(checkpoint, settled_later).ok);

  checkpoint.last_completed_state = pick_place::State::DESCEND;
  checkpoint.next_state = pick_place::State::CLOSE_GRIPPER;
  EXPECT_FALSE(validator.validate(checkpoint, settled_later).ok);

  checkpoint.next_state = pick_place::State::WAIT_GRASP_STABLE;
  settled_later.gazebo_task_object_attached = false;
  EXPECT_FALSE(validator.validate(checkpoint, settled_later).ok);
}

TEST(CommonResumeValidator, AcceptsPhysicalGraspValidationCheckpointForExplicitOverride)
{
  auto checkpoint = makeRecoveryCheckpoint();
  checkpoint.phase = pick_place::CheckpointPhase::FORWARD;
  checkpoint.last_completed_state = pick_place::State::VERIFY_PHYSICAL_GRASP;
  checkpoint.failed_state = pick_place::State::VERIFY_PHYSICAL_GRASP;
  checkpoint.next_state = pick_place::State::VALIDATION_FAILED;
  checkpoint.original_failure = pick_place::Failure{pick_place::FailureCategory::POSTCONDITION,
                                                    "PHYSICAL_GRASP_TABLE_CLEARANCE",
                                                    "Cup did not clear the table",
                                                    {}};
  checkpoint.resumable = true;
  const auto snapshot = snapshotFrom(checkpoint);
  const pick_place::CommonResumeValidator validator(checkpoint.configuration_fingerprint,
                                                    checkpoint.simulation_session_id);

  const auto result = validator.validate(checkpoint, snapshot);

  EXPECT_TRUE(result.ok);
  EXPECT_TRUE(result.failures.empty());
}

TEST(CommonResumeValidator, FailsClosedForIncompleteNonFiniteOrStaleBoundaryEvidence)
{
  auto checkpoint = makeRecoveryCheckpoint();
  checkpoint.resumable = true;
  const pick_place::CommonResumeValidator validator(checkpoint.configuration_fingerprint,
                                                    checkpoint.simulation_session_id);
  const auto matching = snapshotFrom(checkpoint);

  auto missing_optional = matching;
  missing_optional.gazebo_task_object_pose_world.reset();
  EXPECT_FALSE(validator.validate(checkpoint, missing_optional).ok);

  auto nonfinite = matching;
  nonfinite.joint_positions.at("joint_a") = std::numeric_limits<double>::quiet_NaN();
  EXPECT_FALSE(validator.validate(checkpoint, nonfinite).ok);

  auto stale = matching;
  stale.fresh = false;
  EXPECT_FALSE(validator.validate(checkpoint, stale).ok);

  auto moving = matching;
  moving.arm_stationary = false;
  EXPECT_FALSE(validator.validate(checkpoint, moving).ok);

  auto wrong_session = matching;
  wrong_session.simulation_session_id = "other-session";
  EXPECT_FALSE(validator.validate(checkpoint, wrong_session).ok);

  checkpoint.configuration_fingerprint = "other-config";
  EXPECT_FALSE(validator.validate(checkpoint, matching).ok);
}

TEST(CommonResumeValidator, RejectsNonResumableAndIncompleteRecoveryContext)
{
  auto checkpoint = makeRecoveryCheckpoint();
  const auto snapshot = snapshotFrom(checkpoint);
  const pick_place::CommonResumeValidator validator(checkpoint.configuration_fingerprint,
                                                    checkpoint.simulation_session_id);

  checkpoint.resumable = false;
  EXPECT_FALSE(validator.validate(checkpoint, snapshot).ok);

  checkpoint.resumable = true;
  checkpoint.failed_state.reset();
  EXPECT_FALSE(validator.validate(checkpoint, snapshot).ok);

  checkpoint = makeRecoveryCheckpoint();
  checkpoint.resumable = true;
  checkpoint.original_failure.reset();
  EXPECT_FALSE(validator.validate(checkpoint, snapshot).ok);
}

TEST(CommonResumeValidator, RejectsPostReleaseEpochCheckpoint)
{
  auto checkpoint = makeForwardCheckpointWithNullOptionals();
  checkpoint.last_completed_state = pick_place::State::WAIT_RELEASE_SETTLE;
  checkpoint.next_state = pick_place::State::VALIDATE_FINAL_PLACEMENT;
  checkpoint.resumable = false;
  const auto current = snapshotFrom(checkpoint);
  const pick_place::CommonResumeValidator validator(checkpoint.configuration_fingerprint,
                                                    checkpoint.simulation_session_id);

  const auto result = validator.validate(checkpoint, current);

  ASSERT_FALSE(result.ok);
  ASSERT_FALSE(result.failures.empty());
  EXPECT_EQ("POST_RELEASE_EPOCH_NON_RESUMABLE", result.failures.front().code);
}
