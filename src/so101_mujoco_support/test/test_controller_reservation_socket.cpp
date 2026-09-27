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
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include "so101_mujoco_support/controller_reservation_socket.hpp"

namespace
{
using so101_mujoco_support::ControllerGoalAdmission;
using so101_mujoco_support::ControllerReservationCapability;
using so101_mujoco_support::ControllerReservationService;
using so101_mujoco_support::ControllerReservationSocket;

std::string read_line(int fd)
{
  std::string line;
  while (true) {
    pollfd handle{fd, POLLIN, 0};
    if (poll(&handle, 1, 2000) <= 0) {
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
  ClientProcess(const std::filesystem::path & path, const ControllerReservationCapability & key)
  {
    std::string key_hex;
    constexpr char digits[] = "0123456789abcdef";
    for (const auto byte : key) {
      key_hex += digits[byte >> 4];
      key_hex += digits[byte & 15];
    }
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
      const auto script = std::filesystem::path(__FILE__).parent_path() /
        "controller_reservation_client.py";
      execl("/usr/bin/python3", "python3", script.c_str(), path.c_str(),
        static_cast<char *>(nullptr));
      _exit(127);
    }
    close(to_child[0]);
    close(from_child[1]);
    input_ = to_child[1];
    output_ = from_child[0];
    const auto key_line = key_hex + "\n";
    if (write(input_, key_line.data(), key_line.size()) !=
      static_cast<ssize_t>(key_line.size()))
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
  const auto task_root = scratch_tmp.parent_path().parent_path().parent_path();
  const auto ipc_root = task_root / "ipc";
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
  ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate.arm(5));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(1000));
  client.start("valid");
  EXPECT_TRUE(server.serve_one());
  EXPECT_EQ(client.result(), "ACK");
  ControllerGoalAdmission::GoalUUID uuid{};
  uuid.fill(0x11);
  EXPECT_EQ(gate.admit(uuid, goal(), 5), ControllerGoalAdmission::Result::ALLOW);
}

TEST(ControllerReservationSocket, ArmRequestWithoutLocalStopProofCannotOpenGeneration)
{
  const auto path = socket_path("arm-no-proof.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(1000));
  client.start("arm_generation");
  EXPECT_FALSE(server.serve_one());
  EXPECT_EQ(client.result(), "REJECT");
  ControllerGoalAdmission::GoalUUID uuid{};
  uuid.fill(0x11);
  EXPECT_EQ(gate.admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, ArmAndCloseRequireFreshProofOnlyForOpening)
{
  const auto path = socket_path("arm-stopped.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
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
  EXPECT_EQ(gate.admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, ReservationRechecksLocalStopAfterArm)
{
  const auto path = socket_path("reserve-stopped.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
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
  EXPECT_EQ(gate.admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, StopProofLostDuringArmCannotProduceAck)
{
  const auto path = socket_path("arm-proof-lost.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
  int proof_reads = 0;
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(1000), [&proof_reads] {return ++proof_reads == 1;});
  client.start("arm_generation");
  EXPECT_FALSE(server.serve_one());
  EXPECT_EQ(client.result(), "REJECT");
  EXPECT_EQ(proof_reads, 2);
  ControllerGoalAdmission::GoalUUID uuid{};
  uuid.fill(0x11);
  EXPECT_EQ(gate.admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, SequentialGoalsUseOneAuthenticatedOwnerGeneration)
{
  const auto path = socket_path("sequential.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate.arm(5));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(1000));
  client.start("valid");
  ASSERT_TRUE(server.serve_one());
  ASSERT_EQ(client.result(), "ACK");
  ControllerGoalAdmission::GoalUUID first_uuid{};
  first_uuid.fill(0x11);
  ASSERT_EQ(gate.admit(first_uuid, goal(), 5), ControllerGoalAdmission::Result::ALLOW);

  client.start("valid_second");
  ASSERT_TRUE(server.serve_one());
  ASSERT_EQ(client.result(), "ACK");
  ControllerGoalAdmission::GoalUUID second_uuid{};
  second_uuid.fill(0x22);
  auto second_goal = goal();
  second_goal.trajectory.points[0].positions[0] = 0.25;
  EXPECT_EQ(gate.admit(second_uuid, second_goal, 5), ControllerGoalAdmission::Result::ALLOW);
}

TEST(ControllerReservationSocket, IdleListenerDoesNotRevokeAnArmedOwnerLease)
{
  const auto path = socket_path("idle-lease.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate.arm(5));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(500));
  EXPECT_FALSE(server.serve_one());
  client.start("valid");
  ASSERT_TRUE(server.serve_one());
  ASSERT_EQ(client.result(), "ACK");
  ControllerGoalAdmission::GoalUUID id{};
  id.fill(0x11);
  EXPECT_EQ(gate.admit(id, goal(), 5), ControllerGoalAdmission::Result::ALLOW);
}

TEST(ControllerReservationSocket, DeadRegisteredPeerRevokesOwnerLeaseOnIdle)
{
  const auto path = socket_path("dead-peer.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate.arm(5));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(50));

  ASSERT_EQ(kill(client.pid(), SIGTERM), 0);
  int child_status = 0;
  ASSERT_EQ(waitpid(client.pid(), &child_status, 0), client.pid());
  EXPECT_FALSE(server.serve_one());
  ControllerGoalAdmission::GoalUUID id{};
  id.fill(0x11);
  EXPECT_EQ(gate.admit(id, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, UnreapedRegisteredPeerRevokesOwnerLeaseOnIdle)
{
  const auto path = socket_path("zombie-peer.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate.arm(5));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(50));

  ASSERT_EQ(kill(client.pid(), SIGTERM), 0);
  siginfo_t child_info{};
  ASSERT_EQ(waitid(P_PID, client.pid(), &child_info, WEXITED | WNOWAIT), 0);
  ASSERT_EQ(child_info.si_pid, client.pid());
  EXPECT_FALSE(server.serve_one());
  ControllerGoalAdmission::GoalUUID id{};
  id.fill(0x11);
  EXPECT_EQ(gate.admit(id, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, ServiceShutdownClosesGateAndRemovesOwnedSocket)
{
  const auto path = socket_path("service-lifetime.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
  auto service = std::make_unique<ControllerReservationService>(
    path, gate, key, client.peer(), std::chrono::milliseconds(500));
  ASSERT_TRUE(gate.arm(5));
  client.start("valid");
  ASSERT_EQ(client.result(), "ACK");
  ASSERT_TRUE(std::filesystem::exists(path));

  service.reset();
  EXPECT_FALSE(std::filesystem::exists(path));
  ControllerGoalAdmission::GoalUUID id{};
  id.fill(0x11);
  EXPECT_EQ(gate.admit(id, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, RejectsWrongPeerBeforeReadingFrame)
{
  const auto key = capability();
  for (const auto & field : {"uid", "pid", "start_ticks"}) {
    const auto path = socket_path(std::string("wrong-") + field + ".sock");
    ClientProcess client(path, key);
    ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
    ASSERT_TRUE(gate.arm(5));
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
    EXPECT_EQ(gate.admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED) << field;
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
    ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
    ASSERT_TRUE(gate.arm(5));
    ControllerReservationSocket server(path, gate, key, client.peer(),
      std::chrono::milliseconds(100));
    client.start(mode);
    EXPECT_FALSE(server.serve_one()) << mode;
    EXPECT_NE(client.result(), "ACK") << mode;
    ControllerGoalAdmission::GoalUUID uuid{};
    uuid.fill(0x11);
    EXPECT_EQ(gate.admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED) << mode;
  }
}

TEST(ControllerReservationSocket, DuplicateReservationClosesGeneration)
{
  const auto path = socket_path("duplicate.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate.arm(5));
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
  EXPECT_EQ(gate.admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, RefusesExistingPath)
{
  const auto path = socket_path("existing.sock");
  ASSERT_TRUE(std::filesystem::create_directory(path));
  ControllerGoalAdmission gate;
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
  ControllerGoalAdmission gate;
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
  ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate.arm(5));
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
  EXPECT_EQ(gate.admit(uuid, goal(), 5), ControllerGoalAdmission::Result::DENY_CLOSED);
}

TEST(ControllerReservationSocket, StaleCloseCannotRevokeANewerGeneration)
{
  const auto path = socket_path("stale-close.sock");
  const auto key = capability();
  ClientProcess client(path, key);
  ControllerGoalAdmission gate([] {return 1000000000LL;}, 2000000000);
  ASSERT_TRUE(gate.arm(6));
  ControllerGoalAdmission::GoalUUID uuid{};
  uuid.fill(0x11);
  ASSERT_TRUE(gate.reserve(uuid, goal(), 6));
  ControllerReservationSocket server(path, gate, key, client.peer(),
    std::chrono::milliseconds(100));
  client.start("close_stale");
  EXPECT_FALSE(server.serve_one());
  EXPECT_EQ(client.result(), "REJECT");
  EXPECT_EQ(gate.admit(uuid, goal(), 6), ControllerGoalAdmission::Result::ALLOW);
}
