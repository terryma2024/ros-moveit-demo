# MuJoCo RGB-D perception-driven pick-place design

**Date:** 2026-08-26

**Runtime target:** Local macOS MuJoCo simulation

**Package scope:** `src/so101_demo_py`

**Evidence root:** `/tmp/so101-debug-rgbd-perception-pick-place-20260826/`

## 1. Objective

Complete the production simulation chain:

```text
MuJoCo
  -> aligned RGB-D
  -> segmented cup point cloud
  -> tf2 world transform
  -> /cup_pose
  -> dynamic_cup_pick_place
  -> MoveIt
  -> controllers
  -> MuJoCo physical outcome
```

The final demonstration consists of four independent full-stack runs. Each run starts from one
named MJCF keyframe, perceives the cup through the camera topics, and places it in the existing red
target region:

- `task_start`: `(0.02, -0.28, 0.165)`;
- `cup_test_forward_5cm`: `(0.02, -0.33, 0.165)`;
- `cup_test_left_5cm`: `(-0.03, -0.28, 0.165)`;
- `cup_test_right_5cm`: `(0.07, -0.28, 0.165)`.

The four runs demonstrate position coverage. They are not a five-consecutive-run stability
qualification.

## 2. Chosen approach

Use one independent production perception node plus one dedicated end-to-end launch composition.
The perception node owns RGB-D synchronization, segmentation, point-cloud reconstruction, tf2
lookup, world-frame cup fitting, and `/cup_pose` publication. The existing dynamic workflow owns
pose freezing, motion-target derivation, planning, execution, physical gates, and final evidence.

Alternatives were rejected as follows:

- A serialized `PointCloud2` intermediate topic adds a high-rate transport and QoS boundary that
  is unnecessary for this four-position experiment.
- Embedding perception inside `dynamic_cup_pick_place` would couple sensor and execution failure
  domains and would remove an independently testable `/cup_pose` boundary.
- Routing the production result through `cup_pose_tf_demo` would duplicate the transform boundary.
  The upright-cylinder fit needs points expressed relative to world-up, so production transforms
  the segmented point cloud to `world` before fitting. `cup_pose_tf_demo` remains an independent
  teaching and diagnostic executable.

## 3. Runtime architecture

Each run uses a fresh MuJoCo, controller, MoveIt, perception, and dynamic-workflow process graph:

```text
MJCF named keyframe
  -> mujoco_ros2_control + CameraPlugin
  -> /task_camera/camera_info
     /task_camera/color
     /task_camera/depth
  -> rgbd_cup_pose
       exact-stamp RGB-D match
       orange mask + DBSCAN
       optical-frame point cloud
       tf2(world <- task_camera_frame) at the image stamp
       upright-cylinder center fit in world
  -> /cup_pose (geometry_msgs/msg/PoseStamped, frame_id=world)
  -> dynamic_cup_pick_place
       freeze one fresh sample
       compare perception against MuJoCo lossless pose
       synchronize the MoveIt plastic_cup shadow
       verify topic / MuJoCo / Planning Scene convergence
       derive dynamic grasp targets
  -> MoveIt planning and execution
  -> arm and gripper controllers
  -> MuJoCo transport, release, and placement
```

The dedicated launch owns every process it starts. A terminal perception, readiness, scene,
planning, execution, or physical-validation failure shuts down the owned graph with a nonzero
result. It does not stop unrelated processes.

## 4. Camera frame contract

The launch publishes the two approved static transforms:

```text
base -> camera_link
  translation = (0.65, -0.65, 0.3600814)
  RPY = (0, 0.517, 2.35619449)

camera_link -> task_camera_frame
  translation = (0, 0, 0)
  RPY = (-1.57079633, 0, -1.57079633)
```

`robot_state_publisher` already supplies `world -> base` with a `0.1899186 m` vertical offset.
The composed camera origin is therefore `(0.65, -0.65, 0.55)` in world, matching the MJCF
`task_camera`. The second rotation maps the physical camera link to the ROS optical convention used
by CameraPlugin: X right, Y down, and Z forward. A contract test must compare the composed transform
against the MJCF `pos` and `xyaxes` rather than validating only the literal command arguments.

No business logic may manually flip point-cloud axes. All convention changes must be represented in
the TF tree.

## 5. Initial keyframe selection

Add a `mujoco_initial_keyframe` launch argument and a corresponding token in the rendered MuJoCo
URDF. The value is passed to the pinned `mujoco_ros2_control` `initial_keyframe` hardware parameter.
The default remains `task_start`, preserving current behavior.

