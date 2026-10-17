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

## Task 4 complete

- RED `red-4-c8c232e0`: five intended verify/manager assertions failed, rc=1, 1.38 s. GREEN `green-4-a179c2b2`: 56 passed. Additional bounded chunk cancellation and injected terminal exception checks passed (`green-4-review-b7c327e1`, 58 passed).
- Inline review reproduced a parent-link replacement between validation/hash: `red-4-race-ae952ad1`, 1 failed / 6 passed, rc=1. Fix pins directory descriptors, uses O_NOFOLLOW on each component and checks regular-file identity. `green-4-final-891b8386`: complete archive scope + unified lifecycle + CTest registration, 59 passed, rc=0, 6.07 s.
- One owned non-daemon worker; busy while old thread alive, per-package status isolation, deterministic Event-based cancel test, 1 MiB chunks, bounded 100 issues, retained snapshot during refresh, manifest/seal identity revalidation, shutdown cancel/join. Symlink targets are never hashed, external targets are refused issues.
- Non-root proof (lenovo) exercises all successful endpoint families, parameter/id errors, JSONL second page, both cameras at first/last, refresh, verify cancel/restart. After chmod of synthetic fixture only, write-mode and Path mutation probes stayed silent; complete path/type/mode/size/mtime/hash snapshot unchanged. Fixture and scratch retained, never permission-restored or removed. Backend-only visual/robot gates N/A.
- Retained all evidence; archived none; all read-back scratch runs deletion candidates only. No full ordinary/installed/real-data gate claimed. Next Task 5 RED.

## Task 5 complete

- API RED `red-5-api-ec8addb9`: 1 failed / 6 passed at archive routes leaking into compatibility Teleop schema. GREEN `green-5-api-407a276d`: 10 passed (OpenAPI + CTest registration). All 11 archive operations and response DTOs export offline while disabled; compatibility views retain shared components, exclude archive paths.
- Frontend dependency gate: Bun 1.3.14 frozen lock install `web-install-75925a3f`, rc=0; no new dependencies/lock changes. `red-5-web-284f4a39` only printed Bun usage due CLI argument placement, INVALID (not test RED). Actual `red-5-web-actual-f19027cf`: 2 failed / 11 passed at missing Archives navigation/path mapping. Runner now chooses web cwd for Bun, old runner retained as `run-antzb.before-web-cwd.py`.
- Added generated-type client, encoded ids/query/AbortSignal, structured HTTP failures; package discovery, URL/history selection, complete statistics/identity/unavailable values, all 12 sortable scene columns, split/outcome/search/paging and full reasons. Supporting roots expose seal metadata only. Verifier polls only active jobs and cleans up requests/timers on selection changes.
- Inline review RED `red-5-restart-0f23bd8a` reproduced same-action verify restart not issuing a second POST; changed actions to fresh request objects. `green-5-web-review-a527cc98`: 6 files / 20 tests passed, rc=0, 1.23 s. Existing runtime negative-test console errors and Sheet ref warning retained, not hidden. `typecheck-5-final` evidence records tsc result; early malformed Bun x invocation and strict optional-field compile errors retained as environment/build feedback.
- Regenerated unified and both compatibility schemas/types using exporters/Bun scripts, no hand edits. Backend/ frontend RED/GREEN logs and scratch preserved. Visible browser acceptance deferred to installed build after Task 6; real registry remains absent. Next Task 6 RED; retained all, archived none, read-back scratch deletion candidates only.

## Task 6 complete

