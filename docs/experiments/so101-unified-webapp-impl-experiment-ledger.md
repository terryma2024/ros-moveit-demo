# Unified webapp implementation ledger

```yaml
task_id: so101-unified-webapp-impl-20260920
goal: Execute docs/superpowers/plans/2026-09-18-so101-unified-webapp-shadcn-implementation.md (Tasks 0-11 and 12A) in one isolated worktree
success_contract: Every plan task that this host can execute reaches RED -> GREEN with recorded evidence, exact scoped commits, and no fabricated runtime authority
executor: DeepSeek Harness TUI (dst) inline, per plan model/executor rules
worktree: /Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp
branch: codex/so101-unified-webapp
base_commit: 5b8d1231e97e10f650ac1d626e8dff801a7d21ea
current_commit: da05a69d51b63f88945f599c12a0e5a3376d9123
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
latest_checkpoint: CP-33
next_experiment: Task 11 configure/build unless the Task 8 registry path is unblocked first; Task 9's page-effect migration and browser viewport checks remain
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

## CP-05: Task 3 - isolated safety lane

Delivered `unified/goals.py`, `unified/safety.py`, cancellation receipt types in
`unified/contracts.py` and `test/teleop/test_unified_safety.py` (registered `test_unified_safety`).

RED: 10 failed / 2 passed, exit 1 (the lane could not unpack its own shutdown sentinel and the
late-ACK fixture never prepared a child; both were fixture/implementation defects fixed forward).
GREEN: 12 passed, exit 0. Covered: delivery then stop-evidence wait, durable `cancel_requested`
before any goal is touched with later children refused, arm and gripper cancelled independently by
real UUID, duplicate cancels merged into one delivery, late ACK cancelled safely without discarding
the goal record, foreign authority refused before delivery, browser authority without an instance
refused, delivery timeout and accepted-without-stop-proof both blocking, safe queue full refusing
instead of queueing behind normal mutations, revoke without a pending authorizer refused, and
revoke linearization without a goal handle. Commit `ccb00db4`.

## CP-06: Task 4 - closed IPC and non-web child

Delivered `unified/{ipc,child_runtime,bridge,ros_child}.py`,
`test/e2e/unified_child_harness.py`, `test/e2e/noros_child_helper.py` and three test modules
(`test_unified_ipc`, `test_unified_bridge`, `test_unified_two_channel`).

IPC GREEN: 11 passed. Two-channel GREEN: 6 passed. Bridge GREEN: 7 passed. The two-channel tests run
the production `ChildRuntime` socket servers against the production `BridgeClient` over real Unix
sockets, with only the leaf `ActionDriver` test-owned; the proxy can only hold/release normal-channel
bytes and never touches the safety socket. Proven: safety revoke wins over a delayed normal packet
with `submit_count == 0`, submit wins exactly once and a repeated token never double-submits, cancel
targets the accepted UUID and keeps the reservation, expired queued mutations never dispatch,
repeated revokes do not undo the tombstone, the web-death latch cancels known pending goals and
refuses new work, and wrong epoch/token never reaches the child. Bridge tests spawn a real
ROS-free child process: fixed argv, live identity recomputation, owner-identity drift refusing to
signal, crash making the bridge unready, safety cancel over the independent socket, and a subprocess
proof that importing the web modules never loads `rclpy`.

Platform fact recorded: Darwin caps `AF_UNIX` paths at 104 bytes, so the harness allocates a short
socket scratch directory under `SO101_IPC_SOCKET_BASE` (registered root) and the child refuses an
over-long socket path explicitly.

Deviation: `unified/ros_child.py` imports the existing ROS worker lazily and its
`RclpyActionDriver.submit/cancel/terminal` intentionally fail with `ROS_DRIVER_NOT_PROVISIONED` on
this host. The socket, protocol, runtime, ownership and cancellation layers are verified; the ROS
driver wiring cannot be verified on macOS and is not claimed as working. `server.py` was not
modified in this task: the application-logic migration belongs to Task 5, and changing ROS worker
code that cannot be exercised here would be an unverifiable edit. Commit `ad1a861a`.

## CP-07: Task 5 - parent operations and admission

Delivered `unified/{parents,admission,teleop_service}.py`, `unified/arbiter.py` and
`unified/intent_store.py` additions, a minimal `so101_teleop/server.py` gate hook, and
`test/teleop/test_unified_{parents,admission}.py` (registered `test_unified_parents`,
`test_unified_admission`).

GREEN: 12 parent tests + 8 admission tests passed, and the full backend set
(`test_unified_gate`, `arbiter`, `instances`, `safety`, `ipc`, `bridge`, `two_channel`,
`parents`, `admission`) passes in one gated invocation, exit 0. Covered: the exact
arm-then-gripper barrier from the plan with a Validation start refused in the middle, cancel
between the arm terminal and the gripper dispatch never dispatching the gripper, a failed
arm never dispatching the gripper, missing cleanup proof blocking the parent, home as one
parent across planning/arm/gripper, workflow pause keeping the reservation and resume
requiring authority, a workflow physical terminal settling, an authority-guard failure
blocking instead of releasing, duplicate execute-all returning the recorded parent and
payload drift refused; plus a complete per-entry operation classification table, read
entries never taking a reservation, motion without instance authority refused, safety
entries refused from the reservation path, teleop-refuses-validation and
validation-refuses-teleop/tasks in both directions, and resume that cannot be minted from a
parent id.

`server.py` gained an optional admission hook (`bind_admission`, `_admission_gate`) wired
into the two existing choke points `_mutation_gate` and `task_mutation_gate`, with the
operation name carried in a `contextvars.ContextVar`. Because those modules import `rclpy`
at module level, the regression check runs through a ROS-sourced gate:

Executable gate recipe (recreate `operator/gate-env.sh` from this description if the `/tmp`
root is gone): export `SO101_TASK_ROOT`, `SO101_GATE_POLICY`, `SO101_GATE_POLICY_SHA256`,
`TEST_PYTHON=/Users/matianyi/ros2_jazzy/.venv/bin/python`, `BUN=/opt/homebrew/bin/bun`,
`SO101_IPC_SOCKET_BASE="$SO101_TASK_ROOT/ipc"`, `PYTHONNOUSERSITE=1`,
`PYTHONDONTWRITEBYTECODE=1`, and prepend the worktree `src/so101_teleop` and
`src/so101_demo_py` to `PYTHONPATH`; `pygate <paths>` runs `record_gate.py --root
$SO101_TASK_ROOT --python $TEST_PYTHON -- $TEST_PYTHON -m pytest -p no:cacheprovider <paths>`
with a fresh `pytest-XXXXXXXX` invocation directory; `pyrgate` does the same after sourcing
`~/ros2_jazzy/install/setup.bash`, `extra_ws/install/setup.bash`,
`so101_isolated_ws/install/setup.bash` and the venv, and must pass
`-p no:launch_testing -p no:launch_ros -p no:launch_pytest` (ROS's `launch_testing` pytest
plugin otherwise hijacks module collection and reports a misleading import error).

Verified with that recipe: `pyrgate src/so101_teleop/test/teleop/test_server_safety.py`
exits 0, so the existing Teleop gate behavior is unchanged by the new hook.

Deviations from the plan's Task 5 staging list: `service.py`, `task_service.py`,
`expert_validation/service.py` and `expert_validation/production.py` are **not** modified.
`TaskService` already routes every mutation through `teleop.task_mutation_gate`, so the hook
covers it once `server.TeleopService` is the bound service; the plan's full
`ProductionTeleopService` swap of `service.py` belongs with Task 6's factory composition and
is not claimed done. `unified/arbiter.py` and `unified/intent_store.py` are included because
`resume_parent`, `lookup_command`, `parent_record`/`child_record` and the hold registry are
required by the new modules. `ProductionTeleopService` is exercised by three tests driving a
real gateway, arbiter, safety lane and parent sequencer with a fake `WorkerPort`; its ROS
transport is not claimed.

Known limitation to carry forward: for `SHORT_WRITE` entries the gateway takes a short
reservation that is settled at the end of the gate call, so the reservation covers admission
but not the write itself. A later task must move that settle to the operation's completion.

## Evidence accounting at CP-07

`gates/` holds 11 recorded invocations: 7 green runs (Task 0 gate suite, Task 1, Task 2,
Task 3, Task 4, the final nine-module backend run, and the ROS-sourced
`test_server_safety.py` run) plus 4 nonzero records. The four nonzero records are the
ROS-sourced debugging sequence for `test_server_safety.py`: first the missing ROS underlay
(`ModuleNotFoundError: control_msgs`), then ROS's `launch_testing` pytest plugin hijacking
module collection and reporting a misleading `so101_demo.parallel_batch` import error. The
final run of that same command exits 0 and supersedes them; the failure records are retained,
not deleted. Every task commit is backed by a green gated invocation of that task's own test
modules. Test modules delivered: gate 15, arbiter 15, instances 12, safety 12, ipc 8,
bridge 7, two_channel 6, parents 12, admission 8 (95 test functions).

## CP-08: Task 6 - one factory, lifecycle, routers and OpenAPI

Delivered `unified/{ports,app,lifecycle,main,compose}.py`, `scripts/so101_unified_web_server.py`,
a rewritten `openapi_export.py` (one schema, three views), `QualificationView` in
`unified/contracts.py`, `web/package.json` `generate:api:unified`, and
`test/teleop/test_unified_{api,lifecycle}.py` plus an added export test.

GREEN: ROS-sourced gate over `test_unified_api.py` + `test_unified_lifecycle.py` +
`test_openapi_export.py` exits 0; the plain gate over the nine backend modules exits 0.
Covered: exactly one `/tasks/runs` POST route, no `disabled_tasks` shim, unique operation ids,
the plan's literal factory test, structured `CONTROLLER_INSTANCE_REQUIRED` for every legacy
mutation path (POST/PUT/DELETE) without authority headers, authority headers without a
composed registry failing closed as `SERVICE_NOT_COMPOSED`, read-only routes staying reachable
while a domain is unavailable, unknown API/artifact paths returning JSON 404 instead of the SPA,
the legacy `max_points_per_worker` contract rejected before body validation, bind-address
policy, lifecycle ordering (bridge failure lowering Teleop readiness only, blocked arbiter
refusing to serve, validation maintenance failure recorded, shutdown closing owned work),
composition without ROS producing a readable app with reasons, the budget-view field set, the
entry point having no helper/driver flags, and a subprocess import probe proving the web chain
never loads rclpy.

Exports generated through the gate: `unified_openapi.json` (45 paths, "SO-101 Unified"),
`openapi.json` (29, "SO-101 Teleop"), `expert_validation_openapi.json` (22, "SO-101 Expert
Validation"), and the three generated `.d.ts` files after `bun install --frozen-lockfile`
(lockfile unchanged).

### Environment facts discovered in this checkpoint (they change how gates must run)

1. `so101_demo_py` uses setuptools `package_dir={so101_demo: "src"}`, so the source tree has
   no `so101_demo/` directory: `so101_demo.*` is only importable after a colcon install. A
   symlink shim `$SO101_TASK_ROOT/pyshim/so101_demo -> src/so101_demo_py/src` reproduces the
   install-time mapping for source-mode tests. The plan's Task 0 export
   (`PYTHONPATH=.../src/so101_demo_py`) does **not** make `so101_demo` importable and is
   recorded as a plan defect. Installed gates (Task 11) must still use the real copied prefix.
2. `so101_teleop.expert_validation.__init__` imports `.catalog`, which imports
   `ament_index_python`; therefore the unified factory currently needs the ROS environment to
   import. `pyrgate`/`rosgate` (see the CP-07 recipe, extended with the shim path and
   `-p no:launch_testing -p no:launch_ros -p no:launch_pytest`) is the gate for anything that
   touches the validation package. Making that import lazy is a candidate follow-up, not done.
3. `rosgate <cmd...>` runs an arbitrary command through `record_gate` under the sourced
   workspace; the three OpenAPI exports were produced through it.

## CP-09: Tasks 10 and 12A, plus two pre-existing defects repaired

**Task 10 (budget adapter)** - `unified/budget_adapter.py`, `test/teleop/test_unified_budget_adapter.py`
(registered `test_unified_budget_adapter`), lifecycle start gate. GREEN: 15 tests (plain gate).
Covers the plan's literal exact-N test, every N disabled while the provider is UNKNOWN,
AVAILABLE requiring a promoted profile and approval hash, a provider answering for a different
N refused, a v1 contract refused, a provider exception becoming UNKNOWN with a reason, and the
retry N1 context staying separate. Commit `f2871ac1`. The frontend half of Task 10
(`qualification-view.ts`) is deferred to Task 7, which the plan makes the file's creator.

**Task 12A (live fixture authorization, code only)** - `live-sim.ts` now requires
`SO101_UNIFIED_LIVE_AUTHORIZATION` (a non-secret operator JSON with scope, runtime identities,
deadline, owned-process rule; proof-shaped keys rejected) *before* stack inspection, and the
fixture spawns only `so101_unified_web_server.py`. Added the `unified` Playwright project
depending on the reviewed `r01-sequential` producer and `web/e2e/unified/live-sim.spec.ts`.
`test/teleop/test_unified_{live_fixture,launch}.py` registered. Commit `9690b7f8`.

Two plan/source conflicts were resolved in favour of the newer reviewed source and recorded in
the tests themselves:
- The plan's RED test asserts `SO101_VALIDATION_PROVENANCE_BINDING` appears in the fixture. The
  reviewed source deliberately *retired* provenance bindings as runtime authority ("The retired
  provenance binding is gone..."). The binding was not reintroduced; a test now pins that
  decision in both directions.
- The plan names four Playwright projects (`sequential`/`parallel`/`adaptive`/`unified`). The
  branch has eight, owned by the parallel-budget task. Renaming or deleting them would break
  another task's live workflow, so the unified project was added and the existing names kept.

**Pre-existing defect 1 (repaired, out of plan)**: `bun run build` failed on pristine HEAD -
`expert-validation-types.ts` imports `Schemas["CapabilitiesResponse"]` and
`Schemas["StartGuardPolicyResponse"]`, which no exported schema defines. Proven pre-existing by
building a detached `git worktree` of HEAD, which produced the identical five TypeScript errors.
Repaired by registering the capabilities route with a `CapabilitiesResponse` model that keeps the
reviewed name, widens `extra` to `allow`, requires `worker_qualifications`, and still nests
`StartGuardPolicyResponse`; regenerated the three schemas and three `.d.ts` files; added the
required qualification list to the app test fixture. Commit `768328f0`.

**Pre-existing defect 2 (gate-level, not a product bug)**: this harness exports
`NODE_ENV=production`, so React loads its production build and every component test fails with
`act(...) is not supported in production builds of React` (77 failures). With `NODE_ENV=test`
the whole frontend suite passes: **30 files / 126 tests**. `buntest` in the gate recipe sets it
and must never be used for `run build`.

### Running gates (current recipe)

`pygate <paths>` - plain source gate. `pyrgate <paths>` - ROS-sourced pytest gate (required for
anything importing the validation package, because `expert_validation/__init__` pulls `catalog`
→ `ament_index_python`). `rosgate <cmd...>` - ROS-sourced arbitrary command.
`bungate <...>` - Bun in `web/`. `buntest` - `NODE_ENV=test bun run test`. All of them go through
`record_gate.py` and land in `<root>/gates/<uuid>/`.

### Remaining work

Tasks 7, 8, 9 (frontend root providers/instance transport, the frozen preset plus theme smart
merge, the unified shell and two-page layouts), Task 11 (CMake dependency list, full
configure/build, copied-install Chrome gate), and Task 12B/C (measurement, live runs, the
Chinese operation guide). Task 11's colcon stages need a complete `so101_demo_py` closure; the
source shim is only for source-mode tests and must not be used for the installed gate.

## CP-10: Task 7 part A - root runtimes, instance transport, qualification view

Delivered `web/src/api/{instance-client.ts,domain-transport.ts,qualification-view.ts}` and
`web/src/state/{domain-runtime.ts,runtime-provider.tsx}` with their four test modules, and
rewired `main.tsx` to build the two runtimes once and mount `RuntimeProvider` around a
History-API page switch. `unified/app.py` now types `/control/instances` with
`InstanceProofResponse` so the client type is generated rather than hand-written.

GREEN: `bun run build` exit 0 and **34 files / 149 tests** (up from 30/126) with `NODE_ENV=test`.
Covered: the plan's literal sequence-gap test (a gap re-snapshots and never posts), contiguous
and stale events, an epoch change forcing a snapshot and advancing the execution generation,
events buffered while a snapshot is in flight with a bounded buffer, posting without authority
refused, `dispose` closing the transport, registration not touching storage, a rejected
handshake surfacing the server code, all four authority headers on a mutation, every unknown
N disabled before provider integration, only an available promoted N selectable, points 4..20,
page-path mapping, and navigation inside one provider neither re-registering nor closing the
runtime.

Remaining in Task 7 (not claimed): moving the telemetry/renew effects out of `app.tsx` and
`expert-validation-app.tsx` into the runtimes, replacing the two-POST `TeleopApiClient.executeAll`
with one `POST /plans/{id}/execute-all`, and having the three page components and the existing
`client.ts`/`task-client.ts`/`expert-validation-client.ts`/state stores consume the provider.
Until that lands the pages keep their current effects and the runtimes only own instance
authority, subscription and recovery.

## CP-11: Task 7B (single execute-all) done; Task 8 blocked on registry access

**Task 7B** - `TeleopApiClient.executeAll` now sends exactly one
`POST /plans/{plan_id}/execute-all` carrying the command id, lease, session and gripper
target, and returns the parent projection; the caller in `app.tsx` records the parent's phase
instead of two child results and only clears the plan when the parent is COMPLETE. A non-COMPLETE
parent is never retried with a second POST. `bun run build` exit 0, `NODE_ENV=test bun run test`
**34 files / 150 tests**. Commit `1933e95c`.

**Task 8 is blocked on the pinned CLI's registry access.** Reproduced twice in the isolated
preview project `<root>/preset-preview-8f09f448` (created by the plan's own recipe):

```
cd <root>/preset-preview-8f09f448
bunx shadcn@4.21.0 init -d --template vite --base radix --preset b311momZs0
# -> Request to https://ui.shadcn.com/init?...preset=b311momZs0... failed, reason: other side closed
# same failure with HTTPS_PROXY/HTTP_PROXY=http://127.0.0.1:10809 exported for bun
```

The package itself resolves (`bunx shadcn@4.21.0 --version` prints `4.21.0`, matching the
plan's pinned version), and the same URL returns **200 to curl** through the proxy, so this is a
bun-specific fetch failure for `ui.shadcn.com`, not general network denial. Evidence retained:
`operator/preset-init.json`, `preset-preview-8f09f448/init.log`, `init-proxy.log`.

What was nevertheless verified and captured for the later Task 8 work:

- The CLI's own request URL independently confirms the decoded preset:
  `base=radix, style=maia, baseColor=mist, theme=blue, chartColor=mist, iconLibrary=lucide,
  font=dm-sans, fontHeading=outfit, radius=large, menuAccent=subtle, menuColor=default`.
- `operator/preset-init.json` holds the real manifest: `name=radix-maia`,
  `dependencies=["shadcn@latest","class-variance-authority","cn","tw-animate-css","radix-ui","lucide-react"]`,
  `registryDependencies=["utils","font-dm-sans","font-heading-outfit"]`, and the complete
  light/dark `cssVars` token sets in oklch plus `css` and `config`.
- `https://ui.shadcn.com/r/styles/new-york/utils.json` returns 200; `/r/styles/maia/*.json` and
  the `font-*` items return 404, so the maia/font registry URL shape still has to be determined
  from the CLI rather than guessed.

