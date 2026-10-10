#include <gtest/gtest.h>

#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

#include <chrono>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <functional>
#include <future>
#include <limits>
#include <memory>
#include <string>
#include <thread>
#include <vector>

#include <control_msgs/action/follow_joint_trajectory.hpp>
#include <control_msgs/msg/speed_scaling_factor.hpp>
#include <hardware_interface/handle.hpp>
#include <hardware_interface/loaned_command_interface.hpp>
#include <hardware_interface/loaned_state_interface.hpp>
#include <lifecycle_msgs/msg/state.hpp>
#include <pluginlib/class_loader.hpp>
#include <rcl_interfaces/srv/get_parameters.hpp>
#include <rcl_interfaces/srv/set_parameters.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>

#include "so101_mujoco_support/head_neck_trajectory_controller.hpp"

namespace
{
using namespace std::chrono_literals;
using Action = control_msgs::action::FollowJointTrajectory;
using so101_mujoco_support::HeadNeckTrajectoryController;

std::string continuous_neck_urdf()
{
  return "<robot name='neck_test'><link name='base'/><link name='head'/>"
         "<joint name='neck_yaw_joint' type='continuous'><parent link='base'/><child link='head'/>"
         "<origin xyz='0 0 0' rpy='0 0 0'/><axis xyz='0 0 1'/></joint></robot>";
}

class Neck : public HeadNeckTrajectoryController
{
public:
  using HeadNeckTrajectoryController::ErrorReason;
  bool topic_subscriber_exists() const {return static_cast<bool>(joint_command_subscriber_);}
  bool query_service_exists() const {return static_cast<bool>(query_state_srv_);}
  bool action_server_exists() const {return static_cast<bool>(action_server_);}
  bool wraps() const {return joints_angle_wraparound_.at(0);}
  void force_scaling(double value) {scaling_factor_.store(value);}
  void force_scaling_command(double value) {scaling_factor_cmd_.store(value);}
  void force_desired_position(double value) {state_desired_.positions.at(0) = value;}
  double desired_velocity() const {return state_desired_.velocities.at(0);}
  double desired_position() const {return state_desired_.positions.at(0);}
  bool holding() const {return rt_is_holding_.load();}
  ErrorReason error_reason() const {return last_error_reason();}
  uint64_t rejected() const {return goals_rejected();}
  uint64_t activations() const {return activation_id();}
  std::shared_ptr<so101_mujoco_support::NeckDeadman> deadman() const {return deadman_copy();}
  bool goal_decision_admits() const {return goal_admitted();}
};

std::filesystem::path private_directory()
{
  char pattern[] = "/tmp/so101-neck-XXXXXX";
  if (mkdtemp(pattern) == nullptr) {throw std::runtime_error("TEST_DIR_FAILED");}
  chmod(pattern, 0700);
  return pattern;
}

int connect_to(const std::filesystem::path & path)
{
  const int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  sockaddr_un address{};
  address.sun_family = AF_UNIX;
  std::strncpy(address.sun_path, path.c_str(), sizeof(address.sun_path) - 1);
  if (connect(fd, reinterpret_cast<sockaddr *>(&address), sizeof(address)) != 0) {
    close(fd);
    return -1;
  }
  return fd;
}

bool wait_until(const std::function<bool()> & predicate, std::chrono::milliseconds limit = 2000ms)
{
  const auto deadline = std::chrono::steady_clock::now() + limit;
  while (std::chrono::steady_clock::now() < deadline) {
    if (predicate()) {return true;}
    std::this_thread::sleep_for(1ms);
  }
  return predicate();
}

struct Options
{
  bool continuous{true};
  std::vector<rclcpp::Parameter> extra;
  bool directory{true};
  double timeout_s{0.2};
};

// One controller, its interfaces, an executor thread and an action client in this process.
class Rig
{
public:
  explicit Rig(Options options = {}) : directory(private_directory())
  {
    if (!rclcpp::ok()) {rclcpp::init(0, nullptr);}
    std::vector<rclcpp::Parameter> parameters{
      rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
      rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
      rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
      rclcpp::Parameter("head_deadman_timeout_s", options.timeout_s),
    };
    if (options.directory) {
      parameters.emplace_back("head_deadman_directory", directory.string());
    }
    for (const auto & item : options.extra) {parameters.push_back(item);}
    rclcpp::NodeOptions node_options;
    node_options.parameter_overrides(parameters);
    EXPECT_EQ(controller.init("neck_controller",
      options.continuous ? continuous_neck_urdf() :
      "<robot name='n'><link name='base'/><link name='head'/><joint name='neck_yaw_joint' type='revolute'>"
      "<parent link='base'/><child link='head'/><origin xyz='0 0 0' rpy='0 0 0'/><axis xyz='0 0 1'/>"
      "<limit lower='-3' upper='3' effort='1' velocity='1'/></joint></robot>",
      500, "", node_options), controller_interface::return_type::OK);
    hardware_interface::InterfaceInfo position;
    position.name = "position";
    position.initial_value = "0.1";
    hardware_interface::InterfaceInfo velocity;
    velocity.name = "velocity";
    velocity.initial_value = "0";
    command = std::make_shared<hardware_interface::CommandInterface>(
      hardware_interface::InterfaceDescription("neck_yaw_joint", position));
    state_position = std::make_shared<hardware_interface::StateInterface>(
      hardware_interface::InterfaceDescription("neck_yaw_joint", position));
    state_velocity = std::make_shared<hardware_interface::StateInterface>(
      hardware_interface::InterfaceDescription("neck_yaw_joint", velocity));
  }

