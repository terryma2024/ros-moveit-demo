#!/bin/zsh

set -euo pipefail

readonly script_path="${0:A}"
readonly script_dir="${script_path:h}"
readonly repository_root="${script_dir:h}"
readonly ros_root=/opt/ros2_jazzy
readonly python_path="${ros_root}/.venv/bin/python"
readonly colcon_path="${ros_root}/.venv/bin/colcon"
readonly ros2_script="${ros_root}/install/ros2cli/bin/ros2"
readonly farm_path="${ros_root}/dylib_farm/current"
readonly data_root=/opt/data
readonly temp_root=/tmp
readonly runtime_root="${data_root}/so101"
readonly fork_runtime_root="${runtime_root}/runtime/fork"
readonly fork_install="${fork_runtime_root}/current"
readonly workspace_root="${runtime_root}/workspace"
readonly project_install="${workspace_root}/install"
readonly contract_tool="${script_dir}/so101_macos_runtime_contract.py"
readonly farm_tool="${script_dir}/setup-macos-ros-dylib-farm.zsh"
readonly fork_installer="${script_dir}/install-mujoco-ros2-control.zsh"

fail() {
  print -u2 -- "so101-macos: $1"
  exit 2
}

usage() {
  cat <<'EOF'
Usage:
  scripts/so101-macos.zsh doctor [--base] [--json]
  scripts/so101-macos.zsh prepare
  scripts/so101-macos.zsh launch PACKAGE LAUNCH_FILE [ARG...]
  scripts/so101-macos.zsh run PACKAGE EXECUTABLE [ARG...]

No environment variable is required. ROS_DOMAIN_ID is optional (0-232; default 0).
EOF
}

validated_domain_id() {
  local candidate="${ROS_DOMAIN_ID:-0}"
  [[ "${candidate}" == <-> ]] || fail "ROS_DOMAIN_ID must be an integer from 0 to 232"
  (( candidate >= 0 && candidate <= 232 )) || fail "ROS_DOMAIN_ID must be an integer from 0 to 232"
  print -- "${candidate}"
}

clean_reexec() {
  local internal_command="$1"
  shift
  local domain_id
  domain_id="$(validated_domain_id)"
  exec /usr/bin/env -i \
    HOME="${runtime_root}/home" \
    PATH="${ros_root}/.venv/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
    VIRTUAL_ENV="${ros_root}/.venv" \
    PYTHONNOUSERSITE=1 \
    TMPDIR="${temp_root}" TMP="${temp_root}" TEMP="${temp_root}" \
    ROS_HOME="${runtime_root}/ros-home" \
    ROS_LOG_DIR="${runtime_root}/ros-logs" \
    ROS_DOMAIN_ID="${domain_id}" \
    /bin/zsh -f "${script_path}" "${internal_command}" "$@"
}

source_setup() {
  local setup_file="$1"
  [[ -f "${setup_file}" ]] || fail "missing setup file: ${setup_file}; run scripts/so101-macos.zsh prepare"
  set +u
  source "${setup_file}"
  set -u
}

source_base_ros() {
  source_setup "${ros_root}/install/setup.zsh"
  source_setup "${ros_root}/extra_ws/install/setup.zsh"
}

source_complete_runtime() {
  source_base_ros
  source_setup "${fork_install}/setup.zsh"
  source_setup "${project_install}/setup.zsh"
  export DYLD_LIBRARY_PATH="${farm_path}"
}

