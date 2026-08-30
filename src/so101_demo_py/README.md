# SO-101 Unified Python Demo

`so101_demo_py` is the ROS 2 package and runtime-resource owner for the SO-101
MuJoCo and Gazebo pick-place demos. The installed package name is
`so101_demo_py`; its Python import namespace is `so101_demo`.

This README is the operator-facing index for the package. It explains which
workflow to choose, how to start every launch file and executable, which safety
gate applies, and where to find the detailed architecture and source guides.

## Choose a workflow

| Goal | Recommended entry point | What it proves | Detailed guide |
|---|---|---|---|
| Start MuJoCo, controllers, MoveIt, and the Planning Scene | `so101_mujoco.launch.py` | Stack readiness only | [Launch parameters](../../docs/pick-place-launch-parameters.md) |
| Run the fixed-waypoint cup workflow | `so101_mujoco_pick_place.launch.py` | Fixed policy planning or execution | [Python architecture](../../docs/pick-place-python-architecture.md) |
| Consume a supplied `/cup_pose` | `dynamic_cup_pick_place` | Dynamic target calculation and planning/execution | [Dynamic cup source guide](../../docs/so101-dynamic-cup-pick-place-source-guide.md) |
| Detect the cup from RGB-D and pick it | `so101_mujoco_perception_pick_place` | Camera-to-pose-to-motion integration | [RGB-D source guide](../../docs/so101-rgbd-perception-pick-place-source-guide.md) |
| Convert natural language into a bounded cup task | `text_pick_agent` | Planner validation and, when authorized, dispatch | [Text Pick Agent source guide](../../docs/so101-text-pick-agent-source-guide.md) |
| Keep one visible MuJoCo environment alive for multiple points | `so101_mujoco_task_station.launch.py` or `so101_mujoco_rgbd_batch` | `RESET_WORLD` task-station workflow | [RGB-D task-station guide](../../docs/so101-rgbd-perception-pick-place-source-guide.md) |
| Compare the shared workflow on Gazebo | `so101_gazebo_pick_place.launch.py` | Functional comparison, not MuJoCo qualification | [Shared architecture](../../docs/pick-place-architecture.md) |

## Quick start and installed-runtime provenance

Build from the repository root, source the exact overlay you intend to run,
and confirm that ROS 2 discovers the installed package:

```bash
colcon build --packages-select so101_demo_py
source install/setup.zsh

ros2 pkg prefix so101_demo_py
ros2 pkg executables so101_demo_py | sort
ros2 launch so101_demo_py so101_mujoco.launch.py --show-args
```

Use `install/setup.bash` instead of `install/setup.zsh` in Bash. A source file
appearing in the checkout does not prove that `ros2 run` will execute it:
console scripts and launch resources are resolved from the selected install
overlay. Rebuild and source the candidate overlay whenever the reported prefix
or executable list is stale.

Create a unique evidence root for each task. Ordinary low-rate development
evidence belongs under `/tmp/so101-debug-<task-id>/`:

```bash
export SO101_EVIDENCE_ROOT=/tmp/so101-debug-readme-example-001
mkdir -p "$SO101_EVIDENCE_ROOT"
```

Do not reuse a session ID, evidence stem, or exclusive capture directory from
an earlier run.

## Runtime dataflow

The main perception-driven path is:

```text
launch owner
  -> MuJoCo ros2_control node
  -> joint_state_broadcaster + arm_controller + gripper_controller
  -> MoveIt move_group + canonical Planning Scene
  -> /task_camera/{camera_info,color,depth}
  -> rgbd_cup_pose
  -> source-stamped world /cup_pose
  -> dynamic_cup_pick_place
  -> MoveIt plans and controller goals
  -> MuJoCo physics and lossless outcome evidence
```

`text_pick_agent` adds a bounded planning layer in front of the same dynamic
runtime. The model may propose only the closed `TaskCommand`; fixed Python code
validates, authorizes, claims, and dispatches it.

## Launch-file catalog

The package installs six launch files.

