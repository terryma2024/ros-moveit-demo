# Text Agent RGB-D end-to-end launch experiment ledger

```yaml
task_id: so101-text-agent-rgbd-e2e-launch
goal: Add one MuJoCo launch for natural-language planning, RGB-D perception, dynamic pick-place, and owned cleanup, then validate all four preset positions on the local Mac.
success_contract: Four independent FULL_RESTART runs at task_start, cup_test_forward_5cm, cup_test_left_5cm, and cup_test_right_5cm satisfy text-agent, RGB-D, controller, MoveIt, MuJoCo physical, visual, exit, and cleanup gates.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo
branch: main
base_commit: 03887b424797a2f644156725742077b970100a0f
current_commit: 5396e2e7e1a07330a3872712e25bbdb8931fc5a7
evidence_root: /tmp/so101-debug-text-agent-e2e-launch-20260831
confirmed_conclusions:
  - DESIGN-001: The existing perception launch already owns MuJoCo, controllers, MoveIt, camera TF, RGB-D perception, and dynamic pick-place; the approved design adds a separate public launch that substitutes text_pick_agent for the direct dynamic workflow.
  - DESIGN-001: DeepSeek and Ollama remain external services; the launch inherits provider configuration but does not own either service.
  - PROV-001: Local main is 03887b424797a2f644156725742077b970100a0f with pinned mujoco_ros2_control 71bc9346cf93d6227a6678fcacf63f3e18acfcba.
  - PROV-001: A pre-existing local MuJoCo stack and rgbd_cup_pose process tree is present and must not be stopped or reused without ownership confirmation.
  - PROV-001: ai-station remains at e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4 with its untracked RGB-D ledger and codex/codex-cua sessions preserved.
disproven_routes:
  - DESIGN-001: A shell wrapper is rejected because it splits process ownership, exit status, and evidence provenance.
  - DESIGN-001: Adding workflow selection to the existing perception launch is rejected to preserve its public contract.
open_hypotheses:
  - The dedicated launch can preserve existing fail-closed semantics while passing installed provenance to text_pick_agent automatically.
  - Each of the four FULL_RESTART runs can complete the full natural-language-to-physical chain on the local Mac.
latest_checkpoint: CP-002
next_experiment: Execute Task 1 of docs/superpowers/plans/2026-08-31-text-agent-rgbd-e2e-launch.md after the user selects the execution mode.
```

## DESIGN-001

```yaml
design_id: DESIGN-001
status: APPROVED_IN_WRITING
date: 2026-08-31
design: docs/superpowers/specs/2026-08-31-text-agent-rgbd-e2e-launch-design.md
single_variable: Add one dedicated text-agent RGB-D launch while leaving the existing perception launch unchanged.
evidence:
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/design/local-provenance.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/design/local-domain-231-nodes-final.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/design/local-processes.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/design/local-ollama-ps.log
  - /tmp/so101-debug-text-agent-e2e-launch-20260831/design/ai-station-provenance.log
decision: KEEP
```

## CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The dedicated launch can compose the existing proven components without changing their internal contracts.
working_tree_status: Design spec and this ledger are new; no pre-existing local source changes were observed at task start.
owned_processes: NONE
preserved_processes:
  - Local ros2 launch PID 79408 and descendant MuJoCo/MoveIt/RGB-D processes 79419, 79423, 80039, and 80040.
  - ai-station codex and codex-cua tmux sessions and its untracked RGB-D experiment ledger.
confirmed_conclusions:
  - Approved architecture is recorded in DESIGN-001.
disproven_routes:
  - Shell wrapper and modification of the existing perception launch public contract.
open_risks:
  - Local pre-existing runtime ownership must be resolved before any FULL_RESTART acceptance run.
  - Ollama currently reports no loaded model in ollama ps; provider health must be rechecked before acceptance.
next_command: User reviews the written spec; after approval, create the implementation plan before editing production code.
evidence_disposition:
  retained:
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/design
  archived: NONE
  deletion_candidates: NONE
```

## CP-002

```yaml
checkpoint_id: CP-002
date: 2026-08-31
last_valid_experiment: DESIGN-001
current_hypothesis: The approved design can be implemented as six TDD tasks without changing the existing perception launch contract.
written_design_approval: CONFIRMED_BY_USER
implementation_plan: docs/superpowers/plans/2026-08-31-text-agent-rgbd-e2e-launch.md
source_commit: 5396e2e7e1a07330a3872712e25bbdb8931fc5a7
owned_processes: NONE
preserved_processes:
  - Local pre-existing MuJoCo and RGB-D process tree recorded in CP-001.
  - ai-station sessions and untracked ledger recorded in CP-001.
next_command: Select subagent-driven or inline plan execution, then begin the canonical installed execution identity RED test.
evidence_disposition:
  retained:
    - /tmp/so101-debug-text-agent-e2e-launch-20260831/design
  archived: NONE
  deletion_candidates: NONE
```
