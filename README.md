# SO-101 MoveIt simulation workspace

This repository is a ROS 2 Jazzy and MoveIt 2 workspace for SO-101 simulation.
It includes Gazebo Harmonic and MuJoCo backends, RGB-D perception, a bounded
natural-language task layer, a browser-based Teleop interface, and pick-place
examples. The recommended SO-101 entry point is the unified Python package
`so101_demo_py`. The workspace also keeps the shared-state-machine C++ Gazebo
implementation and several Panda examples.

## What is included

- One Python application layer for fixed-waypoint SO-101 pick-place on MuJoCo
  and Gazebo.
- An RGB-D path that synchronizes CameraInfo, color, and depth by source stamp,
  transforms the detected cup through tf2, and publishes `/cup_pose` in
  `world`.
- A dynamic target path that freezes one fresh `/cup_pose`, derives TCP targets,
  runs 5-DoF IK, and uses MoveIt plus the controllers for planning and motion.
- A Text Pick Agent that lets DeepSeek or local Ollama propose a closed
  `TaskCommand`. Deterministic Python code keeps validation, confirmation,
  request claiming, dispatch, and execution authority.
- A full MuJoCo Text Agent E2E entry point that can run YOLO-Seg or Grounded
  SAM before the existing dynamic pick-place workflow. The original Text Agent
  and perception launchers remain available for focused checks and compatibility.
- A YOLO-Seg object-pose path for one-shot multi-instance detection, fail-closed
  target selection, aligned RGB-D localization, and atomic evidence artifacts.
  It runs as `rgbd_object_pose` or as the `yolo_seg` backend of the integrated
  perception and Text Agent E2E launches.
- A Grounded SAM object-pose backend using Grounding DINO Tiny and SAM 2.1
  Hiera Tiny, with verified local model bundles, per-instance masks, and the
  same unique-target and RGB-D localization rules as YOLO-Seg.
- Synthetic dataset generation, Grounding DINO fine-tuning, SAM decoder-only
  training, and an offline perception benchmark with sealed datasets, threshold
  calibration, and production/replay consistency checks.
- Portable semantic profiling for the full Text Agent workflow. `summary` mode
  writes cross-platform JSON; `trace` adds a Chrome trace and can start
  `ros2_tracing` with LTTng on Linux.
- MoveIt 2 and `ros2_control` integration for planning, trajectory execution,
  and Planning Scene management.
- Shared Planning Scene geometry, camera presets, transactional world reset,
  and layered runtime evidence.
- A backend-independent SO-101 Teleop Web UI.
- A project-pinned `mujoco_ros2_control` 0.1.0 architecture fork with Linux and
  Apple Silicon macOS build and qualification records.

## Architecture at a glance

```text
Natural-language instruction
  -> DeepSeek or Ollama planner
  -> closed TaskCommand validation
  -> confirmation + request claim + allowlisted dispatch
  -> select MuJoCo perception backend
                                      |
MuJoCo task_camera                    |
  -> exact-stamp RGB-D                |
  -> color_geometry, YOLO-Seg,        |
     or Grounded SAM                  |
  -> source-stamped /cup_pose --------+-> dynamic_cup_pick_place
                                             |
Fixed policy ------------------------------->+-> MoveIt 2 + ros2_control
                                                 -> Gazebo Harmonic or MuJoCo

Optional observation path:
  launch + perception + agent + runtime spans
    -> JSONL events -> summary.json -> trace.json
    -> Linux ros2_tracing / LTTng CTF when requested and available

Model perception path:
  aligned RGB-D -> YOLO-Seg or Grounded SAM
    -> exactly-one target selector -> 3D localization
    -> /cup_pose + detections + overlay + per-request evidence
```

The main package boundaries are:

- `so101_demo_py` owns the SO-101 Python launchers, application logic, fixed and
  dynamic workflows, perception adapters, profiling, configuration, and
  installed resources.
- `so101_teleop` provides backend selection, the ROS 2 server, and the Web UI.
- `pick_place_common` contains the robot-independent C++ pick-place core.
  Robot resources and policies remain in their own C++ packages.
- `so101_mujoco_support` provides SO-101 MuJoCo physics-evidence support. The
  pinned `mujoco_ros2_control` fork is built as a separate overlay.
- `panda_mujoco_demo` contains the Panda MuJoCo model, controllers, MoveIt
  configuration, and launch entry points.

