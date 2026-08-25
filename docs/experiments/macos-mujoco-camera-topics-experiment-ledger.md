# macOS MuJoCo RGB-D camera topics experiment ledger

```yaml
task_id: so101-v4-t005-macos-camera-topics
goal: Restore non-headless MuJoCo RGB-D camera publication on macOS while preserving Linux and headless behavior.
success_contract: With headless=false on Darwin, rendering remains enabled and task_camera CameraInfo, RGB, and floating-point depth messages contain aligned valid samples; shutdown joins rendering resources.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo
branch: main
base_commit: 842fb05041d4ba487354cf0c6f9668db6e65a9fb
current_commit: project=db1b658b4bc34f11c923640e1d188cf11aeebc1b; fork=f19a8cc3af61feccacb22a9f0d16cc972e3b2c08 (so101-0.0.3-r11)
evidence_root: /tmp/so101-debug-v4-t005-macos-camera-topics/
confirmed_conclusions:
  - The Darwin launch guard deterministically sets disable_rendering=true for interactive launches, suppressing the camera worker despite publisher registration.
  - EXP-005 confirms the post-migration SIGBUS was an ABI mismatch in the legacy plugin base vtable, not a MuJoCo GL-context failure.
  - EXP-005 receives aligned valid 640x480 RGB-D samples in the logged-in Aqua session and shuts down cleanly.
  - EXP-006 builds and tests r11 on ai-station Linux, receives aligned valid 640x480 RGB-D samples in the logged-in X11 session, and shuts down cleanly.
  - EXP-007 rebuilds the primary macOS workspace's default install, passes affected tests, receives aligned valid 640x480 RGB-D samples from that install, and leaves no ROS node or task process after an exit-0 full-ready shutdown.
disproven_routes:
  - Removing the Darwin condition without changing GLFW ownership is not an acceptable repair.
open_hypotheses:
  - H1: the Darwin launch guard deliberately prevents GLFW/Cocoa window-context creation from the existing background rendering thread; it also disables all camera publishers.
  - H2: a main-thread-owned macOS rendering context can preserve camera publication without relaxing the Cocoa constraint.
  - H3: a headless/offscreen MuJoCo context can publish camera images on Darwin without a GLFW window, but must be verified against the pinned MuJoCo API.
latest_checkpoint: CP-010
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
experiment_id: EXP-007
status: VALID
prior_experiment: EXP-005
hypothesis: The accepted r11 source and CameraPlugin runtime remain functional when built and launched entirely from the primary moveit-demo workspace's default isolated build/install layout.
prediction: Rebuilding the fork and so101_demo_py into the primary install produces current binaries and installed assets; a logged-in Aqua launch from only that overlay publishes valid aligned task_camera CameraInfo, RGB8, and 32FC1 depth samples and shuts down cleanly.
single_variable: Install/runtime target changes from the EXP-005 temporary isolated overlays to /Users/matianyi/Projects/robot_demo_001/moveit-demo/{build,install}; source commits and camera configuration remain fixed.
lifecycle: ISOLATED_STACK
preconditions:
  - Primary moveit-demo main is clean at db1b658b4bc34f11c923640e1d188cf11aeebc1b and the fork checkout is clean at f19a8cc3af61feccacb22a9f0d16cc972e3b2c08.
  - Parent-repository changes to learners/zjumty/progress.yaml and the moveit-demo gitlink are preserved and not staged or modified by this experiment.
  - No existing MuJoCo, ros2_control_node, move_group, RViz, or robot_state_publisher process is present; ROS_DOMAIN_ID 147 has an empty no-daemon graph.
success_criteria:
  - Primary fork and so101_demo_py builds exit 0; affected package tests and the 259-project-test contract have no failures.
  - ros2 package prefixes resolve mujoco_ros2_control, mujoco_ros2_control_plugins, and so101_demo_py exclusively below the primary workspace install directory.
  - Installed plugin XML and dylib both expose CameraPlugin; installed launch renders disable_rendering=false for Darwin headless=false.
  - /task_camera/camera_info, /task_camera/color, and /task_camera/depth each receive messages within a bounded timeout.
  - One aligned batch is 640x480 with task_camera_frame; RGB is rgb8 and non-empty; depth is 32FC1 with finite positive values; CameraInfo/RGB/depth timestamps satisfy the probe contract; publication frequency is observed.
  - Task-owned launch exits 0 after SIGINT, logs hardware/plugin shutdown, and leaves domain 147 plus the task process scan empty.
failure_criteria:
  - Any runtime package resolves outside the primary install, rendering is disabled, payload validation fails, or shutdown crashes/deadlocks/leaks a task-owned process.
invalid_criteria:
  - Source/installed commits differ from the recorded pair, another stack appears in domain 147, or the launch is not executed in the logged-in Aqua session.
provenance:
  source_commit: project=db1b658b4bc34f11c923640e1d188cf11aeebc1b; fork=f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/mujoco_ros2_control/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: 147
  gz_partition: NOT_APPLICABLE_MUJOCO
commands:
  - command: colcon build --base-paths third_party/mujoco_ros2_control --packages-up-to mujoco_ros2_control mujoco_ros2_control_plugins --build-base build --install-base install --symlink-install
    exit_code: 0 (3 packages finished)
  - command: colcon build --base-paths src/so101_demo_py --packages-select so101_demo_py --build-base build --install-base install --symlink-install
    exit_code: 0 (1 package finished)
  - command: colcon test --base-paths third_party/mujoco_ros2_control --packages-select mujoco_ros2_control mujoco_ros2_control_plugins; colcon test-result --verbose
    exit_code: 0 (core 126 tests and plugins 13 tests; 0 errors, failures, or skips)
  - command: python -m pytest -q src/so101_demo_py/test
    exit_code: 0 (259 passed)
  - command: launchctl asuser 501 ... ros2 launch so101_demo_py so101_mujoco.launch.py headless:=false run_mode:=execute execute:=true
    exit_code: 0 for the full-ready foreground launch after SIGINT and bounded SIGTERM escalation
  - command: python src/so101_demo_py/test/macos_camera_topic_probe.py --timeout-s 30 --output <evidence>/main-workspace-camera-topic-samples.json
    exit_code: 0
  - command: capture_main_workspace_rgb.py; sips -s format png <ppm> --out <png>
    exit_code: 0
observed:
  - Package prefixes for mujoco_ros2_control, mujoco_ros2_control_plugins, and so101_demo_py all resolve below /Users/matianyi/Projects/robot_demo_001/moveit-demo/install; launch reports source commit db1b658b4bc34f11c923640e1d188cf11aeebc1b.
  - The Aqua launch logs the macOS main-thread GLFW preparation, loads mujoco_camera_plugin, starts the camera rendering loop, resizes the offscreen target to 640x480, and never logs Camera and lidar rendering is disabled.
  - Probe samples camera_info=19, color=3, depth=19; dimensions=640x480; frame_id=task_camera_frame; encodings rgb8 and 32FC1; RGB bytes=921600; depth bytes=1228800; finite positive depth values=307200.
  - CameraInfo, RGB and depth share stamp 62334000000 ns. The bounded subscriber observes RGB at 1.5384615384615383 Hz while the configured publisher rate is 10 Hz.
  - A directly captured RGB topic frame at stamp 159818000000 ns has 921600 bytes. Visual inspection shows the table, plastic_cup, tolerance ring, SO-101 arm and scene lighting; the PNG SHA-256 is 7fbeafbb00b1167e8d6a3d8d3531bbf1a48ac48763458196f45dfd8d53ed164a.
  - The final shutdown waits until all three controllers, scene_setup and MoveGroup are ready. Launch returns 0; ros2_control_node deactivates and shuts down RobotSystem, and all remaining nodes report clean exit. Launch escalates from SIGINT to SIGTERM after its 5-second grace period, but uses no SIGKILL, logs no process death, and leaves the domain-147 graph plus targeted PID scan empty.
  - A preceding background-launch shutdown attempt is INVALID because the shell background job inherited ignored SIGINT. A startup-phase foreground diagnostic is not counted because sibling processes had not finished initialization; both batches were terminated and leave no process.
inferred:
  - CONFIRMED: the primary default install contains and executes the same accepted r11 CameraPlugin architecture as the isolated macOS acceptance overlay.
  - The 5-second SIGINT grace-period escalation and controller_manager PAL statistics context warnings are shutdown-path noise outside the camera payload contract; CameraPlugin's owning ros2_control_node still completes deactivate/shutdown and exits cleanly with no leaked process.
conclusion: PASS. The primary macOS workspace builds and tests from current source, its installed runtime publishes validated aligned RGB-D payloads, and the full-ready launch exits 0 without crash, deadlock, SIGKILL, or residual task process.
evidence:
  - /tmp/so101-debug-v4-t005-macos-camera-topics/main-workspace-fork-build.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/main-workspace-project-build.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/main-workspace-fork-tests.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/main-workspace-core-test-result.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/main-workspace-plugin-test-result.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/main-workspace-project-tests.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/main-workspace-live-launch.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/main-workspace-camera-topic-samples.json
  - /tmp/so101-debug-v4-t005-macos-camera-topics/main-workspace-camera-probe.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/main-workspace-task-camera-color.png
  - /tmp/so101-debug-v4-t005-macos-camera-topics/main-workspace-rgb-capture.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/main-workspace-ready-shutdown.log
decision: KEEP
next_experiment: NONE
```

