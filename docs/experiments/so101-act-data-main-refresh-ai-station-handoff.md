# SO-101 ACT data recovery handoff — 2026-09-24

你当前直接运行在 ai-station 上。不要 SSH 到 ai-station；仓库、tmux、进程、ROS、MuJoCo、CUA 和截图命令都在当前主机直接执行。

这是一个持续执行的开发与仿真数据任务。用户授权你在当前 Codex session 中以 inline 模式自主执行。不要启动 `dst`、subagent、第二个 Codex/Kimi 实现任务或并行 writer。按照更新后的设计和实施计划逐任务执行，直到数据验收完成或遇到 handoff 规定的真实停止条件。不要只输出新计划，也不要在正常、可逆、已授权的步骤前停下来询问。

## Dispatch identity

- Dispatch ID: `66c42e4c-4723-461c-9340-1b4f8974e2c8`
- Receipt: `/data/work/so101-evidence/act-data/20260924-fbc25063-resume/dispatch-66c42e4c-4723-461c-9340-1b4f8974e2c8.receipt`
- Tmux session: `act-data-rebase-20260924`, pane `%6`
- Worktree: `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`
- Branch: `codex/so101-act-data-0917a`
- Dispatch source HEAD: `fbc25063f7d6ca5b7ccf67696d142074600aed55`
- Rebase base: `fd7348aa27361750f7e2e7954df53ef75e96545c` (`main`, `origin/main`, and `github/main` at dispatch)
- MuJoCo submodule: `54463fce3bfa6192976e74113f5ed7152f708a3f`
- Registered task evidence root: `/data/work/so101-evidence/act-data/20260924-fbc25063-resume`
- Runtime ledger: `docs/experiments/so101-act-data-experiment-ledger.md` in the worktree
- Reviewed design: `docs/superpowers/specs/2026-09-10-so101-act-head-wrist-rgb-design.md`, SHA256 `2d1db796d8ddfd20f63304ba3e976c7b07bef496c6fff265db4c3910195480ca`
- Reviewed plan: `docs/superpowers/plans/2026-09-11-so101-act-head-wrist-rgb-implementation.md`, SHA256 `5fe40259879f03fa13c0bc5e50a5e0da1902f1e98bd170a5008b55936728b83c`
- Review record: `<evidence-root>/inputs/so101-act-parallel-plan-review-experiment-ledger.md`; final independent Astra high review has no P0/P1/P2/P3.

Before any other task action, use a shell command to create the receipt with exactly the Dispatch ID and no other bytes. Read it back and verify exact equality. Then read this handoff completely, both AGENTS.md files, project-local `$so101-dev` with the applicable access/system-map/debug/test/ledger references, `superpowers:executing-plans`, `superpowers:test-driven-development`, the complete design and plan, the review record, and the runtime ledger.

## Recovery boundary

The old implementation worktree `/data/work/ws_moveit/.worktrees/so101-act-data-0917a` and old evidence root `/data/work/so101-evidence/act-data/0917a` are absent. Their episode files, QC artifacts, scratch output and runtime proofs are unavailable. The Git branch and tracked runtime ledger are the only recovered artifacts.

Treat every historical runtime result in the ledger as an audit lead, not current acceptance evidence. Do not claim or import old episodes, qualification, calibration, replay, throughput, controller, physical, model or training results. Formal qualified Train/Validation/Offline Test counts start at `0/0/0` under this new evidence root and new dataset/run identity.

The source branch was recovered from remote commit `e2ec28c33ecaa455045477185b9c5dbc5e367538`, rebased on current `main`, and extended with the reviewed documents. The rebased source commits are `7102c67a`, `874ea617`, `72e5bc16`, `f3e1d826`, and document commit `fbc25063`. The two remote branch refs still point to `e2ec28c3`; no push is authorized.

