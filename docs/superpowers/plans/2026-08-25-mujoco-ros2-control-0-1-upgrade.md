# MuJoCo ROS 2 Control 0.1.0 Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the vendored `mujoco_ros2_control` fork to exact upstream commit `57fc6744844902d4532160b403fa95840c1d6f96`, retain the SO-101 fork capabilities on the upstream 0.1.0 architecture, and qualify the exact result on macOS and Linux with working task-camera topics and one successful dynamic cup pick-place run per platform.

**Architecture:** Start a fork branch at the exact upstream commit and merge the local r11 tip so the result has true two-parent ancestry. Keep the upstream `MujocoSimulation`, double-buffered snapshots, free-joint reset model, plugin ABI, and camera modes as the foundation; express SO-101 lifecycle hooks through separate optional capability interfaces, dispatch them after authoritative physics transitions, and adapt the project evidence plugin and dependency locks to that result. Build and test in isolated overlays, transfer exact Git bundles to ai-station, and accept only runtime evidence produced by the same commit on both operating systems.

**Tech Stack:** C++17, ROS 2 Jazzy, `ros2_control`, MuJoCo, pluginlib, GLFW/EGL, Objective-C++/Cocoa bridge where already used by the fork, Python 3.11, pytest, CMake/ament, colcon, Git submodules, tmux, macOS Apple Silicon, Linux x86_64.

**Spec:** `docs/superpowers/specs/2026-08-25-mujoco-ros2-control-0-1-upgrade-design.md`

## Global Constraints

- The upstream target is exactly `57fc6744844902d4532160b403fa95840c1d6f96`; the displayed version is `0.1.0`, not `1.0.0`.
- The local source lineage is exactly `f19a8cc3af61feccacb22a9f0d16cc972e3b2c08` (`so101-0.0.3-r11`).
- The upgraded fork must contain both target commits in its ancestry; a copied upstream tree is not acceptable.
- Do not add SO-101 lifecycle methods to `MuJoCoROS2ControlPluginBase`; preserve the exact upstream 0.1.0 virtual ABI.
- Preserve upstream `MujocoSimulation`, double-buffer snapshots, decoupled controller and physics loops, `ResetWorld.state_overrides`, free-joint services/plugins, `pre_step`, camera modes, sensor/transmission handling, lidar, and mobile-base features.
- Preserve SO-101 viewer-camera services, authoritative post-step evidence, reset/pause/state-snapshot notifications, paused-reset gate, macOS main-thread UI/context ownership, camera worker lifecycle, and GLFW primary-monitor/video-mode null guards.
- Camera acceptance is `/task_camera/color`, `/task_camera/depth`, and `/task_camera/camera_info` at configured 10 Hz, 640 x 480, frame `task_camera_frame`, encodings `rgb8` and `32FC1`, with aligned timestamps and non-empty image data.
- Dynamic acceptance uses `dynamic_cup_pick_place`, `--backend mujoco`, `--mode execute`, `--execute`, `--scene-source observe_only`, a unique session id, and the test-only simulation-truth `/cup_pose` bridge.
- Do not change the dynamic pick policy, geometry, trajectory, or external camera calibration unless a reproducible 0.1.0 compatibility failure first provides RED evidence.
- Use one evidence root: `/tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/`. Store local artifacts below `macos/`; copy ai-station artifacts below `linux/`; never delete evidence without explicit user authorization.
- The main agent is the only ledger writer. Subagents return commands, hashes, outputs, and artifact paths; the main agent records them in `docs/experiments/mujoco-ros2-control-0-1-upgrade-experiment-ledger.md`.
- Keep all builds isolated from `/Users/matianyi/ros2_jazzy/ws_mujoco_ros2_control_fork/install`, `/Users/matianyi/ros2_jazzy/so101_isolated_ws/install`, and ai-station's current overlays until every gate passes.
- Do not push, merge to `origin`, replace a persistent overlay, or delete evidence without a separate user authorization.
- Do not run `ament_uncrustify --reformat`; formatting fixes must be targeted patches.

## File and Responsibility Map

- `third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/mujoco_simulation.hpp` and `src/mujoco_simulation.cpp`: upstream-owned simulation, authoritative transition order, pause/reset gate, observer dispatch calls, viewer-camera service wiring, macOS UI handoff, and monitor guards.
- `third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/simulation_observer_dispatcher.hpp` and `src/simulation_observer_dispatcher.cpp`: focused storage, dynamic capability discovery, ordered dispatch, exception isolation, and one-time disable logging for optional observers.
- `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/include/mujoco_ros2_control_plugins/mujoco_ros2_control_plugin_capabilities.hpp`: ABI-independent optional observer and renderer contracts.
- `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/src/camera_plugin.hpp` and `camera_plugin.cpp`: upstream camera streaming/polled/disabled behavior plus platform-specific renderer lifecycle.
- `third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/viewer_camera.hpp`, `src/viewer_camera.cpp`, and viewer camera message/services: port the r11 viewer pose conversion and ROS API into `MujocoSimulation`.
- `src/so101_mujoco_support/include/so101_mujoco_support/simulation_evidence_plugin.hpp` and `src/simulation_evidence_plugin.cpp`: consume the new optional observer capability without changing the upstream base class.
- `scripts/install-mujoco-ros2-control.zsh`, both dependency lock files, integration checks, and contract tests: pin and prove the exact fork, new `mujoco_3d_lidar` package, interfaces, prefixes, and runtime files.
- `src/so101_demo_py/test/macos_camera_topic_probe.py`: platform-neutral runtime topic acceptance despite its historical filename.
- `docs/experiments/mujoco-ros2-control-0-1-upgrade-experiment-ledger.md`: append-only experiment decisions, controlled variables, commands, results, hashes, retained artifacts, and next gate.

---

### Task 1: Register the Experiment and Create the Two-Parent Upgrade Baseline

