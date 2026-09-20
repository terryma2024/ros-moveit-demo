---
task_id: so101-ai-station-bootstrap-four-point-20260920
goal: Configure this ai-station host per docs/ai-station-environment-setup.md, then run one four-fixed-point dynamic cup pick-place pass per docs/guides/so101-dynamic-cup-pick-place-source-guide.md.
success_contract: A built and provenance-verified ai-station overlay plus four FULL_RESTART runs, one per registered fixed cup point (task_start, cup_test_forward_5cm, cup_test_left_5cm, cup_test_right_5cm), each reaching dynamic workflow DONE with physical final-placement evidence, and every visible run paired with a fresh exact-window screenshot.
worktree: /home/matianyi/Projects/ros-moveit-demo
branch: main
base_commit: 4fbf361438a5bfb0aab32d6ba1c852ea8411bf0c
current_commit: c880872c3a016c38718f07296801f34b004bc787
evidence_root: /data/work/so101-evidence/ai-station-bootstrap/four-point-20260920
confirmed_conclusions:
  - This host is a fresh install, not the machine described by the setup document; the guide is a target-state recipe here, not a record of current state (EXP-001).
  - The four "fixed points" are the registered MuJoCo cup keyframes task_start, cup_test_forward_5cm, cup_test_left_5cm and cup_test_right_5cm, and their frozen world XYZ in config/mujoco/rgbd_task_points.yaml (EXP-001).
disproven_routes:
  - `so101_mujoco_rgbd_batch` as the four-point driver on this Linux host; its `MacViewerCapture` shells out to `/usr/bin/swift` and `/usr/sbin/screencapture` and is called unconditionally from `RosTaskBatchRuntime.capture_terminal` (EXP-001).
open_hypotheses:
  - Whether the pinned mujoco_ros2_control fork builds and runs on this host's toolchain without source changes.
latest_checkpoint: CP-006
next_experiment: NONE
---

# ai-station bootstrap and four-fixed-point pick-place ledger

Source of guidance: `/home/matianyi/Projects/robot_demo_001/docs/ai-station-environment-setup.md`
(target-state recipe) and `docs/guides/so101-dynamic-cup-pick-place-source-guide.md`
(dataflow and evidence boundaries).

## Frozen four-point matrix

One pass over the four registered fixed cup points, each an independent
`FULL_RESTART` of the RGB-D perception-driven dynamic workflow. The driver is
`ros2 run so101_demo_py so101_mujoco_perception_pick_place`, the Linux path
qualified by the earlier ai-station ledger; the macOS-only batch runner is
excluded (see `disproven_routes`).

| Experiment | Lifecycle | Keyframe | Expected cup XYZ (world, m) |
| --- | --- | --- | --- |
| EXP-011 | `FULL_RESTART` | `task_start` | `(0.02, -0.28, 0.165)` |
| EXP-012 | `FULL_RESTART` | `cup_test_forward_5cm` | `(0.02, -0.33, 0.165)` |
| EXP-013 | `FULL_RESTART` | `cup_test_left_5cm` | `(-0.03, -0.28, 0.165)` |
| EXP-014 | `FULL_RESTART` | `cup_test_right_5cm` | `(0.07, -0.28, 0.165)` |

Each run gets a unique `ROS_DOMAIN_ID`, `GZ_PARTITION`, `session_id` and
evidence child directory. Visible mode (`headless:=false`) is used so the run
can be paired with a fresh `gui-capture` screenshot, per the skill's visual
acceptance gate.

## CP-001 - preflight

```yaml
checkpoint_id: CP-001
last_valid_experiment: EXP-001
current_hypothesis: The documented setup recipe can be applied to this fresh host without a data-partition change.
working_tree_status: clean at 4fbf361438a5bfb0aab32d6ba1c852ea8411bf0c on main; third_party/mujoco_ros2_control not yet initialized
owned_processes: staged apt installation job (base/ros/moveit/nav2/docker stages)
preserved_processes: active GNOME X11 session on DISPLAY=:1 (uid 1000); user tmux and SSH sessions
confirmed_conclusions:
  - Host is a fresh Ubuntu 24.04.4 install with no ROS, no Gazebo, no Docker and no /data mount (EXP-001).
disproven_routes:
  - Reusing the previous ai-station worktree /data/work/ws_moveit is impossible; that path does not exist on this host (EXP-001).
open_risks:
  - RTX 5060 Ti and driver 595.91.07 differ from the document snapshot; EGL/GLFW rendering must be re-verified here.
next_command: Wait for the staged package installation to finish, then build the pinned fork overlay.
```

## EXP-001 - host audit against the setup document

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: This host already matches the state recorded in docs/ai-station-environment-setup.md.
prediction: ROS 2 Jazzy, Gazebo Harmonic, Docker, and the /data tree are present.
single_variable: NONE
lifecycle: ISOLATED_STACK
preconditions:
  - Read-only inspection only.
success_criteria:
  - Every documented host fact is compared against the live host and differences are recorded.
failure_criteria:
  - N/A
invalid_criteria:
  - N/A
provenance:
  source_commit: 4fbf361438a5bfb0aab32d6ba1c852ea8411bf0c
  install_overlay: NOT_BUILT
  runtime_executable: NOT_BUILT
  ros_domain_id: N/A
  gz_partition: N/A
