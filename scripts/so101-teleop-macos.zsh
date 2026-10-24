#!/bin/zsh
set -euo pipefail
exec /usr/bin/python3 "${0:A:h}/so101-teleop-service.py" --platform darwin "$@"