**Files:**
- Create: `docs/experiments/mujoco-ros2-control-0-1-upgrade-experiment-ledger.md`
- Modify: `third_party/mujoco_ros2_control` Git history and working tree
- Test: Git ancestry and tree provenance commands in this task

**Interfaces:**
- Consumes: upstream commit `57fc6744844902d4532160b403fa95840c1d6f96`; local tip `f19a8cc3af61feccacb22a9f0d16cc972e3b2c08`; evidence root `/tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/`.
- Produces: fork branch `codex/upstream-0.1.0-so101-r1` with a merge commit whose first parent is the exact upstream target and whose second-parent ancestry includes r11; an initialized main-agent ledger.

- [ ] **Step 1: Create the experiment ledger before changing runtime code**

Create the ledger with this exact top-level shape and fill its hashes from live Git output:

```yaml
# MuJoCo ROS 2 Control 0.1.0 Upgrade Experiment Ledger

task_id: mujoco-control-1-0-upgrade-20260825
evidence_root: /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825
parent_branch: codex/mujoco-ros2-control-0-1-upgrade
parent_head: 5ebc183d92609fee4d884bc7b7526bc7ee7670c4
upstream_target: 57fc6744844902d4532160b403fa95840c1d6f96
local_r11: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
fork_branch: codex/upstream-0.1.0-so101-r1
retained_runs: []
archived_runs: []
deletion_candidates: []

latest_checkpoint:
  state: PLANNED
  hypothesis: A true two-parent upstream-first merge can preserve r11 lineage while adopting the 0.1.0 architecture.
  next_command: Create the fork branch at the exact upstream target and merge r11 without committing conflict resolutions prematurely.
```

- [ ] **Step 2: Capture the clean baseline and import the exact upstream object into the submodule**

Run:

```bash
git status --short
git -C third_party/mujoco_ros2_control status --short
git -C third_party/mujoco_ros2_control remote -v
git -C third_party/mujoco_ros2_control fetch https://github.com/ros-controls/mujoco_ros2_control.git 57fc6744844902d4532160b403fa95840c1d6f96
git -C third_party/mujoco_ros2_control cat-file -e 57fc6744844902d4532160b403fa95840c1d6f96^{commit}
```

Expected: both status outputs are empty before the branch operation; `cat-file` exits 0. If either worktree is dirty, stop and preserve those paths rather than overwriting them.

- [ ] **Step 3: Create the upstream-first branch and make the deliberate merge**

Run:

```bash
git -C third_party/mujoco_ros2_control switch -c codex/upstream-0.1.0-so101-r1 57fc6744844902d4532160b403fa95840c1d6f96
git -C third_party/mujoco_ros2_control merge --no-ff --no-commit f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
git -C third_party/mujoco_ros2_control status --short
```

Expected: conflicts are visible and the merge is not committed. Resolve generated metadata toward upstream 0.1.0; resolve behavior-bearing files according to the File and Responsibility Map. Do not choose an entire side for `mujoco_simulation`, system interface, plugin base, camera plugin, messages, CMake, or package manifests.

- [ ] **Step 4: Prove the resolved tree still contains the upstream package surface before committing**

Run:

```bash
git -C third_party/mujoco_ros2_control diff --check
test -f third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/mujoco_simulation.hpp
test -f third_party/mujoco_ros2_control/mujoco_extensions/mujoco_3d_lidar/package.xml
test -f third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/src/base_velocity_plugin.cpp
test -f third_party/mujoco_ros2_control/mujoco_ros2_control_msgs/srv/SetFreeJointState.srv
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit the merge and verify both ancestry paths**

Run:

```bash
git -C third_party/mujoco_ros2_control commit -m "merge: upgrade fork to upstream 0.1.0 architecture"
git -C third_party/mujoco_ros2_control merge-base --is-ancestor 57fc6744844902d4532160b403fa95840c1d6f96 HEAD
git -C third_party/mujoco_ros2_control merge-base --is-ancestor f19a8cc3af61feccacb22a9f0d16cc972e3b2c08 HEAD
git -C third_party/mujoco_ros2_control rev-list --parents -n 1 HEAD
```

Expected: both `merge-base` calls exit 0 and `rev-list` prints the merge commit followed by two parent hashes. Append the merge hash, parents, conflict list, and commands to the ledger.

---

### Task 2: Add ABI-Neutral Observer Capabilities and Fault-Isolated Dispatch

**Files:**
- Create: `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/include/mujoco_ros2_control_plugins/mujoco_ros2_control_plugin_capabilities.hpp`
- Create: `third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/simulation_observer_dispatcher.hpp`
- Create: `third_party/mujoco_ros2_control/mujoco_ros2_control/src/simulation_observer_dispatcher.cpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control/CMakeLists.txt`
- Test: `third_party/mujoco_ros2_control/mujoco_ros2_control/tests/test_simulation_observer_dispatcher.cpp`
- Modify test registration: `third_party/mujoco_ros2_control/mujoco_ros2_control/tests/CMakeLists.txt`

**Interfaces:**
- Consumes: loaded `std::shared_ptr<MuJoCoROS2ControlPluginBase>` instances and `rclcpp::Logger`.
- Produces: `MuJoCoROS2ControlSimulationObserver` with `on_physics_step`, `on_reset`, `on_pause`, and `on_state_snapshot`; `MuJoCoROS2ControlRenderingPlugin`; `SimulationObserverDispatcher` that preserves load order and disables only the observer that throws.

- [ ] **Step 1: Write RED tests for capability discovery, order, fault isolation, and upstream ABI preservation**

Add a test fixture with `RecordingPlugin : public MuJoCoROS2ControlPluginBase, public MuJoCoROS2ControlSimulationObserver` and `OrdinaryPlugin : public MuJoCoROS2ControlPluginBase`. Assert:

```cpp
dispatcher.add(first);
dispatcher.add(ordinary);
dispatcher.add(throwing);
dispatcher.add(last);
dispatcher.on_physics_step(model, data);
EXPECT_EQ(events, (std::vector<std::string>{"first:step", "throwing:step", "last:step"}));
dispatcher.on_physics_step(model, data);
EXPECT_EQ(events, (std::vector<std::string>{
  "first:step", "throwing:step", "last:step", "first:step", "last:step"}));
