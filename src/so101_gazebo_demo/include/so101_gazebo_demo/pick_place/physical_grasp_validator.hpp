#pragma once

#include "so101_gazebo_demo/pick_place/domain_types.hpp"
#include "so101_gazebo_demo/pick_place/world_observer.hpp"

namespace so101_gazebo_demo::pick_place
{
struct PhysicalGraspThresholds
{
  double min_table_clearance_m{0.0005};
  double min_cup_follow_ratio{0.8};
  // Millimetre-scale lateral compliance is acceptable for end-to-end pick/place.
  // Keep a wider bound only to reject an obviously unstable or dropped grasp.
  double max_xy_slip_m{0.003};
  double max_orientation_change_rad{0.10};
  bool require_gripper_contact{true};
};

// Gazebo reports the model frame pose, not necessarily the lowest collision
// point.  The offset is expressed in the model frame's world-Z direction for
// the upright cup used by this simulation.
struct PhysicalGraspGeometry
{
  double table_surface_z_m{0.0};
  double cup_bottom_offset_z_m{0.0};
};

struct PhysicalGraspResult
{
  bool passed{false};
  double table_clearance_m{0.0};
  double cup_bottom_z_m{0.0};
  double tcp_z_delta_m{0.0};
  double cup_z_delta_m{0.0};
  double cup_follow_ratio{0.0};
  double xy_slip_m{0.0};
  double orientation_change_rad{0.0};
  bool gripper_contact{false};
  Failure failure{};
};

class PhysicalGraspValidator
{
public:
  explicit PhysicalGraspValidator(PhysicalGraspThresholds thresholds = {});
  [[nodiscard]] PhysicalGraspResult evaluate(const WorldSnapshot & before,
                                             const WorldSnapshot & after,
                                             const PhysicalGraspGeometry & geometry) const;

private:
  PhysicalGraspThresholds thresholds_;
};
}  // namespace so101_gazebo_demo::pick_place
