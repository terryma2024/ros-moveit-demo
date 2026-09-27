#include <gtest/gtest.h>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <hardware_interface/handle.hpp>
#include <hardware_interface/loaned_command_interface.hpp>
#include <hardware_interface/loaned_state_interface.hpp>
#include <pluginlib/class_loader.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>
#include <vector>

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

class ScopedReservationEnvironment
{
public:
  ScopedReservationEnvironment(const std::filesystem::path & directory, const char * session)
  {
    for (const auto * name : {"SO101_ACT_CONTROLLER_RESERVATION_DIR",
        "SO101_SIMULATION_SESSION_ID"})
    {
      const auto * previous = std::getenv(name);
      previous_.push_back({name, previous ? previous : "", previous != nullptr});
    }
    setenv("SO101_ACT_CONTROLLER_RESERVATION_DIR", directory.c_str(), 1);
    setenv("SO101_SIMULATION_SESSION_ID", session, 1);
  }

  ~ScopedReservationEnvironment()
  {
    for (const auto & item : previous_) {
      if (item.present) {setenv(item.name.c_str(), item.value.c_str(), 1);} else {
        unsetenv(item.name.c_str());
      }
    }
  }

private:
  struct Previous {std::string name; std::string value; bool present;};
  std::vector<Previous> previous_;
};

std::filesystem::path private_socket_directory()
{
  const auto * base = std::getenv("SO101_IPC_SOCKET_BASE");
  if (!base) {throw std::runtime_error("TEST_IPC_BASE_REQUIRED");}
  const auto suffix = std::chrono::steady_clock::now().time_since_epoch().count();
  const auto directory = std::filesystem::path(base) /
    ("p" + std::to_string(getpid()) + "-" + std::to_string(suffix));
  if (!std::filesystem::create_directory(directory) || chmod(directory.c_str(), 0700) != 0) {
    throw std::runtime_error("TEST_PRIVATE_DIRECTORY_FAILED");
  }
  return directory;
}

uint64_t self_start_ticks()
{
  std::ifstream input("/proc/self/stat");
  std::string line;
  std::getline(input, line);
  const auto closing = line.rfind(')');
  if (closing == std::string::npos) {throw std::runtime_error("TEST_START_TICKS_INVALID");}
  std::istringstream fields(line.substr(closing + 2));
  std::vector<std::string> values;
  for (std::string value; fields >> value; ) {
    values.push_back(value);
  }
  if (values.size() <= 19) {throw std::runtime_error("TEST_START_TICKS_INVALID");}
  return std::stoull(values[19]);
}

void append_big_endian(std::vector<uint8_t> & bytes, uint64_t value, size_t count)
{
  for (size_t shift = count; shift > 0; --shift) {
    bytes.push_back(static_cast<uint8_t>(value >> ((shift - 1) * 8)));
  }
}

void write_self_provision(const std::filesystem::path & path, uint8_t role)
{
  const std::string session = "session-17";
  std::vector<uint8_t> bytes{'S', 'O', 'P', 'R', 1, role,
    static_cast<uint8_t>(session.size()), 0};
  append_big_endian(bytes, geteuid(), 4);
  append_big_endian(bytes, getpid(), 4);
  append_big_endian(bytes, self_start_ticks(), 8);
  bytes.insert(bytes.end(), 32, 0xa5);
  bytes.insert(bytes.end(), session.begin(), session.end());
  std::ofstream output(path, std::ios::binary);
  output.write(reinterpret_cast<const char *>(bytes.data()), bytes.size());
  output.close();
  if (chmod(path.c_str(), 0600) != 0) {throw std::runtime_error("TEST_PROVISION_MODE_FAILED");}
}
}

TEST(BrokerOwnedTrajectoryController, ControllerBeforeBrokerStartsClosedRegistrationService)
{
  using namespace std::chrono_literals;
  const auto directory = private_socket_directory();
  const ScopedReservationEnvironment scope(directory, "session-17");
  const auto socket = directory / "arm.sock";
  ASSERT_LT(socket.string().size(), 108u);
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
  EXPECT_FALSE(std::filesystem::exists(socket));
  write_self_provision(directory / "arm.provision", 1);
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(controller.get_node()->get_node_base_interface());
  const auto deadline = std::chrono::steady_clock::now() + 2s;
  while (!std::filesystem::exists(socket) && std::chrono::steady_clock::now() < deadline) {
    executor.spin_some();
    std::this_thread::sleep_for(10ms);
  }
  ASSERT_TRUE(std::filesystem::exists(socket));
  Admission::GoalUUID id{};
  id.fill(1);
  EXPECT_EQ(controller.probe_goal(id, stationary_goal(), 1), Admission::Result::DENY_CLOSED);
  executor.remove_node(controller.get_node()->get_node_base_interface());
  ASSERT_EQ(controller.get_node()->cleanup().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_UNCONFIGURED);
  EXPECT_FALSE(std::filesystem::exists(socket));
  rclcpp::shutdown();
}

TEST(BrokerOwnedTrajectoryController, BrokerBeforeControllerStartsClosedRoleService)
{
  using namespace std::chrono_literals;
  const auto directory = private_socket_directory();
  write_self_provision(directory / "gripper.provision", 2);
  const ScopedReservationEnvironment scope(directory, "session-17");
  const auto socket = directory / "gripper.sock";
  ASSERT_LT(socket.string().size(), 108u);
  rclcpp::init(0, nullptr);
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"6"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
  });
  ASSERT_EQ(controller.init("gripper_controller", "", 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(controller.get_node()->get_node_base_interface());
  const auto deadline = std::chrono::steady_clock::now() + 2s;
  while (!std::filesystem::exists(socket) && std::chrono::steady_clock::now() < deadline) {
    executor.spin_some();
    std::this_thread::sleep_for(10ms);
  }
  ASSERT_TRUE(std::filesystem::exists(socket));
  Admission::GoalUUID id{};
  id.fill(2);
  EXPECT_EQ(controller.probe_goal(id, stationary_goal(), 1), Admission::Result::DENY_CLOSED);
  executor.remove_node(controller.get_node()->get_node_base_interface());
  ASSERT_EQ(controller.on_error(rclcpp_lifecycle::State()),
    controller_interface::CallbackReturn::SUCCESS);
  EXPECT_FALSE(std::filesystem::exists(socket));
  rclcpp::shutdown();
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
  id.fill(6);
  ASSERT_TRUE(controller.reserve_goal(id, goal, 4));
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_EQ(controller.probe_goal(id, goal, 4), Admission::Result::DENY_CLOSED);
  rclcpp::shutdown();
}
