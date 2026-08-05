# Pick/place launch parameters

> Safety: these launch surfaces are simulation-only. Do not point them at real
> robot controllers or reuse a ROS domain/Gazebo partition owned by another stack.

## Modes and side effects

| Mode | Robot motion | Gazebo / Planning Scene | Checkpoints and recovery |
|---|---|---|---|
| `dry_run` | None | None | No persisted checkpoint; injected failures only model the trace |
| `plan_only` | Real predecessors execute; the named target is planned but never executed | Predecessor attachment/scene actions really occur | Predecessors write execute/FORWARD checkpoints and can recover; the target writes no completion checkpoint |
| `execute` | Full execution | Full attachment and scene mutation | Schema-v3 checkpoints and normal recovery |

Run-to-plan-only is not side-effect-free: every predecessor before the named
target really executes. Only the named target executor and its postcondition are
skipped.

## Approved plan-only targets

The exact whitelist for both robots is `MOVE_ABOVE_OBJECT`, `DESCEND`, `LIFT`,
`MOVE_ABOVE_PLACE`, `DESCEND_TO_PLACE`, and `RETREAT`. Recovery workflow states
are excluded from plan-only.

| Target | Predecessor stages that execute first |
|---|---|
| `MOVE_ABOVE_OBJECT` | `PREPARE_OPEN_GRIPPER` |
| `DESCEND` | Through `MOVE_ABOVE_OBJECT` |
| `LIFT` | Through close-gripper and Gazebo/MoveIt attach stages (plus SO-101 grasp-stability stages) |
| `MOVE_ABOVE_PLACE` | Through `LIFT` |
| `DESCEND_TO_PLACE` | Through `MOVE_ABOVE_PLACE` |
| `RETREAT` | Full release, detach, and world-sync path through `SYNC_WORLD_OBJECT` |

## Common request controls

| Control | Default | Meaning |
|---|---|---|
| Panda `mode` / SO-101 `run_mode` | `execute` / `dry_run` | Selects the mode above |
| `plan_only_state` | empty | Required only for `plan_only`; one exact whitelist value |
| `stop_after` | empty | Execute/dry-run checkpoint boundary; must name any nonterminal action in the workflow and is never a plan-only target |
| `fail_at` | empty | Dry-run failure injection; must name a forward action in the workflow |
| `resume` | `false` | Load a compatible checkpoint; requires the same explicit session ID |
| `checkpoint_path` | `/tmp/panda_pick_place_checkpoint.json` or `/tmp/so101_pick_place_checkpoint.json` | Schema-v3 checkpoint file |
| `simulation_session_id` | empty | Generated for fresh executable modes; mandatory and unchanged for resume |
| SO `planning_diagnostics_dir` | empty | Opt-in micro-lift planning-failure artifacts; for example `/tmp/so101-r3-planning-diagnostics/artifacts` |
| `max_state_transitions` | Panda `100` | Positive transition safety bound (SO-101 CLI uses its runtime default) |
| SO CLI `--step` | off | Execute-resume single-step control |
| SO CLI `--force-continue` | off | Only valid for execute resume |

## SO-101 physical validation and validation-pause resume

SO-101 planning diagnostics are disabled by default. When enabled, the absolute
directory is created with mode `0700` and artifacts with mode `0600`. Artifacts
are written only for request-scoped micro-lift planning failures; successful
planning emits none. Writer failures preserve the original planning failure.
These artifacts do not alter checkpoint or resume semantics, are retained until
the operator removes them, and can be inspected with the test-only, non-installed
plan-only replay harness. A matching replay may still produce a different
stochastic planner outcome and never executes a trajectory.

Before Gazebo attachment, SO-101 always executes the physical chain
`WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP`.
Only a validator postcondition may take `VERIFY_PHYSICAL_GRASP -> VALIDATION_FAILED`.
The evidence is stored robot-locally at `checkpoint_path + ".physical-grasp.json"`,
bound to the simulation session and policy-bundle fingerprint. A fresh run removes
prior sidecar evidence; continuous execution and subprocess-per-step execution use
the same persisted samples and therefore the same validation result.

A physical validation failure produces a FORWARD checkpoint at
`VALIDATION_FAILED` retaining the original failure. A normal execute resume is
side-effect-free at that checkpoint: it reports the same validation pause and
leaves checkpoint bytes unchanged. `--force-continue` is execute-resume only,
may consume that declared pause once, and proceeds only through its declared
succeeded edge. Any other checkpoint is rejected with
`FORCE_CONTINUE_STATE_MISMATCH` before observation or action side effects.

Deep plan-only paths do not bypass physical validation: they must pass it
naturally before an attachment predecessor can run. Set `RunRequest` extension
fields by name (`single_step`, `force_continue`, and `plan_only_state`) so older
positional aggregate initializers retain their historical meaning. The common
runner is declaration-driven; Panda declares no force-continue state.
The retired Panda `attach_and_lift_demo` is no longer an installed entry point.

## Invalid plan-only requests

| Condition | Stable code |
|---|---|
| Missing target | `PLAN_ONLY_STATE_REQUIRED` |
| Target outside the whitelist | `PLAN_ONLY_STATE_NOT_ALLOWED` |
| Target unreachable on the forward path | `PLAN_ONLY_STATE_UNREACHABLE` |
| Target supplied outside plan-only, or combined with `stop_after`/single-step | `PLAN_ONLY_ARGUMENT_CONFLICT` |
| Resume checkpoint is already downstream of the target | `PLAN_ONLY_TARGET_ALREADY_PASSED` |
| Resume checkpoint is in recovery phase | `PLAN_ONLY_RECOVERY_RESUME_UNSUPPORTED` |

