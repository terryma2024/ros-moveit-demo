#pragma once
#include "so101_gazebo_demo/pick_place/domain_types.hpp"
#include "so101_gazebo_demo/pick_place/world_observer.hpp"
#include <pick_place_common/checkpoint.hpp>
namespace so101_gazebo_demo::pick_place
{
using pick_place_common::Checkpoint;
using pick_place_common::CheckpointLoadResult;
using pick_place_common::CheckpointPhase;
using pick_place_common::ExpectedWorldState;
using pick_place_common::ICheckpointStore;
}  // namespace so101_gazebo_demo::pick_place
