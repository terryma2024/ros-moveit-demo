# SO-101 Teleop service scripts experiment ledger

```yaml
task_id: so101-teleop-service-scripts-20260923-9c6a7e42
goal: Provide one-command macOS and Linux start/status/cleanup for the installed unified Teleop and Expert Validation service.
success_contract: Both hosts pass dependency preflight; each starts a separate smoke service, reports Validation ready, and cleans up only its recorded service PID. Existing port 8000 services and evidence remain intact.
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: 779b4e67923478d8c95f622db31b5199abbde72f
current_commit: 47006619cfebcc9e13e843c0d3ee25fa4209149c
evidence_root: /opt/data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42 (macOS); /data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42 (ai-station)
low_rate_logs: /tmp/so101-debug-teleop-service-scripts-20260923-9c6a7e42 (per host)
confirmed_conclusions:
  - CP-001: Both existing port 8000 services return Validation ready; neither has an executing campaign.
  - CP-003: The current manager revision passed eight safety unit tests on each host; origin/main was fetched and the branch rebased successfully.
  - EXP-003: The frozen post-rebase manager started and cleaned up isolated installed Validation services on both hosts while preserving both port 8000 services.
disproven_routes:
  - CP-001: /data/work/ws_moveit is not the ai-station checkout; the live checkout is /home/matianyi/Projects/ros-moveit-demo.
open_hypotheses:
  - Full Teleop control remains unavailable in the existing production acceptance services and is outside this script-only repair.
latest_checkpoint: CP-004
next_experiment: NONE
```

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The installed service can be started and cleaned up with a platform-specific sourced environment and recorded PID identity.
working_tree_status: clean before this task; new scripts and this ledger are task-owned.
owned_processes: Existing Mac service PID 13297 in so101-teleop-tailscale-mac; existing ai-station service PID 2118905 in so101-teleop-tailscale-ai.
preserved_processes: Both port 8000 services, Mac static transform publishers, all unrelated ROS/tmux processes.
confirmed_conclusions:
  - Existing Mac and ai-station /health responses report domains.validation=ready and global_state=IDLE.
disproven_routes:
  - Old /data/work/ws_moveit path on ai-station is absent.
open_risks:
  - The current services predate the new manager and have no manager ownership receipt.
next_command: Run isolated port 8014 smoke start/status/cleanup on each host.
```

```yaml
experiment_id: EXP-001
status: INVALID
prior_experiment: NONE
hypothesis: The new manager can prove both installed environments and own a separate service lifecycle.
prediction: Each host doctor and app check succeeds; port 8014 reaches Validation ready; cleanup stops only the recorded PID; port 8000 stays healthy.
single_variable: Use the new service manager on port 8014 and a fresh evidence root.
lifecycle: ISOLATED_STACK
preconditions:
  - Port 8000 services are retained, with no active campaign.
  - Port 8014 is free on both hosts.
success_criteria:
  - Mac and Linux service PIDs pass identity validation and leave no port 8014 listener after cleanup.
  - Both pre-existing port 8000 services remain healthy.
failure_criteria:
  - Any preflight, app check, start, ownership, cleanup, or retained-service check fails.
invalid_criteria:
  - Port 8014 is occupied by another owner, or installed overlays change mid-run.
provenance:
  source_commit: 779b4e67923478d8c95f622db31b5199abbde72f (Mac); 3a750cfac91f2bcb88e5b6d8882d24ac8fa3f1ec (ai-station)
  install_overlay: /opt/data/so101/workspace/install (Mac); /home/matianyi/Projects/ros-moveit-demo/install (ai-station)
  runtime_executable: /opt/ros/jazzy/.venv/bin/python (Mac); /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python (ai-station)
  ros_domain_id: 225 (Mac); 226 (ai-station)
  gz_partition: so101-teleop-tailscale-mac-225 (Mac); so101-teleop-tailscale-ai-226 (ai-station)
