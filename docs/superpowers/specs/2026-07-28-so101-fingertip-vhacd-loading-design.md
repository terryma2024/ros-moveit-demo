# SO101 Fingertip VHACD and Convex Loading Design

## Goal

Replace the fixed-finger box collision with offline convex pieces that follow the real fingertip, while reducing Gazebo / Bullet convex-hull construction time without changing either visual STL.

## Scope

- Preserve the complete visual meshes for `wrist_roll_follower_so101_v1.stl` and `moving_jaw_so101_v1.stl`.
- Build collision meshes only for the two load-bearing fingertip regions.
- Keep `gz-physics-bullet-featherstone-plugin` and offline VHACD.
- Do not change the Coke geometry, 50 g inertial model, MoveIt visual model, wrist orientation, or state-machine ordering in this change.

## Collision Geometry

Create a generic offline generator that accepts a source STL, an axis-aligned fingertip ROI in source-mesh coordinates, an output prefix, and a maximum hull count. It extracts triangles intersecting the ROI, runs VHACD, verifies each result is non-empty and convex, and emits binary STL pieces plus a deterministic JSON manifest containing source hash, ROI, VHACD parameters, piece filenames, triangle counts, bounds, and hashes.

Use separate manifests and prefixes:

- `moving_jaw_contact_convex_*`
- `fixed_finger_contact_convex_*`

Start with a maximum of eight pieces per fingertip. Increase one side to at most twelve only when its contact-region surface error or runtime contact evidence fails acceptance. Total fingertip collision count must not exceed twenty-four.

The fixed-finger ROI is extracted from `wrist_roll_follower_so101_v1.stl`; housing, screw holes, motor features, and non-contact outer geometry are excluded. The moving-jaw ROI excludes the hinge and upper structures that currently create Coke top-edge contacts.

## Model Preparation and Cache

Replace the hard-coded expectation of exactly 64 moving-jaw pieces with manifest-driven validation for both prefixes. Every listed file must exist, have the recorded hash, and appear exactly once in the generated SDF. Each mesh keeps `optimization="convex_hull"`; runtime convex decomposition is forbidden.

Cache the prepared SDF by a digest of:

- Xacro content and referenced collision manifests;
- generator version and VHACD parameters;
- `base_height` and Gazebo collision mode.

On a cache hit, launch reuses the prepared SDF and skips Xacro to URDF to SDF conversion. Cache writes remain atomic. A stale, incomplete, or hash-mismatched cache is rejected and rebuilt.

The primary performance gain must come from reducing Bullet collision objects, not merely from the preprocessing cache.

## Contact Semantics

The observer continues to classify contacts by collision prefix. Fixed and moving contacts remain independently observable. The bilateral attach gate, 2 mm maximum penetration limit, and fingertip sidewall-height gate remain fail-closed.

Collision names must preserve stable fixed/moving prefixes so existing attachment evidence can be migrated without weakening validation.

## Verification

Automated checks must cover:

- deterministic manifests and binary STL output;
- both fingertip prefixes emitted into Xacro/SDF;
- no box collision named `fixed_finger_contact` in Gazebo mode;
- manifest count/hash mismatch rejected before launch;
- cache miss, hit, and invalidation behavior;
- bilateral contact classification with the new names;
- existing attachment and state-machine tests remain green.

Runtime acceptance uses three clean GUI launches in `so101-moveit`, with `source ~/gui-env.zsh`, Bullet Featherstone, and the established ROS domain and Gazebo partition. Record median time from Gazebo process start to active arm and gripper controllers. The median convex-loading/startup interval must improve by at least 40 percent from the retained baseline.

Each run must also show:

- both fingertip convex sets loaded with no mesh construction or resource errors;
- Coke contact on both fingertip sidewalls and clear of the top edge;
- maximum penetration below 2 mm;
- real-time factor at least 0.98 after settling;
- no position-controller forced penetration;
- attach, lift, detach, MoveIt/Gazebo membership, and recovery evidence when the physical contact gate passes.

The GUI result must be captured with the repository's ai-station screenshot workflow. Test or API success without a screenshot is not visual acceptance.

## Failure Handling

- Empty ROI, non-convex output, missing files, duplicate names, or hash mismatch aborts model preparation.
- More than twelve pieces per fingertip or twenty-four total fails configuration tests.
- A faster launch that worsens contact placement or penetration is rejected.
- If eight pieces fail geometric/contact acceptance, increase only the failing fingertip budget and remeasure; do not restore the 64-piece set by default.
