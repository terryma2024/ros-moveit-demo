#pragma once

#include <condition_variable>
#include <memory>
#include <mutex>
#include <optional>

#include "so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp"
#include "so101_gazebo_demo/pick_place/state_action.hpp"

namespace so101_gazebo_demo::pick_place
{

enum class MoveItSceneOperation
{
  ATTACH,
  DETACH,
  SYNC,
};

struct MoveItSceneConfig
{
  State state;
  MoveItSceneOperation operation;
  bool idempotent{false};
};

class MoveItSceneExecutor final : public IStateExecutor
{
public:
  MoveItSceneExecutor(std::shared_ptr<IMoveItSceneAdapter> adapter, MoveItSceneConfig config,
                      MoveItAttachmentSpec attachment, double timeout_seconds = 2.0,
                      double poll_interval_seconds = 0.05);

  [[nodiscard]] ActionResult execute(const ExecutionContext & context) override;
  [[nodiscard]] ActionResult cancel() override;

private:
  [[nodiscard]] ActionResult waitForConvergence(const std::optional<Pose3d> & pose);

  std::shared_ptr<IMoveItSceneAdapter> adapter_;
  MoveItSceneConfig config_;
  MoveItAttachmentSpec attachment_;
  double timeout_seconds_;
  double poll_interval_seconds_;
  std::mutex mutex_;
  std::condition_variable condition_;
  bool cancel_requested_{false};
};

}  // namespace so101_gazebo_demo::pick_place
