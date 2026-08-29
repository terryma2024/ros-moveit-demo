# Task 1 report

## Implementation

Added an immutable `TaskCommand` value object, strict closed-world command validator, instruction validator, JSON schema, and `CommandValidationError` with code `COMMAND_INVALID`. Constraints are normalized into sorted immutable tuples and exposed as a dictionary by `to_dict()`.

## Files changed

- `src/so101_demo_py/src/core/task_command.py`
- `src/so101_demo_py/test/test_task_command.py`

## RED

Command:

```bash
PYTHONPATH=src/so101_demo_py/src /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_task_command.py -q
```

Output:

```text
ModuleNotFoundError: No module named 'so101_demo'
```

The requested source-layout invocation cannot import the package because this ament Python package maps `so101_demo` to `src` only at installation time. After using a temporary import symlink rooted at `/tmp/so101-debug-task1/import`, the focused test collected and failed 1 test (9 passed): the supplied 200-character check did not reject 51 repetitions of a three-character Chinese phrase. The implementation therefore bounds UTF-8 encoded length, which satisfies the specified regression case while retaining the `max_chars=200` interface.

## GREEN

Command:

```bash
PYTHONPATH=/tmp/so101-debug-task1/import /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_task_command.py -q
```

Output: `10 passed in 0.03s` (exit 0).

## Full suite

Command:

```bash
source /opt/ros/jazzy/setup.zsh
PYTHONPATH=/tmp/so101-debug-task1/import /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test -q
```

The suite did not collect because the macOS environment lacks ROS Python modules (`rclpy`, `launch_ros`, `moveit_msgs`, `ament_index_python`, and `launch`). This is an environment/bootstrap failure, not a TaskCommand assertion failure. A package build attempt was also blocked by missing dependency install package hooks in the temporary install base.

## Self-review

`git diff --check` passed. The patch is limited to the requested two files, uses Python built-ins only, freezes the dataclass with slots, rejects unknown fields and unsupported values, and preserves deterministic constraint ordering.

## Concerns

The task brief's exact `max_chars=200` implementation conflicts with its required test case (`"拿杯子" * 51` is 153 Unicode code points). The implementation uses UTF-8 byte length so that the supplied case is correctly rejected. Full package verification remains pending a ROS-enabled test environment.

Evidence root: `/tmp/so101-debug-task1/` (retained during this task; no archived runs; files are deletion candidates only with explicit authorization).

## Correction

Follow-up review corrected the contract: `max_chars` counts Unicode characters, with explicit acceptance of 200 non-ASCII characters and rejection of 201. Target and action now explicitly reject non-string values. The boundary tests were changed first, then run against the byte-count implementation to capture the intended RED:

```bash
E=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task1-fix
PYTHONPATH="$E/import" /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_task_command.py -q
```

Result: `1 failed, 11 passed`; the 200-character Chinese boundary was rejected by the old byte-count implementation.

After changing production code to `len(instruction)` and adding explicit type checks, the exact focused command produced `12 passed in 0.04s` (exit 0). The registered root for this correction is `/tmp/so101-debug-v5-t003-text-agent-20260829-164105/`, with logs/JUnit under `task1-fix/`. The prior `/tmp/so101-debug-task1/` remains untouched and is classified as a deletion candidate only; it was not deleted.

The required ROS-environment full-suite command (`direnv export`, isolated worktree install overlay, ROS_HOME/ROS_LOG_DIR and JUnit all below the registered root) ran but collected 15 errors because this macOS installation lacks `rclpy`, `launch_ros`, `moveit_msgs`, `ament_index_python`, and `launch`. No TaskCommand tests failed in that run; full-suite completion remains an environment concern.
