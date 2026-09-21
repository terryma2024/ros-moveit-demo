# SO-101 macOS fixed runtime contract experiment ledger

## RUN-001 — Registered

- Date: 2026-09-21 Asia/Shanghai
- Status: `PLANNED`
- Branch: `codex/so101-unified-webapp`
- Baseline HEAD: `6e38b11af2212f2eceb03f94f5678b5600c91376`
- Submodule HEAD: `6591771de32c4d2e66bcb5076b3a851cfe6a9833`
- Evidence root: `/tmp/so101-debug-macos-runtime-contract-54f5d922-9678-4cff-a340-dc4f59479a23`
- Scope: fixed macOS ROS 2 runtime contract, unified SO-101 launcher, adaptive contract tests, current-host validation
- Current host: `Terry-Mac-mini.local`, Darwin arm64
- Initial observation: `/opt/ros2_jazzy` is an exact symlink to `/Users/matianyi/ros2_jazzy`; fixed install, Python, `/opt/data`, and `/tmp` exist; `/opt/ros2_jazzy/dylib_farm` does not exist.
- Initial loader observation: the legacy `macos_dylib_farm/current` contains `librosidl_typesupport_c.dylib` but not `libhardware_interface.dylib`; the latter exists under `/opt/ros2_jazzy/extra_ws/install/lib`.
- Retention: keep the registered root; nothing deleted or archived.

## RUN-002 — Current-host implementation and validation

- Date: 2026-09-21 Asia/Shanghai
- Status: `SCOPED_RUNTIME_PASS_WITH_OPEN_CROSS_HOST_AND_PACKAGE_GATES`
- Parent source at validation: `b4c149e6b120fbaa368580c07ebab4222855f9ae`
- Locked fork source: `85d2a5c42686a3d6b0d909a047a4188b24edd257`
- Current host: `Terry-Mac-mini.local`, Darwin arm64
- Evidence root: `/tmp/so101-debug-macos-runtime-contract-54f5d922-9678-4cff-a340-dc4f59479a23`
- Runtime contract:
  - ROS root: `/opt/ros2_jazzy`
  - ROS install: `/opt/ros2_jazzy/install`
  - ROS Python: `/opt/ros2_jazzy/.venv/bin/python`
  - temporary directory: `/tmp`
  - workspace data root: `/opt/data`
  - locked fork overlay: `/opt/data/so101/runtime/fork/current`
  - project overlay: `/opt/data/so101/workspace/install`
  - dylib farm: `/opt/ros2_jazzy/dylib_farm/current`
- External environment contract: no required environment variables. `ROS_DOMAIN_ID` is optional,
  defaults to `0`, and is accepted only in the range `0..232`.
- MuJoCo task-station identity: `ROS_DOMAIN_ID=225`; `GZ_PARTITION` is not applicable to the
  MuJoCo launch.

### Observed results

- TDD RED: `tests/red-explicit-python-003` failed at the intended explicit-Python boundary
  before the installer was repaired.
- Scoped GREEN: `tests/focused-contract-005` completed with 35 passed tests. The later
  `tests/post-rpath-contract-001` rerun also completed with 35 passed tests; zsh syntax checks
  and backend integration checks returned zero.
- Final verification: `tests/final-verification-001` is invalid as a test result because the
  command omitted the fixed project overlay and the two requested files were not collected.
  The corrected `tests/final-verification-002` used the complete overlay order and disabled
  unrelated pytest plugin auto-loading: 35 passed; zsh syntax, Python byte compilation, full
  doctor, backend integration, and `git diff --check` all returned zero.
- Fork build/test: `prepare/current-mac-012` built the locked fork and reported 233 tests,
  zero errors, zero failures, and zero skipped tests. The installer invokes the fixed Python
  explicitly and, on macOS with the test farm supplied, runs the generated CTest boundary
  directly so `/bin/sh` cannot strip the required loader environment.
- Publish regression: `prepare/current-mac-013` returned zero after the atomic symlink update
  was changed to `mv -fh`. The current fork points to
  `/opt/data/so101/runtime/fork/runs/85d2a5c42686a3d6b0d909a047a4188b24edd257/ws_mujoco_ros2_control_fork/install`.
- Dylib farm: current points to
  `/opt/ros2_jazzy/dylib_farm/runs/20260921T102951Z-31305`, contains 767 library symlinks,
  and has doctor inventory SHA-256
  `055ace69e50c05512c14b75fcb29e214c8052cc1a5c87300abe56f85451997d0`. It
  records deterministic later-prefix wins in `.overrides.tsv` (SHA-256
  `932118e1928c62d5939ef42fe4ff9c67a64b5bce933c1129f619dd1384779ffc`). Full doctor
  successfully loaded `libcontrol_toolbox.dylib`, `libhardware_interface.dylib`, and
  `librosidl_typesupport_c.dylib`, imported `rclpy`, and verified the fixed package prefixes.
- Environment isolation: `validation/environment-matrix-001` ran two different poisoned
  HOME/PATH/Python/AMENT/CMake/colcon/DYLD configurations. Both commands returned zero, both
  outputs were valid JSON, and the JSON files were byte-identical.
