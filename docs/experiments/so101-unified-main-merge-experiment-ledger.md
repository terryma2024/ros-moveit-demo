---
task_id: so101-unified-main-merge-20260923
goal: Preserve both published histories, publish the descendant fix on the unified branch, then integrate the verified branch into main.
success_contract: origin/codex/so101-unified-webapp contains both old remote and new local tips; origin/main contains the verified unified tip; no force push, lost remote-only commit, or unverified merge.
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: b352f71178b276ef60ab26e2acde0ccfc274b7c8
current_commit: HEAD in the named feature worktree; base was b352f71178b276ef60ab26e2acde0ccfc274b7c8
evidence_root: /tmp/so101-debug-unified-main-merge-20260923-b352f711
confirmed_conclusions:
  - CP-003: Origin's unified feature branch contains the old published tip and the descendant fix through history join 10fdb21c.
  - CP-004: The web, both complete eight-worker Python module suites, and the clean installed browser suite passed on macOS.
disproven_routes:
  - A direct non-force push of local HEAD to the old remote unified ref; the earlier attempt was rejected as non-fast-forward.
open_hypotheses:
  - Whether the published feature and main refs remain stable through the final gates and push.
latest_checkpoint: CP-004
next_experiment: EXP-004
---

## CP-001: integration handoff

The user explicitly authorized integration into `codex/so101-unified-webapp` and continuation of the unfinished `main` merge. The earlier instruction to avoid `dst` and `dsh` remains in force. `git fetch origin main codex/so101-unified-webapp codex/so101-descendant-helper-orphans-20260923` exited 0; remote SHA readback matched local tracking refs.

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The published feature chain was rebased onto current main and only needs a history-preserving merge of its old remote tip.
working_tree_status: Both linked worktrees clean before this ledger was created; main submodule uninitialized, not a source edit.
owned_processes: NONE launched by this integration task.
preserved_processes: Existing foreign tmux and host processes are not part of the merge.
confirmed_conclusions:
  - Local b352f711 descends from origin/main 77d763bb; old remote feature tip is 5c946cfd.
  - Git reflog records the rebase onto 77d763bb, then 4f39f618 conflict integration, then the two descendant fix commits.
disproven_routes:
  - Direct push to old remote feature ref is a fast-forward; prior non-force push was rejected.
open_risks:
  - Rebasing changed 470 feature commit IDs and the fork gitlink; correspondence requires readback before recording old remote history as merged.
next_command: git range-diff 5b8d1231..origin/codex/so101-unified-webapp 77d763bb..4f39f618
```

## EXP-001: compare published and rebased feature histories

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: The local rebased chain includes the content of the published old feature tip, including its conflict resolutions.
prediction: Range-diff reports matching commits or explainable conflict adaptations; branch tree changes beyond old tip are accounted for by new main and the descendant fix.
single_variable: NONE (read-only ancestry and tree comparison)
lifecycle: REUSE_STACK
preconditions:
  - Clean local feature and main worktrees; freshly fetched origin refs; no merge in progress.
success_criteria:
  - Every old-only change is accounted for before a history-joining merge; no uncertain remote-only content.
failure_criteria:
  - An old-only code or data change is absent from local HEAD.
invalid_criteria:
  - Fetch moved during analysis or working tree became dirty for another reason.
provenance:
  source_commit: b352f71178b276ef60ab26e2acde0ccfc274b7c8
  install_overlay: NONE (Git comparison only)
  runtime_executable: /usr/bin/git
  ros_domain_id: UNSET
  gz_partition: UNSET
commands:
  - command: git range-diff 5b8d1231..origin/codex/so101-unified-webapp 77d763bb..4f39f618
    exit_code: 0
observed:
  - 462 old commits have patch-equivalent rebased commits; eight old commits lack exact patch equivalence. Range-diff identifies two omitted macOS fork-pin commits and six altered patch identities, including the runtime, parallel-test, and macOS gate adaptations.
  - The old fork pin 85d2a5c and current pin 5a590b2 are siblings: current pin merges the prior vendor-rpath work 6591771 and the staged MuJoCo header fix f89033c. The old pin adds a test expecting an extra vendor rpath, whereas the current test expects only @loader_path, matching the new fork contract.
  - The rebase reconciliation commit 4f39f618 updates both dependency locks, the backend checker, the fork gitlink, and the macOS install contract tests. The old remote tree has no unaccounted code addition against the rebased feature plus current main.
  - A dry-run recursive merge produced conflicts in nine paths, all within the audited rebase adaptations; the existing feature tree is the reviewed resolution.
inferred:
  - Joining the published parent with Git's ours strategy retains remote ancestry and the reviewed rebased tree without replaying obsolete conflict resolutions.
conclusion: VALID; all old-only code changes are accounted for or deliberately superseded by the current main-compatible fork contract.
evidence:
  - /tmp/so101-debug-unified-main-merge-20260923-b352f711/range-diff.txt
decision: Proceed with a no-fast-forward history join using the reviewed feature tree.
next_experiment: EXP-002
```

