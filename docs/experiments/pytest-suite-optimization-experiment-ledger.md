# Pytest suite optimization experiment ledger

task_id: so101-pytest-opt-20260924-021323
goal: Execute the reviewed SO-101 pytest optimization plan.
success_contract: Four omitted teleop files enter CTest; key retry behavior runs without historical /tmp evidence; launch and runner weak assertions are replaced; both ordinary pytest and package gates are verified.
worktree: /home/matianyi/Projects/ros-moveit-demo/.worktrees/20260924-pytest-opt-021323
branch: codex/20260924-pytest-opt-021323
base_commit: fd7348aa27361750f7e2e7954df53ef75e96545c
current_commit: 54cd6f9c
evidence_root: /data/work/so101-evidence/pytest-suite-optimization/20260924-pytest-opt-021323
confirmed_conclusions:
  - Static review found four unregistered teleop test files, two identical launch test bodies, historical /tmp fixture skips, and a self-asserting JSON round trip.
disproven_routes: []
open_hypotheses:
  - The review findings can be corrected without reducing unique behavioral coverage.
latest_checkpoint: CP-005
next_experiment: NONE

checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The worktree can collect and execute the existing ordinary test suites using a task-owned overlay and NVMe scratch.
working_tree_status: Untracked reviewed plan and this ledger only.
owned_processes: NONE
preserved_processes: Existing tmux codex session; no ROS simulation processes observed.
confirmed_conclusions:
  - Source branch main at fd7348aa27361750f7e2e7954df53ef75e96545c; submodule third_party/mujoco_ros2_control uninitialized in task worktree.
disproven_routes: []
open_risks:
  - Exact pytest interpreter and complete underlay closure remain to be determined.
next_command: Check task worktree dependencies and identify exact Python/overlay before baseline tests.

experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: Baseline ordinary tests are collectible in this isolated worktree with task-owned dependencies and scratch.
prediction: Collection and directed baseline commands distinguish environment setup failures from test failures.
single_variable: Isolated task worktree at current source commit.
lifecycle: ISOLATED_STACK
preconditions:
  - No SO-101 simulation stack started for this task.
  - Exact interpreter and overlay checked before tests.
success_criteria:
  - Baseline collection, skip counts, and selected red boundaries recorded.
failure_criteria:
  - Intended test boundary runs and produces a failing assertion.
invalid_criteria:
  - Missing package setup, incomplete underlay, or collection failure before intended tests run.
provenance:
  source_commit: fd7348aa27361750f7e2e7954df53ef75e96545c
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/.worktrees/20260924-pytest-opt-021323/install
  runtime_executable: /usr/bin/python3 (CTest); /data/work/so101-evidence/pytest-suite-optimization/20260924-pytest-opt-021323/env/bin/python (direct pytest)
  ros_domain_id: UNSET
  gz_partition: UNSET
commands:
  - command: ctest --test-dir build/so101_teleop -N
    exit_code: 0
  - command: run-pytest.sh task1-red-05 src/so101_teleop -- test/test_ctest_registration.py
    exit_code: 1
  - command: run-pytest.sh task1-green-01 src/so101_teleop -- test/test_ctest_registration.py
    exit_code: 0
observed:
  - CTest initially registered 89 tests; after five registrations it listed 94.
  - New contract produced 1 failure before registration and 3 passes after registration, with 8 xdist workers.
  - First CTest execution exposed a Linux-only incomplete test double; correction committed in Task 1.
  - New five CTest cases ran with exit 0, but retry cases still had 5 historical fixture skips.
inferred: []
conclusion: Baseline registry gap and test-double defect reproduced; Task 1 fixes verified at the targeted boundaries.
evidence:
  - /data/work/so101-evidence/pytest-suite-optimization/20260924-pytest-opt-021323/task-ledger.txt
decision: KEEP
next_experiment: NONE

checkpoint_id: CP-002
last_valid_experiment: EXP-001
current_hypothesis: Task 2 can replace five historical fixture skips while preserving production service assembly.
working_tree_status: Isolated branch has commit 71b586a7 plus untracked plan and ledger.
owned_processes: dst-pytest-opt-20260924 tmux session; no ROS simulation stack launched for this task.
preserved_processes: Existing unrelated tmux and ROS processes remain untouched.
confirmed_conclusions:
  - Task 1 RED/GREEN and new CTest cases verified; see results/task-1-status.md in evidence root.
disproven_routes: []
open_risks:
  - Full ordinary xdist and package gates remain pending.
  - Five registered retry test cases still skip due to missing historical /tmp fixture.
