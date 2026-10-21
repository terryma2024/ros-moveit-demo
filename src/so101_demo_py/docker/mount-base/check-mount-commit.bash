#!/usr/bin/bash
# usage: check-mount-commit.bash EXPECTED_COMMIT DIR...
# Each mounted tree carries a BUILD-COMMIT record that the host build wrote last. The container starts only when every record names the
# commit the launch asked for. Exit 2: no or malformed expected commit; 3: a record is missing; 4: a record differs or is malformed.
expected=${1:-}
[[ $expected =~ ^[0-9a-f]{40}$ ]] || { echo "MOUNT_COMMIT_NOT_GIVEN: expected a 40-hex commit, got '$expected'" >&2; exit 2; }
shift
(( $# )) || { echo "MOUNT_COMMIT_NOT_GIVEN: no mounted directory to check" >&2; exit 2; }
for dir in "$@"; do
    record=$dir/BUILD-COMMIT
    [[ -f $record ]] || { echo "MOUNT_COMMIT_MISSING: $record" >&2; exit 3; }
    found=$(<"$record")
    [[ $found == "$expected" ]] || { echo "MOUNT_COMMIT_MISMATCH: $record holds '$found', expected $expected" >&2; exit 4; }
done
