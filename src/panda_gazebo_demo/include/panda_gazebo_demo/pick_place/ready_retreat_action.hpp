#pragma once

#include <map>
#include <memory>
#include <string>

#include "panda_gazebo_demo/pick_place/gripper_command_adapter.hpp"
#include "panda_gazebo_demo/pick_place/moveit_motion_adapter.hpp"
#include "panda_gazebo_demo/pick_place/named_target_validation.hpp"
#include "panda_gazebo_demo/pick_place/state_action.hpp"

namespace panda_gazebo_demo::pick_place
{

struct ReadyRetreatConfig
{
  State state;
  State next_state;
  std::string named_target;
  std::map<std::string, double> ready_joint_positions;
  double joint_tolerance;
  double close_position;
  double max_effort;
  double clearance_height;
};

class ReadyRetreatAction final : public IStatePlanner, public IStateExecutor
{
public:
  ReadyRetreatAction(std::shared_ptr<IMoveItMotionAdapter> motion,
                     std::shared_ptr<IGripperCommandAdapter> gripper,
                     std::shared_ptr<IWorldObserver> observer, ReadyRetreatConfig config);

  [[nodiscard]] PlanResult plan(State current_state, State next_state,
                                const ObservationResult & observation) override;
  [[nodiscard]] ActionResult execute(const ExecutionContext & context) override;
  [[nodiscard]] ActionResult cancel() override;

private:
  std::shared_ptr<IMoveItMotionAdapter> motion_;
  std::shared_ptr<IGripperCommandAdapter> gripper_;
  std::shared_ptr<IWorldObserver> observer_;
  ReadyRetreatConfig config_;
};

}  // namespace panda_gazebo_demo::pick_place