- RED `red-6-abd24af4`: two real deep-link/scene-switch UI assertions failed because scene query still displayed package view; the three not-yet-created component imports also failed collection (not counted as behavioral RED). GREEN `green-6-0e93aea0`: 4 files / 8 tests passed, rc=0, 0.90 s.
- Episode summary/timeline/files, two lazy cameras, unique current row for frame URLs/time and both SVG cursors, actual signal dimensions, 10 Hz play/pause/end cleanup, next-two-row-per-camera prefetch, accessible slider/buttons and Radix paged file dialog implemented. Keyed scene changes reset row/playback/file state; abort + active guard rejects late responses, tested with a fetcher deliberately ignoring abort.
- Full Vitest initial `full-web-6-666eadfb`: 334 passed / 1 failed in preexisting durable-root.test.ts. That negative test derived its supposed unregistered path from tmpdir, which this task correctly places under the registered Linux evidence prefix. Ruling: make this negative case use an explicit unregistered path instead of weakening production prefix validation or moving TMPDIR. Final `full-web-6-review-6965cb2b`: 64 files / 335 tests passed, rc=0, 5.77 s. Legacy negative-test console/ref warnings retained.
- Strict compile found test afterEach returning VitestUtils; corrected callback to return void. `build-web-6-fd3a42d6`: tsc -b + Vite production build rc=0, 4.67 s; large existing shared bundle warning retained. Exact standalone typecheck recorded in `typecheck-6-final` run. No dependencies added.
- Inline self review checked cursor interpolation against original row_times, first/middle/last navigation, empty FAULT, bounded prefetch and timer/request cleanup. Installed fresh visual evidence remains a final gate. Full xdist8 Python gate currently running separately; not inferred green. All artifacts retained; archived none, read-back scratch deletion candidates only. Next final gates/install/available acceptance.

## Full gate environment correction

- `full-teleop-8-6f757800`: 1408 passed / 43 skipped / 4 failed / 6 collection errors, rc=1. Underlay was not on isolated Python path; rclpy/launch/ament_package unavailable. Two fixed-helper failures reproduced historical CONTROL_SOCKET_OUTSIDE_BATCH_ROOT because the test batch root retained the short socket symlink alias.
- Ruling: canonicalize only the synthetic fixed-helper batch root before deriving socket paths; retain the short alias for tests needing direct short AF_UNIX addresses. Do not weaken production containment. Original failure was at the intended helper boundary; the changed test helper keeps all original assertions.
- `full-teleop-8-underlay-6b73d89f`: INVALID environment, 831 passed / 35 skipped / 47 failed / 62 collection errors after distro Pydantic v1 took precedence. Exact import proof `underlay-proof-e9e5f880` confirms private Pydantic 2.14.1 plus ROS underlay after path order correction. Disable automatic pytest plugin loading, explicitly load xdist instead of inheriting ROS launch plugins. No test scopes/skips changed.
- `full-teleop-8-correct-env-e30f79df`: full ordinary Teleop scope, 1480 passed / 43 skipped, rc=0, 42.45 s, 24 CPUs / 8 workers, fresh NVMe scratch. All names and skip reasons in JUnit. CTest full package gate running independently; its per-process/worker interpreter/tempfile proofs are task-owned gate_probe records, not source changes.

## Final inline review: pinned read descriptors

- Important finding: validation followed by Starlette FileResponse / Path.open allowed a symlink replacement before the actual open. `red-final-open-race-3979e9e5`: both frame and JSON tests returned 200 instead of 409, 2 failed / 16 passed, rc=1. No real evidence was involved.
- Fixed every archive payload/metadata/manifest open through one read-only descriptor walk, pinning each directory and refusing links on every open component. Frames retain the descriptor through response completion/disconnect. Ruling: use StreamingResponse over the validated original PNG descriptor instead of FileResponse's delayed pathname open; same bytes/cache policy, bounded 64 KiB chunks, explicit image/png OpenAPI contract. This closes the demonstrated race without disk caches or image conversion.
- First GREEN caught missing files classified as refused by the common open helper; corrected verifier issue mapping, preserving exact missing/mismatch semantics. Final full ordinary `full-final-pytest8-0873ee2c`: 1482 passed / 43 skipped, rc=0, 47.73 s, 8 workers on 24 CPUs. `worker-proofs/` confirms each worker's exact interpreter and NVMe tempfile location. JUnit retains all skip reasons.
- Final frontend `full-web-final-24f81a2f`: 64 files / 335 passed, rc=0, 4.81 s; `types-final-check-f05463e2`: rc=0. Exported/re-generated final PNG contract via official repository scripts. `install-final-6d999b13`: task-local build/install, rc=0, 4.59 s. Existing compiler/bundle warnings retained separately.
- Review is inline per direct user/AGENTS.md; no independent reviewer dispatched. Deferred minor: archive TSX JSX formatting is compact; existing shared bundle remains above Vite's warning threshold. Neither changes endpoint/read-only contracts. Real-data/visual/CTest acceptance still tracked below, no overall completion claim.
