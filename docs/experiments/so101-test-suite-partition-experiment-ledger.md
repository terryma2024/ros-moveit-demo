# SO-101 test suite partition experiment ledger

task_id: so101-test-suite-partition-20260903
source_commit: 9361784ff00ec9774a19cc9dcd9fb38b7361e093
commit_verification_head: 1cde365cb39cdc25e224ee3d0ec73ea2f83e99cb
branch: codex/v5-t004-yolo-seg-rgbd
evidence_root: /tmp/so101-debug-test-suite-partition-20260903
run_mode: package_test_only
ros_domain_id: UNSET_NO_ROS_RUNTIME
gz_partition: UNSET_NO_SIMULATOR

## EXP-001 — Default and benchmark suite partition

status: PASS
hypothesis: Moving the low-frequency perception benchmark tests behind an explicit package-test entry will remove them from ordinary `so101_demo_py` package testing without reducing the explicit benchmark suite.
prediction:
  - Before the change, ordinary collection under `src/so101_demo_py/test` contains `test_perception_benchmark_*` node IDs.
  - After the change, ordinary package collection contains no benchmark node IDs.
  - Explicit benchmark collection still contains every moved benchmark test.
  - Production benchmark persistence and `fsync` behavior are unchanged.
lifecycle: REUSE_STACK_NO_RUNTIME
preserved_user_state:
  - Existing untracked `build-*`, `install-*`, and `log-*` directories are retained and excluded from edits.
  - No ROS, MuJoCo, Gazebo, or MoveIt process was started.
red_evidence:
  - /tmp/so101-debug-test-suite-partition-20260903/tests/red-partition.xml
  - /tmp/so101-debug-test-suite-partition-20260903/tests/red-default-config.xml
red_result: The partition contract failed because 13 `test_perception_benchmark_*` modules were still under the ordinary test tree and `setup.cfg` did not constrain default pytest discovery.
green_evidence:
  - /tmp/so101-debug-test-suite-partition-20260903/tests/green-partition.xml
green_result: The partition contract passed 2/2 checks after the physical move and `testpaths = test` configuration.
explicit_benchmark_collection: 557 tests collected from `benchmark_test/`; no benchmark test was executed during the collection check.
environment_note: An initial no-plugin collection used a source-tree `PYTHONPATH` that does not match this package's nonstandard `package_dir` mapping. The retry used the existing `build-rebase-final-r15/so101_demo_py` build path. This was an environment provenance correction, not a product-code change.
implementation:
  - Moved all 13 `test_perception_benchmark_*` modules and their dry-run fixture from `test/` to `benchmark_test/`.
  - Configured package-level pytest discovery with `testpaths = test`, so an argument-free pytest or colcon package test excludes `benchmark_test/`.
  - Added a regression contract that rejects benchmark modules in the ordinary test tree and verifies the default pytest path.
  - Added repository rules that permit the explicit benchmark gate only for benchmark maintenance or perception-model comparison/selection.
verification:
  - partition_contract: 2 passed in 0.31 seconds; JUnit `/tmp/so101-debug-test-suite-partition-20260903/tests/partition-final.xml`.
  - ordinary_suite: 1167 passed in 17.85 seconds; 0 benchmark-named cases; JUnit `/tmp/so101-debug-test-suite-partition-20260903/tests/default-suite-r2.xml`.
  - explicit_benchmark_suite: 557 passed in 320.33 seconds; JUnit `/tmp/so101-debug-test-suite-partition-20260903/tests/benchmark-suite.xml`.
  - move_integrity: All 13 moved test-module bodies are byte-equivalent after removing the new suite docstring and accounting for the fixture path; fixture JSON is semantically unchanged.
  - commit_default_suite: 1167 passed in 20.69 seconds; JUnit `/tmp/so101-debug-test-suite-partition-20260903/tests/commit-default.xml`.
  - commit_benchmark_suite: 557 passed in 340.41 seconds; JUnit `/tmp/so101-debug-test-suite-partition-20260903/tests/commit-benchmark.xml`.
  - diff_check: `git diff --check` passed.
measured_effect: A workflow that previously ran both groups would spend 338.18 seconds in these tests. The ordinary gate now spends 17.85 seconds, saving 320.33 seconds (94.7 percent) and returning about 18.9 times faster on this macOS run.
colcon_note: The macOS colcon runner reported `testpaths: test`, proving the default discovery boundary, but its child pytest process could not load `@rpath/librosidl_typesupport_c.dylib`. The same sourced overlay passed the full ordinary suite when pytest was invoked directly. This existing macOS child-process runtime issue is outside the test-partition change.
linux_status: Not executed from this uncommitted worktree. The pytest discovery configuration is platform-neutral; Linux runtime verification should follow after an authorized commit/push and ai-station pull.
durability: Production benchmark persistence, atomic writes, and `fsync` calls were not changed.
retained_runs:
  - /tmp/so101-debug-test-suite-partition-20260903
archived_runs: []
deletion_candidates:
  - Failed environment-provenance attempts under `/tmp/so101-debug-test-suite-partition-20260903/tests/colcon-default*`; retained for audit and not deleted.
next_command: Review the scoped diff; commit and push only after explicit user authorization.
