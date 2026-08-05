#include <filesystem>
#include <fstream>

#include <gtest/gtest.h>

#include "planning_failure_replay.hpp"
#include "so101_gazebo_demo/pick_place/planning_failure_diagnostics.hpp"

namespace spp = so101_gazebo_demo::pick_place;
namespace replay = so101_gazebo_demo::pick_place::test;

namespace
{

spp::PlanningFailureArtifact artifact()
{
  moveit_msgs::action::MoveGroup::Goal request;
  request.request.group_name = "arm";
  request.planning_options.plan_only = true;
  moveit_msgs::msg::PlanningScene scene;
  scene.robot_model_name = "so101";
  return {1000,
          1,
          "session",
          std::string(64, 'a'),
          {0.02, -0.28, 0.20, 0.0, 0.0, 0.0, 1.0},
          0.002,
          request,
          scene,
          {},
          spp::SO101Profile::canonical(),
          {spp::PlanningFailureStage::MOVEIT_ERROR,
           {spp::ActionStatus::FAILED, spp::Failure{spp::FailureCategory::PLANNING,
                                                    "MICRO_LIFT_MOVEIT_PLAN_FAILED",
                                                    "planning failed",
                                                    {}}}}};
}

}  // namespace

TEST(PlanningFailureReplay, OfflineModeRoundTripsWithoutRos)
{
  const auto root = std::filesystem::temp_directory_path() / "so101-replay-offline";
  std::filesystem::remove_all(root);
  auto selected = spp::selectPlanningFailureDiagnostics(root);
  ASSERT_FALSE(selected.failure);
  ASSERT_FALSE(selected.sink->record(artifact()));
  const auto path = *std::filesystem::directory_iterator(root);
  const auto result = replay::runPlanningFailureReplay(
    {replay::PlanningFailureReplayMode::OFFLINE, path.path(), {}, {}, {}});
  EXPECT_FALSE(result.failure);
  EXPECT_FALSE(result.sent);
  std::filesystem::remove_all(root);
}

TEST(PlanningFailureReplay, RejectsProvenanceBeforeSend)
{
  const auto root = std::filesystem::temp_directory_path() / "so101-replay-provenance";
  std::filesystem::remove_all(root);
  auto selected = spp::selectPlanningFailureDiagnostics(root);
  ASSERT_FALSE(selected.failure);
  ASSERT_FALSE(selected.sink->record(artifact()));
  const auto path = *std::filesystem::directory_iterator(root);
  const auto result =
    replay::runPlanningFailureReplay({replay::PlanningFailureReplayMode::LIVE_PLAN_ONLY,
                                      path.path(),
                                      {},
                                      "wrong",
                                      std::string(64, 'b')});
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "PLANNING_REPLAY_PROVENANCE_MISMATCH");
  EXPECT_FALSE(result.sent);
  std::filesystem::remove_all(root);
}

TEST(PlanningFailureReplay, LiveModeForcesPlanOnly)
{
  const std::filesystem::path source = __FILE__;
  std::ifstream stream(source.parent_path() / "planning_failure_replay.cpp");
  const std::string bytes((std::istreambuf_iterator<char>(stream)), {});
  const auto force = bytes.find("artifact.request.planning_options.plan_only = true;");
  const auto send = bytes.find("async_send_goal(artifact.request)");
  ASSERT_NE(force, std::string::npos);
  ASSERT_NE(send, std::string::npos);
  EXPECT_LT(force, send);
}

TEST(PlanningFailureReplay, CaptureInjectionWritesOneArtifactWithoutSending)
{
  const std::filesystem::path source = __FILE__;
  std::ifstream stream(source.parent_path() / "planning_failure_replay.cpp");
  const std::string bytes((std::istreambuf_iterator<char>(stream)), {});
  const auto injection = bytes.find("CAPTURE_AND_INJECT_MOVEIT_ERROR");
  const auto record = bytes.find("selection.sink->record(artifact)", injection);
  ASSERT_NE(injection, std::string::npos);
  ASSERT_NE(record, std::string::npos);
  EXPECT_EQ(bytes.find("async_send_goal", record), std::string::npos);
}

TEST(PlanningFailureReplay, SourceOwnsNoExecutionOrControllerClient)
{
  const std::filesystem::path source = __FILE__;
  const auto core = source.parent_path() / "planning_failure_replay.cpp";
  std::ifstream stream(core);
  const std::string bytes((std::istreambuf_iterator<char>(stream)), {});
  EXPECT_EQ(bytes.find(".execute("), std::string::npos);
  EXPECT_EQ(bytes.find("FollowJointTrajectory"), std::string::npos);
  EXPECT_EQ(bytes.find("gripper_action"), std::string::npos);
  EXPECT_EQ(bytes.find("applyPlanningScene"), std::string::npos);
}
