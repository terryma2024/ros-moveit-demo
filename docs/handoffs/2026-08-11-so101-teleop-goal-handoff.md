# SO-101 Teleop Extraction One-Shot Goal Handoff

## User directive

Continue this development task in the existing ai-station `codex-teleop` session as one `/goal`, execute inline from start to finish, and do not delegate to subagents.

At approval prompts, take the recommended safe in-scope action and continue. The user explicitly pre-approved those recommended actions, including publishing the validated feature branch when needed. The only approval exception is any action that would stop, kill, restart, interrupt, or take over a process/session created or owned by another Codex/agent: stop and ask the user before that action. Never force-push.

## Objective

Finish and verify the ai-station-owned portions of the approved standalone `so101_teleop` and `ai-station-gui` work, commit coherent checkpoints, and push the feature branch so the Mac parent repository can later advance its moveit-demo submodule to a remote-fetchable commit.

Do not attempt the Mac-only parent-repository worktree in `2026-08-11-robot-demo-capture-owner-migration.md` from ai-station. Report its exact required follow-up after the moveit-demo feature branch is pushed.

## Required execution mode

- Work inline in this Codex session; no subagents or parallel agent delegation.
- Use `/goal` persistence until the objective above is achieved or a genuine user-only blocker is reached.
- Use the repository Skills required by the task, especially `so101-dev`, `superpowers:executing-plans`, `superpowers:test-driven-development`, and `superpowers:verification-before-completion`.
- Keep the user updated at meaningful checkpoints.
- Use `apply_patch` for edits.
- Preserve unrelated changes and all other worktrees.

## Worktree and branch

```text
workspace: /data/work/ws_moveit/.worktrees/so101-teleop-extraction
branch: codex/so101-teleop-extraction
base: c6982116d79c834de60b21d9e324a449a569a9c9
current HEAD at handoff: 511c168
```

Recent commits:

```text
511c168 feat: define immutable Teleop backend profiles
ea18148 docs: checkpoint standalone Teleop extraction
b95432c refactor: extract standalone SO101 Teleop package
58cd719 docs: checkpoint shared X11 ownership decision
a54598f test: lock standalone Teleop ownership
132cec4 docs: checkpoint Teleop execution constraints
3cba80f docs: plan standalone Teleop implementation
98f8bde docs: design standalone SO101 Teleop adapters
```

## Current dirty state: intentional Task 4 GREEN candidate

Exactly these files should be dirty when this handoff starts:

```text
M  src/so101_teleop/CMakeLists.txt
?? src/so101_teleop/so101_teleop/backends/cli_adapter.py
?? src/so101_teleop/test/backends/test_cli_adapter.py
?? docs/handoffs/2026-08-11-so101-teleop-goal-handoff.md
```

The CLI adapter work already followed RED then GREEN:

- RED: `ModuleNotFoundError: so101_teleop.backends.cli_adapter`
- GREEN: `8 passed` for `test_cli_adapter.py`
- Regression: backend + Teleop suites `96 passed, 3 warnings`

Before editing, inspect the diff and rerun those tests. If equivalent, commit Task 4 as `feat: add fail-closed installed CLI adapter`. The handoff document can be committed with the next ledger/documentation checkpoint.

## Approved plans to execute

Read fully and follow:

1. `docs/superpowers/plans/2026-08-11-so101-teleop-package-backends.md`
2. `docs/superpowers/plans/2026-08-11-ai-station-gui-skill-capture.md`
3. Read `docs/superpowers/plans/2026-08-11-robot-demo-capture-owner-migration.md` only to understand the publication boundary and Mac follow-up; do not execute its local parent-repository edits on ai-station.

The approved design is `docs/superpowers/specs/2026-08-11-so101-teleop-standalone-backend-adapters-design.md`.

## Already completed; do not redo

- Standalone package exists at `src/so101_teleop`.
- Old C++ Teleop launch was deleted; no compatibility wrapper exists.
- Web/backend/config/docs/tests were moved from C++ to the standalone package.
- `tile_ai_station_guis.py`, `gazebo_window_recorder.py`, `so101_stack_inventory.py`, their tests, and the single X11 implementation were moved into `so101_teleop` per the user's option 1.
- C++ Teleop/Bun/Python/X11 ownership and direct-only dependencies were removed.
- Launch requires explicit `backend`; the intermediate checkpoint only accepts `gazebo_cpp` until registry injection is complete.
- Installed ownership was verified: `so101_teleop` exposes server, tiler, recorder, and inventory; C++ exposes robot owners only.
- Immutable profiles and fixed registry exist for `gazebo_cpp`, `gazebo_py`, and probe-only `mujoco_py`.
- `gazebo_py.scene_operations=false` is deliberate because its current scene CLI lacks Teleop `upsert`.
- `mujoco_py` must remain probe-only; executable presence is not live capability.

Verified evidence before the adapter checkpoint:

