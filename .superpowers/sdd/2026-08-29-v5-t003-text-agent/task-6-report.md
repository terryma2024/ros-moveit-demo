# Task 6 report — safe text pick CLI

## Scope

- Added `text_pick_agent` as an installed `so101_demo_py` console entry point.
- Kept preview fail-closed and ROS-free; execution requires explicit double authorization plus complete runtime provenance.
- Did not start Task 7 or dispatch a live MuJoCo action.

## RED → GREEN

- RED: `/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task6/red.log`
  recorded 27 expected failures: the CLI module did not exist and the executed
  setuptools capture lacked the entry point.
- Focused GREEN: 29 passed in 0.53s; JUnit:
  `/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task6/focused-junit.xml`.
- Candidate install: `colcon build --packages-select so101_demo_py --symlink-install`
  completed successfully. The macOS post-build LaunchServices warning did not change
  the colcon success result.
- Package GREEN: 677 passed in 20.453s, 0 errors and 0 failures; JUnit:
  `/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task6/so101_demo_py-pytest.xml`.
  The exact zsh ROS overlay imported `rclpy` from
  `/Users/matianyi/ros2_jazzy/install/rclpy/lib/python3.11/site-packages/rclpy/__init__.py`.

## Installed-runtime evidence

- Prefix: `/Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-text-agent/install/so101_demo_py`.
- Executable: `lib/so101_demo_py/text_pick_agent` is executable.
- `ros2 pkg executables so101_demo_py` reported `so101_demo_py text_pick_agent`.
- `ros2 run so101_demo_py text_pick_agent --instruction 帮我拿杯子 --backend gazebo --request-id installed-gate`
  emitted exactly one sorted JSON document with `BACKEND_NOT_QUALIFIED` and exited 1;
  no provider, ROS runtime, or physical action was started.

## Evidence disposition

- Retained: the complete Task 6 evidence directory above (RED log and JUnit files).
- Archived: none.
- Deletion candidates: none. No evidence was deleted.

## Review correction — CLI composition hardening

The first report summarized installed-entry-point results without retaining the
corresponding raw command output. That evidence gap is corrected under the same
task evidence root at
`/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task6-review-fix/`:

- `red.log`: 14 expected RED failures for missing provider-option pre-gates and
  source/session whitespace normalization; the production-composition ROS-free
  preview regression was already green because the existing preview executor was
  lazy and never imported the ROS runtime.
- `focused-junit.xml`: 44 passed, 0 errors, 0 failures.
- `build.log`: candidate `so101_demo_py` rebuild output.
- `installed-evidence.log`: resolved current HEAD and package prefix, executable
  stat, `ros2 pkg executables` output, and installed wrong-backend JSON/exit 1.
- `so101_demo_py-pytest.xml`: exact zsh ROS-overlay full package result, 692
  passed, 0 errors, 0 failures.

The CLI now strips session IDs and source commits before constructing runtime
context, rejects normalized empty or `UNRECORDED_SOURCE` commits, and validates
normalized nonempty provider names/endpoints with finite positive timeouts before
constructing either provider. Preview composition remains ROS-runtime-free.
