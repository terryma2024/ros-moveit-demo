#include <chrono>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <memory>
#include <optional>
#include <string>

#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/common_resume_validator.hpp"
#include "so101_gazebo_demo/pick_place/file_checkpoint_store.hpp"
#include "so101_gazebo_demo/pick_place/follow_joint_trajectory_gripper_adapter.hpp"
#include "so101_gazebo_demo/pick_place/gazebo_attachment_executor.hpp"
#include "so101_gazebo_demo/pick_place/gazebo_world_observer.hpp"
#include "so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp"
#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "so101_gazebo_demo/pick_place/node_spinner.hpp"
#include "so101_gazebo_demo/pick_place/pick_place_runtime.hpp"
#include "so101_gazebo_demo/pick_place/runner.hpp"
#include "so101_gazebo_demo/pick_place/simulation_session_id.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

struct CliOptions
{
  spp::RunRequest request;
  std::filesystem::path checkpoint_path{"/tmp/so101_pick_place_checkpoint.json"};
  std::string simulation_session_id;
};

bool booleanValue(const std::string & value, bool & result)
{
  if (value == "true" || value == "1") {
    result = true;
    return true;
  }
  if (value == "false" || value == "0") {
    result = false;
    return true;
  }
  return false;
}

std::optional<CliOptions> parse(int argc, char ** argv)
{
  CliOptions options;
  const auto arguments = rclcpp::remove_ros_arguments(argc, argv);
  for (std::size_t i = 1; i < arguments.size(); ++i) {
    const std::string & argument = arguments[i];
    if (argument == "--mode" && i + 1 < arguments.size()) {
      const auto mode = spp::runModeFromString(arguments[++i]);
      if (!mode) return std::nullopt;
      options.request.mode = *mode;
    } else if (argument == "--fail-at" && i + 1 < arguments.size()) {
      const auto state = spp::stateFromString(arguments[++i]);
      if (!state) return std::nullopt;
      options.request.fail_at = *state;
    } else if (argument == "--stop-after" && i + 1 < arguments.size()) {
      const std::string value = arguments[++i];
      if (!value.empty()) {
        const auto state = spp::stateFromString(value);
        if (!state) return std::nullopt;
        options.request.stop_after = *state;
      }
    } else if (argument == "--resume") {
      options.request.resume = true;
      if (i + 1 < arguments.size()) {
        bool value = false;
        if (booleanValue(arguments[i + 1], value)) {
          options.request.resume = value;
          ++i;
        }
      }
    } else if (argument == "--checkpoint" && i + 1 < arguments.size()) {
      options.checkpoint_path = arguments[++i];
      if (options.checkpoint_path.empty()) return std::nullopt;
    } else if (argument == "--session-id" && i + 1 < arguments.size()) {
      options.simulation_session_id = arguments[++i];
    } else {
      return std::nullopt;
    }
  }
  return options;
}

void print(const spp::RunResult & result)
{
  std::cout << "status=" << spp::toString(result.status) << "\ntrace=";
  for (std::size_t i = 0; i < result.state_trace.size(); ++i) {
    std::cout << (i ? " -> " : "") << spp::toString(result.state_trace[i]);
  }
  std::cout << '\n';
  if (result.failure) std::cout << spp::formatFailure(*result.failure) << '\n';
}

