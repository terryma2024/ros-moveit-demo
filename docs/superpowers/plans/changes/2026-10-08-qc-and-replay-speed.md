# QC and replay speed (Phase B1 and B2)

Date: 2026-10-08

Trigger: on the L2 episode (bag 45315499) the offline processing took 537 s (scan 13, replay 267, fresh QC 253), the in-run commit proof 421 s, and the readback about 1,993 s (qc 247, verify-commit 421, check-export 1,325). The user asked for the three steps to fall to 10% of that time without changing a byte of what the QC reports.

Options considered:

1. Parallelise the QC. Rejected: the cost is the same pure verifiers run several times over the same files, and the GIL-bound C message decoding does not run in threads (measured: 4 threads take as long as 1).
2. Speed the verifiers up one by one and leave the repetition. Rejected as the main lever: the repetition (audit manifest verified 4 times, native events 2, seal 2, execution snapshot 34, MuJoCo model loaded 66) was the larger part.
3. Keep every verifier and its semantics, run each pure verifier once per process and per unchanged set of files, and remove the quadratic scans and redundant per-value work. Taken.

Recommended option taken under CP-3394: option 3.

## What changed

New module `act/qc_session.py`: a per-process memo that exists only inside a `with qc_session():` block.

- `session_memo(key)`: a verifier called twice with the same arguments over files with the same signature (path, size, inode, mtime of every file it reads) returns the first call's result. A verifier that raises is not remembered. Outside a session nothing is kept, so every other caller behaves as before.
- `cached_lines(path, parse, kind)`: one parse of a JSON-lines file per file signature, shared between callers (they only read it; checked: after a full QC the cached rows equal a fresh parse).
- `load_model(scene, root)`: one `MjModel` per session instead of 66.

Where it is applied (verifiers and the files they read are unchanged):

- `verify_audit_manifest`, `verify_episode_seal`, `verify_execution_snapshot`, `verify_native_collection_events`, `verify_episode_physical_audit`, `verify_original_frame`, `verify_raw_chunk`, `validate_world_source`, and the pure helpers `_world`, `_raw_source_matches` and the source-model check.
- Sessions are opened by `recompute_native_qc`, by `ActCollectionResultVerifier.verify` (the commit proof) and, in the offline engine, around the final seal and its readback. The fresh-process QC never shares a session with the engine: it is a separate interpreter.

Primitives:

- `native_endpoints.first_world_after_capture_start` and `first_world_after_stop` scanned all raw samples for every world source (8,000 sources against 58,000 samples): they use the existing step index (`_raw_steps_at`).
- `raw_physics_chunks`: the per-value `_number` checks of a vector or a group are one C-level pass (`_numbers`; same verdict and error code, tested against the old check for 20 value kinds); `_exact` compares key views instead of building sets; `verify_raw_chunk(previous_verified=True)` skips re-verifying the previous chunk where the caller verified it one pass earlier with the same arguments (the three QC loops and the physics adapter's admission; the default stays the full check).
- `raw_chunk_from_ros` no longer deep-copies the tree `message_to_ordereddict` has just built.

## What was measured, and what was not the cause

Replay profile (45315499, `phase-times.py`, unprofiled wall time, after the changes): `deliver_due` 70 s (of which message deserialisation 33 s over 368,000 messages), the physics chunk admission 24 s, the controller-reference callback 17 s, draining the sources 29 s, the capture and row minting 25 s, the final seal and readback 30 s. Before the changes the seal and readback alone took about 100 s because they ran the audit verifiers six times. PNG encoding and decoding is not a visible cost (the hypothesis in the task was not borne out), so no compression setting was touched and no output byte changed for that reason.

Not done, and why: threading the message deserialisation (no gain, GIL), replacing `json.loads(json.dumps(...))` in the controller-reference observer (about 8 s, but it fixes the text of a hazard reason), memoising `decode_ros` across rows (the rows hold equal but distinct dicts and the result is a mutable ROS message).

## Results (L2 episode, quiet machine, sequential, same machine)

| Stage | Before | After | After / before |
| --- | --- | --- | --- |
| Offline processing, total | 537 s | 190 s | 35% |
| scan | 13.5 s | 13.0 s | |
| replay (including seal) | 266.7 s | 147.9 s | 55% |
| fresh QC (in the processor) | 252.8 s | 25.9 s | 10% |
| Readback `qc` | 247 s | 26 s | 11% |
| Readback `verify-commit` (= the in-run commit proof) | 421 s | 27 s | 6% |
| Readback `check-export` | 1,325 s | 77 s | 6% |
| The three steps together (processing + proof + readback) | 2,951 s | 347 s | 11.8% |

The target was 293 s. With this change alone the three steps are at 347 s; the remaining distance is the three recomputations `check-export` still makes, and the replay. The single-readback design (`2026-10-08-single-fresh-readback.md`, awaiting review) removes the repetition across the readback commands and brings the total to about 245 s by the same measurements. It is not implemented.

Raw numbers: `phaseb/times-base1.tsv`, `phaseb/times-final1.tsv`, `golden-20261008/45315499/{base1-proc,final1-proc}/`.

## Verification (CP-3468 definition)

(a) QC byte identity, old code (commit d33def737, `phaseb/baseline-d33def737/`) against the new code on the same episodes:

- the live sealed L2 episode and the processor-built L2 and 147cb073 episodes: the three `qc-report.json` are byte-identical (sha256 7c43bcf7... for the live L2 episode, which is also the hash of the readback evidence; 6c70cc79... and e06aaad... for the two processor-built ones);
- the INVALID golden cases and the three fault bags have no sealed episode: both versions fail with the same error chain (`EPISODE_PHYSICAL_READBACK_INVALID` caused by `EPISODE_SEAL_MISSING`);
- nine deliberately damaged copies of the L2 episode (a byte of `events.jsonl`; a frame; a malformed number in a raw chunk, re-signed; a world source with a missing native step, re-signed; a reference value, re-signed; a terminal event clock moved before the normal stop, re-signed; a record action with the seal re-signed; a record's measured state with the seal re-signed; a Teacher manifest whose end is past the recording): the same error chain from both versions, and for the Teacher-manifest case a byte-identical FAIL report. They reach five different stages: hash chain, audit streams, native collection QC, seal rows and physical readback.
- the three readback outputs (`qc.json`, `verify-commit.json`, `check-export.json`) are byte-identical to the original readback evidence.

(b) The processor, run on all eight golden inputs after the change: EQUIVALENT to golden modulo the nondeterminism list. One item was added to the list (N9): the lossless writer queue's evidence in `events.jsonl` (interleaving of `accepted` and `written` events, their outstanding counts and `peak_samples`) follows thread timing; the totals, the event count, the closing event and the policy are compared. It is new in the list because the faster main thread made it visible once in eight runs; it was always possible. The comparator still reports 147cb073 against 45315499 as NOT_EQUIVALENT.

(c) Full gate (`pytest -n 8`, cwd outside the worktree, the three git-cwd provenance files excluded): 7,490 passed, 186 skipped, 0 failed (23 new tests in `test_b1_qc_session.py`; RED against d33def737 where the module does not exist). Scratch colcon install: build OK, 212 tests of the installed package pass.

(d) Independence: `recompute_native_qc` never reads the memo and starts its own session; the processor's fresh QC and the readback commands are separate interpreters that share nothing with the engine. A session never outlives its block and is not written to disk.

## Rollback

`p5b-base.tar.gz` (sha256 in `p5b-base.tar.gz.sha256`) holds the files this change touched as of d33def737.
