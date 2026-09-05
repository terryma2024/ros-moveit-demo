"""The generator must not accept intersecting task-object visual solids."""

import shutil
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def scene():
    import mujoco

    path = Path(__file__).parents[1] / "assets/mujoco/v5_multi_object_scene.xml"
    model = mujoco.MjModel.from_xml_path(str(path))
    data = mujoco.MjData(model)
    return mujoco, model, data


def position(scene, joint, xyz):
    mujoco, model, data = scene
    identifier = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint)
    address = model.jnt_qposadr[identifier]
    data.qpos[address : address + 7] = [*xyz, 1, 0, 0, 0]


def mutated_task_scene(tmp_path, old, new):
    import mujoco

    source = Path(__file__).parents[1] / "assets/mujoco"
    copied = tmp_path / "mujoco"
    shutil.copytree(source, copied)
    scene_path = copied / "v5_multi_object_scene.xml"
    xml = scene_path.read_text()
    assert xml.count(old) == 1
    scene_path.write_text(xml.replace(old, new, 1))
    model = mujoco.MjModel.from_xml_path(str(scene_path))
    return mujoco, model, mujoco.MjData(model)


def assert_intersecting_bottle_variant_fails_closed(scene):
    from so101_demo.adapters.perception.mujoco_scene_geometry import measure_task_scene_geometry

    position(scene, "bottle_free_joint", (0.07, -0.28, 0.19))
    _, model, data = scene
    try:
        receipt = measure_task_scene_geometry(model, data, active_cup_count=1)
    except ValueError:
        return
    assert not receipt.accepted


@pytest.mark.parametrize(
    "a,b",
    [
        (
            (-0.01108236475239045, -0.30643568681807, 0.165),
            (-0.07089558924358477, -0.2916752050674982, 0.165),
        ),
        (
            (-0.011953791423131448, -0.3234084768598057, 0.165),
            (-0.07215261978332065, -0.3161774062417523, 0.165),
        ),
        (
            (-0.02340189135551839, -0.28321527512919653, 0.165),
            (-0.06601366343122776, -0.28982635630085696, 0.165),
        ),
    ],
)
def test_retained_residual_positions_are_rejected_without_rendering(scene, a, b):
    from so101_demo.adapters.perception.mujoco_scene_geometry import measure_task_scene_geometry

    position(scene, "cup_free_joint", a)
    position(scene, "cup_b_free_joint", b)
    _, model, data = scene
    before = data.qpos.copy()
    receipt = measure_task_scene_geometry(model, data, active_cup_count=2)

    assert not receipt.accepted
    assert any(
        p.body_names == ("plastic_cup", "plastic_cup_b") and p.signed_distance_m < -0.001
        for p in receipt.pairs
    )
    assert np.array_equal(data.qpos, before)
    assert data.time == 0


def test_separated_cups_and_table_contact_are_accepted(scene):
    from so101_demo.adapters.perception.mujoco_scene_geometry import measure_task_scene_geometry

    position(scene, "cup_b_free_joint", (-0.10, -0.30, 0.165))
    _, model, data = scene
    receipt = measure_task_scene_geometry(model, data, active_cup_count=2)

    assert receipt.accepted
    assert len(receipt.pairs) == 12
    assert len(receipt.state_sha256) == 64
    assert any(p.body_names == ("plastic_cup", "table") for p in receipt.pairs)


def test_cup_bottle_intersection_is_rejected(scene):
    from so101_demo.adapters.perception.mujoco_scene_geometry import measure_task_scene_geometry

    position(scene, "bottle_free_joint", (0.07, -0.28, 0.19))
    _, model, data = scene
    receipt = measure_task_scene_geometry(model, data, active_cup_count=1)

    assert not receipt.accepted
    assert any(
        p.body_names == ("plastic_cup", "orange_bottle") and p.signed_distance_m < -0.001
        for p in receipt.pairs
    )


