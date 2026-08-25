# MuJoCo RGB-D Perception Pick-Place Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and validate a fail-closed Mac MuJoCo chain that derives `/cup_pose` from real RGB-D data and completes one physical dynamic pick-place from each of four named cup positions.

**Architecture:** A long-running `rgbd_cup_pose` node converts exact-stamp CameraPlugin RGB-D samples into an in-memory segmented cup cloud, transforms that cloud into `world` with tf2, fits the upright cup center, and publishes fresh `/cup_pose` messages. A dedicated launch starts the MuJoCo stack, static camera TF, perception node, and existing dynamic workflow; dynamic preflight compares perception against MuJoCo truth before synchronizing the MoveIt cup shadow.

**Tech Stack:** Python 3, ROS 2 Jazzy, rclpy, tf2_ros, geometry_msgs, sensor_msgs, NumPy, Open3D, MoveIt 2, mujoco_ros2_control, pytest, colcon, MuJoCo native viewer on macOS.

**Spec:** `docs/superpowers/specs/2026-08-26-mujoco-rgbd-perception-pick-place-design.md`

## Global Constraints

- Work in `/Users/matianyi/Projects/robot_demo_001/moveit-demo`; preserve every unrelated or pre-existing dirty change.
- Treat the current dirty MJCF, `setup.py`, geometry hash, `rgbd_cup_pose.py`, and their tests as user-owned in-scope starting work; never overwrite them wholesale.
- Use exactly one registered evidence root: `/tmp/so101-debug-rgbd-perception-pick-place-20260826/`.
- Do not create `/data/work/so101-debug-*`, delete evidence, run broad process cleanup, or run `ament_uncrustify --reformat`.
- Final acceptance is local macOS MuJoCo with `headless=false`; it does not operate a real robot.
- Production `/cup_pose` must come from CameraPlugin RGB-D through `rgbd_cup_pose`; `mujoco_cup_pose_bridge` must not run.
- `cup_pose_tf_demo` stays an independent teaching/debug executable and is not part of the production launch.
- All four positions use the existing dynamic place target; only the named initial keyframe changes.
- Each position receives one independent `FULL_RESTART` demonstration. Do not report five-run stability qualification.
- Perception, TF, Planning Scene, planning, controller, MuJoCo physics, and visual gates all remain mandatory.
- Use targeted patches and explicit file lists for every commit; do not stage unrelated files.

## File structure

- `src/so101_demo_py/assets/mujoco/scene.xml`: owns the four named physical initial states.
- `src/so101_demo_py/assets/mujoco/so101.urdf`: exposes the selected MJCF initial keyframe to the pinned hardware plugin.
- `src/so101_demo_py/src/runtime/camera_tf.py`: owns camera static-transform constants and launch-node construction.
- `src/so101_demo_py/src/runtime/launch_composition.py`: owns stack/workflow event ordering and initial-keyframe rendering.
- `src/so101_demo_py/launch/so101_mujoco_perception_pick_place.launch.py`: thin public launch entry.
- `src/so101_demo_py/src/cli/rgbd_point_cloud.py`: owns exact-stamp RGB-D matching, decoding, back-projection, segmentation, clustering, and optional PLY output.
- `src/so101_demo_py/src/cli/rgbd_cup_pose.py`: owns pure point transform, upright cup fitting, CLI arguments, and lazy ROS dispatch.
- `src/so101_demo_py/src/ros/rgbd_cup_pose_node.py`: owns ROS subscriptions, tf2 lookup, fresh `/cup_pose` publication, startup deadline, and bounded evidence writing.
- `src/so101_demo_py/src/application/dynamic_scene_sync.py`: owns perception-vs-MuJoCo validation ordering and dynamic cup shadow preparation.
- `src/so101_demo_py/src/ros/dynamic_runtime.py`: composes the new scene synchronization before existing dynamic execution.
- `docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md`: sole persistent experiment writer and checkpoint.

---

### Task 1: Register the experiment and make named keyframes selectable at startup

**Files:**
- Create: `docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md`
- Modify: `src/so101_demo_py/assets/mujoco/scene.xml`
- Modify: `src/so101_demo_py/assets/mujoco/so101.urdf`
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`
- Modify: `src/so101_demo_py/test/test_geometry_manifest.py`
- Modify: `src/so101_demo_py/test/test_launch_composition.py`
- Test: `src/so101_demo_py/test/test_mujoco_cup_test_keyframes.py`

**Interfaces:**
- Consumes: existing `task_start` MJCF keyframe and `_render_mujoco_robot_description()`.
- Produces: string tuple `MUJOCO_CUP_KEYFRAMES`, launch argument `mujoco_initial_keyframe`, and rendered hardware parameter `initial_keyframe`.

- [ ] **Step 1: Record the protected baseline and register the one evidence root**

Run:

```bash
mkdir -p /tmp/so101-debug-rgbd-perception-pick-place-20260826
git rev-parse HEAD
git branch --show-current
git status --short
pgrep -af 'mujoco|move_group|rviz2|dynamic_cup_pick_place|rgbd_cup_pose' || true
tmux list-sessions 2>/dev/null || true
```

Create the ledger with this concrete header and first planned experiment:

```yaml
task_id: so101-mujoco-rgbd-perception-pick-place
goal: Complete one RGB-D perception-driven physical MuJoCo pick-place from each of four named cup positions on the local Mac.
success_contract: Four independent FULL_RESTART runs each use real aligned RGB-D, publish a fresh world /cup_pose from rgbd_cup_pose, reach dynamic DONE, and pass physical, Planning Scene, controller, TF, and visual gates.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo
branch: main
base_commit: e06ee41
current_commit: e06ee41
evidence_root: /tmp/so101-debug-rgbd-perception-pick-place-20260826/
confirmed_conclusions:
  - Existing macOS CameraPlugin acceptance proves real aligned RGB-D is available only from a correctly sourced interactive runtime; topic names alone are insufficient.
  - Existing dynamic MuJoCo execution accepts one fresh world-frame /cup_pose and has already completed a canonical physical demonstration with a truth-only test bridge.
