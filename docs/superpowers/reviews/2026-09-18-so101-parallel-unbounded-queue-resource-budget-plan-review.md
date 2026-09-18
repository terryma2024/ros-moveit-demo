# Independent implementation-plan review audit

review_date: 2026-09-18
reviewer: GPT-6 Astra / High, independent reviewer
decision: CHANGES_REQUIRED
reviewed_plan: docs/superpowers/plans/2026-09-18-so101-parallel-unbounded-queue-resource-budget-implementation.md
reviewed_plan_lines: 667
reviewed_plan_sha256: 2215580f442fb93a2651b99105600d007a6768a0248196e89c7f772b0712e726
frozen_design_sha256: 5e085f98e9926591fbefd3d6e16c16b33bfc9956df9221c46f383b310553657b
design_rereview_sha256: da7ed1f20cfcbbd503c9c0c812e4ce75bdf52fe1a46c00a624f7ca392ae894e0
source_of_truth: ai-station:/data/work/ws_moveit
fresh_source_commit: 6701a7be794eac410aa351106cbc17d58568d1ad
registered_evidence_root: /data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main

## Scope and accepted dependencies

All 667 plan lines were read against the previously fully reviewed, unchanged frozen design and design re-review. Existing helpers, APIs, coordinator state transitions, browser fixtures, commands, and retained recovery source were inspected read-only on ai-station. No implementation, pytest, colcon, Bun, browser, service, cleanup, dst, commit, or push was run. Only this audit file was written; the plan, design, and earlier reviews remain unchanged.

The stage graph at plan lines 83-93 and Task 12's entry gate at 530 is accepted: Task 13 aggregation, Task 14 promotion/deployment parsing, and Task 15 verifier/test code are completed offline before the final Task 12 install/identity freeze. Numeric task order is not the execution order. There is no finding merely because the runtime implementation does not yet exist.

The plan carries the design's K removal, immutable v1 history, typed authority separation, candidate/calibration bootstrap, raw resource/error accounting, finite coverage, independent promotion, model selection, and fresh service ownership boundaries. The following concrete corrections are needed before this can serve as the executable plan.

## Required corrections

### P1 [P1] Preserve the recovery function's preview-by-default API

Plan location: line 153, Task 1 interfaces.

The quoted retained API is not the actual API. The snapshot defines `recover(*, store, campaign_id, command_id, parallel_config, inspector=None, source_commit, apply=False)` at `operator-recovery-implementation/recovery-source-snapshot/data/work/ws_moveit/src/so101_teleop/so101_teleop/expert_validation/operator_recovery.py:109-110`. The plan declares a positional `store` and `apply: bool = True`. Following that declaration either breaks callers against the retained implementation or changes an explicitly preview-by-default operator boundary into an applying default. The later instruction to preserve the actual API does not resolve the contradictory signature.

Minimum correction: quote the real keyword-only signature with `apply=False` and optional inspector. Keep the CLI's explicit `--apply` boundary. Add an offline assertion that omission of `apply` produces preview without mutating store/fences/receipts, plus keyword-only invocation coverage. No new operator recovery application is authorized by this correction.

### P2 [P1] Repair the unbounded-queue regression to use the real result and recovery lifecycle

Plan locations: lines 391-404, Task 7 RED example; helper reuse at 389.

`make` defaults to EXECUTE. The existing `finish` helper calls `commit_result`, which converts the result to `AttemptStatus`, so `ValidationStatus.VALIDATION_PASSED` fails at the first point. Moreover, committing any normal result moves the worker to RECOVERING; the next `start(c)` at generation 1 cannot grant a lease. The test therefore cannot turn GREEN after only removing K, and could encourage weakening the very recovery boundary this plan requires preserving.

Source evidence: `src/so101_demo_py/test/test_parallel_batch_coordinator.py:55-99` defines the fixture/start helpers; `finish` and `recover_worker` at 162-191 use the real commit and fenced generation transition. `src/so101_demo_py/src/parallel_batch/coordinator.py:771-803` uses AttemptStatus for physical results and moves the worker to RECOVERING. Existing `test_terminal_point_never_requeued_and_recovered_worker_steals_next` demonstrates the intended flow.

Minimum correction: keep this a fake-evidence EXECUTE scheduler test, pass `'PASSED'` (or `AttemptStatus.PASSED`) to `finish`, retain a generation variable, and call the existing `recover_worker` between points before the next `start(..., generation=generation)`. After the twentieth point, check the terminal state and total lease_count against the current generation without requesting an obsolete-generation lease. Assert that the same slot consumed all points and that recovery count/generations are correct. Do not make commit_result accept validation outcomes or remove recovery to make the example pass.

### P3 [P1] Complete the browser fixture environment and generate R01 in the new evidence batch

Plan locations: lines 508-521, 624-635. Primary anchor: line 631.

The Stage E command selects `preflight.spec.ts`, `02-parallel.spec.ts`, and the new 04 suite in a newly created browser batch. The existing 02 suite requires an R01 receipt under that exact root; only `01-sequential.spec.ts` produces it. The preflight spec checks fail-closed setup behavior and does not run R01. Thus this command deterministically reaches `R01_GATE_REQUIRED` even with valid resource profiles. The text saying not to skip R01 does not provide a producer/order for it.

