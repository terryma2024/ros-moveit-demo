#include <chrono>
#include <cstdlib>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <Eigen/Geometry>
#include <rclcpp/executors/single_threaded_executor.hpp>
#include <rclcpp/rclcpp.hpp>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include "panda_gazebo_demo/pick_place/file_checkpoint_store.hpp"
#include "panda_gazebo_demo/pick_place/gazebo_attachment_executor.hpp"
#include "panda_gazebo_demo/pick_place/panda_attachment_convergence_policy.hpp"
#include "panda_gazebo_demo/pick_place/gazebo_world_observer.hpp"
#include "panda_gazebo_demo/pick_place/gripper_command_adapter.hpp"
#include "panda_gazebo_demo/pick_place/moveit_motion_adapter.hpp"
#include "panda_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "panda_gazebo_demo/pick_place/pick_place_runtime.hpp"
#include "panda_gazebo_demo/pick_place/common_resume_validator.hpp"
#include "panda_gazebo_demo/pick_place/runner.hpp"
#include "panda_gazebo_demo/pick_place/runtime_parameters.hpp"
#include "panda_gazebo_demo/pick_place/simulation_session_id.hpp"

namespace pick_place = panda_gazebo_demo::pick_place;

namespace
{

class NodeSpinner
{
public:
  explicit NodeSpinner(const std::shared_ptr<rclcpp::Node> & node) : node_(node)
  {
    executor_.add_node(node_);
    thread_ = std::thread([this]() { executor_.spin(); });
  }

  ~NodeSpinner()
  {
    executor_.cancel();
    if (thread_.joinable()) {
      thread_.join();
    }
    executor_.remove_node(node_);
  }

private:
  std::shared_ptr<rclcpp::Node> node_;
  rclcpp::executors::SingleThreadedExecutor executor_;
  std::thread thread_;
};

class RosExecutionObservationLogger final : public pick_place::IExecutionObservationSink
{
public:
  explicit RosExecutionObservationLogger(rclcpp::Logger logger) : logger_(std::move(logger)) {}

  void record(pick_place::State state, const pick_place::WorldSnapshot & before,
              const pick_place::WorldSnapshot & after) override
  {
    const pick_place::TransitionTable transitions;
    RCLCPP_INFO(
      logger_, "STATE_TRANSITION state=%s next_state=%s", pick_place::toString(state),
      pick_place::toString(transitions.resolve(state, pick_place::ActionStatus::SUCCEEDED)));
    logPose("COKE_POSE_BEFORE", state, before.gazebo_task_object_pose_world);
    logPose("COKE_POSE_AFTER", state, after.gazebo_task_object_pose_world);
    logGripper("BEFORE", state, before);
    logGripper("AFTER", state, after);
    RCLCPP_INFO(logger_,
                "ATTACHMENT_EVIDENCE state=%s GAZEBO_ATTACHED_BEFORE=%d GAZEBO_ATTACHED_AFTER=%d "
                "MOVEIT_ATTACHED_BEFORE=%d MOVEIT_ATTACHED_AFTER=%d",
                pick_place::toString(state), valueOrUnknown(before.gazebo_task_object_attached),
                valueOrUnknown(after.gazebo_task_object_attached),
                valueOrUnknown(before.moveit_task_object_attached),
                valueOrUnknown(after.moveit_task_object_attached));
    RCLCPP_INFO(
      logger_,
      "MOVEIT_MEMBERSHIP state=%s COKE_IN_WORLD_BEFORE=%d COKE_IN_WORLD_AFTER=%d "
      "ATTACHED_LINK=%s TOUCH_LINK_COUNT=%zu",
      pick_place::toString(state), before.moveit_world_object_poses.count("coke") == 1 ? 1 : 0,
      after.moveit_world_object_poses.count("coke") == 1 ? 1 : 0,
      after.moveit_task_object_attached_link ? after.moveit_task_object_attached_link->c_str() : "",
      after.moveit_task_object_touch_links.size());
    if (before.gazebo_task_object_pose_world && after.gazebo_task_object_pose_world) {
      RCLCPP_INFO(logger_, "COKE_DRIFT state=%s position=%.6f orientation_rad=%.6f",
                  pick_place::toString(state),
                  pick_place::positionDistance(*before.gazebo_task_object_pose_world,
                                               *after.gazebo_task_object_pose_world),
                  pick_place::orientationDistance(*before.gazebo_task_object_pose_world,
                                                  *after.gazebo_task_object_pose_world));
      const auto before_relative =
        pick_place::relativePose(before.tcp_pose_world, *before.gazebo_task_object_pose_world);
      const auto after_relative =
        pick_place::relativePose(after.tcp_pose_world, *after.gazebo_task_object_pose_world);
      if (before_relative && after_relative) {
        RCLCPP_INFO(logger_,
                    "TCP_COKE_RELATIVE_POSE_ERROR state=%s position=%.6f orientation_rad=%.6f",
                    pick_place::toString(state),
                    pick_place::positionDistance(*before_relative, *after_relative),
                    pick_place::orientationDistance(*before_relative, *after_relative));
      } else {
        RCLCPP_INFO(logger_, "TCP_COKE_RELATIVE_POSE_ERROR state=%s unavailable",
                    pick_place::toString(state));
      }
    } else {
      RCLCPP_INFO(logger_, "COKE_DRIFT state=%s unavailable", pick_place::toString(state));
      RCLCPP_INFO(logger_, "TCP_COKE_RELATIVE_POSE_ERROR state=%s unavailable",
                  pick_place::toString(state));
    }
    const auto moveit_coke = after.moveit_world_object_poses.find("coke");
    if (after.gazebo_task_object_pose_world &&
        moveit_coke != after.moveit_world_object_poses.end()) {
      RCLCPP_INFO(
        logger_, "CROSS_WORLD_COKE_POSE_ERROR state=%s position=%.6f orientation_rad=%.6f",
        pick_place::toString(state),
        pick_place::positionDistance(*after.gazebo_task_object_pose_world, moveit_coke->second),
        pick_place::orientationDistance(*after.gazebo_task_object_pose_world, moveit_coke->second));
    } else {
      RCLCPP_INFO(logger_, "CROSS_WORLD_COKE_POSE_ERROR state=%s unavailable",
                  pick_place::toString(state));
    }
  }

private:
  static int valueOrUnknown(const std::optional<bool> & value)
  {
    return value ? (*value ? 1 : 0) : -1;
  }