The submodule conflict was resolved by merge commit `54463fce3bfa6192976e74113f5ed7152f708a3f`, whose parents are main pin `5a590b22770b270b71ba6a1c3443d4e67edc7f4b` and ACT RGB pin `498472acdcc57752071ac03245942d8c5fe06411`. Both dependency locks, the macOS install contract, and the gitlink select `54463fce`. Preserve this ancestry and do not downgrade or rewrite it.

The recovered ledger header and historical checkpoints contain stale worktree, commit and evidence paths. Do not rewrite historical entries. After receipt and preflight, append a new recovery checkpoint and update only the current header snapshot to this handoff's worktree, HEAD and evidence root. Record `evidence_unavailable` for the missing old root.

## Scope and stopping boundary

Execute Task 1–6, Task 7, Task 7A, Task 8–11 and Task 11A from the reviewed plan, in dependency order. First audit the recovered implementation against every refreshed interface and acceptance gate, then resume at the first incomplete contract. Existing code or historical checkmarks do not prove completion under the new contracts.

This task includes:

- reconciling the recovered implementation with fixed exact-N v3, start guard, owned cleanup and unified global mutation arbitration from `main`;
- completing camera/search/reset/execution safety, actual controller-reference labels, lossless dual-RGB recording and frozen split manifests;
- implementing and qualifying the ACT fixed exact-N collection workload, unified operation binding and physical-GPU workload arbitration;
- completing W1/W2 and bounded W4/W6/W8 qualification when prerequisites pass;
- collecting and independently verifying 50 Train, 10 Validation and 10 Offline Test successful expert episodes from frozen candidates;
- producing deterministic manifests, campaign index, verifier receipts, replay evidence, resource/throughput reports and a data acceptance report.

STOP before Task 12. Do not implement or run Task 12, Task 12A or Task 13–16. Do not install training-only dependencies, export a LeRobot dataset for training, launch training, create a policy bundle, run ACT inference/application, execute Rollout Validation/Test, or change the UI for model rollout. You may inspect the training design to preserve upstream interfaces, but training and policy application remain `NOT_STARTED` until separately authorized.

No physical robot operation is authorized. MuJoCo simulation is authorized only after the plan's lower-risk contract, unit, build, provenance and safety gates pass.

## First checkpoint and source audit

After the receipt, record to the new evidence root:

1. `hostname`, `pwd`, exact branch/HEAD, `git status --short --branch`, submodule status and remote/main ancestry;
2. SHA256 readback of this handoff, the reviewed design, plan and review record;
3. process/tmux/ROS/GPU inventory, including ownership, ports, `ROS_DOMAIN_ID` and `GZ_PARTITION` when present;
4. source/install/runtime provenance, with installed overlay initially `NOT_BUILT` unless verified otherwise;
5. the last trustworthy ledger checkpoint and the next experiment.

At dispatch the target worktree is clean. A separate old tmux session named `codex` runs another Codex process in `/home/matianyi/Projects/ros-moveit-demo`; preserve it and do not queue messages to it. No task ROS, MuJoCo, Gazebo, MoveIt or RViz stack was observed during dispatch preflight. Recheck before every live stack or source-writing phase. If another process starts writing this worktree, HEAD changes unexpectedly, or task-owned resource identity becomes ambiguous, stop source/runtime writes and append an ownership-conflict checkpoint.

Do not reset, clean, stash, rebase, pull, switch branch or rewrite history. Preserve all user work. Make small scoped local commits after their gates pass. Do not push, merge, publish or force-update either remote.

Use `superpowers:executing-plans` inline. Create or recover its plan workspace/ledger, read the spec as binding authority, run its preflight interface scan and use TDD for every implementation change. Record every necessary deviation as a ledger `Ruling:`. Do not mark a task complete without the plan's current expected evidence and fresh verification.

## Latest recovered technical boundary

The last tracked checkpoint is CP-024. It records an incomplete paused implementation, not accepted data collection:

