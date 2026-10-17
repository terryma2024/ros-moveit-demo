# SO-101 Teleop sealed archive viewer task ledger

```yaml
task_id: so101-teleop-sealed-archive-viewer-20261017
goal: Implement a strictly read-only archive browser after plan approval
success_contract: ordinary Teleop pytest, Vitest, types; seven sealed roots; EXP-620 acceptance; unchanged sealed bytes
worktree: /data/work/ws_moveit/.worktrees/teleop-archive-viewer
source_worktree: /home/matianyi/Projects/ros-moveit-demo/.worktrees/teleop-archive-viewer
branch: codex/teleop-archive-viewer
base_commit: 007cb1e3c1830f9348052fa2cc4f39e4bd0396a7
current_commit: 0eec8606f945c951294bb6eed4505a0c7774933b (latest implementation; handoff docs committed separately)
evidence_root: /data/work/so101-evidence/teleop-archive-viewer/20261017T062429Z-007cb1e3
confirmed_conclusions:
  - OBSERVED: remote tip matched ls-remote when the isolated worktree was created
  - OBSERVED: fixture-compatible scene list exists inside collection inputs/frozen/scene_manifest/scenes.json
  - OBSERVED: frm-000 episode seal committed=false, while collection-index lists it as committed
  - OBSERVED: seal manifest excludes SEALED.json itself
  - OBSERVED: system Python lacks xdist, FastAPI, httpx and uvicorn
  - OBSERVED: skills default test Python path does not exist on this host
disproven_routes:
  - existing page routing uses paths, not page query parameters
open_hypotheses:
  - real discovery and cold package latency require measurement during approved implementation
latest_checkpoint: CP-005-USER-REQUESTED-SUCCESSOR-HANDOFF
next_experiment: Task-3-episode-and-file-RED on antzb
```

## CP-001-PLAN-ONLY

- Read-only source and real metadata inspection; no tests or services started.
- Copied the two uncommitted specifications byte-for-byte into this worktree; SHA256 in evidence root/spec-provenance.json.
- Existing main checkout submodule metadata is broken; new worktree submodule is uninitialized. Neither was repaired or initialized.
- Existing Claude gate build imports the protected collection worktree. Preserve every existing process; no default tmux server/codex-cua session was present.
- ROS graph query omitted: no robot runtime or ROS graph change is part of this file-only plan. Process inventory shows active gate compiler work.
- Local upstream cleared from the new branch to avoid accidentally targeting the collection branch. Allowed push: git push origin codex/teleop-archive-viewer.
- Current changes: the two supplied specs, this ledger, and the implementation plan when written. No implementation changes.
- Owned processes: NONE. Runtime install/executable, ROS_DOMAIN_ID and GZ_PARTITION: N/A (plan-only).
- Retained: this evidence root and spec provenance. Archived: NONE. Deletion candidates: NONE yet; no scratch test run has begun.
- Next action: user review of docs/superpowers/plans/2026-10-17-so101-teleop-sealed-archive-viewer-implementation.md.

## CP-002-IMPLEMENTATION-AUTHORIZED

- User explicitly approved the plan and requested implementation in this session, without dst.
- Direct on ai-station; clean isolated worktree at 250141cd9. Existing gate ROS processes belong to Claude and remain untouched. ROS/Gazebo mutation is outside scope.
- Private venv at evidence_root/venv, Python 3.12; dependencies and versions in environment-install.log. Temp proof and runner in evidence root; no shared environment changes.
- Ruling: use this persistent ledger and evidence-root run records instead of skill-created .superpowers scratch; the repository requires a single registered evidence root and prohibits deleting evidence. All review remains inline per AGENTS.md.
- Pre-flight Task 1→2: ArchiveStore/root ids supply PackageSnapshot; same owner/cache, no conflict.
- Pre-flight Task 2→3→4: package snapshot supplies manifest and scene map; episode/verify retain snapshot references across eviction, no conflict.
- Pre-flight Task 3/4→5→6: generated DTOs supply typed client then browser/player; schema export must happen before client compilation, no conflict.
- Next: baseline full pytest xdist8 and frontend gates, then Task 1 RED. No owned service processes.

