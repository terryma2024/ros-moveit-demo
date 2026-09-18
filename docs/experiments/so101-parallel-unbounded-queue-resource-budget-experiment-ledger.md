# SO-101 unbounded queue / per-N resource budget — execution ledger

Single writer: the DST inline executor session for dispatch `so101-unbounded-queue-20260918-84620fc0`.
This ledger records execution of the frozen plan
`docs/superpowers/plans/2026-09-18-so101-parallel-unbounded-queue-resource-budget-implementation.md`
(SHA-256 `cd1b606fd8a40d7bb6e576f6f59a6ef5abcb45a8bee7e2a669c7b7a40bfc8789`) against the frozen design
(SHA-256 `5e085f98e9926591fbefd3d6e16c16b33bfc9956df9221c46f383b310553657b`).

```yaml
task_id: so101-parallel-unbounded-queue-resource-budget
goal: Emit v2 no-quota contracts, a shared no-quota queue, one exact-N resource-budget provider, an
  independently authorized candidate measurement path, independent promotion, and browser acceptance.
success_contract: Stage A offline implementation gates; Stage B full gates and frozen copied installs;
  Stage C finite authorized per-N measurement producing sealed B/Q and candidate P; Stage D independent
  review and operator promotion; Stage E owned live Chrome acceptance. Each Nx budget stays NOT_MEASURED
  until its own current-hardware evidence satisfies the plan.
worktree: /data/work/so101-worktrees/unbounded-queue-resource-budget
branch: codex/so101-unbounded-queue-resource-budget
base_commit: 84620fc0529779a27c6985f8717d78f0386e0135
current_commit: 84620fc0529779a27c6985f8717d78f0386e0135
evidence_root: /data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main
task_root: /data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget
dispatch: /data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/dispatch-20260918-84620fc0
confirmed_conclusions:
  - Frozen design/plan hashes match the dispatch-required values (EXP-UQ00).
  - Published base commit contains no v2 contract, no resource_budget.py, no operator_recovery.py, and
    still contains the three N>3 hardcodes and 41 max_points_per_worker references (EXP-UQ00).
  - Canonical /data/work/ws_moveit is main at 6701a7be with only the two preserved untracked documents;
    the task worktree is clean on the dispatch branch (EXP-UQ00).
  - No Teleop/validation/ROS process, no tmux execution session and no listener on 8000/8001 exists;
    CP-Z01/CP-Z02 stop state is unchanged and no signal was sent (EXP-UQ00).
disproven_routes:
  - "Restarting or recovering services from historical PIDs: CP-Z01/CP-Z02 already stopped them and the
    design forbids treating a stopped service as a missing-worker invitation (design 507-513)."
  - "Running the ordinary demo gate against the deep mandated scratch: 71 pre-existing socket-path
    failures, root-caused to >107-byte Unix socket paths, not to task code (EXP-UQ00)."
open_hypotheses:
  - Whether the operator approves a short-path scratch relocation for the socket-based demo gate in
    Stage B, or accepts those pre-existing failures as documented environment blockers.
latest_checkpoint: CP-UQ00
next_experiment: EXP-UQ01
```

## Approvals (four independent authorities; plan lines 13-25, 36-40, 144, 193)

| Authority | State | Evidence |
| --- | --- | --- |
| Stage A offline implementation + scoped local commits | GRANTED by dispatch handoff | `dispatch-20260918-84620fc0/handoff.md` lines 26, 30-38; `executor-receipt.md` |
| Candidate owned measurement window (Stage C) | NOT GRANTED — pause before any candidate measurement | design 188-194; plan Task 13 Stage C |
| Owned service refresh / exclusive recovery / deployment window (Stage B/C/D) | NOT GRANTED — pause before any owned service start, stop or deployment | design 507-513; plan Task 12 |
| Profile promotion (exact-N/hash operator approval, Stage D) | NOT GRANTED — no APPROVED M may be written | design 490-494; plan Task 14 |
| Exclusive owned live Chrome acceptance window (Stage E) | NOT GRANTED — pause before live browser acceptance | design 554-556; plan Task 15 |

