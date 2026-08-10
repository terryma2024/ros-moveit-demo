#!/usr/bin/env bash
set -eo pipefail

upstream_url="https://github.com/ros-controls/mujoco_ros2_control"
upstream_commit="35ba8174b62d9560093614f981a3d4b978a96036"
dependency_root="/data/work/ws_mujoco_ros2_control_003"
source_dir="${dependency_root}/src/mujoco_ros2_control"
install_dir="${dependency_root}/install"
package_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
patch_file="${package_root}/patches/mujoco_ros2_control-0.0.3-reset-hook.patch"

source /opt/ros/jazzy/setup.bash
set -u

if [[ ! -d "${source_dir}/.git" ]]; then
  mkdir -p "${dependency_root}/src"
  git clone --no-checkout "${upstream_url}" "${source_dir}"
  git -C "${source_dir}" fetch origin "${upstream_commit}"
  git -C "${source_dir}" checkout --detach FETCH_HEAD
fi

[[ "$(git -C "${source_dir}" remote get-url origin)" == "${upstream_url}" ]]
[[ "$(git -C "${source_dir}" rev-parse HEAD)" == "${upstream_commit}" ]]
git -C "${source_dir}" tag --points-at HEAD | grep -Fxq "0.0.3"
already_applied=false
[[ -z "$(git -C "${source_dir}" status --short --untracked-files=all)" ]] || {
  if git -C "${source_dir}" status --short --untracked-files=all | grep -q '^??'; then
    echo "dependency checkout contains untracked files" >&2
    exit 1
  fi
  diff_file="$(mktemp)"
  trap 'rm -f "${diff_file}"' EXIT
  git -C "${source_dir}" diff HEAD --binary --unified=0 >"${diff_file}"
  cmp --silent "${patch_file}" "${diff_file}" || {
    echo "dependency checkout has changes other than the exact approved patch" >&2
    exit 1
  }
  already_applied=true
}

if [[ "${already_applied}" == false ]] &&
  git -C "${source_dir}" apply --unidiff-zero --check "${patch_file}" 2>/dev/null; then
  git -C "${source_dir}" apply --unidiff-zero "${patch_file}"
elif [[ "${already_applied}" == false ]]; then
  echo "approved patch is not applicable to the clean pinned checkout" >&2
  exit 1
fi

colcon --log-base "${dependency_root}/log" build \
  --base-paths "${source_dir}" \
  --build-base "${dependency_root}/build" \
  --install-base /data/work/ws_mujoco_ros2_control_003/install \
  --merge-install \
  --packages-select mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control

set +u
source "${install_dir}/setup.bash"
set -u
colcon --log-base "${dependency_root}/log" test \
  --base-paths "${source_dir}" \
  --build-base "${dependency_root}/build" \
  --install-base "${install_dir}" \
  --merge-install \
  --packages-select mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control \
  --event-handlers console_direct+
colcon test-result --test-result-base "${dependency_root}/build" --verbose
