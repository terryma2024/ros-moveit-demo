# SO-101 Teleop sealed archive viewer task ledger

```yaml
task_id: so101-teleop-sealed-archive-viewer-20261017
goal: Implement a strictly read-only archive browser after plan approval
success_contract: ordinary Teleop pytest, Vitest, types; seven sealed roots; EXP-620 acceptance; unchanged sealed bytes
worktree: /home/matianyi/Projects/ros-moveit-demo/.worktrees/teleop-archive-viewer
branch: codex/teleop-archive-viewer
base_commit: 007cb1e3c1830f9348052fa2cc4f39e4bd0396a7
current_commit: 250141cd91634214e368e1bc1787cc76a9f1906c
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
latest_checkpoint: CP-002-IMPLEMENTATION-AUTHORIZED
next_experiment: BASELINE-001
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
