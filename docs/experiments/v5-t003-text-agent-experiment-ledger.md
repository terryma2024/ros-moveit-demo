# V5-T003 Text Agent Experiment Ledger

```yaml
task_id: so101-v5-t003-text-agent
goal: Implement and final-review-correct the approved V5-T003 single-turn text instruction agent with deterministic validation, preview-bound confirmation, verified provenance, fail-closed providers, and the existing MuJoCo dynamic cup pick-place runtime boundary.
success_contract: RED-GREEN tests prove the closed planner outcome, confirmation digest, provider boundary, verified provenance, atomic idempotency, and bounded qwen behavior; focused/full package tests pass; final-candidate ai-station DeepSeek, Mac DeepSeek, and Mac qwen simulations each preview then execute exactly once with correlated cleanup, without claiming V5-T005 physical completion.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-text-agent
branch: codex/v5-t003-text-agent
base_commit: e58eee1a2ad94c859a6784bb968ca9702ec4031a
current_commit: 4ebdf451021f975f5f4903777bdcd5bb9a31b347 (final production candidate; final documentation commit is resolved live at handoff)
documentation_snapshot_parent: 44a4471cd1df4d6d15e8f69cf1eeea66f295ba2d
live_commit_rule: Every live experiment records the exact committed production candidate before mutation; final documentation resolves its containing commit with `git rev-parse HEAD` at handoff rather than embedding a self-reference.
evidence_root: /tmp/so101-debug-v5-t003-text-agent-20260829-164105
confirmed_conclusions:
  - Local moveit-demo is at e58eee1 while ai-station is at e6ab8c1; source/install/runtime parity must be established before live validation (CP-001).
  - V5-T003 acceptance ends at correct state-machine dispatch and does not claim V5-T005 physical pick-place completion (CP-001).
  - Local candidate validation at 25c30bec8aae4dd5fc0ca6b29945febe660f9d87 passed focused and package gates; the offline preview validated a fallback-marked PlannerCandidate without dispatch (EXP-001).
  - Final candidate 4ebdf451021f975f5f4903777bdcd5bb9a31b347 closes the final-review findings and the EXP-005 qwen reasoning/prompt boundary with TDD evidence.
  - EXP-006 ai-station DeepSeek, EXP-007 Mac DeepSeek, and EXP-008 Mac qwen are each VALID at the final candidate with exactly one execute, correlated runtime completion, and clean targeted shutdown.
disproven_routes:
  - Treating a valid-looking planner command as sufficient authorization without a preview-bound digest.
  - Treating old-candidate EXP-003/004 or fail-closed EXP-005 as qualification of the newer final candidate.
open_hypotheses:
  - NONE within V5-T003; physical acceptance belongs to separately authorized V5-T005 work.
latest_checkpoint: CP-004
next_experiment: NONE
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
experiment_id: EXP-002
status: VALID
prior_experiment: EXP-001
hypothesis: The committed V5-T003 candidate can pass fail-closed preview qualification and perform exactly one authorized ai-station MuJoCo state-machine dispatch correlated by request_id and runtime session ID, without claiming V5-T005 physical success.
prediction: Preview cases reject every incomplete or invalid request without a dynamic_cup_pick_place process, while one fully authorized installed-CLI execute request reaches the existing state-machine dispatch boundary exactly once with request_id/runtime session ID v5-t003-live-001.
single_variable: One authorized live execute dispatch is added after preview and isolated-stack readiness gates; candidate implementation, request/session ID, install prefix, ROS domain, and Gazebo partition remain fixed.
lifecycle: ISOLATED_STACK
preconditions:
  - Candidate source commit is exactly 02e086be0171f08bb5e936901c79bfa70cda665f and is transferred with ancestry and file-hash read-back without overwriting ai-station user changes.
  - ai-station checkout, install overlay, tmux sessions, relevant processes, ROS graph, Ollama qwen3.5:4b availability, and provider availability are inspected read-only before any remote write.
  - No conflicting pre-existing gz sim, move_group, rviz2, dynamic_cup_pick_place, or text_pick_agent process exists in ROS_DOMAIN_ID 198 and GZ_PARTITION v5-t003-text-agent-task8-ai-20260829-164105.
  - The only registered evidence root is /tmp/so101-debug-v5-t003-text-agent-20260829-164105 and no evidence is deleted.
  - Installed so101_demo_py resolves from /data/work/ws_moveit/install/so101_demo_py and exposes text_pick_agent before stack startup.
  - Request ID and runtime session ID are both v5-t003-live-001; the observed reset epoch is supplied to the installed CLI.
success_criteria:
  - Valid preview returns dispatch=false; empty input, semantically invalid candidate, both-provider failure, unconsumed constraint, partial authorization, and wrong backend all fail closed with dispatch=false and no dynamic_cup_pick_place process.
  - The isolated MuJoCo stack is ready with fresh /cup_pose and an observed reset epoch before EXP-002 enters RUNNING.
  - Exactly one installed live CLI execute command is invoked; it validates the candidate, resolves dynamic_cup_pick_place, passes double authorization and backend qualification, calls the executor once, and produces Agent/runtime log correlation for request_id and runtime session ID v5-t003-live-001 through the state-machine dispatch attempt.
  - A single resident TextAgent harness rejects a duplicate v5-t003-live-001 request as DISPATCH_REJECTED while its injected executor call count remains one and it does not trigger a second live runtime dispatch.
  - Only task-owned processes and tmux session are stopped; cleanup read-back preserves codex, codex-cua, unrelated processes, user changes, and all evidence.
failure_criteria:
  - Any validly configured preview or the sole authorized execute reports a product-level failure while provenance, readiness, and evidence remain valid.
  - The live runtime reports a downstream MoveIt, controller, Planning Scene, or MuJoCo failure after the correlated state-machine dispatch attempt; this remains a downstream observation and is not a V5-T005 physical-success result.
invalid_criteria:
  - ai-station checkout, transferred source, built install, or runtime executable does not match candidate source commit 02e086be0171f08bb5e936901c79bfa70cda665f and expected prefix /data/work/ws_moveit/install/so101_demo_py.
  - A pre-existing conflicting process, tmux session, ROS graph, ROS_DOMAIN_ID, or GZ_PARTITION contaminates the isolated stack.
  - The execute CLI is invoked more than once, the observed reset epoch is missing or stale, request/runtime correlation is absent, or evidence leaves the sole registered evidence root.
  - User-owned checkout changes, RGB-D ledger, codex/codex-cua session, unrelated process, or evidence is modified, stopped, overwritten, stashed, reset, cleaned, or deleted.
  - Any real-hardware execution, push, merge, publication, broad cleanup, or V5-T005 physical-success claim occurs.
provenance:
  source_commit: 02e086be0171f08bb5e936901c79bfa70cda665f
  install_overlay: /data/work/ws_moveit/install/so101_demo_py
  runtime_executable: /data/work/ws_moveit/install/so101_demo_py/lib/so101_demo_py/text_pick_agent
  ros_domain_id: 198
  gz_partition: v5-t003-text-agent-task8-ai-20260829-164105
rulings:
  - RULING-EXP-002-001: The planned so101_demo_py-only build is insufficient under proven installed dependency drift. Candidate 02e086be and remote main e6ab8c1 are post-91f7ebbc and require so101_mujoco_support/graceful_shutdown_move_group, while the selected fusion-final support prefix contains only the pre-rename so101_move_group executable. Building and installing the exact candidate so101_mujoco_support package and only its required closure into /data/work/ws_moveit/install is authorized as the smallest no-code provenance repair; candidate implementation remains 02e086be.
  - RULING-EXP-002-002: The visible-only task-station wrapper failed before readiness because its external ros2_control_node could not create a GLFW window on DISPLAY=:1. Source inspection and retained ai-station EXP-211 through EXP-214 evidence establish so101_mujoco.launch.py headless=true as the supported equivalent persistent MuJoCo/controller/MoveIt/Planning Scene stack; sensor_rendering=false is sufficient because this qualification uses the test-only MuJoCo truth bridge rather than RGB-D.
  - RULING-EXP-002-003: The first headless invocation failed before starting a simulator because installed_bundle ran git rev-parse from /home/lenovo. It did not test the headless hypothesis. A one-shot no-stack installed_bundle check from the isolated source root with SO101_SOURCE_COMMIT fixed invocation provenance, after which exactly one actual headless readiness start was allowed.
  - RULING-EXP-002-004: Audit fix round 1 is documentation/evidence closure only. It may perform read-only remote verification and copy secret-safe artifacts beneath the registered evidence root, but it may not restart the provider tunnel or stack, invoke the live CLI, or execute the runtime. Pre-fix validation is fixed at 5f8994c78355c0a49ad55bde0d0e288b2bad196a; the documentation-fix commit is reported from live git rev-parse HEAD at handoff to avoid an impossible self-reference.
  - RULING-EXP-002-005: Audit fix round 2 is retained-evidence qualification only. A recursive scanner must inspect every regular file in the remote registered root and emit only aggregate coverage plus relative path/rule names; any plausible match blocks copying. With zero matches, only the already-retained injected preview artifacts may be copied locally and no preview, provider, CLI, runtime, or cleanup command may be rerun.
costs:
  - Two pre-readiness stack starts were INVALID and cleaned because the selected dependency overlay lacked graceful_shutdown_move_group. The exact retained wrappers are task8/start-stack-v2.zsh and task8/reproduce-stack-debug.zsh, both exit 1 with logs task8/stack-v2.log and task8/stack-debug.log; neither entered EXP-002 RUNNING or invoked the TextAgent execute CLI.
  - The shared install overlay received path-scoped rebuilds of candidate mujoco_ros2_control_msgs, mujoco_ros2_control_plugins, and so101_mujoco_support because the exact candidate support package requires a candidate plugin header absent from the external installed fork. No implementation source, main-checkout user file, unrelated package, user tmux session, or unrelated process was modified.
  - The visible failure, pre-provenance headless invocation, and failed build directories remain retained diagnostic artifacts. Nothing was deleted.
commands:
  - command: 'ssh ai-station ''cd /data/work/ws_moveit && git status --short && git branch --show-current && git rev-parse HEAD && git submodule status; tmux list-sessions; process/ROS/provider collision checks'''
    exit_code: 0
  - command: 'git bundle create /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/candidate-transport.bundle 02e086be0171f08bb5e936901c79bfa70cda665f && scp ... ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/'
    exit_code: 0
  - command: 'git -C /data/work/ws_moveit fetch /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/candidate-transport.bundle 02e086be0171f08bb5e936901c79bfa70cda665f:refs/remotes/task8/v5-t003-text-agent-transport && git -C /data/work/ws_moveit worktree add --detach /data/work/ws_moveit/.worktrees/v5-t003-text-agent-task8 02e086be0171f08bb5e936901c79bfa70cda665f'
    exit_code: 0
  - command: 'colcon build --base-paths src/so101_demo_py --packages-select so101_demo_py --symlink-install --build-base /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/build-scoped --install-base /data/work/ws_moveit/install'
    exit_code: 0
  - command: 'python3 /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/preview_cases.py'
    exit_code: 0
  - command: 'ros2 run so101_demo_py text_pick_agent --instruction ''Pick the plastic cup. Apply no constraints. Leave constraints empty.'' --request-id v5-t003-preview-live-ready --backend mujoco --ollama-model qwen3.5:4b --ollama-endpoint http://127.0.0.1:21434/api/chat --ollama-timeout-s 300.0'
    exit_code: 0
  - command: 'colcon build --base-paths third_party/mujoco_ros2_control/mujoco_ros2_control_msgs third_party/mujoco_ros2_control/mujoco_ros2_control_plugins --packages-select mujoco_ros2_control_msgs mujoco_ros2_control_plugins --build-base /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/build-closure --install-base /data/work/ws_moveit/install'
    exit_code: 0
  - command: 'colcon build --base-paths src/so101_mujoco_support --packages-select so101_mujoco_support --cmake-clean-cache --build-base /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/build-support --install-base /data/work/ws_moveit/install'
    exit_code: 0
  - command: 'tmux new-session -d -s v5-t003-task8-stack -n stack "zsh -f /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/start-stack-v2.zsh > /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/stack-v2.log 2>&1"'
    exit_code: 0
    runtime_exit_code: 1
    evidence: task8/start-stack-v2.zsh; task8/stack-v2.log; selected fusion-final support libexec lacked graceful_shutdown_move_group
  - command: 'tmux new-session -d -s v5-t003-task8-diagnose -n debug "zsh -f /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/reproduce-stack-debug.zsh > /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/stack-debug.log 2>&1"'
    exit_code: 0
    runtime_exit_code: 1
    evidence: task8/reproduce-stack-debug.zsh; task8/stack-debug.log; debug reproduction of the same selected-overlay failure, followed by targeted owned-session cleanup
  - command: 'ros2 launch so101_demo_py so101_mujoco_task_station.launch.py headless:=false session_id:=v5-t003-live-001 task_evidence_root:=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/stack include_teleop:=false readiness_timeout_s:=90.0'
    exit_code: 1
  - command: 'tmux new-session -d -s v5-t003-text-agent-task8-headless "/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/start-stack-headless.zsh > /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/stack-headless.log 2>&1"'
    exit_code: 0
    runtime_exit_code: 1
    evidence: task8/start-stack-headless.zsh; task8/stack-headless.log; failed before simulator because git rev-parse HEAD ran outside a checkout
  - command: 'SO101_SOURCE_COMMIT=02e086be0171f08bb5e936901c79bfa70cda665f python3 -c ''from so101_demo.runtime.provenance import installed_bundle; print(installed_bundle().bundle_sha256)'''
    exit_code: 0
  - command: 'ros2 launch so101_demo_py so101_mujoco.launch.py run_mode:=execute execute:=true headless:=true sensor_rendering:=false session_id:=v5-t003-live-001 evidence_file:=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/stack-headless-v2/unused-result.json readiness_timeout_s:=90.0'
    exit_code: 0
  - command: 'ros2 run so101_demo_py text_pick_agent --instruction ''Pick the plastic cup. Apply no constraints. Leave constraints empty.'' --request-id v5-t003-live-001 --mode execute --execute --backend mujoco --ollama-model qwen3.5:4b --ollama-endpoint http://127.0.0.1:21434/api/chat --ollama-timeout-s 300.0 --session-id v5-t003-live-001 --expected-reset-epoch 0 --evidence-root /tmp/so101-debug-v5-t003-text-agent-20260829-164105 --source-commit 02e086be0171f08bb5e936901c79bfa70cda665f --installed-prefix /data/work/ws_moveit/install/so101_demo_py'
    exit_code: 0
  - command: 'python3 /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/duplicate_request_harness.py'
    exit_code: 0
  - command: 'tmux send-keys -t v5-t003-text-agent-task8-headless-v2:cup-pose C-c; tmux send-keys -t v5-t003-text-agent-task8-headless-v2:zsh C-c'
    exit_code: 0
  - command: 'tmux has-session -t v5-t003-text-agent-task8-headless-v2'
    exit_code: 1
    evidence: task8/owned-cleanup.log; expected owned session absent after targeted SIGINT
  - command: 'tmux list-sessions 2>/dev/null'
    exit_code: 0
    evidence: task8/final-cleanup-readback-v2.log; only codex and codex-cua
  - command: 'ps -eo pid,ppid,args | grep -E ''[m]ove_group|[d]ynamic_cup_pick_place|[t]ext_pick_agent|[r]os2_control_node|[m]ujoco_cup_pose_bridge|[r]obot_state_publisher|[s]o101_mujoco'''
    exit_code: 1
    evidence: task8/final-cleanup-readback-v2.log; expected no related process
  - command: 'source /opt/ros/jazzy/setup.bash; export ROS_DOMAIN_ID=198; ros2 node list --no-daemon'
    exit_code: 0
    evidence: task8/final-cleanup-readback-v2.log; empty graph
  - command: 'curl --silent --show-error --max-time 3 http://127.0.0.1:21434/api/tags'
    exit_code: 7
    evidence: task8/final-cleanup-readback-v2.log; expected closed provider tunnel
  - command: 'ssh ai-station ''python3 -'' < /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/remote_secret_scan.py'
    exit_code: 0
    evidence: candidate_file_count=14; secret_match_path_count=0; output contains only counts and would contain paths, never values, on a match
  - command: 'ssh ai-station ''cd /tmp/so101-debug-v5-t003-text-agent-20260829-164105 && sha256sum task8/live-execute-count.log task8/preview-live-ready.json task8/duplicate-request-proof.json dynamic-execute-manifest.json reachability-observed.json task8/live-execute.log task8/stack-headless-v2.log task8/stack-headless-v2-provenance.log task8/start-stack-v2.zsh task8/stack-v2.log task8/reproduce-stack-debug.zsh task8/stack-debug.log task8/start-stack-headless.zsh task8/stack-headless.log'''
    exit_code: 0
    evidence: task8/audit-fix-round1/remote.sha256
  - command: 'scp ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/live-execute-count.log ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/preview-live-ready.json ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/duplicate-request-proof.json /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/copied-remote/task8/'
    exit_code: 0
  - command: 'scp ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/dynamic-execute-manifest.json ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/reachability-observed.json /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/copied-remote/'
    exit_code: 0
  - command: 'scp ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/live-execute.log ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/stack-headless-v2.log ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/stack-headless-v2-provenance.log /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/copied-remote/task8/'
    exit_code: 0
  - command: 'scp ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/start-stack-v2.zsh ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/stack-v2.log ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/reproduce-stack-debug.zsh ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/stack-debug.log ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/start-stack-headless.zsh ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/stack-headless.log /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/copied-remote/task8/'
    exit_code: 0
    evidence: task8/audit-fix-round1/copied-remote; no remote mutation and no file outside the zero-match candidate set copied
  - command: 'python3 /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/evidence_contract_check.py'
    exit_code: 0
    evidence: task8/audit-fix-round1/contract-check.json; 14/14 remote/local hashes equal, execute count one, duplicate executor_calls one, zero secret-pattern paths
  - command: 'PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_task_command.py src/so101_demo_py/test/test_planner_chain.py src/so101_demo_py/test/test_planner_adapters.py src/so101_demo_py/test/test_text_agent.py src/so101_demo_py/test/test_pick_place_executor_adapter.py src/so101_demo_py/test/test_text_pick_agent_cli.py -q --junitxml=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/local-final/focused.xml'
    exit_code: 0
    evidence: task8/audit-fix-round1/local-final/focused.log; 139 passed at live final documentation HEAD
  - command: 'PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test -q --junitxml=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/local-final/full-package.xml'
    exit_code: 1
    evidence: task8/audit-fix-round1/local-final/full-package.log; 628 passed and 64 failed because ROS launch attempted sandbox-disallowed /Users/matianyi/.ros/log writes; no product assertion failed before that PermissionError
  - command: 'ROS_HOME=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/local-final/ros-home ROS_LOG_DIR=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/local-final/ros-home/log PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test -q --junitxml=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/local-final/full-package-corrected.xml'
    exit_code: 0
    evidence: task8/audit-fix-round1/local-final/full-package-corrected.log; 692 passed at live final documentation HEAD
  - command: 'ssh ai-station ''python3 - f6625317a4b8e3f2ec7790aa57bcbe254705c6068ca4a133712dea8e627d3e82'' < /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round2/full_root_secret_scan.py'
    exit_code: 0
    evidence: task8/audit-fix-round2/full-root-secret-scan-report.txt; scanner definition so101-full-root-credential-values-private-keys-v1 version 1.0.0 hash f6625317, 2143 regular files, 206053346 bytes, zero match paths
  - command: 'ssh ai-station ''python3 -'' < /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round2/remote_preview_matrix_check.py'
    exit_code: 0
    evidence: task8/audit-fix-round2/remote-preview-matrix-report.json; seven exact named cases, aggregate dispatch false, dispatch_true_count 0, executor_calls_total 0
  - command: 'ssh ai-station ''cd /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8 && sha256sum preview-injected.json preview-injected.stderr.log preview_cases.py; grep -c "execute_invocation_count=1" live-execute-count.log; printf "execute_count_check_exit=%s\n" "$?"; ps -eo pid,ppid,args | grep -E "[m]ove_group|[d]ynamic_cup_pick_place|[t]ext_pick_agent|[r]os2_control_node|[m]ujoco_cup_pose_bridge|[r]obot_state_publisher|[s]o101_mujoco"; printf "related_process_exit=%s\n" "$?"'''
    exit_code: 0
    nested_exit_codes: sha256sum 0; execute-count grep 0 with one matching line; related-process grep 1 expected no match
  - command: 'scp ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/preview-injected.json ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/preview-injected.stderr.log ai-station:/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/preview_cases.py /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/copied-remote/task8/'
    exit_code: 0
    evidence: extended task8/audit-fix-round1/remote.sha256 and task8/audit-fix-round2/artifact.sha256; all three remote/local hashes equal
  - command: 'python3 /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/evidence_contract_check.py'
    exit_code: 0
    evidence: task8/audit-fix-round2/contract-check.json; 17/17 hashes equal, seven-case matrix valid, full-root scan contract valid, execute count one, duplicate executor_calls one
  - command: 'ROS_HOME=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round2/local-final/ros-home ROS_LOG_DIR=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round2/local-final/ros-home/log PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_task_command.py src/so101_demo_py/test/test_planner_chain.py src/so101_demo_py/test/test_planner_adapters.py src/so101_demo_py/test/test_text_agent.py src/so101_demo_py/test/test_pick_place_executor_adapter.py src/so101_demo_py/test/test_text_pick_agent_cli.py -q --junitxml=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round2/local-final/focused.xml'
    exit_code: 0
    evidence: task8/audit-fix-round2/local-final/focused.log; 139 passed at live final documentation HEAD
  - command: 'ROS_HOME=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round2/local-final/ros-home ROS_LOG_DIR=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round2/local-final/ros-home/log PYTHONNOUSERSITE=1 /Users/matianyi/ros2_jazzy/.venv/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test -q --junitxml=/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round2/local-final/full-package.xml'
    exit_code: 0
    evidence: task8/audit-fix-round2/local-final/full-package.log; 692 passed at live final documentation HEAD
observed:
  - CP-002 restored before remote access: EXP-001 is the last valid experiment; owned processes are NONE; codex and codex-cua are preserved; ai-station parity, provider availability, and live correlation remain open.
  - Corrected headless readiness passed after the installed-bundle preflight fixed invocation provenance without code changes: source/cwd are the isolated candidate 02e086be0171f08bb5e936901c79bfa70cda665f, SO101_SOURCE_COMMIT matches, bundle SHA-256 is 12623bb80044d8e6f3a415f01eabf6e345849258d4263fdb2cf65d39a3ab034e, and the installed package prefix is /data/work/ws_moveit/install/so101_demo_py.
  - Before EXP-002 entered RUNNING, the durable readiness/ownership snapshot recorded stack pane/launch PID 3062266; persistent child PIDs 3062375 robot_state_publisher, 3062376 ros2_control_node, and 3062380 graceful_shutdown_move_group; bridge pane/PID 3064379; and already-exited one-shot child PIDs 3062377, 3062378, 3062379, and 3062385. The preserved codex/codex-cua panes 75520 and 365114 were not task-owned. All three required controllers were active, Planning Scene READ_BACK succeeded, simulation evidence correlated to v5-t003-live-001/reset_epoch 0, and a fresh world-frame /cup_pose was observed; live execute count was still zero at this transition. Evidence: task8/headless-readiness.log, task8/headless-cup-pose-readiness.log, task8/stack-headless-v2-provenance.log, and task8/stack-headless-v2.log.
  - Injected provider cases covered valid preview, empty input, invalid primary candidate, both-provider failure, unconsumed constraint, partial authorization, and wrong backend. Every rejection had dispatch=false and executor_calls=0; no dynamic runtime process appeared.
  - The Mac Ollama reverse tunnel exposed qwen3.5:4b digest 2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd at remote localhost:21434 without installing on ai-station. Earlier live previews failed closed for model-added constraints and timeout; the readiness-gated no-constraint preview returned DISPATCH_PREVIEW with dispatch=false.
  - Exactly one installed live execute command was invoked. qwen3.5:4b returned plastic_cup/pick/{}; Agent output has dispatch=true, capability dynamic_cup_pick_place, request_id v5-t003-live-001, runtime_session_id v5-t003-live-001, state_trace RUNTIME_STARTED then RUNTIME_COMPLETED, and exit 0.
  - Correlated runtime evidence reports status DONE, transition_count 19, simulation_session_id v5-t003-live-001, expected_reset_epoch 0, and reachability SUCCEEDED. These are downstream MoveIt/controller/Planning Scene/MuJoCo observations only and do not establish V5-T005 physical success.
  - Before DONE/19, the complete live execute log reported 20 CUP_POSE_INVALID/CUP_POSE_STALE outcomes with message source stamp is too far in the future; the post-dispatch read-back tail retains the final six. One RosCupPoseSource.get_one acquisition continued within its unchanged absolute deadline, reported and skipped each invalid queued sample, then accepted the first later sample within the clock-skew contract. There was no Text Agent re-dispatch, second runtime, or restart. These transient failures and recovery are downstream observations only and make no V5-T005 claim.
  - The resident duplicate harness handled v5-t003-live-001 twice, returned RUNTIME_COMPLETED then DISPATCH_REJECTED/DUPLICATE_REQUEST_ID, and recorded executor_calls=1 without a second live runtime dispatch.
  - Cleanup sent SIGINT only to the two windows of owned tmux session v5-t003-text-agent-task8-headless-v2. Final read-back has only codex and codex-cua, no related process, no ROS node in domain 198, and remote port 21434 closed. The Mac SSH master PIDs 98246 and 6473 were each closed through their task-owned control socket.
  - ai-station focused Text Agent suite passed 139 tests. Direct full package pytest passed 690 and failed 2 mujoco_rgbd_batch mock argv assertions; the colcon package runner additionally had 11 workspace-relative FileNotFound failures. Current evidence does not establish whether those remote runner failures predated this task, so historical attribution remains unresolved. No implementation change was made for them.
  - Audit fix round 1 read-only verified 14 candidate artifacts on ai-station, printed only candidate/secret-match path counts, copied only files with zero secret-pattern matches into task8/audit-fix-round1/copied-remote, and proved 14/14 remote/local SHA-256 equality. The deterministic contract proves execute_invocation_count=1, preview DISPATCH_PREVIEW/dispatch=false, duplicate executor_calls=1 with DUPLICATE_REQUEST_ID, runtime DONE/19, reachability SUCCEEDED, and zero secret-pattern paths.
  - The first final-HEAD full-suite command omitted task-owned ROS_HOME/ROS_LOG_DIR and therefore produced 64 sandbox PermissionError failures while launch logging attempted /Users/matianyi/.ros/log; 628 tests passed. The smallest environment-only correction routed both paths beneath task8/audit-fix-round1/local-final/ros-home, after which the unchanged 692-test suite passed. No source or runtime change was made.
  - Audit fix round 2 recursively scanned all 2143 regular files and 206053346 raw bytes beneath the remote registered evidence root using scanner version 1.0.0/hash f6625317a4b8e3f2ec7790aa57bcbe254705c6068ca4a133712dea8e627d3e82. It found zero credential/private-key/Bearer/token match paths and printed no matched content or secret value.
  - The retained injected matrix has exactly valid_preview, empty_input, semantic_invalid_primary_candidate, both_provider_failure, unconsumed_constraint, partial_authorization, and wrong_backend. The valid preview is DISPATCH_PREVIEW/exit 0; all six rejection cases have their expected failure status/reason and exit 1. Every case has dispatch=false and executor_calls=0; no provider or preview command was rerun.
  - The three newly copied injected artifacts match ai-station byte-for-byte: preview-injected.json b85a95c734276290b254f54cf0fa84993843f9a4bd615fd8a123d7a1675a6a45, empty stderr e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855, and preview_cases.py d4c8e4fd2a270860abc531700d7a38c648c2e244f9db059240b56e07a36cf4fa.
inferred:
  - V5-T003 ai-station qualification is complete at the fail-closed provider, installed CLI, exactly-once state-machine dispatch, correlation, duplicate-request, and owned-cleanup boundaries.
  - The retained runtime DONE/19 data is useful downstream diagnostic evidence but is intentionally not promoted to a V5-T005 physical-success conclusion.
conclusion: VALID for V5-T003. The installed Text Agent dispatched the qualified MuJoCo state machine exactly once with request/runtime correlation and clean owned shutdown; real hardware and V5-T005 physical acceptance remain outside scope.
evidence:
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/dynamic-execute-manifest.json
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/reachability-observed.json
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round2/
decision: KEEP
next_experiment: NONE
```

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-002
documentation_snapshot_parent: 32dd34a39b540f20a682d3aa088e27c50b5a104f
current_hypothesis: No further V5-T003 experiment is required; any physical-success claim belongs to separately planned and authorized V5-T005 acceptance.
working_tree_status: "Final ledger/result commit is 5357762448a06d2e43c0210fc1ca00cb08e06501 and pre-fix verification/report commit is 5f8994c78355c0a49ad55bde0d0e288b2bad196a. Audit fix round 1 commit is afe7b7ade4aaad1220008aad08ac4dd1073822c6; round 2 uses the same live/final-doc rule and resolves its commit with git rev-parse HEAD at handoff rather than embedding a self-reference. ai-station main remains e6ab8c1 with only its preserved untracked RGB-D ledger; isolated candidate remains 02e086be with gitlink 71bc934. No source implementation was changed."
owned_processes: NONE
preserved_processes: ai-station tmux sessions codex and codex-cua; unrelated desktop processes. The task-owned SSH reverse tunnels and task-owned stack session were closed.
confirmed_conclusions:
  - Installed source/runtime parity is candidate 02e086be at /data/work/ws_moveit/install/so101_demo_py; text_pick_agent SHA-256 is 07b82ce9518ee33b58c81f377480c1dc7827ecc7dce331a50098ed08065b8dd3.
  - Candidate support closure resolves graceful_shutdown_move_group from /data/work/ws_moveit/install/so101_mujoco_support with SHA-256 6afcbd6c9f417d06934cdf54121f3c0ee2068e4d8a9e96a08ce70319eb35f042.
  - Exactly one live execute was invoked and it produced correlated request/runtime session v5-t003-live-001, dispatch=true, RUNTIME_COMPLETED, runtime DONE/19, and exit 0.
  - The live runtime first rejected 20 future-stamped queued /cup_pose samples within one absolute-deadline acquisition, including the final six retained in live-post-dispatch-readback.log, then accepted a contract-valid later sample without Text Agent re-dispatch or runtime restart. This is downstream diagnostic evidence only.
  - Duplicate request proof rejected the second resident-agent request with one injected executor call and no second live dispatch.
  - Final cleanup preserved user state and left no owned tmux session, process, ROS node, or provider tunnel.
  - Audit fix round 1 copied 14 secret-safe artifacts beneath the registered evidence root and proved remote/local hash equality, execute count one, duplicate executor_calls one, and zero secret-pattern paths.
  - Audit fix round 2 proves the complete seven-case tested-injected matrix with dispatch=false/executor_calls=0 in every case, extends copied remote hash coverage to 17 files, and recursively scans all 2143 regular remote-root files/206053346 bytes with zero secret match paths.
