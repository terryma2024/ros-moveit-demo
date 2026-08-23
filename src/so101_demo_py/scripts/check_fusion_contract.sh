#!/usr/bin/env bash
set -euo pipefail

script_dir="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"
workspace_root="$(realpath "${script_dir}/../../..")"
expected_prefix="${SO101_DEMO_EXPECTED_PREFIX:-${workspace_root}/install/fusion-final/so101_demo_py}"
ros2_command=(ros2)
if [[ "$(uname -s)" == Darwin ]]; then
  dyld_library_path=""
  while IFS= read -r prefix; do
    if [[ -d "${prefix}/lib" ]]; then
      dyld_library_path="${dyld_library_path:+${dyld_library_path}:}${prefix}/lib"
    fi
  done < <(printf '%s' "${AMENT_PREFIX_PATH:-}" | tr ':' '\n')
  export DYLD_LIBRARY_PATH="${dyld_library_path}"
  ros2_command=(python3 "$(command -v ros2)")
fi

cd "${workspace_root}"

packages="$(colcon list --base-paths src)"
printf '%s\n' "${packages}" | rg '^so101_demo_py[[:space:]]'
for backend in mujoco gazebo; do
  removed="so101_${backend}_demo_py"
  ! printf '%s\n' "${packages}" | rg -q "^${removed}[[:space:]]"
  test ! -e "src/${removed}"
done

actual_prefix="$("${ros2_command[@]}" pkg prefix so101_demo_py)"
test "${actual_prefix}" = "${expected_prefix}"

executables="$("${ros2_command[@]}" pkg executables so101_demo_py)"
for executable in \
  camera_preset gazebo_execute gazebo_ready pick_place run_qualification scene_setup \
  teleop_reset teleop_workflow; do
  printf '%s\n' "${executables}" | rg "^so101_demo_py ${executable}$"
done

share="$("${ros2_command[@]}" pkg prefix --share so101_demo_py)"
for launcher in \
  so101_gazebo.launch.py \
  so101_gazebo_pick_place.launch.py \
  so101_mujoco.launch.py \
  so101_mujoco_pick_place.launch.py; do
  test -f "${share}/launch/${launcher}"
done
test -f "${share}/assets/mujoco/scene.xml"
test -f "${share}/assets/gazebo/world.sdf"
test -f "${share}/config/policies/light_cup_wall_pick/v1/mujoco.yaml"
test -f "${share}/config/policies/light_cup_wall_pick/v1/gazebo.yaml"
test -f "${share}/config/policies/light_cup_wall_pick/v1/real_stub.yaml"

policy_sha256="$(python3 - "${share}/config/policies/light_cup_wall_pick/v1/mujoco.yaml" <<'PY'
from pathlib import Path
import hashlib
import sys

print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"
test "${policy_sha256}" = "aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356"
cmp -s \
  "${share}/config/policies/light_cup_wall_pick/v1/mujoco.yaml" \
  "${share}/config/policies/light_cup_wall_pick/v1/gazebo.yaml"

python3 -m pytest -q src/so101_demo_py/test
python3 -m pytest --collect-only -q src/so101_demo_py/test | rg '[1-9][0-9]* tests collected'
python3 scripts/check_backend_integration.py

test ! -e src/so101_demo_py/launch/so101_real.launch.py
if rg -n 'serial|pyudev|socket|create_publisher|ActionClient|create_client|subprocess' \
  src/so101_demo_py/src/backends/real_stub; then
  exit 1
fi
git diff --check