## Environment and provenance (fresh, EXP-UQ00)

- Host `AI-STATION-001`, 24 logical CPUs, `MemTotal: 32583596 kB` — observations only, never a budget.
- `WORKTREE=/data/work/so101-worktrees/unbounded-queue-resource-budget`, branch
  `codex/so101-unbounded-queue-resource-budget`, HEAD `84620fc0529779a27c6985f8717d78f0386e0135`,
  `git status --porcelain` empty, submodule `third_party/mujoco_ros2_control` e4c0241a.
- Canonical `/data/work/ws_moveit` main `6701a7be794eac410aa351106cbc17d58568d1ad`, tracked clean, two
  preserved untracked documents (operator recovery guide, fixed-eight proposal). Not modified.
- `TEST_PYTHON=/data/work/so101-evidence/teleop-chrome-e2e/20260916T130435Z-e2ffff62-kimi01/python-venv/bin/python3`
  (Python 3.12.3; pydantic 2.13.4 from `TEST_SITE`) — verified fresh before use.
- Environment fact: that shared venv ships `_kimi_so101_demo_editable.pth` plus
  `_kimi_so101_demo_editable_finder.py`, a meta-path finder that hard-maps `so101_demo` to
  `/data/work/ws_moveit/.worktrees/kimi-teleop-chrome-e2e/src/so101_demo_py/src`. The finder honors
  `SO101_DISABLE_KIMI_EDITABLE_FINDER=1`; the task environment sets it per invocation so the task
  overlay is the only `so101_demo` origin. No shared file, venv or global setting was changed.
- `dst` `/usr/local/bin/dst` reports `@deepseek-harness-tui/dsh-tui 0.10.2`; Bun 1.3.14 at
  `/home/lenovo/.bun/bin/bun`; colcon `/usr/bin/colcon`.
- Recorded test entry points: `$TASK_ROOT/tools/test-gate.zsh` SHA-256
  `04b2d82330e4dab1910832b519b89e1421aad02e38c70bbc0005b882546cebb4` (contains the plan's exact
  `so101_pytest`, `so101_record_tool`, `so101_colcon`, `so101_bun` text) and `$TASK_ROOT/tools/task-env.zsh`
  SHA-256 `a9895d0b6a7edc42bc92170c57e5f563b4d8b6ba25f548bc6da064155a21c3ff` (frozen variables +
  per-invocation overlay activators). No bare tool invocation is used for build/test/Bun.
