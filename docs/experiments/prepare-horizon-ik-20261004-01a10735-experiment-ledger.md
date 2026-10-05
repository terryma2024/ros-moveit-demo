# prepare_horizon CPU IK experiment ledger

```yaml
task_id: prepare-horizon-ik-20261004-01a10735
goal: ai-station before/after fixed-fixture comparison on one isolated physical P core
success_contract: unchanged search, scoring, gates and receipts; equivalence and package gates
worktree: /Users/matianyi/.codex/worktrees/0a4f/moveit-demo
branch: codex/prepare-horizon-ik-20261004-01a10735
base_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0
benchmark_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0
current_commit: see evidence ai-station/publish.json
second_baseline_commit: e1030ccf474f02105fdb62db19568255b1fce289
delivery_commit: see evidence review/publish.json
second_delivery_commit: see evidence native50/review/publish.json
evidence_root: /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735
host: Terry-Mac-mini.local
model: gpt-6.1-sol
reasoning_effort: xhigh
confirmed_conclusions:
  - bootstrap prompt and bundle SHA256 verified; dispatch receipt exact
  - native CLI worktree was isolated and clean at detached f0677823 before branch switch
  - task branch starts at imported frozen source baseline; old checkouts untouched
  - host-access doctor --base exit 0; sandbox denial was not host absence
disproven_routes:
  - EXP-014 handwritten sequential 4x4 product has float drift; original NumPy @ retained
open_hypotheses:
  - NONE; Mac acceptance and isolated ai-station comparison achieved
final_confirmed_conclusions:
  - aggregate ratio 0.2727275234730253 <= 0.30
  - exact fixture outputs and complete xdist8 ordinary package gate passed
  - scoped product/test diff unchanged from formal measurement
second_round_confirmed_conclusions:
  - EXP-020 installed aggregate ratio 0.48161196881098667 <=0.50, exact outputs and 64-case lossless trace equivalence
  - EXP-020 full ordinary xdist8 gate 3920 passed, 30 skipped, 0 errors/failures
  - EXP-021 workload unchanged, shared prefixes and compiled scalar loops reduce repeated work
ai_station_confirmed_conclusions:
  - EXP-023 native ratio0.46745505113034813, median1110.83325925 ->519.264618ms, reduction53.25449488696519%
  - EXP-023 cumulative original ratio0.13214663949466043, reduction86.78533605053396%
  - EXP-023 all Linux complete outputs exact; CPU14 only, isolated physical P core7 with SMT15 reserved idle, no migrations
  - CPU masks/governor and existing remote checkouts/submodules unchanged after measurement; complete evidence copy hashes verified
latest_checkpoint: CP-015
next_experiment: NONE
retained: all evidence in registered root
archived: NONE
deletion_candidates: registered scratch listed in review/final-retention.json, native50/review/retention.json and ai-station/retention.json; none deleted
```

## Scope and authorization

Mac/source baseline only; no equivalence claim about ai-station dirty sources.
CPU-only, inline self review, no implementation agent or dst. During the initial
Mac optimization, ai-station access was outside scope. The current user request
authorizes SSH benchmark execution and temporary P-core isolation on ai-station.
Stack launch, merge, evidence deletion and shared dependency changes remain outside scope.
The user explicitly authorized commit and push to the current Gitee task branch;
that authorization applies to this completed second optimization round.
Baseline harness and read-only investigation explicitly authorized before plan approval.
Optimization implementation requires explicit approval (AGENTS.md Task model selection
and brainstorming HARD-GATE); user explicitly approved the presented plan before any optimization code.
Only compute has observable output; GUI/physics/controller/live gates are N/A for
this task and cannot be inferred from kernel benchmarks.

## EXP-001

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: frozen source can execute real prepare_horizon without ROS service waits
prediction: real URDF IK produces repeatable receipts and complete or rejected horizons
single_variable: NONE; baseline only
lifecycle: FULL_RESTART
preconditions:
  - source package snapshotted from exact frozen commit
  - fixed ROS Python 3.11; NumPy Accelerate; one BLAS thread; no concurrent benchmark
  - fixture selection retained before latency acceptance protocol is frozen
success_criteria:
  - actual prepare_horizon runs with real IK, all 14 waypoints assembled
  - fixtures include complete, boundary and expensive rejected cases
failure_criteria:
  - real fixed fixtures yield rejected horizons; retain as workload
invalid_criteria:
  - wrong module provenance, changed source, missing interpreter dependency or altered IK
provenance:
  source_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0
  install_overlay: NONE; explicit frozen source package import, no shared overlay writes
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: N/A; no ROS node or graph created
  gz_partition: N/A; no simulation
commands:
  - command: /opt/ros/jazzy/.venv/bin/python EVIDENCE_ROOT/baseline/characterize.py --mode characterize --out EVIDENCE_ROOT/baseline/characterization
    exit_code: 0
observed:
  - OBSERVED: complete 14-step horizons for p18_home and canonical_home
  - OBSERVED: outer_boundary rejected after 149 receipts; unreachable after 14 receipts
  - OBSERVED: p18_home 599 solve requests / 339 unique exact requests / 260 potential hits
  - OBSERVED: canonical_home 599 requests / 339 unique / 260 potential hits
  - OBSERVED: boundary 149 requests / 89 unique / 60 potential hits; unreachable 14 / 14
  - OBSERVED: failed seeds consume 3.055 s of instrumented p18 time, 2.287 s at boundary
inferred: []
conclusion: representative fixed fixtures include success, boundary failure and expensive failure; retain all four
evidence:
  - /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/bootstrap
decision: KEEP
next_experiment: EXP-002
```

## CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: baseline compute path is ROS-free with real solver injected
working_tree_status: only this newly created task ledger
owned_processes: current tmux Codex session 01a10740-6a5a-7081-93bb-ec35b32a2caa
preserved_processes: all pre-existing host processes and tmux sessions
confirmed_conclusions: bootstrap/host/model/worktree checks passed
disproven_routes: NONE
open_risks: full runtime doctor and baseline fixture characterization pending
next_command: create frozen source snapshot and run baseline characterization harness
```

## EXP-002

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: uninstrumented fixed-fixture latency is repeatable across independent processes
prediction: all output documents match characterization; formal latency quantifies baseline
single_variable: instrumentation removed; source and inputs unchanged
lifecycle: FULL_RESTART
preconditions:
  - baseline/protocol-v1.json frozen before formal measurement
  - three independent rounds; one warmup plus five measured calls per fixture per round
  - no concurrent benchmark or package gate; one compute/BLAS thread
success_criteria: all 60 formal calls plus warmups deterministic; 15 equal-weight suite samples
failure_criteria: repeatable expensive failure retained as workload, never excluded
invalid_criteria: output drift, wrong source, changed protocol/fixtures, nonzero exit
provenance:
  source_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0
  install_overlay: NONE; explicit immutable frozen source import
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: N/A; no ROS node created
  gz_partition: N/A; no simulation
commands:
  - command: characterize.py --mode measure --round 0/1/2 --samples 5 --out baseline/round-0/1/2
    exit_code: 0
  - command: characterize.py --mode profile --out baseline/profile
    exit_code: 0
observed:
  - OBSERVED: 15 samples/fixture; equal-weight suite median 2145.619 ms, p95 2164.032 ms, CV 0.02007
  - OBSERVED: p18_home median/p95 4291.527/4329.279 ms
  - OBSERVED: canonical_home median/p95 963.757/979.761 ms
  - OBSERVED: outer_boundary median/p95 2574.903/2596.456 ms
  - OBSERVED: unreachable median/p95 739.347/749.293 ms
  - OBSERVED: all three rounds exactly match instrumented output documents
  - OBSERVED: source, protocol and fixtures unchanged; setup 0.315-0.649 ms
  - OBSERVED: cProfile _matrix 10.546/13.719 s; _rotation_axis 6.850 s inclusive
inferred: NONE
conclusion: baseline measured; primary target <=643.686 ms on this initial baseline; final gate uses fresh interleaved controls
evidence:
  - /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/baseline/protocol-v1.json
  - /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/baseline/characterization
  - /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/baseline/round-0
  - /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/baseline/round-1
  - /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/baseline/round-2
  - /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/baseline/profile