next_command: Continue Task 2 in the running DeepSeek Harness TUI session.

checkpoint_id: CP-003
last_valid_experiment: EXP-002
current_hypothesis: Deterministic retry and campaign fixtures preserve the historical regression boundaries.
working_tree_status: Task 1 through Task 4 committed on isolated branch; plan and ledger remain untracked.
owned_processes: DeepSeek TUI interrupted at user's request; its background baseline run was interrupted after no progress and recorded exit 2. A separately started full teleop gate remains in progress and is being inspected.
preserved_processes: Unrelated ROS and tmux sessions untouched.
confirmed_conclusions:
  - Task 2's endpoint, owner and campaign projection files ran with 8 workers: 46 passed, 0 skipped, exit 0, in results/takeover-task2-targeted-01.
  - Explicit recorded replay ran with absent evidence: 4 skipped with clear not-run reasons, exit 0, in results/takeover-task2-replay-absent-01.
  - The baselineB teleop run advanced to 1003 passes and 43 failures but hung near the end; interrupted at 188 seconds and exit 2, so it is not a complete baseline.
disproven_routes: []
open_risks:
  - Complete ordinary xdist and package gates remain pending; baseline suites already showed many failures outside changed boundaries.
  - Recorded macOS replay bytes are absent on this host; the explicit replay entry is not validated against them.
next_command: Finish full suite, CTest and package gates; compare baseline failures and audit skips.

experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: Replacing fixed /tmp state with production service composition can exercise the same retry boundaries on this host.
prediction: The three task-2 files run without historical fixture skips, and the absent-recording replay reports itself as not run.
single_variable: Task-2 test and fixture code at commit 0bf311a6.
lifecycle: ISOLATED_STACK
preconditions:
  - Exact task venv and task-local NVMe scratch verified by run-pytest.sh for controller and all 8 workers.
  - No simulator or physical robot started.
success_criteria:
  - All deterministic task-2 cases pass with no skips.
failure_criteria:
  - A retry or campaign assertion fails in the intended boundary.
invalid_criteria:
  - Collection or environment setup fails before the assertion runs.
provenance:
  source_commit: 0bf311a6
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/.worktrees/20260924-pytest-opt-021323/install
  runtime_executable: /data/work/so101-evidence/pytest-suite-optimization/20260924-pytest-opt-021323/env/bin/python
  ros_domain_id: 197
  gz_partition: pytest-opt-021323
commands:
  - command: run-pytest.sh takeover-task2-targeted-01 <worktree> -- <three task-2 files>
    exit_code: 0
  - command: run-pytest.sh takeover-task2-replay-absent-01 <worktree> -- <explicit replay file>
    exit_code: 0
observed:
  - Deterministic files: 46 passed, 0 skipped in 3.09 seconds.
  - Explicit replay: 4 skipped because the recorded macOS roots were absent, in 1.77 seconds.
inferred: []
conclusion: Task-2 ordinary tests exercise the targeted boundaries without fixed historical state; raw recorded replay is separately opt-in.
evidence:
  - /data/work/so101-evidence/pytest-suite-optimization/20260924-pytest-opt-021323/results/takeover-task2-targeted-01
  - /data/work/so101-evidence/pytest-suite-optimization/20260924-pytest-opt-021323/results/takeover-task2-replay-absent-01
decision: KEEP
next_experiment: Full ordinary and package gates.

Task 5: Ruling: Fix the test-only `HoldProxy` teardown even though it is outside the four planned files — three unrelated ordinary teleop cases hung indefinitely in both the untouched baseline and current tree because `Server.wait_closed()` waited on active proxy handlers; serial `--full-trace` located the wait at `unified_child_harness.py:156`. Cancelling owned handlers before waiting makes all six two-channel tests pass in 0.98 seconds with 8 workers. Cost if wrong: the harness teardown has a broader lifecycle contract than these six tests exercise; production code is unchanged. Commit 8fb2ea8f; RED evidence `takeover-two-channel-serial-01`, GREEN evidence `takeover-two-channel-green-01`.

Task 1: Ruling: Remove the pre-existing static `EXPERT_VALIDATION_TESTS` registration list after the new directory-to-CMake contract exposed its drift — maintaining two independent lists reintroduces the exact registration gap Task 1 fixes. Cost if wrong: the old expert-validation-only registry assertion no longer runs, while the new all-test registry contract covers its full set and more. Commit b591e8e7; full RED `takeover-full-teleop-02`, targeted GREEN `takeover-registry-contract-green-01` (8 passed).

