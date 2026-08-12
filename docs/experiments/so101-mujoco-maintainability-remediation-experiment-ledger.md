# SO-101 MuJoCo Maintainability Remediation Experiment Ledger

```yaml
task_id: so101-mujoco-maintainability-remediation
goal: Replace migration experiment scaffolding with approved policy-driven state-machine production runtime and requalify it.
success_contract: All seven audit findings pass automated gates plus independent FULL_RESTART qualification and a fresh final five-consecutive-success RESET_WORLD challenge; only then merge this branch to main and push main to Gitee origin.
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
branch: codex/so101-mujoco-ros2-teleop
base_commit: 70bece06e008b27da8f0923472668e95a369309e
current_commit: ad73015c80664b23f1f967fde6346a1b57e9bf5f
evidence_root: /tmp/so101-debug-mujoco-maintainability-remediation/
confirmed_conclusions:
  - CP-156: prior implementation passed the published five FULL_RESTART plus five RESET_WORLD simulation qualification.
  - AUDIT-001: contact_calibration.yaml is PLANNED/disabled while production phases hard-code contact limits.
  - AUDIT-002: execute bypasses StateMachineRunner and ignores public checkpoint controls.
disproven_routes:
  - Treating the prior 857-result colcon summary as a clean three-package result; it included 240 stale Gazebo tests.
open_hypotheses:
  - A fresh seven-regime fixed-fingerprint campaign can produce non-overlapping deterministic thresholds for the current model and motion policy.
latest_checkpoint: MNT-CP-004
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

## Checkpoint MNT-CP-003

```yaml
checkpoint_id: MNT-CP-003
recorded_at: 2026-08-12T12:34:30+08:00
last_valid_experiment: NONE
current_hypothesis: A pure evaluator can distinguish a fresh bilateral stable grasp from every stale, unsafe, unilateral, slipping, or forbidden-contact window.
working_tree_status: Clean at b526f5167e996f2247b9577594a100b27a36c82b after Project A Task 3.
owned_processes: NONE
preserved_processes:
  - Existing codex, codex-cua, and so101-mujoco-gui tmux sessions remain untouched.
confirmed_conclusions:
  - OBSERVED: Proposal hashing excludes exactly the approval envelope; activating an exact proposal preserves its proposal_sha256 while threshold mutation changes it.
  - OBSERVED: New collector raw output is schema v2 with source/dependency/model/scene/motion identities; malformed, placeholder, or changed identities fail closed.
  - OBSERVED: Analyzer accepts archived schema-v1 raw data through an explicit adapter and emits schema-v2 proposals; new raw data follows the schema-v2 path.
  - OBSERVED: Approval CLI writes atomically for an exact hash and refuses to overwrite an approved file with a different hash.
  - OBSERVED: Fifty-seven focused tests and the full MuJoCo Python package gate of 388 passed plus 4 skipped completed without failures; Ruff lint/format passed.
  - OBSERVED: Checked-in contact_calibration.yaml validates as PLANNED, unapproved, and disabled.
disproven_routes:
  - Keeping enabled outside the approval envelope; changing it during activation would invalidate the exact proposal hash.
  - Accepting an approved_at timestamp without timezone; the new mutation test failed before validation was added and passes afterward.
open_risks:
  - The schema-v1 adapter maps its legacy config hash to scene and motion fields only for archived-read compatibility; live activation will use fresh schema-v2 evidence.
  - Physical thresholds remain unavailable until the seven-regime campaign and exact user approval.
next_command: PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_grasp_outcome.py
```

## Checkpoint MNT-CP-004

```yaml
checkpoint_id: MNT-CP-004
recorded_at: 2026-08-12T12:38:06+08:00
last_valid_experiment: NONE
current_hypothesis: Correlated cup/TCP motion plus table-clearance and relative-pose evidence can reject non-causal micro-lift and transport false positives.
working_tree_status: Clean at ad73015c80664b23f1f967fde6346a1b57e9bf5f after Project A Task 4.
owned_processes: NONE
preserved_processes:
  - Existing codex, codex-cua, and so101-mujoco-gui tmux sessions remain untouched.
confirmed_conclusions:
  - OBSERVED: A five-sample fresh bilateral window with allowed table evidence passes and returns immutable metrics/telemetry.
  - OBSERVED: Stale, provenance, truncation, forbidden contact, missing side, low/high force, compression, slip, and dwell failures have stable distinct codes and declared precedence.
  - OBSERVED: Receipt-age and reset-epoch fault injections each made their dedicated regression fail before restoring the checks.
  - OBSERVED: Twenty-five grasp/contact focused tests and Ruff lint/format passed.
disproven_routes:
  - Treating evidence newer than the action sequence as automatically fresh regardless of callback receipt age.
  - Checking session identity without independently checking reset epoch.
open_risks:
  - Grasp proof alone does not establish causal cup carry; micro-lift and every transport segment remain unproved.
next_command: PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_micro_lift_outcome.py
```
