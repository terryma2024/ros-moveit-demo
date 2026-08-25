# macOS MuJoCo RGB-D camera topics experiment ledger

```yaml
task_id: so101-v4-t005-macos-camera-topics
goal: Restore non-headless MuJoCo RGB-D camera publication on macOS while preserving Linux and headless behavior.
success_contract: With headless=false on Darwin, rendering remains enabled and task_camera CameraInfo, RGB, and floating-point depth messages contain aligned valid samples; shutdown joins rendering resources.
worktree: /Users/matianyi/.codex/worktrees/c727/moveit-demo
branch: codex/macos-mujoco-camera-topics
base_commit: 842fb05041d4ba487354cf0c6f9668db6e65a9fb
current_commit: project=1c36e0e8ebd5b25d345cb5655068b0ef20417590; fork=f19a8cc3af61feccacb22a9f0d16cc972e3b2c08 (so101-0.0.3-r11)
evidence_root: /tmp/so101-debug-v4-t005-macos-camera-topics/
confirmed_conclusions:
  - The Darwin launch guard deterministically sets disable_rendering=true for interactive launches, suppressing the camera worker despite publisher registration.
  - EXP-005 confirms the post-migration SIGBUS was an ABI mismatch in the legacy plugin base vtable, not a MuJoCo GL-context failure.
  - EXP-005 receives aligned valid 640x480 RGB-D samples in the logged-in Aqua session and shuts down cleanly.
disproven_routes:
  - Removing the Darwin condition without changing GLFW ownership is not an acceptable repair.
open_hypotheses:
  - H1: the Darwin launch guard deliberately prevents GLFW/Cocoa window-context creation from the existing background rendering thread; it also disables all camera publishers.
  - H2: a main-thread-owned macOS rendering context can preserve camera publication without relaxing the Cocoa constraint.
  - H3: a headless/offscreen MuJoCo context can publish camera images on Darwin without a GLFW window, but must be verified against the pinned MuJoCo API.
latest_checkpoint: CP-007
next_experiment: NONE
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
experiment_id: EXP-005
status: VALID
prior_experiment: EXP-004
hypothesis: SIGBUS is an ABI mismatch caused by adding rendering virtuals to MuJoCoROS2ControlPluginBase while the installed simulation_evidence plugin still has the r9 vtable.
prediction: The macOS crash report shows CameraPlugin initialized and waiting, while the faulting executor thread calls set_rendering_enabled on the next legacy plugin; preserving the base vtable and moving rendering controls to an optional interface will remove this crash without requiring all legacy plugins to rebuild.
single_variable: Rendering lifecycle methods move from the existing plugin base vtable to a separately cast optional capability interface.
lifecycle: ISOLATED_STACK
preconditions:
  - Project source commit is 1c36e0e8ebd5b25d345cb5655068b0ef20417590 and fork source commit is 44c4fb3ce4cd4706a6c0c179b86c48550a408c86.
  - No process from EXP-004 is owned by this task.
  - Live runtime intentionally includes the r9-built simulation_evidence plugin to exercise backwards compatibility.
success_criteria:
  - A source contract first fails because the base vtable contains the new rendering virtuals.
  - Rebuilt r10 loads CameraPlugin plus the existing legacy simulation_evidence plugin without SIGBUS.
  - The three task_camera topics deliver valid aligned samples and shutdown exits without crash or unjoined thread.
failure_criteria:
  - Crash remains at the same base virtual dispatch boundary or any camera payload contract fails.
invalid_criteria:
  - Runtime resolves a different fork library, project YAML or ROS domain than recorded.
provenance:
  source_commit: project=1c36e0e8ebd5b25d345cb5655068b0ef20417590; fork=44c4fb3ce4cd4706a6c0c179b86c48550a408c86
  install_overlay: /tmp/so101-debug-v4-t005-macos-camera-topics/fork-install-py311 and /tmp/so101-debug-v4-t005-macos-camera-topics/project-install-r10-isolated
  runtime_executable: /tmp/so101-debug-v4-t005-macos-camera-topics/fork-install-py311/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: 145
  gz_partition: NOT_APPLICABLE_MUJOCO
commands:
  - command: python3 -m pytest -q test_primary_monitor_guard.py -k optional_capability
    exit_code: 1 (expected RED)
  - command: colcon build --merge-install --packages-up-to mujoco_ros2_control mujoco_ros2_control_plugins
    exit_code: 0
  - command: ctest -R 'test_headless_init|test_primary_monitor_guard'
    exit_code: 0 (2/2)
  - command: colcon test --packages-select mujoco_ros2_control_plugins mujoco_ros2_control; colcon test-result --verbose
    exit_code: 0 (139 tests, 0 errors, 0 failures, 0 skipped)
  - command: launchctl asuser 501 ... ros2 launch so101_demo_py so101_mujoco.launch.py headless:=false run_mode:=execute execute:=true
    exit_code: 0 after bounded probe and SIGINT
  - command: macos_camera_topic_probe.py --timeout-s 25
    exit_code: 0
observed:
  - macOS crash report ros2_control_node-2026-08-25-105801.ips records EXC_BAD_ACCESS/SIGBUS, faulting thread 26 at MujocoSystemInterface::load_mujoco_plugins line 3558.
  - The same report shows CameraPlugin::update_loop already waiting at camera_plugin.cpp:556, so GL initialization completed before the fault.
  - RED fails specifically because the legacy base contains set_macos_render_context; GREEN passes after rendering lifecycle moves to an independent optional capability.
  - The installed r11 fork loads CameraPlugin and the pre-r11 simulation_evidence binary together, completes hardware activation, and publishes all three task_camera topics without SIGBUS.
  - Probe samples camera_info=23, color=3, depth=23; dimensions=640x480; frame_id=task_camera_frame; encodings rgb8 and 32FC1; RGB bytes=921600; depth bytes=1228800; finite positive depth values=307200.
  - CameraInfo, RGB and depth share stamp 55888000000 ns. The bounded subscriber observed RGB at 1.3333333333333333 Hz; the configured publisher rate remains 10 Hz.
  - SIGINT shutdown returns launch exit 0; ros2_control_node, robot_state_publisher and move_group all finish cleanly, and ROS_DOMAIN_ID 145 has no remaining nodes.
  - The preliminary launch using a nonexistent venv ros2 path exited 2 before starting a process; a dry-run launch exited 0 without starting the stack. Neither was counted as runtime acceptance.
inferred:
  - CONFIRMED: the next plugin is simulation_evidence, built against the r9 base vtable; calling the newly appended base virtual dispatched outside its legacy vtable.
conclusion: PASS. The optional rendering capability preserves legacy plugin ABI and macOS live RGB-D plus clean shutdown acceptance passes.
evidence:
  - /Users/matianyi/Library/Logs/DiagnosticReports/ros2_control_node-2026-08-25-105801.ips
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-040-red-plugin-abi-capability.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-041-green-plugin-abi-capability.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-042-fork-r11-build.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-043-fork-r11-directed-tests.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-047-camera-topic-samples.json
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-048-fork-r11-package-tests.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-049-fork-r11-test-results.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-050-post-shutdown-node-list.log
decision: KEEP
next_experiment: NONE
```

