# SO-101 ACT Data Dispatch Ledger

- Date: 2026-09-17
- Scope: Start remote inline implementation through expert data collection and correctness verification; stop before Task 12.
- Registered task evidence root: `/data/work/so101-evidence/act-data/0917a`
- Implementation worktree: `/data/work/ws_moveit/.worktrees/kimi-teleop-chrome-e2e`
- Branch: `codex/kimi-teleop-chrome-e2e`
- Verified baseline: `5182ed71905ed376c64ab9a400a92de552703293`
- Verified submodule: `e4c0241aee52a40727681bd5872c09bf814e941a`
- Existing dirty path: `src/so101_teleop/web/MUJOCO_LOG.TXT`, preserved.
- Orchestrator source: `/Users/matianyi/Projects/robot_demo_001/moveit-demo`, main `8c63b21f3e2f0f93d468bc3f839ca19d9b7a3982`.
- Preserved sessions: `codex:0`, `kimi`, `kimi-teleop-chrome-e2e`; existing scripted-validation servers are outside this task's ownership.
- Dispatch UUID: `52db9e78-d933-4e52-a5b7-a60f81e5b886`
- Handoff source: [handoff](so101-act-data-ai-station-handoff.md).
- Remote handoff: `/data/work/so101-evidence/act-data/0917a/inputs/so101-act-data-ai-station-handoff.md`
- Runtime writer: remote Codex task; runtime ledger must be maintained in the implementation worktree.

## CP-001 — Ready to dispatch

Read-only preflight confirmed the exact branch and baseline. The existing Codex pane is idle. The older Kimi task is paused at quota and retains unfinished Teleop work. No MoveIt/MuJoCo live stack was observed in the process inventory; existing helper servers remain preserved. The reviewed inputs were copied to the registered root rather than overwriting older checked-out documents.

Design SHA256: `73db08a54f9a29aa5b4c164a214fbc824b981250bb69ee0fb42fd3c4de264b67`.
Plan SHA256: `6a7985f6a3ffc3c25eeb02722899ae6e9c4f4bccb727a52bc9137287c163e93a`.

Next action: create a dedicated window in the existing `codex` tmux session, launch Codex with the handoff instruction as argv, then verify the matching agent-created receipt and baseline probe.

## CP-002 — HANDOFF_SUBMITTED

- Tmux target: `codex:1.0`, window `act-data`, pane `%59`.
- Codex session UUID: `01a0ad0e-00bf-7571-a816-ddfab0b72a18`, source `cli` / originator `codex-tui`; cwd verified from session metadata.
- Runtime: Codex CLI 0.154.0, configured `gpt-5.6-sol high`; automatic approval review with writable worktree/evidence paths.
- Receipt: `/data/work/so101-evidence/act-data/0917a/dispatch-52db9e78-d933-4e52-a5b7-a60f81e5b886.receipt`, created by the agent's shell tool and exact contents verified.
- First task probe: `/data/work/so101-evidence/act-data/0917a/preflight.txt`, baseline/branch/cwd/submodule and preserved dirty path match.
- Handoff SHA256: `75eeb2f9b39cb2aaaf6caa171c1c5750f67d68a58750ec08591f97f1758094d8`; reviewed design and plan hashes match CP-001.
- Fresh task capture: `/data/work/so101-evidence/act-data/0917a/dispatch-after.txt`; shows agent tool execution, input hash readback, skill usage and ownership inventory.

The first tmux creation attempt selected occupied index 0 and failed before launching any task. The script was corrected to explicitly use `codex:1`; only one implementation executor was launched. Initial sandbox tmux access failed, then the agent completed a read-only ownership inventory through automatic approval review. The security guardian metadata is not a second implementation task.

Dispatch is complete. Remote implementation is running; data collection, QC and runtime acceptance remain pending. Task 12 onward remains excluded. No user session was interrupted, no evidence was deleted, and no push/merge occurred.

## Evidence disposition

## CP-003 — Same-session recovery

