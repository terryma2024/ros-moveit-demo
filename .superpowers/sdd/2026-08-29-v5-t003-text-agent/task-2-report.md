# Task 2 Report: Planner Port and One-Way Fallback Chain

## RED

Tests were written first in `src/so101_demo_py/test/test_planner_chain.py`.

Command:

```bash
source install/setup.zsh
PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_planner_chain.py -q
```

Result: RED during collection with `ModuleNotFoundError: No module named 'so101_demo.application.planner_chain'` (before implementation). Evidence: `/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task2/red-focused-sourced.log`.

## GREEN

Implemented `PlannerMetadata`, `PlannerCandidate`, `PlannerProviderError`, `PlannerPort`, and a bounded `PlannerChain`. The chain calls the primary once, falls back once only for `PlannerProviderError`, marks fallback metadata, and raises `PLANNER_CHAIN_FAILED` when both providers fail. Candidate content is returned unchanged and is never semantically repaired.

Command:

```bash
source install/setup.zsh
PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_planner_chain.py -q
```

Result: `4 passed in 0.79s`. Evidence: `/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task2/green-focused.log`.

## Full suite

Used the required zsh environment, with `ROS_HOME` and `ROS_LOG_DIR` under the registered root:

```zsh
eval "$(direnv export zsh)"
source "$PWD/install/setup.zsh"
export ROS_HOME=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task2/ros-home
export ROS_LOG_DIR=$ROS_HOME/log
PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -c 'import rclpy; print(rclpy.__file__)'
PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test -q --junitxml=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task2/so101_demo_py-pytest.xml
```

`rclpy` imported from `/Users/matianyi/ros2_jazzy/install/rclpy/lib/python3.11/site-packages/rclpy/__init__.py`; full suite result: `569 passed in 23.34s`. Evidence: `/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task2/full-suite.log`, `/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task2/so101_demo_py-pytest.xml`, and `/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task2/rclpy-import.log`.

## Changed files and self-review

- `src/so101_demo_py/src/ports/task_planner.py`: immutable planner value types, provider error, and protocol.
- `src/so101_demo_py/src/application/planner_chain.py`: exact-once primary/fallback behavior.
- `src/so101_demo_py/test/test_planner_chain.py`: primary success, invalid candidate non-repair, provider fallback, and bounded double-failure tests.

Self-review confirms no provider loop, no catch-all exception fallback, no candidate validation or mutation beyond fallback metadata, and no unrelated files changed. No Task 3 work was started.

## Evidence and concerns

Registered evidence root: `/tmp/so101-debug-v5-t003-text-agent-20260829-164105/`. Retained Task 2 artifacts are under its `task2/` subdirectory; archived runs: none; deletion candidates: none (no evidence deleted). Concern: the initial literal `python3` RED command lacked pytest in the system Python, so the behavior-relevant RED was rerun with the mandated ROS Jazzy venv and recorded above.