case "${1:-}" in
  doctor)
    shift
    clean_reexec __doctor "$@"
    ;;
  prepare)
    shift
    (( $# == 0 )) || fail "prepare does not accept arguments"
    clean_reexec __prepare
    ;;
  launch|run)
    public_command="$1"
    shift
    (( $# >= 2 )) || fail "${public_command} requires PACKAGE and target"
    clean_reexec __execute "${public_command}" "$@"
    ;;
  __doctor)
    shift
    [[ -x "${python_path}" ]] || fail "missing fixed Python: ${python_path}"
    exec "${python_path}" "${contract_tool}" doctor \
      --repo-root "${repository_root}" --domain-id "${ROS_DOMAIN_ID}" "$@"
    ;;
  __prepare)
    shift
    [[ -x "${python_path}" ]] || fail "missing fixed Python: ${python_path}"
    [[ -x "${colcon_path}" ]] || fail "missing fixed colcon: ${colcon_path}"
    "${python_path}" "${contract_tool}" doctor --base --repo-root "${repository_root}"
    mkdir -p \
      "${runtime_root}/home" \
      "${runtime_root}/ros-home" \
      "${runtime_root}/ros-logs" \
      "${fork_runtime_root}/runs" \
      "${workspace_root}"
    source_base_ros
    locked_commit="$(/usr/bin/git -C "${repository_root}/third_party/mujoco_ros2_control" rev-parse HEAD)"
    vendor_extras="${ros_root}/extra_ws/install/share/mujoco_vendor/cmake/mujoco_vendor-extras.cmake"
    [[ -f "${vendor_extras}" ]] || fail "missing MuJoCo vendor metadata: ${vendor_extras}"
    lodepng_commit="$(/usr/bin/sed -nE 's/.*MUJOCO_DEP_VERSION_lodepng[[:space:]]+"([0-9a-f]{40})".*/\1/p' "${vendor_extras}")"
    [[ "${lodepng_commit}" != *[^0-9a-f]* ]] && (( ${#lodepng_commit} == 40 )) ||
      fail "invalid MuJoCo lodepng lock in ${vendor_extras}"
    lodepng_cache="${runtime_root}/runtime/vendor/lodepng/${lodepng_commit}"
    if [[ ! -e "${lodepng_cache}/.git" ]]; then
      legacy_lodepng="${ros_root}/ws_mujoco_ros2_control_fork/build/mujoco_ros2_control/_deps/lodepng-src"
      if /usr/bin/git -C "${legacy_lodepng}" cat-file -e "${lodepng_commit}^{commit}" 2>/dev/null; then
        [[ ! -e "${lodepng_cache}" && ! -L "${lodepng_cache}" ]] ||
          fail "incomplete lodepng cache already exists: ${lodepng_cache}"
        mkdir -p "${lodepng_cache:h}"
        /usr/bin/git clone --shared --no-checkout "${legacy_lodepng}" "${lodepng_cache}"
        /usr/bin/git -C "${lodepng_cache}" checkout --detach "${lodepng_commit}"
      fi
    fi
    if [[ -e "${lodepng_cache}/.git" ]]; then
      export SO101_LODEPNG_SOURCE_DIR="${lodepng_cache}"
    fi
    fork_workspace="${fork_runtime_root}/runs/${locked_commit}"
    built_fork_install="${fork_workspace}/ws_mujoco_ros2_control_fork/install"
    required_fork_header="${built_fork_install}/include/mujoco_ros2_control_plugins/mujoco_ros2_control_plugin_capabilities.hpp"
    fork_commit_marker="${built_fork_install}/share/mujoco_ros2_control/so101-locked-commit.txt"
    installed_fork_commit=""
    if [[ -f "${fork_commit_marker}" ]]; then
      installed_fork_commit="$(<"${fork_commit_marker}")"
    fi
    if [[ ! -f "${required_fork_header}" || "${installed_fork_commit}" != "${locked_commit}" ]]; then
      bootstrap_farm_root="${runtime_root}/runtime/bootstrap-dylib-farm"
      SO101_DYLIB_FARM_ROOT="${bootstrap_farm_root}" \
      SO101_ROS_PREFIXES="${ros_root}/install:${ros_root}/extra_ws/install" \
        "${farm_tool}" >/dev/null
      SO101_WORKSPACE_DIR="${fork_workspace}" \
      SO101_ROS_UNDERLAY="${ros_root}/install" \
      SO101_ROS_DEPENDENCY_OVERLAY="${ros_root}/extra_ws/install" \
      SO101_TEST_DYLIB_FARM="${bootstrap_farm_root}/current" \
      SO101_PYTHON="${python_path}" \
      SO101_COLCON="${colcon_path}" \
      SO101_ROS2="${ros2_script}" \
      SO101_CTEST="$(command -v ctest)" \
        "${fork_installer}"
    fi
    [[ -f "${required_fork_header}" ]] || fail "locked fork install is incomplete: ${required_fork_header}"
    [[ -f "${fork_commit_marker}" && "$(<"${fork_commit_marker}")" == "${locked_commit}" ]] ||
      fail "locked fork validation marker is missing or stale: ${fork_commit_marker}"
    next_fork_link="${fork_runtime_root}/.current-${$}"
    ln -s "${built_fork_install}" "${next_fork_link}"
    mv -fh "${next_fork_link}" "${fork_install}"
    source_setup "${fork_install}/setup.zsh"
    "${colcon_path}" --log-base "${workspace_root}/log" build \
      --base-paths "${repository_root}/src" \
      --build-base "${workspace_root}/build" \
      --install-base "${project_install}" \
      --cmake-clean-cache \
      --packages-select so101_mujoco_support so101_teleop so101_demo_py
    "${farm_tool}"
    export DYLD_LIBRARY_PATH="${farm_path}"
    "${python_path}" "${contract_tool}" doctor --json \
      --repo-root "${repository_root}" --domain-id "${ROS_DOMAIN_ID}"
    ;;
  __execute)
    shift
    (( $# >= 3 )) || fail "internal execute requires command, package, and target"
    [[ -x "${python_path}" ]] || fail "missing fixed Python: ${python_path}"
    "${python_path}" "${contract_tool}" doctor \
      --repo-root "${repository_root}" --domain-id "${ROS_DOMAIN_ID}"
    source_complete_runtime
    exec "${python_path}" "${ros2_script}" "$@"
    ;;
  help|-h|--help|"")
    usage
    ;;
  *)
    usage >&2
    fail "unknown command: $1"
    ;;
esac
