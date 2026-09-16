---
task_id: so101-video-debug-mujoco-live
goal: Record and visually validate a real SO-101 MuJoCo GUI video sample on ai-station.
success_contract: The installed recorder runs against the owned MuJoCo window, produces a non-empty decodable video, yields a fresh final frame, and the frame visibly contains the expected SO-101 simulation scene.
worktree: /data/work/worktrees/so101-video-debug-forward-test-20260916
branch: detached
base_commit: 80e02810102190135c505a768bd5f6ebbfd71dae
current_commit: 80e02810102190135c505a768bd5f6ebbfd71dae
evidence_root: /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01
confirmed_conclusions:
  - EXP-001 did not start MuJoCo or produce video because GUI-only tools imported Pydantic-v2 server models under the ai-station Pydantic-v1 runtime.
disproven_routes:
  - A local-only test pass is sufficient evidence for MuJoCo video sampling (EXP-001).
open_hypotheses:
  - Removing the eager package-level models import allows GUI-only installed tools to run without changing server model behavior.
latest_checkpoint: CP-001
next_experiment: EXP-002
---

## EXP-001

```yaml
experiment_id: EXP-001
status: INVALID
prior_experiment: NONE
hypothesis: The published simulator-neutral recorder can sample a MuJoCo GUI on ai-station.
prediction: Inventory, layout, and recorder commands start and a decodable video is produced.
single_variable: Published simulator-neutral video workflow at commit 80e02810102190135c505a768bd5f6ebbfd71dae.
lifecycle: ISOLATED_STACK
preconditions:
  - The task worktree is clean at the published commit.
success_criteria:
  - MuJoCo starts and a decodable video plus fresh frame are retained.
failure_criteria:
  - The owned MuJoCo window is not recordable or the resulting media is invalid.
invalid_criteria:
  - A prerequisite tool fails before MuJoCo sampling starts.
provenance:
  source_commit: 80e02810102190135c505a768bd5f6ebbfd71dae
  install_overlay: /data/work/worktrees/so101-video-debug-forward-test-20260916/install
  runtime_executable: so101_teleop installed scripts
  ros_domain_id: NOT_STARTED
  gz_partition: NOT_APPLICABLE
commands:
  - command: installed inventory, tiler, and recorder probes
    exit_code: 1
observed:
  - Python 3 imported Pydantic 1.10.14 and failed on models.field_validator before argument parsing.
  - MuJoCo was not launched; no video or screenshot was created.
inferred:
  - Importing so101_teleop.gui.x11 executes so101_teleop.__init__, which eagerly imports server models.
conclusion: The run is invalid as a video-sampling validation because prerequisite import failed before sampling.
evidence:
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/result.md
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01/report.md
decision: REPEAT
next_experiment: EXP-002
```

## EXP-002

```yaml
experiment_id: EXP-002
status: PLANNED
prior_experiment: EXP-001
hypothesis: Deferring package-level server model imports lets GUI-only tools run under ai-station's Pydantic-v1 environment, enabling real MuJoCo video sampling.
prediction: The installed inventory, layout, and recorder tools parse and run; the owned MuJoCo window produces a non-empty decodable video and a visibly valid final frame.
single_variable: Replace the eager so101_teleop.models package import with a lazy compatibility boundary.
lifecycle: ISOLATED_STACK
preconditions:
  - The task worktree and install overlay resolve to the follow-up commit.
  - No unrelated MuJoCo window or task-owned runtime remains.
  - GUI environment comes from ~/gui-env.zsh.
success_criteria:
  - Installed GUI-only commands no longer import so101_teleop.models during startup.
  - A unique task-owned MuJoCo window is discovered by owner PID.
  - Recorder stop succeeds and ffprobe decodes a non-empty video.
  - A fresh extracted frame visibly contains the SO-101 robot and expected task scene.
failure_criteria:
  - The valid owned window cannot be recorded, media cannot be decoded, or visual content is blank/error/loading/incorrect.
invalid_criteria:
  - Commit or overlay provenance differs, window ownership is ambiguous, or evidence is stale.
provenance:
  source_commit: PENDING
  install_overlay: /data/work/worktrees/so101-video-debug-forward-test-20260916/install
  runtime_executable: PENDING
  ros_domain_id: PENDING
  gz_partition: NOT_APPLICABLE
commands:
  - command: targeted RED/GREEN regression and package tests
    exit_code: PENDING
  - command: installed GUI-tool probes
    exit_code: PENDING
  - command: task-owned MuJoCo launch, record, probe, extract, capture, cleanup
    exit_code: PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/so101-video-debug-forward-test/20260916-a01
decision: PENDING
next_experiment: NONE
```

## Checkpoint CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: Package-level eager server model imports are the first bad boundary for GUI-only tools.
working_tree_status: Clean published worktree before the new test and ledger files.
owned_processes: NONE
preserved_processes: Existing unrelated tmux sessions and processes on ai-station.
confirmed_conclusions:
  - EXP-001 is invalid and cannot support a video-sampling success claim.
disproven_routes:
  - Re-running the same published commit without removing the import failure adds no evidence.
open_risks:
  - MuJoCo launch or scene visibility may expose a later independent failure after the import boundary is fixed.
next_command: Run test_package_import_isolation.py and confirm the expected RED failure.
```
