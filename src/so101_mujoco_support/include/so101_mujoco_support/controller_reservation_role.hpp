#ifndef SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_ROLE_HPP_
#define SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_ROLE_HPP_

#include <cstdint>

namespace so101_mujoco_support
{
enum class ControllerReservationRole : uint8_t {ARM = 1, GRIPPER = 2, NECK = 3};
}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__CONTROLLER_RESERVATION_ROLE_HPP_
