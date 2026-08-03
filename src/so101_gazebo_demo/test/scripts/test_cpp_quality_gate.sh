#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 2 ]]; then
  printf 'usage: %s QUALITY_GATE_SCRIPT QUALITY_GATE_CMAKE_MODULE\n' "$0" >&2
  exit 2
fi

quality_gate_script="$(realpath "$1")"
quality_gate_module="$(realpath "$2")"
test_dir="$(mktemp -d)"
trap 'rm -rf "${test_dir}"' EXIT

workspace_root="${test_dir}/workspace"
compilation_database_dir="${test_dir}/build"
fake_bin="${test_dir}/bin"
command_log="${test_dir}/commands.log"
source_file="${workspace_root}/src/example.cpp"
mkdir -p "${workspace_root}/src" "${compilation_database_dir}" "${fake_bin}"
touch "${workspace_root}/.clang-tidy" "${workspace_root}/.clang-format" "${source_file}"
printf '[]\n' >"${compilation_database_dir}/compile_commands.json"

cat >"${fake_bin}/run-clang-tidy" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf 'tidy %s\n' "$*" >>"${COMMAND_LOG}"
exit "${FAKE_TIDY_EXIT_CODE:-0}"
EOF

cat >"${fake_bin}/clang-format" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf 'format argc=%s args=' "$#" >>"${COMMAND_LOG}"
printf '<%s>' "$@" >>"${COMMAND_LOG}"
printf '\n' >>"${COMMAND_LOG}"
EOF
chmod +x "${fake_bin}/run-clang-tidy" "${fake_bin}/clang-format"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

run_gate() {
  COMMAND_LOG="${command_log}" \
    FAKE_TIDY_EXIT_CODE="${1:-0}" \
    cmake \
    -DRUN_CLANG_TIDY_EXECUTABLE="${fake_bin}/run-clang-tidy" \
    -DCLANG_FORMAT_EXECUTABLE="${fake_bin}/clang-format" \
    -DCOMPILATION_DATABASE_DIR="${compilation_database_dir}" \
    -DWORKSPACE_ROOT="${workspace_root}" \
    -DQUALITY_SOURCE_FILES="${source_file}" \
    -P "${quality_gate_script}"
}

run_gate
mapfile -t commands <"${command_log}"
[[ "${#commands[@]}" -eq 2 ]] || fail 'successful gate did not run exactly tidy then format'
[[ "${commands[0]}" == *'tidy -p '* &&
  "${commands[0]}" == *"${compilation_database_dir}"* &&
  "${commands[0]}" == *'-warnings-as-errors='* &&
  "${commands[0]}" == *"-config-file ${workspace_root}/.clang-tidy"* &&
  "${commands[0]}" == *"${source_file}"* ]] ||
  fail 'tidy did not receive the strict compilation database arguments'
[[ "${commands[1]}" == "format argc=3 args=<-i><--style=file><${source_file}>" ]] ||
  fail 'format did not receive repository style arguments'

: >"${command_log}"
if run_gate 1 >/dev/null 2>&1; then
  fail 'gate succeeded after clang-tidy failed'
fi
mapfile -t commands <"${command_log}"
[[ "${#commands[@]}" -eq 1 && "${commands[0]}" == tidy* ]] ||
  fail 'format ran after clang-tidy failure'

missing_input_output="${test_dir}/missing-input-output.log"
if COMMAND_LOG="${command_log}" cmake \
  -DRUN_CLANG_TIDY_EXECUTABLE="${fake_bin}/run-clang-tidy" \
  -DCLANG_FORMAT_EXECUTABLE="${fake_bin}/clang-format" \
  -DCOMPILATION_DATABASE_DIR="${compilation_database_dir}" \
  -DWORKSPACE_ROOT="${workspace_root}" \
  -P "${quality_gate_script}" >"${missing_input_output}" 2>&1
then
  fail 'gate accepted missing source files'
fi
grep -Fq 'QUALITY_SOURCE_FILES' "${missing_input_output}" ||
  fail 'missing source files did not produce a clear diagnostic'

