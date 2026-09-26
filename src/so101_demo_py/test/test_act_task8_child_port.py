"""Only a calibrated admitted child may compose the physical SEARCH port."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import mujoco
import pytest

from so101_demo.act.calibration import REQUIRED_MEASUREMENTS
from so101_demo.act.head_search_binding import HeadSearchBinding
from so101_demo.act.task8_manifest import build_task8_live_manifest
from so101_demo.adapters.act.physics import model_sha256
from so101_demo.adapters.act.task8_child_port import build_task8_child_search_port
from so101_demo.adapters.act.task8_search_port import Task8SearchPhasePort


PACKAGE = Path(__file__).parents[1]


def _report(tmp_path):
    sample = tmp_path / "sample.json"
    sample.write_text("test measurement sample\n")
    digest = hashlib.sha256(sample.read_bytes()).hexdigest()
    measurements = {}
    for name, (unit, size) in REQUIRED_MEASUREMENTS.items():
        value = [1.0] * size if size > 1 else 1.0
        if name == "max_fine_corrections":
            value = 3
        measurements[name] = {
            "value": value, "unit": unit, "sample_path": str(sample),
            "sample_sha256": digest,
        }
    measurements["path_step_s"]["value"] = 0.002
    measurements["path_clearance_m"]["value"] = 0.002
    measurements["max_age_s"]["value"] = 0.1
    measurements["max_skew_s"]["value"] = 0.005
    measurements["stop_latency_s"]["value"] = 2.0
    return {
        "schema_version": 1, "status": "TASK8_READY",
        "source_commit": "a" * 40, "config_sha256": "b" * 64,
        "measurements": measurements,
        "checks": {name: "PASS" if name not in ("release", "retreat") else "UNMEASURED"
                   for name in ("fov", "collision", "search", "synchronization",
                                "execution", "release", "retreat")},
    }


def _manifest():
    anchors = {
        name: {"cup_start_m": [0.1, 0.1, 0.2], "neck_start_rad": 0.0}
        for name in ("default", "left", "forward")
    }
    return build_task8_live_manifest(
        anchors, source_sha256="a" * 64, runtime_config_sha256="b" * 64,
        collection_config_sha256="c" * 64,
        contact_policy_fingerprint="d" * 64,
    )


def _inputs(tmp_path):
    scene = PACKAGE / "assets/mujoco/act/scene.xml"
    model = mujoco.MjModel.from_xml_path(str(scene))
    digest = model_sha256(model)
    pairs = SimpleNamespace(model_sha256=digest, for_phase=lambda _phase: frozenset())
    sources = SimpleNamespace(session_id="session-297", contact_pairs=pairs)
    broker = SimpleNamespace(simulation_session_id="session-297")
    connection = SimpleNamespace(broker=broker)
    binding = HeadSearchBinding({}, {}, {}, {})
    return {
        "node": object(), "model": model, "contact_pairs": pairs,
        "manifest": _manifest(), "report": _report(tmp_path), "sources": sources,
        "command_broker": broker, "connection": connection,
        "cancelled": object(), "binding": binding,
        "evidence_root": tmp_path, "campaign_id": "case-297",
        "worker_id": "w00", "generation": 1,
        "scene_node_factory": lambda: object(), "package_share": PACKAGE,
    }


def test_unmeasured_task6_refuses_port_before_creating_case_evidence(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["report"]["status"] = "CALIBRATION_REQUIRED"
    with pytest.raises(ValueError, match="CALIBRATION_REQUIRED"):
        build_task8_child_search_port(**inputs)
    assert not (tmp_path / "task8-live").exists()


def test_child_port_uses_installed_model_and_measured_neck_sweep(tmp_path):
    inputs = _inputs(tmp_path)
    seen = {}

    def sweep_factory(path, **kwargs):
        seen["sweep"] = (path, kwargs)
        return SimpleNamespace(check=lambda *_args, **_kwargs: True, step_s=0.002)

    def reset_factory(**kwargs):
        seen["reset"] = kwargs
        return SimpleNamespace(sources=inputs["sources"])

    def boundary_factory(reset, **kwargs):
        seen["boundary"] = (reset, kwargs)
        return SimpleNamespace(
            reset=reset, neck_sweep_checker=kwargs["neck_sweep_checker"],
            begin=lambda _request: None, search=lambda _request: None,
            safe_stop=lambda _reason, _request: True,
        )

    port = build_task8_child_search_port(
        **inputs, sweep_factory=sweep_factory,
        reset_factory=reset_factory, boundary_factory=boundary_factory,
    )
    assert isinstance(port, Task8SearchPhasePort)
    assert seen["sweep"][0] == PACKAGE / "assets/mujoco/act/scene.xml"
    assert seen["sweep"][1]["expected_model_sha256"] == inputs["contact_pairs"].model_sha256
    assert seen["sweep"][1]["path_step_s"] == 0.002
    assert seen["sweep"][1]["path_clearance_m"] == 0.002
    assert seen["sweep"][1]["allowed_pairs"] == ()
    assert seen["reset"]["connection"] is inputs["connection"]
    assert seen["reset"]["sources"] is inputs["sources"]
    assert seen["boundary"][0].sources is inputs["sources"]
    assert seen["boundary"][1]["snapshot_root"] == (
        tmp_path / "task8-live/case-297/snapshots"
    )
    assert seen["boundary"][1]["snapshot_root"].is_dir()


def test_case_path_traversal_refuses_before_writing_outside_evidence_root(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["campaign_id"] = "../outside"
    with pytest.raises(ValueError, match="TASK8_CHILD_PORT_SCOPE_INVALID"):
        build_task8_child_search_port(**inputs)
    assert not (tmp_path / "task8-live").exists()


def test_linked_task8_parent_cannot_redirect_snapshots_outside_evidence_root(tmp_path):
    inputs = _inputs(tmp_path)
    outside = tmp_path.parent / "outside-case-root"
    outside.mkdir()
    (tmp_path / "task8-live").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="TASK8_CHILD_PORT_SCOPE_INVALID"):
        build_task8_child_search_port(**inputs)
    assert not (outside / "case-297").exists()
