"""The real-twin scene: the human's real SO-101 table with a cube-to-bowl task, built from `twin_params.yaml`.

Every assertion reads files of the repository; no test assumes a file outside it. Plan (x, y) cm map to world
(x / 100, -y / 100) m, the follower pan axis is world (0, 0) and the table top is at z = 0.75 m.
"""

import copy
import hashlib
import importlib.util

import mujoco
import numpy as np
import pytest
from paths import PACKAGE_ROOT

TWIN_DIR = PACKAGE_ROOT / "assets/mujoco/real_twin"
SCENE = TWIN_DIR / "scene_real_twin_cube_bowl.xml"
TABLE_TOP = 0.75
ARM_BODIES = ("base", "shoulder", "upper_arm", "lower_arm", "wrist", "gripper", "jaw")


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_real_twin_scene", PACKAGE_ROOT / "scripts/build_real_twin_scene.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder():
    return _load_builder()


@pytest.fixture(scope="module")
def params(builder):
    return builder.load_params()


@pytest.fixture(scope="module")
def model():
    return mujoco.MjModel.from_xml_path(str(SCENE))


@pytest.fixture
def data(model):
    state = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, state, model.key("task_start").id)
    mujoco.mj_forward(model, state)
    return state


def _free_qpos(model, body: str) -> int:
    return int(model.jnt_qposadr[model.body_jntadr[model.body(body).id]])


def test_committed_files_equal_a_fresh_generation(builder, params):
    for name, text in builder.generate(params).items():
        assert (TWIN_DIR / name).read_text(encoding="utf-8") == text, name


def test_follower_copy_records_and_matches_its_source(builder, params):
    source = PACKAGE_ROOT / params["follower"]["source_file"]
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest == params["follower"]["source_sha256"]
    copy = (TWIN_DIR / "so101_follower_twin.xml").read_text(encoding="utf-8")
    assert digest in copy
    expected = source.read_text(encoding="utf-8").splitlines()
    lines = copy.splitlines()
    end = next(i for i, line in enumerate(lines) if line.endswith("-->"))
    actual = lines[:1] + lines[end + 1 :]  # drop the generated header comment (second line to its closing -->)
    changed = [(a, b) for a, b in zip(expected, actual, strict=True) if a != b]
    assert len(changed) == 3  # the base body position, the 3d_printed colour and the wrist camera intrinsics
    camera_edit = [(a, b) for a, b in changed if "wrist_camera" in a]
    assert len(camera_edit) == 1
    old, new = camera_edit[0]
    assert old.replace('fovy="90" ', "") == new.replace(builder.camera_intrinsics_attrs(params["wrist_camera"]["intrinsics"]) + " ", "")


def test_scene_loads_with_the_arm_and_both_cubes(model):
    assert model.nu == 6
    assert model.nq == 6 + 7 + 7
    assert [model.key(i).name for i in range(model.nkey)] == ["task_start", "rest_pose"]
    for name in ("green_cube", "red_cube", "paper_bowl", "base"):
        model.body(name)


def test_base_underside_is_on_the_table_top(model, data):
    base = model.body("base").id
    lowest = np.inf
    for geom in range(model.ngeom):
        if model.geom_bodyid[geom] == base and model.geom_type[geom] == mujoco.mjtGeom.mjGEOM_MESH:
            mesh = model.geom_dataid[geom]
            start, count = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
            vertices = model.mesh_vert[start : start + count]
            world = vertices @ data.geom_xmat[geom].reshape(3, 3).T + data.geom_xpos[geom]
            lowest = min(lowest, world[:, 2].min())
    assert abs(lowest - TABLE_TOP) < 1e-3
    table = model.geom("table_collision")
    top = data.geom_xpos[table.id][2] + model.geom_size[table.id][2]
    assert abs(top - TABLE_TOP) < 1e-6


def test_pan_axis_is_the_plan_origin_and_the_robot_faces_world_minus_y(model, data):
    joint = model.joint("1").id
    assert np.allclose(data.xanchor[joint][:2], 0.0, atol=1e-6)
    assert np.isclose(abs(data.xaxis[joint][2]), 1.0, atol=1e-5)  # vertical axis (the source points it down)
    tcp = data.site_xpos[model.site("so101_tcp").id]
    assert tcp[1] < -0.2  # forward is world -y


