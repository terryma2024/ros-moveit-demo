#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "so101_gazebo_demo/pick_place/so101_motion_evidence_builder.hpp"
#include "so101_gazebo_demo/pick_place/so101_motion_planner.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

namespace so101_gazebo_demo::pick_place
{

struct CurrentJointStateEvidence
{
  std::vector<std::string> joint_names;
  std::vector<double> positions;
  std::uint64_t observed_stamp_nanoseconds{0};
};

struct MotionPlanningSceneFacts
{
  bool table_in_world{false};
  bool coke_in_world{false};
  bool coke_attached{false};
  std::optional<std::string> attached_link;
  std::set<std::string> touch_links;
};

struct JointSegmentPlan
{
  std::vector<std::string> joint_names;
  std::vector<TrajectoryPointEvidenceInput> points;
  bool moveit_success{false};
  int moveit_error_code{0};
  std::string planner_id;
  bool collision_aware{false};
};

struct JointSegmentPlanResult
{
  ActionResult action;
  std::optional<JointSegmentPlan> segment;
};

class IJointPlanningBoundary
{
public:
  virtual ~IJointPlanningBoundary() = default;
  [[nodiscard]] virtual std::optional<CurrentJointStateEvidence> currentState() = 0;
  [[nodiscard]] virtual std::optional<MotionPlanningSceneFacts> sceneFacts() = 0;
  [[nodiscard]] virtual JointSegmentPlanResult
  planSegment(const std::vector<std::string> & joint_names,
              const std::vector<double> & start, const std::vector<double> & goal) = 0;
  [[nodiscard]] virtual ActionResult execute(const MotionPlanArtifact &)
  {
    return {ActionStatus::NOT_SUPPORTED,
            Failure{FailureCategory::EXECUTION, "MOTION_EXECUTION_NOT_IMPLEMENTED",
                    "Joint planning boundary does not implement execution", {}}};
  }
  [[nodiscard]] virtual ActionResult cancel()
  {
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }
};

class ProfiledJointMotionAdapter final : public IMoveItJointMotionAdapter
{
public:
  ProfiledJointMotionAdapter(std::shared_ptr<IJointPlanningBoundary> boundary,
                             std::shared_ptr<const IRobotStateEvidenceProvider> evaluator,
                             SO101Profile profile = SO101Profile::canonical());
  PlanResult plan(const JointMotionRequest & request,
                  const ObservationResult & observation) override;
  ActionResult execute(const MotionPlanArtifact & artifact) override;
  ActionResult cancel() override;

private:
  std::shared_ptr<IJointPlanningBoundary> boundary_;
  std::shared_ptr<const IRobotStateEvidenceProvider> evaluator_;
  SO101Profile profile_;
};

}  // namespace so101_gazebo_demo::pick_place
