#pragma once

#include <cstddef>
#include <map>
#include <memory>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include "panda_gazebo_demo/pick_place/world_observer.hpp"

namespace panda_gazebo_demo::pick_place
{

struct PlanArtifact
{
  virtual ~PlanArtifact() = default;
  std::size_t trajectory_points{0};
};

struct PlanResult
{
  ActionResult action;
  std::shared_ptr<const PlanArtifact> artifact;
};

struct ExecutionContext
{
  State state;
  State next_state;
  WorldSnapshot before;
  std::shared_ptr<const PlanArtifact> plan;
};

class IStatePlanner
{
public:
  virtual ~IStatePlanner() = default;
  [[nodiscard]] virtual PlanResult plan(
    State current_state, State next_state,
    const ObservationResult & observation) = 0;
};

class IStateExecutor
{
public:
  virtual ~IStateExecutor() = default;
  [[nodiscard]] virtual ActionResult execute(const ExecutionContext & context) = 0;
  [[nodiscard]] virtual ActionResult cancel() = 0;
};

class StateActionRegistry
{
public:
  void registerPlanner(State state, std::shared_ptr<IStatePlanner> planner);
  void registerExecutor(State state, std::shared_ptr<IStateExecutor> executor);
  [[nodiscard]] IStatePlanner * findPlanner(State state) const noexcept;
  [[nodiscard]] IStateExecutor * findExecutor(State state) const noexcept;

private:
  std::map<State, std::shared_ptr<IStatePlanner>> planners_;
  std::map<State, std::shared_ptr<IStateExecutor>> executors_;
};

}  // namespace panda_gazebo_demo::pick_place
