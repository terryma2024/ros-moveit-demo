#pragma once
#include "so101_gazebo_demo/pick_place/world_observer.hpp"
namespace so101_gazebo_demo::pick_place { struct RecoveryRoute { std::optional<State> next_state; std::optional<Failure> failure; }; class IRecoveryPolicy { public: virtual ~IRecoveryPolicy()=default; virtual RecoveryRoute select(State,const Failure&,const WorldSnapshot&) const=0; }; }
