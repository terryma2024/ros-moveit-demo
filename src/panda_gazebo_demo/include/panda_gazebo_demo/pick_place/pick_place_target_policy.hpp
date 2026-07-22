#pragma once

#include <optional>
#include <string>

#include "panda_gazebo_demo/pick_place/world_observer.hpp"

namespace panda_gazebo_demo::pick_place
{

struct TargetPoseResult
{
  std::optional<Pose3d> target_pose;
  std::optional<Failure> failure;
};

class PickPlaceTargetPolicy
{
public:
  virtual ~PickPlaceTargetPolicy() = default;

  [[nodiscard]] virtual TargetPoseResult targetPose(
    State current_state, State next_state,
    const ObservationResult & observation) const = 0;
  [[nodiscard]] virtual std::string configurationSignature() const = 0;
};

class FixedPickPlaceTargetPolicy final : public PickPlaceTargetPolicy
{
public:
  [[nodiscard]] TargetPoseResult targetPose(
    State current_state, State next_state,
    const ObservationResult & observation) const override;
  [[nodiscard]] std::string configurationSignature() const override;
};

}  // namespace panda_gazebo_demo::pick_place
