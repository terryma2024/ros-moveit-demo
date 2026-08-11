---
task_id: so101-teleop-extraction
goal: Extract Teleop and GUI tooling into independently owned packages and validate explicit backend adapters without disturbing active robot stacks.
success_contract: Standalone so101_teleop and ai-station-gui owners pass package, Web, adapter, capture, installed-overlay, and approved live backend evidence gates; parent repository retains no duplicate capture implementation.
worktree: /data/work/ws_moveit/.worktrees/so101-teleop-extraction
branch: codex/so101-teleop-extraction
base_commit: c6982116d79c834de60b21d9e324a449a569a9c9
current_commit: bb99f90ee08706f9988d2c17c229ab89c227e951
evidence_root: /tmp/so101-debug-teleop-extraction-20260811/
confirmed_conclusions:
  - Approved design keeps robot workflow and physics ownership in each backend module; Teleop owns only the control plane (SPEC-2026-08-11).
  - Active physical-five-success and MuJoCo GUI stacks are preserved and are not implementation test fixtures (CP-001).
  - Gazebo Python scene CLI lacks Teleop scene-repair upsert, so scene_operations must remain false initially (CP-001).
disproven_routes:
  - FULL_RESTART is not an authorized lifecycle for later validation; use RESET_WORLD where reset is required (prior user decision).
open_hypotheses:
  - Gazebo C++ and Gazebo Python installed owner envelopes can preserve the existing Teleop workflow/session semantics through fixed CLI profiles.
  - Full desktop capture remains valid when RViz and Ghostty are both absent.
latest_checkpoint: CP-004
next_experiment: NONE
---

# SO-101 Teleop Extraction Experiment Ledger

This ledger begins before implementation. Automated RED/GREEN/build evidence is recorded in commits and `/tmp`; live experiments will be added as `PLANNED` entries before any new stack, reset, workflow command, GUI action, or capture validation.

## CP-001 — Approved design and execution start

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: Fixed installed CLI profiles can preserve control-plane semantics without moving robot workflow ownership.
working_tree_status: clean at 3cba80f before this ledger and plan correction
owned_processes: NONE
preserved_processes: physical-five-success Gazebo/RViz/move_group; existing MuJoCo GUI; codex-cua and other user tmux sessions
confirmed_conclusions:
  - Standalone worktree and three implementation plans are committed.
  - Current Gazebo Python scene owner lacks upsert and cannot honestly expose Teleop scene repair.
disproven_routes:
  - No compatibility wrapper at the old C++ Teleop or tiler entry.
open_risks:
  - CMake ownership moves must be atomic so neither package has a broken intermediate commit.
  - Live backend validation requires an isolated domain/partition or explicit authorization to reuse a verified idle stack.
next_command: Write and run the Task 1 package ownership RED test.
```

## CP-002 — Ownership RED complete; shared X11 dependency decision required

```yaml
checkpoint_id: CP-002
last_valid_experiment: NONE
current_hypothesis: The standalone package move is valid, but X11 helper ownership must preserve non-Teleop diagnostic commands without reversing dependencies.
working_tree_status: dirty with tracked Teleop/Web/config/docs/server moves into src/so101_teleop plus untracked src/so101_teleop/test/test_launch_contract.py; no implementation edits applied after the moves
owned_processes: NONE
preserved_processes: physical-five-success Gazebo/RViz/move_group; existing MuJoCo GUI; codex-cua and other user tmux sessions
confirmed_conclusions:
  - Task 1 ownership contract failed RED for exactly the missing standalone owner and present legacy owner, then committed as a54598f.
  - New launch contract failed RED because the standalone launch path does not yet exist.
  - ai_station_x11.py is imported by gazebo_window_recorder.py and so101_stack_inventory.py in addition to tile_ai_station_guis.py.
disproven_routes:
  - Deleting ai_station_x11.py while leaving the two dependent C++ diagnostic commands unchanged would create a broken installed package.
  - Making so101_gazebo_demo_cpp depend on so101_teleop violates the approved dependency direction.
open_risks:
  - Moving the two additional diagnostic commands changes their package owner beyond the explicitly named tiler migration.
  - Retaining a C++ copy leaves two X11 helper owners and weakens the intended extraction boundary.
next_command: NONE pending user selection between moving the dependent diagnostic commands or retaining a backend-local X11 helper copy.
```

## CP-003 — Shared X11 owner selected; GREEN migration resumed

```yaml
checkpoint_id: CP-003
last_valid_experiment: NONE
current_hypothesis: A single X11 owner in so101_teleop can support tiling, read-only stack inventory, and Gazebo window recording without a reverse dependency from the C++ robot package.
working_tree_status: HEAD 58cd719 contains the mechanical Teleop move; launch RED test is untracked and the package remains intentionally non-buildable until this GREEN step completes
owned_processes: NONE
preserved_processes: physical-five-success Gazebo/RViz/move_group; existing MuJoCo GUI; codex-cua and other user tmux sessions
confirmed_conclusions:
  - The user selected moving both dependent diagnostic commands and their tests into so101_teleop.
  - gazebo_window_recorder.py and so101_stack_inventory.py are operator diagnostics, not C++ robot behavior owners.
  - The new package will expose one importable so101_teleop.gui.x11 implementation and install all three operator commands as executables.
