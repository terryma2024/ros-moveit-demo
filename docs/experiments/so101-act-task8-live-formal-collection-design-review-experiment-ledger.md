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
- Web and headless CLI share one typed WorkerPort/child IPC path and one unique ROS child.
- W2 is followed directly by an independent 40-scene exact-W8 qualification. W4 and W6 are skipped.
- Any W8 resource bottleneck stops execution for human review; there is no automatic downshift.
- Formal collection runs exact W8, does not retry business failures, and returns `QUOTA_UNSATISFIED` when frozen candidates cannot fill 50/10/10.

## Review log

| Round | Reviewer | Input hash | Result | Evidence |
| --- | --- | --- | --- | --- |
| 1 | Pending Astra high | Pending | Pending | Pending |

## Evidence disposition

- Retained: the reviewed specification, supersession notices, and this ledger.
- Archived: none.
- Deletion candidates: `/tmp/so101-debug-act-task8-design-20260924` after readback; do not delete without explicit authorization.
- Deletion performed: none.
