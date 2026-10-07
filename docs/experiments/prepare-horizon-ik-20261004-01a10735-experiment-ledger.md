# prepare_horizon CPU IK experiment ledger

```yaml
task_id: prepare-horizon-ik-20261004-01a10735
goal: extract the frozen weighted QuIK CPU backend into one independent ROS2 package consumed by so101_demo_py; baseline/protocol and concrete design before implementation approval
success_contract: one independent ROS2 QuIK package with explicit demo dependency, same-platform exact64requests/20horizon/2003FK, preserved in-process latency, standalone/ROS two-platform install, full ordinary xdist/CTest gates; explicit design/plan confirmation before implementation
worktree: /Users/matianyi/.codex/worktrees/0a4f/moveit-demo
branch: codex/prepare-horizon-ik-20261004-01a10735
base_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0
benchmark_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0
current_commit: f6ba3231c; approved QuIK package extraction implemented and tested; final artifact transport/review/publication pending
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
  - weighting first target is confirmed inEXP-039/042; completep18 failure remains, native iteration control next hypothesis
  - five-joint rank-safe linear algebra and separate pose-tolerance stopping may improve reliability; each variable must be isolated
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
full_loop_confirmed_conclusions:
  - EXP-031 median525.59152825 ->207.5054745ms; ratio0.394803689456157, reduction60.51963105438429%; absolute target259.632309ms achieved
  - full horizon18566 update matrices/rhs/raw steps exact; all24 full documents exact and120 timed calls validated
  - independent64case6043update traces exact on each of Mac/Linux; no cross-platform float equivalence claim
  - final normal Mac xdist8 ordinary gate3928passed30skipped; Linux directed42passed
  - complete remote transfer10564files151symlinks523928172bytes verified; old repos/submodules/tmux preserved; cpuset/governor restored
latest_checkpoint: CP-028
next_experiment: EXP-051 RUNNING; user approved complete package plan with ok; inline execution
retained: all evidence in registered root
archived: NONE
deletion_candidates: registered scratch/private builds/duplicates listed in review/final-retention.json, native50/review/retention.json, ai-station/retention.json and loop50/review/retention.json; none deleted
```

## Scope and authorization

Mac/source baseline only; no equivalence claim about ai-station dirty sources.
CPU-only, inline self review, no implementation agent or dst. During the initial
Mac optimization, ai-station access was outside scope. The current user request
authorizes SSH benchmark execution and temporary P-core isolation on ai-station.
Stack launch, merge, evidence deletion and shared dependency changes remain outside scope.
The user explicitly authorized commit and push to the current Gitee task branch;
that authorization applies to this continuing task and the completed full-loop optimization round.
The previous comparison request authorized isolated research adapters and comparative experiments for
QuIK and IKPy. The latest request authorizes retaining both current native and QuIK with a
compatible interface and explicit switch. The user explicitly confirmed the short implementation
design with "确认" before implementation. Read-only discovery and frozen baseline readback are complete. Native remains
the proposed default, and QuIK is an explicit optional backend. The research results
use common acceptance gates and task outcomes, rather than the previous optimization's
bitwise equivalence contract.
The subsequent formal setup request and explicit "ok" approve automatic dependency preparation
in owned prefixes on Ubuntu 24.04 x86_64 and Apple Silicon macOS. The reviewed protocol and
approval receipt are under `quik-setup-01/`; system package installation is exercised only inside
task-owned fresh Ubuntu containers. Shared host dependencies and checkouts remain unchanged.
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

## CP-016 — user approved full native loop optimization

```yaml
checkpoint_id: CP-016
last_valid_experiment: EXP-023
authorization: user says ok。设定目标，继续执行 after complete Cython loop/workspace/path-FK proposal
native_goal_status: active; no token budget
current_commit: 505e06ad1e211bb488828a33a8cb9b75953cc87e
working_tree_status: initially clean isolated task worktree
execution: current mac-mini Codex gpt-6.1-sol/xhigh; inline; no dst/agents
contract: exact outputs and solver traces; finite differences retained; one compute/BLAS thread; target <=259.632309 ms and <=0.50 contemporaneous control ratio
confirmed_conclusions: EXP-023 trustworthy Linux baseline519.264618ms; original fixtures/harness retained
disproven_routes: EXP-014 handwritten 4x4 product drifts; do not retry or replace NumPy backend without new differentiating evidence
owned_processes: NONE at preflight
preserved_processes: remote claude tmux, all prior checkouts, shared environments
next_command: EXP-024 isolated current native baseline and separate Linux profile
```

## EXP-024 — current native Linux baseline and separate profile

```yaml
experiment_id: EXP-024
status: PLANNED
prior_experiment: EXP-023
hypothesis: remaining Python solve/control, gate object creation and NumPy dispatch/allocation dominate reducible Linux cost
prediction: new single-P-core profile distinguishes actual Linux stage cost from Mac profile
single_variable: instrumentation in separate process; product/source unchanged
lifecycle: FULL_RESTART
preconditions: verified ai-station, P14/P15 topology, existing private install, no simulation or conflicting task
success_criteria: baseline full documents exact to EXP-023; current latency quantified; independent profile; before/after CPU isolation proofs and complete restoration
failure_criteria: valid profile shows limited reducible Python cost; retain evidence
invalid_criteria: stale source/native artifact, altered frozen harness/fixtures, affinity/thread/partition failure
provenance:
  source_commit: 2966203300af093b7aa7235daf02261c91814a73
  install_overlay: /data/tmp/so101-prepare-horizon-ik-20261004-01a10735-p14-01/install/optimized/so101_demo_py
  runtime_executable: /usr/bin/python3, Python3.12.3 NumPy1.26.4
  ros_domain_id: N/A; no ROS nodes
  gz_partition: N/A; no simulation
commands: loop50/isolate-and-run-v2.py, unchanged timer harness --mode measure; separate --mode profile
observed: PENDING
conclusion: PENDING
evidence: registered root loop50/baseline-profile-01
decision: PENDING
next_experiment: EXP-025 native full loop RED/GREEN and differential
```

## EXP-024 result

```yaml
status: VALID
exit_codes: baseline0, profile0, controller0
median_ms: 534.924531
full_output_gate: exact to EXP-023 optimized all four complete Linux documents
profile: loop50/baseline-profile-01/profile-r0/profile.txt; 5.13M calls,3.430s; inclusive times overlap, not formal timing
observed: solve2.624s; pose construction0.864s across solve/FK; path checks0.667s; generator/native perturbation0.511s
restoration: complete cpuset masks restored; one thread CPU14 both processes
conclusion: native outer loop and deferred unused gate quaternions are supported candidates; profile alone does not guarantee50%
next_experiment: EXP-025
```

## EXP-025 — compiled outer solve loop

```yaml
status: RUNNING
prior_experiment: EXP-024
single_variable: complete Cython iteration and short-circuited unused quaternion gate
lifecycle: FULL_RESTART
source_commit: 505e06ad plus scoped kernel/wrapper/test diff
install_overlay: task-private loop50/dev-v1/runtime
runtime_executable: /opt/ros/jazzy/.venv/bin/python
ros_domain_id: N/A
gz_partition: N/A
red: loop50/loop-red.log, expected missing native solve capability, exit1
criteria: exact complete update traces and full horizon docs; no change to 200 finite differences, solve or clip
next_experiment: workspace reuse
```

## EXP-025 Mac result / EXP-026 workspace

```yaml
experiment_id: EXP-025
status: VALID
loop_green: 20 passed;64cases6043 lossless updates/outcomes exact
mac_exploratory_median_ms: 242.00062475; full documents exact
linux_measurement: separate v1 normal install and profile pending
next_experiment: EXP-026
```

```yaml
experiment_id: EXP-026
status: RUNNING
prior_experiment: EXP-025
single_variable: invocation-local reusable motion/residual/Jacobian/damping buffers
lifecycle: FULL_RESTART
source_commit: 505e06ad plus scoped diff
install_overlay: loop50/dev-v2/runtime
runtime_executable: /opt/ros/jazzy/.venv/bin/python
ros_domain_id: N/A
gz_partition: N/A
red: workspace-red.log exit1,3800 explicit arrays in failed200-update solve
invalid_preparation: first copy command wrong cwd, no compiler invoked; corrected with explicit workspace cwd
criteria: bounded explicit workspace construction; exact update traces/full outputs; isolated per-call ownership
next_experiment: path FK specialization
```

## EXP-026 result / EXP-027 path FK

```yaml
experiment_id: EXP-026
status: VALID
workspace_green:21passed;64cases6043updates exact; explicit allocations bounded<=20
mac_exploratory_median_ms:213.5720835; full documents exact
next_experiment:EXP-027
```

```yaml
experiment_id: EXP-027
status: RUNNING
prior_experiment: EXP-026
single_variable: exact path sample position batch without unused quaternion/Pose objects
lifecycle: FULL_RESTART
source_commit:505e06ad plus scoped diff
install_overlay:loop50/dev-v3/runtime
runtime_executable:/opt/ros/jazzy/.venv/bin/python
ros_domain_id:N/A
gz_partition:N/A
red:path-red.log exit1, missing position batch in two collected tests
criteria: true endpoints and9interpolated points retained; same exact keys/local lifetime; identical metrics and complete documents
next_experiment: native remaining dispatch profile
```

## EXP-027 result / EXP-028 direct NumPy dispatch

```yaml
experiment_id: EXP-027
status: VALID
path_green:38passed after correct fixed ROS overlay; first invocation missing moveit_msgs classified environment failure
invalid_measurement:path-measure started before directed test exit confirmed; excluded
mac_exploratory_median_ms:190.068302 from path-measure-clean; full outputs exact
next_experiment:EXP-028
```

```yaml
experiment_id: EXP-028
status: RUNNING
prior_experiment: EXP-027
single_variable: NumPy own resolved matrix product loop called directly into per-call slots; same multiplication algorithm/order
lifecycle: FULL_RESTART
source_commit:505e06ad plus scoped diff
install_overlay:loop50/dev-v4/runtime
runtime_executable:/opt/ros/jazzy/.venv/bin/python
ros_domain_id:N/A
gz_partition:N/A
probe:3000 bit-identical matrix cases independently on NumPy2.4.6 Mac and1.26.4 Linux; own versioned NumPy capsule, no handwritten product
red:product-red.log exit1, missing product capability
compatibility: explicit supported minor versions1.26/2.4; unsupported/capsule mismatch/custom origins fall back to NumPy; GIL held; capsule retains all pointers; FPE arithmetic replayed through normal NumPy policy; alias protected
criteria: exact all solver traces/full outputs; bounded workspace; no warnings/errors/ownership regression
next_experiment: normal installed Mac/Linux validation and formal P-core A/B
```

## EXP-028 primitive review / EXP-029 compatibility

```yaml
experiment_id: EXP-028
status: VALID
primitive_green:23tests;64cases6043updates/outcomes exact; complete fixture outputs exact
mac_exploratory_median_ms:105.8751455
first_primitive_failure: test incorrectly assumed BLAS overflow must raise; same-platform NumPy reference does not raise on Mac; corrected to compare reference error/result policy
next_experiment:EXP-029
```

```yaml
experiment_id: EXP-029
status: RUNNING
prior_experiment: EXP-028
single_variable: eager-validation compatibility fallback for nonrigid/custom FK
lifecycle: FULL_RESTART
source_commit:505e06ad plus scoped diff
install_overlay:loop50/dev-v5/runtime; numeric binary unchanged fromv4
runtime_executable:/opt/ros/jazzy/.venv/bin/python
ros_domain_id:N/A
gz_partition:N/A
red:compatibility-red.log, nonrigid custom chain original error args differed when quaternion gate was deferred
correction: full loop/position specialization only for rigid standard transforms and unmodified instance hooks; other layouts retain original validation/forward cache path
criteria: original exception args/fallback/customization maintained; exact frozen outputs/traces
next_experiment:EXP-030 normal installed gates and formal Linux comparison
```

## EXP-029 result / EXP-030 installed gates

```yaml
experiment_id:EXP-029
status:VALID
gate:41passed; nonrigid original exception restored; unknown NumPy ABI uses exact fallback
numeric_binary:unchanged from EXP-028
next_experiment:EXP-030
```

```yaml
experiment_id:EXP-030
status:PLANNED
prior_experiment:EXP-029
single_variable:prototype -> normal private colcon source/install
lifecycle:FULL_RESTART
source_commit:505e06ad plus source-hashes-v5.json
install_overlay:loop50/mac-build/install, remote install-v5
runtime_executable:fixed Mac ROS Python, Linux/usr/bin/python3
ros_domain_id:N/A
gz_partition:N/A
preconditions:generated C fixed; no Cython in runtime; full isolated source closure and independent fork metadata
criteria:native origins correct; directed+complete ordinary xdist8 package gates; exact64case traces; own supported ABI active
next_experiment:EXP-031 formal isolated Linux B/O comparison
```

## EXP-030 v5 result / final shape guard

```yaml
status:RUNNING
mac_v5_package:3927passed30skipped;3957tests0failures/errors,xdist8,32.91s
linux_v5_exploratory:521.7389945 ->206.10252825ms; exact full outputs; original NumPy1.26.4 own product kernel active; cpuset restored
shape_red:shape-red.log, four-element malformed target got different dimension error; corrected native buffer shape guard before unchecked residual
final_source:source-hashes-final.json; native input shape and released ABI/layout validation only; ordinary valid compute arithmetic unchanged
final_gates: fresh normal builds, same directed/full ordinary scope, frozen64cases, separate formal B/O
linux_dependencies:system benchmark Python has pytest/ROS, lacks xdist/mujoco; no shared environment changes; ordinary module package gate runs on fixed Mac runtime; Linux directed numeric/ROS and full solver/horizon differential below
next_experiment:EXP-031
```