disproven_routes:
  - Keeping a second C++-local X11 implementation is unnecessary under the selected ownership model.
  - A C++ dependency on so101_teleop remains forbidden.
open_risks:
  - Source-tree script tests must explicitly expose the new Python package root before importing installed-style modules.
  - Both CMake install/test manifests must change atomically before the next commit.
next_command: Move the three diagnostic commands and four tests, then implement the standalone package CMake, launch, and installed lookup GREEN changes.
```

## CP-004 — Standalone package and shared GUI diagnostics GREEN

```yaml
checkpoint_id: CP-004
last_valid_experiment: NONE
current_hypothesis: Immutable installed backend profiles can now replace the remaining hard-coded Gazebo C++ owner lookup without moving workflow logic into Teleop.
working_tree_status: implementation committed as b95432c; only this ledger checkpoint remains dirty
owned_processes: NONE
preserved_processes: physical-five-success Gazebo/RViz/move_group PIDs 580035/580038/580060/580061/581537; move_group PID 2049562; existing MuJoCo GUI; codex-cua and other user tmux sessions
confirmed_conclusions:
  - so101_teleop owns the Web/FastAPI/Python package, launch, tiler, stack inventory, Gazebo recorder, and one importable gui.x11 implementation.
  - Explicit backend is required by launch; the extraction checkpoint accepts gazebo_cpp only and freezes SO101_TELEOP_BACKEND in the server environment.
  - Focused source tests passed: GUI/ownership/launch 82 and migrated Teleop 81; Web passed 38 of 38.
  - Installed package test passed 182 tests with 0 errors, 0 failures, and 0 skipped.
  - so101_teleop build and so101_gazebo_demo_cpp build passed after first building the worktree-local pick_place_common dependency.
  - Installed ownership exposes four so101_teleop executables; the C++ package no longer exposes Teleop, tiler, inventory, or recorder commands.
disproven_routes:
  - The worktree-local C++ build cannot run before pick_place_common is installed in the same worktree overlay.
  - bun --cwd ... run test was not accepted by the installed Bun CLI; running bun commands from the Web directory is the verified form.
deviations:
  - A direct run of test_so101_launch_contract.py unexpectedly started one temporary headless Gazebo server pair, PIDs 2290778/2290780. The existing test cleaned both processes on completion; no user stack was stopped or modified. Do not repeat this file outside a PLANNED isolated test lifecycle.
open_risks:
  - server.py still resolves so101_gazebo_demo_cpp executables directly; backend profiles and the fixed registry are not implemented yet.
  - No live Teleop backend validation is claimed at this checkpoint.
next_command: Write RED tests for frozen backend profiles, fixed backend IDs, strict schema rejection, and probe-only MuJoCo capabilities.
```

## EXP-001 — Isolated installed-package contract suite

```yaml
experiment_id: EXP-001
status: COMPLETE
hypothesis: The extracted Teleop owner and the unchanged C++ robot owner pass their installed package suites together without observing or modifying the preserved live stacks.
source_commit: e5ac41a28c3f59b71d43fb759d40aa5c2ab5601d
branch: codex/so101-teleop-extraction
overlay: /data/work/ws_moveit/.worktrees/so101-teleop-extraction/install/setup.zsh
installed_owners:
  - /data/work/ws_moveit/.worktrees/so101-teleop-extraction/install/so101_gazebo_demo_cpp
  - /data/work/ws_moveit/.worktrees/so101-teleop-extraction/install/so101_teleop
runtime_executable: colcon test --packages-select so101_gazebo_demo_cpp so101_teleop
lifecycle: REUSE_STACK
isolation:
  ros_domain_id: Per-test unique values from test_so101_pick_place_world.py, beginning at 100 + pytest PID modulo 100.
  gz_partition: Per-test UUID-suffixed so101_task1 and so101_task1_ready partitions; one one-iteration static world check uses so101_pick_place_world_contract.
