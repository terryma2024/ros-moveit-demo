# SO-101 ACT Task 8 Live and Formal Collection Design Review Ledger

## Task identity

- Date: 2026-09-24
- Scope: Freeze the MuJoCo-only Task 8 live, contact calibration, exact-W8 qualification, and formal 50/10/10 collection design before revising the implementation plan.
- Starting HEAD: `fd10ed0226f80870a3a8e88bf6a663f731c19378`
- Branch: `main`
- Registered evidence root: `/tmp/so101-debug-act-task8-design-20260924`
- Writer: current GPT-6 Sol / High task
- Independent reviewer: GPT-6 Astra / High, read-only

## Files under review

- `docs/superpowers/specs/2026-09-24-so101-act-task8-live-formal-collection-design.md`
- `docs/superpowers/specs/2026-09-10-so101-act-head-wrist-rgb-design.md`
- `docs/superpowers/plans/2026-09-11-so101-act-head-wrist-rgb-implementation.md` (execution-hold notice only before written-spec approval)

## Evidence boundary

This task changes documentation only. It does not run MuJoCo, ROS 2, MoveIt, contact calibration, Task 8 live, W8 qualification, recording, collection, training, or policy deployment. Static checks and document review cannot prove runtime behavior.

## Confirmed design decisions

- MuJoCo is the only supported simulator. There is no Gazebo fallback.
- Campaign resource binding is validated at startup only. Internal components receive business payload and audit identity, not resource-verification duties.
- Contact calibration uses deterministic offline MuJoCo generation plus isolated ROS/MuJoCo live evaluation. A disabled proposal becomes active only after exact-hash user approval.
- Web and headless CLI share one typed WorkerPort/child IPC path. Each `(campaign_id, worker_id, generation)` has one isolated ROS execution child; exact W8 therefore has eight children.
- W2 is followed directly by an independent 40-scene exact-W8 qualification. W4 and W6 are skipped.
- Any W8 resource bottleneck stops execution for human review; there is no automatic downshift.
- Formal collection runs exact W8, does not retry business failures, and returns `QUOTA_UNSATISFIED` when frozen candidates cannot fill 50/10/10.

## Review log

| Round | Reviewer | Input hash | Result | Evidence |
| --- | --- | --- | --- | --- |
| 1 | GPT-6 Astra / High | Commit `64a27064`; new design `2a435fa5ccd9309e3df8a4ec182b8f9d49f43125fdcdcc1df8f88b02f7239b32`; overall design `dc6c879195aee4d791e473bd2738554ba97041aca5be7e2920583643d0189483`; plan `aba2f4f2724d1efbc482552268945e405230fe5cb340bd8b7ad0991fba1b1000` | Changes requested: 2 P1, 2 P2 | Release epoch was incorrectly treated as episode-invalid; W8 qualification lacked executable pass criteria; ROS child uniqueness scope conflicted with W8; proposal hash and `POLICY_FINGERPRINT` approval objects were ambiguous. |
| 2 | GPT-6 Astra / High | New design `ebdaf3e031fb95bdee26a637cfd75059bd4e03940328fda2d09f603f62212e34` | Changes requested: 1 P1, 1 P3 | Round 1 findings were closed. Business failures were incorrectly excluded from durable result commit, and the ledger summary retained the old global ROS-child wording. |
| 3 | GPT-6 Astra / High | New design `1f6aca59a44eee1b06e22cb7f5d468968b7ea529de5346ec9077cf3b72c45e0c`; ledger `2a7c20f242c3b544d4ceaf087389429a9196b6c7636a7daa78170780540d842e` | PASS: no P0/P1/P2/P3 | PASSED/FAILED now share the durable commit path; only PASSED+QC enters training. ROS child uniqueness is scoped per campaign/Worker/generation. All earlier findings remain closed. |
| 4 | GPT-6 Astra / High | New design `cacd061f1c0728e68092c3f658755e20e22c7c509ccef382ed4510f5926137e0`; ledger before this row `5168c56a50131cd7fab9daa4ac9f39655f9597d12aa6dd66fb4399ec9e5b599e` | PASS: final hash-lock, no P0/P1/P2/P3 | The design changed after Round 3 only to record review status. Normalized readback reproduced the Round 3 PASS hashes exactly. |

## Evidence disposition

- Retained: the reviewed specification, supersession notices, and this ledger.
- Archived: none.
- Deletion candidates: `/tmp/so101-debug-act-task8-design-20260924` after readback; do not delete without explicit authorization.
- Deletion performed: none.
