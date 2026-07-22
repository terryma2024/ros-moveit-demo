#include "panda_gazebo_demo/pick_place/state_action.hpp"

namespace panda_gazebo_demo::pick_place
{

void StateActionRegistry::registerPlanner(State state, std::shared_ptr<IStatePlanner> planner)
{
  planners_[state] = std::move(planner);
}

void StateActionRegistry::registerExecutor(State state, std::shared_ptr<IStateExecutor> executor)
{
  executors_[state] = std::move(executor);
}

IStatePlanner * StateActionRegistry::findPlanner(State state) const noexcept
{
  const auto planner = planners_.find(state);
  return planner == planners_.end() ? nullptr : planner->second.get();
}

IStateExecutor * StateActionRegistry::findExecutor(State state) const noexcept
{
  const auto executor = executors_.find(state);
  return executor == executors_.end() ? nullptr : executor->second.get();
}

}  // namespace panda_gazebo_demo::pick_place