commands:
  - command: scripts/so101-teleop-macos.zsh start --host 127.0.0.1 --port 8014 --state-dir /tmp/so101-debug-teleop-service-scripts-20260923-9c6a7e42/state-mac --evidence-root /opt/data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42/smoke-mac
    exit_code: 2 (first revision); 0 (later revisions)
  - command: scripts/so101-teleop-macos.zsh cleanup --state-dir /tmp/so101-debug-teleop-service-scripts-20260923-9c6a7e42/state-mac; Linux equivalent.
    exit_code: 0 (later revisions)
observed:
  - Mac doctor passed. First port 8014 start reached Validation ready but ownership comparison rejected macOS Python.app argv[0]; the exact task-owned PID 21852 was stopped after an empty campaign query. No listener remains on 8014.
  - Later Mac and Linux start/status/cleanup cycles passed, but the manager changed during this experiment. Its first configuration also tried a ROS child bridge that failed for a missing child token, which the existing production services do not enable.
inferred:
  - The initial process identity assumption and unconfigured bridge environment were incorrect. The final manager uses the installed validation service configuration.
conclusion: This mixed-revision experiment cannot count as frozen-code validation; its failures and later diagnostics are retained.
evidence:
  - /opt/data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42
  - /data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42
decision: REPEAT
next_experiment: EXP-002
```

```yaml
checkpoint_id: CP-002
last_valid_experiment: NONE
current_hypothesis: The final manager revision starts the installed Validation service on each platform and stops only its recorded idle PID.
working_tree_status: Task-owned new scripts, test, and this ledger; ai-station main has pre-existing Web UI changes, preserved without edits.
owned_processes: No port 8014 test service remains.
preserved_processes: Mac port 8000 PID 13297; ai-station port 8000 PID 2118905; all unrelated ROS and tmux processes.
confirmed_conclusions:
  - Seven safety unit tests pass on each host; the Linux test scratch is on /data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42/scratch.
  - Both existing services are Validation ready and IDLE; Teleop is unavailable in those existing services.
disproven_routes:
  - Comparing macOS process argv[0] to the venv symlink rejects Python.app despite the correct entry and PID.
  - Passing bridge configuration without a child token makes an unnecessary ROS child fail at startup.
open_risks:
  - Full Teleop control is not configured by these existing acceptance services.
next_command: Run EXP-002 with the frozen final script revision on 127.0.0.1:8014 on each host.
```

```yaml
experiment_id: EXP-002
status: INVALID
prior_experiment: EXP-001
hypothesis: The frozen final manager starts the installed Validation service and cleans up only its own idle process on both platforms.
prediction: Both isolated port 8014 services report Validation ready with no ROS child token error, then their recorded PIDs exit; both pre-existing Tailscale port 8000 services stay healthy.
frozen_manager_sha256: 05deb5df5a52c67c2b19c1c2266f61ef247251e41600699dc832e2dd91455d01 (matched on both hosts before start)
single_variable: Frozen final script revision after correcting Mac process identity and matching the installed validation-only service environment.
lifecycle: ISOLATED_STACK
preconditions:
  - Both port 8014 listeners are absent and both port 8000 services are Validation ready and IDLE.
success_criteria:
  - Both start and cleanup commands return 0; exact test PIDs exit; no port 8014 listener remains; port 8000 PIDs and Validation readiness remain.
failure_criteria:
  - Any startup, health, ownership, campaign status, cleanup, or preservation check fails.
invalid_criteria:
  - A code change or unrelated service takes port 8014 during the experiment.
provenance:
  source_commit: 779b4e67923478d8c95f622db31b5199abbde72f plus task-owned scripts (Mac); 3a750cfac91f2bcb88e5b6d8882d24ac8fa3f1ec plus copied task-owned scripts (ai-station)
  install_overlay: /opt/data/so101/workspace/install (Mac); /home/matianyi/Projects/ros-moveit-demo/install (ai-station)
  runtime_executable: /opt/ros/jazzy/.venv/bin/python (Mac); /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python (ai-station)
  ros_domain_id: 225 (Mac); 226 (ai-station)
  gz_partition: so101-teleop-tailscale-mac-225 (Mac); so101-teleop-tailscale-ai-226 (ai-station)