See the [SO-101 Python architecture](docs/pick-place-python-architecture.md) for
the dependency rules and runtime boundaries. The
[shared C++ pick-place architecture](docs/pick-place-architecture.md) describes
the backend-neutral state machine and physical-outcome ownership.

## Repository layout

```text
ws_moveit/
├── src/
│   ├── so101_demo_py/             # Unified SO-101 Python application
│   ├── so101_teleop/              # Teleop server, Web UI, and backend profiles
│   ├── so101_mujoco_support/      # SO-101 MuJoCo support resources
│   ├── pick_place_common/         # Robot-independent C++ workflow core
│   ├── so101_gazebo_demo_cpp/     # SO-101 Gazebo and MoveIt C++ example
│   ├── panda_gazebo_demo_cpp/     # Panda Gazebo and MoveIt C++ example
│   ├── panda_mujoco_demo/         # Panda MuJoCo and MoveIt example
│   └── fixed_pose_goal/           # Panda fixed-target pose example
├── docs/                          # Architecture, integration, and experiment docs
├── scripts/                       # Dependency and maintenance scripts
└── third_party/
    └── mujoco_ros2_control/       # Pinned fork submodule
```

`build/`, `install/`, and `log/` are generated by colcon and are not part of
the source layout.

## Project skills

Repository-level agent workflows live in `.agents/skills/`:

- [`so101-dev`](.agents/skills/so101-dev/SKILL.md) defines source and runtime
  provenance, evidence storage, and layered acceptance for SO-101 development.
- [`gui-capture`](.agents/skills/gui-capture/SKILL.md) routes GUI inspection on
  macOS and GNOME Linux. Visual acceptance requires a fresh screenshot paired
  with runtime data.
- [`gazebo-video-debug`](.agents/skills/gazebo-video-debug/SKILL.md) records and
  inspects Gazebo pick-place video. It supplements ROS, MoveIt, and physics
  evidence rather than replacing them.

## Requirements

- Ubuntu 24.04 with ROS 2 Jazzy, or Apple Silicon macOS with the source-built
  Jazzy underlay linked at `/opt/ros/jazzy`
- MoveIt 2
- Gazebo Harmonic and its ROS 2 bridge and control packages
- `colcon`, `rosdep`, and Zsh
- MuJoCo versions, fork commits, and dependencies pinned by
  `dependency-lock.yaml` and the repository installation scripts
- Bun for the Teleop Web UI
- Optional model runtimes from the pinned perception lockfiles: Ultralytics and
  PyTorch for YOLO-Seg, or the Grounding DINO and SAM 2.1 dependencies and a
  verified local model bundle for Grounded SAM

## Build

Install the ROS dependencies declared by the workspace:

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
rosdep install --from-paths src --ignore-src -r -y
```

For a complete build, including the MuJoCo overlay, use the pinned dependency
installer:

```bash
zsh scripts/install-mujoco-ros2-control.zsh --init-submodule
source /data/work/ws_mujoco_ros2_control_fork/install/setup.zsh
colcon build --base-paths src --symlink-install
source install/setup.zsh
```

The installer initializes, builds, and verifies the fork against
`src/so101_demo_py/config/mujoco/dependency-lock.yaml`. To build only a Gazebo
or C++ example, select the required packages:

```bash
source /opt/ros/jazzy/setup.zsh
colcon build --symlink-install --packages-up-to so101_gazebo_demo_cpp so101_teleop
source install/setup.zsh
```

Every new terminal must source the ROS underlay, the backend dependency overlay,
and this workspace overlay in that order.

## Run

The commands below assume the relevant overlays have been built and sourced.
Confirm the installed runtime before testing a source change:

```bash
ros2 pkg prefix so101_demo_py
ros2 pkg executables so101_demo_py | sort
ros2 launch so101_demo_py so101_mujoco.launch.py --show-args
```

### Fixed-waypoint workflows

The MuJoCo and Gazebo pick-place launchers default to
`run_mode:=dry_run execute:=false`:

```bash
ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py
ros2 launch so101_demo_py so101_gazebo_pick_place.launch.py
```

Enable motion only inside the intended simulation environment:

```bash
ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py \
  run_mode:=execute execute:=true

ros2 launch so101_demo_py so101_gazebo_pick_place.launch.py \
  run_mode:=execute execute:=true