```yaml
experiment_id: EXP-004
status: PARTIAL
prior_experiment: EXP-003
hypothesis: The upstream CameraPlugin ownership model can replace r9's hard-wired MujocoCameras path while retaining the Darwin main-thread GLFW-window handoff.
single_variable: Camera publication lifecycle is loaded through mujoco_plugins.task_camera rather than MujocoSystemInterface::cameras_.
lifecycle: ISOLATED_STACK
preconditions:
  - No ROS or MuJoCo process is owned by this task.
  - Fork is at local r9 commit 1ef550cbbcbbcf8c0e5784648f81545724d5f90f.
  - Current project branch is codex/macos-mujoco-camera-topics at dc224b5.
success_criteria:
  - A RED regression test proves current r9 lacks the task_camera plugin configuration.
  - The installed fork discovers CameraPlugin and current SO-101 parameters load it.
  - A logged-in macOS desktop launch yields valid aligned task-camera RGB-D samples and clean shutdown.
failure_criteria:
  - The worker creates or destroys a Cocoa GLFW window off the process main thread.
  - Camera rendering shares mutable authoritative mjData without a snapshot boundary.
invalid_criteria:
  - Source-only test or build is reported as installed runtime verification.
evidence:
  - /tmp/so101-debug-v4-t005-macos-camera-topics/
observed:
  - RED proved r9 lacked both the task_camera plugin configuration and camera_plugin.cpp build target.
  - GREEN configuration tests prove the installed project selects CameraPlugin, 10 Hz streaming, task_camera RGB-D topics, and a 640x480 MJCF camera resolution.
  - The built and installed fork exports CameraPlugin; final directed headless and Darwin primary-monitor tests pass 2/2 under the complete ROS overlay.
  - The installed r10 project overlay resolves `so101_demo_py` from `project-install-r10-isolated`; its plugin YAML, r10 lock and 640x480 task camera bytes are verified in-place. Launch/plugin tests pass 13/13 and r10 lock/plugin-contract tests pass 5/5.
  - GUI-domain live launch proves headless=false does not emit the rendering-disabled branch, creates the hidden GLFW window on the process main thread, loads CameraPlugin, and starts its rendering worker.
  - The process receives SIGBUS (-10) while the worker creates its MuJoCo rendering context after glfwMakeContextCurrent on the hidden main-thread-created window. No RGB-D samples can be claimed.
  - Earlier GUI launch provenance initially selected an old primary-checkout dylib; explicit fork-first DYLD_LIBRARY_PATH corrected this and is recorded in EXP-019 through EXP-027 logs.
inferred: Upstream's background GLFW render-worker architecture needs a macOS-specific context-initialization/render-execution design beyond window creation handoff.
conclusion: PARTIAL. Plugin migration compiles and loads; macOS RGB-D functional/shutdown acceptance remains blocked by SIGBUS before the first render.
evidence:
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-004-red-camera-plugin-contract.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-012-directed-ctest-complete-overlay.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-023-desktop-live-after-resize-guard.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-027-desktop-live-resolution.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-028-final-directed-ctest.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-036-project-reinstall-r10-isolated.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-037-r10-lock-and-camera-contract-tests.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-039-project-tests-r10-installed-overlay.log
next_experiment: Make the macOS MuJoCo rendering context on the process main thread and schedule camera rendering there, or replace GLFW with a verified macOS offscreen backend; retain snapshot/timestamp semantics.
```

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

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-004-PARTIAL
working_tree_status: Pending local commits for the plugin migration; no push or merge performed.
owned_processes: NONE (each failed GUI-domain launch was terminated by launch after ros2_control_node exited)
preserved_processes: No pre-existing ROS/MuJoCo process was intentionally stopped.
confirmed_conclusions:
  - Pluginlib discovers and enters CameraPlugin from the installed fork and installed SO-101 YAML.
  - macOS viewer resize is now skipped while Linux retains the guarded primary-monitor sizing path.
