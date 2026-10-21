# Host gate

`run_host_gate.zsh` builds the worktree it lives in, then runs the `so101_demo_py` pytest suite and `colcon test`. The same
scripts run on every host. What differs between hosts (paths, interpreters, worker counts, memory limits) is in
`hosts/<host>.env`. The scripts are tracked, so a gate result names the exact tools that produced it.

```
scripts/gate/run_host_gate.zsh [--host H] [--gate-suffix S] [--demo-workers N] [--no-isolation] [--serial] [--full]
                               [--teleop-jobs N] [--plan] [--no-rerun-known-flakes]
```

Run it from the worktree under test, with a clean `git status`. The gate refuses to start when the worktree is dirty, when
`scripts/gate` has uncommitted changes, or when its gate directory, build root or scratch directory already exists. A gate
result is valid only if `scripts/gate` was clean at the commit that was tested.

| Option | Effect |
| --- | --- |
| `--host H` | Use `hosts/H.env`. Without it, the host whose `HOST_NAMES` contains `hostname` is used. An unknown host is refused (exit 2). |
| `--full` | Run the `controller_manager` and `hardware_interface_testing` tests even when the skip rule allows skipping them. |
| `--serial` | Demo pytest, then colcon test; the colcon parts one after the other; `so101_teleop` with `ctest -j1`. The skip rule still applies; add `--full` for full coverage. |
| `--teleop-jobs N` | `ctest -j` for the parallel part of `so101_teleop` (default 6). |
| `--gate-suffix S` | Gate directory `gates/<commit12>.S` instead of `gates/<commit12>`. |
| `--demo-workers N` | xdist workers of the demo stage. Default: `DEMO_WORKERS` of the host config. |
| `--no-isolation` | No per-stage ROS domains and no loopback-only discovery. |
| `--plan` | Print both skip decisions and exit. Creates nothing. |
| `--no-rerun-known-flakes` | Do not do the one allowed rerun after a failure (on by default). |

## Host config

Every host-specific value is a `KEY=VALUE` line in `hosts/<host>.env`. No script contains a host path. The loader
(`load_host.zsh`) never overrides a variable that is already set in the environment, so one run can override any value.
`scripts/evidence/*` and `scripts/images/*` read the same values (`source scripts/gate/load_host.zsh; so101_load_host`).

| Key | Meaning |
| --- | --- |
| `HOST_NAMES` | Names that `hostname` can return (lowercase), for host detection. |
| `W` | Platform work root. |
| `EVIDENCE_ROOT`, `EVIDENCE_R` | Registered evidence root, and the results root `R` that holds `gates/<id>`. |
| `SCRATCH_ROOT` | Per-run TMPDIR scratch; must be on the durable evidence filesystem. |
| `BUILD_ROOT`, `GATE_CCACHE_DIR` | Build, install and log trees (`BUILD_ROOT/gates/<id>`) and the ccache directory. |
| `DEPS_FREEZE` | Frozen Python dependencies and lodepng (`python-deps`, `build-deps/lodepng`). |
| `TEST_VENV` | colcon test interpreter environment. |
| `DEMO_PYTHON` | Demo pytest interpreter. |
| `DISK_PATH` | Filesystem reported in `df.txt`. |
| `DEMO_WORKERS` | Default xdist workers of the demo stage. |
| `GATE_STAGED` | `1`: demo stage first, then the colcon stage (its parts still run concurrently). `0`: both stages at once. |
| `GATE_SCOPE`, `GATE_SCOPE_MEMORY_HIGH`, `GATE_SCOPE_MEMORY_MAX` | `1`: run inside `systemd-run --user --scope` with these `MemoryHigh` and `MemoryMax` values. |
| `GATE_MEM_SAMPLER` | `1`: start `run_tools/memory_sampler.py`; its log is `memory-sampler.log` in the gate directory. |
| `GATE_RESET_SIGINT` | `1`: start the gate through `sigdfl.py`, which resets SIGINT to its default (a job started with `&` inherits "ignored", and every launch-supervisor test then waits out a 20 s timeout). |
| `DEMO_DIST` | xdist `--dist` mode of the demo stage; empty keeps the xdist default. |
| `DEMO_MALLOC_ARENA_MAX`, `DEMO_MALLOC_TRIM_THRESHOLD`, `DEMO_MALLOC_MMAP_THRESHOLD` | glibc malloc settings of the demo stage only; empty means not set. |
| `GATE_EXTRA_PYTHONPATH` | Extra `PYTHONPATH` entries for the demo stage. |
| `NATIVE_BUILD_DEPS`, `BUN_BIN`, `BUN_CACHE` | Inputs of the image build (`scripts/images`). |

