#include <array>
#include <cstdlib>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <thread>
#include <utility>

#include <geometry_msgs/msg/pose.hpp>
#include <moveit/move_group_interface/move_group_interface.hpp>
#include <rclcpp/executors/single_threaded_executor.hpp>
#include <rclcpp/rclcpp.hpp>

enum class Mode
{
  DRY_RUN,
  PLAN_ONLY,
  EXECUTE
};

[[nodiscard]] std::optional<Mode> modeFromParameter(std::string_view value)
{
  if (value == "dry_run")
  {
    return Mode::DRY_RUN;
  }

  if (value == "plan_only")
  {
    return Mode::PLAN_ONLY;
  }

  if (value == "execute")
  {
    return Mode::EXECUTE;
  }

  return std::nullopt;
}

class StateMachine
{
public:
  enum class State
  {
    IDLE,
    MOVE_ABOVE_OBJECT,
    DESCEND,
    CLOSE_GRIPPER,
    ATTACH_GAZEBO,
    ATTACH_MOVEIT,
    LIFT,
    MOVE_ABOVE_PLACE,
    DESCEND_TO_PLACE,
    OPEN_GRIPPER,
    DETACH_GAZEBO,
    DETACH_MOVEIT,
    SYNC_WORLD_OBJECT,
    RETREAT,
    DONE,
    PLAN_ONLY_COMPLETE,
    RECOVER_DETACH_MOVEIT,
    RECOVER_OPEN_GRIPPER,
    RECOVER_DETACH_GAZEBO,
    RECOVER_SYNC_WORLD_OBJECT,
    RECOVER_RETREAT,
    ERROR
  };

  enum class Outcome
  {
    SUCCEEDED,
    FAILED,
    PLANNED_ONLY
  };

  [[nodiscard]] State currentState() const noexcept
  {
    return current_state_;
  }

  [[nodiscard]] bool isTerminal() const noexcept
  {
    return current_state_ == State::DONE || current_state_ == State::PLAN_ONLY_COMPLETE ||
           current_state_ == State::ERROR;
  }

  [[nodiscard]] bool completedSuccessfully() const noexcept
  {
    return current_state_ == State::DONE || current_state_ == State::PLAN_ONLY_COMPLETE;
  }

  void advance(Outcome outcome)
  {
    if (!isTerminal())
    {
      current_state_ = resolveActionOutcome(current_state_, outcome);
    }
  }

  static const char* toString(State state) noexcept
  {
    switch (state)
    {
      case State::IDLE:
        return "IDLE";
      case State::MOVE_ABOVE_OBJECT:
        return "MOVE_ABOVE_OBJECT";
      case State::DESCEND:
        return "DESCEND";
      case State::CLOSE_GRIPPER:
        return "CLOSE_GRIPPER";
      case State::ATTACH_GAZEBO:
        return "ATTACH_GAZEBO";
      case State::ATTACH_MOVEIT:
        return "ATTACH_MOVEIT";
      case State::LIFT:
        return "LIFT";
      case State::MOVE_ABOVE_PLACE:
        return "MOVE_ABOVE_PLACE";
      case State::DESCEND_TO_PLACE:
        return "DESCEND_TO_PLACE";
      case State::OPEN_GRIPPER:
        return "OPEN_GRIPPER";
      case State::DETACH_GAZEBO:
        return "DETACH_GAZEBO";
      case State::DETACH_MOVEIT:
        return "DETACH_MOVEIT";
      case State::SYNC_WORLD_OBJECT:
        return "SYNC_WORLD_OBJECT";
      case State::RETREAT:
        return "RETREAT";
      case State::DONE:
        return "DONE";
      case State::PLAN_ONLY_COMPLETE:
        return "PLAN_ONLY_COMPLETE";
      case State::RECOVER_DETACH_MOVEIT:
        return "RECOVER_DETACH_MOVEIT";
      case State::RECOVER_OPEN_GRIPPER:
        return "RECOVER_OPEN_GRIPPER";
      case State::RECOVER_DETACH_GAZEBO:
        return "RECOVER_DETACH_GAZEBO";
      case State::RECOVER_SYNC_WORLD_OBJECT:
        return "RECOVER_SYNC_WORLD_OBJECT";
      case State::RECOVER_RETREAT:
        return "RECOVER_RETREAT";
      case State::ERROR:
        return "ERROR";
    }

    return "UNKNOWN";
  }

private:
  struct StateTransitions
  {
    State succeeded;
    State failed;
    State planned_only;
  };