## EXP-031 — final installed isolated P-core A/B

```yaml
experiment_id:EXP-031
status:PLANNED
prior_experiment:EXP-030
single_variable:296620330 baseline vs frozen source-hashes-final.json native loop
lifecycle:FULL_RESTART
source_commit:296620330 vs505e06ad+final scoped hashes
install_overlay:remote retained baseline install/optimized vs install-v6
runtime_executable:/usr/bin/python3 Python3.12.3 NumPy1.26.4
ros_domain_id:N/A
gz_partition:N/A
protocol:loop50/protocol-final.json frozen before measured run
order:B0,O0,O1,B1,B2,O2;3fresh processes per variant;1warmup+5samples per fixture/process
preconditions:builds,tests,differential/profile exited; P14/P15 isolated physical core; one thread/BLAS1
criteria:15samples/fixture/variant; median ratio<=.50 and optimized<=259.632309ms; exact full outputs; native/source/resource provenance; allaffinity14, sibling15idle, zero migrations, full restoration
invalid_criteria:source/input/runtime/thread/provenance drift or competing task
command:isolate-and-run-final.py
evidence:loop50/formal-final
next_experiment:final inline review and retention/publication
```


## EXP-030 final installed result

```yaml
experiment_id:EXP-030
status:VALID
final_sources:loop50/source-hashes-final.json; v6
normal_builds:Mac private colcon and Linux private colcon both exit0
mac_gate:3958total;3928passed30skipped0failures/errors;xdist8;32.77s
mac_gate_evidence:loop50/tests-final/{results/so101_demo_py/pytest.xml,worker-proofs.json,preflight.json,gate.exit,test-result.exit}
linux_directed:42passed0skipped0errors/failures;2.32s
linux_scope_limit:full Linux ordinary gate not run; system benchmark Python lacks xdist/mujoco; shared dependencies unchanged; complete ordinary package gate on fixed Mac ROS runtime
solver_differential:64frozen cases6043updates per platform; full outcomes and all lossless lhs/rhs/rawstep bytes exact against same-platform baseline
generated_C:private Cython3.3.0 reproduction byte-identical
next_experiment:EXP-031
```

## EXP-031 final result

```yaml
experiment_id:EXP-031
status:VALID
lifecycle:FULL_RESTART
source_commit:2966203300af093b7aa7235daf02261c91814a73 vs505e06ad+source-hashes-final.json
install_overlay:retained remote install/optimized vs private install-v6
runtime_executable:/usr/bin/python3 Python3.12.3 NumPy1.26.4
ros_domain_id:N/A
gz_partition:N/A
command:isolate-and-run-final.py; all6processes exit0
statistic:median of15 equal-weight four-fixture mean samples per variant; p95linear
baseline_median_p95_ms:525.59152825 /535.5663462
optimized_median_p95_ms:207.5054745 /209.743708575
ratio:0.394803689456157
reduction_percent:60.51963105438429
absolute_target_ms:259.632309
result:GOAL_ACHIEVED
CV:baseline.0136692905 optimized.0096946984
per_round_medians_ms:baseline[535.429951,525.59152825,518.844133];optimized[204.76225475,209.37816875,207.5054745]
outputs:24saved full documents byte-identical;120timedcalls checked against full warmup outputs
CPU:physical Pcore7;isolated cpuset14-15; one task affinity14 and actualCPU14; sibling15user/nice/system ticks0; migrations0
restoration:all cpuset masks exactly restored; powersave governor unchanged
protocol_metadata_note:inherited variants label baseline/profile; frozen explicit order and6command/provenance records specify baseline/optimized; no profile enters statistics
scope:real prepare_horizon entry-return, no ROS waits/GUI/physics/live qualification
comparison_note:prior campaign519.264618ms remains historical evidence; contemporaneous525.59152825ms control used for formal ratio
artifacts:loop50/{protocol-final.json,formal-final,summary.json,result.md}
next_experiment:EXP-032 final inline review/counters/retention
```

| Frozen fixture | Baseline median / p95 ms | Full-loop median / p95 ms |
|---|---:|---:|
| p18_home | 1028.455 / 1050.101 | 401.316 / 409.711 |
| canonical_home | 321.793 / 331.773 | 142.530 / 146.434 |
| outer_boundary | 508.102 / 516.774 | 193.666 / 196.723 |
| unreachable | 245.273 / 249.390 | 91.166 / 92.020 |
| Equal-weight suite | 525.592 / 535.566 | 207.505 / 209.744 |

## EXP-032 full workload update trace and final inline review

```yaml
experiment_id:EXP-032
status:VALID
prior_experiment:EXP-031
single_variable:separate instrumentation, excluded from acceptance latency
lifecycle:FULL_RESTART
source_install_runtime:unchanged final v6 and retained296620330 installations, Linux Python3.12.3 NumPy1.26.4
ros_domain_id:N/A
gz_partition:N/A
command:counters-final.py baseline /optimized; both exit0
workload_counts_exact:1361requests781bottomsolves79failed18566updates19268iterations580cachehits1242pathmetrics11178ninepoints
lossless_result:all18566 normal-equation matrices/right-hand sides/raw steps byte-identical; complete warmup documents unchanged
implementation:whole Cython iteration loop, invocation-local reusable arrays, deferred unused quaternion construction, own resolved NumPy product loop, exact position batching/cache
unchanged:finite differences epsilon1e-5/damping1e-5/200iterations/stepcap.20;14waypoints/beam3/seeds/order/scoring/gates/9samples
compatibility:experimental NumPy capsule explicitly limited to released1.26.x/2.4.x; tested1.26.4Linux/2.4.6Mac; other versions/layouts/custom hooks retain NumPy/original paths; same speedup not promised elsewhere
review:GIL and capsule lifetime retained; disjoint workspaces and public alias guard; floating error policy replays exceptional products through NumPy; malformed-target and nonrigid-chain original errors covered
transfer:10564files151symlinks523928172bytes exact; all staging retained in registered root loop50/remote-staging
runner_corrections:read-only audit corrected sources-v6 to actual source-v6; macOS tar consumed7AppleDouble metadata files, restored exact originals with direct copy and verified all inventory hashes; no product or formal measurement changed
preservation:old remote repos/status/submodule hashes and claude tmux byte-identical; all owned cpuset groups absent
retention:all root retained; archivedNONE; deletedNONE; deletion candidates in loop50/review/retention.json
next_experiment:NONE; authorized current Gitee branch publication
```

## CP-017 — full-loop goal achieved, publication ready

```yaml
checkpoint_id:CP-017
last_valid_experiment:EXP-032
current_hypothesis:NONE
working_tree_status:only4product files,1numeric test file,task plan and experiment ledger
native_goal_status:active until evidence/publication finished; no token budget
confirmed_conclusions:formal60.52% reduction; absolute207.505ms<=259.632309ms; exact outputs/updates; installed gates and complete transfer passed
owned_processes:NONE; remote controller/instrumentation/tests/build/transfer exited
preserved_processes:all prior tmux/worktrees/checkouts and shared environments
retained:sole registered evidence root including loop50
archived:NONE
deletion_candidates:private builds/prototypes/duplicate remote staging and registered test scratch; no authorization to delete
next_command:scoped commit and standard git push origin current codex branch; verify remote hash then mark goal complete
```


## CP-018 — current Gitee branch published

```yaml
checkpoint_id:CP-018
last_valid_experiment:EXP-032
product_commit:204ff2e0857bbf538747a976b73b48650ff04069
publication:normal git push origin codex/prepare-horizon-ik-20261004-01a10735 exit0; git ls-remote matches product commit
final_commit_metadata:registered root loop50/publish.json (includes documentation closeout commit)
source_after_validation:all5final scoped source/test hashes unchanged; documentation closeout only
native_goal_final_status:registered root loop50/goal-final.json
owned_processes:NONE
retained:all prior runs and loop50 in sole registered root
archived:NONE
deleted:NONE
deletion_candidates:registered scratch and private build/prototype/duplicate staging entries in loop50/review/retention.json; authorization required
open_hypotheses:NONE
next_command:NONE; final remote hash and native goal status are recorded in immutable delivery metadata
```


## EXP-033 — explicit native IK dependency pins

```yaml
experiment_id:EXP-033
status:RUNNING
prior_experiment:EXP-032
user_authorization:explicit request to enforce library versions in startup scripts or dependency-management configuration
last_trustworthy_checkpoint:CP-018
hypothesis:NumPy constraints currently only in native dispatch checks, not main package install metadata; dependency resolver can admit an unvalidated version
prediction:installer metadata selects exactly1.26.4 forLinux and2.4.6 forDarwin, rejecting mismatched patch/minor/prerelease versions; same installed IK lock is shipped
single_variable:dependency declaration only; native/Python numerical source and generatedC unchanged
lifecycle:FULL_RESTART
source_commit:94d6a6b28066ebe2e789e301bfb5792ddfe2d1bf plus scoped config/setup/test/ledger diff
install_overlay:private dependency-lock-01/mac-build/install
runtime_executable:/opt/ros/jazzy/.venv/bin/python CPython3.11; current NumPy2.4.6 unchanged
ros_domain_id:N/A
gz_partition:N/A
preconditions:clean isolated task worktree; base doctorPASS; existing task tmux preserved; no stack/agents/dependency installation
success_criteria:platform marker/lock/install metadata contract RED ->GREEN; fresh normal private install; complete ordinary so101_demo_py/test xdist8 gate
invalid_criteria:shared environment/source/overlay changes or wrong provenance
evidence:sole root dependency-lock-01
next_experiment:NONE; inline review and persistent authorized current-branch publication
```


## EXP-033 directed and installed checkpoint

```yaml
red:3 intended assertion failures, missing NumPy install metadata and missing shipped lock
runner_invalid:pytest-rerunfailures loopback bind denied before testcase; retained runner-bind-denied.*; authorized host execution corrected it
implementation:config/ik/requirements.lock withLinux numpy==1.26.4 andDarwin numpy==2.4.6; setup.py reads this single lock into install_requires; installed_resources ships lock
metadata_contract:11directed tests passed; platform marker selects one pin and rejects differing patch/minor/prerelease; installed metadata independently verified for both platform selections
normal_build:private colcon build exit0; native kernel source unchanged; no shared dependency installation
installed_runtime:fixed Mac Python3.11.15 NumPy2.4.6; native direct NumPy kernel active; immediate-success IK smoke passed
full_package_gate:RUNNING, same complete ordinary test scope xdist8
GUI_physics_controller:N/A; dependency-only headless scope
```


## EXP-033 final result

```yaml
experiment_id:EXP-033
status:VALID
runtime_executable:/opt/ros/jazzy/.venv/bin/python;CPython3.11.15 NumPy2.4.6
source_commit:94d6a6b28 plus3setup/lock/test changes; shipped commit in dependency-lock-01/publish.json
install_overlay:registered root dependency-lock-01/mac-build/install
ros_domain_id:N/A
gz_partition:N/A
red:3expected assertions failed after host runner correction; initial sandbox preconfiguration failure retained INVALID
changes:exact Linux NumPy1.26.4 /Darwin2.4.6 platform requirements lock; setup.py single-source install_requires; lock shipped through existing installed_resources
directed:11passed; actual marker selection and rejection of wrong patch/minor/prerelease versions
normal_build:exit0; actual installed distribution requirements and installed lock SHA exact
runtime:fixed Mac NumPy2.4.6 unchanged; private installed native kernel active; immediate-success IK smoke pass
full_package:3961total3931passed30skipped0errors/failures;xdist8;32.97s;colcon test-result exit0
full_scope:complete ordinary src/so101_demo_py/test;benchmark_test not collected
provenance:all8 worker/tempfile proofs; logical CPUs10; fixed runtime; newly built task private install and full new source clone
numeric_equivalence_scope:all5previous final numerical source/test hashes unchanged; no new latency or Linux native-runtime measurement
Linux_version_contract:verified using actual packaging marker evaluation and installed Requires-Dist; no dependency install or remote runtime change
evidence:dependency-lock-01/{red.*,green.*,mac-build,installed-metadata.json,tests-final,verification.json,retention.json}
GUI_physics_controller:N/A; dependency configuration only; no stack launched
review:inline self review; no agents/dst; no unresolved findings
retained:entire phase and all prior registered-root evidence
archived:NONE
deleted:NONE
deletion_candidates:task private clone/build/install and registered Mac test scratch; retention.json; no authorization to delete
next_experiment:NONE
```

## CP-019 — dependency constraints verified

```yaml
checkpoint_id:CP-019
last_valid_experiment:EXP-033
current_hypothesis:NONE
current_commit:registered root dependency-lock-01/publish.json
confirmed_conclusions:NumPy exact platform pins consumed by setup and shipped with package; fresh installed metadata verified; full ordinary xdist8 gate passed; numerical code unchanged
working_tree_status:setup.py,new IK requirements lock,new dependency regression test and task ledger only
owned_processes:NONE; private build and tests exited
preserved_processes:existing so101-ik-cpu-20261004 tmux and all old checkouts/shared runtime
open_risks:NONE for dependency-declaration scope
next_command:authorized current-branch commit/push; record remote equality in delivery metadata
```

## EXP-034 — QuIK and IKPy isolated comparison setup