```

Also use compile-time pointer-to-member declarations for only the exact upstream base methods:

```cpp
using Base = mujoco_ros2_control_plugins::MuJoCoROS2ControlPluginBase;
static_assert(std::is_same_v<decltype(&Base::init), bool (Base::*)(rclcpp::Node::SharedPtr, const mjModel*, mjData*)>);
static_assert(std::is_same_v<decltype(&Base::update), void (Base::*)(const mjModel*, mjData*)>);
static_assert(std::is_same_v<decltype(&Base::pre_step), void (Base::*)(mjData*)>);
static_assert(std::is_same_v<decltype(&Base::cleanup), void (Base::*)()>);
```

- [ ] **Step 2: Run the focused test and verify RED**

Run from an isolated fork workspace whose `src/mujoco_ros2_control` points at the submodule:

```bash
source /opt/ros/jazzy/setup.zsh
source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
colcon build --base-paths third_party/mujoco_ros2_control --build-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task2/build --install-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task2/install --log-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task2/log --packages-select mujoco_ros2_control
```

Expected: compile fails because the capability header and dispatcher do not exist. Save the diagnostic under `macos/task2/red.txt`.

- [ ] **Step 3: Define the optional contracts without editing the upstream base class**

Implement these public signatures exactly:

```cpp
class MuJoCoROS2ControlSimulationObserver
{
public:
  virtual ~MuJoCoROS2ControlSimulationObserver() = default;
  virtual void on_physics_step(const mjModel*, const mjData*) {}
  virtual void on_reset() {}
  virtual void on_pause(bool) {}
  virtual void on_state_snapshot(const mjModel*, const mjData*, bool) {}
};

class MuJoCoROS2ControlRenderingPlugin
{
public:
  virtual ~MuJoCoROS2ControlRenderingPlugin() = default;
  virtual void set_platform_render_context(void* context) = 0;
  virtual void set_rendering_enabled(bool enabled) = 0;
  virtual void close_rendering() = 0;
};
```

> 2026-08-26 approved amendment: the context handoff is a platform-neutral optional capability.
> Apple supplies the main-thread-created GLFW context; non-Apple callers pass `nullptr`, and the
> implementation treats that handoff as a no-op. Do not expose a macOS-named public virtual method.

Keep these in `mujoco_ros2_control_plugins` namespace and leave `mujoco_ros2_control_plugins_base.hpp` byte-for-byte equivalent to upstream at the public class declaration.

- [ ] **Step 4: Implement the dispatcher with dynamic capability discovery and one-fault containment**

The dispatcher public API is:

```cpp
class SimulationObserverDispatcher
{
public:
  explicit SimulationObserverDispatcher(rclcpp::Logger logger);
  void add(const std::shared_ptr<mujoco_ros2_control_plugins::MuJoCoROS2ControlPluginBase>& plugin);
  void on_physics_step(const mjModel* model, const mjData* data);
  void on_reset();
  void on_pause(bool paused);
  void on_state_snapshot(const mjModel* model, const mjData* data, bool paused);
};
```

`add()` uses `std::dynamic_pointer_cast<MuJoCoROS2ControlSimulationObserver>`. Each dispatch iterates in plugin load order, skips disabled entries, wraps one observer call in `try/catch (const std::exception&)` plus `catch (...)`, marks only that entry disabled, and logs its index exactly once.

- [ ] **Step 5: Run focused tests and ABI diff gate**

Run:

```bash
colcon test --base-paths third_party/mujoco_ros2_control --build-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task2/build --install-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task2/install --log-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task2/log --packages-select mujoco_ros2_control --ctest-args -R simulation_observer_dispatcher --output-on-failure
git -C /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/upstream show 57fc6744844902d4532160b403fa95840c1d6f96:mujoco_ros2_control_plugins/include/mujoco_ros2_control_plugins/mujoco_ros2_control_plugins_base.hpp > /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task2/upstream-plugin-base.hpp
diff -u /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task2/upstream-plugin-base.hpp third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/include/mujoco_ros2_control_plugins/mujoco_ros2_control_plugins_base.hpp
```

Expected: focused tests pass; the base-header diff is empty.

- [ ] **Step 6: Commit the capability boundary**

```bash
git -C third_party/mujoco_ros2_control add mujoco_ros2_control_plugins/include/mujoco_ros2_control_plugins/mujoco_ros2_control_plugin_capabilities.hpp mujoco_ros2_control/include/mujoco_ros2_control/simulation_observer_dispatcher.hpp mujoco_ros2_control/src/simulation_observer_dispatcher.cpp mujoco_ros2_control/tests/test_simulation_observer_dispatcher.cpp mujoco_ros2_control/tests/CMakeLists.txt mujoco_ros2_control/CMakeLists.txt
git -C third_party/mujoco_ros2_control commit -m "feat: add optional simulation observer capabilities"
```

---

### Task 3: Wire Authoritative Physics, Pause, Reset, and Snapshot Transitions

**Files:**
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/mujoco_simulation.hpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control/src/mujoco_simulation.cpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system_interface.hpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control/src/mujoco_system_interface.cpp`
- Test: `third_party/mujoco_ros2_control/mujoco_ros2_control/tests/test_mujoco_simulation.cpp`
- Test: `third_party/mujoco_ros2_control/mujoco_ros2_control/tests/test_mujoco_system_interface.cpp`

**Interfaces:**
- Consumes: `SimulationObserverDispatcher` from Task 2; upstream `ResetWorld.state_overrides`; upstream `PreStepCallback`.
- Produces: authoritative order `staged controls -> pre_step -> mj_step -> observer post-step -> control snapshot -> full snapshot -> /clock`; paused-only atomic reset; after-reset observer/snapshot notifications.

- [ ] **Step 1: Add RED transition-order and reset atomicity tests**

