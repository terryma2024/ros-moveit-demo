#pragma once

#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include <rclcpp/node.hpp>

#include "so101_gazebo_demo/pick_place/so101_profile.hpp"
#include "so101_gazebo_demo/workspace/workspace_types.hpp"

namespace so101_gazebo_demo::workspace
{
using CollisionPairCounts = std::map<std::pair<std::string, std::string>, std::uint64_t>;
using CollisionPairSampleIds =
  std::map<std::pair<std::string, std::string>, std::vector<std::uint64_t>>;

struct WorkspaceEvaluatorBuildResult
{
  std::unique_ptr<class WorkspaceStateEvaluator> evaluator;
  std::optional<WorkspaceFailure> failure;
};

class WorkspaceStateEvaluator
{
public:
  static WorkspaceEvaluatorBuildResult create(const std::shared_ptr<rclcpp::Node> & node,
                                              const pick_place::SO101Profile & profile);
  ~WorkspaceStateEvaluator();
  WorkspaceStateEvaluator(WorkspaceStateEvaluator &&) noexcept;
  WorkspaceStateEvaluator & operator=(WorkspaceStateEvaluator &&) noexcept;
  WorkspaceStateEvaluator(const WorkspaceStateEvaluator &) = delete;
  WorkspaceStateEvaluator & operator=(const WorkspaceStateEvaluator &) = delete;

  PoseSample evaluate(std::uint64_t sample_id, const GeneratedJointSample & generated);
  const CollisionPairCounts & collisionPairCounts() const noexcept;
  const CollisionPairSampleIds & collisionPairSampleIds() const noexcept;
  std::vector<std::string> worldObjectIds() const;
  double gripperPreopen() const noexcept;

private:
  class Impl;
  explicit WorkspaceStateEvaluator(std::unique_ptr<Impl> impl);
  std::unique_ptr<Impl> impl_;
};
}  // namespace so101_gazebo_demo::workspace
