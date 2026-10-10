#include <gtest/gtest.h>

#include <signal.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#include <array>
#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "so101_mujoco_support/controller_reservation_provision.hpp"

using so101_mujoco_support::read_controller_primary_fault_provision;

namespace
{
using so101_mujoco_support::ControllerReservationRole;
using so101_mujoco_support::read_controller_reservation_provision;
using so101_mujoco_support::read_controller_revocation_provision;

std::filesystem::path private_directory(const char * suffix)
{
  const auto parent = std::filesystem::path(std::getenv("TMPDIR")) /
    ("provision-" + std::to_string(getpid()) + "-" + suffix);
  if (!std::filesystem::create_directory(parent) || chmod(parent.c_str(), 0700) != 0) {
    throw std::runtime_error("PRIVATE_DIRECTORY_FAILED");
  }
  return parent;
}

std::array<uint8_t, 32> read_key(int fd)
{
  std::array<uint8_t, 32> key{};
  size_t received = 0;
  while (received < key.size()) {
    const auto count = read(fd, key.data() + received, key.size() - received);
    if (count <= 0) {throw std::runtime_error("PROVISION_WRITER_CLOSED");}
    received += static_cast<size_t>(count);
  }
  return key;
}

class ProvisionWriter
{
public:
  ProvisionWriter(const std::filesystem::path & path, const char * role, const char * session)
  {
    int to_child[2];
    int from_child[2];
    if (pipe(to_child) != 0 || pipe(from_child) != 0) {
      throw std::runtime_error("PIPE_FAILED");
    }
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
        "controller_reservation_provision_writer.py";
      execl("/usr/bin/python3", "python3", script.c_str(), path.c_str(), role, session,
        static_cast<char *>(nullptr));
      _exit(127);
    }
    close(to_child[0]);
    close(from_child[1]);
    input_ = to_child[1];
    output_ = from_child[0];
    key_ = read_key(output_);
  }

  ~ProvisionWriter()
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

  pid_t pid() const {return pid_;}
  std::array<uint8_t, 32> key() const {return key_;}

  void stop()
  {
    close(input_);
    input_ = -1;
    int child_status = 0;
    if (waitpid(pid_, &child_status, 0) != pid_ || !WIFEXITED(child_status) ||
      WEXITSTATUS(child_status) != 0)
    {
      throw std::runtime_error("PROVISION_WRITER_EXIT_FAILED");
    }
  }

private:
  pid_t pid_{-1};
  int input_{-1};
  int output_{-1};
  std::array<uint8_t, 32> key_{};
};

void write_copy(const std::filesystem::path & path, const std::vector<uint8_t> & bytes)
{
  std::ofstream output(path, std::ios::binary);
  output.write(reinterpret_cast<const char *>(bytes.data()), bytes.size());
  output.close();
  if (chmod(path.c_str(), 0600) != 0) {throw std::runtime_error("COPY_MODE_FAILED");}
}
}  // namespace

TEST(ControllerReservationProvision, ReadsLivePythonWriterWithoutExposingTheCapability)
{
  const auto parent = private_directory("live");
  const auto path = parent / "arm.provision";
  ProvisionWriter writer(path, "arm", "session-17");
  const auto provision = read_controller_reservation_provision(
    path, ControllerReservationRole::ARM, "session-17");
  EXPECT_EQ(provision.peer.uid, geteuid());
  EXPECT_EQ(provision.peer.pid, writer.pid());
  EXPECT_GT(provision.peer.start_ticks, 0u);
  EXPECT_EQ(provision.capability, writer.key());
  writer.stop();
  EXPECT_THROW(read_controller_reservation_provision(
      path, ControllerReservationRole::ARM, "session-17"), std::runtime_error);
}

TEST(ControllerReservationProvision, ReadsNeckOnlyFromItsOwnLiveBrokerProvision)
{
  const auto parent = private_directory("neck-live");
  const auto path = parent / "neck.provision";
  ProvisionWriter writer(path, "neck", "session-17");
  const auto provision = read_controller_reservation_provision(
    path, ControllerReservationRole::NECK, "session-17");
  EXPECT_EQ(provision.peer.pid, writer.pid());
  EXPECT_EQ(provision.capability, writer.key());
  EXPECT_THROW(read_controller_reservation_provision(
      path, ControllerReservationRole::ARM, "session-17"), std::runtime_error);
  EXPECT_THROW(read_controller_reservation_provision(
      path, ControllerReservationRole::GRIPPER, "session-17"), std::runtime_error);
  writer.stop();
  EXPECT_THROW(read_controller_reservation_provision(
      path, ControllerReservationRole::NECK, "session-17"), std::runtime_error);
}

