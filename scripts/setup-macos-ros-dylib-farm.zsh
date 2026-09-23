#!/bin/zsh

set -euo pipefail

readonly ros_workspace="${SO101_ROS_WORKSPACE:-${SO101_ROS_ROOT:-/opt/ros/jazzy}}"
readonly ros_underlay="${SO101_ROS_UNDERLAY:-${ros_workspace}/install}"
readonly farm_root="${SO101_DYLIB_FARM_ROOT:-${ros_workspace}/dylib_farm}"
readonly fork_install="${SO101_MUJOCO_FORK_INSTALL:-/opt/data/so101/runtime/fork/current}"
readonly project_install="${SO101_PROJECT_INSTALL:-/opt/data/so101/workspace/install}"
readonly default_prefixes="${ros_underlay}:${ros_workspace}/extra_ws/install:${fork_install}:${project_install}"
readonly prefix_spec="${SO101_ROS_PREFIXES:-${default_prefixes}}"
readonly -a required_libraries=(
  libcontrol_toolbox.dylib
  libhardware_interface.dylib
  librosidl_typesupport_c.dylib
)

mkdir -p "${farm_root}/runs"
building_dir="$(mktemp -d "${farm_root}/runs/.building.XXXXXX")"
trap 'rm -rf -- "${building_dir}"' EXIT
readonly override_manifest="${building_dir}/.overrides.tsv"
print -- $'basename\tprevious\tselected\tprevious_sha256\tselected_sha256' > "${override_manifest}"

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
      if [[ "${existing}" == "${library}" ]]; then
        continue
      fi
      existing_sha="$(shasum -a 256 "${existing}" | awk '{print $1}')"
      selected_sha="$(shasum -a 256 "${library}" | awk '{print $1}')"
      print -- "${basename}\t${existing}\t${library}\t${existing_sha}\t${selected_sha}" >> "${override_manifest}"
      ln -sfn -- "${library}" "${target}"
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

for required_library in "${required_libraries[@]}"; do
  if [[ ! -L "${building_dir}/${required_library}" ]]; then
    print -u2 -- "missing required ROS dylib: ${required_library}"
    exit 2
  fi
done

run_name="$(date -u +%Y%m%dT%H%M%SZ)-${$}"
final_dir="${farm_root}/runs/${run_name}"
mv -- "${building_dir}" "${final_dir}"
trap - EXIT

next_link="${farm_root}/.current-${$}"
ln -s -- "${final_dir}" "${next_link}"
/bin/mv -fh -- "${next_link}" "${farm_root}/current"

print -- "${final_dir}"
