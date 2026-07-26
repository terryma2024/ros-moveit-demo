#pragma once
#include <map>
#include <memory>
#include "so101_gazebo_demo/pick_place/plan_validation.hpp"
namespace so101_gazebo_demo::pick_place {
struct TransitionKey { State from; State to; friend bool operator<(const TransitionKey&a,const TransitionKey&b) noexcept { return a.from!=b.from?a.from<b.from:a.to<b.to; } };
class TransitionContractRegistry { public: class ITransitionContract { public: virtual ~ITransitionContract()=default; virtual ValidationResult validatePrecondition(const WorldSnapshot&) const=0; virtual ValidationResult validate(const WorldSnapshot&,const WorldSnapshot&,const ActionResult&) const=0; }; void registerContract(TransitionKey,std::shared_ptr<const ITransitionContract>); bool hasContract(TransitionKey) const noexcept; ValidationResult validatePrecondition(TransitionKey,const WorldSnapshot&) const; ValidationResult validate(TransitionKey,const WorldSnapshot&,const WorldSnapshot&,const ActionResult&) const; ValidationResult validateResume(TransitionKey,const WorldSnapshot&,const WorldSnapshot&) const; private: std::map<TransitionKey,std::shared_ptr<const ITransitionContract>> contracts_; };
class AlwaysPassValidator final: public TransitionContractRegistry::ITransitionContract { public: ValidationResult validatePrecondition(const WorldSnapshot&) const override; ValidationResult validate(const WorldSnapshot&,const WorldSnapshot&,const ActionResult&) const override; };
}  // namespace so101_gazebo_demo::pick_place
