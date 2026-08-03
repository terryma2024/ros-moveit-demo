#pragma once

#include <memory>
#include <optional>
#include <set>
#include <vector>

#include "so101_gazebo_demo/pick_place/so101_motion_validation.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

namespace so101_gazebo_demo::pick_place
{

struct JointMotionTarget
{
  std::vector<std::string> joint_names;
  std::vector<std::vector<double>> joint_waypoints;
  bool ladder{false};
  double gripper_position{0.0};
  std::optional<TemporalContactPolicy> temporal_contact_policy;
  double velocity_scaling{0.1};
  double acceleration_scaling{0.1};
};

struct JointMotionTargetResult
{
  std::optional<JointMotionTarget> target;
  std::optional<Failure> failure;
};

class IJointMotionTargetPolicy
{
public:
  virtual ~IJointMotionTargetPolicy() = default;
  [[nodiscard]] virtual JointMotionTargetResult
  target(State state, State next_state, const ObservationResult & observation) const = 0;
};

struct JointMotionRequest
{
  State state{State::ERROR};
  State next_state{State::ERROR};
  std::vector<std::string> joint_names;
  std::vector<std::vector<double>> joint_waypoints;
  bool ladder{false};
  bool carrying{false};
  std::set<std::string> allowed_touch_pairs;
  double gripper_position{0.0};
  std::optional<TemporalContactPolicy> temporal_contact_policy;
  double velocity_scaling{0.1};
  double acceleration_scaling{0.1};
};

class IMoveItJointMotionAdapter
{
public:
  virtual ~IMoveItJointMotionAdapter() = default;
  [[nodiscard]] virtual PlanResult plan(const JointMotionRequest & request,
                                        const ObservationResult & observation) = 0;
  [[nodiscard]] virtual ActionResult execute(const MotionPlanArtifact & artifact) = 0;
  [[nodiscard]] virtual ActionResult cancel() = 0;
};

[[nodiscard]] bool isCarryingMotionState(State state) noexcept;

class SO101MotionPlanner final : public IStatePlanner
{
public:
  SO101MotionPlanner(std::shared_ptr<const IJointMotionTargetPolicy> policy,
                     std::shared_ptr<IMoveItJointMotionAdapter> adapter,
                     SO101Profile profile = SO101Profile::canonical());
  PlanResult plan(State state, State next_state, const ObservationResult & observation) override;

private:
  std::shared_ptr<const IJointMotionTargetPolicy> policy_;
  std::shared_ptr<IMoveItJointMotionAdapter> adapter_;
  SO101Profile profile_;
};

}  // namespace so101_gazebo_demo::pick_place