TEST(ControllerReservationProvision, RejectsWrongScopeAndUnsafeFileMetadata)
{
  const auto parent = private_directory("invalid");
  const auto path = parent / "arm.provision";
  ProvisionWriter writer(path, "arm", "session-17");
  EXPECT_THROW(read_controller_reservation_provision(
      path, ControllerReservationRole::GRIPPER, "session-17"), std::runtime_error);
  EXPECT_THROW(read_controller_reservation_provision(
      path, ControllerReservationRole::ARM, "session-18"), std::runtime_error);

  std::ifstream input(path, std::ios::binary);
  const std::vector<uint8_t> original(
    (std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
  ASSERT_GT(original.size(), 56u);
  auto truncated = original;
  truncated.pop_back();
  write_copy(parent / "truncated.provision", truncated);
  EXPECT_THROW(read_controller_reservation_provision(
      parent / "truncated.provision", ControllerReservationRole::ARM, "session-17"),
    std::runtime_error);
  auto extra = original;
  extra.push_back(0);
  write_copy(parent / "extra.provision", extra);
  EXPECT_THROW(read_controller_reservation_provision(
      parent / "extra.provision", ControllerReservationRole::ARM, "session-17"),
    std::runtime_error);
  auto wrong_ticks = original;
  wrong_ticks[23] ^= 1;
  write_copy(parent / "wrong-ticks.provision", wrong_ticks);
  EXPECT_THROW(read_controller_reservation_provision(
      parent / "wrong-ticks.provision", ControllerReservationRole::ARM, "session-17"),
    std::runtime_error);
  auto zero_key = original;
  std::fill(zero_key.begin() + 24, zero_key.begin() + 56, 0);
  write_copy(parent / "zero-key.provision", zero_key);
  EXPECT_THROW(read_controller_reservation_provision(
      parent / "zero-key.provision", ControllerReservationRole::ARM, "session-17"),
    std::runtime_error);
  ASSERT_EQ(chmod(path.c_str(), 0644), 0);
  EXPECT_THROW(read_controller_reservation_provision(
      path, ControllerReservationRole::ARM, "session-17"), std::runtime_error);
  ASSERT_EQ(chmod(path.c_str(), 0600), 0);
  std::filesystem::create_symlink(path, parent / "linked.provision");
  EXPECT_THROW(read_controller_reservation_provision(
      parent / "linked.provision", ControllerReservationRole::ARM, "session-17"),
    std::runtime_error);
  std::filesystem::create_directory_symlink(parent, parent.parent_path() / "alias");
  EXPECT_THROW(read_controller_reservation_provision(
      parent.parent_path() / "alias" / "arm.provision",
      ControllerReservationRole::ARM, "session-17"), std::runtime_error);
  std::filesystem::create_hard_link(path, parent / "hard.provision");
  EXPECT_THROW(read_controller_reservation_provision(
      path, ControllerReservationRole::ARM, "session-17"), std::runtime_error);
}

TEST(ControllerReservationProvision, MonitorProvisionBindsNativeOwnerEndpointAndDistinctLivePeer)
{
  const auto * base = std::getenv("SO101_IPC_SOCKET_BASE");
  ASSERT_NE(base, nullptr);
  const auto parent = std::filesystem::path(base) /
    ("rev-provision-" + std::to_string(getpid()));
  ASSERT_TRUE(std::filesystem::create_directory(parent));
  ASSERT_EQ(chmod(parent.c_str(), 0700), 0);
  const auto original_path = parent / "neck.provision";
  ProvisionWriter monitor(original_path, "neck", "session-17");
  std::ifstream input(original_path, std::ios::binary);
  const std::vector<uint8_t> original(
    (std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
  ASSERT_EQ(original.size(), 66u);
  const auto endpoint = parent / "neck-revoke.sock";
  const auto endpoint_text = endpoint.string();
  ASSERT_LE(endpoint_text.size(), 107u);
  auto bytes = std::vector<uint8_t>(original.begin(), original.begin() + 56);
  bytes[4] = 2;
  bytes[7] = static_cast<uint8_t>(endpoint_text.size());
  const auto append_integer = [&bytes](uint64_t value, int width) {
      for (int shift = (width - 1) * 8; shift >= 0; shift -= 8) {
        bytes.push_back(static_cast<uint8_t>((value >> shift) & 0xff));
      }
    };
  std::ifstream process("/proc/self/stat");
  std::string line;
  ASSERT_TRUE(std::getline(process, line));
  std::istringstream fields(line.substr(line.rfind(')') + 2));
  std::string token;
  for (int index = 3; index <= 22; ++index) {
    if (!(fields >> token)) {throw std::runtime_error("NATIVE_PROCESS_IDENTITY_UNAVAILABLE");}
  }
  append_integer(geteuid(), 4);
  append_integer(getpid(), 4);
  append_integer(std::stoull(token), 8);
  bytes.insert(bytes.end(), original.begin() + 56, original.end());
  bytes.insert(bytes.end(), endpoint_text.begin(), endpoint_text.end());
  const auto path = parent / "neck-revoke.provision";
  write_copy(path, bytes);
  const auto provision = read_controller_revocation_provision(path, "session-17", endpoint);
  EXPECT_EQ(provision.peer.pid, monitor.pid());
  EXPECT_NE(provision.peer.pid, getpid());
  EXPECT_EQ(provision.capability, monitor.key());
  // Same private encoding, distinct authority and endpoint: neither provision
  // may be interpreted as the other's authorization.
  const auto primary_endpoint = parent / "neck-primary-revoke.sock";
  auto primary_bytes = std::vector<uint8_t>(bytes.begin(), bytes.begin() + 72 + bytes[6]);
  primary_bytes[5] = 4;
  primary_bytes[7] = static_cast<uint8_t>(primary_endpoint.string().size());
  const auto primary_text = primary_endpoint.string();
  primary_bytes.insert(primary_bytes.end(), primary_text.begin(), primary_text.end());
  const auto primary_path = parent / "neck-primary-revoke.provision";
  write_copy(primary_path, primary_bytes);
  EXPECT_EQ(read_controller_primary_fault_provision(primary_path, "session-17",
    primary_endpoint).peer.pid, monitor.pid());
  EXPECT_THROW(read_controller_revocation_provision(primary_path, "session-17",
    primary_endpoint), std::runtime_error);
  EXPECT_THROW(read_controller_primary_fault_provision(path, "session-17", endpoint),
    std::runtime_error);
  auto native_as_monitor = bytes;
  std::copy(bytes.begin() + 56, bytes.begin() + 72, native_as_monitor.begin() + 8);
  const auto self_path = parent / "native-as-monitor.provision";
  write_copy(self_path, native_as_monitor);
  EXPECT_THROW(read_controller_revocation_provision(self_path, "session-17", endpoint),
    std::runtime_error);
  EXPECT_THROW(read_controller_reservation_provision(
      path, ControllerReservationRole::NECK, "session-17"), std::runtime_error);
  EXPECT_THROW(read_controller_revocation_provision(path, "wrong-session", endpoint),
    std::runtime_error);
  EXPECT_THROW(read_controller_revocation_provision(path, "session-17", parent / "wrong.sock"),
    std::runtime_error);
  for (const size_t index : {size_t{5}, size_t{23}, size_t{60}, size_t{71}, bytes.size() - 1}) {
    auto altered = bytes;
    altered[index] ^= 1;
    const auto altered_path = parent / ("altered-" + std::to_string(index) + ".provision");
    write_copy(altered_path, altered);
    EXPECT_THROW(read_controller_revocation_provision(altered_path, "session-17", endpoint),
      std::runtime_error) << index;
  }
  ASSERT_EQ(chmod(path.c_str(), 0644), 0);
  EXPECT_THROW(read_controller_revocation_provision(path, "session-17", endpoint),
    std::runtime_error);
  ASSERT_EQ(chmod(path.c_str(), 0600), 0);
  std::filesystem::create_symlink(path, parent / "alias.provision");
  EXPECT_THROW(read_controller_revocation_provision(parent / "alias.provision", "session-17",
    endpoint),
    std::runtime_error);
  std::filesystem::create_hard_link(path, parent / "hard.provision");
  EXPECT_THROW(read_controller_revocation_provision(path, "session-17", endpoint),
    std::runtime_error);
  // Keep the hard-link refusal fixture; use a separate regular file for peer death.
  const auto live_path = parent / "live.provision";
  write_copy(live_path, bytes);
  monitor.stop();
  EXPECT_THROW(read_controller_revocation_provision(live_path, "session-17", endpoint),
    std::runtime_error);
}
