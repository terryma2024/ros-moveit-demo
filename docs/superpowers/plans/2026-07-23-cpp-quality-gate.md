# C++ Quality Gate Implementation Plan

> **For implementation:** use `superpowers:executing-plans` and execute this plan task-by-task.

**Goal:** Make every normal CMake/colcon build of `panda_gazebo_demo` run a strict C++ quality gate—clang-tidy with zero diagnostics, then clang-format using the repository `.clang-format`—before compiling C++ targets.

**Architecture:** Keep the ordering in a CMake script invoked by a stamp-producing custom command.  The CMake package wiring discovers required executables, provides cache overrides for deterministic tests, collects only package-owned C/C++ files, and makes each production C++ target depend on the gate.  The script uses `run-clang-tidy` against the configured compilation database and only formats after tidy has succeeded.

**Tech Stack:** CMake 3.8+, colcon/ament_cmake, clang-tidy/run-clang-tidy, clang-format, Bash test fixtures.

---

### Task 1: Add a testable ordered quality-gate script

**Files:**

- Create: `src/panda_gazebo_demo/cmake/run_cpp_quality_gate.cmake`
- Create: `src/panda_gazebo_demo/test/scripts/test_cpp_quality_gate.sh`

**Step 1: Write the failing tests**

Create a Bash test that creates a temporary source tree, compilation database, and fake `run-clang-tidy`/`clang-format` executables.  Have the fake commands append their names and arguments to a log.  Invoke the CMake script with explicit executable, compilation-database, workspace-root, and source-file inputs.

Cover these cases:

1. tidy succeeds: log order is exactly `tidy` then `format`; tidy receives `-p`, the package build directory, `-warnings-as-errors=*`, the root `.clang-tidy`, and the package source-file list; format receives `-i` and `--style=file`.
2. tidy fails: script exits nonzero and the log contains only `tidy`—format must never run.
3. required input or executable is missing: script exits nonzero with a clear message.

Run: `bash src/panda_gazebo_demo/test/scripts/test_cpp_quality_gate.sh`

Expected: FAIL because the script does not yet exist.

**Step 2: Implement the minimal script**

Implement `run_cpp_quality_gate.cmake` to:

- require `RUN_CLANG_TIDY_EXECUTABLE`, `CLANG_FORMAT_EXECUTABLE`, `COMPILATION_DATABASE_DIR`, `WORKSPACE_ROOT`, and a nonempty `QUALITY_SOURCE_FILES` list;
- verify that `${COMPILATION_DATABASE_DIR}/compile_commands.json`, `${WORKSPACE_ROOT}/.clang-tidy`, and `${WORKSPACE_ROOT}/.clang-format` exist;
- run `run-clang-tidy -p <build-dir> -warnings-as-errors=* -config-file <root/.clang-tidy> <package-source-files>` and fail immediately on a nonzero exit code, so dependency compilation-database entries are excluded;
- only after success, run `clang-format -i --style=file` over the supplied source list, so style discovery reaches the repository root;
- fail closed on any command failure and emit concise status messages.

Do not invoke `ament_uncrustify`, and do not add an automatic ament-uncrustify reformat path.

**Step 3: Run the focused test**

Run: `bash src/panda_gazebo_demo/test/scripts/test_cpp_quality_gate.sh`

Expected: PASS.

**Step 4: Commit**

```bash
git add src/panda_gazebo_demo/cmake/run_cpp_quality_gate.cmake \
  src/panda_gazebo_demo/test/scripts/test_cpp_quality_gate.sh
git commit -m "test: cover ordered C++ quality gate"
```

### Task 2: Wire the gate into package CMake targets

**Files:**

- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Modify: `src/panda_gazebo_demo/test/scripts/test_cpp_quality_gate.sh`

**Step 1: Extend the failing test**

Add checks that configure a minimal CMake fixture using the package wiring semantics with fake tool paths.  Assert:

1. configuration exports `compile_commands.json`;
2. `cpp_quality_gate` is a build target;
3. building a representative production C++ target runs tidy then format before the compile command;
4. touching a package C++ source reruns the stamp-producing gate;
5. configuration without either required tool fails with an actionable diagnostic.

Run: `bash src/panda_gazebo_demo/test/scripts/test_cpp_quality_gate.sh`

Expected: FAIL because CMake does not yet define the gate.

**Step 2: Implement CMake wiring**

Near the start of the package CMake file:

