#include "so101_mujoco_support/head_revocation_transport.h"

#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <cerrno>
#include <charconv>
#include <cstddef>
#include <cstring>
#include <filesystem>
#include <limits>
#include <sstream>
#include <string>

namespace
{
enum Error : uint32_t {OK, CONFIG, PATH, PEER, IO, DEADLINE, REPLY, REJECTED};

struct Descriptor
{
  explicit Descriptor(int value) : fd(value) {}
  ~Descriptor() {if (fd >= 0) {close(fd);}}
  int fd;
};

uint64_t now_ns()
{
  timespec now{};
  if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {return 0;}
  return static_cast<uint64_t>(now.tv_sec) * 1000000000ULL + now.tv_nsec;
}

Error wait_ready(int fd, short events, uint64_t deadline)
{
  while (true) {
    const auto now = now_ns();
    if (now == 0 || now >= deadline) {return DEADLINE;}
    const auto remaining = deadline - now;
    timespec timeout{static_cast<time_t>(remaining / 1000000000ULL),
      static_cast<long>(remaining % 1000000000ULL)};
    pollfd handle{fd, events, 0};
    const auto ready = ppoll(&handle, 1, &timeout, nullptr);
    if (ready > 0) {return (handle.revents & events) ? OK : IO;}
    if (ready == 0) {return DEADLINE;}
    if (errno != EINTR) {return IO;}
  }
}

uint64_t start_ticks(int32_t pid)
{
  const std::string path = "/proc/" + std::to_string(pid) + "/stat";
  Descriptor input(open(path.c_str(), O_RDONLY | O_CLOEXEC));
  if (input.fd < 0) {return 0;}
  std::array<char, 8192> bytes{};
  const auto count = read(input.fd, bytes.data(), bytes.size());
  if (count <= 0 || static_cast<size_t>(count) == bytes.size()) {return 0;}
  const std::string line(bytes.data(), count);
  const auto closing = line.rfind(')');
  if (closing == std::string::npos || closing + 2 >= line.size()) {return 0;}
  std::istringstream fields(line.substr(closing + 2));
  std::string token;
  for (int field = 3; field <= 22; ++field) {
    if (!(fields >> token) || (field == 3 && token == "Z")) {return 0;}
  }
  uint64_t value{};
  const auto parsed = std::from_chars(token.data(), token.data() + token.size(), value);
  return parsed.ec == std::errc{} && parsed.ptr == token.data() + token.size() ? value : 0;
}

bool matches_peer(int fd, uint32_t uid, int32_t pid, uint64_t ticks)
{
  ucred peer{};
  socklen_t length = sizeof(peer);
  return getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &peer, &length) == 0 &&
         length == sizeof(peer) && peer.uid == uid && peer.pid == pid &&
         start_ticks(peer.pid) == ticks;
}

bool private_path(const std::filesystem::path & path)
{
  if (!path.is_absolute() || path != path.lexically_normal() || path.filename().empty()) {
    return false;
  }
  for (auto parent = path.parent_path(); ; parent = parent.parent_path()) {
    struct stat info{};
    if (lstat(parent.c_str(), &info) != 0 || !S_ISDIR(info.st_mode)) {return false;}
    if (parent == parent.root_path()) {break;}
  }
  struct stat parent{}, endpoint{};
  return lstat(path.parent_path().c_str(), &parent) == 0 &&
         parent.st_uid == geteuid() && (parent.st_mode & 0777) == 0700 &&
         lstat(path.c_str(), &endpoint) == 0 && S_ISSOCK(endpoint.st_mode) &&
         endpoint.st_uid == geteuid() && (endpoint.st_mode & 0777) == 0600;
}

Error read_exact(int fd, uint8_t * destination, size_t size, uint64_t deadline)
{
  size_t offset{};
  while (offset < size) {
    const auto ready = wait_ready(fd, POLLIN, deadline);
    if (ready != OK) {return ready;}
    const auto count = recv(fd, destination + offset, size - offset, MSG_DONTWAIT);
    if (count > 0) {offset += count;} else if (count == 0) {return REPLY;} else if (
      errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK)
    {return IO;}
  }
  return OK;
}

