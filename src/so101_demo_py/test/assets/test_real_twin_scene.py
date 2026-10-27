"""The real-twin scene: the human's real SO-101 table with a cube-to-bowl task, built from `twin_params.yaml`.

Every assertion reads files of the repository; no test assumes a file outside it. Plan (x, y) cm map to world
(x / 100, -y / 100) m, the follower pan axis is world (0, 0) and the table top is at z = 0.75 m.
"""

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
    assert len(changed) == 2  # the base body position and the 3d_printed colour


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


def test_side_camera_is_45_cm_above_the_table_and_looks_down_at_the_workspace(model, data, params):
    camera = model.camera("side_camera").id
    assert abs(data.cam_xpos[camera][2] - (TABLE_TOP + 0.45)) < 1e-3
    assert tuple(model.cam_resolution[camera]) == (640, 480)
    assert model.cam_fovy[camera] == 70.0
    forward = -data.cam_xmat[camera].reshape(3, 3)[:, 2]
    aim = np.array([-0.02, -0.18, TABLE_TOP])
    to_aim = (aim - data.cam_xpos[camera]) / np.linalg.norm(aim - data.cam_xpos[camera])
    assert np.dot(forward, to_aim) > 0.9999
    assert forward[2] < -0.5  # pitched down


def test_the_wrist_camera_mount_is_the_existing_one(model):
    camera = model.camera("wrist_camera").id
    assert model.cam_fovy[camera] == 90.0
    assert tuple(model.cam_resolution[camera]) == (640, 480)


def test_leader_is_visual_only_and_mirrored(model, params):
    leader = [g for g in range(model.ngeom) if model.geom(g).name.startswith("leader_")]
    assert leader
    for geom in leader:
        assert model.geom_contype[geom] == 0 and model.geom_conaffinity[geom] == 0
    bodies = [b for b in range(model.nbody) if model.body(b).name.startswith("leader_")]
    assert all(model.body_dofnum[b] == 0 and model.body_mass[b] == 0 for b in bodies)
    assert len([n for n in range(model.njnt) if model.jnt_type[n] != mujoco.mjtJoint.mjJNT_FREE]) == 6


def test_leader_equals_the_follower_at_the_rest_pose_shifted_to_x_41_9(model, params):
    state = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, state, model.key("rest_pose").id)
    mujoco.mj_forward(model, state)
    shift = np.array([0.419, 0.0, 0.0])
    checked = 0
    for geom in range(model.ngeom):
        name = model.geom(geom).name
        if name.endswith("_visual_00") or name.endswith("_pad_visual") or name.endswith("_visual_01"):
            twin = model.geom(f"leader_{name}").id if name and f"leader_{name}" in _geom_names(model) else None
            if twin is None:
                continue
            assert np.allclose(state.geom_xpos[twin] - state.geom_xpos[geom], shift, atol=1e-6), name
            assert np.allclose(state.geom_xmat[twin], state.geom_xmat[geom], atol=1e-6), name
            checked += 1
    assert checked >= 8


def _geom_names(model) -> set[str]:
    return {model.geom(g).name for g in range(model.ngeom)}


def test_every_estimated_parameter_names_an_existing_key(params):
    for dotted, how in params["estimated"].items():
        top = dotted.split(".")[0]
        assert top in params, dotted
        assert isinstance(how, str) and how
