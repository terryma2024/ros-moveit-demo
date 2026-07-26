#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

namespace so101_gazebo_demo::pick_place
{

const SO101Profile & SO101Profile::canonical() noexcept
{
  static const SO101Profile profile;
  return profile;
}

}  // namespace so101_gazebo_demo::pick_place
