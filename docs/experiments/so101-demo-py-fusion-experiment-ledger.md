---
task_id: so101-demo-py-fusion
goal: Fuse the qualified MuJoCo and Gazebo Python demos into the single so101_demo_py implementation package while preserving the frozen MuJoCo policy bytes.
success_contract: Complete approved Tasks 1-18; obtain separate fixed-bundle MuJoCo FULL_RESTART 5/5 and RESET_WORLD 5/5; record one valid Gazebo execute result and fresh visual/numeric evidence; do not push or merge.
worktree: /data/work/ws_moveit/.worktrees/so101-demo-py-fusion
branch: codex/so101-demo-py-fusion
base_commit: 866656b217eff4c57eade161c94ea0cef326d13d
current_commit: 616308b3bc24c4cc2c0d684a2aa2e6c8f503d3a7
evidence_root: /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/
confirmed_conclusions:
  - Clean main at 866656b contains the qualified migration and is the selected implementation base; CP-FUSION-001.
  - The frozen MuJoCo policy SHA-256 is aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356; CP-FUSION-001.
  - Historical CP-156 records separate qualified FULL_RESTART EXP-158 through EXP-162 and RESET_WORLD EXP-163 through EXP-167 batches; CP-FUSION-001.
  - The initialized clean-baseline MuJoCo Python suite passes 525 tests with 4 skips; CP-FUSION-001.
  - Tasks 2-5 preserve mapped identity, core/runtime parity, nine-phase order, and exact v1 simulator policy bytes; CP-FUSION-002.
disproven_routes:
  - Historical TASK15-FULL-A is INVALID because headless execution could not satisfy the required viewer-camera readiness gate; CP-156.
  - Recreating or sourcing the removed migration worktree is unnecessary and would contradict the verified merged-main handoff; CP-FUSION-001.
open_hypotheses:
  - The strangler migration can preserve the qualified MuJoCo behavior while making the unified package the sole runtime owner.
  - The clean-main Gazebo installed-independence failure will become GREEN when Tasks 10 and 14 remove legacy runtime ownership.
latest_checkpoint: CP-FUSION-002
next_experiment: NONE
---

# SO-101 Demo Python Fusion Experiment Ledger

Raw build, test, runtime, screenshot, video, and qualification evidence remains under the single
task evidence root. This ledger stores checkpoints and conclusions only. Live experiments must be
pre-registered here before any stack is launched.

## Baseline recovery

The last trusted historical checkpoint is migration ledger `CP-156`. Its counted qualification
batches are `EXP-158` through `EXP-162` (`FULL_RESTART`) and `EXP-163` through `EXP-167`
(`RESET_WORLD`). Those results establish the behavior baseline only and are never counted toward
the new fusion bundle.

The approved plan's former migration-worktree commands are stale after the migration was merged
and that worktree was removed. The verified handoff and live clean-main/content checks replace
that path-specific probe without weakening the baseline gate. The installed colcon CLI also
requires global `--log-base` before the subcommand, so plan commands will use that equivalent
argument order.

## Checkpoint CP-FUSION-001

```yaml
checkpoint_id: CP-FUSION-001
last_valid_experiment: EXP-168 historical uncounted visual corroboration
current_hypothesis: Mechanical migration from the qualified MuJoCo package can preserve all nine production phases under the new mapped namespace.
working_tree_status: Clean implementation worktree at 66918d7 before adding this ledger and baseline provenance record.
owned_processes: NONE
preserved_processes: tmux sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui; no live SO-101, ROS, Gazebo, RViz, MoveIt, or MuJoCo process was observed.
confirmed_conclusions:
  - Main, origin/main, and the selected base all equal 866656b217eff4c57eade161c94ea0cef326d13d.
  - The implementation worktree is isolated on codex/so101-demo-py-fusion and contains only the two approved docs-only commits above the selected base.
  - The canonical policy hash is aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356.
  - The historical FULL_RESTART qualification manifest remains available and hashes to 98c29b847cd40c5ca2061596739f8d66eaf96d3b4b1c707048371fb9773b6f11.
  - After pinned submodule initialization, the MuJoCo Python baseline is 525 passed and 4 skipped.
  - Gazebo baseline is 227 passed, 1 failed, and 2 skipped; the failure is the pre-existing installed legacy-ownership sentinel targeted by Tasks 10 and 14.
disproven_routes:
  - Running both flat test directories in one pytest process is invalid because duplicate test module basenames collide; package suites must be invoked independently.
  - Running linked-worktree dependency tests before submodule initialization produces false wrong-remote/wrong-commit evidence because git falls back to the superproject.
open_risks:
  - No unified package exists yet and no fusion-bundle live behavior has been tested.
  - The Gazebo clean-main ownership failure must become GREEN without weakening the installed-independence contract.
next_command: Write and run the Task 2 mapped-layout RED tests before creating src/so101_demo_py production files.
```