def test_plan_cells_map_to_world(model, data, params):
    green = data.xpos[model.body("green_cube").id]
    red = data.xpos[model.body("red_cube").id]
    bowl = data.xpos[model.body("paper_bowl").id]
    assert np.allclose(green[:2], [-0.04, -0.16], atol=1e-9)  # cell B3 = plan (-4, 16) cm
    assert np.allclose(red[:2], [0.04, -0.24], atol=1e-9)  # cell D1 = plan (4, 24) cm
    assert np.allclose(bowl, [0.13, -0.18, TABLE_TOP], atol=1e-9)  # plan (13, 18) cm
    table = data.geom_xpos[model.geom("table_collision").id]
    half = model.geom_size[model.geom("table_collision").id]
    assert np.isclose(table[0] - half[0], -0.1155)  # right edge, plan x = -11.55
    assert np.isclose(table[1] - half[1], -(38.02 / 100.0))  # front edge plan y = 38.02 -> world -0.3802
    assert np.isclose(table[1] + half[1], 0.0698)  # back edge flush with the base rear, plan y = -6.98


def test_both_cubes_rest_for_two_seconds(model, data):
    cubes = [data.xpos[model.body(n).id].copy() for n in ("green_cube", "red_cube")]
    for _ in range(round(2.0 / model.opt.timestep)):
        mujoco.mj_step(model, data)
    for name, start in zip(("green_cube", "red_cube"), cubes, strict=True):
        end = data.xpos[model.body(name).id]
        assert np.linalg.norm(end - start) < 1e-3
        assert abs(end[2] - (TABLE_TOP + 0.01)) < 1e-3
        speed = np.linalg.norm(data.cvel[model.body(name).id])
        assert speed < 1e-3


def test_a_cube_dropped_into_the_bowl_stays_inside(model, data):
    bowl = data.xpos[model.body("paper_bowl").id]
    address = _free_qpos(model, "green_cube")
    data.qpos[address : address + 3] = [bowl[0] + 0.015, bowl[1] - 0.01, TABLE_TOP + 0.10]
    mujoco.mj_forward(model, data)
    for _ in range(round(2.0 / model.opt.timestep)):
        mujoco.mj_step(model, data)
    cube = data.xpos[model.body("green_cube").id]
    assert np.hypot(cube[0] - bowl[0], cube[1] - bowl[1]) < 0.04
    assert TABLE_TOP + 0.004 < cube[2] < TABLE_TOP + 0.03  # on the bowl floor, below the 4 cm rim


def test_bowl_geometry_follows_the_given_sizes(model, params):
    bowl = params["bowl"]
    assert (bowl["outer_top_diameter"], bowl["inner_top_diameter"], bowl["height"]) == (12.0, 10.5, 4.0)
    walls = [g for g in range(model.ngeom) if model.geom(g).name.startswith("bowl_wall_")]
    assert len(walls) == bowl["wall_segments"]
    assert all(model.geom_contype[g] == 1 for g in walls)
    assert model.body_dofnum[model.body("paper_bowl").id] == 0  # fixed


def test_cube_size_and_mass(model, params):
    for name in ("green_cube", "red_cube"):
        body = model.body(name)
        geom = model.geom(f"{name}_geom")
        assert np.allclose(model.geom_size[geom.id], 0.01)
        assert 0.004 <= model.body_mass[body.id] <= 0.008


def _arm_contacts_with_table(model, data) -> int:
    table = model.geom("table_collision").id
    arm = {model.body(n).id for n in ARM_BODIES}
    count = 0
    for index in range(data.ncon):
        a, b = data.contact[index].geom1, data.contact[index].geom2
        other = b if a == table else a if b == table else None
        if other is not None and model.geom_bodyid[other] in arm:
            count += 1
    return count


def _solve_position(model, data, target, seeds, rng_seed=0):
    """Damped least-squares position IK on joints 1 to 5, from several starts; returns the first solution that has no arm contact with the table."""
    site = model.site("so101_tcp").id
    low, high = model.jnt_range[:5, 0], model.jnt_range[:5, 1]
    rng = np.random.default_rng(rng_seed)
    starts = list(seeds) + [rng.uniform(low, high) for _ in range(40)]
    jac = np.zeros((3, model.nv))
    best = np.inf
    for start in starts:
        data.qpos[:5] = start
        for _ in range(150):
            mujoco.mj_forward(model, data)
            error = target - data.site_xpos[site]
            if np.linalg.norm(error) < 5e-4:
                break
            mujoco.mj_jacSite(model, data, jac, None, site)
            j = jac[:, :5]
            step = j.T @ np.linalg.solve(j @ j.T + 1e-4 * np.eye(3), error)
            data.qpos[:5] = np.clip(data.qpos[:5] + step, low, high)
        mujoco.mj_forward(model, data)
        residual = np.linalg.norm(target - data.site_xpos[site])
        best = min(best, residual)
        if residual < 1e-3 and _arm_contacts_with_table(model, data) == 0:
            return residual
    return best