  ~Rig()
  {
    stop_spinning();
    for (const int fd : owners) {if (fd >= 0) {close(fd);}}
    client.reset();
    client_node.reset();
  }

  bool configure()
  {
    return controller.configure().id() == lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE;
  }

  void assign()
  {
    std::vector<hardware_interface::LoanedCommandInterface> commands;
    std::vector<hardware_interface::LoanedStateInterface> states;
    commands.emplace_back(command, []() {});
    states.emplace_back(state_position);
    states.emplace_back(state_velocity);
    controller.assign_interfaces(std::move(commands), std::move(states));
  }

  bool set_pid(pid_t pid)
  {
    return controller.get_node()->set_parameter(
      rclcpp::Parameter("head_deadman_peer_pid", static_cast<int64_t>(pid))).successful;
  }

  bool activate(pid_t pid = getpid())
  {
    if (pid > 0 && !set_pid(pid)) {return false;}
    assign();
    return controller.get_node()->activate().id() ==
           lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE;
  }

  void deactivate()
  {
    controller.get_node()->deactivate();
    controller.release_interfaces();
  }

  int connect_owner()
  {
    const auto deadman = controller.deadman();
    const int fd = connect_to(deadman->socket_path());
    owners.push_back(fd);
    return fd;
  }

  void heartbeat(int fd) {char byte = 'h'; (void)!write(fd, &byte, 1);}

  void start_spinning()
  {
    client_node = rclcpp::Node::make_shared("neck_test_client");
    client = rclcpp_action::create_client<Action>(client_node, "/neck_controller/follow_joint_trajectory");
    executor = std::make_unique<rclcpp::executors::SingleThreadedExecutor>();
    executor->add_node(controller.get_node()->get_node_base_interface());
    executor->add_node(client_node);
    spinning = true;
    spinner = std::thread([this] {executor->spin();});
  }

  void stop_spinning()
  {
    if (spinning) {
      executor->cancel();
      spinner.join();
      executor.reset();
      spinning = false;
    }
  }

  controller_interface::return_type raw_update()
  {
    ++step;
    return controller.update(rclcpp::Time(static_cast<int64_t>(step * 2000000), RCL_ROS_TIME),
        rclcpp::Duration::from_seconds(0.002));
  }