## CP-002: published feature history audited

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-001
current_hypothesis: The old published feature parent can be joined while retaining the existing, tested feature tree.
working_tree_status: Only this ledger and two targeted whitespace fixes are pending before the history join.
owned_processes: NONE
preserved_processes: Existing foreign processes remain untouched.
confirmed_conclusions:
  - The rebased feature includes the old published behavior, with the fork rpath expectation intentionally updated.
  - The recursive merge conflicts are confined to the audited rebase conflict resolutions.
open_risks:
  - The remote ref may move before push; verify it again and use a normal fast-forward push.
next_command: git merge -s ours --no-ff origin/codex/so101-unified-webapp
```

## EXP-002: join the published feature history

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: A history-only merge preserves the reviewed feature tree and makes both feature tips ancestors.
prediction: The merge tree equals the pre-merge tree, both old remote and rebased tip are ancestors, and a normal push fast-forwards the remote feature ref.
single_variable: Add the old published feature tip as a second parent using the ours merge strategy.
lifecycle: REUSE_STACK
preconditions:
  - Commit the ledger and whitespace cleanup; feature worktree clean; old remote tip unchanged.
success_criteria:
  - Identical pre/post tree IDs, both parents reachable, origin feature ref equals local merge tip after normal push.
failure_criteria:
  - Tree changes, wrong parents, or remote rejects normal push.
invalid_criteria:
  - Remote moved after audit, or worktree has unrelated edits.
provenance:
  source_commit: b352f71178b276ef60ab26e2acde0ccfc274b7c8
  install_overlay: NONE (Git history only)
  runtime_executable: /usr/bin/git
  ros_domain_id: UNSET
  gz_partition: UNSET
commands:
  - command: git merge -s ours --no-ff origin/codex/so101-unified-webapp
    exit_code: 0
observed:
  - Merge commit 10fdb21c has first parent c31b6842 and second parent old published tip 5c946cfd.
  - Both 10fdb21c and c31b6842 have tree 5206ee487f5a39bc3ea729df64036af77c3b1c4e.
  - Both old tip 5c946cfd and descendant-fix tip b352f711 are ancestors of merge tip.
  - Normal push advanced origin/codex/so101-unified-webapp from 5c946cfd to 10fdb21c; ls-remote readback matched.
  - git diff --check origin/main...HEAD exited 0.
inferred:
  - The published feature history and current rebased work are joined without a tree change.
conclusion: VALID; feature history joined and published without force push.
evidence:
  - /tmp/so101-debug-unified-main-merge-20260923-b352f711/feature-history-join.txt
decision: Run current feature gates before main integration.
next_experiment: EXP-003
```

## CP-003: unified feature history published

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-002
current_hypothesis: The merged feature tree still satisfies the macOS package, web, and installed acceptance gates.
working_tree_status: This ledger update is pending; no code changes after 10fdb21c.
owned_processes: NONE
preserved_processes: Existing foreign processes remain untouched.
confirmed_conclusions:
  - origin/codex/so101-unified-webapp now contains both the old published and descendant-fix tips.
open_risks:
  - Fresh verification of the feature tree and the installed acceptance suite is pending.
next_command: Run the feature verification gates under this task's registered evidence root.
```

## EXP-003: feature verification before main integration

```yaml
experiment_id: EXP-003
status: SUPERSEDED_BY_EXP-003A_THROUGH_EXP-003C
prior_experiment: EXP-002
hypothesis: The history-joined feature tree passes the web unit/build, relevant Python package, and installed suite gates on this macOS host.
prediction: All runnable gates exit zero, except explicitly documented host skips; test reports and exact environment provenance are retained.
single_variable: NONE (verification of tree 5206ee48)
lifecycle: REUSE_STACK
preconditions:
  - Exact Bun and ROS Python executables verified; no foreign service cleanup.
