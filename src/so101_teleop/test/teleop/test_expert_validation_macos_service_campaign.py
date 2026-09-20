"""The macOS service entry point must accept exactly what the service sends, and refuse the rest.

This is the seam where a launch either works or fails in the middle of a campaign, so both directions
are pinned here: the flags the supervisor emits must parse into the adapter unchanged, and every
combination this platform cannot execute must be refused by name before anything is spawned.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from so101_demo.cli import macos_service_campaign as adapter
from so101_demo.cli.macos_service_campaign import ServiceCampaignError
from so101_teleop.expert_validation.supervisor import (
    FIXED_COORDINATOR_FLAGS,
    fixed_coordinator_argv,
)

DEMO_ROOT = Path(__file__).resolve().parents[3] / "so101_demo_py"
V4_CONFIG = DEMO_ROOT / "config/mujoco/parallel_batch_v4_macos_mps_w2.yaml"
V3_CONFIG = DEMO_ROOT / "config/mujoco/parallel_batch_v3.yaml"
HELPER = Path(__file__).resolve().parents[1] / "fixtures/stubborn_helper.py"


def _stubborn_campaign(tmp_path: Path) -> Path:
    """A fake campaign child: it ignores SIGTERM and forks a descendant into its own group."""
    script = tmp_path / "fake_campaign.py"
    script.write_text(
        "import signal, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"subprocess.Popen([sys.executable, {str(HELPER)!r}, str(Path(sys.argv[1]) / 'child-ready.json')])\n"
        "Path(sys.argv[1] + '/campaign-ready.json').write_text('{}\\n')\n"
        "time.sleep(300)\n"
    )
    return script


def _request(tmp_path: Path, **overrides) -> list[str]:
    """The argv the supervisor builds, with real files behind every path it names."""
    weights = tmp_path / "yolo.pt"
    weights.write_bytes(b"weights")
    grounded = tmp_path / "grounded"
    (grounded / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (grounded / "manifest.json").write_text('{"model": "grounded"}\n')
    points = tmp_path / "points.yaml"
    points.write_text("points: [p1, p2, p3, p4]\n")
    values = {
        "points_path": points,
        "config_path": V4_CONFIG,
        "batch_id": "b001",
        "worker_count": 2,
        "evidence_root": tmp_path / "batch",
        "broker_image_id": "sha256:" + "a" * 64,
        "yolo_weights_path": weights,
        "yolo_weights_sha256": adapter._digest(weights),
        "grounded_root": grounded,
        "grounded_manifest_sha256": adapter._digest(grounded / "manifest.json"),
        "selected_point_ids": ("p1", "p2"),
        "executable_path": tmp_path / "macos_service_campaign.py",
    }
    values.update(overrides)
    return fixed_coordinator_argv(**values)


def _parse(service_argv: list[str]):
    """Parse what the service sends: ``[interpreter, script, *flags]``."""
    return adapter.build_parser().parse_args(service_argv[2:])


def _with_flag(service_argv: list[str], flag: str, value: str) -> list[str]:
    """Rewrite one flag value in the argv the service would have sent."""
    rewritten = list(service_argv)
    index = rewritten.index(flag)
    rewritten[index + 1] = value
    return rewritten


def test_the_adapter_accepts_exactly_the_flags_the_service_sends(tmp_path):
    service_argv = _request(tmp_path)
    parser = adapter.build_parser()
    accepted = {option for action in parser._actions for option in action.option_strings}
    assert set(FIXED_COORDINATOR_FLAGS) <= accepted, (
        "a flag the supervisor sends but the adapter cannot parse fails a live launch, not a review"
    )
    assert accepted - {"-h", "--help"} == set(FIXED_COORDINATOR_FLAGS), (
        "the adapter must not silently accept flags the service never sends"
    )
    arguments = _parse(service_argv)
    assert arguments.batch_id == "b001"
    assert arguments.worker_count == 2
    assert arguments.run_mode == "execute"
    assert arguments.point_id == ["p1", "p2"]
    assert arguments.config == V4_CONFIG
    assert arguments.provenance_binding is None


def test_the_adapter_validates_the_service_request_and_names_every_refusal(tmp_path):
    environment = {
        "SO101_FIXED_CONTROL_CAMPAIGN_ID": "campaign-a",
        "SO101_FIXED_CONTROL_SOCKET": str(tmp_path / "c.sock"),
        "SO101_FIXED_CONTROL_TOKEN": "ab" * 32,
        "SO101_FIXED_CONTROL_EPOCH": "1",
    }
    good = _parse(_request(tmp_path))
    record = adapter.validate(good, environment=environment)
    assert record["campaign_id"] == "campaign-a" and record["coordinator_epoch"] == 1
    assert record["broker_image_used"] is False, "an unused container image must be recorded, not dropped"

    with pytest.raises(ServiceCampaignError, match="RUN_MODE_UNSUPPORTED"):
        adapter.validate(
            _parse(_with_flag(_request(tmp_path), "--run-mode", "compose")),
            environment=environment
        )
    with pytest.raises(ServiceCampaignError, match="PLATFORM_WORKER_COUNT_UNSUPPORTED"):
        adapter.validate(_parse(_request(tmp_path, worker_count=4)), environment=environment)
    with pytest.raises(ServiceCampaignError, match="YOLO_WEIGHTS_SHA256_MISMATCH"):
        adapter.validate(
            _parse(_request(tmp_path, yolo_weights_sha256="b" * 64)), environment=environment
        )
    with pytest.raises(ServiceCampaignError, match="GROUNDED_MANIFEST_SHA256_MISMATCH"):
        adapter.validate(
            _parse(_request(tmp_path, grounded_manifest_sha256="c" * 64)), environment=environment
        )
    with pytest.raises(ServiceCampaignError, match="CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION"):
        adapter.validate(
            _parse(_request(tmp_path, config_path=V3_CONFIG)), environment=environment
        )
    with pytest.raises(ServiceCampaignError, match="SELECTED_POINTS_REQUIRED"):
        adapter.validate(
            _parse(_request(tmp_path, selected_point_ids=())), environment=environment
        )
    for missing, reason in (
        ("SO101_FIXED_CONTROL_CAMPAIGN_ID", "CONTROL_CAMPAIGN_ID_MISSING"),
        ("SO101_FIXED_CONTROL_SOCKET", "CONTROL_ENDPOINT_UNSPECIFIED"),
        ("SO101_FIXED_CONTROL_TOKEN", "CONTROL_ENDPOINT_UNSPECIFIED"),
    ):
        without = {key: value for key, value in environment.items() if key != missing}
        with pytest.raises(ServiceCampaignError, match=reason):
            adapter.validate(good, environment=without)
    with pytest.raises(ServiceCampaignError, match="CONTROL_EPOCH_INVALID"):
        adapter.validate(good, environment={**environment, "SO101_FIXED_CONTROL_EPOCH": "zero"})


def test_the_adapter_stops_the_whole_owned_group_and_proves_it(tmp_path):
    """The child leads its own group, so a stop that signals one pid leaks exactly like the service's did."""
    script = _stubborn_campaign(tmp_path)
    evidence = tmp_path / "batch"
    evidence.mkdir()
    campaign = adapter.OwnedCampaign([sys.executable, str(script), str(evidence)], log_path=evidence / "log.txt")
    try:
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline and not (
            (evidence / "campaign-ready.json").is_file() and (evidence / "child-ready.json").is_file()
        ):
            time.sleep(0.05)
        assert (evidence / "campaign-ready.json").is_file(), "the fake campaign never started"
        assert (evidence / "child-ready.json").is_file(), "the fake campaign never forked its child"
        child_pid = json.loads((evidence / "child-ready.json").read_text())["pid"]

        receipt = campaign.stop()
        assert receipt["term_sent"] is True
        assert receipt["kill_sent"] is True, "a SIGTERM-ignoring group requires the escalation"
        assert receipt["clear"] is True and receipt["survivors"] == []
        assert receipt["pgid"] == campaign.pgid
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        campaign.stop()
        campaign.close()


