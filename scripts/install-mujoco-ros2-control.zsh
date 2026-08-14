#!/usr/bin/env zsh
set -euo pipefail

readonly installer_path=${0:A}
readonly ros_underlay=${SO101_ROS_UNDERLAY:-/opt/ros/jazzy}
readonly ros_dependency_overlay=${SO101_ROS_DEPENDENCY_OVERLAY:-${ros_underlay}}
readonly -a fork_packages=(
  mujoco_ros2_control_msgs
  mujoco_ros2_control_plugins
  mujoco_ros2_control
)

fail() {
  print -u2 -- "mujoco_ros2_control installer failed: $1"
  return 1
}

source_setup() {
  set +u
  source "$1"
  set -u
}

resolve_project_root() {
  local physical_script_dir
  physical_script_dir=$(cd -- "$(dirname -- "${installer_path}")" && pwd -P)
  project_root=$(cd -- "${physical_script_dir}/.." && pwd -P)
  lock_file=${project_root}/src/so101_demo_py/config/mujoco/dependency-lock.yaml
  [[ -f ${lock_file} ]] || fail "dependency lock is missing: ${lock_file}"

  local -a values
  values=("${(@f)$(python3 - "${lock_file}" <<'PY'
from pathlib import Path
import sys
import yaml

lock = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
if lock.get("schema_version") != 3 or lock.get("provider") != "gitee_fork_submodule":
    raise SystemExit("dependency lock is not schema-3 gitee_fork_submodule")
for value in (
    lock["fork"]["url"],
    lock["fork"]["tag"],
    lock["fork"]["commit"],
    lock["upstream"]["commit"],
    lock["submodule_path"],
    lock["paths"]["workspace_env"],
    lock["paths"]["workspace_default"],
    lock["paths"]["fork_workspace"],
    lock["paths"]["fork_install"],
):
    print(value)
PY
  )}")
  (( ${#values} == 9 )) || fail "dependency lock fields are incomplete"
  fork_url=${values[1]}
  fork_tag=${values[2]}
  fork_commit=${values[3]}
  upstream_commit=${values[4]}
  submodule_path=${values[5]}
  workspace_env=${values[6]}
  workspace_default=${values[7]}
  fork_workspace_relative=${values[8]}
  fork_install_relative=${values[9]}
  [[ ${workspace_env} == SO101_WORKSPACE_DIR ]] || fail "unsupported workspace environment: ${workspace_env}"
  [[ ${workspace_default} == repo_parent ]] || fail "unsupported workspace default: ${workspace_default}"
  [[ ${fork_install_relative} == ${fork_workspace_relative}/install ]] ||
    fail "fork install path must be relative to the fork workspace"
  local configured_workspace=${SO101_WORKSPACE_DIR:-${project_root:h}}
  workspace_dir=$(python3 - "${configured_workspace}" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).expanduser().resolve())
PY
  )
  fork_workspace=${workspace_dir}/${fork_workspace_relative}
  build_base=${fork_workspace}/build
  install_base=${workspace_dir}/${fork_install_relative}
  log_base=${fork_workspace}/log
  source_dir=${project_root}/${submodule_path}
  build_source_dir=${fork_workspace}/src/mujoco_ros2_control
}

initialize_submodule() {
  git -C "${project_root}" submodule update --init -- "${submodule_path}"
}

verify_superproject_gitlink() {
  local superproject_root
  superproject_root=$(git -C "${project_root}" rev-parse --show-toplevel 2>/dev/null) ||
    fail "project root is not a Git superproject: ${project_root}"
  [[ ${superproject_root:A} == ${project_root:A} ]] ||
    fail "installer checkout is not the superproject root: ${project_root}"

  local tree_entry
  tree_entry=$(git -C "${project_root}" ls-tree HEAD -- "${submodule_path}") ||
    fail "could not read superproject gitlink: ${submodule_path}"
  [[ -n ${tree_entry} ]] || fail "superproject has no gitlink for ${submodule_path}"

  local recorded_mode recorded_type recorded_commit recorded_path
  read -r recorded_mode recorded_type recorded_commit recorded_path <<< "${tree_entry}"
  [[ ${recorded_mode} == 160000 && ${recorded_type} == commit ]] ||
    fail "superproject must record ${submodule_path} as mode 160000"
  [[ ${recorded_commit} == ${fork_commit} ]] ||
    fail "superproject gitlink commit ${recorded_commit} does not match lock ${fork_commit}"
  gitlink_commit=${recorded_commit}
}