  using TransitionTable = std::map<State, StateTransitions>;

  static State resolveActionOutcome(State current_state, Outcome outcome) noexcept
  {
    const auto transitions = kTransitionTable.find(current_state);
    if (transitions == kTransitionTable.end())
    {
      return State::ERROR;
    }

    switch (outcome)
    {
      case Outcome::SUCCEEDED:
        return transitions->second.succeeded;
      case Outcome::FAILED:
        return transitions->second.failed;
      case Outcome::PLANNED_ONLY:
        return transitions->second.planned_only;
    }

    return State::ERROR;
  }

  // Keys are explicit enum values, so enum declaration order does not affect
  // transitions. Each row gives the next state for {SUCCEEDED, FAILED,
  // PLANNED_ONLY} outcomes.
  inline static const TransitionTable kTransitionTable{
    { State::IDLE, { State::MOVE_ABOVE_OBJECT, State::MOVE_ABOVE_OBJECT, State::PLAN_ONLY_COMPLETE } },
    { State::MOVE_ABOVE_OBJECT, { State::DESCEND, State::ERROR, State::PLAN_ONLY_COMPLETE } },
    { State::DESCEND, { State::CLOSE_GRIPPER, State::CLOSE_GRIPPER, State::PLAN_ONLY_COMPLETE } },
    { State::CLOSE_GRIPPER, { State::ATTACH_GAZEBO, State::RECOVER_OPEN_GRIPPER, State::PLAN_ONLY_COMPLETE } },
    { State::ATTACH_GAZEBO, { State::ATTACH_MOVEIT, State::RECOVER_DETACH_MOVEIT, State::PLAN_ONLY_COMPLETE } },
    { State::ATTACH_MOVEIT, { State::LIFT, State::RECOVER_DETACH_MOVEIT, State::PLAN_ONLY_COMPLETE } },
    { State::LIFT, { State::MOVE_ABOVE_PLACE, State::MOVE_ABOVE_PLACE, State::PLAN_ONLY_COMPLETE } },
    { State::MOVE_ABOVE_PLACE, { State::DESCEND_TO_PLACE, State::DESCEND_TO_PLACE, State::PLAN_ONLY_COMPLETE } },
    { State::DESCEND_TO_PLACE, { State::OPEN_GRIPPER, State::OPEN_GRIPPER, State::PLAN_ONLY_COMPLETE } },
    { State::OPEN_GRIPPER, { State::DETACH_GAZEBO, State::ERROR, State::PLAN_ONLY_COMPLETE } },
    { State::DETACH_GAZEBO, { State::DETACH_MOVEIT, State::ERROR, State::PLAN_ONLY_COMPLETE } },
    { State::DETACH_MOVEIT, { State::SYNC_WORLD_OBJECT, State::ERROR, State::PLAN_ONLY_COMPLETE } },
    { State::SYNC_WORLD_OBJECT, { State::RETREAT, State::ERROR, State::PLAN_ONLY_COMPLETE } },
    { State::RETREAT, { State::DONE, State::ERROR, State::PLAN_ONLY_COMPLETE } },
    { State::DONE, { State::DONE, State::DONE, State::DONE } },
    { State::PLAN_ONLY_COMPLETE, { State::PLAN_ONLY_COMPLETE, State::PLAN_ONLY_COMPLETE, State::PLAN_ONLY_COMPLETE } },
    { State::RECOVER_DETACH_MOVEIT, { State::RECOVER_OPEN_GRIPPER, State::ERROR, State::ERROR } },
    { State::RECOVER_OPEN_GRIPPER, { State::RECOVER_DETACH_GAZEBO, State::ERROR, State::ERROR } },
    { State::RECOVER_DETACH_GAZEBO, { State::RECOVER_SYNC_WORLD_OBJECT, State::ERROR, State::ERROR } },
    { State::RECOVER_SYNC_WORLD_OBJECT, { State::RECOVER_RETREAT, State::ERROR, State::ERROR } },
    { State::RECOVER_RETREAT, { State::ERROR, State::ERROR, State::ERROR } },
    { State::ERROR, { State::ERROR, State::ERROR, State::ERROR } },
  };

