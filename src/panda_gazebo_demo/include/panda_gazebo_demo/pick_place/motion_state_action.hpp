#pragma once

#include <memory>

#include "panda_gazebo_demo/pick_place/moveit_motion_adapter.hpp"
#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"
#include "panda_gazebo_demo/pick_place/state_action.hpp"

namespace panda_gazebo_demo::pick_place
{

class MotionStateAction final : public IStatePlanner, public IStateExecutor
{
public:
  MotionStateAction(std::shared_ptr<IMoveItMotionAdapter> adapter,
                    std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
                    MotionStateConfig config);

  [[nodiscard]] PlanResult plan(State current_state, State next_state,
                                const ObservationResult & observation) override;
  [[nodiscard]] ActionResult execute(const ExecutionContext & context) override;
  [[nodiscard]] ActionResult cancel() override;

private:
  std::shared_ptr<IMoveItMotionAdapter> adapter_;
  std::shared_ptr<const PickPlaceTargetPolicy> target_policy_;
  MotionStateConfig config_;
};

}  // namespace panda_gazebo_demo::pick_place