disproven_routes:
  - Publishing MuJoCo truth as /cup_pose does not validate production camera perception.
  - Routing production through cup_pose_tf_demo duplicates the selected world-point transform boundary.
open_hypotheses:
  - The current color mask, DBSCAN, static TF, and circle fit localize all four named positions within 0.01 m.
latest_checkpoint: CP-001
next_experiment: EXP-001
```

Append `EXP-001` as `PLANNED`, lifecycle `ISOLATED_STACK`, with the single variable “named initial keyframe is threaded into rendered URDF”; no runtime command starts in this task.

- [ ] **Step 2: Add RED launch and keyframe assertions**

Extend `test_launch_composition.py`:

```python
def test_mujoco_launch_declares_and_renders_selected_initial_keyframe() -> None:
    description = build_launch_description(backend="mujoco", pick_place=False)
    declared = _declared(description)
    assert "mujoco_initial_keyframe" in declared

    rendered = launch_composition._render_mujoco_robot_description(
        PACKAGE_ROOT,
        str(PACKAGE_ROOT / "assets/mujoco/scene.xml"),
        headless=False,
        initial_keyframe="cup_test_left_5cm",
    )
    assert '<param name="initial_keyframe">cup_test_left_5cm</param>' in rendered
```

Keep `test_mujoco_cup_test_keyframes.py` strict about all six robot qpos values being zero and the final seven values matching each expected cup Pose.

- [ ] **Step 3: Run RED tests**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  src/so101_demo_py/test/test_mujoco_cup_test_keyframes.py \
  src/so101_demo_py/test/test_launch_composition.py::test_mujoco_launch_declares_and_renders_selected_initial_keyframe
```

Expected: keyframe XML test passes; launch test fails because the argument, renderer parameter, and URDF token do not exist.

- [ ] **Step 4: Implement the minimal initial-keyframe contract**

In `launch_composition.py` define:

```python
MUJOCO_CUP_KEYFRAMES = (
    "task_start",
    "cup_test_forward_5cm",
    "cup_test_left_5cm",
    "cup_test_right_5cm",
)
```

Change the renderer signature and token substitution:

```python
def _render_mujoco_robot_description(
    share: Path,
    scene: str,
    *,
    headless: bool,
    initial_keyframe: str = "task_start",
    platform_name: str | None = None,
) -> str:
    if initial_keyframe not in MUJOCO_CUP_KEYFRAMES:
        raise RuntimeError(f"unsupported MuJoCo initial keyframe: {initial_keyframe}")
    description = (share / "assets/mujoco/so101.urdf").read_text(encoding="utf-8")
    description = description.replace("@SO101_MUJOCO_SCENE@", scene)
    description = description.replace("@SO101_MUJOCO_INITIAL_KEYFRAME@", initial_keyframe)
```

Add this hardware parameter beside `mujoco_model` in `so101.urdf`:

```xml
<param name="initial_keyframe">@SO101_MUJOCO_INITIAL_KEYFRAME@</param>
```

Declare the launch argument only for MuJoCo:

```python
DeclareLaunchArgument(
    "mujoco_initial_keyframe",
    default_value="task_start",
    choices=MUJOCO_CUP_KEYFRAMES,
)
```

Read it inside `_mujoco_execute_actions()` and pass it to the renderer. Preserve the existing default behavior of all public MuJoCo launch files.

- [ ] **Step 5: Run GREEN tests and geometry hash check**

Run:

```bash
PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  src/so101_demo_py/test/test_mujoco_cup_test_keyframes.py \
  src/so101_demo_py/test/test_geometry_manifest.py \
  src/so101_demo_py/test/test_launch_composition.py
```

Expected: all selected tests pass and the pinned `scene.xml` hash matches the user-updated geometry test.

- [ ] **Step 6: Update the ledger checkpoint and commit only Task 1 files**

Set `current_commit` to the pre-commit source commit, record test commands and exits under `EXP-001`, mark it `VALID`, and set `next_experiment: EXP-002`.

```bash
git add -- \
  docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md \
  src/so101_demo_py/assets/mujoco/scene.xml \
  src/so101_demo_py/assets/mujoco/so101.urdf \
  src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/test/test_geometry_manifest.py \
  src/so101_demo_py/test/test_launch_composition.py \
  src/so101_demo_py/test/test_mujoco_cup_test_keyframes.py
git diff --cached --check
git commit -m "feat: select MuJoCo cup keyframes at startup"
```

---

### Task 2: Encode and verify the camera TF contract

**Files:**
- Create: `src/so101_demo_py/src/runtime/camera_tf.py`
- Create: `src/so101_demo_py/test/test_camera_tf_contract.py`
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`

**Interfaces:**
- Consumes: `launch_ros.actions.Node` and the MJCF `task_camera` attributes.
- Produces: `StaticTransformSpec`, `BASE_TO_CAMERA`, `CAMERA_TO_OPTICAL`, and `camera_static_transform_nodes()`.

- [ ] **Step 1: Write the RED extrinsics test**

Create a test that composes RPY rotations without SciPy:

```python
def test_static_tf_composes_to_mjcf_camera_and_ros_optical_axes() -> None:
    camera = next(
        item
        for item in ElementTree.parse(SCENE).iter("camera")
        if item.attrib.get("name") == "task_camera"
    )
    world_origin = np.array((0.0, 0.0, 0.1899186)) + np.array(
        BASE_TO_CAMERA.translation_xyz
    )
    np.testing.assert_allclose(world_origin, np.fromstring(camera.attrib["pos"], sep=" "))

    mj_x, mj_y = np.fromstring(camera.attrib["xyaxes"], sep=" ").reshape(2, 3)
    mj_x /= np.linalg.norm(mj_x)
    mj_y /= np.linalg.norm(mj_y)
    mj_z = np.cross(mj_x, mj_y)
    expected_optical = np.column_stack((mj_x, -mj_y, -mj_z))
    composed = _rpy_matrix(BASE_TO_CAMERA.rpy) @ _rpy_matrix(CAMERA_TO_OPTICAL.rpy)
    np.testing.assert_allclose(composed, expected_optical, atol=3e-4)