`MUJOCO_GL=egl` is exported by the build, demo and colcon stages on every host.

## Where things go

| What | Where |
| --- | --- |
| `build/`, `install/`, `log/` (colcon), `test-run.*` and `demo-run.*` trees | `BUILD_ROOT/gates/<id>/` |
| Results: `gates-result.txt`, `fast-gate-timing.txt`, `head.txt`, `*.rc`, decisions, `stage-*`, `build.log`, ccache statistics | `EVIDENCE_R/gates/<id>/` |
| Small files of each `test-run.*` and `demo-run.*` (JUnit, logs, rc, elapsed), copied by `collect_results.zsh` | `EVIDENCE_R/gates/<id>/test-run.*/`, `.../demo-run.*/` |
| Pointer to the build root | `EVIDENCE_R/gates/<id>/build-root.txt` |
| Per-run TMPDIR of pytest and colcon test | `SCRATCH_ROOT/gate-<id>/` (deletion candidate after readback) |

`<id>` is `<commit12>` or `<commit12>.<suffix>`. Anything that needs the install reads `build-root.txt` and refuses when it is missing.

Files added to the gate directory by the repository version of the gate:

| File | Content |
| --- | --- |
| `gate-tools.txt` | `gate_tools_commit` (last commit that changed `scripts/gate`), `gate_tools_head`, number of tracked files, `gate_tools_clean`, and the `git diff --stat` of `scripts/gate` (empty when clean). |
| `ros2-control-tests.json`, `jtc-tests.json` | Also carry `gate_tools_commit`. |
| `gate-host.txt` | Host name and the effective host switches. |
| `stage-env.txt` | Stage settings, read by `rerun_known_flakes.zsh`. |
| `gate-verdict.txt` | `first_run_rc`, `known_flake_rerun`, `rerun_rc`, `final_rc`. |
| `rerun/`, `rerun-known-flakes.console` | Output of the known-flake rerun, when it ran. |

`gates-result.txt` and `fast-gate-timing.txt` keep their format and always describe the first run.

## Stages

1. `gate_build.zsh`: fresh `colcon build` of the worktree and `third_party` with tests on, the `third_party/ros2_controllers`
   overlay, and ccache.
2. `gate_demo_py.zsh`: `so101_demo_py/test` (never `benchmark_test`) against the installed package of the build root, xdist, TMPDIR
   proven inside `GATE_SCRATCH`. Target paths can be narrowed with `GATE_DEMO_TARGETS`.
3. `colcon_stage.zsh` runs `colcon_part.zsh` three times (`main`, `teleop`, `jtc`), each with its own TMPDIR, IPC base and
   colcon log base, then one `colcon test-result` and `ctest_extra_phases.py`, which adds the older ctest phases of `so101_teleop`.

Without `--serial` and with `GATE_STAGED=0` the demo stage and the colcon stage run at the same time. When either skip decision is
`run`, the gate switches to serial by itself: the upstream suites are timing sensitive and flake under concurrent mode.

## Parallel upstream tests

Off by default (`GATE_UPSTREAM_PARALLEL=0` in the host config; `--upstream-parallel` / `--no-upstream-parallel` per run). When the
decisions say `run`, the gate normally goes serial. With the switch on it does not: the upstream suites run in the groups of
`upstream-groups.txt`, each group on CPUs of its own and in its own ROS domain, beside the demo stage and the other colcon parts, which are
kept to the remaining CPUs (`taskset -c`; the user systemd manager here does not delegate the `cpuset` controller, so
`systemd-run -p AllowedCPUs=` is not available).

- `upstream_groups.py cpus` gives the groups whole cores (both threads), the fastest first, until they hold `GATE_UPSTREAM_CPU_SHARE`
  of the logical CPUs (at least one core per group); the group weights split the cores; the rest is every other CPU. The split is
  written to `upstream-cpus.json` in the gate directory.
