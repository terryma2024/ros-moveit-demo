#pragma once

#include "so101_gazebo_demo/pick_place/domain_types.hpp"
#include "so101_gazebo_demo/pick_place/world_observer.hpp"

namespace so101_gazebo_demo::pick_place
{
struct PhysicalGraspThresholds
{
  // The default EXP081 contract is outcome-first.  Process telemetry remains
  // available and stricter callers can still opt into the legacy gates.
  double min_table_clearance_m{-1.0};
  double min_cup_follow_ratio{0.0};
  double max_xy_slip_m{0.006};
  double max_orientation_change_rad{3.141592653589793};
  bool require_gripper_contact{false};
  double minimum_axial_progress_m{0.0001};
  double maximum_position_error_m{0.006};
  bool require_arm_stable{true};
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
  double position_error_m{0.0};
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