- set `CMAKE_EXPORT_COMPILE_COMMANDS ON`;
- derive the workspace root as two parent directories above the package source directory and validate its `.clang-tidy` and `.clang-format` files;
- expose cache variables `RUN_CLANG_TIDY_EXECUTABLE` and `CLANG_FORMAT_EXECUTABLE`; use `find_program` defaults and produce a fatal configure error if either is unavailable;
- collect only package-owned C/C++ implementation, header, and C++ test files under `src/`, `include/`, and `test/`, excluding generated/build/install/log paths and non-C++ assets.

Define a custom command that produces `${CMAKE_CURRENT_BINARY_DIR}/cpp_quality_gate.stamp`, invokes `cmake -P cmake/run_cpp_quality_gate.cmake` with the collected files and paths, and touches the stamp only after success.  Make `cpp_quality_gate` depend on that stamp and make the stamp depend on its script, configs, source files, and compilation database.  Attach `cpp_quality_gate` as a dependency of every production C++ library and executable:

- `pick_place_core`
- `pick_place_ros_adapters`
- `pick_place_state_machine`
- `gazebo_attachment_state_relay`
- `reset_moveit_world`

Keep lint targets and all existing build/test registrations intact.  Do not modify the root `.clang-tidy`, root `.clang-format`, or IDE configuration.

**Step 3: Run focused verification**

Run: `bash src/panda_gazebo_demo/test/scripts/test_cpp_quality_gate.sh`

Expected: PASS.

Run: `cmake -S src/panda_gazebo_demo -B /tmp/panda_quality_gate_missing_tools -DBUILD_TESTING=OFF`

Expected: FAIL with the documented missing-tool diagnostic on machines without the required toolchain.

**Step 4: Commit**

```bash
git add src/panda_gazebo_demo/CMakeLists.txt \
  src/panda_gazebo_demo/test/scripts/test_cpp_quality_gate.sh
git commit -m "build: gate C++ compilation on tidy and format"
```

### Task 3: Run the real gate and remediate project diagnostics

**Files:**

- Modify only project-owned C/C++ files reported by the real clang-tidy/clang-format run.
- Modify: `src/panda_gazebo_demo/test/scripts/test_cpp_quality_gate.sh` only if a newly observed tool-interface difference requires a portable regression case.

**Step 1: Establish RED with the real toolchain**

Install or make the configured LLVM toolchain available outside this repository if it is absent.  Do not vendor tool binaries or weaken the gate.  Then run:

```bash
colcon build --packages-select panda_gazebo_demo --event-handlers console_direct+
```

Expected: initially fail on clang-tidy diagnostics or formatting changes that expose compile errors; capture the exact diagnostics.

**Step 2: Apply minimal project-only fixes**

Resolve every clang-tidy diagnostic in `panda_gazebo_demo` without disabling checks, adding blanket suppressions, or modifying dependencies.  Repeat the build until clang-tidy exits with zero diagnostics.  Allow the gate to run clang-format using the root configuration; inspect its diff and keep only project source/test formatting changes.

**Step 3: Verify the complete build and test path**

Run:

```bash
colcon build --packages-select panda_gazebo_demo --event-handlers console_direct+
colcon test --packages-select panda_gazebo_demo --event-handlers console_direct+
colcon test-result --all --verbose
ament_uncrustify --check src/panda_gazebo_demo/include src/panda_gazebo_demo/src src/panda_gazebo_demo/test
git diff --check
```

Expected: build passes only after tidy has zero diagnostics and format has completed; package tests pass; uncrustify is read-only; `git diff --check` is clean.  If existing unrelated lint failures remain, report them separately with evidence and do not mask them.

**Step 4: Commit**

```bash
git add src/panda_gazebo_demo
git commit -m "style: satisfy C++ quality gate"
```

### Task 4: Final independent review and handoff

**Files:**

- Review: `src/panda_gazebo_demo/CMakeLists.txt`
- Review: `src/panda_gazebo_demo/cmake/run_cpp_quality_gate.cmake`
- Review: `src/panda_gazebo_demo/test/scripts/test_cpp_quality_gate.sh`

**Step 1: Inspect the final diff and build graph**

Verify that each listed production target depends on `cpp_quality_gate`, formatting cannot run after tidy failure, the root configs are used, and no `ament_uncrustify --reformat` invocation was introduced.

**Step 2: Re-run final verification**

Run the Task 3 verification commands again, plus:

```bash
git status --short
git log --oneline -3
```

**Step 3: Report**

Report the commits, zero-diagnostic evidence, format/build/test outcomes, missing external tooling if it remains a real machine blocker, and final worktree status.  Do not push.