## BASELINE-001 (environment gate; not product RED)

- Full pytest: baseline-bad35529, 1390 passed / 44 skipped / 24 failed / 18 setup errors, rc=1, 94.80 s. Source implementation unchanged. Failures are missing so101_demo_py ament resources and Unix socket path length under long TMPDIR; complete names/messages retained in JUnit.
- Frontend baseline: 56 files, 318 tests passed; typecheck rc=0.
- Ruling: stage a resource-only ament prefix from this worktree config for Python tests (not a runtime install), and use evidence_root/i as short private IPC base with existing per-worker isolation. No source regression inferred from this invalid environment gate. Runtime acceptance still requires a real new Teleop install.

- Ruling: the registered root itself is too long for worker/bridge AF_UNIX names. /tmp/sav-20261017-062429 is a symlink alias to evidence_root/i, not a separate storage root; all socket data remain under the same NVMe root. Retain the alias until task-owned processes finish.

## Task 1 checkpoint

- Implemented explicit roots, seal discovery with pruning, opaque ids, disabled middleware and package-contained path resolution. No robot dependency added.
- RED red-1-089d5eaa: missing ARCHIVES_DISABLED body, testcase assertion failed as intended (rc=1).
- GREEN green-1-review-bbb3ddfc: archive tests, CTest registration, unified API regressions, 23 passed (rc=0, 4.48 s). Inline review checked fallback order, symlink pruning and id lookup.
- Whole-scope environment checks remain recorded separately; missing assets/launch resources in test-only prefix now corrected. The initial diagnostic retry used the long IPC path before the short alias fix; final complete scope will run with the corrected runner. No failures suppressed or product gate claimed.
- Task 2 tests written after task 1 targeted gate: red-2-bd2ed410, 5 intended HTTP assertion failures. They are not included in the Task 1 commit.
- Retain all evidence; each scratch result.json labels its tree a deletion candidate after readback. No deletion authorized.

## CP-003-ANTZB-HANDOFF

- User redirected work: push the current task, pull on antzb, launch a Codex successor inside antzb Herdr. Source-side implementation is frozen now. This is a WIP transfer, not a completion claim.
- Task 1 committed: 1c611eb09. Targeted gate green-1-review-bbb3ddfc: 23 passed. Full task-1-full-8fffec4e: 1430 passed, 44 skipped, 3 failed, 9 setup errors, rc=1, 93.37 s; all details retained.
- Task 2 initial RED red-2-bd2ed410: five real HTTP assertion failures; initial implementation GREEN green-2-99d969c4: archive scope plus CTest registration 18 passed, rc=0, 3.48 s.
- Task 2 review tests then RED red-2-review-1b1f42c8: 7 passed, 1 failed (test_malformed_scene_object_returns_document_error); PackageSnapshot._load_collection indexes None in campaign scenes, leaking TypeError instead of 422. This is intentionally preserved for the successor to fix before Task 2 completion. No Task 2 completion claimed.
- Task 1 integration test test_web_entry_point_has_no_helper_or_driver_flags now allows the new archive_root option; this uncommitted-at-interruption correction is included in the handoff WIP commit.
- Remaining environment issues: resource-only prefix initially lacked assets/launch; those symlinks are now present but not yet revalidated. Two fixed-helper tests failed CONTROL_SOCKET_OUTSIDE_BATCH_ROOT because the IPC alias resolves outside their batch root check; investigate the test-owned path contract rather than suppressing the tests. The previous full run started before the assets fix.
- Tasks 3–6, verification manager, readonly proof, generated schema/types, frontend archive UI, installed service, real acceptance and final push are NOT implemented/completed.
- Owned long-running tests/services: NONE; interrupted test poll was resumed and read back, completed rc=1. Existing unrelated Claude/ROS/Herdr processes must be preserved.
- New destination discovered: SSH alias antzb, actual hostname AI-STATION-001, user lenovo, repo /data/work/ws_moveit. Existing main and unrelated worktrees must not be modified. Use a fresh teleop-archive-viewer worktree on the same named branch.
- Destination Herdr 0.9.3 is running in default session. Codex 0.163.0 exists at /home/lenovo/.local/bin/codex; gpt-6.1-sol/high is in its model cache. Start a distinct named pane/agent, no dst and no model-default edits.
- Source evidence retained at the registered root. Exported logs/JUnit/metadata will be copied to the corresponding destination root, without moving or deleting source evidence. Archive: NONE. All read-back scratch trees are deletion candidates only.

