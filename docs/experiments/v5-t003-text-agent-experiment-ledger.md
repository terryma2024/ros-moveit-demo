# V5-T003 Text Agent Experiment Ledger

```yaml
task_id: so101-v5-t003-text-agent
goal: Implement the approved V5-T003 single-turn text instruction agent with deterministic validation, fail-closed dispatch, and the existing MuJoCo dynamic cup pick-place runtime boundary.
success_contract: Pure-Python RED-GREEN tests prove every static gate and exactly-once dispatch; package tests pass; ai-station preview and authorized MuJoCo dispatch are traced by one request_id without claiming V5-T005 physical completion.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-text-agent
branch: codex/v5-t003-text-agent
base_commit: e58eee1a2ad94c859a6784bb968ca9702ec4031a
current_commit: LIVE_GIT_REV_PARSE_HEAD
documentation_snapshot_parent: 44a4471cd1df4d6d15e8f69cf1eeea66f295ba2d
live_commit_rule: Every EXP-002/Task 8 action must run and record `git rev-parse HEAD` immediately before its provenance-sensitive command.
evidence_root: /tmp/so101-debug-v5-t003-text-agent-20260829-164105
confirmed_conclusions:
  - Local moveit-demo is at e58eee1 while ai-station is at e6ab8c1; source/install/runtime parity must be established before live validation (CP-001).
  - V5-T003 acceptance ends at correct state-machine dispatch and does not claim V5-T005 physical pick-place completion (CP-001).
  - Local candidate validation at 25c30bec8aae4dd5fc0ca6b29945febe660f9d87 passed focused and package gates; the offline preview validated a fallback-marked PlannerCandidate without dispatch (EXP-001).
disproven_routes:
  - NONE
open_hypotheses:
  - The existing so101_demo_py package can expose the TextAgent through focused Python modules without changing the dynamic pick-place runtime contract.
  - The existing dynamic runtime can be called through a typed Python adapter without shell command construction.
latest_checkpoint: CP-002
next_experiment: EXP-002
```

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: The installed V5-T003 candidate locally validates one injected PlannerCandidate, resolves only the MuJoCo cup-pick capability, and remains non-dispatching in preview.
prediction: The six-file suite and full package suite pass; an injected fallback candidate emits one secret-free DISPATCH_PREVIEW JSON document with dispatch=false.
single_variable: Candidate install rebuilt at the validation HEAD; no ROS/MuJoCo runtime dispatch was started.
lifecycle: ISOLATED_STACK
preconditions:
  - Original moveit-demo checkout and parent repository were inspected read-only before validation; no reset, stash, clean, edit, or remote action was performed there.
  - Candidate overlay was sourced through zsh/direnv; ROS_HOME and ROS_LOG_DIR were under this experiment's sole evidence root.
success_criteria:
  - Focused six-file and full so101_demo_py pytest JUnit have zero failures and errors.
  - Installed prefix is the candidate worktree and includes executable text_pick_agent.
  - Locally injected preview contains exactly one JSON document, validated command/capability and PlannerCandidate metadata, with dispatch=false and no secret.
failure_criteria:
  - A test failure, provenance mismatch, missing entry point, multiple/invalid preview documents, dispatch=true, or secret projection.
invalid_criteria:
  - A live provider call, ROS/MuJoCo runtime dispatch, or evidence outside the registered parent root.
provenance:
  source_commit: 25c30bec8aae4dd5fc0ca6b29945febe660f9d87
  install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-text-agent/install
  runtime_executable: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-text-agent/install/so101_demo_py/lib/so101_demo_py/text_pick_agent
  ros_domain_id: 197
  gz_partition: v5-t003-text-agent-task7-local-20260829-164105