| Launch file | Purpose | Safe default | Typical use |
|---|---|---|---|
| `so101_mujoco.launch.py` | MuJoCo stack without a pick-place workflow | `headless:=true` | Bring up simulator, controllers, MoveIt, and scene ownership |
| `so101_mujoco_pick_place.launch.py` | MuJoCo stack plus fixed-waypoint workflow | `run_mode:=dry_run execute:=false` | Fixed-policy dry-run or explicitly authorized execution |
| `so101_mujoco_perception_pick_place.launch.py` | MuJoCo stack, RGB-D perception, and dynamic workflow | `run_mode:=dry_run execute:=false` | Full RGB-D integration; prefer the status-preserving executable for automation |
| `so101_mujoco_task_station.launch.py` | Persistent visible RGB-D task station | Visible viewer and sensor rendering are mandatory | Manual observation, Teleop task page, and attached batch runs |
| `so101_gazebo.launch.py` | Gazebo stack without a workflow | `headless:=true` | Gazebo readiness and operator-command testing |
| `so101_gazebo_pick_place.launch.py` | Gazebo stack plus shared fixed workflow | `run_mode:=dry_run execute:=false` | Functional comparison; not a qualification backend |

### Stack-only launches

Start a visible MuJoCo stack:

```bash
ros2 launch so101_demo_py so101_mujoco.launch.py \
  headless:=false \
  sensor_rendering:=true \
  session_id:=mujoco-stack-001
```

Start the Gazebo stack:

```bash
ros2 launch so101_demo_py so101_gazebo.launch.py \
  headless:=false \
  session_id:=gazebo-stack-001
```

Stack-only launches do not claim that a pick-place task ran successfully.

### Fixed-waypoint pick-place launches

Inspect the MuJoCo request without live execution:

```bash
ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py
```

Live simulation requires both execution controls:

```bash
ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py \
  run_mode:=execute \
  execute:=true \
  session_id:=fixed-mujoco-001 \
  evidence_file:="$SO101_EVIDENCE_ROOT/fixed-mujoco-001.json"
```

Use the Gazebo variant by changing only the launch file and session/evidence
identity:

```bash
ros2 launch so101_demo_py so101_gazebo_pick_place.launch.py \
  run_mode:=execute \
  execute:=true \
  session_id:=fixed-gazebo-001 \
  evidence_file:="$SO101_EVIDENCE_ROOT/fixed-gazebo-001.json"
```

Gazebo reports the shared phase at which planning or control succeeds or
fails. It does not provide the lossless physics-step evidence required by the
MuJoCo qualification gate.

### RGB-D perception launch

For terminal automation, use the console wrapper because it preserves the
terminal child failure status:

```bash
ros2 run so101_demo_py so101_mujoco_perception_pick_place \
  run_mode:=execute \
  execute:=true \
  headless:=false \
  session_id:=rgbd-task-start-001 \
  mujoco_initial_keyframe:=task_start \
  evidence_file:="$SO101_EVIDENCE_ROOT/rgbd-task-start-001.json"
```

The equivalent launch file remains useful for interactive launch inspection:

```bash
ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py \
  run_mode:=execute \
  execute:=true \
  session_id:=rgbd-interactive-001 \
  evidence_file:="$SO101_EVIDENCE_ROOT/rgbd-interactive-001.json"
```

The integrated graph starts the dynamic consumer before accepting a cup pose,
starts perception only after scene setup succeeds, and fails closed if a
required long-lived component exits early.

### Persistent task station

```bash
ros2 launch so101_demo_py so101_mujoco_task_station.launch.py \
  session_id:=task-station-001 \
  task_evidence_root:="$SO101_EVIDENCE_ROOT/task-station" \
  include_teleop:=true \
  teleop_port:=8080
```

This launch already owns MuJoCo, robot-state publication, controllers, MoveIt,
Planning Scene setup, camera TF, and the optional Teleop server. Do not start a
second owner for any of those components in the same ROS domain. The task page
is available at `http://127.0.0.1:8080/tasks` when Teleop is enabled.

### Common launch arguments

