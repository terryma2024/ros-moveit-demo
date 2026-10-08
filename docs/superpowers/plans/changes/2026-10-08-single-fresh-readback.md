# One fresh-process readback instead of five recomputations

Date: 2026-10-08 (design reviewed PASS-WITH-CHANGES, CP-3470; implemented 2026-10-09)

Trigger: Phase B of the plan to cut the three slow steps on the L2 episode (bag 45315499) to 10% of their time. Before B1/B2 the readback cost about 1,993 s (qc 247, verify-commit 421, check-export 1,325): each of its three commands recomputed the QC from the sealed files, `check-export` three times.

## Where the repeated recomputation comes from

| Caller | Recomputes of the QC |
| --- | --- |
| offline processor, fresh-process QC subprocess | 1 (writes the report and the memo) |
| Coordinator and ResultStore at seal and commit | 0 (they trust the memo, CP-3456) |
| `act_first_episode run`, `_verified_run_completion` -> `verify_coordinator_commit` | 1 (the in-run commit proof) |
| readback `qc --run` | 1 |
| readback `verify-commit --run` | 1 |
| readback `check-export --run` | 3: `verify_coordinator_commit`, `resolve_committed_episodes`, `export_dataset` each verify the commit |

Seven recomputations for one episode. After B1 (`qc_session.py`, CP-3469) a recomputation costs 26 s instead of 250 s; this change takes the readback from five of them to one.

## What independence means

The rule (CP-3469 (d)): before anything counts as committed or exportable, a process that did not write the episode and does not trust the memo has recomputed the whole QC from the sealed originals, with the original scope and frozen inputs, and its verdict equals the stored report.

- **The run command is not that process.** It builds `ActCollectionResultVerifier(trust_fresh_qc_memo=True)` (`mujoco_parallel_batch.py`) and fills `qc_memo._CACHE`; its commit proof (`commit-proof.json`) is the proof of a process that trusts the memo. The review required that the run write **only** that file: no readback receipt, no export check (test: `test_the_run_command_writes_the_commit_proof_only`).
- **`act_first_episode readback --run` is always its own process**, and its receipt is what acceptance reads. Minimum recomputations of the QC for one episode: three (the processor, the in-run proof, the readback).
- Before the change the property was met by each readback command separately, with redundant repetition. After it, by one recomputation per readback process, shared by the stages of that process.

## The design as implemented

1. **Entry points.** `qc`, `verify-commit`, `check-export` and `readback` are the only places that open a session for sharing (`_readback_entry`): the owner of the session is `readback:<command>` (`qc_session.ENTRY_OWNERS`). Nothing in `bundle.py`, training or the libraries opens one.
2. **Only the QC result is shared** (`episode_qc._recompute_for_readback`). The stored `qc-report.json`, the journal, the index, the receipt, the scope document and every eligibility decision (`mode`, result status, `act_data_qc`, `export_eligible`) are read and decided afresh on every call: `bundle._verify_collection_for_export` runs in full for each export path; a test checks that non-PASS formal episodes are still refused with a session open. "Cached proofs grant no eligibility" stays the rule (docstring updated): a recomputation is a computation, not a proof.
3. **The reuse key is a forced full-content fingerprint**, not stat data and not report-derived digests. `qc_memo.fingerprint(..., use_cache=False)` hashes every byte of the episode tree, the scope, the frozen inputs, the Teacher manifest and (since phase C) the gate document, without the memo's stat cache; the key adds the QC code digest and the call arguments. It is computed **before** the recomputation, **after** it, and at **every lookup**; any difference raises `READBACK_INPUT_CHANGED` and nothing is kept. A stat key (size, inode, mtime) would serve a stale result after an in-place same-size rewrite with the mtime restored (test: `test_an_in_place_rewrite_of_the_same_size_with_the_mtime_restored_is_not_a_hit`). Report-derived digests would be circular: the report is what is being checked.
4. **B1's verifier memos** (`qc_session.py`, stat-keyed, from CP-3469) also live in the entry session, so the stages share the seal and audit verifications. They are guarded at the stage boundaries: `readback` hashes the full-content fingerprint before and after every stage and fails closed on a difference. (Between two such checks a rewrite that is reverted before the next check is not detectable; the same is true of a single recomputation, which reads its files at different times.)
5. **Readback guard** (`qc_memo.readback_guard`). The entry points refuse to start if the process holds memo state (a filled `qc_memo._CACHE`) or ever built a memo-trusting store or verifier; inside, building one, reading or writing a memo, or a memo-style fingerprint raises `ReadbackMemoForbidden` (a `RuntimeError`, because the gates catch `ValueError` as "the memo does not cover this"). `qc-verification-memo.json` is never opened (test: `os.open` spy with a matching memo present).
6. **Export guard.** `bundle.resolve_committed_episodes` and `export_dataset` refuse (`QC_SESSION_IN_EXPORT_PATH`) when a session whose owner is not a readback entry point is active.
7. **Check-export** shares the single recomputation between its three verifications: 3 -> 1 at report level (test: `test_check_export_recomputes_the_qc_once_not_three_times`).

## `readback --run <run> --output-dir <dir>`