```

Also assert the parent/child names are exactly `base -> camera_link -> task_camera_frame` and each generated Node runs `tf2_ros static_transform_publisher`.

- [ ] **Step 2: Run the RED test**

```bash
PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  src/so101_demo_py/test/test_camera_tf_contract.py
```

Expected: import failure because `so101_demo.runtime.camera_tf` does not exist.

- [ ] **Step 3: Implement focused transform specifications**

Create:

```python
@dataclass(frozen=True, slots=True)
class StaticTransformSpec:
    name: str
    parent_frame: str
    child_frame: str
    translation_xyz: tuple[float, float, float]
    rpy: tuple[float, float, float]

    def arguments(self) -> list[str]:
        x, y, z = self.translation_xyz
        roll, pitch, yaw = self.rpy
        return [
            "--x", str(x), "--y", str(y), "--z", str(z),
            "--roll", str(roll), "--pitch", str(pitch), "--yaw", str(yaw),
            "--frame-id", self.parent_frame,
            "--child-frame-id", self.child_frame,
        ]


BASE_TO_CAMERA = StaticTransformSpec(
    "so101_base_to_camera_link",
    "base",
    "camera_link",
    (0.65, -0.65, 0.3600814),
    (0.0, 0.517, 2.35619449),
)
CAMERA_TO_OPTICAL = StaticTransformSpec(
    "so101_camera_link_to_task_camera_frame",
    "camera_link",
    "task_camera_frame",
    (0.0, 0.0, 0.0),
    (-1.57079633, 0.0, -1.57079633),
)
```

`camera_static_transform_nodes()` returns two `Node` actions with `output="both"`. Do not put axis flips in perception code.

- [ ] **Step 4: Run GREEN tests**

```bash
PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  src/so101_demo_py/test/test_camera_tf_contract.py \
  src/so101_demo_py/test/test_launch_composition.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit the TF boundary**

```bash
git add -- \
  src/so101_demo_py/src/runtime/camera_tf.py \
  src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/test/test_camera_tf_contract.py
git diff --cached --check
git commit -m "feat: define MuJoCo task camera TF contract"
```

---

### Task 3: Return segmented cup clouds in memory

**Files:**
- Modify: `src/so101_demo_py/src/cli/rgbd_point_cloud.py`
- Modify: `src/so101_demo_py/test/test_rgbd_point_cloud.py`

**Interfaces:**
- Consumes: CameraInfo, RGB Image, depth Image, NumPy arrays, and Open3D DBSCAN.
- Produces: `AlignedRgbdBuffer`, `CupPointCloudResult`, `build_cup_point_cloud()`, `write_cup_point_cloud()`, and backward-compatible `build_point_cloud_report()`.

- [ ] **Step 1: Add RED exact-stamp and in-memory-result tests**

Add:

```python
def test_aligned_buffer_emits_only_an_exact_three_message_stamp() -> None:
    buffer = AlignedRgbdBuffer(max_samples=3)
    assert buffer.add_camera_info(_message(stamp_ns=10)) is None
    assert buffer.add_color(_message(stamp_ns=11)) is None
    assert buffer.add_depth(_message(stamp_ns=10)) is None
    aligned = buffer.add_color(_message(stamp_ns=10))
    assert tuple(message_stamp_ns(item) for item in aligned) == (10, 10, 10)


def test_build_cup_point_cloud_returns_selected_points_without_ply_roundtrip(
    monkeypatch,
) -> None:
    monkeypatch.setattr(rgbd_point_cloud, "_open3d_cloud", _fake_open3d_cloud)
    result = build_cup_point_cloud(
        _camera_info(),
        _rgb_message(),
        _depth_message(),
        depth_trunc_m=3.0,
        cluster_eps_m=0.02,
        cluster_min_points=2,
        minimum_cup_points=2,
    )
    assert result.frame_id == "task_camera_frame"
    assert result.stamp_ns == 20_000_000
    assert result.points_xyz.shape[1] == 3
    assert result.colors_rgb.shape == result.points_xyz.shape
    assert np.isfinite(result.points_xyz).all()
```

Add stride rejection tests for RGB `step != width * 3` and depth `step != width * 4`.

- [ ] **Step 2: Run the RED test file**

```bash
PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  src/so101_demo_py/test/test_rgbd_point_cloud.py
```

Expected: failures for missing buffer, result type, in-memory builder, and stride checks.

- [ ] **Step 3: Implement the exact-stamp buffer and result type**

Use these signatures:

```python
@dataclass(frozen=True, slots=True)
class CupPointCloudResult:
    frame_id: str
    stamp_ns: int
    image_width: int
    image_height: int
    intrinsics_fx_fy_cx_cy: tuple[float, float, float, float]
    points_xyz: np.ndarray
    colors_rgb: np.ndarray
    full_point_count: int
    color_candidate_point_count: int

    @property
    def cup_point_count(self) -> int:
        return int(self.points_xyz.shape[0])


class AlignedRgbdBuffer:
    def __init__(self, max_samples: int = 20) -> None:
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        self._max_samples = max_samples
        self._camera_infos: dict[int, Any] = {}
        self._colors: dict[int, Any] = {}
        self._depths: dict[int, Any] = {}

    def _add(
        self,
        messages: dict[int, Any],
        message: Any,
    ) -> tuple[Any, Any, Any] | None:
        messages[message_stamp_ns(message)] = message
        while len(messages) > self._max_samples:
            messages.pop(next(iter(messages)))
        common = self._camera_infos.keys() & self._colors.keys() & self._depths.keys()
        if not common:
            return None
        stamp = max(common)
        aligned = (
            self._camera_infos.pop(stamp),
            self._colors.pop(stamp),
            self._depths.pop(stamp),
        )
        return aligned

    def add_camera_info(self, message: Any) -> tuple[Any, Any, Any] | None:
        return self._add(self._camera_infos, message)

    def add_color(self, message: Any) -> tuple[Any, Any, Any] | None:
        return self._add(self._colors, message)

    def add_depth(self, message: Any) -> tuple[Any, Any, Any] | None:
        return self._add(self._depths, message)
```