| Argument | Default | Meaning |
|---|---|---|
| `run_mode` | `dry_run` | `dry_run` or `execute`; workflow launches only |
| `execute` | `false` | Second, independent live-execution authorization |
| `headless` | `true` on generic launches | Viewer visibility; it is independent of sensor rendering |
| `policy_id` | `light_cup_wall_pick` | Registered fixed-motion policy |
| `policy_version` | `v1` | Frozen policy version |
| `session_id` | Generated unique value | Correlation identity for simulator, reset, workflow, and evidence |
| `evidence_file` | Unique file under `/tmp` | Top-level result anchor; detailed artifacts use a sibling `.d` directory |
| `readiness_timeout_s` | `90.0` | Stack readiness deadline |

MuJoCo generic launches additionally accept `sensor_rendering` (`auto`,
`true`, or `false`), `mujoco_scene`, and `mujoco_initial_keyframe`. The four
installed keyframes are:

- `task_start`
- `cup_test_forward_5cm`
- `cup_test_left_5cm`
- `cup_test_right_5cm`

The perception launch defaults to `headless:=false` and
`sensor_rendering:=true`, and adds `perception_startup_timeout_s` and
`cup_pose_timeout_s`. The task-station launch permits only
`headless:=false` and `sensor_rendering:=true`; it adds
`task_evidence_root`, `include_teleop`, and `teleop_port`.

Use `ros2 launch ... --show-args` as the source of truth for the installed
overlay. See the [launch-parameter reference](../../docs/pick-place-launch-parameters.md)
for mode, checkpoint, resume, and validation semantics.

## Executable catalog

The package installs 18 console executables. The examples below assume the
selected overlay is sourced and the required stack is already ready.

### Workflow and orchestration executables

| Executable | Role | Usage boundary |
|---|---|---|
| `fixed_cup_pick_place` | Named fixed-waypoint state-machine entry point | Safe inspection: `ros2 run so101_demo_py fixed_cup_pick_place --backend mujoco --run-mode dry_run` |
| `dynamic_cup_pick_place` | Freeze one `/cup_pose`, resolve dynamic TCP targets, and plan or execute | Plan-only: `ros2 run so101_demo_py dynamic_cup_pick_place --backend gazebo --mode plan_only --plan-only-state MOVE_ABOVE_OBJECT` |
| `so101_mujoco_perception_pick_place` | Run the integrated perception launch while preserving child exit status | Use the RGB-D command shown above |
| `text_pick_agent` | Validate a DeepSeek or local Ollama proposal and optionally dispatch the dynamic runtime | Preview by default; Execute accepts either a reviewed digest or explicit `--skip-confirmation` |
| `so101_mujoco_rgbd_batch` | Own or attach to one visible MuJoCo stack and run an ordered `RESET_WORLD` point list | Requires `--points`, `--batch-id`, `--session-id`, and absolute `--evidence-root` |
| `run_qualification` | Run or verify lifecycle-separated qualification batches | Production tool; inspect `ros2 run so101_demo_py run_qualification --help` first |
| `teleop_workflow` | Adapt the Teleop service contract to the qualified MuJoCo runner | Orchestration-owned: `--mode execute --checkpoint <path> --session-id <id>` |
| `gazebo_execute` | Bounded Gazebo execution adapter used by launch composition | Launch-owned; use `so101_gazebo_pick_place.launch.py` instead |

`dynamic_cup_pick_place` accepts Gazebo for `plan_only`; live dynamic
execution is qualified only for MuJoCo and requires `--mode execute` plus
`--execute`, current session/reset provenance, and an evidence root. Prefer the
integrated perception launch unless intentionally testing a supplied
`/cup_pose` producer.

A qualification run requires an explicit lifecycle and isolation range:

```bash
ros2 run so101_demo_py run_qualification run \
  --batch-id full-restart-001 \
  --lifecycle FULL_RESTART \
  --count 5 \
  --fingerprint <installed-bundle-sha256> \
  --evidence-root <absolute-durable-evidence-root> \
  --base-domain-id <reserved-domain> \
  --base-port <reserved-port>
```

