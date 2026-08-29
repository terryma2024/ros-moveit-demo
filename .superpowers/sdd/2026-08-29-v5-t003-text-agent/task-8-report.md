# Task 8 report — ai-station Text Agent qualification

Status: **DONE_WITH_CONCERNS**

## Scope and commits

This task qualified V5-T003 through preview, exactly one installed live CLI execute invocation,
request/runtime correlation, duplicate-request rejection, and owned cleanup. It did not access real
hardware, push, merge, publish, delete evidence, or claim V5-T005 physical success.

- Ledger-only planning commit: `32dd34a39b540f20a682d3aa088e27c50b5a104f`.
- Executable candidate: `02e086be0171f08bb5e936901c79bfa70cda665f`.
- Final ledger/result commit: `5357762448a06d2e43c0210fc1ca00cb08e06501`.
- Pre-fix verification-report commit: `5f8994c78355c0a49ad55bde0d0e288b2bad196a`.
- Audit documentation-fix commit: use the live `git rev-parse HEAD` value at handoff. The report
  deliberately does not self-reference the commit that contains itself.

## Source, install, and runtime provenance

- ai-station main stayed at `e6ab8c1b7398bf757b2ab2f2ac9a503a93f5d2a4`; its only dirty item remained
  `docs/experiments/ai-station-linux-headless-rgbd-four-point-upgrade-experiment-ledger.md`.
- Candidate was transferred as a complete Git bundle into detached worktree
  `/data/work/ws_moveit/.worktrees/v5-t003-text-agent-task8`. Local and remote bundle SHA-256 were
  `526d6d2f2e484f5f6db5a57c04d5875c4173b7105fc52bec52dd528691f2e3ee`.
- Candidate nested gitlink was
  `71bc9346cf93d6227a6678fcacf63f3e18acfcba`. Candidate and remote main both descend from the
  `graceful_shutdown_move_group` change at
  `91f7ebbc776b0af7dd3c57bb4942a2b06d80c4de`.
- `so101_demo_py` was built from only `src/so101_demo_py` into
  `/data/work/ws_moveit/install/so101_demo_py`. Installed `text_pick_agent` SHA-256 is
  `07b82ce9518ee33b58c81f377480c1dc7827ecc7dce331a50098ed08065b8dd3`.
- Installed dependency drift required a no-code candidate-closure repair. Exact candidate
  `mujoco_ros2_control_msgs`, `mujoco_ros2_control_plugins`, and `so101_mujoco_support` were built
  into `/data/work/ws_moveit/install`. Installed
  `lib/so101_mujoco_support/graceful_shutdown_move_group` SHA-256 is
  `6afcbd6c9f417d06934cdf54121f3c0ee2068e4d8a9e96a08ce70319eb35f042`.
- Runtime `ros2_control_node` remained the verified external executable at
  `/data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install/lib/mujoco_ros2_control/ros2_control_node`,
  SHA-256 `9fd047eaae7ed2eff3f49aeb42880f88019ccf84787ecd5183ee5de78d73506e`.
- The corrected installed-bundle preflight ran from the isolated source root with
  `SO101_SOURCE_COMMIT=02e086be0171f08bb5e936901c79bfa70cda665f` and produced bundle SHA-256
  `12623bb80044d8e6f3a415f01eabf6e345849258d4263fdb2cf65d39a3ab034e`.

## Commands and exits

The complete raw logs are retained below the sole evidence root
`/tmp/so101-debug-v5-t003-text-agent-20260829-164105/`. Salient commands were:

| Command | Exit/result |
| --- | --- |
| Remote checkout/tmux/process/ROS/provider preflight | 0; no conflicting stack, domain, or partition |
| Bundle create, SHA read-back, fetch, detached worktree creation | 0 |
| Scoped `colcon build --base-paths src/so101_demo_py --packages-select so101_demo_py --symlink-install --install-base /data/work/ws_moveit/install` | 0 |
| Injected seven-case preview harness | 0; all failures `dispatch=false`, executor calls 0 |
| Candidate closure build for messages/plugins, then candidate support build | 0, 0 |
| `tmux new-session -d -s v5-t003-task8-stack -n stack "zsh -f .../task8/start-stack-v2.zsh > .../task8/stack-v2.log 2>&1"` | tmux 0; launched runtime 1 because selected `fusion-final` support libexec lacked `graceful_shutdown_move_group` |
| `tmux new-session -d -s v5-t003-task8-diagnose -n debug "zsh -f .../task8/reproduce-stack-debug.zsh > .../task8/stack-debug.log 2>&1"` | tmux 0; launched debug runtime 1 with the same selected-overlay failure; targeted cleanup 0 |
| Visible task-station launch | runtime exit 1: `ERROR: could not create window` before readiness |
| `tmux new-session -d -s v5-t003-text-agent-task8-headless ".../task8/start-stack-headless.zsh > .../task8/stack-headless.log 2>&1"` | tmux 0; launched runtime 1 before simulator because `git rev-parse HEAD` ran outside a checkout |
| Corrected installed-bundle one-shot preflight | 0 |
| Corrected `so101_mujoco.launch.py` headless readiness start | ready; later targeted SIGINT cleanup 0 |
| Readiness-gated live qwen preview with exact no-constraint instruction | 0, `DISPATCH_PREVIEW` |
| Installed live Text Agent execute command | invoked exactly once; exit 0 |
| Resident duplicate-request harness | 0; second request rejected, executor calls 1 |
| Targeted tmux cleanup | bridge SIGINT 0; stack SIGINT 0; owned session absent afterward (tmux lookup 1) |
| Final tmux/process/ROS/provider read-back | 0 / 1 / 0 / 7 respectively; expected empty process query and closed provider port |