Consequences: `design-system.lock.json`, the `src/lib/design-system.test.ts` RED test, the CLI
`--dry-run --diff` capture and the theme/primitives smart merge are **not** done. Task 11's static
CMake test also asserts `design-system.lock.json`, so that assertion stays unmet until Task 8
produces the lock. Next attempt should run the pinned CLI under the repository's own Node
(`NODE_USE_ENV_PROXY=1 npx -y shadcn@4.21.0 ...`) or discover the correct registry URL shape from
the CLI source, and must still fail closed rather than substitute `latest`.

## CP-12: Task 9 first increment - map display contract

`TopViewMap` markers now carry `data-point-status` and a `<title>` element with the readable
business state, so a state is never conveyed by colour alone, and a test pins the display
contract: one marker radius across PASSED/EXECUTING/FAILED/INDETERMINATE/INVALID_BLOCKED, the
state names present as text, and `preserveAspectRatio="xMidYMid meet"` on the accessible image.
The existing geometry (`projectXY`, `pixels_per_m`, cup footprint, target tolerance) is
untouched. `bun run build` exit 0 and **34 files / 151 tests**. Commit `d8c0d56c`.

Still open in Task 9: `components/unified/app-shell.tsx`, `styles/unified-layout.css` (the plan's
grid rules), the Sidebar/Sheet navigation, wiring the pages to the root runtimes and the
qualification view, and the 1400x900 / 390x844 no-overflow checks.

