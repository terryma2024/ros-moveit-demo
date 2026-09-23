---
task_id: so101-unified-main-merge-20260923
goal: Preserve both published histories, publish the descendant fix on the unified branch, then integrate the verified branch into main.
success_contract: origin/codex/so101-unified-webapp contains both old remote and new local tips; origin/main contains the verified unified tip; no force push, lost remote-only commit, or unverified merge.
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: b352f71178b276ef60ab26e2acde0ccfc274b7c8
current_commit: b352f71178b276ef60ab26e2acde0ccfc274b7c8
evidence_root: /tmp/so101-debug-unified-main-merge-20260923-b352f711
confirmed_conclusions:
  - CP-001: Local b352f711 includes the descendant fix; origin/codex/so101-unified-webapp is still 5c946cfd, before the rebase; origin/main 77d763bb is an ancestor of local HEAD.
disproven_routes:
  - A direct non-force push of local HEAD to the old remote unified ref; the earlier attempt was rejected as non-fast-forward.
open_hypotheses:
  - Whether the published feature and main refs remain stable through the final gates and push.
latest_checkpoint: CP-002
next_experiment: EXP-002
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
status: PLANNED
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
    exit_code: PENDING
observed: []
inferred: []
conclusion: PENDING
evidence:
  - /tmp/so101-debug-unified-main-merge-20260923-b352f711/feature-history-join.txt
decision: PENDING
next_experiment: EXP-003
```
