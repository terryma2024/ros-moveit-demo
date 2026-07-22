#include <cstdlib>
#include <cstdint>
#include <memory>
#include <optional>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <rclcpp/executors/single_threaded_executor.hpp>
#include <rclcpp/rclcpp.hpp>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include "panda_gazebo_demo/pick_place/file_checkpoint_store.hpp"
#include "panda_gazebo_demo/pick_place/gazebo_world_observer.hpp"
#include "panda_gazebo_demo/pick_place/move_above_object_planner.hpp"
#include "panda_gazebo_demo/pick_place/open_gripper_executor.hpp"
#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"
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
  const std::string & gazebo_attachment_topic, double gazebo_observation_max_age_seconds,
  bool gazebo_coke_initially_detached, const std::string & gripper_action_name,
  double gripper_open_position, double gripper_max_effort, double gripper_action_timeout_seconds,
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
        << gazebo_attachment_topic << '\n'
        << gazebo_observation_max_age_seconds << '\n'
        << gazebo_coke_initially_detached << '\n'
        << gripper_action_name << '\n'
        << gripper_open_position << '\n'
        << gripper_max_effort << '\n'
        << gripper_action_timeout_seconds << '\n'
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
  const auto gazebo_attachment_topic =
    parameterOrDeclare(node, "gazebo_attachment_topic", std::string("/panda/coke_attached"));
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
  if (max_transitions <= 0 || velocity_scaling <= 0.0 || velocity_scaling > 1.0 ||
    acceleration_scaling <= 0.0 || acceleration_scaling > 1.0 || tcp_position_tolerance <= 0.0 ||
    tcp_orientation_tolerance_rad <= 0.0 || coke_position_tolerance <= 0.0 ||
    coke_orientation_tolerance_rad <= 0.0 || gazebo_observation_max_age_seconds <= 0.0 ||
    gripper_action_name.empty() || gripper_open_position <= 0.0 || gripper_max_effort < 0.0 ||
    gripper_action_timeout_seconds <= 0.0)
  {
    RCLCPP_ERROR(
      logger,
      "transition count and tolerances must be positive; scaling factors must be in (0, 1]");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  const auto target_policy = std::make_shared<pick_place::FixedPickPlaceTargetPolicy>();
  std::shared_ptr<pick_place::MoveAboveObjectPlanner> move_above_action;
  std::shared_ptr<pick_place::OpenGripperExecutor> open_gripper_action;
  std::unique_ptr<pick_place::FileCheckpointStore> checkpoint_store;
  std::unique_ptr<pick_place::GazeboWorldObserver> world_observer;
  std::unique_ptr<pick_place::CommonResumeValidator> common_resume_validator;
  if (*mode == pick_place::RunMode::PLAN_ONLY || *mode == pick_place::RunMode::EXECUTE) {
    move_above_action = std::make_shared<pick_place::MoveAboveObjectPlanner>(
      node, planning_group, tcp_link, required_objects, target_policy, velocity_scaling,
      acceleration_scaling);
    actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, move_above_action);
  }
  if (*mode == pick_place::RunMode::EXECUTE) {
    open_gripper_action = std::make_shared<pick_place::OpenGripperExecutor>(
      node, gripper_action_name, gripper_open_position, gripper_max_effort,
      gripper_action_timeout_seconds);
    actions.registerExecutor(pick_place::State::PREPARE_OPEN_GRIPPER, open_gripper_action);
    actions.registerExecutor(pick_place::State::MOVE_ABOVE_OBJECT, move_above_action);
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
                        gazebo_coke_model, gazebo_attachment_topic,
                        gazebo_observation_max_age_seconds, gazebo_coke_initially_detached,
                        gripper_action_name, gripper_open_position, gripper_max_effort,
                        gripper_action_timeout_seconds, target_policy->configurationSignature()),
      simulation_session_id);
  }

  NodeSpinner spinner(node);
  pick_place::IWorldObserver * runner_observer = world_observer.get();
  if (runner_observer == nullptr && move_above_action) {
    runner_observer = move_above_action.get();
  }
  const pick_place::StateMachineRunner runner(actions, contracts, runner_observer,
    checkpoint_store.get(),
    common_resume_validator.get());
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