open_risks:
  - SIGBUS in CameraPlugin's worker-side MuJoCo GL context initialization prevents first frames, aligned timestamps, rate evidence, and clean-shutdown acceptance.
  - Current Computer Use policy permits desktop inspection but not typing in the logged-in terminal; GUI-domain launchctl replay was used instead.
next_command: Design and validate a main-thread rendering dispatch or an actually supported macOS offscreen context before claiming RGB-D runtime success.
```

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-005
current_hypothesis: NONE; macOS RGB-D acceptance passed.
working_tree_status: Fork r11 is locally committed; project r11 lock, gitlink and this ledger are pending the final local project commit.
owned_processes: NONE; ROS_DOMAIN_ID 145 node list is empty after launch exit 0.
preserved_processes: No pre-existing ROS/MuJoCo process was stopped.
confirmed_conclusions:
  - The SIGBUS root cause was legacy plugin ABI corruption from extending MuJoCoROS2ControlPluginBase, not worker-side OpenGL rendering.
  - An independent MuJoCoROS2ControlRenderingPlugin capability preserves the legacy base vtable and supports CameraPlugin lifecycle dispatch.
  - Logged-in Aqua runtime publishes aligned valid 640x480 rgb8/32FC1 data and shuts down without crash or deadlock.
disproven_routes:
  - Moving camera rendering itself to the process main thread is not required for this failure; the GL render worker had already initialized and was waiting when the ABI crash occurred.
open_risks:
  - The bounded Python subscriber observed RGB at 1.33 Hz rather than the configured 10 Hz; payload validity and repeated publication passed, but performance tuning is outside this correctness fix.
next_command: Commit the r11 project gitlink, dependency locks and completed experiment ledger; do not push.
```