owned_processes: Only subprocesses created by this test invocation; test cleanup may stop those exact child process groups.
preserved_processes: physical-five-success Gazebo/RViz/move_group; existing MuJoCo GUI; codex-cua and all other user/agent tmux sessions
motion_scope: Isolated headless test fixtures only; no commands target the preserved live ROS domain or Gazebo partition.
evidence_dir: /tmp/so101-debug-teleop-extraction-20260811/exp-001-installed-package-tests
success_gate: colcon test completes and colcon test-result --verbose reports zero errors and zero failures for both selected packages; post-test inventory shows no surviving test-owned Gazebo children.
abort_gate: Any evidence that a test resolves the preserved live ROS domain/partition, any unowned process cleanup target, or any attempt to stop/take over another agent process.
observed_result:
  - so101_teleop passed all 24 CTest entries.
  - so101_gazebo_demo_cpp passed all 67 CTest entries, including the isolated headless Gazebo contracts and C++ quality gate.
  - colcon test-result reported 1000 tests, 0 errors, 0 failures, and 8 skipped.
  - Post-test process audit found no surviving task1/task1_ready/world-contract process; only the audit shell and rg command matched their own query text.
conclusion: The extracted Teleop and C++ robot owners pass together from the worktree-installed overlay without leaking isolated test children or disturbing preserved stacks.
next_command: Commit the Task 10 ownership boundary and proceed to the ai-station-gui skill TDD plan.
```

## EXP-002 — Live desktop-first capture fallback

```yaml
experiment_id: EXP-002
status: COMPLETE
hypothesis: The project-local ai-station-gui fallback captures a fresh nonempty desktop and exits zero even when RViz or Ghostty is naturally absent, without using SSH or taking over the existing codex-cua session.
source_commit: bb99f90ee08706f9988d2c17c229ab89c227e951
branch: codex/so101-teleop-extraction
agent: Codex running directly on AI-STATION-001
capability_route:
  current_agent_cua_schema: unavailable in the current callable tool inventory
  existing_cua_session: codex-cua belongs to the so101-mujoco-ros2 worktree and is preserved read-only
  selected_route: .agents/skills/ai-station-gui/scripts/capture-ai-station.sh --local
overlay: /data/work/ws_moveit/.worktrees/so101-teleop-extraction/install/setup.zsh
runtime_executable: .agents/skills/ai-station-gui/scripts/capture-ai-station.sh
lifecycle: REUSE_STACK
ros_domain_id: not used by screenshot capture
gz_partition: not used by screenshot capture
owned_processes: Only the wrapper, Python helper, and ImageGrab/X11 read operations created by this invocation.
preserved_processes: physical-five-success Gazebo/RViz/move_group; existing MuJoCo GUI; codex-cua daemon/session; all other user/agent tmux sessions
action_scope: Full-desktop and optional-window screenshots; optional capture may focus the selected window and then restore the original active window. No semantic UI action, key, mouse, window close, stack reset, or robot movement.
evidence_dir: /tmp/so101-debug-teleop-extraction-20260811/exp-002-ai-station-gui.LFG1Ng
success_gate: Local wrapper exits zero; manifest is valid; desktop is fresh and nonempty; naturally absent optional windows are null; desktop is visually inspected; a no-Ghostty tab test, if naturally applicable, reports skipped_no_window without constructing an X11 manager.
abort_gate: Any SSH attempt, any key/mouse or focus action beyond capture-and-restore mechanics, any need to restart/take over codex-cua, or any stale/empty/placeholder capture.
next_command: Run the local wrapper into the planned evidence directory and inspect its manifest before deciding whether the no-Ghostty tab case is naturally safe.
observed_result:
  - The current Codex tool inventory exposed no callable cua-driver screen schema; codex-cua was read-only inspected and preserved because it belongs to so101-mujoco-ros2.
  - Initial desktop capture exited zero and produced a fresh 438242-byte desktop showing maximized Gazebo, the SO-101 arm, table, cup, and red target circle without an error dialog.
  - Ghostty was naturally absent in every live manifest; the final tab-skip manifest recorded ghostty null and ghostty_tab_test skipped_no_window, and the unit-injected path proves no send_shortcut call occurs.
  - Live visual inspection exposed two optional-window bugs before acceptance: xwininfo relative coordinates were used instead of the final absolute offsets, and raise/XSetInputFocus did not activate the Mutter-managed client.
  - RED tests now lock absolute geometry, application-client selection with its paired Mutter frame, and EWMH activation before capture; the full Skill suite passes 18 tests.
  - Final fresh RViz capture was 262226 bytes and visibly showed the RViz menu, Displays/MotionPlanning panels, SO-101 model, and planning-scene objects. The original Gazebo client 0x400000e was restored as _NET_ACTIVE_WINDOW afterward.
deviations:
  - The planned action wording initially said no focus. The approved helper contract requires capture-and-restore mechanics for optional windows, so the ledger was corrected before the successful reruns to distinguish screenshot activation from semantic GUI control.
  - Both optional windows were not naturally absent: RViz was present and Ghostty was absent. The required desktop and the naturally available no-Ghostty path were validated without closing user windows.