success_criteria:
  - Web unit and build pass, ordinary Python tests have no regression, and installed E2E suite passes or has explained platform skips.
failure_criteria:
  - Product test or build failure in current tree.
invalid_criteria:
  - Collection/environment fails before intended boundary; classify separately.
provenance:
  source_commit: 10fdb21c107c7ad6d7d520c5c34b59c61c933a4e
  install_overlay: /opt/data/so101/workspace/install
  runtime_executable: /opt/ros2_jazzy/.venv/bin/python; /opt/homebrew/bin/bun
  ros_domain_id: UNSET
  gz_partition: UNSET
commands:
  - command: bun run test && bun run build
    exit_code: PENDING
  - command: Python package pytest gate with the exact ROS environment
    exit_code: PENDING
  - command: bun run test:e2e:installed
    exit_code: PENDING
observed: []
inferred: []
conclusion: PENDING
evidence:
  - /tmp/so101-debug-unified-main-merge-20260923-b352f711/web-unit.log
  - /tmp/so101-debug-unified-main-merge-20260923-b352f711/web-build.log
  - /tmp/so101-debug-unified-main-merge-20260923-b352f711/python-package.log
  - /tmp/so101-debug-unified-main-merge-20260923-b352f711/installed-e2e.log
decision: PENDING
next_experiment: EXP-004
```

The first installed suite finished in 188 seconds: 20 passed, two platform skips, three failed.
S06 reached a terminal, cleanup-complete first-pass projection but an immediate retry received
`VALIDATION_RECOVERY_REQUIRED`; its stored owner row still said RUNNING when the API call arrived.
Two S15 windows received `UPSTREAM_PROJECTION_INVALID` while polling the first-pass campaign.
The complete retained journal of each failed campaign verified in a fresh read-only replay after
the run (23 events ending in `CLEANUP_COMMITTED`), so the cause lies in a live transition, not
persistently invalid journal bytes. The suite's fixture reaped every named test process; one S15
teardown initially reported a process leak, but host readback after suite exit found no remaining
task-owned helper/launcher process. The failure artifacts and screenshots remain under
`installed-full/`. The next targeted run adds task-overlay-only diagnostic logging of the
underlying projection error; that overlay will be restored from source before final acceptance.

### EXP-003 runner correction before package retry

The first package command exited 1 with eight collection errors before any test assertion. The
direct fixed-Python `rclpy` import proof passed under the same sourced overlays and task scratch;
the package invocation then inserted `/usr/bin/time` ahead of Python. That protected macOS process
boundary removed `DYLD_LIBRARY_PATH`, causing `@rpath/librosidl_typesupport_c.dylib` to fail in
the xdist workers. This is an INVALID environment run, not a RED product result. The next command
removes only `/usr/bin/time`, retains the same source tree, overlays and test selection, and records
elapsed time using zsh before/after timestamps outside the process-launch boundary. The first
scratch, basetemp and IPC directories remain deletion candidates, with no deletion performed.

The corrected combined-package run collected tests and ran for 69 seconds: 3,865 passed, nine
skipped, 54 failed, eight collection errors. The collection errors are a duplicate module basename
(`test_task_artifacts.py`) across two package directories collected in one pytest invocation;
run each package separately. Most failures in `test_parallel_batch_resources.py` reused fixed
`/opt/data/tmp/rr*` names left by an earlier task; its fixture chooses `TMPDIR`'s parent, so the
next scratch must be a unique short task-owned parent. Two macOS assertions use Linux `/proc` or
assume every pytest `tmp_path` is under `/private/tmp`; they are genuine test-portability defects,
to be evaluated in their own package run. `test_unix_address_strategy.py` also loaded a stale
installed `unix_address.py` rather than the source revision; installation provenance must be
corrected before treating that result as a source failure. No retained scratch was deleted.

### EXP-003A: repair macOS package-test assumptions

```yaml
experiment_id: EXP-003A
status: VALID
prior_experiment: EXP-003 corrected package attempt
hypothesis: Three test failures are assertions tied to Linux procfs or the pytest temp location, while the underlying portable contracts are correct.
prediction: Restrict the procfs case to Linux, create the macOS /tmp alias sample under its actual shared directory, and assert the canonical private base without assuming its grandparent is /.
single_variable: Correct those three test preconditions/assertions; keep production code unchanged.
lifecycle: REUSE_STACK
preconditions:
  - The 69-second RED run and exact tracebacks are retained; no old scratch deletion.