- `upstream_stage.zsh` first checks the groups against `ctest -N` of each package (every test in exactly one group; a selector naming a test
  that no longer exists is refused), then starts the groups. The slowest tests (`test_trajectory_actions`, `test_controller_manager`, the
  spawner tests; see the times in `upstream-groups.txt`) each have a group of their own. `upstream_groups.py timing` lists them for a build.
- Domains: group *i* uses `UPSTREAM_DOMAIN_BASE` (223) + *i*. `joint_trajectory_controller` stays loopback only, `controller_manager` does not.
- A package split over several groups is several ctest runs in one build directory. A ctest tag has minute resolution and colcon reads only the
  newest, so `upstream_slot.zsh` keeps the starts of one package at least 75 s apart; `ctest_extra_phases.py` adds the older phases.
- `upstream_groups.py sets` writes the executed tests of the upstream packages (ctest name and status, gtest cases per file) to
  `upstream-sets.json`; `--upstream-sets-reference FILE` compares them with those of a serial gate and fails the gate on any difference.
- The known-flake rerun is one serial colcon stage; the groups do not take part in it.

## so101_teleop as one xdist run

Off by default (`GATE_TELEOP_XDIST=0` in the host config; `--teleop-xdist` / `--no-teleop-xdist` per run). The ordinary gate runs one ctest process (one pytest
process) per `so101_add_pytest_test` registration of `src/so101_teleop/CMakeLists.txt`, `-j $TELEOP_JOBS` at a time, after the serial tests. With the switch on, the
serial tests (`SERIAL_TELEOP_TESTS` in `colcon_part.zsh`) still run first as ctest runs with `-j1`, and every other registered module runs as ONE
`python3 -u -m pytest <files> -n $TELEOP_JOBS` in the build directory, with the flags `ament_add_pytest_test` uses (`--junit-xml`, `--junit-prefix=so101_teleop`, a cache
directory of its own) and one xunit file `so101_teleop_xdist.xunit.xml` in the same results directory, so `colcon test-result` counts it as before.

- `teleop_pytest.py paths` gives the files from the registrations (refusing an excluded name that is not registered, a missing file, a duplicate name or path), so one
  pytest run collects exactly what the separate runs collect. The serial tests stay separate because one of them kills the process group of a sibling pytest.
- `teleop_pytest.py sets` writes the executed tests of the package (`classname::name` -> pass|fail|error|skipped) to `teleop-sets.json` in the gate directory in every gate;
  `--teleop-sets-reference FILE` compares them with another gate's and fails the gate on any difference (ids or results).
- The whole run is bounded by `timeout 1800`; there is no per-module ctest timeout in this mode.

## Skip rules

`controller_manager` and `hardware_interface_testing` (`third_party/ros2_control`) and the upstream `joint_trajectory_controller`
suite (`third_party/ros2_controllers`) are skipped only when all of these hold:

1. `--full` was not given.
2. `git status --porcelain --untracked-files=all` of the third-party directory is empty.
3. A baseline exists: the newest record (by `recorded_at_epoch`) among `gates/*/ros2-control-tests.json` (or `jtc-tests.json`) and the
   seed file `gates/ros2-control-tests-baseline.json` (no seed exists for `jtc`) with `ran: true` and `green: true`.
4. The baseline `tree` equals `git rev-parse HEAD:<directory>`.
5. The baseline `apt_hash` equals the hash of `dpkg-query -W 'ros-jazzy-*'` now.

A skipped gate writes `ran: false`, so it never becomes a baseline. The packages are always built. When the `jtc` upstream suite is
skipped, `test_state_queue_publication` still runs. The rule does not see a change of compiler, CMake flags or `gate_build.zsh`; run once
with `--full` after such a change. `--plan` prints both decisions.

## Why concurrent stages are safe

- Temp directories: each stage and part has its own `tmp` under the scratch root, with a `tempfile.gettempdir()` proof.
- IPC sockets: each process group makes its own `mktemp -d /tmp/so101-ipc.XXXXXXXX` for `SO101_IPC_SOCKET_BASE`.
- ROS domains: `main` stays unset on purpose, because `run_test_isolated.py` only picks a private domain per launch test while
  `ROS_DOMAIN_ID` is unset. The demo stage uses 203, `teleop` 204 and `jtc` 229, all loopback only (override with
  `DEMO_ROS_DOMAIN_ID`, `TELEOP_ROS_DOMAIN_ID`, `JTC_ROS_DOMAIN_ID`). `main` is not restricted to loopback: the
  `controller_manager` spawner tests that pass `--controller-manager-timeout 1.0` cannot discover the manager in 1 s over loopback.