conclusion: The local screenshot fallback and CUA-priority routing satisfy the live acceptance gate without SSH, key/mouse injection, codex-cua takeover, stack reset, or robot movement.
next_command: Run the official Skill validator and final static/unit checks, then commit the live-discovered capture correction and ledger evidence.
```

## EXP-003 — Installed backend fail-closed and MuJoCo probe-only acceptance

```yaml
experiment_id: EXP-003
status: COMPLETE
hypothesis: The installed Teleop launch fails before binding a server for an invalid backend or an absent selected owner executable, while a resolvable MuJoCo owner starts probe-only and reports no live runtime features.
source_commit: 7db054c7168f967a197d913ff2fd2981643a07b6
branch: codex/so101-teleop-extraction
overlay: /data/work/ws_moveit/.worktrees/so101-teleop-extraction/install/setup.zsh
installed_owner: /data/work/ws_moveit/.worktrees/so101-teleop-extraction/install/so101_teleop
runtime_executable: ros2 launch so101_teleop so101_teleop.launch.py
lifecycle: ISOLATED
isolation:
  ros_domain_id: 221
  gz_partition: so101_teleop_exp003_20260811
  ports: 18103 for each sequential case, verified unbound between cases
owned_processes: Only the foreground timeout/launch/server process groups created for EXP-003; cleanup may signal only those exact process groups or interactive exec sessions.
preserved_processes: physical-five-success Gazebo/RViz/move_group; existing MuJoCo GUI and move_group; codex-cua and all other user/agent tmux sessions
action_scope: Backend selection, executable probing, and read-only HTTP health/capability/snapshot requests only; no workflow, planning, controller, reset, keyboard, mouse, or robot action.
evidence_dir: /tmp/so101-debug-teleop-extraction-20260811/exp-003-backend-failclosed-probe
success_gate:
  - An invalid backend exits nonzero before port 18103 is bound.
  - A synthetic first-prefix package marker with no owner executable causes the Teleop server child to exit nonzero with an explicit BACKEND_EXECUTABLE_NOT_FOUND error before port 18103 is bound; the enclosing ROS 2 launch service may still exit zero after reporting that child failure.
  - A resolvable mujoco_py owner serves health/capabilities/snapshot, reports backend_probe true, and reports all live runtime capabilities false.
  - The server exits through its owned foreground session and port 18103 is unbound afterward.
abort_gate: Any route that targets a preserved ROS domain/partition, any attempt to clean an unowned process, any live command capability unexpectedly true in probe-only mode, or any request to stop/take over another agent process.
observed_result:
  - The installed prefix resolved to the current worktree; installed launch, three fixed backend YAML profiles, Web bundle, server, tiler, inventory, and recorder were present. Symlink-install paths resolved back to this worktree's source and built Web assets.
  - backend:=not_a_backend exited 1 with unsupported Teleop backend and port 18103 remained unbound.
  - The synthetic ament first-prefix marker resolved so101_gazebo_demo_cpp to the fixture. The Teleop server child exited 1 with BACKEND_EXECUTABLE_NOT_FOUND for the fixture path and port 18103 remained unbound. ROS 2 launch itself returned 0 after logging the child failure, consistent with its process-service semantics.
  - With the MuJoCo installed overlay below the current Teleop overlay, /health returned 200, /capabilities named so101_mujoco_demo_py/pick_place_state_machine, backend_probe was true, and every live capability was false. /snapshot stayed STARTING with no claimed live session or telemetry.
  - The owned launch session was stopped by its own foreground Ctrl-C; Uvicorn and the server child shut down cleanly, port 18103 was reusable, and the only post-cleanup process match was the read-only audit shell matching its query text.
deviations:
  - The first invalid-backend harness post-processing used zsh's read-only status variable. The product had already failed closed and the port was free; the case was rerun end-to-end with exit_code and passed.
  - The initially drafted gate incorrectly required the enclosing ROS 2 launch command to propagate the missing server child's nonzero status. It was corrected before acceptance to the approved requirement: explicit child failure and no server.
conclusion: Installed selection fails closed before serving for invalid or unresolved owners, while the resolvable MuJoCo owner remains honestly probe-only with no live-success claim.
next_command: Plan EXP-004 for a dedicated Gazebo C++ stack, Teleop connection, one Start/single-step boundary, independent ROS/Gazebo/MoveIt evidence, and a fresh Skill capture.
```

## EXP-004 — Dedicated Gazebo C++ Teleop single-step acceptance

```yaml
experiment_id: EXP-004
status: COMPLETE
hypothesis: Teleop from the current installed overlay connects to a newly owned Gazebo C++ stack, reports its fixed C++ owner and live READY provenance, and dispatches one Start/single-step boundary whose checkpoint and physical effects are independently observable.
source_commit: 7db054c7168f967a197d913ff2fd2981643a07b6
branch: codex/so101-teleop-extraction
overlay: /data/work/ws_moveit/.worktrees/so101-teleop-extraction/install/setup.zsh
backend: gazebo_cpp
lifecycle: ISOLATED
isolation:
  ros_domain_id: 222
  gz_partition: so101_teleop_exp004_cpp_20260811
  port: 18104
  simulation_session_id: exp004-cpp-live
