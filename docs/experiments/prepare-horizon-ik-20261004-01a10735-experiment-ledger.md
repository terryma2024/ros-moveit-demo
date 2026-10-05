# prepare_horizon CPU IK experiment ledger

```yaml
task_id: prepare-horizon-ik-20261004-01a10735
goal: fixed-fixture prepare_horizon compute median latency <= 0.30 frozen baseline
success_contract: unchanged search, scoring, gates and receipts; equivalence and package gates
worktree: /Users/matianyi/.codex/worktrees/0a4f/moveit-demo
branch: codex/prepare-horizon-ik-20261004-01a10735
base_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0
benchmark_commit: 7a62d8e88f4b04fa5f20359649013a16bae909b0
delivery_commit: see evidence review/publish.json
evidence_root: /opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735
host: Terry-Mac-mini.local
model: gpt-6.1-sol
reasoning_effort: xhigh
confirmed_conclusions:
  - bootstrap prompt and bundle SHA256 verified; dispatch receipt exact
  - native CLI worktree was isolated and clean at detached f0677823 before branch switch
  - task branch starts at imported frozen source baseline; old checkouts untouched
  - host-access doctor --base exit 0; sandbox denial was not host absence
disproven_routes: []
open_hypotheses: []
final_confirmed_conclusions:
  - aggregate ratio 0.2727275234730253 <= 0.30
  - exact fixture outputs and complete xdist8 ordinary package gate passed
  - scoped product/test diff unchanged from formal measurement
latest_checkpoint: CP-010
next_experiment: NONE
retained: all evidence in registered root
archived: NONE
deletion_candidates: registered scratch listed in review/final-retention.json; none deleted
```

## Scope and authorization

Mac/source baseline only; no equivalence claim about ai-station dirty sources.
CPU-only, inline self review, no implementation agent or dst. No ai-station access,
stack launch, push, merge, evidence deletion, or shared dependency changes authorized.
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
