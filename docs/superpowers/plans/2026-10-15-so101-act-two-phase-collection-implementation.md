# SO-101 ACT two-phase collection: implementation plan

The design is in `docs/superpowers/specs/2026-10-15-so101-act-two-phase-collection-design.md`. Nothing here may be executed before the human confirms this plan.

## Execution rules

- **Roles.** Claude Sonnet 5.5 subagents implement and Opus reviews (human rule "审查用Opus模型，执行用Sonnet模型"). There is one writer at a time, in the existing worktree and branch.
- **Workflow.** Use TDD: write the failing test first. Run targeted tests through `run-gate-env-targeted.zsh`.
- **Gate.** The coordinator runs the full host gate at each checkpoint marked GATE.
- **Thresholds.** Do not lower any threshold. Do not change any data rule.
- **Ledger.** Every task commits separately and the ledger records each checkpoint.

## Tasks

| # | Task | Main files | Done when |
| --- | --- | --- | --- |
| 1 | Phase-1 seal without processing: shard task ends after the Teacher and the bag; result sealed with `PENDING_QC`; `raw/recording-receipt.json` with raw-file hashes; no processor call | `act/offline/orchestration.py`, `runtime/parallel_worker_parts/collection.py`, `execution_recovery.py`, `act/result_store.py`, `container_campaign/task_builder.py` | unit tests: PENDING_QC seal, receipt hashes, Teacher fields final, no processor process started |
| 2 | Phase-1 host verification of PENDING_QC records and receipts; phase-1 summary; post-phase `syncfs` | `result_verifier.py`, `result_store.verify_container_task_registration`, `owner.py` | tests with fixture records |
| 3 | Processor program `campaign_processor`: one-way control (start, assign_task, get_status, terminate); runs `act_offline_episode` on an assigned attempt; writes `processed-result.json` bound to the phase-1 `result_sha256` and the receipt | new `cli/campaign_processor.py`, `runtime/act_processor/` | tests with a fake processor and fixture attempts; rc mapping 0, 2, 3, 4 |
| 4 | Processor container role: argv without GPU; read-only mounts of phase-1 attempts; registry role; admission and cleanup role; stop proof | `container_campaign/launch.py`, `paths.py`, `registry.py`, `so101_teleop/unified/admission.py`, new `processor_owner.py` | tests for argv, mounts, registry and admission refusal |
| 5 | Phase-2 scheduler: queue, `processor_count` (memory-derived default), retries up to `processing_max_attempts` for infrastructure failures only, `host/processing-journal.jsonl`; time limits: total deadline, optional `collect_timeout_s` / `process_timeout_s` (sum at most the total), otherwise `processing_reserve_s`; config keys `processor_count`, `processing_max_attempts`, `processing_reserve_s`, `collect_timeout_s`, `process_timeout_s` | `coordinator.py` or a new `processing_coordinator.py`, `owner.py`, `runtime/inference/config.py` | tests for retry, no retry on rc 3 or rc 2, each per-phase limit and the total, refusal when the sum exceeds the total |
| 6 | `verify_processing`, combined per-scene proof, `campaign-result.json` and `collection-index.json` from it; quality gates and recompute topology read the combined proof | `result_verifier.py`, `act/collection_quality_gates.py`, `act/collection_qualification_recompute.py`, `act/bundle.py` | qualification recompute tests on fixtures; functional runs still refused as qualification evidence |
| 7 | Native processor owner and launcher for single-worker native runs | `container_campaign/native_owner.py`, `native_launcher.py` | tests mirroring the native shard owner |
| CP-A | Checkpoint: Opus review of tasks 1–7, then GATE, then image rebuild with a processor entrypoint readback (`rosbag2_py`, MuJoCo, processor imports) | — | gate PASS |
| 9 | Debug run: both phases, 16 scenes, eight workers, all samplers and traces | prep dir cloned from the debug inputs | Teacher and recording results; VALID count against EXP-599 (13 of 16); phase durations; per-message trace classification of late frames in phase 1 |
| 11 | Remove the inline mode and POST_RECORDING / CPU-shares code (design section "Removal"); adjust the affected tests (about 24 files) | listed in the design | gate PASS; no references left |
| CP-B | Checkpoint: Opus review, then GATE, then image rebuild | — | — |
| 12 | Eight-shard qualification run (40 scenes, both phases) and report | prep dir from the EXP-595 template | report built and verified |

## Order and dependencies

- **Implementation.** Tasks 1–2 come first. Tasks 3–5 come next, then 6. Task 7 can run after task 5.
- **Debug run.** Task 9 runs after CP-A.
- **Removal.** Task 11 waits until the two-phase path has passed task 9, so the inline mode is only removed after the replacement works.
- **Qualification.** Task 12 runs after CP-B. Its result decides whether the formal collection follows.

## Out of scope

- macOS verification of the native processor; it follows later on the mac-mini.
- The shard-shell image design (`2026-10-14-so101-act-shard-shell-image-design.md`), which is still unconfirmed.
- Any change to data rules.
