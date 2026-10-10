#include <gtest/gtest.h>

#include <poll.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#include <array>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <future>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include "so101_mujoco_support/controller_reservation_socket.hpp"
#include "so101_mujoco_support/controller_ingress_witness.hpp"
#include "so101_mujoco_support/controller_reservation_role.hpp"

namespace
{
using so101_mujoco_support::ControllerGoalAdmission;
using so101_mujoco_support::ControllerIngressWitness;
using so101_mujoco_support::ControllerReservationCapability;
using so101_mujoco_support::ControllerReservationRole;
using so101_mujoco_support::ControllerReservationService;
using so101_mujoco_support::ControllerReservationSocket;

std::string read_line(int fd)
{
  std::string line;
  while (true) {
    pollfd handle{fd, POLLIN, 0};
    if (poll(&handle, 1, 5000) <= 0) {
      throw std::runtime_error("CLIENT_RESPONSE_TIMEOUT");
    }
    char character;
    if (read(fd, &character, 1) != 1) {
      throw std::runtime_error("CLIENT_RESPONSE_CLOSED");
    }
    if (character == '\n') {return line;}
    line.push_back(character);
  }
}

class ClientProcess
{
public:
  ClientProcess(
    const std::filesystem::path & path, const ControllerReservationCapability & key,
    const std::filesystem::path & second_path = {},
    const ControllerReservationCapability & second_key = {})
  {
    constexpr char digits[] = "0123456789abcdef";
    const auto encode_key = [&digits](const ControllerReservationCapability & value) {
        std::string hex;
        for (const auto byte : value) {
          hex += digits[byte >> 4];
          hex += digits[byte & 15];
        }
        return hex;
      };
    int to_child[2];
    int from_child[2];
    if (pipe(to_child) || pipe(from_child)) {throw std::runtime_error("PIPE_FAILED");}
    pid_ = fork();
    if (pid_ < 0) {throw std::runtime_error("FORK_FAILED");}
    if (pid_ == 0) {
      dup2(to_child[0], STDIN_FILENO);
      dup2(from_child[1], STDOUT_FILENO);
      close(to_child[0]);
      close(to_child[1]);
      close(from_child[0]);
      close(from_child[1]);
      const auto * configured_script = std::getenv("SO101_CONTROLLER_RESERVATION_CLIENT");
      const auto script = configured_script ? std::filesystem::path(configured_script) :
        std::filesystem::path(__FILE__).parent_path() / "controller_reservation_client.py";
      if (second_path.empty()) {
        execl("/usr/bin/python3", "python3", script.c_str(), path.c_str(),
          static_cast<char *>(nullptr));
      } else {
        execl("/usr/bin/python3", "python3", script.c_str(), path.c_str(),
          second_path.c_str(), static_cast<char *>(nullptr));
      }
      _exit(127);
    }
    close(to_child[0]);
    close(from_child[1]);
    input_ = to_child[1];
    output_ = from_child[0];
    const auto key_lines = encode_key(key) + "\n" +
      (second_path.empty() ? "" : encode_key(second_key) + "\n");
    if (write(input_, key_lines.data(), key_lines.size()) !=
      static_cast<ssize_t>(key_lines.size()))
    {
      throw std::runtime_error("CLIENT_CAPABILITY_DELIVERY_FAILED");
    }
    const auto ready = read_line(output_);
    if (ready.rfind("READY ", 0) != 0) {throw std::runtime_error("CLIENT_NOT_READY");}
    const auto separator = ready.find(' ', 6);
    peer_.uid = getuid();
    peer_.pid = static_cast<pid_t>(std::stol(ready.substr(6, separator - 6)));
    peer_.start_ticks = std::stoull(ready.substr(separator + 1));
  }

  ~ClientProcess()
  {
    if (input_ >= 0) {close(input_);}
    if (output_ >= 0) {close(output_);}
    if (pid_ > 0) {
      int child_status = 0;
      if (waitpid(pid_, &child_status, WNOHANG) == 0) {
        kill(pid_, SIGTERM);
        waitpid(pid_, &child_status, 0);
      }
    }
  }

  ControllerReservationSocket::ExpectedPeer peer() const {return peer_;}
  pid_t pid() const {return pid_;}

  void start(const std::string & mode)
  {
    const auto command = mode + "\n";
    if (write(input_, command.data(), command.size()) != static_cast<ssize_t>(command.size())) {
      throw std::runtime_error("CLIENT_COMMAND_FAILED");
    }
  }

  std::string result() {return read_line(output_);}

private:
  pid_t pid_{-1};
  int input_{-1};
  int output_{-1};
  ControllerReservationSocket::ExpectedPeer peer_{};
};

ControllerReservationCapability capability()
{
  ControllerReservationCapability value{};
  value.fill(0xa5);
  return value;
}

std::filesystem::path socket_path(const std::string & name)
{
  const auto scratch_tmp = std::filesystem::path(std::getenv("TMPDIR"));
  const auto * socket_base = std::getenv("SO101_IPC_SOCKET_BASE");
  if (!socket_base) {throw std::runtime_error("TEST_IPC_BASE_REQUIRED");}
  const auto ipc_root = std::filesystem::path(socket_base);
  const auto scratch_name = scratch_tmp.parent_path().filename().string();
  const auto parent = ipc_root / scratch_name.substr(scratch_name.size() - 8);
  if (!std::filesystem::exists(ipc_root) && mkdir(ipc_root.c_str(), 0700) != 0) {
    throw std::runtime_error("IPC_ROOT_FAILED");
  }
  if (!std::filesystem::exists(parent) && mkdir(parent.c_str(), 0700) != 0) {
    throw std::runtime_error("IPC_DIRECTORY_FAILED");
  }
  return parent / name;
}

ControllerGoalAdmission::Goal goal()
{
  const auto fixture = std::filesystem::path(__FILE__).parent_path() /
    "fixtures/follow_joint_trajectory_goal.cdr.hex";
  std::ifstream input(fixture);
  std::string hex;
  input >> hex;
  std::vector<uint8_t> frame{0, 0, 1, 62, 'S', 'O', 'G', 'R', 1, 1};
  const auto key = capability();
  frame.insert(frame.end(), key.begin(), key.end());
  frame.insert(frame.end(), {0, 0, 0, 0, 0, 0, 0, 5});
  frame.insert(frame.end(), 16, 0x11);
  for (size_t index = 0; index + 1 < hex.size(); index += 2) {
    frame.push_back(static_cast<uint8_t>(std::stoul(hex.substr(index, 2), nullptr, 16)));
  }
  return so101_mujoco_support::parse_controller_reservation_frame(frame, key).goal;
}
}  // namespace