- Recovery request: restore missing `codex:1`; original task process absent, CLI transcript retained. Exact process-exit cause is unconfirmed.
- Later user steering recovered from original transcript: create an independent implementation worktree and preserve the baseline worktree.
- Actual implementation: `/data/work/ws_moveit/.worktrees/so101-act-data-0917a`, branch `codex/so101-act-data-0917a`, HEAD `cdd79d15bb87fc2bc41a0df8820409ee91cd1a5a`; all dirty source files retained.
- Latest ledger: EXP029 refused stale path timing before goal submission; EXP030 planned, interrupted without a confirmed result. Formal data acceptance remains pending.
- Restored same CLI session `01a0ad0e-00bf-7571-a816-ddfab0b72a18` via explicit `codex resume` UUID, with cwd set to the implementation worktree.
- Tmux target restored: `codex:1.0`, pane `%60`, window `act-data`.
- Recovery receipt UUID: `c5c05816-1509-4647-b4ca-18158b39f678`; agent shell tool created the matching receipt under the original evidence root and readback verified it.
- External Kimi W8 Teleop campaign is now active and preserved; recovery explicitly avoids treating concurrent resource contention as qualification performance evidence.
- Recovery launcher keeps a shell in the window if Codex exits again and records its exit code in `/data/work/so101-evidence/act-data/0917a/recovery-exit.log`.
- Recovery script: `/data/work/so101-evidence/act-data/0917a/recovery.sh`; local staging `/tmp/so101-act-data-recovery.sh` is retained as a deletion candidate, not deleted.
- Remote task acknowledged recovery and is restoring ledger/EXP030 ownership before further experiments. Inline and Task 12 exclusion persist.

## Evidence disposition after recovery

- Retained: remote task root, reviewed inputs, handoff and this ledger.
- Archived: none.
- Deletion candidates: local `/tmp/so101-act-data-dispatch.sh` and `/tmp/so101-act-data-dispatch-id.txt` after dispatch readback; do not delete without authorization.
- Data/runtime acceptance: PENDING at CP-002. Training and ACT policy application: excluded.

## CP-004 — Source-only recovery and rebase on current main

- Date: 2026-09-24.
- Recovery boundary: the former `/data/work/ws_moveit/.worktrees/so101-act-data-0917a` worktree and `/data/work/so101-evidence/act-data/0917a` root are absent. No episode, QC, qualification, runtime, or training claim was recovered. Git source history is the only recovered artifact.
- Last published source: `e2ec28c33ecaa455045477185b9c5dbc5e367538`, identical on `origin/codex/so101-act-data-0917a` and `github/codex/so101-act-data-0917a` before this operation.
- Rebase base: ai-station `main` at `fd7348aa27361750f7e2e7954df53ef75e96545c`.
- New tmux session: `act-data-rebase-20260924`, running an ordinary `zsh` through `script`; no `dst`, DeepSeek Harness, Codex CLI, or implementation executor was launched.
- New worktree: `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`, branch `codex/so101-act-data-0917a`.
- Rebased source commits: `7102c67a`, `874ea617`, `72e5bc16`, and `f3e1d826`; the reviewed document commit is `fbc25063`.
- MuJoCo submodule conflict: `54463fce3bfa6192976e74113f5ed7152f708a3f` is a merge descendant of main pin `5a590b22770b270b71ba6a1c3443d4e67edc7f4b` and the ACT RGB pin `498472acdcc57752071ac03245942d8c5fe06411`. Both dependency locks, the macOS install contract, and the superproject gitlink now select `54463fce3bfa6192976e74113f5ed7152f708a3f`.
- Document readback: design `2d1db796d8ddfd20f63304ba3e976c7b07bef496c6fff265db4c3910195480ca`; plan `5fe40259879f03fa13c0bc5e50a5e0da1902f1e98bd170a5008b55936728b83c`. Independent Astra high review passed with no P0/P1/P2/P3.
- Progress reconciliation: the old Task 1 checkmarks were not retained. The recovered implementation accepts the old `pool_generation` result schema and does not satisfy the refreshed batch/Worker generation/coordinator commit contract.
- Verification boundary: rebase ancestry, clean diff checks, submodule ancestry, document hashes, and static document syntax were verified. No collection, MuJoCo, ROS, MoveIt, pytest, training, rollout, or robot acceptance ran.
- Publication boundary: no push was performed. Both remote branch refs therefore remain at `e2ec28c33ecaa455045477185b9c5dbc5e367538`; the rebased branch exists only in the new ai-station worktree.
- Registered evidence root: `/data/work/so101-evidence/act-main-refresh/20260924-e2ec-rebase`; retained transcript and conflict/document resolution patches are audit evidence.

## Evidence disposition after source-only recovery

- Retained: the new ai-station worktree and tmux session, registered evidence root, transcript, resolution patches, reviewed documents, and both old remote refs.
- Archived: none; the missing prior evidence root could not be archived.
- Deletion candidates: local `/tmp/act-rebase-resolution.patch`, `/tmp/act-remote-docs.m1IipE`, and `/tmp/act-doc-refresh.hsEpQu`; no deletion authorized or performed.
- Data/runtime acceptance: not recovered and remains pending. Training and ACT policy application were not started.
