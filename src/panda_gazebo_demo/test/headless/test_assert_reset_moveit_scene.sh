#!/usr/bin/env bash
set -euo pipefail

validator=$1
fixture=$2
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

if [[ ! -f "${validator}" ]]; then
  fail 'reset MoveIt scene validator is missing'
fi

sed 's/y=0.2/y=0.0/' "${fixture}" >"${tmp_dir}/canonical.txt"
python3 "${validator}" "${tmp_dir}/canonical.txt"

sed 's/attached_collision_objects=\[\]/attached_collision_objects=[coke]/' \
  "${tmp_dir}/canonical.txt" >"${tmp_dir}/attached.txt"
if python3 "${validator}" "${tmp_dir}/attached.txt" >/dev/null 2>&1; then
  fail 'validator accepted attached MoveIt Coke'
fi

sed 's/x=0.3, y=0.0, z=0.836/x=0.35, y=0.0, z=0.836/' \
  "${tmp_dir}/canonical.txt" >"${tmp_dir}/wrong_position.txt"
if python3 "${validator}" "${tmp_dir}/wrong_position.txt" >/dev/null 2>&1; then
  fail 'validator accepted the wrong MoveIt Coke position'
fi

sed 's/x=0.0, y=0.0, z=0.0, w=1.0/x=0.258819, y=0.0, z=0.0, w=0.965926/' \
  "${tmp_dir}/canonical.txt" >"${tmp_dir}/wrong_orientation.txt"
if python3 "${validator}" "${tmp_dir}/wrong_orientation.txt" >/dev/null 2>&1; then
  fail 'validator accepted the wrong MoveIt Coke orientation'
fi

sed "s/id='coke'/id='table'/" "${tmp_dir}/canonical.txt" \
  >"${tmp_dir}/missing.txt"
if python3 "${validator}" "${tmp_dir}/missing.txt" >/dev/null 2>&1; then
  fail 'validator accepted a scene without world Coke'
fi

printf 'PASS: reset MoveIt scene validator rejects inconsistent evidence\n'
