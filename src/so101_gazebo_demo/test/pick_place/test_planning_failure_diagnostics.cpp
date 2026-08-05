#include <filesystem>
#include <fstream>
#include <regex>

#include <sys/stat.h>

#include <gtest/gtest.h>
#include <moveit_msgs/msg/collision_object.hpp>
#include <shape_msgs/msg/solid_primitive.hpp>

#include "so101_gazebo_demo/pick_place/planning_failure_diagnostics.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{
moveit_msgs::action::MoveGroup::Goal representativeGoal()
{
  moveit_msgs::action::MoveGroup::Goal goal;
  goal.request.workspace_parameters.header.frame_id = "world";
  goal.request.workspace_parameters.min_corner.x = -1.0;
  goal.request.workspace_parameters.max_corner.z = 2.0;
  goal.request.start_state.joint_state.name = {"1", "2"};
  goal.request.start_state.joint_state.position = {0.1, 0.2};
  goal.request.start_state.joint_state.effort = {0.3, 0.4};
  goal.request.start_state.is_diff = true;
  moveit_msgs::msg::Constraints constraints;
  constraints.name = "goal";
  moveit_msgs::msg::JointConstraint joint;
  joint.joint_name = "1";
  joint.position = 0.5;
  joint.tolerance_above = 0.01;
  joint.tolerance_below = 0.02;
  joint.weight = 0.9;
  constraints.joint_constraints.push_back(joint);
  goal.request.goal_constraints.push_back(constraints);
  goal.request.path_constraints.name = "path";
  goal.request.trajectory_constraints.constraints.push_back(constraints);
  moveit_msgs::msg::GenericTrajectory reference;
  reference.header.frame_id = "world";
  goal.request.reference_trajectories.push_back(reference);
  goal.request.pipeline_id = "ompl";
  goal.request.planner_id = "RRTConnectkConfigDefault";
  goal.request.group_name = "arm";
  goal.request.num_planning_attempts = 1;
  goal.request.allowed_planning_time = 5.0;
  goal.request.max_velocity_scaling_factor = 0.03;
  goal.request.max_acceleration_scaling_factor = 0.03;
  goal.request.cartesian_speed_limited_link = "so101_tcp";
  goal.request.max_cartesian_speed = 0.02;
  goal.planning_options.plan_only = true;
  goal.planning_options.look_around = true;
  goal.planning_options.look_around_attempts = 2;
  goal.planning_options.max_safe_execution_cost = 3.0;
  goal.planning_options.replan = true;
  goal.planning_options.replan_attempts = 4;
  goal.planning_options.replan_delay = 0.25;
  goal.planning_options.planning_scene_diff.name = "request-scene";
  goal.planning_options.planning_scene_diff.is_diff = true;
  return goal;
}

moveit_msgs::msg::PlanningScene representativeScene()
{
  moveit_msgs::msg::PlanningScene scene;
  scene.name = "observed";
  scene.robot_model_name = "so101";
  scene.robot_state.joint_state.header.stamp.sec = 10;
  scene.robot_state.joint_state.name = {"1"};
  scene.robot_state.joint_state.position = {0.1};
  moveit_msgs::msg::CollisionObject object;
  object.header.frame_id = "world";
  object.header.stamp.sec = 11;
  object.id = "plastic_cup";
  object.operation = moveit_msgs::msg::CollisionObject::ADD;
  shape_msgs::msg::SolidPrimitive primitive;
  primitive.type = shape_msgs::msg::SolidPrimitive::CYLINDER;
  primitive.dimensions = {0.09, 0.04};
  object.primitives.push_back(primitive);
  geometry_msgs::msg::Pose pose;
  pose.position.x = 0.02;
  pose.position.y = -0.28;
  pose.position.z = 0.165;
  pose.orientation.w = 1.0;
  object.primitive_poses.push_back(pose);
  scene.world.collision_objects.push_back(object);
  scene.allowed_collision_matrix.entry_names = {"plastic_cup", "jaw"};
  moveit_msgs::msg::AllowedCollisionEntry row;
  row.enabled = {false, true};
  scene.allowed_collision_matrix.entry_values = {row, row};
  return scene;
}

