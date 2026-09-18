# SO-101 ACT data implementation handoff — 2026-09-17

你当前直接运行在 ai-station 上。不要 ssh 到 ai-station；仓库、tmux、进程、CUA 和截图命令都在当前主机直接执行。

这是开发任务。用户已授权按计划自主执行，采用 inline 模式：由本任务直接实现、构建、测试、运行和校验，不启动 subagent、不把实施分发到新 Codex/Kimi 任务。继续直到下面的数据验收完成，或存在必须由用户解决的真实阻塞。不要仅交付计划或在正常可逆步骤前重复询问。

## Execution identity and authoritative inputs

- Worktree: `/data/work/ws_moveit/.worktrees/kimi-teleop-chrome-e2e`
- Branch: `codex/kimi-teleop-chrome-e2e`
- Dispatch baseline: `5182ed71905ed376c64ab9a400a92de552703293`
- Task evidence root: `/data/work/so101-evidence/act-data/0917a`
- Runtime experiment ledger: `docs/experiments/so101-act-data-experiment-ledger.md` in that worktree.
- Reviewed design input: `<evidence-root>/inputs/2026-09-10-so101-act-head-wrist-rgb-design.md`, SHA256 `73db08a54f9a29aa5b4c164a214fbc824b981250bb69ee0fb42fd3c4de264b67`.
- Reviewed implementation plan: `<evidence-root>/inputs/2026-09-11-so101-act-head-wrist-rgb-implementation.md`, SHA256 `6a7985f6a3ffc3c25eeb02722899ae6e9c4f4bccb727a52bc9137287c163e93a`.
- Independent review record: `<evidence-root>/inputs/so101-act-parallel-plan-review-experiment-ledger.md`. Final Astra high review passed without P0/P1/P2/P3 findings. This proves document consistency only, not runtime readiness.

Read the complete design, implementation plan and review ledger before implementation. Verify these hashes. The checked-out documentation is older; the transferred reviewed inputs govern this task. Preserve old tracked copies in evidence, confirm they have no pre-existing user edits, then update those two repository documents to the reviewed versions. Adapt measured baseline facts and integration paths to the actual branch; never reset/rebase to the plan's historical commit or downgrade the submodule to its historical lock. Record any necessary contract clarification in the ledger before proceeding.

## Scope and stopping boundary

Execute Task 1–6, Task 7, Task 7A, Task 8–11 and Task 11A, in dependency order. This includes implementing prerequisites, calibration, execution safety, actual controller-reference labels, lossless RGB recording, frozen sampling manifests, single-stack QC, parallel qualification and formal expert demonstration collection.

STOP before Task 12. Do not implement or run Task 12, Task 12A or Task 13–16: no LeRobot export/training, no short training smoke, no formal ACT model training, no policy inference/application, no ACT UI rollout or model evaluation. Data-only validation and supervised expert-action replay belong to this task. Rollout Validation/Test scenario manifests can be frozen as Task 10 requires, but do not execute them to collect expert labels or apply a model.

Acceptance target: 50 Train, 10 Validation and 10 Offline Test qualified successful expert episodes, selected deterministically from frozen candidates, with independent physical outcome, image/state/action/timestamp correctness, replay evidence and complete provenance. Failures and surplus are retained separately. If frozen candidates are exhausted, report QUOTA_UNSATISFIED with the real counts; never manufacture, duplicate, relax gates or silently rerun business failures to fill quotas. A new data version may be sampled only through the approved frozen-manifest procedure.

## Baseline and ownership preflight

Before task actions, create the dispatch receipt requested by the startup prompt. Then record hostname, pwd, exact branch/HEAD, status and submodule status in `<evidence-root>/preflight.txt`. Confirm the worktree/branch above; do not switch to `/data/work/ws_moveit` main. Read applicable parent and worktree AGENTS.md, `$so101-dev` and its current access/system-map/debug/test/ledger/dependency references. Read existing experiment ledgers before starting stacks.

At dispatch, the known dirty path is `src/so101_teleop/web/MUJOCO_LOG.TXT`; preserve it and any additional existing changes. An older Kimi task in tmux `kimi-teleop-chrome-e2e` is paused at provider quota. It has unfinished Teleop acceptance work and must not be resumed or modified by this task. The existing `codex:0` pane is idle at `/data/work/ws_moveit` and is preserved. Some older scripted-validation servers are still running; inventory their PIDs/ports and preserve them. Do not kill sessions, perform broad pkill, or treat their helper output as ACT runtime evidence.

Recheck for a concurrent writer or live stack immediately before modifying sources and starting execution. If the old Kimi task resumes, or HEAD/source changes unexpectedly, stop writes and save an ownership-conflict checkpoint instead of racing. Existing helper servers alone do not block implementation; choose distinct ports/domains/partitions and account for resource use. No physical hardware operation is authorized.

Record source/install/runtime provenance and use a fresh worktree-specific overlay. Do not blindly source the main worktree install and claim it proves the new implementation. Build inside this worktree or its registered evidence root as appropriate, then source Jazzy `setup.zsh` and the verified new overlay. Preserve baseline features, task_camera RGB-D teacher, V5 Agent/VLM/MoveIt behavior and existing sampler.

## Non-negotiable data and control contracts