`build_cup_point_cloud()` performs the current decode, projection, mask, DBSCAN, and minimum-count gates, then returns selected points/colors directly. `write_cup_point_cloud(result, output_ply)` is the only writer. `build_point_cloud_report()` calls those two functions and returns the current JSON-compatible keys so the existing CLI contract stays intact.

Replace the private dictionaries inside `_capture_aligned_rgbd()` with `AlignedRgbdBuffer`; do not change the public topics.

- [ ] **Step 4: Run GREEN and regression tests**

```bash
PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  src/so101_demo_py/test/test_rgbd_point_cloud.py \
  src/so101_demo_py/test/test_package_identity.py
```

Expected: all tests pass and `rgbd_point_cloud` remains registered.

- [ ] **Step 5: Commit the reusable point-cloud core**

```bash
git add -- \
  src/so101_demo_py/src/cli/rgbd_point_cloud.py \
  src/so101_demo_py/test/test_rgbd_point_cloud.py
git diff --cached --check
git commit -m "refactor: return segmented RGB-D cup clouds in memory"
```

---

### Task 4: Implement the continuous production cup-pose publisher

**Files:**
- Create: `src/so101_demo_py/src/ros/rgbd_cup_pose_node.py`
- Modify: `src/so101_demo_py/src/cli/rgbd_cup_pose.py`
- Modify: `src/so101_demo_py/setup.py`
- Modify: `src/so101_demo_py/package.xml`
- Modify: `src/so101_demo_py/test/test_rgbd_cup_pose.py`
- Modify: `src/so101_demo_py/test/test_installed_provenance.py`

**Interfaces:**
- Consumes: `CupPointCloudResult`, `transform_points()`, `estimate_upright_cup_pose()`, tf2 `TransformStamped`, and exact source stamps.
- Produces: `RgbdCupPoseOptions`, `CupPoseFrame`, `CupPoseFrameProcessor`, `estimate_world_cup_pose()`, `run_rgbd_cup_pose()`, and repeated fresh `geometry_msgs/msg/PoseStamped` on `/cup_pose`.

- [ ] **Step 1: Write RED pure and lifecycle tests**

Add pure estimation coverage:

```python
def test_estimate_world_cup_pose_transforms_points_before_circle_fit() -> None:
    estimate = estimate_world_cup_pose(
        _camera_partial_cylinder(),
        _world_from_camera_transform(),
        table_top_z=0.12,
        cup_height=0.09,
        expected_radius=0.04,
        radius_tolerance=0.005,
    )
    np.testing.assert_allclose(estimate.center_world_xyz, (0.02, -0.28, 0.165), atol=1e-6)
    assert estimate.fitted_radius_m == pytest.approx(0.04, abs=1e-6)
```

Add an adapter test with fake callbacks:

```python
def test_failed_frame_never_republishes_last_valid_pose() -> None:
    published = []
    errors = []
    valid = _valid_aligned_sample()

    def estimate(aligned):
        if aligned is valid:
            return _valid_cup_pose_frame()
        raise ValueError("fitted radius is outside tolerance")

    processor = CupPoseFrameProcessor(
        estimate=estimate,
        publish=published.append,
        on_error=errors.append,
    )
    processor.process(valid)
    processor.process(_sample_with_wrong_radius())
    assert len(published) == 1
    assert [str(error) for error in errors] == ["fitted radius is outside tolerance"]
```

Add a startup-deadline test expecting `RGBD_CUP_POSE_TIMEOUT` and nonzero return when every frame is invalid. Assert evidence PLY/JSON are written only for the first valid frame while later valid frames may continue publishing.

- [ ] **Step 2: Run RED tests**

```bash
PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  src/so101_demo_py/test/test_rgbd_cup_pose.py
```

Expected: failures because the continuous adapter and option/result types do not exist.

- [ ] **Step 3: Keep pure geometry in the CLI module**

Define:

```python
@dataclass(frozen=True, slots=True)
class CupPoseEstimate:
    center_world_xyz: tuple[float, float, float]
    fitted_radius_m: float


def estimate_world_cup_pose(
    points_camera: np.ndarray,
    transform_stamped: Any,
    *,
    table_top_z: float,
    cup_height: float,
    expected_radius: float,
    radius_tolerance: float,
) -> CupPoseEstimate:
    points_world = transform_points(points_camera, transform_stamped)
    center, radius = estimate_upright_cup_pose(
        points_world,
        table_top_z=table_top_z,
        cup_height=cup_height,
        expected_radius=expected_radius,
        radius_tolerance=radius_tolerance,
    )
    return CupPoseEstimate(tuple(float(value) for value in center), radius)
```

The CLI parser adds `--startup-timeout-s`, `--output-topic`, `--output-ply`, and `--evidence-json`, validates positive finite values, and lazily calls `run_rgbd_cup_pose(options)`. Remove the PLY read-back path from the calculation.

- [ ] **Step 4: Implement the ROS adapter**

Use a single rclpy node with CameraInfo/RGB/depth subscriptions, `AlignedRgbdBuffer`, a tf2 Buffer/Listener, and a reliable depth-1 `/cup_pose` publisher. Use `use_sim_time=True` and source timestamps for TF and output headers.

The core callback contract is:

```python
@dataclass(frozen=True, slots=True)
class CupPoseFrame:
    stamp_ns: int
    source_frame_id: str
    center_world_xyz: tuple[float, float, float]
    fitted_radius_m: float
    cloud: CupPointCloudResult


class CupPoseFrameProcessor:
    def __init__(
        self,
        *,
        estimate: Callable[[tuple[Any, Any, Any]], CupPoseFrame],
        publish: Callable[[CupPoseFrame], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._estimate = estimate
        self._publish = publish
        self._on_error = on_error

    def process(self, aligned: tuple[Any, Any, Any]) -> bool:
        """Publish exactly once for this valid frame; return False without publishing on error."""
        try:
            frame = self._estimate(aligned)
        except (RuntimeError, TimeoutError, ValueError) as error:
            self._on_error(error)
            return False
        self._publish(frame)
        return True
```