int runProduction(const CliOptions & options, int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  int exit_code = 1;
  try {
    {
      rclcpp::NodeOptions node_options;
      node_options.parameter_overrides({rclcpp::Parameter("use_sim_time", true)});
      auto node = std::make_shared<rclcpp::Node>("so101_pick_place_state_machine", node_options);
      spp::NodeSpinner spinner(node);
      const auto profile = spp::SO101Profile::canonical();
      const auto milliseconds = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
          std::chrono::system_clock::now().time_since_epoch()).count());
      auto session = spp::resolveSimulationSessionId(
        options.request.mode, options.request.resume, options.simulation_session_id, milliseconds);
      if (!session.value) {
        if (options.request.mode == spp::RunMode::PLAN_ONLY && !options.request.resume) {
          session.value = "plan-only-" + std::to_string(milliseconds);
        } else {
          std::cerr << session.error << '\n';
          rclcpp::shutdown();
          return 2;
        }
      }

      auto boundary = std::make_shared<spp::MoveItJointPlanningBoundary>(node, profile);
      auto motion = std::make_shared<spp::ProfiledJointMotionAdapter>(boundary, boundary, profile);
      auto policy = std::make_shared<spp::SO101FixedMotionTargetPolicy>(profile);
      auto gripper_client =
        std::make_shared<spp::RosTrajectoryActionClient>(node, profile.gripper_action);
      auto gripper = std::make_shared<spp::FollowJointTrajectoryGripperAdapter>(
        gripper_client, 1.0, 8.0);
      auto scene = std::make_shared<spp::MoveItSceneAdapter>(
        node, profile.planning_group,
        spp::MoveItSceneGeometry{profile.world_frame, profile.table_object,
                                profile.table_size, profile.pedestal_object,
                                profile.pedestal_size, profile.coke_model,
                                profile.coke_height, profile.coke_radius});
      auto gazebo_attach = std::make_shared<spp::GazeboAttachmentExecutor>(
        spp::State::ATTACH_GAZEBO, true, profile.attach_topic, profile.detach_topic,
        profile.attachment_event_topic, 3.0, 0.05, false);
      auto gazebo_detach = std::make_shared<spp::GazeboAttachmentExecutor>(
        spp::State::DETACH_GAZEBO, false, profile.attach_topic, profile.detach_topic,
        profile.attachment_event_topic, 3.0, 0.05, false);
      auto recovery_gazebo_detach = std::make_shared<spp::GazeboAttachmentExecutor>(
        spp::State::RECOVER_DETACH_GAZEBO, false, profile.attach_topic,
        profile.detach_topic, profile.attachment_event_topic, 3.0, 0.05, true);

      auto moveit_observer = std::make_shared<spp::SO101MoveItWorldObserver>(boundary, profile);
      spp::GazeboWorldObserver observer(
        *moveit_observer, profile.gazebo_world, profile.coke_model,
        profile.attachment_state_topic, *session.value, 2.0, 3, 0.02,
        profile.coke_position_drift_tolerance,
        profile.coke_orientation_drift_tolerance_rad, true);
      spp::FileCheckpointStore checkpoint(options.checkpoint_path);
      spp::CommonResumeValidator resume(policy->version(), *session.value);

      spp::SO101PickPlaceRuntimeDependencies dependencies;
      dependencies.gripper = gripper;
      dependencies.moveit_scene = scene;
      dependencies.gazebo_attach = gazebo_attach;
      dependencies.gazebo_detach = gazebo_detach;
      dependencies.recovery_gazebo_detach = recovery_gazebo_detach;
      dependencies.motion_policy = policy;
      dependencies.motion = motion;
      const auto runtime = spp::makeSO101PickPlaceRuntimeRegistries(dependencies);
      if (!runtime.execution_safe) {
        const auto failure = runtime.configuration_failure.value_or(
          spp::Failure{spp::FailureCategory::CONFIGURATION, "RUNTIME_UNSAFE",
                       "Production runtime registry is incomplete", {}});
        print({spp::RunStatus::ERROR, spp::State::ERROR, std::nullopt, failure, 0, {}});
        exit_code = 1;
      } else {
        spp::StateMachineRunner runner(
          runtime.actions, runtime.contracts, &observer, &checkpoint, &resume,
          &runtime.plan_validators, runtime.recovery_policy.get());
        const auto result = runner.run(options.request);
        print(result);
        exit_code = result.status == spp::RunStatus::ERROR ? 1 : 0;
      }
    }
  } catch (const std::exception & error) {
    std::cerr << "runtime assembly failed: " << error.what() << '\n';
    exit_code = 1;
  }
  rclcpp::shutdown();
  return exit_code;
}

}  // namespace

int main(int argc, char ** argv)
{
  const auto options = parse(argc, argv);
  if (!options) {
    std::cerr << "usage: pick_place_state_machine [--mode dry_run|plan_only|execute] "
                 "[--fail-at STATE] [--stop-after STATE] [--resume [true|false]] "
                 "[--checkpoint PATH] [--session-id ID]\n";
    return 2;
  }
  if (options->request.mode == spp::RunMode::DRY_RUN) {
    spp::StateMachineRunner runner;
    const auto result = runner.run(options->request);
    print(result);
    return result.status == spp::RunStatus::ERROR ? 1 : 0;
  }
  return runProduction(*options, argc, argv);
}
