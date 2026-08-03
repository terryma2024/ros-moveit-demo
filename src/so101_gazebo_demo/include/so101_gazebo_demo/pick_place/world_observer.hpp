#pragma once
#include "so101_gazebo_demo/pick_place/domain_types.hpp"
#include <pick_place_common/world_observer.hpp>
namespace so101_gazebo_demo::pick_place
{
using pick_place_common::ContactVector3;
using pick_place_common::IWorldObserver;
using pick_place_common::ObservationResult;
using pick_place_common::Pose3d;
using pick_place_common::TaskObjectContactSample;
using pick_place_common::WorldSnapshot;
}  // namespace so101_gazebo_demo::pick_place
