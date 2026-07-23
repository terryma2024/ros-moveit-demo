# C++ Quality Gate Design

## Goal

Make normal CMake/colcon C++ builds run a repository-local quality gate before compilation:
clang-tidy must report zero diagnostics, then clang-format applies the root `.clang-format` rules,
then and only then may compilation continue.

## Scope

The gate applies to the C/C++ sources owned by `panda_gazebo_demo`. It uses the root `.clang-tidy`
and `.clang-format` files and does not change their contents. It does not invoke
`ament_uncrustify --reformat`, consistent with the repository rule.

## Build ordering

At CMake configure time, enable `CMAKE_EXPORT_COMPILE_COMMANDS` so clang-tidy receives the exact
ROS/MoveIt compilation flags. The package creates one `cpp_quality_gate` custom target, and its
normal build targets depend on it.

The target runs in this strict order:

1. `run-clang-tidy` reads the package compilation database and repository `.clang-tidy`, with
   warnings treated as errors. It receives the package-owned C/C++ source list explicitly, so
   compilation-database entries belonging to ROS, GTest, or other dependencies are never linted.
   Any project diagnostic exits nonzero and stops the build before formatting or compilation.
2. `clang-format -i --style=file` processes only tracked package C/C++ headers and sources. The
   tool discovers the workspace root `.clang-format` through its parent directories.
3. CMake compiles the potentially reformatted sources.

Formatting runs only after zero clang-tidy diagnostics, so formatting never obscures an outstanding
analysis failure. clang-tidy is not auto-fixed: its diagnostics require deliberate source changes,
then a new quality-gate invocation.

## File selection and portability

CMake discovers `clang-format` and `run-clang-tidy` during configuration. If either is unavailable,
configuration fails with a clear error instead of silently omitting the gate. CMake gathers package
files with C/C++ extensions from `include/`, `src/`, and `test/`, excluding generated build/install/
log paths by construction.

The custom command is marked with a stamp output so a single build invocation runs it once even when
multiple C++ targets depend on it. Source changes invalidate the stamp. The compile database is a
dependency of the tidy command.

## Developer workflow

`colcon build --packages-select panda_gazebo_demo` automatically runs the gate. Developers can
also invoke `cmake --build build/panda_gazebo_demo --target cpp_quality_gate` to repair diagnostics
and inspect formatting before a complete build. The gate's diagnostics and command output stay in
the standard build log.

## Test strategy

Add a CMake-level regression test that configures the package and verifies that `cpp_quality_gate`
is a target and is a dependency of C++ build targets. Add a script-level test with fake
`run-clang-tidy` and `clang-format` executables to assert ordering, that a tidy nonzero exit blocks
format/compile, and that a zero tidy exit runs format before compilation. Run complete package
tests, read-only uncrustify, and `git diff --check`.
