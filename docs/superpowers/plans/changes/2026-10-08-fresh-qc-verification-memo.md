# A content-bound memo of the fresh-process QC for the run's result gates

Date: 2026-10-08

Trigger: with native collection the full QC recomputation (`recompute_native_qc`: seal verification, physical audit, native QC) is no longer cheap. Measured on the sealed episode of 147cb073 (440 MB, 856 rows, 51300 native steps): 289 s without profiling, 447 s under cProfile; the profile is flat (JSON decoding of 164k records, world-source verification 74 s, raw-chunk verification 83 s). The run's result chain repeats it:

- the Worker's ResultStore at seal: seal verification, physical audit, QC recomputation;
- the Coordinator's `_commit`: `result_port.verify` is called twice, each doing the same three steps, inside the Coordinator's state lock;
- the Worker waits `result_ack_timeout_s = 10 s` for that commit; the heartbeat timeout is 5 s; the FINALIZING stage is 120 s.

About 8 minutes of verification per gate against a 10 s acknowledgement cannot pass, and a Coordinator lock held for that long starves the heartbeat.

Options considered:

1. Raise `result_ack_timeout_s`, the FINALIZING stage and the heartbeat timeout. Rejected: the Coordinator would hold its lock for about 16 minutes and every other worker would starve; these are safety bounds.
2. Memoise inside one process. Insufficient: the processor, the Worker and the Coordinator are three processes.
3. A memo written by the independent fresh-process QC and bound to the content. Taken.
4. Drop the commit-time recomputation. Rejected: the commit would then trust a claim.

Recommended option taken under CP-3394: option 3.

## What changed

- `act/qc_memo.py` (new). `fingerprint` hashes every file of the episode tree (path, size, SHA-256; a symbolic link or special file refuses), the run scope, the frozen inputs and the Teacher manifest (absent is a value). `write_memo` (PASS reports only) writes `qc-verification-memo.json` beside the report: kind, schema, QC rule version, what it covers (`episode_seal`, `physical_audit`, `native_qc`), the SHA-256 of the canonical report and the fingerprint. `memo_matches` is true only if all of those equal what is on disk now. The fingerprint is cached per process while every file's size, mtime and inode are unchanged, so the Coordinator's second call in `_commit` hashes nothing.
- `act/offline/fresh_qc.py` writes the memo after it published a PASS report (never for a diagnostic run).
- `ActCollectionResultStore` and `ActCollectionResultVerifier` take `trust_fresh_qc_memo` (class default False). When true and the memo covers the report and the files, they skip the three covered verifications (reading the identity facts from the seal document instead) and use the report as its own recomputation. Any mismatch recomputes in full. The Worker's store and the Coordinator's verifier are built with it in `mujoco_parallel_batch.py`.
- The readback never trusts the memo: `verify_coordinator_commit`, `act_first_episode qc` and `verify-commit` construct their verifiers with the default, so the post-run readback is still the full independent recomputation (about 5 minutes).

Measured on the real episode (laid out as a working directory with its Teacher manifest): `_verify_result_qc` with the memo 0.4 s, without 289.4 s, same report. The same run showed that the full recomputation of the report written by the processor (with the Teacher manifest) equals the ResultStore's recomputation (which finds the manifest beside the episode), so the two QC paths agree on a real episode.

Trade-off, stated: at seal and commit the run trusts that the fresh-process QC ran honestly on exactly these bytes. It cannot be forged by changing the episode afterwards (the fingerprint), but a hand-written memo for a hand-made episode would pass those two gates; the readback would still fail it. The files are written by the same user in one evidence tree, so this is the same trust boundary as before.

## Tests

`test_p3_qc_memo.py` (23): the memo is recognised for the same content; fourteen kinds of other content recompute in full (episode byte, added or removed file, symlink, scope, inputs, Teacher manifest changed or removed, report, status, rule version, memo missing, garbage, other fingerprint); only PASS gets a memo; the fingerprint cache; the fresh-process QC writes it beside a PASS and not beside a FAIL; the gates trust it only when asked, with the coverage skipped on a real sealed result for the Coordinator's verifier and the Store; the readback never asks; the composition asks in both gates.

Rollback: `p3-base.tar.gz` (`result_store.py`), `p3-base3.tar.gz` (`mujoco_parallel_batch.py`, `fresh_qc.py`); delete `act/qc_memo.py`.

Ledger CP: CP-3456.

## Rework (CP-3457)

- The memo is also bound to the QC code: `qc_memo.code_digest()` is the SHA-256 of the source of `episode_qc`, `episode_audit`, `recorder`, `native_endpoints`, `raw_physics_chunks`, `scene_association`, `execution_snapshot`, `collection_boundaries`, `first_episode_inputs` and `qc_memo`, stored in the memo (schema 2). A Coordinator or Worker running other QC source than the process that wrote the memo recomputes in full; a memo of schema 1 or without a digest is not trusted. Test: `test_a_memo_written_by_other_qc_code_triggers_a_full_recompute`.
- Stated plainly (review item 10): a journal commit rests on the memo. The Worker's seal and the Coordinator's commit accept the episode because the fresh-process QC wrote a memo for exactly these bytes and this code. Nothing is exportable on that basis: `bundle.py` and `resolve_committed_episodes` call `verify_coordinator_commit`, which constructs its verifier without the memo and recomputes in full; so does `act_first_episode verify-commit` and `qc --run`. P4 L2 therefore requires the readback receipt (`commit-proof.json` from the full recomputation) in addition to the commit; a commit without it is not an acceptance.
