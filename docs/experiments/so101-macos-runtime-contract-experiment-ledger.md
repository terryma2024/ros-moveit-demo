# SO-101 macOS fixed runtime contract experiment ledger

```yaml
task_id: so101-macos-runtime-contract
goal: validate the current macOS runtime patch on the local second physical Mac and preserve the exact cross-host boundary
success_contract: on matianyideMacBook-Air.local, prepare and full doctor pass, a real GUI task station reaches READY, and task-owned processes and windows clean up
worktree: /tmp/so101-debug-macos-runtime-contract-second-mac-2oruml/repo
branch: codex/so101-unified-webapp
base_commit: d8416d15e69d1e2a025f7735360d89ff4cccda66
current_commit: c521d4f96d356aef7da0157a08c7371a87e29972
evidence_root: /tmp/so101-debug-macos-runtime-contract-second-mac-2oruml
confirmed_conclusions:
  - Terry-Mac-mini.local passed the earlier /tmp runtime contract in RUN-002
  - matianyideMacBook-Air.local passed the current /opt/data/tmp worktree patch in EXP-MRC-007
  - ai-station passed the ordinary non-ML Linux package gate with eight pytest workers in RUN-006
disproven_routes:
  - a transferred submodule origin outside the approved remote allowlist is rejected by prepare
  - a user-home-only bun installation is invisible to the clean fixed runtime PATH
open_hypotheses:
  - the current /opt/data/tmp patch still needs a fresh Mac mini prepare, doctor, READY, and cleanup run before a same-patch two-host claim
latest_checkpoint: CP-MRC-LINUX-PARITY-PASS
next_experiment: EXP-MRC-MAC-MINI-CURRENT-PATCH
```

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
  `pytest -n 8 --dist loadscope src/so101_demo_py/test`. The ordinary gate excludes the twelve
  tests marked `explicit_ml` and does not collect `benchmark_test/`.
- Result: after aligning the nine Torch/GroundingDINO cases discovered by the Linux environment,
  the final fresh `package-gate-n8-sshd-notty-020` completed with 3654 passed, 9 skipped, zero
  failed in 41.61 seconds. The four additional passes are the new interactive/headless SSH
  transport classification regressions.
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
- Stability follow-up: a later full run exposed a synchronous `PerceptionService.run_next()` test
  racing the executor threads started by `service.start()`. All four tests of the synchronous seam
  now start only the fake runtime, leaving threaded behavior to the dedicated executor tests. The
  four focused cases passed before `package-gate-n8-final-015`.
- Runtime impact: no ROS stack was launched by this test-only A/B. Pytest-owned child processes
  exited with their runs.
- Retained: all RED/GREEN, focused, and package-gate evidence under the registered root.
- Archived: none.
- Deletion candidates only: basetemp trees recorded under `/opt/data/tmp`; none deleted.

## RUN-006 — Linux eight-worker parity gate

- Date: 2026-09-21 Asia/Shanghai
- Status: `PASS_LINUX_NON_ML_PACKAGE_GATE`
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
- Preparation observations: the first recursive fetch updated the parent branch but failed because
  Gitee no longer served the locked submodule object `6591771d`; a parent-only fetch then resolved
  commit `97a69638`. The isolated `so101_demo_py` build passed. The first pytest attempt did not
  collect tests: all eight workers failed importing `torch` from
  `test_grounding_dino_domain_retention.py`. The fixed Linux Python has no Torch, and the file is a
  Torch/GroundingDINO suite, so it is being aligned with the user-authorized `explicit_ml` boundary
  rather than counted as a code failure. A first alignment using module-level `importorskip` made
  the ROS launch-testing collector return only one skip and no tests (pytest exit 5); Torch import
  is therefore delayed to the two tensor tests while the module-level marker remains available at
  collection. Both failed scratch trees are retained as deletion candidates.