success_criteria:
  - All three targeted tests pass or are intentionally skipped on macOS, then package gate runs from current source in isolated namespace.
failure_criteria:
  - A targeted assertion still fails against the current source package.
invalid_criteria:
  - Tests load stale installed modules or collide with fixed scratch names.
provenance:
  source_commit: 10fdb21c107c7ad6d7d520c5c34b59c61c933a4e
  install_overlay: task-owned source package overlay pending
  runtime_executable: /opt/ros2_jazzy/.venv/bin/python
  ros_domain_id: 227
  gz_partition: so101-mainmerge-227
commands:
  - command: Targeted macOS portable tests under exact Python and task source overlay
    exit_code: 0
observed:
  - Corrected portability assertions passed in the complete demo eight-worker gate.
inferred: []
conclusion: The test preconditions now reflect macOS procfs and temporary-path semantics.
evidence:
  - /tmp/so101-debug-unified-main-merge-20260923-b352f711/python-package-retry.log
decision: Retain the corrections and proceed to complete module gates.
next_experiment: EXP-003B
```

### EXP-003B: required eight-worker teleop package gate

The user required every module's complete ordinary pytest scope to pass with
`min(8, logical CPU count)` workers and explicitly rejected a serial fallback. This macOS host
reports 10 logical CPUs, so the mandatory gate uses `-n 8`. The prior serial teleop result
(910 passed, one skipped) is diagnostic only. The revised `so101-dev` skill and its test references
state this rule and require resource isolation fixes before a gate can be called complete.

```yaml
experiment_id: EXP-003B
status: VALID
prior_experiment: EXP-003A
hypothesis: The teleop complete package scope passes under eight xdist workers once every test owns its child and IPC resources.
prediction: The first eight-worker run either passes or exposes exact shared-resource collisions to repair and rerun without reducing worker count.
single_variable: Teleop package test concurrency changes from serial diagnostic to required eight-worker gate.
lifecycle: REUSE_STACK
preconditions:
  - Demo package eight-worker gate passed 3918/3918 with ten skips; teleop serial diagnostic passed 910/910 with one skip.
success_criteria:
  - Entire src/so101_teleop/test/teleop scope passes with -n 8 and no leaked task-owned descendants.
failure_criteria:
  - Any product or test assertion failure under eight workers.
invalid_criteria:
  - Runner environment fails before collection.
provenance:
  source_commit: 10fdb21c107c7ad6d7d520c5c34b59c61c933a4e plus pending test and skill edits
  install_overlay: /tmp/so101-debug-unified-main-merge-20260923-b352f711/install-overlay
  runtime_executable: /opt/ros2_jazzy/.venv/bin/python
  ros_domain_id: 227
  gz_partition: so101-mainmerge-227
commands:
  - command: python -m pytest -n 8 --dist loadscope src/so101_teleop/test/teleop
    exit_code: 0
observed:
  - Full scope collected 911 items and finished with 910 passed and one skipped on eight workers.
inferred: []
conclusion: Worker-specific IPC bases and short fixed-helper roots removed the parallel collisions.
evidence:
  - /tmp/so101-debug-unified-main-merge-20260923-b352f711/python-teleop-parallel.log
decision: Count the eight-worker run as the teleop module gate.
next_experiment: EXP-003C
```

The first required eight-worker teleop run collected and executed the whole module: 900 passed,
one skipped, ten failed in 30 seconds. Eight bridge failures had children exit by SIGTERM while
other workers' autouse teardown scanned the shared `SO101_IPC_SOCKET_BASE`; one worker could
terminate another worker's owned child. Two fixed-helper cases put a control socket under pytest's
deep `tmp_path`, exceeding Darwin's Unix socket limit. The next correction assigns each xdist
worker its own short IPC base and keeps the two helper batch roots under that worker-owned base.
It retains eight workers and the full collection scope.

The corrected three-file subset passed 17/17 with eight workers. The complete teleop scope then
passed 910/910 with one skip using eight workers on this ten-logical-CPU Mac, in 30 seconds. The
demo package complete scope passed 3918/3918 with ten skips using eight workers, in 32 seconds.
Both package gates used unique scratch parents and the task-owned install overlay; JUnit and
environment readback are in the registered evidence root. The diagnostic serial teleop run is not
counted as the package gate.

### EXP-003C: installed browser acceptance

```yaml
experiment_id: EXP-003C
status: VALID
prior_experiment: EXP-003B
hypothesis: The current installed Python package files and newly built web assets pass the macOS installed Playwright suite.
prediction: The suite reports every runnable installed case passed, with only explicitly supported platform skips.
single_variable: Use a task-owned copy of the fixed installed prefix, replacing its one stale Python module and web bundle with current source artifacts.
lifecycle: REUSE_STACK
preconditions:
  - Exact Bun, Python, Chrome, model paths, dependency underlays, and task-owned install prefix verified.
