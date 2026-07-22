#pragma once

#include <cstddef>
#include <memory>
#include <vector>

#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"
#include "panda_gazebo_demo/pick_place/plan_validation.hpp"

namespace panda_gazebo_demo::pick_place
{

enum class MotionKind
{
  POSE,
  CARTESIAN_UP,
  CARTESIAN_DOWN,
};

struct MotionStateConfig
{
  State state;
  State next_state;
  MotionKind kind;
  bool carrying;
};

struct MotionPlanEvidence : PlanArtifact
{
  State state{State::ERROR};
  State next_state{State::ERROR};
  MotionKind kind{MotionKind::POSE};
  bool carrying{false};
  double cartesian_fraction{1.0};
  double duration_seconds{0.0};
  double max_joint_jump{0.0};
  Pose3d start_tcp_pose;
  Pose3d end_tcp_pose;
  std::vector<Pose3d> tcp_path;
  bool collision_aware{false};
  bool attached_object_in_model{false};
  bool carried_relative_pose_available{false};
  double max_carried_relative_position_error{0.0};
  double max_carried_relative_orientation_error_rad{0.0};
  bool carried_clearance_verified{false};
};

struct MotionPlanLimits
{
  double min_cartesian_fraction{0.99};
  double max_joint_jump{0.2};
  double max_lateral_deviation{0.02};
  double max_orientation_error_rad{0.1};
  double endpoint_position_tolerance{0.02};
  double endpoint_orientation_tolerance_rad{0.1};
  double carried_relative_position_tolerance{0.003};
  double carried_relative_orientation_tolerance_rad{0.035};
};

[[nodiscard]] ValidationResult validateMotionPlan(
  const MotionPlanEvidence & evidence, const Pose3d & target,
  MotionKind expected_kind, bool expected_carrying,
  const MotionPlanLimits & limits);

class MotionPlanValidator final : public IPlanValidator
{
public:
  MotionPlanValidator(
    MotionStateConfig config,
    std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
    MotionPlanLimits limits = {});

  [[nodiscard]] ValidationResult validate(
    State state, const WorldSnapshot & before,
    const PlanArtifact & artifact) const override;

private:
  MotionStateConfig config_;
  std::shared_ptr<const PickPlaceTargetPolicy> target_policy_;
  MotionPlanLimits limits_;
};

}  // namespace panda_gazebo_demo::pick_place
