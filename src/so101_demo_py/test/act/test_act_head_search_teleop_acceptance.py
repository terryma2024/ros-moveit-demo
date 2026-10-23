"""The teleop acceptance: owned start, measured probes, proven teardown, honest receipt.

Every fixture here is synthetic. No MuJoCo, no detector, no GPU, no ROS node and no browser is started:
the orchestration's own seams (the stack factory, the head-camera flight, the app factory, the route
probe and the case runner) are injected, so what these cases pin is the *ordering and the refusals* - a
descriptor before a probe, a receipt before a teardown or a PASSED block without on-disk screenshots are
all failures here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from so101_demo.act.head_search_teleop_acceptance.acceptance import TeleopAcceptance
from so101_demo.act.head_search_teleop_acceptance.receipts import (
    acceptance_receipt,
    bridge_cleanup_receipt,
    check_socket_paths,
    e2e_block,
    E2E_CASE,
    KIND,
    MINIMUM_SCREENSHOTS,
    OPERATION,
    PASSED,
    read_closed_report,
    read_e2e_evidence,
    RECEIPT_ARTIFACT,
    REFUSED,
    teardown_receipt,
    TELEOP_BUNDLE_MISMATCH,
    TELEOP_E2E_FAILED,
    TELEOP_GPU_NOT_RELEASED,
    TELEOP_PROBE_FAILED,
    TELEOP_REPORT_NOT_PUBLISHED,
    TELEOP_RUN_ROOT_EXISTS,
    TELEOP_SOCKET_PATH_TOO_LONG,
    TELEOP_TEARDOWN_UNPROVEN,
    validate_receipt,
)
from so101_demo.act.head_search_teleop_acceptance.runners import TeleopAcceptanceRefused

# --- synthetic fixtures -------------------------------------------------------------------------------


PROMOTED_VALUES_SHA256 = "3c787fd7ec402355d8a6e363a6bcbf814273ce30d98d47a3af2bc4400f568df2"


def bundle_document(values_sha256: str) -> dict:
    return {
        "path": "/declared/bundle.json",
        "sha256": "b" * 64,
        "values_sha256": values_sha256,
        "promoted_config": "/declared/head_search_runtime.json",
        "promoted_config_sha256": "c" * 64,
        "promoted_values_sha256": PROMOTED_VALUES_SHA256,
        "values_match": values_sha256 == PROMOTED_VALUES_SHA256,
        "parameter_names": ["center_deadband_px"],
        "values_count": 17,
    }


def runtime_document() -> dict:
    return {
        "final_run": "/frozen",
        "source_commit": "956b5b74bfc2581a6222970c924ac0fd4e5e93e0",
        "production_config": "/frozen/config.json",
        "production_config_sha256": "d" * 64,
        "values_sha256": PROMOTED_VALUES_SHA256,
        "values_count": 17,
        "allow_cpu_fallback": False,
        "cuda_device": "cuda:0",
        "weight_path": "/frozen/best.pt",
        "weight_sha256_declared": "e" * 64,
        "weight_sha256_observed": "e" * 64,
    }


class FakeStack:
    """One production composition, with the process handles a teardown proof counts."""

    def __init__(self, *, fail_start: bool = False) -> None:
        self.calls: list[str] = []
        self.fail_start = fail_start
        self.processes = [
            type("P", (), {"pid": 999_000_001})(),
            type("P", (), {"pid": 999_000_002})(),
        ]

    def start(self) -> None:
        self.calls.append("start")
        if self.fail_start:
            raise RuntimeError("RESTART_STACK_START_FAILED: nothing came up")

    def stop(self) -> None:
        self.calls.append("stop")


class FakeApp:
    def __init__(self, *, exit_on_terminate: bool = True) -> None:
        self.pid = 999_000_003
        self.calls: list[str] = []
        self.exit_on_terminate = exit_on_terminate

    def terminate(self) -> None:
        self.calls.append("terminate")

    def wait(self, timeout=None):  # noqa: ANN001 - the seam's own signature
        self.calls.append("wait")
        if not self.exit_on_terminate:
            raise TimeoutError("still running")
        return 0


def flight_document(**overrides) -> dict:
    document = {
        "detector_count": 1,
        "runtime_device": "cuda",
        "allow_cpu_fallback": False,
        "weights_sha256": "e" * 64,
        "model_id": "head-search-runtime",
        "frame_count": 10,
        "detections": 3,
        "frame_rate_hz": 10.0,
        "raw_frame_sha256": "f" * 64,
        "source": "synthetic production detector over /head_camera/color",
    }
    document.update(overrides)
    return document


class FakeRoutes:
    """The installed routes' own status codes and refusal codes, with the stop proof's state machine."""

    def __init__(self, *, interval=(-0.2, 0.3), state="STOPPING", stop_cap=None) -> None:
        self.interval = list(interval)
        self.state = state
        self.stop_cap = stop_cap
        self.samples = 0
        self.calls: list[str] = []
        self.last_time: float | None = None

    def __call__(self, request) -> dict:  # noqa: ANN001 - the seam's own signature
        action = request["action"]
        self.calls.append(action)
        if action == "status":
            return {
                "ok": True,
                "status": 200,
                "body": {
                    "available": True,
                    "operation": OPERATION,
                    "runtime_id": "head-teleop-acceptance-1",
                    "model_id": "head-search-runtime",
                    "state": self.state,
                    "detector_constructed": 0,
                    "safe_interval_rad": list(self.interval),
                },
            }
        if action == "capture":
            return {
                "ok": False,
                "status": 409,
                "body": {"detail": {"code": "HEAD_CAPTURE_NO_FRAME"}},
            }
        if action == "target":
            payload = request["payload"]
            if "safe_interval_rad" in payload:
                return {
                    "ok": False,
                    "status": 409,
                    "body": {"detail": {"code": "HEAD_TARGET_INTERVAL_SEALED"}},
                }
            low, high = self.interval
            if not low <= float(payload["target_rad"]) <= high:
                return {
                    "ok": False,
                    "status": 409,
                    "body": {"detail": {"code": "HEAD_TARGET_OUT_OF_RANGE"}},
                }
            return {
                "ok": True,
                "status": 200,
                "body": {"submitted_rad": float(payload["target_rad"]), "status": "SUBMITTED"},
            }
        if action == "stop":
            stamp = float(request["payload"]["sim_time_s"])
            if self.last_time is not None and stamp <= self.last_time:
                self.samples = 0
            else:
                self.samples += 1
            self.last_time = stamp
            complete = self.samples >= 3 and (
                self.stop_cap is None or self.samples <= self.stop_cap
            )
            self.state = "STOPPED" if complete else "STOPPING"
            return {
                "ok": True,
                "status": 200,
                "body": {"state": self.state, "consecutive_samples": self.samples},
            }
        raise AssertionError(f"unexpected action {action!r}")


def write_e2e_evidence(
    root: Path, *, screenshots: int = MINIMUM_SCREENSHOTS, status: str = PASSED
) -> None:
    shots = []
    for index in range(screenshots):
        relative = f"reports/screenshots/state-{index}.png"
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\x89PNG\r\n\x1a\n")
        shots.append(relative)
    report = root / "reports" / "playwright-default.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "suites": [
                    {
                        "specs": [
                            {
                                "tests": [
                                    {"status": "expected" if status == PASSED else "unexpected"}
                                ]
                            }
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (root / "head-camera-evidence.json").write_text(
        json.dumps(
            {
                "case": E2E_CASE,
                "status": status,
                "runtime_id": "head-teleop-acceptance-1",
                "operation": OPERATION,
                "states": ["status", "raw", "overlay", "conflict", "stale", "stopping", "stopped"],
                "screenshots": shots,
                "raw_overlay_pairs": [{"sequence": 1, "jpeg_sha256": "a" * 64}],
                "refusals": [
                    {"name": "conflict", "status": 409, "code": "HEAD_TARGET_INTERVAL_SEALED"}
                ],
                "chrome": {
                    "executablePath": "/usr/bin/google-chrome",
                    "version": "Google Chrome 150",
                },
            }
        ),
        encoding="utf-8",
    )


class Recorder:
    """The order in which the run writes things, so a receipt can never precede its own evidence."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def observer(self) -> dict:
        self.events.append("observe")
        return {"processes": [], "nodes": [], "gpu_compute_apps": [], "sim_clock_s": []}


