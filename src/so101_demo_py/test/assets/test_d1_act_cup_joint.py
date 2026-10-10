"""D1: the ACT cup free joint is explicit (damping 0.01, frictionloss 0, armature 0), nothing else moved, every pinned
ACT identity follows, and the physics regressions that motivated the change hold (bounds from dfacts-exp)."""
import json
import math
from pathlib import Path

import numpy as np
import pytest
import yaml

from act_identity import ACT_MODEL_SHA256, ACT_SCENE, ACT_SCENE_SHA256, PACKAGE

pytestmark = pytest.mark.fast
MOTION = PACKAGE / "config/policies/light_cup_wall_pick/mujoco.yaml"
# sha256 of the files: the main/robot-default ones as they were BEFORE D1 (must not change); act/so101.xml carries the R11 official ranges.
UNCHANGED = {
    "assets/mujoco/act/so101.xml": "264dd124c27d06a14a96baf2cc8bf7789c407a81a9ca648159957bf7713eebfe",
    "assets/mujoco/scene.xml": "fec97df90ada01bed12e09110986caac52881312360c5549763dcb2a02d99d9c",
    "assets/mujoco/multi_object_scene.xml": "dbe85e6cd3e2a3cefaf6e2a1621f449cf1a29e87680e00d4b26f53d3fdae0237",
    "assets/mujoco/so101.xml": "f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca",
}


def sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_act():
    import mujoco
    return mujoco.MjModel.from_xml_path(str(ACT_SCENE))


def test_the_act_cup_joint_carries_the_three_explicit_values():
    import mujoco
    model = load_act()
    joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint")
    start = int(model.jnt_dofadr[joint])
    assert list(model.dof_damping[start:start + 6]) == [0.01] * 6
    assert list(model.dof_frictionloss[start:start + 6]) == [0.0] * 6
    assert list(model.dof_armature[start:start + 6]) == [0.0] * 6
    text = ACT_SCENE.read_text()
    assert 'name="cup_free_joint" type="free" damping="0.01" frictionloss="0" armature="0"' in text


@pytest.mark.parametrize("relative", sorted(UNCHANGED))
def test_robot_defaults_and_the_non_act_scenes_are_byte_identical_to_pre_d1(relative):
    assert sha(PACKAGE / relative) == UNCHANGED[relative]


def _walk(value, keys):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and isinstance(item, str):
                yield key, item
            yield from _walk(item, keys)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item, keys)


PIN_MODULES = ("contact_collector", "contact_diagnostic")


@pytest.mark.parametrize("module", PIN_MODULES)
def test_every_pinned_module_identity_is_the_derived_one(module):
    import importlib
    loaded = importlib.import_module("so101_demo.act." + module)
    pins = {name: value for name, value in vars(loaded).items()
            if name in ("_SCENE_SHA", "_MODEL_SHA", "_SCENE_SHA256", "_MODEL_SHA256")}
    assert pins, module
    for name, value in pins.items():
        assert value == (ACT_SCENE_SHA256 if "SCENE" in name else ACT_MODEL_SHA256), (module, name)


def test_every_pinned_json_identity_is_the_derived_one():
    # CP-3529: the eight Task 6 / held-cup sealed profiles bound to the old model were retired; any pin that remains
    # under config/mujoco/act must still be the derived identity.
    for path in sorted((PACKAGE / "config/mujoco/act").glob("*.json")):
        for key, value in _walk(json.loads(path.read_text()), {"scene_sha256", "model_sha256"}):
            assert value == (ACT_SCENE_SHA256 if key.startswith("scene") else ACT_MODEL_SHA256), (path.name, key)


def test_no_old_act_identity_is_left_outside_docs():
    old = ("4db4" + "8e35", "3c87" + "6e7b")
    hits = [str(path.relative_to(PACKAGE)) for folder in ("src", "config", "test")
            for path in (PACKAGE / folder).rglob("*") if path.is_file() and path.suffix in {".py", ".json", ".yaml", ".md"}
            and any(prefix in path.read_text(errors="ignore") for prefix in old)]
    assert hits == []


# ---- physics regressions (dfacts-exp exp_ab.py; bounds = observed + margin, stated per assertion) ----------------------

