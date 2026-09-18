# Independent implementation-plan re-review audit

review_date: 2026-09-18
reviewer: GPT-6 Astra / High, independent reviewer
decision: CHANGES_REQUIRED
reviewed_plan: docs/superpowers/plans/2026-09-18-so101-parallel-unbounded-queue-resource-budget-implementation.md
reviewed_plan_lines: 813
reviewed_plan_sha256: 1cdc2e83f7349a76118c394d688c3e9400ef15ec628626c837a0da955063a2c1
frozen_design_sha256: 5e085f98e9926591fbefd3d6e16c16b33bfc9956df9221c46f383b310553657b
prior_plan_review_sha256: 6ef9a6fc04c75431912096f30f751b2d14db970fb520bd73aa5fa4a18fb212af
source_of_truth: ai-station:/data/work/ws_moveit
fresh_source_commit: 6701a7be794eac410aa351106cbc17d58568d1ad
registered_evidence_root: /data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main

## Scope and closure

The complete 813-line revision was read. Read-only checks reconfirmed the retained recovery API/helpers, actual provenance comparison, and installed colcon CMake test task behavior. No implementation, tests, build, browser, service, cleanup, dst, remote write, commit, or push was performed. Only this new review was written; earlier reviews, design, and plan were preserved.

| Prior finding | Revision evidence | Disposition |
| --- | --- | --- |
| P1 recovery default/API | 197-230 | CLOSED. Keyword-only store and apply=False now match the snapshot; default-preview/no-write and positional-call rejection are explicit. |
| P2 queue regression lifecycle | 461-484 | CLOSED. The fake-evidence EXECUTE test commits PASSED, performs 19 legitimate generation transitions, and verifies the same slot's 20 leases and final RECOVERING state. It no longer asks physical commit to accept validation outcomes. |
| P3 browser environment/R01/dependencies | 581-583, 629-644, 743-780 | CLOSED. Copied offline and production prefixes are distinct, child dependency origins are mapped explicitly, required fixture environment is exported, and the same-invocation project dependency runs preflight then the genuine v2 N1 R01 producer before 02/04. Earlier-root receipts cannot satisfy it. |
| P4 source/copy/A1/D publication order | 720-739 | CLOSED for promotion. Source references are committed before copied-carrier publication; unchanged non-carrier bytes and R are checked before clean A1/D. Owned consumers then read back actual installed references. Later metadata commits require new equivalent audit records without replacing history. |
| P5 logs/evidence root | 81-122 and tool calls throughout | CLOSED. Concrete wrappers set global colcon log base and new per-invocation browser roots, retain argv/output/exit/elapsed, and keep independent NVMe tempfile proof. |
| Actual allocator restore API | 557, 571-572 | CLOSED. adopt_existing is named correctly, its separate old formula is included in migration, and fresh budget/provenance and v1-rejection regressions are required. |

The Stage A code completion → Stage B freeze → Stage C measurement → Stage D promotion → Stage E browser graph remains sound. No runtime feature expansion is requested. Two remaining Task 12 sequencing errors must be corrected before the plan can be followed literally.

## Required corrections

### R1 [P2] Reconfigure/rebuild the dev test tree after Stage A and before inspecting/running CTest

Plan locations: initial build at 180-186; Task 12 lines 614-628.

The only dev-build creation occurs in Task 0, before Tasks 1, 9, and 10 add CMake pytest registrations and before later Stage A changes. Task 12 then inspects that original CMakeCache/CTestTestfile and immediately runs colcon test. Those generated files still describe the earlier test set. The subsequent offline copied build happens after the claimed full colcon gate, so it cannot repair that gate retroactively.

Source evidence: `src/so101_teleop/CMakeLists.txt:69-72` registers tests through ament_add_pytest_test at configure time. The installed `/usr/lib/python3/dist-packages/colcon_cmake/task/cmake/test.py:38-103` consumes the existing build tree and invokes CTest; it does not reconfigure/build the changed package first. The direct full pytest pass does not prove the missing CTest registrations were exercised.

Minimum correction: after all Stage A code is committed and before Task 12's CMakeCache/CTest executable inspection, run a fresh logged `so101_colcon` build against the existing dev-build/dev-install bases, preserving symlink-install and explicitly refreshing CMake configuration (for example the existing package-scoped build plus `--cmake-clean-cache`). Re-source that overlay, enumerate the resulting CTest registrations, assert all newly added package tests are registered, and derive the exact interpreter list from those newly generated commands. Only then run the two package test gates with their separate NVMe scratch proofs. This adds a build prerequisite, not another test suite or benchmark run.

### R2 [P1] Refresh immutable provenance bindings after metadata commits before every runtime boundary

Plan locations: lines 653-657 and 690-696; existing correct promotion handling at 739.

Task 12 generates `production-provenance.json` and A0 with the current clean source commit, then explicitly commits checkpoint/ledger changes before spawning the owned server and commits the recovery ledger again at the end. Stage C subsequently launches the candidate using the same binding path. These documentation commits leave R unchanged but change HEAD, so the already generated strict external binding no longer identifies the current source. Current CLI verification rejects this exact case with PROVENANCE_EXTERNAL_SOURCE_COMMIT. The promotion section handles the same problem at line 739, but its refresh step is not applied to the earlier Task 12 → Stage C transition or later guide/checkpoint commits before another runtime use.

Source evidence: `src/so101_demo_py/src/cli/mujoco_parallel_batch.py:725-731` checks source-root identity and requires `document['source_commit'] == source_commit`; live fixture source checks likewise bind the exact clean HEAD. The frozen design allows metadata-only commit differences through unchanged L/S/E/I/R, but does not authorize stale raw deployment/provenance audit bindings.

Minimum correction: make a common pre-spawn/pre-admission rule for server start/refresh, every candidate batch, production admission, and live browser invocation. First finish all pending tracked metadata commits and prove clean HEAD plus unchanged execution/install identity. Then create a new immutable provenance/raw-audit record for that HEAD, retain the old binding/A0/A1/D records, and explicitly select the new binding in the next runtime environment/authorization. For a candidate, bind the next authorization to the new audit and exact HEAD before sealing it; never rewrite a sealed earlier authorization or measurement. After promotion, create a new equivalent A1/D when required without changing R/P/Q/M or overwriting previous receipts. No extra tracked commit may occur between that selection and spawn without repeating the metadata-only refresh.

Move Task 12's ledger commit before the final pre-spawn audit/binding generation, or add the same explicit refresh immediately after it. Apply the rule again after its final recovery ledger commit before Stage C. Writing the new audit/binding under the registered evidence root avoids creating another tracked-source commit loop. R-changing edits still require the existing new qualification path; this correction is only for allowed metadata changes.

## Disposition

CHANGES_REQUIRED is limited to R1-R2. Original plan findings and the design remain closed at their respective levels. There is no request to rerun old runtime experiments during document revision or to implement a new provenance bypass. Re-review the minimally amended plan at a new immutable hash.

Current remote tracked source was clean with the same two unrelated untracked documents. Fresh source/install/service/ownership verification remains an execution precondition; no old PID or missing service was acted upon.

retained: this re-review, unchanged prior reviews/design/plan, and all existing evidence.
archived: none.
deletion_candidates_created_by_review: none.
