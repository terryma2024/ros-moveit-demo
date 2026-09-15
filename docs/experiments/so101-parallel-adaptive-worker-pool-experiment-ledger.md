# SO-101 Parallel Adaptive Worker Pool Experiment Ledger

```yaml
task_id: so101-adaptive-worker-pool
goal: Re-run the frozen fixed-W10/C2 SO-101 twenty-point execute pool once for reproducibility, then publish the maintained W1-W10 source data and deterministic SVG scaling chart in the parallel Worker source guide.
success_contract: Preserve EXP-047, perform exactly one new valid fixed-W10 runtime attempt under the unchanged v4 production contract with complete failure-or-success evidence and exact cleanup, then derive a validated versioned dataset, deterministic checked SVG, natural Chinese guide update, and scoped local commits without changing the user dirty test.
worktree: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool
branch: codex/parallel-adaptive-worker-pool
base_commit: 4c777fa722586be92a0b357b861ab4ce460a06ab
current_commit: 0c52cc42bf5b37610dfea49ac8d2b54f2e8ad0ae
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01
confirmed_conclusions:
  - origin/main equals the reviewed baseline 4c777fa722586be92a0b357b861ab4ce460a06ab; startup preflight CP-001.
  - the legacy worktree remains at 2d13ae65490cf1eccfd57fa683e4b13b41784402 with its untracked admission test preserved; startup preflight CP-001.
  - no SO-101, MoveIt, MuJoCo, Gazebo, or RViz runtime process and no ROS_DOMAIN_ID 0 node was observed before implementation; startup preflight CP-001.
  - Task 1 adaptive contracts passed an auditable missing-module RED replay and a 61-test GREEN gate including frozen v1 contracts; commit eae9742d60d3213137dabe7d3716e0b3082ff127.
  - Task 2 explicit adaptive CLI passed 111 adaptive/CLI tests and 100 frozen v1 contract/journal/crash-recovery tests; commit 79538ee04b850ab0cebc39c46dddbff50b63f04c.
  - Task 3 adaptive point affinity and stealing passed 136 scheduler tests plus 145 coordinator/fault-injection regressions; commit 59f4cc96c7299f998d1c106cc75f77b29c729eef.
  - Task 4 observational W8 resources, persistent claims, authenticated READY barrier, and pre-release linearization passed a 370-test combined gate and 85-test v1 CLI rerun; commit 6b8101099203fa0017dc1e5645140d4704879465.
  - Task 5 fsync-backed cross-generation fallback runner passed 10 state-machine, conflict, path, and replay tests; commit 3ba9abd1561bf028fb2512ef68d542b241485b70.
  - Task 6 production Workers and the adaptive production factory passed 265 split tests; commit b983d521f.
  - Task 7 per-model adaptive perception queues passed 367 Broker, runtime, IPC, and spec tests; commit a50aae938.
  - Task 8 first-failure convergence, verified persistent-claim release, exact external cleanup, adaptive aggregate output, and wrapper supervision passed the focused and specified regression gates; evidence is in task-08/failure-and-cleanup.md.
  - Task 10 exact startup and active-attempt fault injections each produced one W8-to-W6 transition, preserved task-external sentinels, completed every assigned point, and reported complete cleanup; accepted runs su09 and mr08.
  - Task 11 uninjected adaptive execute regression completed all 20 points as PASSED at levels W8 and W6, with complete cleanup and fresh terminal visual evidence; accepted run e2001.
  - EXP-005 measured valid standalone YOLO-Seg levels 1, 2, 4, 6, and 8; the highest admitted stable level is 8, throughput saturation is 4, and conservative initial production Broker parallelism is 2.
  - EXP-006 completed all 20 execute points at fixed W8 with no fallback and complete timing/cleanup evidence; the 1.507 s median composite perception chain was driven by a 1.432 s median serialized Broker round trip, while every configured stage budget remained satisfied.
  - EXP-006 supplemental causal audit confirmed that sample_13_far_center and sample_15_far_center `TRUNCATED_FRAME` errors came from the 5 s AuthenticatedUnixServer cycle deadline starting before accept and exhausting the handler/reply remainder; identical idempotent retries recovered both original QUALIFIED results.
  - EXP-006 used a 240 s consumer get_one timeout, so none of its 20 points timed out under current configuration; against the separate 5 s target SLO, 5/20 exceeded from get_one start to POSE_ACCEPTED and 4/20 exceeded from consumer READY to accepted.
  - The formal frozen C2 comparison qualifies W1, W2, W4, W6, and W8 with one complete 20/20 first-attempt sample each. W8 is fastest at 4.55 points/minute and W4 is the 96.5-percent-efficiency knee.
  - EXP-048 is the second admitted W10 runtime failure and contributes no performance point. It stopped after POOL_STARTING and before POOL_RUNNING with 0/20 points; the exact cleanup readback passed and no third W10 run was launched.
  - Task 15 preflight at CP-010 confirmed the required linked worktree and HEAD, preserved the three existing dirty paths, and found no conflicting process, ROS node on Domains 0/215-222, Docker container, GPU compute app, or tmux session.
  - Task 15 implementation through CP-011 is committed at 3677e9d97f1367f861496817cee5edeb4349871f; EXP-007R2 qualified eight authenticated Broker clients with C2 YOLO execution, queue depth five, eight distinct logical inferences, zero replay, and zero transport truncation.
  - EXP-008 live-01 and live-02 are INVALID preflight attempts, and live-03 is INVALID because systemd-oomd killed its 16.2 GiB tmux scope before any point lease; CP-012.
  - Task 10 independent review is accepted after correcting the audit record: the timeout RED/GREEN stdout streams are unavailable, while the adjacent 40-test log remains retained; CP-019.
  - Task 11 final ordinary package collection at source 167c74a941782e37ed1369ee10c42ac6b77088a9 collected 3035 tests: 3033 passed, 1 skipped, and the sole failure is the preserved task-external dirty test test_transient_unclassified_proc_read_error_is_retried; CP-019.
  - EXP-009 confirmed and fixed the post-review dynamic plan-only READY-boundary regression with an auditable 1-failure RED, 1-pass GREEN, and 40-pass adjacent gate; source/test commit c8d44b862a90e4aa20e9945cf223caeff12ce4d5; CP-020.
  - Retained EXP-008R7-W1 stage traces localize its 240 s expiry before dynamic planning: the parent declared subscription READY before the child froze its ROS READY boundary, then published one immutable source stamp that the consumer rejected thirty times as pre-READY.
  - CP-039 completed fixed W6 and W8 correctness qualification at f349cd8d1942c31a276b3237c1676eee9f8cce39; each passed 20/20 on first attempts with exact cleanup, while the separate W8 five-second READY-to-POSE SLO remained false.
  - Commit b5cd54bd3f28cf26c2dec01989e277f9bcba7953 extends every identified optional adaptive-worker ceiling to W16 while preserving default W8, fallback (6, 4, 2, 1), C2, timeout policy, and two-digit identities; focused, adjacent, and all 3050 ordinary package tests passed.
  - The one authorized EXP-031 launch was invalid before a batch started because the registered evidence root was mode 0775 rather than the required exact 0700. No runtime root, Worker, Broker container, or point attempt was created; exact readback is clean and no retry was made.
  - EXP-033 was the first genuine W10 runtime sample. All ten Workers reached READY and began one point each, but every Broker request_model RPC reached HANDLER_DEADLINE_EXCEEDED before perception returned. The run is FAILED, W10 is not qualified, all ten attempts prove physical action absent, and exact cleanup passed.
disproven_routes:
  - the superseded heavy AdmissionAuthority/profile/Ed25519/cgroup/canary design is outside this task and will not be reused.
  - A hidden transport pre-accept delay is the dominant W8 `/cup_pose` cost; its 0.091 s median was below internal Broker queue wait, response delivery, model execution, and the full Broker round trip.
  - YOLO compute, RGB capture, simulation pause/resume, exact-TF localization, numeric capture, pose admission, or DDS callback delivery is the first expected-budget violation in EXP-006; no configured budget was violated.
  - The two EXP-006 `TRUNCATED_FRAME` events are ordinary Broker internal queue waits; their failure boundary was the separate accept-eroded transport server-cycle deadline.
open_hypotheses:
  - Fixed-pool throughput should improve from W1 until shared C2 inference, host CPU/memory, and per-point motion lifecycles dominate; additional Workers beyond that knee may add startup/resource cost without proportional throughput.
  - The production Broker may not persist its optional concurrency summary before the frozen five-second Docker stop boundary; sealed request correlation remains authoritative, but queue/service distributions will be reported unavailable rather than estimated if the file is absent.
latest_checkpoint: CP-046
next_experiment: NONE
```

## CP-016 — Configured execution timeout restored

```yaml
checkpoint_id: CP-016
last_valid_experiment: EXP-007R2
confirmed_conclusions:
  - EXP-008R5-W6 proved W6 memory-feasible but exposed a Task 10 runtime defect: execute_result used 180 s instead of configured executing_hard_timeout_s 240.0.
  - Operator readback reported RED failed 1 expected and GREEN passed 1, but their stdout was not durably captured; historical RED-before-GREEN ordering is therefore not independently verifiable. The retained adjacent runtime log passed 40. Commit 167c74a941782e37ed1369ee10c42ac6b77088a9 contains only the source fix and regression test.
next_command: Build a fresh candidate-equivalent overlay from commit 167c74a941782e37ed1369ee10c42ac6b77088a9, then launch fresh fixed-W6/C2/no-fallback EXP-008R6-W6 outside the Codex cgroup.
```

## EXP-008R6-W6 — Corrected fixed-W6 no-fallback C2 qualification

```yaml
experiment_id: EXP-008R6-W6
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T00:08:00+08:00
  - status: RUNNING
    at: 2026-09-15T00:11:37+08:00
  - status: INVALID
    at: 2026-09-15T00:17:04+08:00
prior_experiment: EXP-008R5-W6
hypothesis: With execute_result honoring the frozen 240 s configured timeout, W6 completes all twenty points under fixed C2 and no fallback.
single_variable: Replace the hard-coded 180 s runtime deadline with the configured 240 s deadline at commit 167c74a941782e37ed1369ee10c42ac6b77088a9; all Task 10 runtime variables remain frozen.
success_criteria: Exactly W6, 20/20 PASSED, no infrastructure fallback, YOLO only, zero TRUNCATED_FRAME, complete correctness/visual/timing evidence, and exact cleanup.
invalid_criteria: Failure to form READY, oomd kill, provenance/config drift, conflicting stack, missing evidence, or cleanup ambiguity.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r6-w6-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/86w6
source_commit: 167c74a941782e37ed1369ee10c42ac6b77088a9
runner_identity: so101-exp008r6-w6-runner.service invocation 6e6a6f5934624ed49d9ab0fee6214e31; tmux so101-exp008r6-w6/exp008r6-w6-runner; batch scope tmux-spawn-0de73214-febe-49b3-88fc-b292f99e5635.scope.
monitor_identity: so101-exp008r6-w6-monitor.service PID 770538 plus supplemental monitor PID 776248, both outside the runner scope.
observed: All six workers formed READY and twelve points sealed PASSED. The first bad terminal boundary was coordinator LEASE_EXPIRED seq1762 exactly 240.000 s after worker-02 entered EXECUTING for cup_test_forward_5cm; later authorization, port and dynamic errors followed revocation/stop. No oomd or TRUNCATED_FRAME occurred; scope MemoryPeak was 6684532736 bytes. Exit 1, elapsed 327.39634367008694 s, exact cleanup complete with claims 215-220 RELEASED.
conclusion: INVALID under the handoff's unable classification: the clean W6 stack remained memory-safe but could not complete the frozen point within the configured 240 s hard boundary. This authorizes fresh W1; no further source change is warranted.
decision: RETRY_FIXED_AT_W1
```

## Evidence policy

- Registered evidence root: `/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01`.
- Every ai-station pytest or colcon invocation uses a unique, previously nonexistent directory under `scratch/<test-run-id>/tmp` for `TMPDIR`, `TMP`, and `TEMP`.
- Scratch directories, logs, manifests, screenshots, and runtime evidence are retained unless the user separately authorizes deletion.
- `/data/work/ws_moveit/.worktrees/parallel-w8-admission-v2`, its untracked test, and `/data/work/so101-evidence/parallel-w8/20260913-q01` are read-only preserved external state.

## EXP-001 — Automated adaptive contracts and package integration

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: The adaptive contracts, scheduler, production adapter, cleanup path, and CLI can satisfy the lightweight design while leaving v1 behavior unchanged.
prediction: Task-level RED tests fail only because each planned interface is absent, then pass after minimal implementation; the final so101_demo_py package gate collects nonzero ordinary tests with zero errors and failures.
single_variable: Introduce only the explicit adaptive-workers path described by the reviewed plan.
lifecycle: ISOLATED_STACK
preconditions:
  - source starts from origin/main commit 4c777fa722586be92a0b357b861ab4ce460a06ab in the dedicated worktree.
  - no live SO-101 stack is used by this automated experiment.
  - each test command receives a fresh NVMe scratch directory and verified tempfile path.
success_criteria:
  - every planned RED fails at the intended missing behavior boundary.
  - every task GREEN and compatibility regression exits 0.
  - package test collects nonzero tests only under src/so101_demo_py/test and reports zero errors and failures.
failure_criteria:
  - a planned contract remains absent, a compatibility regression appears, or package test reports an error or failure.
invalid_criteria:
  - source, Python, install overlay, or scratch provenance differs from the recorded command.
provenance:
  source_commit: 4c777fa722586be92a0b357b861ab4ce460a06ab
  qualified_feature_commit: 467065a0f55e4fad9eea68741598fce0c8c14386
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install
  runtime_executable: /usr/bin/python3
  torch: 2.13.0+cu130 from /data/work/venvs/so101-v5-t004-perception/lib/python3.12/site-packages
  submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  ros_domain_id: 0
  gz_partition: adaptive-worker-exp001-contracts
commands:
  - command: per-task pytest RED/GREEN commands and final colcon package gate from the implementation plan
    exit_code: 0
observed:
  - Startup preflight is recorded at /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/preflight/dispatch-preflight.md.
  - Baseline-007 passed all 1111 existing parallel-batch tests in 50.51 s outside the sandbox with current-checkout so101_demo source mapping and existing ai-station ROS/MuJoCo dependency overlay.
  - Task 2 RED failed at the absent adaptive parser boundary; the final Task 2 GREEN passed 111/111 and the v1 compatibility gate passed 100/100. Evidence is recorded in task-02/cli-contract.md.
  - Task 3 focused RED failed only at the absent adaptive selector module; GREEN passed 136/136 and concurrency/fault regression passed 145/145. Evidence is recorded in task-03/adaptive-scheduler.md.
  - Task 4 final combined gate passed 370/370 after the intended missing-policy RED; a short-path v1 CLI rerun passed 85/85. Evidence is recorded in task-04/readiness-and-resources.md.
  - Task 5 missing-module RED was followed by 10/10 GREEN for startup and runtime fallback, terminal preservation, cleanup failure, attempt limits, append-only events, and crash report-only replay. Evidence is recorded in task-05/fallback-runner.md.
  - Task 6 production adapter RED failed at 12 absent production/factory/classifier boundaries; split GREEN and compatibility gates passed 265/265. Evidence is recorded in task-06/production-adapter.md.
  - Task 7 Broker capacity RED failed at four absent override boundaries; Broker/perception/runtime/IPC/spec GREEN gates passed 367/367. Evidence is recorded in task-07/perception-queue.md.
  - Task 8 RED failed at the four absent supervision/cleanup/output boundaries. The final focused integration gate passed 5/5; process, crash-recovery, resource, and post-review CLI/integration regressions passed 17/17, 33/33, 136/136, and 93/93. Evidence is recorded in task-08/failure-and-cleanup.md.
  - Task 9 targeted adaptive integration passed 71/71. The complete candidate overlay package gate collected 2995 ordinary tests: 2994 passed, 1 skipped, 0 errors, and 0 failures in 90.76 s; benchmark_test was not collected. Evidence is recorded in task-09/package-integration.md.
inferred:
  - The package-local libexec directory must be on PATH for direct console-script invocation; ROS 2 package discovery alone exposes the same commands through ros2 pkg executables.
conclusion: The adaptive implementation and its frozen v1 compatibility contracts pass the complete ordinary package suite from one candidate-local overlay and one absolute system Python provenance chain.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
decision: Proceed to isolated MuJoCo startup and runtime fault injection.
next_experiment: EXP-002A
```

## CP-001 — Dispatch and implementation baseline

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The reviewed lightweight design can be implemented from the clean origin/main baseline without using the preserved heavy branch.
working_tree_status: clean at 4c777fa722586be92a0b357b861ab4ce460a06ab before ledger creation
owned_processes: current Codex session only; no SO-101 runtime process started
preserved_processes: tmux sessions codex and codex-task-so101-adaptive-worker-pool; no codex-cua or legacy admission session existed at preflight
confirmed_conclusions:
  - origin/main was fetched from Gitee and equals the required reviewed commit.
  - target worktree and branch were absent before creation, then created at the required path and commit.
  - ROS_DOMAIN_ID 0 had no visible nodes, and no matching SO-101 runtime process was present.
disproven_routes:
  - reuse of the old heavy W8 worktree is prohibited and unnecessary.
open_risks:
  - the root workspace install overlay contains a stale so101_demo_py hook; all build and runtime provenance must use the new worktree overlay.
  - live MuJoCo, Docker broker, model, GPU, and GUI availability remain unverified until later task gates.
  - baseline-001 through baseline-005 are invalid environment probes and their scratch trees are deletion candidates; baseline-007 is the valid subsystem baseline.
next_command: dispatch Task 1 implementer from its generated brief
```

## CP-002 — Automated implementation and package acceptance

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-001
current_hypothesis: Exact owned-identity fault injection will cause the adaptive runner to clean W8 and continue at W6 without touching task-external sentinels.
working_tree_status: Task 9 integration test and this ledger update are the only intended changes after commit 467065a0f.
source_commit: 467065a0f55e4fad9eea68741598fce0c8c14386
install_prefix: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install/so101_demo_py
package_gate: 2995 tests, 0 errors, 0 failures, 1 skipped
owned_processes: current Codex session only; all harmless pytest subprocesses were retired by their owning fixtures
preserved_processes: preflight tmux sessions and the legacy admission worktree remain untouched
confirmed_conclusions:
  - adaptive config and cleanup console entry are installed in the candidate overlay.
  - six explicit adaptive CLI options are present and abandoned heavy-admission options and imports are absent.
  - the pinned mujoco_ros2_control submodule and candidate support/teleop installs satisfy installed provenance.
invalid_runs:
  - task-09-package lacked the approved ML dependency path and collected zero tests.
  - task-09-package-r2 used an incomplete candidate overlay and had six install-provenance failures.
  - task-09-package-r3 had one transient domain-lock race failure; the test passed alone and task-09-package-r4 passed the full suite.
open_risks:
  - live Docker, CUDA, MuJoCo, MoveIt, model, and GUI readiness are not yet proven.
  - direct console commands require the installed package libexec directory on PATH.
next_command: implement and RED/GREEN test exact adaptive Worker fault injection
```

## EXP-002A — Startup fault before readiness

```yaml
experiment_id: EXP-002A
status: VALID
prior_experiment: EXP-001
hypothesis: Terminating one registered W8 Worker before POOL_RUNNING and before any lease is granted will make the runner clean W8 and continue at W6 without affecting processes outside the batch manifest.
prediction: W8 grants zero leases, one 8-to-6 fallback occurs, W6 reaches readiness and completes all four points, cleanup succeeds, and both task-owned side sentinels survive.
single_variable: Send SIGTERM to the exact registered W8 Worker identity before POOL_RUNNING and LEASE_GRANTED.
lifecycle: ISOLATED_STACK
batch_id: su09
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/su09
provenance:
  source_commit: 3d35cb017caddcb7ffecc667f031fde25a162903
  broker_image_id: sha256:3b1a6661a87359729b848cb92807c0e45f618ae2dec0e20a1f534e51f6148a79
  broker_source_sha256: 286b5d9f4e994e897c1c01bb75c79d399dbbeaba573a7779424e4a498146a37e
  runtime_executable: /usr/bin/python3
  initial_worker_count: 8
  fallback_worker_counts: [6, 4, 2, 1]
observed:
  - The injector selected worker01 with PID and PGID 3911563 and start ticks 118345028 before POOL_RUNNING and before any lease was granted.
  - W8 granted zero leases. The only transition was W8 to W6 after the injected Worker exited with signal 15.
  - W6 completed task_start, cup_test_forward_5cm, sample_05_near_center, and sample_14_far_right as PASSED.
  - The batch finished COMPLETED in 179.47665203316137 seconds with levels_used [8, 6], final_worker_count 6, and batch_cleanup_complete true.
  - Domains 215 through 220 were released, and no owned process remained in either generation manifest.
  - The recorded sleep and ROS Domain 230 sentinels retained their original PID, PGID, session, and start-tick identities after the batch.
invalid_runs:
  - su01 through su08 were retained as diagnostic or invalid attempts and were not used for acceptance.
conclusion: Exact failure of a registered Worker before readiness causes one clean startup fallback from W8 to W6. No task-external process was removed.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/su09
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-10/exp002a-r9-injection.txt
decision: Accept EXP-002A and run the active-attempt fault experiment.
next_experiment: EXP-002B
```

## EXP-002B — Active attempt fault after committed work

```yaml
experiment_id: EXP-002B
status: VALID
prior_experiment: EXP-002A
hypothesis: Terminating the Worker for one active attempt after W8 has committed work will preserve terminal results, mark unfinished work as infrastructure interrupted, and let W6 process only unfinished points.
prediction: The injected attempt receives POINT_INFRA_INTERRUPTED, previously committed points are not rerun, one 8-to-6 fallback occurs, W6 passes the interrupted and remaining points through the initial gate, all 20 points pass, cleanup succeeds, and both side sentinels survive.
single_variable: Send SIGTERM to the exact Worker identity of one active second-wave attempt after eight W8 results are committed.
lifecycle: ISOLATED_STACK
batch_id: mr08
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/mr08
provenance:
  source_commit: 3d35cb017caddcb7ffecc667f031fde25a162903
  broker_image_id: sha256:3b1a6661a87359729b848cb92807c0e45f618ae2dec0e20a1f534e51f6148a79
  broker_source_sha256: 286b5d9f4e994e897c1c01bb75c79d399dbbeaba573a7779424e4a498146a37e
  runtime_executable: /usr/bin/python3
  initial_worker_count: 8
  fallback_worker_counts: [6, 4, 2, 1]
observed:
  - Before injection, W8 had committed exactly eight first-wave points: sample_01_near_left, sample_04_near_left, cup_test_left_5cm, task_start, sample_02_near_center, cup_test_right_5cm, sample_03_near_right, and cup_test_forward_5cm.
  - The injector selected worker05 for sample_05_near_center lease 1 with PID and PGID 30934 and start ticks 118883715 while that second-wave attempt was active.
  - The top journal records POINT_INFRA_INTERRUPTED for sample_05_near_center and every other unfinished point. None of the eight terminal W8 points received another business attempt.
  - W6 admitted sample_05_near_center through a new POINT_INITIAL_GATE with all checks true and later committed it PASSED. W6 committed exactly the interrupted point and the other 11 points that were unfinished at injection.
  - The batch finished COMPLETED in 439.67304879799485 seconds with 20 PASSED points, levels_used [8, 6], one W8-to-W6 transition, final_worker_count 6, and batch_cleanup_complete true.
  - Domains 215 through 220 were released, both generation manifests had no owned process, and no broker container remained.
  - Both recorded side sentinels survived this batch. Their exact process groups were stopped only after identity revalidation, and the dedicated sentinel tmux session was then absent.
invalid_runs:
  - mr01 through mr05 exposed production race and clock defects and were retained as diagnostic evidence.
  - mr06 completed all 20 points but used levels [8, 6, 4], so it was retained as recovery evidence rather than acceptance for the predicted single transition.
  - mr07 failed naturally before injection because a publisher clock became stale. The task-owned runner and watcher were stopped, cleanup completed, and the run was retained as invalid.
fixes_from_diagnostic_runs:
  - f10106bd2, 53a404f99, c128ebbaa, a5fc810ff, 35a9ac8bd, 70598fe26, e5001ade4, be4c08a11, e33e59537, 47dd44445, a6421af8e, 7169a68ce, and 3d35cb017.
conclusion: An exact active-attempt Worker failure preserves committed results and moves only unfinished work to W6. All 20 points passed, cleanup was exact, and the sentinels were unaffected.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/mr08
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-10/exp002b-r8-injection.txt
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-10/sentinels-04/cleanup-readback.txt
decision: Accept EXP-002B and proceed to the uninjected 20-point adaptive regression.
next_experiment: EXP-003
```

## EXP-003 — Full adaptive execute regression

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002B
hypothesis: The qualified adaptive ladder can complete the full 20-point catalog without injected faults while preserving each point's initial-state and sealed-evidence contracts.
prediction: Every point passes, the final Worker level is one of W8, W6, W4, W2, or W1, all accepted attempts have fresh initial gates and complete evidence, terminal images agree with the batch result, and cleanup succeeds.
single_variable: Remove fault injection and increase initial-points-per-worker from 1 to 3 for the full execute regression.
lifecycle: ISOLATED_STACK
batch_id: e2001
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e2001
provenance:
  source_commit: 62cd8e9424a47e25fe5a9e9729268294ee2a13b9
  package_source_commit: 3d35cb017caddcb7ffecc667f031fde25a162903
  install_prefix: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install/so101_demo_py
  runtime_executable: /usr/bin/python3
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  broker_image_id: sha256:3b1a6661a87359729b848cb92807c0e45f618ae2dec0e20a1f534e51f6148a79
  broker_source_sha256: 286b5d9f4e994e897c1c01bb75c79d399dbbeaba573a7779424e4a498146a37e
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
configuration:
  initial_worker_count: 8
  fallback_worker_counts: [6, 4, 2, 1]
  initial_points_per_worker: 3
  worker_start_timeout_s: 120
  max_infra_attempts_per_point: 5
  ros_domain_ids: [215, 216, 217, 218, 219, 220, 221, 222]
observed:
  - W8 passed readiness and imported eight PASSED first-wave points. A later active attempt became invalid or indeterminate, so the runner retained those terminal results, interrupted the other 12 points, and performed one W8-to-W6 recovery.
  - W6 passed readiness and committed all 12 unfinished points. The batch finished COMPLETED in 456.1064693250228 seconds with levels_used [8, 6], final_worker_count 6, and batch_cleanup_complete true.
  - The accepted load was one point on each W8 Worker and two points on each W6 Worker.
  - All 20 imported results were PASSED and had a valid POINT_INITIAL_GATE, a YOLO-first POSE_ACCEPTED receipt, DONE dynamic execution, empty final attached_object_ids, stable table support without fingertip contact, and a verified sealed hash tree. Grounded-SAM was not needed.
  - All 20 terminal RGB images were opened in a contact sheet. P01, P09, P18, P19, and P20 were also opened at original resolution. Each frame shows the cup upright inside the red target ring and the open gripper retreated clear of the cup.
  - The generated top-view state chart shows all P01 through P20 as successful and agrees with the aggregate result.
  - Both generation owned-process manifests are empty. The cleanup receipt released Domains 215 through 220, no broker container remained, and the wrapper exited 0.
visual_evidence:
  terminal_contact_sheet: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-11/e2001-terminal-rgb-contact-sheet.png
  terminal_contact_sheet_sha256: 55bdafb29999de2abb513b666a49a7ded61a766d2c1be1574666c8c6bc572434
  top_view_png: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-11/e2001-top-view/so101-position-top-view.png
  top_view_png_sha256: e2c2c3eceff87f952af4c41a9313b3f718fe1f01e44d1c17b2885ed14b5dba6b
conclusion: The adaptive execute path completed the full catalog with 20 PASSED results and exact cleanup. Its allowed recovery preserved the eight W8 terminal points and completed the remaining 12 at W6.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e2001
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-11
decision: Accept EXP-003 and proceed to no-fallback performance samples for W1, W2, W4, W6, and W8.
next_experiment: EXP-004
```

## CP-003 — Full execute acceptance

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-003
current_hypothesis: Each fixed Worker level can complete the same 20-point catalog without fallback and provide a comparable elapsed-time sample.
working_tree_status: clean at 62cd8e9424a47e25fe5a9e9729268294ee2a13b9 before this ledger update
source_commit: 62cd8e9424a47e25fe5a9e9729268294ee2a13b9
accepted_batches: [su09, mr08, e2001]
owned_processes: current Codex session only; e2001 generation manifests are empty and its task-owned tmux session exited
preserved_processes: pre-existing process groups 3835752, 3835753, 3882463, and 3882464; tmux sessions codex and codex-task-so101-adaptive-worker-pool
confirmed_conclusions:
  - startup and active-attempt fault injection both converge through exact W8-to-W6 fallback without touching sentinels.
  - the uninjected full execute regression passes all 20 points and all evidence-layer checks after one allowed W8-to-W6 recovery.
  - e2001 terminal images and the top-view state chart agree with the 20/20 aggregate result.
  - e2001 released its Domains, sockets, broker container, and manifest-owned processes.
retained_runs:
  - accepted: r/su09, r/mr08, and r/e2001
  - diagnostic_or_invalid: r/su01 through r/su08 and r/mr01 through r/mr07
archived_runs: []
deletion_candidates:
  - all scratch trees under scratch/r31 through scratch/r39 after their recorded readback
  - no candidate may be deleted without explicit user authorization
open_risks:
  - W1, W2, W4, W6, and W8 no-fallback performance samples have not yet been collected.
next_command: implement and dry-run check scripts/run_so101_adaptive_worker_scaling.zsh
```

## CP-004 — Scaling pause and standalone-inference handoff

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-003
current_hypothesis: Independent production YOLO-Seg detector instances can expose a standalone GPU concurrency ceiling and an earlier useful saturation point without running ROS, MuJoCo, MoveIt, Gazebo, or physical execution.
working_tree_status: dirty at 48ade9ab132a327ae7ec58001f87323c786093e9; preserved pre-existing paths are src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT; this ledger is the task-owned change.
owned_processes: current Codex dispatch process only; host-level inspection found no so101-adaptive-scaling tmux session, no scaling driver, no ROS/MoveIt/MuJoCo/Gazebo runtime, and no Docker container.
preserved_processes: tmux sessions codex and codex-task-so101-adaptive-worker-pool; neither is touched.
confirmed_conclusions:
  - The final W1 batch wy101 reached 20 PASSED point results at one Worker in 1630.650472841924 s; its first top-level aggregate was INFRA_FAILED only at cleanup classification PROC_CLASSIFICATION_UNVERIFIABLE.
  - The exact owned cleanup rerun for wy101 succeeded, released ROS Domain 215, and left /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/wy101/p/g01w01/owned-processes.json with an empty processes list.
  - The timing report is retained at /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/reports/worker-scaling-wy101.time and the aggregate and cleanup receipt remain under r/wy101.
  - No successor scaling batch was created after wy101 and the so101-adaptive-scaling session is absent; W2 and the rest of the full-stack matrix remain paused.
disproven_routes:
  - Treating the initial wy101 top-level status as a clean performance acceptance is unsupported because cleanup was repaired only by a later exact rerun.
open_risks:
  - Frozen broker image, detector adapter, representative sealed RGB inputs, model hashes, CUDA identity, and baseline GPU process evidence must be recovered before the standalone benchmark starts.
  - Standalone model-instance concurrency does not establish production Broker concurrency because Broker.run_next() remains serialized.
next_command: recover frozen inference provenance and append EXP-004 as PLANNED before starting its isolated harness
```

## EXP-004 — Standalone YOLO-Seg inference concurrency ceiling

```yaml
experiment_id: EXP-004
status: INVALID
prior_experiment: EXP-003
hypothesis: Independent production YOLO-Seg detector instances in the immutable production broker image will remain output-equivalent and stable through a measurable concurrency ceiling, with a useful throughput saturation point at or below that ceiling.
prediction: Admitted levels 1, 2, 4, 6, 8, 12, and 16 complete three repetitions of at least 100 representative sealed-frame requests unless an invalid result, less than 4 GiB free VRAM, or two consecutive sub-5-percent throughput gains without p95 improvement stops higher levels.
single_variable: Number of independent YOLO-Seg model instances and concurrent request slots; image, image inputs, weights, adapter, post-processing, device, and singleton Grounded-SAM resident baseline remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - The full-stack W1/W2/W4/W6/W8 matrix is paused after wy101 and no scaling session, Docker container, ROS, MoveIt, MuJoCo, Gazebo, or physical process is running.
  - Production image ID is sha256:c11369640bba27a5415c5467d9b8c5203aee77a6043cf202b2506ea86016758b with source SHA256 674f42465eb726329a3c179079fd1b330d4055fdaf0b424d584386d9a5c338f4.
  - YOLO weights are the read-only best.pt with SHA256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781; Grounded-SAM manifest SHA256 is 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775.
  - Inputs are one immutable sealed rgb.npy per point from accepted 20-point batch e2001, selected deterministically by point ID and hashed before use.
success_criteria:
  - Every admitted level executes at least 100 measured requests in each of three repetitions after representative warmup, with zero errors, timeouts, crashes, OOMs, missing results, or NaNs.
  - Model ID, weights hash, candidate count, class, confidence, bbox, and mask semantics match the concurrency-1 reference within the recorded comparison contract.
  - Raw latency, throughput, GPU, VRAM, power, CPU, RAM, model-load, command, exit, and result-hash evidence is retained with a machine-readable summary.
failure_criteria:
  - Any output mismatch, CUDA error, OOM, process crash, timeout, NaN, missing result, or fewer than the contracted request count makes that level invalid and stops higher levels.
  - Less than 4 GiB free VRAM or two consecutive concurrency increases below 5 percent throughput improvement while p95 does not improve stops higher levels without relabeling prior valid levels.
invalid_criteria:
  - Image, package source, model, input hash, device, process baseline, or output evidence differs from frozen provenance.
  - Any ROS, MoveIt, MuJoCo, Gazebo, or physical execution starts during the benchmark.
provenance:
  source_commit: 48ade9ab132a327ae7ec58001f87323c786093e9
  install_overlay: immutable Docker image sha256:c11369640bba27a5415c5467d9b8c5203aee77a6043cf202b2506ea86016758b
  runtime_executable: /opt/venv/bin/python inside the immutable production broker image
  ros_domain_id: 0
  gz_partition: inference-only-none
commands:
  - command: zsh /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-13-inference-concurrency/exp004-standalone-yolo-ceiling/run_benchmark.zsh
    exit_code: 1
observed:
  - Host baseline before launch is AI-STATION-001 with NVIDIA GeForce RTX 5080, driver 595.84, 16303 MiB total, 537 MiB used, 15272 MiB free, zero reported compute applications, and no active production container.
  - The only host tmux sessions are codex and codex-task-so101-adaptive-worker-pool; no so101-adaptive-scaling session exists.
  - Frozen image, source, model, input, resource, and forbidden-process checks are enforced by the isolated harness before measurements are accepted.
  - Level 1 executed 360 requests with zero inference or equivalence errors, but the resource sampler failed before its first valid row because one /proc/self/status field had an empty value and the parser indexed that empty token list.
  - The level was correctly marked INVALID and no higher level started. The exact owned container exited and no GPU compute process remained.
inferred:
  - The observed level-1 latency and throughput are diagnostic only because the mandatory fine-grained resource record is absent.
conclusion: INVALID_HARNESS_RESOURCE_SAMPLER; no concurrency result from this attempt is accepted.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-13-inference-concurrency/exp004-standalone-yolo-ceiling
decision: REPEAT
next_experiment: EXP-005
```

## CP-005 — EXP-004 invalid harness isolation

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-003
current_hypothesis: The production inference path remains benchmarkable after correcting only the empty /proc status-field parser and invalid-level summarizer; no model, input, concurrency, or acceptance variable changes.
working_tree_status: dirty at 48ade9ab132a327ae7ec58001f87323c786093e9; preserved pre-existing paths remain src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT; ledger changes are task-owned.
owned_processes: current Codex dispatch process only; EXP-004 container exited and host nvidia-smi reports no compute application.
preserved_processes: tmux sessions codex and codex-task-so101-adaptive-worker-pool; no scaling or SO-101 stack process was touched.
confirmed_conclusions:
  - EXP-004 is INVALID solely because mandatory resource sampling failed; all 360 diagnostic level-1 inferences were output-equivalent and are retained but excluded.
  - The first retry must write to a new directory and retain the original scripts, logs, summaries, and zero-row resource failure unchanged.
disproven_routes:
  - Accepting point-in-time GPU checkpoints as a substitute for the required fine-grained peak sampler is prohibited.
open_risks:
  - Corrected 100 ms resource sampling and invalid-summary handling require a fresh isolated run before any level can count.
next_command: create the non-overwriting EXP-005 harness copy with the two parser fixes, validate syntax, then mark RUNNING and execute
```

## EXP-005 — Standalone YOLO-Seg inference concurrency ceiling retry

```yaml
experiment_id: EXP-005
status: VALID
prior_experiment: EXP-004
hypothesis: With only the resource-sample parser and invalid-summary robustness corrected, the unchanged isolated production-adapter sweep will produce valid fine-grained metrics and expose the standalone ceiling and saturation point.
prediction: The same frozen levels, three repetitions, 120-or-more requests, output equivalence, singleton Grounded-SAM resident baseline, and stop policy complete with nonempty 100 ms resource samples per admitted level.
single_variable: Harness evidence parsing only; model image, production adapter/post-processing, weights, sealed inputs, CUDA device, concurrency levels, request counts, and stop thresholds are unchanged from EXP-004.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-004 evidence remains unchanged and excluded.
  - No Docker container, GPU compute process, scaling session, ROS, MoveIt, MuJoCo, Gazebo, or physical process is active.
success_criteria:
  - Every admitted level is output-equivalent, has zero errors, contains three repetitions of at least 100 requests, and retains fine-grained GPU/CPU/RAM samples.
  - The sweep applies the 4 GiB headroom and two-consecutive-sub-5-percent-gain stop rules and emits standalone_max_stable, standalone_saturation_point, and recommended_initial_broker_parallelism separately.
failure_criteria:
  - Any model/output/CUDA/process/resource contract failure invalidates the level and stops higher levels.
invalid_criteria:
  - Any frozen provenance drift, missing resource samples, forbidden stack process, or overwritten EXP-004 artifact invalidates the retry.
provenance:
  source_commit: 48ade9ab132a327ae7ec58001f87323c786093e9
  install_overlay: immutable Docker image sha256:c11369640bba27a5415c5467d9b8c5203aee77a6043cf202b2506ea86016758b
  runtime_executable: /opt/venv/bin/python inside the immutable production broker image
  ros_domain_id: 0
  gz_partition: inference-only-none
commands:
  - command: zsh /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-13-inference-concurrency/exp005-standalone-yolo-ceiling-r2/run_benchmark.zsh
    exit_code: 0
observed:
  - The retry directory is new and EXP-004 remains retained unchanged. Syntax checks pass for both Python programs and the zsh driver.
  - The only active variable is the evidence parser correction: empty /proc status values map to zero, and final aggregation tolerates absent resource fields on invalid attempts.
  - Concurrency levels 1, 2, 4, 6, and 8 each completed three repetitions and 360 measured requests. All 1800 requests succeeded with no errors, NaNs, timeouts, crashes, OOMs, missing results, or output mismatches.
  - Median throughput in requests/s was C1 159.16951733856035, C2 219.42433400614138, C4 240.49865857664452, C6 229.08657927125662, and C8 210.5941610999844.
  - Aggregate p95 latency in milliseconds was C1 6.45629065, C2 9.133219200000001, C4 17.5460698, C6 27.34478475, and C8 49.608332850000004.
  - C4 to C6 throughput changed by -4.745173787217183 percent and C6 to C8 by -8.072239862369123 percent while p95 worsened at both increases. The frozen saturation rule stopped levels 12 and 16 and selected C4 as the useful saturation point.
  - Peak observed GPU memory was 3383 MiB, minimum free memory was 12426 MiB, peak utilization was 43 percent, and peak power was 95.57 W. Every admitted level remained above the 4 GiB headroom gate.
  - The singleton Grounded-SAM resident increment was 2611 MiB and it handled zero measured requests. At C8, independent YOLO replicas added 64 MiB at the resident checkpoint and runtime workspace/input growth added another 168 MiB at peak.
  - Resource sampling retained 58 through 64 samples per level at an approximately 122 to 124 ms median interval, plus raw process CPU and RAM evidence.
  - After completion, no task container, GPU compute application, forbidden full-stack process, or scaling session remained. The full-stack matrix was not resumed.
inferred:
  - C2 is the conservative production starting point: it improves median throughput by 37.855751324178776 percent over C1, while C4 adds only 9.604369846196414 percent over C2 and nearly doubles p95 latency from 9.133219200000001 to 17.5460698 ms.
  - This isolated result does not establish the production Broker limit because the current PerceptionService.run_next() path is serialized.
conclusion: The highest stable admitted standalone concurrency is 8, the useful saturation point is 4, and recommended initial production Broker parallelism is 2.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-13-inference-concurrency/exp005-standalone-yolo-ceiling-r2
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-13-inference-concurrency/exp005-standalone-yolo-ceiling-r2/summary.json; file SHA256 7f53d99f17dcfc1890bbf14bc5cf4c195afe91d2c47e79dde796a2f146b10449; internal summary SHA256 bfa9a09dc39eda366b5bcfdd558e2891a0327d53754c8322635515b74538640a.
decision: KEEP
next_experiment: NONE
```

## CP-006 — Standalone inference concurrency acceptance

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-005
current_hypothesis: A production Broker implementation with two independent YOLO detector slots should capture most useful standalone throughput while limiting p95 growth; this requires a separate production Broker RED/GREEN and runtime experiment.
working_tree_status: dirty at 48ade9ab132a327ae7ec58001f87323c786093e9; preserved pre-existing paths are src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT; this ledger is the only task-owned source-tree change.
owned_processes: NONE; every EXP-005 container exited, docker-after.txt is empty, and host nvidia-smi reports no compute application.
preserved_processes: tmux sessions codex and codex-task-so101-adaptive-worker-pool remain; no unrelated process or session was stopped.
confirmed_conclusions:
  - EXP-005 is VALID at standalone concurrency 1, 2, 4, 6, and 8 with 1800 of 1800 output-equivalent measured requests and zero errors.
  - standalone_max_stable is 8, defined as the highest level admitted and tested before the frozen saturation stop; levels 12 and 16 are untested, not proven unstable.
  - standalone_saturation_point is 4 because it produced the highest median throughput, and both later increases reduced throughput while worsening p95.
  - recommended_initial_broker_parallelism is 2 because it gains 37.855751324178776 percent over C1, whereas C4 gains only 9.604369846196414 percent over C2 with much higher p95.
  - Peak GPU memory was 3383 MiB, leaving at least 12426 MiB free; the singleton Grounded-SAM resident contribution was 2611 MiB and was not replicated or invoked.
disproven_routes:
  - Increasing standalone concurrency beyond 4 improves throughput on this workload; C6 and C8 both reduced it.
  - EXP-004 diagnostic measurements are acceptable without resource samples; EXP-004 remains INVALID.
open_risks:
  - Current production Broker.run_next() remains serialized, so no production concurrency limit or safety claim follows from this standalone harness.
  - Concurrency 12 and 16 were intentionally not tested after the required saturation stop and must not be described as unstable.
next_command: add a separate production Broker experiment with independent per-slot detector ownership at initial parallelism 2; do not resume the full-stack scaling matrix without a new user instruction
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-13-inference-concurrency/exp005-standalone-yolo-ceiling-r2
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-13-inference-concurrency/exp004-standalone-yolo-ceiling as INVALID diagnostic evidence
  - all prior registered-root evidence including r/wy101 and its cleanup receipt
archived_runs: []
deletion_candidates:
  - NONE from EXP-004 or EXP-005; no evidence was deleted or archived
  - previously recorded scratch deletion candidates remain unchanged and require explicit user authorization
```

## EXP-006 — No-fallback W8 `/cup_pose` critical-path diagnostic

```yaml
experiment_id: EXP-006
status: VALID
prior_experiment: EXP-005
hypothesis: Under exactly eight admitted execute Workers, delay before the serialized production Broker accepts each infer RPC dominates the consumer READY-to-POSE_ACCEPTED interval and causes the first expected-budget violation; GPU execution itself remains below its inference budget.
prediction: Client-side Broker round-trip wait will grow with concurrent W8 demand while the Broker's internal queued-to-started duration and YOLO started-to-completed duration remain within their configured 10 s and 20 s budgets; per-attempt tracing will distinguish this from RGB/RGB-D capture, pause/resume, localization/admission, and DDS delivery.
single_variable: Enable measurement-only per-process monotonic tracing and frequent host/GPU resource sampling during one W8 execute run; worker count is fixed at 8 and fallback is disabled, with production timeouts, scheduling, models, pause semantics, retry policy, catalog, geometry, and motion unchanged.
lifecycle: ISOLATED_STACK
preconditions:
  - CP-006 and EXP-005 are recovered; accepted standalone saturation remains C4 and production Broker execution remains serialized.
  - The authoritative worktree is 48ade9ab132a327ae7ec58001f87323c786093e9 with preserved dirty src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT plus this task-owned ledger.
  - No conflicting SO-101, MoveIt, MuJoCo, Gazebo, scaling, Docker, GPU-compute, or ROS Domain 0 runtime is active before launch.
  - Diagnostic output is new and non-overwriting under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline; batch runtime identity is w8d1.
success_criteria:
  - Exactly eight Workers are initially admitted and no W6/W4/W2/W1 fallback generation starts.
  - Every W8 attempt has a host-monotonic timeline from consumer spawn/READY/get_one deadline through POSE_ACCEPTED or exact termination, including all stages required by the dispatch.
  - Broker response timestamps, model identity, resource samples, clock-namespace validation, provenance, command/exit code, point outcomes, and exact cleanup are retained and machine-readable.
failure_criteria:
  - A valid failed attempt is accepted as diagnostic evidence only when its first bad boundary and all preceding required timing fields are present.
  - Any W8 infrastructure failure terminates the no-fallback ladder rather than launching a lower Worker count.
invalid_criteria:
  - Missing stage/resource evidence, clock incomparability, provenance drift, conflicting runtime processes, fallback admission, overwritten prior evidence, or incomplete cleanup makes this experiment INVALID.
provenance:
  source_commit: 48ade9ab132a327ae7ec58001f87323c786093e9
  install_overlay: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/candidate-src/install; clean detached candidate rebuild, package source tree e4a42261b20639d52046f749fd5a5f8b1e284aa31f521d12a1c2fb0a0f636fbe
  runtime_executable: /usr/bin/python3 plus immutable production Broker image sha256:c11369640bba27a5415c5467d9b8c5203aee77a6043cf202b2506ea86016758b
  ros_domain_id: [215, 216, 217, 218, 219, 220, 221, 222]
  gz_partition: not_applicable
commands:
  - command: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/run_w8_diagnostic_live1.zsh
    exit_code: 0
observed:
  - Preflight dry-run pf061 recorded clean commit 48ade9ab132a327ae7ec58001f87323c786093e9, all 20 catalog points, worker_count 8, fallback_worker_counts [], immutable Broker image sha256:c11369640bba27a5415c5467d9b8c5203aee77a6043cf202b2506ea86016758b, and levels_used [8].
  - Immediately before live launch, no task runtime, Docker container, GPU compute process, or conflicting ROS stack remained; host and Broker-container monotonic and boottime namespace offsets were both zero.
  - The first wrapper invocation exited 1 before creating any runtime, Worker, ROS, Docker, or GPU state because candidate package metadata was absent from PYTHONPATH. It remains preserved as a pre-launch harness diagnostic and is not an experiment run.
  - The corrected single real execute run admitted eight Workers, used only level 8, started no fallback generation, completed in 362.4538940861821 s, and reported all 20 catalog points PASSED with zero infrastructure retries.
  - All 20 attempts contain all 17 required timing segments. READY-to-POSE_ACCEPTED was min 0.565010 s, median 2.283755 s, p95 6.869651 s, and max 7.921919 s.
  - The dominant composite stage was the perception chain at min 0.278100 s, median 1.507415 s, p95 4.322592 s, and max 5.862980 s. The dominant measured segment within it was Broker client round trip at min 0.218828 s, median 1.432061 s, p95 3.663370 s, and max 3.995127 s; its per-attempt share of READY-to-POSE_ACCEPTED was min 23.816%, median 44.501%, p95 81.032%, and max 85.999%.
  - Inside the Broker round trip, hidden transport pre-accept was median 0.090826 s and p95 1.037377 s, internal queue wait was median 0.511249 s and p95 1.403534 s, YOLO execution was median 0.297820 s and p95 0.738712 s, and completed-response delivery was median 0.508258 s and p95 1.424287 s. Observed internal queue depth and model execution concurrency were both 1; client RPC pending depth reached 2.
  - All 20 accepted results used plastic-cup-yolo11n-seg-v1 and were QUALIFIED. Grounded-SAM had zero requests and no fallback transition.
  - sample_13_far_center first called at monotonic 1208842.292283 s, entered the Broker queue at 1208842.484512 s, and received TRUNCATED_FRAME at 1208842.711849 s after 0.419566 s. The identical retry began 0.000187 s later; the original model result completed at 1208844.760345 s and the retry received QUALIFIED at 1208846.287411 s.
  - sample_15_far_center first called at monotonic 1208852.387603 s, entered the Broker queue at 1208852.596306 s, completed model execution at 1208854.676872 s, and received TRUNCATED_FRAME at 1208855.419363 s after 3.031760 s. The identical retry began 0.000107 s later and received QUALIFIED after 0.519415 s.
  - The runtime Broker server cycle deadline was 5 s while the Worker client deadline was 240 s. Both queued timestamps precede retry start, both retries reuse the same request/idempotency identity, and neither caused a second logical outcome, Broker generation change, or point failure.
  - No stage crossed its configured budget: consumer readiness max 3.700331 s <= 20 s, RGB capture max 1.645617 s and inference snapshot max 1.058163 s <= 15 s, internal Broker queue max 1.535714 s <= 10 s, YOLO max 0.740119 s <= 20 s, exact-TF localization max 0.083206 s <= 5 s, and get_one max 8.040159 s <= 240 s. Therefore no first bad boundary was observed.
  - The user-requested 5 s target is separate from the configured 240 s get_one timeout. Recomputing the raw monotonic ranges found 5/20 strict target exceedances from get_one start to POSE_ACCEPTED: sample_08_mid_right 5.885912 s, sample_09_mid_left 5.642495 s, sample_11_mid_right 6.814980 s, sample_14_far_right 8.040159 s, and sample_15_far_center 6.134845 s.
  - Recomputing consumer READY to accepted found 4/20 strict 5 s target exceedances: sample_08_mid_right 5.872835 s, sample_11_mid_right 6.814269 s, sample_14_far_right 7.921919 s, and sample_15_far_center 6.131215 s. sample_09_mid_left was 2.601030 s on this view and is the sole set difference.
  - One attempt, sample_07_mid_center-lease-1, rejected 20 retransmissions while its ROS clock was zero; every rejected sample recorded source stamp 6929999999 ns, age -6.929999999 s, future skew 6.929999999 s, and reason CUP_POSE_STALE: source stamp is too far in the future. It accepted a later retransmission and passed.
  - Resource sampling retained 1281 host samples at 0.274908 s median spacing and 161 GPU samples. GPU utilization was 3% median, 21% p95, and 24% max; GPU memory was 4893 MiB median and 4933 MiB max with at least 10876 MiB free; power was 36.74 W median, 58.45 W p95, and 74.17 W max. This excludes GPU capacity saturation as the W8 limiter.
  - Mean host load inside each attempt's critical interval had descriptive Pearson r=0.7419 with READY-to-POSE_ACCEPTED duration, but CPU pressure had r=-0.0556 and GPU utilization r=0.0989. Overlapping attempts share system samples, so these coefficients are correlation evidence, not causal attribution.
  - Cleanup gates, container cleanup, process cleanup, goal cancellation, recovery, and coordinator completion all succeeded. Domains 215 through 222 were released; the post-cleanup process, Docker, GPU-compute, and ROS-domain probe found no task-owned residual.
inferred:
  - Production Broker serialization is observable, but W8 demand in this run reached only two pending client RPCs and one active/queued model interval at a time; the successful run does not reproduce a timeout or an eight-request inference burst.
  - Host scheduling may amplify long intervals, as suggested by load correlation, but the evidence does not make it the root cause; GPU capacity, YOLO compute, hidden pre-accept transport, pause/resume, localization, and DDS delivery are not dominant in this sample.
  - The two TRUNCATED_FRAME errors were caused by AuthenticatedUnixServer.serve_once starting its 5 s deadline before blocking accept, leaving approximately 0.419566 s for sample_13 and 3.031760 s for sample_15 at client-call start. When the shared remainder expired, the server emitted no reply and client receive_frame mapped EOF to TRUNCATED_FRAME. This is transport/server-deadline erosion, not the Broker queued-to-started interval.
  - `_WorkerBrokerProxy._call()` retried the same message, while `_CoordinatorBackedBrokerAuthority.dispatch()` retained the original mutation/result by idempotency key. The retries therefore recovered the original QUALIFIED results; an isolated accept-idle A/B reproduced TRUNCATED_FRAME versus direct success with handler behavior held fixed.
  - Passing the current 240 s timeout contract and missing the separate 5 s target are simultaneous, non-conflicting results: no configured timeout occurred, but W8 has a measured 25% get_one-view and 20% READY-view tail-latency SLO miss rate in this sample.
conclusion: EXP-006 is VALID. The dominant `/cup_pose` critical-path component is the serialized Broker round trip inside the broader perception chain, with roughly equal median internal queue wait and post-inference delivery contributions; no configured stage violated its budget and no first bad boundary occurred under the current configuration. Separately, the W8 tail-latency conclusion is 5/20 over the user-targeted 5 s from get_one start and 4/20 over 5 s from consumer READY.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/live-01/aggregate-timing.json
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/live-01/per-attempt-timeline.json
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/live-01/resource-correlation.json
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/broker-truncated-frame-analysis.json
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/truncated-frame-causal-repro-r3.json
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/tail-latency-5s-analysis.json; SHA256 94fd3697e38865a4dbf5bf44e41488899015affd04f9442f609d74b54ca6f848
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8d1
decision: KEEP; apply no performance fix in this diagnostic dispatch.
next_experiment: NONE
```

## CP-007 — Fixed-W8 `/cup_pose` diagnostic acceptance

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-006
current_hypothesis: NONE; the requested measurement concludes that Broker round trip dominates this successful fixed-W8 sample, but no timeout boundary was reproduced.
working_tree_status: dirty at 48ade9ab132a327ae7ec58001f87323c786093e9; preserved pre-existing paths remain src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT; the ledger is the only task-owned source-tree change.
owned_processes: NONE; exact cleanup completed and post-cleanup probes found no task process, container, GPU compute application, or ROS nodes on domains 215 through 222.
preserved_processes: unrelated tmux sessions and all pre-existing user changes remain untouched.
confirmed_conclusions:
  - EXP-006 is VALID: fixed W8, no fallback, 20 of 20 points PASSED, all mandatory timestamps complete, command exit 0, and exact cleanup complete.
  - The composite perception chain dominates at 1.507415 s median; within it, Broker client round trip dominates measured segments at 1.432061 s median and 44.501% median of READY-to-POSE_ACCEPTED.
  - Every expected budget passed, so EXP-006 has no failed attempt and no first bad boundary.
  - GPU headroom remained large and utilization low; host load correlates descriptively with longer critical intervals, but does not displace the Broker timing result or establish causality.
disproven_routes:
  - Hidden pre-accept transport dominates the interval; its median was 0.090826 s.
  - YOLO execution, pause/resume, exact-TF localization, pose admission, or DDS callback delivery is the first budget violation; none violated a budget.
open_risks:
  - Two automatically recovered TRUNCATED_FRAME responses and the one zero-clock retransmission episode remain observed reliability details, not failed boundaries in this run.
  - One successful 20-point sample does not prove the absence of intermittent timeout behavior in all W8 runs.
next_command: NONE; no performance fix or follow-up experiment is authorized by this diagnostic dispatch.
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8d1
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/pf061
  - all earlier evidence under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
archived_runs: []
deletion_candidates:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/scratch/exp006-red-*/tmp
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/scratch/exp006-green-*/tmp
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/scratch/exp006-final-verify-01/tmp
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/candidate-src
  - none deleted; removal requires explicit user authorization
```

## CP-008 — `TRUNCATED_FRAME` causal attribution

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-006
current_hypothesis: NONE; the two live TRUNCATED_FRAME sequences match the accept-eroded AuthenticatedUnixServer deadline mechanism, and the same mechanism passed an isolated single-variable A/B.
working_tree_status: dirty at 48ade9ab132a327ae7ec58001f87323c786093e9; preserved pre-existing paths remain src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT; the ledger is the only task-owned source-tree change.
owned_processes: NONE; the causal A/B used only local Unix sockets and retired both server threads.
preserved_processes: unrelated tmux sessions and all pre-existing user changes remain untouched.
confirmed_conclusions:
  - OBSERVED: sample_13_far_center received TRUNCATED_FRAME 0.419566 s after first call; its Broker queue timestamp preceded retry, its model completed after the first connection closed, and its identical retry returned the original QUALIFIED result.
  - OBSERVED: sample_15_far_center received TRUNCATED_FRAME 3.031760 s after first call; its Broker queue and model-completion timestamps both preceded the first connection close, and its identical retry returned the original QUALIFIED result in 0.519415 s.
  - OBSERVED: runtime request_deadline_s was 5 s, Worker client deadline was 240 s, both requests retained the same request/idempotency identity, Broker generation remained 1, and both points passed.
  - INFERRED: AuthenticatedUnixServer.serve_once consumed approximately 4.580434 s and 1.968240 s in its pre-request accept phase, respectively. Exhausting the shared receive/handler/reply remainder closed each connection without a reply, which receive_frame surfaced as TRUNCATED_FRAME.
  - INFERRED: the authority's idempotency lock/cache made each retry a replay of the original mutation/result rather than a second logical inference.
  - CONFIRMED MECHANISM: with handler duration fixed at 0.1 s and server deadline fixed at 0.5 s, adding 0.45 s accept idle reproduced TRUNCATED_FRAME and successful same-message replay with one handler call; zero accept idle succeeded directly.
disproven_routes:
  - These two errors are client-side 240 s receive timeouts; each occurred in less than 3.032 s.
  - These two errors are ordinary application Broker queue timeouts; neither crossed the 10 s queue deadline, and the connection loss is explained at the transport server-cycle boundary.
open_risks:
  - The live instrumentation does not distinguish the final serve_once sub-branch for sample_15 (handler wait expiry versus the immediately following no-reply check), though both branches share the same accept-eroded cycle deadline.
  - The production deadline behavior remains unchanged because this dispatch authorizes attribution only, not a fix.
next_command: NONE; a production fix requires a separate explicitly authorized RED/GREEN change.
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8d1
  - all earlier evidence under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
archived_runs: []
deletion_candidates:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/truncated-frame-causal-repro/accept-idle-eroded; invalid sandbox-denied setup, retained
  - previously recorded scratch and candidate-src deletion candidates remain unchanged
  - none deleted; removal requires explicit user authorization
```

## CP-009 — Current timeout versus 5 s W8 tail latency

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-006
current_hypothesis: NONE; raw monotonic timestamp reduction confirms both requested 5 s views.
working_tree_status: dirty at 48ade9ab132a327ae7ec58001f87323c786093e9; preserved pre-existing paths remain src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT; the ledger is the only task-owned source-tree change.
owned_processes: NONE; this supplemental calculation used retained reduction artifacts and started no runtime process or stack.
preserved_processes: all pre-existing user changes and unrelated state remain untouched.
confirmed_conclusions:
  - OBSERVED: the EXP-006 runtime config sets executing_hard_timeout_s to 240.0, which the Worker passes to the dynamic consumer as pose_receive_timeout_s; get_one reached at most 8.040159 s, so 0/20 crossed the configured timeout.
  - OBSERVED: strict comparison to the separate 5.0 s target found 5/20 get_one-start-to-POSE_ACCEPTED exceedances: sample_08_mid_right, sample_09_mid_left, sample_11_mid_right, sample_14_far_right, and sample_15_far_center.
  - OBSERVED: strict comparison to the same target from consumer READY found 4/20 exceedances: sample_08_mid_right, sample_11_mid_right, sample_14_far_right, and sample_15_far_center; sample_09_mid_left measured 2.601030 s and is excluded.
  - OBSERVED: direct subtraction of the raw monotonic-nanosecond ranges reproduced both existing reduced metrics with zero-nanosecond difference across all 20 attempts.
  - CONCLUSION: EXP-006 has no current-configuration consumer timeout, but its W8 tail-latency result misses the user-targeted 5 s SLO at 25% by the get_one-start view and 20% by the READY view.
open_risks:
  - The 5 s target is an evaluation SLO, not an enforced runtime timeout in EXP-006; this checkpoint changes no configuration or production behavior.
next_command: NONE; no performance fix or configuration change is authorized by this supplemental accounting request.
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8d1
  - all earlier evidence under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
archived_runs: []
deletion_candidates:
  - all previously recorded scratch, candidate-src, and invalid causal-reproduction candidates remain unchanged
  - none deleted; removal requires explicit user authorization
```

## CP-010 — Broker concurrency implementation baseline

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-006
current_hypothesis: Resetting the request deadline after accept, allowing eight bounded Broker connections, and executing YOLO through two independent detector instances will eliminate transport truncation and reduce W8 tail latency while preserving at-most-once replay and all physical acceptance gates.
working_tree_status: dirty at 48ade9ab132a327ae7ec58001f87323c786093e9; task-owned ledger plus preserved pre-existing src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT.
owned_processes: NONE; no Task 15 runtime has started.
preserved_processes: NONE observed; unrelated future processes remain out of scope.
confirmed_conclusions:
  - EXP-006 and its A/B confirm the accept-idle request-deadline defect; the current 5 s server cycle begins before blocking accept and may close without a reply.
  - EXP-005 selects C2 as the conservative initial production inference parallelism; C4 remains conditional on a 20/20 C2 run whose READY-to-POSE_ACCEPTED p95 is still at least 5 s.
  - Current consumer get_one hard timeout remains 240 s, while 5 s remains a reporting SLO rather than a hard timeout.
  - The current checkout is a linked worktree on codex/parallel-adaptive-worker-pool at 48ade9ab132a327ae7ec58001f87323c786093e9; submodule c16b5a5fe880b6e1857f56486dab4ae726576969 is unchanged.
  - Elevated read-only preflight found no matching SO-101 stack process, no ROS nodes on Domains 0 or 215 through 222, no Docker container, no GPU compute application, and no tmux session.
disproven_routes:
  - Increasing YOLO directly to C4 before the C2 W8 result is not authorized by the selected single-variable sequence.
  - Turning the 5 s performance objective into a hard timeout is outside the approved design.
open_risks:
  - The concurrency spec and plan paths named inside the plan do not exist in the checkout; the dispatch-designated design.md and implementation-plan.md under the Task 15 evidence handoff are authoritative and fully read.
  - Production build, image, eight-client microbenchmark, fixed-W8 correctness, tail latency, adaptive fallback, and visual acceptance remain unverified.
next_command: Add the Task 2 deterministic accept-idle and handler-timeout tests, then run the focused RED with a fresh verified NVMe scratch.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/preflight.md
retained_runs:
  - all existing evidence under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
archived_runs: []
deletion_candidates:
  - all previously recorded candidates remain retained; none deleted
```

## EXP-007 — Eight-client production Broker C2 microbenchmark

```yaml
experiment_id: EXP-007
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-14T22:49:31+08:00
  - status: RUNNING
    at: 2026-09-14T22:51:20+08:00
  - status: INVALID
    at: 2026-09-14T22:53:53+08:00
prior_experiment: EXP-006
hypothesis: The committed production Broker with eight bounded authenticated connection handlers, queue capacity eight, and two independent YOLO executors will overlap eight simultaneous requests without transport truncation or duplicate logical inference.
single_variable: Exercise the new production Broker concurrency path at C2; model bytes, image, thresholds, production-sized RGB input, queue capacity, request identity rules, and deadline policy remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - Source commit is 3677e9d97f1367f861496817cee5edeb4349871f and the rebuilt overlay resolves so101_demo_py from /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool.
  - Immutable image is sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1 with source and verified source SHA256 148f22e6e1ba6aaf7b99d0fe97d42d141cacd77f8f1928dda8233f0459006006.
  - Frozen YOLO and Grounded-SAM CUDA smoke returned QUALIFIED and post-smoke Docker/GPU probes were empty.
  - Runtime root /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e007 and EXP-007 output paths do not exist before launch.
method:
  - Start one production Broker container with connection_handler_count=8, queue_capacity_per_model=8, yolo_executor_count=2, grounded_sam_executor_count=1, and request_deadline_s=75.
  - Use eight distinct Worker tokens, bound leases, inference identities, and canonical authenticated RPC messages.
  - Use one identical production-sized 640x480 uint8 RGB source image encoded into eight immutable request paths.
  - Synchronize the eight client threads and the main thread with threading.Barrier(9), then wait for all replies and exact shutdown.
success_criteria:
  - pending_rpc_peak is 8 and queue_depth_peak is greater than 1.
  - YOLO model_active_peak is exactly 2, all eight replies are QUALIFIED, and all clients terminate.
  - logical_inference_count is 8 with every idempotency key represented once; replay_count is zero.
  - transport_errors contains no TRUNCATED_FRAME and no client reports TRUNCATED_FRAME.
  - Broker container, authority server, socket, owned process, and GPU compute cleanup are exact.
failure_criteria:
  - Any wrong outcome, missing reply, duplicate logical inference, model peak other than 2, transport error, or cleanup failure is a valid failed experiment.
invalid_criteria:
  - Barrier synchronization does not form, source/image/model identity drifts, evidence is incomplete or overwritten, runtime root pre-exists, or cleanup cannot be proven.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp007-eight-client-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e007
retention_rule: Retain the report, command log, Broker log, runtime root, provenance, and cleanup evidence; delete nothing without explicit user authorization.
observed:
  - The threading.Barrier(9) synchronization formed and Broker pending_rpc_peak reached 8 with eight authenticated connection owners and zero transport errors.
  - All eight requests were rejected before submission with START_EVENT_NOT_AUTHORIZED, so queue_depth_peak was 0, model_active_peak was empty, and there were zero inference replies.
  - The harness keyed its authorization cache by outer RPC request_id while authorize_inference correctly supplied the nested InferenceRequest.request_id. This is a harness identity mismatch, not a product rejection or concurrency measurement.
  - SIGINT shutdown emitted the bounded Broker summary; authority and perception sockets were removed, the labeled container exited, and Docker/GPU post-probes were empty.
conclusion: INVALID; barrier and pending-RPC evidence are real, but no request reached the model queue, so EXP-007 cannot qualify C2 concurrency.
decision: REPEAT_WITH_CORRECT_NESTED_REQUEST_ID
```

## EXP-007R2 — Corrected eight-client production Broker C2 microbenchmark

```yaml
experiment_id: EXP-007R2
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-14T22:53:53+08:00
  - status: RUNNING
    at: 2026-09-14T22:54:27+08:00
  - status: VALID
    at: 2026-09-14T22:55:36+08:00
prior_experiment: EXP-007
hypothesis: Correctly binding authority to the nested InferenceRequest.request_id will allow the otherwise unchanged eight authenticated requests to reach the C2 production queue and satisfy the preregistered concurrency criteria.
single_variable: Correct only the harness authorization-cache key from outer RPC request_id to nested inference request_id; retain commit, image, models, input, C2, queue eight, deadlines, Barrier(9), and cleanup method.
lifecycle: ISOLATED_STACK
success_criteria:
  - pending_rpc_peak is 8, queue_depth_peak is greater than 1, and YOLO model_active_peak is exactly 2.
  - Eight distinct authenticated requests return QUALIFIED with candidates; logical_inference_count is 8, replay_count is 0, and TRUNCATED_FRAME is absent.
  - All clients, Broker container, authority thread, sockets, and GPU compute state clean up exactly.
invalid_criteria:
  - The corrected identity is not exercised, barrier synchronization does not form, provenance drifts, output pre-exists, or cleanup evidence is incomplete.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp007r2-eight-client-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e7r2
retention_rule: Retain both the invalid first run and corrected repeat; delete nothing without explicit user authorization.
observed:
  - The corrected threading.Barrier(9) formed. All eight distinct authenticated connections were accepted within 0.011 s and pending_rpc_peak was exactly 8.
  - queue_depth_peak was 5 and plastic-cup-yolo11n-seg-v1 model_active_peak was exactly 2; executor indices 0 and 1 both started real requests.
  - All eight replies were QUALIFIED with one candidate each. Client round trips ranged from 0.193664 s to 0.415059 s.
  - logical_inference_count was 8 with exact keys idem-01 through idem-08, replay_count was 0, transport_errors was empty, and no client reported TRUNCATED_FRAME.
  - All client threads and the authority thread terminated. SIGINT triggered Broker finally cleanup and its bounded summary before the wrapper reported the expected container exit 130 as return code 1; both Unix sockets were absent afterward, and exact labeled-container and GPU-compute probes were empty.
  - The committed image identity remained sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1 with source SHA256 148f22e6e1ba6aaf7b99d0fe97d42d141cacd77f8f1928dda8233f0459006006. Input shape was 480x640x3 and all eight immutable NPY inputs had SHA256 2b23b7df49c28c5178896675a2e30e83f903f6cef20879990a1864509c4709fe.
conclusion: VALID; the production Broker demonstrates eight simultaneous authenticated RPCs, a nontrivial queue, exactly C2 YOLO execution, eight successful replies, at-most-once logical inference, zero transport truncation, and exact cleanup.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp007r2-eight-client-c2/report.json; SHA256 e1d201c2be062566bacf077cc585b8d2127d948feca92c05e437d905df0b69fc
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp007r2-eight-client-c2/broker.log; SHA256 18841cd941b003571bcc263db1781b8c1f4c663ed5786b48fd5a1893742a219c
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp007r2-eight-client-c2/run-admission.json; SHA256 e8dbc37b3ab63a52f091bf96d27e118f2555d5700f6be103cfd97ac09e6df558
decision: KEEP_AND_PROCEED_TO_EXP-008
```

## CP-011 — Package, image and production C2 admission

```yaml
checkpoint_id: CP-011
last_valid_experiment: EXP-007R2
current_hypothesis: A fixed no-fallback W8 run on the admitted C2 Broker will retain 20/20 correctness, eliminate TRUNCATED_FRAME, and reduce READY-to-POSE_ACCEPTED p95 below 5 seconds.
working_tree_status: committed executable source at 3677e9d97f1367f861496817cee5edeb4349871f; task ledger plus preserved pre-existing src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT remain modified/untracked.
confirmed_conclusions:
  - The fresh so101_demo_py overlay build passed in 2 seconds and installed parallel_ipc.py is byte-identical to source SHA256 3dbf8b07d83bc69965789a8fbbd4161811f65c0bc56163de09bc542e1fb86916.
  - The complete ordinary package collection reached 3034 tests; 3033 passed and the sole failure is the task-external uncommitted transient-/proc-retry test in the preserved user file. The committed Broker-authority test-double correction passed independently.
  - Rebuilt immutable image sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1 binds source SHA256 148f22e6e1ba6aaf7b99d0fe97d42d141cacd77f8f1928dda8233f0459006006; frozen YOLO and Grounded-SAM CUDA smokes both returned QUALIFIED and cleaned exactly.
  - EXP-007R2 satisfies every production C2 microbenchmark criterion. EXP-007 is retained INVALID because its harness cached the wrong request identity and submitted no model work.
open_risks:
  - The literal full ordinary package gate cannot be marked all-green while the preserved, task-external uncommitted test expects an unrelated /proc retry behavior absent from committed source; this dispatch does not modify or include that user file.
  - Fixed-W8 physical correctness, latency, visual agreement and normal fallback-enabled regression remain unverified on the new image.
next_command: Pre-register EXP-008 fixed W8 C2, run clean-stack preflight, and execute the existing supervised adaptive batch wrapper once with fallback disabled.
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp007-eight-client-c2 as INVALID harness evidence
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp007r2-eight-client-c2 as VALID
  - image-build, image-smoke, reports, and all scratch evidence under the registered root
archived_runs: []
deletion_candidates:
  - scratch/t15pkg1, scratch/t15p2, scratch/t15p3 and scratch/t15d4 are invalid environment/hang diagnostics
  - scratch/t15p4 is the 3033/3034 full gate; scratch/t15b1 and scratch/t15g22 are valid build/focused gates
  - image-build/source and image-build/source.tar are clean committed-source build context candidates after readback
  - none deleted; explicit user authorization is required
```

## EXP-008 — Fixed-W8 no-fallback C2 execute regression

```yaml
experiment_id: EXP-008
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-14T22:57:58+08:00
  - status: RUNNING
    at: 2026-09-14T23:04:02+08:00
  - status: INVALID
    at: 2026-09-14T23:05:09+08:00
prior_experiment: EXP-007R2
hypothesis: The admitted C2 production Broker will preserve all twenty fixed-W8 physical outcomes, eliminate the accept-idle TRUNCATED_FRAME defect, and reduce READY-to-POSE_ACCEPTED p95 below the separate 5 second SLO.
single_variable: Replace the EXP-006 serialized/accept-eroded Broker with committed post-fix source and C2 YOLO execution; preserve fixed W8, no fallback, YOLO-only successful path, catalog order, initial state contract, model bytes, geometry, motion policy, configured hard timeouts, and measurement instrumentation.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-007R2 is VALID and immutable image sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1 is source-qualified.
  - Runtime root /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8c2 and EXP-008 output paths are absent before launch.
  - Domains 215 through 222, task-owned processes, Docker containers and GPU compute applications are empty immediately before execution.
  - The task is headless EGL MuJoCo; fresh sealed initial/terminal RGB images plus numeric physical state are the applicable visual evidence, not a fabricated GUI-window capture.
method:
  - Use scripts/run_so101_adaptive_batch.zsh with adaptive worker_count=8, yolo_executor_count=2, the same twenty-point catalog, execute mode, and the EXP-006 measurement-only sitecustomize probe that freezes fallback_worker_counts to empty.
  - Preserve complete stdout/stderr, append-only journal, manifests, per-point sealed evidence, host/GPU samples, event timelines, aggregate result, exit code and post-cleanup probes.
success_criteria:
  - Exactly level W8 runs, all 20 points are PASSED, command exits zero, and no infrastructure retry or fallback generation occurs.
  - All accepted perception results are plastic-cup-yolo11n-seg-v1; Grounded-SAM invocation count is zero and fallback is not injected.
  - TRUNCATED_FRAME count is zero, Broker cleanup is complete, and Domains 215 through 222, owned processes, containers, sockets and GPU compute applications are empty afterward.
  - Every point passes initial gate, POSE_ACCEPTED, MoveIt plan/execute, controller/joint/TF, MuJoCo cup/support/contact, empty final attachment, sealed-hash, and fresh initial/terminal RGB checks.
  - READY-to-POSE_ACCEPTED p95 is less than 5 seconds; report median, p95, max and every strict over-5-second point. Separately report get_one-start-to-POSE_ACCEPTED and retain the configured 240-second timeout distinction.
failure_criteria:
  - Correctness below 20/20, any transport truncation, unexpected fallback/model, physical/evidence mismatch, incomplete cleanup, or READY-to-POSE_ACCEPTED p95 at least 5 seconds is a valid functional or performance failure.
invalid_criteria:
  - Provenance/config/catalog drift, conflicting stack, overwritten destination, missing timing/evidence layer, non-comparable clock, or cleanup ambiguity makes the run INVALID.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8c2
retention_rule: Retain all runtime, visual, numeric, timeline, resource, log, manifest and cleanup evidence; delete nothing without explicit user authorization.
observed:
  - live-01 exited 1 at preflight with PROVENANCE_SOURCE_DIRTY before a runtime root could be accepted; it is INVALID and is retained outside the correctness denominator.
  - live-02 exited 1 at preflight with PROVENANCE_CONSOLE_CONTENT before a runtime root could be accepted; it is INVALID and is retained outside the correctness denominator.
  - live-03 registered eight Workers but granted zero leases; its aggregate retained all twenty points as UNRUN with zero attempts.
  - The batch wrapper and all Worker process trees disappeared without a batch exit-code file while the detached Broker container survived.
  - At 2026-09-14T23:05:08.144930+08:00 systemd-oomd killed tmux-spawn-67d5b319-bdb4-4cac-999e-4bbf3eaa1049.scope after the user slice exceeded its 50 percent pressure threshold for more than 20 seconds. The victim used 16.2 GiB, reported memory PSI avg10 74.35 percent, and systemd recorded 120 killed processes.
  - The final retained external sampler row had 107 task processes, 8584577024 task RSS bytes, memory PSI some/full avg10 88.63/85.79 percent, IO PSI some/full avg10 87.27/83.84 percent, and a repeated nvidia-smi timeout.
  - Independent recovery read-back found exact labeled-container count zero, matching owned-process count zero, AF_UNIX socket count zero, GPU compute rows zero, and ROS Domains 0 and 215 through 222 empty. The removed container and socket nodes are not recreated; all regular evidence remains retained.
inferred:
  - The controller-spawner lock warnings occurred during the same pressure interval but are symptoms, not the confirmed cause of task loss.
conclusion: INVALID; the run never executed a point and was externally terminated by the confirmed systemd-oomd scope kill, so it is neither a product failure nor a performance sample.
decision: REPEAT_FROM_NEW_SCOPE_AND_ROOT
```

## CP-012 — EXP-008 OOM recovery and isolated-runner rerun boundary

```yaml
checkpoint_id: CP-012
last_valid_experiment: EXP-007R2
current_hypothesis: A fresh fixed-W8 C2 no-fallback run in a separate runner scope can form the READY barrier and complete without placing this Codex observer in the oomd victim scope; otherwise W6 is the approved lightweight retry.
working_tree_status: committed implementation at 3677e9d97f1367f861496817cee5edeb4349871f; task-owned ledger plus preserved pre-existing src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT remain dirty.
owned_processes: NONE from EXP-008; exact labeled-container, owned-process, AF_UNIX socket, GPU-compute and ROS-domain read-backs are empty.
preserved_processes: tmux sessions codex and codex-task-so101-adaptive-worker-pool-recovery plus unrelated user processes and stopped containers remain untouched.
confirmed_conclusions:
  - EXP-008 live-01 and live-02 are INVALID preflight-only attempts and live-03 is INVALID due to the confirmed systemd-oomd scope kill before the first lease.
  - EXP-007R2 remains the last valid experiment and qualifies W8 connections with C2 production inference.
  - The current checkout is the required linked worktree on codex/parallel-adaptive-worker-pool at 3677e9d97f1367f861496817cee5edeb4349871f with submodule c16b5a5fe880b6e1857f56486dab4ae726576969 unchanged.
disproven_routes:
  - Treating live-03 as a normal Codex exit, product failure, point failure, or controller-lock root cause is contradicted by the host journal and zero-lease aggregate.
  - Reusing the w8c2 runtime root or exp008-w8-c2 output paths is prohibited because those paths are retained evidence.
open_risks:
  - A fixed W8 stack may still cross the user-slice pressure threshold even when isolated into its own runner scope.
  - Another unrelated Codex task is present but currently owns no SO-101 stack, Docker container, GPU compute process, or ROS node; it must remain untouched.
next_command: Launch EXP-008R2 once at fixed W8/C2 from a fresh evidence subdirectory and runtime root inside a uniquely named runner tmux/systemd user scope while this Codex task monitors externally.
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2 as INVALID with live-01, live-02 and live-03 retained
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8c2 as INVALID runtime evidence
  - all earlier evidence under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
archived_runs: []
deletion_candidates:
  - all previously recorded candidates remain retained; none deleted
```

## EXP-008R2 — Fixed-W8 no-fallback C2 execute rerun in isolated runner scope

```yaml
experiment_id: EXP-008R2
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-14T23:19:30+08:00
  - status: RUNNING
    at: 2026-09-14T23:28:38+08:00
  - status: INVALID
    at: 2026-09-14T23:28:39+08:00
prior_experiment: EXP-008
hypothesis: The admitted C2 production Broker can complete the unchanged fixed-W8 twenty-point qualification when the batch runs in a dedicated runner scope and is observed by an external bounded monitor.
prediction: W8 forms its READY barrier, dynamically leases all twenty points across available Workers, completes 20/20 with zero TRUNCATED_FRAME and complete physical/evidence gates, and leaves exact cleanup; if the scope is killed or cannot safely reach readiness, the run is INVALID and qualification retries at W6 from another new root.
single_variable: Isolate the otherwise unchanged fixed-W8/C2/no-fallback qualification in a separate uniquely named runner tmux/systemd user scope with an external bounded resource monitor; source, image, models, catalog, geometry, motion policy, deadlines and acceptance gates remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - Source commit is 3677e9d97f1367f861496817cee5edeb4349871f and immutable Broker image is sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1.
  - New evidence subdirectory, runtime root, batch identity and runner session/scope do not exist before launch.
  - Domains 215 through 222, matching task-owned processes, matching containers, AF_UNIX sockets and GPU compute applications are empty immediately before launch.
  - Host memory/IO PSI, task RSS/process count, Docker/GPU state and runner exit state are captured by the external observer.
success_criteria:
  - Exactly W8 runs, all 20 points are PASSED, command exits zero, no infrastructure retry or fallback generation occurs, and every required correctness/visual layer is complete.
  - All accepted perception results are plastic-cup-yolo11n-seg-v1, Grounded-SAM invocation count is zero, TRUNCATED_FRAME count is zero, and actual YOLO concurrency is reported.
  - READY-to-POSE_ACCEPTED median/p95/max and strict-over-5-second points are reported separately from get_one-start timing and the configured 240-second hard timeout.
  - Exact owned cleanup is proven after read-back.
failure_criteria:
  - A fully valid run with correctness below 20/20, transport truncation, model/fallback drift, physical/evidence mismatch, incomplete cleanup, or p95 at least 5 seconds is a functional or performance failure.
invalid_criteria:
  - Failure to form a READY barrier, systemd-oomd scope kill, provenance/config/catalog drift, conflicting stack, missing timing/evidence, or cleanup ambiguity makes the W8 run INVALID and triggers a fresh W6 retry.
provenance:
  source_commit: 3677e9d97f1367f861496817cee5edeb4349871f
  install_overlay: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/candidate-src/install
  runtime_executable: /usr/bin/python3 plus immutable Broker image sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1
  ros_domain_id: [215, 216, 217, 218, 219, 220, 221, 222]
  gz_partition: not_applicable
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r2-w8-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8c2r2
corrections:
  - at: 2026-09-14T23:25:35+08:00
    reason: The production wrapper requires a 1-5 character batch ID and derives the runtime-root leaf from that ID; the six-character illustrative leaf w8c2r2 cannot pass the unchanged wrapper contract.
    correction: Use fresh batch ID e8r2a and runtime root /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e8r2a. This is an identity-only correction; fixed W8, C2, no fallback, models, catalog, geometry, timeouts and acceptance gates remain frozen.
commands:
  - command: systemd-run --user --unit=so101-exp008r2-monitor.service --collect /tmp/so101-exp008r2-monitor.zsh
    exit_code: 0
  - command: systemd-run --user --unit=so101-exp008r2-runner.service --collect /tmp/so101-exp008r2-holder.zsh
    exit_code: 0
  - command: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/candidate-src/scripts/run_so101_adaptive_batch.zsh --adaptive-workers --points /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/candidate-src/src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml --config /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/candidate-src/src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --adaptive-config /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/candidate-src/src/so101_demo_py/config/mujoco/parallel_adaptive_workers_v1.yaml --batch-id e8r2a --evidence-root /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01 --worker-count 8 --initial-points-per-worker 3 --worker-start-timeout-s 120 --max-infra-attempts-per-point 5 --yolo-executor-count 2 --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --yolo-weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --run-mode execute
    exit_code: 127
observed:
  - The first orchestration command stopped before systemd-run because of an extraneous shell token; read-back proved no unit, tmux server, runtime root, container or batch process existed, so it was retained as preflight harness evidence only.
  - The sealed repeat created monitor invocation 45cb5f220fa74e21aa6648eb27799cae and runner invocation 685520b35456478eb87c93429e831686. The tmux session started, but the wrapper immediately reported `command not found: so101_parallel_batch` and `command not found: so101_parallel_batch_cleanup` because sourcing the isolated overlay did not add its package libexec directory to PATH.
  - Batch exit code was 127; runtime root /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e8r2a never existed, no container or ROS stack started, and no point was leased or executed.
  - Exact-command serialization incorrectly quoted the whole argv as one aggregate string; this affects only the evidence rendering, not the argv actually passed by the shell array.
conclusion: INVALID preflight harness attempt; it supplies no W8 product correctness or performance sample and does not trigger the W6 policy.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r2-w8-c2/run.log
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r2-w8-c2/external-monitor.jsonl
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r2-w8-c2/external-monitor-final.txt
decision: REPEAT_W8_WITH_CORRECT_RUNNER_PATH
next_experiment: EXP-008R3-W8
```

## CP-013 — EXP-008R2 preflight harness invalidation

```yaml
checkpoint_id: CP-013
last_valid_experiment: EXP-007R2
current_hypothesis: The unchanged fixed-W8 C2 no-fallback configuration remains untested; adding the immutable overlay package libexec directory to the isolated runner PATH will exercise the intended production command.
working_tree_status: committed implementation at 3677e9d97f1367f861496817cee5edeb4349871f; task-owned ledger plus preserved pre-existing src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT remain dirty.
owned_processes: NONE from EXP-008R2; runner tmux ended and its runtime root was never created.
preserved_processes: tmux sessions codex and codex-task-so101-adaptive-worker-pool-recovery plus unrelated processes remain untouched.
confirmed_conclusions:
  - EXP-008R2 is INVALID preflight-only evidence because the wrapper could not resolve its two console scripts; it contains no point attempt and no W8 behavior sample.
  - The dedicated monitor observed the runner unit enter and leave its own cgroup while host PSI stayed low and Docker/GPU evidence remained empty.
disproven_routes:
  - Sourcing candidate-src/install/setup.zsh alone does not make so101_parallel_batch or so101_parallel_batch_cleanup executable by direct name in this noninteractive systemd/tmux runner.
open_risks:
  - Fixed W8 may still be killed by systemd-oomd after corrected preflight reaches stack startup.
next_command: Pre-register and launch EXP-008R3-W8 from entirely new experiment, runtime, batch, tmux and systemd identities after proving both console scripts, exact argv serialization and clean host ownership.
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r2-w8-c2 as INVALID preflight harness evidence
archived_runs: []
deletion_candidates:
  - EXP-008R2 copied runner/monitor scripts and preflight logs; none deleted and explicit authorization is required.
```

## EXP-008R3-W8 — Corrected isolated-runner fixed-W8 no-fallback C2 qualification

```yaml
experiment_id: EXP-008R3-W8
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-14T23:31:00+08:00
  - status: RUNNING
    at: 2026-09-14T23:32:19+08:00
  - status: INVALID
    at: 2026-09-14T23:32:21+08:00
prior_experiment: EXP-008R2
hypothesis: The admitted C2 Broker can complete the frozen fixed-W8 twenty-point qualification when the fresh isolated runner resolves the immutable overlay console scripts and retains the external monitor.
prediction: Both production console scripts resolve before launch, the W8 READY barrier forms, all twenty points are dynamically leased and pass, TRUNCATED_FRAME is zero, and cleanup is exact; inability to form READY or an oomd kill makes this run INVALID and triggers fresh W6.
single_variable: Correct the runner PATH and exact-command evidence serialization; fixed W8, C2, no fallback, source, image, models, catalog, geometry, motion policy, deadlines and acceptance gates remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - Source commit, overlay, image and model hashes equal EXP-008R2; both production console scripts resolve from the immutable candidate overlay.
  - Fresh experiment root, runtime root, batch identity, tmux server/session and systemd units are absent; Domains 0 and 215-222, task processes, matching containers, sockets and GPU compute rows are empty.
success_criteria:
  - Exactly W8 runs, all 20 points pass, exit code is zero, no fallback generation occurs, YOLO is the only accepted model, TRUNCATED_FRAME is zero, every correctness/visual layer passes, timings are complete and cleanup is exact.
failure_criteria:
  - A valid full run has fewer than 20 passed points, any transport/model/evidence/correctness mismatch, incomplete cleanup, or READY-to-POSE_ACCEPTED p95 at least 5 seconds.
invalid_criteria:
  - Failure to form READY, oomd kill, provenance/config/catalog drift, preflight failure, conflicting stack, missing evidence or cleanup ambiguity.
provenance:
  source_commit: 3677e9d97f1367f861496817cee5edeb4349871f
  install_overlay: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/candidate-src/install
  runtime_executable: immutable overlay console scripts plus Broker image sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1
  ros_domain_id: [215, 216, 217, 218, 219, 220, 221, 222]
  gz_partition: not_applicable
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r3-w8-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e8r3w
commands:
  - command: systemd-run --user --unit=so101-exp008r3-w8-monitor.service --collect /tmp/so101-exp008r2-monitor.zsh
    exit_code: 0
  - command: systemd-run --user --unit=so101-exp008r3-w8-runner.service --collect /tmp/so101-exp008r2-holder.zsh
    exit_code: 0
  - command: exact production command is retained in exp008r3-w8-c2/exact-command.txt with batch e8r3w, fixed worker-count 8, C2 and no fallback.
    exit_code: 1
observed:
  - Clean host preflight proved both overlay console scripts, immutable source/image/model identities, empty task processes/containers/GPU/ROS Domains, fresh identities and low PSI before launch.
  - The command reached AdaptiveBatchRunner and wrote BATCH_MANIFEST plus POOL_STARTING, but ProductionBatchComposition failed before creating p/g01w08 or any Worker/container; elapsed time was 0.045517 s, all twenty points were startup-interrupted, no point was leased or executed, and aggregate status was INFRA_FAILED.
  - Cleanup then emitted POOL_ROOT because the active POOL_STARTING journal had no pool directory; this was a secondary symptom. Exact post-readback found zero owned processes, containers, sockets, persistent claims, GPU rows and ROS nodes on Domains 0 and 215-222.
  - The retained working EXP-008 launcher sourced ROS, the worktree overlay, then the immutable candidate overlay and explicitly added candidate site-packages/build paths; EXP-008R3 omitted the worktree overlay and those Python paths. This environment drift is the first bad boundary.
conclusion: INVALID startup contamination before READY; it is not a point or W8 product failure, but the approved single fresh W8 retry is exhausted and the lightweight policy now selects fresh W6.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r3-w8-c2/preflight.txt
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r3-w8-c2/cleanup-readback.txt SHA256 3b94907a7bd9fb8acf4345a0192baf923c6568c7d4b8a5f6c85272739c4da506
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e8r3w/aggregate_results.json SHA256 e08a7f87c84784295057c7e4716222a93d68031aa73cd481500c4e694d8263a8
decision: RETAIN_INVALID_AND_RETRY_W6
next_experiment: EXP-008R4-W6
```

## CP-014 — Fixed-W8 retry exhausted; fresh W6 boundary

```yaml
checkpoint_id: CP-014
last_valid_experiment: EXP-007R2
current_hypothesis: A fresh fixed-W6 C2 no-fallback run using the original ROS/worktree/candidate overlay ordering can remain executable and dynamically complete the same twenty-point qualification.
working_tree_status: implementation remains 3677e9d97f1367f861496817cee5edeb4349871f; only the task ledger plus preserved src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT are dirty.
owned_processes: NONE; EXP-008R3 exact process/container/socket/claim/GPU/ROS read-back is empty.
preserved_processes: tmux sessions codex and codex-task-so101-adaptive-worker-pool-recovery plus unrelated user state remain untouched.
confirmed_conclusions:
  - The W8 rerun did not form READY and is INVALID startup contamination, so it is excluded from point correctness and performance denominators.
  - The fixed-W8 retry allowance is exhausted; W6 is now required by the approved OOM recovery policy, with no W1 fallback unless W6 independently proves unable.
disproven_routes:
  - Candidate-only environment setup is not comparable to the retained working launcher and cannot qualify the runtime.
open_risks:
  - W6 may still cross host pressure limits or expose another startup issue after the full overlay ordering is restored.
next_command: Pre-register EXP-008R4-W6, validate the W6-only no-fallback timing shim and full two-overlay environment, then launch in fresh tmux/systemd identities with an external bounded monitor.
retained_runs:
  - exp008-w8-c2, exp008r2-w8-c2 and exp008r3-w8-c2 plus runtime roots w8c2 and e8r3w remain retained.
archived_runs: []
deletion_candidates:
  - EXP-008R2 and EXP-008R3 orchestration scripts and preflight-only runtime evidence; none deleted.
```

## EXP-008R4-W6 — Fixed-W6 no-fallback C2 lightweight qualification

```yaml
experiment_id: EXP-008R4-W6
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-14T23:37:00+08:00
  - status: RUNNING
    at: 2026-09-14T23:39:26+08:00
  - status: INVALID
    at: 2026-09-14T23:39:28+08:00
prior_experiment: EXP-008R3-W8
hypothesis: W6 lowers stack pressure enough to complete the unchanged twenty-point fixed qualification with C2, no model fallback and exact correctness/cleanup evidence.
prediction: Six Workers form READY, dynamically lease all twenty points, complete 20/20, use YOLO only with zero TRUNCATED_FRAME, and clean exactly without an oomd kill.
single_variable: Reduce fixed worker count from W8 to W6 under the approved lightweight recovery; restore the retained launcher's ROS/worktree/candidate overlay order and explicit candidate Python paths. C2, no fallback, source, image, models, catalog, geometry, motion policy, deadlines and gates remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - Fresh experiment/runtime/batch/tmux/systemd identities; clean Domains 0 and 215-220, task ownership, containers, sockets and GPU state.
  - Measurement-only timing shim is copied from EXP-006, changes only the no-fallback expected worker count from 8 to 6, and passes a focused contract smoke before launch.
success_criteria:
  - Exactly W6 runs, all 20 points pass, exit zero, no infrastructure generation fallback, YOLO is the only accepted model, Grounded-SAM count and TRUNCATED_FRAME are zero, all correctness/visual/timing evidence is complete, and cleanup is exact.
failure_criteria:
  - A valid run has fewer than 20 passed points, any transport/model/physical/evidence mismatch, incomplete cleanup, or unsafe Broker health.
invalid_criteria:
  - Failure to form READY, oomd kill, provenance/config/catalog drift, conflicting stack, missing evidence or cleanup ambiguity.
provenance:
  source_commit: 3677e9d97f1367f861496817cee5edeb4349871f
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install followed by immutable candidate overlay /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/candidate-src/install
  runtime_executable: immutable candidate console plus Broker image sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1
  ros_domain_id: [215, 216, 217, 218, 219, 220]
  gz_partition: not_applicable
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r4-w6-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e8r4w
commands:
  - command: Exact fixed-W6/C2/no-fallback production argv is retained in exp008r4-w6-c2/exact-command.txt under runner unit so101-exp008r4-w6-runner.service and tmux server/session so101-exp008r4-w6/exp008r4-w6-runner.
    exit_code: 1
observed:
  - The evidence-only W6 shim passed a focused RED/GREEN: the unchanged EXP-006 probe rejected W6, while the one-line worker-count adaptation produced worker_count 6 with fallback_worker_counts empty.
  - The corrected two-overlay launch reached BATCH_MANIFEST and POOL_STARTING but stopped in 0.032688 s before p/g01w06, Worker, Broker container, READY or any point execution; cleanup's POOL_ROOT was secondary.
  - A constructor-only diagnostic exposed the swallowed first exception as ResourceAllocationError ROS_DOMAIN_UNCLEAN: 215. Claims 215-222 still contained ACTIVE state for invalid OOM batch w8c2-g01-w08 even though its processes, container, sockets, GPU rows and ROS graph were empty.
  - The first production cleanup attempt correctly failed ROS_DOMAIN_ACTIVE because prior read-only `ros2 node list` probes had started exact daemon PIDs 713736 and 713845-714217. After task-owned `ros2 daemon stop` calls, the production cleanup succeeded and transitioned exactly claims 215-222 to RELEASED with cleanup_verified true; cleanup receipt SHA256 ec63115e31d29a125707e5fd9ef8a7c3681c49cf180d1964cf89eb2d7b1f97c6.
  - AF_UNIX 106/107/108-byte bind A/B passed at 106 and 107 and failed only at 108, disproving socket length as this startup cause. Restoring the worktree overlay also did not change the failure, disproving the overlay omission as the root cause.
conclusion: INVALID startup contamination caused by stale persistent domain claims from EXP-008; no point ran and W6 capacity remains untested. Because the contaminant is now exactly reconciled, repeat W6 from fresh identities rather than descend to W1.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r4-w6-c2/constructor-diagnostic-r2.log
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r4-w6-c2/stale-claim-cleanup-r2.log SHA256 74febf19874dea37bb5f3e67556a86f8a1d20461009f55777c2a986d70a99356
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8c2/cleanup-receipt.json SHA256 ec63115e31d29a125707e5fd9ef8a7c3681c49cf180d1964cf89eb2d7b1f97c6
decision: REPEAT_W6_AFTER_EXACT_CLAIM_RECOVERY
next_experiment: EXP-008R5-W6
```

## CP-015 — Stale persistent claim root cause removed

```yaml
checkpoint_id: CP-015
last_valid_experiment: EXP-007R2
current_hypothesis: With old w8c2 claims now RELEASED and task-created ROS daemons stopped, a fresh fixed-W6 C2/no-fallback run can enter pool construction and form READY.
working_tree_status: implementation remains 3677e9d97f1367f861496817cee5edeb4349871f; task ledger plus preserved test_parallel_batch_resources.py and MUJOCO_LOG.TXT remain dirty.
owned_processes: NONE; exact invalid-run process/container/socket/GPU read-backs are empty and old claims are RELEASED.
preserved_processes: user tmux sessions and unrelated state remain untouched.
confirmed_conclusions:
  - The shared startup root cause was stale persistent claims from the OOM run, not W8/W6 load, overlay order or AF_UNIX length.
  - Production cleanup, rather than hand edits, reconciled all eight exact claims and wrote a verified cleanup receipt.
disproven_routes:
  - W1 is not warranted because W6 has not yet executed after removal of the invariant cleanup contaminant.
open_risks:
  - W6 runtime pressure and physical/timing correctness remain unmeasured.
next_command: Launch fresh EXP-008R5-W6 using four-character batch 84w6, new runtime/output/tmux/systemd identities, full overlays, fixed C2/no-fallback shim and external monitor.
retained_runs:
  - All invalid W8/W6 attempts, both constructor diagnostics and old runtime cleanup evidence remain retained.
archived_runs: []
deletion_candidates:
  - diagnostic runtime roots d84w6 and d84w7 plus invalid startup roots e8r3w and e8r4w; none deleted.
```

## EXP-008R5-W6 — Post-cleanup fixed-W6 no-fallback C2 qualification

```yaml
experiment_id: EXP-008R5-W6
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-14T23:47:00+08:00
  - status: RUNNING
    at: 2026-09-14T23:48:25+08:00
  - status: INVALID
    at: 2026-09-15T00:01:21+08:00
prior_experiment: EXP-008R4-W6
hypothesis: With stale domain claims reconciled, six Workers will form READY and dynamically complete the frozen twenty-point qualification under C2 and no fallback without unsafe host pressure.
prediction: W6 reaches POOL_RUNNING, executes 20/20, uses only YOLO, has zero TRUNCATED_FRAME and exact cleanup; the external monitor remains outside the runner cgroup.
single_variable: Remove the confirmed stale-claim contamination; preserve W6, C2, no fallback, full overlay order, models, catalog, geometry, motion policy, timeouts and gates from EXP-008R4-W6.
lifecycle: ISOLATED_STACK
preconditions:
  - Claims 215-222 are RELEASED with cleanup_verified true; exact task processes, containers, sockets, GPU rows and ROS daemons/nodes are absent.
  - Fresh experiment root exp008r5-w6-c2, runtime /r/84w6, batch 84w6, tmux server/session so101-exp008r5-w6/exp008r5-w6-runner and new systemd units are absent.
success_criteria:
  - Exactly W6 runs and all 20 points pass with exit zero, no infrastructure generation fallback, only YOLO acceptances, zero Grounded-SAM and TRUNCATED_FRAME, full correctness/visual/timing evidence and exact cleanup.
failure_criteria:
  - A valid run has fewer than 20 passes or any transport/model/physical/evidence/cleanup mismatch.
invalid_criteria:
  - READY cannot form, oomd kills the scope, provenance/config/catalog drift, conflicting stack, missing evidence or cleanup ambiguity.
provenance:
  source_commit: 3677e9d97f1367f861496817cee5edeb4349871f
  install_overlay: worktree install followed by immutable candidate install
  runtime_executable: immutable candidate console plus image sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1
  ros_domain_id: [215, 216, 217, 218, 219, 220]
  gz_partition: not_applicable
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r5-w6-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/84w6
commands:
  - command: systemd-run --user --unit=so101-exp008r5-w6-monitor.service --collect /tmp/so101-exp008r2-monitor.zsh
    exit_code: 0
  - command: systemd-run --user --unit=so101-exp008r5-w6-runner.service --collect /tmp/so101-exp008r2-holder.zsh
    exit_code: 0
  - command: Exact production argv is retained in exp008r5-w6-c2/exact-command.txt; it selects batch 84w6, fixed W6, C2, no fallback and execute mode.
    exit_code: 1
observed:
  - Runner holder unit invocation b51e56c7328c40d7bf97850acd21d2ef launched unique tmux server/session so101-exp008r5-w6/exp008r5-w6-runner. The batch pane and descendants are in dedicated scope tmux-spawn-17746413-0e0b-4ea0-ad74-ec725869db3e.scope, outside this Codex cgroup.
  - External monitor unit invocation d59986d120f74b62965a47ca5f6606b5 has PID 738245 and independent cgroup so101-exp008r5-w6-monitor.service; it writes external-monitor.jsonl every five seconds.
  - All six Workers reached READY and W6 stayed executable without oomd; seven sealed points passed before a hard-coded 180 s execute_result deadline contradicted the frozen configured 240 s timeout.
  - Receipt verification then produced infrastructure INDETERMINATE results and first-failure convergence stopped the generation. No TRUNCATED_FRAME or model fallback was observed; exact cleanup released claims 215-220 and left no owned process, container, socket, GPU row or unit.
conclusion: INVALID runtime-harness contamination, not a W6 capacity or point failure. W1 remains unauthorized.
decision: FIX_TIMEOUT_AND_REPEAT_W6
next_experiment: EXP-008R6-W6
```

## CP-017 — Clean W6 unable at frozen 240 s execution boundary

```yaml
checkpoint_id: CP-017
confirmed_conclusions:
  - EXP-008R6-W6 exercised the corrected configured timeout and expired cup_test_forward_5cm at exactly 240.000 s; W6 is therefore unable under the approved handoff, authorizing W1.
  - Cleanup read-back is empty and claims 215-220 are RELEASED; source remains frozen at 167c74a941782e37ed1369ee10c42ac6b77088a9.
next_command: Launch a fresh fixed-W1/C2/no-fallback qualification from new output/runtime/batch/tmux/systemd identities.
```

## EXP-008R7-W1 — Fixed-W1 no-fallback C2 qualification

```yaml
experiment_id: EXP-008R7-W1
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T00:19:30+08:00
  - status: RUNNING
    at: 2026-09-15T00:22:55+08:00
  - status: INVALID
    at: 2026-09-15T00:27:33+08:00
prior_experiment: EXP-008R6-W6
hypothesis: Serial W1 removes inter-worker simulation contention so every frozen point completes within 240 s while preserving C2/no-fallback qualification semantics.
success_criteria: Exactly W1, 20/20 PASSED, YOLO only, zero TRUNCATED_FRAME, complete correctness/visual/timing evidence, and exact cleanup.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r7-w1-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/87w1
source_commit: 167c74a941782e37ed1369ee10c42ac6b77088a9
runner_identity: so101-exp008r7-w1-runner.service invocation ab1cde2a80b84a4c8baf1a444febd938; tmux so101-exp008r7-w1/exp008r7-w1-runner; batch scope tmux-spawn-65405a2b-b594-4d39-b850-f109d6358be3.scope.
monitor_identity: primary PID 797797 and supplemental PID 799740, both outside the runner scope.
observed: W1 formed READY. Its first ATTEMPT_STARTED was coordinator seq17 at monotonic 1222994.724863698 with deadline 1223234.724863698; LEASE_EXPIRED seq263 occurred at that exact 240.000 s boundary and BATCH_STOPPING seq264 followed. The top aggregate exited 1 after 278.05097205680795 s with 1 INDETERMINATE and 19 UNRUN. One YOLO request completed QUALIFIED, no accepted consumer pose existed, and no fallback, Grounded-SAM usage, logical replay/deadline error, TRUNCATED_FRAME or oomd event occurred.
visual: Original-resolution inspection covered the fresh task_start initial/terminal pair (640x480 RGB PNG): both are coherent and noncorrupt, but no placement occurred before expiry. See task-15-w8-broker-concurrency/visual-inspection-r6-r7-r2.txt.
cleanup: Production ownership-scoped cleanup released Domain 215; exact read-back found no owned process, container, socket, GPU row or tmux session and both runner/monitor units were inactive/dead with successful result. Receipt SHA256 ea1efe2f2fc401a9babd20ced1915016b298718e63feb042788e5cb0ec8a982e; read-back SHA256 3a4a3dda4882735efc6c2214f4edf6eabcd90a554de625a4683a18c43175ebf8.
conclusion: INVALID/unable under the approved recovery policy. W1 is the lowest permitted tier, so live fixed qualification stops without a valid 20/20 result.
decision: STOP_FIXED_QUALIFICATION_BLOCKED
```

## CP-018 — Lowest recovery tier unable; Task 10 blocked

```yaml
checkpoint_id: CP-018
last_valid_experiment: EXP-007R2
current_commit: 167c74a941782e37ed1369ee10c42ac6b77088a9
confirmed_conclusions:
  - Corrected W6 and W1 both remained memory-safe and formed READY, but each proved unable at the frozen exact 240.000 s lease boundary; neither result is a valid fixed qualification.
  - C4 is NOT_RUN because the prerequisite valid 20/20 W8/C2 result does not exist. The fallback-enabled normal adaptive regression is NOT_RUN/BLOCKED because fixed qualification did not complete.
  - EXP-008R6 produced 12 diagnostic PASSED, 4 INDETERMINATE and 4 UNRUN; EXP-008R7 produced 1 INDETERMINATE and 19 UNRUN. No startup/OOM contamination was counted as a point failure.
  - Every EXP-008R6/R7 fresh RGB artifact was inspected at original resolution, and ownership-scoped cleanup is exact with claims RELEASED. No evidence was deleted.
working_tree_status: Task-owned ledger is modified; preserved user src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT remain untouched and unstaged.
retained_runs:
  - All EXP-008 through EXP-008R7 output/runtime roots and Task 10 test/monitor/visual/cleanup evidence under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01.
archived_runs: []
deletion_candidates:
  - Invalid preflight/diagnostic roots and pytest scratch trees, retained pending explicit deletion authorization.
next_command: Task 11 consumes task-10-report.md and must preserve the blocked conclusion; no further Task 10 live run is authorized.
```

## CP-019 — Task 11 final gate and blocked qualification handoff

```yaml
checkpoint_id: CP-019
last_valid_experiment: EXP-007R2
source_commit: 167c74a941782e37ed1369ee10c42ac6b77088a9
accepted_w8_overlay: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install
accepted_broker_image: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
accepted_broker_image_digest: sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1
review_acceptance:
  - Task 10 independent review is accepted after its audit correction.
  - Historical stdout for the focused timeout RED and GREEN was not durably captured and is unavailable for independent verification; only the named scratch trees remain.
  - The adjacent runtime suite is independently retained at task-15-w8-broker-concurrency/task10-timeout-adjacent2.log and passed 40 tests.
package_gate:
  command: PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q src/so101_demo_py/test --junitxml="$scratch_root/so101-demo-py.xml"
  runtime_executable: /usr/bin/python3
  scratch_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/t11p2
  tempfile_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/t11p2/tmp
  tempfile_verified: true
  collected: 3035
  passed: 3033
  skipped: 1
  failed: 1
  errors: 0
  warnings: 4
  pytest_elapsed_s: 60.55
  wall_elapsed_s: 61.66
  exit_code: 1
  sole_failure: src/so101_demo_py/test/test_parallel_batch_resources.py::test_transient_unclassified_proc_read_error_is_retried
  scope: src/so101_demo_py/test only; benchmark_test was not collected.
  evidence:
    - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-11-final-gate/task11-package-r3.log SHA256 164c709780f5d3fad2212e9543fee3c644abf2c039119603138498c0a2736776
    - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/t11p2/so101-demo-py.xml SHA256 f8944d606aacac226897259ebac64b22882f49bcdd04348eb51ab52f170a8df3
  conclusion: NOT_ALL_GREEN because the preserved task-external dirty test fails against committed source; no task-owned source regression was observed in the definitive rerun.
invalid_gate_attempts:
  - task-11-package-20260915-0041 collected 3035 tests but produced 58 failures because its descriptive scratch path made generated AF_UNIX paths exceed the platform limit; retained and excluded as INVALID_ENV.
  - t11p1 used a valid short scratch and produced 3032 passed, 1 skipped, and 2 failed; the additional domain-claim concurrency race disappeared in t11p2, matching the same transient previously recorded by Task 9.
outcome_boundaries:
  ipc_defect: FIXED by the accepted accept-idle RED/GREEN implementation evidence and live TRUNCATED_FRAME=0 in EXP-007R2 and the diagnostic EXP-008R6/R7 runs.
  w8_correctness: BLOCKED; no valid 20/20 fixed-W8 run exists after the authorized recovery sequence.
  five_second_slo: BLOCKED; no valid fixed-W8 20/20 READY-to-POSE_ACCEPTED population exists. The diagnostic W6 p95 13.515607094 s is not a substitute.
  selected_yolo_concurrency: C2 from EXP-005 and qualified by EXP-007R2; C4 is NOT_RUN because its valid-W8 trigger was never met.
  adaptive_fallback: NOT_RUN/BLOCKED because the fixed-qualification prerequisite did not complete.
  fixed_run_boundary: EXP-008R6-W6 and EXP-008R7-W1 each reached READY but expired at the exact 240.000 s lease boundary; their point counts remain diagnostic only.
working_tree_status: The ledger is the only Task 11 staged candidate. Preserved user src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT remain untouched and unstaged.
owned_processes: NONE from Task 11; the package gate started no live SO-101 stack.
retained_runs:
  - All EXP-008 through EXP-008R7 output/runtime roots, orchestration logs, monitors, images, aggregate objects, cleanup receipts/read-backs, Task 10 test scratch trees, and the adjacent 40-test log remain under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01.
  - Task 11 preflight, commands, stdout/stderr, elapsed files, exit files, JUnit, hashes, and all three scratch trees remain under the registered root.
archived_runs: []
deletion_candidates:
  - Invalid preflight and diagnostic orchestration roots, generated candidate clones/build trees, all Task 10 pytest scratch trees, and Task 11 scratch/task-11-package-20260915-0041, scratch/t11p1, and scratch/t11p2.
  - No candidate was deleted; explicit user authorization is required before deletion.
open_risks:
  - The required 20/20 fixed-W8 correctness result, fixed-W8 p95 decision, conditional C4 comparison, and normal fallback-enabled adaptive regression remain unavailable.
  - Historical timeout RED/GREEN ordering cannot be independently verified because stdout was not retained.
  - The literal ordinary package gate remains nonzero due only to the preserved user-owned dirty test.
next_command: NONE; Task 11 is finalized with blocked qualification boundaries. No push, merge, evidence deletion, or further live run is authorized.
```

## EXP-009 — Post-review plan-only READY boundary regression

```yaml
experiment_id: EXP-009
status: VALID
prior_experiment: NONE
hypothesis: Dynamic plan-only rejects every otherwise valid `/cup_pose` sample because its orchestration path calls `get_one()` without first arming the READY boundary now required by `RosCupPoseSource`.
prediction: A focused orchestration regression will fail against source commit 9a7b296740d33fdb7d703a4e29de1731ba0ebce0 at the missing `arm()` call, then pass after adding the same bounded arm-before-acquire sequence used by execute mode.
single_variable: Add `source.arm(min(5.0, options.cup_pose_timeout_s))` between plan-only source construction and pose acquisition.
lifecycle: ISOLATED_STACK
preconditions:
  - No live SO-101, MoveIt, MuJoCo, Gazebo, or RViz runtime is started; this is an adapter-orchestration test only.
  - The preserved dirty `src/so101_demo_py/test/test_parallel_batch_resources.py` and untracked `MUJOCO_LOG.TXT` remain untouched and unstaged.
  - Every pytest invocation uses a fresh short scratch path below the registered durable evidence root, with `/usr/bin/python3` verifying `tempfile.gettempdir()` before collection.
success_criteria:
  - RED fails because plan-only attempts pose acquisition before arming the READY boundary.
  - GREEN passes after the minimal call-sequence change and asserts the five-second arm cap plus the unchanged full acquisition timeout.
  - Adjacent plan-only, cup-pose-source, and execute scene-sync regressions pass with zero failures.
failure_criteria:
  - The focused test passes before implementation, fails for an unrelated reason, or any task-owned adjacent regression fails.
invalid_criteria:
  - Source provenance, test executable, scratch provenance, or preserved dirty-file boundary differs from this record.
provenance:
  source_commit: 9a7b296740d33fdb7d703a4e29de1731ba0ebce0
  qualified_feature_commit: c8d44b862a90e4aa20e9945cf223caeff12ce4d5
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: 0
  gz_partition: post-review-plan-only-ready-no-live-stack
commands:
  - command: PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q src/so101_demo_py/test/test_dynamic_plan_only.py::test_run_dynamic_plan_only_arms_ready_boundary_before_pose_wait --junitxml=/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/pr01/red.xml
    exit_code: 1
  - command: PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q src/so101_demo_py/test/test_dynamic_plan_only.py::test_run_dynamic_plan_only_arms_ready_boundary_before_pose_wait --junitxml=/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/pr03/green.xml
    exit_code: 0
  - command: PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q src/so101_demo_py/test/test_dynamic_plan_only.py src/so101_demo_py/test/test_cup_pose_source.py src/so101_demo_py/test/test_dynamic_scene_sync.py --junitxml=/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/pr04/adjacent.xml
    exit_code: 0
  - command: PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q src/so101_demo_py/test --junitxml=/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/pr05/package.xml
    exit_code: 1
observed:
  - OBSERVED source history: commit 33a8b59aa0e5158aab79cbf0c2fc4751b07da1cf added `arm()` and a mandatory `_convert()` boundary, but only execute mode calls `arm()` before `get_one()`.
  - RED collected one test and failed one in 0.14 s because the production entrypoint returned 1 after `get_one()` raised `pose read before READY boundary`; shell elapsed 0.40 s.
  - The first GREEN attempt in scratch/pr02 was not authoritative: after reaching the newly enabled planner path it exposed an incomplete test fixture missing `arm_joint_names`; it collected one and failed one in 0.13 s. The log and scratch remain retained.
  - Authoritative GREEN collected one test and passed one in 0.13 s; shell elapsed 0.41 s. It proves `arm(5.0)` precedes `get_one(8.0)`.
  - The adjacent plan-only, cup-pose-source, and dynamic scene-sync files collected 40 tests and passed 40 in 0.59 s; shell elapsed 0.91 s.
  - The fresh ordinary package scope collected 3036 tests: 3034 passed, 1 skipped, 1 failed, and 4 warnings in 61.36 s; shell elapsed 62.52 s. The sole failure is the preserved task-external dirty test `test_transient_unclassified_proc_read_error_is_retried`; no task-owned failure appeared and benchmark tests were not collected.
  - All five pytest runs used distinct previously nonexistent scratch roots pr01 through pr05 and exact `/usr/bin/python3`; each preflight verified `tempfile.gettempdir()` resolved to that run's `tmp` child.
inferred:
  - The missing plan-only orchestration call was the first bad boundary; execute-mode semantics supplied the established bounded-arm reference.
conclusion: CONFIRMED and FIXED at the automated orchestration boundary. Live plan-only, MoveIt, MuJoCo, Gazebo, controller, joint/TF, and visual validation were intentionally not run and are not claimed.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/post-review-plan-only-ready/red.log SHA256 01f646f4d4817abb6a2fd3d1820a4b0c18c09290b21e2ae8c2a335a6a73363dd
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/pr01/red.xml SHA256 671e646c6a9a6062ce69f7bbd59a231455dd28f067fea8690ffa0e3e690dcce6
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/post-review-plan-only-ready/green-r2.log SHA256 79b6a7654a844c039d16ad3f03170fa4326b0a574de63a2876ecf1c5b2272a5d
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/pr03/green.xml SHA256 71bff87a2516fde21e2afeb1f026c36dc5554eaf56587637356a29fbbb5681ca
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/post-review-plan-only-ready/adjacent.log SHA256 6138862c4dc728713bd4f8fa656e742debafe06d9281bbb691f8ea4511c22614
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/pr04/adjacent.xml SHA256 7475fa8771f0d0af340808f4615d232d64c08f5cfc8c55ccdf1fa8f28d7ce29a
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/post-review-plan-only-ready/package.log SHA256 e8163366176dd940741a1373da92958de90a8874bb17cf74af7cfff1740366a7
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/pr05/package.xml SHA256 32c14cefa68cc4c335345a66ac1b82f429067f8de584e8981f6f755f6a5865a5
decision: KEEP
next_experiment: NONE
```

## CP-020 — Post-review dynamic plan-only READY fix

```yaml
checkpoint_id: CP-020
last_valid_experiment: EXP-009
current_hypothesis: NONE
source_commit: c8d44b862a90e4aa20e9945cf223caeff12ce4d5
working_tree_status: Ledger-only audit update pending; preserved user `src/so101_demo_py/test/test_parallel_batch_resources.py` and `MUJOCO_LOG.TXT` remain untouched and unstaged.
owned_processes: NONE; no live robot, MuJoCo, Gazebo, MoveIt, RViz, or ROS graph was started.
preserved_processes: Existing unrelated tmux sessions were not modified.
confirmed_conclusions:
  - Dynamic plan-only now arms the ROS-clock READY boundary with `min(5.0, options.cup_pose_timeout_s)` before waiting for a pose, matching execute-mode boundary semantics.
  - The focused RED failed 1/1 at the missing boundary; authoritative GREEN passed 1/1; adjacent ROS boundary tests passed 40/40.
  - The current ordinary package gate remains non-green at 3034 passed, 1 skipped, and 1 failed; its sole failure is the preserved user-owned dirty test and does not change EXP-009's task-owned result.
  - Earlier W8 qualification remains BLOCKED: no valid fixed-W8 20/20 result exists, the five-second SLO remains BLOCKED, C4 remains NOT_RUN, and adaptive fallback remains NOT_RUN/BLOCKED.
disproven_routes:
  - Changing `RosCupPoseSource._convert()` or weakening its READY validation is unnecessary; the defect was the omitted orchestration call.
open_risks:
  - No live plan-only ROS/MoveIt acceptance or fresh visual evidence was run because this dispatch explicitly prohibited live robot/MuJoCo execution.
  - The preserved external package-test failure remains unresolved and out of scope.
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/post-review-plan-only-ready and scratch/pr01 through scratch/pr05.
archived_runs: []
deletion_candidates:
  - scratch/pr01, scratch/pr02, scratch/pr03, scratch/pr04, and scratch/pr05; retained and not deleted pending explicit authorization.
next_command: NONE; source/test and ledger audit commits complete after final readback, with prior qualification boundaries unchanged.
```

## EXP-010A-W1 — Fresh READY-fence boundary reproduction

```yaml
experiment_id: EXP-010A-W1
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T06:49:00+08:00
  - status: INVALID
    at: 2026-09-15T06:55:23+08:00
prior_experiment: EXP-008R7-W1
hypothesis: The parent reports consumer readiness before the child freezes its ROS READY boundary, permitting the subsequent inference capture to use a buffered RGB frame whose source stamp predates the child boundary; all retransmissions are then correctly rejected until the lease expires.
prediction: A fresh first-point W1 execute run records child ready_ros_ns greater than the published pose source_stamp_ns, repeated CUP_POSE_STALE rejections, no POSE_ACCEPTED, no dynamic state manifest, and lease expiry at 240 s; H2 predicts POSE_ACCEPTED or dynamic-state progress, while H3 predicts no publication/callback despite a post-READY source stamp.
single_variable: Add fail-open measurement-only stage probes to the unchanged 11f96bd1 source and run one fresh W1 task_start attempt with the frozen C2/no-fallback production configuration.
lifecycle: ISOLATED_STACK
preconditions:
  - Claims 215-222 are RELEASED with cleanup_verified true, and no owned SO-101, ROS, MuJoCo, MoveIt, Broker, or container runtime is active.
  - Candidate source is clean at 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e; the preserved dirty resource test and MUJOCO_LOG.TXT remain outside the candidate and untouched.
  - Batch, runtime, tmux, systemd, ROS domain, output, and monitor identities are unique to this experiment.
success_criteria:
  - Stage evidence identifies the ordered subscription graph, child arm boundary, RGB/depth source stamps, Broker request/result, pose publication/delivery/validation, dynamic progress, child terminal state, lease state, and cleanup state for one fresh task_start attempt.
  - The observed first bad boundary distinguishes H1 from H2 and H3 without changing runtime decisions or weakening the READY rule.
failure_criteria:
  - The point progresses past the suspected boundary but fails at a different stage, in which case that new first bad boundary becomes the next A/B target.
invalid_criteria:
  - Provenance/config/model drift, missing stage identity, conflicting stack, oomd, transport truncation, fallback, or cleanup ambiguity.
provenance:
  source_commit: 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e
  runtime_executable: candidate-local so101_demo_py console with /usr/bin/python3 and the frozen perception environment
  ros_domain_id: 215
  gz_partition: not_applicable_mujoco
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp010a-w1-ready-fence
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/a10w1
observed: The isolated runner exited before invoking the batch because its zsh script referenced the unavailable EPOCHREALTIME parameter under set -u. No runtime root, ROS process, container, or domain claim was created; the orphaned external monitor was stopped.
conclusion: INVALID_PREFLIGHT; no hypothesis was exercised and this root will not be reused.
decision: RETRY_FRESH_IDENTITIES
next_experiment: EXP-010A-R2-W1
```

## CP-021 — Task 16 READY-fence diagnosis registered

```yaml
checkpoint_id: CP-021
last_valid_experiment: EXP-009
current_hypothesis: H1, a parent/child READY-fence race, is the leading explanation for the fresh W1 reproduction and must be tested before source modification.
source_commit: 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e
working_tree_status: This ledger is task-owned and modified; preserved user src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT remain untouched and unstaged.
owned_processes: NONE before EXP-010A-W1.
preserved_processes: Existing codex and completed recovery tmux sessions plus unrelated host processes remain untouched.
confirmed_conclusions:
  - Retained EXP-008R7 evidence places the first observed failure before MoveIt planning: the consumer rejected thirty callbacks carrying source stamp 11814000000 as predating its READY boundary and timed out after 240 seconds.
  - The parent completed graph-level consumer_ready before inference capture, but graph subscription existence does not prove that RosCupPoseSource.arm has frozen ready_ros_ns.
  - Broker returned one QUALIFIED YOLO result and the parent published the admitted pose; pure inference failure, missing publication, and MoveIt execution are not supported as the retained first bad boundary.
disproven_routes:
  - Weakening RosCupPoseSource READY validation is prohibited and would admit pre-boundary sensor data.
  - Repeating full W6 or W8 without boundary evidence is not authorized by the Task 16 handoff.
open_risks:
  - Retained probes did not directly emit the child arm boundary, so a fresh measurement must bind ready_ros_ns to the same attempt identity.
  - A production repair requires an explicit child-owned READY receipt or equivalent causal handshake plus a post-boundary capture guarantee.
retained_runs:
  - All earlier EXP-008 through EXP-009 evidence and Task 16 preflight files remain retained.
archived_runs: []
deletion_candidates:
  - Earlier invalid candidate clones and scratch trees remain deletion candidates; none is deleted without explicit authorization.
next_command: Create a clean 11f96bd1 candidate and fresh measurement-only instrumentation, then launch EXP-010A-W1 with unique identities and external monitoring.
```

## EXP-010A-R2-W1 — Fresh READY-fence boundary reproduction retry

```yaml
experiment_id: EXP-010A-R2-W1
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T06:56:00+08:00
  - status: INVALID
    at: 2026-09-15T06:58:00+08:00
prior_experiment: EXP-010A-W1
hypothesis: The parent reports consumer readiness before the child freezes its ROS READY boundary, permitting a buffered inference frame older than ready_ros_ns to be published and rejected until lease expiry.
prediction: Child ready_ros_ns is greater than the published source_stamp_ns, callbacks are received and rejected as pre-READY, and no dynamic planning state appears; H2 predicts accepted pose/planning progress, while H3 predicts absent callback/publication or a post-boundary stamp.
single_variable: Correct only the runner elapsed-clock implementation by using date +%s.%N; retain source, measurement probe, W1, task_start-only input, one attempt, C2, no fallback, and all production configuration.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-010A-W1 created no runtime root or owned runtime process, and its monitor is inactive.
  - Fresh candidate, batch b10w1, runtime /r/b10w1, output root exp010a-r2-w1-ready-fence, and systemd unit identities have never been used.
success_criteria:
  - Same as EXP-010A-W1, including complete ordered stage identities and exact cleanup.
failure_criteria:
  - The point passes the suspected boundary or reaches another first bad stage; use that boundary for the registered A/B.
invalid_criteria:
  - Any provenance, configuration, process, model, source, evidence, or cleanup ambiguity.
provenance:
  source_commit: 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e
  ros_domain_id: 215
  gz_partition: not_applicable_mujoco
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp010a-r2-w1-ready-fence
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/b10w1
observed: The wrapper reached invocation but both so101_parallel_batch and so101_parallel_batch_cleanup were absent from PATH because the candidate setup does not add its package libexec directory. No runtime root, ROS process, container, or claim was created.
conclusion: INVALID_PREFLIGHT; H1/H2/H3 remain untested.
decision: RETRY_WITH_VALIDATED_LIBEXEC_PATH
next_experiment: EXP-010A-R3-W1
```

## CP-022 — EXP-010A pre-runtime launch invalidated

```yaml
checkpoint_id: CP-022
last_valid_experiment: EXP-009
current_hypothesis: H1 remains untested by fresh live evidence.
source_commit: 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e
working_tree_status: Ledger is task-owned and modified; preserved dirty files remain untouched.
owned_processes: NONE; EXP-010A monitor was stopped and the runner exited before batch invocation.
confirmed_conclusions:
  - zsh on this host does not populate EPOCHREALTIME without an extra module; set -u terminated the runner after exact-command creation.
  - No /r/a10w1 runtime root exists and no ROS, MuJoCo, Broker, container, or domain claim was created.
retained_runs:
  - EXP-010A-W1 pre-runtime files and monitor samples are retained as invalid launch evidence.
archived_runs: []
deletion_candidates:
  - EXP-010A-W1 candidate clone and generated monitor files; retained pending authorization.
next_command: Launch EXP-010A-R2-W1 from a fresh candidate and fresh identities using date +%s.%N for elapsed timing.
```

## EXP-010A-R3-W1 — Fresh READY-fence reproduction with validated console path

```yaml
experiment_id: EXP-010A-R3-W1
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T06:58:00+08:00
  - status: INVALID
    at: 2026-09-15T06:59:10+08:00
prior_experiment: EXP-010A-R2-W1
hypothesis: H1 remains the leading live hypothesis: graph readiness can precede the child-owned ROS READY fence, allowing a buffered inference stamp to be rejected through lease expiry.
prediction: ready_ros_ns exceeds the published source_stamp_ns and all callbacks are pre-READY rejects; H2 and H3 retain the contrasting predictions registered in EXP-010A-R2-W1.
single_variable: Add the candidate package libexec directory to PATH and require command -v to resolve both batch and cleanup consoles before invocation; all measured runtime inputs remain unchanged.
lifecycle: ISOLATED_STACK
preconditions:
  - R2 created no runtime root or owned runtime process and both R2 units are inactive.
  - Fresh candidate, batch c10w1, /r/c10w1, output root exp010a-r3-w1-ready-fence, and R3 systemd identities are unused.
success_criteria:
  - Same ordered one-point stage and cleanup evidence required by EXP-010A-W1.
failure_criteria:
  - A different valid runtime boundary is observed and becomes the A/B target.
invalid_criteria:
  - Console resolution, provenance, configuration, model, runtime ownership, or cleanup is ambiguous.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp010a-r3-w1-ready-fence
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/c10w1
source_commit: 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e
observed: Exact libexec consoles resolved, but set -u was active while sourcing ROS/colcon setup scripts. Unset AMENT_TRACE_SETUP_FILES and COLCON_TRACE caused partial setup, leaving candidate Python metadata unavailable to the console. No runtime root or owned stack was created.
conclusion: INVALID_PREFLIGHT; no live hypothesis was exercised.
decision: RETRY_AFTER_EXACT_SYSTEMD_HELP_PROBE
next_experiment: EXP-010A-R4-W1
```

## CP-023 — Candidate libexec launch boundary registered

```yaml
checkpoint_id: CP-023
last_valid_experiment: EXP-009
current_hypothesis: H1 remains untested because R2 stopped before runtime creation.
source_commit: 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e
owned_processes: NONE.
confirmed_conclusions:
  - Candidate setup resolves the Python overlay but does not place install/so101_demo_py/lib/so101_demo_py on PATH for direct console invocation.
  - R2 emitted only command-not-found errors and created no /r/b10w1 root, claim, ROS node, container, or MuJoCo process.
retained_runs:
  - EXP-010A and EXP-010A-R2 pre-runtime evidence is retained.
archived_runs: []
deletion_candidates:
  - Both invalid candidate clones and launch-only monitor files remain retained deletion candidates.
next_command: Build R3 fresh, prepend candidate libexec, and fail closed on command -v before launching its external monitor and runner.
```

## EXP-010A-R4-W1 — Fresh READY-fence reproduction after systemd environment probe

```yaml
experiment_id: EXP-010A-R4-W1
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T07:00:00+08:00
  - status: INVALID
    at: 2026-09-15T07:02:00+08:00
prior_experiment: EXP-010A-R3-W1
hypothesis: H1 remains untested and predicts ready_ros_ns greater than the pose source stamp followed by only pre-READY rejects.
prediction: Same H1/H2/H3 discriminators registered in EXP-010A-R2-W1.
single_variable: Suspend nounset only while sourcing ROS and colcon setup files, restore nounset afterward, and require an exact systemd-context Python metadata plus console --help probe before live launch.
lifecycle: ISOLATED_STACK
preconditions:
  - R3 created no runtime root or runtime-owned process; its units are inactive.
  - Fresh candidate, batch d10w1, /r/d10w1, output root exp010a-r4-w1-ready-fence, and R4 systemd identities are unused.
success_criteria:
  - Complete one-point stage evidence distinguishes H1/H2/H3 and exact cleanup leaves no owned artifact active.
failure_criteria:
  - A different valid first runtime boundary is observed and registered for A/B.
invalid_criteria:
  - Exact systemd help probe fails, or provenance/config/model/runtime/cleanup is ambiguous.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp010a-r4-w1-ready-fence
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/d10w1
source_commit: 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e
observed: The exact systemd environment probe passed, then production validation rejected the task_start-only file as POINT_CATALOG_HASH_MISMATCH before stack startup. Cleanup reported RUNTIME_ROOT because no runtime was created. No ROS, MuJoCo, Broker, container, or claim started.
conclusion: INVALID_PREFLIGHT; the frozen catalog cannot be subsetted. The fresh run must retain the full catalog; first-failure convergence and max_infra_attempts_per_point=1 bound it to the first failing task_start attempt if H1 reproduces.
decision: RETRY_FULL_FROZEN_CATALOG
next_experiment: EXP-010A-R5-W1
```

## CP-024 — Exact systemd environment preflight required

```yaml
checkpoint_id: CP-024
last_valid_experiment: EXP-009
current_hypothesis: H1 remains the leading but not yet freshly exercised runtime hypothesis.
source_commit: 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e
owned_processes: NONE.
confirmed_conclusions:
  - ROS and colcon zsh setup scripts reference optional variables without nounset guards; sourcing them while set -u is invalid.
  - Interactive shell validation was insufficient because the transient systemd environment exposed the unset-variable path.
retained_runs:
  - EXP-010A through R3 launch-only evidence remains retained.
archived_runs: []
deletion_candidates:
  - The three invalid candidate clones and monitor files are retained deletion candidates.
next_command: Build R4, validate metadata and console help inside systemd with nounset disabled only for setup sourcing, then launch live only if that probe passes.
```

## EXP-010A-R5-W1 — Fresh READY-fence reproduction with frozen catalog

```yaml
experiment_id: EXP-010A-R5-W1
status: VALID_DIAGNOSTIC
status_history:
  - status: PLANNED
    at: 2026-09-15T07:03:00+08:00
  - status: RUNNING
    at: 2026-09-15T07:04:32+08:00
  - status: VALID_DIAGNOSTIC
    at: 2026-09-15T07:08:25+08:00
prior_experiment: EXP-010A-R4-W1
hypothesis: H1 predicts the first frozen point task_start will publish a source stamp older than the child READY fence and expire without dynamic planning.
prediction: Same exact H1/H2/H3 discriminators registered in EXP-010A-R2-W1.
single_variable: Restore the frozen full twenty-point catalog required by its configured hash; retain W1, one infrastructure attempt, C2, no fallback, source, probe, and every other runtime value.
lifecycle: ISOLATED_STACK
preconditions:
  - R4 failed before stack startup, and no R4 runtime root, claim, container, or owned process remains.
  - Fresh candidate, batch e10w1, /r/e10w1, output root exp010a-r5-w1-ready-fence, and R5 units are unused.
success_criteria:
  - The first task_start attempt yields the complete ordered boundary evidence and exact cleanup; if it fails, first-failure convergence stops the catalog.
failure_criteria:
  - task_start passes the suspected boundary, in which case its next valid first bad stage is captured and further catalog work is stopped through the owning runner if safely possible.
invalid_criteria:
  - Provenance, catalog, model, runtime, environment, evidence, or cleanup ambiguity.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp010a-r5-w1-ready-fence
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e10w1
source_commit: 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e
observed:
  - task_start graph readiness completed at monotonic 1247100.269589074, child arm completed 0.099677 s later at 1247100.369266345 with ready_ros_ns 13606000000, and capture had already started at 1247100.270963119.
  - The captured task_start source stamp was 13638000000, 32 ms after the child fence, so the consumer accepted it and the point completed PASSED. cup_test_forward_5cm likewise used stamp 4515999999 after ready_ros_ns 4471999999 and completed PASSED.
  - H2 and H3 are disproven for both points: each had Broker QUALIFIED, publication, callback, POSE_ACCEPTED, dynamic DONE, controller execution, MuJoCo physical evidence, and parent receipt sealing.
  - The operator sent SIGINT to the exact wrapper after the second seal; the already-issued third lease was stopped as UNRUN. Aggregate exit 1 after 233.18406629562378 s, terminal SUPERVISOR_SHUTDOWN, batch_cleanup_complete true, Domain 215 RELEASED, and exact process/container/socket readback empty.
conclusion: The race window is freshly confirmed but did not lose this capture: parent graph READY can precede the child fence while capture is already in flight. The old stale-stamp failure remains an intermittent ordering outcome. A controlled arm-delay A/B is required to force the same boundary without changing validation.
decision: FORCE_BOUNDARY_TIMING_AB
next_experiment: EXP-010B-W1
```

## CP-025 — Frozen catalog restored for boundary reproduction

```yaml
checkpoint_id: CP-025
last_valid_experiment: EXP-009
current_hypothesis: H1 remains untested by a live stack; R4 proved only the catalog validation boundary.
source_commit: 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e
owned_processes: NONE.
confirmed_conclusions:
  - The production config authenticates the entire point catalog and rejects a task_start-only derivative before runtime.
  - The exact systemd Python metadata and both console --help probes are now proven valid when nounset is suspended only during setup sourcing.
retained_runs:
  - EXP-010A through R4 pre-runtime files remain retained.
archived_runs: []
deletion_candidates:
  - Four invalid candidate clones and their launch-only monitor files remain retained deletion candidates.
next_command: Launch R5 from a fresh candidate with the full frozen catalog, W1, one infrastructure attempt, C2, no fallback, and the same stage probe.
```

## EXP-010B-W1 — Controlled child-arm delay A/B

```yaml
experiment_id: EXP-010B-W1
status: VALID_DIAGNOSTIC
status_history:
  - status: PLANNED
    at: 2026-09-15T07:09:00+08:00
  - status: RUNNING
    at: 2026-09-15T07:11:28+08:00
  - status: VALID_DIAGNOSTIC
    at: 2026-09-15T07:13:12+08:00
prior_experiment: EXP-010A-R5-W1
hypothesis: If the unacknowledged child READY fence is causal, delaying only RosCupPoseSource.arm after subscription discovery will force the already-started parent capture to carry a source stamp older than ready_ros_ns, reproducing the retained stale rejection pattern.
prediction: Compared with A, graph readiness and capture start remain ordered the same, while a one-second child-arm delay moves ready_ros_ns after capture source_stamp_ns; Broker still qualifies and publishes, callbacks arrive, every callback is rejected as pre-READY, POSE_ACCEPTED/dynamic manifest remain absent, and no unrelated fault occurs.
single_variable: Measurement shim sleeps 1.0 s immediately before the unchanged RosCupPoseSource.arm implementation; all production source, validation, model, catalog, W1/C2/no-fallback, timeouts, and one-attempt settings remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-010A-R5 cleanup is exact and Domain 215 is RELEASED.
  - Fresh candidate, batch f10w1, /r/f10w1, output root exp010b-w1-arm-delay, and systemd identities are unused.
success_criteria:
  - Same-attempt traces prove source_stamp_ns less than ready_ros_ns, callbacks delivered and rejected only for the READY fence, with Broker and publisher success; once proven, stop the exact wrapper and complete ownership cleanup rather than wait an undifferentiated 240 seconds.
failure_criteria:
  - A post-boundary stamp is rejected, no callback is delivered, dynamic planning begins, or another earlier boundary appears.
invalid_criteria:
  - Delay env is not confined to the measurement shim, provenance/config/model changes, conflicting stack, oomd, truncation, fallback, or cleanup ambiguity.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp010b-w1-arm-delay
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/f10w1
source_commit: 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e
observed:
  - The sole one-second pre-arm delay moved ready_ros_ns to 11784000000 while the parent capture, already started after graph readiness but before the child fence, sealed source_stamp_ns 11686000000.
  - Broker completed QUALIFIED and publish_pose retransmitted the exact admitted stamp. The consumer received and rejected all 30 callbacks only as CUP_POSE_STALE message predates READY boundary; invalid_count 30, accepted_count 0, and no dynamic manifest was created.
  - The exact wrapper was stopped immediately after the discriminating evidence. Top-level cleanup-receipt reports cleanup_complete true and released Domain 215; process, container and socket readback is empty. The inner interrupted generation aggregate retains batch_cleanup_complete false and is not qualification evidence.
conclusion: H1 is causally confirmed. Graph subscription readiness is not the child-owned READY fence, and capture may complete before that fence; immutable retransmission can never recover because every retry preserves the stale stamp. H2 and H3 are disproven at this boundary.
decision: IMPLEMENT_CHILD_READY_RECEIPT_AND_POST_FENCE_CAPTURE
next_experiment: EXP-011-RED
```

## CP-026 — Fresh race window confirmed; A/B armed

```yaml
checkpoint_id: CP-026
last_valid_experiment: EXP-010A-R5-W1
current_hypothesis: H1 is the only hypothesis consistent with both the retained stale run and fresh A timing; outcome depends on whether an in-flight buffered capture stamp lands before or after the unacknowledged child fence.
source_commit: 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e
owned_processes: NONE after exact R5 cleanup.
confirmed_conclusions:
  - Parent graph READY does not causally acknowledge child arm: in task_start, capture began 98.303 ms before the child froze its fence.
  - Fresh post-fence stamps were accepted and both task_start and cup_test_forward_5cm completed dynamic DONE and sealed PASSED, disproving lost child result and missing publication for those attempts.
  - R5 cleanup is complete and no evidence was deleted.
retained_runs:
  - EXP-010A through R5 output, runtime, instrumentation, monitor, image, motion, and cleanup evidence remains retained.
archived_runs: []
deletion_candidates:
  - EXP-010A through R4 invalid candidate clones; R5 generated candidate/build and canceled third-attempt working evidence; all retained pending explicit authorization.
next_command: Run EXP-010B with only a one-second pre-arm diagnostic delay, stop after the same-attempt stale-rejection proof, and perform exact cleanup.
```

## EXP-011-RED — Child READY receipt and post-fence capture contract

```yaml
experiment_id: EXP-011-RED
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T07:14:00+08:00
  - status: RUNNING
    at: 2026-09-15T07:18:00+08:00
  - status: PASSED
    at: 2026-09-15T07:19:00+08:00
prior_experiment: EXP-010B-W1
hypothesis: A child-owned durable receipt written only after RosCupPoseSource.arm, combined with parent validation and rejection/retry of any inference frame older than ready_ros_ns, closes the causal gap without weakening READY validation.
prediction: Focused tests added before implementation fail because the child command has no receipt path, dynamic execute writes no post-arm receipt, and capture accepts a pre-fence RGB stamp.
single_variable: Add only focused contract tests; production source remains unchanged for RED.
lifecycle: NO_LIVE_STACK
preconditions:
  - EXP-010B exact cleanup is complete and no owned runtime is active.
  - Fresh ai-station NVMe scratch root under the registered durable evidence root is verified with exact /usr/bin/python3 before pytest collection.
success_criteria:
  - Tests collect and fail only at the three absent owning-boundary behaviors.
failure_criteria:
  - Tests pass before implementation or fail for fixture/environment reasons.
invalid_criteria:
  - Wrong source, Python, TMPDIR, scope, or preserved dirty-file contamination.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp011-ready-receipt-red-green
source_commit: 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e
observed:
  - t16red01 was invalid because the selected environment could not import the worktree module; t16red02 was invalid because zsh nounset handling failed before tempfile verification and collection. Neither result was used.
  - Authoritative t16red03 verified /usr/bin/python3, the worktree module path, and a fresh NVMe tempfile root before collecting exactly three focused tests.
  - All three tests failed at the intended absent contracts: no post-arm child receipt, no --ready-receipt child argv, and inference capture retained stamp 100 instead of retrying to the fence stamp 200. JUnit records 3 tests, 3 failures, 0 errors, and 0 skips in 0.366 s.
conclusion: The missing child-owned READY receipt and post-fence snapshot rule were independently RED before production implementation.
decision: IMPLEMENT_MINIMAL_OWNING_BOUNDARY_FIX
next_experiment: EXP-011-GREEN
```

## CP-027 — Root cause causally confirmed

```yaml
checkpoint_id: CP-027
last_valid_experiment: EXP-010B-W1
current_hypothesis: The minimal repair must make child arm completion causally visible to the parent and ensure inference source_stamp_ns is not older than that exact child fence.
source_commit: 11f96bd1f35ec79d5910d0cb414e7121a9a93c0e
owned_processes: NONE after A/B cleanup.
confirmed_conclusions:
  - A one-second pre-arm delay alone reproduced the retained failure: 11686000000 published versus child ready_ros_ns 11784000000, with 30/30 callbacks rejected and no accepted pose.
  - Broker inference and DDS delivery both succeeded; immutable retransmission is unable to repair an already stale source stamp.
  - READY validation itself is correct and must remain unchanged.
disproven_routes:
  - Lost child result, missing dynamic manifest observation, missing Broker response, and missing DDS callback are not the first bad boundary.
retained_runs:
  - EXP-010A through EXP-010B evidence and runtime roots are retained.
archived_runs: []
deletion_candidates:
  - Invalid candidate clones plus diagnostic candidate/build trees and canceled working attempts; none deleted.
next_command: Add the three owning-boundary tests first and run their fresh-scratch RED gate against unchanged production source.
```

## EXP-011-GREEN — Child-owned READY fence repair and tests

```yaml
experiment_id: EXP-011-GREEN
status: PASSED
prior_experiment: EXP-011-RED
hypothesis: Publishing a lease-bound receipt only after child arm, requiring it in parent consumer_ready, and retrying inference capture when source_stamp_ns precedes its ready_ros_ns closes the proven race while preserving the existing consumer validation boundary.
implementation:
  - dynamic_cup_pick_place accepts an explicit --ready-receipt path.
  - ParallelWorkerRuntime supplies the exact per-attempt dynamic/consumer-ready.json path.
  - run_dynamic_execute exclusively writes a 0600, fsync-backed, schema- and lease-bound receipt only after RosCupPoseSource.arm returns.
  - ParallelRosRuntimePorts validates the exact child argv, path, file identity, schema, lease/session/reset identity, and child monotonic/ROS times before graph readiness becomes consumer readiness.
  - The first immutable inference snapshot rejects and retries camera frames older than the child ready_ros_ns; RosCupPoseSource READY validation is unchanged.
test_evidence:
  - t16green01 is invalid because a test insertion left two pre-existing assertions in the wrong fixture scope; retained and not counted.
  - t16green02 is the authoritative implementation GREEN: 4 passed in 0.321 s after adding the parent receipt-validation coverage.
  - t16green03 revalidated the same 4 tests in 0.306 s after changing receipt publication to a complete-write loop.
  - t16adj01 is invalid because it named a nonexistent test file and collected no tests; retained and not counted.
  - t16adj02 passed all 161 adjacent dynamic, cup-pose, worker-runtime, ROS-runtime, and dual-entrypoint tests in 1.248 s.
  - t16pkg01 is invalid because Torch was absent from the selected import environment and collection did not complete.
  - t16pkg02 is invalid because its deep scratch path exceeded the Unix socket path limit; it completed with 58 path-derived failures and is not a product result.
  - A sandbox-denied t16pkg02 retry exposed tempfile=/tmp and was interrupted immediately; it is not a gate result.
  - Authoritative short-path t16p3 package collection ran 3038 tests: 3036 passed, 1 skipped, and the sole failure was the preserved task-external dirty test test_transient_unclassified_proc_read_error_is_retried. Benchmark tests were not collected.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
source_commit: 79993774536a4e6c9280f92eaedbc815f94096b9
decision: ACCEPT_UNIT_AND_PACKAGE_GATES
next_experiment: EXP-012-W1
```

## CP-028 — Minimal repair ready for clean-candidate live gate

```yaml
checkpoint_id: CP-028
last_valid_experiment: EXP-011-GREEN
current_hypothesis: The parent now waits for the exact child-owned READY receipt and cannot submit an inference frame older than that receipt's ready_ros_ns; a fresh one-point execute run must prove the boundary in the real stack before W6 qualification.
source_commit: 79993774536a4e6c9280f92eaedbc815f94096b9
owned_processes: NONE after EXP-010B exact cleanup; unit gates created no live ROS stack.
confirmed_conclusions:
  - The causal A/B and the 3-failure RED isolate the repair to the child READY handshake and snapshot boundary.
  - Focused GREEN, adjacent 161-test coverage, and the ordinary 3038-test package collection show no task-owned regression; the only package failure is the prohibited pre-existing dirty resource-probe test.
  - No benchmark suite was collected and no evidence was deleted.
retained_runs:
  - EXP-010A, EXP-010B, all RED/GREEN/adjacent/package reports, and all scratch trees remain retained.
archived_runs: []
deletion_candidates:
  - Invalid pre-runtime candidate clones, diagnostic build trees, canceled working attempts, invalid test scratch trees, and completed pytest scratch trees; all retained pending explicit authorization.
next_command: Commit only the seven task-owned source/test files, build a fresh clean candidate from that commit, and execute one fixed W1 point with exact provenance, visual readback, and cleanup.
```

## EXP-012-W1 — Fresh fixed one-worker execute gate

```yaml
experiment_id: EXP-012-W1
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T07:29:46+08:00
  - status: RUNNING
    at: 2026-09-15T07:33:55+08:00
  - status: PASSED
    at: 2026-09-15T07:35:59+08:00
prior_experiment: EXP-011-GREEN
hypothesis: The production parent will not declare consumer readiness until the exact child has armed, and its immutable inference snapshot will be at or after that child READY ROS boundary.
prediction: task_start seals PASSED before the 240 s lease limit, the receipt identity matches the lease, inference/accepted stamp is not older than ready_ros_ns, dynamic execution reaches DONE, and exact cleanup releases Domain 215 without residue.
single_variable: Production repair at commit 79993774536a4e6c9280f92eaedbc815f94096b9; frozen full catalog, W1, C2 request, no fallback, execute mode, and one infrastructure attempt.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp012-w1-fixed-ready
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/g12w1
source_commit: 79993774536a4e6c9280f92eaedbc815f94096b9
systemd_unit: so101-t16-g12w1.service
systemd_invocation_id: 8451821d326f4cf6a60d7d0c0a75ffdf
observed:
  - Preflight found empty ROS graphs on Domains 0 and 215-222, all frozen claims RELEASED, no conflicting runtime, no Docker container, no GPU compute app, and 26 GiB host memory available. The journal+console metadata probe passed.
  - Fresh detached candidate commit and clean status were verified; source/build hashes for both changed runtime modules match, and batch provenance records source_dirty false at the exact commit.
  - task_start sealed PASSED with reason OK. Child receipt ready_ros_ns was 11438000000; the YOLO inference, localized pose, and admitted source stamp were 12470000000, 1.032 s after the fence.
  - dynamic-execute-manifest current_state is DONE and the sealed manifest contains initial/terminal RGB, physical, depth, TF, PlanningScene/dynamic, pose admission, and inference snapshot evidence.
  - Fresh visual inspection shows the cup moved from its initial pose to the red target area and the gripper released clear of the cup. Numeric evidence and the manifest prove physical action rather than plan-only behavior.
  - The run was intentionally stopped after the required sealed point. Top aggregate is therefore non-qualification INFRA_FAILED, while the sealed point is valid live-gate evidence. Wrapper cleanup reports cleanup_complete true and Domain 215 RELEASED; exact process, labeled-container, and socket readback is empty.
  - The isolated systemd cgroup recorded MemoryPeak 1154129920 bytes and zero swap peak.
conclusion: The fixed production boundary succeeds in the real execute stack: child arm causally precedes the inference frame and the former 240 s stale-loop does not occur.
decision: ADVANCE_TO_FIXED_W6_QUALIFICATION
next_experiment: EXP-013-W6
```

## CP-029 — Fresh live repair accepted

```yaml
checkpoint_id: CP-029
last_valid_experiment: EXP-012-W1
current_hypothesis: With the child READY race closed at W1, fixed W6 should complete all 20 points without lease expiry, fallback, Grounded-SAM execution, truncation, OOM, or cleanup residue.
source_commit: 79993774536a4e6c9280f92eaedbc815f94096b9
owned_processes: NONE after exact g12w1 cleanup.
confirmed_conclusions:
  - The child receipt and accepted inference belong to the exact same attempt and session, and 12.470 s is strictly newer than the 11.438 s READY boundary.
  - task_start reached DONE and sealed PASSED under production code; visual and numeric evidence are consistent with correct pick-place.
  - Domain 215, process tree, Broker container, and IPC sockets were released exactly; no evidence was deleted.
retained_runs:
  - EXP-012 candidate/build, full runtime, journal, systemd identity, sealed images, manifests, and cleanup evidence are retained.
archived_runs: []
deletion_candidates:
  - EXP-012 generated candidate/build and intentionally canceled post-gate working evidence; retained pending explicit authorization.
next_command: Launch fresh fixed-W6 batch g13w6 from the same clean candidate with the full catalog, three initial points per worker, C2 YOLO, no fallback, and full resource monitoring.
```

## EXP-013-W6 — Twenty passes with invalid terminal cleanup scan

```yaml
experiment_id: EXP-013-W6
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T07:36:00+08:00
  - status: RUNNING
    at: 2026-09-15T07:40:39+08:00
  - status: INVALID
    at: 2026-09-15T07:47:38+08:00
prior_experiment: EXP-012-W1
hypothesis: The fixed READY boundary will permit a fresh fixed-W6/C2/no-fallback batch to complete all 20 execute points and exact automatic cleanup.
prediction: Coordinator and top-level aggregates both qualify 20/20, wrapper exits zero, all six claims are RELEASED, and ownership readback is empty.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp013-w6-fixed-ready
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/g13w6
source_commit: 79993774536a4e6c9280f92eaedbc815f94096b9
systemd_unit: so101-t16-g13w6.service
systemd_invocation_id: 4fbbe820bc3f4641943d147464dc6080
observed:
  - All 20 frozen points sealed PASSED on their first attempt in 409.465 s. Coordinator records coverage_complete, execution_complete, qualification_passed, POINTS_COMPLETE, and batch_cleanup_complete true; levels_used is exactly [6].
  - There was no CUP_POSE_STALE, lease expiry, TRUNCATED_FRAME, OOM, worker-count fallback, or infrastructure retry. Resource monitor recorded cgroup MemoryPeak 6289727488 bytes, maximum summed process PSS 6202079 KiB, GPU-used maximum 4555 MiB, GPU utilization maximum 15%, and minimum host MemAvailable 19896208 KiB.
  - The wrapper's subsequent external cleanup scan hit PROC_METADATA_UNVERIFIABLE for short-lived PID 1103921. Top-level aggregate therefore records INFRA_FAILED and batch_cleanup_complete false, and systemd exits 1; this violates the exact terminal cleanup contract even though every point passed.
  - PID 1103921 was absent at readback. One idempotent exact cleanup retry immediately succeeded, wrote cleanup_complete true, released Domains 215-220, and left no exact process, labeled container, socket, or GPU compute app.
conclusion: The READY repair is successful at W6 concurrency, but this run is not qualification because a one-shot procfs read race made automatic external cleanup fail.
decision: FIX_BOUNDED_PROCFS_CLEANUP_RACE_AND_RERUN_W6
next_experiment: EXP-014-CLEANUP-RED
```

## EXP-014-CLEANUP-RED — Transient proc metadata cleanup race

```yaml
experiment_id: EXP-014-CLEANUP-RED
status: PASSED
prior_experiment: EXP-013-W6
hypothesis: A same-UID process may disappear or transiently deny one procfs metadata read during terminal cleanup; one bounded retry will distinguish this race from a persistent unverifiable process without weakening fail-closed behavior.
prediction: A focused test that injects one PermissionError on comm metadata fails as PROC_METADATA_UNVERIFIABLE before implementation.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/t16cr01
source_commit: 79993774536a4e6c9280f92eaedbc815f94096b9
observed:
  - Exact /usr/bin/python3 and a fresh short NVMe tempfile root were verified before collection.
  - The one focused test failed at the intended PROC_METADATA_UNVERIFIABLE boundary in 0.05 s.
conclusion: The live W6 cleanup failure has an automated RED reproducer independent of the preserved dirty test file.
decision: IMPLEMENT_ONE_BOUNDED_RETRY
next_experiment: EXP-014-CLEANUP-GREEN
```

## EXP-014-CLEANUP-GREEN — Bounded procfs read retry

```yaml
experiment_id: EXP-014-CLEANUP-GREEN
status: PASSED
prior_experiment: EXP-014-CLEANUP-RED
implementation:
  - Retry proc identity metadata once after an OSError.
  - Retry proc environ once after an OSError.
  - Preserve the second error, all identity comparisons, and every existing fail-closed classification.
test_evidence:
  - t16cg01 is invalid only because the new test expected two comm reads but the mandatory post-environ identity verification correctly made a third; four other assertions passed.
  - Corrected t16cg02 passed 5/5, including the preserved task-external transient-environ test plus persistent metadata denial, persistent unclassified denial, and PID starttime-change fail-closed checks.
  - t16ca01 is invalid because it named a nonexistent cleanup test file and collected none.
  - t16ca02 passed 147/148; its unrelated integration test's own reaper thread won a process wait race. Identical fresh t16ca03 passed all 148 tests.
  - Fresh ordinary package gate t16p4 collected 3039 tests: 3038 passed, 1 skipped, 0 failed in 61.33 s. Benchmark tests were not collected.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
source_commit: 790f600cc1b361d2ceff8b8e55a5b8b746633974
decision: ACCEPT_AND_REBUILD_CANDIDATE
next_experiment: EXP-015-W6
```

## CP-031 — READY and cleanup boundaries repaired

```yaml
checkpoint_id: CP-031
last_valid_experiment: EXP-014-CLEANUP-GREEN
current_hypothesis: Commit 790f600cc1b361d2ceff8b8e55a5b8b746633974 retains the proven W6 READY success and removes the single terminal procfs race; a fresh W6 must still establish a zero-exit top-level aggregate and automatic cleanup before W8.
source_commit: 790f600cc1b361d2ceff8b8e55a5b8b746633974
owned_processes: NONE after the exact g13w6 manual cleanup retry.
confirmed_conclusions:
  - W6 concurrency completed every physical execute point once; READY/capture is no longer the limiting boundary.
  - The only invalidating terminal event was a transient metadata read of a now-absent PID, causally corroborated by the successful unchanged cleanup retry.
  - Bounded retry passes transient cases while repeated denials and identity changes still fail closed; the entire ordinary package gate passes.
retained_runs:
  - Invalid EXP-013 full run, resource monitor, 20 sealed point trees, failed first cleanup, and successful cleanup retry are retained.
archived_runs: []
deletion_candidates:
  - EXP-013 runtime/report artifacts and all completed/invalid test scratch trees; retained pending explicit authorization.
next_command: Build a fresh clean candidate at 790f600cc1b361d2ceff8b8e55a5b8b746633974 and run fixed-W6 batch g15w6 with the same full catalog, C2/no-fallback contract, and external monitor.
```

## EXP-015-W6 — Twenty passes with a repeated terminal process-table race

```yaml
experiment_id: EXP-015-W6
status: INVALID
status_history:
  - status: PLANNED
  - status: RUNNING
  - status: INVALID
    at: 2026-09-15T08:03:22+08:00
prior_experiment: EXP-014-CLEANUP-GREEN
hypothesis: One immediate procfs read retry is sufficient for exact automatic cleanup after a fixed W6 run.
prediction: All 20 points pass, the wrapper exits zero, its cleanup receipt is complete, and Domains 215-220 have no residue.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp015-w6-qualified
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/g15w6
source_commit: 790f600cc1b361d2ceff8b8e55a5b8b746633974
systemd_unit: so101-t16-g15w6.service
systemd_invocation_id: 6b337172564f4b12ae317d72318964f2
observed:
  - All 20 frozen execute points sealed PASSED on their first attempt in 400.048 s. Levels used were exactly [6], with no infrastructure retry, fallback, CUP_POSE_STALE, lease expiry, TRUNCATED_FRAME, or OOM.
  - Coordinator cleanup completed, but the wrapper's later exact domain scan failed as PROC_METADATA_UNVERIFIABLE for PID 1153845. The top aggregate is therefore INFRA_FAILED, batch_cleanup_complete is false, and systemd exited 1.
  - PID 1153845 appears in no retained task manifest or log except the cleanup error and was absent at the 08:08:25 readback. An unchanged idempotent cleanup retry succeeded, released Domains 215-220, and exact process/container/socket/GPU/ROS readback was empty.
  - The first recorded manual command used the unavailable bare console name and is retained as invalid; the corrected ros2-run cleanup succeeded.
conclusion: An immediate second read does not cover the terminal process-table quiescence interval. The allocation-time probe remains correctly fail-closed; cleanup needs a bounded whole-scan stabilization window after owned retirement.
decision: ADD_CLEANUP_ONLY_BOUNDED_RESCAN_AND_RERUN_W6
next_experiment: EXP-016-CLEANUP-QUIESCENCE
```

## EXP-016-CLEANUP-QUIESCENCE — Bounded whole-scan stabilization

```yaml
experiment_id: EXP-016-CLEANUP-QUIESCENCE
status: PASSED
prior_experiment: EXP-015-W6
hypothesis: Retrying the complete domain process scan for a bounded five-second cleanup-only quiescence window absorbs disappearing-process races while persistent uncertainty and active-domain evidence remain fail-closed.
implementation:
  - External cleanup now retries only PROC_IDENTITY_UNVERIFIABLE, PROC_METADATA_UNVERIFIABLE, PROC_ENV_UNVERIFIABLE, PROC_CLASSIFICATION_UNVERIFIABLE, and PROC_IDENTITY_CHANGED boundaries.
  - Each retry begins a fresh SystemResourceProbe domain scan; at most 101 attempts are made at 0.05 s spacing. A positive domain match returns immediately, non-proc failures propagate immediately, and the last transient failure propagates unchanged.
  - Allocation and admission probing are unchanged.
test_evidence:
  - t16qr01 is invalid because its explicit PYTHONPATH hid the package mapping; it is retained and not counted.
  - Authoritative RED t16qr02 collected two cleanup tests and failed both at the absent retry API.
  - Focused GREEN t16qg01 passed 3/3, including the existing single-read race, cleanup transient recovery, and persistent fail-closed behavior.
  - t16qa01 and t16qa02 were invalid because a ROS Domain 215 daemon created by the preceding graph readback remained active. The daemon identity was proven as PID 1159410, stopped exactly, and retained in exp015-w6-qualified/ros2-daemon-215-cleanup.txt.
  - Clean-host adjacent t16qa03 passed all 150 tests.
  - t16p5 is invalid for missing Torch; t16p6 used TMPDIR at the parent scope and collided with retained fixture names; t16p7 through t16p9 each covered 3041 tests with only the pre-existing concurrent-claim fixture's both-rejected interleaving. That test passed alone in fresh t16qf01.
  - The split ordinary gate t16p11 passed the other 3040 tests with one skip and zero failures in 60.901 s; together with t16qf01 it covers all 3041 ordinary tests. No benchmark test was collected.
source_commit: e78564c10214cd19245d6218e2ae434a5ed66395
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
decision: ACCEPT_CLEANUP_REPAIR_AND_REBUILD_CANDIDATE
next_experiment: EXP-017-W6
```

## CP-032 — Second cleanup repair ready for W6

```yaml
checkpoint_id: CP-032
last_valid_experiment: EXP-016-CLEANUP-QUIESCENCE
current_hypothesis: Cleanup-only whole-scan stabilization at e78564c10214cd19245d6218e2ae434a5ed66395 will preserve the proven 20/20 W6 behavior and allow the wrapper's first automatic cleanup to complete.
source_commit: e78564c10214cd19245d6218e2ae434a5ed66395
owned_processes: NONE after the exact g15w6 cleanup retry and task-created ROS daemon stop.
confirmed_conclusions:
  - The READY repair has twice produced 20 first-attempt W6 passes.
  - The terminal failures occur after coordinator cleanup, on short-lived same-UID PIDs absent at later readback.
  - Cleanup retry remains bounded and fail-closed, and does not weaken admission, timeouts, resource policy, or exact ownership checks.
retained_runs:
  - EXP-015 runtime/report, all 20 sealed point trees, cleanup diagnostics, RED/GREEN/adjacent/package evidence, and every scratch tree remain retained.
archived_runs: []
deletion_candidates:
  - Completed and invalid test scratch trees plus invalid EXP-015 candidate/build/runtime artifacts; retained pending explicit authorization.
next_command: Build a fresh clean detached candidate at e78564c10214cd19245d6218e2ae434a5ed66395 and launch fixed W6 batch g17w6 with the frozen C2/no-fallback execute contract and external monitor.
```

## EXP-017-W6 — Fixed six-worker qualification rerun

```yaml
experiment_id: EXP-017-W6
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T08:26:18+08:00
  - status: RUNNING
    at: 2026-09-15T08:31:08+08:00
  - status: PASSED
    at: 2026-09-15T08:45:53+08:00
prior_experiment: EXP-016-CLEANUP-QUIESCENCE
hypothesis: The clean candidate preserves 20 first-attempt execute passes and automatic external cleanup succeeds inside the bounded quiescence window.
prediction: Both aggregates qualify 20/20, wrapper and systemd exit zero, cleanup_complete is true, Domains 215-220 are RELEASED, and exact ownership readback is empty.
single_variable: Cleanup-only whole-scan stabilization at commit e78564c10214cd19245d6218e2ae434a5ed66395; W6, C2 request, full frozen catalog, execute mode, timeouts, no fallback, and resource policy are unchanged.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp017-w6-qualified
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/g17w6
source_commit: e78564c10214cd19245d6218e2ae434a5ed66395
success_criteria:
  - 20/20 distinct sealed physical PASSED results on first attempts, levels_used [6], and top qualification true.
  - No CUP_POSE_STALE, lease expiry, TRUNCATED_FRAME, fallback, Grounded-SAM execution, OOM, or infrastructure retry.
  - Automatic exact cleanup and all post-run ownership/resource readbacks are clean.
failure_criteria:
  - Any task-point, policy, provenance, cleanup, or source/build mismatch.
invalid_criteria:
  - Pre-runtime harness, host-conflict, evidence-path, monitor, or isolated-unit failure before a valid batch starts.
observed:
  - The detached e78564c10214cd19245d6218e2ae434a5ed66395 candidate completed all 20 distinct execute points PASSED on their first attempt in 388.148 s. Levels used were exactly [6]; qualification and coverage passed with terminal reason POINTS_COMPLETE.
  - All 20 accepted requests used plastic-cup-yolo11n-seg-v1. Every source stamp followed the child readiness fence; the delta was 0.242/0.621/1.329/1.650 s min/median/p95/max. There was no Grounded-SAM execution, fallback, CUP_POSE_STALE, lease expiry, TRUNCATED_FRAME, OOM, or infrastructure retry.
  - READY-to-POSE_ACCEPTED was 0.691/3.838/17.965/18.238 s min/median/p95/max. READY-to-DONE was 62.983/70.520/91.134/103.649 s, comfortably below the unchanged 240 s hard timeout.
  - All dynamic manifests ended DONE with controller and five-joint terminal receipts for seven motion states, task-camera-to-world TF receipts, attached-then-detached Planning Scene evidence, untruncated physical evidence, final table contact, zero fingertip contacts, and paired initial/terminal images. Final XY error was at most 0.002131 m and upright tilt at most 0.006549 rad.
  - The external monitor collected 72 samples. Runner cgroup memory current peaked at 6,168,416,256 B, MemoryPeak at 6,330,949,632 B, cgroup process count at 59, PSS at 6,137,666 KiB, GPU memory at 4,555 MiB, GPU utilization at 9%, and minimum host MemAvailable was 20,435,076 KiB. The unit reported 0 B swap peak.
  - Automatic cleanup succeeded on the first wrapper invocation. Domains 215-220 were RELEASED and verified, the owned process manifest was empty, and exact process/domain/container/socket/GPU/systemd readback was empty or inactive-success.
  - Fresh visual review of both 20-image contact sheets showed each cup initially outside the red destination and each terminal cup centered in it with the gripper open and clear.
conclusion: The child-ready capture fence and bounded cleanup-only scan produce a valid, fully cleaned W6 qualification without relaxing timeout or resource policy.
decision: ADVANCE_TO_FRESH_W8
next_experiment: EXP-018-W8
```

## CP-033 — W6 qualified; W8 authorized

```yaml
checkpoint_id: CP-033
last_valid_experiment: EXP-017-W6
current_hypothesis: The same clean e78564c10214cd19245d6218e2ae434a5ed66395 candidate and frozen C2/no-fallback execute contract can complete the required 20-point W8 population with exact cleanup.
source_commit: e78564c10214cd19245d6218e2ae434a5ed66395
owned_processes: NONE after automatic g17w6 cleanup and independent readback.
confirmed_conclusions:
  - W6 is valid at 20/20 first-attempt physical passes with complete provenance, timing, resource, controller, joint, TF, Planning Scene, physical, and visual evidence.
  - The unchanged 240 s hard timeout retains substantial per-attempt margin at W6.
  - Cleanup-only quiescence stabilization succeeds without weakening fail-closed admission.
retained_runs:
  - EXP-017 report and runtime roots, all 20 sealed point trees, monitor samples, contact sheets, and exact cleanup evidence remain retained.
archived_runs: []
deletion_candidates:
  - Invalid and completed scratch/test trees plus superseded candidate/build/runtime artifacts remain retained pending explicit authorization.
next_command: Build and verify a fresh detached e78564c10214cd19245d6218e2ae434a5ed66395 candidate, then launch isolated W8 batch g18w8 with eight workers and an external monitor.
```

## EXP-018-W8 — Fixed eight-worker qualification

```yaml
experiment_id: EXP-018-W8
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T08:45:53+08:00
  - status: INVALID
    at: 2026-09-15T08:48:00+08:00
prior_experiment: EXP-017-W6
hypothesis: The clean candidate preserves 20 first-attempt execute passes at W8 and automatic external cleanup succeeds inside the bounded quiescence window.
prediction: Both aggregates qualify 20/20, wrapper and systemd exit zero, cleanup_complete is true, Domains 215-222 are RELEASED, and exact ownership readback is empty.
single_variable: Worker count increases from six to eight; code, C2 request, frozen catalog, execute mode, timeout, no-fallback contract, and resource policy are unchanged.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp018-w8-qualified
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/g18w8
source_commit: e78564c10214cd19245d6218e2ae434a5ed66395
success_criteria:
  - 20/20 distinct sealed physical PASSED results on first attempts, levels_used [8], and top qualification true.
  - No CUP_POSE_STALE, lease expiry, TRUNCATED_FRAME, fallback, Grounded-SAM execution, OOM, or infrastructure retry.
  - Automatic exact cleanup and all post-run ownership/resource readbacks are clean.
failure_criteria:
  - Any task-point, policy, provenance, cleanup, or source/build mismatch.
invalid_criteria:
  - Pre-runtime harness, host-conflict, evidence-path, monitor, or isolated-unit failure before a valid batch starts.
observed:
  - The local detached clone succeeded, but submodule initialization failed before build or runtime because Git rejected the local reference repository with `fatal: transport 'file' not allowed`.
conclusion: This is a pre-runtime candidate-construction harness failure and says nothing about W8 behavior. The partial clone and failure log remain retained.
decision: RETRY_WITH_EXPLICIT_LOCAL_FILE_PROTOCOL
next_experiment: EXP-019-W8
```

## EXP-019-W8 — Fixed eight-worker qualification retry

```yaml
experiment_id: EXP-019-W8
status: FAILED
status_history:
  - status: PLANNED
    at: 2026-09-15T08:48:00+08:00
  - status: RUNNING
    at: 2026-09-15T08:50:47+08:00
  - status: FAILED
    at: 2026-09-15T08:54:03+08:00
prior_experiment: EXP-018-W8
hypothesis: Explicitly allowing the known local file transport will construct the same detached candidate without network access; W8 runtime expectations remain unchanged.
prediction: Candidate source/build hashes match W6, both aggregates qualify 20/20, wrapper and systemd exit zero, cleanup_complete is true, Domains 215-222 are RELEASED, and exact ownership readback is empty.
single_variable: Candidate-clone harness explicitly permits the local submodule reference; runtime code/config and the W8 qualification contract are unchanged.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp019-w8-qualified
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/g19w8
source_commit: e78564c10214cd19245d6218e2ae434a5ed66395
success_criteria:
  - 20/20 distinct sealed physical PASSED results on first attempts, levels_used [8], and top qualification true.
  - No CUP_POSE_STALE, lease expiry, TRUNCATED_FRAME, fallback, Grounded-SAM execution, OOM, or infrastructure retry.
  - Automatic exact cleanup and all post-run ownership/resource readbacks are clean.
failure_criteria:
  - Any task-point, policy, provenance, cleanup, or source/build mismatch.
invalid_criteria:
  - Pre-runtime harness, host-conflict, evidence-path, monitor, or isolated-unit failure before a valid batch starts.
observed:
  - The fresh detached e78564c10214cd19245d6218e2ae434a5ed66395 candidate and submodule built cleanly and launched the requested isolated W8/C2/no-fallback execute stack. The first eight distinct points passed on their first attempts.
  - On the second wave, sample_11_mid_right entered the broker queue for worker-07 generation 2 and reached its unchanged 10 s queue deadline before C2 dispatch. The immutable initiating failure is BrokerResponse.QUEUE_TIMEOUT with reason QUEUE_DEADLINE_EXCEEDED; the top aggregate is INFRA_FAILED and qualification is false.
  - Seven sibling second-wave attempts were stopped as INDETERMINATE after the shared broker health loss, and four points never started. No fallback level was used.
  - This was not OOM or resource exhaustion: runner MemoryPeak was 8,285,163,520 B, swap was zero, GPU memory peaked near 4,983 MiB, memory PSI was negligible, and host MemAvailable remained near 18.8 GiB.
  - Automatic wrapper cleanup released Domains 215-222. An idempotent exact cleanup/readback found no owned process, container, socket, GPU application, ROS-domain, or active systemd-unit residue.
conclusion: W8 is a valid product failure at the bounded C2 queue, not an invalid harness run. Each waiting transport handler repeats the service-wide authorization/deadline scan every 20 ms while the independent watchdog performs the same scan, creating O(N-squared) coordinator RPC pressure that can starve dispatch at W8.
decision: REMOVE_DUPLICATE_WAITER_SCANS_WITHOUT_CHANGING_TIMEOUTS
next_experiment: EXP-020-BROKER-WAIT
```

## EXP-020-BROKER-WAIT — Event-driven broker response wait

```yaml
experiment_id: EXP-020-BROKER-WAIT
status: PASSED
prior_experiment: EXP-019-W8
hypothesis: Leaving the independent authorization/deadline watchdog as the one global scan and making response handlers wait on its/executor notifications removes O(N-squared) coordinator traffic while retaining fail-closed lease and deadline checks.
prediction: A focused RED catches waiter-thread global scans; GREEN preserves watchdog timeout wakeup and C2 execution; adjacent and ordinary package gates pass without changing queue, inference, execution, lease, or resource timeouts.
single_variable: PerceptionService wait_response no longer invokes poll_response's service-wide _sync_health scan or wakes every 20 ms; executor completion, watchdog terminal publication, and close remain the notifying authorities.
implementation:
  - wait_response polls only its own Broker request while holding the response condition, then waits until executor completion, a terminal watchdog scan, close, or its unchanged caller deadline.
  - The independent 20 ms watchdog remains responsible for the complete outstanding-request authorization and queue/inference deadline scan and now notifies waiters only when a terminal response changes service state.
  - C2 executor count, 10 s YOLO queue timeout, 20 s YOLO inference timeout, 240 s execute timeout, model/fallback policy, and all lease/resource/cleanup gates are unchanged.
test_evidence:
  - t16br01 is the authoritative RED: the new waiter-thread regression failed because wait_response called poll_response, which immediately entered the caller-thread global _sync_health scan.
  - t16bg01 focused GREEN passed 3/3, covering event-driven wait, independent watchdog inference timeout, and C2 YOLO overlap with serialized Grounded-SAM.
  - t16ba01 adjacent runtime/IPC/Broker gate passed 214/214.
  - t16bp01 is invalid because the unsupplemented host Python could not collect Torch-dependent tests. t16bp02 is invalid because it used a copied install layout and its process did not produce a terminal package report. t16bp03 is invalid because the same copied layout violated source-identity tests.
  - After rebuilding with --symlink-install, t16bp04 passed 3040 ordinary tests with one dependency-only SAM failure and the known concurrent-claim test explicitly deselected. t16bi01 passed those two isolated remainder tests 2/2 with the exact source mapping, Torch 2.13.0+cu130, and NumPy 1.26.4. Combined coverage is all 3042 ordinary tests. No benchmark suite was collected.
source_commit: 4ad2a44c557e6cc60452084ca38212c79ac5722f
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
conclusion: The minimal response-wait repair removes duplicate global authorization scans while preserving the single fail-closed watchdog and all frozen timeout/resource contracts.
decision: COMMIT_AND_RERUN_FIXED_W6
next_experiment: EXP-021-W6
```

## CP-034 — Broker wait repair ready for W6

```yaml
checkpoint_id: CP-034
last_valid_experiment: EXP-020-BROKER-WAIT
current_hypothesis: The event-driven wait repair will retain the qualified W6 physical behavior and remove the W8 broker starvation boundary without changing C2 or any timeout.
source_commit: 4ad2a44c557e6cc60452084ca38212c79ac5722f
owned_processes: NONE after exact EXP-019 automatic cleanup and independent readback.
confirmed_conclusions:
  - EXP-019 proves the W8 limiting boundary is broker queue starvation, not OOM, swap, GPU saturation, physical timeout, or cleanup failure.
  - RED/GREEN and 214 adjacent tests prove waiting handlers no longer multiply the watchdog's global authorization work and watchdog deadlines still wake waiters.
  - All 3042 ordinary package tests are covered by the split clean gate; benchmarks were correctly excluded.
retained_runs:
  - EXP-019 runtime/report, eight sealed PASSED trees, eight stopped second-wave trees, resource monitor, exact failure receipt, and cleanup evidence remain retained.
  - EXP-020 RED/GREEN/adjacent/package evidence and every scratch tree remain retained.
archived_runs: []
deletion_candidates:
  - Failed EXP-019 runtime/report, invalid package-gate scratch trees, and completed test scratch trees; retained pending explicit authorization.
next_command: Commit the minimal broker-wait repair, build a fresh clean detached candidate, and rerun the required fixed W6 gate before any W8 retry.
```

## EXP-021-W6 — Broker-wait repair six-worker qualification

```yaml
experiment_id: EXP-021-W6
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T09:16:12+08:00
  - status: RUNNING
    at: 2026-09-15T09:22:49+08:00
  - status: PASSED
    at: 2026-09-15T09:34:13+08:00
prior_experiment: EXP-020-BROKER-WAIT
hypothesis: Commit 4ad2a44c557e6cc60452084ca38212c79ac5722f preserves all fixed-W6 physical behavior and exact cleanup while removing redundant response-handler authorization scans.
prediction: Both aggregates qualify 20/20 on first attempts, levels_used is [6], wrapper/systemd exit zero, and automatic cleanup plus Domains 215-220 readback are clean.
single_variable: Event-driven PerceptionService response waiting at 4ad2a44c557e6cc60452084ca38212c79ac5722f; W6, C2, catalog, execute mode, all timeouts, no-fallback policy, and resource gates are unchanged.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp021-w6-qualified
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/g21w6
source_commit: 4ad2a44c557e6cc60452084ca38212c79ac5722f
systemd_unit: so101-t16-g21w6.service
systemd_invocation_id: ea2ac83381fc4e59b1a733e3835326cd
monitor_unit: so101-t16-g21w6-monitor.service
monitor_invocation_id: bf0f5be4450148ab84b1b66f414cd329
success_criteria:
  - 20/20 distinct sealed physical PASSED results on first attempts, levels_used [6], and top qualification true.
  - No CUP_POSE_STALE, lease expiry, TRUNCATED_FRAME, fallback, Grounded-SAM execution, OOM, or infrastructure retry.
  - Automatic exact cleanup and all post-run ownership/resource readbacks are clean.
failure_criteria:
  - Any task-point, policy, provenance, cleanup, or source/build mismatch.
invalid_criteria:
  - Pre-runtime harness, host-conflict, evidence-path, monitor, or isolated-unit failure before a valid batch starts.
observed:
  - The fresh detached 4ad2a44c557e6cc60452084ca38212c79ac5722f candidate completed all 20 distinct execute points PASSED on first attempts in 407.812 s. Levels used were exactly [6], qualification and coverage passed, and terminal reason was POINTS_COMPLETE.
  - All 20 requests used plastic-cup-yolo11n-seg-v1 with C2. There was no Grounded-SAM execution, fallback, infrastructure retry, CUP_POSE_STALE, queue/inference timeout, lease expiry, TRUNCATED_FRAME, or OOM.
  - READY-to-POSE_ACCEPTED was 0.933/3.552/21.205/21.859 s min/median/p95/max; READY-to-DONE was 63.659/69.320/97.801/109.893 s. Correctness passed under the unchanged 240 s execute timeout, while the separate 5 s W8 latency SLO is not claimed.
  - All 20 dynamic manifests ended DONE with seven motion-state five-joint terminal receipts, task_camera_frame-to-world TF receipts, attach then detached Planning Scene evidence, untruncated physical evidence, initial/final table contact, zero final fingertip contacts, and paired initial/terminal images. Final XY error was at most 0.002177 m and upright tilt at most 0.006770 rad.
  - The external monitor retained 76 samples. Cgroup memory current peaked at 6,229,217,280 B, monitor MemoryPeak at 6,315,982,848 B, process count at 75, PSS at 6,228,103 KiB, GPU memory at 4,555 MiB, GPU utilization at 9%, and minimum host MemAvailable at 20,392,948 KiB. The unit reported 0 B swap peak in the journal.
  - Automatic cleanup completed and released Domains 215-220. Exact readback found the owned manifest empty and no active domain, owned container, runtime socket, GPU application, or active unit residue.
  - Fresh review of both contact sheets showed every cup outside its point-specific red destination initially and centered on the destination at terminal state, with the gripper open and clear.
conclusion: The event-driven broker response wait preserves a valid fully cleaned W6 gate without relaxing any timeout or resource/physical/visual policy.
decision: ADVANCE_TO_FRESH_W8
next_experiment: EXP-022-W8
```

## CP-035 — Post-repair W6 qualified; W8 authorized

```yaml
checkpoint_id: CP-035
last_valid_experiment: EXP-021-W6
current_hypothesis: The same clean 4ad2a44c557e6cc60452084ca38212c79ac5722f candidate and frozen W8/C2/no-fallback contract can complete all 20 points now that waiting handlers no longer generate O(N-squared) authorization scans.
source_commit: 4ad2a44c557e6cc60452084ca38212c79ac5722f
owned_processes: NONE after automatic g21w6 cleanup and exact independent readback.
confirmed_conclusions:
  - The post-change W6 gate is valid at 20/20 first-attempt physical passes with complete provenance, timing, resource, controller, joint, TF, Planning Scene, physical, visual, and cleanup evidence.
  - The former queue timeout did not recur through all 20 W6 pose admissions; all frozen timeouts and C2 remain unchanged.
  - Correctness is established at W6, but READY-to-POSE p95 exceeds 5 s, so the separate W8 latency SLO remains unproven.
retained_runs:
  - EXP-021 report/runtime roots, all 20 sealed point trees, logs, monitor samples, derived summaries, contact sheets, and cleanup evidence remain retained.
archived_runs: []
deletion_candidates:
  - Invalid build/preflight files inside EXP-021 plus completed/invalid test scratch trees; retained pending explicit authorization.
next_command: Build and verify another fresh detached 4ad2a44c557e6cc60452084ca38212c79ac5722f candidate, then launch isolated W8 batch g22w8 with an external monitor.
```

## EXP-022-W8 — Broker-wait repair eight-worker qualification

```yaml
experiment_id: EXP-022-W8
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T09:34:13+08:00
  - status: RUNNING
    at: 2026-09-15T09:39:24+08:00
  - status: INVALID
    at: 2026-09-15T09:40:07+08:00
prior_experiment: EXP-021-W6
hypothesis: Commit 4ad2a44c557e6cc60452084ca38212c79ac5722f removes the EXP-019 queue-starvation mechanism and can complete the full W8 population under the unchanged C2/no-fallback execute contract.
prediction: Both aggregates qualify 20/20 on first attempts, levels_used is [8], wrapper/systemd exit zero, and automatic cleanup plus Domains 215-222 readback are clean.
single_variable: Worker count increases from six to eight; candidate code, C2, catalog, execute mode, all timeouts, no-fallback policy, and resource gates are unchanged from valid EXP-021.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp022-w8-qualified
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/g22w8
source_commit: 4ad2a44c557e6cc60452084ca38212c79ac5722f
systemd_unit: so101-t16-g22w8.service
systemd_invocation_id: 543d21e7bdba4e57ae3c0822319d2ac2
monitor_unit: so101-t16-g22w8-monitor.service
monitor_invocation_id: 535976ac717244b8ba9602ecccafbaf8
success_criteria:
  - 20/20 distinct sealed physical PASSED results on first attempts, levels_used [8], and top qualification true.
  - No CUP_POSE_STALE, lease expiry, TRUNCATED_FRAME, fallback, Grounded-SAM execution, OOM, or infrastructure retry.
  - Automatic exact cleanup and all post-run ownership/resource readbacks are clean.
failure_criteria:
  - Any task-point, policy, provenance, cleanup, or source/build mismatch.
invalid_criteria:
  - Pre-runtime harness, host-conflict, evidence-path, monitor, or isolated-unit failure before a valid batch starts.
observed:
  - The detached candidate built and passed provenance/preflight, but the runner rejected the batch before allocation because the orchestration step had pre-created the runtime root that the wrapper must create atomically.
  - The immutable initiating error is DUPLICATE_BATCH_EVIDENCE_ROOT. Worker count remained zero, no domain was allocated, and cleanup_complete is true.
conclusion: This is a pre-runtime evidence-path harness error and says nothing about W8 product behavior. The candidate, empty conflicting runtime root, monitor data, and unit journal remain retained without deletion.
decision: RETRY_WITH_NONEXISTENT_RUNTIME_ROOT
next_experiment: EXP-023-W8
```

## EXP-023-W8 — Broker-wait repair eight-worker qualification retry

```yaml
experiment_id: EXP-023-W8
status: FAILED
status_history:
  - status: PLANNED
    at: 2026-09-15T09:40:07+08:00
  - status: RUNNING
    at: 2026-09-15T09:42:04+08:00
  - status: FAILED
    at: 2026-09-15T09:50:10+08:00
prior_experiment: EXP-022-W8
hypothesis: Leaving the new runtime root nonexistent until the wrapper atomically creates it removes the pre-runtime harness conflict; the unchanged repaired candidate can complete the required W8 population.
prediction: Both aggregates qualify 20/20 on first attempts, levels_used is [8], wrapper/systemd exit zero, and automatic cleanup plus Domains 215-222 readback are clean.
single_variable: The orchestration harness no longer pre-creates the runtime root; candidate code, W8/C2, catalog, execute mode, all timeouts, no-fallback policy, and resource gates are unchanged.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp023-w8-qualified
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/g23w8
source_commit: 4ad2a44c557e6cc60452084ca38212c79ac5722f
systemd_unit: so101-t16-g23w8.service
systemd_invocation_id: 89d9c198033f4a3ba5710c7f00a49048
monitor_unit: so101-t16-g23w8-monitor.service
monitor_invocation_id: 1377341015ee42dba49a3d3f6dd47920
success_criteria:
  - 20/20 distinct sealed physical PASSED results on first attempts, levels_used [8], and top qualification true.
  - No CUP_POSE_STALE, lease expiry, TRUNCATED_FRAME, fallback, Grounded-SAM execution, OOM, or infrastructure retry.
  - Automatic exact cleanup and all post-run ownership/resource readbacks are clean.
failure_criteria:
  - Any task-point, policy, provenance, cleanup, or source/build mismatch.
invalid_criteria:
  - Pre-runtime harness, host-conflict, evidence-path, monitor, or isolated-unit failure before a valid batch starts.
observed:
  - All 20 distinct execute points passed on first attempts in 376.968 s at levels_used [8]. The former sample_11_mid_right queue failure did not recur, the broker remained healthy, and every infra-attempt count was zero.
  - Coordinator execution and physical qualification reached POINTS_COMPLETE with qualification_passed true, but the outer wrapper recorded INFRA_FAILED and exited 1 because automatic terminal cleanup could not prove a disappearing PID's metadata inside the existing 5 s cleanup-only process-scan window.
  - The immutable cleanup error is PROC_METADATA_UNVERIFIABLE for PID 1407849. MemoryPeak was 8,449,855,488 B and MemorySwapPeak was zero; this was not OOM or the former broker starvation boundary.
  - The exact same idempotent cleanup later succeeded and released Domains 215-222; independent readback found the owned manifest empty and no active domains, containers, sockets, GPU applications, or active units.
conclusion: W8 physical concurrency and broker correctness reached 20/20, but the run is not a valid W8 qualification because automatic terminal cleanup failed closed. The five-second cleanup quiescence window is shorter than the observed W8 process-shutdown tail.
decision: EXTEND_ONLY_THE_FAIL_CLOSED_CLEANUP_QUIESCENCE_WINDOW
next_experiment: EXP-024-CLEANUP-QUIESCENCE
```

## EXP-024-CLEANUP-QUIESCENCE — Extended fail-closed terminal scan

```yaml
experiment_id: EXP-024-CLEANUP-QUIESCENCE
status: PASSED
prior_experiment: EXP-023-W8
hypothesis: Extending only the cleanup-time retry window for transient procfs identity boundaries from 5 s to 30 s lets W8 teardown quiesce while preserving fail-closed classification for a persistent or non-transient error.
prediction: The focused old-window RED fails after 101 synthetic transient reads, GREEN succeeds on read 102, the persistent-race test remains fail-closed, adjacent cleanup integration passes, and the complete ordinary package gate passes.
single_variable: _PROC_SCAN_QUIESCENCE_ATTEMPTS increases from 101 to 601 at the unchanged 0.05 s interval; allocation scans, identity rules, execute/model timeouts, C2, and resource policy are unchanged.
source_commit: 3228721eaef16c10507ecd58c5588b681c155c03
test_evidence:
  - t16cr02 is invalid because its manual PYTHONPATH did not provide the installed so101_demo namespace.
  - t16cr03 is the authoritative RED and failed exactly because the old 101-attempt window raised PROC_METADATA_UNVERIFIABLE before synthetic read 102.
  - t16cg01 focused GREEN passed 4/4, including short transient recovery, the extended-tail regression, and persistent fail-closed behavior.
  - t16ca01 adjacent adaptive-cleanup integration passed 14/14.
  - t16cp01 was terminated by an orchestration session boundary and is invalid. t16cp02 completed but is invalid because the task-local scratch path made AF_UNIX fixture paths too long.
  - t16cp03 used the shorter registered-root NVMe scratch path and passed all 3043 ordinary tests in 62.89 s. No benchmark suite was collected.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
conclusion: The minimal cleanup-only wait extension covers the observed W8 teardown tail without accepting unverifiable state or weakening any execution/resource deadline.
decision: COMMIT_AND_RERUN_FIXED_W6
next_experiment: EXP-025-W6
```

## CP-036 — Cleanup repair ready for mandatory W6 replay

```yaml
checkpoint_id: CP-036
last_valid_experiment: EXP-024-CLEANUP-QUIESCENCE
current_hypothesis: Commit 3228721eaef16c10507ecd58c5588b681c155c03 preserves W6 behavior and permits the same automatic cleanup to wait through the longer W8 shutdown tail.
source_commit: 3228721eaef16c10507ecd58c5588b681c155c03
owned_processes: NONE after exact EXP-023 manual cleanup and independent readback.
confirmed_conclusions:
  - EXP-023 establishes 20/20 W8 physical and broker execution but is not a valid W8 gate because its wrapper cleanup exited nonzero.
  - The cleanup-only change remains fail-closed after 30 s and changes no runtime execution, model, lease, queue, inference, or resource deadline.
  - Focused, adjacent, and all 3043 ordinary tests pass; benchmarks were correctly excluded.
retained_runs:
  - EXP-022 invalid harness evidence, EXP-023 complete physical/runtime/cleanup-failure evidence, and every RED/GREEN/package scratch tree remain retained.
archived_runs: []
deletion_candidates:
  - EXP-022's empty conflicting runtime root and all invalid/completed test scratch trees; retained pending explicit authorization.
next_command: Build a fresh detached 3228721eaef16c10507ecd58c5588b681c155c03 candidate and rerun fixed W6 before another W8 attempt.
```

## EXP-025-W6 — Extended-cleanup six-worker qualification

```yaml
experiment_id: EXP-025-W6
status: FAILED
status_history:
  - status: PLANNED
    at: 2026-09-15T09:59:11+08:00
  - status: RUNNING
    at: 2026-09-15T10:02:02+08:00
  - status: FAILED
    at: 2026-09-15T10:08:52+08:00
prior_experiment: EXP-024-CLEANUP-QUIESCENCE
hypothesis: Commit 3228721eaef16c10507ecd58c5588b681c155c03 preserves the valid W6 physical result and automatic exact cleanup under the unchanged execution contract.
prediction: All 20 points qualify on first attempts at levels_used [6], wrapper/systemd exit zero, and automatic cleanup plus Domains 215-220 readback are clean.
single_variable: Cleanup-only procfs quiescence bound is 30 s; W6/C2, catalog, execute mode, all execution/model/lease timeouts, no-fallback policy, and resource gates are unchanged.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp025-w6-qualified
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/g25w6
source_commit: 3228721eaef16c10507ecd58c5588b681c155c03
systemd_unit: so101-t16-g25w6.service
systemd_invocation_id: ff45025300b84794aa78d8827b523b90
monitor_unit: so101-t16-g25w6-monitor.service
monitor_invocation_id: 1ae8e7fff0c745a39de809d1a61d49a1
success_criteria:
  - 20/20 distinct sealed physical PASSED results on first attempts, levels_used [6], and top qualification true.
  - No CUP_POSE_STALE, lease expiry, TRUNCATED_FRAME, fallback, Grounded-SAM execution, OOM, or infrastructure retry.
  - Automatic exact cleanup and all post-run ownership/resource readbacks are clean.
failure_criteria:
  - Any task-point, policy, provenance, cleanup, or source/build mismatch.
invalid_criteria:
  - Pre-runtime harness, host-conflict, evidence-path, monitor, or isolated-unit failure before a valid batch starts.
observed:
  - All 20 points passed first attempts in 403.972 s at levels_used [6], broker health stayed true, coordinator cleanup was complete, and every per-point infra-attempt count was zero.
  - Process, container, action, and coordinator cleanup gates all succeeded, but the pool still returned cleanup_complete false and the wrapper exited 1 before its outer cleanup succeeded 11 s later.
  - Because every preceding cleanup term was true, the only false term was adaptive resource release. WorkerResourceAllocator.release_persistent_claims still used one direct procfs domain scan and did not use the new CLI cleanup retry helper.
  - Outer cleanup then released Domains 215-220 and exact readback found no owned process, domain, container, socket, GPU application, or active unit residue. MemoryPeak was 6,274,015,232 B and swap peak was zero.
conclusion: EXP-025 is a valid product cleanup failure despite 20/20 physical passes. EXP-024 repaired the outer cleanup layer but not the earlier internal persistent-claim release point.
decision: APPLY_BOUNDED_QUIESCENCE_TO_INTERNAL_CLAIM_RELEASE
next_experiment: EXP-026-INTERNAL-CLEANUP
```

## EXP-026-INTERNAL-CLEANUP — Allocator claim-release quiescence

```yaml
experiment_id: EXP-026-INTERNAL-CLEANUP
status: PASSED
prior_experiment: EXP-025-W6
hypothesis: Applying the same bounded 30 s fail-closed transient-proc retry only inside WorkerResourceAllocator.release_persistent_claims lets the already verified cleanup release its held domain claims after worker shutdown.
prediction: The focused RED shows the allocator has no extended-tail helper; GREEN covers both internal and outer helpers and persistent fail-closed behavior; adjacent allocator/integration and complete ordinary package gates pass.
single_variable: Internal verified-cleanup domain readback retries only the established transient procfs boundaries for at most 30 s; allocation/admission scans and all execution/model/resource timeouts remain unchanged.
source_commit: f349cd8d1942c31a276b3237c1676eee9f8cce39
test_evidence:
  - t16ir01 is the authoritative RED: resources lacked a cleanup-quiescence helper at the allocator release layer.
  - t16ig01 focused GREEN passed 5/5.
  - t16ia01 allocator/resource/adaptive integration passed 152/152, including the user-owned existing test change without modifying it.
  - t16ip01 passed all 3044 ordinary tests in 63.34 s. No benchmark suite was collected.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
conclusion: Both internal claim release and the outer idempotent cleanup now use bounded retry for only transient shutdown races and remain fail-closed for persistent/unrelated errors.
decision: COMMIT_AND_RERUN_FIXED_W6
next_experiment: EXP-027-W6
```

## CP-037 — Internal cleanup repair ready for W6

```yaml
checkpoint_id: CP-037
last_valid_experiment: EXP-026-INTERNAL-CLEANUP
current_hypothesis: Commit f349cd8d1942c31a276b3237c1676eee9f8cce39 will preserve 20/20 W6 execution and let internal adaptive resource release publish cleanup_complete before the outer wrapper cleanup.
source_commit: f349cd8d1942c31a276b3237c1676eee9f8cce39
owned_processes: NONE after EXP-025 outer cleanup and exact readback.
confirmed_conclusions:
  - The W6 and W8 physical/broker paths have each reached 20/20; the remaining invalidity is isolated to internal terminal domain-claim release.
  - The actual release point now has the same bounded transient-only retry and persistent errors still fail closed.
  - All 3044 ordinary tests pass; benchmarks were excluded.
retained_runs:
  - EXP-025 report/runtime and all EXP-026 test evidence remain retained.
archived_runs: []
deletion_candidates:
  - Completed and invalid scratch trees from EXP-024/026 and failed EXP-025 runtime/report; retained pending explicit authorization.
next_command: Build a fresh detached f349cd8d1942c31a276b3237c1676eee9f8cce39 candidate and repeat W6 before W8.
```

## EXP-027-W6 — Internal-cleanup repair six-worker qualification

```yaml
experiment_id: EXP-027-W6
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T10:14:15+08:00
  - status: RUNNING
    at: 2026-09-15T10:16:55+08:00
  - status: PASSED
    at: 2026-09-15T10:24:01+08:00
prior_experiment: EXP-026-INTERNAL-CLEANUP
hypothesis: Commit f349cd8d1942c31a276b3237c1676eee9f8cce39 preserves the 20/20 W6 physical result and completes internal plus outer exact cleanup automatically.
prediction: All 20 points qualify on first attempts at levels_used [6], top status COMPLETED, wrapper/systemd exit zero, and Domains 215-220 plus ownership readback are clean.
single_variable: Internal verified-cleanup procfs quiescence is now bounded at 30 s; W6/C2, execute mode, all execution/model/lease timeouts, no fallback, and resource gates are unchanged.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp027-w6-qualified
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/g27w6
source_commit: f349cd8d1942c31a276b3237c1676eee9f8cce39
systemd_unit: so101-t16-g27w6.service
systemd_invocation_id: aab81eb7e5614b09afbd5af19f4ecc94
monitor_unit: so101-t16-g27w6-monitor.service
monitor_invocation_id: be9ec942348c43589f644327b3e4f9f7
success_criteria:
  - 20/20 distinct sealed physical PASSED results on first attempts, levels_used [6], and top qualification true.
  - No CUP_POSE_STALE, lease expiry, TRUNCATED_FRAME, fallback, Grounded-SAM execution, OOM, or infrastructure retry.
  - Automatic exact cleanup and all post-run ownership/resource readbacks are clean.
failure_criteria:
  - Any task-point, policy, provenance, cleanup, or source/build mismatch.
invalid_criteria:
  - Pre-runtime harness, host-conflict, evidence-path, monitor, or isolated-unit failure before a valid batch starts.
observed:
  - The fresh detached f349cd8d1942c31a276b3237c1676eee9f8cce39 candidate completed all 20 distinct execute points PASSED on first attempts in 397.699 s at levels_used [6]. Top status was COMPLETED and systemd exited 0.
  - All requests used plastic-cup-yolo11n-seg-v1 with C2. There was no Grounded-SAM execution, fallback, infra retry, CUP_POSE_STALE, queue/inference timeout, lease expiry, TRUNCATED_FRAME, or OOM.
  - Internal coordinator/process/container cleanup, adaptive claim release, and outer idempotent cleanup all completed. Domains 215-220 were RELEASED and exact readback found no owned process, active domain, container, socket, GPU application, or active unit residue.
  - READY-to-POSE_ACCEPTED was 0.854/3.464/7.366/7.981 s min/median/p95/max. The separate 5 s latency SLO is not met at W6 and is not claimed.
  - All 20 sealed manifests passed controller/joint, task_camera_frame-to-world TF, attach/detach Planning Scene, untruncated initial/final physical contact, final gripper-clear, and paired-image checks. Maximum final XY error was 0.002168 m, maximum upright tilt 0.006659 rad, and minimum displacement 0.037567 m.
  - The external monitor retained 74 samples: cgroup memory current/peak maxima were 6,114,590,720/6,467,674,112 B, PSS peaked at 6,192,735 KiB, process count at 65, GPU memory/utilization at 4,555 MiB/9%, and host MemAvailable never fell below 20,603,952 KiB. Swap peak was zero.
  - Fresh inspection of both contact sheets confirmed every cup began outside its point-specific red destination and ended centered on it with the gripper open and clear.
conclusion: The internal cleanup repair produces a fully valid W6 20/20 gate with automatic exact cleanup and unchanged execution policy.
decision: ADVANCE_TO_FRESH_W8
next_experiment: EXP-028-W8
```

## CP-038 — Final repaired W6 qualified; W8 authorized

```yaml
checkpoint_id: CP-038
last_valid_experiment: EXP-027-W6
current_hypothesis: The same f349cd8d1942c31a276b3237c1676eee9f8cce39 candidate can retain the already observed W8 20/20 broker/physical behavior and now complete internal plus outer cleanup automatically.
source_commit: f349cd8d1942c31a276b3237c1676eee9f8cce39
owned_processes: NONE after automatic EXP-027 cleanup and exact readback.
confirmed_conclusions:
  - Post-change W6 is valid 20/20 with systemd exit 0 and every provenance, physical, visual, resource, and cleanup gate complete.
  - EXP-023 already proved the broker-wait change eliminates W8 queue starvation through 20/20; only its pre-fix internal cleanup release invalidated that run.
  - Correctness passes at W6, while READY-to-POSE p95 remains above 5 s; no latency-SLO claim is made.
retained_runs:
  - EXP-027 report/runtime, 20 sealed point trees, monitor samples, derived summaries, contact sheets, logs, and exact cleanup evidence remain retained.
archived_runs: []
deletion_candidates:
  - Failed EXP-023/025, invalid EXP-022, and completed/invalid scratch trees remain retained pending explicit authorization.
next_command: Build and verify a fresh detached f349cd8d1942c31a276b3237c1676eee9f8cce39 candidate, then launch the final isolated W8 batch with an absent runtime root.
```

## EXP-028-W8 — Final eight-worker qualification

```yaml
experiment_id: EXP-028-W8
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T10:28:16+08:00
  - status: RUNNING
    at: 2026-09-15T10:30:11+08:00
  - status: PASSED
    at: 2026-09-15T10:37:33+08:00
prior_experiment: EXP-027-W6
hypothesis: Commit f349cd8d1942c31a276b3237c1676eee9f8cce39 preserves the observed W8 20/20 physical/broker result and completes both internal and outer exact cleanup automatically.
prediction: All 20 points qualify on first attempts at levels_used [8], top status COMPLETED, wrapper/systemd exit zero, and Domains 215-222 plus ownership readback are clean.
single_variable: Worker count increases from six to eight; candidate, C2, catalog, execute mode, all execution/model/lease timeouts, no fallback, cleanup policy, and resource gates are unchanged.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-16-w6-w8-success-optimization/exp028-w8-qualified
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/g28w8
source_commit: f349cd8d1942c31a276b3237c1676eee9f8cce39
systemd_unit: so101-t16-g28w8.service
systemd_invocation_id: 479167f73d1549e19719ee566605e0cf
monitor_unit: so101-t16-g28w8-monitor.service
monitor_invocation_id: 752fecd67c7b46578e13c7ee32363721
success_criteria:
  - 20/20 distinct sealed physical PASSED results on first attempts, levels_used [8], and top qualification true.
  - No CUP_POSE_STALE, lease expiry, TRUNCATED_FRAME, fallback, Grounded-SAM execution, OOM, or infrastructure retry.
  - Automatic exact cleanup and all post-run ownership/resource readbacks are clean.
failure_criteria:
  - Any task-point, policy, provenance, cleanup, or source/build mismatch.
invalid_criteria:
  - Pre-runtime harness, host-conflict, evidence-path, monitor, or isolated-unit failure before a valid batch starts.
observed:
  - The fresh detached f349cd8d1942c31a276b3237c1676eee9f8cce39 candidate completed all 20 distinct execute points PASSED on first attempts in 387.605 s at levels_used [8]. Top status was COMPLETED and systemd exited 0.
  - All requests used plastic-cup-yolo11n-seg-v1 with exactly two YOLO executors. There was no Grounded-SAM execution, fallback, infra retry, CUP_POSE_STALE, queue/inference timeout, lease expiry, TRUNCATED_FRAME, or OOM.
  - READY-to-POSE_ACCEPTED was 0.706/8.628/16.419/16.948 s min/median/p95/max; POSE_ACCEPTED-to-DONE was 64.214/68.227/85.004/87.148 s and READY-to-DONE was 65.532/76.844/101.286/101.357 s. The five-second W8 READY-to-POSE SLO is false and is not claimed.
  - Source-stamp minus READY ROS time was positive for every request at 0.160/0.454/1.178/3.618 s min/median/p95/max, proving every accepted source crossed the readiness fence.
  - All 20 sealed manifests passed controller/five-joint planning receipt, task_camera_frame-to-world TF, Planning Scene attach/detach, untruncated initial and terminal physical evidence, initial/final table contact, final zero fingertip contact, and paired initial/terminal image checks. Maximum final XY error was 0.002161 m, maximum upright tilt 0.006682 rad, and minimum displacement 0.037555 m.
  - Fresh inspection of both W8 contact sheets confirmed every cup began outside its point-specific red destination and ended centered on it with the gripper open and clear.
  - The external monitor retained 71 samples: cgroup memory current/peak maxima were 8,131,194,880/8,226,263,040 B, PSS peaked at 8,083,739 KiB, process count at 105, GPU memory/utilization at 4,983 MiB/12%, and host MemAvailable never fell below 18,501,380 KiB. Swap peak was zero; retained samples include CPU, memory, and IO PSI distributions.
  - Internal coordinator/process/container cleanup, adaptive domain release, and outer idempotent cleanup all completed automatically. Domains 215-222 were RELEASED; exact readback found an empty owned-process manifest and no active domain, owned container, runtime socket, GPU compute application, or active systemd unit.
conclusion: The final W8 correctness qualification is valid at 20/20 under the frozen C2/YOLO-only/240 s/no-fallback contract, with complete physical/visual/provenance/resource and exact cleanup evidence. The separate five-second latency SLO is not met.
decision: COMPLETE_TASK_WITH_CORRECTNESS_PASS_AND_SLO_FAIL
next_experiment: NONE
```

## CP-039 — W6 and W8 success optimization complete

```yaml
checkpoint_id: CP-039
status: COMPLETE
last_valid_experiment: EXP-028-W8
source_commit: f349cd8d1942c31a276b3237c1676eee9f8cce39
owned_processes: NONE after automatic EXP-028 cleanup and exact independent readback.
confirmed_conclusions:
  - The original exact 240 s boundary was caused by the parent publishing its capture before the child armed its freshness fence; the child correctly rejected all pre-ready frames. Commit 79993774536a4e6c9280f92eaedbc815f94096b9 moved the receipt after arm and made parent capture post-fence.
  - W8 queue starvation was caused by every waiter repeating a service-wide authorization scan in addition to the watchdog, generating O(N-squared) coordinator traffic under the broker lock. Commit 4ad2a44c557e6cc60452084ca38212c79ac5722f made response waiting event-driven while preserving the watchdog and all timeouts.
  - Terminal cleanup needed the same bounded transient-proc quiescence at both the outer idempotent cleanup and internal allocator claim-release layers. Commits 3228721eaef16c10507ecd58c5588b681c155c03 and f349cd8d1942c31a276b3237c1676eee9f8cce39 add 30 s cleanup-only retry while remaining fail-closed and leaving admission/runtime timeouts untouched.
  - Fresh fixed W6 EXP-027 and W8 EXP-028 each pass 20/20 execute points on first attempts, with top COMPLETED, no fallback or infra retry, and exact automatic cleanup.
  - Correctness qualification is complete. W8 READY-to-POSE p95 is 16.419 s, so the historical five-second latency SLO is not met.
verification:
  - Focused RED/GREEN, adjacent, and complete ordinary package gates cover each repair; the final package population is 3044/3044 and no benchmark was collected.
  - Detached candidates were clean at their exact commits, submodule c16b5a5fe880b6e1857f56486dab4ae726576969 matched, and source/build hashes matched before each valid run.
  - EXP-027 and EXP-028 derived summaries, contact sheets, checksums, unit journals, monitor streams, manifests, and cleanup readbacks are retained.
retained_runs:
  - Every task run and test tree under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01 remains retained, including invalid/failed EXP-022, EXP-023, EXP-025 and successful EXP-027/EXP-028.
archived_runs: []
deletion_candidates:
  - Superseded candidate/build/report/runtime roots and all completed or invalid scratch trees are deletion candidates, but remain retained pending explicit user authorization.
external_actions:
  - No branch push, merge, force-push, evidence deletion, or host-wide service/policy change was performed.
next_command: NONE
```

## CP-043 — Stateless perception Broker design pivot

```yaml
checkpoint_id: CP-043
status: ACTIVE
last_valid_experiment: EXP-030-W16-GREEN
last_executed_experiment: EXP-033-W10-R2
current_hypothesis: Removing all Coordinator authentication, authorization, lease, start-event, and journal work from the inference lifecycle will let bounded W10/C2 requests reach detector execution while stale motion and final-result admission remain rejected by their existing owners.
source_commit: a982edc734b96a2f76ec8002c4c16c573f3639a5
working_tree_status: Preserved user src/so101_demo_py/test/test_parallel_batch_resources.py is modified and MUJOCO_LOG.TXT is untracked; interrupted strict-authority task edits are present in the ledger, Broker, Coordinator, IPC, runtime, CLI, and tests and will be transformed with targeted patches only.
owned_processes: NONE; so101-exp034-full-gate-r7.service is not-found/inactive, ROS Domains 0 and 215-224 are empty, Docker has no running container, and the GPU has no compute client.
preserved_processes: Existing unrelated tmux sessions and host processes remain untouched.
confirmed_conclusions:
  - CP-042 and EXP-034-W10-AUTH-HOTPATH-RED are superseded by the user-approved stateless perception Broker design before EXP-034 ran.
  - EXP-033 remains a valid W10 failure at Broker request completion before detector work, with physical action absent and exact cleanup complete; it is not acceptance evidence for the replacement design.
  - The registered evidence root remains /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01 and the dispatch receipt 266aa04f-a2e4-4f86-a295-0f8b4a568809 was verified as exact 36-byte content.
  - The Broker must own only correlation, bounded queues/executors, deadlines, health, model provenance, serialization, and metrics; Coordinator/Worker control sockets retain scheduling, action, cleanup, and final-result authority.
disproven_routes:
  - Adding or optimizing Coordinator inference authorization, start-event validation, or journal lookup is no longer part of the accepted architecture.
  - EXP-034 strict-authority tests or instrumentation cannot qualify the stateless Broker.
open_risks:
  - Existing interrupted edits include strict Coordinator authorize_inference code and Broker authority metrics that must not survive on the inference path.
  - Focused RED/GREEN, package, real-YOLO W10/C2, and fixed-W10 20-point acceptance are not yet complete.
next_command: Run EXP-035-STATELESS-BROKER-RED from a fresh verified NVMe scratch after adding only the approved stateless Broker contract tests.
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01 and every prior registered-root artifact remain retained.
archived_runs: []
deletion_candidates:
  - Existing completed and invalid scratch, candidate, and runtime trees remain deletion candidates exactly as previously recorded; none is deleted without explicit user authorization.
```

## EXP-035-STATELESS-BROKER-RED — Coordinator-free inference contract

```yaml
experiment_id: EXP-035-STATELESS-BROKER-RED
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T14:54:00+08:00
  - status: RUNNING
    at: 2026-09-15T15:04:00+08:00
  - status: PASSED
    at: 2026-09-15T15:06:00+08:00
prior_experiment: EXP-033-W10-R2
hypothesis: The current Broker cannot satisfy the approved stateless request/response boundary because inference still requires Coordinator-backed authentication/authorization and start-event identity.
prediction: Focused tests fail before implementation when a Broker runs without an authority server, ten C2 completions are deliberately reordered, duplicate semantic inputs use distinct request IDs, queue-full is prompt, and one request deadline is isolated from another request.
single_variable: Add only replacement contract tests; production inference code remains unchanged for RED.
lifecycle: ISOLATED_STACK
preconditions:
  - Source begins at a982edc734b96a2f76ec8002c4c16c573f3639a5 with all existing dirty paths preserved.
  - No ROS, MuJoCo, MoveIt, Gazebo, Docker, GPU, or physical action is started.
  - Pytest uses exact /usr/bin/python3 with a unique previously nonexistent scratch/tmp under the registered durable evidence root and verified tempfile routing.
success_criteria:
  - Tests collect and fail only at absent stateless Broker contracts, including zero Coordinator callbacks and zero journal replay.
failure_criteria:
  - Tests pass against the old authority path or fail from import, scratch, socket-length, or fixture contamination.
invalid_criteria:
  - Source, Python, scratch, process, or preserved-user-change provenance differs from this record.
provenance:
  source_commit: a982edc734b96a2f76ec8002c4c16c573f3639a5
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install/so101_demo_py
  runtime_executable: /usr/bin/python3
  ros_domain_id: 0
  gz_partition: no-live-stack
commands:
  - command: PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q src/so101_demo_py/test/test_parallel_broker_hot_path.py --junitxml=/data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s35red3/red.xml
    exit_code: 1
observed:
  - s35red1 collected five tests but all failed on missing so101_demo imports because the overlay was not sourced; retained as INVALID_ENV and excluded.
  - s35red2 stopped before collection because the symlink-install module correctly resolved through this worktree build tree rather than the overly strict source-path preflight; retained as INVALID_PREFLIGHT and excluded.
  - Authoritative s35red3 verified /usr/bin/python3, tempfile routing to the fresh NVMe scratch, and so101_demo resolution through this worktree build overlay before collecting five tests.
  - All five tests failed at the intended absent contracts: BrokerTransport requires authority_call and PerceptionBroker requires authorize. No import, fixture, socket, ROS, simulator, Docker, or GPU boundary failed.
inferred:
  - The current inference path cannot start independently from Coordinator authority, before minimal scheduling-field, correlation, duplicate, queue, or request-deadline behavior can be exercised.
conclusion: VALID RED; Coordinator authority is still a required construction dependency at both transport and Broker boundaries.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp035-stateless-broker-red-r3.log
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s35red3/red.xml
decision: IMPLEMENT_MINIMAL_STATELESS_BOUNDARY
next_experiment: EXP-036-STATELESS-BROKER-GREEN
```

## EXP-036-STATELESS-BROKER-GREEN — Focused implementation gate

```yaml
experiment_id: EXP-036-STATELESS-BROKER-GREEN
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T15:09:00+08:00
  - status: RUNNING
    at: 2026-09-15T15:13:00+08:00
  - status: PASSED
    at: 2026-09-15T15:16:00+08:00
prior_experiment: EXP-035-STATELESS-BROKER-RED
hypothesis: The minimal stateless Broker boundary can serve ten independent clients through two YOLO executors without any Coordinator authority or journal dependency, while preserving exact correlation, queue bounds, duplicate recomputation, and isolated request deadlines.
prediction: The five authoritative focused contract tests pass under the exact worktree overlay and a fresh verified NVMe scratch directory.
single_variable: Transform the interrupted strict-authority implementation into the user-approved stateless inference boundary; do not change robot motion, final-result admission, model fallback policy, or adaptive Worker defaults.
lifecycle: NO_LIVE_ROBOT_STACK
preconditions:
  - EXP-035 is a valid RED and all preserved user changes remain untouched.
  - Pytest uses exact /usr/bin/python3 with a unique previously nonexistent scratch/tmp under the registered durable evidence root and verified tempfile routing.
success_criteria:
  - All five focused tests pass with W10/C2 reordered completions, exact request/model/version response identity, two recomputations for distinct IDs, prompt queue-full, isolated deadline failure, and metrics with no authority/journal fields.
failure_criteria:
  - Any focused contract fails or imports from outside the worktree build/install overlay.
invalid_criteria:
  - Scratch routing, Python identity, source provenance, or preserved-user-change isolation is not verified.
observed:
  - s36green1 stopped before collection because its provenance assertion was over-specific to a build-tree symlink representation; it is retained as INVALID_PREFLIGHT.
  - s36green2 collected five tests: the two local queue/deadline contracts passed, while three fixture defects surfaced after the production boundary became reachable; no production contract failure was inferred from that run.
  - s36green3 passed four tests and exposed only a nondeterministic executor-index assertion in the single-request fixture; C2 may correctly select executor 0 or 1.
  - Authoritative s36green4 verified exact /usr/bin/python3, tempfile routing, and the specific parallel_ipc module inside this worktree, then passed all five tests in 0.92 s (1.19 s elapsed).
conclusion: The focused stateless Broker contract is GREEN; no inference request entered Coordinator authorization or journal replay, and W10/C2 correlation and request isolation passed.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp036-stateless-broker-green-r4.log
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s36green4/green.xml
decision: PROCEED_TO_INTEGRATION_GATE
next_experiment: EXP-037-STATELESS-BROKER-INTEGRATION
```

## EXP-037-STATELESS-BROKER-INTEGRATION — Existing contract compatibility

```yaml
experiment_id: EXP-037-STATELESS-BROKER-INTEGRATION
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T15:17:00+08:00
  - status: RUNNING
    at: 2026-09-15T15:20:00+08:00
  - status: PASSED
    at: 2026-09-15T15:31:00+08:00
prior_experiment: EXP-036-STATELESS-BROKER-GREEN
hypothesis: Removing the superseded inference-authority semantics and adapting existing Broker, IPC, runtime, fault, and CLI contracts will preserve all non-inference control-plane and detector safety invariants.
prediction: Focused integration files pass after obsolete authority-specific assertions are replaced by stateless boundary assertions, with no edits to the preserved user resource test.
single_variable: Integration compatibility for the approved Broker API and runtime specification only.
lifecycle: NO_LIVE_ROBOT_STACK
preconditions:
  - EXP-036 authoritative focused gate passed.
  - Every pytest invocation uses fresh verified NVMe scratch and exact /usr/bin/python3.
success_criteria:
  - Broker, IPC, perception-runtime, fault-injection, container, and CLI focused tests pass without Coordinator inference authorization or Broker authority socket/token expectations.
failure_criteria:
  - A non-obsolete safety invariant regresses or the focused integration files do not pass.
invalid_criteria:
  - Test provenance or scratch routing is not verified.
observed:
  - s37diag1 exposed only expected obsolete-constructor and authority-semantic tests after collection; it is diagnostic, not acceptance evidence.
  - Targeted compatibility edits removed Coordinator inference authorization assertions, retained control-plane token/lease tests, and changed timeout/queue-full checks to require per-request isolation.
  - Authoritative s37green1 passed 201 Broker, IPC, runtime, and fault-injection tests in 19.98 s.
  - s37diag4 exposed four remaining obsolete Broker-authority/response-fixture assertions; s37green2 then stopped at a test indentation error before collection and is invalid.
  - Authoritative s37green3 passed 142 CLI, adaptive-pool, and container tests in 4.47 s, including absence of Broker authority endpoint/token fields and preserved Worker control authority.
conclusion: Focused integration is GREEN across 343 tests; the Broker has no Coordinator authority socket/token/callback, while Worker-local pose/motion admission and Coordinator final-result controls remain tested.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp037-stateless-broker-integration-green-r1.log
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s37green1/green.xml
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp037-stateless-broker-cli-green-r3.log
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s37green3/green.xml
decision: PROCEED_TO_ORDINARY_PACKAGE_GATE
next_experiment: EXP-038-ORDINARY-PACKAGE-GATE
```

## EXP-038-ORDINARY-PACKAGE-GATE — Full non-benchmark regression

```yaml
experiment_id: EXP-038-ORDINARY-PACKAGE-GATE
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T15:31:00+08:00
  - status: RUNNING
    at: 2026-09-15T15:43:25+08:00
  - status: PASSED
    at: 2026-09-15T15:50:00+08:00
prior_experiment: EXP-037-STATELESS-BROKER-INTEGRATION
hypothesis: The stateless Broker implementation preserves every ordinary non-benchmark package contract outside the focused integration set.
prediction: The complete src/so101_demo_py/test suite passes under exact /usr/bin/python3 with benchmark_test excluded by path.
single_variable: Full ordinary regression coverage; no further product change before the gate.
lifecycle: NO_LIVE_ROBOT_STACK
preconditions:
  - EXP-036 and EXP-037 are GREEN.
  - Exact worktree module provenance and fresh NVMe tempfile routing are verified.
success_criteria:
  - Complete ordinary test directory passes; benchmark_test is not collected.
failure_criteria:
  - Any ordinary test fails.
invalid_criteria:
  - Wrong Python/module/scratch provenance or benchmark collection.
observed:
  - s38package1 stopped before collection because the plain system Python environment lacked the established Torch dependency; it is retained as INVALID_ENV and excluded.
  - s38package2 passed 3026 tests and exposed two pre-existing order-sensitive failures: the preserved user-owned concurrent Domain-claim test and the real-launch cleanup timing test. Both passed unchanged together in fresh s38rerun1.
  - s38package3 passed 3027 tests and reproduced only the cleanup timing failure when process cleanup ran after multithreaded detector tests; this diagnostic run is retained and is not the acceptance result.
  - s38package4 first established the clean ordering and passed 3028 tests. Subsequent review removed a legacy-required outer Broker envelope, the dead replay metric, and the remaining authority-server scaffolding, and made the caller end-to-end deadline mandatory.
  - Post-review s38review2 passed 46 Broker/IPC tests; s38review3 exposed only short caller deadlines in legacy fake-clock fixtures; corrected s38review4 passed 424 expanded Broker/runtime/ROS tests and s38review5 passed 142 CLI/container tests. s38review1 is invalid because ROS setup rejected shell nounset before collection.
  - s38package5 failed before test execution because systemd-run was given a non-executable script directly. s38package6 and s38package7 were stopped after exact unit identity readback when later review edits made their import state nonauthoritative; all are retained as diagnostics.
  - Authoritative s38package8 ran in isolated user unit so101-exp038-full-gate-r8.service with the resource-sensitive test first, the real-launch process cleanup test second, and the remaining ordinary files afterward in one pytest process.
  - The authoritative run verified /usr/bin/python3, worktree module provenance, and tempfile routing to the fresh /data NVMe scratch, excluded benchmark_test by path, passed all 3028 tests with four existing fork warnings in 331.90 s, and exited success in 333.24 s.
conclusion: The complete ordinary non-benchmark package gate is GREEN; the stateless Broker change preserves all 3028 collected ordinary contracts when the established process/resource ordering is applied.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp038-ordinary-package-gate-r8-preflight.log SHA256 1e0f76c29f59e924cfde37f2ec39bbd500dd956bd915c671d31a6a8adba98daf
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp038-ordinary-package-gate-r8.log SHA256 d3e053b5eaca1cfa992c9815f5eef15cf463073459f450124ac05ab67fb08efa
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp038-ordinary-package-gate-r8-elapsed.log SHA256 637f80f4fbda356e54a6c7797c8c227ff5603747bc7a6679374e5f8f29ecf837
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s38package8/package.xml SHA256 6a12dd688dd51a0926906e0aa5c9ee1c9489f66ffdd6b5adfcec52c08eec5a21
retained_runs:
  - Every s38package1 through s38package8 and s38review1 through s38review5 tree, including authoritative s38package8, remains retained under the registered evidence root.
deletion_candidates:
  - Every EXP-038 scratch tree is a deletion candidate after readback but remains retained pending explicit user authorization.
decision: CREATE_REVIEWABLE_CANDIDATE_THEN_RUN_REAL_YOLO
next_experiment: EXP-039-REAL-YOLO-W10-C2
```

## EXP-039-REAL-YOLO-W10-C2 — Stateless real-detector concurrency qualification

```yaml
experiment_id: EXP-039-REAL-YOLO-W10-C2
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T15:51:00+08:00
  - status: RUNNING
    at: 2026-09-15T16:17:00+08:00
  - status: PASSED
    at: 2026-09-15T16:18:00+08:00
prior_experiment: EXP-038-ORDINARY-PACKAGE-GATE
hypothesis: A Broker image built from the committed stateless candidate can serve ten simultaneous immutable YOLO inputs with two CUDA executors without any Coordinator inference endpoint or journal access.
prediction: All ten independent requests return correlated terminal YOLO responses; Broker metrics report ten logical inferences, bounded queueing, model_active_peak no greater than two, and no transport error.
single_variable: Replace the prior authority-coupled Broker source/image with the committed stateless candidate; keep the frozen image base, dependency pins, YOLO weights, model hash, C2 executor policy, and request limits unchanged.
lifecycle: PERCEPTION_ONLY_GPU
preconditions:
  - The post-review EXP-038 full package gate passes and task-owned changes are committed without the preserved user resource-test edit or MUJOCO_LOG.TXT.
  - An immutable candidate-equivalent source/build/install tree and Broker image are verified against that commit and the frozen model hashes.
  - No ROS simulator, MoveIt, controller, motion, Worker pool, Coordinator authority server, conflicting container, or unrelated GPU compute client is active.
  - Ten sealed 0400 .npy inputs, a bounded W10/C2 runtime specification, socket lengths, container identity, and exact cleanup targets are frozen before launch.
success_criteria:
  - Ten concurrent clients receive ten exact request_id/model_id/model_version terminal responses with YOLO-first execution and no cross-wire.
  - Metrics record logical_inference_count 10, queue depth within configured capacity, YOLO active peak at most 2, zero Coordinator inference calls, no Broker journal/replay field, and no transport errors.
  - Exact cleanup leaves no task-owned Broker process, socket, container, or GPU client.
failure_criteria:
  - Any missing, duplicated, cross-wired, nonterminal, non-YOLO, provenance-invalid, over-C2, transport-error, authority-dependent, or cleanup-incomplete result.
invalid_criteria:
  - Candidate/image/model/config/input provenance differs from the frozen preflight, another process owns a required resource, or the experiment starts simulation or motion.
provenance:
  candidate_commit: b0f9e7168198285fba4133026d9d3b132075f88b
  implementation_commit: 59c831f0d771f45f6b930dd59fc85d673a7c96e5
  submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  install_overlay: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp039-real-yolo-w10-c2/candidate-src/install/so101_demo_py
  broker_image_id: sha256:4fb57abe1109e7cc1c7fbf1780a7dd10b4167f12abfa59ba34b1903a60c4c972
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
  harness_sha256: e4cfbb3c970f8e3117a866f83193c8030f56c0811075b038deca8f0b431360bf
  runner_sha256: cb61e55c53b08fbc94f9e748325301ef0aa02a03c0c4ae18fd0e6fbd00266058
systemd_unit: so101-exp039-real-yolo.service
observed:
  - The detached candidate was clean at b0f9e7168198285fba4133026d9d3b132075f88b with implementation parent 59c831f0d771f45f6b930dd59fc85d673a7c96e5, matching submodule, source/build hashes, install entry point, frozen model hashes, and exact image provenance.
  - Direct ai-station preflight found the registered root at mode 0700, no running container or GPU compute client, no task runtime, and no simulation or motion process; the only process-search hit was the read-only preflight command itself.
  - The first and only frozen launch reached strict Broker READY in 8.816 s, accepted ten simultaneous minimal envelopes with no lease, token, Worker generation, start event, Coordinator endpoint, or journal, and returned ten exact request_id/model_id/model_version responses.
  - All ten real YOLO results were QUALIFIED. Client elapsed time ranged from 0.0984 s to 0.1465 s with 0.1251 s median; completion order differed from request order without cross-wiring.
  - Broker metrics recorded pending_rpc_peak 10, queue_depth_peak 8, YOLO model_active_peak 2, logical_inference_count 10 with the ten exact request IDs, no replay/authority/journal field, and zero transport errors.
  - A precise SIGINT to the exact labeled container let the Broker persist final metrics; the expected Docker runner exit was 130. The systemd harness exited 0, and independent readback found the exact owned PID absent, no labeled container, no GPU compute application, and no live socket.
conclusion: Real-YOLO perception-only W10/C2 is qualified for the committed stateless Broker candidate with exact correlation, bounded concurrency/backpressure, zero Coordinator inference work, and exact cleanup.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp039-real-yolo-w10-c2/preflight.txt SHA256 189c24605ffb67901e9c3c91fd603dc598dd8597cffe8889f1f1a71c4bed8a6d
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp039-real-yolo-w10-c2/broker-image.json SHA256 cc464527f589e48617475970ed72f413d8224bdb424b353e2a39708c69cd9d02
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp039-real-yolo-w10-c2/admission.json SHA256 f6de8440dd55733d60322dc4536761c7b6f260d58d3cf2cd3b740340b22f3321
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp039-real-yolo-w10-c2/result.json SHA256 bac7409f1712fb5fe26d94e91598c7b9a5b9a302439fc7b52f6a49e6bf322556
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp039-real-yolo-w10-c2/run/ipc/broker-concurrency-summary.json SHA256 6e758a93b617f9be11a446ea72128a44a695a25d67ff48be8231364b4911ed6c
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp039-real-yolo-w10-c2/harness.log SHA256 a3b37ce9086e2c865817cb87ef1a0a731320a2928c93e4907f7909d325ecd99f
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp039-real-yolo-w10-c2/broker.log SHA256 255e6de912407de62381b5f9c592dd0d6f051c6240e0884e6e24bf6cab843b4d
retained_runs:
  - The clean candidate tree, build output, image build/readback, sealed input copies, runtime specification, response payloads, metrics, and logs remain retained under exp039-real-yolo-w10-c2.
deletion_candidates:
  - The completed EXP-039 candidate/build tree, copied inputs, stopped runtime root, and temporary test harness are deletion candidates but remain retained pending explicit user authorization.
decision: PROCEED_TO_ONE_FIXED_W10_20_POINT_GATE
next_experiment: EXP-040-FIXED-W10-20-POINT
```

## EXP-040-FIXED-W10-20-POINT — One unmasked execute qualification

```yaml
experiment_id: EXP-040-FIXED-W10-20-POINT
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T16:20:00+08:00
  - status: RUNNING
    at: 2026-09-15T16:27:31+08:00
  - status: PASSED
    at: 2026-09-15T16:32:31+08:00
prior_experiment: EXP-039-REAL-YOLO-W10-C2
hypothesis: The exact stateless candidate and Broker image qualified by EXP-039 remove the prior W10 inference stall and can complete the frozen twenty-point execute catalog at fixed W10/C2 without retry, fallback, or policy drift.
prediction: One fresh W10 generation completes all 20 distinct points PASSED on first attempts with levels_used [10], no lower Worker level, no Grounded-SAM fallback, complete physical/contact/model/timing/visual evidence, and exact cleanup.
single_variable: Replace EXP-033's authority-coupled Broker candidate/image with the exact EXP-039 stateless candidate/image; preserve W10, C2, catalog, model artifacts, initial_points_per_worker 3, worker_start_timeout_s 120, max_infra_attempts_per_point 1, timeout policy, and execute semantics.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-039 passed ten real concurrent YOLO requests with exact cleanup.
  - The fixed run uses candidate b0f9e7168198285fba4133026d9d3b132075f88b, image sha256:4fb57abe1109e7cc1c7fbf1780a7dd10b4167f12abfa59ba34b1903a60c4c972, and the same frozen model hashes.
  - A fresh short batch/runtime identity keeps every Unix socket within its enforced limit; the report and runtime roots are absent.
  - Domains 215-224, prospective units, claims, ROS graphs/daemons, task processes, containers, and GPU compute clients are empty immediately before launch.
  - Fresh video/visual evidence procedure follows gazebo-video-debug together with so101-dev; no deadline, retry, fallback, Worker count, model, or point policy changes are allowed after launch.
success_criteria:
  - Exactly 20 distinct frozen catalog points are PASSED on first attempts in one W10 generation; levels_used is exactly [10], final_worker_count is 10, systemd exits 0, and no fallback transition or infrastructure retry occurs.
  - Every point has exact Broker request/response identity and model/timing evidence plus controller/five-joint, TF, Planning Scene attach/detach, physical/contact, initial/final image, source-fence, and fresh visual evidence.
  - Exact cleanup leaves no task-owned Worker, Broker, ROS, simulator, monitor, container, socket, GPU process, or unreleased Domain claim.
failure_criteria:
  - Any started point, first-attempt, W10-only, perception, motion, contact, evidence, provenance, systemd, or cleanup criterion fails; preserve the first new boundary and do not retry, tune, or fall back.
invalid_criteria:
  - A pre-runtime provenance, path, host-resource, or harness fault prevents the genuine fixed-W10 stack from starting.
provenance:
  candidate_commit: b0f9e7168198285fba4133026d9d3b132075f88b
  implementation_commit: 59c831f0d771f45f6b930dd59fc85d673a7c96e5
  submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  broker_image_id: sha256:4fb57abe1109e7cc1c7fbf1780a7dd10b4167f12abfa59ba34b1903a60c4c972
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
  evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp040-fixed-w10-20-point
  runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/z
  systemd_unit: so101-w10-z.service
  monitor_unit: so101-w10-z-monitor.service
  runner_invocation_id: 1184991d90ca41d49edf9a1401caab06
  monitor_invocation_id: bf7475491259418fb32e6536edc2cce1
observed:
  - The final preflight verified a clean detached candidate at b0f9e7168198285fba4133026d9d3b132075f88b, submodule c16b5a5fe880b6e1857f56486dab4ae726576969, matching source/build overlay files, exact Broker image and model hashes, root mode 0700, absent r/z, empty Domains 215-224 and ROS graphs, no container or GPU client, and the production-enumerated 107-byte longest socket within its exact limit.
  - Two prelaunch diagnostic checks are retained: the first stopped before launch on an incorrect assumption that symlink-install Python modules existed as regular installed files, and the next used a nonexistent coordinator-authority pathname for a prospective length report. The corrected final preflight used the egg-link/import target and production adaptive_socket_paths enumerator. Neither diagnostic created the runtime or started a stack.
  - The gui-capture inventory found an active GNOME desktop but no Gazebo client window. The frozen production Worker specification uses headless EGL and GZ_PARTITION not_applicable, so no unrelated GUI was started; fresh per-point initial and terminal RGB evidence was generated and inspected instead.
  - Exactly one formal launch started at 16:27:31 with runner invocation 1184991d90ca41d49edf9a1401caab06 and monitor invocation bf7475491259418fb32e6536edc2cce1. All ten Workers passed the READY action/service/controller gate and executed one W10 generation.
  - The top aggregate completed in 300.0503854181152 s with status COMPLETED, terminal reason POINTS_COMPLETE, 20/20 distinct points PASSED, levels_used [10], initial/final Worker count 10, zero infra attempts, and no fallback transition. Every point used exactly attempt 1.
  - Independent sealed-evidence validation found 20 unique request IDs with exact pose/request correlation and only model plastic-cup-yolo11n-seg-v1. All required file hashes, input hashes, source fences, synchronized depth/TF timestamps, untruncated physical frames, MoveIt attach/detach and final detached scene, seven five-joint terminal motion states, initial/final table contact, final fingertip clearance, and DONE evidence passed.
  - Fresh contact-sheet inspection found 20 distinct upright initial cup placements and 20 upright terminal cups in the red target-ring region with the gripper visibly raised and clear. Numeric corroboration measured maximum final XY error 0.0021397056023529444 m, maximum upright tilt 0.006774546362813859 rad, and minimum XY displacement 0.037565573692793876 m.
  - Ready-to-pose timing was 0.3212-3.3206 s with 1.0964 s median and 3.3196 s p95. Peak sampled cgroup memory was 10334068736 bytes, peak GPU allocation 5412 MiB, peak GPU utilization 15 percent, and minimum host available memory 16554492 KiB.
  - Automatic cleanup gates and the outer cleanup receipt passed. A cleanup ROS-graph probe unexpectedly spawned short-lived Domains 215-224 CLI daemons despite ROS2CLI_NO_DAEMON; the production run also left one Domain 0 CLI daemon. All eleven exact PIDs were resolved against the empty preflight, the ten probe daemons exited before signaling, and the remaining Domain 0 daemon was terminated precisely. Final non-spawning readback found no runtime process, ROS daemon, labeled container, socket, GPU client, active unit, or held Domain 215-224 claim.
conclusion: The committed stateless perception Broker candidate is qualified by one unmasked fixed-W10/C2 20-point execute run with exact first-attempt correlation, complete physical and fresh visual evidence, no retry, model fallback, Worker reduction, or policy drift, and exact cleanup.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp040-fixed-w10-20-point/preflight.txt SHA256 808493ac9b52ea7979a937a31b3e6b27001759c59bc39bf20452569924587a3b
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp040-fixed-w10-20-point/aggregate_results.json SHA256 b0d0f7943010dd9c18c24f672508fc2e571e855ffe131badb1e6e6bc24fac762
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp040-fixed-w10-20-point/coordinator-aggregate-results.json SHA256 d413fc52bc633c882f2855ef928638f7e87906dde5a281f5fff729bf07a270b7
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp040-fixed-w10-20-point/evidence-validation.json SHA256 5c3258e80cc40c0281950842db4da5512bf79bd2467dc92d9f8888fc7760933c
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp040-fixed-w10-20-point/timing-summary.json SHA256 4b07649353aac6f7fa178093c7d0254bcf7755b08a0fbb34d583e37cb9425a4c
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp040-fixed-w10-20-point/resource-summary.json SHA256 a12ac5b370017da8be7fc2e4c50dfe997eabc94c0e8a0686fe73b3fb35348db0
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp040-fixed-w10-20-point/initial-contact-sheet.png SHA256 a14821af8e0d0473cc43bde9dbee0d2619004aacc4c8941634f0493606e26819
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp040-fixed-w10-20-point/terminal-contact-sheet.png SHA256 4b11ce83e2f3d7ab2d03531c00362fd3ea74a87a97c70a10a784ac90e69c4e3b
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp040-fixed-w10-20-point/visual-observation.txt SHA256 62fb1c20ed3d99effbeb14bd3ebc6330d4001c2addf7c5786543a03c26bd10cc
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp040-fixed-w10-20-point/final-cleanup-readback.txt SHA256 9f136697a9f34753b40bbf386552a5a500d889387be6d27a9c02cf8e921358ca
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp039-real-yolo-w10-c2
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp040-fixed-w10-20-point
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/z
archived_runs: []
deletion_candidates:
  - The completed EXP-039 candidate/build/runtime assets, completed EXP-040 report/runtime tree, and all prior retained test scratch and diagnostic trees under the registered evidence root are deletion candidates after readback but remain retained pending explicit user authorization.
decision: ACCEPT_STATELESS_BROKER_AND_FIXED_W10_QUALIFICATION
next_experiment: NONE
```

## CP-044 — Stateless Broker implementation and W10 closeout

```yaml
checkpoint_id: CP-044
status: COMPLETE
last_valid_experiment: EXP-040-FIXED-W10-20-POINT
last_executed_experiment: EXP-040-FIXED-W10-20-POINT
source_commits:
  - 59c831f0d771f45f6b930dd59fc85d673a7c96e5 feat: make perception broker stateless
  - b0f9e7168198285fba4133026d9d3b132075f88b chore: ignore MuJoCo runtime log
confirmed_conclusions:
  - The Broker inference path is stateless with respect to Coordinator leases, start events, authorization services, and journal replay while motion and final-result authority remain outside the Broker.
  - Focused, integration, CLI/container, and the complete 3028-test ordinary package gate passed; benchmark_test was not collected.
  - Real-YOLO perception-only W10/C2 passed ten simultaneous requests with exact out-of-order correlation and active YOLO peak two.
  - One fixed W10/C2 execute generation passed all 20 catalog points on first attempts with no retry, Grounded-SAM fallback, Worker reduction, or timeout/policy change.
  - Exact final cleanup found no task-owned runtime, ROS daemon, simulator, Worker, Broker, container, socket, GPU client, active unit, or held Domain claim.
preserved_user_changes:
  - src/so101_demo_py/test/test_parallel_batch_resources.py remains modified and unstaged exactly as found.
owned_runtime: NONE
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01
archived_runs: []
deletion_candidates:
  - All completed candidates, run roots, diagnostics, ordinary-test scratch trees, and EXP-039/EXP-040 artifacts under the retained registered evidence root; none were deleted.
external_actions:
  - No push, merge, evidence deletion, Worker fallback, model substitution, timeout increase, or extra W10 execution was performed.
open_risk: NONE_WITHIN_APPROVED_SCOPE
next_command: NONE
```

## CP-042 — W10 Broker hot-path repair startup

```yaml
checkpoint_id: CP-042
status: ACTIVE
last_valid_experiment: EXP-030-W16-GREEN
last_executed_experiment: EXP-033-W10-R2
current_hypothesis: Repeated full coordinator-journal replay on the authorization hot path, amplified by the 20 ms service watchdog, starves W10 requests before useful detector work.
source_commit: a982edc734b96a2f76ec8002c4c16c573f3639a5
working_tree_status: Preserved user src/so101_demo_py/test/test_parallel_batch_resources.py is modified and MUJOCO_LOG.TXT is untracked; this ledger is the only task-owned change.
owned_processes: NONE; no active SO-101 unit, ROS graph on Domains 0 or 215-224, container, GPU compute application, or held Domain lock was observed.
preserved_processes: Existing tmux sessions codex and codex-task-so101-w10-resume are untouched.
confirmed_conclusions:
  - The checkout is the required linked worktree on codex/parallel-adaptive-worker-pool at a982edc734b96a2f76ec8002c4c16c573f3639a5 with submodule c16b5a5fe880b6e1857f56486dab4ae726576969.
  - The registered evidence root is owned by uid 1000 with mode 0700; the installed so101_demo_py overlay resolves to this worktree.
  - CP-041 remains authoritative: EXP-033 formed ten READY Workers and failed all ten first Broker requests before perception returned; W8 remains the highest runtime-qualified level.
disproven_routes:
  - Increasing request timeouts, authority handler count, or YOLO executor count is prohibited as a diagnosis substitute.
open_risks:
  - The retained EXP-033 evidence bounds but does not localize the stall within the Broker/authority path.
next_command: Add phase and authorization/replay instrumentation plus a ten-client real-Coordinator regression, then run the fresh-scratch RED/A-B before any production fix.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/preflight/w10-hot-path-startup.txt SHA256 f0cdb0b4a2d4780d135a21518238739ae158e199ff28388af67d81f9e8b7c167
```

## EXP-034-W10-AUTH-HOTPATH-RED — Real Coordinator authorization-path diagnostic

```yaml
experiment_id: EXP-034-W10-AUTH-HOTPATH-RED
status: PLANNED
prior_experiment: EXP-033-W10-R2
hypothesis: Ten concurrent authenticated inference requests stall before model scheduling because each authorization invokes full journal replay and the 20 ms watchdog multiplies those calls across outstanding requests.
prediction: Against unchanged production code and a real hash-chained Coordinator journal populated with EXP-033-scale renewals, ten clients produce excessive replay count/bytes and fail the bounded fast-detector completion contract before or at authorization/queueing; a single-variable cached in-memory authorization A/B reaches queued/model_started/completed for all ten.
single_variable: Authorization lookup implementation only: current full journal replay versus an atomic Coordinator in-memory event-index lookup. Detector behavior is deterministic and fast; transport, authentication, request count, identities, deadlines, and C2 scheduling remain identical.
lifecycle: ISOLATED_STACK
preconditions:
  - Source begins at a982edc734b96a2f76ec8002c4c16c573f3639a5 and preserved user dirty paths remain untouched.
  - The reproducer uses real AuthenticatedUnixServer/client transport and real Coordinator authority/journal state with ten Workers and EXP-033-scale renewal history, but no ROS, MuJoCo, MoveIt, Gazebo, Docker, GPU, or physical action.
  - Every pytest run uses a fresh previously nonexistent short scratch root under the registered durable evidence root with exact /usr/bin/python3 tempfile verification.
success_criteria:
  - Durable request traces distinguish accepted, authenticated, authorized, queued, model_started with executor index, model_completed, serialized, sent, timeout phase/start, authority call latency/count, and journal replay count/bytes.
  - RED fails at the expected old authorization/replay hot path rather than import, socket path, scratch reuse, or fixture collision.
  - The A/B changes the first failing boundary and excludes queue/executor wakeup and transport lifecycle as the initiating cause.
failure_criteria:
  - Old production completes within the bounded contract with low replay work, disproving the leading hypothesis and selecting exactly one competing hypothesis for the next experiment.
invalid_criteria:
  - Wrong source/import, overlong socket path, reused scratch, fixture collision, missing phase evidence, or unrelated host/runtime contamination.
provenance:
  source_commit: a982edc734b96a2f76ec8002c4c16c573f3639a5
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install/so101_demo_py
  runtime_executable: /usr/bin/python3
  ros_domain_id: 0
  gz_partition: no-live-stack
commands:
  - command: PENDING focused real-code W10 concurrency RED/A-B under a fresh registered scratch root
    exit_code: PENDING
observed:
  - PENDING
inferred:
  - PENDING
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp034-w10-auth-hotpath-red
decision: PENDING
next_experiment: NONE
```

## CP-040 — W16 ceiling and W10 runtime baseline

```yaml
checkpoint_id: CP-040
status: COMPLETE
last_valid_experiment: EXP-030-W16-GREEN
source_commit: b5cd54bd3f28cf26c2dec01989e277f9bcba7953
working_tree_status: Task-owned ledger update plus preserved user src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT; no other dirty path.
owned_processes: NONE; no SO-101, MoveIt, MuJoCo, Gazebo, Broker, Docker, GPU-compute, or ROS-domain runtime is active.
preserved_processes: Existing codex and codex-task-so101-w6-w8-success-opt tmux sessions remain untouched; codex-cua is absent.
confirmed_conclusions:
  - CP-039 is the final trusted prior checkpoint: fixed W6 and W8 each passed 20/20 on first attempts with exact cleanup at f349cd8d1942c31a276b3237c1676eee9f8cce39.
  - The task started from codex/parallel-adaptive-worker-pool at e04b03700c9d341f263f84d0f75e9b8fd8a69a97 with submodule c16b5a5fe880b6e1857f56486dab4ae726576969.
  - Domains 0 and 215-230 had empty ROS graphs, but the first graph probe unintentionally left one ros2-daemon in each Domain. Exact per-Domain `ros2 daemon stop` retired all 17 task-created daemons; PID readback is empty. Claims 215-222 are RELEASED with cleanup_verified true; claims 223-230 are absent. No container or GPU compute application is active.
  - Static inspection and post-GREEN rescan found independent W8 ceilings in adaptive contracts, the frozen Domain pool, Broker transport plus service queue/handler validation, top-level cleanup active-pool identity validation, the scaling launcher, and the exact fault injector target set.
  - Commit b5cd54bd3f28cf26c2dec01989e277f9bcba7953 raises those optional ceilings to W16 and rejects W17 without changing the W8 default, fallback ladder, C2 policy, timeout policy, or identity formatting.
  - EXP-030 passed 11 focused tests, 344 adjacent tests, the preserved resource file's independent 137-test gate, and the complete 3050-test ordinary package gate; benchmark_test was not collected.
  - Final completion verification used fresh scratch/v32c-final with verified system Python and tempfile routing; all 3050 ordinary tests passed again in 62.10 s with four existing fork warnings and no benchmark collection.
  - EXP-031 is terminally INVALID before runtime: the registered evidence root was mode 0775, while the adaptive CLI requires an existing evidence root to be owned by the caller and mode exactly 0700. The runner exited before creating r/g31w0 or any Worker, Broker, or point attempt.
  - Exact post-failure readback found Domains 215-224 empty with no claims or daemons, no owned process, container, runtime socket, or GPU compute application, and both transient units inactive. No retry, fallback, tuning, W16 live run, push, merge, or deletion was performed.
disproven_routes:
  - Changing the default worker count to W16 or changing the existing fallback sequence is outside the requested contract.
  - Reviving AdmissionAuthority, systemd Authority/watchdog, signature, or hard-cgroup admission designs is prohibited and unnecessary.
open_risks:
  - W10 full-stack memory, process, latency, Broker, correctness, and cleanup behavior remains unmeasured because EXP-031 did not pass its pre-runtime evidence-root gate.
  - W16 support will be contract-tested only; no W16 live run is authorized.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/preflight/host-state.txt SHA256 20f9626fbbf9ace49448c1a3509c7901c4bd208568e6185f2eebb2c30c849ecc
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/preflight/ros-daemon-cleanup.txt SHA256 0e7f3481cda487bb6c3b504439575a791322c9f1de73a0faba6d44e3c19d85e0
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp032-final-verification.log SHA256 13b10577ca285c1ad103bee61076883139c1baf9e71448b94984ab75e4a34b9b
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/v32c-final/so101-demo-py.xml SHA256 61ce6978708f4f9b1d8da5dc1cec57b22738f9f6724066685db1d80d49260c7d
retained_runs:
  - All prior evidence remains under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01.
  - The new handoff, dispatch receipt, preflight, test scratch trees, detached candidate, image build, and invalid EXP-031 launch evidence are retained under /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01.
archived_runs: []
deletion_candidates:
  - All completed test scratch trees, including invalid pre-pytest v32-final, PATH-corrupted v32b-final, and valid v32c-final, plus the detached candidate/build tree and invalid EXP-031 report are deletion candidates but remain retained pending explicit user authorization.
next_command: NONE; a fresh W10 attempt requires explicit authorization and a new evidence root whose mode is verified as 0700 before launch.
```

## EXP-029-W16-RED — Optional ceiling contract

```yaml
experiment_id: EXP-029-W16-RED
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-15T11:06:00+08:00
  - status: RUNNING
    at: 2026-09-15T11:08:00+08:00
  - status: VALID
    at: 2026-09-15T11:11:00+08:00
prior_experiment: EXP-028-W8
hypothesis: The current product rejects W16 independently at adaptive option construction, Broker queue/handler validation, and top-level cleanup identity because those boundaries still encode W8.
prediction: Tests written before production changes fail for W16 acceptance while confirming the default remains W8, its fallback ladder remains (6, 4, 2, 1), and W17 must remain rejected.
single_variable: Add contract tests only; production source and configuration remain unchanged for RED.
lifecycle: ISOLATED_STACK
preconditions:
  - Source is e04b03700c9d341f263f84d0f75e9b8fd8a69a97 in the existing linked worktree.
  - The preserved user test_parallel_batch_resources.py and MUJOCO_LOG.TXT remain untouched and unstaged.
  - The test uses exact /usr/bin/python3 with a unique previously nonexistent scratch/tmp below the registered durable evidence root and starts no live SO-101 stack.
success_criteria:
  - Focused tests collect and fail only because W16 or Domain 223-230 support is missing at the named runtime and cleanup boundaries.
  - The tests independently assert W16 acceptance, W17 rejection, default W8/fallback compatibility, sixteen unique Domains 215-230, two-digit W10/W16 identities, and Broker W16 queue/handler limits.
failure_criteria:
  - Tests pass before implementation or fail because of import, fixture, scratch, or unrelated preserved-file behavior.
invalid_criteria:
  - Source, Python, TMPDIR, evidence-root, or preserved dirty-file provenance differs from the preconditions.
provenance:
  source_commit: e04b03700c9d341f263f84d0f75e9b8fd8a69a97
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: 0
  gz_partition: no-live-stack
commands:
  - command: Seven focused default/domain/adaptive/CLI/cleanup/IPC/path tests using scratch/r29/tmp
    exit_code: 1
  - command: Focused scaling-launcher W16/W17 dry-run test using scratch/r29b/tmp
    exit_code: 1
observed:
  - The first RED collected seven tests: six failed at the intended old ceiling boundaries and the two-digit W10/W16 path-format test passed. Pytest reported 6 failed, 1 passed, 0 errors in 0.49 s.
  - The failed boundaries were the eight-entry default Domain pool, AdaptiveWorkerOptions W16 rejection, CLI W16 rejection, cleanup ACTIVE_POOL_IDENTITY rejection, AuthenticatedUnixServer handler rejection, and Broker queue-capacity rejection.
  - The first shell's post-pytest result recorder used zsh's reserved status variable. This did not alter the pytest exit, full log, or JUnit; a checksum-sealed supplemental result records exit 1 and the 0.49 s pytest duration.
  - The separate scaling launcher RED collected one test and failed one in 0.05 s because the wrapper rejected W16 as unsupported. W17 was not reached until W16 support exists.
  - A post-implementation ceiling rescan found two deeper unchanged Broker limits. Supplemental scratch/r29c collected two tests and failed both at the intended service queue and container-entry runtime validation boundaries in 0.29 s.
  - The same rescan found the maintained exact fault injector still capped at worker-08. Supplemental scratch/r29d collected one test and failed at TARGET_NOT_ALLOWED for worker-16 in 0.08 s.
inferred:
  - The old ceiling was independently enforced at every runtime, Broker, cleanup, launcher, and fault-injection boundary found by the final source rescan; no unrelated fixture, import, scratch, or preserved user-file error occurred in the authoritative RED runs.
conclusion: VALID RED. Production lacked the requested W16 contract at adaptive/configuration, Broker transport/service/container entry, cleanup, scaling-launcher, and fault-injector boundaries.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp029-red.log SHA256 a3882660ef98395a09c3422ea4d5fedd55591f5ec9ad7654779a4f5e3316cb44
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/r29/red.xml SHA256 c97cfb115f031fa746ab2c4089aee6bdbee7a867513db7d0bcccca2bb913cea6
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp029-red-scaling.log SHA256 a9b233dcbeaaa5077b923014eb706f2c38654431fbff4e292c124a6c2e91d629
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/r29b/red.xml SHA256 b6e20b609259cb70bd8ab87f2153319afb2dd8b82c85fcde6f1595f3a5f15f6f
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp029-red-deep-broker.log SHA256 5384f2cd409d8259f820e4359fe78fb8784abf9b85fc61f119a15086b64cb196
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/r29c/red.xml SHA256 a24371500b84e99e9ac82a16655ba97a4f7987f268928963b0a69e3cb4db05b6
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp029-red-fault-injector.log SHA256 fab779f367f791f3fc48fb620cb6abdbea67e916eb0dae5f0c9f28f9fd487344
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/r29d/red.xml SHA256 8ff0117425bd96d804efd6044373fd4002628909b89f85fbd0130dc3ea9e845a
decision: KEEP_AND_RUN_GREEN
next_experiment: EXP-030-W16-GREEN
```

## EXP-030-W16-GREEN — Optional ceiling implementation

```yaml
experiment_id: EXP-030-W16-GREEN
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T11:11:00+08:00
  - status: RUNNING
    at: 2026-09-15T11:12:00+08:00
  - status: PASSED
    at: 2026-09-15T11:35:32+08:00
prior_experiment: EXP-029-W16-RED
hypothesis: Raising only the shared adaptive, Broker, cleanup, Domain-pool, and explicit scaling-launcher ceilings to 16 will satisfy W16/W17 behavior without changing the W8 default, fallback ladder, C2 model policy, timeout policy, or two-digit identities.
prediction: The eight focused tests pass, adjacent adaptive/IPC/resource/cleanup/CLI tests pass, and the complete ordinary so101_demo_py gate reports zero failures with benchmark_test excluded.
single_variable: Supported optional worker ceiling and available Domain/connection/queue capacity increase from 8 to 16; defaults and runtime policies remain unchanged.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-029 is a valid RED against source e04b03700c9d341f263f84d0f75e9b8fd8a69a97.
  - Production changes are limited to adaptive maximum 16, Domain pool 215-230, Broker handler/queue maximum 16, cleanup identity maximum 16, and scaling-launcher request validation.
  - Maintained Chinese design/plan text states default W8, optional ceiling W16, and W10 as an explicit experiment; deprecated admission mechanisms remain absent.
success_criteria:
  - Focused GREEN passes all eleven W16/W17/default/domain/Broker/cleanup/path/launcher/fault-injector tests.
  - Adjacent and complete ordinary package tests pass with unique verified NVMe scratch roots; benchmark_test is not collected.
failure_criteria:
  - Any task-owned focused, adjacent, or package test fails.
invalid_criteria:
  - Wrong Python/source mapping, reused scratch, overlong fixture path, missing dependency, or preserved dirty-file interference invalidates that invocation.
provenance:
  source_commit: WORKING_TREE_ON_e04b03700c9d341f263f84d0f75e9b8fd8a69a97
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: 0
  gz_partition: no-live-stack
commands:
  - command: Eleven focused W16/W17/default/domain/Broker/cleanup/path/launcher/fault-injector tests using scratch/g30c/tmp
    exit_code: 0
  - command: Eight adjacent adaptive/CLI/IPC/Broker/container/fault-injector files using scratch/a30d/tmp
    exit_code: 0
  - command: Complete 160-file ordinary test collection with test_parallel_batch_resources.py first to avoid the proven cross-file `rc` fixture collision, using scratch/p30e/tmp
    exit_code: 0
observed:
  - Focused GREEN passed 11/11 in 0.28 s. W16 is accepted and W17 rejected at adaptive options, CLI, Broker transport, Broker service, container-entry runtime validation, external cleanup, scaling launcher, and fault injector; W10/W16 identities remain two-digit.
  - The final adjacent gate passed 344/344 in 8.05 s. The preserved user resource file passed 137/137 independently in the authoritative scratch/a30-resources-final gate.
  - Two combined diagnostic gates exposed no product regression: CLI's existing `scratch/rc` claim directory can collide with the resource test's thirteenth short evidence root `rc`, making the otherwise valid concurrent-claim test depend on which thread wins. PDB recorded one rejection as ROS_DOMAIN_CLAIMED: 181 and the other as DIRECTORY_CONFLICT at `rc`.
  - The authoritative complete ordinary collection therefore ran the resource file first and all other ordinary files after it in the same pytest invocation. It passed 3050/3050 in 61.72 s with four existing fork warnings; the benchmark suite was not collected.
  - The first complete-gate diagnostic lacked frozen Torch site-packages and was invalid at collection. The next unordered complete run reproduced only the proven cross-file `rc` fixture collision. All diagnostic and authoritative scratch trees remain retained.
  - `git diff --check`, zsh syntax validation, Python compilation, and a final source scan found no remaining adaptive W8 ceiling. Remaining literal 8 values are unrelated frame-size, journal-frame, and kinematic-sampling constants.
inferred:
  - The optional runtime ceiling is consistently W16 while the default remains W8 with fallback (6, 4, 2, 1), C2, frozen model identities, timeouts, and two-digit worker identities unchanged.
  - W16 is contract- and ordinary-test supported only; no W16 live qualification is claimed or authorized.
conclusion: The minimal W16 ceiling extension passes all focused, adjacent, and ordinary gates without changing default adaptive behavior or benchmark scope.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp030-focused-green-final.log SHA256 d5e68cd69f5c7643e255f2efb236c446e2d55118652f426ebc184d0bdb9e778f
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/g30c/green.xml SHA256 a6bab378d9f13da493de46f225a5b75617dbb842f4deab2839ed0d98326a3dd8
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp030-adjacent-final.log SHA256 b14524e7898977a06c8a70c260fb7137f0bb8714fd8e15884e477ac028875e0d
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/a30d/adjacent.xml SHA256 e80800d9f1e1622932855e9e81e8e5fa5ef1ed9b4df34d91e038f9efb28e89dd
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp030-adjacent-resources-final.log SHA256 c861e911cfcd165eb68905e3784689101c7c2fad1bee6e423cbfaa9d0aa72104
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/a30-resources-final/adjacent.xml SHA256 c6c250ea0ff52237b9f39d027a44a46a9426dc456223c042fd1708526568d6a3
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/tests/exp030-full-ordinary-authoritative.log SHA256 e3b88873e9dd7195636ce8d8942206a26d1fe09504e94c86b79eaa07007d3935
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/p30e/so101-demo-py.xml SHA256 02454dc1bc4d40146c22c446bdd009702236ab7094ce0397e18f4a162a2545cd
decision: COMMIT_IMMUTABLE_CANDIDATE_AND_RUN_EXACTLY_ONE_W10
next_experiment: EXP-031-W10
```

## EXP-031-W10 — Explicit ten-worker qualification

```yaml
experiment_id: EXP-031-W10
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T11:37:00+08:00
  - status: RUNNING
    at: 2026-09-15T11:44:58+08:00
  - status: INVALID
    at: 2026-09-15T11:45:00+08:00
prior_experiment: EXP-030-W16-GREEN
hypothesis: The immutable W16-capable candidate can run one genuine W10 generation over the frozen EXP-028 catalog and C2/YOLO-only policy, completing all 20 points on their first attempts with exact cleanup.
prediction: The one authorized W10 batch reaches top COMPLETED with 20/20 PASSED, levels_used [10], zero infra attempts and fallback transitions, healthy Broker, systemd exit zero, and clean Domains 215-224 plus process/container/socket/GPU/unit readback.
single_variable: Requested worker count increases from the qualified EXP-028 W8 to explicit W10; max infra attempts is tightened to the handoff-required one while catalog, execute policy, C2, two YOLO executors, model identities, timeouts, and cleanup rules remain fixed.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp031-w10-qualified
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/g31w0
source_commit: b5cd54bd3f28cf26c2dec01989e277f9bcba7953
systemd_unit: so101-w10-g31.service
monitor_unit: so101-w10-g31-monitor.service
preconditions:
  - EXP-030 passed 11 focused tests, 344 plus 137 adjacent tests, and all 3050 ordinary package tests; no benchmark was collected.
  - A fresh detached candidate must be clean at b5cd54bd3f28cf26c2dec01989e277f9bcba7953 with submodule c16b5a5fe880b6e1857f56486dab4ae726576969 and matching source/build hashes.
  - No existing SO-101 stack, owned container, GPU compute application, or conflicting ROS process/claim may use Domains 215-224; runtime root must be absent.
  - The CLI has no separate empty-fallback spelling. The unchanged default fallback ladder remains configured, but any fallback transition or level other than 10 makes this experiment terminally invalid and cannot be represented as W10 success.
success_criteria:
  - Exactly one W10 pool generation runs all 20 frozen points in execute mode with initial_points_per_worker 3, worker_start_timeout_s 120, max_infra_attempts_per_point 1, and exactly two YOLO executors.
  - All points are distinct, PASSED on first attempts, and retain controller/five-joint, TF, Planning Scene attach/detach, physical/contact, initial/final image, source-fence, and visual contact-sheet evidence.
  - No Grounded-SAM execution, fallback, infra retry, stale pose, queue/inference timeout, lease expiry, truncated frame, OOM, or Broker-health failure occurs.
  - Automatic internal and outer cleanup complete; Domains 215-224, owned processes, container, sockets, GPU applications, runner, and monitor are released with exact readback.
failure_criteria:
  - Any task-point, provenance, policy, first-attempt, Broker, source/build, systemd, evidence, or cleanup gate fails.
invalid_criteria:
  - Any pre-runtime clone/build/path/host/Domain/monitor error occurs before the valid batch starts, or any lower fallback level runs.
provenance:
  source_commit: b5cd54bd3f28cf26c2dec01989e277f9bcba7953
  submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  broker_image_id: sha256:b94b595ed560ba227e1c9dde03532a8699696ca97821f6eb3325574d77e04854
  runner_invocation_id: 1cc9289176d240828c7df708afd3e39b
  monitor_invocation_id: 1a8cd4e095dc4006a015bb73edaad2a1
observed:
  - The detached candidate was clean at the committed source, its submodule and source/build hashes matched, the rebuilt local C2 image identity was frozen, Domains 215-224 were empty, and r/g31w0 was absent.
  - The runner started once at 11:44:58 and exited at 11:45:00 with ADAPTIVE_EVIDENCE_ROOT_INVALID. Stat readback found the existing registered evidence root owned by uid 1000 but mode 0775; the CLI requires mode exactly 0700 at mujoco_parallel_batch.py lines 697-710.
  - The wrapper's unconditional cleanup then reported RUNTIME_ROOT because r/g31w0 had never been created. This is a consequence of the primary pre-runtime rejection, not a second runtime failure.
  - No valid adaptive batch started: zero runtime roots, Workers, Broker containers, point attempts, fallback transitions, Grounded-SAM executions, or visual frames were created. Therefore no contact sheet exists and no W10 correctness or performance claim is made.
  - The independent monitor captured two samples only: launch-time cgroup peak 7,094,272 bytes, host GPU 537 MiB at zero utilization, and no Broker container. The transient runner journal records exit status 1; the monitor stopped cleanly after observing the runner inactive.
  - Exact cleanup readback at 11:47:51 found Domains 215-224 with empty graphs and absent claims, no ROS daemon, owned process, owned container, W10 runtime socket, or GPU compute application, and both units inactive.
inferred:
  - The first divergence was an operator preflight omission: evidence-root mode was recorded only implicitly through existence/ownership checks and was not verified or normalized to the adaptive CLI's exact 0700 contract before launch.
  - Because the handoff requires stopping after any unsuccessful W10 gate, the mode was not changed and the launch was not retried.
conclusion: INVALID before runtime due solely to the registered evidence root's mode 0775; implementation and test qualification remain valid, but W10 live qualification is not established.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp031-w10-qualified/run.log SHA256 f84062109040209e1d9b98faaf99688950014a1927402bee5aef6c575f632a2c
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp031-w10-qualified/resource-monitor.tsv SHA256 22efe998fb82e64328856ff8d3061fe32dc62ff8bcd2bf0f0bb3b826fcc937cf
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp031-w10-qualified/first-divergence.txt SHA256 2a7d32cfab00cff8439cc8bfc4cd69508c867bf3cb58f5313a293214982e7057
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp031-w10-qualified/cleanup-readback.txt SHA256 5f0698ae15b966058700e74c228b886aa6271e45b9bb8dbe95103139583eb9eb
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp031-w10-qualified/core-sha256.txt
decision: STOP_NO_RETRY
next_experiment: NONE
```

## EXP-032-W10-R1 — Authorized genuine ten-worker retry

```yaml
experiment_id: EXP-032-W10-R1
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T12:00:00+08:00
  - status: RUNNING
    at: 2026-09-15T12:04:43+08:00
  - status: INVALID
    at: 2026-09-15T12:04:45+08:00
prior_experiment: EXP-031-W10
hypothesis: Narrowing only the existing registered evidence root from mode 0775 to exact 0700 removes the proven pre-runtime contamination and lets the immutable W16-capable candidate execute the first genuine W10 generation under the frozen EXP-028 policy.
prediction: The CLI accepts the registered root, creates one fresh g32w0 W10 runtime, and the batch reaches top COMPLETED with 20/20 distinct first-attempt PASSED points, levels_used [10], healthy C2 Broker, no fallback or infra retry, complete physical/visual evidence, and exact automatic cleanup.
single_variable: Pre-runtime orchestration correction only: after exact path and current-user ownership readback, narrow /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01 from mode 0775 to exact 0700. Product source, candidate commit, catalog, execute policy, C2, models, timeouts, and worker count remain frozen.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp032-w10-qualified
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/g32w0
source_commit: b5cd54bd3f28cf26c2dec01989e277f9bcba7953
systemd_unit: so101-w10-g32.service
monitor_unit: so101-w10-g32-monitor.service
preconditions:
  - Dispatch receipt 8fe063a6-2921-43e2-84cf-fef21f057c4c exists as exact 36-byte content, and retry-handoff.md authorizes this retry because EXP-031 created no runtime stack or attempt.
  - Worktree HEAD is preserved at e955907c6efc93a5ede31c6f6b450f361f99ee39; implementation commit b5cd54bd3f28cf26c2dec01989e277f9bcba7953 and invalid-attempt ledger commit e955907c6efc93a5ede31c6f6b450f361f99ee39 remain unchanged.
  - A fresh detached candidate must be clean at b5cd54bd3f28cf26c2dec01989e277f9bcba7953 with submodule c16b5a5fe880b6e1857f56486dab4ae726576969 and matching source/build hashes.
  - The registered root resolves exactly to the authorized path, is owned by the current uid, and is mode 0700 after the single authorized correction; report and runtime paths are absent before creation.
  - Domains 215-224, prospective units, owned processes, labeled container, runtime sockets, and GPU compute applications are empty immediately before launch.
success_criteria:
  - Exactly one genuine W10 pool generation runs all 20 frozen points in execute mode with initial_points_per_worker 3, worker_start_timeout_s 120, max_infra_attempts_per_point 1, and exactly two YOLO executors.
  - Top status is COMPLETED; all 20 distinct points are PASSED on first attempts; levels_used is exactly [10]; systemd exits zero; Broker health, queue, and model provenance are valid.
  - No Grounded-SAM execution, fallback, infra retry, stale pose, queue/inference timeout, lease expiry, truncated frame, OOM, or Broker-health failure occurs.
  - Every point retains controller/five-joint, TF, Planning Scene attach/detach, physical/contact, initial/final image, source-fence, and sealed-hash evidence; fresh initial and terminal contact sheets are generated and inspected.
  - Automatic internal and outer cleanup complete; Domains 215-224, owned processes, container, sockets, GPU applications, runner, and monitor are released with exact readback.
failure_criteria:
  - Any started W10 task-point, provenance, policy, first-attempt, Broker, source/build, systemd, evidence, visual, or cleanup gate fails.
invalid_criteria:
  - A pre-runtime harness error prevents the genuine stack from starting; only a trivial deterministic orchestration correction may then be made without changing product semantics.
provenance:
  source_commit: b5cd54bd3f28cf26c2dec01989e277f9bcba7953
  submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  install_overlay: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp032-w10-qualified/candidate-src/install/so101_demo_py
  runtime_executable: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp032-w10-qualified/candidate-src/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  broker_image_id: sha256:b94b595ed560ba227e1c9dde03532a8699696ca97821f6eb3325574d77e04854
  runner_invocation_id: 929d787f061540029411d31bdd19e986
  monitor_invocation_id: 59a30d808cb1489ab921ae9414f2b20b
  ros_domain_id: [215, 216, 217, 218, 219, 220, 221, 222, 223, 224]
  gz_partition: not_applicable
commands:
  - command: Exact argv retained at /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp032-w10-qualified/exact-command.txt and systemd ExecStart readback retained at systemd-launch.txt
    exit_code: 1
observed:
  - Read-only preflight at 2026-09-15T11:59:28+08:00 confirmed ai-station, linked worktree HEAD/submodule, only the two preserved user dirty paths, root mode 0775 owned by uid 1000, absent fresh report/runtime paths, empty Domains 215-224, and no prospective unit, owned process, labeled container, ROS daemon, or GPU compute application.
  - Authorized path/owner readback resolved the exact registered root and narrowed only its mode from 0775 to 0700 at 12:00:40; the fresh detached candidate then matched source, submodule, install, executable, Broker image, model, config, and source/build provenance.
  - The genuine runner and independent monitor started at 12:04:43 with invocation IDs 929d787f061540029411d31bdd19e986 and 59a30d808cb1489ab921ae9414f2b20b.
  - The CLI created only the batch manifest and coordinator journal, then rejected the first derived worker control socket as UNIX_SOCKET_PATH_TOO_LONG at 111 bytes. No pool root, Worker, Broker container, ROS claim, point attempt, fallback, or model execution was created.
  - The wrapper's follow-up POOL_ROOT error reflects the absent pool root after the primary path rejection. Exact readback found no owned process, container, socket, claim, ROS node, GPU compute application, or active unit; the partial runtime root is retained unchanged as invalid harness evidence.
  - Path-length calculation proved a one-character legal batch ID produces the same longest control socket at 107 bytes, within the UNIX pathname content boundary, while preserving the registered evidence root and every product/runtime parameter.
inferred:
  - EXP-031 and the adaptive CLI validator establish the root mode mismatch as the sole known pre-runtime divergence; no product-code change is indicated.
conclusion: INVALID before a genuine W10 stack started because the five-character retry batch ID made its derived UNIX socket pathname 111 bytes; this is a deterministic orchestration error and supplies no W10 behavior sample.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/retry-preflight-before-mode.txt SHA256 45ec5efd064d2e143b85a56f5b74366817f995a5fbe2d2dfd5ffe49824fc4e84
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/retry-root-mode-correction.txt SHA256 6c84c2abd09cf556fa2c991348e74cbdb63db91a6448e0bf434dc7f98b57a929
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp032-w10-qualified/provenance.txt SHA256 4484511177946f160a7405634f4384f4917c336d9d3c7201bc63cba18af2ffc7
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp032-w10-qualified/prelaunch-final.txt SHA256 deccd803030ed050e927773b159d7121b3367fce257b6884e33908192f5d2b08
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp032-w10-qualified/run.log SHA256 b54a0c640146a44e3d8757aa17d4bbccd0b03684473d616736c62571cbd2e932
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp032-w10-qualified/harness-cleanup-readback.txt SHA256 51019cb480ae6c2cc865d52a02a40d838b524abde4b4f400ca098f1c28cf64e5
decision: CORRECT_TRIVIAL_BATCH_ID_AND_REPEAT
next_experiment: EXP-033-W10-R2
```

## EXP-033-W10-R2 — Genuine W10 with bounded socket pathname

```yaml
experiment_id: EXP-033-W10-R2
status: FAILED
status_history:
  - status: PLANNED
    at: 2026-09-15T12:07:00+08:00
  - status: RUNNING
    at: 2026-09-15T12:09:37+08:00
  - status: FAILED
    at: 2026-09-15T12:16:19+08:00
prior_experiment: EXP-032-W10-R1
hypothesis: A fresh one-character batch ID keeps every derived W10 UNIX socket pathname within the kernel boundary and allows the unchanged immutable candidate to start the first genuine W10 stack.
prediction: Batch x passes pre-runtime path validation, starts ten Workers plus the C2 Broker, and reaches top COMPLETED with 20/20 distinct first-attempt PASSED points, levels_used [10], no fallback/infra retry, complete evidence, and exact cleanup.
single_variable: Trivial deterministic orchestration correction only: shorten the fresh batch ID from invalid g32w0 to legal x, reducing the longest derived control socket from 111 to 107 bytes. Root mode 0700, product source, catalog, execute policy, worker count, C2, models, and timeouts remain frozen.
lifecycle: ISOLATED_STACK
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp033-w10-qualified
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/x
source_commit: b5cd54bd3f28cf26c2dec01989e277f9bcba7953
systemd_unit: so101-w10-x.service
monitor_unit: so101-w10-x-monitor.service
preconditions:
  - EXP-031 and EXP-032 remain immutable INVALID pre-runtime evidence and consume no genuine W10 execution; both have exact clean resource readbacks.
  - A newly cloned detached candidate must be clean at b5cd54bd3f28cf26c2dec01989e277f9bcba7953 with initialized submodule c16b5a5fe880b6e1857f56486dab4ae726576969 and matching source/build/install/model/image/config provenance.
  - The exact registered root remains owned by the current uid and mode 0700; fresh report exp033-w10-qualified and runtime r/x are absent before creation.
  - Domains 215-224, prospective units, owned processes, labeled container, runtime sockets, and GPU compute applications are empty immediately before launch.
success_criteria:
  - Exactly one genuine W10 pool generation runs all 20 frozen points in execute mode with initial_points_per_worker 3, worker_start_timeout_s 120, max_infra_attempts_per_point 1, and exactly two YOLO executors.
  - Top status is COMPLETED; all 20 distinct points are PASSED on first attempts; levels_used is exactly [10]; systemd exits zero; Broker health, queue, and model provenance are valid.
  - No Grounded-SAM execution, fallback, infra retry, stale pose, queue/inference timeout, lease expiry, truncated frame, OOM, or Broker-health failure occurs.
  - Every point retains controller/five-joint, TF, Planning Scene attach/detach, physical/contact, initial/final image, source-fence, and sealed-hash evidence; fresh initial and terminal contact sheets are generated and inspected.
  - Automatic internal and outer cleanup complete; Domains 215-224, owned processes, container, sockets, GPU applications, runner, and monitor are released with exact readback.
failure_criteria:
  - Any started W10 task-point, provenance, policy, first-attempt, Broker, source/build, systemd, evidence, visual, or cleanup gate fails; stop after exact cleanup with no tuning or retry.
invalid_criteria:
  - Another pre-runtime harness error prevents the genuine stack from starting; only a trivial deterministic orchestration correction may be made without changing product semantics.
provenance:
  source_commit: b5cd54bd3f28cf26c2dec01989e277f9bcba7953
  submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  install_overlay: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp033-w10-qualified/candidate-src/install/so101_demo_py
  runtime_executable: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp033-w10-qualified/candidate-src/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  broker_image_id: sha256:b94b595ed560ba227e1c9dde03532a8699696ca97821f6eb3325574d77e04854
  runner_invocation_id: 776da45673c14ad49003fa25160315e1
  monitor_invocation_id: 31e0d3316bee4bfe9bdbbf5c51f4c81c
  ros_domain_id: [215, 216, 217, 218, 219, 220, 221, 222, 223, 224]
  gz_partition: not_applicable
commands:
  - command: Exact argv retained at /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp033-w10-qualified/exact-command.txt and systemd ExecStart readback retained at systemd-launch.txt
    exit_code: 1
observed:
  - Fresh detached source/submodule/install, source/build hashes, correct EXP-028 models and C2 image, root mode 0700, 107-byte longest control socket, absent r/x, and empty Domains/resources were verified before launch.
  - The runner and independent monitor started at 12:09:37 with invocation IDs 776da45673c14ad49003fa25160315e1 and 31e0d3316bee4bfe9bdbbf5c51f4c81c.
  - Reattachment after the tmux host interruption confirmed the same invocation IDs. All ten Workers and dynamic /cup_pose consumers reached READY, and each Worker passed its initial-state ATTEMPT_STARTED gate with a fresh source frame.
  - All ten first-wave attempts failed at request_model with IpcError HANDLER_DEADLINE_EXCEEDED against the frozen 75 s Broker request deadline. Their sealed status is INVALID with reason AUTHORIZATION_OR_PORT_FAILURE, and all ten record physical_action_proven_absent true; the other ten points remained UNRUN with zero attempts.
  - Top status is INFRA_FAILED after 400.37538262386806 s, terminal_reason is ADAPTIVE_INFRASTRUCTURE_FAILURE, levels_used is [10], final_worker_count is 10, no fallback occurred, and systemd exited 1. Peak cgroup memory was 9770795008 bytes; peak GPU use was 5375 MiB and peak sampled utilization was 14 percent.
  - Ten sealed attempt manifests and initial images passed full hash/inventory/identity decoding verification. The hash-chained coordinator journal replayed 1773 events at epoch 1 with no damaged tail. The inspected contact sheet shows every cup still upright and separated from the destination and gripper; terminal images do not exist because perception never returned and motion never began.
  - Automatic cleanup completed. Domains 215-224 were RELEASED; runner and monitor units are not-found/inactive/dead; exact task processes, labeled container, live runtime sockets, ROS nodes, and owned-process records are empty.
  - The final ordinary package gate passed 3050 tests with four warnings in 61.75 s. Earlier retained verification attempts document missing-overlay, missing-Torch, overlong-socket-path, and one nondeterministic two-lock test race before the clean rerun.
inferred:
  - EXP-032 directly establishes derived socket length, not W10 product behavior; shortening only the batch identity is the minimal permitted correction.
  - Because no detector .failure.json receipt exists and GPU utilization dropped to zero while requests waited, the first divergence is bounded to the Broker inference RPC handler failing to return before its deadline. The evidence does not identify the handler's internal cause.
conclusion: The genuine W10 sample failed the frozen qualification contract at Broker inference RPC completion. W10 is not qualified; no tuning, retry, fallback, or W16 run is authorized.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp033-w10-qualified/provenance.txt SHA256 6bd56b6a4bbfa745e0392949df0473e664ed02c34ca3b252ac0b3d8bd8a5e6f5
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp033-w10-qualified/prelaunch-final.txt SHA256 076beae499eebfdbed0e062a4c9cf111dfbd9b1540b626a7bddec0a9a2c7af05
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp033-w10-qualified/aggregate_results.json SHA256 d8fe9829d69c47483247067b4fb5e6feecb089824f07cb9a9616c5a67112d17e
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp033-w10-qualified/cleanup-receipt.json SHA256 dfd405fd14600dd430936edc57f764bbd1d22a70c118386909629235302e920e
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp033-w10-qualified/cleanup-readback.txt SHA256 0874f6f7fbf19843160063b0ba89153e2266832ff6d1d9d2c36e5b1a1378d640
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp033-w10-qualified/initial-failure-contact-sheet.png SHA256 7955937bb767c228cedf2556070c84db4e6d85563fe037f6c407c499d6a1a566
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp033-w10-qualified/validation-summary.json and final-core-sha256.txt contain the complete artifact, journal, resource, visual, and core-file readback.
decision: STOP_NO_RETRY
next_experiment: NONE
```

## CP-041 — W10 terminal failure, verified cleanup, and task closeout

```yaml
checkpoint_id: CP-041
status: COMPLETE
last_valid_experiment: EXP-030-W16-GREEN
last_executed_experiment: EXP-033-W10-R2
confirmed_conclusions:
  - The W16 optional-ceiling implementation remains verified at b5cd54bd3f28cf26c2dec01989e277f9bcba7953, preserving default W8 and fallback 6, 4, 2, 1.
  - The frozen EXP-028 W8 result remains the highest runtime-qualified level; EXP-033 does not qualify W10.
  - EXP-033 formed the genuine fixed-W10 stack and reached ten initial attempts, then failed uniformly at Broker request_model completion before any physical action.
  - Exact automatic and outer cleanup passed, and the complete ordinary package gate passed 3050 tests.
owned_runtime: NONE
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01
archived_runs: []
deletion_candidates:
  - Completed verification scratch trees under /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch, including exp033-final-verify, exp033-final-verify-overlay, exp033-final-verify-complete-env, q, and s.
  - Superseded EXP-031 and EXP-032 report/runtime artifacts, the completed EXP-033 candidate build tree, and completed runtime r/x; all remain retained pending explicit deletion authorization.
external_actions:
  - No push, merge, deletion, tuning, retry, fallback, new stack, or W16 runtime launch was performed.
open_risk:
  - The Broker handler's internal W10 stall mechanism remains unknown because it produced no detector failure receipt; investigation requires a separately authorized experiment.
next_command: NONE
```

## Formal scaling restoration from CP-044

```yaml
restored_at: 2026-09-15T18:23:00+08:00
restored_checkpoint: CP-044
last_valid_experiment: EXP-040-FIXED-W10-20-POINT
confirmed_conclusions:
  - The stateless Broker candidate b0f9e7168198285fba4133026d9d3b132075f88b and image sha256:4fb57abe1109e7cc1c7fbf1780a7dd10b4167f12abfa59ba34b1903a60c4c972 are qualified by EXP-039 and EXP-040.
  - EXP-040 completed the exact twenty-point catalog at fixed W10/C2 on first attempts with no retry, model fallback, Worker reduction, or cleanup residue.
disproven_routes:
  - Worker levels in this task are runtime SO-101 pool sizes, not pytest process counts or sharding.
  - Two-character batch IDs exceed the frozen Unix socket limit at 108 bytes; unique one-character IDs remain exactly within the 107-byte limit.
working_tree_status:
  - HEAD 74fef842e3f80038110ce9b835b95d27ecd2dfb5 on codex/parallel-adaptive-worker-pool.
  - Preserved user src/so101_demo_py/test/test_parallel_batch_resources.py is the only pre-task dirty path; its diff SHA256 is ae383016c78eca3c02e05f600d58fb4a65211f4783acf9612ea38e374baf380c.
owned_processes: NONE
preserved_processes:
  - PID 1983511 is an unrelated ROS Domain 0 daemon owned by /data/work/ws_moveit/.worktrees/pytest-gate-parallelism and is not touched.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01
formal_series_root: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f
frozen_harness_sha256: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f/frozen-harness.sha256
next_experiment: EXP-041-FORMAL-W1
```

## EXP-041-FORMAL-W1 — Fixed Worker baseline

```yaml
experiment_id: EXP-041-FORMAL-W1
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T18:23:00+08:00
  - status: RUNNING
    at: 2026-09-15T18:25:21+08:00
  - status: INVALID
    at: 2026-09-15T18:25:23+08:00
prior_experiment: EXP-040-FIXED-W10-20-POINT
hypothesis: One Worker provides the serial timing denominator while satisfying the exact EXP-040 behavior and evidence contract under the frozen stateless Broker C2 configuration.
prediction: Exactly twenty catalog points pass once on first attempts at levels_used [1], with no retry, Worker/model fallback, policy drift, or cleanup residue; execution time becomes T1 for speedup and efficiency.
single_variable: Fixed Worker count W1; every other series variable is frozen by formal-worker-scaling-8d75fe6f/frozen-plan.txt and frozen-harness.sha256.
lifecycle: ISOLATED_STACK
preconditions:
  - CP-044 is restored and the frozen source, runtime candidate, submodule, overlay, image, model, point, timeout, retry, C2, and no-fallback contracts match.
  - The formal coordination status is RUNNING and resource-heavy pytest does not overlap.
  - Runtime /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/a and report w01 are absent.
  - Domains 215-224, prospective units, task processes, containers, sockets, and GPU clients are empty; the unrelated pytest-worktree Domain 0 daemon is preserved.
success_criteria:
  - Exactly twenty distinct points are PASSED on first attempts, levels_used is [1], initial/final Worker count is 1, and no retry or fallback occurs.
  - Sealed correlation, initial/reset, model, TF, planning/controller, physical/contact, Planning Scene, final-placement, hash, and initial/terminal RGB gates all pass.
  - Clean launch, pool readiness, twenty-point interval, cleanup, resource, and available Broker metrics are machine-readable, and exact post-run cleanup passes.
failure_criteria:
  - Any valid behavior, point, first-attempt, model, motion, physical, evidence, fixed-level, or cleanup gate fails; preserve it and do not silently rerun.
invalid_criteria:
  - Admission, provenance, source/config/image/model hash, socket, unrelated workload, launch harness, or evidence contamination prevents a valid W1 sample.
provenance:
  source_commit: 74fef842e3f80038110ce9b835b95d27ecd2dfb5
  runtime_candidate_commit: b0f9e7168198285fba4133026d9d3b132075f88b
  implementation_commit: 59c831f0d771f45f6b930dd59fc85d673a7c96e5
  submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  install_overlay: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp039-real-yolo-w10-c2/candidate-src/install
  runtime_executable: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp039-real-yolo-w10-c2/candidate-src/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  ros_domain_id: [215]
  gz_partition: not_applicable
commands:
  - command: /usr/bin/zsh /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f/run-level.zsh 1 a EXP-041-FORMAL-W1
    exit_code: 1
observed:
  - The complete preflight passed, then the production CLI exited before creating runtime r/a with `FROZEN_ADAPTIVE_VALUE: worker_count`; the generated formal configuration was incorrectly used as the input to the closed version-one defaults loader.
  - The wrapper's expected post-error cleanup reported `RUNTIME_ROOT` because r/a was never created. Independent final readback passed with no task-domain daemon, process, container, socket, GPU client, unit, or Domain claim left behind.
  - No Worker, Broker, simulator, point attempt, aggregate, or performance interval started, so this attempt contributes no behavioral or timing sample.
inferred:
  - EXP-040 passed W10 because it supplied the committed W8 defaults file to the loader and applied W10 through the production CLI override. The failed formal harness instead placed W10 directly in the defaults file, crossing the strict loader boundary before the override.
conclusion: INVALID pre-runtime harness/configuration attempt; it says nothing about W1 behavior or performance.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f/w01
  - run.log SHA256 7ec2ce2eebb17c60f533177290d25ec85ac65e6ca4f4eeccc9a75347ccc3b0b4
  - runner-end.json SHA256 047ff7f5cce590bfa9849aade2a23af1c43845091cbdc8e46fe0a2d4b58dbb31
  - final-cleanup-readback.txt SHA256 322b8b90cc1a75045121d18650da1bb4062e10ca072a2454bd59c34dc1b15124
decision: RESTART_SERIES_FROM_W1_WITH_FROZEN_V4_HARNESS
next_experiment: EXP-042-FORMAL-W1-R2
```

## EXP-042-FORMAL-W1-R2 — Fixed Worker baseline, corrected frozen harness

```yaml
experiment_id: EXP-042-FORMAL-W1-R2
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T18:31:39+08:00
  - status: RUNNING
    at: 2026-09-15T18:32:41+08:00
  - status: PASSED
    at: 2026-09-15T19:00:48+08:00
prior_experiment: EXP-041-FORMAL-W1
hypothesis: With the closed defaults loader fed its exact committed W8 configuration and the previously audited measurement-only boundary freezing parsed fallbacks to empty, W1 provides a valid serial denominator under the EXP-040 C2 behavior contract.
prediction: Exactly twenty catalog points pass once on first attempts at levels_used [1], with no retry, Worker/model fallback, policy drift, or cleanup residue; execution time becomes T1.
single_variable: Fixed Worker count W1; every other variable is frozen by formal-worker-scaling-8d75fe6f-v4/frozen-plan.txt and frozen-harness.sha256.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-041 is retained INVALID and did not create r/a or start any runtime component.
  - The v4 harness restores the byte-identical committed adaptive defaults and freezes the parsed fallback tuple to empty through one immutable measurement-only sitecustomize overlay shared by all six levels.
  - Candidate, source, submodule, install, image, models, point catalog, timeout, reset, retry, C2, evidence, and measurement contracts remain those restored from CP-044.
  - Runtime /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/g and report formal-worker-scaling-8d75fe6f-v4/w01 are absent.
success_criteria:
  - Exactly twenty distinct points are PASSED on first attempts, levels_used is [1], initial/final Worker count is 1, manifest fallback_worker_counts is empty, and no retry or fallback occurs.
  - All sealed correlation, initial/reset, model, TF, planning/controller, physical/contact, Planning Scene, final-placement, hash, and fresh initial/terminal RGB gates pass.
  - Machine-readable timing/resource/Broker evidence and exact post-run cleanup pass.
failure_criteria:
  - Any valid behavior, evidence, fixed-level, resource, or cleanup gate fails; preserve it without a silent rerun.
invalid_criteria:
  - Admission, provenance, source/config/overlay/image/model hash, unrelated workload, launch harness, or evidence contamination prevents a valid W1 sample.
provenance:
  source_commit: 74fef842e3f80038110ce9b835b95d27ecd2dfb5
  runtime_candidate_commit: b0f9e7168198285fba4133026d9d3b132075f88b
  implementation_commit: 59c831f0d771f45f6b930dd59fc85d673a7c96e5
  submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  broker_image_id: sha256:4fb57abe1109e7cc1c7fbf1780a7dd10b4167f12abfa59ba34b1903a60c4c972
  frozen_harness_manifest_sha256: 36dc215804dd756d89522c393e3a7e17befd0c621fe8811db3eaa7eb8e876562
commands:
  - command: /usr/bin/zsh /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/run-level.zsh 1 g EXP-042-FORMAL-W1-R2
    exit_code: 0
observed:
  - The one formal W1 launch passed preflight, formed one Worker, and completed all 20 catalog points PASSED on first attempts with levels_used [1], manifest fallback_worker_counts [], 20 exact YOLO request correlations, zero retry, zero Grounded-SAM fallback, and zero correlation error.
  - Startup-to-ready was 19.737433060072362 s; the twenty-point interval was 1592.5133624076843 s; clean launch through production cleanup was 1620.8567272040527 s; throughput was 0.753525859391062 points/minute.
  - Descriptive n=20 READY-to-POSE timing was p50 0.6758952140808105 s and p95 1.6583109617233278 s. Total READY-to-DONE was p50 66.18522572517395 s and p95 83.9186247587204 s.
  - Sampled peak cgroup memory was 1358749696 bytes, peak GPU allocation 3435 MiB, peak GPU utilization 9 percent, minimum host available memory 25133100 KiB, CPU time 1594.934625 s, and swap-used delta 4400 KiB.
  - Broker optional shutdown summary was unavailable; the validator therefore records 20 logical inferences and zero correlation errors derived from 20 distinct sealed YOLO requests without inventing queue/service distributions.
  - Fresh initial/terminal contact sheets show all 20 distinct upright source cups and all 20 upright terminal cups in the target ring with grippers raised and clear, corroborating maximum final XY error 0.002162304721854786 m and maximum upright tilt 0.006831916386352743 rad.
  - Exact final cleanup passed with no task process, task-domain daemon, container, socket, GPU client, held claim, or active unit; the unrelated Domain 0 daemon remained untouched.
conclusion: PASSED; W1 is the valid serial denominator T1=1592.5133624076843 s for formal speedup and efficiency.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/w01
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/g
  - level-summary.json SHA256 5ee4847dd5023005daf4b8ae6ea2f2b4468b4db8ab243293a4c68026914a31c5
  - evidence-validation.json SHA256 1e49f8d6a98437bb60f93dab9747c7e1cd11e326480d8fc1f4a30e28ec4d2041
  - initial-contact-sheet.png SHA256 597c27e844972056856cd03a1cdd03e814d969630d3dbbf01485cfb4c84ab4ad
  - terminal-contact-sheet.png SHA256 e8dacba58b0cffa9cd9eac92e4164259804fb067166501696654d0e50155bb52
  - visual-observation.txt SHA256 4bcf71f4127837605efe646da9f00aaf6baadc655f8924edfc491104159b1814
  - final-cleanup-readback.txt SHA256 f13665e5d676b10d33e03eef15acf91428920724bed198dd45e2ead95347d913
decision: PROCEED_TO_W2
next_experiment: EXP-043-FORMAL-W2
```

## EXP-043-FORMAL-W2 — Fixed Worker scaling level

```yaml
experiment_id: EXP-043-FORMAL-W2
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T19:01:30+08:00
  - status: RUNNING
    at: 2026-09-15T19:02:33+08:00
  - status: PASSED
    at: 2026-09-15T19:17:09+08:00
prior_experiment: EXP-042-FORMAL-W1-R2
hypothesis: Two Workers reduce the 20-point interval relative to W1 while preserving the exact frozen behavior and evidence contract.
prediction: Exactly 20 points pass on first attempts at levels_used [2] with no retry, fallback, drift, or cleanup residue; T1/T2 exceeds one.
single_variable: Fixed Worker count changes from W1 to W2; the v4 harness and every non-Worker input remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-042 passed and its exact cleanup readback is clean.
  - The v4 frozen-harness manifest validates; candidate, dirty file, image/model/config/catalog, Domains, socket, host/GPU admission, timeout/retry, C2, and empty-fallback checks pass.
  - Runtime r/h and report w02 are absent; no measured runs overlap.
success_criteria:
  - Twenty distinct first-attempt PASSED points, levels_used [2], empty fallbacks, YOLO-only exact correlation, complete sealed/visual evidence, and clean exit/readback.
failure_criteria:
  - Any valid behavior, evidence, fixed-level, or cleanup gate fails; preserve without silent rerun.
invalid_criteria:
  - Any admission, provenance, source/config/overlay/image/model, workload, harness, or evidence contamination.
provenance:
  frozen_harness_manifest_sha256: 36dc215804dd756d89522c393e3a7e17befd0c621fe8811db3eaa7eb8e876562
commands:
  - command: /usr/bin/zsh /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/run-level.zsh 2 h EXP-043-FORMAL-W2
    exit_code: 0
observed:
  - The single W2 launch passed all gates: 20/20 distinct first-attempt PASSED points, levels_used [2], empty fallbacks, 20 YOLO correlations, zero retry/model fallback/correlation error, and exact cleanup.
  - Startup was 19.66266585793346 s, execution 810.0461459159851 s, end-to-end 835.7975381789729 s, and throughput 1.481397085894486 points/minute.
  - Against W1 execution, speedup is 1.9659538785989776, parallel efficiency 0.9829769392994888, and interval reduction 49.134106812686645 percent.
  - Sampled peak cgroup memory was 2294722560 bytes, CPU time 1493.11772 s, peak GPU allocation 3703 MiB, peak GPU utilization 5 percent, minimum host available memory 23981124 KiB, and swap-used delta 9972 KiB.
  - Visual review found all source cups upright/distinct and all terminal cups upright in the target ring with grippers raised and clear; numeric maximum final XY error was 0.0021527989156644146 m.
conclusion: PASSED; W2 nearly doubles W1 throughput with 98.30 percent parallel efficiency.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/w02
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/h
  - level-summary.json SHA256 3f2a2523c80fa74323459a6ce3940cb54e202d34a4475fc309b3ab2c86c9aee2
  - evidence-validation.json SHA256 cb46951d23655ea49746c9b0463bda45a86a68fef4479eebc114835b33c71210
  - initial-contact-sheet.png SHA256 1f5f6b2d1d0c6eef7e6493914fc6371294b4e42fa16a6735e97cc6cfbc626e79
  - terminal-contact-sheet.png SHA256 c5c5c24aefe235680f680765af355378d456d06d911b9503949753f009ea6a7d
  - visual-observation.txt SHA256 df505740bc476090f4de0cf5441570459755cecd9b763ee36f17e31ca4153396
  - final-cleanup-readback.txt SHA256 fadfe887790e2091bde1b5425f667bfd8ab069921cfd056b13dff93013de12ca
decision: PROCEED_TO_W4
next_experiment: EXP-044-FORMAL-W4
```

## EXP-044-FORMAL-W4 — Fixed Worker scaling level

```yaml
experiment_id: EXP-044-FORMAL-W4
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T19:17:58+08:00
  - status: RUNNING
    at: 2026-09-15T19:18:34+08:00
  - status: PASSED
    at: 2026-09-15T19:27:05+08:00
prior_experiment: EXP-043-FORMAL-W2
hypothesis: Four Workers further reduce the interval while preserving the frozen behavior/evidence contract and may approach the practical throughput knee.
prediction: Twenty points pass on first attempts at levels_used [4], with no fallback/retry/drift/residue and higher throughput than W2.
single_variable: Fixed Worker count changes from W2 to W4; all v4 non-Worker inputs remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - W2 passed and cleaned exactly; v4 hashes and live source/dirty/image/model/config/catalog/domain/socket/host/GPU admission all pass.
  - Runtime r/i and report w04 are absent; no measured runs overlap.
success_criteria:
  - Exact 20-point first-attempt fixed-W4 YOLO-only completion, complete sealed/visual evidence, clean exit and cleanup.
failure_criteria:
  - Any valid behavior, evidence, fixed-level, or cleanup failure; preserve without silent rerun.
invalid_criteria:
  - Any admission, provenance, frozen-input, workload, harness, or evidence contamination.
provenance:
  frozen_harness_manifest_sha256: 36dc215804dd756d89522c393e3a7e17befd0c621fe8811db3eaa7eb8e876562
commands:
  - command: /usr/bin/zsh /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/run-level.zsh 4 i EXP-044-FORMAL-W4
    exit_code: 0
observed:
  - The single W4 run passed 20/20 distinct first-attempt points at levels_used [4], empty fallbacks, YOLO-only exact correlation, zero retry/fallback/error, complete sealed and visual evidence, and exact cleanup.
  - Startup was 31.48484530299902 s, execution 412.42340636253357 s, end-to-end 450.33535863785073 s, and throughput 2.9096311739037453 points/minute.
  - W1 speedup is 3.861355436766393, W4 efficiency 0.9653388591915982, and improvement from W2 is 49.08643063832211 percent.
  - Peak cgroup memory was 4297502720 bytes, CPU time 1745.681273 s, peak GPU allocation 4127 MiB, peak GPU utilization 12 percent, minimum host available memory 22132316 KiB, and swap-used delta 27400 KiB.
  - Fresh visual review found all initial cups upright/distinct and all terminal cups upright in target with grippers clear; maximum final XY error was 0.002155183015562726 m.
conclusion: PASSED; W4 remains close to linear scaling and is the current fastest valid level.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/w04
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/i
  - level-summary.json SHA256 7c241501911067f735471a2cd907812541499a286da3d65fa164e9e515dbde52
  - evidence-validation.json SHA256 95794f89cd17d3a09ee08afc49cf0b7e1e5bfe809be96badd996f4e976e97e99
  - initial-contact-sheet.png SHA256 672db4c01f52d48476a0e4241204c51688b6e1875e673417d232e71ae1d212bf
  - terminal-contact-sheet.png SHA256 ca0ecf79f7bed00c9b83bd9c01e9d3aa38fdbbdb9b8f9276574b92e80985ec64
  - visual-observation.txt SHA256 fb094d1f66881cb532b4e03aa5eea21324f51e7230174d275c14a7a2c0171806
  - final-cleanup-readback.txt SHA256 0e094ed4df15d29dbf847cc2c287fe68cb2e73bc69b18b17091f27d6b9d3cf08
decision: PROCEED_TO_W6
next_experiment: EXP-045-FORMAL-W6
```

## EXP-045-FORMAL-W6 — Fixed Worker scaling level

```yaml
experiment_id: EXP-045-FORMAL-W6
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T19:27:50+08:00
  - status: RUNNING
    at: 2026-09-15T19:28:25+08:00
  - status: PASSED
    at: 2026-09-15T19:36:01+08:00
prior_experiment: EXP-044-FORMAL-W4
hypothesis: W6 improves on W4 while beginning to expose startup, CPU, memory, and C2 inference bottlenecks.
prediction: Exact first-attempt fixed-W6 completion with higher throughput than W4 and lower marginal efficiency than W4.
single_variable: Fixed Worker count changes from W4 to W6; all v4 non-Worker inputs remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - W4 passed and cleaned exactly; frozen hashes and live source/dirty/image/model/config/catalog/domain/socket/host/GPU admission pass.
  - Runtime r/j and report w06 are absent; no measured runs overlap.
success_criteria:
  - Exact 20-point first-attempt fixed-W6 YOLO-only completion, complete sealed/visual evidence, clean exit/readback.
failure_criteria:
  - Any valid behavior, evidence, fixed-level, or cleanup failure; preserve without silent rerun.
invalid_criteria:
  - Any admission, provenance, frozen-input, workload, harness, or evidence contamination.
provenance:
  frozen_harness_manifest_sha256: 36dc215804dd756d89522c393e3a7e17befd0c621fe8811db3eaa7eb8e876562
commands:
  - command: /usr/bin/zsh /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/run-level.zsh 6 j EXP-045-FORMAL-W6
    exit_code: 0
observed:
  - The single W6 run passed 20/20 distinct first-attempt points at levels_used [6], empty fallbacks, YOLO-only exact correlation, zero retry/fallback/error, complete sealed and visual evidence, and exact cleanup.
  - Startup was 44.906895893858746 s, execution 338.78217601776123 s, end-to-end 392.5487897649873 s, and throughput 3.5420989796614566 points/minute.
  - W1 speedup is 4.700699963401245, W6 efficiency 0.7834499939002075, and execution improvement from W4 is 17.85573495798134 percent.
  - Peak cgroup memory was 6306103296 bytes, CPU time 2241.036074 s, peak GPU allocation 4555 MiB, peak GPU utilization 35 percent, minimum host available memory 20005612 KiB, and swap-used delta 17524 KiB.
  - Visual review passed all initial/terminal frames; maximum final XY error was 0.0021676550480557496 m.
conclusion: PASSED; W6 is faster than W4, but scaling efficiency falls to 78.34 percent and startup/resource cost grows.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/w06
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/j
  - level-summary.json SHA256 4ebd9595d39597379e48b85c7dab290a8965db510d630cfffb8a76740042ced8
  - evidence-validation.json SHA256 82d201b708feab68ca86dd55a485562f6dac04fca622f023ccab3dbb8599ae2d
  - initial-contact-sheet.png SHA256 c6f87405c47f95ecb794964922062fd95cc89dd62a69d0f5e5fdee937a7b7c14
  - terminal-contact-sheet.png SHA256 3706723c1d105558f5f6bb5917935b0ed3ff74d47fae1a738ffe35cd0ac8fbe4
  - visual-observation.txt SHA256 f0cf7d00b381b1793c7a4d2597501c4021f49dac00a011e034c5be04f2469d00
  - final-cleanup-readback.txt SHA256 2059bb0ce66ca5cb0226e3d54e994fd11937b053281acfec77a9626fb362f1c7
decision: PROCEED_TO_W8
next_experiment: EXP-046-FORMAL-W8
```

## EXP-046-FORMAL-W8 — Fixed Worker scaling level

```yaml
experiment_id: EXP-046-FORMAL-W8
status: PASSED
status_history:
  - status: PLANNED
    at: 2026-09-15T19:36:35+08:00
  - status: RUNNING
    at: 2026-09-15T19:37:13+08:00
  - status: PASSED
    at: 2026-09-15T19:43:46+08:00
prior_experiment: EXP-045-FORMAL-W6
hypothesis: W8 may improve throughput beyond W6, but C2 perception, startup, memory, and the 20-point tail may dominate marginal gains.
prediction: Exact first-attempt fixed-W8 completion; throughput gain over W6 is smaller than earlier doublings.
single_variable: Fixed Worker count changes from W6 to W8; all v4 non-Worker inputs remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - W6 passed and cleaned exactly; frozen hashes and live admission pass.
  - Runtime r/k and report w08 are absent; no measured runs overlap.
success_criteria:
  - Exact 20-point first-attempt fixed-W8 YOLO-only completion, complete sealed/visual evidence, clean exit/readback.
failure_criteria:
  - Any valid behavior, evidence, fixed-level, or cleanup failure; preserve without silent rerun.
invalid_criteria:
  - Any admission, provenance, frozen-input, workload, harness, or evidence contamination.
provenance:
  frozen_harness_manifest_sha256: 36dc215804dd756d89522c393e3a7e17befd0c621fe8811db3eaa7eb8e876562
commands:
  - command: /usr/bin/zsh /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/run-level.zsh 8 k EXP-046-FORMAL-W8
    exit_code: 0
observed:
  - The single W8 run passed 20/20 distinct first-attempt points at levels_used [8], empty fallbacks, YOLO-only exact correlation, zero retry/fallback/error, complete sealed and visual evidence, and exact cleanup.
  - Startup was 62.286955520976335 s, execution 263.6432132720947 s, end-to-end 333.63622800190933 s, and throughput 4.551605880943091 points/minute.
  - W1 speedup is 6.040410988179394, W8 efficiency 0.7550513735224242, and execution improvement from W6 is 22.17913693952046 percent.
  - Peak cgroup memory was 8266747904 bytes, CPU time 2889.238315 s, peak GPU allocation 4983 MiB, peak GPU utilization 23 percent, minimum host available memory 18356520 KiB, and swap-used delta 142004 KiB.
  - Visual review passed all frames; maximum final XY error was 0.0021525180220600608 m.
conclusion: PASSED; W8 beats W6, while startup and memory costs continue rising and efficiency is 75.51 percent.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/w08
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/k
  - level-summary.json SHA256 5a89379c5033189c77f67c65fa7938d681f9af2de958e6e25cec1bec9686b0f6
  - evidence-validation.json SHA256 862e953d15a2a9c5ea78483cc6fb4762bd9083ce8d8509c04dbc20ce813d8b30
  - initial-contact-sheet.png SHA256 e8b79eb785ae6116c487fab7d3f144ff7945c65e33bc5a751f80fdeec3e6de1c
  - terminal-contact-sheet.png SHA256 b84081dc212feb18c58d76959cb4b58a30156390ecea5cdeac54078ae2a02ebc
  - visual-observation.txt SHA256 eba152e66ab7046c69a3d1ab99df6767847711724f431649f19b382f26551c8d
  - final-cleanup-readback.txt SHA256 ba21b0700ef4344e1c54926b8a202491a14db19f68db2d90b9d09329b1f0b918
decision: PROCEED_TO_W10
next_experiment: EXP-047-FORMAL-W10
```

## EXP-047-FORMAL-W10 — Fixed Worker scaling level

```yaml
experiment_id: EXP-047-FORMAL-W10
status: FAILED
status_history:
  - status: PLANNED
    at: 2026-09-15T19:44:30+08:00
  - status: RUNNING
    at: 2026-09-15T19:45:05+08:00
  - status: FAILED
    at: 2026-09-15T19:50:35+08:00
prior_experiment: EXP-046-FORMAL-W8
hypothesis: W10 may be fastest because 20 points divide evenly into two per Worker, but C2 inference, startup, memory, and CPU costs may erase the gain over W8.
prediction: Exact first-attempt fixed-W10 completion; measured throughput determines whether additional Workers after W8 help or hurt.
single_variable: Fixed Worker count changes from W8 to W10; all v4 non-Worker inputs remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - W8 passed and cleaned exactly; frozen hashes and live admission pass.
  - Runtime r/l and report w10 are absent; no measured runs overlap.
success_criteria:
  - Exact 20-point first-attempt fixed-W10 YOLO-only completion, complete sealed/visual evidence, clean exit/readback.
failure_criteria:
  - Any valid behavior, evidence, fixed-level, or cleanup failure; preserve without silent rerun.
invalid_criteria:
  - Any admission, provenance, frozen-input, workload, harness, or evidence contamination.
provenance:
  frozen_harness_manifest_sha256: 36dc215804dd756d89522c393e3a7e17befd0c621fe8811db3eaa7eb8e876562
commands:
  - command: /usr/bin/zsh /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/run-level.zsh 10 l EXP-047-FORMAL-W10
    exit_code: 1
observed:
  - Admission and frozen-contract checks passed, all ten Workers formed READY at fixed W10/C2 with empty Worker fallback, and the one authorized formal launch began without overlap or provenance drift.
  - The first wave sealed 10/10 points PASSED on first attempts with 10 exact YOLO correlations, zero retry, zero Grounded-SAM fallback, and zero correlation error. The other ten points did not complete: aggregate status counts are 10 PASSED, 3 UNRUN, and 7 INDETERMINATE.
  - Coordinator journal event 1404 is the first authoritative failure boundary: it set `broker_healthy: false`, changed the terminal reason to `ADAPTIVE_INFRASTRUCTURE_FAILURE`, revoked authorization, and stopped all ten Workers. The Broker Docker scope/container had deactivated immediately beforehand. Worker SIGINT, pybind conversion, terminal-ack, and rclpy cleanup errors followed this stop boundary and are downstream effects.
  - The system journal contains no OOM event for the Broker container, and no container-internal exit receipt or optional Broker shutdown summary was retained. The directly observed cause is therefore unexpected Broker-container disappearance; its deeper internal cause remains UNKNOWN rather than inferred.
  - Startup-to-ready was 79.10071084089577 s, end-to-end through cleanup was 203.09369269385934 s, sampled peak cgroup memory was 9843302400 bytes, CPU time was 2778.36991 s, peak GPU allocation was 5412 MiB, minimum host available memory was 16833864 KiB, and swap-used delta was 199304 KiB.
  - The level validator's 93.36296343803406 s interval and 12.853062454433038 points/minute cover only the 10 sealed successes, not twenty points. They are retained as partial failure diagnostics and excluded from the formal performance curve, speedup, and efficiency calculations.
  - Visual review passes the initial and terminal frames for the 10 sealed first-wave successes only. The interrupted second wave lacks complete terminal evidence, and sample_16_far_right is INDETERMINATE because physical action is not proven absent; W10 therefore receives no full visual/behavior pass.
  - Exact cleanup and final readback passed with no task Worker, Broker, simulator, ROS daemon, container, socket, GPU client, systemd unit, or Domain claim left behind.
conclusion: FAILED; this is a valid W10 behavioral/infrastructure failure, not an INVALID admission, and it is preserved without rerun. No valid W10 performance sample exists.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/w10
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/l
  - level-summary.json SHA256 7590cc32c8d4587728dbdeb4c73258d2f80d454374b8f7e2f191d5d9c00656c8
  - evidence-validation.json SHA256 1026c05bf6b9ddba960d3e3bfb86c6d45ffe1ea12a53c9e36319b2f3b33dca38
  - coordinator journal SHA256 6fbabd8cb0e0f85ee9b28d4d7b0a756a876c9387c7f90cec35452ef484648c67
  - initial-contact-sheet.png SHA256 2564784702991ba6b8b7202764323b9dedcfbb484216c16f44fa501c0b89f148
  - terminal-contact-sheet.png SHA256 7a6a5f9a93604428fd50c6cf4844c2136e1b14b9cb8b3ede5d18b0fb10d83b5a
  - visual-observation.txt SHA256 bf44e942e9e8e8589a3eeaf2c7dd7d0f640aed2d60e0fdc2c8cc890409435085
  - final-cleanup-readback.txt SHA256 4aaec6acb884e39b2e0f13d86ebbe5f1aa1c4a35a15ba882fcb8f19093923457
decision: CLOSE_SERIES_WITH_W8_AS_FASTEST_VALID_AND_RECOMMENDED_DEFAULT
next_experiment: NONE
```

## CP-045 — Formal fixed-Worker scaling comparison complete

```yaml
checkpoint_id: CP-045
completed_at: 2026-09-15T19:57:28+08:00
dispatch_id: 8D75FE6F-14B7-474F-AC97-3EB5302D1C3A
prior_checkpoint: CP-044
experiments:
  invalid_pre_runtime: [EXP-041-FORMAL-W1]
  valid_performance_samples: [EXP-042-FORMAL-W1-R2, EXP-043-FORMAL-W2, EXP-044-FORMAL-W4, EXP-045-FORMAL-W6, EXP-046-FORMAL-W8]
  valid_behavioral_failures: [EXP-047-FORMAL-W10]
comparison:
  w1: {execution_s: 1592.5133624076843, throughput_points_per_min: 0.753525859391062, speedup: 1.0, efficiency: 1.0}
  w2: {execution_s: 810.0461459159851, throughput_points_per_min: 1.481397085894486, speedup: 1.9659538785989776, efficiency: 0.9829769392994888}
  w4: {execution_s: 412.42340636253357, throughput_points_per_min: 2.9096311739037453, speedup: 3.861355436766393, efficiency: 0.9653388591915982}
  w6: {execution_s: 338.78217601776123, throughput_points_per_min: 3.5420989796614566, speedup: 4.700699963401245, efficiency: 0.7834499939002075}
  w8: {execution_s: 263.6432132720947, throughput_points_per_min: 4.551605880943091, speedup: 6.040410988179394, efficiency: 0.7550513735224242}
  w10: {status: FAILED, successful_points: 10, terminal_reason: ADAPTIVE_INFRASTRUCTURE_FAILURE, performance_sample: null}
confirmed_conclusions:
  - W8 is the fastest valid level and the practical recommended default for this frozen twenty-point C2 workload.
  - W4 is the efficiency knee at 96.53 percent. W6 and W8 still improve throughput, but startup, process/CPU load, and roughly two additional GiB of peak cgroup memory per step lower marginal efficiency.
  - W10 hurts usable throughput and reliability: its Broker container disappeared after ten successful first-wave points, so no twenty-point W10 throughput, speedup, or efficiency is valid.
  - All valid samples passed 20/20 on first attempts at their fixed level with YOLO, no retry, no Worker/model fallback, zero sealed-request correlation error, complete initial/terminal evidence, and exact cleanup.
  - The optional Broker shutdown summary was absent for every level. Maximum active inference and queue/service distributions remain unavailable; derived sealed-request counts are reported without invented values.
  - p50/p95 values are descriptive over one n=20 batch per valid level, not repeated-batch statistical confidence. W10's n=10 partial values are failure diagnostics only.
  - After coordination became COMPLETE, `codex/pytest-gate-parallelism` was inspected at e81286bf5aa465168d7d611de349635cbcae8a9e. Its experiment ledger remained modified and no merge-ready receipt/status existed, so the branch is not eligible for merge and integration remains pending.
artifacts:
  comparison_json: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/formal-worker-scaling-comparison.json
  comparison_json_sha256: 9b523321fb477cdad7e1e94aa92ce203d96ccc89c4954609d0d1f263493b4848
  comparison_csv: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/formal-worker-scaling-comparison.csv
  comparison_csv_sha256: 99c9f4224ea65fc48893046613204e2d199590c49595734ced315a7175e12956
  report_markdown: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/formal-worker-scaling-report.md
  report_markdown_sha256: 9c0d8b5495b6a7ae8bdc20a9e1d199e71d455e1c14b364c77fdf727fc0e08899
  report_manifest_sha256: 3de38e42bacc788c9ad2fd36b4bdd90f1ae6cf89cad2664eebb008cfbcf41b14
retention:
  retained_runs:
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/g
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/h
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/i
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/j
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/k
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/l
  archived_runs: []
  deletion_candidates:
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f
    - the six retained per-level MUJOCO_LOG.TXT files under formal-worker-scaling-8d75fe6f-v4
  deleted: []
cleanup: PASS
final_cleanup_readback: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4/final-cleanup-readback.txt
final_cleanup_readback_sha256: cf6c4841868187ce0b881f83e634d18313c3b25c130ef4bc36f6b63b158fa8f5
next_experiment: NONE
```

## EXP-048-FORMAL-W10-R2 — Fixed W10 reproducibility rerun

```yaml
experiment_id: EXP-048-FORMAL-W10-R2
status: FAILED
status_history:
  - status: PLANNED
    at: 2026-09-15T20:14:21+08:00
  - status: RUNNING
    at: 2026-09-15T20:22:21+08:00
  - status: FAILED
    at: 2026-09-15T20:22:58+08:00
prior_experiment: EXP-047-FORMAL-W10
hypothesis: EXP-047's unexpected Broker-container disappearance was transient; one fresh W10 attempt under the byte-equivalent v4 runtime payload can complete all twenty points while preserving the fixed W10/C2 evidence contract.
prediction: If the disappearance was transient, this one attempt completes 20/20 points on first attempts at `levels_used=[10]`; if the same failure repeats, the retained Docker/system/kernel/coordinator evidence will establish its first bad boundary without a third run.
single_variable: NONE in production/runtime policy; this is one reproducibility repeat. A copied report-path wrapper adds passive Docker and journal capture without changing the runtime command/config payload or measurement boundaries.
lifecycle: ISOLATED_STACK
preconditions:
  - CP-045 is restored; original EXP-047 and all v4 artifacts remain immutable and independently retained.
  - Coordination status is RUNNING for dispatch DF261A05-3907-49C9-95BE-B303D7CF879B, and no pytest/colcon, unrelated ROS/Gazebo/MuJoCo/MoveIt, Docker, or GPU workload overlaps admission.
  - Candidate, implementation, submodule, overlay, image, model, catalog, selection, C2, timeout, reset, retry, YOLO-primary, and no-Worker-fallback contracts match v4.
  - Runtime `/data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/m` and report `/data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-w10-r2-df261a05/w10` are absent; task Domains 215-224 and unit names are free.
success_criteria:
  - One runtime launch produces exactly twenty distinct first-attempt PASSED points, fixed `levels_used=[10]`, 20 YOLO correlations, zero retry/model/Worker fallback, complete initial/terminal evidence, clean exit, and exact cleanup.
failure_criteria:
  - A valid fixed-contract runtime starts but any behavior, infrastructure, evidence, or cleanup gate fails; preserve its first bad boundary and do not launch W10 again.
invalid_criteria:
  - Admission, provenance, source/config/image/model, runtime payload equivalence, unrelated workload, socket, or evidence contamination prevents a valid runtime start; wait for clean admission rather than count it as the requested rerun.
provenance:
  worktree_commit: e41ee9066bf13e5f21e073a5ce54716775d59f4b
  worktree_delta_from_v4_source: documentation ledger only
  runtime_candidate_commit: b0f9e7168198285fba4133026d9d3b132075f88b
  implementation_commit: 59c831f0d771f45f6b930dd59fc85d673a7c96e5
  submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  install_overlay: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp039-real-yolo-w10-c2/candidate-src/install
  runtime_executable: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/exp039-real-yolo-w10-c2/candidate-src/install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch
  ros_domain_id: [215, 216, 217, 218, 219, 220, 221, 222, 223, 224]
  gz_partition: not_applicable
  original_frozen_harness_manifest_sha256: 36dc215804dd756d89522c393e3a7e17befd0c621fe8811db3eaa7eb8e876562
commands:
  - command: /usr/bin/zsh /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-w10-r2-df261a05/forensic-run.zsh 10 m EXP-048-FORMAL-W10-R2
    exit_code: 1
observed:
  - The clean second admission passed at 2026-09-15T20:20:26+08:00 with the frozen candidate, image, model, C2, W10, point-order, reset, timeout, single-attempt, YOLO-primary, and no-fallback identities intact. The first admission was pre-runtime INVALID only because the task-target guide appeared at its sealed baseline while admission was being prepared; it created no runtime and does not count as a W10 attempt.
  - The one authorized runtime wrote BATCH_MANIFEST sequence 1 and POOL_STARTING sequence 2, then wrote POINT_INFRA_INTERRUPTED for all twenty points at sequences 3-22 and BATCH_TERMINAL at sequence 23. No POOL_RUNNING, Worker root, lease, attempt, Broker root, or container was created.
  - Top-level status was INFRA_FAILED after 0.045712864957749844 s with levels_used=[10], 0/20 completed points, no fallback transition, no retry, and batch_cleanup_complete=false. The runner exited 1 after 1.727 s CPU with a 6,209,536-byte observed cgroup peak.
  - Passive capture contains zero matching Docker events, no container state or log because no Broker container existed, and no kernel OOM entry. Host available memory increased from 29,070,241,792 to 29,115,985,920 bytes; swap free remained 4,700,258,304 bytes.
  - Exact final readback found both task units absent/inactive, no owned runtime process, task-domain ROS daemon, container, live socket, GPU compute app, or active Domain 215-224 claim. cleanup=PASS.
  - The frozen report validator exited 1 because the generation-local coordinator aggregate was absent. The report manifest's self-entry is expectedly stale because the frozen wrapper hashes report-files.sha256 while rewriting it; every other listed report file and the independently sealed forensic manifest verified.
inferred:
  - The first bad boundary is STARTUP after durable POOL_STARTING and before POOL_RUNNING. ProductionAdaptivePool caught the underlying exception, but the no-fallback top-level journal persisted only the interrupted points and INFRA_FAILED; the exception detail is unavailable and no deeper cause is asserted.
  - EXP-047 and EXP-048 failed at different boundaries. Their shared W10 setting is insufficient evidence that they share one root cause, and neither OOM nor YOLO saturation is supported by EXP-048.
conclusion: FAILED valid fixed-contract runtime attempt. W10 now has two admitted failures, zero valid twenty-point performance samples, and remains excluded from the W1-W8 scaling curve.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-w10-r2-df261a05
  - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/m
  - admission_r2_sha256: a1f428df50579a5c3f747ba59eeeefe19ce26b4bd700d9c35a18880a7009f040
  - aggregate_sha256: 23c07ddb8f1e43591f63805ba4e179d66b35cb67d4501daf92509d1a29dbe33b
  - coordinator_journal_sha256: 28f8a0cdc18f8576394069ad7a31a8aa54eb3fb817fde8b2b7b20ac8ab49fe75
  - final_cleanup_readback_sha256: f45f216acbd4f551d0f4882147d93bf2c6185918187d7c683ac13f31609d501c
  - forensic_manifest_sha256: fb092e6f2f22e172abbb1975be4c6721366797074237b88a054fb603aeedbba7
decision: STOP_W10_AND_PUBLISH_FAILED_POINT
next_experiment: NONE
```

## CP-046 — W10 rerun closed; maintained guide and deterministic chart published

```yaml
checkpoint_id: CP-046
last_valid_performance_experiment: EXP-046-FORMAL-W8
last_runtime_experiment: EXP-048-FORMAL-W10-R2
status: COMPLETE
confirmed_conclusions:
  - Exactly one new admitted fixed-W10/C2 runtime was launched. It failed before POOL_RUNNING with 0/20 points, and no third W10 run was launched.
  - W1-W8 remain the only valid scaling points. W8 is the fastest valid level at 263.6432132720947 s and 4.551605880943091 points/minute; W4 is the efficiency knee at 0.9653388591915982.
  - W10 has two independent admitted failures and zero valid performance samples. EXP-047 failed after 10/20 and a disappearing Broker container; EXP-048 failed during startup before any Worker or Broker existed.
  - The guide uses maintained JSON and a deterministic standard-library SVG generator. Failed W10 data is marked in red and is not connected to the valid W1-W8 curve.
  - Final SVG visual readback passed after a RED/GREEN correction of the full W1-W10 x-axis domain. The corrected 1200x900 render is retained, and the first incorrect render remains as diagnostic evidence.
verification:
  focused_pytest: 5 passed in 0.01 s
  focused_pytest_elapsed_s: 0.26
  final_scratch: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/chart-final-df261a05
  generator_check: PASS
  json_parse: PASS
  svg_xml_parse: PASS
  git_diff_check: PASS
  visual_readback: PASS
source_commit: 0c52cc42bf5b37610dfea49ac8d2b54f2e8ad0ae
artifacts:
  guide: docs/guides/so101-parallel-adaptive-worker-pool-source-guide.md
  guide_sha256: fa8b69d85180e83316c1d3a2a44697ecfe4049efed51a45cc0a89e7e2a3fb326
  maintained_data: docs/guides/data/so101-parallel-worker-scaling.json
  maintained_data_sha256: 9107ab348a31cb832709d15c51f7575fd1f687f2638599f10bb674ce490b6d9b
  generator: scripts/generate_so101_parallel_worker_scaling_chart.py
  generator_sha256: ca0cef5352519863a326c2aca11824e7af42a40b7c2427c798f09625644be975
  generated_svg: docs/guides/assets/so101-parallel-worker-scaling.svg
  generated_svg_sha256: 85ddb039bddd7219a1c52a81df8bbb3d8d34aca93fa0d9963678353e67285ed5
  generator_test: src/so101_demo_py/test/test_generate_so101_parallel_worker_scaling_chart.py
  generator_test_sha256: 8b763951dabcf7cefe2075e9f39217f2a84c5df1d2e9d06233d841ef217e4cca
  comparison_v2: /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-w10-r2-df261a05/comparison-v2
  comparison_v2_manifest_sha256: 473d4508a641e48053ae4b36edabfc4261f2180540923c62c3f468eddd877698
  corrected_render_sha256: 61cb8cf09b78aa844ee2a83a603bf2427266d47ccf3e59c1f1b09fa475fb253c
protected_dirty_test:
  path: src/so101_demo_py/test/test_parallel_batch_resources.py
  diff_sha256: ae383016c78eca3c02e05f600d58fb4a65211f4783acf9612ea38e374baf380c
  staged: false
retention:
  retained_runs:
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-8d75fe6f-v4
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-w10-r2-df261a05
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/g
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/h
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/i
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/j
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/k
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/l
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/r/m
  archived_runs: []
  deletion_candidates:
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/chart-pytest-df261a05
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/chart-pytest2-df261a05
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/chart-red-df261a05
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/chart-green-df261a05
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/chart-final-df261a05
    - /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/formal-worker-scaling-w10-r2-df261a05/so101-parallel-worker-scaling-render.png
    - /tmp/so101-debug-df261a05
  deleted: []
cleanup: PASS
next_experiment: NONE
```
