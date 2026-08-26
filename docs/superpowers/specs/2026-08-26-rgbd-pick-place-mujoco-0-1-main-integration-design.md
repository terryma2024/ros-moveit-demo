# RGB-D Pick-Place on mujoco_ros2_control 0.1.0 Main Integration Design

**Date:** 2026-08-26

**Status:** Approved

**Parent baseline:** `origin/main@b73748f86acc891711aa455fc911a9ebde52686d`

**Perception baseline:** `origin/codex/rgbd-perception-pick-place@0649f3bdf4e321eb488154ec17484366d0da3895`

**mujoco_ros2_control target:** `origin/main@5e9d67ce9fde39d35bf94cc498721abf203a0ddd`

**Evidence root:** `/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/`

## Objective

Integrate the already-qualified RGB-D perception pick-place chain with the repository's
`mujoco_ros2_control` 0.1.0 upgrade line and prove that all four configured cup start positions
complete one physical pick-place through the installed runtime on both macOS and ai-station:

- `task_start`: `(0.02, -0.28, 0.165)`;
- `cup_test_forward_5cm`: `(0.02, -0.33, 0.165)`;
- `cup_test_left_5cm`: `(-0.03, -0.28, 0.165)`;
- `cup_test_right_5cm`: `(0.07, -0.28, 0.165)`.

The production data flow remains:

```text
MuJoCo -> RGB-D -> segmented point cloud -> tf2 -> /cup_pose
       -> dynamic_cup_pick_place -> MoveIt -> controller -> MuJoCo
```

## Version and provenance decision

The child repository's `main@5e9d67c` is a two-parent merge that contains the previously qualified
SO-101 commit `aeff7e5` as a parent. Its source tree is byte-for-byte identical to `aeff7e5`.
Therefore the integration advances the parent gitlink and both dependency locks to `5e9d67c` so the
project follows the formal child `main`, while retaining the exact code that passed the existing
macOS and Linux 0.1.0 qualification.

The lock's `fork.tag` provenance label changes from the no-longer-current candidate label to
`main`; reproducibility still comes from the immutable full commit hash, never from resolving the
moving branch name at build or runtime.

Acceptance must prove all three references agree:

1. parent gitlink `third_party/mujoco_ros2_control`;
2. `src/so101_demo_py/config/dependency-lock.yaml`;
3. `src/so101_demo_py/config/mujoco/dependency-lock.yaml`.

No floating branch lookup is allowed at runtime. The installed overlay and executable paths must be
traced back to the final integration commit and child commit `5e9d67c`.

## Integration strategy

Create `codex/rgbd-pick-place-mujoco-0-1-main` from parent `main@b73748f` and merge the completed
perception branch with `--no-ff`. Keeping both histories preserves the prior RGB-D experiment ledger
and the 0.1.0 upgrade qualification rather than reconstructing either line with selective
cherry-picks.

The two branches overlap in one production contract test:
`src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py`. The resolved file must retain both:

- 0.1.0 CameraPlugin/lifecycle/interface expectations from parent `main`;
- task-camera RGB-D configuration and perception expectations from the RGB-D branch.

All other conflicts, if Git reports any, are treated as an integration defect and resolved at the
smallest owning boundary. The merge must not alter grasp geometry, motion policy, place target,
controller configuration, camera calibration, or failure recovery unless a reproducible 0.1.0
compatibility failure first establishes a RED test.

## Runtime architecture retained from the perception branch

Each acceptance run starts a fresh owned graph. The selected MJCF keyframe initializes the physical
cup before simulation epoch zero. CameraPlugin publishes aligned `640x480` `rgb8` and `32FC1`
messages in `task_camera_frame`. `rgbd_cup_pose` reconstructs and segments the point cloud, applies
the timestamped `world <- task_camera_frame` transform, fits the upright cup, and publishes a fresh
world-framed `/cup_pose`.

`dynamic_cup_pick_place` compares that perceived pose against independent MuJoCo truth before it is
allowed to update the MoveIt cup shadow. The existing workflow then derives dynamic targets,
executes through MoveIt and the arm/gripper controllers, validates physical lift and transport,
detaches the planning shadow before release, and synchronizes the final world object from MuJoCo.

The static transform contract remains:

```text
base -> camera_link
  xyz = (0.65, -0.65, 0.3600814)
  rpy = (0, 0.517, 2.35619449)

camera_link -> task_camera_frame
  xyz = (0, 0, 0)
  rpy = (-1.57079633, 0, -1.57079633)
```