- The next complete Linux run reached the test boundary: 3544 passed, 22 skipped, 45 failed, and
  49 errors. The errors were missing MuJoCo and Darwin-private-path fixtures. The failures grouped
  into macOS-only MPS/install contracts, Linux transport assertions using Darwin path rules, a
  leaked live child from the oversized-cmdline procfs test, two missing Darwin platform patches,
  one Linux v4 document retaining MPS-only fields, an unmarked Torch checkpoint test, and an
  unpopulated locked submodule. These are environment/platform test boundaries, not represented as
  Linux acceptance. Scratch `linux-pytest-n8-003` is retained as a deletion candidate.
- After dependency and platform alignment, `c080b343` reached 3521 passed, 135 skipped, and three
  failures. All three were the same protected environment read for the per-session
  `sshd: <user>@notty` process. The scanner already froze the interactive `@pts/N` form but not
  headless SSH. The exact `@notty` spelling is now classified as the same non-ROS transport; other
  SSH command shapes remain fail-closed. Full and focused failed runs are retained under scratches
  `linux-pytest-n8-004` and `linux-pytest-n8-005`.
- Commit `de91458d` reduced the complete gate to one failure: 3527 passed, 135 skipped, and
  `test_external_cleanup_retires_only_owned_worker_and_releases_claim` failed after process
  retirement timed out. Linux identity reads already treated an exited zombie as absent because
  its procfs command line was empty, but the process-group scan still counted that same zombie as
  a live member. This disagreed with the macOS `psutil` path and made an external cleaner wait for
  a child it could not reap. Scratch `linux-pytest-n8-006` retains the complete failed run.
- Commit `c521d4f9` makes both Linux procfs readers exclude zombie processes and adds a real
  unreaped-zombie regression test. The source was rebuilt into isolated build and install roots
  `build-c521d4f9` and `install-c521d4f9`; the locked submodule was restored from the registered
  bundle at exact commit `85d2a5c42686a3d6b0d909a047a4188b24edd257`.
- Authoritative Linux gate: the exact test Python was
  `/data/work/so101-evidence/macos-parallel-compat-linux/20260921-a50dcb6c-n8-001/venv/bin/python`.
  Before pytest, it proved `tempfile.gettempdir()` resolved to the new scratch
  `scratch/linux-pytest-n8-007/tmp`. The command used `-n 8 --dist loadscope`, collected only
  `src/so101_demo_py/test/`, and retained the ordinary `not explicit_ml` marker filter.
- Final result: **3529 passed, 135 skipped, zero failed** in 25.37 seconds; pytest exit 0. The four
  Python fork warnings did not change the result. Readback resolved `so101_demo_py` to
  `install-c521d4f9/so101_demo_py`, and the imported Python package to the matching isolated build.
- Retained: the complete durable evidence root, all seven scratch runs, isolated worktrees,
  builds, installs, full logs, JUnit documents, preflight/readback records, and the submodule bundle.
- Archived: none.
- Deletion candidates only: `scratch/linux-pytest-n8-001` through
  `scratch/linux-pytest-n8-007`, after readback. Nothing was deleted.

## RUN-007 — Second physical Mac reproduction

- Date: 2026-09-21 Asia/Shanghai
- Host: `matianyideMacBook-Air.local`, Darwin arm64
- Source commit: `d8416d15e69d1e2a025f7735360d89ff4cccda66` plus the
  `/opt/data/tmp` worktree patch copied from `Terry-Mac-mini.local`
- Locked fork source: `85d2a5c42686a3d6b0d909a047a4188b24edd257`
- Status: `PASS_SECOND_PHYSICAL_MAC`
- Evidence root: `/tmp/so101-debug-macos-runtime-contract-second-mac-2oruml`
- Fixed paths: `/opt/ros2_jazzy` resolves to `/Users/matianyi/ros2_jazzy`;
  `/opt/data/tmp` is owned by the current user with mode `0700`.
- Build prerequisite: the first project-overlay attempt stopped at `BUN_EXECUTABLE` because
  the clean launcher does not accept `~/.bun/bin`. Homebrew `bun 1.4.2` was installed at
  `/opt/homebrew/bin/bun`, matching the launcher's fixed PATH. No user-home bun path was added
  to source or runtime configuration.
