#pragma once

#include <cstddef>
#include <memory>
#include <string>

#include "so101_gazebo_demo/pick_place/world_observer.hpp"

namespace so101_gazebo_demo::pick_place
{

/// Enriches robot and Planning Scene observations with Gazebo's authoritative
/// TaskObject pose and DetachableJoint state. Missing or stale Gazebo data is an
/// observation failure; it is never silently replaced with Planning Scene data.
/// max_observation_age_seconds is also the bounded startup wait for the first
/// pose and durable attachment-state messages.
class GazeboWorldObserver final : public IWorldObserver
{
public:
  GazeboWorldObserver(IWorldObserver & moveit_observer, const std::string & world_name,
                      std::string task_object_id, const std::string & attachment_topic,
                      std::string simulation_session_id, std::string intended_support_collision,
                      double minimum_support_contact_depth_m, double max_observation_age_seconds,
                      std::size_t task_object_settle_samples,
                      double task_object_settle_interval_seconds,
                      double task_object_settle_position_tolerance,
                      double task_object_settle_orientation_tolerance_rad,
                      bool initially_detached = true);
  ~GazeboWorldObserver() override;

  [[nodiscard]] ObservationResult observe() override;

private:
  class Impl;
  IWorldObserver & moveit_observer_;
  std::unique_ptr<Impl> impl_;
};

}  // namespace so101_gazebo_demo::pick_place
