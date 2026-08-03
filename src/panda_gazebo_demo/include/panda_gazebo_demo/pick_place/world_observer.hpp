#pragma once
#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include <pick_place_common/world_observer.hpp>
namespace panda_gazebo_demo::pick_place
{
using pick_place_common::IWorldObserver;
using pick_place_common::ObservationResult;
using pick_place_common::orientationDistance;
using pick_place_common::Pose3d;
using pick_place_common::positionDistance;
using pick_place_common::WorldSnapshot;
}  // namespace panda_gazebo_demo::pick_place