decision: KEEP
next_experiment: EXP-003
```

## EXP-003

```yaml
experiment_id: EXP-003
status: INVALID
prior_experiment: EXP-002
hypothesis: existing kernel/horizon/reachability regression tests pass under frozen source
prediction: nonzero directed collection, no failures and correct source/dylib provenance
single_variable: ordinary pytest invocation after benchmark, source unchanged
lifecycle: FULL_RESTART
preconditions:
  - benchmark and profile processes completed
  - fixed ROS Python and all four fixed overlays loaded in current zsh
  - explicit frozen source alias before shared installed Python package
success_criteria: all selected tests pass; JUnit collected; import source verified
failure_criteria: pytest assertion or collection failure preserved, no unrelated fixes
invalid_criteria: wrong module or runtime executable; absent required dylib
provenance:
  source_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0
  install_overlay: /opt/data/so101/workspace/install (dependencies only); frozen source alias under registered root
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: unset; tests do not create live ROS graph
  gz_partition: unset; no simulation
commands:
  - command: /opt/ros/jazzy/.venv/bin/python -m pytest -p no:cacheprovider src/so101_demo_py/test/test_underactuated_ik.py src/so101_demo_py/test/test_deterministic_ik_horizon.py src/so101_demo_py/test/test_task_reachability_ros.py -q --junitxml=EVIDENCE_ROOT/tests/baseline-targeted.xml
    exit_code: 3
observed: OBSERVED pytest_rerunfailures bootstrap bind(127.0.0.1, 0) denied by sandbox; no testcase collected
inferred: NONE
conclusion: runner environment failure, not test RED or code regression
evidence:
  - /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/tests/baseline-targeted.log
decision: KEEP
next_experiment: EXP-004
```

## CP-002

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-002
current_hypothesis: exact request reuse plus invariant FK setup can reduce cost without search changes
working_tree_status: task ledger only; product source unchanged
owned_processes: no active benchmark; current Codex tmux only
preserved_processes: all existing checkouts, host processes and tmux sessions
confirmed_conclusions: baseline and four fixture outputs measured and retained
disproven_routes: ROS wait does not contribute to this compute-only benchmark
open_risks: latency goal not achieved; implementation approval pending
next_command: baseline directed pytest, then present concise implementation plan
```

## EXP-004

```yaml
experiment_id: EXP-004
status: VALID
prior_experiment: EXP-003
hypothesis: host access resolves pytest plugin localhost socket sandbox denial
prediction: identical runtime/source/plugins and testcase selection actually collect and run
single_variable: host execution access; no source or dependency change
lifecycle: FULL_RESTART
preconditions:
  - EXP-003 preserved as INVALID, not a code failure
  - fixed Python/overlay and same frozen source alias
  - new scratch and separate output log/JUnit
success_criteria: selected tests pass, nonzero count, JUnit and exit 0
failure_criteria: actual test assertion or required environment still fails
invalid_criteria: wrong source/Python/dylib provenance or no collection
provenance:
  source_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0
  install_overlay: /opt/data/so101/workspace/install dependencies only; frozen source alias
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: unset
  gz_partition: unset
commands:
  - command: same directed pytest as EXP-003 with host access and tests/baseline-targeted-host.xml
    exit_code: 0
observed: OBSERVED 14 tests passed in 8.34 s; JUnit tests=14 errors=0 failures=0 skipped=0
inferred: NONE
conclusion: pytest bootstrap denial isolated to sandbox; directed baseline regression passes; full package gate remains for implementation
evidence:
  - /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/tests/baseline-targeted-host.log
decision: KEEP
next_experiment: WAIT_FOR_IMPLEMENTATION_APPROVAL
```

## CP-003 — implementation approval gate

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-004
current_hypothesis: exact request cache plus FK invariant/iteration reuse can reach <=0.30 ratio
working_tree_status:
  - untracked docs/experiments/prepare-horizon-ik-20261004-01a10735-experiment-ledger.md
  - untracked docs/superpowers/plans/2026-10-04-prepare-horizon-ik-cpu.md
owned_processes: benchmark/profile/pytest exited; current tmux Codex only
preserved_processes: all other host processes/tmux sessions; no simulation started
confirmed_conclusions:
  - EXP-002 four-fixture suite median 2145.619 ms; p95 2164.032 ms; all output hashes exact
  - EXP-004 14 existing directed tests pass under fixed runtime
  - frozen snapshot 787 files, fixture/protocol/harness hashes and receipt reverified
  - product source diff empty at frozen commit; old checkouts not modified
disproven_routes:
  - sandbox denial does not imply missing runtime or test regression (EXP-003/004)
open_risks:
  - implementation approval required; no optimized latency or ratio exists yet
  - full xdist package and new installation provenance gates not run yet
  - pure compute measurement is not live ROS/robot qualification
next_command: await explicit user approval of docs/superpowers/plans/2026-10-04-prepare-horizon-ik-cpu.md before implementation
native_goal_status: active; objective not yet achieved
approval_gate_consecutive_goal_turns: 1
retained: all bootstrap, frozen source, inputs, raw samples, profile, directed test logs/JUnit, review artifacts
archived: NONE
deletion_candidates:
  - tests/t0 and tests/t1 scratch; retained until explicit deletion authorization
```

## CP-004 — automatic continuation, approval still pending

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-004
previous_goal_turn_classification: progress; baseline, regression evidence and reviewable plan completed
current_goal_turn_classification: no_progress; implementation requires missing explicit human approval
current_hypothesis: unchanged; awaiting approval to test exact request cache and FK reuse
working_tree_status: only task ledger and proposed plan untracked; product source diff empty
owned_processes: no task benchmark/profile/pytest active; current Codex only
preserved_processes: all pre-existing checkouts/processes/sessions
confirmed_conclusions: frozen HEAD and CP-003 baseline/test evidence remain valid
disproven_routes: automatic goal continuation is not human implementation approval
open_risks: optimization ratio and final package/installation gates remain unproven
next_command: await response to the existing implementation approval request
native_goal_status: active
approval_gate_consecutive_goal_turns: 2
retained: all registered-root artifacts
archived: NONE
deletion_candidates: tests/t0 and tests/t1 scratch; no deletion authorized or performed
```

## CP-005 — blocked audit passed

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-004
previous_goal_turn_classification: no_progress; missing explicit implementation approval
current_goal_turn_classification: no_progress; same approval condition revalidated
approval_gate_consecutive_goal_turns: 3
blocked_audit:
  condition: explicit approval of the reviewable implementation plan has not arrived
  recurrence: original turn CP-003 plus automatic continuations CP-004 and CP-005
  verified_state: frozen HEAD unchanged, product diff empty, plan SHA256 unchanged
  available_safe_progress: NONE; authorized baseline/investigation/protocol/plan complete
  needed_external_change: user approval or plan revision request
current_hypothesis: exact request cache plus FK invariant/iteration reuse; untested pending approval
working_tree_status: only task ledger and proposed plan untracked
owned_processes: no task benchmark/profile/pytest live
preserved_processes: all existing checkouts/processes/tmux sessions
confirmed_conclusions: CP-003 baseline and directed regression evidence remain retained
disproven_routes: automatic continuation cannot satisfy the explicit approval gate
open_risks: <=0.30 latency target and final equivalence/package/install gates unachieved
next_command: respond to existing implementation approval request, then resume full objective
native_goal_status: blocked; update_goal returned blocked after CP-005 audit
retained: all evidence under the unique registered root
archived: NONE
deletion_candidates: tests/t0 and tests/t1; not deleted
```

## CP-006 — user approved implementation

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-004
approval: user explicitly replied 批准计划
approved_plan_sha256: e89b5a10f52eef13c714d5b5b19cb3715c61d30b574524cf07ebf552b8803f08
current_hypothesis: exact request cache first, then invariant FK and iteration reuse
working_tree_status: task ledger and approved plan only; product source initially unchanged
owned_processes: current Codex only
preserved_processes: all other processes/worktrees
confirmed_conclusions: baseline and regression from EXP-002/004
open_risks: final latency/equivalence/package/install evidence still required
native_goal_status: get_goal still reports blocked; tools expose no resume action; user approval authorizes continued objective work
next_command: write and run exact-cache RED tests
```

