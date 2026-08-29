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

## Review-fix correction

The review identified that context values were previously trusted and that an import-time
failure on the default runner path was outside the adapter's operational exception boundary.
This correction preserves the earlier evidence and adds fail-closed validation after qualified
request validation but before any context projection, runner call, or ROS import.

- Context now accepts only: a nonblank exact `str` session ID; non-bool `int` epoch at least
  zero; absolute `Path` evidence root; nonblank exact `str` source commit; and nonempty exact
  `str` absolute installed prefix. Any invalid value raises only
  `ExecutorDispatchError("DYNAMIC_RUNTIME_CONTEXT_INVALID")`.
- Invalid typed requests still return nonzero first, even if context is invalid. They do not
  validate context, import the default runtime, or invoke a runner.
- The lazy default import and runner call share one `except Exception` boundary, so import-time
  and runner operational failures become `DYNAMIC_RUNTIME_EXCEPTION` with `from None`; no
  arbitrary runtime text is exposed. `BaseException` is still not caught.

Review-fix evidence stays under the same registered root:
`/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task5-review-fix/`.

- RED: `red.log`, exact zsh/direnv candidate-overlay command, **15 failed, 14 passed**. The
  failures demonstrate that invalid contexts previously reached the injected runner and that
  a real default import failure previously leaked past the adapter boundary.
- GREEN focused: `green-focused.log` and `focused-junit.xml`, with ROS imports confirmed,
  **36 passed**.
- GREEN full package: `full-green.log` and
  `full-junit/so101_demo_py-pytest.xml`, **651 passed, 0 errors, 0 failures, 0 skipped**.

`git diff --check` passed for this correction. Retained runs: prior `task5/` and
`task5-review-fix/`; archived: none; deletion candidates: none. No runtime stack was started.

## Audit clarification — reviewer Minor finding

The original `task5-review-fix/red.log` honestly records **15 context-related failures**, but its
exact-name default-import hook did not match Python's relative import form. That test therefore
entered the runtime and ended at `CUP_POSE_TIMEOUT`; this artifact does **not** itself prove the
pre-fix import-exception leak. The reviewer independently probed base commit `4d4a99d` and
confirmed that the import exception leaked there; the current `9705da6` boundary redacts it.

Fresh authoritative reviewer verification is retained under
`/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task5-review-fix/rereview-rerun/`:
focused **36 passed** and full package **651 passed**. The separate
`task5-review-fix/rereview/` directory is retained as a deletion candidate because its environment
preflight failed. Nothing was deleted.