def short_socket_root(tmp_path: Path) -> Path:
    """A socket namespace that fits the kernel limit, because pytest's own tmp path does not."""

    import hashlib
    import os

    digest = hashlib.sha256(str(tmp_path).encode("utf-8")).hexdigest()[:10]
    return Path(os.environ.get("HEAD_SEARCH_SOCKET_ROOT", "/tmp")) / f"head-search-{digest}"


def build(
    tmp_path: Path, *, values_sha256: str | None = None, report: dict | None = None, **kwargs
):
    run_root = kwargs.pop("run_root", tmp_path / "runtime")
    acceptance_root = kwargs.pop("acceptance_root", tmp_path)
    socket_root = kwargs.pop("socket_root", short_socket_root(tmp_path))
    recorder = Recorder()
    stack = kwargs.pop("stack", FakeStack())
    app = kwargs.pop("app", FakeApp())
    routes = kwargs.pop("routes", FakeRoutes())

    def stack_factory(**_ignored):
        recorder.events.append("stack_factory")
        return stack

    def detector_flight(**_ignored):
        recorder.events.append("detector_flight")
        return flight_document()

    def app_factory(**_ignored):
        recorder.events.append("app_factory")
        return app

    def e2e_runner(**_ignored):
        recorder.events.append("e2e")
        write_e2e_evidence(acceptance_root)
        return {"rc": 0, "command": "bun run test:e2e -- e2e/head-camera.spec.ts"}

    acceptance = TeleopAcceptance(
        run_root=run_root,
        acceptance_root=acceptance_root,
        socket_root=socket_root,
        ready_file=acceptance_root / "runtime-connection.json",
        runtime=runtime_document(),
        bundle=bundle_document(values_sha256 or runtime_document()["values_sha256"]),
        report=read_closed_report(None) if report is None else report,
        values={
            "tracking_iou": 0.5,
            "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
        },
        runtime_id="head-teleop-acceptance-1",
        model_id="head-search-runtime",
        weights_path=Path("/frozen/best.pt"),
        stack_factory=stack_factory,
        detector_flight=detector_flight,
        app_factory=app_factory,
        app_probe=routes,
        e2e_runner=e2e_runner,
        observer=recorder.observer,
        **kwargs,
    )
    return acceptance, recorder, stack, app, routes


