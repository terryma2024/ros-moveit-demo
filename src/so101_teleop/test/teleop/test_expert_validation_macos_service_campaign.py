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
    RETRY_COORDINATOR_FLAGS,
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
    assert accepted - {"-h", "--help"} == set(FIXED_COORDINATOR_FLAGS) | set(
        RETRY_COORDINATOR_FLAGS
    ), (
        "the adapter must not silently accept flags the service never sends; the retry "
        "binding flags are the v5 route's own contract and are forwarded only when set"
    )
    arguments = _parse(service_argv)
    assert arguments.batch_id == "b001"
    assert arguments.worker_count == 2
    assert arguments.run_mode == "execute"
    assert arguments.point_id == ["p1", "p2"]
    assert arguments.config == V4_CONFIG
    assert arguments.provenance_binding is None
    # A first-pass request never carries a retry binding.
    for flag in RETRY_COORDINATOR_FLAGS:
        assert getattr(arguments, flag.lstrip("-").replace("-", "_")) is None


def test_the_adapter_validates_the_service_request_and_names_every_refusal(tmp_path):
    def validate(arguments, *, environment):
        return adapter.validate(arguments, environment=environment, platform="darwin")

    environment = {
        "SO101_FIXED_CONTROL_CAMPAIGN_ID": "campaign-a",
        "SO101_FIXED_CONTROL_SOCKET": str(tmp_path / "c.sock"),
        "SO101_FIXED_CONTROL_TOKEN": "ab" * 32,
        "SO101_FIXED_CONTROL_EPOCH": "1",
    }
    good = _parse(_request(tmp_path))
    record = validate(good, environment=environment)
    assert record["campaign_id"] == "campaign-a" and record["coordinator_epoch"] == 1
    assert record["broker_image_used"] is False, "an unused container image must be recorded, not dropped"

    with pytest.raises(ServiceCampaignError, match="RUN_MODE_UNSUPPORTED"):
        validate(
            _parse(_with_flag(_request(tmp_path), "--run-mode", "compose")),
            environment=environment
        )
    with pytest.raises(ServiceCampaignError, match="PLATFORM_WORKER_COUNT_UNSUPPORTED"):
        validate(_parse(_request(tmp_path, worker_count=4)), environment=environment)
    with pytest.raises(ServiceCampaignError, match="YOLO_WEIGHTS_SHA256_MISMATCH"):
        validate(
            _parse(_request(tmp_path, yolo_weights_sha256="b" * 64)), environment=environment
        )
    with pytest.raises(ServiceCampaignError, match="GROUNDED_MANIFEST_SHA256_MISMATCH"):
        validate(
            _parse(_request(tmp_path, grounded_manifest_sha256="c" * 64)), environment=environment
        )
    with pytest.raises(ServiceCampaignError, match="CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION"):
        validate(
            _parse(_request(tmp_path, config_path=V3_CONFIG)), environment=environment
        )
    with pytest.raises(ServiceCampaignError, match="SELECTED_POINTS_REQUIRED"):
        validate(
            _parse(_request(tmp_path, selected_point_ids=())), environment=environment
        )
    for missing, reason in (
        ("SO101_FIXED_CONTROL_CAMPAIGN_ID", "CONTROL_CAMPAIGN_ID_MISSING"),
        ("SO101_FIXED_CONTROL_SOCKET", "CONTROL_ENDPOINT_UNSPECIFIED"),
        ("SO101_FIXED_CONTROL_TOKEN", "CONTROL_ENDPOINT_UNSPECIFIED"),
    ):
        without = {key: value for key, value in environment.items() if key != missing}
        with pytest.raises(ServiceCampaignError, match=reason):
            validate(good, environment=without)
    with pytest.raises(ServiceCampaignError, match="CONTROL_EPOCH_INVALID"):
        validate(good, environment={**environment, "SO101_FIXED_CONTROL_EPOCH": "zero"})


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