commands:
  - command: Start, query health, query campaigns, and clean up each host's port 8014 manager with the pre-existing smoke state and durable roots.
    exit_code: Mac start 0, health 0, campaigns 0, cleanup 0; Linux start 0, health 0, campaigns 0, cleanup 2; Linux follow-up state cleanup 0.
observed:
  - Both installed services reported Validation ready and IDLE; both campaign lists were empty and no ROS child token error appeared.
  - Mac PID 22960 stopped through cleanup. Linux PID 2201787 received SIGTERM, logged normal shutdown, and left no port 8014 listener, but cleanup returned OWNER_COMMAND_CHANGED while the process command line disappeared during exit. Readback showed the process gone; follow-up cleanup marked the state ALREADY_EXITED.
inferred:
  - The final polling loop raced process exit and mistook an empty /proc cmdline for a live foreign command.
conclusion: The Linux cleanup command did not meet the success contract even though its owned process exited; the result is retained as an invalid manager run.
evidence:
  - /opt/data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42/smoke-mac
  - /data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42/smoke-linux
decision: REPEAT
next_experiment: EXP-003
```

```yaml
checkpoint_id: CP-003
last_valid_experiment: NONE
current_hypothesis: Treating a disappearing command line as an exit transition lets cleanup return success without accepting a changed live process.
working_tree_status: Rebased codex/so101-unified-webapp with task-owned new scripts, test, and ledger; ai-station main retains its pre-existing Web UI changes.
owned_processes: No port 8014 test service remains.
preserved_processes: Mac port 8000 PID 13297; ai-station port 8000 PID 2118905; all unrelated ROS and tmux processes.
confirmed_conclusions:
  - The final manager SHA256 8e241066526939eb66f4f87064f20cfa132e484cc01207338d42bb002033d685 matches on both hosts.
  - Eight manager safety unit tests pass on each host; ai-station scratch used /data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42/scratch/manager-unit-005/tmp.
  - origin/main is fd7348aa; rebase completed with no conflicts, placing the two prior branch commits on top of it.
disproven_routes:
  - A post-SIGTERM /proc cmdline read is stable throughout process exit.
open_risks:
  - Full Teleop control remains unavailable in the production acceptance services; this manager validates the Expert Validation domain.