## Failure and ownership boundaries

Perception remains fail closed. Missing or invalid camera samples, TF lookup failure, segmentation
failure, stale `/cup_pose`, divergence from MuJoCo truth, or Planning Scene non-convergence stops the
run before motion. After motion begins, the existing physical safety gates own recovery; an
unsupported held cup is never released merely to simplify cleanup.

Every run uses a distinct `ROS_DOMAIN_ID`, `GZ_PARTITION`, session ID, install overlay, and run
directory under the registered evidence root. Only processes and tmux panes created by this task may
be stopped. Existing ai-station worktrees, tmux sessions, Codex processes, and user stacks are
preserved.

## Automated verification

Implementation follows RED -> GREEN at the version contract boundary:

1. add an assertion that the dependency lock and gitlink select child `main@5e9d67c`;
2. observe that assertion fail on `b73748f`, which still selects `aeff7e5`;
3. advance the gitlink and both locks to `5e9d67c`;
4. merge the RGB-D branch and resolve the camera contract test by retaining both lines' assertions;
5. run directed version, camera, RGB-D, TF, keyframe, launch, scene-sync, and runner tests;
6. build an isolated `so101_demo_py` install and run the complete package suite with nonzero test
   discovery;
7. prove installed launch files and executables resolve from that isolated install;
8. run `git diff --check` and validate a clean intended worktree.

On macOS, `/tmp` resolves to `/private/tmp`; build and install commands use the canonical path so
the installed provenance manifest and `ament_index` resolve identically. This is the same registered
evidence root, not a second evidence location.

## macOS acceptance

The Mac must run the exact committed candidate through a fresh isolated project/fork install, not
the source tree or an older workspace overlay. CameraPlugin runs with `headless=false` in the
logged-in graphical session so real MuJoCo rendering produces the RGB-D messages.

Four independent `FULL_RESTART` runs cover `task_start`, `cup_test_forward_5cm`,
`cup_test_left_5cm`, and `cup_test_right_5cm`. Each run uses a distinct ROS domain, session ID, and
owned process graph, and must satisfy the same camera, point-cloud, TF, `/cup_pose`, dynamic
workflow, MoveIt, controller, MuJoCo physical, Planning Scene, fresh-visual, and shutdown gates
listed below for ai-station. All four Mac positions are mandatory; Mac build/tests or one
default-position run cannot substitute for them.

## ai-station acceptance

The candidate is transferred to a new isolated ai-station worktree or clone without changing the
canonical `/data/work/ws_moveit`. A fresh fork/project build must prove the child checkout is exactly
`5e9d67c` and the installed package comes from the candidate source.

Five consecutive `FULL_RESTART` runs use the same commit, policies, and acceptance contract:

1. `task_start`;
2. `cup_test_forward_5cm`;
3. `cup_test_left_5cm`;
4. `cup_test_right_5cm`;
5. `task_start` repeat as the SO-101 five-run stability gate.

The first four runs satisfy the requested position coverage. The fifth adds stability evidence and
does not replace any position result. A run is countable only when all of these agree:

- exact source, child commit, installed prefix, executable, domain, partition, session, and keyframe;
- real aligned CameraInfo/RGB/depth samples with finite positive depth;
- segmented point-cloud and accepted cup fit with retained summary/PLY evidence;
- fresh `world` `/cup_pose` produced by `rgbd_cup_pose`, within the existing tolerance of MuJoCo;
- zero-exit `dynamic_cup_pick_place`, complete state trace, and `DONE`;
- MoveIt plan/execute plus active arm/gripper controllers and consistent joint/TCP motion;
- MuJoCo lift, transport, release, stable final placement, and no final physical attachment;
- MoveIt attach/detach/world synchronization ending at the MuJoCo pose;
- a fresh inspected screenshot for that session;
- clean shutdown of only the run-owned graph before the next restart.

An invalid environment or provenance run is retained as `INVALID` and does not count. A valid
behavioral failure ends the consecutive batch. A replacement batch receives new experiment IDs;
historical records are never rewritten.

## Publication and completion

Completion requires the integration branch to be clean, committed, pushed to Gitee, and read back
from the remote. Publication evidence is reported separately from functional evidence. The final
report lists each Mac position, each ai-station position, the ai-station fifth stability run,
automated test counts, installed provenance, camera/point-cloud/TF/workflow/MoveIt/controller/
MuJoCo/visual evidence, clean shutdown, preserved user changes, retained evidence, archived
evidence, and deletion candidates.

No evidence is deleted without explicit user authorization.