uint64_t generation_of(const uint8_t * bytes)
{
  uint64_t value{};
  for (int index = 0; index < 8; ++index) {value = (value << 8) | bytes[index];}
  return value;
}

Error validate_reply(const So101HeadRevocationResult & result, uint32_t operation, uint64_t generation)
{
  const auto * reply = result.reply;
  if (operation == 2) {
    if (result.reply_size != 16 || std::memcmp(reply, "SOGA\x01", 5) != 0 ||
      reply[6] != 0 || reply[7] != 0 || reply[5] > 1 || generation_of(reply + 8) != generation)
    {return REPLY;}
    return reply[5] == 0 ? OK : REJECTED;
  }
  if (result.reply_size < 17 || std::memcmp(reply, "SOID\x01\x01\x03", 7) != 0 ||
    generation_of(reply + 7) != generation)
  {return REPLY;}
  size_t offset = 15;
  for (int value = 0; value < 2; ++value) {
    if (offset >= result.reply_size) {return REPLY;}
    const auto length = reply[offset++];
    if (length == 0 || length > 64 || offset + length > result.reply_size) {return REPLY;}
    for (size_t index = 0; index < length; ++index) {
      if (reply[offset + index] < 32 || reply[offset + index] > 126) {return REPLY;}
    }
    offset += length;
  }
  return offset == result.reply_size ? OK : REPLY;
}

Error exchange(
  const char * path, const uint8_t * capability, uint64_t generation,
  uint32_t uid, int32_t pid, uint64_t ticks, uint64_t request,
  uint64_t budget, uint64_t maximum_budget, uint32_t operation,
  So101HeadRevocationResult & result)
{
  result.entry_ns = now_ns();
  if (!path || !capability || !request || !budget || budget > maximum_budget ||
    request > result.entry_ns || budget > std::numeric_limits<uint64_t>::max() - request ||
    !generation || pid <= 0 || !ticks || (operation != 1 && operation != 2) ||
    std::all_of(capability, capability + 32, [](auto byte) {return byte == 0;}))
  {return CONFIG;}
  const auto deadline = request + budget;
  if (result.entry_ns >= deadline) {return DEADLINE;}
  const auto length = strnlen(path, 108);
  if (length == 0 || length >= 108 || !private_path(path)) {return PATH;}
  result.phases_ns[0] = now_ns();result.phases_present |= 1;
  result.phase = 1;
  Descriptor connection(socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0));
  if (connection.fd < 0) {return IO;}
  if (now_ns() >= deadline) {return DEADLINE;}
  sockaddr_un address{};address.sun_family = AF_UNIX;
  std::memcpy(address.sun_path, path, length + 1);
  const auto size = static_cast<socklen_t>(offsetof(sockaddr_un, sun_path) + length + 1);
  if (connect(connection.fd, reinterpret_cast<sockaddr *>(&address), size) != 0) {
    if (errno != EINPROGRESS) {return IO;}
    const auto ready = wait_ready(connection.fd, POLLOUT, deadline);
    if (ready != OK) {return ready;}
    int error{};socklen_t error_size = sizeof(error);
    if (getsockopt(connection.fd, SOL_SOCKET, SO_ERROR, &error, &error_size) != 0 || error != 0) {
      return IO;
    }
  }
  result.phases_ns[1] = now_ns();result.phases_present |= 2;result.phase = 2;
  if (!matches_peer(connection.fd, uid, pid, ticks)) {return PEER;}
  result.phases_ns[2] = now_ns();result.phases_present |= 4;result.phase = 3;
  std::array<uint8_t, 66> frame{};
  frame[3] = operation == 1 ? 39 : 62;
  std::memcpy(frame.data() + 4, operation == 1 ? "SOIA" : "SOGR", 4);
  frame[8] = 1;frame[9] = operation == 1 ? 1 : 2;
  std::memcpy(frame.data() + 10, capability, 32);
  if (operation == 1) {frame[42] = 3;} else {
    for (int index = 0; index < 8; ++index) {frame[42 + index] = generation >> (56 - 8 * index);}
  }
  const size_t frame_size = operation == 1 ? 43 : 66;
  size_t sent{};
  while (sent < frame_size) {
    const auto ready = wait_ready(connection.fd, POLLOUT, deadline);
    if (ready != OK) {return ready;}
    const auto count = send(connection.fd, frame.data() + sent, frame_size - sent,
      MSG_DONTWAIT | MSG_NOSIGNAL);
    if (count > 0) {sent += count;} else if (count == 0 ||
      (errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK))
    {return IO;}
  }
  result.phases_ns[3] = now_ns();result.phases_present |= 8;result.phase = 4;
  result.reply_size = 16;
  if (operation == 1) {
    std::array<uint8_t, 4> header{};
    const auto read = read_exact(connection.fd, header.data(), header.size(), deadline);
    if (read != OK) {return read;}
    result.reply_size = (static_cast<uint32_t>(header[0]) << 24) |
      (static_cast<uint32_t>(header[1]) << 16) | (static_cast<uint32_t>(header[2]) << 8) | header[3];
    if (result.reply_size < 17 || result.reply_size > sizeof(result.reply)) {return REPLY;}
  }
  const auto read = read_exact(connection.fd, result.reply, result.reply_size, deadline);
  if (read != OK) {return read;}
  result.phases_ns[4] = now_ns();result.phases_present |= 16;result.phase = 5;
  if (!matches_peer(connection.fd, uid, pid, ticks)) {return PEER;}
  result.phases_ns[5] = now_ns();result.phases_present |= 32;result.phase = 6;
  const auto validated = validate_reply(result, operation, generation);
  if (validated != OK) {return validated;}
  const auto now = now_ns();
  if (now == 0 || now >= deadline) {return DEADLINE;}
  result.ack_ns = now;result.phase = 7;
  return OK;
}
}  // namespace

