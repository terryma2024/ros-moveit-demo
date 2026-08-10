#pragma once

#include <filesystem>
#include <memory>
#include <optional>
#include <string>

#include <rclcpp/node.hpp>

#include "so101_gazebo_demo/pick_place/domain_types.hpp"

namespace so101_gazebo_demo::pick_place::test
{

enum class PlanningFailureReplayMode
{
  OFFLINE,
  LIVE_PLAN_ONLY,
  CAPTURE_AND_INJECT_MOVEIT_ERROR
};

struct PlanningFailureReplayOptions
{
  PlanningFailureReplayMode mode{PlanningFailureReplayMode::OFFLINE};
  std::filesystem::path artifact;
  std::filesystem::path output_directory;
  std::string expected_session_id;
  std::string expected_fingerprint;
};

struct PlanningFailureReplayResult
{
  bool sent{false};
  std::optional<std::filesystem::path> output;
  std::optional<Failure> failure;
};

[[nodiscard]] PlanningFailureReplayResult
runPlanningFailureReplay(const PlanningFailureReplayOptions & options,
                         const std::shared_ptr<rclcpp::Node> & node = nullptr);

}  // namespace so101_gazebo_demo::pick_place::test
