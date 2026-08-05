#pragma once

#include <pick_place_common/runner.hpp>

namespace so101_gazebo_demo::pick_place
{

class SO101RunnerBehaviorPolicy final : public pick_place_common::IRunnerBehaviorPolicy
{
public:
  [[nodiscard]] bool retryPrecondition(pick_place_common::State, const pick_place_common::Failure &,
                                       std::size_t attempt) const override;
  [[nodiscard]] bool retryPostcondition(pick_place_common::State,
                                        const pick_place_common::Failure &,
                                        std::size_t attempt) const override;
  [[nodiscard]] bool includeIdleInTrace() const noexcept override;
  [[nodiscard]] bool runExecutePreflight() const noexcept override;
  [[nodiscard]] bool recoverForwardObservationFailure() const noexcept override;
  [[nodiscard]] bool preserveEnvironmentFailureWithoutRecovery() const noexcept override;
  [[nodiscard]] bool retryTransientObservation(pick_place_common::State,
                                                const pick_place_common::Failure &,
                                                std::size_t attempt) const override;
  [[nodiscard]] bool waitForStationaryObjectOnResume() const noexcept override;
  [[nodiscard]] bool preserveOriginalFailureOnRecoveryError() const noexcept override;
};

}  // namespace so101_gazebo_demo::pick_place