`run_rgbd_cup_pose()` exits nonzero if no valid frame is published by the startup deadline. After first success it remains alive, publishes only newly calculated valid frames, writes the PLY/JSON evidence once, and returns zero on orderly SIGINT/shutdown. It never imports or calls `mujoco_cup_pose_bridge`.

- [ ] **Step 5: Register dependencies and installed provenance**

Keep the existing `setup.py` entry:

```python
"rgbd_cup_pose = so101_demo.cli.rgbd_cup_pose:main"
```

Ensure `package.xml` contains `sensor_msgs`, `geometry_msgs`, `tf2_ros`, and `python3-numpy`. Open3D remains an explicit runtime preflight because the ROS package index does not provide a portable Mac rosdep key; absence must produce the existing actionable nonzero error, never a fallback algorithm.

Add `rgbd_cup_pose` to the installed executable contract in `test_installed_provenance.py`.

- [ ] **Step 6: Run GREEN and affected package tests**

```bash
PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  src/so101_demo_py/test/test_rgbd_cup_pose.py \
  src/so101_demo_py/test/test_rgbd_point_cloud.py \
  src/so101_demo_py/test/test_cup_pose_tf_demo.py \
  src/so101_demo_py/test/test_installed_provenance.py
```

Expected: all tests pass; the independent TF demo remains unchanged.

- [ ] **Step 7: Commit the production perception node**

```bash
git add -- \
  src/so101_demo_py/src/ros/rgbd_cup_pose_node.py \
  src/so101_demo_py/src/cli/rgbd_cup_pose.py \
  src/so101_demo_py/setup.py \
  src/so101_demo_py/package.xml \
  src/so101_demo_py/test/test_rgbd_cup_pose.py \
  src/so101_demo_py/test/test_installed_provenance.py
git diff --cached --check
git commit -m "feat: publish perceived cup pose from live RGB-D"
```

---

### Task 5: Synchronize only a perception-confirmed MoveIt cup shadow

**Files:**
- Create: `src/so101_demo_py/src/application/dynamic_scene_sync.py`
- Create: `src/so101_demo_py/test/test_dynamic_scene_sync.py`
- Modify: `src/so101_demo_py/src/application/cup_pose_preflight.py`
- Modify: `src/so101_demo_py/src/ros/dynamic_runtime.py`

**Interfaces:**
- Consumes: `CupPoseSample`, `CupSceneObservation`, `DynamicPickTemplate`, `TaskGeometry`, and `TaskScenePort`.
- Produces: `validate_cup_against_simulator()`, `geometry_with_cup_pose()`, and `prepare_dynamic_cup_scene()`.

- [ ] **Step 1: Write RED ordering and mutation-scope tests**

Create fakes that record every scene call:

```python
def test_divergent_perception_rejects_before_any_scene_mutation() -> None:
    scene = RecordingTaskScenePort()
    with pytest.raises(CupPosePreflightError, match="topic_vs_simulator"):
        prepare_dynamic_cup_scene(
            _sample(x=0.07),
            _observation(simulator_x=0.02),
            _template(position_tolerance=0.01),
            _geometry(),
            scene,
        )
    assert scene.calls == []


def test_confirmed_perception_updates_only_plastic_cup_and_reads_back() -> None:
    scene = RecordingTaskScenePort()
    updated = prepare_dynamic_cup_scene(
        _sample(x=-0.03),
        _observation(simulator_x=-0.03),
        _template(position_tolerance=0.01),
        _geometry(),
        scene,
    )
    assert scene.calls == ["apply", "observe"]
    assert updated.object("plastic_cup").pose.values[:3] == (-0.03, -0.28, 0.165)
    assert updated.object("table") == _geometry().object("table")
    assert updated.object("pedestal") == _geometry().object("pedestal")
```

Also test apply failure and read-back failure raise `CUP_POSE_SCENE_DIVERGENCE`.

- [ ] **Step 2: Run RED tests**

```bash
PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  src/so101_demo_py/test/test_dynamic_scene_sync.py
```

Expected: import failure because the application module does not exist.

- [ ] **Step 3: Split simulator validation from final three-source validation**

In `cup_pose_preflight.py`, add:

```python
def validate_cup_against_simulator(
    sample: CupPoseSample,
    observation: CupSceneObservation,
    template: DynamicPickTemplate,
) -> None:
    if observation.moveit_attached:
        raise CupPosePreflightError(
            "CUP_POSE_SCENE_DIVERGENCE",
            "plastic_cup must be a MoveIt world object",
        )
    topic = PoseEvidence(sample.pose_world.values[:3], sample.pose_world.values[3:])
    if (
        _position_distance(topic, observation.simulator_pose_world)
        > template.scene_position_tolerance_m
        or _orientation_distance(topic, observation.simulator_pose_world)
        > template.scene_orientation_tolerance_rad
    ):
        raise CupPosePreflightError(
            "CUP_POSE_SCENE_DIVERGENCE",
            "topic_vs_simulator exceeds configured tolerance",
        )
```

Leave `validate_cup_scene()` as the final topic/simulator/MoveIt convergence gate.

- [ ] **Step 4: Implement immutable geometry replacement and scene transaction**

Use `dataclasses.replace`:

