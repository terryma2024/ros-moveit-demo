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
inferred:
  - V5-T003 ai-station qualification is complete at the fail-closed provider, installed CLI, exactly-once state-machine dispatch, correlation, duplicate-request, and owned-cleanup boundaries.
  - The retained runtime DONE/19 data is useful downstream diagnostic evidence but is intentionally not promoted to a V5-T005 physical-success conclusion.
conclusion: VALID for V5-T003. The installed Text Agent dispatched the qualified MuJoCo state machine exactly once with request/runtime correlation and clean owned shutdown; real hardware and V5-T005 physical acceptance remain outside scope.
evidence:
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/dynamic-execute-manifest.json
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/reachability-observed.json
  - /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/
decision: KEEP
next_experiment: NONE
```

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-002
documentation_snapshot_parent: 32dd34a39b540f20a682d3aa088e27c50b5a104f
current_hypothesis: No further V5-T003 experiment is required; any physical-success claim belongs to separately planned and authorized V5-T005 acceptance.
working_tree_status: "Final ledger/result commit is 5357762448a06d2e43c0210fc1ca00cb08e06501 and pre-fix verification/report commit is 5f8994c78355c0a49ad55bde0d0e288b2bad196a. Audit documentation fix is complete under the live/final-doc rule: resolve its commit with git rev-parse HEAD at handoff rather than embedding a self-reference. ai-station main remains e6ab8c1 with only its preserved untracked RGB-D ledger; isolated candidate remains 02e086be with gitlink 71bc934. No source implementation was changed."
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
disproven_routes:
  - Treating visible DISPLAY=:1 as qualified merely because xdpyinfo succeeds; the runtime failed GLFW window creation.
  - Treating a task-station-only wrapper as the only persistent stack path; the supported generic headless launch composes the same controller/MoveIt/scene stack.
  - Treating runtime DONE, transition count, or manifest physical fields as V5-T005 physical acceptance within V5-T003.
open_risks:
  - Live qwen3.5:4b latency was 120139 ms for execute and earlier previews demonstrated constraint drift and timeout; fail-closed behavior is qualified, not model service-level reliability.
  - ai-station /data/work/ws_moveit/install/setup.zsh remains stale because unrelated indexed packages are absent; this task sourced exact package scripts and explicit prefix ordering instead of changing unrelated overlay state.
  - ai-station direct full package pytest has two test_mujoco_rgbd_batch_cli mock argv failures; colcon cwd adds eleven workspace-relative path failures. Current evidence does not establish their historical attribution. Fresh pre-fix evidence verification at 5f8994c78355c0a49ad55bde0d0e288b2bad196a passed 139 focused and 692 full-package tests; audit-fix final-HEAD results are retained in task8/audit-fix-round1/local-final under the live/final-doc rule.
evidence_disposition:
  retained: /tmp/so101-debug-v5-t003-text-agent-20260829-164105/ (Task 8 build, provider, readiness, live execute, duplicate, runtime manifest, cleanup, and audit-fix-round1 copied/hash-contract artifacts remain beneath this sole registered root)
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
