#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  printf 'usage: %s QUALITY_GATE_SCRIPT\n' "$0" >&2
  exit 2
fi

quality_gate_script="$1"
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

printf 'format %s\n' "$*" >>"${COMMAND_LOG}"
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
  "${commands[0]}" == *"-config-file ${workspace_root}/.clang-tidy"* ]] ||
  fail 'tidy did not receive the strict compilation database arguments'
[[ "${commands[1]}" == "format -i --style=file ${source_file}" ]] ||
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

printf 'PASS: C++ quality gate runs tidy before format and fails closed\n'
