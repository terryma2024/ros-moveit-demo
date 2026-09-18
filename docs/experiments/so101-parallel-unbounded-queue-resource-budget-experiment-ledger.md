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
current_commit: PENDING_AFTER_COMMIT (continuation dispatch 2e37ac85; last probe HEAD ccdb0119140ee3095144b948f57d8dd592502db8)
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
latest_checkpoint: CP-UQ08
next_experiment: EXP-UQ09 (Task 8 adaptive no-K)
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
