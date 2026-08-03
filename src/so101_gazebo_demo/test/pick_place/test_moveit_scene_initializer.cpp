#include <gtest/gtest.h>

#include <chrono>
#include <cmath>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "so101_gazebo_demo/pick_place/moveit_scene_initializer.hpp"
#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "so101_gazebo_demo/pick_place/so101_joint_motion_adapter.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

spp::ActionResult ok()
{
  return {spp::ActionStatus::SUCCEEDED, std::nullopt};
}

spp::ActionResult fail(std::string code)
{
  return {spp::ActionStatus::FAILED,
          spp::Failure{spp::FailureCategory::MOVEIT_SCENE, std::move(code), "test", {}}};
}

spp::CurrentJointStateEvidence completeEvidence()
{
  spp::CurrentJointStateEvidence e;
  e.joint_names = {"1", "2", "3", "4", "5"};
  e.positions = {0.0, 0.0, 0.0, 0.0, 0.0};
  e.velocities = {0.0, 0.0, 0.0, 0.0, 0.0};
  e.gripper_position = 0.5;
  e.gripper_velocity = 0.0;
  e.received_at = std::chrono::steady_clock::now();
  return e;
}

spp::CurrentJointStateEvidence incompleteEvidence()
{
  spp::CurrentJointStateEvidence e;
  e.joint_names = {"1", "2", "3"};
  e.positions = {0.0, 0.0, 0.0};
  e.velocities = {0.0, 0.0, 0.0};
  e.gripper_position = 0.5;
  e.gripper_velocity = 0.0;
  return e;
}

spp::MoveItSceneState convergedScene()
{
  spp::MoveItSceneState s;
  s.table_in_world = true;
  s.table_world_pose = spp::Pose3d{0.0, -0.20, 0.10, 0.0, 0.0, 0.0, 1.0};
  s.pedestal_in_world = true;
  s.pedestal_world_pose = spp::Pose3d{0.0, 0.0, 0.17, 0.0, 0.0, 0.0, 1.0};
  s.task_object_in_world = true;
  s.task_object_world_pose = spp::Pose3d{0.02, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0};
  return s;
}

spp::MoveItSceneState emptyScene()
{
  return {};
}

class FakeBoundary final : public spp::IJointPlanningBoundary
{
public:
  std::optional<spp::CurrentJointStateEvidence> currentState() override
  {
    ++current_state_calls;
    if (evidence_sequence_index < evidence_sequence.size()) {
      return evidence_sequence[evidence_sequence_index++];
    }
    return current_evidence;
  }

  std::optional<spp::MotionPlanningSceneFacts> sceneFacts() override { return std::nullopt; }

  spp::JointSegmentPlanResult planSegment(
    const std::vector<std::string> &, const std::vector<double> &,
    const std::vector<double> &, const std::set<std::string> &,
    const std::optional<spp::TemporalContactPolicy> &, double, double, double) override
  {
    return {};
  }

  std::optional<spp::CurrentJointStateEvidence> current_evidence;
  std::vector<std::optional<spp::CurrentJointStateEvidence>> evidence_sequence;
  std::size_t evidence_sequence_index{0};
  int current_state_calls{0};
};

class FakeScene final : public spp::IMoveItSceneAdapter
{
public:
  spp::ActionResult attachTaskObject(const spp::MoveItAttachmentSpec &) override
  {
    return ok();
  }
  spp::ActionResult detachTaskObject() override { return ok(); }

  spp::ActionResult upsertTableWorldPose(const spp::Pose3d &) override
  {
    ++upsert_table_calls;
    return table_result;
  }

  spp::ActionResult upsertPedestalWorldPose(const spp::Pose3d &) override
  {
    ++upsert_pedestal_calls;
    return pedestal_result;
  }

  spp::ActionResult upsertTaskObjectWorldPose(const spp::Pose3d &) override
  {
    ++upsert_task_object_calls;
    return task_object_result;
  }

  std::optional<spp::MoveItSceneState> observe() override
  {
    ++observe_calls;
    if (observe_sequence_index < observe_sequence.size()) {
      return observe_sequence[observe_sequence_index++];
    }
    return observe_result;
  }

