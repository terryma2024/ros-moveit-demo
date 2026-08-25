# macOS MuJoCo RGB-D camera topics experiment ledger

```yaml
task_id: so101-v4-t005-macos-camera-topics
goal: Restore non-headless MuJoCo RGB-D camera publication on macOS while preserving Linux and headless behavior.
success_contract: With headless=false on Darwin, rendering remains enabled and task_camera CameraInfo, RGB, and floating-point depth messages contain aligned valid samples; shutdown joins rendering resources.
worktree: /Users/matianyi/.codex/worktrees/c727/moveit-demo
branch: codex/macos-mujoco-camera-topics
base_commit: 842fb05041d4ba487354cf0c6f9668db6e65a9fb
current_commit: 842fb05041d4ba487354cf0c6f9668db6e65a9fb
evidence_root: /tmp/so101-debug-v4-t005-macos-camera-topics/
confirmed_conclusions:
  - The Darwin launch guard deterministically sets disable_rendering=true for interactive launches, suppressing the camera worker despite publisher registration.
  - Cocoa UI-task dispatch reaches the process main thread; the current desktop execution environment blocks inside upstream mj::Simulate GUI construction before camera activation.
disproven_routes:
  - Removing the Darwin condition without changing GLFW ownership is not an acceptable repair.
open_hypotheses:
  - H1: the Darwin launch guard deliberately prevents GLFW/Cocoa window-context creation from the existing background rendering thread; it also disables all camera publishers.
  - H2: a main-thread-owned macOS rendering context can preserve camera publication without relaxing the Cocoa constraint.
  - H3: a headless/offscreen MuJoCo context can publish camera images on Darwin without a GLFW window, but must be verified against the pinned MuJoCo API.
latest_checkpoint: CP-004
next_experiment: BLOCKED-LOCAL-GUI
```

## Baseline / competing hypotheses

The known repro is a Darwin, `headless=false` launch whose rendered URDF contains
`disable_rendering=true`. The control plugin still registers `task_camera`, but its documented
disable-rendering branch prints `Camera and lidar rendering is disabled`, so the camera topics
have publishers but no frames.

| Hypothesis | Prediction | Distinguishing evidence |
| --- | --- | --- |
| H1 — existing safety guard | Enabling the existing worker-owned GLFW path on macOS violates Cocoa main-thread requirements or fails during GLFW lifecycle. | Trace `on_activate -> cameras_->init -> glfwInit -> rendering_thread_`; reproduce with only that variable changed. |
| H2 — main-thread GUI ownership | Moving window/context ownership to the control node's main thread removes the Darwin failure and camera thread can render safely. | Source/API test and live launch with window/context creation thread recorded. |
| H3 — offscreen rendering | MuJoCo can create a non-GLFW offscreen context on Darwin that supports readpixels for cameras. | Pinned MuJoCo build/API inspection plus end-to-end image/depth samples. |

## Experiments

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: H1 is responsible for the observed no-message topics, and a source-level test currently encodes the safety guard rather than the desired Darwin camera contract.
prediction: The installed/source contract renders disable_rendering=true for Darwin interactive mode; the fork source is unavailable until this worktree's locked submodule is initialized.
single_variable: NONE
lifecycle: ISOLATED_STACK
preconditions:
  - No MuJoCo or ROS processes owned by this task are running.
  - The current independent worktree is at 842fb05041d4ba487354cf0c6f9668db6e65a9fb.
success_criteria:
  - Record source, lock, and installed-overlay provenance before changing code.
failure_criteria:
  - The launch contract does not encode the reported Darwin behavior.
invalid_criteria:
  - Git commands resolve the primary checkout rather than this worktree.
provenance:
  source_commit: 842fb05041d4ba487354cf0c6f9668db6e65a9fb
  install_overlay: PENDING
  runtime_executable: PENDING
  ros_domain_id: PENDING
  gz_partition: PENDING
