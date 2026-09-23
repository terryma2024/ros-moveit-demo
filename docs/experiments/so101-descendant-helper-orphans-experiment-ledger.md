---
task_id: so101-descendant-helper-orphans-20260923
goal: Find and stop accumulation of installed-suite descendant_helper.py processes.
success_contract: A failed or interrupted S07 run cannot leave an unbounded test helper; fixture teardown clears attributable survivors.
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: 4f39f618f24894d5f2d962cbaa0f913d688af9c6
current_commit: 9fd86e7f29c762e11451fff1457e394a548d91b7 (verified implementation commit; final ledger-only commit follows)
evidence_root: /tmp/so101-debug-descendant-orphans-20260923-4f39f618
confirmed_conclusions:
  - EXP-001: 39 resident helpers at initial inventory, all PPID 1; S07 deliberately forks a survivor, and its second survivor cleanup is outside finally.
  - EXP-001: PID 5212 appears in an S07 coordinator log under the previous task root; fixture residue check searches serverRoot in argv, which the current helper omits.
  - EXP-002: The helper's lifetime and argv marker tests failed at the intended boundary before the fix and passed afterward.
  - EXP-003: Test-root teardown now terminates only exact attributed descendants; a prefix-collision test failed then passed.
  - EXP-004: After individual identity-checked SIGTERM, all 39 historical helpers exited; fresh S07 passed with zero residue.
disproven_routes:
  - The current process-owner group stop alone prevents these leaks; S07 directly creates a survivor after its leader exits.
open_hypotheses:
  - Historical helpers' exact per-PID source testcase remains partly unknown; all 39 had the same test-only script, PPID 1, and no new attribution argument.
latest_checkpoint: CP-003
next_experiment: NONE
---

## EXP-001: initial process and source inventory

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: The installed S07 fixture produces unattributed long-lived descendants on failure.
prediction: Resident descendants have PPID 1 and at least one PID maps to an S07 coordinator log; the fixture cannot match their argv to serverRoot.
single_variable: NONE
lifecycle: REUSE_STACK
preconditions:
  - Read-only process inventory on Terry-Mac-mini.local; no ROS or Gazebo stack started.
success_criteria:
  - Process, log and source attribution agree.
failure_criteria:
  - No survivor can be linked to S07 or cleanup is unconditional.
invalid_criteria:
  - Process metadata denied or log not attributable to a real PID.
provenance:
  source_commit: 4f39f618f24894d5f2d962cbaa0f913d688af9c6
  install_overlay: NONE (read-only attribution)
  runtime_executable: /opt/homebrew/Cellar/python@3.11/3.11.15_3/Frameworks/Python.framework/Versions/3.11/Resources/Python.app/Contents/MacOS/Python
  ros_domain_id: UNSET
  gz_partition: UNSET
commands:
  - command: ps -axo pid,ppid,pgid,stat,lstart,command | rg descendant_helper.py
    exit_code: 0
  - command: rg -n -g '*.coordinator.log' 'descendant_pid=5212' /tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1
    exit_code: 0
observed:
  - OBSERVED 39 helpers, all PPID 1, in the initial process snapshot.
  - OBSERVED PID 5212 in S07 b39f6 coordinator log; S07 source spawns a second descendant and cleans it outside finally.
  - OBSERVED descendant argv has no per-test runtime marker; fixture checks pgrep -f serverRoot.
inferred:
  - Failure or interruption before S07's late cleanup leaves a survivor invisible to fixture teardown.
conclusion: Confirmed leak path in test helper/fixture lifecycle. Other historical PIDs need attribution before cleanup.
evidence:
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618/initial-processes.txt
decision: KEEP
next_experiment: EXP-002
```

## CP-001

```yaml
checkpoint_id: CP-001
last_valid_experiment: EXP-001
current_hypothesis: A per-test argv marker plus bounded helper lifetime and teardown cleanup closes the ongoing leak path.
working_tree_status: clean before ledger creation
owned_processes: NONE created by this task
preserved_processes: 39 historical descendant_helper.py PIDs; unrelated running pytest shell PID 33929
confirmed_conclusions:
  - EXP-001 leak path confirmed in S07 and fixture source.
disproven_routes:
  - Relying only on product process-owner group cleanup cannot close S07's intentional survivor.
open_risks:
  - Historical helpers include other evidence roots and must be individually attributed before signalling.