```

Stack-only launchers are also available:

```bash
ros2 launch so101_demo_py so101_mujoco.launch.py
ros2 launch so101_demo_py so101_gazebo.launch.py
```

### RGB-D perception and dynamic pick-place

The status-preserving wrapper owns MuJoCo, CameraPlugin, static camera TF,
`rgbd_cup_pose`, MoveIt, the controllers, and `dynamic_cup_pick_place`. It uses
camera data to produce `/cup_pose`; it does not substitute MuJoCo object truth
for perception.

The launch file declares safe defaults for inspection, but its configured graph
rejects the request unless `run_mode:=execute` and `execute:=true` are both
present. The example below keeps the viewer visible with `headless:=false`;
sensor rendering is controlled separately and also works in headless runs:

```bash
mkdir -p /tmp/so101-debug-rgbd-readme-demo
ros2 run so101_demo_py so101_mujoco_perception_pick_place \
  run_mode:=execute execute:=true headless:=false \
  session_id:=rgbd-readme-demo \
  mujoco_initial_keyframe:=task_start \
  evidence_file:=/tmp/so101-debug-rgbd-readme-demo/result.json
```

`evidence_file` must be a new absolute path with an existing parent directory.
Use a new `session_id` and evidence path for every run. Available initial cup
poses include `task_start`, `cup_test_forward_5cm`, `cup_test_left_5cm`, and
`cup_test_right_5cm`.

For perception-only work, inspect the bounded tools before running them:

```bash
ros2 run so101_demo_py rgbd_point_cloud --help
ros2 run so101_demo_py rgbd_cup_pose --help
ros2 run so101_demo_py rgbd_object_pose --help
ros2 run so101_demo_py cup_pose_subscriber --help
```

The integrated perception launch and the full Text Agent E2E launch support
three backends. The perception-only launch defaults to `color_geometry`. The
full E2E launch defaults to `yolo_seg` and accepts `color_geometry` as a
diagnostic compatibility path. The original
`so101_mujoco_text_pick_agent.launch.py` entry point still uses
`rgbd_cup_pose` and keeps its existing arguments and behavior.

| `perception_backend` | Detector | Required model arguments |
| --- | --- | --- |
| `color_geometry` | Color and geometry through `rgbd_cup_pose` | None |
| `yolo_seg` | YOLO instance segmentation through `rgbd_object_pose` | `perception_weights`, `perception_weights_sha256` |
| `grounded_sam` | Grounding DINO boxes followed by SAM masks through `rgbd_object_pose` | `perception_model_root`, `perception_model_manifest_sha256` |

YOLO-Seg requires a regular weights file and its expected SHA-256 digest.
Grounded SAM verifies a local bundle manifest and its files before loading the
models. Both object-pose backends require a unique evidence root and reject zero
or multiple matching `plastic_cup` candidates instead of choosing one
heuristically. Grounded SAM runs both models on the selected device; CPU
fallback is disabled by default.

Follow the [Grounded SAM source guide](docs/guides/so101-grounded-sam-rgbd-perception-pick-place-source-guide.md)
for bundle preparation, launch arguments, frozen thresholds, training recipes,
and delivery artifacts. The accepted adapted bundle uses Grounding DINO Tiny
epoch 1 and SAM 2.1 Hiera Tiny decoder epoch 4.

The [acceptance report](docs/reports/grounded-sam-yolo-seg-benchmark-report.md)
records four independent MuJoCo pick-place runs per machine as of September 7,
2026: Linux CUDA and two Mac MPS hosts each completed all four preset positions.
Linux and `mac-mini` met the two-second inference target; the other Mac exceeded
it on three positions. The Mac runs used a five-second source-age budget, while
the Linux acceptance used two seconds. These are recorded simulation results,
not fresh validation of another installation. The frozen model also had zero
recall in the historical COCO100 diagnostic, so its acceptance is limited to
the tested near-workspace domain.

### Natural-language RGB-D workflows

Set `DEEPSEEK_API_KEY` in the current process environment, or provide the local
Ollama model `qwen3.5:4b`. The original launch keeps the color and geometry
perception path. It requires all three execution controls and owns the ROS and
MuJoCo stack for the request:

```bash
mkdir -p /tmp/so101-debug-text-agent-readme
ros2 launch so101_demo_py so101_mujoco_text_pick_agent.launch.py \
  instruction:='Pick the plastic cup. Apply no constraints.' \
  run_mode:=execute execute:=true skip_confirmation:=true \
  headless:=false sensor_rendering:=true \
  mujoco_initial_keyframe:=task_start \
  session_id:=text-agent-readme-001 \
  evidence_file:=/tmp/so101-debug-text-agent-readme/result.json
