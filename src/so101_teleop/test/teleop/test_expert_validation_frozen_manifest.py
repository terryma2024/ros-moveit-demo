"""Production manifests freeze installed inputs, not Web golden fixtures."""

import asyncio
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import httpx
import pytest

from so101_teleop.expert_validation import catalog
from so101_teleop.expert_validation.api import create_expert_validation_app
from so101_teleop.expert_validation.artifacts import ValidationArtifactRegistry
from so101_teleop.expert_validation.production import ProductionExpertValidationService
from so101_teleop.expert_validation.service import ServiceConflict
from so101_teleop.expert_validation.store import SupervisorStore


INPUTS = {
    "catalog": "config/mujoco/moveit_expert_validation_points_v1.yaml",
    "parallel_config": "config/mujoco/parallel_batch_v1.yaml",
    "adaptive_config": "config/mujoco/parallel_adaptive_workers_v1.yaml",
    "execution_policy": "config/mujoco/headless_execution.yaml",
    "dynamic_policy": "config/policies/dynamic_cup_pick/v1/mujoco.yaml",
    "placement_policy": "config/policies/light_cup_wall_pick/v1/mujoco.yaml",
    "task_scene": "config/mujoco/task_scene.yaml",
    "scene": "assets/mujoco/scene.xml",
    "target_mesh": "assets/mujoco/assets/target_landing_tolerance_ring.obj",
    "anchors": "config/mujoco/rgbd_task_points.yaml",
}
DEMO_SOURCE = Path(__file__).resolve().parents[3] / "so101_demo_py"


class SameThreadApi:
    """Keep the real SQLite authority on its creating event-loop thread."""

    def __init__(self, service):
        self.app = create_expert_validation_app(service)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def request(self, method, path, **kwargs):
        async def request():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app), base_url="http://test",
            ) as client:
                return await client.request(method, path, **kwargs)
        return asyncio.run(request())


def _installed_service(tmp_path, monkeypatch):
    prefix = tmp_path / "install/so101_demo_py"
    share = prefix / "share/so101_demo_py"
    for relative in INPUTS.values():
        destination = share / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DEMO_SOURCE / relative, destination)
    monkeypatch.setattr(catalog, "get_package_share_directory", lambda _name: str(share))
    layout = SimpleNamespace(
        source_commit="a" * 40, demo_prefix=prefix,
        points_path=share / INPUTS["catalog"],
        parallel_config_path=share / INPUTS["parallel_config"],
        adaptive_config_path=share / INPUTS["adaptive_config"],
    )
    store = SupervisorStore.open((tmp_path / "store").resolve())
    service = ProductionExpertValidationService(
        layout=layout, registry=None, artifacts=ValidationArtifactRegistry(),
        store=store, supervisor=None, lease_service=None,
        current_source_config_sha256=lambda: hashlib.sha256(
            layout.parallel_config_path.read_bytes()
        ).hexdigest(),
    )
    return service, share


@pytest.mark.parametrize("count", [4, 12, 20])
def test_production_api_freezes_only_selected_points_and_installed_geometry(
    tmp_path, monkeypatch, count,
):
    service, share = _installed_service(tmp_path, monkeypatch)
    try:
        with SameThreadApi(service) as client:
            response = client.request("POST", "/expert-validation/manifests", json={"total_points": count})
            assert response.status_code == 200
            document = response.json()
            top_view = document["top_view"]
            assert len(top_view["points"]) == count
            assert [point["id"] for point in top_view["points"]] == [
                point["id"] for point in document["points"]
            ]
            if count == 12:
                assert [point["id"] for point in top_view["points"]] == [
                    "task_start", "cup_test_forward_5cm", "cup_test_left_5cm", "cup_test_right_5cm",
                    "sample_01_near_left", "sample_02_near_center", "sample_03_near_right",
                    "sample_06_mid_left", "sample_07_mid_center", "sample_08_mid_right",
                    "sample_13_far_center", "sample_14_far_right",
                ]
                assert top_view["points"][-1]["display_id"] == "P12"
                assert top_view["points"][-1]["projected_px"] == pytest.approx([668.37082, 636.8563])
            assert top_view["points"][0]["projected_px"] == pytest.approx([626.8, 557.2])
            assert top_view["projection"]["pixels_per_m"] == 1340.0
            assert top_view["geometry"]["table_bounds"] == [-0.25, 0.25, -0.5, 0.1]
            assert top_view["geometry"]["target_center"] == [-0.08, -0.25]
            assert top_view["geometry"]["candidate_bounds"] == [-0.045, 0.08, -0.34, -0.24]
            assert top_view["cup_footprint_radius_px"] == pytest.approx(53.6)
            assert top_view["target_tolerance_radius_px"] == pytest.approx(13.4)
            assert top_view["marker_radius_px"] == 10.0
            for name, relative in INPUTS.items():
                assert document["source_hashes"][name] == hashlib.sha256(
                    (share / relative).read_bytes()
                ).hexdigest()
            canonical = service.get_manifest(document["manifest_id"]).canonical_document
            assert canonical["manifest_id"] == document["manifest_id"]
            assert document["manifest_sha256"] == hashlib.sha256(json.dumps(
                canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode()).hexdigest()
            assert str(share) not in response.text
            fetched = client.request("GET", f"/expert-validation/manifests/{document['manifest_id']}")
            assert fetched.json() == document
    finally:
        service.close()


@pytest.mark.parametrize("changed_input", list(INPUTS))
def test_input_drift_preserves_frozen_map_after_reopen_but_fences_selection(
    tmp_path, monkeypatch, changed_input,
):
    service, share = _installed_service(tmp_path, monkeypatch)
    try:
        original = service.create_manifest_from_count(4)
        path = share / INPUTS[changed_input]
        with path.open("ab") as stream:
            stream.write(b"\n")
        service.store.close()
        service.store = SupervisorStore.open((tmp_path / "store").resolve())
        restored = service.get_manifest_api(original["manifest_id"])
        assert restored["stale"] is True
        assert restored["top_view"] == original["top_view"]
        assert restored["manifest_sha256"] == original["manifest_sha256"]
        with pytest.raises(ServiceConflict, match="VALIDATION_MANIFEST_STALE"):
            service._selection(original["manifest_id"])
    finally:
        service.close()


def test_inconsistent_installed_target_policy_fails_before_manifest_persistence(
    tmp_path, monkeypatch,
):
    service, share = _installed_service(tmp_path, monkeypatch)
    try:
        path = share / INPUTS["scene"]
        path.write_text(path.read_text().replace('pos="-0.08 -0.05 0.0201"',
                                                'pos="-0.07 -0.05 0.0201"'))
        with pytest.raises(ServiceConflict, match="VALIDATION_MANIFEST_GEOMETRY_INVALID"):
            service.create_manifest_from_count(4)
        assert service.store._connection.execute("SELECT count(*) FROM manifests").fetchone()[0] == 0
    finally:
        service.close()
