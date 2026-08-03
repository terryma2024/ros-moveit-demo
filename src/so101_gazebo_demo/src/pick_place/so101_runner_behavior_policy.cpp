#include "so101_gazebo_demo/pick_place/so101_runner_behavior_policy.hpp"

#include <set>
#include <string>

namespace so101_gazebo_demo::pick_place
{
namespace
{
constexpr std::size_t kMaximumConvergenceAttempts = 480;
const std::set<std::string> kTransientBoundaryCodes{"MOTION_JOINT_ENDPOINT_MISMATCH",
                                                    "TCP_ENDPOINT_OUTSIDE_TOLERANCE",
                                                    "TCP_AXIS_OUTSIDE_TOLERANCE",
                                                    "Q6_TARGET_OUT_OF_TOLERANCE",
                                                    "Q6_WIDTH_OUT_OF_TOLERANCE",
                                                    "Q6_NOT_STATIONARY",
                                                    "ARM_NOT_QUIESCENT",
                                                    "BILATERAL_GRIPPER_CONTACT_REQUIRED",
                                                    "CONTACT_PENETRATION_EVIDENCE_REQUIRED",
                                                    "SEMANTIC_FINGER_CONTACT_REQUIRED"};

bool retry(const pick_place_common::Failure & failure, std::size_t attempt)
{
  return attempt < kMaximumConvergenceAttempts && kTransientBoundaryCodes.count(failure.code) != 0;
}
}  // namespace

bool SO101RunnerBehaviorPolicy::retryPrecondition(pick_place_common::State,
                                                  const pick_place_common::Failure & failure,
                                                  std::size_t attempt) const
{
  return retry(failure, attempt);
}

bool SO101RunnerBehaviorPolicy::retryPostcondition(pick_place_common::State,
                                                   const pick_place_common::Failure & failure,
                                                   std::size_t attempt) const
{
  return retry(failure, attempt);
}

bool SO101RunnerBehaviorPolicy::includeIdleInTrace() const noexcept
{
  return true;
}

}  // namespace so101_gazebo_demo::pick_place
