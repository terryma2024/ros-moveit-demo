import os
from pathlib import Path
import subprocess


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RESET_SCRIPT = PACKAGE_ROOT / 'scripts' / 'reset_world.sh'


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding='utf-8')
    path.chmod(0o755)


def test_reset_world_waits_for_late_gazebo_service_discovery(tmp_path):
    """A fresh gz CLI may need several discovery cycles before seeing the world."""
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    discovery_count = tmp_path / 'discovery-count'

    _write_executable(
        bin_dir / 'gz',
        f'''#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == service && "$2" == -l ]]; then
  count=0
  [[ ! -f "{discovery_count}" ]] || count="$(<"{discovery_count}")"
  count=$((count + 1))
  printf '%s\n' "$count" >"{discovery_count}"
  if ((count >= 3)); then
    printf '%s\n' /world/pick_place_world/control /world/pick_place_world/set_pose
  fi
elif [[ "$1" == service ]]; then
  printf 'data: true\n'
elif [[ "$1" == topic && "$2" == -l ]]; then
  printf '%s\n' /panda/detach_coke /panda/coke_attached
elif [[ "$1" == topic && " $* " == *' -e '* ]]; then
  printf 'data: "detached"\n'
elif [[ "$1" == topic ]]; then
  exit 0
elif [[ "$1" == model ]]; then
  printf 'Pose [ XYZ (m) ] [ RPY (rad) ]: [ 0.3 0.0 0.836 ] [ 0 0 0 ]\n'
else
  exit 2
fi
''',
    )
    _write_executable(
        bin_dir / 'ros2',
        '''#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == action && "$2" == list ]]; then
  printf '%s\n' /panda_arm_controller/follow_joint_trajectory /panda_hand_controller/gripper_cmd
elif [[ "$1" == action && "$2" == send_goal ]]; then
  printf 'Goal finished with status: SUCCEEDED\n'
elif [[ "$1" == run ]]; then
  exit 0
else
  exit 2
fi
''',
    )

    env = os.environ.copy()
    env.update(
        {
            'PATH': f'{bin_dir}:{env["PATH"]}',
            'EXPECTED_COKE_DETACHED': 'true',
            'GAZEBO_SERVICE_DISCOVERY_TIMEOUT_SECONDS': '1',
            'GAZEBO_SERVICE_DISCOVERY_POLL_INTERVAL_SECONDS': '0.01',
        }
    )
    result = subprocess.run(
        ['/bin/bash', str(RESET_SCRIPT)],
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert int(discovery_count.read_text(encoding='utf-8')) >= 3
