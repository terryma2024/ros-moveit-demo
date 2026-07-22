#include <cstdlib>
#include <cmath>
#include <cstdint>
#include <memory>
#include <optional>
#include <sstream>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <Eigen/Geometry>
#include <rclcpp/executors/single_threaded_executor.hpp>
#include <rclcpp/rclcpp.hpp>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include "panda_gazebo_demo/pick_place/descend_planner_executor.hpp"
#include "panda_gazebo_demo/pick_place/file_checkpoint_store.hpp"
#include "panda_gazebo_demo/pick_place/gazebo_attachment_executor.hpp"
#include "panda_gazebo_demo/pick_place/gazebo_world_observer.hpp"
#include "panda_gazebo_demo/pick_place/gripper_command_adapter.hpp"
#include "panda_gazebo_demo/pick_place/gripper_state_executor.hpp"
#include "panda_gazebo_demo/pick_place/move_above_object_planner.hpp"
#include "panda_gazebo_demo/pick_place/motion_plan_evidence.hpp"
#include "panda_gazebo_demo/pick_place/motion_state_action.hpp"
#include "panda_gazebo_demo/pick_place/moveit_motion_adapter.hpp"
#include "panda_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "panda_gazebo_demo/pick_place/moveit_scene_executor.hpp"
#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"
#include "panda_gazebo_demo/pick_place/pick_place_contracts.hpp"
#include "panda_gazebo_demo/pick_place/recovery_contracts.hpp"
#include "panda_gazebo_demo/pick_place/common_resume_validator.hpp"
#include "panda_gazebo_demo/pick_place/runner.hpp"

namespace pick_place = panda_gazebo_demo::pick_place;