  spp::ActionResult table_result{ok()};
  spp::ActionResult pedestal_result{ok()};
  spp::ActionResult task_object_result{ok()};
  std::optional<spp::MoveItSceneState> observe_result;
  std::vector<std::optional<spp::MoveItSceneState>> observe_sequence;
  std::size_t observe_sequence_index{0};
  int upsert_table_calls{0};
  int upsert_pedestal_calls{0};
  int upsert_task_object_calls{0};
  int observe_calls{0};
};

const auto kShortTimeout = std::chrono::milliseconds(200);
const auto kNoPoll = std::chrono::milliseconds(1);

}  // namespace

TEST(MoveItSceneInitializer, succeedsWhenEvidenceAndSceneReady)
{
  FakeBoundary boundary;
  boundary.current_evidence = completeEvidence();
  FakeScene scene;
  scene.observe_result = convergedScene();

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_FALSE(result.has_value()) << result->code << ": " << result->message;
  EXPECT_EQ(scene.upsert_table_calls, 1);
  EXPECT_EQ(scene.upsert_pedestal_calls, 1);
  EXPECT_EQ(scene.upsert_task_object_calls, 1);
}

TEST(MoveItSceneInitializer, failsOnJointTimeout)
{
  FakeBoundary boundary;
  boundary.current_evidence = incompleteEvidence();
  FakeScene scene;

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "JOINT_EVIDENCE_INCOMPLETE");
  EXPECT_EQ(scene.upsert_table_calls, 0);
  EXPECT_EQ(scene.upsert_pedestal_calls, 0);
  EXPECT_EQ(scene.upsert_task_object_calls, 0);
}

TEST(MoveItSceneInitializer, failsWhenJointsNeverArrive)
{
  FakeBoundary boundary;
  boundary.current_evidence = std::nullopt;
  FakeScene scene;

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "JOINT_EVIDENCE_INCOMPLETE");
}

TEST(MoveItSceneInitializer, waitsForDelayedCompleteJoints)
{
  FakeBoundary boundary;
  boundary.evidence_sequence = {
    incompleteEvidence(), incompleteEvidence(), std::nullopt, completeEvidence()};
  boundary.current_evidence = completeEvidence();
  FakeScene scene;
  scene.observe_result = convergedScene();

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), std::chrono::seconds(2));
  ASSERT_FALSE(result.has_value()) << result->code << ": " << result->message;
  EXPECT_EQ(scene.upsert_table_calls, 1);
}

TEST(MoveItSceneInitializer, upsertsTableBeforePedestalBeforeTaskObject)
{
  FakeBoundary boundary;
  boundary.current_evidence = completeEvidence();
  FakeScene scene;
  scene.observe_result = convergedScene();

  std::vector<std::string> order;
  auto trackOrder = [&](const std::string & name, spp::ActionResult result) {
    return spp::ActionResult{result.status, result.failure};
  };

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  EXPECT_GE(scene.upsert_table_calls, 1);
  EXPECT_GE(scene.upsert_pedestal_calls, 1);
  EXPECT_GE(scene.upsert_task_object_calls, 1);
}

TEST(MoveItSceneInitializer, failsOnTableUpsertFailure)
{
  FakeBoundary boundary;
  boundary.current_evidence = completeEvidence();
  FakeScene scene;
  scene.table_result = fail("MOVEIT_TABLE_UPSERT_APPLY_FAILED");

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->category, spp::FailureCategory::MOVEIT_SCENE);
  EXPECT_EQ(scene.upsert_pedestal_calls, 0);
  EXPECT_EQ(scene.upsert_task_object_calls, 0);
}

TEST(MoveItSceneInitializer, failsOnPedestalUpsertFailure)
{
  FakeBoundary boundary;
  boundary.current_evidence = completeEvidence();
  FakeScene scene;
  scene.pedestal_result = fail("MOVEIT_PEDESTAL_UPSERT_APPLY_FAILED");

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->category, spp::FailureCategory::MOVEIT_SCENE);
  EXPECT_EQ(scene.upsert_table_calls, 1);
  EXPECT_EQ(scene.upsert_task_object_calls, 0);
}

TEST(MoveItSceneInitializer, failsOnTaskObjectUpsertFailure)
{
  FakeBoundary boundary;
  boundary.current_evidence = completeEvidence();
  FakeScene scene;
  scene.task_object_result = fail("MOVEIT_TASK_OBJECT_UPSERT_APPLY_FAILED");

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->category, spp::FailureCategory::MOVEIT_SCENE);
  EXPECT_EQ(scene.upsert_table_calls, 1);
  EXPECT_EQ(scene.upsert_pedestal_calls, 1);
}