  void logPose(const char * label, pick_place::State state,
               const std::optional<pick_place::Pose3d> & pose) const
  {
    if (!pose) {
      RCLCPP_INFO(logger_, "%s state=%s unavailable", label, pick_place::toString(state));
      return;
    }
    const Eigen::Quaterniond orientation(pose->qw, pose->qx, pose->qy, pose->qz);
    const auto rpy = orientation.normalized().toRotationMatrix().eulerAngles(0, 1, 2);
    RCLCPP_INFO(logger_, "%s state=%s x=%.6f y=%.6f z=%.6f roll=%.6f pitch=%.6f yaw=%.6f", label,
                pick_place::toString(state), pose->x, pose->y, pose->z, rpy.x(), rpy.y(), rpy.z());
  }

  void logGripper(const char * label, pick_place::State state,
                  const pick_place::WorldSnapshot & snapshot) const
  {
    const auto finger1_position = snapshot.joint_positions.find("panda_finger_joint1");
    const auto finger2_position = snapshot.joint_positions.find("panda_finger_joint2");
    const auto finger1_velocity = snapshot.joint_velocities.find("panda_finger_joint1");
    const auto finger2_velocity = snapshot.joint_velocities.find("panda_finger_joint2");
    if (finger1_position == snapshot.joint_positions.end() ||
        finger2_position == snapshot.joint_positions.end() ||
        finger1_velocity == snapshot.joint_velocities.end() ||
        finger2_velocity == snapshot.joint_velocities.end()) {
      RCLCPP_INFO(logger_, "%s state=%s unavailable", label, pick_place::toString(state));
      return;
    }
    RCLCPP_INFO(logger_,
                "GRIPPER_EVIDENCE state=%s sample=%s FINGER1_POSITION=%.6f FINGER2_POSITION=%.6f "
                "FINGER1_VELOCITY=%.6f FINGER2_VELOCITY=%.6f",
                pick_place::toString(state), label, finger1_position->second,
                finger2_position->second, finger1_velocity->second, finger2_velocity->second);
  }

