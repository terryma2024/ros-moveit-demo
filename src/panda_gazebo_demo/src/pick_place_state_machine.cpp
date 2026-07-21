#include <chrono>
#include <cstdlib>
#include <memory>
#include <string>
#include <thread>
#include <vector>
#include <cmath>

#include <geometry_msgs/msg/pose.hpp>
#include <moveit/move_group_interface/move_group_interface.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>
#include <moveit_msgs/msg/robot_trajectory.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp/executors/single_threaded_executor.hpp>

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

class StateMachine
{
public:
  State current_state;
  std::shared_ptr<rclcpp::Node> node;

  State next(Outcome outcome)
  {
    switch (current_state)
    {
      case State::IDLE:
        return State::MOVE_ABOVE_OBJECT;

      case State::MOVE_ABOVE_OBJECT:
        if (outcome == Outcome::FAILED)
        {
          return State::RECOVER_DETACH_MOVEIT;
        }
        else if (outcome == Outcome::PLANNED_ONLY)
        {
          return State::PLAN_ONLY_COMPLETE;
        }
        else
        {
          return State::DESCEND;
        }

      case State::DESCEND:
        return State::CLOSE_GRIPPER;

      case State::CLOSE_GRIPPER:
        return State::ATTACH_GAZEBO;

      case State::ATTACH_GAZEBO:
        return State::ATTACH_MOVEIT;

      case State::ATTACH_MOVEIT:
        if (outcome == Outcome::FAILED)
        {
          return State::RECOVER_DETACH_MOVEIT;
        }
        else if (outcome == Outcome::PLANNED_ONLY)
        {
          return State::PLAN_ONLY_COMPLETE;
        }
        else
        {
          return State::LIFT;
        }

      case State::LIFT:
        return State::MOVE_ABOVE_PLACE;

      case State::MOVE_ABOVE_PLACE:
        return State::DESCEND_TO_PLACE;

      case State::DESCEND_TO_PLACE:
        return State::OPEN_GRIPPER;

      case State::OPEN_GRIPPER:
        return State::DETACH_GAZEBO;

      case State::DETACH_GAZEBO:
        return State::DETACH_MOVEIT;

      case State::DETACH_MOVEIT:
        return State::SYNC_WORLD_OBJECT;

      case State::SYNC_WORLD_OBJECT:
        return State::RETREAT;

      case State::RETREAT:
        return State::DONE;

      case State::RECOVER_DETACH_MOVEIT:
        return State::RECOVER_OPEN_GRIPPER;

      case State::RECOVER_OPEN_GRIPPER:
        return State::RECOVER_DETACH_GAZEBO;

      case State::RECOVER_DETACH_GAZEBO:
        return State::RECOVER_SYNC_WORLD_OBJECT;

      case State::RECOVER_SYNC_WORLD_OBJECT:
        return State::RECOVER_RETREAT;

      case State::RECOVER_RETREAT:
        return State::ERROR;

      default:
        return State::ERROR;
    }
  }

  static std::string toString(State state)
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

      default:
        return "UNKNOWN";
    }
  }
};

Outcome runDryAction(State state, const std::string& fail_at)
{
  if (fail_at == StateMachine::toString(state))
  {
    return Outcome::FAILED;
  }
  else
  {
    return Outcome::SUCCEEDED;
  }
}

int main(int argc, char* argv[])
{
  rclcpp::init(argc, argv);

  auto node = std::make_shared<rclcpp::Node>(
      "pick_place_state_machine", rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true));

  const auto logger = node->get_logger();

  const bool dry_run = node->get_parameter_or("dry_run", false);
  const bool execute = node->get_parameter_or("execute", false);
  const auto fail_at = node->get_parameter_or("fail_at", std::string(""));

  if (!dry_run || execute)
  {
    RCLCPP_ERROR(logger, "Only dry-run is supported: require dry_run=true and execute=false");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  if (!fail_at.empty() && fail_at != StateMachine::toString(State::ATTACH_MOVEIT))
  {
    RCLCPP_ERROR(logger, "Unsupported fail_at: %s", fail_at.c_str());
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  StateMachine state_machine;
  state_machine.current_state = State::IDLE;
  state_machine.node = node;

  while (state_machine.current_state != State::DONE && state_machine.current_state != State::ERROR)
  {
    auto current_state = state_machine.current_state;
    state_machine.current_state = state_machine.next(runDryAction(state_machine.current_state, fail_at));
    RCLCPP_INFO(logger, "Current state: %s -> %s", StateMachine::toString(current_state).c_str(),
                StateMachine::toString(state_machine.current_state).c_str());
  }

  const bool succeeded = state_machine.current_state == State::DONE;
  rclcpp::shutdown();
  return succeeded ? EXIT_SUCCESS : EXIT_FAILURE;
}