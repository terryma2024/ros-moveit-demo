# SO-101 sealed archive viewer: antzb successor handoff

Checkpoint date: 2026-10-17. This is a task handoff, not a feature completion report. The user requested this document before starting another Codex. Implementation is paused at the Task 2 → Task 3 boundary; do not start a second implementer concurrently.

## Execution authority and location

- You run directly on **antzb**, hostname **AI-STATION-001**, user `lenovo`. This is distinct from source host `ai-station`, user `matianyi`. Do not SSH to yourself.
- Worktree: `/data/work/ws_moveit/.worktrees/teleop-archive-viewer`.
- Branch: `codex/teleop-archive-viewer`. Implement only in this worktree; do not modify main, any collecting worktree, or shared submodule metadata.
- User already approved the complete plan and explicitly overrode the default dst workflow: **current Codex implements itself, no dst, no subagents, inline self review**. Do not ask for the same plan approval again. Continue decisions autonomously within that authorized scope.
- Required session model from repository rules: GPT-6.1 Sol / High. Do not change global model defaults. Report a genuine model/tool limitation rather than silently substituting.
- The user subsequently authorized autonomous decisions and unsandboxed execution. This handing-off session now has unrestricted filesystem/network access and approval policy `never`; check the successor's actual permissions. Do not claim a chat instruction bypasses tool-enforced restrictions.
- Original Herdr dispatch was workspace `w3`, pane `w3:p1`, id `049f4a0e-1580-4d81-baf2-7bfcf97aa349`. The original receipt was already written correctly before task probes. Do not overwrite/replay that dispatch. `successor-first-probe.json` records the earlier takeover at abcc17ff7a; it is historical, not current HEAD.

## Read before task actions

Load `superpowers:using-superpowers`, project-local `.agents/skills/so101-dev/SKILL.md`, and applicable execution/debugging/TDD/verification skills. Read the root `AGENTS.md` and routed skill references. Preserve evidence; do not use skill cleanup steps to delete it.

Then read these files completely:

1. This handoff.
2. `docs/experiments/so101-teleop-sealed-archive-viewer-experiment-ledger.md` (canonical persistent task ledger).
3. `docs/superpowers/plans/2026-10-17-so101-teleop-sealed-archive-viewer-implementation.md` (complete approved plan).
4. `docs/superpowers/specs/2026-10-17-so101-teleop-sealed-archive-viewer-requirements.md`.
5. `docs/superpowers/specs/2026-10-17-so101-teleop-sealed-archive-viewer-design.md`.

The plan/spec draft statuses and source-host paths are historical. Authorization is recorded in CP-002/CP-004 and the user's direct instructions; adapt implementation paths to antzb. The earlier `so101-teleop-sealed-archive-viewer-antzb-handoff.md` describes the incoming Task 2 RED and is superseded by this handoff for resume state. Do not revert Task 2 to reproduce that old checkpoint.

## Current Git state

Last implementation commit: **`0eec8606f945c951294bb6eed4505a0c7774933b`**. The source worktree was clean immediately after it. This successor handoff and its ledger checkpoint are a separate documentation commit; obtain actual HEAD/status afresh.

| Commit | State |
| --- | --- |
| `250141cd91` | Initial plan/spec/ledger |
| `1c611eb097` | Task 1 discovery/config/path boundaries |
| `abcc17ff7a` | Transfer checkpoint, includes initial Task 2 WIP |
| `0eec8606f9` | Task 2 reviewed corrections and regression tests |

The Task 2 completion commit changed only `archive_viewer/package.py`, `test/archive_viewer/test_archive_package.py`, and the ledger. Initial manifest/package/models/API work already resides in the WIP transfer commit. Task 3–6 code is **not implemented**. No final full-suite, installed-service, browser, or real-data acceptance is complete.

No remote operation was performed in this continuation; do not assume 0eec8606f9 is pushed. Before the final authorized push, fetch/read the target and preserve all remote-only commits. The only allowed push is `git push origin codex/teleop-archive-viewer`, without force. No gh, no main push, no other branch push. Actual origin is Gitee SSH; github fetch currently uses HTTPS and push uses SSH. Do not normalize remotes unnecessarily.

## What Task 2 changed and proved