commands:
  - git --git-dir=<worktree-git-dir> --work-tree=<worktree> submodule update --init -- third_party/mujoco_ros2_control
  - pytest test_launch_composition.py::test_mujoco_rendering_is_enabled_for_interactive_macos_camera_stack
observed:
  - The RED assertion expected disable_rendering=false but the baseline rendered true for platform_name=darwin.
  - The fork at 78758d5 creates its GLFW camera window in rendering_thread_.
inferred: H1 supported
conclusion: The launch-level Darwin guard is the nearest regression boundary and must be replaced by a main-thread-safe fork capability.
evidence:
  - /tmp/so101-debug-v4-t005-macos-camera-topics/
decision: PENDING
next_experiment: EXP-002
```

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: H2 can preserve Cocoa ownership by creating the hidden GLFW camera window on the process main thread before the worker makes its context current.
single_variable: Main-thread window ownership and handoff in mujoco_ros2_control.
lifecycle: ISOLATED_STACK
commands:
  - colcon build --base-paths third_party/mujoco_ros2_control --packages-select mujoco_ros2_control
  - ctest --test-dir /tmp/so101-debug-v4-t005-macos-camera-topics/fork-build-py311/mujoco_ros2_control -R headless_init --output-on-failure
observed:
  - Initial post-sim_ready handoff caused a circular wait (on_init waits for sim_ready before camera registration).
  - Final handoff creates the hidden window in the UI task before sim_ready, then attaches it to MujocoCameras after registration.
  - Fork rebuild exited 0; test_headless_init passed (1/1, 8.60 s).
inferred: H2 source architecture is compiled and retains headless behavior.
conclusion: VALID for build and directed regression; live rendering remains separately gated.
evidence:
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-021-fork-rebuild-main-context.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/ros-test-final/
next_experiment: EXP-003
```

```yaml
experiment_id: EXP-003
status: BLOCKED
prior_experiment: EXP-002
hypothesis: The current desktop GUI session permits the upstream non-headless Simulate constructor to return, enabling RGB-D topic sampling.
single_variable: Local macOS GUI-session availability.
lifecycle: ISOLATED_STACK
commands:
  - ros2 launch so101_demo_py so101_mujoco.launch.py headless:=false run_mode:=execute execute:=true
observed:
  - The installed launch resolved the current project and fork overlays and rendered disable_rendering=false.
  - mujoco_macos_ui logged both task submission and main-thread execution.
  - The task remained inside upstream mj::Simulate construction for more than 50 seconds; on_init timed out before camera activation, so the bounded camera probe received no samples.
  - SIGINT after this upstream pre-activation failure also aborts controller_manager's existing clock-sleep thread; this is not a clean-shutdown pass.
inferred: The missing condition is an interactive macOS GUI session/service available to the Codex process, not camera topic discovery or the Darwin disable guard.
conclusion: BLOCKED-LOCAL-GUI. Do not claim live RGB-D or shutdown acceptance.
evidence:
  - /tmp/so101-debug-v4-t005-macos-camera-topics/ros-live-dispatch/
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-020-camera-probe.log
next_experiment: Relaunch from a logged-in macOS desktop session with a usable WindowServer, then run macos_camera_topic_probe.py.
```

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-002
current_hypothesis: H2 is implemented; EXP-003 is blocked before the camera runtime becomes active.
working_tree_status: Git's default core.worktree points at the primary checkout; all Git operations for this task use the worktree-specific git-dir and explicit --work-tree.
owned_processes: NONE
preserved_processes: No pre-existing ROS/MuJoCo processes are owned by this task.
confirmed_conclusions:
  - RED and GREEN launch-contract regression tests completed.
  - The installed fork build and directed headless test completed.
disproven_routes:
  - A delayed post-sim_ready main-thread handoff deadlocks.
open_risks:
  - Live RGB-D samples and clean shutdown require a graphical macOS session; neither is verified in this Codex process.
  - The local r9 fork tag and commit are intentionally unpushed.
next_command: Run the installed launch from a logged-in GUI terminal, then invoke src/so101_demo_py/test/macos_camera_topic_probe.py with the same ROS domain.
```
