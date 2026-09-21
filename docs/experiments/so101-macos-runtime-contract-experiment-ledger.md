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
