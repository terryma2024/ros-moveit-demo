# SO-101 MuJoCo Maintainability Remediation Experiment Ledger

```yaml
task_id: so101-mujoco-maintainability-remediation
goal: Replace migration experiment scaffolding with approved policy-driven state-machine production runtime and requalify it.
success_contract: All seven audit findings pass automated gates plus independent FULL_RESTART qualification and a fresh final five-consecutive-success RESET_WORLD challenge; only then merge this branch to main and push main to Gitee origin.
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
branch: codex/so101-mujoco-ros2-teleop
base_commit: 70bece06e008b27da8f0923472668e95a369309e
current_commit: 120cefa069b96210db88a72678df10dc3983e380
evidence_root: /tmp/so101-debug-mujoco-maintainability-remediation/
confirmed_conclusions:
  - CP-156: prior implementation passed the published five FULL_RESTART plus five RESET_WORLD simulation qualification.
  - AUDIT-001: contact_calibration.yaml is PLANNED/disabled while production phases hard-code contact limits.
  - AUDIT-002: execute bypasses StateMachineRunner and ignores public checkpoint controls.
disproven_routes:
  - Treating the prior 857-result colcon summary as a clean three-package result; it included 240 stale Gazebo tests.
open_hypotheses:
  - A fresh seven-regime fixed-fingerprint campaign can produce non-overlapping deterministic thresholds for the current model and motion policy.
latest_checkpoint: MNT-CP-002
next_experiment: EXP-001
```

## Checkpoint MNT-CP-001

```yaml
checkpoint_id: MNT-CP-001
recorded_at: 2026-08-12T12:13:33+08:00
last_valid_experiment: NONE
current_hypothesis: A typed motion-policy loader can remove duplicated final-outcome data without changing existing physical evaluation behavior.
working_tree_status: Clean at 68c5ab1ab2cb4da62a26b6e521590db54aa14e01 before this ledger was created; dirty_paths_at_capture is NONE.
owned_processes: NONE
preserved_processes:
  - tmux session codex
  - tmux session codex-cua, idle after prior passive visual acceptance
  - tmux session so101-mujoco-gui with historical windows; no task-owned ROS process was observed
confirmed_conclusions:
  - OBSERVED: Host is AI-STATION-001 and the target checkout is a linked worktree on codex/so101-mujoco-ros2-teleop.
  - OBSERVED: Root and target worktrees were clean; fork submodule was f42b7b3d77288c2fee750fe53b0258e0a3d18194 at tag so101-0.0.3-r5.
  - OBSERVED: The ROS graph was empty and the process probe found no MuJoCo, move_group, RViz, pick-place, or ros2_control runtime process other than the probe shell itself.
disproven_routes:
  - Reusing the prior contaminated 857-test total as the clean Project D qualification count.
open_risks:
  - Exact contact thresholds remain uncalibrated and require a new seven-regime campaign plus explicit hash-bound user approval.
  - Projects B, C, and D remain pending after the Project A gate.
next_command: PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_task_policy.py
```

## Checkpoint MNT-CP-002

```yaml
checkpoint_id: MNT-CP-002
recorded_at: 2026-08-12T12:21:11+08:00
last_valid_experiment: NONE
current_hypothesis: A schema-v2 contact proposal can bind calibration evidence and approval without permitting an unapproved execute path.
working_tree_status: Clean at 120cefa069b96210db88a72678df10dc3983e380 after Project A Task 2.
owned_processes: NONE
preserved_processes:
  - Existing codex, codex-cua, and so101-mujoco-gui tmux sessions remain untouched.
confirmed_conclusions:
  - OBSERVED: The typed task-policy RED failed on the missing module and the YAML contract RED failed on missing physical_outcome.
  - OBSERVED: Three validator mutations for excessive scaling, zero sample count, and zero duration each failed before the minimal bounds were restored.
  - OBSERVED: Thirty-five affected tests passed; Ruff 0.15.20 lint and format checks passed.
  - OBSERVED: The motion YAML parses with one 11.60 N literal and compatibility aliases for the two legacy consumers.
  - USER-DIRECTIVE: After A through D, run a new frozen RESET_WORLD five-success streak. Only a valid 5/5 result authorizes merge to main and push of main to Gitee origin.
disproven_routes:
  - Invoking Ruff as /usr/bin/python3 -m ruff; the repository tool is the installed ruff 0.15.20 executable.
open_risks:
  - Contact calibration remains PLANNED and disabled; execute activation still requires exact hash-bound user approval.
  - The final RESET_WORLD challenge must not reuse historical qualification runs, and any INVALID or valid failure terminates its batch.
next_command: PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_contact_policy.py src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py src/so101_mujoco_demo_py/test/test_contact_calibration_collector.py src/so101_mujoco_demo_py/test/test_task_policy.py
```
