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
  state: PLANNED
  hypothesis: A true two-parent upstream-first merge can preserve r11 lineage while adopting the 0.1.0 architecture.
  next_command: Create the fork branch at the exact upstream target and merge r11 without committing conflict resolutions prematurely.
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
state: IN_PROGRESS
```