- Reproduced the retained malformed campaign scene on antzb: `None` leaked TypeError; now it gives structured HTTP 422 `ARCHIVE_DOCUMENT_INVALID`.
- Validates duplicate/invalid scene ids and nested recording/processing attempt containers; checks a supplied frozen scene-list SHA binding.
- Schema 2 fallback preserves scene ids from campaign-index wave plans when frozen scene metadata/campaign-result are absent.
- Existing projection keeps collection membership distinct from `episode/seal.json.committed`, separates processing retries from recording attempts, preserves FAULT/MISSING rows, supports sort/filter/search/paging, and uses a two-package LRU with retained snapshot references.
- New metadata projection probe confirms package statistics do not open records, PNGs, or audit payloads.
- Inline review and targeted archive/CTest-registration test gate passed. This is not proof that every malformed shape or real-world metadata field has been covered. During subsequent review, compare identity/config sources, full recording timeline, retry decisions, frozen binding behavior and package-cache/path safety against the complete plan; missing identity must remain explicitly unavailable rather than invented or filled from another package.

### Antzb test runs

All paths below are under the registered root's `scratch/`; each completed run contains command/hostname/CPU/elapsed/rc in `result.json`, exact-interpreter tempfile proof, `output.log`, and JUnit when pytest reached XML emission.

| Run | Outcome |
| --- | --- |
| `red-2-host-f738b6dc` | 7 passed / 1 failed, intended None-scene boundary, rc=1, 1.68 s |
| `green-2-resume-6bd866cc` | 8 package tests passed, rc=0, 1.48 s |
| `red-2-contracts-43a991f5` | 9 passed / 3 failed: bound SHA, schema-2 fallback, malformed nested attempts, rc=1, 1.78 s |
| `green-2-contracts-f6c44aef` | Entire archive test directory + CTest registration: 25 passed, rc=0, 2.80 s |

Latest GREEN is targeted, not the complete ordinary Teleop gate. Starlette/AnyIO emitted a retained deprecation warning.

Environment-only runs remain retained: `red-2-resume-90a8ee4b` and `75241430` inherited ROS launch pytest plugins and lacked `lark`; `bbb7cac3` lacked the so101_demo source mapping. They are not code RED. `red-2-resume-831ad004` hung in sandboxed TestClient with empty output; SIGINT did not release it. Host process inspection identified owned pytest PID 3342752, which was terminated with SIGTERM. Its final runner result is rc=-15, elapsed 1701.14 s. Unsandboxed runner then reached all tests in under 2 s. Do not rerun that sandbox hang or present it as a product regression.

## Evidence and ready-to-use environment

One registered durable evidence root, retained on antzb:

`/data/work/so101-evidence/teleop-archive-viewer/20261017T062429Z-007cb1e3`

- Exact private Python: `<root>/venv-antzb/bin/python` (3.12.3).
- Runner: `<root>/run-antzb.py`. Read it before use. Unlike the copied source runner, it points to this antzb worktree. It creates a new unique NVMe `scratch/<label>-<uuid>/tmp` for every run, exports TMPDIR/TMP/TEMP, sets PYTHONDONTWRITEBYTECODE, proves tempfile with the actual interpreter, saves logs/JUnit/result, and propagates the true exit code.
- Example next RED: `<root>/venv-antzb/bin/python <root>/run-antzb.py red-3 pytest -q src/so101_teleop/test/archive_viewer/test_archive_episode.py src/so101_teleop/test/archive_viewer/test_archive_files.py` after writing those tests.
- Private dependency cache: `<root>/uv-cache`. Global uv default `/data/uv-cache` was read-only in the old sandbox; use the task cache explicitly for any new dependency work. Dependencies were installed from TUNA per skill. Do not modify a shared venv.
- `<root>/python-path/so101_demo` links to this worktree `src/so101_demo_py/src`; `ament_index_python` links to the ROS underlay. Runner replaces inherited PYTHONPATH so ROS pytest plugins do not leak in.
- `<root>/test-resource-prefix` has resource-only ament registration for `so101_demo_py` and config/assets/launch links to this worktree. This enables source tests; it is **not an installed runtime**.
- Source logs remain separately under `<root>/source-ai-station-evidence`; its `run.py` still has source-host hardcoded paths. Do not execute it on antzb or copy its venv.
- Actual antzb CPU count is **24**, so complete ordinary pytest still uses **8 xdist workers**. Source host had 32. Record scope, CPU, workers, skips, JUnit, rc and elapsed.
- Bun verified at `/home/lenovo/.bun/bin/bun`, version `1.3.14`. Record path/version in every new web shell; use Bun for install/scripts/CLI, frozen `bun.lock`, no npm/npx/package-lock.
- `/opt/ros/jazzy` exists but a new Teleop build/install has not been attempted. Resolve exact executables and dependency closure before build/test.