  State current_state_{ State::IDLE };
};

using State = StateMachine::State;
using Outcome = StateMachine::Outcome;

class StateExecutor
{
public:
  virtual ~StateExecutor() = default;

  [[nodiscard]] virtual State state() const noexcept = 0;
  virtual Outcome execute() = 0;
};

class AlwaysFailExecutor final : public StateExecutor
{
public:
  explicit AlwaysFailExecutor(State state) : state_(state)
  {
  }

  [[nodiscard]] State state() const noexcept override
  {
    return state_;
  }

  Outcome execute() override
  {
    return Outcome::FAILED;
  }

private:
  State state_;
};

class AlwaysSucceedExecutor final : public StateExecutor
{
public:
  explicit AlwaysSucceedExecutor(State state) : state_(state)
  {
  }

  [[nodiscard]] State state() const noexcept override
  {
    return state_;
  }

  Outcome execute() override
  {
    return Outcome::SUCCEEDED;
  }

private:
  State state_;
};

class NodeSpinner
{
public:
  explicit NodeSpinner(const std::shared_ptr<rclcpp::Node>& node) : node_(node)
  {
    executor_.add_node(node_);
    spin_thread_ = std::thread([this]() { executor_.spin(); });
  }

  ~NodeSpinner()
  {
    executor_.cancel();
    if (spin_thread_.joinable())
    {
      spin_thread_.join();
    }
    executor_.remove_node(node_);
  }

  NodeSpinner(const NodeSpinner&) = delete;
  NodeSpinner& operator=(const NodeSpinner&) = delete;

private:
  std::shared_ptr<rclcpp::Node> node_;
  rclcpp::executors::SingleThreadedExecutor executor_;
  std::thread spin_thread_;
};

class MoveAboveObjectExecutor final : public StateExecutor
{
public:
  MoveAboveObjectExecutor(std::shared_ptr<rclcpp::Node> node, Mode mode) : node_(std::move(node)), mode_(mode)
  {
  }

  [[nodiscard]] State state() const noexcept override
  {
    return State::MOVE_ABOVE_OBJECT;
  }

  Outcome execute() override
  {
    if (mode_ != Mode::PLAN_ONLY)
    {
      return Outcome::FAILED;
    }

    return planMoveAboveObject();
  }

private:
  Outcome planMoveAboveObject()
  {
    NodeSpinner node_spinner(node_);
    const auto logger = node_->get_logger();
    using MoveGroupInterface = moveit::planning_interface::MoveGroupInterface;
    MoveGroupInterface move_group(node_, "panda_arm");

    if (!move_group.startStateMonitor(2.0))
    {
      RCLCPP_ERROR(logger, "Failed to start current state monitor");
      return Outcome::FAILED;
    }

    move_group.setPoseReferenceFrame("world");
    if (!move_group.setEndEffectorLink("panda_tcp"))
    {
      RCLCPP_ERROR(logger, "MoveIt RobotModel does not accept panda_tcp");
      return Outcome::FAILED;
    }

    geometry_msgs::msg::Pose pre_grasp_pose;
    pre_grasp_pose.position.x = 0.3;
    pre_grasp_pose.position.y = 0.0;
    pre_grasp_pose.position.z = 0.987;
    pre_grasp_pose.orientation.x = 1.0;
    pre_grasp_pose.orientation.y = 0.0;
    pre_grasp_pose.orientation.z = 0.0;
    pre_grasp_pose.orientation.w = 0.0;

    move_group.clearPoseTargets();
    move_group.setStartStateToCurrentState();
    if (!move_group.setPoseTarget(pre_grasp_pose, "panda_tcp"))
    {
      RCLCPP_ERROR(logger, "Failed to set panda_tcp pre-grasp pose target");
      return Outcome::FAILED;
    }

    MoveGroupInterface::Plan plan;
    const bool planning_succeeded = static_cast<bool>(move_group.plan(plan));
    const bool has_trajectory = !plan.trajectory.joint_trajectory.points.empty();
    if (!planning_succeeded || !has_trajectory)
    {
      RCLCPP_ERROR(logger, "Planning to pre-grasp failed or produced an empty trajectory");
      return Outcome::FAILED;
    }

    RCLCPP_INFO(logger, "Pre-grasp plan succeeded: %zu trajectory points; not executing",
                plan.trajectory.joint_trajectory.points.size());
    return Outcome::PLANNED_ONLY;
  }

