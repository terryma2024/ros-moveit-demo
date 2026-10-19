# SO-101 ACT open optimisation and engineering to-dos

This is the tracking list for to-dos the human asked to record. Update it when an item starts, finishes or changes, and cite
the ledger checkpoint. Evidence and results belong in the ledger (`docs/experiments/so101-act-data-experiment-ledger.md`).

Last updated: 2026-10-19.

| # | Item | Status | Source / evidence |
| --- | --- | --- | --- |
| 1 | **Logic vs runtime parameters, and stage-by-stage collection.**<ul><li>L frozen and sha-bound, R free, RO within the qualified envelope.</li><li>`act_collect_parallel --stop-after-phase1`, and `act_process_parallel --phase2 \| --retry-round \| --finalize`, each with a fresh runtime document; skipped retry rounds can run later.</li><li>Templates freeze and check only logic files; source-text checks are replaced by behavioural tests.</li><li>Training: runtime block, `num_workers` ≥ 1, optimiser constants in the hash, source commit bound to the policy.</li></ul> | Confirmed design; implementation starts after the EXP-625 seal | `docs/superpowers/specs/2026-10-19-so101-act-logic-vs-runtime-params-design.md` |
| 2 | **Phase-2 per-case processing.**<ul><li>About 183 s median, single-core (about 1.0–1.1 cores and 1.1–2.4 GiB per processor).</li><li>Find the hotspots and add parallelism within a case.</li></ul> | Profiling (subagent) | EXP-625 `host/processing-journal.jsonl`; report `R/phase2-profile-20261019/report.md` |
| 2b | **Post-run collection verification** (`so101_demo.act.bundle._verified_collection_uncached`).<ul><li>On EXP-625 it ran 17+ min on one core (about 98.6% CPU).</li><li>Find out why the O1 parallel readback / verify-once path is not used.</li><li>Make it parallel (workers = runtime) or reuse the existing proofs.</li></ul> | Analysis (same subagent) | Same report |
| 3 | **Finalize readback and merge.**<ul><li>EXP-625 retry-2 ended at 02:36:28Z, but the index and result were written at 02:45:15Z: about 8 min 47 s with no writes, about 200k files and 60–70 GB at about 120 MB/s.</li><li>Options: more `readback_workers` (runtime), verify once with reuse of the phase-2 proofs, batching, an incremental merge per round.</li></ul> | Analysis (same subagent) | Same report |
| 4 | **Phase-2 `processor_count`.**<ul><li>About 14 at an 80% CPU and memory budget, or 16 if the per-processor peak stays at or below 2.5 GiB.</li><li>Needs item 1 first, because processor_count must become a runtime parameter.</li></ul> | Waiting on item 1 | Measured on EXP-625: 6 processors used about 7.6 of 32 threads and 16 of 62 GB |
| 5 | **Gate scratch.** Each v4 gate leaves about 12 GB of pytest TMPDIR under `R/scratch`; let the gate prune it after readback. | Open | Batch h deleted 93.6 GiB (`R/evidence-deletion-20261019h`) |
| 6 | Rollout O6 hardening, then a real rollout run. | Open | Native rollout design 2026-10-18 |
| 7 | Load flakes: `test_owner_phase2`, `test_capture_runs_before_teacher_start` (real-rate replay), `so101_teleop` `test_process_identity` (UNKNOWN identity), C++ timing tests. | Open | Gates `d1815a322f89.run1-fail` and others |
| 8 | Nsight Compute: SM Active and bubble ratio for training. | Open | — |
| 9 | frm-044 refusal message specificity (`EPISODE_COLLECTION_IDENTITY_INVALID`). | Open | Differential readbacks 2026-10-18 |
| 10 | Template defects found on side-wrist: verify-report fingerprint source (fixed in the template, CP-3740), stale source pattern (fixed, CP-3741). These are covered by item 1's template work. | Covered by item 1 | Ledger CP-3739..CP-3741 |
