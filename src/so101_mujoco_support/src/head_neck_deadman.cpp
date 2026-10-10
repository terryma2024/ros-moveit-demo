#include "so101_mujoco_support/head_neck_deadman.hpp"

#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cstring>
#include <stdexcept>
#include <string>

namespace so101_mujoco_support
{
namespace
{
int64_t now_ns()
{
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
}

[[noreturn]] void refuse(const char * code) {throw std::runtime_error(code);}

void close_fd(int & fd) noexcept
{
  if (fd >= 0) {
    ::close(fd);
    fd = -1;
  }
}

bool set_nonblocking(int fd)
{
  const int flags = fcntl(fd, F_GETFL, 0);
  return flags >= 0 && fcntl(fd, F_SETFL, flags | O_NONBLOCK) == 0;
}
}  // namespace

const char * NeckDeadman::reason_name(LatchReason reason) noexcept
{
  switch (reason) {
    case LatchReason::NONE: return "NONE";
    case LatchReason::PEER_EOF: return "PEER_EOF";
    case LatchReason::TIMEOUT: return "TIMEOUT";
    case LatchReason::SOCKET_ERROR: return "SOCKET_ERROR";
  }
  return "UNKNOWN";
}

NeckDeadman::NeckDeadman(Config config)
: config_(std::move(config)),
  socket_path_(config_.directory / ("neck-" + std::to_string(config_.activation_id) + ".sock"))
{
}

NeckDeadman::~NeckDeadman() {stop();}

void NeckDeadman::start()
{
  if (started_.exchange(true)) {refuse("DEADMAN_ALREADY_STARTED");}
  try {
    if (config_.activation_id == 0 || config_.peer_pid <= 0 ||
      config_.timeout <= std::chrono::nanoseconds::zero())
    {
      refuse("DEADMAN_CONFIG_INVALID");
    }
    struct stat directory{};
    if (lstat(config_.directory.c_str(), &directory) != 0) {refuse("DEADMAN_DIRECTORY_MISSING");}
    if (!S_ISDIR(directory.st_mode)) {refuse("DEADMAN_DIRECTORY_NOT_DIRECTORY");}
    if (directory.st_uid != geteuid()) {refuse("DEADMAN_DIRECTORY_OWNER");}
    if ((directory.st_mode & 07777) != 0700) {refuse("DEADMAN_DIRECTORY_MODE");}
    const std::string path = socket_path_.string();
    sockaddr_un address{};
    if (path.size() >= sizeof(address.sun_path)) {refuse("DEADMAN_PATH_TOO_LONG");}
    // A stale path is unlinked only if it is a socket of ours that nobody listens on.
    struct stat existing{};
    if (lstat(path.c_str(), &existing) == 0) {
      if (!S_ISSOCK(existing.st_mode) || existing.st_uid != geteuid()) {
        refuse("DEADMAN_STALE_PATH_UNSAFE");
      }
      const int probe = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
      if (probe < 0) {refuse("DEADMAN_SOCKET_FAILED");}
      sockaddr_un target{};
      target.sun_family = AF_UNIX;
      std::memcpy(target.sun_path, path.c_str(), path.size() + 1);
      const int rc = connect(probe, reinterpret_cast<sockaddr *>(&target), sizeof(target));
      const int error = errno;
      ::close(probe);
      if (rc == 0) {refuse("DEADMAN_SOCKET_LIVE");}
      if (error != ECONNREFUSED && error != ENOENT) {refuse("DEADMAN_STALE_PATH_UNSAFE");}
      if (unlink(path.c_str()) != 0 && errno != ENOENT) {refuse("DEADMAN_STALE_PATH_UNSAFE");}
    }
    listen_fd_ = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (listen_fd_ < 0) {refuse("DEADMAN_SOCKET_FAILED");}
    address.sun_family = AF_UNIX;
    std::memcpy(address.sun_path, path.c_str(), path.size() + 1);
    const mode_t previous = umask(0177);
    const int bound = bind(listen_fd_, reinterpret_cast<sockaddr *>(&address), sizeof(address));
    umask(previous);
    if (bound != 0) {refuse("DEADMAN_BIND_FAILED");}
    if (chmod(path.c_str(), 0600) != 0 || listen(listen_fd_, 4) != 0 ||
      !set_nonblocking(listen_fd_))
    {
      unlink(path.c_str());
      refuse("DEADMAN_LISTEN_FAILED");
    }
    int pipes[2];
    if (pipe2(pipes, O_CLOEXEC | O_NONBLOCK) != 0) {
      unlink(path.c_str());
      refuse("DEADMAN_PIPE_FAILED");
    }
    wake_read_ = pipes[0];
    wake_write_ = pipes[1];
    thread_ = std::thread([this] {run();});
  } catch (...) {
    close_fd(listen_fd_);
    close_fd(wake_read_);
    close_fd(wake_write_);
    started_.store(false);
    throw;
  }
}

void NeckDeadman::stop() noexcept
{
  if (!started_.load()) {return;}
  stopping_.store(true);
  if (wake_write_ >= 0) {
    const char byte = 'x';
    (void)!::write(wake_write_, &byte, 1);
  }
  if (thread_.joinable()) {thread_.join();}
  close_fd(listen_fd_);
  close_fd(client_fd_);
  close_fd(wake_read_);
  close_fd(wake_write_);
  unlink(socket_path_.c_str());
  started_.store(false);
}

void NeckDeadman::latch(LatchReason reason) noexcept
{
  if (!latched_.load(std::memory_order_acquire)) {
    reason_.store(static_cast<int>(reason), std::memory_order_release);
    latched_.store(true, std::memory_order_release);
  }
  // A latched activation accepts nobody and listens to nobody.
  close_fd(client_fd_);
  close_fd(listen_fd_);
}

void NeckDeadman::run()
{
  int64_t last_byte_ns = 0;
  const int64_t timeout_ns = config_.timeout.count();
  while (!stopping_.load(std::memory_order_acquire)) {
    pollfd items[3];
    nfds_t count = 0;
    items[count++] = {wake_read_, POLLIN, 0};
    const nfds_t listen_index = listen_fd_ >= 0 ? count : 3;
    if (listen_fd_ >= 0) {items[count++] = {listen_fd_, POLLIN, 0};}
    const nfds_t client_index = client_fd_ >= 0 ? count : 3;
    if (client_fd_ >= 0) {items[count++] = {client_fd_, POLLIN, 0};}
    const int ready = poll(items, count, 2);
    if (stopping_.load(std::memory_order_acquire)) {break;}
    if (ready < 0 && errno != EINTR) {
      latch(LatchReason::SOCKET_ERROR);
      break;
    }
    if (ready > 0 && listen_index < 3 && (items[listen_index].revents & POLLIN)) {
      const int accepted = accept4(listen_fd_, nullptr, nullptr, SOCK_CLOEXEC | SOCK_NONBLOCK);
      if (accepted >= 0) {
        ucred credentials{};
        socklen_t length = sizeof(credentials);
        const bool known = getsockopt(accepted, SOL_SOCKET, SO_PEERCRED, &credentials, &length) == 0;
        if (client_fd_ >= 0 || latched_.load() || !known || credentials.uid != geteuid() ||
          credentials.pid != config_.peer_pid)
        {
          ::close(accepted);
          refused_.fetch_add(1, std::memory_order_acq_rel);
        } else {
          client_fd_ = accepted;
          connected_pid_.store(credentials.pid, std::memory_order_release);
          last_byte_ns = now_ns();
          connected_.store(true, std::memory_order_release);
          continue;
        }
      }
    }
    if (client_fd_ >= 0) {
      bool eof = false;
      bool error = false;
      char buffer[64];
      if (ready > 0 && client_index < 3 && items[client_index].revents != 0) {
        for (;;) {
          const ssize_t got = recv(client_fd_, buffer, sizeof(buffer), 0);
          if (got > 0) {
            bytes_.fetch_add(static_cast<uint64_t>(got), std::memory_order_acq_rel);
            last_byte_ns = now_ns();
            continue;
          }
          if (got == 0) {eof = true;} else if (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) {
            error = true;
          }
          break;
        }
      }
      if (eof) {
        latch(LatchReason::PEER_EOF);
        break;
      }
      if (error) {
        latch(LatchReason::SOCKET_ERROR);
        break;
      }
      if (now_ns() - last_byte_ns > timeout_ns) {
        latch(LatchReason::TIMEOUT);
        break;
      }
    }
  }
}

}  // namespace so101_mujoco_support