## EXP-005

```yaml
experiment_id: EXP-005
status: PLANNED
prior_experiment: EXP-004
hypothesis: request-local exact IK/FK reuse preserves all horizon receipts while reducing bottom-level solves
prediction: RED duplicate-work test fails baseline; GREEN complete/failure receipts match frozen outputs exactly
single_variable: horizon-local cache adapter in prepare_horizon
lifecycle: FULL_RESTART
preconditions: explicit plan approved; frozen baseline/fixtures/protocol unchanged
success_criteria: exact-key isolation, local lifetime, deterministic failure receipts; real fixture equivalence
failure_criteria: changed search/order/scoring/error/gate; caching unexpected errors or other IK implementations
invalid_criteria: wrong runtime/module/thread provenance
provenance:
  source_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0 plus scoped working diff
  install_overlay: fixed shared overlays for dependencies only; task source alias
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: unset; no live ROS graph
  gz_partition: unset; no simulation
commands: PENDING
observed: PENDING
inferred: NONE
conclusion: PENDING
evidence: /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/tests
next_experiment: EXP-006
```

## EXP-005 execution evidence

```yaml
status: RUNNING
commands:
  - command: implementation/run-tests.zsh cache-red; cache-red-forward
    exit_code: 1 (intended RED: absent adapter; repeated real solve count 3 instead of 1)
  - command: implementation/run-tests.zsh cache-green, four directed files including test_dynamic_execute.py
    exit_code: 0
  - command: baseline/characterize.py --mode measure --source CURRENT_TASK_PACKAGE --samples 3 --out implementation/cache-measure
    exit_code: PENDING
observed: 37 directed tests passed in 9.13 s; exact key/signed-zero/error/lifetime regressions green
```

## EXP-006

```yaml
experiment_id: EXP-006
status: PLANNED
prior_experiment: EXP-005
hypothesis: invariant FK setup removes repeated axis normalization with bit-identical chain products
prediction: RED norm count 18 vs desired 3; optimized FK matches reference chain exactly
single_variable: precomputed fixed axis skew matrices and identity matrices
lifecycle: FULL_RESTART
preconditions: cache-only timing completed before further code change or test load
success_criteria: FK reference exact; real four fixture documents exact; reduced cost
failure_criteria: changed finite FK values/exception/gates or receipt outputs
invalid_criteria: wrong source/runtime/thread provenance
provenance:
  source_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0 plus scoped diff
  install_overlay: fixed dependency overlays, task source alias
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: unset
  gz_partition: unset
commands: PENDING
observed: PENDING
conclusion: PENDING
next_experiment: EXP-007
```

## EXP-005 result

```yaml
status: VALID
exit_code: 0
observed: cache-only weighted median 1293.323 ms (exploratory n=3); all four output documents exactly match baseline
conclusion: exact horizon cache reduces work and preserves receipt/path/score/error behavior
retained_diff: implementation/cache-only.patch
next_experiment: EXP-006
```

## EXP-006 execution

```yaml
status: RUNNING
commands:
  - command: implementation/run-tests.zsh fk-red test_underactuated_ik.py
    exit_code: 1; norm count 18 vs 3 and duplicate gate matrix count 2 vs 1
  - command: implementation/run-tests.zsh fk-invariants-green test_underactuated_ik.py -k 'not solve_reuses_gate'
    exit_code: 0
  - command: baseline/characterize.py --mode measure --source CURRENT_TASK_PACKAGE --samples 3 --out implementation/fk-invariants-measure
    exit_code: PENDING
observed: 7 FK directed regressions pass, including 44 exact chain comparisons, joint limits and invalid seed error
next_experiment: EXP-007
```

## EXP-007

```yaml
experiment_id: EXP-007
status: PLANNED
prior_experiment: EXP-006
hypothesis: sharing each iteration base matrix between residual and gate saves one FK without numerical drift
prediction: one base FK on immediate success; all 200 failed iterations and five finite differences retained
single_variable: solve-local target constants and base FK reuse
lifecycle: FULL_RESTART
preconditions: EXP-006 timing completes before code modification; gate FK RED captured
success_criteria: real failed-seed matrix count 1201; complete/failure outputs exactly equal frozen baseline
failure_criteria: iteration cap, residual/gate/path/score/order/exception difference
invalid_criteria: changed fixtures/tolerances/runtime or concurrent test load
provenance:
  source_commit: frozen baseline plus scoped working diff
  install_overlay: dependency overlays only
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: unset
  gz_partition: unset
commands: PENDING
observed: PENDING
conclusion: PENDING
next_experiment: EXP-008
```

## EXP-006 result

```yaml
status: VALID
exit_code: 0
observed: weighted median 656.083 ms, exploratory n=3; exact output documents for all four fixtures
conclusion: invariant setup halves the cache-only compute cost without changing arithmetic order
retained_diff: implementation/fk-invariants.patch
```

## EXP-007 execution

```yaml
status: RUNNING
commands:
  - command: implementation/run-tests.zsh fk-iteration-red test_underactuated_ik.py -k 'reuses_gate or failed_solve'
    exit_code: 1; intended RED matrix counts 2 vs 1, 1401 vs 1201
  - command: implementation/run-tests.zsh kernel-green four directed files
    exit_code: 0
observed: 42 directed tests passed; 200 failed iterations remain, all five finite-difference columns retained
conclusion: solve-local target constant and FK reuse implemented; final equivalence pending
next_experiment: EXP-008
```

## EXP-008

```yaml
experiment_id: EXP-008
status: PLANNED
prior_experiment: EXP-007
hypothesis: approved cache and FK reuse reach <=0.30 ratio with bit-identical full outputs
prediction: formal ratio <=0.30; four success/failure receipts and selected paths exactly match
single_variable: baseline vs approved optimized source
lifecycle: FULL_RESTART
preconditions:
  - fixed protocol-v1 and fixtures/source snapshots unchanged
  - directed GREEN exited; no concurrent profiling or package test
  - optimized product hashes frozen in final/source-hashes-before.json
success_criteria: three independent rounds/variant, 15 samples/fixture, equal-weight suite ratio <=0.30; output exact
failure_criteria: ratio >0.30 or semantic/receipt/exception drift
invalid_criteria: protocol/input/source drift, wrong executable/thread budget or command failure
provenance:
  source_commit: baseline 7a62d8e88f4b04fa5f20359649013a16bae909b0; optimized working diff implementation/kernel-final.patch
  install_overlay: NONE; explicit source import in identical interpreter
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: N/A; no live ROS graph
  gz_partition: N/A; no simulation
commands: final/run-comparison.zsh
observed: PENDING
conclusion: PENDING
next_experiment: EXP-009
```

## EXP-008 start

```yaml
status: RUNNING
observed: directed GREEN 42 passed, 0 skipped, exit 0; final three-round comparison process started
owned_process: exec session 10729 running final/run-comparison.zsh; per-round pid retained in environment.json
next_command: inspect final samples/outputs only after all six variant blocks exit
```

## EXP-007 / EXP-008 result

```yaml
status: VALID
exit_codes: [0, 0, 0, 0, 0, 0]
formal_baseline_suite_median_ms: 2126.4748855
formal_optimized_suite_median_ms: 579.94822925
primary_ratio: 0.2727275234730253
speedup: 3.6666632955324254
output_gate: all 24 fixture output files exactly equal frozen characterization documents; every measured repeat equals its warmup
source_gate: input/harness/protocol and product hashes unchanged
summary: final/summary.json
analysis_note: aggregation script first checked logical executable string; sys.executable reports physical /Users/matianyi/ros2_jazzy alias. Corrected check to samefile fixed interpreter. Raw runs unaffected.
conclusion: approved implementation meets the CPU-only latency and complete-output equivalence criteria; package/provenance gate remains
next_experiment: EXP-009
```

## EXP-009

