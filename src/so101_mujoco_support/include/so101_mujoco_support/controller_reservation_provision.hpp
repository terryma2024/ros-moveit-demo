#ifndef SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_PROVISION_HPP_
#define SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_PROVISION_HPP_

#include <cstdint>
#include <filesystem>
#include <string>

#include "so101_mujoco_support/controller_reservation_socket.hpp"
#include "so101_mujoco_support/controller_reservation_role.hpp"

namespace so101_mujoco_support
{

struct ControllerReservationProvision
{
  ControllerReservationSocket::ExpectedPeer peer;
  ControllerReservationCapability capability;
};

ControllerReservationProvision read_controller_reservation_provision(
  const std::filesystem::path & path, ControllerReservationRole expected_role,
  const std::string & expected_session);

}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_PROVISION_HPP_
