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

enum class ListenerWait {READY, IDLE, ERROR};

ListenerWait wait_for_listener(int fd, Deadline deadline)
{
  while (true) {
    const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(
      deadline - std::chrono::steady_clock::now()).count();
    if (remaining <= 0) {return ListenerWait::IDLE;}
    pollfd handle{fd, POLLIN, 0};
    const int result = poll(&handle, 1, static_cast<int>(remaining));
    if (result > 0) {
      if (handle.revents & (POLLERR | POLLHUP | POLLNVAL)) {return ListenerWait::ERROR;}
      return handle.revents & POLLIN ? ListenerWait::READY : ListenerWait::ERROR;
    }
    if (result == 0) {return ListenerWait::IDLE;}
    if (errno != EINTR) {return ListenerWait::ERROR;}
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
    if (field == 3 && token == "Z") {return 0;}
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

std::chrono::milliseconds bounded_service_deadline(std::chrono::milliseconds deadline)
{
  if (deadline.count() <= 0 || deadline > std::chrono::milliseconds(1000)) {
    throw std::invalid_argument("CONTROLLER_RESERVATION_SERVICE_DEADLINE_INVALID");
  }
  return deadline;
}
}  // namespace

ControllerReservationSocket::ControllerReservationSocket(
  std::filesystem::path path, std::shared_ptr<ControllerGoalAdmission> gate,
  ControllerReservationCapability capability, ExpectedPeer expected_peer,
  std::chrono::milliseconds deadline, StopProof stop_proof,
  ControllerReservationRole role, IngressSnapshot ingress_snapshot)
: path_(std::move(path)), gate_(std::move(gate)), capability_(capability), expected_peer_(expected_peer),
  deadline_(deadline), stop_proof_(std::move(stop_proof)), role_(role),
  ingress_snapshot_(std::move(ingress_snapshot))
{
  if (!gate_) {throw std::invalid_argument("CONTROLLER_RESERVATION_GATE_REQUIRED");}
#ifndef __linux__
  throw std::runtime_error("CONTROLLER_RESERVATION_SOCKET_LINUX_REQUIRED");
#else
  if (!path_.is_absolute() || path_ != path_.lexically_normal() ||
    path_.filename().empty() || deadline_.count() <= 0 ||
    static_cast<uint8_t>(role_) < 1 || static_cast<uint8_t>(role_) > 3 ||
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
  gate_->close();
  return false;
#else
  const auto ready = wait_for_listener(listener_, std::chrono::steady_clock::now() + deadline_);
  if (ready == ListenerWait::IDLE) {
    if (process_start_ticks(expected_peer_.pid) != expected_peer_.start_ticks) {
      gate_->close();
    }
    return false;
  }
  if (ready != ListenerWait::READY) {
    gate_->close();
    return false;
  }
  FileDescriptor connection(accept4(listener_, nullptr, nullptr, SOCK_CLOEXEC | SOCK_NONBLOCK));
  if (connection.get() < 0 || !peer_matches(connection.get())) {
    gate_->close();
    return false;
  }
  const auto deadline = std::chrono::steady_clock::now() + deadline_;
  std::vector<uint8_t> frame(4);
  if (!read_exact(connection.get(), frame.data(), frame.size(), deadline)) {
    gate_->close();
    return false;
  }
  const uint32_t body_size =
    (static_cast<uint32_t>(frame[0]) << 24) |
    (static_cast<uint32_t>(frame[1]) << 16) |
    (static_cast<uint32_t>(frame[2]) << 8) |
    static_cast<uint32_t>(frame[3]);
  if (body_size == 0 || body_size > max_body_size) {
    gate_->close();
    return false;
  }
  frame.resize(4 + body_size);
  if (!read_exact(connection.get(), frame.data() + 4, body_size, deadline)) {
    gate_->close();
    return false;
  }
  try {
    // SOIA identity query: the service reports only its own active role/generation
    if (frame.size() > 9 && std::memcmp(frame.data() + 4, "SOIA", 4) == 0) {
      const auto reject = [&connection, deadline]() {
          const std::vector<uint8_t> body{'S', 'O', 'I', 'D', 1, 0};
          std::vector<uint8_t> framed{0, 0, 0, static_cast<uint8_t>(body.size())};
          framed.insert(framed.end(), body.begin(), body.end());
          write_exact(connection.get(), framed.data(), framed.size(), deadline);
          return false;
        };
      if (frame.size() != 43 || frame[8] != 1 || frame[9] != 1 ||
        std::memcmp(frame.data() + 10, capability_.data(), capability_.size()) != 0 ||
        frame[42] != static_cast<uint8_t>(role_))
      {
        gate_->close();          // impersonating or malformed query: fail closed
        return reject();
      }
      const auto identity = gate_->service_identity();
      const auto generation = gate_->generation();
      if (!identity || generation == 0) {
        return reject();        // simply not ready: reject, invent nothing, close nothing
      }
      const auto body = encode_identity_reply(role_, generation, identity->incarnation,
                                              identity->boot);
      std::vector<uint8_t> framed{0, 0, 0, static_cast<uint8_t>(body.size())};
      framed.insert(framed.end(), body.begin(), body.end());
      return write_exact(connection.get(), framed.data(), framed.size(), deadline);
    }
    // SOGB v2 bound reservation: detected before the legacy SOGR dispatch
    if (is_bound_reservation_frame(frame)) {
      const auto status = handle_bound_reservation_frame(*gate_, frame, role_, capability_);
      uint64_t generation = 0;
      if (frame.size() >= 50 && frame[8] == kBoundProtocolVersion) {
        for (int index = 0; index < 8; ++index) {
          generation = (generation << 8) | frame[42 + static_cast<size_t>(index)];
        }
      }
      const auto reply = encode_controller_reservation_reply(
        status == BoundReserveStatus::ACCEPTED ? ReservationReplyStatus::ACK :
                                                 ReservationReplyStatus::REJECT,
        generation);
      write_exact(connection.get(), reply.data(), reply.size(), deadline);
      return status == BoundReserveStatus::ACCEPTED;
    }
    if (frame.size() > 9 && frame[9] == 2) {
      const auto generation = parse_controller_reservation_close_frame(frame, capability_);
      const auto closed = gate_->close_generation(generation);
      const auto reply = encode_controller_reservation_reply(
        closed ? ReservationReplyStatus::ACK : ReservationReplyStatus::REJECT, generation);
      return write_exact(connection.get(), reply.data(), reply.size(), deadline) && closed;
    }
    if (frame.size() > 9 && frame[9] == 3) {
      const auto generation = parse_controller_reservation_arm_frame(frame, capability_);
      if (!stop_proof_ || !stop_proof_() || !gate_->arm(generation) || !stop_proof_()) {
        gate_->close();
        const auto reply = encode_controller_reservation_reply(
          ReservationReplyStatus::REJECT, generation);
        write_exact(connection.get(), reply.data(), reply.size(), deadline);
        return false;
      }
      const auto reply = encode_controller_reservation_reply(
        ReservationReplyStatus::ACK, generation);
      if (write_exact(connection.get(), reply.data(), reply.size(), deadline)) {return true;}
      gate_->close();
      return false;
    }
    if (frame.size() > 9 && frame[9] == 4) {
      const auto generation = parse_controller_ingress_query_frame(
        frame, capability_, role_);
      std::optional<ControllerIngressWitness::Snapshot> snapshot;
      if (gate_->is_exclusive_generation(generation) && stop_proof_ &&
        stop_proof_() && ingress_snapshot_)
      {
        snapshot = ingress_snapshot_();
      }
      const bool accepted = snapshot.has_value() &&
        gate_->is_exclusive_generation(generation) && stop_proof_ && stop_proof_();
      const auto reply = encode_controller_ingress_reply(
        accepted ? ReservationReplyStatus::ACK : ReservationReplyStatus::REJECT,
        role_, generation, accepted ? snapshot->sequence : 0,
        accepted ? snapshot->last_ingress_monotonic_ns : 0,
        accepted ? snapshot->observed_monotonic_ns : 0);
      return write_exact(connection.get(), reply.data(), reply.size(), deadline) && accepted;
    }
    if (gate_->has_service_identity()) {
      // a bound-mode service must never authorize a legacy raw reservation: the
      // opcode is refused fail-closed and the gate is closed
      const auto request = parse_controller_reservation_frame(frame, capability_);
      gate_->close();
      const auto reply = encode_controller_reservation_reply(
        ReservationReplyStatus::REJECT, request.generation);
      write_exact(connection.get(), reply.data(), reply.size(), deadline);
      return false;
    }
    const auto request = parse_controller_reservation_frame(frame, capability_);
    if (stop_proof_ && !stop_proof_()) {
      gate_->close();
      const auto reply = encode_controller_reservation_reply(
        ReservationReplyStatus::REJECT, request.generation);
      write_exact(connection.get(), reply.data(), reply.size(), deadline);
      return false;
    }
    if (!gate_->reserve(request.uuid, request.goal, request.generation)) {
      gate_->close();
      return false;
    }
    const auto reply = encode_controller_reservation_reply(
      ReservationReplyStatus::ACK, request.generation);
    if (write_exact(connection.get(), reply.data(), reply.size(), deadline)) {return true;}
  } catch (...) {
    // Bad credentials, malformed CDR or an allocation failure cannot leave the gate armed.
  }
  gate_->close();
  return false;
#endif
}

ControllerReservationService::ControllerReservationService(
  std::filesystem::path path, std::shared_ptr<ControllerGoalAdmission> gate,
  ControllerReservationCapability capability,
  ControllerReservationSocket::ExpectedPeer expected_peer,
  std::chrono::milliseconds deadline,
  ControllerReservationSocket::StopProof stop_proof,
  ControllerReservationRole role,
  ControllerReservationSocket::IngressSnapshot ingress_snapshot)
: gate_(gate), socket_(std::move(path), std::move(gate), capability, expected_peer,
    bounded_service_deadline(deadline), std::move(stop_proof), role,
    std::move(ingress_snapshot))
{   // a service without an active gate is misconfigured, not merely idle
  if (!gate_) {throw std::invalid_argument("CONTROLLER_RESERVATION_GATE_REQUIRED");}
  try {
    worker_ = std::thread([this]() {
          while (!stop_.load()) {
            try {
              socket_.serve_one();
            } catch (...) {
              gate_->close();
              return;
            }
          }
      });
  } catch (...) {
    gate_->close();
    throw;
  }
}

ControllerReservationService::~ControllerReservationService()
{
  gate_->close();
  stop_.store(true);
  if (worker_.joinable()) {worker_.join();}
}

}  // namespace so101_mujoco_support
