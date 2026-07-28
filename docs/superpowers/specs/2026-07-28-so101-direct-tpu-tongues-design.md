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
| Reference geometry q6 | 0.30 rad |
| Initial close q6 | 0.29 rad |
| Initial preopen q6 | 0.465038 rad |
| Initial release q6 | 1.70 rad |
| Allowed vertical contact band | 8–35 mm below rim; at least 20 mm above bottom |
| Maximum individual contact penetration | 0.8 mm |
| Initial friction coefficient | 1.2, only if the installed Bullet path proves it effective |

The 5.0 mm value is the direct, link-local projection of each tongue. It is not a
permission to compensate for an uncalibrated gap by increasing penetration, altering the
cup wall thickness, or weakening the attachment gate.

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

The final box origins and orientations are deliberately not guessed in this document. They
must be derived from the current mesh/URDF transforms, the q6 reference, the 5 mm direct
projection, and the retained wrist orientation. The calibration artifact must record the
raw-finger gap, direct-tongue spans, preopen insertion clearance, closed face gap, and all
adapter/original-link self-collision checks. A raw gap of approximately 33 mm is evidence
that the final placement must be calculated, rather than inferred from the 5 mm nominal
projection alone.

## Motion policy boundary

All q6 values, the lateral approach clearance, and arm waypoints remain motion-policy YAML
data. A policy edit takes effect by restarting the task process; it must not require a C++
rebuild or introduce a C++ action constant. The retained wrist orientation is not rotated
180 degrees.

At preopen, both direct tongues need enough insertion clearance to descend from above
without rim contact or pad-pad collision. At close, the moving tongue must push the near
wall toward the fixed tongue. The fixed tongue may act as the outside backing face only
after the moving side establishes a valid inside contact. A direct tongue must never turn a
single-sided scrape into a valid grasp.

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

If exact calibration proves that 5 mm direct projections cannot provide both preopen
clearance and the approved same-wall 2–3 mm closed face gap without violating any safety
gate, record the competing geometry and retain the fail-closed contract. Do not silently
change the 5 mm design input, rotate the wrist, relax the contact band, or emulate TPU
softness with penetration.
