# Installed SO-101 Web suite dependencies

The installed Playwright suite starts the unified Web service through
`src/so101_teleop/test/e2e/installed_test_launcher.py`. Its Python interpreter must be able to
import the installed ROS packages and the service's Python dependencies. The browser tests also
need a WebSocket connection to `/control/instances/{instance_id}/channel` to obtain mutation
authority.

## Python packages

The task-owned Linux environment used for the September 23, 2026 installed-suite run had these
packages. The versions describe that environment; they are not project-wide version pins.

| Package | Observed version | Used for |
| --- | --- | --- |
| `mujoco` | 3.12.0 | Simulator runtime |
| `uvicorn` | 0.53.0 | ASGI server |
| `fastapi` | 0.141.1 | HTTP and WebSocket routes |
| `pydantic` | 2.13.5 | Request and response models |
| `psutil` | 7.2.2 | Process ownership and recovery checks |
| `websockets` | 17.1 | Uvicorn WebSocket protocol backend |

To recreate this Python package set in a task-owned venv, use that venv's interpreter:

```sh
"$SO101_E2E_PYTHON" -m pip install \
  'mujoco==3.12.0' 'uvicorn==0.53.0' 'fastapi==0.141.1' \
  'pydantic==2.13.5' 'psutil==7.2.2' 'websockets==17.1'
```

Installing `uvicorn` alone did not install a WebSocket protocol backend in that venv. Without
`websockets` or another Uvicorn-supported backend, Uvicorn rejected the channel upgrade and the
installed browser suite could not acquire authority. Check the exact Python selected by
`SO101_E2E_PYTHON` before running the suite:

```sh
test -x "$SO101_E2E_PYTHON"
"$SO101_E2E_PYTHON" -c 'import fastapi, mujoco, psutil, pydantic, uvicorn, websockets'
"$SO101_E2E_PYTHON" -m pip show websockets
```

For a task-owned venv that already has the other packages, install the missing backend into that
venv with `"$SO101_E2E_PYTHON" -m pip install websockets`. The Linux run installed it from the
TUNA PyPI mirror with `--index-url https://pypi.tuna.tsinghua.edu.cn/simple`, after adding that
host to the command's `NO_PROXY` and `no_proxy` values. This did not change system Python or a
global pip configuration. The repository's
[`python-dependency-install.md`](../../.agents/skills/so101-dev/references/python-dependency-install.md)
describes the mirror and proxy rule.

## Browser and installed ROS closure

The same Linux run used Python 3.12.3, Node 26.9.0, Bun 1.4.2 for the ROS package build, and the
Web package's installed `node_modules`. Node 26.9.0 is an observation from this run, not a
supported project version: `web/package.json` requires Node `>=24.18.1 <25`. Use a Node version
within that range for a supported setup. The suite drives the installed Google Chrome binary at
`/usr/bin/google-chrome` on Linux or
`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` on macOS. Set
`SO101_PLAYWRIGHT_CHROME` to use another Chrome executable. The suite ran Playwright with Node:

```sh
cd src/so101_teleop/web
node node_modules/.bin/playwright test --config playwright.installed.config.ts
```

Set `SO101_E2E_INSTALL_PREFIX` to the copied install under test and `SO101_E2E_PYTHON` to its
verified Python environment. Source the host's ROS underlay and the copied install before running
Playwright. The fixture also needs `SO101_E2E_EVIDENCE_ROOT`, `SO101_TASK_ROOT`, and the two model
paths `SO101_VALIDATION_YOLO_WEIGHTS` and `SO101_VALIDATION_GROUNDED_ROOT`; see the
[`installed-suite repair plan`](../superpowers/plans/2026-09-23-so101-installed-suite-platform-repair.md)
for the host-specific paths and commands. Keep test evidence in the task's registered root.
