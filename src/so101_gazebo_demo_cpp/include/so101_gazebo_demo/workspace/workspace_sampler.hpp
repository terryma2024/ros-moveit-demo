#pragma once

#include <chrono>
#include <functional>

#include "so101_gazebo_demo/workspace/workspace_checkpoint_store.hpp"
#include "so101_gazebo_demo/workspace/workspace_state_evaluator.hpp"

namespace so101_gazebo_demo::workspace
{
struct RunControl
{
  std::function<std::chrono::steady_clock::time_point()> now;
  std::function<bool()> stop_requested;
};

class WorkspaceSampler
{
public:
  WorkspaceSampler(WorkspaceSamplingConfig config, JointSampleGenerator generator,
                   WorkspaceStateEvaluator & evaluator, PoseCoverageIndex coverage,
                   WorkspaceArtifactWriter & writer, WorkspaceCheckpointStore & checkpoint_store);
  RunSummary run(const RunControl & control);

private:
  WorkspaceSamplingConfig config_;
  JointSampleGenerator generator_;
  WorkspaceStateEvaluator & evaluator_;
  PoseCoverageIndex coverage_;
  WorkspaceArtifactWriter & writer_;
  WorkspaceCheckpointStore & checkpoint_store_;
};
}  // namespace so101_gazebo_demo::workspace