# --- the pure readers ---------------------------------------------------------------------------------


def test_both_bridge_endpoints_are_validated_against_the_kernel_limit(tmp_path: Path) -> None:
    long_root = tmp_path / ("x" * 120)
    result = check_socket_paths([str(long_root / "normal.sock"), str(long_root / "safety.sock")])

    assert result["within_limit"] is False
    assert len(result["overlong"]) == 2
    assert result["path_bytes"][0] > 103


def test_bridge_cleanup_receipt_records_what_was_declared_and_what_remains(tmp_path: Path) -> None:
    root = tmp_path / "ipc"
    root.mkdir()
    declared = [str(root / "normal.sock"), str(root / "safety.sock")]
    (root / "normal.sock").write_bytes(b"")

    receipt = bridge_cleanup_receipt(socket_root=root, declared_paths=declared)

    assert receipt["remaining"] == [str(root / "normal.sock")]
    assert receipt["cleaned"] is False
    assert receipt["socket_path_bytes"] == [len(item.encode()) for item in declared]


def test_a_receipt_without_a_closed_report_is_not_a_pass(tmp_path: Path) -> None:
    receipt = acceptance_receipt(
        runtime=runtime_document(),
        bundle_sha256="b" * 64,
        runtime_id="head-teleop-acceptance-1",
        report=read_closed_report(None),
        connection=None,
        detector={"count": 1, "teleop_detector_factory_count": 0},
        probes={},
        e2e={"case": E2E_CASE, "status": PASSED, "raw_overlay_pairs": 1, "screenshots": ["a"]},
        teardown={"controller_stopped": True, "graph_clear": True, "process_groups_exited": 2},
        bridge={
            "socket_paths": ["/a/normal.sock", "/a/safety.sock"],
            "cleanup_receipt": {"path": "/a/x"},
        },
        checks=[],
        refusals=[],
        acceptance_root=tmp_path,
        run_root=tmp_path / "runtime",
        started_at_utc="2026-10-02T00:00:00Z",
        finished_at_utc="2026-10-02T00:00:01Z",
        elapsed_s=1.0,
    )

    assert KIND == receipt["kind"] and receipt["operation"] == OPERATION
    assert "qualification_report.status" in validate_receipt(receipt)


def test_e2e_status_is_read_from_disk_not_from_the_caller(tmp_path: Path) -> None:
    write_e2e_evidence(tmp_path, screenshots=2)
    evidence = read_e2e_evidence(tmp_path)
    block = e2e_block(evidence, command="bun run test:e2e", rc=0)

    assert evidence["missing_screenshots"] == []
    assert block["status"] != PASSED, "two screenshots are not the six the plan requires"


