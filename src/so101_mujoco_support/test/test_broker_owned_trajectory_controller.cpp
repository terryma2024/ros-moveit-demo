#include <gtest/gtest.h>
#include <chrono>
#include <hardware_interface/handle.hpp>
#include <hardware_interface/loaned_command_interface.hpp>
#include <hardware_interface/loaned_state_interface.hpp>
#include <pluginlib/class_loader.hpp>
#include <rclcpp/rclcpp.hpp>

#include "so101_mujoco_support/broker_owned_trajectory_controller.hpp"
#include "so101_mujoco_support/controller_goal_admission.hpp"

namespace
{
using Action = control_msgs::action::FollowJointTrajectory;
using SendGoal = Action::Impl::SendGoalService;
using Admission = so101_mujoco_support::ControllerGoalAdmission;

class InspectableController : public so101_mujoco_support::BrokerOwnedTrajectoryController
{
public:
  bool topic_subscriber_exists() const {return static_cast<bool>(joint_command_subscriber_);}
  bool action_server_exists() const {return static_cast<bool>(action_server_);}
  bool reserve_goal(const Admission::GoalUUID & id, const Action::Goal & goal, uint64_t generation)
  {
    return goal_admission_.arm(generation) && goal_admission_.reserve(id, goal, generation);
  }
  Admission::Result probe_goal(
    const Admission::GoalUUID & id, const Action::Goal & goal, uint64_t generation)
  {
    return goal_admission_.admit(id, goal, generation);
  }
};

Action::Goal stationary_goal()
{
  Action::Goal goal;
  goal.trajectory.joint_names = {"1", "2", "3", "4", "5"};
  trajectory_msgs::msg::JointTrajectoryPoint point;
  point.positions = {0.0, 0.0, 0.0, 0.0, 0.0};
  point.time_from_start.sec = 1;
  goal.trajectory.points = {point};
  return goal;
}
}