  controller_interface::return_type tick()
  {
    ++step;
    // a perfect plant: the measured position follows the command
    const auto written = command->get_optional();
    if (written.has_value() && std::isfinite(written.value())) {
      const double previous = state_position->get_optional().value_or(0.0);
      state_position->set_value(written.value());
      state_velocity->set_value((written.value() - previous) / 0.002);
    }
    return controller.update(rclcpp::Time(static_cast<int64_t>(step * 2000000), RCL_ROS_TIME),
        rclcpp::Duration::from_seconds(0.002));
  }

  void run_ticks(int count)
  {
    for (int i = 0; i < count; ++i) {
      ASSERT_EQ(tick(), controller_interface::return_type::OK);
    }
  }

  Action::Goal goal(double target = 0.3, double seconds = 2.0)
  {
    Action::Goal value;
    value.trajectory.joint_names = {"neck_yaw_joint"};
    trajectory_msgs::msg::JointTrajectoryPoint point;
    point.positions = {target};
    point.velocities = {0.0};
    point.time_from_start.sec = static_cast<int32_t>(seconds);
    point.time_from_start.nanosec = static_cast<uint32_t>((seconds - std::floor(seconds)) * 1e9);
    value.trajectory.points = {point};
    return value;
  }

  // Returns the goal handle, or nullptr when the goal was rejected.
  rclcpp_action::ClientGoalHandle<Action>::SharedPtr send(const Action::Goal & value)
  {
    if (!client->wait_for_action_server(2s)) {return nullptr;}
    auto future = client->async_send_goal(value);
    if (future.wait_for(2s) != std::future_status::ready) {return nullptr;}
    return future.get();
  }

  std::filesystem::path directory;
  Neck controller;
  std::shared_ptr<hardware_interface::CommandInterface> command;
  std::shared_ptr<hardware_interface::StateInterface> state_position, state_velocity;
  std::unique_ptr<rclcpp::executors::SingleThreadedExecutor> executor;
  std::shared_ptr<rclcpp::Node> client_node;
  rclcpp_action::Client<Action>::SharedPtr client;
  std::thread spinner;
  bool spinning{false};
  std::vector<int> owners;
  int64_t step{0};
};

class RclcppEnvironment : public ::testing::Environment
{
public:
  void TearDown() override {rclcpp::shutdown();}
};
const auto * const kEnvironment = ::testing::AddGlobalTestEnvironment(new RclcppEnvironment);
}  // namespace

// ---- input closure -------------------------------------------------------------------------------

TEST(HeadNeckTrajectoryController, RegisteredForTheControllerManager)
{
  pluginlib::ClassLoader<controller_interface::ControllerInterface> loader(
    "controller_interface", "controller_interface::ControllerInterface");
  ASSERT_TRUE(loader.isClassAvailable("so101_mujoco_support/HeadNeckTrajectoryController"));
  EXPECT_NE(loader.createSharedInstance("so101_mujoco_support/HeadNeckTrajectoryController"), nullptr);
}

TEST(HeadNeckTrajectoryController, ConfigureLeavesNoTopicCommandSubscription)
{
  Rig rig;
  ASSERT_TRUE(rig.configure());
  EXPECT_FALSE(rig.controller.topic_subscriber_exists());
  EXPECT_EQ(rig.controller.get_node()->count_subscribers("/neck_controller/joint_trajectory"), 0U);
  EXPECT_TRUE(rig.controller.get_node()->get_subscriptions_info_by_topic(
      "/neck_controller/joint_trajectory").empty());
  EXPECT_TRUE(rig.controller.action_server_exists());
}