spp::PlanningDiagnosticsJson representativeArtifactDocument()
{
  const auto request = spp::canonicalMoveGroupGoalJson(representativeGoal());
  const auto scene_message = representativeScene();
  const auto scene = spp::canonicalPlanningSceneJson(scene_message);
  return {{"schema_version", 1},
          {"artifact_kind", "SO101_PLANNING_FAILURE"},
          {"operation", "MICRO_LIFT_WORLD_Z"},
          {"captured_at_unix_ns", 1000},
          {"process_sequence", 1},
          {"simulation_session_id", "test-session"},
          {"configuration_fingerprint", std::string(64, 'a')},
          {"request_sha256", spp::planningDiagnosticsSha256(request.dump())},
          {"scene_sha256", spp::planningDiagnosticsSha256(scene.dump())},
          {"replay_scene_fingerprint", spp::replaySceneFingerprint(scene_message)},
          {"source_tcp_world",
           {{"position", {0.02, -0.28, 0.20}}, {"orientation", {0.0, 0.0, 0.0, 1.0}}}},
          {"world_z_delta_m", 0.002},
          {"request", request},
          {"scene", scene},
          {"contacts",
           {{"raw_collision", true},
            {"request_collision", false},
            {"raw_contacts", {{"jaw|plastic_cup", 1}}},
            {"request_contacts", spp::PlanningDiagnosticsJson::object()}}},
          {"profile_identity",
           {{"world_frame", "world"},
            {"planning_group", "arm"},
            {"tcp_link", "so101_tcp"},
            {"task_object_id", "plastic_cup"},
            {"table_object", "table"},
            {"pedestal_object", "base_pedestal"},
            {"moveit_attach_link", "gripper"},
            {"moveit_touch_links", {"gripper", "jaw"}}}},
          {"result",
           {{"failure_stage", "MOVEIT_ERROR"},
            {"original_status", static_cast<int>(spp::ActionStatus::FAILED)},
            {"original_failure_category", static_cast<int>(spp::FailureCategory::PLANNING)},
            {"original_failure_code", "MICRO_LIFT_MOVEIT_PLAN_FAILED"},
            {"original_failure_message", "planning failed"},
            {"transport_result_code", 4},
            {"moveit_error_code", -1},
            {"planning_time", 0.5},
            {"trajectory_joint_names", spp::PlanningDiagnosticsJson::array()},
            {"trajectory_points", 0},
            {"trajectory_duration_seconds", nullptr},
            {"cancel_acknowledged", nullptr},
            {"cancel_terminal", nullptr}}}};
}

std::filesystem::path writeDocument(const std::filesystem::path & directory,
                                    const std::string & name, const std::string & bytes)
{
  const auto path = directory / name;
  std::ofstream stream(path, std::ios::binary);
  stream << bytes;
  return path;
}

spp::PlanningFailureArtifact representativeArtifact()
{
  return {1000,
          1,
          "test-session",
          std::string(64, 'a'),
          {0.02, -0.28, 0.20, 0.0, 0.0, 0.0, 1.0},
          0.002,
          representativeGoal(),
          representativeScene(),
          {true, false, {{"jaw|plastic_cup", 1}}, {}},
          spp::SO101Profile::canonical(),
          {spp::PlanningFailureStage::MOVEIT_ERROR,
           {spp::ActionStatus::FAILED, spp::Failure{spp::FailureCategory::PLANNING,
                                                    "MICRO_LIFT_MOVEIT_PLAN_FAILED",
                                                    "planning failed",
                                                    {}}},
           4,
           -1,
           0.5,
           {},
           0,
           std::nullopt,
           std::nullopt,
           std::nullopt}};
}
}  // namespace

TEST(PlanningFailureDiagnostics, ExactCdrRoundTripPreservesAbsentStartVelocities)
{
  const auto original = representativeGoal();
  const auto canonical = spp::canonicalMoveGroupGoalJson(original);
  ASSERT_TRUE(canonical.at("human_readable")
                .at("request")
                .at("start_state")
                .at("joint_state")
                .at("velocity")
                .is_null());
  spp::PlanningDiagnosticsJson document{{"request", canonical}};

  const auto reconstructed = spp::reconstructMoveGroupGoal(document);

  ASSERT_TRUE(std::holds_alternative<moveit_msgs::action::MoveGroup::Goal>(reconstructed));
  const auto & goal = std::get<moveit_msgs::action::MoveGroup::Goal>(reconstructed);
  EXPECT_TRUE(goal.request.start_state.joint_state.velocity.empty());
  EXPECT_EQ(spp::canonicalMoveGroupGoalJson(goal), canonical);
}