```python
def geometry_with_cup_pose(
    geometry: TaskGeometry,
    pose: Pose7,
) -> TaskGeometry:
    objects = tuple(
        replace(item, pose=pose) if item.object_id == "plastic_cup" else item
        for item in geometry.objects
    )
    return replace(geometry, objects=objects)


def prepare_dynamic_cup_scene(
    sample: CupPoseSample,
    observation: CupSceneObservation,
    template: DynamicPickTemplate,
    geometry: TaskGeometry,
    scene: TaskScenePort,
) -> TaskGeometry:
    validate_cup_against_simulator(sample, observation, template)
    updated = geometry_with_cup_pose(geometry, sample.pose_world)
    applied = scene.apply_task_scene(updated)
    if not applied.success:
        raise CupPosePreflightError("CUP_POSE_SCENE_DIVERGENCE", "scene apply failed")
    observed = scene.observe_task_scene(updated, expected_cup_attachment=None)
    if not observed.success:
        raise CupPosePreflightError("CUP_POSE_SCENE_DIVERGENCE", "scene readback failed")
    return updated
```

- [ ] **Step 5: Compose it before target resolution and motion**

In `run_dynamic_execute()`:

1. load the common geometry manifest;
2. acquire one fresh sample;
3. create `RosMujocoCupSceneObserver` and observe once;
4. call `prepare_dynamic_cup_scene()` using `RosTaskScenePort`;
5. observe and run `validate_cup_scene()` twice;
6. only then call `resolve_motion_targets()` and construct `RosDynamicMujocoExecution`.

Close every created adapter in `finally`. No motion-planning object may be constructed before the scene transaction passes.

- [ ] **Step 6: Run GREEN and dynamic regressions**

```bash
PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  src/so101_demo_py/test/test_dynamic_scene_sync.py \
  src/so101_demo_py/test/test_cup_pose_preflight.py \
  src/so101_demo_py/test/test_dual_cup_entrypoints.py \
  src/so101_demo_py/test/test_dynamic_pick.py
```

Expected: all tests pass, divergence causes zero scene mutation, and no fixed-pose fallback appears.

- [ ] **Step 7: Commit the dynamic scene gate**

```bash
git add -- \
  src/so101_demo_py/src/application/dynamic_scene_sync.py \
  src/so101_demo_py/src/application/cup_pose_preflight.py \
  src/so101_demo_py/src/ros/dynamic_runtime.py \
  src/so101_demo_py/test/test_dynamic_scene_sync.py
git diff --cached --check
git commit -m "feat: sync perceived cup into MoveIt after truth check"
```

---

### Task 6: Add the fail-closed perception pick-place launch

**Files:**
- Create: `src/so101_demo_py/launch/so101_mujoco_perception_pick_place.launch.py`
- Create: `src/so101_demo_py/test/test_perception_pick_place_launch.py`
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`
- Modify: `src/so101_demo_py/test/test_launch_composition.py`
- Modify: `src/so101_demo_py/test/test_package_identity.py`

**Interfaces:**
- Consumes: existing MuJoCo stack actions, `camera_static_transform_nodes()`, `rgbd_cup_pose`, and `dynamic_cup_pick_place`.
- Produces: `build_perception_pick_place_launch_description()` and public launch `so101_mujoco_perception_pick_place.launch.py`.

- [ ] **Step 1: Write RED launch-topology tests**

Test the thin launcher and inspect the dedicated action builder:

```python
def test_perception_launch_is_thin_and_has_required_arguments() -> None:
    description = build_perception_pick_place_launch_description()
    assert {
        "run_mode",
        "execute",
        "headless",
        "session_id",
        "evidence_file",
        "mujoco_scene",
        "mujoco_initial_keyframe",
        "perception_startup_timeout_s",
        "cup_pose_timeout_s",
    } <= _declared(description)


def test_perception_workflow_is_scene_gated_and_fail_closed() -> None:
    source = inspect.getsource(launch_composition._mujoco_perception_execute_actions)
    assert 'executable="rgbd_cup_pose"' in source
    assert 'executable="dynamic_cup_pick_place"' in source
    assert "camera_static_transform_nodes" in source
    assert "OnProcessExit(" in source
    assert "scene_setup" in source
    assert "Shutdown" in source
    assert "mujoco_cup_pose_bridge" not in source
```

Assert the dynamic arguments include `--backend mujoco --mode execute --execute`, session ID,
`--expected-reset-epoch 0`, `--scene-source observe_only`, and a run-owned evidence directory.

- [ ] **Step 2: Run RED tests**

```bash
PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  src/so101_demo_py/test/test_perception_pick_place_launch.py
```

Expected: missing builder and launch file.

- [ ] **Step 3: Implement the dedicated action composition**

Add `_mujoco_perception_execute_actions()` without duplicating controller or MoveIt parameter construction. It creates:

```python
perception = Node(
    package="so101_demo_py",
    executable="rgbd_cup_pose",
    arguments=[
        "--startup-timeout-s", perception_timeout,
        "--output-topic", "/cup_pose",
        "--output-ply", str(evidence_root / "perception" / "cup.ply"),
        "--evidence-json", str(evidence_root / "perception" / "summary.json"),
    ],
    parameters=[{"use_sim_time": True}],
    output="both",
)

workflow = Node(
    package="so101_demo_py",
    executable="dynamic_cup_pick_place",
    arguments=[
        "--backend", "mujoco",
        "--mode", "execute",
        "--execute",
        "--cup-pose-timeout-s", cup_pose_timeout,
        "--scene-source", "observe_only",
        "--session-id", session_id,
        "--expected-reset-epoch", "0",
        "--evidence-root", str(evidence_root / "dynamic"),
    ],
    output="both",
)
```

Start both only after `scene_setup` exits zero. A nonzero `scene_setup` prevents both. A terminal perception failure shuts down the launch; workflow exit always shuts down the owned graph. Start static TF nodes with the stack so they are available before the first image callback.

Defaults: `perception_startup_timeout_s=30.0`, `cup_pose_timeout_s=45.0`, `headless=false`, and `mujoco_initial_keyframe=task_start`. Reject any execute flag mismatch before processes start.

- [ ] **Step 4: Add the thin public launch**

```python
"""MuJoCo RGB-D perception-driven dynamic pick-place launcher."""

from so101_demo.runtime.launch_composition import (
    build_perception_pick_place_launch_description,
)


def generate_launch_description():
    return build_perception_pick_place_launch_description()