```yaml
experiment_id: EXP-009
status: PLANNED
prior_experiment: EXP-008
hypothesis: unchanged dependencies and task-only fresh installation preserve ordinary package behavior
prediction: complete test/ scope with xdist 8 passes, installed product hashes match benchmark source
single_variable: task-private build/install of approved scoped patch
lifecycle: FULL_RESTART
preconditions:
  - no benchmark measurement running
  - fresh checkout from local frozen bundle inside registered evidence root
  - fixed runtime overlays and CPython; no dependency installs
  - macOS short scratch receipt registered under this evidence root
success_criteria: build exit 0, expected installed prefix/modules; full ordinary test/ xdist 8 zero failures/errors and colcon test-result zero failures
failure_criteria: product/hash drift or test assertion failure
invalid_criteria: wrong interpreter/overlay/tempdir; collection or runner failure
provenance:
  source_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0 plus implementation/kernel-final.patch
  install_overlay: build/install/so101_demo_py under existing registered root
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: no live ROS graph
  gz_partition: no simulation
commands: build/build-package.zsh then tests/package/run-gate.zsh
observed: PENDING
conclusion: PENDING
next_experiment: EXP-010 counters/profile and inline review
```

## EXP-009 build bootstrap correction

```yaml
status: INVALID
command: build/build-package-bundle-attempt.zsh
exit_code: 128
observed: transferred bundle is incremental and lacks prerequisite commit 074f7ae777a6e96f6a59e7d27f4be93a60fcd2a2 in an empty clone
conclusion: source bundle was already imported into task repository; build checkout must clone its now-complete local object graph
retry: clone only task codex branch with --no-local into previously nonexistent build/source, checkout exact frozen commit and apply captured patch; no source or benchmark changes
retained: build/clone-bundle-attempt.log; no build or test started in invalid attempt
```

## EXP-009 runner correction

```yaml
status: INVALID
command: build/build-package.zsh
exit_code: 2
observed: fixed colcon installation has no --allow-overriding extension; argument parsing refused before build
conclusion: omit unsupported optional flag; all build/install destinations remain task-private
source_checkout: build/source now exists on exact frozen commit with captured patch; no source change
retry: build/run-colcon.zsh
```

## EXP-009 build result / package gate start

```yaml
status: RUNNING
build_command: build/run-colcon.zsh
build_exit_code: 0
build_elapsed_s: 2.16
build_source: task-private build/source checkout of frozen commit plus captured scoped patch
build_note: byte compilation deliberately disabled; debug-provenance manifest emitted
dependency_inventory: build/preflight.json; fixed ROS dependencies found; rosdep Python keys are not ament package names
package_command: tests/package/run-gate.zsh
package_scope: complete src/so101_demo_py/test/; default not explicit_ml; no benchmark_test
workers: 8; loadscope
scratch: /opt/data/tmp/so101-service-gate-01a10735; identity and worker proof retained under tests/package; not a second evidence root
install_prefix: build/install/so101_demo_py
next_experiment: EXP-010
```

## EXP-009 colcon test runner failure

```yaml
status: INVALID
command: tests/package/run-gate.zsh
colcon_test_exit_code: 0
test_result_exit_code: 1
observed: xdist starts 8 workers but 0 items; all 8 collection errors fail loading @rpath/librosidl_typesupport_c.dylib
preflight: fixed Python imports rclpy and task installed package successfully before colcon subprocess environment boundary
conclusion: macOS shell/SIP environment boundary loses DYLD_LIBRARY_PATH; no testcase ran and no code RED
retained: tests/package gate.log, JUnit, scratch identity, worker proofs, test-result summary
retry: macOS documented direct fixed-Python full test/ -n8 path, same task installed overlay, fresh scratch; colcon test-result reads its actual JUnit
```

## EXP-009 first complete test result and correction

```yaml
status: INVALID
command: tests/package-direct/run-gate.zsh
exit_code: 1
counts: 3869 passed, 39 failed, 32 skipped; 3940 executed
elapsed_s: 33.17
failure_groups:
  - 32 socket-boundary assertions: registered helper leaf length plus xdist/testname exceeds Darwin 104-byte budget
  - 7 macOS fork-source contract assertions: independent build clone has empty locked submodule
conclusion: correct runner scratch to documented short unique /opt/data/tmp/ik.* and initialize copied locked submodule from local object graph; no product/test patch changes
sip_proof: tests/package/sip-boundary-proof.json; direct fixed Python retains DYLD, /bin/sh loses it
retry: tests/package-final/run-gate.zsh; full scope/workers preserved
retention: retain both failed scratch trees and all failed JUnit; no deletion
```

## EXP-009 final runner start

```yaml
status: RUNNING
fork_copy: clean detached 5a590b22770b270b71ba6a1c3443d4e67edc7f4b, fetched exact local object after initial clone did not include unreachable pin
fork_release_ref: copied local main ancestry 738e304551b4ea6db020b466086a13db71b65607; verified ancestor of locked pin
source_mutation: none in task product/test files; only isolated fork checkout populated
scratch: new unique /opt/data/tmp/ik.* per macOS ordinary gate guide; owner 0700 and 104-byte endpoint budget recorded
command: tests/package-final/run-gate.zsh
workers: 8
scope: full ordinary test/ unchanged
```

## EXP-009 result

```yaml
status: VALID
command: tests/package-final/run-gate.zsh
pytest_exit_code: 0
colcon_test_result_exit_code: 0
counts: 3910 passed, 30 skipped, 0 failures/errors; 3940 executed
elapsed_s: 33.47
workers: 8
install_gate: expected task prefix and all three product file hashes match formal optimized source
provenance: tests/package-final/preflight.json; worker-proofs.json; results/so101_demo_py/pytest.xml
conclusion: complete ordinary macOS regression gate passes from freshly built task installation; corrected all runner conditions without changing tests/product
next_experiment: EXP-010
```

## EXP-010

```yaml
experiment_id: EXP-010
status: RUNNING
prior_experiment: EXP-009
hypothesis: measured improvement comes from exact repeated work removal and FK reuse without changing logical candidate/path workload
prediction: requests/receipts/path-metric count unchanged; bottom solves equal unique requests; cached failures avoid duplicate work but all unique failed solves keep 200 iterations
single_variable: separate observational instrumentation of real baseline/optimized solver
lifecycle: FULL_RESTART
preconditions: formal latency and complete package gate exited; product/protocol hashes still fixed
success_criteria: exact complete output documents, documented request/hit/iteration/FK/failure cost and inclusive stage timings; separate real cProfile
failure_criteria: instrumentation changes output or fails original path workload checks
invalid_criteria: solver subclass disables cache; profiler/counters included in formal samples
provenance:
  source_commit: frozen baseline vs approved scoped working diff
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: N/A; no ROS boundary use
  gz_partition: N/A; no simulation
commands: final/run-diagnostics.zsh
observed: PENDING
conclusion: PENDING
next_experiment: completion review/checkpoint
```

## EXP-010 result

```yaml
status: VALID
exit_codes: counters baseline 0; counters optimized 0; optimized cProfile 0
source_type: exact builtin UnderactuatedPoseIk with observational method wrappers, no subclass
output_gate: all four full output documents exactly match frozen characterization
logical_workload: 1361 original requests and receipt documents, 1242 accepted candidate path-metric checks retained
compute_workload: bottom solves 1361 -> 781; exact solve hits 580; FK matrix calls 225593 -> 121669
iterations: 30968 -> 19268; every unique failed solve retains 200 iterations
failure_cost_instrumented_ms:
  p18_home: 3120.631 -> 914.382
  canonical_home: 0 -> 0
  outer_boundary: 2375.758 -> 570.784
  unreachable: 742.066 -> 316.065
stage_evidence: final/counters-comparison.json; inclusive intervals overlap and never substitute for formal latency
profile: final/profile-optimized/profile.txt; _matrix 1.793 s / prepare 3.533 s inclusive
conclusion: improvement is exact repeated-work removal and kernel invariant/FK reuse; candidate, score and safety path workload preserved
next_experiment: NONE
```

## CP-007 — completion checkpoint

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-010
current_hypothesis: CLOSED; performance and semantic acceptance achieved
working_tree_status: three product files, three regression files and two task documents; HEAD remains frozen base, scoped diff retained
owned_processes: current tmux Codex only; all benchmark/build/test/profile sessions exited
preserved_processes: all pre-existing host/tmux processes
preserved_worktrees: old HEAD values unchanged; user GUI skill/replica ledger dirty work present
confirmed_conclusions:
  - approved plan implemented inline on task branch
  - fresh aggregate ratio 0.2727275234730253 <= 0.30
  - full fixture outputs bit-identical and independent failed solves still 200 iterations
  - task install provenance and full xdist8 ordinary package gate passed
  - all source/protocol/harness hashes unchanged through measurement and validation
