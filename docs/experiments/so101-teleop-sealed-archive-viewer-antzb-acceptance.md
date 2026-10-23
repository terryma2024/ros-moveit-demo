# Sealed archive viewer: antzb verification record

Date: 2026-10-17. Host: antzb / `AI-STATION-001`, user `lenovo`.
Worktree: `/data/work/ws_moveit/.worktrees/teleop-archive-viewer`.
Branch: `codex/teleop-archive-viewer`.
Latest implementation: `39e20806dcd94e5c05446b639ecfda43903da981`.

Status: Tasks 3–6 implemented; complete ordinary gates and installed synthetic acceptance passed. **Real seven-root and EXP-620 acceptance has not run.** The genuine registry is absent on antzb. No source-host connection or data transfer was attempted.

## Evidence identity

All paths below are relative to the one registered root:

`/data/work/so101-evidence/teleop-archive-viewer/20261017T062429Z-007cb1e3`

The ledger records task-level RED/GREEN runs and inline review. `successor-probe-1f692586.json` records the clean takeover at `f76a4a99386fe8a882b13ccf47f3b3ef70b677e9`. No dst or subagent was used. Existing Codex/Herdr/RustDesk/CUA processes were preserved.

## Complete gates

| Gate | Actual scope and result | Evidence |
| --- | --- | --- |
| Ordinary Python | `pytest -p xdist.plugin -q src/so101_teleop/test -n 8`: 1482 passed, 43 skipped, rc=0, 47.73 s | `scratch/full-final-pytest8-0873ee2c/{output.log,junit.xml,result.json,worker-proofs/}` |
| Package CTest | `colcon test --packages-select so101_teleop --executor sequential --event-handlers console_direct+`, complete 134/134 registration cases, rc=0, 258.17 s | `scratch/ctest-final-full-a1c11ca6/`; `colcon-final-test-log/`; `build/so101_teleop/test_results/` |
| Result readback | `colcon test-result --test-result-base <root>/build/so101_teleop --verbose`: 1659 reported tests, 0 errors, 0 failures, 43 skipped, rc=0 | `scratch/ctest-final-results-5b3d0de7/` |
| Complete frontend | `bun run test`: 64 files, 335 passed, rc=0, 5.06 s | `scratch/full-web-visual-final-38bf1487/` |
| Types | `bun x --no-install tsc -b`: rc=0, 2.26 s | `scratch/standalone-types-final-4ab0196d/` |
| Installed build | Task-local colcon build, including `tsc -b && vite build`, rc=0, 5.25 s | `scratch/install-visual-fix-ee72e0fb/`; `colcon-visual-log/` |
| Export drift | All three offline OpenAPI exports byte-identical; all three generated type files unchanged after regeneration | `schema-drift-result.json`; `generated-types-drift-result.json` |

