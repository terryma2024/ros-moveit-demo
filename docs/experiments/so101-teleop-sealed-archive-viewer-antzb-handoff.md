# SO-101 sealed archive viewer: antzb handoff

This is a handoff record, not a completion report. The user approved the implementation plan, explicitly required Codex to implement it itself without dst, then requested continuing on antzb inside Herdr.

## Resume here

1. You run on **antzb**, hostname `AI-STATION-001`, user `lenovo`, in `/data/work/ws_moveit/.worktrees/teleop-archive-viewer`. Do not confuse it with the source host `ai-station` (`matianyi`, `/home/matianyi/Projects/ros-moveit-demo`). No self-SSH.
2. Read this checkout's AGENTS.md, `.agents/skills/so101-dev/SKILL.md`, the task ledger and the complete approved plan `docs/superpowers/plans/2026-10-17-so101-teleop-sealed-archive-viewer-implementation.md`, plus both linked specs. Host-specific source paths in the plan must be adapted to this new worktree; do not import or modify any collecting worktree.
3. Keep branch `codex/teleop-archive-viewer`. Only allowed push is `git push origin codex/teleop-archive-viewer`; no main/ACT branch edits, no gh, no force-push. Preserve existing destination worktree changes and running tasks.
4. Continue from Task 2 review RED. Task 1 is committed; Task 2 has useful initial code and tests, but is deliberately WIP. Fix malformed campaign scene objects to a structured document 422, rerun the 8 package tests, then all archive tests and CTest registration. Review package structure validation, schema-2 fallback, identity fields, bound scene SHA, duplicate scenes and cache safety against the approved plan; initial passing tests do not mean these are all finished.
5. Complete Tasks 3–6 using test-first changes, one commit per finished task, inline self review, no dst/subagent reviewer. Do not restart the already completed Task 1 or declare this WIP feature complete. Preserve the existing failing test and its RED evidence before fixing it.

## State and evidence

- Base remote ACT tip at task creation: `007cb1e3c1830f9348052fa2cc4f39e4bd0396a7`.
- Docs/plan commit `250141cd9`; Task 1 commit `1c611eb09`; the transfer commit includes this record and the incomplete Task 2 files.
- Canonical ledger: `docs/experiments/so101-teleop-sealed-archive-viewer-experiment-ledger.md`.
- Logical task evidence root on each host: `/data/work/so101-evidence/teleop-archive-viewer/20261017T062429Z-007cb1e3`. Source logs are retained; destination `source-ai-station-evidence` holds copied logs/JUnit/runner metadata, not a copied Python venv or sealed data. Register destination provenance before testing. Keep source and destination runs labelled with hostname.
- Source runner `run.py` has hardcoded source paths: read for reference, adapt before using on antzb. Build a task-private environment; resolve exact Python/Bun executables, no shared venv edits. Every pytest/colcon run needs new NVMe scratch, TMPDIR/TMP/TEMP proof using the actual Python, elapsed time/rc/JUnit, and 8 xdist workers for full ordinary Teleop scope. Retain scratch as deletion candidates; never delete evidence without user permission. No benchmark or uncrustify reformat.
- Initial full baseline was an environment failure (ament resources absent, IPC names too long), NOT code RED. Resource-only ament prefix was staged from source config/assets/launch for tests, not a runtime install. Two fixed-helper tests reject symlinked IPC roots (`CONTROL_SOCKET_OUTSIDE_BATCH_ROOT`); solve their isolation path correctly. Source full run totals and exact failure names are in ledger and exported JUnit.
- Frontend baseline: 56 files / 318 tests passed, typecheck rc=0. Current new feature frontend/schema is still absent.
- Task 2 RED→initial GREEN: `red-2-bd2ed410` → `green-2-99d969c4` (18 archive/registration tests passed). Latest review RED: `red-2-review-1b1f42c8`, 7 passed, 1 failed: `test_malformed_scene_object_returns_document_error` (None row causes TypeError in package.py).

## Hard boundaries and remaining acceptance

Viewer strictly read-only: never write/create/rename/delete/chmod any sealed root, seal manifest or root containing SEALED.json. Do not execute/import sealed source or open sealed SQLite. Client passes issued ids, never paths; reject package escapes and external symlinks. Unit tests only use synthetic packages.

The real registry `/data/work/so101-evidence/act-data/20260924-fbc25063-resume` was present on the source host and was not found on antzb during initial probing. Do not silently copy 55 GB or fabricate live acceptance. Confirm its accessibility separately; coordinate the final installed-service/browser and byte-level checks on the host actually holding the evidence using authorized existing SSH access, or report this acceptance boundary explicitly if unavailable. Implementation/synthetic gates can proceed on antzb without ROS/Docker.

Real acceptance still required: seven sealed roots; EXP-620 70 planned / 69 committed (49 train, 10 validation, 10 offline_test), frm-007 FAULT, round 1 recovers 5; frm-000 905 rows with head/wrist and synchronized inline SVG; full byte hashes plus complete directory listing/mtime unchanged afterwards. Installed server must come from the new feature worktree, independent port/state, no collection disruption. Manifest excludes SEALED.json, so hash that separately and detect new files. Do not mix collection_committed with episode seal.committed (frm-000 has false in the latter).

## Receipt

The dispatch prompt provides a random receipt id and path. As your first task command, write that exact id to the given receipt path, then read these documents and record `pwd`, branch, HEAD and hostname in a separate task-owned receipt/provenance file. The coordinator verifies receipt plus actual first probe before calling handoff successful. Continue autonomously through the approved plan after that; do not ask the user to approve the same plan again.