disproven_routes:
  - Treating visible DISPLAY=:1 as qualified merely because xdpyinfo succeeds; the runtime failed GLFW window creation.
  - Treating a task-station-only wrapper as the only persistent stack path; the supported generic headless launch composes the same controller/MoveIt/scene stack.
  - Treating runtime DONE, transition count, or manifest physical fields as V5-T005 physical acceptance within V5-T003.
open_risks:
  - Live qwen3.5:4b latency was 120139 ms for execute and earlier previews demonstrated constraint drift and timeout; fail-closed behavior is qualified, not model service-level reliability.
  - ai-station /data/work/ws_moveit/install/setup.zsh remains stale because unrelated indexed packages are absent; this task sourced exact package scripts and explicit prefix ordering instead of changing unrelated overlay state.
  - ai-station direct full package pytest has two test_mujoco_rgbd_batch_cli mock argv failures; colcon cwd adds eleven workspace-relative path failures. Current evidence does not establish their historical attribution. Fresh pre-fix evidence verification at 5f8994c78355c0a49ad55bde0d0e288b2bad196a passed 139 focused and 692 full-package tests; audit-fix round 2 final-HEAD results are retained in task8/audit-fix-round2/local-final under the live/final-doc rule.
evidence_disposition:
  retained: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/ (Task 8 build, provider, readiness, live execute, duplicate, runtime manifest, cleanup, audit-fix-round1 copied/hash-contract artifacts, and audit-fix-round2 matrix/full-root-scan artifacts remain beneath this sole registered root)
  archived: NONE
  deletion_candidates: task8/build, task8/build-clean, task8/build-staging, task8/staging-install, failed visible/headless diagnostic wrappers and logs; listed only, nothing deleted
