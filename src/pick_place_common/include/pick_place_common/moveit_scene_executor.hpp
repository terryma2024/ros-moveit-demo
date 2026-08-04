#pragma once

#include <condition_variable>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

#include "pick_place_common/state_action.hpp"

namespace pick_place_common::ros_adapters
{
enum class MoveItSceneOperation
{
  ATTACH,
  DETACH,
  SYNC
};

struct MoveItAttachmentSpec
{
  std::string link_name;
  std::vector<std::string> touch_links;
};

struct MoveItSceneState
{
  bool task_object_in_world{false};
  bool task_object_attached{false};
  std::string attached_link;
  std::vector<std::string> touch_links;
  std::optional<Pose3d> task_object_world_pose;
  bool table_in_world{false};
  std::optional<Pose3d> table_world_pose;
  bool pedestal_in_world{false};
  std::optional<Pose3d> pedestal_world_pose;
};

class IMoveItSceneAdapter
{
public:
  virtual ~IMoveItSceneAdapter() = default;
  [[nodiscard]] virtual ActionResult attachTaskObject(const MoveItAttachmentSpec & spec) = 0;
  [[nodiscard]] virtual ActionResult detachTaskObject() = 0;
  [[nodiscard]] virtual ActionResult upsertTaskObjectWorldPose(const Pose3d & pose) = 0;
  [[nodiscard]] virtual std::optional<MoveItSceneState> observe() = 0;
};

struct ScenePreparation
{
  bool skip_command{false};
  bool upsert_before_attach{false};
  std::optional<Pose3d> task_object_pose;
  std::optional<ActionResult> failure;
};

class IMoveItScenePolicy
{
public:
  virtual ~IMoveItScenePolicy() = default;
  [[nodiscard]] virtual ScenePreparation prepare(MoveItSceneOperation operation,
                                                 const ExecutionContext & context) const = 0;
};

struct MoveItSceneConfig
{
  State state;
  MoveItSceneOperation operation;
  bool idempotent{false};
  std::string task_object_id;
  MoveItAttachmentSpec attachment;
  double timeout_seconds{2.0};
  double poll_interval_seconds{0.05};
};

class MoveItSceneExecutor final : public IStateExecutor
{
public:
  MoveItSceneExecutor(std::shared_ptr<IMoveItSceneAdapter> adapter, MoveItSceneConfig config,
                      std::shared_ptr<const IMoveItScenePolicy> policy);

  [[nodiscard]] ActionResult execute(const ExecutionContext & context) override;
  [[nodiscard]] ActionResult cancel() override;

private:
  [[nodiscard]] ActionResult waitForConvergence(const std::optional<Pose3d> & pose);

  std::shared_ptr<IMoveItSceneAdapter> adapter_;
  MoveItSceneConfig config_;
  std::shared_ptr<const IMoveItScenePolicy> policy_;
  std::mutex mutex_;
  std::condition_variable condition_;
  bool cancel_requested_{false};
};
}  // namespace pick_place_common::ros_adapters