TEST(ControllerReservationSocket, AcknowledgesOnlyStoredCrossProcessReservation)
{
  const auto path = socket_path("valid.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(1000));
  client.start("valid");
  EXPECT_TRUE(server.serve_one());
  EXPECT_EQ(client.result(), "ACK");
  ControllerGoalAdmission::GoalUUID uuid{};
  uuid.fill(0x11);
  EXPECT_EQ(gate->admit(uuid, goal(), 5), ControllerGoalAdmission::Result::ALLOW);
}

TEST(ControllerReservationSocket, BoundModeServiceRejectsALegacyRawReservation)
{
  // A bound-identity service must never ACK the legacy SOGR reservation opcode:
  // the request is refused fail-closed and nothing becomes admissible.
  const auto path = socket_path("bound-legacy.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>(
    [] {return 1000000000LL;}, 2000000000, 1048576, 2048,
    so101_mujoco_support::ServiceControllerIdentity{
    so101_mujoco_support::ControllerReservationRole::ARM, "inc-1", "boot-1"});
  ASSERT_TRUE(gate->has_service_identity());
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(1000));
  client.start("valid");
  EXPECT_FALSE(server.serve_one());                  // no ACK
  EXPECT_EQ(client.result(), "REJECT");
  EXPECT_EQ(gate->generation(), 0u);                 // the gate closed fail-closed
  ControllerGoalAdmission::GoalUUID uuid{};
  uuid.fill(0x11);
  EXPECT_NE(gate->admit(uuid, goal(), 5), ControllerGoalAdmission::Result::ALLOW);
}

TEST(ControllerReservationSocket, NullGateIsRefusedAtConstruction)
{
  const auto path = socket_path("null-gate.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  EXPECT_THROW(
    ControllerReservationSocket(path, nullptr, key, client.peer(),
      std::chrono::milliseconds(1000)),
    std::invalid_argument);
}

