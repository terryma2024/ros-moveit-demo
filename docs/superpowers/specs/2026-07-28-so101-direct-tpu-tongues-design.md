# SO-101 5 mm Direct TPU Tongues Design

Date: 2026-07-28
Status: approved design specification only — no implementation is included in this change

## Purpose

Replace the previously considered stem-and-tongue adapter assembly with two removable,
simulation-only direct TPU tongues: one on the fixed finger and one on the moving jaw.
They support the approved 20 g open light-plastic-cup task: approach `wall_near` from
above, place the fixed tongue outside the near wall and the moving tongue inside it, close
on that same 2 mm wall, lift, carry, place, detach, and retreat.

This specification does not authorize a change to the cup, motion semantics, validation
semantics, original STL, original VHACD, or the Bullet Featherstone physics plugin.

## Frozen design inputs

| Item | Value |
| --- | --- |
| Cup mass | 0.020 kg |
| Cup height / outer radius | 90 mm / 40 mm |
| Near-wall thickness | 2.0 mm |
| Tongue material designation | TPU 95A |
| Direct tongue projection, each side | 5.0 mm |
| Active-face width / height | 12 mm / 27 mm |
| Overlap with each original fingertip | 3.0 mm |
| Reference geometry q6 | 0.30 rad |
| Calculated tongue-touch q6 | -0.007113433021 rad |
| Safe lower / home / fullclose q6 | 0.002757025188 rad, giving 1.0 mm pad gap |
| Cup-grasp close q6 | 0.004728114131 rad, giving 1.2 mm pad gap |
| Initial preopen q6 | 0.465038 rad |
| Calculated preopen pad gap | 44.514 mm |
| Initial release q6 | 1.70 rad |
| Initial q6 position tolerance | 0.001 rad |
| Allowed vertical contact band | 8–35 mm below rim; at least 20 mm above bottom |
| Maximum individual contact penetration | 0.8 mm |
| Initial friction coefficient | 1.2, only if the installed Bullet path proves it effective |

The 5.0 mm value is the direct, link-local projection of each tongue. It is not a
permission to compensate for an uncalibrated gap by increasing penetration, altering the
cup wall thickness, or weakening the attachment gate.

## Considered thicknesses

| Projection per side | q6 at 1.0 mm safe gap | q6 at 1.2 mm grasp gap | Decision |
| --- | --- | --- | --- |
| 3 mm | -0.035771889455 | -0.033792842587 | Rejected: requires a negative nominal home and gives less mounting stiffness. |
| 5 mm | 0.002757025188 | 0.004728114131 | Selected: stays near the original zero home while retaining a practical direct pad. |
| 10 mm | 0.099312170614 | 0.101263777284 | Rejected: unnecessarily reduces usable opening range and increases protrusion. |

All three are geometric candidates within the original joint range. Selection of 5 mm is
therefore a packaging and safety-limit choice, not proof of successful Bullet contact.

## Geometry and material model

Each tongue is a removable, link-local convex box primitive directly attached to the
existing fixed-finger or moving-jaw link. There is no separate mounting stem, child link,
controller, STL edit, or VHACD regeneration. The visual material must be visibly distinct
from the original gripper and named as TPU 95A. The collision primitive remains rigid;
Gazebo is **not** modelling TPU deformation, compliance, or a soft-body contact model.

The direct tongues use the same 12 mm by 27 mm active face as the approved cup-contact
envelope. Their 5 mm projections are measured along the calibrated gripper opening axis,
not along an arbitrary world axis. The fixed active face must lie on the cup exterior side
of `wall_near`; the moving active face must lie on its interior side. Neither tongue may
qualify a contact on `rim`, `bottom`, or `wall_opposite`.

The approved link-local box transforms, calculated from the current STL and URDF joint
transforms, are:

| Tongue | Parent link | `xyz` (m) | `rpy` (rad) |
| --- | --- | --- | --- |
| Fixed | `gripper` | `[-0.009099999852, 0, -0.114449432212]` | `[0, 0, 0]` |
| Moving | `jaw` | `[-0.019701707396, -0.089211614425, 0.018800334443]` | `[-1.5708, 0, -0.30]` |

Each box overlaps its owning original fingertip by 3 mm. This same-link overlap represents
the direct mounting land; it is not a mounting stem and must not be classified as cup
contact. The calibration artifact must independently regenerate these transforms and
record direct-tongue spans, preopen insertion clearance, closed face gaps, and all
cross-link and opposite-original-link collision checks. These values are geometric results;
they have not yet been validated by Bullet contact simulation.

