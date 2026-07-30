# SO-101 TPU Fingertip Adapter Design

Date: 2026-07-28
Status: user-approved Task 6 scope expansion; implementation remains uncommitted

## Objective and preserved safety contract

Add removable simulation-only fingertip adapters to the existing SO-101 fixed finger and
moving jaw so they can pinch the outside and inside surfaces of the same 2 mm
`wall_near`. Keep the 20 g open cup, Bullet Featherstone, cached STL/VHACD collisions,
two-sided contact evidence, named-wall/height/normal checks, forbidden rim/bottom/opposite
contacts, and maximum 0.8 mm penetration unchanged.

The adapters represent TPU 95A visually and semantically, but Gazebo models them as rigid
convex primitives. The implementation and documentation must not claim real soft-body
deformation. Compliance must not be imitated by increasing allowed penetration.

## Considered approaches

1. Add link-local primitive adapter assemblies to `gripper` and `jaw` (selected). This
   preserves the original links, joints, STL visuals, and cached VHACD pieces. MoveIt and
   Gazebo see the same adapter geometry. Each assembly consists of a narrow contact tongue
   and a rearward mounting stem; only the tongue is classified as cup contact.
2. Add separate fixed child links. This makes removability explicit in TF but expands the
   robot model, SRDF collision matrix, attachment touch links, and controller-independent
   state without improving the contact physics.
3. Modify the original STL or regenerate VHACD. This violates the approved boundary and
   increases startup/provenance risk, so it is rejected.

## Calibration and configuration

Adapter geometry is stored in the strict task-object YAML and included in the existing
policy digest. Gripper actions remain in the motion YAML; validation thresholds remain in
the validation YAML. C++ receives typed values and does not introduce new action constants.

The real 80 mm cup-diameter ray section at 20 mm fingertip depth is used. Candidate q6
values are accepted only when the moving mesh face normal points into the gap within 30
degrees. The first stable region starts near q6=0.272; q6=0.30 is selected with margin:

- raw STL gap at geometry reference q6=0.30: 0.041842074610 m;
- target adapter-face gap at reference: 0.002500000000 m;
- symmetric tongue extension: `(0.041842074610 - 0.0025) / 2`
  = 0.019671037305 m per side;
- initial motion-policy close q6=0.29: predicted face gap 0.001864951452 m;
- initial motion-policy preopen q6=0.89: predicted face gap 0.047670702603 m.

The close command therefore requests about 0.135 mm total interference against the 2 mm
wall while retaining positive pad-to-pad clearance. Live Bullet contact must still report
no individual penetration above 0.8 mm.

The contact tongue is 12 mm wide across `wall_near`, leaving lateral clearance inside the
20.705524 mm wall segment. Its vertical active face is limited to the configured contact
band (8--35 mm below the rim). A rearward stem connects it to the original fingertip while
remaining behind the active face, so the stem cannot satisfy contact classification.
Exact origins are derived from the current URDF transforms, selected q6, cup pose, and
DESCEND endpoint and are locked by independent literal tests.

## TPU contact approximation

Visuals use a distinct TPU material. Collisions remain boxes. The initial friction target
is a conservative isotropic coefficient of 1.2, but it may be emitted only through an SDF
surface parameter that the installed Bullet Featherstone path demonstrably honors. A
runtime A/B must show a changed tangential-slip result with geometry, mass, force, and
penetration policy held fixed. Unsupported stiffness/damping fields are omitted rather
than documented as effective.

## Runtime and evidence flow

The launch path reads adapter geometry from the same object YAML used by the task process
and passes it to xacro. Missing, non-finite, inconsistent, or unsafe geometry fails closed.
The observer classifies `fixed_tpu_adapter_contact` as fixed-finger evidence and
`moving_tpu_adapter_contact` as moving-jaw evidence. Mounting stems never count as valid
finger contact. The existing attachment contract continues to require both classified
samples on `wall_near`, correct outside/inside normals, finite allowed heights, no forbidden
collision, stationary q6/controller evidence, RTF, and penetration at or below 0.8 mm.

## Verification sequence

Automated RED/GREEN tests cover strict config parsing, independent calibration literals,
preopen clearance, close wall interference with positive pad-pad gap, link/primitive
placement, forbidden adapter-to-original/cross-link self-collision, observer classification,
and unchanged attachment rejection cases. Live acceptance then proceeds from a clean reset
one boundary at a time: MOVE_ABOVE, DESCEND, CLOSE, ATTACH_GAZEBO, ATTACH_MOVEIT, LIFT,
MOVE_ABOVE_PLACE, DESCEND_TO_PLACE, detach/sync, and RETREAT. Task 7 begins only after the
full chain and fresh Gazebo/RViz visual evidence pass.
