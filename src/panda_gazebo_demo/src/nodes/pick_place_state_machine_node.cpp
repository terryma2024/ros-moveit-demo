#include <cstdlib>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <rclcpp/executors/single_threaded_executor.hpp>
#include <rclcpp/rclcpp.hpp>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include "panda_gazebo_demo/pick_place/file_checkpoint_store.hpp"
#include "panda_gazebo_demo/pick_place/moveit_pregrasp_planner.hpp"
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
  const std::string & name, bool forward_action_only,
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

}  // namespace

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  const auto node = std::make_shared<rclcpp::Node>(
    "pick_place_state_machine",
    rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true).
    append_parameter_override("use_sim_time", true));
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
  const auto planning_group = parameterOrDeclare(node, "planning_group", std::string("panda_arm"));
  const auto tcp_link = parameterOrDeclare(node, "tcp_link", std::string("panda_tcp"));
  const auto required_objects = parameterOrDeclare(node, "required_world_objects",
    std::vector<std::string>{"table", "coke"});
  const auto velocity_scaling = parameterOrDeclare(node, "velocity_scaling", 0.1);
  const auto acceleration_scaling = parameterOrDeclare(node, "acceleration_scaling", 0.1);
  const auto checkpoint_path = parameterOrDeclare(
    node, "checkpoint_path", std::string("/tmp/panda_pick_place_checkpoint.yaml"));
  const auto tcp_position_tolerance = parameterOrDeclare(node, "tcp_position_tolerance", 0.02);
  const auto coke_position_tolerance = parameterOrDeclare(node, "coke_position_tolerance", 0.01);
  if (max_transitions <= 0 || velocity_scaling <= 0.0 || velocity_scaling > 1.0 ||
    acceleration_scaling <= 0.0 || acceleration_scaling > 1.0 ||
    tcp_position_tolerance <= 0.0 || coke_position_tolerance <= 0.0)
  {
    RCLCPP_ERROR(logger,
      "transition count and tolerances must be positive; scaling factors must be in (0, 1]");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  pick_place::StateActionRegistry actions;
  pick_place::TransitionContractRegistry contracts;
  std::shared_ptr<pick_place::MoveItPreGraspPlanner> move_above_action;
  std::unique_ptr<pick_place::FileCheckpointStore> checkpoint_store;
  if (*mode == pick_place::RunMode::PLAN_ONLY || *mode == pick_place::RunMode::EXECUTE) {
    move_above_action = std::make_shared<pick_place::MoveItPreGraspPlanner>(
      node, planning_group, tcp_link, required_objects, velocity_scaling, acceleration_scaling);
    actions.registerPlanner(pick_place::State::MOVE_ABOVE_OBJECT, move_above_action);
  }
  if (*mode == pick_place::RunMode::EXECUTE) {
    actions.registerExecutor(pick_place::State::MOVE_ABOVE_OBJECT, move_above_action);
    contracts.registerContract(
      {pick_place::State::MOVE_ABOVE_OBJECT, pick_place::State::DESCEND},
      std::make_shared<pick_place::MoveAboveObjectContract>(
        pick_place::Pose3d{0.3, 0.0, 0.987, 1.0, 0.0, 0.0, 0.0}, required_objects,
        tcp_position_tolerance, coke_position_tolerance));
    checkpoint_store = std::make_unique<pick_place::FileCheckpointStore>(checkpoint_path);
  }

  NodeSpinner spinner(node);
  const pick_place::StateMachineRunner runner(
    actions, contracts, move_above_action.get(), checkpoint_store.get());
  const auto result = runner.run({*mode, stop_after, resume, fail_at,
        static_cast<std::uint64_t>(max_transitions)});
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