## Checkpoint CP-FUSION-002

```yaml
checkpoint_id: CP-FUSION-002
last_valid_experiment: EXP-168 historical uncounted visual corroboration; no fusion live experiment has started
current_hypothesis: The direct MuJoCo world and lifecycle dependencies can be replaced by neutral ports without changing the installed nine-phase behavior.
working_tree_status: HEAD 616308b3bc24c4cc2c0d684a2aa2e6c8f503d3a7; Task 5 policy registry, provenance, immutable variants, tests, and this ledger checkpoint are intentionally dirty before the scoped Task 5 commit.
owned_processes: NONE
preserved_processes: tmux sessions MNT-Q-RESET-EXP136-140, codex, codex-cua, and so101-mujoco-gui; no preserved session was controlled.
confirmed_conclusions:
  - Task 2 mapped namespace/ament identity is installed under install/fusion-t2 and its four original identity tests passed.
  - Task 3 core parity plus selected legacy domain/runner/policy tests passed 43/43; unified tests at that checkpoint passed 10/10.
  - Task 4 unified tests passed 14/14 and the selected legacy motion/MoveIt/runtime/phase/qualification/outcome/recovery suite passed 150/150.
  - Task 4 installed executables are pick_place and run_qualification; installed dry-run completes the unchanged 19-transition state trace.
  - Task 5 unified suite passes 25/25 and its installed provenance module prints exactly one 64-character hash with empty stderr.
  - v1 mujoco.yaml and gazebo.yaml are byte-identical to the canonical source and each hash to aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356.
  - No live stack, GUI action, or physical experiment was needed for Tasks 1-5.
disproven_routes:
  - The design snippet using find_packages(where="src", include=(python_package, ...)) would discover zero packages for a namespace mapped directly to the src directory; behavioral setup capture proves the explicit mapped-root plus prefixed subpackage list.
  - An immutable MappingProxyType bundle manifest is not JSON serializable; canonical plain mappings retain deterministic hashing and support evidence publication.
  - Eagerly importing provenance from runtime.__init__ contaminates module execution with a runpy warning; the runtime package now leaves module selection explicit.
open_risks:
  - MuJoCo application phases still consume direct concrete clients; Tasks 6-9 must inject neutral ports one boundary at a time.
  - The current bundle hash covers the policy registry and installed prefix only; Tasks 10 and 16 must expand it to the complete installed asset/control/evidence closure before qualification.
next_command: Write and run Task 6 WorldPort/LifecyclePort contract tests before modifying the MuJoCo adapters or application.
evidence:
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task3-green.log sha256=50b8f9f6d1a623001b13c6d56e82ba636af5acaf0eb2d3c285b40e977928a188
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task4-unified-tests.log sha256=e9a40502bbab4cd186bd34f41859604522147a6b66ee852c24ddbc945d7e0a5a
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task4-legacy-selected.log sha256=7eb2a748ac180ba6cc281861db498e923702dc0a24152ca1c96addd88a16dcad
  - /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/task5-unified-tests.log sha256=f2a8ce02b42cc30701feff1a09e68203a567b1e4f46c1861cb179bdb4da53bd1
```