```text
GUI/ownership/launch source tests: 82 passed
migrated Teleop source tests: 81 passed
Web Vitest: 38/38
installed so101_teleop colcon test: 182 tests, 0 errors, 0 failures, 0 skipped
so101_teleop build: passed
pick_place_common build: passed
so101_gazebo_demo_cpp build: passed
C++ package layout: 7 passed
profile + Teleop regression after Task 3: 93 passed
```

## User decisions and hard constraints

- Explicit backend only: `gazebo_cpp|gazebo_py|mujoco_py`; no auto-detection, fallback, or runtime switching.
- Robot workflow/reset/scene/physics remains in the corresponding ROS module. Teleop owns the control plane and fixed adapter only.
- Web/API input must never select a package, executable, shell command, environment key, argument template, or profile path.
- Unsupported operations fail before run/checkpoint/subprocess creation with `BACKEND_CAPABILITY_UNAVAILABLE`.
- `subprocess.run(argv, shell=False)` only; sanitized bounded diagnostics under `/tmp/so101-teleop/<session>/`.
- No old entrypoints or wrappers.
- Capture contract: a fresh full desktop is required; RViz and Ghostty may both be absent. In that case emit a valid manifest and exit 0.
- The long-term Skill owner is moveit-demo `.agents/skills/ai-station-gui/`, not the parent `robot_demo_001` Skill.
- Skill routing must first check whether the live Codex/Claude/Kimi agent has a healthy loaded `cua-driver`; prefer healthy agent+CUA for screenshot/control. Script fallback is screenshot-only.
- A local ai-station agent never SSHes to ai-station itself.
- CUA interaction is `snapshot -> action -> fresh snapshot`; never reuse stale element indices.
- Do not rewrite historical specs, plans, handoffs, or experiment ledgers. Append new ledger checkpoints; update only current operator docs/Skills.
- Use `RESET_WORLD` for reset-required validation. Never use `FULL_RESTART`.
- Do not count old attach-based Teleop/C++ stability evidence toward Gazebo physical-contact five-success.

## Runtime ownership and safety

Preserve these known user/agent stacks unless a fresh read-only inventory proves they ended naturally:

```text
physical five-success Gazebo: 580035, 580038, 580060, 580061
physical five-success move_group: 581537
other move_group: 2049562
tmux: codex, codex-cua, codex-teleop, kimi,
      so101-mujoco-gui, so101-phy5-v2-r0, so101-py-qual
```

Do not stop or repurpose them. `codex-cua` was previously observed and must not receive keys if busy. Never kill another Codex/agent process without new user approval.

One earlier direct C++ launch-contract test unexpectedly started a temporary headless Gazebo pair `2290778/2290780`; the test cleaned it. The ledger records the deviation. Do not rerun that whole file casually. Before any new stack/reset/workflow/GUI action/live capture, add a `PLANNED` experiment entry to `docs/experiments/so101-teleop-extraction-experiment-ledger.md`, select an unused ROS domain/partition, and record owned PIDs/session. Automated unit/build tests are not permission to reuse the physical-five-success stack.

## Remaining ai-station work

1. Re-verify and commit the dirty CLI adapter Task 4.
2. Inject the fixed backend adapter into service/main/launch and enforce capability gates before side effects.
3. Characterize exact Gazebo Python argv and keep scene repair unavailable.
4. Lock MuJoCo probe-only behavior.
5. Make Web UI capability-driven; regenerate OpenAPI/schema; run Vitest/build/E2E.
6. Finish ownership/documentation scans and both-package build/test gates. Account for nonzero test counts.
7. Implement `.agents/skills/ai-station-gui` via TDD, including desktop-only no-window success and safe local/remote wrapper.
8. Route current moveit-demo Skills/docs to the new owner and new `so101_teleop` tiler command.
9. Perform live acceptance only under a PLANNED isolated lifecycle. If a required stack would conflict with an existing agent-owned process, stop and ask rather than killing it. Use RESET_WORLD only.
10. Update the experiment ledger with exact commits, tests, runtime provenance, owned-process cleanup, confirmed/disproven conclusions, and remaining boundaries.
11. Run verification-before-completion, commit coherent changes, and push `codex/so101-teleop-extraction` to its configured remote. The user's current instruction explicitly approves the recommended feature-branch publication needed for the parent submodule update. Do not force-push and do not merge/push a default branch unless a plan explicitly requires it and every gate is green.
12. Report the remote branch/SHA and the Mac-only parent migration follow-up; do not claim the parent repo was changed from ai-station.

## Completion contract

The goal is complete only when:

- worktree source and installed overlays agree;
- backend profiles, adapter, API/service, and UI capability gates are covered by automated tests;
- C++ and Gazebo Python select only their own installed owners;
- MuJoCo reports probe-only without fake live success;
- standalone package, C++ package, Web, Skill, wrapper, and ownership scans pass with nonzero test counts;
- live actions, if performed, have backend/controller/Gazebo/MoveIt/fresh visual evidence and use RESET_WORLD only;
- all task-owned temporary processes are cleaned without touching other stacks;
- ledger is current;
- feature branch is committed and pushed, and remote SHA is read back;
- remaining Mac parent-repository migration is stated accurately rather than marked complete.