- AGENTS.md in the worktree already carries the published `## Task model selection` section (lines 73-85,
  semantically the plan's required rules). No duplicate section was appended; the file was left byte-identical.

## EXP-UQ00 — Task 0 fresh ownership, isolation and reproducible test entry

```yaml
experiment_id: EXP-UQ00
status: VALID
prior_experiment: NONE
hypothesis: The published base commit is clean and unmodified, no execution process remains, and a
  task-owned dev overlay can run the recorded gates with the exact shared test interpreter.
prediction: Ownership facts match the dispatch preflight; the dev overlay imports so101_demo/so101_teleop
  from the worktree; baseline gates either pass or fail for pre-existing environment reasons.
single_variable: NONE (read-only preflight plus first dev overlay build)
lifecycle: ISOLATED_STACK
preconditions:
  - User-authorized stop state from CP-Z01/CP-Z02; no service to preserve or restart.
success_criteria:
  - Clean worktree at base commit; dev overlay builds exit 0; overlay import check passes; baselines recorded.
failure_criteria:
  - Unexpected dirty tracked files, running owned service, or overlay importing foreign source.
invalid_criteria:
  - Hidden running stack, foreign modification of the worktree, or a wrong interpreter.
provenance:
  source_commit: 84620fc0529779a27c6985f8717d78f0386e0135
  install_overlay: /data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/dev-install
  runtime_executable: /data/work/so101-evidence/teleop-chrome-e2e/20260916T130435Z-e2ffff62-kimi01/python-venv/bin/python3
  ros_domain_id: n/a (no ROS runtime started)
  gz_partition: n/a
commands:
  - command: so101_colcon dev-build build --packages-select so101_demo_py so101_teleop --allow-overriding so101_demo_py so101_teleop --symlink-install --build-base $TASK_ROOT/dev-build --install-base $TASK_ROOT/dev-install
    exit_code: 0
  - command: so101_pytest baseline-demo src/so101_demo_py/test
    exit_code: 2
  - command: so101_pytest baseline-demo-rest src/so101_demo_py/test --ignore=src/so101_demo_py/test/test_grounding_dino_domain_retention.py -q
    exit_code: 1
  - command: so101_pytest baseline-teleop src/so101_teleop/test -q
    exit_code: 0
observed:
  - dev-build run root colcon/dev-build.FVW8grLF, elapsed 35.87 s, exit 0 (colcon/test-gate recorded).
  - Overlay import check exit 0 after SO101_DISABLE_KIMI_EDITABLE_FINDER=1; so101_demo resolved to
    dev-build/so101_demo_py/so101_demo/__init__.py and so101_teleop to dev-install/.../so101_teleop/__init__.py.
  - baseline-demo exit 2 = pytest collection error, ModuleNotFoundError: torch, single module
    test_grounding_dino_domain_retention.py. Matches the pre-existing environment blocker in the root
    ledger CP-C02 (no dependency install authorized).
  - baseline-demo-rest 71 failed / 3012 passed / 12 skipped / 40 errors in 303.32 s
    (scratch/baseline-demo-rest.APiSNyVF). Failure groups: test_parallel_batch_resources 35,
    test_mujoco_scene_geometry 5+28 errors, test_parallel_batch_cli 22, test_mujoco_runtime_observability
    12 errors, installed provenance 3, camera plugin 2, macos install contract 2, sam/ipc 2.
  - baseline-teleop 489 passed in 38.95 s, exit 0 (scratch/baseline-teleop.gD0uLflg). Matches the
    historical 489-passed record and establishes a clean product baseline for the teleop package.
inferred:
  - The dominant demo-gate failure class is environmental: tests build Unix sockets under
    `Path(TMPDIR).parent/'qe'`, and TASK_ROOT is 108 characters, so paths exceed the 107-byte
    AF_UNIX limit (ResourceAllocationError UNIX_SOCKET_PATH_TOO_LONG). A one-off diagnostic with a short
    /data scratch (deleted afterwards, no evidence retained) made
    test_fixed_cli_epoch_matches_real_journal_before_endpoint_or_worker_setup pass, confirming the cause.
  - Those failures are therefore NOT task regressions, but they do block a clean full-demo gate in
    Stage B until the scratch path question is decided by the operator.
conclusion: VALID. Task 0 preflight, isolation, recorded test entry and dev overlay are established;
  baseline failures are classified as pre-existing environment blockers, not new-function RED.
evidence:
  - $TASK_ROOT/run-index.txt, $TASK_ROOT/colcon/dev-build.FVW8grLF/
  - $TASK_ROOT/scratch/baseline-demo.Yj4abRMz/, scratch/baseline-demo-rest.APiSNyVF/, scratch/baseline-teleop.gD0uLflg/
  - dispatch-20260918-84620fc0/executor-receipt.md
decision: KEEP
next_experiment: EXP-UQ01
```

## CP-UQ00 — Task 0 checkpoint

```yaml
checkpoint_id: CP-UQ00
last_valid_experiment: EXP-UQ00
current_hypothesis: Stage A offline implementation can proceed task-by-task with targeted RED/GREEN gates.
working_tree_status: clean at 84620fc0 (task ledger untracked until the Task 0 commit)
owned_processes: NONE (no service, tmux execution session or ROS runtime started)
preserved_processes: NONE running from this task family; canonical install, Kimi venv, other worktrees and
  Codex/dst sessions untouched
confirmed_conclusions:
  - Frozen design/plan hashes verified (EXP-UQ00).
  - Teleop baseline 489 passed; demo baseline blocked by pre-existing torch and socket-path environment issues.
disproven_routes:
  - Claiming a clean full-demo gate before the scratch-path question is resolved.
open_risks:
  - Stage B full-demo gate currently cannot pass in this environment without an operator decision on scratch path.
  - Socket-creating Stage A target tests may hit the same path limit; each occurrence will be reported, not hidden.
next_command: implement Task 1 (operator recovery entry) RED test, then GREEN
```

## EXP-UQ01 — Task 1 audited operator recovery integration

```yaml
experiment_id: EXP-UQ01
status: VALID
prior_experiment: EXP-UQ00
hypothesis: The retained six-file recovery snapshot can be integrated with targeted patches so the
  formal operator recovery entry exists, previews by default, and never rewrites history or claims cleanup.
prediction: RED fails only on the missing formal entry; GREEN passes the snapshot suite plus the plan's
  keyword-only/preview/no-write assertions without touching original fences.
single_variable: recovery source integration
lifecycle: ISOLATED_STACK
preconditions:
  - Worktree clean at Task 0 checkpoint; no running validation service; live apply remains unauthorized.
success_criteria:
  - 22 RED tests fail at "formal operator recovery entry is missing"; GREEN passes all of them plus the
    package layout registration test; snapshot bytes are reproduced exactly.
failure_criteria:
  - RED fails on import path/interpreter errors, or GREEN needs weakened assertions.
invalid_criteria:
  - Wrong overlay origin, foreign so101_teleop module, or any live apply/recovery.
provenance:
  source_commit: 8709912d9a60d3b5eb4e0f4a20f7c2b3ab0e9d38 (Task 0 checkpoint, pre-Task-1 tree)
  install_overlay: $TASK_ROOT/dev-build + $TASK_ROOT/dev-install (symlink-install dev overlay)
  runtime_executable: the exact shared TEST_PYTHON above
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest recovery-red src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py -q
    exit_code: 1
  - command: so101_pytest recovery-green src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py src/so101_teleop/test/test_expert_validation_package_layout.py -q
    exit_code: 0
observed:
  - RED scratch/recovery-red.GLNxsSja: 22 failed in 0.59 s; 42 occurrences of the intended
    "formal operator recovery entry is missing" assertion, no import/interpreter error.
  - GREEN scratch/recovery-green.8iJu3eb9: 28 passed in 15.56 s; JUnit comparison shows all 22 RED test
    IDs are present and passing, plus the 6 package-layout tests; zero non-pass results.
  - Integration used reviewed snapshot diffs (patch -p0), not whole-file overwrite: CMakeLists.txt,
    expert_validation/store.py and test_expert_validation_package_layout.py are byte-identical to the
    retained snapshot, and the three new files were copied with their recorded hashes
    (operator_recovery.py d8e7cf0c, recover script 3e3706c8, recovery test 6f86a679 + appended key RED tests).
inferred:
  - The snapshot's RuntimeInspector keyword-only constructor and preview default are preserved; the plan's
    Task 1 interface note is satisfied by the retained API.
conclusion: VALID. Formal recovery entry integrated offline; NOT deployed and NOT ONLINE_RECOVERY_VERIFIED.
evidence:
  - scratch/recovery-red.GLNxsSja/, scratch/recovery-green.8iJu3eb9/
  - recovery-source-snapshot hashes above; commit for this task (see CP-UQ01)
decision: KEEP
next_experiment: EXP-UQ02
```

## CP-UQ01 — Task 1 checkpoint

```yaml
checkpoint_id: CP-UQ01
last_valid_experiment: EXP-UQ01
current_hypothesis: v2 contract and readonly v1 reader can be added without changing v1 bytes.
working_tree_status: Task 1 six files staged/committed; no other tracked changes
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - Recovery entry exists and previews by default; original fence/history untouched in all tests.
disproven_routes:
  - Treating receipt persistence as deployment success (design 503-505); live apply stays gated to Stage B.
open_risks:
  - Live/installed recovery entry and online refresh remain unverified and unauthorized.
next_command: implement Task 2 RED (test_v1_can_be_read_but_not_executed)
```

## EXP-UQ02 — Task 2 v2 execution contract and immutable v1 reading

```yaml
experiment_id: EXP-UQ02
status: VALID
prior_experiment: EXP-UQ01
hypothesis: A closed v2 contract plus a read-only historical reader can remove the lifetime quota from
  new execution without changing any v1 byte or the v1 journal frame format.
prediction: RED fails only because require_v2_execution is absent; after implementation the new contract
  tests, the retained journal tests and the crash-recovery tests all pass.
single_variable: version-two contract surface
lifecycle: ISOLATED_STACK
preconditions:
  - Task 1 committed; dev overlay importable; no runtime process started.
success_criteria:
  - require_v2_execution rejects 1/1 and 3/2 with LEGACY_CONTRACT_EXECUTION_FORBIDDEN and accepts 2/2.
  - v1 YAML stays byte-identical (aadcac01d...), historical view is read-only and byte-stable.
  - v2 config is closed (unknown/duplicate/nonfinite rejected) and carries no quota/resource-formula fields.
  - v2 journal records schema_version 2 and still replays read-only; v1 header bytes are unchanged.
failure_criteria:
  - Any v1 byte change, weakened assertion, or v2 config accepting legacy quota fields.
invalid_criteria:
  - Wrong overlay, foreign module origin, or the tests not actually running.
provenance:
  source_commit: e81634585 (Task 1 checkpoint; this task's parent commit)
  install_overlay: $TASK_ROOT/dev-build + $TASK_ROOT/dev-install (symlink-install dev overlay)
  runtime_executable: the exact shared TEST_PYTHON above
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest contracts-red src/so101_demo_py/test/test_parallel_batch_contracts.py::test_v1_can_be_read_but_not_executed -q
    exit_code: 1
  - command: so101_pytest contracts-green src/so101_demo_py/test/test_parallel_batch_contracts.py src/so101_demo_py/test/test_parallel_batch_journal.py src/so101_demo_py/test/test_parallel_batch_crash_recovery.py -q
    exit_code: 0
observed:
  - RED scratch/contracts-red.Qp8SMjIr: 1 failed, ImportError "cannot import name 'require_v2_execution'"
    at the intended new boundary (not a dependency/collection failure).
  - GREEN scratch/contracts-green.*: 116 passed in 1.39 s, zero failures; the 9 new tests all ran and
    passed (v1 gate, v1 YAML hash freeze, read-only historical view, unknown-version rejection, closed
    v2 config, unknown/duplicate/nonfinite rejection, mode/count-only fixed config, no-quota v2 request
    with retry N1 invariants, v2 journal schema 2 readback).
  - v1 YAML/source hash baseline retained at bindings/v1-contract-baseline.json (base 84620fc0 blob hashes
    for contracts/journal/coordinator/resources/adaptive_contracts plus the three v1 YAML hashes).
inferred:
  - ContractError.code is additive: existing message-based assertions keep working (full retained test
    modules passed unchanged).
conclusion: VALID. v2 contract and read-only v1 history exist; no new execution path is enabled yet.
evidence:
  - scratch/contracts-red.Qp8SMjIr/, scratch/contracts-green.*
  - $TASK_ROOT/bindings/v1-contract-baseline.json
decision: KEEP
next_experiment: EXP-UQ03
```

## CP-UQ02 — Task 2 checkpoint

```yaml
checkpoint_id: CP-UQ02
last_valid_experiment: EXP-UQ02
current_hypothesis: The acyclic identity layer (L/S/E/I/R plus full-byte audit) can be added as a new
  module with synthetic closed configs only.
working_tree_status: Task 2 files committed; no other tracked changes
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - v1 bytes/hashes frozen and still readable; v2 contract closed and quota-free (EXP-UQ02).
disproven_routes:
  - Reusing v1 asdict hashing for v2 identity (design 434-455): v2 separates semantic S from raw bytes.
open_risks:
  - Later consumers must call require_v2_execution before any spawn; not yet wired (Tasks 7-10).
next_command: implement Task 3 RED (test_first_promotion_changes_audit_not_semantic_identity)
