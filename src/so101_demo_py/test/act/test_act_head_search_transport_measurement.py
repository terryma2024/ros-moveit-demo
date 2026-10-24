"""The running-topic measurement: the frame contract declaration and the skew measurement.

Both documents this module produces are the two the phase 6/7 inventory still lacks a producer for. The
decision layer is pure - a caller's plugin configuration, a capture port's records and a clock reading
list are all the tests need - so no ROS node, no MuJoCo, no detector and no GPU take part here.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest
import yaml
from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search.timing_params import (
    compute_max_skew_s,
)
from so101_demo.act.head_search.transport_measurement import (
    CAL_FRAME_CONTRACT_CONTRADICTORY,
    CAL_SKEW_CLOCK_UNMEASURED,
    CAL_SKEW_EVIDENCE_CONTRADICTORY,
    CAL_SKEW_SOURCE_MISSING,
    CLOCK_RESOLUTION_BASIS,
    FRAME_CONTRACT_ARTIFACT,
    SKEW_ARTIFACT,
    build_skew_document,
    frame_contract_declaration,
    measure_clock_resolution,
    read_production_head_camera,
    skew_sample,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

PLUGIN_CONFIG = {
    "/**": {
        "ros__parameters": {
            "mujoco_plugins": {
                "mujoco_camera_plugin": {
                    "type": "mujoco_ros2_control_plugins/CameraPlugin",
                    "camera_publish_rate": 10.0,
                    "head_camera": {
                        "policy": "streaming",
                        "frame_name": "head_camera_frame",
                        "image_topic": "/head_camera/color",
                        "info_topic": "/head_camera/camera_info",
                        "publish_depth": False,
                    },
                    "task_camera": {
                        "policy": "streaming",
                        "frame_name": "task_camera_frame",
                        "image_topic": "/task_camera/color",
                        "info_topic": "/task_camera/camera_info",
                    },
                }
            }
        }
    }
}


def plugin_config(tmp_path: Path, **changes) -> Path:
    document = json.loads(json.dumps(PLUGIN_CONFIG))
    camera = document["/**"]["ros__parameters"]["mujoco_plugins"]["mujoco_camera_plugin"]
    camera.update(changes.pop("camera", {}))
    camera["head_camera"].update(changes.pop("head_camera", {}))
    path = tmp_path / "mujoco_plugins.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=True), encoding="utf-8")
    return path


def capture_document(tmp_path: Path, *, samples=None, clock_resolution_s=0.002) -> dict:
    document_path = tmp_path / "skew-measurements.json"
    records = (
        samples
        if samples is not None
        else [
            skew_sample(
                index=index,
                image={"stamp_s": 1.0 + 0.1 * index, "received_monotonic_s": 10.0 + 0.1 * index},
                camera_info={
                    "stamp_s": 1.0 + 0.1 * index,
                    "received_monotonic_s": 10.0 + 0.1 * index,
                },
                joint_state={
                    "stamp_s": 1.0 + 0.1 * index - 0.002,
                    "received_monotonic_s": 10.0 + 0.1 * index - 0.001,
                },
                tf={"resolved": True, "stamp_s": 1.0 + 0.1 * index},
            )
            for index in range(3)
        ]
    )
    return build_skew_document(
        document_path=document_path,
        samples=records,
        clock_resolution_s=clock_resolution_s,
        clock_resolution_basis=dict(CLOCK_RESOLUTION_BASIS),
        capture={"frame_count": len(records), "achieved_rate_hz": 10.0},
    )


# --- the frame contract declaration ---------------------------------------------------------------


def test_the_declaration_is_read_from_the_production_camera_plugin(tmp_path: Path) -> None:
    config = plugin_config(tmp_path)
    camera = read_production_head_camera(config)

    assert camera["camera_publish_rate"] == 10.0
    assert camera["head_camera"]["image_topic"] == "/head_camera/color"
    assert camera["head_camera"]["info_topic"] == "/head_camera/camera_info"
    assert camera["head_camera"]["frame_name"] == "head_camera_frame"
    assert camera["sha256"] == hashlib.sha256(config.read_bytes()).hexdigest()


def test_the_declaration_records_its_declaring_source_and_stays_measured_here_false(
    tmp_path: Path,
) -> None:
    config = plugin_config(tmp_path)
    document = frame_contract_declaration(
        plugin_config_path=config,
        document_path=tmp_path / FRAME_CONTRACT_ARTIFACT,
        command="ros2 run so101_demo_py so101_head_search_calibration measure-frame-contract",
    )

    assert document["frame_rate_hz"] == 10.0
    assert document["frame_period_s"] == 0.1
    assert document["item"] == "frame_contract_10_hz"
    assert document["measured_here"] is False
    assert document["value_source"] == "declaration"
    declared = document["declared_by"]
    assert declared["source"] == str(config)
    assert declared["sha256"] == hashlib.sha256(config.read_bytes()).hexdigest()
    assert declared["declared_value"] == 10.0
    assert declared["json_pointer"].endswith("/camera_publish_rate")
    assert declared["head_camera"]["image_topic"] == "/head_camera/color"


def test_the_declaration_carries_the_path_and_digest_phase_seven_cites(tmp_path: Path) -> None:
    config = plugin_config(tmp_path)
    path = tmp_path / FRAME_CONTRACT_ARTIFACT
    document = frame_contract_declaration(plugin_config_path=config, document_path=path)

    assert document["path"] == str(path)
    body = {key: value for key, value in document.items() if key != "sha256"}
    assert document["sha256"] == canonical_sha256(body)


def test_the_declaration_refuses_a_production_rate_that_is_not_ten_hz(tmp_path: Path) -> None:
    config = plugin_config(tmp_path, camera={"camera_publish_rate": 5.0})
    with pytest.raises(CalibrationInputsRefused) as refused:
        frame_contract_declaration(
            plugin_config_path=config, document_path=tmp_path / FRAME_CONTRACT_ARTIFACT
        )
    assert CAL_FRAME_CONTRACT_CONTRADICTORY in str(refused.value)


def test_the_declaration_refuses_a_head_camera_that_is_not_the_production_stream(
    tmp_path: Path,
) -> None:
    config = plugin_config(tmp_path, head_camera={"image_topic": "/head_camera/image_raw"})
    with pytest.raises(CalibrationInputsRefused) as refused:
        frame_contract_declaration(
            plugin_config_path=config, document_path=tmp_path / FRAME_CONTRACT_ARTIFACT
        )
    assert CAL_FRAME_CONTRACT_CONTRADICTORY in str(refused.value)


def test_the_declaration_records_a_measured_rate_beside_it_and_says_which_is_the_value(
    tmp_path: Path,
) -> None:
    config = plugin_config(tmp_path)
    document = frame_contract_declaration(
        plugin_config_path=config,
        document_path=tmp_path / FRAME_CONTRACT_ARTIFACT,
        measured_rate_hz=9.94,
        measured_rate_detail={"frame_count": 300, "window_sim_s": 30.18},
    )

    assert document["frame_rate_hz"] == 10.0
    assert document["value_source"] == "declaration"
    assert document["measured_frame_rate_hz"] == 9.94
    assert document["measured_frame_rate_detail"]["frame_count"] == 300


# --- the skew document ----------------------------------------------------------------------------


def test_a_skew_sample_carries_the_three_required_source_stamps() -> None:
    sample = skew_sample(
        index=7,
        image={"stamp_s": 3.0, "received_monotonic_s": 40.0},
        camera_info={"stamp_s": 3.0, "received_monotonic_s": 40.001},
        joint_state={"stamp_s": 2.998, "received_monotonic_s": 40.002},
        tf={"resolved": True, "stamp_s": 3.0},
    )

    assert sample["index"] == 7
    assert sample["stamps"] == [3.0, 3.0, 2.998]
    assert sample["skew_s"] == pytest.approx(0.002)
    assert sample["sources"]["joint_state"]["stamp_s"] == 2.998
    assert sample["sources"]["tf"]["resolved"] is True


def test_the_document_carries_the_samples_the_contract_and_the_measured_clock(
    tmp_path: Path,
) -> None:
    document = capture_document(tmp_path)

    assert document["kind"] == "head_search_calibration_skew_measurements"
    assert document["phase"] == "skew_measurements"
    assert len(document["samples"]) == 3
    assert document["clock_resolution_s"] == 0.002
    assert document["measured_here"] is True
    assert document["detector_loaded"] is False
    assert document["motion_commanded"] is False
    body = {key: value for key, value in document.items() if key != "sha256"}
    assert document["sha256"] == canonical_sha256(body)


def test_the_document_refuses_a_sample_that_is_missing_a_required_source(tmp_path: Path) -> None:
    incomplete = {
        "index": 0,
        "stamps": [1.0, 1.0],
        "skew_s": 0.0,
        "sources": {
            "head_image": {"stamp_s": 1.0},
            "camera_info": {"stamp_s": 1.0},
        },
    }
    with pytest.raises(CalibrationInputsRefused) as refused:
        build_skew_document(
            document_path=tmp_path / SKEW_ARTIFACT,
            samples=[incomplete],
            clock_resolution_s=0.002,
            clock_resolution_basis=dict(CLOCK_RESOLUTION_BASIS),
        )
    assert CAL_SKEW_SOURCE_MISSING in str(refused.value)


def test_the_document_refuses_stamps_that_do_not_match_the_recorded_sources(tmp_path: Path) -> None:
    sample = skew_sample(
        index=0,
        image={"stamp_s": 1.0, "received_monotonic_s": 5.0},
        camera_info={"stamp_s": 1.0, "received_monotonic_s": 5.0},
        joint_state={"stamp_s": 0.998, "received_monotonic_s": 5.0},
    )
    sample["stamps"] = [1.0, 1.0, 0.5]
    with pytest.raises(CalibrationInputsRefused) as refused:
        build_skew_document(
            document_path=tmp_path / SKEW_ARTIFACT,
            samples=[sample],
            clock_resolution_s=0.002,
            clock_resolution_basis=dict(CLOCK_RESOLUTION_BASIS),
        )
    assert CAL_SKEW_EVIDENCE_CONTRADICTORY in str(refused.value)


def test_the_document_refuses_a_clock_resolution_that_was_not_measured(tmp_path: Path) -> None:
    with pytest.raises(CalibrationInputsRefused) as refused:
        build_skew_document(
            document_path=tmp_path / SKEW_ARTIFACT,
            samples=[
                skew_sample(
                    index=0,
                    image={"stamp_s": 1.0, "received_monotonic_s": 5.0},
                    camera_info={"stamp_s": 1.0, "received_monotonic_s": 5.0},
                    joint_state={"stamp_s": 0.998, "received_monotonic_s": 5.0},
                )
            ],
            clock_resolution_s=None,
            clock_resolution_basis=dict(CLOCK_RESOLUTION_BASIS),
        )
    assert CAL_SKEW_CLOCK_UNMEASURED in str(refused.value)


def test_the_document_refuses_a_capture_with_no_samples(tmp_path: Path) -> None:
    with pytest.raises(CalibrationInputsRefused):
        build_skew_document(
            document_path=tmp_path / SKEW_ARTIFACT,
            samples=[],
            clock_resolution_s=0.002,
            clock_resolution_basis=dict(CLOCK_RESOLUTION_BASIS),
        )


def test_the_clock_resolution_is_the_smallest_positive_step_of_the_running_clock() -> None:
    resolution = measure_clock_resolution([0.0, 0.002, 0.004, 0.004, 0.01, 0.012])

    assert resolution == pytest.approx(0.002)


def test_the_clock_resolution_refuses_a_clock_that_never_moved() -> None:
    with pytest.raises(CalibrationInputsRefused) as refused:
        measure_clock_resolution([0.5, 0.5, 0.5])
    assert CAL_SKEW_CLOCK_UNMEASURED in str(refused.value)


# --- what the installed phase 7 does with the document ---------------------------------------------


def test_phase_seven_computes_max_skew_from_the_measured_document(tmp_path: Path) -> None:
    config = plugin_config(tmp_path)
    contract = frame_contract_declaration(
        plugin_config_path=config, document_path=tmp_path / FRAME_CONTRACT_ARTIFACT
    )
    document = capture_document(tmp_path)
    document["path"] = str(tmp_path / SKEW_ARTIFACT)

    block = compute_max_skew_s(skew=document, frame_contract=contract)

    assert block["value"] == pytest.approx(0.002 + 0.002)
    assert block["observed_distribution"]["sample_count"] == 3
    assert block["observed_distribution"]["clock_resolution_s"] == 0.002
    assert block["safety_margin"]["cap_s"] == pytest.approx(0.05)
    cited = {reference["path"] for reference in block["input_evidence"]}
    assert str(tmp_path / SKEW_ARTIFACT) in cited
    assert str(tmp_path / FRAME_CONTRACT_ARTIFACT) in cited


def test_phase_seven_still_refuses_a_measured_skew_beyond_half_a_frame(tmp_path: Path) -> None:
    config = plugin_config(tmp_path)
    contract = frame_contract_declaration(
        plugin_config_path=config, document_path=tmp_path / FRAME_CONTRACT_ARTIFACT
    )
    samples = [
        skew_sample(
            index=index,
            image={"stamp_s": 1.0 + index, "received_monotonic_s": float(index)},
            camera_info={"stamp_s": 1.0 + index, "received_monotonic_s": float(index)},
            joint_state={"stamp_s": 1.0 + index - 0.06, "received_monotonic_s": float(index)},
        )
        for index in range(3)
    ]
    document = capture_document(tmp_path, samples=samples)
    document["path"] = str(tmp_path / SKEW_ARTIFACT)

    with pytest.raises(CalibrationInputsRefused) as refused:
        compute_max_skew_s(skew=document, frame_contract=contract)
    assert "CAL_SKEW_EXCEEDED" in str(refused.value)


def test_the_measured_skew_is_the_spread_of_the_three_required_sources() -> None:
    sample = skew_sample(
        index=0,
        image={"stamp_s": 12.5, "received_monotonic_s": 90.0},
        camera_info={"stamp_s": 12.5, "received_monotonic_s": 90.0},
        joint_state={"stamp_s": 12.494, "received_monotonic_s": 90.0},
    )

    assert sample["stamps"] == [12.5, 12.5, 12.494]
    assert math.isclose(sample["skew_s"], 0.006, rel_tol=0.0, abs_tol=1e-12)