- Real station: `validation/task-station-current-mac-002` reached `READY` on the first attempt
  through `scripts/so101-macos.zsh`, with all three controllers active, all three required
  MoveIt services callable, and all three required actions available. The launch log records
  `mujoco_ros2_control/MujocoSystemInterface`, the main-thread UI handoff, and camera rendering.
  One SIGINT was sent to the recorded launch owner. The owner exited before its wrapper could
  persist a launch exit-code file; a subsequent task-identity process scan found zero residue.
  Readiness is therefore accepted, while launch-owner exit-code capture remains explicitly
  unavailable.
- Ordinary package gate: the fixed-Python `rclpy` probe passed, but the ordinary
  `src/so101_demo_py/test/` run is not GREEN. It was interrupted at 83% after 1867.28 seconds
  once the Darwin run had accumulated Linux-only parallel-suite failures: 2881 passed,
  136 failed, 8 skipped, pytest exit 2. Representative failures assume `/proc/self/fd`,
  Linux `/usr/bin/sleep`, or Linux UNIX-socket/path behavior. Those planned parallel-suite
  repairs are outside this runtime-contract checkpoint and were not started.
- Cross-host status: two isolated configurations on this Mac passed. A second physical Mac
  was not available and was not tested; the local matrix is not represented as a substitute.

### Conclusions and evidence accounting

- `OBSERVED`: the unified entry builds and starts the current SO-101 MuJoCo station on this
  Mac without either `@rpath/libhardware_interface.dylib` or
  `@rpath/librosidl_typesupport_c.dylib` loader failure.
- `OBSERVED`: the caller does not need to export any environment variable; the launcher
  reconstructs the fixed environment and rejects a host that violates the `/opt` contract.
- `OPEN`: the complete ordinary package gate and a second-physical-Mac run remain open, so
  this record does not claim repository-wide or two-host acceptance.
- Retained runs: the entire registered evidence root; the current locked-fork run under
  `/opt/data/so101/runtime/fork/runs/85d2a5c42686a3d6b0d909a047a4188b24edd257`;
  `/opt/data/so101/workspace`; and dylib-farm run `20260921T102951Z-31305`.
- Archived runs: none.
- Deletion candidates only (nothing deleted): repository-local regenerable `build/` and
  `install/`; the superseded fork run `6591771de32c4d2e66bcb5076b3a851cfe6a9833`; older farm
  runs `20260921T090338Z-66881` and `20260921T102507Z-26981`; any stale `.current-*` symlinks
  accidentally placed inside superseded targets before the `mv -fh` fix; and pytest temporary
  scratch trees under the registered evidence root. Explicit user authorization is required
  before deleting any of them.

## RUN-003 — `so101-dev` conditional macOS runtime reference

- Date: 2026-09-21 Asia/Shanghai
- Source commit: `0704b367dd85d696afbcdef18570f4cb232322ac`
- Status: `PASS`
- Evidence: `/tmp/so101-debug-macos-runtime-contract-54f5d922-9678-4cff-a340-dc4f59479a23/skill-macos-runtime-reference`
- RED: `red-001` exited 1 because `references/macos-runtime-environment.md` did not exist.
- Change: added the macOS runtime reference, routed to it from `so101-dev/SKILL.md` only for
  Apple Silicon runtime/test environment failures, and replaced the stale hard-coded macOS
  package-test block in `test-and-acceptance.md` with that conditional route.
- GREEN: `green-001` passed the skill validator, conditional-routing checks, all six local-link
  resolution checks, the no-user-path check, and `git diff --check`.
- Runtime impact: none; no ROS process or external service was started.
- Retained: RED/GREEN logs under the registered evidence root.
- Archived: none.
- Deletion candidates: none added by this run. No evidence was deleted.

## RUN-004 — Complete ordinary `so101_demo_py` pytest on macOS

- Date: 2026-09-21 Asia/Shanghai
- Source commit: `dc371162585b6d1f974bed8e0fc5716bf01c55f8`
- Locked fork source: `85d2a5c42686a3d6b0d909a047a4188b24edd257`
- Status: `FAIL`
- Evidence: `/tmp/so101-debug-macos-runtime-contract-54f5d922-9678-4cff-a340-dc4f59479a23/tests/ordinary-so101-demo-002`
- Preparation: `scripts/so101-macos.zsh prepare` rebuilt `so101_mujoco_support`,
  `so101_teleop`, and `so101_demo_py` from the frozen source. Full doctor passed, including
  all three required dylib loads and fixed package-prefix checks (`prepare_rc=0`, 83 seconds).
- Command boundary: fixed ROS Python, all four fixed overlays, fixed dylib farm,
  `PYTHONNOUSERSITE=1`, `TMPDIR/TMP/TEMP=/tmp`, and package scope
  `src/so101_demo_py/test/`; `benchmark_test/` was not collected.
- Result: 3669 tests collected, 3453 passed, 208 failed, 8 skipped in 93.84 seconds;
  pytest exit 1. The run reached 100% without interruption. JUnit reports zero collection
  errors and zero benchmark cases.