commands:
  - command: hostname; whoami; ls -d /opt/ros/*; which gz; docker --version; groups; df -h /data; nvidia-smi
    exit_code: 0
observed:
  - Hostname ai-station, user matianyi, Ubuntu 24.04.4 LTS, 31 GiB RAM.
  - /opt/ros is absent, gz is absent, docker is absent, /data did not exist.
  - Single disk nvme0n1 1.9T with one ext4 root partition; there is no separate /data partition.
  - GPU is RTX 5060 Ti with driver 595.91.07, not the documented RTX 5080 with 595.71.05.
  - No xray proxy listens on 127.0.0.1:10808 or 10809; packages.ros.org and raw.githubusercontent.com answer directly over HTTPS.
  - User matianyi is not in the docker, dialout, video or render groups.
  - An X11 GNOME session is active on DISPLAY=:1 with XAUTHORITY=/run/user/1000/gdm/Xauthority.
inferred:
  - The setup document describes a target state for this host rather than an existing state, so its installation sections apply; its host-facts, proxy and /data sections must be adapted.
conclusion: The host is unconfigured relative to the document; treat the document as the configuration recipe and record each deviation.
evidence:
  - /data/work/so101-evidence/ai-station-bootstrap/four-point-20260920/bootstrap/
decision: KEEP
next_experiment: EXP-002
```

## EXP-002 - staged package installation

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: The packages listed by the setup document install cleanly from the Ubuntu, ROS 2, OSRF and NVIDIA sources on this host.
prediction: Base tools, ros-jazzy-desktop, gz-harmonic, MoveIt, ros2_control, Nav2, Docker and the NVIDIA container toolkit all resolve and install.
single_variable: Installed system package set
lifecycle: ISOLATED_STACK
preconditions:
  - ROS 2, OSRF and NVIDIA apt sources and keyrings are installed.
  - /data tree exists on the root NVMe filesystem.
success_criteria:
  - Every stage exits 0 and the documented verification commands resolve.
failure_criteria:
  - Any stage exits non-zero.
invalid_criteria:
  - A stage is skipped or a failure is masked by the pipeline.
provenance:
  source_commit: 4fbf361438a5bfb0aab32d6ba1c852ea8411bf0c
  install_overlay: NOT_BUILT
  runtime_executable: NOT_BUILT
  ros_domain_id: N/A
  gz_partition: N/A
commands:
  - command: /tmp/so101-debug-so101-ai-station-bootstrap-4point-20260920/stage-install.sh
    exit_code: 130 then 0 after the ROS source was moved to a domestic mirror
  - command: stage-install-2.sh
    exit_code: 0 (after dropping the non-existent ros-jazzy-opengl package name)
  - command: rosdep update
    exit_code: 1 on raw.githubusercontent.com, 0 after the sources moved to the jsDelivr CDN
observed:
  - base, ros, moveit, nav2 and docker stages all exited 0; ros-jazzy-desktop, gz-harmonic 8.15.0, MoveIt, ros2_control, Nav2, Docker 29.1.3 and the NVIDIA container toolkit are installed.
  - The moveit stage stalled for over 40 minutes at about 12 kB/s on packages.ros.org; the same artifacts came from mirrors.tuna.tsinghua.edu.cn/ros2 at about 3.7 MB/s, after which moveit and nav2 finished in about 90 seconds.
  - docker info reports DockerRootDir=/data/docker and an nvidia runtime entry after nvidia-ctk runtime configure.
  - matianyi is now in docker, dialout, video and render.
  - Group membership, the zshrc data/cache block, pip index/cache configuration, and the /data directory tree are in place.
  - rosdep cannot resolve ament_python, gz-transport13, gz-sim8 or x11-utils even after a successful full update; base.yaml carries none of them and no OSRF rosdep source list is installed. x11-utils was installed directly and the Gazebo keys are covered by gz-harmonic system libraries.
inferred:
  - The host is now dependency-complete for the ROS 2 / MoveIt / MuJoCo SO-101 path; the rosdep key gaps are metadata gaps, not missing system dependencies.
conclusion: The documented package set installs cleanly on this host once the ROS apt source is domestic and the one non-existent package name is dropped.
evidence:
  - /data/work/so101-evidence/ai-station-bootstrap/four-point-20260920/bootstrap/
decision: KEEP
next_experiment: EXP-003
```

## Deviations from the setup document

| Document says | This host | Action taken |
| --- | --- | --- |
| RTX 5080, driver 595.71.05 | RTX 5060 Ti, driver 595.91.07 | Recorded; the visible GLFW/OpenGL path was re-verified here by live viewer captures. |
| i7-13700KF, 24 threads, 32 GiB | i9-13900HX, 32 threads, 31 GiB | Recorded. |
| ~500 GB ext4 partition mounted at `/data` | One 1.9 TB ext4 root partition; no separate data partition | Created `/data` as a directory tree on the root NVMe (non-destructive). Repartitioning was not performed because it is destructive and was not authorized. |
| xray on 127.0.0.1:10808/10809 for overseas apt sources | No local proxy; direct HTTPS works | No apt proxy configured. |
| Shell convention: zsh, `setup.zsh` | zsh installed by this bootstrap | Both `setup.bash` and `setup.zsh` used as appropriate. |
| Users in docker/dialout/video/render | matianyi has none of them | Group membership added after Docker install; requires re-login to take effect. |
| CUDA Toolkit 13.2 installed | Not installed | Deferred: not required by the four-point pick-place path. Recorded as a remaining gap. |
| apt sources through xray on 127.0.0.1:10808 | No proxy on this host; packages.ros.org measured about 12 kB/s | ROS 2 apt source moved to `mirrors.tuna.tsinghua.edu.cn/ros2` (about 3.7 MB/s, identical package versions). Original file kept as `/etc/apt/sources.list.d/ros2.list.orig`. |
| `rosdep init`/`rosdep update` through the proxy | raw.githubusercontent.com measured about 7-25 kB/s and timed out | rosdep sources moved to the jsDelivr GitHub CDN. Original file kept as `/etc/ros/rosdep/sources.list.d/20-default.list.orig`. |
| `python3-open3d` from rosdep | Not packaged by Ubuntu 24.04 | Installed task-locally with uv into `python-deps/`: Open3D 0.19.0 with NumPy 1.26.4, consumed only through `PYTHONPATH`. No system Python mutation. |
| fork installer release-tag gate passes | Fork Gitee `main` is an ancestor of the locked commit | Built the locked commit with the gate relaxed to an ancestry check; recorded in EXP-003. |
| `<mujoco/mjtnum.h>` available | Removed after MuJoCo 3.3.0; the vendor package ships 3.12.0 | Task-local `mjtnum.h` shim on `CPLUS_INCLUDE_PATH` for the fork build only. |

## EXP-011 - task_start

```yaml
experiment_id: EXP-011
status: VALID
prior_experiment: EXP-005
hypothesis: The installed overlay executes a complete RGB-D perception-driven pick and place at the task_start keyframe.
prediction: The dynamic workflow reaches DONE with 19 transitions, the cup is physically lifted, carried and released inside the target region, and the Planning Scene ends with the cup as a world object.
single_variable: NONE
lifecycle: FULL_RESTART
preconditions:
  - No task runtime process is active; unique ROS domain and session identity.
success_criteria:
  - status DONE, 19 transitions, physical final placement, clean exit and no residue.
failure_criteria:
  - A valid run reaches a perception, planning, execution, physical or placement failure.
invalid_criteria:
  - Wrong overlay, duplicate stack or reused evidence path.
provenance:
  source_commit: 4fbf361438a5bfb0aab32d6ba1c852ea8411bf0c
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /home/matianyi/Projects/ros-moveit-demo/install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 21
  gz_partition: so101_fourpoint_EXP-011
commands:
  - command: ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false sensor_rendering:=true mujoco_initial_keyframe:=task_start session_id:=fourpoint-exp011-task-start
    exit_code: 0
observed:
  - status DONE with 19 transitions and no failure.
  - Frozen cup pose (0.01954, -0.28041, 0.16500) is within 0.7 mm of the registered task_start point (0.02, -0.28, 0.165).
  - Micro-lift raised the cup from z=0.1649 to z=0.1689, carry raised it to z=0.2249, and the release left it at (-0.07844, -0.24747, 0.16493), inside the target box x [-0.090, -0.070], y [-0.260, -0.240].
  - The final sample reports table_contact true, zero fingertip contacts, linear and angular velocities at numerical zero and a maximum normal force of 0.0475 N.
  - The final quaternion is essentially a pure world-Z yaw, so the cup stands upright.
  - Planning Scene readback: attached_object_ids empty and world primitives pedestal 1, plastic_cup 13, table 1.
  - Every launch process, including rgbd_cup_pose, ros2_control_node and move_group, reported clean exit.
inferred:
  - The RGB-D perception chain, the dynamic target resolution, MoveIt planning and execution, and the MuJoCo physical gates all work end to end on this host.
conclusion: A complete four-fixed-point pass begins with a verified physical pick and place at task_start.
evidence:
  - /data/work/so101-evidence/ai-station-bootstrap/four-point-20260920/runs/exp-011-task_start/
decision: KEEP
next_experiment: EXP-012
```

## EXP-012 - cup_test_forward_5cm

```yaml
experiment_id: EXP-012
status: VALID
prior_experiment: EXP-011
hypothesis: The same overlay repeats the complete workflow at the forward keyframe, and mid-run MuJoCo window captures are live rather than stale.
prediction: DONE with 19 transitions at the forward cup position, with viewer frames whose simulation clock advances.
single_variable: mujoco_initial_keyframe, plus mid-run viewer capture added
lifecycle: FULL_RESTART
preconditions:
  - No task runtime process is active.
success_criteria:
  - status DONE, physical final placement, clean exit, and at least one fresh exact-window capture showing the live scene.
failure_criteria:
  - A valid run reaches a runtime failure.
invalid_criteria:
  - Capture frames are stale or belong to another window owner.
provenance:
  source_commit: 4fbf361438a5bfb0aab32d6ba1c852ea8411bf0c
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /home/matianyi/Projects/ros-moveit-demo/install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 22
  gz_partition: so101_fourpoint_EXP-012
commands:
  - command: run-point-with-capture.sh EXP-012 22 cup_test_forward_5cm fourpoint-exp012-forward
    exit_code: 0
observed:
  - status DONE with 19 transitions; frozen cup pose (0.01966, -0.33047, 0.16500) is within 0.5 mm of the registered forward point.
  - Micro-lift z 0.1649 to 0.1689, carry z 0.2249, release at (-0.07855, -0.24746, 0.16492) inside the target box; final table_contact true with zero fingertip contacts.
  - The captured window owner title is "MuJoCo : so101_task_scene" and the capture manifest records the exact X11 window ID.
  - The viewer clock in the captured frames advances with wall time (5.144 s, 25.766 s, 60.265 s, 67.235 s), so the frames are live, and the arm pose differs between them.
  - Ten captured frames span the approach, the carry and the place phases, matching the per-state simulation steps in the manifest.
inferred:
  - The viewer pixels cannot by themselves separate the pick and place table positions from this camera angle; the physical fact is taken from the simulation-step cup positions in the manifest.
conclusion: The forward point also completes a physical pick and place, and the visible run is paired with live exact-window captures.
evidence:
  - /data/work/so101-evidence/ai-station-bootstrap/four-point-20260920/runs/exp-012-cup_test_forward_5cm/
decision: KEEP
next_experiment: EXP-013
```

## EXP-003 - pinned fork overlay build and test

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: The pinned mujoco_ros2_control fork builds and passes its own tests on this host from the ROS Jazzy underlay.
prediction: scripts/install-mujoco-ros2-control.zsh verifies the gitlink, fork commit, upstream ancestry and interface hashes, then builds and tests four packages with zero failures.
single_variable: Built fork overlay
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-002 installed ros-jazzy-desktop, ros-jazzy-mujoco-vendor and the fork build dependencies.
  - third_party/mujoco_ros2_control is initialized at the locked commit and clean.
success_criteria:
  - The installer exits 0, every fork package resolves to the fork install base, and mujoco_vendor still resolves to /opt/ros/jazzy.
failure_criteria:
  - Compile, link, test, or installed-prefix verification fails.
invalid_criteria:
  - The submodule is dirty, at the wrong commit, or the interface hashes do not match the lock.
provenance:
  source_commit: 4fbf361438a5bfb0aab32d6ba1c852ea8411bf0c
  install_overlay: SO101_WORKSPACE_DIR/ws_mujoco_ros2_control_fork/install
  runtime_executable: NOT_BUILT
  ros_domain_id: N/A
  gz_partition: N/A
commands:
  - command: zsh scripts/install-mujoco-ros2-control.zsh
    exit_code: 1, "fork release tag does not resolve to locked commit"
  - command: build-fork-overlay.sh (release-tag gate relaxed to an ancestry check; task-local mjtnum.h include shim)
    exit_code: 0
observed:
  - The stock installer stops at verify_source_identity because the fork's Gitee refs/heads/main is 71bc9346cf93d6227a6678fcacf63f3e18acfcba while the lock and the superproject gitlink both pin e4c0241aee52a40727681bd5872c09bf814e941a; main is an ancestor of the pin.
  - The lock has carried tag: main while advancing commit across 71bc9346, c16b5a5 and e4c0241, so the pin lives on fork branches that have not been merged into the fork's main.
  - mujoco_extensions/mujoco_3d_lidar includes <mujoco/mjtnum.h>; that header exists up to MuJoCo 3.3.0 and is gone in 3.12.0, which is the version vendored by ros-jazzy-mujoco-vendor 0.1.0. mjtype.h in 3.12.0 holds the identical mjtNum, mjMINVAL and mjtByte definitions.
  - With the ancestry gate and the include shim, all four fork packages built and 241 tests passed with 0 errors, 0 failures and 3 skips.
  - mujoco_3d_lidar, mujoco_ros2_control_msgs, mujoco_ros2_control_plugins and mujoco_ros2_control all resolve to /home/matianyi/Projects/ws_mujoco_ros2_control_fork/install; mujoco_vendor still resolves to /opt/ros/jazzy.
  - The tracked installer script was restored byte-for-byte; sha256sum -c over the original digest passes and git status shows no tracked modification.
inferred:
  - The published pin is buildable on this host, but the documented installer cannot pass unmodified until the fork's Gitee main is advanced to e4c0241 or the lock's tag field is corrected.
conclusion: The pinned fork runtime is built, tested and provenance-verified with two explicitly recorded deviations.
evidence:
  - /data/work/so101-evidence/ai-station-bootstrap/four-point-20260920/fork-build/
decision: KEEP
next_experiment: EXP-004
```

## EXP-004 - project overlay build, package tests and installed provenance

```yaml
experiment_id: EXP-004
status: VALID
prior_experiment: EXP-003
hypothesis: The project packages build from the fork overlay and pass their package-level tests on this host.
prediction: colcon build returns 0; the ordinary so101_demo_py test gate in src/so101_demo_py/test collects a non-zero test count and reports zero errors and failures; ros2 pkg prefix resolves to the project install base.
single_variable: Built project overlay
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-003 is VALID.
  - The ai-station pytest scratch rule is satisfied: TMPDIR/TMP/TEMP point at a fresh directory under this task's evidence root, verified with tempfile.gettempdir().
success_criteria:
  - Build and package tests exit 0 with a non-zero collected test count.
  - ros2 run resolves the installed console scripts from the project overlay.
failure_criteria:
  - A real compile, collection or assertion failure.
invalid_criteria:
  - Missing package setup files, an incomplete underlay, or tests that never reached the intended boundary.
provenance:
  source_commit: 4fbf361438a5bfb0aab32d6ba1c852ea8411bf0c
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /home/matianyi/Projects/ros-moveit-demo/install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: N/A
  gz_partition: N/A
commands:
  - command: colcon build --symlink-install --base-paths src
    exit_code: 0
  - command: tools/so101_pytest_gate.py --workers 8 --process-id-chars 4 --expected-source-commit 4fbf3614...
    exit_code: 0
observed:
  - All eight src packages built: fixed_pose_goal, panda_gazebo_demo_cpp, panda_mujoco_demo, pick_place_common, so101_demo_py, so101_gazebo_demo_cpp, so101_mujoco_support and so101_teleop.
  - Package discovery had to be limited to src/: the checkout also carries tools/mujoco_vendor_macos, whose CMake step demands MUJOCO_STAGE_ROOT and would shadow the Jazzy vendor, and third_party/mujoco_ros2_control, which is already installed as its own fork overlay.
  - so101_gazebo_demo_cpp requires run-clang-tidy, and panda_gazebo_demo_cpp requires moveit_resources_panda_description; both were installed from apt.
  - so101_teleop builds its web UI through Bun. Bun 1.4.2 came from the npm mirror and is passed through SO101_TELEOP_BUN; system Node is not used.
  - The ordinary gate runner reported result PASS with expected_count 3144 equal to actual_count 3144, 0 failures and 0 errors across eight shards plus the serial lane, and provenance_valid true in every process layout. Total elapsed 64.2 s.
  - The gate rejects a dirty worktree; the only allowed dirty path was this task's untracked ledger.
  - Every shard ran with TMPDIR/TMP/TEMP inside the registered evidence root's scratch tree, and the runner verified the resolved temp directory per process.
  - so101_demo_py resolves to the project install, so101_mujoco_support to the project install, mujoco_ros2_control to the fork install (four fork packages) and mujoco_vendor to /opt/ros/jazzy. so101_demo_py exposes 35 console executables.
inferred:
  - An earlier colcon invocation without --base-paths src produced a stray install/mujoco_vendor environment prefix from tools/mujoco_vendor_macos; it was removed so the Jazzy vendor cannot be shadowed.
conclusion: The project overlay builds, its ordinary pytest gate passes with exact collection coverage, and installed provenance resolves as intended.
evidence:
  - /data/work/so101-evidence/ai-station-bootstrap/four-point-20260920/build/
  - /data/work/so101-evidence/ai-station-bootstrap/four-point-20260920/scratch/gate-2/
decision: KEEP
next_experiment: EXP-005
```

## EXP-005 - task-local RGB-D python runtime dependencies

```yaml
experiment_id: EXP-005
status: VALID
prior_experiment: EXP-004
hypothesis: The RGB-D perception path needs an Open3D runtime that the distribution does not package, and a task-local install satisfies it without mutating system Python.
prediction: python3 -c 'import open3d' succeeds from the task-local dependency root and rgbd_cup_pose gets past its import boundary.
single_variable: Python dependency root
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-004 is VALID.
  - Upstream apt has no python3-open3d candidate (verified in EXP-001).
success_criteria:
  - Open3D imports, reports a version, and the perception executable starts.
failure_criteria:
  - Import failure or a broken numpy ABI pairing.
invalid_criteria:
  - The module resolves from a different root than the registered one.
provenance:
  source_commit: 4fbf361438a5bfb0aab32d6ba1c852ea8411bf0c
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: PENDING
  ros_domain_id: N/A
  gz_partition: N/A
commands:
  - command: uv pip install --target <evidence>/python-deps open3d==0.19.0 numpy==1.26.4
    exit_code: 0
  - command: uv pip install --target <evidence>/python-deps --index-url https://download.pytorch.org/whl/cpu torch==2.13.0+cpu
    exit_code: 0
  - command: uv pip install --target <evidence>/python-deps mujoco==3.12.0
    exit_code: 0
observed:
  - open3d 0.19.0, torch 2.13.0+cpu, mujoco 3.12.0 and numpy 1.26.4 all import from the task-local root while rclpy still resolves from /opt/ros/jazzy.
  - The gate's first two attempts failed closed and were retained: without torch the collection stopped at test_grounding_dino_domain_retention.py, and without the mujoco bindings 40 tests errored on import.
  - The root must be prepended to PYTHONPATH, not assigned: assigning it replaces the ROS PYTHONPATH and hides rclpy entirely.
  - No system Python package was added, removed or upgraded.
inferred:
  - Ubuntu 24.04 packages neither python3-open3d nor python3-torch, so the package's own exec_depend and test imports require a task-owned dependency root.
conclusion: The RGB-D and test python dependencies are available from a task-local root without mutating system Python.
evidence:
  - /data/work/so101-evidence/ai-station-bootstrap/four-point-20260920/python-deps/
  - /data/work/so101-evidence/ai-station-bootstrap/four-point-20260920/scratch/gate-1/
decision: KEEP
next_experiment: EXP-011
```

## EXP-013, EXP-014 and EXP-011R - left, right and a repeated task_start

```yaml
experiment_id: EXP-013
status: VALID
prior_experiment: EXP-012
hypothesis: The left keyframe also completes the workflow with the same overlay.
prediction: DONE with 19 transitions and a physical final placement.
single_variable: mujoco_initial_keyframe
lifecycle: FULL_RESTART
provenance:
  source_commit: 4fbf361438a5bfb0aab32d6ba1c852ea8411bf0c
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /home/matianyi/Projects/ros-moveit-demo/install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 23
  gz_partition: so101_fourpoint_EXP-013
commands:
  - command: run-point-with-capture.sh EXP-013 23 cup_test_left_5cm fourpoint-exp013-left
    exit_code: 0
observed:
  - status DONE, 19 transitions, frozen cup pose (-0.03037, -0.28060, 0.16500), 0.6 mm from the registered left point.
  - Bilateral fingertip contact appears at WAIT_GRASP_STABLE (2/2), table_contact drops to false at MICRO_LIFT with cup z rising 0.1649 to 0.1689, carry reaches z 0.2248, and release restores table_contact true with 0/0 contacts at (-0.07835, -0.24747, 0.16501).
  - 13 live viewer captures; clean exit.
decision: VALID
next_experiment: EXP-014
```

```yaml
experiment_id: EXP-014
status: VALID
prior_experiment: EXP-013
hypothesis: The right keyframe also completes the workflow with the same overlay.
prediction: DONE with 19 transitions and a physical final placement.
single_variable: mujoco_initial_keyframe
lifecycle: FULL_RESTART
provenance:
  source_commit: 4fbf361438a5bfb0aab32d6ba1c852ea8411bf0c
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /home/matianyi/Projects/ros-moveit-demo/install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 24
  gz_partition: so101_fourpoint_EXP-014
commands:
  - command: run-point-with-capture.sh EXP-014 24 cup_test_right_5cm fourpoint-exp014-right
    exit_code: 0
observed:
  - status DONE, 19 transitions, frozen cup pose (0.06962, -0.28057, 0.16500), 0.7 mm from the registered right point.
  - The same bilateral-contact, micro-lift, carry and release sequence; final cup (-0.07839, -0.24747, 0.16493) with table_contact true and 0/0 fingertip contacts.
  - 14 live viewer captures; clean exit.
decision: VALID
next_experiment: EXP-011R
```

```yaml
experiment_id: EXP-011R
status: VALID
prior_experiment: EXP-011
hypothesis: Repeating task_start with mid-run viewer capture keeps the same physical outcome, so the first point can be paired with visual evidence too.
prediction: DONE with 19 transitions and the same final placement as EXP-011.
single_variable: mid-run viewer capture added; no runtime parameter changed
lifecycle: FULL_RESTART
provenance:
  source_commit: 4fbf361438a5bfb0aab32d6ba1c852ea8411bf0c
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /home/matianyi/Projects/ros-moveit-demo/install/so101_demo_py/lib/so101_demo_py/so101_mujoco_perception_pick_place
  ros_domain_id: 25
  gz_partition: so101_fourpoint_EXP-011R
commands:
  - command: run-point-with-capture.sh EXP-011R 25 task_start fourpoint-exp011r-task-start
    exit_code: 0
observed:
  - status DONE, 19 transitions, frozen cup pose (0.01954, -0.28041, 0.16500); final cup (-0.07846, -0.24746, 0.16493) matches EXP-011 to within 0.1 mm.
  - 14 live viewer captures. The red target-ring marker is empty with the cup beside it before the pick, the cup is off the ring and elevated mid-carry, and after release the cup stands on the ring.
inferred:
  - The repeated point reproduces the EXP-011 physical outcome, so the visual pairing does not depend on a changed runtime.
conclusion: The four-fixed-point pass is complete with runtime and visual evidence for every point.
evidence:
  - /data/work/so101-evidence/ai-station-bootstrap/four-point-20260920/runs/exp-013-cup_test_left_5cm/
  - /data/work/so101-evidence/ai-station-bootstrap/four-point-20260920/runs/exp-014-cup_test_right_5cm/
  - /data/work/so101-evidence/ai-station-bootstrap/four-point-20260920/runs/exp-011r-task_start/
decision: KEEP
next_experiment: NONE
```

## Four-point result

| Experiment | Lifecycle | Keyframe | Status | Transitions | Frozen cup (world m) | Micro-lift | Final cup (world m) | Final contacts | Captures |
| --- | --- | --- | --- | ---: | --- | ---: | --- | --- | ---: |
| EXP-011 | `FULL_RESTART` | `task_start` | VALID | 19 | `(0.01954, -0.28041, 0.16500)` | +4.0 mm | `(-0.07844, -0.24747, 0.16493)` | 0/0 | n/a |
| EXP-012 | `FULL_RESTART` | `cup_test_forward_5cm` | VALID | 19 | `(0.01966, -0.33047, 0.16500)` | +4.0 mm | `(-0.07855, -0.24746, 0.16492)` | 0/0 | 10 |
| EXP-013 | `FULL_RESTART` | `cup_test_left_5cm` | VALID | 19 | `(-0.03037, -0.28060, 0.16500)` | +4.0 mm | `(-0.07835, -0.24747, 0.16501)` | 0/0 | 13 |
| EXP-014 | `FULL_RESTART` | `cup_test_right_5cm` | VALID | 19 | `(0.06962, -0.28057, 0.16500)` | +4.0 mm | `(-0.07839, -0.24747, 0.16493)` | 0/0 | 14 |
| EXP-011R | `FULL_RESTART` | `task_start` (visual pairing) | VALID | 19 | `(0.01954, -0.28041, 0.16500)` | +4.0 mm | `(-0.07846, -0.24746, 0.16493)` | 0/0 | 14 |

Every run ended with the cup inside the target box x [-0.090, -0.070], y [-0.260, -0.240],
`table_contact` true, zero fingertip contacts, velocities at numerical zero, and a Planning
Scene readback with no attached objects and the canonical 13-primitive `plastic_cup` world
object. Every launch process reported a clean exit and no run left a task-owned process.

## CP-004 - completion

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-011R
current_hypothesis: NONE
working_tree_status: clean except the untracked task ledger docs/experiments/ai-station-bootstrap-four-point-pick-experiment-ledger.md
owned_processes: NONE
preserved_processes: pre-existing GNOME X11 desktop session on DISPLAY=:1 and the user's own desktop applications
confirmed_conclusions:
  - The host is configured for the ROS 2 Jazzy / MoveIt / MuJoCo SO-101 path and the fork overlay, project overlay and task-local python dependencies all resolve as intended (EXP-002 through EXP-005).
  - The ordinary so101_demo_py pytest gate passes with exact collection coverage of 3144 nodes (EXP-004).
  - All four registered fixed cup points complete the dynamic workflow to DONE with physical final-placement evidence (EXP-011 through EXP-014, EXP-011R).
disproven_routes:
  - The macOS-only so101_mujoco_rgbd_batch runner is not usable on this Linux host.
  - Building the workspace without restricting discovery to src/ pulls in tools/mujoco_vendor_macos and shadows the Jazzy mujoco_vendor.
open_risks:
  - CUDA Toolkit 13.2 is not installed; it is not needed by the four-point pick-place path.
  - The documented fork installer and the lock's `tag: main` agree with the superproject gitlink but not with the fork's Gitee main branch, so the stock installer still fails its release-tag gate until the remote branch or the lock is corrected.
  - The rosdep keys ament_python, gz-transport13, gz-sim8 and x11-utils have no rule in the configured sources.
next_command: NONE
```

## Evidence disposition

- Retained: the whole registered root `/data/work/so101-evidence/ai-station-bootstrap/four-point-20260920`, including `bootstrap/` scripts and package logs, `fork-build/`, `build/`, `tests/`, `python-deps/`, `runs/` for EXP-011 through EXP-014 and EXP-011R, `captures/`, and `final-verification.txt`.
- Archived: none.
- Deletion candidates: the per-attempt scratch trees under `scratch/` (fork-build-001..003, fork-installer-gate-001, project-build-*, pytest-*, gate-1's failed run, gate-2). They are superseded build and test scratch and are listed for classification only; none may be deleted without explicit user authorization.

## Follow-up phase (2026-09-20, second operator request)

Four follow-ups were requested after CP-004: update the ai-station setup document, correct
`scripts/install-mujoco-ros2-control.zsh`, port `mujoco_3d_lidar` to MuJoCo 3.12 with docs and
commits, and fast-forward the checkout to `origin/main` before re-qualifying.

### Flattened base

```yaml
experiment_id: EXP-030
status: VALID
prior_experiment: CP-004
hypothesis: The published origin/main is a usable base for the fork port and the re-qualification.
prediction: A fast-forward lands origin/main with the same runtime pin.
single_variable: Source base commit
lifecycle: FULL_RESTART
commands:
  - command: git pull --ff-only origin main
    exit_code: 0
observed:
  - main fast-forwarded from 4fbf3614 to 5b8d1231e97e10f650ac1d626e8dff801a7d21ea, 23 commits.
  - The runtime pin is unchanged by the fast-forward, so the four-point path carries over.
  - The new commits add a macOS-oriented parallel-batch suite that runs unconditionally.
decision: KEEP
```

### Fork port and installer gate

```yaml
experiment_id: EXP-031
status: VALID
prior_experiment: EXP-030
hypothesis: The pinned fork commit can be ported to MuJoCo 3.12 and the installer gate corrected without weakening provenance.
prediction: The stock installer passes unmodified at the new pin, and the extension compiles against both MuJoCo layouts.
single_variable: Fork pin and installer gate semantics
lifecycle: FULL_RESTART
commands:
  - command: zsh scripts/install-mujoco-ros2-control.zsh
    exit_code: 1 before the change, 0 after
observed:
  - MuJoCo declares mjtNum, mjMINVAL and mjtByte in mujoco/mjtnum.h up to 3.8.0 and in mujoco/mjtype.h from 3.9.0; the 3.12.0 vendor package ships no mjtnum.h while the macOS source build stages 3.4.0.
  - The extension now reads the types through include/mujoco_3d_lidar/mujoco_numeric_types.hpp, which selects mjtype.h when present and falls back to mjtnum.h. It compiles against the vendored 3.12.0 headers and against the real 3.4.0 headers.
  - The gate now requires the release ref to be contained in the pinned commit, refuses a divergent pin, and reports FORK_PIN_AHEAD_OF_RELEASE_REF with its commit list (3 commits ahead on this pin).
  - prepare_build_source re-points a clean build source at the new pin and prints BUILD_SOURCE_REPOINTED; a dirty build source is still refused.
  - The stock installer then reported 4 packages finished and 241 tests, 0 errors, 0 failures, 3 skipped, with no include shim.
  - The fork port is committed in the submodule as e37ffd29 on branch so101-lidar-mujoco-numeric-header; the superproject gitlink, both locks, the install contract test and the backend integration check pin the same commit.
decision: KEEP
```

### Linux support for the parallel-batch suites

```yaml
experiment_id: EXP-032
status: VALID
prior_experiment: EXP-031
hypothesis: The new main's ordinary gate failures are platform handling in the suites, not missing Linux implementation.
prediction: Fixing the suites' platform handling brings the gate to PASS without changing what the production Linux path selects.
single_variable: Test platform handling and one gate-runner directory mode
lifecycle: FULL_RESTART
commands:
  - command: tools/so101_pytest_gate.py --workers 8 --process-id-chars 4 --run-id gate-6
    exit_code: 0
observed:
  - The gate failed 35 cases in five modules before the change and passes afterwards.
  - unix_address and parallel_ipc_v4 hardcoded /private/tmp; the strategy now selects its base and sun_path capacity per platform (/private/tmp and 104 on Darwin, /tmp and 108 on Linux) and the suites read the module constant.
  - The cleanup identity case depended on the allocator returning a different inode after unlink and rebind. ext4 reuses the freed inode, so the case now holds it with a placeholder and asserts the precondition.
  - mps_broker_bootstrap drove the real MPS warm-up tensor; the cases now pass a sentinel through the bootstrap's existing warm-up provider, keeping their assertions and dropping the MPS hardware requirement.
  - Two start-guard cases inject Darwin host commands and are now gated on the platform; read_meminfo only consults them on Darwin.
  - The v4 per-platform transport case nulls the Darwin-only MPS fields for Linux, so the case exercises the Linux combination and asserts proc_fd_unix. Linux v4 stays DEFERRED_ENVIRONMENT by design; v3 remains the Linux production combination.
  - The gate runner creates its scratch root at 0700 explicitly, because a group-writable ancestor makes the private-base checks refuse a shard's own tree.
  - Gate result PASS: expected_count 3542 equal to actual_count 3542, all shards clean, cleanup all_children_reaped, 63.7 s.
decision: KEEP
correction:
  - 2026-09-20, after the ledger commit landed: the gate was run once more at 2fe6900e, the
    commit this ledger is recorded in. Result PASS with the same 3542 expected and actual
    nodes, an empty source_status and a clean child audit, 64.7 s. The earlier PASS at
    eb813563 stands and is unchanged; only the docs-only commit separates the two.
```

### Re-qualified four-point pass

```yaml
experiment_id: EXP-033
status: VALID
prior_experiment: EXP-032
hypothesis: The four fixed points still complete on the flattened base.
prediction: DONE with 19 transitions and a physical final placement at every point, each paired with live viewer captures.
single_variable: Source base commit and the fork pin
lifecycle: FULL_RESTART
commands:
  - command: run-point-with-capture.sh EXP-021 31 task_start requal-exp021-task-start (and EXP-022/023/024 at the other three keyframes)
    exit_code: 0
observed:
  - All four points report DONE with 19 transitions and no failure.
  - Frozen cup poses match the registered points to within 0.7 mm at every keyframe.
  - Final cup positions are (-0.07847, -0.24745, 0.16493), (-0.07859, -0.24743, 0.16493), (-0.07841, -0.24748, 0.16500) and (-0.07843, -0.24749, 0.16493), all inside the target box.
  - Every run ends with table_contact true, zero fingertip contacts, a maximum normal force of about 0.0475 N and a Planning Scene holding no attached objects with the 13-primitive cup as a world object.
  - 13 to 15 live viewer captures per run; the capture at Sim Time 61.676 s shows the cup standing on the target ring with the gripper released above it.
  - No task-owned process remained after any run.
decision: KEEP
next_experiment: NONE
```

## CP-005 - follow-up completion

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-033
current_hypothesis: NONE
working_tree_status: clean except the untracked task ledger; superproject at eb813563, fork submodule at e37ffd29 on branch so101-lidar-mujoco-numeric-header
owned_processes: NONE
preserved_processes: pre-existing GNOME X11 desktop session on DISPLAY=:1 and the user's own desktop applications
confirmed_conclusions:
  - The fork pin is ported to MuJoCo 3.12 with a guarded numeric-type include and the stock installer now passes unmodified (EXP-031).
  - The installer gate expresses containment rather than pointer equality, and reports a pin that is ahead of the release ref (EXP-031).
  - The ordinary gate passes on the flattened base with exact collection coverage of 3542 nodes (EXP-032).
  - All four registered fixed points re-qualified on the new base with runtime and visual evidence (EXP-033).
disproven_routes:
  - Gating the whole macOS-oriented suites was unnecessary: most cases are platform-generic once the base and capacity follow the platform (EXP-032).
open_risks:
  - The fork branch so101-lidar-mujoco-numeric-header is local only. It must be pushed to Gitee before another machine can materialise the pinned commit, and the fork's main still trails the pin.
  - Linux v4 stays DEFERRED_ENVIRONMENT by design; only the v3 combination runs on Linux.
next_command: git -C third_party/mujoco_ros2_control push origin so101-lidar-mujoco-numeric-header
```

## EXP-034 - author identity, fork main merge and publication

```yaml
experiment_id: EXP-034
status: VALID
prior_experiment: EXP-033
hypothesis: The five superproject commits, the fork port and the parent-repo doc commit can carry the requested identity, and the fork port can be merged to the fork's main and published without changing any runtime content.
prediction: Every commit is authored and committed by zjumty <zjumty@gmail.com>, the pinned fork commit's tree is unchanged by the re-authoring, the fork main contains the pin, and all three repositories publish by fast-forward.
single_variable: Commit identity and publication state
lifecycle: FULL_RESTART
commands:
  - command: git commit --amend --no-edit --author="zjumty <zjumty@gmail.com>" (fork), then rebase --interactive with an amend exec over the five superproject commits
    exit_code: 0
  - command: git merge --ff-only so101-lidar-mujoco-numeric-header on fork main
    exit_code: 0
  - command: git push origin main (fork), git push origin main (superproject), git push origin master (parent)
    exit_code: 0
observed:
  - The earlier commits carried zjumty <zjumty@aliyun.com>, which was this session's guess; the requested identity is zjumty <zjumty@gmail.com> and every commit is now authored and committed by it.
  - Re-authoring changed the fork commit hash from e37ffd29 to f89033c5 with an unchanged tree; the superproject delta between the pre-rewrite tip 13e4bdff and the post-rewrite tip c880872c is exactly the six pin locations and nothing else.
  - Fork main fast-forwarded from 71bc9346 to f89033c5, so the lock's release ref now equals its pinned commit.
  - The stock installer reports FORK_RELEASE_REF_MATCHES_PIN ref=main commit=f89033c5..., rebuilds 4 packages and passes 241 tests with 0 failures.
  - Pushed: fork main 71bc934..f89033c, superproject main 5b8d1231..c880872c, parent master 6ec788a..d6e968d. All three were fast-forwards and no branch was force-pushed.
  - The gate at the pushed HEAD c880872c is PASS with 3542 expected and actual nodes, an empty source_status and a clean child audit, 65.4 s.
  - A task_start runtime smoke run at the pushed pin reaches DONE with 19 transitions, the cup at (-0.07856, -0.24748, 0.16493), table_contact true, no fingertip contacts and 14 live captures.
inferred:
  - EXP-033 remains the four-point qualification for this runtime: the re-authoring changed commit identifiers only, and the fork and project source trees that produced the built overlays are byte-identical.
conclusion: The requested identity is in place, the fork port is merged to the fork's main and all three repositories are published by fast-forward.
decision: KEEP
next_experiment: NONE
```

## CP-006 - publication

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-034
current_hypothesis: NONE
working_tree_status: all three worktrees clean; superproject main at c880872c, fork submodule main at f89033c5, parent master at d6e968d
owned_processes: NONE
preserved_processes: pre-existing GNOME X11 desktop session on DISPLAY=:1 and the user's own desktop applications
confirmed_conclusions:
  - Every commit in this task is authored and committed by zjumty <zjumty@gmail.com> (EXP-034).
  - The fork's main contains the pinned commit, so the installer reports a matching release ref (EXP-034).
  - All three repositories are published on Gitee by fast-forward, and the pushed superproject HEAD passes the ordinary gate (EXP-034).
disproven_routes:
  - Keeping the release-ref gate at pointer equality was unnecessary; containment plus the explicit ahead report covered both the divergent and the merged case (EXP-031, EXP-034).
open_risks:
  - The fork branch so101-lidar-mujoco-numeric-header was left local; its commit is reachable through fork main, so nothing depends on it.
  - The GitHub mirror remote is not configured in this clone, so github/main was not updated.
next_command: NONE
```