## CP-13: Task 9 shell and layout rules

`components/unified/app-shell.tsx`, `components/unified/app-shell.test.tsx` and
`styles/unified-layout.css` (imported by `index.css`). The shell owns theme, the two primary
entries, a separate domain-health strip and the global-owner reason. Tasks stays a compatibility
route: it renders under the shell but is not a third primary entry, and there is no shared
business lease in the shell.

The layout CSS implements the plan's approved grid verbatim (`.validation-layout` 3fr/2fr with
`minmax(0, ...)`, `.validation-map svg { width: 100%; height: auto; max-width: none }`,
`.point-results` three columns falling to two at 1100px and one at 360px, single-column
validation below 760px) plus the shell/sidebar/teleop-joint-table rules.

GREEN: `bun run build` exit 0, `NODE_ENV=test bun run test` **35 files / 156 tests**. Covered:
navigation between the two entries without rebuilding the shell (the same content node stays
mounted), Tasks as a compatibility route rather than a primary entry, the collapsible
narrow-screen navigation (always present on wide screens via a media query rather than a
permanent `hidden` attribute, which had made the entries unreachable for assistive technology),
domain health and the global owner reason rendered outside the page content, and a light-default
theme that flips and applies to the document even when storage is unavailable or partial.
Commit `195606f7`.

