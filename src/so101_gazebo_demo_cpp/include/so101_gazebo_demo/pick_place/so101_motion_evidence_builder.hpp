#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "so101_gazebo_demo/pick_place/so101_motion_validation.hpp"

namespace so101_gazebo_demo::pick_place
{

struct TrajectoryPointEvidenceInput
{
  std::vector<double> joint_positions;
  double time_from_start_seconds{0.0};
};

struct TrajectoryEvidenceInput
{
  std::vector<std::string> joint_names;
  std::vector<double> current_joint_snapshot;
  std::vector<TrajectoryPointEvidenceInput> points;
  bool moveit_success{false};
  int moveit_error_code{0};
  std::string planner_id;
  std::uint64_t start_state_stamp_nanoseconds{0};
  bool collision_aware_planner{false};
  std::set<std::string> allowed_touch_pairs;
  double gripper_position{0.0};
  std::optional<TemporalContactPolicy> temporal_contact_policy;
};

struct RobotStateEvidence
{
  Pose3d tcp_pose;
  bool collision_free{false};
  std::set<std::string> raw_contact_pairs;
  std::optional<Pose3d> attached_task_object_pose_world;
};

class IRobotStateEvidenceProvider
{
public:
  virtual ~IRobotStateEvidenceProvider() = default;
  [[nodiscard]] virtual std::optional<RobotStateEvidence>
  evaluate(const std::vector<std::string> & joint_names,
           const std::vector<double> & joint_positions,
           const std::set<std::string> & allowed_touch_pairs,
           const std::optional<TemporalContactPolicy> & temporal_contact_policy,
           double gripper_position) const = 0;
};

struct MotionEvidenceBuildResult
{
  std::shared_ptr<MotionPlanArtifact> artifact;
  std::optional<Failure> failure;
};

[[nodiscard]] MotionEvidenceBuildResult
buildMotionPlanEvidence(const TrajectoryEvidenceInput & input,
                        const IRobotStateEvidenceProvider & evaluator);

}  // namespace so101_gazebo_demo::pick_place
