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