Runner currently does **not** configure a short IPC root. The source full gate still had 3 failures/9 setup errors; exact names and logs are retained in the ledger/source JUnit. Some failures were resource-prefix incompleteness (antzb prefix now includes config/assets/launch); fixed-helper isolation rejected symlinked IPC aliases (`CONTROL_SOCKET_OUTSIDE_BATCH_ROOT`). Resolve test-owned IPC paths without weakening production checks, suppressing failures, shrinking scope, or moving fsync-heavy fixtures off NVMe. Do not reuse the source short alias blindly.

## Next work

1. Confirm actual hostname/pwd/branch/HEAD/status and absence of owned active tests/services. Save a new uniquely named successor probe under the evidence root and add ledger checkpoint; preserve old probes.
2. Start **Task 3** test-first: episode detail, attempts timeline, records cache bounded to two episodes, both cameras, at most 2000 signal points retaining endpoints, real action/state dimensions, manifest-issued file ids, strict frame/path checks, bounded JSON/UTF-8 JSONL paging. Maintain CTest registration. Run RED → GREEN, inline review, one task commit.
3. **Task 4:** single background verifier, cancellation/thread lifecycle, bounded issues, per-open path validation, manifest identity, symlink refusal, and a complete synthetic non-root read-only proof over every successful/error endpoint. Preserve fixtures/evidence.
4. **Task 5:** offline-exported complete OpenAPI + generated types, compatible schema filtering, typed abortable client, `/archives` navigation, URL state, package statistics/scene table/filter/sort and verify UI. Use existing theme/components without new chart dependencies.
5. **Task 6:** episode summary/files/timeline, one currentRow drives two cameras and both inline SVG cursors, playback cleanup, bounded prefetch, paging dialog, rapid-switch stale response protection. Tests first, then full Bun test/typecheck/build.
6. Run complete ordinary `src/so101_teleop/test/` with xdist8 and proper NVMe scratch; fix isolation/environment before claiming a product failure. Run required CTest/package gate, `colcon test-result`, exporter/type drift checks. Build a fresh task-owned install and prove module/script/web provenance outside source PYTHONPATH. No benchmarks, no uncrustify reformat.
7. Attempt real acceptance only with genuine accessible sealed evidence; preserve all data and existing collection processes. Commit final evidence/ledger separately and push only the authorized feature branch after review.

## Strict read-only and real acceptance boundary

Never write/create/rename/delete/chmod a real sealed root, a directory containing SEALED.json, or its manifest. Never execute/import sealed code or open sealed SQLite. Synthetic fixtures only for unit tests; fixture TMPDIR being on `/data` does not authorize opening real business data. Client requests contain issued ids, never paths. Refuse traversal/external symlinks and arbitrary external manifest addresses. Only the exact package sibling manifest is allowed outside a package.

The registry `/data/work/so101-evidence/act-data/20260924-fbc25063-resume` exists on source **ai-station** according to the earlier verified evidence. On **antzb** its existence check returned **False again at this handoff**. Do not fabricate seven-package acceptance or silently transfer 55 GB. Later, use only a verified authorized connection to the distinct source host for final installed-service/browser/byte checks, or explicitly report the inaccessible acceptance boundary. No SSH to any host occurred in this continuation.

Real acceptance still requires seven sealed roots; EXP-620 planned=70, committed=69 (49 train / 10 validation / 10 offline_test), frm-007 FAULT, round 1 recovered=5 and rounds_run=1; frm-000 has 905 rows, action dimension 6 and state dimension 8 with synchronized head/wrist/SVG. Collection membership and episode seal.committed are different facts. Before/after hash the EXP-620 contents, SEALED.json, sibling manifest and registry; snapshot all seven roots' complete paths/types/sizes/mtime/link targets to detect new files too. Manifest expected SHA from source plan: `82e06969c9a94ff69ac936237248fc4e117da8aafdf4b8e99f5d11b2fbb4bbfd`. Real acceptance has **not** run here.

## Processes and retention at handoff

Fresh host process inspection found no remaining `run-antzb.py`, `python -m pytest`, task unified server or uvicorn process (excluding the inspection shell itself). The sandbox-hung run has a final result; do not retry it as if still active. No service/browser was started by this continuation. Existing unrelated Codex/Herdr/RustDesk/listeners were preserved. ROS/Gazebo/collection stacks were not started or modified.

- Retained: entire registered root, all source export and antzb run logs/JUnit/proofs, private venv/cache/resource prefix, old receipt/probe and new handoff evidence.
- Archived: none.
- Deletion candidates: every read-back `scratch/<run-id>` tree, including failed/interrupted environment runs. They remain physically present; no deletion is authorized. The exact run paths and results are enumerated by `<root>/handoff-successor-state.json`.