```

- [ ] **Step 5: Run GREEN launch and identity tests**

```bash
PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  src/so101_demo_py/test/test_perception_pick_place_launch.py \
  src/so101_demo_py/test/test_launch_composition.py \
  src/so101_demo_py/test/test_package_identity.py
```

Expected: all tests pass and the fixed MuJoCo launch still selects the fixed workflow.

- [ ] **Step 6: Commit the production launch**

```bash
git add -- \
  src/so101_demo_py/launch/so101_mujoco_perception_pick_place.launch.py \
  src/so101_demo_py/src/runtime/launch_composition.py \
  src/so101_demo_py/test/test_perception_pick_place_launch.py \
  src/so101_demo_py/test/test_launch_composition.py \
  src/so101_demo_py/test/test_package_identity.py
git diff --cached --check
git commit -m "feat: launch RGB-D perception dynamic pick-place"
```

---

### Task 7: Build, verify installation, and pass a perception-only Mac runtime gate

**Files:**
- Modify: `docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md`
- Runtime evidence only: `/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-002/`

**Interfaces:**
- Consumes: Tasks 1-6 code and the current logged-in Mac Aqua session.
- Produces: verified installed provenance plus one real aligned RGB-D -> point cloud -> tf2 -> `/cup_pose` result before any robot motion.

- [ ] **Step 1: Re-read the SO-101 runtime and visual instructions**

Read `.agents/skills/so101-dev/SKILL.md`, its required references, and the local `computer-use` skill before GUI actions. Record a `PLANNED` `EXP-002` with lifecycle `ISOLATED_STACK`, source commit, domain `180`, session `rgbd-perception-gate-20260826`, and the success/failure/invalid criteria below before starting a process.

- [ ] **Step 2: Run the complete source test suite**

```bash
mkdir -p /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-002/tests
PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  src/so101_demo_py/test \
  2>&1 | tee /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-002/tests/pytest.log
```

Expected: exit 0 with no new failure. Record the exact test count rather than copying a historical number.

- [ ] **Step 3: Build and re-source the installed package**

In a shell where the repository `.envrc` is already authorized:

```bash
eval "$(direnv export zsh)"
command -v colcon
colcon build --packages-select so101_demo_py --symlink-install --event-handlers console_direct+ \
  2>&1 | tee /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-002/tests/colcon-build.log
source install/setup.zsh
ros2 pkg prefix so101_demo_py
ros2 pkg prefix mujoco_ros2_control
ros2 pkg prefix mujoco_ros2_control_plugins
ros2 pkg executables so101_demo_py | sort
```

Expected: build exit 0; every prefix resolves to the current project install; executables include `rgbd_cup_pose` and `dynamic_cup_pick_place`; the installed share contains the new launch and updated scene.

- [ ] **Step 4: Confirm domain and process isolation**

```bash
ROS_DOMAIN_ID=180 ros2 node list
pgrep -af 'mujoco|move_group|rviz2|dynamic_cup_pick_place|rgbd_cup_pose' || true
tmux list-sessions 2>/dev/null || true
```

Expected: domain 180 is empty and no conflicting process is owned by another task. If not, mark `EXP-002` invalid and select a new documented domain; do not stop the conflicting process.

- [ ] **Step 5: Start the stack without a workflow and run perception manually**

Use the logged-in Mac terminal/GUI session and retain each PID or tmux pane owner. Launch:

```bash
ROS_DOMAIN_ID=180 \
ROS_LOG_DIR=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-002/ros \
ros2 launch so101_demo_py so101_mujoco.launch.py \
  run_mode:=execute execute:=true headless:=false \
  session_id:=rgbd-perception-gate-20260826 \
  mujoco_initial_keyframe:=task_start \
  evidence_file:=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-002/stack.json
```

In sibling owned panes start the two exact static transforms from the approved design, then run:

```bash
ROS_DOMAIN_ID=180 ros2 run so101_demo_py rgbd_cup_pose \
  --startup-timeout-s 30 \
  --output-topic /cup_pose \
  --output-ply /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-002/cup.ply \
  --evidence-json /tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-002/perception.json
```

Do not run `dynamic_cup_pick_place` in this experiment.

- [ ] **Step 6: Capture numeric and visual perception proof**

Save fresh one-shot evidence:

```bash
ROS_DOMAIN_ID=180 ros2 topic echo /task_camera/camera_info --once
ROS_DOMAIN_ID=180 ros2 topic echo /task_camera/color --once --field header
ROS_DOMAIN_ID=180 ros2 topic echo /task_camera/depth --once --field header
ROS_DOMAIN_ID=180 ros2 topic echo /cup_pose --once
ROS_DOMAIN_ID=180 ros2 topic info /cup_pose --verbose
ROS_DOMAIN_ID=180 timeout 5 ros2 run tf2_ros tf2_echo world task_camera_frame
```

Acceptance requires aligned 640x480 `rgb8`/`32FC1`, finite positive depth, nonempty PLY, fitted radius inside tolerance, `/cup_pose` from `rgbd_cup_pose`, and perceived-vs-MuJoCo error at most `0.01 m`. Use local Computer Use `snapshot -> action -> fresh snapshot` and retain a new viewer image that visibly shows the canonical cup and active MuJoCo scene.

- [ ] **Step 7: Stop only owned processes and close the experiment**

Send SIGINT to the owned launch and owned helper panes, wait for clean exits, then verify domain 180 and the targeted PID scan are empty. Mark `EXP-002` `VALID` only if all perception gates and cleanup pass; otherwise record the exact first bad boundary and retain it as a valid failure or invalid environment.

- [ ] **Step 8: Update checkpoint and commit runtime documentation**

```bash
git add -- docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md
git diff --cached --check
git commit -m "test: record RGB-D cup perception runtime gate"
```

---

### Task 8: Complete and document the four-position physical acceptance

**Files:**
- Modify: `docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md`
- Runtime evidence only: `/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/` through `exp-006/`

**Interfaces:**
- Consumes: accepted installed runtime from Task 7 and public `so101_mujoco_perception_pick_place.launch.py`.
- Produces: four independent accepted physical runs, final verification, and retained/archived/deletion-candidate classification.

- [ ] **Step 1: Freeze four planned experiments before execution**

Add these ledger entries as `PLANNED`, each with lifecycle `FULL_RESTART`, the same installed commit and policy, unique session/domain, and only the initial keyframe changed:

| Experiment | ROS domain | Session | Initial keyframe |
|---|---:|---|---|
| EXP-003 | 181 | `rgbd-pick-task-start-20260826` | `task_start` |
| EXP-004 | 182 | `rgbd-pick-forward-20260826` | `cup_test_forward_5cm` |
| EXP-005 | 183 | `rgbd-pick-left-20260826` | `cup_test_left_5cm` |
| EXP-006 | 184 | `rgbd-pick-right-20260826` | `cup_test_right_5cm` |

For every entry, success requires camera, cloud, TF, perceived Pose, dynamic `DONE`, controller/joint/TCP, MuJoCo physical outcome, MoveIt convergence, three fresh visual frames, and clean shutdown. A mixed session, duplicate stack, missing screenshot, wrong overlay, or unavailable camera sample is invalid.

- [ ] **Step 2: Run EXP-003 from `task_start`**

After confirming domain 181 and the targeted process scan are empty, launch from the logged-in Mac GUI terminal:

```bash
ROS_DOMAIN_ID=181 \
ROS_LOG_DIR=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/ros \
ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py \
  run_mode:=execute execute:=true headless:=false \
  session_id:=rgbd-pick-task-start-20260826 \
  mujoco_initial_keyframe:=task_start \
  perception_startup_timeout_s:=30 \
  cup_pose_timeout_s:=45 \
  evidence_file:=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-003/run.json