next_command: Begin any V5-T005 physical acceptance only from a separately planned and explicitly authorized experiment; do not reuse V5-T003 runtime DONE as physical proof.
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

```yaml
experiment_id: EXP-003
status: VALID
transitions:
  - status: PLANNED
    recorded_in_commit: e71f556f553c2f6749ff653044f5035235a67b10
  - status: RUNNING
    recorded_at: 2026-08-30T01:05:15+08:00
    evidence: final-fix/ai-station/exp-003-ai-deepseek-785a95e/{build-provenance-corrected.log,focused.xml,stack-provenance.log,simulation-evidence-readiness.log,cup-pose-readiness.log,controllers-readiness.log,owned-panes-readiness.log}
  - status: VALID
    recorded_at: 2026-08-30T01:11:36+08:00
    evidence: final-fix/ai-station/exp-003-ai-deepseek-785a95e/{preview.json,execute-invocation.marker,execute.json,execute-result.json,text-agent-provenance,dynamic-execute-manifest.json,reachability-observed.json,cleanup-readback-no-daemon.log}
execute_invocation_count: 1
observed_reset_epoch: 0
prior_experiment: EXP-002
hypothesis: The corrected committed candidate can use the qualified DeepSeek provider on ai-station and execute the existing headless MuJoCo state machine exactly once with preview-bound confirmation and verified runtime provenance.
prediction: One DeepSeek preview returns supported plastic_cup/pick/{}, provider/model deepseek/deepseek-v4-flash, and the precomputed digest; the exact instruction/digest pair then produces one correlated execute invocation and clean owned shutdown.
single_variable: The corrected candidate and DeepSeek provider replace EXP-002's earlier candidate/qwen provider; the supported headless stack composition and V5-T003 evidence boundary remain unchanged.
lifecycle: ISOLATED_STACK
preconditions:
  - Candidate source is exactly 785a95e9df5dd18f32d8cb7d875f3fac948ce53e, transferred by an ancestry/hash-verified bundle into a new detached task-owned worktree without modifying ai-station main.
  - ai-station main/submodule/status, tmux/process/ROS state, preserved RGB-D ledger, and DEEPSEEK_API_KEY SET/UNSET state are read back before mutation without printing the value.
  - A candidate-only so101_demo_py overlay is built beneath this experiment evidence identity and resolves the imported module and installed entry point to the exact candidate.
  - A fresh supported headless stack and one test-only MuJoCo truth bridge pass controller, Planning Scene, reset-epoch, and fresh /cup_pose readiness before status changes to RUNNING.
instruction: Pick the plastic cup.
provider: deepseek
model: deepseek-v4-flash
endpoint: https://api.deepseek.com/chat/completions
preview_digest: sha256:v1:a362fa42188acf5e277bc88ae17d1bb64ed41aa8db957101bc1075a27c837cfb
request_id: v5-t003-exp003-ai-deepseek-785a95e
runtime_session_id: v5-t003-exp003-ai-deepseek-785a95e
expected_reset_epoch: CAPTURE_FROM_READINESS_BEFORE_RUNNING
provenance:
  source_commit: 785a95e9df5dd18f32d8cb7d875f3fac948ce53e
  source_worktree: /data/work/ws_moveit/.worktrees/v5-t003-final-fix-785a95e
  install_overlay: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/ai-station/exp-003-ai-deepseek-785a95e/install
  installed_prefix: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/ai-station/exp-003-ai-deepseek-785a95e/install/so101_demo_py
  runtime_executable: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/ai-station/exp-003-ai-deepseek-785a95e/install/so101_demo_py/lib/so101_demo_py/text_pick_agent
  ros_domain_id: 206
  gz_partition: v5-t003-exp003-ai-deepseek-785a95e
  remote_evidence_identity: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/ai-station/exp-003-ai-deepseek-785a95e
  local_copy_identity: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/ai-station/copied-remote/exp-003-ai-deepseek-785a95e
success_criteria:
  - Preview is DISPATCH_PREVIEW/dispatch=false with supported outcome, exact provider/model, normalized empty-constraint command, capability, request_id, and exact planned digest.
  - Exactly one execute command is invoked with the byte-identical instruction and preview digest; verified provenance is persisted/returned before dispatch and matches the candidate source, prefix, runtime hashes, session, reset epoch, and evidence root.
  - Agent and runtime evidence correlate the request/session through one state-machine dispatch and RUNTIME_COMPLETED; downstream observations are recorded by layer without a V5-T005 claim.
  - Cleanup targets only recorded experiment PIDs/tmux panes and final read-back preserves codex, codex-cua, ai-station main, the untracked RGB-D ledger, unrelated processes, and all evidence.
failure_criteria:
  - Qualified provider/stack/provenance remain valid but the sole execute returns a product-level runtime failure or correlated downstream failure.
invalid_criteria:
  - Provider/model/digest/instruction/provenance/readiness mismatch, execute count other than one, contamination by an existing process/domain/partition, missing correlation, evidence outside the registered root, user-state modification, broad cleanup, real hardware, or V5-T005 claim.
execution_rule: Preview retries, if any, are separately recorded fail-closed provider observations; after the sole execute command is invoked it is never rerun.
observed:
  - Candidate source, imported module, installed prefix, entry point, and persisted/returned artifact hashes resolve to 785a95e9df5dd18f32d8cb7d875f3fac948ce53e in the detached task worktree and experiment overlay; ai-station main remained e6ab8c1 with its untracked RGB-D ledger.
  - Focused corrected-candidate gate passed 188 tests. Headless readiness recorded three active controllers, Planning Scene READ_BACK success, fresh /cup_pose, simulation_session_id v5-t003-exp003-ai-deepseek-785a95e, reset_epoch 0, and only the two owned tmux windows.
  - Preview returned DISPATCH_PREVIEW/dispatch=false with supported plastic_cup/pick/{}, deepseek/deepseek-v4-flash, request ID match, and exact digest sha256:v1:a362fa42188acf5e277bc88ae17d1bb64ed41aa8db957101bc1075a27c837cfb.
  - Exactly one execute command was invoked. It exited 0 and its final Agent JSON reports dispatch=true, RUNTIME_STARTED then RUNTIME_COMPLETED, exact request/runtime session correlation, DeepSeek provider/model, and verified provenance. The mixed stdout also contains dynamic runtime status lines, so the first whole-stream JSON parser failed after the successful execute; execute-result.json is the byte-preserved final JSON line, not a retry.
  - Dynamic runtime reached DONE with transition_count 19; reachability was SUCCEEDED; controller logs record 22 arm, 3 gripper, and 22 MoveIt successful execution messages. Two future-stamped /cup_pose samples were rejected within the same acquisition before a valid sample was accepted. These are downstream diagnostics only and make no V5-T005 claim.
  - Targeted SIGINT cleanup removed only v5-t003-exp003-ai-deepseek stack/bridge windows. Fresh no-daemon domain 206 discovery and related-process read-back were empty; codex and codex-cua remained.
conclusion: VALID for corrected-candidate V5-T003 ai-station DeepSeek qualification with exactly one execute and clean owned shutdown; no real-hardware or V5-T005 conclusion.
decision: KEEP
next_experiment: EXP-004
```

