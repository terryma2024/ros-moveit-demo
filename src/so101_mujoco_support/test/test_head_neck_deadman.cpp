#include <gtest/gtest.h>

#include <poll.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

#include <chrono>
#include <cstring>
#include <functional>
#include <stdexcept>
#include <filesystem>
#include <string>
#include <thread>

#include "so101_mujoco_support/head_neck_deadman.hpp"

namespace
{
using namespace std::chrono_literals;
using so101_mujoco_support::NeckDeadman;

std::filesystem::path private_directory()
{
  char pattern[] = "/tmp/so101-deadman-XXXXXX";
  if (mkdtemp(pattern) == nullptr) {throw std::runtime_error("TEST_DIR_FAILED");}
  chmod(pattern, 0700);
  return pattern;
}

NeckDeadman::Config config(const std::filesystem::path & directory, pid_t pid = getpid(),
  std::chrono::milliseconds timeout = 200ms, uint64_t id = 1)
{
  NeckDeadman::Config value;
  value.directory = directory;
  value.activation_id = id;
  value.peer_pid = pid;
  value.timeout = timeout;
  return value;
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

bool wait_until(const std::function<bool()> & predicate, std::chrono::milliseconds limit = 1000ms)
{
  const auto deadline = std::chrono::steady_clock::now() + limit;
  while (std::chrono::steady_clock::now() < deadline) {
    if (predicate()) {return true;}
    std::this_thread::sleep_for(1ms);
  }
  return predicate();
}

// A peer that is gone from the other side reads as EOF; a refused peer is closed by the controller.
bool peer_closed_by_server(int fd, std::chrono::milliseconds limit = 500ms)
{
  pollfd item{fd, POLLIN, 0};
  if (poll(&item, 1, static_cast<int>(limit.count())) <= 0) {return false;}
  char byte;
  return recv(fd, &byte, 1, MSG_DONTWAIT) == 0;
}
}  // namespace

TEST(NeckDeadman, StartCreatesTheActivationSocketWithMode0600AndNothingConnected)
{
  const auto dir = private_directory();
  NeckDeadman deadman(config(dir, getpid(), 200ms, 7));
  deadman.start();
  EXPECT_EQ(deadman.socket_path(), dir / "neck-7.sock");
  struct stat info{};
  ASSERT_EQ(lstat(deadman.socket_path().c_str(), &info), 0);
  EXPECT_TRUE(S_ISSOCK(info.st_mode));
  EXPECT_EQ(info.st_mode & 0777, 0600u);
  EXPECT_EQ(info.st_uid, geteuid());
  EXPECT_FALSE(deadman.owner_connected());
  EXPECT_FALSE(deadman.latched());
  deadman.stop();
  EXPECT_FALSE(std::filesystem::exists(dir / "neck-7.sock"));
}

TEST(NeckDeadman, NoLatchBeforeTheOwnerConnectsHoweverLongItTakes)
{
  const auto dir = private_directory();
  NeckDeadman deadman(config(dir, getpid(), 50ms));
  deadman.start();
  std::this_thread::sleep_for(300ms);
  EXPECT_FALSE(deadman.latched());
  EXPECT_FALSE(deadman.owner_connected());
}

TEST(NeckDeadman, DirectoryMustExistBeOwnedAndHaveMode0700)
{
  const auto dir = private_directory();
  auto bad = [&](const NeckDeadman::Config & c, const char * code) {
      NeckDeadman deadman(c);
      try {
        deadman.start();
        FAIL() << "expected " << code;
      } catch (const std::runtime_error & error) {
        EXPECT_STREQ(error.what(), code);
      }
    };
  bad(config(dir / "missing"), "DEADMAN_DIRECTORY_MISSING");
  chmod(dir.c_str(), 0755);
  bad(config(dir), "DEADMAN_DIRECTORY_MODE");
  chmod(dir.c_str(), 0770);
  bad(config(dir), "DEADMAN_DIRECTORY_MODE");
  chmod(dir.c_str(), 0700);
  const auto file = dir / "plain";
  { auto out = fopen(file.c_str(), "w"); fclose(out); }
  bad(config(file), "DEADMAN_DIRECTORY_NOT_DIRECTORY");
  const auto link = dir / "link";
  std::filesystem::create_directory_symlink(dir, link);
  bad(config(link), "DEADMAN_DIRECTORY_NOT_DIRECTORY");
  auto too_long = config(dir);
  too_long.activation_id = 1;
  too_long.directory = dir / std::string(120, 'd');
  std::filesystem::create_directory(too_long.directory);
  chmod(too_long.directory.c_str(), 0700);
  bad(too_long, "DEADMAN_PATH_TOO_LONG");
}

TEST(NeckDeadman, AStalePathIsUnlinkedButALiveOrForeignPathIsRefused)
{
  const auto dir = private_directory();
  {
    NeckDeadman first(config(dir));
    first.start();
    // simulate a crashed owner: the path stays, nobody listens
    const auto path = first.socket_path();
    first.stop();
    const int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    std::strncpy(address.sun_path, path.c_str(), sizeof(address.sun_path) - 1);
    ASSERT_EQ(bind(fd, reinterpret_cast<sockaddr *>(&address), sizeof(address)), 0);
    close(fd);  // bound path with no listener: stale
    ASSERT_TRUE(std::filesystem::exists(path));
  }
  NeckDeadman second(config(dir));
  second.start();  // the stale path is unlinked
  EXPECT_TRUE(second.socket_path().string().size() > 0);
  NeckDeadman third(config(dir));
  try {
    third.start();
    FAIL() << "a live path must be refused";
  } catch (const std::runtime_error & error) {
    EXPECT_STREQ(error.what(), "DEADMAN_SOCKET_LIVE");
  }
  second.stop();
  { auto out = fopen((dir / "neck-1.sock").c_str(), "w"); fclose(out); }
  NeckDeadman fourth(config(dir));
  try {
    fourth.start();
    FAIL() << "a regular file must be refused";
  } catch (const std::runtime_error & error) {
    EXPECT_STREQ(error.what(), "DEADMAN_STALE_PATH_UNSAFE");
  }
  EXPECT_TRUE(std::filesystem::exists(dir / "neck-1.sock"));
}

TEST(NeckDeadman, TheNamedPeerConnectsAndItsPidIsRecorded)
{
  const auto dir = private_directory();
  NeckDeadman deadman(config(dir));
  deadman.start();
  const int fd = connect_to(deadman.socket_path());
  ASSERT_GE(fd, 0);
  ASSERT_TRUE(wait_until([&] {return deadman.owner_connected();}));
  EXPECT_EQ(deadman.connected_peer_pid(), getpid());
  EXPECT_EQ(deadman.refused_peers(), 0u);
  EXPECT_FALSE(deadman.latched());
  close(fd);
}

TEST(NeckDeadman, APeerWithAnotherPidIsRefusedAndNeverConnects)
{
  const auto dir = private_directory();
  NeckDeadman deadman(config(dir, getpid() + 1));  // this process is not the named peer
  deadman.start();
  const int fd = connect_to(deadman.socket_path());
  ASSERT_GE(fd, 0);
  EXPECT_TRUE(peer_closed_by_server(fd));
  EXPECT_TRUE(wait_until([&] {return deadman.refused_peers() == 1;}));
  EXPECT_FALSE(deadman.owner_connected());
  EXPECT_FALSE(deadman.latched());
  close(fd);
}

TEST(NeckDeadman, ARealForeignProcessIsRefusedByItsCredentialsAndTheNamedChildIsAccepted)
{
  const auto dir = private_directory();
  int ready[2];
  ASSERT_EQ(pipe(ready), 0);
  // the child connects when told its parent has started the server
  const pid_t child = fork();
  ASSERT_GE(child, 0);
  if (child == 0) {
    close(ready[1]);
    char go;
    if (read(ready[0], &go, 1) != 1) {_exit(2);}
    const int fd = connect_to(dir / "neck-1.sock");
    if (fd < 0) {_exit(3);}
    char byte = 'h';
    (void)!write(fd, &byte, 1);
    pause();
    _exit(0);
  }
  close(ready[0]);
  {
    NeckDeadman wrong(config(dir, child + 1));
    wrong.start();
    ASSERT_EQ(write(ready[1], "g", 1), 1);
    ASSERT_TRUE(wait_until([&] {return wrong.refused_peers() == 1;}, 2000ms));
    EXPECT_FALSE(wrong.owner_connected());
  }
  kill(child, SIGKILL);
  int rc;
  waitpid(child, &rc, 0);
  close(ready[1]);

  int ready2[2];
  ASSERT_EQ(pipe(ready2), 0);
  const pid_t child2 = fork();
  ASSERT_GE(child2, 0);
  if (child2 == 0) {
    close(ready2[1]);
    char go;
    if (read(ready2[0], &go, 1) != 1) {_exit(2);}
    const int fd = connect_to(dir / "neck-1.sock");
    if (fd < 0) {_exit(3);}
    char byte = 'h';
    (void)!write(fd, &byte, 1);
    pause();
    _exit(0);
  }
  close(ready2[0]);
  NeckDeadman right(config(dir, child2));
  right.start();
  ASSERT_EQ(write(ready2[1], "g", 1), 1);
  ASSERT_TRUE(wait_until([&] {return right.owner_connected();}, 2000ms));
  EXPECT_EQ(right.connected_peer_pid(), child2);
  EXPECT_EQ(right.refused_peers(), 0u);
  kill(child2, SIGKILL);
  waitpid(child2, &rc, 0);
  close(ready2[1]);
  EXPECT_TRUE(wait_until([&] {return right.latched();}, 1000ms));
  EXPECT_EQ(right.latch_reason(), NeckDeadman::LatchReason::PEER_EOF);
}

TEST(NeckDeadman, ASecondPeerIsRefusedWhileTheFirstStaysConnected)
{
  const auto dir = private_directory();
  NeckDeadman deadman(config(dir));
  deadman.start();
  const int first = connect_to(deadman.socket_path());
  ASSERT_TRUE(wait_until([&] {return deadman.owner_connected();}));
  const int second = connect_to(deadman.socket_path());
  ASSERT_GE(second, 0);
  EXPECT_TRUE(peer_closed_by_server(second));
  EXPECT_TRUE(wait_until([&] {return deadman.refused_peers() == 1;}));
  EXPECT_TRUE(deadman.owner_connected());
  EXPECT_FALSE(deadman.latched());
  char byte = 'h';
  EXPECT_EQ(write(first, &byte, 1), 1);
  std::this_thread::sleep_for(20ms);
  EXPECT_FALSE(deadman.latched());
  close(first);
  close(second);
}

TEST(NeckDeadman, EofLatchesWithinAFewMilliseconds)
{
  const auto dir = private_directory();
  NeckDeadman deadman(config(dir));
  deadman.start();
  const int fd = connect_to(deadman.socket_path());
  ASSERT_TRUE(wait_until([&] {return deadman.owner_connected();}));
  const auto closed_at = std::chrono::steady_clock::now();
  close(fd);
  ASSERT_TRUE(wait_until([&] {return deadman.latched();}, 200ms));
  EXPECT_LT(std::chrono::steady_clock::now() - closed_at, 50ms);
  EXPECT_EQ(deadman.latch_reason(), NeckDeadman::LatchReason::PEER_EOF);
}

TEST(NeckDeadman, SilenceLatchesAfterTheTimeoutAndNotBefore)
{
  const auto dir = private_directory();
  NeckDeadman deadman(config(dir, getpid(), 200ms));
  deadman.start();
  const int fd = connect_to(deadman.socket_path());
  char byte = 'h';
  const auto sent_at = std::chrono::steady_clock::now();
  ASSERT_EQ(write(fd, &byte, 1), 1);
  ASSERT_TRUE(wait_until([&] {return deadman.owner_connected() && deadman.bytes_received() == 1;}));
  std::this_thread::sleep_for(150ms);
  EXPECT_FALSE(deadman.latched());
  ASSERT_TRUE(wait_until([&] {return deadman.latched();}, 400ms));
  const auto elapsed = std::chrono::steady_clock::now() - sent_at;
  EXPECT_GE(elapsed, 190ms);
  EXPECT_LE(elapsed, 260ms);
  EXPECT_EQ(deadman.latch_reason(), NeckDeadman::LatchReason::TIMEOUT);
  close(fd);
}

TEST(NeckDeadman, HeartbeatsEveryTwentyMillisecondsKeepTheOwnerAlive)
{
  const auto dir = private_directory();
  NeckDeadman deadman(config(dir));
  deadman.start();
  const int fd = connect_to(deadman.socket_path());
  ASSERT_GE(fd, 0);
  char byte = 'h';
  for (int i = 0; i < 40; ++i) {
    ASSERT_EQ(write(fd, &byte, 1), 1);
    std::this_thread::sleep_for(20ms);
    ASSERT_FALSE(deadman.latched()) << "beat " << i;
  }
  EXPECT_GE(deadman.bytes_received(), 40u);
  close(fd);
}

TEST(NeckDeadman, AfterALatchNoPeerCanReconnectWithinThisActivation)
{
  const auto dir = private_directory();
  NeckDeadman deadman(config(dir));
  deadman.start();
  int fd = connect_to(deadman.socket_path());
  ASSERT_TRUE(wait_until([&] {return deadman.owner_connected();}));
  close(fd);
  ASSERT_TRUE(wait_until([&] {return deadman.latched();}));
  fd = connect_to(deadman.socket_path());
  if (fd >= 0) {
    EXPECT_TRUE(peer_closed_by_server(fd));
    close(fd);
  }
  EXPECT_TRUE(deadman.latched());
}

TEST(NeckDeadman, StopJoinsTheThreadUnlinksThePathAndIsIdempotent)
{
  const auto dir = private_directory();
  NeckDeadman deadman(config(dir));
  deadman.start();
  const int fd = connect_to(deadman.socket_path());
  ASSERT_TRUE(wait_until([&] {return deadman.owner_connected();}));
  deadman.stop();
  deadman.stop();
  EXPECT_FALSE(std::filesystem::exists(dir / "neck-1.sock"));
  EXPECT_EQ(connect_to(dir / "neck-1.sock"), -1);
  close(fd);
}

TEST(NeckDeadman, ANewActivationIdMakesANewSocketAndTheOldOneIsNotReused)
{
  const auto dir = private_directory();
  NeckDeadman first(config(dir, getpid(), 200ms, 1));
  first.start();
  const int fd = connect_to(first.socket_path());
  ASSERT_TRUE(wait_until([&] {return first.owner_connected();}));
  first.stop();
  NeckDeadman second(config(dir, getpid(), 200ms, 2));
  second.start();
  EXPECT_EQ(second.socket_path(), dir / "neck-2.sock");
  EXPECT_FALSE(second.owner_connected());
  close(fd);
}