TEST(HeadNeckTrajectoryController, ConfigureLeavesNoSpeedScalingSubscriptionAndNoQueryService)
{
  Rig rig;
  ASSERT_TRUE(rig.configure());
  const auto node = rig.controller.get_node();
  EXPECT_TRUE(node->get_subscriptions_info_by_topic("/neck_controller/speed_scaling_input").empty());
  EXPECT_FALSE(rig.controller.query_service_exists());
  // publishing a factor reaches nobody
  auto probe = rclcpp::Node::make_shared("scaling_probe");
  auto publisher = probe->create_publisher<control_msgs::msg::SpeedScalingFactor>(
    "/neck_controller/speed_scaling_input", rclcpp::SystemDefaultsQoS().transient_local());
  control_msgs::msg::SpeedScalingFactor message;
  message.factor = 2.0;
  publisher->publish(message);
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node->get_node_base_interface());
  executor.add_node(probe);
  for (int i = 0; i < 20; ++i) {executor.spin_some(); std::this_thread::sleep_for(5ms);}
  EXPECT_EQ(publisher->get_subscription_count(), 0U);
  EXPECT_TRUE(node->get_subscriptions_info_by_topic("/neck_controller/speed_scaling_input").empty());
}

TEST(HeadNeckTrajectoryController, AngleWraparoundIsOffAfterEveryConfigureOfAContinuousJoint)
{
  Rig rig;
  ASSERT_TRUE(rig.configure());
  EXPECT_FALSE(rig.controller.wraps());
  ASSERT_EQ(rig.controller.get_node()->cleanup().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_UNCONFIGURED);
  ASSERT_TRUE(rig.configure());
  EXPECT_FALSE(rig.controller.wraps());
  EXPECT_EQ(rig.controller.get_node()->count_subscribers("/neck_controller/joint_trajectory"), 0U);
}

TEST(HeadNeckTrajectoryController, TheImmutableConfigurationIsCheckedAtConfigure)
{
  const std::vector<rclcpp::Parameter> bad[] = {
    {rclcpp::Parameter("interpolate_from_desired_state", true)},
    {rclcpp::Parameter("open_loop_control", true)},
    {rclcpp::Parameter("allow_integration_in_goal_trajectories", true)},
    {rclcpp::Parameter("allow_partial_joints_goal", true)},
    {rclcpp::Parameter("interpolation_method", "none")},
    {rclcpp::Parameter("speed_scaling.initial_scaling_factor", 0.5)},
  };
  for (const auto & extra : bad) {
    Options options;
    options.extra = extra;
    Rig rig(options);
    EXPECT_FALSE(rig.configure()) << extra[0].get_name();
  }
  Options no_directory;
  no_directory.directory = false;
  Rig missing(no_directory);
  EXPECT_FALSE(missing.configure());
  Options relative;
  relative.extra = {rclcpp::Parameter("head_deadman_directory", "relative/dir")};
  Rig bad_directory(relative);
  EXPECT_FALSE(bad_directory.configure());
}

TEST(HeadNeckTrajectoryController, TheFrozenParametersRefuseChangesAfterConfigure)
{
  Rig rig;
  ASSERT_TRUE(rig.configure());
  const auto node = rig.controller.get_node();
  for (const char * name : {"open_loop_control", "interpolate_from_desired_state",
      "allow_integration_in_goal_trajectories", "allow_partial_joints_goal"})
  {
    EXPECT_FALSE(node->set_parameter(rclcpp::Parameter(name, true)).successful) << name;
  }
  EXPECT_FALSE(node->set_parameter(rclcpp::Parameter("interpolation_method", "none")).successful);
  EXPECT_FALSE(node->set_parameter(rclcpp::Parameter("head_deadman_directory", "/tmp")).successful);
  EXPECT_FALSE(node->set_parameter(rclcpp::Parameter("head_deadman_timeout_s", 0.9)).successful);
  EXPECT_FALSE(node->set_parameter(rclcpp::Parameter("head_activation_id", int64_t(5))).successful);
}

// ---- per-tick refusals -----------------------------------------------------------------------------

TEST(HeadNeckTrajectoryController, AForcedScalingFactorOtherThanOneReturnsError)
{
  Rig rig;
  ASSERT_TRUE(rig.configure());
  ASSERT_TRUE(rig.activate());
  rig.run_ticks(5);
  rig.controller.force_scaling(0.5);
  EXPECT_EQ(rig.tick(), controller_interface::return_type::ERROR);
  EXPECT_EQ(rig.controller.error_reason(), Neck::ErrorReason::SCALING_FACTOR);
  rig.controller.force_scaling(1.0);
  rig.controller.force_scaling_command(2.0);
  EXPECT_EQ(rig.tick(), controller_interface::return_type::ERROR);
  rig.controller.force_scaling_command(1.0);
  EXPECT_EQ(rig.tick(), controller_interface::return_type::OK);
}