Still open in Task 9: rendering the pages through `AppShell` in `main.tsx`, migrating the page
effects onto the root runtimes, consuming the qualification view in `CampaignSetup`, and the
1400x900 / 390x844 no-horizontal-overflow checks. Task 8 remains blocked on registry access as
recorded in CP-11.

## CP-14: shell becomes the app frame; design-system lock; web build inputs

**Task 9** - `main.tsx` now renders every page inside `AppShell`, so a page switch replaces only
the page content and the root providers stay mounted. Build 0, suite green. Commit `6a477c92`.

**Task 8 partial** - `design-system.lock.json` plus `src/lib/design-system.test.ts` (the plan's
RED test, extended so the lock can never overclaim). The lock records only verified facts:

- `cli.version = 4.21.0`, verified by running the pinned CLI (`bunx shadcn@4.21.0 --version`);
- the decoded preset exactly as the CLI's own request URL encodes it
  (`maia / mist / blue / mist / lucide / dm-sans / outfit / large / subtle / default`, `radix` base);
- one `registry` entry that is the real preset manifest fetched from
  `https://ui.shadcn.com/init?...preset=b311momZs0...`, with `sha256 =
  242969b2ed2d4ced3c35fdbc07605fd47758b3893f00f972f5af98df322a60df`, its `type`
  (`registry:base`), and the manifest's own dependency lists;