```yaml
experiment_id: EXP-004
status: VALID
transitions:
  - status: PLANNED
    recorded_in_commit: e71f556f553c2f6749ff653044f5035235a67b10
    provenance_path_amended_in_commit: ea9496405b959e51dd8a1c16ec7d03ff698350c4
  - status: RUNNING
    recorded_at: 2026-08-30T01:34:59+08:00
    evidence: final-fix/mac-deepseek/exp-004-mac-deepseek-785a95e/{stack-provenance-attempt2.log,full-readiness-corrected.log,simulation-and-cup-readiness-corrected.log,owned-panes-attempt2-start.log}
  - status: VALID
    recorded_at: 2026-08-30T01:42:35+08:00
    evidence: final-fix/mac-deepseek/exp-004-mac-deepseek-785a95e/{preview.json,execute-invocation.marker,execute.json,execute-result.json,text-agent-provenance,dynamic-execute-manifest.json,reachability-observed.json,downstream-layer-summary.log,cleanup-readback-no-daemon.log}
execute_invocation_count: 1
observed_reset_epoch: 0
prior_experiment: EXP-003
hypothesis: After valid ai-station requalification, the same corrected candidate can use DeepSeek on Mac and execute one fresh isolated headless MuJoCo simulation with exact preview confirmation and provenance.
prediction: The Mac DeepSeek preview returns the planned supported candidate/digest, then one and only one confirmed execute reaches the correlated state machine and cleans up its owned stack.
single_variable: Host changes from ai-station to Mac while candidate, provider/model, instruction, confirmation contract, and headless composition remain fixed.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-003 is VALID; otherwise this experiment remains PLANNED and no Mac live mutation occurs.
  - Local candidate HEAD and worktree install resolve exactly to 785a95e9df5dd18f32d8cb7d875f3fac948ce53e.
  - Mac processes, ROS graph, candidate overlay, DEEPSEEK_API_KEY SET/UNSET state, Ollama tags/model digest, and headless runtime support are inspected before stack startup without printing credential values.
  - A fresh headless stack and one test-only truth bridge pass readiness in the unique domain/partition before status changes to RUNNING; unsupported headless runtime makes this experiment INVALID/BLOCKED without visible-mode substitution.
instruction: Pick the plastic cup.
provider: deepseek
model: deepseek-v4-flash
endpoint: https://api.deepseek.com/chat/completions
preview_digest: sha256:v1:a362fa42188acf5e277bc88ae17d1bb64ed41aa8db957101bc1075a27c837cfb
request_id: v5-t003-exp004-mac-deepseek-785a95e
runtime_session_id: v5-t003-exp004-mac-deepseek-785a95e
expected_reset_epoch: CAPTURE_FROM_READINESS_BEFORE_RUNNING
provenance:
  source_commit: 785a95e9df5dd18f32d8cb7d875f3fac948ce53e
  source_worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-final-fix-mac-785a95e
  install_overlay: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-candidate-785a95e/install
  installed_prefix: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-candidate-785a95e/install/so101_demo_py
  runtime_executable: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-candidate-785a95e/install/so101_demo_py/lib/so101_demo_py/text_pick_agent
  ros_domain_id: 207
  gz_partition: v5-t003-exp004-mac-deepseek-785a95e
  evidence_identity: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-deepseek/exp-004-mac-deepseek-785a95e
success_criteria:
  - Preview is DISPATCH_PREVIEW/dispatch=false with supported outcome, deepseek/deepseek-v4-flash, normalized empty-constraint command, request_id, and exact planned digest.
  - Exactly one byte-identical confirmed execute invocation returns verified provenance and reaches correlated state-machine dispatch/RUNTIME_COMPLETED in the fresh Mac headless stack.
  - Downstream observations are separated by Agent, state machine, MoveIt/Planning Scene, controllers, and MuJoCo layers; cleanup removes only recorded owned processes and leaves no experiment ROS nodes.
failure_criteria:
  - Qualified provider/stack/provenance remain valid but the sole execute returns a product-level runtime or correlated downstream failure.
invalid_criteria:
  - EXP-003 not VALID; Mac headless unsupported; provider/model/digest/instruction/provenance/readiness mismatch; execute count other than one; contamination, missing correlation, broad cleanup, evidence loss, real hardware, or V5-T005 claim.
execution_rule: Preview retries, if any, are separately recorded fail-closed provider observations; after the sole execute command is invoked it is never rerun.
observed:
  - The first headless precondition attempt exposed a stale standalone-fork MuJoCo message library that the macOS dylib-farm wrapper had prepended ahead of the project-qualified library, causing a simulation-evidence plugin ABI mismatch. No preview or execute occurred, status remained PLANNED, targeted cleanup removed only the owned panes, and the preserved diagnostic evidence records the root cause. The corrected wrapper mirrors the approved environment ordering: project libraries first, stale standalone paths filtered, and the dylib farm appended.
  - The second fresh headless stack resolved candidate source/install provenance exactly to 785a95e9df5dd18f32d8cb7d875f3fac948ce53e, loaded the project MuJoCo packages, activated three controllers, passed Planning Scene READ_BACK, and produced fresh /so101/simulation/evidence plus /cup_pose for simulation_session_id v5-t003-exp004-mac-deepseek-785a95e at reset_epoch 0.
  - Preview returned DISPATCH_PREVIEW/dispatch=false with supported plastic_cup/pick/{}, deepseek/deepseek-v4-flash, exact request ID, and digest sha256:v1:a362fa42188acf5e277bc88ae17d1bb64ed41aa8db957101bc1075a27c837cfb; its stderr was empty.
  - Exactly one execute command was invoked. It exited 0 and its final Agent JSON reports dispatch=true, RUNTIME_STARTED then RUNTIME_COMPLETED, exact request/runtime session correlation, DeepSeek provider/model, and verified source/prefix/module/entry-point/Python/session/reset/evidence provenance persisted before dispatch.
  - Dynamic runtime reached DONE with transition_count 19; reachability was SUCCEEDED; controller logs record 22 arm, 3 gripper, and 22 MoveIt successful execution messages. Planning Scene and final MuJoCo samples are retained as downstream diagnostics only and make no real-hardware or V5-T005 claim.
  - Targeted SIGINT cleanup removed only the two v5-t003-exp004-mac-deepseek panes. Fresh no-daemon domain 207 discovery and related-process read-back were empty; candidate and task worktrees remained clean, the DeepSeek key was reported SET without value disclosure, and the existing Ollama qwen3.5:4b service/model was preserved.
conclusion: VALID for corrected-candidate V5-T003 Mac DeepSeek qualification with exactly one execute and clean owned shutdown; no real-hardware or V5-T005 conclusion.
decision: KEEP
next_experiment: EXP-005 only if EXP-004 is VALID
```

