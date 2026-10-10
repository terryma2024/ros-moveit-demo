#include <future>
#include <gtest/gtest.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <control_msgs/msg/speed_scaling_factor.hpp>
#include <action_msgs/msg/goal_status.hpp>
#include <rcl_interfaces/srv/describe_parameters.hpp>
#include <rcl_interfaces/srv/get_parameters.hpp>
#include <rcl_interfaces/srv/set_parameters.hpp>
#include <hardware_interface/handle.hpp>
#include <hardware_interface/loaned_command_interface.hpp>
#include <hardware_interface/loaned_state_interface.hpp>
#include <limits>
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
#include "so101_mujoco_support/controller_stop_evaluation.hpp"
#include "controller_stop_witness_test_access.hpp"
#include "so101_mujoco_support/controller_goal_admission.hpp"
#include "so101_mujoco_support/controller_stop_witness.hpp"
#include "so101_mujoco_support/sha256.hpp"

namespace
{
using Action = control_msgs::action::FollowJointTrajectory;
using SendGoal = Action::Impl::SendGoalService;
using GetResult = Action::Impl::GetResultService;
using CancelGoal = Action::Impl::CancelGoalService;
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
  so101_mujoco_support::ControllerStopEvaluation stop_evaluation()
  {return controller_stop_evaluation();}
  bool topic_subscriber_exists() const {return static_cast<bool>(joint_command_subscriber_);}
  bool action_server_exists() const {return static_cast<bool>(action_server_);}
  void publish_trajectory_for_test(
    const std::shared_ptr<trajectory_msgs::msg::JointTrajectory> & trajectory)
  {
    stage_head_trajectory_for_testing(trajectory);
  }
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
  std::optional<so101_mujoco_support::ControllerStopWitness::Proof> stopped_state()
  {
    return controller_stop_proof();
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
  std::shared_ptr<Admission> active_gate_for_test() {return active_gate_copy();}
  double scaling_factor_for_test() const {return scaling_factor_.load(std::memory_order_acquire);}
  bool holding_for_test() const {return rt_is_holding_.load(std::memory_order_acquire);}
  bool neck_wraps_for_test() const {return joints_angle_wraparound_.at(0);}
  double position_error_for_test() const {return state_error_.positions.at(0);}
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

Action::Goal safe_head_goal(int64_t header_ns, double position = 0.1)
{
  Action::Goal goal;
  goal.trajectory.joint_names = {"neck_yaw_joint"};
  goal.trajectory.header.stamp.sec = static_cast<int32_t>(
    header_ns / 1000000000LL);
  goal.trajectory.header.stamp.nanosec = static_cast<uint32_t>(
    header_ns % 1000000000LL);
  trajectory_msgs::msg::JointTrajectoryPoint first;
  first.positions = {position};
  first.velocities = {0.0};
  first.accelerations = {0.0};
  first.time_from_start.sec = 0;
  first.time_from_start.nanosec = 400000000;
  trajectory_msgs::msg::JointTrajectoryPoint last;
  last.positions = {position};
  last.velocities = {0.0};
  last.accelerations = {0.0};
  last.time_from_start.sec = 1;
  last.time_from_start.nanosec = 400000000;
  goal.trajectory.points = {first, last};
  return goal;
}

bool reserve_bound_head_goal(
  const std::shared_ptr<Admission> & gate, const Admission::GoalUUID & uuid,
  const Action::Goal & goal)
{
  if (!gate) {return false;}
  const auto identity = gate->service_identity();
  const auto generation = gate->generation();
  if (!identity || generation == 0) {return false;}
  rclcpp::SerializedMessage serialized;
  rclcpp::Serialization<Action::Goal>().serialize_message(&goal, &serialized);
  const auto & raw = serialized.get_rcl_serialized_message();
  so101_mujoco_support::BoundControllerReservationRequest request;
  request.generation = generation;
  for (size_t index = 0; index < request.permit_uuid.size(); ++index) {
    request.permit_uuid[index] = static_cast<uint8_t>(uuid[index] ^ 0xa1);
  }
  request.permit_uuid[6] = static_cast<uint8_t>((request.permit_uuid[6] & 0x0f) | 0x40);
  request.permit_uuid[8] = static_cast<uint8_t>((request.permit_uuid[8] & 0x3f) | 0x80);
  request.role = so101_mujoco_support::ControllerReservationRole::NECK;
  request.uuid = uuid;
  request.goal_cdr.assign(raw.buffer, raw.buffer + raw.buffer_length);
  request.target_digest = so101_mujoco_support::sha256::digest(request.goal_cdr);
  request.claim_monotonic_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
  request.deadline_ns = request.claim_monotonic_ns + 400000000LL;
  request.session_id = "session-17";
  request.broker_incarnation = "test-broker";
  request.controller_incarnation = identity->incarnation;
  request.controller_boot_incarnation = identity->boot;
  request.goal = goal;
  return gate->reserve_bound(request) ==
         so101_mujoco_support::BoundReserveStatus::ACCEPTED;
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

std::string continuous_neck_urdf()
{
  auto urdf = neck_urdf();
  urdf.replace(urdf.find("type='revolute'"), std::strlen("type='revolute'"),
    "type='continuous'");
  return urdf;
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
  uint8_t capability_byte = 0xa5, uint64_t generation = 5, int fragment_delay_ms = 0)
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
  if (fragment_delay_ms > 0) {
    if (send(connection, frame.data(), 4, MSG_NOSIGNAL) != 4) {
      close(connection);
      throw std::runtime_error("TEST_SOCKET_PREFIX_FAILED");
    }
    sent = 4;
    std::this_thread::sleep_for(std::chrono::milliseconds(fragment_delay_ms));
  }
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
  explicit ScopedNativeMonitor(
    const std::filesystem::path & directory, bool primary = false, int fragment_delay_ms = 0)
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
        const auto endpoint = directory /
          (primary ? "neck-primary-revoke.sock" : "neck-revoke.sock");
        const uint8_t capability_byte = primary ? 0x3c : 0x5a;
        if (primary) {write_self_provision(directory / "neck.provision", 3);}
        const auto endpoint_text = endpoint.string();
        std::vector<uint8_t> bytes{'S', 'O', 'P', 'R', 2, static_cast<uint8_t>(primary ? 4 : 3),
          static_cast<uint8_t>(session.size()), static_cast<uint8_t>(endpoint_text.size())};
        append_big_endian(bytes, geteuid(), 4);
        append_big_endian(bytes, getpid(), 4);
        append_big_endian(bytes, self_start_ticks(), 8);
        bytes.insert(bytes.end(), 32, capability_byte);
        append_big_endian(bytes, geteuid(), 4);
        append_big_endian(bytes, native_pid, 4);
        append_big_endian(bytes, native_ticks, 8);
        bytes.insert(bytes.end(), session.begin(), session.end());
        bytes.insert(bytes.end(), endpoint_text.begin(), endpoint_text.end());
        const auto path = directory /
          (primary ? "neck-primary-revoke.provision" : "neck-revoke.provision");
        std::ofstream output(path, std::ios::binary);
        output.write(reinterpret_cast<const char *>(bytes.data()), bytes.size());
        output.close();
        if (chmod(path.c_str(), 0600)) {_exit(1);}
        const char ready = 'R';
        if (write(replies[1], &ready, 1) != 1) {_exit(1);}
        char operation;
        while (read(commands[0], &operation, 1) == 1) {
          uint8_t response;
          if (operation == 'M') {
            response = query_neck_generation(directory / "neck.sock", 0xa5);
          } else if (operation == 'A' || operation == 'N') {
            response = send_generation_request(directory / "neck.sock", 3, 0xa5,
              operation == 'N' ? 6 : 5);
          } else {
            response = operation == 'I' ? query_neck_generation(endpoint, capability_byte) :
              send_generation_request(endpoint, operation, capability_byte, 5, fragment_delay_ms);
          }
          if (write(replies[1], &response, 1) != 1) {_exit(1);}
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
  uint8_t main_generation() {return request('M');}
  uint8_t arm(bool next = false) {return request(next ? 'N' : 'A');}

private:
  uint8_t request(char operation)
  {
    if (write(input_, &operation, 1) != 1) {throw std::runtime_error("PRIMARY_REQUEST_FAILED");}
    return reply();
  }
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
  EXPECT_FALSE(controller.get_node()->get_subscriptions_info_by_topic("/arm_controller/speed_scaling_input").empty());
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
  EXPECT_FALSE(controller.get_node()->get_subscriptions_info_by_topic("/gripper_controller/speed_scaling_input").empty());
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
  const auto node = controller.get_node();
  EXPECT_TRUE(node->get_parameter("speed_scaling_input_enabled").as_bool());
  EXPECT_TRUE(node->describe_parameter("speed_scaling_input_enabled").read_only);
  EXPECT_FALSE(node->get_subscriptions_info_by_topic(
      "/arm_controller/speed_scaling_input").empty());
  auto probe = rclcpp::Node::make_shared("act_speed_scaling_switch_probe");
  auto publisher = probe->create_publisher<control_msgs::msg::SpeedScalingFactor>(
    "/arm_controller/speed_scaling_input", rclcpp::SystemDefaultsQoS().transient_local());
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node->get_node_base_interface());
  executor.add_node(probe);
  control_msgs::msg::SpeedScalingFactor scaling;
  scaling.factor = 0.5;
  publisher->publish(scaling);
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(500);
  while (controller.scaling_factor_for_test() != 0.5 &&
    std::chrono::steady_clock::now() < deadline)
  {
    executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }
  EXPECT_DOUBLE_EQ(controller.scaling_factor_for_test(), 0.5);
  executor.remove_node(probe->get_node_base_interface());
  executor.remove_node(node->get_node_base_interface());
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
  EXPECT_FALSE(controller.stopped_state().has_value());

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
  EXPECT_FALSE(controller.stopped_state().has_value());
  ASSERT_EQ(controller.update(rclcpp::Time(int64_t{51} *2000000, RCL_ROS_TIME),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  const auto proof = controller.stopped_state();
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
  EXPECT_FALSE(controller.stopped_state().has_value());
  executor.remove_node(client_node);
  executor.remove_node(controller.get_node()->get_node_base_interface());
  for (int64_t index = 52; index <= 102; ++index) {
    ASSERT_EQ(controller.update(rclcpp::Time(index * 2000000, RCL_ROS_TIME),
        rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  }
  ASSERT_TRUE(controller.stopped_state().has_value());
  controller.set_pending_goal_for_test(true);
  EXPECT_FALSE(controller.stopped_state().has_value());
  controller.set_pending_goal_for_test(false);
  EXPECT_FALSE(controller.stopped_state().has_value());
  ASSERT_EQ(controller.get_node()->deactivate().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(controller.stopped_state().has_value());
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
  const auto stopped = controller.stopped_state();
  ASSERT_TRUE(stopped.has_value());
  EXPECT_EQ(stopped->sample_count, 51u);
  EXPECT_EQ(stopped->last_sim_time_ns, 102000000);
  EXPECT_EQ(stopped->measured_positions[0], 0.0);
  EXPECT_EQ(send_generation_request(socket, 3), 0u);
  EXPECT_EQ(send_generation_request(socket, 3), 1u);
  ASSERT_EQ(controller.get_node()->deactivate().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(std::filesystem::exists(socket));
  EXPECT_FALSE(controller.stopped_state().has_value());
  controller.release_interfaces();
  executor.remove_node(controller.get_node()->get_node_base_interface());
  rclcpp::shutdown();
}

static void exercise_neck_native_scope()
{
  const auto directory = private_socket_directory();
  write_self_provision(directory / "neck.provision", 3);
  const ScopedReservationEnvironment scope(directory, "session-17");
  const auto socket = directory / "neck.sock";
  rclcpp::init(0, nullptr);
  struct ShutdownGuard {~ShutdownGuard() {rclcpp::shutdown();}} shutdown_guard;
  InspectableController controller;
  rclcpp::NodeOptions options;
  std::vector<rclcpp::Parameter> parameters{
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
  };
  options.parameter_overrides(parameters);
  ASSERT_EQ(controller.init("neck_controller", neck_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_TRUE(controller.get_node()->describe_parameter("head_simulation_mode").read_only);
  EXPECT_TRUE(controller.get_node()->describe_parameter("head_fault_connection_timeout_ns").read_only);
  EXPECT_EQ(controller.get_node()->get_parameter("head_simulation_mode").as_string(), "");
  EXPECT_EQ(controller.get_node()->get_parameter("head_fault_connection_timeout_ns").as_int(),
    2000000);
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(controller.get_node()->get_node_base_interface());
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (!std::filesystem::exists(socket) && std::chrono::steady_clock::now() < deadline) {
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
  const auto stopped = controller.stopped_state();
  ASSERT_TRUE(stopped.has_value());
  EXPECT_EQ(stopped->sample_count, 51u);
  EXPECT_EQ(send_generation_request(socket, 3), 0u);
  EXPECT_EQ(send_generation_request(socket, 3), 1u);
  ASSERT_EQ(controller.get_node()->deactivate().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(std::filesystem::exists(socket));
  controller.release_interfaces();
  rclcpp::shutdown();
}

TEST(BrokerOwnedTrajectoryController, NeckNativeUpdatesArmOnlyItsPrivateRoleService)
{
  exercise_neck_native_scope();
}

TEST(BrokerOwnedTrajectoryController, HeadFileModeConfiguresMainAndLocalPrimaryWithoutMonitor)
{
  const auto directory = private_socket_directory();
  const ScopedReservationEnvironment scope(directory, "session-17");
  ASSERT_EQ(std::getenv("SO101_HEAD_SEARCH_V2_MONITOR_REQUIRED"), nullptr);
  ScopedNativeMonitor primary(directory, true);
  rclcpp::init(0, nullptr);
  struct ShutdownGuard {~ShutdownGuard() {rclcpp::shutdown();}} shutdown_guard;
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
    rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1"),
    rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000)),
    rclcpp::Parameter("head_measured_prefix_guard", "quintic_measured_prefix_v1"),
    rclcpp::Parameter("speed_scaling_input_enabled", false),
  });
  ASSERT_EQ(controller.init("neck_controller", neck_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  const auto node = controller.get_node();
  EXPECT_TRUE(node->get_subscriptions_info_by_topic("/neck_controller/speed_scaling_input").empty());
  EXPECT_TRUE(node->describe_parameter("head_simulation_mode").read_only);
  EXPECT_TRUE(node->describe_parameter("head_fault_connection_timeout_ns").read_only);
  EXPECT_TRUE(node->describe_parameter("head_measured_prefix_guard").read_only);
  EXPECT_TRUE(node->describe_parameter("speed_scaling_input_enabled").read_only);
  EXPECT_FALSE(node->get_parameter("speed_scaling_input_enabled").as_bool());
  auto speed_probe = rclcpp::Node::make_shared("speed_scaling_switch_probe");
  auto speed_publisher = speed_probe->create_publisher<control_msgs::msg::SpeedScalingFactor>(
    "/neck_controller/speed_scaling_input", rclcpp::SystemDefaultsQoS().transient_local());
  rclcpp::executors::SingleThreadedExecutor speed_executor;
  speed_executor.add_node(speed_probe);
  for (const double factor : {2.0, std::numeric_limits<double>::quiet_NaN(), 0.0}) {
    control_msgs::msg::SpeedScalingFactor message;
    message.factor = factor;
    speed_publisher->publish(message);
    speed_executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    speed_executor.spin_some();
    EXPECT_TRUE(node->get_subscriptions_info_by_topic(
        "/neck_controller/speed_scaling_input").empty());
  }
  speed_executor.remove_node(speed_probe->get_node_base_interface());
  speed_probe.reset();
  EXPECT_EQ(node->get_parameter("head_simulation_mode").as_string(),
    "mujoco_bounded_stop_search_file_v1");
  EXPECT_EQ(node->get_parameter("head_fault_connection_timeout_ns").as_int(), 50000000);
  EXPECT_EQ(node->get_parameter("head_measured_prefix_guard").as_string(),
    "quintic_measured_prefix_v1");
  std::ifstream main_file(directory / "neck.provision", std::ios::binary);
  std::ifstream primary_file(directory / "neck-primary-revoke.provision", std::ios::binary);
  const std::vector<uint8_t> main_bytes((std::istreambuf_iterator<char>(main_file)),
    std::istreambuf_iterator<char>());
  const std::vector<uint8_t> primary_bytes((std::istreambuf_iterator<char>(primary_file)),
    std::istreambuf_iterator<char>());
  ASSERT_EQ(main_bytes.size(), 66u);
  ASSERT_GT(primary_bytes.size(), 72u);
  EXPECT_EQ(primary_bytes[5], 4u);
  EXPECT_EQ(std::vector<uint8_t>(main_bytes.begin() + 8, main_bytes.begin() + 24),
    std::vector<uint8_t>(primary_bytes.begin() + 8, primary_bytes.begin() + 24));
  EXPECT_NE(std::vector<uint8_t>(main_bytes.begin() + 24, main_bytes.begin() + 56),
    std::vector<uint8_t>(primary_bytes.begin() + 24, primary_bytes.begin() + 56));
  EXPECT_NE(std::all_of(primary_bytes.begin() + 24, primary_bytes.begin() + 56,
      [](uint8_t value) {return value == 0;}), true);
  EXPECT_EQ(primary_bytes[60], static_cast<uint8_t>((getpid() >> 24) & 0xff));
  EXPECT_EQ(primary_bytes[61], static_cast<uint8_t>((getpid() >> 16) & 0xff));
  EXPECT_EQ(primary_bytes[62], static_cast<uint8_t>((getpid() >> 8) & 0xff));
  EXPECT_EQ(primary_bytes[63], static_cast<uint8_t>(getpid() & 0xff));
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node->get_node_base_interface());
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (!std::filesystem::exists(directory / "neck.sock") &&
    std::chrono::steady_clock::now() < deadline)
  {
    executor.spin_some();
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  EXPECT_TRUE(std::filesystem::exists(directory / "neck.sock"));
  EXPECT_TRUE(std::filesystem::exists(directory / "neck-primary-revoke.sock"));
  EXPECT_FALSE(std::filesystem::exists(directory / "neck-revoke.sock"));
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
  ASSERT_EQ(node->activate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);
  for (int64_t index = 1; index <= 51; ++index) {
    ASSERT_EQ(controller.update(rclcpp::Time(index * 2000000, RCL_ROS_TIME),
        rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  }
  EXPECT_EQ(primary.arm(), 0u);  // main authority accepts only its bound actor
  ASSERT_TRUE(state_position->set_value(0.102));
  ASSERT_TRUE(state_velocity->set_value(0.04136050464213824));
  auto late = std::make_shared<trajectory_msgs::msg::JointTrajectory>();
  late->joint_names = {"neck_yaw_joint"};
  late->header.stamp = rclcpp::Time(static_cast<int64_t>(2000000000), RCL_ROS_TIME);
  trajectory_msgs::msg::JointTrajectoryPoint first;
  first.positions = {0.1};
  first.velocities = {0.0};
  first.accelerations = {0.0};
  first.time_from_start.sec = 0;
  first.time_from_start.nanosec = 400000000;
  trajectory_msgs::msg::JointTrajectoryPoint last;
  last.positions = {0.2};
  last.velocities = {0.0};
  last.accelerations = {0.0};
  last.time_from_start.sec = 5;
  late->points = {first, last};
  controller.publish_trajectory_for_test(late);
  const auto command_before = command->get_optional();
  ASSERT_TRUE(command_before.has_value());
  ASSERT_EQ(controller.update(rclcpp::Time(static_cast<int64_t>(2399900000), RCL_ROS_TIME),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  const auto command_after = command->get_optional();
  ASSERT_TRUE(command_after.has_value());
  std::cerr << "HEAD_FIRST_SAMPLE_BASELINE command_before=" << command_before.value()
            << " measured_q=0.102 measured_v=0.04136050464213824 remaining_ns=100000"
            << " command_after=" << command_after.value() << std::endl;
  EXPECT_NEAR(command_after.value(), 0.102, 1e-12);
  EXPECT_EQ(primary.revoke(), 0u);
  EXPECT_EQ(primary.arm(true), 1u);  // sticky close prevents main re-arm
  ASSERT_EQ(node->deactivate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(std::filesystem::exists(directory / "neck.sock"));
  EXPECT_FALSE(std::filesystem::exists(directory / "neck-primary-revoke.sock"));
  executor.remove_node(node->get_node_base_interface());
  controller.release_interfaces();
}

TEST(BrokerOwnedTrajectoryController, HeadAcceptedActionAbortCancelAndNormalResultUseActualServices)
{
  using namespace std::chrono_literals;
  const auto directory = private_socket_directory();
  const ScopedReservationEnvironment scope(directory, "session-17");
  ScopedNativeMonitor primary(directory, true);
  rclcpp::init(0, nullptr);
  struct ShutdownGuard {~ShutdownGuard() {rclcpp::shutdown();}} shutdown_guard;
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
    rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1"),
    rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000)),
    rclcpp::Parameter("head_measured_prefix_guard", "quintic_measured_prefix_v1"),
    rclcpp::Parameter("speed_scaling_input_enabled", false),
  });
  ASSERT_EQ(controller.init("neck_controller", neck_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  auto client_node = rclcpp::Node::make_shared("head_action_lifecycle_test");
  auto send_client = client_node->create_client<SendGoal>(
    "/neck_controller/follow_joint_trajectory/_action/send_goal");
  auto result_client = client_node->create_client<GetResult>(
    "/neck_controller/follow_joint_trajectory/_action/get_result");
  auto cancel_client = client_node->create_client<CancelGoal>(
    "/neck_controller/follow_joint_trajectory/_action/cancel_goal");
  auto get_client = client_node->create_client<rcl_interfaces::srv::GetParameters>(
    "/neck_controller/get_parameters");
  auto describe_client = client_node->create_client<rcl_interfaces::srv::DescribeParameters>(
    "/neck_controller/describe_parameters");
  auto set_client = client_node->create_client<rcl_interfaces::srv::SetParameters>(
    "/neck_controller/set_parameters");
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(controller.get_node()->get_node_base_interface());
  executor.add_node(client_node);
  const auto provision_deadline = std::chrono::steady_clock::now() + 2s;
  while ((!std::filesystem::exists(directory / "neck.sock") ||
    !std::filesystem::exists(directory / "neck-primary-revoke.sock")) &&
    std::chrono::steady_clock::now() < provision_deadline)
  {
    executor.spin_some();
    std::this_thread::sleep_for(10ms);
  }
  ASSERT_TRUE(std::filesystem::exists(directory / "neck.sock"));
  ASSERT_TRUE(std::filesystem::exists(directory / "neck-primary-revoke.sock"));
  ASSERT_TRUE(send_client->wait_for_service(2s));
  ASSERT_TRUE(result_client->wait_for_service(2s));
  ASSERT_TRUE(cancel_client->wait_for_service(2s));
  ASSERT_TRUE(get_client->wait_for_service(2s));
  ASSERT_TRUE(describe_client->wait_for_service(2s));
  ASSERT_TRUE(set_client->wait_for_service(2s));

  auto get_request = std::make_shared<rcl_interfaces::srv::GetParameters::Request>();
  get_request->names = {"head_simulation_mode", "head_fault_connection_timeout_ns",
    "head_measured_prefix_guard", "speed_scaling_input_enabled"};
  auto get_future = get_client->async_send_request(get_request);
  ASSERT_EQ(executor.spin_until_future_complete(get_future, 2s),
    rclcpp::FutureReturnCode::SUCCESS);
  const auto get_response = get_future.get();
  ASSERT_EQ(get_response->values.size(), 4u);
  EXPECT_EQ(get_response->values[0].type,
    rcl_interfaces::msg::ParameterType::PARAMETER_STRING);
  EXPECT_EQ(get_response->values[0].string_value, "mujoco_bounded_stop_search_file_v1");
  EXPECT_EQ(get_response->values[1].type,
    rcl_interfaces::msg::ParameterType::PARAMETER_INTEGER);
  EXPECT_EQ(get_response->values[1].integer_value, 50000000);
  EXPECT_EQ(get_response->values[2].type,
    rcl_interfaces::msg::ParameterType::PARAMETER_STRING);
  EXPECT_EQ(get_response->values[2].string_value, "quintic_measured_prefix_v1");
  EXPECT_EQ(get_response->values[3].type,
    rcl_interfaces::msg::ParameterType::PARAMETER_BOOL);
  EXPECT_FALSE(get_response->values[3].bool_value);
  auto describe_request =
    std::make_shared<rcl_interfaces::srv::DescribeParameters::Request>();
  describe_request->names = get_request->names;
  auto describe_future = describe_client->async_send_request(describe_request);
  ASSERT_EQ(executor.spin_until_future_complete(describe_future, 2s),
    rclcpp::FutureReturnCode::SUCCESS);
  const auto describe_response = describe_future.get();
  ASSERT_EQ(describe_response->descriptors.size(), 4u);
  for (size_t index = 0; index < get_request->names.size(); ++index) {
    EXPECT_EQ(describe_response->descriptors[index].name, get_request->names[index]);
    EXPECT_TRUE(describe_response->descriptors[index].read_only);
    EXPECT_FALSE(describe_response->descriptors[index].dynamic_typing);
    const auto expected_type = index == 0 || index == 2 ?
      rcl_interfaces::msg::ParameterType::PARAMETER_STRING :
      index == 1 ? rcl_interfaces::msg::ParameterType::PARAMETER_INTEGER :
      rcl_interfaces::msg::ParameterType::PARAMETER_BOOL;
    EXPECT_EQ(describe_response->descriptors[index].type, expected_type);
  }
  auto set_request = std::make_shared<rcl_interfaces::srv::SetParameters::Request>();
  set_request->parameters.push_back(
    rclcpp::Parameter("speed_scaling_input_enabled", true).to_parameter_msg());
  auto set_future = set_client->async_send_request(set_request);
  ASSERT_EQ(executor.spin_until_future_complete(set_future, 2s),
    rclcpp::FutureReturnCode::SUCCESS);
  const auto set_response = set_future.get();
  ASSERT_EQ(set_response->results.size(), 1u);
  EXPECT_FALSE(set_response->results[0].successful);

  hardware_interface::InterfaceInfo position;
  position.name = "position";
  position.initial_value = "0.1";
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
  ASSERT_EQ(controller.get_node()->activate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);
  const auto time_origin = controller.get_node()->get_clock()->now();
  for (int64_t index = 1; index <= 51; ++index) {
    ASSERT_EQ(controller.update(time_origin + rclcpp::Duration::from_nanoseconds(index * 2000000),
        rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  }
  const auto gate = controller.active_gate_for_test();
  ASSERT_NE(gate, nullptr);
  ASSERT_TRUE(gate->arm(1));

  const auto send_actual_goal = [&](const Admission::GoalUUID & uuid,
      const Action::Goal & goal) -> bool {
      if (!reserve_bound_head_goal(gate, uuid, goal)) {return false;}
      auto request = std::make_shared<SendGoal::Request>();
      request->goal_id.uuid = uuid;
      request->goal = goal;
      auto future = send_client->async_send_request(request);
      if (executor.spin_until_future_complete(future, 2s) != rclcpp::FutureReturnCode::SUCCESS) {
        return false;
      }
      return future.get()->accepted;
    };
  const auto actual_result = [&](const Admission::GoalUUID & uuid)
    -> std::shared_ptr<GetResult::Response> {
      auto request = std::make_shared<GetResult::Request>();
      request->goal_id.uuid = uuid;
      auto future = result_client->async_send_request(request);
      if (executor.spin_until_future_complete(future, 3s) !=
        rclcpp::FutureReturnCode::SUCCESS)
      {
        return {};
      }
      return future.get();
    };
  const auto uuid_text = [](const Admission::GoalUUID & uuid) {
      std::ostringstream text;
      for (const auto byte : uuid) {text << std::hex << static_cast<int>(byte);}
      return text.str();
    };
  const auto wait_for_component_clock = [&](int64_t last_update_ns) {
      const auto deadline = std::chrono::steady_clock::now() + 5s;
      while (controller.get_node()->get_clock()->now().nanoseconds() <= last_update_ns &&
        std::chrono::steady_clock::now() < deadline)
      {
        executor.spin_some();
        std::this_thread::sleep_for(2ms);
      }
      const auto value = controller.get_node()->get_clock()->now();
      EXPECT_GT(value.nanoseconds(), last_update_ns);
      std::cerr << "HEAD_COMPONENT_CLOCK_WAIT last_update_ns=" << last_update_ns
                << " next_header_ns=" << value.nanoseconds() << std::endl;
      return value;
    };

  const auto abort_header = wait_for_component_clock(
    time_origin.nanoseconds() + 51 * 2000000LL);
  const auto abort_goal = safe_head_goal(abort_header.nanoseconds());
  Admission::GoalUUID abort_uuid{};
  abort_uuid.fill(0x11);
  ASSERT_TRUE(send_actual_goal(abort_uuid, abort_goal));
  ASSERT_TRUE(state_position->set_value(std::numeric_limits<double>::quiet_NaN()));
  EXPECT_EQ(controller.update(abort_header + rclcpp::Duration::from_nanoseconds(2000000),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::ERROR);
  ASSERT_TRUE(state_position->set_value(0.1));
  ASSERT_EQ(controller.update(abort_header + rclcpp::Duration::from_nanoseconds(4000000),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  const int64_t abort_last_update_ns = abort_header.nanoseconds() + 4000000LL;
  const auto abort_response = actual_result(abort_uuid);
  ASSERT_NE(abort_response, nullptr);
  EXPECT_EQ(static_cast<int>(abort_response->status),
    action_msgs::msg::GoalStatus::STATUS_ABORTED);
  EXPECT_EQ(abort_response->result.error_code,
    Action::Result::INVALID_GOAL);
  EXPECT_EQ(abort_response->result.error_string,
    "Head measured-prefix guard refused the first command");
  std::cerr << "HEAD_ACTION_TERMINAL uuid=" << uuid_text(abort_uuid)
            << " status=" << static_cast<int>(abort_response->status)
            << " error_code=" << abort_response->result.error_code
            << " error_string=" << abort_response->result.error_string << std::endl;

  ASSERT_TRUE(gate->arm(2));
  const auto cancel_header = wait_for_component_clock(abort_last_update_ns);
  const auto cancel_goal = safe_head_goal(cancel_header.nanoseconds());
  Admission::GoalUUID cancel_uuid{};
  cancel_uuid.fill(0x22);
  ASSERT_TRUE(send_actual_goal(cancel_uuid, cancel_goal));
  Admission::GoalUUID overlapping_pending_uuid{};
  overlapping_pending_uuid.fill(0x26);
  ASSERT_TRUE(reserve_bound_head_goal(gate, overlapping_pending_uuid, cancel_goal));
  auto overlapping_pending_request = std::make_shared<SendGoal::Request>();
  overlapping_pending_request->goal_id.uuid = overlapping_pending_uuid;
  overlapping_pending_request->goal = cancel_goal;
  auto overlapping_pending_future = send_client->async_send_request(overlapping_pending_request);
  ASSERT_EQ(executor.spin_until_future_complete(overlapping_pending_future, 2s),
    rclcpp::FutureReturnCode::SUCCESS);
  EXPECT_FALSE(overlapping_pending_future.get()->accepted);
  EXPECT_TRUE(gate->cancel_bound(overlapping_pending_uuid));
  std::cerr << "HEAD_ACTION_OVERLAP pending_uuid=" << uuid_text(overlapping_pending_uuid)
            << " accepted=0" << std::endl;
  auto cancel_request = std::make_shared<CancelGoal::Request>();
  cancel_request->goal_info.goal_id.uuid = cancel_uuid;
  auto cancel_future = cancel_client->async_send_request(cancel_request);
  ASSERT_EQ(executor.spin_until_future_complete(cancel_future, 2s),
    rclcpp::FutureReturnCode::SUCCESS);
  const auto cancel_response = cancel_future.get();
  ASSERT_EQ(cancel_response->goals_canceling.size(), 1u);
  EXPECT_EQ(cancel_response->goals_canceling[0].goal_id.uuid, cancel_uuid);
  ASSERT_EQ(controller.update(cancel_header + rclcpp::Duration::from_nanoseconds(2000000),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  const int64_t cancel_last_update_ns = cancel_header.nanoseconds() + 2000000LL;
  const auto canceled_response = actual_result(cancel_uuid);
  ASSERT_NE(canceled_response, nullptr);
  EXPECT_EQ(static_cast<int>(canceled_response->status),
    action_msgs::msg::GoalStatus::STATUS_CANCELED);
  EXPECT_EQ(canceled_response->result.error_code, 0);
  std::cerr << "HEAD_ACTION_TERMINAL uuid=" << uuid_text(cancel_uuid)
            << " status=" << static_cast<int>(canceled_response->status)
            << " error_code=" << canceled_response->result.error_code << std::endl;

  ASSERT_TRUE(gate->arm(3));
  const auto active_cancel_header = wait_for_component_clock(cancel_last_update_ns);
  auto active_cancel_goal = safe_head_goal(active_cancel_header.nanoseconds());
  active_cancel_goal.trajectory.points[1].positions[0] = 0.101;
  Admission::GoalUUID active_cancel_uuid{};
  active_cancel_uuid.fill(0x33);
  ASSERT_TRUE(send_actual_goal(active_cancel_uuid, active_cancel_goal));
  ASSERT_EQ(controller.update(active_cancel_header + rclcpp::Duration::from_nanoseconds(2000000),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  Admission::GoalUUID overlapping_active_uuid{};
  overlapping_active_uuid.fill(0x36);
  ASSERT_TRUE(reserve_bound_head_goal(gate, overlapping_active_uuid, active_cancel_goal));
  auto overlapping_active_request = std::make_shared<SendGoal::Request>();
  overlapping_active_request->goal_id.uuid = overlapping_active_uuid;
  overlapping_active_request->goal = active_cancel_goal;
  auto overlapping_active_future = send_client->async_send_request(overlapping_active_request);
  ASSERT_EQ(executor.spin_until_future_complete(overlapping_active_future, 2s),
    rclcpp::FutureReturnCode::SUCCESS);
  EXPECT_FALSE(overlapping_active_future.get()->accepted);
  EXPECT_TRUE(gate->cancel_bound(overlapping_active_uuid));
  std::cerr << "HEAD_ACTION_OVERLAP active_uuid=" << uuid_text(overlapping_active_uuid)
            << " accepted=0" << std::endl;
  auto active_cancel_request = std::make_shared<CancelGoal::Request>();
  active_cancel_request->goal_info.goal_id.uuid = active_cancel_uuid;
  auto active_cancel_future = cancel_client->async_send_request(active_cancel_request);
  ASSERT_EQ(executor.spin_until_future_complete(active_cancel_future, 2s),
    rclcpp::FutureReturnCode::SUCCESS);
  const auto active_cancel_response = active_cancel_future.get();
  ASSERT_EQ(active_cancel_response->goals_canceling.size(), 1u);
  EXPECT_EQ(active_cancel_response->goals_canceling[0].goal_id.uuid, active_cancel_uuid);
  ASSERT_EQ(controller.update(active_cancel_header + rclcpp::Duration::from_nanoseconds(4000000),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  const int64_t active_cancel_last_update_ns = active_cancel_header.nanoseconds() + 4000000LL;
  const auto active_canceled_result = actual_result(active_cancel_uuid);
  ASSERT_NE(active_canceled_result, nullptr);
  EXPECT_EQ(static_cast<int>(active_canceled_result->status),
    action_msgs::msg::GoalStatus::STATUS_CANCELED);
  EXPECT_EQ(active_canceled_result->result.error_code, 0);
  std::cerr << "HEAD_ACTION_TERMINAL_ACTIVE_CANCEL uuid=" << uuid_text(active_cancel_uuid)
            << " status=" << static_cast<int>(active_canceled_result->status)
            << " error_code=" << active_canceled_result->result.error_code << std::endl;

  ASSERT_TRUE(gate->arm(4));
  const auto success_header = wait_for_component_clock(active_cancel_last_update_ns);
  auto success_goal = safe_head_goal(success_header.nanoseconds());
  success_goal.trajectory.points[1].positions[0] = 0.101;
  Admission::GoalUUID success_uuid{};
  success_uuid.fill(0x44);
  ASSERT_TRUE(send_actual_goal(success_uuid, success_goal));
  for (int64_t index = 1; index <= 751; ++index) {
    ASSERT_EQ(controller.update(success_header + rclcpp::Duration::from_nanoseconds(
        (index + 1) * 2000000), rclcpp::Duration::from_seconds(0.002)),
      controller_interface::return_type::OK);
    if (index % 10 == 0) {executor.spin_some();}
  }
  const auto success_response = actual_result(success_uuid);
  ASSERT_NE(success_response, nullptr);
  EXPECT_EQ(static_cast<int>(success_response->status),
    action_msgs::msg::GoalStatus::STATUS_SUCCEEDED);
  EXPECT_EQ(success_response->result.error_code, 0);
  const auto successful_command = command->get_optional();
  ASSERT_TRUE(successful_command.has_value());
  EXPECT_NEAR(successful_command.value(), 0.101, 1e-6);
  std::cerr << "HEAD_ACTION_TERMINAL_MOVING uuid=" << uuid_text(success_uuid)
            << " status=" << static_cast<int>(success_response->status)
            << " error_code=" << success_response->result.error_code
            << " command=" << successful_command.value() << std::endl;

  ASSERT_TRUE(gate->arm(5));
  const auto lifecycle_header = wait_for_component_clock(
    success_header.nanoseconds() + 752 * 2000000LL);
  const auto lifecycle_goal = safe_head_goal(lifecycle_header.nanoseconds());
  Admission::GoalUUID lifecycle_uuid{};
  lifecycle_uuid.fill(0x55);
  ASSERT_TRUE(send_actual_goal(lifecycle_uuid, lifecycle_goal));
  ASSERT_EQ(controller.get_node()->deactivate().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  const auto lifecycle_result = actual_result(lifecycle_uuid);
  ASSERT_NE(lifecycle_result, nullptr);
  EXPECT_EQ(static_cast<int>(lifecycle_result->status),
    action_msgs::msg::GoalStatus::STATUS_ABORTED);
  EXPECT_EQ(lifecycle_result->result.error_code, Action::Result::INVALID_GOAL);
  EXPECT_EQ(lifecycle_result->result.error_string, "Head goal retired during lifecycle transition");
  std::cerr << "HEAD_ACTION_TERMINAL_LIFECYCLE uuid=" << uuid_text(lifecycle_uuid)
            << " status=" << static_cast<int>(lifecycle_result->status)
            << " error_code=" << lifecycle_result->result.error_code
            << " error_string=" << lifecycle_result->result.error_string << std::endl;
  EXPECT_FALSE(std::filesystem::exists(directory / "neck.sock"));
  EXPECT_FALSE(std::filesystem::exists(directory / "neck-primary-revoke.sock"));
  executor.remove_node(client_node->get_node_base_interface());
  executor.remove_node(controller.get_node()->get_node_base_interface());
  controller.release_interfaces();
}

static void exercise_primary_close_owned_action(
  bool first_sample_before_close, bool concurrent_cancel = false)
{
  using namespace std::chrono_literals;
  const auto directory = private_socket_directory();
  const ScopedReservationEnvironment scope(directory, "session-17");
  ScopedNativeMonitor primary(directory, true);
  rclcpp::init(0, nullptr);
  struct ShutdownGuard {~ShutdownGuard() {rclcpp::shutdown();}} shutdown_guard;
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
    rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1"),
    rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000)),
    rclcpp::Parameter("head_measured_prefix_guard", "quintic_measured_prefix_v1"),
    rclcpp::Parameter("speed_scaling_input_enabled", false),
  });
  ASSERT_EQ(controller.init("neck_controller", neck_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  auto client_node = rclcpp::Node::make_shared("head_primary_close_component_test");
  auto send_client = client_node->create_client<SendGoal>(
    "/neck_controller/follow_joint_trajectory/_action/send_goal");
  auto result_client = client_node->create_client<GetResult>(
    "/neck_controller/follow_joint_trajectory/_action/get_result");
  auto cancel_client = client_node->create_client<CancelGoal>(
    "/neck_controller/follow_joint_trajectory/_action/cancel_goal");
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(controller.get_node()->get_node_base_interface());
  executor.add_node(client_node);
  const auto provision_deadline = std::chrono::steady_clock::now() + 2s;
  while ((!std::filesystem::exists(directory / "neck.sock") ||
    !std::filesystem::exists(directory / "neck-primary-revoke.sock")) &&
    std::chrono::steady_clock::now() < provision_deadline)
  {
    executor.spin_some();
    std::this_thread::sleep_for(10ms);
  }
  ASSERT_TRUE(std::filesystem::exists(directory / "neck.sock"));
  ASSERT_TRUE(std::filesystem::exists(directory / "neck-primary-revoke.sock"));
  ASSERT_TRUE(send_client->wait_for_service(2s));
  ASSERT_TRUE(result_client->wait_for_service(2s));
  ASSERT_TRUE(cancel_client->wait_for_service(2s));

  hardware_interface::InterfaceInfo position;
  position.name = "position";
  position.initial_value = "0.1";
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
  ASSERT_EQ(controller.get_node()->activate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);
  const auto gate = controller.active_gate_for_test();
  ASSERT_NE(gate, nullptr);
  ASSERT_TRUE(gate->arm(5));
  EXPECT_EQ(gate->generation(), 5u);
  EXPECT_EQ(primary.armed_generation(), 5u);
  EXPECT_EQ(primary.main_generation(), 5u);
  const auto header = controller.get_node()->get_clock()->now();
  auto goal = safe_head_goal(header.nanoseconds());
  goal.trajectory.points[1].positions[0] = 0.101;
  Admission::GoalUUID uuid{};
  uuid.fill(first_sample_before_close ? 0x72 : 0x71);
  const auto close_uuid_text = [&uuid]() {
      std::ostringstream text;
      for (const auto byte : uuid) {
        text << std::hex << std::setw(2) << std::setfill('0') << static_cast<unsigned>(byte);
      }
      return text.str();
    };
  std::cerr << "HEAD_PRIMARY_CLOSE_FIXTURE uuid=" << close_uuid_text()
            << " armed_generation=" << gate->generation()
            << " primary_identity_generation=" << static_cast<unsigned>(primary.armed_generation())
            << " main_identity_generation=" << static_cast<unsigned>(primary.main_generation())
            << " close_generation=5 first_sample=" << first_sample_before_close << std::endl;
  ASSERT_TRUE(reserve_bound_head_goal(gate, uuid, goal));
  auto send_request = std::make_shared<SendGoal::Request>();
  send_request->goal_id.uuid = uuid;
  send_request->goal = goal;
  auto send_future = send_client->async_send_request(send_request);
  ASSERT_EQ(executor.spin_until_future_complete(send_future, 2s),
    rclcpp::FutureReturnCode::SUCCESS);
  ASSERT_TRUE(send_future.get()->accepted);
  if (first_sample_before_close) {
    ASSERT_EQ(controller.update(header + rclcpp::Duration::from_nanoseconds(2000000),
        rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  }
  const auto stop_deadline = std::chrono::steady_clock::now() + 1s;
  const uint8_t close_ack = primary.revoke();
  std::cerr << "HEAD_PRIMARY_CLOSE_REQUEST uuid=" << close_uuid_text()
            << " requested_generation=5 ack=" << static_cast<unsigned>(close_ack)
            << " first_sample=" << first_sample_before_close << std::endl;
  EXPECT_EQ(close_ack, 0u);
  if (concurrent_cancel) {
    auto request = std::make_shared<CancelGoal::Request>();
    request->goal_info.goal_id.uuid = uuid;
    auto future = cancel_client->async_send_request(request);
    ASSERT_EQ(executor.spin_until_future_complete(future, 500ms),
      rclcpp::FutureReturnCode::SUCCESS);
    const auto cancellation = future.get();
    ASSERT_EQ(cancellation->goals_canceling.size(), 1u);
    EXPECT_EQ(cancellation->goals_canceling[0].goal_id.uuid, uuid);
    std::cerr << "HEAD_CLOSE_CANCEL_SAME_UUID uuid=" << close_uuid_text()
              << " cancel_accepted=1 before_revoked_update=1" << std::endl;
  }
  const int64_t update_offset = first_sample_before_close ? 4000000LL : 2000000LL;
  ASSERT_EQ(controller.update(header + rclcpp::Duration::from_nanoseconds(update_offset),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  const auto held_command = command->get_optional();
  ASSERT_TRUE(held_command.has_value());
  EXPECT_NEAR(held_command.value(), 0.1, 1e-12);
  const uint8_t socket_rearm = primary.arm(true);
  std::cerr << "HEAD_PRIMARY_CLOSE_SOCKET_REARM uuid=" << close_uuid_text()
            << " attempted_generation=6 result=" << static_cast<unsigned>(socket_rearm)
            << std::endl;
  EXPECT_EQ(socket_rearm, 1u);

  auto result_request = std::make_shared<GetResult::Request>();
  result_request->goal_id.uuid = uuid;
  auto result_future = result_client->async_send_request(result_request);
  const auto result_budget = concurrent_cancel ?
    std::max(std::chrono::steady_clock::duration::zero(),
      stop_deadline - std::chrono::steady_clock::now()) : std::chrono::seconds(3);
  ASSERT_EQ(executor.spin_until_future_complete(result_future, result_budget),
    rclcpp::FutureReturnCode::SUCCESS);
  const auto result = result_future.get();
  ASSERT_NE(result, nullptr);
  EXPECT_EQ(static_cast<int>(result->status), action_msgs::msg::GoalStatus::STATUS_ABORTED);
  EXPECT_EQ(result->result.error_code, Action::Result::INVALID_GOAL);
  EXPECT_EQ(result->result.error_string, "Head measured-prefix guard refused the first command");
  const bool direct_rearm = gate->arm(6);
  std::cerr << "HEAD_PRIMARY_CLOSE_STICKY uuid=" << close_uuid_text()
            << " attempted_generation=6 direct_gate_rearm=" << direct_rearm << std::endl;
  EXPECT_FALSE(direct_rearm);
  std::cerr << "HEAD_ACTION_PRIMARY_CLOSE first_sample=" << first_sample_before_close
            << " status=" << static_cast<int>(result->status)
            << " error_code=" << result->result.error_code
            << " held_command=" << held_command.value() << std::endl;
  ASSERT_EQ(controller.get_node()->deactivate().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(std::filesystem::exists(directory / "neck.sock"));
  EXPECT_FALSE(std::filesystem::exists(directory / "neck-primary-revoke.sock"));
  executor.remove_node(client_node->get_node_base_interface());
  executor.remove_node(controller.get_node()->get_node_base_interface());
  controller.release_interfaces();
}

TEST(BrokerOwnedTrajectoryController, HeadPrimaryClosePublishesActualPendingAndActiveGoalResults)
{
  exercise_primary_close_owned_action(false);
  exercise_primary_close_owned_action(true);
}

TEST(BrokerOwnedTrajectoryController, HeadPrimaryCloseAndConcurrentCancelPublishOneTerminal)
{
  exercise_primary_close_owned_action(false, true);
  exercise_primary_close_owned_action(true, true);
}

static void exercise_file_mode_prefix_edges(bool continuous_neck, int speed_profile = 0)
{
  struct PrefixCase
  {
    const char * name;
    int64_t remaining_ns;
    int64_t first_point_ns;
    double measured_position;
    double measured_velocity;
    double first_position;
    double last_position;
    const char * damage;
    bool expected_holding;
  };
  const double velocity_limit = 0.04136050464213824;
  std::vector<PrefixCase> cases{
    {"nominal_T404ms", 404000000, 400000000, 0.1, 0.0, 0.1, 0.101, "", false},
    {"positive_residual_velocity_T404ms", 404000000, 400000000, 0.1,
      velocity_limit, 0.1, 0.101, "", false},
    {"negative_residual_velocity_T404ms", 404000000, 400000000, 0.1,
      -velocity_limit, 0.1, 0.101, "", false},
    {"positive_velocity_and_positive_2mm_mismatch", 2014000000, 2000000000,
      0.1, velocity_limit, std::nextafter(0.102, 0.0), 0.103, "", false},
    {"negative_velocity_and_negative_2mm_mismatch", 2014000000, 2000000000,
      0.1, -velocity_limit, std::nextafter(0.098, 1.0), 0.097, "", false},
    {"positive_2mm_mismatch_inside_binary", 404000000, 400000000, 0.1, 0.0,
      std::nextafter(0.102, 0.0), 0.103, "", false},
    {"negative_2mm_mismatch_inside_binary", 404000000, 400000000, 0.1, 0.0,
      std::nextafter(0.098, 1.0), 0.097, "", false},
    {"unsafe_100us_remaining", 100000, 400000000, 0.1, velocity_limit,
      0.101, 0.102, "", true},
    {"at_exact_first_point", 0, 400000000, 0.1, 0.0, 0.101, 0.102, "", true},
    {"late_first_point_2ms", -2000000, 400000000, 0.1, 0.0, 0.101, 0.102, "", true},
    {"position_mismatch_one_ulp_above_limit", 404000000, 400000000, 0.1, 0.0,
      std::nextafter(0.102, std::numeric_limits<double>::infinity()), 0.103, "", true},
    {"negative_position_mismatch_one_ulp_above_limit", 404000000, 400000000, 0.1, 0.0,
      std::nextafter(0.098, -std::numeric_limits<double>::infinity()), 0.097, "", true},
    {"remaining_time_one_ns_above_upper_bound", 414000001, 400000000, 0.1, 0.0,
      0.1, 0.101, "", true},
    {"measured_velocity_above_limit", 2014000000, 2000000000, 0.1,
      std::nextafter(velocity_limit, std::numeric_limits<double>::infinity()),
      0.1, 0.101, "", true},
    {"nonzero_first_derivative", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.101, "first_velocity", true},
    {"nonzero_first_acceleration", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.101, "first_acceleration", true},
    {"nonzero_last_velocity", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.101, "last_velocity", true},
    {"nonzero_last_acceleration", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.101, "last_acceleration", true},
    {"missing_velocity_shape", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.101, "missing_velocity", true},
    {"missing_acceleration_shape", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.101, "missing_acceleration", true},
    {"missing_position_shape", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.101, "missing_position", true},
    {"missing_last_position_shape", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.101, "missing_last_position", true},
    {"planned_nan_position", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.101, "planned_nan_position", true},
    {"planned_nan_velocity", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.101, "planned_nan_velocity", true},
    {"planned_nan_acceleration", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.101, "planned_nan_acceleration", true},
    {"invalid_header_nanosec", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.101, "invalid_header_nanosec", true},
    {"zero_header", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.101, "zero_header", true},
    {"main_velocity_bound", 404000000, 400000000, 0.1, 0.0,
      0.1, 1.2, "two_second_main", true},
    {"main_acceleration_bound", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.2, "short_main_time", true},
    {"main_position_geometry", 404000000, 400000000, 0.1, 0.0,
      0.1, 7.0, "", true},
    {"positive_geometry_edge", 404000000, 400000000, 6.283, 0.0,
      6.283, 6.283175307179587, "", false},
    {"negative_geometry_edge", 404000000, 400000000, -6.283, 0.0,
      -6.283, -6.283175307179587, "", false},
    {"positive_geometry_overflow", 404000000, 400000000, 6.283, 0.0,
      6.283, std::nextafter(6.283175307179587, 7.0), "", true},
    {"negative_geometry_overflow", 404000000, 400000000, -6.283, 0.0,
      -6.283, std::nextafter(-6.283175307179587, -7.0), "", true},
    {"full_turn_displacement", 404000000, 400000000, -3.14, 0.0,
      -3.14, 3.143185307179586, "", true},
    {"main_time_limit", 404000000, 400000000, 0.1, 0.0,
      0.1, 0.101, "long_main_time", true},
  };
  if (speed_profile >= 1) {
    // One-second rest-to-rest motion: peak v=0.2625, peak a=0.808291.
    cases.push_back({"faster_acceleration_1", 54000000, 50000000, 0.1, 0.0,
      0.1, 0.24, "", false});
  }
  if (speed_profile >= 2) {
    // One-second rest-to-rest motion: peak v=0.45, peak a=1.385641.
    cases.push_back({"faster_acceleration_2", 54000000, 50000000, 0.1, 0.0,
      0.1, 0.34, "", false});
  }
  if (speed_profile >= 3) {
    // 1.1-second rest-to-rest motion: peak v=0.681818, peak a=1.908596.
    cases.push_back({"faster_velocity_1_acceleration_2", 54000000, 50000000, 0.1, 0.0,
      0.1, 0.5, "eleven_tenths_main", false});
  }
  const auto directory = private_socket_directory();
  const ScopedReservationEnvironment reservation_scope(directory, "session-17");
  ScopedNativeMonitor primary(directory, true);
  rclcpp::init(0, nullptr);
  struct ShutdownGuard {~ShutdownGuard() {rclcpp::shutdown();}} shutdown_guard;
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
    rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1"),
    rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000)),
    rclcpp::Parameter("head_measured_prefix_guard", "quintic_measured_prefix_v1"),
    rclcpp::Parameter("speed_scaling_input_enabled", false),
  });
  ASSERT_EQ(controller.init("neck_controller",
      continuous_neck ? continuous_neck_urdf() : neck_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  hardware_interface::InterfaceInfo position;
  position.name = "position";
  position.initial_value = "0.1";
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
  ASSERT_EQ(controller.get_node()->activate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);
  const auto origin = controller.get_node()->get_clock()->now();
  for (size_t index = 0; index < cases.size(); ++index) {
    const auto & test_case = cases[index];
    const auto update_time = origin + rclcpp::Duration::from_nanoseconds(
      static_cast<int64_t>(index + 1) * 4000000);
    ASSERT_TRUE(state_position->set_value(test_case.measured_position));
    ASSERT_TRUE(state_velocity->set_value(test_case.measured_velocity));
    const auto header_ns = update_time.nanoseconds() + test_case.remaining_ns -
      test_case.first_point_ns;
    auto goal = safe_head_goal(header_ns, test_case.first_position);
    auto & trajectory = goal.trajectory;
    trajectory.points[0].time_from_start.sec = static_cast<int32_t>(
      test_case.first_point_ns / 1000000000LL);
    trajectory.points[0].time_from_start.nanosec = static_cast<uint32_t>(
      test_case.first_point_ns % 1000000000LL);
    trajectory.points[1].time_from_start.sec = static_cast<int32_t>(
      (test_case.first_point_ns + 1000000000LL) / 1000000000LL);
    trajectory.points[1].time_from_start.nanosec = static_cast<uint32_t>(
      (test_case.first_point_ns + 1000000000LL) % 1000000000LL);
    trajectory.points[1].positions[0] = test_case.last_position;
    if (std::string(test_case.damage) == "first_velocity") {
      trajectory.points[0].velocities[0] = 0.01;
    } else if (std::string(test_case.damage) == "first_acceleration") {
      trajectory.points[0].accelerations[0] = 0.01;
    } else if (std::string(test_case.damage) == "last_velocity") {
      trajectory.points[1].velocities[0] = 0.01;
    } else if (std::string(test_case.damage) == "last_acceleration") {
      trajectory.points[1].accelerations[0] = 0.01;
    } else if (std::string(test_case.damage) == "missing_velocity") {
      trajectory.points[0].velocities.clear();
    } else if (std::string(test_case.damage) == "missing_acceleration") {
      trajectory.points[0].accelerations.clear();
    } else if (std::string(test_case.damage) == "missing_position") {
      trajectory.points[0].positions.clear();
    } else if (std::string(test_case.damage) == "missing_last_position") {
      trajectory.points[1].positions.clear();
    } else if (std::string(test_case.damage) == "planned_nan_position") {
      trajectory.points[0].positions[0] = std::numeric_limits<double>::quiet_NaN();
    } else if (std::string(test_case.damage) == "planned_nan_velocity") {
      trajectory.points[0].velocities[0] = std::numeric_limits<double>::quiet_NaN();
    } else if (std::string(test_case.damage) == "planned_nan_acceleration") {
      trajectory.points[0].accelerations[0] = std::numeric_limits<double>::quiet_NaN();
    } else if (std::string(test_case.damage) == "zero_header") {
      trajectory.header.stamp.sec = 0;
      trajectory.header.stamp.nanosec = 0;
    } else if (std::string(test_case.damage) == "invalid_header_nanosec") {
      trajectory.header.stamp.nanosec = 1000000000U;
    } else if (std::string(test_case.damage) == "short_main_time" ||
      std::string(test_case.damage) == "two_second_main" ||
      std::string(test_case.damage) == "eleven_tenths_main")
    {
      const auto duration_ns = std::string(test_case.damage) == "short_main_time" ?
        500000000LL : (std::string(test_case.damage) == "two_second_main" ?
        2000000000LL : 1100000000LL);
      const auto end_ns = test_case.first_point_ns + duration_ns;
      trajectory.points[1].time_from_start.sec = static_cast<int32_t>(end_ns / 1000000000LL);
      trajectory.points[1].time_from_start.nanosec = static_cast<uint32_t>(end_ns % 1000000000LL);
    } else if (std::string(test_case.damage) == "long_main_time") {
      trajectory.points[1].time_from_start.sec = std::numeric_limits<int32_t>::max();
      trajectory.points[1].time_from_start.nanosec = 0;
    }
    const auto previous = command->get_optional();
    ASSERT_TRUE(previous.has_value());
    controller.publish_trajectory_for_test(
      std::make_shared<trajectory_msgs::msg::JointTrajectory>(trajectory));
    const auto result = controller.update(update_time, rclcpp::Duration::from_seconds(0.002));
    ASSERT_EQ(result, controller_interface::return_type::OK) << test_case.name;
    EXPECT_EQ(controller.holding_for_test(), test_case.expected_holding) << test_case.name;
    const auto after = command->get_optional();
    ASSERT_TRUE(after.has_value()) << test_case.name;
    if (test_case.expected_holding) {
      EXPECT_NEAR(after.value(), test_case.measured_position, 1e-12) << test_case.name;
    } else {
      const double remaining = static_cast<double>(test_case.remaining_ns) / 1e9;
      const double normalized_time = 0.002 / remaining;
      const double initial_tangent = test_case.measured_velocity * remaining;
      const double displacement = test_case.first_position - test_case.measured_position;
      const double c3 = 10.0 * displacement - 6.0 * initial_tangent;
      const double c4 = -15.0 * displacement + 8.0 * initial_tangent;
      const double c5 = 6.0 * displacement - 3.0 * initial_tangent;
      const double expected_sample = test_case.measured_position +
        initial_tangent * normalized_time + c3 * std::pow(normalized_time, 3) +
        c4 * std::pow(normalized_time, 4) + c5 * std::pow(normalized_time, 5);
      EXPECT_NEAR(after.value(), expected_sample, 1e-12) << test_case.name;
      if (std::string(test_case.name).find("mismatch") != std::string::npos) {
        EXPECT_NE(expected_sample, test_case.measured_position) << test_case.name;
        EXPECT_NE(after.value(), previous.value()) << test_case.name;
      }
      std::cerr << "HEAD_PREFIX_ANALYTIC name=" << test_case.name
                << " remaining_ns=" << test_case.remaining_ns
                << " sample_offset_ns=2000000 expected=" << expected_sample << std::endl;
    }
    std::cerr << std::setprecision(17) << "HEAD_PREFIX_CASE name=" << test_case.name
              << " holding=" << controller.holding_for_test()
              << " measured_q=" << test_case.measured_position
              << " measured_v=" << test_case.measured_velocity
              << " first_q=" << test_case.first_position
              << " mismatch=" << std::abs(test_case.first_position - test_case.measured_position)
              << " command=" << after.value() << std::endl;
    if (test_case.expected_holding) {
      const auto retry_time = update_time + rclcpp::Duration::from_nanoseconds(2000000);
      EXPECT_EQ(controller.update(retry_time, rclcpp::Duration::from_seconds(0.002)),
        controller_interface::return_type::OK) << test_case.name;
      EXPECT_TRUE(controller.holding_for_test()) << test_case.name;
      const auto retry_command = command->get_optional();
      ASSERT_TRUE(retry_command.has_value()) << test_case.name;
      EXPECT_NEAR(retry_command.value(), test_case.measured_position, 1e-12) << test_case.name;
      EXPECT_TRUE(std::isfinite(retry_command.value())) << test_case.name;
    }
  }
  ASSERT_EQ(controller.get_node()->deactivate().id(),
    lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  controller.release_interfaces();
}

TEST(BrokerOwnedTrajectoryController, FileModeAcceptsFasterAccelerationProfile)
{
  exercise_file_mode_prefix_edges(true, 1);
}

TEST(BrokerOwnedTrajectoryController, FileModeAcceptsAccelerationTwoProfile)
{
  exercise_file_mode_prefix_edges(true, 2);
}

TEST(BrokerOwnedTrajectoryController, FileModeAcceptsVelocityOneAccelerationTwoProfile)
{
  exercise_file_mode_prefix_edges(true, 3);
}

TEST(BrokerOwnedTrajectoryController, FileModeLoanedUpdateCoversMeasuredPrefixEdgesAndRefusals)
{
  exercise_file_mode_prefix_edges(false);
}

TEST(BrokerOwnedTrajectoryController, ContinuousFileModePreservesPrefixAndSafetyRefusals)
{
  exercise_file_mode_prefix_edges(true);
}

TEST(BrokerOwnedTrajectoryController, ContinuousNeckRetainsCoordinatesAcrossPiOnlyInHeadMode)
{
  const auto directory = private_socket_directory();
  const ScopedReservationEnvironment scope(directory, "session-17");
  ScopedNativeMonitor primary(directory, true);
  rclcpp::init(0, nullptr);
  struct ShutdownGuard {~ShutdownGuard() {rclcpp::shutdown();}} shutdown_guard;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
    rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1"),
    rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000)),
    rclcpp::Parameter("head_measured_prefix_guard", "quintic_measured_prefix_v1"),
    rclcpp::Parameter("speed_scaling_input_enabled", false),
  });
  InspectableController controller;
  ASSERT_EQ(controller.init("neck_controller", continuous_neck_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(controller.neck_wraps_for_test());
  hardware_interface::InterfaceInfo position;
  position.name = "position";
  position.initial_value = "3.14";
  hardware_interface::InterfaceInfo velocity;
  velocity.name = "velocity";
  velocity.initial_value = "0";
  auto command = std::make_shared<hardware_interface::CommandInterface>(
    hardware_interface::InterfaceDescription("neck_yaw_joint", position));
  auto measured_position = std::make_shared<hardware_interface::StateInterface>(
    hardware_interface::InterfaceDescription("neck_yaw_joint", position));
  auto measured_velocity = std::make_shared<hardware_interface::StateInterface>(
    hardware_interface::InterfaceDescription("neck_yaw_joint", velocity));
  std::vector<hardware_interface::LoanedCommandInterface> commands;
  std::vector<hardware_interface::LoanedStateInterface> states;
  commands.emplace_back(command, []() {});
  states.emplace_back(measured_position);
  states.emplace_back(measured_velocity);
  controller.assign_interfaces(std::move(commands), std::move(states));
  ASSERT_EQ(controller.get_node()->activate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);
  const auto origin = controller.get_node()->get_clock()->now();
  for (const int direction : {1, -1}) {
    SCOPED_TRACE(direction);
    const double start = direction * 3.14;
    const double target = direction * 3.19;
    ASSERT_TRUE(measured_position->set_value(start));
    const auto update_time = origin + rclcpp::Duration::from_seconds(direction == 1 ? 0.0 : 3.0);
    auto goal = safe_head_goal(update_time.nanoseconds(), start);
    goal.trajectory.points[1].positions[0] = target;
    controller.publish_trajectory_for_test(
      std::make_shared<trajectory_msgs::msg::JointTrajectory>(goal.trajectory));
    ASSERT_EQ(controller.update(update_time, rclcpp::Duration::from_seconds(0.002)),
      controller_interface::return_type::OK);
    ASSERT_FALSE(controller.holding_for_test());
    EXPECT_NEAR(command->get_optional().value(), start, 1e-12);
    // JTC advances its trajectory clock by the actual period of each update.
    // Exercise every native 500 Hz tick; a timestamp jump is not 450 ticks.
    for (int tick = 1; tick <= 450; ++tick) {
      const auto sample_time = update_time + rclcpp::Duration::from_nanoseconds(tick * 2000000LL);
      ASSERT_EQ(controller.update(sample_time, rclcpp::Duration::from_seconds(0.002)),
        controller_interface::return_type::OK);
    }
    // JTC samples one update period ahead: u=(0.9+0.002-0.4)/1.0.
    const double u = 0.502;
    const double expected = start + (target-start) *
      (10*std::pow(u, 3) - 15*std::pow(u, 4) + 6*std::pow(u, 5));
    EXPECT_NEAR(command->get_optional().value(), expected, 1e-10);
    EXPECT_GT(std::abs(command->get_optional().value()), std::acos(-1.0));
    // Error uses the current sample (u=0.5), while the command looks ahead.
    EXPECT_NEAR(controller.position_error_for_test(), (target-start)*0.5, 1e-10);
    ASSERT_TRUE(measured_position->set_value(-start));
    ASSERT_EQ(controller.update(update_time + rclcpp::Duration::from_nanoseconds(902000000),
        rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
    EXPECT_NEAR(controller.position_error_for_test(), expected+start, 1e-10);
    EXPECT_GT(std::abs(controller.position_error_for_test()), 6.0);
  }
  ASSERT_EQ(controller.get_node()->deactivate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  controller.release_interfaces();
  ASSERT_EQ(controller.get_node()->cleanup().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_UNCONFIGURED);

  InspectableController legacy_controller;
  rclcpp::NodeOptions legacy_options;
  legacy_options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
  });
  ASSERT_EQ(legacy_controller.init("legacy_neck_controller", continuous_neck_urdf(), 500,
      "", legacy_options), controller_interface::return_type::OK);
  ASSERT_EQ(legacy_controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_TRUE(legacy_controller.neck_wraps_for_test());
  EXPECT_FALSE(legacy_controller.get_node()->get_subscriptions_info_by_topic(
      "/legacy_neck_controller/speed_scaling_input").empty());
}

TEST(BrokerOwnedTrajectoryController, FileModeNaNMeasuredPositionCannotInstallCandidateLater)
{
  const auto directory = private_socket_directory();
  const ScopedReservationEnvironment scope(directory, "session-17");
  ScopedNativeMonitor primary(directory, true);
  rclcpp::init(0, nullptr);
  struct ShutdownGuard {~ShutdownGuard() {rclcpp::shutdown();}} shutdown_guard;
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
    rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1"),
    rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000)),
    rclcpp::Parameter("head_measured_prefix_guard", "quintic_measured_prefix_v1"),
    rclcpp::Parameter("speed_scaling_input_enabled", false),
  });
  ASSERT_EQ(controller.init("neck_controller", neck_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
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
  ASSERT_EQ(controller.get_node()->activate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);
  for (int64_t index = 1; index <= 51; ++index) {
    ASSERT_EQ(controller.update(rclcpp::Time(index * 2000000, RCL_ROS_TIME),
        rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  }
  ASSERT_TRUE(state_position->set_value(std::numeric_limits<double>::quiet_NaN()));
  auto candidate = std::make_shared<trajectory_msgs::msg::JointTrajectory>();
  candidate->joint_names = {"neck_yaw_joint"};
  candidate->header.stamp = rclcpp::Time(static_cast<int64_t>(2000000000), RCL_ROS_TIME);
  trajectory_msgs::msg::JointTrajectoryPoint first;
  first.positions = {0.1};
  first.velocities = {0.0};
  first.accelerations = {0.0};
  first.time_from_start.nanosec = 400000000;
  trajectory_msgs::msg::JointTrajectoryPoint last;
  last.positions = {0.2};
  last.velocities = {0.0};
  last.accelerations = {0.0};
  last.time_from_start.sec = 5;
  candidate->points = {first, last};
  controller.publish_trajectory_for_test(candidate);
  const auto command_before = command->get_optional();
  ASSERT_TRUE(command_before.has_value());
  EXPECT_EQ(controller.update(rclcpp::Time(static_cast<int64_t>(2399900000), RCL_ROS_TIME),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::ERROR);
  const auto command_after_nan = command->get_optional();
  ASSERT_TRUE(command_after_nan.has_value());
  EXPECT_TRUE(std::isfinite(command_after_nan.value()));
  EXPECT_EQ(command_after_nan.value(), command_before.value());
  ASSERT_TRUE(state_position->set_value(0.102));
  ASSERT_TRUE(state_velocity->set_value(0.0));
  EXPECT_EQ(controller.update(rclcpp::Time(static_cast<int64_t>(2401900000), RCL_ROS_TIME),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  const auto later_command = command->get_optional();
  ASSERT_TRUE(later_command.has_value());
  EXPECT_NEAR(later_command.value(), 0.102, 1e-12);
  ASSERT_TRUE(state_velocity->set_value(std::numeric_limits<double>::quiet_NaN()));
  auto velocity_candidate = std::make_shared<trajectory_msgs::msg::JointTrajectory>(*candidate);
  velocity_candidate->header.stamp = rclcpp::Time(static_cast<int64_t>(2403900000), RCL_ROS_TIME);
  controller.publish_trajectory_for_test(velocity_candidate);
  EXPECT_EQ(controller.update(rclcpp::Time(static_cast<int64_t>(2405900000), RCL_ROS_TIME),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::ERROR);
  EXPECT_NEAR(command->get_optional().value(), 0.102, 1e-12);
  ASSERT_TRUE(state_position->set_value(0.103));
  ASSERT_TRUE(state_velocity->set_value(0.0));
  EXPECT_EQ(controller.update(rclcpp::Time(static_cast<int64_t>(2407900000), RCL_ROS_TIME),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  EXPECT_NEAR(command->get_optional().value(), 0.103, 1e-12);
  ASSERT_EQ(controller.get_node()->deactivate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  controller.release_interfaces();
}

TEST(BrokerOwnedTrajectoryController, FileModeActiveNaNStateRecoveryReplacesInstalledTrajectoryWithHold)
{
  const auto directory = private_socket_directory();
  const ScopedReservationEnvironment scope(directory, "session-17");
  ScopedNativeMonitor primary(directory, true);
  rclcpp::init(0, nullptr);
  struct ShutdownGuard {~ShutdownGuard() {rclcpp::shutdown();}} shutdown_guard;
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
    rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1"),
    rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000)),
    rclcpp::Parameter("head_measured_prefix_guard", "quintic_measured_prefix_v1"),
    rclcpp::Parameter("speed_scaling_input_enabled", false),
  });
  ASSERT_EQ(controller.init("neck_controller", neck_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  ASSERT_EQ(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  hardware_interface::InterfaceInfo position;
  position.name = "position";
  position.initial_value = "0.1";
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
  ASSERT_EQ(controller.get_node()->activate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);
  for (int64_t index = 1; index <= 51; ++index) {
    ASSERT_EQ(controller.update(rclcpp::Time(index * 2000000, RCL_ROS_TIME),
        rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  }
  auto active = std::make_shared<trajectory_msgs::msg::JointTrajectory>();
  active->joint_names = {"neck_yaw_joint"};
  active->header.stamp = rclcpp::Time(static_cast<int64_t>(2000000000), RCL_ROS_TIME);
  trajectory_msgs::msg::JointTrajectoryPoint first;
  first.positions = {0.1};
  first.velocities = {0.0};
  first.accelerations = {0.0};
  first.time_from_start.nanosec = 404000000;
  trajectory_msgs::msg::JointTrajectoryPoint last;
  last.positions = {0.2};
  last.velocities = {0.0};
  last.accelerations = {0.0};
  last.time_from_start.sec = 5;
  active->points = {first, last};
  controller.publish_trajectory_for_test(active);
  ASSERT_EQ(controller.update(rclcpp::Time(static_cast<int64_t>(2000000000), RCL_ROS_TIME),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  for (int64_t index = 1; index <= 302; ++index) {
    ASSERT_EQ(controller.update(
        rclcpp::Time(static_cast<int64_t>(2000000000 + index * 2000000), RCL_ROS_TIME),
        rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  }
  const auto command_before_nan = command->get_optional();
  ASSERT_TRUE(command_before_nan.has_value());
  EXPECT_GT(std::abs(command_before_nan.value() - 0.1), 1e-6);
  ASSERT_TRUE(state_position->set_value(std::numeric_limits<double>::quiet_NaN()));
  EXPECT_EQ(controller.update(rclcpp::Time(static_cast<int64_t>(2606000000), RCL_ROS_TIME),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::ERROR);
  EXPECT_EQ(command->get_optional().value(), command_before_nan.value());
  ASSERT_TRUE(state_position->set_value(0.15));
  EXPECT_EQ(controller.update(rclcpp::Time(static_cast<int64_t>(2608000000), RCL_ROS_TIME),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  ASSERT_TRUE(command->get_optional().has_value());
  EXPECT_NEAR(command->get_optional().value(), 0.15, 1e-12);
  EXPECT_EQ(controller.update(rclcpp::Time(static_cast<int64_t>(2610000000), RCL_ROS_TIME),
      rclcpp::Duration::from_seconds(0.002)), controller_interface::return_type::OK);
  EXPECT_NEAR(command->get_optional().value(), 0.15, 1e-12);
  ASSERT_EQ(controller.get_node()->deactivate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  controller.release_interfaces();
}

static void exercise_head_policy_rejection(
  rclcpp::Parameter mode, rclcpp::Parameter timeout, bool predeclared_mutable = false,
  rclcpp::Parameter speed_switch = rclcpp::Parameter("speed_scaling_input_enabled", false),
  bool predeclared_mutable_switch = false,
  std::optional<rclcpp::Parameter> extra_parameter = std::nullopt)
{
  const auto directory = private_socket_directory();
  const ScopedReservationEnvironment scope(directory, "session-17");
  rclcpp::init(0, nullptr);
  struct ShutdownGuard {~ShutdownGuard() {rclcpp::shutdown();}} shutdown_guard;
  InspectableController controller;
  rclcpp::NodeOptions options;
  std::vector<rclcpp::Parameter> overrides{
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
    mode, timeout,
    rclcpp::Parameter("head_measured_prefix_guard", "quintic_measured_prefix_v1"),
    speed_switch,
  };
  if (extra_parameter) {overrides.push_back(*extra_parameter);}
  options.parameter_overrides(overrides);
  ASSERT_EQ(controller.init("neck_controller", neck_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  if (predeclared_mutable) {
    controller.get_node()->declare_parameter("head_simulation_mode", std::string{});
    controller.get_node()->declare_parameter("head_fault_connection_timeout_ns", int64_t(2000000));
  }
  if (predeclared_mutable_switch) {
    controller.get_node()->declare_parameter("speed_scaling_input_enabled", false);
  }
  EXPECT_NE(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(controller.action_server_exists());
  for (const auto * endpoint : {"neck.sock", "neck-revoke.sock", "neck-primary-revoke.sock"}) {
    EXPECT_FALSE(std::filesystem::exists(directory / endpoint));
  }
}

TEST(BrokerOwnedTrajectoryController, FileModeRejectsNonCandidateBudgetAndLegacyMode)
{
  const auto mode = rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1");
  for (const int64_t timeout : {int64_t(0), int64_t(-1), int64_t(50000001), int64_t(250000001)}) {
    exercise_head_policy_rejection(mode, rclcpp::Parameter("head_fault_connection_timeout_ns", timeout));
  }
  exercise_head_policy_rejection(rclcpp::Parameter("head_simulation_mode", "other"),
    rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000)));
  exercise_head_policy_rejection(rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search"),
    rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000)));
  exercise_head_policy_rejection(rclcpp::Parameter("head_simulation_mode", ""),
    rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000)));
}

TEST(BrokerOwnedTrajectoryController, FileModeWrongParameterTypesCannotPublishServices)
{
  exercise_head_policy_rejection(rclcpp::Parameter("head_simulation_mode", true),
    rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000)));
  for (const auto & timeout : {rclcpp::Parameter("head_fault_connection_timeout_ns", true),
      rclcpp::Parameter("head_fault_connection_timeout_ns", 50000000.)})
  {
    exercise_head_policy_rejection(
      rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1"), timeout);
  }
}

TEST(BrokerOwnedTrajectoryController, FileModeRejectsMutableReadonlyDescriptors)
{
  const auto mode = rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1");
  const auto timeout = rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000));
  exercise_head_policy_rejection(mode, timeout, true);
}

TEST(BrokerOwnedTrajectoryController, FileModeRequiresDisabledReadonlyBaseSpeedScalingSwitch)
{
  const auto mode = rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1");
  const auto timeout = rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000));
  exercise_head_policy_rejection(mode, timeout, false,
    rclcpp::Parameter("speed_scaling_input_enabled", true));
  exercise_head_policy_rejection(mode, timeout, false,
    rclcpp::Parameter("speed_scaling_input_enabled", std::string("false")));
  exercise_head_policy_rejection(mode, timeout, false,
    rclcpp::Parameter("speed_scaling_input_enabled", false), true);
}

TEST(BrokerOwnedTrajectoryController, FileModeRejectsUnsupportedBaseScalingConfiguration)
{
  const auto mode = rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1");
  const auto timeout = rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000));
  exercise_head_policy_rejection(mode, timeout, false,
    rclcpp::Parameter("speed_scaling_input_enabled", false), false,
    rclcpp::Parameter("speed_scaling.state_interface", "speed_scaling"));
  exercise_head_policy_rejection(mode, timeout, false,
    rclcpp::Parameter("speed_scaling_input_enabled", false), false,
    rclcpp::Parameter("speed_scaling.command_interface", "speed_scaling"));
  exercise_head_policy_rejection(mode, timeout, false,
    rclcpp::Parameter("speed_scaling_input_enabled", false), false,
    rclcpp::Parameter("speed_scaling.initial_scaling_factor", 0.5));
}

TEST(BrokerOwnedTrajectoryController, FileModeMissingReservationScopeCannotConfigure)
{
  const auto * previous_directory = std::getenv("SO101_ACT_CONTROLLER_RESERVATION_DIR");
  const auto * previous_session = std::getenv("SO101_SIMULATION_SESSION_ID");
  const std::optional<std::string> directory_value = previous_directory ?
    std::optional<std::string>(previous_directory) : std::nullopt;
  const std::optional<std::string> session_value = previous_session ?
    std::optional<std::string>(previous_session) : std::nullopt;
  unsetenv("SO101_ACT_CONTROLLER_RESERVATION_DIR");
  unsetenv("SO101_SIMULATION_SESSION_ID");
  rclcpp::init(0, nullptr);
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
    rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1"),
    rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000)),
    rclcpp::Parameter("head_measured_prefix_guard", "quintic_measured_prefix_v1"),
    rclcpp::Parameter("speed_scaling_input_enabled", false),
  });
  ASSERT_EQ(controller.init("neck_controller", neck_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  EXPECT_NE(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(controller.action_server_exists());
  if (directory_value) {setenv("SO101_ACT_CONTROLLER_RESERVATION_DIR", directory_value->c_str(), 1);}
  if (session_value) {setenv("SO101_SIMULATION_SESSION_ID", session_value->c_str(), 1);}
  rclcpp::shutdown();
}

TEST(BrokerOwnedTrajectoryController, FileModeRejectsUnsupportedUpdateRate)
{
  const auto directory = private_socket_directory();
  const ScopedReservationEnvironment scope(directory, "session-17");
  ScopedNativeMonitor primary(directory, true);
  rclcpp::init(0, nullptr);
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
    rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1"),
    rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000)),
    rclcpp::Parameter("head_measured_prefix_guard", "quintic_measured_prefix_v1"),
    rclcpp::Parameter("speed_scaling_input_enabled", false),
  });
  ASSERT_EQ(controller.init("neck_controller", neck_urdf(), 499, "", options),
    controller_interface::return_type::OK);
  EXPECT_NE(controller.configure().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  EXPECT_FALSE(controller.action_server_exists());
  rclcpp::shutdown();
}

static void exercise_head_local_provision_refusal(const std::string & damage)
{
  const auto directory = private_socket_directory();
  ASSERT_EQ(std::getenv("SO101_HEAD_SEARCH_V2_MONITOR_REQUIRED"), nullptr);
  ScopedNativeMonitor primary(directory, true);
  const auto main_path = directory / "neck.provision";
  const auto primary_path = directory / "neck-primary-revoke.provision";
  if (damage == "missing_main") {
    std::filesystem::remove(main_path);
  } else if (damage == "missing_primary") {
    std::filesystem::remove(primary_path);
  } else if (damage != "valid") {
    std::ifstream input(primary_path, std::ios::binary);
    std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(input)),
      std::istreambuf_iterator<char>());
    if (damage == "actor_pid") {
      for (size_t index = 0; index < 4; ++index) {
        bytes[12 + index] = static_cast<uint8_t>(getpid() >> ((3 - index) * 8));
      }
    } else if (damage == "actor_ticks") {
      for (size_t index = 0; index < 8; ++index) {
        bytes[16 + index] = static_cast<uint8_t>((self_start_ticks() + 1) >> ((7 - index) * 8));
      }
    } else if (damage == "actor_uid") {
      bytes[11] = static_cast<uint8_t>(bytes[11] ^ 1);
    } else if (damage == "main_capability") {
      std::ifstream main_input(main_path, std::ios::binary);
      std::vector<uint8_t> main_bytes((std::istreambuf_iterator<char>(main_input)),
        std::istreambuf_iterator<char>());
      std::copy(main_bytes.begin() + 24, main_bytes.begin() + 56, bytes.begin() + 24);
    } else if (damage == "zero_capability") {
      std::fill(bytes.begin() + 24, bytes.begin() + 56, 0);
    } else if (damage == "wrong_role") {
      bytes[5] = 3;
    } else if (damage == "truncated") {
      bytes.resize(20);
    } else if (damage == "wrong_type") {
      const auto valid_path = directory / "primary.valid";
      std::filesystem::rename(primary_path, valid_path);
      std::filesystem::create_symlink(valid_path, primary_path);
    }
    if (damage != "wrong_type") {
      std::ofstream output(primary_path, std::ios::binary | std::ios::trunc);
      output.write(reinterpret_cast<const char *>(bytes.data()), bytes.size());
    }
  }
  const ScopedReservationEnvironment scope(directory, "session-17");
  rclcpp::init(0, nullptr);
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"}),
    rclcpp::Parameter("head_simulation_mode", "mujoco_bounded_stop_search_file_v1"),
    rclcpp::Parameter("head_fault_connection_timeout_ns", int64_t(50000000)),
    rclcpp::Parameter("head_measured_prefix_guard", "quintic_measured_prefix_v1"),
    rclcpp::Parameter("speed_scaling_input_enabled", false),
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
  EXPECT_FALSE(std::filesystem::exists(directory / "neck-primary-revoke.sock"));
  executor.remove_node(controller.get_node()->get_node_base_interface());
  rclcpp::shutdown();
}

TEST(BrokerOwnedTrajectoryController, FileModeMissingMainProvisionCannotOpenServices)
{
  exercise_head_local_provision_refusal("missing_main");
}

TEST(BrokerOwnedTrajectoryController, FileModeMissingPrimaryProvisionCannotOpenMainEndpoint)
{
  exercise_head_local_provision_refusal("missing_primary");
}

TEST(BrokerOwnedTrajectoryController, FileModePrimaryProvisionRejectsWrongActorCapabilityTypeOrRole)
{
  for (const auto * damage : {"actor_pid", "actor_ticks", "actor_uid", "main_capability",
      "zero_capability", "wrong_role", "truncated", "wrong_type"})
  {
    exercise_head_local_provision_refusal(damage);
  }
}

namespace
{
void fill_wrapper_window(so101_mujoco_support::ControllerStopWitness & witness)
{
  const int64_t now=std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
  for(uint64_t seq=1;seq<=51;++seq) {
    so101_mujoco_support::ControllerStopWitness::Observation sample;
    sample.sequence=seq; sample.sim_time_ns=seq*2000000; sample.joint_count=1;
    sample.received_monotonic_ns=now-102000000+seq*2000000; sample.holding=true;
    witness.observe(sample);
  }
}
}
TEST(BrokerOwnedTrajectoryController, wrapper_inactive_joint_scope_active_before_after)
{
  using namespace so101_mujoco_support;
  ControllerStopWitness witness(1);
  for(int mode=0;mode<6;++mode) {
    fill_wrapper_window(witness);
    int active_calls=0,goal_calls=0;
    const auto result=evaluate_controller_stop(100+mode,
      [&] {return mode!=0 && (mode!=3 || ++active_calls==1);},
      [&]() -> ControllerStopWitness * {return mode==1 ? nullptr : &witness;},
      [&] {return mode==2 || (mode==4 && ++goal_calls==2);});
    const StopWrapperReason reasons[]={StopWrapperReason::INACTIVE_BEFORE,StopWrapperReason::JOINT_SCOPE,
      StopWrapperReason::ACTIVE_BEFORE,StopWrapperReason::INACTIVE_AFTER,StopWrapperReason::ACTIVE_AFTER,
      StopWrapperReason::PASS};
    EXPECT_EQ(result.record.wrapper_reason,reasons[mode]) << mode;
    EXPECT_EQ(result.record.evaluation_id,100u+mode);
    EXPECT_EQ(result.allowed,mode==5);
    EXPECT_EQ(result.snapshot.has_value(),mode>=3);
    if((mode==3 || mode==4) && result.snapshot) {EXPECT_TRUE(result.snapshot->rejection==ControllerStopWitness::RejectionReason::NONE);}
  }
}
TEST(BrokerOwnedTrajectoryController, evaluation_ids_remain_bound_after_subsequent_observe)
{
  using namespace so101_mujoco_support;
  ControllerStopWitness witness(1);
  fill_wrapper_window(witness);
  auto evaluation=evaluate_controller_stop(41,[] {return true;},[&] {return &witness;},[] {return false;});
  ASSERT_TRUE(evaluation.allowed); ASSERT_TRUE(evaluation.snapshot);
  const auto bytes=encode_stop_proof_record(evaluation.record);
  witness.reset();
  const auto next=evaluate_controller_stop(42,[] {return true;},[&] {return &witness;},[] {return false;});
  EXPECT_FALSE(next.allowed); EXPECT_EQ(next.record.wrapper_reason,StopWrapperReason::WITNESS_REJECT);
  EXPECT_EQ(next.record.witness_rejection,2); EXPECT_EQ(next.record.last_reset_reason,2);
  EXPECT_EQ(next.record.sample_count,0);
  EXPECT_EQ(encode_stop_proof_record(evaluation.record),bytes);
  EXPECT_EQ(next.record.evaluation_id,42u);
}
TEST(BrokerOwnedTrajectoryController, fault_close_does_not_wait_for_witness_mutex)
{
  using namespace so101_mujoco_support;
  ControllerStopWitness witness(1); fill_wrapper_window(witness);
  ControllerGoalAdmission gate([] {return 1000;},100,1024,2048,
    ServiceControllerIdentity{ControllerReservationRole::NECK,"inc","boot"});
  std::promise<void> locked,release; auto unlock=release.get_future();
  auto query=std::async(std::launch::async,[&] {return witness.checked_proof_with_clock([&] {
      locked.set_value(); unlock.wait(); return int64_t(0);
    });});
  locked.get_future().wait();
  auto close=std::async(std::launch::async,[&] {return gate.close_scoped(17,ControllerReservationRole::NECK,"inc","boot");});
  EXPECT_EQ(close.wait_for(std::chrono::milliseconds(50)),std::future_status::ready);
  release.set_value(); query.get();
  EXPECT_EQ(close.get().status,ControllerGoalAdmission::ScopedCloseStatus::NOT_ARMED_CLOSED);
}

TEST(BrokerOwnedTrajectoryController, EvaluationIdsIncreaseBeforeAnyOuterCheck)
{
  InspectableController controller;
  const auto first=controller.stop_evaluation();
  const auto second=controller.stop_evaluation();
  EXPECT_FALSE(first.allowed);
  EXPECT_EQ(first.record.wrapper_reason,so101_mujoco_support::StopWrapperReason::INACTIVE_BEFORE);
  EXPECT_GT(first.record.evaluation_id,0u);
  EXPECT_GT(second.record.evaluation_id,first.record.evaluation_id);
  EXPECT_FALSE(first.snapshot);
}

TEST(BrokerOwnedTrajectoryController, UnavailableEvaluationHasNoSnapshotAndKeepsId)
{
  using namespace so101_mujoco_support;
  ControllerStopWitness witness(1);
  fill_wrapper_window(witness);
  ControllerStopWitnessTestAccess::reader_lock(witness);
  int active_calls = 0, goal_calls = 0;
  auto future = std::async(std::launch::async, [&]() {
      return evaluate_controller_stop(97, [&]() {++active_calls; return true;},
        [&]() {return &witness;}, [&]() {++goal_calls; return false;});
    });
  const auto evaluation = future.get();
  ControllerStopWitnessTestAccess::reader_unlock(witness);
  EXPECT_FALSE(evaluation.allowed);
  EXPECT_FALSE(evaluation.snapshot);
  EXPECT_FALSE(evaluation.proof);
  EXPECT_EQ(evaluation.record.evaluation_id, 97u);
  EXPECT_EQ(static_cast<uint8_t>(evaluation.record.wrapper_reason), 8);
  EXPECT_EQ(active_calls, 2);
  EXPECT_EQ(goal_calls, 2);
  EXPECT_NO_THROW(encode_stop_proof_record(evaluation.record));
  witness.reset();
  EXPECT_EQ(evaluation.record.flags, 0);
  EXPECT_EQ(evaluation.record.evaluated_ns, 0);
  EXPECT_EQ(evaluation.record.cumulative_observation_lock_losses, 0u);
}


namespace so101_mujoco_support
{
struct BrokerOwnedTrajectoryControllerTestAccess
{
  static ControllerStopWitness & prepare(BrokerOwnedTrajectoryController & controller)
  {
    controller.witness_active_.store(true);
    controller.monitored_joints_.store(1);
    controller.reservation_role_ = ControllerReservationRole::NECK;
    controller.head_simulation_mode_ = true;
    controller.rt_is_holding_.store(true);
    return controller.neck_stop_witness_;
  }
  static bool unavailable_pending_without_snapshot(BrokerOwnedTrajectoryController & controller)
  {
    const auto & pending = controller.pending_stop_failure_;
    return pending && pending->owner == &controller && !pending->snapshot &&
      pending->wrapper_reason == BrokerOwnedTrajectoryController::StopFailureReason::SNAPSHOT_UNAVAILABLE;
  }
  static void emit(BrokerOwnedTrajectoryController & controller)
  {
    controller.emit_stop_refusal_diagnostic();
  }
};
}

TEST(BrokerOwnedTrajectoryController, UnavailableRefusalLogDoesNotRereadWitness)
{
  using namespace so101_mujoco_support;
  rclcpp::init(0, nullptr);
  InspectableController controller;
  rclcpp::NodeOptions options;
  options.parameter_overrides({
    rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
    rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
    rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"})});
  ASSERT_EQ(controller.init("neck_controller", neck_urdf(), 500, "", options),
    controller_interface::return_type::OK);
  auto & witness = BrokerOwnedTrajectoryControllerTestAccess::prepare(controller);
  fill_wrapper_window(witness);
  std::promise<void> locked, release;
  auto released = release.get_future();
  auto pin = std::async(std::launch::async, [&]() {
      ControllerStopWitnessTestAccess::reader_lock(witness);
      locked.set_value();
      released.wait();
      ControllerStopWitnessTestAccess::reader_unlock(witness);
    });
  locked.get_future().wait();
  const auto evaluation = controller.stop_evaluation();
  release.set_value();
  pin.get();
  EXPECT_FALSE(evaluation.allowed);
  EXPECT_EQ(evaluation.record.wrapper_reason, StopWrapperReason::SNAPSHOT_UNAVAILABLE);
  EXPECT_TRUE(BrokerOwnedTrajectoryControllerTestAccess::unavailable_pending_without_snapshot(controller));
  witness.reset();
  fill_wrapper_window(witness);
  ASSERT_TRUE(witness.proof());
  // The post-reply sink must emit the captured refusal even after recovery.
  EXPECT_TRUE(BrokerOwnedTrajectoryControllerTestAccess::unavailable_pending_without_snapshot(controller));
  BrokerOwnedTrajectoryControllerTestAccess::emit(controller);
  EXPECT_FALSE(BrokerOwnedTrajectoryControllerTestAccess::unavailable_pending_without_snapshot(controller));
  rclcpp::shutdown();
}