review: review/inline-review.md; review/scoped-diff.patch; review/result.md
open_risks:
  - benchmark is mac-mini pure compute, not ROS/MoveIt wait or live robot qualification
  - 22 Linux capability and 8 optional copied-prefix tests skipped as declared
retained: all baseline/intermediate/final/build/test/profile/review batches, including INVALID runs
archived: NONE
deletion_candidates: registered test/build scratch only; see review/final-retention.json; none deleted
native_goal_status: active after user approval; all objective gates achieved, ready to mark complete
next_command: final artifact verification then native update_goal complete and final report
```

## EXP-011 — retained cache-only workload audit

```yaml
experiment_id: EXP-011
status: RUNNING
prior_experiment: EXP-010
hypothesis: the retained first optimization snapshot accounts for duplicate-work savings independently of FK-kernel reuse
prediction: bottom requests/hits equal final cache counts; original kernel arithmetic remains; full outputs exact
single_variable: retained cache-only snapshot vs frozen baseline
lifecycle: FULL_RESTART
preconditions: no formal timing/tests running; rebuild audit source from frozen snapshot and three retained cache-only product files
success_criteria: exact original fixture outputs; recorded intermediate request/hit/FK/stage counts
failure_criteria: reconstructed source or behavior drift
invalid_criteria: instrumentation substitutes subclass, or new samples enter primary latency metric
provenance:
  source_commit: frozen baseline plus retained implementation/cache-kernel files
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: N/A
  gz_partition: N/A
command: final/counters.py --source implementation/cache-audit-source --out final/counters-cache-only
next_experiment: completion artifact inventory
```

## EXP-011 result

```yaml
status: VALID
exit_code: 0
output_gate: exact full output for all four fixtures
observed: cache-only original kernel 781 bottom solves, 580 exact solve hits, 140937 matrix calls; final optimized kernel 121669
per_fixture_matrix: p18_home 70142; canonical_home 13379; outer_boundary 37801; unreachable 19615
conclusion: retained intermediate audit independently accounts for cache reduction and additional iteration FK reduction; no new latency acceptance samples
next_experiment: NONE
```

## CP-008 — final verification ready

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-011
goal_acceptance: achieved; aggregate ratio <=0.30, exact output, regressions and fresh install provenance all verified
scope: three product files, three test files, two task documents; no other tracked paths changed
owned_processes: all experiment processes exited; current Codex only
retained: all registered evidence, including failed/invalid runner attempts and cache-only audit
archived: NONE
deletion_candidates: test/build scratch, review/final-retention.json; none deleted
native_goal_status: ready to mark complete
next_command: native update_goal complete; save returned status and final artifact index
```

## CP-009 — native goal complete

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-011
native_goal_status: complete
native_goal_receipt: review/goal-complete.json
native_goal_elapsed_s: 4876
goal_acceptance: verified; ratio 0.2727275234730253, exact outputs, task install, complete ordinary xdist8 gate
working_tree: task branch preserved; implementation remains uncommitted on frozen baseline HEAD
owned_processes: all experiment sessions completed; no task background worker remains
preserved_worktrees: old heads and existing user dirty work retained
retained: all evidence indexed in review/final-artifact-index.json
archived: NONE
deleted: NONE
deletion_candidates: registered scratch listed in review/final-retention.json; no deletion authorized
next_command: final user report; no further experiment required
```

## CP-010 — commit and push authorized

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-011
approval: user explicitly requested "commit & push" after acceptance
scope: commit the six verified product/test files and two task documents; push only codex/prepare-horizon-ik-20261004-01a10735 to Gitee origin
remote: git@gitee.com:zjumty/ros-moveit-demo.git
verification: current product/test diff exactly equals review/scoped-diff.patch; product hashes unchanged; saved full xdist8 gate has 3910 passed, 30 skipped, no failures/errors
source_changes_since_test: NONE
commit_message: perf(so101): reuse exact horizon IK and FK computations
publication_record: registered evidence root review/publish.json will retain commit, command exit codes and remote-ref verification
retained: existing evidence root and scratch classification preserved
archived: NONE
deleted: NONE
next_command: stage only eight task files, commit, push current codex branch and verify remote SHA
```

## CP-011 — second optimization goal authorized

```yaml
checkpoint_id: CP-011
approval: 用户明确要求“以此为goal，进行优化”，批准前述 FK 前缀复用及编译 CPU 内核方案
native_goal_status: active
baseline_commit: e1030ccf474f02105fdb62db19568255b1fce289
execution: mac-mini/Terry-Mac-mini.local, current Codex gpt-6.1-sol/xhigh inline; no dst or agents
worktree: existing task-owned isolated codex/prepare-horizon-ik-20261004-01a10735; initially clean
protocol: native50/protocol-v2.json, original frozen harness reused unchanged
objective: same four fixture equal-weight aggregate median optimized/baseline <=0.50; exact full outputs; single compute worker and BLAS/OMP all1
plan: docs/superpowers/plans/2026-10-05-prepare-horizon-ik-native.md
scope: IK numeric kernel and required build integration plus differential tests only
retained: original evidence unchanged; new native50 phase uses same registered evidence_root
archived: NONE
deleted: NONE
next_experiment: EXP-012 e1030ccf fixed-runtime baseline
```

## EXP-012 — second baseline

```yaml
experiment_id: EXP-012
status: PLANNED
single_variable: frozen e1030ccf source
lifecycle: FULL_RESTART
command: frozen baseline/characterize.py --source native50/baseline/source/src/so101_demo_py --mode measure --samples 5 --out native50/baseline/round0
success_criteria: identical complete output documents to original characterization, runtime/fixture/harness hashes preserved
invalid_criteria: source/runtime/input drift, profiling instrumentation, changed thread budget
next_experiment: prefix reuse RED and GREEN
```

## EXP-012 result / EXP-013 prefix reuse

```yaml
experiment_id: EXP-012
status: VALID
exit_code: 0
result: new baseline round0 full outputs exact to original characterization; p18 1109.828 ms, canonical 241.081 ms, boundary 595.720 ms, unreachable 303.249 ms
model_proof: read-only process argv verifies current codex -m gpt-6.1-sol -c model_reasoning_effort=xhigh --enable goals
next_experiment: EXP-013
```

```yaml
experiment_id: EXP-013
status: RUNNING
single_variable: shared FK prefixes and unchanged joint rotations in five finite differences
lifecycle: FULL_RESTART
red: native50/prefix-red-actual.log; intended assertion missing shared finite-difference FK
invalid_runner: native50/prefix-red.log, import failed before test ran; not RED
change: underactuated_ik.py prefix helpers plus solve adaptation; tests count actual 200 five-column updates instead of recomputed FK calls
numeric_gate: 84 vectors including signed zero and limits, six matrices per vector bit-identical, motion sin calls 30 -> 10
unit_gate: native50/prefix-green.log, 10 passed
timing: native50/prefix-measure, exploratory 3 samples/fixture, excluded from final acceptance
next_experiment: compiled kernel numeric primitive probe
```

## EXP-013 result / EXP-014 compiled primitive probe

```yaml
experiment_id: EXP-013
status: VALID
output_gate: all four complete output documents exact to e1030ccf baseline
exploratory_median_ms: 389.2193335
scope: prefix-only; 3 samples per fixture, not final acceptance
retained_source: native50/prefix-source
next_experiment: EXP-014
```

```yaml
experiment_id: EXP-014
status: PLANNED
single_variable: Cython float64 motion/residual primitives with original NumPy matrix multiplication retained
lifecycle: FULL_RESTART
build_tool: Cython 3.3.0 in native50/build-deps only; fixed runtime interpreter unchanged
probe: native50/probe, exploratory code retained, not product or final benchmark
hypothesis: eliminating tiny elementwise array allocations reduces remaining compute latency without changing bits
numeric_gate: probe original primitives vs native, actual URDF matrices plus finite random and boundary inputs
invalid_runner: first build exec could not enter nonexistent cwd; no compiler invoked
next_experiment: native primitive tests before product integration
```