def test_renamed_rendered_bottle_solid_is_measured_or_rejected(tmp_path):
    changed = mutated_task_scene(
        tmp_path,
        'name="bottle_visual"',
        'name="bottle_shell"',
    )
    assert_intersecting_bottle_variant_fails_closed(changed)


def test_unnamed_rendered_bottle_solid_is_measured_or_rejected(tmp_path):
    changed = mutated_task_scene(
        tmp_path,
        'name="bottle_visual" ',
        "",
    )
    assert_intersecting_bottle_variant_fails_closed(changed)


def test_descendant_rendered_bottle_solid_is_measured_or_rejected(tmp_path):
    direct = """      <geom name="bottle_visual" type="cylinder" size="0.025 0.070"
            group="0" contype="0" conaffinity="0" material="bottle_material"/>"""
    descendant = """      <body name="bottle_shell_child">
        <geom name="bottle_descendant_visual" type="cylinder" size="0.025 0.070"
              group="0" contype="0" conaffinity="0" material="bottle_material"/>
      </body>"""
    changed = mutated_task_scene(tmp_path, direct, descendant)
    assert_intersecting_bottle_variant_fails_closed(changed)


def test_invisible_collision_proxies_are_excluded_from_visual_measurement(scene):
    from so101_demo.adapters.perception.mujoco_scene_geometry import measure_task_scene_geometry

    _, model, data = scene
    receipt = measure_task_scene_geometry(model, data, active_cup_count=1)
    pair = next(
        item
        for item in receipt.pairs
        if item.body_names == ("plastic_cup", "orange_bottle")
    )
    assert pair.primitive_pair_count == 26
    assert all("collision" not in name for name in pair.geom_names)


def test_parked_inactive_cups_are_not_physical_targets(scene):
    from so101_demo.adapters.perception.mujoco_scene_geometry import measure_task_scene_geometry

    position(scene, "cup_free_joint", (2, 2, 2))
    position(scene, "cup_b_free_joint", (2, 2, 2))
    _, model, data = scene
    receipt = measure_task_scene_geometry(model, data, active_cup_count=0)

    assert receipt.accepted
    assert len(receipt.pairs) == 3
    assert all(p.body_names[0] == "orange_bottle" for p in receipt.pairs)


@pytest.mark.parametrize("count", [-1, 3, True])
def test_invalid_active_count_fails_closed(scene, count):
    from so101_demo.adapters.perception.mujoco_scene_geometry import measure_task_scene_geometry

    _, model, data = scene
    with pytest.raises(ValueError, match="active_cup_count"):
        measure_task_scene_geometry(model, data, active_cup_count=count)


def test_nonfinite_state_fails_closed_before_forward(scene):
    from so101_demo.adapters.perception.mujoco_scene_geometry import measure_task_scene_geometry

    _, model, data = scene
    data.qpos[0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        measure_task_scene_geometry(model, data, active_cup_count=1)


def test_missing_task_body_fails_closed():
    import mujoco
    from so101_demo.adapters.perception.mujoco_scene_geometry import measure_task_scene_geometry

    model = mujoco.MjModel.from_xml_string("<mujoco><worldbody/></mujoco>")
    with pytest.raises(ValueError, match="body"):
        measure_task_scene_geometry(model, mujoco.MjData(model), active_cup_count=1)


def test_unsupported_visual_primitive_fails_closed(scene):
    from so101_demo.adapters.perception.mujoco_scene_geometry import measure_task_scene_geometry

    mujoco, model, data = scene
    geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "bottle_visual")
    model.geom_type[geom] = int(mujoco.mjtGeom.mjGEOM_SPHERE)
    with pytest.raises(ValueError, match="primitive"):
        measure_task_scene_geometry(model, data, active_cup_count=1)


