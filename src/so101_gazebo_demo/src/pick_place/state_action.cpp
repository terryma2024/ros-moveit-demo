#include "so101_gazebo_demo/pick_place/state_action.hpp"
#include <stdexcept>
namespace so101_gazebo_demo::pick_place {
void StateActionRegistry::registerPlanner(State s,std::shared_ptr<IStatePlanner> p){ if(!p) throw std::invalid_argument("null planner"); if(planners_.count(s)) throw std::logic_error("duplicate planner"); planners_.emplace(s,std::move(p)); }
void StateActionRegistry::registerExecutor(State s,std::shared_ptr<IStateExecutor> e){ if(!e) throw std::invalid_argument("null executor"); if(executors_.count(s)) throw std::logic_error("duplicate executor"); executors_.emplace(s,std::move(e)); }
IStatePlanner* StateActionRegistry::findPlanner(State s)const noexcept{auto i=planners_.find(s);return i==planners_.end()?nullptr:i->second.get();} IStateExecutor* StateActionRegistry::findExecutor(State s)const noexcept{auto i=executors_.find(s);return i==executors_.end()?nullptr:i->second.get();} }