- Scoped verification: `test_macos_runtime_contract.py` passed all 13 tests; zsh syntax,
  Python byte compilation, and `git diff --check` passed.
- Prepare: the locked fork build reported 233 tests, zero errors, zero failures, and zero skips.
  `so101_mujoco_support`, `so101_teleop`, and `so101_demo_py` then built successfully. The
  published dylib farm contains 879 libraries at run `20260921T140346Z-14147`, with inventory
  SHA-256 `f731368429c8f1a36944a60ce67ee9205b59b9cd7bbcab543ef0e950dc353536`.
- Full doctor: `PASS`; CPython 3.11.15 imported `rclpy`, loaded
  `libcontrol_toolbox.dylib`, `libhardware_interface.dylib`, and
  `librosidl_typesupport_c.dylib`, and verified all fixed package prefixes.
- Real station: `ROS_DOMAIN_ID=226` launched the GUI task station through
  `scripts/so101-macos.zsh`. `motion_stack_ready --timeout-s 90` returned `phase=READY`, with
  all three controllers active, all three required MoveIt services callable, and all three
  required actions available.
- Visual evidence: exact window ID `27275`, owner `ros2_control_node`, title
  `MuJoCo : so101_task_scene`, was captured at original window resolution. The image shows the
  SO-101, cup, table, and MuJoCo `Running` status.
- Cleanup: one Ctrl-C was sent to the task-owned launch PTY. The MuJoCo window disappeared and
  the task-identity process scan found zero `ros2_control_node`, MoveGroup, robot-state,
  readiness, or task-station residue.
- Acceptance: **second physical Mac runtime reproduction passed**. This closes the cross-host
  host run only. It does not prove a strict same-patch two-host A/B because `RUN-002` used the
  earlier `/tmp` contract; the current `/opt/data/tmp` patch still needs a fresh Mac mini run.
  The ordinary non-ML `so101_demo_py` package gate passed in `RUN-005`; the Linux parity run in
  `RUN-006` remains open, and explicit ML tests are outside that gate.
- Retained: the complete registered evidence root; locked-fork run
  `/opt/data/so101/runtime/fork/runs/85d2a5c42686a3d6b0d909a047a4188b24edd257`;
  `/opt/data/so101/workspace`; and dylib-farm run `20260921T140346Z-14147`.
- Archived: none.
- Deletion candidates only: the registered evidence root, failed prepare logs, and generated
  launch-parameter entries under `/opt/data/tmp`. A later `mac-mini-worktree.patch` snapshot is
  also a deletion candidate: it was captured only after the Mac mini writer had expanded the
  dirty worktree into unrelated parallel-suite files, so it is invalid as the six-file source
  patch and was not used for this result. Nothing was deleted.