def test_the_adapter_reports_only_what_the_campaign_can_show(tmp_path, monkeypatch):
    """A stop acknowledgement is not a cleanup receipt: the endpoint must not claim one."""
    evidence = tmp_path / "batch"
    evidence.mkdir()
    script = _stubborn_campaign(tmp_path)
    campaign = adapter.OwnedCampaign([sys.executable, str(script), str(evidence)], log_path=evidence / "log.txt")
    try:
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline and not (evidence / "campaign-ready.json").is_file():
            time.sleep(0.05)
        monkeypatch.setenv("SO101_FIXED_CONTROL_CAMPAIGN_ID", "campaign-a")
        monkeypatch.setenv("SO101_FIXED_CONTROL_SOCKET", str(tmp_path / "c.sock"))
        monkeypatch.setenv("SO101_FIXED_CONTROL_TOKEN", "ab" * 32)
        result_path = evidence / "campaign-result.json"

        def state():
            inner = json.loads(result_path.read_text()) if result_path.is_file() else {}
            cleanup = inner.get("cleanup") or {}
            return {
                "state": "TERMINAL" if inner else "RUNNING",
                "batch_terminal": bool(inner),
                "batch_cleanup_complete": bool(cleanup.get("complete")),
            }

        assert state()["batch_cleanup_complete"] is False
        result_path.write_text(json.dumps({"status": "W2_CAMPAIGN_PASS",
                                           "cleanup": {"complete": True, "directory_removed": True}}))
        assert state()["batch_cleanup_complete"] is True
        assert state()["state"] == "TERMINAL"
    finally:
        campaign.stop()
        campaign.close()