- The colcon invocations select disjoint packages and use separate `--log-base` directories.

## so101_teleop

The 124 `so101_teleop` ctests are plain `python3 -m pytest <file>` commands, so parallelism comes only from `ctest -j`. The tests in
`SERIAL_TELEOP_TESTS` (top of `colcon_part.zsh`) run first with `-j1`; everything else runs with `-j N` (`--teleop-jobs`, default
6). The script exits 98 if a listed name is not registered in `src/so101_teleop/CMakeLists.txt`.

Teleop parallel self-kill (fixed 2026-10-14): `test_fixed_helper_full_protocol` ran `fixed_helper.py` with plain `subprocess.run`, so the
helper sat in the gate's process group. The autouse fixture in `test/conftest.py` of a sibling pytest found it through the shared
`SO101_IPC_SOCKET_BASE` marker and called `killpg` on that group, which was the gate's own. The test is now in `SERIAL_TELEOP_TESTS`, and
every teleop `colcon test` call runs under `setsid -w`, so a stray group signal fails tests instead of killing the gate. The test
defects themselves (no `start_new_session=True`; `terminate_group` signals a group that contains the caller) are not fixed.

## Known flakes and the one rerun

`known-flakes.txt` lists tests that fail under load and pass alone. Format, one entry per line:
`<test id substring> | <reason> | <date added>` (date `YYYY-MM-DD`; `#` starts a comment). After a failed gate,
`rerun_known_flakes.zsh <gate dir name>` runs automatically, once, unless `--no-rerun-known-flakes` is given:

- It refuses (exit 3) when any failing test id is not matched by an entry, when `known-flakes.txt` is malformed, or when a failed
  stage has no failed test case to name.
- A failed demo stage is rerun with only the failed test ids and one worker. A failed colcon stage is rerun in full, with the stage
  settings recorded in `stage-env.txt`.
- `gate-verdict.txt` records the first run and the rerun. The exit code is 0 only when the rerun passed. A gate that is green only after a known-flake rerun is recorded as such in `gate-verdict.txt` (`known_flake_rerun=passed` with a non-zero `first_run_rc`). The first run stays in
  `gates-result.txt`, and a gate whose colcon stage needed the rerun is not a skip-rule baseline.

A red result on a listed test is not evidence of a regression until it fails again alone.

## Other tools in this directory

| File | Use |
| --- | --- |
| `upstream_groups.py`, `upstream-groups.txt`, `upstream_stage.zsh`, `upstream_slot.zsh` | The parallel upstream tests: CPU split, group partition, executed sets, timing, start slots. |
| `rc_record.py` | `decide`, `finish`, `seed` (skip-rule records) and `tools` (gate tools commit and diff stat). |
| `ros2_control_decision.zsh`, `jtc_decision.zsh` | The two skip decisions. Read only. |
| `collect_results.zsh <gate dir> <build root>` | Copy the small result files of the run directories into the evidence gate directory. |
| `rerun_subset.zsh <gate dir> <workers> <pytest paths...>` | Rerun demo tests against the installed package of an existing build root. |
| `rerun_gtest.zsh <gate dir> <package> <binary> <n> [gtest args]` | Run one gtest binary of a build root `n` times. |
| `known_flakes.py <file>` | Validate `known-flakes.txt`; prints the substrings. |
| `sigdfl.py <command...>` | `exec` a command with SIGINT and SIGQUIT at their defaults. |
| `pytest-plugin/so101_pytest_worker_temp.py` | Per-xdist-worker TMPDIR inside the registered scratch; loaded with `-p`. |
| `diagnostic-plugins/` | Pytest plugins for diagnosis only; not part of any gate. Not on the gate's `PYTHONPATH`. |

Deleting a gate: after the results are read back, the build root and the scratch directory are deletion candidates; the evidence gate
directory stays. Do not delete the build root of a gate that an image was built from until the template runs for that commit are
finished.
