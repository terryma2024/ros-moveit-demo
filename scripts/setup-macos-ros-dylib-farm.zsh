#!/bin/zsh

set -euo pipefail

readonly ros_workspace="${SO101_ROS_WORKSPACE:-${SO101_ROS_ROOT:-${HOME}/ros2_jazzy}}"
readonly ros_underlay="${SO101_ROS_UNDERLAY:-/opt/ros/jazzy}"
readonly farm_root="${SO101_DYLIB_FARM_ROOT:-${ros_workspace}/macos_dylib_farm}"
readonly default_prefixes="${ros_underlay}:${ros_workspace}/extra_ws/install:${ros_workspace}/ws_mujoco_ros2_control_fork/install:${ros_workspace}/so101_isolated_ws/install"
readonly prefix_spec="${SO101_ROS_PREFIXES:-${default_prefixes}}"

mkdir -p "${farm_root}/runs"
building_dir="$(mktemp -d "${farm_root}/runs/.building.XXXXXX")"
trap 'rm -rf -- "${building_dir}"' EXIT

prefixes=("${(@s/:/)prefix_spec}")
for prefix in "${prefixes[@]}"; do
  if [[ ! -d "${prefix}" ]]; then
    print -u2 -- "missing ROS prefix: ${prefix}"
    exit 2
  fi

  while IFS= read -r -d '' library; do
    basename="${library:t}"
    target="${building_dir}/${basename}"
    if [[ -e "${target}" || -L "${target}" ]]; then
      existing="$(readlink "${target}")"
      if ! cmp -s -- "${existing}" "${library}"; then
        print -u2 -- "ambiguous dylib basename: ${basename}"
        print -u2 -- "  first: ${existing}"
        print -u2 -- "  second: ${library}"
        exit 2
      fi
      continue
    fi
    ln -s -- "${library}" "${target}"
  done < <(find -L "${prefix}" \( -type f -o -type l \) -name '*.dylib' -print0 | sort -z)
done

library_count="$(find "${building_dir}" -type l | wc -l | tr -d ' ')"
if [[ "${library_count}" == "0" ]]; then
  print -u2 -- "no dylibs found in configured ROS prefixes"
  exit 2
fi

run_name="$(date -u +%Y%m%dT%H%M%SZ)-${$}"
final_dir="${farm_root}/runs/${run_name}"
mv -- "${building_dir}" "${final_dir}"
trap - EXIT

next_link="${farm_root}/.current-${$}"
ln -s -- "${final_dir}" "${next_link}"
mv -f -- "${next_link}" "${farm_root}/current"

print -- "${final_dir}"