```yaml
experiment_id: EXP-005
status: VALID
transitions:
  - status: PLANNED
    recorded_in_commit: e71f556f553c2f6749ff653044f5035235a67b10
    provenance_path_amended_in_commit: ea9496405b959e51dd8a1c16ec7d03ff698350c4
  - status: RUNNING
    recorded_at: 2026-08-30T01:50:25+08:00
    evidence: final-fix/mac-qwen/exp-005-mac-qwen-785a95e/{pre-mutation-readback-corrected.log,stack-provenance.log,full-readiness.log,owned-panes-start.log}
  - status: VALID
    recorded_at: 2026-08-30T02:03:41+08:00
    evidence: final-fix/mac-qwen/exp-005-mac-qwen-785a95e/{preview.json,preview-attempt2.json,preview-attempt3-qualified.json,provider-direct-diagnostic-corrected.json,provider-think-false-diagnostic.json,ollama-server-chat-lines-after-preview3.log,provider-invalid-cleanup-readback.log,provider-invalid-cleanup-process-readback.log}
execute_invocation_count: 0
observed_reset_epoch: 0
prior_experiment: EXP-004
hypothesis: After both DeepSeek qualifications are valid, the corrected candidate can use local qwen3.5:4b on Mac and execute one separately isolated headless MuJoCo simulation with provider-bound preview confirmation.
prediction: Loading ~/.env and then unsetting only DEEPSEEK_API_KEY selects ollama/qwen3.5:4b, returns the precomputed qwen digest, and one confirmed execute reaches the correlated state machine with clean owned shutdown.
single_variable: Provider/model changes from Mac DeepSeek to Mac loopback Ollama while candidate, host, instruction, confirmation/provenance rules, and headless composition remain fixed; domain/partition/request/session and stack are fresh.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-004 is VALID; otherwise this experiment remains PLANNED and no qwen live mutation occurs.
  - Local candidate/install provenance remains exactly 785a95e9df5dd18f32d8cb7d875f3fac948ce53e.
  - ~/.env is loaded with export semantics and suppressed output, then only DEEPSEEK_API_KEY is unset in the experiment shell; only SET/UNSET is reported.
  - Ollama loopback /api/tags proves qwen3.5:4b and records its model digest without changing the service.
  - A separate fresh supported Mac headless stack/truth bridge passes readiness in this experiment domain/partition before status changes to RUNNING.
instruction: Pick the plastic cup.
provider: ollama
model: qwen3.5:4b
endpoint: http://127.0.0.1:11434/api/chat
preview_digest: sha256:v1:48f93b8acc2bc64be60a7be8c95264e21ae4a6f1f19c9c02eec0227359e7e89e
request_id: v5-t003-exp005-mac-qwen-785a95e
runtime_session_id: v5-t003-exp005-mac-qwen-785a95e
expected_reset_epoch: CAPTURE_FROM_READINESS_BEFORE_RUNNING
provenance:
  source_commit: 785a95e9df5dd18f32d8cb7d875f3fac948ce53e
  source_worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-final-fix-mac-785a95e
  install_overlay: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-candidate-785a95e/install
  installed_prefix: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-candidate-785a95e/install/so101_demo_py
  runtime_executable: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-candidate-785a95e/install/so101_demo_py/lib/so101_demo_py/text_pick_agent
  ros_domain_id: 208
  gz_partition: v5-t003-exp005-mac-qwen-785a95e
  evidence_identity: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-qwen/exp-005-mac-qwen-785a95e
success_criteria:
  - Preview is DISPATCH_PREVIEW/dispatch=false with supported outcome, ollama/qwen3.5:4b, normalized empty-constraint command, request_id, and exact planned qwen digest.
  - Exactly one byte-identical confirmed execute invocation returns verified provenance and reaches correlated state-machine dispatch/RUNTIME_COMPLETED in the separately owned Mac headless stack.
  - Downstream observations remain V5-T003 diagnostics; targeted cleanup leaves no experiment stack/bridge/ROS process and preserves Ollama and unrelated user state.
failure_criteria:
  - Qualified provider/stack/provenance remain valid but the sole execute returns a product-level runtime or correlated downstream failure.
invalid_criteria:
  - EXP-004 not VALID; provider/model/digest/instruction/provenance/readiness mismatch; cloud key remains set; endpoint is non-loopback/non-/api/chat; headless unsupported; execute count other than one; contamination, missing correlation, broad cleanup, real hardware, or V5-T005 claim.
execution_rule: Preview retries, if any, are separately recorded fail-closed provider observations; after the sole execute command is invoked it is never rerun.
observed:
  - Preflight loaded ~/.env with export semantics and suppressed output, reported DEEPSEEK_API_KEY SET, then unset only that variable and reported UNSET. Loopback /api/tags and /api/ps resolved qwen3.5:4b with digest 2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd. Candidate/install provenance, separate headless stack, three active controllers, Planning Scene READ_BACK, fresh simulation evidence, /cup_pose, session ID, and reset_epoch 0 all passed.
  - Three separately retained preview observations used the exact instruction/request/provider/model/loopback endpoint with execute count 0. The first two used the 12-second default and the third used an evidence-based 180-second timeout after the local server log showed earlier successful qwen requests needed 1m31s and 1m59s. All three failed closed as PLANNER_FAILED/PLANNER_CHAIN_FAILED with dispatch=false, no confirmation digest, and empty stderr.
  - Ollama server request lines show each provider request ran until its client deadline and then returned 500 at 12 seconds, 12 seconds, 60 seconds, or 180 seconds; the loaded model and loopback endpoint remained healthy. A one-variable direct diagnostic adding top-level think=false returned 200/done in 6.046 seconds, isolating qwen3.5 reasoning-mode interaction with strict structured output. That diagnostic also inferred center/normal constraints absent from the instruction, proving the prompt must explicitly forbid invented constraints before the planned empty-constraint digest can be qualified.
  - No execute command was invoked, no dynamic manifest or execution provenance was created, and no state-machine dispatch occurred. This is a valid provider-boundary/fail-closed observation, not a successful qwen execution qualification.
  - Targeted SIGINT cleanup removed only the two owned EXP-005 panes. Fresh read-back found no task tmux session or related process; domain 208 had no experiment topics; candidate/task worktrees remained clean; the persistent Ollama service/model and all evidence were preserved.
conclusion: VALID fail-closed provider-boundary result for candidate 785a95e; qwen3.5 cannot qualify this candidate because reasoning mode never completes the structured preview and the diagnostic response invents unspecified constraints. No execute, real-hardware, or V5-T005 conclusion.
ruling: The controller accepted EXP-005 as a valid provider-boundary/fail-closed observation despite the original execute-oriented criteria; it does not satisfy the required qwen execute qualification, does not count as one of the corrected-candidate execution proofs, and cannot qualify any candidate newer than 785a95e.
cost: Three Agent preview calls, one 60-second direct default-reasoning diagnostic, and one 6.046-second think=false diagnostic were retained; four provider calls ended at their 12/12/60/180-second client deadlines, execute count stayed zero, and the persistent Ollama service was not restarted or changed.
decision: REPLACE after a bounded TDD correction; EXP-003 and EXP-004 remain truthful evidence for 785a95e only.
next_experiment: EXP-006 after the new final candidate is committed and fresh EXP-006/007/008 PLANNED entries are recorded.
```