def test_enabled_renderer_rejects_penetration_before_rgb(scene, monkeypatch):
    from types import SimpleNamespace

    from so101_demo.adapters.perception.mujoco_dataset import DatasetScenario, MuJoCoDatasetRenderer
    from so101_demo.adapters.perception.mujoco_scene_geometry import ScenePenetrationError

    class ForbiddenRenderer:
        def disable_segmentation_rendering(self):
            raise AssertionError("RGB must not be reached for a penetrating scene")

    _, model, data = scene
    position(scene, "bottle_free_joint", (0.07, -0.28, 0.19))
    renderer = MuJoCoDatasetRenderer.__new__(MuJoCoDatasetRenderer)
    renderer._model, renderer._data = model, data
    renderer._config = SimpleNamespace(require_nonpenetrating_scene=True)
    renderer._renderer = ForbiddenRenderer()
    monkeypatch.setattr(renderer, "_prepare", lambda random, scenario: None)
    with pytest.raises(ScenePenetrationError):
        renderer._render_attempt(np.random.default_rng(1), DatasetScenario.ONE_CUP_DISTRACTORS)


def test_enabled_all_scenarios_stop_at_deterministic_retry_limit():
    from so101_demo.adapters.perception.mujoco_dataset import (
        DatasetScenario,
        SceneGeometry,
        select_bounded_render,
    )
    from so101_demo.adapters.perception.mujoco_scene_geometry import ScenePenetrationError

    attempts = []

    def penetrating(random):
        attempts.append(float(random.random()))
        raise ScenePenetrationError("intersecting task solids")

    for _ in range(2):
        with pytest.raises(RuntimeError, match="3 deterministic attempts"):
            select_bounded_render(
                123,
                DatasetScenario.TWO_CUPS,
                penetrating,
                SceneGeometry(maximum_deterministic_attempts=3),
                require_nonpenetrating_scene=True,
            )
    assert len(attempts) == 6
    assert attempts[:3] == attempts[3:]
    assert len(set(attempts[:3])) == 3


def test_enabled_generation_rejects_missing_geometry_receipt():
    from so101_demo.adapters.perception.mujoco_dataset import (
        DatasetScenario,
        RawRender,
        SceneGeometry,
        select_bounded_render,
    )

    render = RawRender(np.zeros((4, 4, 3), dtype=np.uint8), np.full((4, 4), -1), np.array([0]), {})
    with pytest.raises(ValueError, match="geometry receipt"):
        select_bounded_render(
            123,
            DatasetScenario.NO_CUP,
            lambda random: render,
            SceneGeometry(),
            require_nonpenetrating_scene=True,
        )


def test_nonpenetration_policy_is_explicit_and_legacy_default_is_preserved(tmp_path):
    from so101_demo.adapters.perception.mujoco_dataset import DatasetConfig

    path = tmp_path / "model.xml"
    path.write_text("<mujoco/>")
    kwargs = dict(
        mjcf_path=path, split_counts={"train": 1, "val": 1, "test": 1}, generator_commit="a" * 40
    )
    assert DatasetConfig(**kwargs).require_nonpenetrating_scene is False
    assert DatasetConfig(**kwargs, require_nonpenetrating_scene=True).require_nonpenetrating_scene
    with pytest.raises(ValueError, match="require_nonpenetrating_scene"):
        DatasetConfig(**kwargs, require_nonpenetrating_scene="false")


def test_empty_receipt_cannot_certify_geometry():
    from so101_demo.adapters.perception.mujoco_scene_geometry import TaskSceneGeometry

    with pytest.raises(ValueError, match="pairs"):
        TaskSceneGeometry("a" * 64, ())


def test_nonfinite_pair_cannot_be_serialized_as_valid_truth():
    from so101_demo.adapters.perception.mujoco_scene_geometry import TaskGeometryPair

    with pytest.raises(ValueError, match="finite"):
        TaskGeometryPair(("cup", "bottle"), ("a", "b"), float("nan"), 1)


@pytest.mark.parametrize("count", [0, -1, True, 1.0])
def test_pair_requires_positive_non_boolean_integer_primitive_count(count):
    from so101_demo.adapters.perception.mujoco_scene_geometry import TaskGeometryPair

    with pytest.raises(ValueError, match="primitive.*count"):
        TaskGeometryPair(("cup", "bottle"), ("a", "b"), 0.1, count)