```yaml
experiment_id: EXP-034
status: PLANNED
prior_experiment: EXP-033
user_authorization: research QuIK and IKPy and compare experimentally with the current solver; previous same isolated ai-station P-core requirement and current Gitee branch publication apply
scope: research prototypes only; no production numerical implementation or dependency changes; no robot or ROS stack execution
source_commit: bb9a9c5a045410d62d25bd76380ae5401cdee76c
QuIK_commit: a9ebd1f21dfd3c9f0869140dfb0a4ae5a538cccc
IKPy_commit: e76c285c06121b2c7c71fc7541a1a9e571b03873
hypothesis: analytic fixed-size C++ QuIK can reduce solve cost; IKPy offers bounded URDF optimization but its residual and convergence policy differ
single_variable: solver backend through experimental adapter; shared robot, request data and independent acceptance gates
lifecycle: FULL_RESTART
evidence: sole registered root solver-compare-01; remote task-owned staging copied back with integrity inventory
preconditions: existing installed current native kernel; Python3.12.3 NumPy1.26.4; no shared installs or checkout changes; old processes preserved
geometry_gate: retained DH conversion and reduced URDF reproduce canonical FK on home, bounds and 2000 frozen random joint vectors before timing
primary_measurement: identical frozen 64 requests, independent position/orientation/control-margin gates; invalid input cases identified separately
secondary_measurement: same four frozen prepare_horizon fixtures; retain complete receipts and solver-dependent path/acceptance differences
CPU_protocol: CPU14 on physical P core7, SMT15 reserved idle, one computational thread, fresh balanced-order processes, cpuset restored in finally
success_criteria: valid geometry and isolation, raw quality and latency for every backend; failures retained and not converted to accepted solutions
invalid_criteria: geometry mismatch, wrong loaded source, extra computational threads, migration, shared environment changes or un-restored isolation
equivalence_claim: foreign algorithms are not expected to be bitwise equivalent; assess common numerical gates and task outcome
next_experiment: EXP-035 pilot, then frozen formal protocol
```

## EXP-034 result and EXP-035 pilot

```yaml
experiment_id: EXP-034
status: VALID
model_gate: 2003 frozen vectors including home/control bounds; max_abs QuIK4.3298697960381105e-15 /IKPy1.1102230246251565e-15 <1e-12
setup_invalid_runs: early copy provenance check; missing iostream in upstream non-self-contained header; two DH common-normal precision failures; all retained, no numerical timing
corrections: shim include iostream; SVD rank tolerance1e-12 for axes parallel to1e-15; analytic cross-product direction for almost intersecting axes; no robot parameters or gate changed
foreign_geometry: same retained canonical URDF; exact original chain reduced forIKPy; audited five-row standardDH forQuIK
dependencies: existing Linux Python3.12.3 NumPy1.26.4 SciPy1.11.4 SymPy1.12 Eigen3 GCC13.3; no installs; IKPy4.1.0 from frozen source; noJAX
QuIK_options: constructor code differs from README; retain actual defaults and separately explicit recommended damped configuration
analytics_control: IKPy import HTTP disabled, its daemon joined before process proof/timing; numerical modules unmodified
next_experiment: EXP-035
---
experiment_id: EXP-035
status: PLANNED
single_variable: solver backend, five labeled variants; all input data and shared gates unchanged
lifecycle: FULL_RESTART
variants: current,quik-default,quik(damped),ikpy,ikpy-weighted
protocol: solver-compare-01/protocol-pilot-01.json
CPU: isolated physicalPcore7, CPU14, SMT15 idle; group owned bytask and restored finally
samples: one64request warmup+one timed repetition; four horizon warmups+one timed repetition
purpose: adapter contract, deterministic output and runtime sizing; excluded from formal statistics
success_criteria: all geometry/source/isolation/gate proofs; rejected candidates preserved; process exits0
invalid_criteria: adapter/runner defect, migration, extra thread or un-restored cpuset
next_experiment: EXP-036 frozen balanced formal comparison
```

## EXP-035 pilot result / EXP-036 formal protocol

```yaml
experiment_id: EXP-035
status: VALID
proof: five child processes exited0; CPU14 only; migrations0; SMT15 user/nice/system tick deltas0; original cpuset restored
finite_request_success: current34/60; QuIK_actual_defaults37/60; QuIK_damped36/60; IKPy38/60; IKPy_weighted42/60
task_outcome: current and IKPy_weighted complete both p18_home and canonical_home; other variants complete canonical_home only; all reject outer_boundary/unreachable
interpretation: QuIK early rejection cannot count as same-workload horizon acceleration; IKPy weight adaptation restores the lost supported task but is slower
evidence: solver-compare-01/pilot-summary.json,pilot-validation.json; complete raw pilot copied back after formal
next_experiment: EXP-036
---
experiment_id: EXP-036
status: PLANNED
single_variable: same five solver backends; parameters unchanged from pilot
lifecycle: FULL_RESTART
protocol: solver-compare-01/protocol-formal-01.json
order: five rotating offsets0,2,4,1,3; every variant occupies each of five process positions once
samples: five fresh processes per variant; one warmup+three timed observations per frozen request and fixture per process
same_core: isolated CPU14, physicalPcore7, reserved idleSMT15; one computational thread and BLAS/OMP1
statistics: 15observations per request/fixture, pooled median and linearp95; equal-weight fourfixture suite; failed/successful request latency separated
quality: same independent finite/control-margin/position/orientation gates; full receipts and selected steps retained; no foreign bitwise equivalence claim
invalid_criteria: model/source/output drift, extra threads, migrations, SMT activity or un-restored cpuset
publication: experimental report and ledger only; no production solver replacement
next_experiment: NONE after complete evidence verification and inline review
```

## EXP-036 result / EXP-037 first-divergence diagnostic

```yaml
experiment_id: EXP-036
status: VALID
execution: all25freshprocesses exited0; all timed outputs equal own warmups and across five processes
geometry: 2003FK vectors <1e-12, unchanged fromEXP-034
isolation: all25before/after proofs one thread CPU14 only, migrationdelta0, SMT15user/nice/system tickdelta0; all cpuset state restored
canonical_baseline: every current full output document byte-identical to prior EXP-031 Linux formal documents
fixed64: four input-validation cases reported separately; each of60finite requests15timed observations per variant,900times per variant
fixed_median_ms: current1.2460615; QuIKdefault0.1477905; QuIKdamped0.1491135; IKPy6.583842; IKPyweighted5.672289
finite_success: 34/60,37/60,36/60,38/60,42/60 respectively; deliberate adversarial/extrema/far-seed suite, not field reliability
p18_horizon: current396.029877ms/14steps; bothQuIKvariants andIKPystock fail to complete; IKPyweighted1554.263709ms/14steps
canonical_horizon_ms: current139.621868; QuIKdefault203.351664; QuIKdamped102.041179; IKPy1130.266684; IKPyweighted1098.609465; all14steps
quality: foreign solutions/residuals/branches differ; all shared independent gates preserved; no illegal output accepted; early rejection not a valid same-workload speedup
remote_state: oldtwo checkouts/submodules andclaude tmux unchanged; governor powersave unchanged; task groups removed
transfer: 647files120925839bytes0symlinks copied and SHA/size checked; later untimed diagnostic recorded separately
additional_required_gate: explicit perception benchmark_test via colcon xdist8,585total553passed32failed0skip; all32 CONFIG_SHA256_MISMATCH
gate_root_cause: actual YAML5c8b0046 versus embedded511e0e64; both source and installed files exactly equal original7a62d8e8 frozen baseline; unrelated pre-existing inconsistency, no product edits
next_experiment: EXP-037
---
experiment_id: EXP-037
status: PLANNED
purpose: explain lost p18 task at first waypoint using frozen target and all14same seeds
single_variable: same solver backend; parameters unchanged; no timing claim and no retuning
lifecycle: FULL_RESTART
inputs: EXP-036 current-r0 firstMOVE_ABOVE_OBJECT waypoint and QuIKdamped first-segment14seed receipts
CPU: same isolatedCPU14 physicalPcore7/SMT15 idle; private diagnostic group restored finally
success_criteria: independent bounds/position/orientation rejection classification with fullrawcandidate retained
evidence: solver-compare-01/protocol-diagnostic-01.json and complete remote diagnostic copy
next_experiment: NONE
```

## EXP-037 result and CP-020 — solver comparison complete

```yaml
experiment_id: EXP-037
status: VALID
first_waypoint_same14seeds: current14accepted; QuIKdefault13; QuIKdamped0; IKPystock0; IKPyweighted14
first_rejection: QuIKdamped position4.625mm/orientation0.00156rad; IKPystock position4.873mm/orientation0.000822rad; all14inlimit candidates fail2mmpositiongate
weighted_result: position0.274mm/orientation0.01446rad,14/14accepted; unchanged2mm/0.10rad gates
default_QuIK: 13first-target accepted andonebounds rejection; full p18fails later; no claim oneparameter repairs allcases
diagnostic_isolation: oneCPU14thread, migrationdelta0, SMT15tickdelta0; controllerexit0 andcpusetfullyrestored
numeric_source: unchanged; no QuIK/IKPy production adoption
final_remote_inventory: 660files121152175bytes0symlinks; complete canonical copy SHA/size verified; earlier formal647file inventory also retained
topology_clarification: CPU14/SMT15 are P-core ordinal7(eighthPcore); actual Linuxcore_id28, hardware.json; historical Pcore7 label denotes ordinal
report: docs/experiments/prepare-horizon-ik-quik-ikpy-comparison-20261006.md
evidence: solver-compare-01/analysis.json,comparison.png,comparison.svg,remote-staging,package-benchmark-gate,retention.json
review: inline self review; no agents/dst; no unresolved IK evidence/protocol findings
unresolved_repository_gate: 32pre-existing perception configSHA failures reproduced from unchanged original frozenbaseline; no all-tests-pass claim
retained: all registered-root pilot/formal/diagnostic/invalid evidence, including existing phases
archived: NONE
deleted: NONE
deletion_candidates: task remote staging, duplicate clones/builds and test/cache scratch; no deletion authorization
next_experiment: NONE
---
checkpoint_id: CP-020
last_valid_experiment: EXP-037
current_commit: numericalbb9a9c5a; report/ledger delivery commit in solver-compare-01/publish.json
confirmed_conclusions: QuIK~0.15ms IK but loses p18; weightedIKPy retains two supported fixtures but3.86x four-fixture suite latency; foreign outputs not bitwise equivalent
recommendation: keep current production solver; future analytic derivative/bounded native solve work requires separate reviewed plan and outcome/equivalence contract
working_tree: task ledger andnew comparison audit report only
owned_processes: NONE; all private benchmark/test/controller processes exited
preserved_processes: oldcheckouts/submodules,existingclaude tmux; no stack launched; cpusetrestored
next_command: authorized current Gitee branch commit/push; verify remote HEAD equality
```

## EXP-038 — QuIK-only phase, unchanged baseline

```yaml
experiment_id: EXP-038
status: PLANNED
prior_experiment: EXP-036 and EXP-037
hypothesis: the unchanged QuIK/current binary and frozen fixtures remain reproducible in the current ai-station environment after IKPy is excluded from candidacy
prediction: complete fixed/horizon output documents match EXP-036; latency and isolation are freshly measured, so implementation approval can review a concrete baseline
single_variable: NONE; exact same current/QuIK configurations; fresh balanced three-backend baseline excluding IKPy
lifecycle: FULL_RESTART
preconditions: CP-020 restored; Mac task worktree clean before ledger edit and isolated on codex/ branch; old main/worktrees untouched; no remote stack; existing claude tmux preserved; CPU14 sibling15 verified; no existing isolated cpuset
success_criteria: original output documents identical; all child commands exit0; one CPU14 thread; zero measured migrations and sibling15 user/nice/system ticks; cgroup fully restored
failure_criteria: effective solver gates and supported task outcomes may remain poor; expected QuIK failures are retained, not invalidated or counted as speedup
invalid_criteria: binary/input/provenance mismatch, output drift, extra computational threads, migration, sibling activity or un-restored isolation
provenance:
  source_commit: 867a33e5ab7dc79033ecfe58c162deef0cd77b9f; numerical bb9a9c5a
  install_overlay: /data/tmp/so101-prepare-horizon-ik-20261004-01a10735-loop50-01/install-v6/so101_demo_py
  runtime_executable: /usr/bin/python3 on ai-station; exact frozen libquik_compare.so copied to task-owned staging
  ros_domain_id: N/A, pure computation; no ROS stack
  gz_partition: N/A, pure computation; no simulator
commands: original run_compare.py and isolate_and_run.py under protocol-baseline-01.json; exit codes PENDING
sampling: 3 fresh processes per current/quik-default/quik(damped), each order position once; warmup separate; 3 timed observations per request/fixture,9 per input
evidence: sole registered root quik-position-01; temporary remote execution staging copied back and hash-verified
observed: original QuIK SO SHA b4272715f4d01c62ba00dfc24df5621c4ded261c5420e8c964cd64bfb51a2e2f exists; Python3.12.3, CPU14/SMT15, no prior cpuset isolation
inferred: weight must apply to both error and Jacobian/Halley matrix; 6x6 undamped covariance has rank<=5 and no SPD guarantee
conclusion: PENDING
scope: no optimized solver code, no production dependency replacement, no implementation plan execution before approval
retention: retain all; archive/delete none
next_experiment: reviewed QuIK adaptation protocol, not yet authorized for implementation
```

```yaml
experiment_id: EXP-038
status: RUNNING
provenance_verified: all7 harness/input/shim hashes and protocol44680818c85a... match local freeze; original QuIK SO b4272715f4d0... unchanged; no output directory existed before run
command: ssh -T -o BatchMode=yes ai-station 'sudo -n /usr/bin/python3 /data/tmp/so101-prepare-horizon-ik-20261004-01a10735-quik-position-01/isolate_and_run.py'
exit_code: PENDING
```

## EXP-038 result and CP-021 — baseline complete, QuIK adaptation review ready