- ACT inputs: head+wrist RGB only, 640×480 at 10 Hz; state8 is six measured joints plus sin/cos neck yaw. Action6 contains absolute joint references in radians. No depth or simulator truth in the policy observation. task_camera RGB-D remains MoveIt teacher input.
- Neck search is deterministic and independently bounded. Bearing is fresh, attempt-scoped and invalidated on reset; it is not distance or truth pose.
- `act_timeout_s=120`: the monotonic two-minute attempt budget includes the recorded expert phase/retries/retreat according to the approved contract. Do not restart the clock to extend an attempt. Search has its separately bounded contract.
- Labels must be accepted/executing expert controller references aligned causally with RGB/state/time; do not substitute next-frame measured joints. Drop stale/invalid frames and seal failed runs with explicit reasons.
- Task 7A common control ownership and Task 8 path/full-robot contact supervision must pass before live formal collection. Cup-only contacts and goal-only collision checks do not establish safety. Reset writes, controller stop confirmation and release/retreat evidence follow the plan.
- Five-set split isolation is frozen before collection. `collection.json` is a deterministic three-split projection of sealed `splits.json`, retaining its SHA256. Offline Test QC is integrity checking, not model-based selection or tuning. Qualification scenarios are excluded from formal datasets.
- Existing multi-stack MoveIt point validation is infrastructure, not an ACT recorder. Implement the specified closed workload ports/factories, reference source, atomic seal/import and actual child composition; keep lease/heartbeat/fallback/cleanup authoritative in the existing runner.
- Reuse max-20-item waves, full-wave barriers and frozen-manifest-order selection. Business FAILED is terminal. Only classified infrastructure invalidation may use bounded retry. Crash reconciliation must fence old resources and use coordinator authority; late/expired/revoked/replaced lease seals cannot become successes.
- Use the unified ACT socket endpoint manifest, including each command broker. Check the longest complete path in bytes before spawning; 107 bytes allowed, 108 refused. Keep prescribed short runtime paths and record actual endpoints/PIDs.

## Execution and qualification gates

Follow named files/interfaces/tests/commands in the plan. Update plan checkboxes only after corresponding evidence passes. For each code boundary run the relevant failing regression first, then minimal fix, targeted tests, package gates and runtime reproduction. Do not collect the benchmark suite for unrelated work. Web tools use Bun if touched. Dependency installs follow the local skill; record exact versions and hashes. Do not install training dependencies for excluded stages.

For every ai-station pytest/colcon test run using fsync fixtures, create a unique previously nonexistent `<evidence-root>/scratch/<test-run-id>/tmp` on /data NVMe. Set TMPDIR, TMP and TEMP before collection, and use the exact test Python to assert `tempfile.gettempdir()` resolves there. Save the command, Python path, elapsed time and readback. Fail closed if the scratch contract fails; do not disable fsync or use tmpfs. Classify read-back scratch trees as deletion candidates; do not delete them.

Task 6 may initially emit CALIBRATION_REQUIRED; complete measurements and Task 7–8 evidence before declaring QUALIFIED. Linux evidence does not prove macOS camera regression; record unavailable platform gates explicitly. Do not turn planned thresholds or nominal coordinates into measurements.

After prerequisites pass: W1 five-scenario smoke and frame/action/physical readback with replay; full eight-scenario single-stack baseline, W1 parallel entry and W2 functional qualification on identical frozen inputs. Start formal parallel defaults at W2/fallback W1 only after qualification. Expand W4→W6→W8 using the separate 40-scenario/two-wave sustained-load manifest, with ≥2 terminal leases per worker per wave and pure level `[n]`, zero infrastructure retry/fallback/crash continuation. Stop expansion at the first failing level. Repeat the selected default on a separately registered new run root before formal collection. Choose the stable highest qualified valid-episodes/minute level using frozen resource/RTF/frame/QC gates, never inherit MoveIt W8 performance claims.

The main task uses the single registered root above. The plan's explicitly separate qualification/replication runs each receive their own unique short root under `/data/work/so101-evidence/act-data/`, registered as separate run identities in the same ledger before use; do not scatter one run's raw evidence across roots. Preserve runs and hashes. Use the plan's short run codes and wave directories throughout.

## Data correctness acceptance and final checkpoint

For every selected episode, read back sealed files and verify: file count/size/SHA256; both RGB streams decode losslessly with correct shape/key/order; complete causal 10 Hz grid, monotonic source and monotonic wall timestamps, tolerated skew/freshness; finite state8/action6, joint order/units/limits, accepted/executing reference source, reset epoch and ownership identity; no hidden truth/depth features; no cross-split scene/seed/state/trajectory leakage; calibration/config/source/overlay/runtime/model provenance. Verify manifest order and physical final placement, support/release/retreat and whole-robot contact supervision independently of MoveIt SUCCESS. Save fresh visual evidence and actually inspect it under `$gui-capture`. Replay representative expert actions as the plan requires, including reference-versus-feedback timing and physical outcome; do not replay sealed test scenarios for tuning.

Produce a machine-readable QC/integrity summary, deterministic dataset manifest with selected/surplus/failed/unscheduled counts per split, original frozen manifests, qualification/resource/throughput reports and a concise data acceptance report. Document any unmet gates plainly. Keep failed evidence. Do not claim training or ACT runtime acceptance.

Use small scoped local commits where the plan requires, preserving unrelated changes and committing submodule changes before parent gitlink/lock updates. No push, merge or history rewrite is requested. Update `docs/experiments/so101-act-data-experiment-ledger.md` after each experiment and before compaction/stop, with exact provenance, statuses, ownership and next command. Finish with retained runs, archived runs and deletion candidates; delete nothing without user authorization. Once data collection/QC passes, save a stopping checkpoint explicitly stating Task 12 onward NOT_STARTED, then stop.