```yaml
experiment_id: EXP-006
status: VALID
transitions:
  - status: PLANNED
    recorded_in_commit: 493e9aed5082385485b29dd6be16a8d833b19d98
  - status: RUNNING
    recorded_at: 2026-08-30T02:19:35+08:00
    evidence: final-fix/ai-station/exp-006-ai-deepseek-4ebdf45/{pre-mutation-readback-corrected.log,import-provenance.log,build-provenance.log,module-resolution-corrected.log,focused.xml,stack-provenance.log,full-readiness.log,owned-panes-readiness-corrected.log}
  - status: VALID
    recorded_at: 2026-08-30T02:29:33+08:00
    evidence: final-fix/ai-station/exp-006-ai-deepseek-4ebdf45/{preview.json,execute-invocation.marker,execute.json,execute-result.json,text-agent-provenance,dynamic-execute-manifest.json,reachability-observed.json,downstream-layer-summary.log,qualified-artifact-hashes.log,cleanup-readback.log,cleanup-readback-corrected.log}
execute_invocation_count: 1
observed_reset_epoch: 0
created_at: 2026-08-30T02:10:40+08:00
prior_experiment: EXP-005
correction_origin: EXP-005 proved candidate 785a95e fails closed because qwen3.5 reasoning mode does not complete strict structured output; candidate 4ebdf45 explicitly disables Ollama reasoning and forbids invented constraints.
hypothesis: The bounded final candidate can still use DeepSeek on ai-station and execute the qualified headless MuJoCo state machine exactly once with preview-bound confirmation and verified runtime provenance.
prediction: One DeepSeek preview returns supported plastic_cup/pick/{}, provider/model deepseek/deepseek-v4-flash, and the planned digest; the exact pair then produces one correlated execute invocation and clean owned shutdown.
single_variable: Candidate changes from 785a95e to 4ebdf45 while host, DeepSeek provider/model, instruction, confirmation contract, and supported headless composition remain fixed; domain/partition/request/session/evidence are fresh.
lifecycle: ISOLATED_STACK
preconditions:
  - Candidate source is exactly 4ebdf451021f975f5f4903777bdcd5bb9a31b347, transferred by an ancestry/hash-verified bundle into a new detached task-owned ai-station worktree without modifying main or preserved evidence.
  - ai-station main/submodule/status, tmux/process/ROS state, preserved RGB-D ledger, and DEEPSEEK_API_KEY SET/UNSET state are read back before mutation without printing the value.
  - A candidate-only so101_demo_py overlay resolves imported source and installed entry point to the exact candidate and passes the authoritative focused gate.
  - A fresh supported headless stack and one test-only MuJoCo truth bridge pass controller, Planning Scene, reset-epoch, and fresh /cup_pose readiness before status changes to RUNNING.
instruction: Pick the plastic cup.
provider: deepseek
model: deepseek-v4-flash
endpoint: https://api.deepseek.com/chat/completions
preview_digest: sha256:v1:a362fa42188acf5e277bc88ae17d1bb64ed41aa8db957101bc1075a27c837cfb
request_id: v5-t003-exp006-ai-deepseek-4ebdf45
runtime_session_id: v5-t003-exp006-ai-deepseek-4ebdf45
expected_reset_epoch: CAPTURE_FROM_READINESS_BEFORE_RUNNING
provenance:
  source_commit: 4ebdf451021f975f5f4903777bdcd5bb9a31b347
  source_worktree: /data/work/ws_moveit/.worktrees/v5-t003-final-qwen-4ebdf45
  install_overlay: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/ai-station/exp-006-ai-deepseek-4ebdf45/install
  installed_prefix: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/ai-station/exp-006-ai-deepseek-4ebdf45/install/so101_demo_py
  runtime_executable: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/ai-station/exp-006-ai-deepseek-4ebdf45/install/so101_demo_py/lib/so101_demo_py/text_pick_agent
  ros_domain_id: 209
  gz_partition: v5-t003-exp006-ai-deepseek-4ebdf45
  evidence_identity: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/ai-station/exp-006-ai-deepseek-4ebdf45
success_criteria:
  - Preview is DISPATCH_PREVIEW/dispatch=false with supported outcome, exact provider/model, normalized empty-constraint command, exact request ID, and planned digest.
  - Exactly one byte-identical confirmed execute returns verified provenance and reaches correlated state-machine dispatch/RUNTIME_COMPLETED; downstream observations are separated by layer without a V5-T005 claim.
  - Targeted cleanup removes only recorded owned processes and preserves ai-station main, RGB-D ledger, codex sessions, unrelated processes, and all evidence.
failure_criteria:
  - Qualified provider/stack/provenance remain valid but the sole execute returns a product-level runtime or correlated downstream failure.
invalid_criteria:
  - Provider/model/digest/instruction/provenance/readiness mismatch, execute count other than one, contamination, missing correlation, evidence loss, user-state modification, broad cleanup, real hardware, or V5-T005 claim.
execution_rule: Preview retries, if any, are separately recorded fail-closed provider observations; after the sole execute command is invoked it is never rerun.
observed:
  - The ancestry/hash-verified bundle had local and remote SHA-256 cdae8404ea013d0a74c4a9a4a8b52e0f13657023c478af5854c5857f26a370c0. The detached source worktree was clean at exact candidate 4ebdf451021f975f5f4903777bdcd5bb9a31b347, and the task-only install resolved the installed Text Agent entry point and source module to that candidate. The authoritative focused gate passed 190 tests.
  - Supported headless readiness passed with three active controllers, Planning Scene READ_BACK, fresh /so101/simulation/evidence and /cup_pose, exact simulation_session_id v5-t003-exp006-ai-deepseek-4ebdf45, reset_epoch 0, domain 209, partition match, and only the two task-owned stack/bridge panes.
  - Preview exited 0 with empty stderr and returned DISPATCH_PREVIEW/dispatch=false, supported plastic_cup/pick/{}, deepseek/deepseek-v4-flash with fallback false, exact request ID, and digest sha256:v1:a362fa42188acf5e277bc88ae17d1bb64ed41aa8db957101bc1075a27c837cfb. The retained preview SHA-256 is 731a66abfb32520966154808df20276e475f9d464821ff60720b8564d7165515.
  - Exactly one execute command was invoked with the exact instruction/digest pair. It exited 0; the final Agent result is RUNTIME_COMPLETED/dispatch=true with RUNTIME_STARTED then RUNTIME_COMPLETED, exact request/runtime session correlation, DeepSeek provider/model/fallback false, and verified source/prefix/entry-point/module/Python/session/reset/evidence provenance. The persisted provenance artifact count is one.
  - The state machine reached DONE with transition_count 19 and no failure; reachability was SUCCEEDED for perceived_cup. Controller/MoveIt logs contain 22 arm-goal, 3 gripper-goal, and 22 MoveIt execution successes. Three future-stamped /cup_pose samples were rejected within the same acquisition before a valid sample. These are downstream simulation diagnostics only and do not establish real-hardware or V5-T005 acceptance.
  - Targeted SIGINT cleanup gracefully removed the two owned panes and all five captured owned PIDs. The first cleanup assertion expected an entirely empty domain and stopped after observing two topics; systematic read-back proved they are exactly /parameter_events and /rosout, identical to preflight, with zero nodes and no experiment session/PIDs. The corrected cleanup read-back also proves ai-station main e6ab8c1/main, gitlink 71bc934, the preserved untracked RGB-D ledger, codex/codex-cua, the clean detached candidate, and the registered evidence root remain intact.
conclusion: VALID for final-candidate V5-T003 ai-station DeepSeek qualification with exactly one execute and clean owned shutdown; no real-hardware or V5-T005 conclusion.
decision: KEEP
next_experiment: EXP-007
```