TEST(PlanningFailureDiagnostics, CdrRoundTripCoversEveryRequestAndPlanningOptionsField)
{
  const auto original = representativeGoal();
  spp::PlanningDiagnosticsJson document{{"request", spp::canonicalMoveGroupGoalJson(original)}};
  const auto reconstructed = spp::reconstructMoveGroupGoal(document);
  ASSERT_TRUE(std::holds_alternative<moveit_msgs::action::MoveGroup::Goal>(reconstructed));
  EXPECT_EQ(
    spp::canonicalMoveGroupGoalJson(std::get<moveit_msgs::action::MoveGroup::Goal>(reconstructed)),
    document.at("request"));
}

TEST(PlanningFailureDiagnostics, ReplaySceneFingerprintIgnoresFeedbackAndTimestamps)
{
  const auto scene = representativeScene();
  auto changed = scene;
  changed.robot_state.joint_state.header.stamp.sec = 99;
  changed.robot_state.joint_state.position = {0.9};
  changed.world.collision_objects.front().header.stamp.sec = 100;
  EXPECT_EQ(spp::replaySceneFingerprint(scene), spp::replaySceneFingerprint(changed));
}

TEST(PlanningFailureDiagnostics, ReplaySceneFingerprintChangesForReplayRelevantTopology)
{
  const auto scene = representativeScene();
  const auto original = spp::replaySceneFingerprint(scene);
  auto geometry = scene;
  geometry.world.collision_objects.front().primitives.front().dimensions[1] += 0.001;
  auto pose = scene;
  pose.world.collision_objects.front().primitive_poses.front().position.x += 0.001;
  auto attached = scene;
  moveit_msgs::msg::AttachedCollisionObject body;
  body.link_name = "gripper";
  body.object = attached.world.collision_objects.front();
  body.touch_links = {"jaw"};
  attached.robot_state.attached_collision_objects.push_back(body);
  auto acm = scene;
  acm.allowed_collision_matrix.entry_values.front().enabled.back() = false;
  EXPECT_NE(spp::replaySceneFingerprint(geometry), original);
  EXPECT_NE(spp::replaySceneFingerprint(pose), original);
  EXPECT_NE(spp::replaySceneFingerprint(attached), original);
  EXPECT_NE(spp::replaySceneFingerprint(acm), original);
}

TEST(PlanningFailureDiagnostics, FullSceneCanonicalizationChangesWithFeedback)
{
  const auto scene = representativeScene();
  auto changed = scene;
  changed.robot_state.joint_state.position.front() += 0.1;
  EXPECT_NE(spp::canonicalPlanningSceneJson(scene), spp::canonicalPlanningSceneJson(changed));
}

TEST(PlanningFailureDiagnostics, RejectsTruncatedUnsupportedOrHashMutatedArtifact)
{
  const auto directory =
    std::filesystem::temp_directory_path() / "so101-planning-diagnostics-schema-test";
  std::filesystem::remove_all(directory);
  std::filesystem::create_directories(directory);
  const auto document = representativeArtifactDocument();
  auto unsupported = document;
  unsupported["schema_version"] = 2;
  auto hash_mutated = document;
  hash_mutated["request"]["human_readable"]["request"]["planner_id"] = "mutated";

  const auto truncated_result = spp::loadPlanningFailureArtifact(
    writeDocument(directory, "truncated.json", "{\"schema_version\":"));
  const auto unsupported_result = spp::loadPlanningFailureArtifact(
    writeDocument(directory, "unsupported.json", unsupported.dump()));
  const auto hash_result =
    spp::loadPlanningFailureArtifact(writeDocument(directory, "hash.json", hash_mutated.dump()));

  EXPECT_TRUE(std::holds_alternative<spp::Failure>(truncated_result));
  EXPECT_TRUE(std::holds_alternative<spp::Failure>(unsupported_result));
  EXPECT_TRUE(std::holds_alternative<spp::Failure>(hash_result));
  std::filesystem::remove_all(directory);
}

