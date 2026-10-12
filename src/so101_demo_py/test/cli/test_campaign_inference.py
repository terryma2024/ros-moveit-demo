"""The private container entry rejects bad inputs before any model/socket starts."""

import importlib
import time

from so101_demo.runtime.parallel_ipc.frames import canonical_json
from test_config_identity import campaign_fixture


def argv(tmp_path, role="teacher"):
    config = tmp_path / "service.json"
    config.write_bytes(canonical_json(campaign_fixture(tmp_path)[role + "_service"]))
    return ["--config", str(config), "--socket", str(tmp_path / "inference.sock"),
        "--role", role, "--generation", "g1", "--gpu-uuid", "GPU-selected",
        "--startup-deadline-monotonic-ns", str(time.monotonic_ns() + 5_000_000_000),
        "--receive-budget-s", "0.5"]


def test_head_cannot_start_without_bound_or_approved_candidate_descriptor(tmp_path, capsys):
    module = importlib.import_module("so101_demo.cli.campaign_inference")
    assert module.main(argv(tmp_path, "head")) == 2
    assert "HEAD_DESCRIPTOR_REQUIRED" in capsys.readouterr().err
    assert not (tmp_path / "inference.sock").exists()


def test_invalid_closed_service_config_rejected_before_spawn(tmp_path, capsys):
    module = importlib.import_module("so101_demo.cli.campaign_inference")
    arguments = argv(tmp_path)
    config = tmp_path / "service.json"
    import json
    document = json.loads(config.read_bytes()) | {"grounded_model_id": "grounded-sam"}
    config.write_bytes(canonical_json(document))
    assert module.main(arguments) == 2
    assert "INFERENCE_SERVICE_INPUT_INVALID" in capsys.readouterr().err
    assert not (tmp_path / "inference.sock").exists()


def test_entry_without_ml_dependencies_reports_start_failure_without_fallback(tmp_path, capsys):
    import importlib.util
    import pytest
    if importlib.util.find_spec("torch") is not None:
        pytest.skip("requires non-ML interpreter")
    module = importlib.import_module("so101_demo.cli.campaign_inference")
    assert module.main(argv(tmp_path)) == 1
    assert "EXECUTOR_START_FAILED" in capsys.readouterr().err
    assert not (tmp_path / "inference.sock").exists()