TEST(ControllerReservationSocket, ArmRequestWithoutLocalStopProofCannotOpenGeneration)
{
  const auto path = socket_path("arm-no-proof.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(1000));
  client.start("arm_generation");
  EXPECT_FALSE(server.serve_one());
  EXPECT_EQ(client.result(), "REJECT");
  ControllerGoalAdmission::GoalUUID uuid{};
  uuid.fill(0x11);
  EXPECT_EQ(gate->admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, ArmAndCloseRequireFreshProofOnlyForOpening)
{
  const auto path = socket_path("arm-stopped.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  bool stopped = false;
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(1000), [&stopped] {return stopped;});
  client.start("arm_generation");
  EXPECT_FALSE(server.serve_one());
  EXPECT_EQ(client.result(), "REJECT");
  stopped = true;
  client.start("arm_generation");
  EXPECT_TRUE(server.serve_one());
  EXPECT_EQ(client.result(), "ACK");
  stopped = false;
  client.start("close_generation");
  EXPECT_TRUE(server.serve_one());
  EXPECT_EQ(client.result(), "ACK");
  ControllerGoalAdmission::GoalUUID uuid{};
  uuid.fill(0x11);
  EXPECT_EQ(gate->admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, ReservationRechecksLocalStopAfterArm)
{
  const auto path = socket_path("reserve-stopped.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  bool stopped = true;
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(1000), [&stopped] {return stopped;});
  client.start("arm_generation");
  ASSERT_TRUE(server.serve_one());
  ASSERT_EQ(client.result(), "ACK");
  stopped = false;
  client.start("valid");
  EXPECT_FALSE(server.serve_one());
  EXPECT_EQ(client.result(), "REJECT");
  ControllerGoalAdmission::GoalUUID uuid{};
  uuid.fill(0x11);
  EXPECT_EQ(gate->admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, StopProofLostDuringArmCannotProduceAck)
{
  const auto path = socket_path("arm-proof-lost.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  int proof_reads = 0;
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(1000), [&proof_reads] {return ++proof_reads == 1;});
  client.start("arm_generation");
  EXPECT_FALSE(server.serve_one());
  EXPECT_EQ(client.result(), "REJECT");
  EXPECT_EQ(proof_reads, 2);
  ControllerGoalAdmission::GoalUUID uuid{};
  uuid.fill(0x11);
  EXPECT_EQ(gate->admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, SequentialGoalsUseOneAuthenticatedOwnerGeneration)
{
  const auto path = socket_path("sequential.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(1000));
  client.start("valid");
  ASSERT_TRUE(server.serve_one());
  ASSERT_EQ(client.result(), "ACK");
  ControllerGoalAdmission::GoalUUID first_uuid{};
  first_uuid.fill(0x11);
  ASSERT_EQ(gate->admit(first_uuid, goal(), 5), ControllerGoalAdmission::Result::ALLOW);

  client.start("valid_second");
  ASSERT_TRUE(server.serve_one());
  ASSERT_EQ(client.result(), "ACK");
  ControllerGoalAdmission::GoalUUID second_uuid{};
  second_uuid.fill(0x22);
  auto second_goal = goal();
  second_goal.trajectory.points[0].positions[0] = 0.25;
  EXPECT_EQ(gate->admit(second_uuid, second_goal, 5), ControllerGoalAdmission::Result::ALLOW);
}

TEST(ControllerReservationSocket, PythonBrokerOwnsBothRoleArmsBeforePreparedGoalSend)
{
  const auto arm_path = socket_path("broker-arm.sock");
  const auto gripper_path = socket_path("broker-gripper.sock");
  const auto arm_key = capability();
  auto gripper_key = capability();
  gripper_key.fill(0x5a);
  ClientProcess client(arm_path, arm_key, gripper_path, gripper_key);
  auto arm_gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  auto gripper_gate = std::make_shared<ControllerGoalAdmission>([] {
        return 1000000000LL;
    }, 2000000000);
  ControllerReservationService arm_service(arm_path, arm_gate, arm_key, client.peer(),
    std::chrono::milliseconds(50), [] {return true;});
  ControllerReservationService gripper_service(
    gripper_path, gripper_gate, gripper_key, client.peer(),
    std::chrono::milliseconds(50), [] {return true;});

  client.start("broker_transaction");
  ASSERT_EQ(client.result(), "ACK");
  ControllerGoalAdmission::GoalUUID arm_uuid{};
  arm_uuid.fill(0x11);
  ControllerGoalAdmission::GoalUUID gripper_uuid{};
  gripper_uuid.fill(0x22);
  EXPECT_EQ(arm_gate->admit(arm_uuid, goal(), 1), ControllerGoalAdmission::Result::ALLOW);
  EXPECT_EQ(gripper_gate->admit(gripper_uuid, goal(), 1), ControllerGoalAdmission::Result::ALLOW);
  client.start("broker_release");
  ASSERT_EQ(client.result(), "ACK");
  EXPECT_EQ(arm_gate->admit(arm_uuid, goal(), 1), ControllerGoalAdmission::Result::DENY_CLOSED);
  EXPECT_EQ(gripper_gate->admit(gripper_uuid, goal(), 1),
    ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, IdleListenerDoesNotRevokeAnArmedOwnerLease)
{
  const auto path = socket_path("idle-lease.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(500));
  EXPECT_FALSE(server.serve_one());
  client.start("valid");
  ASSERT_TRUE(server.serve_one());
  ASSERT_EQ(client.result(), "ACK");
  ControllerGoalAdmission::GoalUUID id{};
  id.fill(0x11);
  EXPECT_EQ(gate->admit(id, goal(), 5), ControllerGoalAdmission::Result::ALLOW);
}

TEST(ControllerReservationSocket, DeadRegisteredPeerRevokesOwnerLeaseOnIdle)
{
  const auto path = socket_path("dead-peer.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(50));

  ASSERT_EQ(kill(client.pid(), SIGTERM), 0);
  int child_status = 0;
  ASSERT_EQ(waitpid(client.pid(), &child_status, 0), client.pid());
  EXPECT_FALSE(server.serve_one());
  ControllerGoalAdmission::GoalUUID id{};
  id.fill(0x11);
  EXPECT_EQ(gate->admit(id, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, DeadPrimaryFaultPeerPermanentlyRevokesOwnerLease)
{
  const auto path = socket_path("dead-primary-fault-peer.sock");
  const auto key = capability();
  ClientProcess primary(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path, gate, key, primary.peer(),
    std::chrono::milliseconds(50), {}, ControllerReservationRole::NECK, {},
    ControllerReservationSocket::Authority::PRIMARY_FAULT);

  ASSERT_EQ(kill(primary.pid(), SIGTERM), 0);
  int child_status = 0;
  ASSERT_EQ(waitpid(primary.pid(), &child_status, 0), primary.pid());
  EXPECT_FALSE(server.serve_one());
  EXPECT_EQ(gate->generation(), 0u);
  EXPECT_FALSE(gate->arm(6));
}

TEST(ControllerReservationSocket, UnreapedRegisteredPeerRevokesOwnerLeaseOnIdle)
{
  const auto path = socket_path("zombie-peer.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(50));

  ASSERT_EQ(kill(client.pid(), SIGTERM), 0);
  siginfo_t child_info{};
  ASSERT_EQ(waitid(P_PID, client.pid(), &child_info, WEXITED | WNOWAIT), 0);
  ASSERT_EQ(child_info.si_pid, client.pid());
  EXPECT_FALSE(server.serve_one());
  ControllerGoalAdmission::GoalUUID id{};
  id.fill(0x11);
  EXPECT_EQ(gate->admit(id, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, ServiceShutdownClosesGateAndRemovesOwnedSocket)
{
  const auto path = socket_path("service-lifetime.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  auto service = std::make_unique<ControllerReservationService>(
    path, gate, key, client.peer(), std::chrono::milliseconds(500));
  ASSERT_TRUE(gate->arm(5));
  client.start("valid");
  ASSERT_EQ(client.result(), "ACK");
  ASSERT_TRUE(std::filesystem::exists(path));

  service.reset();
  EXPECT_FALSE(std::filesystem::exists(path));
  ControllerGoalAdmission::GoalUUID id{};
  id.fill(0x11);
  EXPECT_EQ(gate->admit(id, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, RejectsWrongPeerBeforeReadingFrame)
{
  const auto key = capability();
  for (const auto & field : {"uid", "pid", "start_ticks"}) {
    const auto path = socket_path(std::string("wrong-") + field + ".sock");
    ClientProcess client(path, key);
    auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
    ASSERT_TRUE(gate->arm(5));
    auto wrong_peer = client.peer();
    if (std::string(field) == "uid") {++wrong_peer.uid;}
    if (std::string(field) == "pid") {++wrong_peer.pid;}
    if (std::string(field) == "start_ticks") {++wrong_peer.start_ticks;}
    ControllerReservationSocket server(path, gate, key, wrong_peer,
      std::chrono::milliseconds(1000));
    client.start("valid");
    EXPECT_FALSE(server.serve_one()) << field;
    EXPECT_EQ(client.result(), "EOF") << field;
    ControllerGoalAdmission::GoalUUID uuid{};
    uuid.fill(0x11);
    EXPECT_EQ(gate->admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED) << field;
  }
}

TEST(ControllerReservationSocket, RejectsBadFrameAndClosesGeneration)
{
  const auto key = capability();
  for (const auto & mode : {"wrong_capability", "truncated", "oversized", "slow_prefix",
      "stale_generation"})
  {
    const auto path = socket_path(std::string(mode) + ".sock");
    ClientProcess client(path, key);
    auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
    ASSERT_TRUE(gate->arm(5));
    ControllerReservationSocket server(path, gate, key, client.peer(),
      std::chrono::milliseconds(100));
    client.start(mode);
    EXPECT_FALSE(server.serve_one()) << mode;
    EXPECT_NE(client.result(), "ACK") << mode;
    ControllerGoalAdmission::GoalUUID uuid{};
    uuid.fill(0x11);
    EXPECT_EQ(gate->admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED) << mode;
  }
}

TEST(ControllerReservationSocket, DuplicateReservationClosesGeneration)
{
  const auto path = socket_path("duplicate.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(1000));
  client.start("valid");
  ASSERT_TRUE(server.serve_one());
  ASSERT_EQ(client.result(), "ACK");
  client.start("valid");
  EXPECT_FALSE(server.serve_one());
  EXPECT_NE(client.result(), "ACK");
  ControllerGoalAdmission::GoalUUID uuid{};
  uuid.fill(0x11);
  EXPECT_EQ(gate->admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, RefusesExistingPath)
{
  const auto path = socket_path("existing.sock");
  ASSERT_TRUE(std::filesystem::create_directory(path));
  auto gate = std::make_shared<ControllerGoalAdmission>();
  const auto key = capability();
  ControllerReservationSocket::ExpectedPeer peer{getuid(), getpid(), 1};
  EXPECT_THROW(
    ControllerReservationSocket(path, gate, key, peer, std::chrono::milliseconds(100)),
    std::runtime_error);
}

TEST(ControllerReservationSocket, CapabilityNeverAppearsInClientCommandLine)
{
  const auto path = socket_path("argv-secret.sock");
  ClientProcess client(path, capability());
  std::ifstream command_line("/proc/" + std::to_string(client.pid()) + "/cmdline",
    std::ios::binary);
  const std::string arguments(
    (std::istreambuf_iterator<char>(command_line)), std::istreambuf_iterator<char>());
  EXPECT_EQ(arguments.find("a5a5a5a5a5a5a5a5"), std::string::npos);
}

TEST(ControllerReservationSocket, RefusesSymlinkInSocketPath)
{
  const auto parent = socket_path("unused.sock").parent_path();
  const auto real = parent / "real";
  const auto nested = real / "nested";
  ASSERT_TRUE(std::filesystem::create_directories(nested));
  ASSERT_EQ(chmod(nested.c_str(), 0700), 0);
  const auto alias = parent / "alias";
  std::filesystem::create_directory_symlink(real, alias);
  auto gate = std::make_shared<ControllerGoalAdmission>();
  const auto key = capability();
  ControllerReservationSocket::ExpectedPeer peer{getuid(), getpid(), 1};
  EXPECT_THROW(
    ControllerReservationSocket(alias / "nested" / "goal.sock", gate, key, peer,
      std::chrono::milliseconds(100)),
    std::runtime_error);
}

TEST(ControllerReservationSocket, AuthenticatedCloseRevokesAnAcknowledgedReservation)
{
  const auto path = socket_path("close.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(1000));
  client.start("valid");
  ASSERT_TRUE(server.serve_one());
  ASSERT_EQ(client.result(), "ACK");
  client.start("close_generation");
  EXPECT_TRUE(server.serve_one());
  EXPECT_EQ(client.result(), "ACK");
  ControllerGoalAdmission::GoalUUID uuid{};
  uuid.fill(0x11);
  EXPECT_EQ(gate->admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, StaleCloseCannotRevokeANewerGeneration)
{
  const auto path = socket_path("stale-close.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(6));
  ControllerGoalAdmission::GoalUUID uuid{};
  uuid.fill(0x11);
  ASSERT_TRUE(gate->reserve(uuid, goal(), 6));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(100));
  client.start("close_stale");
  EXPECT_FALSE(server.serve_one());
  EXPECT_EQ(client.result(), "REJECT");
  EXPECT_EQ(gate->admit(uuid, goal(), 6), ControllerGoalAdmission::Result::ALLOW);
}

TEST(ControllerReservationSocket, MonitorCloseIrreversiblyRevokesTheIncarnation)
{
  const auto path = socket_path("fault-close.sock");
  const auto key = capability();
  ClientProcess monitor(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerGoalAdmission::GoalUUID uuid{};
  uuid.fill(0x11);
  ASSERT_TRUE(gate->reserve(uuid, goal(), 5));
  {
    ControllerReservationSocket server(path, gate, key, monitor.peer(),
      std::chrono::milliseconds(100), {}, ControllerReservationRole::NECK, {},
      ControllerReservationSocket::Authority::REVOKER);
    monitor.start("close_generation");
    ASSERT_TRUE(server.serve_one());
    ASSERT_EQ(monitor.result(), "ACK");
  }
  EXPECT_EQ(gate->admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
  EXPECT_FALSE(gate->arm(6));
  gate->close();
  EXPECT_FALSE(gate->arm(7));
}

TEST(ControllerReservationSocket, MonitorCannotArmReserveOrReadIngress)
{
  for (const auto mode : {"arm_next", "raw_valid", "ingress_neck"}) {
    const auto path = socket_path(std::string("revoker-") + mode + ".sock");
    const auto key = capability();
    ClientProcess monitor(path, key);
    auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
    ASSERT_TRUE(gate->arm(5));
    ControllerReservationSocket server(path, gate, key, monitor.peer(),
      std::chrono::milliseconds(100), [] {return true;}, ControllerReservationRole::NECK,
      [] {return std::optional{ControllerIngressWitness::Snapshot{7, 123, 140}};},
      ControllerReservationSocket::Authority::REVOKER);
    monitor.start(mode);
    EXPECT_FALSE(server.serve_one()) << mode;
    EXPECT_NE(monitor.result(), "ACK") << mode;
    EXPECT_FALSE(gate->arm(6)) << mode;
  }
}

TEST(ControllerReservationSocket, NormalPrimaryCloseStillAllowsANewerGeneration)
{
  const auto path = socket_path("normal-rearm.sock");
  const auto key = capability();
  ClientProcess primary(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path, gate, key, primary.peer(),
    std::chrono::milliseconds(100));
  primary.start("close_generation");
  ASSERT_TRUE(server.serve_one());
  ASSERT_EQ(primary.result(), "ACK");
  EXPECT_TRUE(gate->arm(6));
}

TEST(ControllerReservationSocket, MonitorIdentityIsUnavailableUntilPrimaryArm)
{
  const auto path = socket_path("revoker-identity.sock");
  ClientProcess monitor(path, capability());
  auto gate = std::make_shared<ControllerGoalAdmission>(
    [] {return 1000000000LL;}, 2000000000, 1048576, 2048,
    so101_mujoco_support::ServiceControllerIdentity{ControllerReservationRole::NECK, "inc",
      "boot"});
  ControllerReservationSocket server(path, gate, capability(), monitor.peer(),
    std::chrono::milliseconds(100), {}, ControllerReservationRole::NECK, {},
    ControllerReservationSocket::Authority::REVOKER);
  monitor.start("identity_neck");
  EXPECT_FALSE(server.serve_one());
  EXPECT_EQ(monitor.result(), "REJECT");
  ASSERT_TRUE(gate->arm(5));
  monitor.start("identity_neck");
  EXPECT_TRUE(server.serve_one());
  EXPECT_EQ(monitor.result(), "IDENTITY 5");
  EXPECT_EQ(gate->generation(), 5u);
}

TEST(ControllerReservationSocket, MonitorStaleCloseCannotRevokeAnotherGeneration)
{
  const auto path = socket_path("revoker-stale.sock");
  ClientProcess monitor(path, capability());
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(6));
  ControllerReservationSocket server(path, gate, capability(), monitor.peer(),
    std::chrono::milliseconds(100), {}, ControllerReservationRole::NECK, {},
    ControllerReservationSocket::Authority::REVOKER);
  monitor.start("close_stale");
  EXPECT_FALSE(server.serve_one());
  EXPECT_EQ(monitor.result(), "REJECT");
  EXPECT_EQ(gate->generation(), 6u);
  EXPECT_TRUE(gate->arm(7));
}

TEST(ControllerReservationSocket, RevokerInvalidCredentialRoleOrReusedPidLatchesFault)
{
  for (const auto mode : {"close_wrong_capability", "identity_wrong_role", "reused_pid"}) {
    const auto path = socket_path(std::string(mode) + ".sock");
    ClientProcess monitor(path, capability());
    auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
    ASSERT_TRUE(gate->arm(5));
    auto peer = monitor.peer();
    if (std::string(mode) == "reused_pid") {++peer.start_ticks;}
    ControllerReservationSocket server(path, gate, capability(), peer,
      std::chrono::milliseconds(100), {}, ControllerReservationRole::NECK, {},
      ControllerReservationSocket::Authority::REVOKER);
    monitor.start(std::string(mode) == "reused_pid" ? "close_generation" : mode);
    EXPECT_FALSE(server.serve_one()) << mode;
    EXPECT_NE(monitor.result(), "ACK") << mode;
    EXPECT_FALSE(gate->arm(6)) << mode;
  }
}

TEST(ControllerReservationSocket, MonitorCannotUseThePrimaryEndpointEvenWithItsCapability)
{
  const auto path = socket_path("primary-exact-peer.sock");
  ClientProcess primary(path, capability());
  ClientProcess monitor(path, capability());
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path, gate, capability(), primary.peer(),
    std::chrono::milliseconds(100));
  monitor.start("close_generation");
  EXPECT_FALSE(server.serve_one());
  EXPECT_NE(monitor.result(), "ACK");
  // Wrong-primary-peer refusal keeps the legacy closure semantics.
  EXPECT_TRUE(gate->arm(6));
}

TEST(ControllerReservationSocket, ForeignPeerCannotUseTheRevokerEndpoint)
{
  const auto path = socket_path("revoker-exact-peer.sock");
  ClientProcess monitor(path, capability());
  ClientProcess foreign(path, capability());
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path, gate, capability(), monitor.peer(),
    std::chrono::milliseconds(100), {}, ControllerReservationRole::NECK, {},
    ControllerReservationSocket::Authority::REVOKER);
  foreign.start("close_generation");
  EXPECT_FALSE(server.serve_one());
  EXPECT_NE(foreign.result(), "ACK");
  EXPECT_FALSE(gate->arm(6));
}

TEST(ControllerReservationSocket, LostMonitorAckNeverReopensTheNativeGate)
{
  const auto path = socket_path("revoker-lost-ack.sock");
  ClientProcess monitor(path, capability());
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path, gate, capability(), monitor.peer(),
    std::chrono::milliseconds(100), {}, ControllerReservationRole::NECK, {},
    ControllerReservationSocket::Authority::REVOKER);
  monitor.start("close_drop_reply");
  EXPECT_FALSE(server.serve_one());
  EXPECT_EQ(monitor.result(), "CLOSE_SENT_WITHOUT_ACK");
  EXPECT_EQ(gate->generation(), 0u);
  EXPECT_FALSE(gate->arm(6));
}

TEST(ControllerReservationSocket, RevokerListenerDoesNotWaitForAnIncompletePrimaryFrame)
{
  const auto primary_path = socket_path("blocked-primary.sock");
  const auto revoke_path = socket_path("independent-revoke.sock");
  auto revoke_key = capability();
  revoke_key.fill(0x5a);
  ClientProcess primary(primary_path, capability());
  ClientProcess monitor(revoke_path, revoke_key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationService main_service(primary_path, gate, capability(), primary.peer(),
    std::chrono::milliseconds(50));
  ControllerReservationService revoke_service(revoke_path, gate, revoke_key, monitor.peer(),
    std::chrono::milliseconds(2), {}, ControllerReservationRole::NECK, {},
    ControllerReservationSocket::Authority::REVOKER);
  primary.start("hold_prefix");
  ASSERT_EQ(primary.result().rfind("PARTIAL ", 0), 0u);
  const auto accept_deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(10);
  while (!main_service.connection_in_progress() &&
    std::chrono::steady_clock::now() < accept_deadline)
  {
    std::this_thread::sleep_for(std::chrono::microseconds(100));
  }
  ASSERT_TRUE(main_service.connection_in_progress());
  RecordProperty("native_primary_processing_observed", "true");
  const auto started = std::chrono::steady_clock::now();
  monitor.start("close_generation");
  ASSERT_EQ(monitor.result(), "ACK");
  const auto elapsed = std::chrono::steady_clock::now() - started;
  EXPECT_LT(elapsed, std::chrono::milliseconds(10));
  RecordProperty("close_elapsed_ns",
    std::chrono::duration_cast<std::chrono::nanoseconds>(elapsed).count());
  EXPECT_EQ(gate->generation(), 0u);
  EXPECT_FALSE(gate->arm(6));
  EXPECT_NE(primary.result(), "ACK");
}

TEST(ControllerReservationSocket, PrimaryFaultCloseLatchesAndRepeatsIdempotently)
{
  const auto path = socket_path("primary-fault-close.sock");
  ClientProcess primary(path, capability());
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path, gate, capability(), primary.peer(),
    std::chrono::milliseconds(2), {}, ControllerReservationRole::NECK, {},
    ControllerReservationSocket::Authority::PRIMARY_FAULT);
  for (int repeat = 0; repeat < 2; ++repeat) {
    primary.start("close_generation");
    EXPECT_TRUE(server.serve_one());
    EXPECT_EQ(primary.result(), "ACK");
    EXPECT_FALSE(gate->arm(6));
  }
}

TEST(ControllerReservationSocket, PrimaryFaultZeroAndStaleCloseRejectWithoutAnotherLatch)
{
  for (const auto * mode : {"close_zero", "close_stale"}) {
    const auto path = socket_path(std::string("primary-fault-") + mode + ".sock");
    ClientProcess primary(path, capability());
    auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
    ASSERT_TRUE(gate->arm(6));
    ControllerReservationSocket server(path, gate, capability(), primary.peer(),
      std::chrono::milliseconds(2), {}, ControllerReservationRole::NECK, {},
      ControllerReservationSocket::Authority::PRIMARY_FAULT);
    primary.start(mode);
    EXPECT_FALSE(server.serve_one());
    EXPECT_EQ(primary.result(), "REJECT") << mode;
    EXPECT_EQ(gate->generation(), 6u) << mode;
    EXPECT_TRUE(gate->arm(7)) << mode;
  }
}

TEST(ControllerReservationSocket, PrimaryFaultCannotArmReserveOrAuthorizeIngress)
{
  for (const auto * mode : {"arm_next", "raw_reserve", "ingress_neck"}) {
    const auto path = socket_path(std::string("primary-fault-") + mode + ".sock");
    ClientProcess primary(path, capability());
    auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
    ASSERT_TRUE(gate->arm(5));
    ControllerReservationSocket server(path, gate, capability(), primary.peer(),
      std::chrono::milliseconds(2), [] {return true;}, ControllerReservationRole::NECK, {},
      ControllerReservationSocket::Authority::PRIMARY_FAULT);
    primary.start(std::string("sent_") + mode);
    ASSERT_EQ(primary.result(), "REQUEST_SENT");
    EXPECT_FALSE(server.serve_one()) << mode;
    EXPECT_NE(primary.result(), "ACK") << mode;
    EXPECT_FALSE(gate->arm(7)) << mode;
  }
}

TEST(ControllerReservationSocket, PrimaryFaultWorkerBypassesItsOwnIncompleteMainConnection)
{
  const auto main_path = socket_path("own-main-held.sock");
  const auto fault_path = socket_path("own-primary-fault.sock");
  auto fault_key = capability();
  fault_key.fill(0x5a);
  ClientProcess primary(fault_path, fault_key, main_path, capability());
  ClientProcess live_monitor(socket_path("unused-live-monitor.sock"), capability());
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationService main_service(main_path, gate, capability(), primary.peer(),
    std::chrono::milliseconds(50));
  ControllerReservationService fault_service(fault_path, gate, fault_key, primary.peer(),
    std::chrono::milliseconds(2), {}, ControllerReservationRole::NECK, {},
    ControllerReservationSocket::Authority::PRIMARY_FAULT);
  primary.start("hold_other");
  ASSERT_EQ(primary.result(), "PARTIAL");
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(10);
  while (!main_service.connection_in_progress() && std::chrono::steady_clock::now() < deadline) {
    std::this_thread::sleep_for(std::chrono::microseconds(100));
  }
  ASSERT_TRUE(main_service.connection_in_progress());
  ASSERT_EQ(kill(live_monitor.pid(), 0), 0);
  RecordProperty("native_primary_processing_observed", "true");
  RecordProperty("unresponsive_monitor_still_alive", "true");
  const auto started = std::chrono::steady_clock::now();
  primary.start("close_generation");
  ASSERT_EQ(primary.result(), "ACK");
  const auto elapsed = std::chrono::steady_clock::now() - started;
  RecordProperty("close_elapsed_ns",
    std::chrono::duration_cast<std::chrono::nanoseconds>(elapsed).count());
  EXPECT_LT(elapsed, std::chrono::milliseconds(10));
  EXPECT_FALSE(gate->arm(6));
}

TEST(ControllerReservationSocket, PrimaryFaultRejectsForeignPeerAndWrongCapabilityWithLatch)
{
  for (const auto * damage : {"peer", "capability"}) {
    const auto path = socket_path(std::string("primary-fault-invalid-") + damage + ".sock");
    ClientProcess primary(path, capability());
    ClientProcess foreign(path, capability());
    auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
    ASSERT_TRUE(gate->arm(5));
    ControllerReservationSocket server(path, gate, capability(), primary.peer(),
      std::chrono::milliseconds(2), {}, ControllerReservationRole::NECK, {},
      ControllerReservationSocket::Authority::PRIMARY_FAULT);
    auto & actor = std::string(damage) == "peer" ? foreign : primary;
    actor.start(std::string(damage) == "peer" ? "sent_close_generation" :
      "sent_close_wrong_capability");
    ASSERT_EQ(actor.result(), "REQUEST_SENT");
    EXPECT_FALSE(server.serve_one());
    EXPECT_NE(actor.result(), "ACK");
    EXPECT_FALSE(gate->arm(6));
  }
}

TEST(ControllerReservationSocket, AuthenticatedIngressSnapshotDoesNotMutateArmedGeneration)
{
  const auto path = socket_path("ingress-query.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate->arm(5));
  ControllerIngressWitness witness;
  for (int index = 0; index != 7; ++index) {
    auto ingress = witness.enter();
  }
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(1000), [] {return true;},
    ControllerReservationRole::ARM, [&witness] {return witness.snapshot();});
  client.start("ingress_snapshot");
  EXPECT_TRUE(server.serve_one());
  EXPECT_EQ(client.result().rfind("SNAPSHOT 5 1 7 ", 0), 0u);
  ControllerGoalAdmission::GoalUUID id{};
  id.fill(0x11);
  ASSERT_TRUE(gate->reserve(id, goal(), 5));
  EXPECT_EQ(gate->admit(id, goal(), 5), ControllerGoalAdmission::Result::ALLOW);
}

TEST(ControllerReservationSocket, WrongRoleAndStaleGenerationCannotReadIngress)
{
  const auto key = capability();
  for (const auto mode : {"ingress_wrong_role", "ingress_stale_generation"}) {
    const auto path = socket_path(std::string(mode) + ".sock");
    ClientProcess client(path, key);
    auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
    ASSERT_TRUE(gate->arm(5));
    ControllerReservationSocket server(path, gate, key, client.peer(),
      std::chrono::milliseconds(1000), [] {return true;},
      ControllerReservationRole::ARM, [] {
        return std::optional{ControllerIngressWitness::Snapshot{7, 123, 140}};
      });
    client.start(mode);
    EXPECT_FALSE(server.serve_one());
    EXPECT_NE(client.result(), "SNAPSHOT 5 1 7 123 140");
  }
}

TEST(ControllerReservationSocket, InFlightCallbackOrMissingStopCannotProduceIngressSnapshot)
{
  const auto key = capability();
  for (const auto mode : {"missing-stop", "in-flight"}) {
    const auto path = socket_path(std::string(mode) + ".sock");
    ClientProcess client(path, key);
    auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
    ASSERT_TRUE(gate->arm(5));
    ControllerIngressWitness witness;
    ControllerReservationSocket server(path, gate, key, client.peer(),
      std::chrono::milliseconds(1000),
      [mode] {return std::string(mode) != "missing-stop";},
      ControllerReservationRole::ARM, [&witness] {return witness.snapshot();});
    if (std::string(mode) == "in-flight") {
      auto ingress = witness.enter();
      client.start("ingress_snapshot");
      EXPECT_FALSE(server.serve_one());
      EXPECT_NE(client.result().rfind("SNAPSHOT", 0), 0u);
    } else {
      client.start("ingress_snapshot");
      EXPECT_FALSE(server.serve_one());
      EXPECT_NE(client.result().rfind("SNAPSHOT", 0), 0u);
    }
    ControllerGoalAdmission::GoalUUID id{};
    id.fill(0x11);
    EXPECT_TRUE(gate->reserve(id, goal(), 5));
  }
}

namespace
{
std::unique_ptr<ControllerReservationSocket> diagnostic_socket(
  const std::filesystem::path & path, std::shared_ptr<ControllerGoalAdmission> gate,
  ControllerReservationCapability key, ControllerReservationSocket::ExpectedPeer peer,
  std::function<bool()> proof, std::function<void()> sink)
{
  return std::make_unique<ControllerReservationSocket>(path, std::move(gate), key, peer,
    std::chrono::milliseconds(1000), std::move(proof), ControllerReservationRole::ARM,
    ControllerReservationSocket::IngressSnapshot{}, ControllerReservationSocket::Authority::PRIMARY,
    std::move(sink));
}
}

TEST(ControllerReservationSocket, StopRefusalClosesAndRepliesBeforeBlockingDiagnostics)
{
  for (const bool fail_after : {false, true}) {
    const auto path = socket_path(fail_after ? "diag-after.sock" : "diag-before.sock");
    const auto key = capability();
    ClientProcess client(path, key);
    auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
    ASSERT_TRUE(gate->arm(1));
    int reads = 0;
    std::promise<void> sink_entered;
    auto entered = sink_entered.get_future();
    std::promise<void> release_sink;
    auto release = release_sink.get_future().share();
    auto server = diagnostic_socket(path, gate, key, client.peer(),
        [&reads, fail_after] {return fail_after && ++reads == 1;},
        [&sink_entered, release] {
          sink_entered.set_value();
          release.wait();
      });
    client.start("arm_generation");
    auto serving = std::async(std::launch::async, [&server] {return server->serve_one();});
    EXPECT_EQ(entered.wait_for(std::chrono::seconds(2)), std::future_status::ready);
    auto result = std::async(std::launch::async, [&client] {return client.result();});
    auto closed = std::async(std::launch::async, [&gate] {return gate->generation();});
    const auto closed_status = closed.wait_for(std::chrono::milliseconds(500));
    const auto reply_status = result.wait_for(std::chrono::milliseconds(500));
    EXPECT_EQ(closed_status, std::future_status::ready);
    if (closed_status == std::future_status::ready) {EXPECT_EQ(closed.get(), 0u);}
    EXPECT_EQ(reply_status, std::future_status::ready);
    EXPECT_EQ(serving.wait_for(std::chrono::milliseconds(0)), std::future_status::timeout);
    release_sink.set_value();
    EXPECT_FALSE(serving.get());
    EXPECT_EQ(result.get(), "REJECT");
    EXPECT_EQ(gate->generation(), 0u);
  }
}

TEST(ControllerReservationSocket, ThrowingStopDiagnosticsCannotChangeFailClosedReply)
{
  for (const bool fail_after : {false, true}) {
    const auto path = socket_path(fail_after ? "diag-throw-after.sock" : "diag-throw-before.sock");
    const auto key = capability();
    ClientProcess client(path, key);
    auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
    ASSERT_TRUE(gate->arm(1));
    int reads = 0;
    int diagnostics = 0;
    auto server = diagnostic_socket(path, gate, key, client.peer(),
        [&reads, fail_after] {return fail_after && ++reads == 1;},
        [&diagnostics] {
          ++diagnostics;
          throw std::runtime_error("DIAGNOSTIC_SINK_FAILED");
      });
    client.start("arm_generation");
    EXPECT_FALSE(server->serve_one());
    EXPECT_EQ(client.result(), "REJECT");
    EXPECT_EQ(diagnostics, 1);
    EXPECT_EQ(gate->generation(), 0u);
  }
}

TEST(ControllerReservationSocket, SuccessfulStopProofDoesNotInvokeDiagnostics)
{
  const auto path = socket_path("diag-quiet.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  auto gate = std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;}, 2000000000);
  int diagnostics = 0;
  auto server = diagnostic_socket(path, gate, key, client.peer(), [] {return true;},
      [&diagnostics] {++diagnostics;});
  client.start("arm_generation");
  EXPECT_TRUE(server->serve_one());
  EXPECT_EQ(client.result(), "ACK");
  EXPECT_EQ(diagnostics, 0);
}

namespace
{
using namespace so101_mujoco_support;
std::vector<uint8_t> startup_body(const std::string & line)
{
  if(line.rfind("WIRE ",0)!=0) {throw std::runtime_error("STARTUP_RESPONSE_MISSING: "+line);}
  const auto hex=line.substr(5); std::vector<uint8_t> body;
  for(size_t i=0;i+1<hex.size();i+=2) {body.push_back(std::stoul(hex.substr(i,2),nullptr,16));}
  return body;
}
void fill_socket_window(ControllerStopWitness & witness)
{
  const auto now=std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
  for(uint64_t seq=1;seq<=51;++seq) {
    ControllerStopWitness::Observation sample;
    sample.sequence=seq; sample.sim_time_ns=seq*2000000;
    sample.received_monotonic_ns=now-102000000+seq*2000000;
    sample.joint_count=1; sample.holding=true; witness.observe(sample);
  }
}
std::shared_ptr<ControllerGoalAdmission> startup_gate()
{
  return std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;},2000000000,1048576,2048,
    ServiceControllerIdentity{ControllerReservationRole::NECK,"startup-inc","startup-boot"});
}
}
TEST(ControllerReservationSocket, prearm_ready_and_not_ready_never_open_ingress)
{
  const auto path=socket_path("prearm.sock");
  ClientProcess client(path,capability()); auto gate=startup_gate();
  ControllerStopWitness witness(1); uint64_t calls=0;
  ControllerReservationSocket server(path,gate,capability(),client.peer(),std::chrono::milliseconds(1000),
    [&] {return evaluate_controller_stop(++calls,[] {return true;},[&] {return &witness;},[] {return false;});},
    ControllerReservationRole::NECK);
  client.start("prearm_status"); server.serve_one();
  const auto not_ready=parse_prearm_reply(startup_body(client.result()));
  EXPECT_EQ(not_ready.status,PrearmStatus::NOT_READY); EXPECT_EQ(not_ready.proof.evaluation_id,1u);
  EXPECT_EQ(not_ready.proof.witness_rejection,2); EXPECT_EQ(gate->generation(),0u);
  fill_socket_window(witness);
  client.start("prearm_status"); server.serve_one();
  const auto ready=parse_prearm_reply(startup_body(client.result()));
  EXPECT_EQ(ready.status,PrearmStatus::READY); EXPECT_EQ(ready.proof.evaluation_id,2u);
  EXPECT_EQ(gate->generation(),0u); EXPECT_FALSE(gate->service_identity());
  EXPECT_EQ(gate->admit({},goal(),5),ControllerGoalAdmission::Result::DENY_CLOSED);
  EXPECT_EQ(calls,2u);
}
TEST(ControllerReservationSocket, proof_ready_invalidated_before_arm_rejects_before)
{
  const auto path=socket_path("prearm-race.sock");
  ClientProcess client(path,capability()); auto gate=startup_gate();
  ControllerStopWitness witness(1); fill_socket_window(witness); uint64_t calls=0;
  ControllerReservationSocket server(path,gate,capability(),client.peer(),std::chrono::milliseconds(1000),
    [&] {return evaluate_controller_stop(++calls,[] {return true;},[&] {return &witness;},[] {return false;});},
    ControllerReservationRole::NECK);
  client.start("prearm_status"); server.serve_one();
  EXPECT_EQ(parse_prearm_reply(startup_body(client.result())).status,PrearmStatus::READY);
  witness.invalidate_nonblocking();
  client.start("diagnostic_arm"); EXPECT_FALSE(server.serve_one());
  const auto refused=parse_diagnostic_arm_reply(startup_body(client.result()));
  EXPECT_EQ(refused.phase,ArmPhase::STOP_BEFORE); EXPECT_EQ(refused.proof.evaluation_id,2u);
  EXPECT_EQ(refused.proof.witness_rejection,1); EXPECT_EQ(calls,2u);
  EXPECT_EQ(gate->prearm_scope(5).stored_generation,0u);
}
TEST(ControllerReservationSocket, arm_after_failure_keeps_matching_stored_generation)
{
  const auto path=socket_path("arm-after.sock");
  ClientProcess client(path,capability()); auto gate=startup_gate();
  ControllerStopWitness witness(1); fill_socket_window(witness); uint64_t calls=0;
  ControllerReservationSocket server(path,gate,capability(),client.peer(),std::chrono::milliseconds(1000),
    [&] {++calls; if(calls==2) {witness.invalidate_nonblocking();}
      return evaluate_controller_stop(calls,[] {return true;},[&] {return &witness;},[] {return false;});},
    ControllerReservationRole::NECK);
  client.start("diagnostic_arm"); EXPECT_FALSE(server.serve_one());
  const auto refused=parse_diagnostic_arm_reply(startup_body(client.result()));
  EXPECT_EQ(refused.phase,ArmPhase::STOP_AFTER); EXPECT_EQ(refused.proof.evaluation_id,2u);
  EXPECT_EQ(calls,2u); EXPECT_EQ(gate->generation(),0u);
  EXPECT_EQ(gate->prearm_scope(6).stored_generation,5u);
}
TEST(ControllerReservationSocket, diagnostic_and_legacy_arm_share_before_gate_after_order)
{
  const auto path=socket_path("arm-shared.sock");
  ClientProcess client(path,capability()); auto gate=startup_gate();
  ControllerStopWitness witness(1); fill_socket_window(witness); uint64_t calls=0;
  std::vector<uint64_t> generations;
  ControllerReservationSocket server(path,gate,capability(),client.peer(),std::chrono::milliseconds(1000),
    [&] {generations.push_back(gate->prearm_scope(10).stored_generation);
      return evaluate_controller_stop(++calls,[] {return true;},[&] {return &witness;},[] {return false;});},
    ControllerReservationRole::NECK);
  client.start("diagnostic_arm"); EXPECT_TRUE(server.serve_one());
  const auto ack=parse_diagnostic_arm_reply(startup_body(client.result()));
  EXPECT_EQ(ack.status,ReservationReplyStatus::ACK); EXPECT_EQ(ack.proof.evaluation_id,2u);
  EXPECT_EQ(generations,(std::vector<uint64_t>{0,5}));
  client.start("arm_next"); EXPECT_TRUE(server.serve_one()); EXPECT_EQ(client.result(),"ACK");
  EXPECT_EQ(generations,(std::vector<uint64_t>{0,5,5,6})); EXPECT_EQ(calls,4u);
  client.start("diagnostic_arm"); EXPECT_FALSE(server.serve_one());
  const auto stale=parse_diagnostic_arm_reply(startup_body(client.result()));
  EXPECT_EQ(stale.phase,ArmPhase::GATE_ARM); EXPECT_EQ(stale.gate_reason,GateReason::NONINCREASING_GENERATION);
  EXPECT_EQ(stale.proof.evaluation_id,5u); EXPECT_EQ(calls,5u); EXPECT_EQ(gate->generation(),0u);
}
TEST(ControllerReservationSocket, main_peer_cap_role_and_frame_refuse)
{
  for(const std::string damage: {"prearm_wrong_cap","prearm_bad_reserved","peer","role"}) {
    const auto path=socket_path(damage+".sock"); ClientProcess owner(path,capability()),foreign(path,capability());
    auto gate=startup_gate(); ASSERT_TRUE(gate->arm(5));
    ControllerReservationSocket server(path,gate,capability(),owner.peer(),std::chrono::milliseconds(1000),
      [] {return true;},damage=="role"?ControllerReservationRole::ARM:ControllerReservationRole::NECK);
    auto & client=damage=="peer"?foreign:owner;
    client.start(damage=="peer" || damage=="role"?"prearm_status":damage);
    EXPECT_FALSE(server.serve_one()); EXPECT_EQ(client.result(),"EOF");
    EXPECT_EQ(gate->generation(),0u);
  }
}
TEST(ControllerReservationSocket, blocked_failure_sink_cannot_delay_gate_close_or_reply)
{
  const auto path=socket_path("new-arm-block.sock"); ClientProcess client(path,capability());
  auto gate=startup_gate(); ControllerStopWitness witness(1); fill_socket_window(witness); uint64_t calls=0;
  std::promise<void> entered,release; auto entered_future=entered.get_future();
  auto release_future=release.get_future().share();
  ControllerReservationSocket server(path,gate,capability(),client.peer(),std::chrono::milliseconds(1000),
    [&] {if(++calls==2) {witness.invalidate_nonblocking();}
      return evaluate_controller_stop(calls,[] {return true;},[&] {return &witness;},[] {return false;});},
    ControllerReservationRole::NECK,{},ControllerReservationSocket::Authority::PRIMARY,
    [&] {entered.set_value();release_future.wait();});
  client.start("diagnostic_arm");
  auto serve=std::async(std::launch::async,[&] {return server.serve_one();});
  EXPECT_EQ(entered_future.wait_for(std::chrono::seconds(2)),std::future_status::ready);
  auto reply=std::async(std::launch::async,[&] {return client.result();});
  EXPECT_EQ(reply.wait_for(std::chrono::milliseconds(100)),std::future_status::ready);
  EXPECT_EQ(gate->generation(),0u);
  release.set_value(); EXPECT_FALSE(serve.get());
  const auto decoded=parse_diagnostic_arm_reply(startup_body(reply.get()));
  EXPECT_EQ(decoded.phase,ArmPhase::STOP_AFTER); EXPECT_EQ(decoded.proof.evaluation_id,2u);
}
TEST(ControllerReservationSocket, bootstrap_reads_identity_at_stored_zero)
{
  const auto path=socket_path("bootstrap.sock"); ClientProcess client(path,capability()); auto gate=startup_gate();
  ControllerReservationSocket server(path,gate,capability(),client.peer(),std::chrono::milliseconds(1000),{},
    ControllerReservationRole::NECK,{},ControllerReservationSocket::Authority::PRIMARY_FAULT);
  client.start("bootstrap_query"); EXPECT_TRUE(server.serve_one());
  const auto body=parse_identity_scope_reply(startup_body(client.result()),false);
  EXPECT_EQ(body.status,0); EXPECT_EQ(body.stored_generation,0u);
  EXPECT_EQ(body.generation,5u); EXPECT_EQ(body.identity.incarnation,"startup-inc");
  EXPECT_TRUE(gate->arm(5)); // no latch or gate mutation from bootstrap
}
TEST(ControllerReservationSocket, stale_same_pid_same_cap_rejects_identity_without_mutation)
{
  const auto path=socket_path("recreated-scope.sock"); ClientProcess client(path,capability());
  auto first=startup_gate();
  {
    ControllerReservationSocket server(path,first,capability(),client.peer(),std::chrono::milliseconds(1000),{},
      ControllerReservationRole::NECK,{},ControllerReservationSocket::Authority::PRIMARY_FAULT);
    client.start("bootstrap_query"); server.serve_one();
    EXPECT_EQ(parse_identity_scope_reply(startup_body(client.result()),false).identity.incarnation,"startup-inc");
  }
  auto next=std::make_shared<ControllerGoalAdmission>([] {return 1000000000LL;},2000000000,1048576,2048,
    ServiceControllerIdentity{ControllerReservationRole::NECK,"replacement-inc","replacement-boot"});
  ASSERT_TRUE(next->arm(5));
  ControllerReservationSocket replacement(path,next,capability(),client.peer(),std::chrono::milliseconds(1000),{},
    ControllerReservationRole::NECK,{},ControllerReservationSocket::Authority::PRIMARY_FAULT);
  client.start("scoped_close"); EXPECT_FALSE(replacement.serve_one());
  const auto body=parse_identity_scope_reply(startup_body(client.result()),true);
  EXPECT_EQ(body.status,3); EXPECT_EQ(body.identity.incarnation,"replacement-inc");
  EXPECT_EQ(next->generation(),5u); EXPECT_TRUE(next->arm(6));
}
TEST(ControllerReservationSocket, stale_rotated_cap_valid_sopc_is_nonmutating_without_success_receipt)
{
  const auto path=socket_path("rotated-scope.sock"); ClientProcess client(path,capability());
  auto first=startup_gate();
  {
    ControllerReservationSocket server(path,first,capability(),client.peer(),std::chrono::milliseconds(1000),{},
      ControllerReservationRole::NECK,{},ControllerReservationSocket::Authority::PRIMARY_FAULT);
    client.start("bootstrap_query"); server.serve_one();
    EXPECT_EQ(parse_identity_scope_reply(startup_body(client.result()),false).status,0);
  }
  auto rotated=capability(); rotated[0]^=1;
  auto next=startup_gate(); ASSERT_TRUE(next->arm(5));
  ControllerReservationSocket replacement(path,next,rotated,client.peer(),std::chrono::milliseconds(1000),{},
    ControllerReservationRole::NECK,{},ControllerReservationSocket::Authority::PRIMARY_FAULT);
  client.start("scoped_close"); EXPECT_FALSE(replacement.serve_one()); EXPECT_EQ(client.result(),"EOF");
  EXPECT_EQ(next->generation(),5u); EXPECT_TRUE(next->arm(6));
}
TEST(ControllerReservationSocket, nonmatching_generation_reply_write_failure_does_not_fault_revoke)
{
  const auto path=socket_path("wrong-generation-drop.sock"); ClientProcess client(path,capability());
  auto gate=startup_gate(); ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path,gate,capability(),client.peer(),std::chrono::milliseconds(1000),{},
    ControllerReservationRole::NECK,{},ControllerReservationSocket::Authority::PRIMARY_FAULT);
  client.start("scoped_other_generation_drop_reply");
  EXPECT_FALSE(server.serve_one()); EXPECT_EQ(client.result(),"DROPPED");
  EXPECT_EQ(gate->generation(),5u); EXPECT_TRUE(gate->arm(6));
}
TEST(ControllerReservationSocket, scoped_close_zero_and_matching_generation_receipts)
{
  for(bool armed:{false,true}) {
    const auto path=socket_path(armed?"scoped-armed.sock":"scoped-zero.sock");
    ClientProcess client(path,capability()); auto gate=startup_gate();
    if(armed) {ASSERT_TRUE(gate->arm(5));gate->close();}
    ControllerReservationSocket server(path,gate,capability(),client.peer(),std::chrono::milliseconds(1000),{},
      ControllerReservationRole::NECK,{},ControllerReservationSocket::Authority::PRIMARY_FAULT);
    client.start("scoped_close"); EXPECT_TRUE(server.serve_one());
    const auto reply=parse_identity_scope_reply(startup_body(client.result()),true);
    EXPECT_EQ(reply.status,armed?0:1); EXPECT_EQ(reply.stored_generation,armed?5u:0u);
    EXPECT_FALSE(gate->arm(6));
  }
}
TEST(ControllerReservationSocket, malformed_scoped_role_keeps_old_fault_security_behavior)
{
  const auto path=socket_path("scoped-bad-role.sock"); ClientProcess client(path,capability());auto gate=startup_gate();
  ASSERT_TRUE(gate->arm(5));
  ControllerReservationSocket server(path,gate,capability(),client.peer(),std::chrono::milliseconds(1000),{},
    ControllerReservationRole::NECK,{},ControllerReservationSocket::Authority::PRIMARY_FAULT);
  client.start("scoped_bad_role"); EXPECT_FALSE(server.serve_one());EXPECT_EQ(client.result(),"EOF");
  EXPECT_FALSE(gate->arm(6));
}