fixture_root="${test_dir}/fixture"
fixture_build_dir="${test_dir}/fixture-build"
mkdir -p "${fixture_root}/src" "${fixture_root}/include"
touch "${fixture_root}/.clang-tidy" "${fixture_root}/.clang-format"
printf 'int example() { return 1; }\n' >"${fixture_root}/src/example.cpp"
printf 'int other() { return 2; }\n' >"${fixture_root}/src/other.cpp"
printf 'generated header\n' >"${fixture_root}/include/generated.hpp"
cat >"${fixture_root}/CMakeLists.txt" <<EOF
cmake_minimum_required(VERSION 3.8)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
project(cpp_quality_gate_fixture LANGUAGES CXX)
include("${quality_gate_module}")
add_library(example STATIC src/example.cpp src/other.cpp)
set(FIXTURE_RUN_CLANG_TIDY "${fake_bin}/run-clang-tidy" CACHE FILEPATH "")
set(FIXTURE_CLANG_FORMAT "${fake_bin}/clang-format" CACHE FILEPATH "")
so101_gazebo_add_cpp_quality_gate(
  WORKSPACE_ROOT "\${CMAKE_CURRENT_SOURCE_DIR}"
  SOURCE_ROOT "\${CMAKE_CURRENT_SOURCE_DIR}"
  RUN_CLANG_TIDY_EXECUTABLE "\${FIXTURE_RUN_CLANG_TIDY}"
  CLANG_FORMAT_EXECUTABLE "\${FIXTURE_CLANG_FORMAT}"
  EXCLUDE_FILES include/generated.hpp
  TARGETS example
)
EOF

cmake -S "${fixture_root}" -B "${fixture_build_dir}" >/dev/null
[[ -f "${fixture_build_dir}/compile_commands.json" ]] ||
  fail 'quality-gate CMake wiring did not export compile_commands.json'
cmake --build "${fixture_build_dir}" --target help >"${test_dir}/target-help.log"
grep -Fq 'cpp_quality_gate' "${test_dir}/target-help.log" ||
  fail 'quality-gate CMake wiring did not define cpp_quality_gate'

: >"${command_log}"
COMMAND_LOG="${command_log}" cmake --build "${fixture_build_dir}" --target example \
  >/dev/null
mapfile -t commands <"${command_log}"
[[ "${#commands[@]}" -eq 2 && "${commands[0]}" == tidy* &&
  "${commands[1]}" == *'format argc=4'* &&
  "${commands[1]}" == *"<${fixture_root}/src/example.cpp>"* &&
  "${commands[1]}" == *"<${fixture_root}/src/other.cpp>"* ]] ||
  fail 'target compilation did not run tidy then format first'
[[ "${commands[0]}" != *"${fixture_root}/include/generated.hpp"* &&
  "${commands[1]}" != *"${fixture_root}/include/generated.hpp"* ]] ||
  fail 'explicitly excluded generated header reached the quality tools'

sleep 1
touch "${fixture_root}/src/example.cpp"
COMMAND_LOG="${command_log}" cmake --build "${fixture_build_dir}" --target example \
  >/dev/null
mapfile -t commands <"${command_log}"
[[ "${#commands[@]}" -eq 4 && "${commands[2]}" == tidy* &&
  "${commands[3]}" == format* ]] ||
  fail 'touching a C++ source did not rerun the quality gate'

missing_tool_build_dir="${test_dir}/missing-tool-build"
missing_tool_output="${test_dir}/missing-tool-output.log"
if cmake -S "${fixture_root}" -B "${missing_tool_build_dir}" \
  -DFIXTURE_RUN_CLANG_TIDY="${test_dir}/does-not-exist" \
  -DFIXTURE_CLANG_FORMAT="${fake_bin}/clang-format" >"${missing_tool_output}" 2>&1
then
  fail 'CMake accepted a missing clang-tidy executable'
fi
grep -Fq 'RUN_CLANG_TIDY_EXECUTABLE' "${missing_tool_output}" ||
  fail 'missing clang-tidy did not produce a clear CMake diagnostic'

printf 'PASS: C++ quality gate runs tidy before format and fails closed\n'
