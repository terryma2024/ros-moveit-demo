# SO-101 pick/place CP31B — Codex continuation handoff

Updated: 2026-07-29

## Mission

Continue the SO-101 Gazebo + MoveIt demo until one complete, visually verified
pick-close-attach-lift-place-detach-retreat run succeeds. Qoder quota is exhausted;
do not use Qoder. Work in this repository and supervise the single owned runtime
stack on ai-station.

Read completely before acting:

- `/data/work/ws_moveit/AGENTS.md`
- `/data/work/ws_moveit/src/so101_gazebo_demo/AGENTS.md`
- `/data/work/ws_moveit/.agents/skills/so101-dev/SKILL.md`
- every reference required by that skill

Inspect current files, diff, live PIDs/tmux windows, and retained logs before
editing. Preserve the large dirty worktree and all unrelated/user changes.

## Git and recovery state

- Branch: `codex/direct-tpu-tongues`
- HEAD after rebase: `c687a02d288b3cbde250b0da60ba999019fca0cd`
- Rebased onto `origin/main` `f364f679a946c6344b85af82aba4d03145fb187d`
- Protected pre-rebase stash: `stash@{0}` / `0e89b8de62318bc4cab8002b7b51498466bd223b`
  (`cp31b-pre-rebase-2026-07-29T05:11:17Z`). Never pop or drop it.
- Recovery evidence:
  - `/tmp/so101-debug-cp31b-recover-20260729T051605Z`
  - `/tmp/so101-debug-cp31b-full-recovery-20260729T052701Z`
- Runtime graph files `frames_*.gv/pdf` are artifacts and must not be committed.

Restored policy hashes:

- motion: `c1c123b7c7e3fcf6d2188ab1133a9cdbfc40eeec227a50f59a7e474a5d457279`
- validation: `6dbbe602e2f57ef39ad747d7ad924281e8d71f06d5880d29198dc9576ab248c6`
- CP31B includes a 4 mm retreat waypoint.

The older `so101-pick-place-qoder-handoff.md` ends at CP29 and is historical;
this document supersedes its stop point.

## Verified completed work

### Model preparation and cup visibility

- `prepare_simulation_model.py` supports manifest/object config, fail-closed
  validation, caching, relative manifest paths, and robust Gazebo lump matching.
- Focused prepare-model tests: 17/17.
- Prepared SDF has 15 convex-hull markers: 7 fixed and 8 moving.
- Launch contract test passes.
- Cup is warm orange in `worlds/so101_pick_place.sdf`, all 13 visual materials:
  ambient `0.75 0.30 0.05 1`, diffuse `1.0 0.55 0.12 1`, specular
  `0.20 0.20 0.20 1`.
- Static color test passed; installed world contains all 13 orange materials.
- Still required: a fresh GUI screenshot proving inner/outer wall and rim clarity.

### Live-test reliability

- The joint/controller smoke test retries until controller-reference acceptance
  and emits richer failure diagnostics; its CTest timeout is 300 s.
- Focused live test passed twice from zero relevant processes: 56.90 s and
  53.47 s.
- Latest full package gate passed 41/41 after scene-bootstrap corrections.

### MoveIt scene bootstrap

- First CP31B `stop_after:=DESCEND` failed with
  `JOINT_EVIDENCE_INCOMPLETE`; a runtime-only retry then exposed missing initial
  planning-scene objects.
- Root cause: production launch constructed `MoveItSceneAdapter` but had no
  initial scene owner.
- New `MoveItSceneInitializer` is implemented, tested, wired, and validates
  exact five-arm-joint evidence plus separate q6 gripper fields, finite values,
  configured table/pedestal/task poses, and detached task in the world.
- Focused initializer test binary has 17 cases.
- Initialization failures now trace `BOOTSTRAP -> ERROR`.

## Current first bad boundary

Latest full CP31B passed BOOTSTRAP, then failed:

```text
IDLE -> PREPARE_OPEN_GRIPPER -> ERROR
failure=ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION
```

Evidence: `/tmp/so101-debug-cp31b/green2-launch.log`.

On a stable stack, positions were below `1e-5`, velocities below `1e-8`, and a
runtime-only run passed that boundary but failed at
`GAZEBO_TASK_OBJECT_POSE_UNAVAILABLE`.

Evidence: `/tmp/so101-debug-cp31b/ab-green02-runtime.log`.

Observed interpretation: full launch has an arm-settling startup race, and a
new `GazeboWorldObserver` has a DDS/fresh-data startup race. Do not relax motion
or validation thresholds to hide either race.

## Incomplete Qoder work: finish first

Qoder created but did not finish:

- `include/so101_gazebo_demo/pick_place/world_readiness_gate.hpp`
- `src/pick_place/world_readiness_gate.cpp`

Inspect these files rather than assuming correctness. The intended gate is after
`GazeboWorldObserver` construction and before `StateMachineRunner`. It may retry
only bounded, explicit startup-transient errors:

- `ROBOT_STATE_CHANGED_DURING_MOVEIT_OBSERVATION`
- `GAZEBO_TASK_OBJECT_POSE_UNAVAILABLE`
- `GAZEBO_ATTACHMENT_STATE_UNAVAILABLE`

A successful snapshot must be fresh, arm-stationary, contain a finite Gazebo
task pose and attachment state, and match the simulation session ID.
Non-transient failures must fail immediately.

Next implementation steps:

1. Review the two partial gate files and adjacent observer/runner contracts.
2. Add `test/pick_place/test_world_readiness_gate.cpp` with a fake observer:
   transient motion then success; delayed pose/attachment then success; timeout;
   wrong session/fresh=false/nonfinite pose; non-retryable immediate failure.
3. Add source/test targets to CMake and wire the gate at the production boundary.
4. Build, source the installed overlay, and prove executable provenance.
5. Run focused tests, then the full package suite (expected test count 42).

## Runtime and visual acceptance ladder

Before experiments, preserve needed logs and stop only explicitly identified,
owned ROS/Gazebo/MoveIt PIDs. Do not use broad `pkill`. Reuse tmux
`so101-moveit`; run only one stack. GUI launches must run in tmux after:

```bash
source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/install/setup.zsh
```

Use a unique ROS domain (<=232), GZ partition, simulation session ID, and
checkpoint. First run one GUI `stop_after:=DESCEND` checkpoint. Require:

- controller/action result and joint/TCP movement evidence;
- cup drift and fingertip/cup penetration <= 0.8 mm;
- no CLOSE/attach action;
- fresh Gazebo + RViz screenshot inspected visually.

Then tear down cleanly and run one full GUI execute cycle. Do not claim success
until all are proven together:

1. state-machine/controller result;
2. joint and TF/TCP motion;
3. Gazebo cup pose and attachment through close/lift/place/detach;
4. MoveIt world/attached-object membership;
5. final upright pose/table clearance and retreat;
6. fresh tiled CUA screenshots, including visible orange cup rim/interior/exterior.

Capture via the project `scripts/capture-ai-station.sh` workflow and actually
inspect the image. API/log success alone is insufficient.

## Operating rule

Use hypothesis -> provenance -> minimal A/B -> RED/GREEN -> fresh visual
acceptance. At the first failed boundary, retain evidence and change one
variable. Continue autonomously until the whole pick/place task passes, unless
new authority or unavoidable user input is required.
