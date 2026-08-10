#pragma once
#include <memory>
#include <string>
#include <vector>
#include <pick_place_common/transition_contract.hpp>
#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"
#include "panda_gazebo_demo/pick_place/panda_workflow.hpp"
#include "panda_gazebo_demo/pick_place/world_observer.hpp"
namespace panda_gazebo_demo::pick_place
{
using pick_place_common::AlwaysPassValidator;
using pick_place_common::TransitionKey;
using pick_place_common::ValidationResult;
class PandaBoundaryMetricsDecorator final : public pick_place_common::ITransitionValidationDecorator
{
public:
  ValidationResult decoratePrecondition(TransitionKey, const WorldSnapshot &,
                                        ValidationResult) const override;
  ValidationResult decoratePostcondition(TransitionKey, const WorldSnapshot &,
                                         const WorldSnapshot &, const ActionResult &,
                                         ValidationResult) const override;
  ValidationResult decorateResume(TransitionKey, const WorldSnapshot &, const WorldSnapshot &,
                                  ValidationResult) const override;
};
class TransitionContractRegistry : public pick_place_common::TransitionContractRegistry
{
public:
  TransitionContractRegistry();
  std::optional<Failure> validateExecuteCoverage() const
  {
    return pick_place_common::TransitionContractRegistry::validateExecuteCoverage(
      pandaWorkflowDefinition());
  }
};
class PrepareOpenGripperToMoveAboveObjectValidator final
    : public TransitionContractRegistry::ITransitionContract
{
public:
  PrepareOpenGripperToMoveAboveObjectValidator(std::vector<std::string> required_world_objects,
                                               double tcp_position_tolerance,
                                               double tcp_orientation_tolerance_rad,
                                               double coke_position_tolerance,
                                               double coke_orientation_tolerance_rad);

  [[nodiscard]] ValidationResult validate(const WorldSnapshot & before, const WorldSnapshot & after,
                                          const ActionResult & action_result) const override;
  [[nodiscard]] ValidationResult validatePrecondition(const WorldSnapshot & before) const override;

private:
  std::vector<std::string> required_world_objects_;
  double tcp_position_tolerance_;
  double tcp_orientation_tolerance_rad_;
  double coke_position_tolerance_;
  double coke_orientation_tolerance_rad_;
};

class MoveAboveObjectToDescendValidator final
    : public TransitionContractRegistry::ITransitionContract
{
public:
  MoveAboveObjectToDescendValidator(std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
                                    std::vector<std::string> required_world_objects,
                                    double tcp_position_tolerance,
                                    double tcp_orientation_tolerance_rad,
                                    double coke_position_tolerance,
                                    double coke_orientation_tolerance_rad);

  [[nodiscard]] ValidationResult validate(const WorldSnapshot & before, const WorldSnapshot & after,
                                          const ActionResult & action_result) const override;
  [[nodiscard]] ValidationResult validatePrecondition(const WorldSnapshot & before) const override;

private:
  std::shared_ptr<const PickPlaceTargetPolicy> target_policy_;
  std::vector<std::string> required_world_objects_;
  double tcp_position_tolerance_;
  double tcp_orientation_tolerance_rad_;
  double coke_position_tolerance_;
  double coke_orientation_tolerance_rad_;
};

class DescendToCloseGripperValidator final : public TransitionContractRegistry::ITransitionContract
{
public:
  DescendToCloseGripperValidator(std::shared_ptr<const PickPlaceTargetPolicy> target_policy,
                                 std::vector<std::string> required_world_objects,
                                 double tcp_position_tolerance,
                                 double tcp_orientation_tolerance_rad,
                                 double coke_position_tolerance,
                                 double coke_orientation_tolerance_rad);

  [[nodiscard]] ValidationResult validate(const WorldSnapshot & before, const WorldSnapshot & after,
                                          const ActionResult & action_result) const override;
  [[nodiscard]] ValidationResult validatePrecondition(const WorldSnapshot & before) const override;

private:
  std::shared_ptr<const PickPlaceTargetPolicy> target_policy_;
  std::vector<std::string> required_world_objects_;
  double tcp_position_tolerance_;
  double tcp_orientation_tolerance_rad_;
  double coke_position_tolerance_;
  double coke_orientation_tolerance_rad_;
};

}  // namespace panda_gazebo_demo::pick_place