The exact Python is `<root>/venv-antzb/bin/python` (3.12.3), Bun is `/home/lenovo/.bun/bin/bun` (1.3.14). Logical CPUs=24; xdist workers=8. Each run has a newly created NVMe scratch with TMPDIR/TMP/TEMP and an exact-interpreter tempfile proof. The final ordinary run contains 9 provenance records; final CTest contains 1206 (controller plus eight workers for each registered process). All eight worker ids and physical scratch locations were checked in `final-readonly-proof.json`.

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` prevents unrelated ROS pytest plugins from leaking in; xdist is explicitly loaded. CTest uses `PYTEST_ADDOPTS='-p xdist.plugin -p gate_probe -n 8'`, `CTEST_PARALLEL_LEVEL=1`. Full scope was never reduced. No benchmark suite ran. All 43 skip names/reasons remain in JUnit. Existing Starlette/ref warnings, the dependency's generated-C compiler warning and Vite shared-bundle warning remain in logs.

The initial complete CTest run also passed; its 273 result/log files were copied with SHA/size verification to `ctest-initial-snapshot/` before the final rerun, because the first archive cases preceded the final descriptor fix.

## Installed provenance and synthetic acceptance

The runtime uses the new `install/so101_teleop` and `install/so101_demo_py`, both built from this worktree. The existing unified factory imports `so101_demo`, so that runtime dependency was installed into the same private prefix. Its code was not modified and no demo/benchmark suite was collected. No collecting worktree/install was reused.

`installed-provenance.json` records module, script environment, tempfile and bundle hashes from outside the source tree. The source PYTHONPATH was cleared, then only the ROS underlay, private venv and task install were loaded. `server-check.log` contains `SO101_UNIFIED_APP_OK`. Service was isolated on `127.0.0.1:8014` in task tmux, without bridge/ROS Python/ACT worker configuration. Teleop/tasks were unavailable; archive routes were usable. No robot/simulator/control stack was started.

Two retained synthetic registry batches each contain a collection and a supporting package. They are explicitly labelled synthetic, use head/wrist PNGs with visible synthetic captions, and are not substitutes for the seven genuine packages. V2 has 130 UTF-8 audit lines for browser pagination. Only these self-created fixtures were made read-only.

- `browser-acceptance-result.json` and `browser-acceptance-steps.json`: 17 installed browser steps, zero page script errors. Covered package/filter/search/FAULT, share/reload, keyboard first/middle/last row, both cameras and SVG cursors, play-to-end, seal JSON, audit next page, browser back, verify/restart and supporting metadata. Each step saved before/after page state.
- `installed-api-acceptance.json`: 24/24 synthetic frames loaded with zero failures; UTF-8 pages had no repeated/missing rows; verification went running → cancelling → cancelled, restarted, then completed 38/38 with zero mismatches/missing files.
- `final-readonly-proof.json`: both batches' complete 61-path snapshots are unchanged, including permissions, sizes, mtime_ns and hashes. Package seals, sibling manifests and registry are included. Before/after snapshots are retained separately.
- Synthetic discovery=0.0014 s, package cold=0.0025 s, warm=0.0006 s. These timings describe only the small fixture; genuine package performance is unmeasured.

The CUA exact-window bind and two page actions were verified by fresh snapshots. The trusted background click route refused; explicit DOM-event actions changed the expected URL/page state. A separate Playwright CDP attachment timed out before product assertions; that tool run is retained. The completed browser acceptance reused the launcher's pipe. An earlier acceptance snapshot helper waited for an optional absent slider; its partial trace was preserved and the helper was corrected to check presence immediately. These runs are not product failures or successful acceptance runs.

## Visual evidence

All cited images were opened and inspected in this session:

- Baseline: `captures/packages/20261017T165403-f4abbce1e30e/window.png`.
- Package layout after local SHA-cell wrapping correction: `browser-packages-fixed.png`.
- Final installed row 4: `captures/final-row4/20261017T165846-c28e62960ff0/window.png`.

The final image shows head and wrist labels `000004`, row 4/4, sim_time 36.6, both cursors at the endpoint, six action labels and eight state labels. A pre-existing GNOME low-space notification appears over browser chrome; a fresh `df -h /data` showed 230 GiB free. The unrelated notification was preserved.

## Open acceptance boundary

`/data/work/so101-evidence/act-data/20260924-fbc25063-resume` is absent on antzb. Consequently none of the following is claimed: seven genuine roots, EXP-620 70/69 scene counts and 49/10/10 split, frm-007 FAULT and five recovered recordings, frm-000's 905 real rows, genuine package latency, or before/after real-data byte verification against manifest `82e06969c9a94ff69ac936237248fc4e117da8aafdf4b8e99f5d11b2fbb4bbfd`.

Next real acceptance step: verify that genuine registry's availability through an authorized connection to the distinct source host or a genuine local mount; freeze the real seal/manifest/registry identities and full directory snapshots before starting installed-service browsing. Never synthesize the expected counts or silently copy the collection.

## Cleanup, retention and review

`final-process-probe.json`: only task-owned browser launcher 3430385 and server 3421925 were signalled after checking their current argv; both exited, port 8014 is free, task tmux sessions ended. No existing process was stopped.

Retained: complete evidence root, source export, failed and successful runs, private environments, build/install, CTest snapshots, fixtures, browser profiles, screenshots and provenance. Archived runs: none. `final-retention-inventory.json` enumerates read-back scratch deletion candidates; they remain present. No evidence was deleted or chmod-restored.

Final review was inline. The demonstrated delayed-open race was fixed using descriptor-pinned reads and bounded original-PNG streaming; production containment was not relaxed. The fixed-helper test now canonicalizes its own synthetic batch root. The durable-root negative frontend test uses an explicitly unregistered path so NVMe TMPDIR cannot invalidate its premise. Deferred minor items: compact TSX formatting and the existing large shared bundle warning. Real-data acceptance remains the only unperformed acceptance category.
