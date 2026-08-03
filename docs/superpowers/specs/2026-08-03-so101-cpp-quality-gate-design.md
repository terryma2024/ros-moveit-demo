# SO-101 C++ Quality Gate Design

## Goal

Give `so101_gazebo_demo` the same mandatory C++ quality gate used by
`panda_gazebo_demo`. Every production C++ target must depend on a gate that
runs clang-tidy with warnings promoted to errors and then applies the
workspace clang-format configuration to all package C/C++ production and test
sources.

## Reference behavior

The implementation mirrors these canonical files:

- `src/panda_gazebo_demo/cmake/cpp_quality_gate.cmake`
- `src/panda_gazebo_demo/cmake/run_cpp_quality_gate.cmake`

The SO-101 copy keeps the same validation, source discovery, manifest, stamp,
dependency, clang-tidy, and clang-format behavior. Only package-specific names
and target lists change.

## CMake integration

`src/so101_gazebo_demo/CMakeLists.txt` will:

1. enable `CMAKE_EXPORT_COMPILE_COMMANDS`;
2. resolve the workspace root from the package source directory;
3. require `run-clang-tidy` and `clang-format`, accepting the same versioned
   executable names as Panda;
4. include the SO-101 quality-gate module;
5. attach the gate to every production C++ library and executable owned by the
   package;
6. register a contract test for the two CMake modules under `BUILD_TESTING`.

The quality gate will not be attached to generated Web assets or Python-only
targets. Test C/C++ files remain inputs to the gate, matching Panda behavior.

## Execution semantics

The gate runs `run-clang-tidy` with the package build directory's
`compile_commands.json`, the repository `.clang-tidy`, and
`-warnings-as-errors=*`. If clang-tidy fails, the build stops before formatting.

After a clean clang-tidy run, `clang-format -i --style=file` formats all
discovered SO-101 C/C++ files using the repository `.clang-format`. These
formatting changes are intentional working-tree changes and will be reported;
they will not be silently discarded or committed.

The stamp depends on the scripts, root configuration, compilation database,
source manifest, and all discovered C/C++ files. A relevant change therefore
invalidates and reruns the gate.

## Test strategy

1. Add the adapted Panda shell contract test first and run it against the
   absent SO-101 modules to obtain RED.
2. Add the two CMake modules and CMake integration, then rerun the contract test
   for GREEN.
3. Configure/build `so101_gazebo_demo` so the real gate executes.
4. If the gate reports findings, diagnose each class from its first failing
   boundary and apply only explicit targeted fixes; do not use
   `ament_uncrustify --reformat`.
5. Rebuild and run the package test suite, then run `git diff --check` and
   inspect all quality-gate and formatter changes.

## Safety and scope

The work does not start, stop, or interact with Gazebo, MoveIt, controllers, or
the Teleop service. Existing live processes remain untouched. Existing user
changes are preserved. Any formatter output is reviewed as part of this task
and is never reverted merely to obtain a clean tree.
