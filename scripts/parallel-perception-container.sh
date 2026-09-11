#!/bin/sh
set -eu
repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
exec python3 -m so101_demo.cli.parallel_perception_broker container --repository-root "$repository_root" "$@"
