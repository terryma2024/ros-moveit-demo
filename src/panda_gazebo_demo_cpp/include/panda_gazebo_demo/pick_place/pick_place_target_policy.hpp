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

  [[nodiscard]] virtual TargetPoseResult
  targetPose(State current_state, State next_state,
             const ObservationResult & observation) const = 0;
  [[nodiscard]] virtual std::string configurationSignature() const = 0;
};

class FixedPickPlaceTargetPolicy final : public PickPlaceTargetPolicy
{
public:
  static constexpr double kCanonicalSafeHeight = 0.987;
  static constexpr double kSupportedCokeCenterOffsetZ = -0.034;

  explicit FixedPickPlaceTargetPolicy(double recovery_safe_height = kCanonicalSafeHeight);

  [[nodiscard]] TargetPoseResult targetPose(State current_state, State next_state,
                                            const ObservationResult & observation) const override;
  [[nodiscard]] std::string configurationSignature() const override;

private:
  double recovery_safe_height_;
};

[[nodiscard]] TargetPoseResult supportedCokePose(const PickPlaceTargetPolicy & target_policy,
                                                 State current_state, State next_state,
                                                 const ObservationResult & observation);
[[nodiscard]] Pose3d supportedCokePoseFromTcp(const Pose3d & tcp_pose);

}  // namespace panda_gazebo_demo::pick_place
