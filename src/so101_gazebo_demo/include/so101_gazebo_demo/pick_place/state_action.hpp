#pragma once
#include <map>
#include <memory>
#include "so101_gazebo_demo/pick_place/world_observer.hpp"
namespace so101_gazebo_demo::pick_place {
struct PlanArtifact { virtual ~PlanArtifact()=default; std::size_t trajectory_points{0}; };
struct PlanResult { ActionResult action; std::shared_ptr<const PlanArtifact> artifact; };
struct ExecutionContext { State state; State next_state; WorldSnapshot before; std::shared_ptr<const PlanArtifact> plan; };
class IStatePlanner { public: virtual ~IStatePlanner()=default; virtual PlanResult plan(State,State,const ObservationResult&)=0; };
class IStateExecutor { public: virtual ~IStateExecutor()=default; virtual ActionResult execute(const ExecutionContext&)=0; virtual ActionResult cancel()=0; };
class StateActionRegistry { public: void registerPlanner(State,std::shared_ptr<IStatePlanner>); void registerExecutor(State,std::shared_ptr<IStateExecutor>); IStatePlanner * findPlanner(State) const noexcept; IStateExecutor * findExecutor(State) const noexcept; private: std::map<State,std::shared_ptr<IStatePlanner>> planners_; std::map<State,std::shared_ptr<IStateExecutor>> executors_; };
}  // namespace so101_gazebo_demo::pick_place