  std::shared_ptr<rclcpp::Node> node_;
  Mode mode_;
};

class StateExecutorRegistry
{
public:
  StateExecutorRegistry(std::shared_ptr<rclcpp::Node> node, Mode mode) : node_(std::move(node)), mode_(mode)
  {
    for (const auto state : kStates)
    {
      executors_.emplace(state, createExecutor(state));
    }
  }

  Outcome execute(State state)
  {
    const auto executor = executors_.find(state);
    if (executor == executors_.end() || executor->second->state() != state)
    {
      return Outcome::FAILED;
    }

    return executor->second->execute();
  }

private:
  [[nodiscard]] std::unique_ptr<StateExecutor> createExecutor(State state) const
  {
    if (mode_ == Mode::PLAN_ONLY && state == State::MOVE_ABOVE_OBJECT)
    {
      return std::make_unique<MoveAboveObjectExecutor>(node_, mode_);
    }

    return std::make_unique<AlwaysSucceedExecutor>(state);
  }

  static constexpr std::array<State, 22> kStates{
    State::IDLE,
    State::MOVE_ABOVE_OBJECT,
    State::DESCEND,
    State::CLOSE_GRIPPER,
    State::ATTACH_GAZEBO,
    State::ATTACH_MOVEIT,
    State::LIFT,
    State::MOVE_ABOVE_PLACE,
    State::DESCEND_TO_PLACE,
    State::OPEN_GRIPPER,
    State::DETACH_GAZEBO,
    State::DETACH_MOVEIT,
    State::SYNC_WORLD_OBJECT,
    State::RETREAT,
    State::DONE,
    State::PLAN_ONLY_COMPLETE,
    State::RECOVER_DETACH_MOVEIT,
    State::RECOVER_OPEN_GRIPPER,
    State::RECOVER_DETACH_GAZEBO,
    State::RECOVER_SYNC_WORLD_OBJECT,
    State::RECOVER_RETREAT,
    State::ERROR,
  };

  std::shared_ptr<rclcpp::Node> node_;
  Mode mode_;
  std::map<State, std::unique_ptr<StateExecutor>> executors_;
};

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);

  const auto node = std::make_shared<rclcpp::Node>(
      "pick_place_state_machine", rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true));
  const auto logger = node->get_logger();

  const auto mode_parameter = node->get_parameter_or("mode", std::string(""));
  const auto mode = modeFromParameter(mode_parameter);
  if (!mode.has_value())
  {
    RCLCPP_ERROR(logger, "Unsupported mode: %s. Use dry_run or plan_only", mode_parameter.c_str());
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  if (*mode == Mode::EXECUTE)
  {
    RCLCPP_ERROR(logger, "Execution mode is not supported");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  StateExecutorRegistry executors(node, *mode);
  StateMachine state_machine;
  while (!state_machine.isTerminal())
  {
    const auto previous_state = state_machine.currentState();
    state_machine.advance(executors.execute(previous_state));
    RCLCPP_INFO(logger, "Current state: %s -> %s", StateMachine::toString(previous_state),
                StateMachine::toString(state_machine.currentState()));
  }

  const bool succeeded = state_machine.completedSuccessfully();
  rclcpp::shutdown();
  return succeeded ? EXIT_SUCCESS : EXIT_FAILURE;
}