The exactly-once live command was:

```text
ros2 run so101_demo_py text_pick_agent --instruction 'Pick the plastic cup. Apply no constraints. Leave constraints empty.' --request-id v5-t003-live-001 --mode execute --execute --backend mujoco --ollama-model qwen3.5:4b --ollama-endpoint http://127.0.0.1:21434/api/chat --ollama-timeout-s 300.0 --session-id v5-t003-live-001 --expected-reset-epoch 0 --evidence-root /tmp/so101-debug-v5-t003-text-agent-20260829-164105 --source-commit 02e086be0171f08bb5e936901c79bfa70cda665f --installed-prefix /data/work/ws_moveit/install/so101_demo_py
```

`task8/live-execute-count.log` records `execute_invocation_count=1`. The command was not rerun.

## Provider and preview result

- ai-station had no Ollama install or local model. No software was installed there.
- A task-owned SSH reverse tunnel exposed the Mac service only on remote localhost port 21434.
  Remote `/api/tags` returned `qwen3.5:4b` digest
  `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`.
- Earlier live previews failed closed: one qwen response added unconsumed constraints and one timed
  out. The readiness-gated exact instruction returned `plastic_cup/pick/{}` with
  `DISPATCH_PREVIEW`, `dispatch=false`, provider `ollama`, model `qwen3.5:4b`.
- The seven injected cases prove valid preview plus empty input, semantically invalid primary
  candidate, both-provider failure, unconsumed constraint, partial authorization, and wrong
  backend. Every rejection remained non-dispatching. These are labeled injected adapter evidence.

## Readiness, live correlation, and downstream observation

The visible-only task-station wrapper could not create a GLFW window under the live DISPLAY. Source
and retained current-main ai-station evidence showed that `so101_mujoco.launch.py headless:=true` is
the supported persistent equivalent for the same MuJoCo, ros2_control, MoveIt, and Planning Scene
actions. The corrected actual headless start used:

- `ROS_DOMAIN_ID=198`;
- `GZ_PARTITION=v5-t003-text-agent-task8-ai-20260829-164105`;
- owned tmux session `v5-t003-text-agent-task8-headless-v2`;
- all three controllers active;
- Planning Scene `READ_BACK` success;
- fresh simulation evidence for `v5-t003-live-001`, reset epoch `0`;
- fresh world-frame `/cup_pose` from the test-only MuJoCo truth bridge.

The single live Agent result was `RUNTIME_COMPLETED`, `dispatch=true`, capability
`dynamic_cup_pick_place`, with `request_id=v5-t003-live-001` and
`runtime_session_id=v5-t003-live-001`; its state trace is `RUNTIME_STARTED` then
`RUNTIME_COMPLETED`. Runtime output reported `DONE`, 19 transitions, and exit 0. The correlated
manifest SHA-256 is `4d57be35702f7a904c5d9e599fc98f6cc7307cc39cdb61e11d61c5cbf48db936`;
reachability evidence SHA-256 is
`dba9b980af0d437528fcd8e44ec3c1168905535fca701da312fb81c7cebc207a`.

Before `EXP-002` was changed to `RUNNING`, the durable ownership/readiness snapshot recorded owned
stack pane/launch PID `3062266`, persistent children `3062375` (robot state publisher), `3062376`
(`ros2_control_node`), and `3062380` (`graceful_shutdown_move_group`), plus cup-pose bridge pane/PID
`3064379`. One-shot child PIDs `3062377`, `3062378`, `3062379`, and `3062385` had started and exited
while activating the three controllers and completing Planning Scene `READ_BACK`. The preserved
`codex` and `codex-cua` panes were PIDs `75520` and `365114` and were never task-owned.

