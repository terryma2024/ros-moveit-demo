#pragma once

#include <memory>

#include "so101_gazebo_demo/pick_place/follow_joint_trajectory_gripper_adapter.hpp"
#include "so101_gazebo_demo/pick_place/so101_gripper_validation.hpp"
#include "so101_gazebo_demo/pick_place/state_action.hpp"
#include "so101_gazebo_demo/pick_place/transition_contract.hpp"

namespace so101_gazebo_demo::pick_place
{

enum class SO101GripperTarget
{
  PREOPEN,
  CONTACT,
  FULL_OPEN,
};

[[nodiscard]] ValidationResult
validateSO101GripperTarget(const WorldSnapshot & snapshot, SO101GripperTarget target,
                           const SO101Profile & profile = SO101Profile::canonical());

struct SO101GripperStateConfig
{
  State state;
  SO101GripperTarget target;
  bool no_op_if_at_target{false};
};

class SO101GripperStateExecutor final : public IStateExecutor
{
public:
  SO101GripperStateExecutor(std::shared_ptr<ISO101GripperCommand> command,
                            SO101GripperStateConfig config,
                            SO101Profile profile = SO101Profile::canonical(),
                            std::shared_ptr<IWorldObserver> observer = {});

  [[nodiscard]] ActionResult execute(const ExecutionContext & context) override;
  [[nodiscard]] ActionResult cancel() override;

private:
  std::shared_ptr<ISO101GripperCommand> command_;
  SO101GripperStateConfig config_;
  SO101Profile profile_;
  std::shared_ptr<IWorldObserver> observer_;
};

using SO101Contract = TransitionContractRegistry::ITransitionContract;

[[nodiscard]] std::shared_ptr<const SO101Contract>
makeSO101GripperContract(SO101GripperStateConfig config,
                         SO101Profile profile = SO101Profile::canonical());

}  // namespace so101_gazebo_demo::pick_place
