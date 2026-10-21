#!/usr/bin/bash
# Entry script of the mount-base image: ROS first, then the host-built install tree that is bind-mounted read-only at SO101_MOUNT_INSTALL.
set -eo pipefail
set +u
if [[ -n ${SO101_MOUNT_INSTALL:-} ]]; then
    # The launch passes the commit it wants; the host build wrote the same commit into both trees last. No record, or another one: refuse.
    [[ -n ${SO101_MOUNT_SOURCE:-} ]] || { echo "MOUNT_COMMIT_NOT_GIVEN: SO101_MOUNT_SOURCE is not set" >&2; exit 2; }
    /act/check-mount-commit.bash "${SO101_EXPECTED_COMMIT:-}" "$SO101_MOUNT_INSTALL" "$SO101_MOUNT_SOURCE"
fi
source /opt/ros/jazzy/setup.bash
if [[ -n ${SO101_MOUNT_INSTALL:-} ]]; then
    export COLCON_CURRENT_PREFIX=$SO101_MOUNT_INSTALL
    source "$SO101_MOUNT_INSTALL/setup.bash"
fi
export PATH=/act/venv/bin:$PATH
# Console scripts built on the host start with #!/usr/bin/python3, which does not see the venv packages.
export PYTHONPATH=${PYTHONPATH:-}:/act/venv/lib/python3.12/site-packages:/opt/venv/lib/python3.12/site-packages
exec "$@"
