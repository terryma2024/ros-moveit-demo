# SO-101 8000 service restart, 2026-09-23

```yaml
task_id: so101-teleop-service-restart-20260923-70919020
goal: Rebase the unified Web branch on origin/main, then replace the old port 8000 Expert Validation services on Mac and ai-station with the managed service.
success_contract: Both Tailscale port 8000 endpoints run the manager-owned installed Web service, report domains.validation=ready, and retain their prior evidence; no active campaign is interrupted.
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
linux_worktree: /home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: fd7348aa27361750f7e2e7954df53ef75e96545c
current_commit: bedf45c746733996382d9ca68c8faf0189ee1944
evidence_root_mac: /opt/data/work/so101-evidence/teleop-service-restart/20260923-70919020
evidence_root_linux: /data/work/so101-evidence/teleop-service-restart/20260923-70919020
low_rate_root_mac: /tmp/so101-debug-teleop-service-restart-20260923-70919020
low_rate_root_linux: /tmp/so101-debug-teleop-service-restart-20260923-70919020
confirmed_conclusions:
  - At the initial rebase, origin/main was fd7348aa; git rebase origin/main returned up to date and the branch was 70919020 with four commits ahead of main.
  - Mac old PID 13297 belongs to tmux so101-teleop-tailscale-mac; its sole campaign is INFRA_FAILED with batch_cleanup_complete=true.
  - ai-station old PID 2118905 belongs to tmux so101-teleop-tailscale-ai; its campaign list is empty.
  - Both old services report domains.validation=ready and global_state=IDLE before restart.
  - EXP-001 and EXP-003: Mac and ai-station now have manager-owned port 8000 services with Validation ready, IDLE, zero campaigns, and Web index/assets HTTP 200.
disproven_routes:
  - Rebase requires rewriting commits after the latest origin/main fetch.
open_hypotheses: []
latest_checkpoint: CP-004
next_experiment: NONE
```

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The new manager can replace each old idle service using the same installed overlay and Tailscale endpoint.
working_tree_status: Mac feature worktree has this task-owned untracked ledger; Linux feature worktree is clean; ai-station main retains unrelated untracked pytest plan.
owned_processes: NONE
preserved_processes: Mac old PID 13297 and ai-station old PID 2118905 until preflight and final campaign readback.
confirmed_conclusions:
  - Rebase was a no-op against origin/main fd7348aa.
  - Old service campaign states are terminal and cleaned (Mac) or absent (Linux).
disproven_routes:
  - No rebase conflict or branch divergence from origin/main.
open_risks:
  - Existing installed overlays may not satisfy manager preflight or application --check.
next_command: Run doctor on both hosts with the verified Linux install-prefix override, then plan the port ownership handoff.
```

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: The Mac installed service can be restarted under the manager on the same Tailscale endpoint.
prediction: Doctor and application check pass, old owned PID exits, manager start returns STARTED, and port 8000 returns Validation ready with an empty campaign list.
single_variable: Replace the old Mac tmux launcher with the branch manager while retaining install overlay, Python, config, models, ROS domain, and Gazebo partition.
lifecycle: FULL_RESTART
preconditions:
  - Old Mac campaign is terminal with batch_cleanup_complete=true; PID 13297 still owns 100.74.192.81:8000.
success_criteria:
  - New manager-owned PID serves 100.74.192.81:8000 with domains.validation=ready, global_state=IDLE, and empty campaign list.
failure_criteria:
  - Manager doctor/start fails, health is not ready, or old PID survives.
invalid_criteria:
  - A new campaign starts before the old service stop or port ownership changes unexpectedly.
provenance:
  source_commit: 7091902086891d2fd276879e198ff93355f6d3d0
  install_overlay: /opt/data/so101/workspace/install
  runtime_executable: /opt/ros/jazzy/.venv/bin/python
  ros_domain_id: 225
  gz_partition: so101-teleop-tailscale-mac-225
commands:
  - command: scripts/so101-teleop-macos.zsh doctor
    exit_code: 0
  - command: Stop verified old tmux-owned PID 13297 with campaign guard.
    exit_code: 1 after SIGTERM; guard falsely reported port not released while old connections were in TIME_WAIT.
  - command: scripts/so101-teleop-macos.zsh start --evidence-root /opt/data/work/so101-evidence/teleop-service-restart/20260923-70919020
    exit_code: 0
  - command: scripts/so101-teleop-macos.zsh status and fresh health/campaign/listener checks
    exit_code: 0
observed:
  - Old PID 13297 exited; its tmux session ended. lsof showed no listener, while netstat showed only TIME_WAIT sockets; a later bind to 100.74.192.81:8000 succeeded.
  - New manager-owned PID 25883 serves 100.74.192.81:8000 with Validation ready, IDLE, and zero campaigns; old PID is absent.
inferred:
  - The stop guard's bind probe raced macOS TIME_WAIT and did not indicate an active listener or failed service stop.
conclusion: Mac port 8000 restart succeeded under the manager; Teleop control remains unavailable as before.
evidence:
  - /tmp/so101-debug-teleop-service-restart-20260923-70919020/start-mac.json
  - /opt/data/work/so101-evidence/teleop-service-restart/20260923-70919020/service-20260923T155740Z.log
decision: KEEP
next_experiment: EXP-002
```

