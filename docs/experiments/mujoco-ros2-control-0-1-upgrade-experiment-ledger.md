# MuJoCo ROS 2 Control 0.1.0 Upgrade Experiment Ledger

```yaml
task_id: mujoco-control-1-0-upgrade-20260825
evidence_root: /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825
parent_branch: codex/mujoco-ros2-control-0-1-upgrade
parent_head: 453faaddcca6468bc0d68cb5dbc81cd7bb773e34
upstream_target: 57fc6744844902d4532160b403fa95840c1d6f96
local_r11: f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
fork_branch: codex/upstream-0.1.0-so101-r1
retained_runs: []
archived_runs: []
deletion_candidates: []

latest_checkpoint:
  state: TASK_2_QUALIFIED
  hypothesis: The reviewed optional observer dispatcher can now be wired only at upstream 0.1.0's authoritative physics, pause, reset, and snapshot transition points.
  next_command: Add Task 3 RED transition-order and reset-atomicity tests before wiring the dispatcher into MujocoSimulation.
```

## Controller rulings

- Ruling: use the current clean dedicated feature checkout instead of creating a nested parent-repository worktree. The checkout is itself a Git submodule of the parent robotics repository, is already on the approved feature branch, and the vendored dependency has its own branch boundary. Cost if wrong: changes are visible in this checkout, but remain isolated from `main` and recoverable through the task commits.

## Experiments

### EXP-000: relevant contract baseline

```yaml
scope: read-only local contract baseline; no runtime or source mutation
controlled_environment:
  python: /Users/matianyi/ros2_jazzy/.venv/bin/python
  ros_underlay: /opt/ros/jazzy/setup.zsh
  pytest_plugin_autoload: disabled for pure source/installer contract tests
command: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -p no:cacheprovider src/so101_demo_py/test/test_macos_install_contract.py src/so101_demo_py/test/test_mujoco_camera_plugin_contract.py -q
result: 16 passed in 5.01s
diagnosis: The first unsourced run failed to find ament_cmake. Sourcing ROS exposed launch_testing auto-collection, so the pure contract suite disables plugin autoload while retaining the ROS CMake environment.
```

No runtime experiment has started. All ordinary logs and artifacts for this task are registered under the single evidence root above.

### Task 1 dispatch

```yaml
base: 453faaddcca6468bc0d68cb5dbc81cd7bb773e34
implementer: /root/task1_merge_baseline
brief: .superpowers/sdd/2026-08-25-mujoco-ros2-control-0-1-upgrade/task-1-brief.md
state: COMPLETE
```

### EXP-001: upstream-first fork merge baseline

```yaml
scope: Git history and resolved source-tree provenance; no runtime
fork_merge_commit: 6c562f861e09394ba631fa7dc4e63ea98f95e04c
merge_parents:
  - 57fc6744844902d4532160b403fa95840c1d6f96
  - f19a8cc3af61feccacb22a9f0d16cc972e3b2c08
parent_commit: 34c87e4bd2e1e826f142a6417fe941679bc33ae2
ancestry_checks: PASS
diff_checks: PASS
upstream_surface_checks: PASS
contract_tests:
  passed: 15
  failed: 1
  expected_failure: test_r11_gitlink_history_and_portable_bytes_are_exact because Task 6 has not updated the r11 dependency lock yet
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/upstream
archived_runs: []
deletion_candidates: []
review_state: ACCEPTED_AFTER_FIX_ROUND_1
```

Conflict resolution retained upstream ownership for the new simulation and plugin architecture, removed the legacy core camera implementation, retained viewer-camera sources/interfaces/tests as later migration inputs, kept upstream camera streaming/polled/disabled behavior, and preserved only the macOS compile boundary in the baseline camera plugin. Exact conflict rationale and commands are in the SDD Task 1 report.

Merge conflicts resolved:

1. `mujoco_ros2_control/CMakeLists.txt`
2. `mujoco_ros2_control/include/mujoco_ros2_control/mujoco_cameras.hpp`
3. `mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system_interface.hpp`
4. `mujoco_ros2_control/src/mujoco_cameras.cpp`
5. `mujoco_ros2_control/src/mujoco_system_interface.cpp`
6. `mujoco_ros2_control/tests/CMakeLists.txt`
7. `mujoco_ros2_control/tests/test_headless_init.cpp`
8. `mujoco_ros2_control_msgs/CMakeLists.txt`
9. `mujoco_ros2_control_plugins/CMakeLists.txt`
10. `mujoco_ros2_control_plugins/mujoco_ros2_control_plugins.xml`
11. `mujoco_ros2_control_plugins/src/camera_plugin.cpp`
12. `mujoco_ros2_control_plugins/src/camera_plugin.hpp`
13. `mujoco_ros2_control_plugins/src/heartbeat_publisher_plugin.cpp`

