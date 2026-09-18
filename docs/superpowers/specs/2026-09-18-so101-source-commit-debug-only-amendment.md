# Scope amendment: source commit is DEBUG metadata only (2026-09-18)

**Status:** user-authorized narrow amendment to the frozen design and plan. It changes one
rule only (source-commit runtime admission) and preserves every other resource,
qualification, authority, control, lease, session, reset and cleanup rule unchanged.

Dispatch: `41326eaf-39da-45d1-a9e8-0352d304dff5` (followup
`debug-only-provenance-41326eaf-39da-45d1-a9e8-0352d304dff5`).

## Preserved sealed bytes

No previously sealed document is rewritten, moved or re-hashed by this amendment:

| Document | SHA256 |
| --- | --- |
| Design `docs/superpowers/specs/2026-09-18-so101-parallel-unbounded-queue-resource-budget-design.md` | `5e085f98e9926591fbefd3d6e16c16b33bfc9956df9221c46f383b310553657b` |
| Plan `docs/superpowers/plans/2026-09-18-so101-parallel-unbounded-queue-resource-budget-implementation.md` | `cd1b606fd8a40d7bb6e576f6f59a6ef5abcb45a8bee7e2a669c7b7a40bfc8789` |
| Execution review `docs/superpowers/reviews/2026-09-18-so101-parallel-unbounded-queue-resource-budget-execution-review.md` | `bbedfc5dc999086c34506a2252765b661291972583c1508d390b46d6eba1c603` |
| Repair re-review (this unit's input) | `84303c2a939927059e0e2ca5202344e06a816afbb4d906fff8bffa2b99714ced` |

This file is a new, dated addendum. It supersedes only the clauses listed below.

## User requirement

Source commit must not be a runtime validation rule: a deployment may be a pure copied
install with no Git checkout. Source commit and installed file SHA256 are **observations**
for debugging, never runtime authority.

## Superseded clauses

1. **Design §"execution provenance" clauses** that make a resolved Git commit a condition
   of execution: `resolve_installed_execution_identity()` requiring `git rev-parse HEAD`,
   `verify_execution_provenance()` rejecting a non-40-hex or mismatched
   `--source-commit`, and the "source tree must be clean" condition. Superseded by a
   provenance contract that verifies the installed **location** and byte artifacts only.
2. **Plan Task 12/Task 15 wording** that treats the runtime source commit as verified
   runtime source (`--source-commit` as a required argument, `EXECUTION_SOURCE_COMMIT_*`
   refusal codes). Superseded: the option remains as optional DEBUG metadata.
3. **Any qualification/identity consumer** whose only rejection reason was a source
   commit: the parallel batch CLI provenance verifier
   (`PROVENANCE_SOURCE_COMMIT`, `PROVENANCE_SOURCE_DIRTY`,
   `PROVENANCE_EXTERNAL_SOURCE_COMMIT`), the teleop runtime layout
   (`SO101_VALIDATION_SOURCE_IDENTITY`, `SO101_VALIDATION_SOURCE_COMMIT_MISMATCH`), the
   teleop execution-owner record (`SOURCE_COMMIT`), and the operator-recovery request
   (`RECOVERY_SOURCE_COMMIT_INVALID`).

**Not superseded, still required:** installed prefix/location semantics and equality,
content inventories and byte hashes, the resource execution identity
(R/L/S/E/I and the exact-N budget chain), budget/qualification/authority/promotion/
deployment/control/lease/session/reset/cleanup gates, the measurement authorization
chain, and every plan/design rule unrelated to source commits.

## Amended contract

* `ExecutionProvenance.source_commit` is `str | None`, with
  `source_commit_source ∈ {OBSERVED, DECLARED, UNKNOWN}`; persisted JSON carries both.
* Runtime resolves no Git state on any execution path. `--source-commit`, the teleop
  `SO101_VALIDATION_SOURCE_COMMIT` and similar inputs are recorded as DEBUG metadata;
  missing, malformed, mismatched or foreign values never refuse, and no zero/default
  commit is fabricated.
* The **DEBUG-only install manifest** (`share/so101_demo_py/debug-provenance-manifest.json`,
  schema version 1, kind `DEBUG_INSTALL_PROVENANCE`, authority
  `DEBUG_ONLY_NOT_RUNTIME_AUTHORITY`) is emitted by the final installation step. It
  records install-relative paths, actual file-byte SHA-256 values, nullable
  `source_commit`/`source_dirty`, a documented coverage policy and symlink semantics. It
  contains no timestamp, no self-hash, no absolute prefix, so identical bytes produce
  identical manifest bytes and relocation keeps it valid.
* No runtime path reads, hashes or verifies the manifest. Only the explicitly requested
  `so101_debug_provenance` reader inspects it and prints diagnostics.

## Out of scope (reported, not weakened)

Model/training/benchmark artifact identities that declare a commit inside their own
artifact contract without running Git on a deployment path are unchanged:
`adapters/perception/model_bundle.py`, `training/sam_decoder_runtime.py` (training entry),
`training/frozen_candidate_evaluation.py`, `training/saved_checkpoint_revalidation.py`,
`training/grounded_sam_proposal_receipts.py`, `perception_benchmark/*`. These are
declared content identities of produced artifacts, not deployment runtime admission.