next_command: Add RED test for bounded descendant lifetime and argv attribution.
```

## EXP-002: test-owned descendant carries provenance and cannot live forever

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: The old helper loop and missing argv marker are sufficient to create unattributed permanent orphans.
prediction: A real helper does not exit at a test deadline, and a fixed coordinator's descendant argv lacks its batch root; both pass after a bounded-lifetime and marker change.
single_variable: Add test-only helper argv and bounded lifetime.
lifecycle: REUSE_STACK
preconditions:
  - Source commit 4f39f618; no service or robot stack started; /opt/ros2_jazzy/.venv/bin/python verified executable.
success_criteria:
  - Both direct process tests fail at the intended behavior before the change and pass afterward.
failure_criteria:
  - A child survives the configured deadline or the batch-root argument is absent.
invalid_criteria:
  - Collection failure or Darwin AF_UNIX path-length refusal before the target assertion.
provenance:
  source_commit: 4f39f618f24894d5f2d962cbaa0f913d688af9c6 plus uncommitted task patch
  install_overlay: /opt/data/so101/workspace/install
  runtime_executable: /opt/ros2_jazzy/.venv/bin/python
  ros_domain_id: UNSET
  gz_partition: UNSET
commands:
  - command: /opt/ros2_jazzy/.venv/bin/python -m pytest -q test_expert_validation_e2e_installed_port.py -k descendant_helper_exits_after_its_test_lifetime
    exit_code: 1
  - command: /opt/ros2_jazzy/.venv/bin/python -m pytest -q --basetemp=/opt/data/tmp/dh-UWFZ1e/b test_expert_validation_e2e_installed_port.py -k fixed_helper_descendant_survives_leader_exit
    exit_code: 1
  - command: /opt/ros2_jazzy/.venv/bin/python -m pytest -q --basetemp=/opt/data/tmp/dh-OyTtE5/b test_expert_validation_e2e_installed_port.py
    exit_code: 0
observed:
  - OBSERVED lifetime RED timed out after 2 seconds over a real helper; finally reaped it.
  - OBSERVED attribution RED read kernel argv containing only interpreter and script, no batch root.
  - OBSERVED full file GREEN 7 passed in 1.94 seconds.
  - INVALID preliminary collection without ROS environment; INVALID long Darwin socket path before target assertion. Neither counted as code RED.
inferred:
  - A crashed test now leaves its test helper for at most 120 seconds; routine fixture teardown can match it by batch root.
conclusion: Helper lifecycle has bounded survival and exact run attribution without changing product execution.
evidence:
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618/red-lifetime-env.log
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618/red-attribution-short.log
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618/python-full.log
decision: KEEP
next_experiment: EXP-003
```

## EXP-003: fixture teardown after any test result

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: Teardown can safely reap a real descendant by exact test root even if the testcase skipped its own cleanup.
prediction: A real child survives no-op cleanup; an exact-root cleanup ends it while preserving a sibling with the root as a string prefix.
single_variable: Add test-root descendant cleanup to the installed fixture finally block.
lifecycle: REUSE_STACK
preconditions:
  - Two real helper processes started under distinct marker roots; one root is a prefix of the other.
success_criteria:
  - Matching child gone, prefix sibling alive, no leftovers after test finally.
failure_criteria:
  - Matched child remains or sibling is signalled.
invalid_criteria:
  - Spawn or process-state reader fails before both are ready.
provenance:
  source_commit: 4f39f618f24894d5f2d962cbaa0f913d688af9c6 plus uncommitted task patch
  install_overlay: NONE (source TypeScript and test helper)
  runtime_executable: /opt/homebrew/bin/bun
  ros_domain_id: UNSET
  gz_partition: UNSET
commands:
  - command: bun run test src/api/installed-descendant-cleanup.test.ts (no-op cleanup)
    exit_code: 1
  - command: bun run test src/api/installed-descendant-cleanup.test.ts (prefix collision)
    exit_code: 1
  - command: bun run test src/api/installed-descendant-cleanup.test.ts (exact boundary)
    exit_code: 0
  - command: bun run test
    exit_code: 0
  - command: bun run build
    exit_code: 0
observed:
  - OBSERVED no-op RED returned no PID while the child lived.
  - OBSERVED prefix RED selected both PIDs; the corrected boundary selected only the exact root.
  - OBSERVED full Vitest 53 files/300 tests passed; TypeScript and Vite build exited 0.
inferred:
  - Ordinary testcase failures cannot bypass fixture teardown; hard runner death remains bounded by the helper lifetime.
conclusion: Fixture cleanup now has real-process behavior and a prefix-isolation regression test.
evidence:
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618/red-fixture.log
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618/red-prefix.log
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618/green-prefix.log
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618/web-vitest.log
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618/web-build.log
decision: KEEP
next_experiment: EXP-004
```

## EXP-004: installed S07 and historical orphan convergence

```yaml
experiment_id: EXP-004
status: VALID
prior_experiment: EXP-003
hypothesis: The patched installed fixture and bounded helper leave zero new descendants, and the historical idle helper set can be retired without touching other processes.
prediction: S07 passes under the installed test port, identity-checked SIGTERM clears the 39 old helpers, and fresh S07 leaves zero residue.
single_variable: Exact per-PID termination of already orphaned test-only helpers after the code fix.
lifecycle: REUSE_STACK
preconditions:
  - Darwin host; 39 old helpers have PPID 1; no fixed/adaptive helper or installed test server is live; exact start marker, group and argv read before any signal.