```yaml
experiment_id: EXP-MRC-007
status: VALID
prior_experiment: RUN-002
hypothesis: the fixed macOS runtime contract is portable to a second Apple Silicon Mac
prediction: prepare and full doctor pass, then a real GUI task station reaches READY and cleans up without task-owned residue
single_variable: not a strict single-variable A/B; host changed and the contract advanced from RUN-002 /tmp to the current /opt/data/tmp patch
lifecycle: ISOLATED_STACK
preconditions:
  - no SO-101 task-station, ros2_control_node, MoveGroup, robot-state publisher, or readiness process was present
  - /opt/ros2_jazzy resolved to /Users/matianyi/ros2_jazzy
  - /opt/data/tmp existed with current-user ownership and mode 0700
  - parent source was d8416d15e69d1e2a025f7735360d89ff4cccda66 and the locked fork was 85d2a5c42686a3d6b0d909a047a4188b24edd257
success_criteria:
  - locked fork and project overlays build successfully
  - full doctor imports rclpy, loads all required dylibs, and verifies package prefixes
  - motion_stack_ready reports three active controllers, three services, and three actions
  - exact MuJoCo window evidence shows the running SO-101 task scene
  - one owner Ctrl-C leaves no task-owned process or window residue
failure_criteria:
  - any prepare, doctor, READY, GUI, or cleanup boundary fails under the fixed contract
invalid_criteria:
  - source or submodule drift, a reused stack, a non-isolated ROS domain, or missing cleanup evidence
provenance:
  source_commit: d8416d15e69d1e2a025f7735360d89ff4cccda66
  source_patch_paths:
    - .agents/skills/so101-dev/references/macos-runtime-environment.md
    - docs/experiments/so101-macos-runtime-contract-experiment-ledger.md
    - docs/guides/macos-apple-silicon-ros2-jazzy-so101-mujoco.md
    - scripts/so101-macos.zsh
    - scripts/so101_macos_runtime_contract.py
    - src/so101_demo_py/test/test_macos_runtime_contract.py
  install_overlay: /opt/data/so101/workspace/install
  runtime_executable: /opt/ros2_jazzy/.venv/bin/python /opt/ros2_jazzy/install/ros2cli/bin/ros2
  ros_domain_id: 226
  gz_partition: N/A (MuJoCo)
commands:
  - command: scripts/so101-macos.zsh doctor --base --json
    exit_code: 0
  - command: scripts/so101-macos.zsh prepare
    exit_code: nonzero; rejected transferred unapproved submodule origin
  - command: scripts/so101-macos.zsh prepare
    exit_code: nonzero; fork passed 233 tests, then project overlay rejected missing fixed-PATH bun
  - command: HOMEBREW_NO_AUTO_UPDATE=1 /opt/homebrew/bin/brew install bun
    exit_code: 0
  - command: scripts/so101-macos.zsh prepare
    exit_code: 0
  - command: scripts/so101-macos.zsh doctor --json
    exit_code: 0
  - command: ROS_DOMAIN_ID=226 scripts/so101-macos.zsh launch so101_demo_py so101_mujoco_task_station.launch.py headless:=false sensor_rendering:=true include_teleop:=false
    exit_code: unavailable; the task-owned PTY was stopped by one Ctrl-C and cleanup was verified independently
  - command: ROS_DOMAIN_ID=226 scripts/so101-macos.zsh run so101_demo_py motion_stack_ready --timeout-s 90
    exit_code: 0
  - command: .agents/skills/gui-capture/scripts/capture-gui.sh --local --window-id 27275 --output-root /tmp/so101-debug-macos-runtime-contract-second-mac-2oruml/gui
    exit_code: 0
observed:
  - final prepare built three project packages and published an 879-library farm with manifest SHA-256 f731368429c8f1a36944a60ce67ee9205b59b9cd7bbcab543ef0e950dc353536
  - READY reported all required controllers, services, and actions available
  - exact GUI evidence showed MuJoCo running the SO-101 task scene
  - post-Ctrl-C process and window readbacks found zero task-owned residue
  - Octomap sensor configuration and an unattached plastic_cup warning were present but did not fail the declared runtime READY gate
inferred:
  - the current /opt/data/tmp patch runs successfully on matianyideMacBook-Air.local
  - same-patch portability across both Macs remains unproven until a fresh Mac mini run
  - this result does not qualify pick-place behavior or explicit ML tests
conclusion: PASS_SECOND_PHYSICAL_MAC for this host and runtime patch only; not a same-patch two-host closure
evidence:
  - /tmp/so101-debug-macos-runtime-contract-second-mac-2oruml/prepare.log sha256=919a3a3623d10db48ed6b5012178898d7dfe85d73156cee3f17e7fb919a78f28
  - /tmp/so101-debug-macos-runtime-contract-second-mac-2oruml/prepare-approved-origin.log sha256=c211d8319f569d9e623376050983b31ac0e946ccea051139094008fe091c42c6
  - /tmp/so101-debug-macos-runtime-contract-second-mac-2oruml/prepare-with-bun.log sha256=bcae60b067851bad3a666bb5623d826236f075d84b57c510a0edd526bbb8982a
  - /tmp/so101-debug-macos-runtime-contract-second-mac-2oruml/doctor.json sha256=c356988d37fd6f3366572b5da72ccfd467d9c9614f8b1f95c059eaa07b4083da
  - /tmp/so101-debug-macos-runtime-contract-second-mac-2oruml/motion-stack-ready.log sha256=760515f1ee343a60f848889cf48a6fea110a98ebed150235ad05562a76ef9ab8
  - /tmp/so101-debug-macos-runtime-contract-second-mac-2oruml/task-station.log sha256=7bfb5c6e77875bed04063724fbfae5cbc820c9911576e4991ab438a0945be5c3
  - /tmp/so101-debug-macos-runtime-contract-second-mac-2oruml/gui/20260921T222338-19c8110358a2/manifest.json sha256=e3698aa27aedc5b5987725b9947ef30597533e47e4b6e58cb5b6db5874914e5e
  - /tmp/so101-debug-macos-runtime-contract-second-mac-2oruml/gui/20260921T222338-19c8110358a2/window.png sha256=f6be2333d4ee9d7e43ad60d5552a0ade810673154e53d94ff90b7b4e013c49da
  - /tmp/so101-debug-macos-runtime-contract-second-mac-2oruml/tests/final/junit.xml sha256=a034a032852048ed8dc41ce3a321b4d28fb96a61ddc2d977ff21cb8053056909
  - /tmp/so101-debug-macos-runtime-contract-second-mac-2oruml/cleanup-readback.md sha256=02c0d083b764d565ed3ff64fc247dac51bc9b3e41f3d3153179df1580ea9cd6d
decision: KEEP
next_experiment: EXP-MRC-MAC-MINI-CURRENT-PATCH
```

