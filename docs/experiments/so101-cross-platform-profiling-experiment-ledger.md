# SO-101 cross-platform profiling experiment ledger

```yaml
task_id: so101-cross-platform-profiling
goal: Provide one switchable semantic profiling contract on macOS and Linux, with official ros2_tracing CTF on Linux.
success_contract: Profiling off preserves business results and bounded overhead; enabled modes produce correlated complete portable artifacts; Linux required trace produces readable ROS UST CTF and cleans up its owned session.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/so101-cross-platform-profiling
branch: codex/so101-cross-platform-profiling
base_commit: e7e0299cf8115214a0daf483cc40da6b09309091
current_commit: 1a00ce20167ef3fcac53fc45c74ca6c7a0fba4ba (verified implementation; this checkpoint is a subsequent ledger-only update)
evidence_root: /tmp/so101-debug-cross-platform-profiling-design-20260831
remote_platform_evidence: /data/work/so101-evidence/so101-cross-platform-profiling/20260831T052807Z-7583857
confirmed_conclusions:
  - EXP-001 macOS package gate passed 842 tests and portable artifacts parsed.
  - EXP-002 Linux candidate passed 842 tests and official Trace produced readable ROS UST CTF.
disproven_routes:
  - EXP-002A ExecuteProcess talker did not satisfy clean-shutdown acceptance.
  - EXP-002B A missing smoke-fixture environment variable invalidated the first final trace attempt.
open_hypotheses:
  - Production SO-101 launch integration is still covered by composition tests rather than a non-physical run of the full MuJoCo launch.
latest_checkpoint: CP-004
next_experiment: NONE
```

## Imported experiment checkpoints

```yaml
experiment_id: EXP-001
status: VALID
hypothesis: The portable semantic backend works on macOS without importing tracetools_launch and without changing the disabled hot path beyond its allowance.
single_variable: profiling implementation enabled in the isolated candidate
lifecycle: ISOLATED_STACK
provenance:
  source_commit: d88774bb9ecb7e004d2e66bdabd26593b7b4f3b8
  install_overlay: /tmp/so101-debug-cross-platform-profiling-design-20260831/install-macos
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: UNSET_TEST_ONLY
  gz_partition: UNSET_TEST_ONLY
observed:
  - Package gate passed 842 tests; summary and Chrome Trace JSON parsed; normal macOS import loaded no tracetools_launch module.
  - Disabled Text Agent and state-action paired benchmarks stayed within the 2 percent or 100 ns allowance.
conclusion: Portable macOS backend met the original automated and non-physical smoke contract.
evidence:
  - /tmp/so101-debug-cross-platform-profiling-design-20260831/task-ledger.md
decision: KEEP
next_experiment: EXP-002
```

```yaml
experiment_id: EXP-002
status: VALID
hypothesis: The Linux adapter can start the official Jazzy Trace action, retain the semantic artifacts, produce readable CTF, and cleanly stop owned processes.
single_variable: Linux official ros2_tracing backend
lifecycle: ISOLATED_STACK
provenance:
  source_commit: d88774bb9ecb7e004d2e66bdabd26593b7b4f3b8
  install_overlay: /data/work/so101-evidence/so101-cross-platform-profiling/20260831T052807Z-7583857/install
  runtime_executable: /data/work/so101-evidence/so101-cross-platform-profiling/20260831T052807Z-7583857/install/so101_demo_py
  ros_domain_id: 191
  gz_partition: so101-prof-7583857-052807
observed:
  - Final accepted session linux-final2-d88774b produced complete semantic artifacts and 162 Babeltrace-readable ROS UST events.
  - Text Agent preview and talker exited cleanly; lttng list reported no recording session and no owned process remained.
  - The earlier ExecuteProcess and missing-environment attempts were retained but not counted.
conclusion: The bounded Linux harness met the original Trace/CTF contract; production-launch integration remains a review risk rather than claimed physical acceptance.
evidence:
  - /data/work/so101-evidence/so101-cross-platform-profiling/20260831T052807Z-7583857/task-ledger.md
  - /data/work/so101-evidence/so101-cross-platform-profiling/20260831T052807Z-7583857/final-trace-2
decision: KEEP
next_experiment: EXP-003
```

