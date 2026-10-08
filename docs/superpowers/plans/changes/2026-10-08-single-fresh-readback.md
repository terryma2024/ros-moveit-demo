# One fresh-process readback instead of five recomputations

Date: 2026-10-08

Status: **DRAFT for independent review. Not implemented.** B1 (QC speed) and B2 (replay speed) proceed without this change and do not depend on it.

Trigger: Phase B of the plan to cut the three slow steps on the L2 episode (bag 45315499) to 10% of their time. Measured before the change (about 2,927 s together): offline processing 526 s (scan 13, replay 264, fresh QC 249), the in-run commit proof about 428 s, and the manual readback about 1,973 s (qc 260, verify-commit 423, check-export about 1,290).

## Where the repeated recomputation comes from

A full QC recompute (`recompute_native_qc`; about 250 s before B1, 26 s after it) is not the cost of "the readback" once; it is paid once per caller:

| Caller | Recomputes |
| --- | --- |
| offline processor, fresh-process QC subprocess | 1 (writes the report and the memo) |
| Coordinator and ResultStore at seal and commit | 0 (they trust the memo, CP-3456) |
| `act_first_episode run`, `_verified_run_completion` -> `verify_coordinator_commit` | 1 (the in-run commit proof) |
| readback `qc --run` | 1 |
| readback `verify-commit --run` | 1 |
| readback `check-export --run` | 3: once inside `verify_coordinator_commit`, once in `resolve_committed_episodes`, once in `export_dataset` |

That is seven recomputations for one episode (processor 1, run proof 1, qc 1, verify-commit 1, check-export 3). Every one of them runs the same deterministic code on the same sealed files in a fresh process; none of them can disagree with another except through a nondeterministic defect or a change of the files.

## What independence means

The property the amendment asks for (section 4.4, verification rule d of CP-3468) is: **before anything counts as committed or exportable, a process that did not write the episode and does not trust the memo has recomputed the whole QC from the sealed originals, with the original scope and frozen inputs, and its verdict equals the stored report.**

Not required, and not what makes the check independent: that the same computation is repeated several times in the same kind of process.

Before the change the property is met by the in-run commit proof (`run`) and by each readback command separately, with redundant repetitions (seven recomputations in all). After the change it is met by exactly one recompute per readback process:

- The recompute runs in the readback process (a fresh interpreter started by the operator, the run command or the live wrapper). That process never reads the memo: `trust_fresh_qc_memo` stays false there, and the memo file is not opened by the readback code path.
- Everything downstream in that process (commit proof, both export-refusal checks) is derived from that one result, but each one still re-reads and re-verifies its own inputs: the journal hash chain, the index, the phase leases, the receipt binding, the stored report against the recomputed one, the export boundaries. Only the QC recomputation is shared.
- The shared result is keyed on the files it was computed from (episode tree, scope, frozen inputs, with name, size, inode and mtime of every file). If any of those changes between two uses in the same process, the result is not reused and is recomputed. A reuse never extends beyond the process and never beyond the context manager that created it.
- The seal and the Coordinator keep trusting the memo exactly as now (no change to `trust_fresh_qc_memo` anywhere).

Repeating the recomputation a second and third time inside check-export adds no information: the code is deterministic and the files are the same. It would detect a file change in the middle of a readback, which the signature check now detects directly and more cheaply.

## Proposal

1. `act/qc_session.py` (new): a context manager `qc_session()` that holds a per-process cache. `recompute_native_qc` (current schema only; the legacy v2 reader is untouched) looks up `(canonical paths, tree signature)` and returns a deep copy of the report on a hit. The session counts computations and hits. Outside a session nothing is cached, so every existing caller and test behaves as before.
2. `act_first_episode readback --run <run> --output-dir <dir>` (new subcommand): inside one `qc_session()` it runs, in this order, the QC recompute (writes `qc.json`), `verify_coordinator_commit` (writes `verify-commit.json`), the two export-refusal checks (writes `check-export.json`), and the coordinator cleanup check. It writes one combined receipt, `readback-receipt.json`, that names the three outputs by sha256 and states `qc_recomputations: 1` and the number of session hits. Exit codes follow the three existing commands (first failure wins; a failing stage stops the rest).
3. `_verified_run_completion` (the commit proof of the `run` command) enters a `qc_session()` too, so the proof it writes to `commit-proof.json` is one recompute. When the run is a diagnostic run (collection on), it also performs the export-refusal checks in the same session and writes the readback receipt next to `commit-proof.json`, so the live wrapper needs no separate readback pass.
4. The three existing subcommands (`qc`, `verify-commit`, `check-export`) stay, each now wrapped in its own session: `check-export` goes from three recomputations to one, and `verify-commit` stays at one. No output format changes; the three existing outputs are byte-identical to today's for the same episode (to be tested).
5. Tooling, new revisions only: `run-qualified-live-20261009-r10.zsh` (stage `run` reads the receipt the run command wrote and fails when `qc_recomputations` is not 1 or the receipt is missing; stage `readback` calls `readback --run` if the receipt is absent) and `tooling/live-r7.zsh` (calls r10). The older wrappers are not edited.

Measured basis (B1 and B2 in place, quiet machine): processing 190 s, `qc` 26 s, `verify-commit` 27 s, `check-export` 77 s (three recomputations). Expected time on the L2 episode with this change, from those numbers: the in-run commit proof and the readback each cost one QC plus a few seconds, so the recomputations go from seven to two when the run command writes the readback receipt (processor, run), and to three when an operator also runs `readback` afterwards.

## What is deliberately not changed

- `verify_coordinator_commit`, `verify_coordinator_cleanup`, the verifier, the ResultStore and the memo protocol keep their logic and their error codes.
- The QC rules and the QC report bytes do not change here (B1 is held to byte-identical reports).
- The offline processor still runs its own fresh-process QC (the memo producer). It is a different process with a different purpose (it decides VALID versus INVALID for the attempt) and is not merged with the readback.

## Test plan (RED first)

- RED: a test with a counting wrapper on the QC compute shows `check-export` calls it three times today; GREEN: once.
- Session scope: a call outside a session recomputes every time; a second call inside one with the same files hits; after touching one file of the episode tree it recomputes; a nested session does not leak into the outer one; an exception inside leaves no cache behind.
- The cached report is a copy: mutating a returned report does not change the next one.
- `readback`: the three outputs and the receipt exist; `qc_recomputations == 1`; the outputs equal the standalone commands' outputs; a corrupted stored QC report, a missing commit, and a diagnostic-mode violation each fail with the same reason as the standalone command.
- The run command's proof: a fake run context counts one recompute for `_verified_run_completion`; exit-code mapping unchanged (existing tests).
- Independence: with the memo present and deliberately wrong, the readback still fails on the recomputed verdict (the memo is never read), and a tampered episode file is caught by the recompute.
- Acceptance on the real episodes: the receipt's `qc_recomputations` is 1 on L2 45315499 and on 147cb073, and the standalone commands' outputs are byte-identical to their previous bytes.

## Questions for the reviewer

1. Is "one recompute per readback process, shared by commit proof and export checks" enough for the independence rule, given that each downstream check re-verifies its own inputs?
2. Should the run command also write the full readback receipt, or only the commit proof, leaving the export-refusal checks to the operator's `readback`?
3. Is the stat-based file signature acceptable for the reuse key, or should the key be the three content digests the QC report already binds (seal, audit manifest, scope) plus the frozen inputs digest?
