#!/usr/bin/bash
set -euo pipefail
source /opt/ros/jazzy/setup.bash
if [[ -f /act/install/local_setup.bash ]]; then
    source /act/install/local_setup.bash
fi
export PATH=/act/venv/bin:/act/install/bin:/opt/ros/jazzy/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
exec "$@"