commands:
  - command: 'zsh -lc ''cd /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-text-agent; export ROS_DOMAIN_ID=197 GZ_PARTITION=v5-t003-text-agent-task7-local-20260829-164105; eval "$(direnv export zsh)"; colcon build --packages-select so101_demo_py --symlink-install'''
    exit_code: 0
  - command: 'zsh -lc ''cd /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-text-agent; export ROS_DOMAIN_ID=197 GZ_PARTITION=v5-t003-text-agent-task7-local-20260829-164105 ROS_HOME=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/ros-home ROS_LOG_DIR=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/ros-home/log; eval "$(direnv export zsh)"; source install/setup.zsh; /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_task_command.py src/so101_demo_py/test/test_planner_chain.py src/so101_demo_py/test/test_planner_adapters.py src/so101_demo_py/test/test_text_agent.py src/so101_demo_py/test/test_pick_place_executor_adapter.py src/so101_demo_py/test/test_text_pick_agent_cli.py -q --junitxml=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/text-agent-focused.xml'''
    exit_code: 0
  - command: 'zsh -lc ''cd /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-text-agent; export ROS_DOMAIN_ID=197 GZ_PARTITION=v5-t003-text-agent-task7-local-20260829-164105; eval "$(direnv export zsh)"; source install/setup.zsh; git rev-parse HEAD; ros2 pkg prefix so101_demo_py; ros2 pkg executables so101_demo_py; stat -f "%N %Sp" "$(ros2 pkg prefix so101_demo_py)/lib/so101_demo_py/text_pick_agent"'''
    exit_code: 0
  - command: 'zsh -lc ''cd /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-text-agent; export ROS_DOMAIN_ID=197 GZ_PARTITION=v5-t003-text-agent-task7-local-20260829-164105 ROS_HOME=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/ros-home ROS_LOG_DIR=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/ros-home/log; eval "$(direnv export zsh)"; source install/setup.zsh; PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -c "import rclpy; print(rclpy.__file__)"; PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test -q --junitxml=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/so101_demo_py-pytest.xml; /Users/matianyi/ros2_jazzy/.venv/bin/colcon test-result --test-result-base /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7 --verbose'''
    exit_code: 0
  - command: 'zsh -lc ''cd /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-text-agent; eval "$(direnv export zsh)"; source install/setup.zsh; /Users/matianyi/ros2_jazzy/.venv/bin/python3 /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7-review-fix/offline_preview.py > /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7-review-fix/offline-preview.stdout.json 2> /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7-review-fix/offline-preview.stderr.log'''
    exit_code: 0
observed:
  - Focused JUnit: 139 tests, 0 failures, 0 errors, 0 skipped.
  - Full package JUnit: 692 tests, 0 failures, 0 errors, 0 skipped; colcon test-result over the retained task evidence root reported 831 tests, 0 errors, 0 failures, 0 skipped.
  - rclpy resolved to /Users/matianyi/ros2_jazzy/install/rclpy/lib/python3.11/site-packages/rclpy/__init__.py.
  - ros2 pkg prefix resolved to the candidate worktree install/so101_demo_py; ros2 pkg executables listed so101_demo_py text_pick_agent, whose installed file is executable.
  - task7-review-fix/offline-preview.stdout.json is one DISPATCH_PREVIEW document with dispatch=false, command plastic_cup/pick/{}, capability dynamic_cup_pick_place, and PlannerCandidate metadata provider=ollama, model=qwen3.5:4b, input_tokens=7, output_tokens=11, cache_hit_tokens=0, fallback_used=true; the contract check found no DEEPSEEK_API_KEY, stderr was empty, and the script guarded network/socket, rclpy, and runtime imports.
  - No live provider, runtime dispatch, robot process, or physical verification was started by EXP-001.
inferred:
  - Local evidence supports semantic validation, fail-closed preview, package installation, and the agent-to-dispatch boundary only.