## CP-004-ANTZB-SUCCESSOR

- Dispatch 049f4a0e-1580-4d81-baf2-7bfcf97aa349 receipt written before task probes. `successor-first-probe.json` records hostname AI-STATION-001, worktree `/data/work/ws_moveit/.worktrees/teleop-archive-viewer`, branch codex/teleop-archive-viewer, HEAD abcc17ff7, clean status. Source host ai-station is distinct; no self-SSH.
- Same registered evidence root retained on antzb. Source run records remain under `source-ai-station-evidence`; new antzb runs use `run-antzb.py`, `venv-antzb`, and new unique `scratch` directories. Source Python environment was not copied.
- User explicitly authorized current Codex implementation, no dst, no subagents, inline review, without reconfirming the approved plan. Ruling: preserve existing plan/spec wording and record authorization here; prior plan's draft status is historical.
- Host process/port inventory read with approved host access after sandbox tmux denial; no existing ROS/Gazebo/pytest stack observed, no default tmux server, unrelated Codex/Herdr/RustDesk listeners retained. No robot or collection operation is part of this task.
- Initial uv venv creation hit the global `/data/uv-cache` read-only boundary; repeated with task-owned cache, without modifying global configuration. This is environment setup, not product RED.
- Next: re-run retained malformed-scene regression before Task 2 fix. Real registry and installed/browser acceptance remain unconfirmed on this host.

## Task 2 antzb continuation

- Local CPU count is 24 (source was 32); full gate remains min(8,24)=8 workers. Test-only resource prefix points only at this worktree config/assets/launch; this is not runtime provenance.
- Environment-only attempts red-2-resume-90a8ee4b / 75241430 inherited ROS launch pytest plugins; bbb7cac3 lacked so101_demo mapping. No code RED claimed. Isolated python-path now exposes only this worktree's so101_demo plus underlay ament_index_python. All failed environment scratch retained.
- Sandbox TestClient run red-2-resume-831ad004 stalled with empty output; process state inspected on host. SIGINT did not release it, owned pytest 3342752 terminated with SIGTERM. Host runner red-2-host-f738b6dc completed in 1.68 s: 7 passed/1 failed at the retained None-scene boundary. Host execution used thereafter; no product timeout workaround.
- Minimal malformed-scene fix green-2-resume-6bd866cc: 8 passed. Additional contracts red-2-contracts-43a991f5: 3 failed/9 passed (bound scene SHA, schema-2 campaign-index fallback, nested attempts structure). Fixed at document projection boundary; duplicate campaign scenes also refused rather than overwritten.
- green-2-contracts-f6c44aef: all archive tests and CTest registration, 25 passed, rc=0, 2.80 s. Deprecation warning belongs to Starlette/AnyIO, retained in log. Inline review checked frozen binding and duplicate handling, membership semantics, fallback union, independent retry counters, null-last sort, two-package LRU/refresh and no records/frame/audit opens during metadata projection.
- Task 2 existing initial implementation was in the WIP handoff commit; this task completion commit contains its reviewed corrections and new regression tests. Next Task 3. Retained: all source and antzb runs; archived: none; read-back scratch trees are deletion candidates only, none deleted.