  rclcpp::Logger logger_;
};

class LoggingCheckpointStore final : public pick_place::ICheckpointStore
{
public:
  LoggingCheckpointStore(std::filesystem::path path, rclcpp::Logger logger) :
      delegate_(std::move(path)), logger_(std::move(logger))
  {
  }

  std::optional<pick_place::Failure> commit(const pick_place::Checkpoint & checkpoint) override
  {
    const auto failure = delegate_.commit(checkpoint);
    if (!failure) {
      RCLCPP_INFO(logger_, "CHECKPOINT_PHASE=%s CHECKPOINT_SEQUENCE=%lu NEXT_STATE=%s",
                  checkpoint.phase == pick_place::CheckpointPhase::FORWARD ? "FORWARD" : "RECOVERY",
                  checkpoint.sequence, pick_place::toString(checkpoint.next_state));
    }
    return failure;
  }

  pick_place::CheckpointLoadResult loadLatestCompatible() override
  {
    const auto result = delegate_.loadLatestCompatible();
    if (result.checkpoint) {
      RCLCPP_INFO(
        logger_, "CHECKPOINT_PHASE=%s CHECKPOINT_SEQUENCE=%lu NEXT_STATE=%s resume_load=1",
        result.checkpoint->phase == pick_place::CheckpointPhase::FORWARD ? "FORWARD" : "RECOVERY",
        result.checkpoint->sequence, pick_place::toString(result.checkpoint->next_state));
    }
    return result;
  }

private:
  pick_place::FileCheckpointStore delegate_;
  rclcpp::Logger logger_;
};

template <typename T>
T parameterOrDeclare(const std::shared_ptr<rclcpp::Node> & node, const std::string & name,
                     const T & default_value)
{
  if (!node->has_parameter(name)) {
    node->declare_parameter<T>(name, default_value);
  }
  return node->get_parameter(name).get_value<T>();
}

enum class StateParameterScope
{
  FORWARD_ACTION,
  ANY_ACTION,
};

std::optional<pick_place::State> optionalStateParameter(const std::shared_ptr<rclcpp::Node> & node,
                                                        const std::string & name,
                                                        StateParameterScope scope,
                                                        const rclcpp::Logger & logger)
{
  const auto value = parameterOrDeclare(node, name, std::string(""));
  if (value.empty()) {
    return std::nullopt;
  }
  const auto state = pick_place::stateFromString(value);
  const bool valid_action = state && pick_place::isAction(*state);
  const bool valid_scope = valid_action && (scope == StateParameterScope::ANY_ACTION ||
                                            pick_place::isForwardAction(*state));
  if (!valid_scope) {
    const char * expected = scope == StateParameterScope::ANY_ACTION ? "a non-terminal action State"
                                                                     : "a forward action State";
    RCLCPP_ERROR(logger, "%s must name %s; got '%s'", name.c_str(), expected, value.c_str());
    return std::nullopt;
  }
  return state;
}

bool successful(pick_place::RunStatus status)
{
  return status == pick_place::RunStatus::DONE ||
         status == pick_place::RunStatus::PLAN_ONLY_COMPLETE ||
         status == pick_place::RunStatus::CHECKPOINT_COMPLETE;
}

}  // namespace

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  const auto node = std::make_shared<rclcpp::Node>(
    "pick_place_state_machine", rclcpp::NodeOptions()
                                  .automatically_declare_parameters_from_overrides(true)
                                  .append_parameter_override("use_sim_time", true));
  const auto logger = node->get_logger();

  const auto mode_value = parameterOrDeclare(node, "mode", std::string(""));
  const auto mode = pick_place::runModeFromString(mode_value);
  if (!mode) {
    RCLCPP_ERROR(logger, "Unsupported mode '%s'. Use dry_run, plan_only, or execute",
                 mode_value.c_str());
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  const auto fail_at =
    optionalStateParameter(node, "fail_at", StateParameterScope::FORWARD_ACTION, logger);
  const auto fail_at_value = node->get_parameter("fail_at").get_value<std::string>();
  const auto stop_after =
    optionalStateParameter(node, "stop_after", StateParameterScope::ANY_ACTION, logger);
  const auto stop_after_value = node->get_parameter("stop_after").get_value<std::string>();
  if ((!fail_at_value.empty() && !fail_at) || (!stop_after_value.empty() && !stop_after)) {
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  const auto resume = parameterOrDeclare(node, "resume", false);
  if (resume && *mode == pick_place::RunMode::DRY_RUN) {
    RCLCPP_ERROR(logger, "resume is supported only in plan_only and execute modes");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }
  pick_place::PickPlaceParameters parameters;
  parameters.planning_group = parameterOrDeclare(node, "planning_group", parameters.planning_group);
  parameters.tcp_link = parameterOrDeclare(node, "tcp_link", parameters.tcp_link);
  parameters.required_world_objects =
    parameterOrDeclare(node, "required_world_objects", parameters.required_world_objects);
  parameters.velocity_scaling =
    parameterOrDeclare(node, "velocity_scaling", parameters.velocity_scaling);
  parameters.acceleration_scaling =
    parameterOrDeclare(node, "acceleration_scaling", parameters.acceleration_scaling);
  parameters.cartesian_eef_step =
    parameterOrDeclare(node, "cartesian_eef_step", parameters.cartesian_eef_step);
  parameters.cartesian_min_fraction =
    parameterOrDeclare(node, "cartesian_min_fraction", parameters.cartesian_min_fraction);
  parameters.joint_jump_threshold =
    parameterOrDeclare(node, "joint_jump_threshold", parameters.joint_jump_threshold);
  parameters.motion_start_joint_tolerance = parameterOrDeclare(
    node, "motion_start_joint_tolerance", parameters.motion_start_joint_tolerance);
  parameters.ready_named_target =
    parameterOrDeclare(node, "ready_named_target", parameters.ready_named_target);
  parameters.ready_joint_tolerance =
    parameterOrDeclare(node, "ready_joint_tolerance", parameters.ready_joint_tolerance);
  parameters.tcp_position_tolerance =
    parameterOrDeclare(node, "tcp_position_tolerance", parameters.tcp_position_tolerance);
  parameters.tcp_orientation_tolerance_rad = parameterOrDeclare(
    node, "tcp_orientation_tolerance_rad", parameters.tcp_orientation_tolerance_rad);
  parameters.coke_position_tolerance =
    parameterOrDeclare(node, "coke_position_tolerance", parameters.coke_position_tolerance);
  parameters.coke_orientation_tolerance_rad = parameterOrDeclare(
    node, "coke_orientation_tolerance_rad", parameters.coke_orientation_tolerance_rad);
  parameters.gripper_open_position =
    parameterOrDeclare(node, "gripper_open_position", parameters.gripper_open_position);
  parameters.gripper_open_min_position =
    parameterOrDeclare(node, "gripper_open_min_position", parameters.gripper_open_min_position);
  parameters.gripper_close_position =
    parameterOrDeclare(node, "gripper_close_position", parameters.gripper_close_position);
  parameters.gripper_close_tolerance =
    parameterOrDeclare(node, "gripper_close_tolerance", parameters.gripper_close_tolerance);
  parameters.gripper_grasp_min_position =
    parameterOrDeclare(node, "gripper_grasp_min_position", parameters.gripper_grasp_min_position);
  parameters.gripper_grasp_max_position =
    parameterOrDeclare(node, "gripper_grasp_max_position", parameters.gripper_grasp_max_position);
  parameters.gripper_symmetry_tolerance =
    parameterOrDeclare(node, "gripper_symmetry_tolerance", parameters.gripper_symmetry_tolerance);
  parameters.joint_velocity_tolerance =
    parameterOrDeclare(node, "joint_velocity_tolerance", parameters.joint_velocity_tolerance);
  parameters.gripper_max_effort =
    parameterOrDeclare(node, "gripper_max_effort", parameters.gripper_max_effort);
  parameters.gripper_action_timeout_seconds = parameterOrDeclare(
    node, "gripper_action_timeout_seconds", parameters.gripper_action_timeout_seconds);
  parameters.attachment_timeout_seconds =
    parameterOrDeclare(node, "attachment_timeout_seconds", parameters.attachment_timeout_seconds);
  parameters.planning_scene_timeout_seconds = parameterOrDeclare(
    node, "planning_scene_timeout_seconds", parameters.planning_scene_timeout_seconds);
  parameters.state_poll_interval_seconds =
    parameterOrDeclare(node, "state_poll_interval_seconds", parameters.state_poll_interval_seconds);
  parameters.gazebo_observation_max_age_seconds = parameterOrDeclare(
    node, "gazebo_observation_max_age_seconds", parameters.gazebo_observation_max_age_seconds);
  const auto coke_settle_samples = parameterOrDeclare<std::int64_t>(
    node, "coke_settle_samples", static_cast<std::int64_t>(parameters.coke_settle_samples));
  parameters.coke_settle_interval_seconds = parameterOrDeclare(
    node, "coke_settle_interval_seconds", parameters.coke_settle_interval_seconds);
  parameters.coke_settle_position_tolerance = parameterOrDeclare(
    node, "coke_settle_position_tolerance", parameters.coke_settle_position_tolerance);
  parameters.coke_settle_orientation_tolerance_rad =
    parameterOrDeclare(node, "coke_settle_orientation_tolerance_rad",
                       parameters.coke_settle_orientation_tolerance_rad);
  parameters.recovery_safe_height =
    parameterOrDeclare(node, "recovery_safe_height", parameters.recovery_safe_height);
  parameters.gazebo_world_name =
    parameterOrDeclare(node, "gazebo_world_name", parameters.gazebo_world_name);
  parameters.gazebo_coke_model =
    parameterOrDeclare(node, "gazebo_coke_model", parameters.gazebo_coke_model);
  parameters.gazebo_attach_topic =
    parameterOrDeclare(node, "gazebo_attach_topic", parameters.gazebo_attach_topic);
  parameters.gazebo_detach_topic =
    parameterOrDeclare(node, "gazebo_detach_topic", parameters.gazebo_detach_topic);
  parameters.gazebo_attachment_event_topic = parameterOrDeclare(
    node, "gazebo_attachment_event_topic", parameters.gazebo_attachment_event_topic);
  parameters.gazebo_attachment_topic =
    parameterOrDeclare(node, "gazebo_attachment_topic", parameters.gazebo_attachment_topic);
  parameters.gazebo_coke_initially_detached = parameterOrDeclare(
    node, "gazebo_coke_initially_detached", parameters.gazebo_coke_initially_detached);
  parameters.gripper_action_name =
    parameterOrDeclare(node, "gripper_action_name", parameters.gripper_action_name);
  const auto max_state_transitions = parameterOrDeclare<std::int64_t>(
    node, "max_state_transitions", static_cast<std::int64_t>(parameters.max_state_transitions));
  const auto checkpoint_path = parameterOrDeclare(
    node, "checkpoint_path", std::string("/tmp/panda_pick_place_checkpoint.json"));
  const auto configured_simulation_session_id =
    parameterOrDeclare(node, "simulation_session_id", std::string(""));
  const auto unix_timestamp_milliseconds =
    static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
                                 std::chrono::system_clock::now().time_since_epoch())
                                 .count());
  const auto session_id = pick_place::resolveSimulationSessionId(
    *mode, resume, configured_simulation_session_id, unix_timestamp_milliseconds);
  if (!session_id.error.empty()) {
    RCLCPP_ERROR(logger, "%s", session_id.error.c_str());
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }
  const auto simulation_session_id = session_id.value.value_or("");
  if (session_id.value) {
    RCLCPP_INFO(logger, "SIMULATION_SESSION_ID=%s", simulation_session_id.c_str());
  }
  if (coke_settle_samples < 2 || max_state_transitions <= 0) {
    RCLCPP_ERROR(logger, "coke_settle_samples and max_state_transitions are outside safe ranges");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }
  parameters.coke_settle_samples = static_cast<std::size_t>(coke_settle_samples);
  parameters.max_state_transitions = static_cast<std::uint64_t>(max_state_transitions);
  if (const auto invalid_parameters = pick_place::validatePickPlaceParameters(parameters)) {
    RCLCPP_ERROR(logger, "%s: %s", invalid_parameters->code.c_str(),
                 invalid_parameters->message.c_str());
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  const auto target_policy =
    std::make_shared<pick_place::FixedPickPlaceTargetPolicy>(parameters.recovery_safe_height);
  const pick_place::GripperLimits gripper_limits{
    parameters.gripper_open_min_position, parameters.gripper_grasp_min_position,
    parameters.gripper_grasp_max_position, parameters.gripper_symmetry_tolerance,
    parameters.joint_velocity_tolerance};
  const pick_place::FixedRecoveryPolicy recovery_policy(
    target_policy, parameters.tcp_position_tolerance, parameters.tcp_orientation_tolerance_rad,
    parameters.coke_position_tolerance, parameters.coke_orientation_tolerance_rad, gripper_limits);
  pick_place::PickPlaceRuntimeRegistries runtime;
  std::shared_ptr<pick_place::MoveItMotionAdapter> motion_adapter;
  if (*mode == pick_place::RunMode::PLAN_ONLY || *mode == pick_place::RunMode::EXECUTE) {
    motion_adapter = std::make_shared<pick_place::MoveItMotionAdapter>(
      node, parameters.planning_group, parameters.tcp_link, parameters.required_world_objects,
      parameters.velocity_scaling, parameters.acceleration_scaling, parameters.cartesian_eef_step,
      parameters.motion_start_joint_tolerance, parameters.joint_velocity_tolerance, gripper_limits);
    pick_place::PickPlaceRuntimeDependencies dependencies;
    dependencies.motion = motion_adapter;
    dependencies.observer = motion_adapter;
    if (*mode == pick_place::RunMode::EXECUTE) {
      const auto attachment_convergence_policy =
        std::make_shared<pick_place::PandaAttachmentConvergencePolicy>(gripper_limits);
      dependencies.gripper = std::make_shared<pick_place::GripperCommandAdapter>(
        node, parameters.gripper_action_name, parameters.gripper_action_timeout_seconds);
      dependencies.moveit_scene =
        std::make_shared<pick_place::MoveItSceneAdapter>(node, parameters.planning_group);
      dependencies.gazebo_attach = std::make_shared<pick_place::GazeboAttachmentExecutor>(
        pick_place::State::ATTACH_GAZEBO, true, parameters.gazebo_attach_topic,
        parameters.gazebo_detach_topic, parameters.gazebo_attachment_topic,
        parameters.attachment_timeout_seconds, parameters.state_poll_interval_seconds, false,
        attachment_convergence_policy);
      dependencies.gazebo_detach = std::make_shared<pick_place::GazeboAttachmentExecutor>(
        pick_place::State::DETACH_GAZEBO, false, parameters.gazebo_attach_topic,
        parameters.gazebo_detach_topic, parameters.gazebo_attachment_topic,
        parameters.attachment_timeout_seconds, parameters.state_poll_interval_seconds, false,
        attachment_convergence_policy);
      dependencies.recovery_gazebo_detach = std::make_shared<pick_place::GazeboAttachmentExecutor>(
        pick_place::State::RECOVER_DETACH_GAZEBO, false, parameters.gazebo_attach_topic,
        parameters.gazebo_detach_topic, parameters.gazebo_attachment_topic,
        parameters.attachment_timeout_seconds, parameters.state_poll_interval_seconds, true,
        attachment_convergence_policy);
    }
    pick_place::PickPlaceRuntimeConfig runtime_config;
    const auto ready_joints =
      motion_adapter->namedTargetJointPositions(parameters.ready_named_target);
    if (!ready_joints) {
      RCLCPP_ERROR(logger, "NAMED_TARGET_UNAVAILABLE: %s", parameters.ready_named_target.c_str());
      rclcpp::shutdown();
      return EXIT_FAILURE;
    }
    runtime_config.target_policy = target_policy;
    runtime_config.required_world_objects = parameters.required_world_objects;
    runtime_config.motion_plan_limits = {
      parameters.cartesian_min_fraction,      parameters.joint_jump_threshold,
      parameters.tcp_position_tolerance,      parameters.tcp_orientation_tolerance_rad,
      parameters.tcp_position_tolerance,      parameters.tcp_orientation_tolerance_rad,
      parameters.coke_position_tolerance,     parameters.coke_orientation_tolerance_rad,
      parameters.motion_start_joint_tolerance};
    runtime_config.gripper = gripper_limits;
    runtime_config.contract.tcp_position_tolerance = parameters.tcp_position_tolerance;
    runtime_config.contract.tcp_orientation_tolerance_rad =
      parameters.tcp_orientation_tolerance_rad;
    runtime_config.contract.coke_position_tolerance = parameters.coke_position_tolerance;
    runtime_config.contract.coke_orientation_tolerance_rad =
      parameters.coke_orientation_tolerance_rad;
    runtime_config.contract.carried_relative_position_tolerance =
      parameters.coke_position_tolerance;
    runtime_config.contract.carried_relative_orientation_tolerance_rad =
      parameters.coke_orientation_tolerance_rad;
    runtime_config.contract.gripper = runtime_config.gripper;
    runtime_config.gripper_open_position = parameters.gripper_open_position;
    runtime_config.gripper_close_position = parameters.gripper_close_position;
    runtime_config.gripper_close_tolerance = parameters.gripper_close_tolerance;
    runtime_config.gripper_max_effort = parameters.gripper_max_effort;
    runtime_config.planning_scene_timeout_seconds = parameters.planning_scene_timeout_seconds;
    runtime_config.state_poll_interval_seconds = parameters.state_poll_interval_seconds;
    runtime_config.ready_named_target = parameters.ready_named_target;
    runtime_config.ready_joint_positions = *ready_joints;
    runtime_config.ready_joint_tolerance = parameters.ready_joint_tolerance;
    runtime_config.contract.ready_joint_positions = runtime_config.ready_joint_positions;
    runtime_config.contract.ready_joint_tolerance = runtime_config.ready_joint_tolerance;
    runtime_config.contract.gripper_close_position = runtime_config.gripper_close_position;
    runtime_config.contract.gripper_close_tolerance = runtime_config.gripper_close_tolerance;
    runtime = pick_place::makePickPlaceRuntimeRegistries(dependencies, std::move(runtime_config));
  }

  std::unique_ptr<LoggingCheckpointStore> checkpoint_store;
  std::unique_ptr<pick_place::GazeboWorldObserver> world_observer;
  std::unique_ptr<pick_place::CommonResumeValidator> common_resume_validator;
  if (*mode == pick_place::RunMode::EXECUTE || resume) {
    checkpoint_store = std::make_unique<LoggingCheckpointStore>(checkpoint_path, logger);
    world_observer = std::make_unique<pick_place::GazeboWorldObserver>(
      *motion_adapter, parameters.gazebo_world_name, parameters.gazebo_coke_model,
      parameters.gazebo_attachment_topic, simulation_session_id,
      parameters.gazebo_observation_max_age_seconds, parameters.coke_settle_samples,
      parameters.coke_settle_interval_seconds, parameters.coke_settle_position_tolerance,
      parameters.coke_settle_orientation_tolerance_rad, parameters.gazebo_coke_initially_detached);
    common_resume_validator = std::make_unique<pick_place::CommonResumeValidator>(
      pick_place::pickPlaceConfigurationHash(parameters, target_policy->configurationSignature()),
      simulation_session_id, parameters.motion_start_joint_tolerance);
  }

  NodeSpinner spinner(node);
  pick_place::IWorldObserver * runner_observer = world_observer.get();
  if (runner_observer == nullptr && motion_adapter) {
    runner_observer = motion_adapter.get();
  }
  RosExecutionObservationLogger execution_observation_logger(logger);
  const pick_place::StateMachineRunner runner(runtime.actions, runtime.contracts, runner_observer,
                                              checkpoint_store.get(), common_resume_validator.get(),
                                              &execution_observation_logger,
                                              &runtime.plan_validators, &recovery_policy);
  const auto result =
    runner.run({*mode, stop_after, resume, fail_at, parameters.max_state_transitions});
  if (result.failure) {
    RCLCPP_ERROR(logger, "Run failed: status=%s state=%s category=%d code=%s message=%s",
                 pick_place::toString(result.status), pick_place::toString(result.current_state),
                 static_cast<int>(result.failure->category), result.failure->code.c_str(),
                 result.failure->message.c_str());
  } else {
    RCLCPP_INFO(logger, "Run completed: status=%s current_state=%s next_state=%s transitions=%lu",
                pick_place::toString(result.status), pick_place::toString(result.current_state),
                result.next_state ? pick_place::toString(*result.next_state) : "",
                result.transition_count);
  }

  rclcpp::shutdown();
  return successful(result.status) ? EXIT_SUCCESS : EXIT_FAILURE;
}