```yaml
experiment_id: EXP-007
status: VALID
transitions:
  - status: PLANNED
    recorded_in_commit: 493e9aed5082385485b29dd6be16a8d833b19d98
  - status: RUNNING
    recorded_at: 2026-08-30T02:48:45+08:00
    evidence: final-fix/mac-deepseek/exp-007-mac-deepseek-4ebdf45/{pre-mutation-readback.log,pre-mutation-readback-corrected.log,runtime-env-resolution.log,stack-provenance.log,full-readiness.log,full-readiness-assertion.log,owned-panes-start.log,process-isolation-readback.log}; final-fix/mac-candidate-4ebdf45/{build-and-provenance.log,installed-provenance-corrected-v2.log,focused-corrected-v2.xml}
  - status: VALID
    recorded_at: 2026-08-30T02:55:32+08:00
    evidence: final-fix/mac-deepseek/exp-007-mac-deepseek-4ebdf45/{preview.json,pre-execute-readiness.log,execute-invocation.marker,execute.json,execute-result.json,text-agent-provenance,dynamic-execute-manifest.json,reachability-observed.json,downstream-layer-summary.log,qualified-artifact-hashes.log,cleanup-readback.log,post-cleanup-process-readback.log}
execute_invocation_count: 1
observed_reset_epoch: 0
created_at: 2026-08-30T02:10:40+08:00
prior_experiment: EXP-006
hypothesis: After valid final-candidate ai-station requalification, the same candidate can use DeepSeek on Mac and execute one fresh isolated headless MuJoCo simulation with exact preview confirmation and provenance.
prediction: The Mac DeepSeek preview returns the planned supported candidate/digest, then one and only one confirmed execute reaches the correlated state machine and cleans up its owned stack.
single_variable: Host changes from ai-station to Mac while final candidate, provider/model, instruction, confirmation contract, and headless composition remain fixed; domain/partition/request/session/evidence are fresh.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-006 is VALID; otherwise this experiment remains PLANNED and no Mac live mutation occurs.
  - Local detached candidate and isolated install resolve exactly to 4ebdf451021f975f5f4903777bdcd5bb9a31b347.
  - Mac process/ROS state, key SET/UNSET state, Ollama model/digest, and supported headless runtime are read back before startup without displaying secrets.
  - A fresh headless stack and one test-only truth bridge pass exact readiness before status changes to RUNNING; unsupported headless runtime ends this route without visible-mode substitution.
instruction: Pick the plastic cup.
provider: deepseek
model: deepseek-v4-flash
endpoint: https://api.deepseek.com/chat/completions
preview_digest: sha256:v1:a362fa42188acf5e277bc88ae17d1bb64ed41aa8db957101bc1075a27c837cfb
request_id: v5-t003-exp007-mac-deepseek-4ebdf45
runtime_session_id: v5-t003-exp007-mac-deepseek-4ebdf45
expected_reset_epoch: CAPTURE_FROM_READINESS_BEFORE_RUNNING
provenance:
  source_commit: 4ebdf451021f975f5f4903777bdcd5bb9a31b347
  source_worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-final-fix-mac-4ebdf45
  install_overlay: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-candidate-4ebdf45/install
  installed_prefix: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-candidate-4ebdf45/install/so101_demo_py
  runtime_executable: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-candidate-4ebdf45/install/so101_demo_py/lib/so101_demo_py/text_pick_agent
  ros_domain_id: 210
  gz_partition: v5-t003-exp007-mac-deepseek-4ebdf45
  evidence_identity: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-deepseek/exp-007-mac-deepseek-4ebdf45
success_criteria:
  - Preview is DISPATCH_PREVIEW/dispatch=false with supported outcome, deepseek/deepseek-v4-flash, normalized empty-constraint command, exact request ID, and planned digest.
  - Exactly one byte-identical confirmed execute returns verified provenance and reaches correlated state-machine dispatch/RUNTIME_COMPLETED in the fresh Mac headless stack.
  - Downstream evidence remains V5-T003 diagnostic and targeted cleanup leaves no experiment node/process while preserving Ollama and unrelated user state.
failure_criteria:
  - Qualified provider/stack/provenance remain valid but the sole execute returns a product-level runtime or correlated downstream failure.
invalid_criteria:
  - EXP-006 not VALID; Mac headless unsupported; provider/model/digest/instruction/provenance/readiness mismatch; execute count other than one; contamination, missing correlation, broad cleanup, evidence loss, real hardware, or V5-T005 claim.
execution_rule: Preview retries, if any, are separately recorded fail-closed provider observations; after the sole execute command is invoked it is never rerun.
observed:
  - Fresh preflight proved candidate target/overlay absent, domain 210 had only /parameter_events and /rosout with no nodes, DEEPSEEK_API_KEY was SET without value disclosure, qwen3.5:4b remained present at digest 2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd, and no related process existed. Normal-scope ps was denied and retained; the corrected read-only elevated inventory was empty.
  - The detached target initially inherited the repository's empty per-worktree config.worktree and therefore resolved its common Git directory as the work tree. A narrow per-worktree core.worktree metadata correction restored the exact target without reset or source change. The resulting worktree was clean at 4ebdf451021f975f5f4903777bdcd5bb9a31b347 with gitlink 71bc934.
  - The isolated candidate-only build exited 0 and installed Text Agent at the planned prefix. Two verifier-only harness errors were retained: an unqualified import name, then a symlink-preserving __file__ comparison; the corrected resolved-source provenance matched entry-point SHA-256 ffc193c71996d6743ca1fe7e762b25d231099fd04113efb6389be9c216fcb5d0, text-agent a30fde609c75bd4cc29bd467e161f523f7260173fdf57507aba634036b1cbbbf, Ollama adapter 656ba6ac751557c07facf8c30959c5a16b4b20a503df4171773b0452ccdece57, and prompt module 60d222cd22c3ed3539c3ccf75b4c2702d3691d8297b8bafb78f8ba9e397c98f6. A first focused run from the controller cwd correctly rejected three source-commit mismatches with 187 passes; the identical gate from candidate cwd passed 190 tests. No production change followed any harness issue.
  - Runtime ordering filtered the stale standalone fork, placed project libraries first, and appended the macOS dylib farm last. The fresh stack passed supported headless mode, simulation-evidence plugin loading with no ABI failure, three active controllers, Planning Scene READ_BACK, fresh /cup_pose, exact session/partition/domain, and reset_epoch 0. Five active stack/bridge PIDs correlated to the two owned tmux roots before preview.
  - Preview exited 0 with empty stderr and returned DISPATCH_PREVIEW/dispatch=false, supported plastic_cup/pick/{}, deepseek/deepseek-v4-flash with fallback false, exact request ID, and digest sha256:v1:a362fa42188acf5e277bc88ae17d1bb64ed41aa8db957101bc1075a27c837cfb. Its retained SHA-256 is bd46ebbf7f846991216fe8fe94a74be16a19c0326423874d77f01cb0fceca551.
  - Exactly one execute command was invoked with the exact instruction/digest pair. It exited 0 with empty stderr; the final Agent result is RUNTIME_COMPLETED/dispatch=true with RUNTIME_STARTED then RUNTIME_COMPLETED, exact request/runtime session correlation, DeepSeek provider/model/fallback false, and verified source/prefix/entry-point/module/Python/session/reset/evidence provenance. The persisted provenance artifact count is one.
  - The state machine reached DONE with transition_count 19 and no failure; reachability was SUCCEEDED for perceived_cup. Controller/MoveIt logs contain 22 arm-goal, 3 gripper-goal, and 22 MoveIt execution successes, with zero future-stamp rejections in the Agent stream. These are downstream simulation diagnostics only and do not establish real-hardware or V5-T005 acceptance.
  - Targeted SIGINT cleanup removed only the two owned stack/bridge roots; their launch children had already exited after the runtime lifecycle. Post-cleanup domain 210 returned to its two pre-existing infrastructure topics with zero nodes, and the elevated related-process inventory was empty. Candidate/task worktrees stayed clean, main plus its three pre-existing untracked files were unchanged, all evidence remained retained, and the persistent Ollama service/model/digest stayed live.
conclusion: VALID for final-candidate V5-T003 Mac DeepSeek qualification with exactly one execute and clean owned shutdown; no real-hardware or V5-T005 conclusion.
decision: KEEP
next_experiment: EXP-008
```