success_criteria:
  - S07 passes; 39 exact identities exit; fresh process inventory has zero descendant_helper.py.
failure_criteria:
  - Identity mismatch, a survivor, or a fresh S07 leak.
invalid_criteria:
  - Preflight fails before helper spawn due missing test model paths.
provenance:
  source_commit: 4f39f618f24894d5f2d962cbaa0f913d688af9c6 plus uncommitted task patch
  install_overlay: /opt/data/so101/workspace/install
  runtime_executable: /opt/ros2_jazzy/.venv/bin/python; /opt/homebrew/bin/bun; /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
  ros_domain_id: UNSET
  gz_partition: UNSET
commands:
  - command: bun run test:e2e:installed --grep 'S07 a surviving descendant' (missing model fixture)
    exit_code: 1
  - command: bun run test:e2e:installed --grep 'S07 a surviving descendant' (test-only model fixtures configured)
    exit_code: 0
  - command: identity-checked per-PID SIGTERM from cleanup-plan.json
    exit_code: 0
  - command: bun run test:e2e:installed --grep 'S07 a surviving descendant' (after old orphan cleanup)
    exit_code: 0
observed:
  - INVALID first S07 attempt refused VALIDATION_MODELS_NOT_CONFIGURED before helper spawn.
  - OBSERVED configured S07 passed twice, latest 3.4 seconds, using copied install and test helper port.
  - OBSERVED plan identified 39 PPID-1 helpers with exact two-argument old test script argv; excluded 0.
  - OBSERVED 39/39 received SIGTERM after start-marker and argv recheck; 0 needed SIGKILL; 0 survived; final ps count 0.
inferred:
  - Old helpers came from multiple prior test rounds; precise testcase attribution for every PID remains unavailable because old argv omitted the run marker.
conclusion: Present-process residue cleared and the ongoing test leak path verified in a clean S07 run.
evidence:
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618/s07-installed-configured.log
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618/cleanup-plan.json
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618/cleanup-applied.json
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618/final-processes.txt
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618/s07-installed-post-cleanup.log
decision: KEEP
next_experiment: NONE
```

## CP-002: completion checkpoint

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-004
current_hypothesis: NONE
working_tree_status: Task patch and this ledger pending commit.
owned_processes: NONE; descendant_helper.py count 0 after fresh S07.
preserved_processes: Unrelated tmux and test activity; not signalled.
confirmed_conclusions:
  - EXP-001 S07/fixture had an ongoing orphan path.
  - EXP-002 lifetime and attribution RED/GREEN.
  - EXP-003 fixture cleanup and prefix isolation RED/GREEN.
  - EXP-004 39 exact old helpers terminated; fresh S07 passed with zero residue.
disproven_routes:
  - Product process-owner stop alone covers test-created surviving descendants.
open_risks:
  - A hard-killed test runner may leave a helper for up to 120 seconds; it cannot persist indefinitely.
next_command: git diff --check, commit, and non-force push if remote history permits.
retained_runs:
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618 (all logs, model fixtures, process inventories and receipts).
archived_runs: []
deletion_candidates:
  - This task's /opt/data/tmp/dh-* pytest scratch trees after readback.
  - Temporary owned-descendant-* roots below the registered evidence root after readback.
```

## CP-003: commit, non-force publication and final residue readback

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-004
current_hypothesis: NONE
working_tree_status: Clean after implementation commit 9fd86e7f; this checkpoint is a ledger-only follow-up.
owned_processes: NONE; descendant_helper.py count 0 on final ps readback.
preserved_processes: Unrelated host processes were not signalled.
confirmed_conclusions:
  - EXP-004 fresh S07 passed, 39/39 old test-only helpers exited, zero same-name residue.
  - Implementation commit 9fd86e7f29c762e11451fff1457e394a548d91b7 was pushed to origin/codex/so101-descendant-helper-orphans-20260923.
disproven_routes:
  - Direct ordinary push to origin/codex/so101-unified-webapp is possible without reconciliation; remote rejected it as non-fast-forward.
open_risks:
  - The designated local branch and its remote have divergent history (480 ahead, 470 behind after the implementation commit); no force push or merge was attempted.
next_command: Publish this ledger-only checkpoint to the new remote branch, then verify its tip and a clean worktree.
retained_runs:
  - /tmp/so101-debug-descendant-orphans-20260923-4f39f618.
archived_runs: []
deletion_candidates:
  - This task's /opt/data/tmp/dh-* scratch trees and temporary owned-descendant-* fixture roots; no evidence was deleted.
```