- Failure concentration: 69 in `test_parallel_perception_runtime.py`, 51 in
  `test_parallel_batch_resources.py`, 28 in `test_parallel_batch_cli.py`, 18 in
  `test_parallel_batch_web_control.py`, 16 in `test_parallel_ipc.py`, 11 in
  `test_parallel_batch_artifacts.py`, and 15 across five smaller parallel-runtime files.
- Observed repeated boundaries: tests deriving a writable runtime root from
  `Path(TMPDIR).parent` resolve to `/` under the fixed macOS contract; several durability and
  process-identity tests read Linux `/proc`; many runtime/container cases fail closed with
  `PATH_OWNER` or `IPC_BASE`; one wrapper invokes a Python without `yaml`. These observations
  explain large failure clusters but do not prove that every one of the 208 failures has the
  same platform-only cause.
- Runtime impact: no ROS stack was launched; pytest exited and left no task-owned test process.
- Retained: prepare log, source identity, preflight, complete pytest log, JUnit, parsed failure
  summary, result, and post-test status under the registered evidence root.
- Archived: none.
- Deletion candidates: pytest temporary files created under `/tmp`; none deleted.

## RUN-005 — Fixed macOS temporary directory and parallel-suite compatibility

- Date: 2026-09-21 Asia/Shanghai
- Source commit at start: `d8416d15e69d1e2a025f7735360d89ff4cccda66`
- Status: `PASS_MACOS_NON_ML_PACKAGE_GATE`
- Prior run: `RUN-004`
- Evidence: `/tmp/so101-debug-macos-runtime-contract-54f5d922-9678-4cff-a340-dc4f59479a23/tests/macos-temp-and-parallel-compat-005`
- Hypothesis result: changing the fixed macOS `TMPDIR`, `TMP`, and `TEMP` from `/tmp` to
  `/opt/data/tmp` removed the read-only-root and pytest temporary-directory group mismatches. The
  remaining Linux-only `/proc`, UNIX-socket, process-identity, and wrapper-Python assumptions were
  repaired with platform-specific runtime boundaries rather than test-only path substitutions.
- Regression sequence: the runtime-contract test was RED while it still expected `/tmp`, then
  GREEN after the fixed contract moved to `/opt/data/tmp`. A focused rerun of the previously
  failing parallel-runtime groups reported 468 passed and 1 skipped.
- Authoritative macOS gate: fixed ROS Python, all four overlays, fixed dylib farm,
  `TMPDIR/TMP/TEMP=/opt/data/tmp`, a fresh short basetemp, and
  `pytest -n 8 --dist loadscope src/so101_demo_py/test`. The ordinary gate excludes the two tests
  marked `explicit_ml` and does not collect `benchmark_test/`.
- Result: the final fresh `package-gate-n8-final-011` completed with 3660 passed, 9 skipped,
  zero failed in 60.47 seconds;
  pytest exit 0. Its JUnit, complete log, preflight, exit code, elapsed time, and basetemp record are
  retained under the run evidence directory.
- Expanded diagnostic: `package-gate-n8-all-007` deliberately overrode the marker filter. It
  reported 3659 passed, 9 skipped, and 3 timing-sensitive non-ML failures while co-scheduled with
  the explicit ML workload. A fresh eight-worker focused rerun of those three cases then passed
  3/3. Per user direction, explicit ML is outside this acceptance gate; the expanded run is not
  represented as a passing full gate.
- Final-gate repair: an intervening ordinary run exposed four long Darwin AF_UNIX fixture paths
  and three high-load fixture races. The socket tests now select a short per-process root only on
  Darwin, while Linux retains pytest's normal path. The success-process fixture no longer races
  perception scheduling, and the stderr fixture gives its diagnostic child a bounded scheduling
  window. The seven exact failures passed 7/7 with eight workers before the final full gate.
- Runtime impact: no ROS stack was launched by this test-only A/B. Pytest-owned child processes
  exited with their runs.
- Retained: all RED/GREEN, focused, and package-gate evidence under the registered root.
- Archived: none.
- Deletion candidates only: basetemp trees recorded under `/opt/data/tmp`; none deleted.

## RUN-006 — Linux eight-worker parity gate

- Date: 2026-09-21 Asia/Shanghai
- Status: `PLANNED_AFTER_MACOS_COMMIT_AND_PUSH`
- Branch: `codex/so101-unified-webapp`
- Evidence root: `/data/work/so101-evidence/macos-parallel-compat-linux/20260921-a50dcb6c-n8-001`
- Scope: on `ai-station`, verify the same ordinary non-ML `src/so101_demo_py/test/` boundary with
  eight pytest workers. Do not collect `benchmark_test/`.
- Scratch contract: create one previously nonexistent directory below
  `scratch/linux-pytest-n8-001/tmp`, export `TMPDIR`, `TMP`, and `TEMP` to it, and prove with the
  exact test Python that `tempfile.gettempdir()` resolves inside that directory before pytest.
- Retention: retain the full test log, JUnit, environment preflight, elapsed time, exit code, and
  scratch-path record. Treat the scratch tree as a deletion candidate after readback; delete
  nothing without explicit authorization.