@pytest.mark.parametrize(
    "names",
    [
        ("", "b"),
        ("a", ""),
        ("only",),
        ("a", "b", "c"),
        ("a", 1),
    ],
)
def test_pair_requires_exactly_two_nonempty_geom_name_strings(names):
    from so101_demo.adapters.perception.mujoco_scene_geometry import TaskGeometryPair

    with pytest.raises(ValueError, match="geom.*names"):
        TaskGeometryPair(("cup", "bottle"), names, 0.1, 1)


def test_writer_rejects_supplied_receipt_with_malformed_pair_fields(scene, tmp_path):
    from so101_demo.adapters.perception.mujoco_dataset import (
        DatasetConfig,
        RawRender,
        generate_dataset,
    )
    from so101_demo.adapters.perception.mujoco_scene_geometry import (
        TaskGeometryPair,
        TaskSceneGeometry,
        measure_task_scene_geometry,
    )

    _, model, data = scene
    valid = measure_task_scene_geometry(model, data, active_cup_count=0)
    malformed_pairs = []
    for pair in valid.pairs:
        malformed = object.__new__(TaskGeometryPair)
        object.__setattr__(malformed, "body_names", pair.body_names)
        object.__setattr__(malformed, "geom_names", ("", ""))
        object.__setattr__(malformed, "signed_distance_m", pair.signed_distance_m)
        object.__setattr__(malformed, "primitive_pair_count", 0)
        malformed_pairs.append(malformed)
    malformed_receipt = object.__new__(TaskSceneGeometry)
    object.__setattr__(malformed_receipt, "state_sha256", valid.state_sha256)
    object.__setattr__(malformed_receipt, "pairs", tuple(malformed_pairs))

    class SuppliedRenderer:
        def render(self, seed, scenario):
            return RawRender(
                np.zeros((4, 4, 3), dtype=np.uint8),
                np.full((4, 4), -1),
                np.array([0]),
                {},
                geometry_receipt=malformed_receipt,
            )

    model_path = tmp_path / "toy.xml"
    model_path.write_text("<mujoco/>")
    splits = ("train", "val", "test")
    config = DatasetConfig(
        mjcf_path=model_path,
        generator_commit="a" * 40,
        split_counts={split: 1 for split in splits},
        scenario_quotas={split: {"no_cup": 1} for split in splits},
        require_nonpenetrating_scene=True,
    )
    output = tmp_path / "malformed-receipt-dataset"
    with pytest.raises(ValueError, match="geometry receipt|primitive|geom"):
        generate_dataset(config, output, renderer=SuppliedRenderer())
    assert not list(output.rglob("*.png"))


@pytest.mark.parametrize("enabled,with_receipt", [(True, True), (True, False), (False, False)])
def test_writer_enforces_and_persists_explicit_geometry_policy(
    scene, tmp_path, enabled, with_receipt
):
    import json

    from so101_demo.adapters.perception.mujoco_dataset import (
        DatasetConfig,
        RawRender,
        generate_dataset,
    )
    from so101_demo.adapters.perception.mujoco_scene_geometry import measure_task_scene_geometry

    _, model, data = scene
    receipt = measure_task_scene_geometry(model, data, active_cup_count=0) if with_receipt else None

    class ToyRenderer:
        def render(self, seed, scenario):
            return RawRender(
                np.zeros((4, 4, 3), dtype=np.uint8),
                np.full((4, 4), -1),
                np.array([0]),
                {},
                geometry_receipt=receipt,
            )

    path = tmp_path / "toy.xml"
    path.write_text("<mujoco/>")
    splits = ("train", "val", "test")
    config = DatasetConfig(
        mjcf_path=path,
        generator_commit="a" * 40,
        split_counts={s: 1 for s in splits},
        scenario_quotas={s: {"no_cup": 1} for s in splits},
        require_nonpenetrating_scene=enabled,
    )
    output = tmp_path / "toy-dataset"
    if enabled and not with_receipt:
        with pytest.raises(ValueError, match="geometry receipt"):
            generate_dataset(config, output, renderer=ToyRenderer())
        assert not list(output.rglob("*.png"))
        return
    manifest = generate_dataset(config, output, renderer=ToyRenderer())
    truths = [json.loads(p.read_text()) for p in (output / "truth").rglob("*.json")]
    assert len(truths) == 3
    if enabled:
        assert manifest["scene_geometry_policy"] == "task-visual-nonpenetration-v1"
        for truth in truths:
            assert truth["scene_geometry"]["accepted"] is True
            assert truth["scene_geometry"]["state_sha256"] == receipt.state_sha256
            assert len(truth["scene_geometry"]["pairs"]) == 3
    else:
        assert "scene_geometry_policy" not in manifest
        assert all("scene_geometry" not in truth for truth in truths)


