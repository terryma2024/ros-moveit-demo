#!/usr/bin/bash
set -euo pipefail
# ROS-generated setup scripts read optional unset tracing variables.
set +u
source /opt/ros/jazzy/setup.bash
if [[ -f /act/install/local_setup.bash ]]; then
    source /act/install/local_setup.bash
fi
set -u
export AMENT_PREFIX_PATH=/act/install:${AMENT_PREFIX_PATH:-/opt/ros/jazzy}
export PATH=/act/venv/bin:/act/install/bin:/opt/ros/jazzy/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
exec "$@"
