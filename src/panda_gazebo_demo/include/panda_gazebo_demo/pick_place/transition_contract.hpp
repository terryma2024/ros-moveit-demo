#pragma once

#include <map>
#include <memory>
#include <string>
#include <vector>

#include "panda_gazebo_demo/pick_place/domain_types.hpp"
#include "panda_gazebo_demo/pick_place/pick_place_target_policy.hpp"
#include "panda_gazebo_demo/pick_place/world_observer.hpp"

namespace panda_gazebo_demo::pick_place
{

class TransitionTable;

struct TransitionKey
{
  State from;
  State to;

  friend bool operator<(const TransitionKey & lhs, const TransitionKey & rhs) noexcept
  {
    return lhs.from != rhs.from ? lhs.from < rhs.from : lhs.to < rhs.to;
  }
};

struct ValidationResult
{
  bool ok{false};
  std::vector<Failure> failures;
  std::map<std::string, double> metrics;
};

class TransitionContractRegistry
{
public:
  class ITransitionContract
  {
  public:
    virtual ~ITransitionContract() = default;
    [[nodiscard]] virtual ValidationResult
    validatePrecondition(const WorldSnapshot & before) const = 0;
    [[nodiscard]] virtual ValidationResult validate(const WorldSnapshot & before,
                                                    const WorldSnapshot & after,
                                                    const ActionResult & action_result) const = 0;
  };

  void registerContract(TransitionKey key, std::shared_ptr<const ITransitionContract> contract);
  [[nodiscard]] bool hasContract(TransitionKey key) const noexcept;
  [[nodiscard]] ValidationResult validate(TransitionKey key, const WorldSnapshot & before,
                                          const WorldSnapshot & after,
                                          const ActionResult & action_result) const;
  [[nodiscard]] ValidationResult validatePrecondition(TransitionKey key,
                                                      const WorldSnapshot & before) const;
  [[nodiscard]] ValidationResult validateResume(TransitionKey key, const WorldSnapshot & expected,
                                                const WorldSnapshot & current) const;
  [[nodiscard]] std::optional<Failure> validateExecuteCoverage() const;

private:
  std::map<TransitionKey, std::shared_ptr<const ITransitionContract>> contracts_;
};

class AlwaysPassValidator final : public TransitionContractRegistry::ITransitionContract
{
public:
  [[nodiscard]] ValidationResult validatePrecondition(const WorldSnapshot & before) const override;
  [[nodiscard]] ValidationResult validate(const WorldSnapshot & before, const WorldSnapshot & after,
                                          const ActionResult & action_result) const override;
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