Each acceptance run launches a new stack with exactly one of the four allowed names. The selected
keyframe is applied during hardware initialization, so the cup starts at the requested pose at
simulation epoch zero. The run does not teleport the cup after startup and does not use a truth
publisher to manufacture `/cup_pose`.

An unknown or malformed keyframe fails hardware initialization and the launch exits before
perception or motion.

## 6. Perception components

### 6.1 Shared RGB-D and point-cloud core

Refactor `rgbd_point_cloud.py` so the reusable operation returns an in-memory structured result:

- aligned source stamp and frame;
- intrinsics and image dimensions;
- segmented cup points and colors in `task_camera_frame`;
- full, color-candidate, and selected-cluster point counts;
- point-cloud bounds and robust diagnostic center.

Writing a PLY is optional evidence output. Computation must not write a PLY and read it back. The
same in-memory points drive both PLY serialization and world-frame pose estimation.

Input gates remain fail closed:

- CameraInfo, RGB, and depth have identical nonzero stamps, dimensions, and frame IDs;
- RGB is packed `rgb8` and depth is packed `32FC1` with valid row strides;
- depth contains finite positive values within the configured truncation distance;
- intrinsics are finite and focal lengths are positive;
- the orange mask and largest non-noise DBSCAN cluster meet their minimum point counts.

### 6.2 Production `rgbd_cup_pose` node

`rgbd_cup_pose` becomes a long-running ROS node. For each aligned RGB-D triple it:

1. builds the segmented cup point cloud;
2. looks up `world <- task_camera_frame` at the exact source stamp;
3. transforms all selected cup points into `world`;
4. fits the XY circle of the upright cup wall;
5. validates the fitted radius against the known cup geometry;
6. sets the body origin Z from the known table top and cup height;
7. publishes a `PoseStamped` on `/cup_pose` with the original source stamp and `frame_id=world`;
8. writes a bounded per-sample summary and the selected PLY into the registered evidence root.

The node never publishes a default pose, the configured MJCF keyframe position, a MuJoCo truth
sample, or the last valid pose after a new failed calculation. A bad frame is recorded and skipped.
If no valid pose is produced before the startup deadline, the node exits nonzero. After the first
valid pose it continues publishing fresh valid observations until the workflow finishes or the
launch shuts it down.

## 7. Dynamic scene synchronization

The dynamic workflow continues to freeze exactly one fresh `/cup_pose` before motion. Its preflight
becomes a two-stage transaction:

1. Compare the perceived world Pose with the current lossless MuJoCo cup Pose. Reject position or
   orientation divergence above the existing dynamic-policy tolerances.
2. Only after that comparison passes, replace the `plastic_cup` Pose in the MoveIt task geometry,
   apply the world object, and read it back.
3. Run the existing three-source topic / simulator / Planning Scene consistency check twice before
   deriving targets or sending a motion goal.

Only the `plastic_cup` collision shadow changes. The table, pedestal, geometry primitives, colors,
place target, state transitions, controller configuration, and dynamic grasp policy remain
unchanged.

This ordering retains MuJoCo as the independent physical truth source. Perception cannot silently
move the Planning Scene to an arbitrary pose and then pass its own consistency check.

## 8. Launch lifecycle

Add a thin public launch entry point named
`so101_mujoco_perception_pick_place.launch.py`. It reuses the existing MuJoCo stack construction and
adds only the perception strategy composition.

For each run the launch:

1. validates execute mode, explicit execute confirmation, session ID, evidence paths, and the
   initial keyframe;
2. starts `robot_state_publisher`, MuJoCo, controllers, MoveIt, and initial Planning Scene setup;
3. starts the two static TF publishers;
4. after scene readiness, starts the long-running `rgbd_cup_pose` node and
   `dynamic_cup_pick_place` with a bounded pose deadline;
5. passes `expected_reset_epoch=0`, the shared session ID, and the run evidence directory to the
   dynamic workflow;
6. shuts down the complete owned graph when the workflow or any required predecessor exits;
7. preserves exact process exit codes and failure ownership in the run log.

Final Mac acceptance uses `headless=false`, because CameraPlugin must render real camera frames in
the logged-in graphical session. Headless tests may validate contracts but cannot satisfy the final
RGB-D or visual gate.

## 9. Failure handling

The workflow must stop before robot motion when any of these occur:

- the named keyframe is absent;
- camera publishers exist but no real aligned messages arrive;
- RGB/depth payloads or camera intrinsics are invalid;
- TF is missing at the image timestamp;
- segmentation, clustering, or radius fitting fails;
- `/cup_pose` is stale, non-finite, outside the workspace, or inconsistent with MuJoCo;
- Planning Scene apply or read-back does not converge;
- MoveIt or controller readiness is missing.

