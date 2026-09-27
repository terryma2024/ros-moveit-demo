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
#include <stdexcept>
#include <string>
#include <vector>

#include "so101_mujoco_support/controller_reservation_provision.hpp"

namespace
{
using so101_mujoco_support::ControllerReservationRole;
using so101_mujoco_support::read_controller_reservation_provision;

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
