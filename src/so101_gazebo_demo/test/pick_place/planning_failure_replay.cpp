#include "planning_failure_replay.hpp"

#include <chrono>
#include <fstream>
#include <regex>
#include <variant>

#include <moveit_msgs/msg/move_it_error_codes.hpp>
#include <rclcpp_action/create_client.hpp>

#include "so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp"
#include "so101_gazebo_demo/pick_place/planning_failure_diagnostics.hpp"

namespace so101_gazebo_demo::pick_place::test
{
namespace
{

Failure replayFailure(std::string code, std::string message)
{
  return {FailureCategory::CONFIGURATION, std::move(code), std::move(message), {}};
}

bool validFingerprint(const std::string & value)
{
  return std::regex_match(value, std::regex("[0-9a-f]{64}"));
}

PlanningFailureReplayResult failed(Failure failure)
{
  return {false, std::nullopt, std::move(failure)};
}

}  // namespace

PlanningFailureReplayResult runPlanningFailureReplay(const PlanningFailureReplayOptions & options,
                                                     const std::shared_ptr<rclcpp::Node> & node)
{
  if (options.mode != PlanningFailureReplayMode::CAPTURE_AND_INJECT_MOVEIT_ERROR) {
    if (!options.artifact.is_absolute())
      return failed(
        replayFailure("PLANNING_REPLAY_ARTIFACT_INVALID", "artifact path must be absolute"));
    auto loaded = loadPlanningFailureArtifact(options.artifact);
    if (std::holds_alternative<Failure>(loaded))
      return failed(std::get<Failure>(std::move(loaded)));
    auto artifact = std::get<PlanningFailureArtifact>(std::move(loaded));
    if (options.mode == PlanningFailureReplayMode::OFFLINE)
      return {};
    if (!node || !validFingerprint(options.expected_fingerprint) ||
        artifact.simulation_session_id != options.expected_session_id ||
        artifact.configuration_fingerprint != options.expected_fingerprint) {
      return failed(replayFailure("PLANNING_REPLAY_PROVENANCE_MISMATCH",
                                  "artifact session or configuration fingerprint mismatch"));
    }
    MoveItJointPlanningBoundary boundary(node, artifact.profile_identity);
    const auto current = boundary.captureWorldZMicroLiftPlanningRequest(artifact.source_tcp_world,
                                                                        artifact.world_z_delta_m);
    if (std::holds_alternative<ActionResult>(current))
      return failed(*std::get<ActionResult>(current).failure);
    const auto & capture = std::get<MicroLiftPlanningCapture>(current);
    if (replaySceneFingerprint(capture.observed_scene) !=
        replaySceneFingerprint(artifact.observed_scene)) {
      return failed(replayFailure("PLANNING_REPLAY_SCENE_MISMATCH",
                                  "current replay topology differs from the artifact"));
    }
    artifact.request.planning_options.plan_only = true;
    auto client =
      rclcpp_action::create_client<moveit_msgs::action::MoveGroup>(node, "/move_action");
    if (!client->wait_for_action_server(std::chrono::seconds(5)))
      return failed(replayFailure("PLANNING_REPLAY_ACTION_UNAVAILABLE", "MoveGroup unavailable"));
    const auto goal = client->async_send_goal(artifact.request);
    if (goal.wait_for(std::chrono::seconds(3)) != std::future_status::ready || !goal.get())
      return failed(replayFailure("PLANNING_REPLAY_GOAL_REJECTED", "MoveGroup rejected replay"));
    const auto output = options.artifact.string() + ".replay-result.json";
    std::ofstream stream(output, std::ios::binary | std::ios::trunc);
    stream << PlanningDiagnosticsJson{{"sent", true}, {"plan_only", true}}.dump(2) << '\n';
    return {true, std::filesystem::path(output), std::nullopt};
  }

  if (!node || !options.output_directory.is_absolute() ||
      !validFingerprint(options.expected_fingerprint)) {
    return failed(replayFailure("PLANNING_REPLAY_CONFIGURATION_INVALID",
                                "injection requires node, absolute output, and fingerprint"));
  }
  MoveItJointPlanningBoundary boundary(node, SO101Profile::canonical());
  const Pose3d source{0.02, -0.28, 0.20, 0.0, 0.0, 0.0, 1.0};
  auto captured = boundary.captureWorldZMicroLiftPlanningRequest(source, 0.002);
  if (std::holds_alternative<ActionResult>(captured))
    return failed(*std::get<ActionResult>(captured).failure);
  auto capture = std::get<MicroLiftPlanningCapture>(std::move(captured));
  MicroLiftPlanningOutcome outcome;
  outcome.action = {ActionStatus::SUCCEEDED, std::nullopt};
  outcome.failure_stage = PlanningFailureStage::MOVEIT_ERROR;
  outcome.result = std::make_shared<moveit_msgs::action::MoveGroup::Result>();
  outcome.result->error_code.val = moveit_msgs::msg::MoveItErrorCodes::PLANNING_FAILED;
  const auto original = classifyMicroLiftPlanningOutcome(outcome);
  PlanningFailureArtifact artifact{std::chrono::duration_cast<std::chrono::nanoseconds>(
                                     std::chrono::system_clock::now().time_since_epoch())
                                     .count(),
                                   1,
                                   options.expected_session_id,
                                   options.expected_fingerprint,
                                   source,
                                   0.002,
                                   std::move(capture.request),
                                   std::move(capture.observed_scene),
                                   std::move(capture.contacts),
                                   SO101Profile::canonical(),
                                   {PlanningFailureStage::MOVEIT_ERROR, original, std::nullopt,
                                    moveit_msgs::msg::MoveItErrorCodes::PLANNING_FAILED}};
  auto selection = selectPlanningFailureDiagnostics(options.output_directory);
  if (selection.failure)
    return failed(*selection.failure);
  if (const auto failure = selection.sink->record(artifact))
    return failed(*failure);
  return {};
}

}  // namespace so101_gazebo_demo::pick_place::test
