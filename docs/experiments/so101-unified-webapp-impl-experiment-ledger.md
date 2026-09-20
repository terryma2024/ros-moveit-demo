# Unified webapp implementation ledger

```yaml
task_id: so101-unified-webapp-impl-20260920
goal: Execute docs/superpowers/plans/2026-09-18-so101-unified-webapp-shadcn-implementation.md (Tasks 0-11 and 12A) in one isolated worktree
success_contract: Every plan task that this host can execute reaches RED -> GREEN with recorded evidence, exact scoped commits, and no fabricated runtime authority
executor: DeepSeek Harness TUI (dst) inline, per plan model/executor rules
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: 5b8d1231e97e10f650ac1d626e8dff801a7d21ea
current_commit: ad84703433a1718e4c6c35174490aa3f5d84cbd1
spec: docs/superpowers/specs/2026-09-18-so101-unified-webapp-shadcn-design.md
spec_sha256: 4e11f3a385e8d078523ee3c3b3b11d2ec372215188cfbdabdea824c35dd54fa1
plan: docs/superpowers/plans/2026-09-18-so101-unified-webapp-shadcn-implementation.md
plan_sha256: 71648ebbce07388af016e125c6e168b80fd3752305d62e71b412f64fdb6ae039
evidence_root: /tmp/so101-debug-so101-unified-webapp-impl-20260920
gate_policy: /tmp/so101-debug-so101-unified-webapp-impl-20260920/operator/gate-policy.json
gate_policy_sha256: 204c3f5e2670c643734c06efba83b31bb89d715aa7a88fbe3d7a85014ef4e5e1
execution_host: Terry-Mac-mini.local (macOS 26.6.2, arm64)
test_python: /Users/matianyi/ros2_jazzy/.venv/bin/python (Python 3.11.15)
test_python_declared: Python 3.12 (NOT AVAILABLE on this host; see CP-01 deviation D-2)
bun: /opt/homebrew/bin/bun 1.3.14
node: /Users/matianyi/.nvm/versions/node/v25.9.0/bin/node v25.9.0 (outside plan range >=24.18.1 <25; see D-3)
ros_workspace: /Users/matianyi/ros2_jazzy (macOS source build; no /opt/ros/jazzy on this host)
confirmed_conclusions:
  - Plan Tasks 0-11 and 12A are authorized by the goal; Stage B measurement and Stage C live replacement remain separately authorized
  - Only this worktree is modified; no existing service, simulator or ROS runtime was started or stopped
  - Spec hash matches the plan-declared frozen value
disproven_routes: []
open_hypotheses:
  - Unified arbiter/instance/IPC design can be implemented and unit-verified without ROS on macOS
latest_checkpoint: CP-04
next_experiment: Task 3 safety lane and goal registry
```

## CP-01: Registration, host probe and deviations

Worktree `.worktrees/so101-unified-webapp` on branch `codex/so101-unified-webapp` from `main`
5b8d1231. Single evidence root `/tmp/so101-debug-so101-unified-webapp-impl-20260920` registered in
this ledger; no `/data` path applies on this host. Files under `operator/` hold the frozen gate
policy object that Task 0 verifies by SHA256 and hostname.

Preserved processes: tmux sessions `dst`, `dst-so101-macos-mps-w2` (attached), `so101-teleop-w2-e2e`
were observed before work started and were not touched. No ROS graph or service was started,
stopped or inspected for ownership during this checkpoint.

Probed facts: `bun` 1.3.14 at `/opt/homebrew/bin/bun`; `node` v25.9.0; `dst` present at
`/Users/matianyi/.nvm/versions/node/v25.9.0/bin/dst`; ROS 2 Jazzy is a macOS source build rooted at
`/Users/matianyi/ros2_jazzy` with install overlays `extra_ws`, `so101_isolated_ws` and a Python 3.11
venv at `~/ros2_jazzy/.venv`; there is no `/opt/ros/jazzy` and no ai-station shell in this session.

### Deviations from the plan (reported, not silently substituted)

- **D-1 host**: the plan is written for ai-station Linux with a `/data/work/so101-evidence` root and
  NVMe scratch rules. This session runs on macOS, where `AGENTS.md` explicitly exempts the `/data`
  rule. Registered root is therefore the `/tmp` root above; every gate still proves the exact
  interpreter and `tempfile.gettempdir()` inside a per-invocation scratch directory.
