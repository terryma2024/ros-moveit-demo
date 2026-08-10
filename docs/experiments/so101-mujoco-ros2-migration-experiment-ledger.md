---
task_id: so101-mujoco-ros2-migration
goal: Replace the Gazebo Python demonstration with an independently packaged MuJoCo ROS 2 demonstration.
success_contract: The MuJoCo implementation satisfies its ROS 2 and physical outcome contracts without changing or depending on the protected Gazebo Python tree.
main_base_commit: d300e7a41fb274d6d7e120699b7040666ea61904
task_base_commit: 45c6efc701b133c45875e86b0053cfc37dab7f4f
behavior_source_commit: 8d7913e7f552a40ee627d65be8b873ac16748bc9
rejected_backup_commit: 3add34f8390b78a1f4a13ff49aefb2dc87638245
rejected_backup_branch: codex/so101-mujoco-ros2-pre-isolation-20260810
branch: codex/so101-mujoco-ros2
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
base_commit: d300e7a41fb274d6d7e120699b7040666ea61904
last_verified_implementation_commit: 9c7889accfdb0eb253a2c9ef1b795b56fe680dad
ledger_commit_pending: false
task_status: TASK_1_COMPLETE
evidence_root: /tmp/so101-debug-mujoco-migration/
protected_nontracked_baseline_sha256: 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f
strict_physics_contract: The successful positive path must use physical contact and grasp forces with no weld, no equality constraint, no adhesion or adhesive actuator, no mocap body, no teleport or set-pose, no direct object qpos writes, and no direct object qvel writes.
confirmed_conclusions:
  - The rebased migration starts from the exact main baseline; CP-001.
disproven_routes:
  - The pre-isolation backup is provenance only and is not an implementation source; CP-001.
open_hypotheses:
  - The behavior source can be migrated to MuJoCo while preserving the strict no-weld/no-teleport contract.
latest_checkpoint: CP-005
next_experiment: EXP-002
---

# SO-101 MuJoCo ROS 2 Migration Experiment Ledger

Raw logs, screenshots, videos, bags, and build artifacts belong only under the evidence root. The
ledger records conclusions and evidence references, never copied raw evidence. Experiments must use
the `PLANNED -> RUNNING -> VALID | INVALID` state transitions from the SO-101 development workflow.

## Checkpoint CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The behavior source can be migrated without a Gazebo Python runtime dependency and without weld or teleport shortcuts.
working_tree_status: Clean baseline plus the three Task 1 isolation deliverables pending their single scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - HEAD before the Task 1 commit is 45c6efc701b133c45875e86b0053cfc37dab7f4f.
  - The merge-base with origin/main is d300e7a41fb274d6d7e120699b7040666ea61904.
  - The protected Gazebo Python tree has no baseline difference or worktree status.
disproven_routes:
  - The rejected backup must remain read-only provenance and must not supply migration behavior.
open_risks:
  - No MuJoCo runtime experiment has run yet.
next_command: Define EXP-001 before the first runtime-affecting migration experiment.
```

## Checkpoint CP-004

```yaml
checkpoint_id: CP-004
last_valid_experiment: NONE
current_hypothesis: The pinned MuJoCo ROS 2 dependency can satisfy the required binary interface without a source fallback.
working_tree_status: Clean at Task 2 implementation commit 9c7889accfdb0eb253a2c9ef1b795b56fe680dad; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The independent ament_python package is commit 9c7889accfdb0eb253a2c9ef1b795b56fe680dad.
  - Package identity tests passed 5 of 5, the combined isolation suite passed 36 of 36, and the package-only colcon build completed successfully.
  - The installed resource marker and package manifest exist under the new package prefix, with no dependency on the protected package.
  - The protected tracked diff and protected status remained empty before and after the Task 2 implementation commit.
disproven_routes:
  - Running pytest with its cache provider inside implementation scope is incompatible with the fail-closed isolation scanner because generated node identifiers can contain rejected provenance strings.
open_risks:
  - No MuJoCo dependency interface or runtime behavior has been proven yet.
