#ifndef SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_SOCKET_HPP_
#define SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_SOCKET_HPP_

#include <sys/types.h>

#include <chrono>
#include <atomic>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <optional>
#include <thread>

#include "so101_mujoco_support/controller_ingress_witness.hpp"
#include "so101_mujoco_support/controller_reservation_protocol.hpp"

namespace so101_mujoco_support
{

class ControllerReservationSocket final
{
public:
  using StopProof = std::function<bool()>;
  using IngressSnapshot =
    std::function<std::optional<ControllerIngressWitness::Snapshot>()>;

  struct ExpectedPeer
  {
    uid_t uid;
    pid_t pid;
    uint64_t start_ticks;
  };

  ControllerReservationSocket(
    std::filesystem::path path, std::shared_ptr<ControllerGoalAdmission> gate,
    ControllerReservationCapability capability, ExpectedPeer expected_peer,
    std::chrono::milliseconds deadline, StopProof stop_proof = {},
    ControllerReservationRole role = ControllerReservationRole::ARM,
    IngressSnapshot ingress_snapshot = {});
  ~ControllerReservationSocket();

  ControllerReservationSocket(const ControllerReservationSocket &) = delete;
  ControllerReservationSocket & operator=(const ControllerReservationSocket &) = delete;

  // One connection per call. Returns only after ACK was fully written.
  bool serve_one();

private:
  bool peer_matches(int connection) const;

  std::filesystem::path path_;
  std::shared_ptr<ControllerGoalAdmission> gate_;
  ControllerReservationCapability capability_;
  ExpectedPeer expected_peer_;
  std::chrono::milliseconds deadline_;
  StopProof stop_proof_;
  ControllerReservationRole role_;
  IngressSnapshot ingress_snapshot_;
  int listener_{-1};
  dev_t bound_device_{0};
  ino_t bound_inode_{0};
};

class ControllerReservationService final
{
public:
  ControllerReservationService(
    std::filesystem::path path, std::shared_ptr<ControllerGoalAdmission> gate,
    ControllerReservationCapability capability,
    ControllerReservationSocket::ExpectedPeer expected_peer,
    std::chrono::milliseconds deadline,
    ControllerReservationSocket::StopProof stop_proof = {},
    ControllerReservationRole role = ControllerReservationRole::ARM,
    ControllerReservationSocket::IngressSnapshot ingress_snapshot = {});
  ~ControllerReservationService();

  ControllerReservationService(const ControllerReservationService &) = delete;
  ControllerReservationService & operator=(const ControllerReservationService &) = delete;

private:
  std::shared_ptr<ControllerGoalAdmission> gate_;
  ControllerReservationSocket socket_;
  std::atomic<bool> stop_{false};
  std::thread worker_;
};

}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_SOCKET_HPP_