uint32_t so101_head_revocation_abi(void) {return 1;}
uint32_t so101_head_revocation_result_size(void) {return sizeof(So101HeadRevocationResult);}

uint32_t so101_head_revocation_exchange(
  const char * path, const uint8_t * capability, uint64_t generation,
  uint32_t native_uid, int32_t native_pid, uint64_t native_start_ticks,
  uint64_t request_ns, uint64_t budget_ns, uint32_t operation,
  So101HeadRevocationResult * result)
{
  if (!result) {return CONFIG;}
  *result = {};
  Error code = IO;
  try {
    code = exchange(path, capability, generation, native_uid, native_pid,
      native_start_ticks, request_ns, budget_ns, 2000000, operation, *result);
  } catch (...) {code = IO;}
  result->error_number = code == OK ? 0 : errno;
  result->ended_ns = now_ns();
  return code;
}

uint64_t so101_head_revocation_simulation_max_budget_ns(void) {return 250000000;}

uint32_t so101_head_revocation_simulation_exchange(
  const char * path, const uint8_t * capability, uint64_t generation,
  uint32_t native_uid, int32_t native_pid, uint64_t native_start_ticks,
  uint64_t request_ns, uint64_t budget_ns, uint32_t operation,
  So101HeadRevocationResult * result)
{
  if (!result) {return CONFIG;}
  *result = {};
  Error code = IO;
  try {
    code = exchange(path, capability, generation, native_uid, native_pid,
      native_start_ticks, request_ns, budget_ns,
      so101_head_revocation_simulation_max_budget_ns(), operation, *result);
  } catch (...) {code = IO;}
  result->error_number = code == OK ? 0 : errno;
  result->ended_ns = now_ns();
  return code;
}