The live command did not proceed directly from dispatch to `DONE`. The complete
`task8/live-execute.log` records 20 rejected `/cup_pose` samples as
`CUP_POSE_INVALID/CUP_POSE_STALE: source stamp is too far in the future`; the retained
`task8/live-post-dispatch-readback.log` tail displays the final six of those diagnostics before
`DONE/19`. `RosCupPoseSource.get_one()` remained inside one absolute-deadline `acquire_one()` call:
each invalid queued sample was reported and skipped, subscription/spinning continued, and the first
later sample within the clock-skew contract was accepted. There was no Text Agent re-dispatch, no
second runtime process, and no restart; this was in-call input acquisition recovery before the one
state-machine execution completed. These transient failures and the later `DONE/19` remain
downstream observations only, not V5-T005 evidence.

MoveIt plans/controller actions, Planning Scene data, MuJoCo state, `DONE`, and manifest physical
fields are downstream observations only. They are not a V5-T005 physical-success claim.

The resident duplicate harness submitted `v5-t003-live-001` twice to one `TextAgent`. The first
injected execution returned `RUNTIME_COMPLETED`; the second returned
`DISPATCH_REJECTED/DUPLICATE_REQUEST_ID`; `executor_calls=1`. It did not invoke a second live
runtime.

## Cleanup, evidence, and preserved user state

Cleanup sent SIGINT only to the two windows in the owned task session. The simulator deactivated
all controllers and hardware, MoveIt logged `GRACEFUL_SHUTDOWN_MOVE_GROUP_OK`, and the owned session
exited. Both task-owned reverse-tunnel masters were closed by their exact control sockets.

Final read-back showed:

- only `codex` and `codex-cua` tmux sessions remain;
- no related MuJoCo, MoveIt, Text Agent, bridge, robot-state-publisher, or ros2_control process;
- no node in ROS domain 198;
- remote localhost port 21434 closed;
- ai-station main and its untracked RGB-D ledger unchanged;
- detached candidate source still at exact commit/gitlink.

Retained: the complete registered evidence root, including Task 8 build, failed diagnostic,
provider, readiness, live execute, duplicate, runtime-manifest, and cleanup artifacts. Archived:
`NONE`. Deletion candidates: failed build/staging directories and failed visible/pre-provenance
wrappers/logs listed in CP-003. Nothing was deleted.

## Tests and concerns

- ai-station focused Text Agent suite: 139 passed, exit 0.
- ai-station direct package pytest: 690 passed, 2 failed, exit 1. Both observed failures are
  `test_mujoco_rgbd_batch_cli` mock argv slice mismatches; their historical attribution is
  unresolved by current evidence.
- ai-station colcon package test: 692 collected, 13 failed, exit 1; eleven additional failures are
  workspace-root-relative file lookups under the colcon package working directory. Their historical
  attribution is likewise unresolved.
- Fresh pre-fix evidence verification at `5f8994c78355c0a49ad55bde0d0e288b2bad196a`:
  focused **139 passed in 0.35s** and full package **692 passed in 12.91s**, both exit 0 with retained
  JUnit.

Concerns: live qwen latency was 120139 ms and prior previews showed constraint drift/timeout;
ai-station's aggregate `install/setup.zsh` remains stale because unrelated indexed packages are
missing, so exact package scripts and explicit prefix ordering were used; remote package-test
runner gaps remain. None invalidated the focused Text Agent gate, exact live dispatch correlation,
or cleanup proof.

## Audit fix round 1 — raw evidence and command closure

This amendment performed no provider, stack, Text Agent, or runtime action. The live execute count
remained one. Read-only ai-station inspection found all four reviewer-blocking artifacts and the
supporting live/ownership/failure logs. A secret-safe byte scan covered 14 candidate files and
reported only `candidate_file_count=14`, `secret_match_path_count=0`; no secret value was printed or
copied.

The reproducible remote scan command was
`ssh ai-station 'python3 -' < /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/remote_secret_scan.py`,
exit 0. Remote `sha256sum` over the same explicit 14 paths exited 0. The files were then transferred
by four explicit `scp` batches (key Agent JSON/logs, root runtime JSONs, live/ownership logs, and
failed-start wrappers/logs); all four batches exited 0. Full exact path lists and exits are recorded
in the EXP-002 command list.

The exact minimum artifacts and supporting audit logs were copied read-only into the clearly
labeled local artifact subdirectory
`/tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/copied-remote/`,
below the sole registered evidence root. The remote SHA-256 manifest is
`task8/audit-fix-round1/remote.sha256`; a deterministic local contract checker and its output are
`task8/audit-fix-round1/evidence_contract_check.py` and `task8/audit-fix-round1/contract-check.json`.
Remote/local equality was true for all 14 files with zero missing paths, zero hash mismatches, and
zero secret-pattern paths. The reviewer-blocking artifacts matched as follows:

| Artifact | Remote/local SHA-256 |
| --- | --- |
| `task8/live-execute-count.log` | `b0378526ff82e793ddb23b79c8706c636f69bf8720d975b847f7aad1c8644d6f` |
| `task8/preview-live-ready.json` | `b1852e237ff35eaa7558d19bfd48c3fec64a74a3f39137ae4f68b2b21d3fbb8a` |
| `task8/duplicate-request-proof.json` | `3277e85804c03f67aa538ae84f6a7b0bc119f63c2ac3923d72e8b588bfe4c9d7` |
| `dynamic-execute-manifest.json` | `4d57be35702f7a904c5d9e599fc98f6cc7307cc39cdb61e11d61c5cbf48db936` |
| `reachability-observed.json` | `dba9b980af0d437528fcd8e44ec3c1168905535fca701da312fb81c7cebc207a` |

The contract command was:

```text
python3 /tmp/so101-debug-v5-t003-text-agent-20260829-164105/task8/audit-fix-round1/evidence_contract_check.py
```

It exited 0 and proved: 14/14 files present with remote/local hash equality; one execute invocation;
preview `DISPATCH_PREVIEW/dispatch=false`; resident duplicate `executor_calls=1` and second result
`DISPATCH_REJECTED/DUPLICATE_REQUEST_ID`; runtime `DONE/19` and reachability `SUCCEEDED`; 20 full-log
future-stamp diagnostics; and zero secret-pattern paths.

The exact final cleanup/read-back commands and exits were:

| Command | Exit | Evidence |
| --- | ---: | --- |
| `tmux send-keys -t v5-t003-text-agent-task8-headless-v2:cup-pose C-c` | 0 | `task8/owned-cleanup.log` |
| `tmux send-keys -t v5-t003-text-agent-task8-headless-v2:zsh C-c` | 0 | `task8/owned-cleanup.log` |
| `tmux has-session -t v5-t003-text-agent-task8-headless-v2` | 1 | `task8/owned-cleanup.log`; expected absent |
| `tmux list-sessions 2>/dev/null` | 0 | `task8/final-cleanup-readback-v2.log`; only `codex`, `codex-cua` |
| `ps -eo pid,ppid,args \| grep -E '[m]ove_group\|[d]ynamic_cup_pick_place\|[t]ext_pick_agent\|[r]os2_control_node\|[m]ujoco_cup_pose_bridge\|[r]obot_state_publisher\|[s]o101_mujoco'` | 1 | `task8/final-cleanup-readback-v2.log`; expected no match |
| `source /opt/ros/jazzy/setup.bash; export ROS_DOMAIN_ID=198; ros2 node list --no-daemon` | 0 | `task8/final-cleanup-readback-v2.log`; empty graph |
| `curl --silent --show-error --max-time 3 http://127.0.0.1:21434/api/tags` | 7 | `task8/final-cleanup-readback-v2.log`; expected closed task-owned tunnel |

The two dependency-overlay-invalid starts and the invocation-provenance-invalid first headless start
are now preserved locally with exact wrapper commands, logs, and remote/local hashes in the audit
artifact directory. All three exited 1 before `EXP-002` became `RUNNING`; none invoked the Text Agent
execute CLI. No evidence was deleted.

Covering final-documentation-HEAD verification uses the live/final-doc rule: the pre-fix validation
commit is fixed as `5f8994c78355c0a49ad55bde0d0e288b2bad196a`, while the documentation-fix commit is the live
`git rev-parse HEAD` returned at handoff rather than a self-reference embedded here. At that final
HEAD, the deterministic evidence-contract command exits 0; `git diff --check` exits 0; the focused
six-file Text Agent suite reports **139 passed**, exit 0; and the full local package suite reports
**692 passed**, exit 0. Fresh outputs and JUnit are retained under
`task8/audit-fix-round1/local-final/`.

The focused command used the six files named in EXP-002 and reported **139 passed in 0.38s**, exit
0, on the first documentation-fix HEAD. The first full-suite command omitted task-owned ROS logging
paths and reported **628 passed, 64 failed**, exit 1; every shown failure was a sandbox
`PermissionError` while ROS launch attempted to create `/Users/matianyi/.ros/log/...`, not a product
assertion. Its exact command/output remains retained in `local-final/full-package.log` and
`full-package.xml`. The smallest environment-only correction set
`ROS_HOME=.../local-final/ros-home` and `ROS_LOG_DIR=.../local-final/ros-home/log` beneath the sole
evidence root, then reran the unchanged full suite: **692 passed in 12.88s**, exit 0, retained as
`full-package-corrected.log` and `full-package-corrected.xml`. The ledger records the exact three
test commands and exits; the focused and corrected full commands are rerun once more after the
documentation-only amend so their final retained logs begin with the live final HEAD.