Instrument a deterministic event vector in the test fixture and assert this order after one successful step:

```cpp
EXPECT_EQ(events, (std::vector<std::string>{
  "apply_staged_control", "pre_step", "mj_step", "observer_post_step",
  "control_state", "data_snapshot", "clock"}));
```

Add service-level cases asserting:

```cpp
EXPECT_FALSE(reset_while_running.success);
EXPECT_THAT(reset_while_running.message, testing::HasSubstr("paused"));
EXPECT_EQ(before_qpos, after_qpos);
EXPECT_FALSE(invalid_override.success);
EXPECT_EQ(before_qpos, after_invalid_qpos);
EXPECT_TRUE(valid_paused_override.success);
EXPECT_EQ(events_after_reset, (std::vector<std::string>{"reset", "state_snapshot"}));
```

- [ ] **Step 2: Run focused tests and verify RED on missing order/gates**

Run:

```bash
source /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task2/install/setup.zsh
colcon build --base-paths third_party/mujoco_ros2_control --build-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task3/build --install-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task3/install --log-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task3/log --packages-select mujoco_ros2_control
colcon test --build-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task3/build --install-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task3/install --log-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task3/log --packages-select mujoco_ros2_control --ctest-args -R 'mujoco_(simulation|system_interface)' --output-on-failure
```

Expected: new assertions fail because observers and the paused-reset gate are not wired.

- [ ] **Step 3: Register loaded plugins with the dispatcher and preserve upstream pre-step behavior**

After each successful plugin load/init, call `observer_dispatcher_.add(plugin)`. Keep upstream `plugin->pre_step(data)` fan-out in the existing pre-step callback. Do not route pre-step through the optional observer interface and do not move ordinary `plugin->update(model, snapshot)` from the controller thread.

- [ ] **Step 4: Dispatch only from authoritative transition points**

In the physics loop, call:

```cpp
apply_staged_control(mj_data_);
pre_step_callback_(mj_data_);
mj_step(mj_model_, mj_data_);
observer_dispatcher_.on_physics_step(mj_model_, mj_data_);
refresh_control_state();
refresh_data_snapshot();
publish_clock();
```

Use the actual existing upstream helper names where they already encode these operations, but preserve this exact ordering and keep all post-step readers on the same successful-step path. No observer call may run when `mj_step()` is skipped or throws.

- [ ] **Step 5: Add the paused-only, validate-before-mutate reset transaction**

The reset service must perform this sequence under the simulation mutex:

```cpp
if (!paused_.load()) {
  response->success = false;
  response->message = "reset_world requires the simulation to be paused";
  return;
}
validate_keyframe_and_state_overrides(*request);  // no mjData mutation
apply_keyframe_or_initial_state(*request);
apply_validated_state_overrides(request->state_overrides);
refresh_control_state();
refresh_data_snapshot();
observer_dispatcher_.on_reset();
observer_dispatcher_.on_state_snapshot(mj_model_, mj_data_, true);
```

On pause-state changes, notify `observer_dispatcher_.on_pause(paused)` after the atomic state changes. Preserve upstream free-joint frame resolution and last-duplicate-wins behavior.

- [ ] **Step 6: Run focused and package tests**

Run the Task 3 focused command again, followed by:

```bash
colcon test --build-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task3/build --install-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task3/install --log-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task3/log --packages-select mujoco_ros2_control --event-handlers console_direct+
colcon test-result --test-result-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task3/build --verbose
```

Expected: zero failures and zero errors; the new order and reset tests pass.

- [ ] **Step 7: Commit authoritative lifecycle dispatch**

```bash
git -C third_party/mujoco_ros2_control add mujoco_ros2_control/include/mujoco_ros2_control/mujoco_simulation.hpp mujoco_ros2_control/src/mujoco_simulation.cpp mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system_interface.hpp mujoco_ros2_control/src/mujoco_system_interface.cpp mujoco_ros2_control/tests/test_mujoco_simulation.cpp mujoco_ros2_control/tests/test_mujoco_system_interface.cpp
git -C third_party/mujoco_ros2_control commit -m "feat: dispatch authoritative simulation lifecycle events"
```

---

### Task 4: Port Viewer Camera Services and Cross-Platform Rendering Lifecycle

**Files:**
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/viewer_camera.hpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control/src/viewer_camera.cpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/mujoco_simulation.hpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control/src/mujoco_simulation.cpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/src/camera_plugin.hpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/src/camera_plugin.cpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/CMakeLists.txt`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control_msgs/CMakeLists.txt`
- Preserve: `third_party/mujoco_ros2_control/mujoco_ros2_control_msgs/msg/ViewerCamera.msg`
- Preserve: `third_party/mujoco_ros2_control/mujoco_ros2_control_msgs/srv/GetViewerCamera.srv`
- Preserve: `third_party/mujoco_ros2_control/mujoco_ros2_control_msgs/srv/SetViewerCamera.srv`
- Test: `third_party/mujoco_ros2_control/mujoco_ros2_control/tests/test_viewer_camera.cpp`
- Test: `third_party/mujoco_ros2_control/mujoco_ros2_control/tests/test_primary_monitor_guard.py`
- Test: `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/test/test_camera_plugin.cpp`

**Interfaces:**
- Consumes: Task 2 `MuJoCoROS2ControlRenderingPlugin`; upstream CameraPlugin modes `streaming`, `polled`, and `disabled`; r11 viewer camera message/service definitions.
- Produces: `~/get_viewer_camera` and `~/set_viewer_camera` on `MujocoSimulation`; macOS main-thread context handoff; renderer shutdown before context/viewer destruction; Linux GLFW/EGL behavior unchanged.

- [ ] **Step 1: Add RED tests for service round-trip, null monitor, and renderer close order**

Retain the r11 camera conversion round-trip tests. Extend tests so they assert:

