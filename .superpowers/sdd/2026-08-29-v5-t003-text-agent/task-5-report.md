# Task 5 report — typed dynamic-runtime adapter

## Scope and changed files

- `src/so101_demo_py/src/adapters/pick_place_executor.py`
  - Adds frozen `DynamicRuntimeContext` and `DynamicCupPickPlaceExecutor`.
  - Projects only the fixed runtime option allowlist into a `SimpleNamespace`.
  - Validates the one qualified typed capability before dispatch, preserves context provenance,
    rejects malformed runner return values, and converts runner `Exception` failures to the
    redacted `ExecutorDispatchError("DYNAMIC_RUNTIME_EXCEPTION") from None`.
- `src/so101_demo_py/test/test_pick_place_executor_adapter.py`
  - Covers frozen context, exact one-call option projection, rejected capability/backend/scene/
    object/action requests, preview lazy-import behavior, exception redaction, and exact-integer
    runner results.

## Evidence and commands

All Task 5 evidence is retained under the registered root
`/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task5/`.

1. RED (expected missing module):

   ```zsh
   zsh -lc 'eval "$(direnv export zsh)"; PYTHONNOUSERSITE=1 python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_pick_place_executor_adapter.py -q'
   ```

   Exit 2; `ModuleNotFoundError: No module named 'so101_demo.adapters'` is retained in
   `red.log`.

2. Build the candidate install overlay:

   ```zsh
   zsh -lc 'eval "$(direnv export zsh)"; colcon build --packages-select so101_demo_py --symlink-install'
   ```

   Exit 0; `build.log` retains the output.

3. Focused GREEN, after `source install/setup.zsh` with successful `rclpy`, `launch`,
   `launch_ros`, and `ament_index_python` imports:

   ```zsh
   PYTHONNOUSERSITE=1 python3 -m pytest -p no:cacheprovider \
     src/so101_demo_py/test/test_pick_place_executor_adapter.py \
     src/so101_demo_py/test/test_dual_cup_entrypoints.py -q \
     --junitxml=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task5/focused-junit.xml
   ```

   Exit 0; **20 passed**. See `green-focused.log` and `focused-junit.xml`.

4. Full GREEN, exact zsh/direnv overlay plus the candidate install; `ROS_HOME` and
   `ROS_LOG_DIR` were set beneath the same task evidence root:

   ```zsh
   zsh -lc 'eval "$(direnv export zsh)"; source install/setup.zsh; \
     export ROS_HOME=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task5/ros-home; \
     export ROS_LOG_DIR="$ROS_HOME/log"; mkdir -p "$ROS_LOG_DIR"; \
     PYTHONNOUSERSITE=1 python3 -c "import rclpy, launch, launch_ros, ament_index_python"; \
     PYTHONNOUSERSITE=1 python3 -m pytest -p no:cacheprovider src/so101_demo_py/test -q \
       --junitxml=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task5/full-junit-rerun/so101_demo_py-pytest.xml; \
     /Users/matianyi/ros2_jazzy/.venv/bin/colcon test-result \
       --test-result-base /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task5/full-junit-rerun --verbose'
   ```

   Exit 0; **635 passed, 0 errors, 0 failures, 0 skipped**. See
   `full-green-rerun.log` and `full-junit-rerun/so101_demo_py-pytest.xml`.

The first full-suite attempt is retained in `full-green.log` and `full-junit/`; it had 64
failures caused by launch-test writes to a sandbox-denied `~/.ros/log`, not an assertion or
collection regression. It is non-authoritative. No evidence was deleted.

## Boundary review

- Importing the adapter, handling TextAgent preview, and rejecting typed requests do not import
  `rclpy`; the default dynamic runtime import occurs only after a qualified dispatch request.
- The runner receives exactly one newly-created `SimpleNamespace` with only fixed execution,
  policy, timeout, provenance, session, epoch, and evidence-root fields. No shell command,
  arbitrary provider option, or request-supplied runtime option crosses this boundary.
- Context provenance (`source_commit`, `installed_prefix`, `session_id`,
  `expected_reset_epoch`, and `evidence_root`) is preserved unchanged.
- Only `Exception` is normalized. `BaseException` remains uncaught. Any ordinary runtime/runner
  exception is redacted to `DYNAMIC_RUNTIME_EXCEPTION`; a bool or other malformed result is
  rejected with `DYNAMIC_RUNTIME_RESULT_INVALID` before a `RuntimeDispatchResult` is built.

## Self-review and concerns

`git diff --check` passed. The adapter has no ROS import at module load and no shell execution.
The runtime itself is intentionally not invoked by unit tests; the injected runner isolates this
adapter boundary and avoids physical side effects. Runtime return code zero still only indicates
the existing runtime's outcome, not physical pick-place acceptance.

Retained runs: `task5/` evidence listed above. Archived runs: none. Deletion candidates: none.