- source tests at that time included 242 ACT/reset, 41 Teleop ownership/server and 26 native-simulation passes, but they predate this rebase and new contracts;
- formal dataset counts were `0/0/0`;
- Task 8–11A and data quotas were incomplete;
- Task 12 onward was `NOT_STARTED`;
- `EXP052` accepted the first moving pair but rejected the second with `REFERENCE_QUERY_INVALID`; the raw arm reference jumped to the terminal row while the gripper remained on the original curve;
- the arm controller then remained `CANCELING`, so the common Stop gate failed even though independently measured joint velocity was near zero;
- the planned next experiment was `EXP053`, an offline oracle for the installed Jazzy `Trajectory.sample` mutable cursor, followed by a side-effect-free accepted-interval reference reconstruction if the hypothesis was confirmed.

Re-establish current source and installed behavior before continuing that hypothesis. Use `superpowers:systematic-debugging`: distinguish native query cursor mutation from accepted-goal interval, cancellation, timestamp or rebase regressions. Preserve fail-closed `CONTROL_NOT_STOPPED`, `REFERENCE_QUERY_INVALID`, `PATH_TIMING_INVALID`, permit and deadline semantics. Never relax a safety/timing gate to make data collection progress.

## Refreshed non-negotiable contracts

- ACT policy observation is only head RGB, wrist RGB and state8; action is six absolute joint positions. Depth, simulator truth, TF, Planning Scene and task-camera inputs remain outside policy observation.
- The 120-second attempt budget uses monotonic wall time and cannot restart. Search is separately bounded. Timeout still requires safe stop/hold and evidence-preserving cleanup.
- All single-stack and parallel collection entry points require a persistent unified-service operation binding and `GlobalMutationArbiter` reservation before reset or spawn. The binding remains valid through terminal cleanup proof.
- Single collection, parallel collection, shared teacher Broker and future training use one persistent `ActGpuWorkloadArbiter` authority keyed by stable host identity and resolved physical GPU UUID. Index/UUID aliases and different `CUDA_VISIBLE_DEVICES` mappings to the same device must contend for one lease. Ambiguous or drifting mappings fail closed.
- Linux new execution uses `ParallelRuntimeConfigV3`, `BatchRequestV3`, ordered pending shared queue, start guard and fixed exact N. ACT `max_wave_size=20` is a collection fault-domain limit, not a `BatchRequestV3` point limit. No cross-N adaptive fallback is allowed in a qualification or formal campaign.
- Business failure is terminal. Infrastructure recovery must retain the same N, manifest, config and operation identity. Late, expired, revoked, superseded or uncommitted seals never become training-eligible results.
- Each wave retains its real coordinator journal and verifier receipt. The outer `campaign-index.json` references the journal root/hash, commit sequence, receipt root/hash and episode hash; it does not invent or merge a synthetic top-level coordinator journal.
- Only verifier-approved coordinator commits may enter a formal dataset. Qualification, failed, surplus, late, directory-only, missing-commit and old 0917a results remain excluded.
- Labels are causally aligned accepted/executing controller references. Next-frame measured joints are feedback, not labels. Joint order, units, timestamps, reset epoch, lease/owner identity and reference provenance are sealed and verified.
- Task 7A control ownership and Task 8 whole-robot contact/path supervision must pass before formal collection. Cup-only contact or planning success is insufficient.
- Five-set split isolation is frozen before collection. Rollout Validation/Test never receives expert labels or enters training data. Offline Test QC verifies integrity without model-based filtering.
- Successful business results still require independent physical final placement, support, release, retreat, controller, MoveIt shadow and whole-robot contact evidence.

## Test, build and runtime evidence

Follow the exact current plan and project-local `so101-dev` gates. For each change: create the failing regression first, observe the intended RED boundary, implement the minimum fix, run targeted GREEN, then the affected module's complete ordinary test range and required package gate.

On ai-station, every pytest/benchmark/colcon run that creates fsync-heavy fixtures must use a unique, previously nonexistent directory under:

`/data/work/so101-evidence/act-data/20260924-fbc25063-resume/scratch/<test-run-id>/tmp`