```cpp
EXPECT_TRUE(set_viewer_camera(request));
EXPECT_NEAR(get_viewer_camera().lookat.x, request.lookat.x, 1e-9);
EXPECT_NEAR(get_viewer_camera().distance, request.distance, 1e-9);
EXPECT_EQ(events, (std::vector<std::string>{
  "disable_rendering", "close_rendering", "destroy_context", "destroy_viewer"}));
```

The monitor guard source test must require both `glfwGetPrimaryMonitor()` and `glfwGetVideoMode()` results to be checked before dereference. Camera tests must retain upstream streaming/polled/disabled cases.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
source /Users/matianyi/ros2_jazzy/.venv/bin/activate
python -m pytest third_party/mujoco_ros2_control/mujoco_ros2_control/tests/test_primary_monitor_guard.py -q
colcon build --base-paths third_party/mujoco_ros2_control --build-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task4/build --install-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task4/install --log-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task4/log --packages-select mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control
colcon test --build-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task4/build --install-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task4/install --log-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task4/log --packages-select mujoco_ros2_control_plugins mujoco_ros2_control --ctest-args -R '(camera|viewer|monitor)' --output-on-failure
```

Expected: one or more new lifecycle assertions fail before implementation.

- [ ] **Step 3: Move viewer-camera ownership into the new simulation container**

Create services from the simulation node:

```cpp
rclcpp::Service<GetViewerCamera>::SharedPtr get_viewer_camera_service_;
rclcpp::Service<SetViewerCamera>::SharedPtr set_viewer_camera_service_;
```

Both callbacks take the simulation/UI synchronization mutex used by the upstream viewer. Reuse r11 `to_message(const mjvCamera&)` and `apply_message(const ViewerCamera&, mjvCamera&)`; do not keep duplicate services in `MujocoSystemInterface`.

- [ ] **Step 4: Implement the optional renderer lifecycle in CameraPlugin**

Make CameraPlugin implement `MuJoCoROS2ControlRenderingPlugin`. On macOS, `set_platform_render_context(void*)` stores only the context prepared on the main/UI thread; the camera worker makes that context current only while rendering. `set_rendering_enabled(false)` stops new frames. `close_rendering()` joins the worker and releases MuJoCo render resources before context destruction. On non-Apple builds, retain upstream EGL/GLFW setup and make the platform handoff a harmless no-op.

- [ ] **Step 5: Wire macOS UI ownership and defensive monitor checks**

In `MujocoSimulation`, prepare GLFW/Cocoa UI and render contexts on the main thread, then hand the camera context to every loaded rendering capability. Guard:

```cpp
GLFWmonitor* monitor = glfwGetPrimaryMonitor();
if (monitor != nullptr) {
  const GLFWvidmode* mode = glfwGetVideoMode(monitor);
  if (mode != nullptr) {
    // derive window placement from mode
  }
}
```

Shutdown order is: disable all rendering capabilities, close/join all renderers, destroy camera contexts, stop/destroy viewer UI, then terminate GLFW.

- [ ] **Step 6: Run camera, viewer, monitor, and upstream plugin tests**

Repeat the Task 4 focused commands and add:

```bash
colcon test --build-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task4/build --install-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task4/install --log-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task4/log --packages-select mujoco_ros2_control_plugins --event-handlers console_direct+
colcon test-result --test-result-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task4/build --verbose
```

Expected: upstream camera mode tests, local viewer tests, lifecycle tests, and monitor guard all pass.

- [ ] **Step 7: Commit viewer and platform rendering migration**

```bash
git -C third_party/mujoco_ros2_control add mujoco_ros2_control mujoco_ros2_control_msgs mujoco_ros2_control_plugins
git -C third_party/mujoco_ros2_control commit -m "feat: migrate viewer and camera lifecycle to simulation"
```

---

### Task 5: Complete the Fork Regression Gate and Produce the Candidate Commit

**Files:**
- Modify if required by failures: files already scoped by Tasks 1-4 only
- Test: all packages beneath `third_party/mujoco_ros2_control`
- Evidence: `/tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/`

**Interfaces:**
- Consumes: Tasks 1-4 fork branch.
- Produces: one clean candidate commit hash, complete package/test results, upstream feature inventory proof, and a Git bundle for Linux.

- [ ] **Step 1: Configure the isolated full-fork build**

Run:

```bash
source /Users/matianyi/ros2_jazzy/.venv/bin/activate
source /opt/ros/jazzy/setup.zsh
source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
colcon list --base-paths third_party/mujoco_ros2_control --names-only | tee /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/packages.txt
colcon build --base-paths third_party/mujoco_ros2_control --build-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/build --install-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/install --log-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/log --event-handlers console_direct+
```

Expected: `packages.txt` includes `mujoco_3d_lidar`, core, msgs, plugins, demos, and tests; build exits 0.

- [ ] **Step 2: Run every discovered fork test and inspect actual results**

Run:

```bash
source /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/install/setup.zsh
colcon test --build-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/build --install-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/install --log-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/log --event-handlers console_direct+
colcon test-result --test-result-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/build --verbose | tee /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/test-result.txt
```

Expected: tests were actually discovered; zero failures and zero errors. Treat zero discovered tests for a package that registers tests as a failure.

- [ ] **Step 3: Prove retained and absorbed surface area**

Run:

```bash
ros2 interface show mujoco_ros2_control_msgs/srv/ResetWorld
ros2 interface show mujoco_ros2_control_msgs/srv/SetFreeJointState
ros2 interface show mujoco_ros2_control_msgs/srv/GetViewerCamera
ros2 interface show mujoco_ros2_control_msgs/srv/SetViewerCamera
pluginlib_headers=$(find /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/install -path '*mujoco_ros2_control_plugins*plugin_capabilities.hpp' -print)
test -n "$pluginlib_headers"
git -C third_party/mujoco_ros2_control merge-base --is-ancestor 57fc6744844902d4532160b403fa95840c1d6f96 HEAD
git -C third_party/mujoco_ros2_control merge-base --is-ancestor f19a8cc3af61feccacb22a9f0d16cc972e3b2c08 HEAD
```

Expected: all interfaces resolve from the isolated prefix and both ancestry checks pass.

- [ ] **Step 4: Record the exact candidate and create the transfer bundle**

Run:

```bash
git -C third_party/mujoco_ros2_control status --short
git -C third_party/mujoco_ros2_control rev-parse HEAD | tee /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/candidate-commit.txt
git -C third_party/mujoco_ros2_control bundle create /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/mujoco_ros2_control-0.1.0-r1.bundle codex/upstream-0.1.0-so101-r1
shasum -a 256 /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/mujoco_ros2_control-0.1.0-r1.bundle | tee /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/bundle.sha256
```

Expected: fork status empty. Append the candidate hash, test counts, package list, and bundle hash to the ledger. Do not create the final `so101-0.1.0-r1` tag yet.

---

### Task 6: Adapt SO-101 Evidence and Pin the Project to the Candidate

**Files:**
- Modify: `src/so101_mujoco_support/include/so101_mujoco_support/simulation_evidence_plugin.hpp`
- Modify: `src/so101_mujoco_support/src/simulation_evidence_plugin.cpp`
- Modify: `src/so101_mujoco_support/test/test_simulation_evidence_plugin.cpp`
- Modify: `src/so101_demo_py/config/dependency-lock.yaml`
- Modify: `src/so101_demo_py/config/mujoco/dependency-lock.yaml`
- Modify: `scripts/install-mujoco-ros2-control.zsh`
- Modify: `scripts/check_backend_integration.py`
- Modify: `src/so101_demo_py/test/test_macos_install_contract.py`
- Modify: `src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py`
- Modify: `src/so101_demo_py/test/macos_camera_topic_probe.py`
- Modify: `docs/guides/macos-apple-silicon-ros2-jazzy-so101-mujoco.md`
- Modify: `docs/guides/so101-mujoco-ros2-integration-guide.md`
- Modify: parent gitlink `third_party/mujoco_ros2_control`

**Interfaces:**
- Consumes: Task 5 fork candidate and `MuJoCoROS2ControlSimulationObserver`.
- Produces: project evidence plugin using the optional capability; lock schema that pins exact commit and release-candidate label; installer that builds `mujoco_3d_lidar`, msgs, plugins, and core; platform-neutral camera probe requiring the approved topic contract.

- [ ] **Step 1: Write RED adapter and contract tests**

Change the evidence-plugin test to require:

```cpp
static_assert(std::is_base_of_v<
  mujoco_ros2_control_plugins::MuJoCoROS2ControlSimulationObserver,
  so101_mujoco_support::SimulationEvidencePlugin>);
