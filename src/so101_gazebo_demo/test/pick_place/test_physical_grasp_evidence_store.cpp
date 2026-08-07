#include <gtest/gtest.h>

#include <chrono>
#include <filesystem>

#include "so101_gazebo_demo/pick_place/physical_grasp_evidence_store.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{
WorldSnapshot snapshot()
{
  WorldSnapshot value;
  value.tcp_pose_world = {0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0};
  value.gazebo_task_object_pose_world = Pose3d{0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 1.0};
  value.gazebo_task_object_gripper_contact = true;
  return value;
}

std::filesystem::path sidecarPath()
{
  return std::filesystem::temp_directory_path() / "so101-physical-grasp-evidence-test.json";
}

TEST(PhysicalGraspEvidenceStore, AtomicallyRoundTripsFiniteOrderedSamples)
{
  FilePhysicalGraspEvidenceStore store(sidecarPath(), "session", "fingerprint");
  ASSERT_FALSE(store.resetForFreshRun());
  const PhysicalGraspRetryEvidence retry{{2, 1, -0.048}, -0.053, PhysicalGraspRetryPhase::IDLE};
  ASSERT_FALSE(store.saveRetryEvidence(retry));
  ASSERT_FALSE(store.saveBefore(snapshot()));
  ASSERT_FALSE(store.saveAfter(snapshot()));
  const auto loaded = store.load();
  ASSERT_TRUE(std::holds_alternative<PhysicalGraspEvidenceRecord>(loaded));
  const auto & record = std::get<PhysicalGraspEvidenceRecord>(loaded);
  ASSERT_TRUE(record.before_lift);
  ASSERT_TRUE(record.after_lift);
  EXPECT_EQ(record.retry.progress.attempt_index, 2U);
  EXPECT_EQ(record.retry.progress.contact_missing_count, 1U);
  EXPECT_DOUBLE_EQ(record.retry.progress.current_reclose_target_q6, -0.048);
  EXPECT_DOUBLE_EQ(record.retry.micro_lift_preload_target_q6, -0.053);
  EXPECT_LE(record.before_lift->captured_at_unix_ns, record.after_lift->captured_at_unix_ns);
}

TEST(PhysicalGraspEvidenceStore, StartingRetryAttemptInvalidatesPriorAfterLiftSample)
{
  FilePhysicalGraspEvidenceStore store(sidecarPath(), "session", "fingerprint");
  ASSERT_FALSE(store.resetForFreshRun());
  ASSERT_FALSE(store.saveBefore(snapshot()));
  ASSERT_FALSE(store.saveAfter(snapshot()));

  ASSERT_FALSE(store.saveBefore(snapshot()));

  const auto loaded = store.load();
  ASSERT_TRUE(std::holds_alternative<PhysicalGraspEvidenceRecord>(loaded));
  const auto & record = std::get<PhysicalGraspEvidenceRecord>(loaded);
  EXPECT_TRUE(record.before_lift.has_value());
  EXPECT_FALSE(record.after_lift.has_value());
}

TEST(PhysicalGraspEvidenceStore, RejectsSessionFingerprintAndMissingEvidence)
{
  FilePhysicalGraspEvidenceStore writer(sidecarPath(), "session-a", "fingerprint-a");
  ASSERT_FALSE(writer.resetForFreshRun());
  ASSERT_FALSE(writer.saveBefore(snapshot()));
  FilePhysicalGraspEvidenceStore reader(sidecarPath(), "session-b", "fingerprint-a");
  const auto mismatch = reader.load();
  ASSERT_TRUE(std::holds_alternative<Failure>(mismatch));
  EXPECT_EQ(std::get<Failure>(mismatch).code, "PHYSICAL_GRASP_EVIDENCE_SESSION_MISMATCH");
  ASSERT_FALSE(writer.resetForFreshRun());
  const auto missing = writer.load();
  ASSERT_TRUE(std::holds_alternative<Failure>(missing));
  EXPECT_EQ(std::get<Failure>(missing).code, "PHYSICAL_GRASP_EVIDENCE_MISSING");
}
}  // namespace
}  // namespace so101_gazebo_demo::pick_place