```yaml
experiment_id: EXP-038
status: VALID
commands: all9 unchanged child processes exit0; isolation controller exit0
provenance: original QuIK binary and7 harness/input/shim hashes exact; every fixed-output/full-horizon/outcome document byte-identical EXP-036
isolation: all9 before/after proofs one thread on CPU14, zero measured migrations, zero SMT15 user/nice/system ticks; cpuset fully restored
preserved: both existing remote checkout HEAD/status/submodule snapshots, claude tmux, powersave governor unchanged
baseline_IK_median_ms: current1.353919; QuIKdefault0.156998; QuIKdamped0.167873
baseline_IK_p95_ms: current7.9336798; QuIKdefault0.1967096; QuIKdamped0.2923462
baseline_supported_horizon_median_ms: currentp18=422.064161/currentcanonical=149.569951; QuIKdampedp18 rejected/QuIKdampedcanonical=120.536319
quality: current34/60; QuIKdefault37/60 andQuIKdamped36/60 retain only27/34 current successes; p18 lost by both QuIK configs; no valid complete-workload speedup claim
baseline_samples: nine observations per request/fixture, excluded from future optimization formal acceptance
first_loss_classification: dampedQuIK finite current-success losses7; six candidates violate bounds, one orientation_gate_below fails position; positive_inf_seed extra contract case also lost
new_design: weighted native QuIK/Halley; separate staged matrix/metric weighting, damped5x5 solve, per-request pose/control exit,0.2rad step cap, bound-aware iteration; independent canonical FK gates unchanged
measurement_protocol: final current/originalQuIK/adaptedQuIK six fresh processes each, all6 order permutations,3 measured repetitions per input; quality gating precedes timing and no formal retuning
native_code: scoped C++ shim/header adaptation in task-owned experimental copies; production source unchanged
approval_status: PENDING; current user authorized investigation/baseline; AGENTS and initial handoff require concrete-plan confirmation before new implementation
scope: pure headless computation; ROS_DOMAIN_ID/GZ_PARTITION N/A, no simulator/robot/GUI output
package_tests: NOT_RUN; no production or benchmark code changed, original research harness byte-identical; prior unrelated32 perception configSHA failures remain retained and unresolved
evidence: quik-position-01/baseline-analysis.json,review-protocol.json,inline-review.json,remote-staging
transfer: 127files6455036bytes0symlinks plusinventory copied to sole registered root; every recorded SHA/size verified
retained: complete baseline/protocol/review records and prior phases
archived: NONE
deleted: NONE
deletion_candidates: remote temporary staging/duplicate original binary only; no deletion authorization
next_experiment: QuIK adaptation stageA after user approval, not yet started
---
checkpoint_id: CP-021
last_valid_experiment: EXP-038
current_commit: 867a33e5ab7dc79033ecfe58c162deef0cd77b9f
confirmed_conclusions: unchanged QuIK speed opportunity reproducible, position and bound failures persist; IKPy excluded by user
current_hypothesis: weighted native QuIK plus controlled joint updates may retain current successes and reduce successful full-horizon latency
working_tree_status: task experiment ledger only; original product and benchmark source unchanged
owned_processes: NONE; controller/children/copyback complete
preserved_processes: remote existingclaude tmux andoldcheckout state; no stack launched
open_risks: adapted convergence/limits/supported-horizon latency unmeasured; native implementation not approved yet
next_command: user review of quik-position-01/review-protocol.json; implementation after explicit approval
```

## EXP-039 — weighted QuIK first-target RED/GREEN

```yaml
experiment_id: EXP-039
status: PLANNED
prior_experiment: EXP-037,EXP-038
user_authorization: explicit approval to try QuIK weighting and pass the position gate; inline Codex as originally instructed; IKPy excluded
scope: stageA only, residual/matrix/progress weighting0.08; no5x5/early-exit/step-cap/bound-policy tuning in this experiment
hypothesis: weighting the rotational residual and corresponding linear-system rows restores the first p18 target's2mm position gate without changing pose/control thresholds
prediction: original dampedQuIK fails14/14 frozen seeds for position; weighted variant passes those position gates; raworientation andlimits independently checked
single_variable: W=diag(1,1,1,0.08,0.08,0.08) metric consistently applied to linear solves and error-progress norm
lifecycle: FULL_RESTART
preconditions: CP-021 baseline exact, task worktree has ledger edits only; originalbinary preserved; fresh private weighted-01 source/binary copies; no robot or stack; CPU14/SMT15 available
success_criteria: explicit real-code RED testexit1 on original position assertion, then GREEN testexit0 on all14 originalseeds with canonical position/orientation/control gates; geometry2003-vector gate unchanged
failure_criteria: valid weighted outputs still fail original pose orcontrol gates; no threshold widening orpost-solve clipping rescue
invalid_criteria: wrongbinary/model/import; errors before intendedassertion; migration/extra thread/SMT activity; un-restored cpuset
provenance:
  source_commit: 867a33e5ab7dc79033ecfe58c162deef0cd77b9f; current numericalbb9a9c5a
  QuIK_commit: a9ebd1f21dfd3c9f0869140dfb0a4ae5a538cccc, original frozen copy preserved
  install_overlay: /data/tmp/so101-prepare-horizon-ik-20261004-01a10735-loop50-01/install-v6/so101_demo_py
  runtime_executable: /usr/bin/python3; originallibquik_compare.so and separately builtlibquik_weighted.so
  ros_domain_id: N/A, purecompute
  gz_partition: N/A, purecompute
commands: isolate_position_gate.py/test_first_position_gate.py; PENDING
observed: original first-target failure reproduced inEXP-037; fresh RED required before weightedcore implementation
inferred: weights must affect RHS, matrix and progressnorm; raw geometric Jacobian/Hessian remain unchanged
conclusion: PENDING
evidence: sole root quik-position-01/weighted-01; original14seed fixture andallcandidate details retained
next_experiment: EXP-040 fixed/fullhorizon weightedpilot, then frozen formal A/B if outcome validates the speedcomparison
```

```yaml
experiment_id: EXP-039
status: RUNNING
RED: fresh actualtestexit1,14expectedposition subtestfailures,0errors; all14positions4.624558754..4.624562105mm; orientation andlimits alreadypass; CPU restored
implementation: only weighted progressnorm andbothmatrix/RHS rows in copied IKSolver.hpp; raw J/hessianProduct unchanged; same200iterations/lambda_squared1e-10/clamps/gradient budgets; originalheader andbinary preserved
next_command: compile separate weighted SO, same14seed GREEN, no5x5/stop/step/bounds-policy modifications
```

## EXP-039 result / EXP-040 weighted quality pilot

```yaml
experiment_id: EXP-039
status: VALID
RED: testexit1,14position failures0errors on original dampedQuIK,4.624558754..4.624562105mm
GREEN: same actualtestexit0,14/14accepted; position0.274384178..0.274384354mm,orientation0.014458829855..0.014458830378rad; allcontrolbounds pass
geometry: originalandweighted both2003vectors max_abs4.3298697960381105e-15 <1e-12; unchanged URDF73ab5bdd2645...
weighted_build: GCC13.3 sameflagsO3/ffp-contract=off,no fastmath; exit0; SO74523747023cf4cef7de881a028ac79c6ac7ae964c35bce2a879a02c21fa9a37
isolation: bothRED/GREEN oneCPU14thread, zero measured migrations/SMT15ticks; cpuset restored
conclusion: weighting is sufficient to recover the first p18 target's position gate across all14 original seeds; complete horizon and broader success retention not yet established
next_experiment: EXP-040
---
experiment_id: EXP-040
status: PLANNED
prior_experiment: EXP-039
hypothesis: weight-only QuIK also recovers supported completehorizons without requiring step/limit/stop policy changes
prediction: p18 first divergence removed; all64fixed request and4full horizon outputs classify remaining failures before any formal speedup claim
single_variable: weighted metric only, originaldamped versusweighted; current native retained asreference
lifecycle: FULL_RESTART
preconditions: originalandnewSO/source proven; geometryand14seed testpass; unchangedsearch/limits/tolerance overrides; no external stack
success_criteria: allcommands exit0, deterministictimed/warmup output; quality independently checked; both supported14step horizons checked; everycurrent-success loss identified
failure_criteria: valid retained limit/pose/task rejection, report rather than widen thresholds orclip finalsolution
invalid_criteria: source/output drift, isolation violation, un-restored cpuset
provenance:
  source_commit: 867a33e5ab7dc79033ecfe58c162deef0cd77b9f; numericalbb9a9c5a
  install_overlay: /data/tmp/so101-prepare-horizon-ik-20261004-01a10735-loop50-01/install-v6/so101_demo_py
  runtime_executable: /usr/bin/python3 plusseparatefrozen andweightedSO
  ros_domain_id: N/A
  gz_partition: N/A
commands: isolate_and_run.py withprotocol-pilot-01.json,threefreshprocesses,1warmup+1measurement perinput; PENDING
observed: firsttarget GREEN14/14
inferred: nativecompiled weightchange addslittlework but remaining far-seed branch/limits maystillfail
conclusion: PENDING
evidence: sole root quik-position-01/weighted-01/pilot-01
next_experiment: frozen formal weight-onlycomparison after inspecting pilot; nocurrentfallback andno furtherkernelretuning
```

## EXP-040 result / EXP-041 bounded weight grid

```yaml
experiment_id: EXP-040
status: VALID
execution: threefreshprocesses exit0, deterministic outputs; isolationcontroller restoredcpuset
fixed_quality: weight0.08 accepts37/60; retains30/34 current successes, loses4 for bounds; improves from originaldamped27/34
horizon: weight0.08 p18 passesMOVE_ABOVE waypoints1..5 butrejectsall15seed calls atwaypoint6; canonical14steps complete; outer/unreachable rejected
remaining_boundary: current waypoint6 selectedwristq=1.65606 atcontroluppermargin0.002rad; currentposition0.979591mm/ori0.029289rad; weightedq wrist outsidebounds andposition4.97..8.38mm in first/lastdiagnosticrows
diagnostic_limit: additionalwaypoint6 replay untimed/unpinned, explicitlynot latency or isolation evidence; retained separately
conclusion: positionweighting fixesfirsttarget but0.08alone doesnot restorefullp18; no successfulp18 accelerationclaim
next_experiment: EXP-041, two additionalweights frozenbeforemeasurement; allotherQuIK settings unchanged
---
experiment_id: EXP-041
status: PLANNED
prior_experiment: EXP-040
hypothesis: smallerorientationweight may find afeasible position/pose compromise atbound-limitedwaypoint6 without changingbound orstep/stopping policy
prediction: weight0.04 or0.02 mayreduceout-of-limit compromise; fullhorizon andalloriginalgates determine success
single_variable: orientationresidualweight,0.04 and0.02;0.02 equalsdefaultposition/orientation tolerance ratio0.002/0.10
lifecycle: FULL_RESTART
preconditions: same frozeninputs/current/originalbinary, existingweight0.08 sourceandSO kept; template/controlbounds unchanged
success_criteria: complete14step p18/canonical, acceptedsolutions independent canonicalgates; current-success retention separatelyreported
failure_criteria: remaininglimit/pose/horizon rejection withcompletecandidates retained; no fallback/rescue
invalid_criteria: source/determinism/isolation defects
provenance:
  source_commit: 867a33e5ab7dc79033ecfe58c162deef0cd77b9f; numericalbb9a9c5a
  install_overlay: existing privatev6 currentinstall
  runtime_executable: /usr/bin/python3, separatelybuilt004/002weightedSOs
  ros_domain_id: N/A
  gz_partition: N/A
commands: build_weight_grid.py thenisolate_and_run.py withprotocol-weight-grid-01.json; PENDING
observed:0.08 lossboundary providednewdiscriminatingevidence
inferred: bound-limited unconstrained solution maystill requirebound-awareiterations; thisexperimenttestsonlyweighting
bounded_loop: three totalweights0.08/0.04/0.02, zero additionalretunes; no stagesB/C/D/E execution
conclusion: PENDING
evidence: quik-position-01/weighted-01/weight-grid-01
next_experiment: finalize weight-onlyfindings andspeedcomparison, preservingremaininglimits
```

## EXP-041 result / EXP-042 formal characterization

