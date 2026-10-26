"""Random draws from every appearance pool keep the stripped physics fingerprint of their layout's nominal scene (indoor P3 appearance library)."""

from __future__ import annotations

import pytest

mujoco = pytest.importorskip("mujoco")

from paths import PACKAGE_ROOT  # noqa: E402
from so101_demo.act import indoor_assets, scene_variant  # noqa: E402
from so101_demo.act import indoor_yolo_dataset as iyd  # noqa: E402
from so101_demo.act.physics_fingerprint import stripped_physics_fingerprint_of_file  # noqa: E402

ACT_ASSETS = PACKAGE_ROOT / "assets/mujoco/act"
PER_SPLIT = 14


@pytest.mark.parametrize("split", ["train", "val", "test"])
def test_draws_from_each_split_pool_compile_and_keep_the_nominal_stripped_fingerprint(indoor_pool_act, tmp_path, split):
    assets = iyd.asset_pools(indoor_pool_act)
    inventories = iyd.layout_inventories(ACT_ASSETS)
    plan = iyd.build_plan({split: PER_SPLIT}, 20261025, inventories, assets)
    nominal = {}
    seen = set()
    for item in plan:
        layout = item["layout"]
        nominal_dir = iyd.materialize_layout(indoor_pool_act, layout, tmp_path / layout)
        if layout not in nominal:
            nominal[layout] = stripped_physics_fingerprint_of_file(nominal_dir / iyd.NOMINAL_SCENE)
        realized = scene_variant.realize(nominal_dir, item["variant"])
        path = tmp_path / f"{item['sample_id']}.xml"
        path.write_text(realized.xml_text)
        mujoco.MjModel.from_xml_path(str(path))
        assert stripped_physics_fingerprint_of_file(path) == nominal[layout], item["sample_id"]
        seen |= {item["variant"]["set"][f"{surface}.texture"] for surface in indoor_assets.SURFACES}
    assert all(texture in {t for ids in assets["pools"][split].values() for t in ids} for texture in seen)
    assert any(texture.startswith("proc/") for texture in seen)


def test_draws_over_all_three_layouts_are_covered_for_the_test_split(indoor_pool_act):
    plan = iyd.build_plan({"test": 40}, 3, iyd.layout_inventories(ACT_ASSETS), iyd.asset_pools(indoor_pool_act))
    assert {item["layout"] for item in plan} == {"A", "B", "C"}