next_command: Start Task 3 with the apt mujoco_ros2_control 0.0.3 binary probe and define EXP-001 before any runtime-affecting experiment.
```

## Experiment EXP-001

```yaml
experiment_id: EXP-001
status: VALID
hypothesis: The installed apt mujoco_ros2_control 0.0.3 provider exactly satisfies the pinned package, prefix, file-hash, and service-interface contract.
independent_variable: Read-only execution of the dependency probe against the apt provider.
controlled_variables: ROS Jazzy underlay /opt/ros/jazzy; no overlay; no simulator; no ROS graph mutation; no hardware.
acceptance_criteria: Probe exit 0; all four prefixes equal /opt/ros/jazzy; control version starts 0.0.3-; exact ResetWorld, SetPause, and StepSimulation definitions; all pinned file SHA-256 values match.
evidence_path: /tmp/so101-debug-mujoco-migration/exp-001-dependency-probe.json
owned_processes: NONE
result: Probe exit 0; all required prefixes, versions, interfaces, and pinned file hashes matched. Evidence SHA-256 is 8c2b83d7821f79e618c3ffaf5c6ead133853434367a28bf28d41e6ef978ab104.
next_command: NONE
```

## Checkpoint CP-005

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-001
current_hypothesis: Atomic evidence can be implemented against the proven apt 0.0.3 plugin API.
working_tree_status: Task 3 dependency lock, probe, contract tests, package dependencies, and this checkpoint are pending their single scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The apt provider is release 0.0.3 at /opt/ros/jazzy and no source fallback is required.
  - EXP-001 is VALID with exact versions, prefixes, service definitions, and file hashes recorded under the evidence root.
disproven_routes:
  - Floating main and unpinned source dependency resolution remain forbidden.
open_risks:
  - The Task 4 atomic evidence plugin has not yet been compiled against the proven API.
next_command: Run final Task 3 tests, package build, isolation gates, and create the scoped dependency commit.
```

## Checkpoint CP-002

```yaml
checkpoint_id: CP-002
last_valid_experiment: NONE
current_hypothesis: A fail-closed physical-tree and Python AST scanner can enforce Task 1 isolation without touching protected content or runtime processes.
working_tree_status: The three Task 1 files contain the review fix and are pending one scoped implementation commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The Task 1 base is 45c6efc701b133c45875e86b0053cfc37dab7f4f and the pinned main base is d300e7a41fb274d6d7e120699b7040666ea61904.
  - The original implementation commit is 91c482bd609f7240d5f8547c968363135524bb4f.
  - The protected tracked diff and ordinary status are empty, and its pre-fix nontracked physical baseline digest is 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f.
  - Review RED produced 25 failures and 6 passes before the fix.
disproven_routes:
  - Case-sensitive best-effort text search cannot enforce package isolation.
  - Ordinary Git status cannot detect ignored or generated protected content.
open_risks:
  - The review fix implementation commit is not known until the scoped commit is created.
next_command: Run GREEN and all pre-commit gates, then create the scoped Task 1 review-fix commit.
```

## Checkpoint CP-003

```yaml
checkpoint_id: CP-003
last_valid_experiment: NONE
current_hypothesis: NONE
working_tree_status: Clean at implementation commit e6489ee2949caf435fe028fbe7f65d30a371b5fb; this ledger-only checkpoint update is pending its scoped commit.
owned_processes: NONE
preserved_processes: Existing tmux sessions codex, kimi, and so101-py-qual; no session or process was stopped.
confirmed_conclusions:
  - The fail-closed isolation implementation is commit e6489ee2949caf435fe028fbe7f65d30a371b5fb.
  - Review GREEN produced 31 passes, and the implementation commit passed its immediate isolation, protected-diff, protected-status, and clean-worktree gates.
  - The protected nontracked baseline remains 65f17d820ad021ada76043e38ce1b458ce1e80b447a289a935cf9bffbeb9d52f.
disproven_routes:
  - Case-sensitive text search, broad provenance exclusion, ordinary-status-only protection, and whole-repository backup scanning are not sufficient isolation gates.
open_risks:
  - No Task 1 repository-isolation risk remains; runtime migration experiments have not started.
next_command: Define EXP-001 before the first runtime-affecting migration experiment.
```