```

Use `so101_mujoco_text_pick_agent_e2e.launch.py` when the request must pass
through YOLO-Seg or Grounded SAM before dynamic pick-place. This Ubuntu example
uses a registered local Grounded SAM bundle and CUDA:

```bash
export E2E_MODEL_ROOT=/data/work/models/grounded-sam-bundle
export E2E_MODEL_MANIFEST_SHA256=<manifest-sha256>
export E2E_ROOT=/data/work/so101-evidence/text-agent-e2e/<fresh-run-id>

ros2 launch so101_demo_py so101_mujoco_text_pick_agent_e2e.launch.py \
  instruction:='Pick the plastic cup. Apply no constraints.' \
  run_mode:=execute execute:=true skip_confirmation:=true \
  headless:=true sensor_rendering:=true \
  mujoco_initial_keyframe:=task_start \
  session_id:=text-agent-e2e-readme-001 \
  evidence_file:="$E2E_ROOT/e2e-result.json" \
  perception_backend:=grounded_sam \
  perception_runtime:=host perception_device:=cuda \
  perception_allow_cpu_fallback:=false \
  perception_model_root:="$E2E_MODEL_ROOT" \
  perception_model_manifest_sha256:="$E2E_MODEL_MANIFEST_SHA256"
```

The paths above show one Ubuntu layout. They are not fixed installation paths.
Create a new run root and session for each attempt, verify the installed overlay
and model digest first, and use the frozen thresholds from the
[multi-backend Text Agent E2E guide](docs/guides/text-agent-multibackend-mujoco-e2e.md)
for qualification runs.

Use the standalone `text_pick_agent` preview and digest flow when an operator
must inspect the proposed command before dispatch. `skip_confirmation` bypasses
that human review only. It does not bypass schema validation, the capability
allowlist, request claiming, runtime provenance, or downstream motion and
evidence checks.

The recorded Text Agent E2E qualification covers both model backends on two
platforms. YOLO-Seg and Grounded SAM each completed the four registered MuJoCo
cup positions on Ubuntu/CUDA and macOS/MPS, for `16/16` accepted runs. Every
accepted run reached `E2E_ACCEPTED` and `DONE/19`, used the requested GPU device
with CPU fallback disabled, left no attached Planning Scene object, and matched
the final Planning Scene and MuJoCo poses. These results apply to the registered
simulation environments and model artifacts. They do not qualify a physical
SO-101 or replace fresh provenance and run evidence on another installation.

### Cross-platform profiling

The Text Agent launch accepts `profiling:=off|summary|trace`. Profiling is off by
default. A portable summary run adds:

```bash
  profiling:=summary \
  profiling_require_system_trace:=false
```

Enabled sessions write per-process JSONL streams and aggregate them into
`profiling/manifest.json` and `profiling/summary.json`. `trace` also writes
`profiling/trace.json`. On Linux it attempts the `ros2_tracing` and LTTng backend;
set `profiling_require_system_trace:=true` when missing CTF output must fail the
run. macOS keeps the portable semantic trace and records that the system backend
is unavailable.

The profiler observes launch, RGB-D, planner, validation, dispatch, dynamic
runtime, state, and cleanup spans. It does not change task decisions or provide
execution authority. See the
[PickPlace profiling source guide](docs/guides/so101-pick-place-profiling-source-guide.md)
for the artifact schema and interpretation rules.

### Shared simulation tools

Select the active backend explicitly:

```bash
ros2 run so101_demo_py scene_setup --backend gazebo setup
ros2 run so101_demo_py camera_preset --backend gazebo overview
ros2 run so101_demo_py teleop_reset --backend gazebo --session-id operator-reset-001
```

### Teleop Web UI

Start a compatible simulation stack first, then launch Teleop with the same
simulation session:

```bash
ros2 launch so101_teleop so101_teleop.launch.py \
  backend:=gazebo_py \
  bind_address:=127.0.0.1 \
  simulation_session_id:=<session-id>
```

Teleop also supports `mujoco_py` and `gazebo_cpp` profiles. See the
[Teleop Web UI guide](src/so101_teleop/docs/so101-teleop-web-ui.md) for network,
safety, and Web bundle details.

### C++ and example packages

```bash
# SO-101 Gazebo and MoveIt C++ simulation
ros2 launch so101_gazebo_demo_cpp so101_gazebo.launch.py

# Panda Gazebo and MoveIt example
ros2 launch panda_gazebo_demo_cpp panda_gazebo.launch.py