```

Add Python assertions that both lock files contain the same candidate commit, upstream target, local lineage, and candidate label `so101-0.1.0-r1-candidate`; that the installer package array is exactly:

```python
[
    "mujoco_3d_lidar",
    "mujoco_ros2_control_msgs",
    "mujoco_ros2_control_plugins",
    "mujoco_ros2_control",
]
```

Extend the camera contract test to require 640 x 480, 10 Hz, `task_camera_frame`, `rgb8`, `32FC1`, and all three approved topic names.

- [ ] **Step 2: Run the RED test set**

Run:

```bash
source /Users/matianyi/ros2_jazzy/.venv/bin/activate
python -m pytest src/so101_demo_py/test/test_macos_install_contract.py src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py -q
```

Expected: lock/package assertions fail before the project adapter changes.

- [ ] **Step 3: Change SimulationEvidencePlugin inheritance only at the optional boundary**

The declaration must be:

```cpp
class SimulationEvidencePlugin final
  : public mujoco_ros2_control_plugins::MuJoCoROS2ControlPluginBase,
    public mujoco_ros2_control_plugins::MuJoCoROS2ControlSimulationObserver
```

Keep `init`, controller-rate `update`, and `cleanup` on the base interface. Keep `on_physics_step`, `on_reset`, `on_pause`, and `on_state_snapshot` on the observer interface with the Task 2 signatures. Do not change evidence schemas, chunking, hazard publication, or session-id semantics.

- [ ] **Step 4: Update lock and installer provenance**

Set both locks to the Task 5 candidate hash, upstream target `57fc6744844902d4532160b403fa95840c1d6f96`, lineage `f19a8cc3af61feccacb22a9f0d16cc972e3b2c08`, and temporary label `so101-0.1.0-r1-candidate`. Make the installer build the four-package list above and verify installed free-joint, reset, pause, viewer-camera, and camera plugin artifacts. Continue rejecting a dirty checkout, wrong gitlink, wrong origin, wrong commit, or missing ancestry.

- [ ] **Step 5: Make the topic probe enforce the approved contract on both platforms**

Keep its executable path for compatibility, but add explicit checks:

```python
if (color.width, color.height) != (640, 480):
    raise RuntimeError(f"unexpected dimensions: {color.width}x{color.height}")
if color.header.frame_id != "task_camera_frame":
    raise RuntimeError(f"unexpected frame_id: {color.header.frame_id}")
if not 8.0 <= frequency_hz <= 12.0:
    raise RuntimeError(f"unexpected color frequency: {frequency_hz}")
