#include "panda_gazebo_demo/pick_place/runtime_parameters.hpp"

#include <cmath>
#include <iomanip>
#include <limits>
#include <sstream>
#include <utility>

namespace panda_gazebo_demo::pick_place
{
namespace
{

std::optional<Failure> invalid(std::string message)
{
  return Failure{FailureCategory::CONFIGURATION, "INVALID_RUNTIME_PARAMETERS",
    std::move(message), {}};
}

bool positiveFinite(double value)
{
  return std::isfinite(value) && value > 0.0;
}

bool nonnegativeFinite(double value)
{
  return std::isfinite(value) && value >= 0.0;
}

}  // namespace

std::optional<Failure> validatePickPlaceParameters(
  const PickPlaceParameters & parameters)
{
  if (parameters.planning_group.empty() || parameters.tcp_link.empty() ||
    parameters.required_world_objects.empty() || parameters.gazebo_world_name.empty() ||
    parameters.gazebo_coke_model.empty() || parameters.gazebo_attach_topic.empty() ||
    parameters.gazebo_detach_topic.empty() || parameters.gazebo_attachment_topic.empty() ||
    parameters.gripper_action_name.empty())
  {
    return invalid("Runtime names, topics, links, groups, and required objects must be non-empty");
  }
  for (const auto & object : parameters.required_world_objects) {
    if (object.empty()) {
      return invalid("Required world object IDs must be non-empty");
    }
  }
  if (!positiveFinite(parameters.velocity_scaling) || parameters.velocity_scaling > 1.0 ||
    !positiveFinite(parameters.acceleration_scaling) || parameters.acceleration_scaling > 1.0)
  {
    return invalid("Velocity and acceleration scaling must be finite and in (0, 1]");
  }
  if (!positiveFinite(parameters.cartesian_eef_step) ||
    !positiveFinite(parameters.cartesian_min_fraction) ||
    parameters.cartesian_min_fraction > 1.0 ||
    !positiveFinite(parameters.joint_jump_threshold))
  {
    return invalid("Cartesian step, fraction, and joint-jump threshold are outside safe ranges");
  }
  if (!positiveFinite(parameters.tcp_position_tolerance) ||
    !positiveFinite(parameters.tcp_orientation_tolerance_rad) ||
    !positiveFinite(parameters.coke_position_tolerance) ||
    !positiveFinite(parameters.coke_orientation_tolerance_rad))
  {
    return invalid("TCP and Coke pose tolerances must be finite and positive");
  }
  if (!positiveFinite(parameters.gripper_open_position) ||
    !positiveFinite(parameters.gripper_open_min_position) ||
    parameters.gripper_open_min_position > parameters.gripper_open_position ||
    !nonnegativeFinite(parameters.gripper_close_position) ||
    parameters.gripper_close_position >= parameters.gripper_open_min_position ||
    !nonnegativeFinite(parameters.gripper_grasp_min_position) ||
    !positiveFinite(parameters.gripper_grasp_max_position) ||
    parameters.gripper_grasp_min_position >= parameters.gripper_grasp_max_position ||
    parameters.gripper_grasp_max_position > parameters.gripper_open_position ||
    !positiveFinite(parameters.gripper_symmetry_tolerance) ||
    !positiveFinite(parameters.joint_velocity_tolerance) ||
    !nonnegativeFinite(parameters.gripper_max_effort) ||
    !positiveFinite(parameters.gripper_action_timeout_seconds))
  {
    return invalid("Gripper positions, tolerances, effort, or timeout are outside safe ranges");
  }
  if (!positiveFinite(parameters.attachment_timeout_seconds) ||
    !positiveFinite(parameters.planning_scene_timeout_seconds) ||
    !positiveFinite(parameters.state_poll_interval_seconds) ||
    parameters.state_poll_interval_seconds > parameters.attachment_timeout_seconds ||
    parameters.state_poll_interval_seconds > parameters.planning_scene_timeout_seconds ||
    !positiveFinite(parameters.gazebo_observation_max_age_seconds))
  {
    return invalid("Attachment, Planning Scene, polling, and observation timing is invalid");
  }
  if (parameters.coke_settle_samples < 2 ||
    !positiveFinite(parameters.coke_settle_interval_seconds) ||
    !positiveFinite(parameters.coke_settle_position_tolerance) ||
    !positiveFinite(parameters.coke_settle_orientation_tolerance_rad))
  {
    return invalid("Coke settle sampling and tolerances are outside safe ranges");
  }
  if (!positiveFinite(parameters.recovery_safe_height) ||
    parameters.max_state_transitions == 0)
  {
    return invalid("Recovery safe height and maximum transitions must be positive");
  }
  return std::nullopt;
}

std::string pickPlaceConfigurationHash(
  const PickPlaceParameters & parameters,
  const std::string & target_policy_signature)
{
  std::ostringstream input;
  input << std::setprecision(std::numeric_limits<double>::max_digits10)
        << parameters.planning_group << '\n'
        << parameters.tcp_link << '\n'
        << parameters.velocity_scaling << '\n'
        << parameters.acceleration_scaling << '\n'
        << parameters.cartesian_eef_step << '\n'
        << parameters.cartesian_min_fraction << '\n'
        << parameters.joint_jump_threshold << '\n'
        << parameters.tcp_position_tolerance << '\n'
        << parameters.tcp_orientation_tolerance_rad << '\n'
        << parameters.coke_position_tolerance << '\n'
        << parameters.coke_orientation_tolerance_rad << '\n'
        << parameters.gripper_open_position << '\n'
        << parameters.gripper_open_min_position << '\n'
        << parameters.gripper_close_position << '\n'
        << parameters.gripper_grasp_min_position << '\n'
        << parameters.gripper_grasp_max_position << '\n'
        << parameters.gripper_symmetry_tolerance << '\n'
        << parameters.joint_velocity_tolerance << '\n'
        << parameters.gripper_max_effort << '\n'
        << parameters.gripper_action_timeout_seconds << '\n'
        << parameters.attachment_timeout_seconds << '\n'
        << parameters.planning_scene_timeout_seconds << '\n'
        << parameters.state_poll_interval_seconds << '\n'
        << parameters.gazebo_observation_max_age_seconds << '\n'
        << parameters.coke_settle_samples << '\n'
        << parameters.coke_settle_interval_seconds << '\n'
        << parameters.coke_settle_position_tolerance << '\n'
        << parameters.coke_settle_orientation_tolerance_rad << '\n'
        << parameters.recovery_safe_height << '\n'
        << parameters.gazebo_world_name << '\n'
        << parameters.gazebo_coke_model << '\n'
        << parameters.gazebo_attach_topic << '\n'
        << parameters.gazebo_detach_topic << '\n'
        << parameters.gazebo_attachment_topic << '\n'
        << parameters.gazebo_coke_initially_detached << '\n'
        << parameters.gripper_action_name << '\n'
        << parameters.max_state_transitions << '\n'
        << target_policy_signature;
  for (const auto & object : parameters.required_world_objects) {
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

}  // namespace panda_gazebo_demo::pick_place