Stages in order, in one process: `qc` -> `qc.json`, `verify-commit` -> `verify-commit.json`, `check-export` -> `check-export.json`, then `readback-receipt.json` (exclusive, durable). The three outputs are byte-identical to the standalone commands' (test per failure case: all pass, missing commit). An existing output directory is refused.

Stage behaviour:

- A QC FAIL with a valid commit: `verify-commit` still runs (and `check-export` too). The receipt is complete and records `qc_verdict`.
- A run that is not a diagnostic (formal): `check-export` is `NOT_APPLICABLE` with reason `DIAGNOSTIC_EXPORT_CHECK_MODE_REQUIRED` (the refusal check exists for diagnostic runs; the standalone command still refuses with 3). Recorded in the receipt, no file written.
- A stage that cannot complete does not stop the others (parity with running the commands one by one).

Exit codes (stage codes are today's):

| Command | 0 | 3 | 4 | other |
| --- | --- | --- | --- | --- |
| `qc --run` | PASS | FAIL verdict (report written) | error | `--episode`: 1 FAIL, 2 error |
| `verify-commit` | proof written | refused or error | | |
| `check-export` | both boundaries refused the diagnostic, proof written | refused, not a diagnostic, or error | | |
| any entry point | | | refused by the readback guard | |
| `readback` | every stage 0 (or `NOT_APPLICABLE`) and the receipt PASS | the first non-zero stage code in the order qc, verify-commit, check-export | the stages passed but the receipt's own checks did not (or the guard, or the directory) | |

The receipt (`ACT_READBACK_RECEIPT` v1) records: the three digests (`recomputed` = sha of `qc.json`, `stored` = sha of the run's `qc-report.json`, `commit_proof` = `qc_report_sha256` of the commit proof) and whether they agree; the content fingerprint; the QC code digest; the journal's terminal frame digest; the pid; `qc_recomputations` (counted at report level, must be 1 when the stages completed) and the reuse hits; each stage's status, rc and output digest. Its status is FAIL for a stage that did not complete, a recomputation count other than 1, or digests that disagree; a QC FAIL verdict does not fail it.

## Tooling (new revisions only)

- `run-qualified-live-20261009-r10.zsh`: the `run` stage runs the run command, then starts an independent `readback` process of its own (`readback` stage, also callable alone) and judges it by its receipt: kind and schema, `pid` equal to the readback process the wrapper started (a receipt the run wrote could never match), `run` equal to the live root, PASS, `qc_recomputations` 1, the digests agreeing, `verify-commit` rc 0, `check-export` PASS or NOT_APPLICABLE, fingerprint and code digest present. A run that exits 0 and whose readback does not pass ends with rc 95. It reads the readback only when the run committed (rc 0 or 3 and `commit-proof.json` present).
- `tooling/live-r7.zsh` calls r10 and reports `READBACK_RC`. The older wrappers are not edited. The installed `act_first_episode` of the freeze must be a build that has the `readback` subcommand: a new freeze.

## Measurements (L2 episode, quiet machine, sequential)

Measured on the L2 live run with the pre-phase-C source plus this change (`phaseb/composite-b3`; phase C makes the run's rule-v3 report unreadable, and the run cannot be redone without a live stack):

| Stage | B1/B2 only | With this change |
| --- | --- | --- |
| `qc` | 26 s | 27 s |
| `verify-commit` (= the in-run proof's work) | 27 s | 27 s |
| `check-export` | 77 s | 28 s |
| `readback` (all three, one receipt) | 130 s as three commands | 31 s |
| Processing + proof + readback | 347 s | 248 s (190 + 27 + 31) = 8.4% of 2,951 s |

The first item of the review: measure the outer-session-only option before adding the report-level cache. One session with B1's memos and no reuse of the QC result also runs the three stages in 27 s (five recomputations, each cheap because the verifiers are shared). **The target is met without the report-level cache**; the cache costs about 4 s of fingerprinting (full-content hashes at every boundary, 0.4 s each) and buys the property the review asked for: exactly one recomputation at report level, a stale-proof guard that does not depend on stat data, and a receipt that says so. It is implemented because the verdict lists it; dropping it saves the 4 s and the receipt's recomputation count, and nothing else in this design depends on it.

## Tests

`test_b3_single_readback.py`, 31 tests (RED against c039b78be, where the API does not exist): the stale stat (in-place rewrite, mtime restored, same inode), change during compute, change between lookups for each input, failures not remembered, the key including the code digest, the fingerprint without the cache; the memo leak (filled cache, a trusting gate built before or inside the guard, a flipped trust flag, memo read/write/fingerprint, an `os.open` spy with a matching memo present); the export guard for sessions opened elsewhere and for an entry owner; formal export decisions with a session open; byte and exit-code parity of `readback` with the standalone commands (all passing, missing commit); `check-export` 3 -> 1; the receipt contents; `NOT_APPLICABLE` for a non-diagnostic; the receipt failing on two recomputations; refusal of every entry point with a leaked cache or a trusting gate; the run writing the commit proof only. `conftest.py` resets the memo state per test.

## Questions closed by the review

1. One recomputation per readback process, shared by the stages: accepted, with the changes above.
2. The run writes the commit proof only; the independent readback is a separate process the wrapper starts.
3. The key is a forced full-content fingerprint, not a stat key.
