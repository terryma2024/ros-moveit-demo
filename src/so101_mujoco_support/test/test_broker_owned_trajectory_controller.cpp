#include <gtest/gtest.h>
#include <chrono>
#include <cstring>
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
#include <sys/wait.h>
#include <poll.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>
#include <thread>
#include <unistd.h>
#include <vector>

#include "so101_mujoco_support/broker_owned_trajectory_controller.hpp"
#include "so101_mujoco_support/controller_goal_admission.hpp"
#include "so101_mujoco_support/controller_stop_witness.hpp"

namespace
{
using Action = control_msgs::action::FollowJointTrajectory;
using SendGoal = Action::Impl::SendGoalService;
using Admission = so101_mujoco_support::ControllerGoalAdmission;

class InspectableController : public so101_mujoco_support::BrokerOwnedTrajectoryController
{
public:
  // Explicit legacy-only unit mode: no gate exists until a test asks for one, so
  // the "before provision" state stays fail-closed exactly as in production.
  std::shared_ptr<Admission> legacy_gate()
  {
    auto gate = active_gate_copy();
    if (!gate) {
      gate = std::make_shared<Admission>();
      install_active_gate_for_testing(gate);
    }
    return gate;
  }
  bool topic_subscriber_exists() const {return static_cast<bool>(joint_command_subscriber_);}
  bool action_server_exists() const {return static_cast<bool>(action_server_);}
  bool reserve_goal(const Admission::GoalUUID & id, const Action::Goal & goal, uint64_t generation)
  {
    const auto gate = legacy_gate();
    return gate->arm(generation) && gate->reserve(id, goal, generation);
  }
  Admission::Result probe_goal(
    const Admission::GoalUUID & id, const Action::Goal & goal, uint64_t generation)
  {
    return legacy_gate()->admit(id, goal, generation);
  }
  std::optional<so101_mujoco_support::ControllerStopWitness::Proof> stopped_state(
    int64_t now_monotonic_ns)
  {
    return controller_stop_proof(now_monotonic_ns);
  }
  std::optional<so101_mujoco_support::ControllerIngressWitness::Snapshot> native_ingress()
  {
    return controller_ingress_snapshot();
  }
  std::array<size_t, 4> state_shape() const
  {
    return {joints_angle_wraparound_.size(), state_current_.positions.size(),
      state_desired_.positions.size(), state_error_.positions.size()};
  }
  void set_pending_goal_for_test(bool value) {rt_has_pending_goal_.store(value);}
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

std::string five_joint_urdf()
{
  std::string urdf = "<robot name='controller_stop_test'><link name='base'/>";
  for (int joint = 1; joint <= 5; ++joint) {
    const auto name = std::to_string(joint);
    const auto parent = joint == 1 ? "base" : "link" + std::to_string(joint - 1);
    urdf += "<link name='link" + name + "'/>";
    urdf += "<joint name='" + name + "' type='revolute'><parent link='" + parent +
      "'/><child link='link" + name + "'/><origin xyz='0 0 0' rpy='0 0 0'/>" +
      "<axis xyz='0 0 1'/><limit lower='-3' upper='3' effort='1' velocity='1'/>" +
      "</joint>";
  }
  return urdf + "</robot>";
}

std::string gripper_urdf()
{
  return "<robot name='gripper_stop_test'><link name='base'/>"
         "<link name='finger'/><joint name='6' type='prismatic'>"
         "<parent link='base'/><child link='finger'/>"
         "<origin xyz='0 0 0' rpy='0 0 0'/><axis xyz='0 0 1'/>"
         "<limit lower='0' upper='1' effort='1' velocity='1'/>"
         "</joint></robot>";
}

std::string neck_urdf()
{
  return "<robot name='neck_stop_test'><link name='base'/>"
         "<link name='head'/><joint name='neck_yaw_joint' type='revolute'>"
         "<parent link='base'/><child link='head'/>"
         "<origin xyz='0 0 0' rpy='0 0 0'/><axis xyz='0 0 1'/>"
         "<limit lower='-3' upper='3' effort='1' velocity='1'/>"
         "</joint></robot>";
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

uint8_t send_generation_request(
  const std::filesystem::path & path, uint8_t operation,
  uint8_t capability_byte = 0xa5, uint64_t generation = 5)
{
  std::vector<uint8_t> frame{0, 0, 0, 62, 'S', 'O', 'G', 'R', 1, operation};
  frame.insert(frame.end(), 32, capability_byte);
  append_big_endian(frame, generation, 8);
  frame.insert(frame.end(), 16, 0);
  sockaddr_un address{};
  address.sun_family = AF_UNIX;
  const auto name = path.string();
  if (name.size() >= sizeof(address.sun_path)) {throw std::runtime_error("TEST_SOCKET_PATH_LONG");}
  std::memcpy(address.sun_path, name.c_str(), name.size() + 1);
  const int connection = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (connection < 0) {throw std::runtime_error("TEST_SOCKET_CREATE_FAILED");}
  timeval timeout{2, 0};
  if (setsockopt(connection, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) != 0 ||
    setsockopt(connection, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)) != 0)
  {
    close(connection);
    throw std::runtime_error("TEST_SOCKET_TIMEOUT_FAILED");
  }
  const auto address_size = static_cast<socklen_t>(offsetof(sockaddr_un,
      sun_path) + name.size() + 1);
  if (connect(connection, reinterpret_cast<sockaddr *>(&address), address_size) != 0) {
    close(connection);
    throw std::runtime_error("TEST_SOCKET_CONNECT_FAILED");
  }
  size_t sent = 0;
  while (sent < frame.size()) {
    const auto count = send(connection, frame.data() + sent, frame.size() - sent, MSG_NOSIGNAL);
    if (count <= 0) {
      close(connection);
      throw std::runtime_error("TEST_SOCKET_SEND_FAILED");
    }
    sent += static_cast<size_t>(count);
  }
  std::array<uint8_t, 16> reply{};
  size_t received = 0;
  while (received < reply.size()) {
    const auto count = recv(connection, reply.data() + received, reply.size() - received, 0);
    if (count <= 0) {
      close(connection);
      throw std::runtime_error("TEST_SOCKET_REPLY_FAILED");
    }
    received += static_cast<size_t>(count);
  }
  close(connection);
  if (reply[0] != 'S' || reply[1] != 'O' || reply[2] != 'G' || reply[3] != 'A' ||
    reply[4] != 1 || reply[15] != generation)
  {
    throw std::runtime_error("TEST_SOCKET_REPLY_INVALID");
  }
  return reply[5];
}

uint64_t query_neck_generation(const std::filesystem::path & path, uint8_t capability_byte)
{
  sockaddr_un address{};
  address.sun_family = AF_UNIX;
  const auto name = path.string();
  if (name.size() >= sizeof(address.sun_path)) {
    throw std::runtime_error("TEST_IDENTITY_PATH_LONG");
  }
  std::memcpy(address.sun_path, name.c_str(), name.size() + 1);
  const int connection = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (connection < 0) {throw std::runtime_error("TEST_IDENTITY_SOCKET_FAILED");}
  try {
    timeval timeout{2, 0};
    if (setsockopt(connection, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) ||
      connect(connection, reinterpret_cast<sockaddr *>(&address),
        static_cast<socklen_t>(offsetof(sockaddr_un, sun_path) + name.size() + 1)))
    {
      throw std::runtime_error("TEST_IDENTITY_CONNECT_FAILED");
    }
    std::vector<uint8_t> frame{0, 0, 0, 39, 'S', 'O', 'I', 'A', 1, 1};
    frame.insert(frame.end(), 32, capability_byte);
    frame.push_back(3);
    if (send(connection, frame.data(), frame.size(), MSG_NOSIGNAL) !=
      static_cast<ssize_t>(frame.size()))
    {
      throw std::runtime_error("TEST_IDENTITY_SEND_FAILED");
    }
    const auto read_bytes = [connection](size_t size) {
        std::vector<uint8_t> bytes(size);
        size_t received = 0;
        while (received < size) {
          const auto count = recv(connection, bytes.data() + received, size - received, 0);
          if (count <= 0) {throw std::runtime_error("TEST_IDENTITY_REPLY_FAILED");}
          received += static_cast<size_t>(count);
        }
        return bytes;
      };
    const auto prefix = read_bytes(4);
    uint32_t size = 0;
    for (const auto byte : prefix) {
      size = (size << 8) | byte;
    }
    if (size < 6 || size > so101_mujoco_support::kMaxIdentityReplyBytes) {
      throw std::runtime_error("TEST_IDENTITY_REPLY_SIZE");
    }
    const auto body = read_bytes(size);
    if (body == std::vector<uint8_t>{'S', 'O', 'I', 'D', 1, 0}) {
      close(connection);
      return 0;
    }
    so101_mujoco_support::ServiceControllerIdentity identity;
    if (!so101_mujoco_support::parse_identity_reply(
        body, so101_mujoco_support::ControllerReservationRole::NECK, &identity))
    {
      throw std::runtime_error("TEST_IDENTITY_REPLY_INVALID");
    }
    uint64_t generation = 0;
    for (size_t index = 7; index != 15; ++index) {
      generation = (generation << 8) | body[index];
    }
    close(connection);
    return generation;
  } catch (...) {
    close(connection);
    throw;
  }
}

class ScopedNativeMonitor
{
public:
  explicit ScopedNativeMonitor(const std::filesystem::path & directory)
  {
    int commands[2];
    int replies[2];
    if (pipe(commands) || pipe(replies)) {throw std::runtime_error("MONITOR_PIPE_FAILED");}
    const auto native_pid = getpid();
    const auto native_ticks = self_start_ticks();
    pid_ = fork();
    if (pid_ < 0) {throw std::runtime_error("MONITOR_FORK_FAILED");}
    if (pid_ == 0) {
      close(commands[1]);
      close(replies[0]);
      try {
        const std::string session = "session-17";
        const auto endpoint = directory / "neck-revoke.sock";
        const auto endpoint_text = endpoint.string();
        std::vector<uint8_t> bytes{'S', 'O', 'P', 'R', 2, 3,
          static_cast<uint8_t>(session.size()), static_cast<uint8_t>(endpoint_text.size())};
        append_big_endian(bytes, geteuid(), 4);
        append_big_endian(bytes, getpid(), 4);
        append_big_endian(bytes, self_start_ticks(), 8);
        bytes.insert(bytes.end(), 32, 0x5a);
        append_big_endian(bytes, geteuid(), 4);
        append_big_endian(bytes, native_pid, 4);
        append_big_endian(bytes, native_ticks, 8);
        bytes.insert(bytes.end(), session.begin(), session.end());
        bytes.insert(bytes.end(), endpoint_text.begin(), endpoint_text.end());
        const auto path = directory / "neck-revoke.provision";
        std::ofstream output(path, std::ios::binary);
        output.write(reinterpret_cast<const char *>(bytes.data()), bytes.size());
        output.close();
        if (chmod(path.c_str(), 0600)) {_exit(1);}
        const char ready = 'R';
        if (write(replies[1], &ready, 1) != 1) {_exit(1);}
        char operation;
        while (read(commands[0], &operation, 1) == 1) {
          const uint8_t reply = operation == 'I' ? query_neck_generation(endpoint, 0x5a) :
            send_generation_request(endpoint, operation, 0x5a);
          if (write(replies[1], &reply, 1) != 1) {_exit(1);}
        }
        _exit(0);
      } catch (...) {
        _exit(1);
      }
    }
    close(commands[0]);
    close(replies[1]);
    input_ = commands[1];
    output_ = replies[0];
    try {
      if (reply() != 'R') {throw std::runtime_error("MONITOR_NOT_READY");}
    } catch (...) {
      close(input_);
      close(output_);
      kill(pid_, SIGTERM);
      int child_rc;
      waitpid(pid_, &child_rc, 0);
      throw;
    }
  }
  ~ScopedNativeMonitor()
  {
    close(input_);
    close(output_);
    int child_rc;
    if (waitpid(pid_, &child_rc, WNOHANG) == 0) {
      kill(pid_, SIGTERM);
      waitpid(pid_, &child_rc, 0);
    }
  }
  uint8_t revoke()
  {
    const char operation = 2;
    if (write(input_, &operation, 1) != 1) {throw std::runtime_error("MONITOR_REQUEST_FAILED");}
    return reply();
  }
  uint8_t armed_generation()
  {
    const char operation = 'I';
    if (write(input_, &operation, 1) != 1) {throw std::runtime_error("MONITOR_QUERY_FAILED");}
    return reply();
  }

private:
  uint8_t reply()
  {
    pollfd ready{output_, POLLIN, 0};
    uint8_t value;
    if (poll(&ready, 1, 2000) <= 0 || read(output_, &value, 1) != 1) {
      throw std::runtime_error("MONITOR_RESPONSE_FAILED");
    }
    return value;
  }
  pid_t pid_{-1};
  int input_{-1};
  int output_{-1};
};

class ScopedHeadMonitorRequirement
{
public:
  ScopedHeadMonitorRequirement()
  {
    const auto * previous = std::getenv("SO101_HEAD_SEARCH_V2_MONITOR_REQUIRED");
    if (previous) {previous_ = previous;}
    setenv("SO101_HEAD_SEARCH_V2_MONITOR_REQUIRED", "1", 1);
  }
  ~ScopedHeadMonitorRequirement()
  {
    if (previous_) {
      setenv("SO101_HEAD_SEARCH_V2_MONITOR_REQUIRED", previous_->c_str(), 1);
    } else {
      unsetenv("SO101_HEAD_SEARCH_V2_MONITOR_REQUIRED");
    }
  }

private:
  std::optional<std::string> previous_;
};
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
  ASSERT_TRUE(controller.native_ingress().has_value());
  EXPECT_EQ(controller.native_ingress()->sequence, 0U);
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
  ASSERT_TRUE(controller.native_ingress().has_value());
  EXPECT_EQ(controller.native_ingress()->sequence, 1U);

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
  ASSERT_TRUE(controller.native_ingress().has_value());
  EXPECT_EQ(controller.native_ingress()->sequence, 2U);
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
  ASSERT_EQ(controller.init("lifecycle_controller", five_joint_urdf(), 500, "", options),
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

TEST(BrokerOwnedTrajectoryController, NativeUpdatesProvideFreshStoppedStateOnlyWhileActive)
{
  rclcpp::init(0, nullptr);
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"1", "2", "3", "4", "5"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
  });
  ASSERT_EQ(controller.init("arm_controller", five_joint_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(controller.stopped_state(0).has_value());

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
  const auto state_shape = controller.state_shape();
  ASSERT_EQ(state_shape[0], 5u);
  ASSERT_EQ(state_shape[1], 5u);
  ASSERT_EQ(state_shape[2], 5u);
  ASSERT_EQ(state_shape[3], 5u);

  for (int64_t index = 1; index < 51; ++index) {
    ASSERT_EQ(controller.update(rclcpp::Time(index * 2000000, RCL_ROS_TIME),
        rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  }
  auto now = std::chrono::steady_clock::now().time_since_epoch();
  EXPECT_FALSE(controller.stopped_state(
      std::chrono::duration_cast<std::chrono::nanoseconds>(now).count()).has_value());
  ASSERT_EQ(controller.update(rclcpp::Time(int64_t{51} *2000000, RCL_ROS_TIME),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  now = std::chrono::steady_clock::now().time_since_epoch();
  const auto proof = controller.stopped_state(
    std::chrono::duration_cast<std::chrono::nanoseconds>(now).count());
  ASSERT_TRUE(proof.has_value());
  EXPECT_EQ(proof->last_sim_time_ns, 102000000);
  auto client_node = std::make_shared<rclcpp::Node>("stopped_window_goal_client");
  auto client = client_node->create_client<SendGoal>(
    "/arm_controller/follow_joint_trajectory/_action/send_goal");
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(controller.get_node()->get_node_base_interface());
  executor.add_node(client_node);
  ASSERT_TRUE(client->wait_for_service(std::chrono::seconds(2)));
  auto request = std::make_shared<SendGoal::Request>();
  request->goal_id.uuid.fill(9);
  request->goal = stationary_goal();
  auto response = client->async_send_request(request);
  ASSERT_EQ(executor.spin_until_future_complete(response, std::chrono::seconds(2)),
    rclcpp::FutureReturnCode::SUCCESS);
  EXPECT_FALSE(response.get()->accepted);
  now = std::chrono::steady_clock::now().time_since_epoch();
  EXPECT_FALSE(controller.stopped_state(
      std::chrono::duration_cast<std::chrono::nanoseconds>(now).count()).has_value());
  executor.remove_node(client_node);
  executor.remove_node(controller.get_node()->get_node_base_interface());
  for (int64_t index = 52; index <= 102; ++index) {
    ASSERT_EQ(controller.update(rclcpp::Time(index * 2000000, RCL_ROS_TIME),
        rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  }
  now = std::chrono::steady_clock::now().time_since_epoch();
  ASSERT_TRUE(controller.stopped_state(
      std::chrono::duration_cast<std::chrono::nanoseconds>(now).count()).has_value());
  controller.set_pending_goal_for_test(true);
  EXPECT_FALSE(controller.stopped_state(
      std::chrono::duration_cast<std::chrono::nanoseconds>(now).count()).has_value());
  controller.set_pending_goal_for_test(false);
  EXPECT_FALSE(controller.stopped_state(
      std::chrono::duration_cast<std::chrono::nanoseconds>(now).count()).has_value());
  ASSERT_EQ(controller.get_node()->deactivate().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(controller.stopped_state(
      std::chrono::duration_cast<std::chrono::nanoseconds>(now).count()).has_value());
  controller.release_interfaces();
  rclcpp::shutdown();
}

TEST(BrokerOwnedTrajectoryController, GripperNativeUpdatesUseOneJointStoppedScope)
{
  const auto directory = private_socket_directory();
  write_self_provision(directory / "gripper.provision", 2);
  const ScopedReservationEnvironment scope(directory, "session-17");
  const auto socket = directory / "gripper.sock";
  rclcpp::init(0, nullptr);
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"6"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
  });
  ASSERT_EQ(controller.init("gripper_controller", gripper_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(controller.get_node()->get_node_base_interface());
  const auto service_deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (!std::filesystem::exists(socket) &&
    std::chrono::steady_clock::now() < service_deadline)
  {
    executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  ASSERT_TRUE(std::filesystem::exists(socket));
  EXPECT_EQ(send_generation_request(socket, 3), 1u);
  hardware_interface::InterfaceInfo position;
  position.name = "position";
  position.initial_value = "0";
  hardware_interface::InterfaceInfo velocity;
  velocity.name = "velocity";
  velocity.initial_value = "0";
  auto command = std::make_shared<hardware_interface::CommandInterface>(
    hardware_interface::InterfaceDescription("6", position));
  auto state_position = std::make_shared<hardware_interface::StateInterface>(
    hardware_interface::InterfaceDescription("6", position));
  auto state_velocity = std::make_shared<hardware_interface::StateInterface>(
    hardware_interface::InterfaceDescription("6", velocity));
  std::vector<hardware_interface::LoanedCommandInterface> commands;
  std::vector<hardware_interface::LoanedStateInterface> states;
  commands.emplace_back(command, []() {});
  states.emplace_back(state_position);
  states.emplace_back(state_velocity);
  controller.assign_interfaces(std::move(commands), std::move(states));
  ASSERT_EQ(controller.get_node()->activate().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);
  for (int64_t index = 1; index <= 51; ++index) {
    ASSERT_EQ(controller.update(rclcpp::Time(index * 2000000, RCL_ROS_TIME),
        rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  }
  const auto now = std::chrono::steady_clock::now().time_since_epoch();
  const auto stopped = controller.stopped_state(
    std::chrono::duration_cast<std::chrono::nanoseconds>(now).count());
  ASSERT_TRUE(stopped.has_value());
  EXPECT_EQ(stopped->sample_count, 51u);
  EXPECT_EQ(stopped->last_sim_time_ns, 102000000);
  EXPECT_EQ(stopped->measured_positions[0], 0.0);
  EXPECT_EQ(send_generation_request(socket, 3), 0u);
  EXPECT_EQ(send_generation_request(socket, 3), 1u);
  ASSERT_EQ(controller.get_node()->deactivate().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(std::filesystem::exists(socket));
  EXPECT_FALSE(controller.stopped_state(
      std::chrono::duration_cast<std::chrono::nanoseconds>(now).count()).has_value());
  controller.release_interfaces();
  executor.remove_node(controller.get_node()->get_node_base_interface());
  rclcpp::shutdown();
}

static void exercise_neck_native_scope(bool monitor_required)
{
  const auto directory = private_socket_directory();
  write_self_provision(directory / "neck.provision", 3);
  const ScopedReservationEnvironment scope(directory, "session-17");
  const auto socket = directory / "neck.sock";
  std::unique_ptr<ScopedNativeMonitor> monitor;
  std::unique_ptr<ScopedHeadMonitorRequirement> requirement;
  if (monitor_required) {
    requirement = std::make_unique<ScopedHeadMonitorRequirement>();
    monitor = std::make_unique<ScopedNativeMonitor>(directory);
  }
  rclcpp::init(0, nullptr);
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
  });
  ASSERT_EQ(controller.init("neck_controller", neck_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(controller.get_node()->get_node_base_interface());
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (!std::filesystem::exists(socket) && std::chrono::steady_clock::now() < deadline) {
    executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  ASSERT_TRUE(std::filesystem::exists(socket));
  if (monitor_required) {ASSERT_TRUE(std::filesystem::exists(directory / "neck-revoke.sock"));}
  EXPECT_EQ(send_generation_request(socket, 3), 1u);
  hardware_interface::InterfaceInfo position;
  position.name = "position";
  position.initial_value = "0";
  hardware_interface::InterfaceInfo velocity;
  velocity.name = "velocity";
  velocity.initial_value = "0";
  auto command = std::make_shared<hardware_interface::CommandInterface>(
    hardware_interface::InterfaceDescription("neck_yaw_joint", position));
  auto state_position = std::make_shared<hardware_interface::StateInterface>(
    hardware_interface::InterfaceDescription("neck_yaw_joint", position));
  auto state_velocity = std::make_shared<hardware_interface::StateInterface>(
    hardware_interface::InterfaceDescription("neck_yaw_joint", velocity));
  std::vector<hardware_interface::LoanedCommandInterface> commands;
  std::vector<hardware_interface::LoanedStateInterface> states;
  commands.emplace_back(command, []() {});
  states.emplace_back(state_position);
  states.emplace_back(state_velocity);
  controller.assign_interfaces(std::move(commands), std::move(states));
  ASSERT_EQ(controller.get_node()->activate().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);
  for (int64_t index = 1; index <= 51; ++index) {
    ASSERT_EQ(controller.update(rclcpp::Time(index * 2000000, RCL_ROS_TIME),
        rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  }
  const auto now = std::chrono::steady_clock::now().time_since_epoch();
  const auto stopped = controller.stopped_state(
    std::chrono::duration_cast<std::chrono::nanoseconds>(now).count());
  ASSERT_TRUE(stopped.has_value());
  EXPECT_EQ(stopped->sample_count, 51u);
  EXPECT_EQ(send_generation_request(socket, 3), 0u);
  if (monitor) {
    ASSERT_EQ(query_neck_generation(socket, 0xa5), 5u);
    ASSERT_EQ(monitor->armed_generation(), 5u);
    ASSERT_EQ(monitor->revoke(), 0u);
    EXPECT_EQ(query_neck_generation(socket, 0xa5), 0u);
    EXPECT_EQ(monitor->armed_generation(), 0u);
    EXPECT_EQ(send_generation_request(socket, 3, 0xa5, 6), 1u);
  } else {
    EXPECT_EQ(send_generation_request(socket, 3), 1u);
  }
  ASSERT_EQ(controller.get_node()->deactivate().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(std::filesystem::exists(socket));
  if (monitor_required) {EXPECT_FALSE(std::filesystem::exists(directory / "neck-revoke.sock"));}
  controller.release_interfaces();
  rclcpp::shutdown();
}

TEST(BrokerOwnedTrajectoryController, NeckNativeUpdatesArmOnlyItsPrivateRoleService)
{
  exercise_neck_native_scope(false);
}

TEST(BrokerOwnedTrajectoryController, HeadV2ProvisionStartsTwoIndependentNativeRoleServices)
{
  exercise_neck_native_scope(true);
}

TEST(BrokerOwnedTrajectoryController, HeadV2MissingMonitorProvisionCannotOpenPrimaryEndpoint)
{
  const auto directory = private_socket_directory();
  write_self_provision(directory / "neck.provision", 3);
  const ScopedReservationEnvironment scope(directory, "session-17");
  const ScopedHeadMonitorRequirement requirement;
  rclcpp::init(0, nullptr);
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
  });
  ASSERT_EQ(controller.init("neck_controller", neck_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(controller.get_node()->get_node_base_interface());
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(200);
  while (std::chrono::steady_clock::now() < deadline) {
    executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  EXPECT_FALSE(std::filesystem::exists(directory / "neck.sock"));
  EXPECT_FALSE(std::filesystem::exists(directory / "neck-revoke.sock"));
  executor.remove_node(controller.get_node()->get_node_base_interface());
  rclcpp::shutdown();
}
