#pragma once
#include <memory>
#include <map>
#include "so101_gazebo_demo/pick_place/domain_types.hpp"
namespace so101_gazebo_demo::pick_place
{
struct PlanArtifact { virtual ~PlanArtifact() = default; std::size_t trajectory_points{0}; };
struct PlanResult { ActionResult action; std::shared_ptr<const PlanArtifact> artifact; };
class IStatePlanner { public: virtual ~IStatePlanner() = default; };
class IStateExecutor { public: virtual ~IStateExecutor() = default; };
class StateActionRegistry { public: void registerPlanner(State, std::shared_ptr<IStatePlanner>);
  void registerExecutor(State, std::shared_ptr<IStateExecutor>); private:
  std::map<State, std::shared_ptr<IStatePlanner>> planners_; std::map<State, std::shared_ptr<IStateExecutor>> executors_; };
}  // namespace so101_gazebo_demo::pick_place
