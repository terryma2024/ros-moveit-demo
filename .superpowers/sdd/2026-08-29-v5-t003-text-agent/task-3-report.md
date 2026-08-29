# Task 3 report: DeepSeek and Ollama planner adapters

Implemented standard-library JSON POST transport and injected-transport DeepSeek/Ollama planner adapters with exact request envelopes, stable redacted errors, documented token counters, latency, and pass-through JSON candidates.

Registered evidence root: `/tmp/so101-debug-v5-t003-text-agent-20260829-164105/`; all Task 3 artifacts are under `task3/`.

## TDD evidence

RED command:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_planner_adapters.py -q
```

Result: exit 2 during collection with `ModuleNotFoundError: No module named 'so101_demo'`, expected because adapters were absent. Log: `task3/red.log`.

GREEN command:

```bash
PYTHONPATH=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task3/import /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_planner_adapters.py -q
```

Result: exit 0, **21 passed** (`task3/green.log`).

Full package command used `eval "$(direnv export zsh)"`, `source "$PWD/install/setup.zsh"`, ROS_HOME and ROS_LOG_DIR under `task3/`, and:

```bash
PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test -q --junitxml=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task3/so101_demo_py-pytest.xml
```

Result: exit 0, **590 passed in 19.66s** (`task3/full-suite.log`; JUnit under `task3/`).

## Changed files

Added the six adapter package/implementation files and `test/test_planner_adapters.py`.

## Self-review

Transport and provider failures never include keys, instruction, raw body/content, or URL secrets. Usage envelopes/counters are type guarded; only documented counters map to metadata. Syntactically valid JSON of any shape proceeds unchanged to Task 4. No network calls or Task 4 work were performed.

Retained runs: Task 3 logs, JUnit, and ROS_HOME under the registered root. Archived runs: none. Deletion candidates: none; no evidence was deleted.