Provenance commands and observed results:

```text
git -C third_party/mujoco_ros2_control merge-base --is-ancestor 57fc6744844902d4532160b403fa95840c1d6f96 HEAD
exit 0

git -C third_party/mujoco_ros2_control merge-base --is-ancestor f19a8cc3af61feccacb22a9f0d16cc972e3b2c08 HEAD
exit 0

git -C third_party/mujoco_ros2_control rev-list --parents -n 1 HEAD
6c562f861e09394ba631fa7dc4e63ea98f95e04c 57fc6744844902d4532160b403fa95840c1d6f96 f19a8cc3af61feccacb22a9f0d16cc972e3b2c08

git -C third_party/mujoco_ros2_control diff --check
exit 0

test -f third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/mujoco_simulation.hpp
test -f third_party/mujoco_ros2_control/mujoco_extensions/mujoco_3d_lidar/package.xml
test -f third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/src/base_velocity_plugin.cpp
test -f third_party/mujoco_ros2_control/mujoco_ros2_control_msgs/srv/SetFreeJointState.srv
all exit 0
```

### EXP-002: Task 1 fix round 1 primary-monitor guard

```yaml
finding: The upstream 0.1.0 owner dereferenced primary monitor and video mode without null checks, while the retained regression test still targeted the removed r11 owner.
red_command: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/matianyi/ros2_jazzy/.venv/bin/python -m pytest -p no:cacheprovider third_party/mujoco_ros2_control/mujoco_ros2_control/tests/test_primary_monitor_guard.py -q
red_result: 1 failed because MujocoSimulation lacked the required GLFWmonitor guard
fork_fix_commit: 102aba33f7566918a884aef3a57eefdf892cd56f
parent_gitlink_commit: dadeb5c413cde9d50177612ecba67690cc7c99fc
green_direct: 1 passed
green_registered_ctest: 1/1 passed
ancestry_checks: PASS
diff_checks: PASS
full_build_observation: Upstream mujoco_3d_lidar did not compile because its target lacks the C++17 requirement for std::byte; this is a downstream full-fork gate issue, not claimed passing here.
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task1-fix-round-1
archived_runs: []
deletion_candidates: []
```

Task 1 scoped re-review verdict:

```yaml
primary_monitor_guard: ADDRESSED
ledger_completion: ADDRESSED
new_breakage: none
verdict: ACCEPTED
```

### Task 2 dispatch

```yaml
parent_base: e265dde
fork_base: 102aba33f7566918a884aef3a57eefdf892cd56f
implementer: /root/task2_capabilities
state: COMPLETE
scope: Optional plugin capability header, fault-isolated observer dispatcher, focused tests, and unchanged upstream base ABI.
ruling: The upstream mujoco_3d_lidar C++17 defect remains outside Task 2 and is a mandatory Task 5 full-fork gate item.
```

### EXP-003: Task 2 optional capabilities and dispatcher

```yaml
fork_commit: 65d60eab9f23ea30cbbf1f73ae4a81ee1ce6c899
parent_gitlink_commit: 7154a17df27e1abce18f2924d994bb2e264b6974
focused_gtests: 3/3 passed
abi_base_header_diff: empty
abi_base_header_sha256: e4bb0f69a48fd9686a1cd50e7e064cae0bdfc011b09576b91d6945b8f5d8b5ee
ancestry_checks: PASS
format_check: PASS
full_package_gate: NOT_CLAIMED
full_package_blockers:
  - upstream mujoco_3d_lidar missing C++17 target requirement for std::byte
  - upstream plugin/core AppleClang -Werror sign/float conversion diagnostics
retained_evidence:
  - /tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/macos/task2
archived_runs: []
deletion_candidates: []
review_state: ACCEPTED
```

Task 2 independent review:

```yaml
spec_compliance: PASS
task_quality: Approved
critical: 0
important: 0
minor: 0
package_full_fork_green: not established and explicitly deferred to Task 5
```