```yaml
experiment_id: EXP-008
status: VALID
transitions:
  - status: PLANNED
    recorded_in_commit: 493e9aed5082385485b29dd6be16a8d833b19d98
  - status: RUNNING
    recorded_at: 2026-08-30T03:02:32+08:00
    evidence: final-fix/mac-qwen/exp-008-mac-qwen-4ebdf45/{pre-mutation-readback.log,runtime-env-resolution.log,stack-provenance.log,full-readiness.log,full-readiness-assertion.log,owned-panes-start.log,process-isolation-readback.log}; final-fix/mac-candidate-4ebdf45/{installed-provenance-corrected-v2.log,focused-corrected-v2.xml}
  - status: VALID
    recorded_at: 2026-08-30T03:15:06+08:00
    evidence: final-fix/mac-qwen/exp-008-mac-qwen-4ebdf45/{preview.json,preview.stderr.log,pre-execute-readiness.log,execute-invocation.marker,execute.json,execute.stderr.log,execute-result.json,dynamic-execute-manifest.json,reachability-observed.json,downstream-layer-summary.log,qualified-artifact-hashes.log,cleanup-readback.log,preserved-state-readback.log,text-agent-provenance/*.json}
execute_invocation_count: 1
observed_reset_epoch: 0
created_at: 2026-08-30T02:10:40+08:00
prior_experiment: EXP-007
hypothesis: After both final-candidate DeepSeek qualifications are valid, candidate 4ebdf45 can use local qwen3.5:4b on Mac and execute one separately isolated headless MuJoCo simulation with provider-bound preview confirmation.
prediction: Loading ~/.env and then unsetting only DEEPSEEK_API_KEY selects ollama/qwen3.5:4b; think=false returns supported plastic_cup/pick/{} and the planned qwen digest within the normal deadline; one confirmed execute reaches the correlated state machine with clean shutdown.
single_variable: Provider/model changes from Mac DeepSeek to Mac loopback Ollama while final candidate, host, instruction, confirmation/provenance rules, and headless composition remain fixed; domain/partition/request/session/evidence are fresh.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-007 is VALID; otherwise this experiment remains PLANNED and no qwen live mutation occurs.
  - Local candidate/install provenance remains exactly 4ebdf451021f975f5f4903777bdcd5bb9a31b347.
  - ~/.env is loaded with export semantics and suppressed output, then only DEEPSEEK_API_KEY is unset in the experiment shell; only SET/UNSET is reported.
  - Ollama loopback /api/tags proves qwen3.5:4b and records its model digest without service mutation.
  - A separate fresh supported Mac headless stack/truth bridge passes readiness before status changes to RUNNING.
instruction: Pick the plastic cup.
provider: ollama
model: qwen3.5:4b
endpoint: http://127.0.0.1:11434/api/chat
preview_digest: sha256:v1:48f93b8acc2bc64be60a7be8c95264e21ae4a6f1f19c9c02eec0227359e7e89e
request_id: v5-t003-exp008-mac-qwen-4ebdf45
runtime_session_id: v5-t003-exp008-mac-qwen-4ebdf45
expected_reset_epoch: 0
provenance:
  source_commit: 4ebdf451021f975f5f4903777bdcd5bb9a31b347
  source_worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo/.worktrees/v5-t003-final-fix-mac-4ebdf45
  install_overlay: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-candidate-4ebdf45/install
  installed_prefix: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-candidate-4ebdf45/install/so101_demo_py
  runtime_executable: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-candidate-4ebdf45/install/so101_demo_py/lib/so101_demo_py/text_pick_agent
  ros_domain_id: 211
  gz_partition: v5-t003-exp008-mac-qwen-4ebdf45
  evidence_identity: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/final-fix/mac-qwen/exp-008-mac-qwen-4ebdf45
success_criteria:
  - Preview is DISPATCH_PREVIEW/dispatch=false with supported outcome, ollama/qwen3.5:4b, normalized empty-constraint command, exact request ID, and planned qwen digest.
  - Exactly one byte-identical confirmed execute returns verified provenance and reaches correlated state-machine dispatch/RUNTIME_COMPLETED in the separately owned Mac headless stack.
  - Downstream observations remain V5-T003 diagnostics; targeted cleanup leaves no experiment process and preserves the persistent Ollama service/model and unrelated user state.
failure_criteria:
  - Qualified provider/stack/provenance remain valid but the sole execute returns a product-level runtime or correlated downstream failure.
invalid_criteria:
  - EXP-007 not VALID; provider/model/digest/instruction/provenance/readiness mismatch; cloud key remains set; endpoint is non-loopback/non-/api/chat; headless unsupported; execute count other than one; contamination, missing correlation, broad cleanup, real hardware, or V5-T005 claim.
execution_rule: Preview retries, if any, are separately recorded fail-closed provider observations; after the sole execute command is invoked it is never rerun. If another production defect emerges, stop the bounded patch chain and report it rather than modifying production again.
observations:
  - Candidate/source/install provenance remained exact and clean at 4ebdf451021f975f5f4903777bdcd5bb9a31b347. The isolated build/install and corrected candidate-cwd focused gate from EXP-007 were reused without mutation; EXP-008 passed a new domain-211 supported-headless readiness check with three active controllers, Planning Scene READ_BACK, fresh simulation evidence and cup pose, exact session/partition, and reset_epoch 0.
  - ~/.env was loaded with export semantics and suppressed output, then only DEEPSEEK_API_KEY was unset and reported UNSET. The pre-existing loopback Ollama service remained live throughout; qwen3.5:4b tag digest was 2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd before preview and after cleanup.
  - Preview exited 0 with empty stderr and returned DISPATCH_PREVIEW/dispatch=false, supported plastic_cup/pick/{}, ollama/qwen3.5:4b with fallback true, exact request ID, and digest sha256:v1:48f93b8acc2bc64be60a7be8c95264e21ae4a6f1f19c9c02eec0227359e7e89e. Its retained SHA-256 is a886560009172a2f305cad28ad7c4930b0b4a49aa16c953af079b81acd086ba9.
  - Exactly one execute command was invoked with the exact instruction/digest pair. It exited 0 with empty stderr; the final Agent result is RUNTIME_COMPLETED/dispatch=true with RUNTIME_STARTED then RUNTIME_COMPLETED, exact v5-t003-exp008-mac-qwen-4ebdf45 request/runtime-session correlation, ollama/qwen3.5:4b/fallback true, and verified source/prefix/entry-point/module/Python/session/reset/evidence provenance. The persisted provenance artifact count is one.
  - The state machine reached DONE with transition_count 19 and no failure; reachability was SUCCEEDED for perceived_cup. Controller/MoveIt logs contain 22 arm-goal, 3 gripper-goal, and 22 MoveIt execution successes, with zero future-stamp rejections in the Agent stream. These are downstream simulation diagnostics only and do not establish real-hardware or V5-T005 acceptance.
  - Targeted tmux cleanup removed only the two owned roots. Three exact launch children had reparented to PID 1 while retaining owned process group 85575; read-only process correlation identified robot_state_publisher PID 85742, ros2_control_node PID 85743, and graceful_shutdown_move_group PID 85747, and targeted SIGTERM removed only those PIDs. Final domain 211 had zero nodes and only /parameter_events plus /rosout; related-process count was zero. Candidate/task worktrees remained clean, main plus its three pre-existing untracked files were unchanged, and the persistent Ollama service/model was not stopped or mutated.
conclusion: VALID for final-candidate V5-T003 Mac qwen3.5:4b qualification with exactly one execute and clean targeted shutdown; EXP-006, EXP-007, and EXP-008 are all VALID. No real-hardware or V5-T005 conclusion.
decision: KEEP
next_experiment: NONE
```

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-008
production_candidate: 4ebdf451021f975f5f4903777bdcd5bb9a31b347
current_hypothesis: No further V5-T003 experiment or production patch is required; the controller should perform the single final re-review before any authorized local merge.
working_tree_status: The final documentation/checkpoint commit is the commit containing this block and final-fix-report.md; resolve it live with git rev-parse HEAD. No merge or push was performed. A pre-report clean gate at 38a0773 passed build, installed provenance, 190 focused tests, 743 full tests, diff, status, and worktree secret scan; a post-commit final-HEAD rerun is retained outside Git under final-fix/final-gates.
owned_processes: NONE; EXP-006/007/008 stacks, bridges, launch children, and provider tunnels are absent. The Mac Ollama service is persistent user state and remains live.
preserved_processes: ai-station codex and codex-cua; persistent Mac Ollama; unrelated desktop/system processes.
confirmed_conclusions:
  - The final-review RED suite failed as expected with 37 failures/4 passes plus four CLI-provider failures; initial GREEN passed 45 final-review, 188 focused, and 741 full tests.
  - EXP-005 was a valid fail-closed qwen provider-boundary result at candidate 785a95e with execute count zero. Its one-variable diagnostic isolated think=false and prompt constraint invention, leading to two new RED tests and final candidate 4ebdf45; GREEN passed 31 adapter, 190 focused, and 743 full tests.
  - EXP-006, EXP-007, and EXP-008 are VALID at 4ebdf45. Each invoked execute exactly once, reached RUNTIME_COMPLETED and downstream DONE/19 with exact request/session correlation, retained verified provenance, and ended with zero owned nodes/processes.
  - The 23-file ai-station evidence copy is byte-identical by remote/local SHA-256. Secret-safe scans found zero actual-key or strong generic credential matches across 23 selected remote/copied files, 2395 full remote-root files, 744 full local-root files, 563 new-evidence files, and 3342 worktree files at their respective scan times.
  - The teaching guide is docs/so101-text-pick-agent-source-guide.md and is linked from the package README.
  - No evidence was deleted, no real hardware was touched, and no V5-T005 conclusion is made.
disproven_routes:
  - Reusing old candidate live evidence for corrected shared provider/prompt behavior.
  - Switching Mac to visible mode without gui-capture authorization; supported headless worked, so no switch occurred.
  - Treating scan tool source identifiers as credential values; v1's sole generic match was its own secret_text identifier, while exact-key matches were zero and the token-shaped v2 scan passed both roots.
open_risks:
  - EXP-008 tmux teardown left three exact reparented launch children that required targeted SIGTERM after PGID/PID correlation; final graph/process read-back passed.
  - macOS colcon prints a post-success LaunchServices kLSNoExecutableErr message despite exit zero; install/provenance/tests pass.
  - Downstream DONE/MoveIt/controller/cup evidence remains diagnostic, not physical acceptance.
evidence_disposition:
  retained: Both complete registered roots; all RED/GREEN/JUnit, old/final experiments, failed verifier/environment observations, remote copied/hash/scan artifacts, and final gates.
  archived: NONE
  deletion_candidates: Superseded candidate-785a95e build/install, failed EXP-004 attempt, EXP-005 provider diagnostics, superseded bundle/intermediate build trees, failed verifier wrappers/logs, scanner v1, wrong-cwd full-gate evidence, and the previously listed /tmp/so101-debug-task1/ stray root. Listed only; nothing deleted.
next_command: Controller runs one scoped final re-review; only if clean may the controller perform the separately authorized local main merge. Do not merge or push from this worktree.
```