def test_the_adapter_runs_as_the_script_the_service_launches(tmp_path):
    """The service launches a *script path*, not a module.

    A relative import in the adapter works under pytest - which imports it as a module - and fails at
    the first live launch with "attempted relative import with no known parent package". The only test
    that can see that is one that runs the file the way the supervisor does.
    """
    adapter_path = DEMO_ROOT / "src/cli/macos_service_campaign.py"
    environment = dict(os.environ)
    # The child gets its import root from this test's own source paths and whatever PYTHONPATH the
    # caller already exported. A task-specific SO101_TASK_ROOT must not be required: the service
    # launches the installed script, where the shim is an installation detail, not an input.
    environment["PYTHONPATH"] = os.pathsep.join(
        part
        for part in (
            str(DEMO_ROOT / "src"),
            str(DEMO_ROOT / "src/cli"),
            environment.get("PYTHONPATH", ""),
        )
        if part
    )
    service_argv = _request(tmp_path, config_path=tmp_path / "missing.yaml")
    completed = subprocess.run(
        [sys.executable, str(adapter_path), *service_argv[2:]],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(tmp_path),
    )
    assert completed.returncode == 1, completed.stderr
    assert "ModuleNotFoundError" not in completed.stderr, completed.stderr
    document = json.loads(completed.stdout)
    assert document["status"] == "REFUSED" and document["refusal"] == "CONFIG_MISSING"


def test_the_control_socket_can_be_addressed_on_this_platform():
    """A service-driven campaign died binding a 200-byte control path Darwin cannot address.

    Linux keeps the endpoint inside the batch root because its client pins the parent through
    ``/proc/self/fd``. Darwin has neither that indirection nor room for such a path, so the endpoint
    has to live somewhere short - and the client's own mode checks still require a private directory.
    """
    import sys

    from so101_teleop.expert_validation.coordinator import CONTROL_SOCKET_ROOT
    from so101_teleop.expert_validation.supervisor import control_socket_path

    batch_root = Path("/private/tmp/so101-debug-task/stageC-accept/campaigns/campaign-x/bc7b5")
    campaign_id = "campaign-9937d7c939b446108e92fb8733c36323"
    standard = batch_root / "control" / "control.sock"
    chosen = control_socket_path(batch_root, campaign_id)
    if sys.platform == "darwin":
        assert chosen != standard
        assert len(os.fsencode(chosen)) < 104, f"{chosen} cannot be bound on Darwin"
        assert chosen.parent == CONTROL_SOCKET_ROOT
        assert campaign_id in chosen.name and batch_root.name in chosen.name, (
            "two batches must not share one endpoint"
        )
    else:
        assert chosen == standard, "the Linux path stays inside the batch root"


def test_the_contract_accepts_the_platform_endpoint_and_still_refuses_the_rest(tmp_path):
    """Both contracts validate the socket's privacy, so the composer and the validator must agree."""
    from so101_teleop.expert_validation.coordinator import CONTROL_SOCKET_ROOT

    accepted = _parse(_request(tmp_path))
    batch_root = tmp_path / "batch"
    batch_root.mkdir(parents=True, exist_ok=True)
    from so101_teleop.expert_validation.supervisor import control_socket_path

    chosen = control_socket_path(batch_root, "campaign-a")
    from so101_teleop.expert_validation.coordinator import CoordinatorStartRequest

    request = CoordinatorStartRequest(
        campaign_id="campaign-a",
        batch_id="b001",
        execution_mode="PARALLEL",
        worker_count=2,
        max_points_per_worker=None,
        argv=accepted.argv if hasattr(accepted, "argv") else (sys.executable, str(HELPER)),
        environment={},
        batch_root=batch_root,
        control_socket=chosen,
        control_token_sha256="a" * 64,
        coordinator_epoch=1,
    )
    assert request.control_socket == Path(chosen).resolve(strict=False)
    if sys.platform == "darwin":
        assert chosen.parent == CONTROL_SOCKET_ROOT
    with pytest.raises(ValueError, match="CONTROL_SOCKET_OUTSIDE_BATCH_ROOT"):
        CoordinatorStartRequest(
            campaign_id="campaign-a",
            batch_id="b001",
            execution_mode="PARALLEL",
            worker_count=2,
            max_points_per_worker=None,
            argv=(sys.executable, str(HELPER)),
            environment={},
            batch_root=batch_root,
            control_socket=(tmp_path / "elsewhere" / "control.sock").resolve(),
            control_token_sha256="a" * 64,
            coordinator_epoch=1,
        )