# Panda MuJoCo and MoveIt example
ros2 launch panda_mujoco_demo panda_mujoco.launch.py

# Panda fixed-target pose example
ros2 launch fixed_pose_goal fixed_pose_goal.launch.py
```

## Tests and perception evaluation

After building and sourcing the workspace, run the ordinary Python package
suite on Linux with:

```bash
colcon test --packages-select so101_demo_py --pytest-args test
colcon test-result --verbose
```

The package's default pytest collection is restricted to
`src/so101_demo_py/test/`. Low-frequency model comparison tests live separately
in `src/so101_demo_py/benchmark_test/`. Run them explicitly when changing the
benchmark or selecting/comparing perception models:

```bash
colcon test --packages-select so101_demo_py --pytest-args benchmark_test
```

On `ai-station`, tests that create fsync-heavy fixtures require a new scratch
directory under the task's registered `/data/work/so101-evidence/` root. Before
testing, set `TMPDIR`, `TMP`, and `TEMP` to that directory and verify
`tempfile.gettempdir()` with the exact test Python. Follow the
[test and acceptance workflow](.agents/skills/so101-dev/references/test-and-acceptance.md)
for the macOS runner and environment checks.

The benchmark separates dataset sealing, raw candidate collection, threshold
calibration, and production/replay verification. Synthetic object IDs and truth
masks are evaluation labels only. The
[benchmark and acceptance report](docs/reports/grounded-sam-yolo-seg-benchmark-report.md)
keeps the earlier invalid comparison separate from the later adapted-model
acceptance; it does not establish a formal Grounded SAM versus YOLO-Seg ranking.

## Documentation

### Package overview and architecture

- [Unified SO-101 Python package](src/so101_demo_py/README.md)
- [SO-101 Python architecture](docs/pick-place-python-architecture.md)
- [Shared C++ pick-place architecture](docs/pick-place-architecture.md)
- [C++ launch parameters and safety contract](docs/pick-place-launch-parameters.md)

### Perception and task execution

- [Text Pick Agent source guide](docs/guides/so101-text-pick-agent-source-guide.md)
- [Multi-backend MuJoCo Text Agent E2E guide](docs/guides/text-agent-multibackend-mujoco-e2e.md)
- [RGB-D perception PickPlace source guide](docs/guides/so101-rgbd-perception-pick-place-source-guide.md)
- [YOLO-Seg RGB-D perception source guide](docs/guides/so101-yolo-seg-rgbd-perception-pick-place-source-guide.md)
- [Grounded SAM RGB-D perception, training, and delivery guide](docs/guides/so101-grounded-sam-rgbd-perception-pick-place-source-guide.md)
- [Dynamic cup PickPlace source guide](docs/guides/so101-dynamic-cup-pick-place-source-guide.md)

### Profiling and evaluation

- [PickPlace profiling source guide](docs/guides/so101-pick-place-profiling-source-guide.md)
- [Grounded SAM benchmark and cross-platform acceptance report](docs/reports/grounded-sam-yolo-seg-benchmark-report.md)

### Platform setup and integration

- [Apple Silicon ROS 2 Jazzy and SO-101 MuJoCo guide](docs/guides/macos-apple-silicon-ros2-jazzy-so101-mujoco.md)
- [SO-101 MuJoCo ROS 2 integration guide](docs/guides/so101-mujoco-ros2-integration-guide.md)
- [`mujoco_ros2_control` 0.1.0 upgrade notes](docs/guides/mujoco-ros2-control-0-1-upgrade-change-notes.md)

### Teleop and example packages

- [Teleop Web UI guide](src/so101_teleop/docs/so101-teleop-web-ui.md)
- [SO-101 Gazebo C++ package](src/so101_gazebo_demo_cpp/README.md)
- [Panda Gazebo C++ package](src/panda_gazebo_demo_cpp/README.md)
- [Panda MuJoCo package](src/panda_mujoco_demo/README.md)

## Safety boundary

All current SO-101 launchers in this repository target simulation. The Python
`real_stub` remains fail closed, and the repository does not include a launcher
that can drive a physical SO-101. A dynamic MuJoCo policy is usable only under
the qualification state recorded in its current manifest. Historical ledgers
or a successful run on another machine do not replace current source, installed
runtime, and run evidence.

Do not use these simulation execution commands on a physical arm. Real hardware
requires a separate adapter and safety design with calibrated limits, an
operator enable, watchdogs, stop behavior, an emergency stop, and independent
acceptance evidence.