```yaml
experiment_id: EXP-041
status: VALID
execution: bothfreshprocesses exit0, warmup/timed outputs deterministic; cpuset restored
weight0.04: accepts40/60,retains30/34 current finite successes; fourlosses allbounds
weight0.02: accepts40/60,retains29/34 current finite successes; fivelosses allbounds
full_horizon: bothweights passfirstfiveMOVE_ABOVEwaypoints andfailwaypoint6; canonical14stepscomplete; outer/unreachable rejected
conclusion: bounded weight-onlysearch exhausted; weight0.08 fixesfirsttarget but allthreeweights retainbound-relatedfullp18failure; stopretuning andreport scope truthfully
next_experiment: EXP-042 characterization only; no broadenedsolverimplementation
---
experiment_id: EXP-042
status: PLANNED
prior_experiment: EXP-039,EXP-040,EXP-041
hypothesis: weightednative QuIK retains low solve cost and canonical fullhorizon latency, whilepartialquality canbe separated fromspeed
prediction: sameweightconfig outputsduring15independentobservations; allweightedp18failures remain failures andnotcounted assuccessfulspeedup
single_variable: weightedmetricbackend; allthreepilotweights frozen, noformalretuning
lifecycle: FULL_RESTART
preconditions: weightsearchclosed; originalbinary unchanged; independentgeometryandRED/GREEN verified; frozen64requests/4fixtures andallgates
success_criteria: quality/latency characterization evidencecomplete; everytime outputownwarmup andfreshprocesses equal; actualbinary/source pathproven; sameCPU14one thread, zero measuredmigrations/SMTactivity, fullyrestoredcpuset
failure_criteria: fullp18 andall34success retentionstillfail; thosearevalidcandidatequalificationfailures, notinvalidruns
invalid_criteria: geometry/source/output/isolation/restoredefect
provenance:
  source_commit: 867a33e5ab7dc79033ecfe58c162deef0cd77b9f; numericalbb9a9c5a
  install_overlay: existingprivatev6 currentinstall
  runtime_executable: /usr/bin/python3, frozenoriginalandthreeweightedSOvariants
  ros_domain_id: N/A
  gz_partition: N/A
commands: isolate_and_run.py withfrozenprotocol-formal-01.json;25freshprocesses,5eachvariantx3reps; PENDING
statistics:15perinput; median/linear-p95; shared-success ratios separately; canonicalcompletehorizon latencyvalid, incompletep18timecannotcountasspeedup
package_gate: firstMaccolconattempt INVALID beforetestexecution, pytest_rerunfailures bind127.0.0.1 sandboxPermissionError; host-access retry unchangedscope planned, new scratch/results retained
observed: actualpilotquality above; noreadyproductionreplacement
inferred: remaining bound-aware solve work distinctfromresidualweighting, wouldrequire next reviewedexperiment
conclusion: PENDING
evidence: quik-position-01/weighted-01/formal-01 andpackage gateevidence
next_experiment: NONE; stageA report afterverification, nofurtherkernelchanges
```

```yaml
experiment_id: EXP-042
status: RUNNING
frozen_protocol: formal-01 fivevariant rotatingorders0,2,4,1,3; loadedweightedsource/binary hashes captured
formal_execution:25freshchildren all exit0; controllerexit0, cpusetrestored; completecopyback/proofanalysis PENDING
final_gate: all4QuIKlibraries2003FKvectorchecks pass; all3weightedvariants14/14 firsttargetgatepass onisolatedCPU14
firsttarget_position_mm: original4.624559..4.624562; weight0.08=0.274384178..0.274384354;0.04=0.071450761..0.071450799;0.02=0.018050491..0.018050503
package_gate: hostaccessretry ranactualsuite andhasfailures; counts/rootcause readback PENDING; originalsandboxrun retainedasINVALID
```

## EXP-043 — remaining waypoint6 boundary, all frozen weights

```yaml
experiment_id: EXP-043
status: PLANNED
prior_experiment: EXP-042
hypothesis: unchanged weightedvariants' fullp18failure is associated with nativeunconstrained joint updates at a bound-limited target, ratherthan geometry conversion
prediction: replay actual15failedseeds pervariant fromformal receipts, classify position/orientation/control rejection; currentselectedsolution shows a feasible tolerated pose at wrist upperbound
single_variable: NONE; diagnostic readback ofsameweights andactualseedbank, untimed
lifecycle: FULL_RESTART
preconditions: formalall25 exited0; cpusetrestored; no retuning, no otherkernel modifications
success_criteria: fullrawcandidates andindependentgate classifications preserved; isolatedCPU14one thread, zero migrations/SMTticks, cpusetrestored
failure_criteria: expectedvalid pose/limitfailure retained, no rescue
invalid_criteria: wrongtarget/seed/source, isolation orrestore defects
provenance:
  source_commit: 867a33e5ab7dc79033ecfe58c162deef0cd77b9f; numericalbb9a9c5a
  install_overlay: existingprivatev6currentinstall
  runtime_executable: /usr/bin/python3 andthethreefrozenweightedSOs
  ros_domain_id: N/A
  gz_partition: N/A
commands: isolate_remaining_diagnostic.py,protocol-remaining-boundary-01.json; PENDING
observed: allthreepilot/fullmeasurements stop atsamewaypoint6
inferred: box-constrained iterationmaybenextrequiredmethod, outsidecurrentweight-onlyscope
conclusion: PENDING
evidence: quik-position-01/weighted-01/remaining-boundary-01
next_experiment: NONE; closeauthorizedweight-onlytrial andpublishfindings
```

## EXP-042 / EXP-043 results and CP-022 — weight-only trial complete

```yaml
experiment_id: EXP-042
status: VALID
execution: 25freshprocesses,5perbackendx3repetitions, allchild/controllerexit0; allcompleteoutputs matchownwarmup andacross5processes
original_reference: everycurrent/originalQuIK fixed/fullhorizon/outcomedocument byte-identical EXP-036
isolation: all25proofsone threadCPU14, zeromeasuredmigrations, zeroSMT15user/nice/systemticks; cgroupremoved andoriginalcpusetrestored
provenance: actualweightedSO andheaderloadedhashes verified; originalQuIK clone/binary andcurrentprivateinstall unchanged
formal_IK_median_ms: current1.246972,originalQuIK0.148230,w0.08=0.149282,w0.04=0.151538,w0.02=0.150207
formal_IK_p95_ms: 6.596753,0.252307,0.256537,0.257960,0.254707
finite_success_retention: current34/60; original36/60_retains27/34;w0.08_37/60_retains30/34;w0.04_40/60_retains30/34;w0.02_40/60_retains29/34
shared_success_median_per_request_ratio: original0.243425646,w0.08=0.240035891,w0.04=0.242929216,w0.02=0.232350633; commonallbackendmask25requests also retained
canonical14step_horizon_median_ms: current138.892683,original101.312427,w0.08=102.504456,w0.04=103.308447,w0.02=103.073463
canonical_p95_ms: current141.9171205,original107.4764385,w0.08=107.4857852,w0.04=109.4356701,w0.02=109.2724792
p18_quality: current14steps; everyQuIKvariant stillincomplete; allweightedvariants failMOVE_ABOVEwaypoint6; failedreturntimes notsuccessfulspeedup
selected_steps: everyrecordedselectedstep position<=2mm/ori<=0.10rad/controlmargin>=0.002rad, independentcanonicalFK
geometry: all4QuIKlibraries2003vectors<1e-12; max4.3298697960381105e-15
firsttarget: original0/14accepted at4.625mm; w0.08=14/14 at0.274384mm;w0.04=14/14 at0.071451mm;w0.02=14/14 at0.018050mm, raworientationpassesall
input_contracts: w0.08 recoverspositive_inf_seed aftersamecanonicalclip; w0.04/w0.02stillreject; foreignNaNexception/failurelabels differ, noAPI-equivalenceclaim
repository_gate: MacfixedPython/colcon/xdist8 benchmark_test 585total553pass32fail0errors0skip;29directCONFIG_SHA mismatch and3secondarydry-runexitfailures, source/confighashes exactoriginal7a62d8e8 frozenbaseline andprivateinstall
invalid_gate: initialsandboxattempt failedbeforecollection duepytest_rerunfailures localhostsocketbind denied; retainedseparately; hostretryactualsuiteexecuted
ordinary_package_gate: NOT_RUN becauseproduction source unchanged; no alltests-passclaim
conclusion: weighting fixesfirsttarget andretainslowQuIK latency, butneithercompletep18 norallcurrent34successes; notqualifiedforproductionreplacement
next_experiment: EXP-043
---
experiment_id: EXP-043
status: VALID
execution: diagnosticchild/controllerexit0, oneCPU14thread,0migrations/SMTticks,cpusetrestored
actual_seed_replay: 15actualwaypoint6failedseeds perweight,allpositionreject; boundsreject8/11/10 forweights0.08/0.04/0.02; noorientationreject
position_min_mm: 2.544801360/2.515257955/2.631136914; failedrawcandidates includinglargeovershoots retained
current_feasible_pose: wristq1.65606 atuppercontrolboundary; position0.979591266mm,orientation0.02928937984rad; thisdoesnotproveexact6Dreachability,butprovescurrenttoleratedposeexists
classification: OBSERVED remainingpositionandsomeboundsfailures; INFERRED unconstrainediteration/stepbehavior important; notconfirmedlimitsaloneexplainallfailures
scope: no furtherweightretunes, no5x5/step/bound/stopping implementation; originalsolverunchanged
final_remote_inventory: 455files17274957bytes0symlinks plusinventory; completecanonicalcopy everySHA/sizeverified
preserved_state: botholdremotecheckouts/submodules,existingclaude tmux,governor unchanged; all7trial/test/formalgroups restored
report: docs/experiments/prepare-horizon-ik-quik-weighted-20261006.md
evidence: quik-position-01/weighted-01/analysis.json,weighted-core.patch,remote-staging,package-gates,inline-review-final.json
retained: alltrial/invalid/formal/diagnostic/build/testevidence
archived: NONE
deleted: NONE
deletion_candidates: taskremote staging,duplicateSOs/sources,packagegate scratch; noauthorization
next_experiment: NONE; nativebounded-step/tolerance/linear-algebra adaptation needsnextscope review
---
checkpoint_id: CP-022
last_valid_experiment: EXP-043
current_commit: 867a33e5ab7dc79033ecfe58c162deef0cd77b9f beforedocsdelivery
confirmed_conclusions: weight-onlyfirstpositiongaterecovered withnearoriginalsolve latency; fullp18 stillfails6thwaypoint andcurrent-successretention incomplete
current_hypothesis: nativeboundedjointupdates/stepcontrol/tasktoleranceexit may recoverremainingcases whilepreservingCPU speed
working_tree_status: taskledger andnewweightedexperimentreportonly; productionnumericalsource untouched
owned_processes: NONE; compile/test/formal/gates/transfer complete
preserved_processes: existingremoteclaude tmux; oldworktrees andCPUstate unchanged
open_risks: fullQuIKadoptionnotqualified;29/30-of34retention, remainingposition/boundfailures, foreignexceptiondifferences; preexisting32perceptionconfigSHAfailures
next_command: verifydocsandretention, authorizedcurrentGiteebranch publication; anysolverstep/boundchange requiresnextapprovedscope
```

## EXP-044 — Frozen twenty-point current / weighted QuIK comparison

```yaml
experiment_id: EXP-044
status: VALID
prior_experiment: EXP-042 / EXP-043
hypothesis: the frozen20point catalog reveals whether weightedQuIK0.08 retains the current solver's supported IKprefixes beyond p18 andcanonical
prediction: perpoint complete14waypoint outcomes identify additional losses or gains; successfulsharedpoints permit valid latency comparison
single_variable: solver backend current native versus frozenweightedQuIK0.08; sharedinputcatalog expandedfrom4to20, numerical parameters andsearch unchanged
lifecycle: FULL_RESTART; six fresh processes perbackend, no ROS or simulator
preconditions:
  - CP-022 restored; weighted firsttarget fixed, p18 failswaypoint6; no productionadoption
  - Mac hostname Terry-Mac-mini.local, inlinegpt-6.1-sol/xhigh; sameclean taskworktree atd766b7bf3 beforeledger edit
  - unchanged source bb9a9c5a andinstalled Linux numericSO hash196ce025; weightedSO74523747, headerdc63f92e
  - authoritative20point YAML sha256c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5; exact originalfrozen7a62d8e8 catalog
  - P18 is sample_14_far_right andmatchespreviousp18; samehomearmq0/gripper0.465038 foreverypoint
  - remote oldcheckouts/submodules andexistingclaude tmuxpreserved; no ROS/simulator processes, noexistingCPUisolation
success_criteria:
  - all20points measuredforbothbackends with18timedobservations each, warmups separate
  - allselectedsteps passindependentcanonicalFK position2mm/orientation0.10rad/controlmargin0.002rad gates
  - deterministic outputs acrosswarmup/repeats/freshprocesses; P01/P18 matchpreviouscanonical/p18 outputdocs
  - sameisolatedCPU14 Pcore, idleSMT15, onecomputationalthread, cpusetfinallyrestored
  - report perpoint median/p95, firstfailedstate/waypoint, completepath counts, sharedsuccess speed andfailedexit times separately
failure_criteria: backend inability toproduce full14step path is a validqualityfailure, retainedwithoutretuning; no fullphysicalgrasp claim
invalid_criteria: provenance drift, inputcoverage mismatch, selectedpose outsidegates, outputdrift, CPUmigration/SMTsibling userspaceactivity, unrestoredcpuset
provenance:
  source_commit: bb9a9c5a045410d62d25bd76380ae5401cdee76c numerical; d766b7bf3dc3f4740216ca2d0f4c06edafc45454 catalog andtasksource
  install_overlay: /data/tmp/so101-prepare-horizon-ik-20261004-01a10735-loop50-01/install-v6
  runtime_executable: /usr/bin/python3 withtask-owned points20-01/run_compare.py throughenter-exec-v2.py
  ros_domain_id: N/A; pureIKcompute, ForbiddenBoundary rejectsROS calls
  gz_partition: N/A; no simulator launched
commands:
  - command: /opt/ros/jazzy/.venv/bin/python evidence/quik-position-01/points20-01/prepare_points20.py
    exit_code: 0
  - command: ssh -T ai-station sudo -n /usr/bin/python3 /data/tmp/so101-prepare-horizon-ik-20261004-01a10735-quik-position-01/points20-01/isolate_and_run.py
    exit_code: 0
observed:
  - OBSERVED remote preflightpassed;32logicalCPUs, PCPU14/core_id28/SMT15, powersaveunchanged; version3.12.3/NumPy1.26.4
  - OBSERVED firstpreflightassumed_numeric.py butactualmoduleiscompiledSO; failedbeforeanybenchmark; correctedfrompriorruntimeprovenance, failedrecordretained
inferred: NONE
conclusion: VALID complete20pointmeasurement; current20/20 andQuIK0.08 18/20, common18medianratio0.735628
evidence:
  - /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/quik-position-01/points20-01
decision: KEEP; productionunchanged
next_experiment: EXP-045 explicitrepositorybenchmarkgate; noalgorithmadjustment
```

