---
task_id: so101-demo-py-fusion
goal: Fuse the qualified MuJoCo and Gazebo Python demos into the single so101_demo_py implementation package while preserving the frozen MuJoCo policy bytes.
success_contract: Complete approved Tasks 1-18; obtain separate fixed-bundle MuJoCo FULL_RESTART 5/5 and RESET_WORLD 5/5; record one valid Gazebo execute result and fresh visual/numeric evidence; do not push or merge.
worktree: /data/work/ws_moveit/.worktrees/so101-demo-py-fusion
branch: codex/so101-demo-py-fusion
base_commit: 866656b217eff4c57eade161c94ea0cef326d13d
current_commit: 66918d7cd780983be801e5d91f79db2b470bddfd
evidence_root: /tmp/so101-debug-so101-demo-py-fusion-SyIBjl/
confirmed_conclusions:
  - Clean main at 866656b contains the qualified migration and is the selected implementation base; CP-FUSION-001.
  - The frozen MuJoCo policy SHA-256 is aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356; CP-FUSION-001.
  - Historical CP-156 records separate qualified FULL_RESTART EXP-158 through EXP-162 and RESET_WORLD EXP-163 through EXP-167 batches; CP-FUSION-001.
  - The initialized clean-baseline MuJoCo Python suite passes 525 tests with 4 skips; CP-FUSION-001.
disproven_routes:
  - Historical TASK15-FULL-A is INVALID because headless execution could not satisfy the required viewer-camera readiness gate; CP-156.
  - Recreating or sourcing the removed migration worktree is unnecessary and would contradict the verified merged-main handoff; CP-FUSION-001.
open_hypotheses:
  - The strangler migration can preserve the qualified MuJoCo behavior while making the unified package the sole runtime owner.
  - The clean-main Gazebo installed-independence failure will become GREEN when Tasks 10 and 14 remove legacy runtime ownership.
latest_checkpoint: CP-FUSION-001
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