```

Retain aligned timestamp, non-empty data, and finite-positive-depth checks.

- [ ] **Step 6: Build and test the project adapter in an isolated overlay**

Run:

```bash
source /Users/matianyi/ros2_jazzy/.venv/bin/activate
source /opt/ros/jazzy/setup.zsh
source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
source /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/install/setup.zsh
python -m pytest src/so101_demo_py/test/test_macos_install_contract.py src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py -q
colcon build --base-paths src --build-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/project/build --install-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/project/install --log-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/project/log --packages-select so101_mujoco_support so101_demo_py
source /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/project/install/setup.zsh
colcon test --build-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/project/build --install-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/project/install --log-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/project/log --packages-select so101_mujoco_support so101_demo_py --event-handlers console_direct+
colcon test-result --test-result-base /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/project/build --verbose
```

Expected: all selected package tests pass and were discovered.

- [ ] **Step 7: Commit fork and parent project changes separately**

First commit any required fork compatibility fix with its focused regression test. Then in the parent:

```bash
git add third_party/mujoco_ros2_control src/so101_mujoco_support src/so101_demo_py/config src/so101_demo_py/test scripts/install-mujoco-ros2-control.zsh scripts/check_backend_integration.py docs/guides
git diff --cached --check
git commit -m "feat: integrate mujoco ros2 control 0.1.0 candidate"
```

Expected: the parent records the exact candidate gitlink and project adaptation; unrelated paths are not staged.

---

### Task 7: Qualify Camera Topics and Dynamic Pick-Place on macOS

**Files:**
- Runtime inputs: installed fork/project overlays from Tasks 5-6
- Evidence: `/tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/runtime/`
- Modify only on reproducible failure: the narrow source and test that explain that failure

**Interfaces:**
- Consumes: exact candidate hash, isolated macOS overlays, task-camera probe, test-only `so101_demo.ros.mujoco_cup_pose_bridge`.
- Produces: live package provenance, camera JSON, launch logs, dynamic run evidence bundle, successful outcome record, and a GUI screenshot from macOS.

- [ ] **Step 1: Establish an uncontaminated runtime shell and provenance file**

Run in a new shell with a unique `ROS_DOMAIN_ID` recorded in the ledger:

```bash
source /Users/matianyi/ros2_jazzy/.venv/bin/activate
source /opt/ros/jazzy/setup.zsh
source /Users/matianyi/ros2_jazzy/extra_ws/install/setup.zsh
source /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/install/setup.zsh
source /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/project/install/setup.zsh
export DYLD_LIBRARY_PATH=/Users/matianyi/ros2_jazzy/macos_dylib_farm/current:${DYLD_LIBRARY_PATH:-}
ros2 pkg prefix mujoco_ros2_control
ros2 pkg prefix mujoco_ros2_control_plugins
ros2 pkg prefix so101_mujoco_support
ros2 interface show mujoco_ros2_control_msgs/srv/ResetWorld
```

Expected: prefixes resolve only to the task overlays, and ResetWorld includes 0.1.0 state overrides. Save output to `macos/runtime/provenance.txt`.

- [ ] **Step 2: Start the GUI stack and test-only pose bridge with unique identifiers**

In separate tmux panes, run:

```bash
ROS_LOG_DIR=/tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/runtime/ros-log ros2 launch so101_demo_py so101_mujoco.launch.py run_mode:=execute execute:=true headless:=false simulation_session_id:=mrc010-macos
```

```bash
python -m so101_demo.ros.mujoco_cup_pose_bridge --session-id mrc010-macos
```

Expected: stack remains alive, controllers activate, the evidence plugin reports session `mrc010-macos`, and `/cup_pose` becomes available. Do not reuse another running ROS domain.

- [ ] **Step 3: Prove the camera topics live**

Run:

```bash
python src/so101_demo_py/test/macos_camera_topic_probe.py --timeout-s 20 --output /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/runtime/camera-topics.json
```

Expected: exit 0; JSON reports all three topics with at least three samples, 640 x 480, `task_camera_frame`, `rgb8`, `32FC1`, aligned timestamps, positive finite depth, and frequency between 8 and 12 Hz.

- [ ] **Step 4: Execute one dynamic cup pick-place**

Run:

```bash
ros2 run so101_demo_py dynamic_cup_pick_place --backend mujoco --mode execute --execute --cup-pose-timeout-s 30 --scene-source observe_only --session-id mrc010-macos --expected-reset-epoch 0 --evidence-root /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/runtime/dynamic-run
```

Expected: exit 0 and final outcome is successful; evidence proves the cup was lifted, transported, placed, released, and the robot retreated under the existing qualification policy. A plan-only result or visual-only claim does not pass.

- [ ] **Step 5: Capture GUI and shutdown evidence without deleting the run**

Capture one local screenshot showing the final placed cup and store it as `macos/runtime/final-place.png`. Stop only the task's tmux panes/processes. Verify the camera worker and simulation exit cleanly with no context/thread crash. Append provenance, JSON summary, dynamic outcome, screenshot path, and retained run path to the ledger.

---

### Task 8: Qualify the Exact Candidate on ai-station Linux in an Independent Codex tmux Session

**Files:**
- Transfer: Task 5 fork bundle and a parent-project bundle containing Task 6
- Remote evidence root: `/tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/linux-runtime/`
- Local retained copy: `/tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/linux/`
- Modify only on reproducible Linux failure: the narrow source and regression test explaining that failure

**Interfaces:**
- Consumes: exact Git bundles and SHA-256 files, ai-station existing Codex/tmux capability, project-local `so101-dev` and `ai-station-gui` skills.
- Produces: Linux clean worktree at the same parent/fork commits, full build/test evidence, camera JSON, one successful dynamic run, GUI screenshot, and copied-back hashes.

- [ ] **Step 1: Create and verify exact transfer artifacts locally**

Run:

```bash
git bundle create /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/project/moveit-demo-upgrade.bundle codex/mujoco-ros2-control-0-1-upgrade
shasum -a 256 /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/project/moveit-demo-upgrade.bundle /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/mujoco_ros2_control-0.1.0-r1.bundle > /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/project/transfer.sha256
```

Expected: bundle verification succeeds locally and hashes are recorded in the ledger.

- [ ] **Step 2: Start a dedicated ai-station Codex tmux task with a precise handoff**

The first line of the remote instruction must be exactly:

```text
你当前直接运行在 ai-station 上。不要 ssh 到 ai-station；仓库、tmux、进程、CUA 和截图命令都在当前主机直接执行。
```

The remainder must instruct the remote worker to: read the project-local `so101-dev` and `ai-station-gui` skills; inspect existing tmux/processes and leave unrelated sessions untouched; create a new isolated worktree and evidence root; import and SHA-verify both bundles; checkout the exact parent and submodule commits; use a unique ROS domain and session id `mrc010-linux`; build to task-specific fork/project overlays; run all relevant fork and project tests; start the GUI stack and truth bridge; run the same camera probe and dynamic command as macOS; capture a final GUI screenshot; stop only its own processes; and report commands, hashes, results, and artifact paths.

- [ ] **Step 3: Monitor the remote worker at checkpoints, not by taking over its shell**

Required checkpoints are:

```text
CHECKPOINT 1: bundle hashes and exact Git commits verified
CHECKPOINT 2: fork and project builds/tests pass with actual test counts
CHECKPOINT 3: camera-topics.json passes the 640x480/10Hz/frame/encoding/timestamp contract
CHECKPOINT 4: dynamic_cup_pick_place exits 0 with successful qualified outcome
CHECKPOINT 5: final screenshot and retained evidence paths reported; task processes stopped
```

If a failure occurs, require the worker to use `superpowers:systematic-debugging`, add a RED reproducer, make the smallest cross-platform fix on the shared branch, and repeat affected macOS gates before rerunning Linux.

- [ ] **Step 4: Copy Linux evidence back and verify it locally**

Copy the remote camera JSON, test results, runtime provenance, dynamic result, logs, and screenshot beneath `/tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/linux/`. Verify transferred SHA-256 hashes against the remote report. Append Linux commands, exact commits, package prefixes, test counts, camera summary, dynamic outcome, screenshot, retained runs, and any deletion candidates to the ledger.

---

### Task 9: Finalize the Release Pin, Review, and Local Tag

**Files:**
- Modify: `src/so101_demo_py/config/dependency-lock.yaml`
- Modify: `src/so101_demo_py/config/mujoco/dependency-lock.yaml`
- Modify: any docs that still name the candidate label
- Modify: parent gitlink only if a Linux fix changed the fork candidate
- Test: final contract, provenance, diff, fork ancestry, and evidence audit

**Interfaces:**
- Consumes: passing Tasks 5-8 for one exact fork commit.
- Produces: final tag `so101-0.1.0-r1`, final lock parity, clean fork/parent commits, independent code review, and completion report with retained/archived/deletion-candidate evidence.

- [ ] **Step 1: Freeze one exact cross-platform commit and create the local tag**

Confirm both macOS and Linux evidence name the same fork hash, then run:

```bash
read -r qualified_fork_hash < /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/fork-gate/candidate-commit.txt
test "$(cat /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/linux/qualified-fork-commit.txt)" = "$qualified_fork_hash"
git -C third_party/mujoco_ros2_control tag -a so101-0.1.0-r1 -m "SO-101 mujoco_ros2_control 0.1.0 r1" "$qualified_fork_hash"
git -C third_party/mujoco_ros2_control rev-list -n 1 so101-0.1.0-r1
```

Expected: the tag resolves exactly to the hash qualified on both platforms. Do not push it.

- [ ] **Step 2: Replace the candidate label with the final tag and run lock parity tests**

Change only the tag/label fields from `so101-0.1.0-r1-candidate` to `so101-0.1.0-r1`; the commit hash must not change. Run:

```bash
source /Users/matianyi/ros2_jazzy/.venv/bin/activate
python -m pytest src/so101_demo_py/test/test_macos_install_contract.py src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py -q
python scripts/check_backend_integration.py
git diff --check
git -C third_party/mujoco_ros2_control diff --check
```

Expected: all commands pass and the integration report resolves the final tag to the qualified commit.

- [ ] **Step 3: Commit the final lock label**

```bash
git add src/so101_demo_py/config/dependency-lock.yaml src/so101_demo_py/config/mujoco/dependency-lock.yaml docs/guides scripts src/so101_demo_py/test third_party/mujoco_ros2_control
git diff --cached --check
git commit -m "chore: finalize mujoco ros2 control 0.1.0 r1 pin"
```

Stage only paths actually changed by finalization; remove unchanged path arguments rather than staging unrelated files.

- [ ] **Step 4: Run independent specification and code-quality reviews**

Give reviewers the spec, this plan, fork diff from `57fc674...`, parent diff from `5ebc183...`, both platform evidence summaries, and exact test results. A specification reviewer must verify every approved requirement and excluded scope. A code-quality reviewer must inspect thread ownership, lock order, reset atomicity, plugin ABI, exception isolation, shutdown order, platform guards, and test reliability. Resolve findings with RED tests and rerun affected platform gates.

- [ ] **Step 5: Perform the final verification-before-completion audit**

Run fresh:

```bash
git status --short
git submodule status third_party/mujoco_ros2_control
git -C third_party/mujoco_ros2_control status --short
git -C third_party/mujoco_ros2_control merge-base --is-ancestor 57fc6744844902d4532160b403fa95840c1d6f96 so101-0.1.0-r1
git -C third_party/mujoco_ros2_control merge-base --is-ancestor f19a8cc3af61feccacb22a9f0d16cc972e3b2c08 so101-0.1.0-r1
git -C third_party/mujoco_ros2_control rev-parse so101-0.1.0-r1^{commit}
python -m pytest src/so101_demo_py/test/test_macos_install_contract.py src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py -q
python scripts/check_backend_integration.py
```

Read back `macos/runtime/camera-topics.json`, the macOS dynamic result, `linux/camera-topics.json`, the Linux dynamic result, both screenshots, and both test-result summaries. Completion requires clean intended worktrees, exact tag/lock/gitlink parity, two-parent ancestry, all tests passing with nonzero discovery, camera contract passing on both platforms, and one successful dynamic run on each platform.

- [ ] **Step 6: Close the ledger and report retained evidence**

Set the ledger checkpoint to `QUALIFIED` only after Step 5. List:

```yaml
retained_runs:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/runtime
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/linux
archived_runs: []
deletion_candidates:
  - each superseded task build/log directory, without deleting it
```

Report the parent commit, fork commit/tag, macOS and Linux test counts, camera summaries, dynamic outcomes, screenshot links, unresolved limitations, and that no push/persistent-overlay replacement/evidence deletion occurred.