`FULL_RESTART` and `RESET_WORLD` batches have different ownership and counting
rules and must never be combined. Do not run qualification from placeholder
values; reserve the environment and obtain the installed bundle fingerprint
through the project qualification workflow first.

### Perception and ROS-interface executables

| Executable | Role | Minimal usage |
|---|---|---|
| `rgbd_cup_pose` | Continuously synchronize aligned RGB-D, estimate the cup, transform it to `world`, and publish `/cup_pose` | `ros2 run so101_demo_py rgbd_cup_pose` |
| `rgbd_point_cloud` | Convert one aligned RGB-D set into an Open3D cup cloud | `ros2 run so101_demo_py rgbd_point_cloud --output-ply /tmp/cup.ply` |
| `rgbd_sensor_capture` | Capture one synchronized RGB-D/TF evidence set and exit | `ros2 run so101_demo_py rgbd_sensor_capture --output-directory /tmp/rgbd-capture-001` |
| `cup_pose_subscriber` | Wait for and validate diagnostic `/cup_pose` samples | `ros2 run so101_demo_py cup_pose_subscriber --timeout-s 10` |
| `cup_pose_tf_demo` | Transform one `/cup_pose_camera` sample into `world` `/cup_pose` | `ros2 run so101_demo_py cup_pose_tf_demo --input-topic /cup_pose_camera --output-topic /cup_pose --target-frame world` |

The default RGB-D topics are `/task_camera/camera_info`,
`/task_camera/color`, and `/task_camera/depth`. `rgbd_sensor_capture` requires
an absolute output directory that does not already exist. `rgbd_cup_pose` is a
resident producer; `rgbd_point_cloud`, `rgbd_sensor_capture`, and
`cup_pose_tf_demo` are bounded one-shot tools.

### Operator, reset, and diagnostic executables

| Executable | Role | Minimal usage |
|---|---|---|
| `scene_setup` | Apply or read back the canonical Planning Scene | `ros2 run so101_demo_py scene_setup --backend mujoco setup` |
| `camera_preset` | Apply and read back a backend-specific camera preset | `ros2 run so101_demo_py camera_preset --backend mujoco table_corner_nw` |
| `teleop_reset` | Perform a transactional simulation reset and resynchronize MoveIt | `ros2 run so101_demo_py teleop_reset --backend mujoco --session-id task-station-001` |
| `task_reachability` | Plan-only check of every TCP segment for one or more task points | Requires `--points`, `--policy`, `--session-id`, and `--evidence-file` |
| `motion_stack_ready` | Wait for the three controllers and required MoveIt services/actions | `ros2 run so101_demo_py motion_stack_ready --timeout-s 90` |

`scene_setup` supports `setup`, `observe`, `attach`, `detach`, and `upsert`.
Every operation prints a JSON receipt and returns nonzero on failure. The
canonical table, pedestal, and plastic-cup geometry manifest is shared by both
simulator backends.

`task_reachability` returns `0` when all requested points are reachable, `2`
for a definite unreachable result, and `1` for unknown/configuration/runtime
failure. A typical check is:

```bash
SHARE="$(ros2 pkg prefix so101_demo_py)/share/so101_demo_py"
ros2 run so101_demo_py task_reachability \
  --points "$SHARE/config/mujoco/rgbd_task_points.yaml" \
  --policy "$SHARE/config/policies/dynamic_cup_pick/v1/mujoco.yaml" \
  --session-id task-station-001 \
  --evidence-file "$SO101_EVIDENCE_ROOT/reachability.json"
```

## Common recipes

### Run the visible four-point RGB-D batch

`so101_mujoco_rgbd_batch` starts and cleans up its own persistent stack unless
`--attach-existing-stack` is supplied:

```bash
SHARE="$(ros2 pkg prefix so101_demo_py)/share/so101_demo_py"
ros2 run so101_demo_py so101_mujoco_rgbd_batch \
  --points "$SHARE/config/mujoco/rgbd_task_points.yaml" \
  --batch-id visible-four-001 \
  --session-id visible-four-001 \
  --evidence-root "$SO101_EVIDENCE_ROOT/batch" \
  --include-teleop
```

