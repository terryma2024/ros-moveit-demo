#pragma once

#include <cstdint>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "so101_gazebo_demo/pick_place/plan_validation.hpp"

namespace so101_gazebo_demo::pick_place
{

struct Vec3
{
  double x{0.0};
  double y{0.0};
  double z{0.0};
};

enum class TemporalContactLocation
{
  FIRST_ONLY,
  LAST_ONLY,
  PREFIX_UNTIL_AXIAL_CLEARANCE
};

struct TemporalContactPolicy
{
  std::set<std::string> allowed_pairs;
  TemporalContactLocation location{TemporalContactLocation::FIRST_ONLY};
  double max_axial_clearance_m{0.0};
};

[[nodiscard]] bool operator==(const TemporalContactPolicy & first,
                              const TemporalContactPolicy & second) noexcept;

struct MotionPlanSample
{
  Pose3d tcp_pose{};
  std::vector<double> joint_positions;
  double time_from_start_seconds{0.0};
  bool collision_free{false};
  std::set<std::string> raw_contact_pairs;
};

struct MotionPlanArtifact : PlanArtifact
{
  std::vector<std::string> joint_names;
  std::vector<double> start_joint_positions;
  std::vector<double> goal_joint_positions;
  std::vector<MotionPlanSample> samples;
  bool collision_aware{false};
  bool time_parameterized{false};
  bool moveit_success{false};
  int moveit_error_code{0};
  std::string planner_id;
  std::uint64_t start_state_stamp_nanoseconds{0};
  std::vector<double> current_joint_snapshot;
  // Raw contacts are measured with no world-object touch exemption.  The
  // allowed set is the exact, state-scoped exception used for this artifact.
  std::set<std::string> allowed_touch_pairs;
  std::set<std::string> raw_contact_pairs;
  std::optional<TemporalContactPolicy> temporal_contact_policy;
};

struct MotionValidationConfig
{
  std::vector<std::string> expected_joint_names;
  Vec3 endpoint_position{};
  Vec3 local_approach_axis{0.0, 0.0, -1.0};
  Vec3 target_approach_axis{0.0, 0.0, -1.0};
  Vec3 path_direction{0.0, 0.0, -1.0};
  double position_tolerance{0.005};
  double axis_tolerance_rad{0.08726646259971647};
  double max_lateral_deviation{0.005};
  double max_joint_jump{0.15};
  double joint_endpoint_tolerance{1e-4};
  double min_duration_seconds{0.1};
  double monotonic_tolerance{1e-5};
  std::set<std::string> allowed_touch_pairs;
  std::optional<TemporalContactPolicy> temporal_contact_policy;
};

// Returns +infinity when either axis or the quaternion is zero/non-finite.
[[nodiscard]] double approachAxisError(const Pose3d & pose, const Vec3 & local_axis,
                                       const Vec3 & target_axis) noexcept;

[[nodiscard]] ValidationResult validateJointGoalPlan(const MotionPlanArtifact & plan,
                                                     const MotionValidationConfig & config);

[[nodiscard]] ValidationResult validateWaypointLadder(const MotionPlanArtifact & plan,
                                                      const MotionValidationConfig & config);

class SO101MotionPlanValidator final : public IPlanValidator
{
public:
  SO101MotionPlanValidator(MotionValidationConfig config, bool require_ladder);
  ValidationResult validate(State, const WorldSnapshot &, const PlanArtifact &) const override;

private:
  MotionValidationConfig config_;
  bool require_ladder_{false};
};

}  // namespace so101_gazebo_demo::pick_place