conclusion: Local V5-T003 gates are valid at the observed source/install provenance. This is not ai-station qualification, does not prove state-machine dispatch in a live stack, and does not claim V5-T005 physical pick-place success.
evidence:
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/preflight-provenance-and-preservation.log
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/candidate-colcon-build.log
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/focused-six-file-suite.log
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/text-agent-focused.xml
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/installed-provenance.log
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/full-package-suite.log
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/so101_demo_py-pytest.xml
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/local-preview.json
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7/local-preview-contract.log
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7-review-fix/offline_preview.py
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7-review-fix/invocation.log
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7-review-fix/offline-preview.stdout.json
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7-review-fix/offline-preview.stderr.log
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task7-review-fix/contract-verification.log
decision: KEEP
next_experiment: EXP-002
```

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-001
documentation_snapshot_parent: 44a4471cd1df4d6d15e8f69cf1eeea66f295ba2d
current_hypothesis: A separately authorized ai-station run can establish source/install/runtime parity and preview/one-dispatch correlation without promoting it to V5-T005 physical proof.
working_tree_status: "Candidate worktree was clean before this Task 7 documentation change. Preserved original moveit-demo untracked paths: docs/experiments/v5-t003-text-agent-experiment-ledger.md, docs/superpowers/plans/2026-08-29-v5-t003-text-agent.md, src/so101_demo_py/docs/planner-schema.md. Preserved parent paths: learners/zjumty/progress.yaml, moveit-demo, docs/model-runtime-choice.md, learners/zjumty/sessions/2026-08-28-002-v5-t001-llm-planner-schema.md, learners/zjumty/sessions/2026-08-28-003-v5-t002-model-runtime-choice.md."
owned_processes: NONE
preserved_processes: No local runtime was started. CP-001's ai-station tmux sessions codex and codex-cua remain out of scope and untouched.
confirmed_conclusions:
  - EXP-001 local semantic, dispatch-preview, installed-entry-point, focused, and package gates passed at 25c30bec8aae4dd5fc0ca6b29945febe660f9d87.
  - V5-T003 evidence ends at semantic/dispatch/package boundaries; physical outcome remains a V5-T005 responsibility.
disproven_routes:
  - Treating a local DISPATCH_PREVIEW, RUNTIME_STARTED, or RUNTIME_COMPLETED value as state-machine or physical proof without correlated runtime evidence.
open_risks:
  - ai-station checkout/install parity, provider availability, live state-machine correlation, and downstream physical evidence have not been tested.
evidence_disposition:
  retained: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/ (Task 7 artifacts remain in task7/ and task7-review-fix/ beneath this sole registered root; the initial failed ad-hoc preview and review-fix initial script failure are preserved)
  archived: NONE
  deletion_candidates: NONE
next_command: On ai-station only after explicit authorization and preflight preservation, run `git rev-parse HEAD`, record that live value, source the candidate overlay, and run EXP-002 preview before any authorized dispatch.
```

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The approved design can be implemented inside so101_demo_py while preserving the existing dynamic runtime boundary.
working_tree_status: "Isolated codex/v5-t003-text-agent worktree contains task-owned plan and ledger; the original checkout's pre-existing untracked src/so101_demo_py/docs/planner-schema.md remains outside this worktree. Parent repository and ai-station have separate preserved changes recorded below."
owned_processes: NONE
preserved_processes: ai-station tmux sessions codex and codex-cua; no running gz sim, move_group, rviz2, pick_place_state_machine, or dynamic_cup_pick_place was observed at CP-001.
confirmed_conclusions:
  - Local moveit-demo HEAD is e58eee1a2ad94c859a6784bb968ca9702ec4031a on main; ai-station checkout is e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4 on main.
  - Parent repository has pre-existing learner progress and model-runtime-choice work; ai-station has a pre-existing RGB-D experiment ledger. None is owned by this task.
disproven_routes:
  - NONE
open_risks:
  - User execution-method choice is pending; live DeepSeek credential and ai-station Ollama availability will be observed rather than assumed.
next_command: Await the user's choice of Subagent-Driven or Inline Execution, then load the selected Superpowers execution skill before Task 1.
```