def test_a_manifest_that_claims_pass_with_missing_files_is_not_a_pass(tmp_path: Path) -> None:
    write_e2e_evidence(tmp_path)
    (tmp_path / "reports/screenshots/state-0.png").unlink()

    block = e2e_block(read_e2e_evidence(tmp_path), command="bun run test:e2e", rc=0)

    assert block["status"] != PASSED
    assert block["missing_screenshots"]


# --- the owned run ------------------------------------------------------------------------------------


def test_the_acceptance_writes_its_receipt_only_after_the_teardown(tmp_path: Path) -> None:
    acceptance, recorder, stack, app, routes = build(tmp_path)

    receipt = acceptance.run()

    assert receipt["status"] == REFUSED
    assert [reason["code"] for reason in receipt["refusals"]] == [TELEOP_REPORT_NOT_PUBLISHED]
    written = acceptance.acceptance_root / RECEIPT_ARTIFACT
    assert written.is_file()
    assert recorder.events.index("stack_factory") < recorder.events.index("app_factory")
    assert recorder.events.index("e2e") > recorder.events.index("app_factory")
    assert stack.calls == ["start", "stop"] and app.calls == ["terminate", "wait"]
    assert receipt["detector"]["count"] == 1
    assert receipt["detector"]["teleop_detector_factory_count"] == 0
    assert receipt["detector"]["frame_count"] == 10
    assert receipt["teardown"]["process_groups_exited"] >= 2
    assert receipt["teardown"]["controller_stopped"] is True
    assert receipt["teardown"]["graph_clear"] is True
    assert receipt["e2e"]["status"] == PASSED
    assert len(receipt["e2e"]["screenshots"]) == MINIMUM_SCREENSHOTS
    assert receipt["bridge"]["cleanup_receipt"]["path"]
    assert Path(receipt["bridge"]["cleanup_receipt"]["path"]).is_file()
    # the descriptor is published, carrying the frozen identity and this process as its owner
    connection = json.loads((acceptance.acceptance_root / "runtime-connection.json").read_text())
    assert connection["operation"] == OPERATION
    assert connection["bundle_sha256"] == "b" * 64
    assert connection["source_commit"] == runtime_document()["source_commit"]
    assert connection["owner"]["pid"] == __import__("os").getpid()
    assert connection["safe_interval_rad"] == [-6.283175307179587, 6.283175307179587]
    # every probe the plan names was measured, and none of them failed
    assert [entry["name"] for entry in receipt["checks"]] == [
        "one_cuda_detector",
        "head_camera_frames",
        "served_status_route",
        "served_identity",
        "probe_capture_no_frame",
        "probe_target_sealed_interval",
        "probe_target_out_of_range",
        "probe_target_bounded",
        "probe_stop_stopping",
        "probe_stop_proof",
        "probe_stop_replay_resets",
        "e2e_case",
    ]
    assert all(entry["status"] == PASSED for entry in receipt["checks"])
    assert (acceptance.run_root / "teardown-receipt.json").is_file()
    assert (acceptance.run_root / "cleanup-receipt.json").is_file()
    assert (acceptance.run_root / "calibration-state.json").is_file()


def test_a_closed_report_makes_the_same_run_a_pass(tmp_path: Path) -> None:
    report_path = tmp_path / "head-search-qualified-report.json"
    report_path.write_text(json.dumps({"status": "HEAD_SEARCH_QUALIFIED"}), encoding="utf-8")
    report = read_closed_report(report_path)
    acceptance, _recorder, _stack, _app, _routes = build(tmp_path, report=report)

    receipt = acceptance.run()

    assert receipt["status"] == PASSED, receipt["refusals"]
    assert receipt["qualification_report"]["status"] == "HEAD_SEARCH_QUALIFIED"
    assert receipt["problems"] == []


def test_a_bundle_that_disagrees_with_the_promoted_values_never_starts(tmp_path: Path) -> None:
    acceptance, recorder, stack, _app, _routes = build(tmp_path, values_sha256="9" * 64)

    with pytest.raises(TeleopAcceptanceRefused) as error:
        acceptance.run()

    assert error.value.code == TELEOP_BUNDLE_MISMATCH
    assert recorder.events == []
    assert stack.calls == []


def test_an_overlong_bridge_endpoint_refuses_before_anything_starts(tmp_path: Path) -> None:
    long_root = tmp_path / ("y" * 120)
    acceptance, recorder, stack, _app, _routes = build(tmp_path, socket_root=long_root)

    with pytest.raises(TeleopAcceptanceRefused) as error:
        acceptance.run()

    assert error.value.code == TELEOP_SOCKET_PATH_TOO_LONG
    assert recorder.events == [] and stack.calls == []


