#pragma once

#include <cstddef>
#include <memory>
#include <vector>

#include "so101_gazebo_demo/pick_place/so101_joint_motion_adapter.hpp"

namespace rclcpp { class Node; }
namespace moveit::core { class RobotState; }

namespace so101_gazebo_demo::pick_place
{

[[nodiscard]] std::optional<Pose3d>
updatedLinkPose(const moveit::core::RobotState & source, const std::string & link_name);

struct CalibrationCandidate
{
  std::vector<double> joints;
  Pose3d tcp_pose;
  double position_error{0.0};
  double axis_error{0.0};
  bool collision_free{false};
  double minimum_distance{0.0};
  std::vector<std::string> collision_pairs;
};

class MoveItJointPlanningBoundary final : public IJointPlanningBoundary,
                                           public IRobotStateEvidenceProvider
{
public:
  MoveItJointPlanningBoundary(std::shared_ptr<rclcpp::Node> node,
                              SO101Profile profile = SO101Profile::canonical(),
                              std::string planner_id = "RRTConnectkConfigDefault",
                              double velocity_scaling = 0.1,
                              double acceleration_scaling = 0.1,
                              double state_timeout_seconds = 2.0);
  ~MoveItJointPlanningBoundary() override;

  std::optional<CurrentJointStateEvidence> currentState() override;
  std::optional<MotionPlanningSceneFacts> sceneFacts() override;
  JointSegmentPlanResult planSegment(const std::vector<std::string> & joint_names,
                                     const std::vector<double> & start,
                                     const std::vector<double> & goal,
                                     const std::set<std::string> & allowed_touch_pairs,
                                     const std::optional<TemporalContactPolicy> & temporal_contact_policy,
                                     double gripper_position) override;
  std::optional<RobotStateEvidence>
  evaluate(const std::vector<std::string> & joint_names,
           const std::vector<double> & joint_positions,
           const std::set<std::string> & allowed_touch_pairs,
           const std::optional<TemporalContactPolicy> & temporal_contact_policy,
           double gripper_position) const override;

  std::vector<CalibrationCandidate>
  search(const Vec3 & target_position, const Vec3 & local_axis, const Vec3 & target_axis,
         std::size_t seed_count = 4096, std::size_t result_count = 8,
         double gripper_q6 = 0.707194871);

private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace so101_gazebo_demo::pick_place
