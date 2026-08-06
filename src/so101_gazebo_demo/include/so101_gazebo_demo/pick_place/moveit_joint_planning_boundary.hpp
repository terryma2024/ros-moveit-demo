#pragma once

#include <chrono>
#include <cstddef>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <variant>
#include <vector>

#include <moveit_msgs/msg/robot_trajectory.hpp>
#include <moveit_msgs/action/move_group.hpp>
#include <sensor_msgs/msg/joint_state.hpp>

#include "so101_gazebo_demo/pick_place/so101_joint_motion_adapter.hpp"
#include "so101_gazebo_demo/pick_place/planning_failure_diagnostics.hpp"

namespace rclcpp
{
class Node;
}
namespace moveit::core
{
class RobotState;
}

namespace so101_gazebo_demo::pick_place
{

inline constexpr double kMicroLiftPositionToleranceM = 0.0002;
inline constexpr double kMicroLiftOrientationToleranceRad = 0.005;

[[nodiscard]] std::set<std::string> exactTaskObjectTouchWhitelist(const SO101Profile & profile);

[[nodiscard]] std::optional<Pose3d> updatedLinkPose(const moveit::core::RobotState & source,
                                                    const std::string & link_name);

[[nodiscard]] std::optional<Pose3d> updatedAttachedBodyPose(const moveit::core::RobotState & source,
                                                            const std::string & attached_body_name);

class IRequestScopedGoalCancellation
{
public:
  virtual ~IRequestScopedGoalCancellation() = default;
  virtual ActionResult requestCancel(double timeout_seconds) = 0;
  virtual std::optional<RequestScopedGoalTerminal> waitForTerminal(double timeout_seconds) = 0;
};

[[nodiscard]] ActionResult cancelRequestScopedGoalAndWait(IRequestScopedGoalCancellation & goal,
                                                          double cancel_ack_timeout_seconds,
                                                          double terminal_timeout_seconds);

/// Rebuilds an execution message solely from the artifact that passed runtime
/// validation. It never invokes MoveIt planning or target selection.
[[nodiscard]] std::optional<moveit_msgs::msg::RobotTrajectory>
executableTrajectoryFromValidatedArtifact(const MotionPlanArtifact & artifact,
                                          const std::vector<std::string> & expected_joint_names);

[[nodiscard]] std::optional<CurrentJointStateEvidence>
currentJointStateEvidenceFromMessage(const sensor_msgs::msg::JointState & message,
                                     const SO101Profile & profile,
                                     std::chrono::steady_clock::time_point received_at);

struct MoveItJointPlanningDiagnostics
{
  std::string simulation_session_id;
  std::string configuration_fingerprint;
  std::shared_ptr<IPlanningFailureDiagnosticsSink> sink;
};

struct MoveItJointPlanningBoundaryOptions
{
  std::string planner_id{"RRTConnectkConfigDefault"};
  double velocity_scaling{0.1};
  double acceleration_scaling{0.1};
  double state_timeout_seconds{2.0};
  std::optional<MoveItJointPlanningDiagnostics> diagnostics;
};

struct MicroLiftPlanningOutcome
{
  ActionResult action;
  std::optional<RequestScopedGoalTerminal> terminal;
  std::optional<std::int8_t> transport_result_code;
  std::shared_ptr<moveit_msgs::action::MoveGroup::Result> result;
  std::optional<PlanningFailureStage> failure_stage;
  std::optional<bool> cancel_acknowledged;
};

[[nodiscard]] ActionResult
classifyMicroLiftPlanningOutcome(const MicroLiftPlanningOutcome & outcome);

struct MicroLiftPlanningCapture
{
  moveit_msgs::action::MoveGroup::Goal request;
  moveit_msgs::msg::PlanningScene observed_scene;
  PlanningSceneContactEvidence contacts;
};

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
                                          public IRobotStateEvidenceProvider,
                                          public IWorldZMicroLift
{
public:
  MoveItJointPlanningBoundary(std::shared_ptr<rclcpp::Node> node,
                              SO101Profile profile = SO101Profile::canonical(),
                              std::string planner_id = "RRTConnectkConfigDefault",
                              double velocity_scaling = 0.1, double acceleration_scaling = 0.1,
                              double state_timeout_seconds = 2.0);
  MoveItJointPlanningBoundary(std::shared_ptr<rclcpp::Node> node, SO101Profile profile,
                              MoveItJointPlanningBoundaryOptions options);
  ~MoveItJointPlanningBoundary() override;

  std::optional<CurrentJointStateEvidence> currentState() override;
  std::optional<MotionPlanningSceneFacts> sceneFacts() override;
  JointSegmentPlanResult
  planSegment(const std::vector<std::string> & joint_names, const std::vector<double> & start,
              const std::vector<double> & goal, const std::set<std::string> & allowed_touch_pairs,
              const std::optional<TemporalContactPolicy> & temporal_contact_policy,
              double gripper_position, double velocity_scaling,
              double acceleration_scaling) override;
  ActionResult execute(const MotionPlanArtifact & artifact) override;
  ActionResult cancel() override;
  ActionResult executeWorldZMicroLift(const Pose3d & current_tcp_world,
                                      double world_z_delta_m) override;
  [[nodiscard]] std::variant<MicroLiftPlanningCapture, ActionResult>
  captureWorldZMicroLiftPlanningRequest(const Pose3d & current_tcp_world, double world_z_delta_m);
  ActionResult cancelWorldZMicroLift() override;
  ActionResult executeWorldZMicroDescend(const Pose3d & current_tcp_world,
                                         double target_world_z_m) override;
  [[nodiscard]] std::variant<MicroLiftPlanningCapture, ActionResult>
  captureWorldZMicroDescendPlanningRequest(const Pose3d & current_tcp_world,
                                           double target_world_z_m);
  ActionResult cancelWorldZMicroDescend() override;
  std::optional<RobotStateEvidence>
  evaluate(const std::vector<std::string> & joint_names,
           const std::vector<double> & joint_positions,
           const std::set<std::string> & allowed_touch_pairs,
           const std::optional<TemporalContactPolicy> & temporal_contact_policy,
           double gripper_position) const override;

  std::vector<CalibrationCandidate> search(const Vec3 & target_position, const Vec3 & local_axis,
                                           const Vec3 & target_axis, std::size_t seed_count = 4096,
                                           std::size_t result_count = 8,
                                           double gripper_q6 = 1.100000000);

private:
  [[nodiscard]] std::variant<MicroLiftPlanningCapture, ActionResult>
  captureWorldZPlanningRequest(const Pose3d & current_tcp_world, double target_world_z_m);
  ActionResult executeWorldZPlanningRequest(const Pose3d & current_tcp_world,
                                            double world_z_displacement_m, bool descend);
  class Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace so101_gazebo_demo::pick_place