verify_source_identity() {
  [[ -e ${source_dir}/.git ]] || fail "submodule is not initialized: ${submodule_path}"
  local configured_url
  configured_url=$(git config -f "${project_root}/.gitmodules" --get "submodule.${submodule_path}.url") ||
    fail "submodule URL is missing from .gitmodules"
  [[ ${configured_url} == ${fork_url} ]] || fail "unapproved submodule URL: ${configured_url}"
  local origin_url
  origin_url=$(git -C "${source_dir}" remote get-url origin) || fail "submodule origin is unavailable"
  [[ ${origin_url} == ${fork_url} ]] || fail "unapproved fork origin: ${origin_url}"

  local dirty_status
  dirty_status=$(git -C "${source_dir}" status --porcelain --untracked-files=all)
  [[ -z ${dirty_status} ]] || fail "dirty submodule source is not buildable"

  local observed_commit
  observed_commit=$(git -C "${source_dir}" rev-parse HEAD)
  [[ ${observed_commit} == ${fork_commit} && ${observed_commit} == ${gitlink_commit} ]] ||
    fail "wrong fork commit: ${observed_commit} (expected lock/gitlink ${fork_commit})"
  git -C "${source_dir}" merge-base --is-ancestor "${upstream_commit}" HEAD ||
    fail "official 0.0.3 commit is not an ancestor of fork HEAD"
  local tagged_commit
  tagged_commit=$(git -C "${source_dir}" rev-list -n 1 "${fork_tag}") ||
    fail "fork release tag is unavailable: ${fork_tag}"
  [[ ${tagged_commit} == ${fork_commit} ]] || fail "fork release tag does not resolve to locked commit"
}

prepare_build_source() {
  if [[ ! -e ${build_source_dir}/.git ]]; then
    mkdir -p "${build_source_dir:h}"
    git clone --shared --no-checkout "${source_dir}" "${build_source_dir}"
    git -C "${build_source_dir}" checkout --detach "${fork_commit}"
  fi
  [[ $(git -C "${build_source_dir}" rev-parse HEAD) == ${fork_commit} ]] ||
    fail "build source is not at locked commit: ${build_source_dir}"
  local build_source_changes
  build_source_changes=$(git -C "${build_source_dir}" status --porcelain --untracked-files=all)
  [[ -z ${build_source_changes} ]] ||
    fail "build source must be clean at locked fork commit: ${build_source_dir}"
}

build_and_test_overlay() {
  source_setup "${ros_underlay}/setup.zsh"
  if [[ ${ros_dependency_overlay:A} != ${ros_underlay:A} ]]; then
    source_setup "${ros_dependency_overlay}/setup.zsh"
  fi
  colcon --log-base "${log_base}" build \
    --base-paths "${build_source_dir}" \
    --build-base "${build_base}" \
    --install-base "${install_base}" \
    --merge-install \
    --cmake-clean-cache \
    --cmake-args -DFETCHCONTENT_UPDATES_DISCONNECTED=ON \
    --packages-select "${fork_packages[@]}"
  source_setup "${install_base}/setup.zsh"
  colcon --log-base "${log_base}" test \
    --base-paths "${build_source_dir}" \
    --build-base "${build_base}" \
    --install-base "${install_base}" \
    --merge-install \
    --packages-select "${fork_packages[@]}" \
    --event-handlers console_direct+
  colcon test-result --test-result-base "${build_base}" --verbose
}

verify_installed_overlay() {
  source_setup "${ros_underlay}/setup.zsh"
  if [[ ${ros_dependency_overlay:A} != ${ros_underlay:A} ]]; then
    source_setup "${ros_dependency_overlay}/setup.zsh"
  fi
  source_setup "${install_base}/setup.zsh"
  local package_name
  for package_name in "${fork_packages[@]}"; do
    [[ $(ros2 pkg prefix "${package_name}") == ${install_base} ]] ||
      fail "installed prefix mismatch for ${package_name}"
  done
  [[ $(ros2 pkg prefix mujoco_vendor) == ${ros_dependency_overlay} ]] ||
    fail "mujoco_vendor must continue to resolve from ${ros_dependency_overlay}"
  local interface_name
  for interface_name in \
    mujoco_ros2_control_msgs/msg/ViewerCamera \
    mujoco_ros2_control_msgs/srv/SetViewerCamera \
    mujoco_ros2_control_msgs/srv/GetViewerCamera \
    mujoco_ros2_control_msgs/srv/ResetWorld \
    mujoco_ros2_control_msgs/srv/SetPause \
    mujoco_ros2_control_msgs/srv/StepSimulation; do
    ros2 interface show "${interface_name}" >/dev/null
  done
  python3 - "${lock_file}" "${install_base}" <<'PY'
from pathlib import Path
import platform
import sys
import yaml

lock = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
prefix = Path(sys.argv[2])
suffix = ".dylib" if platform.system() == "Darwin" else ".so"
required = [
    path.removesuffix(".so") + suffix if path.endswith(".so") else path
    for path in lock["required_files"]
]
missing = [path for path in required if not (prefix / path).is_file()]
if missing:
    raise SystemExit("missing installed files: " + ", ".join(missing))
PY
}

main() {
  local init_submodule=false
  while (( $# > 0 )); do
    case $1 in
      --init-submodule) init_submodule=true ;;
      *) print -u2 -- "unknown argument: $1"; return 2 ;;
    esac
    shift
  done

  resolve_project_root
  verify_superproject_gitlink
  if [[ ! -e ${source_dir}/.git ]]; then
    if [[ ${init_submodule} == true ]]; then
      initialize_submodule
    else
      fail "submodule is not initialized; rerun with --init-submodule"
    fi
  fi
  verify_source_identity
  prepare_build_source
  build_and_test_overlay
  verify_installed_overlay
}

main "$@"