- **D-2 test Python**: Task 0 requires proving Python 3.12 before use. No 3.12 interpreter with
  Pydantic 2, FastAPI, pytest, uvicorn and rclpy exists on this host: Homebrew has 3.11 and 3.14,
  `uv` has a bare managed 3.12.13 without those packages, and the plan forbids installing
  dependencies or quietly swapping interpreters. The repository's own macOS test contract
  (`.agents/skills/so101-dev/references/test-and-acceptance.md`) names
  `/Users/matianyi/ros2_jazzy/.venv/bin/python3` as the actual test interpreter, so that verified
  3.11.15 venv (Pydantic 2.13.4, FastAPI 0.115.14, pytest 8.4.2, uvicorn 0.34.3) is registered as
  `TEST_PYTHON`. This is a documented deviation from the plan's version literal, not a silent swap;
  ai-station execution must re-prove 3.12 before any Linux gate is trusted.
- **D-3 Node**: the plan requires Node `>=24.18.1 <25`. This host has only v25.9.0. All frontend
  install/build/test work goes through Bun 1.3.14 per repository rules, so no Node-versioned
  production artifact is produced here; the mismatch is recorded rather than resolved by installing
  a second Node runtime.
- **D-4 worktree creation**: the plan assigns worktree creation to the operator before dispatch. The
  goal for this session explicitly asks for the worktree and branch, so it was created here and
  recorded with branch, base commit and remotes above.

## CP-02: Task 0 - registered execution gate

Delivered `src/so101_teleop/test/e2e/record_gate.py` and `src/so101_teleop/test/test_unified_gate.py`,
registered as `test_unified_gate` in `src/so101_teleop/CMakeLists.txt`.

RED: 2 failed / 17 errors because the helper did not exist (`ModuleNotFoundError`-class collection
errors), exit 1, scratch `/private/tmp/.../scratch-9DGvEZoP/tmp`. GREEN: 19 passed, exit 0.
`pygate` was then validated end-to-end: gate record `gates/b8a2e0c40aa4469a971ac838d05b438f/result.json`
shows `test_python=/Users/matianyi/ros2_jazzy/.venv/bin/python`, `tempfile_dir` inside that run's own
`tmp/`, `exit_code=0`, `elapsed_seconds=1.37`, and the registered policy digest.

The gate refuses an unregistered root, a non-NVMe root when the operator object requires NVMe, host
mismatch, policy hash drift, missing policy fields, missing policy reference, and any interpreter or
TEMP mismatch - and in the mismatch cases it proves the command under test never started.
Commit `d66f9ae4`.

## CP-03: Task 1 - persistent global mutation arbiter

Delivered `unified/{__init__,contracts,intent_store,arbiter}.py` and
`test/teleop/test_unified_arbiter.py`, registered as `test_unified_arbiter`.

RED: `ModuleNotFoundError: No module named 'so101_teleop.unified'`, exit 2. GREEN: 15 passed, exit 0.
Covered: durable reservation across restart with unconverged-intent blocking, command idempotency by
canonical fingerprint with NaN refusal, two-thread admission race admitting exactly one domain, the
second service instance refused by `flock` both in-process and from a second process, cancel between
prepare and ACK still registering the late goal, terminal without cleanup proof staying blocked, and
an existing legacy journal's bytes unchanged.

Deviation: `IntentStore.settle` commits a refusal fence before the arbiter raises, so a blocked parent
can never be rolled back into `active` by the refusal itself. Commit `958bb86c`.

## CP-04: Task 2 - instance proof and lease binding fences

Delivered `unified/instances.py`, instance/authority types in `unified/contracts.py`, and
`test/teleop/test_unified_instances.py`, registered as `test_unified_instances`.

RED: collection error with `instances.py` moved aside, exit 2. GREEN: 12 passed, exit 0. Covered:
copied valid lease cannot control a second document, renew never moves the execution generation,
handoff bumps it once and only when the arbiter is idle, reconnect bumps the channel revision and
rejects the old revision, wrong origin / swapped domain proof / dead channel refused, proofs never
persisted (raw database bytes searched), abandoned-controller recovery requires proof that nothing is
owned, and the coordinator's cut points (acquire failure after the real domain lease committed leaves
a durable fence, restart stays blocked, guard waits out a renew fence and blocks at the parent
deadline).

Deviation from the plan's staging list: `unified/intent_store.py` is included in this commit because
the plan's own Task 2 text requires the execution generation and lease fences to live in the store's
independent tables. The plan's list omits it.