Set `TMPDIR`, `TMP` and `TEMP`; use the exact test Python to assert `tempfile.gettempdir()` resolves inside it before the test starts. Save interpreter and module provenance, complete argv, stdout/stderr, elapsed time, true exit code, JUnit, collected/skipped counts and scratch path. Keep fsync/journaling/integrity enabled. Scratch becomes a deletion candidate after readback; do not delete it.

Each affected Python module's complete ordinary tests must run with `pytest-xdist -n min(8, logical CPU count)`. Targeted and serial runs are diagnostic only. Repair shared resource isolation rather than lowering worker count. Keep benchmark tests excluded unless benchmark code/config/adapters/reports/tests are changed or perception models are being selected.

Use a fresh worktree-specific build/install overlay under the registered evidence root or another path registered in the ledger. Verify exact executables before long-running commands. Source `/opt/ros/jazzy/setup.zsh` and the verified task overlay; do not use the canonical repo's stale install as proof. Distinguish dependency/bootstrap/underlay failures from source RED.

Use the risk ladder: contracts/unit tests, dry run, plan only, headless live simulation, GUI simulation. Register unique task-owned ROS domains, Gazebo partitions, sockets, ports, process manifests and cleanup ownership. Do not start a second conflicting stack. Keep GUI/CUA work in the designated project workflow, use fresh screenshots after actions and inspect the images; process liveness alone is not visual or physical acceptance.

## Qualification, formal collection and QC

After all prerequisites pass, run W1 single-entry smoke and replay readback, W1 fixed-composition semantic comparison and W2 functional qualification on frozen equivalent inputs. Qualification may use its explicit bootstrap exception; formal collection may not.

Use a separate frozen 40-scenario qualification load manifest for W4, W6 and W8. Each exact-N level must run without infrastructure retry or crash recovery to count as throughput qualification; every Worker must complete the required terminal leases per wave. Stop expansion at the first failing level. Repeat the selected stable level in a fresh run identity before formal collection. Qualification episodes never enter formal data.

For formal collection, preserve candidate, failed, surplus and unscheduled identities. Select the first N verifier-approved successes in frozen manifest order, independent of completion order. If candidates are exhausted, report `QUOTA_UNSATISFIED` with real counts. Never duplicate episodes, resample silently, loosen QC, retry business failures or import directory-scanned artifacts to fill quotas.

For every selected episode verify file count/size/SHA256, lossless RGB decode/shape/key/order, causal 10 Hz grid, timestamp monotonicity/skew/freshness, finite state8/action6, joint order/units/limits, reference source, reset epoch, owner/lease/batch/Worker/coordinator identity, no hidden truth/depth, no cross-split scene/seed/state/trajectory leakage, and source/config/calibration/overlay/runtime/model provenance. Verify final physical state independently from MoveIt success. Replay representative expert actions without using sealed test scenarios for tuning.

The final data checkpoint must include deterministic dataset and campaign manifests, selected/surplus/failed/unscheduled counts, qualification/resource/throughput reports, machine-readable QC summary, replay evidence, and a concise acceptance report. State every unmet gate. Keep all failed evidence.

## Stop and reporting rules

Continue autonomously until one of these occurs:

1. the Task 1–11A data acceptance contract is met;
2. a destructive or irreversible action would be required;
3. a push, merge, publication, physical robot operation or training authorization is required;
4. a security-sensitive action requires new authority;
5. source ownership is ambiguous or the plan is so broken that every path is guesswork.

Before every compaction, pause or stop, update the runtime ledger checkpoint with exact source commit, dirty paths, installed overlay, executable/package prefix, ROS domain, Gazebo partition, owned/preserved processes, last valid experiment, confirmed/disproven hypotheses, evidence paths and one exact next command.

At completion or stop, report retained runs, archived runs and deletion candidates separately. Delete nothing without explicit user authorization. Do not claim training, policy application or end-to-end ACT success. The stopping checkpoint must state `Task 12 onward NOT_STARTED`.
