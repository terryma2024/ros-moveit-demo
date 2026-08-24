#!/usr/bin/env zsh
set -euo pipefail

readonly installer_path=${0:A}
readonly mujoco_commit=e55fff5dea6f1d5dd7963ca52eecc41d05ad0922
readonly patch_sha256=aa506e126cf8bec3bcc60a961fbe457e056d2aeb1838bb6c67c7584d7ac5264e
readonly patched_glfw_sha256=98dfb1e3a0ba29516f0ed9f6876b82089ad69bc60f2dd17c67e0eeea648fee3c

fail() {
  print -u2 -- "mujoco_vendor macOS installer failed: $1"
  return 1
}

sha256_file() {
  python3 - "$1" <<'PY'
from hashlib import sha256
from pathlib import Path
import sys

print(sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
}

source_setup() {
  set +u
  source "$1"
  set -u
}

resolve_paths() {
  local physical_script_dir
  physical_script_dir=$(cd -- "$(dirname -- "${installer_path}")" && pwd -P)
  project_root=$(cd -- "${physical_script_dir}/.." && pwd -P)
  patch_file=${project_root}/tools/mujoco_vendor_macos/patches/mujoco-3.4.0-glfw-no-primary-monitor.patch
  vendor_package=${project_root}/tools/mujoco_vendor_macos

  ros_workspace=${SO101_ROS_WORKSPACE:-${SO101_ROS_ROOT:-${HOME}/ros2_jazzy}}
  ros_underlay=${SO101_ROS_UNDERLAY:-/opt/ros/jazzy}
  colcon_command=${SO101_COLCON:-${ros_workspace}/.venv/bin/colcon}
  python_command=${SO101_PYTHON:-${ros_workspace}/.venv/bin/python}
  authority_source=${SO101_MUJOCO_SOURCE_ROOT:-${ros_workspace}/extra_ws/src/mujoco}
  vendor_workspace=${SO101_MUJOCO_VENDOR_WORKSPACE:-${ros_workspace}/mujoco_vendor_macos_ws}
  install_base=${SO101_MUJOCO_VENDOR_INSTALL_PREFIX:-${ros_workspace}/extra_ws/install}
  prepared_source=${vendor_workspace}/src/mujoco
  core_build=${vendor_workspace}/build/mujoco
  vendor_build=${vendor_workspace}/build/mujoco_vendor
  stage_root=${vendor_workspace}/mujoco_stage
  log_base=${vendor_workspace}/log
}

verify_inputs() {
  [[ $(uname -s) == Darwin ]] || fail "this installer is only supported on macOS"
  [[ -x ${colcon_command} ]] || fail "colcon is not executable: ${colcon_command}"
  [[ -x ${python_command} ]] || fail "Python is not executable: ${python_command}"
  "${python_command}" -c "import catkin_pkg" || fail "Python cannot import catkin_pkg: ${python_command}"
  [[ -f ${patch_file} ]] || fail "patch is missing: ${patch_file}"
  local observed_patch_sha256
  observed_patch_sha256=$(sha256_file "${patch_file}")
  [[ ${observed_patch_sha256} == ${patch_sha256} ]] ||
    fail "patch SHA-256 mismatch: ${observed_patch_sha256}"

  [[ -e ${authority_source}/.git ]] || fail "MuJoCo authority is not a Git checkout: ${authority_source}"
  [[ $(git -C "${authority_source}" rev-parse HEAD) == ${mujoco_commit} ]] ||
    fail "MuJoCo authority is not pinned to ${mujoco_commit}"
  local authority_changes
  authority_changes=$(git -C "${authority_source}" status --porcelain --untracked-files=all)
  [[ -z ${authority_changes} ]] || fail "MuJoCo authority must be clean: ${authority_source}"
}

prepare_source() {
  if [[ ! -e ${prepared_source}/.git ]]; then
    mkdir -p "${prepared_source:h}"
    git clone --shared --no-checkout "${authority_source}" "${prepared_source}"
    git -C "${prepared_source}" checkout --detach "${mujoco_commit}"
  fi

  [[ $(git -C "${prepared_source}" rev-parse HEAD) == ${mujoco_commit} ]] ||
    fail "prepared source is not pinned to ${mujoco_commit}: ${prepared_source}"

  local prepared_changes
  prepared_changes=$(git -C "${prepared_source}" status --porcelain --untracked-files=all)
  if [[ -z ${prepared_changes} ]]; then
    git -C "${prepared_source}" apply --unidiff-zero --check "${patch_file}"
    git -C "${prepared_source}" apply --unidiff-zero "${patch_file}"
    prepared_changes=$(git -C "${prepared_source}" status --porcelain --untracked-files=all)
  fi
  [[ ${prepared_changes} == " M simulate/glfw_adapter.cc" ]] ||
    fail "prepared source has unexpected changes: ${prepared_changes}"
  [[ $(sha256_file "${prepared_source}/simulate/glfw_adapter.cc") == ${patched_glfw_sha256} ]] ||
    fail "prepared GLFW source does not match the validated patched bytes"
}

build_core() {
  cmake -S "${prepared_source}" -B "${core_build}" --fresh \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${stage_root}" \
    -DMUJOCO_BUILD_EXAMPLES=OFF \
    -DMUJOCO_BUILD_SIMULATE=OFF \
    -DMUJOCO_BUILD_TESTS=OFF
  cmake --build "${core_build}" --target install --parallel
}

build_vendor_package() {
  source_setup "${ros_underlay}/setup.zsh"
  PATH="${python_command:h}:${PATH}" "${colcon_command}" --log-base "${log_base}" build \
    --base-paths "${vendor_package}" \
    --build-base "${vendor_build}" \
    --install-base "${install_base}" \
    --merge-install \
    --cmake-clean-cache \
    --packages-select mujoco_vendor \
    --event-handlers console_direct+ \
    --cmake-args \
      -DCMAKE_BUILD_TYPE=Release \
      -DPython3_EXECUTABLE="${python_command}" \
      -DMUJOCO_STAGE_ROOT="${stage_root}" \
      -DMUJOCO_SOURCE_ROOT="${prepared_source}"
}

verify_install() {
  local installed_glfw=${install_base}/opt/mujoco_vendor/include/simulate/glfw_adapter.cc
  [[ -f ${installed_glfw} ]] || fail "installed GLFW source is missing: ${installed_glfw}"
  [[ $(sha256_file "${installed_glfw}") == ${patched_glfw_sha256} ]] ||
    fail "installed GLFW source does not match the validated patched bytes"
  [[ -f ${install_base}/opt/mujoco_vendor/lib/libmujoco.dylib ]] ||
    fail "installed MuJoCo dylib is missing"
  [[ -f ${install_base}/share/mujoco_vendor/cmake/mujoco_vendorConfig.cmake ]] ||
    fail "installed mujoco_vendor CMake config is missing"
}

main() {
  local prepare_only=false
  while (( $# > 0 )); do
    case $1 in
      --prepare-only) prepare_only=true ;;
      *) print -u2 -- "unknown argument: $1"; return 2 ;;
    esac
    shift
  done

  resolve_paths
  verify_inputs
  prepare_source
  if [[ ${prepare_only} == true ]]; then
    print -- "${prepared_source}"
    return 0
  fi
  build_core
  build_vendor_package
  verify_install
  print -- "${install_base}"
}

main "$@"