## CP-005-USER-REQUESTED-SUCCESSOR-HANDOFF

- User requested a handoff document and prompt before starting another Codex; no Task 3 implementation begun. Latest implementation commit 0eec8606f945c951294bb6eed4505a0c7774933b, clean before this documentation update.
- Resume document: `docs/experiments/so101-teleop-sealed-archive-viewer-antzb-successor-handoff.md`. It supersedes the earlier incoming handoff's Task 2 RED resume point, while preserving that historical record.
- Fresh direct host probe: AI-STATION-001, same authorized worktree/branch. No task runner/pytest/unified server/uvicorn remains. Previously hung scratch red-2-resume-831ad004 now has final rc=-15, elapsed 1701.14 s; retained without deletion.
- Real registry existence on antzb rechecked False. No service/browser, real-data acceptance, final full pytest, CTest install gate, or push performed in this continuation. Next implementation action is Task 3 RED, after the successor reads full approved plan/specs and current state.
- Permissions were changed by the session owner to danger-full-access / approval never immediately before this handoff request; no global defaults changed by the agent. Ruling: stop feature edits for this user-requested handoff; do not launch a successor or parallel worker.
- Retained: full root, source export, all antzb evidence and new handoff state snapshot; archived: none; read-back scratch trees remain deletion candidates only. No evidence deleted.

## CP-006-ANTZB-RESUME

- Fresh probe `successor-probe-1f692586.json`: direct AI-STATION-001 / lenovo, HEAD f76a4a99386fe8a882b13ccf47f3b3ef70b677e9, authorized branch/worktree clean; submodule uninitialized and preserved. No pytest/runner/uvicorn/ROS stack or default tmux server. Existing Codex/Herdr/RustDesk processes/listeners preserved. ROS graph N/A: archive file-only work; no ROS operation.
- Last trusted checkpoint CP-005 and Task 2 targeted 25 passes; no full gate inferred. Next experiment Task-3 RED adds episode/file contracts absent from Task 2. Same registered evidence root and exact `venv-antzb/bin/python`; 24 CPUs / full workers=8.
- Ruling: current direct user authorization continues Codex implementation, no dst/subagents, inline review, no repeated approval. Keep durable ledger instead of skill scratch and preserve every evidence artifact. Real seven-root/EXP-620 acceptance remains unavailable pending real registry, never synthetic-labelled as real.

## Task 3 complete

- RED `red-3-64024eda`: 13 failed / 1 passed, rc=1, 1.98 s; intended missing HTTP detail/series/files/frame contracts. GREEN `green-3-5f5bd635`: 39 passed, rc=0. Inline review added actual state-dimension/bounded-read probe and redirected frame-directory test; `red-3-review-ff2b9813`: 1 failed / 11 passed at cross-episode frame redirect (200 instead of 409).
- Fixed frame boundary against the original episode frames subtree, rather than trusting a redirected frames directory. Global records LRU holds at most two episodes across package evictions, unique snapshot tokens avoid object-id reuse. Only signal fields/frame names retained; PNG/audit never cached. All file opens validate package paths afresh; JSON/JSONL cap 2 MiB, UTF-8 byte cursor and line boundaries enforced.
- Final targeted gate `green-3-review-a72c7473`: archive directory plus CTest registration, 41 passed, rc=0, 4.15 s; JUnit/tempfile proofs/output/result under registered `scratch/<run-id>`. Synthetic only; no real registry/robot access. Runtime/visual N/A for backend-only task. Full gate and installed acceptance still pending.
- Inline self review: metadata/recording-processing timeline separation, fault details, manifest file ids, camera bounds, endpoint retention, paging EOF/no-final-newline and symlink replacements reviewed. Retained all runs, archived none, read-back scratch deletion candidates only. Next Task 4 RED.