Attached mode requires both `--attach-existing-stack` and the exact
`--mujoco-pid` belonging to that stack. It does not authorize attaching to an
unverified or unrelated process.

### Run a Text Pick Agent preview with DeepSeek

The executable reads `DEEPSEEK_API_KEY` only from the process environment. It
does not open `~/.env` itself. Load the environment without printing secrets:

```zsh
set -a
source "$HOME/.env" >/dev/null 2>&1
env_load_exit=$?
set +a
if (( env_load_exit != 0 )); then
  print -u2 -- "failed to load ~/.env"
  exit 1
fi
[[ -n ${DEEPSEEK_API_KEY:-} ]] && print 'DEEPSEEK_API_KEY=SET' || print 'DEEPSEEK_API_KEY=UNSET'
```

Preview is the default and cannot dispatch the robot runtime:

```bash
ros2 run so101_demo_py text_pick_agent \
  --instruction "Pick the plastic cup. Apply no constraints." \
  --request-id text-preview-deepseek-001 \
  --backend mujoco
```

The default primary is `deepseek-v4-flash`. If it is unavailable, the planner
chain tries local Ollama once at `http://127.0.0.1:11434/api/chat` with
`qwen3.5:4b`.

To deterministically validate the local model, remove the cloud key only from
the current shell and run a new preview request:

```zsh
unset DEEPSEEK_API_KEY
ollama list | rg 'qwen3.5:4b'

ros2 run so101_demo_py text_pick_agent \
  --instruction "Pick the plastic cup. Apply no constraints." \
  --request-id text-preview-qwen-001 \
  --backend mujoco
```

The result must identify `planner.provider=ollama`,
`planner.model=qwen3.5:4b`, and `fallback_used=true`. A
`DISPATCH_PREVIEW` result proves schema, capability, and dispatch-gate
validation only; it is not physical pick evidence.

### Dispatch with a previously inspected Text Pick Agent digest

Execution requires the exact preview digest, both authorization controls, a
readiness-qualified MuJoCo stack, one `/cup_pose` producer, and fresh session,
reset, source, and installed-prefix provenance:

```bash
ros2 run so101_demo_py text_pick_agent \
  --instruction "$INSTRUCTION" \
  --request-id "$REQUEST_ID" \
  --backend mujoco \
  --mode execute \
  --execute \
  --confirmation-digest "$CONFIRMATION_DIGEST" \
  --cup-pose-timeout-s 30 \
  --session-id "$SESSION_ID" \
  --expected-reset-epoch "$RESET_EPOCH" \
  --evidence-root "$SO101_EVIDENCE_ROOT" \
  --source-commit "$(git rev-parse HEAD)" \
  --installed-prefix "$(ros2 pkg prefix so101_demo_py)"
```

`--cup-pose-timeout-s` defaults to `30.0` and accepts only a finite positive
number. It starts counting after the dynamic runtime reports
`status=READY subscription=/cup_pose`; start the production RGB-D producer
within that window. Increasing the timeout does not replay a volatile
`/cup_pose` sample that was published before the subscriber became ready.

Do not copy session, epoch, digest, or provenance values from an old run. See
the [Text Pick Agent source guide](../../docs/so101-text-pick-agent-source-guide.md)
for provider boundaries, confirmation construction, request claiming, and
evidence interpretation.

### Dispatch without Preview confirmation

For unattended simulation workflows, `--skip-confirmation` permits a direct
Execute without a prior Preview or `--confirmation-digest`:

```bash
ros2 run so101_demo_py text_pick_agent \
  --instruction "$INSTRUCTION" \
  --request-id "$REQUEST_ID" \
  --backend mujoco \
  --mode execute \
  --execute \
  --skip-confirmation \
  --cup-pose-timeout-s 30 \
  --session-id "$SESSION_ID" \
  --expected-reset-epoch "$RESET_EPOCH" \
  --evidence-root "$SO101_EVIDENCE_ROOT" \
  --source-commit "$(git rev-parse HEAD)" \
  --installed-prefix "$(ros2 pkg prefix so101_demo_py)"
```