## EXP-045 — Required benchmark package gate for the twenty-point report

```yaml
experiment_id: EXP-045
status: VALID
prior_experiment: EXP-042
hypothesis: unchanged package source retains the previously documented32 baselineconfigSHAfailures withnoaddedfailures
prediction: completebenchmark_test collection remains585,553pass32fail0errors/skips; failuresmatchpriorgateIDs
single_variable: freshtest invocation anduniqueMacscratch fornew20pointbenchmarkreport; packagecode unchanged
lifecycle: FULL_RESTART
preconditions:
  - MacfixedROS Python andcolcon executables verified; hostdoctor--base exit0
  - task-private dependency-lock-01/mac-build/install overlay retained; no shareddependency edits
success_criteria: completescope andxdist8 recorded; exactfailureID comparisonwithpriorgate; no alltests-passclaimifknownfailuresremain
failure_criteria: anynewfailure orfailureidentitychange requiresclassification
invalid_criteria: collection/environmentfailure, wrongPython/prefix orworker count, scratch reused
provenance:
  source_commit: bb9a9c5a numerical source unchanged; taskHEAD d766b7bf3 beforeledger edits
  install_overlay: /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/dependency-lock-01/mac-build/install
  runtime_executable: /opt/ros/jazzy/.venv/bin/python andcolcon
  ros_domain_id: N/A; packagebenchmarktests, noROSstack
  gz_partition: N/A; no simulator
commands:
  - command: zsh evidence/quik-position-01/points20-01/run-package-benchmark-gate.zsh
    exit_code: 1; colcontest0/test-result1
observed: 585tests553pass32fail0errors0skip; exactpreviousfailureIDs, xdist8andfixedruntimeprovenance confirmed
inferred: NONE
conclusion: knownbaseline32configSHA failures reproduced; no new failingtestID, packagegate remainsFAIL
evidence:
  - /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/quik-position-01/points20-01/package-benchmark-gate-host-01
decision: KEEP allgateand scratch evidence
next_experiment: NONE
```

## Twenty-point final readback

```yaml
experiment_id: EXP-044
execution_exit: 0; all12child exitcodes0, controllerCOMPLETE_CPU_ISOLATION_RESTORED
observed:
  - OBSERVED current20/20 complete14step IKprefixes; QuIKweighted0.08 18/20
  - OBSERVED P18andP19 QuIKreject15candidates eachatMOVE_ABOVE_OBJECT waypoint6; no complete selectedpath
  - OBSERVED all720timedoutputs matchwarmups; outputdocs exactacross6processes perbackend
  - OBSERVED P01/P18 outputdocs byteequal EXP-042 canonical/p18 foreachbackend
  - OBSERVED allselectedstep recordedcanonical pose/control gatespass; no numericalsource/parameter changes
  - OBSERVED all12proofs CPU14,onecomputationalthread,0measuredmigrations and0SMT15user/nice/systemticks
  - OBSERVED cpuset/governor restored, oldremotecheckouts/submodules andclaude tmuxunchanged; runtimefiles unchanged
  - OBSERVED completecopy355files62227284bytes0symlinks plusinventory, everySHA/size verified
shared_success_points: P01-P17 andP20,18points324timedsamples perbackend
shared_success_pooled_median_ms: current151.9137485,QuIK111.7519645
shared_success_pooled_p95_ms: current168.4321718,QuIK132.67112585
shared_success_median_ratio: 0.7356277203573842; reduction26.43722796426158percent
shared_equalpoint_mean_medians_ms: current151.71390538888886,QuIK111.66427280555553;ratio0.7360187091573844
selected_errors: currentmaxpos1.420810mm/maxori0.086101rad/minmargin0.002rad; QuIK18successesmaxpos1.434305mm/maxori0.085715rad/minmargin0.055014rad; different successsets
classification: OBSERVED QuIK0.08 loses two farcatalogpoints; P19 component-gate rootcause notindependently replayed inthismeasurement
conclusion: userrequested20pointcomparison complete;26.4percent warmIKprefix reductiononcommon18points, supportedcoverage20to18 preventsproductionadoption
decision: KEEP researchresults; productionunchanged, no furtherretuning
---
experiment_id: EXP-045
execution_exit: shell1, colcontest0, colcontest-result1
observed: fixedMacROSPython/colcon/xdist8 585tests553pass32fail0errors0skip; failureIDs exactpreviousgate
classification: VALID completegateexecution, FAIL packagegate;29CONFIG_SHA256_MISMATCH and3secondarydry-runexit failures pre-exist
conclusion: no new failingtestID; noalltests-passclaim, no unrelatedconfigfix
decision: KEEP allgateevidence andscratch
---
checkpoint_id: CP-023
last_valid_experiment: EXP-045
measurement_reference: EXP-044
current_commit: d766b7bf3dc3f4740216ca2d0f4c06edafc45454 beforedocsdelivery; finalSHA inpoints20-01/publish.json
current_hypothesis: QuIK iterationcontrol may recoverP18/P19; outsidecompletedmeasurement scope
working_tree_status: taskledger andnew20pointreportonly; productioncode unchanged
owned_processes: NONE; formalcontroller,packagegate andtransfer complete
preserved_processes: existingremoteclaude tmux; oldcheckouts andCPUstate unchanged
confirmed_conclusions: current20/20,QuIK0.08 18/20; sharedsuccessratio0.735628; allruntime/quality/determinism/source/transferproofs valid
open_risks: P18/P19 fullprefixloss; noROS/MoveIt/controller/physics/livegrasp qualification; existing32benchmarkconfig failures
report: docs/experiments/prepare-horizon-ik-quik-points20-20261006.md
evidence: quik-position-01/points20-01; same registeredMacroot
retained: allpoint/protocol/raw/figure/source/binary/packagegate evidence andpriorruns
archived: NONE
deleted: NONE
deletion_candidates: taskremote staging,duplicates,packagegate scratch; no deletionauthorization
next_command: inline review, authorizedcurrentGiteecommit/push andremoteSHA readback
```

## CP-024 — Compatible backend switch design discovery

```yaml
checkpoint_id: CP-024
last_valid_experiment: EXP-045
measurement_reference: EXP-044
current_commit: ed7998674d44b5ee8e37594ea94b839de5242fe1
current_hypothesis: a factory and optional packaged weightedQuIK adapter can retain both implementations without changing caller contracts or default native outputs
working_tree_status: task ledger only; product code unchanged; clean before discovery
owned_processes: NONE; no tests, runtime or benchmark started in this phase
preserved_processes: all existing host and remote processes/checkouts; no remote commands in this phase
confirmed_conclusions:
  - OBSERVED current native20/20 and weightedQuIK0.08 18/20 from completed EXP-044; baseline report publication hashes verified
  - OBSERVED sixteen source/adapter/protocol/publication files fingerprinted; task worktree is isolated, on the existing codex branch
  - OBSERVED reachability and dynamic execution construct native IK independently; both need the same resolved backend
  - OBSERVED existing PoseIk protocol and QuIK research adapter provide the flow to extend; native exact-type cache guards must retain their semantics
  - OBSERVED QuIK experimental bad-input and rejection errors need compatibility adaptation; no solver retuning is proposed
open_risks: QuIK P18/P19 full-prefix failures remain; optional binary/dependency packaging and same-backend child routing require verification after approval
scope: read-only discovery and audit evidence only; no product implementation
evidence:
  - /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/dual-backend-01/preflight.json
  - /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/dual-backend-01/protocol.json
retained: all prior runs and both new discovery records under the same registered root
archived: NONE
deleted: NONE
deletion_candidates: no new candidates; prior classifications unchanged
next_command: present short reviewed design and obtain explicit confirmation required by AGENTS.md and brainstorming HARD-GATE
```

## EXP-046 — Approved dual backend contract and installed regression

```yaml
experiment_id: EXP-046
status: VALID
prior_experiment: EXP-044
hypothesis: a shared selection factory and packaged QuIK adapter can expose both solvers while preserving native default outputs and independent geometry gates
prediction: contract tests RED before implementation, GREEN afterward; full ordinary installed xdist8 gate has no added failures; QuIK optional build installs both implementations
single_variable: backend selection and integration, no numerical solver retuning
lifecycle: FULL_RESTART
preconditions: approved short design; source freeze ed7998674; single registered evidence root and existing task worktree
success_criteria: compatible APIs and errors, explicit override precedence, same backend in preflight/execution, installed QuIK integration tests execute without skips
failure_criteria: changed native outputs, backend mixing, silent fallback, invalid accepted QuIK poses, new package test failures
invalid_criteria: wrong interpreter, stale module, missing dependency closure or collection error
provenance:
  source_commit: ed7998674d44b5ee8e37594ea94b839de5242fe1 plus scoped approved worktree diff
  install_overlay: task-private dual-backend-01/mac-build/install
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: N/A; headless tests only
  gz_partition: N/A; no simulator
commands:
  - command: fixedROSPython pytest contract, launcher andworker-selection regressions
    exit_code: validRED1; finaldirected0,138passed21skipped
  - command: task-private colcon build with SO101_BUILD_QUIK=1 andEigen3.4.0 onMac andLinux
    exit_code: 0 onbothplatforms; installedmodules verified
  - command: full ordinary colcon test/test-result,tests-complete-final,xdist8
    exit_code: 0/0;3953passed30skipped0failures/errors,3983total,33.49s
  - command: independent SO101_BUILD_QUIK=0 build withabsentEigen;native-only smoke
    exit_code: 0; defaultnativeworks, explicitQuikmoduleunavailable, nofallback
observed:
  - OBSERVED defaultfactory returns exactexistingnative class; explicitselection overridesenvironment withoutmutating it
  - OBSERVED QuIK canonicalFK/tuple/error/concurrent-context regressions executed withcompiledmodule required
  - OBSERVED dynamicpreflight closure andexecution receiveone resolvedbackend; CLI,Maccleanexec andworkerallocator propagate selection
  - OBSERVED vendoredweightedheader SHA256/pinnedupstream/Eigen compileassert/buildflags/license retained; no native solver or iteration/search-policy retuning
  - OBSERVED initialplugin socketdenial didnotrun intendedassertions; initialworkerwrongtemp boundaryinvalid; validRED retained separately
  - OBSERVED first broad directedmissing-module failure fixed withimportlib import; final138passed21skipped
  - OBSERVED firstfullordinary22failures classifiedINVALID_SOURCE_SNAPSHOT_CLOSURE; restored actualindependentGit/submodule refs and44trackedsymlinks, not productcompensation
  - OBSERVED finalcompleteordinary gate preserves original30skipidentities; allQuIK integrationtests executed
inferred: NONE
conclusion: compatible selectable backends installed andverified; defaultnative andoptionalbuild behavior preserved; no livephysics qualification
evidence: dual-backend-01/approval.json,contract-red-valid.*,launcher-red.*,worker-route-red-valid.*,directed.*,mac-build,tests-complete-final,native-only-smoke.json,snapshot-closure-correction.json
decision: KEEP implementation andallvalid/invalid evidence
next_experiment: EXP-047 installed twenty-point isolated-P-core comparison
```

## EXP-047 — Installed selectable backends on the frozen twenty points

```yaml
experiment_id: EXP-047
status: VALID
prior_experiment: EXP-044
hypothesis: installation and explicit backend selection preserve each solver's frozen numerical outcomes and QuIK speed advantage
prediction: native20/20, QuIK18/20 with same P18/P19 failures; shared-success latency retains advantage
single_variable: installed shared-factory backend integration, no solver parameter tuning
lifecycle: FULL_RESTART
preconditions: compiled installed native and QuIK modules verified; exact catalog/URDF/targets/starts; isolatedCPU14 with sibling15 idle and one compute thread
success_criteria: 12 fresh processes x20points x3measurements; six process outputs identical perbackend; frozen native documents exact; QuIK documents exact after only COMPARISON_GATE_REJECTED to DYNAMIC_IK_RESIDUAL_EXCEEDED normalization; canonical gates pass; cpusets restored and old checkouts preserved
failure_criteria: numerical/result drift beyond specified error-code mapping, accepted gate violation, lost additional points, failed QuIK speed advantage
invalid_criteria: migration, sibling activity, incorrect imported artifact, source/input drift or incomplete controller/transfer
provenance:
  source_commit: ed7998674d44b5ee8e37594ea94b839de5242fe1 plus approved scoped diff; source.tar.gz hash retained
  install_overlay: /data/tmp/so101-prepare-horizon-ik-20261004-01a10735-dual-backend-01/install
  runtime_executable: /usr/bin/python3; 3.12.3 andNumPy1.26.4
  ros_domain_id: N/A; pure compute, no ROS graph
  gz_partition: N/A; no simulator
commands:
  - command: frozencontroller withinstalledfactory harness,12freshprocesses,CPU14andSMT15idle
    exit_code: controller0, all12children0; COMPLETE_CPU_ISOLATION_RESTORED
  - command: verifyremote archive/members;analyze_points20.py
    exit_code: 0; 3576regularfiles49symlinks315369742regularbytes; archiveSHA fb602833e09ed82217231ca998542693324357ace604f2d69f43f178d7329705
  - command: untimedactualinstalled auditafterCPUrestoration
    exit_code: 0;2003FKvectors,532selectedsteps,64fixedrequests perbackend
observed:
  - OBSERVED native20/20,QuIK18/20; P18/P19 still15rejects atMOVE_ABOVE_OBJECT waypoint6, no additionalpointloss
  - OBSERVED all20completeoutputdocs exact perbackend versusEXP-044 after onlyapprovedQuIKfailure-code mapping; all6processoutputs identical perbackend
  - OBSERVED all12processes actualinstalled source/nativeSHA/CPU14/onecompute thread; measuredmigration0 andSMT15user/nice/systemtickdelta0
  - OBSERVED samecatalog SHA c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5 andURDF73ab5bdd26451778c094a837817c65748b1e8bacd48672e313c941d8ca85f0b2
  - OBSERVED common18points324samples perbackend pooledmedian147.2256495ms/native,103.0917045ms/QuIK;ratio0.7002292389275552,reduction29.977076percent
  - OBSERVED pooledp95/native156.05632605ms,QuIK112.7675843ms; failedexits excludedfromspeedup
  - OBSERVED installedQuIKFK maxmatrixdelta4.3298697960381105e-15<1e-12; canonicalselectedpose/controlmetricrecalculation exactlymatches all532steps
  - OBSERVED installed64request return/reject andq exactversusEXP-042 forbothbackends; acceptedgates exact; allnativeerrorclass/messages exact
  - OBSERVED oldcheckouts/submodules/tmux/governors preserved; allisolationrestored; specialfiles notdereferenced duringcopy
  - OBSERVED inheritedprotocol source-label metadata corrected onlyinanalysis-provenance.json; actualsourcebaseed7998674 + archivee00d51115bf4d2b0c675c7f5b89ad3f08796f8e0808448767c6e9588f6650492, installedfiles individuallyverified
  - OBSERVED setupreference reuseisasymmetric andoutsidetimedboundary; nocross-backendcold-startclaim
inferred: NONE
conclusion: installedintegration preserves perbackend numericalbehavior andweightedQuIK warm-speedadvantage; P18/P19 limitation remains; onlycomputeprefix qualification
evidence: dual-backend-01/points20-01/{protocol.json,analysis-provenance.json,analysis.json,installed-audit-verified.json,copy-verification.json,remote-staging}
decision: KEEP selectableQuIK alongside defaultnative; no solverretuning orsilentfallback
next_experiment: NONE
```