TEST(BrokerOwnedTrajectoryController, ConfigureHasNoTopicCommandIngress)
{
  rclcpp::init(0, nullptr);
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"1", "2", "3", "4", "5"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
  });
  ASSERT_EQ(controller.init("arm_controller", "", 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(controller.topic_subscriber_exists());
  EXPECT_EQ(controller.get_node()->count_subscribers("/arm_controller/joint_trajectory"), 0U);
  EXPECT_TRUE(controller.action_server_exists());
  rclcpp::shutdown();
}

TEST(BrokerOwnedTrajectoryController, RegisteredForControllerManager)
{
  pluginlib::ClassLoader<controller_interface::ControllerInterface> loader(
    "controller_interface", "controller_interface::ControllerInterface");
  ASSERT_TRUE(loader.isClassAvailable("so101_mujoco_support/BrokerOwnedTrajectoryController"));
  EXPECT_NE(loader.createSharedInstance(
    "so101_mujoco_support/BrokerOwnedTrajectoryController"), nullptr);
}

TEST(BrokerOwnedTrajectoryController, ActionIngressConsumesOrClosesReservationBeforeBaseCallback)
{
  using namespace std::chrono_literals;
  rclcpp::init(0, nullptr);
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"1", "2", "3", "4", "5"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
  });
  ASSERT_EQ(controller.init("arm_controller", "", 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  auto client_node = std::make_shared<rclcpp::Node>("goal_ingress_test_client");
  auto client = client_node->create_client<SendGoal>(
    "/arm_controller/follow_joint_trajectory/_action/send_goal");
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(controller.get_node()->get_node_base_interface());
  executor.add_node(client_node);
  ASSERT_TRUE(client->wait_for_service(2s));
  EXPECT_EQ(client_node->count_services(
      "/arm_controller/follow_joint_trajectory/_action/send_goal"), 1u);

  const auto goal = stationary_goal();
  Admission::GoalUUID id{};
  id.fill(1);
  ASSERT_TRUE(controller.reserve_goal(id, goal, 1));
  auto altered = goal;
  altered.trajectory.points[0].positions[0] = 0.1;
  auto request = std::make_shared<SendGoal::Request>();
  request->goal_id.uuid = id;
  request->goal = altered;
  auto response = client->async_send_request(request);
  ASSERT_EQ(executor.spin_until_future_complete(response, 2s),
    rclcpp::FutureReturnCode::SUCCESS);
  EXPECT_FALSE(response.get()->accepted);
  EXPECT_EQ(controller.probe_goal(id, goal, 1), Admission::Result::DENY_CLOSED);

  id.fill(2);
  ASSERT_TRUE(controller.reserve_goal(id, goal, 2));
  request = std::make_shared<SendGoal::Request>();
  request->goal_id.uuid = id;
  request->goal = goal;
  response = client->async_send_request(request);
  ASSERT_EQ(executor.spin_until_future_complete(response, 2s),
    rclcpp::FutureReturnCode::SUCCESS);
  EXPECT_FALSE(response.get()->accepted);
  EXPECT_EQ(controller.probe_goal(id, goal, 2), Admission::Result::DENY_FAULT);
  executor.remove_node(client_node);
  executor.remove_node(controller.get_node()->get_node_base_interface());
  rclcpp::shutdown();
}

TEST(BrokerOwnedTrajectoryController, LifecycleTransitionsRevokePendingGoals)
{
  rclcpp::init(0, nullptr);
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"1", "2", "3", "4", "5"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
  });
  ASSERT_EQ(controller.init("lifecycle_controller", "", 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);

  std::vector<hardware_interface::CommandInterface::SharedPtr> command_backing;
  std::vector<hardware_interface::StateInterface::SharedPtr> state_backing;
  std::vector<hardware_interface::LoanedCommandInterface> commands;
  std::vector<hardware_interface::LoanedStateInterface> states;
  for (const auto & joint : std::vector<std::string>{"1", "2", "3", "4", "5"}) {
    hardware_interface::InterfaceInfo position;
    position.name = "position";
    position.initial_value = "0";
    hardware_interface::InterfaceInfo velocity;
    velocity.name = "velocity";
    velocity.initial_value = "0";
    auto command = std::make_shared<hardware_interface::CommandInterface>(
      hardware_interface::InterfaceDescription(joint, position));
    auto state_position = std::make_shared<hardware_interface::StateInterface>(
      hardware_interface::InterfaceDescription(joint, position));
    auto state_velocity = std::make_shared<hardware_interface::StateInterface>(
      hardware_interface::InterfaceDescription(joint, velocity));
    command_backing.push_back(command);
    state_backing.push_back(state_position);
    state_backing.push_back(state_velocity);
    commands.emplace_back(command, []() {});
    states.emplace_back(state_position);
    states.emplace_back(state_velocity);
  }
  controller.assign_interfaces(std::move(commands), std::move(states));
  ASSERT_EQ(controller.get_node()->activate().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);

  const auto goal = stationary_goal();
  Admission::GoalUUID id{};
  id.fill(3);
  ASSERT_TRUE(controller.reserve_goal(id, goal, 1));
  ASSERT_EQ(controller.get_node()->deactivate().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_EQ(controller.probe_goal(id, goal, 1), Admission::Result::DENY_CLOSED);

  id.fill(4);
  ASSERT_TRUE(controller.reserve_goal(id, goal, 2));
  EXPECT_EQ(controller.on_error(rclcpp_lifecycle::State()),
    controller_interface::CallbackReturn::SUCCESS);
  EXPECT_EQ(controller.probe_goal(id, goal, 2), Admission::Result::DENY_CLOSED);

  id.fill(5);
  ASSERT_TRUE(controller.reserve_goal(id, goal, 3));
  ASSERT_EQ(controller.get_node()->cleanup().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_UNCONFIGURED);
  EXPECT_EQ(controller.probe_goal(id, goal, 3), Admission::Result::DENY_CLOSED);
  controller.release_interfaces();
  rclcpp::shutdown();
}
