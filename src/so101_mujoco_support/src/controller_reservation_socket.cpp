#include "so101_mujoco_support/controller_reservation_socket.hpp"

#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cstddef>
#include <cstring>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace so101_mujoco_support
{
namespace
{
using Deadline = std::chrono::steady_clock::time_point;
constexpr uint32_t max_body_size = 1048640;

class FileDescriptor final
{
public:
  explicit FileDescriptor(int value)
  : value_(value) {}
  ~FileDescriptor() {if (value_ >= 0) {close(value_);}}
  int get() const {return value_;}

private:
  int value_;
};

bool wait_for(int fd, short events, Deadline deadline)
{
  while (true) {
    const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(
      deadline - std::chrono::steady_clock::now()).count();
    if (remaining <= 0) {return false;}
    pollfd handle{fd, events, 0};
    const int result = poll(&handle, 1, static_cast<int>(remaining));
    if (result > 0) {return (handle.revents & events) != 0;}
    if (result == 0) {return false;}
    if (errno != EINTR) {return false;}
  }
}

bool read_exact(int fd, uint8_t * bytes, size_t size, Deadline deadline)
{
  size_t offset = 0;
  while (offset < size) {
    if (!wait_for(fd, POLLIN, deadline)) {return false;}
    const auto count = recv(fd, bytes + offset, size - offset, MSG_DONTWAIT);
    if (count > 0) {
      offset += static_cast<size_t>(count);
    } else if (count == 0) {
      return false;
    } else if (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) {
      return false;
    }
  }
  return true;
}

bool write_exact(int fd, const uint8_t * bytes, size_t size, Deadline deadline)
{
  size_t offset = 0;
  while (offset < size) {
    if (!wait_for(fd, POLLOUT, deadline)) {return false;}
#ifdef MSG_NOSIGNAL
    constexpr int flags = MSG_DONTWAIT | MSG_NOSIGNAL;
#else
    constexpr int flags = MSG_DONTWAIT;
#endif
    const auto count = send(fd, bytes + offset, size - offset, flags);
    if (count > 0) {
      offset += static_cast<size_t>(count);
    } else if (count == 0) {
      return false;
    } else if (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) {
      return false;
    }
  }
  return true;
}

uint64_t process_start_ticks(pid_t pid)
{
#ifdef __linux__
  std::ifstream input("/proc/" + std::to_string(pid) + "/stat");
  std::string line;
  if (!std::getline(input, line)) {return 0;}
  const auto close = line.rfind(')');
  if (close == std::string::npos || close + 2 >= line.size()) {return 0;}
  std::istringstream fields(line.substr(close + 2));
  std::string token;
  for (size_t field = 3; field <= 22; ++field) {
    if (!(fields >> token)) {return 0;}
  }
  try {
    return std::stoull(token);
  } catch (...) {
    return 0;
  }
#else
  (void)pid;
  return 0;
#endif
}
}  // namespace

ControllerReservationSocket::ControllerReservationSocket(
  std::filesystem::path path, ControllerGoalAdmission & gate,
  ControllerReservationCapability capability, ExpectedPeer expected_peer,
  std::chrono::milliseconds deadline)
: path_(std::move(path)), gate_(gate), capability_(capability), expected_peer_(expected_peer),
  deadline_(deadline)
{
#ifndef __linux__
  throw std::runtime_error("CONTROLLER_RESERVATION_SOCKET_LINUX_REQUIRED");
#else
  if (!path_.is_absolute() || path_ != path_.lexically_normal() ||
    path_.filename().empty() || deadline_.count() <= 0 ||
    expected_peer_.pid <= 0 || expected_peer_.start_ticks == 0 ||
    std::all_of(capability_.begin(), capability_.end(), [](uint8_t byte) {return byte == 0;}))
  {
    throw std::runtime_error("CONTROLLER_RESERVATION_SOCKET_CONFIG_INVALID");
  }
  struct stat parent_info {};
  const auto parent = path_.parent_path();
  for (auto ancestor = parent; !ancestor.empty(); ancestor = ancestor.parent_path()) {
    struct stat ancestor_info {};
    if (lstat(ancestor.c_str(), &ancestor_info) != 0 || !S_ISDIR(ancestor_info.st_mode)) {
      throw std::runtime_error("CONTROLLER_RESERVATION_ANCESTOR_INVALID");
    }
    if (ancestor == ancestor.root_path()) {break;}
  }
  if (lstat(parent.c_str(), &parent_info) != 0 || !S_ISDIR(parent_info.st_mode) ||
    parent_info.st_uid != geteuid() || (parent_info.st_mode & 0777) != 0700)
  {
    throw std::runtime_error("CONTROLLER_RESERVATION_DIRECTORY_INVALID");
  }
  struct stat existing {};
  if (lstat(path_.c_str(), &existing) == 0 || errno != ENOENT) {
    throw std::runtime_error("CONTROLLER_RESERVATION_PATH_OCCUPIED");
  }
  sockaddr_un address{};
  address.sun_family = AF_UNIX;
  const auto name = path_.string();
  if (name.size() >= sizeof(address.sun_path)) {
    throw std::runtime_error("CONTROLLER_RESERVATION_PATH_TOO_LONG");
  }
  std::memcpy(address.sun_path, name.c_str(), name.size() + 1);
  listener_ = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
  if (listener_ < 0) {throw std::runtime_error("CONTROLLER_RESERVATION_SOCKET_FAILED");}
  const auto address_size = static_cast<socklen_t>(offsetof(sockaddr_un,
      sun_path) + name.size() + 1);
  if (bind(listener_, reinterpret_cast<const sockaddr *>(&address), address_size) != 0) {
    close(listener_);
    listener_ = -1;
    throw std::runtime_error("CONTROLLER_RESERVATION_BIND_FAILED");
  }
  if (chmod(path_.c_str(), 0600) != 0 || listen(listener_, 1) != 0 ||
    lstat(path_.c_str(), &existing) != 0 || !S_ISSOCK(existing.st_mode))
  {
    close(listener_);
    listener_ = -1;
    unlink(path_.c_str());
    throw std::runtime_error("CONTROLLER_RESERVATION_LISTEN_FAILED");
  }
  bound_device_ = existing.st_dev;
  bound_inode_ = existing.st_ino;
#endif
}

ControllerReservationSocket::~ControllerReservationSocket()
{
  if (listener_ >= 0) {close(listener_);}
  struct stat current {};
  if (bound_inode_ != 0 && lstat(path_.c_str(), &current) == 0 &&
    current.st_dev == bound_device_ && current.st_ino == bound_inode_)
  {
    unlink(path_.c_str());
  }
}

bool ControllerReservationSocket::peer_matches(int connection) const
{
#ifdef __linux__
  struct ucred peer {};
  socklen_t length = sizeof(peer);
  return getsockopt(connection, SOL_SOCKET, SO_PEERCRED, &peer, &length) == 0 &&
         length == sizeof(peer) && peer.uid == expected_peer_.uid &&
         peer.pid == expected_peer_.pid &&
         process_start_ticks(peer.pid) == expected_peer_.start_ticks;
#else
  (void)connection;
  return false;
#endif
}

bool ControllerReservationSocket::serve_one()
{
#ifndef __linux__
  gate_.close();
  return false;
#else
  const auto deadline = std::chrono::steady_clock::now() + deadline_;
  if (!wait_for(listener_, POLLIN, deadline)) {
    gate_.close();
    return false;
  }
  FileDescriptor connection(accept4(listener_, nullptr, nullptr, SOCK_CLOEXEC | SOCK_NONBLOCK));
  if (connection.get() < 0 || !peer_matches(connection.get())) {
    gate_.close();
    return false;
  }
  std::vector<uint8_t> frame(4);
  if (!read_exact(connection.get(), frame.data(), frame.size(), deadline)) {
    gate_.close();
    return false;
  }
  const uint32_t body_size =
    (static_cast<uint32_t>(frame[0]) << 24) |
    (static_cast<uint32_t>(frame[1]) << 16) |
    (static_cast<uint32_t>(frame[2]) << 8) |
    static_cast<uint32_t>(frame[3]);
  if (body_size == 0 || body_size > max_body_size) {
    gate_.close();
    return false;
  }
  frame.resize(4 + body_size);
  if (!read_exact(connection.get(), frame.data() + 4, body_size, deadline)) {
    gate_.close();
    return false;
  }
  try {
    if (frame.size() > 9 && frame[9] == 2) {
      const auto generation = parse_controller_reservation_close_frame(frame, capability_);
      const auto closed = gate_.close_generation(generation);
      const auto reply = encode_controller_reservation_reply(
        closed ? ReservationReplyStatus::ACK : ReservationReplyStatus::REJECT, generation);
      return write_exact(connection.get(), reply.data(), reply.size(), deadline) && closed;
    }
    const auto request = parse_controller_reservation_frame(frame, capability_);
    if (!gate_.reserve(request.uuid, request.goal, request.generation)) {
      gate_.close();
      return false;
    }
    const auto reply = encode_controller_reservation_reply(
      ReservationReplyStatus::ACK, request.generation);
    if (write_exact(connection.get(), reply.data(), reply.size(), deadline)) {return true;}
  } catch (...) {
    // Bad credentials, malformed CDR or an allocation failure cannot leave the gate armed.
  }
  gate_.close();
  return false;
#endif
}

}  // namespace so101_mujoco_support
