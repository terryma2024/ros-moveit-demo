#pragma once

#include <memory>

#include "panda_gazebo_demo/pick_place/gripper_command_adapter.hpp"
#include "panda_gazebo_demo/pick_place/state_action.hpp"
#include "panda_gazebo_demo/pick_place/state_validation.hpp"

namespace panda_gazebo_demo::pick_place
{

struct GripperStateConfig
{
  State state;
  double target_position;
  double max_effort;
  bool no_op_if_already_open{false};
};

class GripperStateExecutor final : public IStateExecutor
{
public:
  GripperStateExecutor(
    std::shared_ptr<IGripperCommandAdapter> adapter, GripperStateConfig config,
    GripperLimits limits = {});

  [[nodiscard]] ActionResult execute(const ExecutionContext & context) override;
  [[nodiscard]] ActionResult cancel() override;

private:
  std::shared_ptr<IGripperCommandAdapter> adapter_;
  GripperStateConfig config_;
  GripperLimits limits_;
};

}  // namespace panda_gazebo_demo::pick_place