## EXP-014 result / EXP-015 native integration

```yaml
experiment_id: EXP-014
status: VALID
motion_gate: 10020 exact float64 matrices
residual_gate: 2004 exact residuals
rejected_variant: handwritten sequential 4x4 product differs in 1884/2004 probes; never enters product
selected_primitive: original NumPy @ retained for every matrix product
next_experiment: EXP-015
```

```yaml
experiment_id: EXP-015
status: RUNNING
single_variable: Cython NumericKernel for shared FK and residual, unchanged NumPy products and solve
lifecycle: FULL_RESTART
red: native50/native-red.log intended missing compiled backend integration
first_build_invalid: wrong relative Cython source path; native-build.log missing generated C; corrected with fail-closed required extension and set -e
first_unit_failure: strided joint-limit input rejected by contiguous memoryview; native-green.log retained
correction: readonly strided input memoryview accepted; original references and buffers retained
packaging: checked-in generated Cython 3.3.0 C source, normal setuptools extension; runtime/build requires no installed Cython
exploratory_median_ms: 283.42734375, native-measure v1; full fixture outputs exact
next_experiment: native Jacobian assembly, independent RED -> GREEN
```

## EXP-015 result / EXP-016 Jacobian assembly

```yaml
experiment_id: EXP-015
status: VALID
corrected_numeric_gate: native-green-v2.log, 11 passed, no skips
full_output_gate: exact four real fixture outputs
next_experiment: EXP-016
```

```yaml
experiment_id: EXP-016
status: VALID
prior_experiment: EXP-015
single_variable: Cython Jacobian column assembly, original five perturbations and arithmetic retained
lifecycle: FULL_RESTART
red: jacobian-red.log, intended assertion missing native Jacobian
numeric_gate: jacobian-green.log 12 passed; numeric-expanded.log 16 passed, no skips
expanded_gate: arbitrary dense joint axes, reversed joint order, readonly strided limits, signed zero, small-angle/pi residual branches, invalid shape guards
exploratory_median_ms: 268.73497925, 3 samples/fixture; excluded from formal acceptance
full_output_gate: exact four real fixture documents to e1030ccf and original characterization
decision: KEEP for fresh installed verification
next_experiment: EXP-017
```

## CP-012 / EXP-017 — private build and installed gates

```yaml
checkpoint_id: CP-012
last_valid_experiment: EXP-016
native_goal_status: active
confirmed_conclusions: FK prefix reuse and Cython FK/residual/Jacobian preserve exact tested results; exploratory aggregate ~269 ms
current_worktree: task codex branch at e1030ccf; eight scoped product/test/task-document paths dirty
owned_processes: all exploratory compilers and timing processes completed
preserved_processes: existing tmux sessions untouched; no simulation launched
next_command: build private package from e1030ccf standalone clone plus scoped current files
```

```yaml
experiment_id: EXP-017
status: PLANNED
prior_experiment: EXP-016
hypothesis: normal package build loads the same compiled kernel without Cython in shared runtime
single_variable: source prototype -> task-private normal colcon install
lifecycle: FULL_RESTART
source_commit: e1030ccf plus six scoped product/test files
install_overlay: native50/build/install
runtime_executable: /opt/ros/jazzy/.venv/bin/python
ros_domain_id: N/A, no ROS nodes created
gz_partition: N/A, no simulation
success_criteria: native extension present and loaded from task install, exact source hashes, targeted and full ordinary xdist8 gate
invalid_criteria: shared venv mutation, stale installed binary, source drift or different interpreter
next_experiment: EXP-018 expanded solver trace equivalence and formal A/B
```

## EXP-017 result / EXP-018 solver trace differential

```yaml
experiment_id: EXP-017
status: VALID
build_exit: 0
build: native50/build/build.log and build.exit; normal colcon build, generated C, no Cython in runtime
install: native50/build/install/so101_demo_py
provenance: native50/tests/preflight.json; compiled extension and Python kernel load from task prefix; source hash exact
unit_gate: native50/tests/targeted.xml and targeted.log
package_gate: native50/tests/results/so101_demo_py/pytest.xml, xdist8, 3947 tests, 0 failures, 0 errors, 3916 passed, 31 skipped
scratch: native50/tests/scratch-identity.json; all eight worker tempfile proofs retained
next_experiment: EXP-018
```

```yaml
experiment_id: EXP-018
status: PLANNED
prior_experiment: EXP-017
hypothesis: full solve iterations preserve exact normal equation inputs/steps and outcomes beyond four acceptance fixtures
single_variable: frozen e1030ccf solver vs newly installed native solver
lifecycle: FULL_RESTART
source_commit: e1030ccf vs scoped installed implementation, native50/source-hashes.json
install_overlay: native50/build/install/so101_demo_py
runtime_executable: /opt/ros/jazzy/.venv/bin/python
ros_domain_id: N/A
gz_partition: N/A
input: native50/solver-diff/inputs.json generated once from frozen baseline; random targets/seeds, joint limits, signed zero, exact/nextafter position and orientation gates, integer target, invalid and nonfinite seeds
success_criteria: exact per-case output and all linear solve lhs/rhs/step byte hashes and lossless npz arrays
profiling: independent instrumented process, excluded from formal timing
next_experiment: EXP-019 installed formal interleaved A/B
```

## EXP-018 result / EXP-017 metadata follow-up

```yaml
experiment_id: EXP-018
status: VALID
cases: 64
updates: 6043
outcome_gate: exact solutions in float.hex and exact exception type/args
trace_gate: all normal-equation lhs/rhs and raw solve steps bit-identical, lossless per-case arrays also byte-identical
inputs_sha256: c8e6946670fab0dc0b4b3d39d457deffdb91e81dbba97ceb2ae3a906eefecac0
evidence: native50/solver-diff/comparison.json, baseline/optimized .json/.npz/.meta.json
next_experiment: EXP-019
```

```yaml
experiment_id: EXP-017-M1
status: PLANNED
prior_experiment: EXP-017
single_variable: restore imported fork release main metadata in task-owned new submodule clone only
reason: initial gate gained one skip because clone of detached fork copied origin/main but no local main ref
ref: refs/remotes/origin/main = 738e304551b4ea6db020b466086a13db71b65607, same exact local main in retained original build fork
head_preserved: 5a590b22770b270b71ba6a1c3443d4e67edc7f4b
source_and_install_changes: NONE
full_gate: repeat complete xdist8 gate in native50/tests-final; earlier native50/tests and its scratch retained
next_experiment: EXP-019 formal A/B
```

## EXP-019 — formal installed A/B

```yaml
experiment_id: EXP-019
status: PLANNED
prior_experiment: EXP-018
hypothesis: new installed kernel reduces frozen-suite compute median by at least 50% against e1030ccf
single_variable: baseline archive vs task-private installed compiled kernel
lifecycle: FULL_RESTART
source_commit: e1030ccf vs native50/source-hashes.json
install_overlay: native50/build/install/so101_demo_py via installed-harness links
runtime_executable: /opt/ros/jazzy/.venv/bin/python, unchanged NumPy 2.4.6/Accelerate
ros_domain_id: N/A
gz_partition: N/A
command: native50/final/run-ab.py, invokes unchanged original harness
protocol: native50/protocol-v2.json, SHA256 ed2f3e8ca0776be7dea8d2e277e1fc56c5f9f5ae7043d5d2b303c03efc98f810
order: B0,O0,O1,B1,B2,O2; 3 fresh processes per variant, 1 warmup and 5 measured calls per fixture per process
budget: one compute worker; VECLIB/OMP/OPENBLAS/MKL all1; tests/profiling/compiler processes must have exited
success_criteria: 15 samples/fixture/variant, aggregate median ratio <=0.50; all full outputs exact, all original source/input/runtime hashes preserved
invalid_criteria: changed source or input, profiling overlap, source rather than installed optimized artifact, changed thread budget
next_experiment: separate final profiling and inline review
```

## EXP-017-M1 result / EXP-019 result

```yaml
experiment_id: EXP-017-M1
status: VALID
source_changes: NONE
package_gate: native50/tests-final, 3917 passed, 30 skipped, 3947 executed, no errors/failures, xdist8, 33.17 s
skip_gate: same 30 skip identities as original accepted package gate; restored source-clone ref metadata only
next_experiment: EXP-019
```

