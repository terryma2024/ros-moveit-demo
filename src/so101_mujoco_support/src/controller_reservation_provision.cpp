#include "so101_mujoco_support/controller_reservation_provision.hpp"

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace so101_mujoco_support
{
namespace
{
class Descriptor
{
public:
  explicit Descriptor(int value)
  : value_(value) {}
  ~Descriptor() {if (value_ >= 0) {close(value_);}}
  Descriptor(const Descriptor &) = delete;
  Descriptor & operator=(const Descriptor &) = delete;
  int get() const {return value_;}

private:
  int value_;
};

bool valid_session(const std::string & value)
{
  if (value.empty() || value.size() > 64) {return false;}
  const auto alnum = [](unsigned char byte) {
      return (byte >= 'A' && byte <= 'Z') || (byte >= 'a' && byte <= 'z') ||
             (byte >= '0' && byte <= '9');
    };
  if (!alnum(value[0])) {return false;}
  return std::all_of(value.begin(), value.end(), [&](unsigned char byte) {
             return alnum(byte) || byte == '_' || byte == '-';
    });
}

uint64_t integer(const std::vector<uint8_t> & bytes, size_t first, size_t width)
{
  uint64_t value = 0;
  for (size_t index = first; index < first + width; ++index) {
    value = (value << 8) | bytes[index];
  }
  return value;
}

uint64_t process_start_ticks(pid_t pid)
{
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
}

void verify_path(const std::filesystem::path & path)
{
  if (!path.is_absolute() || path != path.lexically_normal() || path.filename().empty()) {
    throw std::runtime_error("CONTROLLER_RESERVATION_PROVISION_INVALID");
  }
  const auto parent = path.parent_path();
  for (auto ancestor = parent; !ancestor.empty(); ancestor = ancestor.parent_path()) {
    struct stat info {};
    if (lstat(ancestor.c_str(), &info) != 0 || !S_ISDIR(info.st_mode)) {
      throw std::runtime_error("CONTROLLER_RESERVATION_PROVISION_INVALID");
    }
    if (ancestor == ancestor.root_path()) {break;}
  }
  struct stat info {};
  if (lstat(parent.c_str(), &info) != 0 || !S_ISDIR(info.st_mode) ||
    info.st_uid != geteuid() || (info.st_mode & 07777) != 0700)
  {
    throw std::runtime_error("CONTROLLER_RESERVATION_PROVISION_INVALID");
  }
}
}  // namespace

ControllerReservationProvision read_controller_reservation_provision(
  const std::filesystem::path & path, ControllerReservationRole expected_role,
  const std::string & expected_session)
{
#ifndef __linux__
  (void)path;
  (void)expected_role;
  (void)expected_session;
  throw std::runtime_error("CONTROLLER_RESERVATION_PROVISION_LINUX_REQUIRED");
#else
  if (!valid_session(expected_session) ||
    (expected_role != ControllerReservationRole::ARM &&
    expected_role != ControllerReservationRole::GRIPPER &&
    expected_role != ControllerReservationRole::NECK))
  {
    throw std::runtime_error("CONTROLLER_RESERVATION_PROVISION_INVALID");
  }
  verify_path(path);
  Descriptor file(open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW));
  struct stat info {};
  if (file.get() < 0 || fstat(file.get(), &info) != 0 || !S_ISREG(info.st_mode) ||
    info.st_uid != geteuid() || (info.st_mode & 07777) != 0600 || info.st_nlink != 1 ||
    info.st_size < 57 || info.st_size > 120)
  {
    throw std::runtime_error("CONTROLLER_RESERVATION_PROVISION_INVALID");
  }
  std::vector<uint8_t> bytes(static_cast<size_t>(info.st_size));
  size_t offset = 0;
  while (offset < bytes.size()) {
    const auto count = read(file.get(), bytes.data() + offset, bytes.size() - offset);
    if (count <= 0) {throw std::runtime_error("CONTROLLER_RESERVATION_PROVISION_INVALID");}
    offset += static_cast<size_t>(count);
  }
  struct stat after {};
  struct stat current {};
  if (fstat(file.get(), &after) != 0 || after.st_size != info.st_size ||
    lstat(path.c_str(), &current) != 0 ||
    current.st_dev != info.st_dev || current.st_ino != info.st_ino)
  {
    throw std::runtime_error("CONTROLLER_RESERVATION_PROVISION_INVALID");
  }
  if (bytes[0] != 'S' || bytes[1] != 'O' || bytes[2] != 'P' || bytes[3] != 'R' ||
    bytes[4] != 1 || bytes[5] != static_cast<uint8_t>(expected_role) ||
    bytes[6] == 0 || bytes[6] > 64 || bytes[7] != 0 ||
    bytes.size() != 56 + bytes[6])
  {
    throw std::runtime_error("CONTROLLER_RESERVATION_PROVISION_INVALID");
  }
  const std::string session(bytes.begin() + 56, bytes.end());
  const auto uid = integer(bytes, 8, 4);
  const auto pid = integer(bytes, 12, 4);
  const auto ticks = integer(bytes, 16, 8);
  if (session != expected_session || uid != geteuid() || pid == 0 ||
    pid > static_cast<uint64_t>(std::numeric_limits<pid_t>::max()) || ticks == 0 ||
    process_start_ticks(static_cast<pid_t>(pid)) != ticks)
  {
    throw std::runtime_error("CONTROLLER_RESERVATION_PROVISION_INVALID");
  }
  ControllerReservationCapability capability{};
  std::copy(bytes.begin() + 24, bytes.begin() + 56, capability.begin());
  if (std::all_of(capability.begin(), capability.end(), [](uint8_t value) {return value == 0;})) {
    throw std::runtime_error("CONTROLLER_RESERVATION_PROVISION_INVALID");
  }
  return {{static_cast<uid_t>(uid), static_cast<pid_t>(pid), ticks}, capability};
#endif
}

}  // namespace so101_mujoco_support