```

Capture inspected perception-baseline, transport, and final screenshots for the same session. Record exact command exit, dynamic manifest, source Pose, fitted radius, perception error, state trace, controllers, joint/TCP changes, final MuJoCo support/stability/contact, and Planning Scene membership.

- [ ] **Step 3: Run EXP-004 from `cup_test_forward_5cm`**

Repeat only after EXP-003 owned processes and domain are empty:

```bash
ROS_DOMAIN_ID=182 \
ROS_LOG_DIR=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/ros \
ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py \
  run_mode:=execute execute:=true headless:=false \
  session_id:=rgbd-pick-forward-20260826 \
  mujoco_initial_keyframe:=cup_test_forward_5cm \
  perception_startup_timeout_s:=30 \
  cup_pose_timeout_s:=45 \
  evidence_file:=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-004/run.json
```

Apply the same ten acceptance gates and retain the same evidence classes.

- [ ] **Step 4: Run EXP-005 from `cup_test_left_5cm`**

```bash
ROS_DOMAIN_ID=183 \
ROS_LOG_DIR=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-005/ros \
ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py \
  run_mode:=execute execute:=true headless:=false \
  session_id:=rgbd-pick-left-20260826 \
  mujoco_initial_keyframe:=cup_test_left_5cm \
  perception_startup_timeout_s:=30 \
  cup_pose_timeout_s:=45 \
  evidence_file:=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-005/run.json
```

Apply the same ten acceptance gates and retain the same evidence classes.

- [ ] **Step 5: Run EXP-006 from `cup_test_right_5cm`**

```bash
ROS_DOMAIN_ID=184 \
ROS_LOG_DIR=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-006/ros \
ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py \
  run_mode:=execute execute:=true headless:=false \
  session_id:=rgbd-pick-right-20260826 \
  mujoco_initial_keyframe:=cup_test_right_5cm \
  perception_startup_timeout_s:=30 \
  cup_pose_timeout_s:=45 \
  evidence_file:=/tmp/so101-debug-rgbd-perception-pick-place-20260826/exp-006/run.json
```

Apply the same ten acceptance gates and retain the same evidence classes.

- [ ] **Step 6: Diagnose failures one boundary at a time**

If a run fails, finish its ledger entry before any retry. Mark environment/provenance/session contamination `INVALID`; mark a correctly initialized behavioral failure `VALID` with a failed conclusion. Create a new experiment ID and change only one hypothesis variable. Never weaken the `0.01 m` gate, use truth `/cup_pose`, reuse stale screenshots, or silently change the motion policy to obtain a success.

- [ ] **Step 7: Run final verification from the accepted installed commit**

```bash
PYTHONPATH=src/so101_demo_py/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q src/so101_demo_py/test
eval "$(direnv export zsh)"
colcon build --packages-select so101_demo_py --symlink-install --event-handlers console_direct+
source install/setup.zsh
ros2 pkg prefix so101_demo_py
ros2 pkg executables so101_demo_py | sort
git diff --check
git status --short
```

Record fresh exits and counts. Confirm domains 180-184 are empty and no task-owned process remains.

- [ ] **Step 8: Hash evidence and write the final checkpoint**

Generate a deterministic inventory without moving or deleting files:

```bash
find /tmp/so101-debug-rgbd-perception-pick-place-20260826 -type f -print0 \
  | sort -z \
  | xargs -0 shasum -a 256 \
  > /tmp/so101-debug-rgbd-perception-pick-place-20260826/sha256.txt
find /tmp/so101-debug-rgbd-perception-pick-place-20260826 -type f -exec stat -f '%z %N' {} \; \
  | sort \
  > /tmp/so101-debug-rgbd-perception-pick-place-20260826/sizes.txt
```

The final checkpoint lists the four accepted experiment IDs, exact first bad boundaries for retained failures, owned processes `NONE`, preserved processes, remaining risks, and `next_command: NONE` only if all four positions pass.

- [ ] **Step 9: Commit the completed ledger and request final code review**

```bash
git add -- docs/experiments/mujoco-rgbd-perception-pick-place-experiment-ledger.md
git diff --cached --check
git commit -m "test: validate four RGB-D cup pick positions"
```

Use `superpowers:requesting-code-review` for the final implementation diff and `superpowers:verification-before-completion` before reporting success. Report retained runs, archived runs, and deletion candidates separately; do not delete any evidence.