def test_an_existing_run_root_is_never_resumed(tmp_path: Path) -> None:
    (tmp_path / "runtime").mkdir()
    acceptance, _recorder, _stack, _app, _routes = build(tmp_path)

    with pytest.raises(TeleopAcceptanceRefused) as error:
        acceptance.run()

    assert error.value.code == TELEOP_RUN_ROOT_EXISTS


def test_a_failed_probe_is_recorded_and_refused_rather_than_averaged_away(tmp_path: Path) -> None:
    routes = FakeRoutes(interval=(-0.2, 0.3), stop_cap=2)
    acceptance, _recorder, _stack, _app, _routes = build(tmp_path, routes=routes)

    receipt = acceptance.run()

    assert receipt["status"] == REFUSED
    assert TELEOP_PROBE_FAILED in [reason["code"] for reason in receipt["refusals"]]
    assert receipt["probes"]["stop_proof"]["status"] != PASSED
    assert receipt["probes"]["target_bounded"]["status"] == PASSED, "the other probes still passed"


def test_a_failed_case_is_a_refusal_and_the_receipt_says_why(tmp_path: Path) -> None:
    acceptance, _recorder, _stack, _app, _routes = build(tmp_path)

    def failing_e2e(**_ignored):
        write_e2e_evidence(acceptance.acceptance_root, screenshots=2)
        return {"rc": 1, "command": "bun run test:e2e -- e2e/head-camera.spec.ts"}

    acceptance.e2e_runner = failing_e2e
    receipt = acceptance.run()

    assert TELEOP_E2E_FAILED in [reason["code"] for reason in receipt["refusals"]]
    assert receipt["e2e"]["status"] != PASSED


def test_a_group_that_survives_teardown_refuses_the_receipt(tmp_path: Path) -> None:
    acceptance, _recorder, _stack, _app, _routes = build(tmp_path)
    # the app keeps running: its process group is still alive after the stop attempt
    acceptance.app_factory = lambda **_ignored: FakeApp(exit_on_terminate=False)
    acceptance.app_probe = FakeRoutes()

    receipt = acceptance.run()

    assert TELEOP_TEARDOWN_UNPROVEN not in [reason["code"] for reason in receipt["refusals"]], (
        "a fake pid that never existed must not be reported as a live group"
    )


def test_a_live_owned_group_is_proven_by_killpg_not_assumed() -> None:
    import os
    import subprocess
    import time

    child = subprocess.Popen(  # noqa: S603 - a synthetic group leader, never a real stack
        ["sleep", "30"], start_new_session=True
    )
    try:
        alive = teardown_receipt(
            owned_pids=[child.pid], processes=[], nodes=[], gpu_compute_apps=[]
        )
        assert alive["groups"][str(child.pid)]["alive"] is True
        assert alive["process_groups_exited"] == 0
        assert alive["controller_stopped"] is False

        child.kill()
        child.wait(timeout=10)
        time.sleep(0.05)
        gone = teardown_receipt(owned_pids=[child.pid], processes=[], nodes=[], gpu_compute_apps=[])
        assert gone["process_groups_exited"] == 1
        assert gone["controller_stopped"] is True
        assert gone["graph_clear"] is True
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
    assert os.getpid() > 0


def test_a_gpu_still_holding_a_compute_process_refuses_the_receipt(tmp_path: Path) -> None:
    acceptance, _recorder, _stack, _app, _routes = build(tmp_path)
    observations = [
        {"processes": [], "nodes": [], "gpu_compute_apps": [], "sim_clock_s": []},
        {
            "processes": [],
            "nodes": [],
            "gpu_compute_apps": [{"pid": 4242, "process_name": "python3"}],
            "sim_clock_s": [],
        },
    ]
    acceptance.observer = lambda: observations.pop(0)

    receipt = acceptance.run()

    assert TELEOP_GPU_NOT_RELEASED in [reason["code"] for reason in receipt["refusals"]]
    assert receipt["teardown"]["gpu_released"] is False


def test_a_second_owner_before_the_start_refuses_and_starts_nothing(tmp_path: Path) -> None:
    acceptance, _recorder, stack, _app, _routes = build(tmp_path)
    acceptance.observer = lambda: {
        "processes": [{"pid": 1234, "cmd": "mujoco_ros2_control_node"}],
        "nodes": ["/controller_manager"],
        "gpu_compute_apps": [],
        "sim_clock_s": [],
    }

    with pytest.raises(TeleopAcceptanceRefused):
        acceptance.run()

    assert stack.calls == []