```yaml
experiment_id: EXP-006
status: VALID
prior_experiment: EXP-005
hypothesis: The r11 optional rendering capability compiles and runs unchanged on Linux, retaining the upstream GLFW/EGL backend and publishing the same valid RGB-D contract.
prediction: An isolated ai-station checkout of the r11 project and fork builds without Apple-only symbol leakage; headless=false loads CameraPlugin, publishes valid aligned task-camera samples, and exits cleanly.
single_variable: Runtime platform changes from macOS arm64/Aqua to ai-station Linux x86_64/GNOME; source commits and camera configuration remain fixed.
lifecycle: ISOLATED_STACK
preconditions:
  - ai-station /data/work/ws_moveit main is clean at b3770360b26fe8f6fac0e19338d250b6f5cab0e7.
  - ai-station has no running ros2_control_node, MuJoCo, move_group or RViz process before this experiment.
  - Existing ai-station source, install and tmux sessions are preserved; r11 is cloned only below the registered evidence root.
success_criteria:
  - Fork and affected project packages build from the exact r11 commits and affected package tests pass.
  - Installed prefixes point to the experiment overlay, not /data/work/ws_moveit/install or its old fork overlay.
  - headless=false does not log rendering disabled; camera_info, RGB and depth pass the same dimensions/frame/encoding/data/depth/timestamp/rate checks used on macOS.
  - Task-owned launch exits without crash/deadlock and leaves ROS_DOMAIN_ID 146 empty.
failure_criteria:
  - Linux build changes are required, EGL/GLFW selection regresses, payload validation fails, or shutdown leaks a task-owned process.
invalid_criteria:
  - Any runtime package resolves outside the isolated r11 overlay, an unrelated stack appears in domain 146, or remote source provenance differs from the bundles.
provenance:
  source_commit: project=e0c5b05ef21683ae292a94fad8297e54885bb148; fork=f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
  install_overlay: ai-station:/tmp/so101-debug-v4-t005-macos-camera-topics/linux-r11-17dcf1f/project-install-isolated/so101_demo_py and fork-install
  runtime_executable: ai-station:/tmp/so101-debug-v4-t005-macos-camera-topics/linux-r11-17dcf1f/fork-install/lib/mujoco_ros2_control/ros2_control_node
  ros_domain_id: 146
  gz_partition: NOT_APPLICABLE_MUJOCO
commands:
  - command: Create and verify local Git bundles; clone exact commits into the remote registered evidence root.
    exit_code: 0 (local and remote SHA-256 values match)
  - command: colcon build --merge-install --packages-select mujoco_ros2_control_msgs mujoco_ros2_control mujoco_ros2_control_plugins
    exit_code: 0
  - command: colcon test --base-paths <fork> --merge-install --packages-select mujoco_ros2_control mujoco_ros2_control_plugins; colcon test-result --verbose
    exit_code: 0 (138 tests, 0 errors, 0 failures, 0 skipped)
  - command: colcon build --symlink-install --packages-select so101_demo_py
    exit_code: 0 (isolated package-prefix layout)
  - command: python3 -m pytest -q src/so101_demo_py/test
    exit_code: 1 RED (258 passed, one stale scene.xml hash), then 0 GREEN (259 passed)
  - command: ros2 launch so101_demo_py so101_mujoco.launch.py headless:=false run_mode:=execute execute:=true
    exit_code: native NVIDIA path could not create the viewer because the installed 595.84 user library does not match the loaded driver; Mesa software GLX acceptance launch exited 0
  - command: macos_camera_topic_probe.py --timeout-s 30
    exit_code: 0
  - command: capture-ai-station.sh --remote; task-owned tmux Ctrl-C; ROS2CLI_NO_DAEMON=1 ros2 node list
    exit_code: 0
observed:
  - ai-station builds project e0c5b05 and fork f19a8cc from isolated Git bundles; /data/work/ws_moveit remains clean at b377036.
  - CMake finds Linux OpenGL/EGL and compiles camera_plugin.cpp, the upstream GLFW path, and the independent rendering capability without Apple-only symbol leakage.
  - Fork package tests pass 138/138. Project repository-root tests first fail only because the 640x480 camera edit changed scene.xml bytes; updating that regression pin produces 259/259 passing tests.
  - The updated scene-byte pin also passes the installed macOS overlay geometry suite 6/6, so the Linux-discovered test correction is cross-platform.
  - Installed prefixes resolve so101_demo_py to project-install-isolated/so101_demo_py and both fork packages to fork-install. The installed plugin XML exports CameraPlugin, the installed YAML registers task_camera, and the installed scene contains resolution 640 480.
  - The native NVIDIA viewer cannot create a window. xdpyinfo and xrandr succeed, while nvidia-smi exits 18 with Driver/library version mismatch (user library 595.84); this is host GPU state, not a source failure.
  - With the installed Mesa GLX fallback selected, the logged-in X11 launch starts the viewer, does not log Camera and lidar rendering is disabled, loads CameraPlugin plus the pre-r11 simulation_evidence binary, selects GLFW rendering, and resizes the offscreen buffer to 640x480.
  - Probe samples camera_info=3, color=3, depth=3; dimensions=640x480; frame_id=task_camera_frame; encodings rgb8 and 32FC1; RGB bytes=921600; depth bytes=1228800; finite positive depth values=307200.
  - CameraInfo, RGB and depth share stamp 27541999999 ns. The bounded subscriber observes RGB at 6.622516556291391 Hz while the configured publisher rate is 10 Hz.
  - A fresh screenshot was visually inspected and shows the running MuJoCo so101_task_scene viewer with the robot, table and plastic_cup.
  - The final direct-log launch handles SIGINT with exit 0, deactivates RobotSystem, records ordered MoveGroup shutdown, and reports ros2_control_node, robot_state_publisher and MoveGroup clean exits. A no-daemon domain-146 graph and task process scan are empty.
inferred:
  - CONFIRMED: r11 retains Linux GLFW rendering and ABI compatibility while adding the macOS-specific ownership path only behind platform guards.
  - The ai-station native NVIDIA launch remains dependent on repairing the host driver installation or rebooting into the matching kernel module; software GLX provides a complete functional Linux acceptance path meanwhile.
conclusion: PASS. Linux build, package tests, installed provenance, true RGB-D payloads, GUI evidence and clean shutdown pass on ai-station; native NVIDIA acceleration is an external host-state caveat.
evidence:
  - ai-station:/tmp/so101-debug-v4-t005-macos-camera-topics/linux-r11-17dcf1f/linux-fork-build.log
  - ai-station:/tmp/so101-debug-v4-t005-macos-camera-topics/linux-r11-17dcf1f/linux-fork-test-result-final.log
  - ai-station:/tmp/so101-debug-v4-t005-macos-camera-topics/linux-r11-17dcf1f/linux-project-root-pytest-red.log
  - ai-station:/tmp/so101-debug-v4-t005-macos-camera-topics/linux-r11-17dcf1f/linux-project-root-pytest-green.log
  - /tmp/so101-debug-v4-t005-macos-camera-topics/exp-051-geometry-pin-green.log
  - ai-station:/tmp/so101-debug-v4-t005-macos-camera-topics/linux-r11-17dcf1f/linux-installed-provenance.log
  - ai-station:/tmp/so101-debug-v4-t005-macos-camera-topics/linux-r11-17dcf1f/linux-gui-diagnostics.log
  - ai-station:/tmp/so101-debug-v4-t005-macos-camera-topics/linux-r11-17dcf1f/linux-live-launch-swgl.log
  - ai-station:/tmp/so101-debug-v4-t005-macos-camera-topics/linux-r11-17dcf1f/linux-camera-topic-samples.json
  - /tmp/so101-debug-v4-t005-macos-camera-topics/linux-r11-17dcf1f/captures/20260825T115718-dJwtW1NT/desktop.png
  - ai-station:/tmp/so101-debug-v4-t005-macos-camera-topics/linux-r11-17dcf1f/linux-live-cleanexit.log
  - ai-station:/tmp/so101-debug-v4-t005-macos-camera-topics/linux-r11-17dcf1f/linux-cleanexit-fresh-graph.log
decision: KEEP
next_experiment: NONE
```

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

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-006
current_hypothesis: NONE; macOS and Linux RGB-D functional acceptance passed.
working_tree_status: Project test-pin commit e0c5b05 is local; the completed ledger is pending the final local documentation commit. No push or merge was performed.
owned_processes: NONE; the no-daemon ROS_DOMAIN_ID 146 graph and task PID scan are empty after launch exit 0.
preserved_processes: ai-station /data/work/ws_moveit remains clean at b377036; no pre-existing process or tmux session was stopped.
confirmed_conclusions:
  - Linux GCC/OpenGL/EGL build succeeds and affected fork/project package tests pass 138/138 and 259/259.
  - Installed ai-station r11 runtime publishes aligned valid 640x480 rgb8/32FC1 data from CameraPlugin while loading the existing simulation_evidence plugin.
  - Direct-log SIGINT shutdown exits 0 with hardware deactivation, ordered MoveGroup shutdown and no remaining task process or ROS node.