next_command: Run EXP-003 post-rebase frozen manager smoke on port 8014, then commit the task-owned scripts and ledger.
```

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: The Linux exit-race fix lets each host's cleanup report success while preserving all other services.
prediction: Both managers start on port 8014, report Validation ready, and cleanup exits 0; both test PIDs leave, port 8014 closes, and old port 8000 PIDs stay healthy.
single_variable: Manager SHA256 8e241066526939eb66f4f87064f20cfa132e484cc01207338d42bb002033d685 after exit-race handling and rebase onto fd7348aa.
lifecycle: ISOLATED_STACK
preconditions:
  - Both port 8014 listeners are absent; both port 8000 services are Validation ready and IDLE; manager SHA256 matches across hosts.
success_criteria:
  - Start, health, campaign query, and cleanup all exit 0 on each host; recorded PIDs exit; no port 8014 listener remains; existing port 8000 PIDs and Validation readiness remain.
failure_criteria:
  - Any command exits nonzero, owned process survives, or preserved service changes identity or readiness.
invalid_criteria:
  - The frozen manager changes or another process takes port 8014 during the run.
provenance:
  source_commit: 47006619cfebcc9e13e843c0d3ee25fa4209149c plus task-owned scripts (Mac); 3a750cfac91f2bcb88e5b6d8882d24ac8fa3f1ec plus copied task-owned scripts (ai-station)
  install_overlay: /opt/data/so101/workspace/install (Mac); /home/matianyi/Projects/ros-moveit-demo/install (ai-station)
  runtime_executable: /opt/ros/jazzy/.venv/bin/python (Mac); /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python (ai-station)
  ros_domain_id: 225 (Mac); 226 (ai-station)
  gz_partition: so101-teleop-tailscale-mac-225 (Mac); so101-teleop-tailscale-ai-226 (ai-station)
commands:
  - command: Start, query health/campaigns, cleanup, and verify port 8000 preservation on each host with the frozen post-rebase manager.
    exit_code: 0 for Mac and Linux start, health, campaign query, cleanup, and preservation checks.
observed:
  - Mac PID 23308 and Linux PID 2204134 each started on 127.0.0.1:8014, reported domains.validation=ready and global_state=IDLE, and returned an empty campaign list.
  - Both cleanup commands returned STOPPED with exit code 0. Neither host retained a port 8014 listener; both test logs show orderly application shutdown and no ROS child token error.
  - Mac original PID 13297 and ai-station original PID 2118905 stayed on their Tailscale port 8000 endpoints with Validation ready.
inferred:
  - The exit-race handling fixed the observed false OWNER_COMMAND_CHANGED result on the Linux cleanup path in this run.
conclusion: The one-command start and cleanup lifecycle passed on both installed hosts for the Expert Validation domain.
evidence:
  - /opt/data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42/smoke-mac/service-20260923T152055Z.log
  - /data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42/smoke-linux/service-20260923T152054Z.log
decision: KEEP
next_experiment: NONE
```

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-003
current_hypothesis: NONE
working_tree_status: Task-owned new scripts, test, and ledger pending commit; ai-station main retains its pre-existing Web UI changes untouched.
owned_processes: NONE; the isolated port 8014 PIDs 23308 and 2204134 exited.
preserved_processes: Mac port 8000 PID 13297; ai-station port 8000 PID 2118905; unrelated ROS and tmux processes.
confirmed_conclusions:
  - EXP-003 passed the frozen cross-host installed service lifecycle after rebase onto origin/main fd7348aa.
  - Eight manager safety unit tests passed on each host; Linux used verified NVMe scratch manager-unit-005/tmp for the final unit run.
disproven_routes:
  - EXP-001 Mac venv path equality for process argv[0].
  - EXP-002 assumption that /proc cmdline remains populated until process exit.
open_risks:
  - Existing port 8000 services and the new managed Validation service report Teleop unavailable; no Teleop control backend was configured or tested.
  - Linux scratch directories manager-unit-001 through manager-unit-005 and both hosts' /tmp task roots are deletion candidates after readback; no evidence was deleted.
retained_runs:
  - /opt/data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42/smoke-mac
  - /data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42/smoke-linux
archived_runs: NONE
next_command: Commit the task-owned scripts, test, and ledger; then push the rebased feature branch with a lease check.
```

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-003
current_hypothesis: NONE
working_tree_status: Branch codex/so101-unified-webapp at 413ddf4d; README and so101-dev reference updated for service operations.
owned_processes: NONE
preserved_processes: Mac port 8000 PID 13297; ai-station port 8000 PID 2118905.
confirmed_conclusions:
  - README documents platform launch, doctor, status, cleanup, health validation, and port ownership.
  - so101-dev links to a dedicated reference with installed paths, overrides, evidence roots, and service cleanup rules.
  - Skill validation and local documentation link checks pass; no service or test process was started for this documentation update.
open_risks:
  - Port 8000 remains owned by earlier services on both hosts; new manager requires a verified handoff before it can use that port.
retained_runs:
  - /opt/data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42/smoke-mac
  - /data/work/so101-evidence/teleop-service-scripts/20260923-9c6a7e42/smoke-linux
archived_runs: NONE
deletion_candidates:
  - Linux scratch directories manager-unit-001 through manager-unit-005 after readback.
  - Both hosts' /tmp/so101-debug-teleop-service-scripts-20260923-9c6a7e42 roots after readback.
next_command: Commit and push the documentation update on codex/so101-unified-webapp.
```