owned_processes: Exact child trees of the new foreground Gazebo, MoveIt, and Teleop exec sessions; PIDs and window IDs will be appended after startup. Cleanup may interrupt only those three owned sessions.
preserved_processes: physical-five-success Gazebo/RViz/move_group; other move_group; existing MuJoCo GUI; codex-cua and all other user/agent tmux sessions
motion_scope: One Teleop workflow Start request only, which maps to the installed C++ owner with --step. No subsequent Step/Run/Resume, manual motion, attach/detach, scene repair, or FULL_RESTART. RESET_WORLD is the only permitted reset if recovery is needed.
evidence_dir: /tmp/so101-debug-teleop-extraction-20260811/exp-004-gazebo-cpp-live
success_gate:
  - Dedicated stack exposes its own controller, joint/TF, Gazebo world/model, and MoveIt Planning Scene facts and Teleop reaches READY with exp004-cpp-live.
  - /capabilities names gazebo_cpp and so101_gazebo_demo_cpp/pick_place_state_machine.
  - Start returns the installed backend owner envelope, creates a fresh checkpoint, and advances exactly one workflow boundary.
  - Before/after evidence records expected joint/TF effects (including an explicit no-change conclusion if the first boundary is non-motion), Gazebo object facts, and MoveIt scene facts.
  - The ai-station-gui Skill emits a fresh desktop manifest/image; the visible new GUI is correlated to an EXP-004-owned PID/window before it is used as evidence.
  - All EXP-004 sessions exit cleanly and domain/partition/port have no surviving task-owned process.
abort_gate: Any conflict with an existing agent-owned process/session/window, ambiguity that would require controlling another window, readiness loss, action beyond the single-step scope, or cleanup target outside exact EXP-004 child sessions.
owned_runtime:
  gazebo_launch_session: exec session 17677; launch PID 2475406; robot_state_publisher 2475535; Gazebo launch child 2475536 with server/GUI descendants 2475538/2475559/2475560; relay 2475574
  moveit_launch_session: exec session 92239; launch PID 2476596; move_group 2476650
  teleop_launch_session: exec session 89898; launch PID 2477879; server 2477935
  shutdown_probe_session: exec session 27846; launch PID 2493368; server 2493539
observed_result:
  - Before mutation, /health and /capabilities returned 200; /snapshot was READY with exp004-cpp-live, both arm and gripper controllers active, six fresh joints, TCP and Gazebo cup pose. Capabilities fixed the owner as so101_gazebo_demo_cpp/pick_place_state_machine.
  - The only workflow request was POST /workflow/start after acquiring its own lease. It returned 200/OK with a fresh run/checkpoint and the owner-produced trace IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT; the checkpoint recorded last_completed_state PREPARE_OPEN_GRIPPER, next_state MOVE_ABOVE_OBJECT, source_mode execute, and exp004-cpp-live.
  - Independent before/after telemetry measured joint 6 delta +0.46503919138831407 rad; joints 1-5 changed by at most 1.04e-7 rad, TCP translation by at most 2.02e-8 m, and cup translation by exactly 0.0 m. Arm/gripper controllers remained active.
  - Direct Gazebo Pose_V evidence kept plastic_cup at approximately (0.02, -0.28, 0.165) m and the SO-101 base at the world origin. MoveIt's WORLD_OBJECT_NAMES response changed from empty before the boundary to base_pedestal, plastic_cup, and table afterward, matching the owner checkpoint.
  - Active X11 window 0x4e0000e reported PID 2475560 and Gazebo Sim, correlating it to the EXP-004 Gazebo child tree. The ai-station-gui Skill produced a fresh 513295-byte desktop at gui/captures/20260811T184237-c21123761f88/desktop.png; visual inspection showed the owned foreground Gazebo with open gripper and the cup still supported on the table. Optional RViz belonged to a preserved stack and was not counted as EXP-004 evidence. The active window was restored to 0x4e0000e after capture.
  - After cleanup, every listed EXP-004 PID was absent and port 18104 was reusable. The only partition/session process match was the read-only audit shell matching its query text.
deviations:
  - The workflow-response harness expected layers.owner, but the stable API currently proves fixed package/executable provenance through /capabilities and returns the owner's parsed checkpoint/trace under data.workflow. The workflow was not rerun; the successful response and checkpoint were used as the owner-output evidence.
  - The first Skill post-processing pass retained the literal Manifest: prefix and stopped after capture. The existing fresh manifest was read and validated without repeating the screenshot action.
  - On the first live cleanup, Uvicorn completed shutdown but the Teleop child aborted because RosTelemetryWorker had no explicit executor/thread teardown. A RED lifecycle test reproduced the missing stop call; main now uses finally and the worker explicitly stops/join/releases its middleware resources. The test passes 4/4, and a fresh READ_ONLY installed launch on the emptied EXP-004 domain then exited cleanly with child exit 0.
  - The Jazzy move_group binary segfaulted inside its upstream destructor after SIGINT. This affected only the already-stopping EXP-004-owned process; it left no child and did not alter the successful pre-shutdown MoveIt evidence. No repository behavior was changed to mask that external teardown defect.
