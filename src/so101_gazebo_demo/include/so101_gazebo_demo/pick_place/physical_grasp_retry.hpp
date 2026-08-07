#pragma once

#include <cstddef>
#include <memory>
#include <optional>

#include "so101_gazebo_demo/pick_place/physical_grasp_validator.hpp"
#include "so101_gazebo_demo/pick_place/so101_profile.hpp"

namespace so101_gazebo_demo::pick_place
{
class ISO101GripperCommand;
class IWorldZMicroLift;
class IPhysicalGraspEvidenceStore;
class SO101PhysicalGraspStabilizer;

struct PhysicalGraspRetryConfig
{
  std::size_t max_attempts{5};
  double contact_missing_tighten_step_q6{0.001};
  double max_tighten_q6{0.004};
};

struct PhysicalGraspRetryProgress
{
  std::size_t attempt_index{1};
  std::size_t contact_missing_count{0};
  double current_reclose_target_q6{0.0};
};

struct PhysicalGraspRetryDecision
{
  bool retry{false};
  PhysicalGraspRetryProgress next;
  std::optional<Failure> rejection;
};

[[nodiscard]] PhysicalGraspRetryDecision
decidePhysicalGraspRetry(const PhysicalGraspRetryConfig & config, const SO101Profile & profile,
                         const PhysicalGraspRetryProgress & current,
                         const PhysicalGraspResult & physical_result, const WorldSnapshot & after);

class PhysicalGraspRetryCoordinator
{
public:
  PhysicalGraspRetryCoordinator(std::shared_ptr<ISO101GripperCommand> gripper,
                                std::shared_ptr<IWorldZMicroLift> micro_lift,
                                std::shared_ptr<IWorldObserver> observer,
                                std::shared_ptr<IPhysicalGraspEvidenceStore> evidence,
                                std::shared_ptr<SO101PhysicalGraspStabilizer> stabilizer,
                                PhysicalGraspValidator validator, PhysicalGraspGeometry geometry,
                                SO101Profile profile = SO101Profile::canonical(),
                                PhysicalGraspRetryConfig config = {});
  ~PhysicalGraspRetryCoordinator();

  PhysicalGraspRetryCoordinator(const PhysicalGraspRetryCoordinator &) = delete;
  PhysicalGraspRetryCoordinator & operator=(const PhysicalGraspRetryCoordinator &) = delete;
  PhysicalGraspRetryCoordinator(PhysicalGraspRetryCoordinator &&) noexcept;
  PhysicalGraspRetryCoordinator & operator=(PhysicalGraspRetryCoordinator &&) noexcept;

  [[nodiscard]] ActionResult verifyOrRetry();
  [[nodiscard]] ActionResult cancel();

private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};
}  // namespace so101_gazebo_demo::pick_place