After motion begins, existing state-machine recovery and physical safety gates remain authoritative.
If the cup is physically held without support, failure handling stops and retains evidence rather
than automatically opening the gripper or resetting the world. A failed run is retained and a new
session is required before retrying that keyframe.

The implementation must not use broad process cleanup, delete evidence, replace user-owned dirty
files, or alter the fixed pick-place workflow.

## 10. Test strategy

Implementation follows RED -> GREEN tests at the smallest owning boundary.

### Unit and contract tests

- all four MJCF keyframes contain zero robot joints and only the intended cup free-joint Pose;
- the rendered URDF carries the selected initial keyframe and defaults to `task_start`;
- the composed static TF matches the MJCF camera extrinsics and ROS optical convention;
- RGB-D matching rejects mismatched stamps, frames, sizes, encodings, and strides;
- point-cloud reconstruction, orange segmentation, DBSCAN selection, transform, circle fitting,
  radius validation, and no-publication failure paths are deterministic;
- perception/MuJoCo divergence prevents Planning Scene mutation;
- a valid perception/MuJoCo pair updates only the cup shadow and passes read-back;
- launch event ordering starts no dynamic workflow before scene readiness and propagates every
  predecessor failure;
- existing fixed and dynamic entry points retain their current defaults and gates.

### Package and installation tests

- run directed pytest files first;
- run the complete `src/so101_demo_py/test` suite;
- build with `colcon build --packages-select so101_demo_py --symlink-install`;
- re-source the installed overlay;
- prove the new launch file and `rgbd_cup_pose` executable resolve from the new install;
- record package and pinned-fork prefixes plus runtime executable paths;
- run `git diff --check` without formatting unrelated files.

## 11. Four-position runtime acceptance

Create one persistent experiment ledger at
`docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md`. It registers the single
evidence root and records every planned, valid, failed, or invalid run with source commit, installed
overlay, runtime executable, `ROS_DOMAIN_ID`, session ID, keyframe, commands, exit codes, and
evidence paths.

Each of the four keyframes receives an independent `FULL_RESTART` run. A run counts only when all
of the following agree:

1. **Provenance:** source, installed package and fork, session, domain, keyframe, and owned processes
   are recorded.
2. **Camera:** CameraInfo, RGB, and depth contain aligned `640x480` samples in
   `task_camera_frame`; encodings are `rgb8` and `32FC1`; depth contains finite positive values.
3. **Point cloud:** the cup cluster satisfies configured gates, the fitted radius is accepted, and
   the selected PLY plus calculation summary are retained.
4. **Pose:** `/cup_pose` is produced by `rgbd_cup_pose`, not the test truth bridge; it is fresh,
   world-framed, and within the existing `0.01 m` position tolerance of both the selected keyframe
   and the current MuJoCo cup Pose.
5. **Workflow:** `dynamic_cup_pick_place` exits zero, reaches `DONE`, records the accepted Pose and
   derived targets, and contains the complete expected state trace.
6. **MoveIt and controllers:** planning and execution succeed; arm and gripper controllers remain
   active; joint and TCP samples change consistently with approach, grasp, lift, transport,
   release, and retreat.
7. **Physical outcome:** MuJoCo proves the cup left its initial region with the gripper, was released
   in the existing red target region, and is upright, table-supported, stable, and free of final
   fingertip contact.
8. **Planning Scene:** the cup completes its attach/detach lifecycle and ends detached as a world
   object at the final MuJoCo Pose.
9. **Visual evidence:** fresh, inspected images show the perception baseline, cup transport, and
   final released placement for the same session.
10. **Cleanup:** the run-owned graph exits and no run-owned ROS node or process remains before the
    next full restart.

Missing provenance, duplicate stacks, wrong session/reset epoch, stale screenshots, unavailable
camera payloads, or mixed-run artifacts make a run invalid rather than successful. Any behavioral
failure makes the run a retained valid failure and ends that attempt.

## 12. Evidence and reporting

Ordinary logs, one-shot topic payload summaries, four selected PLY files, and screenshots stay under
the registered `/tmp` evidence root. No high-frequency rosbag or lossless stream recording is
planned. If later debugging requires such evidence, this task must first migrate to one registered
persistent `/data/work/so101-evidence/...` root with a hashed migration manifest; it may not split
evidence across roots.

The final report separates:

- code and package test status;
- installed/runtime provenance;
- one result row for each keyframe;
- camera, point-cloud, TF, workflow, physical, Planning Scene, controller, and visual facts;
- preserved user changes;
- retained runs, archived runs, and deletion candidates.

No evidence is deleted without explicit user authorization.