TEST(PlanningFailureDiagnostics, EmptySelectionUsesNullSinkWithoutFilesystemEffects)
{
  const auto selection = spp::selectPlanningFailureDiagnostics({});
  ASSERT_FALSE(selection.failure);
  ASSERT_TRUE(selection.sink);
  EXPECT_FALSE(selection.sink->record(representativeArtifact()));
}

TEST(PlanningFailureDiagnostics, RejectsRelativeFileAndUnwritableDirectories)
{
  const auto root = std::filesystem::temp_directory_path() / "so101-planning-sink-invalid";
  std::filesystem::remove_all(root);
  std::filesystem::create_directories(root);
  const auto file = root / "file";
  std::ofstream(file) << "not a directory";
  const auto unwritable = root / "unwritable";
  std::filesystem::create_directory(unwritable);
  ASSERT_EQ(::chmod(unwritable.c_str(), 0500), 0);

  for (const auto & path : {std::filesystem::path("relative"), file, unwritable}) {
    const auto selection = spp::selectPlanningFailureDiagnostics(path);
    ASSERT_TRUE(selection.failure) << path;
    EXPECT_EQ(selection.failure->code, "PLANNING_DIAGNOSTICS_DIR_INVALID");
  }
  ASSERT_EQ(::chmod(unwritable.c_str(), 0700), 0);
  std::filesystem::remove_all(root);
}

TEST(PlanningFailureDiagnostics, FileSinkCreatesOwnerOnlyUniqueImmutableArtifacts)
{
  const auto directory = std::filesystem::temp_directory_path() / "so101-planning-sink-artifacts";
  std::filesystem::remove_all(directory);
  const auto selection = spp::selectPlanningFailureDiagnostics(directory);
  ASSERT_FALSE(selection.failure);
  ASSERT_TRUE(selection.sink);
  auto artifact = representativeArtifact();
  EXPECT_FALSE(selection.sink->record(artifact));
  EXPECT_FALSE(selection.sink->record(artifact));

  struct stat directory_stat
  {
  };
  ASSERT_EQ(::stat(directory.c_str(), &directory_stat), 0);
  EXPECT_EQ(directory_stat.st_mode & 0777, 0700);
  std::vector<std::filesystem::path> files;
  for (const auto & entry : std::filesystem::directory_iterator(directory)) {
    files.push_back(entry.path());
    struct stat file_stat
    {
    };
    ASSERT_EQ(::stat(entry.path().c_str(), &file_stat), 0);
    EXPECT_EQ(file_stat.st_mode & 0777, 0600);
    EXPECT_TRUE(std::regex_match(entry.path().filename().string(),
                                 std::regex("[0-9]+-[0-9]+-micro-lift-[0-9a-f]{12}\\.json")));
    EXPECT_TRUE(std::holds_alternative<spp::PlanningFailureArtifact>(
      spp::loadPlanningFailureArtifact(entry.path())));
  }
  ASSERT_EQ(files.size(), 2U);
  EXPECT_NE(files[0], files[1]);
  std::filesystem::remove_all(directory);
}

TEST(PlanningFailureDiagnostics, WriteFailurePreservesInputAndReturnsDiagnosticFailure)
{
  const auto directory = std::filesystem::temp_directory_path() / "so101-planning-sink-failure";
  std::filesystem::remove_all(directory);
  const auto selection = spp::selectPlanningFailureDiagnostics(directory);
  ASSERT_FALSE(selection.failure);
  auto artifact = representativeArtifact();
  const auto request_before = spp::canonicalMoveGroupGoalJson(artifact.request);
  ASSERT_EQ(::chmod(directory.c_str(), 0500), 0);

  const auto failure = selection.sink->record(artifact);

  ASSERT_TRUE(failure);
  EXPECT_EQ(failure->code, "PLANNING_DIAGNOSTIC_WRITE_FAILED");
  EXPECT_EQ(spp::canonicalMoveGroupGoalJson(artifact.request), request_before);
  ASSERT_EQ(::chmod(directory.c_str(), 0700), 0);
  std::filesystem::remove_all(directory);
}
