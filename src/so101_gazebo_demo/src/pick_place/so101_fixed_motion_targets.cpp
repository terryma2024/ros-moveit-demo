#include "so101_gazebo_demo/pick_place/so101_fixed_motion_targets.hpp"

#include <map>
#include <utility>

namespace so101_gazebo_demo::pick_place
{
namespace
{

using Joints = std::vector<double>;

const Joints kHome{0.0, 0.0, 0.0, 0.0, 0.0};
const Joints kAbovePick{-0.000074896, 0.406242712, -0.335892969, 1.500452910, -0.029650203};
const Joints kPick262{-0.004520982, 0.427298423, -0.219093530, 1.362597749, -0.083117591};
const Joints kPick242{-0.000416079, 0.471283543, -0.135531958, 1.235051068, -0.033743502};
const Joints kPick{-0.000011454, 0.536286226, -0.082912794, 1.117429221, -0.028880766};
const Joints kAbovePlace{0.331019977, 0.550670543, -0.562313463, 1.582446437, -1.600206428};
const Joints kPlace262{0.331012586, 0.555338833, -0.421537209, 1.437001892, -1.597230266};
const Joints kPlace242{0.331041085, 0.592207044, -0.331690813, 1.310287286, -1.607707019};
const Joints kPlace{0.331034755, 0.648891100, -0.272710221, 1.194622637, -1.605735287};

MotionValidationConfig config(const SO101Profile & profile, Vec3 endpoint, Vec3 direction,
                              bool allow_world_touch)
{
  MotionValidationConfig result;
  result.expected_joint_names = profile.arm_joints;
  result.endpoint_position = endpoint;
  result.local_approach_axis = {0.0, 0.0, -1.0};
  result.target_approach_axis = {0.0, 0.0, -1.0};
  result.path_direction = direction;
  if (allow_world_touch) {
    for (const auto & link : profile.moveit_touch_links) {
      result.allowed_touch_pairs.insert(profile.coke_model + ":" + link);
    }
  }
  return result;
}

JointMotionTarget goal(const SO101Profile & profile, const Joints & target, double q6)
{
  return {profile.arm_joints, {target}, false, q6};
}

JointMotionTarget ladder(const SO101Profile & profile, std::vector<Joints> waypoints, double q6,
                         std::optional<TemporalContactPolicy> temporal = std::nullopt)
{
  return {profile.arm_joints, std::move(waypoints), true, q6, std::move(temporal)};
}

}  // namespace

SO101FixedMotionTargetPolicy::SO101FixedMotionTargetPolicy(SO101Profile profile)
: profile_(std::move(profile))
{
}

std::optional<SO101FixedMotionSpec> SO101FixedMotionTargetPolicy::spec(State state) const
{
  const auto preopen = profile_.q6_preopen;
  const auto contact = profile_.q6_contact;
  const auto full_open = profile_.q6_full_open;
  switch (state) {
    case State::MOVE_ABOVE_OBJECT:
      return SO101FixedMotionSpec{state, kHome, goal(profile_, kAbovePick, preopen),
        config(profile_, {0.02, -0.28, 0.282}, {0, 0, -1}, false), preopen};
    case State::DESCEND:
      return SO101FixedMotionSpec{state, kAbovePick,
        ladder(profile_, {kPick262, kPick242, kPick}, preopen),
        config(profile_, {0.02, -0.28, 0.222}, {0, 0, -1}, true), preopen};
    case State::LIFT:
    {
      auto validation = config(profile_, {0.02, -0.28, 0.282}, {0, 0, 1}, false);
      validation.temporal_contact_policy =
        TemporalContactPolicy{{"coke:table"}, TemporalContactLocation::FIRST_ONLY};
      return SO101FixedMotionSpec{state, kPick,
        ladder(profile_, {kPick242, kPick262, kAbovePick}, contact,
               TemporalContactPolicy{{"coke:table"}, TemporalContactLocation::FIRST_ONLY}),
        std::move(validation), contact};
    }
    case State::MOVE_ABOVE_PLACE:
      return SO101FixedMotionSpec{state, kAbovePick, goal(profile_, kAbovePlace, contact),
        config(profile_, {-0.08, -0.25, 0.282}, {0, 0, -1}, false), contact};
    case State::DESCEND_TO_PLACE:
      return SO101FixedMotionSpec{state, kAbovePlace,
        ladder(profile_, {kPlace262, kPlace242, kPlace}, contact),
        config(profile_, {-0.08, -0.25, 0.222}, {0, 0, -1}, false), contact};
    case State::RETREAT:
    case State::RECOVER_LIFT_TO_SAFE_HEIGHT:
    {
      auto validation = config(profile_, {-0.08, -0.25, 0.282}, {0, 0, 1}, false);
      std::optional<TemporalContactPolicy> temporal;
      if (state == State::RETREAT) {
        temporal = TemporalContactPolicy{{"coke:gripper", "coke:jaw"},
          TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE, 0.043};
        validation.temporal_contact_policy = temporal;
      }
      return SO101FixedMotionSpec{state, kPlace,
        ladder(profile_, {kPlace242, kPlace262, kAbovePlace},
               state == State::RECOVER_LIFT_TO_SAFE_HEIGHT ? contact : full_open, temporal),
        std::move(validation),
        state == State::RECOVER_LIFT_TO_SAFE_HEIGHT ? contact : full_open};
    }
    case State::RECOVER_MOVE_ABOVE_PICK:
      return SO101FixedMotionSpec{state, kAbovePlace, goal(profile_, kAbovePick, contact),
        config(profile_, {0.02, -0.28, 0.282}, {0, 0, -1}, false), contact};
    case State::RECOVER_DESCEND_TO_PICK:
    {
      auto validation = config(profile_, {0.02, -0.28, 0.222}, {0, 0, -1}, false);
      validation.temporal_contact_policy =
        TemporalContactPolicy{{"coke:table"}, TemporalContactLocation::LAST_ONLY};
      return SO101FixedMotionSpec{state, kAbovePick,
        ladder(profile_, {kPick262, kPick242, kPick}, contact,
               TemporalContactPolicy{{"coke:table"}, TemporalContactLocation::LAST_ONLY}),
        std::move(validation), contact};
    }
    case State::RECOVER_RETREAT:
    {
      auto validation = config(profile_, {0.02, -0.28, 0.282}, {0, 0, 1}, false);
      const TemporalContactPolicy temporal{{"coke:gripper", "coke:jaw"},
        TemporalContactLocation::PREFIX_UNTIL_AXIAL_CLEARANCE, 0.043};
      validation.temporal_contact_policy = temporal;
      return SO101FixedMotionSpec{state, kPick,
        ladder(profile_, {kPick242, kPick262, kAbovePick}, full_open, temporal),
        std::move(validation), full_open};
    }
    default:
      return std::nullopt;
  }
}

JointMotionTargetResult SO101FixedMotionTargetPolicy::target(
  State state, State, const ObservationResult &) const
{
  const auto selected = spec(state);
  if (!selected) {
    return {std::nullopt,
            Failure{FailureCategory::CONFIGURATION, "SO101_FIXED_MOTION_TARGET_UNAVAILABLE",
                    "State has no target in " + version_, {}}};
  }
  return {selected->target, std::nullopt};
}

const std::string & SO101FixedMotionTargetPolicy::version() const noexcept { return version_; }

}  // namespace so101_gazebo_demo::pick_place