def test_the_bowl_and_the_cube_grid_are_within_reach(model, params):
    """Reach by IK: the TCP must reach every grid cell 2 cm above the table top and the bowl centre 6 cm above it.

    The solver is damped least squares on the five arm joints from the rest pose, q = 0 and 40 seeded random starts, inside the
    sim joint limits. A solution counts only with no contact between any arm geom and the table top. The tool orientation is not
    constrained, so this is a reach check, not a grasp-feasibility check.
    """
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, model.key("task_start").id)
    rest = np.array(model.key("rest_pose").qpos[:5])
    grid = params["grid"]
    targets = {}
    for row, y_cm in zip(grid["row_names"], grid["rows_y"], strict=True):
        for column, x_cm in enumerate(grid["columns_x"]):
            targets[f"{row}{column + 1}"] = [x_cm / 100.0, -y_cm / 100.0, TABLE_TOP + 0.02]
    bowl = params["bowl"]["center_plan_cm"]
    targets["bowl"] = [bowl[0] / 100.0, -bowl[1] / 100.0, TABLE_TOP + 0.06]
    failures = {}
    for name, target in targets.items():
        residual = _solve_position(model, data, np.array(target), [np.zeros(5), rest])
        if residual >= 1e-3:
            failures[name] = residual
    assert failures == {}


def _opencv_k(model, camera: int):
    """OpenCV K (pixel centres at integers) read back from the compiled MuJoCo camera."""
    width, height = (int(v) for v in model.cam_resolution[camera])
    fx, fy, px, py = model.cam_intrinsic[camera] / model.cam_sensorsize[camera][[0, 1, 0, 1]] * [width, height, width, height]
    return np.array([fx, fy, (width - 1) / 2.0 - px, (height - 1) / 2.0 - py])


def test_side_camera_pose_is_the_calibrated_one(model, data, params):
    cam = params["side_camera"]
    assert cam["status"].startswith("measured (calibrated 2026-10-27)")
    assert len(cam["source"]["extrinsics_sha256"]) == 64 and len(cam["source"]["intrinsics_sha256"]) == 64
    camera = model.camera("side_camera").id
    x, y, z = cam["position_plan_cm"]
    assert np.allclose(data.cam_xpos[camera], [x / 100.0, -y / 100.0, TABLE_TOP + z / 100.0], atol=1e-6)
    forward = -data.cam_xmat[camera].reshape(3, 3)[:, 2]
    up = data.cam_xmat[camera].reshape(3, 3)[:, 1]
    fx, fy, fz = cam["forward_plan"]
    ux, uy, uz = cam["image_up_plan"]
    assert np.allclose(forward, [fx, -fy, fz], atol=1e-6)  # the plan y axis is flipped, as for points
    assert np.allclose(up, [ux, -uy, uz], atol=1e-6)  # roll kept
    assert abs(np.dot(forward, up)) < 1e-6
    assert np.isclose(np.linalg.det(data.cam_xmat[camera].reshape(3, 3)), 1.0)
    assert forward[2] < -0.5  # pitched down (calibrated 43.8 degrees)


def test_side_camera_intrinsics_are_the_calibrated_ones_and_distortion_is_recorded(model, params):
    intrinsics = params["side_camera"]["intrinsics"]
    camera = model.camera("side_camera").id
    assert tuple(model.cam_resolution[camera]) == (640, 480) == tuple(intrinsics["resolution"])
    assert np.allclose(_opencv_k(model, camera), [intrinsics[k] for k in ("fx", "fy", "cx", "cy")], atol=1e-3)
    assert set(intrinsics["distortion_not_rendered"]) == {"k1", "k2", "p1", "p2", "k3"}
    assert intrinsics["distortion_not_rendered"]["k1"] < 0  # barrel


def test_the_wrist_camera_has_calibrated_intrinsics_and_the_existing_mount(model, params):
    camera = model.camera("wrist_camera").id
    intrinsics = params["wrist_camera"]["intrinsics"]
    assert params["wrist_camera"]["status_pose"] == "estimated"
    assert tuple(model.cam_resolution[camera]) == (640, 480)
    assert np.allclose(_opencv_k(model, camera), [intrinsics[k] for k in ("fx", "fy", "cx", "cy")], atol=1e-3)
    assert not np.isclose(model.cam_fovy[camera], 90.0)
    assert np.allclose(model.cam_pos[camera], [-0.014, -0.012, 0.050])  # the mount pose of the robot file, unchanged