```yaml
checkpoint_id: CP-MRC-SECOND-MAC-SCOPED-PASS
last_valid_experiment: EXP-MRC-007
current_hypothesis: RUN-006 Linux parity and the Mac mini current-patch rerun remain open
working_tree_status: RUN-007 second-Mac evidence and implementation-plan updates atop the RUN-005 fixes
owned_processes: NONE
preserved_processes: unrelated user GUI and terminal processes were not touched
confirmed_conclusions:
  - second physical Mac runtime reproduction passed
disproven_routes:
  - unapproved transferred submodule origin
  - user-home-only bun path under a clean launcher
open_risks:
  - explicit ML tests are outside the RUN-005 ordinary non-ML gate
  - RUN-006 Linux eight-worker parity is still running
  - runtime READY does not prove pick-place motion behavior
  - current /opt/data/tmp patch has not been rerun on Terry-Mac-mini.local
next_command: rerun prepare, full doctor, READY, exact-window evidence, and cleanup on Terry-Mac-mini.local with the current patch
```

```yaml
checkpoint_id: CP-MRC-LINUX-PARITY-PASS
last_valid_experiment: RUN-006
current_hypothesis: the ordinary non-ML package gate is portable across macOS and Linux; only the fresh same-patch Mac mini runtime rerun remains open
working_tree_status: c521d4f96d356aef7da0157a08c7371a87e29972 passed and was pushed to origin/codex/so101-unified-webapp
owned_processes: NONE
preserved_processes: no user process or ROS stack was modified by the Linux package gate
confirmed_conclusions:
  - macOS passed 3654 tests with 10 platform skips under the fixed runtime and eight workers
  - ai-station passed 3529 tests with 135 platform or unavailable-feature skips under eight workers
  - Linux process identity and group membership now agree that an unreaped zombie is no longer running
disproven_routes:
  - treating a zombie process-group entry as a live external-cleanup target
  - sourcing the stale worktree-local macOS install overlay
open_risks:
  - explicit ML tests remain outside the user-authorized acceptance gate
  - runtime READY does not prove pick-place motion behavior
  - the current /opt/data/tmp patch has not been rerun on Terry-Mac-mini.local after RUN-007
next_command: rerun prepare, full doctor, READY, exact-window evidence, and cleanup on Terry-Mac-mini.local with the current patch
```
