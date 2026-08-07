#pragma once

#include <memory>
#include <variant>

#include "so101_gazebo_demo/pick_place/policy_config.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"
#include "so101_gazebo_demo/pick_place/transition_contract.hpp"

namespace so101_gazebo_demo::pick_place
{

[[nodiscard]] std::variant<Pose3d, Failure>
derivePlanningShadowPose(const WorldSnapshot & snapshot);

[[nodiscard]] ValidationResult
evaluatePlanningShadowDivergence(const WorldSnapshot & snapshot,
                                 const PhysicalOutcomePolicyConfig & policy);

[[nodiscard]] std::shared_ptr<const TransitionContractRegistry::ITransitionContract>
makeSO101AttachmentContract(TransitionKey key, const SO101Profile & profile,
                            const TaskObjectConfig & object,
                            const GraspContactValidationConfig & grasp_contact);

void registerSO101AttachmentContracts(TransitionContractRegistry & registry,
                                      const SO101Profile & profile, const TaskObjectConfig & object,
                                      const GraspContactValidationConfig & grasp_contact);

}  // namespace so101_gazebo_demo::pick_place
