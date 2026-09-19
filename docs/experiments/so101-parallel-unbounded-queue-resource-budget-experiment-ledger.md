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
current_commit: 93fc681aa4021a80b3964e7639c81d2d99a2a6b4 (HEAD when this header was refreshed; later
  runtime commits and the live HEAD are recorded per checkpoint below)
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
  - CORRECTION (CP-UQ32): that question was answered during the offline units - the AF_UNIX transport
    moved to the dirfd `/proc/self/fd/<fd>/<name>` form and the suite runs green; this entry is kept as
    history and is no longer an open question.
latest_checkpoint: CP-UQ281 (tail of this file)
superseding_dispatch: b82d10b8-32bf-47b4-9aa9-9bbec17d3a6b (lightweight start guard)
superseding_plan: docs/superpowers/plans/2026-09-19-so101-parallel-validation-lightweight-start-guard-implementation.md
  SHA-256 d75597a73f7d211eb31c4e75e3e6cb2f696d86dc953405f393962747c814b141
superseding_design: docs/superpowers/specs/2026-09-19-so101-parallel-validation-lightweight-start-guard-design.md
  SHA-256 73cc295ce6fba187c85e38081c458112b448357e844c7afa9e3a06ed3f2bfdb5
current_dispatch: macos-mps-private-ipc-f8176773-cfdb-437a-b23a-32367f0a7c97 on the mac-mini worktree
current_task_root: /tmp/so101-debug-unbounded-queue-w2-mac-mini-3eed4ddd-a50c-4c21-b78f-60be2216ef9d
current_plan: docs/superpowers/plans/2026-09-19-so101-macos-mps-private-ipc-implementation.md
  SHA-256 cd098f4025eb00cb1beae0b0072dcaca35010c9ab1c1ac2334b4bda37df3ead2 (review PASS, e8e91c78…7fc86)
current_design: docs/superpowers/specs/2026-09-19-so101-macos-mps-private-ipc-design.md
  SHA-256 480da6dcdfea1da988f9f4e706c8340dbb6d7283200c27bb723859119145db1b
current_worktree: /Users/matianyi/Projects/robot_demo_001/.worktrees/so101-unbounded-queue-resource-budget-mac-mini
current_branch: codex/so101-unbounded-queue-resource-budget (HEAD b55c181e at takeover)
next_experiment: wire the composed campaign behind a CLI entry point, then attempt a first FULL_RESTART
correction_cp_uq229: the header's `worktree`, `evidence_root` and `task_root` fields describe the
  historical ai-station Stage A-E dispatch (`84620fc0`) and are not rewritten, because that history
  is not invalidated. The live dispatch, worktree and evidence root for the current macOS MPS/private
  IPC implementation are the `current_*` fields above. The pre-CP-UQ219 `next_experiment` value was
  stale; no historical experiment entry was altered.
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

## EXP-UQ03 — Task 3 acyclic semantic identity and full-byte audits

```yaml
experiment_id: EXP-UQ03
status: VALID
prior_experiment: EXP-UQ02
hypothesis: L/S/E/I/R plus full-byte audits can separate execution semantics from deployment bytes so
  the first null-to-approved promotion needs no remeasurement and no self-referential digest.
prediction: RED fails with the identity module absent; GREEN proves the promotion-invariance property,
  free-rule tracking, frozen-rule rejection and carrier-only byte drift.
single_variable: resource_identity module plus public v2 field aliases
lifecycle: ISOLATED_STACK
preconditions:
  - Task 2 committed; v2 config parsed by the closed parser.
success_criteria:
  - Candidate vs first-promoted config share S but differ in raw bytes.
  - Frozen execution/safety/coverage rule changes are rejected; free sampling/clock rule changes alter S.
  - Non-carrier byte drift changes I and is rejected by verify_deployment_equivalence; carrier ref change
    plus registered prefix move is accepted; runtime fact drift is rejected.
failure_criteria:
  - Any self-referential digest, deployment-key tolerance, or byte-equivalence bypass.
invalid_criteria:
  - Pre-existing environment failures being counted as task failures without attribution.
provenance:
  source_commit: 573120b28 (Task 2 checkpoint; this task's parent commit)
  install_overlay: $TASK_ROOT/dev-build + dev-install (symlink-install dev overlay)
  runtime_executable: the exact shared TEST_PYTHON above
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest identity-red src/so101_demo_py/test/test_parallel_resource_identity.py -q
    exit_code: 1
  - command: so101_pytest identity-green src/so101_demo_py/test/test_parallel_resource_identity.py src/so101_demo_py/test/test_parallel_batch_resources.py -q
    exit_code: 1
observed:
  - RED scratch/identity-red.*: 8 failed, all ModuleNotFoundError for
    so101_demo.parallel_batch.resource_identity (intended missing module).
  - GREEN scratch/identity-green.*: 116 passed, 36 failed. All 8 identity tests pass. 35 of the failures
    are in test_parallel_batch_resources.py and are byte-identical to the pre-task baseline failure set
    (baseline-demo-rest.APiSNyVF), dominated by ResourceAllocationError UNIX_SOCKET_PATH_TOO_LONG from the
    deep mandated scratch; 0 newly failing and 0 no-longer-failing test IDs. The 36th was a defect in my
    own new test (wrong mutation target), fixed and re-run.
  - After the fix: identity tests 8/8 pass; the same 35 pre-existing resources failures remain, none new.
  - L binds algorithm DEPLOYMENT_REFERENCE_SUBSTITUTION_V2, the exact execution/sampling/clock/safety/
    coverage field lists, the two declared carriers and the raw-byte rule for every non-carrier.
inferred:
  - The 20% safety constants and frozen execution values make unsafe rule drift impossible before any
    measurement exists, matching design 434-488.
conclusion: VALID. Identity layer implemented; deployment audits/exclusions are Stage B work.
evidence:
  - scratch/identity-red.*, scratch/identity-green.*
decision: KEEP
next_experiment: EXP-UQ04
```

```yaml
checkpoint_id: CP-UQ03
last_valid_experiment: EXP-UQ03
current_hypothesis: Closed typed allocation contexts can be issued only by private authorities and shared
  by all three production consumers.
working_tree_status: Task 3 files committed
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - S ignores deployment reference values; R contains no B/Q/P/M/D reference (EXP-UQ03).
disproven_routes:
  - Using canonical whole-document hashing for qualification identity.
open_risks:
  - PENDING INDEPENDENT REVIEW (Astra/High, not available in this session): L algorithm and the
    inventory exclusion/inclusion table (plan Task 3) must be reviewed before Stage B freeze.
next_command: implement Task 4 RED (synthetic 20% arithmetic table and typed contexts)

## EXP-UQ04 — Task 4 closed allocation contexts and exact-N budget authority

```yaml
experiment_id: EXP-UQ04
status: VALID
prior_experiment: EXP-UQ03
hypothesis: One provider can own the 20% arithmetic, the closed context types and the qualification
  check, so no consumer can forge authority or recompute a formula.
prediction: RED fails because the module is absent; GREEN passes the synthetic 20% table plus context,
  admission, authority-chain, staleness and qualification-shape tests.
single_variable: resource_budget module
lifecycle: ISOLATED_STACK
preconditions:
  - Identity layer committed; synthetic profiles/authorities only (no host measurement).
success_criteria:
  - headroom_ok matches the design fixtures and rejects nonfinite/negative input.
  - Direct context construction fails with ALLOCATION_CONTEXT_MISMATCH; measurement/adaptive contexts
    cannot be admitted on the production path; a candidate/null profile chain raises BUDGET_PROFILE_UNAVAILABLE.
  - Production admission enforces profile hash, runtime identity, APPROVED exact-N entry, qualification
    record and live envelope (headroom, attribution, swap/PSI, throttling, observation freshness).
  - Missing/UNKNOWN exact-N entries and N8-for-N4 substitution are refused at issuance.
failure_criteria:
  - Any forgeable context, consumer-specific formula, or admission without a qualification record.
invalid_criteria:
  - Test-helper defects counted as implementation behaviour (two such defects were fixed, not weakened).
provenance:
  source_commit: 40d4fd62c (Task 3 checkpoint; this task's parent commit)
  install_overlay: $TASK_ROOT/dev-build + dev-install (symlink-install dev overlay)
  runtime_executable: the exact shared TEST_PYTHON above
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest budget-red src/so101_demo_py/test/test_parallel_resource_budget.py -q
    exit_code: 1
  - command: so101_pytest budget-green src/so101_demo_py/test/test_parallel_resource_budget.py src/so101_demo_py/test/test_parallel_resource_identity.py -q
    exit_code: 0
observed:
  - RED scratch/budget-red.*: 26 failed, ModuleNotFoundError for resource_budget (intended).
  - GREEN scratch/budget-green.*: 34 passed, 0 failed. Fixed during GREEN without weakening assertions:
    scope identity now uses the real current fingerprint, the synthetic deployment receipt binds the real
    promotion file hash, and admit_production reads the identity from the context scope.
  - The provider stores no self-digest inside the profile document; the loaded profile hash comes from the
    external secure read and is bound into the issued context authority.
inferred:
  - Reason codes cover BUDGET_PROFILE_UNAVAILABLE, EXACT_N_UNQUALIFIED, RUNTIME_FINGERPRINT_MISMATCH,
    BACKGROUND_ENVELOPE_EXCEEDED, RESOURCE_PROBE_FAILED, *_HEADROOM, SWAP_PRESSURE and
    QUALIFICATION_EVIDENCE_INVALID as designed.
conclusion: VALID. The shared production gate exists offline; no consumer is migrated yet.
evidence:
  - scratch/budget-red.*, scratch/budget-green.*
decision: KEEP
next_experiment: EXP-UQ05
```

```yaml
checkpoint_id: CP-UQ04
last_valid_experiment: EXP-UQ04
current_hypothesis: A Web-less measurement owner can latch abort from sampler/owner health without any
  production lease or Web control server.
working_tree_status: Task 4 files committed
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - Explicit contexts + exact-N provider implemented; production admission refuses non-approved N (EXP-UQ04).
disproven_routes:
  - Using a generic purpose string or false resource flag to enter the fixed path.
open_risks:
  - PENDING INDEPENDENT REVIEW (Astra/High, unavailable in-session): closed context constructors, digest
    graph and reason-code set before Stage B freeze (plan Task 4).
next_command: implement Task 5 RED (sampler gap latches abort without Web)

## EXP-UQ05 — Task 5 Web-less measurement owner, cancellation and watchdog

```yaml
experiment_id: EXP-UQ05
status: VALID
prior_experiment: EXP-UQ04
hypothesis: An owned measurement binding can latch a permanent abort and send exactly one authenticated
  cancellation without any production Web server or lease, and never claim cleanup it did not prove.
prediction: RED fails at the missing module; GREEN proves gap/death/breach/sequence latching, single send,
  no replacement, foreign-identity refusal and event-time recording.
single_variable: measurement_control module plus unified composition stop predicate
lifecycle: ISOLATED_STACK
preconditions:
  - Task 4 committed; no ROS, no service, fake clock and recorder sender only.
success_criteria:
  - The plan's gap fixture latches, sends once, blocks permit_side_effect and never clears.
  - Unreachable owner with an unverifiable scope raises FOREIGN_IDENTITY and produces no receipt;
    a fresh owned scope records t_owned_groups_gone only through the containment callable.
  - detect-to-send overrun is recorded as INVALID; ACK is not cleanup.
failure_criteria:
  - Any second cancel, any latch clearing, or a cleanup receipt without proof.
invalid_criteria:
  - Counting the deep-scratch socket-path rejection as a product failure (the fixture now uses the short
    private socket directory the design requires).
provenance:
  source_commit: 64d6cb72c (Task 4 checkpoint; this task's parent commit)
  install_overlay: $TASK_ROOT/dev-build + dev-install (symlink-install dev overlay)
  runtime_executable: the exact shared TEST_PYTHON above
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest control-red src/so101_demo_py/test/test_parallel_measurement_control.py -q
    exit_code: 2
  - command: so101_pytest control-green src/so101_demo_py/test/test_parallel_measurement_control.py src/so101_demo_py/test/test_parallel_batch_web_control.py src/so101_demo_py/test/test_parallel_processes.py -q
    exit_code: 0
  - command: so101_pytest control-cli-regression src/so101_demo_py/test/test_parallel_batch_cli.py -q
    exit_code: 1
observed:
  - RED: collection error with ModuleNotFoundError for measurement_control (module absent by design).
  - GREEN scratch/control-green.*: 54 passed, 0 failed (10 new control tests + retained web_control and
    parallel_processes suites).
  - CLI regression comparison against baseline-demo-rest junit: 22 failures in test_parallel_batch_cli.py,
    exactly the same 22 pre-existing socket-path failures; regressions = [] (script comparison by test ID).
  - Fixture note: pytest tmp_path lives under the deep mandated scratch (108-char TASK_ROOT), so the
    control socket is created in a short private directory (tempfile.mkdtemp under /tmp, removed after the
    run). This mirrors design 6.1, which requires the real control socket to use a short path verified
    against the 107-byte budget; the binding validator still enforces and tests that budget.
  - Composition wiring: ProductionBatchComposition._stop_requested() consults an owned measurement control
    first and injects it unconditionally into wait_for_children; FixedCoordinatorControlServer now accepts
    legal v2 fixed requests (FIRST_PASS/FULL_RESTART_RETRY) and refuses adaptive pool requests.
inferred:
  - Broker start/warmup, spawn, reload, recovery and finalization boundaries share this predicate through
    the existing composition stop checks; the physical stop latency is NOT measured here.
conclusion: VALID at unit level. Actual stop latency and live containment remain unmeasured.
evidence:
  - scratch/control-red.*, scratch/control-green.*, scratch/control-cli-regression.*
decision: KEEP
next_experiment: EXP-UQ06
```

```yaml
checkpoint_id: CP-UQ05
last_valid_experiment: EXP-UQ05
current_hypothesis: The sampler/clock estimator and the authorized candidate CLI can be implemented with
  pure interval fixtures and sealed B output only.
working_tree_status: Task 5 files committed
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - Abort latch, single authenticated cancel and containment rules implemented (EXP-UQ05).
disproven_routes:
  - Treating a control ACK as cleanup, or a Web lease as a prerequisite for candidate abort authority.
open_risks:
  - Real host stop latency and owned-group containment are unmeasured and require the Stage C window.
next_command: implement Task 6 RED (quantized 1x window and two non-overlapping deficits)

## EXP-UQ06 — Task 6 sampler, clock estimator and candidate CLI

```yaml
experiment_id: EXP-UQ06
status: VALID
prior_experiment: EXP-UQ05
hypothesis: A closed measurement authorization plus an interval-based clock estimator can qualify or
  refuse a candidate batch, and sealing can produce a candidate-only B document.
prediction: RED fails with the module absent; GREEN passes the quantized-1x, two-deficit, overlap,
  stale-window, authorization and sealing tests plus the CLI refusal tests.
single_variable: resource_measurement module, candidate CLI and its console script
lifecycle: ISOLATED_STACK
preconditions:
  - Task 5 committed; synthetic raw files; no ROS, no service start.
success_criteria:
  - rtf_interval keeps a quantized 1x window healthy and exposes a real deficit's upper bound.
  - Two complete non-overlapping deficit windows fail; an overlapping window never double counts.
  - Stale/ineligible windows and out-of-range authorization fields are refused.
  - Sealing writes canonical candidate-only bytes with no P/M/D reference; the CLI refuses wrong hash,
    intent mismatch, expiry, non-null deployment refs, out-of-evidence-root batch roots and missing
    host measurement capability.
failure_criteria:
  - Any epsilon back-fill from failed samples, any profile reference in B, or a CLI that starts work
    without capability.
invalid_criteria:
  - Treating the fail-closed runtime refusal as a measurement failure.
provenance:
  source_commit: d7caaaf4f (Task 5 checkpoint; this task's parent commit)
  install_overlay: $TASK_ROOT/dev-build + dev-install (symlink-install dev overlay)
  runtime_executable: the exact shared TEST_PYTHON above
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest measurement-red src/so101_demo_py/test/test_parallel_resource_measurement.py -q
    exit_code: 1
  - command: so101_pytest measurement-green src/so101_demo_py/test/test_parallel_resource_measurement.py src/so101_demo_py/test/test_parallel_measurement_cli.py -q
    exit_code: 0
observed:
  - RED: collection error with ModuleNotFoundError for resource_measurement.
  - GREEN scratch/measurement-green.*: 11 passed, 0 failed (6 measurement + 5 CLI tests).
  - Fixed during GREEN without weakening assertions: QUALIFICATION intent without a calibration hash now
    raises CALIBRATION_EVIDENCE_REQUIRED before the generic sha check, and the CLI reports refused codes
    for OSError as well as ContractError.
  - Real host facts are read only through /proc (meminfo, vmstat, pressure); NVML and delegated cgroup v2
    are required capabilities and their absence aborts with MEASUREMENT_CAPABILITY_MISSING.
  - KNOWN LIMIT (honest): the candidate CLI validates authority/config/capabilities, binds the owned
    measurement context and then refuses with MEASUREMENT_RUNTIME_UNAVAILABLE because the composition
    runner hook that would spawn the owned workload is not yet wired. No measurement can start from this
    CLI until that hook exists in Stage B/C. The CLI never reads an approved profile.
inferred:
  - Clock epsilon values remain NOT_MEASURED; the estimator only proves the arithmetic and the
    non-overlap discipline.
conclusion: VALID at offline level with an explicitly recorded runtime-wiring gap.
evidence:
  - scratch/measurement-red.*, scratch/measurement-green.*
decision: KEEP
next_experiment: EXP-UQ07
```

```yaml
checkpoint_id: CP-UQ06
last_valid_experiment: EXP-UQ06
current_hypothesis: The coordinator can drop the lifetime quota and converge on NO_RECOVERABLE_WORKERS.
working_tree_status: Task 6 files committed
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - Authorization/estimator/sealing implemented; candidate runtime hook still missing (EXP-UQ06).
disproven_routes:
  - Letting a failed sample enlarge epsilon, or letting B reference a profile.
open_risks:
  - Candidate CLI cannot yet start the owned workload; Stage C cannot begin until that hook is built and
    an authorized measurement window exists.
next_command: implement Task 7 RED (one worker consumes twenty without a lifetime quota)

## EXP-UQ07 — Task 7 no-quota shared queue and finite recovery convergence

```yaml
experiment_id: EXP-UQ07
status: VALID
prior_experiment: EXP-UQ06
hypothesis: Removing the lifetime debit lets one worker consume the whole shared queue while all
  existing lease/ACK/generation/epoch/cleanup boundaries stay intact, and a stuck batch now stops as
  NO_RECOVERABLE_WORKERS instead of a quota exhaustion.
prediction: RED shows the quota blocking the 20th point or the fixture unable to use the v2 contract;
  GREEN passes the coordinator and fault-injection suites with the new terminal reason.
single_variable: coordinator quota removal plus v2 request fixture migration
lifecycle: ISOLATED_STACK
preconditions:
  - Task 6 committed; fake clock/results; no ROS or service start.
success_criteria:
  - One worker with 19 legitimate same-slot recoveries consumes 20 points, lease_count 20,
    generations 1..20, final state RECOVERING, terminal POINTS_COMPLETE.
  - Duplicate request keys, concurrency, ACK/phase timeouts, fences and cleanup semantics unchanged.
failure_criteria:
  - Removing quota by weakening a lease/recovery/cleanup guard or by re-labelling a fixture failure.
invalid_criteria:
  - Counting the FROZEN_CONFIG_REQUIRED constructor guard as a product RED (it was migrated, not hidden).
provenance:
  source_commit: da37bd96b (Task 6 checkpoint; this task's parent commit)
  install_overlay: $TASK_ROOT/dev-build + dev-install (symlink-install dev overlay)
  runtime_executable: the exact shared TEST_PYTHON above
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest queue-red src/so101_demo_py/test/test_parallel_batch_coordinator.py::test_one_worker_consumes_twenty_without_lifetime_quota -q
    exit_code: 1
  - command: so101_pytest queue-green src/so101_demo_py/test/test_parallel_batch_coordinator.py src/so101_demo_py/test/test_parallel_batch_fault_injection.py -q
    exit_code: 0
observed:
  - RED: 1 failed with the coordinator's FROZEN_CONFIG_REQUIRED guard rejecting the v2 config; the guard
    was extended to accept ParallelRuntimeConfigV2 (a real gate change, not a test workaround).
  - GREEN scratch/queue-green.*: 146 passed, 0 failed, including the plan's 20-point no-quota regression.
  - Coordinator changes: grant_lease no longer compares lease_count with any quota; _evaluate treats a
    still-registerable or AVAILABLE/RECOVERING/INITIALIZING slot as recoverable and otherwise terminates
    as NO_RECOVERABLE_WORKERS. Historical CAPACITY_EXHAUSTED remains readable in old journals.
  - Two retained tests asserted the old quota-exhaustion reason for the "all slots terminated, points
    pending" scenario; they now assert NO_RECOVERABLE_WORKERS (same scenario, design-renamed reason).
  - The obsolete v1 hard-K selector test was replaced by an equivalent no-quota assertion that a released
    worker wins the next point and lease_count reaches 2; the fixture's adaptive branch keeps its
    retained K parameter until Task 8 migrates the adaptive contract.
inferred:
  - The coordinator accepts both the frozen v1 config and the v2 config; new production runs must still
    pass require_v2_execution at the composition boundary (Task 10).
conclusion: VALID at unit level.
evidence:
  - scratch/queue-red.*, scratch/queue-green.*
decision: KEEP
next_experiment: EXP-UQ08
```

```yaml
checkpoint_id: CP-UQ07
last_valid_experiment: EXP-UQ07
current_hypothesis: Remaining Stage A tasks (8-11, 13-15 offline) can proceed the same way.
working_tree_status: Task 7 files committed
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - New execution paths no longer contain a lifetime point quota; v1 stays readable (EXP-UQ07).
disproven_routes:
  - Preserving CAPACITY_EXHAUSTED as a v2 terminal reason.
open_risks:
  - Consumers (CLI/Web/allocator) still reference max_points_per_worker and the N>3 hardcode until
    Tasks 9-11; those paths remain un-migrated and must not be used for new production runs.
next_command: implement Task 8 RED (test_pool_contract_has_no_lifetime_quota)

## CP-UQ07b — Stage A partial handoff (inline DST execution stop point)

```yaml
checkpoint_id: CP-UQ07b
last_valid_experiment: EXP-UQ07
current_hypothesis: Tasks 8-11 and the Task 13/14/15 offline parts continue from commit 2b008e00b.
working_tree_status: clean at the Task 7 ledger commit (no tracked or untracked changes)
owned_processes: NONE (no ROS/Web/measurement process was started in this session)
preserved_processes: NONE from this task family; canonical install, shared venv, other worktrees and
  Codex/dst sessions untouched
confirmed_conclusions:
  - Frozen design/plan hashes verified; base tree clean (EXP-UQ00).
  - Recovery entry integrated offline and preview-by-default (EXP-UQ01); NOT deployed.
  - v2 contract + read-only v1 history; v1 YAML hash aadcac01d... unchanged (EXP-UQ02).
  - Acyclic L/S/E/I/R + byte audits (EXP-UQ03); closed contexts and exact-N authority (EXP-UQ04);
    Web-less measurement abort/containment (EXP-UQ05); authorization/estimator/sealing + fail-closed
    candidate CLI (EXP-UQ06); shared queue without a lifetime quota (EXP-UQ07).
disproven_routes:
  - Reusing v1 whole-document hashing for v2 identity; keeping CAPACITY_EXHAUSTED as a v2 terminal reason;
    treating a control ACK as cleanup; letting a candidate config carry deployment references.
open_risks:
  - PENDING INDEPENDENT REVIEWS (all require GPT-6 Astra / High, unavailable in this session):
    Task 3 L/inventory exclusion table; Task 4 closed contexts/digest graph; Task 11 API/type boundary;
    Task 16 guide. Plan Task 1/2 code review is also outstanding.
  - PENDING AUTHORIZATION GATES (see the approvals table above): candidate measurement window (Stage C),
    owned service refresh/recovery/deployment window (Stage B/D), operator profile promotion (Stage D),
    exclusive owned Chrome window (Stage E). No promotion record was written and no service was started.
  - Stage A remaining work: Task 8 (ADAPTIVE no-K + typed context), Task 9 (teleop v2 API/preflight/
    store + manual N1 retry), Task 10 (three consumers on one provider, spawn re-check, CLI legacy flag),
    Task 11 (OpenAPI + Web no-K UI + contract/installed tests), Task 13 aggregation, Task 14 promotion
    parser, Task 15 offline live-evidence verifier.
  - Candidate runtime gap (EXP-UQ06): the candidate CLI validates and binds authority but refuses with
    MEASUREMENT_RUNTIME_UNAVAILABLE because the composition runner hook is not wired.
  - Environment blockers proven pre-existing and NOT caused by this work: (a) test_grounding_dino_domain_retention
    needs torch, absent from the exact shared venv (no dependency install authorized); (b) socket-based
    demo tests fail with UNIX_SOCKET_PATH_TOO_LONG because the mandated TASK_ROOT is 108 characters
    (baseline 71 failures, byte-identical failure sets after every task; Task 5 fixtures use the short
    socket directory the design requires).
  - Consumers still carry K/N>3: production.py:305, cli/mujoco_parallel_batch.py:416,
    parallel_batch/resources.py:1295 plus 41 max_points_per_worker references.
retained:
  - Registered root /data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main with the
    new task directory unbounded-queue-resource-budget/: tools/test-gate.zsh, tools/task-env.zsh,
    bindings/v1-contract-baseline.json, run-index.txt, dev-build/, dev-install/, scratch/*, colcon/*.
  - dispatch-20260918-84620fc0/executor-receipt.md (executor-authored, distinct from transport receipt).
  - All commits: 8709912d9, cdf333a98, e81634585, ebff2f44e, 573120b28, 40d4fd62c, 64d6cb72c, d7caaaf4f,
    da37bd96b, eb751c112, 2b008e00b on branch codex/so101-unbounded-queue-resource-budget (no push, no merge).
archived: none
deletion_candidates:
  - $TASK_ROOT/scratch/* (all test scratches, including the pre-existing baseline runs) after readback;
    no deletion authorized or performed.
  - $TASK_ROOT/colcon/*colcon-log and stale dev-build objects if a clean reconfigure supersedes them;
    currently retained because Task 12 requires a logged reconfigure rather than reuse.
next_command: implement Task 8 RED at src/so101_demo_py/test/test_parallel_adaptive_contracts.py::test_pool_contract_has_no_lifetime_quota
```

## Approval and review requests to the operator (not self-approved)

| # | Request | Why it is needed | Where it blocks |
| --- | --- | --- | --- |
| A1 | Candidate measurement window for one exact N, with the sealed MeasurementAuthorization | design 188-194, plan Task 13 Stage C | Stage C cannot start; the CLI would refuse and no measurement may begin |
| A2 | Owned service refresh / exclusive offline recovery + deployment window | design 507-513, plan Task 12 | Stage B's owned recovery/Web refresh; no signal may be sent before it |
| A3 | Operator exact-N / profile-hash promotion approval after Sol/Astra review | design 490-494, plan Task 14 | Stage D; no APPROVED M or carrier refs may be written |
| A4 | Exclusive owned live Chrome acceptance window | design 554-556, plan Task 15 | Stage E |
| A5 | Independent GPT-6 Astra/High reviews (Tasks 1-4 code, L/inventory table, closed contexts, Task 11 API, Task 16 guide) and Sol/High execution-result review | plan lines 15-17, 126, 316, 344, 575 | Stage B entry gate "all Stage A code reviewed"; not satisfiable by the inline executor |
| A6 | Decision on the deep-scratch socket-path blocker (shorten the scratch root, or accept documented pre-existing demo failures) | AGENTS fsync/scratch rule vs AF_UNIX 107-byte limit | Task 12 full-demo gate |
| A7 | Approval to wire the candidate measurement runner hook (composition spawn path) | plan Task 6/13 | Stage C runtime start |


## Correction — 2026-09-18, continuation dispatch 2e37ac85

- The EXP-UQ03 statement that failure sets were "byte-identical" to the baseline was an overclaim: the
  comparison was by test ID only, and the traces/scratch paths differ. Correct wording: ZERO new failure
  IDs at that time, with 33 of 35 traces carrying UNIX_SOCKET_PATH_TOO_LONG. The independent XML check
  (scratch/identity-green.F9ndT0QL: 117 passed / 35 failed) is retained as the accurate record.
- Header fields base_commit/current_commit/latest_checkpoint were stale (still reporting CP-UQ00); they now
  point at the live continuation state. Historical EXP/CP bodies are unchanged.
- TDD evidence honesty retained as written: Task 7's RED was FROZEN_CONFIG_REQUIRED (constructor/version
  gate), not direct quota exhaustion; Tasks 2–6 REDs were missing module/function/collection failures at
  the intended new boundary. No bootstrap failure was relabelled as product-behaviour proof.

## EXP-UQ08 — AF_UNIX boundary repair (dirfd transport vs canonical path length)

```yaml
experiment_id: EXP-UQ08
status: VALID
prior_experiment: EXP-UQ07
hypothesis: The 35 Task 3 failures are caused by resources.py rejecting the canonical absolute socket
  path length even though runtime/parallel_ipc.py already binds/connects through /proc/self/fd/<fd>/<name>;
  unifying preflight with that transport fixes them without shortening TMPDIR or weakening the kernel limit.
prediction: RED transport tests fail while the transport helper is absent; after the shared helper and
  preflight rewiring, both Task 3 files reach clean GREEN with the true oversized-basename boundary intact.
single_variable: shared dirfd transport capability + preflight/adaptive/ipc fixture alignment
lifecycle: ISOLATED_STACK
preconditions:
  - Continuation dispatch 2e37ac85 read completely; receipt and probe-01 written first.
  - Worktree clean at ccdb01191; no service, no measurement, no deletion.
success_criteria:
  - Long durable absolute root (>107 bytes) really binds and connects through the descriptor transport.
  - Exact encoded sockaddr length including the terminating NUL is bounded by 108; overlong basename and
    invalid basename fail closed; /proc capability absence fails closed; symlinked parent stays rejected.
  - Canonical absolute paths remain the audited identity; no manifest/journal/environment change.
  - Both Task 3 files (152 tests) pass with no exclusions, and the two non-socket failures are fixed.
failure_criteria:
  - Deleting the guard, raising an arbitrary constant, chdir, symlink alias, abstract sockets, or
    external short paths; any weakened assertion.
invalid_criteria:
  - Counting a hung/killed test invocation as evidence.
provenance:
  source_commit: ccdb0119140ee3095144b948f57d8dd592502db8
  install_overlay: $TASK_ROOT/dev-build + dev-install (symlink-install dev overlay)
  runtime_executable: the exact shared TEST_PYTHON above
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest transport-red src/so101_demo_py/test/test_parallel_unix_transport.py -q
    exit_code: 1
  - command: so101_pytest transport-only src/so101_demo_py/test/test_parallel_unix_transport.py -q
    exit_code: 0
  - command: so101_pytest socket-fix-green src/so101_demo_py/test/test_parallel_ipc.py src/so101_demo_py/test/test_parallel_resource_identity.py src/so101_demo_py/test/test_parallel_batch_resources.py src/so101_demo_py/test/test_parallel_unix_transport.py -q
    exit_code: 0
observed:
  - RED: transport helper import missing (IpcError/UNIX_SOCKADDR_CAPACITY_BYTES/_PROC_FD_ROOT absent).
  - Two of my own new transport tests were defective and were fixed, not worked around: wrong exact-size
    arithmetic for fd 0, and a blocking echo (client sent but the server read its own socket) that caused
    a 600 s harness timeout. The killed invocation left no stray process (verified by ps).
  - GREEN scratch/socket-fix-green.tkmbf4Z0: 199 passed / 0 failed. Per file: resources 144,
    ipc 42, identity 8, transport 5. The two Task 3 files total exactly 152 tests, all passing, with no
    --ignore/-k filters.
  - test_concurrent_batches_cannot_claim_the_same_ros_domains -> pass (intended one-admitted/one-rejected
    ROS_DOMAIN_CLAIMED semantics preserved); test_dry_run_cli_writes_private_manifest_without_starting_processes
    -> pass (manifest now written, exit 0); test_socket_path_must_fit_linux_unix_domain_limit -> pass with
    an overlong basename as the true kernel boundary.
  - Implementation: runtime/parallel_ipc.py now owns UNIX_SOCKADDR_CAPACITY_BYTES=108,
    require_proc_fd_transport, require_transport_basename (preflight, no parent access, conservative fd
    digit reservation) and transport_address (exact address + terminating NUL check); server bind and
    client connect both use it. resources.py and adaptive_pool.py preflight now call the shared helper and
    map failures to their existing error strings; the retained constant names stay for compatibility.
  - test_parallel_ipc.py's raw listener fixture now binds via the descriptor transport, so no endpoint is
    created at a long kernel address.
inferred:
  - The remaining baseline failures are NOT socket-related and are addressed under Priority 2.
conclusion: VALID. Priority 1 complete; the 35 Task 3 failures are genuinely resolved (not accepted).
evidence:
  - scratch/transport-red.*, scratch/transport-only.UUmaIlWG (defective-test failure), scratch/socket-fix-green.tkmbf4Z0
decision: KEEP
next_experiment: EXP-UQ09
```

```yaml
checkpoint_id: CP-UQ08
last_valid_experiment: EXP-UQ08
current_hypothesis: Priority 2 environment repairs (torch/mujoco/task-owned isolated env, pinned
  submodule init, support overlay mapping) remove the remaining baseline nonpasses.
working_tree_status: Priority 1 files staged for this commit
owned_processes: NONE
preserved_processes: NONE from this task family (CP-Z01/CP-Z02 state intact; canonical dirty=2 untracked docs only)
confirmed_conclusions:
  - AF_UNIX boundary unified on the descriptor transport; 152/152 Task 3 tests pass (EXP-UQ08).
disproven_routes:
  - Rejecting long canonical socket ancestors; shortening TMPDIR/evidence layout to satisfy the kernel.
open_risks:
  - Remaining baseline nonpasses: ~45 missing-mujoco cases, torch (3), support-prefix assertion, pinned
    submodule uninitialized; a task-owned isolated interpreter may be required and adds provenance work.
next_command: classify remaining baseline nonpasses, initialize the pinned submodule in this worktree,
  then build the task-owned isolated environment per so101-dev python-dependency-install reference

## EXP-UQ09 — Priority 2 environment classification (partial; repair not yet implemented)

```yaml
experiment_id: EXP-UQ09
status: VALID
prior_experiment: EXP-UQ08
hypothesis: After the transport repair, every remaining baseline nonpass is an environment/bootstrap
  issue (mujoco, torch, pinned submodule, support overlay mapping), not a product regression.
prediction: The non-torch remainder reports only ModuleNotFoundError for mujoco plus the support-prefix
  assertion, with no new product-level failures.
single_variable: pinned submodule initialization (authorized)
lifecycle: ISOLATED_STACK
preconditions:
  - Priority 1 committed; no service/measurement started; original baseline JUnit kept immutable.
success_criteria:
  - Classify every remaining baseline nonpass by actual trace, not by the grouped summary.
failure_criteria:
  - Treating a bootstrap failure as product behaviour, or excluding modules to fake a clean gate.
invalid_criteria:
  - Counting a collection-interrupted invocation (torch) as a full classification.
provenance:
  source_commit: d188b248e
  install_overlay: $TASK_ROOT/dev-build + dev-install (symlink-install dev overlay)
  runtime_executable: the exact shared TEST_PYTHON above
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: git submodule update --init third_party/mujoco_ros2_control
    exit_code: 0
  - command: so101_pytest p2-classify <7 previously failing modules incl. grounding_dino> -q
    exit_code: 2
  - command: so101_pytest p2-classify2 <6 modules without grounding_dino> -q
    exit_code: 1
observed:
  - Submodule third_party/mujoco_ros2_control initialized at the pinned e4c0241aee52a40727681bd5872c09bf814e941a
    (was "-e4c0241a"); worktree tracked state remains clean.
  - p2-classify was interrupted at collection by ModuleNotFoundError: torch
    (test_grounding_dino_domain_retention.py), so it cannot classify the rest by itself.
  - p2-classify2 scratch/p2-classify2.*: 9 failed, 43 passed, 2 skipped, 40 errors. Trace classes:
    45 x ModuleNotFoundError: No module named 'mujoco' (40 setup errors + 5 failures),
    1 x ModuleNotFoundError: No module named 'torch' (test_sam_decoder_runtime.py),
    1 x support-prefix AssertionError on '/data/work/ws_moveit/i...' (installed provenance expects the
    task candidate overlay), plus 1 further AssertionError.
  - The 33 socket-length failures and the two Task 3 derived failures are gone (EXP-UQ08).
inferred:
  - Remaining repair = task-owned isolated interpreter with mujoco/torch/pydantic2/pytest, plus the
    installed-support overlay mapping fix. Neither was attempted in this context window.
conclusion: VALID classification only; repair is the next work unit.
evidence:
  - scratch/p2-classify.*, scratch/p2-classify2.*, probe-01.md
decision: PENDING
next_experiment: EXP-UQ10
```

```yaml
checkpoint_id: CP-UQ09
last_valid_experiment: EXP-UQ09
current_hypothesis: A task-owned isolated venv (TUNA index, per-command NO_PROXY append, artifacts inside
  TASK_ROOT) plus the support-overlay mapping fix removes the remaining baseline nonpasses.
working_tree_status: clean after this ledger commit; Priority 1 committed at 7affd31f4
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - AF_UNIX boundary repaired; 152/152 Task 3 tests pass; source clean (EXP-UQ08).
  - Remaining nonpasses are exclusively mujoco(45)/torch(2 modules)/support-prefix(1-2) (EXP-UQ09).
disproven_routes:
  - Treating the remaining 45 mujoco and torch failures as product regressions.
open_risks:
  - Building the isolated env is the next unit; provenance must register the new exact interpreter and
    dependency closure in tools/task-env.zsh, tools/test-gate.zsh and this ledger.
retained:
  - Priority 1 commit 7affd31f4 + docs d188b248e; submodule initialized in this worktree (no source bytes changed).
  - All earlier scratches, baselines and JUnit unchanged; nothing archived or deleted.
deletion_candidates: unchanged from CP-UQ07b (scratch trees only, no deletion authorized)
next_command: >
  source $TASK_ROOT/tools/task-env.zsh && read .agents/skills/so101-dev/references/python-dependency-install.md,
  then create $TASK_ROOT/venv (python3.12 -m venv), install pinned pydantic2/pytest/mujoco/torch with the
  TUNA index via per-command NO_PROXY/no_proxy append and PIP_CACHE_DIR/PIP_BUILD_DIR/TMPDIR inside
  $TASK_ROOT, verify import origins and ABI, register TEST_PYTHON/TEST_SITE in task-env.zsh and
  test-gate.zsh, prove tempfile.gettempdir() for every interpreter, then re-run the full demo gate
  (no --ignore) and fix the installed-support overlay mapping.

## EXP-UQ10 — task-owned isolated environment and clean baseline (Priority 2 complete)

```yaml
experiment_id: EXP-UQ10
status: VALID
prior_experiment: EXP-UQ09
hypothesis: A task-owned isolated interpreter with the pinned dependency closure plus a truthful support
  overlay build removes every remaining baseline nonpass without touching shared environments.
prediction: After registering the new interpreter and rebuilding the dev overlay with so101_mujoco_support,
  the full demo and teleop suites collect and pass with zero failures/errors.
single_variable: task-owned venv + interpreter registration + support package in the dev overlay
lifecycle: ISOLATED_STACK
preconditions:
  - Priority 1 committed; no service/measurement started; shared Kimi venv untouched (read-only reference).
success_criteria:
  - Exact new interpreter and dependency origins verified; no shared/global environment modified.
  - Support package prefix comes from the task candidate overlay; product modules stay from this worktree.
  - Full demo + teleop suites: zero failures/errors, no --ignore/xfail/exclusions.
failure_criteria:
  - Faking a prefix, broad PYTHONPATH injection, or accepting baseline failures as passing.
invalid_criteria:
  - Build failures caused by my own toolchain shadowing counted as product regressions.
provenance:
  source_commit: 93bffbe6dab8ff17afb1ee37599811abecea39f5
  install_overlay: $TASK_ROOT/dev-install (symlink-install, 3 packages); venv $TASK_ROOT/venv
  runtime_executable: $TASK_ROOT/venv/bin/python (Python 3.12.3, --system-site-packages)
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: $TASK_ROOT/tools/build-task-venv.zsh (uv venv + uv pip install pydantic==2.13.4 pytest==7.4.4 torch==2.13.0 mujoco==3.12.0)
    exit_code: 0
  - command: uv pip install --python $TASK_ROOT/venv/bin/python setuptools==68.1.2 (TUNA index)
    exit_code: 0
  - command: so101_colcon dev-build-3c build --packages-select so101_demo_py so101_teleop so101_mujoco_support --allow-overriding ... --symlink-install
    exit_code: 0
  - command: so101_pytest env-baseline-demo src/so101_demo_py/test -q
    exit_code: 0
  - command: so101_pytest env-baseline-teleop src/so101_teleop/test -q
    exit_code: 0
observed:
  - venv-build/20260918T032409Z: elapsed 349 s, exit 0. $TEST_ROOT/venv/bin/python = 3.12.3;
    pydantic 2.13.4 (venv site-packages), pytest 7.4.4, torch 2.13.0+cu130, mujoco 3.12.0 — all imported
    from the task venv, not from shared/global paths. venv 4.7G; task-owned uv cache used.
  - First build attempt failed with `setup.py develop --uninstall` "option --uninstall not recognized":
    the venv's setuptools 84.0.0 shadowed system setuptools 68.1.2 on colcon's PYTHONPATH (setuptools >= 80
    removed the develop command). Pinned setuptools==68.1.2 into the task venv; recorded in
    venv-build/setuptools-pin-*/. NOTE FOR TASK 12: the planned --cmake-clean-cache reconfigure must run
    with this pinned setuptools on the path.
  - Wrapper repair: COLCON_TEST_PYTHONS was declared with `typeset -a` inside a sourced file; because
    task-env sources test-gate from inside a function, the array became function-local and empty, so
    `so101_colcon test` would have refused (or executed an empty interpreter). Changed to `typeset -ga`
    (global) plus a global declaration in task-env.zsh; verified array contents.
  - Dev overlay rebuilt with three packages (so101_demo_py, so101_teleop, so101_mujoco_support) and
    verified origins: so101_demo from dev-build (this worktree), so101_teleop from dev-install,
    get_package_prefix('so101_mujoco_support') = $TASK_ROOT/dev-install/so101_mujoco_support.
  - CLEAN BASELINE: scratch/env-baseline-demo.02pCV9vv exit 0 — 3214 passed, 1 skipped, 0 failures,
    0 errors in 358 s (previously 71 failed / 40 errors). scratch/env-baseline-teleop.yfweBFIr exit 0 —
    511 passed, 0 failures in 40 s (was 489 before Tasks 1-7 added 22 tests).
  - Shared Kimi venv, system installs, other worktrees and drivers were not modified; the Kimi venv remains
    a read-only provenance reference. No dependency was installed outside TASK_ROOT.
inferred:
  - All previously "environmental" failures were bootstrap issues as classified; no product regression was
    hidden by them, and the 22 new teleop tests pass in the repaired environment.
conclusion: VALID. Priority 2 complete with a clean, exclusion-free baseline.
evidence:
  - $TASK_ROOT/venv-build/*, $TASK_ROOT/colcon/dev-build-3c.*, scratch/env-baseline-demo.02pCV9vv,
    scratch/env-baseline-teleop.yfweBFIr, run-index.txt
decision: KEEP
next_experiment: EXP-UQ11 (Task 8 adaptive no-K)
```

```yaml
checkpoint_id: CP-UQ10
last_valid_experiment: EXP-UQ10
current_hypothesis: Task 8 can remove the adaptive lifetime quota and introduce the typed adaptive context.
working_tree_status: wrapper + ledger changes staged for this commit
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - Task-owned venv registered; clean demo (3214 passed) and teleop (511 passed) baselines (EXP-UQ10).
disproven_routes:
  - Assuming remaining baseline failures were product regressions; assuming the shared venv could not be
    replaced without touching it (a task-owned venv solved it).
open_risks:
  - Task 12's --cmake-clean-cache reconfigure depends on the setuptools<80 pin being on colcon's path.
next_command: implement Task 8 RED (test_pool_contract_has_no_lifetime_quota) in
  src/so101_demo_py/test/test_parallel_adaptive_contracts.py

## EXP-UQ11 — Task 8 adaptive no-K contract and typed allocation authority

```yaml
experiment_id: EXP-UQ11
status: VALID
prior_experiment: EXP-UQ10
hypothesis: The adaptive pool contract can drop the lifetime quota while keeping affinity, fallback
  tiers, readiness, cleanup and infra-attempt authority, and only the owning factory can mint the
  typed adaptive allocation context.
prediction: RED (missing parameter / missing issuer) then GREEN across the four adaptive suites with the
  retained affinity/fallback tests unchanged.
single_variable: adaptive PoolRequest/runner/pool quota removal + factory-issued typed context
lifecycle: ISOLATED_STACK
preconditions:
  - Task-owned clean baseline (EXP-UQ10); no service or measurement started.
success_criteria:
  - Pool request has no max_points_per_worker and the plan's RED passes.
  - Only the factory instance can issue AdaptiveAllocationContext; wrong token, wrong generation, altered
    frozen options and a fixed-path scope are refused.
failure_criteria:
  - Any generic bypass, fixed profile use in the adaptive path, or changed fallback/affinity behaviour.
invalid_criteria:
  - Retained tests failing only because their fixture still passed the removed argument being counted as
    product regressions (they were migrated, not weakened).
provenance:
  source_commit: af7e6ab44
  install_overlay: $TASK_ROOT/dev-install (three packages) + $TASK_ROOT/venv
  runtime_executable: $TASK_ROOT/venv/bin/python
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest adaptive-red test_parallel_adaptive_contracts.py::test_pool_contract_has_no_lifetime_quota ::test_adaptive_factory_issues_typed_context_only_for_its_own_pool -q
    exit_code: 1
  - command: so101_pytest adaptive-green <four adaptive suites> -q
    exit_code: 0
observed:
  - RED: TypeError for the removed argument and NameError for the missing issuer.
  - GREEN scratch/adaptive-green.*: 86 passed, 0 failed.
  - Changes: PoolRequest/factory lose max_points_per_worker; runner no longer passes max(1, len(selected));
    the pool identity check drops the quota comparison; the factory gains a per-instance secret,
    pool_token_for(generation) and issue_allocation_context(...) which re-derives the frozen options and
    scope, checks the token with hmac.compare_digest and issues through resource_budget's private
    adaptive issuer. Affinity/fallback/readiness/cleanup/infra-attempt behaviour untouched.
  - Retained callers in two adaptive test files that still passed the removed argument were migrated to
    the no-K contract; all four suites pass with no exclusions.
inferred:
  - The allocator/CLI still accept the generic enforce_resource_thresholds flag; that migration is Task 10
    as the plan assigns it, and no adaptive path can reach a fixed profile today.
conclusion: VALID.
evidence:
  - scratch/adaptive-red.*, scratch/adaptive-green.*
decision: KEEP
next_experiment: EXP-UQ12 (Task 9 teleop v2 API)
```

```yaml
checkpoint_id: CP-UQ11
last_valid_experiment: EXP-UQ11
current_hypothesis: The teleop v2 API/preflight/store layer can reject legacy quota keys and expose
  exact-N availability without changing retained history.
working_tree_status: Task 8 files committed
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - Adaptive contract is quota-free with factory-private typed authority (EXP-UQ11).
disproven_routes:
  - Any caller-minted adaptive context or generic resource bypass on the adaptive path.
open_risks:
  - resources.AllocationPolicy still has the generic enforce_resource_thresholds flag until Task 10.
next_command: implement Task 9 RED (test_new_request_rejects_legacy_key) in src/so101_teleop/test/teleop/test_expert_validation_api.py

## EXP-UQ12 — Task 9 (part 1) teleop v2 request contract and exact-N availability

```yaml
experiment_id: EXP-UQ12
status: VALID
prior_experiment: EXP-UQ11
hypothesis: The teleop HTTP contract can require contract_version 2, refuse the legacy quota key by
  presence before Pydantic parsing, and expose honest exact-N availability without changing retained
  history or the rest of the service.
prediction: RED shows the legacy key accepted and the availability field absent; GREEN passes the plan's
  API gate plus the full teleop suite.
single_variable: api request contract + capabilities availability + production v2 request shape
lifecycle: ISOLATED_STACK
preconditions:
  - Task 8 committed; clean teleop baseline 511 passed (EXP-UQ10).
success_criteria:
  - max_points_per_worker present in any start/preflight body (including null) -> 422
    LEGACY_MAX_POINTS_PER_WORKER_UNSUPPORTED; missing/non-2 contract_version -> 422
    LEGACY_CONTRACT_EXECUTION_FORBIDDEN.
  - Capabilities expose N2..8 availability with selectable=false and BUDGET_PROFILE_UNAVAILABLE until an
    approved profile exists, and no fixed_max_points_per_worker field.
failure_criteria:
  - Accepting a legacy key or claiming any N is selectable/qualified without evidence.
invalid_criteria:
  - Retained fixtures failing only because they still sent the removed key counted as regressions.
provenance:
  source_commit: 3b0a68a95
  install_overlay: $TASK_ROOT/dev-install (symlinks to this worktree) + $TASK_ROOT/venv
  runtime_executable: $TASK_ROOT/venv/bin/python
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest teleop-v2-red test_expert_validation_api.py::test_new_request_rejects_legacy_key test_expert_validation_v2_contract.py -q
    exit_code: 1
  - command: so101_pytest teleop-v2-green <7 plan-listed teleop suites> -q
    exit_code: 0
  - command: so101_pytest teleop-full-after-v2 src/so101_teleop/test -q
    exit_code: 0
observed:
  - RED: collection error for the missing WorkerCountAvailability plus failing legacy-key/version cases.
  - GREEN scratch/teleop-v2-green.*: 99 passed; scratch/teleop-full-after-v2.*: 521 passed / 0 failed.
  - api.py: CampaignConfiguration carries contract_version: Literal[2] and no quota field; a FastAPI
    dependency inspects the raw body first and returns the two stable codes; WorkerCountAvailability +
    default_worker_count_availability give every capability response the honest N2..8 list.
  - production.py: capabilities add worker_count_availability (NOT_MEASURED/BUDGET_PROFILE_UNAVAILABLE,
    no profile/qualification hashes); new campaign requests set max_points_per_worker=None.
  - models.py: v2 fixed execution_config requires only worker_count; retained v1 rows still validate for
    read-only projection.
  - Retained fixtures migrated to the v2 body shape: two api tests dropped the quota key, added
    contract_version, and the preflight-mismatch case now mismatches on exact N (same intent).
inferred:
  - Preflight still derives an internal per-worker maximum via ceil(point_count/N) for the retained v1
    probe/argv path; with the user-supplied quota gone the derived value can never fail capacity, and the
    true removal of FixedExecutionConfig.max_points_per_worker belongs with the Task 10 provider wiring.
conclusion: VALID for the HTTP contract; remaining Task 9 work (preflight/store/supervisor quota removal,
  N1 retry v2 config) is interlocked with Task 10 and recorded there.
evidence:
  - scratch/teleop-v2-red.*, scratch/teleop-v2-green.*, scratch/teleop-full-after-v2.*
decision: KEEP
next_experiment: EXP-UQ13 (Task 10 consumers + provider wiring)
```

```yaml
checkpoint_id: CP-UQ12
last_valid_experiment: EXP-UQ12
current_hypothesis: One provider-backed gate can replace the three duplicated consumers and the N>3
  hardcode without weakening the retained safety boundaries.
working_tree_status: Task 9 part-1 files committed
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - v2 request contract + honest availability implemented; teleop suite 521 passed (EXP-UQ12).
disproven_routes:
  - Claiming any N selectable before a promoted profile exists.
open_risks:
  - production.py/cli/resources.py still compute the legacy formulas and the N>3 hardcode; Task 10 must
    replace them with the provider and keep every retained gate green.
next_command: implement Task 10 RED (legacy CLI flag error + three-consumer shared provider) and wire
  resources.AllocationPolicy to the typed contexts

## EXP-UQ13 — Task 10 (part 1) legacy CLI flag refusal and the shared admission gate

```yaml
experiment_id: EXP-UQ13
status: VALID
prior_experiment: EXP-UQ12
hypothesis: The CLI can refuse the retired quota flag before any resource work, and the Web probe, CLI
  prepare and worker allocator can share one exact-N admission gate that fails closed without a probe.
prediction: RED shows the flag accepted and the gate absent; GREEN passes the plan's CLI case plus a spy
  gate proving identical requests from all three consumers.
single_variable: legacy-flag guard + FixedAdmissionGate seams
lifecycle: ISOLATED_STACK
preconditions:
  - Task 9 part 1 committed; teleop 521 passed; demo baseline clean (EXP-UQ10).
success_criteria:
  - prepare_batch(['--max-points-per-worker', '20']) raises ContractError with
    LEGACY_MAX_POINTS_PER_WORKER_UNSUPPORTED before argparse or allocation.
  - All three consumers accept a gate, ask the same FixedAdmissionRequest (N + kind + R) and report the
    gate's reason code; a gate without a runtime fingerprint/probe refuses instead of passing.
failure_criteria:
  - Any consumer keeping its own formula/hardcode on the gate path, or a gate that passes silently.
invalid_criteria:
  - Retained tests failing only because their argv still carried the retired flag counted as regressions.
provenance:
  source_commit: 18f2b9ee2
  install_overlay: $TASK_ROOT/dev-install (symlinks) + $TASK_ROOT/venv
  runtime_executable: $TASK_ROOT/venv/bin/python
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest adapters-red test_parallel_batch_cli.py::test_legacy_cli_flag_is_an_explicit_error -q
    exit_code: 1
  - command: so101_pytest adapters-green <legacy flag> <test_expert_validation_resource_budget.py> -q
    exit_code: 0
  - command: so101_pytest task10-regression4 test_parallel_batch_cli.py test_parallel_batch_resources.py src/so101_teleop/test -q
    exit_code: 0
observed:
  - RED: the flag was accepted and parsed; GREEN: 5 passed on the adapters gate.
  - resource_budget.py gains FixedAdmissionRequest and FixedAdmissionGate; the gate refuses with
    RESOURCE_PROBE_FAILED when no current fingerprint/live observation is attached, and otherwise
    delegates to admit_production/admit_measurement with the exact-N context.
  - resources.WorkerResourceAllocator accepts resource_gate= and, for the gate path, raises
    ResourceAllocationError with the gate's first reason code and records its decision; the allocator now
    also accepts ParallelRuntimeConfigV2.
  - production._HostResourceProbe accepts resource_gate= and returns the gate's reasons instead of its own
    hardcoded N>3 block when a gate is supplied; cli._prepare_live_headroom accepts resource_gate= and
    raises CliError with the same code.
  - Retained test helpers that still built argv with --max-points-per-worker were migrated (CLI + resources
    fixtures); the adaptive legacy-flag case now expects the stable legacy code; the CLI capacity case uses
    the internally derived quota of the retained path.
  - Suites: adapters 5 passed; task10-regression4 (CLI + resources + full teleop) 784 passed / 0 failed.
inferred:
  - The composition still builds the retained v1 BatchRequest internally and the parser still declares the
    flag for that internal pass-through; switching the composition to BatchRequestV2, deleting the parser
    argument and the coordinator argv entry, and making the gate mandatory for fixed production are the
    remaining Task 10 steps, recorded as the next unit.
conclusion: VALID for the guard and the shared seam; the formula/hardcode removal and mandatory gate are
  the remaining Task 10 work.
evidence:
  - scratch/adapters-red.*, scratch/adapters-green.*, scratch/task10-regression*. *
decision: KEEP
next_experiment: EXP-UQ14

## EXP-UQ13 confirmation and CP-UQ13 checkpoint

Full-gate confirmation after the Task 10 slice and the adaptive-fixture migration:

- `so101_pytest task10-demo-full2 src/so101_demo_py/test -q` exit 1: 3216 passed, 1 skipped,
  1 failed — `test_parallel_adaptive_integration.py::test_external_cleanup_retires_only_owned_worker_and_releases_claim`
  failed with `CleanupError: PROCESS_RETIREMENT_FAILED`. The same file re-run alone in a fresh scratch
  (`adaptive-integration-retry`) passed 14/14, so this is an order/retirement flake, NOT accepted as a pass
  and NOT hidden; it stays an open risk.
- `so101_pytest task10-demo-full3 src/so101_demo_py/test -q` exit 0: **3217 passed, 1 skipped, 0 failed,
  0 errors** in 355 s (scratch/task10-demo-full3.iimdppws, JUnit 3218 cases, zero bad). This is the clean
  full-demo confirmation.
- Teleop package: `task10-regression4` (CLI + resources + full teleop) 784 passed / 0 failed; the teleop
  package alone is 521 passed.

```yaml
checkpoint_id: CP-UQ13
last_valid_experiment: EXP-UQ13
current_hypothesis: The remaining Task 10 unit is the composition switch to BatchRequestV2 plus removal of
  the legacy formulas/hardcodes and the internal parser flag.
working_tree_status: clean at 803a7d1e6 (code) + this docs commit
owned_processes: NONE
preserved_processes: NONE from this task family (canonical install, shared venv, other worktrees untouched)
confirmed_conclusions:
  - AF_UNIX boundary repaired on the dirfd transport; 152/152 Task 3 tests pass (EXP-UQ08).
  - Task-owned venv Python 3.12.3 with pydantic 2.13.4 / pytest 7.4.4 / torch 2.13.0+cu130 /
    mujoco 3.12.0 and pinned setuptools 68.1.2; support package built into the dev overlay; clean
    baselines (demo 3217 passed, teleop 521 passed) (EXP-UQ10, CP-UQ13).
  - Adaptive contract is quota-free with factory-private typed authority (EXP-UQ11).
  - Teleop v2 request contract: legacy key refused by presence, contract_version 2 enforced, honest
    N2..8 availability (EXP-UQ12).
  - Legacy CLI flag refused pre-argparse; Web probe, CLI prepare and allocator share FixedAdmissionGate
    and fail closed without a probe (EXP-UQ13).
disproven_routes:
  - Treating the deep-scratch socket failures, missing mujoco/torch, or the support-prefix assertion as
    product regressions.
open_risks:
  - One flaky adaptive-integration process-retirement run (recorded above); needs monitoring in later full gates.
  - CLI composition still builds the retained v1 BatchRequest and internally passes --max-points-per-worker
    to the coordinator; parser argument, manifest field, coordinator argv entry and the three legacy
    formula/N>3 blocks are still present on the compatibility path.
  - resources.AllocationPolicy still carries the generic enforce_resource_thresholds flag; the typed-context
    migration (plan Task 10) is pending.
  - Remaining Stage A work: Task 10 part 2, Task 11, Task 13/14/15 offline code; then the plan's full
    offline/frozen gates with CTest registration readback.
retained:
  - Commits on codex/so101-unbounded-queue-resource-budget through 803a7d1e6 plus this docs commit.
  - $TASK_ROOT: tools/ (test-gate, task-env, build-task-venv), venv/ + venv-build/*, uv-cache/, dev-build/,
    dev-install/, bindings/v1-contract-baseline.json, run-index.txt, scratch/* (env-baseline-*,
    socket-fix-green, task10-demo-full3, p2-classify*, adaptive-*, adapters-*, teleop-*), colcon/*.
  - Dispatch records: dispatch-20260918-84620fc0/executor-receipt.md,
    followup-20260918T110443-2e37ac85/{executor-receipt.md,probe-01.md},
    followup-20260918T112151-5abbdb70/{executor-receipt.md,probe-01.md}.
archived: none
deletion_candidates: $TASK_ROOT/scratch/* (test scratches) and superseded colcon run logs; no deletion
  authorized or performed; /tmp/uq-ctl-* socket dirs from the Task 5 fixture are removed by the fixture itself.
next_command: >
  Implement Task 10 part 2 in src/so101_demo_py/src/cli/mujoco_parallel_batch.py + resources.py +
  src/so101_teleop/so101_teleop/expert_validation/{preflight,supervisor}.py: load
  config/mujoco/parallel_batch_v2.yaml for new execution, build BatchRequestV2 (FIRST_PASS) with no quota
  field, delete the parser --max-points-per-worker argument and the coordinator argv entry, make
  FixedAdmissionGate mandatory for fixed production admission, remove the N>3/N3-special blocks and the
  4N/6+4N/GPU8 formulas, and migrate the retained CLI/teleop fixtures to the v2 config path; then re-run
  the demo + teleop full gates and add the adopt_existing v2 recheck regression.

## EXP-UQ14 — Task 10 part 2: version-two consumers, formula removal, mandatory gate

```yaml
experiment_id: EXP-UQ14
status: VALID
prior_experiment: EXP-UQ13
hypothesis: New execution can run entirely on the version-two carrier with one shared exact-N gate:
  the CLI, resources CLI, allocator, worker and teleop preflight/supervisor stop using the v1 quota and
  formula fields, and a fixed production run without an approved profile fails closed.
prediction: CLI/resource/teleop suites need fixture migration but no product assertion is weakened; the
  full demo and teleop gates pass with zero failures.
single_variable: v2 config/request/manifest carrier + gate-mandatory fixed allocation
lifecycle: ISOLATED_STACK
preconditions:
  - Task 10 part 1 committed; clean baselines (demo 3217, teleop 521).
success_criteria:
  - prepare_batch loads only schema 2 (v1 -> LEGACY_CONTRACT_EXECUTION_FORBIDDEN), builds BatchRequestV2
    with no quota field, and writes a schema-2 manifest carrying batch_kind.
  - The parser no longer declares --max-points-per-worker; a user argv with it still raises
    LEGACY_MAX_POINTS_PER_WORKER_UNSUPPORTED.
  - Allocator allocate/adopt_existing, worker, resources CLI and teleop preflight/supervisor carry no
    lifetime quota; legacy live-headroom evidence is refused loudly on the v2 path; a v1 manifest never
    starts a v2 restore; a missing/refusing gate refuses with its own code.
  - Retained fixtures migrate to the v2 carrier and the synthetic offline gate; no --ignore/xfail.
failure_criteria:
  - Any consumer silently ignoring a retired authority, or a fixed allocation admitted without a gate.
invalid_criteria:
  - Counting fixture-only failures caused by the retired argv/fields as product regressions.
provenance:
  source_commit: 803a7d1e6 (Task 10 part 1) with this task's changes
  install_overlay: $TASK_ROOT/dev-install (symlinks) + $TASK_ROOT/venv
  runtime_executable: $TASK_ROOT/venv/bin/python
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest cli-v2h -> teleop-k8 ... (iterative RED/GREEN per suite)
    exit_code: 0
  - command: so101_pytest adopt-v2b test_parallel_batch_resources.py::test_v2_adopt_existing_rechecks_budget_and_provenance -q
    exit_code: 0
  - command: so101_pytest teleop-k8 src/so101_teleop/test -q
    exit_code: 0
  - command: so101_pytest task10p2-demo2 src/so101_demo_py/test -q
    exit_code: 0
  - command: so101_pytest task10p2-teleop src/so101_teleop/test -q
    exit_code: 0
observed:
  - CLI: `_load_runtime_config` refuses v1 for new execution; parser arg replaced by --contract-version /
    --batch-kind; BatchRequestV2(FIRST_PASS) built; manifest schema 2 with batch_kind and no quota;
    provenance expects the v2 carrier; gate thread through PreparedBatch into the allocator; the CLI
    live-headroom path is gate-only for v2 and refuses legacy evidence with
    LIVE_HEADROOM_EVIDENCE_UNEXPECTED (missing gate -> BUDGET_PROFILE_UNAVAILABLE).
  - resources.py: allocate and adopt_existing use the gate for v2 (no v1 formula fields), manifests carry
    schema 2, v1 manifests are refused with LEGACY_CONTRACT_EXECUTION_FORBIDDEN, recorded profile drift
    raises RUNTIME_FINGERPRINT_MISMATCH; the resources CLI loads only schema 2 and refuses legacy
    headroom evidence.
  - worker.py accepts ParallelRuntimeConfigV2; teleop preflight FixedExecutionConfig is mode+exact N with
    receipt capacity = shared selection size; the supervisor child argv no longer carries
    --max-points-per-worker and the manual retry stays an independent single-point N1 batch;
    CoordinatorStartRequest keeps the quota optional for historical rows only.
  - Offline test entry: an autouse synthetic gate fixture in the CLI and resources test modules (and a
    module-level _DEFAULT_RESOURCE_GATE in both CLIs) keeps production fail-closed while unit tests
    exercise composition; the new adopt_existing regression passes.
  - Migrated retained tests: CLI argv/manifest/topology/resume/overlay fixtures, resources headroom
    evidence tests (now asserting the gate authority), preflight capacity tests (now asserting the shared
    selection capacity and legacy-quota refusal), supervisor timeline markers.
inferred:
  - The three duplicated consumers now share one parser/provider path for new execution; the retained v1
    formula code is reachable only through historical v1 configs in unit fixtures.
conclusion: VALID pending the recorded full-gate confirmation below.
evidence:
  - scratch/cli-v2*, scratch/res-v2*, scratch/teleop-k*, scratch/adopt-v2*, scratch/task10p2-demo.*
decision: KEEP


### EXP-UQ14 confirmation

- `task10p2-demo2` exit 0: **3217 passed, 1 skipped, 0 failed** (full demo suite).
- `task10p2-teleop` exit 0: **525 passed, 0 failed** (full teleop suite).
- The only full-gate failure during the migration was the retained guard
  `test_adaptive_cli_has_no_parallel_v2_config_route`, which asserted the CLI source must never mention
  the v2 carrier. That guard is superseded by this task (the fixed path now requires the v2 carrier), so
  it was replaced with a behavioural check that the adaptive route still loads
  `parallel_adaptive_workers_v1.yaml` and keeps its own options — not deleted or weakened.

```yaml
checkpoint_id: CP-UQ14
last_valid_experiment: EXP-UQ14
current_hypothesis: Task 11 (OpenAPI + Web no-K UI + contract/installed tests) is the next Stage A unit.
working_tree_status: Task 10 part 2 files committed after this entry
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - New fixed execution runs only on the v2 carrier with the shared exact-N gate; demo 3217 and teleop 525
    pass with zero failures (EXP-UQ14).
disproven_routes:
  - Any fixed allocation admitted by a v1 formula, or a v1 manifest starting a v2 restore.
open_risks:
  - Web/TypeScript surfaces still expose the retired quota input until Task 11; the OpenAPI export and
    generated types must be regenerated from the FastAPI schema in Task 11.
  - The adaptive-specific `max_points_per_worker` compatibility property in teleop adaptive.py remains a
    read-only projection; verify it does not re-enter an execution request in Task 11.
next_command: run the OpenAPI export and Web tests for Task 11 (no-K UI, availability, contract/installed
  specs) after updating web/src and e2e fixtures
```

## EXP-UQ15 — Task 11 Web/OpenAPI no-quota surface and contract e2e

```yaml
experiment_id: EXP-UQ15
status: VALID
prior_experiment: EXP-UQ14
hypothesis: Regenerating the OpenAPI/types and rewriting the setup UI removes the quota input and
  capacity display while exposing exact-N availability, and the contract e2e specs can assert the new
  request/availability contract end to end in Chrome.
prediction: Web unit tests and the contract specs pass with the v2 bodies; the built app no longer
  renders the quota input.
single_variable: OpenAPI schema + Web UI + contract/installed fixtures
lifecycle: ISOLATED_STACK
preconditions:
  - Task 10 committed; clean HEAD; bun 1.3.14 with the existing lock; no service started.
success_criteria:
  - OpenAPI export carries contract_version and worker_count_availability and no
    fixed_max_points_per_worker; generated TS types regenerated from it.
  - Setup UI shows the shared-queue copy and exact-N status/reasons, has no quota input and no Capacity
    text, and blocks Start unless the exact N is selectable.
  - Contract specs (setup + live-preflight) pass in real Chrome; Web unit suite and build pass.
failure_criteria:
  - Any residual quota input, capacity claim, or unversioned request body.
invalid_criteria:
  - A dirty worktree invalidating the provenance binding counted as a product failure (the binding was
    regenerated for the clean commit, which is the designed metadata boundary rule).
provenance:
  source_commit: f19efb21233812f695bf6204f7d98301397c54ae
  install_overlay: $TASK_ROOT/dev-install for the Stage-A contract gate
  runtime_executable: $TASK_ROOT/venv/bin/python + bun 1.3.14
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: $TEST_PYTHON -m so101_teleop.openapi_export --validation src/so101_teleop/so101_teleop/expert_validation_openapi.json
    exit_code: 0
  - command: so101_bun api-types run generate:api:validation
    exit_code: 0
  - command: so101_bun web-unit-final run test
    exit_code: 0
  - command: so101_bun web-build-v2e run build
    exit_code: 0
  - command: so101_bun contract-setup-v2h run test:e2e e2e/expert-validation/contract/setup.spec.ts e2e/expert-validation/contract/live-preflight.spec.ts
    exit_code: 0
observed:
  - OpenAPI: CapabilitiesResponse exposes worker_count_availability and no fixed_max_points_per_worker;
    the only remaining max_points_per_worker is the historical WorkerProjectionResponse field, which the
    plan allows for history projection.
  - Web unit suite 114 passed / 28 files; web build exit 0 (built in 2.7 s).
  - Contract e2e: 17 passed / 0 failed in real Chrome against the scripted server, including C06
    availability refusal, C07 versioned adaptive body, C08/C22 forged-body lease errors and the N8
    availability preview. The gate initially failed twice for real reasons: the scripted capability model
    needed keyword construction (pydantic BaseModel), and the live-sim provenance binding rejects a dirty
    tracked tree, so the binding was regenerated for the clean commit.
  - Fixture migration: setup/installed/live-sim page objects and specs, support.ts fixed/adaptive configs,
    the two scenario YAMLs and scenario.schema.json now carry contract_version 2 and
    worker_count_availability; resolvePackagePrefixes() was added to fixtures/installed.ts and reused by
    live-sim so both gates audit the same overlay/underlay origins.
  - Environment finding: vitest needs NODE_ENV=test (the inherited NODE_ENV=production breaks
    @testing-library/react act()); recorded as so101_web_test_env in the task env helper.
inferred:
  - The installed gate must run from the copied offline overlay (Stage B), not the dev symlink overlay.
conclusion: VALID for the Stage A Web/contract surface.
evidence:
  - browser/web-unit-final.*, browser/web-build-v2e.*, browser/contract-setup-v2h.*, bindings/dev-contract-binding.json
decision: KEEP
next_experiment: EXP-UQ16 (offline copied install + installed gate)

## EXP-UQ16 — Tasks 13/14/15 offline code (qualification, promotion, live verifier)

```yaml
experiment_id: EXP-UQ16
status: VALID
prior_experiment: EXP-UQ15
hypothesis: The offline halves of Tasks 13-15 can be implemented and unit-verified without any live
  measurement, promotion or browser window: the exact-N accumulator, the independent promotion parser,
  and the live-evidence verifier all fail closed on synthetic tampered evidence.
prediction: RED for each unit (missing module/function) then GREEN with the plan's named cases.
single_variable: qualification/promotion/verifier offline modules and suites
lifecycle: ISOLATED_STACK
preconditions:
  - Tasks 10/11 committed; clean teleop/demo baselines; no live window, no promotion.
success_criteria:
  - Five valid business failures do not fill motion coverage; five normal runs plus two experiments per
    cell qualify; invalid/infra runs terminate the sequence; fault pressure never extends normal/product
    counts; a wrong exact N is refused as EXACT_N_UNQUALIFIED.
  - Candidate profile stays CANDIDATE with no review reference; Q contains no P/M/D reference.
  - A candidate tree can never approve itself; M binds P/A0/reviews/operator and never A1/D; D binds
    M/P/A1/location.
  - verifyV2LiveEvidence accepts complete evidence and refuses tampered hashes, a missing runtime slot,
    policy DONE without independent physics and any identity/profile mismatch.
failure_criteria:
  - Any silent acceptance of partial evidence or self-approval.
invalid_criteria:
  - Fixture wiring mistakes counted as product failures (two such defects were fixed: missing pytest
    fixture decorators and a missing private writer helper).
provenance:
  source_commit: dc81fb2faa (installed-gate helpers) plus this unit's changes
  install_overlay: $TASK_ROOT/dev-install + $TASK_ROOT/venv
  runtime_executable: $TASK_ROOT/venv/bin/python and bun 1.3.14
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest qualification-red src/so101_demo_py/test/test_parallel_exact_n_qualification.py -q
    exit_code: 1
  - command: so101_pytest qualification-green3 test_parallel_exact_n_qualification.py test_parallel_resource_measurement.py test_parallel_resource_budget.py -q
    exit_code: 0
  - command: so101_pytest promotion-red src/so101_demo_py/test/test_parallel_budget_promotion.py -q
    exit_code: 1
  - command: so101_pytest promotion-green3 test_parallel_budget_promotion.py test_parallel_resource_identity.py test_parallel_resource_budget.py -q
    exit_code: 0
  - command: so101_bun live-evidence-green run test src/api/live-evidence.test.ts
    exit_code: 0
observed:
  - qualification-green3: 39 passed (7 qualification + 6 measurement + 26 budget).
  - promotion-green3: 38 passed. PromotionAuthority requires an independent 0700 owned root; M binds
    P/A0/Sol/Astra/operator and refuses A1/D keys; a different authority root cannot verify another
    root's promotion; a candidate-tree approval raises PROMOTION_AUTHORITY_INVALID.
  - live-evidence-green: 5 passed (complete root accepted; tampered artifact hash, missing runtime slot,
    policy DONE without physics, and profile/identity mismatch all refused).
  - Task 15 Stage A suite code: 04-resource-budget.spec.ts (N2..8 availability and qualified exact-N
    preservation), 02-parallel migrated to exact N and the detailed R01 gate, R01 now records producer/
    identity/profile/qualification/manifest/cleanup in its gate receipt, requireGateDetail re-checks them,
    resolvePackagePrefixes is shared, and playwright.live-sim.config.ts declares the
    preflight -> r01 -> 02/04 project dependencies. `tsc --noEmit` over the new specs is clean and the
    web build passes.
inferred:
  - Nothing here claims a measured budget, a qualified N, a promotion or a live acceptance; those remain
    NOT_MEASURED / unauthorized.
conclusion: VALID for the offline halves of Tasks 13-15.
evidence:
  - scratch/qualification-*, scratch/promotion-*, browser/live-evidence-green.*, browser/live-suite-build.*
decision: KEEP
next_experiment: EXP-UQ17 (Task 12 unified offline gates)

## EXP-UQ17 — Task 12 offline gates (dev reconfigure, CTest registration, full gates, colcon)

```yaml
experiment_id: EXP-UQ17
status: VALID
prior_experiment: EXP-UQ16
hypothesis: After all Stage A code is committed and clean, a logged dev reconfigure exposes every new
  CTest gate and the full source/package/colcon gates pass without exclusions.
prediction: CTest lists the three required new suites with registered absolute interpreters; the demo,
  teleop, colcon and colcon-test-result gates exit 0.
single_variable: final dev reconfigure + full offline gates
lifecycle: ISOLATED_STACK
preconditions:
  - Stage A code committed and clean; task venv with pinned setuptools 68.1.2 (required by colcon's
    setup.py develop path); no service or measurement started.
success_criteria:
  - ctest --show-only=json-v1 lists test_expert_validation_operator_recovery, _v2_contract and
    _resource_budget, with absolute interpreters inside the registered set.
  - full-demo, full-teleop, colcon test (both packages) and colcon test-result all exit 0.
failure_criteria:
  - Any exclusion, xfail or accepted baseline failure counted as a pass.
invalid_criteria:
  - Harness path/Python-path issues treated as product regressions (two were fixed as environment work).
provenance:
  source_commit: 0f1f7d697 plus the registration/test fixes in this unit
  install_overlay: $TASK_ROOT/dev-install (symlink install) + $TASK_ROOT/venv
  runtime_executable: $TASK_ROOT/venv/bin/python and /usr/bin/python3 (CTest)
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_colcon final-dev-reconfigure build ... --cmake-clean-cache
    exit_code: 0
  - command: so101_record_tool <run> ctest --test-dir $TASK_ROOT/dev-build/so101_teleop --show-only=json-v1
    exit_code: 0
  - command: so101_pytest full-demo src/so101_demo_py/test -q
    exit_code: 0
  - command: so101_pytest full-teleop2 src/so101_teleop/test -q
    exit_code: 0
  - command: so101_colcon full-demo-colcon2 test --packages-select so101_demo_py ... --pytest-args test
    exit_code: 0
  - command: so101_colcon full-teleop-colcon test --packages-select so101_teleop ...
    exit_code: 0
  - command: so101_colcon full-test-result test-result --test-result-base $TASK_ROOT/dev-build --verbose
    exit_code: 0
observed:
  - dev reconfigure (with --cmake-clean-cache) exit 0 after the setuptools pin.
  - First CTest readback found 52 registered suites and reported the two NEW suites
    (test_expert_validation_v2_contract, test_expert_validation_resource_budget) as missing; both were
    registered in src/so101_teleop/CMakeLists.txt and the retained package-layout expectation was updated.
    Second readback: 54 registered, missing none, interpreters ['/usr/bin/python3'] all absolute and
    inside the registered COLCON_TEST_PYTHONS set.
  - full-demo pytest: 3228 passed, 1 skipped, 0 failed, exit 0 (6min4s).
  - full-teleop pytest: 525 passed, 0 failed, exit 0 (40s).
  - demo colcon test: exit 0, 1 package finished in 5min54s. The first attempt failed at collection with
    ModuleNotFoundError: tools (the demo suite imports the repo-root helper package); the colcon/CTest
    harness runs per package, so the repo root is now appended to PYTHONPATH by so101_colcon_gate_env —
    the same path the direct `python -m pytest` gate gets implicitly from the repo-root CWD.
  - teleop colcon test: exit 0 (1min10s); colcon test-result: exit 0.
  - Web gates (EXP-UQ15): unit 114 passed, build exit 0, contract e2e 17 passed; installed e2e from the
    copied offline overlay 15 passed.
inferred:
  - The Stage A offline implementation and the Task 12 offline gate set are complete; the remaining plan
    work needs separate authority (owned recovery/deployment, candidate measurement, promotion, Chrome)
    and the independent Astra/Sol reviews.
conclusion: VALID offline; no runtime, measurement or promotion claim.
evidence:
  - colcon/final-dev-reconfigure*, colcon/ctest-registration.*, scratch/full-demo.*, scratch/full-teleop2.*,
    colcon/full-demo-colcon2.W4qsiawV, colcon/full-teleop-colcon.9Q1viRup, colcon/full-test-result.*
decision: KEEP
next_experiment: NONE-AUTHORIZED (Stage B owned actions need authority)

## EXP-UQ18 — production copied install, A0 audit and final authorized state

```yaml
experiment_id: EXP-UQ18
status: VALID
prior_experiment: EXP-UQ17
hypothesis: With all Stage A code committed and clean, the production copied overlay can be built and
  audited offline, producing the frozen install and A0 that Stage C/D would reference.
prediction: The production build exits 0; the external binding binds the clean HEAD and the production
  prefix; the A0 full-byte audit covers the copied files and the v2 config carrier.
single_variable: production copied install + A0 audit generation
lifecycle: ISOLATED_STACK
preconditions:
  - All Stage A code committed; full offline gates green (EXP-UQ17); no service started.
success_criteria:
  - production-install copied (no symlink install), module origins inside the prefix.
  - bindings/production-provenance.json binds the clean HEAD, and bindings/production-a0.json records the
    full-byte inventory including the v2 config carrier.
failure_criteria:
  - A dirty tree, a symlinked install, or an unverifiable origin.
invalid_criteria:
  - n/a
provenance:
  source_commit: a812c9c6693a5adab3a01fad2f0cf50f7197ed3b
  install_overlay: $TASK_ROOT/production-install (copied)
  runtime_executable: $TASK_ROOT/venv/bin/python
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_colcon production-copy-build build --packages-select so101_demo_py so101_teleop so101_mujoco_support --build-base $TASK_ROOT/production-build --install-base $TASK_ROOT/production-install
    exit_code: 0
observed:
  - production-install built exit 0; module origins resolve inside the production prefix (verified by the
    A0 generation script that imported both packages from the production overlay).
  - bindings/production-provenance.json: source_commit a812c9c66, worktree_dirty_tracked false,
    install_prefix $TASK_ROOT/production-install, carrier sha256 8ae1855adaf6bc9f…
  - bindings/production-a0.json: 1275 files, A0 sha256 08277ce1ce78a13e…, carrier recorded as the only
    semantic S carrier among the audited files.
inferred:
  - Stage C measurement, Stage D promotion and Stage E browser acceptance remain blocked on their own
    authority; nothing here claims a qualified N, an approved profile or a live acceptance.
conclusion: VALID offline. This is the final authorized artifact of the current instruction set.
evidence:
  - colcon/production-copy-build.*, bindings/production-provenance.json, bindings/production-a0.json
decision: KEEP
next_experiment: NONE-AUTHORIZED
```

```yaml
checkpoint_id: CP-UQ18
last_valid_experiment: EXP-UQ18
current_hypothesis: NONE (authorized offline work complete)
working_tree_status: clean at the final docs commit
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - Stage A implementation complete with clean demo (3228 passed) / teleop (525 passed) / colcon
    (3807 tests, 0 errors, 0 failures) / Web (unit 114, build, contract 17, installed 15) gates.
  - Production copied install + A0 audit frozen at commit a812c9c66 (EXP-UQ18).
  - All N budgets remain NOT_MEASURED; no profile, promotion, deployment receipt or live acceptance exists.
blocked_commands:
  - Stage B owned recovery/Web refresh: production-install launcher + so101_expert_validation_recover.py --apply + owned Web start (needs the exclusive owned window).
  - Stage C measurement: $TASK_ROOT/production-install/so101_demo_py/lib/so101_demo_py/so101_measure_parallel_resources --authorization <sealed> --intent CALIBRATION_ONLY (needs a sealed MeasurementAuthorization window; the candidate runner hook is also still unwired).
  - Stage D promotion: publish_promotion + carrier-ref commit + A1/D (needs operator exact-N/profile-hash approval plus Astra/Sol reviews).
  - Stage E live Chrome: so101_bun live-qualified-pipeline run test:e2e:live-sim --project parallel-resource (needs the exclusive owned browser window).
  - Independent reviews: GPT-6 Astra/High for Tasks 1-4 code, L/inventory, closed contexts, Task 11 API and Task 16 guide; GPT-5.6 Sol/High execution-result review (cannot be self-approved).
retained:
  - All prior evidence plus venv-build/*, offline-install/offline-build, production-install/production-build,
    bindings/{dev-contract,offline-provenance,production-provenance,production-a0}.json, colcon/*,
    scratch/*, browser/*.
archived: none
deletion_candidates: $TASK_ROOT/scratch/* and superseded colcon run logs (classification only; nothing deleted)
next_command: NONE authorized; awaiting the operator decisions listed above.

## Correction to CP-UQ18 (review F1–F3) and EXP-UQ19 — F1 candidate runtime composition

Correction (appended, not rewriting history): CP-UQ18's "authorized offline work complete" was an
overclaim. The Sol/High execution review (`followups/repair-review-3c00fb20-.../execution-review.md`,
SHA256 `bbedfc5dc999086c34506a2252765b661291972583c1508d390b46d6eba1c603`, decision CHANGES_REQUIRED)
found three P1 integration gaps that the package-green gates did not cover: the candidate CLI had no
successful runtime path (F1), installed production factories did not compose the shared budget gate (F2),
and the promotion/deployment producers could not be consumed by the context issuer (F3). Tasks 0–11 plus
the offline halves of 13/14/15 stand as recorded; the "offline complete" claim does not.

```yaml
experiment_id: EXP-UQ19
status: VALID
prior_experiment: EXP-UQ18
hypothesis: The candidate entry can compose a real, sealed measurement lifecycle from closed sealed
  runtime bindings, with a typed bounded fake workload boundary offline and fail-closed refusals.
prediction: RED at the missing runtime_bindings/plan/lifecycle; GREEN with a positive sealed lifecycle,
  binding tamper/containment refusals and specific workload/seal/abort codes.
single_variable: measurement runtime bindings + candidate plan/lifecycle + CLI runner composition
lifecycle: ISOLATED_STACK
preconditions:
  - Review read completely and hash-verified; receipt written exclusively; startup probe matched the
    handoff (HEAD dacbdbd8, clean, CP-UQ18, pane %68, task venv origins).
success_criteria:
  - MeasurementAuthorization requires the closed MeasurementRuntimeBindings (plan Task 6 line 418).
  - build_candidate_plan derives EXECUTE/v2/FIRST_PASS argv from the bindings, verifies exact bytes,
    containment and the catalog binding, and re-verifies at use time.
  - run_candidate_batch composes sampler -> authorized workload -> seal with
    MEASUREMENT_WORKLOAD_FAILED / MEASUREMENT_SEAL_FAILED / latch propagation, and a valid run emits a
    sealed candidate document with no profile reference.
  - The CLI reaches the composition (positive exit 0 with a typed fake runner/capability boundary) and
    still refuses missing capability, expired/wrong authority and tampered bindings.
failure_criteria:
  - Any unconditional success path, production-profile borrowing, arbirary env override, or fake pass.
invalid_criteria:
  - Capability absence on this host counted as a product failure (the typed probe boundary is explicit).
provenance:
  source_commit: dacbdbd8dc143387191353fd6e1ff5e9c55bfb3d
  install_overlay: $TASK_ROOT/dev-install + $TASK_ROOT/venv
  runtime_executable: $TASK_ROOT/venv/bin/python
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest f1-red src/so101_demo_py/test/test_parallel_measurement_runtime.py -q
    exit_code: 1
  - command: so101_pytest f1-green5 test_parallel_measurement_runtime.py test_parallel_measurement_cli.py test_parallel_resource_measurement.py -q
    exit_code: 0
observed:
  - RED: 5 failed at the missing runtime_bindings/build_candidate_plan/run_candidate_batch/runner_factory.
  - GREEN: 16 passed. Positive lifecycle returns status SEALED with the authorization hash and intent and
    no profile/promotion/deployment keys; the fake runner receives the exact plan argv (EXECUTE/v2,
    FIRST_PASS, no --max-points-per-worker).
  - Refusals proven: unknown/missing binding fields, non-absolute declared path (BINDING_PATH at parse),
    missing declared file and tampered weight bytes (BINDING_HASH_MISMATCH), catalog mismatch,
    workload exception (MEASUREMENT_WORKLOAD_FAILED), latched abort propagation, sealing failure
    (MEASUREMENT_SEAL_FAILED), and the production runner factory refusing without an installed launcher.
  - The real factory drives the frozen copied install's so101_parallel_batch with the binding-derived
    argv; no environment override and no profile authority is read. Nothing was executed live.
inferred:
  - Actual measurement still requires the separate sealed window; this repair only supplies the path.
conclusion: VALID for F1. F2 and F3 remain.
evidence:
  - scratch/f1-red.*, scratch/f1-green*.*, followups/repair-review-3c00fb20-.../startup-probe01.*
decision: KEEP
next_experiment: EXP-UQ20 (F2 production composition)

## EXP-UQ20 — F2 installed production composition and dynamic exact-N capability

```yaml
experiment_id: EXP-UQ20
status: VALID
prior_experiment: EXP-UQ19
hypothesis: The installed factory, both console CLIs and the allocator can compose the SAME provider
  from verified installed P/Q/M/D authority, derive per-N capabilities from provider decisions, and keep
  fail-closed refusals with no formula path for v2.
prediction: RED at the missing composer; GREEN with the actual installed factory (imported from a copied
  prefix in a child process) reporting exactly one selectable N and every other N refused by code.
single_variable: production admission composer + consumer wiring + capability derivation
lifecycle: ISOLATED_STACK
preconditions:
  - F1 committed; review findings used as root cause; frozen plan/design hashes unchanged.
success_criteria:
  - compose_production_admission returns None only with no declared authority and raises on partial or
    tampered authority; it verifies the profile hash and records per-N qualification documents.
  - The gate mints the exact-N context per request, converts exact-N/profile refusals into decisions and
    re-reads a fresh live observation per admission.
  - _HostResourceProbe uses the gate for v2 (no N>3/4N/6+4N/GPU8 path), capabilities come from
    worker_count_availability, and prepare_batch/resources.main default to the installed composer.
  - A copied-install child process running the ACTUAL create_production_service reports N4 selectable with
    the profile/Q hashes and every other N refused with EXACT_N_UNQUALIFIED.
failure_criteria:
  - Any production dependence on a test seam, hand-written availability, or silent downgrade.
invalid_criteria:
  - Fixture/environment errors counted as product failures (four were fixed: coverage matrix, fingerprint
    identity, copied-install AMENT prefixes, stale copied install).
provenance:
  source_commit: 97985069e plus the F2 commits
  install_overlay: repair-offline-install (copied from the repaired source) + dev overlay + task venv
  runtime_executable: $TASK_ROOT/venv/bin/python
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest f2-red test_expert_validation_installed_budget.py -q
    exit_code: 1
  - command: so101_pytest f2-green14 test_expert_validation_installed_budget.py -q
    exit_code: 0
  - command: so101_pytest f2-regression src/so101_teleop/test test_parallel_batch_cli.py test_parallel_batch_resources.py -q
    exit_code: 0
observed:
  - RED: 3 failed at the missing compose_production_admission / capability derivation.
  - GREEN: 4 passed, including the copied-install child that imports so101_demo/so101_teleop from
    repair-offline-install via explicit PYTHONPATH+AMENT_PREFIX_PATH, resolves the test-owned binding for
    the current clean HEAD, and prints capabilities with N4 selectable (profile/Q hashes bound) and
    N2,N3,N5..N8 refused by EXACT_N_UNQUALIFIED; the child also proved its tempdir resolved inside the
    run scratch.
  - Regression: 788 passed across the teleop package plus the CLI and resources suites.
  - The three consumers agree through the same gate: Web probe (admit N4, refuse N5), CLI _prepare_live_headroom
    (admit N4 via the gate summary) and allocator _live_headroom (admit N4 with the gate's profile hash,
    refuse N5 with the same code).
  - Missing authority returns None and every consumer keeps BUDGET_PROFILE_UNAVAILABLE; tampered profile
    bytes raise HASH_MISMATCH at composition; live drift (unattributed background) refuses the requested N
    with BACKGROUND_ENVELOPE_EXCEEDED and worker_count 4 (no downgrade).
  - New immutable artifacts: repair-offline-build*/repair-offline-install (copied from the repaired
    source); the earlier offline-install/production-install and their bindings were not modified.
inferred:
  - F3 remains: the promotion/deployment producers still emit schema 1 while the context issuer reads
    schema 2.
conclusion: VALID for F2.
evidence:
  - scratch/f2-red.*, scratch/f2-green*.*, scratch/f2-regression.*, colcon/repair-offline-build*.*
decision: KEEP
next_experiment: EXP-UQ21 (F3 producer/reader round-trip)

## EXP-UQ21 — F3 unified promotion/deployment round-trip

```yaml
experiment_id: EXP-UQ21
status: VALID
prior_experiment: EXP-UQ20
hypothesis: One closed schema2 validation shared by the promotion producer, the verifier and the context
  issuer makes the actual producer outputs consumable, without weakening reviews/operator/profile/N/location
  checks.
prediction: RED shows the actual publish_promotion output refused by the issuer (PROMOTION_SCHEMA_VERSION);
  after unification the actual round-trip reaches the issuer and every altered artifact is refused.
single_variable: promotion/deployment schema unification + shared validation
lifecycle: ISOLATED_STACK
preconditions:
  - F2 committed; synthetic private task-owned authority fixtures only; no real approval/promotion written.
success_criteria:
  - publish_promotion writes schema2 with structured sol/astra review references plus the shared hash
    fields; build_deployment_receipt writes schema2 with kind; verify_promotion and
    issue_production_context share one closed validation.
  - Actual producer -> actual issuer round-trip succeeds; altered review result, review list, profile
    hash, exact N and deployment receipt are refused with their specific codes.
failure_criteria:
  - Any weakening of review/operator/hash/exact-N/location validation to make fixtures pass.
invalid_criteria:
  - Retained fixtures still written in the superseded shape counted as regressions (migrated).
provenance:
  source_commit: c3396fb2c plus the F3 commits
  install_overlay: dev overlay + task venv (copied install rebuilt separately for the e2e gate)
  runtime_executable: $TASK_ROOT/venv/bin/python
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_pytest f3-red src/so101_demo_py/test/test_parallel_budget_promotion.py -q
    exit_code: 1
  - command: so101_pytest f3-green3 test_expert_validation_installed_budget.py test_parallel_budget_promotion.py -q
    exit_code: 0
  - command: so101_pytest repair-full-demo src/so101_demo_py/test -q
    exit_code: 0
  - command: so101_pytest repair-full-teleop src/so101_teleop/test -q
    exit_code: 0
observed:
  - RED: the real publish_promotion output was refused with PROMOTION_SCHEMA_VERSION (the reviewer's static
    deduction reproduced as an executed failing assertion).
  - GREEN: 10 passed for the F2+F3 files; 37 passed for promotion+budget+measurement runtime.
  - Full gates: repair-full-demo exit 0 (see counts below), repair-full-teleop exit 0.
  - Round-trip: publish_promotion -> verify_promotion -> build_deployment_receipt -> issue_production_context
    produced a FixedProductionContext bound to the profile and qualification hashes; refusals proven for a
    CHANGES_REQUIRED Astra review (INDEPENDENT_REVIEW_REQUIRED), altered profile hash
    (PROMOTION_PROFILE_MISMATCH), missing review list (PROMOTION_REVIEWS), a different exact N
    (EXACT_N_UNQUALIFIED) and a tampered deployment receipt
    (DEPLOYMENT_RECEIPT_PROMOTION_MISMATCH).
  - Retained fixtures written in the superseded shape (Task 4 synthetic chain, F2 installed fixture) were
    migrated to the unified schema; no assertion was weakened.
inferred:
  - Producer and consumer now agree; the independent Sol/Astra review gates and the operator promotion
    remain external and are still pending.
conclusion: VALID for F3.
evidence:
  - scratch/f3-red.*, scratch/f3-green*.*, scratch/f3-regression.*, scratch/repair-full-*.*
decision: KEEP
next_experiment: EXP-UQ22 (repaired copied install and installed gate)

## EXP-UQ22 — repaired copied install and post-repair gate matrix

```yaml
experiment_id: EXP-UQ22
status: VALID
prior_experiment: EXP-UQ21
hypothesis: After F1-F3 the frozen repaired source can be copied into a new immutable install and every
  required offline gate passes against it.
prediction: The final copied install builds exit 0; the demo/teleop/colcon/OpenAPI/Web/contract/installed
  gates all pass with the repaired code.
single_variable: repair-final copied install + gate matrix
lifecycle: ISOLATED_STACK
preconditions:
  - F1-F3 committed and the tree clean; earlier frozen copies and bindings untouched.
success_criteria:
  - repair-final-install built from the repaired HEAD with module origins inside the prefix.
  - All required gates exit 0 with real collected counts.
failure_criteria:
  - Any exclusion, stale overlay or overwritten prior artifact.
invalid_criteria:
  - A missing test-mode environment counted as a product failure (re-run with NODE_ENV=test).
provenance:
  source_commit: a2373a6b29f7023d48b45978186aff657c8ac98e
  install_overlay: $TASK_ROOT/repair-final-install (copied, repaired source)
  runtime_executable: $TASK_ROOT/venv/bin/python + /usr/bin/python3 (CTest) + bun 1.3.14
  ros_domain_id: n/a
  gz_partition: n/a
commands:
  - command: so101_colcon repair-final-build build --packages-select so101_demo_py so101_teleop so101_mujoco_support --build-base $TASK_ROOT/repair-final-build --install-base $TASK_ROOT/repair-final-install
    exit_code: 0
  - command: so101_pytest repair-full-demo src/so101_demo_py/test -q
    exit_code: 0
  - command: so101_pytest repair-full-teleop src/so101_teleop/test -q
    exit_code: 0
  - command: so101_colcon repair-demo-colcon test ... --pytest-args test
    exit_code: 0
  - command: so101_colcon repair-teleop-colcon test ...
    exit_code: 0
  - command: so101_colcon repair-test-result test-result --test-result-base $TASK_ROOT/dev-build --verbose
    exit_code: 0
  - command: so101_pytest repair-openapi src/so101_teleop/test/teleop/test_openapi_export.py -q
    exit_code: 0
  - command: so101_bun repair-web-unit2 run test
    exit_code: 0
  - command: so101_bun repair-web-build run build
    exit_code: 0
  - command: so101_bun repair-contract-gate run test:e2e e2e/expert-validation/contract/setup.spec.ts e2e/expert-validation/contract/live-preflight.spec.ts
    exit_code: 0
  - command: so101_bun repair-installed-gate run test:e2e:installed <four installed specs>
    exit_code: 0
observed:
  - repair-full-demo: 3235 passed, 1 skipped, exit 0 (354.58 s).
  - repair-full-teleop: 529 passed, exit 0 (40.55 s) — includes the F2 installed-composition suite.
  - colcon: demo exit 0 (339.68 s), teleop exit 0 (70.61 s), test-result summary
    3814 tests, 0 errors, 0 failures, 1 skipped.
  - OpenAPI: 5 passed.
  - Web unit: 119 passed / 29 files (exit 0) after NODE_ENV=test; build exit 0 (2.56 s).
  - Contract e2e: 17 passed (exit 0). Installed e2e against repair-final-install: 15 passed (exit 0).
  - bindings/repair-final-provenance.json binds commit a2373a6b29f7023d48b45978186aff657c8ac98e, clean
    tree, install_prefix repair-final-install, with both product module origins inside the prefix.
inferred:
  - The three review findings are repaired at their real consumer boundaries; the remaining plan work needs
    the external authority stages and reviews that this unit is not authorized to perform.
conclusion: VALID. Stop for Sol/High re-review per the dispatch.
evidence:
  - colcon/repair-final-build.*, scratch/repair-full-*.*, colcon/repair-*colcon.*, colcon/repair-test-result.*,
    browser/repair-web-unit2.*, browser/repair-web-build.*, browser/repair-contract-gate.*,
    browser/repair-installed-gate.*, bindings/repair-final-provenance.json
decision: KEEP
next_experiment: NONE-AUTHORIZED (await Sol/High re-review)
```

```yaml
checkpoint_id: CP-UQ23
last_valid_experiment: EXP-UQ23
current_hypothesis: R1-R4 of the Sol/High execution re-review (CHANGES_REQUIRED) are repaired at the
  real default consumer boundaries and offline-proven; the remaining plan work still needs the
  external authority stages and independent reviews.
dispatch: 4d4468ef-5403-4103-b95a-2243c9211b49 (repair unit; receipt written O_EXCL first, then a
  read-only startup probe with HEAD f3a6aa22, clean tree, CP-UQ22, tmux pane %68)
review_input: followups/repair-rereview-4d4468ef-.../execution-rereview.md
  SHA256 84303c2a939927059e0e2ca5202344e06a816afbb4d906fff8bffa2b99714ced
repairs:
  - R1 candidate entry: the sealed authorization path + raw hash and the provenance binding now travel
    in CandidateRunPlan.runner_argv(); the installed launcher re-reads the same bytes, the measurement
    composer refuses any inherited production authority (MEASUREMENT_AUTHORITY_ENV_CONFLICT), verifies
    the batch/worker/points/yolo/grounded/broker/config arguments against the sealed bindings
    (MEASUREMENT_ARGUMENT_MISMATCH) and admits only through a MEASUREMENT-kind context.
  - R2 lifecycle: MeasurementSession owns a delegated cgroup whose memory/cpu caps are written and read
    back (MEASUREMENT_LIMIT_UNENFORCEABLE otherwise), a real sampler thread over the owned cgroup plus
    NVML, a real AF_UNIX control endpoint inside the batch root, a latch that signals the owned process
    group, the authorized deadline, and a containment-verified removal plus cleanup receipt. Sealing now
    uses the ORIGINAL immutable authorization (plan_authorization_view deleted) and lands inside the
    authorized per-batch root; raw_files carry the real samples/events/streams/receipt.
  - R3 observation/identity: probe_host_facts reads effective cpuset/quota CPU, MemTotal/MemAvailable,
    swap/PSI/throttle counters and whole-device NVML (ctypes libnvidia-ml, no new dependency);
    attribution_complete is derived from what the probe could attribute; admit_production applies the
    profile's exact-N stage demand/uncertainty; the runtime fingerprint is recomputed from the v2 config,
    source/installed inventory bytes and hardware facts, verified against the declared identity, and
    refreshed before every admission (fingerprint_source); the control binding is the verified
    deployment location binding, not a literal.
  - R4 authority chain: publish_promotion re-reads operator approval and both independent reviews through
    the PromotionAuthority root, requires reviewer/target/profile/A0 bindings, records the authority
    document names, and M is validated with a closed field set; issue_production_context now requires the
    trusted A1 audit, the current R identity, the current location binding and equality with D's
    installed_audit_sha256/execution_identity_sha256/location_binding before minting a context.
  - Audit gaps: test_expert_validation_installed_budget.py is registered in
    src/so101_teleop/CMakeLists.txt (55 CTest registrations) and in the teleop layout expectation; the
    gate wrappers now persist argv.txt for direct pytest runs and write labelled interpreter records
    (role=..., interpreter=..., resolved=..., prefix=..., tempdir=...).
tests:
  - New: src/so101_demo_py/test/test_parallel_default_authority_paths.py (10 passed) proves the real
    default probe attribution/effective capacity, the derived-and-verified identity, per-admission
    refresh, profile-stage demand admission/refusal, and the closed M/D chain negatives (deleted field,
    foreign audit, identity drift, location/control mismatch, unknown field, substituted review).
  - New: src/so101_demo_py/test/test_parallel_measurement_default_path.py (8 passed) runs the installed
    CLI, the default runner factory and the real session with hermetic low-level host/workload ports:
    launcher argv transport, seal preserving the original authorization, cgroup cap readback, real
    sampler samples, latch on a memory-event breach, authorized deadline, verified cleanup, refusal of a
    non-zero workload and of an inherited production authority.
  - Migrated: test_parallel_budget_promotion.py, test_parallel_resource_budget.py,
    test_parallel_measurement_runtime.py, test_parallel_measurement_cli.py, and the teleop
    installed_budget suite now build authority only through the real producers; the child process test
    uses the DEFAULT admission factory with the real host probe (no admission_factory injection).
gates:
  - scratch/rereview-full-demo.wGZ173ak: exit 1, 3250 passed, 1 skipped, 1 failed
    (test_parallel_adaptive_integration.py::test_external_cleanup_retires_only_owned_worker_and_releases_claim,
    CleanupError PROCESS_RETIREMENT_FAILED under full-suite load); scratch/rereview-cleanup-retry passes
    that test in isolation (exit 0) - recorded as an intermittent ordering/load flake, not a silent pass.
  - scratch/rereview-full-teleop2.*: 528 passed + the 4 installed-budget tests after the layout commit
    (scratch/rereview-teleop-budget4.*, 4 passed) = 529; colcon/colcon/... see below.
  - browser/rereview-web-unit3.SUsUZB9t: exit 0, 29 files / 119 passed.
  - colcon: rereview-d-colcon.jJj6dEhO build exit 0 (real cmake re-run, 17s);
    rereview-e-colcon.kOYZxX00 test -> see the result appended by this unit's readback.
  - Command-level: every pytest/colcon/web run above resolved its executable through the task venv plus
    registered /usr/bin/python3 with labelled proofs and an argv.txt.
install:
  - New immutable copied install for this unit: rereview-build/rereview-install (built from the repaired
    HEAD, module origins inside the prefix). It is NOT a production A0 or full inventory/dependency
    audit; the stale repair-offline-install/repair-final-install copies and old A0/binding remain
    historical and are not reused as proof of the repaired execution.
inferred:
  - R1-R4 close the default-path authority, safety, sampling, sealing and closed-chain defects at their
    real consumers; production still cannot admit anything on this host because no approved profile,
    promotion, deployment receipt or qualification exists.
conclusion: VALID offline. Stop for Sol/High re-review per the dispatch.
evidence:
  - scratch/rereview-*, colcon/rereview-*, browser/rereview-*, rereview-build, rereview-install,
    followups/repair-rereview-4d4468ef-*/{executor.receipt,startup-probe01.log,startup-probe01.result.json}
decision: KEEP
next_experiment: NONE-AUTHORIZED (await Sol/High re-review)
```

```yaml
checkpoint_id: CP-UQ23A
last_valid_experiment: EXP-UQ23
current_hypothesis: Readback correction and completion of the CP-UQ23 gate matrix.
readback:
  - colcon/rereview-e-colcon.kOYZxX00 (test against the COPIED rereview-install base, exit 1):
    so101_teleop 55/55 CTest registrations passed, including the newly registered
    test_expert_validation_installed_budget (Start 41, run with /usr/bin/python3 from
    dev-build/so101_teleop/CTestTestfile.cmake). so101_demo_py had 10 failures in
    test_text_agent_execution_provenance.py, test_text_pick_agent_cli.py and
    test_text_pick_agent_e2e_process.py with EXECUTION_SOURCE_PROVENANCE_UNAVAILABLE: the copied
    (non-symlink) install resolves so101_demo.application.text_agent outside any git repository.
    Those were 3241 passed there and only 1 failed under the direct dev-overlay pytest run, so this
    is an artifact of pointing CTest at the copied prefix, not a source regression. CTest is
    therefore run against the dev overlay bases exactly as before.
  - colcon/rereview-g-colcon.tJ6liTYr (build into dev-build/dev-install): exit 0, real cmake
    re-configure, so dev-build/so101_teleop/CTestTestfile.cmake now carries the new registration.
  - colcon/rereview-h-colcon.8cRVknD1 (test against dev-build/dev-install, exit 1):
    so101_teleop 100% passed, 0 failed out of 55; so101_demo_py 3250 passed, 1 skipped,
    1 failed = test_text_pick_agent_e2e_process.py::test_real_launch_service_accepts_only_after_owned_cleanup
    (a real-launch E2E process test that passes under the direct pytest run of the same tree).
    This one failure is recorded OPEN and is not claimed as green; it is unrelated to the
    parallel-batch modules changed by this unit (no shared code path, and its direct run is green).
  - scratch/rereview-full-demo.wGZ173ak (direct): 3250 passed / 1 skipped / 1 failed
    (test_parallel_adaptive_integration.py::test_external_cleanup_retires_only_owned_worker_and_releases_claim);
    scratch/rereview-cleanup-retry.Nj82zL4F re-ran that exact test alone and it passed (exit 0).
  - browser/rereview-web-unit3.SUsUZB9t: exit 0, 29 files / 119 passed.
  - scratch/rereview-teleop-budget4.DV9aUuQq: 4 passed (installed budget suite against the copied
    rereview-install prefix with the DEFAULT admission factory and the real host probe).
wrapper_change:
  - $TASK_ROOT/tools/test-gate.zsh (task-owned gate tooling, not part of the worktree commit): direct
    pytest runs now persist argv.txt and every pytest/colcon interpreter check writes a labelled
    record (role=..., interpreter=..., resolved=..., prefix=..., tempdir=...) instead of bare paths.
inferred:
  - The repair unit's code/tests are offline-proven; two environment-sensitive E2E tests remain open in
    the colcon context and are recorded rather than explained away.
conclusion: VALID offline with two OPEN E2E observations. Stop for Sol/High re-review.
evidence: colcon/rereview-{e,g,h}-colcon.*, scratch/rereview-*, browser/rereview-web-unit3.*
decision: KEEP
next_experiment: NONE-AUTHORIZED (await Sol/High re-review)
```

```yaml
checkpoint_id: CP-UQ24
last_valid_experiment: EXP-UQ23
current_hypothesis: NONE (repair unit complete; awaiting independent re-review)
working_tree_status: clean after the code/test commits plus this ledger commit
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - The measurement default path carries only the sealed authorization and runs under a real owned
    cgroup, sampler, latch, deadline and verified cleanup (EXP-UQ23).
  - Production admission now derives effective attributed host facts, the exact-N stage demand from the
    approved profile and a freshly derived runtime identity, and the M/D chain is re-read through the
    independent authority before any context is minted (EXP-UQ23).
unresolved_independent_reviews:
  - GPT-5.6 Sol/High re-review of R1-R4 (this checkpoint stops for it); the execution review stays
    CHANGES_REQUIRED until it passes.
  - GPT-6 Astra/High: Task 1-4 identity/inventory/closed-context boundaries, Task 11 API/installed
    closure, Task 16 guide (none performed).
unperformed_live_stages:
  - Stage B owned recovery/Web refresh; Stage C candidate measurement (no sealed authorization; the
    default runner is implemented and offline-proven but has never been invoked live); Stage D operator
    promotion/deployment (no approval); Stage E live Chrome acceptance.
  - All exact-N budgets remain NOT_MEASURED; none is qualified or selectable in reality.
retained:
  - Every run, log, binding, copied install and scratch from this and earlier units, including the
    intermittent full-suite failure and its isolated passing re-run.
archived: none
deletion_candidates: $TASK_ROOT/scratch/*, superseded colcon run logs and the stale
  repair-offline-build/repair-offline-install copies after readback (classification only)
next_command: NONE authorized; await Sol/High re-review and the separate Astra/High and operator gates.
```

```yaml
checkpoint_id: CP-UQ22
last_valid_experiment: EXP-UQ22
current_hypothesis: NONE (authorized repair unit complete; awaiting independent re-review)
working_tree_status: clean at the final docs commit
owned_processes: NONE
preserved_processes: NONE from this task family
confirmed_conclusions:
  - F1 candidate lifecycle composes and seals from closed sealed bindings, offline-proven (EXP-UQ19).
  - F2 installed factory/CLIs/allocator compose one provider; capabilities derive from decisions; copied
    install child proves N4-only selectability (EXP-UQ20).
  - F3 producer/verifier/issuer share one closed schema2 promotion/deployment contract with a real
    round-trip (EXP-UQ21).
  - Post-repair gate matrix green: demo 3235, teleop 529, colcon 3814/0/0/1 skipped, OpenAPI 5, Web 119,
    contract 17, installed 15 (EXP-UQ22).
unresolved_independent_reviews:
  - GPT-6 Astra/High: Task 1-4 identity/inventory/closed-context boundaries, Task 11 API/installed
    closure, Task 16 guide (none performed).
  - GPT-5.6 Sol/High re-review of these F1-F3 repairs (this checkpoint stops for it)
  - The earlier Sol/High execution review remains CHANGES_REQUIRED until that re-review passes.
unperformed_live_stages:
  - Stage B owned recovery/Web refresh (no owned window); Stage C candidate measurement (no sealed
    authorization; the runner hook is now implemented but has never been invoked live); Stage D operator
    promotion/deployment (no approval; no real promotion record exists); Stage E live Chrome acceptance.
  - All exact-N budgets remain NOT_MEASURED; none is qualified or selectable in reality.
retained:
  - Every run, log, binding, copied install and scratch from this and earlier units, including the failed
    intermediate attempts (f2-green1..13, f3-red, repair-web-unit.5RMhplZE).
archived: none
deletion_candidates: $TASK_ROOT/scratch/*, superseded colcon run logs, the outdated
  repair-offline-build/repair-offline-install copies after readback (classification only; nothing deleted)
next_command: NONE authorized; await Sol/High re-review and the separate Astra/High and operator gates.

```yaml
checkpoint_id: CP-UQ25
last_valid_experiment: EXP-UQ23
current_hypothesis: The pytest-parallelism guidance notice is acknowledged and its narrow skill delta is
  applied; R1-R4 repair stays the primary line and remains stopped for Sol re-review.
notice:
  dispatch: 2a146e37-cffb-4443-8939-947180cd75d9
  handoff: followups/pytest-xdist8-2a146e37-cffb-4443-8939-947180cd75d9/handoff.md
    SHA256 e7ea16fa075fb35348a2ffc523fc4bdb6c9fa901a140967a1abc2eba074fb70f
  receipt: followups/pytest-xdist8-.../executor.receipt (exclusive O_EXCL, UUID+newline)
  probe: followups/pytest-xdist8-.../startup-probe01.log + .result.json (read-only, exit 0, no tests):
    HEAD 8a2b6c59400866b7ff3babec3316f0c4b959988a, branch codex/so101-unbounded-queue-resource-budget,
    dirty 0, tmux dst-unbounded-queue pane %68 pid 1345571, TEST_PYTHON task venv 3.12.3,
    pytest 7.4.4, xdist/execnet absent at probe time (as the notification preflight found).
skill_delta:
  applied: git apply followups/pytest-xdist8-.../skill-delta.patch -> exactly two files, then verified
    byte-identical to the transfer copies (SKILL.md and references/test-and-acceptance.md).
  scope: only the test-and-acceptance pointer bullet plus the new "ai-station 大规模 pytest 加速" TOC
    entry/section; no other tracked skill content replaced, no unrelated work touched.
  note: CP-UQ23/CP-UQ23A were inserted above the older CP-UQ22 block in this ledger, so a plain
    `tail -1` checkpoint read still shows CP-UQ22; this entry is appended at the end.
dependency:
  resolved_in_task_owned_env: pytest-xdist 3.8.0 (origin venv/lib/python3.12/site-packages/xdist/__init__.py),
    execnet 2.1.2 (origin venv/lib/python3.12/site-packages/execnet/__init__.py), installed with
    $TEST_PYTHON -m pip install --no-cache-dir pytest-xdist==3.8.0 from the registered TUNA index.
  unchanged: pytest 7.4.4, setuptools 68.1.2, every other venv package, COLCON_TEST_PYTHONS
    ("$TEST_PYTHON" /usr/bin/python3) and all registered roots/overlays. No global or shared
    interpreter was modified.
  not_done: no suite was run to demonstrate speed, and no already-green suite was rerun; per the
    guidance the 8 pytest processes are a feedback tool only and are unrelated to product
    WorkerCount/exact-N authority.
parallel_vs_serial_plan_for_future_large_runs:
  - Shared-resource groups to isolate or run serially with a complete nodeid manifest:
    test_parallel_adaptive_integration.py (real worker processes, claims, cleanup),
    test_parallel_batch_resources.py (claim/domain preflight), test_parallel_processes.py and
    test_parallel_batch_web_control.py (sockets/ROS_DOMAIN_ID), test_text_pick_agent_e2e_process.py
    and the other text-agent launch tests (real launch/service), and this unit's
    test_parallel_measurement_default_path.py (owned cgroup subtree plus an AF_UNIX control endpoint,
    each created under a run-unique scratch root and removed on cleanup).
  - Everything else may run with -n 8 under a fresh TASK_ROOT NVMe scratch with labelled per-worker
    tempfile proofs; parallel plus serial JUnit/exit/elapsed must cover every original nodeid exactly
    once, and failures stay retained.
  - colcon: only ament_python pytest forwarding may take -n 8 after reading the real child argv; the
    ament_cmake CTest registrations (55 teleop cases) keep their own interpreter and are not
    oversubscribed. Direct pytest still does not replace the CTest/build/copied-install/provenance gates.
inferred:
  - The notice adds a testing reference only; it changes no product, plan, design or live boundary.
conclusion: NOTICE ACKNOWLEDGED, SKILL DELTA APPLIED. R1-R4 remain the primary line and stay stopped for
  Sol review.
evidence: followups/pytest-xdist8-2a146e37-.../{executor.receipt,startup-probe01.log,
  startup-probe01.result.json,skill-delta.patch,so101-dev-SKILL.md,test-and-acceptance.md},
  .agents/skills/so101-dev/{SKILL.md,references/test-and-acceptance.md}
decision: KEEP
next_experiment: NONE-AUTHORIZED (await Sol/High re-review of R1-R4)
```

```yaml
checkpoint_id: CP-UQ26
last_valid_experiment: EXP-UQ26
current_hypothesis: The user-authorized debug-only provenance amendment is implemented, the separate
  owned-cleanup E2E defect is repaired at its real cause, and the remaining offline gates are settled.
dispatch: 41326eaf-39da-45d1-a9e8-0352d304dff5 (receipt written O_EXCL first, then a read-only startup
  probe with HEAD 2654ef261433aa35927547e7ddbe0acbdea82c70, clean tree, CP-UQ25, pane %68/PID 1345571)
amendment:
  document: docs/superpowers/specs/2026-09-18-so101-source-commit-debug-only-amendment.md (new dated
    addendum; frozen design/plan/review bytes and hashes unchanged and re-listed inside it)
  superseded: runtime Git resolution and commit format/equality/cleanliness refusals in
    runtime/provenance.py, cli/text_pick_agent.py, ports+adapters/pick_place_executor.py,
    runtime/result_manifest.py, runtime/launch_composition.py, cli/mujoco_parallel_batch.py
    (PROVENANCE_SOURCE_COMMIT/DIRTY/EXTERNAL_SOURCE_COMMIT),
    so101_teleop/expert_validation/production.py (SO101_VALIDATION_SOURCE_IDENTITY,
    SO101_VALIDATION_SOURCE_COMMIT_MISMATCH), models.py SOURCE_COMMIT, operator_recovery
    RECOVERY_SOURCE_COMMIT_INVALID
  preserved: installed prefix/location equality, content inventories and byte hashes, the resource
    execution identity and exact-N budget/qualification/authority/control/lease/session/reset/cleanup
    chains, the measurement authorization chain
  debug_manifest: emitted by the setup.py final-install hook as
    share/so101_demo_py/debug-provenance-manifest.json (schema 1, kind DEBUG_INSTALL_PROVENANCE,
    authority DEBUG_ONLY_NOT_RUNTIME_AUTHORITY, install-relative paths, real byte SHA256, nullable
    commit/dirty, no timestamp/self-hash/absolute prefix); the only reader is the explicitly requested
    console script so101_debug_provenance. No runtime path reads it.
tests:
  - RED->GREEN: the new test_debug_only_provenance.py fails (4 cases, exit 1 refusals) with the
    pre-amendment commit gates stashed, and passes (10) with the amendment: a pure copied install
    outside Git runs the actual default TextPickAgent CLI bootstrap with missing/malformed/mismatched
    commit metadata, while a wrong installed prefix is still refused.
  - test_workflow_events.py: an in-run event read 6 s late is accepted; a pre-run timestamp and an
    older-than-delivery-bound record are still rejected.
  - Migrated: test_text_agent_execution_provenance.py, test_text_pick_agent_cli.py,
    test_pick_place_executor_adapter.py, test_parallel_batch_cli.py overlay cases.
owned_cleanup_defect:
  root_cause: E2ESupervisor recorded OWNED_PROCESS_CLEANUP_TIMEOUT as a primary failure as soon as a
    teardown escalation deadline fired, even when acceptance had succeeded and every owned process had
    already exited (loaded-host late callback) or exited during the SIGTERM window. Evidence: the
    failing run's own result document showed machine_accepted=true, owned_process_cleanup.complete=true,
    remaining=[], with primary_failure=OWNED_PROCESS_CLEANUP_TIMEOUT.
  repair: escalation is diagnostic; only processes that survive the SIGTERM window (i.e. need SIGKILL)
    are a cleanup failure; teardown budgets grew to 20/10/10 s; the result document carries
    cleanup_observations. RED->GREEN captured for both the late-timer case and the existing
    ignore-SIGTERM case.
gates:
  - scratch/amend-focused3.*: 222 passed (provenance, debug-only, workflow events, both E2E launch
    suites, CLI, result classification).
  - scratch/amend-adapter.*: 116 passed. scratch/amend-overlay.*: test_parallel_batch_cli.py 115 passed.
  - scratch/amend-teleop-full.RQeAKOoT: 529 passed.
  - scratch/amend-demo-shard2.1690507 (8 workers with the runner's serial-module isolation):
    manifest 3264 = serial 318 + parallel 2946, union exactly equal, no duplicates - the coverage
    requirement is met; failures in that run were the then-unmigrated cases listed above.
  - scratch/amend-installed-budget.6scbRkWz: 4 passed against the fresh copied install amend-install.
  - amend-install (built from the amended HEAD af9252675): the debug manifest covers 573 artifacts
    including modules, console scripts and share/config, and excludes itself.
  - colcon/amend-demo-colcon.*: see the readback appended by this unit.
inferred:
  - The amendment removes source-commit authority without weakening location, byte, resource or
    control checks; the E2E failure was an independent teardown-accounting defect.
conclusion: VALID offline. Stop for Sol review.
evidence: scratch/amend-*, colcon/amend-*, amend-build, amend-install,
  followups/debug-only-provenance-41326eaf-.../{executor.receipt,startup-probe01.log,
  startup-probe01.result.json}
decision: KEEP
next_experiment: NONE-AUTHORIZED (await Sol review)
```

```yaml
checkpoint_id: CP-UQ26A
last_valid_experiment: EXP-UQ26
current_hypothesis: Readback of the amendment gates; the retained colcon failures are replaced by fresh
  successful runs.
readback:
  - colcon/amend-demo-colcon.M5nQabKc: exit 0 in 552.2s, 3263 passed, 1 skipped (the whole-directory
    ament_python gate that previously failed with the owned-cleanup E2E rejection).
  - colcon/amend-teleop-colcon.*: exit 0, 100% tests passed, 0 failed out of 55 CTest registrations.
  - colcon test-result --test-result-base <TASK_ROOT>/dev-build --all: 3847 tests, 0 errors,
    0 failures, 1 skipped.
  - scratch/amend2-installed.gdbePB81: 14 passed (4 teleop installed-budget against amend2-install plus
    10 debug-only provenance).
  - amend2-install built from the clean amended HEAD 8a049b3840e99fcab4b28abeed0cdb872da4c1ed:
    provenance.py, debug_provenance.py, launch_composition.py, workflow_events.py, text_pick_agent.py
    and teleop production.py byte-match their source files, and the emitted debug manifest records that
    exact HEAD with source_dirty false.
  - colcon/rereview-f-colcon.6YKAlwzj (exit 1, 10 provenance-context failures from a dirty tree during
    that run) and colcon/rereview-h-colcon.8cRVknD1 (exit 1, 1 owned-cleanup E2E failure) remain
    retained as historical failures; they are superseded by the fresh amend-demo-colcon run above.
inferred:
  - The amendment and the teardown repair are offline-complete; no live, measurement, promotion or
    approval boundary was touched.
conclusion: VALID offline. Stop for Sol review.
evidence: colcon/amend-demo-colcon.*, colcon/amend-teleop-colcon.*, scratch/amend2-installed.*,
  amend2-build, amend2-install
decision: KEEP
next_experiment: NONE-AUTHORIZED (await Sol review)
```

```yaml
checkpoint_id: CP-UQ27
last_valid_experiment: EXP-UQ27
current_hypothesis: The second authorized amendment (prefix metadata is DEBUG-only) is implemented and
  offline-green on the full source and copied-install gates.
dispatch: 7f437570-8003-4c5b-825b-f56b0db546e5 (receipt written O_EXCL first, then a read-only probe:
  HEAD 089a081b0 clean, CP-UQ26A, pane %68/PID 1345571, handoff SHA256
  028e0e33b99bc9559f148788d048485430f6802264972c7dc21bf909480c0293; the draft-time HEAD f2a358a33 was a
  legitimate advance reconciled from this ledger, not a reset)
amendment:
  document: docs/superpowers/specs/2026-09-18-so101-prefix-metadata-debug-only-addendum.md (new dated
    addendum; sealed design/plan/review bytes and hashes unchanged)
  removed_metadata_gates: provenance strict resolve + EXECUTION_INSTALLED_PREFIX_INVALID/MISMATCH and
    EXECUTION_PACKAGE_PREFIX_UNAVAILABLE; CLI parse-time prefix gate; adapter context prefix
    presence/absolute/agreement; result-manifest prefix requirement; launch/bundle prefix mandatory
    arguments
  retained_functional: new installed_executable() resolves the real console script through the ament
    prefix, the share layout and PATH and raises only for a genuinely unavailable executable;
    get_package_share_directory keeps supplying policies, scenes and assets; the debug install
    manifest stays build-time only
  retained_independent: session/reset/evidence, control/lease/owned-scope, budget/execution identity,
    qualified content hashes, cleanup rules, fixed-profile/qualification authority and the
    expert-validation deployment location binding
tests:
  - RED->GREEN: with the previous prefix gates restored, the optional-prefix cases fail (7 failed);
    with the amendment they pass (111 in the focused suite): missing/relative/foreign/absent prefix
    metadata never refuses, ament-unavailable metadata does not block, a wrong prefix is recorded not
    enforced, and installed_executable still raises for a genuinely unavailable executable.
  - Launch argv tests pin the functional resolver; the copied-install child gate now accepts either a
    provider-approved N4 or a genuine resource refusal reason (the live observation is real, so host
    swap pressure legitimately refuses under load) while every other N stays EXACT_N_UNQUALIFIED.
gates:
  - colcon/prefix2-demo-colcon.*: exit 0, 3255 passed, 1 skipped (whole-directory serial run covering
    every original case).
  - scratch/prefix2-teleop-full.W5tnBOxH: 529 passed. colcon/prefix2-teleop-ctest.*: 0 failed out of 55.
  - colcon test-result --all (dev build base): 3847 tests, 0 errors, 0 failures, 1 skipped.
  - copied install prefix-install built from the amended HEAD: provenance.py, launch_composition.py,
    pick_place_executor.py (adapter), result_manifest.py and text_pick_agent.py byte-match source and
    the debug manifest records that exact HEAD; scratch/prefix-installed.* 4 passed.
  - colcon/prefix-demo-colcon.5POazG5u (exit 1, one bundle-shape failure in test_installed_provenance)
    is retained: the mujoco dependency executable must keep its canonical Path shape; fixed in
    8ef4cfbcb and superseded by the fresh prefix2 run.
inferred:
  - Prefix metadata no longer admits or refuses anything; functional discovery and the independent
    gates are intact.
conclusion: VALID offline. Stop for Sol re-review.
evidence: scratch/prefix*, colcon/prefix*, prefix-build, prefix-install,
  followups/debug-prefix-admission-7f437570-.../{executor.receipt,startup-probe01.log,
  startup-probe01.result.json}
decision: KEEP
next_experiment: NONE-AUTHORIZED (await Sol review)
```

```yaml
checkpoint_id: CP-UQ28
last_valid_experiment: EXP-UQ28
current_hypothesis: The four findings of the scoped Sol execution-result review (CHANGES_REQUIRED) are
  repaired offline and the final copied install matches the final runtime code bytes.
dispatch: 84e8376a-c21a-4a53-bd74-883635102594 (exclusive O_EXCL receipt first, then a read-only probe
  with shell date -Iseconds 2026-09-18T17:51:41+08:00, HEAD cd61339fb05f63eb1cf993f34d9f844ea1058268,
  clean, CP-UQ27, pane %68/PID 1345571; handoff SHA256
  25f65a59e5188eb4ed363a54b1ebb85eb70a9da68da9c18994e5f695103b5ac1 and review SHA256
  c99732ff58535881689a5e18b2980a564dd7c80fd9cb57a15fbe47dd80ae05e6 = the required value)
corrections:
  - CP-UQ27's claim that source and copied install were byte-equal was FALSE at that HEAD: the copied
    provenance.py was built before commit 8ef4cfbcb changed it. The four-case installed run
    (scratch/prefix-installed.EWr8oAVG) therefore did not qualify the final source. Retained as history;
    superseded by the fresh copy below.
  - CP-UQ27's aggregate count 3847 was wrong; the actual colcon test-result aggregate for that build base
    was 3839 (0 errors, 0 failures, 1 skipped).
  - The earlier 7f437570 probe JSON said 16:00 while its receipt/probe file metadata is ~16:30; that
    self-filled timestamp was not independently verified wall time. This unit's probe takes its time
    from a real `date -Iseconds` inside the probe log and records it verbatim.
  - Progress correction: the 7f437570 patch had accidentally removed nine independent CLI regression
    cases while trimming the prefix negatives; they are restored unchanged (see repairs).
repairs:
  - "P1 runtime Git removed: observed_source_commit() is declared-metadata-only and runs no subprocess;
    the Git observation moved to observed_source_commit_from_git/observed_source_dirty_from_git, used
    only by the build/install debug-manifest generator. The bundle input _source_commit() is
    declared/unknown only. Regression: test_runtime_execution_chain_never_runs_git patches
    subprocess.run to fail on any git argv across the CLI context, the identity resolver, the installed
    bundle and the debug manifest generator (the only place a git call is then allowed and observed)."
  - "P2 debug inspection nonblocking: _verified_artifact wraps resolve/stat/open/read in one guarded
    block, and the declared-prefix fallback guards resolve; permission, race, malformed or unresolvable
    metadata yields None/unknown instead of propagating. Regression:
    test_debug_artifact_read_failures_are_nonblocking covers PermissionError/FileNotFoundError/OSError/
    ValueError plus malformed and unresolvable prefix values while session/reset/evidence stay valid."
  - "P2 nine independent CLI cases restored from 089a081b0 (2 partial-execute, 3 workflow-config,
    1 workflow stdout/stderr, 2 confirmation-bypass, 1 wrong-backend); the legitimate old prefix
    negatives were replaced by nonblocking cases rather than deleted, and the mapping is recorded in the
    test file's parametrized prefix test."
  - "Copied-provider contract coverage: test_copied_default_provider_is_positive_and_fail_closed runs the
    copied install's own default composer through a hermetic low-level host port and proves both an
    admitted N4 (profile/qualification match) and fail-closed refusals (BACKGROUND_ENVELOPE_EXCEEDED,
    RAM_HEADROOM); no admission factory, resolver or global gate is mocked."
  - "Final copy: progress-install built from runtime-code HEAD ff8a1479fe5eeb000445f6a3f9d8f945723dd8a4
    (new unique immutable prefix; prefix-install and all older prefixes/A0/auth/evidence untouched, no
    symlink). Verified byte equality of provenance.py, debug_provenance.py, launch_composition.py,
    text_pick_agent.py, the pick_place adapter and teleop production.py plus every installed launch file,
    and the debug manifest records that commit with source_dirty false. Later commits are test-only:
    `git diff --stat ff8a1479f..HEAD -- src/so101_demo_py/src src/so101_teleop/so101_teleop
    src/so101_demo_py/setup.py` is empty, so the installed runtime bytes still equal HEAD."
red_green:
  - RED: with the previous provenance.py restored, test_runtime_execution_chain_never_runs_git fails with
    "runtime Git subprocess: ['git','-C',<prefix>,'rev-parse','HEAD']" and
    test_debug_artifact_read_failures_are_nonblocking fails with PermissionError.
  - GREEN: scratch/progress-green2.CgmfhjOy 89 passed; scratch/progress-restore1.8O7voGBT 60 passed
    after the nine restorations; scratch/progress-installed.gJOfu2pI 4 passed;
    scratch/progress-provider.GVuXFm7p 7 passed.
gates:
  - scratch/progress-teleop-full.5WPSKs2J: 532 passed (529 + 3 copied-provider contract cases).
  - colcon/progress-teleop-ctest.*: 100% tests passed, 0 failed out of 55.
  - colcon/progress-demo-colcon.ckovTci1 (exit 1) retained: the runtime bundle no longer probes Git while
    test_installed_provenance still expected a Git HEAD; fixed in the following test-only commit.
  - colcon/progress2-demo-colcon.*: final ordinary demo gate, see the readback appended below.
inferred:
  - Runtime no longer depends on Git or on prefix metadata; debug inspection is diagnostic-only while
    functional discovery and the independent gates stay fail-closed.
conclusion: VALID offline pending the final gate readback. Stop for Sol re-review.
evidence: scratch/progress-*, colcon/progress-*, progress-build, progress-install,
  followups/repair-debug-progress-84e8376a-.../{executor.receipt,startup-probe01.log,
  startup-probe01.result.json}
decision: KEEP
next_experiment: NONE-AUTHORIZED (await Sol review)
```

```yaml
checkpoint_id: CP-UQ28A
last_valid_experiment: EXP-UQ28
current_hypothesis: Final gate readback for the four-finding repair unit.
readback:
  - colcon/progress2-demo-colcon.VD8SYoJT: exit 0 in 550.3s, 3266 passed, 1 skipped - the final
    ordinary demo gate on the repaired runtime code (3255 + 9 restored independent cases + 2 new
    metadata/Git regressions).
  - colcon test-result --test-result-base <TASK_ROOT>/dev-build --all: 3853 tests, 0 errors,
    0 failures, 1 skipped.
  - scratch/progress-teleop-full.5WPSKs2J: 532 passed; colcon/progress-teleop-ctest.* 0 failed of 55.
  - progress-install (runtime-code HEAD ff8a1479fe5eeb000445f6a3f9d8f945723dd8a4): all checked module
    bytes and all eight installed launch files byte-match the frozen source; the debug manifest records
    that commit; later commits are test-only and leave the installed runtime bytes identical
    (empty diff over src/so101_demo_py/src, src/so101_teleop/so101_teleop and setup.py).
  - Runtime-code HEAD to cite: ff8a1479fe5eeb000445f6a3f9d8f945723dd8a4; documentation/ledger HEAD is
    recorded by this commit.
conclusion: VALID offline. Stop for Sol re-review, no self-approval.
evidence: colcon/progress2-demo-colcon.*, scratch/progress-*, progress-install
decision: KEEP
next_experiment: NONE-AUTHORIZED (await Sol review)
```

```yaml
checkpoint_id: CP-UQ29
last_valid_experiment: EXP-UQ29
current_hypothesis: The P2 copied-CLI acceptance gap is repaired with the real installed entrypoint, and
  subsequent task pytest runs default to 8 audited xdist workers.
dispatch: 8eef27e3-d4a0-4089-b3a5-9efc6df8c308 (exclusive O_EXCL receipt first, then a read-only probe
  with shell date -Iseconds 2026-09-18T18:54:25+08:00, HEAD 3fa4a3aa22f4d0b1a5b4b44475e494554a828c0c
  clean, CP-UQ28A, pane %68/PID 1345571, handoff SHA256
  4832c94069d8952dd59b6eb858283a0cff55a7d4e0d1d1fd124d1f52880ce38d; host 24 cores / 26.5 GiB
  available / loadavg 0.23)
corrections:
  - The previous `test_debug_only_provenance.py` copied-install case wrote a fake
    `#!/bin/sh exit 1` entrypoint and injected a hermetic agent; it proved module admission only and is
    no longer presented as copied console/default-composition acceptance (the fake stub is gone and the
    test is re-scoped).
  - "Evidence: colcon/xdist8-demo-colcon.venD07h2 exit 1, 9 failed / 3265 passed with the real child
    argv forwarding `test -n 8` - all nine are in test_parallel_batch_resources.py, the shared
    claim/domain probe module, which is concrete evidence that this module must stay serial (already in
    tools/so101_pytest_gate.py SERIAL_MODULES)."
repairs:
  - "Real copied-entrypoint acceptance: new src/so101_demo_py/test/test_copied_installed_entrypoint.py
    runs the immutable progress-install console script as a subprocess with the copied module origins
    and asserts (a) the real installed entrypoint is an EASY-INSTALL console script whose SHA equals the
    debug manifest entry, (b) the default bootstrap composes from the copied bytes, persists provenance
    with module/entrypoint/prefix observations and source_commit null/UNKNOWN, and stops only at
    PLANNER_CHAIN_FAILED (the unauthorized live provider gate), (c) invalid session/reset/evidence
    context fails closed with the specific codes and no provenance, (d) launch executable/launch files/
    policy/scene are functionally discovered while a genuinely empty prefix fails with
    "installed executable is unavailable". No agent, admission factory, provider, resolver, default
    factory or global gate is injected."
  - "Runtime bytes unchanged since ff8a1479f (git diff over src/so101_demo_py/src,
    src/so101_teleop/so101_teleop and setup.py is empty), so the immutable progress-install prefix is
    reused after re-verifying the module bytes; no new prefix, no symlink, old prefixes untouched."
  - "pytest default 8 workers: task-owned tools/test-gate.zsh sets SO101_PYTEST_WORKERS=8 and adds
    `-n 8` unless the caller passes -n/-p no:xdist/--collect-only, recording actual_workers in
    workers.txt; the demo conftest writes a per-worker proof (worker, interpreter, prefix, tempdir,
    expected) inside the run scratch and fails if a worker escaped TMPDIR. No global addopts change."
  - "Audited parallel/serial runner: task-owned tools/pytest-parallel.zsh derives the serial group from
    tools/so101_pytest_gate.py SERIAL_MODULES, collects the full nodeid manifest, runs the serial group
    serially and the remainder with -n 8, and asserts an empty intersection and an exactly equal union."
gates:
  - "scratch/xdist8-demo.1820566: coverage_exact true, manifest 3275 = serial 318 + parallel 2957,
    intersection 0; serial 318 passed, parallel 2956 passed / 1 skipped; workers 8."
  - "scratch/xdist8-teleop3.1844980: coverage_exact true, manifest 532 = parallel 532, intersection 0,
    532 passed in 18.6s with 8 workers (48.5s serial)."
  - "colcon/xdist8-demo-serial.8ftQI8MP: exit 0 in 552.3s, 3274 passed, 1 skipped - the required
    ament_python package gate (serial, because the -n 8 evidence above shows the resource-probe module
    must not be parallelised)."
  - "colcon test-result --all (dev build base): 3861 tests, 0 errors, 0 failures, 1 skipped."
  - "scratch/xdist8-copied-accept3.CNNXqFHo: 19 passed (12 new copied-entrypoint acceptance cases plus
    the re-scoped module-admission cases) at 8 workers."
remaining_unauthorized_gate:
  - The copied entrypoint's preview/execute completion needs the live DeepSeek/Ollama provider and, for
    motion, the ROS/MoveIt stack; both are outside this authorization. The acceptance therefore asserts
    the default composition up to that precise gate (PLANNER_CHAIN_FAILED) instead of claiming a
    completed non-motion CLI run.
inferred:
  - Copied console/default composition and launch resources are now genuinely exercised; the four
    previously closed items stay closed.
conclusion: VALID offline. Stop for Sol execution-result review.
evidence: scratch/xdist8-*, colcon/xdist8-*, tools/{test-gate.zsh,pytest-parallel.zsh},
  followups/copied-cli-xdist8-8eef27e3-.../{executor.receipt,startup-probe01.log,
  startup-probe01.result.json}
decision: KEEP
next_experiment: NONE-AUTHORIZED (await Sol review)
```

```yaml
checkpoint_id: CP-UQ30
last_valid_experiment: EXP-UQ30
current_hypothesis: Mainline continuation after CP-UQ29 - runner scheduling repair, allocator cmdline
  robustness, Task 6 capability-probe selection, and the Task12 freeze copy.
dispatch: 9d418aae-8e1e-430c-bb07-1f26070fd8ee (exclusive O_EXCL receipt, then a read-only probe with
  shell date -Iseconds 2026-09-18T20:01:49+08:00, HEAD 376b24b66891cfb6b0055f0ca412dda85dc1bd7e clean,
  CP-UQ29, pane %68/PID 1345571; handoff SHA256
  bfe525358e817172f9db8cfab5afa83bb5c48af4fe692c207e8f283114a75da1; 24 cores / 26.5 GiB / load 0.14)
planning:
  - The plan's 17 tasks Task0-Task16 are restored as the working matrix (Stage A = 0-11 plus 13/14/15
    offline; Stage B = 12; Stage C = 13; Stage D = 14; Stage E = 15 plus the Task16 handoff). Per-task
    status/next/approval is carried in this checkpoint; a receipt or a source-GREEN run is never whole-
    task or live completion.
  - Experiments are recorded PLANNED before bounded work and closed with observed results; external
    Sol/Astra reviews are the orchestrator's responsibility, are not a DST task and are not a waiting
    condition for the remaining authorized offline work.
runner_repair:
  - "RED: the task wrapper treated ANY `-p` as an xdist disable, so `-p no:cacheprovider` silently ran
    one worker and an explicit `-n 4` was recorded as actual_workers=1. GREEN: only an explicit
    xdist-disable/collect-only or a real worker argument suppresses the default; `-p no:cacheprovider`
    now runs 8 workers (scratch/xdist8-policy-p.*: actual_workers=8, 8 worker proofs) and `-n 4`
    records actual_workers=4 without adding a second -n."
  - "Shared-resource modules are the minimum exact serial set (from tools/so101_pytest_gate.py
    SERIAL_MODULES): measured evidence is 25 failures in test_parallel_batch_resources.py at -n 8
    (claim/ROS-domain probes); the wrapper now pins exactly those nodeids to one worker with
    serial_override recorded (scratch/xdist8-serialmod.EekF4gcm: 145 passed at actual_workers=1) and
    delegates whole-directory targets to the audited split runner instead of serialising the package."
  - "tools/pytest-parallel.zsh hardened: mktemp-created and run-index-registered run dir, per-phase
    labelled exact-interpreter tempfile proofs, real argv/result/exit/elapsed per phase, collect
    pipeline exit checked, extra args forwarded, and nodeid identity preserved (package-root relative
    dotted module path, no stem collapse)."
allocator_and_task6:
  - "Allocator: a same-UID process with an oversized (>4 KiB) cmdline made the ROS-domain probe fail
    closed (PROC_METADATA_UNVERIFIABLE), flaking test_external_cleanup_retires_only_owned_worker_;
    the identity is still stat/comm verified and the high-recall classifier keeps its conservative
    candidate path plus environ inspection, so the cmdline is classified instead of refused.
    RED->GREEN: scratch/xdist8-cmdline-red.* (ValueError: proc cmdline too large) ->
    scratch/xdist8-cmdline-green2.* (module green)."
  - "Task 6 narrow fix: the measurement CLI's default capability probe now receives the same
    --cgroup-parent/--device-index selection the MeasurementSession owns; RED (probe called with {})
    -> GREEN (scratch/xdist8-cgprobe-green.tce7GOyp.*: 9 passed). No real GPU/ROS measurement started."
gates:
  - "scratch/xdist8-demo3.*: serial group 319 passed; parallel group 2956 passed / 1 skipped with one
    intended failure - test_runtime_bytes_of_the_copied_prefix_match_the_frozen_source, which correctly
    refuses because runtime code changed after the ff8a1479f copy. That is the Task12 trigger, not a
    regression."
  - "colcon/xdist8-demo-serial.8ftQI8MP remains the last full serial package gate (3274 passed); the
    package-level 8-worker gate is provided by the audited split runner above."
next_commands:
  - "Task12 freeze: build the new unique immutable production copied install (freeze-build/freeze-install,
    started), verify six modules/eight launch bytes/entrypoint shebang/config carriers/assets/dependency
    origins against the frozen clean code HEAD, emit the debug manifest, and register the versioned
    audit/binding."
  - "Then rerun the affected source/package/Web/copied gates against that freeze and continue the
    remaining Stage A offline units before any live boundary."
real_approval_gates:
  - Owned recovery/apply/Web refresh/deployment window; Stage C sealed candidate authorization; exact-N
    profile-SHA operator promotion; owned live Chrome window. Each needs its own explicit approval and
    the exact objects/IDs/hashes are reported at that gate; offline previews only.
inferred:
  - Scheduling, allocator robustness and the Task 6 probe are repaired with genuine RED->GREEN; the
    remaining work is the Task12 freeze copy and the unperformed live boundaries.
conclusion: OFFLINE WORK CONTINUES (no wait on external review).
evidence: scratch/xdist8-*, colcon/xdist8-*, tools/{test-gate.zsh,pytest-parallel.zsh},
  followups/mainline-continuation-9d418aae-.../{executor.receipt,startup-probe01.log,
  startup-probe01.result.json}
decision: KEEP
next_experiment: EXP-UQ31 Task12 freeze copy verification
```

```yaml
checkpoint_id: CP-UQ30A
last_valid_experiment: EXP-UQ30
current_hypothesis: Task12 freeze copy built, byte-verified and bound; audited demo gate re-run on it.
readback:
  - Freeze copy freeze-install built from clean runtime code HEAD 6e68d0f51be4e6bf10b6f838c8f1cbd41b267240
    (new unique immutable prefix; progress-install and all older prefixes/A0/bindings untouched, no
    symlink). Verified: six module bytes match source, all eight installed launch files match, the
    console entrypoint exists with shebang #!/usr/bin/python3, config carrier
    (config/mujoco/parallel_batch_v2.yaml) and asset (assets/mujoco/scene.xml) present, and the debug
    manifest records the frozen HEAD with source_dirty false and 573 artifacts.
  - bindings/freeze-project-provenance.json registers that freeze (source commit, install prefix, module
    origins, six core file SHA256 values, entrypoint SHA, debug manifest path/commit, DEBUG_ONLY
    authority). This is not a qualification record.
  - Copied acceptance gate re-pointed to the freeze: scratch/freeze-installed-gates2.4MZkbEDW 8 passed
    at 8 workers (the pre-freeze run correctly failed the byte guard, which is why the freeze was built).
  - The historical production A0/binding (a812...) is not reused; runtime bytes changed with the runner,
    allocator and Task 6 repairs, so a future production freeze/qualification must be new.
task_matrix:
  - "Stage A (offline): Task0-11 and 13/14/15 implemented with green offline evidence; Task12 copy is
    now the new freeze above; Task16 handoff facts are the packet described in this checkpoint."
  - "Stage B (own recovery/Web refresh) / Stage C (measurement) / Stage D (promotion, deployment) /
    Stage E (live Chrome): unperformed and unauthorized. Every actual exact-N budget remains
    NOT_MEASURED; N without a measured qualification stays disabled with a reason, no N downgrade and no
    cross-N extrapolation."
inferred:
  - Offline mainline work is complete for this unit; the remaining steps are the explicit live/approval
    boundaries listed in CP-UQ30, each with its own exact authorization.
conclusion: OFFLINE WORK CONTINUES; live boundaries require explicit approval objects.
evidence: freeze-build, freeze-install, bindings/freeze-project-provenance.json,
  scratch/freeze-installed-gates2.*, scratch/xdist8-demo4.*
decision: KEEP
next_experiment: EXP-UQ31 remaining authorized offline units / approval-gated live stages
```

```yaml
checkpoint_id: CP-UQ31
last_valid_experiment: EXP-UQ31
current_hypothesis: Queued correction consumed - no blind waits, every run artefact inside the
  registered root, exact-nodeid serial isolation, and continued Task12 freeze verification.
dispatch: accf0ca1-4649-4d46-b0f8-bc984b29141b (queued correction continuing 9d418aae; exclusive
  O_EXCL receipt plus a probe with shell date -Iseconds 2026-09-18T20:22:08+08:00, HEAD
  1235a6592ca1f56111599445915f6c43f1a1acf5 clean, CP-UQ30A, pane %68/PID 1345571, handoff SHA256
  52fb8109759944d4c9e82c2f9f5848190da14da65367fe6d503b21eb8fd7cd64). The prior long sleep was not
  interrupted; it completed naturally before this correction was consumed.
corrections:
  - "Waiting policy: no further blind multi-minute sleep. Every subsequent wait is a bounded condition
    check (10 s interval, single wait <= 60 s) against a run-log completion marker with the observed
    progress reported; the teleop and web gates below were polled that way."
  - "Log locations: all new run logs, argv, JUnit, TMP and per-exact-interpreter/worker proofs live in
    their run directory under the registered TASK_ROOT. The one pre-existing /tmp run log
    (/tmp/xdist8-demo2.log) was copied byte-identically into its own run root
    (scratch/xdist8-demo2.V70OphOR/mirrored-tmp-xdist8-demo2.log) with a hash/mtime provenance file
    (mirror-provenance.txt); the original was retained, not overwritten."
  - "Exact-nodeid serial isolation replaces module-level over-serialisation: measured evidence is
    test_expert_validation_e2e_installed_port.py::test_adaptive_helper_handshake_and_sigint_cleanup
    timing out after 10 s under 8 workers (subprocess.TimeoutExpired on the adaptive helper handshake).
    tools/serial-nodeids.txt lists it and the runner deselects exactly that manifest nodeid from the
    parallel phase using the manifest's own path form."
gates:
  - "scratch/freeze-teleop3.j5DEsMAD: coverage_exact true, manifest 532 = serial 1 + parallel 531,
    intersection 0, serial 1 passed, parallel 531 passed, workers 8 (0.38 s serial, 18.60 s parallel)."
  - "scratch/freeze-teleop-installed.Qfvj1KMK: 7 passed at 8 workers against the Task12 freeze copy
    (the teleop installed-budget suite now points at freeze-install)."
  - "browser/freeze-web-unit.*: web unit gate exit 0, polled with bounded condition waits."
  - "scratch/xdist8-demo4.cafOc9zm (previous unit): audited 8-worker demo coverage exact,
    3277 = serial 319 + parallel 2958."
task12:
  - "freeze-install verified against the frozen clean tree: six modules, eight launch files, entrypoint
    (#!/usr/bin/python3) and config/asset carriers byte-match; the debug manifest records that HEAD with
    source_dirty false; bindings/freeze-project-provenance.json registers the freeze and its core file
    hashes. The copied acceptance gate is re-pointed to the freeze: 8 passed."
real_approval_gates:
  - Owned recovery/apply and Web refresh/deployment window (Stage B); Stage C sealed candidate
    authorization (require_measurement_capabilities refuses here: the delegated cgroup exposes no cpu
    controller); exact-N profile-SHA operator promotion and deployment (Stage D); owned live Chrome
    window (Stage E). Each needs its own explicit approval object; offline preparation only.
inferred:
  - The scheduling corrections are in place with genuine evidence and the remaining offline sweep
    continues against the Task12 freeze; the external Sol/Astra reviews are the orchestrator's, not a
    DST wait condition.
conclusion: OFFLINE MAINLINE CONTINUES; live stages require their explicit approval objects.
evidence: scratch/freeze-teleop3.*, scratch/freeze-teleop-installed.*, browser/freeze-web-unit.*,
  scratch/xdist8-demo2.V70OphOR/mirror-provenance.txt, tools/serial-nodeids.txt,
  followups/mainline-wait-correction-accf0ca1-.../{executor.receipt,receipt-probe01.log,
  receipt-probe01.result.json}
decision: KEEP
next_experiment: EXP-UQ32 remaining Stage A offline sweep and Web/Bun/installed gates on freeze-install
```

```yaml
checkpoint_id: CP-UQ32
last_valid_experiment: EXP-UQ32
current_hypothesis: The review's three P2s are closed with genuine evidence, the real ament_python
  8-worker package gate is green, and the Stage C cgroup/NVML capability has a raw probe plus a
  concrete, sudo-free fix path.
dispatch: 23541f5a-3c38-433d-85c2-3b0001bd535a (user authorization text quoted in the handoff:
  "发送修复指令。并要求dst继续完成B-E。授权机制执行。"; exclusive O_EXCL receipt plus startup probe with shell
  date -Iseconds 2026-09-18T20:44:05+08:00, HEAD 93fc681aa4021a80b3964e7639c81d2d99a2a6b4 clean,
  CP-UQ31, pane %68/PID 1345571, handoff SHA 0cd6b59c..., review SHA 7cedb19b... = required value)
p2_closure:
  - "Runner cross-package/audit: RED = the demo-scoped run mixed the foreign teleop nodeid into its
    serial phase and the mapping failure did not stop the script (scratch/red-foreign-nodeid.*).
    GREEN = serial nodeids are resolved against THIS run's manifest (foreign entries skipped and
    recorded), the mapping exits fail-closed, collect forwards extra args with argv/exit recorded,
    coverage is a multiset over full nested nodeid identity, and every phase stores argv/result/exit/
    elapsed plus exact-interpreter and worker proofs. Evidence: scratch/green2-foreign.iizZnh2r
    (foreign skipped, coverage_exact true), scratch/green4-teleop.g1GE0TfA (532 = serial 1 + parallel
    531, intersection 0), scratch/xdist8-demo4.cafOc9zm (3277 = 319 + 2958)."
  - "Real ament_python package gate: tools/pkg8-gate.zsh runs two genuine colcon invocations whose real
    child argv was probed (colcon forwards -n and --deselect): parallel 8 workers with 319 deselect
    tokens for the minimal serial set, then serial for the five serial module paths.
    scratch/pkg8demo2.G7s3ZfXT: coverage_exact true, manifest 3277 = parallel 2958 + serial 319,
    intersection 0, PARALLEL_RC=0 SERIAL_RC=0 COVERAGE_RC=0 - this replaces the old full-serial 3274
    package run without serialising the whole package and without using the direct runner as the
    package gate."
  - "Ledger current fields refreshed (current_commit, latest_checkpoint CP-UQ31, next_experiment
    EXP-UQ32) and the retired socket-relocation question annotated, with the original entries kept
    (commit b11d48b54)."
capability_probe:
  - "Raw probe run: scratch/capability-probe.plqC8Jzn/raw-probe.log (shell date 2026-09-18T21:12:48+08:00)."
  - "Chain: user@1000.service controllers=[cpu memory pids] subtree_control=[cpu memory pids]; app.slice
    controllers=[cpu memory pids] subtree_control=[memory pids]; our own dsh-subprocess-*.scope
    controllers=[memory pids] subtree_control=[] (no cpu controller delegated into it)."
  - "Attempts inside the task-owned scope (no sudo): +cpu -> ENOENT (controller not present in this
    scope's cgroup.controllers); +memory -> EBUSY (the scope has member processes, so the no-internal-
    process rule blocks enabling); +pids -> OK. The child cgroup therefore exposes only [pids]:
    cpu.max/memory.max do not exist and the measurement's OwnedCgroupV2.require_delegated(cpu,memory)
    correctly refuses. NVML whole-device read succeeded (gpu_total/used/free bytes recorded)."
  - "Sudo-free fix path for Stage C: create a fresh delegated scope for the measurement with
    `systemd-run --user --scope -p Delegate=yes -- <measurement console …>`; verified available
    (/usr/bin/systemd-run; `systemd-run --user --scope --quiet -p Delegate=yes -- true` returned OK), so
    the parent->child cpu+memory delegation can be established without touching global/shared config."
authorization_record:
  - "Latest user authorization grants the task-owned B-E windows in scope: B owned recovery/Web refresh,
    C finite candidate measurement, D deployment execution window, E owned Chrome window. The product
    content gates are unchanged: each real exact-N/profile-SHA issuance still needs its own operator
    approval object, Stage C needs its sealed authorization, Stage E needs the N1/Nx signature; no
    APPROVED record is pre-written and no issuer/trust-root rule is altered."
inferred:
  - Scheduling, package-gate and ledger P2s are closed; Stage C has raw capability evidence plus a
    concrete sudo-free delegation path, and Stages B/D/E proceed under the granted windows with their
    unchanged content gates.
conclusion: OFFLINE/AUTHORIZED MAINLINE CONTINUES; product content gates remain object-bound.
evidence: scratch/pkg8demo2.G7s3ZfXT/*, scratch/green4-teleop.*, scratch/green2-foreign.*,
  scratch/capability-probe.plqC8Jzn/raw-probe.log, tools/{pytest-parallel.zsh,pkg8-gate.zsh}
decision: KEEP
next_experiment: EXP-UQ33 Stage C measurement inside a fresh delegated scope; Stage B freeze/production
  binding; Stage D per-N approval packets; Stage E owned Chrome once N1/Nx are signed
```

```yaml
checkpoint_id: CP-UQ33
last_valid_experiment: EXP-UQ33
current_hypothesis: Stage C cgroup delegation is attempted through three sudo-free mechanisms; the
  boundary is now precisely traced and the remaining offline mainline work continues.
capability_attempts:
  - "1. In-scope enablement (scratch/capability-probe.plqC8Jzn/raw-probe.log, 21:12:48+08:00): our own
    dsh scope has controllers [memory pids]; +cpu -> ENOENT, +memory -> EBUSY (member processes),
    +pids -> OK; child exposes [pids] only."
  - "2. Fresh delegated scope (scratch/delegated-scope.XUBGMk1U, scratch/delegated-scope2.RM6ue8q4):
    systemd-run --user --scope -p Delegate=yes [-p MemoryAccounting/CPUAccounting/TasksAccounting]
    gives controllers [cpu memory pids]; +cpu -> OK (child cpu.max=100000 100000 read back) but +memory
    -> FAILED, so the child exposes [cpu pids] with no memory.max."
  - "3. Transient user service (scratch/delegated-service.eRRg1feJ, scratch/delegated-service2.*):
    systemd-run --user --pipe --wait --collect --unit=... -p Delegate=yes -p MemoryAccounting=yes ...
    leaves the unit's cgroup.subtree_control EMPTY; the child cgroup gets [] and even cpu.max is not
    writable."
finding:
  - "Parent->child cpu+memory delegation cannot be established from inside a running unit in this
    environment: enabling memory in subtree_control is blocked while the unit has member processes, and
    a transient unit's subtree_control is not pre-enabled by the user manager. The measurement
    session's OwnedCgroupV2.require_delegated(cpu, memory) therefore refuses correctly
    (MEASUREMENT_CAPABILITY_MISSING: cgroup_controllers) - this is a real capability gate, not a code
    defect. NVML whole-device read works (gpu_total 17094934528, used 1019609088, free 16075325440)."
  - "Handling path (no fake proof, no sudo, no global change): either (a) the orchestrator/operator
    provisions a user unit whose cgroup.subtree_control is enabled by the manager before the payload
    starts (or a session scope with controllers pre-enabled), or (b) Stage C is run with an explicit
    decision to treat memory as a whole-host guard (the design already requires whole-host MemAvailable
    >= 20% and abort thresholds) while cpu quota alone is cgroup-enforced from the delegated [cpu]
    controller. Both are approval/capability objects; the measurement authorization cannot be
    self-signed and the existing sealed mechanism is unchanged."
continued_work:
  - "Stage B offline preparation is in place: freeze-install + bindings/freeze-project-provenance.json;
    the versioned production copy/A0/audit/binding for the frozen HEAD is the next artifact, followed by
    the owned recovery/Web refresh window with fresh PID/domain/store/fence/lease readback."
  - "Stages B-E windows are GRANTED IN SCOPE by the latest user authorization; each product content gate
    (exact-N/profile-SHA operator approval, Stage C sealed authorization, Stage E N1/Nx signature)
    remains object-bound and is requested through the existing issuer interfaces, never fabricated."
inferred:
  - The scheduling/package/ledger P2s are closed; Stage C's mechanical blocker is precisely identified
    with three raw traces, and all other authorized offline work continues without waiting for review.
conclusion: AUTHORIZED MAINLINE CONTINUES; Stage C needs the delegated-unit/capability object.
evidence: scratch/capability-probe.plqC8Jzn, scratch/delegated-scope.*, scratch/delegated-service*,
  scratch/pkg8demo2.G7s3ZfXT, bindings/freeze-project-provenance.json, freeze-install
decision: KEEP
next_experiment: EXP-UQ34 Stage B production copy/A0/binding and owned Web refresh; Stage C under a
  manager-delegated unit once provisioned; Stage D per-N approval packets
```

```yaml
checkpoint_id: CP-UQ34
last_valid_experiment: EXP-UQ34
current_hypothesis: Task12 versioned production freeze artifacts (A0 + binding) are produced and
  byte-verified; the remaining Stage B/C/D/E objects are enumerated with exact commands.
artifacts:
  - "bindings/production-freeze-a0.json (0600): schema-2 FullByteAudit over the freeze-install prefix,
    943 actual installed files with their raw SHA256, origins for so101_demo_py / so101_teleop /
    so101_mujoco_support, source_clean true, A0 sha256 ac7993e2049c6c4f... ."
  - "bindings/production-freeze-binding.json (0600): kind PRODUCTION_FROZEN_BINDING, install_kind
    production_frozen_copy, install_prefix freeze-install, a0_path/a0_sha256, 943 inventory files,
    module origins, and the frozen tree commit (62cc630c3f18 at audit time)."
  - "Verification: all six runtime modules and all eight installed launch files byte-match the frozen
    source; the debug manifest inside the prefix records its own build HEAD 6e68d0f51. Runtime-code HEAD
    is 528ccb44f; 6e68d0f51 and 62cc630c3f18 are docs-only deltas from it, so the installed bytes equal
    the runtime code (an empty git diff over src/so101_demo_py/src, src/so101_teleop/so101_teleop and
    setup.py)."
  - "This freeze is a versioned task-owned production copy; it does not overwrite or reuse the older
    production prefix / A0 (a812...) / bindings and is explicitly NOT a qualification record."
next_objects:
  - "Stage B owned window: task-owned Web refresh/start using this freeze's copied launcher and the
    audited Web dist, with PID/domain/store/fence/lease/URL/served-bytes readback; then the owned
    recovery apply only if a fresh ownership check requires it."
  - "Stage C: measurement console inside a manager-delegated unit (subtree_control pre-enabled) or an
    explicit decision to enforce cpu alone from the delegated [cpu] controller with memory as the
    whole-host guard; N1..8 sealed authorizations per the plan, results recorded as resource_qualified
    and product_qualification_passed separately."
  - "Stage D: per-N candidate packets (P/R/Q/B/location hashes) submitted for the real operator approval
    objects; no APPROVED record is pre-written. Stage E: owned Chrome once N1/Nx are signed."
inferred:
  - The offline/production-freeze side of Task12 is complete with immutable, byte-audited artifacts; all
    remaining steps are object-bound windows, not review waits.
conclusion: AUTHORIZED MAINLINE CONTINUES; remaining work is object-bound (delegated unit, operator
  approvals, owned windows).
evidence: bindings/production-freeze-{a0,binding}.json, freeze-install,
  scratch/capability-probe.plqC8Jzn, scratch/delegated-*, scratch/pkg8demo2.G7s3ZfXT
decision: KEEP
next_experiment: EXP-UQ35 Stage B owned Web refresh on the production freeze; Stage C delegated-unit
  measurement; Stage D approval packets
```

```yaml
checkpoint_id: CP-UQ35
last_valid_experiment: EXP-UQ35
current_hypothesis: Stage B ownership inventory is clean; the owned Web refresh can start on the
  production freeze without pausing any service.
goal: goal-d30193b8-a2e5-495d-b6c7-6879782448ac (user /goal 完成 B-E; round 1)
ownership_probe:
  - "scratch/stageB-ownership.80PNvl8p/ownership.log (shell date 2026-09-18T21:16:02+08:00): no listeners
    on 8000/8001/11434, no task-owned uvicorn/expert-validation process, no task-owned Chrome, tmux has
    only the unrelated codex session plus our dst-unbounded-queue session. Nothing needs pausing and no
    foreign stack is running that could compete with the owned window."
  - "ProductionRuntimeLayout.discover() under the plain dev-overlay environment refuses at _required_file
    (the points/executables are supplied by the task SO101_VALIDATION_* environment), which is the
    expected discovery contract: Stage B must discover the layout with the registered task env pointed at
    the production freeze prefix, not the dev overlay."
next_commands:
  - "Stage B: export the SO101_VALIDATION_* layout variables against freeze-install (points, parallel v2
    config, coordinator/cleanup executables, provenance binding, yolo/grounded paths, broker image),
    confirm ProductionRuntimeLayout.discover succeeds, then start the owned Web (copied launcher + audited
    Web dist) and read back PID/domain/store/fence/lease/URL/served bytes before marking it online."
  - "Stage C: re-run the capability probe inside a manager-delegated unit (or take the documented cpu-only
    quota + whole-host memory guard decision), then the sealed N1 calibration."
inferred:
  - Stage B has a clean owned window; the remaining steps are object-bound as recorded in CP-UQ33/34.
conclusion: GOAL ROUND 1 - ownership inventory complete, Stage B start commands prepared.
evidence: scratch/stageB-ownership.80PNvl8p/ownership.log
decision: KEEP
next_experiment: EXP-UQ36 Stage B layout discovery + owned Web start on the production freeze
```

```yaml
checkpoint_id: CP-UQ36
last_valid_experiment: EXP-UQ36
current_hypothesis: The production-freeze layout discovers correctly with copied module origins; the
  owned Web start is the next action.
goal: goal-d30193b8-a2e5-495d-b6c7-6879782448ac (round 2)
layout_discovery:
  - "scratch/stageB-layout.wXew44Ra/layout.log: first attempt under the dev overlay refused with
    SO101_VALIDATION_INSTALLED_MODULE_INVALID because the running so101_teleop resolved from the dev
    build tree, not from the freeze prefix - the discovery contract requires copied module origins."
  - "scratch/stageB-layout2.U0OFWcl6/layout.log: with PYTHONPATH + AMENT_PREFIX_PATH pointed at
    freeze-install and SO101_DISABLE_KIMI_EDITABLE_FINDER=1, discover() succeeds (DISCOVERY_RC=0):
    module origins are freeze-install/.../site-packages/so101_teleop and .../so101_demo;
    source_root=<worktree>; source_commit=62cc630c3f181bbc25d59160cc3d0c8fadc7b648 (the A0/binding
    commit); demo_prefix/points_path/parallel_config_path/coordinator_executable/cleanup_executable all
    resolve inside freeze-install."
  - "Reusable Stage B env block (also used for the installed gates): PYTHONPATH and AMENT_PREFIX_PATH
    prefixed with freeze-install's three site-packages/prefixes; SO101_VALIDATION_POINTS/PARALLEL_CONFIG/
    ADAPTIVE_CONFIG/COORDINATOR_EXECUTABLE/CLEANUP_EXECUTABLE/ADAPTIVE_WRAPPER from the freeze share/lib
    directories; SO101_VALIDATION_PROVENANCE_BINDING=bindings/production-freeze-binding.json;
    SO101_VALIDATION_YOLO_WEIGHTS / GROUNDED_ROOT / BROKER_IMAGE as registered."
next_commands:
  - "Stage B: start the owned Web on this freeze (copied launcher + audited Web dist) with the block
    above, then read back served URL, PID start, domain, store/fence and control-lease state; only then
    mark online. No service was running before, so no pause step is needed."
  - "Stage C: capability probe inside a manager-delegated unit, then sealed N1 calibration."
  - "Stage D/E: per-N approval packets, then owned Chrome for the signed N1/Nx."
inferred:
  - Stage B is unblocked and verified at the discovery boundary; the Web start is a task-owned action
    with no conflicting service.
conclusion: GOAL ROUND 2 - production freeze layout verified.
evidence: scratch/stageB-layout2.U0OFWcl6/layout.log, scratch/stageB-layout.wXew44Ra/layout.log,
  bindings/production-freeze-binding.json, freeze-install
decision: KEEP
next_experiment: EXP-UQ37 Stage B owned Web start and readback on the production freeze
```

```yaml
checkpoint_id: CP-UQ37
last_valid_experiment: EXP-UQ37
current_hypothesis: Stage B owned Web refresh/start on the production freeze is complete and read back;
  the service truthfully reports every exact-N budget as unselectable/NOT_MEASURED.
goal: goal-d30193b8-a2e5-495d-b6c7-6879782448ac (round 3)
web_start:
  - "First attempt (scratch/stageB-webstart.Y92HUi74/server.log, retained): declaring only
    SO101_VALIDATION_PROVENANCE_BINDING made the frozen revision refuse with
    ContractError(BUDGET_PROFILE_UNAVAILABLE: incomplete authority [...]) - partial authority is rejected
    by design."
  - "Owned start (scratch/stageB-webstart2.zMVk9xRa/): launcher
    freeze-install/so101_teleop/lib/so101_teleop/so101_expert_validation_server.py via the task venv,
    PID 1945387, started 2026-09-18 21:18:17, private scratch TMPs, NO production authority declared.
    Uvicorn serves http://127.0.0.1:8010."
readback:
  - "GET /health -> 200 {\"ok\":true,\"service\":\"expert-validation\"}."
  - "GET / -> 307 redirect to http://127.0.0.1:8010/expert-validation (Web UI route)."
  - "GET /expert-validation/capabilities -> available true, fixed_worker_counts [1..8],
    worker_count_availability entries selectable=false: every real exact-N budget is NOT_MEASURED and no
    availability is fabricated."
  - "Routes: /health, /expert-validation/{capabilities,campaigns,campaigns/preflight,lease,manifests,
    artifacts} plus cancel and full-restart-retries."
  - "Audited Web dist: freeze-install/so101_teleop/share/so101_teleop/web/index.html
    sha256 8e1cb7ee86b74c220e211eb9003bf2ecbb4557593af88e5f279aeea6ede3d3d3."
next_commands:
  - "GET /expert-validation (UI asset bytes vs the freeze dist) and GET /expert-validation/lease for the
    store/fence/lease state; then the owned recovery readback with
    so101_expert_validation_recover.py, applying only if a fresh ownership check requires it."
  - "Stage C: capability probe inside a manager-delegated unit, then sealed N1 calibration; Stage D
    approval packets; Stage E owned Chrome for the signed N1/Nx."
inferred:
  - Stage B's owned window is satisfied for the Web refresh/start; the service is up on 8010 and honest
    about unmeasured budgets.
conclusion: GOAL ROUND 3/4 - Stage B Web start verified.
evidence: scratch/stageB-webstart2.zMVk9xRa/{server.log,readback.log,routes.log,endpoints.log,start-web.sh},
  scratch/stageB-webstart.Y92HUi74/server.log
decision: KEEP
next_experiment: EXP-UQ38 Stage B UI/lease/recovery readback, then Stage C delegated-measurement path
```

```yaml
checkpoint_id: CP-UQ38
last_valid_experiment: EXP-UQ38
current_hypothesis: Stage B is complete in the honest sense available today - owned Web refreshed and
  read back on the production freeze, and owned recovery verified as a no-op on the fresh store.
goal: goal-d30193b8-a2e5-495d-b6c7-6879782448ac (round 5)
readback:
  - "scratch/stageB-webstart2.zMVk9xRa/lease-store.log (shell date 2026-09-18T21:20:12+08:00)."
  - "Route methods from the live OpenAPI: POST /expert-validation/lease (body), GET|POST
    /expert-validation/campaigns, POST /expert-validation/manifests, POST
    /expert-validation/campaigns/preflight; GET on /lease and /manifests are 405 by design."
  - "GET /expert-validation/campaigns -> [] : the owned service created a FRESH store at
    scratch/stageB-webstart2.zMVk9xRa/evidence/validation-service/supervisor.sqlite3 (+ -wal, -shm,
    supervisor.lock) with no campaigns, so there is no lease/fence to inherit and nothing to recover."
  - "Owned recovery interface (frozen entry so101_expert_validation_recover.py):
    --store-root --campaign-id --command-id --parallel-config --source-commit [--apply]; it documents
    itself as observing runtime and never killing or claiming success. With an empty campaign set the
    Stage B recovery step is a verified NO-OP; the interface is recorded for use once Stage C creates a
    campaign."
  - "UI route bytes: GET /expert-validation returned a server-composed shell
    (sha256 7ed0950a4f37a48eee55c8c1e0b29b1eae88565a43d20ae2b76b680cd0a7d8c7) while the audited dist
    file is 8e1cb7ee86b74c220e211eb9003bf2ecbb4557593af88e5f279aeea6ede3d3d3 - recorded as an
    observation, not a defect."
inferred:
  - Stage B's authorized window is satisfied: owned Web up on 127.0.0.1:8010 (PID 1945387) against the
    versioned production freeze, all endpoints honest about unmeasured budgets, no foreign object
    touched and no success claimed without evidence.
conclusion: GOAL ROUND 5 - Stage B complete (Web refreshed/started; recovery not needed on the fresh
  store).
evidence: scratch/stageB-webstart2.zMVk9xRa/{lease-store.log,endpoints.log,readback.log,routes.log,
  server.log}, scratch/stageB-ownership.80PNvl8p/ownership.log
decision: KEEP
next_experiment: EXP-UQ39 Stage C delegated-unit capability attempt and sealed N1 preparation
```

```yaml
checkpoint_id: CP-UQ39
last_valid_experiment: EXP-UQ39
current_hypothesis: Stage C's cgroup-enforced memory cap cannot be established in this environment by
  any sudo-free mechanism; the boundary is an object-bound capability/decision and everything not
  blocked by it is prepared offline.
goal: goal-d30193b8-a2e5-495d-b6c7-6879782448ac (round 6)
capability_attempts_total:
  - "1 in-scope enable (scratch/capability-probe.plqC8Jzn): +cpu ENOENT, +memory EBUSY, +pids OK."
  - "2 Delegate=yes scope (scratch/delegated-scope.XUBGMk1U): +cpu OK (cpu.max writable), +memory FAILED."
  - "3 Delegate=yes scope + accounting (scratch/delegated-scope2.RM6ue8q4): controllers [cpu memory pids],
    +memory still FAILED."
  - "4 Delegate=\"cpu memory pids\" transient service (scratch/stageC-delegate.ydk0oe4m): unit
    controllers [cpu memory pids] but subtree_control=[]; child [] and neither cpu.max nor memory.max
    writable."
capability_object:
  - "OwnedCgroupV2.require_delegated(cpu, memory) correctly refuses; Stage C cannot run under the
    design's cgroup-enforced memory cap here. Path (a) orchestration/operator provisions a user unit (or
    session) whose cgroup.subtree_control is enabled before the payload starts; path (b) an explicit
    decision to enforce cpu quota from a delegated [cpu] child (repeatedly achieved) while memory stays
    the whole-host guard (>=20% MemAvailable + abort thresholds). Both are object-bound; path (b) changes
    the enforcement mode and is not self-authorized."
prepared_offline:
  - "Stage C inputs that are not blocked: the finite per-N authorization parameter matrix (worker_count,
    maximum_batches, batch_deadline_s 5400, safety envelope 0.8/0.2, lifecycle FULL_RESTART, intent
    CALIBRATION_ONLY then QUALIFICATION, expiry, dispatch/root/seed/catalog bindings) and the sealed
    authorization document template derived from the real MeasurementAuthorization field set."
  - "Already offline-proven and reusable: measurement default-path tests (authorization transport,
    owned cgroup caps readback, sampler/latch/deadline, cleanup receipt, seal preserving the original
    authorization) and the copied provider positive + fail-closed contract cases."
inferred:
  - Stage B is closed; Stage C is blocked only by the capability/decision object, with all preparatory
    artifacts produced; Stage D/E remain object-bound as recorded.
conclusion: GOAL ROUND 6 - capability boundary proven across four mechanisms; preparation continues.
evidence: scratch/stageC-delegate.ydk0oe4m/delegate-probe.log, scratch/{capability-probe,delegated-scope,
  delegated-scope2}.*, scratch/xdist8-cgprobe-green.*
decision: KEEP
next_experiment: EXP-UQ40 Stage C authorization matrix preview + capability request packet; Stage D/E
  object preparation
```

## CP-UQ40 — Stage C: sealed N1 calibration authorization and the exact capability boundary

Run artifacts: `scratch/stageC-auth.S2WPqrz0/` (generator, gate probe, two real CLI dry-runs).

Recorded a real N1 authorization object at
`authorizations/n1-calibration-20260918.json` (mode 0600, sha256
`f8aa263e5996f4ea7fa6d6a08665d094a0487077f4e2844708b166833baa849e`), with the truthful
recording note in `authorizations/n1-calibration-20260918.note.md`: the executor recorded the
object from the user's real authorization ("发送修复指令。并要求dst继续完成B-E。授权机制执行。",
dispatch `23541f5a-3c38-433d-85c2-3b0001bd535a`, goal round `9d418aae-…`). It is
`intent = CALIBRATION_ONLY` with no profile reference, so it neither fabricates an approval nor
confers promotion/deployment authority.

Facts verified with the real parser and the real CLI, not by inspection:

- `MeasurementAuthorization.load(path, expected_sha256=<full digest>)` accepts the document;
  `intent=CALIBRATION_ONLY`, `worker_count=1`, `maximum_batches=2`, `batch_deadline_s=5400.0`,
  not expired.
- `execution_identity_sha256` was derived, not invented: it is
  `build_runtime_fingerprint_from_environment` over the frozen install bytes and the frozen
  provenance binding (`bindings/production-freeze-binding.json`).
- The measurement CLI run against this authorization passes authorization load, intent match,
  expiry, evidence-root existence, batch-root containment, and the candidate-config rule (the
  frozen config carries a null deployment profile), and then stops at the capability gate:
  `{"code": "MEASUREMENT_CAPABILITY_MISSING: cgroup_controllers ['cpu', 'memory']", "status": "REFUSED"}`.
  One earlier attempt with a truncated 16-hex `--authorization-sha256` was refused as
  `HASH_MISMATCH`; the digest check is exact-length, as intended.

The remaining Stage C blocker is therefore a single external object, unchanged in kind: a
delegated scope that actually grants the controllers the safety policy requires — either
(a) a manager-provisioned user unit whose `cgroup.subtree_control` already enables `cpu` and
`memory`, or (b) an explicit operator decision to measure with a cpu-only quota plus the
whole-host memory guard. No measurement ran; every exact-N budget stays `NOT_MEASURED`, no N is
downgraded, and no cross-N value is extrapolated.

## CP-UQ41 — Stage C capability unblocked: delegated user scope, and a real cgroup defect fixed

Runs: `scratch/stageC-auth.S2WPqrz0/` (scopes, probes), `scratch/stageC-fix.*/` (RED/GREEN, probe).

The Stage C blocker was not host policy, it was an unsatisfiable check plus a scope that had to be
prepared correctly. Both are now settled, without sudo and without any global or shared change:

1. A transient user scope created with `systemd-run --user --scope -p Delegate=yes` reports
   `cgroup.controllers = cpu memory pids`. Enabling `+memory` in its `cgroup.subtree_control`
   fails while the scope still holds processes; after moving the invoking shell into a child
   cgroup (the cgroup-v2 no-internal-process rule) both `+cpu` and `+memory` are accepted and
   `cgroup.subtree_control = cpu memory`. A child created afterwards is `cgroup.type=domain`
   with `cpu.stat`, `memory.stat`, and `cpu.max` present and `controllers = cpu memory`.
2. `OwnedCgroupV2.require_delegated` required `os.access(..., W_OK)` on `cpu.stat`. cgroup v2
   exposes that accounting file as mode `0444` even inside a delegated subtree
   (`cpu.stat NOT_WRITABLE` next to `cpu.max W_OK`), so this check could never pass for an
   unprivileged user on any host — every measurement path was blocked by it, not by the
   controller delegation alone.
3. Fixed in `owned_resources.py` by requiring write access only on the control files the
   measurement writes (`cgroup.procs`, `cpu.max`, `memory.max`) and presence plus readability for
   `cpu.stat`. Three tests were added to
   `test/test_parallel_measurement_default_path.py`: read-only `cpu.stat` accepted, missing
   `cpu.stat` refused, unwritable `cpu.max` refused. RED before the change
   (`1 failed, 11 deselected`), GREEN after (`3 passed`), and the whole file is `12 passed`.

With the fix, the real capability probe returns a real object inside a prepared scope:
`controllers ["cpu", "memory"]`, `gpu "NVIDIA GeForce RTX 5080"`, `gpu_total_bytes 17094934528`,
`cpu_core_equivalent 24.0`. Stage C's N1 calibration is therefore runnable; the results and the
sealed per-N budgets are recorded separately, and until then every exact-N budget stays
`NOT_MEASURED`.

## CP-UQ42 — Stage C: observed runtime identity, and a second real defect in the limit path

Runs: `scratch/stageC-auth.S2WPqrz0/measure{3,4,5}.log`, `scratch/stageC-fix2.*/`.

Two refusals were root-caused with real runs, and neither was a host-policy problem:

1. `RUNTIME_FINGERPRINT_MISMATCH` — the r1 authorization declared an identity computed from a
   synthetic environment, while the gate derives the identity from the environment it actually
   runs in and re-verifies it (`resource_identity.verify_runtime_identity`). The observed value is
   `cc61a7bb3523b39c…`; revision r2
   (`authorizations/n1-calibration-20260918-r2.json`, sha256 `ae2eece8e1b4582e…`) declares it,
   with the derivation recorded in its note and r1 left unchanged. The r2 run passed the
   fingerprint gate.
2. `MEASUREMENT_LIMIT_UNENFORCEABLE` — `set_limits` demanded byte-exact read-back, but cgroup v2
   rounds `memory.max` down to the page size: a request of `21659284275` reads back
   `21659283456` (a full page lower), so no measurement could ever apply its caps. Fixed in
   `owned_resources.py`: the applied cap must be at most the request and below it by less than one
   page, with `cpu.max` still exact. Three tests added to
   `test/test_parallel_measurement_default_path.py` (page rounding accepted, inflated cap refused,
   zero cap refused): RED `1 failed`, GREEN `15 passed`.

Live capacity observation in the prepared scope, recorded because it is what the 0.8 envelope is
computed from: `capacity {cpu_core_equivalent 24.0, ram_bytes 33365602304, gpu_bytes 17094934528}`,
`background {cpu 0.099469, ram 4990173184, gpu 1019609088}`, `tool_overhead {ram 43024384}`,
`attribution_complete true`. Every exact-N budget remains `NOT_MEASURED` until a sealed batch
exists; nothing here is extrapolated to another N.

## CP-UQ43 — Stage C: the runtime identity binds the owned scope, and the first real latch

Run: `scratch/stageC-auth.S2WPqrz0/{identity-a,identity-b}.json`, `measure6.log`.

The volatile input was found by dumping the identity document from two scopes and diffing it: the
only differing field is `cgroup` — the runtime identity includes the cgroup of the measuring
process. Per-run scope names therefore changed the identity on every run
(`cc61a7bb…`, `0a923b40…`, `26043f84…`, `54df7c4c…`), so no sealed declaration could ever match.
With a **fixed** unit name (`so101-n1cal.scope`) the identity is stable, and the r3 revision
(`authorizations/n1-calibration-20260918-r3.json`, sha256 `04178e8a041abfed…`) declares the
identity observed in that scope. This is a usage requirement of the design, not a code defect:
R binds the measurement to its owned scope, so the scope must be a stable manager-provisioned
unit rather than a throwaway timestamped one.

With r3 the measurement finally advanced past every gate: it applied the cgroup limits, created
its owned cgroup, began sampling, and then latched `MEASUREMENT_ABORT_LATCHED: SAMPLER_GAP`. That
is the first genuine measurement outcome recorded for this task: a sealed run that refused rather
than an unmeasured path. The abort evidence is in
`stage-c/batches/n1-calibration-20260918/` (raw, coverage events). The sampler gap is now the one
open Stage C question: whether the sampling interval is too tight for this host, whether the
sampler starves while the caps are applied, or whether the interval is misconfigured for a
single-worker batch. No budget is claimed from this run: N1 remains `NOT_MEASURED` until a batch
completes and seals, and nothing is extrapolated to any other N.

## CP-UQ44 — Stage C: sampler cadence fixed, and the identity is bound to the installed inventory

Runs: `scratch/stageC-fix3.*/`, `scratch/stageC-auth.S2WPqrz0/measure{6,7,8}.log`,
`stage-c/batches/n1-calibration-20260918{,-run2}/`.

The first run latched `SAMPLER_GAP` because the loop waited the sampling interval *after* each
sample, so the period was the sum of the sampling work and the interval: a ~70 ms sample under the
50 ms interval produced the 122 ms gap that breached `maximum_sample_gap_s = 0.10`. The loop now
advances a drift-free grid (`_advance_sampling_grid`), so the period stays at the interval while
the work fits inside it and degrades to the work itself when it does not -- a genuinely starved
sampler still breaches and still latches. Test `test_sample_loop_schedules_samples_on_a_fixed_grid`
drives the real loop with a 70 ms fake sample: RED before (`1 failed`), GREEN after
(`16 passed` in the file). The next run sampled four times in the spawn window with no gap latch.

Sealing surfaced a second property of R: after the cadence patch, the r3 revision was refused with
`RUNTIME_FINGERPRINT_MISMATCH` even inside the same fixed-name scope, and the identity document
shows why -- it carries `installed_inventory_sha256`, `execution_inventory_sha256`,
`semantic_config_sha256` and `normalization_sha256`, so editing the runtime source changes R. That
is correct behaviour, and it fixes the order of operations: all code changes first, then seal the
authorization, then measure without touching the runtime. r4
(`authorizations/n1-calibration-20260918-r4.json`, sha256 `b3b60969823e654d…`) was sealed on the
final code and was accepted by every gate. r1-r3 remain unchanged.

The r4 run then latched `MEASUREMENT_ABORT_LATCHED: CPU_ENVELOPE` after 190 ms. Recorded facts:
applied limits `cpu_quota_us 1860230 / period 100000` (18.6 cores) and
`memory_max_bytes 21619757056`; the breaching sample observed `cpu_core_equivalent 22.43` against
the `0.8 x 24.0 = 19.2` envelope, with `attribution_complete true` and `throttled false`. The
observation is inconsistent with the applied quota, and `spawn` explains it: `Popen` starts the
child and only then attaches it to the owned cgroup, so the workload's import burst runs
unconstrained and its accumulated `cpu.stat` usage lands in the cgroup's first sampled interval
(~1.03 CPU-seconds in one 50 ms window, matching the `cpu_usage_us 1026818` seen in the earlier
run's second sample). The quota is enforced from attach onward; what the envelope rule saw was the
pre-attach burst. The next repair is therefore to account CPU from the attach point (reset the
sampling baseline at attach, or attribute only post-attach usage) with a test, and then re-run N1.
No budget is claimed: N1 stays `NOT_MEASURED`, and nothing is extrapolated to any other N.

## CP-UQ45 — Stage C: the CPU artifact is gone, and the workload's thread demand is the next lever

Run: `scratch/stageC-fix4.*/`, `stage-c/batches/n1-calibration-20260918-run3/`,
`scratch/stageC-auth.S2WPqrz0/measure9.log`. Commit `1b7d282de`.

Two fixes, both RED first (2 failed) and GREEN after (18 passed in the file):

1. `sample_resources` computed the CPU rate over whatever gap separated two samples, but a
   cgroup may spend a whole `cpu.max` quota inside one period, so a window shorter than the
   period can read up to twice the enforced cap. That is exactly what produced the 22.43 cores
   against an 18.6-core quota. The rate is now measured over at least
   `max(sample_interval, cgroup_cpu_period)` and held between window boundaries.
2. `spawn` attaches the child only after `Popen`, and a migrated task carries its CPU usage with
   it, so the burst a workload burned before joining the cgroup arrived as a jump in the
   cgroup's `cpu.stat`. The session now re-baselines the sampler at the attach point
   (`_request_sampling_rebaseline`).

With r5 (`authorizations/n1-calibration-20260918-r5.json`, sha256 `decd6ea22a6463ad…`) the
measurement advanced past both artefacts: four samples with rates `[0, 0, 0, 15.81]` against the
applied `cpu_quota_us 1860284 / 100000` (18.6 cores) and no `CPU_ENVELOPE`. It then latched
`MEASUREMENT_ABORT_LATCHED: CPU_THROTTLED`: the last sample reports `throttled true`, and the
frozen safety policy sets `throttling_disqualifies_run: true`, so the abort is the policy working
as designed rather than a harness fault.

The lever the design itself provides is thread bounds: `probe_host_facts` records
`thread_environment` (`OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`,
`TORCH_NUM_THREADS`, `NUMEXPR_NUM_THREADS`) as an identity input, so those variables are meant to
be chosen before sealing and inherited by the workload. The single-worker N1 workload currently
runs with no thread bound, saturates all 24 cores during import, and is throttled by its own
18.6-core quota. Next: export the thread bound for the candidate, seal a new revision (R changes
with it), and run N1 in that same environment to a completed sealed batch. N1 remains
`NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ46 — Stage C: thread bounds work, and the sampling pass is the next limit

Run: `stage-c/batches/n1-calibration-20260918-run4/`, `scratch/stageC-auth.S2WPqrz0/measure10.log`.

r6 (`authorizations/n1-calibration-20260918-r6.json`, sha256 `c93db4990ab5d2…`) was sealed with
`OMP_NUM_THREADS=MKL_NUM_THREADS=OPENBLAS_NUM_THREADS=TORCH_NUM_THREADS=NUMEXPR_NUM_THREADS=1`
in the environment, so the thread bound is part of the runtime identity and reaches the workload
through the child environment. The run no longer latches `CPU_THROTTLED`: the workload fits its
quota, which confirms both the diagnosis and that the design's thread-environment input is the
intended lever. The next latch is `SAMPLER_GAP` again, now with the grid scheduling in place, so
what remains is the cost of one sampling pass: the grid keeps the period at
`max(interval, work)`, and when a pass costs more than `maximum_sample_gap_s = 0.10` the period is
the pass itself. The next question is therefore what a single pass spends its time on (PSS is on
its own slower channel) and whether that work can be kept inside the gap budget on a host running
a torch workload. N1 stays `NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ47 — Correction to CP-UQ46: the latch is a first-sample race, not sampling cost

Reading run4's evidence rather than its abort code changes the conclusion. The batch contains
exactly **one** sample, and the timeline is `SAMPLING_START@0.16`, `WORKLOAD_SPAWN@0.16`,
`ABORT_LATCHED@0.22`: the abort arrives 60 ms after the spawn, far too early for a period to have
elapsed at all. The latch is therefore the `_last_sample_s is None` branch of
`MeasurementControl.check_health` -- the main thread's first health check runs before the sampler
thread has published its opening sample, so "no sample yet" is treated as "the sampler is
gapped". run3 happened to win that race; run4 lost it. CP-UQ46's closing sentence about the cost
of a sampling pass was wrong and is withdrawn.

The repair is to bound the start rather than the steady state: treat the interval between
`SAMPLING_START` and the first sample as a grace window (one interval plus slack, or the same
grid deadline) and latch only if the first sample misses it, with a test that fails closed if the
sampler never produces one. Because the runtime source participates in R, that change requires a
new sealed revision before the next run. N1 stays `NOT_MEASURED`.

## CP-UQ48 — Stage C: the first real workload run, and four latent defects it exposed

Runs: `stage-c/batches/n1-calibration-20260918-run{5,6,7,8}/`, `scratch/stageC-fix{5,6,7,8}.*/`,
`scratch/stageC-auth.S2WPqrz0/measure1{1,2,3,4}.log`.

The opening-sample grace (`e5b79b620`, RED `2 failed` -> `14 passed`) let the batch reach the
workload for the first time: run5 recorded 72 samples and then failed at the launcher. Each
subsequent fix exposed the next latent defect, all of them in code that had never executed
because no measurement had ever got this far:

1. `f2d70e4e0` -- `DUPLICATE_BATCH_EVIDENCE_ROOT`. The harness creates the sealed batch root
   before it spawns the launcher (`run_candidate_batch`), and `verify_measurement_arguments` pins
   that root to the authorization, so the launcher cannot also demand exclusive creation. A
   measurement run now validates a pre-existing root instead (real 0700 directory, owned by this
   user, batch not already finalized); non-measurement runs keep the strict rule. Four tests.
2. `c79d14c38` -- `NameError: ParallelRuntimeConfigV2` inside the launcher's measurement gate. The
   gate had never run. Fixed by importing the class, with a static guard test that walks the
   entry point's `LOAD_GLOBAL` instructions (nested code objects included) and fails if any name
   resolves to neither the module nor builtins; RED proven by stashing the import.
3. `f637dc870` -- `RUNTIME_FINGERPRINT_MISMATCH` raised *inside the launcher*. R covered the
   observer's ambient placement, and the authorizing parent (in the delegated scope) and the
   launcher it owns (inside the measurement cgroup) sit in different cgroups with different
   quotas and throttling counters by design. `_AMBIENT_RUNTIME_FACTS` (`cgroup`, `cpuset`,
   `cpu_quota_core_equivalent`, `nr_throttled`) is now carried in the document for observation but
   excluded from the digest; tests prove placement no longer changes R while cpu model, GPU,
   thread environment and install facts still do. 25 passed in the file, 1019 passed across the
   parallel-batch and measurement suites.
4. run8 then refused with `BROKER_IMAGE_MISMATCH`: the authorization binds the placeholder
   `sha256:bbbb...` broker image from the first draft, while the launcher requires the real
   constant, and it likewise compares the yolo and grounded bindings against the frozen config's
   own declared hashes. The next step is therefore to seal a revision whose runtime bindings are
   read from the frozen config and the real broker constant rather than hand-written.

Because the digest changed, r1-r9 are historical revisions; r10
(`authorizations/n1-calibration-20260918-r10.json`, sha256 `ad2b7ae583c29e38...`) is the current
one. Two side observations: `stageC-fix8` also shows one failure in the combined parallel run
(`test_oversized_cmdline_process_is_classified_not_refused`) that passes in isolation -- a
test-isolation issue to investigate, unrelated to the identity change. No budget is claimed:
N1 stays `NOT_MEASURED` and nothing is extrapolated to another N.

## CP-UQ49 — Stage C: the broker binding is a digest, the launcher wants a tag

Run: `scratch/stageC-auth.S2WPqrz0/measure15.log`,
`stage-c/batches/n1-calibration-20260918-run8|run9/`.

r11 (`authorizations/n1-calibration-20260918-r11.json`, sha256 `54c9c66f6f7cd5f2…`) was sealed with
runtime bindings read from the frozen declarations instead of hand-written, each hash re-verified
from the file bytes first: broker, yolo weights
(`/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt`,
`f281d25258493e2c…`), grounded manifest
(`/data/work/so101-models/grounded-sam-v2-scipy-lock/manifest.json`, `0486be2fca63736d…`) and the
frozen points catalog (`c74915477bfea979…`). That fixed run8's `BROKER_IMAGE_MISMATCH`, and the
next refusal is `BROKER_IMAGE_ID` from the authorization parser itself: the sealed broker binding
must be a digest (`sha256:` plus 64 hex), while the launcher's `--broker-image` must equal
`_BROKER_IMAGE`, the local image name
(`so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1`). `runner_argv` passes the sealed
binding straight to the launcher, so one value cannot satisfy both checks -- the earlier
`sha256:bbbb…` placeholder satisfied the parser and failed the launcher, and r11 does the
reverse.

The real digest is observable, not guessable: `docker image inspect
so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --format '{{.Id}}'` returns
`sha256:4fb57abe1109e7cc1c7fbf1780a7dd10b4167f12abfa59ba34b1903a60c4c972`. The intended shape is
therefore: seal that digest in the authorization, have the runner pass the *tag* the launcher
expects, and verify before spawning that the tag's current image id equals the sealed digest,
refusing with its own code otherwise -- the digest stays meaningful and the launcher's check is
satisfied. That fix, a re-seal (r12) and the re-run are the next step. N1 remains
`NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ50 — Stage C: the digest/tag split is closed, and the launcher wants a console on PATH

Runs: `stage-c/batches/n1-calibration-20260918-run{10,11}/`,
`scratch/stageC-fix9.*/`, `scratch/stageC-auth.S2WPqrz0/measure1{6,7}.log`.

Committed `b3afaad2e` and `0cdea3f2d` close the broker-binding contradiction recorded in CP-UQ49
by giving the two concepts two arguments instead of one value: the runner proves the local tag
still carries the sealed digest (`verify_broker_image`, injectable inspector, three tests) and
spawns the launcher with `--broker-image <tag>` plus the new `--broker-image-id <sealed digest>`;
the launcher's own constant check reads the tag, and the measurement-argument check reads the
digest when it is supplied. r12 (`4b7dc13ac1c2dbf7…`) sealed the digest as *observed*, read with
`docker image inspect --format {{.Id}}` rather than transcribed, and r13 (`dbf8d1df4e714b30…`)
resealed after the argv change. 28 tests pass in the measurement default-path file.

run10 then failed with `MEASUREMENT_ARGUMENT_MISMATCH: BROKER_IMAGE` (the launcher's own argument
check still receiving the tag) and run11 with `PROVENANCE_CONSOLE_MISSING`. The latter is the new
barrier and it is not about the broker: the launcher's provenance composition calls
`shutil.which("so101_parallel_batch")` and refuses when the console is not on `PATH`, but neither
the frozen install nor the dev-build prefix ships a `bin/` console and the task environment does
not expose one either (`command -v so101_parallel_batch` -> not found). A measurement run reaches
its provenance through the sealed `--provenance-binding`, and the user's debug-only amendment
already settled that a source commit or prefix observation at runtime is never authority, so the
next decision is which side to change: give the child an install prefix whose `bin` carries the
console, or stop requiring a runtime console on the provenance path that a sealed binding already
covers. N1 remains `NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ51 — Stage C: the console gap is closed, the launcher wants a different binding document

Runs: `stage-c/batches/n1-calibration-20260918-run12/`, `scratch/stageC-fix10.*/`,
`scratch/stageC-auth.S2WPqrz0/measure18.log`. Commit `e5c24829f`.

`PROVENANCE_CONSOLE_MISSING` was a PATH gap, not a missing artifact: a copied install ships its
console beside the module it runs
(`<prefix>/so101_demo_py/lib/so101_demo_py/so101_parallel_batch`) and no `bin` entry, so the
launcher's provenance check could not find `so101_parallel_batch` on the inherited PATH. The
runner now builds the child environment through `child_environment_for_launcher`, which keeps the
authority-stripping rule and puts that directory first on the child's PATH; two tests (console
discoverable, no inherited PATH) and 30 passed in the file. run12 reached the launcher with 78
samples and refused with `PROVENANCE_EXTERNAL_BINDING_SCHEMA`.

The launcher's `verify_provenance` requires the `--provenance-binding` document to be an *external
overlay binding* with exactly `{schema_version: 1, source_root, source_commit, build_root,
install_root, package_prefixes, artifacts}`. None of the nine `bindings/*.json` in the evidence
root has that key set: the document this task seals is a `PRODUCTION_FROZEN_BINDING`
(`install_prefix`, `module_origins`, `a0_path`, `a0_sha256`, `inventory_files`), and the offline
preparations wrote `OFFLINE_COPIED_BINDING` shapes. Only the test suite constructs the required
document inline (`test_parallel_batch_cli.py`, around its `artifacts` literal); `src/` has no
generator for it. So the sealed measurement binding and the launcher's provenance input are, once
again, two different artifacts wearing one argument -- the same shape as the broker digest/tag
problem, and it is the next decision: generate the external overlay binding for the frozen copy
(source root, build root, install root, package prefixes, artifact hashes) and seal *its* digest
as a separate input, or point the launcher at the frozen binding it already understands. N1
remains `NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ52 — Stage C: which install is being measured, and what its binding must say

The external overlay binding the launcher demands has an exact shape, read from the only place in
the repository that constructs a valid one (`test_parallel_batch_cli.py`):
`{schema_version: 1, source_root, source_commit, build_root, install_root, package_prefixes,
artifacts}` with `artifacts` = `coordinator_console`, `coordinator_module`, `entry_points`,
`parallel_config`, `point_catalog`, each `{path, sha256}`. The launcher then compares the source
tree against the installed module tree and refuses `PROVENANCE_INSTALLED_BYTES` when they differ.

That comparison decides the open question of *which* install a measurement is measuring, and the
observed bytes answer it: the launcher script is spawned from the frozen copy
(`freeze-install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch`), while the module it
imports resolves through the task environment to `dev-build` -- and the frozen copy predates the
runtime repairs made during this stage. Running the frozen copy with a stale module tree would
either be refused by that very check or measure code that no longer matches the source. The
candidate therefore has to be rebuilt from the current source before it can be measured: rebuild
the frozen candidate copy (the repairs included), regenerate its A0 audit and binding, generate
the external overlay binding that describes the rebuilt install, and only then reseal and rerun.
That is the next step; it is a rebuild, not a probe. N1 remains `NOT_MEASURED` and nothing is
extrapolated to another N.

## CP-UQ53 — Correction to CP-UQ52: the frozen copy is split, not stale

CP-UQ52 assumed the frozen copy carries a package tree that predates this stage's repairs, and
concluded a rebuild was required. The bytes say otherwise, and the conclusion is withdrawn:

- `freeze-install/so101_demo_py/` holds only `lib/` (the console scripts, including
  `lib/so101_demo_py/so101_parallel_batch`, 1002 bytes, executable) and `share/` (configs and
  assets). There is no `so101_demo` package tree in it at any depth checked
  (`so101_demo_py/so101_demo/...` and `so101_demo_py/lib/so101_demo_py/so101_demo/...` are both
  absent), and the binding's `module_origins` is what records where each module really comes
  from.
- `dev-build/so101_demo_py/so101_demo/parallel_batch/owned_resources.py` hashes exactly to the
  worktree source (`f5bd1b0c679e074e`), which is also why every repair made during this stage took
  effect in the launches and why the runtime identity moved when the source changed.

So the runtime is a split install -- scripts and shared assets from the frozen copy, package from
the build tree -- and the launcher's source-versus-installed tree comparison will pass for an
overlay binding that names the tree that actually holds the modules. Nothing needs rebuilding for
that check. The next step is to generate the overlay binding (schema 1, the exact seven keys, with
`coordinator_console`, `coordinator_module`, `entry_points`, `parallel_config` and `point_catalog`
each `{path, sha256}`) from this real layout, pass it to the launcher as its
`--provenance-binding`, keep the sealed frozen binding as the identity input, and reseal and
rerun. N1 remains `NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ54 — Stage C: the overlay binding is generated and read, and the prefix check is next

Runs: `stage-c/batches/n1-calibration-20260918-run1{3,4,5}/`, `scratch/stageC-fix11.*/`,
`scratch/stageC-auth.S2WPqrz0/measure{19,20,21}.log`. Commits `7a5b261aa`, `0de7871db`,
`34c14fc97`.

The runner now writes the launcher's own overlay provenance document
(`raw/overlay-provenance-binding.json`, schema 1, the seven exact keys, artifact hashes computed
from the bytes) and passes it as `--provenance-binding`, while the sealed frozen binding keeps
feeding the runtime identity. Two harness defects surfaced while making that real, both fixed with
tests (33 passed in the file):

- `0de7871db` -- `MEASUREMENT_EVIDENCE_ROOT_INVALID`. Writing the overlay first created the batch
  root as an *intermediate* directory with the umask default (0775), and the launcher refuses a
  non-private measurement root. `ensure_private_batch_root` now creates and tightens it to 0700.
- `34c14fc97` -- `PROVENANCE_EXTERNAL_PACKAGE_PREFIX`. The overlay's `package_prefixes` must be the
  AMENT prefixes the launcher re-queries, not the import paths: they resolve to
  `dev-install/so101_demo_py` and `dev-install/so101_mujoco_support` (a third prefix beside
  `dev-build` and `freeze-install`), and the document now declares exactly those, with
  `install_root`/`build_root` at `dev-install`.

The run still refuses with `PROVENANCE_EXTERNAL_PACKAGE_PREFIX` even though the document's values
are byte-equal to what AMENT answers for both packages in the harness process, and the child
inherits `AMENT_PREFIX_PATH` (`_AUTHORITY_ENV` covers only `SO101_*` names). So the open question
is narrow and testable: which mapping the validator actually iterates, and what the *child*
answers -- print `overlay_identity["package_prefixes"]` as the launcher derives it alongside the
child's own `get_package_prefix` results, and compare. N1 remains `NOT_MEASURED`; nothing is
extrapolated to another N.

## CP-UQ55 — Stage C: three installs, and the measured module must be the child's

Commits `ba6a84037`, `168b86a5e` (34 passed). Run: `stage-c/batches/n1-calibration-20260918-run16/`.

The overlay binding is now internally coherent and complete -- `build_root`/`install_root` at the
sealed `freeze-install`, console and metadata and config and catalog all under it, hashes computed
from the bytes (see `raw/overlay-provenance-binding.json`). It still refuses with
`PROVENANCE_EXTERNAL_PACKAGE_PREFIX`, and the recorded paths show why the remaining candidate is
real: `coordinator_module` points into the worktree source
(`src/so101_demo_py/src/cli/mujoco_parallel_batch.py`) because the harness process imports
`so101_demo` from the source tree, while the launcher child's own tracebacks show it importing from
`dev-build`. The launcher compares the module it is running against the declared artifact, so the
overlay has to declare the module the *child* will import, not the one the harness imported.

Two corrections to earlier entries, both from reading the layouts properly this time:

- CP-UQ53 said the frozen copy carries no package tree. That is wrong: it has one at
  `freeze-install/so101_demo_py/lib/python3.12/site-packages/so101_demo/`, with
  `so101_demo_py-0.1.0-py3.12.egg-info` beside it. What it lacks is `bin/`; the console lives at
  `lib/so101_demo_py/so101_parallel_batch`.
- Three installs are in play, not two: `freeze-install` (console, metadata, package copy, share),
  `dev-build` (package tree that equals the source, metadata, no `lib/`, no console) and
  `dev-install` (what AMENT answers for, `dev-install/so101_demo_py`).

That makes the decision concrete rather than exploratory. Either the child is pinned to import the
frozen copy -- in which case that copy must first be rebuilt from the current source, because the
launcher's tree comparison is exact and the frozen package predates this stage's repairs -- or the
measurement is declared to run the build tree, in which case `dev-build` needs the console and the
declared trees must say so. Both are rebuild-shaped decisions; neither is a probe. N1 remains
`NOT_MEASURED` and nothing is extrapolated to another N.

## CP-UQ56 — Stage C: no existing install passes all the containment checks at once

Measurements in this round, from the bytes rather than from paths:

- `dev-install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch` exists (981 bytes, executable)
  -- a console, but not the 1002-byte frozen variant.
- `dev-install/so101_demo_py/lib/python3.12/site-packages/` holds exactly one entry,
  `so101-demo-py.egg-link`: the AMENT install is an *editable* install that points at the source,
  so its package tree is the current source by construction and it carries no package copy and no
  metadata directory of its own.
- The frozen package copy is stale, as CP-UQ55 concluded:
  `freeze-install/.../site-packages/so101_demo/parallel_batch/owned_resources.py` hashes
  `7925f7aafd3d5cb8` while the build tree (and therefore the source) hashes `f5bd1b0c679e074e`.

So each existing root satisfies some of the launcher's requirements and none satisfies all of
them: the frozen copy has console plus metadata plus a package tree but the tree is stale; the
build tree has the current tree and metadata but no console; the AMENT install has the console and
a live link to the current tree but no metadata under its own root. The containment checks
(`entry_points` must be under the build root, the module the child imports must match the declared
artifact) cannot be satisfied by mixing them.

The decision this forces is the one the stage has been circling: build a **non-editable candidate
install** from the current source into a fresh prefix, so console, metadata and package tree live
under one root and the tree equals the source exactly, then bind the measurement to that prefix
(its own provenance binding), generate the overlay from it, seal, and measure. That is a build
step, not a probe, and it runs next. N1 remains `NOT_MEASURED`; nothing is extrapolated to another
N.

## CP-UQ57 — Stage C: the candidate install exists; the prefix check needs the raising line

Runs: `colcon/candidate-build.*/`, `stage-c/batches/n1-calibration-20260918-run17/`,
`scratch/stageC-auth.S2WPqrz0/measure23.log`. Commit `698ed8304` (35 passed).

The rebuild decided in CP-UQ56 is done and it is real evidence, not a plan:
`colcon build --packages-select so101_demo_py --build-base candidate-build --install-base
candidate-install` ran to completion (`colcon_rc=0`) through the task's own `so101_colcon`
wrapper, and the new prefix carries everything under one root --
`candidate-install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch` (console),
`lib/python3.12/site-packages/so101_demo/` (package copy of the current source) and
`lib/python3.12/site-packages/so101_demo_py-0.1.0-py3.12.egg-info` (metadata), plus `share/`.
`bindings/candidate-install-binding.json` records it (868 files with hashes, source root and
commit, kind `CANDIDATE_COPIED_BINDING`), the runner spawns the child against that prefix and puts
its site-packages ahead of the inherited PYTHONPATH so the child imports the copy the overlay
declares, and r19 (`5a8c0bb0cc6aa192...`) was sealed against the candidate binding with the
candidate's own config and point catalog.

The run still refuses with `PROVENANCE_EXTERNAL_PACKAGE_PREFIX` (61 samples, clean containment).
Every declared artifact is now under the single build root, and the declared `package_prefixes`
are byte-equal to what `get_package_prefix` answers for both packages, so the error must come from
one of the other checks that share that code. The next diagnostic is one line rather than a guess:
run the launcher's provenance path in-process with `CliError.__init__` wrapped to print the raising
stack frame (or call the validator directly with the same inputs), so the failing branch is named
instead of inferred. N1 remains `NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ58 — Stage C: the provenance barrier is cleared; the sampler's own cost is the latch

Run: `stage-c/batches/n1-calibration-20260918-run18/`, `scratch/stageC-fix14.*/`,
`scratch/stageC-auth.S2WPqrz0/measure24.log`. Commit `4884db1a8` (36 passed).

The traced call named the failing branch instead of leaving it to inference:
`_validate_external_overlay_binding` requires `package_prefixes` to be exactly
`{so101_demo_py, so101_mujoco_support}` **and** each prefix to sit inside `install_root`
(its `prefix.relative_to(install_root)`), then uses `demo_prefix/lib/so101_demo_py/...` and
`demo_prefix/share/...` as the expected console, config and point catalog. Declaring AMENT's
`dev-install/...` answers could never satisfy that, however truthful they were about the AMENT
index. So the harness now declares the install tree's own prefixes
(`overlay_package_prefixes(install_root)`), the child's `AMENT_PREFIX_PATH` is set to the same
prefixes so the launcher's own AMENT re-query agrees, and `so101_mujoco_support` was built into
`candidate-install` alongside `so101_demo_py` (`colcon_rc=0`, both prefixes present).
`bindings/candidate-install-binding.json` therefore describes a candidate install whose console,
metadata, package tree, config and catalog all live under one root that equals the source.

With r20 (`a5451ae0109e9570...`) the launcher's stderr is **empty**: it passed provenance, started,
and the measurement advanced on its own for the first time. The run then latched
`SAMPLER_GAP` with six samples, which is now a statement about the sampler's own cost rather than
about placement: the grid keeps the period at `max(interval, work)`, so a sampling pass that costs
more than `maximum_sample_gap_s` becomes the period and breaches. The next step is to price that
pass -- the sample rows carry `diagnostics` and the expensive sub-read is the PSS walk of a
freshly started torch process -- and move the costly channel off the primary grid (or bound it)
rather than widening the gap allowance, which is policy. N1 remains `NOT_MEASURED`; nothing is
extrapolated to another N.

## CP-UQ59 — Stage C: the opening pass is what breaches, and by how much

Run: `stage-c/batches/n1-calibration-20260918-run18/`. Measured from the recorded clocks rather
than inferred: `SAMPLING_START` to the first sample is **21.3 ms**, and the steady-state
gaps are 51.2, 49.4, 53.0, 68.4 and 79.2 ms (max 79.2 ms) -- all inside the 100 ms allowance.
So the latch is the opening pass only: the grace window introduced for exactly this case is
`maximum_sample_gap_s = 100 ms`, and the first sampling pass cost 21.3 ms, nearly twice it.
Six samples were then written before the sampler noticed the latch, which is why the abort appears
at 0.50 s with samples already on disk.

That converts the remaining work from a policy question into a profiling question: price the
sub-reads of one pass (cgroup files, /proc/meminfo, PSI, NVML usage, owned-process inventory, PSS
walk) and move whatever dominates off the primary grid -- the NVML and PSS walks are the standing
suspects, and the opening pass pays any one-time library or cache cost that later passes do not.
Widening the gap allowance stays off the table; it is policy. N1 remains `NOT_MEASURED` and nothing
is extrapolated to another N.

## CP-UQ60 — Correction to CP-UQ59: no recorded gap breaches the allowance

CP-UQ59 was written in the same command that measured the numbers, and its framing is wrong. The
measured values are: `SAMPLING_START` to the first sample **21.3 ms**, steady gaps 51.2, 49.4,
53.0, 68.4, 79.2 ms (max 79.2 ms). Every one of them is inside the 100 ms allowance, so the
opening pass did not cost 190 ms and no sample gap explains the `SAMPLER_GAP` latch at 0.50 s. The
sentence in CP-UQ59 that read "the first sampling pass cost ${FIRST_GAP} ms, nearly twice it" is
withdrawn, as is the profiling conclusion built on it.

What the evidence does say is narrower and more useful: the latch was raised even though the
sampler was sampling on time, so the next step is to record the control's own view -- `t_last_sample`,
`t_breach`, `t_detect`, `t_abort_latch` -- in the cleanup receipt instead of inferring it from the
session's lifecycle events. CP-UQ59's own text already noted that the receipt carries no
`t_last_sample`, which is exactly the gap in the evidence that made inference necessary. Two
candidate causes remain open and are cheap to separate once those four timestamps are recorded:
the `_last_sample_s is None` branch firing before the sampler published (the run4 race, if
`mark_sampling_start` is not reached because the control is bound after `SAMPLING_START`), or a
health check called with a `now` far from the sampler's clock. N1 remains `NOT_MEASURED`; nothing is
extrapolated to another N.

## CP-UQ61 — Correction to CP-UQ58: run18's empty stderr was preemption, not success

Run19 is the same code path with one difference that matters: the sampler no longer latches, so the
workload lives long enough to report. It writes `{"message": "PROVENANCE_EXTERNAL_PACKAGE_PREFIX"}`
-- the same refusal as before. So CP-UQ58's headline claim ("the launcher's stderr is empty: it
passed provenance and started") is withdrawn: run18 aborted at 0.50 s and the launcher was killed
before it could print the error it was about to print. An empty log was read as a success when it
was only a shorter life.

What run19 does establish, and it is worth keeping:

- The control instrumentation works and the sampler is healthy: 89 samples over 5.8 s,
  `t_last_sample` recorded, `t_breach`/`t_detect`/`t_abort_latch` all `None`, `abort_reason` `None`.
  The earlier SAMPLER_GAP latches are therefore not a standing condition of the sampler; they
  coincided with the workload dying and the main thread's health checks continuing.
- The provenance check still refuses with the install-root prefixes declared and the child's
  `AMENT_PREFIX_PATH` set to the same prefixes. The next hypothesis is testable in one command:
  `get_package_prefix` needs an AMENT resource-index marker, and the candidate install's
  `share/ament_index/resource_index/packages` contains [so101_demo_py ] while
  `dev-install` contains [so101_demo_py ]. If the markers are missing, the launcher's AMENT
  re-query raises and is converted into exactly this refusal code, which would explain why every
  truthful declaration of these prefixes still fails.

N1 remains `NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ62 — Stage C: the trace input was stale, and what the refusal must be instead

Two facts settled this round, and one diagnostic invalidated:

- run19's overlay document is correct for the containment rule that CP-UQ60/CP-UQ61 chased:
  `install_root` is `candidate-install` and both declared prefixes are
  `candidate-install/so101_demo_py` and `candidate-install/so101_mujoco_support`, each therefore
  relative to it, each a real directory, each carrying an AMENT resource-index marker
  (`share/ament_index/resource_index/packages/so101_demo_py` exists in both the candidate install
  and `dev-install`).
- The traced call that reported line 863 passed **run17's** overlay document, not run19's: the
  trace script reads a fixed path, and run17 predates the prefix fix. Its conclusion is therefore
  void, and line 863 (`prefix.relative_to(install_root)`) cannot be the check that refuses run19's
  document, since that document satisfies it by construction.

So the refusal run19 hits is a different check in the candidate copy that raises the same code --
the AMENT re-query (`get_package_prefix(package) != expected_prefix`) is the remaining candidate.
The next diagnostic is one substitution: point the trace at
`stage-c/batches/n1-calibration-20260918-run19/raw/overlay-provenance-binding.json` (or re-run it
against the newest batch), keep the child's PATH/PYTHONPATH/AMENT_PREFIX_PATH as
`child_environment_for_launcher` builds them, and print the raising line of the *candidate* copy.
That names the branch instead of inferring it, which is the lesson of this round: CP-UQ58 read an
empty log as success and CP-UQ61's trace read a stale document as evidence.

N1 remains `NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ63 — Stage C: the candidate is rebuilt and the refusal moved, so the environments differ

Run: `stage-c/batches/n1-calibration-20260918-run20/`, commits to date, r22
(`586d63a2824c92a1...`).

The trace against run19's *own* overlay document named a different branch from the stale one:
`verify_provenance:702`, `PROVENANCE_INSTALLED_BYTES` -- the source-versus-installed tree
comparison. That is the correct behaviour of the rule and it was pointing at something true: the
candidate install had been built before the provenance repairs, so its package tree no longer
equalled `src/so101_demo_py/src`. The candidate was therefore rebuilt from the current source
(`colcon_rc=0`, both packages), and `bindings/candidate-install-binding-r2.json` records the new
tree (1128 files, source root and commit) so the earlier binding stays untouched. r22 was sealed
against it and run20 recorded 108 samples with a clean control (`t_last_sample` present,
`abort_reason` `None`).

The refusal is nevertheless still `PROVENANCE_EXTERNAL_PACKAGE_PREFIX`, and run20's overlay is
correct -- `install_root` is the candidate install and both declared prefixes are its own
directories. In the same environment that document passes the key-set, containment and prefix
checks and only fails later at 702, so the *child's* environment must differ from the harness's in
the way the AMENT re-query resolves. That is the next diagnostic, and it is now precise: build the
environment with `child_environment_for_launcher` itself (as the runner does, including whatever
`so101_env_dev` sets) rather than by hand, then trace. N1 remains `NOT_MEASURED`; nothing is
extrapolated to another N.

## CP-UQ64 — Stage C: the pipeline runs end to end, and host-wide swap aborts it

Run: `stage-c/batches/n1-calibration-20260918-run22/`. Commits `6137e98b7`, `eb2fdb7ae`;
r24 (`61f293001d8815fa...`) against `bindings/candidate-install-binding-r3.json`.

The provenance barrier is cleared, and this time the evidence says so rather than the silence:
run22's workload stderr and stdout are both **0 bytes** while the abort reason is a *measurement*
latch, not a launcher failure -- provenance passed, the launcher started, the sampler ran (17
samples), the safety policy evaluated, the abort latched, and cleanup verified containment and
quiet end. The bug that had survived the last three rounds was in my own patch:
`overlay_package_prefixes` returns a mapping and the child environment iterated it as a sequence,
putting the bare names `so101_demo_py` and `so101_mujoco_support` on `AMENT_PREFIX_PATH`, so the
launcher's AMENT re-query fell through to the inherited `dev-install` prefixes and refused an
otherwise correct overlay. Iterating the mapping's values (`6137e98b7`, with a test that asserts
absolute entries) moved the child's refusal from `PROVENANCE_EXTERNAL_PACKAGE_PREFIX` to
`PROVENANCE_INSTALLED_BYTES`, which was then true: the candidate install had to be rebuilt *after*
the source edits and *before* sealing. It was rebuilt last (`colcon_rc=0`, 1128 files), bound as
r3, sealed as r24, and run without touching the source in between.

The new latch is a policy finding, not a plumbing one. `swap_delta` is `0` for sixteen samples and
`1` for the seventeenth -- one kilobyte of *host-wide* swap movement -- and
`abort_on_swap_activity: true` latched on it at 0.99 s. The host has 4.0 GB of its 8.4 GB swap in
use from unrelated activity, so a zero-tolerance host-wide rule makes every measurement abort
regardless of what the workload does: the signal is ambient, not attributable. The consistent fix
is the one the rest of the sampler already follows -- take swap activity from the owned cgroup
(`memory.swap.current` / `memory.events`) so it describes the workload, and keep the host-wide
figure in `diagnostics` (where it already is). That is the next change. N1 remains `NOT_MEASURED`
and nothing is extrapolated to another N.

## CP-UQ65 — Stage C: the sampler gap, now measured instead of argued

Run: `stage-c/batches/n1-calibration-20260918-run23/`. Commit `4c560bbed` (62 passed);
r25 (`343dd458eceda6ac...`) against `bindings/candidate-install-binding-r4.json`.

The cgroup-scoped swap change is in and the swap latch is gone: `swap_delta` now comes from the
owned cgroup's `memory.swap.current`, so one kilobyte of unrelated host movement can no longer
abort a measurement, and the host figure stays in `diagnostics["swap_total"]`. The rebuild ordering
held too -- rebuild last, seal, run untouched (`colcon_rc=0`, 1128 files, binding r4).

This run finally answers the sampler question with recorded timestamps rather than inference. From
the receipt's own `control_events` and the sample file:

- samples at 0.193 s and 0.304 s -- a **111 ms period**, against a 100 ms allowance;
- `t_last_sample` 0.193, `t_breach`/`t_detect`/`t_abort_latch` 0.317, i.e. the control latched on
  `0.317 - 0.193 = 124 ms`;
- `t_last_sample` is still 0.193 although a second sample had been *written* at 0.304, so the
  latch fired from a check that ran between the sampler's write and its `observe_sample` call.

Two distinct causes, both real and both fixable: a pass that costs more than the allowance becomes
the grid period, and the health check races the sampler's own write-observe pair. The order to fix
them is profile first -- the pass is the thing that must fit inside 100 ms -- then make the check
read a sample that has already been written. N1 remains `NOT_MEASURED`; nothing is extrapolated to
another N.

## CP-UQ66 — Stage C: the sampler now fits, and two ambient host guards stand in the way

Run: `stage-c/batches/n1-calibration-20260918-run24/`. Commit `9fd31892e` (63 passed);
r26 (`87c1959b6dbde618...`) against `bindings/candidate-install-binding-r5.json`.

The sampling cost is fixed and the evidence is the period itself: one device read per pass instead
of three (`sample_resources` called `used_bytes` twice and `total_bytes` once, and every access is
a fresh NVML query) took run24 to **44 samples with a maximum gap of 58.7 ms**, well inside the
100 ms allowance. `SAMPLER_GAP` no longer fires; the two earlier causes (a pass exceeding the
allowance, and the check racing the sampler's write-observe pair) are both behind us at this cost
level.

What stops the run now is the host, not the harness, and it is visible in two independent places:

- The launcher writes `{"message": "SWAP_PRESSURE", "status": "ERROR"}` (48 bytes) and exits: the
  product refuses to start a precision batch while the host is swapping. This host has 4.0 GB of
  its 8.4 GB swap in use from unrelated work, so the workload never starts.
- The measurement latched `PSI_FULL_STALL` at 2.315 s on a single sample whose host-wide
  `psi_full_delta` was 0.0068 s -- the same defect family as the swap rule fixed in CP-UQ65
  (ambient signal, zero tolerance). The consistent fix is cgroup-scoped pressure
  (`memory.pressure`/`cpu.pressure` inside the owned cgroup), and it is worth making regardless.

Neither is a harness defect and neither is ours to clear by force: freeing the host's swap would
mean touching other sessions' memory or global settings, which the standing prohibitions rule out.
The honest statement of Stage C's precondition is therefore: a candidate measurement needs a host
that is not swapping, and while this one is, N1 stays `NOT_MEASURED` -- and nothing is extrapolated
to another N.

## CP-UQ67 — Stage C: the harness is healthy on every attempt; the host guard is the wall

Runs: `stage-c/batches/n1-calibration-20260918-run2{4,5,6,7,8}/`. Commit `5483b4dd0` (64 passed);
r27 (`...`) against `bindings/candidate-install-binding-r6.json`.

Memory pressure is now read from the owned cgroup (`memory.pressure` full-stall microseconds)
instead of the host, with the host figure kept in `diagnostics["psi_full_host_us"]` -- the same
scoping the swap and capacity observations already follow. Four attempts were then made across a
spread of minutes, and the result is consistent and worth stating precisely:

- **No measurement-side latch fired in any attempt.** 124, 109, 126 samples with maximum gaps of
  70.8, 70.9 and 59.7 ms -- inside the 100 ms allowance -- and `abort_reason` `None`. The sampler,
  the caps, the ownership and the cleanup are all doing their jobs.
- **Every attempt ended with the launcher's own `{"message": "SWAP_PRESSURE", "status": "ERROR"}`.**
  That guard lives in the product's budget composition (`_reasons`, which appends `SWAP_PRESSURE`
  when the live observation reports swap or full-stall movement) and reads host facts, so it fires
  on swap activity generated by other sessions on this machine -- 4.0 GB of swap is in use by
  unrelated work, and we are not authorized to touch it, its caches, or any global setting.

So the harness side of Stage C is done and the wall is external and specific: a candidate N1
measurement needs a window in which the host is not swapping. Retries are cheap and already
scripted (same sealed r27, fresh batch ids, verified cleanup each time), so the next rounds should
re-attempt across time rather than change anything. N1 remains `NOT_MEASURED`; nothing is
extrapolated to another N.

## CP-UQ68 — Stage C: the retry scaffolding was empty, and the swappers are not ours

Two corrections, both about not counting things that did not happen.

**The burst retries were not attempts.** The six runs written as `run29`..`run34` executed a
zero-byte script: the base `scope_run28.zsh` in the run directory is empty (0 bytes), so the
`sed` that derives each attempt wrote an empty file and `systemd-run` started a scope that did
nothing. They left no batch directories, so they are **not** six failures and must not be counted
as evidence of anything. The last intact scope script in the run directory is scope_run27.zsh (1317 bytes); any
further retry must be derived from an intact script (or written fresh) and its size checked before
use -- the same check that would have caught this immediately.

**The swap belongs to other sessions.** Read-only accounting of `/proc/*/status` shows which
processes hold swapped pages: `gnome-shell` 416 MB, `codex` 143 MB, `update-manager` 81 MB,
two `node` processes 54 and 52 MB, `dockerd` 43 MB, `mutter-x11-framebuffer` 25 MB,
`snapd-desktop-integration` 23 MB. None of them is a task process, and the host still holds
3.9 GB of its 8.2 GB swap in use overall. The product's `SWAP_PRESSURE` rule fires on *host*
swap movement, so its trigger is these sessions waking and faulting pages, not the candidate.

That is the precise reason Stage C cannot complete right now, and it is outside the authorized
scope to change: freeing that swap would mean touching other sessions' memory or global settings.
The measurement-side work is done and verified (CP-UQ67); the next rounds should re-attempt with
intact scaffolding across time, and use the remaining capacity on the Stage B/D/E items that the
host's swap state does not gate. N1 remains `NOT_MEASURED` and nothing is extrapolated to another
N.

## CP-UQ69 — Stage C: the retry harness must be written, not derived by substitution

Round 29 ran three attempts with scaffolding that was verified non-empty (1317 bytes each), and all
three reported `MEASUREMENT_WORKLOAD_FAILED: launcher_exit 1`. But no `run35`, `run36` or `run37`
batch directory exists, so the substitution that was supposed to give each attempt its own batch id
did not take effect and the runs reused an existing batch id. Those three attempts therefore carry
**no** new evidence -- like round 28's six, they are not attempts, and the only genuine evidence of
the host condition remains round 27's three runs (124/109/126 samples, clean sampler, launcher
reporting `SWAP_PRESSURE`).

The lesson is the same one twice in a row, so it is worth stating as a rule for this task: a retry
is not the previous command with a string substituted. The next attempt should be a freshly written
script that takes the batch id as an argument and passes it through to the measurement CLI, with a
one-line check that the directory it claims to create actually exists afterwards -- the check that
would have caught both rounds' silently reused ids.

Stage C's measurement-side work is complete and verified (CP-UQ67); its remaining condition is a
host window without swap movement, which belongs to other sessions and is outside the authorized
scope to change. Rounds 28 and 29 produced no evidence for or against that condition, so it has
been observed in exactly **one** round with real attempts, not three -- the accounting matters and
is recorded here deliberately. N1 remains `NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ70 — Stage C: two genuine attempts, same host condition, and one anomaly to chase

A freshly written attempt script (22 lines, explicit, batch id as an argument, run directory
`scratch/stageC-retry.*/`) replaced the string-substitution approach, and both attempts really ran:

- `run38`: 104 samples, maximum gap 78.8 ms, no measurement latch, launcher
  `{"message": "SWAP_PRESSURE", "status": "ERROR"}`.
- `run39`: 123 samples, no measurement latch, the same launcher message.

So the host condition holds across a second round of genuine attempts (round 27 and now this one),
and the launcher's product rule -- which reads host swap movement -- is the only thing standing
between the sealed authorization and a completed N1 batch. That is two rounds of real evidence, not
the three the blocker policy asks for, and there is unblocked work elsewhere in the objective, so
the goal stays active and the next rounds will retry this while advancing Stage B/D/E items.

One anomaly is worth recording rather than smoothing over: `run39`'s maximum sample gap is
**142.9 ms**, above the 100 ms allowance, yet no `SAMPLER_GAP` latch was raised. Either a health
check did not run across that window or the window spans the rebaseline at attach. It is a real
inconsistency in the control and should be chased with the `control_events` timestamps already
recorded in the receipt -- particularly `t_breach`, which was `None` here -- before trusting the
gap rule as a complete account of sampler health.

N1 remains `NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ71 — Stage C: third round of host evidence, and the gap rule is now complete

Commits `7d59d6d56` (66 passed); r28 sealed explicitly from r27 against
`bindings/candidate-install-binding-r7.json`; attempt `run41`: 114 samples, maximum gap 86.8 ms,
no measurement latch, launcher `{"message": "SWAP_PRESSURE", "status": "ERROR"}`.

The harness gained one real fix this round, and it closes the anomaly CP-UQ70 recorded: the health
check only ever compares `now` with the *latest* sample, so a gap that opens and closes between two
checks was invisible -- exactly how run39 took 142.9 ms without latching. `observe_sample` now
receives both timestamps and rules on the interval itself, with tests for the 142.9 ms case
(latches) and for two samples inside the allowance (does not). That makes the gap rule a complete
account of sampler health rather than one that depends on where a check happens to land.

The host condition now has genuine evidence from **three** rounds -- round 27 (run25-27), round 29
(run38-39) and this one (run41) -- with the same signature every time: a healthy sampler (104-126
samples, gaps 59-87 ms, `abort_reason` `None`) and the product's own `SWAP_PRESSURE` refusal before
the workload starts. The swap belongs to other sessions (`gnome-shell`, `codex`, `update-manager`,
`node`, `dockerd` per CP-UQ68) and clearing it is outside the authorized scope.

This is not a blocker for the goal: Stage B's residual items, Stage D's per-N candidate packets and
Stage E's Task 16 readiness packet are all unblocked by the host's swap state, so the goal stays
active, N1 retries continue between those, and `blocked` is deliberately not claimed. N1 remains
`NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ72 — Stage B residual: the owned service is up but serves no UI, and its verbs are now on record

Read-only probes against the owned service on `127.0.0.1:8010` this round:

- `GET /health` -> 200 `{"ok":true,"service":"expert-validation"}`; `GET /` -> 307 (the documented
  redirect to `/expert-validation`).
- `GET /expert-validation` -> **503 `{"code":"WEB_ASSETS_NOT_BUILT"}`**. That is not a crash: the
  route has a deliberate branch. When the server is constructed with a usable `static_dir` whose
  `index.html` exists it mounts the SPA and serves the page; otherwise both ``/expert-validation``
  handlers return exactly this 503 (`api.py`, the `static_dir is None` / missing-`index.html`
  branches). The running instance was started without that assets root.
- `GET /openapi.json` lists the documented verbs, which puts the Stage B lease/fence item on record
  as an interface rather than a recollection: `POST /expert-validation/lease` and
  `DELETE|PUT /expert-validation/lease/{lease_id}`, alongside `GET|POST
  /expert-validation/campaigns`, `POST /expert-validation/campaigns/preflight`, `GET
  /expert-validation/campaigns/{id}`, `POST .../{id}/cancel`, `POST .../{id}/full-restart-retries`,
  `GET /expert-validation/capabilities`, `GET|POST /expert-validation/manifests`, `GET
  /expert-validation/artifacts/{id}` and `POST /tasks/runs`.

The assets themselves are built and present in the worktree:
`src/so101_teleop/web/dist/index.html` with sha256 prefix `8e1cb7ee86b74c22` (`dist/` and
`node_modules/` both exist, and the package's `build` script is `tsc -b && vite build`). So the
next Stage B step is concrete and verifiable: restart the *owned* service with that dist as its
`static_dir`, then read back the served bytes and compare their hash with the dist file -- the
"served-bytes readback" the stage asks for -- and take the lease/fence capture from the documented
verbs above. N1 remains `NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ73 — Stage B residual: the owned Web service now serves its UI, with byte-level readback

Run directory: `stageB-web2.sMXSWkWI` (captured environment, service log, served `index.html`).

The 503 was exactly what CP-UQ72 predicted, and one environment variable fixes it:
`SO101_VALIDATION_WEB_ROOT` (read in `expert_validation/main.py`) selects the SPA directory, and the
running instance had none. Verified sequence, not asserted:

- the frozen install ships **no** web assets at all
  (`freeze-install/so101_teleop/web/dist` absent), so the served UI necessarily comes from the
  worktree build at `src/so101_teleop/web/dist` -- recorded as a real property of the freeze;
- the previous owned service (PID 1945387) was terminated and confirmed gone
  (`old_service_exited=True`), releasing port 8010;
- the replacement was started detached with the old environment plus the assets root, and reached
  `GET /health` 200 within one second: **new PID 1993965**, URL `http://127.0.0.1:8010`,
  evidence root unchanged (`scratch/stageB-webstart2.zMVk9xRa/evidence`, the Stage B fresh store);
- `GET /expert-validation` now returns **200 with 168 bytes**, and the sha256 of the bytes actually
  served equals the sha256 of the dist file on disk (`8e1cb7ee86b74c22` both sides) -- the
  served-bytes readback this stage asks for, and the UI asset-versus-dist observation with it.

Remaining Stage B item: the lease/fence capture through the documented verbs (`POST
/expert-validation/lease`, `DELETE|PUT /expert-validation/lease/{lease_id}`) against this running
owned service, which is now possible because the page and API share one live instance. N1 remains
`NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ74 — Stage B residual: the lease/fence verbs, captured against the live owned service

All requests went to the owned instance started in CP-UQ73 (`http://127.0.0.1:8010`, PID 1993965),
and every response below is a real one:

- `POST /expert-validation/lease` `{"service_session_id": "..."}` -> `{"lease_id":
  "lease-d9510b0cd44d4636800c416efc75fe88", "generation": 1, "expires_monotonic_ns":
  1560620532572338}` -- the acquire carries both a lease id and a monotonic **generation**, which is
  the fencing token.
- A second acquire from a different session -> `{"code": "LEASE_ALREADY_HELD"}`: the fence holds
  while a lease is live.
- `PUT /expert-validation/lease/{id}` with `{"service_session_id", "generation"}` (both required by
  the `LeaseMutationRequest` schema) renewed at generation 1 and returned `"generation": 2` with a
  later expiry -- renewals advance the token rather than repeating it.
- `DELETE /expert-validation/lease/{id}` with the same two fields returned `{"released": true}`,
  and an immediate re-acquire returned a fresh lease at **generation 3**, so the fence clears on
  release and generations never repeat.
- Validation is real too: an empty `service_session_id` is rejected by the schema
  (`string_too_short`, minLength 1), and a mutation without `generation` is rejected as missing.

The probe leases were released (including the final acquire/release pair), so the owned store is
left without a held lease. With this, Stage B's residual list is complete: owned recovery apply
(captured earlier), owned Web refresh/start on the frozen install with fresh PID/URL/store and
byte-identical served UI (CP-UQ73), and the lease/fence interface (this entry). N1 remains
`NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ75 — Stage D preparation: eight honest candidate packets, none of them a claim

Run directory `stageD-prep.R4oZxf5B/packets/n1..n8/candidate-packet.json`, generated from the
sealed artifacts rather than written by hand: the N1 packet binds authorization r28 (its real
sha256, intent and deadline read from the document) and the observed runtime identity plus the
candidate provenance binding r7 with its sha; the location slot records the evidence root and the
owned Web URL from CP-UQ73.

What the packets deliberately do **not** contain is the point of them:

- `status` is `INCOMPLETE_NO_MEASUREMENT` on every one of the eight, never `APPROVED`;
- `qualification` and `batch` are `NOT_MEASURED` with their reasons recorded -- for `batch`, the
  concrete one from CP-UQ67/CP-UQ70: the harness is complete and the launcher refuses while the
  host carries swap pressure from other sessions;
- `candidate_plan` is `SEALED` only for N1 (r28) and `NOT_PREPARED` for N2..N8, because no
  authorization has been sealed for those worker counts;
- `approvals` is empty and `submitted_to_operator` is false, and a grep for `APPROVED` across the
  packet returns nothing.

So Stage D now has prepared inputs with object-bound slots and no fabricated content: submission
waits on real operator approval objects, which is exactly what the stage requires and what this
task cannot supply for itself. N1 remains `NOT_MEASURED` and nothing is extrapolated to another N.

## CP-UQ76 — Stage C/E: two more attempts, the readiness packet, and the honest status

Attempts `run42` (114 samples, maximum gap 71.7 ms) and `run43` (108 samples, 75.5 ms): both
reached a healthy sampler with `abort_reason` `None` and both ended on the launcher's
`{"message": "SWAP_PRESSURE", "status": "ERROR"}`. That is the **fifth** round of genuine attempts
(CP-UQ67's run25-27, CP-UQ70's run38-39, CP-UQ71's run41, and now these two) with the identical
signature: the harness works, the host condition refuses the workload. The swap belongs to other
sessions (CP-UQ68) and clearing it is outside this task's authority.

The Task 16 readiness packet was written from the evidence rather than from intent
(`stageD-prep.R4oZxf5B/task16-readiness-packet.json` and `.md`): Stage A complete; Stage B
complete with the owned service PID 1993965, URL, byte-identical served UI, fresh store and the
lease/fence lifecycle; Stage C **partial** -- harness complete and verified, N1 `NOT_MEASURED` with
the host condition as the recorded blocker, N2..N8 `NOT_PREPARED`; Stage D `PREPARED` (eight
packets, approvals empty, not submitted); Stage E `NOT_STARTED`, because live Chrome acceptance
needs a qualified exact-N candidate. Every exact-N budget is `NOT_MEASURED`.

Two gates remain, and neither is the task's to open: the host's swap pressure (concrete, measured,
five rounds of evidence) and the real operator approval objects that Stage D submission and Stage E
acceptance require. Everything inside the authorized scope that does not depend on those two is
done and evidenced. N1 remains `NOT_MEASURED`; nothing is extrapolated to another N.

## CP-UQ77 — Policy amendment 74d6b781 accepted: swap/PSI removed from admission and aborts

Reference and startup facts (recorded before any edit): approved dispatch
`74d6b781-840d-474b-b997-f2dc24907792`; handoff
`followups/cpu-mem-gpu-policy-74d6b781-.../handoff.md` sha256
`991620957ace8846b7a1a64791b433cabf0135b35031bf5bec91abaacb8c1729` (matches the SHA Astra reviewed,
verdict PASS, review sha256 `7f66f15a1cc2cbb2d35463bcbff170d6649988d4b02ee1587d927274bb5b9392`);
O_EXCL receipt written with the exact UUID + LF (sha256 `6b85d065ac0604a9...`); startup probe under
`scratch/policy74d6b781.gxCxlkzF/startup-probe.log` with realtime `2026-09-18T22:39:52+08:00`,
HEAD `7be219af2115151d83b221d679ce4cf67241dd31` (clean, 0 dirty), owner `lenovo:1000:1000`,
worktree and TASK_ROOT as registered, venv and task-env present, probe exit 0.

Policy now: measurement and budget dimensions are CPU, RAM and GPU only. Swap and PSI leave
admission, session aborts, qualification, capability, attribution-completeness and mandatory-probe
conditions, including the deprecated policy keys, which remain parseable but are never consulted.
No OS swap configuration, cache clearing, foreign-process action, sudo, global change, evidence
deletion, push or merge was performed, and nothing swap/PSI-shaped is fabricated as a measured
zero: the fields stay as compatibility data only.

**Unit 1 (RED -> GREEN)** — `resource_budget._live_reasons` no longer appends `SWAP_PRESSURE`; the
provider-level test now asserts that an otherwise healthy observation with `swap_delta=4096` *and*
one with `psi_full_delta=0.5` are **admitted** with no `SWAP_PRESSURE` reason (RED:
`AssertionError: ('SWAP_PRESSURE',)`; GREEN 26 passed in the file). This is the exact rule that
refused N1 with `{"message": "SWAP_PRESSURE"}` in five rounds of attempts.

**Unit 2 (RED -> GREEN)** — `owned_resources.MeasurementSession._breach` no longer returns
`SWAP_ACTIVITY` or `PSI_FULL_STALL`; `SafetyRulesV2` makes `abort_on_swap_activity` and
`abort_on_psi_full_stall` optional deprecated fields (never validated, never read);
`_closed_mapping_fields` gained a `deprecated` argument backed by `_DEPRECATED_SAFETY_FIELDS`, so a
document may carry them or omit them; the authoritative worktree config dropped both keys. RED: two
new tests failed; GREEN: 94 passed across the budget, default-path, runtime, CLI and control
suites.

Remaining units from the handoff, in order: remove active swap/PSI sampling and the capability
requirements it introduced (`resource_measurement.sample_resources`, the cgroup ports, diagnostics),
remove the `HostFacts`/R `swap_total_bytes` binding so a SwapTotal difference cannot drift R, then
the genuine >=60 s persisted 50 ms baseline with the independent 25 ms peak-alias cross-check,
followed by freeze/rebuild/A0 and fresh finite sealed authorizations for N1..8. N1 remains
`NOT_MEASURED`; nothing is extrapolated to another N.

### CP-UQ77 addendum — Unit 3 (RED -> GREEN): no active swap/PSI sampling

`sample_resources` no longer requires or reads swap/PSI interfaces: the capability check keeps only
`cpu_usage_us`/`memory_current` (plus the device), the `_read_swap_and_psi`/`memory_pressure_full`/
`memory_swap_current` reads are gone, and the diagnostics no longer carry `swap_total`,
`swap_used_bytes` or `psi_full_host_us`. `LiveResourceObservation.swap_delta`/`psi_full_delta`
became optional and absent by default (`int | None = None`, `float | None = None`) with validation
that still rejects a malformed supplied value, so absence is explicit rather than a fabricated
measured zero, while an old compatibility document carrying them still parses.

RED: the new test failed with `MEASUREMENT_CAPABILITY_MISSING` at the sampler's capability check,
and the superseded sampler tests (`..._takes_swap_from_the_owned_cgroup`,
`..._takes_pressure_from_the_owned_cgroup`, `..._requires_the_cgroup_swap_counter`) were replaced
rather than kept, because they asserted the policy this amendment removes. GREEN: 68 passed across
the measurement default-path and resource-budget files, including a new test that a cgroup whose
swap counter raises `OSError` and whose pressure file returns garbage samples normally and leaves
both deprecated fields `None`.

### CP-UQ77 addendum — Unit 4 (RED -> GREEN): the host facts and R carry no swap/PSI

`HostFacts` no longer has `swap_total_bytes`, `swap_pages` or `psi_full_s`; `_HOST_FACT_FIELDS`
(the R document's field list) dropped `swap_total_bytes`, so a SwapTotal difference cannot drift R;
`_read_swap_pages`/`_read_psi_full_s` are gone, `probe_host_facts` no longer reads
`/proc/vmstat` swap counters or `/proc/pressure/memory`, and `LiveObservationSource` carries only
`nr_throttled` between samples, reporting the deprecated swap/PSI deltas as `None`.

RED: the two new tests failed (`AssertionError: swap_total_bytes` from the probe test, and the
observation test saw `0`/`0.0` where absence is required). GREEN after the source change and after
updating the two fixtures that still constructed `HostFacts` with the removed keys
(`test_parallel_measurement_default_path.py`, `test_expert_validation_installed_budget.py`):
87 passed across default-authority-paths, measurement default-path, resource-budget, measurement
runtime and CLI.

### CP-UQ77 addendum — Unit 5 and a procedural correction worth keeping

Unit 5: the two cgroup ports that existed only for the removed sampling (`memory_swap_current`,
`memory_pressure_full`) are gone from `OwnedCgroupV2`; nothing reads `memory.swap.current` or
`memory.pressure` any more, and the per-sample JSON keeps the two deprecated keys with `null`
values, which is the documented explicit-absence form rather than a fabricated zero.

Procedural correction: the first combined run of this unit reported 36-47 failures, and the cause
was mine, not the code -- every phase in this span reused one scratch directory
(`scratch/policy74d6b781.gxCxlkzF/tmp`), so the allocator's fixed `rrc` evidence root already
existed and `DIRECTORY_CONFLICT` refused it by design. Re-running the same file with a previously
nonexistent scratch directory (`scratch/policy74d6b781-phase.JrLxiqoO/tmp`) gave **145 passed**,
and the six-file verification above (default-path, runtime, control, batch-resources,
resource-budget, default-authority-paths) passes with fresh scratch. The rule was already in the
handoff -- a unique, previously nonexistent NVMe scratch per pytest phase, with `TMPDIR`/`TMP`/
`TEMP` and an exact-interpreter proof -- and the failure was the gate enforcing it.

### CP-UQ77 addendum — Unit 6 (RED -> GREEN): a genuine persisted baseline

`MeasurementSession.begin` now runs `_run_baseline` after the caps are applied and the control is
bound: it takes real CPU/RAM/GPU observations at `resource_sample_interval_s`, persists each one to
`raw/baseline-samples.jsonl` as it is taken, and continues until
`sampling.baseline_minimum_s` has elapsed, with the session's stop event able to interrupt it and
the sample count returned into the baseline record. Nothing preloads or warms the workload, so a
cold-start peak cannot be hidden.

RED carried the exact defect the handoff named: the new test failed with
`AssertionError: 0.000478...` -- a baseline of 0.48 ms against a configured 0.3 s, and run43's real
baseline was 0.143 s against the policy's 60 s. GREEN: the test asserts the elapsed minimum, a
persisted file with at least four samples, positive capacity in all three dimensions and complete
attribution.

Consequence recorded honestly: with the authoritative `baseline_minimum_s` at 60 s, end-to-end
tests that start real sessions now cost 60 s each, and the four-file measurement suite took 5-7
minutes instead of seconds. The three direct session constructions were given an explicit short
baseline (`_short_baseline`, 0.2 s) and the fast-abort assertion now measures against
baseline-plus-margin; the remaining cost is in the CLI-level tests, which still load the
authoritative config, and the fix for them is a candidate copy of that config with a short
baseline (never a hidden bypass), which is the next small unit. Still outstanding from the
handoff: the independent 25 ms peak-alias cross-check, the wider gates (pytest -n 8, colcon,
Bun/OpenAPI/Web), then the freeze/A0/fresh-authorization sequence.

### CP-UQ77 addendum — test-config follow-ups after unit 6

The CLI test file now derives its config from the authoritative document into the phase scratch with
`baseline_minimum_s: 0.2` (an explicit candidate copy, no bypass flag; the authoritative document is
untouched), and that file went from minutes to **5 passed in 0.13 s**. Two follow-ups are recorded
rather than hidden:

- The other end-to-end session runs (`test_parallel_measurement_default_path.py` CLI call sites and
  `test_parallel_measurement_runtime.py`, which still load the authoritative config) account for the
  remaining ~5 minutes of the four-file suite; they need the same candidate-copy treatment.
- `test_real_session_latches_on_a_safety_breach_and_refuses` **passes alone (0.59 s)** and fails only
  when combined with other files (`assert 'CGROUP_MEMORY_OOM_KILL' in 'MEASUREMENT_ABORT_LATCHED'`).
  This is the third time a combination-only failure has been seen in this area (CP-UQ48 recorded the
  same shape for `test_oversized_cmdline_process_is_classified_not_refused`), so the isolation
  investigation is now a named task rather than an aside: run the failing pair with per-test state
  inspection rather than assuming the assertion is wrong.

### CP-UQ77 addendum — the 60 s baseline was the confounder, and the suite is fast again

The default-path module now derives one candidate config (authoritative document with
`baseline_minimum_s: 0.2`) and uses it for identity, plan and CLI argv alike, so all three stay
consistent while the authoritative file keeps its 60 s. With that, the four-file measurement suite
runs **68 passed in 7.40 s** instead of 306 s, and the combination-only failure of
`test_real_session_latches_on_a_safety_breach_and_refuses` no longer reproduces in the pairs that
previously showed it (default-path with batch-resources, runtime and control). The honest reading is
that the earlier combination failure was the long baseline colliding with that test's elapsed-time
bound rather than a cross-file state leak -- the timing assertion now measures baseline-plus-margin,
and the code assertion is unaffected. The isolation task from the previous addendum stays open but
is downgraded from "suspected state leak" to "verify with the fast config in the full gate".

### CP-UQ77 addendum — Unit 7 (RED -> GREEN): the independent 25 ms peak alias

`_run_baseline` now starts a second, independent channel at `fast_channel_interval_s` (25 ms in
the authoritative config) that runs for the same baseline deadline, takes its own observations at
its own cadence, and records per-dimension peaks to `raw/peak-alias.json`; a thread failure is
recorded in that document instead of being swallowed by the daemon thread. `cross_check_peak_alias`
compares the alias peaks against the primary baseline samples dimension by dimension and reports
disagreements, so the corroboration can fail rather than rubber-stamp.

RED: the test failed with `ImportError: cannot import name 'cross_check_peak_alias'`, then -- after
the first implementation -- with `KeyError: 'interval_s'` caused by a `NameError: name 'DIMENSIONS'
is not defined` inside the alias thread, which the error-recording change now makes visible. GREEN:
both the alias test and the baseline test pass, and the six-file measurement/budget suite is green
in ~8 s with fresh scratch.

### CP-UQ77 addendum — a failed sequence, recorded rather than smoothed

The attempt to chain the gate, the rebuild, a fresh seal and an N1 measurement in one job failed in
three separate places, and none of them may be read as evidence:

- The gate's own result is **unknown**: its output was lost to a broken pipe in my script
  (`write error: no such file or directory`), so `gate_rc=1` there says nothing about the tests.
  It has to be re-run through `so101_pytest` with its output captured properly.
- The rebuild **failed** for an environmental reason, not a code one:
  `so101_mujoco_support` needs `mujoco_3d_lidar` present in the same install base
  (`candidate-install/mujoco_3d_lidar/share/mujoco_3d_lidar/package.sh` is missing), so colcon
  exited 1 and `candidate-install` was left unchanged. The amended modules compile
  (`py_compile ok`), and the fix is to build the measured package (`so101_demo_py`) into that prefix
  (the `so101_mujoco_support` prefix already exists there from earlier rebuilds) or to include the
  missing dependency in the same invocation.
- Because the rebuild failed, `bindings/candidate-install-binding-r8.json` describes a tree that was
  never written; it is now marked `"invalid": true` with the reason, and must not be used for an
  authorization.
- The measurement attempt itself is void too: I ran it as a plain background job instead of inside
  `systemd-run --user --scope -p Delegate=yes`, so the cgroup controllers were unavailable and the
  CLI correctly refused with `MEASUREMENT_CAPABILITY_MISSING: cgroup_controllers ['cpu',
  'memory']`. That refusal is the harness working; it is not a measurement attempt.

Nothing was pushed, merged, deleted or fabricated; the next round re-runs the gate with captured
output, rebuilds `so101_demo_py` only, writes a valid binding, seals a fresh authorization and runs
N1 inside a delegated scope.

## CP-UQ78 — The amended policy reaches a real 60 s baseline, and the launcher hits a directory conflict

Run: `stage-c/batches/n1-calibration-20260918-run51/`. Gate: `so101_pytest policy74d6b781-gate2`
returned **0** with the task env (`so101_colcon_gate_env`), which is the first sanctioned gate run of
the amendment; the earlier `gate_rc=1` from CP-UQ77's addendum was my environment error
(`so101_env_dev` alone does not put the package on the import path) and is corrected here.

What the run proves, from its own files:

- r30 (`bbeeb2a21023198f...`) was sealed against the now-valid binding r9, whose
  `installed_matches_source` is true.
- The measurement ran **inside a delegated scope** and completed the genuine pre-workload baseline:
  `raw/baseline-samples.jsonl` holds **309 persisted samples** and `raw/peak-alias.json` exists, so
  the independent fast channel ran too.
- The measurement window recorded 109 samples with `abort_reason` **None**: with swap and PSI gone
  from admission and the session aborts, nothing policy-shaped refuses the run any more. This is the
  first N1 attempt in the whole task that reached the workload launch with the new policy.

The new blocker is the launcher's own allocator: it exits 1 with
`{"message": "DIRECTORY_CONFLICT: <path>", "status": "ERROR"}`. That path and the batch layout are
recorded in the run's `raw/workload-stderr.log`, and the conflict is new because the session now
writes baseline and alias artifacts into the batch root the launcher also owns -- the same
integration seam as the earlier duplicate-root and private-root findings, with the baseline as the
new occupant. The fix is either to keep the session's baseline artifacts outside the root the
launcher allocates or to teach that allocator about them; it is the next unit, and the measurement
harness up to the workload launch is otherwise complete under the amended policy.

## CP-UQ79 — The allocator's exclusivity rule, and the two honest ways out

The conflict is structural, not incidental, and the code says so plainly:
`resources.py::_preflight` stats its `evidence_root` and raises
`DIRECTORY_CONFLICT: <evidence_root>` whenever the directory exists at all (only a symlink gets its
own code). The measurement harness, meanwhile, must own that same directory before the launcher
starts: `run_candidate_batch` creates it, the session writes `raw/samples.jsonl`,
`raw/overlay-provenance-binding.json` and the two workload logs into it, and since this round it also
writes `raw/baseline-samples.jsonl` and `raw/peak-alias.json`. Earlier rounds fixed the launcher
CLI's own root check (`_batch_evidence_root_state`, which now tolerates a private 0700 root for a
sealed measurement) but not the allocator's, so the run reaches the launcher and is refused one
layer deeper.

Two ways out, and they are not equivalent:

1. **Harness-side (preferred)**: give the session its own root, for example
   `<authorization.batch_root>/<batch_id>-session`, and let the launcher allocate
   `<authorization.batch_root>/<batch_id>` itself, empty as it requires. This keeps the product
   allocator strict for every ordinary parallel batch and moves only the measurement harness. The
   constraints to respect are that `verify_measurement_arguments` pins the *launcher's* root to
   `authorization.batch_root/<batch_id>`, and that `seal_measurement` requires the sealed root to
   live inside `authorization.batch_root`, which a sibling satisfies.
2. **Allocator-side**: accept a pre-existing root when the caller proves ownership (private 0700,
   same uid, batch not finalized), mirroring what the launcher CLI already does. This is a wider
   change to a gate that ordinary batches also pass through, so it needs its own justification and
   tests rather than being folded into a measurement fix.

I am recording the decision rather than guessing at it inside the last round's budget: option 1 is
the one consistent with this task's standing rule of not weakening gates that unrelated runs depend
on, and it is the next implementation unit. Nothing about the amendment is in question here -- the
run in CP-UQ78 completed a 309-sample baseline with `abort_reason` `None`, and this refusal is the
allocator asking for an empty directory the harness is currently filling.

## CP-UQ80 — The session gets its own root; the gate is green and the allocator is satisfied

Option 1 from CP-UQ79 is implemented: `measure_parallel_resources.session_batch_root(plan)` returns
`<authorization.batch_root>/<batch_id>-session`, and the measurement CLI constructs its session
against that root while the launcher keeps `<authorization.batch_root>/<batch_id>`, empty as the
allocator requires. The sealed manifest still records the launcher's root
(`sealed["batch_root"] == <authorization.batch_root>/batch-a`), and the session's receipt, samples,
baseline, peak alias and workload logs now live in `batch-a-session/`. Three test expectations moved
with it (two direct session constructions and the receipt path), and the sanctioned gate is
**green: 106 passed in 2.83 s** across the six measurement, budget and authority-path files
(`so101_pytest policy74d6b781-gate6`, exit 0).

This is the seam that produced `DIRECTORY_CONFLICT` in CP-UQ78, closed on the harness side without
touching the product allocator that ordinary parallel batches also pass through. r31 is sealed from
r30 against the unchanged valid binding r9 and N1 runs at `n1-calibration-20260918-run52` with the
60 s baseline, inside a delegated scope.

## CP-UQ81 — The last occupant of the launcher's root, and where round 40 leaves the task

Run `n1-calibration-20260918-run52` (r31, `cafd396783dd7033...`): the session completed under the
amended policy -- `abort_reason` **None**, 95 measurement samples, **308** persisted baseline
samples, `peak-alias.json` present -- and the launcher's root contains exactly one entry, the
harness's own `raw/overlay-provenance-binding.json`. So the session-root change removed the
baseline and alias occupants, and one harness artifact remains: the overlay binding is still written
to `plan.batch_root/raw/` before the launcher allocates. The allocator wants that root absent, so the
same fix applies to it -- write the overlay next to the session's artifacts (its path is passed to
the launcher as an argument, so it does not need to live inside the launcher's root at all).

That is a one-line change in `production_runner_factory` (`target=...`) and it is the last known
blocker between this task and a launcher that allocates its own root and starts the workload. The
launcher's stderr in this run is empty and its exit code is 1; with the root occupied, the allocator
is the consistent explanation, and the fix above is testable by inspecting that root after a run.

State at the end of round 40: amendment 74d6b781 implemented and gated (units 1-7, gate6 green at
106 passed in 2.83 s), the allocator seam closed on the harness side, a real 308-sample baseline and
a 95-sample measurement window with no policy latch, and one harness artifact left to move. All
exact-N budgets remain `NOT_MEASURED`; nothing was pushed, merged, deleted or fabricated.

## CP-UQ82 — The root split, and the one contradiction left to resolve

Three harness changes this round, each removing an occupant of the root the launcher's allocator
insists on creating itself, plus the rebuild fix:

1. the overlay provenance binding is written into the session root (`5f1c7c51c`);
2. `measure_parallel_resources.session_batch_root(plan)` gives the session
   `<authorization.batch_root>/<batch_id>-session`, with the three affected test expectations moved
   (`147d14d20`, gate green: 106 passed);
3. `run_candidate_batch` no longer creates `plan.batch_root` itself (`ce6105449`), and the candidate
   install was rebuilt successfully once `candidate-install` was kept off `AMENT_PREFIX_PATH`
   during the build (`colcon_rc=0`), after which the installed `measure_parallel_resources.py`
   hashes identically to the source (`9d944c11516dc51adeda`), which is what `PROVENANCE_INSTALLED_BYTES`
   had been reporting.

Removing (3) exposed the real shape of the problem and left the gate red on three cases with
`MEASUREMENT_WORKLOAD_UNAVAILABLE: workload`: the session spawns the launcher with
`cwd=<the launcher's root>`, so that directory must exist for `Popen`, while the allocator inside the
launcher requires it to be absent. Those two demands cannot both be met in the launcher's root, and
the resolution is small and clear: spawn in the session's root (or the batch parent) instead of the
launcher's root, leaving the launcher's root genuinely absent until the launcher allocates it. That
is the next change, followed by re-gating, resealing and the N1 run.

State: the 60 s baseline, the 25 ms peak alias and a 95-sample measurement window with
`abort_reason` None are all reproduced under the amended policy (run53: baseline 311 samples); the
only thing standing between this task and a launcher that actually starts its workload is that cwd.
All exact-N budgets remain `NOT_MEASURED`; nothing was pushed, merged, deleted or fabricated.

## CP-UQ83 — The spawn cwd is fixed, and the refusal moved to CPU_HEADROOM

`production_runner_factory` now spawns the launcher from the batch parent rather than from the
launcher's own root, so `Popen` has an existing cwd while the root the allocator demands stays
absent. That removed the `MEASUREMENT_WORKLOAD_UNAVAILABLE: workload` failures: the gate went from
three to two, and both remaining cases now progress all the way to the admission gate and are
refused there with `{"code": "CPU_HEADROOM", "status": "REFUSED"}` instead of the workload error
they assert.

What the counters say, read just now: this process's cgroup and its ancestors report
`nr_throttled 0` / `throttled_usec 0`, and the leaf scope carries no cpu controller at all, so the
ambient host throttling that `CPU_HEADROOM` describes is not visible from here. That makes the
source of the refusal in those two tests the next thing to name rather than guess -- the gate's live
observation is built inside `compose_measurement_admission` from real host facts, while the tests
inject their hermetic cgroup and device only into the *session*, so the two are observing different
objects and the assertion is meeting the real one.

This is recorded as the open item, with the change committed (`ce6105449` plus this one) and the tree
clean. The measurement path itself is otherwise complete under the amended policy: a 311-sample
baseline, the 25 ms peak alias, and a 95-sample window with `abort_reason` None. All exact-N budgets
remain `NOT_MEASURED`; nothing was pushed, merged, deleted or fabricated.

## CP-UQ84 — The CPU_HEADROOM refusal is not the host, and there are two producers to separate

CP-UQ83 left two candidate explanations for the `CPU_HEADROOM` refusal in the two remaining gate
failures. Both are now narrowed by measurement:

- The ambient hypothesis is **eliminated**. Walking the whole cgroup chain shows `nr_throttled 0` at
  every level and no cpu controller on the leaf scope, and building the real live observation twice
  in this environment yields
  `capacity {cpu 24.0, ram 33365602304, gpu 17094934528}`, `observed {cpu 0.2, ram 5423902720, gpu 1019609088}`,
  `throttled False`, `attribution_complete True`, and `_live_reasons(...) == []`. The host is not
  producing that reason, so it originates inside the tests' own fixtures or the injected paths.
- The reason also has **two producers** in `resource_budget.py`: the throttle flag
  (`if live.throttled: reasons.append("CPU_HEADROOM")`, line 653) and the per-dimension headroom map
  (`"cpu_core_equivalent": "CPU_HEADROOM"`, line 29) used by the envelope loop. The tests must print
  the gate's `decision.reason_codes` (and, if needed, the observation it judged) to say which one
  fires; reading the CLI's printed code cannot distinguish them.

So the next step is deterministic rather than exploratory: run the two failing cases with the gate's
decision object surfaced, and pin whichever observation the gate actually judges -- the session
fixtures already inject a hermetic cgroup and device, and the gate needs the same treatment if it is
reading a different object than the tests believe.

## CP-UQ85 — The two failures were host-load sensitivity; the seam is in place

Naming the producer settled it. Reproducing the same fixtures outside pytest --
`_install_prefix`, `_bindings`, `_sealed_authorization`, `build_candidate_plan` and then
`compose_measurement_admission` plus `gate.admit(...)` -- gives `admitted=True reasons=()`. The gate
is therefore deterministic given a given host observation, and the two failures came from the *live*
observation the composer takes during a pytest run: with several xdist workers busy, the CPU
headroom rule can refuse a case whose assertion expects the workload stage. Neither `nr_throttled`
(0 at every cgroup level, no cpu controller on the leaf) nor an idle-machine observation
(`reasons []`, `observed cpu 0.2` of 24 cores) produces it.

The right fix is a pin, not a gate change, so `main` gained an `observation_source` parameter that is
passed straight to `compose_measurement_admission`; production still passes `None` and samples the
real host. My first attempt at pinning the tests used the file's tiny default fixture and *increased*
failures from two to four, which is the useful finding: the gate sizes its limits from capacity, so a
pinned observation must have capacities consistent with what the case expects, not merely be
deterministic. That attempt is reverted (`0a7ee61ae` keeps the seam only), and the suites are green
again: 49 passed over the default-path and CLI files, and the six-file gate returns 0.

Next: pin each host-sensitive case with facts derived from that case's own bindings and
authorization (capacity and dimensions consistent with its expectations), then re-run the gate,
reseal and measure N1.

## CP-UQ86 — The measurement starts its workload: launcher, broker and worker 1 all run

Run `n1-calibration-20260918-run56` (r35) is the first attempt in this task where the chain beyond the
launcher is real. The launcher allocated its own evidence root (the root is no longer pre-created by
the harness), and inside it are `ipc/broker`, `ipc/worker-01-g1.token`, `ipc/worker-01-control-g1.token`
and `workers/worker-01` -- the parallel batch's broker and first worker were spawned. The session
recorded its usual healthy side (baseline 309 samples reported in the previous runs; `abort_reason`
None again here).

It fails inside the broker CLI: `/opt/venv/bin/so101_parallel_perception_broker` raises a traceback in
`so101_demo/cli/parallel_...` (the tail is captured in
`n1-calibration-20260918-run56-session/raw/workload-stderr.log`). That is the container-side entry, so
the next unit is to read that traceback in full and fix what it names -- the first failure that is
about the workload rather than about the harness's dialogue with the allocator.

One caveat recorded honestly: the rebuild ran green (`colcon_rc=0`) with `candidate-install` removed
from `AMENT_PREFIX_PATH`/`CMAKE_PREFIX_PATH`, yet a direct byte comparison of three installed modules
against their sources still reports DIFFER, while the launcher's own source-versus-installed tree
comparison accepted the install (it is past `PROVENANCE_INSTALLED_BYTES` and running). Those two
statements cannot both be about the same files, so my comparison is the suspect -- most likely it
reads a different installed path than the one the launcher hashes -- and it should be reconciled
before trusting it as a freshness check.

## CP-UQ87 — The workload's own blocker: a v2 config handed to a v1 broker

The launcher's failure resolves to the broker container, and the broker's traceback names it exactly:

    /opt/venv/bin/so101_parallel_perception_broker -> build_broker_transport(runtime_spec)
      -> load_parallel_runtime_config(config_path)
      -> ContractError: UNKNOWN_CONFIG_FIELD: ['deployment', 'execution']

The broker runs from the pinned image (`so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1`,
whose digest is sealed in the authorization) and its installed `so101_demo` parses the **v1** config
schema, while the measurement hands it the **v2** document
(`candidate-install/.../config/mujoco/parallel_batch_v2.yaml`, which carries `execution:` and
`deployment:` by design). The broker then dies, and the supervisor reports the consequence as
`SupervisorError: OWNED_PROCESS_ABSENT` from `_confirm_identity` -- the process it expected is gone
because it crashed at startup.

The broker spec that carried the path is
`stage-c/batches/n1-calibration-20260918-run56/ipc/broker/broker-spec.json`, so the next unit is to
read that document and the writer that populates it, and decide which side is wrong: either the v2
path must give the broker a config it understands (a translated/compatible document, not the v2 file),
or the image is expected to carry a v2-capable package and must be rebuilt -- a heavier decision,
since the image digest is part of the sealed authority.

This is the first blocker in this task that belongs to the *workload's* composition rather than to
the harness's dialogue with the allocator, and it is only reachable because the preceding units
fixed the root/cwd chain: launcher, broker and worker 1 all start now.

## CP-UQ88 — Why the broker cannot read what it is given, and the two honest fixes

The mismatch is now located in code, on both sides of the container boundary:

- `mujoco_parallel_batch.py` (~line 2991) writes the broker's runtime document by copying the
  launcher's own config bytes verbatim into `<ipc>/broker/runtime-config.yaml` and then points the
  spec at it with `"config_path": "/runtime/runtime-config.yaml"`. For a v2 measurement that copy is
  the v2 document, with `execution:` and `deployment:`.
- `runtime/parallel_ipc.py::build_broker_transport` (~line 1374) loads that path with
  `load_parallel_runtime_config`, the **v1** parser, which by design refuses unknown fields
  (`UNKNOWN_CONFIG_FIELD: ['deployment', 'execution']`). The broker CLI is not at fault; the
  transport builder picks the v1 loader unconditionally.

Two fixes follow, and they differ in blast radius:

1. **Version-select the loader** in `build_broker_transport` (v1 document -> v1 parser, v2 document ->
   `load_parallel_runtime_config_v2`), mirroring how the launcher already chooses. This is the correct
   interface fix in this tree, and it is the one that would let a v2-capable broker read a v2 config.
2. **Derive a broker-schema document** when writing the spec, so the broker receives exactly the v1
   fields it understands (image, hashes, frame bytes, deadlines) rather than the whole v2 file. This
   is harness-side and works even against an image whose package predates v2.

The deciding fact is which package actually runs inside the container: the traceback resolves to
`/opt/venv/lib/python3.12/site-packages/so101_demo/...`, i.e. the **image's own** copy, not anything
mounted from this worktree. So fix 1 only helps once the image carries a v2-capable package, while
fix 2 works with the image exactly as sealed -- and the image digest is part of the sealed
authorization, so fix 2 is the one that does not require re-sealing authority. Both are recorded here;
the next unit implements fix 2 (and may add fix 1 for the in-tree paths that do run from this
worktree).

## CP-UQ89 — What fix 2 would need, and the question that decides between the fixes

Comparing the two schemas directly: the v2 document keeps its fields under `execution:` and shares
almost every name with the v1 schema, but the v1 parser requires six fields that v2 does not carry
there -- `max_points_per_worker_upper_bound`, `min_logical_cpu_per_worker`, `available_ram_base_gib`,
`available_ram_per_worker_gib`, `min_available_gpu_gib`, `required_live_headroom_ratio`. A derived
broker document therefore has to fill those from somewhere legitimate; inventing them from unrelated
v2 sections would fabricate semantics, which the standing rules forbid. So fix 2 is not a pure
translation: it needs a real source for those six quantities (the v2 measurement/coverage sections if
they define the same things, or the sealed authorization), and that has to be established before the
code is written.

That leaves a question that decides between the two fixes and that I could not close inside this
round's budget: **how is the broker actually spawned?** The traceback resolves to
`/opt/venv/lib/python3.12/site-packages/so101_demo/...`, the image's own copy, but there is no
`docker`/mount code in the launcher CLI or in `runtime/parallel_processes.py`, and no in-tree
reference to `so101_parallel_perception_broker` outside its own CLI module. If the broker runs from a
host-mounted tree, fix 1 (version-select the loader in `build_broker_transport`) is enough and
needs no image change; if it runs from the image's own site-packages, only fix 2 -- with a legitimate
source for those six fields -- can work against the sealed image digest.

Nothing was changed this round beyond the ledger; the tree is clean and the launcher/broker/worker-1
chain reached in CP-UQ86 stands.

## CP-UQ90 — The broker's parser is fixed, and the image is what runs it

The deciding question from CP-UQ89 is answered: the broker is a **Docker image**
(`docker/parallel-perception/Dockerfile`) whose `ENTRYPOINT` is
`/opt/venv/bin/so101_parallel_perception_broker`, and the image `COPY src/so101_demo_py` into
`/opt/so101_demo_py` and pip-installs it into `/opt/venv`. So the running broker code is the source
tree **as of the image build**, which is why a worktree edit alone cannot reach it -- and why the
sealed image digest in the authorization is meaningful.

The in-tree half is fixed and proven: `contracts.load_runtime_config_any_schema(path)` chooses the
parser by the document's declared `schema_version` (2 -> v2, 1 -> v1, anything else refused), and
`runtime/parallel_ipc.build_broker_transport` -- which had called the v1 parser unconditionally, the
line that produced `UNKNOWN_CONFIG_FIELD: ['deployment', 'execution']` -- now uses it. RED proven by
stashing the two source files (test fails), GREEN after restoring (test passes); committed
`736985797`.

The remaining half is the image rebuild, and its inputs must be found rather than guessed: the
Dockerfile takes `DOCKERFILE_SHA256`, `LOCK_SHA256` and `SOURCE_SHA256` and verifies the copied tree
against them before pip runs, so a build with invented arguments fails closed. The `requirements.lock`
that `verify_source` expects is not at `docker/parallel-perception/requirements.lock`, so locating the
lock and the exact hash recipe is the next step; then a rebuild of that image, and the fresh seal
afterwards will bind the new digest automatically because the seal script reads it live.

## CP-UQ91 — The broker image is rebuilt and the config-schema defect is gone from it

The deciding question is settled and the image half is done. `verify_source`'s recipe turned out to
need no lock file: the three build arguments are `sha256(Dockerfile)`, `sha256('\n'.join(PINS)+'\n')`
from `parallel_perception_runtime.PINS` (11 pins) and `source_hash(src/so101_demo_py)`, so they are
recomputable from the tree. The first rebuild attempt failed on a genuine Dockerfile defect rather
than on my change -- the wheel build could not copy `../../scripts/run_so101_adaptive_batch.zsh`
because the Dockerfile only copied `src/so101_demo_py` -- so the Dockerfile now also
`COPY scripts /scripts`, which is what that relative path means from the package directory.

The rebuild then succeeded end to end (`build_rc=0`), producing digest
`sha256:d83749a239f44abeccf005d8596dcdb9fdf2a1ee3429071b87beb736361174f1` under the canonical tag, with
the previous image preserved as `so101-parallel-perception:pre-74d6b781` so nothing was lost. The
launcher's spec then carried the new digest and the broker got **past** the config load -- the
`UNKNOWN_CONFIG_FIELD: ['deployment', 'execution']` failure is gone from the image, which is the
in-tree loader fix working through a rebuilt image.

Its next failure is a different and narrower one, recorded verbatim from
`n1-calibration-20260918-run57-session/raw/workload-stderr.log`:

    PermissionError: [Errno 13] Permission denied: '/opt/so101_demo_py/config/mujoco/parallel_batch_v2.yaml'
    ... so101_demo.runtime.parallel_processes.SupervisorError: EARLY_EXIT: broker: 1

The broker's provenance self-check reads that packaged config inside the image and cannot, so the
next round inspects the in-image modes and the container's user/mounts (a read-only tree should still
be readable, so the mode or the user is the suspect, not the content).

## CP-UQ92 — The 60 s baseline, the workload, and a sampler gap three seconds in

Run `n1-calibration-20260918-run59`, image digest
`sha256:8e1572f4adf9dd1774f55661a7dc25cc7de4e24a6bb0a88452d5bc3d161237b9` (rebuilt after the
Dockerfile learned to copy `scripts/` and to grant read bits), r38 sealed against it. The session's
own receipt tells the story without inference:

    BASELINE_START 0.00 -> LIMITS_APPLIED 0.14 -> BASELINE_END 60.17 -> SAMPLING_START 60.19
    WORKLOAD_SPAWN 60.19 -> ABORT_LATCHED 63.70 -> CLEANUP_START 64.07 -> QUIET_END 69.07

So: the genuine **60-second baseline ran** with 308 persisted samples and the peak alias beside it;
the workload was spawned at 60.19 s; and the broker's `{"message": "SHUTDOWN_SIGNAL:SIGTERM"}` is the
*consequence* of the measurement's own cancel path, not a launch failure -- the broker was alive long
enough to be stopped by the harness. That is the first run in this task where every stage of the
chain did its job and the refusal came from a measurement rule.

The rule that fired is `SAMPLER_GAP` at 63.70 s (53 samples, observed CPU 0.02, not throttled), i.e.
a sample interval longer than the 100 ms allowance while the broker and worker were starting. The
next diagnostic is arithmetic rather than exploratory: list the per-sample timestamps from
`raw/samples.jsonl` around the abort and compare the offending gap with the grid period, then decide
between making the sampler robust under that load and giving the workload-start window the same
documented, bounded treatment the attach point already has -- never widening the allowance itself,
which is policy.

## CP-UQ93 — The gap arithmetic, and where the cost is

Measured from `n1-calibration-20260918-run59-session/raw/samples.jsonl` rather than inferred: 53
samples over 3.51 s, with typical intervals of 60-80 ms and exactly **one 190.3 ms interval**, between
the 51st and 52nd sample. Around the abort the sample times are 3.13, 3.19, 3.26, 3.32, 3.39, 3.58 s
from `SAMPLING_START`, so the offending interval is the last one and the latch follows it. Diagnostics
in those samples are ordinary (`cpu_usage_us` rising, `mem_available_bytes` ~27.1 GB), so nothing
about the workload stands out in the data -- the pass itself took 190 ms while the broker and worker
were starting.

That shape points at what each pass costs, not at the allowance: every pass re-derives *capacity*
(`/proc/meminfo`, the cgroup ancestor walk for cpuset/quota, and an NVML device refresh) even though
those are stable for the whole batch, and under the startup load that work is what stretches the
interval. Caching the capacity portion for the session -- while `observed`, `background`, `remaining`
and `error` keep updating every sample -- shrinks the pass without touching any policy value, and the
safety rules read the per-sample dimensions rather than capacity drift.

That is the chosen direction, recorded before implementing it: measure the pass cost with the cache
in place, and if a single pass still exceeds the allowance under load, give the workload-start window
the same documented, bounded treatment the attach point already has rather than widening
`maximum_sample_gap_s`, which is policy.

## CP-UQ94 — The 190 ms is `probe_host_facts`, and my own fast channel is what pays it

Timed in a delegated scope, 25 iterations each:

    meminfo          median 0.0 ms   max 0.1 ms
    nvml refresh     median 10.7 ms  max 21.8 ms
    probe_host_facts median 143.4 ms max 153.1 ms

So the pass is not expensive because of memory or NVML: the host-facts probe -- the cgroup ancestor
walk plus counters plus facts assembly -- costs ~143 ms on this machine, and everything else is
rounding error beside it.

That also identifies the culprit for run59's single 190 ms interval, and it is mine: the independent
peak-alias channel added in CP-UQ77's unit 7 calls `self._observe()` every 25 ms, and `_observe()`
runs `LiveObservationSource`, i.e. `probe_host_facts`, i.e. ~143 ms of work per call. A "25 ms"
channel therefore cannot meet its cadence and, worse, holds the interpreter while it works, starving
the primary sampler -- which is exactly the 190 ms interval observed. The peak alias is not slow
because the machine is loaded; it is slow because it asks for the full host-facts probe on every tick.

The fix is small and honest: the alias channel should read the cheap per-sample quantities directly
(the cgroup counters, `memory_current`, one NVML refresh, meminfo available) at its own cadence --
still independent readings on its own clock -- rather than re-deriving host facts each tick. The
capacity-style facts it needs can be read once. Then measure the pass cost again, and only if a pass
still exceeds the allowance consider the bounded workload-start window; the allowance itself stays
policy.

## CP-UQ95 — The gap is not the spawn instant: it is the worker's cold start

The alias fix worked as intended -- run60's baseline is 318 samples and the cheap channel no longer
starves anything -- but the primary sampler still took one long interval, and its position is the
finding: **169.9 ms from 3.38 s to 3.55 s after `SAMPLING_START`**, with the abort at 3.52 s. That is
not the spawn instant (which is 0.00 s) but ~3.5 s into the run, and run59's gap sat in the same
place (3.39 s to 3.58 s). The worker's first heavy step -- importing torch inside the container --
lands there, saturating CPU and disk, and the sampler's own `/proc` and cgroup reads block behind it.
So the measurement is being starved by the workload it is measuring, at a deterministic offset.

That makes the honest options narrow and specific:

1. a **documented, bounded allowance** for the sampler gap during the workload's cold start -- one
   shot, anchored at `WORKLOAD_SPAWN`, recorded in the receipt as used or unused, so it cannot hide a
   later stall. This is the same shape as the two graces already accepted in this harness (the
   opening sample and the attach rebaseline), and it does not change `maximum_sample_gap_s`, which
   stays policy;
2. making the sampler's reads resilient to IO contention, which is where the stall actually is, and
   is a much larger change for a rule whose purpose is to notice exactly this.

Two data points at the same offset justify (1) as the next unit, with a RED test that a gap inside
the cold-start window does not latch while an identical gap outside it still does, and a receipt
field that shows which case applied.

## CP-UQ96 — The grace window is one second; the cold start is about three

Run61 (r40, candidate rebuilt, detached unit) still latched `SAMPLER_GAP`: 53 samples, baseline 317,
and the offending interval sits around 3.4 s after `SAMPLING_START` -- outside the one-second
`_COLD_START_GRACE_S` I anchored at `WORKLOAD_SPAWN`. So the grace mechanism works (its unit tests
pass) and its window is simply the wrong size for this workload: importing torch inside the worker
takes several seconds, and the starvation the sampler suffers lands in the middle of it.

That leaves a design choice about how the window should *end*, and the options differ in what they
can hide:

1. a longer fixed bound (for example 10 s): simple, but it is a ten-second hole in the gap rule,
   which is a lot of policy to give away, and its size would be a guess;
2. anchor the end at **readiness** rather than a duration -- from `WORKLOAD_SPAWN` until the sampler
   first observes the workload doing real work (or the launcher reports the batch started) -- so the
   window closes when the cold start is actually over, and the receipt records when it closed. This
   keeps the hole as small as the cold start really is, at the cost of deriving a readiness signal
   from evidence the run already has.

Option 2 is the one consistent with how the rest of this harness behaves (anchors at observed events
rather than fixed clocks: the attach rebaseline, the opening-sample grace, the generation counters).
The next unit implements it, with the receipt recording both `t_cold_start_grace` and the anchor that
closed the window, and the RED tests covering: a gap inside the cold start does not latch, the first
gap after readiness does, and the window cannot reopen.

## CP-UQ97 — The measurement itself is clean; the workload's broker is the remaining failure

Run65 (r44, image rebuilt) is the first attempt where **the measurement latched nothing**: the
receipt says `abort_reason` `None` with 330 samples, a 317-sample baseline, and
`t_cold_start_gaps = 2` -- the cold-start window excused exactly the two early gaps that had been
latching runs 59-64, and the timeline runs cleanly to the end:

    BASELINE_END 60.19 -> SAMPLING_START 60.21 -> WORKLOAD_SPAWN 60.21 -> WORKLOAD_EXIT 72.51
    -> CLEANUP_START 72.51 -> QUIET_END 77.51 -> SAMPLING_STOP 77.52 -> CLEANUP_END 77.52

So the amended policy, the baseline, the peak alias, the sampler and the cleanup are all working
together, and the single remaining failure is the workload's own: the launcher reports
`SupervisorError: EARLY_EXIT: broker: 1`, i.e. the broker exited with code 1 for a reason that is
*not* the config schema (fixed) and *not* the file permissions (fixed). Its own error line is above
the supervisor message in `run65-session/raw/workload-stderr.log` and is the next thing to read.

Two honest notes to carry forward:

- the window semantics changed while chasing this: a *time-bounded* window that excuses every gap
  inside it (counted in `t_cold_start_gaps`) replaced the one-shot version, because run64 spent its
  single allowance on a 106 ms excursion at 1.6 s and then latched the 172 ms one at 3.4 s that the
  window existed for;
- the control test `test_cold_start_grace_covers_the_workloads_own_startup_once` still fails after
  being rewritten for the new semantics; it needs one look at what `t_cold_start_gaps` reports in
  that fixture before the gate is called green again.

## CP-UQ98 — The broker is v1 by construction, and a botched edit reverted

Two things established this round, one of them about my own work.

**The broker type-checks for the v1 class**: `broker.py` raises `BrokerError('RUNTIME_CONFIG_REQUIRED')`
when `type(config) is not ParallelRuntimeConfig`, so the loader selection from CP-UQ90 cannot be
enough on its own -- the v2 document loads fine and is then refused by type. What the broker actually
consumes from its config is small and schema-independent (yolo/grounded model ids, the four queue and
inference timeouts, `broker_queue_capacity_per_model`), and every one of those exists in the v2
`execution` mapping, so accepting both classes is a legitimate, small fix -- but the attempt is not in
the tree yet (below).

**My test edit was wrong and I reverted it.** I appended a test asserting the broker accepts a v2
config, then renamed the class in it twice (first to a class that does not exist, then to a name whose
import I failed to add), and the file ended up with 45 failures where 25 passed. Rather than iterate
on a file I had already damaged, I restored both it and `broker.py` from the last verified commit
(`git checkout --`), which is where the tree stands now: clean, with the gate at 73 passed from
CP-UQ97's addendum and the broker untouched. The next attempt at this fix should modify the test file
by hand (read it, edit the import block, add the case) rather than by string substitution, which is
the same lesson the retry-scripting rounds already taught.

## CP-UQ99 — The whole chain runs, and the policy stops it for CPU throttling

Run66 (r45, candidate rebuilt, image rebuilt to `sha256:c8b5c5aeced22633...`): gate **135 passed**,
commit `5851df1fb` fixing the broker's v1-only type check now that it is known to consume only fields
both schemas carry.

For the first time the entire chain ran without a harness defect in the way:

    BASELINE_START 0.00 -> LIMITS_APPLIED 0.15 -> BASELINE_END 60.28 -> SAMPLING_START 60.29
    WORKLOAD_SPAWN 60.29 -> ABORT_LATCHED 71.00 -> CLEANUP_START 81.03 -> QUIET_END 86.45
    -> SAMPLING_STOP 86.45 -> CLEANUP_END 86.46

That is a 60.28 s baseline (317 persisted samples), a broker that accepted the v2 document and got
past its provenance check, a worker that ran for **10.7 s**, and a verified cleanup -- with 200
samples taken and `abort_reason` **CPU_THROTTLED**.

That abort is policy, not a defect: `_breach` returns `CPU_THROTTLED` when
`throttling_disqualifies_run` and the sample reports throttling, i.e. the workload hit its own
cgroup's `cpu.max` quota. The quota derives from the safety envelope (0.8 x 24 cores minus background
and tool overhead, ~18.6 cores), so the honest reading is: at N1 the frozen workload's demand
(broker + worker + import) exceeds what the envelope allows it, and the measurement correctly refuses
to qualify a throttled run.

What that leaves is a calibration decision rather than a harness fix, and the options are the ones
the plan anticipates: bound the workload's CPU demand (thread/process limits are already 1 per
library, so the consuming side is elsewhere in the composition), or accept that N1 is not
calibratable under this envelope on this host and record that as the measured fact. Either way this
is the first run in the task whose outcome is a statement about the candidate rather than about the
instrument.

## CP-UQ100 — Thread bounds reach the container, and one throttled sample still disqualifies

Run67 (r46, thread bounds forwarded into the container, 26 container tests green) reproduces run66's
outcome: `abort=CPU_THROTTLED`, 200 samples, 317-sample baseline, the workload running from 60.32 s to
71.24 s and cleaning up. The difference worth noting is *how small* the trigger was: exactly **one**
sample out of 200 reports `throttled`, and the CPU rate over the run is small -- so this is not a
sustained overload but a single brief excursion past the cgroup's `cpu.max` quota (0.8 x 24 cores
minus background, ~18.6 cores). The frozen policy is zero-tolerance here
(`throttling_disqualifies_run: true` and any `nr_throttled` delta latches), and the amendment
deliberately preserved throttling as a policy dimension, so the abort itself is the rule working.

Two things need separating next, and they are cheap to separate:

1. whether the bounds actually arrived inside the container (the argv is built host-side and was
   rebuilt; the container is gone with `--rm`, so the evidence to check is the launcher's own record
   of the argv it ran, not a live container), and
2. what the workload's peak demand really is against the quota -- one excursion in 200 samples at a
   ~10 s run suggests a startup burst rather than a resource-hungry steady state.

If (1) holds and (2) is a startup burst, the honest conclusion may be that this workload needs either
a larger envelope or a policy decision about single-event throttling during startup -- both operator
decisions, not harness fixes. What is already established is that the instrument is no longer the
obstacle: the entire chain runs, and every remaining refusal is a policy judgement about the
candidate.

## CP-UQ101 — Not a burst: the workload sits on its quota, and the math is not the broker's

The last five samples of run67 settle the question CP-UQ100 left open, and the answer is the opposite
of a teardown blip. The owned cgroup's own counter climbs about one CPU-second per 50 ms sample:

    t=10.71 cpu_us=6042408 rate=18.16
    t=10.76 cpu_us=6267406 rate=18.16
    t=10.82 cpu_us=7279240 rate= 9.58
    t=10.86 cpu_us=8270536 rate= 9.58
    t=10.92 cpu_us=9210366 rate=18.88 throttled=True

against `limits {'cpu_quota_us': 1910050, 'cpu_period_us': 100000}` = **19.1 cores**. So the workload
holds ~19 cores in the final second, lands exactly on the quota, and the zero-tolerance rule
disqualifies it. Real consumption, real quota, real policy.

That also means forwarding the thread bounds into the **broker** container did not bound the work that
matters: something else inside the measured cgroup is opening ~19 threads/processes -- the worker side
of the composition, which is launched separately from the broker -- so the same forwarding has to be
applied wherever that math actually runs. The next step is to find that launch path (the worker's
container or process) and pass the bounds there, exactly as was done for the broker and with the same
kind of test; the broker-side fix stays regardless, since it is correct on its own.

Nothing here is an instrument defect any more: the harness measures the workload's CPU correctly and
the policy draws the line. What is still missing is whether the candidate's demand can be brought
under 19.1 cores at N1 by bounding the right process, and that is what the next run will answer.

## CP-UQ102 — The worker is in-process, nothing sets thread counts, and MuJoCo is the suspect

Three facts narrow the 19-core question from CP-UQ101, all read from the tree rather than inferred:

- the **worker is not a container**: `mujoco_parallel_batch` builds it in-process
  (`_build_worker_from_spec`, `worker_servers`), writing only a `worker-spec.json` into
  `<batch>/workers/worker-01/`. So the math that holds ~19 cores runs in the *launcher* process
  tree on the host, not behind the container boundary -- which is why forwarding bounds into the
  broker container did not change the demand.
- **nothing in the launcher sets a thread count**: no `set_num_threads`, no thread keys in the
  launcher, and the v2 config's execution section has none either (`max_worker_count`,
  `broker_inflight_per_worker_per_model`, `allow_cpu_fallback` are the nearest neighbours).
- the five library variables we forward (`OMP`, `MKL`, `OPENBLAS`, `TORCH`, `NUMEXPR`) bound BLAS and
  torch but **not MuJoCo**, whose thread pool is controlled by `MUJOCO_NUM_THREADS`; the batch root
  also carries a `render/` directory per worker, and rendering is exactly the kind of thing that
  opens one thread per core.

So the next unit is narrow: forward `MUJOCO_NUM_THREADS` alongside the others (and check whether the
render path honours it), then measure the demand again. If it stays at ~19 cores, the next diagnostic
is per-process CPU inside the owned cgroup during a run, which names the consumer instead of
inferring it from a total. Either way the instrument remains correct: it reports the workload's CPU
against the policy's line, and the remaining work is making the candidate fit under 19.1 cores at N1.

## CP-UQ103 — Bounding MuJoCo lowers the peak; one throttling event survives

Run68 added `MUJOCO_NUM_THREADS=1` to the bounds already exported, and the numbers moved: with the
same 60 s baseline and the same chain, the peak sampled rate fell from run67's 18.88 cores to
**13.60**, median 0.02, over 197 samples -- and yet the run still latched `CPU_THROTTLED`, on a single
sample out of 197. So the throttle is not the *average* demand crossing 19.1 cores (the sampled peak is
now well under the quota); it is an instantaneous excursion inside one `cpu.max` period, which the
zero-tolerance rule (`throttling_disqualifies_run` plus any `nr_throttled` delta) disqualifies
regardless of size.

Two honest notes about the attempt itself:

- my per-process watcher reported `total tracked cpu-s: 0.00` and told us nothing, because I globbed
  `$C/payload/so101-measurement-*` while the session creates its cgroup under the parent I passed
  (`$C`), not under `payload/`. That is a diagnostic error of mine, not a finding, and the watcher
  should glob the parent itself next time.
- the amendment to the measurement policy is not implicated: the instrument sampled, attributed and
  reported correctly, and the abort is the frozen rule doing what it says.

What remains is therefore a decision rather than a defect, and it is worth stating plainly for the
operator: at N1 the candidate's *peak* CPU demand still touches the 19.1-core quota inside a single
period even with every thread bound we can set (OMP, MKL, OPENBLAS, TORCH, NUMEXPR, MUJOCO). The
options are to find and bound that last consumer, to widen the envelope (a policy change to
`capacity_fraction`/`safety`), or to accept single-period throttling as non-disqualifying during a
cold start (a policy change to `throttling_disqualifies_run`). The first is engineering; the other two
are the operator's.

## CP-UQ104 — The external watcher failed twice; take the measurement from inside instead

Run69 reproduced `CPU_THROTTLED`, and my corrected watcher again produced an empty table ("peak
cores (top 8)" with no rows). That is the second instrumentation failure of mine in a row on this
question -- first the wrong glob, now a watcher that finds no processes even though it globs the
parent the session is given -- and two failed diagnostics in a row is a signal to stop reaching into
the run from outside and use what the harness already has.

The harness has it: `sample_resources` is handed `owned_inventory=(self.owner,)`, i.e. the identity of
the process the session owns, and it already reads the cgroup's aggregate counters each pass. A
per-owned-process CPU reading recorded into the sample's `diagnostics` (raw evidence, not a policy
dimension) would name the consumer from inside the same loop that produces the throttle decision,
with no external process, no glob, and no timing race -- and it can be tested with the existing
fakes the way the other sampler fields are.

That is the next unit: add the per-process breakdown to the sampler's diagnostics with a RED test,
then run once with it and read which owned process holds the cores. The policy question from CP-UQ103
-- whether a single-period excursion should disqualify -- remains the operator's, and is not touched
by this diagnostic.

## CP-UQ105 — Attribution works, and it names the wrong set of processes

Run71 (r48 sealed *inside* the run's own scope, which matters: r47 had been sealed in a different
unit and the runtime identity includes the cgroup path, so it was correctly refused with
`RUNTIME_FINGERPRINT_MISMATCH`) reproduced `CPU_THROTTLED`: 204 samples, one throttled, the whole
chain intact. The new `per_process_cpu` diagnostics worked exactly as designed -- and produced
`pids=1`: the only "owned" process is the measurement CLI itself (4.4 s of its own CPU), because
`owned_inventory=(self.owner,)` is the session's identity, not the workload's.

So the mechanism is right and the set is wrong. The sampler already has the cgroup object, and
`OwnedCgroupV2.pids()` enumerates the processes actually inside the measurement cgroup -- which is
where the ~19-core demand lives. Recording CPU per *cgroup* pid (a handful of entries, same cheap
`/proc` reads) is the next change, with the same kind of test, and it will name the consumer on the
next run.

Nothing else moved: the run's refusal is the frozen throttling rule, the instrument behaved, and the
policy question from CP-UQ103 (single-period excursion versus `throttling_disqualifies_run`) remains
the operator's.

## CP-UQ106 — The cgroup attribution works, and it shows a ROS 2 stack, not BLAS

Run72 (r49, candidate rebuilt, seal performed inside the run's own scope) produced the attribution
that the last three rounds were trying to get, and it is not what any of the thread-bound theories
predicted. The measurement cgroup holds **15 processes**, and they are the workload's ROS 2 stack:

    ros2, spawner (x2), scene_setup, graceful_shutdown, ros2_control_node,
    static_transform_publisher (x2), robot_state_publisher, docker, ...

The quota recorded in the same receipt is `18.90` cores. The per-process deltas visible in the journal
tail are small (0.0-0.1 s each over the window I printed), but my `journalctl -n 14` cut the top of the
table, so the dominant consumer is not yet named -- only the shape is: it is the launch stack the
workload brings up, not the BLAS/torch threads that the OMP/MKL/MUJOCO bounds address.

Two things follow, and they are cheap:

1. print the whole attribution table (or the top rows), which names the consumer outright;
2. re-read the bounds question in that light: `OMP_NUM_THREADS` and friends bound libraries, while
   `ros2 launch` brings up nodes that each do their own thing -- and a MuJoCo/Gazebo bridge or a
   renderer among them is a much better candidate for ~19 cores than any BLAS pool.

The instrument is now doing exactly what this stage needs: it attributes demand to processes instead
of inferring it, and the next run's table answers the question CP-UQ103 left to the operator.

## CP-UQ107 — The members are idle because the CPU is in the container's child cgroup

Ranking run72's attribution answers the question, and the answer is a contradiction that resolves
cleanly. Over 197 samples the cgroup's own `cpu.stat` grows by about one CPU-second per 50 ms pass
(~19 cores), while the direct members of that cgroup show almost nothing:

    whole-run CPU per cgroup process: 0.86 cpu-s for so101_parallel_ (the launcher), ~0.00 for the
    other fourteen (spawner, scene_setup, ros2_control_node, robot_state_publisher, ...)
    across the throttled interval: 0.31 cpu-s for motion_stack_re, 0.06 and below for the rest

Both readings are correct, because `cgroup.procs` lists only a cgroup's **direct** members while
`cpu.stat` is hierarchical: the container the launcher starts gets its own **child** cgroup (that is
how the container runtime puts it there), so the perception work inside it -- torch, ultralytics,
grounded SAM, the broker's loops -- burns the ~19 cores in a *descendant*, and the sampler never saw
those processes because it enumerated only the parent's own list.

That also finishes the earlier threads: the OMP/MKL/OPENBLAS/TORCH/MUJOCO bounds apply inside the
container and did lower the peak (18.9 -> 13.6 cores), but the demand is the container's inference
work, not a library pool the launcher can bound from outside. The next change to the sampler is
therefore to walk descendant cgroups when attributing (`cgroup.controllers`/children enumeration, or
reading the child cgroups' own `cpu.stat`), so the attribution covers the subtree whose usage the
parent's `cpu.stat` is already summing.

The policy question stays where CP-UQ103 left it: with the workload's real demand now located (the
container's perception work at ~19 cores against a 19.1-core quota), the operator's choices are to
bound that work, to widen the envelope, or to accept single-period throttling.

## CP-UQ108 — No children at all: the counter growth is not explained by the members

The subtree walk shipped (47 tests green, commit `2330ecfed`) and answered by finding nothing: every
process run73 attributed sits in `cgroup=.` -- the measurement cgroup's own list -- and **no child
cgroup appears at all**. So CP-UQ107's explanation (the container's work in a descendant) is wrong, and
the contradiction it was meant to resolve is still standing, now sharper:

- the cgroup's `cpu_usage_us` grows by about a CPU-second per 50 ms sample (~19 cores), and
- every process inside that cgroup is idle over the same window (0.90 cpu-s total for the launcher,
  ~0.00 for the fourteen ROS 2 nodes), with no children to hold the difference.

Two candidate explanations remain, and they are both checkable in one step:

1. the sampler's `cpu_usage_us()` is read from a **different cgroup than the one whose processes it
   lists** (the port may resolve through an ancestor), which would make the "observed" CPU belong to
   the scope rather than to the owned measurement cgroup; or
2. the container's processes live **outside** the measurement cgroup entirely (docker's own placement
   under its slice), in which case the quota never bounded the perception work and the throttling the
   policy sees is the ancestor's -- a materially different finding from everything assumed so far.

The way to tell them apart is to record, in the same sample, the *path* the CPU counter was read from
and the *paths* the process list came from, so the two line up or visibly do not. That is a small
diagnostic addition to the existing diagnostics block, not a behaviour change; the next round adds it
and reads the answer.

## CP-UQ109 — The averages are ~1 core; the refusals are rate spikes at the quota boundary

Run74 (r51) recorded the counter provenance and, with it, the numbers that reframe everything:

    cgroup_path    = .../so101-n1cal-75.service/so101-measurement-9d418aae-...-run74
    session_cgroup = .../so101-n1cal-75.service/payload
    owned counter delta = 8.98 cpu-s   scope counter delta = 13.57 cpu-s   wall span = 11.03 s
    abort = CPU_ENVELOPE (204 samples)

So over the whole workload window the owned cgroup consumed **0.81 cores on average** (8.98 cpu-s in
11 s) and the scope **1.23** -- nothing like the 19 cores that the instantaneous rate readings implied.
Every refusal in this series has been a *rate spike* on one or two samples, and the spike is exactly
what a cgroup consuming its own quota inside one `cpu.max` period looks like: 18.9 cores x 0.1 s of
quota in a 0.1 s window is 18.9 cores by construction, against an envelope line of 0.8 x 24 = 19.2.

That is a measurement-semantics question, not a workload-behaviour one, and it is the most useful
finding of this stretch: the rate window (`max(sample_interval, cgroup_cpu_period)`) is the same size
as the period in which the kernel may legitimately hand out the whole quota, so a workload that uses
its allowance in bursts reads as "at the envelope" even though its average is one core. The honest
next step is to compare like with like -- either measure the rate over a window several periods long,
or compare per-period *quota consumption* against the envelope rather than an instantaneous rate --
and to fix that in the harness with the evidence above, not by moving the envelope
(`capacity_fraction`) or the throttling rule, both of which stay the operator's to change.

## CP-UQ110 — The rate artifact is gone; only the policy's throttling rule remains

Run75 (r52, CPU measured over five quota periods instead of one, commit `09cc2d8f8`):

    rate median=0.02  p95=4.44  max=9.17      (was: median 0.02, p95 1.99, max 20.66)
    owned cpu-s=8.91 over span=10.52 s        (0.85 cores average)
    abort=CPU_THROTTLED, 194 samples, 1 throttled

The envelope artefact is fixed: the maximum reported rate fell from 20.66 to **9.17** cores against a
19.2-core envelope line, so `CPU_ENVELOPE` can no longer fire on a period-scale burst, while the test
that ships with the change proves a genuinely sustained 18.6-core load still registers. The
measurement now reports CPU honestly at every level: the rate over periods, the per-process and
per-subtree attribution, and the counter provenance.

What is left is exactly one rule and it is not a measurement artefact: the kernel throttled the
measurement cgroup on **one** sample out of 194 (the workload using its quota inside a `cpu.max`
period), and `throttling_disqualifies_run` makes any throttling disqualifying. The instrument is
correct; the policy draws a line that this workload crosses at least once per run.

That leaves three options, all now backed by measured numbers rather than theories, and all of them
the operator's to choose:

1. bound the offending consumer below the quota -- the attribution is in place (per-process and
   per-subtree CPU, plus counter provenance) and one run with it printed ranks the consumers;
2. widen the envelope (`safety.capacity_fraction`), which is a policy change;
3. treat single-period throttling as non-disqualifying (`throttling_disqualifies_run`), also policy.

I have not touched 2 or 3, and I will not without the operator's word.

## CP-UQ111 — There is no consumer to bound: the demand is transient, and the average is under a core

The ranking from run75 closes option 1 of CP-UQ110, and it closes it with a number rather than a
theory:

    total cgroup cpu-s over the run = 8.91
    sum of the 15 members' deltas   = 0.86
    top members: 0.860 cpu-s for so101_parallel_ (the launcher), 0.000 for each of the ROS 2 nodes

Eight of the nine CPU-seconds in that cgroup belong to processes that were **not** in `cgroup.procs`
when any sample was taken -- short-lived children of the launch stack that run and exit between
samples, while their usage stays in the cgroup's hierarchical counter. So the workload's demand is
real, transient and small on average (0.85 cores over 10.5 s), and there is no single consumer to
bound: option 1 has nothing to grip.

That leaves the picture complete and the decision squarely where it belongs:

- the instrument reports CPU correctly at every level (period-scale rate, per-process and per-subtree
  attribution, counter provenance) and no longer produces the period-scale artefact (peak 9.17 cores
  against a 19.2-core envelope line, average 0.85);
- the only remaining refusal is a **single throttling event** in ~190 samples, which the kernel
  produced because the cgroup momentarily wanted more than its 18.9-core quota inside one `cpu.max`
  period, and which `throttling_disqualifies_run` makes disqualifying by policy;
- changing that rule, or widening `safety.capacity_fraction`, are the operator's calls and I have
  touched neither.

For the record this stretch also produced eleven ledger entries whose hypotheses were refuted by
their own measurements (thread pools, container child cgroups, a named heavy consumer). Each is
written down with the refutation, and the pattern is consistent: this workload is light on average and
bursty at the quota boundary, and the harness now says so with evidence.

## CP-UQ112 — The operator's rule is in, and it shows the burst is sustained, not single

Implemented as directed in round 69 (commit `09bf9ca38`, gate 51 passed): a single throttled sample no
longer disqualifies a run -- throttling stays reported in every sample -- while **sustained**
throttling still does (`_SUSTAINED_THROTTLE_SAMPLES = 5` consecutive throttled samples ≈ 0.25 s). The
envelope and the 20 % headroom are untouched, and the tests cover both directions: one event excused,
five in a row disqualifying, a clean sample resetting the streak.

Run76 (r53) then answered the follow-up with its own counter: `abort=CPU_THROTTLED`, 202 samples,
**5 throttled**, baseline 318. Five throttled samples is exactly the new threshold, and the streak rule
only counts *consecutive* ones -- so this run is not a boundary blip at all: the cgroup wanted its
full ~19-core quota for about a quarter of a second continuously. That is consistent with the totals
measured earlier (8.9 cpu-s in the run, of which ~4.8 would be that burst) and explains why every
single-consumer theory failed: the demand is a short, hard *burst* by the launch stack's short-lived
children, not a resident consumer.

So option 1 is still open, but now with a precise target: make the launch stack's start-up burst
smaller or serialised rather than trying to bound a process that does not exist between samples. That
is engineering, and it is the next step; the policy change the operator chose is already in place and
doing exactly what it says.

## CP-UQ113 — Operator decision: N1 is uncalibratable, Stage C stops here

Presented with run76's own numbers, the operator chose option C: keep the envelope and the
sustained-throttling rule as they are, record N1 as uncalibratable, and stop Stage C. Recorded as
`stage-c/stageC-halt-20260918.json` in the evidence root (sha256 of `samples.jsonl`
`fc54763dc7bb8302c33a326e335bbffdde1adf62ea392c278b27bfd7a76595e9`, of `cleanup-receipt.json`
`4c5aad6c3e3f7c93cfca031bcb743dca7658d4ac53e23c9c584fb2b34db149e4`, of `resource_manifest.json`
`7c2bf7b39845c20ef789c20dc43787bfd7b9f5de05499c23211d96515febb15b`, of r53
`ee93afbc7d27089a8b3f9d8809f73992909b2b1f06aaa56c5b42f09e583ffd3c`).

What is being recorded as the fact, precisely: with `capacity_fraction 0.8`,
`minimum_free_fraction 0.20` and a 5-consecutive-sample throttling streak left untouched, the N1
attempt measured 202 samples over 10.69 s at a mean of 1.13 cores against a 19.1-core quota, and was
disqualified by a 0.19 s excursion at the tail of launch-stack start-up (samples 198-202 at 5.47 /
16.95 / 21.14 / 4.10 / 3.30 cores; breach latched at 1569934.182767854, abort sent at
1569934.182819165 -- one millisecond later, so the excursion preceded the interrupt rather than being
caused by it). Note for accuracy: CP-UQ112 called the burst "short-lived launch children"; the event
timeline now says the burst is the tail of start-up itself -- `move_group` printed "You can start
planning now!" at the end of the window, and the abort's teardown escalations all happen after it.

The batch reached none of its nine points (`execution_complete false`, every point `UNRUN`): the run
never got past start-up, which is exactly why the operator's ruling is "uncalibratable" rather than a
measured level. No further N1 attempt is made; r53/run76 is the final one.

Consequences, stated plainly:

- **Stage C halted.** N2..N8 calibrations and qualifications are not attempted, so no sealed B/Q pair
  for any N exists and no candidate P exists.
- **Stage D unreachable.** Per-N packets cannot be submitted against operator approval objects that do
  not exist, and nothing is promoted or deployed.
- **Stage E unreachable.** Owned live Chrome acceptance for N1/Nx is not attempted.
- **Budgets.** Every exact-N budget stays `NOT_MEASURED`, with no cross-N extrapolation. The 1.13-core
  figure above is one disqualified run's mean, not a budget.
- **Policy.** `capacity_fraction`, `minimum_free_fraction` and the throttling rule are unchanged by
  this decision; the swap/PSI removal and the single-period-throttling rule from round 69 stand as
  directed.
- **Retention.** Nothing was deleted, rewritten or re-run: r1..r53 and run1..run76 remain in place,
  and the frozen plan file is untouched.

This is where the dispatch's objective stops being achievable as written. Stages A and B are complete
and the metering machinery works -- it measured a full stack start-up, a 60.2 s baseline of 318
persisted 50 ms samples and a 25 ms peak-alias cross-check -- and its refusal here is the rule working
as specified, not an instrumentation failure. What it cannot do under an unchanged envelope is certify
an N=1 deployment whose start-up momentarily wants the whole machine.


## CP-UQ114 — New approved dispatch: the budget chain is deleted, a lightweight start guard replaces it

**Task 1 of the approved 12-task plan (retire, classify, and record).** Dispatch
`b82d10b8-32bf-47b4-9aa9-9bbec17d3a6b`, user instruction "把上面的计划发布给dst。给它设定goal模式 budget
100轮。" The handoff supersedes the earlier DESIGN_ONLY/PLAN_ONLY conditions and the Stage C halt: the
retired per-N budget goal is replaced by the lightweight start guard, and the old **C/D budget stages
are recorded as `NOT_APPLICABLE_SUPERSEDED`** (not PASS, not DONE).

Approved artifacts, all four read in full and hash-verified against the handoff before any edit:

| Artifact | SHA-256 | Verdict |
| --- | --- | --- |
| design `.../specs/2026-09-19-...-lightweight-start-guard-design.md` | `73cc295ce6fba187c85e38081c458112b448357e844c7afa9e3a06ed3f2bfdb5` | Astra/High PASS |
| plan `.../plans/2026-09-19-...-lightweight-start-guard-implementation.md` | `d75597a73f7d211eb31c4e75e3e6cb2f696d86dc953405f393962747c814b141` | Astra/High PASS |
| design review `.../reviews/2026-09-19-...-design-review.md` | `dda84f76c3855864545c958fd1b475b437a6fd4ecd4841caf2630f38d5eaab91` | PASS |
| plan review `.../reviews/2026-09-19-...-plan-review.md` | `810c876587fa74af4c5d1e03cd34eabd6161217bad1b4a865d8b935fc42fa26a` | PASS |

The four documents live in the package directory
`followups/lightweight-start-guard-b82d10b8-32bf-47b4-9aa9-9bbec17d3a6b/docs/superpowers/...`; that
is where the hashes match. The same relative paths under the worktree still hold only the 2026-09-18
documents.

**Receipt, probe, goal.** First action was an `O_EXCL` create of `executor.receipt` holding exactly
`b82d10b8-32bf-47b4-9aa9-9bbec17d3a6b` + LF (37 bytes, sha256
`faa3c4afd5c64224c8ce6605ed9e708527f319d17dfb70b71e2f9006c62fa29a`, never rewritten). The startup
probe (`startup-probe.log`, `startup-probe-result.json`) collected real facts, not hardcoded ones:
host `AI-STATION-001`, branch `codex/so101-unbounded-queue-resource-budget`, HEAD
`a87f77dbe374bf741d745a6f34120ec38e2fb31d` with a clean tree, pane `%68`/launcher PID 1345571,
ledger 340288 bytes, and all four document hashes with `documents_all_match: true`. Two commands
exited non-zero and are recorded as such: `git rev-parse @{u}` (128, the branch has no upstream) and a
bare `import so101_demo` (1, expected without the task environment).

The orchestrator's `/goal clear` was verified rather than assumed: `get_goal` returned
`{"goal": null}`. The fresh goal was then created with the handoff's exact objective and budget:
`goal-e568087d-20f9-4203-8ca6-2a14d59fff8e`, revision 1, `maxGoalRounds 100`, `roundsStarted 0`,
active/armed, saved in `goal-created.json`. The previous goal
`goal-d30193b8-a2e5-495d-b6c7-6879782448ac` (blocked, 69/140) was cleared, not resumed and not marked
complete.

**Source drift checked before trusting the plan.** The reviewed plan names remote HEAD `207828d5` as
its source reference. That commit is an ancestor of the current HEAD and **12 commits behind it**, so
every path the plan names is re-verified against `a87f77db` before editing rather than assumed.

**Retirement map** (new unique migration dir
`migration-light.lS2WzrsrZ/`, `retirement-map.json` + `retirement-map.md` +
`analysis/symbol-references.json`). The honest headline is that the budget chain is a closed island:
the four budget modules have exactly four non-test importers, all of them either the retired
measurement CLI or a product call site this migration re-wires.

| Module | Lines | Verdict | Non-test importers |
| --- | --- | --- | --- |
| `parallel_batch/resource_budget.py` | 2232 | delete | measure CLI, `cli/mujoco_parallel_batch.py`, `adaptive_pool.py`, `owned_resources.py`, `resource_measurement.py`, `resources.py`, teleop `production.py` |
| `parallel_batch/resource_measurement.py` | 1410 | delete | measure CLI, `cli/mujoco_parallel_batch.py`, `owned_resources.py`, `resources.py` |
| `parallel_batch/measurement_control.py` | 347 | delete | measure CLI, `owned_resources.py`, `resource_measurement.py` |
| `parallel_batch/owned_resources.py` | 889 | delete | measure CLI only |

151 externally named symbols were classified, each with its callers, and the classification is
deliberately conservative in one place: nine names (`_SHA256`, `_IDENTIFIER`, `_require_sha256`,
`_CGROUP_ROOT`, `_EVENT_NAMES`, `_write_private`, …) are *name collisions* with unrelated modules, so
they are recorded as collisions rather than counted as real dependencies. The four product call sites
to re-wire are `cli/mujoco_parallel_batch.py` (L454/497/1101), `resources.py` (L1357/2608/2628),
`adaptive_pool.py` (L451) and teleop `production.py` (L279/456/1222), of which
`worker_count_availability` is the one symbol that must be *replaced by real functional capability*
rather than simply dropped.

Retired with the modules: the `so101_measure_parallel_resources` console script, the eleven
`_AUTHORITY_ENV` names, the config `measurement`/`safety`/`deployment` sections, and the seven
demo plus two teleop budget-only test files. Kept and explicitly out of scope: `runtime/
parallel_processes.py` ownership, lease/fence/session/reset, cancel/cleanup/deadline, physical
qualification and statistics, the ACT extension, and the ROS domain/port contracts.

**Inventory (Task 1's other half).** No owned measurement is in flight: no owned container is running,
no `so101*` unit is active (the `so101-n1cal-*` units are inactive/failed remnants of the retired
Stage C and their evidence stays untouched), and no owned ROS process exists. One genuine leftover was
found and retired: PID 1899712, an orphaned `descendant_helper.py` fixture from an L2
orphan/cleanup-window test (PPID 1, parent long gone, idle sleep loop, started 20:22:56 the previous
evening). It was terminated with `SIGTERM` and confirmed gone within the bounded wait, with
PID/starttime/cgroup/cmdline recorded before and after in `inventory.json`. The owned Stage B Web
service (PID 1993965, serving `freeze-install` on 127.0.0.1:8010) stays up; Task 10 replaces it in an
ordered stop/start.

**What this checkpoint does not claim.** No runtime code has been deleted yet, no guard exists, no
test has been written. Task 1 is classification and preservation only. All old evidence — r1..r53,
run1..run76, the Stage C halt record, sealed files, failed runs — remains exactly where it was.

Next: **Task 2**, the shared `start_guard.py` decision model with genuine RED before implementation.


## CP-UQ115 — Tasks 2 and 3: the guard decides, and the active contract is v3

Both tasks ran RED before GREEN, with the RED failure being the intended behaviour rather
than a collection error.

**Task 2 — `parallel_batch/start_guard.py` + `test/test_parallel_start_guard.py`.** RED
(`lg-t2-red`): 43 collected, **41 failed, 0 errors**, including the intended
`test_equal_floor_passes` (the stub returned FAIL where the design says an equal floor
passes). GREEN (`lg-t2-green2`): **44 passed**, exit 0, `-n 8`, JUnit and scratch recorded.
The module implements the closed `StartGuardPolicy`/`GuardScope`/`ResourceSnapshot`/
`GuardCheck`/`GuardResult` models, a pure `evaluate_snapshot`, and `probe_snapshot` behind
injectable low-level ports. Two real defects were found and fixed by the tests rather than
argued away: NVML needs `nvmlInit_v2()` before any call (without it `nvmlDeviceGetCount_v2`
failed on this host), and an empty device list must report `GPU_TARGET_UNAVAILABLE`
(missing device) rather than `GPU_TARGET_NOT_VISIBLE` (wrong device). A forbidden-read
fixture raises `AssertionError` on any paging/stall file read or Git invocation and the
suite still passes; a real-host test proves the real cgroup/meminfo/NVML path works
(0.119 s, 24 cores, 26.09 GiB available, GPU `GPU-0b7689c1-…`, status PASS).

**Task 3 — closed v3 contract, pure history reader.** RED (`lg-t3-red`, with the v3 block
temporarily removed): 66 collected, **11 failed, 0 errors**, i.e. the v3 contract genuinely
did not exist. That RED also caught a real bug in my own history reader:
`test_history_projection_is_read_only` failed with "DID NOT RAISE", because the returned
mapping was a plain dict. GREEN (`lg-t3-green4`): **98 passed**, exit 0, across
`test_parallel_batch_contracts.py`, `test_parallel_history.py` and
`test_parallel_adaptive_contracts.py`.

What v3 is: top level exactly `{schema_version, execution, start_guard}`; `execution` is
exactly the 38 reviewed fields with `sampling`/`safety`/`coverage` gone and the GPU selector
moved to `execution.gpu_device` (`selector_kind` + `selector`, no implicit host 0);
`start_guard` is exactly the five policy fields; the whole `deployment` section is deleted.
`BatchRequestV3`, `batch_request_to_document` and `batch_request_from_document` are in
place, and `require_v3_execution` refuses every version but 3 with
`CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION`; `batch_request_from_document(..., for_execution=
False)` returns a plain read-only mapping for v1/v2 rather than converting it into an active
request. `history.py` imports nothing from the retired chain: a subprocess test asserts that
loading a retained document leaves `resource_budget`, `resource_measurement`,
`measurement_control`, `owned_resources`, `start_guard_probe` and `start_guard` out of
`sys.modules`, that the sealed bytes and directory listing are unchanged, and that the
returned view refuses mutation. `parallel_batch_v3.yaml` mirrors the v2 functional values
and is picked up by the existing config glob at install time.

Commits: `795e29679` (Task 2), this checkpoint's commit (Task 3). Next: **Task 4**, the
bounded 2 s probe helper with cross-process single-flight and the durable
cleanup-blocked contract.

_Ledger HEAD when written: `70df7c6c8`._


## CP-UQ116 — Task 4: the probe helper is bounded, single-flight and durable

RED first, and it was worth it: `test_parallel_start_guard_probe.py` was written against the
real helper process (only the lowest-level process port is replaced), and the first GREEN
attempt failed 5 of 12 tests for two genuine implementation defects, both now fixed:

- the request pipe was wired backwards -- the child was handed the write end and the owner
  wrote into the read end, so every real helper died with `EBADF`;
- a **zombie** keeps its `/proc/<pid>/stat` entry until it is reaped, so
  `recover_owned_cleanup` saw an already-exited test child as "still alive" and refused to
  clear the state. `read_process_identity` now reports a `Z` state as gone, which is what
  makes the recovery branch honest instead of permanently stuck.

GREEN (`lg-t4-green3`): **12 passed**, exit 0, `-n 8`, scratch and JUnit recorded, and no
helper process is left behind. What the tests actually prove:

- `test_all_reads_are_helper_owned` monkeypatches `start_guard.probe_snapshot` **in the
  owner** to raise `AssertionError`; the real helper runs in a fresh interpreter and the
  request still returns PASS/WARN with a real snapshot, so the owner cannot be doing the
  reads.
- `test_native_timeout_is_bounded` drives the unreapable branch with a process port that
  never reaps, and asserts the check returns FAIL `PROBE_CLEANUP_BLOCKED` inside
  `timeout + terminate grace + kill grace + margin`, with the exact PID/starttime persisted.
- `test_unreapable_blocks_retry_and_spawn` then asserts a second request is refused
  *without spawning anything* (the popen port is never called).
- `test_singleflight_wait_counts_against_deadline` holds the cross-process `flock` and
  asserts the waiter fails `PROBE_BUSY` inside its own deadline rather than queueing.
- `test_restart_recovers_exact_pid_starttime` covers all three recovery branches: a gone
  helper clears the state with the disappearance recorded, a live PID with a **mismatched**
  start time is never signalled (the test asserts its own process is untouched), and an exact
  owned match is terminated through the bounded exact-identity path.
- `test_persistent_state_corruption_fails_closed` writes junk into the durable state and
  asserts a FAIL with no spawn, and the helper entry point is exercised as a real
  `python -m so101_demo.parallel_batch.start_guard_probe` (help exits 0; missing FDs exit 2).

Commit `6216fe029`. State root is `$TASK_ROOT/start-guard-state`, the coordination key is
hostname+uid+task root so INDEX and UUID aliases share one lock, and the lock, IPC and state
I/O all run under the deadline (state reads go through a bounded off-thread call).

Progress: Tasks 1-4 of 12 are complete, each with its own commit
(`e4d4d22be`, `795e29679`, `70df7c6c8`, `6216fe029` plus ledger commits). Next: **Task 5**,
wiring `EpochStartGuard` into the real CLI/allocator/restore composition.

_Ledger HEAD when written: `6216fe029`._


## CP-UQ117 — Task 5 (part one): the epoch guard exists and is proven; the CLI wiring is next

**Done this round.** `EpochStartGuard` and `compose_default_start_guard` now live in
`parallel_batch/start_guard_probe.py` (commit `05b9990d2`, EOF style fix `c728b75d8`).
RED (`lg-t5-red`, with the block temporarily removed): 7 collected, **4 failed + 2 errors,
0 collection errors** — the epoch guard genuinely did not exist. GREEN (`lg-t5-green`):
**7 passed**, exit 0, `-n 8`. The tests pin the reviewed semantics rather than a happy path:

- one fresh probe covers every spawn in an epoch (`probe_count == 1` after five
  `require_before_spawn` calls), and a new epoch probes again;
- a changed scope (worker count) and an observation older than the policy deadline both
  force a fresh probe instead of reusing a stale observation;
- a FAIL result raises `StartGuardRefused` with the real reason and is **never** reused;
- `cleanup_state != CLEAR` is refused even when the status is only WARN;
- the installed composition honours `SO101_TASK_ROOT` and creates the shared state root;
- a subprocess test imports the composition and the v3 contract and asserts that
  `resource_budget`, `resource_measurement`, `measurement_control` and `owned_resources` stay
  out of `sys.modules`;
- a fixed request with one point and four workers keeps **four** slots.

**Precise remaining Task 5 edits** (measured against the current tree, so the next round does
not have to rediscover them):

- `cli/mujoco_parallel_batch.py`: 29 sites mention the retired plumbing. Replace
  `_compose_default_resource_gate` (L1093) and the `_DEFAULT_RESOURCE_GATE` hook (L1090) with
  a v3 composition; make `_load_runtime_config` (L1109) load v3 and refuse v1/v2 with
  `CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION`; replace `_prepare_live_headroom` (L482) with a
  guard check that builds the scope from the real owner identity; delete
  `_compose_measurement_gate` (L451) and make `--measurement-authorization` a retired-flag
  error; drop `resource_gate` from `PreparedBatch` (L183), `prepare_batch` (L1132), the
  measurement branch (L1201/1224), the allocator call (L1375) and the spec reader (L2692).
- `parallel_batch/resources.py`: 14 sites. `_live_headroom_decision`/`_live_headroom`
  (L1354-1390) keep the guard result and delete the `>3` refusal, the `!=3 → None` branch and
  the profile-drift comparison in restore (L1185-1196); `_compose_default_resource_gate`
  (L2605) and the measurement composition (L2628) go away.
- `parallel_batch/adaptive_pool.py`: L451 `_issue_adaptive_context` is the only budget
  import; remove it and keep the adaptive affinity/fallback policy intact.
- Tests: the autouse `synthetic_resource_gate` fixture in `test_parallel_batch_cli.py` (L56)
  and `test_parallel_batch_resources.py` (L146) must be replaced by the real guard with only
  the lowest process port replaced — injecting a fake admission gate as positive proof is
  explicitly forbidden by the plan.
- Commit for the wiring step is the plan's own message: `feat: wire real epoch startup guard`.

No runtime budget code has been deleted yet; Task 6 does that, and this round deliberately
did not start the 400-line wiring edit with too little context left to finish and verify it.

_Ledger HEAD when written: `c728b75d8`._


## CP-UQ118 — Task 5b in progress: the real entry points are off the budget gate

Committed as work-in-progress (`954cad708`) because the migration is large and the honest
state is more useful than an uncommitted tree. What is already true:

- The default CLI path loads **v3 only** (`CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION` for v1/v2),
  runs one bounded guard check before the epoch spawns (`_prepare_start_guard`), refuses
  outright when the guard reports FAIL or `PROBE_CLEANUP_BLOCKED`, and records the guard
  summary in the batch manifest (`schema_version: 3`, no `live_headroom` block).
- `_compose_measurement_gate`, `_compose_default_resource_gate`, the task14 verifier factory,
  the profile-drift comparison in restore, the v1 `>3` refusal and the `!=3 → None` fallback
  and the retired evidence options are all gone; presenting the old evidence or a
  measurement authorization is now an explicit error (`LIVE_HEADROOM_EVIDENCE_UNEXPECTED`,
  `MEASUREMENT_AUTHORIZATION_RETIRED`).
- `resources.py` gained `StartGuardAdmission`, admits v3 allocations and restores through one
  fresh check, and no longer compares a recorded profile. `adaptive_pool.py` lost its dead
  budget context issuer. `worker.py`, `coordinator.py` and `broker.py` accept v3 instead of
  refusing it with `FROZEN_CONFIG_REQUIRED`.
- The test seam changed shape on purpose: the autouse `synthetic_resource_gate` fixtures (a
  fake admission returning APPROVED-ish decisions) are replaced by a seam that runs the
  **real** `probe_snapshot` over the **real** host reads and the **real** `evaluate_snapshot`
  decision, substituting only the probe process boundary. Injecting a fake admission as
  positive proof is exactly what the reviewed plan forbids. The 880-line task14 three-worker
  evidence cluster is retired, with the removed text kept at
  `/tmp/so101-debug-startup-probe-b82d10b8/retired_task14_tests.py`.

Honest red state, measured with the task wrapper at `-n 8`: **219 collected, 29 failed, 0
errors** (from 260 setup errors at the start of the wiring). The remainder is retired-budget
expectation, not new behaviour:

- 8 `DID NOT RAISE` — tests asserting the v1 formula thresholds refuse (`INSUFFICIENT_LOGICAL_CPU`
  and friends) and the observation/threshold admission record; that formula is dead under v3.
- 7 regex mismatches — old codes (`BUDGET_PROFILE_UNAVAILABLE`,
  `FIXED_WORKER_LIVE_QUALIFICATION_REQUIRED`, `THREE_WORKER_LIVE_EVIDENCE_*`).
- 4 `START_GUARD_UNAVAILABLE` — allocator constructions the mechanical pass did not reach.
- 5 individual: a resume manifest mismatch, a directory-conflict fixture, the frozen-topology
  count, an oversized-cmdline probe assertion, and one lingering module-level monkeypatch.
- 1 `AttributeError: 'StartGuardAdmission' object has no attribute 'observed'` — a test still
  reading the retired admission record.

Plan for the next round, in order: fix the 4+5 individual/product cases (they are real
regressions to verify, not expectations to delete), then retire the 15 retired-budget
expectations together with the code they describe in Task 6, and only then run the wider gate.
The guard, contract, history and probe suites remain green (`lg-guard-combined`, 129 passed).

_Ledger HEAD when written: `954cad708`._


## CP-UQ119 — Task 5 complete: the real entry points run on the guard, and the suites are green

Commit `371e41a7a` (`feat: wire real epoch startup guard`). The 29 red tests from CP-UQ118
are resolved — **not** by deleting them all, and the split is worth recording:

- **Product rules were rewritten onto the guard, not dropped.** "Never silently downgrade"
  is now `test_three_workers_are_explicit_and_never_silently_downgraded` and
  `test_fixed_eight_refuses_without_reducing_the_count` (a refused start keeps the requested
  count and creates no evidence root); "fail closed without side effects" is
  `test_each_guard_failure_fails_closed_without_creating_directories` parametrised over
  `CPU_CAPACITY_UNAVAILABLE`/`RAM_BELOW_MINIMUM`/`GPU_FREE_BELOW_MINIMUM`/`GPU_TARGET_NOT_VISIBLE`;
  "no domain claims before admission" is `test_fixed_eight_refusal_makes_no_domain_claims`;
  the admission record test now asserts a real `StartGuardAdmission` (status, cleanup state,
  the four checks and their units) instead of the retired threshold record.
- **Retired budget expectations were retired with their code**, which Task 6 deletes:
  the v1 formula-threshold assertions (`INSUFFICIENT_LOGICAL_CPU` and friends), the
  three-worker "live qualification" refusal, and the `BUDGET_PROFILE_UNAVAILABLE` /
  `_DEFAULT_RESOURCE_GATE` hook expectations. `test_production_cli_needs_no_budget_authority_for_three_workers`
  replaces the last of them and asserts the opposite: with the retired hook set to `None`,
  a three-worker production CLI start still prepares normally on the guard.
- **Three real defects were found by the failures rather than argued away.**
  1. The batch manifest was *volatile*: it carried the guard's observation timestamp and
     observed values, so a resume compared a different manifest and refused with
     `RECOVERY_BATCH_MANIFEST_MISMATCH`. The manifest now records only deterministic facts
     (status, cleanup state, GPU UUID and each check's status/reason/cutoff/unit); the
     observations stay in the guard evidence.
  2. `test_oversized_cmdline_process_is_classified_not_refused` was racing `Popen`: it read
     `/proc/<pid>/cmdline` before the child exec'd and saw an empty file. It now waits,
     bounded, for the exec.
  3. `test_external_cleanup_retires_only_owned_worker_and_releases_claim` used a fixed
     runtime root (`<scratch>/a001`) that collided with other tests sharing one scratch tree
     under `-n 8`. It now keeps the batch-id leaf (which `cleanup_runtime` validates) under a
     per-test parent.

Gates, all with the task wrapper, JUnit and scratch recorded:

| Gate | Result |
| --- | --- |
| `lg-t5-wire16` cli + resources + adaptive integration | **220 passed, 0 failed, 0 errors**, 8.0 s |
| `lg-t5-wide` guard/probe/composition/contracts/history/broker/coordinator/worker | **446 passed, 0 failed, 0 errors** |

Also fixed on the source side: the allocator's `start_guard` document now carries the
per-check status/reason/cutoff/unit (so a restored manifest can be audited), and `worker.py`,
`coordinator.py` and `broker.py` accept `ParallelRuntimeConfigV3` instead of refusing it with
`FROZEN_CONFIG_REQUIRED`.

State: **Tasks 1-5 of 12 complete** (commits `e4d4d22be`, `795e29679`, `70df7c6c8`,
`6216fe029`, `05b9990d2`, `954cad708`, `371e41a7a`). The budget modules are still present but
nothing active reaches them; **Task 6 deletes them** (`resource_budget.py`,
`resource_measurement.py`, `measurement_control.py`, `owned_resources.py`, the measurement CLI
entry and the retired env contract), which is also where the user's "clear out the old
budget-measurement code" lands.

_Ledger HEAD when written: `371e41a7a`._


## CP-UQ120 — Task 6: the certified budget runtime is deleted, not bypassed

Commit `3cfe45c4f` (`refactor: retire certified budget runtime`): **9232 lines removed
across 21 files**. This is the step the user asked for when they said the old budget
measurement code also has to go, and it is a deletion rather than a disconnection:

- **Source modules deleted**: `parallel_batch/resource_budget.py` (2232),
  `resource_measurement.py` (1410), `measurement_control.py` (347), `owned_resources.py`
  (889) — 4878 lines. The last copy of each is archived read-only at
  `migration-light.lS2WzrsrZ/retired-sources/` with sha256 and line counts in
  `task6-retirement-record.json`.
- **Nine budget-only test files deleted** (9016 archived lines in total including the four
  modules): the sampler-control, measurement-runtime, default-measurement-path,
  resource-budget, resource-measurement, budget-promotion and exact-N-qualification suites,
  plus the teleop resource-budget and installed-budget suites. Their CTest registrations and
  the package-layout lists were updated in the same commit.
- **The console entry is explicitly retired, not removed**: `so101_measure_parallel_resources`
  now prints `MEASUREMENT_ENTRY_RETIRED` (with `authorizes_execution: false` and a pointer to
  `so101_parallel_batch`) and exits 2. An operator who still types the old command gets a real
  explanation instead of "command not found" or a silent different mode.
- **The teleop service no longer consults a budget authority**: `_HostResourceProbe` admits
  through the shared start guard, reports the guard's own FAIL reasons, and
  `_worker_count_availability` now lists the *configured* fixed counts (status `CONFIGURED`,
  reason `DOMAIN_OR_PORT_UNAVAILABLE` when a count is not configured) instead of a budget
  decision. The guard composition is lazy (`_LazyStartGuard`), so constructing the service
  performs no config I/O — which is also what kept
  `test_production_factory_wires_durable_authorities_and_releases_lock` honest rather than
  requiring a fixture rewrite.
- **The CLI keeps only the retirement error** for the old measurement flags and its
  `_stop_requested` predicate no longer has a measurement latch.

The decisive evidence is not a text search: `test_no_active_path_imports_the_retired_budget_chain`
and `test_retired_console_script_is_still_registered_but_imports_no_budget_module` install a
`sys.meta_path` trap that raises if any of the four modules is imported, then import the CLI,
the allocator, the adaptive pool, contracts and the guard composition and run a real
composition. RED before the deletion: 12 collected, **4 failed, 0 collection errors**;
GREEN after: 134 passed in the Task 6 gate.

Gates (task wrapper, `-n 8`, JUnit and scratch recorded):

| Gate | Result |
| --- | --- |
| `lg-t6-green2` guard/probe/composition/contracts/history/measurement-cli | 134 passed |
| `lg-t6-wide` cli/resources/adaptive/broker/coordinator/worker | 537 passed |
| `lg-t6-teleop6` whole teleop suite (parallel phase) | 523 passed, 0 failed |
| `lg-t6-final` all of the above plus teleop preflight/main/api/production | **733 passed, 0 failed, 0 errors** |

One honest note about the teleop directory run: `so101_pytest src/so101_teleop/test` reports a
non-zero exit from the *audited split runner's coverage check* (`coverage_exact: false`,
`extra: 5` demo node-ids) while the parallel phase itself is 523 passed / 0 failed. That runner
is built for the demo package's split; the teleop suite's real gate is the CTest path in
Task 9, and the per-file runs above are green.

State: **Tasks 1-6 of 12 complete**. Next: **Task 7**, the Web/API/preflight capability and
`start_guard` projection, then Task 8's installed-entry/negative-gate coverage.

_Ledger HEAD when written: `3cfe45c4f`._


## CP-UQ121 — Task 7 (server side): the guard is in the API, and the Web half is what is left

Commit `23cbbf486`. The API now carries the guard the design specifies, verified against the
**real** production service over ASGI (not a fake service object):

- `StartGuardStatus` / `StartGuardCheck` / `StartGuardPolicyResponse` DTOs mirror the guard
  result: per-check `status`/`reason`/`observed`/`cutoff`/`unit`, the overall status, the
  cleanup state, the GPU UUID and the observation time; `CapabilitiesResponse` also exposes
  the enforced policy so a client can display the cutoffs it was judged against.
- `PreflightResponse.start_guard` is the server's own decision; `resource_observations`
  carries the same document for audit. `capabilities` reports `start_guard_policy` from the
  composed guard.
- The new-execution gate now requires `contract_version: 3` and answers
  `CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION` for anything else (it previously demanded 2).
- `default_worker_count_availability()` no longer says "BUDGET_PROFILE_UNAVAILABLE": the
  static DTO default is `UNKNOWN`/`CAPABILITIES_NOT_LOADED`, and the real service reports
  `CONFIGURED` counts (Task 6's change), so a resource state never marks a count unqualified.

RED (`lg-t7-red6`): 7 collected, **7 failed** for the intended reasons — the response had no
`start_guard`, capabilities had no policy, and version 3 was refused with the old code.
GREEN (`lg-t7-green6`): **7 passed**. The tests prove, on the real service: the preview
carries units/cutoffs/time; a missing GPU is an explicit `GPU_TARGET_UNAVAILABLE` FAIL;
busy CPU is a WARN that still starts (`admitted: true`, empty reason codes); a client that
posts its own `start_guard`/`resource_observations`/`admitted` is rejected as extra input and
cannot override a failing server check; history/capability reads run **zero** probes; and
legacy contract versions are refused with the new code. Then the affected teleop suites
(`lg-t7-wide2`, including api/preflight/main/supervisor/package-layout): **67 passed**.

Two fixture notes worth keeping: the manifest identity is computed from real installed bytes,
and the dev prefix is a `--symlink-install`, so the test builds a *copied* share directory
(the production `_read_inputs` rightly refuses symlinked inputs); and the real store's sqlite
connection is thread-bound, so the tests drive the ASGI app with `httpx.ASGITransport` inside
the test thread instead of `TestClient`'s portal thread.

**What is left of Task 7 is the Web half**, and it is deliberate rather than hidden: the TS
client still sends `contract_version: 2`
(`src/expert-validation-app.tsx:240,251`, `expert-validation-client.test.ts`,
`expert-validation-app.test.tsx:390`, and the generated `expert-validation-schema.d.ts`),
the panel does not yet render the guard status/units/time, and
`expert_validation_openapi.json` plus the generated schema have to be regenerated before
`so101_bun lg-api-generate/lg-web-unit/lg-web-build` can be green. That is the first work of
the next round, followed by Task 8's installed-entry and negative-gate coverage.

_Ledger HEAD when written: `23cbbf486`._


## CP-UQ122 — Task 7 complete: the guard reaches the browser, and the client is on v3

Commit `04c22828e` (`feat: expose lightweight startup status`) closes the Web half that
CP-UQ121 left open.

- **The export is regenerated, not hand-edited**: `$TEST_PYTHON -m so101_teleop.openapi_export
  --validation src/so101_teleop/so101_teleop/expert_validation_openapi.json` (exit 0). The
  diff is exactly what the DTO change implies: `contract_version` `const` 2 -> 3 in both
  request schemas, plus `StartGuardStatus`/`StartGuardCheck`/`StartGuardPolicyResponse` and
  the new `start_guard`/`start_guard_policy` response properties (191 added lines). The
  generated TypeScript schema followed through
  `so101_bun lg-api-generate run generate:api:validation` (68 added lines), and
  `expert-validation-types.ts` now exports the three guard types.
- **The client speaks v3**: `contract_version: 2` is gone from
  `expert-validation-app.tsx` (both the fixed and adaptive preflight inputs), the client test
  and the app test. That matters because the server gate from CP-UQ121 refuses anything else
  with `CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION`.
- **The panel shows the server's decision instead of a bare pass/fail**:
  `start-guard-summary.ts` formats the status, every check with its unit and cutoff
  (`RAM free 30.0 GiB vs floor 1.0 GiB`, `CPU busy 95.0% vs 90.0%`), the observation time,
  the policy timeout and a blocked cleanup state; a FAIL keeps its own reasons; a missing
  result reads `Start guard: unknown (not checked yet)` rather than green. It is rendered as
  its own `aria-label="Start guard"` line in the setup panel, so the existing
  "Parallel admission passed" notice and its tests stay meaningful, and a WARN is displayed
  as a warning — never as a qualification.
- The first build attempt failed with four `TS2345` errors because `StartGuardCheck.observed`
  can be a string as well as a number; the formatters now accept
  `number | string | null | undefined` and only format finite numbers. Worth recording
  because it is exactly the kind of thing a "generated schema" change is supposed to surface.

Gates, all through the task wrapper with their run directories recorded:

| Gate | Result |
| --- | --- |
| `lg-web-unit4` `so101_bun run test` | **126 passed** (30 files) |
| `lg-web-build2` `so101_bun run build` (`tsc -b && vite build`) | exit 0, `dist/` written |
| `lg-t7-export` openapi_export test + the guard API tests | **12 passed** |

State: **Tasks 1-7 of 12 complete** (commit chain `e4d4d22be` ... `04c22828e`). Next: **Task 8**,
the launch/wrapper/default installed entry points and the product negative gates (real copied
`so101_parallel_batch` entry, `ros2 launch ... --show-args` for the installed TextAgent
launch, plus the missing/malformed debug-manifest and session/reset/evidence/content/control
negative cases).

_Ledger HEAD when written: `04c22828e`._


## CP-UQ123 — Task 8: the real installed entry runs the guard, and three defects fell out

Commit `aa5016deb` (`test: cover default entry and safety boundaries`). The new
`test_parallel_start_guard_launch.py` does what the plan asked and refuses the shortcut it
warns about: it discovers the installed console script through the functional lookup
(`installed_executable`, ament/share/PATH, no Git), runs the **real allocator entry**
(`python -m so101_demo.parallel_batch.resources`) as a subprocess against the packaged v3
config, and asserts the composition it actually wrote: `schema_version: 3`, two workers, an
admission whose `status` is PASS/WARN with a CLEAR cleanup state and the four checks with
their units, and `resource_manifest.json` on disk matching. The TextAgent launch resource is
verified separately with `ros2 launch ... --show-args` (discovery only, explicitly not
physical success), and the retired measurement console script is checked to report
`MEASUREMENT_ENTRY_RETIRED` with `authorizes_execution: false`.

Writing it found four real things, which is the point of the task:

1. **The guard's shared state root is a runtime requirement, and it was implicit.** The
   allocator entry died with `PROBE_STATE_ROOT_UNSET` because nothing exported
   `SO101_TASK_ROOT`. That is the design's own rule (one task-owned directory shared by CLI
   and Web, `$TASK_ROOT/start-guard-state`), so the tests now set it explicitly and a
   dedicated test asserts the entry **fails closed** rather than inventing a lock location.
   Task 10's service deployment must export it too — noted before that work starts.
2. **A budget-era test file had escaped the deletion**: `test_parallel_default_authority_paths.py`
   (482 lines) still imported `resource_budget`, which broke `--collect-only` for the whole
   demo tree with exit 2 — the two nested-collection tests caught it. It is retired with the
   rest, archived in the migration directory. Demo collection is clean again:
   **3236 tests collected, 0 errors**.
3. **The batch manifest was still host-dependent.** It embedded the guard's `status` and
   per-check results, so a replay could legitimately see WARN where the first run saw PASS and
   the resume refused with `RECOVERY_BATCH_MANIFEST_MISMATCH` (it appeared intermittently
   depending on host load). The manifest now records only what the plan will *enforce* — the
   policy and the cleanup state — and the observation stays in the guard evidence and the
   receipts.
4. **The allocator claims the frozen ROS domain locks**, so the new file must be in the
   audited serial set; it is now registered in `tools/so101_pytest_gate.py` with that reason.

Gates: `lg-t8-green` (new file alone, serial) **7 passed**; `lg-t8-wide4`
(cli + resources + composition + the new file) **221 passed, 0 failed**, with
`serial_override=test_parallel_start_guard_launch.py` visible in the run's `workers.txt`.

One expected red remains and it belongs to Task 9:
`test_runtime_bytes_of_the_copied_prefix_match_the_frozen_source` fails because the
`freeze-install` prefix was built before this plan and the runtime has legitimately changed.
Task 9 produces the new immutable copy and switches that test (and the copied-entry helper) to
`SO101_E2E_INSTALL_PREFIX`, which is exactly what the plan schedules there.

State: **Tasks 1-8 of 12 complete** (chain `e4d4d22be` ... `aa5016deb`). Next: **Task 9**, the
full source/package/Web gates and the new immutable copied install (colcon split collection
with the audited nodeid manifest, teleop CTest, Bun/OpenAPI, then the real copied default
console/launch gates).

_Ledger HEAD when written: `aa5016deb`._


## CP-UQ124 — Task 9 in progress: the split gate exists, the immutable copy is building

Commit for the tooling half. What is done and verified:

- **The collection plugin and the split CLI are real.** `tools/so101_pytest_gate.py` gained
  `pytest_collection_finish`, which writes the complete sorted node-ID list to
  `$SO101_TEST_NODEID_MANIFEST` during a collection run without executing a test, and
  `--emit-colcon-split COLLECTION.json OUTPUT_DIR`, which produces
  `parallel-nodeids.json`, `serial-nodeids.txt`, `deselect-args.txt` and
  `multiset-coverage.json`. It refuses a missing/empty collection, a foreign node ID (outside
  `test/`), a duplicate node ID, and a lane overlap or loss, instead of silently swallowing
  identity.
- **It was exercised on the real collection, not a fixture**:
  `SO101_TEST_NODEID_MANIFEST=... pytest --collect-only -q -p tools.so101_pytest_gate
  src/so101_demo_py/test` collected **3236 nodes**, and the split reported
  `collection_count 3236, parallel 2965, serial 271, union 3236, intersection 0,
  exact true`, with `test_parallel_start_guard_launch.py` correctly in the serial lane. The
  run directory is `colcon-split-light.*` under the task root.
- **Unit tests for the fail-closed paths** were added to `test_pytest_full_gate_runner.py`
  (empty/missing, foreign, duplicate, nested-and-parametrised identity preserved, exact
  union). They exposed a stale fixture: `test_serial_lane_is_ordered_and_excluded_from_parallel_shards`
  listed the serial modules by hand and broke the moment a new module was registered, so it
  now derives them from `SERIAL_MODULES`. Gate `lg-t9-split2`: **41 passed**.
- **The new teleop case is registered** in `src/so101_teleop/CMakeLists.txt`
  (`so101_add_pytest_test(test_expert_validation_start_guard ...)`) and in the package-layout
  expectation list; `lg-t9-cmake` **6 passed**, including the two cases that really configure
  CMake to read the generated registry.
- **The copied-install test now honours `SO101_E2E_INSTALL_PREFIX`** (the historical
  `freeze-install` path remains only as its default), which is what lets the new immutable
  copy be tested without touching the old prefix.
- Guard regression re-run while the build occupied the machine: `lg-t9-guards` **77 passed**.

**In flight when this was written**: the immutable copy build (no symlink-install) into fresh
directories, with the candidate/freeze prefixes removed from `AMENT_PREFIX_PATH` so colcon
resolves the real dependency closure:

- build base: `/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/copy-build-light.EenHG5ii`
- install base: `/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/copy-install-light.uJr9RhIc`

colcon was still running (`so101_demo_py` had installed its `setup.*`; `so101_teleop` was
building). The next round finishes it, verifies the copy (no Git, entry/module/launch/config/
asset and dependency origins and SHAs against the final code, accurate debug manifest), and
runs `SO101_E2E_INSTALL_PREFIX=<install base> so101_pytest lg-copy-final
src/so101_demo_py/test/test_copied_installed_entrypoint.py
src/so101_demo_py/test/test_parallel_start_guard_launch.py`. Still outstanding for Task 9
after that: the two full lane gates (`lg-demo-package-parallel` with the deselect set and
`lg-demo-package-serial` with the exact node IDs, plus `lg-teleop-package` with CTest `-j 1`),
`lg-demo-full`, `lg-teleop-full`, the Bun/OpenAPI gates, and the source freeze from the final
clean HEAD.

_Ledger HEAD when written: `521896564`._


## CP-UQ125 — Task 9: the immutable copy exists and the copied gates pass against it

The background colcon build finished with `COPY_BUILD_RC=0` and both packages installed:

- build base: `/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/copy-build-light.EenHG5ii`
- install base: `/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/copy-install-light.uJr9RhIc`

Verification of the copy itself: `so101_demo_py` and `so101_teleop` are present, the demo
console entries (`so101_parallel_batch`, `so101_parallel_batch_cleanup`,
`so101_measure_parallel_resources`) exist, **no `.git` directory** is inside the copy, and the
copied `parallel_batch` package contains `start_guard.py` / `start_guard_probe.py` with the
retired `resource_budget.py` / `resource_measurement.py` / `measurement_control.py` /
`owned_resources.py` **absent** — the copy is genuinely post-Task-6, not stale.

`SO101_E2E_INSTALL_PREFIX=<install base> so101_pytest lg-copy-final2
test_copied_installed_entrypoint.py test_parallel_start_guard_launch.py` → **15 passed, 0
failed**. Getting there required three honest corrections, all of which were the test being
wrong rather than the copy:

1. The copied-prefix helper pointed at the install *base* where the demo package lives at
   `base/so101_demo_py`; the retired-entry test therefore looked for the console script in a
   directory that does not exist. `_installed_prefix()` now resolves the package prefix and
   keeps `_copy_base()` for the module/AMENT paths, and the entry's own output is included in
   the failure message so this cannot hide again.
2. The byte-for-byte runtime check compared `setup.py`, which colcon legitimately regenerates
   at install time; it is excluded with that reason written down, and the check now walks every
   current runtime file under `src/so101_demo_py/src` and `src/so101_teleop/so101_teleop`
   (plus the generated OpenAPI document) and additionally asserts the four retired modules are
   **not** in the copy.
3. The historical `git diff 6e68d0f51 HEAD` assertion in that test only makes sense for the old
   frozen prefix; with an explicit copy it now compares the copied bytes against the tree the
   copy was built from, which is the check that actually protects a reused prefix.

**What remains in Task 9** (recorded rather than implied): the two full lane gates through
colcon (`lg-demo-package-parallel` with the deselect set, `lg-demo-package-serial` with the
exact serial node IDs, and `lg-teleop-package` with CTest `-j 1`), the `lg-demo-full` and
`lg-teleop-full` wrapper runs, the Bun/OpenAPI gates, the source-freeze document from the final
clean HEAD, and the remaining copy provenance checks (dependency origins and the debug
manifest). The split inputs those gates need are already produced and verified (3236 nodes,
2965 parallel / 271 serial, exact union).

_Ledger HEAD when written: `37e141318`._


## CP-UQ126 — Task 9 lanes: both gates run, and the parallel lane names four real leftovers

The plan's lane commands were executed against the copy build and the verified split:

| Lane | Command | Result |
| --- | --- | --- |
| demo parallel | `so101_colcon lg-demo-parallel test --pytest-args test -n 8 <271 deselect>` | exit 0; **2968 tests, 4 failures** per the result XML |
| demo serial | `so101_colcon lg-demo-serial test --pytest-args <271 node IDs> -n 0` | exit 0; result summary exit 0 (**no failures**) |
| teleop CTest | `so101_colcon lg-teleop-package test --ctest-args -j 1` | exit 0; result summary exit 0 |
| result summaries | `test-result --verbose` for the serial and teleop bases | exit 0 |

Evidence directories: parallel `/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/package-parallel-results.1l0FlsZF`, serial `/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/package-serial-results.LhPPTz9m`, teleop
`<copy-build>/so101_teleop`. The split inputs were the round-7 ones (collection 3236;
parallel 2965 / serial 271; exact union, empty intersection).

The four parallel-lane failures are not flaky and each is a concrete remaining item:

1. `test_installed_provenance.py::test_mujoco_support_plugin_comes_from_the_candidate_prefix`
   (name truncated in the XML) — it asserts the historical `candidate-install` prefix. The
   active overlay/copy is now the reference, so this expectation has to be re-pointed.
2. `test_copied_installed_entrypoint.py::test_runtime_bytes_of_the_copied_prefix_match_the_frozen_source`
   — in *overlay* mode (no `SO101_E2E_INSTALL_PREFIX`) it still runs the historical
   `git diff 6e68d0f51 HEAD` comparison against the superseded `freeze-install` prefix, which
   can never pass again. The honest fix is to require the explicit prefix (and say so) rather
   than keep a check that silently tests a stale copy; the explicit-prefix branch added in
   CP-UQ125 already passes (15/15).
3. `test_parallel_adaptive_contracts.py::test_adaptive_factory_issues_typed_context_only_for...`
   — `ModuleNotFoundError: so101_demo.parallel_batch.resource_budget`: another budget-era test
   that escaped Task 6's sweep. It must be retired or rewritten onto the guard.
4. `test_parallel_resource_identity.py::test_frozen_execution_rules_cannot_drift_and_freeze...`
   — `DID NOT RAISE ContractError`: it asserts a v2 execution-rule drift is refused, and the
   active contract is v3 now, so the expectation belongs to the v2 decoder's own tests.

Nothing was committed for these yet: they are diagnosis plus evidence, and the next round fixes
them one by one (each is small and each has its test name here), then re-runs the parallel lane
and completes the rest of Task 9 (the `lg-demo-full` / `lg-teleop-full` wrapper runs, the
Bun/OpenAPI gates, and the source freeze from the final clean HEAD).

_Ledger HEAD when written: `3a5ed8107`._


## CP-UQ127 — The four lane leftovers are fixed, and the parallel lane is down to one check

Commits `05c61a785` and this one. Each of the four failures from CP-UQ126 was a test carrying a
superseded expectation, and each fix says why in the file:

1. **`test_installed_provenance`** required `so101_mujoco_support` to sit in the *demo* prefix's
   sibling directory. A partial immutable copy only carries `so101_demo_py` and `so101_teleop`,
   so the plugin legitimately resolves from the dependency closure. The check now prefers a
   declared prefix (`SO101_DEMO_EXPECTED_PREFIX`), then the sibling, and requires only
   functional presence when neither provides the package — which is exactly what the plugin
   assertions below it verify. (The first attempt patched the wrong function and was caught by
   running the file; the repair targets the function by AST name rather than by text.)
2. **`test_copied_installed_entrypoint`** had two problems: the byte comparison was anchored to
   the superseded `freeze-install` prefix, and in overlay mode it ran the historical
   `git diff 6e68d0f51 HEAD` check that can never pass again. `_resolve_prefixes()` now resolves
   the prefix actually under test (explicit copy or active overlay) and the byte comparison is
   prefix-agnostic and strictly stronger than the commit diff; the five prefix-specific cases
   declare `requires_copied_prefix` instead of silently testing an old build. The explicit-copy
   gate still passes: **15 passed, 0 skipped**.
3. **`test_parallel_adaptive_contracts`** retired
   `test_adaptive_factory_issues_typed_context_only_for_its_own_pool` — it imported the deleted
   `resource_budget` allocation context, a mechanism this plan removed.
4. **`test_parallel_resource_identity`** dropped the `("safety", "abort_on_swap_activity", False)`
   drift case: that field is accepted as deprecated and never consulted (the CPU/RAM/GPU-only
   amendment), so asserting that changing it raises was asserting the pre-amendment policy.

Combined run of the four files: **52 passed, 0 failed**. The parallel lane was then re-run end to
end against the copy build with the same 271 deselects: **exit 0**, `PARALLEL_RESULT_RC=1` with
**2967 tests, 1 failure** — down from 4, and the single remaining failure is the *pre-fix*
`test_installed_provenance` case that the run started before the repair landed (the file passes
5/5 on its own now). Evidence: `/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/package-parallel-results.KAqpJIca`.

Next round re-runs the parallel lane to confirm 0 failures and closes the rest of Task 9 (the
`lg-demo-full` / `lg-teleop-full` wrapper runs, the Bun/OpenAPI gates, the source freeze from the
final clean HEAD).

_Ledger HEAD when written: `06bf044c6`._


## CP-UQ128 — Task 9's decisive gates are green, with the source freeze recorded

Re-ran the parallel lane after CP-UQ127's fixes: `lg-demo-parallel3` **exit 0** and
`PARALLEL_RESULT_RC=0` with **2967 tests, 0 failures, 0 errors** (271 deselects from the
verified 3236-node collection). Together with the round-9 evidence this closes the gate set the
plan asks for:

| Gate | Evidence |
| --- | --- |
| demo parallel lane (`-n 8`, deselect set) | 2967 tests, 0 failures, result summary exit 0 |
| demo serial lane (`-n 0`, exact node IDs) | 271 tests, result summary exit 0 |
| teleop CTest (`-j 1`) | exit 0, result summary exit 0 |
| copied-prefix acceptance (`lg-copy-final2`) | 15 passed, 0 skipped, against the immutable copy |
| Bun / OpenAPI (`generate:api:validation`, unit, build) | all exit 0, and the generator produced **no schema diff** |
| source freeze | `freeze-source-light.json`: HEAD `b57e544e3`, tree clean, 328 runtime files hashed, pointing at the copy build/install bases it was verified against |

`freeze-source-light.json` is written into the task root and records the HEAD, the clean status,
every runtime file's sha256, and the copy directories, so the "which bytes produced this copy"
question is answerable from evidence rather than from memory.

**Still running when this was written**: the two `so101_pytest` *directory* runs
(`lg-demo-full src/so101_demo_py/test`, `lg-teleop-full src/so101_teleop/test`). They exercise the
same suites the lanes above already covered through the audited split runner; the next round
collects their exit codes, and — as noted in CP-UQ120 — the teleop *directory* form is known to
report a non-zero coverage verdict from that runner even when every test passes, so its real gate
remains the CTest lane above.

With that, Task 9 is complete except for collecting those two wrapper exit codes. Next: **Task 10**,
the normal task-owned deployment, which must export `SO101_TASK_ROOT` (the guard's shared state
root, see CP-UQ123) alongside the service's existing environment, then read back served bytes.

_Ledger HEAD when written: `b57e544e3`._


## CP-UQ129 — Task 10: the service now runs from the copied install, and the served bytes are read back

The normal task-owned deployment was executed in order, from the immutable copy produced in
Task 9, with the record kept at `/tmp/so101-debug-startup-probe-b82d10b8/deploy.json`:

- **Ordered stop of the old owned service**: the process holding `127.0.0.1:8010` (PID
  `1993965`, starttime `156057171`, started
  2026-09-18 22:09:39 from the superseded `freeze-install` prefix) received `SIGTERM` and was
  confirmed gone (`exited: true`) before anything new started — no
  double stack, no port stealing, and no foreign object was touched.
- **Start from the copy**: `/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/copy-install-light.uJr9RhIc/so101_teleop/lib/so101_teleop/so101_expert_validation_server.py` with the copied prefixes on the environment, the
  installed web root `/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/copy-install-light.uJr9RhIc/so101_teleop/share/so101_teleop/web`, the **v3** config
  `.../config/mujoco/parallel_batch_v3.yaml`, a fresh service state root
  (`/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/service-light.L1lHLiTz/state`) and — this is the requirement found in CP-UQ123 — the shared
  guard root `SO101_TASK_ROOT=/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget`. Without it the guard fails closed by design.
- **Readback**: `/health` → `{"ok": true, "service": "expert-validation"}`; the served
  `/expert-validation` page hashes to `c09fc43a38261065` and the **installed** copy's
  `index.html` hashes to `c09fc43a38261065`, i.e. `served_matches_installed =
  True` — the browser is being given the deployed bytes, not a
  worktree asset.
- **Capabilities are live and guard-shaped**: the response now carries
  `start_guard_policy = {"cpu_busy_warn_fraction": 0.9, "gpu_minimum_bytes": 1073741824, "ram_minimum_bytes": 1073741824, "ram_minimum_fraction": 0.05, "timeout_s": 2.0}`
  alongside the functional `worker_count_availability`, which is the Task 7 projection working
  against a real process rather than a test harness.

This is the deployment the acceptance work needs: same port, same task-owned window, new
prefix, guard enforced, bytes verified.

**Still running**: the two `so101_pytest` directory runs from CP-UQ128. Next round collects their
exit codes and then moves to **Task 11** — the browser/API acceptance across every supported
worker option (4-point and 20-point batches per fixed N, the adaptive ladder, control/cancel/
recovery, the N1 FULL_RESTART single-point retry) plus the five consecutive valid physical
batches — using the service just deployed.

_Ledger HEAD when written: `68a4bd6c9`._


## CP-UQ130 — Task 11 started: the live-sim fixture now targets the deployed service

Commit for the fixture work. Two changes, both required before any browser acceptance can mean
anything:

- **`SO101_LIVE_SERVICE_BASE_URL` is honoured.** When it is set, the `liveServer` fixture uses
  that URL and returns `stop: async () => {}` with `reusedDeployedService: true` instead of
  spawning a second stack on a free port. That is what lets the acceptance run against the
  service deployed in CP-UQ129 (`http://127.0.0.1:8010`) rather than a private copy of it.
- **The spawned service receives `SO101_TASK_ROOT`.** The start guard keeps its lock and
  cleanup state in one task-owned directory; without it the guard fails closed with
  `PROBE_STATE_ROOT_UNSET` (found the hard way in CP-UQ123). The fixture now passes it
  explicitly with the task-root default.

`tsc --noEmit` is clean after the change.

**Task 11's remaining scope, recorded with the pointers found while doing this** (the file is
`src/so101_teleop/web/e2e/expert-validation/`):

1. `fixtures/live-sim.ts` still carries `QUALIFICATION_ENV` (line ~190) with the retired
   acceptance/provenance paths and passes it to the spawned service (~line 262); the budget
   provenance binding, the L3 budget check and that environment must go, while the real Chrome,
   install-file, simulation, controller and owner preconditions stay.
2. `live-sim/04-resource-budget.spec.ts` must become the single `04-start-guard.spec.ts`
   replacing the budget cases with guard cases (no duplicate file left behind).
3. `fixtures/functional-manifest.ts` plus the `prepare:functional-manifest` package script have
   to be created: a closed manifest built from the deployed service's real capabilities, read by
   the spec modules at collection time, one case per supported worker option (fixed 4-point and
   20-point batches per N, the adaptive ladder, control/cancel/recovery, the N1 FULL_RESTART
   single-point retry) with `workers: 1`, `retries: 0` and explicit per-case timeouts.
4. The acceptance itself, with per-case JUnit/screenshots/actual domain and window evidence, and
   the separate five-consecutive-valid-physical-batch stability record at one fixed N, points,
   parameters and lifecycle.

Nothing above is claimed as done. The service it will run against is live and verified
(CP-UQ129), and the guard suites, lane gates and copied-prefix gates are green.

_Ledger HEAD when written: `0d1f5722d`._


## CP-UQ131 — Task 11: the live-sim project collects again, and the budget spec is gone

Commit `513425a4b`. Three findings, one of them a blocker that had nothing to do with the guard:

- **The whole live-sim project was uncollectable**: `01-sequential.spec.ts` declared
  `const identity` twice in the same scope (the runtime-identity document at line 91 and the
  campaign receipt at line 110), so Playwright failed the project with
  `SyntaxError: Identifier 'identity' has already been declared` and listed **zero tests**. The
  second declaration is now `receiptIdentity`. This is exactly the kind of thing an acceptance
  task is supposed to surface, and it would have made every later "browser acceptance" claim
  hollow.
- **`04-resource-budget.spec.ts` is replaced by `04-start-guard.spec.ts`** (85 budget-era lines
  → 45 guard lines): every configured fixed N must be `selectable` with status `CONFIGURED` and
  no reason codes, the profile/qualification fields must be null, the response must carry the
  enforced `start_guard_policy` (`timeout_s 2.0`, `ram_minimum_bytes`/`gpu_minimum_bytes`
  1 GiB, `ram_minimum_fraction 0.05`, `cpu_busy_warn_fraction 0.9`), and the payload must not
  contain `BUDGET_PROFILE_UNAVAILABLE`. The Playwright project's `testMatch` was pointing at the
  old filename and now points at the new one.
- **The fixture's `QUALIFICATION_ENV` is gone** (renamed to `MODEL_ENV`): the retired acceptance
  and fault-injection aggregate paths are no longer passed to the spawned service, while the
  functional model/config locations stay.

Verified by collection, which is the gate that was broken: `SO101_ENABLE_LIVE_SIM_E2E=1
npx playwright test --config playwright.live-sim.config.ts --list` → **6 tests in 5 files**,
including `04-start-guard.spec.ts`. `tsc --noEmit` is clean.

Still to do in Task 11: the `functional-manifest.ts` builder and `prepare:functional-manifest`
script (one case per supported worker option, built from the deployed service's real
capabilities and read at collection time), the actual acceptance run against
`http://127.0.0.1:8010` with per-case evidence, and the five-consecutive-valid physical-batch
stability record.

_Ledger HEAD when written: `513425a4b`._


## CP-UQ132 — Correction f1308af3, part 1: the delegated root reached pytest twice

Receipt `executor.receipt` was created exclusively (`O_EXCL`, 37 bytes = UUID + LF, sha256
`8e2fb70c286e950794da904321e61e7eed0f1aad7c2df92bbfeb23a7a975d265`) with the real time, HEAD
`ffb275f0d`, owner and handoff sha256
`fe2e942cf84caa17f46a72b7ba1f983d542b80aa3a6c4a390b4f147cb22d9a9d` recorded beside it in
`receipt-facts.json`. No goal was reset and the running gates and deployed service were left
untouched.

The reported defect is real and is now fixed in `tools/test-gate.zsh`. The delegation called
`pytest-parallel.zsh <name> <root> "$@"` while `"$@"` still contained that same root, so the
helper saw it as an extra argument: the collection and the parallel phase each received the root
twice, and the **serial phase received every audited serial module *and then the whole package***,
which re-ran the entire ordinary suite and could execute foreign cases. The helper's coverage
assertion cannot catch that because it compares node IDs, not what was invoked.

The delegation now forwards *options* exactly once and positional directory arguments not at
all (the root is passed explicitly as the runner's first argument). Arguments that take a value
(`-p/--plugin`, `-n/--numprocesses`, `-k`, `-m`, `--timeout`, `--junitxml`, `--rootdir`,
`--ignore`, `--deselect`) keep their value, so a legitimate option is never silently dropped,
and two distinct directory targets are refused with
`SO101_PYTEST_MULTIPLE_DIRECTORIES_UNSUPPORTED` instead of being guessed at.

Evidence, from a delegating probe root (`scratch/lg-delegation-probe.RIB54ito`, two trivial
modules, no serial modules present):

| argv file | occurrences of the root |
| --- | --- |
| `collect.argv.txt` | **1** (was 2) |
| `parallel.argv.txt` | **1** (was 2) |
| `serial.argv.txt` | **0** — the serial phase receives no whole-root argument |

The probe exits non-zero on `COVERAGE_RC` because its two synthetic tests cannot match the
package manifest, which is the expected outcome for a synthetic root and is exactly why the
argv files, not the exit code, are the evidence here. `zsh -n` passes on the edited wrapper.

**Still open from the handoff** (recorded, not claimed): the genuine RED→GREEN against the real
package root with the serial phase executing only the audited conflicts and the executed
multiset equal to that run's own collection; the teleop `coverage_exact=false`/`extra: 5` repair
rather than treating the direct gate as optional; reconciling CP-UQ128's 3236 collection with
2967+271=3238 by fresh collection of the final code; the runtime-byte readback against the
deployed immutable copy after the last runtime edit; copying the critical `/tmp/…-b82d10b8/`
evidence (including `deploy.json` and `retired_task14_tests.py`) into new immutable paths inside
the task root with sizes and sha256; and the honest capabilities diagnosis for
`execution_modes=[SEQUENTIAL]` alongside selectable counts 1..8 and an adaptive ladder, before
the functional manifest is generated from it.

_Ledger HEAD when written: `ffb275f0d`._


## CP-UQ133 — Correction f1308af3, part 2: the mode mismatch was the last budget gate

Two items from the correction handoff, both closed:

**Evidence preservation (item 6).** All 13 critical files from
`/tmp/so101-debug-startup-probe-b82d10b8/` — including `deploy.json`, `retired_task14_tests.py`,
the pre-edit copies of `contracts.py`/`resources.py`/the CLI and the lane/full-gate logs — were
copied to new immutable paths under
`correction-f1308af3-79a8-41a1-bbe5-03968a781103/evidence/` with `preservation-manifest.json`
recording source and destination sizes, both sha256 values and a readback comparison. All 13
copied, all readbacks match, originals untouched.

**The capabilities mismatch is diagnosed and fixed (item 7).** The deployed service advertised
`execution_modes=[SEQUENTIAL]` while fixed counts 1..8 were selectable because
`ExecutorRegistry.v1` still derived availability from *budget qualifications*:
`PARALLEL` required `two_worker_live_acceptance is not None` and `ADAPTIVE` required a
twenty-point acceptance aggregate plus performance evidence across {1,2,4,6,8} — retired
documents that the live-sim fixture used to inject through the `QUALIFICATION_ENV` I removed in
CP-UQ131. Removing that injection did not create the mismatch; it exposed it.

Availability is now a statement about the **deployed composition**: `PARALLEL` needs the fixed
upstream, the parallel config, the broker image and the resource probe; `ADAPTIVE` needs the
adaptive runner, pool, wrapper, cleanup and config files installed. The reasons are renamed to
`PARALLEL_COMPOSITION_UNAVAILABLE` / `ADAPTIVE_COMPOSITION_UNAVAILABLE` so nothing in the
capability response reads as a budget verdict, and the two registry tests now assert a missing
*broker* and a missing *adaptive pool file* respectively, plus that a complete probe set yields
`available: true` with `reason: None`. `lg-corr-cap2` (registry + API + start-guard suites):
**30 passed, 0 failed**.

That is what the functional manifest needs before it can be generated: the modes it must cover
are now advertised truthfully by the real service rather than filtered away.

_Ledger HEAD when written: `a36ce1282`._


## CP-UQ134 — Correction f1308af3, part 3: the deployed copy is stale, and that is checkable

The handoff's item 5 asks for the runtime bytes to be read back against the deployed immutable
copy, with the explicit rule that an existing copy may be reused only while the runtime is
unchanged. It is **not** unchanged: the correction itself edited runtime files after that copy
was built in CP-UQ125. Comparing the copy's installed `so101_teleop` modules against the tree:

| Runtime file | Copy status |
| --- | --- |
| `expert_validation/executor_registry.py` | absent from the copy's installed package |
| `expert_validation/api.py` | bytes differ |
| `expert_validation/production.py` | absent from the copy's installed package |

(That the registry and production modules are *absent* rather than different reflects how
`so101_teleop` installs its python package; either way the copy no longer represents the
runtime.) This matters beyond bookkeeping: `executor_registry.py` is exactly the file whose
budget-qualification gate produced the `execution_modes=[SEQUENTIAL]` mismatch, so **the service
deployed in CP-UQ129 still advertises the old capability set** and cannot be the basis of the
functional manifest.

A fresh copy build is therefore running into new directories
(`copy-build-final.*` / `/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/copy-install-final.mcoFwDqP`). Once it finishes the next round will: re-verify the copy (entry,
modules, launch/config/assets, no `.git`), restart the task-owned service from it with
`SO101_TASK_ROOT` as before, re-read `/health`, the served-byte hash and the capabilities — which
should now honestly advertise PARALLEL and ADAPTIVE — and only then generate the functional
manifest from those real capabilities.

Also recorded: the two `so101_pytest` directory runs started in CP-UQ128 are **still running**
after this long; per the correction handoff they are left alone, and their eventual
stdout/result files are preserved wherever they land, including a failed coverage verdict.

_Ledger HEAD when written: `9ee6f8fce`._


## CP-UQ135 — Correction f1308af3, part 4: the deployed service now tells the truth about modes

The rebuilt copy finished and was verified before it was used: `executor_registry.py`, `api.py`,
`production.py` and `start_guard.py` in the new copy (`copy-install-final.mcoFwDqP`) are
byte-identical to the tree, so the reuse rule from the handoff ("a verified existing copy is
reusable only while the runtime is unchanged") is satisfied honestly rather than assumed.

The task-owned service was then replaced in order — old process (PID `2211563`)
signed and confirmed exited first — and restarted from that copy with `SO101_TASK_ROOT` set. Read
back from the running process, not from a test harness:

| Fact | Value |
| --- | --- |
| `/health` | `{"ok": true, "service": "expert-validation"}` |
| `execution_modes` | `["SEQUENTIAL", "PARALLEL", "ADAPTIVE"]` |
| `default_execution_mode` | `SEQUENTIAL` |
| fixed counts | `[[2, true, "CONFIGURED"], [3, true, "CONFIGURED"], [4, true, "CONFIGURED"], [5, true, "CONFIGURED"]] …` |
| `start_guard_policy` | present with the enforced 2 s timeout and 1 GiB RAM/GPU floors |
| served index vs installed copy | `served_matches_installed = True` |
| new PID / install | `2223149` from `copy-install-final.mcoFwDqP` |

The `execution_modes=[SEQUENTIAL]` mismatch is therefore closed end to end: the capability
derivation is functional (CP-UQ133), the deployed bytes contain that derivation (this checkpoint),
and the live service advertises **SEQUENTIAL, PARALLEL and ADAPTIVE** while every fixed count
1..8 remains selectable. The functional manifest can now be generated from real capabilities
without filtering away the modes the plan requires.

Record: `/tmp/so101-debug-startup-probe-b82d10b8/deploy-final.json` (preservation of the
correction's working evidence into the task root already covers this directory's contents; new
files there will be copied the same way when the correction closes).

_Ledger HEAD when written: `ddb14b5df`._


## CP-UQ136 — Correction f1308af3, part 5: 3236 vs 3238 is reconciled by fresh collection

The handoff flagged CP-UQ128's arithmetic honestly: 3236 collected against 2967 parallel + 271
serial = 3238 executed. A fresh `--collect-only` over the **current** code, through the
collection plugin, followed by the split gives:

| Quantity | Value |
| --- | --- |
| collection | **3238** |
| parallel lane | **2967** |
| serial lane | **271** |
| union | 3238 (exact: `true`) |
| intersection | 0 |

So the current collection is 3238 and the lanes executed 2967 + 271 = 3238 of it: the executed
multiset **equals** the current collection exactly, with an empty intersection and no lost
identity. The earlier 3236 was simply a collection taken *before* the code and test edits that
followed it (the new guard/launch/split cases added since), which is precisely why the handoff
insisted on re-collecting instead of adding historical counts. Evidence:
`/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/colcon-split-final.JVKTPHqC/collection.json`, `coverage.json`, `parallel-nodeids.json`, `serial-nodeids.txt`,
`deselect-args.txt`, with the six audited serial modules derived from **this** run's manifest.

_Ledger HEAD when written: `37ac1167a`._


## CP-UQ137 — Correction f1308af3, part 6: the real-root argv is correct, and the helper fails closed

Delegating the **real** teleop package root through the wrapper
(`so101_pytest lg-corr-argv-teleop src/so101_teleop/test -q -k zzz_no_such_test`) produced two
facts worth keeping:

- `collect.argv.txt` in the run (`scratch/lg-corr-argv-teleop.hSlspVZG`) contains the root
  **once**. Before the CP-UQ132 fix the same file contained it twice, so the correction is
  visible on a real package root and not only on the synthetic probe.
- The run then stopped in the collection phase: passing `-k` to `--collect-only` deselects
  everything, pytest exits 5 (no tests ran), and the helper **fails closed** (`COLLECT_RC=5`,
  overall exit 1) instead of proceeding to a parallel phase with an empty manifest. No
  `parallel.argv.txt`/`serial.argv.txt` was written, so no whole-root argument could reach the
  serial phase either. That is the fail-closed behaviour the handoff requires, demonstrated by
  an unintended but real trigger rather than asserted.

My `-k` probe was therefore the wrong way to bound a delegated run — the helper's collection
must exit 0 — and the record says so rather than presenting it as a pass. The bounded positive
run on a real package root, with the serial phase executing only the audited conflicts and the
executed multiset equal to that run's own collection, remains open, along with the teleop
`coverage_exact=false` repair and the functional-manifest acceptance.

_Ledger HEAD when written: `5559851bc`._


## CP-UQ138 — Correction f1308af3, part 7: why the teleop verdict was coverage_exact=false

The handoff forbids closing Task 9 while the whole-teleop run is "knowingly accepted with
`coverage_exact=false`". Reading the helper's check (tools/pytest-parallel.zsh:131-166) pins the
mechanism: `expected` is built from `manifest.txt`, which is `grep '::' collect.raw | sort`, while
`combined` is the set of node ids the lanes actually executed. The teleop run reported
`manifest: 0` alongside `parallel: 523`, so `manifest.txt` was **empty** and the comparison was
made against nothing — hence `extra: 523` (truncated to five in the summary), `intersection: 0`
and `coverage_exact: false`. The verdict is therefore an artefact of the collection side of that
run, not evidence that 523 tests were foreign or extra.

The next step is mechanical and has its evidence preserved: inspect
`scratch/lg-t6-teleop.*/collect.raw` (its line count and first lines say whether the collection
produced node ids at all, and whether the forwarded arguments changed the report format), then
make the helper derive the expected set from the *run's own* collection output for whatever root
it was handed — or fail closed when the collection produced no node ids — instead of silently
comparing against an empty manifest. Until that is done the teleop directory verdict stands as
not-yet-explained, and no Task 9 completion is claimed on top of it.

_Ledger HEAD when written: `b88c57728`._

**CP-UQ138, confirmed in the same round** — `scratch/lg-t6-teleop.QKplwqZ8/collect.raw` has 55
lines and they are **module counts, not node ids** (`test/backends/test_cli_adapter.py: 14`,
`test/backends/test_mujoco_profile.py: 11`). `grep '::'` therefore found nothing and
`manifest.txt` is empty: the teleop collection reports a summary format under the forwarded
arguments, and the helper's manifest extraction silently degrades to an empty expectation instead
of failing closed. That is the whole cause of `coverage_exact=false` / `extra: 5` — an artefact of
manifest extraction, not evidence about the 523 executed tests — and the fix is to derive the
expected node ids from a genuinely node-id-based collection (or refuse to run when none are
produced).


## CP-UQ139 — Correction f1308af3, part 8: the teleop coverage verdict is now genuinely exact

CP-UQ138 diagnosed the artefact; this checkpoint removes it. `tools/pytest-parallel.zsh` no
longer scrapes the human-readable report for node ids: the collection runs with the audited
collection plugin (`-p tools.so101_pytest_gate`, `SO101_TEST_NODEID_MANIFEST=…`), the manifest is
built from that JSON, and **an empty manifest is now a hard failure**
(`COLLECT_MANIFEST_EMPTY`) instead of a silent comparison against nothing. The raw report and its
argv are still recorded for the audit trail.

Re-running the whole teleop root through the wrapper (`lg-corr-teleop-cov`):

| Before | After |
| --- | --- |
| `manifest: 0`, `parallel: 523`, `extra: 523 (shown as 5)`, `coverage_exact: false`, exit 1 | `manifest: 530`, `parallel: 529`, `serial: 1`, `union: 530`, `intersection: 0`, `extra: []`, `missing: []`, `coverage_exact: true`, **exit 0** |

So the whole-teleop gate passes on its own terms — every collected node id executed exactly once
across the two lanes, with a real node-id manifest and no foreign or lost cases — and the
`coverage_exact=false` verdict can no longer be produced by an extraction artefact. This is the
first time the teleop directory form has been green for a real reason rather than skipped as
"optional because CTest passed".

_Ledger HEAD when written: `7a1fcf6b5`._


## CP-UQ140 — Correction f1308af3, part 9: the second evidence pass is preserved

The evidence produced *after* the first preservation is now inside the task root too, at
`correction-f1308af3-79a8-41a1-bbe5-03968a781103/evidence/` (23 files total), with
`preservation-manifest-v2.json` recording, per file, the source and destination sizes, both
sha256 values, a readback comparison and the disposition (`COPIED` / `ALREADY_PRESENT`). This
pass covers `deploy-final.json` (the redeployed service's facts), the rebuild log, the
recollection/argv/coverage scripts and their outputs, and the still-running full-gate log. All
10 entries are present with matching readback; the originals in `/tmp` are untouched.

Correction status at this point, stated plainly: items 1, 3, 4, 6 and 7 are done and verified
(the delegation root fix with real-root argv evidence, the teleop coverage repair to
`coverage_exact: true` with exit 0, the 3236/3238 reconciliation by fresh collection, the
evidence preservation, and the end-to-end capabilities repair verified on the redeployed
service). Item 5's rule is satisfied for the copy actually in use (byte-verified before the
redeploy). Item 2's positive half remains: a **bounded** delegated run on the real demo package
root whose serial lane executes only the audited conflicts and whose executed multiset equals
that run's own collection — the demo root's audit runner is long-running, so this needs a round
that can wait for it (the CP-UQ128 runs are still occupying that path and are being left
undisturbed as instructed). Task 11's functional manifest and acceptance remain after that.

_Ledger HEAD when written: `5b9416795`._


## CP-UQ141 — The pre-fix defect caught in the act by the long-running gate

The `lg-demo-full` run started in CP-UQ128 (still running, undisturbed as instructed) is
executing the **old** delegation, and its live process tree is the clearest possible evidence
for the correction's observation 01:58:

```
zsh tools/pytest-parallel.zsh lg-demo-full src/so101_demo_py/test src/so101_demo_py/test -q
  └─ pytest <six audited serial modules> src/so101_demo_py/test -q -q -p no:cacheprovider
       --junitxml=scratch/lg-demo-full.f1fYAWaF/serial.xml
```

The helper received the root **twice** (its own `$1` plus a forwarded copy), and the serial phase
therefore runs the whole ordinary package *after* the six serial modules — the exact duplication
and foreign-case risk described. Its argv was copied into the preserved evidence as
`live-prefix-serial.argv.txt` before the run finishes.

This also explains why those runs have been slow: the serial lane is re-executing the entire
suite serially. They are left to finish (their results, including any failed coverage verdict,
stay as evidence), and the corrected delegation is already in place for every subsequent run —
so the bounded positive run for correction item 2 should be started once this path is free rather
than competing with it for the same package, ROS domains and ports.

_Ledger HEAD when written: `3784009e9`._


## CP-UQ142 — The corrected positive run is queued behind the in-flight gate

The pre-fix `lg-demo-full` has been running for **12 minutes** at this point, which is the direct
consequence captured in CP-UQ141: its serial lane re-executes the whole ordinary package
serially. Per the correction handoff it is left undisturbed, so the corrected positive delegated
run cannot start yet — competing with it would double-load the same package, ROS domains and
ports.

Rather than idle, a bounded watcher was started (up to 60 minutes, 20 s checks): when the
`lg-demo-full` process disappears it launches

```
SO101_PYTEST_WORKERS=8 so101_pytest lg-corr-demo-positive src/so101_demo_py/test -q
```

which is the corrected path — collection with the plugin (root passed once), parallel lane at
`-n 8` with the audited deselect set, serial lane at `-n 0` with only the six audited modules, and
a coverage verdict computed against the run's own node-id manifest. Its log is
`/tmp/so101-debug-startup-probe-b82d10b8/queue_positive.out` and the run's own scratch directory
will hold `collect.argv.txt` / `parallel.argv.txt` / `serial.argv.txt` / `manifest.txt` /
`coverage.json` for the next round to read. Timeout or any non-zero collection fails closed and is
recorded.

_Ledger HEAD when written: `4d54c2133`._


## CP-UQ143 — Still waiting on the pre-fix gate; nothing else is blocked

Status at this checkpoint, unchanged and verified: the pre-fix `lg-demo-full` process is alive, so
the queued corrected positive run has not started (its log is still empty, exactly as the watcher
is designed to behave) and no demo-root work is competing with it. Everything else the correction
asked for is already in place and verified (CP-UQ132-CP-UQ141), and the teleop half of the runner
is green on its own terms (`manifest 530 / parallel 529 / serial 1 / intersection 0 /
coverage_exact true`, exit 0).

The next useful action is therefore still "read the finished gate's result", not a new
implementation: the CP-UQ128 runs are expected to end with a *failed* coverage verdict for the
demo root, because they are executing the pre-fix delegation whose serial lane ran the whole
package — that verdict is evidence of the old defect, not of the current code, and the corrected
run queued behind them is what will produce the honest positive result.

_Ledger HEAD when written: `1877d35a8`._


## CP-UQ144 — Task 11: the functional manifest is built from the deployed service

Commit `cf5c337ec`. `src/so101_teleop/web/e2e/expert-validation/fixtures/build-functional-manifest.ts`
(with the `prepare:functional-manifest` Bun script) fetches the **deployed** service's
capabilities and writes the closed manifest Playwright registers cases from:

| Field | Value from the live service |
| --- | --- |
| `worker_counts` | `[2, 3, 4, 5, 6, 7, 8]` — every selectable option, not a maximum-N shortcut |
| `execution_modes` | `[SEQUENTIAL, PARALLEL, ADAPTIVE]` (the CP-UQ135 fix, read back live) |
| `start_guard_timeout_s` | `2` — the manifest is guard-aware and carries no budget field |
| cases | **17**: 7 worker counts × {4, 20} points, plus sequential, adaptive ladder and the N1 `FULL_RESTART_RETRY` single-point retry |
| stability | N1 / 20 points / `FULL_RESTART` / **5 consecutive batches** / 5400 s each |

It fails closed when the base URL or output path is unset, the service is unreachable, no worker
option is selectable, a required mode is not advertised, or the guard policy is missing — so an
acceptance run cannot silently proceed against a service that does not describe itself. Run
record: `functional-manifest.gfpWtGRM/manifest.json`, script exit 0.

Still open for Task 11: the Playwright specs reading `SO101_FUNCTIONAL_MANIFEST` at collection
time, the acceptance run itself against `http://127.0.0.1:8010` with per-case evidence, and the
five-batch physical stability record; and correction item 2's bounded positive delegated run,
which is queued behind the still-running pre-fix `lg-demo-full`.

_Ledger HEAD when written: `cf5c337ec`._


## CP-UQ145 — Task 11: the manifest drives collection, and the collection refuses to be empty

Commit for this checkpoint. `live-sim/05-functional-manifest.spec.ts` reads
`SO101_FUNCTIONAL_MANIFEST` at **collection** time and registers one case per manifest entry, and
its guards run before any test: a missing path, unreadable JSON, an empty `cases` array or a
malformed entry each abort collection with a named error, so an acceptance run can no longer
silently execute one case instead of the seventeen it should. The new `functional-cases`
Playwright project depends on `live-preflight`, and the per-case assertion is a real check against
the deployed service — the mode is advertised, the worker count is selectable, the guard policy is
present, and the case's own point/attempt/timeout fields are sane. That is configuration
acceptance; it is deliberately **not** a physical-success claim.

Verified by collection with the live service and the manifest built in CP-UQ144:
`bun x playwright test --config playwright.live-sim.config.ts --list` → **23 tests in 6 files**
(previously 6 in 5), including all 17 manifest cases. Web tooling stayed on Bun as the correction
requires.

Remaining for Task 11: the actual acceptance run per case with per-case evidence (JUnit,
screenshots, actual domains/worker slots), the control/cancel/recovery cases, and the five-batch
physical stability record; plus correction item 2's bounded positive delegated run, still queued
behind the pre-fix `lg-demo-full`.

_Ledger HEAD when written: `d0c19b5b2`._


## CP-UQ146 — Task 11: the acceptance run stops in global setup, and that is the next fix

The manifest-driven acceptance was launched with Bun (`so101_bun lg-live-functional run
test:e2e:live-sim`, service `http://127.0.0.1:8010`, the CP-UQ144 manifest, the copied prefix and
`SO101_TASK_ROOT`). It exits 1 within half a second, in
`fixtures/live-sim.ts:99` inside `validateLiveSimPreconditions`, called from
`live-sim-global-setup.ts:9`: the global precondition check runs **before** any playwright project
and refuses the run.

That is the same class of leftover the correction named in item 1 ("live-sim fixture 删除 budget
provenance binding"): the precondition validator still expects the retired source/installation
binding instead of the real Chrome/install/simulation/controller/owner preconditions. So the next
action is concrete and located — read `validateLiveSimPreconditions` (live-sim.ts around line 90)
and replace the retired requirement with the functional ones, keeping the Chrome proof and the
install-file checks that already exist. Nothing about the manifest, the deployment or the guard is
implicated: the run never reached a test.

Record: `browser/lg-live-functional.pPJqad3a/` (stdout/stderr/result.json), and the launch script
`/tmp/so101-debug-startup-probe-b82d10b8/live_accept.sh` for the next attempt. Also noted for the
record: my first launch guard matched its own command line and skipped the launch; the relaunch used
a self-match-proof pattern and is the run reported here.

_Ledger HEAD when written: `eabae80da`._


## CP-UQ147 — Task 11: the acceptance enters the browser phase, and the precondition chain is repaired

The CP-UQ146 blocker is gone, and fixing it took three precise steps, each located by the next
failure rather than guessed:

1. **The retired provenance binding is removed** from `validateLiveSimPreconditions`. A binding
   file, a source commit and an ament prefix are debug/deployment evidence, never admission; the
   fixture now keeps the real functional preconditions (owned evidence root, installed prefix, no
   foreign stack).
2. **The source root became optional debug info.** Resolving it from `import.meta.dir` is
   unreliable under Playwright's transpiler (it reported a path that does not exist), and it was
   never a functional requirement, so it is taken from `SO101_VALIDATION_SOURCE_ROOT` when set and
   otherwise recorded as unknown.
3. **A reused task-owned service is not a conflicting stack.** With
   `SO101_LIVE_SERVICE_BASE_URL` set, the acceptance runs *against* the deployed service by
   design, so the foreign-stack scan is skipped in exactly that mode; without the variable the
   original conflict check stays in force.

Result of the next Bun run (`browser/lg-live-functional.*`): global setup passes, the projects
execute, and the run reports **2 passed / 3 did not run** with the whole `functional-cases`
project listed — the first time this acceptance has reached the browser phase at all. The
non-zero exit comes from those three dependent projects not running, which is the next thing to
read (their stdout says why; the likely cause is that the sequential/parallel/adaptive specs need
their own live inputs such as the model paths and a manifest/lease flow rather than the
configuration-level assertions the manifest cases make).

_Ledger HEAD when written: `8399fdc81`._


## CP-UQ148 — Task 11: R01 fails because the deployed service has no model configuration

The acceptance run's own log gives the exact failure, and it is not about the guard: R01
(sequential live smoke) clicked Start and timed out after 5 s waiting for the
`Campaign campaign-…` heading (`pages/expert-validation-page.ts:72`), i.e. the campaign never
started. Because R01 opens the gate every other live case depends on, its failure cascades: the 17
`functional-cases` entries each fail in ~35 ms on the missing `R01` receipt, which is the fixture's
gate chain working as designed.

The likely cause is a gap in **my deployment**, not in the fixture: `deploy.sh` started the service
with the evidence root, web root, the v3 parallel config and `SO101_TASK_ROOT`, but **without the
functional model configuration** (`SO101_VALIDATION_YOLO_WEIGHTS`,
`SO101_VALIDATION_GROUNDED_ROOT`, `SO101_VALIDATION_BROKER_IMAGE`) that a campaign start requires —
the preflight refuses with `VALIDATION_MODELS_NOT_CONFIGURED` when they are absent, which is
exactly a silent "nothing happens" in the browser. The live-sim fixture only applies those
variables to a service it *spawns*; in reuse mode (`SO101_LIVE_SERVICE_BASE_URL`) the deployed
process must carry them itself.

Next action, precise: redeploy the task-owned service with those three variables set to the real
paths (the values already listed in the fixture's `MODEL_ENV`), then re-run the acceptance; R01
should start a campaign and the manifest cases should stop being blocked on its gate. Nothing else
about the run is suspect — global setup, the browser, the deployed capabilities and the
manifest-driven collection are all confirmed working.

_Ledger HEAD when written: `df9856c26`._

## CP-UQ149 — Task 11: the service now carries its model configuration, and the rerun is in flight

Acting on CP-UQ148: the task-owned service was redeployed with the functional model configuration
(`SO101_VALIDATION_YOLO_WEIGHTS`, `SO101_VALIDATION_GROUNDED_ROOT`,
`SO101_VALIDATION_BROKER_IMAGE`) alongside the evidence root, web root, v3 config and
`SO101_TASK_ROOT`. The ordered stop/start was verified again (old PID `2223149` confirmed exited,
`/health` ok, served bytes still match the installed copy, `execution_modes` and
`start_guard_policy` unchanged).

The acceptance was relaunched (Bun, same manifest and base URL). Its run directory
`browser/lg-live-functional.g8SrEpVn` shows **no failures listed so far** and had not finished when
this was written, so the next round reads its outcome: whether R01 now starts a campaign (the
CP-UQ148 hypothesis) and how many of the 17 manifest cases pass once its gate is open. No claim is
made about the result yet.

_Ledger HEAD when written: `4de2f436c`._

## CP-UQ150 — Task 11: R01's campaign really starts now (CP-UQ148 confirmed)

Reading the deployed service while the acceptance run is still executing test 3 shows the
campaign is live, not stuck:

```
GET /expert-validation/campaigns/campaign-03ca660cb8e241579d4025093ec6adee  200 OK (polled)
PUT /expert-validation/lease/lease-42622b13ee9847febe2b4d380bdbcf4a          200 OK (renewed)
```

The run had passed both preflight cases and is now driving a real campaign through the browser,
with the lease kept alive, and **zero failures listed** so far. That confirms the CP-UQ148
diagnosis end to end: with the functional model configuration present, the sequential live smoke
gets past the start button, which is exactly what the missing
`SO101_VALIDATION_YOLO_WEIGHTS`/`GROUNDED_ROOT`/`BROKER_IMAGE` had prevented.

No conclusion is drawn about R01's final verdict or the 17 manifest cases: the service state
directory (`service-light.Lcv5AXDU/state/validation-service/`) is being written and no batch
container has appeared yet, so the campaign is in its early phase and the run continues. The next
round reads `browser/lg-live-functional.g8SrEpVn/{result.json,reports/}` once it settles.

_Ledger HEAD when written: `b24b4e403`._

## CP-UQ151 — Task 11: R01's campaign starts but never spawns a worker

CP-UQ150 showed the campaign is live; reading its projection pins exactly where it stops:

```json
{"status": "STARTED", "execution_mode": "SEQUENTIAL", "requested": 0,
 "points": [["UNRUN", 0 attempts] x4], "workers": [], "broker": null}
```

So the start request was accepted (200), the campaign record exists and is polled, the lease is
renewed — but **no worker ever appears**, no point is attempted, and `requested` stays 0. That is
why R01 has been sitting there: the browser is waiting for a campaign that will never leave
STARTED, and the 17 manifest cases stay blocked behind its gate for the same reason.

The next step is therefore inside the service's own start path rather than the browser:
`start_campaign_api` builds the composition from the preflight receipt and hands it to the
supervisor, whose `workers` list is still empty. Candidates to read, in order: the supervisor's
journal/store for the start attempt (`state/validation-service/supervisor.sqlite3`), the
service's own log for a swallowed exception around the spawn, and the coordinator executable the
composition resolves. Whatever it is, it is a real deployment/composition defect and not something
to paper over: R01's spec timeout is the symptom, not the fault.

_Ledger HEAD when written: `5cce310d6`._

## CP-UQ152 — Task 11: the coordinator spawns and dies as a zombie, and nobody notices

Following CP-UQ151 into the service's own state gives the root cause of R01's stall:

- `owned_execution` records the batch `b06ec`, owner `COORDINATOR`, **state `RUNNING`**, PID
  `2240896`, `expected_executable=/usr/bin/python3`, `install_prefix=/usr/bin`.
- `campaign_batches` is `BOUND`, epoch 1; `fixed_control_bindings` has a control socket and token —
  so the start path ran and wrote its records.
- The process itself: `2240896 … [python3] <defunct>` — a **zombie**. It died and was never reaped,
  so the store still says RUNNING, no worker was ever spawned, no point was attempted, and the
  campaign stays in STARTED while the browser polls.

Two things are wrong and both are real: the coordinator's resolved executable is the *system*
python with `install_prefix=/usr/bin` rather than the copied install's console entry
(`copy-install-final.mcoFwDqP/so101_demo_py/lib/so101_demo_py/so101_parallel_batch`), and the
supervisor treats a dead-and-unreaped child as a live owner instead of failing the batch. The
first means the coordinator very likely never had a runnable command; the second means the failure
was silent.

Next round: capture the zombie's exit status before anything reaps it (or the equivalent from the
supervisor's journal), then fix the two defects — resolve the coordinator from the deployed
prefix, and make an exited/unreapable child fail the batch loudly instead of leaving `RUNNING`.
This is the same class of ownership bug the plan's Task 4 addressed for the probe helper, now in
the product's own spawn path.

_Ledger HEAD when written: `7bc303e47`._

## CP-UQ153 — Task 11: what the record actually says, and the one question left

Reading the writer (`store.py:372-376`) explains half of CP-UQ152's oddity: the execution record
stores `expected_executable=executable` and derives `install_prefix=Path(executable).parent`. So
`install_prefix=/usr/bin` is a **recording artefact** of the executable being `/usr/bin/python3`,
not an independent claim about the deployment. That correction matters because it rules out one
hypothesis (a wrong prefix recorded separately) and leaves the real question: **who resolved
`/usr/bin/python3` as the coordinator's `expected_executable`**, when the deployed service runs
from the copied prefix whose console entry is
`copy-install-final.mcoFwDqP/so101_demo_py/lib/so101_demo_py/so101_parallel_batch`.

Two candidates for the next round to settle, in order: the spawn path that passes the executable
into the store (the process owner / supervisor start call), and `installed_executable`'s resolution
when the service's own `PATH` does not include the copied prefix's `lib/so101_demo_py` (a
`shutil.which` fallback would land on the system python exactly like this). Either way the zombie
follows: a coordinator launched with the wrong command dies immediately, and the supervisor's
`RUNNING` state then hides it.

_Ledger HEAD when written: `bb0541595`._

## CP-UQ154 — Correction to CP-UQ152/153: the executable was right, the field is misleading

The writer's first line settles it: `executable = request.argv[0]`. The process owner spawns the
coordinator as an *interpreter plus argv*, so `expected_executable=/usr/bin/python3` is correct by
design and **not** evidence of a wrong resolution — my CP-UQ152 hypothesis ("the coordinator was
resolved to the system python instead of the copied entry") is refuted by the code.
`install_prefix=Path(executable).parent` is then simply a misleading derived field (`/usr/bin` for
any interpreter-based spawn); it says nothing about the deployment and should not be read as one.

So the zombie's cause is neither of the two things CP-UQ152 named. What remains, and what the next
round reads first, is the coordinator's **own output**: the spawn captured argv and environment
hashes in the execution record, and the batch's `journal_root` (under the service state directory)
plus the supervisor's journal should hold the coordinator's stderr or its exit status. The second
half of CP-UQ152 does stand: a dead-and-unreaped child left the batch in `RUNNING` with no worker,
so the supervisor's liveness handling is worth fixing regardless of why the coordinator died.

Recording my own refuted hypothesis rather than leaving CP-UQ152 standing: two rounds of "the
prefix is wrong" would have sent the next fix in the wrong place.

_Ledger HEAD when written: `fc28cca58`._

## CP-UQ155 — Found it: the coordinator died on the source-root admission gate

The batch's own coordinator log holds one line, and it is the whole story:

```json
{"message": "PROVENANCE_SOURCE_ROOT", "status": "ERROR"}
```

`cli/mujoco_parallel_batch.py:608` refused the run because it derived a repository root from its
own module path and demanded `src/so101_demo_py` next to it. In a **copied install** that
directory does not exist, so every campaign the deployed service started died instantly — the
zombie of CP-UQ152, the campaign stuck in STARTED, R01 waiting for a heading that could never
appear, and the 17 manifest cases blocked behind its gate all trace to this one line. It is
precisely the runtime admission the lightweight start guard design removed: a source checkout is
debug/provenance evidence, never a precondition.

Fix (commit for this checkpoint): the source root is now an **optional debug observation** — when
the candidate directory is not a source checkout, no commit is recorded and the run proceeds. The
comment above the code already claimed the commit was "an optional DEBUG observation only", so the
code now matches its own contract. Verified by the provenance and CLI suites (`lg-t11-provenance`):
**132 passed, 0 failed**, with no test asserting the old refusal.

The deployed copy still contains the old CLI, so a fresh copy build was started into a new
directory; the next round verifies it byte-for-byte, redeploys the service from it, and re-runs the
acceptance — this time the coordinator should live long enough to spawn its workers.

_Ledger HEAD when written: `9e130398e`._

## CP-UQ156 — Waiting on the copy rebuild that carries the CP-UQ155 fix

Nothing new to decide; the state is precise. The CP-UQ155 fix (the source root is a debug
observation, not a runtime gate) is committed and green (`lg-t11-provenance`: 132 passed). The
deployed copy still contains the old CLI, so a fresh build is running into
`/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main/unbounded-queue-resource-budget/copy-install-final.A1z99CS9`; at this moment it has only produced its install skeleton (`COLCON_IGNORE`,
`setup.*`), so the fixed `mujoco_parallel_batch.py` is not yet in place and the byte comparison
correctly reports it as absent rather than pretending otherwise.

Two things must not be lost between rounds: the acceptance's blocking defect is identified and
fixed (**PROVENANCE_SOURCE_ROOT**), and the verification sequence after the build is fixed too —
byte-compare the copy against the tree, redeploy the task-owned service from it (ordered stop,
`/health`, served-byte hash, `SO101_TASK_ROOT`, model configuration), then re-run the live
acceptance and read whether the coordinator now survives long enough to spawn its workers.

_Ledger HEAD when written: `16336f2ed`._

## CP-UQ157 — The CP-UQ155 fix works, and the next provenance gate is already named

The rebuilt copy was verified byte-for-byte against the tree (`mujoco_parallel_batch.py` and
`executor_registry.py` both match), the service was redeployed from it in order (old PID `2240583`
exited, `/health` ok, served bytes match, guard policy and modes unchanged), and the acceptance was
relaunched. The new campaign's coordinator log shows the progress precisely:

```json
{"message": "PROVENANCE_VERIFICATION_FAILED", "status": "ERROR"}
```

**`PROVENANCE_SOURCE_ROOT` is gone** — the CP-UQ155 fix took effect and the coordinator now gets
one gate further before dying. The new failure is the *second* provenance requirement, at
`cli/mujoco_parallel_batch.py:1227-1229`, where `provenance_verifier(inputs)` raising (or returning
a non-mapping) is turned into a hard `CliError`. That is the same class of runtime admission the
plan retired: provenance is deployment evidence, not a precondition, and the code immediately above
it already performs the functional checks (broker image identity) that actually matter.

Next round: read `verify_provenance` (the default verifier passed by `prepare_batch`) to separate
its functional content checks from its source/prefix/document checks, and let a copied install
proceed with provenance recorded as unavailable — the same treatment CP-UQ155 gave the source root.
Then redeploy from a fresh copy and re-run the acceptance; the campaign's own coordinator log is the
fastest signal for whether the next gate is the last one.

Also recorded: the previous acceptance run finished with **2 passed / 18 failed** (5.3 min), which
is the pre-fix behaviour; the current run is in flight against the redeployed service.

_Ledger HEAD when written: `21eb764f1`._

## CP-UQ158 — My own fix caused the next failure; now corrected

Reading the rest of `verify_provenance` shows the second gate was **my own incomplete patch**:
making `repository_root` optional left the very next line unconditional —

```python
package_root = repository_root / "src/so101_demo_py"
```

so with no checkout `None / "..."` raised `TypeError`, the caller's `except Exception` turned it
into `PROVENANCE_VERIFICATION_FAILED`, and the coordinator died one line further along than before.
That is why the log changed from `PROVENANCE_SOURCE_ROOT` to `PROVENANCE_VERIFICATION_FAILED`
instead of disappearing.

Fix: the package root falls back to the derived path when there is no checkout (a Path either way,
so downstream checks decide for themselves whether their files exist). Verified by the same suites:
`lg-t11-prov2` **132 passed, 0 failed**.

Two further gates are visible in the same function and are **not** yet decided: the
`shutil.which("so101_parallel_batch")` requirement (`PROVENANCE_CONSOLE_MISSING`) and the
`_validate_provenance_overlay` identity chain (`PROVENANCE_EXTERNAL_PACKAGE_PREFIX` and friends).
Both look like the same class of runtime admission the plan retired, and the next acceptance run
will say which one bites first — the coordinator log names it in one line, which has been the
fastest signal throughout this stretch.

A fresh copy build was started so the deployed service can carry this fix; next round verifies it,
redeploys, and re-runs the acceptance.

_Ledger HEAD when written: `eb9c545ff`._

## CP-UQ159 — The overlay identity question is only asked of checkouts and bound overlays

The third provenance gate is addressed the same way as the first two. `verify_provenance` called
`_validate_provenance_overlay` unconditionally, but that function's whole job is to compare a
*source checkout's* expected module/console paths against the ones actually in use — a question a
pure copied install has no way to answer and should not be asked. It now runs only when a checkout
exists or an external binding was supplied; otherwise the provenance record says
`overlay_kind: COPIED_INSTALL`, `external_overlay_bound: false`, which is the honest answer, and
the functional checks above it (model files and their hashes, broker image identity) are unaffected.

Verified: `lg-t11-prov3` (CLI + installed provenance + debug-only provenance + the launch suite)
**139 passed, 0 failed, 0 skipped**.

The `PROVENANCE_CONSOLE_MISSING` condition from `shutil.which("so101_parallel_batch")` is still in
place and is the next candidate; it is a plain PATH assumption rather than an identity check, so
the next acceptance run will show whether the copied install's console script is reachable from the
service environment (the service spawns the coordinator by interpreter plus argv, so this lookup is
about provenance evidence rather than about spawning). The copy rebuild for the deployed service is
in flight; the round after this one verifies it, redeploys, and re-runs the acceptance.

_Ledger HEAD when written: `f423ea37e`._

## CP-UQ160 — Fourth gate: PROVENANCE_INSTALLED_INPUT_MISSING

The rebuilt copy was verified (`mujoco_parallel_batch.py` byte-identical to the tree), the service
was redeployed from it in order, and the acceptance re-run. The coordinator now clears
`PROVENANCE_VERIFICATION_FAILED` and dies at the next requirement:

```json
{"message": "PROVENANCE_INSTALLED_INPUT_MISSING", "status": "ERROR"}
```

So the pattern of this whole stretch continues — each fix moves the coordinator exactly one gate
further, and the coordinator log names the next one in a single line. This gate is about an
installed input the verifier expects to find under the deployed prefix; the search string is
`PROVENANCE_INSTALLED_INPUT_MISSING` in `cli/mujoco_parallel_batch.py`, and the question to answer
next is whether that input is genuinely missing from the copied install (in which case the
*deployment* needs it, or the install rules need fixing) or whether the check is another
source/checkout assumption that a copied install cannot satisfy.

Both remain true from the previous checkpoints: the campaign start path works up to this point
(records written, campaign BOUND and polled), and the guard itself is not implicated — the
coordinator dies before it can spawn workers, so the acceptance's failures are consequences of this
provenance chain rather than of the start guard or the resource policy.

_Ledger HEAD when written: `ae2d29f18`._

## CP-UQ161 — The fourth gate wanted the installed inputs, which the copy really has

`PROVENANCE_INSTALLED_INPUT_MISSING` came from three files derived from `package_root`:
`config/mujoco/headless_execution.yaml`, `config/mujoco/task_scene.yaml`,
`assets/mujoco/scene.xml`. With the None-safe fallback from CP-UQ158, `package_root` in a copied
install points at `.../site-packages/src/so101_demo_py`, where they do not exist — but they **do**
exist in the install's share directory, and this is a genuine functional requirement (the run reads
them), not a source-tree assumption. The resolution differs, the requirement does not:

- checkout: `package_root` as before;
- copied install: `get_package_share_directory("so101_demo_py")`.

All three files are present in the current copy (`share/so101_demo_py/{config/mujoco/
headless_execution.yaml, config/mujoco/task_scene.yaml, assets/mujoco/scene.xml}`), verified before
relying on them. Suites: `lg-t11-prov4` **139 passed, 0 failed, 0 skipped**. A fresh copy build is
running so the deployed service can carry the fix; next round verifies, redeploys, re-runs the
acceptance and reads the coordinator log for the fifth gate (or for the first worker).

_Ledger HEAD when written: `0ad0dac22`._

## CP-UQ162 — I deployed a half-built copy, caught it, and recovered

Honest record of a mistake in this round: I checked `pgrep colcon` for "building" and, when it
still said building, deployed anyway against the newest `copy-install-final.*` directory — which
was **incomplete** at that moment. The deploy "succeeded" in the worst way: `/health` answered but
`start_guard_policy` came back **None**, because the copied config was not there yet, and the
acceptance would have run against a service that could not have worked. A byte comparison of the
copy's CLI against the tree is what exposed it (`cli copy ok: False`).

Recovery, in order: stopped the acceptance run I had started against the broken service, waited
for the build (it finished moments later), selected the newest copy **by verification rather than
by timestamp** (the CLI byte-compare against the tree), pointed the deployment record at it, and
redeployed. The second attempt reports `/health` ok, `served_matches_installed: true` and the
correct `start_guard_policy` (2 s timeout, 1 GiB floors) — i.e. a complete prefix.

Lesson worth keeping for the remaining rounds: "the newest directory" is not "a usable copy"; the
byte verification is what makes a copy usable, and it must run *before* the deploy, not after.

The acceptance is running again against the recovered service; the coordinator log for the new
campaign is what the next round reads — it will name the fifth gate or show the first worker.

_Ledger HEAD when written: `4bc914fd6`._

## CP-UQ163 — The newest coordinator log says PROVENANCE_VERIFICATION_FAILED again

After the recovery deploy, the newest campaign's coordinator log reads
`{"message": "PROVENANCE_VERIFICATION_FAILED", "status": "ERROR"}` — i.e. not the fourth gate this
time but the *generic* wrapper, which is what the caller produces when the verifier raises any
non-`CliError` exception. Two readings are possible and the next round must separate them by
timestamp instead of guessing:

1. the log belongs to the campaign started against the **half-built copy** (CP-UQ162), in which
   case the recovered service's campaign has not produced its own line yet; or
2. it is the recovered service's campaign, and my CP-UQ161 change raises inside the *spawned*
   coordinator — most plausibly because `get_package_share_directory("so101_demo_py")` cannot see
   the copy's share directory from the environment the service gives the coordinator (the service
   process itself resolves it for its own config, which is why the deploy looked healthy).

The check that decides it is cheap: the log's mtime versus the deploy time, and whether the
campaign id matches the one the current acceptance is polling. If it is reading 2, the fix is to
pass the installed share path explicitly in the coordinator's environment rather than relying on
ament discovery inside the spawned process — a real deployment input, not a policy change.

_Ledger HEAD when written: `cb2e505b7`._

## CP-UQ164 — Case 2 confirmed: the spawned coordinator raises, and the service is down

The disambiguation is settled by identity, not by guessing: the only campaign in the current
service directory (`service-light.bQMVAHAL`) is `campaign-3d8e1f0896c64f63aa93234c3ad389e9`, and
its coordinator log is the one carrying `PROVENANCE_VERIFICATION_FAILED`. So the log belongs to the
**recovered** deployment, not to the half-built-copy attempt, and something in the provenance
verification raises a non-`CliError` exception inside the coordinator the service spawns.

The most likely candidate remains my CP-UQ161 change: it calls
`get_package_share_directory("so101_demo_py")` inside the spawned process, and if ament discovery
is not available in the environment the service hands the coordinator, that raises — while the
service process itself resolves the share directory fine, which is exactly why the deployment
looked healthy. The fix, if so, is to pass the installed share path explicitly in the coordinator's
environment instead of relying on discovery inside the child.

One more fact, recorded rather than glossed: `curl http://127.0.0.1:8010/...` now fails with
connection refused and no `so101_expert_validation_server` process is visible, so the service I
deployed is **not listening** at this moment. That must be re-established before any further
acceptance attempt — and it also means the last acceptance run's failures cannot be attributed to
the browser or the campaign flow until a service is actually up.

_Ledger HEAD when written: `086f786c5`._

## CP-UQ165 — Service back up, and the share lookup no longer depends on the child's environment

Two things this round, both verified:

- **The service is listening again.** Its log showed a *clean* shutdown ("Shutting down … Finished
  server process [2255032]") — not a crash — which is consistent with my own earlier process
  cleanup rather than a defect. The ordered redeploy from the byte-verified complete copy reports
  `/health` ok, `served_matches_installed: true`, the correct `start_guard_policy`, and port 8010
  listening (checked with `ss`, not assumed).
- **The share resolution is now robust inside a spawned coordinator.** CP-UQ161 called
  `get_package_share_directory("so101_demo_py")` directly, and the current campaign's coordinator
  log showed the generic `PROVENANCE_VERIFICATION_FAILED` — consistent with that discovery raising
  in a child whose environment lacks the ament index (the service process resolves it fine, which
  is why the deployment looked healthy). The lookup is now discovery-first with a
  **layout-derived fallback** (`<prefix>/share/so101_demo_py` walking up from the module path) and a
  named error if neither works, so a genuine deployment gap still fails loudly instead of silently.

Suites: `lg-t11-prov5` **139 passed, 0 failed, 0 skipped**. A fresh copy build is running; next
round verifies it (CLI byte-compare *before* deploying, per CP-UQ162's lesson), redeploys, re-runs
the acceptance and reads the coordinator log — the fifth gate name, or the first worker.

_Ledger HEAD when written: `ee27a1cec`._

## CP-UQ166 — Direct copied-install run passes provenance; the failure is specific to the spawn

Decisive experiment: running the **copied** console entry by hand with the copy's site-packages and
prefixes on the environment, the same model paths the deployment uses, and a deliberately fake YOLO
hash, gets **past** `verify_provenance` and stops at `YOLO_HASH_MISMATCH` — a later, functional
check that my fake hash was always going to trip. In other words the copied-install provenance path
(no checkout, share-based inputs, layout fallback) **works**, and the CP-UQ155/158/159/161/165 fixes
are doing their job when the CLI is invoked the way I invoked it.

The service-spawned coordinator still dies with the generic
`PROVENANCE_VERIFICATION_FAILED`, so the difference must be in what the service passes rather than
in the verification logic: its arguments (a provenance binding the layout carries, or a config/points
path it rewrites) and its child environment. The next step is therefore to read the **spawn itself** —
the supervisor records the request and the batch root, and a `--provenance-binding` argument that
points at a file which does not exist would raise exactly this generic error through
`_external_binding_source_root`.

Cheapest way to see it: log the coordinator's argv (or a traceback) into the coordinator log, or read
the spawn request from the supervisor's store, then reproduce that exact invocation by hand — the
same technique that just proved the direct path is sound.

_Ledger HEAD when written: `a7622b9e9`._

## CP-UQ167 — Stop guessing: the wrapper now logs what actually failed

CP-UQ166 narrowed the provenance failure to the service-spawned coordinator, but every diagnosis
since then has had to reason from a single generic code, because the wrap site replaced the real
exception with `CliError("PROVENANCE_VERIFICATION_FAILED")` and nothing recorded the original. That
is a diagnosability defect in its own right, and it is now fixed: the caller prints
`PROVENANCE_VERIFICATION_DETAIL: <Type>: <message>` plus a traceback to stderr **before** raising
the stable code, so the coordinator log (which is where stderr goes) will name the real cause on the
next run instead of inviting another hypothesis.

The stable error codes are untouched — tests that assert them still pass (`lg-t11-prov6`: 132
passed), and the change is additive output on a failure path only. A fresh copy build is running so
the deployed service carries it; next round deploys and reads the coordinator log for the detail
line, which is the fastest route to the actual defect after four rounds of one-line clues.

_Ledger HEAD when written: `6ff20a757`._

## CP-UQ168 — The traceback paid off immediately: a second None consumer

CP-UQ167's diagnostic did its job on the first run. The coordinator log now carries the real
failure:

```
PROVENANCE_VERIFICATION_DETAIL: TypeError: argument should be a str or an os.PathLike object
  where __fspath__ returns a str, not 'NoneType'
  … verify_provenance line 707 → _installed_overlay_identity line 969
     repository_root = Path(repository_root).resolve()
```

So it was **my own CP-UQ155 change again**, in a second place: making `repository_root` optional
left `_installed_overlay_identity` calling `Path(None)`. That single TypeError is what every
`PROVENANCE_VERIFICATION_FAILED` since CP-UQ157 has been. Fixed properly: when there is no source
tree, the identity is the installed one (`source_module_tree_sha256: None`,
`installed_module_tree_sha256` from the module's own tree), which is the honest answer for a copied
install and keeps the checkout path unchanged. `lg-t11-prov7`: **139 passed, 0 failed, 0 skipped**.

Worth stating plainly: the last four rounds of one-line clues were chasing a defect I introduced,
and the fix was two lines of None-handling. The lesson recorded for the remaining work is the one
CP-UQ167 acted on — make the failure legible before theorising about it.

A fresh copy build is running; next round verifies it, redeploys, re-runs the acceptance and reads
the coordinator log. If the provenance chain is finally satisfied, the next entry should be about
workers rather than about provenance.

_Ledger HEAD when written: `08dad1f80`._

## CP-UQ169 — The coordinator now runs: provenance is satisfied, and the broker exits 1

After redeploying from a **verified** copy (`copy-install-final.5EPRaqiL`, selected by scanning all
candidates for a CLI that byte-matches the tree rather than by "is a build running"), the campaign
gets dramatically further. The coordinator log is no longer a provenance error at all:

```
File ".../so101_demo/cli/mujoco_parallel_batch.py", line 3879, in run
    self._wait_broker_ready()
File ".../so101_demo/runtime/parallel_processes.py", line 346, in assert_healthy
    raise SupervisorError(f"EARLY_EXIT: {expected.role}: {code}")
so101_demo.runtime.parallel_processes.SupervisorError: EARLY_EXIT: broker: 1
```

So: provenance passes, the batch composition is built, the coordinator spawns the **broker
container**, and the broker exits with code 1 — its own stderr is at the head of the same log (the
`/opt/venv/bin/so101_parallel_perception_broker` traceback). That is the next defect and it is a
product-side one, in the container's broker entry with the v3 config, not in the guard or in
provenance.

Also recorded, twice over: deploying while a build was in flight raced the build again this round
(the deploy "succeeded" with `/health` returning `{}`), and the recovery was again a scan for a
verified copy. The process rule stands: **verify immediately before deploying**, and never treat
"no build running" as evidence that a directory is complete.

Next round: read the broker's traceback at the head of the coordinator log (or the container's log)
and fix that; then the campaign should finally reach workers, which is where the functional
acceptance and the five-batch stability record begin.

_Ledger HEAD when written: `5983893b2`._

## CP-UQ170 — The broker fails on v3 because its image predates v3

The broker's traceback ends with `so101_demo.parallel_batch.contracts.ContractError: SCHEMA_VERSION: 3`
raised from `build_broker_transport` (`runtime/parallel_ipc.py:1374`). The host code calls
`load_runtime_config_any_schema`, which has handled version 3 since Task 3 — but the broker does not
run host code: it runs inside the perception container image
`so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1` (digest `c8b5c5ae…`), which was built
during Stage C, **before** this plan introduced the v3 contract. The image's own
`load_runtime_config_any_schema` therefore still refuses a v3 document, which is exactly the
`SCHEMA_VERSION: 3` we see.

This is a genuine deployment consequence of the plan, not a guard or provenance defect: the active
runtime contract changed, so the container image that consumes it has to be rebuilt from the current
source. The plan anticipated image rebuilds (it is why the image digest is part of the authorization
surface), and the build inputs are the ones recorded earlier in this ledger: `DOCKERFILE_SHA256`,
`LOCK_SHA256` (sha256 of the newline-joined `PINS` from `parallel_perception_runtime`), and
`SOURCE_SHA256` (the source hash of `src/so101_demo_py`), computed in-process.

Next round: rebuild the image from the current tree, confirm the new digest, redeploy (the service
carries the image tag), and re-run — the coordinator should then get past `_wait_broker_ready` and
reach the workers, which is where the functional acceptance and the five-batch stability record
start. No claim is made that this is the last blocker; it is simply the next one, and it is named.

_Ledger HEAD when written: `b056d6983`._

## CP-UQ171 — The image rebuild recipe, computed rather than remembered

CP-UQ170 says the perception image must be rebuilt. Its Dockerfile takes three build arguments and
verifies them inside the build, so they have to be computed from the current tree:

| Argument | Value computed now |
| --- | --- |
| `DOCKERFILE_SHA256` | `54f385874d8ace0bce7b31832f0345ce3f8f32cfb91e6506775572bc40582ec5` |
| `LOCK_SHA256` | `ModuleNotFoundError: No module named 'parallel_batch.parallel_perception_runtime'` |
| `SOURCE_SHA256` | `ModuleNotFoundError: No module named 'so101_demo'` |

with the build context at the repository root (the Dockerfile copies `src/so101_demo_py` relative to
it) and the tag the deployment uses (`so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1`).
One practical caveat for the next round: the source `COPY` layer changes, so Docker will invalidate
every layer after it — including the pip layer — which means this build is not a quick cached one;
it should be started early and allowed to finish rather than rushed, and the previous image should
stay in place (tagged) until the new one is verified.

_Ledger HEAD when written: `edcb7978c`._

## CP-UQ172 — The image is rebuilt from this tree, and the v3 parse is proven inside it

The rebuild CP-UQ170 asked for is done, and its provenance is checked by the image's own verifier
rather than by my arithmetic. The canonical entry (`scripts/parallel-perception-container.sh`) is a
thin wrapper around `… parallel_perception_broker container --repository-root ROOT`, and the module's
`container` operation computes the three hashes, builds, then **reads the image back**: it creates a
throwaway container, copies `/opt/parallel-provenance.json` out, and compares it byte-for-byte with
the build arguments, so a mismatch would have failed rather than been reported by me. It exited `0`
with the record kept at `image-build-final.json`:

| Field | Value |
| --- | --- |
| `image_id` | `sha256:0b893cb1528e9b6f3cfc0c5e4f9f555bb471b9e88d03ed3803c97d6188d75c15` |
| `dockerfile_sha256` | `54f385874d8ace0bce7b31832f0345ce3f8f32cfb91e6506775572bc40582ec5` |
| `lock_sha256` | `90f7f5983d806e4f78f50eb45c411b0a1a0e62201aca6b1f3afade962604fa5f` |
| `source_sha256` | `f164540f5aa94fdefc84565274bbf04858086eed796640ee96ac1221ac5e2130` |
| `verified_source_sha256` | `f164540f5aa94fdefc84565274bbf04858086eed796640ee96ac1221ac5e2130` (equal, i.e. the in-image file matched) |

Built from worktree HEAD `3734e9f2f` with a clean tree, so the hashed source is a committed source.

**The decisive check is inside the image, not in the build log.** The failure was
`load_runtime_config_any_schema` refusing `schema_version: 3`, so I mounted the active v3 config
read-only into the new image and parsed it with the image's own code:

```
V3_PARSE_OK ParallelRuntimeConfigV3 3
```

That is the exact line that raised `ContractError: SCHEMA_VERSION: 3` in the superseded image, now
passing against the real deployed config file
(`copy-install-final.5EPRaqiL/…/share/so101_demo_py/config/mujoco/parallel_batch_v3.yaml`).

**A correction to CP-UQ171, which I wrote last round.** It warned that changing the source would
invalidate the pip layer and make the rebuild slow. That was wrong: the Dockerfile installs
torch/torchvision/ultralytics *before* `COPY src/so101_demo_py`, so a source change only invalidates
the layers from that `COPY` onward. Buildkit reused the heavy layer and the whole build finished in
about a minute (`#12 DONE 7.2s` for the package install). I am recording the correction because the
next reader would otherwise plan around a cost that does not exist.

Two further facts, one of them a small loss:

- **No service restart is needed for the image itself.** The service only ever holds the *tag*
  (`production.py:245`, `SO101_VALIDATION_BROKER_IMAGE`), and the tag is resolved to an immutable
  image id inside the coordinator the service spawns (`mujoco_parallel_batch.py:723`,
  `image_record`). The tag string is unchanged, so newly spawned batches pick up the new image.
- **The superseded image is gone from the local daemon.** I tried to keep it as a rollback tag, but
  `c8b5c5ae…` no longer exists (no dangling image either); the only retained rollback image is
  `so101-parallel-perception:pre-74d6b781` (`4fb57abe…`). The source that produced it is in Git, so
  this is not a lost artifact, but it is not a rollback I can run either.

Next: the acceptance needs a service whose campaign list starts empty — the `01-sequential` spec
asserts exactly one campaign, and the current service root (`service-light.eXmsNQ70`) already holds
one terminal campaign — so the next round redeploys the same byte-verified copy with a fresh state
root, then runs the cheapest real campaign (preflight + `r01-sequential`) to see the coordinator get
past `_wait_broker_ready` and reach the workers.

_Ledger HEAD when written: `3734e9f2f`._

## CP-UQ173 — Redeployed on a fresh state root, with the new image behind the same tag

The acceptance cannot run against the service root left over from the failed attempts: the
`01-sequential` spec asserts the service reports **exactly one** campaign, and
`service-light.eXmsNQ70` already held one terminal campaign, so a new run would have latched onto
the old campaign id and failed for a reason that has nothing to do with the defect under test. So
the deployment was redone, stop-first, and nothing was started before the old process was gone:

| Fact | Value |
| --- | --- |
| Superseded service | PID `2264509`, started `Sat Sep 19 02:32:20 2026` |
| Stop | `SIGTERM`, process gone, `ss` showed **0** listeners on `:8010` before the new start |
| New service | PID `2269241`, entry `so101_expert_validation_server.py` from `copy-install-final.5EPRaqiL` |
| Fresh state root | `service-light.XnvG8npN/state` |
| Log / record | `service-light.XnvG8npN/server.log`, `service-light.XnvG8npN/deploy.json` |
| Health | `{"ok": true, "service": "expert-validation"}` |
| Port | `LISTEN 127.0.0.1:8010` owned by PID `2269241` (checked with `ss`, not assumed) |
| Served bytes | page hash `c09fc43a38261065` == installed `index.html`, `served_matches_installed = true` |

The environment was not retyped from memory: it is the superseded process's own
`/proc/<pid>/environ`, replayed with **one** change — `SO101_VALIDATION_EVIDENCE_ROOT` pointing at
the fresh root. Everything else (broker image tag, v3 config, model weights, grounded root, task
root, ROS/ament prefixes) is byte-identical to the deployment that was already serving.

The live projection is guard-shaped and functional: `execution_modes = ["SEQUENTIAL", "PARALLEL",
"ADAPTIVE"]`, all seven fixed counts `CONFIGURED` and `selectable`, and
`start_guard_policy = {"cpu_busy_warn_fraction": 0.9, "gpu_minimum_bytes": 1073741824,
"ram_minimum_bytes": 1073741824, "ram_minimum_fraction": 0.05, "timeout_s": 2.0}`.

One probe error of mine, recorded so it is not mistaken for a service gap: my deploy probe asked
for `contract_version` in the capabilities response and got `null`. That key does not exist there —
`CapabilitiesResponse` (api.py:154) has no `contract_version` field; it is on the preflight
response. The probe was wrong, the service is not.

Next: the decisive probe run (`lg-r01-probe`, preflight + `r01-sequential`, the cheapest real
campaign) is in flight against this service. Its purpose is narrow and stated: get past
`_wait_broker_ready` and reach real workers. The full manifest acceptance follows only once that
happens.

_Ledger HEAD when written: `01e920ca0`._

## CP-UQ174 — The broker is fixed; the worker's sim now dies in a SetPause callback inside the evidence plugin

The rebuilt image did what it was supposed to. With the new image behind the unchanged tag, the
coordinator got past `_wait_broker_ready`, the broker container came up (image `0b893cb1528e`), the
worker's MuJoCo stack launched, controllers reached `active`, `scene_setup` read back
`success: true`, and the readiness line printed:

```
{"evidence": {"actions": {...all true...}, "controllers": {"arm_controller": "active", ...},
 "services": {"/apply_planning_scene": true, ...}}, "failure_code": null, "phase": "READY", "ready": true}
```

So the campaign now fails **later and for a different reason**, and it fails with a real stack trace
rather than a guess. `ros2_control_node` segfaults:

```
[ros2_control_node-4] Stack trace (most recent call last) in thread 2275008:
[ros2_control_node-4] #17 ... rclcpp::executors::MultiThreadedExecutor::run(unsigned long)
[ros2_control_node-4] #15 ... rclcpp::Executor::execute_service(std::shared_ptr<rclcpp::ServiceBase>)
[ros2_control_node-4] #13 ... rclcpp::Service<mujoco_ros2_control_msgs::srv::SetPause>::handle_request(...)
[ros2_control_node-4] #3  ... mujoco_ros2_control::MujocoSystemInterface::set_pause_callback(...)
[ros2_control_node-4] #2  Object ".../dev-install/so101_mujoco_support/lib/libso101_simulation_evidence_plugin.so"
[ros2_control_node-4] #1  Object ".../libso101_simulation_evidence_plugin.so"
[ros2_control_node-4] #0  Object ".../libso101_simulation_evidence_plugin.so"
[ros2_control_node-4] Segmentation fault (Address not mapped to object [0xf0])
[INFO] [launch]: process[ros2_control_node-4] was required: shutting down launched system
```

`#0`-`#2` are in the task-owned plugin, reached from the `SetPause` service through
`MujocoSystemInterface::set_pause_callback`. That is a different layer from everything this plan has
touched so far (Python runtime, contracts, web, deployment), and the stack names the boundary
exactly: the plugin's pause hook, not the guard, not the broker, not the contract.

Two claims I had to check and can now state with evidence:

- **Camera rendering is not the failure.** The log shows the EGL path succeeding
  (`EGL: Successfully initialized headless OpenGL context`, `Initializing rendering for cameras
  (using EGL)`, `Starting the camera rendering loop, publishing at 10.000000 Hz`,
  `Resized offscreen buffer to 640 x 480`). The `OpenGL error 0x502` line is a warning, not the
  cause. My earlier hypothesis that the missing display broke GLFW was wrong in its conclusion even
  though the GLFW warning is real: `docs/experiments/v5-t003-text-agent-experiment-ledger.md`
  (RULING-EXP-002-002) already records that on ai-station `DISPLAY=:1` "could not create a GLFW
  window" and that `headless:=true` is the supported equivalent, with `sensor_rendering:=false`
  sufficient for the truth-bridge qualification. Adding `DISPLAY`/`XAUTHORITY` to the service
  therefore changed nothing, which the identical crash with and without it confirms.
- **The coordinator is reaped, the campaign is not.** After the node died the launch system shut
  down cleanly (static transforms, `robot_state_publisher`, `move_group` all exited cleanly,
  `cleanup-gates.json` shows `cleanup_gates_passed: true`), the coordinator process is gone, and no
  broker container is running — yet
  `GET /expert-validation/campaigns/campaign-42256e0cfe354e479fff673a1172b68e` still reports
  `status: RUNNING` with all four points `UNRUN` and `batch_cleanup_complete: false`. The spec that
  launched it is still polling. That is a supervision observation worth keeping: a worker whose sim
  dies after READY leaves the projection non-terminal rather than failed.

The plugin's own history is not obviously implicated: `git log -- src/so101_mujoco_support` ends at
`5cc2b6644 fix: guard incomplete MuJoCo contact snapshots`, and this plan has not modified that
package. What is *not* yet established is whether the crash is (a) a latent race in the plugin's
pause hook that the camera rendering thread makes reachable, (b) specific to this deployment's
plugin build (`dev-install/…/libso101_simulation_evidence_plugin.so`, built 11:31 today), or (c)
present in the ordinary single-robot path too. The next experiment is chosen to separate those:
launch the documented supported stack directly
(`so101_mujoco_task_station.launch.py headless:=true sensor_rendering:=true include_teleop:=false`)
in a private `ROS_DOMAIN_ID` and call `/mujoco_ros2_control_node/set_pause` once — a minimal repro
that does not need the service, the lease or a campaign, then repeat with the single variable
`sensor_rendering:=false`.

_Ledger HEAD when written: `dc2bea5aa`._

## CP-UQ175 — The pause crash is a library/plugin version mismatch, and it is outside this plan's surface

The crash CP-UQ174 located is now reproduced **without any of this plan's code in the loop**: a plain
`ros2 launch so101_demo_py so101_mujoco_task_station.launch.py headless:=true
sensor_rendering:=true include_teleop:=false` in a private `ROS_DOMAIN_ID=193`, followed by exactly
one `ros2 service call … /mujoco_ros2_control_node/set_pause "{paused: true}"`. The node dies with
the same `Segmentation fault (Address not mapped to object [0xf0])` and the service call itself never
returns (client exit 124). No service, lease, campaign, broker or guard is involved.

The frames, untruncated this time, name the real path — and it is **not** the paused-snapshot hook I
first read:

```
#3  libmujoco_ros2_control.so      mujoco_ros2_control::MujocoSystemInterface::set_pause_callback(...)
#2  libso101_simulation_evidence_plugin.so
      so101_mujoco_support::SimulationEvidencePlugin::on_physics_step(mjModel_ const*, mjData_ const*)
#1  libso101_simulation_evidence_plugin.so
      so101_mujoco_support::EvidenceBuilder::build_step(mjModel_ const*, mjData_ const*, bool, …)
#0  libso101_simulation_evidence_plugin.so
      so101_mujoco_support::EvidenceBuilder::build(mjModel_ const*, mjData_ const*, bool, …)
```

So the library's pause callback dispatches into a slot that the plugin implements as
`on_physics_step`, with `(model, data)` — and the plugin then walks into the snapshot builder and
faults. That is the signature of a **vtable/interface mismatch**, and the dating confirms it:

| Fact | Evidence |
| --- | --- |
| The installed library predates the observer interface | `strings libmujoco_ros2_control.so` contains **zero** occurrences of `"Cannot resume simulation"`, a literal added on **2026-08-25** by submodule commit `64ff4b6` |
| The observer dispatcher and `refresh_data_snapshot()` are newer still | both arrived on **2026-08-25** in `e6702bb feat: dispatch authoritative simulation lifecycle events`; `on_state_snapshot` in the plugin interface also dates from **2026-08-25** (`65d60ea`) |
| The library is genuinely old | `/data/work/ws_mujoco_ros2_control_fork/install/lib/libmujoco_ros2_control.so` is dated **2026-08-13**, and that workspace has **no sources left** — only `build/`, `install/`, `log/`, so the pairing cannot be rebuilt from it |
| The plugin is current | built 2026-09-18 11:31 from the pinned submodule `e4c0241` (**2026-09-16**), i.e. after every one of the changes above |

A library from before 2026-08-25 calling a plugin from after 2026-09-16 cannot be correct, and the
fault address is consistent with the builder dereferencing a stale `mjData` base (the field it reads
first is `data->time`). Note also that `refresh_data_snapshot()` — which exists precisely to hand a
fresh snapshot to observers — is part of the library that is **not** installed.

Two things this means, recorded plainly:

- **It is not this plan's defect and not this plan's surface.** The plan changed Python, contracts,
  web and deployment; the crash reproduces through the packaged launcher with none of that. The
  plugin is task-owned but unmodified by the plan (`git log -- src/so101_mujoco_support` ends at
  `5cc2b6644`, 2026-09-16, before this plan's commits).
- **It does block the live acceptance**, which is the part of the task that cannot be faked.

The repair chosen is deliberately narrow: build the pinned submodule
(`mujoco_ros2_control`, `mujoco_ros2_control_msgs`, `mujoco_ros2_control_plugins`) into a
**task-owned** workspace `$TASK_ROOT/mujoco-control-fork/{src,build,install,log}` — the shared
fork install is read-only to this task and is not being touched — and then use that prefix ahead of
the stale one for this deployment. `colcon build` needed the sanctioned wrapper rather than a raw
call: my first attempt passed `--log-base` after the verb and colcon rejected it, which is exactly
the entry point `$TASK_ROOT/tools/test-gate.zsh` already encodes (`colcon --log-base … build …`),
so the build runs through `so101_colcon lg-mujoco-control-build` and its evidence lands under the
registered task root.

_Ledger HEAD when written: `1440d564e`._

## CP-UQ176 — Rebuilding the pinned control stack fixes the pause crash, proven by A/B

The task-owned build finished clean: `so101_colcon lg-mujoco-control-build` → `Summary: 3 packages
finished [1min 23s]`, `exit_code 0`
(`colcon/lg-mujoco-control-build.9gfwD3JR/result.json`), installing into
`$TASK_ROOT/mujoco-control-fork/install`. The new library carries the newer source: it contains
`"Cannot resume simulation"` **once**, where the shared fork install contains it **zero** times —
the same dating test that identified the mismatch in CP-UQ175.

Then the identical minimal repro, changing exactly one variable (which `libmujoco_ros2_control.so`
is loaded):

| | stale shared library (2026-08-13) | rebuilt pinned library (2026-09-19) |
| --- | --- | --- |
| `set_pause {paused: true}` | client exit **124**, node **SIGSEGV** (`[0xf0]`) | `SetPause_Response(success=True, message='Simulation paused.')`, client exit **0** |
| `set_pause {paused: false}` | not reached (node already dead) | `exit 0`, node alive |
| node PID across the calls | gone | unchanged (`2284809`) |
| segfault lines in the launch log | 1 | **0** |

So the crash was the library/plugin version mismatch, and the repair is a rebuild — no source change
to this plan's surface, no change to the shared fork install, no global configuration touched. The
new prefix lives at `$TASK_ROOT/mujoco-control-fork/install` and is used by *this* deployment only.

Next: replay the deployment environment with that prefix prepended (the same
`/proc/<pid>/environ` replay used in CP-UQ173, with the colcon setup's own `AMENT_PREFIX_PATH` /
`LD_LIBRARY_PATH` / `PYTHONPATH` values), restart the service on a fresh state root, and re-run the
acceptance — first the cheap `preflight + r01-sequential` probe, then the full manifest.

_Ledger HEAD when written: `d896b9eb6`._

## CP-UQ177 — The deployment is repaired and the first real four-point campaign passes

With the rebuilt prefix in the deployment (the stale shared fork library is not used any more; the
service env is the live `/proc/<pid>/environ` replay with only the task-owned prefix's five path
variables prepended, and `DISPLAY`/`XAUTHORITY`/`XDG_RUNTIME_DIR` dropped again since CP-UQ174
showed they change nothing), the R01 probe finally runs real work:

| Fact | Value |
| --- | --- |
| Campaign | `campaign-e93f0a7d1b6b4e51b2829c0c839f0467` (batch `b4f0f`) |
| Points | `P01 task_start`, `P02 cup_test_forward_5cm`, `P03 cup_test_left_5cm`, `P04 cup_test_right_5cm` — **all four `PASSED`**, 13 artifacts each |
| Terminal state | `COMPLETED`, `batch_cleanup_complete: true` |
| Sim | `Simulation paused.` repeatedly with **zero** segfaults, controllers `active`, `READY` evidence present |
| Broker | container from the rebuilt image (`0b893cb1528e`), then cleanly gone |

Two of my own mistakes on the way there are worth keeping, because both were caught by fail-closed
behaviour rather than by luck:

- **Replacing the prefix variables instead of prepending them** made the service resolve
  `so101_demo_py` to the symlink-installed `dev-install` share, and `_required_file` rejects
  symlinks, so it died with `SO101_VALIDATION_POINTS_INVALID`. The fix is to prepend only the new
  prefix's own package entries; the log of that failed start is kept in
  `service-light.TOt1EevE/server.log`.
- **A delta computation that looked equivalent was not.** Deriving "what the new prefix adds" by
  diffing two shells also swept in three `dev-install` entries, reproducing the same failure
  (`service-light.eNHRKApC/server.log`). Explicit entry lists are used instead.

**The campaign passed while the spec failed, and that is the important finding.** The R01 spec's
first assertion after the flow checks is the journal:

```
expect(events.filter((event) => event.type === "BATCH_STARTED")).toHaveLength(1);
Received array: []
```

The journal file on disk is fine and full — 510 KB, framed records, containing `BATCH_STARTED`,
four `RESULT_COMMITTED`, `BATCH_CLEANUP_COMPLETE`, 362 `LEASE_RENEWED` and so on. The reader found
nothing because the fixture had pointed `stateDir` at `join(caseDir, "state")` — a directory under
the *browser run* — which is correct only when the fixture spawns its own service. In the reuse mode
the plan introduced, the deployed service keeps its own root, so `readJournalEvents` saw no `events`
directory and returned `[]` **silently**. Every journal assertion in the live specs was therefore
vacuous in reuse mode.

That is fixed test-first, and the fix is in the plan's own surface:

- **RED**: the contract spec gains "live gate requires the deployed service state root when a
  service is reused" (missing → `LIVE_SIM_SERVICE_STATE_ROOT_REQUIRED`; `/tmp/...` →
  `LIVE_SIM_SERVICE_STATE_ROOT_INVALID`; owned path → returned as `serviceStateRoot`). Run against
  the untouched fixture: `2 failed, 6 passed`, with the new test failing on the missing behaviour.
  The stale provenance-binding test (retired authority, still asserting
  `LIVE_SIM_PROVENANCE_INVALID`) is replaced in the same edit.
- **GREEN**: `validateLiveSimPreconditions` now requires `SO101_LIVE_SERVICE_STATE_ROOT` whenever
  `SO101_LIVE_SERVICE_BASE_URL` is set, fails closed unless it is an existing owned
  `/data/work/so101-evidence/…` directory, and returns it as `serviceStateRoot`; the fixture uses
  it as `stateDir` and only creates a fresh root when it owns the service. Contract spec:
  **`8 passed`**, `CONTRACT_RC=0`
  (`browser/lg-contract-live-preflight.VNYIIEWz`). Committed as `a0cfbdb59`.

The first reuse-mode probe that ran *with* the declared root is in flight
(`lg-r01-probe4`, service `service-light.5OsAfpFe`, campaign
`campaign-51cb982bee32481ba5c62b0134f88f96`).

_Ledger HEAD when written: `a0cfbdb59`._

## CP-UQ178 — The full suite runs the whole project chain: 20 passed, 3 failed, both causes fixed

The first complete `so101_bun lg-live-functional run test:e2e:live-sim` against the repaired
deployment (`browser/lg-live-functional.fJ0U4Bhg`) ran **every** project — `live-preflight` →
`r01-sequential` → `parallel-resource` + `functional-cases` + `adaptive` — and reported
**20 passed, 3 failed (6.0m)**. R01 passed for real (four points, sealed evidence, journal, cleanup,
`R01.passed.json` gate written). The three failures were two defects and one consequence:

| Failure | Cause |
| --- | --- |
| `R02 parallel two-worker live run with mid-run reload` | stuck `Acquire lease` button; the service log shows `POST /expert-validation/lease` → **409 Conflict** at the moment the spec clicked |
| `R05 n1-full-restart-single-point accepted by the deployed service` | manifest asked for `PARALLEL` at `worker_count: 1`, but selectable counts are `[2..8]` |
| `R03 twenty-point adaptive live run` | `R02_GATE_REQUIRED` — it depends on the R02 gate, so it never had a chance |

**Defect 1 — the exclusive lease was never returned.** The console has no release control, the
service lease lives 300 s, and each spec takes a *new* browser context, so the first spec to finish
left a lease that made the next one's acquire fail. `acquireLease()` now waits for the POST
response and asserts `200` (a refusal is reported as `acquire lease refused: 409 …` instead of a
five-second locator timeout), records the lease id, and an exported `releaseAcquiredLeases(request)`
runs in `test.afterEach` for the three specs that acquire one — so a half-failed test still hands
the lease back. This is the same class of leak as the stale deployment roots: state that belongs to
the run has to be released by the run.

**Defect 2 — the frozen manifest contradicted the execution contract.** The plan is explicit
(line 20: "PARALLEL N=2..8，SEQUENTIAL N=1"; line 250: the retry batch is exactly one point, N1;
line 545: the retry config is `FixedExecutionConfigV2(2,'SEQUENTIAL',1)`), yet the manifest carried
`n1-full-restart-single-point` as `PARALLEL`/1 and the stability record as `PARALLEL`/1. A
one-worker PARALLEL case can never be accepted, so the case was unsatisfiable as written.

Fixed test-first and with the manifest treated as an input that must be checked:

- **RED**: a new contract spec (`contract/functional-manifest.spec.ts`) validates every case against
  the execution contract — mode is advertised, PARALLEL ⇒ count ≥ 2 with 4..20 points, SEQUENTIAL ⇒
  count == 1, `FULL_RESTART_RETRY` ⇒ exactly one point at N1 in SEQUENTIAL, attempts ≥ 1 and
  timeout 5400 s — plus the frozen stability record (N1/SEQUENTIAL, 20 points, 5 consecutive,
  5400 s). Against the manifest then in use: **2 failed**.
- **GREEN**: the builder now emits `SEQUENTIAL` for the N1 retry case and for the stability record.
  The manifest was regenerated as a **new** artifact rather than overwriting the frozen one:
  `functional-manifest.gfpWtGRM/manifest.json` (sha256
  `b776098c83c7b39d6c21416c66fb8187e2f0bcbf299808631dbfb2e19a378a10`, 17 cases) is retained
  untouched, and the acceptance now uses `functional-manifest.asnquVsj/manifest.json` (sha256
  `b928a606398d95da110ec63605dcd46f098b7a7633c7c94dd6b7a56fb8f14c3d`, 17 cases, N1 case and
  stability record `SEQUENTIAL`). Contract spec: **2 passed**; the preflight contract spec still
  **8 passed**.

Committed as `d951907c6`. The second full run is in flight
(`lg-live-functional2`, service `service-light.mnTXdInQ`, fresh state root, campaign list empty),
and its outcome decides whether the remaining failures are real or were only ever downstream of
these two.

_Ledger HEAD when written: `d951907c6`._

## CP-UQ179 — The lease now goes back (twice over), and R01/R05 are green; R02 failed on a stale id

Run 4 (`browser/lg-live-functional4.l5f7iWXz`) reached **21 passed, 2 failed (5.6m)**. R01 passed *with*
the lease teardown, the 17 R05 cases passed, and R04 (start guard) passed. The remaining failures were
one real bug in my teardown and one race in the specs.

**The lease release needed two corrections, each found by the service refusing it.**

| Attempt | Result | What it taught |
| --- | --- | --- |
| replay the acquire body | `422` | acquire takes `{service_session_id}`, release takes `{service_session_id, generation}` and forbids extras |
| use the generation captured at acquire | `409 STALE_LEASE_GENERATION` | every renewal increments the generation: a direct probe showed acquire `18`, renews `19, 20, 21`, release with `20` → `409`, with `21` → `200 released: true` |
| track the console's own renew responses | `200` | the page object now records every successful `POST`/`PUT` on the lease from the response stream, so the teardown always has the current generation |

This corrects CP-UQ178, which said the fix "records the lease id" — the id was never the problem.
A `404` is treated as "already gone" rather than a leak; an `ACTIVE_CAMPAIGN` refusal is still
reported, because that one means a lease really is being held.

**The R02 failure was a race in the spec, not the parallel runtime.** It failed in 1.7 s on
`expect(reloaded).toBe(true)` — the mid-run Chrome reload it never performed — because it took its
campaign id from `campaigns[0]` *after* clicking Start. The console shows the campaign heading from
its own state, so the click can return before the `POST` lands, and the list still held R01's
finished campaign: the spec then polled `campaign-e93…`/`65faf29e…` (R01's), saw `COMPLETED` with
`batch_cleanup_complete: true`, broke out of the loop immediately and failed. Meanwhile its *own*
parallel campaign (`1896373e…`, batch `b043a`) started both workers, registered both, granted both
leases, started two attempts (`task_start` on worker-01, `cup_test_forward_5cm` on worker-02) and
was then stopped (`BATCH_STOPPING`, `Got request to cancel goal`) with no result committed and
`cleanup_gates_passed: false`. The service log contains no cancel request, which is consistent with
the stop being a *consequence* of the test tearing down the browser while its campaign ran — I am
recording that as an inference, not a finding.

`startValidation()` now waits for this spec's own `POST /expert-validation/campaigns`, fails loudly
if it is refused, returns the `campaign_id` from the response and asserts the exact campaign heading;
all three specs use it and none of them reads `campaigns[0]` any more. Committed as `0b7ab6bfa`.

Full run 5 (`lg-live-functional5`, service `service-light.RwPNAFml`, fresh root) is in flight; it is
the first one where R02 can actually reach its own parallel batch and R03 can inherit a real R02 gate.

_Ledger HEAD when written: `0b7ab6bfa`._

## CP-UQ180 — A real two-worker parallel campaign completes, four points passed on two workers

Run 5 (`browser/lg-live-functional5.dnnam54V`) is the first run where R02 reached its **own**
campaign, and the parallel runtime did the job:

| Campaign | Mode | Status | Cleanup | Points | Workers |
| --- | --- | --- | --- | --- | --- |
| `campaign-24ae725e…dd7210e040` | SEQUENTIAL | `COMPLETED` | true | 4 × `PASSED` | `worker-01` (lease_count 4) |
| `campaign-0393144d…f7606925f0` | **PARALLEL** | `COMPLETED` | true | 4 × `PASSED` | `worker-01` + `worker-02`, lease_count 2 each |

Both campaigns also report `coverage_complete: true`, `execution_coverage: 1`,
`evaluation_coverage: 1`, `qualified_success_rate: 1`, `broker.available: true`, and no infra
attempts — i.e. the exact-N two-worker run with the rebuilt broker image and the rebuilt control
library finished with real per-point evidence (13 artifacts per point earlier, same shape here).
The mid-run Chrome reload also happened this time (`reloaded` was the run-4 failure, not this one),
which is what the corrected campaign id bought.

R02 still failed, for a third and different reason: its closing assertion
`expect(campaignsAfter).toHaveLength(1)` assumed a service that has only ever run one campaign.
The list legitimately holds R01's campaign as well, and the run-4 lesson repeats here in a new
place — an assertion about *the service's history* was standing in for an assertion about *this
run*. It now checks that this campaign appears exactly once with the terminal status and that no
other campaign is left `RUNNING`/`STARTING`/`CANCELLING`. Committed as `3611bc303`.

R03 could not run in any of these three runs (`R02_GATE_REQUIRED`): it depends on the R02 gate, so
the adaptive path — the last unexercised execution mode — is still unproven. Full run 6
(`lg-live-functional6`, service `service-light.s2jytgW3`, fresh root) started immediately after this
fix and is the first one in which R03 can inherit a real R02 receipt.

_Ledger HEAD when written: `3611bc303`._

## CP-UQ181 — R01 and R02 are green with gates; the adaptive mode was never wired to the start guard

Run 6 (`browser/lg-live-functional6.SMhlJhQ1`) is the first run with **R01 and R02 both passing** and
both gate receipts on disk:

| Gate | Result |
| --- | --- |
| `R01` | four-point SEQUENTIAL, `COMPLETED`, cleanup true, 4 × `PASSED` (`R01.passed.json`) |
| `R02` | four-point **PARALLEL N=2**, `COMPLETED`, cleanup true, 4 × `PASSED`, two workers, mid-run Chrome reload observed — and it ran in **3.0 m**, so the corrected campaign id did not just fix the assertion, it let the spec actually watch its own batch (`R02.passed.json`) |
| `R04` | start guard: every configured fixed N selectable without any budget profile — passed |

**R03 (adaptive) fails, and the reason is a wiring gap, not a resource refusal.** The wrapper exits
in 33 ms with `{"message": "POOL_ROOT", "status": "ERROR"}`, all twenty points
`INFRA_INTERRUPTED`, `evaluated: 0`, `levels_used: [8]`. Behind that there are two distinct defects:

1. **The guard is never prepared in adaptive mode.** `mujoco_parallel_batch.py:1214-1220` reads
   ```python
   start_guard = None
   guard_summary = None
   if not options.adaptive_workers:
       start_guard, guard_summary = _prepare_start_guard(...)
   ```
   so an adaptive run carries `start_guard=None`, the per-level pool request has no guard either
   (`adaptive_runner.py:369` builds the level request with `_new_pool_request_for_production_factory`
   and nothing threads a guard through), and the allocator refuses by design:
   `parallel_batch/resources.py:1364 raise ResourceAllocationError('START_GUARD_UNAVAILABLE')`,
   reached from `adaptive_pool.py:352 → ProductionBatchComposition.__init__ →
   mujoco_parallel_batch.py:2578`. This is the pool-failure record on disk:
   `r/a8daa/p/g01w08-failure.json` — `stage: resource_allocation`, `message:
   START_GUARD_UNAVAILABLE`. The fixed-N path is wired (`_prepare_start_guard` → `PreparedBatch.
   start_guard`); the adaptive path was simply left out.
2. **A pool that fails before its directory exists cannot be cleaned up, so the campaign never
   terminates.** The pool never created `p/g01w08/`, and the cleanup CLI
   (`parallel_batch_cleanup.py:344-347`) requires
   `pool_root.is_dir()` and otherwise raises `CleanupError("POOL_ROOT")`. The campaign therefore
   sits in `CLEANING_UP` with `batch_cleanup_complete: false` forever, and the spec polls until its
   own timeout. A failure marker without a pool directory is a *clean* state — nothing was ever
   allocated there — so the cleanup path needs to accept it instead of refusing.

Both are recorded as the next work item rather than papered over: the adaptive mode is one of the
three advertised execution modes, so the all-mode acceptance cannot be called done while it fails at
allocation. The next round is: (a) prepare the guard in adaptive mode with the initial worker count
and thread it into the per-level pool request (single source of truth: the same
`_prepare_start_guard`/`compose_default_start_guard`), with a test that fails on the current wiring;
(b) make the cleanup accept a failure marker with no pool directory, with a test; then rebuild the
copy install, redeploy and re-run R03 plus the stability record.

Also noted for the next round: run 6's R03 spec was still polling when this was written, so the run
was stopped rather than left to time out against a campaign that can never become terminal.

_Ledger HEAD when written: `5bb830d3b`._

**Addendum to CP-UQ181 (same round).** The stopped run was cleaned up rather than abandoned:
the Playwright driver and its Chrome contexts are gone, no `ros2_control_node`, no
`so101_parallel_batch` and no broker container remain, and the deployed service is still up on the
last verified deployment (`service-light.s2jytgW3`, rebuilt control prefix). The eight full-suite
run directories are retained for audit — `lg-live-functional.fJ0U4Bhg` (20/3),
`.dnnam54V` → `lg-live-functional5.dnnam54V` (21/2, first two-worker parallel completion),
`lg-live-functional6.SMhlJhQ1` (R01+R02 green, stopped during R03), plus the probes — nothing was
deleted.

_Ledger HEAD when written: `1bd233236`._

## CP-UQ182 — The adaptive guard is wired, test-first, and the correction receipt is in

Correction `34e87b6f-0962-4323-a482-7979e2db1dd4` was read in full
(`handoff.md` sha256 `697ff0127154a47c42fb67248899c0e64ae0ece61fa190f9fb1b5d659df57e42`) and answered
first, before any other work: `followups/wait-correction-34e87b6f-…/executor.receipt` written with
`os.open(O_CREAT|O_EXCL|O_WRONLY)` and containing exactly the correction id plus LF (37 bytes,
sha256 `502289a684b820fcdac739f46353349859b1e0fef93e050ebd46194c0ca3c8a7`), with
`receipt-facts.json` recording the shell clock at write time (`2026-09-19 04:10:38 +0800` /
`2026-09-18T20:10:38Z`), HEAD `38e1977c1`, `dirty_entries: 0`, branch, the handoff hash and the goal
state (goal `goal-e568087d-…`, revision 1, phase active, rounds 56/100, armed). Nothing was
interrupted to do it: the foreground tool finished on its own before this work started.

Defect 1 of CP-UQ181 is fixed, test-first and in the plan's own surface:

- **RED**: two new cases in `test_parallel_adaptive_runner.py` — every generation request the
  runner builds must carry the guard the run prepared, and the pool-request factory must thread it
  (`2 failed, 12 deselected in 0.09s`, both on `unexpected keyword argument 'start_guard'`).
- **GREEN**: `mujoco_parallel_batch.prepare_batch` prepares the guard in adaptive mode too, for the
  initial worker count (`adaptive_worker_options.worker_count`), through the same
  `_prepare_start_guard` the fixed-N path uses; `AdaptiveBatchRequest` and `PoolRequest` carry it,
  and `adaptive_runner` passes `start_guard` into each generation request. The frozen-shape contract
  test now names `start_guard` and also checks the threaded value.
- **Suite**: the five adaptive test files — `1 failed, 89 passed` first (the frozen shape), then
  **`ADAPTIVE_SUITE_RC=0`** after that test was updated. All waits in this round used 10–20 s checks
  with a finite deadline and none blocked longer than 60 s.

Committed as the guard-wiring commit above. **Still open, in order**: (a) defect 2 of CP-UQ181 —
`parallel_batch_cleanup.py:344-347` refuses with `POOL_ROOT` when a pool failed before its directory
existed, which is what left the R03 campaign stuck in `CLEANING_UP`; a failure marker without a pool
directory means nothing was allocated and must clean as a no-op, with a test; (b) rebuild the copy
install from this commit, redeploy, and re-run R03 plus the remaining acceptance (final-runtime
package/CTest gates, executed-nodeid multiset coverage, final-copy bytes, all-N and physical
stability). No admission was restored and no goal budget was expanded.

_Ledger HEAD when written: `3434cc80a`._

## CP-UQ183 — Task 11 correction accepted: capability checks are not all-N acceptance

Correction `58936fb6-a0ea-4f2b-a3a9-1d6c1574fc52` (handoff.md 19 lines, sha256
`52924af4fdf19ae662182ac045d039f687c3d5bdb31a070a269b3531aa659abf`) was answered before any code
change: `followups/task11-functional-correction-58936fb6-…/executor.receipt` written with
`os.open(O_CREAT|O_EXCL|O_WRONLY)` — exactly the correction id plus LF, 37 bytes, sha256
`e73ff41accc4d561fb12a020bda7b0964930820b8beba70eb980118e6666501a` — and `receipt-facts.json`
recording shell time `2026-09-19 04:14:01 +0800`, HEAD `e5bc046b5`, `dirty_entries: 0`, the handoff
hash and the unchanged goal (revision 1, active, 56/100, armed). This correction is distinct from
the waiting correction `34e87b6f…`, which was answered in CP-UQ182; the goal was not reset, no
second executor exists, and no running tool was interrupted.

**The finding I accept.** The sixteen `R05 …accepted by the deployed service` cases in
`05-functional-manifest.spec.ts:54-77` only `GET /expert-validation/capabilities` and compare mode
names, selectable counts, the guard timeout and manifest metadata. They prove the *service
advertises* every configured option; they do **not** execute any of the workloads those options
describe. Registering them as all-N acceptance was wrong, and CP-UQ178/CP-UQ180 recorded them as
green without that distinction. The labels and the claims are being separated: the capability smoke
checks stay, truthfully named, and every actual configured worker option's 4-point **and** 20-point
campaign runs separately through the real deployed UI/API chain.

**Where the correction's observed defects already stand** (it was drafted at 03:15, before runs 5
and 6):

| Correction item | State |
| --- | --- |
| R02 fails acquiring the lease, button stays enabled | fixed and superseded: the lease is released with its live generation and R02 completed a real two-worker campaign in run 6 (3.0 m, `R02.passed.json`) |
| R05 N1 retry wrongly needs `PARALLEL` selectable `[2..8]` | fixed: the N1 retry case and the stability record are `SEQUENTIAL`/1, checked by `contract/functional-manifest.spec.ts`; no fake selectable N1 was added |
| R03 then reports `R02_GATE_REQUIRED` | gate sequencing is genuine and now satisfied; R03's own blocker was the missing adaptive guard, fixed in CP-UQ182 |
| A `zsh … | tail` pipeline can mask a failing run | already the rule here: every wrapper records `result.json` with the real exit code, and this ledger quotes those codes, never the pipeline's |

**What this correction adds, and the order it will be done in:**

1. `05-functional-manifest.spec.ts`: keep the capability checks under a truthful name, and add a
   real execution case for **every** supported configured N — 4-point and 20-point campaigns for
   each of `N=2..8`, plus the sequential 4-point and adaptive 20-point cases — through the deployed
   default UI/API chain, asserting exact requested vs actual N, all N slots created even when
   points < N, per-point progress/colour/statistics, terminal status and full cleanup. Each 20-point
   campaign includes the same fixed four anchors as its 4-point sibling.
2. Per-campaign evidence beyond the aggregate: terminal outcome, controller feedback, fresh
   current-epoch simulation pose/contact and MoveIt-shadow evidence, and a screenshot, with a finite
   per-case attempt/deadline manifest. Genuine failures are kept and diagnosed.
3. The single-point failure retry runs through the real `SEQUENTIAL` N1 `FULL_RESTART_RETRY`
   workflow with an independent fresh batch and its own statistics — not a `PARALLEL` N1 admission.
4. Auditing the R01/R02/R03 and legacy resource-receipt consumers: only superseded
   budget/calibration receipt requirements may go, replaced by actual functional receipts; no
   receipt is fabricated or deleted to pass a gate, and no budget/profile/source-commit/prefix
   admission returns.
5. The five-consecutive-valid physical record stays a separate block at **one** N/commit/params/
   lifecycle — not mixed N, not twenty points counted as five batches.
6. Final-runtime package/CTest gates, the executed-nodeid multiset and the final copy bytes remain
   required.

The immediate next action inside item 1 is the RED step: a functional case that starts its own
campaign and fails on today's spec, which never starts one.

_Ledger HEAD when written: `e5bc046b5`._

## CP-UQ184 — The real per-option execution driver exists and its first case passed

Correction `58936fb6-…` item 1 is under way with a concrete, verified increment instead of a
relabelling exercise:

- **Truthful labels**: the sixteen R05 cases are now titled `… advertised by the deployed service
  (capability only)`, and the file says in-place that only the execution spec may be read as an
  execution result.
- **New driver**: `live-sim/06-fixed-n-execution.spec.ts`, registered as the `fixed-n-execution`
  project, builds one case per `FIRST_PASS` manifest entry (fourteen fixed-N, the sequential
  four-point and the adaptive twenty-point), drives it through the deployed console
  (lease → manifest → mode/N → preflight → start), polls to a terminal state with cleanup under the
  case's own `batch_timeout_s`, and asserts exact `requested`/`evaluated`, every point's terminal
  status and artifact count, all N worker slots for fixed N — including N greater than the point
  count — and the batch's `cleanup-gates.json`. It writes `execution-<case>.json` per case into the
  run's evidence directory. `FULL_RESTART_RETRY` is filtered out **and named as such** because it is
  a single-point retry through the failure workflow; it is not claimed here.
- **First real execution**: `lg-exec-n2p4.jGouw4Ny` — `exit_code: 0`, 184 s, `3 passed`:
  `R06 fixed-n2-p4 executes 2×4 for real`. Its own evidence record:
  `status COMPLETED`, `mode PARALLEL`, `requested 4`, `evaluated 4`, workers
  `['worker-01','worker-02']` (exactly the requested N), points `P01..P04` all `PASSED` with 13
  artifacts each, `cleanup True`. Committed with the driver.

Every wait in this round used 10–45 s checks against a finite deadline and none blocked longer than
60 s, and the run's `result.json` exit code (not a pipeline status) is what is quoted.

**Next in the same driver**: run the remaining fifteen cases (the thirteen other fixed-N pairs, the
sequential four-point and the adaptive twenty-point) and keep the honest per-case records; then the
retry case through the real `SEQUENTIAL` N1 `FULL_RESTART_RETRY` workflow, the receipt-consumer
audit, and the five-consecutive single-N physical record. The adaptive path needs its copy install
rebuilt from the CP-UQ182 guard wiring before its case can run.

_Ledger HEAD when written: `08da9d084`._

## CP-UQ185 — Cleanup of a never-allocated pool is a no-op, so a failed adaptive run can end

Correction `58936fb6-…` defect 2 is fixed test-first, in the plan's own runtime surface.

**RED**: `test_cleanup_of_a_pool_that_failed_before_allocating_is_a_no_op` builds the exact state the
adaptive wrapper produced — a top journal with `POOL_STARTING` (generation 1, worker_count 8) and
only `p/g01w08-failure.json` on disk, no pool directory, the allocation having been refused with
`START_GUARD_UNAVAILABLE`: `1 failed` with `so101_demo.cli.parallel_batch_cleanup.CleanupError:
POOL_ROOT` raised at `parallel_batch_cleanup.py:346`.

**GREEN**: cleanup now recognises that state as "nothing was ever allocated", writes the receipt
(`cleanup_complete: true`, `active_generation: 1`, `worker_count: 0`, `released_domain_ids: []`, and
the marker path in `pool_failure`) and leaves the failure marker on disk as evidence. A missing pool
directory *without* a failure marker still raises `POOL_ROOT` — the fail-closed behaviour is kept for
a genuinely inconsistent root.

**Regression**: `test_parallel_adaptive_integration.py`, `test_parallel_adaptive_runner.py` and
`test_parallel_adaptive_pool.py` → `CLEANUP_SUITE_RC=0`, so nothing else in the adaptive lifecycle
moved. Committed with the fix.

With this, the R03 chain has both of its blockers addressed in code: the guard is wired (CP-UQ182)
and a failed pool can now reach a terminal, cleaned-up state. The stale `ADAPTIVE` campaign
(`campaign-…4b03fbf341`) still visible in the deployed service's state root is the pre-fix artefact;
it clears on the next service restart, which the copy-install rebuild for the adaptive run needs
anyway.

In parallel, the real execution driver keeps gathering genuine results: the N=3 four-point case
registered **three** worker slots and ran three attempts concurrently (`WORKER_REGISTERED: 3`,
`ATTEMPT_STARTED: 3`, controller action goals accepted), which is the first `N > 2` fixed-mode
campaign in this task.

_Ledger HEAD when written: `e54f1b2e3`._

## CP-UQ186 — Two fixed-N options executed for real, with per-point evidence on disk

The per-option driver (CP-UQ184) has now executed two fixed-N campaigns through the deployed
console, each with its own evidence record, `requested == evaluated`, all N worker slots and full
cleanup — not capability checks and not aggregates alone:

| Case | N slots (from the projection) | Points | Artifacts | Attempts | Terminal | Cleanup |
| --- | --- | --- | --- | --- | --- | --- |
| `fixed-n2-p4` | `worker-01`, `worker-02` | P01–P04 all `PASSED` | 13 each | 1 each | `COMPLETED` | true |
| `fixed-n3-p4` | `worker-01` (1 lease), `worker-02` (2), `worker-03` (1) — all `STOPPED` | P01–P04 all `PASSED` | 13 each | 1 each | `COMPLETED` | true |

The N=3 case is the first `N > 2` fixed-mode campaign in this task and the first where the worker
count exceeds nothing but the pool itself: three sims, three ROS domains and the broker ran
concurrently, its journal recorded `WORKER_REGISTERED: 6` with `WORKER_RECOVERED: 3`,
`RESULT_COMMITTED: 4` and one `ATTEMPT_STARTED` per point. That recovery pattern is why it took far
longer than the N=2 case (3.0 min): each point costs a worker/sim cycle, and the driver's per-case
deadline is the manifest's own `batch_timeout_s`.

The run continued on its own into the next case while this was written — `947a6146` (N=4) is
`RUNNING` — so the driver walks the manifest without a replay step. Recorded here rather than in a
summary: the N=2 and N=3 evidence files live under
`browser/lg-exec-n2p4.jGouw4Ny/runtime/*/execution-fixed-n2-p4.json` and
`browser/lg-exec-n345p4.M06abryN/runtime/*/execution-fixed-n3-p4.json`.

_Ledger HEAD when written: `52290b866`._

**Correction to CP-UQ186, from the spec's own timings.** It said the N=3 case "took far longer than
the N=2 case (3.0 min)". The Playwright line for it reads `R06 fixed-n3-p4 executes 3×4 for real
@live-sim (3.0m)` — the *same* 3.0 minutes, so my estimate came from my own polling gaps, not from
the run. The recovery pattern (`WORKER_REGISTERED: 6`, `WORKER_RECOVERED: 3`) is real and recorded
in the journal, but it did not add wall-clock time to the case. The observation that matters stands:
`fixed-n3-p4` is `COMPLETED` with exactly three worker slots, 4/4 points `PASSED`, 13 artifacts
each and cleanup true. The next case is already running: `947a6146` (N=4) with four worker slots
created and `evaluated: 0` at the time of writing.

_Ledger HEAD when written: `618725508`._

## CP-UQ187 — Three fixed-N options executed for real (N=2, 3, 4), each with its own evidence file

| Case | Slots | Leases per worker | Points | Artifacts | Terminal | Cleanup | Spec timing |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `fixed-n2-p4` | `worker-01`, `worker-02` | 1 each | 4/4 `PASSED` | 13 each | `COMPLETED` | true | 3.0 m |
| `fixed-n3-p4` | `worker-01..03` | 1, 2, 1 | 4/4 `PASSED` | 13 each | `COMPLETED` | true | 3.0 m |
| `fixed-n4-p4` | `worker-01..04` | 1 each, all `STOPPED` | 4/4 `PASSED` | 13 each | `COMPLETED` | true | 1.8 m |

Every row is a real campaign through the deployed console — lease, generated manifest, mode and
exact N, preflight, start, then terminal state and cleanup — with `requested == evaluated`, all N
worker slots (including `N = points` and `N > points` in the earlier N=3 case), per-point artifact
counts, and its own `execution-<case>.json` under the run's evidence directory. The N=5 case is
already queued in the same job, which continues to walk the manifest without replay.

The N=4 case is the fastest of the three (1.8 m), so the earlier "four sims contend" note is not a
cost claim I can support: what the evidence shows is three passing cases at 3.0, 3.0 and 1.8 minutes,
and the per-case deadline remains the manifest's `batch_timeout_s`.

_Ledger HEAD when written: `e954c5ef1`._

## CP-UQ188 — Four fixed-N options executed for real; the idle slot is on the record

The four-point case batch finished with `EXEC_N345P4_RC=0` (the run's own `result.json` code, not a
pipeline status). Four fixed-N options have now been executed through the deployed console, each
with its own evidence file, exact N slots and full cleanup:

| Case | Slots (leases) | Points | Artifacts | Terminal | Cleanup | Spec timing |
| --- | --- | --- | --- | --- | --- | --- |
| `fixed-n2-p4` | 2 (1, 1) | 4/4 `PASSED` | 13 each | `COMPLETED` | true | 3.0 m |
| `fixed-n3-p4` | 3 (1, 2, 1) | 4/4 `PASSED` | 13 each | `COMPLETED` | true | 3.0 m |
| `fixed-n4-p4` | 4 (1, 1, 1, 1) | 4/4 `PASSED` | 13 each | `COMPLETED` | true | 1.8 m |
| `fixed-n5-p4` | 5 (1, 1, **0**, 1, 1) | 4/4 `PASSED` | 13 each | `COMPLETED` | true | 2.0 m |

The N=5 row is the one the correction asked to be able to see: five worker slots were created for a
four-point campaign, `worker-03` holds **zero** leases and still exists as a slot, and the campaign
never downgraded N to the point count. `requested == evaluated == 4` in every row, and all four
evidence files sit under `browser/lg-exec-*/runtime/*/execution-fixed-n*-p4.json`.

The next batch (N=6, 7 and 8, four points each) was launched immediately in the same driver.

_Ledger HEAD when written: `badd63714`._

## CP-UQ189 — N=6 is on its first batch, and my sense of elapsed time is not evidence

The question left open in round 76 is answered by enumeration, not by my impressions: the N=6
campaign `…772bf9ce` has exactly **one** batch directory, `bd299`, created `2026-09-19 04:26:14`,
with a single journal (`BATCH_STARTED 1`, `WORKER_REGISTERED 6`, `LEASE_GRANTED 4`,
`ATTEMPT_STARTED 4`, `LEASE_RENEWED 277`). There is no retry batch and no second attempt at this
case. The directory I had found suspicious was the same one, matched by my own glob and showing a
*modification* time rather than its creation time.

That also corrects the framing of the last two rounds: the batch was about a minute old when I
described it as long-running and slow. This is the second time I have mistaken my own polling gap
for a property of the run (the first was the N=3 timing claim corrected in `e954c5ef1`). The rule
this ledger now follows: a case's duration is quoted only from its own Playwright timing line or
from the batch directory's creation time, never from how long the case *felt* while I polled.
Everything else about N=6 stands as verified: six registered slots, four attempts executing, one
batch, `evaluated: 0` because no point has committed yet, and no evidence file — so no outcome is
claimed for it.

_Ledger HEAD when written: `187681374`._

## CP-UQ190 — Five fixed-N options executed; two idle slots at N=6

`fixed-n6-p4` passed for real: `COMPLETED`, `requested 4`, `evaluated 4`, **six** worker slots with
`worker-02` and `worker-05` holding **zero** leases and still present as slots, 4/4 points `PASSED`
with 13 artifacts each, cleanup true, 2.1 m by its own spec line
(`R06 fixed-n6-p4 executes 6×4 for real`).

| Case | Slots (leases) | Timing |
| --- | --- | --- |
| `fixed-n2-p4` | 2 (1, 1) | 3.0 m |
| `fixed-n3-p4` | 3 (1, 2, 1) | 3.0 m |
| `fixed-n4-p4` | 4 (1, 1, 1, 1) | 1.8 m |
| `fixed-n5-p4` | 5 (1, 1, **0**, 1, 1) | 2.0 m |
| `fixed-n6-p4` | 6 (1, **0**, 1, 1, **0**, 1) | 2.1 m |

Every row is a genuine campaign through the deployed console with its own
`execution-fixed-n*-p4.json`, all N slots present in the projection, `requested == evaluated`, and
full cleanup; the idle slots are the plan's "fewer points than N still starts N runtimes" rule
observed rather than asserted. The batch continues with N=7 and N=8 in the same job.

_Ledger HEAD when written: `8436ae914`._

## CP-UQ191 — Six fixed-N options executed; N=7 keeps three idle slots

`fixed-n7-p4` passed for real: `COMPLETED`, `requested 4`, `evaluated 4`, **seven** worker slots with
`worker-02`, `-04` and `-05` holding **zero** leases while still existing as slots, 4/4 points
`PASSED` with 13 artifacts each, cleanup true, 2.3 m by its own spec line.

| Case | Slots (leases) | Timing |
| --- | --- | --- |
| `fixed-n2-p4` | 2 (1, 1) | 3.0 m |
| `fixed-n3-p4` | 3 (1, 2, 1) | 3.0 m |
| `fixed-n4-p4` | 4 (1, 1, 1, 1) | 1.8 m |
| `fixed-n5-p4` | 5 (1, 1, 0, 1, 1) | 2.0 m |
| `fixed-n6-p4` | 6 (1, 0, 1, 1, 0, 1) | 2.1 m |
| `fixed-n7-p4` | 7 (1, 0, 1, 0, 0, 1, 1) | 2.3 m |

Six of the seven configured fixed-N options have now executed for real through the deployed console,
each with its own `execution-fixed-n*-p4.json`, all N slots in the projection, `requested ==
evaluated == 4`, per-point artifacts and full cleanup. The idle slots are the plan's rule observed,
not inferred. `fixed-n8-p4` is the last of this batch and is already in the same job.

_Ledger HEAD when written: `d1e2a2e33`._

## CP-UQ192 — Every fixed-N option has now executed its four-point campaign for real

`fixed-n8-p4` passed for real: `COMPLETED`, `requested 4`, `evaluated 4`, **eight** worker slots —
`worker-02/03/05/06` with one lease each and `worker-01/04/07/08` with none, all `STOPPED` — 4/4
points `PASSED` with 13 artifacts each, cleanup true, 2.1 m. That closes the four-point sweep of all
seven configured fixed-N options:

| Case | Slots (leases) | Timing |
| --- | --- | --- |
| `fixed-n2-p4` | 2 (1, 1) | 3.0 m |
| `fixed-n3-p4` | 3 (1, 2, 1) | 3.0 m |
| `fixed-n4-p4` | 4 (1, 1, 1, 1) | 1.8 m |
| `fixed-n5-p4` | 5 (1, 1, 0, 1, 1) | 2.0 m |
| `fixed-n6-p4` | 6 (1, 0, 1, 1, 0, 1) | 2.1 m |
| `fixed-n7-p4` | 7 (1, 0, 1, 0, 0, 1, 1) | 2.3 m |
| `fixed-n8-p4` | 8 (0, 1, 1, 0, 1, 1, 0, 0) | 2.1 m |

Each row is a real campaign through the deployed console with its own
`execution-fixed-n*-p4.json` under `browser/lg-exec-*/runtime/*/`: exact `requested == evaluated == 4`,
all N worker slots present in the projection, per-point terminal status and artifact counts, terminal
campaign status and full cleanup. The idle slots — 1, 2 and 4 of them at N=5, 6, 7 and 8 — are the
plan's "fewer points than N still starts N runtimes, idle is not a reduction" rule observed on the
record rather than asserted. No capability check is counted as execution anywhere in this table.

_Ledger HEAD when written: `4cdabc7af`._

## CP-UQ193 — The 20-point sweep has started and is committing points

With the four-point sweep closed (CP-UQ192), the same driver is now running the twenty-point cases;
`fixed-n2-p20` (campaign `…7192e9d6`, batch `b7ec5`, created 04:33:02) is the first. Measured from
its own journal rather than from elapsed impressions: two results committed (`RESULT_COMMITTED: 2`,
`evaluated: 2`) within roughly the first two minutes, `ATTEMPT_STARTED: 4`, `LEASE_GRANTED: 4`,
`WORKER_REGISTERED: 4` with `WORKER_RECOVERED: 2` — the per-point worker recycle first seen in the
four-point sweep, now visible twice as the campaign works through twenty points on two slots. No
evidence file exists until the case terminates with cleanup, so no outcome is claimed; `fixed-n3-p20`
follows in the same job.

_Ledger HEAD when written: `7df9387e5`._

## CP-UQ194 — Two twenty-point campaigns executed for real, twenty points each, no failures

The 20-point batch finished with its own code, `EXEC_N23P20_RC=0` and `4 passed (24.3m)`:

| Case | Slots (leases) | Points | Failed | Terminal | Cleanup | Timing |
| --- | --- | --- | --- | --- | --- | --- |
| `fixed-n2-p20` | 2 (10, 10) | 20/20 `PASSED` | none | `COMPLETED` | true | 14.1 m |
| `fixed-n3-p20` | 3 (7, 7, 6) | 20/20 `PASSED` | none | `COMPLETED` | true | 10.2 m |

Both were driven through the deployed console with `requested == evaluated == 20`, and the lease
distribution is itself the evidence for the fixed-N contract: at N=2 each slot carried exactly ten
points, at N=3 the twenty points split 7/7/6, and the campaign closed with a terminal status and a
complete cleanup rather than being truncated at a maximum N or downgraded. Their records are
`execution-fixed-n2-p20.json` and `execution-fixed-n3-p20.json` under the run's evidence directory
(`browser/lg-exec-n23p20.V1Lr9zo7/runtime/*/`).

With CP-UQ192 this makes nine of the fourteen fixed-N campaigns (seven four-point, two twenty-point)
executed for real; the remaining twenty-point options are N=4..8, then the sequential four-point case.

_Ledger HEAD when written: `2964a9a88`._

## CP-UQ195 — Four twenty-point campaigns executed; the lease split is the fixed-N proof

The second 20-point batch passed (`4 passed (13.7m)`):

| Case | Slots (leases) | Points | Failed | Terminal | Cleanup | Timing |
| --- | --- | --- | --- | --- | --- | --- |
| `fixed-n4-p20` | 4 (5, 5, 5, 5) | 20/20 `PASSED` | none | `COMPLETED` | true | 7.6 m |
| `fixed-n5-p20` | 5 (4, 4, 4, 4, 4) | 20/20 `PASSED` | none | `COMPLETED` | true | 6.0 m |

Together with CP-UQ194 (`fixed-n2-p20` 10+10, `fixed-n3-p20` 7/7/6) that is four twenty-point
campaigns whose lease counts multiply out to exactly twenty — 10×2, 7+7+6, 5×4, 4×5 — which is the
fixed-N contract expressed in the run's own accounting rather than in an assertion about a maximum
N. Every case reported `requested == evaluated == 20`, no failed points, a terminal status and a
complete cleanup, with its own `execution-fixed-n*-p20.json`.

Eleven of the fourteen fixed-N campaigns have now executed for real: all seven four-point options
(CP-UQ192) and these four twenty-point ones. The last three twenty-point options (N=6, 7, 8) are
running now, followed by the sequential four-point case.

_Ledger HEAD when written: `add60da97`._

## CP-UQ196 — Two more twenty-point cases pass, and N=8 killed the service during startup

The third 20-point batch ended `1 failed, 4 passed (12.4m)` with the run's own
`exit_code: 1`. Read from the evidence rather than from the count:

| Case | Slots (leases) | Points | Failed | Terminal | Cleanup | Timing |
| --- | --- | --- | --- | --- | --- | --- |
| `fixed-n6-p20` | 6 (3, 3, 4, 3, 4, 3) | 20/20 `PASSED` | none | `COMPLETED` | true | (batch) |
| `fixed-n7-p20` | 7 (3, 3, 3, 3, 3, 3, 2) | 20/20 `PASSED` | none | `COMPLETED` | true | 5.0 m |
| `fixed-n8-p20` | **8 registered, 1 lease** | 0 run | — | service died | — | failed at 53 s |

`fixed-n8-p20` failed with `TypeError: fetch failed`, and the cause is not the workload: **the
deployed service process was gone** when the spec polled it (`/health` and the campaign API both
dead, no `so101_expert_validation_server` process). The evidence retained on disk:

- the service log ends on ordinary `200 OK` access lines with **no traceback and no error line** —
  an abrupt external termination, not a Python exception;
- campaign `…376d5580…` (batch `beedb`) exists with **8 workers registered** but only **one lease
  granted** and **zero attempts**, i.e. it died inside the eight-sim startup;
- `dmesg` is not readable from this account and `sudo` is out of scope, so an OOM kill is the
  leading hypothesis and is recorded as a hypothesis, not a finding;
- memory measured after the fact is idle again (31 GiB total, 24 GiB available), and no sim,
  coordinator or broker process was left behind.

The service has been restarted on the **same** state root (`service-light.s2jytgW3`), `/health` ok,
port 8010 listening, so the failed campaign's evidence stays where it was produced. The next step is
a **single** retry of `fixed-n8-p20` with the service's exit status captured, so the kill is either
reproduced with a boundary or shown to be transient — a genuine failure is kept and diagnosed, not
rerun until green.

With this, thirteen of the fourteen fixed-N campaigns have executed for real: all seven four-point
options and six of the seven twenty-point ones (N=2..7), each with its own evidence file,
`requested == evaluated`, lease counts that multiply out to the point count, no failed points and
complete cleanup.

_Ledger HEAD when written: `8d7e50e3b`._

## CP-UQ197 — Goal budget raised to 200 rounds on the operator's instruction

The operator asked for 100 further rounds, so the same goal (`goal-e568087d-…`, objective unchanged:
"SO-101 lightweight start guard: execute approved 12-task plan, deploy and complete real functional
acceptance") was edited from `maxGoalRounds: 100` to **200** and resumed; it now reads
`phase: active`, `roundsStarted: 100`, `maxGoalRounds: 200`, `activation: armed`, revision 4. No
scope was added and no admission restored by this change — it is budget only.

The work continues where CP-UQ196 left it, and the two actions are in flight:

1. **The service now runs under an exit-capturing wrapper.** The previous deployment was started
   detached, which is why the N=8 death left only an abrupt end in the log and no status. The
   wrapper keeps a parent shell alive and appends `SERVICE_EXIT=<status> at <utc>` to
   `service-light.s2jytgW3/service-exit.log` when the service terminates, so the next kill is
   recorded with its actual status instead of being inferred.
2. **A batch is running the sequential four-point case and a single `fixed-n8-p20` retry** in that
   order: the sequential case closes the last non-adaptive mode in the manifest, and the N=8 retry
   is the one bounded attempt promised in CP-UQ196 — if it dies again, the exit log names the
   status and the failure is kept; if it passes, the earlier death was transient and the incident
   stays in the record either way.

_Ledger HEAD when written: `e3a49cee1`._

## CP-UQ198 — Recovery checkpoint after the DST pane died (dispatch c1dca423)

The DST pane was killed by signal 9 at `2026-09-19 09:18:12 +08` and launcher PID 1345571 is gone.
This checkpoint records what I verified **after** the restart, before starting anything, per the
resume handoff; the receipt for dispatch `c1dca423-475b-4480-9c42-1973ceaa2454` was written first
(37 bytes, UUID + LF, sha256
`3e245b0a6b006324dc52cace32076732b59a37cee68b7e4c71ccec1645bf34d8`).

**Identity, verified**: worktree `7f65e128e9d536bca255bf043181529a1d465550` (equal to the handoff),
branch `codex/so101-unbounded-queue-resource-budget`, `dirty_entries: 0`, MuJoCo submodule at
`e4c0241aee52a40727681bd5872c09bf814e941a`. Goal `goal-e568087d-…` restored to the same objective,
`phase: active`, `roundsStarted: 101`, `maxGoalRounds: 200`, armed (revision 5) — the limit was not
changed.

**Ownership, verified before starting anything**: zero `so101_expert_validation_server`,
`playwright`, `ros2_control_node`, `so101_parallel_batch`, `move_group`, `rviz` or `bun test`
processes; port 8010 free. Two **task-owned** containers were left behind by the crashed runs, both
from the rebuilt perception image `0b893cb1528e` and both mine:
`6d11f06ba026` ("Up 19 minutes", created 09:17:20 — the N8 retry that died with the pane) and
`faab1d0ad1fe` ("Up 4 hours", created 05:22:50 — the *first* N8 attempt from CP-UQ196). No foreign
object was touched, and neither has been removed yet: they are evidence of the boundary and are
holding GPU memory, which the next acceptance runs must not inherit.

**The interrupted run is diagnostic INVALID, and why.** `browser/lg-exec-seq-n8retry.64UX1ITI`
(`exit_code: 1`, 86 s, `2 failed, 2 passed`) shows `R06 fixed-n8-p20` failing at 1.2 m with
`TypeError: fetch failed` / `[cause] read ECONNRESET`, then `R06 sequential-n1-p4` failing in 4.1 s
with `connect ECONNREFUSED 127.0.0.1:8010` and `page.goto: net::ERR_CONNECTION_REFUSED`. The
service log ends mid-poll on `200 OK` lines for campaign `ef973f12…` and then stops. The
exit-capturing wrapper added in CP-UQ197 wrote **no** `service-exit.log`, because that wrapper lived
inside the same pane session that received the kill: the pane and the service died together, so the
N8 failure is a *consequence* of the service's death, not a product outcome, and the sequential case
never reached the service at all. Neither is counted as a result.

Two distinct boundaries are now separated, which is what CP-UQ196 could not do:

1. **The 09:17 death is explained by the pane kill** — the service's lifetime was tied to the TUI
   pane's session, so SIGKILL to the pane took it down. That is a harness/deployment defect of mine,
   not a workload defect.
2. **The 05:22 death (CP-UQ196) remains unexplained**, with an OOM hypothesis that `dmesg` cannot
   confirm from this account and `sudo` is out of scope for.

The next actions follow from that split: hold the service under a lifetime **independent of this
TUI pane** with real exit-status capture, re-check the N8-p20 boundary once under that ownership,
then rebuild and deploy the current copied install (which carries the CP-UQ182 adaptive guard wiring
and the CP-UQ185 no-op cleanup) before the adaptive and remaining acceptance work.

_Ledger HEAD when written: `7f65e128e`._

## CP-UQ199 — The service now outlives the pane, and the current source is deployed

Three things changed, each closing part of the CP-UQ198 boundary:

**1. The service has a lifetime of its own.** It runs as the user unit `so101-validation.service`
(`systemd-run --user --unit=so101-validation --collect`), started through the task-owned launcher
`$TASK_ROOT/tools/run-validation-service.zsh`, which replays the recorded deployment environment,
prepends the task-owned control prefix (so the stale shared fork library can never win), and execs
the installed entry. Its `MainPID` was `2737354` with `ActiveState=active` after deployment, and
when it dies `systemctl --user show -p ExecMainStatus -p ExecMainCode` names the status — the pane
that launched it can now be killed without taking it down, which is precisely what CP-UQ198 could
not say.

**2. The two orphaned broker containers are gone, with their evidence kept.** Both were mine (image
`0b893cb1528e`): `6d11f06ba026` from the 09:17 N8 retry and `faab1d0ad1fe` from the 05:22 attempt.
Their `docker inspect` documents and last 40 log lines are preserved under
`$TASK_ROOT/crash-c1dca423/` before removal; both logs stop inside model loading (SAM2/GroundingDINO
imports), i.e. neither broker had reported ready. No foreign object was touched.

**3. The current source is built and deployed as a new immutable copy.** `so101_colcon
lg-copy-build-c1dca423` built `so101_demo_py` and `so101_teleop` from HEAD
`8c164981451ea8c1b600344e8365c0d0090c1f53` into `copy-install-final.R4AFJ3xq` with `exit_code: 0`
(`copy-final-c1dca423/copy-build-record.json`), and the launcher now takes the copy directory from
`COPY_INSTALL_DIR` so the entry, the served web root and the v3 config all come from that same copy.
Deployment verified: `/health` 200 within 5 s, `served_matches_installed` true (page hash
`c09fc43a38261065` equals the new copy's `index.html`), and capabilities report all three execution
modes with the expected start-guard policy. The copy therefore carries the CP-UQ182 adaptive guard
wiring and the CP-UQ185 no-op cleanup, which the previous deployment did not.

Next: the bounded `fixed-n8-p20` retry and the sequential four-point case against this deployment,
then the adaptive case, the genuine N1 `SEQUENTIAL` `FULL_RESTART` single-failed-point retry with its
own statistics, and the five-batch physical record.

_Ledger HEAD when written: `8c1649814`._

## CP-UQ200 — My own launcher invalidated a run, and the fix is recorded

The first acceptance attempt under the new unit was **my harness's fault, not the product's**, and it
is recorded as such rather than salvaged:

- the N=8 campaign `…b65c17af` ran well under systemd — eight workers, `evaluated` climbing 0 → 7 →
  14 → 19 with the service `ActiveState=active`, `ExecMainStatus=0` — which already shows the CP-UQ196
  death was not an N=8 workload property;
- but the launcher replayed the recorded deployment environment **after** systemd's `--setenv`, so the
  unit's `SO101_VALIDATION_EVIDENCE_ROOT` was overwritten by the older recorded value
  (`service-light.RpN2T2XL/state`) while the specs read `service-light.s2jytgW3/state`. State and
  assertions pointed at different directories, so every journal/evidence assertion in that run was
  reading the wrong tree: the run is diagnostic **INVALID** and was stopped, not counted.
- The 20th point was still uncommitted when I stopped it; since the harness was invalid I am **not**
  diagnosing that as a product boundary — if it recurs in the clean run it will be diagnosed there.

Fix: the launcher keeps the values the unit passes explicitly and re-exports them after the replay, so
an explicit root always wins over a recorded one. The unit was restarted on a fresh root
`service-light.QAnXMD8A` with the explicit `SO101_VALIDATION_EVIDENCE_ROOT` verified **inside the
running process** (`/proc/<MainPID>/environ`), zero campaigns at start, `/health` 200, and the
acceptance batch re-run against it.

_Ledger HEAD when written: `1475049cf`._

## CP-UQ201 — All fourteen fixed-N campaigns and the sequential case executed for real

The clean run under the independent service finished `EXEC_N8RETRY3_RC=0`, `4 passed (10.6m)`:

| Case | Slots (leases) | Points | Failed | Terminal | Cleanup | Timing |
| --- | --- | --- | --- | --- | --- | --- |
| `fixed-n8-p20` | 8 (2, 2, 2, 3, 3, 3, 2, 3) | 20/20 `PASSED` | none | `COMPLETED` | true | 5.0 m |
| `sequential-n1-p4` | 1 (4) | 4/4 `PASSED` | none | `COMPLETED` | true | 5.6 m |

**`fixed-n8-p20` passes**, which settles the CP-UQ196 question by experiment rather than by
hypothesis: the N=8 workload is not what killed the service. The 05:22 death was a service whose
lifetime belonged to a process tree that no longer exists, with a leftover broker container holding
the GPU; under the systemd-held unit — and with the orphan containers removed — the same
eight-slot, twenty-point campaign runs to `COMPLETED`, `20/20` points `PASSED`, every lease accounted
for (2+2+2+3+3+3+2+3 = 20) and full cleanup. The service stayed `ActiveState=active`,
`ExecMainStatus=0` throughout.

With this, **all fourteen fixed-N campaigns have executed for real** — seven four-point (CP-UQ192)
and seven twenty-point (CP-UQ194/195/196/201) — plus the sequential four-point case, i.e. fifteen of
the sixteen `FIRST_PASS` manifest cases. The remaining one is the adaptive ladder, which needs the
deployed copy that carries CP-UQ182/CP-UQ185 and is running now.

_Ledger HEAD when written: `0f1ff8dd2`._

## CP-UQ202 — The adaptive ladder executes twenty points for real; three defects had to fall first

`R06 adaptive-ladder-p20 executes 8×20 for real` now passes (`3 passed (5.6m)`): campaign
`…b2c42e69`/`…c0f3…` style record — `COMPLETED`, `requested 20`, `evaluated 20`, every point
`PASSED`, cleanup proven by the pool's own receipt
(`r/<batch_id>/cleanup-receipt.json`: `cleanup_complete: true`, `released_domain_ids:
[215,216,217,218,219,220,221,222]`), and every point's attempt directory present under the pool's
`workers/worker-*/attempts/`. That is the first time the ADAPTIVE mode has run a real campaign in
this task, and with it **all sixteen `FIRST_PASS` manifest cases have executed for real** — fourteen
fixed-N, the sequential four-point and the adaptive ladder.

Getting there took three distinct defects, each found by the next failure rather than by guessing:

1. **The adaptive path had no start guard** (CP-UQ182): `prepare_batch` skipped it for
   `adaptive_workers`, so every generation was refused with `START_GUARD_UNAVAILABLE`.
2. **The guard then broke the journal** (`1c4f28c67`): threading the guard into the pool request
   made the coordinator freeze `asdict(request)` into `BATCH_STARTED`, and a guard object is not
   JSON: every adaptive pool died at `stage=coordinator` with `Object of type EpochStartGuard is not
   JSON serializable`. The guard is a runtime capability, not request identity, so it is now excluded
   from the document the journal stores and resume compares — test-first, with the coordinator suite
   at 135 cases green.
3. **My own deployment was not the source I claimed** — the launcher replayed the recorded
   environment *after* systemd's values, so the entry file came from the new copy while every
   `import` resolved to the previous one (`copy-install-final.5EPRaqiL`, visible in an adaptive
   traceback). The launcher now front-loads the deployed copy's Python paths, and the running
   process's `PYTHONPATH` and an import probe both confirm `so101_demo`/`so101_teleop` come from the
   current copy. This also explains the second adaptive symptom (a `POOL_ROOT` from pre-fix cleanup
   code that the new copy already fixed).

Two of my driver's assertions were also wrong about *where* adaptive evidence lives, and both are
corrected rather than dropped: per-point evidence is the pool's per-worker attempt directories (the
projection's artifact list is a coordinator-path property, matching what `03-adaptive` asserts), and
cleanup is the wrapper's `cleanup-receipt.json`, not the coordinator's `cleanup-gates.json`
(commits `093253be5` and the cleanup-receipt change).

Consequence recorded for the next step: the earlier fixed-N evidence was produced by the *previous*
copy's code (same sources except the adaptive/cleanup fixes), so the fixed-N sweep is being re-run
against the current copy rather than being carried forward on a technicality.

_Ledger HEAD when written: `fcd9b0495`._

## CP-UQ203 — The retry case exists, and the sixteen-case sweep is re-running on the current copy

Two things are in flight, both recorded here so the next round does not have to rediscover them.

**1. The live retry case (correction item 4).** A `FULL_RESTART_RETRY` is only reachable through a
*genuine* valid failure, and this environment has passed every point in every campaign so far, so the
case runs against a task-owned points catalog with exactly one anchor moved out of the robot's reach:
`$TASK_ROOT/fault-injection/points-unreachable-anchor.yaml` (sha256 `560980891dfd…`, a copy of the
installed catalog with `cup_test_right_5cm` at `x = 0.60 m`), selected through the product's own
`SO101_VALIDATION_POINTS`. Nothing is faked — the sim really cannot perform that point, the failure
is a valid business failure, and it is fault injection for this workflow only, never counted as a
normal acceptance campaign. The new project `retry-full-restart` drives the console's real retry
panel (select the failed point, `CONFIRM FULL_RESTART RETRIES`, confirm) and then asserts the retry
is an **independent fresh batch**: its own `retry-001/batch_manifest.json` with
`batch_kind = FULL_RESTART_RETRY`, exactly one selected point and `worker_count = 1`, its own
coordinator journal and `cleanup-gates.json`, a batch id different from the first pass, and separate
`FIRST_PASS` / `FULL_RESTART_RETRY` rows in the store's `campaign_batches`. Committed `7f9804117`.

**2. The sixteen-case sweep is re-running against the current copy** (`lg-exec-sweep-current`,
`Running 18 tests`, job `bash-11`). The earlier fixed-N evidence came from the *previous* copy's code
— same sources except the adaptive/cleanup fixes, but not the deployed bytes — so it is being
reproduced rather than carried forward on a technicality. It must finish before the service is
restarted with the fault catalog for the retry case, because both need port 8010 and the same
service.

After those: the five consecutive valid physical batches at one N/commit/params/lifecycle, then the
final source/package/Web, install/served-byte, physics and visual gates.

_Ledger HEAD when written: `7f9804117`._

## CP-UQ204 — Receipt-consumer audit (correction item 5): nothing retired gates acceptance

The audit the correction asked for, read from the code rather than from memory:

**Mode admission is functional, and no budget/calibration receipt is consulted.**
`executor_registry.build()` computes availability from installed components and a live probe only:

```
fixed    = probes.fixed_upstream and probes.parallel_config
parallel = all((fixed, probes.broker_image, probes.resource_probe))
adaptive = all((runner, pool, wrapper, cleanup, config))
```

`resource_probe` is the shared start guard's real observation, not a stored qualification. The
retired budget aggregates and performance tiers appear **nowhere** in that expression, and
`production.py:300` states the same rule in code: "Fixed mode admits through the shared start guard;
no budget authority is consulted."

**The descriptive acceptance fields that survive gate nothing.** `ExecutorCapability` still carries
`two_worker_live_acceptance`, `adaptive_twenty_point_acceptance` and
`adaptive_performance_evidence`; the first two are unused, and the third only fills the *reported*
`performance_qualified_tiers`. Their env files are read through `_optional_file`, so a deployment
without them is unaffected. They are metadata, not requirements — I am leaving them in place rather
than churning the contract, and recording that decision here.

**The R01/R02/R03 receipts are functional and stay.** `02-parallel`, `04-start-guard` and
`05-functional-manifest` call `requireGateDetail(..., "R01", ...)`, which re-checks the *producing
run* (campaign id, status, cleanup, identity hashes) instead of trusting a filename; `R02` is the
same for the adaptive ladder. Those receipts are written by real campaigns (`recordGate` after a
terminal, cleaned-up batch) — exactly the "actual functional receipts" the correction wants in place
of retired ones — so nothing was removed, fabricated or deleted.

With the audit closed, the remaining work is: finish the sixteen-case sweep on the current copy, run
the fault-injected retry case, produce the five consecutive valid physical batches at one N, and the
final source/package/Web, install/served-byte, physics and visual gates.

_Ledger HEAD when written: `2db41f84b`._

## CP-UQ205 — Correction: CP-UQ198 overstated causality, which stays UNKNOWN

**CP-UQ198 claimed more than the evidence supports and this entry retracts that part of it.** It said
the 09:17 service death "is explained by the pane kill -- the service's lifetime was tied to the TUI
pane's session, so SIGKILL to the pane took it down", and called that "a harness/deployment defect of
mine". None of that is established.

What is actually recorded, and all that is:

- pane `%68` died from signal 9 at `2026-09-19 09:18:12 +08`, and its launcher PID 1345571 no longer
  exists;
- the validation service was not running when checked after the restart, and port 8010 was free;
- the exit-capturing wrapper written in CP-UQ197 left **no** `service-exit.log`, so no exit status,
  signal or timestamp for the service exists;
- the interrupted run shows `[cause] read ECONNRESET` on the N8 case and then
  `connect ECONNREFUSED 127.0.0.1:8010` for the sequential case, with the service log ending on
  ordinary `200 OK` lines and no traceback.

Those facts prove a **simultaneous boundary**: the pane and the service disappeared inside the same
window, and the run is diagnostic INVALID because its client lost the service. They do **not** prove
that the pane's SIGKILL caused the service's death. In particular nothing tested whether the service
was in the pane's session or cgroup at all -- it was started detached with `start_new_session=True`
-- so a shared-cause explanation (host-level event, resource kill, or an unrelated failure) is not
excluded. **Causality for the 09:17 death: UNKNOWN.** No harness defect is established by it.

The earlier **05:22 death also remains UNKNOWN**, exactly as CP-UQ196 recorded: it left no traceback,
`dmesg` is unreadable from this account, `sudo` is out of scope, and an OOM kill was and remains a
hypothesis.

This correction applies to CP-UQ198 and to any later entry that inherited its causal reading
(CP-UQ199's "closing part of the CP-UQ198 boundary" and the framing in CP-UQ200/CP-UQ203): the
operational measures that followed are **not** retracted and are **not** rolled back -- a service held
by `systemd --user` with `ExecMainStatus` capture is simply stronger evidence than a detached child
whose status nobody records, and that is why it was adopted. It was not adopted because the causal
claim had been demonstrated, and the claim itself is withdrawn here.

The current build and the running acceptance sweep are untouched by this entry: it changes the record,
not the workspace, the service or any campaign.

_Ledger HEAD when written: `85d9cd3ff`._

## CP-UQ206 — All sixteen FIRST_PASS cases executed for real on the deployed copy

The sweep finished clean: `18 passed (1.3h)`, the run's own `exit_code: 0`, and **zero failed cases**.
Sixteen real campaigns, one per manifest case, driven through the deployed console against the copy
that carries the adaptive and cleanup fixes (`copy-install-final.795JfhlK`):

| Case | Mode | Requested | Evaluated | N slots | Leases | Status | Cleanup |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `adaptive-ladder-p20` | ADAPTIVE | 20 | 20 | 0 | 0 | COMPLETED |
| `fixed-n2-p20` | PARALLEL | 20 | 20 | 2 | 20 | COMPLETED |
| `fixed-n2-p4` | PARALLEL | 4 | 4 | 2 | 4 | COMPLETED |
| `fixed-n3-p20` | PARALLEL | 20 | 20 | 3 | 20 | COMPLETED |
| `fixed-n3-p4` | PARALLEL | 4 | 4 | 3 | 4 | COMPLETED |
| `fixed-n4-p20` | PARALLEL | 20 | 20 | 4 | 20 | COMPLETED |
| `fixed-n4-p4` | PARALLEL | 4 | 4 | 4 | 4 | COMPLETED |
| `fixed-n5-p20` | PARALLEL | 20 | 20 | 5 | 20 | COMPLETED |
| `fixed-n5-p4` | PARALLEL | 4 | 4 | 5 | 4 | COMPLETED |
| `fixed-n6-p20` | PARALLEL | 20 | 20 | 6 | 20 | COMPLETED |
| `fixed-n6-p4` | PARALLEL | 4 | 4 | 6 | 4 | COMPLETED |
| `fixed-n7-p20` | PARALLEL | 20 | 20 | 7 | 20 | COMPLETED |
| `fixed-n7-p4` | PARALLEL | 4 | 4 | 7 | 4 | COMPLETED |
| `fixed-n8-p20` | PARALLEL | 20 | 20 | 8 | 20 | COMPLETED |
| `fixed-n8-p4` | PARALLEL | 4 | 4 | 8 | 4 | COMPLETED |
| `sequential-n1-p4` | SEQUENTIAL | 4 | 4 | 1 | 4 | COMPLETED |

Every row is a genuine campaign with `requested == evaluated`, the exact requested N slots present
(including N greater than the point count), leases summing to the point count (10×2, 7+7+6, 5×4,
3+3+3+3+3+3+2, …), terminal status and completed cleanup; the capability checks of `R05` are labelled
`capability only` and are not part of this table. The adaptive row reports zero workers because the
projection does not list pool workers — its evidence is the pool's per-worker attempt directories and
its `cleanup-receipt.json`, which the case verifies (CP-UQ202).

Consolidated record: `$TASK_ROOT/sweep-current-summary.txt`, derived from the runs' own
`execution-<case>.json` files by `$TASK_ROOT/tools/summarise-execution-evidence.py`.

Next: the fault-injected single-point retry case, then the five consecutive valid physical batches,
then `$TASK_ROOT/tools/final-gates.sh` (package/Web/OpenAPI/CTest, served bytes and the executed-nodeid
multiset) once no campaign is using the sim.

_Ledger HEAD when written: `91e03a9ae`._

## CP-UQ207 — The retry needs a genuine failure, and the product forbids injecting one by catalog

Correction item 4 asks for the single-point failure retry through the real `SEQUENTIAL` N1
`FULL_RESTART` workflow. The driver is ready (CP-UQ203) but it needs a **genuine valid failure**, and
this round established that the product deliberately makes one unavailable by configuration:

- I built a task-owned catalog with one anchor out of reach and started the service with it through the
  product's own `SO101_VALIDATION_POINTS` (verified inside the running process). Manifest generation
  then refused with **`409 VALIDATION_MANIFEST_CATALOG_MISMATCH`** — reproduced directly against the
  API. The reason is a real integrity property, not an accident: `load_baseline_catalog()` requires the
  installed catalog to hash to the frozen `CATALOG_SHA256` (`POINT_CATALOG_HASH_MISMATCH` otherwise),
  while `freeze_manifest_context` compares the identity's catalog hash with the selection's. A changed
  catalog is therefore rejected before any campaign exists.
- Nothing else in the product injects a valid failure: the control channel offers only `STATUS` and
  `CANCEL_BATCH`, and `SO101_VALIDATION_ADAPTIVE_FAULT_INJECTION` is a *capability flag* for the
  scripted suite (`executor_registry`), not a live fault injector.

So a live retry is *conditional on the sim genuinely failing a point*, which twenty-plus campaigns
have not done here. I am recording that as the outcome rather than manufacturing a failure: the
`retry-full-restart` project stays in place, fails loudly with the point statuses when no eligible
failure exists, and will run the moment one appears — including inside the five-batch stability
record. The workflow's own product behaviour is meanwhile covered by the plan's installed suite
(`contract/retry-and-lease.spec.ts`, C17: only a valid failure is retry-eligible, the retry is a
`FULL_RESTART` attempt with its own statistics) and by the code path this audit read:
`supervisor.start_retries` builds `FixedExecutionConfig("SEQUENTIAL", 1)` with
`batch_kind = FULL_RESTART_RETRY` under a fresh `retry-00N` batch root.

The service is being returned to the standard catalog now, and the next block is the five consecutive
valid physical batches at N1 / 20 points.

_Ledger HEAD when written: `52300e598`._

## CP-UQ208 — Web unit gate green (30 files, 126 tests), and the trap that made it look red

Ran the final gates' light portion while the stability batches use the sim. The first attempt
reported `15 failed | 15 passed` files and `77 failed | 49 passed` tests in 2.1 s — every failure the
same sentence: `act(...) is not supported in production builds of React`. That is the documented trap
this task's env already names: the ROS/colcon shell exports `NODE_ENV=production`, and vitest plus
`@testing-library/react` need React's development build. `$TASK_ROOT/tools/task-env.zsh` provides
`so101_web_test_env` for exactly this, and my first script forgot it.

Re-run with `so101_web_test_env`: **30 files passed, 126 tests passed**, `exit_code: 0`
(`browser/lg-final-web2.fOwqWU3j`). The red run is kept as evidence of the environment trap, not of a
product defect, and `tools/final-gates.sh` now sources the helper before the web gate so the mistake
cannot recur silently.

_Ledger HEAD when written: `242d16f66`._

## CP-UQ209 — Stability batch 1 FAILED at shutdown: OWNED_GROUP_SURVIVORS: worker

The first of the five consecutive twenty-point batches did **not** complete, and the series is
therefore at **0 valid batches**, recorded before any further attempt:

- the journal shows 19 `RESULT_COMMITTED` with `ATTEMPT_STARTED: 18`, `WORKER_RECOVERED: 18`,
  `WORKER_REGISTERED: 19`, `WORKER_QUARANTINED: 1`, then `BATCH_STOPPING`;
- the shutdown log escalates on the sim:
  `process[ros2_control_node-4] failed to terminate '5' seconds after receiving 'SIGINT',
  escalating to 'SIGTERM'` → `'10.0' seconds after receiving 'SIGTERM', escalating to 'SIGKILL'`;
- then the coordinator raises, from `supervisor.wait_for_children`:
  `so101_demo.runtime.parallel_processes.SupervisorError: OWNED_GROUP_SURVIVORS: worker`;
- the campaign never reaches a terminal, cleaned-up state: the projection stays `RUNNING` with
  `batch_cleanup_complete: false`, and its own worker manifest
  (`workers/worker-01/owned-runtime-processes.json`) is **empty** — so the survivor the supervisor
  refused to ignore was not a process this worker recorded owning;
- my broker container from that campaign was still up afterwards (logs kept, container removed), and
  the stalled Playwright case was stopped rather than left to time out.

Evidence kept under `$TASK_ROOT/stability-failure-batch1/` (`coordinator.log`, 33,029 lines, and the
broker's last 40 log lines). Nothing was deleted, and no foreign process was touched — the host also
runs an unrelated `codex` ACT-data task whose processes are visible in `ps` and were left alone.

This is a genuine product boundary, not a harness artefact: the plan's own supervisor refuses to
declare a batch stopped while a worker group survives, and refuses to call cleanup complete — which
is the correct fail-closed behaviour — but the shutdown path itself could not retire a worker group
after eighteen per-point worker recoveries. The next step is a **cheap reproduction**: a four-point
N1 sequential campaign (the shape the sweep already ran cleanly) and, if it reproduces, reading
`wait_for_children` together with the worker-recovery path in
`so101_demo/runtime/parallel_processes.py` and the coordinator's worker lifecycle, before any further
five-batch attempt. The service will be restarted on a fresh root so this campaign's stuck state
cannot contaminate the reproduction.

_Ledger HEAD when written: `144f5afeb`._

## CP-UQ210 — The failed stability batch left a container the daemon cannot kill, and the repro stalled in the browser

Two facts from the reproduction attempt, both recorded before any further run:

**1. A container of mine is stuck beyond `docker kill`.** `e2bb172bd754` (image `0b893cb1528e`, the
perception broker from the failed stability batch, created 12:05:56) has been `Up` for 44 minutes
while its init is idle in `do_wait`. Both `docker kill` and `docker rm -f` refuse with
`tried to kill container, but did not receive an exit event`, and the container remains listed. Its
logs are kept (`stability-failure-batch1/broker-e2bb172bd754.log`,
`broker-second-e2bb172bd754.log`), and I am **not** escalating: restarting the Docker daemon or using
`sudo` is out of scope, and no foreign object is touched. Note for context: an earlier orphan broker
from the 05:22 run stayed up for four hours while campaigns continued to pass, so this may not block
work — but it holds GPU memory and its persistence is itself a boundary worth naming.

**2. The four-point N1 reproduction never reached the service.** The run's own service log for that
root contains **zero** `POST`/`PUT`/`DELETE` requests — only the console's capability and campaign
polls — so the case stalled inside the browser before acquiring a lease, and my `acquireLease` waits
for a lease response until the test timeout, which is exactly the shape observed. The run was stopped
rather than left to time out. This is a harness/browser boundary, not a verdict about shutdown
survivors: it neither reproduced nor exonerated `OWNED_GROUP_SURVIVORS`.

**Next, in order.** (a) Re-run the four-point N1 case in a fresh run and confirm from the service log
that `POST /expert-validation/lease` and `POST /manifests` appear; if the browser stalls again, take
the failing page's screenshot/console from the Playwright trace instead of guessing. (b) Only then
chase the shutdown boundary itself: read `wait_for_children` beside the coordinator's worker-recovery
path, and try to reproduce with the smallest N1 campaign that triggers at least one
`WORKER_RECOVERED`. (c) Keep the five-batch stability record at **0 valid batches** until a batch
actually reaches a terminal, cleaned-up state.

_Ledger HEAD when written: `fbf7a3cd6`._

## CP-UQ211 — Owned-cleanup correction: my selection method was unsafe, and is retracted

Correction `9cbb34f7-0503-47a4-8764-2fc3905dc6af` (handoff sha256
`2c3888c24be168c8b53d2b47cc363328527dcac615cd68a2e01759ed3bb1639c`) is accepted in full. Its receipt
was written first, with `os.open(O_CREAT|O_EXCL|O_WRONLY)`: 37 bytes, UUID + LF, sha256
`b4ee5bc4f261e0e2f2866dbc7baa3e45b7383c883b207aa138b2133ed2af5592`, and `receipt-facts.json` records
shell time `2026-09-19 12:51:13 +0800`, HEAD `d15c3272e`, `dirty_entries: 0` and the goal unchanged
(`goal-e568087d-…`, active, 104/200, armed).

**What I did that the correction forbids.** Three of my cleanups selected targets by host-wide pattern
match rather than by proven ownership:

1. `pkill -INT -f "[r]os2_control_node"` — twice, while preparing service restarts (before the
   fault-catalog run and before the stability run).
2. `for P in $(pgrep -f "[r]os2_control_node"); do kill -TERM $P; done` — in the CP-UQ209 round, whose
   read-back file happened to show no matched PID at that instant and therefore proved nothing.
3. `docker ps | grep 0b893cb1528e` then `docker rm -f` — container removal by **image equality**,
   which the correction names as insufficient.

All three are retracted as methods. Nothing foreign was knowingly stopped, but "nothing bad happened"
is not the standard; the standard is proven ownership before a signal.

**Correction to CP-UQ209's cleanup facts.** Its "my broker container ... container removed" sentence
described removals chosen by image match. The ownership of the containers I did remove is now provable
from inspect files I had saved *before* removing them, and it is my own in every case:

| Container | `com.so101.batch-id` | Evidence-root bind | Campaign |
| --- | --- | --- | --- |
| `6d11f06ba026` | `b77d2` | `service-light.s2jytgW3/state/campaigns/campaign-ef973f12…` | the 09:17 N8 retry (CP-UQ198's invalid run) |
| `faab1d0ad1fe` | `beedb` | `service-light.s2jytgW3/state/campaigns/campaign-376d5580…` | the 05:22 N8 attempt (CP-UQ196) |
| `e2bb172bd754` | (captured now) | (captured now) | the failed stability batch (CP-UQ209) |

The broker launcher itself sets `--label com.so101.batch-id=<batch id>` and
`com.so101.broker-generation`, and binds the campaign's `runtime`/`inputs` directories, so **exact**
ownership is available by label plus evidence-root path — image equality was never necessary.

**The rule I will follow from here**, exactly as the correction states it: candidates come only from
the current batch/campaign's recorded owned-process manifest or the task-owned
supervisor/systemd/cgroup; before any signal I re-read and match PID plus `/proc/<pid>/stat` start
time, PGID/cgroup, campaign/session/domain and the evidence-root path, and all of them must identify
the current task-owned object. If ownership cannot be proven I record `OWNERSHIP_UNPROVEN` with the
candidate facts and keep diagnosing instead — never signal. Container removal requires the exact
container ID recorded by the current campaign plus inspected task labels and state/evidence linkage,
with inspect and log evidence preserved before removal.

Also carried forward: the stability requirement stays **at 0 of 5 valid batches** until five
independent terminal, cleaned batches complete; CP-UQ209's `OWNED_GROUP_SURVIVORS` boundary is a real
open failure and will not be softened or fabricated away.

_Ledger HEAD when written: `d15c3272e`._

## CP-UQ212 — Cleanup targets are now selected by proof, with a regression check that proves it

The correction's target-selection requirement is implemented in the task root, not asserted in prose:

- **`$TASK_ROOT/tools/owned_targets.py`** takes the batch's own recorded owned-process manifest and the
  campaign's evidence root, and selects a candidate only after re-reading `/proc/<pid>/stat` and
  matching the recorded **start time** and **PGID**, plus finding the campaign's evidence root in the
  process's environment (`SO101_VALIDATION_EVIDENCE_ROOT` / `SO101_TASK_ROOT`) or command line. Every
  other outcome is reported as `OWNERSHIP_UNPROVEN` with a reason — `MANIFEST_EVIDENCE_ROOT_MISMATCH`,
  `PID_INVALID`, `PID_GONE`, `PID_ZOMBIE`, `STARTTIME_MISMATCH`, `PGID_MISMATCH`,
  `EVIDENCE_ROOT_NOT_IN_PROCESS` — and left alone. `--dry-run` prints the selection; only an explicit
  `--signal` acts, and only on verified targets.
- **`$TASK_ROOT/tools/test_owned_targets.py`** is the hermetic regression check the correction asked
  for. It starts two `/usr/bin/sleep` children with the *same executable and arguments* as the owned
  child: one with a foreign environment and no manifest entry, one with the same evidence root but a
  falsified recorded start time. Result: `verified: [3186002]` (only the exact-owned child),
  `unproven: 3186003 -> EVIDENCE_ROOT_NOT_IN_PROCESS, 3186004 -> STARTTIME_MISMATCH`, the foreign
  sentinel still alive, and `OWNED_TARGETS_REGRESSION_OK`. Nothing real is started and no foreign
  service is involved.

Container cleanup now follows the same standard. The stuck broker `e2bb172bd754` has its ownership
**proven** — label `com.so101.batch-id = bef23`, generation 1, and binds to
`service-light.2l3JdNrA/state/campaigns/campaign-4ee7d85f.../bef23/broker-inputs`, i.e. exactly the
failed stability batch — and its `docker inspect` document is preserved next to its logs. Removal is
blocked by the daemon itself (`tried to kill container, but did not receive an exit event`), so it
stays, with evidence intact and no escalation.

Unchanged and not softened: the five-batch stability requirement remains **0 of 5** until five
independent terminal, cleaned batches complete, and CP-UQ209's `OWNED_GROUP_SURVIVORS` failure stays
open.

_Ledger HEAD when written: `e2202cc45`._

## CP-UQ213 — The N1 diagnostic stalls in the browser, and the host shows a GPU-shaped blockage

The four-point N1 reproduction was re-run against a fresh service root, exactly as the owned-cleanup
correction prescribed, and it stalled the same way: after minutes, that root's service log contains
**zero** `POST`/`PUT`/`DELETE` requests and no campaign exists, so the case never reaches its first
state-changing call. Reading the page instead of guessing says the console itself is healthy — a
direct browser probe against the same service shows the heading rendered,
`Acquire lease` **enabled**, `Generate points` enabled, the two gated buttons disabled, and only a
favicon 404 in the console. So the stall is not a UI defect and not a service defect.

What the host shows at the same moment (read-only; **no signals sent**):

- 22 Chrome processes, including a `--type=gpu-process` that has been in uninterruptible sleep
  (`D`) for ~15 minutes and a utility process in `D` for ~12 minutes, both orphaned to PID 1;
- load average **9.72** (1 min) on a 31 GiB host with 23 GiB available;
- my broker container `e2bb172bd754` — ownership proven earlier: label `com.so101.batch-id = bef23`
  and binds to the failed stability campaign — still `Up 51 minutes`, and the daemon still refuses to
  kill or remove it.

**Hypothesis, explicitly not a finding:** the browser cases cannot start because the GPU is held by
that container and orphaned Chrome GPU processes are stuck on it. I have not proven the causal chain,
and per the correction I am not going to signal anything selected by process name, command substring,
image, port or age: the stuck Chrome processes carry no recorded owned-process manifest, so their
ownership is `OWNERSHIP_UNPROVEN` and they stay untouched; the container's ownership *is* proven but
the daemon itself blocks removal, and restarting Docker or using `sudo` is out of scope.

The stalled run was stopped through its own job handle (exact-owned), not by signalling a match. The
five-batch stability requirement remains **0 of 5**, CP-UQ209's `OWNED_GROUP_SURVIVORS` boundary stays
open, and the next diagnostic step is to establish whether the blockage clears on its own before
re-attempting any browser-driven acceptance — reading the D-state processes' `/proc/<pid>/stack` (if
readable) or waiting for the container's I/O to complete, rather than forcing cleanup.

_Ledger HEAD when written: b2c636009._

## CP-UQ214 — A fresh browser renders the console fine, which weakens the GPU-contention hypothesis

Recorded because it narrows the stall rather than confirming the previous guess:

- a fresh browser probe against the same service, run *after* the stalled case was stopped, loads
  `/expert-validation` and finds the heading plus an **enabled** `Acquire lease` button — i.e. a new
  Chrome instance can start and render even while the host is loaded (load ~10) and the stuck broker
  container is still up;
- at the same time the process table shows **several** Chrome `--type=gpu-process` and utility
  processes in uninterruptible sleep (`D`), ages ~15 m, ~5.5 m and ~2.5 m, one per browser attempt I
  have made, all orphaned; `gnome-shell` has been in `D` for 18 days and is unrelated;
- no acceptance process, simulator or coordinator is running, and my container `e2bb172bd754` is
  still `Up`.

So "the GPU is held, therefore browsers cannot start" is **not supported**: browsers do start. What
remains open is why the *spec's* browser instance never issues its first request while a manual probe
against the same page succeeds. The next diagnostic is therefore click-level and still read-only for
the service: drive the fixture's own launch options (the acceptance suite uses
`executablePath: chromeExecutablePath()`, not Playwright's bundled shell) and perform the
`Acquire lease` click while watching for `POST /expert-validation/lease`; if the click posts, the stall
is in the fixture/runner, and if it does not, the difference is in the launch options and I will
bisect them one at a time.

Nothing was signalled: the stuck Chrome processes have no recorded owned-process manifest, so they stay
as `OWNERSHIP_UNPROVEN`; the stalled run was again stopped through its own job handle.

_Ledger HEAD when written: 2a34bbafa._

## CP-UQ215 — The stall is Playwright's input pipeline, not the console or the CPU

Three probes isolate it, and none of them needed guessing:

1. **The button is fine.** Sampling its box six times over 2.4 s against the deployed service gives an
   identical `[41, 365, 112, 36]`, `documentHeight` 720, `animations: 0`, `disabled: false`.
2. **Playwright cannot act on it.** With the acceptance suite's own Chrome
   (`executablePath: /usr/bin/google-chrome`), `locator.click()` fails after 20 s with
   `waiting for element to be visible, enabled and stable` while the locator resolves to exactly that
   button — the same gate that leaves the acceptance cases hanging until their 30-minute timeout and
   explains the zero state-changing requests.
3. **The console's handler works.** A DOM-level click (`button.click()` inside the page) produces
   `POST /expert-validation/lease` → `200 OK` and disables the button. So the UI and the service are
   both healthy; only the *input dispatch* path fails.

Host measurements rule out the obvious cause: **CPU busy is 13.8 %** with 1.3 % iowait over a 2 s
window, so this is not CPU starvation — but there are **10 tasks in `D` state**, all of them the
orphaned Chrome `--type=gpu-process`/utility processes from my stopped browser attempts, plus my
broker container `e2bb172bd754` which the daemon still refuses to kill. The consistent reading is that
the renderer cannot complete input dispatch while a GPU operation is blocked; script execution
(`element.click()`) bypasses that pipeline and succeeds.

Consequences recorded rather than worked around:

- browser-driven acceptance is **blocked by the host**, not by the product, and I will not force it
  with `force: true`/`dispatchEvent` in the acceptance drivers — that would skip the very
  actionability contract the console is supposed to satisfy;
- the blocking objects cannot be cleared within the rules: the container's ownership is proven but the
  daemon blocks removal, and the Chrome processes have no recorded owned-process manifest, so they are
  `OWNERSHIP_UNPROVEN` and stay — they are also in uninterruptible sleep, so no signal would take
  effect anyway;
- the five-batch stability record stays **0 of 5** and CP-UQ209's `OWNED_GROUP_SURVIVORS` boundary
  stays open.

Next, the non-browser gates proceed because they do not depend on the browser at all: the demo and
teleop package suites through the audited runner, CTest through the colcon harness, the OpenAPI schema
freshness check, and the served-vs-installed byte comparison.

_Ledger HEAD when written: 336063206._

## CP-UQ216 — My browser probes feed the blockage, and the API chain is the way through it

Two things, both learned the hard way this round:

**1. Each browser probe adds another stuck process.** D-state tasks went 10 → 11 and Chrome processes
22 → 25 across the probes, and load rose to 14.18, while the click gate failed identically. The
diagnostic was recreating the very condition it was measuring, so **the browser probes stop here** —
further probing would be self-amplifying rather than informative. The finding from CP-UQ215 stands as
the last measurement: element stable, renderer not dispatching input, CPU idle.

**2. The acceptance does not have to go through the browser.** Correction `58936fb6` asks for every
configured option's campaigns "through the real deployed default UI/API chain". The console is only a
client of that API, and the API carries the same contracts the product enforces — lease/session
binding, manifest integrity, preflight, campaign start, worker/N slot accounting, cleanup — so the
five consecutive valid physical batches can be driven through **the deployed API** while the browser
input path is blocked by the host. That is not a weakened gate: it is the other half of the chain the
correction names, and it exercises the same server-side authority. The UI-driven sweep (CP-UQ206)
already stands as the UI half of the evidence for all sixteen cases.

So the ordering from here is: finish the non-browser gates already running (demo suite now; then
teleop, CTest, OpenAPI freshness, served bytes), and write a task-owned API driver for the
five-batch stability record that performs exactly the HTTP chain the console performs — with the same
lease, confirmation and cleanup discipline, and no browser involved.

Nothing is retracted about the browser: the UI stalls remain a host-side blockage on the record, the
stability requirement stays **0 of 5** until five genuine terminal, cleaned batches complete, and
CP-UQ209's `OWNED_GROUP_SURVIVORS` boundary stays open.

_Ledger HEAD when written: 77afb1c7c._

## CP-UQ217 — The host is degraded: pytest now blocks in D state too

The demo package gate did not fail on an assertion; it **stopped making progress in the kernel**. Its
serial phase was correctly targeted — `serial.argv.txt` names exactly the audited conflict modules
(`test_parallel_batch_resources.py`, `test_parallel_start_guard_launch.py`,
`test_text_pick_agent_e2e_process.py`, `test_parallel_adaptive_integration.py`,
`test_parallel_batch_worker.py`, `test_inject_so101_parallel_fault.py`), with one declared skip
(`test_adaptive_helper_handshake_and_sigint_cleanup`) — so the target list I flagged for checking is
fine. What is not fine is the process state:

- `venv/bin/python -m pytest …` has been in **`D`** (uninterruptible) with
  `wchan = os_acquire_rwlock_write` for over a minute, after writing only `F.` (one failure, one pass)
  to `serial.log`; no junit, no `rc`;
- the host shows **11 `D`-state tasks** and load **14.2**; CPU is otherwise idle (13.8 % busy measured
  earlier), so this is an I/O/lock pathology, not compute saturation;
- my broker container `e2bb172bd754` is still `Up` at 56 minutes and the daemon still refuses to kill
  it, and the orphaned Chrome GPU processes from the blocked browser runs are still stuck.

So the degradation that first showed as "the browser cannot dispatch input" now also blocks the package
suite's I/O. The run was stopped through its own job handle — exact-owned, no pattern-matched signal —
rather than left to accumulate load.

**What this does and does not block.** Blocked: anything that needs the host to complete real I/O or
input under load — the five-batch stability record, the package/CTest gates, and the browser-driven
acceptance. Not blocked: ledger work, the API driver for the stability record (writing it), and
read-only evidence work.

I am recording this as the concrete blocking condition, with three consecutive rounds of the same
observation (105: browser stall, 106: input-dispatch isolation, 107–108: probes and pytest blocked by
the same `D`-state condition). If it persists, the goal belongs in `blocked` with this reason rather
than in a sequence of re-attempts; if it clears, the API route (CP-UQ216) is ready to carry the
stability record without the browser.

_Ledger HEAD when written: f30f2e42f._

## CP-UQ220 — macOS W2 takeover from the last committed ai-station checkpoint

`checkpoint_id: CP-UQ220`
`source_checkpoint: CP-UQ217`
`host: Terry-Mac-mini.local`
`branch: codex/so101-unbounded-queue-resource-budget`
`source_head: 9d0679325bd685a144690909b1c764509a984019`
`source_upstream: origin/codex/so101-unbounded-queue-resource-budget @ 9d0679325bd685a144690909b1c764509a984019`
`submodule third_party/mujoco_ros2_control: e4c0241`
`evidence_root: /tmp/so101-debug-unbounded-queue-w2-mac-mini-3eed4ddd-a50c-4c21-b78f-60be2216ef9d`
`status: RUNNING`
`last_valid_experiment: NONE (takeover checkpoint; no macOS experiment has run yet)`
`next_experiment: EXP-UQ220-MAC-INVENTORY`

The macOS continuation starts from the last committed checkpoint, CP-UQ217. Two later checkpoint
drafts, CP-UQ218 and CP-UQ219, existed only as uncommitted ai-station workspace state and were never
pushed; they are migration context, not repository history. Their admissible facts are carried here
without claiming them as committed checkpoints: a fresh final gate again entered host-level
uninterruptible I/O; the exact-owned pytest was stopped by its owned PGID and its task-side D-state
returned to zero; the partial run collected 65 cases with one failure but never reached its parallel
phase or terminal evidence, so it is not a valid RED, GREEN, or package gate; and the exact task-owned
Docker container remained unremovable. The ai-station executor is frozen and unavailable. This
continuation will not contact it, clean it up, or infer current host state from those old observations.

The takeover contract is deliberately narrow: **W2 means exactly `worker_count = 2`**. It covers only
functional correctness on this Mac — exact two-slot admission, progress/results/evidence, terminal
cleanup ownership, cancellation/recovery, and independent physical evidence. It does not restore or
claim W4/W6/W8 qualification, an N1–N8 budget, provider promotion, swap/PSI criteria, source-commit
admission, ament-prefix admission, or any extrapolation beyond W2. Historical current-copy evidence
that all sixteen FIRST_PASS cases ran green on ai-station remains context, including the two W2 cases;
it is not macOS proof. The five-batch stability record also remains **0 of 5** until this continuation
produces valid W2 evidence. No real hardware is authorized.

Before this entry, the worktree, index, and untracked set were clean. The dispatch receipt was created
atomically with `O_CREAT|O_EXCL` before any other task action and read back as exactly the dispatch UUID
plus LF (37 bytes, sha256
`51e4448b1019044f8c78c0b89f0f996ae971e036b268df413b70aafdf9b23e51`). The handoff and all four
approved artifacts were read completely, and their approved sha256 values matched. No runtime
inventory, service start, test, GUI action, signal, container action, or cleanup has occurred on the
Mac yet. `ROS_DOMAIN_ID`, `GZ_PARTITION`, the exact ROS Python, and the install overlay are therefore
explicitly **UNVERIFIED_PENDING_INVENTORY**, rather than inherited from the other host.

The first exact next command is a read-only ownership and environment inventory whose output is
retained under the registered evidence root:

```zsh
evidence_root=/tmp/so101-debug-unbounded-queue-w2-mac-mini-3eed4ddd-a50c-4c21-b78f-60be2216ef9d
{
  date '+%Y-%m-%dT%H:%M:%S%z'
  hostname
  pwd
  printenv ROS_DOMAIN_ID GZ_PARTITION DYLD_LIBRARY_PATH PYTHONPATH
  command -v ros2 python3 colcon tmux docker lsof
  tmux list-sessions
  ps -axo pid,ppid,pgid,state,lstart,command
  lsof -nP -iTCP:8010 -sTCP:LISTEN
  docker ps --no-trunc
} > "$evidence_root/mac-takeover-inventory.txt" 2>&1
inventory_rc=$?
print -r -- "inventory_rc=$inventory_rc"
```

The inventory is observational only. Any later stop or cleanup target must be derived from a
task-owned manifest or supervisor and revalidated by exact identity; process-name, command-substring,
port, image, or age matches alone never authorize a signal or removal.

_Ledger HEAD when written: `9d0679325` (this checkpoint is the first intentional worktree edit)._

## CP-UQ221 — macOS inventory is valid; no inherited runtime is admitted

`EXP-UQ220-MAC-INVENTORY: VALID`

The sandboxed inventory returned `inventory_rc=1` because macOS denied `ps` and the tmux socket. Per
the repository rule, that denial was not treated as absence: the same read-only checks were repeated
with host access and returned `host_inventory_rc=0`. The retained records are
`mac-takeover-inventory.txt` and `mac-takeover-host-inventory.txt` in the registered evidence root.

- The only task-related tmux/process tree is this same resumed Codex session,
  `codex-unbounded-queue-w2-mac-mini`; no second executor was created.
- `lsof -nP -iTCP:8010 -sTCP:LISTEN` returned 1 with no rows, so no service owns the task port.
- Docker's selected context is `desktop-linux`, but the user socket does not exist and read-only
  `docker ps --no-trunc` returns 1. No container state is inferred beyond the daemon being
  unavailable through that context, and no Docker mutation has occurred.
- `ROS_DOMAIN_ID` and `GZ_PARTITION` were unset. The exact ROS Python exists at
  `/Users/matianyi/ros2_jazzy/.venv/bin/python3`; it imports `rclpy` from the Jazzy install.
- The existing repository overlay is the canonical checkout's install, not this worktree:
  `so101_demo` resolves to
  `/Users/matianyi/Projects/robot_demo_001/moveit-demo/build/so101_demo_py/so101_demo/__init__.py`
  and `so101_teleop` resolves to the corresponding canonical install. It is acceptable only as an
  underlay. It cannot prove this branch and will not be presented as branch acceptance.

`EXP-UQ221-W2-SOURCE-GATE: PLANNED`. The next step is a source-prepended, exact-Python diagnostic
gate over the W2 contract, allocator/start guard, coordinator/CLI, preflight, registry, and supervisor
tests. It uses unique `ROS_DOMAIN_ID=203`, `GZ_PARTITION=so101_uq_w2_mac_3eed4ddd`, a fresh task-local
temp tree, a nonzero collection, a JUnit document, and explicit import/executable provenance. This is
a source diagnostic, not an installed package gate and not physical W2 evidence. Any assertion
failure is recorded before a patch; an environment/bootstrap failure is classified separately.

_Ledger source HEAD: `9d0679325`; intentional dirty path remains this ledger only._

## CP-UQ222 — First source gate is INVALID at collection, not RED

`EXP-UQ221-W2-SOURCE-GATE: INVALID`

The exact Python and isolation preflight passed, but collection returned 4 with no tests collected and
no JUnit. This is a bootstrap/configuration failure, not a source assertion failure:

1. `so101_demo_py/setup.py` maps the installed package name `so101_demo` directly onto the source
   directory named `src`. Prepending `src/so101_demo_py/src` therefore does not create an importable
   `so101_demo` package; the provenance probe visibly resolved `so101_demo` to the stale canonical
   build, and collection could not find branch modules such as `runtime.debug_provenance`.
2. The single invocation crossed the demo and teleop package roots. The demo's `[tool:pytest]`
   `testpaths = test` root then mis-resolved the teleop arguments and the ROS launch-testing hook
   attempted unrelated collection. No selected W2 test boundary ran.

The complete invalid attempt is retained at `unit-w2-source-01/`. The correction uses a task-local
`so101_demo` symlink package pointing at this worktree's `src/so101_demo_py/src`, verifies its resolved
origin, and runs demo and teleop collection/execution as two independent exact-Python invocations from
their own package roots. No product file changes are justified by this bootstrap result.

`EXP-UQ222-W2-SOURCE-GATE-RETRY: PLANNED` with the same tests, domain, partition, and evidence
requirements, under fresh root `unit-w2-source-02`.

_Ledger source HEAD: `9d0679325`; intentional dirty path remains this ledger only._

## CP-UQ223 — Second source gate is INVALID; origin fixed, pytest root incomplete

`EXP-UQ222-W2-SOURCE-GATE-RETRY: INVALID`

The task-local package shim worked: the provenance record resolves `so101_demo`, `so101_teleop`, and
`rclpy` to the intended worktree/Jazzy sources, and the task-local temp directory is effective. The
demo collection still returned 4 before collecting a selected test because running from the package
directory removed the repository root from `sys.path`. The ROS launch-testing collection hook imports
ordinary test modules while inspecting the `test` directory; `test_pytest_full_gate_runner.py` then
correctly required `tools.so101_pytest_gate`, which was not importable without the repository root.
All six selected paths consequently reported no collectors. This is again bootstrap INVALID, not RED,
and the complete evidence is retained under `unit-w2-source-02/`.

The working comparison is the repository's own ordinary gate: it runs with the repository root
importable while selecting package configuration explicitly. The next and final bootstrap correction
keeps the verified package shim, prepends the repository root, runs from the repository root, and uses
`-c src/so101_demo_py/setup.cfg` and `-c src/so101_teleop/pytest.ini` in separate invocations. A third
bootstrap failure will stop this source-shim path in favor of the fresh installed overlay rather than
accumulating more retries.

`EXP-UQ223-W2-SOURCE-GATE-RETRY-2: PLANNED` under fresh root `unit-w2-source-03`.

_Ledger source HEAD: `9d0679325`; intentional dirty path remains this ledger only._

## CP-UQ224 — Valid macOS RED: the start guard unconditionally called a Linux-only API

`EXP-UQ223-W2-SOURCE-GATE-RETRY-2: VALID RED`

The corrected runner collected 454 selected demo cases and 41 selected teleop cases with exact
worktree/Jazzy origins. The demo execution reached assertions and finished `107 failed, 347 passed`
with a readable 454-case JUnit; teleop execution did not start because the demo phase was nonzero.
This is the first valid macOS RED. Its dominant root is precise: 95 assertion traces contain
`AttributeError: module 'os' has no attribute 'sched_getaffinity'`, raised by
`start_guard.host_ports()`. The downstream `START_GUARD_REFUSED` results are consequences, not
independent defects. Smaller Linux-only clusters (`/proc`, `/run/user/<uid>`, `/proc/self/fd`) remain
separately visible and are not hidden by this fix.

TDD cycle 1 names the broken behavior: a non-Linux host with a real logical CPU count must expose a
nonempty affinity set instead of crashing before the guard can make a decision. The new regression
test was first run alone and failed exactly at the unconditional `os.sched_getaffinity(0)` call
(`tdd-cpu-affinity-red/`, 1 failed). The minimal implementation uses `sched_getaffinity` when present
and otherwise returns `range(os.cpu_count())`; the same test then passed (`tdd-cpu-affinity-green/`,
1 passed). This preserves Linux affinity/cgroup semantics and adds no budget or admission bypass.

`EXP-UQ224-W2-SOURCE-GATE-AFTER-AFFINITY: PLANNED`. Re-run the exact selected demo set under a fresh
root to measure the next independent failure boundary before any further patch.

_Ledger source HEAD: `9d0679325`; intentional source changes are the ledger, the guard fallback, and
its regression test._

## CP-UQ225 — The Mac guard boundary is green; remaining full-suite failures are separate Linux assumptions

`EXP-UQ224-W2-SOURCE-GATE-AFTER-AFFINITY: VALID RED` finished `106 failed, 349 passed`.
The dominant next failure was no longer CPU affinity: it was the unconditional read of
`/proc/self/cgroup`. Independent RED → GREEN cycles then established the smallest portable guard
behavior without weakening Linux checks:

- `tdd-cgroup-root-red/` → `tdd-cgroup-root-green/`: an unavailable or undecodable cgroup-membership
  file means the unconstrained host root `/`; a present Linux cgroup file retains its prior parsing.
- `tdd-macos-meminfo-red/` → `tdd-macos-meminfo-green/` and the corrected
  `tdd-macos-sysconf-red2/` → `tdd-macos-sysconf-green/`: on Darwin, total RAM comes from
  `sysconf(SC_PAGE_SIZE) * sysconf(SC_PHYS_PAGES)` (with `/usr/sbin/sysctl` only as a fallback), and
  available RAM comes from `/usr/bin/vm_stat`; malformed or unavailable probes still fail closed.
- `tdd-process-identity-red/` → `tdd-process-identity-green/`: when `/proc/<pid>/stat` is absent,
  `psutil.Process(pid).create_time()` supplies the stable opaque birth identity; missing, changed, or
  unreadable processes still return no identity.

The exact guard-focused Mac gate `start-guard-macos-03/` is GREEN: **61 passed, 0 failed**, with a
readable JUnit result. Its real-host Darwin assertion deliberately expects
`GPU_TARGET_UNAVAILABLE`: the approved production design requires NVML GPU identity, and this Mac
does not provide it. Test-only complete GPU fixtures exercise the W2 allocator/CLI logic without
claiming a production GPU admission.

Two allocator portability cycles were also measured, not inferred. The full selected source gate
moved from `76 failed, 383 passed` (`unit-w2-source-05/`) to `73 failed, 387 passed`
(`unit-w2-source-06/`) after a RED → GREEN fix that accepts only the root-owned `/tmp` symlink whose
exact target is root-owned sticky `/private/tmp`. A further RED → GREEN cycle gives Darwin domain
claims the same stable process-birth identity used by the guard; the next full source gate reached
`72 failed, 389 passed` (`unit-w2-source-07/`). Linux behavior remains unchanged in both cases.

The remaining failures are not evidence that the approved start guard is red. Sixty traces are the
same absent `/proc/self/fd` Unix-socket transport, with downstream `UNIX_TRANSPORT_UNAVAILABLE`
allocation failures; smaller clusters assume `/run/user/<uid>` or other Linux `/proc` process
metadata. Those boundaries are retained rather than masked by platform skips.

_Ledger source HEAD: `9d0679325`; all named RED/GREEN and source-gate directories are retained under
the registered Mac evidence root._

## CP-UQ226 — `/dev/fd` cannot preserve the Linux dirfd Unix-socket transport on Darwin

`EXP-UQ226-DARWIN-DIRFD-PROBE: VALID NEGATIVE`

The task-owned probe `ipc-macos-probe-01/probe.log` opened a mode-0700 runtime directory, retained its
directory descriptor, and attempted the Darwin-looking address `/dev/fd/3/control.sock`. `/dev/fd`
is present and reports as a directory, but `socket.bind()` returned `ENOENT`; no socket was created.
The installed macOS SDK exposes neither `bindat` nor `connectat`. Therefore `/dev/fd/<dirfd>/<name>`
is not a functional or security-equivalent replacement for Linux `/proc/self/fd/<dirfd>/<name>`.

No production IPC fallback is introduced. Returning a long canonical path would violate Darwin's
`sun_path` limit, and a short symlink alias would weaken the pinned-parent identity guarantee. The
Unix transport remains fail closed on this host. This blocks a real two-Worker production launch on
the Mac independently of the already-recorded NVML admission boundary; it does not invalidate the
61-case guard gate or authorize changing the approved GPU/IPC contracts.

The next gate is the complete affected guard test set plus read-only formatting/static checks. If it
is green, the Mac result can establish portable lightweight-guard correctness while reporting full
physical W2 acceptance as unsupported by this host, not as PASS.

_Ledger source HEAD: `9d0679325`; no socket, process, or evidence cleanup was performed._

## CP-UQ227 — Schema-v3 again has exactly one admission probe

`EXP-UQ227-AFFECTED-GUARD-GATE: VALID GREEN`

The valid `guard-affected-final-02/` RED reached 76 tests and finished `4 failed, 72 passed`.
It separated three boundaries:

1. Darwin correctly refuses and re-probes an unavailable GPU rather than caching that refusal as an
   epoch admission.
2. `WorkerResourceAllocator.allocate()` and `adopt_existing()` still called the retired
   `SystemResourceProbe.snapshot()` before their schema-v3 lightweight guard. On this Mac that first
   failed at `/proc/meminfo`; on Linux it duplicated CPU/RAM/GPU observation and contradicted the
   approved one-guard design.
3. launch-test subprocesses did not place `ROS_HOME`/`ROS_LOG_DIR` under the task root and therefore
   tried to write `$HOME/.ros` through the sandbox.

The minimal production correction calls `_probe_snapshot()` only in the legacy non-v3 branches.
Schema-v3 allocation and restore now use only `_start_guard_check()`. The resource regression replaces
the old permissive `SystemResourceProbe.snapshot` stub with a forbidden call, proving that a v3 dry
run does not touch it. No v1/v2 formula, threshold, or legacy restore behavior changed. Test harnesses
now keep ROS logs under their task root and model a complete GPU only inside offline Darwin fixtures;
production continues to refuse this host with exact `GPU_TARGET_UNAVAILABLE`.

The four failed nodeids first passed together in `guard-targeted-green-01/` (`4 passed`). After a
manual cross-platform review, `tdd-nondarwin-meminfo-red3/` proved that an absent proc meminfo file on
a non-Darwin platform incorrectly invoked Darwin commands; `tdd-nondarwin-meminfo-green/` proves the
fallback is now Darwin-only and all other platforms retain the former unavailable result.

Final current-source results after that last production edit:

- `branch-build-01/`: fresh `so101_demo_py` symlink install, exit 0, one package built;
- `guard-affected-final-04/`: **77 passed, 0 failed, 0 errors**, JUnit read back;
- `teleop-guard-final-03/`: **7 passed, 0 failed, 0 errors**, JUnit read back;
- `resource-portability-final-02/`: **3 passed, 0 failed, 0 errors**, including the v3 forbidden
  legacy-probe assertion;
- `final-readback-01/`: all ten changed Python files compile from source bytes and
  `git diff --check` exits 0.

The attempted package-runner record `colcon-guard-package-final-01/` is **INVALID**, not RED: the
correct ROS venv ran pytest but `colcon` removed the macOS dylib search environment, so import of
`rclpy` failed before collection with
`Library not loaded: @rpath/librosidl_typesupport_c.dylib` (zero runnable nodeids, exit 4). This is
the exact bootstrap boundary named by the repository's macOS package-test contract. In the same
current zsh environment, direct `rclpy` import succeeds from the Jazzy tree and the package-boundary
tests above collect and pass. Those targeted direct gates do not masquerade as a complete all-tests
package gate.

The broad `ament_flake8` diagnostic in `static-checks-01/` is also non-gating: it reports 2,764
violations across already-nonconforming complete files (including 2,518 quote-style findings), not a
change-specific baseline. The source-byte compilation and diff whitespace checks are the valid static
readbacks for this continuation.

_Ledger source HEAD: `9d0679325`; the worktree is intentionally dirty pending the terminal commit._

## CP-UQ228 — Mac terminal result: guard portable, production W2 physical acceptance unsupported

`checkpoint_id: CP-UQ228`
`host: Terry-Mac-mini.local`
`scope: exact worker_count=2 only`
`status: PARTIAL_PASS / PHYSICAL_W2_BLOCKED`
`five_batch_stability: 0/5`

The lightweight start guard and its demo/teleop consumers are portable and green at the supported
Mac test boundary. A real production W2 campaign is not supportable on this host without changing
approved contracts:

- the guard's required NVML device enumeration fails closed as `GPU_TARGET_UNAVAILABLE`; Apple GPU
  capacity is not substituted or guessed;
- the authenticated Unix transport requires the Linux pinned-parent address
  `/proc/self/fd/<dirfd>/<name>`; the retained Darwin probe proves `/dev/fd/<dirfd>/<name>` returns
  `ENOENT`, and the SDK offers no `bindat`/`connectat` equivalent. No long-path or symlink-alias
  weakening was added.

These two boundaries occur before a genuine two-Worker simulation can establish exact slot identity,
progress/results, cancellation/recovery, cleanup, or independent physical evidence. Therefore no
Gazebo/MuJoCo stack or GUI was started, no screenshot was manufactured, no physical W2 batch is
claimed, and the stability count remains 0/5. Historical ai-station FIRST_PASS evidence remains
historical context only.

The final host inventory is retained as `final-host-inventory.txt`. It shows no surviving pytest,
colcon, start-guard helper, SO-101 parallel process, or listener on TCP 8010; the only task-related
session is this same `codex-unbounded-queue-w2-mac-mini` continuation. The inventory command exits 1
only because `lsof` correctly found no listener.

Evidence disposition (nothing deleted):

- **retained final evidence:** `guard-affected-final-04/`, `teleop-guard-final-03/`,
  `resource-portability-final-02/`, `branch-build-01/`, `final-readback-01/`,
  `final-host-inventory.txt`, the receipt, approved package, inventory/provenance records, every valid
  RED→GREEN pair, and every full source-gate result;
- **archived runs:** none — this Mac evidence root has no archive move;
- **deletion candidates only:** invalid bootstrap attempts (`unit-w2-source-01/`,
  `unit-w2-source-02/`, `guard-affected-final-01/`, `colcon-guard-package-final-01/`,
  `tdd-macos-sysconf-red/`, `tdd-nondarwin-meminfo-red/`, `tdd-nondarwin-meminfo-red2/`), superseded
  intermediate gates (`unit-w2-source-03/` through `unit-w2-source-07/`,
  `start-guard-macos-01/`, `guard-affected-final-02/`, `guard-affected-final-03/`,
  `teleop-guard-final-01/`, `teleop-guard-final-02/`, `resource-portability-final-01/`), and their
  task-local temp/build byproducts. They remain auditable in place because deletion was not
  authorized.

No W4/W6/W8 run or claim occurred. No ai-station operation, real hardware action, global
configuration change, foreign cleanup, evidence deletion, or main-branch publication occurred.

_Ledger source HEAD before terminal commit: `9d0679325`._

## CP-UQ229 — macOS MPS/private-IPC dispatch is taken over; the v3 baseline is frozen

```yaml
checkpoint_id: CP-UQ229
kind: IMPLEMENTATION_START
last_valid_experiment: EXP-UQ229-TASK0-BASELINE
current_hypothesis: The approved schema-v4 design closes exactly the two boundaries that CP-UQ228
  recorded as blocking (NVML-only admission and the Linux dirfd IPC address), so a real macOS MPS
  W2 campaign becomes supportable without weakening any frozen contract.
working_tree_status: clean at takeover, then this ledger checkpoint and the task-root run records
owned_processes: NONE - no task-owned runtime stack, socket, or test process is running
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  and SkyComputerUseService; they are not task-owned and must not be signalled
open_risks:
  - The 3 pre-existing Darwin /proc/self/fd transport failures must go GREEN through the frozen v3
    path plus the new v4 path, never by deleting or skipping the Linux assertions.
  - macOS package/CTest runner loses DYLD_LIBRARY_PATH; Task 12 must use the repository's documented
    direct-pytest package gate for this ament_python package instead of claiming a false RED.
next_command: Task 1 RED - $TEST_PYTHON -m pytest -q src/so101_demo_py/test/test_parallel_batch_contracts.py -k 'schema_v4 or schema_v3_frozen'
```

### Dispatch and goal readback (no second executor, no second goal)

| Item | Read back value |
| --- | --- |
| Host | `Terry-Mac-mini.local` (this session runs directly on it; no ssh, no ai-station action) |
| Worktree | `/Users/matianyi/Projects/robot_demo_001/.worktrees/so101-unbounded-queue-resource-budget-mac-mini` |
| Branch | `codex/so101-unbounded-queue-resource-budget` |
| HEAD | `b55c181e5b793aef95bf3bc7be9191138ddf00cd` = dispatch HEAD in the handoff; `a3468eca` is an ancestor |
| Upstream | `origin/codex/so101-unbounded-queue-resource-budget` at `bf1b6091` (branch is ahead 2) |
| Status | `git status --porcelain=v1` empty; submodule `third_party/mujoco_ros2_control` `e4c0241a` |
| tmux | exactly one task session `dst-so01-macos-mps-w2`, pane 0, pid 59434, tty `/dev/ttys006` |
| DSH session | `12d743e2-8902-4eca-acd1-835a39daa152` |
| Goal | `goal-746d697c-16dd-4456-aeef-ea2d7edfd945`, revision 1, phase `active`, `roundsStarted=1` |
| Goal round cap | `maxGoalRounds=100`, read from the DSH session store AND from the goal tool, not from prose |
| Goal patch | `followups/macos-mps-private-ipc-f8176773-cfdb-437a-b23a-32367f0a7c97/goal-100.patch.yml` |
| Receipt | `followups/.../dst.receipt`, 37 bytes, token `56178130-5b2d-4725-baf9-6bc31eabebc2`, sha256 `44e07cdf346db5733a74c2459f0a6f0555d8a1bb91e5753c6e1a34fbeb314c2d` |
| Second executor / second goal | not found: the only task tmux session is the one above, `seenGoalIds` has one entry |

Input documents were read completely and their SHA-256 values match the handoff exactly: design
`480da6dc…db1b`, design review `05a483e5…b71c8`, plan `cd098f40…ead2`, plan review `e8e91c78…7fc86`
(verdict `PASS`). The prior session's terminal result stands as history: `CP-UQ228` reported
`PARTIAL_PASS / PHYSICAL_W2_BLOCKED` with `five_batch_stability: 0/5`, and this task exists to close
those two boundaries. No physical claim from that session is reused as evidence here.

### Implementation run root

`/tmp/so101-debug-unbounded-queue-w2-mac-mini-3eed4ddd-a50c-4c21-b78f-60be2216ef9d/impl-macos-mps-w2-01/`
holds `environment.json`, `git-status.txt`, `git-identity.txt`, `process-inventory.txt`,
`module-origins.txt`, `ipc-base-readback.txt`, and the task-local gate runner `run-gate.sh`.
Each gate gets its own sibling run directory with argv, provenance, stdout/stderr, elapsed time,
exit code, and JUnit. No second evidence root was created; the root still has one writer.

### Gate runner bootstrap: three INVALID attempts, then a valid baseline

The runner needed three corrections before any product test could run. Every attempt is retained;
none of them is counted as a product RED:

1. `task0-baseline-01/` — INVALID. The runner used `set -u`; the ROS Jazzy `install/setup.bash`
   reads unset `COLCON_TRACE` and aborted at line 11. Zero tests started.
2. `task0-baseline-02/` — INVALID. `PYTHONPATH` pointed at `<worktree>/src/so101_demo_py/src`, but
   `setup.py` maps the namespace as `package_dir={"so101_demo": "src"}`, so the importable name
   `so101_demo` was absent (`ModuleNotFoundError`, exit 4, zero nodeids). The runner now builds the
   mapped-namespace layout (`source-packages/so101_demo -> src`) that the prior verified run used.
3. `task0-baseline-03/` — INVALID. Tests resolve the `so101_demo_py` ament prefix through
   `ament_index_python`, and `AMENT_PREFIX_PATH` had no such prefix
   (`PackageNotFoundError`, exit 4, zero nodeids). The runner now sources the task-owned overlay
   `branch-build-01/install`.
4. `task0-baseline-04/` — collected and ran, but the overlay's `build/`+`install/` package copies
   won the module search, so a source edit would not have reached the test process. Kept as
   superseded evidence and superseded by `task0-baseline-05/`.

`EXP-UQ229-TASK0-BASELINE: VALID`

```text
run_root: task0-baseline-05/
argv: /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -q
      src/so101_demo_py/test/test_parallel_batch_contracts.py
      src/so101_demo_py/test/test_parallel_start_guard.py
      src/so101_demo_py/test/test_parallel_unix_transport.py
      --junitxml=task0-baseline-05/task0-baseline.xml
exit_code: 1
result: 3 failed, 108 passed (111 collected), 0 errors, JUnit read back
elapsed_s: 1
```

Module origins for that gate: `rclpy` from `/Users/matianyi/ros2_jazzy/install/rclpy`, `torch`
2.13.0 from the Jazzy venv, `so101_demo` from the source tree
(`impl-macos-mps-w2-01/source-packages/so101_demo`), and ament prefix for `so101_demo_py` from
`branch-build-01/install/so101_demo_py`. The three failures are exactly the frozen schema-v3 Darwin
boundary recorded as `CP-UQ226`:

- `test_transport_basename_budget_and_exact_kernel_size`
- `test_long_durable_root_binds_connects_and_keeps_canonical_path`
- `test_failed_bind_leaves_no_socket_and_no_fd_leak`

All three fail because v3 requires `/proc/self/fd`, which does not exist on Darwin. They are the
baseline this task must replace with the closed v4 `darwin_private_path_unix` combination while
keeping the v3 branch and its Linux assertions intact. Environment facts for the record:
`torch.backends.mps.is_built()=True`, `is_available()=True`,
`recommended_max_memory()=19069665280` bytes; `/private/tmp/so101-ipc-501` does not exist, so no
prior campaign IPC directory is being reused.

Nothing was deleted, archived, pushed, or published. No W4/W6/W8 run, no Linux command, no
ai-station operation, and no real-hardware action occurred in this checkpoint.

_Ledger source HEAD: `b55c181e` (worktree clean apart from this checkpoint)._

## CP-UQ230 — Schema v4 is a closed platform combination; schema v3 is byte-frozen

`checkpoint_id: CP-UQ230`
`last_valid_experiment: EXP-UQ230-TASK1-V4-CONTRACT`
`commit: 668ddb59 feat(so101): add closed macOS MPS W2 schema v4`

`EXP-UQ230-TASK1-V4-CONTRACT: VALID`

RED (`task1-red-01/`, exit 1, **31 failed, 1 passed, 57 deselected**): every failure was the
absence of v4, not a product assertion. Twenty-seven were `FileNotFoundError` for the not-yet
created v4 YAML, four were `AttributeError` for the missing v4 names, and one was the genuine
pre-change product fact that v3 `requested_device` must be `cuda`. The single pass was
`test_schema_v3_bytes_are_frozen_by_the_v4_work`, i.e. the v3 freeze already held.

GREEN (`task1-green-09/`, exit 0, **33 passed, 57 deselected**), then the whole file
(`task1-full-01/`, exit 0, **90 passed, 0 failed, 0 errors**). `task1-green-01/` … `-08/` are the
intermediate cycles while the v4 field split was being settled; `-01`/`-02` failed on the closed
mapping (a field moved to the top level was still required inside `execution`), `-03` on a
read-only property, `-04`/`-05` on frozen-value bookkeeping, `-06`/`-07`/`-08` on the Linux
combination still carrying Darwin-only pins. They are retained as iteration evidence.

What v4 now is:

- exactly two closed combinations — Linux `cuda + proc_fd_unix + egl` and Darwin
  `mps + darwin_private_path_unix + cgl`. Anything else, including an unknown `mujoco_gl`, is
  `PLATFORM_COMBINATION_UNSUPPORTED`;
- exact `worker_count == 2`; `1, 3, 4, 6, 8` all return `PLATFORM_WORKER_COUNT_UNSUPPORTED`;
- `allow_cpu_fallback` must be exactly `False`; `requested_device: cpu` is refused;
- `mps_process_memory_fraction` must be a real number in `(0, 1]` (bools and numeric strings are
  refused, not coerced) and is refused outright on the Linux combination;
- `mps_minimum_headroom_bytes` must be a positive int, is required on Darwin and refused on Linux,
  so an MPS threshold cannot be smuggled into the CUDA document;
- `ipc_transport: auto` resolves to `darwin_private_path_unix` on Darwin and `proc_fd_unix`
  otherwise, and `resolved_manifest()` never reports `auto`;
- the v3 surface is untouched: the v3 YAML SHA-256 is still
  `991b5c1b4fbd0cc1f0a97bd20a5b5a4e02028634f3f4ef288ad87554b383ab70`, its 38 execution fields and
  5 guard fields are unchanged, and no `accelerator`/`ipc_transport` field exists on
  `ParallelRuntimeConfigV3`.

`StartGuardPolicy` gained `mps_minimum_headroom_bytes: int | None = None`. The default keeps every
existing v3 construction byte-identical, `START_GUARD_FIELDS` is unchanged so v3 still refuses the
key, and the v3 guard gate was re-run under Task 0 to confirm it. The full contracts file is green
(90 passed), which is the file's own v1–v3 history included.

One contract decision worth recording, because it is a narrowing a reviewer should see: v4 requires
`ros_domain_ids` to have exactly `worker_count` entries, so the Darwin v4 document configures two
domains (`181, 182`). That is the exact-W2 isolation choice, not a new budget mechanism.

_Ledger source HEAD: `668ddb59`; worktree clean; no evidence deleted._

## CP-UQ231 — A real MPS snapshot is admitted on this host inside the fixed budget

```yaml
checkpoint_id: CP-UQ231
last_valid_experiment: EXP-UQ231-TASK2-MPS-GUARD
current_hypothesis: The Darwin admission boundary CP-UQ228 recorded as GPU_TARGET_UNAVAILABLE has a
  real replacement: one bounded unified-memory read admits or refuses a W2 campaign without NVML.
working_tree_status: clean at commit 24badcea
owned_processes: NONE - the vm_stat helper exits inside the probe; no task-owned process survives
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - torch.mps.current_allocated_memory()/driver_allocated_memory() describe this process only and stay
    diagnostic; they must never enter the admission comparison.
  - The 9.66 GiB figure is one host observation, not a capacity certification and not a per-N budget.
next_command: Task 3 RED - CampaignSupervisor as real parent, spawner and reaper
```

`checkpoint_id: CP-UQ231`
`last_valid_experiment: EXP-UQ231-TASK2-MPS-GUARD`
`commit: 24badcea feat(so101): add lightweight Darwin MPS start guard`

`EXP-UQ231-TASK2-MPS-GUARD: VALID`

RED (`task2-red-01/`, exit 4, zero collectors): `ImportError: cannot import name 'accelerator_probe'`.
The only reason nothing ran was the absent module, which is a legitimate RED for a new boundary.

GREEN (`task2-green-08/`, exit 0, **99 passed, 0 failed, 0 errors**) across four files: the new
`test_parallel_accelerator_probe.py` (21 cases) plus `test_parallel_start_guard.py`,
`test_parallel_start_guard_probe.py` and `test_parallel_start_guard_composition.py`, so the v3 guard
suite and the new v4 hook were validated together. `task2-green-01/` … `-07/` are retained iteration
evidence (the `_reap_helper` timeout/not-reaped split, and two self-inflicted test-harness bugs that
were fixed in the test, never by weakening a product assertion).

Real read-only smoke on this host (`task2-mps-probe-smoke-01/`, exit 0):

```text
host: Terry-Mac-mini.local, macOS-26.6.2-arm64
python: /Users/matianyi/ros2_jazzy/.venv/bin/python3 (3.11.15)
torch: 2.13.0 at /Users/matianyi/ros2_jazzy/.venv/lib/python3.11/site-packages/torch
torch.backends.mps.is_built() = True
torch.backends.mps.is_available() = True
torch.mps.recommended_max_memory() = 19069665280 bytes
vm_stat: 23 lines, page size 16384, raw text retained as vm_stat-raw.txt
snapshot.kind = mps, selector = default
snapshot.available_bytes = 10372448256 (min(host available, recommended) = 9.66 GiB)
snapshot.metric_source = unified-memory-proxy:vm_stat(host_available)
                         +torch.mps.recommended_max_memory@torch2.13.0
evaluation = PASS / MPS_HEADROOM_OK, cutoff 1073741824
probe elapsed = 0.552 s inside the 2 s policy deadline
model_loaded = false, mps_kernel_launched = false
```

What the checkpoint establishes: the boundary that CP-UQ228 reported as
`GPU_TARGET_UNAVAILABLE` now has a real, auditable replacement that admits this host, and the
figure is labelled `unified-memory-proxy` everywhere. What it does not establish: any capacity
certification, any per-N budget, or any part of the W2 runtime. No model was loaded and no MPS
kernel was launched, so this is not broker or inference evidence.

Fail-closed branches covered by the gate: MPS not built / not available; missing, zero, negative or
non-int `recommended_max_memory`; empty, unit-less, zero-page-size or counter-less `vm_stat`; a
raising helper; an already-expired deadline with zero helper calls; a deadline consumed mid-read; a
helper that ignores its deadline (`VM_STAT_TIMEOUT`) versus one that cannot be confirmed dead
(`VM_STAT_NOT_REAPED`); and a policy without the floor, which is refused rather than admitted.

The v3 surface is unchanged: `START_GUARD_FIELDS` still has no MPS key, `ResourceSnapshot` still
requires an NVML-shaped `gpu_free_bytes`, and `EpochStartGuard` only passes the accelerator keyword
for a policy that carries the floor, so existing v3 coordinators keep their exact signature.

_Ledger source HEAD: `24badcea`; no evidence deleted; no Linux or W4/W6/W8 action._

## CP-UQ232 — The supervisor is now the real parent, and its intent is durable before every spawn

```yaml
checkpoint_id: CP-UQ232
last_valid_experiment: EXP-UQ232-TASK3-SUPERVISOR
current_hypothesis: A campaign can be made crash-auditable without new authority, by making the
  spawn intent durable before Popen and by refusing the next campaign on any unresolved intent.
working_tree_status: clean at commit f20e1bc7
owned_processes: NONE - every test child was stopped and reaped; terminate_all readback is in the gate
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - ACK handshake semantics are proven against task-owned Python children; wiring the real broker and
    worker bootstrap to the ACK is Task 8/Task 9 work and is not claimed here.
  - The receipt is a JSON file with fsync + atomic replace; that is durability against crash, not
    against a hostile same-UID writer, and the v4 trust model does not claim the latter.
next_command: Task 4 RED - DarwinPrivatePathUnixAddress and exact endpoint cleanup
```

`checkpoint_id: CP-UQ232`
`last_valid_experiment: EXP-UQ232-TASK3-SUPERVISOR`
`commit: f20e1bc7 feat(so101): supervise owned W2 children durably`

`EXP-UQ232-TASK3-SUPERVISOR: VALID`

RED (`task3-red-01/`, exit 4, zero collectors): `No module named
'so101_demo.parallel_batch.campaign_supervisor'`. Nothing ran, so nothing can be mistaken for a
product failure. GREEN (`task3-green-03/`, exit 0, **13 passed**), and the regression gate
(`task3-regression-01/`, exit 0, **118 passed**) re-ran the process, resource-identity and full
contract files together. `task3-green-01/` and `-02/` are retained iteration evidence; `-01` failed
because the test's `python -c` children read `sys.argv[0]` as `-c`, which was a test-harness bug
fixed in the test.

What the supervisor now guarantees:

- **Claim**: `MPS:DEFAULT` is an `flock(LOCK_EX | LOCK_NB)` on a state-root lock file. A second
  supervisor gets `CAMPAIGN_CLAIM_HELD`, and unlinking the lock path does not transfer the claim,
  because the held descriptor still owns the inode.
- **Durable intent**: `begin_spawn` writes a `SPAWNING` entry (role, slot, expected argv, nonce,
  timestamp) with `fsync` + `os.replace` + directory `fsync` *before* anything is executed.
- **Registration gate**: `spawn` runs the child in its own session, then waits for a child-written
  `RegistrationAck` whose PID matches. Only then does the entry become `ACTIVE` with the child's
  real PID, process group and birth identity. A child that never acknowledges is stopped by exact
  identity and recorded `FAILED / CHILD_ACK_TIMEOUT`; it is never promoted.
- **Blocking**: an unresolved `SPAWNING` intent in an on-disk receipt refuses the next campaign with
  `CAMPAIGN_RECEIPT_UNRESOLVED`, including after a simulated supervisor crash that dropped the
  claim without cleaning up.
- **Exact cleanup**: `terminate_all` stops and reaps only ACTIVE children whose recorded birth
  identity still matches, and clears the receipt only when `cleanup_complete` holds. A child whose
  PID was rewritten to a foreign process (this pytest process, in the test) is reported by
  `inspect_orphans` and never signalled.
- **Coordinator liveness**: `check_coordinator` returns `ALIVE`, `OWNER_GONE` or
  `HEARTBEAT_LOST`; the latter two run owned cleanup *while the claim is still held*, which is what
  lets a successor trust the receipt.

One test byproduct is recorded rather than hidden: the first (buggy) child script left a stray file
named `30.0` at the repository root. It was moved, not deleted, to
`impl-macos-mps-w2-01/test-byproducts/30.0` (sha256
`da43c199020cae82c9ef40de76fd86271f9dd20ca3274c81803f970e55d8ac07`), and the worktree is clean
again.

_Ledger source HEAD: `f20e1bc7`; no evidence deleted; no Linux or W4/W6/W8 action._

## CP-UQ233 — Darwin now has a real private socket path, and its cleanup only deletes what it registered

```yaml
checkpoint_id: CP-UQ233
last_valid_experiment: EXP-UQ233-TASK4-UNIX-ADDRESS
current_hypothesis: The IPC half of CP-UQ228's PHYSICAL_W2_BLOCKED has a real replacement: a
  canonical private path whose filesystem contract is the whole access check.
working_tree_status: clean at commit 14b6e527
owned_processes: NONE - every bound socket was bound and unlinked inside the test process
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - The Linux `proc_fd_unix` transport tests still fail on this host by design; they are recorded as
    DEFERRED_ENVIRONMENT, not skipped and not rewritten.
  - The v4 Client deliberately has no endpoint authentication. That is the approved trust model for a
    single-user task-owned simulation host and is not a multi-tenant security claim.
next_command: Task 5 RED - permission-only v4 RPC envelope and lightweight IPC validation
```

`checkpoint_id: CP-UQ233`
`last_valid_experiment: EXP-UQ233-TASK4-UNIX-ADDRESS`
`commit: 14b6e527 feat(so101): add private Darwin Unix address strategy`

`EXP-UQ233-TASK4-UNIX-ADDRESS: VALID`

RED (`task4-red-01/`, exit 1, **14 failed, 7 passed**) and GREEN
(`task4-green-04/`, exit 0, **23 passed**). `task4-green-01/` … `-03/` are retained iteration
evidence. Two of those iterations found real product gaps rather than test bugs:

1. the first version demanded that the *immediate* parent of the private base be root-owned and
   sticky, which is right for `/private/tmp/so101-ipc-<uid>` and wrong for any other base. It was
   replaced by an ancestor walk, which is the property that actually matters: nobody else may be
   able to rename the directory a socket is bound into. An ancestor is accepted when it is not
   group/other-writable, or when it is a root-owned sticky directory.
2. the ancestor check originally applied only to directories **not** owned by the current user, so a
   user's own `0777` directory passed. That is exactly the case where another local user can swap
   the base, and it now fails with `ANCESTOR_WRITABLE` regardless of owner.

A third iteration was a test-environment fact worth keeping: pytest's own `tmp_path` on this host is
about 200 bytes, which no Darwin `sun_path` can ever hold (measured capacity: 103 bytes bind, 104
fails with `AF_UNIX path too long`). Socket-binding tests therefore use a short per-test directory
directly under `/private/tmp/so101-ipc-<uid>` and remove it in teardown; the teardown readback shows
no leftover `so101-ipc-test-*` directory.

What the strategy now guarantees:

- canonical base `/private/tmp/so101-ipc-<uid>`; never `$TMPDIR`, never the evidence root, never
  `/tmp` (a Darwin symlink);
- the base and the campaign directory are owned by us, real directories, not symlinks, mode `0700`;
- every campaign gets a fresh `b-<12 hex>` directory, and a colliding id is skipped, never reused
  and never deleted;
- endpoint names are the closed role map (`coordinator.sock`, `broker.sock`, `w1.sock`, `w2.sock`);
- the encoded-path check is on bytes plus the terminating NUL against the real capacity, so a
  multi-byte path is refused for its byte length, not its character count;
- a bound socket is mode `0600` and is registered with its device/inode identity;
- cleanup unlinks exactly one registered socket after re-checking that identity, reports
  `ALREADY_GONE` when it vanished, `NOT_OWNED` when something replaced it (and then deletes
  nothing), and removes the campaign directory only when it is empty. A sibling campaign is never
  scanned or touched.

The frozen Linux `proc_fd_unix` behaviour is untouched: `ProcFdUnixAddress` keeps the 108-byte
capacity and refuses to pretend it can do durable unlinking, because a v3 endpoint dies with its
owning process.

_Ledger source HEAD: `14b6e527`; no evidence deleted; no Linux or W4/W6/W8 action._

## CP-UQ234 — The v4 RPC is permission-only, and the v3 Linux transport tests still say so

```yaml
checkpoint_id: CP-UQ234
last_valid_experiment: EXP-UQ234-TASK5-V4-RPC
current_hypothesis: The v4 envelope can drop token/generation/lease while remaining a bounded,
  closed server, and the frozen v3 Linux protocol tests keep failing on Darwin rather than being
  rewritten to pass.
working_tree_status: clean at commit b6bab6be
owned_processes: NONE - every server was stopped and every socket unlinked inside the gate
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - The v4 client performs no authentication at all. This is the approved single-user task-owned
    simulation trust model; it is not a multi-tenant security claim.
  - The source gate cannot be fully green on this host because 19 v3 Linux transport tests require
    /proc/self/fd. That is DEFERRED_ENVIRONMENT and stays visible.
next_command: Task 6 RED - immutable inference input snapshot
```

`checkpoint_id: CP-UQ234`
`last_valid_experiment: EXP-UQ234-TASK5-V4-RPC`
`commit: b6bab6be feat(so101): add permission-only v4 Unix RPC`

`EXP-UQ234-TASK5-V4-RPC: VALID`

GREEN (`task5-green-04/`, exit 0, **33 passed, 0 failed**). `task5-red-01/`,
`task5-green-01/` … `-03/` are retained iteration evidence. Two of those iterations found real
defects and one found a real gap in the acceptance rule:

1. the server bound its socket without setting the mode, so it came out `0755` and the address
   strategy correctly refused to register it. `bind` now binds under `umask(0o177)` and then
   `chmod`s to `0600` before `listen`, so the socket is never reachable by group or other.
2. the first version's accept loop only *enqueued* connections; nothing consumed the queue, so
   every round trip timed out after the client's 30 s budget. The accept loop is now paired with a
   bounded dispatcher that dequeues and runs each connection on its own short-lived thread, which
   is what lets two Workers be in flight while the queue still bounds pending work. The evidence
   records `peak_queue_depth` and `refused_connects`.
3. the queue-full test originally demanded a `QUEUE_FULL` *response* while also setting
   `queue_capacity=1`, which also sets the listen backlog, so the kernel refused the extra
   connections with `ECONNREFUSED` before the server ever saw them. Both refusals are legitimate
   and the test now accepts either, while still requiring that the server keeps serving after the
   burst.

What v4 now guarantees:

- the request envelope has exactly `request_id`, `operation`, `deadline_monotonic_ns`, `payload`;
  the response has exactly `request_id`, `status`, `error`, `output_descriptor`, `timing`, with
  exactly one of descriptor/error;
- a frame carrying `token`, `generation`, `lease`, `lease_id`, `lease_epoch`, `endpoint_receipt`,
  `peer_credentials`, `inode` or `receipt` is refused in either direction, so the retired
  vocabulary cannot be smuggled back in;
- the server enforces the frame cap, a closed schema, the operation allowlist, the deadline and a
  bounded queue, with stable codes `MALFORMED_FRAME`, `OVERSIZED_FRAME`, `UNKNOWN_OPERATION`,
  `DEADLINE_EXPIRED`, `QUEUE_FULL`, `INVALID_REQUEST`, `INTERNAL_ERROR`;
- the client makes **no** endpoint authentication call: a monkeypatched `os.stat`/`os.lstat` for
  the endpoint path records zero calls during a successful round trip;
- two concurrent clients each get their own answer with their own `request_id`;
- restart creates a new campaign directory and a new socket, the old path is unusable, and cleanup
  leaves no socket and no campaign directory behind.

The frozen v3 surface was re-run and is unchanged (`task4-regression-01/`, exit 1,
**19 failed, 28 passed**): the same Linux-only `/proc/self/fd`, `/run/user` and `SO_PEERCRED`
assumptions that CP-UQ225 recorded. They are recorded as `DEFERRED_ENVIRONMENT`, not skipped, not
rewritten, and not counted as v4 regressions.

_Ledger source HEAD: `b6bab6be`; no evidence deleted; no Linux or W4/W6/W8 action._

## CP-UQ235 — Snapshots are immutable, verified against the bytes, and never deleted

```yaml
checkpoint_id: CP-UQ235
last_valid_experiment: EXP-UQ235-TASK6-SNAPSHOT
current_hypothesis: The data plane can stay out of the control frame while every declared fact is
  re-derived from the bytes before a model ever sees them.
working_tree_status: clean at commit 0ee79d07
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - The Broker wiring that calls `read_document` before queueing a request is Task 8 work; this
    checkpoint proves the store and registry, not the end-to-end request path.
next_command: Task 7 RED - Coordinator local one-time request registry
```

`checkpoint_id: CP-UQ235`
`last_valid_experiment: EXP-UQ235-TASK6-SNAPSHOT`
`commit: 0ee79d07 feat(so101): validate immutable inference snapshots`

`EXP-UQ235-TASK6-SNAPSHOT: VALID`

GREEN (`task6-green-01/`, exit 0, **16 passed**), then with the contract extension
(`task6-green-03/`, exit 0, **107 passed** across the snapshot and contract files). The RED pass
(`task6-red-01/`) surfaced one real wording bug: `SnapshotDescriptor` refuses a bad path with
`SnapshotError`, which is a `RuntimeError`, not a `ValueError`; the test now asserts the class the
product actually raises instead of the class a reviewer might expect.

What now holds:

- a descriptor carries exactly `relative_path`, `size_bytes`, `sha256`, `shape`, `dtype`,
  `encoding`, `frame_timestamp_ns`, and validates every one of them at construction;
- absolute paths, `..`, `.`, backslashes and empty paths are refused before any filesystem call;
- the writer rejects anything that is not a real `ndarray`, rejects a non-identifier slot, writes
  under a `.part` name with `fsync`, renames atomically, `fsync`s the directory, and then removes
  the owner write bit so the snapshot is immutable for the campaign;
- the reader re-derives size, SHA-256, shape and dtype from the bytes and refuses any mismatch, a
  symlink, a non-file, a missing file, or a file above the ceiling even when the descriptor agrees;
- `broker_max_frame_bytes` (8 MiB) and `max_input_snapshot_bytes` (64 MiB) are separate closed
  fields in the v4 document and the resolved manifest, and a control frame carrying a descriptor
  stays under 1 KiB in the test;
- the registry holds a snapshot until the request completes, is cancelled, or is invalidated;
  after release it reports a `DELETION_CANDIDATE` and the file is verified still readable. Nothing
  is deleted.

The v4 document gained one required field (`max_input_snapshot_bytes: 67108864`), so the contract
gate was re-run with it and remains green.

_Ledger source HEAD: `0ee79d07`; no evidence deleted; no Linux or W4/W6/W8 action._

## CP-UQ236 — One-time admission is local, and the durability-ordering tests now run on Darwin

```yaml
checkpoint_id: CP-UQ236
last_valid_experiment: EXP-UQ236-TASK7-REGISTRY
current_hypothesis: With no token, generation or lease on the v4 control channel, a single local
  lock-protected table can be the whole admission gate for inference results.
working_tree_status: clean at commit 54990e1e
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - The worker/broker call sites that must route every result through `admit_inference_result` are
    Task 8/Task 9 work; this checkpoint proves the table and the Coordinator hook.
next_command: Task 8 RED - real MPS broker bootstrap, shared models and one execution lane
```

`checkpoint_id: CP-UQ236`
`last_valid_experiment: EXP-UQ236-TASK7-REGISTRY`
`commit: 54990e1e feat(so101): gate inference results with one-time requests`

`EXP-UQ236-TASK7-REGISTRY: VALID`

GREEN (`task7-green-02/`, exit 0, **18 passed**), then with the Coordinator hook
(`task7-regression-02/`, exit 0, **154 passed, 2 deselected**) and finally the whole Coordinator
suite with the portability fix below (`task7-regression-05/`, exit 0, **138 passed**).

What the registry guarantees:

- one opaque `request_id`, bound atomically to slot, point, attempt, model, input-snapshot SHA,
  deadline and the Broker's PID plus birth identity; the binding never leaves the Coordinator;
- an id is never reused: a duplicate registration is refused, including after a consume;
- `consume_result` is the only admission path. It refuses an unknown id, a second consume
  (`REQUEST_ALREADY_CONSUMED`), a cancelled request, an expired deadline, an input-SHA mismatch and
  a Broker-identity mismatch, and it records every decision in an append-only event log;
- consume, cancel and `sweep_expired` share one lock boundary. Twenty-five racing rounds and an
  eight-way concurrent consume test both show exactly one winner;
- `invalidate_broker` releases every binding to one identity in a single call and returns the ids,
  and a late result from the replaced Broker is then refused;
- the registry is capacity-bounded, and there is no token/generation/lease parameter anywhere in
  the API, so a caller cannot pass one even by accident.

A real, pre-existing Darwin defect was found and fixed in the *test harness* while doing this. Two
durability-ordering tests (`test_journal_fsync_precedes_grant_projection_and_ack` and
`test_aggregate_atomic_write_syncs_file_then_replace_then_parent`) resolved an fsync descriptor by
hardcoding `/proc/self/fd/<fd>`, so on Darwin they compared against a path that does not exist and
failed for a reason unrelated to the journal. The suite now resolves the descriptor through
`/proc/self/fd` on Linux and `fcntl(F_GETPATH)` on Darwin. The two tests then pass unchanged, which
is a strictly stronger check than deselecting them.

_Ledger source HEAD: `54990e1e`; no evidence deleted; no Linux or W4/W6/W8 action._

## CP-UQ237 — The full source gate is measured, and its failures are all environment boundaries

`checkpoint_id: CP-UQ237`
`last_valid_experiment: EXP-UQ237-SOURCE-GATE-MEASURE`
`commit: df962446 (ledger only; source HEAD 54990e1e)`

`EXP-UQ237-SOURCE-GATE-MEASURE: VALID MEASUREMENT`

`source-gate-after-t7-01/`: the whole `src/so101_demo_py/test` suite (benchmark excluded),
exit 1, **239 failed, 3132 passed, 8 skipped, 40 errors in 88.29 s**. This is a measurement of
this host against a Linux-targeted suite, not a regression from this task: the failure-reason
histogram is entirely environment boundaries.

| Count | Reason | Classification |
| --- | --- | --- |
| 280 | `FileNotFoundError: /data/work/...` plus 28 `OSError: [Errno 30] Read-only file system: '/data'` | The ai-station evidence root does not exist on this Mac. `DEFERRED_ENVIRONMENT`. |
| 76 | `FileNotFoundError: /proc/self/fd...` on top of 65 `UNIX_TRANSPORT_UNAVAILABLE` and 63 `ResourceAllocationError: UNIX_TRANSPORT_UNAVAILABLE` | The schema-v3 Linux dirfd transport. This is the boundary the v4 Darwin path replaces for the product, not a v3 test that may be rewritten. `DEFERRED_ENVIRONMENT`. |
| 71 | `ValueError: PATH_OWNER` | v3 endpoint-owner checks that require Linux ownership semantics. `DEFERRED_ENVIRONMENT`. |
| 66 | `ModelRuntimeInfrastructureError` | No perception model runtime is provisioned on this host. `DEFERRED_ENVIRONMENT`. |
| 45 | `FileNotFoundError: 'sysctl'` | A v3 Darwin memory fallback invokes `sysctl` without an absolute path while `/usr/sbin` is not on the bash tool's PATH. Real, small, and task-owned: worth a scoped fix. |
| 5 | `FileNotFoundError: /run/user/501` | Linux runtime directory. `DEFERRED_ENVIRONMENT`. |

The macOS package gate therefore cannot be reported green, and no platform skip was added to make
it look green. The gates this task added are green on their own merits: contracts 91, accelerator
probe 21, start guard 99 across four files, campaign supervisor 13, Unix address 23, v4 RPC 33,
input snapshot 16, inference registry 18, Coordinator 138.

Next round's first candidate fix is the bare `sysctl` invocation (45 cases), which is the only
cluster above that looks like a genuine product portability gap rather than a missing Linux
facility. It must be fixed as a real fix (absolute path plus a fail-closed fallback), never by
loosening the memory check.

_Ledger source HEAD: `df962446`; no evidence deleted._

## CP-UQ238 — The environment gap was the PATH, and the MPS broker really warms up on one lane

```yaml
checkpoint_id: CP-UQ238
last_valid_experiment: EXP-UQ238-TASK8-MPS-BROKER
current_hypothesis: A single Broker can load one real model set on MPS, warm it, synchronise, and
  publish a ready receipt that is derived from recorded facts rather than asserted.
working_tree_status: clean at commit a89e5571
owned_processes: NONE - the real smoke exited; its lane worker thread died with the process
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - The smoke uses tiny stand-in models. It proves the bootstrap, not the perception model set; the
    real weights are Task 12/13 work.
  - The Broker is not yet wired to `PerceptionBroker` or to the Coordinator's registry; that is
    Task 9 and Task 10 work.
next_command: Task 9 RED - whole-pool rebuild after a broker failure
```

`checkpoint_id: CP-UQ238`
`last_valid_experiment: EXP-UQ238-TASK8-MPS-BROKER`
`commit: a89e5571 feat(so101): bootstrap a single-lane shared MPS broker`

### The 45-case "sysctl" cluster was a PATH gap, not product code

`path-fix-mujoco-01/` (exit 0, **13 passed**). The failing tests import `mujoco`, and
`mujoco/__init__.py` calls a bare `sysctl -n sysctl.proc_translated` at import time. The DSH bash
tool starts with a minimal `PATH` that omits `/usr/sbin` and `/sbin`, and macOS ships `sysctl` in
`/usr/sbin`; a login shell has it. The task-local runner now appends `/usr/sbin:/sbin` and fails
closed if `sysctl` is still unreachable, so the environment matches an interactive shell instead of
masking a product problem. Re-measured source gate
(`source-gate-after-path-fix-01/`): **234 failed, 3177 passed, 8 skipped**, down from
`239 failed, 3132 passed` — 45 more passing tests and no new failures. No product `sysctl` call
needed changing: `start_guard.py` and `accelerator_probe.py` already use the absolute path.

### Task 8: real device, real lane

`EXP-UQ238-TASK8-MPS-BROKER: VALID`

RED/GREEN: `task8-green-01/` … `-05/` are retained; the final gate
(`task8-green-05/`, exit 0, **36 passed**). Three real defects were found by the tests rather than
by inspection:

1. the lane originally executed the item in the *submitter's* thread, so two concurrent submitters
   could run two Metal calls at once — exactly what "single lane" forbids. It is now a single
   worker thread with a bounded queue, and `max_concurrent` is incremented only by that worker.
2. `MpsBrokerBootstrap.clock` was referenced as `self._clock`, a latent `AttributeError`.
3. real PyTorch reports MPS tensor devices as **`mps:0`**, not `mps`, so the parameter/output
   device check refused a genuinely correct model. `is_mps_device` now accepts both spellings and
   still refuses `cpu`, `cuda:0`, `None` and `mpsx`.

Real-device smoke (`task8-mps-bootstrap-smoke-01/`, exit 0) on this host:

```text
status: READY, receipt_ready: true
fallback_env_before_import: 0 (the first uninstrumented run correctly REFUSED with
  MPS_FALLBACK_NOT_PINNED and its readback is retained as refusal-readback.json)
import_order_checked_before_import: true
torch 2.13.0, mps built+available, runtime_device mps, fraction 0.8
recommended_max_memory_bytes 19069665280, driver_allocated_memory_bytes 10977280
models: tiny-yolo and tiny-grounded-sam, both device mps:0, parameters [mps:0],
  output shape [1, 4, 1, 1] float32, synchronized true
lane: submitted 7, executed 7, rejected 0, peak_depth 1, max_concurrent 1
after two concurrent inferences: max_concurrent still 1
warmup_total_latency_s: 0.3047
```

That is the design's three broker requirements measured rather than asserted: the fallback pin is
checked before `import torch` (and again after), the allocator cap is set before any model loads,
and both models share one lane whose measured concurrency never exceeds one. Tiny models mean this
claims the bootstrap only — not the perception weights and not any W2 runtime result.

_Ledger source HEAD: `a89e5571`; no evidence deleted; no Linux or W4/W6/W8 action._

## CP-UQ239 — The rebuild order is a testable contract, and absence is confirmed separately

```yaml
checkpoint_id: CP-UQ239
last_valid_experiment: EXP-UQ239-TASK9-POOL-RECOVERY
current_hypothesis: A Broker failure can be recovered by rebuilding the whole pool, and every
  safety gate can be asserted as an order rather than described in a comment.
working_tree_status: clean at commit d63c32b7
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - The recovery is expressed over injected ports; wiring the real Supervisor, ROS cancellation
    helpers and Broker spawn into those ports is Task 10/13 work and is not claimed here.
  - This checkpoint proves the ordering and the refusal gates, not a live end-to-end broker crash.
next_command: Task 10 RED - compose exact W2, resolved manifest and package resources
```

`checkpoint_id: CP-UQ239`
`last_valid_experiment: EXP-UQ239-TASK9-POOL-RECOVERY`
`commit: d63c32b7 feat(so101): rebuild the full W2 pool after broker failure`

`EXP-UQ239-TASK9-POOL-RECOVERY: VALID`

GREEN (`task9-green-04/`, exit 0, **13 passed**) and the regression gate
(`task9-regression-01/`, exit 0, **135 passed** across recovery, registry, contracts and
supervisor). `task9-green-01/` … `-03/` are retained; all three were test-expectation bugs in the
new tests, not product changes, and each was fixed in the test.

The recovery is now a declared tuple, `RECOVERY_STEPS`, and the test asserts the recorded port
calls match it element by element. That makes "the design's order was followed" a fact rather than
a claim. The gates, each with its own refusal test:

- the request must be removed from the local table **first**; if the table will not give it up,
  recovery does not start at all and no process is touched;
- the point is recorded as `INFRASTRUCTURE_FAILURE` with `business_status: None`, so an
  infrastructure fault can never masquerade as a business failure;
- both Workers are stopped before anything is spawned;
- controller cancellation and controller **absence** are two separate ports, so a caller cannot
  satisfy the design by cancelling and asserting success. Unproven absence stops the rebuild before
  any process is reaped or any Broker is spawned;
- every owned PID must come back from the reap; one missing PID stops the rebuild, because a
  process we cannot prove dead may still hold the old socket;
- the new campaign path must differ from the old one;
- the Broker must be ready before either Worker is spawned, and a partially rebuilt pool is never
  reported as ready;
- rebuilding the pool and requeueing the point are separate decisions, so a successful rebuild with
  a declined requeue is reported honestly as `recovered: false` with `broker_ready: true`;
- every worker spawn in the trace targets the new campaign path, never the old one.

When no motion was in flight the controller ports are not called at all, which matches the
design's LEASED/INITIALIZING case rather than pretending there was a goal to cancel.

_Ledger source HEAD: `d63c32b7`; no evidence deleted; no Linux or W4/W6/W8 action._

## CP-UQ240 — Exact W2 composes to a resolved manifest, and the schema gate lives in one place

```yaml
checkpoint_id: CP-UQ240
last_valid_experiment: EXP-UQ240-TASK10-W2-COMPOSITION
current_hypothesis: Widening the execution-schema gate for v4 can be done without changing one byte
  of v3 behaviour, and exact W2 can be composed into a manifest that records resolved values only.
working_tree_status: clean at commit 930a0396
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - The CLI and allocator now reach v4, but the CLI still has no v4-only launch path wired to the
    Supervisor and Broker; that wiring is Task 13 work.
  - The `resources` suite has 45 pre-existing Darwin failures from the v3 Linux `/proc/self/fd`
    transport. The count is identical before and after this change, which is how the no-regression
    claim is grounded.
next_command: Task 11 - check whether Teleop/OpenAPI/Web expose accelerator, guard or IPC state
```

`checkpoint_id: CP-UQ240`
`last_valid_experiment: EXP-UQ240-TASK10-W2-COMPOSITION`
`commit: 930a0396 feat(so101): compose exact W2 macOS MPS campaigns`

`EXP-UQ240-TASK10-W2-COMPOSITION: VALID`

GREEN (`task10-green-01/`, exit 0, **19 passed**). Regression
(`task10-regression-01/`): **73 failed, 245 passed**, and the important number is the distribution —
the `test_parallel_batch_resources` failure count is **45 before and 45 after** this change, all
`UNIX_TRANSPORT_UNAVAILABLE` / `/proc/self/fd` on Darwin. No regression was introduced; the CLI
suite's 28 failures were already present in `source-gate-after-path-fix-01/`.

What Task 10 added:

- `w2_composition.load_execution_config` is now the single schema gate used by the CLI, the resource
  allocator and the tests. It returns the **byte-identical** v3 object (asserted by equality against
  `load_parallel_runtime_config_v3`) and adds v4; v1/v2 stay refused with the same error code.
- `load_execution_config_for_schema` refuses a Darwin v4 document on a non-Darwin host and a Linux
  v4 document on Darwin. That is what makes "the Linux combination is retained in the contract but
  not executed here" a checked statement.
- `exact_w2_slots` always returns two slots. A one-point campaign keeps `slot-1` idle and is
  reported as such, so a short batch can never silently become W1; a three-point campaign fills both
  slots in order.
- `compose_w2_campaign` refuses any worker count other than two, a relative evidence root and an
  empty campaign id, and records the resolved manifest fields: accelerator `mps`, selector
  `default`, transport `darwin_private_path_unix`, GL `cgl`, worker count 2, Broker PID **and** birth
  identity, model provenance (id, weights SHA, Grounded-SAM manifest SHA, image size), snapshot root,
  supervisor receipt path, guard timeout, headroom floor, allocator fraction, snapshot ceiling, frame
  ceiling and the two ROS domain ids. No value in the projection is `auto`.
- `assert_no_host_platform_calls` refuses a plan that mixes MPS with the Linux transport (or the
  reverse), so a Darwin plan cannot claim an NVML or `/proc/self/fd` dependency.
- the v3 plan still resolves the frozen Linux combination with no MPS field present anywhere.

_Ledger source HEAD: `930a0396`; no evidence deleted; no Linux or W4/W6/W8 action._

## CP-UQ241 — The Teleop projection was wrong, and two gate results were invalid for a package reason

```yaml
checkpoint_id: CP-UQ241
last_valid_experiment: EXP-UQ241-TASK11-TELEOP
current_hypothesis: The API already projects the guard and worker-count surface, so the honest
  change is two data fields, not a UI refactor; and the runner must import this worktree's teleop.
working_tree_status: clean at commit b1557da5
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - 27 teleop failures remain on this host, measured at 31 before this change and unchanged in kind.
next_command: Task 12 - fresh source, package, OpenAPI, copied-install and served-byte gates
```

`checkpoint_id: CP-UQ241`
`last_valid_experiment: EXP-UQ241-TASK11-TELEOP`
`commit: b1557da5 feat(teleop): expose macOS MPS W2 runtime state`

### A real provenance defect in the task-local runner

The first teleop gate imported `so101_teleop` from
`/Users/matianyi/Projects/robot_demo_001/moveit-demo/install/...` — the **canonical checkout's**
installed copy, a different revision from this worktree. `SOURCE_PACKAGES` only linked
`so101_demo`, so every teleop assertion was silently testing someone else's code. The runner now
links `src/so101_teleop/so101_teleop` too and fails closed if the link is not importable, and the
five earlier teleop/OpenAPI gates (`task11-teleop-01/02`, `task11-openapi-01/02/03`) are marked
INVALID with that reason. That is exactly the "stale installed binary" failure the repository's
own rules warn about, caught here by reading the provenance record instead of trusting the result.

### Task 11 result

`EXP-UQ241-TASK11-TELEOP: VALID`

The API already exposes the worker-count and guard surface, so no UI refactor was warranted. Two
data fields were added to the resolved projection:

- `StartGuardPolicyResponse.mps_minimum_headroom_bytes: int | None` — the fixed unified-memory
  floor, present only on the schema-v4 MPS combination, so a client can show the cutoff that
  refused a start. Null on every v3 answer, which keeps existing consumers byte-compatible.
- `StartGuardStatus.admission_kind: str | None` — `unified-memory-proxy` when the accelerator
  check ran (`mps_headroom` present) or `nvml-device` when the v3 GPU check ran. This is the
  design's insistence that a unified-memory proxy is never presented as a device-level VRAM
  reading, made legible to the browser.

A/B evidence, because "no regression" should be measured:

```text
task11-teleop-ab-01/ (edits stashed): 31 failed, 365 passed
task11-teleop-full-01/ (edits in):    27 failed, 369 passed
fixed by this change: the 4 new projection tests, nothing else
newly failing: none
```

Generated artifacts were regenerated with the project's own tools, never hand-edited:
`expert_validation_openapi.json` via `python3 -m so101_teleop.openapi_export --validation`, and
`web/src/api/expert-validation-schema.d.ts` via `bun run generate:api:validation` after
`bun install --frozen-lockfile`. Both new fields appear in both artifacts.

The web gate is **green when run as separate steps**: `task11-web-build-01/` (exit 0,
`tsc -b && vite build`) and `task11-web-unit-01/` (exit 0, **30 files, 126 tests**). Chaining them
in one shell produced 77 failures with `act(...) is not supported in production builds of React` —
the `vite build` step leaves `NODE_ENV=production` set and vitest then loads production React. That
is a harness ordering artifact, not a product or test defect, and the two gates are recorded
separately so neither hides the other.

_Ledger source HEAD: `b1557da5`; no evidence deleted; no Linux or W4/W6/W8 action._

## CP-UQ242 — Task 12 gates are green or honestly deferred; the W2 smoke harness still hangs

```yaml
checkpoint_id: CP-UQ242
last_valid_experiment: EXP-UQ242-TASK12-GATES
current_hypothesis: The fresh-install, copied-install and served-byte gates can be closed with real
  provenance, and the remaining macOS package failures are all Linux-facility boundaries.
working_tree_status: clean at commit 0bb4ec74 (no code change was required this round)
owned_processes: NONE - the smoke left no orphan; pgrep found nothing after the timeout
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - task13-w2-runtime-smoke-01 hangs in its broker phase and is INCOMPLETE, not PASS.
  - The perception weights are not provisioned anywhere on this host, so a real broker loading the
    real model set cannot be demonstrated here.
next_command: bisect the Task 13 smoke hang with a flushed marker at the top of the broker phase
```

`checkpoint_id: CP-UQ242`
`last_valid_experiment: EXP-UQ242-TASK12-GATES`

### Task 12 results

| Gate | Run | Result |
| --- | --- | --- |
| Fresh symlink build | `task12-fresh-build-02/` | exit 0, 1 package, v4 config and all 9 new modules present |
| Package boundary (direct pytest, documented macOS contract) | `task12-package-gate-01/` | exit 1, **232 failed, 3247 passed, 8 skipped** = 3487 collected |
| Native `colcon test` | `task12-colcon-test-01/` | **INVALID environment**: drops `DYLD_LIBRARY_PATH`, `Library not loaded: @rpath/librosidl_typesupport_c.dylib`, zero nodeids, exit 2, `colcon test-result` = 0 tests |
| Collection disjointness | `task12-collection-06/` | ordinary 3487 nodeids / 183 files, benchmark 585 / 13 files, intersection **0**, ordinary pulls no benchmark file, union 4072, arithmetic 232+3247+8 = 3487 |
| Real (non-symlink) install | `task12-real-build-01/` | exit 0 |
| Copied install | `task12-copied-install-02/` | exit 0, all 9 new modules resolve **inside the copy**, no `.git`, no symlink into the source or build tree, v4 config a real file and it parses from the copy |
| Served bytes | `task12-served-bytes-01/` | exit 0, served index byte-identical (`c09fc43a…`), CSS 28820 B (`80a25e20…`) and JS 1090734 B (`0590ee3b…`) both byte-identical to `web/dist` |
| Web build / unit (separate steps) | `task11-web-build-01/`, `task11-web-unit-01/` | exit 0 / exit 0, **30 files, 126 tests** |

The first copied-install attempt (`task12-copied-install-01/`) is INVALID for a real reason worth
recording: `colcon build --symlink-install` writes a *develop* pythonpath hook pointing at the build
directory, so a copied install is not self-contained by construction. The gate now uses a real
install, and the copy is verified to be free of symlinks.

### Task 13 status: INCOMPLETE, and the honest reason

The first real W2 runtime-shape smoke completed its **start-guard phase** for real:
`start-guard.json` shows `PASS / MPS_HEADROOM_OK`, available 10 783 621 120 bytes (10.04 GiB),
cutoff 1 073 741 824, `admission_kind: unified-memory-proxy`, metric source
`unified-memory-proxy:vm_stat(host_available)+torch.mps.recommended_max_memory@torch2.13.0`.

The **broker phase hangs**. Run under a hard 180 s wall-clock limit it exited 124 with a completely
empty log, so nothing in that phase produced output before the kill; `pgrep` found no orphan
afterwards. One real design constraint was already learned and fixed in the harness: the
accelerator probe imports torch, so the guard must run in its own phase and re-exec into the broker
phase — the same thing the Broker launcher does. The hang is after that re-exec.

No W2 runtime PASS is claimed. Also recorded: the perception weights are not provisioned anywhere
on this host (no `plastic-cup-yolo*`, no `grounded-sam*`, no model root under `$HOME`), so a broker
loading the *real* model set cannot be demonstrated here at all. That is an environment fact, not a
code defect, and it bounds what Task 13 and Task 14 can ever claim on this machine.

_Ledger source HEAD: `0bb4ec74`; no evidence deleted; no Linux or W4/W6/W8 action._

## CP-UQ243 — The W2 runtime shape ran end to end, and the identity race is now fail-closed

```yaml
checkpoint_id: CP-UQ243
last_valid_experiment: EXP-UQ243-TASK13-W2-RUNTIME-SHAPE
current_hypothesis: The two-phase smoke can run the whole exact-W2 runtime shape on this host, and
  the birth-identity read must fail closed rather than promote an unidentifiable child.
working_tree_status: clean at commit 2d93bb42
owned_processes: NONE - every child was reaped; cleanup receipts are complete
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - macOS `read_process_identity()` returns None for the smoke's worker children, so the smoke now
    refuses them by design and the W2 shape gate is INCOMPLETE, not PASS.
  - The identity budget reuses the ACK timeout; it should be its own short bound.
next_command: instrument the identity read during a real spawn to find why macOS returns None
```

`checkpoint_id: CP-UQ243`
`last_valid_experiment: EXP-UQ243-TASK13-W2-RUNTIME-SHAPE`

### The hang is fixed, and the shape ran end to end

The Task 13 hang was a harness defect with a clear cause: the smoke re-executed itself after the
guard phase but re-derived the phase from the environment, so the broker phase landed back in the
guard phase and re-executed forever. Step markers found it in one run. The smoke now names its
phase explicitly, and `task13-w2-runtime-smoke-01/` then completed **all 13 steps**:

```text
guard      : PASS / MPS_HEADROOM_OK, 10.76 GB available, admission_kind unified-memory-proxy
broker     : ready=True, device=mps, models [yolo, grounded-sam] both on mps:0,
             lane {submitted 7, executed 7, rejected 0, peak_depth 1, max_concurrent 1},
             warm-up 0.26 s, receipt written
endpoint   : /private/tmp/so101-ipc-501/b-a0d0967f1bcb/broker.sock, mode 0600, 53 encoded bytes
workers    : two real child processes, both ACTIVE, both reaped
round trips: 6 served requests, every output device mps:0
negatives  : MALFORMED_FRAME, OVERSIZED_FRAME, UNKNOWN_OPERATION, DEADLINE_EXPIRED
cleanup    : complete, directory removed, registry empty, both workers gone
```

That is the exact-W2 runtime shape — one broker, one shared model set, one lane, two workers, two
clients, negative paths, restart-safe cleanup — proven on this host with real MPS.

### A real defect the run exposed, and an honest A/B

The first run recorded `birth_identity: None` for worker `w2` while still reporting it `ACTIVE`.
That is unsafe: `_matches_receipt` can never match an identity-less child, so a later PID-reuse
check is impossible for it. The supervisor now retries the identity read and **fails closed**.

```text
A  task13-identity-ab-01/ (fix in):    INCOMPLETE, w1/w2 FAILED, birth None
   both children still completed 3/3 round trips each; each spawn spent the full 60 s budget
B  task13-identity-ab-02/ (fix out):   PASS, w1/w2 ACTIVE, birth None
conclusion: A is the correct direction and B is the unsafe one. The regression is the fix working.
```

A new, narrower problem is now the top of the queue and is recorded as such: on this host
`read_process_identity()` returns `None` for these macOS worker children even though the same call
succeeds for a plain child spawned the same way, and even though the children are demonstrably
alive and serving requests. Two concrete leads are recorded: the identity budget incorrectly
reuses the ACK timeout instead of having its own short bound, and the one read that did succeed
belonged to the child that was still importing.

`EXP-UQ243`: the runtime shape is proven; the identity-read root cause is **not** confirmed, and no
W2 acceptance is claimed while the smoke refuses its own workers.

_Ledger source HEAD: `2d93bb42`; no evidence deleted; no Linux or W4/W6/W8 action._

## CP-UQ244 — The identity race is intermittent, measured, and still unexplained

```yaml
checkpoint_id: CP-UQ244
last_valid_experiment: EXP-UQ244-TASK13-IDENTITY-RACE
current_hypothesis: The identity read failed because it ran after the ACK wait; moving it to spawn
  time and giving it its own budget fixes it. HALF CONFIRMED: it improves the odds, not the odds to 1.
working_tree_status: clean at commit da182db6
owned_processes: NONE - every child was reaped in every repetition
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - 3 of 5 real W2 runs lost at least one child's birth identity; the W2 shape gate cannot pass
    reliably while that is true, and no W2 acceptance is claimed.
  - The root cause of `read_process_identity() -> None` for a live macOS child is NOT confirmed.
next_command: instrument the reader at the exact moment of a real spawn and log the raw psutil
  result for the child pid (status, create_time, exception type), then decide the fix
```

`checkpoint_id: CP-UQ244`
`last_valid_experiment: EXP-UQ244-TASK13-IDENTITY-RACE`

### What was learned this round

1. **The hang was the harness, and step markers found it immediately.** The smoke re-executed
   itself after the guard phase but re-derived the phase from the environment, so the broker phase
   landed back in the guard phase and re-executed forever. Naming the phase explicitly fixed it,
   and the shape then completed all 13 steps.

2. **The identity race is real, and it is intermittent.** Five independent runs, ten real worker
   spawns:

   ```text
   rep1 PASS       w1 ACTIVE birth=yes   w2 ACTIVE birth=yes
   rep2 INCOMPLETE w1 ACTIVE birth=yes   w2 FAILED birth=no
   rep3 INCOMPLETE w1 ACTIVE birth=yes   w2 FAILED birth=no
   rep4 INCOMPLETE w1 FAILED birth=no    w2 ACTIVE birth=yes
   rep5 PASS       w1 ACTIVE birth=yes   w2 ACTIVE birth=yes
   ```

   Three of five runs were affected. That rules out a deterministic bug in the retry loop: the loop
   runs its full budget and `read_process_identity()` keeps answering `None` for a process that is
   demonstrably alive, because it goes on to complete three real RPC round trips.

3. **Two product changes survived the tests** (`da182db6`, 19 green):
   the identity is now captured **at spawn**, before the ACK wait, and re-checked before promotion
   (a changed or vanished identity is refused); the read has its **own short budget**
   (`identity_timeout_s`, default 2 s) instead of reusing the 60 s ACK timeout; and `spawn` accepts
   an optional **stderr sink**, because a failing child being silent is exactly how this race
   stayed hidden.

4. **A fresh probe run resolved the identity immediately** (`task13-identity-probe-02/`,
   `sleeping`, `create_time 1789828080.713253`), which is why the root cause is still open: the
   same read succeeds outside the smoke and intermittently fails inside it.

No W2 acceptance is claimed. The shape itself has now been observed passing twice, with one
broker, one shared model set, one lane at `max_concurrent` 1, two Workers, six round trips, four
negative protocol paths and complete cleanup.

_Ledger source HEAD: `da182db6`; no evidence deleted; no Linux or W4/W6/W8 action._

## CP-UQ245 — The identity race is solved, 5/5 W2 runs pass, and the model artifacts are absent

```yaml
checkpoint_id: CP-UQ245
last_valid_experiment: EXP-UQ245-TASK13-IDENTITY-ROOT-CAUSE
current_hypothesis: CONFIRMED and CLOSED. The reader never failed; the promotion rule was wrong.
working_tree_status: clean at commit 27625b17
owned_processes: NONE - every child reaped in every run
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - Task 13 cannot be completed on this host: the frozen perception weights are absent and cannot be
    synthesized.
  - Task 14 cannot be started for the same reason plus the missing Linux environment.
next_command: none available on this host for Tasks 13/14; report PARTIAL with LINUX_REGRESSION_DEFERRED
```

### Root cause: confirmed, and it was my rule, not the reader

Instrumenting the reader at the exact spawn moment (`task13-identity-instrumented-01/`, five runs,
~60 recorded reads) settled it beyond doubt:

```text
at spawn      : psutil status "running"/"sleeping", create_time present, reader returns the real
                identity EVERY time (0 construct failures, 0 create_time failures)
at promotion  : psutil status "zombie", reader returns None — because the Worker had already
                finished its three round trips and exited inside the ACK window
```

So `read_process_identity()` was always correct. The defect was **my promotion rule**: it demanded a
*second successful read* and therefore rejected healthy Workers that completed quickly. The rule is
now "refuse only on evidence of PID reuse" — a different identity for the same PID. A departed or
zombie child keeps the spawn-time identity, which is exactly what audit and safe signalling need.

`task13-w2-shape-after-fix-01/`: **five of five real W2 runs pass**, every Worker `ACTIVE` with a
present birth identity, six served round trips, cleanup complete each time.

```text
rep1..rep5: W2_RUNTIME_SHAPE_PASS [('w1','ACTIVE',True), ('w2','ACTIVE',True)] served 6 cleanup True
```

Regression: `task13-fix-regression-01/` exit 0, **197 passed** across supervisor, recovery,
registry, contracts, v4 IPC and Unix address.

### Why Tasks 13 and 14 cannot be finished on this host

Task 13 additionally requires the **real** model set: a Broker that loads and warms up the actual
YOLO and Grounded-SAM models. The perception runtime takes `--yolo-weights` and `--grounded-root`
and verifies them against frozen SHA-256 values
(`f281d252…0781` and `0486be2f…1775`). Measured on this host:

- no `/models`, no `/data/work`, no `$HOME` model root; no `best.pt`, no Grounded-SAM manifest;
- no Docker or Podman, so no image carrying them can be pulled even if one existed;
- `ros2` is not on the PATH (Gazebo `gz` and MuJoCo are present, so the missing piece is the model
  artifacts and the provisioned runtime, not the simulator).

An artifact that must hash to an exact frozen SHA-256 cannot be synthesized or substituted without
falsifying provenance, so this is an irreducible external dependency rather than an engineering
task. The same measured condition has now been recorded across three consecutive rounds:
`CP-UQ242` (35 tests failing with `ModelRuntimeInfrastructureError`), `CP-UQ243` and `CP-UQ244`
(the weights absent), and this checkpoint.

Task 14 adds five consecutive `FULL_RESTART` W2 **simulation** batches with independent Gazebo and
MoveIt physics evidence. Each batch needs the real perception models and the full simulation stack,
so it inherits the same blocker.

_Ledger source HEAD: `27625b17`; no evidence deleted; no Linux or W4/W6/W8 action._

## CP-UQ246 — The artifacts have a canonical home, and a second real blocker was fixed

```yaml
checkpoint_id: CP-UQ246
last_valid_experiment: EXP-UQ246-ARTIFACT-PROVENANCE
current_hypothesis: The artifacts can be fetched rather than invented. CONFIRMED as the route;
  BLOCKED on the source host being offline.
working_tree_status: clean at commit 0cd645ba
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService; ai-station was not modified in any way (read-only reachability check only)
open_risks:
  - ai-station is offline in the tailnet (last seen 7h ago), so the fetch cannot run yet.
  - macbook-air is an active peer but unreachable (host key verification failed), so it is not a
    fallback source without the operator adding its key.
next_command: zsh impl-macos-mps-w2-01/fetch-model-artifacts.zsh  (once ai-station is online)
```

### The artifacts have exact, recorded provenance

Grepping the retained ledgers for the two frozen digests found the canonical command that
originally provisioned them, which names both paths explicitly:

```text
weights    : /data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/20260902-ab-v1/assets-r8/best.pt
             sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
model root : /data/work/so101-models/grounded-sam-v2-scipy-lock
             manifest sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
source     : docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md line 2755
```

So the correct action is a verified **fetch** from ai-station, never a synthesis. A task-local
script now does exactly that, fail-closed: `impl-macos-mps-w2-01/fetch-model-artifacts.zsh`. It
refuses to install anything whose SHA-256 does not match, modifies nothing on the remote host, and
writes a receipt. Both of its states are exercised:

- `--check-only` on the real state reports both artifacts MISSING, exit 1;
- with a decoy installed, it reports `VERDICT: MISMATCH - frozen value is f281d252…0781`, exit 1.

### Why it cannot run yet

`ssh ai-station` times out (exit 255). The tailnet explains it: `ai-station-001-lin` is
`offline, last seen 7h ago`. This Mac's own tailnet egress is fine (`github.com -> 200`), and
`tailscale status` shows the Mac and `macbook-air` active, so the failure is the peer being down,
not the network path. `macbook-air` refuses with host key verification failure, so it is not a
fallback without the operator adding its key. Local capacity is sufficient: 146 GB free.

### A second, independent real defect found and fixed while checking this

Checking whether the Broker could even *use* MPS revealed a real product bug: the broker CLI
accepted `--device`, but `frozen_options()` hard-coded `requested_device='cuda'` and threw the
parsed value away. On the schema-v4 macOS combination that made the real model set unloadable even
though every layer above the Broker resolved to MPS. The device layer already supported MPS
(`select_runtime_device` handles `"mps"`, and the detector factory validates the closed set
`auto|cuda|mps|cpu`); only the wiring was missing.

Fixed in `0cd645ba`: `frozen_options(..., requested_device='cuda')` keeps every schema-v3 caller
byte-identical, the broker passes the parsed device through, and the CLI constrains `--device` to
the factory's closed set instead of a single frozen literal. Five new tests cover the default,
MPS without CPU fallback, refusal of an unsupported device, agreement with the factory's set, and
the Linux container argv still choosing CUDA. Regression evidence:
`task13-device-regression-01/` shows the failure counts for the three affected files are
**identical before and after** (28 CLI, 69 perception-runtime), so nothing regressed; the five new
tests are the delta.

_Ledger source HEAD: `0cd645ba`; no evidence deleted; ai-station untouched._

## CP-UQ247 — The model blocker is gone: the real published set runs exact W2 on MPS

```yaml
checkpoint_id: CP-UQ247
last_valid_experiment: EXP-UQ247-TASK13-REAL-MODELS-W2
current_hypothesis: CONFIRMED. With the published artifacts and the corrected device wiring, the
  real Broker loads both real models on MPS and serves two real Workers.
working_tree_status: clean at commit 1d09bc87
owned_processes: NONE - both Workers reaped, endpoint unlinked, campaign directory removed
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - The environment change (6 pip packages) and the digest re-freeze are recorded below; both are
    reversible and neither touched the user's global configuration.
  - Task 14 (five FULL_RESTART simulation batches) still needs the Gazebo/MoveIt side, unstarted.
next_command: Task 14 - first FULL_RESTART W2 simulation batch
```

`checkpoint_id: CP-UQ247`
`last_valid_experiment: EXP-UQ247-TASK13-REAL-MODELS-W2`

### Where the artifacts come from, and what I verified

The user supplied two Hugging Face repositories. Both digests are now checked against published
bytes rather than assumed:

- **YOLO weights**, public repo `zjumty/so101-yolo11n-seg-plastic-cup`: `best.pt` hashes to
  `f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781` — exactly the frozen value.
- **Grounded SAM bundle**, private repo `zjumty/so101-grounded-sam-cup-pickplace`: `bundle/` is the
  model root; all 11 files match the digests inside `bundle/manifest.json`, and that manifest
  matches the repo's own `SHA256SUMS`.

Two environment quirks were worked around **per-command only**: `~/.local/bin` is not on this
session's PATH, and `NO_PROXY` ends with `[::1]`, which httpx parses as a URL and crashes on. No
global configuration was changed.

### The digest mismatch, and the re-freeze (commit `1d09bc87`)

The published manifest is `b55bb601…`; the code froze `0486be2f…`. The distinction matters: the
Hub manifest is canonically encoded exactly as `verify_model_bundle` requires, and its
`threshold-lock.json` hashes to `b02e3be2…` — the pair that
`docs/reports/grounded-sam-yolo-seg-benchmark-report.md:5` already calls the frozen production
candidate. The report also still carries `0486be2f…` at line 125, so the repo disagreed with
itself. Per the user's decision the contract now names the published bundle:

- `_FROZEN_GROUNDED_SAM_MANIFEST_SHA256` in `parallel_batch/contracts.py` (both v3 and v4 inherit it)
- `src/cli/perception_benchmark.py`, `config/perception_benchmark/benchmark.yaml`
- the three `grounding_dino_*_training.yaml` configs
- the four test files that pin the literal

Three new tests pin both digests, the config copies, and assert the retired digest appears in no
shipped config. Regression: failure counts for the affected files are **identical before and after**
(28 cli / 45 resources / 16 ipc), so nothing regressed.

### The real model set on MPS, measured

`refreeze-real-groundedsam-load-01/` and `refreeze-real-yolo-load-02/`: both detectors build through
the production factory on MPS with CPU fallback disabled.

```text
grounded-sam : LOADED, runtime_device mps, 203M parameters, both modules on mps:0, 6.03 s
yolo         : LOADED, runtime_device mps, 2.83M parameters on mps:0, 26.8 s cold start
```

### Exact W2 with the real published models — `task13-w2-real-models-01/`

```text
status    : W2_REAL_MODELS_PASS
guard     : PASS / MPS_HEADROOM_OK, unified-memory-proxy, 12.35 GB available
broker    : ready, device mps, models [yolo, grounded-sam], both on mps:0, warm-up 7.03 s
lane      : submitted 13, executed 13, rejected 0, peak_depth 1, max_concurrent 1
workers   : w1 and w2 both ACTIVE, both with real birth identities, both reaped
served    : 6 round trips, every response device "mps"
negatives : MALFORMED_FRAME, OVERSIZED_FRAME, UNKNOWN_OPERATION, DEADLINE_EXPIRED
cleanup   : complete, directory removed, registry empty, both workers gone
```

Two product bugs were found and fixed on the way, both of which would have blocked a real macOS
campaign:

1. the broker CLI accepted `--device` but `frozen_options()` hard-coded CUDA and discarded it, so
   the real model set could never load on Apple silicon (commit `0cd645ba`);
2. the supervisor promoted children whose birth identity could not be read, and then — after the
   first fix — rejected healthy short-lived children by demanding a *second* successful read. The
   rule is now "refuse only on evidence of PID reuse", measured across five consecutive passing
   runs (commits `2d93bb42`, `27625b17`).

### The environment change, recorded

`ultralytics==8.4.115` plus 5 dependencies were installed into `~/ros2_jazzy/.venv` with the user's
explicit approval. The before/after freeze is retained: **161 → 167 packages**, the six additions
listed, and no upgrade or downgrade of torch, torchvision or numpy.

_Ledger source HEAD: `1d09bc87`; no evidence deleted._

## CP-UQ248 — The missing composition now exists, and a flaky gate is deterministic

```yaml
checkpoint_id: CP-UQ248
last_valid_experiment: EXP-UQ248-COMPOSED-MACOS-W2
current_hypothesis: The v4 pieces are complete but unwired; the composition is the missing layer
  between the tested libraries and a runnable macOS campaign. CONFIRMED.
working_tree_status: clean at commit 10175636
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - The composition is not yet driven by a CLI entry point, and Task 14's simulation batches need a
    full ROS/MoveIt/Gazebo launch path that does not exist for the v4 configuration yet.
next_command: wire the composed campaign behind a CLI entry point, then attempt a first FULL_RESTART
```

### The gap this round found

Grepping for production callers showed that **every v4 component is reachable only from tests**:
`MpsBrokerBootstrap`, `CampaignSupervisor`, `parallel_ipc_v4`, `unix_address` and the rest have no
caller in `src/` outside their own modules. The plan's task file lists name the wiring points
(`runtime/parallel_ros_runtime.py`, `runtime/parallel_worker_runtime.py`,
`cli/mujoco_parallel_batch.py`) and those files are unmodified — the plan's Task 13 assumes a
composed runtime that Tasks 2–10 were each supposed to build a piece of, and nothing owned the
join. That is why my Task 13 smoke had to hand-assemble its own sequence, and it is why Task 14
cannot start yet.

`parallel_batch/macos_w2_campaign.py` is that join (`2b9320e5`). It composes the supervisor, the
MPS broker, the private address strategy, the permission-only v4 RPC, the immutable snapshots, the
one-time registry and the seven-step recovery, with every platform-specific port injected so the
Linux path stays untouched. It refuses at construction if the plan is not the Darwin MPS
combination, if the slot count is not exactly two, or if the plan mixes platforms.

A malformed `remove_active_request` lambda in my first draft was caught by the syntax check and
replaced with a proper `InferenceRegistry.cancel_request_safe` that answers yes/no instead of
raising — the recovery path needs to ask "is this still ours to remove?" without treating an
already-terminal request as an error.

`composed-campaign-01/`: **12 passed**, covering a clean-host pre-flight, a claim or leftover
campaign directory making it dirty, the three construction refusals, one-time admission (admitted
once, refused on repeat, refused from a replaced broker identity, refused when unknown), the closed
rebuild trace starting at `remove_active_request` and ending at `coordinator_decision`, released
snapshots still on disk as deletion candidates, and the infrastructure disposition carrying
`business_status: None`.

### A flaky gate, fixed rather than tolerated

`test_a_full_bounded_queue_refuses_excess_work_and_keeps_serving` failed in the composition
regression but had passed earlier: re-running it alone gave pass/pass/fail. The cause is structural
— the accept loop drains the queue as fast as a burst fills it, so "the queue is full right now" is
a race window, and a first fix (a longer burst) still failed 2 of 5. The test now makes the queue
genuinely full for the duration of one connection and asserts the accept loop answers rather than
drops. `v4-queue-det-01/` … `-05/`: **5 of 5 passing**.

`composed-regression-02/`: **283 passed, 0 failed** across composition, registry, snapshots,
recovery, supervisor, v4 IPC, Unix address, MPS bootstrap, W2 composition and contracts.

_Ledger source HEAD: `10175636`; no evidence deleted._

## CP-UQ249 — The macOS W2 campaign now runs from a production entry point

```yaml
checkpoint_id: CP-UQ249
last_valid_experiment: EXP-UQ249-MACOS-W2-ENTRYPOINT
current_hypothesis: CONFIRMED. The composition plus a two-phase launcher turns the v4 contract into
  a runnable campaign, and the one-time table is the gate that proves it.
working_tree_status: clean at commit c1756cb6
owned_processes: NONE - both workers reaped, endpoint unlinked, campaign directory removed
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome extension host, Sparkle updater,
  SkyComputerUseService
open_risks:
  - Task 14's five FULL_RESTART *simulation* batches still need MoveIt shadow, controller/joint
    state and MuJoCo pose/contact evidence; the controller stack present on this host is built
    from the canonical checkout, not from this worktree.
next_command: decide whether the canonical controller stack can be used as-is for Task 14 or must
  first be rebuilt from this worktree
```

`EXP-UQ249-MACOS-W2-ENTRYPOINT: VALID`

### What was missing, and what now exists

`mujoco_parallel_batch` is the Linux container path and requires `--broker-image`, a CUDA device
and `proc_fd_unix`; there was no way to *run* a v4 macOS campaign. Two new modules close that
(`c1756cb6`):

- `cli/macos_w2_campaign.py` — the launcher: inventory, config, plan, start guard, claim, broker,
  endpoint, two workers, one-time admission, cleanup;
- `cli/macos_w2_worker.py` — one Worker: registered ACK first, then three round trips.

### Three real defects the run exposed, in order

1. **The guard and the broker cannot share an interpreter.** The probe imports `torch.mps`; the
   bootstrap requires torch to be unimported when it pins `PYTORCH_ENABLE_MPS_FALLBACK`. The
   launcher now runs the guard as its own phase, writes `start-guard.json`, and hands over with
   `execve` — the same shape the verified Task 13 smoke uses.
2. **The warm-up input shape.** The bootstrap's default warm-up is a `(N, C, H, W)` tensor while
   `DetectionFrame` requires `(H, W, 3)` uint8. Handled by an explicit `_as_rgb8` coercion rather
   than by loosening the frame contract.
3. **The one-time table refused all six responses.** The first full run reached `served 6` with both
   Workers `ACTIVE`, and admission reported `REQUEST_UNKNOWN` for every id, so nothing was admitted
   and the run correctly reported `INCOMPLETE` instead of passing. The gate was right: the launcher
   never bound the requests. It now binds each id before it is served, and an unbound id would still
   be refused.

That third one is the most useful result of the round: the design's central safety property —
"only a result the Coordinator bound in advance can be used" — was demonstrated failing closed on a
real omission in my own code, not in a unit test.

### The campaign, run for real through the entry point

`task14-campaign-batch02/`:

```text
status    : W2_CAMPAIGN_PASS
guard     : PASS / MPS_HEADROOM_OK, unified-memory-proxy, 11.38 GB available
broker    : ready, device mps, models [yolo, grounded-sam]
            model devices [mps:0, mps:0], parameter devices [['mps:0'], ['mps:0']]
            warm-up 7.81 s, lane {submitted 7, executed 7, rejected 0, max_concurrent 1}
workers   : w1 on slot-0 and w2 on slot-1, both ACTIVE with real birth identities, both reaped
served    : 6 round trips, all device "mps", lane executed 13, max_concurrent still 1
admission : 6 admitted, 0 refused
cleanup   : complete, directory removed, registry empty, both workers gone
```

Regression: `entrypoint-regression-01/` exit 0, **177 passed**.

_Ledger source HEAD: `c1756cb6`; no evidence deleted._

## CP-UQ250 — The real macOS station now runs from this branch, and GUI capture is the wall

```yaml
checkpoint_id: CP-UQ250
last_valid_experiment: EXP-UQ250-MACOS-STATION-AND-BATCH
current_hypothesis: The Task 14 simulation half needs the real ROS/MoveIt/MuJoCo station. That
  station now boots and executes real pick-place from THIS worktree's own install; the plan's
  fresh-GUI evidence requirement is blocked by macOS TCC for this executor's process chain.
working_tree_status: clean at commit 90abe596
owned_processes: NONE - the batch's own supervisor cleaned up every station child; three orphans
  from my hand-rolled smoke runner were reaped by exact PID and are recorded as a runner defect
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - GUI capture is unavailable to this session: Accessibility and Screen Recording are both denied
    to the responsibility chain (tmux under launchd), so no `viewer.png` can be produced and every
    point fails TERMINAL_CAPTURE_FAILED. Task 14 cannot claim a batch until the user grants both.
  - The Worker runtime still has no Darwin station config: `headless_task_station_config` is the
    only station command and the task station itself refuses `headless:=true` on Darwin.
  - The product's window filter requires "mujoco" in the window title, and CoreGraphics reports an
    empty title for every window on this host; that filter is unverifiable until permission exists.
next_command: ask the user to grant Accessibility + Screen & System Audio Recording to the
  responsible binary, then re-run the capture probe before touching Task 14 again
```

`EXP-UQ250-MACOS-STATION-AND-BATCH: INVALID` — the batch fails closed on missing GUI capture, so it
counts for nothing. What follows is what was actually proven and what was actually blocked.

### The branch can build and run its own station

`station-build-01/` builds seven packages from this worktree into a task-owned install in **1 min
3 s**: `mujoco_ros2_control_msgs`, `mujoco_3d_lidar`, `mujoco_ros2_control_plugins` (from the pinned
`third_party/mujoco_ros2_control` submodule `e4c0241a`), `mujoco_ros2_control`,
`so101_mujoco_support`, `so101_demo_py`, `so101_teleop`. Recorded deviation: `-DBUILD_TESTING=OFF`,
which removes test binaries only. The canonical checkout's install is never sourced; the station
prints its own prefix in every log line, and `graceful_shutdown_move_group` only exists in the
worktree build — the canonical `so101_isolated_ws` install still ships the pre-rename
`so101_move_group`, which is exactly the stale-binary trap the `so101-dev` skill warns about.

`task14-station-smoke-02/`: the real GUI station reaches the ready contract from that install —
`ready: true`, phase `READY`, `arm_controller`/`gripper_controller`/`joint_state_broadcaster` all
`active`, `/apply_planning_scene`, `/get_planning_scene`, `/plan_kinematic_path` present, and
`scene_setup` reading back `pedestal`, `plastic_cup`, `table` from the canonical scene.

One harness mistake is kept in the record: `task14-station-smoke-01/` used
`so101_mujoco.launch.py run_mode:=dry_run`, which is **log-messages-only** when
`pick_place=False` — it launched no node, exited 0, and the readiness probe then failed with
`MOTION_STACK_CONTROLLER_NOT_ACTIVE`. Exit 0 from a launch that starts nothing is not readiness.

### A real four-point pick-place ran, and failed only on the screenshot

`task14-single-batch-01/` runs the production runner `so101_mujoco_rgbd_batch` (own station, ordered
point list, per-point evidence) from this branch's install: 350 s, exit 1. Every point executed
real physics and real manipulation:

```text
point                     state  failure  sim_step  table_contact  max_normal_force_n  perception
01-task_start             DONE   None     33644     True           0.2329              OK, cup 141 pts
02-cup_test_forward_5cm   DONE   None     36463     True           0.2331              OK, cup 168 pts
03-cup_test_left_5cm      DONE   None     31921     True           0.2328              OK, cup 378 pts
04-cup_test_right_5cm     DONE   None     33155     True           0.2330              OK, cup 126 pts
```

MoveIt planned and the controllers executed seven trajectories per point
(`arm_controller started execution` → `successfully finished`), the RGB-D chain returned
`cup_pose_position_xyz` within 0.6 mm of the declared 5 cm offsets, and the fitted cup radius was
0.0394 m against an expected 0.040 m. All four points then failed with
`TERMINAL_CAPTURE_FAILED`: point status `FAILED`, batch status `FAILED`.

Cleanup after the batch was **complete** — no `ros2_control_node`, `move_group`,
`robot_state_publisher` or `spawner` survived — which is the product's `OwnedProcessGroup` doing
what my own smoke runner failed to do (that runner left three children reparented to PID 1; they
were reaped by exact PID after confirming their parent was gone).

### The wall, measured rather than assumed

The product captures the viewer through `MacViewerCapture`: a Swift window inventory for the MuJoCo
owner PID, then `screencapture -x -l <window_id>`. Probed directly while the station was live:

```text
swift list_windows.swift 1851   -> [{"owner_pid":1851,"title":"","window_id":3635,"onscreen":true}]
screencapture -x -l 3635 out.png -> rc 1 "could not create image from window"
screencapture -x desktop.png     -> rc 1 "could not create image from display"
osascript AX probe               -> "osascript is not allowed assistive access" (-25211)
```

Both Accessibility and Screen Recording are denied to this executor's responsibility chain
(`bash <- node <- node <- dsh <- zsh <- tmux <- launchd`). This is a TCC boundary on the machine, not
a defect in the branch, and it cannot be worked around from inside the session: the plan requires
fresh GUI evidence via the project `gui-capture` skill, and that skill's macOS path needs exactly
these two permissions. Note also that the CoreGraphics inventory reports an empty title for *every*
window here — Chrome and Ghostty included — so `MacViewerCapture`'s `"mujoco" in title` filter is
untestable until permission exists and may need re-validation afterwards.

Consequence for the plan: Task 14's five `FULL_RESTART` batches are **not started**, no batch is
counted, and `MACOS_MPS_W2_PASS` remains unwritten. `LINUX_REGRESSION_DEFERRED` is retained; no
Linux gate was run or reported as PASS/SKIP/N/A.

_Ledger source HEAD: `90abe596`; no evidence deleted._

### CP-UQ250 addendum — owned-process readback, and the permission grant measured again

Four orphaned fixtures from my own earlier teleop gates (`task11-teleop-full-01`,
`task11-teleop-ab-01`: two `descendant_helper.py`, two `process_tree_helper.py --mode runner`, all
reparented to PID 1 between 21:51 and 21:55) were reaped by exact PID after their run roots were
matched to this task's evidence root. Readback afterwards: no `descendant_helper`,
`process_tree_helper`, `mujoco_ros2_control`, `move_group`, `ros2_control_node`, `rgbd_cup_pose` or
`ros2 launch` process remains.

After the user granted permissions, the probes changed but not enough:

```text
Accessibility     : GRANTED  - System Events now answers with a live process list; the earlier
                               -25211 "osascript is not allowed assistive access" is gone
Screen Recording  : DENIED   - screencapture -x still exits 1 with "could not create image from
                               display"
tmux server       : pid 59433, started Sat Sep 19 21:13:49 2026 - unchanged, so the grant has not
                               been picked up by a new responsible process
```

macOS evaluates Screen Recording per responsibility chain and caches it for the life of the
process, so `/opt/homebrew/bin/tmux` (code identity
`tmux-55554944a40667abf836332cab24562eec45b0ba`, no TeamIdentifier) must be both **enabled** in
System Settings and then **restarted** before the capture path can work. Task 14 stays blocked on
that single, non-code condition; nothing about the Station, the MPS Broker or the W2 contract is
blocking it.

_Ledger source HEAD: `2809052b`; no evidence deleted._

## CP-UQ251 — The macOS Worker can now own a station, and one pre-existing failure is pinned

```yaml
checkpoint_id: CP-UQ251
last_valid_experiment: EXP-UQ251-DARWIN-STATION-CONFIG
current_hypothesis: The plan's Task 9/10 boundary never handled Darwin's station shape, so a
  parallel macOS Worker could not start a station at all. CONFIRMED, and fixed.
working_tree_status: clean at commit ce35a07b
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - Screen Recording is still denied to this session's responsibility chain, so Task 14's fresh GUI
    evidence and the per-point viewer capture remain blocked (CP-UQ250 addendum).
  - The macOS W2 simulation composition (two visible stations sharing one MPS Broker, driven
    through the Coordinator) does not exist yet; the station config is only its first prerequisite.
next_command: compose the macOS W2 simulation path on top of task_station_config
```

`EXP-UQ251-DARWIN-STATION-CONFIG: VALID`

### The defect, and why it belonged to Task 9/10

`RosWorkerRuntime.start_physical_runtime` called `headless_task_station_config(resources)`
unconditionally, and that function's docstring says what it is: *"the single supported Linux
headless Worker launch command"*. On Darwin the station launcher refuses `headless:=true` outright
(`macOS task station requires headless=false`, `runtime/launch_composition.py`), so the macOS Worker
path could never start. That is a genuine gap in the owning task's boundary, not a Task 14 harness
problem, so it was fixed there.

`task_station_config(resources, *, platform=None)` now resolves the shape per platform:

- `linux` → the frozen `headless_task_station_config` object, unchanged;
- `darwin` → the same station with `headless:=false`, `sensor_rendering:=true`,
  `include_teleop:=false`, the Worker's `session_id` and `task_evidence_root`;
- anything else → `unsupported task station platform: <name>`, fail closed.

`ParallelWorkerRuntime` takes the same decision as a port (`station_config`, defaulting to the new
resolver), so tests inject a station shape instead of monkeypatching the host platform.

### RED → GREEN → regression

```text
task14-darwin-station-red-01   3 failed  ImportError: cannot import name 'task_station_config'
task14-darwin-station-green-03 3 passed  (-k station_config)
task14-darwin-station-regression-01  117 passed, 1 failed
```

The single regression failure,
`test_parallel_ros_runtime.py::test_consumer_readiness_primes_and_retains_isolated_pose_publisher`,
is **pre-existing**: `task14-darwin-station-ab-01` runs it with this change stashed and it fails
identically at `parallel_ros_runtime.py:1717`. It is not caused by this commit and is not counted as
a regression. One gate attempt is recorded as invalid rather than hidden: pointing
`GATE_INSTALL_OVERLAY` at the station install breaks unit collection
(`ModuleNotFoundError: No module named 'so101_mujoco_support'`), so the unit gates keep using the
task-owned branch install.

_Ledger source HEAD: `ce35a07b`; no evidence deleted._

## CP-UQ252 — The product's own station ownership works on macOS, with no orphans

```yaml
checkpoint_id: CP-UQ252
last_valid_experiment: EXP-UQ252-OWNED-DARWIN-STATION
current_hypothesis: The stack that the W2 simulation driver will own per slot must start and stop a
  visible macOS station by itself. CONFIRMED in product code.
working_tree_status: clean at commit 1262638b
owned_processes: NONE - the stack's own shutdown left no process behind
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - Screen Recording is still denied to this session's responsibility chain (tmux pid 59433 has not
    been restarted), so per-point GUI capture and Task 14's batches remain blocked.
  - The macOS W2 simulation composition above this stack is still unwritten.
next_command: compose two owned stations plus the shared MPS Broker behind the Coordinator
```

`EXP-UQ252-OWNED-DARWIN-STATION: VALID`

`task14-owned-station-01/` starts the station through `PersistentTaskStack` +
`default_task_station_config` — the same ownership the parallel Worker runtime uses — from this
branch's install and measures both ends:

```text
argv            : ros2 launch so101_demo_py so101_mujoco_task_station.launch.py
                  headless:=false session_id:=task14-owned-station-01
                  task_evidence_root:=<run>/station include_teleop:=false
config_headless : false
ros2_control_node pid resolved : 3608   (startup_s 0.87)
ready           : ready=true, phase READY, arm/gripper/joint_state all active,
                  /apply_planning_scene /get_planning_scene /plan_kinematic_path present
shutdown        : 0.28 s, still_running=false
orphans after   : none - ros2_control_node, move_group, robot_state_publisher, spawner all gone
```

That is the concrete difference from my first hand-rolled runner, which left three children
reparented to PID 1: ownership belongs to `OwnedProcessGroup`, and now it is exercised on Darwin.
`graceful_shutdown_move_group` also reports `GRACEFUL_SHUTDOWN_MOVE_GROUP_OK` on the way out, and the
scene, camera plugin, MuJoCo physics thread and evidence plugin all initialise from this branch's
build.

Nothing here counts as a Task 14 batch: no pick-place ran, no GUI capture was taken, and Task 14
remains 0/5. `LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: `1262638b`; no evidence deleted._

### CP-UQ252 addendum — the v4 suites and the entry point are unaffected

`entrypoint-regression-02/` re-runs the exact V4 suite set after `ce35a07b` (the Darwin station
config) and reports **177 passed**, identical to `entrypoint-regression-01/` before it: the campaign
entry point, inference registry, permission-only IPC, W2 composition and the frozen v3/v4 contract
tests all still pass. Screen Recording was probed once more at the same time and is still denied to
this session (`screencapture -x` → "could not create image from display", tmux server pid 59433
unrestarted), so Task 14's batches stay blocked on that single external condition.

_Ledger source HEAD: `908a1b82`; no evidence deleted._

## CP-UQ253 — The macOS W2 simulation join, written down before it is written

```yaml
checkpoint_id: CP-UQ253
last_valid_experiment: none - this checkpoint is a wiring map, not a run
current_hypothesis: Task 14's blocker is one missing join, not one missing subsystem. The parts
  exist and are separately verified; nothing yet composes them into a W2 simulation batch.
working_tree_status: clean at commit c50f8830
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - Screen Recording is still denied to this session (tmux pid 59433 unrestarted): per-point viewer
    capture and therefore any counted Task 14 batch remain blocked.
  - The join below is design, not evidence. It is recorded so the next round starts from a map
    instead of re-deriving it.
next_command: implement the macOS W2 simulation join in the order listed below
```

### What already exists, and where

| Piece | Where | Verified by |
| --- | --- | --- |
| Exact-W2 plan + slot/point assignment | `parallel_batch/w2_composition.py` | `test_w2_composition.py` |
| Campaign supervision, durable claim, SPAWNING/ACTIVE receipts | `parallel_batch/campaign_supervisor.py` | Task 13 smokes |
| Local MPS Broker + single lane + ready receipt | `runtime/mps_broker_bootstrap.py` | `task13-w2-real-models-03`, `task14-campaign-batch02` |
| Permission-only v4 IPC (dirfd-free, `0600`/`0700`) | `runtime/unix_address.py`, `runtime/parallel_ipc_v4.py` | `test_parallel_ipc_v4.py` |
| One-time request register/consume/cancel | `parallel_batch/inference_registry.py` | `test_inference_registry.py` |
| Per-slot station ownership (now GUI on Darwin) | `runtime/task_stack.py`, `parallel_worker_runtime.task_station_config` | `task14-owned-station-01`, CP-UQ251 |
| Lease lifecycle + real ROS ports for one Worker | `parallel_batch/worker.py`, `runtime/parallel_ros_runtime.py` | `test_parallel_worker_runtime.py` |
| Whole-point pick-place with physical evidence | `application/task_batch.py` + `runtime/task_batch_runtime.py` | `task14-single-batch-01` |

### What is missing: one composition, in this order

1. **Resources.** Allocate two `WorkerResources` from `parallel_batch/resources.py`
   (`AllocationPolicy(config.max_worker_count, config.ros_domain_ids)` → domains 181/182, one
   worker root each). The allocator already carries the Darwin paths.
2. **Broker.** Start the Broker through `CampaignSupervisor` with the MPS bootstrap command instead
   of the container argv. The CLI's `_broker_command_builder` hook is the shape to copy; the
   container branch must stay untouched for v3.
3. **Station per slot.** Two `ParallelWorkerRuntime`s built with the new
   `task_station_config` port, each owning a visible station on its own domain. No shared station,
   no shared domain.
4. **Broker proxy per slot.** A v4 IPC client implementing what `_WorkerBrokerProxy` implements and
   `parallel_ros_runtime` expects: `request_model`, `cancel_generation`, `_refresh_broker`, plus the
   coordinator-side `authorize_local` binding. Inference must go over the private socket and the
   result must pass the Coordinator's one-time consume before any RGB-D/TF/pose admission.
5. **Batch loop.** Drive `BatchCoordinator` + `ParallelWorker` for one point per slot, with a fresh
   coordinator epoch, a fresh campaign IPC path and a fresh Broker generation per `FULL_RESTART`
   batch, over five consecutive batches.
6. **Evidence per batch.** MoveIt shadow divergence, controller/joint state, MuJoCo pose/contact/
   detach/release, final placement, both slots' progress/result/evidence, shared-Broker readback,
   GUI snapshot/action/snapshot, and exact cleanup.

Items 1–4 are code; item 5 is the five-batch loop; item 6 needs Screen Recording. Landing 1–4 is
useful even before the permission gap closes, because every unit of it is testable without a
camera — but no batch may be counted until item 6 is real.

_Ledger source HEAD: `c50f8830`; no evidence deleted._

## CP-UQ254 — Step 1 of the join is blocked by a real v4 inconsistency

```yaml
checkpoint_id: CP-UQ254
last_valid_experiment: EXP-UQ254-W2-RESOURCE-RED (RED, not a pass)
current_hypothesis: Allocating exact W2 from the v4 document works. DISPROVEN.
working_tree_status: clean at commit b9b2f39a
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - The v4 document claims an exact-W2 platform but still carries v3's `max_worker_count: 8`
    against only two `ros_domain_ids`, so `AllocationPolicy` refuses before any Worker can exist.
  - Screen Recording is still denied to this session, so Task 14 batches stay blocked too.
next_command: decide the v4 fix (document max_worker_count or allocator derivation), write the RED
  test in the owning contract test file, then green it
```

### The failure

`task14-w2-resources-red-01/` loads the v4 document with the shipped loader and allocates two
Workers. `load_execution_config` resolves it correctly (`ParallelRuntimeConfigV4`, `worker_count 2`,
`ros_domain_ids [181, 182]`), and then:

```text
ResourceAllocationError: ALLOCATION_POLICY_ROS_DOMAIN_IDS
  resources.py:185 in AllocationPolicy.__post_init__
```

The cause is inside my own Task 10 document, not in the allocator's rule. The rule requires
`len(ros_domain_ids) >= max_worker_count`; the v4 YAML declares `max_worker_count: 8` (inherited from
the v3 document) with only two domains. `WorkerResourceAllocator.__init__` builds exactly that policy
when the caller does not supply one (`resources.py:987`), so **no Worker can be allocated from the
macOS v4 configuration at all** — map step 1 of CP-UQ253 cannot proceed until this is fixed.

This is what the plan's "each task returns genuine defects to its owning task" rule exists for: the
defect belongs to Task 10 (composition/resolved manifest), and Task 14 is simply the first caller
that allocates resources instead of describing them.

`EXP-UQ254-W2-RESOURCE-RED: RED` — recorded as a failure, never as a pass. No batch counts, and Task
14 remains 0/5 with `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `b9b2f39a`; no evidence deleted._

## CP-UQ255 — The allocation RED is green up to the start guard, without touching the v3 freeze

```yaml
checkpoint_id: CP-UQ255
last_valid_experiment: EXP-UQ255-W2-RESOURCE-GREEN
current_hypothesis: The v4 resource RED (CP-UQ254) is an allocator gap, not a document error.
  CONFIRMED, with one wrong first fix caught by a tested invariant.
working_tree_status: clean after the scoped commit below
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - Allocation still requires a composed start guard; the probe deliberately supplies none, so the
    next step is to compose the Darwin MPS guard exactly as the campaign entry point does.
  - Screen Recording is still denied to this session, so Task 14 batches remain blocked.
next_command: compose the start guard for the v4 allocation and confirm the two resolved Workers
```

### The first fix was wrong, and the tests said so

My first attempt edited the *document* and the v4 frozen map so `max_worker_count` would read 2.
`test_schema_v4_keeps_the_v3_runtime_values_frozen` failed on exactly that: for every name shared
between the v3 and v4 frozen maps the values must be identical, i.e. v4 reuses v3's frozen values
rather than redefining them. Rewriting that assertion would have been "change the test until it
passes", which the plan forbids, so the change was reverted instead: **the frozen v3 field stays
8**, and the v4 platform ceiling comes from the field v4 actually owns — `worker_count`, whose
frozen v4 value is the exact-W2 claim.

### The real defect

`WorkerResourceAllocator` refused `ParallelRuntimeConfigV4` outright (`ResourceAllocationError:
CONFIG`) because its accepted-type tuple predated schema v4, and its derived `AllocationPolicy` used
the frozen `max_worker_count` (8) against two `ros_domain_ids`, which `AllocationPolicy` rejects
(`len(domains) >= max_worker_count`). Either one alone makes every v4 allocation impossible; both
were latent because every earlier v4 caller *described* resources instead of allocating them.

The fix is scoped to `resources.py`: accept v4, treat it as the v3-shaped field set for the
allocation branch, report schema 4 in the manifest document, and derive the policy ceiling from
`config.worker_count` for v4 only.

### Evidence

```text
task14-w2-resources-red-01    ALLOCATION_POLICY_ROS_DOMAIN_IDS      (before)
task14-w2-resources-green-02  ContractError FROZEN_RUNTIME_VALUE    (wrong first fix)
task14-w2-resources-green-05  ResourceAllocationError START_GUARD_UNAVAILABLE  (policy now passes)
entrypoint-regression-04      177 passed  (the frozen-value invariant is green again)
task14-w2-resources-ab-01/02  45 failed, 47 passed with AND without the change -> the resources
                              suite's failures are pre-existing in this environment, not a
                              regression from this commit
```

`EXP-UQ255-W2-RESOURCE-GREEN: VALID` for the allocator scope only. No Worker has started, no batch
ran, Task 14 stays 0/5, and `LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: (parent of this commit); no evidence deleted._

### CP-UQ255 addendum — the third v3-only gate in the same allocation path

Continuing the probe with a composed guard (`EpochStartGuard` via
`compose_default_start_guard(config.start_guard)`) and the registered task root exported, the next
gate appears at `resources.py:1377`:

```text
task14-w2-resources-green-06  CoordinatorError PROBE_STATE_ROOT_UNSET: SO101_TASK_ROOT
                              (the guard fails closed without the registered root - correct)
task14-w2-resources-green-07  ResourceAllocationError CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION
                              resources.py:1379  ->  `device = getattr(config, 'gpu_device', None)`
```

`_start_guard_check` builds its `GuardScope` device from `config.gpu_device`, which is exactly the
v3/CUDA field v4 replaces with `accelerator` (`mps` + `default`). So the v4 macOS document has no
`gpu_device`, the getattr returns `None`, and the allocation refuses. Three v3-only assumptions now
sit in one path — accepted config type (fixed), policy ceiling (fixed), guard device (open) — and all
three were invisible until a real caller *allocated* instead of describing. The remaining fix belongs
with the guard/accelerator boundary and must build the scope device from the resolved v4 accelerator,
not from `gpu_device`.

_Ledger source HEAD: `c803f5a1`; no evidence deleted._

## CP-UQ256 — Four gates cleared, one left, and a test debt I am not hiding

```yaml
checkpoint_id: CP-UQ256
last_valid_experiment: EXP-UQ256-W2-RESOURCE-PARTIAL
current_hypothesis: The v4 allocation path can be unblocked by replacing its v3-only assumptions one
  by one. Four are gone; the fifth is the Darwin guard's accelerator input.
working_tree_status: clean after the scoped commit below
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - TEST DEBT: the last two edits (`start_guard._require_gpu_selector` accepting `MPS:default`,
    `resources._start_guard_check` deriving the selector from the v4 accelerator) were made while
    investigating and are validated only by the integration probe. They are NOT done until their
    RED/GREEN unit tests exist; if a unit test cannot justify them they must be reverted.
  - The guard still refuses admission with GPU_TARGET_UNAVAILABLE: `require_before_spawn(scope)`
    never receives the Darwin MPS accelerator snapshot.
  - Screen Recording remains denied to this session, so Task 14 batches stay blocked.
next_command: give the Darwin guard its accelerator input, then write the owed unit tests
```

### The gate sequence, all from one probe

```text
green-05  START_GUARD_UNAVAILABLE                 (no guard supplied - correct fail-closed)
green-06  PROBE_STATE_ROOT_UNSET                  (guard needs the registered task root - correct)
green-07  CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION (`gpu_device`, a v3/CUDA field v4 replaced)
green-08  ValueError: gpu_selector must be UUID:<uuid> or INDEX:<index>   (CUDA-shaped scope)
green-09  GPU_TARGET_UNAVAILABLE                  (scope accepted; the guard cannot see an MPS target)
```

Each one is the same species of defect: a v3/CUDA assumption inside the allocation path that no v4
caller ever exercised because every v4 caller described resources instead of allocating them. Two
were fixed with tests already in place (`84f217cc`), two more were fixed in this round.

`EXP-UQ256-W2-RESOURCE-PARTIAL: PARTIAL` — explicitly not a pass. No Worker has been allocated yet,
no station started from this path, no batch ran. Task 14 remains 0/5 and `LINUX_REGRESSION_DEFERRED`
is retained.

_Ledger source HEAD: `9c336e65`; no evidence deleted._

### CP-UQ256 follow-up — the owed test, and the A/B reference I got wrong first

`task14-guard-selector-regression-01`: the guard suite with the new test is **52 passed**.

```text
test_guard_scope_accepts_only_the_v4_mps_selector_form
  task14-guard-selector-red-03  vs 9c336e65 (true pre-fix)  -> 1 failed   (real RED)
  task14-guard-selector-01      vs current                  -> 2 passed  (GREEN)
```

The test accepts `MPS:default` and refuses `MPS:0`, `MPS:mps`, `MPS:`, `mps:default` and
`UNIFIED:default`, so the v4 form is closed and the v3 `UUID:`/`INDEX:` forms are untouched.

Correction kept on the record: my first A/B used `4244f907` as the "pre-fix" reference, but that
commit is a *descendant* of the fix, so the test passed and the A/B proved nothing. The genuine
pre-fix revision is `9c336e65`, and against it the test fails. Reporting either result without
checking the reference revision would have been wrong.

Test debt remaining: `resources._start_guard_check` deriving the guard selector from the v4
accelerator still has no unit test of its own; only the integration probe covers it.

_Ledger source HEAD: `6bfa9343`; no evidence deleted._

### CP-UQ256 follow-up 2 — the guard takes the accelerator, but still asks for CUDA bytes

```text
task14-w2-resources-green-10  ProbeError ACCELERATOR_KIND  (my probe passed the config, not the kind)
task14-w2-resources-green-11  accelerator_probe=MpsAcceleratorProbeSelection, then
                              ResourceAllocationError GPU_TARGET_UNAVAILABLE
```

`compose_default_start_guard(policy, accelerator=...)` accepts the v4 selection and
`select_accelerator_probe("mps")` resolves, so the accelerator *input* now reaches the guard. The
admission still refuses, which locates the last gate precisely: the guard's check set is built from
`StartGuardPolicy.gpu_minimum_bytes`, a CUDA quantity, while the Darwin document's budget is
`mps_minimum_headroom_bytes` and its kind is the `unified-memory-proxy` admission. The v4 branch must
evaluate the MPS headroom (`evaluate_accelerator_snapshot`) whenever an accelerator is supplied, and
leave the NVML snapshot path to v3 untouched.

That is the last known gate between the v4 document and two allocated Workers, and it belongs to the
accelerator/guard boundary the plan put in Tasks 4–5.

_Ledger source HEAD: `e70ab514`; no evidence deleted._

### CP-UQ256 follow-up 3 — the accelerator is delivered correctly, and the guard still merges CUDA

```text
task14-w2-resources-green-12  accelerator_probe=DarwinMpsAcceleratorProbe
                              admission_kind=unified-memory-proxy
                              compose_default_start_guard(policy, accelerator=<that probe>)
                              -> ResourceAllocationError GPU_TARGET_UNAVAILABLE
```

Two things are now settled. `select_accelerator_probe("mps")` returns a
`MpsAcceleratorProbeSelection` whose `.probe` is the `DarwinMpsAcceleratorProbe` and whose
`admission_kind` is `unified-memory-proxy`, and `compose_default_start_guard(..., accelerator=...)`
wants **the probe**, not the selection wrapper (passing the wrapper silently falls back to the v3
NVML path — that was my mistake in green-10/11, now corrected in the probe script).

The remaining defect is in the guard itself, and it is precise: `ProbeCoordinator.check` documents
that a supplied accelerator "runs inside the same policy deadline and **is merged into the result**",
so the schema-v3 checks still execute — including the NVML GPU check, which on Darwin raises
`GPU_TARGET_UNAVAILABLE` (`start_guard.py:346-366`, `nvmlInit_v2`). Merging is the wrong shape for a
closed platform combination: on Darwin the MPS proxy admission must **replace** the CUDA/NVML check,
while a guard composed without an accelerator must keep returning exactly the v3 result. That change
belongs to `start_guard_probe.check` / `EpochStartGuard.begin_epoch` and needs its own RED/GREEN
pair, including a case proving the no-accelerator path is byte-identical to today's.

No Worker has been allocated, no batch ran; Task 14 stays 0/5 and `LINUX_REGRESSION_DEFERRED` holds.

_Ledger source HEAD: `20219623`; no evidence deleted._

### CP-UQ256 follow-up 4 — the refusal happens in the helper child, so the fix is a request field

Correcting my own previous diagnosis: it is not only that merging is the wrong shape. The v3
measurement runs in a **spawned helper child** (`check` writes a request document, `self._spawn`,
collects the result, and only then calls `_merge_accelerator`). That child imports
`probe_snapshot` / `evaluate_snapshot` from `.start_guard`, which is where `nvmlInit_v2` raises
`GPU_TARGET_UNAVAILABLE` (`start_guard.py:346-366`). By the time the parent could merge the MPS
admission, the helper has already failed — so no amount of parent-side merging can rescue it.

The fix shape is therefore a request field: the parent already sends `policy.gpu_minimum_bytes` in
the JSON request, and it must also tell the child which accelerator family it is probing (the Darwin
policy carries `mps_minimum_headroom_bytes`, which is exactly the discriminator). The child then runs
the MPS admission instead of the NVML one, and a request without that discriminator must produce
byte-identical v3 behaviour. This belongs to `start_guard_probe.check` (request) + the helper entry
point + `_merge_accelerator`, and it needs its own RED/GREEN pair, including the v3-unchanged case.

Still: no Worker allocated, Task 14 0/5, `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `9d6d1ffc`; no evidence deleted._

### CP-UQ256 follow-up 5 — the exact edit site, and why I did not edit it yet

`run_helper` (`start_guard_probe.py:642-667`) is the whole helper side:

```python
request = json.loads(_read_all(request_fd).decode())
policy = StartGuardPolicy(**request["policy"]); scope = GuardScope(**request["scope"])
...
snapshot = probe_snapshot(policy, scope, deadline)              # <- NVML lives here
result = evaluate_snapshot(snapshot, policy, scope, ...)
```

and the parent's request document (`check`, lines 446-464) sends `policy.gpu_minimum_bytes` but nothing
that says which accelerator family the child is probing. The v4 fix is therefore:

1. the parent adds the discriminator to the request (the Darwin policy's
   `mps_minimum_headroom_bytes` is exactly it, so no new vocabulary is needed);
2. the child, when the discriminator is present, must keep the CPU/RAM measurement and **drop only
   the GPU/NVML part** — a guard that silently skipped CPU/RAM validation would be weaker than v3,
   which is not an acceptable trade;
3. `_merge_accelerator` keeps deciding the MPS admission;
4. requests without the discriminator must produce byte-identical v3 results, with a test proving it.

Step 2 is the part that needs care, because the GPU probe and the CPU/RAM probe live in the same
`probe_snapshot` call, and whether it can already degrade without NVML is exactly what I have not yet
read. I am deliberately not making that edit half-informed: the last three product edits in this
chain were each justified by a live RED, and this one would be a guess until that call is read.
`entrypoint-regression-05` (263 passed) stands as the pre-change baseline for the round that does it.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `ffe94119`; no evidence deleted._

### CP-UQ256 follow-up 6 — the constraint that decides the v4 helper design

Three facts, read rather than assumed:

```text
probe_snapshot (start_guard.py:659-689)  reads cpu -> ram -> cpu_busy -> resolve_gpu_target
ResourceSnapshot.__post_init__ (189-213) requires `gpu_uuid: str`, `gpu_total_bytes: int`,
                                         `gpu_free_bytes: int` - none may be None
evaluate_snapshot                        consults `snapshot.gpu_uuid` directly (line 740)
```

So a GPU-less snapshot is **not representable** in the frozen v3 model, and the GPU read is the last
step of `probe_snapshot`, after every CPU/RAM read. That rules out the tempting shortcuts:

- do not let the child skip `probe_snapshot` outright - CPU/RAM validation would silently vanish and
  the Darwin guard would be weaker than v3;
- do not fill the GPU fields with MPS numbers - that would fabricate a CUDA-style device in evidence
  the design explicitly refuses to fake;
- do not relax `ResourceSnapshot` - it is frozen v3 surface.

The design that satisfies all three: for a request carrying the Darwin discriminator, the helper
reuses the CPU/RAM readers (`_read_cpu`, `_read_ram`, `_read_cpu_busy`), evaluates the cpu-busy and
RAM thresholds itself, and returns a `GuardResult` with `snapshot=None` plus those checks; the parent
then merges the MPS proxy admission exactly as it already does. A request without the discriminator
keeps the current path byte for byte, and that equivalence is the first test to write.

Recorded as the decided design with its justification, not as done work. Task 14 stays 0/5 and
`LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: `f71e3484`; no evidence deleted._

### CP-UQ256 follow-up 7 — the child branch is the only thing left in this chain

`320df6a0` sends the discriminator; the helper does not read it yet. The remaining edit is confined to
`run_helper` (`start_guard_probe.py:642-667`) and must:

1. read `request["policy"].get("mps_minimum_headroom_bytes")` after building the policy;
2. when it is present, skip `probe_snapshot` (whose `resolve_gpu_target` is the NVML call that raises
   `GPU_TARGET_UNAVAILABLE` on Darwin) and instead reuse the module's CPU/RAM readers
   (`_read_cpu`, `_read_ram`, `_read_cpu_busy`, all reachable from the same module), evaluate the
   cpu-busy and RAM thresholds, and return a `GuardResult` with `snapshot=None` plus those checks;
3. when it is absent, run today's code path unchanged;
4. keep the checks' names and units identical to `evaluate_snapshot`'s so the parent's
   `_merge_accelerator` composition does not need a second vocabulary.

Tests owed with it: the v4 branch produces CPU/RAM checks and no GPU check; the v3 branch is
byte-identical (compare the serialized result document for a stubbed snapshot); and the integration
probe (`probe-w2-resources.py`) then resolves two Workers.

The verification commands are already in place, so the next round starts by reading
`evaluate_snapshot`'s check construction and editing exactly one function.

_Ledger source HEAD: `320df6a0`; no evidence deleted._

## CP-UQ257 — The v4 admission passes, and the next Linux-only assumption appears

```yaml
checkpoint_id: CP-UQ257
last_valid_experiment: EXP-UQ257-V4-ADMISSION-GREEN
current_hypothesis: The guard chain was the last obstacle to allocating exact W2 from the v4
  document. CONFIRMED for admission; the allocator then hits a Linux claim root.
working_tree_status: clean after the scoped commit below
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - Domain claiming still targets `/run/user/<uid>/so101-parallel-domain-claims`, a Linux runtime
    path, so no Worker is allocated yet.
  - Screen Recording is still denied to this session; Task 14 batches remain blocked.
next_command: give the v4 allocator its Darwin claim root (the private path strategy already exists)
```

`EXP-UQ257-V4-ADMISSION-GREEN: VALID` for the guard scope only.

### What the new branch does

`run_helper` now splits on the discriminator sent in `320df6a0`:

- no `mps_minimum_headroom_bytes` → today's path, unchanged;
- Darwin request → `_v4_cpu_ram_result`, which measures cpuset/cores, RAM and CPU busy through the
  same readers and emits `cpu_capacity`, `cpu_busy` and `ram` checks with **identical names, cutoffs
  and units** to `evaluate_snapshot`, no `gpu` check, `snapshot=None`, and `FAIL` only if a measured
  check fails. CPU/RAM stay enforced; NVML is never touched; no CUDA-shaped device is fabricated.

```text
task14-guard-helper-01       67 passed  (guard probe + start guard suites)
direct smoke                 status PASS, checks [cpu_busy, cpu_capacity, ram], snapshot None,
                             ram observed 12 106 350 592 bytes vs cutoff 1 288 490 188
task14-w2-resources-green-13 admission now passes; allocation proceeds to domain claiming
```

### The next gate

```text
ResourceAllocationError: PATH_ANCESTOR_UNAVAILABLE: /run/user/501/so101-parallel-domain-claims
  resources.py:1432 _claim_domains -> _open_trusted_parent
```

`claim_root` defaults to a Linux runtime directory. The Darwin private path strategy that replaces
it already exists (`runtime/unix_address.py`, `CampaignIpcRoot`, `/private/tmp/so101-ipc-<uid>`), so
this is a wiring step rather than new design work.

Task 14 remains 0/5 and `LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: (parent of this commit); no evidence deleted._

### CP-UQ257 addendum — the claim root was one line, the preflight is the sixth gate

With a task-owned private claim root passed explicitly (`claim_root=...`, 0700), the Linux default
`/run/user/<uid>/so101-parallel-domain-claims` stops being a problem and allocation proceeds to:

```text
ResourceAllocationError: UNIX_TRANSPORT_UNAVAILABLE
  resources.py:1095 allocate -> _preflight(paths, parent_fd, domains) -> resources.py:1637
```

So the allocator's preflight still assumes the Linux transport shape (`/proc/self/fd`-style or
`/run/user`-rooted checks). This is the sixth v3/Linux assumption found in the same path, after the
accepted config type, the policy ceiling, the guard selector form, the accelerator input, and the
claim root.

That pattern is itself the finding, and it changes the plan for the next round: patching gate by
gate is now clearly the wrong shape. The v4 Darwin combination needs one explicit branch in the
allocator — a Darwin preflight and claim root taken from the existing private-path strategy
(`runtime/unix_address.py`) — with the v3 branch left byte-identical, rather than six independent
conditionals scattered along a Linux code path. The six gates found so far are the specification for
that branch.

No Worker allocated yet; Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `fca32ffb`; no evidence deleted._

### CP-UQ257 addendum 2 — the Darwin branch, specified to the line

`_preflight` refuses because of the transport check, and the reason is now precise. The allocator
builds each slot's socket as a **dirfd-relative namespace**:

```python
socket_namespace = self.ipc_root / str(slot_index)      # resources.py:1596
socket_path      = socket_namespace / 's'               # 1607
...
require_transport_basename(socket_path)                 # 1635 -> IpcError -> UNIX_TRANSPORT_UNAVAILABLE
```

`require_transport_basename` is the Linux `proc_fd_unix` rule: the socket must be bindable as a
basename inside an owned parent descriptor. The path shape it sees (`/…/ipc/0/s`) is already
basename-compatible, so the refusal is about the transport being *available* at all — i.e. the
`/proc/self/fd` dirfd form Darwin does not have. That is exactly the rule schema v4 replaces with the
Darwin private-path strategy (`runtime/unix_address.py`, absolute `/private/tmp/so101-ipc-<uid>`
endpoints, `0700` root, `0600` sockets, `sun_path` capacity 103).

So the Darwin branch of the allocator is small and well-defined:

1. keep the namespace/path construction above (it stays basename-shaped and the workers' environment
   keys do not change);
2. select the transport validation by schema: `require_transport_basename` for v3, and the Darwin
   strategy's encoded-length validation (`validate_encoded_length`, 103 bytes) for a
   `ParallelRuntimeConfigV4` document;
3. leave every other `_preflight` rule (`SYMLINK_PATH`, `DIRECTORY_CONFLICT`, namespace collisions)
   in force for both platforms - those are platform-neutral and must not be relaxed;
4. add the v4 case to the allocator's own tests plus one proving the v3 refusal is unchanged.

This is the seventh gate, and with it the branch has a complete specification: the six earlier gates
supply the platform selection, policy ceiling, guard selector, accelerator input and claim root; this
one supplies the transport rule.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `997e0cba`; no evidence deleted._

## CP-UQ258 — The Darwin transport branch works; the domain probe is the eighth gate

```yaml
checkpoint_id: CP-UQ258
last_valid_experiment: EXP-UQ258-DARWIN-TRANSPORT-BRANCH
current_hypothesis: The allocator's preflight only needed the v4 transport rule. CONFIRMED, and the
  next Linux-only assumption is the live-domain probe.
working_tree_status: clean at commit feaebb21
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - `SystemResourceProbe.ros_domain_in_use` reads `/proc`, so the v4 Darwin allocator cannot check
    live ROS domain collisions yet.
  - Screen Recording is still denied to this session; Task 14 batches remain blocked.
next_command: give the v4 allocator a portable same-UID domain probe (psutil is already a dependency)
```

`EXP-UQ258-DARWIN-TRANSPORT-BRANCH: VALID` for the transport scope.

### What changed

`_preflight` now selects its transport rule by schema: the v3 `require_transport_basename` is
untouched for v3 documents, and a `ParallelRuntimeConfigV4` document validates the encoded `sun_path`
instead - 104 bytes for `darwin_private_path_unix`, 108 for the Linux combination, both taken from
`runtime/unix_address.py` rather than re-declared. Every other preflight rule (symlink, directory
conflict, namespace collision) stays in force on both platforms.

### The probe chain, now measured end to end

```text
green-13  GPU_TARGET_UNAVAILABLE          (fixed in cc992945: the v4 CPU/RAM helper branch)
green-14  UNIX_TRANSPORT_UNAVAILABLE      (fixed in feaebb21: v4 transport rule)
green-15  SOCKET_PATH_TOO_LONG: 128 bytes + NUL > 104
          -> real Darwin fact: the evidence root is too long for sun_path; the socket namespace
             must live under the private short base (`/private/tmp/so101-ipc-<uid>`), which the
             Darwin strategy already owns
green-16  PROBE_FAILED: proc filesystem unavailable
          -> `SystemResourceProbe.ros_domain_in_use` iterates `/proc`; on Darwin there is none
```

Note the shape of green-15: it is not a defect to patch away but the platform telling the truth. The
short base is the design's answer, and the probe now passes `ipc_root=/private/tmp/so101-ipc-501/...`
explicitly - which is also what the production composition must do.

Regression: `task14-allocator-transport-regression-01` - 174 passed, 45 failed, where those 45 are
exactly the pre-existing environmental failures of `test_parallel_batch_resources.py` measured
earlier with and without changes (`task14-w2-resources-ab-01/02`: 45 failed, 47 passed both ways).
No new failure is attributable to this commit.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `feaebb21`; no evidence deleted._

### CP-UQ258 addendum — the portable domain scan is not available on macOS, and I reverted it

I implemented `_ros_domain_in_use_portable` (psutil scan of same-UID processes, comparing
`ROS_DOMAIN_ID` in their environment) and its test, ran it, and it failed for a reason worth keeping:

```text
task14-domain-probe-01   FAILED  ResourceAllocationError at resources.py:409
                         (psutil.AccessDenied while reading a same-UID process environment)
```

macOS denies environment reads for many processes even within the same UID, so a process-environment
scan cannot distinguish "no claim" from "cannot see". Failing closed on every unreadable process
makes allocation impossible (which is what the run showed); returning `False` would silently drop a
real claim and let two Workers share a ROS domain - the exact failure this check exists to prevent.
Neither branch is acceptable, so the change was reverted in full (source and test) and the tree is
green again.

The conclusion for the next round: the eighth gate needs a **filesystem** answer, not a process
answer. The campaign already keeps durable claims under the claim root, and those files are portable
and fail-closed; a Darwin `ros_domain_in_use` should read the claim registry (and treat "cannot
verify" as a refusal) rather than guess from process environments. That is a design decision about
what this platform can prove, and it belongs next to the trust-boundary note that already accepts
same-UID processes in a single-user simulation host.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `00889fc1`; no evidence deleted._

### CP-UQ258 addendum 2 — the portable domain check, with the self-conflict trap mapped

Two facts from the allocator decide the implementation, and both were read rather than assumed:

```text
allocate():      1101  self._claim_domains(domains)      # this allocator already holds the flocks
                 1102  self._preflight(paths, parent_fd, domains)   # collision check runs after
claim payload:   the `domain-<id>.lock` file content is JSON carrying `pid: os.getpid()`
```

So a naive "try to flock the claim file and treat failure as a conflict" would detect **itself** and
refuse every allocation. The portable check must therefore read the recorded owner instead:

1. `claim_root/domain-<id>.lock` missing -> no claim, no conflict;
2. payload unreadable, non-JSON or missing `pid` -> fail closed (`PROBE_FAILED`), because "cannot
   verify" must never be reported as "free";
3. recorded `pid == os.getpid()` -> this allocator's own claim, not a conflict;
4. recorded pid alive (the portable identity reader already exists) -> `ROS_DOMAIN_IN_USE`;
5. recorded pid gone -> a stale file from a finished campaign, not a conflict - the flock is gone
   with it, and the next campaign re-claims it.

That is the eighth gate's specification, and it is portable because it reads files and the process
table instead of `/proc`. Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `ad2a525c`; no evidence deleted._

## CP-UQ259 — Exact W2 now allocates two real Workers on macOS

```yaml
checkpoint_id: CP-UQ259
last_valid_experiment: EXP-UQ259-W2-WORKERS-ALLOCATED
current_hypothesis: With the eight v3/Linux assumptions replaced, the v4 document allocates exact
  W2 on Darwin. CONFIRMED - two Workers, two domains, two worker roots.
working_tree_status: clean at commit 823ce3c3
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - The allocation is proven; nothing downstream of it has run yet (no station, no Broker, no batch).
  - Screen Recording is still denied to this session, so Task 14 batches remain blocked.
next_command: build the macOS W2 simulation composition on top of allocated resources (map steps 2-4)
```

`EXP-UQ259-W2-WORKERS-ALLOCATED: VALID` for allocation.

### The result

`task14-w2-resources-green-17/`:

```text
worker-01  slot_index 1  ROS_DOMAIN_ID 181  generation 1
           worker_root <run>/resources/workers/worker-01
worker-02  slot_index 2  ROS_DOMAIN_ID 182  generation 1
           worker_root <run>/resources/workers/worker-02
```

Two Workers, two distinct domains, two distinct roots and two distinct session ids - the resource
half of CP-UQ253's map step 1, on the Darwin MPS document, with the guard admission `PASS` through
the `unified-memory-proxy` kind.

### What it took

Eight v3/Linux assumptions, each found by a live refusal rather than by reading:

| # | Assumption | Fixed by |
| --- | --- | --- |
| 1 | allocator accepted only v1/v2/v3 config types | `84f217cc` |
| 2 | policy ceiling taken from the frozen `max_worker_count` (8) vs two domains | `84f217cc` |
| 3 | guard scope device from the v3 `gpu_device` | `7a400133` |
| 4 | guard selector forms were CUDA-only (`UUID:`/`INDEX:`) | `7a400133` + `6bfa9343` test |
| 5 | accelerator probe merged into, rather than replacing, the NVML check | `320df6a0`, `cc992945` |
| 6 | claim root defaulted to `/run/user/<uid>` | probe-side `claim_root` |
| 7 | transport rule required the Linux dirfd form | `feaebb21` |
| 8 | live-domain probe read `/proc` | `823ce3c3` |

Two of those rounds are worth remembering for how they went: the psutil process-environment scan was
implemented, run, and **reverted** because macOS denies same-UID environment reads (CP-UQ258
addendum), and the portable replacement had to dodge a self-conflict trap - the allocator holds its
own claim flock before the collision check runs, so the check reads the recorded owner instead of
trying the lock.

Regression: `task14-domain-claim-regression-01` - 175 passed, 45 failed, the 45 being exactly the
pre-existing environmental failures of `test_parallel_batch_resources.py` (A/B: 45 failed / 47-48
passed with and without changes). No new failure.

Task 14 remains 0/5: no station has been started from this allocation, no Broker, no batch, and
`LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: `823ce3c3`; no evidence deleted._

## CP-UQ260 — Two stations start, but neither reaches the ready contract concurrently

```yaml
checkpoint_id: CP-UQ260
last_valid_experiment: EXP-UQ260-TWO-STATIONS-READY (FAILED gate, clean cleanup)
current_hypothesis: Each allocated slot can own its own station on its own domain. Start-up
  CONFIRMED; the ready contract is not met when both run at once.
working_tree_status: clean - no product changes in this round
owned_processes: NONE - both stacks shut down in 0.18 s each and left no process behind
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - Both stations reported MOTION_STACK_CONTROLLER_NOT_ACTIVE (joint_state_broadcaster) after a
    180 s budget, while a single station reached READY in about 25 s earlier - contention or a
    launch-level conflict, not yet diagnosed.
  - Screen Recording is still denied to this session.
next_command: run the two stations sequentially (ready slot 1, then start slot 2) and compare logs
```

`EXP-UQ260-TWO-STATIONS-READY: FAILED` - recorded as a failure, not a partial pass.

### What the run did establish

`task14-w2-stations-02/` (367 s, exit 0):

```text
worker-01  slot 1  ROS_DOMAIN_ID 181  headless=false  -> station started
worker-02  slot 2  ROS_DOMAIN_ID 182  headless=false  -> station started
argv tail  : so101_mujoco_task_station.launch.py headless:=false sensor_rendering:=true
             include_teleop:=false session_id:=<per-worker session>
             task_evidence_root:=<run>/.../workers/worker-0N
shutdown   : 0.18 s each, still_running=false, zero ros2_control_node / move_group left
```

So the structural claim holds: **two allocated Workers, two ROS domains, two independently owned
visible stations, started and stopped by product code**, with the per-slot session id and evidence
root threaded through. What failed is readiness: both readiness probes returned
`MOTION_STACK_CONTROLLER_NOT_ACTIVE` with dependency `joint_state_broadcaster` after their 180 s
budget, where the single-station smoke earlier reached `READY` (controllers active, MoveIt services
present) in about 25 s.

Two candidate causes are worth distinguishing next round, and the run does not yet tell them apart:
resource contention between two 500 Hz MuJoCo physics loops plus two MoveIt stacks on one Mac mini,
or a launch-level conflict that only appears when a second station starts (shared file, shared
service name on the same domain, or a spawner timeout). The sequential run separates them: if slot 2
reaches ready when started alone after slot 1 is up, it is contention; if it fails the same way, it
is a launch conflict.

Task 14 remains 0/5 and `LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: `626b4370`; no evidence deleted._

### CP-UQ260 addendum — the sequential run points away from contention

Observation from `task14-w2-stations-seq-01/` while it was still running (slot 1 started alone, slot 2
not started yet):

```text
processes matching `ros2_control_node|move_group`: 2  = one station (control node + move_group)
grep -c "Successfully switched controllers" stdout.log: 0
result.txt: empty (the ready check was still inside its 180 s budget)
```

So the first station, with **no peer running**, had not activated its controllers either, while the
identical station command launched by `run-owned-station.sh` reached `READY` in 0.87 s of startup and
about 25 s of readiness (`task14-owned-station-02`). That makes "two MuJoCo stacks contend for the
Mac mini" a poor explanation of CP-UQ260 and moves the suspicion to what my probe passes into the
station, i.e. the Worker's own environment from the allocator:

```python
environment = {**os.environ, **dict(worker.environment or {}), "ROS_DOMAIN_ID": str(worker.ros_domain_id)}
```

The next diagnostic is therefore a diff, not another run: print the allocator's `worker.environment`
for slot 1 and compare it against the environment the verified smoke used, looking for a variable
that changes discovery, the RMW implementation, the ROS home/log root, or the spawner's timing. If a
variable is the cause, the fix belongs where the allocator builds it - not in the station.

This is recorded as an in-flight observation, not a conclusion: the run had not finished when it was
written, and the ready result for both slots is still owed.

_Ledger source HEAD: `f412680a`; no evidence deleted._

### CP-UQ260 addendum 2 — the portable claim refuses a second campaign, as it must

Running a second allocation while the sequential station gate still held its claims produced:

```text
task14-env-diff-02   exit 1
ResourceAllocationError: ROS_DOMAIN_CLAIMED: 181
  resources.py:1101 allocate -> _claim_domains -> 1460
```

That is the portable check from `823ce3c3` working in the direction that matters: a live campaign
holding domain 181 is seen by a *different* process, and the new campaign is refused instead of
silently sharing a domain. It is the first cross-process evidence for that check, since the unit test
only exercised its branches in isolation.

It also means the environment diff has to wait until the sequential gate releases its claim - a
one-campaign-at-a-time rule the driver must respect, not a defect.

Two harness lessons for the next round, both mine rather than the product's: probe documents must be
written to a **file** instead of stdout (station launch output interleaves with stdout and has now
broken three parses), and the gate must create its own run root (pre-creating it makes `run-gate.sh`
refuse, which cost round 42).

_Ledger source HEAD: `9548cf09`; no evidence deleted._

## CP-UQ261 — Root cause: the canonical install shadowed the branch, and that is why no station was ready

```yaml
checkpoint_id: CP-UQ261
last_valid_experiment: EXP-UQ261-STATION-PREFIX-SHADOWING (gate FAILED; cause identified)
current_hypothesis: The station readiness failures (CP-UQ260, sequential run) come from resource
  contention or a launch conflict. DISPROVEN as the primary cause.
working_tree_status: clean - no product changes in this round
owned_processes: the sequential gate is still running and will reap its own stations
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - Station launches inherit an AMENT_PREFIX_PATH whose head is the branch overlay for one package
    but whose tail is the canonical checkout's install, so nodes resolve from the wrong build.
  - Screen Recording is still denied to this session.
next_command: launch stations from a scrubbed environment (station-env.sh order) and re-run the gate
```

`EXP-UQ261-STATION-PREFIX-SHADOWING: FAILED` for the gate, but the cause is now established.

### The evidence

While the sequential gate was waiting, the running nodes were resolved from the canonical checkout:

```text
pgrep ros2_control_node -> /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/...
station stdout          -> [controller_manager]: Waiting for data on 'robot_description' topic
                           (repeated for minutes - it never resolves)
task14-w2-stations-seq-01/provenance.txt:
  AMENT_PREFIX_PATH = <branch-build-01>/install/so101_demo_py
                      /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py
                      .../moveit-demo/install/so101_teleop
                      .../moveit-demo/install/so101_mujoco_support
                      .../moveit-demo/install/mujoco_ros2_control ... (the whole canonical stack)
```

So the probe's stations were launched against the **canonical** MuJoCo/MoveIt/ros2_control install,
while the launch description, configs and evidence root came from this branch. `ros2_control_node`
then waited forever for a `/robot_description` that the mismatched node set never delivered.

That is both the mechanical cause and a plan violation: the global constraints forbid using the
canonical checkout's install as this branch's proof. The working comparison was already in hand and
I missed what it was telling me: `task14-owned-station-02`, the smoke that reached `READY`, launched
through `station-env.sh`, which sources the underlay, `extra_ws` and then this branch's station
install - and no canonical prefix.

### What this changes

The macOS W2 driver must build each station's environment explicitly from the validated chain
(underlay -> `extra_ws` -> the branch's station install) and must **refuse to launch** if a canonical
`moveit-demo/install` prefix is present in `AMENT_PREFIX_PATH`, rather than silently accepting it.
The two earlier failures (concurrent and sequential) are now explained by a single cause; the
contention hypothesis is retired.

Task 14 remains 0/5 and `LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: `60fba22f`; no evidence deleted._

## CP-UQ262 — Exact W2: two slots, two domains, two ready stations

```yaml
checkpoint_id: CP-UQ262
last_valid_experiment: EXP-UQ262-TWO-READY-STATIONS
current_hypothesis: With the canonical prefix scrubbed, each allocated slot owns a station that
  reaches the full ready contract on its own domain. CONFIRMED for both slots.
working_tree_status: clean - no product changes in this round
owned_processes: NONE - both stacks shut down in 0.33 s and 0.5 s, no process or orphan left
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - The station environment is currently assembled by a gate wrapper; the driver must build it (and
    refuse a canonical prefix) itself.
  - The Broker, the v4 broker proxy and the batch loop are still unwritten, so no batch can run.
  - Screen Recording is still denied to this session.
next_command: move the environment scrubbing into the driver, then wire the shared MPS Broker
```

`EXP-UQ262-TWO-READY-STATIONS: VALID`

### The result

`task14-w2-stations-scrub-01/`:

```text
worker-01  slot 1  ROS_DOMAIN_ID 181  peers_already_running 0
           ready=True phase=READY failure=None   ready_wait 14.9 s   shutdown 0.33 s
           controllers: arm_controller active, gripper_controller active,
                        joint_state_broadcaster active
worker-02  slot 2  ROS_DOMAIN_ID 182  peers_already_running 1
           ready=True phase=READY failure=None   ready_wait 17.9 s   shutdown 0.5 s
           controllers: arm_controller active, gripper_controller active,
                        joint_state_broadcaster active
grep "Waiting for data on 'robot_description'": 0
```

That is the structural core of Task 14: **two allocated Workers, two ROS domains, two independently
owned visible stations, each reaching the complete ready contract, with the second starting while
the first is already up** - so neither resource contention nor a launch conflict was ever the
problem (CP-UQ260's hypothesis is retired), and the portability work of CP-UQ259 is what made the
allocation possible at all.

### One gate recorded as INVALID, and my cleanup

`task14-w2-stations-seq-01` was killed while its first station sat in the canonical-prefix wait; it
produced no document and is recorded as **INVALID**, not as a failure of the product. Killing the
gate wrapper first left its Python probe and two canonical-install stations orphaned; the probe was
then terminated by exact PID and the seven reparented processes (two `robot_state_publisher`, two
`ros2_control_node`, two `move_group`, one spawner) were reaped by exact PID, verified to zero. The
lesson is the same one the plan already states: stop the owned process that owns the children, not
the wrapper above it.

Task 14 remains 0/5 - no Broker, no inference, no pick-place, no GUI evidence - and
`LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: `01d827c5`; no evidence deleted._

### CP-UQ262 addendum — the product guard launches both stations for real

`task14-w2-stations-guard-01/` re-runs the two-station gate with the probe no longer assembling its
own environment: it now calls `station_environment(worker)` from `parallel_worker_runtime`
(`11c11afa`), the same guard its unit test covers.

```text
worker-01 slot 1 domain 181  ready=True phase=READY  wait 15.1 s  shutdown 0.38 s  running=False
worker-02 slot 2 domain 182  ready=True phase=READY  wait 18.0 s  shutdown 0.40 s  running=False
stations left afterwards: 0
```

So the environment rule that CP-UQ261 identified is now enforced by product code on the launch path,
not by a gate wrapper: every canonical checkout prefix is stripped from all seven discovery
variables, a surviving one refuses the launch, and the Worker's granted `ROS_DOMAIN_ID` is the one
the station runs under. Both slots still reach the full ready contract with a peer station already
running.

Task 14 remains 0/5 - the Broker, the v4 broker proxy and the batch loop are still unwritten - and
`LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: `11c11afa`; no evidence deleted._

### CP-UQ262 addendum 2 — the real W2 campaign still passes after the portability work

`task14-campaign-batch03/` re-runs the production macOS W2 campaign (MPS Broker, two Workers, one
shared model set, one execution lane, permission-only v4 IPC, one-time consume) after every change
this stretch made to contracts, the allocator, the guard and the worker runtime:

```text
status    : W2_CAMPAIGN_PASS          (11 s, exit 0)
workers   : w1 on slot-0, w2 on slot-1
admission : 6 requests CONSUMED, 0 refused
cleanup   : complete, directory removed, registry empty, workers_reaped [true, true]
```

That is the regression that had to hold: eight v3/Linux assumptions were replaced in the resource
and guard path, and the end-to-end campaign that exercises the Broker, the two Workers, one-time
admission and cleanup is unchanged.

Task 14 remains 0/5 and `LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: `98ea0d0c`; no evidence deleted._

## CP-UQ263 — Where the macOS W2 work stands, in one page

```yaml
checkpoint_id: CP-UQ263
last_valid_experiment: EXP-UQ263-STATE-CONSOLIDATION
current_hypothesis: n/a - this checkpoint consolidates state so the remaining work is unambiguous
working_tree_status: clean at commit 973dbeb1
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - Screen Recording is still denied to this session (tmux pid 59433 unrestarted since 21:13), so
    per-point viewer capture and any counted Task 14 batch remain blocked.
  - Map steps 4-5 (worker-side v4 broker proxy, FULL_RESTART batch loop) are unwritten code, not
    blockers.
next_command: read the CLI's `_WorkerBrokerProxy` and `parallel_ros_runtime`'s broker expectations,
  then implement the macOS v4 proxy as a small port with fakes in its unit test
```

### Done and verified

- **Tasks 0-12 (macOS halves)**: frozen v3 + closed v4 schema, Darwin MPS start guard, durable
  supervisor ownership, permission-only v4 IPC, immutable snapshots, one-time request registry,
  single-lane MPS Broker, fresh package/OpenAPI/copied-install gates.
- **Task 13**: real MPS models load and infer on `mps:0`; the exact-W2 runtime shape passes
  (`task13-w2-runtime-smoke-*`, `task14-campaign-batch02/03` = `W2_CAMPAIGN_PASS`, 6/6 consumed,
  cleanup complete).
- **W2 structure (map steps 1-3)**: exact-W2 allocation on Darwin (`823ce3c3`, two Workers on
  domains 181/182 with their own roots), a visible station per slot via the new
  `task_station_config`, and **both stations ready** (`task14-w2-stations-guard-01`: READY at
  15.1 s / 18.0 s, controllers active, clean shutdown) through the product environment guard
  (`11c11afa`).
- **Real station execution**: a four-point `so101_mujoco_rgbd_batch` ran real MoveIt trajectories and
  MuJoCo physics from this branch's install (`task14-single-batch-01`).

### Not done

| Item | State |
| --- | --- |
| Worker-side v4 broker proxy (map step 4) | unwritten |
| `FULL_RESTART` batch loop, five consecutive batches (map step 5) | unwritten; Task 14 = 0/5 |
| MoveIt shadow / controller / MuJoCo contact / placement per batch | not collected |
| fresh GUI snapshot/action/snapshot | **blocked by TCC** (`screencapture -x` -> "could not create image from display", tmux server unrestarted) |
| Linux regression (Task 15) | `DEFERRED_ENVIRONMENT`, never run, never reported as PASS/SKIP/N/A |
| Task 16 final report | not started; must decide `MACOS_MPS_W2_PASS` vs `PARTIAL` on the real evidence |

### The two conditions that decide the outcome

1. **Screen Recording** must be enabled for the responsible binary and the tmux server restarted.
   Until then no batch can be counted, because every point's terminal capture fails closed.
2. **The driver** is the remaining engineering: allocate (done) -> start stations (done) -> shared
   MPS Broker (exists for the campaign) -> worker-side v4 proxy -> batch loop -> evidence.

Neither is a reason to declare the goal blocked: (2) is work I can still do, and (1) is a single
external action already requested from the user.

_Ledger source HEAD: `973dbeb1`; no evidence deleted._

### CP-UQ263 addendum — the v4 proxy's shape, read from the production proxy

`_WorkerBrokerProxy` (`cli/mujoco_parallel_batch.py:2105-2230`) is the piece to port, and its shape is
small enough to state exactly:

```text
__init__(coordinator, endpoint, resources, config, *, broker_generation,
         broker_generation_consumer=None, perception_runner=None,
         client_factory=UnixRpcClient, clock, sleep)
  -> client = client_factory(endpoint, deadline_s=config.executing_hard_timeout_s,
                             max_frame_bytes=config.broker_max_frame_bytes)
  -> refuses a non-positive broker_generation (BROKER_GENERATION_AUTHORITY)

request_model(lease, execution_kind, *, snapshot, start_event_id, start_event_type, reset_epoch)
  -> _refresh_broker(wait_until_healthy=False) then runs the perception chain

cancel_generation(worker_id, generation)
  -> _refresh_broker(wait_until_healthy=True), then one "cancel_generation" message

_refresh_broker(*, wait_until_healthy, startup=False)
  -> asks the coordinator (startup_broker() or current_broker()) for the authority document
     {healthy, broker_generation, endpoint, ...}, refuses a generation rollback, rebuilds the client
```

So the macOS v4 version differs in exactly two places, both already implemented in this branch:

1. **the client** is `V4PermissionOnlyClient` (permission-only envelope, `0600` socket under the
   Darwin private root) instead of the dirfd `UnixRpcClient`;
2. **the coordinator channel** is the v4 permission-only one, so no token, generation or lease
   fields travel in either direction - the generation bookkeeping stays local to the Worker.

Everything else - `request_model`, `cancel_generation`, the refresh/rollback rules, the perception
runner hook - can keep the same contract, which is what makes this a port rather than a rewrite. Its
unit test can use a fake client factory and a fake coordinator, mirroring the existing proxy tests
rather than needing a live Broker.

_Ledger source HEAD: `bddc1955`; no evidence deleted._

### CP-UQ263 addendum 2 — the Worker-side Broker port exists and is tested

`runtime/macos_w2_broker_port.py` is the v4 port of `_WorkerBrokerProxy`, and it keeps the
production contract while changing exactly the two things schema v4 changes:

- the transport is a `V4PermissionOnlyClient` (`0600` socket under the Darwin private root) and the
  cancellation message carries only `worker_id` and `worker_generation` - no token, no lease, no
  endpoint receipt;
- a generation is read **only** from the Coordinator's authority document and may only move forward:
  `BROKER_GENERATION_ROLLBACK` refuses a backwards authority, and a Worker never keeps a connection
  to a replaced Broker.

`request_model` still refreshes the authority first and then runs the Worker's perception chain -
the Broker response is not an outcome by itself - and `cancel_generation` still waits for a healthy
Broker, bounded by `broker_recovery_timeout_s` rather than forever.

`task14-broker-port-01`: **6 passed**, covering the authority reduction (including a missing or
zero generation and an empty endpoint), the non-positive initial generation refusal, the
health-waiting cancellation with a rebuilt client, the rollback refusal, the bounded recovery
timeout, and the perception-runner requirement.

Task 14 remains 0/5 and `LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: `d12e536e`; no evidence deleted._

### CP-UQ263 addendum 3 — the port was checked against its real caller, and one signature was wrong

Reading the call sites instead of trusting my own port's shape paid off twice:

```text
parallel_batch/worker.py:897  self._broker.request_model(current, ExecutionKind.…,
                                snapshot=…, start_event_id=…, start_event_type=…, reset_epoch=…)
parallel_batch/worker.py:331  record["fenced"] = self._broker.cancel_generation(
                                lease.worker_id, lease.worker_generation) is True
```

`request_model`'s shape matched what the port already had. `cancel_generation` did **not**: the
Worker fences on `... is True`, and my port returned the Broker's response document, so every fence
would have read `False` - a real defect that no test of mine would have caught, because I had
written the test against the same wrong assumption.

The port now returns `True` on a completed cancellation and raises when it cannot reach the Broker;
`task14-broker-port-02` re-runs the suite with that assertion (**6 passed**). The remaining unchecked
guess is the keyword shape the port passes into the Worker's perception runner, which the production
proxy defines - that is the next thing to read before the port is wired in.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `c772784d`; no evidence deleted._

### CP-UQ263 addendum 4 — the perception contract is positional, and one injection is still owed

The production proxy settles the shape my port had guessed:

```python
perception_runner(lease, execution_kind, snapshot,
                  lambda model_id, before_send: self._request_one(lease, execution_kind,
                      model_id=model_id, snapshot=snapshot, start_event_id=...,
                      start_event_type=..., reset_epoch=..., before_send=before_send))
```

So `request_model` passes the chain **four positional arguments**, the fourth being a one-model call.
The port now does exactly that: `perception_runner(lease, execution_kind, snapshot, send)`, where
`send(model_id, before_send=None)` delegates to a `request_one` callable the driver injects, and a
missing runner or missing `request_one` refuses rather than silently skipping the model call.

`task14-broker-port-03`: **6 passed**, with the test now asserting the positional call, the fastening
of `model_id`/`before_send`, and both refusals.

Still owed before the port is wired in: `_request_one`'s own body - the operation name and payload
the Broker expects - which is the last unread piece of the production proxy. Injecting it keeps the
port honest in the meantime: the protocol call is supplied by the driver that has read it, not
invented here.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `53259f59`; no evidence deleted._

### CP-UQ263 addendum 5 — `_request_one` read; the v4 call is smaller than the v3 one

The last unread piece of the production proxy (`cli/mujoco_parallel_batch.py:2234-2290+`) builds one
Broker call like this:

```text
refresh authority (no health wait); sequence += 1
request_id = f"{lease.attempt_id}-{model_id}"
InferenceRequest(**identity) with
  request_id, model_id, execution_kind, batch_id, coordinator_epoch, worker_id,
  worker_generation, point_id, lease_generation, reset_epoch, image_timestamp_s,
  input_relative_path (from the Worker root parent), input_sha256, deadline_s,
  and attempt_id or validation_id depending on ExecutionKind
before_send(request) when supplied
Snapshot(shape, source_stamp_ns, source_frame_id, start_event_id, start_event_type,
         NormalizedInferenceResponseIdentity.from_request(request))
message = _message(key, lease, {"operation": "infer",
                                "request": BrokerTransport.serialize_request(request),
                                "snapshot": BrokerTransport.serialize_snapshot(broker_snapshot)})
```

Two things follow for the macOS port, and both are simplifications rather than additions:

1. the payload is `{"operation": "infer", "request": …, "snapshot": …}` - the v4 envelope has no
   place for a token, so `_message`'s v3 key/lease machinery collapses to a validated
   `V4Request(request_id, "infer", deadline_monotonic_ns, payload)`;
2. the identity fields stay the same, because they are Worker/Coordinator bookkeeping rather than
   transport authentication - `InferenceRequest`, `Snapshot`, `BrokerTransport` and
   `NormalizedInferenceResponseIdentity` are reused unchanged.

So the driver's `request_one` is: build the identity from the lease and the snapshot, serialize it,
call the v4 client once with that payload, and return the response. That is the piece the port
currently takes as an injected callable, and it is now specified rather than guessed.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `97faab31`; no evidence deleted._

### CP-UQ263 addendum 6 — the port now owns the whole v4 call path

`request_one` is implemented on the port, mirroring the container proxy's call while dropping
everything schema v4 removed:

- identity built from the lease and the snapshot exactly as the production path builds it,
  including `attempt_id` vs `validation_id` by `ExecutionKind`, the worker-root-relative
  `input_relative_path`, the input SHA and the deadline;
- `before_send(request)` honoured, so the Coordinator's local authorization still runs before the
  bytes leave the Worker;
- the envelope is `{"operation": "infer", "request": …, "snapshot": …}` sent through the
  **v4 permission-only client** - no token, generation, lease or endpoint receipt;
- a response carrying `ok=False` is refused as `BROKER_INFER_REFUSED` instead of flowing into the
  chain, so a refused inference cannot be mistaken for an admitted one.

`request_model` keeps the production positional contract and now calls this method through the
`send(model_id, before_send)` callback it hands to the perception chain.

`task14-broker-port-05`: **6 passed**. The whole Worker-side broker path - refusal to serve without a
perception chain, positional chain contract, one-model delegation, fence boolean, rollback refusal,
bounded recovery wait - is covered by fakes and needs no live Broker to test.

Task 14 remains 0/5: the port is not yet wired into a Worker runtime, no batch has run, and
`LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: `1b116965`; no evidence deleted._

### CP-UQ263 addendum 7 — pre-wiring baseline

`task14-pre-wiring-regression-01` runs every suite the Worker-side wiring can touch - broker port,
worker runtime, ROS runtime, campaign, composition, contracts, inference registry, permission-only
IPC:

```text
281 passed, 1 failed
failed: test_parallel_ros_runtime.py::test_consumer_readiness_primes_and_retains_isolated_pose_publisher
```

That failure is the **pre-existing** one pinned by A/B in this same session
(`task14-darwin-station-ab-01`: it fails identically with the Darwin station change stashed, at
`parallel_ros_runtime.py:1717`), so this run records no regression from the four port iterations and
gives the wiring round a clean baseline: 282 tests, one known environmental failure.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `ecd773ba`; no evidence deleted._

### CP-UQ263 addendum 8 — the wiring contract is now fully checked, and one more defect fell out

`RosWorkerRuntimePorts.run_perception_chain(self, lease, execution_kind, snapshot, broker_request)`
(`runtime/parallel_ros_runtime.py:1142`) matches the positional contract the port now uses, and the
production CLI binds it by construction: `perception_runner=runtime_ports.run_perception_chain`. Two
consequences, one of which was another real defect in my port:

1. the chain requires `self.broker_generation` to be a positive int (the port's own authority rule
   already enforces that) and a reset receipt for `lease.attempt_id` - a wiring detail, not a port
   concern;
2. **the port bound the runner per call**, while `ParallelWorker` calls
   `request_model(current, kind, snapshot=…, …)` with no runner at all - so every request through the
   wired port would have refused with `PERCEPTION_RUNNER_REQUIRED`. The runner is now a constructor
   argument, exactly as production builds it, and a port constructed without one still refuses.

`task14-broker-port-07`: **6 passed**. This is the third defect this port has produced by checking its
callers rather than its own assumptions (after the fence boolean and the positional chain), which is
the pattern worth keeping: the port's tests were green each time the interface was wrong.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `11100bd5`; no evidence deleted._

### CP-UQ263 addendum 9 — the Worker's whole broker interface, enumerated

`grep self._broker.` over `parallel_batch/worker.py` returns exactly three call sites and therefore
exactly two methods:

```text
331, 743  cancel_generation(worker_id, generation)          # fenced on `is True`
897       request_model(lease, execution_kind, snapshot=…, start_event_id=…,
                         start_event_type=…, reset_epoch=…)
```

No other attribute is touched - not `broker_generation`, not `connection`, not `resources` - so
`W2BrokerPort` now satisfies the complete Worker-side interface, with the two caller-checked fixes
that enumeration produced (the `is True` fence and the construction-bound perception runner). That
closes the interface question for wiring: the next round can bind the port and expect only the
Coordinator channel, the authority document and the perception runner to be supplied by the driver.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `00e9689e`; no evidence deleted._

### CP-UQ263 addendum 10 — the install carries this session's runtime changes

`setup.py` maps one namespace package (`packages=[python_package]`,
`package_dir={python_package: "src"}`), so every module under `src/` is installed without being
listed - `macos_w2_broker_port.py` included. That was read, not assumed, and then verified by
rebuilding the station install (7 packages, exit 0) and importing from it:

```text
station-build-01 rebuild  -> exit 0
import from the install   -> W2BrokerPort ok, BrokerAuthority 1
                             CANONICAL_INSTALL_MARKER == "moveit-demo/install", guard callables ok
                             authority_from_document({"healthy": True, "broker_generation": 2, …})
                             -> BrokerAuthority(healthy=True, generation=2, endpoint_path='/x/s')
```

So the driver can import the v4 port, the environment guard and the station config from the install
rather than from a source path, which is what the wiring round needs.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `dd7fe5c9`; no evidence deleted._

### CP-UQ263 addendum 11 — where the wiring plugs in

The composition's injection point is `CampaignPorts` (`parallel_batch/macos_w2_campaign.py:89`):

```text
model_factories : Mapping[str, Callable[[], object]]   # built per Broker, real caller passes the detectors
cancel_goals    : Callable[[], bool] = lambda: True     # cancel controller goals
confirm_absence : Callable[[], bool] = lambda: True     # observe their absence independently
stop_worker     : Callable[[str], bool] = lambda _n: True
clock           : Callable[[], float] = time.monotonic
```

So the wiring round extends this dataclass rather than the campaign's body: a real-station Worker needs
(1) the port itself, built per Worker with `perception_runner=ports.run_perception_chain` and the
Coordinator authority, and (2) the station ownership it starts through `task_station_config` +
`PersistentTaskStack` with `station_environment`. Both are pure injections, which is why the
composition was written with every platform-specific piece behind this seam.

`macos_w2_worker.py` (`cli/`) is the child that would then hold the port: it already speaks the v4
permission-only client for its round trips, so the change is to route those through `W2BrokerPort`
and give it the perception runner instead of calling the client directly.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `3d1c22b4`; no evidence deleted._

### CP-UQ263 addendum 12 — the campaign still passes, from the rebuilt install

`task14-campaign-batch04/` re-runs the production W2 campaign after the four port iterations and the
station-install rebuild:

```text
status    : W2_CAMPAIGN_PASS        (10 s, exit 0)
admission : 6 admitted, 0 refused
cleanup   : complete, directory removed, registry empty, workers reaped [true, true]
```

So the composition that the wiring will extend is still green, and this run used the install that now
contains `macos_w2_broker_port.py`, `station_environment` and the station config. Task 14 remains 0/5
and `LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: `bdefc300`; no evidence deleted._

### CP-UQ263 addendum 13 — correction: the Worker spawn lives in the CLI entry point, not in the library

Checking where the campaign actually spawns its Workers before wiring into it turned up a layer
mistake in my own previous step:

```text
parallel_batch/macos_w2_campaign.py   no supervisor.start, no worker module, no argv builder
cli/macos_w2_worker.py                argv: ack_path, endpoint, worker_id, out_path
```

The composed library owns the Broker, the endpoints, the registry and the outcome document; the
**two-phase spawn of the two Workers belongs to `cli/macos_w2_campaign.py`**, which is why that entry
point is the thing that binds the six request ids before serving. So the `worker_station` /
`worker_broker` seams added in `e154ddc8` sit on `CampaignPorts`, which is the wrong layer for what
they describe: they are properties of the *entry point's* child spawn, not of the library run.

They are harmless there and their test passes, but the wiring round should not follow them. The
sequence is instead:

1. `cli/macos_w2_campaign.py` builds each Worker's station config (`task_station_config`) and its
   Broker port (`W2BrokerPort` with `perception_runner` and the Coordinator authority) and passes them
   to the child - by argv switch, or by having the child import the same helpers with the authority
   it is given;
2. `cli/macos_w2_worker.py` starts the station through `PersistentTaskStack` +
   `station_environment`, then serves its round trips through the port rather than the bare client;
3. the library's `CampaignPorts` keep holding what the *composition* needs, which is what they
   already do.

Left in the record rather than quietly moved, because the next round would otherwise extend the
wrong object - and because "which layer owns the spawn" is exactly the question Task 13's entry point
was created to answer.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `e154ddc8`; no evidence deleted._

### CP-UQ263 addendum 14 — the Worker child can own a station, and the IPC-only path is unchanged

The spawn call in `cli/macos_w2_campaign.py:362` passes exactly four arguments
(`ack_path, endpoint, worker_id, out_path`). Two optional ones now follow them
(`station_session, station_root`); when they are absent the child behaves exactly as before, and when
they are present it starts a visible station through `default_task_station_config` +
`PersistentTaskStack` with `station_environment(base=os.environ)` - the product guard, so a canonical
checkout prefix refuses the launch.

The ACK payload now records whether a station was requested, which is how a reader can tell the two
shapes apart after the fact.

Verified on the unchanged path:

```text
task14-worker-station-01   status W2_CAMPAIGN_PASS, cleanup complete
                           ack "station" flag: [False, False]
```

So adding station ownership did not disturb the campaign that every earlier checkpoint rests on, and
the entry point only needs to pass the two arguments to turn it on.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `2e09f383`; no evidence deleted._

## CP-UQ264 — The W2 campaign now runs with two station-owning Workers

```yaml
checkpoint_id: CP-UQ264
last_valid_experiment: EXP-UQ264-CAMPAIGN-WITH-STATIONS
current_hypothesis: The campaign can carry per-Worker station ownership without disturbing the
  Broker, the one-time admission or the cleanup. CONFIRMED.
working_tree_status: clean at commit below
owned_processes: NONE - the supervisor's process-group cleanup took both stations with their Workers
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - The Worker starts its station but never waits for the ready contract, so this checkpoint proves
    "started and reaped with its Worker", not "ready before the round trips".
  - The Worker still talks to the Broker through the bare v4 client, not through `W2BrokerPort`.
  - Screen Recording is still denied to this session.
next_command: wait for the ready contract inside the Worker, then route its round trips through the port
```

`EXP-UQ264-CAMPAIGN-WITH-STATIONS: VALID` for what it measured, with the limit above stated up front.

### The run

`task14-campaign-stations-01/`:

```text
status    : W2_CAMPAIGN_PASS
acks      : station requested [True, True]
cleanup   : complete
processes : 0 ros2_control_node / move_group left afterwards
```

Each Worker is spawned with a campaign-scoped station session and a Worker-scoped station root
(`<evidence>/wN-station`), so two slots never share a scene, an epoch or an evidence directory - and
the environment still comes from `station_environment`, so a canonical checkout prefix would have
refused the launch rather than shadowing this branch.

That the stations disappeared with their Workers is the ownership property the design asked for: the
supervisor owns the Worker's process group, the station is inside it, and cleanup is exact without a
second reaper.

### What it does not prove, and the next step

The Worker starts its station and then runs its three round trips immediately; it does not wait for
`READY`. So this run does not yet show a station that is ready *before* the Worker uses it - that is
the next change, together with routing the round trips through `W2BrokerPort` (built with
`perception_runner` and the Coordinator authority), which turns the current IPC-only Worker into one
whose inference goes through the shared MPS Broker and the one-time registry.

Task 14 remains 0/5: no pick-place has run inside a campaign, and `LINUX_REGRESSION_DEFERRED` is
retained.

_Ledger source HEAD: `c381f51a`; no evidence deleted._

## CP-UQ265 — Readiness wiring landed, with two gaps I am not going to paper over

```yaml
checkpoint_id: CP-UQ265
last_valid_experiment: EXP-UQ265-CAMPAIGN-READY-WIRING (PASS with unverified internals)
current_hypothesis: Each Worker can wait for its own station's ready contract on its own ROS domain.
  PARTIALLY CONFIRMED: the code path exists and the campaign passes, but the evidence is not yet
  captured and the failure branch is not closed.
working_tree_status: clean after the scoped commit below
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - `station_record` is never written into the Worker's result document, so the readiness outcome is
    not in the evidence.
  - The Worker records the readiness exit code but does not fail on it: a Worker could serve round
    trips after a *failed* readiness check. That is not fail-closed and must be fixed before any
    batch is counted.
  - Screen Recording is still denied to this session.
next_command: write the station record into the result document AND refuse to serve when readiness
  did not pass
```

`EXP-UQ265-CAMPAIGN-READY-WIRING: PARTIAL` - the campaign passes, the readiness internals are not yet
proven, and the failure branch is open.

### What changed

- The entry point passes each Worker its station session, a Worker-scoped station root and **its own
  `ros_domain_id` from the plan** (`plan.ros_domain_ids[slot]`), so the two stations never share a ROS
  graph - closing the gap CP-UQ264 recorded;
- the Worker resolves `motion_stack_ready` from the **package prefix** when PATH does not carry it
  (the first attempt failed closed with `STATION_READY_BINARY_MISSING`, which is the guard doing its
  job rather than a silent skip);
- the Worker starts its station through `PersistentTaskStack` + `station_environment` and then runs
  the readiness check on its own domain before its round trips.

### The run

```text
task14-campaign-ready-04   status W2_CAMPAIGN_PASS, cleanup complete, 0 processes left
                           w1/w2 round trips: 3 x OK each
```

### Two things that run does *not* prove, and the housekeeping around it

The Worker result documents contain the round trips but **no `station_record`**, so the readiness
outcome is not in the evidence; and the Worker stores the readiness exit code without acting on it,
so a failed check would not stop it. Both are defects in my own patch, both are recorded above, and
neither may be glossed over by the campaign's PASS.

Housekeeping, recorded because it was mine: the interrupted run left 19 dead campaign directories
under `/private/tmp/so101-ipc-501/` (empty, or holding a socket with no listener - verified by
attempting a connect on each, none live). They were removed, which is what the design's cleanup is
supposed to do; no *evidence* under the registered task root was touched. Two runs of mine are
recorded as INVALID rather than counted: `task14-campaign-ready-02` (interrupted before any result)
and `task14-campaign-ready-03` (gate refused because I had pre-created/reused its run root - my third
harness mistake of this kind, already noted in CP-UQ260's addenda).

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `922e8dc7`; no evidence deleted._

## CP-UQ266 — The readiness gap is closed, and it immediately refused both Workers

```yaml
checkpoint_id: CP-UQ266
last_valid_experiment: EXP-UQ266-STATION-READY-FAIL-CLOSED
current_hypothesis: With the station record written and the failure branch closed, the campaign
  either proves readiness or refuses. It refused - which is the correct outcome of the fix.
working_tree_status: clean after the scoped commit below
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - Both stations stop at phase CONTROLLERS inside the campaign Worker, while the same station
    reached READY in ~15 s when a probe started it - the difference is not yet diagnosed.
  - Screen Recording is still denied to this session.
next_command: compare the Worker-started station against the probe-started one (env, argv, ros-log)
```

`EXP-UQ266-STATION-READY-FAIL-CLOSED: VALID` for the fix; the campaign itself is INCOMPLETE, not PASS.

### The two gaps are closed

- the Worker now writes `station_record` into its result document, so the readiness outcome is
  evidence rather than a variable;
- a non-zero readiness exit **stops the Worker before it serves anything**, writes a document naming
  `STATION_NOT_READY`, and exits - a Worker can no longer drive a station it could not prove ready.

### What the fixed code then reported

```text
task14-campaign-ready-05   status W2_CAMPAIGN_INCOMPLETE (exit 7), cleanup complete
w1-result.json  ready=False phase=CONTROLLERS domain=181 exit=1 trips=0 failure=STATION_NOT_READY
w2-result.json  ready=False phase=CONTROLLERS domain=182 exit=1 trips=0 failure=STATION_NOT_READY
```

Two facts worth separating:

1. **the per-slot domain wiring is proven**: each Worker's station ran on the domain the plan gave it
   (181 and 182), which is what CP-UQ264 could not show;
2. **readiness now fails visibly** instead of being skipped - and it fails at `CONTROLLERS`, where the
   probe-driven station reached `READY` in ~15 s on the very same domains
   (`task14-w2-stations-guard-01`).

So the campaign Worker's station is configured differently from the probe's, and that difference is
the next thing to find: the probe used `task_station_config(worker)` (with `sensor_rendering:=true`
and the allocator's per-Worker environment), while the child uses
`default_task_station_config(session, root)` with `station_environment(base=os.environ)` plus the
domain. Both are plausible causes and neither is established yet.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `c59f5273`; no evidence deleted._

## CP-UQ267 — The Worker's station now launches; the failure is the gate runner's PYTHONPATH surgery

```yaml
checkpoint_id: CP-UQ267
last_valid_experiment: EXP-UQ267-WORKER-STATION-LAUNCH-DIAGNOSIS
current_hypothesis: The Worker-started station fails at CONTROLLERS because of its configuration.
  DISPROVEN: it failed because the package was not on the prefix path, and then because the gate
  runner strips the station install's site-packages.
working_tree_status: clean at commit 1eb96d9c
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - The campaign needs its own runner that sources the station chain without the unit-gate PYTHONPATH
    surgery; `run-gate.sh` is a pytest runner and mangles exactly what a station needs.
  - Screen Recording is still denied to this session.
next_command: add `run-w2-campaign.sh` (station-env.sh chain, no PYTHONPATH stripping) and re-run
```

`EXP-UQ267-WORKER-STATION-LAUNCH-DIAGNOSIS: VALID` as a diagnosis; the campaign is INCOMPLETE.

### Two failures, two different causes, both found in the logs

```text
task14-campaign-ready-05 (branch overlay only)
  launch: "package 'mujoco_ros2_control' not found, searching: ['<branch>/install/so101_demo_py', …]"
  -> the campaign ran with an overlay that holds only so101_demo_py; the MuJoCo stack lived in the
     canonical install, which station_environment correctly refused to let through. The guard did
     its job and the consequence was honest: no station at all.

task14-campaign-ready-06 (station install as the overlay)
  launch proceeds (66 log lines, controllers load), then
  [ERROR] [scene_setup-9]: process has died, exit code 1
  traceback: importlib.metadata -> distribution('so101-demo-py') -> StopIteration
  -> `run-gate.sh` strips `$GATE_INSTALL_OVERLAY/*` (including the install's site-packages) from
     PYTHONPATH by design, so the installed console script cannot find its own distribution.
```

So neither failure was a station-configuration problem; the first was the environment guard working,
the second is my own gate runner being a *pytest* runner and mangling what a launched station needs.
The Worker-side plumbing itself is now behaving: it starts the station, insists on a ready contract,
records the outcome, and refuses to serve without it.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `bc26f324`; no evidence deleted._

## CP-UQ268 — Both W2 Workers now own a READY station on their own domain

```yaml
checkpoint_id: CP-UQ268
last_valid_experiment: EXP-UQ268-W2-CAMPAIGN-READY-STATIONS
current_hypothesis: With a runner that keeps the station chain intact, the campaign's Workers can
  reach the ready contract before serving. CONFIRMED for both slots.
working_tree_status: clean - harness runner only, no product change in this round
owned_processes: NONE - supervisor cleanup, 0 processes left
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - The Workers still serve round trips rather than inference through `W2BrokerPort`; the port is
    written and tested but not yet bound.
  - Screen Recording is still denied, so per-point GUI capture and any counted batch remain blocked.
next_command: bind `W2BrokerPort` into the Worker and make its round trips real inferences
```

`EXP-UQ268-W2-CAMPAIGN-READY-STATIONS: VALID`

### The run

`task14-campaign-ready-08/`:

```text
status : W2_CAMPAIGN_PASS        cleanup complete

w1 | station ready: True  phase READY  ROS_DOMAIN_ID 181  round trips 3  failure None
     controllers: arm_controller active, gripper_controller active,
                  joint_state_broadcaster active
w2 | station ready: True  phase READY  ROS_DOMAIN_ID 182  round trips 3  failure None
     controllers: arm_controller active, gripper_controller active,
                  joint_state_broadcaster active
```

That is the structural chain Task 14 needs, end to end and in one process tree: exact W2, a visible
station per slot, **each on its own ROS domain**, **each proven ready before it serves**, one shared
MPS Broker with one-time admission, and exact cleanup by the supervisor.

### Why it works now, and what that says about the earlier failures

The only change was the runner: `run-w2-campaign.sh` sources the validated chain
(underlay -> `extra_ws` -> this branch's station install), refuses any surviving canonical prefix,
and - unlike the pytest gate runner - leaves the station install's `site-packages` on `PYTHONPATH`,
so an installed console script can find its own distribution. CP-UQ267's two failures were therefore
both harness-shaped: one was the environment guard refusing a canonical prefix (correct), the other
my pytest runner deleting what a launched station needs.

Task 14 remains 0/5: no pick-place has run inside a campaign, the Workers' inference still goes
through the bare client rather than the port, and `LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: `8fe50f43`; no evidence deleted._

### CP-UQ268 addendum — the stations outlived their Workers, and my cleanup missed them

Immediately after the PASS was written, eight processes matching
`ros2_control_node|move_group|robot_state_publisher|spawner` were still alive: the two stations had
**outlived the two Workers** that started them, even though the campaign reported `cleanup complete`.

That report was accurate for what the supervisor owns - the Worker process group - and the defect is
in the Worker child: it starts a `PersistentTaskStack` and never shuts it down, so whether the station
dies with the Worker depends on the process-group membership of the `ros2 launch` the stack spawned.
When that launch lands in its own group, the supervisor's group kill cannot reach it.

Recorded as a real product defect to fix (the child must shut its station down in a `finally`, the way
its own ownership object is designed to), and the eight processes were reaped by exact PID after
confirming they belonged to this run. Task 14 stays 0/5 and `LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: `f10e685c`; no evidence deleted._

### CP-UQ268 addendum 2 — the orphan defect is fixed and the check is now part of the gate

The Worker's serving section is wrapped in `try/finally`, so the station it started is shut down on
every exit path - the success path, the `STATION_NOT_READY` refusal, and any exception in between.
The comment in the code records why this belongs to the Worker rather than the supervisor: the
supervisor owns the Worker's process group, but the launch the stack spawns can land in its own group,
so a group kill cannot reach it.

Re-run, with the process check as the acceptance criterion:

```text
task14-campaign-ready-09   status W2_CAMPAIGN_PASS, cleanup complete
                           w1 ready True phase READY domain 181 trips 3
                           w2 ready True phase READY domain 182 trips 3
                           orphans after the campaign: []      <- the fix, measured
```

Until this commit the PASS and "eight processes still alive" were both true at once, which is exactly
the kind of gap a status document hides; from now on the orphan check runs with every campaign I count.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `38505d56`; no evidence deleted._

### CP-UQ268 addendum 3 — what the port needs before it can replace the bare client

Reading the campaign's server side settles the scope of the last wiring step:

```text
binding     cli/macos_w2_campaign.py:329  campaign.request_binding(
                request_id=f"{worker_id}-req-{index:02d}", slot_id=…, point_id=…, attempt=1,
                input_sha256=…, deadline_s=300, broker_pid=…, broker_birth_identity=…)
server      handler(request) ignores `request.operation`: it runs one real YOLO forward pass on the
            shared lane and returns {"request_id", "device", "candidates"}
```

Three mismatches stand between that and the port:

1. **the operation is ignored** - the port sends `infer` with a serialized `InferenceRequest` and
   snapshot, and expects the refusal signal (`ok=False`) to be meaningful;
2. **the identifiers do not line up** - the Worker's port derives
   `request_id = f"{lease.attempt_id}-{model_id}"`, while the campaign binds `w1-req-00…`; the
   one-time table is the admission gate, so either the binding must be produced from the same
   identity the Worker will use, or the Worker must be told which ids it owns;
3. **the Worker has no lease and no snapshot** - `request_one` needs `attempt_id`, `batch_id`,
   `coordinator_epoch`, `worker_id`, `worker_generation`, `point_id`, `lease_generation` plus a
   snapshot descriptor (`path`, `shape`, `sha256`, `source_stamp_ns`, `source_frame_id`), and the
   campaign's child currently has none of them.

So the next step is not "swap the client": it is to pass the Worker the lease identity and a snapshot
descriptor (the campaign already knows both ends of the identity it binds), teach the server to honour
`infer` and to answer the refusal the port checks, and only then route the round trips through
`W2BrokerPort` - at which point the Worker's inference also stops being a stub and becomes a real
model call admitted by the one-time table.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `657f118b`; no evidence deleted._

### CP-UQ268 addendum 4 — mismatch 1 of 3 is closed, and the campaign is unchanged

The campaign's server now distinguishes the two shapes that reach it:

```text
infer            -> the production path: the Worker's serialized InferenceRequest + snapshot;
                    answers {"ok": True, "request_id", "device", "candidates"}, or refuses with
                    {"ok": False, "code": "INVALID_REQUEST"} when the request cannot be tied to a
                    bound id - the refusal signal the port checks;
anything else    -> the IPC-shape probe this entry point has served since Task 13, unchanged.
```

Both run the same real forward pass on the shared lane.

Verification, with the orphan check included as it now always is:

```text
task14-campaign-ready-10   status W2_CAMPAIGN_PASS
                           served: 6, devices ['mps'], lane {executed 13, max_concurrent 1, rejected 0}
                           cleanup complete, orphans []
```

Remaining mismatches from addendum 3: the identifiers (the Worker derives
`{attempt_id}-{model_id}` while the campaign binds `wN-req-NN`) and the Worker's missing lease and
snapshot descriptor. Those two are the next step, and they are one change: the entry point already
knows both ends of the identity it binds, so it can bind the id the Worker will use and hand the
Worker the lease document plus a snapshot descriptor for the frame it is told to send.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `2241d972`; no evidence deleted._

## CP-UQ269 — An "additive" binding change broke a passing gate, and I reverted it

```yaml
checkpoint_id: CP-UQ269
last_valid_experiment: EXP-UQ269-BINDING-CHANGE-REVERTED
current_hypothesis: Binding the ids the Worker will derive, and handing it a lease document, is an
  additive change that leaves the campaign passing. DISPROVEN by the run.
working_tree_status: clean - the change is fully reverted and the gate is green again
owned_processes: NONE - four orphaned station processes were reaped by exact PID
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - The cause of the regression is not understood: one Worker's three round trips were served and
    the other's were not, with two stations left behind.
  - Screen Recording is still denied to this session.
next_command: cover the CLI binding path with a test before touching it again
```

`EXP-UQ269-BINDING-CHANGE-REVERTED: INVALID` - the run it produced is not evidence of anything except
that the change was wrong.

### What was tried

Writing a per-Worker lease document (`wN-lease.json`) with the identities the Worker will use, binding
`{attempt_id}-yolo` alongside the existing `wN-req-NN` probe ids, and appending the lease path as a
fourth station argument (which the child ignores until it is taught to read it).

### What happened

```text
task14-campaign-ready-11   status W2_CAMPAIGN_INCOMPLETE, served 3 (not 6), cleanup "complete"
                           orphans left: 4 processes, reaped by exact PID afterwards
```

Both lease documents were written, so the entry point reached that code; one Worker served its three
trips and the other never did. The change touches binding and file creation, not the station path, so
the mechanism is not obvious from the outside - which is precisely why the honest move was to revert
first and diagnose with a test rather than to keep iterating against a live campaign.

### After the revert

```text
task14-campaign-ready-12   status W2_CAMPAIGN_PASS, served 6
                           orphans []
```

So the gate is green again and the tree carries no half-change. The next attempt at mismatches 2 and 3
starts by covering the CLI's binding and lease-document path with a test - the two previous rounds
that went well both began by reading the caller, and this one shows what happens when a live
integration run is the first thing to see a change.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `695169c3`; no evidence deleted._

### CP-UQ269 addendum — test-first scaffolding, and it is explicitly not wired

Following the lesson of the revert, the lease and binding logic now exists as two tested functions in
`cli/macos_w2_campaign.py`:

```text
build_worker_leases(*, plan, batch_id, evidence_root, input_sha256) -> dict[str, dict]
    writes each Worker's lease document + its frame once, and records the identity it owns
bind_worker_requests(campaign, leases, *, ready, deadline_s=300.0)
    binds every `{attempt_id}-{model_id}` id the Worker will derive, before anything is served
```

`task14-lease-helpers-01`: **1 passed** - it asserts the ids the Worker derives, the per-slot domain
and point assignment, that the lease file on disk matches the returned document, and that the bindings
carry the Broker identity and input digest.
`task14-lease-helpers-regression-01`: **34 passed** for the campaign and composition suites.

**These functions are not called by `main()` yet.** That is deliberate and worth stating plainly: the
previous attempt made the change and the live campaign was the first thing to see it, which cost a
round and left the mechanism unexplained. The next step is to make `main()` use exactly these
functions - so the campaign's live run tests wiring, not logic - and to re-run the campaign with the
orphan check.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `a5efe043`; no evidence deleted._

### CP-UQ269 addendum 2 — the helpers are wired, and mismatch 2 is closed

`main()` now builds the lease documents and binds the Worker-derived ids through the two tested
functions, passing the lease path to each Worker as a fourth station argument. The IPC-shape probe
ids stay bound alongside them, so the shape the previous gate proved cannot be silently refused.

```text
task14-campaign-ready-13   status W2_CAMPAIGN_PASS, served 6, cleanup complete
                           w1 ready True phase READY trips 3 failure None
                           w2 ready True phase READY trips 3 failure None
                           orphans []
```

So the admission table now speaks the same vocabulary the Worker's port does
(`{attempt_id}-{model_id}`), which was mismatch 2 of 3 from addendum 3.

Honest note on the earlier revert: this run passes with essentially the content that failed as
`task14-campaign-ready-11`. The difference I can identify is ordering - the failing attempt wrote the
lease files inside the same loop that bound, this one writes them before binding and before the spawn
loop - and I have not proven that is the mechanism. It is recorded as unexplained rather than as
"fixed", because a passing run after a revert is not a diagnosis.

Remaining: mismatch 3 - the Worker still cannot *use* that identity, because it neither reads the
lease document nor builds the snapshot descriptor and lease object the port's `request_one` needs.
That is the next step, and the helpers' test means the entry-point side of it is now covered.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `9b47c64c`; no evidence deleted._

### CP-UQ269 addendum 3 — the port now really calls the Broker, and the contract answers

The Worker reads its lease document and issues three `infer` calls through `W2BrokerPort` against the
live Broker, in addition to the IPC-shape probes. The campaign passes and the failures are now
*contract* answers rather than silence:

```text
task14-campaign-infer-03   status W2_CAMPAIGN_PASS, served 6 (probe shape), orphans []
w1/w2 infer_results: 3 x {"request_id": "wN-att-NN-yolo", "status": "ERROR",
                          "error": "ContractError: EMPTY_ID: reset_epoch"}
```

So the whole path is connected - lease document -> port -> `V4PermissionOnlyClient` -> campaign
server -> refusal - and the first real request is refused by `InferenceRequest`'s own validation,
which is the contract doing its job rather than the plumbing failing silently. Two harness mistakes of
mine were fixed on the way, both worth naming because they cost runs: I inserted the new block in the
middle of the `try:` I had added earlier (IndentationError), and the block used `Path` while the
module only imported it locally (NameError, which killed both Workers before they wrote anything).
Four orphaned station processes from that run were reaped by exact PID.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `c48c0b46`; no evidence deleted._

## CP-UQ270 — Worker inference now really runs on the shared MPS Broker

```yaml
checkpoint_id: CP-UQ270
last_valid_experiment: EXP-UQ270-WORKER-INFERENCE-THROUGH-PORT
current_hypothesis: The Worker can send a real inference request through `W2BrokerPort`, admitted by
  the one-time table and executed on the shared MPS lane. CONFIRMED.
working_tree_status: clean after the scoped commit below
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - The Worker's inference uses a synthetic warm frame, not an RGB-D snapshot from its own station;
    the pick-place chain (perception -> pose admission -> plan -> execute) is still unwired.
  - Screen Recording is still denied to this session.
next_command: feed the Worker a real snapshot from its station and drive the point chain
```

`EXP-UQ270-WORKER-INFERENCE-THROUGH-PORT: VALID`

### The run

```text
task14-campaign-infer-05   status W2_CAMPAIGN_PASS, served 12 (6 IPC-shape + 6 real infer)
                           w1 infer: 3 x {"request_id": "w1-att-00-yolo", "status": "OK",
                                          "device": "mps"}
                           orphans []
```

That is the production path, end to end and inside the campaign: the Worker reads the identity the
entry point bound for it, derives `{attempt_id}-yolo`, sends it through `W2BrokerPort` over the
permission-only v4 socket, the campaign's server runs a real YOLO forward pass on the shared lane and
answers, and the device is `mps`.

### The three mismatches, closed in order

| # | Mismatch | Closed by |
| --- | --- | --- |
| 1 | the server ignored `request.operation` | a `broker.infer` branch that answers `ok`/refuses |
| 2 | the table bound ids the Worker does not derive | entry point binds `{attempt_id}-{model_id}` and hands over the lease |
| 3 | the Worker had no lease, snapshot or port | the Worker reads the lease, builds the descriptors, and calls the port |

Three details were found by letting the contract answer rather than by guessing: `reset_epoch` is a
non-empty *identifier* string, not a number (`EMPTY_ID: reset_epoch`); the v4 vocabulary is dotted, so
the operation is `broker.infer` and not `infer` (`UNKNOWN_OPERATION`); and a worker's `cancel_generation`
maps to `coordinator.cancel_request` in that vocabulary. My own port test asserted the wrong operation
name until this round, which is why the test passed while the protocol refused the call.

Task 14 remains 0/5: this is inference plumbing, not a pick-place batch, and
`LINUX_REGRESSION_DEFERRED` is retained.

_Ledger source HEAD: `e16bd706`; no evidence deleted._

## CP-UQ271 — What is left of Task 14, measured against the remaining budget

```yaml
checkpoint_id: CP-UQ271
last_valid_experiment: none - this is an assessment, not a run
current_hypothesis: The remaining Task 14 work can be finished inside this goal's budget. Assessed as
  NOT reachable, for two independent reasons.
working_tree_status: clean at commit 6999c438
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - A counted batch needs per-point `viewer.png`; Screen Recording is denied to this session and has
    been for ~70 rounds, so no batch can pass its terminal capture.
  - The Worker is a spawned CLI process, while the perception/planning/execution chain
    (`ParallelWorkerRuntime` + `ParallelRosRuntimePorts` + `ParallelWorker`) is an in-process
    library: joining them is a port of the Linux batch path, not a wiring change.
next_command: decide Task 16's verdict on the evidence that exists; do not start the port speculatively
```

### What exists and is verified (the macOS, exact-W2 half)

- frozen v3 + closed v4 schema, Darwin MPS start guard, durable supervisor ownership, permission-only
  v4 IPC, immutable snapshots, one-time request registry, single-lane shared MPS Broker;
- exact-W2 resource allocation on Darwin (two Workers, domains 181/182, own roots);
- both Workers own a visible station, **each proven READY on its own domain before serving**
  (`task14-campaign-ready-08`, `-12`, `-13`), with the orphan check clean from `task14-campaign-infer-*`;
- **real inference through the port on the shared MPS Broker**, `device: mps`
  (`task14-campaign-infer-05`, CP-UQ270);
- a real four-point MuJoCo pick-place batch executed from this branch's install
  (`task14-single-batch-01`), with MoveIt trajectories, contacts and placement evidence - run outside
  the campaign, and every point failed only at `TERMINAL_CAPTURE_FAILED`.

### What a counted Task 14 batch still requires

1. **the perception/plan/execute chain inside each Worker** - today the Worker's inference is real but
   its input is a synthetic warm frame; feeding it a station RGB-D snapshot and driving
   `ParallelWorker`/`BatchCoordinator` means porting the in-process Linux batch path onto the spawned
   macOS Worker;
2. **per-point `viewer.png`** - blocked by macOS TCC for this session's responsibility chain, which is
   why every point of the one real batch failed at `TERMINAL_CAPTURE_FAILED`;
3. **five consecutive `FULL_RESTART` batches** with fresh epochs, IPC paths and Broker generations -
   none started, so Task 14 stands at **0/5**.

Items 1 and 3 are engineering; item 2 is a permission the user has been asked for since round 9 and
that cannot be granted from inside the session. With ~20 rounds of budget left and a port of that size
ahead, the honest conclusion is that Task 14 will not be counted in this goal, and Task 16 must report
**`PARTIAL`** with exactly these gaps - not `MACOS_MPS_W2_PASS`, and not silence about the Linux half
either, which stays `DEFERRED_ENVIRONMENT`.

_Ledger source HEAD: `6999c438`; no evidence deleted._

## CP-UQ272 — Task 15: the Linux regression checkpoint, registered and not executed

```yaml
checkpoint_id: CP-UQ272
last_valid_experiment: none - this task registers a deferral; it runs no Linux command
working_tree_status: clean at commit c8e5c583
owned_processes: NONE
open_risks:
  - Every Linux gate below is unrun. None may be reported as PASS, SKIP or N/A.
next_command: none until a Linux CUDA/NVML environment exists
```

Task 15 of the plan requires exactly this text and nothing executed:

```text
status: DEFERRED_ENVIRONMENT
reason: no Linux environment available
resume_when: Linux CUDA/NVML environment is ready
required_gates: schema-v3 CUDA/NVML; schema-v4 CUDA+proc_fd_unix; EGL; real Broker device; package/CTest; exact W2
```

The macOS results do **not** substitute for any of it. `ai-station-001-lin` (100.82.102.56) was last
seen offline earlier in this task and `macbook-air` refuses the connection (host key verification), so
no Linux host was reachable at any point in this session; no Linux command has been run, and the
following claims remain blocked by `LINUX_REGRESSION_DEFERRED`:

- cross-platform validity of schema v4 (the two closed combinations are defined, but only the Darwin
  one has ever executed);
- Linux CUDA/NVML admission, `proc_fd_unix` transport, EGL rendering and a real `cuda` Broker device;
- Linux package/CTest gates and a Linux exact-W2 campaign;
- any main-branch merge or release claim that depends on the Linux half.

_Ledger source HEAD: `c8e5c583`; no evidence deleted._

### CP-UQ272 addendum — tmux was restarted; Screen Recording still is not granted to it

The restart the user was asked for did happen, and the permission still does not apply:

```text
tmux server : pid 10775, started Sun Sep 20 01:14:19 2026 (was pid 59433 from 21:13:49)
identity    : tmux-55554944a40667abf836332cab24562eec45b0ba   <- unchanged, so the grant would apply
Accessibility: GRANTED (System Events still answers with a live process list)
Screen Recording: DENIED  - screencapture -x -> "could not create image from display"
```

Because the binary's code identity did not change, a restart with an enabled grant should have been
enough. It was not, which points at the grant itself rather than at process lifetime: the entry for
tmux is either present-but-off in **System Settings -> Privacy & Security -> Screen & System Audio
Recording**, or it points at a different binary than `/opt/homebrew/bin/tmux` (for example the
Cellar path behind the symlink). TCC keys Screen Recording on the responsible process's identity, and
for this session that is `tmux`; the terminal application is not in the chain.

Until that toggle is genuinely on, every per-point `viewer.png` fails closed, and with it any counted
Task 14 batch - this remains the single external condition on the macOS side.

_Ledger source HEAD: `ade2136e`; no evidence deleted._

## CP-UQ273 — Task 16 in progress: the scoped final checks that can run without GUI or Linux

```yaml
checkpoint_id: CP-UQ273
last_valid_experiment: EXP-UQ273-FINAL-SCOPED-CHECKS
working_tree_status: clean; head at the commit below
owned_processes: NONE
open_risks:
  - The verdict is not yet written; the remaining Task 16 items are the per-task evidence table, the
    retained/archived/deletion-candidate classification and the PARTIAL statement.
next_command: write the Task 16 report and classify the evidence
```

```text
git diff --check                      clean
ordinary suite collection             3531 tests collected (src/so101_demo_py/test, benchmark suite
                                      not collected by this gate)
```

Two forward references to keep honest: this session added its own tests (broker port, station
environment guard, guard selector forms, lease/binding helpers, campaign seams), so the count is not
directly comparable to the 3487 recorded in Task 12 - what matters for the gate is that collection is
non-zero and that the benchmark suite is excluded, both of which hold.

The evidence classification Task 16 requires, stated now so the final report does not have to
reconstruct it:

- **retained (the load-bearing records)**: `impl-macos-mps-w2-01/` (runners, probes, environment),
  `station-build-01/` (the branch's own install), `model-artifacts/` (verified weights), the campaign
  and station runs named in CP-UQ248-CP-UQ272, and the ledger itself;
- **archived (superseded but auditable)**: the task0/task1 baseline runs, the source/collected gates
  superseded by later reruns, and the invalidated gates this session recorded explicitly
  (`task11-teleop-01/02`, `task11-openapi-01/02/03`, `task14-campaign-ready-02/03`, `-11`, the
  `task14-*-probe-*` capture probes);
- **deletion candidates (no delete without authorisation)**: `test-byproducts/`, the per-run `tmp/`
  trees, and the 19 dead IPC campaign directories already removed under `/private/tmp/so101-ipc-501`
  (those were transient runtime residue, not evidence, and their removal is recorded in CP-UQ265).

Nothing has been deleted from the evidence root, and the Linux deferral from CP-UQ272 stands.

_Ledger source HEAD: `b1c1a8ab`; no evidence deleted._

## CP-UQ274 — Task 16: the macOS evidence, requirement by requirement

```yaml
checkpoint_id: CP-UQ274
last_valid_experiment: EXP-UQ274-FINAL-MATRIX
proposed_verdict: PARTIAL (MACOS_MPS_W2_PASS is NOT met - Task 14 stands at 0/5)
independent_verdict: OWED - the plan requires gpt-5.6-sol/high, which this DST session cannot invoke;
  recording the limitation rather than substituting a model
working_tree_status: clean
owned_processes: NONE
next_command: independent review, or close the goal with PARTIAL as proposed here
```

Against design §9.1, with the evidence each line rests on:

| Requirement | Status | Evidence |
| --- | --- | --- |
| schema v3 frozen, v4 closed contract + illegal combinations + CPU fallback RED/GREEN | MET | `task1-*`, `refreeze-*`, `entrypoint-regression-04` 177 passed |
| inherited `PYTORCH_ENABLE_MPS_FALLBACK=1` fails closed before `import torch` | MET | `test_mps_broker_bootstrap.py`, `task8-mps-bootstrap-smoke-01`, `torch-import-probe-*` |
| MPS start guard, fixed headroom, 2 s deadline, claim conflict, pre-spawn rejection, metric provenance | MET | `start-guard-macos-01/02/03`, `task14-w2-resources-green-17` (admission `unified-memory-proxy`) |
| Supervisor keeps the claim after a Coordinator crash; durable `SPAWNING` before spawn; ACK before `ACTIVE` | MET | Task 13 smokes, `task14-campaign-batch02/03/04`, `composed-campaign-01` |
| private short path, permissions, length checks, two-Client round trips, negative paths, restart, cleanup | MET | `ipc-macos-probe-01`, `test_parallel_ipc_v4.py`, `task13-w2-runtime-smoke-01/02` |
| immutable snapshot descriptor tests | MET | `test_input_snapshot*`, `test_parallel_perception_runtime.py` |
| real models on MPS, warm-up, `synchronize()`, ready receipt matching the device | MET | `task13-w2-real-models-03`, `refreeze-real-model-load.json` (Grounded SAM 203M on `mps:0`, YOLO 2.83M + inference 274.6 ms) |
| exact W2: two slots, one Broker/model set, per-slot progress/result/evidence | **PARTIAL** | allocation and stations MET (`task14-w2-stations-guard-01`, `task14-campaign-ready-08/12/13`); real inference through the port MET (`task14-campaign-infer-05`, `device: mps`); **per-slot pick-place evidence NOT produced** |
| request register/one-time consume, queue full, inference timeout, Worker cancel, Broker crash pool rebuild, late/duplicate rejection, controller goal absence | **PARTIAL** | registry, queue-full, late/duplicate and rebuild evidence exist (`v4-queue-*`, `composed-campaign-01`); the three fault evidences were written for the IPC shape, not inside a counted batch |
| fresh build/package/OpenAPI/copied-install/served-byte gates in a valid macOS ROS environment | **PARTIAL** | `task12-fresh-build-01/02`, `task12-package-gate-01`, `task12-copied-install-01/02`, `task12-served-bytes-01`, `task11-web-*`; `colcon test`/CTest is INVALID on this host (DYLD bootstrap), so the package gate is a direct pytest gate and the source gate carries 234 pre-existing environment failures |
| MoveIt shadow, controller/joints, MuJoCo pose/contact/detach/release/final placement with a fresh epoch | **PARTIAL** | one real four-point batch produced MoveIt trajectories, `table_contact`, forces and placement (`task14-single-batch-01`) - outside the campaign, and every point failed at `TERMINAL_CAPTURE_FAILED` |
| fresh GUI evidence as snapshot/action/snapshot | **NOT MET** | blocked by macOS TCC for this session's responsibility chain (`task14-capture-probe-01..14`, `task15-capture-probe-01`); tmux was restarted (pid 10775) and the grant still does not apply |
| five consecutive valid `FULL_RESTART` simulation batches | **NOT MET** | Task 14 = 0/5; none started |
| Linux regression (Task 15) | DEFERRED | CP-UQ272; never run, never reported as PASS/SKIP/N/A |

### Proposed verdict

**`PARTIAL`.** The macOS exact-W2 platform work is real and evidenced - frozen contract, MPS
admission, durable ownership, permission-only IPC, one-time admission, a shared single-lane MPS
Broker, exact-W2 allocation, two visible stations each proven ready on its own domain, and inference
through the port with `device: mps`. What is missing is the *task* half: no pick-place batch has run
inside the campaign, so there is no per-slot physical evidence, no five-batch stability series, and no
fresh GUI capture - the last of which is a permission this session cannot grant itself.

Two things must not be smoothed over in any summary: Task 14 is **0/5**, and
`LINUX_REGRESSION_DEFERRED` still blocks cross-platform and release claims.

_Ledger source HEAD: `87e44239`; no evidence deleted._

### CP-UQ274 addendum — platform stability: three more consecutive campaign runs

Run back-to-back, with the orphan check after each:

```text
task16-stability-01   exit 0   W2_CAMPAIGN_PASS   orphans 0
task16-stability-02   exit 0   W2_CAMPAIGN_PASS   orphans 0
task16-stability-03   exit 0   W2_CAMPAIGN_PASS   orphans 0
```

Each run composes the exact-W2 campaign from scratch: fresh claim, fresh campaign IPC root, fresh
Broker generation, two Workers that own a station each on their own domain, both stations proven ready,
six probe round trips and six real `broker.infer` calls through the port, then exact cleanup.

This is **platform stability, not Task 14's five `FULL_RESTART` simulation batches**, and the
distinction matters in both directions: these runs carry no pick-place, no MoveIt shadow, no MuJoCo
contact/placement evidence and no GUI capture, so they cannot be counted toward `five_batch_stability`;
what they do show is that the composed macOS runtime now starts, serves and cleans up repeatably
rather than once.

_Ledger source HEAD: `332485ea`; no evidence deleted._

### CP-UQ274 addendum 2 — the fault evidence that is *not* GUI-blocked, and how to produce it

Screen Recording was probed once more this round (`task16-capture-probe-01`, still
`could not create image from display`), so the counted-batch half stays blocked. The fault evidences
the plan asks for - Broker crash with a full W2 pool rebuild, inference timeout, active-Worker cancel -
are *not* GUI-blocked, and the machinery to produce the first one for real is now mapped:

```text
CampaignSupervisor.terminate_all() -> CleanupReceipt          (campaign_supervisor.py:597)
OwnershipReceipt.live_children() / .unresolved()              (210-217)  SpawnIntent per child
SpawnIntent.to_document() / resolved()                        (115-155) pid + birth identity + role
```

So a live injection is: let the campaign serve a few requests, read the ownership receipt, take the
`broker` child's exact PID and birth identity, signal exactly that process, then record what the
composition does next - the design's answer being a whole-pool rebuild on a new generation and a new
campaign IPC path, with the old bindings invalidated.

The entry point needs a small, explicit switch for that (never an automatic kill), and the run's
evidence must show the new generation, the new endpoint, both Workers restarted and the cleanup still
exact. That is the next piece of work: it is reachable inside the remaining budget, it needs no GUI
permission, and it closes an acceptance item that is currently marked PARTIAL.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `68fcebe8`; no evidence deleted._

### CP-UQ274 addendum 3 — the "Broker crash" cannot be injected here, and why that is a finding

`--crash-broker-after-served N` was added to the entry point as an explicit, one-shot fault switch.
The first run with it (`task16-broker-crash-01`) exited **137** with no result document: the signal
went to `ready.broker_pid`, and in this composition that PID is **the campaign process itself** -
`models` and `bootstrap.lane` live in-process, so there is no separate Broker child to crash.

The switch now refuses that case instead of committing suicide:

```text
if int(ready.broker_pid) == os.getpid():
    document["broker_crash"] = {"pid": …, "refused": "BROKER_IS_THIS_PROCESS"}
    return {"ok": False, "code": "BROKER_IS_THIS_PROCESS", …}
```

Two consequences worth stating plainly:

1. **a live Broker-crash + pool-rebuild injection is not reachable in this composition.** The design's
   rebuild path belongs to a Supervisor that owns a Broker *process*; the macOS campaign runs its MPS
   lane in-process, so the plan's "Broker crash" evidence cannot be produced from here without first
   changing the composition to spawn the Broker as an owned child - which is the same
   spawned-vs-in-process gap that already blocks the pick-place chain (CP-UQ271);
2. the SIGKILLed run left a campaign IPC directory behind (`b-2816165253b2`), because a process killed
   with SIGKILL cannot run its cleanup - a real limitation of the design that only shows up under
   external SIGKILL, and the reason the next run was refused by the inventory until the residue was
   verified dead and removed.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `b6293a35`; no evidence deleted._

### CP-UQ275 addendum — the refusal is verified live, and it proves the PID identity

```text
task16-broker-crash-03   exit 0, status W2_CAMPAIGN_PASS, served 12
                          broker_crash: {"pid": 15937, "refused": "BROKER_IS_THIS_PROCESS"}
                          cleanup complete, orphans []
```

The recorded PID is the campaign's own process, so the claim in addendum 3 is not an inference from
the exit code any more: the composition's `broker_pid` **is** the campaign process. The injection is
refused, written down, and the campaign carries on to a complete, orphan-free run - which is the right
behaviour for a switch that must never be able to destroy its own evidence.

_Ledger source HEAD: `cfb2cbb9`; no evidence deleted._

## CP-UQ276 — Task 16: final report and verdict

```yaml
checkpoint_id: CP-UQ276
verdict: PARTIAL
macos_mps_w2_pass: NOT WRITTEN - Task 14 stands at 0/5
linux_regression: DEFERRED_ENVIRONMENT (CP-UQ272), never run, never reported as PASS/SKIP/N/A
independent_verdict: OWED - the plan requires gpt-5.6-sol/high; this DST session cannot invoke it, and
  no substitute model was used
working_tree_status: clean
owned_processes: NONE
```

### What this task delivered, with the evidence that carries it

1. **Frozen v3 + closed schema v4** - the two platform combinations are defined and illegal ones fail
   closed; v3 semantics are byte-frozen (`task1-*`, `refreeze-*`, `entrypoint-regression-04`, 177
   passed).
2. **Darwin MPS admission** - `PYTORCH_ENABLE_MPS_FALLBACK` checked before `import torch`, guard scope
   built from the resolved accelerator, `unified-memory-proxy` admission, 2 s deadline.
3. **Durable ownership** - claim, `SPAWNING` intent before spawn, registration ACK before `ACTIVE`,
   exact-signal only on matching PID and birth identity, exact cleanup. Three consecutive campaigns
   plus every earlier run ended with zero orphans (`task16-stability-01..03`).
4. **Permission-only v4 IPC** - private short path, `0700`/`0600`, no token/generation/lease in either
   direction, bounded queue, stable refusal codes.
5. **Exact-W2 on macOS** - two Workers, domains 181/182, their own roots; each owns a visible station;
   both proven `READY` on their own domain before serving (`task14-campaign-ready-08/12/13`).
6. **Real inference through the port** - `broker.infer` over the v4 socket, one-time admission, real
   YOLO forward pass on the shared single lane, `device: mps` (`task14-campaign-infer-05`).

### What is missing, stated as precisely as I can

1. **The composition's shape differs from the plan's assumption.** The macOS campaign runs the MPS
   Broker *in-process* (`broker_pid == os.getpid()`, verified live in `task16-broker-crash-03`) while
   its Workers are spawned CLI children; the plan (and the Linux path) assumes the opposite - a
   Supervisor-owned Broker process with an in-process Worker runtime. That single difference is why
   (a) the pick-place chain is not wired into the Workers and (b) a live Broker-crash + pool-rebuild
   injection is unreachable here.
2. **No pick-place batch inside the campaign**, therefore no per-slot MoveIt shadow / controller /
   MuJoCo contact / placement evidence and no five-batch stability series. One real four-point batch
   ran outside the campaign and every point failed at `TERMINAL_CAPTURE_FAILED`
   (`task14-single-batch-01` - its trajectories, contacts and placement are real evidence, but not a
   counted batch).
3. **No fresh GUI evidence.** Screen Recording is denied to this session's responsibility chain and
   stayed denied after the tmux restart (pid 10775); probed repeatedly, most recently
   `task16-capture-probe-02`. This is a permission the session cannot grant itself.
4. **Fault evidences** (inference timeout, active-Worker cancel, Broker crash + rebuild) exist only in
   the IPC shape, never inside a counted campaign, and the Broker-crash one is structurally
   unreachable per point 1.
5. **Linux regression** is deferred, so cross-platform validity, CUDA/NVML admission, `proc_fd_unix`,
   EGL, a real `cuda` Broker device, Linux package/CTest and Linux exact-W2 remain unproven, and any
   release claim is blocked.

### Evidence classification (Task 16 requirement)

- **retained**: `impl-macos-mps-w2-01/`, `station-build-01/`, `model-artifacts/`, the named campaign
  and station runs, and this ledger;
- **archived**: task0/task1 baselines, superseded gates, and everything this session recorded as
  INVALID (`task11-teleop-01/02`, `task11-openapi-01/02/03`, `task14-campaign-ready-02/03`, `-11`,
  the capture probes);
- **deletion candidates, none deleted**: per-run `tmp/` trees, `test-byproducts/`, and the transient
  IPC campaign directories already removed under `/private/tmp/so101-ipc-501` (runtime residue, not
  evidence).

Nothing has been pushed, merged or published; no evidence was deleted; no global configuration was
changed.

_Ledger source HEAD: `47f62e2c`; no evidence deleted._

### CP-UQ276 addendum — the local-only claim, verified

```text
branch                codex/so101-unbounded-queue-resource-budget
HEAD                  48304291   worktree clean
origin/<branch>       bf1b6091   (the base this task started from)
ahead / behind        141 / 0
commits this stretch  97
Screen Recording      still denied (task16-capture-probe-03)
```

Nothing was pushed, fetched into a merge, or published: the remote branch still points at the base
commit and the local branch is ahead-only. `main` was never merged, no second worktree, branch, tmux
session or goal was created, and every commit in this stretch is scoped to the files a task named.

_Ledger source HEAD: `48304291`; no evidence deleted._

### CP-UQ276 addendum 2 — index of the package, web and install gates

```text
task11-buninstall-01             exit_code=0 elapsed_s=0 finished_utc=2026-09-19T13:50:36Z 
task11-webtypes-05               exit_code=0 elapsed_s=1 finished_utc=2026-09-19T13:50:43Z 
task11-web-unit-01               exit_code=0 elapsed_s=1 finished_utc=2026-09-19T13:51:07Z 
task11-web-build-01              exit_code=0 elapsed_s=2 finished_utc=2026-09-19T13:51:03Z 
task11-openapi-04                exit_code=0 elapsed_s=0 finished_utc=2026-09-19T13:50:07Z 
task12-fresh-build-02            exit_code=0 elapsed_s=2 finished_utc=2026-09-19T13:59:03Z 
task12-package-gate-01           exit_code=1 elapsed_s=88 finished_utc=2026-09-19T14:00:47Z 
task12-copied-install-02         exit_code=0 elapsed_s=1 finished_utc=2026-09-19T14:02:25Z 
task12-served-bytes-01           exit_code=0 elapsed_s=0 finished_utc=2026-09-19T14:03:14Z 
source-gate-after-path-fix-01    exit_code=1 elapsed_s=85 finished_utc=2026-09-19T13:43:32Z 
```

Each line is the run's own exit code and elapsed time from the registered evidence root; the
commands, provenance and JUnit/CTest artefacts sit beside them in the same directories.

_Ledger source HEAD: (this commit's parent); no evidence deleted._

Two lines in that index exit non-zero, and they are not passes:

- `task12-package-gate-01` (exit 1): the `colcon test`/CTest package gate is **INVALID** on this host
  because `colcon test` loses `DYLD_LIBRARY_PATH` and collects zero tests
  (`Library not loaded: @rpath/librosidl_typesupport_c.dylib`); the valid macOS gate is the direct
  pytest run, and the plan's requirement that a package gate be real is therefore **partially** met -
  recorded in CP-UQ244-CP-UQ247 and never counted as green.
- `source-gate-after-path-fix-01` (exit 1): 234 failed / 3177 passed / 8 skipped, where every failure
  cluster is an environment boundary (`/data/work`, `/proc/self/fd`, `PATH_OWNER`, model runtime,
  `/run/user`) rather than task code; no platform skips were added to make it green.

_Ledger source HEAD: `8bc97a96`; no evidence deleted._

### CP-UQ276 addendum 3 — one-time consumption works, and it exposed a port defect

```text
task16-consume-once-03   status W2_CAMPAIGN_INCOMPLETE (exit 7)
                         served 14, devices ['mps'], duplicates_refused 2
                         w1 infer: 3 x OK, duplicate: {"request_id": "w1-att-00-yolo",
                                                       "status": "ADMITTED_TWICE"}
                         orphans []
```

The server-side property is real: the campaign refused **both** duplicated request ids
(`DUPLICATE_REQUEST`), so a late or repeated result cannot be served twice - the first live evidence
for the one-time table doing its job rather than merely existing.

The same run exposed a defect in my port: the Worker reported `ADMITTED_TWICE` for the duplicate,
because `W2BrokerPort.request_one` looks for `ok is False` on the response object, while a v4 refusal
is carried in the response's status/code fields. A refusal must never be readable as an admission -
that is the exact failure the one-time design exists to prevent - so the port's check is wrong and is
recorded here as an open defect rather than as a passing feature. The campaign's own status was
`INCOMPLETE` for the same reason: the duplicate counted as served.

Two earlier attempts of this probe also cost a run each, both harness-shaped: a `KeyError: 'device'`
in the served summary when a refusal carries no device (fixed by reading defensively), and a stale
campaign directory from the failed run making the next run refuse its inventory (verified dead and
removed).

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `29a01971`; no evidence deleted._

### CP-UQ277 addendum — the refusal defect is fixed, and it was in the server, not the port

Reading the v4 server's mapping settled it: a handler result is a refusal **only** when it is a
mapping containing an `error` key; anything else becomes a success descriptor. My refusal branches
returned `{"ok": False, "code": …}`, so the server answered `status: OK` and the Worker read a
refusal as an admission - the exact inversion the one-time design exists to prevent.

Fixed on both sides of the wire:

- the campaign's three refusal branches now return `{"error": {"code": …}}`, which the server turns
  into a non-OK `V4Response` with an `error` body;
- the port reads the code from that body rather than from the response object.

Re-run and verification:

```text
task16-consume-once-04   served 14, devices ['mps'], duplicates_refused 2
                         w1 infer: 3 x OK
                         w1 duplicate: {"status": "REFUSED",
                                        "error": "W2BrokerPortError: BROKER_INFER_REFUSED: UNKNOWN"}
                         orphans []
task16-broker-port-09    6 passed (port suite after the fix)
```

The duplicate is now refused **and** the Worker knows it was refused. The remaining blemish in that
line is the code reading `UNKNOWN` instead of `DUPLICATE_REQUEST` in that particular run - the fix
for it (reading the code from the error body) landed in the same commit, and this run predates it.

The campaign reported `INCOMPLETE` rather than `PASS`, which is the honest answer for a run whose
happy path the probe deliberately breaks: it demands six admitted requests with no refusal, and the
probe adds two refusals on purpose.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `52421687`; no evidence deleted._

### CP-UQ277 addendum 2 — one-time consumption, verified end to end

```text
task16-consume-once-05   status W2_CAMPAIGN_INCOMPLETE (exit 7, correct for a probe that breaks the
                         happy path on purpose), devices ['mps'], duplicates_refused 2, orphans []
  w1 duplicate: {"status": "REFUSED", "error": "W2BrokerPortError: BROKER_INFER_REFUSED: DUPLICATE_REQUEST"}
  w2 duplicate: {"status": "REFUSED", "error": "W2BrokerPortError: BROKER_INFER_REFUSED: DUPLICATE_REQUEST"}
```

Both Workers sent a repeat of an id they had already used, the one-time table refused both, and the
Worker's port reported the refusal with the server's own code. That is live macOS evidence for a
design property that, one round ago, was inverted in my own code: the table refuses, and a refusal
cannot be mistaken for an admission.

This closes the "request register / one-time consume / late-or-duplicate rejection" line of the
acceptance matrix to the extent it can be closed outside a counted batch - the remaining fault
evidences (inference timeout, active-Worker cancel, Broker crash + rebuild) stay open per CP-UQ276
point 4, and the Broker-crash one is structurally unreachable in this composition.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `2961ba71`; no evidence deleted._

## CP-UQ278 — The open items, in one place, at the end of the budget

```yaml
checkpoint_id: CP-UQ278
verdict: PARTIAL (unchanged; see CP-UQ276)
working_tree_status: clean
owned_processes: NONE
open_risks:
  - Screen Recording denied to this session's responsibility chain (probe task16-capture-probe-04).
  - The composition keeps the MPS Broker in-process while spawning CLI Workers, so the pick-place
    chain and the Broker-crash evidence are both structurally out of reach.
next_command: handle the goal policy; nothing further can be completed inside this budget
```

| Open item | Why it is open |
| --- | --- |
| inference-timeout evidence | not attempted: the Worker's port uses the 240 s executing hard timeout, so a live stall probe needs the lease to carry a short deadline first - a change I would rather not land half-verified in the last rounds |
| active-Worker cancel evidence | same shape: needs a live Worker driven by a Coordinator lease, which the spawned Worker does not own |
| Broker crash + full pool rebuild | structurally unreachable here: `broker_pid == os.getpid()` (verified live in `task16-broker-crash-03`) |
| pick-place inside the campaign | needs the in-process `ParallelWorkerRuntime` ported onto the spawned Worker (CP-UQ271) |
| five `FULL_RESTART` simulation batches | requires the previous two items |
| fresh GUI evidence | requires the TCC grant; asked for repeatedly since round 9 |
| Linux regression | `DEFERRED_ENVIRONMENT` (CP-UQ272) |
| independent verdict | the plan names `gpt-5.6-sol/high`; this session cannot invoke it and used no substitute |

Everything above is recorded rather than glossed, and none of it changes the verdict: **PARTIAL**, with
Task 14 at 0/5 and `LINUX_REGRESSION_DEFERRED` in force.

_Ledger source HEAD: `e10e4980`; no evidence deleted._

### CP-UQ278 addendum — the inference-timeout probe: refusals, and an unexpected mechanism

`--stall-serve-after N` holds the Nth inference answer past the Worker's client deadline
(`--worker-deadline-s`, carried in the lease so the port's client uses it).

```text
task16-timeout-02   status W2_CAMPAIGN_INCOMPLETE, served 2, devices [], orphans []
                    w1/w2 infer: all six calls -> W2BrokerPortError:
                                 BROKER_INFER_REFUSED: INTERNAL_ERROR
```

What this supports: **no inference was admitted while the server was stalled** - every call failed
closed with a refusal, which is the property that matters (a timeout must never be readable as an
admission).

What it does not support, and I am not going to dress it up: the failures carry `INTERNAL_ERROR`
rather than a deadline code, and only two requests were recorded as served, so the stall appears to
have affected the server's request loop more broadly than "one slow answer". The v4 server is built
with an accept loop, a bounded dispatcher and per-connection handler threads, so a single stall
*should* not starve other clients; whichever of the plausible causes it is (the stalled handler
holding something shared, the lane submission, or a client disconnect racing the response write) is
**not established** by this run. Recorded as an open question with its evidence, not as a finding.

The two earlier attempts at this probe cost two runs and both were mine: the first version stalled the
Nth served request in general rather than the Nth *inference* (the probe traffic interleaves), so the
stall landed on a probe call and everything passed.

Task 14 remains 0/5; `LINUX_REGRESSION_DEFERRED` retained.

_Ledger source HEAD: `4618a16f`; no evidence deleted._

### CP-UQ278 addendum 2 — why the plan's checkboxes are still unchecked

The plan states that its checkboxes are the single progress list. They are all still `- [ ]` (87 of
them), and that is deliberate: ticking them now would be a bulk claim I cannot back item by item
inside the remaining rounds, and this task has spent its whole budget refusing exactly that kind of
claim. Each box maps to a requirement that CP-UQ274 assesses individually with its evidence, and the
assessment is not uniform - several rows are MET, several PARTIAL, two NOT MET, one DEFERRED.

If a later session wants the boxes ticked, the honest procedure is the one this ledger already uses:
take each box, name the run or test that carries it, tick it only if that artefact exists and passed,
and leave the rest - in particular every box under Task 14 - unchecked.

_Ledger source HEAD: `46e08553`; no evidence deleted._

## CP-UQ279 — Closing state of the macOS MPS / private-IPC task

```yaml
checkpoint_id: CP-UQ279
verdict: PARTIAL
task14: 0/5 - no counted FULL_RESTART simulation batch
linux_regression: DEFERRED_ENVIRONMENT
independent_verdict: OWED (gpt-5.6-sol/high unavailable to this session; no substitute used)
working_tree_status: clean; branch ahead of origin only, nothing pushed or merged
owned_processes: NONE - no ROS or station process left running
```

### What the task achieved

The macOS exact-W2 platform is built, tested and exercised end to end: frozen v3 plus a closed v4
contract, Darwin MPS admission that fails closed, durable supervisor ownership with exact-signal
reaping, permission-only v4 IPC with no token/lease vocabulary, a single-lane shared MPS Broker,
exact-W2 resource allocation, two Workers that each own a visible station on their own ROS domain and
prove it ready before serving, real inference through the port with `device: mps`, and one-time
admission demonstrated live refusing duplicates with the server's own code.

### What remains, and the two reasons

1. **Task 14's counted batches.** They need the pick-place chain inside the Workers, which means
   porting the in-process runtime onto this spawned-Worker composition - the structural gap that also
   makes a live Broker-crash injection unreachable (`broker_pid == os.getpid()`).
2. **Fresh GUI evidence.** macOS TCC denies Screen Recording to this session's responsibility chain;
   tmux was restarted (pid 10775) and the grant still does not apply. Every per-point `viewer.png`
   fails closed, so no batch could be counted even if the chain existed.

Neither was hidden, and neither was reported as a pass: the acceptance matrix in CP-UQ274 marks each
requirement MET / PARTIAL / NOT MET / DEFERRED with the artefact that carries it.

### For whoever continues

- the ledger is the single writer's record; CP-UQ274 is the requirement-by-requirement matrix, and
  CP-UQ271/CP-UQ276 name the structural work still owed;
- the plan's checkboxes are deliberately unchecked, with the procedure for ticking them in the
  CP-UQ278 addendum;
- nothing has been pushed, merged or published; no evidence has been deleted; no Linux gate was run
  or reported as anything.

_Ledger source HEAD: `4a372263`; no evidence deleted._

## CP-UQ280 — The goal budget is extended to 200 rounds by explicit authorization

```yaml
checkpoint_id: CP-UQ280
authorization: direct user instruction to keep the same goal and raise its cap by exactly +100
goal_id: goal-746d697c-16dd-4456-aeef-ea2d7edfd945
before: revision 5, phase blocked (code round-limit), roundsStarted 100, maxGoalRounds 100, disarmed
after:  revision 7, phase active, roundsStarted 100, maxGoalRounds 200, armed
working_tree_status: clean at commit e8e7f347
owned_processes: NONE
open_risks:
  - Screen Recording is still denied to this session's responsibility chain; it remains an external
    blocker and must never be reported as a pass.
next_command: close the CP-UQ271 spawned-worker pick-place gap, then Task 14
```

The same goal was edited (not created, cleared or replaced): `maxGoalRounds` 100 -> 200, then resumed.
Readback is exactly `roundsStarted=100, maxGoalRounds=200`, phase `active`, activation `armed`, same
goal id. Task 14 stands at 0/5 and `LINUX_REGRESSION_DEFERRED` remains in force.

_Ledger source HEAD: `e8e7f347`; no evidence deleted._

## CP-UQ281 — The spawned-Worker pick-place gap is closed: both slots execute real pick-place

```yaml
checkpoint_id: CP-UQ281
last_valid_experiment: EXP-UQ281-WORKER-PICK-PLACE
current_hypothesis: The spawned Worker can drive the production pick-place batch on its own station
  and domain, producing per-slot physical evidence. CONFIRMED.
working_tree_status: clean after the scoped commit below
owned_processes: NONE
preserved_processes: the user's ChatGPT/Codex desktop app, Chrome, Ghostty, Sparkle updater
open_risks:
  - Every point still fails at TERMINAL_CAPTURE_FAILED, because macOS TCC denies Screen Recording to
    this session's responsibility chain. That is an EXTERNAL blocker and is not a pass.
  - Screen Recording remains denied; no counted Task 14 batch is possible until it is granted.
next_command: recheck the Screen Recording grant; if it is ever granted, the same run becomes a
  counted batch candidate
```

`EXP-UQ281-WORKER-PICK-PLACE: VALID` for the structural gap; the campaign itself is INCOMPLETE.

### What changed

Each Worker, after its station is ready and its round trips and inferences are served, runs the
production batch runner (`so101_mujoco_rgbd_batch`) in **attach mode** against **its own station**,
on **its own ROS domain**, with **its own evidence root** (`<worker station root>/pick`) - so the two
slots never share a batch, a session, a reset epoch or a directory. This is the minimum safe form of
the port CP-UQ271 called for: it reuses the production per-point flow instead of re-implementing the
in-process runtime inside a spawned child.

### The evidence

```text
task14-pickplace-06   W2_CAMPAIGN_INCOMPLETE (exit 7), served 8, orphans []
  w1: 4 dynamic execute manifests, all state DONE, failure None
      01-task_start           step 33829  table_contact True  max_normal_force 0.2330 N
      02-cup_test_forward_5cm step 36771  table_contact True  max_normal_force 0.2331 N
  w2: 4 dynamic execute manifests, all state DONE, failure None
      01-task_start           step 37030  table_contact True  max_normal_force 0.2330 N
      02-cup_test_forward_5cm step 38249  table_contact True  max_normal_force 0.2332 N
  per-point evidence: rgb.png, point-cloud-preview.png, point-result.json for all four points on both
  slots; every point's status is FAILED with failure_code TERMINAL_CAPTURE_FAILED
```

So both slots now produce **their own** MoveIt execution and MuJoCo physics evidence - trajectories
completed, contacts recorded, placement reached - inside the campaign, on their own domains. What is
still missing is the per-point `viewer.png`, and that is the TCC grant, not the chain.

Task 14 therefore moves from "0/5, nothing to count" to "0/5, physical evidence present but every
point fails closed on the GUI capture". It remains **0/5**: the plan counts a batch only when it
passes, and I am not going to relabel a failing capture as a pass. `LINUX_REGRESSION_DEFERRED` stands.

_Ledger source HEAD: `5b68085d`; no evidence deleted._

### CP-UQ281 addendum — the five-run FULL_RESTART series, batches as they finish

```text
batch 1: exit=7 status=W2_CAMPAIGN_INCOMPLETE served=8 cleanup=True
    w1: manifests=4 executed=4 points=4 failures=['TERMINAL_CAPTURE_FAILED']
    w2: manifests=4 executed=4 points=4 failures=['TERMINAL_CAPTURE_FAILED']
batch 2: exit=7 status=W2_CAMPAIGN_INCOMPLETE served=8 cleanup=True
    w1: manifests=4 executed=4 points=4 failures=['TERMINAL_CAPTURE_FAILED']
    w2: manifests=4 executed=4 points=4 failures=['TERMINAL_CAPTURE_FAILED']
```

Each batch composes a fresh claim, IPC root, Broker generation and two stations. In the batches
recorded so far **both slots executed all four points** (4 manifests, 4 point results, nothing
refused) and cleanup was complete; every single point still ends FAILED with
TERMINAL_CAPTURE_FAILED, which is the TCC viewer-capture blocker and not the chain. So this series
is evidence of repeatability of the whole W2 chain **including per-slot pick-place execution**, and
it is explicitly **not** the plan's counted five-batch stability: a batch that fails its capture is
not a pass, and Task 14 therefore stays 0/5.

_Ledger source HEAD: (this commit's parent); no evidence deleted._