The existing installed/live fixtures also require environment variables absent from the listed setup commands: `SO101_E2E_INSTALL_PREFIX`, `SO101_E2E_PYTHON`, and, for live, `SO101_VALIDATION_PROVENANCE_BINDING`. Setting TEST_PYTHON or sourcing an overlay does not set these fixture variables. Existing fixture code also needs a deliberate dependency-prefix mapping because this plan's new prefix contains only the two selected packages, while other MuJoCo/ROS support packages remain in the verified canonical underlay.

Source evidence: `web/e2e/expert-validation/live-sim/02-parallel.spec.ts:15` calls requireGate R01; `01-sequential.spec.ts:109` writes it. `fixtures/installed.ts:15-27` requires its prefix/Python variables. `fixtures/live-sim.ts:89-121` requires the existing evidence directory, provenance binding, and prefix; lines 213-240 derive package/Python/library paths and require the Python variable. `fixtures/live-sim.ts:226-250` reconstructs environment paths, so inherited source-shell paths cannot be assumed to survive.

Minimum correction: add an explicit environment/readback block for offline installed gates and a separate production block for live gates, binding the correct dev versus frozen production prefix, exact Python, current provenance binding, v2 configuration, and fresh registered evidence subdirectory. Update the fixture mapping during Stage A to retain the verified dependency origins when using the two-package overlay. In Stage E, run the v2-compatible 01 sequential prerequisite first and verify its fresh R01 in the same browser batch before running 02/04; migrate 01 in Stage A if its assumptions require changes. Do not reuse a receipt from an older root or bypass the gate. Keep the existing approved exclusive-window/stack-conflict guard.

### P4 [P1] Commit and install the deployment-reference change before creating A1/D

Plan locations: lines 541-549 and 615-616. Primary anchor: line 616.

Task 12 deliberately creates a copied, non-symlink production installation with candidate/null references. Task 14 then says to publish references, save raw A1, prove a clean commit, generate D, and perform production admission, but puts the source metadata commit at the end and contains no step that updates the copied installed carrier. A source-only config edit cannot change the already copied runtime YAML. If references are merely edited before A1, source is dirty; if the commit happens after A1, A1 no longer describes the committed deployment. Production can therefore still read null references, or the audit fails its own clean-source check.

Minimum correction: specify the exact sequence after approval: create immutable M; update only the three source carrier references; review and commit the permitted source metadata; publish the corresponding copied installed carrier under the authorized window; prove every non-carrier installed byte and L/S/E/I/R unchanged; then create A1 and D using the now-clean source commit and actual installed bytes; finally refresh/reload only the owned consumer as required and run the three live admission checks. A full rebuild is acceptable only if its non-carrier bytes remain identical; otherwise it requires the already defined new-R qualification path. Record this as ordered deployment steps rather than relying on the word publish.

This is a plan sequencing correction, not a change to the design's acyclic R/B/Q/P/M/A1/D graph.

### P5 [P2] Route tool-created logs and offline browser artifacts into the registered root

Plan locations: lines 139, 511-519, 535-544, 627. Global requirement: lines 19 and 25.

The Python helper correctly allocates NVMe scratch and saves pytest outputs. The listed colcon commands, however, set build/install bases without setting the global log base, so ordinary colcon logs are still emitted under the worktree's default log directory. Offline Playwright commands also omit `SO101_E2E_EVIDENCE_ROOT`; `web/e2e/expert-validation/fixtures/config.ts:11-20` explicitly falls back to `test-results` and omits the JSON report when it is unset. These are deterministic violations of the stated single-root evidence layout, not requests for additional tooling.

Minimum correction: add `colcon --log-base "$TASK_ROOT/<unique-run>/colcon-log" build|test|test-result ...` to the concrete command blocks, with each run directory registered before use. Set a fresh absolute `SO101_E2E_EVIDENCE_ROOT` under TASK_ROOT for every contract/installed/live invocation so the existing config routes reports, screenshots, and traces there. Capture Bun stdout/stderr/exit in that same batch. Preserve the independent pytest/colcon TMPDIR/TMP/TEMP proof; log routing does not replace NVMe scratch proof. Ordinary compiled assets are build/install artifacts, and this correction does not require relocating source files or inventing a new tool.

## Additional exact interface correction

At line 477, the existing allocator restore method is `WorkerResourceAllocator.adopt_existing`, not `reconstruct`. `src/so101_demo_py/src/parallel_batch/resources.py:1070` defines it, and its separate old resource formula begins at 1148. Update the named adapter boundary and add a v2 adopt-existing admission/provenance regression while preserving v1 historical rejection. This is part of Task 10's already intended restore coverage, not a new feature. It should be corrected along with P1-P5 so the executor has a real method target.

## Verification and handoff

Current remote HEAD remained 6701a7be794eac410aa351106cbc17d58568d1ad with clean tracked source and the two existing untracked documents. The earlier live-state drift remains a required Task 0 preflight concern; this review neither restarts the disappeared service nor interprets absence as cleanup completion.

CHANGES_REQUIRED applies to the concrete plan corrections above. The design PASS remains intact. Re-review a new immutable plan hash after corrections; no runtime tests are needed for the documentation revision. During later authorized implementation, the corrected tests must demonstrate the intended behavior without relaxing immutable evidence, recovery, resource, or ownership gates.

retained: this review, unchanged plan/design/previous reviews, and all existing evidence.
archived: none.
deletion_candidates_created_by_review: none.
