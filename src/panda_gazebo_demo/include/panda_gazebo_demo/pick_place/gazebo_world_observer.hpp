#pragma once

#include <cstddef>
#include <memory>
#include <string>

#include "panda_gazebo_demo/pick_place/world_observer.hpp"

namespace panda_gazebo_demo::pick_place
{

/// Enriches robot and Planning Scene observations with Gazebo's authoritative
/// Coke pose and DetachableJoint state. Missing or stale Gazebo data is an
/// observation failure; it is never silently replaced with Planning Scene data.
class GazeboWorldObserver final : public IWorldObserver
{
public:
  GazeboWorldObserver(
    IWorldObserver & moveit_observer, std::string world_name, std::string coke_model,
    std::string attachment_topic, std::string simulation_session_id,
    double max_observation_age_seconds, std::size_t coke_settle_samples,
    double coke_settle_interval_seconds, double coke_settle_position_tolerance,
    double coke_settle_orientation_tolerance_rad, bool initially_detached);
  ~GazeboWorldObserver() override;

  [[nodiscard]] ObservationResult observe() override;

private:
  class Impl;
  IWorldObserver & moveit_observer_;
  std::unique_ptr<Impl> impl_;
};

}  // namespace panda_gazebo_demo::pick_place
