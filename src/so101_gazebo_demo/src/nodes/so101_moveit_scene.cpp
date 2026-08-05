#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <memory>
#include <optional>
#include <sstream>
#include <string>
#include <thread>

#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "so101_gazebo_demo/pick_place/moveit_scene_executor.hpp"
#include "so101_gazebo_demo/pick_place/so101_moveit_scene_policy.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

namespace
{
bool poseMatches(const pick_place::Pose3d & actual, const pick_place::Pose3d & expected)
{
  return pick_place::positionDistance(actual, expected) <= 0.002 &&
         pick_place::orientationDistance(actual, expected) <= 0.02;
}

std::string poseText(const std::optional<pick_place::Pose3d> & pose)
{
  if (!pose) {
    return "missing";
  }
  std::ostringstream stream;
  stream.precision(12);
  stream << pose->x << ',' << pose->y << ',' << pose->z << ',' << pose->qx << ',' << pose->qy << ','
         << pose->qz << ',' << pose->qw;
  return stream.str();
}

void printState(const pick_place::MoveItSceneState & state)
{
  std::ostringstream touch_links;
  for (std::size_t index = 0; index < state.touch_links.size(); ++index) {
    if (index != 0) {
      touch_links << ',';
    }
    touch_links << state.touch_links[index];
  }
  std::cout << std::boolalpha << "task_object_in_world=" << state.task_object_in_world
            << " task_object_attached=" << state.task_object_attached
            << " attached_link=" << (state.attached_link.empty() ? "-" : state.attached_link)
            << " touch_links=" << (state.touch_links.empty() ? "-" : touch_links.str())
            << " task_object_pose=" << poseText(state.task_object_world_pose)
            << " table_in_world=" << state.table_in_world
            << " table_pose=" << poseText(state.table_world_pose)
            << " pedestal_in_world=" << state.pedestal_in_world
            << " pedestal_pose=" << poseText(state.pedestal_world_pose) << '\n';
}

pick_place::ActionResult timedOut(std::string code, std::string message)
{
  return {pick_place::ActionStatus::TIMED_OUT,
          pick_place::Failure{pick_place::FailureCategory::MOVEIT_SCENE,
                              std::move(code),
                              std::move(message),
                              {}}};
}
}  // namespace

int main(int argc, char * argv[])
{
  if (argc == 2 && std::string(argv[1]) == "--help") {
    std::cout << "so101_moveit_scene {observe|upsert|attach|detach} [--ros-args ...]\n";
    return EXIT_SUCCESS;
  }
  if (argc < 2) {
    std::cerr << "so101_moveit_scene {observe|upsert|attach|detach} [--ros-args ...]\n";
    return EXIT_FAILURE;
  }
  const std::string operation(argv[1]);
  rclcpp::init(argc, argv);
  auto node = std::make_shared<rclcpp::Node>("so101_moveit_scene");
  const auto & profile = pick_place::SO101Profile::canonical();
  const auto timeout_seconds = node->declare_parameter<double>("timeout_seconds", 3.0);
  const auto poll_interval_seconds = node->declare_parameter<double>("poll_interval_seconds", 0.05);

  pick_place::ActionResult result;
  try {
    const pick_place::MoveItSceneGeometry geometry{profile.world_frame,
                                                   profile.table_object,
                                                   profile.table_size,
                                                   profile.pedestal_object,
                                                   profile.pedestal_size,
                                                   profile.task_object_id,
                                                   profile.task_object_height,
                                                   profile.task_object_outer_radius,
                                                   profile.task_object_wall_thickness,
                                                   profile.task_object_bottom_thickness,
                                                   profile.task_object_side_count};
    auto adapter =
      std::make_shared<pick_place::MoveItSceneAdapter>(node, profile.planning_group, geometry);
    const pick_place::MoveItAttachmentSpec attachment{profile.moveit_attach_link,
                                                      profile.moveit_touch_links};
    if (operation == "observe") {
      const auto state = adapter->observe();
      if (!state) {
        result = timedOut("MOVEIT_SCENE_OBSERVATION_FAILED", "Planning Scene query failed");
      } else {
        printState(*state);
        result = {pick_place::ActionStatus::SUCCEEDED, std::nullopt};
      }
    } else if (operation == "attach" || operation == "detach") {
      const auto state =
        operation == "attach" ? pick_place::State::ATTACH_MOVEIT : pick_place::State::DETACH_MOVEIT;
      const auto scene_operation = operation == "attach" ? pick_place::MoveItSceneOperation::ATTACH
                                                         : pick_place::MoveItSceneOperation::DETACH;
      pick_place::MoveItSceneExecutor executor(
        adapter,
        {state, scene_operation, false, profile.task_object_id, attachment, timeout_seconds,
         poll_interval_seconds},
        std::make_shared<pick_place::SO101MoveItScenePolicy>(profile.task_object_id, false));
      const pick_place::ExecutionContext context{state, pick_place::State::ERROR,
                                                 pick_place::WorldSnapshot{}, nullptr};
      result = executor.execute(context);
      if (result.status == pick_place::ActionStatus::SUCCEEDED) {
        const auto observed = adapter->observe();
        if (observed) {
          printState(*observed);
        }
      }
    } else if (operation == "upsert") {
      result = adapter->upsertTableWorldPose(profile.table_pose);
      if (result.status == pick_place::ActionStatus::SUCCEEDED) {
        result = adapter->upsertPedestalWorldPose(profile.pedestal_pose);
      }
      if (result.status == pick_place::ActionStatus::SUCCEEDED) {
        result = adapter->upsertTaskObjectWorldPose(profile.task_object_pose);
      }
      if (result.status == pick_place::ActionStatus::SUCCEEDED) {
        const auto deadline =
          std::chrono::steady_clock::now() + std::chrono::duration<double>(timeout_seconds);
        bool converged = false;
        while (std::chrono::steady_clock::now() < deadline) {
          const auto state = adapter->observe();
          if (state && !state->task_object_attached && state->task_object_in_world &&
              state->task_object_world_pose &&
              poseMatches(*state->task_object_world_pose, profile.task_object_pose) &&
              state->table_in_world && state->table_world_pose &&
              poseMatches(*state->table_world_pose, profile.table_pose) &&
              state->pedestal_in_world && state->pedestal_world_pose &&
              poseMatches(*state->pedestal_world_pose, profile.pedestal_pose)) {
            printState(*state);
            converged = true;
            break;
          }
          std::this_thread::sleep_for(std::chrono::duration<double>(poll_interval_seconds));
        }
        if (!converged) {
          result = timedOut("MOVEIT_SCENE_UPSERT_TIMEOUT",
                            "Planning Scene did not re-query canonical objects");
        }
      }
    } else {
      result = {pick_place::ActionStatus::NOT_SUPPORTED,
                pick_place::Failure{pick_place::FailureCategory::CONFIGURATION,
                                    "MOVEIT_SCENE_OPERATION_INVALID",
                                    "Unknown scene operation",
                                    {}}};
    }

    if (result.status != pick_place::ActionStatus::SUCCEEDED) {
      const auto code = result.failure ? result.failure->code : "MOVEIT_SCENE_FAILED";
      const auto message = result.failure ? result.failure->message : "MoveIt scene command failed";
      RCLCPP_ERROR(node->get_logger(), "%s: %s", code.c_str(), message.c_str());
      rclcpp::shutdown();
      return EXIT_FAILURE;
    }
  } catch (const std::exception & error) {
    RCLCPP_ERROR(node->get_logger(), "MoveIt scene exception: %s", error.what());
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  rclcpp::shutdown();
  return EXIT_SUCCESS;
}
