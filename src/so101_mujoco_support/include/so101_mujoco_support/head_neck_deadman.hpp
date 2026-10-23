#ifndef SO101_MUJOCO_SUPPORT__HEAD_NECK_DEADMAN_HPP_
#define SO101_MUJOCO_SUPPORT__HEAD_NECK_DEADMAN_HPP_

#include <sys/types.h>

#include <atomic>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <thread>

namespace so101_mujoco_support
{

// One Unix stream socket per neck-controller activation (design section 1.4).
//
// The directory is created by the owner with mode 0700 before activation; the socket is
// <directory>/neck-<activation_id>.sock. Exactly one peer is accepted: same uid, and the pid
// named in the configuration (checked with SO_PEERCRED). The peer sends heartbeat bytes. The latch
// is set when the peer closes (EOF) or when no byte arrives for the timeout. A latch is permanent
// for this activation, and a closed peer cannot reconnect: a new activation needs a new socket
// and a fresh owner connection.
class NeckDeadman final
{
public:
  struct Config
  {
    std::filesystem::path directory;
    uint64_t activation_id{0};
    pid_t peer_pid{0};
    std::chrono::nanoseconds timeout{std::chrono::milliseconds(200)};
  };
  enum class LatchReason : int {NONE = 0, PEER_EOF = 1, TIMEOUT = 2, SOCKET_ERROR = 3};

  explicit NeckDeadman(Config config);
  ~NeckDeadman();
  NeckDeadman(const NeckDeadman &) = delete;
  NeckDeadman & operator=(const NeckDeadman &) = delete;

  // Throws std::runtime_error whose message is the refusal code.
  void start();
  void stop() noexcept;

  const std::filesystem::path & socket_path() const noexcept {return socket_path_;}
  uint64_t activation_id() const noexcept {return config_.activation_id;}
  bool owner_connected() const noexcept {return connected_.load(std::memory_order_acquire);}
  bool latched() const noexcept {return latched_.load(std::memory_order_acquire);}
  LatchReason latch_reason() const noexcept
  {
    return static_cast<LatchReason>(reason_.load(std::memory_order_acquire));
  }
  pid_t connected_peer_pid() const noexcept {return connected_pid_.load(std::memory_order_acquire);}
  uint64_t refused_peers() const noexcept {return refused_.load(std::memory_order_acquire);}
  uint64_t bytes_received() const noexcept {return bytes_.load(std::memory_order_acquire);}
  static const char * reason_name(LatchReason reason) noexcept;

private:
  void run();
  void latch(LatchReason reason) noexcept;

  Config config_;
  std::filesystem::path socket_path_;
  int listen_fd_{-1};
  int client_fd_{-1};
  int wake_read_{-1};
  int wake_write_{-1};
  std::thread thread_;
  std::atomic<bool> started_{false};
  std::atomic<bool> stopping_{false};
  std::atomic<bool> connected_{false};
  std::atomic<bool> latched_{false};
  std::atomic<int> reason_{0};
  std::atomic<pid_t> connected_pid_{0};
  std::atomic<uint64_t> refused_{0};
  std::atomic<uint64_t> bytes_{0};
};

}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__HEAD_NECK_DEADMAN_HPP_