@pytest.mark.parametrize("sha", ["", "x" * 64, "a" * 63])
def test_receipt_rejects_invalid_state_identity(scene, sha):
    from dataclasses import replace

    from so101_demo.adapters.perception.mujoco_scene_geometry import measure_task_scene_geometry

    _, model, data = scene
    receipt = measure_task_scene_geometry(model, data, active_cup_count=0)
    with pytest.raises(ValueError, match="state_sha256"):
        replace(receipt, state_sha256=sha)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "foreign", "wrong_count"])
def test_selector_rejects_wrong_receipt_scope(scene, mutation):
    from dataclasses import replace

    from so101_demo.adapters.perception.mujoco_dataset import (
        DatasetScenario,
        RawRender,
        SceneGeometry,
        select_bounded_render,
    )
    from so101_demo.adapters.perception.mujoco_scene_geometry import measure_task_scene_geometry

    _, model, data = scene
    receipt = measure_task_scene_geometry(model, data, active_cup_count=0)
    pairs = receipt.pairs
    if mutation == "missing":
        pairs = pairs[:-1]
    elif mutation == "duplicate":
        pairs = pairs + pairs[:1]
    elif mutation == "foreign":
        pairs = (replace(pairs[0], body_names=("foreign", "table")),) + pairs[1:]
    scenario = DatasetScenario.TWO_CUPS if mutation == "wrong_count" else DatasetScenario.NO_CUP
    with pytest.raises(ValueError, match="geometry receipt.*scope"):
        changed = replace(receipt, pairs=pairs)
        raw = RawRender(
            np.zeros((4, 4, 3), dtype=np.uint8),
            np.full((4, 4), -1),
            np.array([0]),
            {},
            geometry_receipt=changed,
        )
        select_bounded_render(
            123, scenario, lambda rng: raw, SceneGeometry(), require_nonpenetrating_scene=True
        )


def test_retry_accepts_first_valid_scene_and_propagates_invalid_measurement(scene):
    from so101_demo.adapters.perception.mujoco_dataset import (
        DatasetScenario,
        RawRender,
        SceneGeometry,
        select_bounded_render,
    )
    from so101_demo.adapters.perception.mujoco_scene_geometry import (
        ScenePenetrationError,
        measure_task_scene_geometry,
    )

    _, model, data = scene
    receipt = measure_task_scene_geometry(model, data, active_cup_count=0)
    raw = RawRender(
        np.zeros((4, 4, 3), dtype=np.uint8),
        np.full((4, 4), -1),
        np.array([0]),
        {},
        geometry_receipt=receipt,
    )
    attempts = []

    def attempt(rng):
        attempts.append(float(rng.random()))
        if len(attempts) == 1:
            raise ScenePenetrationError("penetration")
        return raw

    assert (
        select_bounded_render(
            123, DatasetScenario.NO_CUP, attempt, SceneGeometry(), require_nonpenetrating_scene=True
        )
        is raw
    )
    assert len(attempts) == 2

    def invalid(rng):
        raise ValueError("unsupported primitive")

    with pytest.raises(ValueError, match="unsupported primitive"):
        select_bounded_render(
            123, DatasetScenario.NO_CUP, invalid, SceneGeometry(), require_nonpenetrating_scene=True
        )
