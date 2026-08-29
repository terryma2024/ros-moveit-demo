# Task 8 report — ai-station Text Agent qualification

Status: **DONE_WITH_CONCERNS**

## Scope and commits

This task qualified V5-T003 through preview, exactly one installed live CLI execute invocation,
request/runtime correlation, duplicate-request rejection, and owned cleanup. It did not access real
hardware, push, merge, publish, delete evidence, or claim V5-T005 physical success.

- Ledger-only planning commit: `32dd34a39b540f20a682d3aa088e27c50b5a104f`.
- Executable candidate: `02e086be0171f08bb5e936901c79bfa70cda665f`.
- Final ledger/result commit: `PENDING_FINAL_COMMIT`.
- Final verification-report commit: resolve with `git rev-parse HEAD` at handoff.

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
| Visible task-station launch | runtime exit 1: `ERROR: could not create window` before readiness |
| First headless invocation | launch exit 1 before simulator: `git rev-parse HEAD` ran outside a checkout |
| Corrected installed-bundle one-shot preflight | 0 |
| Corrected `so101_mujoco.launch.py` headless readiness start | ready; later targeted SIGINT cleanup 0 |
| Readiness-gated live qwen preview with exact no-constraint instruction | 0, `DISPATCH_PREVIEW` |
| Installed live Text Agent execute command | invoked exactly once; exit 0 |
| Resident duplicate-request harness | 0; second request rejected, executor calls 1 |
| Targeted tmux/tunnel cleanup and host read-back | 0 |

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
- ai-station direct package pytest: 690 passed, 2 failed, exit 1. Both failures are the existing
  `test_mujoco_rgbd_batch_cli` mock argv slice mismatch.
- ai-station colcon package test: 692 collected, 13 failed, exit 1; eleven additional failures are
  workspace-root-relative file lookups under the colcon package working directory.
- Fresh final candidate-local focused and full package results: `PENDING_FINAL_TESTS`.

Concerns: live qwen latency was 120139 ms and prior previews showed constraint drift/timeout;
ai-station's aggregate `install/setup.zsh` remains stale because unrelated indexed packages are
missing, so exact package scripts and explicit prefix ordering were used; remote package-test
runner gaps remain. None invalidated the focused Text Agent gate, exact live dispatch correlation,
or cleanup proof.
