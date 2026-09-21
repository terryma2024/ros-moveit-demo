#!/bin/sh
set -eu
repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
python_executable=python3
if [ "$(uname -s)" = Darwin ]; then
  python_executable=/opt/ros2_jazzy/.venv/bin/python
fi
exec "$python_executable" -m so101_demo.cli.parallel_perception_broker container --repository-root "$repository_root" "$@"