```yaml
experiment_id: EXP-019
status: VALID
median_ms: baseline 576.89173975, optimized 277.768021
primary_ratio: 0.48149072323409003
reduction_pct: 51.850927676590996
full_output_gate: exact all four outputs in all six processes and every measured call
source_version: retained v3 kernel, native50/source-hashes-v3.json, original native50/build/source/install and final/ batch retained
decision: accepted performance result for v3; final delivery requires compatibility follow-up discovered in inline review
next_experiment: EXP-020
```

## EXP-020 — compatibility review correction and final source

```yaml
experiment_id: EXP-020
status: RUNNING
prior_experiment: EXP-019
discovery: inline review reproduced nonunique coordinate/chain layout and subclass FK regressions in accelerated path
red: native50/nonunique-red.log, two actual finite-difference failures; native50/subclass-red.log, custom FK model not honored
single_variable: accelerated prefix path restricted to exact built-in solver with unique independently named moving coordinates; all other layouts/subclasses use original per-coordinate FK
lifecycle: FULL_RESTART
source_commit: e1030ccf plus current scope in native50/source-hashes.json
install_overlay: native50/build-v4/install
runtime_executable: /opt/ros/jazzy/.venv/bin/python
ros_domain_id: N/A
gz_partition: N/A
scope: compatibility fallback only; Cython kernel unchanged; ordinary built-in native hot path unchanged
preservation: prior build/source/install, tests, source-hashes-v3 and formal samples retained; new standalone source clone has independent copied .git metadata
success_criteria: new regression tests pass, fresh normal build/native provenance, complete ordinary xdist8, 64 solver trace outcomes identical; fresh full interleaved A/B ratio <=0.50
next_experiment: EXP-021 separate profiling and final review
```

## EXP-020 environment correction

```yaml
initial_v4_targeted_gate: 52 passed, no skips/failures; duplicate layouts and subclass behavior pass
initial_v4_full_gate: native50/tests-v4, 3919 passed, 30 skipped, 1 failure in source asset symlink closure
classification: INVALID runner/source-clone preparation; copytree without symlinks=True expanded tracked source links
source_fix: recreate original symlinks from retained original clone; expanded copies moved to native50/build-v4/dereferenced-link-copies, none deleted
receipt: native50/build-v4/source-link-restoration.json
product_source_and_installed_bytes: unchanged; six source-hashes and compiled artifact identical
new_full_gate: native50/tests-v4-final, full ordinary xdist8; do not hide source assertion or reduce scope
formal_timing: final-v4 uses installed artifact; all compiler/test/instrumentation processes exited before timing; source-link restoration performed only after final-v4 timing completed
next_experiment: complete fresh full gate, then profile and review
```

## EXP-021 — final separate profile and workload counters

```yaml
experiment_id: EXP-021
status: PLANNED
prior_experiment: EXP-020
single_variable: separate instrumentation only, no source changes
lifecycle: FULL_RESTART
source_commit: e1030ccf plus native50/source-hashes.json
install_overlay: native50/build-v4/install/so101_demo_py
runtime_executable: /opt/ros/jazzy/.venv/bin/python
ros_domain_id: N/A
gz_partition: N/A
preconditions: formal A/B and complete package tests exited
command: unchanged original harness --mode profile; native50/counters.py on baseline and final installed-harness-v4; cold-import.py 3 interleaved pairs
success_criteria: exact complete outputs, 1361 requests/781 bottom solves/580 hits, original iterations and 200 failed iterations, unchanged receipt/path-sample work; retained profile and startup costs
operation_counts: derived rotation/product counts from measured FK/prefix calls and explicit unchanged loops, labeled derived rather than hardware instruction counters
timing_rule: all instrumented stage times overlap and do not enter primary median
next_experiment: inline review, retention inventory and goal completion
```

## EXP-020 / EXP-021 final results

```yaml
experiment_id: EXP-020
status: VALID
final_build: native50/build-v4, normal colcon, source Cython dependency absent in fixed runtime
source_fingerprints: native50/source-hashes.json and final-v4/source-hashes-used.json, unchanged through formal measurement and tests
targeted_gate: native50/tests-v4/targeted.xml, 52 passed
ordinary_package_gate: native50/tests-v4-final/results/so101_demo_py/pytest.xml, 3920 passed, 30 skipped, 3950 tests, 0 errors/failures, xdist8, 32.89 s
worker_proofs: native50/tests-v4-final/worker-proofs.json, all eight fixed-runtime workers use registered short scratch
formal_summary: native50/final-v4/summary.json
aggregate_median_ms: 581.14852075 -> 279.88808325
aggregate_p95_ms: 585.26275205 -> 285.5386499
primary_ratio: 0.48161196881098667
reduction_pct: 51.83880311890133
output_equivalence: exact all four full output docs across six fresh processes and every warmup/measured call
solver_trace: 64 cases / 6043 updates, exact solution/error outcomes and all lossless linear-system inputs/raw steps
decision: KEEP, goal acceptance achieved
next_experiment: EXP-021
```

```yaml
experiment_id: EXP-021
status: VALID
profile: native50/final-v4/profile/prepare.prof, 5.50M calls in 1.840 s; instrumented only
counter_comparison: native50/final-v4/counter-comparison.json
requests: 1361 -> 1361
bottom_solves: 781 -> 781
solve_cache_hits: 580 -> 580
iterations: 19268 -> 19268
failed_bottom_solves: 79 -> 79, all 200 iterations preserved
logical_fk_outputs: 121669 -> 121669
residuals: 112098 -> 112098
path_metrics: 1242 -> 1242
path_sample_points: 11178 -> 11178
moving_rotation_constructions_derived: 608345 -> 237025
matrix_products_derived: 1460028 -> 903048
native_jacobian_batches: 18566
startup: fresh-process kernel import including NumPy, median 27.891 ms baseline / 28.393 ms optimized; no runtime JIT
invalid_runner: first counters command omitted --mode measure; frozen fixture overwrite guard stopped execution, no fixture changed; corrected command/log retained
generated_source_proof: native50/review/generated-source-proof.json, byte-identical regeneration with isolated Cython 3.3.0
stage_timing_note: inclusive instrumentation times overlap and do not enter formal latency acceptance
next_experiment: NONE
```

## CP-013 — goal achieved, publication authorized

```yaml
checkpoint_id: CP-013
last_valid_experiment: EXP-021
native_goal_status: active, all compute/differential/build/test gates achieved, completing evidence and publication
execution: mac-mini gpt-6.1-sol/xhigh, inline self review; no agents/dst/GPU/ai-station/simulation
scope: four product/build files, two test files, two task documents
publication_authorization: earlier user instructions "commit & push" and "push到 Gitee 当前branch" persist; current task codex branch only, standard Git, no PR/merge/force
source_changes_after_validation: NONE; only task docs/evidence updated
retained: entire registered evidence root, including all exploratory/invalid/failed attempts, source copies and lossless traces
archived: NONE
deleted: NONE
deletion_candidates: task-owned build/temp and package scratch; receipt to native50/review/retention.json
next_command: final review/artifact verification, scoped commit/push current branch, native goal complete
```

## CP-014 — ai-station comparison authorized

```yaml
checkpoint_id: CP-014
last_valid_experiment: EXP-021
native_goal_status: complete; published 2966203300af093b7aa7235daf02261c91814a73
authorization: user requests before/after benchmark on ai-station using one isolated P core
execution: current mac-mini Codex orchestrates SSH batch commands; no delegated agent
current_commit: 2966203300af093b7aa7235daf02261c91814a73
working_tree_status: task ledger only modified for this benchmark
owned_processes: NONE before benchmark staging
preserved_processes: existing remote claude tmux; all remote checkouts and shared environments
confirmed_conclusions: EXP-020/021 Mac compute gates remain valid; do not infer Linux latency
disproven_routes: handwritten matrix product has float drift; excluded
open_risks: Linux output equivalence, native artifact provenance and temporary CPU partition validity
next_command: freeze EXP-022 protocol, stage exact commit archives and build isolated Linux artifacts
```

## EXP-022 — isolated ai-station P-core before/after comparison

