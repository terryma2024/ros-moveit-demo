#!/usr/bin/env bash
set -euo pipefail

cli="$1"
output="$($cli --help)"
grep -q '^Usage: calibrate_so101_motion ' <<<"$output"
grep -q 'search' <<<"$output"
grep -q 'fk' <<<"$output"
grep -q 'plan' <<<"$output"
if grep -q 'execute' <<<"$output"; then
  echo "calibration CLI must not expose arm execution" >&2
  exit 1
fi
