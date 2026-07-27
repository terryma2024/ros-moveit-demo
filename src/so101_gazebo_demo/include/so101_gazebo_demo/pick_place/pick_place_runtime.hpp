#pragma once

#include <cstddef>
#include <memory>
#include <optional>

#include "so101_gazebo_demo/pick_place/plan_validation.hpp"
#include "so101_gazebo_demo/pick_place/so101_fixed_motion_targets.hpp"
#include "so101_gazebo_demo/pick_place/so101_joint_motion_adapter.hpp"
#include "so101_gazebo_demo/pick_place/so101_task3_runtime.hpp"

namespace so101_gazebo_demo::pick_place
{

struct SO101WorldObservationConfig
{
  double max_age_seconds{0.5};
  std::size_t settle_samples{3};
  double settle_interval_seconds{0.05};
  double joint_settle_tolerance{0.001};
};

/// Produces the robot and MoveIt half of a complete world observation. The
/// GazeboWorldObserver enriches this snapshot with independent Gazebo facts and
/// the simulation-session identity.
class SO101MoveItWorldObserver final : public IWorldObserver
{
public:
  SO101MoveItWorldObserver(
    std::shared_ptr<IJointPlanningBoundary> boundary,
    SO101Profile profile = SO101Profile::canonical(),
    SO101WorldObservationConfig config = {});

  [[nodiscard]] ObservationResult observe() override;

private:
  std::shared_ptr<IJointPlanningBoundary> boundary_;
  SO101Profile profile_;
  SO101WorldObservationConfig config_;
};

struct SO101PickPlaceRuntimeDependencies : SO101Task3RuntimeDependencies
{
  std::shared_ptr<const SO101FixedMotionTargetPolicy> motion_policy;
  std::shared_ptr<IMoveItJointMotionAdapter> motion;
};

struct SO101PickPlaceRuntimeConfig : SO101Task3RuntimeConfig
{
};

struct SO101PickPlaceRuntimeRegistries
{
  StateActionRegistry actions;
  PlanValidatorRegistry plan_validators;
  TransitionContractRegistry contracts;
  std::shared_ptr<const IRecoveryPolicy> recovery_policy;
  bool execution_safe{false};
  std::optional<Failure> configuration_failure;
};

[[nodiscard]] std::shared_ptr<const TransitionContractRegistry::ITransitionContract>
makeSO101MotionContract(
  const SO101FixedMotionSpec & spec,
  SO101Profile profile = SO101Profile::canonical());

[[nodiscard]] SO101PickPlaceRuntimeRegistries makeSO101PickPlaceRuntimeRegistries(
  const SO101PickPlaceRuntimeDependencies & dependencies,
  SO101PickPlaceRuntimeConfig config = {});

}  // namespace so101_gazebo_demo::pick_place