## Current review remediation

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002
hypothesis: Independent subagent review can reproduce gaps in business fail-open behavior, semantic artifact integrity, and Linux execute-time backend truthfulness.
prediction: Focused RED tests fail on the reviewed boundaries and pass only after minimal fixes, without starting a robot or simulator stack.
single_variable: review-driven profiling correctness fixes
lifecycle: ISOLATED_STACK
preconditions:
  - Local and ai-station candidate commits both equal d88774bb9ecb7e004d2e66bdabd26593b7b4f3b8 before remediation.
  - Local worktree and remote candidate were clean; submodule commit was 71bc9346cf93d6227a6678fcacf63f3e18acfcba.
  - Remote ROS_DOMAIN_ID 191 had no nodes; codex and codex-cua tmux sessions were preserved; no owned profiling smoke process remained.
success_criteria:
  - Every accepted review defect has a witnessed RED test and focused GREEN result.
  - Full macOS package gate passes after integrating independent patches.
  - No ROS, simulator, physical execution, merge, or push occurs in this experiment.
failure_criteria:
  - A fix changes an existing business status, breaks lazy macOS imports, or cannot be verified without expanding runtime authority.
invalid_criteria:
  - Agents edit overlapping files without review, write the ledger concurrently, or start external stacks.
provenance:
  source_commit: d88774bb9ecb7e004d2e66bdabd26593b7b4f3b8
  install_overlay: /tmp/so101-debug-cross-platform-profiling-design-20260831/install-macos
  runtime_executable: /Users/matianyi/ros2_jazzy/.venv/bin/python3
  ros_domain_id: 191
  gz_partition: so101-prof-7583857-052807
commands:
  - command: Three scoped subagent reviews followed by non-overlapping TDD remediation tasks.
    exit_code: 0
  - command: Direct macOS package pytest after integration.
    exit_code: 0
  - command: ai-station candidate build, direct package pytest, disabled benchmark, and bounded official Trace smoke.
    exit_code: 0
observed:
  - Reviews returned no Critical findings and identified reproducible Important fail-open, artifact integrity, dispatch labeling, and Trace lifecycle risks.
  - Focused RED tests reproduced the accepted defects before implementation; the merged focused suite passed 187 tests.
  - The final macOS package gate passed 874 tests, and the corrected disabled benchmark stayed within its 2 percent or 100 ns allowance.
  - ai-station rebuilt commit 1a00ce2 and passed 874 tests; its corrected disabled benchmark passed.
  - Session linux-final3-1a00ce2 produced complete portable artifacts plus 162 Babeltrace-readable ROS UST events; both child processes exited cleanly and no recording session or owned process remained.
inferred:
  - The original 842-test gates were insufficient for the reviewed boundary cases; the added tests now cover them without expanding robot execution authority.
conclusion: Review remediation is accepted for the semantic core, child-process fail-open behavior, and official Linux Trace lifecycle wrapper.
evidence:
  - /tmp/so101-debug-cross-platform-profiling-design-20260831/task-ledger.md
  - /tmp/so101-debug-cross-platform-profiling-design-20260831/post-review-full.xml
  - /data/work/so101-evidence/so101-cross-platform-profiling/20260831T052807Z-7583857/review-remediation/linux-full-1a00ce2.xml
  - /data/work/so101-evidence/so101-cross-platform-profiling/20260831T052807Z-7583857/review-remediation/final-trace-3
decision: KEEP
next_experiment: NONE
```

## Checkpoint

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-003
current_hypothesis: NONE
working_tree_status: tracked ledger update pending after clean commit 1a00ce2
owned_processes: NONE
preserved_processes: ai-station tmux codex and codex-cua; pre-existing system lttng-sessiond
confirmed_conclusions:
  - Review remediation passed macOS and Linux package gates plus the bounded official Trace smoke at 1a00ce2.
disproven_routes:
  - Failed/preflight Linux harness runs do not count as acceptance.
open_risks:
  - The bounded Linux harness does not execute the full SO-101 MuJoCo production launch; composition and action-ordering remain automated-test evidence.
next_command: NONE
```