conclusion: The installed Gazebo C++ owner passed isolated Teleop connection and one-action single-step acceptance with mutually consistent backend, controller, joint/TF, Gazebo, MoveIt, checkpoint, and fresh visual evidence; the task-owned stack was fully removed.
next_command: Commit the lifecycle correction and current ledger, then plan the separate Gazebo Python acceptance on a new domain/partition.
```

## EXP-005 — Dedicated Gazebo Python Teleop single-step acceptance

```yaml
experiment_id: EXP-005
status: COMPLETE
hypothesis: Teleop from commit dd97ff1 connects to a separately owned Gazebo Python stack, selects only so101_gazebo_demo_py with its fixed --live-runtime adapter argument, and completes one Start/single-step boundary with independent runtime evidence.
source_commit: dd97ff1
branch: codex/so101-teleop-extraction
owner_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/setup.zsh
teleop_overlay: /data/work/ws_moveit/.worktrees/so101-teleop-extraction/install/setup.zsh
backend: gazebo_py
lifecycle: ISOLATED
isolation:
  ros_domain_id: 223
  gz_partition: so101_teleop_exp005_py_20260811
  port: 18105
  simulation_session_id: exp005-py-live
owned_processes: Exact child trees of new foreground Gazebo Python, MoveIt Python, and Teleop exec sessions; PIDs/window IDs will be appended after startup. Cleanup may interrupt only those owned sessions.
preserved_processes: physical-five-success Gazebo/RViz/move_group; other move_group; existing MuJoCo GUI and Python qualification stack; codex-cua and all other user/agent tmux sessions
motion_scope: One Teleop workflow Start request only. No subsequent Step/Run/Resume, reset, manual motion, attachment, scene mutation, camera control, or FULL_RESTART.
evidence_dir: /tmp/so101-debug-teleop-extraction-20260811/exp-005-gazebo-py-live
success_gate:
  - Dedicated Python stack exposes controller, joint/TF, Gazebo world/model, and MoveIt facts; Teleop reaches READY with exp005-py-live.
  - /capabilities names gazebo_py and so101_gazebo_demo_py/pick_place_state_machine, while scene_operations remains false.
  - Start creates a fresh owner checkpoint/trace and only the first workflow boundary is executed.
  - Independent before/after evidence records expected joint/TF effects, stable Gazebo cup facts, and MoveIt scene facts.
  - A fresh ai-station-gui desktop is correlated to the new EXP-005 Gazebo PID/window and visibly agrees with the numerical result.
  - Teleop exits cleanly through the dd97ff1 stop path; all EXP-005 PIDs disappear and port 18105 is reusable.
abort_gate: Any conflict with a preserved process/session/window, action beyond the single-step scope, inability to establish unambiguous installed owner provenance, or cleanup target outside the exact EXP-005 sessions.
owned_runtime:
  gazebo_launch_session: exec session 27278; launch PID 2499281; Gazebo 2499462 with GUI 2499481; robot_state_publisher 2499463; relay 2499630; bridge 2499715
  moveit_launch_session: exec session 68419; launch PID 2500457; move_group 2500534
  teleop_launch_session: exec session 29072; launch PID 2501004; server 2501063
  workflow_owner: so101_gazebo_demo_py/pick_place_state_machine PID 2502876, invoked by the Teleop server
observed_result:
  - Installed provenance and connection gates passed: Teleop resolved from the current overlay, the owner resolved from the so101-mujoco-ros2 installed overlay, /health and /capabilities returned 200, and /snapshot reached READY with exp005-py-live and both controllers active. Capabilities named gazebo_py/so101_gazebo_demo_py/pick_place_state_machine and kept scene_operations false.
  - The only mutation was one POST /workflow/start. The adapter invoked the exact fixed argv with --live-runtime, --mode execute, a unique checkpoint, --session-id exp005-py-live, and --step.
  - The owner opened joint 6 by +0.465037234690044 rad; joints 1-5 changed by at most 1.72e-7 rad, TCP by at most 5.59e-8 m, and the cup translation was 0.0 m in the last fresh Teleop snapshot.
  - The Gazebo child then received SIGINT and shut down while the Python owner waited on a 36-second arm trajectory. The owner ultimately exited 1 with LIVE_EXECUTE_FAILED because its ros2 action send_goal subprocess timed out after 56 seconds. Teleop returned HTTP 503/BACKEND_OPERATION_FAILED with the fixed owner package/executable and owner_failure_code, and no checkpoint was created; it did not report false success.
  - Teleop subsequently exited cleanly through the dd97ff1 worker teardown. The remaining owned MoveIt/Gazebo launch sessions were interrupted directly; every exact EXP-005 PID disappeared and port 18105 was reusable.