Final review: Important finding fixed in 54cd6f9c — the deterministic retry fixture lacked the macOS MPS v5 document, and a Linux-only assertion lost its platform override. The fixture now copies the real v5 document, the Linux case uses a test-scoped production-module platform override, and a new case exercises the macOS branch with the document parser told `darwin`. Targeted gate `takeover-macos-retry-targeted-01`: 11 passed in 2.04 seconds (8 workers). Raw macOS execution remains unverified on this Linux host.

checkpoint_id: CP-004
last_valid_experiment: EXP-002
current_hypothesis: Final branch changes pass targeted gates and the remaining full-suite failures predate this task.
working_tree_status: Branch head 54cd6f9c; plan and ledger untracked.
owned_processes: No DeepSeek TUI session or simulator; package-gate pytest/CTest runs only.
preserved_processes: Unrelated ROS and tmux sessions untouched.
confirmed_conclusions:
  - CTest changed-file selection: 8/8 passed under exact /usr/bin/python3, results/takeover-ctest-changed-02.
  - Complete ordinary demo_py 8-worker gate at 228fb2b6+ changes: 27 failed, 3745 passed, 150 skipped, 5 errors; baseline snapshot also failed (26 failed, 3747 passed, 150 skipped, 5 errors). Changed launch file targeted gate: 17 passed.
  - Complete ordinary teleop 8-worker gate before final macOS fixture fix: 41 failed, 1043 passed, 1 skipped; baseline incomplete run had 43 failures and 19 skips before interruption.
  - Teleop colcon CTest finished but test-result reported 64 failures out of 1180 cases; it did not pass. One earlier package run was terminated mid-run and excluded from conclusions.
disproven_routes: []
open_risks:
  - Final full ordinary teleop gate and package gates after 54cd6f9c remain pending.
  - Raw macOS replay and actual macOS profile execution cannot run on ai-station.
next_command: Complete package demo_py, rerun final teleop gates, report evidence and remaining failures.

checkpoint_id: CP-005
last_valid_experiment: EXP-002
current_hypothesis: Final branch has no failures in changed test boundaries; two full package gates remain red on existing host and platform assumptions.
working_tree_status: Code committed through 54cd6f9c; plan and ledger awaiting documentation commit.
owned_processes: NONE. DeepSeek tmux task session stopped after user handoff; no task pytest, colcon, simulator or robot process remains.
preserved_processes: Unrelated codex and act-data-rebase tmux sessions and unrelated ROS processes untouched.
confirmed_conclusions:
  - Complete final ordinary teleop 8-worker gate: 1086 collected, 41 failed, 1044 passed, 1 skipped in 43.57 seconds; every failure identity is in the incomplete baseline's 43 failures. Results/takeover-full-teleop-final-02.
  - Complete ordinary demo_py 8-worker gate: 3927 collected, 27 failed, 3745 passed, 150 skipped, 5 errors in 29.01 seconds. Results/takeover-full-demo_py-02.
  - Final teleop package gate: all 94 CTests executed serially, 1180 tests, 52 failures, 1 skipped; `colcon test` exit 0 but `test-result --verbose` exit 1. Results/takeover-package-teleop-final-04.
  - Demo_py package gate: 3927 tests, 16 failures, 5 errors, 150 skipped and 12 explicit_ml deselected; `colcon test` exit 0 but `test-result --verbose` exit 1. Results/takeover-package-demo_py-02.
  - Changed CTest selection 8/8 passed, and final retry Linux/macOS branch targeted 11/11 passed with 8 workers.
  - Raw recorded macOS batches are absent on this host; explicit replay reports 4 named not-run skips.
disproven_routes:
  - A parallel CTest package run is not a reliable final acceptance on this host: several attempts received SIGTERM before completion. Serial CTest did finish all 94 registered cases.
open_risks:
  - Ordinary full-suite gates are red from unchanged macOS host assumptions, ROS domain/resource assumptions, and an external ffmpeg encoder check; these were not part of this test optimization scope.
  - Actual macOS runtime execution of the new MPS fixture and raw recorded replay remain unverified on ai-station.
next_command: Commit plan and ledger, verify git state and report result without claiming green package gates.

evidence_status:
  retained: /data/work/so101-evidence/pytest-suite-optimization/20260924-pytest-opt-021323 (results, scripts, logs, JUnit/XML, task venv and scratch pending cleanup authorization)
  archived: none
  deletion_candidates: 66 task-owned scratch entries; task venv; short /run/user/1000/so101-opt.* socket directories; superseded /tmp/so101-debug-20260924-pytest-opt-021323, /tmp/so101-debug-task2, /tmp/b1.log, /tmp/b2.log, /tmp/b3.log
  deletion_performed: none
