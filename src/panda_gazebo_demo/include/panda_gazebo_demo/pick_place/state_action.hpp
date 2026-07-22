#pragma once

#include <cstddef>
#include <map>
#include <memory>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"

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

class IStatePlanner
{
public:
  virtual ~IStatePlanner() = default;
  [[nodiscard]] virtual PlanResult plan(State state) = 0;
};

class IStateExecutor
{
public:
  virtual ~IStateExecutor() = default;
  [[nodiscard]] virtual ActionResult execute(
    State state, std::shared_ptr<const PlanArtifact> plan) = 0;
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