The bypass and `--confirmation-digest` are mutually exclusive. The flag skips
only the human semantic confirmation: planner outcome and command validation,
the capability whitelist, dual Execute authorization, the MuJoCo-only backend,
runtime provenance, request claiming, and every downstream motion/evidence gate
remain mandatory. Execute JSON and the atomic provenance document record
`confirmation_mode=skipped`; normal confirmed execution records
`confirmation_mode=digest`.

## Safety, evidence, and lifecycle boundaries

- `dry_run` validates composition and request semantics without live motion.
- `plan_only` proves that a candidate plan can be produced; it does not prove
  controller execution, grasp contact, transport, release, or final placement.
- `execute` requires explicit authorization and records the first failed
  boundary. A zero process exit alone is not sufficient physical evidence.
- `--skip-confirmation` removes the human-reviewed digest and its protection
  against provider/model/command drift. It does not weaken any runtime gate.
- Physical acceptance requires real RGB-D payloads when perception is in
  scope, nonempty controller trajectories, grasp/transport/release evidence,
  final support and pose checks, Planning Scene synchronization, current
  provenance, and clean ownership shutdown.
- Viewer visibility and sensor rendering are separate controls. A successful
  headless run is not GUI evidence, and a screenshot is not physical proof.

MuJoCo qualification keeps two lifecycle classes separate:

- `FULL_RESTART`: every counted run owns an independent simulator and ROS
  stack.
- `RESET_WORLD`: one owned stack remains alive while each counted point advances
  to a newly observed reset epoch.

Results from one lifecycle never count toward the other lifecycle's
denominator. Retain the original manifest and child evidence for failed and
successful runs; do not overwrite evidence to make a rerun appear continuous.

## Real-arm boundary

`real_stub` parses only the committed fail-closed safety mapping. It has no
launcher and performs no device discovery, serial/socket access, ROS control
I/O, planning, execution, gripper command, reset, stop, or recovery. Every
operation returns `REJECTED / REAL_HARDWARE_NOT_CONFIGURED`. Enabling a physical
SO-101 requires a separate safety design, hardware adapter, and acceptance
process.

## Documentation index

- [Shared pick-place architecture](../../docs/pick-place-architecture.md):
  backend-neutral state machine and physical-outcome ownership.
- [Launch parameter reference](../../docs/pick-place-launch-parameters.md):
  modes, request controls, checkpoint/resume behavior, diagnostics, and
  provenance.
- [SO-101 Python architecture](../../docs/pick-place-python-architecture.md):
  package layers, ports, adapters, runtime composition, and execution flow.
- [Dynamic Cup Pick Place source guide](../../docs/so101-dynamic-cup-pick-place-source-guide.md):
  `/cup_pose`, dynamic target generation, IK, MoveIt, attachment, and evidence.
- [RGB-D Perception PickPlace source guide](../../docs/so101-rgbd-perception-pick-place-source-guide.md):
  RGB-D synchronization, point clouds, TF, pose estimation, task station, and
  batch validation.
- [Text Pick Agent source guide](../../docs/so101-text-pick-agent-source-guide.md):
  DeepSeek/Ollama planning, closed schemas, reviewed or explicitly bypassed
  confirmation, dispatch, and provider/runtime evidence.

## Development and static acceptance

Run package tests against the selected overlay when source code changes:

```bash
colcon test --packages-select so101_demo_py
colcon test-result --verbose
```

Run the package contract gate from the repository root:

```bash
SO101_DEMO_EXPECTED_PREFIX="$(ros2 pkg prefix so101_demo_py)" \
  src/so101_demo_py/scripts/check_fusion_contract.sh
```

The gate checks package discovery, installed resources, executables, launch
files, frozen policy bytes, backend boundaries, repository ownership, the
zero-I/O real stub, and textual hygiene.

When adding a public launch file or `console_scripts` entry, update this README
in the same change. Keep README prose in English, provide one safe minimal
command, state the execution/evidence boundary, and link detailed behavior to
the maintained architecture or source guide rather than duplicating it.