disproven_routes:
  - The current ai-station native NVIDIA path cannot be used for acceptance while its 595.84 user library and loaded kernel driver are mismatched; X11 itself is healthy.
open_risks:
  - Native GPU acceleration should be rechecked after the ai-station NVIDIA driver state is repaired. The accepted software GLX run observed 6.62 Hz versus the configured 10 Hz.
next_command: Commit this completed ledger locally; retain the registered evidence root and do not push.
```

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-006
current_hypothesis: EXP-007 will determine whether the primary default install has the same accepted RGB-D behavior as the isolated r11 overlay.
working_tree_status: Primary moveit-demo main and fork are clean; this ledger has a PLANNED EXP-007 update in the Codex-managed ledger writer worktree.
owned_processes: NONE; ROS_DOMAIN_ID 147 is empty and the system process scan found no existing MuJoCo/ROS stack.
preserved_processes: NONE; parent learners/zjumty/progress.yaml and the parent moveit-demo gitlink modification are preserved.
confirmed_conclusions:
  - EXP-005 and EXP-006 remain the accepted macOS and Linux functional baselines at the same fork commit.
  - The primary CameraPlugin dylib has current camera symbols, while the primary ros2_control_node and so101_demo_py install still need a fresh complete rebuild.
disproven_routes:
  - Source or symlinked XML alone is insufficient provenance for the primary installed runtime.
open_risks:
  - Main-workspace build may expose stale CMake or overlay ordering not present in the isolated acceptance build.
next_command: Build the primary fork packages and so101_demo_py into /Users/matianyi/Projects/robot_demo_001/moveit-demo/install, then verify installed provenance before launching domain 147.
```

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-007
current_hypothesis: NONE; primary macOS default-install RGB-D acceptance passed.
working_tree_status: Primary moveit-demo main remains clean at db1b658b4bc34f11c923640e1d188cf11aeebc1b with its default build/install refreshed; this completed ledger is task-owned in the Codex ledger-writer worktree. No push was performed.
owned_processes: NONE; the no-daemon ROS_DOMAIN_ID 147 graph and targeted launch/PID scan are empty after the full-ready launch exits 0.
preserved_processes: No pre-existing process was stopped; parent learners/zjumty/progress.yaml and the parent moveit-demo gitlink modification remain untouched.
confirmed_conclusions:
  - Primary fork and project builds exit 0; fork test results contain 139 tests with no errors/failures/skips, and project tests pass 259/259.
  - The primary installed overlay loads CameraPlugin without the Darwin rendering-disabled branch and publishes validated aligned 640x480 rgb8/32FC1 task_camera payloads.
  - The accepted RGB frame is visually non-empty, and the full-ready launch completes hardware shutdown with clean core-process exits and no residual ROS node or task PID.
disproven_routes:
  - A shell-background launch cannot validate SIGINT because the job inherits ignored SIGINT; that invalid batch is retained only for audit.
open_risks:
  - The primary macOS probe observes 1.54 Hz instead of the configured 10 Hz; correctness passes, but render/publication performance remains a tuning item.
  - ros2 launch escalates full-ready shutdown to SIGTERM after the 5-second SIGINT grace period, and controller_manager emits PAL statistics invalid-context warnings during exit; all processes nevertheless report clean exit with no SIGKILL or residue.
next_command: NONE. Retain the registered evidence root; do not push or delete evidence without user authorization.
```