```yaml
experiment_id: EXP-022
status: PLANNED
prior_experiment: EXP-020
hypothesis: exact prefix/native optimization reduces full prepare_horizon compute latency on Linux Intel P core
prediction: same-platform complete outputs match; new measurement distinguishes platform-specific performance from Mac results
single_variable: frozen source version; original 7a62d8e8, second-round baseline e1030ccf, optimized 296620330
lifecycle: FULL_RESTART
preconditions:
  - ai-station i9-13900HX verified; CPU14/15 are SMT siblings on physical P core7
  - task-owned cgroup v2 isolated partition reserves 14-15, benchmark affinity is exactly 14, sibling15 unused
  - all other cgroups exclude 14-15; partition state read before/after every process
  - exact /usr/bin/python3 3.12.3 and system NumPy 1.26.4 shared by all variants; BLAS/OMP threads1
  - fresh private normal installs built from archived exact commits; no existing checkout or shared install changes
success_criteria: all nine fresh processes exit0; complete output equality within and between Linux variants; valid CPU isolation and native provenance; report median/p95 and raw samples without assuming Linux50% result
failure_criteria: valid measured latency improvement below desired magnitude, or behavior mismatch
invalid_criteria: wrong source/module, CPU partition invalid, affinity drift, extra compute threads, missing raw evidence
provenance:
  source_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0 / e1030ccf474f02105fdb62db19568255b1fce289 / 2966203300af093b7aa7235daf02261c91814a73
  install_overlay: task-owned remote NVMe execution staging; exact paths in ai-station/protocol.json
  runtime_executable: /usr/bin/python3
  ros_domain_id: N/A; pure compute, no nodes launched
  gz_partition: N/A; no simulation
commands: exact staging/build/controller commands retained under evidence ai-station
observed: read-only preflight confirms boot CPU isolation absent, root cpuset controller enabled, noninteractive sudo available
inferred: cgroup isolated partition can reserve both SMT threads without reboot or modifying existing service configuration
conclusion: PENDING
evidence: existing sole root ai-station/ phase; remote directory is transient execution staging, canonical artifacts copied back with hashes
decision: PENDING
next_experiment: NONE
```

## EXP-022 invalid startup / EXP-023 correction

```yaml
experiment_id: EXP-022
status: INVALID
first_bad_boundary: enter-exec.py sched_setaffinity before moving into task cgroup; Errno22 because outside partition already excludes14-15
timed_samples: 0; NumPy and original timer had not started
isolation_gate: cgroup isolated state and outside masks were correct
restoration: before/after cpuset state identical; restored true
evidence: ai-station/attempt-01, full failed controls/protocol/logs
decision: REPEAT using new experiment id
next_experiment: EXP-023
```

```yaml
experiment_id: EXP-023
status: PLANNED
prior_experiment: EXP-022
single_variable: startup order only; enter owned CPU partition then bind14
lifecycle: FULL_RESTART
product_source_and_installs: exact same frozen commits and newly built private Linux artifacts; no rebuild needed
source_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0 / e1030ccf474f02105fdb62db19568255b1fce289 / 2966203300af093b7aa7235daf02261c91814a73
install_overlay: /data/tmp/so101-prepare-horizon-ik-20261004-01a10735-p14-01/install/<variant>/so101_demo_py
runtime_executable: /usr/bin/python3
ros_domain_id: N/A
gz_partition: N/A
protocol: ai-station/protocol-v2.json, original harness/fixtures, same nine-process balanced order, results-02 and new cgroup p14-02
criteria: identical to EXP-022; previous invalid attempt excluded; before/after restoration required
commands: task-owned tmux so101-prepare-ik-p14-02 launches run-controller-02.sh
observed: PENDING
conclusion: PENDING
decision: PENDING
next_experiment: NONE
```

## EXP-023 running gate

```yaml
experiment_id: EXP-023
status: RUNNING
preflight: task partition isolated, root/user/system/init effective CPUs0-13,16-31; benchmark PID2210363 affinity14 verified
first_original_process: actual frozen timer running, no extra compute process
build: all three normal colcon private installs exit0, optimized native CPython3.12 extension built using generated C
source_provenance: exact Git archives, unchanged original harness SHA e437b9d0 and frozen fixture SHA
observed_boundary: original-r0 sample3; not a final latency result
next_command: wait for all nine independent processes, verify complete outputs/provenance/isolation restoration, stream raw artifacts to sole root
```

## EXP-023 final isolated P-core results

```yaml
experiment_id: EXP-023
status: VALID
source_commit: original7a62d8e88f4b04fa5f20359649013a16bae909b0 / baselinee1030ccf474f02105fdb62db19568255b1fce289 / optimized2966203300af093b7aa7235daf02261c91814a73
install_overlay: /data/tmp/so101-prepare-horizon-ik-20261004-01a10735-p14-01/install/<variant>/so101_demo_py
runtime_executable: /usr/bin/python3, CPython3.12.3, NumPy1.26.4
ros_domain_id: N/A; no nodes created
gz_partition: N/A; no simulation
commands: ai-station/results-02/commands.json, nine fresh processes exit0; controller exit0; analyst exit0
cpu_contract: i9-13900HX physical P core7; cgroup isolated14-15; all benchmark threads affinity14; SMT15 user/nice/system ticks0 in all9 harness intervals
proof: nine before/after valid partitions, one computational thread, actualCPU14, se.nr_migrations delta0
formal_samples: 15 per fixture per variant, 180 timed calls total,36 warmups, balanced independent-process order
aggregate_median_ms: original3929.4576085 / baseline1110.83325925 / optimized519.264618
aggregate_p95_ms: original3943.484190875 / baseline1117.6667442 / optimized522.6159465999999
native_vs_baseline: ratio0.46745505113034813, reduction53.25449488696519%, speedup2.139243115636275
optimized_vs_original: ratio0.13214663949466043, reduction86.78533605053396%, speedup7.567350965745946
aggregate_cv: original0.0024774234329242896 / baseline0.0030572519310814337 / optimized0.004833966472832207
equivalence: all36 saved full output docs exact across Linux variants/processes; all180 timed calls equal own warmup by original harness assertion
source_gate: all archived source files and symlinks exact; installed299/299/300 Python-source files exact; optimized native artifact loaded
preserved_checkouts: remote heads57ab6f6c and0fbef114 unchanged, git status and submodules unchanged; shared environments untouched
cleanup: owned cgroup removed; root/user/system/init masks fully restored0-31; governor unchanged powersave; task tmux naturally exited, old claude preserved
retention: complete remote staging copied to sole root ai-station/remote-staging;10447 regular files611683632 bytes and150 links checked exactly; invalid EXP-022 retained
scope: pure real prepare_horizon compute; no full Linux package regression, perception benchmark, live/ROS/physics/GUI acceptance claim
local_analyzer_ordering: first attempt before scp finished failed on missing restore record; waited copy exit0 and recomputed successfully; no benchmark rerun or sample change
evidence: ai-station/summary.json, result.md, protocol-v2.json, post-audit.json, transfer-proof.json and raw results-02
decision: KEEP; same-P-core Linux comparison complete
next_experiment: NONE
```

## CP-015 — ai-station benchmark complete

```yaml
checkpoint_id: CP-015
last_valid_experiment: EXP-023
current_hypothesis: NONE
working_tree_status: only this task ledger modified; product/test source bytes identical to published296620330
owned_processes: NONE; all benchmark children exited and temporary task tmux ended
preserved_processes: original remote claude tmux and existing user work; no stack started
confirmed_conclusions: native optimization achieves53.25% median reduction on same isolated Intel P core; cumulative86.79%; all complete Linux outputs exact
disproven_routes: pre-partition affinity startup invalid, corrected once and excluded; handwritten matrix arithmetic still excluded
open_risks: NONE for requested pure-compute benchmark; live/platform package acceptance outside scope
evidence_root: existing /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735 only; ai-station NVMe directory is execution staging, fully copied back
retained: all prior and current valid/invalid batches, source/install copies and raw evidence
archived: NONE
deleted: NONE
deletion_candidates: exact paths in ai-station/retention.json; no deletion authorization
next_command: finalize evidence index and scoped ledger publication using existing commit/push authorization
```