def test_rest_on_the_table_for_ten_seconds_is_stable():
    import mujoco
    model = load_act()
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, 0)
    joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint")
    qa, va = int(model.jnt_qposadr[joint]), int(model.jnt_dofadr[joint])
    p0 = data.qpos[qa:qa + 3].copy()
    quat = lambda: data.qpos[qa + 3:qa + 7]
    yaw = lambda q: math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))
    y0, vmax, ke, zs = yaw(quat()), 0.0, [], []
    inertia = np.array([2.95e-5, 2.95e-5, 3.2e-5])
    for _ in range(5000):
        data.ctrl[:] = 0
        mujoco.mj_step(model, data)
        v, w = data.qvel[va:va + 3], data.qvel[va + 3:va + 6]
        vmax = max(vmax, float(np.linalg.norm(v)))
        ke.append(0.5 * 0.02 * float(v @ v) + 0.5 * float((inertia * w * w).sum()))
        zs.append(float(data.qpos[qa + 2]))
    drift = data.qpos[qa:qa + 3] - p0
    # observed (damping .01, f0, a0): xy 8e-4 mm, z -0.153 mm, yaw -3.6e-5 deg, KE(2nd half) max 2.6e-9 J, z std 0.2 um, vmax .0196
    assert np.linalg.norm(drift[:2]) < 1e-5            # 0.01 mm
    assert abs(drift[2]) < 3e-4                        # 0.3 mm
    assert abs(math.degrees(yaw(quat()) - y0)) < 1e-3
    assert max(ke[2500:]) < 2e-8 and vmax < 0.05   # 8x the observed residual; an energy-growing cup is orders above
    assert float(np.std(zs[2500:])) < 2e-6             # 2 um


def carry(rate):
    import mujoco
    model = load_act()
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, 0)
    policy = yaml.safe_load(MOTION.read_bytes())
    close, pre = policy["gripper_actions"]["grasp_close_q6"], policy["gripper_actions"]["preopen_q6"]
    addr = [int(model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, str(i))]) for i in range(1, 7)]
    joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint")
    qa = int(model.jnt_qposadr[joint])
    start = np.array(policy["states"]["DESCEND"]["waypoints"][-1] + [pre])
    closed = start.copy()
    closed[5] = close
    lift = np.array(policy["states"]["LIFT"]["waypoints"][0] + [close])
    data.qpos[addr] = start
    data.qpos[qa:qa + 3] = [.02, -.28, .165]
    data.qpos[qa + 3:qa + 7] = [1, 0, 0, 0]
    data.ctrl[:6] = start
    mujoco.mj_forward(model, data)
    gripper = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "gripper")
    cup = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "plastic_cup")
    for _, duration, first, last in (("settle", .5, start, start), ("close", 2., start, closed),
                                     ("lift", 2., closed, lift), ("hold", .5, lift, lift)):
        count = round(duration / model.opt.timestep)
        for index in range(count):
            data.ctrl[:6] = first + (last - first) * (index + 1) / count
            mujoco.mj_step(model, data)

    def measure():
        force = comp = 0.0
        for k in range(data.ncon):
            contact = data.contact[k]
            geoms = [int(contact.geom[0]), int(contact.geom[1])]
            is_cup = [model.geom_bodyid[g] == cup for g in geoms]
            if is_cup[0] == is_cup[1]:
                continue
            other = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geoms[1] if is_cup[0] else geoms[0])
            vector = np.zeros(6)
            mujoco.mj_contactForce(model, data, k, vector)
            force += max(0.0, vector[0])
            if other.startswith(("fixed_fingertip", "moving_fingertip")):
                comp = max(comp, -contact.dist)
        return force, comp

    yaw = lambda matrix: math.atan2(matrix[1, 0], matrix[0, 0])
    quat_yaw = lambda q: math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))
    hold = measure()
    g0, c0 = yaw(data.xmat[gripper].reshape(3, 3)), quat_yaw(data.qpos[qa + 3:qa + 7])
    steps = round(0.35 / rate / model.opt.timestep) + 250
    peak_force = peak_comp = 0.0
    for index in range(steps):
        data.ctrl[:6] = lift
        data.ctrl[0] = lift[0] + rate * min(index + 1, steps - 250) * model.opt.timestep
        mujoco.mj_step(model, data)
        force, comp = measure()
        peak_force, peak_comp = max(peak_force, force), max(peak_comp, comp)
    error = (yaw(data.xmat[gripper].reshape(3, 3)) - g0) - (quat_yaw(data.qpos[qa + 3:qa + 7]) - c0)
    return hold, peak_force, peak_comp, error


@pytest.mark.parametrize("rate, force_bound, comp_bound", [(0.1, 1.8, 1.15e-4), (0.2, 2.0, 1.3e-4)])
def test_a_035_rad_base_yaw_ramp_no_longer_runs_away(rate, force_bound, comp_bound):
    hold, force, comp, error = carry(rate)
    # observed: hold 1.55 N / 9.8e-5 m; 0.1 rad/s 1.56 N / 1.03e-4 m; 0.2 rad/s 1.62 N / 1.11e-4 m; yaw error <= 7e-4 rad.
    # The inherited joint defaults gave 33.7 N / 4.8e-4 m at 0.1 and 77 N at 0.2, so these bounds (observed +12..23%)
    # separate the two regimes by more than an order of magnitude.
    assert hold[0] < 1.7 and hold[1] < 1.1e-4
    assert force <= force_bound and comp <= comp_bound
    assert abs(error) < 0.01
