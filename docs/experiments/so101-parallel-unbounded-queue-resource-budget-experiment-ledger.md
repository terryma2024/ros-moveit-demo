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
latest_checkpoint: CP-UQ31 (see the tail of this file; CP-UQ32 appended there for the current unit)
next_experiment: EXP-UQ32 Task12 freeze completion, real ament_python 8-worker package gate, Stages B-E
  within the latest user authorization
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