- the product's real toolchain (`tailwindcss 3.4.17`, bun 1.3.14, node 25.9.0).

The lock deliberately records `fonts: []` and a `blocked_reason` naming
`PENDING_REGISTRY_ITEMS`: neither the per-component maia items nor the font files could be
fetched (see CP-11), and inventing them is not acceptable. A second test asserts the lock claims
no component set or font it has not captured and contains no `latest`/guessed version.

**Task 11 partial** - `CMakeLists.txt` now globs `src/*.css` and `public/*` with
`CONFIGURE_DEPENDS` and depends on `index.html`, `components.json` and
`design-system.lock.json`; `test/test_unified_web_dependencies.py` (registered
`test_unified_web_dependencies`) asserts those inputs, that every declared dependency exists, and
that the bundle is built by Bun with the frozen lockfile. `pygate` exit 0. Still open in Task 11:
the three real incremental rebuild proofs, the full configure/build, the 16 registered-test
Python checks and the copied-install Chrome gate.

Both changes are in one commit because the CMake dependency list is exactly what the new lock
file satisfies.

## CP-15: exact-N selection consumes the qualification view

`CampaignSetup` accepts the read-only `qualifications: QualificationView[]` from Task 10. When
present it is authoritative: an exact N whose view is unknown or unpromoted is disabled in the
selector and its provider reason is shown, while an AVAILABLE promoted N stays selectable. The
existing `worker_count_availability` contract is still honoured, so an unqualified N cannot be
enabled by satisfying only one of the two. The component never lowers N, never substitutes
ADAPTIVE, and has no K or max-points-per-worker input.

GREEN: `bun run build` exit 0, two new component tests plus the whole suite pass. Commit
`497ac784`.

## CP-16: the approved layout is a pinned contract

`src/styles/unified-layout.test.ts` asserts the reviewed layout rules so a later edit cannot
silently drop them: the 60/40 `minmax(0, 3fr) / minmax(0, 2fr)` validation split, a map that
fills its column (`width: 100%`) with no small `max-width` and an auto height, point results
stepping 3 -> 2 columns at 1100px -> 1 column at 360px, the single-column validation layout below
760px, the dense joint table scrolling inside its own `overflow-x: auto` container rather than
overflowing the page, the navigation collapsing only below the 901px breakpoint, and the
stylesheet being imported by `index.css` so it is part of the bundle.

GREEN: `bun run build` exit 0, `NODE_ENV=test bun run test` **37 files / 165 tests**. Commit
`aae538a5`.