## Motion policy boundary

All q6 values, the lateral approach clearance, and arm waypoints remain configuration data.
A policy edit takes effect by restarting the task process; it must not require a C++ rebuild
or introduce a C++ action constant. The retained wrist orientation is not rotated 180
degrees.

The calculated zero-gap tongue-touch angle is `-0.007113433021 rad`. It is diagnostic only
and must never be commanded. The enforced lower angle is `0.002757025188 rad`, where the
two tongue faces retain 1.0 mm clearance. That value is the single safety floor for the
URDF joint-6 lower limit, the ros2_control command minimum, the MoveIt joint limit, the
SRDF `home` and `fullclose` named states, reset, and every recovery target. A controller
must not be able to bypass it.

The cup-grasp command is `0.004728114131 rad`, producing a calculated 1.2 mm tongue gap.
Against the 2.0 mm cup wall, the resulting total geometric interference is 0.8 mm, equal to
but not greater than the retained penetration ceiling. The initial q6 position tolerance is
0.001 rad; live controller evidence must prove it is achievable without crossing the hard
lower limit.

At preopen, both direct tongues need enough insertion clearance to descend from above
without rim contact or pad-pad collision. At close, the moving tongue must push the near
wall toward the fixed tongue. The fixed tongue may act as the outside backing face only
after the moving side establishes a valid inside contact. A direct tongue must never turn a
single-sided scrape into a valid grasp.

At `q6=0.465038 rad`, the calculated direct-tongue gap is 44.514 mm. Moving the tongues
upward to overlap the original tips changes the end-effector calibration: the geometric
candidate DESCEND TCP height is `z=0.219000431 m`. This is not a frozen runtime waypoint;
the complete x/y/z pose must be recalibrated in the GUI while retaining the approved wrist
orientation and contact band.

## Validation policy boundary

The observer maps the fixed direct-tongue collision to fixed-finger evidence and the
moving direct-tongue collision to moving-jaw evidence. Original fixed/moving contact
collisions may remain supplemental evidence, but an aggregate contact boolean is
insufficient.

`ATTACH_GAZEBO` remains fail closed and requires all of the following:

- both fixed-outside and moving-inside contact samples on `wall_near`;
- finite, opposing inside/outside normals;
- every qualifying point inside the configured 8–35 mm-below-rim vertical band and at
  least 20 mm above the cup bottom;
- no `rim`, `bottom`, or `wall_opposite` sample;
- finite per-sample penetration no greater than 0.8 mm;
- stationary q6 with the YAML position and velocity tolerances; and
- a calibrated DetachableJoint relative pose that represents an actual two-sided pinch,
  never a one-sided suspension.

The policy must continue to reject any of these failures; rigid-primitive approximation
must not be represented by a larger penetration limit.

## Bullet Featherstone contact parameters

Use only SDF surface fields that the installed Bullet Featherstone runtime demonstrably
honours. Start with isotropic friction 1.2. A runtime A/B must hold geometry, cup mass,
motion, force, and the 0.8 mm penetration ceiling fixed while showing the expected change
in tangential slip. Do not claim contact stiffness or damping is active unless the same
runtime evidence verifies that specific field. Unsupported stiffness/damping fields are to
be omitted.

## Required proof before implementation acceptance

1. RED/GREEN tests lock the 5 mm projection, primitive dimensions, YAML ownership, and
   exact mesh/q6-derived origins.
2. Geometry tests prove preopen insertion clearance, positive closed pad-pad gap, no
   pad-pad collision, and no illegal direct-tongue/original-gripper self-collision.
3. Observer and contract tests prove bilateral `wall_near` classification, valid height and
   normal, forbidden-contact rejection, and the unchanged 0.8 mm limit.
4. From a clean task reset, GUI evidence covers
   `MOVE_ABOVE → DESCEND → CLOSE → ATTACH_GAZEBO → ATTACH_MOVEIT → LIFT → PLACE → DETACH → RETREAT`.
   Record collision names, contact heights, maximum depth, q6 target/error, attachment
   state, RTF, and the first failure if any.
5. Only after the full attachment chain passes may startup benchmarking, full regression,
   and a fresh CUA-reviewed Gazebo/RViz screenshot be considered.

If Bullet validation disproves the calculated 44.514 mm preopen clearance, 1.2 mm grasp
gap, 1.0 mm safe-limit gap, or the derived link transforms, record the first divergent
boundary and return for a new design decision. Do not silently change the 5 mm design
input, q6 safety floor, wrist orientation, contact band, or penetration ceiling, and do not
emulate TPU softness with penetration.
