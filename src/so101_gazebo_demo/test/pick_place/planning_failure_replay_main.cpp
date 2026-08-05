#include "planning_failure_replay.hpp"

#include <iostream>
#include <string>

#include <rclcpp/rclcpp.hpp>

namespace replay = so101_gazebo_demo::pick_place::test;

int main(int argc, char ** argv)
{
  replay::PlanningFailureReplayOptions options;
  for (int index = 1; index < argc; ++index) {
    const std::string argument = argv[index];
    if (argument == "--artifact" && index + 1 < argc)
      options.artifact = argv[++index];
    else if (argument == "--offline")
      options.mode = replay::PlanningFailureReplayMode::OFFLINE;
    else if (argument == "--live-plan-only")
      options.mode = replay::PlanningFailureReplayMode::LIVE_PLAN_ONLY;
    else if (argument == "--capture-current-and-inject" && index + 1 < argc &&
             std::string(argv[++index]) == "MOVEIT_ERROR")
      options.mode = replay::PlanningFailureReplayMode::CAPTURE_AND_INJECT_MOVEIT_ERROR;
    else if (argument == "--output-dir" && index + 1 < argc)
      options.output_directory = argv[++index];
    else if ((argument == "--session-id" || argument == "--expected-session-id") &&
             index + 1 < argc)
      options.expected_session_id = argv[++index];
    else if ((argument == "--fingerprint" || argument == "--expected-fingerprint") &&
             index + 1 < argc)
      options.expected_fingerprint = argv[++index];
    else
      return 2;
  }
  std::shared_ptr<rclcpp::Node> node;
  if (options.mode != replay::PlanningFailureReplayMode::OFFLINE) {
    rclcpp::init(argc, argv);
    node = std::make_shared<rclcpp::Node>("so101_planning_failure_replay");
  }
  const auto result = replay::runPlanningFailureReplay(options, node);
  if (rclcpp::ok())
    rclcpp::shutdown();
  if (result.failure) {
    std::cerr << result.failure->code << ": " << result.failure->message << '\n';
    return 1;
  }
  return 0;
}