namespace
{

class NodeSpinner
{
public:
  explicit NodeSpinner(const std::shared_ptr<rclcpp::Node> & node)
  : node_(node)
  {
    executor_.add_node(node_);
    thread_ = std::thread([this]() {executor_.spin();});
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
  explicit RosExecutionObservationLogger(rclcpp::Logger logger)
  : logger_(std::move(logger)) {}

  void record(
    pick_place::State state, const pick_place::WorldSnapshot & before,
    const pick_place::WorldSnapshot & after) override
  {
    logPose("COKE_POSE_BEFORE", state, before.gazebo_coke_pose_world);
    logPose("COKE_POSE_AFTER", state, after.gazebo_coke_pose_world);
    logGripper("GRIPPER_JOINTS_BEFORE", state, before);
    logGripper("GRIPPER_JOINTS_AFTER", state, after);
  }

private:
  void logPose(
    const char * label, pick_place::State state,
    const std::optional<pick_place::Pose3d> & pose) const
  {
    if (!pose) {
      RCLCPP_INFO(logger_, "%s state=%s unavailable", label, pick_place::toString(state));
      return;
    }
    const Eigen::Quaterniond orientation(pose->qw, pose->qx, pose->qy, pose->qz);
    const auto rpy = orientation.normalized().toRotationMatrix().eulerAngles(0, 1, 2);
    RCLCPP_INFO(
      logger_,
      "%s state=%s x=%.6f y=%.6f z=%.6f roll=%.6f pitch=%.6f yaw=%.6f",
      label, pick_place::toString(state), pose->x, pose->y, pose->z, rpy.x(), rpy.y(), rpy.z());
  }

  void logGripper(
    const char * label, pick_place::State state,
    const pick_place::WorldSnapshot & snapshot) const
  {
    const auto finger1_position = snapshot.joint_positions.find("panda_finger_joint1");
    const auto finger2_position = snapshot.joint_positions.find("panda_finger_joint2");
    const auto finger1_velocity = snapshot.joint_velocities.find("panda_finger_joint1");
    const auto finger2_velocity = snapshot.joint_velocities.find("panda_finger_joint2");
    if (finger1_position == snapshot.joint_positions.end() ||
      finger2_position == snapshot.joint_positions.end() ||
      finger1_velocity == snapshot.joint_velocities.end() ||
      finger2_velocity == snapshot.joint_velocities.end())
    {
      RCLCPP_INFO(logger_, "%s state=%s unavailable", label, pick_place::toString(state));
      return;
    }
    RCLCPP_INFO(
      logger_,
      "%s state=%s finger1_position=%.6f finger2_position=%.6f "
      "finger1_velocity=%.6f finger2_velocity=%.6f",
      label, pick_place::toString(state), finger1_position->second, finger2_position->second,
      finger1_velocity->second, finger2_velocity->second);
  }

  rclcpp::Logger logger_;
};

template<typename T>
T parameterOrDeclare(
  const std::shared_ptr<rclcpp::Node> & node, const std::string & name,
  const T & default_value)
{
  if (!node->has_parameter(name)) {
    node->declare_parameter<T>(name, default_value);
  }
  return node->get_parameter(name).get_value<T>();
}

std::optional<pick_place::State> optionalStateParameter(
  const std::shared_ptr<rclcpp::Node> & node,
  const std::string & name,
  bool forward_action_only,
  rclcpp::Logger logger)
{
  const auto value = parameterOrDeclare(node, name, std::string(""));
  if (value.empty()) {
    return std::nullopt;
  }
  const auto state = pick_place::stateFromString(value);
  if (!state || (forward_action_only && !pick_place::isForwardAction(*state))) {
    RCLCPP_ERROR(logger, "%s must name a forward action State; got '%s'", name.c_str(),
                 value.c_str());
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

std::string configurationHash(
  const std::string & planning_group, const std::string & tcp_link,
  const std::vector<std::string> & required_objects, double velocity_scaling,
  double acceleration_scaling, double tcp_position_tolerance, double tcp_orientation_tolerance_rad,
  double coke_position_tolerance, double coke_orientation_tolerance_rad,
  const std::string & gazebo_world_name, const std::string & gazebo_coke_model,
  const std::string & gazebo_attach_topic, const std::string & gazebo_detach_topic,
  const std::string & gazebo_attachment_topic, double gazebo_attachment_timeout_seconds,
  double gazebo_attachment_poll_interval_seconds, double gazebo_observation_max_age_seconds,
  bool gazebo_coke_initially_detached, const std::string & gripper_action_name,
  double gripper_open_position, double gripper_max_effort, double gripper_action_timeout_seconds,
  double descend_eef_step, double descend_min_fraction, double descend_joint_jump_threshold,
  const std::string & target_policy_signature)
{
  std::ostringstream input;
  input << planning_group << '\n'
        << tcp_link << '\n'
        << velocity_scaling << '\n'
        << acceleration_scaling << '\n'
        << tcp_position_tolerance << '\n'
        << tcp_orientation_tolerance_rad << '\n'
        << coke_position_tolerance << '\n'
        << coke_orientation_tolerance_rad << '\n'
        << gazebo_world_name << '\n'
        << gazebo_coke_model << '\n'
        << gazebo_attach_topic << '\n'
        << gazebo_detach_topic << '\n'
        << gazebo_attachment_topic << '\n'
        << gazebo_attachment_timeout_seconds << '\n'
        << gazebo_attachment_poll_interval_seconds << '\n'
        << gazebo_observation_max_age_seconds << '\n'
        << gazebo_coke_initially_detached << '\n'
        << gripper_action_name << '\n'
        << gripper_open_position << '\n'
        << gripper_max_effort << '\n'
        << gripper_action_timeout_seconds << '\n'
        << descend_eef_step << '\n'
        << descend_min_fraction << '\n'
        << descend_joint_jump_threshold << '\n'
        << target_policy_signature;
  for (const auto & object : required_objects) {
    input << '\n' << object;
  }
  std::uint64_t hash = 14695981039346656037ULL;
  for (const auto character : input.str()) {
    hash ^= static_cast<unsigned char>(character);
    hash *= 1099511628211ULL;
  }
  std::ostringstream output;
  output << std::hex << hash;
  return output.str();
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

  const auto fail_at = optionalStateParameter(node, "fail_at", true, logger);
  const auto fail_at_value = node->get_parameter("fail_at").get_value<std::string>();
  const auto stop_after = optionalStateParameter(node, "stop_after", true, logger);
  const auto stop_after_value = node->get_parameter("stop_after").get_value<std::string>();
  if ((!fail_at_value.empty() && !fail_at) || (!stop_after_value.empty() && !stop_after)) {
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  const auto max_transitions = parameterOrDeclare<std::int64_t>(node, "max_state_transitions", 100);
  const auto resume = parameterOrDeclare(node, "resume", false);
  if (resume && *mode == pick_place::RunMode::DRY_RUN) {
    RCLCPP_ERROR(logger, "resume is supported only in plan_only and execute modes");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }
  const auto planning_group = parameterOrDeclare(node, "planning_group", std::string("panda_arm"));
  const auto tcp_link = parameterOrDeclare(node, "tcp_link", std::string("panda_tcp"));
  const auto required_objects =
    parameterOrDeclare(node, "required_world_objects", std::vector<std::string>{"table", "coke"});
  const auto velocity_scaling = parameterOrDeclare(node, "velocity_scaling", 0.1);
  const auto acceleration_scaling = parameterOrDeclare(node, "acceleration_scaling", 0.1);
  const auto checkpoint_path = parameterOrDeclare(
    node, "checkpoint_path", std::string("/tmp/panda_pick_place_checkpoint.json"));
  const auto tcp_position_tolerance = parameterOrDeclare(node, "tcp_position_tolerance", 0.02);
  const auto tcp_orientation_tolerance_rad =
    parameterOrDeclare(node, "tcp_orientation_tolerance_rad", 0.08726646259971647);
  const auto coke_position_tolerance = parameterOrDeclare(node, "coke_position_tolerance", 0.01);
  const auto coke_orientation_tolerance_rad =
    parameterOrDeclare(node, "coke_orientation_tolerance_rad", 0.08726646259971647);
  const auto gazebo_world_name =
    parameterOrDeclare(node, "gazebo_world_name", std::string("pick_place_world"));
  const auto gazebo_coke_model = parameterOrDeclare(node, "gazebo_coke_model", std::string("coke"));
  const auto gazebo_attach_topic =
    parameterOrDeclare(node, "gazebo_attach_topic", std::string("/panda/attach_coke"));
  const auto gazebo_detach_topic =
    parameterOrDeclare(node, "gazebo_detach_topic", std::string("/panda/detach_coke"));
  const auto gazebo_attachment_topic =
    parameterOrDeclare(node, "gazebo_attachment_topic", std::string("/panda/coke_attached"));
  const auto gazebo_attachment_timeout_seconds =
    parameterOrDeclare(node, "gazebo_attachment_timeout_seconds", 2.0);
  const auto gazebo_attachment_poll_interval_seconds =
    parameterOrDeclare(node, "gazebo_attachment_poll_interval_seconds", 0.01);
  const auto gazebo_observation_max_age_seconds =
    parameterOrDeclare(node, "gazebo_observation_max_age_seconds", 0.5);
  const auto gazebo_coke_initially_detached =
    parameterOrDeclare(node, "gazebo_coke_initially_detached", true);
  const auto simulation_session_id =
    parameterOrDeclare(node, "simulation_session_id", std::string(""));
  const auto gripper_action_name = parameterOrDeclare(
    node, "gripper_action_name", std::string("/panda_hand_controller/gripper_cmd"));
  const auto gripper_open_position = parameterOrDeclare(node, "gripper_open_position", 0.04);
  const auto gripper_max_effort = parameterOrDeclare(node, "gripper_max_effort", 0.0);
  const auto gripper_action_timeout_seconds =
    parameterOrDeclare(node, "gripper_action_timeout_seconds", 5.0);
  const auto descend_eef_step = parameterOrDeclare(node, "descend_eef_step", 0.005);
  const auto descend_min_fraction = parameterOrDeclare(node, "descend_min_fraction", 0.99);
  const auto descend_joint_jump_threshold =
    parameterOrDeclare(node, "descend_joint_jump_threshold", 0.2);
  if (max_transitions <= 0 || !std::isfinite(velocity_scaling) || velocity_scaling <= 0.0 ||
    velocity_scaling > 1.0 || !std::isfinite(acceleration_scaling) ||
    acceleration_scaling <= 0.0 || acceleration_scaling > 1.0 || tcp_position_tolerance <= 0.0 ||
    tcp_orientation_tolerance_rad <= 0.0 || coke_position_tolerance <= 0.0 ||
    coke_orientation_tolerance_rad <= 0.0 || gazebo_attach_topic.empty() ||
    gazebo_detach_topic.empty() || gazebo_attachment_topic.empty() ||
    !std::isfinite(gazebo_attachment_timeout_seconds) ||
    gazebo_attachment_timeout_seconds <= 0.0 ||
    !std::isfinite(gazebo_attachment_poll_interval_seconds) ||
    gazebo_attachment_poll_interval_seconds <= 0.0 ||
    gazebo_observation_max_age_seconds <= 0.0 ||
    gripper_action_name.empty() || gripper_open_position <= 0.0 || gripper_max_effort < 0.0 ||
    gripper_action_timeout_seconds <= 0.0 || !std::isfinite(descend_eef_step) ||
    descend_eef_step <= 0.0 || !std::isfinite(descend_min_fraction) ||
    descend_min_fraction <= 0.0 || descend_min_fraction > 1.0 ||
    !std::isfinite(descend_joint_jump_threshold) || descend_joint_jump_threshold <= 0.0)
  {
    RCLCPP_ERROR(
      logger,
      "transition count and tolerances must be positive; scaling factors must be in (0, 1]");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  pick_place::StateActionRegistry actions;
  pick_place::PlanValidatorRegistry plan_validators;
  pick_place::TransitionContractRegistry contracts;
  const auto target_policy = std::make_shared<pick_place::FixedPickPlaceTargetPolicy>();
  const pick_place::FixedRecoveryPolicy recovery_policy(
    target_policy, tcp_position_tolerance);
  std::shared_ptr<pick_place::MoveAboveObjectPlanner> move_above_action;
  std::shared_ptr<pick_place::DescendPlannerExecutor> descend_action;
  std::unique_ptr<pick_place::FileCheckpointStore> checkpoint_store;
  std::unique_ptr<pick_place::GazeboWorldObserver> world_observer;
  std::unique_ptr<pick_place::CommonResumeValidator> common_resume_validator;
  if (*mode == pick_place::RunMode::PLAN_ONLY || *mode == pick_place::RunMode::EXECUTE) {
    move_above_action = std::make_shared<pick_place::MoveAboveObjectPlanner>(
      node, planning_group, tcp_link, required_objects, target_policy, velocity_scaling,
      acceleration_scaling);
    actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, move_above_action);
    const pick_place::MotionPlanLimits motion_plan_limits{
      descend_min_fraction, descend_joint_jump_threshold, tcp_position_tolerance,
      tcp_orientation_tolerance_rad, tcp_position_tolerance,
      tcp_orientation_tolerance_rad, coke_position_tolerance,
      coke_orientation_tolerance_rad};
    plan_validators.registerValidator(
      pick_place::State::MOVE_ABOVE_OBJECT,
      std::make_shared<pick_place::MotionPlanValidator>(
        pick_place::MotionStateConfig{pick_place::State::MOVE_ABOVE_OBJECT,
          pick_place::State::DESCEND, pick_place::MotionKind::POSE, false},
        target_policy, motion_plan_limits));
    descend_action = std::make_shared<pick_place::DescendPlannerExecutor>(
      node, planning_group, tcp_link, target_policy, velocity_scaling, acceleration_scaling,
      descend_eef_step, descend_min_fraction, descend_joint_jump_threshold,
      tcp_position_tolerance, tcp_orientation_tolerance_rad);
    actions.registerPlanner(pick_place::State::DESCEND, descend_action);
    plan_validators.registerValidator(
      pick_place::State::DESCEND,
      std::make_shared<pick_place::MotionPlanValidator>(
        pick_place::MotionStateConfig{pick_place::State::DESCEND,
          pick_place::State::CLOSE_GRIPPER, pick_place::MotionKind::CARTESIAN_DOWN, false},
        target_policy, motion_plan_limits));

    const auto forward_motion_adapter = std::make_shared<pick_place::MoveItMotionAdapter>(
      node, planning_group, tcp_link, required_objects, velocity_scaling,
      acceleration_scaling, descend_eef_step);
    const std::vector<pick_place::MotionStateConfig> forward_motion_configs{
      {pick_place::State::LIFT, pick_place::State::MOVE_ABOVE_PLACE,
        pick_place::MotionKind::CARTESIAN_UP, true},
      {pick_place::State::MOVE_ABOVE_PLACE, pick_place::State::DESCEND_TO_PLACE,
        pick_place::MotionKind::POSE, true},
      {pick_place::State::DESCEND_TO_PLACE, pick_place::State::OPEN_GRIPPER,
        pick_place::MotionKind::CARTESIAN_DOWN, true},
      {pick_place::State::RETREAT, pick_place::State::DONE,
        pick_place::MotionKind::CARTESIAN_UP, false},
    };
    for (const auto & config : forward_motion_configs) {
      auto action = std::make_shared<pick_place::MotionStateAction>(
        forward_motion_adapter, target_policy, config);
      actions.registerPlanner(config.state, action);
      if (*mode == pick_place::RunMode::EXECUTE) {
        actions.registerExecutor(config.state, action);
      }
      plan_validators.registerValidator(config.state,
        std::make_shared<pick_place::MotionPlanValidator>(
          config, target_policy, motion_plan_limits));
    }
    const std::vector<pick_place::MotionStateConfig> recovery_motion_configs{
      {pick_place::State::RECOVER_LIFT_TO_SAFE_HEIGHT,
        pick_place::State::RECOVER_MOVE_ABOVE_PICK,
        pick_place::MotionKind::CARTESIAN_UP, true},
      {pick_place::State::RECOVER_MOVE_ABOVE_PICK,
        pick_place::State::RECOVER_DESCEND_TO_PICK,
        pick_place::MotionKind::POSE, true},
      {pick_place::State::RECOVER_DESCEND_TO_PICK,
        pick_place::State::RECOVER_OPEN_GRIPPER,
        pick_place::MotionKind::CARTESIAN_DOWN, true},
      {pick_place::State::RECOVER_RETREAT, pick_place::State::ERROR,
        pick_place::MotionKind::CARTESIAN_UP, false, true},
    };
    for (const auto & config : recovery_motion_configs) {
      auto action = std::make_shared<pick_place::MotionStateAction>(
        forward_motion_adapter, target_policy, config);
      actions.registerPlanner(config.state, action);
      if (*mode == pick_place::RunMode::EXECUTE) {
        actions.registerExecutor(config.state, action);
      }
      plan_validators.registerValidator(config.state,
        std::make_shared<pick_place::MotionPlanValidator>(
          config, target_policy, motion_plan_limits));
    }
  }
  if (*mode == pick_place::RunMode::EXECUTE) {
    const auto gripper_adapter = std::make_shared<pick_place::GripperCommandAdapter>(
      node, gripper_action_name, gripper_action_timeout_seconds);
    actions.registerExecutor(
      pick_place::State::PREPARE_OPEN_GRIPPER,
      std::make_shared<pick_place::GripperStateExecutor>(
        gripper_adapter,
        pick_place::GripperStateConfig{pick_place::State::PREPARE_OPEN_GRIPPER,
          gripper_open_position, gripper_max_effort, false}));
    actions.registerExecutor(
      pick_place::State::CLOSE_GRIPPER,
      std::make_shared<pick_place::GripperStateExecutor>(
        gripper_adapter,
        pick_place::GripperStateConfig{pick_place::State::CLOSE_GRIPPER,
          0.0, gripper_max_effort, false}));
    actions.registerExecutor(
      pick_place::State::OPEN_GRIPPER,
      std::make_shared<pick_place::GripperStateExecutor>(
        gripper_adapter,
        pick_place::GripperStateConfig{pick_place::State::OPEN_GRIPPER,
          gripper_open_position, gripper_max_effort, false}));
    actions.registerExecutor(
      pick_place::State::RECOVER_OPEN_GRIPPER,
      std::make_shared<pick_place::GripperStateExecutor>(
        gripper_adapter,
        pick_place::GripperStateConfig{pick_place::State::RECOVER_OPEN_GRIPPER,
          gripper_open_position, gripper_max_effort, true}));
    actions.registerExecutor(pick_place::State::MOVE_ABOVE_OBJECT, move_above_action);
    actions.registerExecutor(pick_place::State::DESCEND, descend_action);
    actions.registerExecutor(
      pick_place::State::ATTACH_GAZEBO,
      std::make_shared<pick_place::GazeboAttachmentExecutor>(
        pick_place::State::ATTACH_GAZEBO, true, gazebo_attach_topic, gazebo_detach_topic,
        gazebo_attachment_topic, gazebo_attachment_timeout_seconds,
        gazebo_attachment_poll_interval_seconds, false));
    actions.registerExecutor(
      pick_place::State::DETACH_GAZEBO,
      std::make_shared<pick_place::GazeboAttachmentExecutor>(
        pick_place::State::DETACH_GAZEBO, false, gazebo_attach_topic, gazebo_detach_topic,
        gazebo_attachment_topic, gazebo_attachment_timeout_seconds,
        gazebo_attachment_poll_interval_seconds, false));
    actions.registerExecutor(
      pick_place::State::RECOVER_DETACH_GAZEBO,
      std::make_shared<pick_place::GazeboAttachmentExecutor>(
        pick_place::State::RECOVER_DETACH_GAZEBO, false, gazebo_attach_topic,
        gazebo_detach_topic, gazebo_attachment_topic, gazebo_attachment_timeout_seconds,
        gazebo_attachment_poll_interval_seconds, true));
    const auto moveit_scene_adapter = std::make_shared<pick_place::MoveItSceneAdapter>(
      node, planning_group);
    const std::vector<pick_place::MoveItSceneConfig> moveit_scene_configs{
      {pick_place::State::ATTACH_MOVEIT, pick_place::MoveItSceneOperation::ATTACH, false},
      {pick_place::State::DETACH_MOVEIT, pick_place::MoveItSceneOperation::DETACH, false},
      {pick_place::State::SYNC_WORLD_OBJECT, pick_place::MoveItSceneOperation::SYNC, false},
      {pick_place::State::RECOVER_DETACH_MOVEIT,
        pick_place::MoveItSceneOperation::DETACH, true},
      {pick_place::State::RECOVER_SYNC_WORLD_OBJECT,
        pick_place::MoveItSceneOperation::SYNC, true},
    };
    for (const auto & config : moveit_scene_configs) {
      actions.registerExecutor(config.state,
        std::make_shared<pick_place::MoveItSceneExecutor>(
          moveit_scene_adapter, config));
    }
  }
  if (*mode == pick_place::RunMode::EXECUTE || resume) {
    contracts.registerContract(
      {pick_place::State::PREPARE_OPEN_GRIPPER, pick_place::State::MOVE_ABOVE_OBJECT},
      std::make_shared<pick_place::PrepareOpenGripperToMoveAboveObjectValidator>(
        required_objects, tcp_position_tolerance, tcp_orientation_tolerance_rad,
        coke_position_tolerance, coke_orientation_tolerance_rad));
    contracts.registerContract({pick_place::State::MOVE_ABOVE_OBJECT, pick_place::State::DESCEND},
                               std::make_shared<pick_place::MoveAboveObjectToDescendValidator>(
                                 target_policy, required_objects, tcp_position_tolerance,
                                 tcp_orientation_tolerance_rad, coke_position_tolerance,
                                 coke_orientation_tolerance_rad));
    contracts.registerContract({pick_place::State::DESCEND, pick_place::State::CLOSE_GRIPPER},
                               std::make_shared<pick_place::DescendToCloseGripperValidator>(
                                 target_policy, required_objects, tcp_position_tolerance,
                                 tcp_orientation_tolerance_rad, coke_position_tolerance,
                                 coke_orientation_tolerance_rad));
    pick_place::PickPlaceContractConfig contract_config;
    contract_config.tcp_position_tolerance = tcp_position_tolerance;
    contract_config.tcp_orientation_tolerance_rad = tcp_orientation_tolerance_rad;
    contract_config.coke_position_tolerance = coke_position_tolerance;
    contract_config.coke_orientation_tolerance_rad = coke_orientation_tolerance_rad;
    contract_config.carried_relative_position_tolerance = coke_position_tolerance;
    contract_config.carried_relative_orientation_tolerance_rad =
      coke_orientation_tolerance_rad;
    pick_place::registerPickPlaceForwardContracts(
      contracts, target_policy, contract_config);
    pick_place::registerRecoveryContracts(
      contracts, target_policy, contract_config);
  }
  if (*mode == pick_place::RunMode::EXECUTE || resume) {
    if (simulation_session_id.empty()) {
      RCLCPP_ERROR(
        logger,
        "simulation_session_id is required for execute or resume to reject stale checkpoints");
      rclcpp::shutdown();
      return EXIT_FAILURE;
    }
    checkpoint_store = std::make_unique<pick_place::FileCheckpointStore>(checkpoint_path);
    world_observer = std::make_unique<pick_place::GazeboWorldObserver>(
      *move_above_action, gazebo_world_name, gazebo_coke_model, gazebo_attachment_topic,
      simulation_session_id, gazebo_observation_max_age_seconds, gazebo_coke_initially_detached);
    common_resume_validator = std::make_unique<pick_place::CommonResumeValidator>(
      configurationHash(planning_group, tcp_link, required_objects, velocity_scaling,
                        acceleration_scaling, tcp_position_tolerance, tcp_orientation_tolerance_rad,
                        coke_position_tolerance, coke_orientation_tolerance_rad, gazebo_world_name,
                        gazebo_coke_model, gazebo_attach_topic, gazebo_detach_topic,
                        gazebo_attachment_topic, gazebo_attachment_timeout_seconds,
                        gazebo_attachment_poll_interval_seconds,
                        gazebo_observation_max_age_seconds, gazebo_coke_initially_detached,
                        gripper_action_name, gripper_open_position, gripper_max_effort,
                        gripper_action_timeout_seconds, descend_eef_step, descend_min_fraction,
                        descend_joint_jump_threshold, target_policy->configurationSignature()),
      simulation_session_id);
  }

  NodeSpinner spinner(node);
  pick_place::IWorldObserver * runner_observer = world_observer.get();
  if (runner_observer == nullptr && move_above_action) {
    runner_observer = move_above_action.get();
  }
  RosExecutionObservationLogger execution_observation_logger(logger);
  const pick_place::StateMachineRunner runner(actions, contracts, runner_observer,
    checkpoint_store.get(),
    common_resume_validator.get(), &execution_observation_logger, &plan_validators,
    &recovery_policy);
  const auto result =
    runner.run({*mode, stop_after, resume, fail_at, static_cast<std::uint64_t>(max_transitions)});
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