TEST(HeadNeckTrajectoryController, ANonFiniteMeasurementReturnsErrorWithoutAnyNonFiniteCommand)
{
  Rig rig;
  ASSERT_TRUE(rig.configure());
  ASSERT_TRUE(rig.activate());
  rig.run_ticks(10);
  const double before = rig.command->get_optional().value();
  ASSERT_TRUE(std::isfinite(before));
  ASSERT_TRUE(rig.state_position->set_value(std::numeric_limits<double>::quiet_NaN()));
  EXPECT_EQ(rig.controller.update(rclcpp::Time(int64_t(1000000000), RCL_ROS_TIME),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::ERROR);
  EXPECT_EQ(rig.controller.error_reason(), Neck::ErrorReason::NON_FINITE_STATE);
  EXPECT_EQ(rig.command->get_optional().value(), before);
  // the controller manager now deactivates a controller that returned ERROR
  rig.deactivate();
  const auto after = rig.command->get_optional();
  ASSERT_TRUE(after.has_value());
  EXPECT_TRUE(std::isfinite(after.value()));
  EXPECT_EQ(after.value(), before);
}

TEST(HeadNeckTrajectoryController, ANonFiniteVelocityOrCommandedStateAlsoReturnsError)
{
  Rig rig;
  ASSERT_TRUE(rig.configure());
  ASSERT_TRUE(rig.activate());
  rig.run_ticks(5);
  ASSERT_TRUE(rig.state_velocity->set_value(std::numeric_limits<double>::infinity()));
  EXPECT_EQ(rig.raw_update(), controller_interface::return_type::ERROR);
  ASSERT_TRUE(rig.state_velocity->set_value(0.0));
  EXPECT_EQ(rig.raw_update(), controller_interface::return_type::OK);
  rig.controller.force_desired_position(std::numeric_limits<double>::quiet_NaN());
  EXPECT_EQ(rig.raw_update(), controller_interface::return_type::ERROR);
  EXPECT_EQ(rig.controller.error_reason(), Neck::ErrorReason::NON_FINITE_COMMANDED_STATE);
}

TEST(HeadNeckTrajectoryController, ADeactivationNeverForwardsANonFiniteCommand)
{
  Rig rig;
  ASSERT_TRUE(rig.configure());
  ASSERT_TRUE(rig.activate());
  rig.run_ticks(10);
  const double last_finite = rig.command->get_optional().value();
  ASSERT_TRUE(rig.command->set_value(std::numeric_limits<double>::quiet_NaN()));
  rig.deactivate();
  const auto after = rig.command->get_optional();
  ASSERT_TRUE(after.has_value());
  EXPECT_TRUE(std::isfinite(after.value()));
  EXPECT_EQ(after.value(), last_finite);
}

// ---- goal admission and the dead-man ---------------------------------------------------------------

TEST(HeadNeckTrajectoryController, AGoalBeforeTheOwnerConnectsIsRejected)
{
  Rig rig;
  ASSERT_TRUE(rig.configure());
  ASSERT_TRUE(rig.activate());
  rig.start_spinning();
  EXPECT_FALSE(rig.controller.goal_decision_admits());
  EXPECT_EQ(rig.send(rig.goal()), nullptr);
  EXPECT_GE(rig.controller.rejected(), 1u);
}

TEST(HeadNeckTrajectoryController, AGoalIsAcceptedOnlyWhileTheOwnerIsConnectedAndUnlatched)
{
  Rig rig;
  ASSERT_TRUE(rig.configure());
  ASSERT_TRUE(rig.activate());
  rig.start_spinning();
  const int owner = rig.connect_owner();
  ASSERT_GE(owner, 0);
  ASSERT_TRUE(wait_until([&] {return rig.controller.goal_decision_admits();}));
  const auto handle = rig.send(rig.goal());
  ASSERT_NE(handle, nullptr);
  EXPECT_EQ(rig.controller.rejected(), 0u);
}

TEST(HeadNeckTrajectoryController, ASecondPeerIsRefusedAndAWrongPidNeverAdmitsGoals)
{
  {
    Rig rig;
    ASSERT_TRUE(rig.configure());
    ASSERT_TRUE(rig.activate());
    const int first = rig.connect_owner();
    ASSERT_TRUE(wait_until([&] {return rig.controller.goal_decision_admits();}));
    const int second = rig.connect_owner();
    ASSERT_GE(second, 0);
    ASSERT_TRUE(wait_until([&] {return rig.controller.deadman()->refused_peers() == 1;}));
    EXPECT_TRUE(rig.controller.goal_decision_admits());
    (void)first;
  }

  Rig wrong;
  ASSERT_TRUE(wrong.configure());
  ASSERT_TRUE(wrong.activate(getpid() + 1));  // the named peer is some other process
  const int stranger = wrong.connect_owner();
  ASSERT_GE(stranger, 0);
  ASSERT_TRUE(wait_until([&] {return wrong.controller.deadman()->refused_peers() == 1;}));
  EXPECT_FALSE(wrong.controller.goal_decision_admits());
}

TEST(HeadNeckTrajectoryController, AnEofLatchAbortsTheActiveGoalHoldsAndRejectsTheNextGoal)
{
  Rig rig;
  ASSERT_TRUE(rig.configure());
  ASSERT_TRUE(rig.activate());
  rig.start_spinning();
  const int owner = rig.connect_owner();
  ASSERT_TRUE(wait_until([&] {return rig.controller.goal_decision_admits();}));
  const auto handle = rig.send(rig.goal(0.5, 3.0));
  ASSERT_NE(handle, nullptr);
  auto result_future = rig.client->async_get_result(handle);
  for (int i = 0; i < 400; ++i) {
    ASSERT_EQ(rig.tick(), controller_interface::return_type::OK);
    if (i % 10 == 0) {rig.heartbeat(owner);}
    std::this_thread::sleep_for(500us);
  }
  EXPECT_GT(std::abs(rig.controller.desired_velocity()), 0.0) << "the goal is moving";
  close(owner);
  rig.owners.clear();
  ASSERT_TRUE(wait_until([&] {return rig.controller.deadman()->latched();}));
  // within two controller ticks of the latch the goal is aborted and the reference is at rest
  rig.tick();
  rig.tick();
  EXPECT_TRUE(rig.controller.holding());
  EXPECT_NEAR(rig.controller.desired_velocity(), 0.0, 1e-9);
  ASSERT_EQ(result_future.wait_for(3s), std::future_status::ready);
  EXPECT_EQ(result_future.get().code, rclcpp_action::ResultCode::ABORTED);
  EXPECT_FALSE(rig.controller.goal_decision_admits());
  EXPECT_EQ(rig.send(rig.goal()), nullptr);
  const double held = rig.controller.desired_position();
  rig.run_ticks(50);
  EXPECT_DOUBLE_EQ(rig.controller.desired_position(), held);
}

TEST(HeadNeckTrajectoryController, SilenceLatchesAfterTheTimeoutAndStopsTheGoal)
{
  Options options;
  options.timeout_s = 0.1;
  Rig rig(options);
  ASSERT_TRUE(rig.configure());
  ASSERT_TRUE(rig.activate());
  rig.start_spinning();
  const int owner = rig.connect_owner();
  rig.heartbeat(owner);
  ASSERT_TRUE(wait_until([&] {return rig.controller.goal_decision_admits();}));
  const auto handle = rig.send(rig.goal(0.5, 3.0));
  ASSERT_NE(handle, nullptr);
  auto result_future = rig.client->async_get_result(handle);
  const auto begin = std::chrono::steady_clock::now();
  while (!rig.controller.deadman()->latched() &&
    std::chrono::steady_clock::now() - begin < 1s)
  {
    ASSERT_EQ(rig.tick(), controller_interface::return_type::OK);
    std::this_thread::sleep_for(1ms);
  }
  ASSERT_TRUE(rig.controller.deadman()->latched());
  const auto elapsed = std::chrono::steady_clock::now() - begin;
  EXPECT_GE(elapsed, 90ms);
  EXPECT_LE(elapsed, 200ms);
  EXPECT_EQ(rig.controller.deadman()->latch_reason(),
    so101_mujoco_support::NeckDeadman::LatchReason::TIMEOUT);
  rig.tick();
  rig.tick();
  EXPECT_NEAR(rig.controller.desired_velocity(), 0.0, 1e-9);
  ASSERT_EQ(result_future.wait_for(3s), std::future_status::ready);
  EXPECT_EQ(result_future.get().code, rclcpp_action::ResultCode::ABORTED);
}

TEST(HeadNeckTrajectoryController, ReactivationNeedsANewPidANewSocketAndANewOwnerConnection)
{
  Rig rig;
  ASSERT_TRUE(rig.configure());
  ASSERT_TRUE(rig.activate());
  EXPECT_EQ(rig.controller.activations(), 1u);
  const auto first_socket = rig.controller.deadman()->socket_path();
  EXPECT_EQ(first_socket, rig.directory / "neck-1.sock");
  const int owner = rig.connect_owner();
  ASSERT_TRUE(wait_until([&] {return rig.controller.goal_decision_admits();}));
  EXPECT_EQ(rig.controller.get_node()->get_parameter("head_activation_id").as_int(), 1);
  rig.deactivate();
  EXPECT_FALSE(std::filesystem::exists(first_socket));
  EXPECT_FALSE(rig.controller.goal_decision_admits());
  EXPECT_EQ(rig.controller.get_node()->get_parameter("head_deadman_peer_pid").as_int(), 0);
  ASSERT_TRUE(rig.activate());
  EXPECT_EQ(rig.controller.activations(), 2u);
  EXPECT_EQ(rig.controller.deadman()->socket_path(), rig.directory / "neck-2.sock");
  EXPECT_EQ(rig.controller.get_node()->get_parameter("head_activation_id").as_int(), 2);
  EXPECT_FALSE(rig.controller.goal_decision_admits()) << "the old connection does not carry over";
  const int again = rig.connect_owner();
  ASSERT_GE(again, 0);
  ASSERT_TRUE(wait_until([&] {return rig.controller.goal_decision_admits();}));
  (void)owner;
}

TEST(HeadNeckTrajectoryController, ActivationWithoutAPeerPidIsRefusedAndLeavesNoSocket)
{
  Rig rig;
  ASSERT_TRUE(rig.configure());
  rig.assign();
  EXPECT_NE(rig.controller.get_node()->activate().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);
  EXPECT_FALSE(std::filesystem::exists(rig.directory / "neck-1.sock"));
  EXPECT_FALSE(rig.controller.goal_decision_admits());
}

TEST(HeadNeckTrajectoryController, ThePeerPidIsSetOncePerActivationAndReadOnlyWhileActive)
{
  Rig rig;
  ASSERT_TRUE(rig.configure());
  const auto node = rig.controller.get_node();
  EXPECT_FALSE(node->set_parameter(rclcpp::Parameter("head_deadman_peer_pid", int64_t(0))).successful);
  EXPECT_FALSE(node->set_parameter(rclcpp::Parameter("head_deadman_peer_pid", int64_t(-4))).successful);
  EXPECT_TRUE(rig.set_pid(getpid()));
  EXPECT_FALSE(rig.set_pid(getpid() + 1)) << "a second change before activation is refused";
  rig.assign();
  ASSERT_EQ(node->activate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);
  EXPECT_FALSE(rig.set_pid(getpid() + 1)) << "read-only while active";
  EXPECT_EQ(node->get_parameter("head_deadman_peer_pid").as_int(), getpid());
}