deviations:
  - The planned success gate was not met: the Python owner did not complete its single-step boundary, and the owned Gazebo GUI ended before a fresh Skill image could be captured. No reset, retry, detach, scene action, or additional workflow request was issued within EXP-005.
  - The Python owner stack began with gazebo_attached true and moveit_attached null. This was recorded as owner telemetry and was not treated as convergence or changed by Teleop.
  - As in EXP-004, the upstream Jazzy move_group binary segfaulted during its own SIGINT destructor. The Python relay also called rclpy.shutdown after its context was already stopped and exited 1 during cleanup. Both were confined to stopping EXP-005-owned processes and left no child.
conclusion: The Python selection, fixed argv, readiness, partial physical effect, and fail-closed error propagation are proven, but the live single-step and fresh visual gates are disproven for this exec-session attempt because the owned Gazebo child ended mid-command.
next_command: Plan one isolated retry with new IDs and task-owned tmux sessions so the long workflow/tool wait cannot share foreground signal handling with the Gazebo GUI session.
```

## EXP-006 — Gazebo Python single-step retry in task-owned tmux sessions

```yaml
experiment_id: EXP-006
status: COMPLETE
hypothesis: Keeping each Python stack component in a task-owned tmux session prevents the unexplained EXP-005 foreground Gazebo SIGINT, allowing the same single Start/--step request to complete and be captured visually without altering owner code.
source_commit: dd97ff1
branch: codex/so101-teleop-extraction
owner_overlay: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/setup.zsh
teleop_overlay: /data/work/ws_moveit/.worktrees/so101-teleop-extraction/install/setup.zsh
backend: gazebo_py
lifecycle: ISOLATED
isolation:
  ros_domain_id: 224
  gz_partition: so101_teleop_exp006_py_20260811
  port: 18106
  simulation_session_id: exp006-py-live
  tmux_sessions: so101-exp006-gazebo, so101-exp006-moveit, so101-exp006-teleop
owned_processes: Only the three newly named tmux sessions and their exact child trees. Cleanup may interrupt/kill only these names after process evidence is complete.
preserved_processes: Every pre-existing tmux session and process listed in prior experiments, including so101-py-qual and codex-cua
motion_scope: One workflow Start request only. No Step/Run/Resume/reset/manual/scene/attachment action; capture is screenshot-only.
evidence_dir: /tmp/so101-debug-teleop-extraction-20260811/exp-006-gazebo-py-tmux-retry
success_gate:
  - New stack reaches READY and fixed Python provenance/capabilities are unchanged.
  - One Start request exits with a fresh checkpoint/trace and no false-success or second request.
  - Independent numerical and scene facts plus a PID-correlated fresh Skill desktop agree with the result.
  - Teleop exits cleanly; all three task-owned tmux sessions are removed; port 18106 is reusable.
abort_gate: Any existing tmux name collision, signal/action affecting a pre-existing session, loss of fixed owner provenance, or need for a second workflow request.
owned_runtime:
  gazebo_tmux: so101-exp006-gazebo, pane leader 2510811; Gazebo GUI PID 2510970; robot_state_publisher 2510948; relay 2511044; bridge 2511205
  moveit_tmux: so101-exp006-moveit, pane leader 2513145
  teleop_tmux: so101-exp006-teleop, pane leader 2513156; server 2513323
observed_result:
  - All three task-owned tmux sessions started without a name collision. The stack reached READY with exp006-py-live, active controllers, and the same fixed gazebo_py owner/capabilities; active Gazebo window 0x4e0000e PID 2510970 belonged to the owned Gazebo tree.
  - The only workflow request used the exact installed Python owner argv with --live-runtime and --step. It returned HTTP 503/BACKEND_OPERATION_FAILED with owner_failure_code LIVE_EXECUTE_FAILED and created no checkpoint.
  - Unlike EXP-005, the isolated Gazebo, MoveIt, and Teleop sessions all stayed alive. The controller accepted the arm goal and then aborted it because joint 2 position error 0.008001 exceeded path tolerance 0.008000; ros2 action reported error_code -4 and ABORTED. This establishes a deterministic owner/controller failure rather than a Teleop routing or signal-lifecycle failure.
  - Independent before/after telemetry kept READY/controllers active. Joint deltas were approximately q1 -0.002766, q2 -0.003988, q3 +0.000421, q4 +0.010126, q5 +0.000192, q6 +0.465060 rad; TCP translated by at most 0.000939 m. The cup translated by (0.000608, 0.002403, 0.000208) m while the Python relay continued to report gazebo_attached true and MoveIt attached remained unknown; the MoveIt world-object-name query remained empty.
  - The ai-station-gui Skill produced a fresh 513440-byte desktop at gui/captures/20260811T190011-4252f72dffe4/desktop.png, restored active window 0x4e0000e, and visual inspection showed the owned foreground Gazebo with opened gripper and cup still visibly on the table. It is failure evidence, not a success claim. Optional preserved RViz was not counted.
  - Ctrl-C was sent only to the three exact task-owned tmux sessions. Their names disappeared, all active children ended, and port 18106 was reusable. The pre-existing tmux session list remained intact.