def test_principalpixel_convention_projects_like_opencv():
    """A sphere rendered through the generated intrinsics lands where OpenCV's pinhole model with the same K puts it."""
    import os

    os.environ.setdefault("MUJOCO_GL", "egl")
    builder = _load_builder()
    intrinsics = {"resolution": [640, 480], "fx": 400.0, "fy": 300.0, "cx": 300.0, "cy": 260.0}
    xml = (
        f'<mujoco><worldbody><light pos="0 0 3"/><camera name="c" resolution="640 480" {builder.camera_intrinsics_attrs(intrinsics)}/>'
        '<geom type="sphere" size="0.05" pos="1.0 0.5 -10" rgba="1 0 0 1"/></worldbody></mujoco>'
    )
    model = mujoco.MjModel.from_xml_string(xml)
    state = mujoco.MjData(model)
    mujoco.mj_forward(model, state)
    try:
        renderer = mujoco.Renderer(model, 480, 640)
    except Exception as error:  # no GL context on this host
        pytest.skip(f"no offscreen GL: {error}")
    try:
        renderer.update_scene(state, camera="c")
        image = renderer.render()
    finally:
        renderer.close()
    rows, cols = np.where((image[..., 0] > 150) & (image[..., 1] < 80))
    # camera frame (OpenCV): x right = 1.0, y down = -0.5, z forward = 10
    assert abs(cols.mean() - (300.0 + 400.0 * 0.1)) < 0.3
    assert abs(rows.mean() - (260.0 - 300.0 * 0.05)) < 0.3


LEADER_DIR = TWIN_DIR / "leader"
FOLLOWER_XML_SHA256 = "93f41c1b188b12fc51c65f8639e57621dde2e73d32df1ed368341828e7753254"


def _leader_geoms(model):
    return [g for g in range(model.ngeom) if model.geom(g).name.startswith("leader_")]


def _lowest_z(model, data, body: int) -> float:
    lowest = np.inf
    for geom in range(model.ngeom):
        if model.geom_bodyid[geom] == body and model.geom_type[geom] == mujoco.mjtGeom.mjGEOM_MESH:
            mesh = model.geom_dataid[geom]
            start, count = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
            vertices = model.mesh_vert[start : start + count]
            world = vertices @ data.geom_xmat[geom].reshape(3, 3).T + data.geom_xpos[geom]
            lowest = min(lowest, world[:, 2].min())
    return float(lowest)


def test_leader_is_visual_only_and_has_no_joints(model):
    leader = _leader_geoms(model)
    assert leader
    for geom in leader:
        assert model.geom_contype[geom] == 0 and model.geom_conaffinity[geom] == 0
    bodies = [b for b in range(model.nbody) if model.body(b).name.startswith("leader_")]
    assert all(model.body_dofnum[b] == 0 and model.body_mass[b] == 0 for b in bodies)
    # the six non-free joints are the follower's; the leader adds none
    assert len([n for n in range(model.njnt) if model.jnt_type[n] != mujoco.mjtJoint.mjJNT_FREE]) == 6


def test_leader_has_the_official_handle_and_trigger_and_no_follower_jaw(model):
    names = {model.geom(g).name for g in _leader_geoms(model)}
    assert {
        "leader_gripper_Handle_SO101_visual",
        "leader_gripper_Wrist_Roll_SO101_visual",
        "leader_trigger_Trigger_SO101_visual",
    } <= names
    assert not any("jaw" in n or "fingertip" in n for n in names)
    for body in (
        "leader_base",
        "leader_shoulder",
        "leader_upper_arm",
        "leader_lower_arm",
        "leader_wrist",
        "leader_gripper",
        "leader_trigger",
    ):
        model.body(body)


def test_vendored_leader_files_match_their_recorded_hashes(params):
    leader = params["leader"]
    assert hashlib.sha256((TWIN_DIR / leader["urdf"]).read_bytes()).hexdigest() == leader["urdf_sha256"]
    for stem, entry in leader["meshes"].items():
        assert hashlib.sha256((TWIN_DIR / entry["file"]).read_bytes()).hexdigest() == entry["sha256"], stem
    source = (LEADER_DIR / "SOURCE.md").read_text(encoding="utf-8")
    assert "a758567c3978dfeefe282ede0500085a48fe8f78" in source and "Apache License 2.0" in source
    assert hashlib.sha256((LEADER_DIR / "LICENSE").read_bytes()).hexdigest() in source
    for name in ("so101_leader_new_calib.urdf", "Handle_SO101.stl", "Trigger_SO101.stl", "Wrist_Roll_SO101.stl"):
        assert hashlib.sha256((LEADER_DIR / name).read_bytes()).hexdigest() in source