```yaml
experiment_id: EXP-002
status: INVALID
prior_experiment: EXP-001
hypothesis: The ai-station installed service can be restarted under the manager on the same Tailscale endpoint.
prediction: Doctor and application check pass, old owned PID exits, manager start returns STARTED, and port 8000 returns Validation ready with an empty campaign list.
single_variable: Replace the old ai-station tmux launcher with the branch manager while retaining install overlay, Python, config, models, ROS domain, and Gazebo partition.
lifecycle: FULL_RESTART
preconditions:
  - Old ai-station campaign list is empty; PID 2118905 still owns 100.104.202.119:8000.
success_criteria:
  - New manager-owned PID serves 100.104.202.119:8000 with domains.validation=ready, global_state=IDLE, and empty campaign list.
failure_criteria:
  - Manager doctor/start fails, health is not ready, or old PID survives.
invalid_criteria:
  - A new campaign starts before the old service stop or port ownership changes unexpectedly.
provenance:
  source_commit: 7091902086891d2fd276879e198ff93355f6d3d0
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_id: 226
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: scripts/so101-teleop-linux.sh doctor --install-prefix /home/matianyi/Projects/ros-moveit-demo/install
    exit_code: 0
  - command: Stop verified old tmux-owned PID 2118905 with campaign guard.
    exit_code: 1 after SIGTERM; guard falsely reported port not released while old connections were in TIME_WAIT.
  - command: scripts/so101-teleop-linux.sh start --install-prefix /home/matianyi/Projects/ros-moveit-demo/install --evidence-root /data/work/so101-evidence/teleop-service-restart/20260923-70919020
    exit_code: 0
  - command: Fresh health, campaign, and Web root checks on 100.104.202.119:8000.
    exit_code: 1 for Web root HTTP 503; health and campaign checks returned 0.
observed:
  - Old PID 2118905 exited as an inactive zombie; no old listener remains.
  - New manager-owned PID 2224105 reported Validation ready, IDLE, zero campaigns, but GET / returned HTTP 503 WEB_ASSETS_NOT_BUILT.
  - Installed Web index and both referenced assets exist; the installed index is a symlink into the source dist tree.
inferred:
  - With a symlink install, unified.main installed_web_assets resolves its module path into source and does not discover the installed share directory; the manager omitted --static-dir, unlike the old launcher.
conclusion: The Linux manager start returned success without a usable Web page; this run does not meet the service acceptance contract.
evidence:
  - /tmp/so101-debug-teleop-service-restart-20260923-70919020/start-linux.json
  - /data/work/so101-evidence/teleop-service-restart/20260923-70919020/service-20260923T155954Z.log
decision: REPEAT
next_experiment: EXP-003
```

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-001
current_hypothesis: The Linux manager can replace its old idle service using the verified root worktree install overlay.
working_tree_status: Mac feature worktree has task-owned ledger; Linux feature worktree clean; ai-station main's unrelated untracked plan preserved.
owned_processes: Mac manager PID 25883 on 100.74.192.81:8000.
preserved_processes: ai-station old PID 2118905 on 100.104.202.119:8000 until final campaign readback.
confirmed_conclusions:
  - EXP-001 Mac restart passed; status and health report Validation ready, IDLE, zero campaigns.
disproven_routes:
  - A macOS bind failure immediately after old PID exit always means a listener still owns the port; TIME_WAIT caused the observed false alarm.
open_risks:
  - Linux manager application check and port release still unverified.
next_command: Copy the verified stop guard to ai-station, then stop only old PID 2118905 if its tmux and campaign checks still pass.
```

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-001
current_hypothesis: Passing the installed Web directory explicitly and requiring GET / HTTP 200 before STARTED will repair Linux service readiness.
working_tree_status: Mac feature worktree has task-owned manager, unit-test, and ledger changes; Linux feature worktree clean; ai-station main unrelated untracked plan preserved.
owned_processes: Mac manager PID 25883 and Linux manager PID 2224105; Linux PID 2224105 has an unusable Web root and must be restarted.
preserved_processes: All unrelated ROS, tmux, and remote main worktree state.
confirmed_conclusions:
  - EXP-001 Mac port 8000 serves Web 200 and Validation ready.
  - EXP-002 Linux port 8000 health is ready but Web root returns WEB_ASSETS_NOT_BUILT; installed Web assets themselves are present.
  - Two new regression tests failed before the manager fix and all 10 manager tests pass after it on Mac.
disproven_routes:
  - Validation ready alone proves the Web page is usable.
  - The Linux installed Web bundle is missing.
open_risks:
  - Linux manager restart with explicit --static-dir remains to be verified.
next_command: Commit and publish the manager fix, fast-forward the Linux feature worktree, then plan EXP-003 before restarting Linux.
```

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: Explicit --static-dir and a Web 200 readiness gate make the Linux installed service usable.
prediction: Manager cleanup stops only PID 2224105, the corrected manager starts a new PID on 100.104.202.119:8000, and both /health Validation and / return ready/200 from both hosts.
single_variable: Manager revision bedf45c7 adds the installed static directory argument and Web page readiness check.
lifecycle: FULL_RESTART
preconditions:
  - Linux manager PID 2224105 owns 100.104.202.119:8000; campaigns are empty; installed index and referenced assets exist.