deviations:
  - The retry disproved the hypothesis that signal isolation alone would make the Python boundary pass. It removed the EXP-005 signal ambiguity and exposed the underlying controller tolerance failure.
  - Pane leaders 2510811 and 2513145 remain as terminated zombie entries parented by the shared tmux server PID 1843453, despite their sessions being gone. Zombies run no code and hold no port/device, but only their shared parent can reap them. Restarting/signaling that parent would interrupt the preserved codex, codex-cua, codex-teleop, kimi, physical, MuJoCo, and Python qualification sessions, so it is forbidden without new user approval and was not attempted.
conclusion: Gazebo Python installed selection and fail-closed behavior are proven with complete numerical/visual failure evidence, but live single-step success is not claimed: the current Python owner/controller aborts at its 8 mrad path-tolerance boundary.
next_command: Run the complete final build/test/Web/Skill/ownership verification, append a final checkpoint, commit the ledger, and publish the feature branch without modifying the Python owner worktree.
```

## CP-005 — Final verification and publication readiness

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-006
source_commit: dd97ff13f835f804cabe32dcb584dc615f249eb2
branch: codex/so101-teleop-extraction
working_tree_status: Only ledger appends EXP-005, EXP-006, and CP-005 are dirty; implementation and EXP-003/004 evidence are committed through dd97ff1.
owned_processes: NONE active
preserved_processes: codex, codex-cua, codex-teleop, kimi, so101-mujoco-gui, so101-phy5-v2-r0, and so101-py-qual tmux sessions and their stacks
verification:
  - colcon build --packages-select so101_gazebo_demo_cpp so101_teleop --symlink-install completed for both packages.
  - colcon test completed all 24 so101_teleop and 67 so101_gazebo_demo_cpp CTest entries; colcon test-result --verbose reported 1001 tests, 0 errors, 0 failures, and 8 skipped.
  - The Web package's declared Vitest entry passed 44 of 44 tests across 14 files; tsc -b and the Vite production build passed; Playwright passed 9 of 9 Chromium tests.
  - The ai-station-gui Skill passed 18 of 18 pytest tests, bash -n for its wrapper, and the official quick_validate.py validator.
  - Source ownership assertions proved no legacy Teleop tree, Web tree, or launch file remains in so101_gazebo_demo_cpp, and its CMake/package manifests contain no Teleop or tiler ownership reference.
  - git diff --check passed.
cleanup_audit:
  - No EXP-004/005/006 tmux session, isolated port 18104/18105/18106 listener, or active experiment process remained.
  - The preserved tmux session inventory was unchanged.
  - EXP-006 pane leaders 2510811 and 2513145 remain terminated zombies under shared tmux server PID 1843453. They execute no code and hold no port or device. Reaping them would require signaling or restarting the shared parent and would interrupt preserved agent/user sessions, so no such action was taken.
deviations:
  - A first Web verification used Bun's built-in `bun test`, which ignored the repository's Vitest environment and tried to mix Playwright and jsdom suites. This was a verification-entry error, not a product failure; the package-declared `bun run test` entry passed 44 of 44.
  - Playwright could not bind its loopback Vite server inside the restricted sandbox. The same package-declared test was rerun with approved host permission and passed 9 of 9.
confirmed_conclusions:
  - The standalone Teleop package, fixed backend profiles, extracted Web UI, C++ ownership boundary, and project-local ai-station-gui Skill satisfy their automated and installed-overlay gates.
  - Gazebo C++ live single-step acceptance passed with backend/controller/Gazebo/MoveIt/checkpoint/fresh-visual evidence.
  - MuJoCo remains honestly probe-only.
  - Gazebo Python routing and fail-closed propagation are proven, but live single-step success remains disproven by the independently observed joint-2 path-tolerance abort at 0.008001 versus 0.008000 rad.
open_boundary: The separate Mac robot_demo_001 owner migration must fetch the published feature commit, remove duplicate root capture code, update current root references, and advance the moveit-demo gitlink in its own branch/worktree.
next_command: Commit CP-005, push codex/so101-teleop-extraction to origin without force, and verify the remote branch SHA with git ls-remote.
```
