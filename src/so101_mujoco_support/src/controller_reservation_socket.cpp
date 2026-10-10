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
#include <cstdio>
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

class ConnectionProgress final
{
public:
  explicit ConnectionProgress(std::atomic<bool> & processing)
  : processing_(processing) {processing_.store(true);}
  ~ConnectionProgress() {processing_.store(false);}

private:
  std::atomic<bool> & processing_;
};

bool wait_for(int fd, short events, Deadline deadline, bool precise = false)
{
  while (true) {
    if (precise) {
#ifdef __linux__
      const auto remaining = std::chrono::duration_cast<std::chrono::nanoseconds>(
        deadline - std::chrono::steady_clock::now()).count();
      if (remaining <= 0) {return false;}
      timespec timeout{static_cast<time_t>(remaining / 1000000000),
        static_cast<long>(remaining % 1000000000)};
      pollfd handle{fd, events, 0};
      const auto result = ppoll(&handle, 1, &timeout, nullptr);
      if (result > 0) {
        return std::chrono::steady_clock::now() < deadline && (handle.revents & events) != 0;
      }
      if (result == 0 || errno != EINTR) {return false;}
      continue;
#else
      return false;
#endif
    }
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

ListenerWait wait_for_listener(int fd, Deadline deadline, bool precise = false)
{
  if (precise) {
    return wait_for(fd, POLLIN, deadline, true) ? ListenerWait::READY :
           (std::chrono::steady_clock::now() >= deadline ? ListenerWait::IDLE : ListenerWait::ERROR);
  }
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

bool read_exact(int fd, uint8_t * bytes, size_t size, Deadline deadline, bool precise = false)
{
  size_t offset = 0;
  while (offset < size) {
    if (!wait_for(fd, POLLIN, deadline, precise)) {return false;}
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

bool write_exact(int fd, const uint8_t * bytes, size_t size, Deadline deadline, bool precise = false)
{
  size_t offset = 0;
  while (offset < size) {
    if (!wait_for(fd, POLLOUT, deadline, precise)) {return false;}
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
  ControllerReservationRole role, IngressSnapshot ingress_snapshot, Authority authority,
  StopRefusalDiagnostic stop_refusal_diagnostic)
: ControllerReservationSocket(std::move(path), std::move(gate), capability, expected_peer,
    std::chrono::duration_cast<std::chrono::nanoseconds>(deadline), std::move(stop_proof),
    role, std::move(ingress_snapshot), authority, false, std::move(stop_refusal_diagnostic))
{}

ControllerReservationSocket::ControllerReservationSocket(
  std::filesystem::path path, std::shared_ptr<ControllerGoalAdmission> gate,
  ControllerReservationCapability capability, ExpectedPeer expected_peer,
  std::chrono::nanoseconds deadline, StopProof stop_proof,
  ControllerReservationRole role, IngressSnapshot ingress_snapshot, Authority authority,
  bool precise_deadline, StopRefusalDiagnostic stop_refusal_diagnostic)
: path_(std::move(path)), gate_(std::move(gate)), capability_(capability),
  expected_peer_(expected_peer),
  deadline_(deadline), precise_deadline_(precise_deadline),
  stop_proof_(std::move(stop_proof)),
  stop_refusal_diagnostic_(std::move(stop_refusal_diagnostic)), role_(role),
  ingress_snapshot_(std::move(ingress_snapshot)), authority_(authority)
{
  if (!gate_) {throw std::invalid_argument("CONTROLLER_RESERVATION_GATE_REQUIRED");}
  if (precise_deadline_ && (authority_ == Authority::PRIMARY ||
    role_ != ControllerReservationRole::NECK || deadline_.count() <= 0 ||
    deadline_ > std::chrono::milliseconds(250)))
  {
    throw std::invalid_argument("CONTROLLER_HEAD_SIMULATION_DEADLINE_INVALID");
  }
  if ((authority_ != Authority::PRIMARY && authority_ != Authority::REVOKER &&
    authority_ != Authority::PRIMARY_FAULT) ||
    (authority_ != Authority::PRIMARY && role_ != ControllerReservationRole::NECK))
  {
    throw std::invalid_argument("CONTROLLER_REVOKER_NECK_REQUIRED");
  }
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

void ControllerReservationSocket::close_gate()
{
  if (authority_ != Authority::PRIMARY) {gate_->fault_revoke();} else {gate_->close();}
}

void ControllerReservationSocket::diagnose_stop_refusal() noexcept
{
  // Call only after fail-closed state and the REJECT write attempt. Diagnostics
  // cannot change the reply, reopen admission, or escape the service worker.
  try {
    if (stop_refusal_diagnostic_) {stop_refusal_diagnostic_();}
  } catch (...) {
  }
}

DiagnosticArmReply ControllerReservationSocket::arm_once(uint64_t generation)
{
  DiagnosticArmReply outcome;
  outcome.role = role_; outcome.generation = generation;
  const auto before = stop_proof_ ? stop_proof_() : ControllerStopEvaluation{};
  outcome.proof = before.record;
  outcome.phase = ArmPhase::STOP_BEFORE;
  if (!before.allowed) {return outcome;}
  const auto armed = gate_->arm_detailed(generation);
  outcome.phase = ArmPhase::GATE_ARM; outcome.gate_reason = armed.reason;
  if (!armed.allowed) {return outcome;}
  const auto after = stop_proof_();
  outcome.proof = after.record;
  outcome.phase = ArmPhase::STOP_AFTER;
  if (!after.allowed) {return outcome;}
  outcome.status = ReservationReplyStatus::ACK;
  outcome.phase = ArmPhase::NONE;
  return outcome;
}

bool ControllerReservationSocket::serve_one()
{
#ifndef __linux__
  close_gate();
  return false;
#else
  const bool precise = precise_deadline_;
  const auto ready = wait_for_listener(listener_, std::chrono::steady_clock::now() + deadline_, precise);
  if (ready == ListenerWait::IDLE) {
    if (process_start_ticks(expected_peer_.pid) != expected_peer_.start_ticks) {
      close_gate();
    }
    return false;
  }
  if (ready != ListenerWait::READY) {
    close_gate();
    return false;
  }
  FileDescriptor connection(accept4(listener_, nullptr, nullptr, SOCK_CLOEXEC | SOCK_NONBLOCK));
  if (connection.get() < 0 || !peer_matches(connection.get())) {
    close_gate();
    return false;
  }
  ConnectionProgress processing(processing_);
  const auto deadline = std::chrono::steady_clock::now() + deadline_;
  std::vector<uint8_t> frame(4);
  if (!read_exact(connection.get(), frame.data(), frame.size(), deadline, precise)) {
    close_gate();
    return false;
  }
  const uint32_t body_size =
    (static_cast<uint32_t>(frame[0]) << 24) |
    (static_cast<uint32_t>(frame[1]) << 16) |
    (static_cast<uint32_t>(frame[2]) << 8) |
    static_cast<uint32_t>(frame[3]);
  if (body_size == 0 || body_size > max_body_size ||
    (authority_ == Authority::REVOKER && body_size > 62) ||
    (authority_ == Authority::PRIMARY_FAULT && body_size > 177))
  {
    close_gate();
    return false;
  }
  frame.resize(4 + body_size);
  size_t consumed = 0;
  if (authority_ == Authority::PRIMARY_FAULT && body_size > 62) {
    // Larger fault frames are reserved solely for the new exact SOPC header.
    if (!read_exact(connection.get(), frame.data() + 4, 6, deadline, precise) ||
      std::memcmp(frame.data() + 4, "SOPC", 4) != 0 || frame[8] != 1 || frame[9] != 1)
    {close_gate(); return false;}
    consumed = 6;
  }
  if (!read_exact(connection.get(), frame.data() + 4 + consumed, body_size - consumed, deadline, precise)) {
    close_gate();
    return false;
  }
  try {
    if (frame.size() >= 10 && std::memcmp(frame.data() + 4, "SOPC", 4) == 0 &&
      authority_ == Authority::PRIMARY_FAULT)
    {
      // Parse syntax before granting nonmutating scope rejection. Invalid peers
      // were already refused above; malformed frames retain old fail-closed behavior.
      const auto request = parse_scoped_close_frame(frame);
      if (role_ != ControllerReservationRole::NECK) {close_gate(); return false;}
      if (request.capability != capability_) {return false;}
      try {
        const auto result = gate_->close_scoped(request.generation,
          request.expected_identity.role, request.expected_identity.incarnation,
          request.expected_identity.boot);
        if (!result.identity) {return false;}
        const IdentityScopeReply reply{static_cast<uint8_t>(result.status),request.generation,
          result.stored_generation,*result.identity};
        const auto body = encode_identity_scope_reply(reply, true);
        std::vector<uint8_t> framed{0,0,0,static_cast<uint8_t>(body.size())};
        framed.insert(framed.end(),body.begin(),body.end());
        const bool written = write_exact(connection.get(),framed.data(),framed.size(),deadline,precise);
        return written && (result.status == ScopedCloseStatus::ARMED_CLOSED ||
          result.status == ScopedCloseStatus::NOT_ARMED_CLOSED);
      } catch (...) {return false;} // no fallback revocation after a valid scoped request
    }
    if (frame.size() >= 10 && std::memcmp(frame.data() + 4, "SOPQ", 4) == 0 &&
      authority_ == Authority::PRIMARY_FAULT)
    {
      const auto generation = parse_bootstrap_identity_frame(frame, capability_);
      if (role_ != ControllerReservationRole::NECK) {close_gate(); return false;}
      try {
        const auto scope = gate_->prearm_scope(generation);
        if (!scope.identity || scope.identity->role != role_) {return false;}
        const IdentityScopeReply reply{0,generation,scope.stored_generation,*scope.identity};
        const auto body = encode_identity_scope_reply(reply,false);
        std::vector<uint8_t> framed{0,0,0,static_cast<uint8_t>(body.size())};
        framed.insert(framed.end(),body.begin(),body.end());
        return write_exact(connection.get(),framed.data(),framed.size(),deadline,precise);
      } catch (...) {return false;} // authenticated bootstrap stays read only
    }
    // SOIA identity query: the service reports only its own active role/generation
    if (frame.size() > 9 && std::memcmp(frame.data() + 4, "SOIA", 4) == 0) {
      const auto reject = [&connection, deadline, precise]() {
          const std::vector<uint8_t> body{'S', 'O', 'I', 'D', 1, 0};
          std::vector<uint8_t> framed{0, 0, 0, static_cast<uint8_t>(body.size())};
          framed.insert(framed.end(), body.begin(), body.end());
          write_exact(connection.get(), framed.data(), framed.size(), deadline, precise);
          return false;
        };
      if (frame.size() != 43 || frame[8] != 1 || frame[9] != 1 ||
        std::memcmp(frame.data() + 10, capability_.data(), capability_.size()) != 0 ||
        frame[42] != static_cast<uint8_t>(role_))
      {
        close_gate();          // impersonating or malformed query: fail closed
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
      return write_exact(connection.get(), framed.data(), framed.size(), deadline, precise);
    }
    // Neither close-only endpoint can decode goal CDR or authorize ingress.
    if (authority_ != Authority::PRIMARY) {
      if (frame.size() != 66 || frame[9] != 2) {
        close_gate();
        return false;
      }
      const auto generation = authority_ == Authority::PRIMARY_FAULT ?
        parse_controller_primary_fault_close_frame(frame, capability_) :
        parse_controller_reservation_close_frame(frame, capability_);
      const bool revoked = gate_->revoke_generation(generation);
      const auto reply = encode_controller_reservation_reply(
        revoked ? ReservationReplyStatus::ACK : ReservationReplyStatus::REJECT, generation);
      return write_exact(connection.get(), reply.data(), reply.size(), deadline, precise) && revoked;
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
      write_exact(connection.get(), reply.data(), reply.size(), deadline, precise);
      return status == BoundReserveStatus::ACCEPTED;
    }
    if (frame.size() > 9 && frame[9] == 2) {
      const auto generation = parse_controller_reservation_close_frame(frame, capability_);
      const auto closed = gate_->close_generation(generation);
      const auto reply = encode_controller_reservation_reply(
        closed ? ReservationReplyStatus::ACK : ReservationReplyStatus::REJECT, generation);
      return write_exact(connection.get(), reply.data(), reply.size(), deadline, precise) && closed;
    }
    if (frame.size() > 9 && frame[9] == 5) {
      const auto generation = parse_prearm_query_frame(frame, capability_);
      if (role_ != ControllerReservationRole::NECK) {close_gate(); return false;}
      // Once authenticated and syntactically valid, a status query is read only,
      // including encoder/write failures. Never fall through to close_gate().
      try {
        const auto scope = gate_->prearm_scope(generation);
        if (!scope.identity || scope.identity->role != role_) {return false;}
        PrearmReply reply;
        reply.generation = generation; reply.stored_generation = scope.stored_generation;
        reply.identity = *scope.identity; reply.gate_reason = scope.reason;
        if (scope.eligible()) {
          if (!stop_proof_) {return false;}
          const auto evaluation = stop_proof_();
          reply.proof = evaluation.record;
          reply.status = evaluation.allowed ? PrearmStatus::READY : PrearmStatus::NOT_READY;
        }
        const auto body = encode_prearm_reply(reply);
        std::vector<uint8_t> framed{0, 0, 0, static_cast<uint8_t>(body.size())};
        framed.insert(framed.end(), body.begin(), body.end());
        return write_exact(connection.get(), framed.data(), framed.size(), deadline, precise);
      } catch (...) {return false;}
    }
    if (frame.size() > 9 && (frame[9] == 3 || frame[9] == 6)) {
      const bool diagnostic = frame[9] == 6;
      const auto generation = diagnostic ? parse_diagnostic_arm_frame(frame, capability_) :
        parse_controller_reservation_arm_frame(frame, capability_);
      if (diagnostic && role_ != ControllerReservationRole::NECK) {close_gate(); return false;}
      const auto outcome = arm_once(generation);
      const bool accepted = outcome.status == ReservationReplyStatus::ACK;
      if (!accepted) {close_gate();}
      bool written;
      if (diagnostic) {
        const auto reply = encode_diagnostic_arm_reply(outcome);
        written = write_exact(connection.get(), reply.data(), reply.size(), deadline, precise);
      } else {
        const auto reply = encode_controller_reservation_reply(outcome.status, generation);
        written = write_exact(connection.get(), reply.data(), reply.size(), deadline, precise);
      }
      if (!accepted) {
        const bool stop_refused = stop_proof_ && (outcome.phase == ArmPhase::STOP_BEFORE ||
          outcome.phase == ArmPhase::STOP_AFTER);
        if (stop_refused) {diagnose_stop_refusal();}
        const char * phase = outcome.phase == ArmPhase::GATE_ARM ? "GENERATION" :
          outcome.phase == ArmPhase::STOP_AFTER ? "STOP_PROOF_AFTER" :
          stop_proof_ ? "STOP_PROOF_BEFORE" : "STOP_PROOF_UNBOUND";
        const auto & p = outcome.proof;
        std::fprintf(stderr,
          "CONTROLLER_ARM_REJECT role=%u generation=%llu phase=%s gate_reason=%u "
          "evaluation_id=%llu wrapper=%u rejection=%u reset=%u flags=%u count=%u losses=%u "
          "first_seq=%llu last_seq=%llu first_received=%lld last_received=%lld evaluated=%lld\n",
          static_cast<unsigned>(role_), static_cast<unsigned long long>(generation), phase,
          static_cast<unsigned>(outcome.gate_reason), static_cast<unsigned long long>(p.evaluation_id),
          static_cast<unsigned>(p.wrapper_reason), p.witness_rejection, p.last_reset_reason,
          p.flags, p.sample_count, p.cumulative_observation_lock_losses,
          static_cast<unsigned long long>(p.first_sequence), static_cast<unsigned long long>(p.last_sequence),
          static_cast<long long>(p.first_received_ns), static_cast<long long>(p.last_received_ns),
          static_cast<long long>(p.evaluated_ns));
        return false;
      }
      if (written) {return true;}
      close_gate(); return false;
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
      return write_exact(connection.get(), reply.data(), reply.size(), deadline, precise) && accepted;
    }
    if (gate_->has_service_identity()) {
      // a bound-mode service must never authorize a legacy raw reservation: the
      // opcode is refused fail-closed and the gate is closed
      const auto request = parse_controller_reservation_frame(frame, capability_);
      close_gate();
      const auto reply = encode_controller_reservation_reply(
        ReservationReplyStatus::REJECT, request.generation);
      write_exact(connection.get(), reply.data(), reply.size(), deadline, precise);
      return false;
    }
    const auto request = parse_controller_reservation_frame(frame, capability_);
    if (stop_proof_ && !stop_proof_()) {
      close_gate();
      const auto reply = encode_controller_reservation_reply(
        ReservationReplyStatus::REJECT, request.generation);
      write_exact(connection.get(), reply.data(), reply.size(), deadline, precise);
      diagnose_stop_refusal();
      return false;
    }
    if (!gate_->reserve(request.uuid, request.goal, request.generation)) {
      close_gate();
      return false;
    }
    const auto reply = encode_controller_reservation_reply(
      ReservationReplyStatus::ACK, request.generation);
    if (write_exact(connection.get(), reply.data(), reply.size(), deadline, precise)) {return true;}
  } catch (...) {
    // Bad credentials, malformed CDR or an allocation failure cannot leave the gate armed.
  }
  close_gate();
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
  ControllerReservationSocket::IngressSnapshot ingress_snapshot,
  ControllerReservationSocket::Authority authority,
  ControllerReservationSocket::StopRefusalDiagnostic stop_refusal_diagnostic)
: ControllerReservationService(std::move(path), std::move(gate), capability, expected_peer,
    std::chrono::duration_cast<std::chrono::nanoseconds>(bounded_service_deadline(deadline)),
    std::move(stop_proof), role, std::move(ingress_snapshot), authority, false,
    std::move(stop_refusal_diagnostic))
{}

ControllerReservationService::ControllerReservationService(
  std::filesystem::path path, std::shared_ptr<ControllerGoalAdmission> gate,
  ControllerReservationCapability capability,
  ControllerReservationSocket::ExpectedPeer expected_peer,
  std::chrono::nanoseconds deadline,
  ControllerReservationSocket::StopProof stop_proof,
  ControllerReservationRole role,
  ControllerReservationSocket::IngressSnapshot ingress_snapshot,
  ControllerReservationSocket::Authority authority, bool precise_deadline,
  ControllerReservationSocket::StopRefusalDiagnostic stop_refusal_diagnostic)
: gate_(gate), socket_(std::move(path), std::move(gate), capability, expected_peer,
    deadline, std::move(stop_proof), role,
    std::move(ingress_snapshot), authority, precise_deadline, std::move(stop_refusal_diagnostic))
{   // a service without an active gate is misconfigured, not merely idle
  if (!gate_) {throw std::invalid_argument("CONTROLLER_RESERVATION_GATE_REQUIRED");}
  if (deadline.count() <= 0 || deadline > (precise_deadline ?
    std::chrono::milliseconds(250) : std::chrono::milliseconds(1000)))
  {
    throw std::invalid_argument("CONTROLLER_RESERVATION_SERVICE_DEADLINE_INVALID");
  }
  try {
    worker_ = std::thread([this, authority]() {
          while (!stop_.load()) {
            try {
              socket_.serve_one();
            } catch (...) {
              if (authority != ControllerReservationSocket::Authority::PRIMARY) {
                gate_->fault_revoke();
              } else {
                gate_->close();
              }
              return;
            }
          }
      });
  } catch (...) {
    if (authority != ControllerReservationSocket::Authority::PRIMARY) {
      gate_->fault_revoke();
    } else {
      gate_->close();
    }
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
