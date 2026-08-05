#pragma once

#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

#include <moveit_msgs/action/move_group.hpp>
#include <moveit_msgs/msg/planning_scene.hpp>
#include <nlohmann/json.hpp>

#include "so101_gazebo_demo/pick_place/domain_types.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

namespace so101_gazebo_demo::pick_place
{

enum class RequestScopedGoalTerminal;

enum class PlanningFailureStage
{
  GOAL_ACCEPT_TIMEOUT,
  GOAL_REJECTED,
  RESULT_TIMEOUT,
  TRANSPORT_FAILURE,
  MISSING_RESULT,
  MOVEIT_ERROR,
  EMPTY_TRAJECTORY
};

struct PlanningSceneContactEvidence
{
  bool raw_collision{false};
  bool request_collision{false};
  std::map<std::string, std::size_t> raw_contacts;
  std::map<std::string, std::size_t> request_contacts;
};

struct PlanningFailureResultEvidence
{
  PlanningFailureStage stage;
  ActionResult original;
  std::optional<std::int8_t> transport_result_code;
  std::optional<std::int32_t> moveit_error_code;
  std::optional<double> planning_time;
  std::vector<std::string> trajectory_joint_names;
  std::size_t trajectory_points{0};
  std::optional<double> trajectory_duration_seconds;
  std::optional<bool> cancel_acknowledged;
  std::optional<RequestScopedGoalTerminal> cancel_terminal;
};

struct PlanningFailureArtifact
{
  std::int64_t captured_at_unix_ns;
  std::uint64_t process_sequence;
  std::string simulation_session_id;
  std::string configuration_fingerprint;
  Pose3d source_tcp_world;
  double world_z_delta_m;
  moveit_msgs::action::MoveGroup::Goal request;
  moveit_msgs::msg::PlanningScene observed_scene;
  PlanningSceneContactEvidence contacts;
  SO101Profile profile_identity;
  PlanningFailureResultEvidence result;
};

using PlanningDiagnosticsJson = nlohmann::ordered_json;

[[nodiscard]] PlanningDiagnosticsJson
canonicalMoveGroupGoalJson(const moveit_msgs::action::MoveGroup::Goal & goal);

[[nodiscard]] PlanningDiagnosticsJson
canonicalPlanningSceneJson(const moveit_msgs::msg::PlanningScene & scene);

[[nodiscard]] std::string replaySceneFingerprint(const moveit_msgs::msg::PlanningScene & scene);

[[nodiscard]] std::string planningDiagnosticsSha256(std::string_view bytes);

[[nodiscard]] std::variant<PlanningFailureArtifact, Failure>
loadPlanningFailureArtifact(const std::filesystem::path & artifact_path);

[[nodiscard]] std::variant<moveit_msgs::action::MoveGroup::Goal, Failure>
reconstructMoveGroupGoal(const PlanningDiagnosticsJson & artifact_document);

}  // namespace so101_gazebo_demo::pick_place