This is a static contract, not the browser evidence the plan asks for: the 1400x900 and 390x844
no-horizontal-overflow checks and the light/dark contrast and focus checks still need a real
browser run (Task 11's installed Chrome gate or a local `bun run dev` capture).

## CP-17: the operation guide

`docs/guides/so101-unified-webapp-operation.md` (Chinese, written with the project-local
`humanizer-zh` skill, filed under `docs/guides/` per AGENTS.md). It documents only what is
implemented and verified: the single launcher and the two deprecating shims, bind-address policy,
`/health/live` versus `/health/ready`, the instance/authority headers and why a copied lease
grants nothing, the refusal codes a user will actually see, the isolated safety lane and the fact
that an accepted cancel is not a physical stop, the single-parent execute-all/home/workflow
lifecycle with explicit resume, explicit recovery instead of automatic takeover, exact-N worker
qualification with no K input, and how evidence and marker semantics are read.

It also has an explicit "not done yet" section listing the unfinished gates (installed Chrome
viewport evidence, the pending preset registry and fonts, the unprovisioned ROS driver, and the
separately authorized Stage B/C measurement and live replacement), plus a symptom-to-check table.
Commit `2a83b1d4`-class docs commit follows this entry.

The plan asks for an independent Astra/high review of the guide before its scoped commit. That
review is a GPT-6 Astra task and is **not** performed in this session; the guide is committed as
an unreviewed draft and the missing review is recorded here rather than silently skipped.

## CP-18: back/forward routing pinned

A test now drives a real `popstate` after an out-of-band `history.pushState` and asserts the shell
follows the browser: the page changes to validation and back to teleop while the runtime is
registered exactly once and never closed. This covers the plan's "direct refresh/back/switch"
requirement at the routing layer. `bun run build` exit 0, `NODE_ENV=test bun run test`
**37 files / 166 tests**. Commit `c38a3aa2`.

## Session status at CP-18 (for the next round)

The account of what is and is not done lives in CP-11 (Task 8 registry blocker with exact
reproductions and retained evidence), CP-14 (the lock file's verified contents and the CMake web
inputs), CP-16 (the pinned layout contract, explicitly not browser evidence) and CP-17 (the
operation guide, including the missing independent Astra review). The two gate helpers and the
full recipe are described in CP-07 and CP-09; the registered evidence root is
`/tmp/so101-debug-so101-unified-webapp-impl-20260920` with `operator/preset-init.json` and
`preset-preview-8f09f448/` as the Task 8 artifacts.

## CP-19: the preset registry really is remote (negative result, closes a hypothesis)

Probed the cached pinned package at `~/.bun/install/cache/shadcn@4.21.0@@@1` to test whether the
preset and its component items ship inside the npm package, which would have made Task 8
reachable without the web registry. They do not:

- `dist/tailwind.css` (16 KB) is the generic v4 `@theme inline` base plus custom variants, not the
  preset's tokens;
- `dist/preset/index.js` and `dist/registry/index.js` are the machinery only: the only preset
  data present is the style list `["nova","vega","maia","lyra","mira","luma","sera","rhea"]`;
- the pinned id `b311momZs0` appears nowhere in the package.

So the resolved preset object and the per-component items are fetched from `ui.shadcn.com`, which
is exactly the path that fails for the CLI here while succeeding for curl. Task 8's remaining work
therefore needs either a CLI HTTP path that works against this proxy or a curl-driven capture of
the correct maia registry URL shape. No product change in this checkpoint; the hypothesis is
recorded so the next round does not repeat it.

## CP-20: the registry template is `r/{name}.json`, and every probed item URL 404s

Extracted the item URL template from the pinned package itself:
`dist/index.js` contains the literal template `r/{name}.json` against the base
`https://ui.shadcn.com`, plus `https://ui.shadcn.com/schema.json` and
`/schema/registry-item.json`. There is no style segment in the template, and the module exposes
`registry:ui|lib|component|hook|page|file|block` item types.

Every candidate item URL was then probed through the working proxy and returned the site's 35 KB
HTML 404 page:

```
/r/button.json                     404
/r/utils.json                      404   (also /r/utils.json?style=maia)
/r/button.json?style=maia&base=radix 404
/r/font-dm-sans.json               404
/r/maia/utils.json                 404
/r/styles/maia/utils.json          404   (also button.json, index.json, font-* items)
/r/styles/new-york/utils.json      200   <- legacy style only
```

So the reachable registry surface here serves the legacy `new-york` style, while the `maia`
(radix preset) items are behind a route this environment cannot resolve. Combined with CP-19,
the remaining Task 8 work needs either (a) a CLI HTTP path that survives this proxy, or (b) the
registry route discovered from a working network — guessing further is not a good use of rounds,
and the lock keeps its honest `PENDING_REGISTRY_ITEMS` marker meanwhile.

## CP-21: Task 8 registry unblocked - the style segment is the manifest's own name

**The blocker is solved.** The registry style segment is `radix-maia` - the `name` field of the
preset manifest - not the decoded style `maia`. The template found in the package is
`r/styles/{style}/{name}.json` with `style = radix-maia`:

```
https://ui.shadcn.com/r/styles/radix-maia/utils.json   -> 200
```

Fetched all 18 needed items successfully (evidence retained in
`<root>/registry/<name>.json`): `utils`, `font-dm-sans`, `font-heading-outfit`, `button`, `card`,
`sidebar`, `sheet`, `field`, `select`, `input`, `label`, `badge`, `alert-dialog`, `tooltip`,
`separator`, `tabs`, `scroll-area`. Each has a verified sha256 recorded in
`web/design-system.lock.json`; the two `registry:font` items record family, provider, import,
variable, subsets and dependency (e.g. DM Sans Variable via `@fontsource-variable/dm-sans`).

The lock's `blocked_reason` is now the narrower, accurate
`PENDING_PRODUCT_MERGE`: the data is captured, but the token/primitives smart merge into this
Tailwind 3.4.17 project and the self-hosted font files are not applied yet. The lock test asserts
all 17 required item names, the real per-item URL and hash, both font entries, and that no version
is guessed.

GREEN: `NODE_ENV=test bun run test` all green. Commit `aefc5e34`.

Next for Task 8: apply the captured foundation tokens to `index.css`/`tailwind.config.ts` as a
v3-compatible smart merge (the captured `cssVars` are v4 oklch values, so the review decision in
the plan about a v4 upgrade versus a v3 equivalent conversion has to be taken explicitly), merge
the primitives while preserving business variants/ARIA/testids, and self-host the fonts with
licences.

## CP-22: the captured preset tokens are applied as v3-compatible variables

`src/styles/theme.css` is generated from the captured pinned manifest (the file records the
manifest sha256 in its header) and imported by `index.css` ahead of the Tailwind layers. It holds
all 31 light and 31 dark foundation tokens - background, card, foreground, muted, border, input,
ring, primary, secondary, accent, destructive, popover, the four sidebar groups and the five chart
colours - as plain custom properties plus the radius.

Two deliberate decisions, both recorded rather than implied:

1. **No v4 upgrade.** The declarations are plain `:root` / `[data-theme="dark"]` custom
   properties consumed through `var()`, so Tailwind 3.4.17 and the existing compiler are
   unchanged. The plan's `@theme`-based v4 path was not taken, so there is no mixed v4/v3 output.
2. **Business outcome colours are independent of primary.** `--state-success` is its own colour,
   `--state-pending` maps to primary, `--state-failure` maps to destructive; blue is never used as
   success. Display fonts declare CJK fallbacks (`PingFang SC`, `Noto Sans CJK SC`) and no runtime
   `@import url(...)` font request is introduced.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` all green with 5 new theme tests.
Commit `5591de0e`.

Still open in Task 8: self-hosting the two font files with licences (the lock records the
`registry:font` items and their `@fontsource-variable/*` dependencies), and the per-primitive smart
merge that preserves business variants, ARIA, events, disabled reasons and testids.

## CP-23: self-hosted fonts, hashes and licences

Downloaded the two captured `registry:font` families as variable woff2 from the packages the
registry items themselves name (`@fontsource-variable/dm-sans`, `@fontsource-variable/outfit`,
via the jsdelivr CDN) into `public/fonts/`, verified the `wOF2` magic bytes, and recorded in the
lock for each: relative file, family, provider, CSS variable, source URL, sha256, byte length,
media type, licence and licence file. `public/fonts/LICENSES.txt` carries both upstream SIL Open
Font License 1.1 texts in full. `theme.css` gained local `@font-face` rules, so the browser never
requests an external font host. The lock marker is now `PENDING_PRIMITIVE_MERGE`, which names the
one thing actually left in Task 8.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **38 files / 172 tests**. Commits
`a1417525` and `c4c8a3c3`.

Process note: `a1417525` was committed before the full suite was read, and the suite caught a stale
assertion of mine (the old `PENDING_PRODUCT_MERGE` marker) within the same round; `c4c8a3c3` fixes
it and the marker assertion now matches the `PENDING_<WORK>:` shape generally instead of one exact
string. The lesson recorded for the next round: gate the commit on the suite result, not on the
build alone.

Remaining in Task 8: the per-primitive smart merge that preserves business variants, ARIA, events,
disabled reasons and testids.

## CP-24: every surface is bound to the tokens

`tailwind.config.ts` now maps the semantic palette onto the captured custom properties -
background, foreground, card, popover, primary, secondary, muted, accent, destructive, border,
input, ring and the sidebar group, plus radius and both font families. Business outcomes get their
own utilities (`success` -> `--state-success`, `pending`, `failure`) so blue is never success. The
base layer in `index.css` moved from `bg-slate-950 text-slate-100` to `bg-background
text-foreground`, so the old hardcoded slate surface is gone rather than left behind a few
restyled buttons. Still Tailwind 3.4.17: plain `var()` bindings, no v4 `@theme` declaration in
either the config or the CSS entry.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **39 files / 175 tests**. Commit
follows this entry.

Two self-inflicted test defects were caught by the suite in this round (a wrong expected variable
name, and a comment mentioning `@theme` tripping a "no v4 syntax" assertion). Both are fixed, and
the second is now comment-stripped the same way the theme test does it. The commit was gated on the
full suite this time.

## CP-25: the last hardcoded palette surfaces are merged

`alert-dialog.tsx`, `button.tsx` and `card.tsx` were the only primitives still naming a raw
palette. They now read the tokens: dialog and card surfaces use `border-border bg-card
text-card-foreground`, descriptions use `text-muted-foreground`, and the button's four business
variants map to `bg-primary`, `bg-secondary`, `bg-destructive` and the outlined
`border-input`/`hover:bg-accent` - every variant and size is kept, along with the focus ring,
`disabled:opacity-50` and the existing props. A new test walks every `components/ui/*.tsx` and
fails on any `bg|text|border|ring|fill|stroke-<palette>-<shade>` class, so the sweep cannot
silently regress. One baseline assertion in `tcp-panel.test.tsx` that pinned `bg-sky-600` was
updated to `bg-primary`.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **40 files / 178 tests**. Commit
`37cbb968`.

Remaining in Task 8: importing the *new* primitives the plan needs beyond the 12 that already exist
(sidebar, sheet, field, select, input, label) from the captured registry items, which is additive
work rather than a merge of existing behaviour.

## CP-26: the captured registry is Tailwind v4, and one primitive is ported

Reading the captured `registry:ui` sources settles the plan's open review question with evidence:
the `radix-maia` items are written for **Tailwind v4**. `input.tsx` uses `rounded-4xl` (no v3
equivalent), `bg-input/30` and `ring-ring/50` (v4 alpha composition of a `var()` colour), and both
items import `cn` from the bare specifier `"cn"` rather than this project's `@/lib/utils`.

Decision taken (mechanical and explicit, recorded rather than implied): **keep Tailwind 3.4.17 and
convert**, rather than perform the v4 upgrade. `src/components/ui/input.tsx` is the ported item:
`rounded-4xl` -> `rounded-md` (the token radius), `bg-input/30` -> `bg-input`, `ring-ring/50` ->
`ring-ring`, `ring-[3px]` -> `ring-2`, `aria-invalid:ring-destructive/20` -> solid
`aria-invalid:ring-destructive`, and the import rebound to `@/lib/utils`. Everything else is kept
verbatim: `data-slot`, the `file:` variants, `placeholder`, `focus-visible:border-ring`,
`disabled:*` and the invalid semantics.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **41 files / 181 tests**; commit gated
on the suite. The three new tests assert the data slot and ordinary props, the token classes with
no v4-only leftovers, and that disabled/invalid state stays declared for assistive technology.

Remaining in Task 8: the same port for the other captured primitives - `label` (which the registry
builds on `radix-ui`, a dependency this project does not yet have, so it needs either that
dependency or a dependency-free equivalent), `select`, `field`, `sheet` and `sidebar`. Each needs
the same explicit v3 conversion the input just had; guessing them in bulk would be the wrong move.

## CP-27: the label primitive is ported without widening the dependency closure

`src/components/ui/label.tsx` ports the captured `radix-maia` label. The registry imports the
`radix-ui` umbrella package; this project already depends on the scoped `@radix-ui/react-label`
(confirmed present in `node_modules`), so the primitive is behaviourally identical while the
import stays inside the existing closure - no new dependency, and `package.json`/`bun.lock` are
untouched. Classes are kept as the registry writes them (`data-slot`, `text-sm`, `font-medium`,
`select-none`, the `group-data-[disabled=true]:` and `peer-disabled:` pairs).

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **42 files / 184 tests**; commit gated
on the suite. The tests assert the data slot and `htmlFor` binding, that clicking the label focuses
its control, and that the disabled selector is preserved.

Remaining in Task 8: `select`, `field`, `sheet` and `sidebar`, each needing the explicit v4-to-v3
conversion. `sheet` and `sidebar` are the largest and pull in portal/sidebar machinery, so they
should be taken one at a time with their own behaviour tests rather than in bulk.

## CP-28: the select port needs real work, not a regex (reverted, tree clean)

Attempted a mechanical port of the captured `select` item (224 lines) and it failed typecheck in
three distinct ways, so the file was reverted and the tree is clean again (`bun run build` exit 0
after the revert). The failure modes are the useful output:

1. `import { Select as SelectPrimitive } from "radix-ui"` uses the umbrella package's namespace
   object. Rebinding it to the scoped `@radix-ui/react-select` must be
   `import * as SelectPrimitive from "@radix-ui/react-select"`; a named import has no `.Root`,
   `.Group`, `.Value` members.
2. The item imports an internal site component, `IconPlaceholder` from
   `@/app/(create)/components/icon-placeholder`, which does not exist in this project. A faithful
   port has to substitute the project's own icons (`lucide-react` is already a dependency) and
   check which indicator slots each one fills.
3. Alpha modifiers and `size-*` utilities need the v4-to-v3 conversion already applied to `input`.

So `select` is a real porting job - import strategy, icon substitution and a class pass - not a
substitution sweep. The same warnings apply to `field` (238 lines, and it declares
`registryDependencies: ["label", "separator"]`), `sheet` and `sidebar`. Next round should port one
item by hand, reusing the `input`/`label` conversions as the pattern, and only then wire the new
primitives into the pages.

## CP-29: select ported by hand with the three conversions CP-28 identified

`src/components/ui/select.tsx` (198 lines) is the captured `radix-maia` select ported properly:
the umbrella `radix-ui` import became `import * as SelectPrimitive from
"@radix-ui/react-select"` (keeping `.Root/.Group/.Value/...`), the site-internal
`IconPlaceholder` became the lucide icon its own `lucide` prop names (`ChevronDownIcon`,
`CheckIcon`, `ChevronUpIcon` - lucide is already this project's icon library), and the v4 classes
were converted (`bg-input/30` -> solid tokens, `rounded-4xl` -> `rounded-md`, `ring-[3px]` ->
`ring-2`, `size-*` -> `h-* w-*`). Structure, roles, data slots and keyboard behaviour are the
registry's own.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **43 files / 186 tests**; commit gated
on the suite. Two jsdom limits are documented in the test rather than papered over: radix renders
its listbox into a portal and calls `scrollIntoView`, so the open/select interaction is asserted in
the browser gate (Task 11), not in jsdom; the test asserts the closed render, the `select-trigger`
data slot, the token classes, and that no standalone v4 `size-*`/alpha class survives.

Remaining in Task 8: the same hand-port for `field` (238 lines, declares
`registryDependencies: ["label","separator"]` - both now available in some form), `sheet` and
`sidebar`.

## CP-30: field ported onto the existing label and separator

`src/components/ui/field.tsx` (238 lines) ports the captured field item. Its registryDependencies
were already satisfied in this project, so the registry's own `@/registry/radix-maia/ui/label` and
`.../ui/separator` imports point at `@/components/ui/label` (ported in CP-27) and the existing
`@/components/ui/separator`; `cn` resolves to `@/lib/utils`; the v4 alpha/size/radius utilities are
converted the same way as the other ports. The component's data slots (`field`, `field-group`,
`field-label`, `field-description`, `field-error`, ...) are the registry's own.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **44 files / 188 tests**; commit gated
on the suite. Tests assert the five data slots render, that the description uses
`text-muted-foreground` and the error uses `text-destructive`, and that no standalone v4
`size-*`/`rounded-4xl`/alpha class survives anywhere in the subtree.

Remaining in Task 8: `sheet` and `sidebar` - the two largest items, both pulling in portal and
sidebar machinery; each should get its own behaviour tests, and the sidebar in particular has to
respect the shell's navigation semantics from Task 9.

## CP-31: sheet ported, and the button gained the variants it needs

`src/components/ui/sheet.tsx` (146 lines) is the captured sheet: the umbrella `radix-ui` import
became the scoped `@radix-ui/react-dialog` namespace, the site-internal `IconPlaceholder` became
`XIcon` from lucide, the registry's button import points at this project's button, and the v4
utilities were converted.

The port surfaced a real gap rather than a workaround: the registry's sheet uses
`variant="ghost"` and `size="icon-sm"`, which this project's button did not have. The captured
button item declares six variants (`default`, `outline`, `secondary`, `ghost`, `destructive`,
`link`) and six sizes (`default`, `xs`, `sm`, `lg`, `icon`, `icon-sm`), so the missing ones were
merged into `src/components/ui/button.tsx` in v3-equivalent form, keeping the existing set intact.
The registry's v4-only refinements (`has-data-[icon=...]` padding, `dark:` alpha variants) are
omitted on purpose and that omission is written into the file.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **45 files / 190 tests**; commit gated
on the suite. The sheet test asserts the trigger renders and that no v4-only utility survives in
the file; the open/portal interaction is deferred to the browser gate, as with select. A second
test renders all six variants and all six sizes to prove the merged button surface is complete.

Remaining in Task 8: `sidebar`, the last item, which also has to respect the shell's navigation
semantics from Task 9.

## CP-32: the shell uses the ported sheet, and the nav semantics survive it

`AppShell`'s hand-rolled collapse is gone. Narrow screens now open the **ported design-system
`Sheet`** (radix dialog) with the two primary entries inside it, while wide screens keep the list
permanently visible (`hidden ... md:block`). The earlier accessibility fix is preserved rather than
undone: the entries are never behind a permanent `hidden` attribute, so assistive technology can
always reach them, and radix owns the trigger's `aria-expanded`.

The shell test was updated to assert what is now true: the sheet trigger renders with
`aria-expanded="false"`, the wide-screen `navigation[aria-label=Primary]` contains both entries,
and clicking the trigger does not throw. The sheet's own portal content is not asserted in jsdom
(no layout), which stays with the browser gate.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **45 files / 190 tests**. Commit
`28bbb6ea`.

Remaining in Task 8: `sidebar` itself, the last item; with the shell's navigation now provided by
the sheet, the sidebar can be introduced only if the shell genuinely needs it, and the plan is
explicit that new items are introduced only where a page needs them.

## CP-33: a page now consumes the ported primitives

`CampaignSetup` uses the ported design-system `Input` for the catalog seed and the final point
count, and its section surface plus select/inputs all read tokens instead of a raw palette. A check
over the file now finds zero `bg|text|border-<palette>-<shade>` classes. Behaviour is unchanged:
the same `aria-label`s, the same read-only seed, the same min/max on the point count, and the same
existing component tests pass untouched.

GREEN: `bun run build` exit 0; `NODE_ENV=test bun run test` **45 files / 190 tests**. Commit
follows this entry.

Note for the next round: `Input`, `Sheet` and `Field` are now used by the product, while `Label` and
`Select` are ported but not yet consumed - `CampaignSetup` still uses a native `<select>` for the
worker count because its nine existing tests query native `<option>` elements, so switching it to
the radix select needs those tests rewritten in the same change. `sidebar` remains unported, and
with the sheet providing the shell's navigation the plan's rule ("introduce new items only where a
page needs them") argues for leaving it out unless a page actually requires it.