## EXP-048 — Separate benchmark package gate after backend integration

```yaml
experiment_id: EXP-048
status: VALID
prior_experiment: EXP-045
hypothesis: the backend integration does notaddfailures to the independently failing perception benchmark package gate
prediction: full585test scope has553pass32knownfailures withsameIDs
single_variable: approvedbackend integration; benchmark config andsource unchanged
lifecycle: FULL_RESTART
preconditions: verifiedtask-privateMac overlay/fixedPython; no stacklaunched; uniqueNVMe scratch
success_criteria: completebenchmark_test scope/xdist8/JUnit; compareallfailureIDs againstEXP-045
failure_criteria: newfailureidentity or countchange requiresclassification
invalid_criteria: wrongPython/prefix/worker count orcollectionfailure
provenance:
  source_commit: ed7998674 plusapprovedintegration; finalSHA inpublish.json
  install_overlay: dual-backend-01/mac-build/install
  runtime_executable: /opt/ros/jazzy/.venv/bin/python andcolcon
  ros_domain_id: N/A; noROSstack
  gz_partition: N/A; nosimulator
commands:
  - command: run-package-benchmark-gate.zsh; complete benchmark_test -n8
    exit_code: shell1,colcontest0,test-result1
observed: 585tests553pass32fail0error/skip; exactEXP-045failureIDs,29CONFIG_SHA256_MISMATCH and3secondarydry-runfailures
inferred: NONE
conclusion: requiredexecution valid; packagebenchmarkgate remainsFAIL withnoaddedfailureidentity; noalltests-passclaim
scoping: thisexplicitgate isseparate fromthepassed3983ordinary testcollection
scratch: /opt/data/tmp/ik.bench.uEReFO; retained/deletioncandidate, no deletionauthorization
evidence: dual-backend-01/package-benchmark-gate-host-01/{preflight.json,results,classification.json,gate.log,test-result.log,scratch.txt}
decision: KEEP alltest/scratch evidence; no unrelatedconfigfix
next_experiment: NONE
```

## CP-025 — Selectable backends verified and ready for publication

```yaml
checkpoint_id: CP-025
last_valid_experiment: EXP-048
measurement_reference: EXP-047
current_commit: ed7998674d44b5ee8e37594ea94b839de5242fe1 beforedelivery; publishedSHA in dual-backend-01/publish.json
current_hypothesis: NONE withinapprovedintegration scope
working_tree_status: scopedapprovedproduct/build/pins/contracts/guides/report/ledger changes; native numericalsource unchanged
owned_processes: NONE; allformalcontrollers/builds/tests/audits/transfers finished
preserved_processes: priorMac tmux andremoteclaude tmux preserved; noROS/simulatorstack launched
confirmed_conclusions:
  - OBSERVED native/defaultandweightedQuIK0.08 retainedbehindsharedposeIK API andCLI/environment switches
  - OBSERVED installedtwenty-point numericaloutputs unchangedperbackend; common18medianratio0.700229,reduction29.98percent
  - OBSERVED bothplatform builds valid; finalordinaryxdist8 gate3953pass30skip0fail/errors; native-onlybuild validwithoutEigen
  - OBSERVED explicitbenchmarkgate585/553/32knownfailures, exactpreviousIDs; separateexistinglimitation
  - OBSERVED pinnedQuIKsource/Eigen/buildflags/license andactualartifact provenance recorded
open_risks: QuIK P18/P19 fullprefixloss; no physicalgrasp/ROS/MoveIt/controllerlivequalification; existing32benchmarkconfiguration failures
report: docs/experiments/prepare-horizon-ik-dual-backend-20261007.md
guide: docs/guides/so101-ik-backend-selection.md
evidence: dual-backend-01 under theunchangedregisteredMac root
retained: allcurrent andprior valid/invalidruns,privatebuilds,source/nativeartifacts,protocols/raw/JUnit/audits
archived: NONE
deleted: NONE
deletion_candidates: task-privateMacscratch,remoteexecutionstaging,duplicatebuild/source/transferarchives; see dual-backend-01/final-retention.json; noauthorizationtodelete
next_command: finalinline review, authorizedcurrentGiteecommit/push, exactremoteSHA readback
```


## EXP-049 — Formal QuIK environment setup and fresh dependency validation

```yaml
experiment_id: EXP-049
status: VALID
prior_experiment: EXP-046
hypothesis: a reusable setup wrapper aroundtheexisting pinnedbuild can bootstrapQuIKdependencies andverifyboth installedbackends in anownedprefix withoutmutating sharedROS/source environments
prediction: initiallymissingformalentry contractfailsRED; implementationpreparesPython/Eigen3.4.0/runtimebuildpins, compilesbothkernels, verifiesindependentpose/controlgates andpassesrepeatsetup
single_variable: formaldependency provisioning/install orchestration; nativeandweightedQuIK numericalsources andparameters unchanged
lifecycle: FULL_RESTART
preconditions:
  - baselinec62695cc6 cleanisolatedtaskworktree andexistinguniqueMac evidence rootverified
  - approvedplatformmatrix Ubuntu24.04x86_64 andAppleSiliconmacOSarm64
  - explicitnewsetup-design confirmation ok recordedbeforeimplementation inapproval.json
success_criteria:
  - dedicated bareUbuntu24.04 container hasno Python/compiler/Eigen beforeinvocation; setup installsdependencies/builds/verifies bothbackends
  - Macfreshownedprefix andcaches; privateEigen andPythonpackages automaticallyprepared; declaredexistingAppleXcode foundation, successfulfirst/repeat verification
  - wrongdownloadSHA/versions/missingmodule/unmanagedprefix fail explicitly
  - installedsource/artifact/versionmanifest andactivation/build environment retained
  - samecomplete ordinarytestscope/xdistmin8/fixedMacROSPython/privateoverlay/JUnit, noaddedfailure
failure_criteria: hiddenexisting dependencyreuse, compile/import/provenance mismatch, illegal acceptedpose, newpackagefailure orsharedcheckout/runtime mutations
invalid_criteria: wronginterpreter/prefix/platform, staleenvironment, missingcollection/dependencyclosure, incompleteDocker/transferproofs
provenance:
  source_commit: c62695cc663dd3e2bf9ee381616d27345d343b8e
  install_overlay: proposedtask-privatequik-setup-01 children; no shareddeployment
  runtime_executable: proposedmanagedcompatibleCPython forstandalonebootstrap; fixed/opt/ros/jazzy/.venv/bin/python forMacpackagegate
  ros_domain_id: N/A; headlesssetup/CPUsmoke, no stack
  gz_partition: N/A; no simulator
commands: officialsetupfirst/repeat andexplicitPython modes; privatecolconbuild; fixedMacROSPython completeordinarypytest-n8; finalUbuntucontroller; actualfourfaultinjections; symlink-safearchivecontentverification
observed:
  - OBSERVED trackedsetup.py requires existingPython/buildtools/Eigen; no formalQuIKsetup entry
  - OBSERVED MacAppleclang21/Xcode andfixedCPython3.11.15/NumPy2.4.6/setuptools79.0.1 available, notfreshmachineproof
  - OBSERVED ai-station Docker29.1.3 accessible withnorunningcontainers; existingcheckouts/submodules andclaude tmux preserved
  - OBSERVED finalMacdelivery empty-prefix/cache first/repeat andexplicitfixedROS Python mode passed; privateEigen3.4.0 andpinnedPythondependencies prepared automatically
  - OBSERVED finalofficialUbuntu24.04.5 barecontainer03 lackedPython/gcc/g++/curl/Eigen; setupaptprovisionedtools, downloadedmanagedCPython3.12.13 andpins, builtbothkernels andpassedfirst/repeat solves
  - OBSERVED bothbackends solve2nonzerojoint-generatedtargets fromzeroseed throughcanonical2mm/0.10rad/0.002radmargin gates; installedpaths andartifactSHA recorded
  - OBSERVED final13contractregressions pass; initial11missingentry/helper failures plusnestedprefix andtransportfailure RED evidence retained
  - OBSERVED actualUVwrongSHA, QuIKbinarymodification, missingkernel anddependencyversionmismatch allfail explicitly; originalbytes restored, successfulrepeatverified
  - OBSERVED finalcompleteordinarygate3996tests/3966pass/30skip/0fail/errors,xdist8 on10logicalCPUs,32.88s; fixedROS Python/privateoverlay/provenance/freshNVMe scratch/JUnit/eightworkerproofs recorded
  - OBSERVED finalarchiveSHA andall21542regularfile hashes/sizes plus2118symlinktargets agree;1201211950uncompressedbytes; noFIFOs/sockets dereferenced
  - OBSERVED remoteoldcheckouts/submodules cleanandunchanged, oldMacservices/tmux andremoteclaude tmux preserved; ownedcontainers01/02/03 stoppedandretained
inferred: freshUbuntuauto-dependency readiness established; Macempty-prefix cannotproveabsentAppletoolchaininstallation; existingOSinstaller confirmation stillrequired whenmissing
invalid_attempts: initialMacuvarchive/version/SDKassumptions corrected; pre-deliveryUbuntuGitHubtransport56/137 retained; initialarchive-rootmtime warning andMaccase/AppleDouble extraction mismatch retained; finalclean-exitarchive verifieddirectly withcase-sensitivearchivepaths
conclusion: formalisolatedsetup accepted; numericalsolver sources/pins unchanged; no newlatency/fullphysicalclaim; no benchmark_test scope triggered
evidence: quik-setup-01/{approval.json,protocol.json,mac-delivery,mac-delivery-explicit,mac-ros-delivery,tests-delivery,ubuntu-verified-metadata,ubuntu-evidence-verified.tar.gz,transfer-verification-final.json,fault-injection-delivery,acceptance.json,implementation-inline-review-final.json,retention.json}
decision: keepallvalid/invalid evidence, publishapprovedsetup tocurrentGiteetaskbranch
next_experiment: NONE
```

## CP-026 — Formal setup baseline and reviewable protocol ready

```yaml
checkpoint_id: CP-026
last_valid_experiment: EXP-048
current_hypothesis: formalsetup canreplace task-specificprepareddependencies withpinned automaticprovisioning in anownedprefix
working_tree_status: taskledger only; productcode unchanged; cleanbeforebaseline
owned_processes: NONE; allreadonlyprobes finished
preserved_processes: Macso101-ik-cpu-20261004 tmux, remoteclaude tmux, allmatchedexistingPID/checkouts/submodules preserved; nostack/container/dependency started orchanged
confirmed_conclusions: no trackedQuIKsetup; bothplatformbuild foundationsknown; UbuntuDockerfreshvalidationpossible; Macnew-empty-prefixvalidationpossible
open_risks: platformmatrix optionalanswerpending; Appletoolchaininstallation requiresOSauthority/confirmation; priorQuIKP18/P19 and32perceptionbenchmarkfailurelimitations unchanged
next_command: obtainexplicitconfirmationofnewreviewedsetup design; thencontractRED beforeimplementation
retained: allpriorruns plusquik-setup-01 baseline/protocol/selfreview underunchangedregisteredMacroot
archived: NONE
deleted: NONE
deletion_candidates: no newexecution artifacts; priorclassifications unchanged
```

## CP-027 — Formal dependency setup accepted