success_criteria:
  - New manager reports RUNNING, health Validation ready/IDLE, zero campaigns, GET / returns 200, referenced JavaScript and CSS return 200, and no old port 8000 listener survives.
failure_criteria:
  - Cleanup/start exits nonzero after port release, or any service/Web check fails.
invalid_criteria:
  - A campaign becomes active before cleanup or another process claims the port.
provenance:
  source_commit: bedf45c746733996382d9ca68c8faf0189ee1944
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python
  ros_domain_id: 226
  gz_partition: so101-teleop-tailscale-ai-226
commands:
  - command: scripts/so101-teleop-linux.sh cleanup
    exit_code: 0
  - command: scripts/so101-teleop-linux.sh start --install-prefix /home/matianyi/Projects/ros-moveit-demo/install --evidence-root /data/work/so101-evidence/teleop-service-restart/20260923-70919020
    exit_code: 0
  - command: Fresh health, campaign, Web index and referenced asset checks from Mac and ai-station.
    exit_code: 0
observed:
  - Manager cleanup stopped PID 2224105 after confirming an empty campaign list. TIME_WAIT briefly prevented a bind without SO_REUSEADDR; the port later became bindable with no listener.
  - Corrected manager started PID 2227775 with explicit --static-dir /home/matianyi/Projects/ros-moveit-demo/install/so101_teleop/share/so101_teleop/web.
  - Mac readback of both Tailscale endpoints showed Validation ready, IDLE, zero campaigns, Web index HTTP 200, and both referenced JS/CSS assets HTTP 200.
  - Source and installed unified Web entry scripts have matching SHA256 c7bff667876a4d00bba5219bd184ecb6b53a46822fc64f051618b7a2498a4816 on each host.
  - Ten manager safety tests passed on Mac and ai-station with the corrected branch manager.
inferred:
  - Explicit installed Web path removes the symlink install discovery failure; the Web readiness gate prevents the prior false STARTED result.
conclusion: Both port 8000 Expert Validation Web services now meet the requested remote access boundary.
evidence:
  - /tmp/so101-debug-teleop-service-restart-20260923-70919020/cleanup-linux.json
  - /tmp/so101-debug-teleop-service-restart-20260923-70919020/start-linux-fixed.json
  - /data/work/so101-evidence/teleop-service-restart/20260923-70919020/service-20260923T160528Z.log
decision: KEEP
next_experiment: NONE
```

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-003
current_hypothesis: NONE
working_tree_status: Mac feature worktree has only this task-owned ledger update pending commit; Linux feature worktree clean at bedf45c7; ai-station main unrelated untracked plan preserved.
owned_processes: Mac manager PID 25883 on 100.74.192.81:8000; ai-station manager PID 2227775 on 100.104.202.119:8000.
preserved_processes: ai-station tmux server PID 2118904 also owns the codex session; old service PID 2118905 remains defunct under it, with no listener or active campaign. All unrelated ROS/tmux processes preserved.
confirmed_conclusions:
  - EXP-001 Mac service replacement passed.
  - EXP-002 showed that Validation health alone missed the Linux Web 503 failure.
  - EXP-003 Linux service replacement passed with installed Web assets and index HTTP 200 from Mac.
disproven_routes:
  - Automatic Web asset discovery works for the Linux symlink install.
  - Validation ready alone proves the page is usable.
open_risks:
  - Teleop control remains unavailable by configuration on both services; Expert Validation is ready.
  - Prior Mac browser polling an old campaign ID now receives 404 until that browser tab is refreshed.
  - Port 8000 may remain temporarily unbindable after shutdown while old connections are in TIME_WAIT.
retained_runs:
  - /opt/data/work/so101-evidence/teleop-service-restart/20260923-70919020
  - /data/work/so101-evidence/teleop-service-restart/20260923-70919020
archived_runs: NONE
deletion_candidates:
  - Both hosts' /tmp/so101-debug-teleop-service-restart-20260923-70919020 after readback; no evidence deleted.
next_command: Commit and push the final ledger update, then verify both manager statuses and remote branch heads.
```