success_criteria:
  - Full installed suite passes; server children exit and report artifacts stay under the registered evidence root.
failure_criteria:
  - Installed route, campaign, retry, or browser assertion fails.
invalid_criteria:
  - Environment or dependency preflight refuses before a product boundary is exercised.
provenance:
  source_commit: 10fdb21c107c7ad6d7d520c5c34b59c61c933a4e plus pending test and skill edits
  install_overlay: /tmp/so101-debug-unified-main-merge-20260923-b352f711/install-overlay
  runtime_executable: /opt/homebrew/bin/bun; /opt/ros2_jazzy/.venv/bin/python; /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
  ros_domain_id: 227
  gz_partition: so101-mainmerge-227
commands:
  - command: bun run test:e2e:installed
    exit_code: 0
observed:
  - Final source-identical install overlay passed 23 cases with two platform skips.
inferred: []
conclusion: The installed browser acceptance suite passes on macOS after S06 owner-exit synchronization.
evidence:
  - /tmp/so101-debug-unified-main-merge-20260923-b352f711/installed-e2e.log
decision: Proceed to commit and main integration; retain first-run S15 traces for follow-up.
next_experiment: EXP-004
```

The diagnostic complete rerun passed 23 cases with two platform skips in 185 seconds; the only
projection diagnostics were the deliberate tampered-artifact negative cases. The S06/S15 failures
therefore depend on timing. Their stored owner records and later valid journals fit two competing
hypotheses: a retry begins before the first-pass owner exits, and a reader samples a canonical
`RESULT_COMMITTED` before its matching `POINT_TERMINAL`. A small repeated diagnostic run of the
affected cases will distinguish these without mutating production source or reducing any gate.

## CP-004: final verification before branch publication

The repeated S06 and S15 cleanup-to-dequeue cases passed 10/10. S06's first-run refusal was
explained by the first-pass owner still running after the cleanup-complete projection. The installed
test now waits for that recorded owner PID to exit before exercising retry idempotency. The two S15
projection failures did not recur in five repeats of the affected case, the diagnostic full suite,
or the final full suite; their exact transient cause remains unconfirmed. No production projection
rule was relaxed. The temporary diagnostic print was removed from the task-owned installed copy;
`cmp` confirmed it matches the unmodified source `production.py` before the final run.

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-003C
working_tree_status: Skill, portability test, xdist isolation, S06 timing, and ledger edits pending commit.
owned_processes: No helper or installed launcher from this task remained after the final suite.
confirmed_conclusions:
  - macOS reported 10 logical CPUs; both Python modules used pytest-xdist 3.8.0 with 8/8 workers and complete ordinary test directories.
  - so101_demo_py finished with 3918 passed and 10 skipped in 31.79 seconds; exit 0.
  - so101_teleop finished with 910 passed and 1 skipped in 29.67 seconds; exit 0.
  - Web unit tests finished with 53 files and 300 tests passed; Bun build exited 0.
  - Clean installed Playwright suite finished with 23 passed and 2 macOS platform skips in 3.1 minutes; exit 0.
  - S06/S15 affected-case repeat finished with 10 passed; exit 0.
open_risks:
  - Initial S15 transient projection errors did not reproduce; the failing first-run trace and valid later journals are retained for future diagnosis.
next_command: Commit and normally push the reviewed feature tree, fast-forward main, and normally push both mapped main remotes after SHA readback.
```

Evidence retained under `/tmp/so101-debug-unified-main-merge-20260923-b352f711`:
`web-unit.log`, `web-build.log`, `python-demo-final.log`, `python-demo-final.xml`,
`python-teleop-final-parallel.log`, `python-teleop-final-parallel.xml`, corresponding environment
and scratch path proofs, `installed-e2e.log`, `installed-diagnostic-full.log`,
`installed-repeated.log`, `installed-final.log`, and their installed run directories. The initial
failed run and diagnostic run remain auditable; no batch was moved to an archive. The test scratch,
basetemp, and IPC directories named in `python-*-scratch.txt`, plus the copied `install-overlay`
after final readback, are deletion candidates only. Nothing was deleted.