TEST(MoveItSceneInitializer, waitsForDelayedSceneConvergence)
{
  FakeBoundary boundary;
  boundary.current_evidence = completeEvidence();
  FakeScene scene;
  scene.observe_sequence = {emptyScene(), emptyScene(), convergedScene()};
  scene.observe_result = convergedScene();

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), std::chrono::seconds(2));
  ASSERT_FALSE(result.has_value()) << result->code << ": " << result->message;
  EXPECT_GE(scene.observe_calls, 3);
}

TEST(MoveItSceneInitializer, failsOnSceneConvergenceTimeout)
{
  FakeBoundary boundary;
  boundary.current_evidence = completeEvidence();
  FakeScene scene;
  scene.observe_result = emptyScene();

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "MOVEIT_SCENE_EVIDENCE_INCOMPLETE");
}

TEST(MoveItSceneInitializer, failsOnNonFiniteJointPosition)
{
  FakeBoundary boundary;
  auto e = completeEvidence();
  e.positions[2] = std::numeric_limits<double>::quiet_NaN();
  boundary.current_evidence = e;
  FakeScene scene;

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "JOINT_EVIDENCE_INCOMPLETE");
}

TEST(MoveItSceneInitializer, failsWhenGripperEvidenceMissing)
{
  FakeBoundary boundary;
  auto e = completeEvidence();
  e.gripper_position = std::nullopt;
  boundary.current_evidence = e;
  FakeScene scene;

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "JOINT_EVIDENCE_INCOMPLETE");
}

TEST(MoveItSceneInitializer, rejectsSixArmPositionsAsWrongSemantics)
{
  FakeBoundary boundary;
  auto e = completeEvidence();
  e.positions.push_back(0.0);
  e.velocities.push_back(0.0);
  boundary.current_evidence = e;
  FakeScene scene;

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "JOINT_EVIDENCE_INCOMPLETE");
}

TEST(MoveItSceneInitializer, rejectsSceneWhenTaskObjectAttached)
{
  FakeBoundary boundary;
  boundary.current_evidence = completeEvidence();
  FakeScene scene;
  auto s = convergedScene();
  s.task_object_attached = true;
  scene.observe_result = s;

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "MOVEIT_SCENE_EVIDENCE_INCOMPLETE");
}

TEST(MoveItSceneInitializer, rejectsSceneWhenTablePoseMismatch)
{
  FakeBoundary boundary;
  boundary.current_evidence = completeEvidence();
  FakeScene scene;
  auto s = convergedScene();
  s.table_world_pose = spp::Pose3d{1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 1.0};
  scene.observe_result = s;

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "MOVEIT_SCENE_EVIDENCE_INCOMPLETE");
}

TEST(MoveItSceneInitializer, rejectsWrongJointNames)
{
  FakeBoundary boundary;
  auto e = completeEvidence();
  e.joint_names = {"a", "b", "c", "d", "e"};
  boundary.current_evidence = e;
  FakeScene scene;

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "JOINT_EVIDENCE_INCOMPLETE");
}

TEST(MoveItSceneInitializer, rejectsNoncanonicalTaskObjectPose)
{
  FakeBoundary boundary;
  boundary.current_evidence = completeEvidence();
  FakeScene scene;
  auto s = convergedScene();
  s.task_object_world_pose = spp::Pose3d{5.0, 5.0, 5.0, 0.0, 0.0, 0.0, 1.0};
  scene.observe_result = s;

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "MOVEIT_SCENE_EVIDENCE_INCOMPLETE");
}

TEST(MoveItSceneInitializer, rejectsQuaternionMismatch)
{
  FakeBoundary boundary;
  boundary.current_evidence = completeEvidence();
  FakeScene scene;
  auto s = convergedScene();
  s.pedestal_world_pose = spp::Pose3d{0.0, 0.0, 0.17, 0.707, 0.0, 0.0, 0.707};
  scene.observe_result = s;

  spp::MoveItSceneInitializer init(boundary, scene, kNoPoll);
  const auto result = init.initialize(spp::SO101Profile::canonical(), kShortTimeout);
  ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result->code, "MOVEIT_SCENE_EVIDENCE_INCOMPLETE");
}