## Invalid control states

| Condition | Stable code |
|---|---|
| `stop_after` is idle, terminal, or otherwise not an action state | `STOP_AFTER_STATE_NOT_ACTION` |
| `fail_at` is terminal, recovery, or otherwise not a forward action state | `FAIL_AT_STATE_NOT_FORWARD_ACTION` |

## Panda launch arguments

The values below match installed `panda_gazebo.launch.py --show-args`.

| Group | Arguments and defaults |
|---|---|
| Lifecycle | `headless=false`, `run_state_machine=false`, `mode=execute`, `resume=false`, `stop_after=''`, `plan_only_state=''`, `simulation_session_id=''`, `checkpoint_path=/tmp/panda_pick_place_checkpoint.json`, `max_state_transitions=100` |
| Motion planning | `velocity_scaling=0.10`, `acceleration_scaling=0.10`, `cartesian_eef_step=0.005`, `cartesian_min_fraction=0.99`, `joint_jump_threshold=0.20`, `motion_start_joint_tolerance=0.010` |
| Tolerances | `tcp_position_tolerance=0.020`, `tcp_orientation_tolerance_rad=0.0872665`, `coke_position_tolerance=0.010`, `coke_orientation_tolerance_rad=0.0872665`, `joint_velocity_tolerance=0.010` |
| Gripper | `gripper_open_position=0.040`, `gripper_open_min_position=0.038`, `gripper_close_position=0.000`, `gripper_grasp_min_position=0.028`, `gripper_grasp_max_position=0.037`, `gripper_symmetry_tolerance=0.003`, `gripper_max_effort=0.0`, `gripper_action_timeout_seconds=5.0` |
| Gazebo/attachment | `attachment_timeout_seconds=2.0`, `planning_scene_timeout_seconds=2.0`, `state_poll_interval_seconds=0.05`, `gazebo_observation_max_age_seconds=0.5`, `coke_settle_samples=5`, `coke_settle_interval_seconds=0.05`, `coke_settle_position_tolerance=0.002`, `coke_settle_orientation_tolerance_rad=0.020` |
| Recovery | `recovery_safe_height=0.987` |

Gazebo also exposes `gz_args=''`, `gz_version=8`, the deprecated ignition
aliases, and debugger/shutdown controls from its included launch.

## SO-101 launch arguments

| Group | Arguments and defaults |
|---|---|
| Runtime | `run_mode=dry_run`, `start_simulation=false`, `headless=false` |
| Lifecycle | `stop_after=''`, `plan_only_state=''`, `resume=false`, `checkpoint_path=/tmp/so101_pick_place_checkpoint.json`, `simulation_session_id=''` |
| Policies | installed `light_plastic_cup.yaml`, `light_cup_wall_pick.yaml` motion policy, and `light_cup_wall_pick.yaml` validation policy |

The included simulation additionally exposes the installed model/world,
`base_height=0.1899186`, and Gazebo/MoveIt arguments.

## Commands

Fresh Panda target:

```bash
ros2 launch panda_gazebo_demo panda_gazebo.launch.py run_state_machine:=true mode:=plan_only plan_only_state:=MOVE_ABOVE_OBJECT simulation_session_id:=panda-plan-1
```

Fresh SO-101 target:

```bash
ros2 launch so101_gazebo_demo so101_pick_place.launch.py start_simulation:=true run_mode:=plan_only plan_only_state:=MOVE_ABOVE_OBJECT simulation_session_id:=so101-plan-1
```

`LIFT` is a deep target: opening, approach, descent, grasp, and attachment
predecessors physically execute before only `LIFT` is withheld.

```bash
ros2 launch panda_gazebo_demo panda_gazebo.launch.py run_state_machine:=true mode:=plan_only plan_only_state:=LIFT simulation_session_id:=panda-lift-1
```

Resume a forward target with exactly the same checkpoint, session, and target:

```bash
ros2 launch panda_gazebo_demo panda_gazebo.launch.py run_state_machine:=true mode:=plan_only plan_only_state:=LIFT resume:=true checkpoint_path:=/tmp/panda_pick_place_checkpoint.json simulation_session_id:=panda-lift-1
```

After a successful deep target plan, either resume in `execute` mode to finish
from the checkpoint, or run the robot-specific explicit reset workflow. Do not
assume plan-only restored the initial world.

## Diagnostics

| Symptom | First checks |
|---|---|
| Request rejected | Mode/target whitelist and conflicting `stop_after`, step, or `fail_at` |
| SO-101 q6/grasp failure | Observed q6, contact threshold, installed object/motion/validation policy provenance |
| Physical evidence failure | Sidecar schema/session/fingerprint and both persisted stable samples |
| Checkpoint/session failure | Schema version 3, phase, fingerprint/hash, identical explicit session ID |
| MoveIt plan failure | `/move_group`, current joint state, start tolerance, target policy and collision scene |
| Attachment failure | Durable Gazebo attachment topic and exclusive MoveIt world/attached membership |
| Duplicate stack | ROS domain, `GZ_PARTITION`, owning tmux session and PIDs before launching |

## Provenance and live evidence

```bash
ros2 pkg prefix panda_gazebo_demo
ros2 pkg prefix so101_gazebo_demo
command -v ros2
printf '%s\n' "$AMENT_PREFIX_PATH"
ps -eo pid,ppid,lstart,args | rg 'gz sim|move_group|controller_manager|pick_place'
ros2 node list
gz topic -e -t /panda/coke_attached -n 1
ros2 service call /get_planning_scene moveit_msgs/srv/GetPlanningScene '{components: {components: 28}}'
```