def test_leader_base_sits_on_the_table_top_and_its_pan_axis_is_mirrored(model, data):
    assert abs(_lowest_z(model, data, model.body("leader_base").id) - TABLE_TOP) < 1e-3
    shoulder = data.xpos[model.body("leader_shoulder").id]
    follower = data.xpos[model.body("shoulder").id]
    assert np.allclose(shoulder[:2] - follower[:2], [0.419, 0.0], atol=1e-6)  # pan axis at plan x = 41.9 cm
    assert np.allclose(shoulder[2], follower[2], atol=1e-6)  # same height above the table


def test_leader_arm_equals_the_follower_when_given_the_follower_pose(model, builder, params):
    """Leader built with the follower's rest pose: its shared arm geoms are the follower's, shifted by 0.419 m in x."""
    probe = copy.deepcopy(params)
    probe["leader"]["rest_pose_deg"] = dict(params["follower"]["rest_pose_deg"])
    text = builder.build_leader(probe).replace('file="', f'file="{TWIN_DIR}/')
    leader_model = mujoco.MjModel.from_xml_string(text)
    leader_data = mujoco.MjData(leader_model)
    mujoco.mj_forward(leader_model, leader_data)
    state = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, state, model.key("rest_pose").id)
    mujoco.mj_forward(model, state)
    shift = np.array([0.419, 0.0, 0.0])
    pairs = {
        "base_visual_01": "leader_base_visual_01",
        "shoulder_visual_02": "leader_shoulder_visual_02",
        "upper_arm_visual_01": "leader_upper_arm_visual_01",
        "lower_arm_visual_00": "leader_lower_arm_visual_00",
        "wrist_visual_01": "leader_wrist_visual_01",
    }
    for follower_name, leader_name in pairs.items():
        a, b = model.geom(follower_name).id, leader_model.geom(leader_name).id
        assert np.allclose(leader_data.geom_xpos[b] - state.geom_xpos[a], shift, atol=2e-4), follower_name
        assert np.allclose(leader_data.geom_xmat[b], state.geom_xmat[a], atol=2e-4), follower_name


def test_follower_xml_is_unchanged(builder, params):
    text = builder.generate(params)["so101_follower_twin.xml"]
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == FOLLOWER_XML_SHA256


def _box_extent(model, data, name: str):
    geom = model.geom(name).id
    centre, half = data.geom_xpos[geom], model.geom_size[geom]
    return centre - half, centre + half


def test_desk_is_90_by_50_by_75_with_the_wide_side_along_plan_y(model, data):
    low, high = _box_extent(model, data, "desk_top")
    size = high - low
    assert np.isclose(high[2], TABLE_TOP, atol=1e-6)  # top surface 75 cm above the floor, level with the table top
    assert np.isclose(size[1], 0.90, atol=1e-6)  # the 90 cm side runs along y, parallel to the bed head
    assert np.isclose(size[0], 0.50, atol=1e-6)  # the 50 cm side runs along x
    # the desk stands behind the table (plan -y is world +y): its front edge is behind the table's back edge
    table = model.geom("table_collision").id
    table_back = data.geom_xpos[table][1] + model.geom_size[table][1]
    assert low[1] >= table_back - 1e-9


def test_monitor_is_parallel_to_the_desk_wide_side_and_faces_plus_x(model, data):
    low, high = _box_extent(model, data, "monitor_panel")
    size = high - low
    assert size[1] > 5 * size[0]  # a thin panel whose plane is parallel to y: its normal is plan x
    desk_low, desk_high = _box_extent(model, data, "desk_top")
    assert desk_low[0] <= low[0] and high[0] <= desk_high[0] and desk_low[1] <= low[1] and high[1] <= desk_high[1]
    assert low[2] > desk_high[2]  # above the desk top


def test_the_back_wall_clears_the_desk_and_both_walls_are_lit_alike(model, data, params):
    wall_low, wall_high = _box_extent(model, data, "room_wall")
    desk_low, desk_high = _box_extent(model, data, "desk_top")
    assert wall_low[1] > desk_high[1]  # world +y is behind the desk
    material = model.mat("tw_wall")
    for name in ("room_wall", "room_bed_head_wall"):
        assert model.geom_matid[model.geom(name).id] == material.id
    assert model.mat_emission[material.id] > 1.0  # lit by emission, so shadows do not change the wall brightness


def _geom_names(model) -> set[str]:
    return {model.geom(g).name for g in range(model.ngeom)}


def test_every_estimated_parameter_names_an_existing_key(params):
    for dotted, how in params["estimated"].items():
        top = dotted.split(".")[0]
        assert top in params, dotted
        assert isinstance(how, str) and how