```yaml
checkpoint_id: CP-027
last_valid_experiment: EXP-049
current_commit: c62695cc663dd3e2bf9ee381616d27345d343b8e beforepublication; exactdeliverySHA inquik-setup-01/publish.json
working_tree_status: approvedsetupwrapper/bootstraplock/helper/regressions/Englishguide/ledger only; numericalruntime sources unchanged
confirmed_conclusions:
  - officialentry scripts/setup-so101-quik.sh automaticallypreparesownedPython/Eigen/build/runtime dependencies andbothkernels
  - Ubuntu24.04 barecontainerfirst/repeat andMacempty-prefixfirst/repeat/explicitROS Python passed
  - sharedROS/hostglobaldependencies andoldcheckouts preserved; installedCPUartifact/gates recorded
  - all13regressions andfouractualintegrityfaultpaths valid; finalordinaryxdist8gate3966pass30skip0failure/errors
  - losslessLinuxarchivepayload verifiedbyallpaths/SHA/sizes/symlinktargets; Maccase-insensitivepartialextraction isINVALID evidence only
owned_processes: NONE; controllers/builds/tests/transfers completed; threeownedcontainers stopped
open_risks: MacAppletoolchainOSinstaller completion notexercised; priorQuIKP18/P19 limitations remain; no ROS/physicslivequalification ornewbenchmarkclaim
retained: allpriorruns plusquik-setup-01 valid/invalidruns/logs/manifests/source/builds/JUnit/rawarchives/faultbackups
archived: NONE
deleted: NONE
deletion_candidates: privateinstall/cache/source/build/testscratch, stoppedownedcontainers01/02/03, remoteexecutionstaging/transferarchives, invalidMacextraction/duplicatearchives; retention.json; noauthorizationtodelete
next_command: finalinline review thenauthorizedcommit/push currentGiteebranch andexactremoteSHA/cleanstatus readback
```

## EXP-050 — QuIK ROS2 package baseline and design protocol

```yaml
experiment_id: EXP-050
status: VALID
prior_experiment: EXP-049
hypothesis: the published frozen installed backends can provide same-source reproducible per-backend numerical references before changing package ownership
prediction: all20 complete horizon documents and64 fixed solve outcomes repeat exactly on Mac; installed numerical sources and parameters match HEAD; independent package is currently absent
single_variable: NONE; read-only baseline, audit harness only
lifecycle: FULL_RESTART
preconditions: clean isolated task worktree HEAD38e333507, retained officialsetup private overlay, fixed ROS Python; existing processes untouched
success_criteria: exact installed/source provenance and repeated complete outputs for both backends; reviewable dependency/build/setup/numerical/latency protocol before asking design approval
failure_criteria: output repeat drift or wrong installed source prevents using baseline
invalid_criteria: stale overlay, missing runtime closure, imports from wrong prefix, missing inputs, absent source-hash proof
provenance:
  source_commit: 38e333507127a8073061811a7b08a02e41cbe7d1
  install_overlay: /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/quik-setup-01/mac-ros-delivery/install
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: N/A; headless CPU baseline, no node creation
  gz_partition: N/A; no simulator launch
commands: git/source/installed hash checks0; capture_baseline.py0 (6.135s); host/tmux/proc probes0; ROS node-list0 andcolcon list0; remote readonly SSH0
observed: OBSERVED isolatedclean HEAD38e333507; actual installed numeric source exact versus HEAD andbinaryhashes matchEXP049 gate; all20completeoutputs and64requests repeatedexactperbackend; native20/20,QuIK18/20 P18/P19 unchanged;2003QuIKFKmatrices frozen; oldcheckouts/tmux/CPUstate preserved; colcon8packages/noindependentQuIK
inferred: package extraction should keep the existing in-process call and SO101-specific URDF/canonical gates in demo to avoid circular dependency
conclusion: valid perbackend installed baseline and reviewed package/build/setup/numerical/latency proposal ready; no product implementation started
evidence: quik-ros-package-01/{baseline-source.json,baseline-verification.json,baseline-mac,protocol.json,design-and-plan.md,inline-design-review.json,host-before.json,remote-before.json,ros-graph-package-baseline.json,retention.json}
decision: KEEP baseline andreviewableplan; awaiting explicit design/plan confirmation before product code
next_experiment: EXP-051 after approval; extraction implementation and acceptance
```

## CP-028 — Independent QuIK ROS2 package baseline and reviewable plan ready

```yaml
checkpoint_id: CP-028
last_valid_experiment: EXP-050
current_commit: 38e333507127a8073061811a7b08a02e41cbe7d1
current_hypothesis: packageownership andbuildboundary canbeextractedwithoutchanging perbackendnumericalbehavior orinprocess latency
working_tree_status: only docs/experiments/prepare-horizon-ik-20261004-01a10735-experiment-ledger.md modified; no productcode orpackage scaffold
owned_processes: NONE; all probes andbaseline capture finished
preserved_processes: existingMac tmuxso101-ik-cpu-20261004 andPIDs1541/1542/27535/85808; remoteclaude tmux; oldcheckouts/submodules andcpusets/governor unchanged
confirmed_conclusions:
  - currentMac installedsource/binary matchespublished baseline;64requests and20completeoutputs repeat exactly perbackend
  - native20/20 andweightedQuIK18/20 P18/P19 unchanged;2003FKvectors/matrices frozen
  - recommendedonepackage so101_quik withament_cmake CPPtarget plusstdlib Pythonloader; demo retainsURDF/canonical gates andnative default
  - reviewedprotocol covers independentconsumers, freshcolcondependencyclosure, officialsetup, fullordinaryxdist/CTest, isolatedPcore14/idleSMT15 beforeafterlatency
disproven_routes: no newalgorithmexperiment; priorconclusions unchanged
open_risks: completeplan approval pending; optionalCPP/Python preference pending (recommendedboth assumed); newCMakepin andpackagepaths require actualtwo-platform buildverification; priorQuIKP18/P19 limitation remains
retained: allpriorregisteredroot contents andquik-ros-package-01 baseline/protocol/plan/host/readback/audit evidence
archived: NONE
deleted: NONE
deletion_candidates: no newbuild/testscratch; priorclassifications unchanged
next_command: obtainexplicitconfirmationof quik-ros-package-01/design-and-plan.md, then recordapproval andcontractRED before any package implementation
```

## EXP-051 — Independent QuIK ROS2 package implementation

```yaml
experiment_id: EXP-051
status: RUNNING
prior_experiment: EXP-050
hypothesis: extracting the frozen QuIK kernel into one independent ament_cmake package preserves all perbackend outputs and the inprocess hotloop while making demo a declared consumer
prediction: newpackage independent C++/Python consumers pass, demo build order/importprefix is correct, exact64requests/20completehorizons/2003FK and <=1.05median/p95 ratios pass
single_variable: package ownership/build/install anddependency/loading boundary; solver sources/parameters androbot model frozen
lifecycle: FULL_RESTART
preconditions: EXP050 installedbaseline valid; userexplicitok confirms entiredesign/plan; owned worktree/prefixes; original sole evidence root
success_criteria: independentpackage consumers, two-platformprivateROSbuilds/officialfreshsetup, fullordinaryxdist8/CTest, exact sameplatformoutputs andisolatedCPU14/idleSMT15 latency, finalinline review andauthorizedGiteepublication
failure_criteria: numericaldrift, newfailedpoints, adapterfallback, timingratio>1.05 in validbatch, source/license/pin loss orsharedstate mutation
invalid_criteria: wrongprefix/interpreter/flags, missingdependencyclosure, incompletecollection orCPUisolation/transfer pollution
provenance:
  source_commit: 38e333507127a8073061811a7b08a02e41cbe7d1 plusapprovedscoped changes
  install_overlay: taskowned quik-ros-package-01 children; exactprefixes inbuild/test manifests
  runtime_executable: Mac /opt/ros/jazzy/.venv/bin/python; Linux exactfrozen ROS interpreter forcomparison; managedPythononly standalonefreshsetup
  ros_domain_id: N/A; headlesslibrary/CPU gates, nostack
  gz_partition: N/A; nosimulator
commands: pending RED thenimplementation/build/ordinarypytest/CTest/setup/comparison
observed: OBSERVED explicituserok recordedbefore productcode
inferred: no algorithmchange required; standalonewheel andROS useone CMakecoretarget
conclusion: PENDING
evidence: quik-ros-package-01/{approval.json,protocol.json,design-and-plan.md,baseline-verification.json}
decision: implement approvedplan withinline selfreview
next_experiment: NONE unless invalidrun requires a distinctreplacement ID
```

## CP-029 — Independent package and Mac installed numerical comparison pass

```yaml
checkpoint_id: CP-029
last_valid_experiment: EXP-050
active_experiment: EXP-051 RUNNING
current_commit: f6ba3231c (approved design documentation commit)
working_tree_status: scoped package extraction/setup/tests in progress; old demo vendor/C++ wrapper migrated
owned_processes: Mac full demo xdist8 and newpackage CTest; exact sessions in tool/evidence records
confirmed_conclusions:
  - RED valid7 actualassertionfailures; earlier socket-denied sandbox attempt INVALID and retained
  - eightvendorSHA andnumericalCABIbody exact; independent5Python tests PASS; installedC++ nonzero solve PASS
  - newMac ROS two-packagecolconbuild PASS independencyorder; actualnewlibrary belongsso101_quik andglobal/Pythoncopies byteidentical
  - Mac64requests perbackend,20completehorizons perbackend and2003QuIKFK exact againstEXP050;43docs byteidentical
  - officialfreshMac managedPythonsetup PASS first/repeat; twowheels anddependencycheck PASS
open_risks: fullordinarypytest/CTest pending; freshbareUbuntusetup, LinuxprivateROSnumericalcapture andisolatedPcorelatency pending; docs/finalsourceclosure/integritycases/review/publication pending
retained: allpriorruns plusquik-ros-package-01 independentbuild/cppconsumer/red/source/ros/afterMac/macsetup evidence
archived: NONE
deleted: NONE
deletion_candidates: privatebuild/setupcache/source/wheels/testscratch; no deletion authorized
next_command: readfullMacgate/CTest exits; complete docs/setup integrity; stage new-owned bareUbuntu andfreshLinuxbeforeafter overlays
```

## EXP-052 — Linux package gate with inherited SSH cwd

```yaml
experiment_id: EXP-052
status: INVALID
prior_experiment: EXP-051
single_variable: NONE; gate runner environment
observed: OBSERVED beforeafter ROS builds0 anduntimed captures/C++consumer complete; colcon test inheritedhomecwd, ignoredunknown so101_quik,0packages/0tests; test-result2 absentresultdirectory
conclusion: invaliddiscoverycannotcount as packagepass; no productfailure inferred
retained: quik-ros-package-01/linux-package-gate-invalid-01.json andalloriginalLinux logs/scratch
next_experiment: EXP-053 explicit sourcecwd/basepaths andfreshscratch, no productchanges
```

## EXP-053 — Corrected Linux package discovery and fixed-runtime comparison

```yaml
experiment_id: EXP-053
status: RUNNING
prior_experiment: EXP-052
hypothesis: explicit tasksourcecwd andso101_quik basepath resolve CTest discovery withoutproductchanges
single_variable: runnerdiscovery boundary
success_criteria: actualnewpackage CTest2CPP/5Python,xdist8/interpreter/scratch/resultproof; completeLinux43doc exactcomparison; thenapproved24processisolatedPcorebenchmark
invalid_criteria: wrongsource/runtime/scope, incompletecollection, wrongCPU/isolation, incompleteevidence
retention: allpriorattempts retained; no deletion
```

## CP-030 — Two-platform package/numerical/setup gates and isolated latency pass

```yaml
checkpoint_id: CP-030
active_experiment: EXP-051/053 pendingfinalartifacttransport andpublication
current_commit: f6ba3231c documentationbaseline; scopedproductchanges uncommitted
confirmed_conclusions:
  - finalMac fullordinarytest scope3997:3967passed30skipped,xdist8,33.12s; originalgate35.14s retained
  - newpackage registeredCTest2CPP/5PythonPASS onMac andLinux; Pythonxdist8each,workerprefix/temp proofs
  - sameplatform Mac/Linux43complete numericaldocs exact:64requests eachbackend,20horizons eachbackend,2003QuIKFK; native20/20 QuIK18/20 P18P19 unchanged
  - formalcoldMac first/repeat finalhelperPASS; freshbareUbuntu24.04 first/repeatPASS; actualSHA/library/versionrejections andrestoredreadbackPASS
  - isolatedphysicalPcoreCPU14/idleSMT15,24freshprocesses,3AB/3BA perbackend; alloutputs exact,all24singlethread/nohotmigrations/SMTactive0
  - native360successsamples/version median145.681051->145.3695415ms ratio0.997861702,p95374.9876929->375.58246ms ratio1.001586098
  - QuIK324common-successsamples/version median102.2960195->102.756137ms ratio1.004497902,p95112.2862485->112.7651346ms ratio1.004264869; <=1.05contractPASS
  - Linuxcpuset exactrestored,CPU14governor powersave,oldcheckouts/submodules/tmux unchanged,ownedbarecontainer stoppedretained
  - originalMac PIDs1541/1542/27535/85808 preserved; numerical/model/gate/vendor sourcesfrozen; installedloaderexact andCPP/Pythonlibcopies identical
  - sourcehelperfinal590inputs exactcurrentworktree,8343installedartifacts inclcompleteCMake/dependencytrees
invalid_attempts: Linuxcolcon cwd discoveryEXP052 retainedandcorrectedEXP053; firstarchive tar directorymtimefailure retainedinsidecanonicalarchive
retained: allpriorandcurrent evidence; verifiedLinuxcanonicalarchive40201entries39024files1177symlinks1913183493rawbytes, transporttoMac pending
archived: NONE
deleted: NONE
deletion_candidates: ownedsetup/source/build/wheels/cache/scratch/container andremoteexecutionstaging/archives; no authorizationtodelete
next_command: verifyLinuxarchiveMacstreamSHA/payload, finalretention/acceptance/ledger,commitpush Gitee currentbranch andreadback
```
